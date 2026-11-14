"""
nicsoft/tests/test_issue329_lichess_http_errors.py — AlChess

Issue #329 : Alain avait obtenu l'appariement d'un adversaire humain en
10+0 à 16:10 le 14/11/2026, puis une recherche en 15+10 (blancs) a échoué
dès l'ouverture, deux fois de suite — l'écran affichait « Connexion à
Lichess impossible — vérifiez le réseau » alors que le réseau et le jeton
fonctionnaient, et le journal ne portait que « TransportHTTPError », sans
le code HTTP ni le corps de la réponse Lichess : la cause réelle restait
invisible.

  (1) transport.py : toute erreur HTTP est journalisée (journal général) —
      méthode/chemin, code, Retry-After, corps tronqué à ~500 caractères,
      jamais le jeton.
  (2) seek.py/game_client.py : le détail (code, Retry-After, corps) est
      transmis jusqu'à l'évènement "error" et au journal de partie dédié.
  (3) game_manager_modes/lichess.py::_classify_seek_error_event : un
      message distinct par famille de code (400/401/403/404/429/5xx),
      jamais « vérifiez le réseau » pour une vraie réponse de Lichess.
  (4) Paramètres exacts envoyés à POST /api/board/seek pour chaque
      cadence proposée et chaque couleur — aucune régression entre #327
      et #328 (vérifié par ailleurs par lecture de l'historique git ; ce
      test fige le comportement actuel pour la suite).

Règle absolue de cette issue : AUCUNE connexion réseau réelle, AUCUNE
recherche/partie réelle sur lichess.org — urllib.request.urlopen est
systématiquement remplacé (monkeypatch) ou un FakeTransport/double est
injecté, jamais UrllibTransport contre un vrai socket. Voir aussi
nicsoft/tests/conftest.py::_guard_no_real_lichess_network (garde explicite).
"""
import io
import json
import logging
import socket
import urllib.error

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.lichess import CLOCK_PRESETS, _classify_seek_error_event
from nicsoft.core.game_manager_modes.state import _TOAST_MESSAGES, set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.game_log import GameLog
from nicsoft.modes.lichess.seek import SeekSession
from nicsoft.modes.lichess.transport import (
    TransportHTTPError,
    TransportNetworkError,
    TransportTimeoutError,
    UrllibTransport,
)
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport
from nicsoft.tests.test_issue311_lichess_sequencing import INITIAL_FEN_W, _ScriptedBoard
from nicsoft.tests.test_issue327_lichess_human import _FakeHandleForClient, _HumanGameClient


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


def _http_error(url, code, body: bytes, headers=None):
    return urllib.error.HTTPError(url, code, "x", headers or {}, io.BytesIO(body))


# ═══════════════════════════════════════════════════════════════════════
# 1. transport.py — journal général : code, Retry-After, corps tronqué,
#    jamais le jeton (point 1).
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("code", [400, 401, 403, 404, 500, 503])
def test_transport_http_error_capture_code_et_journalise(monkeypatch, caplog, code):
    body = json.dumps({"error": f"refus {code}"}).encode("utf-8")

    def raise_err(req, timeout=None):
        raise _http_error("https://lichess.org/api/board/seek", code, body)

    monkeypatch.setattr("urllib.request.urlopen", raise_err)
    transport = UrllibTransport()
    with caplog.at_level(logging.WARNING, logger="niclink.lichess"):
        with pytest.raises(TransportHTTPError) as exc_info:
            transport.request(
                "POST", "https://lichess.org/api/board/seek", "lip_secretTOKEN123456",
                fields={"time": 15.0, "increment": 10, "rated": "false", "color": "white"},
            )
    assert exc_info.value.status_code == code
    assert f"refus {code}" in exc_info.value.body

    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert str(code) in log_text
    assert "/api/board/seek" in log_text
    assert "lip_secretTOKEN123456" not in log_text


