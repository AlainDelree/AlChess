"""
nicsoft/tests/test_issue314_lichess_board_reconnect.py — AlChess

Issue #314 : Lichess — reprise automatique quand la lecture de l'échiquier
échoue (y compris pendant l'attente du premier coup), et diagnostic de la
cause dans nicsoft/niclink/hid_backend.py.

Entièrement sans matériel (faux module hidapi et faux plateaux — doubles
exposant get_fen()/connect()/is_connected() comme le fait le vrai backend)
ni réseau (faux transport/client Lichess, voir test_issue309). driver.py
n'est jamais modifié ni mocké à un niveau plus bas que nécessaire.
"""
import logging
import threading
import time

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.lichess import _BackMenuDuringWait, _ResumeToPositionSetup
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.game import legal_move_for_hardware
from nicsoft.niclink import hid_backend
from nicsoft.tests.test_issue292_board_cleanup import _FakeDevice, _FakeHidModule
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, _events_of, _make_game, _make_recorder
from nicsoft.tests.test_issue311_lichess_sequencing import AFTER_E2E4_W, INITIAL_FEN_W, _RecordingClient


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    hid_backend._reset_state()
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    hid_backend._reset_state()


def _patch_timings(monkeypatch):
    """Réduit à quelques millisecondes les délais de détection/reconnexion
    du module lanceur Lichess, pour des tests rapides et déterministes
    (le comportement exercé est identique, seule la cadence change)."""
    monkeypatch.setattr(lichess_launcher, "_BOARD_LOST_EMPTY_S", 0.0)
    monkeypatch.setattr(lichess_launcher, "_RECONNECT_FAST_INTERVAL_S", 0.01)
    monkeypatch.setattr(lichess_launcher, "_RECONNECT_FAST_DURATION_S", 0.02)
    monkeypatch.setattr(lichess_launcher, "_RECONNECT_SLOW_INTERVAL_S", 0.01)
    monkeypatch.setattr(lichess_launcher, "_RECONNECT_POLL_STEP_S", 0.01)
    monkeypatch.setattr(lichess_launcher, "_UNRECOGNIZED_MOVE_DELAY_S", 0.0)


# ── Double de plateau reconnectable (get_fen/connect/is_connected) ───────────

class _ReconnectableScriptedBoard:
    """Double de nl_inst pour les tests de reconnexion : une liste de FEN
    ("" = lecture perdue, comme le retour permanent de hid_backend.get_fen()
    après une erreur de lecture) consommée dans l'ordre puis répétée.
    `connect()` peut être scriptée pour échouer `connect_failures` fois puis
    réussir, en republiant éventuellement une nouvelle séquence de lecture
    (simule la position relue après reconnexion)."""

    def __init__(self, fen_sequence, connect_failures=0, post_reconnect_sequence=None):
        self._sequence = list(fen_sequence)
        self._idx = 0
        self._connect_failures = connect_failures
        self._post_reconnect_sequence = post_reconnect_sequence
        self.connect_calls = 0
        self.fen_reader_restarts = 0
        self._connected = True
        self.nl_interface = self  # is_connected() exposée comme sur le vrai nl_inst
        self.led_calls = []
        self.leds_off_count = 0
        self.beeped = 0
        self.disconnected = False

    def is_connected(self):
        return self._connected

    def get_fen(self):
        if self._idx < len(self._sequence):
            item = self._sequence[self._idx]
            self._idx += 1
        elif self._sequence:
            item = self._sequence[-1]
        else:
            item = ""
        self._connected = item != ""
        return item

    def connect(self):
        self.connect_calls += 1
        if self.connect_calls <= self._connect_failures:
            raise RuntimeError("échiquier non détecté")
        self._connected = True
        if self._post_reconnect_sequence is not None:
            self._sequence = list(self._post_reconnect_sequence)
            self._idx = 0

    def _start_fen_reader(self):
        self.fen_reader_restarts += 1

    def set_led(self, square, status):
        self.led_calls.append((square, status))

    def turn_off_all_leds(self):
        self.leds_off_count += 1

    def signal_lights(self, sig):
        pass

    def beep(self):
        self.beeped += 1

    def disconnect(self):
        self.disconnected = True


