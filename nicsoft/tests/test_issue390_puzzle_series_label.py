"""
nicsoft/tests/test_issue390_puzzle_series_label.py — AlChess

Issue #390, point 4 : thème/phase CHOISI pour la série transmis dans le
payload "lichess_puzzle_playing" (series_theme/series_type) — et jamais
les thèmes propres du problème reçu (`puzzle["themes"]`, absent par
construction de ce payload, fair-play). Sans réseau ni matériel (mode
virtuel), même pattern d'intégration que
test_issue390_puzzle_fen_actions.py."""

import queue
import threading
import time

import chess

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _FakeGameLog:
    def __init__(self, *a, **k):
        pass

    def state_change(self, *a, **k):
        pass

    def exception(self, *a, **k):
        pass

    def close(self):
        pass


def _run_one_virtual_puzzle(monkeypatch, config):
    events = []
    actions = queue.Queue()
    sent_states = []

    def fake_get_action(timeout=0.0):
        try:
            return actions.get(timeout=timeout)
        except queue.Empty:
            return None

    monkeypatch.setattr(puzzle_game_mod, "send_event", lambda e, d: events.append((e, d)))
    monkeypatch.setattr(puzzle_game_mod, "get_action", fake_get_action)
    monkeypatch.setattr(lichess_launcher, "get_action", fake_get_action)
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_token": "lip_test_token", "lichess_puzzle_session_size": 1,
        **config,
    })
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)

    import nicsoft.modes.lichess.client as lichess_client
    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "account": "", "has_puzzle_read": True, "has_puzzle_write": True,
    })

    start = chess.Board()
    puzzle = {
        "puzzle_id": "pzl_label", "rating": 1500, "themes": ["fork", "middlegame"],
        "solution": ["e2e4"], "fen": start.fen(), "setup_fen": start.fen(),
        "opponent_first_move": None, "game_id": "g1", "rated": True, "players": [],
    }
    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {
        "status": "ok", **puzzle,
    })
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **kw: {
        "status": "ok", "rating_diff": 1, "new_rating": 1501,
    })
    import nicsoft.modes.lichess.game_log as game_log_mod
    monkeypatch.setattr(game_log_mod, "GameLog", _FakeGameLog)

    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        assert _wait_until(lambda: any(e == "lichess_puzzle_your_turn" for e, _ in events))
        actions.put({"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4"})
        assert _wait_until(lambda: any(d.get("win") is True for e, d in events if e == "lichess_puzzle_result"))
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    launcher_thread = threading.Thread(
        target=lambda: lichess_launcher.launch_lichess_puzzle({"player": "Alain", "puzzle_mode": "virtual"}),
        daemon=True,
    )
    driver.start()
    launcher_thread.start()
    try:
        launcher_thread.join(timeout=5.0)
    finally:
        driver.join(timeout=1.0)
        lichess_launcher.web_server._app_state = "menu"

    assert not launcher_thread.is_alive()
    playing_states = [d for s, d in sent_states if s == "lichess_puzzle_playing"]
    assert len(playing_states) == 1
    return playing_states[0]


def test_serie_theme_transmise(monkeypatch):
    payload = _run_one_virtual_puzzle(monkeypatch, {
        "lichess_puzzle_series_mode": "theme", "lichess_puzzle_theme": "fork",
    })
    assert payload["series_theme"] == "fork"
    assert payload["series_type"] == "theme"


def test_serie_phase_transmise(monkeypatch):
    payload = _run_one_virtual_puzzle(monkeypatch, {
        "lichess_puzzle_series_mode": "phase", "lichess_puzzle_phase": "endgame",
    })
    assert payload["series_theme"] == "endgame"
    assert payload["series_type"] == "phase"


def test_serie_melange_transmise(monkeypatch):
    payload = _run_one_virtual_puzzle(monkeypatch, {})
    assert payload["series_theme"] == ""
    assert payload["series_type"] == "mix"


def test_themes_propres_du_probleme_jamais_dans_ce_payload(monkeypatch):
    """Fair-play : puzzle["themes"] (= ["fork", "middlegame"] ci-dessus)
    ne doit jamais apparaître sous quelque forme que ce soit dans le
    payload "lichess_puzzle_playing" — absent par construction, pas
    seulement caché côté client."""
    payload = _run_one_virtual_puzzle(monkeypatch, {
        "lichess_puzzle_series_mode": "theme", "lichess_puzzle_theme": "fork",
    })
    assert "themes" not in payload
