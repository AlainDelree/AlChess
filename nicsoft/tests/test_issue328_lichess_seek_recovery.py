"""
nicsoft/tests/test_issue328_lichess_seek_recovery.py — AlChess

Issue #328 : essai réel du 14/11/2026 (recherche d'adversaire humain,
10+0, blancs) — un adversaire a bien été apparié chez Lichess, mais
AlChess a interprété la fermeture du flux de recherche (board/seek) comme
un échec avant que l'évènement `gameStart` du flux d'évènements ne soit
lu, puis a fermé ce flux pendant que son fil de lecture y attendait
encore — levant une exception non interceptée (`AttributeError`) et
perdant la partie (terminée manuellement sur lichess.org par Alain).

Règle absolue de cette issue : AUCUNE connexion réelle à lichess.org,
AUCUNE recherche/partie réelle. Deux familles de doubles :
  - FakeTransport/FakeStreamHandle/_HumanGameClient/_FakeHandleForClient
    (réutilisés de test_issue309/test_issue327) — SeekSession et le
    lanceur _run_lichess_human testés sans aucun socket réel ;
  - un serveur HTTP local (127.0.0.1, jamais lichess.org — autorisé par la
    garde réseau de conftest.py, qui ne vise que les noms d'hôte Lichess)
    jouant le rôle d'un faux serveur Lichess pour reproduire la racine du
    bug : la fermeture RÉELLE d'une connexion TCP par un autre fil pendant
    une lecture bloquante sur un vrai socket (transport.py::StreamHandle).
"""
import http.client
import http.server
import logging
import threading
import time

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.state import _TOAST_MESSAGES, set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.game_log import GameLog
from nicsoft.modes.lichess.seek import SeekSession
from nicsoft.modes.lichess.transport import StreamHandle
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport
from nicsoft.tests.test_issue311_lichess_sequencing import INITIAL_FEN_W, _ScriptedBoard
from nicsoft.tests.test_issue327_lichess_human import _FakeHandleForClient, _HumanGameClient, _gamestart_line


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ═══════════════════════════════════════════════════════════════════════
# 1. transport.py — fermeture depuis un AUTRE fil pendant une lecture
#    bloquante sur un VRAI socket (faux serveur Lichess local, jamais
#    lichess.org) : plus aucune exception non interceptée (point 7).
# ═══════════════════════════════════════════════════════════════════════

class _SlowStreamHandler(http.server.BaseHTTPRequestHandler):
    """Faux serveur Lichess local — écrit une première ligne puis se tait
    plusieurs secondes avant la suivante, assez longtemps pour que le test
    ferme le flux côté client PENDANT que le fil de lecture est bloqué sur
    la ligne suivante (reproduction du blocage réel du 14/11/2026)."""

    first_line_sent = threading.Event()
    hold_s = 3.0

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(b"premiere-ligne\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        type(self).first_line_sent.set()
        time.sleep(type(self).hold_s)
        try:
            self.wfile.write(b"deuxieme-ligne\n")
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, *a, **kw):
        pass  # silence stderr — un faux 404/erreur de test n'a rien à y faire


@pytest.fixture
def fake_lichess_http_server():
    _SlowStreamHandler.first_line_sent = threading.Event()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowStreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_stream_handle_fermeture_pendant_lecture_bloquante_ne_leve_rien(fake_lichess_http_server):
    """Reproduction directe du bug : close() appelé depuis le fil de test
    PENDANT que le fil de lecture est bloqué dans StreamHandle.lines() sur
    un vrai socket — plus aucune exception ne doit atteindre le hook
    d'exception par défaut des fils (ce qui, avant correction, produisait
    la trace "AttributeError: 'NoneType' object has no attribute 'peek'"
    visible seulement dans le terminal, jamais journalisée)."""
    port = fake_lichess_http_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", "/stream")
    resp = conn.getresponse()
    handle = StreamHandle(resp)

    collected = []
    hook_calls = []
    old_hook = threading.excepthook

    def _hook(args):
        hook_calls.append(args)

    def _reader():
        collected.extend(handle.lines())

    threading.excepthook = _hook
    try:
        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()
        assert _SlowStreamHandler.first_line_sent.wait(timeout=5), "première ligne jamais reçue"
        time.sleep(0.2)  # laisse le fil de lecture se rebloquer sur la ligne suivante
        handle.close()
        reader.join(timeout=5)
        assert not reader.is_alive(), "le fil de lecture ne s'est jamais terminé après close()"
    finally:
        threading.excepthook = old_hook
        conn.close()

    assert hook_calls == [], f"exception non interceptée pendant la fermeture concurrente : {hook_calls}"
    assert collected == ["premiere-ligne"]


