"""
nicsoft/tests/test_issue349_lichess_rating_cadence.py — AlChess

Issue #349 :

Partie 1 — ma cote et ma nouvelle cote :
  1. Ma cote (comme celle de l'adversaire), lue dans le gameFull, jamais
     devinée, transmise par lichess_init (couleur blanche/noire, provisoire,
     absente).
  2. WhiteElo/BlackElo dans les en-têtes PGN, dans le bon ordre selon la
     couleur de l'utilisateur.
  3. Nouvelle cote en fin de partie classée — lecture publique de
     /api/user/<id> (GameClient.fetch_my_rating), jamais de jeton/scope
     supplémentaire, une seule nouvelle tentative si inchangée, silencieux
     en cas d'échec réseau. Remplace l'ancienne fetch_rating_diff (#344,
     retirée).

Partie 2 — dossier « Classée » par cadence :
  1. pgn_cadence_folder_name() — nom de sous-dossier sûr.
  2. Une partie classée est enregistrée dans Lichess/Classée/<cadence>/,
     une partie amicale reste dans Lichess/Amicale/ (inchangé).
  3. En-tête Event dit « classée » (avec la cadence) pour une partie
     classée, jamais pour une amicale.

Entièrement hors ligne (faux transport Lichess scripté, faux plateau USB,
GAMES_DIR isolé par la fixture autouse de conftest.py) — voir
nicsoft/tests/conftest.py::_guard_no_real_lichess_network/_isolate_games_dir.
"""
import time

import pytest

from nicsoft.modes.lichess.game import (
    LichessGame,
    build_pgn_headers,
    pgn_cadence_folder_name,
)
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.transport import TransportNetworkError
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport, _ok
from nicsoft.tests.test_issue331_lichess_opponent_alerts import _AlertBoard, _make_game


# ═══════════════════════════════════════════════════════════════════════
# Partie 2, point 1 : pgn_cadence_folder_name() — fonction pure.
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("clock_limit_s, clock_increment_s, expected", [
    (600, 0, "10+0"),
    (900, 10, "15+10"),
    (1800, 0, "30+0"),
    (3600, 0, "60+0"),
    (5400, 30, "90+30"),
])
def test_pgn_cadence_folder_name(clock_limit_s, clock_increment_s, expected):
    assert pgn_cadence_folder_name(clock_limit_s, clock_increment_s) == expected


def test_pgn_cadence_folder_name_sans_caractere_interdit_windows():
    interdits = set('<>:"/\\|?*')
    for clock_limit_s, clock_increment_s in [(600, 0), (900, 10), (5400, 30)]:
        name = pgn_cadence_folder_name(clock_limit_s, clock_increment_s)
        assert not (set(name) & interdits), name


# ═══════════════════════════════════════════════════════════════════════
# Partie 1, point 2 : WhiteElo/BlackElo dans build_pgn_headers().
# ═══════════════════════════════════════════════════════════════════════

def test_build_pgn_headers_elo_utilisateur_blanc():
    headers = build_pgn_headers(
        "gid", "Alain", "white", 1, 900, 10, "1-0", "2026.11.15",
        opponent_name="Adversaire", user_rating=1400, opponent_rating=1500,
    )
    assert headers["WhiteElo"] == "1400"
    assert headers["BlackElo"] == "1500"


def test_build_pgn_headers_elo_utilisateur_noir():
    headers = build_pgn_headers(
        "gid", "Alain", "black", 1, 900, 10, "0-1", "2026.11.15",
        opponent_name="Adversaire", user_rating=1400, opponent_rating=1500,
    )
    assert headers["WhiteElo"] == "1500"
    assert headers["BlackElo"] == "1400"


def test_build_pgn_headers_elo_absent_si_cote_inconnue():
    headers = build_pgn_headers("gid", "Alain", "white", 1, 900, 10, "1-0", "2026.11.15")
    assert "WhiteElo" not in headers
    assert "BlackElo" not in headers


def test_build_pgn_headers_elo_partiel_un_seul_cote_connu():
    headers = build_pgn_headers(
        "gid", "Alain", "white", 1, 900, 10, "1-0", "2026.11.15", user_rating=1400,
    )
    assert headers["WhiteElo"] == "1400"
    assert "BlackElo" not in headers


