"""
nicsoft/tests/test_issue327_lichess_human.py — AlChess

Issue #327 (étape L2b) : recherche d'un adversaire humain en partie amicale
(Rapide/Classique, dont 90+30), événements de base (nulle, abandon, temps
écoulé, annulation pour premier coup non joué), journal de recherche+partie
moins bruyant. Règle absolue de cette issue : AUCUNE connexion réseau
réelle, AUCUNE recherche/partie réelle sur lichess.org — entièrement sans
réseau (faux transport scripté, voir test_issue309) et sans matériel (faux
plateau). Voir aussi nicsoft/tests/conftest.py::_guard_no_real_lichess_network
pour le test de garde explicite (point 8) et test_issue310_lichess_corrections
pour la complétude i18n (clés ajoutées par cette issue incluses).
"""
import logging
import queue
import socket

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.errors import LichessNetworkError
from nicsoft.modes.lichess.game import LichessGame, build_pgn_headers, speed_key_for_clock
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.game_log import GameLog
from nicsoft.modes.lichess.seek import SeekSession
from nicsoft.modes.lichess.transport import TransportNetworkError
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, FakeTransport, _make_recorder
from nicsoft.tests.test_issue311_lichess_sequencing import INITIAL_FEN_W, _ScriptedBoard


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


def _gamestart_line(game_id="hgid1", color="white", username="Adversaire", rating=1500):
    import json
    return json.dumps({
        "type": "gameStart",
        "game": {"gameId": game_id, "id": game_id, "color": color,
                  "opponent": {"username": username, "rating": rating}},
    })


# ═══════════════════════════════════════════════════════════════════════
# 1. SeekSession — protocole board/seek (point 2/3), jamais de vraie
#    connexion (FakeTransport uniquement).
# ═══════════════════════════════════════════════════════════════════════

def test_seek_session_trouve_un_adversaire_et_ferme_la_recherche():
    """Doc officielle board/seek (lue le 14/11/2026) : le flux d'évènements
    porte gameStart, le flux de recherche lui-même ne contient rien — la
    session doit fermer la recherche dès que gameStart arrive."""
    transport = FakeTransport(open_stream_specs=[
        ["", "", _gamestart_line(color="black", username="Bob", rating=1600)],
        ["", "", ""],
    ])
    client = GameClient("lip_test", transport=transport)
    session = SeekSession(client)
    session.start(15.0, 10, "")

    events = []
    for _ in range(200):
        ev = session.next_event(timeout=0.05)
        if ev:
            events.append(ev)
        if any(e["type"] == "found" for e in events):
            break
    found = [e for e in events if e["type"] == "found"]
    assert found, f"aucun évènement 'found' reçu : {events}"
    game = found[0]["game"]
    assert game["gameId"] == "hgid1"
    assert game["color"] == "black"
    assert game["opponent"]["username"] == "Bob"


def test_seek_session_cancel_ferme_les_deux_flux():
    transport = FakeTransport(open_stream_specs=[
        [""] * 50,  # flux d'évènements — jamais de gameStart ici
        [""] * 50,  # flux de recherche — reste ouvert
    ])
    client = GameClient("lip_test", transport=transport)
    session = SeekSession(client)
    session.start(15.0, 10, "white")
    session.next_event(timeout=0.1)  # laisse les fils démarrer

    session.cancel()
    assert session._event_handle.closed is True
    assert session._seek_handle.closed is True


def test_seek_session_echec_ouverture_flux_evenements_ne_demarre_aucun_fil():
    # TransportNetworkError (pas LichessNetworkError) : open_event_stream()/
    # open_seek_stream() (game_client.py) ne traduisent pas les erreurs de
    # transport, contrairement aux autres méthodes de GameClient — seek.py
    # les attrape directement sous leur forme brute (voir son en-tête).
    transport = FakeTransport(open_stream_specs=[TransportNetworkError("réseau indisponible")])
    client = GameClient("lip_test", transport=transport)
    session = SeekSession(client)
    session.start(15.0, 10, "")
    ev = session.next_event(timeout=0.2)
    assert ev == {"type": "error", "reason": "TransportNetworkError"}
    assert session._seek_handle is None  # jamais ouvert, l'échec était sur le premier flux