# ═══════════════════════════════════════════════════════════════════════
# 2. seek.py — cancel()/close(), évènement "found" après "seek_closed",
#    exception imprévue d'un fil secondaire (sans aucun socket réel).
# ═══════════════════════════════════════════════════════════════════════

def test_close_ne_journalise_pas_annulee_par_lutilisateur(tmp_path):
    transport = FakeTransport(open_stream_specs=[[""] * 5, [""] * 5])
    client = GameClient("lip_test", transport=transport)
    log = GameLog("recherche", logs_dir=tmp_path)
    session = SeekSession(client, game_log=log)
    session.start(15.0, 10, "white")
    session.next_event(timeout=0.1)

    session.close()
    log.close()

    content = log.path.read_text(encoding="utf-8")
    assert "annulée par l'utilisateur" not in content
    assert session._event_handle.closed is True
    assert session._seek_handle.closed is True


def test_cancel_journalise_bien_annulee_par_lutilisateur(tmp_path):
    transport = FakeTransport(open_stream_specs=[[""] * 5, [""] * 5])
    client = GameClient("lip_test", transport=transport)
    log = GameLog("recherche", logs_dir=tmp_path)
    session = SeekSession(client, game_log=log)
    session.start(15.0, 10, "white")
    session.next_event(timeout=0.1)

    session.cancel()
    log.close()

    content = log.path.read_text(encoding="utf-8")
    assert "annulée par l'utilisateur" in content


class _DelayedLineHandle:
    """Double de StreamHandle qui attend réellement `delay_s` avant de
    produire la ligne d'indice `delay_before_index` — seul moyen de forcer
    de façon déterministe, sans vrai réseau, l'ordre « flux de recherche
    fermé D'ABORD, gameStart lu ENSUITE » : avec des doubles purement
    synchrones (FakeStreamHandle), les deux fils se disputent le GIL sans
    garantie d'ordre, même avec des listes de tailles différentes."""

    def __init__(self, lines, delay_before_index=None, delay_s=0.3):
        self._lines = list(lines)
        self.closed = False
        self._delay_before_index = delay_before_index
        self._delay_s = delay_s

    def close(self):
        self.closed = True

    def lines(self):
        for i, item in enumerate(self._lines):
            if self.closed:
                return
            if i == self._delay_before_index:
                time.sleep(self._delay_s)
            yield item


class _DelayedGameStartClient:
    """gameStart arrive après un vrai délai — le flux de recherche (une
    seule ligne, aucun délai) a largement eu le temps de se fermer avant."""

    def open_event_stream(self):
        lines = ["", "", _gamestart_line(color="white", username="Bob")]
        return _DelayedLineHandle(lines, delay_before_index=2, delay_s=0.3)

    def open_seek_stream(self, *a, **kw):
        return _FakeHandleForClient([""])


def test_found_arrive_apres_seek_closed_le_fil_devenements_reste_actif():
    """Cœur du bug #328 : le flux de recherche peut se fermer AVANT que
    gameStart n'arrive sur le flux d'évènements. seek.py ne doit JAMAIS
    fermer ce dernier tant qu'il n'a pas lu gameStart (ou reçu
    cancel()/close()) — "seek_closed" n'est qu'une notification."""
    session = SeekSession(_DelayedGameStartClient())
    session.start(15.0, 10, "")

    seen_types = []
    found_game = None
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        ev = session.next_event(timeout=0.05)
        if ev:
            seen_types.append(ev["type"])
            if ev["type"] == "found":
                found_game = ev["game"]
                break
    assert "seek_closed" in seen_types, f"seek_closed jamais vu avant found : {seen_types}"
    assert found_game is not None, f"found jamais reçu après seek_closed : {seen_types}"
    assert found_game["opponent"]["username"] == "Bob"