# ═══════════════════════════════════════════════════════════════════════
# Partie 1, point 1 : ma cote lue depuis _apply_game_full, transmise par
# lichess_init — deux orientations, provisoire, absente.
# ═══════════════════════════════════════════════════════════════════════

def _started_humain(monkeypatch, user_color, white_extra=None, black_extra=None):
    """Démarre une partie classée contre un humain — `white_extra`/
    `black_extra` décorent toujours le côté Blancs/Noirs respectivement
    (quel que soit `user_color`), comme le ferait un vrai gameFull."""
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=_AlertBoard())
    game._known_user_color = user_color
    white_id = "alain" if user_color == "white" else "opp"
    black_id = "opp" if user_color == "white" else "alain"
    white = {"id": white_id, **(white_extra or {})}
    black = {"id": black_id, **(black_extra or {})}
    game._apply_game_full({
        "white": white, "black": black, "rated": True,
        "state": {"status": "started", "moves": ""},
    })
    return game, events


def test_ma_cote_transmise_couleur_blanche(monkeypatch):
    game, events = _started_humain(
        monkeypatch, "white", white_extra={"rating": 1400, "provisional": False},
        black_extra={"rating": 1500, "provisional": False},
    )
    assert game.user_rating == 1400
    assert game.user_provisional is False
    inits = [d for t, d in events if t == "lichess_init"]
    assert inits[-1]["user_rating"] == 1400
    assert inits[-1]["user_provisional"] is False
    assert inits[-1]["opponent_rating"] == 1500
    assert inits[-1]["opponent_provisional"] is False


def test_ma_cote_transmise_couleur_noire(monkeypatch):
    """Même chose en jouant les Noirs — l'orientation de l'échiquier ne
    doit rien changer à la présence/valeur de la cote transmise."""
    game, events = _started_humain(
        monkeypatch, "black", white_extra={"rating": 1500, "provisional": False},
        black_extra={"rating": 1400, "provisional": True},
    )
    assert game.user_rating == 1400
    assert game.user_provisional is True
    inits = [d for t, d in events if t == "lichess_init"]
    assert inits[-1]["user_rating"] == 1400
    assert inits[-1]["user_provisional"] is True
    assert inits[-1]["opponent_rating"] == 1500


def test_ma_cote_provisoire_transmise(monkeypatch):
    game, events = _started_humain(
        monkeypatch, "white", white_extra={"rating": 900, "provisional": True},
    )
    inits = [d for t, d in events if t == "lichess_init"]
    assert inits[-1]["user_rating"] == 900
    assert inits[-1]["user_provisional"] is True


def test_ma_cote_absente_jamais_zero(monkeypatch):
    """Aucune cote transmise par Lichess (ex. compte anonyme côté test) —
    None, jamais 0 ni une valeur devinée."""
    game, events = _started_humain(monkeypatch, "white")
    assert game.user_rating is None
    inits = [d for t, d in events if t == "lichess_init"]
    assert inits[-1]["user_rating"] is None


def test_ma_cote_contre_ia_si_fournie(monkeypatch):
    """Contre l'IA de Lichess : mon côté porte quand même `rating` (pas
    `aiLevel`, réservé au côté adverse) — affiché si Lichess le fournit."""
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=_AlertBoard())
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain", "rating": 1200, "provisional": False},
        "rated": False,
        "state": {"status": "started", "moves": ""},
    })
    assert game.user_color == "black"
    assert game.user_rating == 1200
    inits = [d for t, d in events if t == "lichess_init"]
    assert inits[-1]["user_rating"] == 1200
    assert inits[-1]["opponent_rating"] is None


# ═══════════════════════════════════════════════════════════════════════
# Partie 1, point 3 : GameClient.fetch_my_rating() — lecture publique.
# ═══════════════════════════════════════════════════════════════════════

def test_fetch_my_rating_trouve_la_cote_de_la_cadence():
    transport = FakeTransport(requests=[
        _ok({"perfs": {"rapid": {"rating": 1413}, "blitz": {"rating": 1200}}}),
    ])
    client = GameClient("lip_test", transport=transport)
    assert client.fetch_my_rating("alain", "rapid") == 1413