# ── 1. Échiquier perdu pendant l'attente du premier coup, puis reconnexion ───

def test_echiquier_perdu_pendant_attente_premier_coup_puis_coup_detecte(monkeypatch):
    _patch_timings(monkeypatch)
    board = _ReconnectableScriptedBoard(
        [""], connect_failures=1, post_reconnect_sequence=[AFTER_E2E4_W],
    )
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "lichess_wait_first_move")

    uci = lichess_launcher._wait_first_move_white_lichess(board, legal_move_for_hardware)

    assert uci == "e2e4"
    assert board.connect_calls == 2  # un échec puis un succès
    assert board.fen_reader_restarts == 1
    assert ("lichess_wait_board_lost", {}) in events
    assert ("lichess_wait_board_ok", {}) in events


# ── 2. Panne persistante : bannière, essais espacés, retour menu possible ────

def test_panne_persistante_banniere_essais_espaces_et_retour_menu_sans_partie(monkeypatch):
    _patch_timings(monkeypatch)
    board = _ReconnectableScriptedBoard([""], connect_failures=10**6)
    client = _RecordingClient(user_color="white")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)

    call_count = {"n": 0}

    def _fake_get_app_state():
        call_count["n"] += 1
        return "menu" if call_count["n"] > 20 else "connecting"

    monkeypatch.setattr(lichess_launcher, "get_app_state", _fake_get_app_state)
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "white", "15+10", "Alain", _error)

    assert client.created_with is None          # jamais de partie créée
    assert board.connect_calls >= 3              # plusieurs essais de reconnexion, espacés
    assert ("lichess_wait_board_lost", {}) in events
    assert _error["occurred"] is False            # retour menu volontaire, pas une erreur affichée
    assert board.disconnected is True             # échiquier libéré au retour menu


# ── 3. Premier coup illégal / non reconnu pendant l'attente ──────────────────

def test_coup_non_reconnu_pendant_attente_premier_coup(monkeypatch):
    _patch_timings(monkeypatch)
    moved_twice = chess.Board()
    moved_twice.push_uci("e2e4")
    moved_twice.push_uci("d7d5")
    illegal_fen_board = moved_twice.board_fen()

    board = _ReconnectableScriptedBoard([illegal_fen_board + " w - - 0 1"])
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))

    call_count = {"n": 0}

    def _fake_get_app_state():
        call_count["n"] += 1
        return "menu" if call_count["n"] > 10 else "lichess_wait_first_move"

    monkeypatch.setattr(lichess_launcher, "get_app_state", _fake_get_app_state)

    with pytest.raises(_BackMenuDuringWait):
        lichess_launcher._wait_first_move_white_lichess(board, legal_move_for_hardware)

    toasts = [d for (t, d) in events if t == "lichess_toast"]
    coup_non_reconnu = [d for d in toasts if d.get("message_key") == "lichess.coup_non_reconnu"]
    assert coup_non_reconnu, f"aucun toast coup_non_reconnu parmi {toasts}"
    squares = coup_non_reconnu[0]["vars"]["squares"]
    assert "e4" in squares or "d5" in squares


# ── Reprise sans coup légal après reconnexion : retour à la mise en place ────

def test_reprise_apres_reconnexion_sans_coup_legal_leve_resume_to_position_setup(monkeypatch):
    _patch_timings(monkeypatch)
    board = _ReconnectableScriptedBoard(
        [""], connect_failures=0,
        post_reconnect_sequence=["8/8/8/8/8/8/8/8 w - - 0 1"],
    )
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: None)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "lichess_wait_first_move")

    with pytest.raises(_ResumeToPositionSetup):
        lichess_launcher._wait_first_move_white_lichess(board, legal_move_for_hardware)


def test_reprise_sans_coup_legal_retourne_a_mise_en_place_puis_partie_creee(monkeypatch):
    """Bout en bout : position confirmée, échiquier perdu pendant l'attente
    du premier coup, reconnexion vers une position illisible (retour à
    l'écran de mise en place), confirmation de la position de départ, puis
    premier coup détecté normalement — jamais de partie créée avant ce
    dernier point (issue #314, point 2)."""
    _patch_timings(monkeypatch)
    board = _ReconnectableScriptedBoard(
        [INITIAL_FEN_W, ""],
        connect_failures=0,
        post_reconnect_sequence=["8/8/8/8/8/8/8/8 w - - 0 1", INITIAL_FEN_W, AFTER_E2E4_W],
    )
    client = _RecordingClient(user_color="white")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: None)

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is False
    assert client.created_with is not None
    assert client.moves_sent == ["e2e4"]


