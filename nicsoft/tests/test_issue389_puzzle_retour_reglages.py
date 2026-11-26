"""
nicsoft/tests/test_issue389_puzzle_retour_reglages.py — AlChess

Issue #389, point 4 : le bouton "Retour aux réglages" du panneau de
problème Lichess (fin de problème ET en cours de séance) et de l'écran de
bilan doit ramener à l'écran de réglages des problèmes (config_lichess),
jamais au menu principal — contrairement à "back_menu" (inchangé partout
ailleurs). Nouveau geste `back_config_lichess` (server.py::on_action),
inspiré du mécanisme de retour "config_lichess" déjà utilisé après une
erreur Lichess (voir launch_lichess_puzzle). Entièrement sans réseau ni
échiquier réel (mode virtuel des problèmes, fausses fonctions réseau)."""

import queue
import threading
import time

import chess
import pytest
from unittest.mock import patch

import nicsoft.web.server as server
import nicsoft.core.game_manager as game_manager
import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod


# ═══════════════════════════════════════════════════════════════════════
# 1. server.py::on_action — routage du nouveau geste "back_config_lichess"
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _clean_server_state():
    server._app_state = "menu"
    for q in (server.action_queue, server.menu_queue, server.event_queue):
        while not q.empty():
            q.get_nowait()
    yield
    server._app_state = "menu"
    for q in (server.action_queue, server.menu_queue, server.event_queue):
        while not q.empty():
            q.get_nowait()


def _fake_checks(monkeypatch):
    calls = []
    monkeypatch.setattr(game_manager, "check_lichess_resumable", lambda: calls.append("resumable"))
    monkeypatch.setattr(game_manager, "check_lichess_network_status", lambda: calls.append("network"))
    monkeypatch.setattr(game_manager, "check_lichess_puzzle_dashboard", lambda: calls.append("dashboard"))
    return calls