def test_transport_retry_after_capture_pour_429(monkeypatch):
    body = json.dumps({"error": "too many requests"}).encode("utf-8")

    def raise_err(req, timeout=None):
        raise _http_error("https://lichess.org/api/board/seek", 429, body, headers={"Retry-After": "42"})

    monkeypatch.setattr("urllib.request.urlopen", raise_err)
    transport = UrllibTransport()
    with pytest.raises(TransportHTTPError) as exc_info:
        transport.request("POST", "https://lichess.org/api/board/seek", "lip_x", fields={"time": 15.0})
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after_s == 42


def test_transport_retry_after_absent_est_none(monkeypatch):
    def raise_err(req, timeout=None):
        raise _http_error("https://lichess.org/api/x", 429, b"{}")

    monkeypatch.setattr("urllib.request.urlopen", raise_err)
    transport = UrllibTransport()
    with pytest.raises(TransportHTTPError) as exc_info:
        transport.request("GET", "https://lichess.org/api/x", "lip_x")
    assert exc_info.value.retry_after_s is None


def test_transport_corps_tronque_a_500_caracteres_dans_le_journal(monkeypatch, caplog):
    long_body = json.dumps({"error": "x" * 2000}).encode("utf-8")

    def raise_err(req, timeout=None):
        raise _http_error("https://lichess.org/api/board/seek", 400, long_body)

    monkeypatch.setattr("urllib.request.urlopen", raise_err)
    transport = UrllibTransport()
    with caplog.at_level(logging.WARNING, logger="niclink.lichess"):
        with pytest.raises(TransportHTTPError):
            transport.request("POST", "https://lichess.org/api/board/seek", "lip_x", fields={"time": 15.0})
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "x" * 2000 not in log_text
    assert "x" * 480 in log_text  # bien au-delà du début, toujours présent une fois tronqué


def test_transport_connexion_refusee_pas_de_ligne_erreur_http(monkeypatch, caplog):
    def raise_err(req, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError("refusée"))

    monkeypatch.setattr("urllib.request.urlopen", raise_err)
    transport = UrllibTransport()
    with caplog.at_level(logging.WARNING, logger="niclink.lichess"):
        with pytest.raises(TransportNetworkError):
            transport.request("POST", "https://lichess.org/api/board/seek", "lip_x", fields={"time": 15.0})
    # Pas de réponse HTTP de Lichess ici : aucune ligne "erreur HTTP" journalisée
    assert not any("erreur HTTP" in r.getMessage() for r in caplog.records)


def test_transport_delai_depasse_devient_timeout_error(monkeypatch):
    def raise_timeout(req, timeout=None):
        raise socket.timeout("délai dépassé")

    monkeypatch.setattr("urllib.request.urlopen", raise_timeout)
    transport = UrllibTransport()
    with pytest.raises(TransportTimeoutError):
        transport.request("POST", "https://lichess.org/api/board/seek", "lip_x", fields={"time": 15.0})


# ═══════════════════════════════════════════════════════════════════════
# 2. seek.py / game_client.py — le détail HTTP atteint l'évènement "error"
#    ET le journal de partie dédié, jamais le jeton (points 1/2).
# ═══════════════════════════════════════════════════════════════════════

def test_seek_session_evenement_error_porte_code_et_delai_429(tmp_path):
    exc = TransportHTTPError(429, body=json.dumps({"error": "too many requests"}), retry_after_s=30)
    transport = FakeTransport(open_stream_specs=[[""] * 3, exc])
    client = GameClient("lip_secretTOKEN123456", transport=transport)
    log = GameLog("recherche", logs_dir=tmp_path)
    session = SeekSession(client, game_log=log)
    session.start(15.0, 10, "white")

    ev = None
    for _ in range(50):
        candidate = session.next_event(timeout=0.05)
        if candidate and candidate["type"] == "error":
            ev = candidate
            break
    log.close()

    assert ev is not None, "aucun évènement 'error' reçu"
    assert ev["status_code"] == 429
    assert ev["retry_after_s"] == 30
    assert ev["detail"] == "too many requests"

    content = log.path.read_text(encoding="utf-8")
    assert "429" in content
    assert "lip_secretTOKEN123456" not in content


