"""
nicsoft/tests/test_issue390_puzzle_rating_hidden.py — AlChess

Issue #390, point 7 : cote du PROBLÈME masquée pendant la résolution —
`"rating"` absent (par construction, pas seulement caché) du payload
"lichess_puzzle_playing" envoyé par les deux lanceurs (échiquier et
virtuel). Toujours présente dans le payload de résultat
(PuzzleGame._result_payload, inchangé par cette issue). Sans réseau ni
matériel (mode virtuel), même pattern d'intégration que
test_issue390_puzzle_series_label.py."""

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


def test_rating_absent_du_payload_lichess_puzzle_playing(monkeypatch):
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
    })
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)

    import nicsoft.modes.lichess.client as lichess_client
    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "account": "", "has_puzzle_read": True, "has_puzzle_write": True,
    })

    start = chess.Board()
    # Cote repérable (1766, comme l'exemple donné par Alain dans l'issue) —
    # sert aussi au test e2e explicite (test_issue390_puzzle_fairplay_e2e.py).
    puzzle = {
        "puzzle_id": "pzl_cache", "rating": 1766, "themes": ["fork"],
        "solution": ["e2e4"], "fen": start.fen(), "setup_fen": start.fen(),
        "opponent_first_move": None, "game_id": "g1", "rated": True, "players": [],
    }
    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {
        "status": "ok", **puzzle,
    })
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **kw: {
        "status": "ok", "rating_diff": 14, "new_rating": 1680,
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
    assert "rating" not in playing_states[0]

    result_events = [d for e, d in events if e == "lichess_puzzle_result"]
    assert len(result_events) == 1
    assert result_events[0]["rating"] == 1766