# ── 4. Perte en cours de partie : pas d'abandon automatique + recalage ───────

def test_board_lost_en_partie_reconnecte_automatiquement_et_recalibre(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    game.RECONNECT_FAST_INTERVAL_S = 0.01
    game.RECONNECT_SLOW_INTERVAL_S = 0.01

    class _ReconnectableBrokenBoard:
        def __init__(self):
            self.connect_calls = 0
            self.restarts = 0
            self._current_fen = ""

        @property
        def current_fen(self):
            return self._current_fen

        def connect(self):
            self.connect_calls += 1
            # Le plateau physique montre encore la position de départ (celle
            # d'avant la coupure), différente de celle de Lichess (après
            # e2e4) : la reconnexion seule ne suffit pas, l'affichage "cases
            # à corriger" doit rester actif jusqu'à ce que les pièces soient
            # remises en place.
            self._current_fen = INITIAL_FEN_W

        def _start_fen_reader(self):
            self.restarts += 1

    broken = _ReconnectableBrokenBoard()
    game.nl_inst = broken

    for _ in range(game.BOARD_LOST_STRIKES + 1):
        game._tick_physical()
    # La reconnexion automatique (fake, instantanée) peut déjà avoir
    # terminé pendant cette boucle — seule la bannière envoyée au moment
    # de la détection est garantie, pas l'état observé après coup.
    assert _events_of(events, "lichess_board_lost")
    assert game.game_over is False  # jamais d'abandon automatique

    deadline = time.time() + 2.0
    while broken.connect_calls == 0 and time.time() < deadline:
        time.sleep(0.01)
    assert broken.connect_calls >= 1

    deadline = time.time() + 2.0
    while game._reconnecting_in_progress and time.time() < deadline:
        time.sleep(0.01)

    assert broken.restarts >= 1
    assert game._board_lost is False
    assert game.game_over is False
    # Recalage sur la position de Lichess (pas sur la lecture physique) via
    # l'affichage existant "cases à corriger" (issue #314, point 2).
    assert game._awaiting_piece_reset is True
    assert game._reset_target_fen == game.board.board_fen()
    assert _events_of(events, "lichess_board_ok")


# ── 5. Un seul essai de reconnexion à la fois ────────────────────────────────

def test_un_seul_essai_de_reconnexion_a_la_fois_en_cours_de_partie(monkeypatch):
    _, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })

    class _SlowBrokenBoard:
        def __init__(self):
            self.connect_calls = 0
            self._current_fen = ""

        @property
        def current_fen(self):
            return self._current_fen

        def connect(self):
            self.connect_calls += 1
            time.sleep(0.1)  # laisse le temps au test d'observer l'essai en cours
            self._current_fen = AFTER_E2E4_W

        def _start_fen_reader(self):
            pass

    slow = _SlowBrokenBoard()
    game.nl_inst = slow

    for _ in range(game.BOARD_LOST_STRIKES + 1):
        game._tick_physical()
    assert game._reconnecting_in_progress is True

    # Un second tick pendant que la reconnexion est en cours ne doit jamais
    # relancer un second essai (protections de #292, issue #314 point 2).
    game._tick_physical()
    assert slow.connect_calls == 1

    deadline = time.time() + 2.0
    while game._reconnecting_in_progress and time.time() < deadline:
        time.sleep(0.01)
    assert slow.connect_calls == 1