def test_classification_429_utilise_le_delai_recu():
    ev = {"status_code": 429, "retry_after_s": 30, "detail": ""}
    key, vars_ = _classify_seek_error_event(ev)
    assert key == "toast.lichess_rate_limited_detail"
    assert vars_ == {"seconds": 30}


def test_classification_429_sans_delai_recu_a_un_repli():
    ev = {"status_code": 429, "retry_after_s": None, "detail": ""}
    _, vars_ = _classify_seek_error_event(ev)
    assert vars_["seconds"] == 60


@pytest.mark.parametrize("status_code,expected_key", [
    (401, "toast.lichess_jeton_refuse"),
    (403, "toast.lichess_jeton_refuse"),
    (404, "toast.lichess_404"),
    (500, "toast.lichess_indisponible"),
    (503, "toast.lichess_indisponible"),
])
def test_classification_codes_connus(status_code, expected_key):
    ev = {"status_code": status_code, "retry_after_s": None, "detail": ""}
    key, _ = _classify_seek_error_event(ev)
    assert key == expected_key


def test_classification_400_porte_le_texte_lichess():
    ev = {"status_code": 400, "detail": "Game already in progress"}
    key, vars_ = _classify_seek_error_event(ev)
    assert key == "toast.lichess_refus_requete"
    assert "Game already in progress" in vars_["detail"]


def test_classification_sans_code_http_est_reseau():
    """Seule une vraie panne réseau (pas de réponse HTTP de Lichess) garde
    le message « vérifiez le réseau » (issue #329, point 2)."""
    ev = {"status_code": None, "retry_after_s": None, "detail": "", "reason": "TransportNetworkError"}
    key, vars_ = _classify_seek_error_event(ev)
    assert key == "toast.lichess_network_error"
    assert vars_ == {}


def test_tous_les_messages_sont_distincts_et_reseau_absent_sauf_pour_le_reseau():
    # 401 et 403 partagent volontairement le même message unifié ("jeton
    # refusé ou droit manquant", demandé tel quel par l'issue #329, point
    # 2) — tous les autres codes restent distincts entre eux.
    codes = [None, 400, 401, 404, 429, 500]
    keys = set()
    for code in codes:
        ev = {"status_code": code, "retry_after_s": 30, "detail": "x"}
        key, _ = _classify_seek_error_event(ev)
        keys.add(key)
        if code is not None:
            assert "reseau" not in key.lower() and "network" not in key.lower()
    assert len(keys) == len(codes), f"au moins deux codes partagent le même message : {keys}"
    for key in keys:
        assert key in _TOAST_MESSAGES, f"{key} absent de _TOAST_MESSAGES (texte de repli)"
    key_401, _ = _classify_seek_error_event({"status_code": 401, "retry_after_s": None, "detail": ""})
    key_403, _ = _classify_seek_error_event({"status_code": 403, "retry_after_s": None, "detail": ""})
    assert key_401 == key_403 == "toast.lichess_jeton_refuse"


# ═══════════════════════════════════════════════════════════════════════
# 3. _run_lichess_human — message affiché + persistance, par code HTTP
#    (point 2 ; jamais de relance automatique : _run_lichess_human
#    retourne, à l'utilisateur de cliquer de nouveau).
# ═══════════════════════════════════════════════════════════════════════

class _HTTPErrorSeekClient(_HumanGameClient):
    """La recherche échoue dès l'ouverture du flux d'évènements — exactement
    le scénario réel du 14/11/2026 (échec « dès l'ouverture »)."""

    def __init__(self, exc):
        super().__init__()
        self._exc = exc

    def open_event_stream(self):
        raise self._exc

    def open_seek_stream(self, *a, **kw):
        return _FakeHandleForClient([""])


def _run_with_seek_exception(monkeypatch, exc):
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _HTTPErrorSeekClient(exc)
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)
    return _error


