"""
nicsoft/tests/test_issue307_lichess_l1.py — AlChess

Issue #307 (étape L1 — client de partie Lichess : flux, coups, abandon,
nulle) : couche de communication seule, aucun mode de jeu, aucun moteur.

  (1) transport.py : UrllibTransport vérifie https (ensure_https), envoie
      le jeton uniquement dans l'en-tête d'autorisation, délais distincts
      requête/flux ; erreurs typées (TransportHTTPError/NetworkError/
      TimeoutError) jamais porteuses du jeton.
  (2) game_client.py : GameClient.create_ai_game/play_move/resign/abort/
      answer_draw/stream_game, verrou sur les requêtes ordinaires (jamais
      sur la lecture du flux), reprise de flux avec attentes croissantes,
      fonctions utilitaires pures.
  (3) client.py : test_ai_game() — scénario complet du bouton "Tester une
      partie" (créer, lire, annuler/abandonner), jamais le jeton exposé.
  (4) server.py : lichess_test_game — jeton enregistré uniquement, un seul
      test à la fois, jamais le jeton journalisé.
  (5) i18n : nouvelles clés présentes dans fr/en/de ; app.js : textContent
      exclusif pour le texte du résultat de ce nouveau test.

Tests entièrement sans réseau (faux transport scénarisé) et sans matériel.
"""
import json
import logging
import threading
import time

import pytest

import nicsoft.web.server as server
from nicsoft.core import config_manager as cm
from nicsoft.modes.lichess import client as lichess_client
from nicsoft.modes.lichess import game_client as gc
from nicsoft.modes.lichess.errors import (
    LichessApiError,
    LichessAuthError,
    LichessNetworkError,
    LichessRateLimitError,
)
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.transport import (
    TransportHTTPError,
    TransportNetworkError,
    TransportTimeoutError,
    UrllibTransport,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg_file)
    return cfg_file


class FakeTransport:
    """Faux transport scénarisé — ne se connecte jamais à Lichess.

    `requests`: liste de callables (method, url, token, fields) -> bytes,
    consommées dans l'ordre, une par appel à `request()`.
    `stream_batches`: liste de listes de lignes (str) ; chaque appel à
    `stream_lines()` consomme le batch suivant. Un batch peut se terminer
    par une exception au lieu d'une simple fin de liste pour simuler une
    coupure en cours de flux.
    """

    def __init__(self, requests=None, stream_batches=None):
        self._requests = list(requests or [])
        self._stream_batches = list(stream_batches or [])
        self.seen_tokens = []
        self.request_calls = []
        self.stream_calls = []
        self.concurrent_requests = 0
        self.max_concurrent_requests = 0

    def request(self, method, url, token, fields=None):
        self.seen_tokens.append(token)
        self.request_calls.append((method, url, fields))
        self.concurrent_requests += 1
        self.max_concurrent_requests = max(self.max_concurrent_requests, self.concurrent_requests)
        try:
            handler = self._requests.pop(0)
            result = handler(method, url, token, fields)
            if isinstance(result, Exception):
                raise result
            return result
        finally:
            self.concurrent_requests -= 1

    def stream_lines(self, url, token):
        self.seen_tokens.append(token)
        self.stream_calls.append(url)
        batch = self._stream_batches.pop(0)
        for item in batch:
            if isinstance(item, Exception):
                raise item
            yield item


def _ok(body: dict):
    return lambda method, url, token, fields: json.dumps(body).encode("utf-8")


def _line(d: dict) -> str:
    return json.dumps(d)


# ── transport.py : UrllibTransport ──────────────────────────────────────────

def test_transport_refuse_adresse_non_https_sans_appeler_urlopen(monkeypatch):
    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: called.append(1))
    transport = UrllibTransport()
    with pytest.raises(ValueError, match="https"):
        transport.request("POST", "http://lichess.org/api/challenge/ai", "lip_x")
    assert not called


def test_transport_stream_refuse_adresse_non_https(monkeypatch):
    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: called.append(1))
    transport = UrllibTransport()
    with pytest.raises(ValueError, match="https"):
        list(transport.stream_lines("http://lichess.org/api/board/game/stream/x", "lip_x"))
    assert not called