def test_hid_backend_connect_lock_tenu_pendant_la_connexion(monkeypatch):
    """Au niveau le plus bas (hid_backend.py), le verrou de connexion est
    tenu pendant toute la durée de connect() — un second essai concurrent
    (reconnexion automatique Lichess + clic manuel sur "Connecter", par
    exemple) ne peut jamais s'exécuter en même temps (issue #292/#314)."""
    release_open = threading.Event()
    proceed = threading.Event()

    class _BlockingDevice(_FakeDevice):
        def open_path(self, path):
            super().open_path(path)
            release_open.set()
            proceed.wait(timeout=2.0)

    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: _BlockingDevice()))
    monkeypatch.setattr(hid_backend.time, "sleep", lambda *a, **k: None)

    t = threading.Thread(target=hid_backend.connect, daemon=True)
    t.start()
    assert release_open.wait(timeout=2.0)
    try:
        assert hid_backend._connect_lock.acquire(blocking=False) is False
    finally:
        proceed.set()
    t.join(timeout=2.0)
    assert hid_backend._connect_lock.acquire(blocking=False) is True
    hid_backend._connect_lock.release()


# ── Diagnostic (hid_backend.py) : une seule ligne par incident, enrichie ─────

def test_log_read_error_une_seule_fois_par_incident_puis_compte(caplog):
    hid_backend._read_error_active_dev = None
    hid_backend._read_error_count = 0
    caplog.set_level(logging.WARNING, logger="nicsoft.niclink.hid_backend")
    dev = object()
    exc = OSError(5, "Input/output error")
    for _ in range(3):
        hid_backend._log_read_error(dev, exc)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "OSError" in warnings[0].getMessage()
    assert "code=5" in warnings[0].getMessage()
    assert hid_backend._read_error_count == 3


def test_log_read_error_nouvel_incident_relance_un_avertissement(caplog):
    hid_backend._read_error_active_dev = None
    hid_backend._read_error_count = 0
    caplog.set_level(logging.WARNING, logger="nicsoft.niclink.hid_backend")
    hid_backend._log_read_error(object(), OSError("premier incident"))
    hid_backend._log_read_error(object(), OSError("second incident, périphérique différent"))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2


def test_get_fen_warning_enrichie_type_et_code(monkeypatch, caplog):
    class _ErrnoDevice(_FakeDevice):
        """Lit normalement pendant l'établissement de connect(), puis bascule
        en échec (errno 5) une fois `fail_now` activé par le test — sans ce
        découpage, une erreur dès la première lecture serait interprétée par
        connect() comme une perte pendant l'établissement (RuntimeError)."""
        def __init__(self):
            super().__init__()
            self.fail_now = False

        def read(self, size, timeout_ms=50):
            if self.fail_now:
                raise OSError(5, "Input/output error")
            return super().read(size, timeout_ms=timeout_ms)

    dev = _ErrnoDevice()
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: dev))
    monkeypatch.setattr(hid_backend.time, "sleep", lambda *a, **k: None)
    hid_backend.connect()
    dev.fail_now = True

    hid_backend._read_error_active_dev = None
    hid_backend._read_error_count = 0
    caplog.set_level(logging.WARNING, logger="nicsoft.niclink.hid_backend")

    assert hid_backend.get_fen() == ""
    assert hid_backend.is_connected() is False
    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("OSError" in m and "code=5" in m for m in msgs)


def test_connect_journalise_ouverture_fermeture_et_appelant(monkeypatch, caplog):
    dev = _FakeDevice()
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: dev))
    monkeypatch.setattr(hid_backend.time, "sleep", lambda *a, **k: None)
    caplog.set_level(logging.INFO, logger="nicsoft.niclink.hid_backend")

    def _appelant_de_test():
        hid_backend.connect()

    _appelant_de_test()

    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("ouverture demandée" in m and "_appelant_de_test" in m for m in infos)
    assert any("Chessnut connecté" in m for m in infos)

    caplog.clear()
    hid_backend.disconnect()
    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("fermeture demandée" in m for m in infos)
    assert any("connexion fermée" in m for m in infos)


# ── Aucune écriture dans les vrais dossiers utilisateur ──────────────────────

def test_aucune_ecriture_dans_les_vrais_dossiers(tmp_path):
    """Garde minimale : la fixture autouse de conftest.py redirige déjà
    GAMES_DIR vers un répertoire temporaire pour toute la suite — ce test
    vérifie que c'est bien le cas pendant ces tests de reconnexion Lichess,
    pour qu'une partie créée ici n'écrive jamais dans le vrai dossier de
    parties de l'utilisateur."""
    import nicsoft.engine.pgn_manager as pgn_manager
    assert pgn_manager.GAMES_DIR == tmp_path / "games"