def test_fetch_my_rating_categorie_absente_renvoie_none():
    transport = FakeTransport(requests=[_ok({"perfs": {"blitz": {"rating": 1200}}})])
    client = GameClient("lip_test", transport=transport)
    assert client.fetch_my_rating("alain", "rapid") is None


def test_fetch_my_rating_erreur_reseau_renvoie_none_sans_exception():
    transport = FakeTransport(requests=[
        lambda method, url, token, fields: TransportNetworkError("réseau indisponible"),
    ])
    client = GameClient("lip_test", transport=transport)
    assert client.fetch_my_rating("alain", "rapid") is None


def test_fetch_my_rating_sans_username_ou_sans_cadence_renvoie_none():
    client = GameClient("lip_test", transport=FakeTransport())
    assert client.fetch_my_rating("", "rapid") is None
    assert client.fetch_my_rating("alain", "") is None


# ═══════════════════════════════════════════════════════════════════════
# Partie 1, point 3 : LichessGame._maybe_fetch_new_rating() — orchestration.
# ═══════════════════════════════════════════════════════════════════════

def _wait_for_event(events, etype, timeout_s=2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        found = [d for t, d in events if t == etype]
        if found:
            return found[-1]
        time.sleep(0.02)
    return None


def test_nouvelle_cote_inchangee_puis_changee_a_la_seconde_tentative(monkeypatch):
    monkeypatch.setattr(LichessGame, "_NEW_RATING_INITIAL_DELAY_S", 0.01)
    monkeypatch.setattr(LichessGame, "_NEW_RATING_RETRY_DELAY_S", 0.01)
    game, events = _started_humain(
        monkeypatch, "white", white_extra={"rating": 1400, "provisional": False},
    )
    calls = []

    def fake_fetch(username, speed_key):
        calls.append((username, speed_key))
        return 1400 if len(calls) == 1 else 1413

    monkeypatch.setattr(game.client, "fetch_my_rating", fake_fetch)
    game._maybe_fetch_new_rating()
    payload = _wait_for_event(events, "lichess_new_rating")
    assert payload == {"new_rating": 1413, "rating_diff": 13}
    assert len(calls) == 2
    assert calls[0][0] == "alain"


def test_nouvelle_cote_echec_reseau_silencieux(monkeypatch):
    monkeypatch.setattr(LichessGame, "_NEW_RATING_INITIAL_DELAY_S", 0.01)
    monkeypatch.setattr(LichessGame, "_NEW_RATING_RETRY_DELAY_S", 0.01)
    game, events = _started_humain(
        monkeypatch, "white", white_extra={"rating": 1400, "provisional": False},
    )
    monkeypatch.setattr(game.client, "fetch_my_rating", lambda username, speed_key: None)
    game._maybe_fetch_new_rating()
    time.sleep(0.3)
    assert not any(t == "lichess_new_rating" for t, _ in events)


def test_nouvelle_cote_jamais_tentee_sans_cote_de_depart(monkeypatch):
    game, events = _started_humain(monkeypatch, "white")  # pas de rating connu
    called = []
    monkeypatch.setattr(game.client, "fetch_my_rating", lambda *a, **kw: called.append(1))
    game._maybe_fetch_new_rating()
    time.sleep(0.2)
    assert called == []
    assert not any(t == "lichess_new_rating" for t, _ in events)


def test_finalize_classee_appelle_la_nouvelle_cote_jamais_lancienne(monkeypatch):
    """_finalize() doit appeler _maybe_fetch_new_rating — plus aucune trace
    de l'ancienne fetch_rating_diff (retirée, voir game_client.py)."""
    assert not hasattr(GameClient, "fetch_rating_diff")
    monkeypatch.setattr(LichessGame, "_NEW_RATING_INITIAL_DELAY_S", 0.01)
    monkeypatch.setattr(LichessGame, "_NEW_RATING_RETRY_DELAY_S", 0.01)
    game, events = _started_humain(
        monkeypatch, "white", white_extra={"rating": 1400, "provisional": False},
    )
    monkeypatch.setattr(game.client, "fetch_my_rating", lambda username, speed_key: 1420)
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()
    payload = _wait_for_event(events, "lichess_new_rating")
    assert payload == {"new_rating": 1420, "rating_diff": 20}


def test_finalize_amicale_ne_tente_jamais_la_nouvelle_cote(monkeypatch):
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=_AlertBoard())
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain", "rating": 1400}, "black": {"id": "opp", "rating": 1500},
        "rated": False,
        "state": {"status": "started", "moves": ""},
    })
    called = []
    monkeypatch.setattr(game.client, "fetch_my_rating", lambda *a, **kw: called.append(1))
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()
    time.sleep(0.2)
    assert called == []