class _BrokenHandle:
    """Double dont lines() lève directement une exception imprévue — ne
    simule pas la fermeture concurrente réelle (déjà couverte ci-dessus
    avec un vrai socket), mais vérifie que seek.py, en défense en
    profondeur, n'en laisse jamais échapper une sans la journaliser."""

    def __init__(self, exc):
        self._exc = exc
        self.closed = False

    def close(self):
        self.closed = True

    def lines(self):
        raise self._exc


def test_exception_imprevue_fil_evenements_journalisee_et_signalee(tmp_path, caplog):
    class _BrokenEventClient:
        def open_event_stream(self):
            return _BrokenHandle(AttributeError("'NoneType' object has no attribute 'peek'"))

        def open_seek_stream(self, *a, **kw):
            return _FakeHandleForClient([""] * 100)

    log = GameLog("recherche", logs_dir=tmp_path)
    session = SeekSession(_BrokenEventClient(), game_log=log)
    with caplog.at_level(logging.ERROR, logger="niclink.lichess"):
        session.start(15.0, 10, "")
        got_error = False
        # Le flux de recherche (100 lignes "waiting") doit être intégralement
        # consommé avant que l'évènement "error" (poussé par le flux
        # d'évènements, en exception immédiate) ne soit forcément atteint —
        # boucle bornée en temps, pas en nombre d'évènements.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            ev = session.next_event(timeout=0.05)
            if ev and ev["type"] == "error":
                got_error = True
                break
    log.close()

    assert got_error, "aucun évènement 'error' poussé après l'exception imprévue"
    assert any("exception imprévue" in r.message for r in caplog.records)
    content = log.path.read_text(encoding="utf-8")
    assert "AttributeError" in content


# ═══════════════════════════════════════════════════════════════════════
# 3. _run_lichess_human — "seek_closed" : attente de gameStart, adoption
#    depuis la liste des parties en cours, messages distincts, compteur.
# ═══════════════════════════════════════════════════════════════════════

class _LateGameStartClient(_HumanGameClient):
    """gameStart arrive APRÈS que le flux de recherche se soit fermé —
    exactement le scénario observé le 14/11/2026."""

    def open_event_stream(self):
        return _FakeHandleForClient(
            [""] * 10 + [_gamestart_line(self.game_id, self.user_color, self.opponent_name)]
        )

    def open_seek_stream(self, *a, **kw):
        return _FakeHandleForClient([""])  # fermé par Lichess presque immédiatement


class _NeverGameStartClient(_HumanGameClient):
    """gameStart n'arrive jamais — recherche vraiment close sans
    appariement, ou appariement dont gameStart s'est perdu (selon ce que
    la liste des parties en cours révèle ensuite)."""

    def open_event_stream(self):
        return _FakeHandleForClient([""] * 50)

    def open_seek_stream(self, *a, **kw):
        return _FakeHandleForClient([""])


def _basic_monkeypatches(monkeypatch, client, grace_s=0.3):
    board = _ScriptedBoard([INITIAL_FEN_W])
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    monkeypatch.setattr(lichess_launcher, "_SEEK_CLOSED_GRACE_S", grace_s)
    return board


def test_seek_closed_puis_gamestart_pendant_lattente_rejoint_la_partie(monkeypatch):
    client = _LateGameStartClient()
    _basic_monkeypatches(monkeypatch, client, grace_s=2.0)

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is False