def test_transport_jeton_uniquement_dans_en_tete_authorization(monkeypatch):
    captured = {}

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        captured["timeout"] = timeout
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = UrllibTransport()
    transport.request("POST", "https://lichess.org/api/challenge/ai", "lip_secret123456789012", fields={"level": 1})

    req = captured["req"]
    assert req.headers.get("Authorization") == "Bearer lip_secret123456789012"
    assert "lip_secret123456789012" not in req.full_url
    data_sent = req.data.decode("utf-8") if req.data else ""
    assert "lip_secret123456789012" not in data_sent
    assert captured["timeout"] == 10


def test_transport_http_error_mappe_sans_le_jeton(monkeypatch):
    import urllib.error

    def raise_http_error(req, timeout=None):
        raise urllib.error.HTTPError("https://lichess.org/api/x", 400, "Bad Request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", raise_http_error)
    transport = UrllibTransport()
    with pytest.raises(TransportHTTPError) as exc_info:
        transport.request("POST", "https://lichess.org/api/x", "lip_secret")
    assert exc_info.value.status_code == 400
    assert "lip_secret" not in str(exc_info.value)


def test_transport_url_error_devient_network_error(monkeypatch):
    import urllib.error

    def raise_url_error(req, timeout=None):
        raise urllib.error.URLError("pas de réseau")

    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    transport = UrllibTransport()
    with pytest.raises(TransportNetworkError):
        transport.request("GET", "https://lichess.org/api/x", "lip_secret")


def test_transport_timeout_devient_timeout_error(monkeypatch):
    import socket

    def raise_timeout(req, timeout=None):
        raise socket.timeout("délai dépassé")

    monkeypatch.setattr("urllib.request.urlopen", raise_timeout)
    transport = UrllibTransport()
    with pytest.raises(TransportTimeoutError):
        transport.request("GET", "https://lichess.org/api/x", "lip_secret")


def test_transport_stream_ignore_les_lignes_vides_de_maintien(monkeypatch):
    class _FakeStreamResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            return iter([b"\n", b'{"type":"gameFull"}\n', b"\n"])

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeStreamResp())
    transport = UrllibTransport()
    lines = list(transport.stream_lines("https://lichess.org/api/board/game/stream/x", "lip_x"))
    assert lines == ["", '{"type":"gameFull"}', ""]


# ── game_client.py : GameClient — actions ───────────────────────────────────

def test_create_ai_game_envoie_niveau_duree_increment_couleur():
    transport = FakeTransport(requests=[_ok({"id": "abcd1234"})])
    client = GameClient("lip_x", transport=transport)
    result = client.create_ai_game(level=1, clock_limit_s=900, clock_increment_s=0, color="")
    assert result == {"id": "abcd1234"}
    method, url, fields = transport.request_calls[0]
    assert method == "POST"
    assert url.endswith("/api/challenge/ai")
    assert fields == {"level": 1, "clock.limit": 900, "clock.increment": 0}


def test_create_ai_game_couleur_facultative_transmise():
    transport = FakeTransport(requests=[_ok({"id": "abcd1234"})])
    client = GameClient("lip_x", transport=transport)
    client.create_ai_game(level=3, clock_limit_s=300, clock_increment_s=5, color="black")
    _, _, fields = transport.request_calls[0]
    assert fields["color"] == "black"


def test_play_move_uci_dans_url_avec_offre_de_nulle():
    transport = FakeTransport(requests=[_ok({"ok": True})])
    client = GameClient("lip_x", transport=transport)
    client.play_move("gid1", "e2e4", offer_draw=True)
    _, url, _ = transport.request_calls[0]
    assert "/board/game/gid1/move/e2e4" in url
    assert "offeringDraw=true" in url