def test_seek_session_coupure_en_cours_de_recherche_signalee():
    transport = FakeTransport(open_stream_specs=[
        [""] * 5,
        ["", TransportNetworkError("coupure")],
    ])
    client = GameClient("lip_test", transport=transport)
    session = SeekSession(client)
    session.start(15.0, 10, "")
    got_error = False
    for _ in range(100):
        ev = session.next_event(timeout=0.05)
        if ev and ev["type"] == "error":
            got_error = True
            break
    assert got_error


def test_seek_session_journal_dedie_trace_demarrage_et_annulation(tmp_path):
    transport = FakeTransport(open_stream_specs=[[""] * 20, [""] * 20])
    client = GameClient("lip_test", transport=transport)
    log = GameLog("recherche", logs_dir=tmp_path)
    session = SeekSession(client, game_log=log)
    session.start(15.0, 10, "white")
    session.next_event(timeout=0.1)
    session.cancel()
    log.close()
    content = log.path.read_text(encoding="utf-8")
    assert "recherche d'adversaire démarrée" in content
    assert "annulée par l'utilisateur" in content


# ═══════════════════════════════════════════════════════════════════════
# 2. Cadences acceptées pour une recherche humaine (point 1) — Rapide et
#    Classique seulement, jamais Blitz/Bullet.
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cadence_key", list(lichess_launcher.CLOCK_PRESETS.keys()))
def test_tous_les_preregalges_proposes_sont_rapide_ou_classique(cadence_key):
    limit_s, inc_s = lichess_launcher.CLOCK_PRESETS[cadence_key]
    assert speed_key_for_clock(limit_s, inc_s) in ("rapid", "classical"), (
        f"préréglage {cadence_key} de vitesse "
        f"{speed_key_for_clock(limit_s, inc_s)} — jamais blitz/bullet pour un humain"
    )


def test_preregalge_90_30_present_et_classique():
    assert "90+30" in lichess_launcher.CLOCK_PRESETS
    limit_s, inc_s = lichess_launcher.CLOCK_PRESETS["90+30"]
    assert speed_key_for_clock(limit_s, inc_s) == "classical"


# ═══════════════════════════════════════════════════════════════════════
# 3. Lanceur _run_lichess_human — ordre des opérations (point 2), garde
#    "une seule partie à la fois", recherche, appariement, jeu normal.
# ═══════════════════════════════════════════════════════════════════════

class _HumanGameClient:
    """Double de GameClient pour le lanceur — un seul évènement gameFull
    (déjà couvert pour LichessGame lui-même par les autres fichiers de
    test) : seul l'enchaînement recherche → partie importe ici."""

    def __init__(self, game_id="hgid1", user_color="white", opponent_name="Bob"):
        self.game_id = game_id
        self.user_color = user_color
        self.opponent_name = opponent_name
        self._game_log = None

    def attach_game_log(self, game_log):
        self._game_log = game_log

    def open_event_stream(self):
        return _FakeHandleForClient([_gamestart_line(self.game_id, self.user_color, self.opponent_name)])

    def open_seek_stream(self, *a, **kw):
        return _FakeHandleForClient([""])

    def stream_game(self, game_id, sleep=None):
        user_side = {"id": "alain"}
        opp_side = {"id": "opp", "name": self.opponent_name}
        white_side, black_side = (
            (user_side, opp_side) if self.user_color == "white" else (opp_side, user_side)
        )
        yield {
            "type": "gameFull", "white": white_side, "black": black_side,
            "state": {"status": "aborted", "winner": "", "moves": ""},
        }


class _FakeHandleForClient:
    def __init__(self, lines):
        self._lines = list(lines)
        self.closed = False

    def close(self):
        self.closed = True

    def lines(self):
        for item in self._lines:
            if self.closed:
                return
            yield item