def test_seek_closed_sans_gamestart_partie_adoptee_depuis_la_liste(monkeypatch):
    client = _NeverGameStartClient()
    _basic_monkeypatches(monkeypatch, client, grace_s=0.3)

    ongoing_games = [{
        "game_id": "adopted1", "color": "white", "opponent": "Bob", "speed": "rapid",
        "is_my_turn": True, "seconds_left": 500, "resumable": False,
    }]
    calls = {"n": 0}

    def _fake_fetch(token):
        calls["n"] += 1
        # 1er appel : garde-fou "une seule partie à la fois" AVANT la
        # recherche (doit laisser démarrer) ; appels suivants : consultation
        # après "seek_closed" — la partie est apparue DEPUIS.
        return [] if calls["n"] == 1 else ongoing_games

    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", _fake_fetch)
    sent_events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent_events.append((etype, data)))

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_seek_partie_non_ouverte"
    assert _error["return_to"] == "config_lichess"
    resumable_events = [d for t, d in sent_events if t == "lichess_resumable"]
    assert resumable_events, "aucun évènement lichess_resumable envoyé — partie adoptée jamais signalée"
    assert resumable_events[-1]["available"] is True
    assert resumable_events[-1]["games"] == ongoing_games


def test_seek_closed_sans_gamestart_et_sans_partie_message_distinct(monkeypatch):
    client = _NeverGameStartClient()
    _basic_monkeypatches(monkeypatch, client, grace_s=0.3)

    calls = {"n": 0}

    def _fake_fetch(token):
        calls["n"] += 1
        return []  # jamais aucune partie, ni avant ni après la recherche

    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", _fake_fetch)
    sent_events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent_events.append((etype, data)))

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_seek_sans_adversaire"
    assert _error["return_to"] == "config_lichess"
    resumable_events = [d for t, d in sent_events if t == "lichess_resumable"]
    assert not resumable_events, "lichess_resumable envoyé alors qu'aucune partie n'existe"


def test_messages_toast_echec_sans_adversaire_partie_non_ouverte_et_reseau_sont_distincts():
    """Point 3 : jamais le message "Connexion impossible — vérifiez le
    réseau" pour une recherche simplement close sans adversaire, ni pour
    un adversaire trouvé mais mal ouvert — trois messages bien distincts."""
    reseau = _TOAST_MESSAGES["toast.lichess_network_error"]
    sans_adversaire = _TOAST_MESSAGES["toast.lichess_seek_sans_adversaire"]
    partie_non_ouverte = _TOAST_MESSAGES["toast.lichess_seek_partie_non_ouverte"]
    assert len({reseau, sans_adversaire, partie_non_ouverte}) == 3
    assert "réseau" not in sans_adversaire.lower()
    assert "réseau" not in partie_non_ouverte.lower()


def test_compteur_temps_ecoule_compte_depuis_avant_l_ouverture_des_flux(monkeypatch):
    """Point 5 : le compteur affiché doit refléter le temps depuis le vrai
    début de la recherche — y compris la mise en place réseau (garde-fou
    "une seule partie à la fois" + ouverture des deux flux), qui précédait
    jusqu'ici le point de départ du compteur (search_start capturé trop
    tard, d'où l'écart observé le 14/11/2026, "0:03" neuf secondes après
    la position confirmée)."""
    client = _HumanGameClient()  # gameStart dès la première ligne — partie trouvée tout de suite
    _basic_monkeypatches(monkeypatch, client)

    sleep_s = 0.6

    def _slow_refuse(token):
        time.sleep(sleep_s)

    monkeypatch.setattr(lichess_launcher, "_refuse_create_if_games_ongoing", _slow_refuse)
    sent_events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent_events.append((etype, data)))

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    ticks = [d["elapsed_s"] for t, d in sent_events if t == "lichess_seek_tick"]
    assert ticks, "aucun lichess_seek_tick envoyé"
    assert ticks[0] >= sleep_s - 0.05, (
        f"le premier tick ({ticks[0]:.2f}s) ne tient pas compte du délai de mise en "
        f"place ({sleep_s}s) — le compteur ne part pas du vrai début de la recherche"
    )