def test_resign_abort_draw_yes_no_urls():
    transport = FakeTransport(requests=[_ok({}), _ok({}), _ok({}), _ok({})])
    client = GameClient("lip_x", transport=transport)
    client.resign("gid1")
    client.abort("gid1")
    client.answer_draw("gid1", True)
    client.answer_draw("gid1", False)
    urls = [u for _, u, _ in transport.request_calls]
    assert urls[0].endswith("/board/game/gid1/resign")
    assert urls[1].endswith("/board/game/gid1/abort")
    assert urls[2].endswith("/board/game/gid1/draw/yes")
    assert urls[3].endswith("/board/game/gid1/draw/no")


def test_requetes_ordinaires_jamais_le_jeton_dans_lurl_ou_les_champs():
    transport = FakeTransport(requests=[_ok({"id": "gid1"})])
    client = GameClient("lip_secretsecretsecret", transport=transport)
    client.create_ai_game(level=1, clock_limit_s=900, clock_increment_s=0)
    _, url, fields = transport.request_calls[0]
    assert "lip_secretsecretsecret" not in url
    assert "lip_secretsecretsecret" not in json.dumps(fields)


# ── game_client.py : erreurs typées ─────────────────────────────────────────

@pytest.mark.parametrize("code", [401, 403])
def test_erreur_401_403_devient_lichess_auth_error(code):
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(code, "{}"),
    ])
    client = GameClient("lip_secret", transport=transport)
    with pytest.raises(LichessAuthError) as exc_info:
        client.create_ai_game(1, 900, 0)
    assert exc_info.value.status_code == code
    assert "lip_secret" not in str(exc_info.value)


def test_erreur_429_devient_lichess_rate_limit_error():
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(429, "{}"),
    ])
    client = GameClient("lip_secret", transport=transport)
    with pytest.raises(LichessRateLimitError) as exc_info:
        client.create_ai_game(1, 900, 0)
    assert exc_info.value.retry_after_s == 60


def test_erreur_400_avec_message_devient_lichess_api_error():
    body = json.dumps({"error": "This move is illegal"})
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, body),
    ])
    client = GameClient("lip_secret", transport=transport)
    with pytest.raises(LichessApiError) as exc_info:
        client.play_move("gid1", "e2e4")
    assert exc_info.value.status_code == 400
    assert exc_info.value.api_message == "This move is illegal"


def test_erreur_reseau_devient_lichess_network_error():
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportNetworkError("coupure"),
    ])
    client = GameClient("lip_secret", transport=transport)
    with pytest.raises(LichessNetworkError):
        client.resign("gid1")


def test_erreur_delai_depasse_devient_lichess_network_error():
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportTimeoutError("délai"),
    ])
    client = GameClient("lip_secret", transport=transport)
    with pytest.raises(LichessNetworkError):
        client.resign("gid1")


def test_jeton_jamais_dans_les_exceptions(isolated_config):
    secret = "lip_super_secret_token_xyz"
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, json.dumps({"error": "boom"})),
    ])
    client = GameClient(secret, transport=transport)
    try:
        client.play_move("gid1", "e2e4")
        assert False, "une exception était attendue"
    except LichessApiError as exc:
        assert secret not in str(exc)
        assert secret not in repr(exc)


# ── game_client.py : verrou sur les requêtes ordinaires ─────────────────────