@pytest.mark.parametrize("etat", ["lichess_puzzle_playing", "lichess_puzzle_session_summary"])
def test_back_config_lichess_pendant_etat_actif_met_app_state_config_lichess(monkeypatch, etat):
    calls = _fake_checks(monkeypatch)
    server._app_state = etat
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": "back_config_lichess"})
    assert server._app_state == "config_lichess"
    assert server.menu_queue.empty()  # jamais utilisé par ce geste
    assert not server.action_queue.empty()
    assert server.action_queue.get_nowait() == {"type": "back_menu"}
    # Tableau de bord/résumabilité/réseau rechargés immédiatement, comme à
    # toute ouverture de l'écran config_lichess (threads daemon — laisser le
    # temps de s'exécuter, fonctions ici instantanées).
    deadline = time.monotonic() + 2.0
    while len(calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sorted(calls) == ["dashboard", "network", "resumable"]


def test_back_config_lichess_depuis_un_etat_non_actif_ne_touche_pas_action_queue(monkeypatch):
    """Garde-fou symétrique à back_menu : si jamais appelé hors état actif
    (ne devrait pas arriver en usage réel, les deux boutons concernés
    n'étant visibles que dans des états actifs), aucune action n'est
    déposée dans action_queue (rien ne la lirait)."""
    _fake_checks(monkeypatch)
    server._app_state = "menu"
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": "back_config_lichess"})
    assert server._app_state == "config_lichess"
    assert server.action_queue.empty()


def test_back_config_lichess_distinct_de_back_menu_dans_app_js():
    """Garde statique minimale : le nouveau geste ne doit jamais réutiliser
    le literal 'sendAction({ type: "back_menu" })' déjà gardé par le test
    de l'issue #383 (compte figé à 1) — vérifie juste la présence d'un
    envoi distinct pour "back_config_lichess"."""
    import pathlib
    app_js = (pathlib.Path(__file__).parent.parent / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'sendAction({ type: "back_config_lichess" })' in app_js
    assert app_js.count('sendAction({ type: "back_menu" })') == 1


# ═══════════════════════════════════════════════════════════════════════
# 2. _wait_initial_position_lichess_puzzle — tolère "config_lichess" comme
#    "menu" pour sortir de l'attente de mise en place physique (mode
#    échiquier uniquement — mode virtuel n'appelle jamais cette fonction).
# ═══════════════════════════════════════════════════════════════════════

def test_wait_initial_position_puzzle_sort_sur_config_lichess(monkeypatch):
    monkeypatch.setattr(lichess_launcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "config_lichess")

    class _Board:
        def get_fen(self):
            return chess.Board().fen()

        def turn_off_all_leds(self):
            pass

    with pytest.raises(lichess_launcher._BackMenuDuringWait):
        lichess_launcher._wait_initial_position_lichess_puzzle(_Board(), chess.Board().fen(), "white")


# ═══════════════════════════════════════════════════════════════════════
# 3. Intégration bout en bout (mode virtuel, sans échiquier) — simule le
#    geste complet "back_config_lichess" (app_state forcé à "config_lichess"
#    AVANT le "back_menu" déposé dans action_queue, comme le fait
#    désormais on_action) pendant une séance en cours ET depuis l'écran de
#    bilan ; vérifie que launch_lichess_puzzle se termine bien sur
#    "config_lichess" (jamais écrasé par "menu") et qu'une relance
#    ultérieure est acceptée sans redémarrage (garde déjà existante :
#    launch_lichess_puzzle accepte "menu" ET "config_lichess").
# ═══════════════════════════════════════════════════════════════════════

def _make_recorder(monkeypatch):
    events = []
    actions = queue.Queue()

    def fake_send_event(event_type, data):
        events.append((event_type, data))

    def fake_get_action(timeout=0.0):
        try:
            return actions.get(timeout=timeout)
        except queue.Empty:
            return None

    monkeypatch.setattr(puzzle_game_mod, "send_event", fake_send_event)
    monkeypatch.setattr(puzzle_game_mod, "get_action", fake_get_action)
    monkeypatch.setattr(lichess_launcher, "get_action", fake_get_action)
    return events, actions


def _events_of(events, etype):
    return [d for t, d in events if t == etype]


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _start_driver(func):
    import traceback
    errors = []

    def _wrapped():
        try:
            func()
        except BaseException:  # noqa: BLE001 — capturé pour le fil principal
            errors.append(traceback.format_exc())

    t = threading.Thread(target=_wrapped, daemon=True)
    t.start()
    return t, errors


class _FakeGameLog:
    def __init__(self, *a, **k):
        pass

    def state_change(self, *a, **k):
        pass

    def exception(self, *a, **k):
        pass

    def close(self):
        pass


def _puzzle(solution, fen=None, puzzle_id="pzl1", rating=1500, themes=None):
    fen = fen or chess.Board().fen()
    return {
        "puzzle_id": puzzle_id,
        "rating": rating,
        "themes": themes or ["fork"],
        "solution": list(solution),
        "fen": fen,
        "setup_fen": fen,
        "opponent_first_move": None,
    }


def _common_monkeypatches(monkeypatch, session_size):
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_token": "lip_test_token", "lichess_puzzle_session_size": session_size,
    })
    import nicsoft.modes.lichess.client as lichess_client
    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "has_puzzle_read": True, "has_puzzle_write": True,
    })
    import nicsoft.modes.lichess.game_log as game_log_mod
    monkeypatch.setattr(game_log_mod, "GameLog", _FakeGameLog)


def test_retour_aux_reglages_en_cours_de_seance_atterrit_sur_config_lichess(monkeypatch):
    events, actions = _make_recorder(monkeypatch)
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    _common_monkeypatches(monkeypatch, session_size=3)

    puzzle1 = _puzzle(["e2e4"], puzzle_id="pzl1")
    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {
        "status": "ok", **puzzle1,
    })
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **k: {
        "status": "ok", "rating_diff": 2, "new_rating": 1502,
    })

    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        assert _wait_until(lambda: _events_of(events, "lichess_puzzle_your_turn"))
        actions.put({"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4"})
        assert _wait_until(lambda: any(
            r.get("win") is True for r in _events_of(events, "lichess_puzzle_result")
        ))
        # Simule on_action("back_config_lichess") : l'état cible est fixé
        # AVANT le "back_menu" déposé dans action_queue (ordre réel —
        # server.py::on_action).
        lichess_launcher.web_server._app_state = "config_lichess"
        actions.put({"type": "back_menu"})

    launcher_thread = threading.Thread(
        target=lambda: lichess_launcher.launch_lichess_puzzle({"player": "Alain", "puzzle_mode": "virtual"}),
        daemon=True,
    )
    driver, errors = _start_driver(_drive)
    launcher_thread.start()
    try:
        launcher_thread.join(timeout=5.0)
    finally:
        driver.join(timeout=1.0)

    assert not errors, errors
    assert not launcher_thread.is_alive(), "launch_lichess_puzzle n'est jamais revenu"
    assert not any(s == "lichess_puzzle_session_summary" for s, _ in sent_states)
    assert lichess_launcher.web_server._app_state == "config_lichess", (
        "l'état final a été écrasé par 'menu' au lieu de rester sur 'config_lichess'"
    )