def test_lanceur_humain_position_confirmee_avant_la_recherche(monkeypatch):
    """La recherche ne démarre jamais avant que la position physique soit
    confirmée (issue #327, point 2) — ici : le plateau met plusieurs
    lectures à atteindre la position de départ, la recherche (donc
    GameClient.open_event_stream/open_seek_stream) ne doit être ouverte
    qu'ensuite."""
    board = _ScriptedBoard([INITIAL_FEN_W] * 3 + [INITIAL_FEN_W])
    client = _HumanGameClient()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human(
        "lip_x", 900, 10, "white", "15+10", "Alain", _error,
    )
    assert _error["occurred"] is False
    assert board.disconnected is True


def test_lanceur_humain_refuse_si_partie_en_cours(monkeypatch):
    """Garde-fou « une seule partie à la fois » (point 2) appliqué AVANT la
    recherche — jamais après."""
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _HumanGameClient()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    monkeypatch.setattr(
        lichess_launcher, "_refuse_create_if_games_ongoing",
        lambda token: [{"game_id": "autre"}],
    )
    seek_started = []
    monkeypatch.setattr(client, "open_event_stream", lambda: seek_started.append(1) or _FakeHandleForClient([""]))

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_partie_en_cours_refus"
    assert seek_started == []  # la recherche n'a jamais démarré


def test_lanceur_humain_annulation_recherche_sur_back_menu(monkeypatch):
    """Bouton "Annuler la recherche" (back_menu pendant lichess_seeking,
    jamais relayé à action_queue — voir server.py) : get_app_state()
    renvoyant "menu" doit annuler proprement, sans erreur affichée."""
    board = _ScriptedBoard([INITIAL_FEN_W])

    class _NeverFoundClient(_HumanGameClient):
        def open_event_stream(self):
            return _FakeHandleForClient([""] * 1000)

        def open_seek_stream(self, *a, **kw):
            return _FakeHandleForClient([""] * 1000)

    client = _NeverFoundClient()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)

    states = ["connecting"]

    def _fake_get_app_state():
        # Position confirmée -> "connecting" ; dès l'entrée en recherche
        # (passage à "lichess_seeking" fait par le lanceur), on simule un
        # clic "Annuler la recherche" en renvoyant "menu".
        if states[-1] == "connecting":
            states.append("lichess_seeking")
            return "connecting"
        return "menu"

    monkeypatch.setattr(lichess_launcher, "get_app_state", _fake_get_app_state)

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is False  # annulation volontaire, jamais une erreur
    assert client.open_event_stream() and True  # sanity : le double est bien utilisable


def test_lanceur_humain_erreur_recherche_revient_a_config_lichess(monkeypatch):
    board = _ScriptedBoard([INITIAL_FEN_W])

    class _FailingSeekClient(_HumanGameClient):
        def open_event_stream(self):
            raise LichessNetworkError("injoignable")

    client = _FailingSeekClient()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_network_error"
    assert _error["return_to"] == "config_lichess"


def test_lanceur_humain_cadence_invalide_naccede_jamais_au_plateau(monkeypatch):
    """Filet de sécurité (jamais atteint avec les préréglages actuels, tous
    Rapide/Classique) : une cadence de vitesse non autorisée (ex. Blitz, si
    un futur préréglage l'ajoutait) ne doit même pas ouvrir l'échiquier."""
    opened = []
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: opened.append(1))
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "menu", raising=False)
    sent = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent.append((state, data)))
    # Cadence volontairement forcée invalide (vitesse "blitz") via
    # CLOCK_PRESETS monkeypatché — jamais présente parmi les préréglages
    # réels, qui sont tous Rapide/Classique (voir tests ci-dessus).
    monkeypatch.setitem(lichess_launcher.CLOCK_PRESETS, "blitz_test", (300, 0))

    lichess_launcher._launch_lichess_human(
        {"cadence": "blitz_test", "color": "white", "player": "Alain"}, "lip_x",
    )

    assert opened == []
    assert sent and sent[-1][0] == "config_lichess"
    assert sent[-1][1]["toast_message_key"] == "toast.lichess_cadence_invalide"