def test_requetes_ordinaires_serialisees_par_le_verrou():
    transport = FakeTransport(requests=[_ok({}) for _ in range(6)])
    # Simule une requête lente pour vérifier qu'aucune autre ne chevauche.
    original_request = transport.request

    def slow_request(method, url, token, fields=None):
        time.sleep(0.05)
        return original_request(method, url, token, fields)

    transport.request = slow_request
    client = GameClient("lip_x", transport=transport)
    threads = [threading.Thread(target=client.resign, args=("gid1",)) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert transport.max_concurrent_requests == 1


def test_flux_ne_bloque_pas_les_requetes_ordinaires():
    """La lecture du flux (générateur séparé) n'emprunte jamais le verrou
    des requêtes ordinaires : jouer un coup pendant qu'on lit le flux doit
    rester possible."""
    transport = FakeTransport(
        requests=[_ok({})],
        stream_batches=[[_line({"type": "gameFull", "state": {"status": "started", "moves": ""}})]],
    )
    client = GameClient("lip_x", transport=transport)
    stream = client.stream_game("gid1")
    next(stream)  # ouvre le flux, ne détient aucun verrou
    client.play_move("gid1", "e2e4")  # ne doit jamais se bloquer
    assert transport.request_calls


# ── game_client.py : lecture du flux — déroulement normal ───────────────────

def test_stream_game_full_puis_gamestate_mat():
    transport = FakeTransport(stream_batches=[[
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
        _line({"type": "gameState", "moves": "e2e4", "status": "started"}),
        _line({"type": "gameState", "moves": "e2e4 e7e5", "status": "mate", "winner": "white"}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert [e["type"] for e in events] == ["gameFull", "gameState", "gameState"]
    assert events[-1]["status"] == "mate"


def test_stream_game_fin_par_abandon():
    transport = FakeTransport(stream_batches=[[
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
        _line({"type": "gameState", "moves": "e2e4", "status": "resign", "winner": "black"}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert events[-1]["status"] == "resign"


def test_stream_game_fin_par_temps_depasse():
    transport = FakeTransport(stream_batches=[[
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
        _line({"type": "gameState", "moves": "e2e4", "status": "outoftime", "winner": "white"}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert events[-1]["status"] == "outoftime"


def test_stream_game_ignore_lignes_vides_et_types_inconnus():
    transport = FakeTransport(stream_batches=[[
        "",
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
        "   ",
        _line({"type": "pingPong", "x": 1}),
        _line({"type": "gameState", "moves": "e2e4", "status": "started"}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert [e["type"] for e in events] == ["gameFull", "gameState"]


def test_stream_game_proposition_nulle_blancs_et_noirs():
    transport = FakeTransport(stream_batches=[[
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
        _line({"type": "gameState", "moves": "e2e4", "status": "started", "wdraw": True}),
        _line({"type": "gameState", "moves": "e2e4 e7e5", "status": "started", "bdraw": True}),
        _line({"type": "gameState", "moves": "e2e4 e7e5", "status": "draw"}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert events[1]["wdraw"] is True
    assert events[2]["bdraw"] is True
    assert events[-1]["status"] == "draw"


def test_stream_game_chatline_et_opponentgone_pas_ignores():
    transport = FakeTransport(stream_batches=[[
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
        _line({"type": "chatLine", "username": "adversaire", "text": "bonne partie"}),
        _line({"type": "opponentGone", "gone": True}),
        _line({"type": "gameState", "moves": "", "status": "aborted"}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert [e["type"] for e in events] == ["gameFull", "chatLine", "opponentGone", "gameState"]


# ── game_client.py : coupure réseau + reprise ───────────────────────────────

def test_stream_game_coupure_puis_reprise_avec_nouveau_gamefull():
    transport = FakeTransport(stream_batches=[
        [
            _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
            TransportNetworkError("coupure"),
        ],
        [
            _line({"type": "gameFull", "state": {"status": "started", "moves": "e2e4"}}),
            _line({"type": "gameState", "moves": "e2e4", "status": "resign", "winner": "white"}),
        ],
    ])
    sleeps = []
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1", sleep=sleeps.append))
    types = [e["type"] for e in events]
    assert types == ["gameFull", "reconnecting", "reconnected", "gameFull", "gameState"]
    # Un seul nouveau gameFull reçu à la reprise, qui remplace l'état local.
    assert events[3]["state"]["moves"] == "e2e4"
    assert sleeps == [1]  # une seule attente, de 1s (première tentative)


def test_stream_game_sequence_attentes_croissantes_sans_attendre_reellement():
    """Plusieurs coupures d'affilée : la séquence d'attentes doit suivre
    1, 2, 4, 8, puis 30s au plus — horloge simulée, aucune vraie attente."""
    transport = FakeTransport(stream_batches=[
        [_line({"type": "gameFull", "state": {"status": "started", "moves": ""}}), TransportNetworkError("x")],
        [TransportNetworkError("x")],
        [TransportNetworkError("x")],
        [TransportNetworkError("x")],
        [TransportNetworkError("x")],
        [TransportNetworkError("x")],
        [_line({"type": "gameState", "moves": "", "status": "aborted"})],
    ])
    sleeps = []
    client = GameClient("lip_x", transport=transport)
    start = time.monotonic()
    events = list(client.stream_game("gid1", sleep=sleeps.append))
    elapsed = time.monotonic() - start
    assert sleeps == [1, 2, 4, 8, 30, 30]
    assert elapsed < 1.0  # l'horloge est simulée : aucune vraie attente
    assert events[-1]["status"] == "aborted"


def test_stream_game_sarrete_sur_statut_termine_sans_relire():
    transport = FakeTransport(stream_batches=[[
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
        _line({"type": "gameState", "moves": "e2e4", "status": "aborted"}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert len(events) == 2
    assert not transport._stream_batches  # un seul appel à stream_lines


def test_stream_game_flux_ferme_normalement_sans_statut_termine():
    """Le flux peut se terminer sans jamais annoncer de statut terminé
    (fin de connexion normale côté Lichess) : le générateur s'arrête alors
    sans boucler ni tenter de reprise."""
    transport = FakeTransport(stream_batches=[[
        _line({"type": "gameFull", "state": {"status": "started", "moves": ""}}),
    ]])
    client = GameClient("lip_x", transport=transport)
    events = list(client.stream_game("gid1"))
    assert len(events) == 1


# ── game_client.py : fonctions utilitaires pures ────────────────────────────

def test_moves_from_state():
    assert gc.moves_from_state({"moves": "e2e4 e7e5 g1f3"}) == ["e2e4", "e7e5", "g1f3"]
    assert gc.moves_from_state({"moves": ""}) == []
    assert gc.moves_from_state({}) == []


def test_side_to_move():
    assert gc.side_to_move({"moves": ""}) == "white"
    assert gc.side_to_move({"moves": "e2e4"}) == "black"
    assert gc.side_to_move({"moves": "e2e4 e7e5"}) == "white"


def test_is_game_over():
    assert gc.is_game_over("mate") is True
    assert gc.is_game_over("resign") is True
    assert gc.is_game_over("outoftime") is True
    assert gc.is_game_over("started") is False
    assert gc.is_game_over("created") is False


def test_result_text_victoire_defaite_nulle_abandon_temps_annulation():
    assert "Victoire" in gc.result_text("mate", winner="white", user_color="white")
    assert "Défaite" in gc.result_text("mate", winner="black", user_color="white")
    assert "Nulle" in gc.result_text("draw")
    assert "Abandon" in gc.result_text("resign")
    assert "Victoire au temps" in gc.result_text("outoftime", winner="white", user_color="white")
    assert "annulée" in gc.result_text("aborted")


# ── client.py : test_ai_game() — scénario complet du bouton ────────────────

def _gamefull_vs_ai(color_user):
    """gamefull où l'utilisateur joue `color_user` contre l'IA."""
    ai_side = "black" if color_user == "white" else "white"
    full = {
        "type": "gameFull",
        "id": "gid-ia-1",
        "state": {"status": "started", "moves": ""},
        "white": {"aiLevel": 1, "name": "Stockfish AI level 1"} if ai_side == "white"
                 else {"id": "alain", "name": "alain"},
        "black": {"aiLevel": 1, "name": "Stockfish AI level 1"} if ai_side == "black"
                 else {"id": "alain", "name": "alain"},
    }
    return full


def test_test_ai_game_succes_couleur_blanche():
    transport = FakeTransport(
        requests=[_ok({"id": "gid-ia-1"}), _ok({"ok": True})],  # create + abort
        stream_batches=[[
            _line(_gamefull_vs_ai("white")),
            _line({"type": "gameState", "moves": "", "status": "aborted"}),
        ]],
    )
    result = lichess_client.test_ai_game("lip_x", transport=transport)
    assert result["status"] == "ok"
    assert result["color"] == "white"
    assert result["opponent"] == "Stockfish AI level 1"
    assert result["game_id"] == "gid-ia-1"
    # Niveau 1, 15 minutes, sans incrément, couleur aléatoire (vide).
    _, _, fields = transport.request_calls[0]
    assert fields == {"level": 1, "clock.limit": 900, "clock.increment": 0}


def test_test_ai_game_succes_couleur_noire():
    transport = FakeTransport(
        requests=[_ok({"id": "gid-ia-2"}), _ok({"ok": True})],
        stream_batches=[[
            _line(_gamefull_vs_ai("black")),
            _line({"type": "gameState", "moves": "", "status": "aborted"}),
        ]],
    )
    result = lichess_client.test_ai_game("lip_x", transport=transport)
    assert result["color"] == "black"


def test_test_ai_game_abandon_si_annulation_refusee():
    transport = FakeTransport(
        requests=[
            _ok({"id": "gid-ia-3"}),
            lambda m, u, t, f: TransportHTTPError(400, json.dumps({"error": "abort refused"})),
            _ok({"ok": True}),  # resign, utilisé après refus de l'abort
        ],
        stream_batches=[[
            _line(_gamefull_vs_ai("white")),
            _line({"type": "gameState", "moves": "", "status": "resign", "winner": "black"}),
        ]],
    )
    result = lichess_client.test_ai_game("lip_x", transport=transport)
    assert result["status"] == "ok"
    urls = [u for _, u, _ in transport.request_calls]
    assert any("/abort" in u for u in urls)
    assert any("/resign" in u for u in urls)


def test_test_ai_game_sans_jeton():
    assert lichess_client.test_ai_game("", transport=FakeTransport()) == {"status": "invalid"}


def test_test_ai_game_jeton_refuse_401():
    transport = FakeTransport(requests=[lambda m, u, t, f: TransportHTTPError(401, "{}")])
    assert lichess_client.test_ai_game("lip_x", transport=transport) == {"status": "invalid"}


def test_test_ai_game_droit_manquant_403():
    transport = FakeTransport(requests=[lambda m, u, t, f: TransportHTTPError(403, "{}")])
    assert lichess_client.test_ai_game("lip_x", transport=transport) == {"status": "missing_scope"}


def test_test_ai_game_limite_429():
    transport = FakeTransport(requests=[lambda m, u, t, f: TransportHTTPError(429, "{}")])
    assert lichess_client.test_ai_game("lip_x", transport=transport) == {"status": "rate_limited"}


def test_test_ai_game_reseau_indisponible():
    transport = FakeTransport(requests=[lambda m, u, t, f: TransportNetworkError("x")])
    assert lichess_client.test_ai_game("lip_x", transport=transport) == {"status": "network_error"}


def test_test_ai_game_jeton_jamais_expose(caplog):
    secret = "lip_le_vrai_secret_ici_123"
    transport = FakeTransport(requests=[lambda m, u, t, f: TransportHTTPError(400, '{"error":"boom"}')])
    with caplog.at_level(logging.WARNING):
        result = lichess_client.test_ai_game(secret, transport=transport)
    assert result == {"status": "network_error"}
    for record in caplog.records:
        assert secret not in record.getMessage()
    assert secret not in json.dumps(result)


# ── server.py : lichess_test_game ───────────────────────────────────────────

class _FakeRequest:
    def __init__(self, sid):
        self.sid = sid


class _FakeSocketIO:
    def __init__(self):
        self.emitted = []

    def emit(self, event, data, to=None):
        self.emitted.append((event, data, to))


def _wait_emitted(fake_sio, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fake_sio.emitted:
            return
        time.sleep(0.02)


def test_lichess_test_game_sans_jeton_enregistre(monkeypatch):
    monkeypatch.setattr(cm, "load_config", lambda: dict(cm.DEFAULT_CONFIG))
    monkeypatch.setattr(server, "request", _FakeRequest("sid-1"))
    fake_sio = _FakeSocketIO()
    monkeypatch.setattr(server, "socketio", fake_sio)
    server.on_lichess_test_game({})
    assert fake_sio.emitted == [("lichess_test_game_result", {"status": "invalid"}, "sid-1")]


def test_lichess_test_game_utilise_le_jeton_enregistre(monkeypatch):
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "lichess_token": "lip_enregistre0000000"})
    monkeypatch.setattr(server, "request", _FakeRequest("sid-1"))
    fake_sio = _FakeSocketIO()
    monkeypatch.setattr(server, "socketio", fake_sio)

    seen = []

    def fake_test_ai_game(token):
        seen.append(token)
        return {"status": "ok", "game_id": "g1", "color": "white", "opponent": "IA"}

    monkeypatch.setattr(lichess_client, "test_ai_game", fake_test_ai_game)
    server.on_lichess_test_game({})
    _wait_emitted(fake_sio)
    assert seen == ["lip_enregistre0000000"]
    assert fake_sio.emitted[0][1]["status"] == "ok"


def test_lichess_test_game_un_seul_test_a_la_fois(monkeypatch):
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "lichess_token": "lip_enregistre0000000"})
    monkeypatch.setattr(server, "request", _FakeRequest("sid-1"))
    fake_sio = _FakeSocketIO()
    monkeypatch.setattr(server, "socketio", fake_sio)

    release_event = threading.Event()
    calls = []

    def fake_test_ai_game(token):
        calls.append(token)
        release_event.wait(timeout=1.0)
        return {"status": "ok", "game_id": "g1", "color": "white", "opponent": "IA"}

    monkeypatch.setattr(lichess_client, "test_ai_game", fake_test_ai_game)
    server.on_lichess_test_game({})  # premier test démarre, reste bloqué
    time.sleep(0.05)
    server.on_lichess_test_game({})  # second test : doit être ignoré (verrou pris)
    release_event.set()
    _wait_emitted(fake_sio)
    time.sleep(0.05)
    assert len(calls) == 1


def test_lichess_test_game_exception_inattendue_ne_journalise_pas_le_jeton(monkeypatch, caplog):
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "lichess_token": "lip_secretsecret00000"})
    monkeypatch.setattr(server, "request", _FakeRequest("sid-1"))
    fake_sio = _FakeSocketIO()
    monkeypatch.setattr(server, "socketio", fake_sio)

    secret = "lip_secretsecret00000"

    def fake_test_ai_game(token):
        raise RuntimeError(f"boom with token {token}")

    monkeypatch.setattr(lichess_client, "test_ai_game", fake_test_ai_game)
    with caplog.at_level(logging.WARNING):
        server.on_lichess_test_game({})
        _wait_emitted(fake_sio)

    assert fake_sio.emitted == [("lichess_test_game_result", {"status": "network_error"}, "sid-1")]
    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in str(record.exc_info)


# ── i18n : nouvelles clés présentes dans les trois langues ──────────────────

NEW_I18N_KEYS = [
    "parametres.lichess.couleur.blancs",
    "parametres.lichess.couleur.noirs",
    "parametres.lichess.test_partie.bouton",
    "parametres.lichess.test_partie.aide",
    "parametres.lichess.test_partie.sans_jeton",
    "parametres.lichess.test_partie.resultat.ok",
    "parametres.lichess.test_partie.resultat.droit_manquant",
]


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_nouvelles_cles_i18n_presentes(locale):
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in NEW_I18N_KEYS:
        assert key in data, f"{key} absente de {locale}.json"
        assert data[key], f"{key} vide dans {locale}.json"


# ── app.js : jamais d'innerHTML pour le texte du nouveau test ──────────────

def test_appjs_resultat_test_partie_utilise_textcontent():
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "nicsoft" / "web" / "static" / "app.js"
    src = path.read_text(encoding="utf-8")
    assert "function lichessTesterPartie()" in src
    assert 'socket.on("lichess_test_game_result"' in src
    # Bloc du nouveau test : uniquement des affectations textContent.
    start = src.index('socket.on("lichess_test_game_result"')
    end = src.index("\n});", start)
    bloc = src[start:end]
    assert "result.innerHTML" not in bloc
    assert "result.textContent = t(" in bloc