def test_retour_aux_reglages_depuis_le_bilan_atterrit_sur_config_lichess(monkeypatch):
    events, actions = _make_recorder(monkeypatch)
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    _common_monkeypatches(monkeypatch, session_size=1)

    puzzle1 = _puzzle(["e2e4"], puzzle_id="pzl1")
    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {
        "status": "ok", **puzzle1,
    })
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **k: {
        "status": "ok", "rating_diff": 2, "new_rating": 1502,
    })

    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        assert _wait_until(lambda: _events_of(events, "lichess_puzzle_your_turn"))
        actions.put({"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4"})
        assert _wait_until(lambda: any(
            r.get("win") is True for r in _events_of(events, "lichess_puzzle_result")
        ))
        time.sleep(0.1)
        actions.put({"type": "lichess_puzzle_next"})
        assert _wait_until(lambda: any(s == "lichess_puzzle_session_summary" for s, _ in sent_states))
        # Simule on_action("back_config_lichess") depuis l'écran de bilan.
        lichess_launcher.web_server._app_state = "config_lichess"
        actions.put({"type": "back_menu"})

    launcher_thread = threading.Thread(
        target=lambda: lichess_launcher.launch_lichess_puzzle({"player": "Alain", "puzzle_mode": "virtual"}),
        daemon=True,
    )
    driver, errors = _start_driver(_drive)
    launcher_thread.start()
    try:
        launcher_thread.join(timeout=5.0)
    finally:
        driver.join(timeout=1.0)

    assert not errors, errors
    assert not launcher_thread.is_alive(), "launch_lichess_puzzle n'est jamais revenu"
    assert any(s == "lichess_puzzle_session_summary" for s, _ in sent_states)
    assert lichess_launcher.web_server._app_state == "config_lichess", (
        "l'état final a été écrasé par 'menu' au lieu de rester sur 'config_lichess'"
    )


def test_relance_dune_seance_acceptee_apres_retour_aux_reglages(monkeypatch):
    """launch_lichess_puzzle refuse de démarrer si l'état n'est ni "menu" ni
    "config_lichess" (garde-fou anti double-lancement déjà en place) — un
    retour aux réglages doit donc bien laisser l'état sur l'une des deux
    valeurs acceptées pour qu'une nouvelle séance démarre sans redémarrer
    AlChess."""
    events, actions = _make_recorder(monkeypatch)
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    _common_monkeypatches(monkeypatch, session_size=1)

    puzzle1 = _puzzle(["e2e4"], puzzle_id="pzl1")
    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {
        "status": "ok", **puzzle1,
    })
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **k: {
        "status": "ok", "rating_diff": 2, "new_rating": 1502,
    })

    # Simule l'état "config_lichess" laissé par un retour aux réglages
    # précédent (issue #389) — launch_lichess_puzzle doit démarrer normalement
    # (jamais le refus "mode déjà actif" que déclencherait tout autre état).
    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        # Si launch_lichess_puzzle avait refusé (garde "mode déjà actif"),
        # l'état ne passerait jamais à "lichess_puzzle_playing" — cette
        # attente est donc la preuve directe que la relance est acceptée.
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        actions.put({"type": "back_menu"})

    launcher_thread = threading.Thread(
        target=lambda: lichess_launcher.launch_lichess_puzzle({"player": "Alain", "puzzle_mode": "virtual"}),
        daemon=True,
    )
    driver, errors = _start_driver(_drive)
    launcher_thread.start()
    try:
        launcher_thread.join(timeout=5.0)
    finally:
        driver.join(timeout=1.0)

    assert not errors, errors
    assert not launcher_thread.is_alive()