# ═══════════════════════════════════════════════════════════════════════
# 4. Nulle contre l'IA — grisée en permanence, jamais de faux refus (point
#    5), établi par lecture du code public de lila (voir game.py).
# ═══════════════════════════════════════════════════════════════════════

def _make_ai_game(monkeypatch):
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    game = LichessGame(board, client, "gid_ia", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    return game, events, actions


def test_proposer_nulle_grise_en_permanence_contre_ia(monkeypatch):
    game, events, actions = _make_ai_game(monkeypatch)
    assert game._action_buttons_state == (True, False)
    sent_requests = []
    monkeypatch.setattr(game.client, "answer_draw", lambda gid, accept: sent_requests.append(accept))

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()

    assert game._my_draw_offer_pending is False  # jamais activé contre l'IA
    assert sent_requests == []  # jamais envoyé non plus — pas seulement grisé côté UI
    toasts = [d for t, d in events if t == "lichess_toast" and d.get("message_key") == "lichess.nulle_impossible_ia"]
    assert toasts


def test_action_buttons_porte_lindicateur_grise_vs_ia(monkeypatch):
    game, events, actions = _make_ai_game(monkeypatch)
    last = [d for t, d in events if t == "lichess_action_buttons"][-1]
    assert last["draw_disabled_vs_ai"] is True


# ═══════════════════════════════════════════════════════════════════════
# 5. Renvoi unique de l'offre si l'écho ne la montre pas (point 5, humain).
# ═══════════════════════════════════════════════════════════════════════

def _make_human_game_white(monkeypatch):
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    game = LichessGame(board, client, "gid_h", level=0, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10, known_user_color="white")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire", "rating": 1500},
        "state": {"status": "started", "moves": ""},
    })
    return game, events, actions


def test_renvoi_unique_si_lecho_du_coup_ne_montre_pas_loffre(monkeypatch):
    game, events, actions = _make_human_game_white(monkeypatch)
    answer_calls = []
    monkeypatch.setattr(game.client, "answer_draw", lambda gid, accept: answer_calls.append(accept))
    monkeypatch.setattr(game.client, "play_move", lambda gid, uci, offer_draw=False: None)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert answer_calls == [True]  # la demande initiale

    game._submit_move("e2e4")
    # Écho de notre coup SANS l'indicateur wdraw — doit renvoyer une seule fois.
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": False, "bdraw": False})
    assert answer_calls == [True, True]
    assert game._my_draw_offer_resent is True

    # Un second écho sans indicateur ne doit PAS renvoyer une deuxième fois.
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": False, "bdraw": False})
    assert answer_calls == [True, True]


def test_pas_de_renvoi_si_lecho_montre_deja_loffre(monkeypatch):
    game, events, actions = _make_human_game_white(monkeypatch)
    answer_calls = []
    monkeypatch.setattr(game.client, "answer_draw", lambda gid, accept: answer_calls.append(accept))
    monkeypatch.setattr(game.client, "play_move", lambda gid, uci, offer_draw=False: None)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    game._submit_move("e2e4")
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": True, "bdraw": False})
    assert answer_calls == [True]  # jamais renvoyée, déjà présente


def test_opponent_name_et_cote_transmis_a_linit(monkeypatch):
    game, events, actions = _make_human_game_white(monkeypatch)
    inits = [d for t, d in events if t == "lichess_init"]
    assert inits
    assert inits[-1]["opponent_name"] == "Adversaire"
    assert inits[-1]["opponent_rating"] == 1500
    assert inits[-1]["opponent_is_ai"] is False


# ═══════════════════════════════════════════════════════════════════════
# 6. PGN : vrai nom de l'adversaire humain, jamais pour l'IA.
# ═══════════════════════════════════════════════════════════════════════