# ═══════════════════════════════════════════════════════════════════════
# Partie 2 : PGN rangé dans Classée/<cadence> ou Amicale, en-tête Event.
# ═══════════════════════════════════════════════════════════════════════

def test_save_pgn_partie_classee_rangee_dans_classee_cadence(monkeypatch, _isolate_games_dir):
    game, events = _started_humain(
        monkeypatch, "white", white_extra={"rating": 1400}, black_extra={"rating": 1500},
    )
    game.clock_limit_s, game.clock_increment_s = 600, 0  # "10+0"
    game._save_pgn("1-0")
    pgn_path = _isolate_games_dir / "Lichess" / "Classée" / "10+0"
    files = list(pgn_path.glob("*.pgn"))
    assert len(files) == 1, f"PGN non trouvé sous {pgn_path}"
    content = files[0].read_text(encoding="utf-8")
    assert "[WhiteElo \"1400\"]" in content
    assert "[BlackElo \"1500\"]" in content
    assert "classée (10+0)" in content


def test_save_pgn_autre_cadence_classee_15_10(monkeypatch, _isolate_games_dir):
    game, events = _started_humain(monkeypatch, "white")
    game.clock_limit_s, game.clock_increment_s = 900, 10  # "15+10"
    game._save_pgn("1-0")
    pgn_path = _isolate_games_dir / "Lichess" / "Classée" / "15+10"
    assert list(pgn_path.glob("*.pgn")), f"PGN non trouvé sous {pgn_path}"


def test_save_pgn_partie_amicale_contre_humain_reste_dans_amicale(monkeypatch, _isolate_games_dir):
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=_AlertBoard())
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "rated": False,
        "state": {"status": "started", "moves": ""},
    })
    game._save_pgn("1-0")
    amicale_dir = _isolate_games_dir / "Lichess" / "Amicale"
    classee_dir = _isolate_games_dir / "Lichess" / "Classée"
    files = list(amicale_dir.glob("*.pgn"))
    assert files
    assert not classee_dir.exists()
    content = files[0].read_text(encoding="utf-8")
    assert '[Event "Lichess, amicale contre un humain"]' in content
    assert "classée" not in content


def test_save_pgn_partie_amicale_contre_ia_reste_dans_amicale(monkeypatch, _isolate_games_dir):
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=_AlertBoard())
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "rated": False,
        "state": {"status": "started", "moves": ""},
    })
    game._save_pgn("0-1")
    amicale_dir = _isolate_games_dir / "Lichess" / "Amicale"
    files = list(amicale_dir.glob("*.pgn"))
    assert files
    assert not (_isolate_games_dir / "Lichess" / "Classée").exists()
    content = files[0].read_text(encoding="utf-8")
    assert '[Event "Lichess, amicale contre l\'IA niveau 1"]' in content


def test_save_pgn_evenement_dit_classee_pour_partie_classee(monkeypatch, _isolate_games_dir):
    game, events = _started_humain(monkeypatch, "white")
    game.clock_limit_s, game.clock_increment_s = 600, 0
    game._save_pgn("1-0")
    pgn_path = _isolate_games_dir / "Lichess" / "Classée" / "10+0"
    content = list(pgn_path.glob("*.pgn"))[0].read_text(encoding="utf-8")
    assert '[Event "Lichess, classée (10+0) contre un humain"]' in content


def test_dossiers_crees_a_la_demande_jamais_a_lavance(_isolate_games_dir):
    """Avant toute partie classée enregistrée, aucun dossier Classée ne
    doit exister (créé à la demande seulement — issue #349, partie 2,
    point 1)."""
    assert not (_isolate_games_dir / "Lichess").exists()