@pytest.mark.parametrize("exc,expected_key,expected_vars", [
    (TransportHTTPError(400, body=json.dumps({"error": "Invalid clock"})),
     "toast.lichess_refus_requete", {"detail": " : Invalid clock"}),
    (TransportHTTPError(401, body=""), "toast.lichess_jeton_refuse", {}),
    (TransportHTTPError(403, body=""), "toast.lichess_jeton_refuse", {}),
    (TransportHTTPError(404, body=""), "toast.lichess_404", {}),
    (TransportHTTPError(429, body="", retry_after_s=17), "toast.lichess_rate_limited_detail", {"seconds": 17}),
    (TransportHTTPError(500, body=""), "toast.lichess_indisponible", {}),
    (TransportNetworkError("connexion refusée"), "toast.lichess_network_error", {}),
    (TransportTimeoutError("délai dépassé"), "toast.lichess_network_error", {}),
])
def test_run_lichess_human_message_distinct_et_persistant_par_code(monkeypatch, exc, expected_key, expected_vars):
    _error = _run_with_seek_exception(monkeypatch, exc)
    assert _error["occurred"] is True
    assert _error["toast_key"] == expected_key
    assert _error["toast_vars"] == expected_vars
    # Persistant (pas éphémère) — issue #329, point 2.
    assert _error["toast_persistent"] is True
    assert _error["return_to"] == "config_lichess"


def test_run_lichess_human_ne_relance_jamais_automatiquement(monkeypatch):
    """Après l'échec, _run_lichess_human retourne simplement — aucune
    nouvelle tentative n'est faite depuis ce fil (jamais de boucle de
    relance automatique, issue #329, point 2)."""
    attempts = {"n": 0}
    exc = TransportHTTPError(500, body="")

    class _CountingClient(_HTTPErrorSeekClient):
        def open_event_stream(self):
            attempts["n"] += 1
            return super().open_event_stream()

    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _CountingClient(exc)
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is True
    assert attempts["n"] == 1, f"la recherche a été retentée automatiquement ({attempts['n']} tentatives)"


# ═══════════════════════════════════════════════════════════════════════
# 4. Paramètres exacts de POST /api/board/seek — par cadence et par
#    couleur (point 3) : aucun paramètre absent ou en trop.
# ═══════════════════════════════════════════════════════════════════════

class _RecordingOpenStreamTransport:
    """Faux serveur Lichess qui enregistre la requête plutôt que de s'y
    connecter — jamais de vrai socket (voir en-tête de module)."""

    def __init__(self):
        self.calls = []

    def open_stream(self, method, url, token, fields=None):
        self.calls.append((method, url, fields))
        return _FakeHandleForClient([""])


@pytest.mark.parametrize("cadence_key", list(CLOCK_PRESETS.keys()))
@pytest.mark.parametrize("color", ["white", "black"])
def test_parametres_exacts_par_cadence_et_couleur(cadence_key, color):
    clock_limit_s, clock_increment_s = CLOCK_PRESETS[cadence_key]
    transport = _RecordingOpenStreamTransport()
    client = GameClient("lip_x", transport=transport)

    client.open_event_stream()
    # Même calcul que le lanceur réel (game_manager_modes/lichess.py,
    # _run_lichess_human : "seek_session.start(clock_limit_s / 60.0, ...)").
    client.open_seek_stream(clock_limit_s / 60.0, clock_increment_s, color)

    assert len(transport.calls) == 2
    event_method, event_url, event_fields = transport.calls[0]
    assert event_method == "GET"
    assert event_url == "https://lichess.org/api/stream/event"
    assert event_fields is None

    seek_method, seek_url, seek_fields = transport.calls[1]
    assert seek_method == "POST"
    assert seek_url == "https://lichess.org/api/board/seek"
    assert seek_fields == {
        "time": clock_limit_s / 60.0,
        "increment": clock_increment_s,
        "rated": "false",
        "color": color,
    }, f"paramètres inattendus pour {cadence_key}/{color} : {seek_fields}"