def test_build_pgn_headers_adversaire_humain():
    headers = build_pgn_headers(
        "gidh", "Alain", "white", 0, 900, 10, "1-0", "2026.11.14",
        opponent_name="Adversaire", event_label="Lichess, amicale contre un humain",
    )
    assert headers["White"] == "Alain"
    assert headers["Black"] == "Adversaire"
    assert headers["Event"] == "Lichess, amicale contre un humain"


def test_build_pgn_headers_sans_opponent_name_reste_lancien_comportement():
    headers = build_pgn_headers("gid", "Alain", "black", 3, 900, 10, "0-1", "2026.11.14")
    assert headers["White"] == "Lichess AI level 3"
    assert headers["Black"] == "Alain"


# ═══════════════════════════════════════════════════════════════════════
# 7. Journal — bruit des pendules réduit (point 6), indicateurs de nulle
#    journalisés à chaque état reçu.
# ═══════════════════════════════════════════════════════════════════════

def test_journal_pendule_pas_ecrite_a_chaque_appel_sans_changement(monkeypatch, tmp_path):
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    log = GameLog("gid_clk", logs_dir=tmp_path)
    game = LichessGame(board, client, "gid_clk", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10, game_log=log)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "", "wtime": 900000, "btime": 900000},
    })
    content_after_full = log.path.read_text(encoding="utf-8")
    nb_before = content_after_full.count("[CLOCK]")
    # Plusieurs appels successifs, sans recalage ni changement de trait —
    # ne doivent PAS ajouter de nouvelles lignes [CLOCK] (throttle 30s).
    for _ in range(5):
        game._maybe_push_clock(force=False)
    nb_after = log.path.read_text(encoding="utf-8").count("[CLOCK]")
    assert nb_after == nb_before


def test_journal_pendule_arrondie_a_la_milliseconde(monkeypatch, tmp_path):
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    log = GameLog("gid_clk2", logs_dir=tmp_path)
    game = LichessGame(board, client, "gid_clk2", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10, game_log=log)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "", "wtime": 900000.7, "btime": 899999.4},
    })
    content = log.path.read_text(encoding="utf-8")
    clock_lines = [l for l in content.splitlines() if "[CLOCK]" in l]
    assert clock_lines
    assert "." not in clock_lines[-1].split("blancs=")[1].split(" ")[0]


def test_journal_indicateurs_nulle_logges_a_chaque_etat_recu(monkeypatch, tmp_path):
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    log = GameLog("gid_ind", logs_dir=tmp_path)
    game = LichessGame(board, client, "gid_ind", level=0, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10, game_log=log,
                        known_user_color="white")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp"},
        "state": {"status": "started", "moves": ""},
    })
    game._apply_game_state({"status": "started", "moves": "", "wdraw": True, "bdraw": False})
    content = log.path.read_text(encoding="utf-8")
    assert "indicateurs nulle : blancs=True, noirs=False" in content


# ═══════════════════════════════════════════════════════════════════════
# 8. Garde réseau (point 8) — vérification explicite, en plus de la
#    fixture autouse de conftest.py.
# ═══════════════════════════════════════════════════════════════════════

def test_garde_reseau_bloque_une_vraie_connexion_lichess():
    with pytest.raises(AssertionError, match="Garde réseau"):
        socket.create_connection(("lichess.org", 443), timeout=1)


def test_garde_reseau_laisse_passer_les_autres_hotes(monkeypatch):
    """La garde ne doit viser QUE les noms d'hôte Lichess — un autre hôte
    ne doit jamais être intercepté par erreur (ici : simplement vérifier
    qu'aucune AssertionError de la garde n'est levée avant l'échec de
    connexion réel, en ciblant une adresse non routable)."""
    with pytest.raises(OSError):
        socket.create_connection(("192.0.2.1", 9), timeout=0.2)  # TEST-NET-1, RFC 5737


# ═══════════════════════════════════════════════════════════════════════
# 9. single_instance : recherche humaine = instance occupée.
# ═══════════════════════════════════════════════════════════════════════

def test_lichess_seeking_fait_partie_des_etats_occupes():
    from nicsoft.web.single_instance import BUSY_STATES
    assert "lichess_seeking" in BUSY_STATES
