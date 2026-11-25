"""
nicsoft/tests/test_issue387_lichess_puzzle_session.py — AlChess

Issue #387, point 2 : séance de N problèmes Lichess avec compteur et
bilan — `_PuzzleSessionTracker`/`_build_puzzle_session`/
`_show_puzzle_session_summary_and_wait` (nicsoft/core/game_manager_modes/
lichess.py). Même esprit que test_issue364_lichess_puzzle_virtuel.py :
mode virtuel (jamais d'échiquier physique à simuler), faux client
Lichess, jamais de réseau réel.

Le lanceur de séance (`_show_puzzle_session_summary_and_wait`) lit
`get_action` (nicsoft.core.ihm_port) directement — contrairement à
PuzzleGame, qui reçoit sa propre fonction `get_action` monkeypatchée côté
module `puzzle_game`. Les tests d'intégration ci-dessous monkeypatchent
donc LES DEUX noms (`puzzle_game_mod.get_action` et
`lichess_launcher.get_action`) vers la MÊME file de test, pour que le
"back_menu" déposé par le pilote de test après le dernier problème soit
bien celui que lit l'écran de bilan (en vrai : une seule action_queue
partagée, voir server.py)."""

import queue
import threading
import time

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod
from nicsoft.core.game_manager_modes.lichess import (
    _PuzzleSeriesSpec,
    _PuzzleSessionTracker,
    _build_puzzle_session,
    _show_puzzle_session_summary_and_wait,
)
from nicsoft.modes.lichess.puzzle_game import VirtualPuzzleGame


def _make_recorder(monkeypatch, patch_launcher_get_action=False):
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
    if patch_launcher_get_action:
        monkeypatch.setattr(lichess_launcher, "get_action", fake_get_action)
    return events, actions


def _events_of(events, etype):
    return [d for t, d in events if t == etype]


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
        "game_id": "g1",
        "rated": True,
        "players": [],
    }


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _start_driver(func):
    """Lance `func` dans un fil daemon qui capture toute exception —
    sinon une assertion échouée dans le pilote de test (fil séparé) ne
    remonterait jamais au fil principal, qui resterait bloqué pour
    toujours sur l'action suivante jamais déposée (voir le rapport de
    clôture : piège réel rencontré en écrivant ces tests)."""
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


class _FakeGame:
    """Double minimal — tout ce que _PuzzleSessionTracker.record() lit."""

    def __init__(self, outcome, puzzle_id="pzl1", rating=1500, duration_s=1.0, rating_diff=None):
        self.outcome = outcome
        self.puzzle_id = puzzle_id
        self.rating = rating
        self.duration_s = duration_s
        self.rating_diff = rating_diff


class _FakeGameLog:
    def __init__(self, *a, **k):
        pass

    def state_change(self, *a, **k):
        pass

    def exception(self, *a, **k):
        pass

    def close(self):
        pass


# ── _PuzzleSessionTracker — unités pures ────────────────────────────────────

def test_record_solved_incremente_solved_et_completed():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 3)])
    tracker.record(_FakeGame("solved"))
    assert tracker.completed == 1
    assert tracker.solved == 1
    assert tracker.failed == 0
    assert tracker.failed_puzzles == []


def test_record_failed_ajoute_a_la_liste_des_rates():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 3)])
    tracker.record(_FakeGame("failed", puzzle_id="pzl_x", rating=1600))
    assert tracker.failed == 1
    assert tracker.completed == 1
    assert tracker.failed_puzzles == [{"puzzle_id": "pzl_x", "rating": 1600}]


def test_is_complete_vrai_seulement_une_fois_le_total_atteint():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 2)])
    assert tracker.is_complete() is False
    tracker.record(_FakeGame("solved"))
    assert tracker.is_complete() is False
    tracker.record(_FakeGame("failed"))
    assert tracker.is_complete() is True


def test_is_complete_toujours_faux_sans_limite():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 0)])
    for _ in range(50):
        tracker.record(_FakeGame("solved"))
    assert tracker.is_complete() is False


def test_summary_payload_duree_moyenne_et_variation_totale():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 3)])
    tracker.record(_FakeGame("solved", duration_s=10.0, rating_diff=6))
    tracker.record(_FakeGame("failed", duration_s=20.0, rating_diff=-8))
    tracker.record(_FakeGame("solved", duration_s=30.0, rating_diff=5))
    payload = tracker.summary_payload()
    assert payload["solved"] == 2
    assert payload["failed"] == 1
    assert payload["avg_duration_s"] == 20.0
    assert payload["rating_diff_total"] == 3  # 6 - 8 + 5


def test_summary_payload_variation_inconnue_sans_aucune_cote_connue():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 1)])
    tracker.record(_FakeGame("failed", duration_s=5.0, rating_diff=None))
    payload = tracker.summary_payload()
    assert payload["rating_diff_total"] is None
    assert payload["avg_duration_s"] == 5.0


def test_summary_payload_sans_aucun_probleme_termine():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 5)])
    payload = tracker.summary_payload()
    assert payload["solved"] == 0
    assert payload["failed"] == 0
    assert payload["avg_duration_s"] is None
    assert payload["rating_diff_total"] is None
    assert payload["failed_puzzles"] == []


# ── _build_puzzle_session — lecture de config.json (mécanisme existant) ────

def test_build_puzzle_session_defaut_25(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {})
    session = _build_puzzle_session()
    assert session.total == 25
    assert session.current_theme == ""


def test_build_puzzle_session_taille_personnalisee(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_puzzle_session_size": 3})
    session = _build_puzzle_session()
    assert session.total == 3


def test_build_puzzle_session_zero_est_sans_limite(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_puzzle_session_size": 0})
    session = _build_puzzle_session()
    assert session.total == 0
    session.record(_FakeGame("solved"))
    assert session.is_complete() is False


def test_build_puzzle_session_valeur_invalide_repliee_sur_25(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_puzzle_session_size": "abc"})
    session = _build_puzzle_session()
    assert session.total == 25


def test_build_puzzle_session_valeur_negative_bornee_a_zero(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_puzzle_session_size": -5})
    session = _build_puzzle_session()
    assert session.total == 0


# ── _show_puzzle_session_summary_and_wait ───────────────────────────────────

def test_show_summary_affiche_le_bilan_et_bloque_jusqu_au_retour_menu(monkeypatch):
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    actions = queue.Queue()

    def fake_get_action(timeout=0.0):
        try:
            return actions.get(timeout=timeout)
        except queue.Empty:
            return None

    monkeypatch.setattr(lichess_launcher, "get_action", fake_get_action)

    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec("", 1)])
    tracker.record(_FakeGame("solved", duration_s=4.0, rating_diff=3))

    done = threading.Event()

    def _run():
        _show_puzzle_session_summary_and_wait(tracker)
        done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert _wait_until(lambda: bool(sent_states))
    assert sent_states[0][0] == "lichess_puzzle_session_summary"
    assert sent_states[0][1] == tracker.summary_payload()
    # Une action hors-sujet ne doit pas débloquer l'attente.
    actions.put({"type": "lichess_puzzle_retry_submit"})
    time.sleep(0.1)
    assert not done.is_set()
    actions.put({"type": "back_menu"})
    t.join(timeout=2.0)
    assert done.is_set()


# ── Routage (états actifs) ───────────────────────────────────────────────────

def test_lichess_puzzle_session_summary_est_un_etat_actif_lichess():
    """Jamais borné par _LICHESS_STOP_TIMEOUT_S (voir
    _join_lichess_launcher_thread) — l'utilisateur doit pouvoir lire le
    bilan sans limite de temps, comme "lichess_puzzle_playing"."""
    assert "lichess_puzzle_session_summary" in lichess_launcher._LICHESS_ACTIVE_STATES


# ── Intégration bout en bout (mode virtuel, sans échiquier) ─────────────────

def test_session_de_deux_problemes_affiche_le_bilan_a_la_fin(monkeypatch):
    events, actions = _make_recorder(monkeypatch, patch_launcher_get_action=True)
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_token": "lip_test_token", "lichess_puzzle_session_size": 2,
    })
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)

    import nicsoft.modes.lichess.client as lichess_client
    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "has_puzzle_read": True, "has_puzzle_write": True,
    })

    puzzle1 = _puzzle(["e2e4"], puzzle_id="pzl1", rating=1500)
    puzzle2 = _puzzle(["d2d4"], puzzle_id="pzl2", rating=1510)
    served = {"n": 0}

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod

    def fake_get_next_puzzle(token, difficulty=None, angle=None):
        idx = served["n"]
        served["n"] += 1
        return {"status": "ok", **(puzzle1 if idx == 0 else puzzle2)}

    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", fake_get_next_puzzle)

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": 5 if win else -3, "new_rating": 1505 if win else 1497}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)

    import nicsoft.modes.lichess.game_log as game_log_mod
    monkeypatch.setattr(game_log_mod, "GameLog", _FakeGameLog)

    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        # Problème 1 : coup correct, puis "Problème suivant".
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        assert _wait_until(lambda: _events_of(events, "lichess_puzzle_your_turn"))
        actions.put({"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4"})
        assert _wait_until(lambda: any(
            r.get("win") is True for r in _events_of(events, "lichess_puzzle_result")
        ))
        # Course bénigne, propre au double de test (même esprit que le
        # commentaire équivalent de test_issue354_lichess_puzzles_l3.py) :
        # juste après avoir traité le coup, VirtualPuzzleGame._process_browser_actions()
        # reboucle une dernière fois sur get_action(timeout=0.0) avant de
        # rendre la main à run() — un "lichess_puzzle_next" déposé dans ce
        # tout petit instant serait lu là (aucun type ne correspond dans
        # cette méthode) plutôt que par _wait_post_result_decision(), et
        # donc silencieusement perdu. Sans effet en usage réel (l'utilisateur
        # ne clique jamais "Problème suivant" dans la même milliseconde que
        # la réception du résultat) ; cette petite pause évite seulement de
        # reproduire cette fenêtre dans le test.
        time.sleep(0.1)
        actions.put({"type": "lichess_puzzle_next"})
        # Problème 2 (dernier de la séance, taille 2) : coup faux, puis
        # "Problème suivant" → doit déclencher le bilan, jamais un 3e
        # problème.
        assert _wait_until(lambda: served["n"] >= 2)
        assert _wait_until(lambda: len(_events_of(events, "lichess_puzzle_your_turn")) >= 2)
        actions.put({"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e3"})  # légal, faux
        assert _wait_until(lambda: any(
            r.get("win") is False for r in _events_of(events, "lichess_puzzle_result")
        ))
        time.sleep(0.1)  # même course bénigne que ci-dessus
        actions.put({"type": "lichess_puzzle_next"})
        assert _wait_until(lambda: any(s == "lichess_puzzle_session_summary" for s, _ in sent_states))
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
        lichess_launcher.web_server._app_state = "menu"

    assert not errors, errors
    assert not launcher_thread.is_alive(), "launch_lichess_puzzle n'est jamais revenu (séance bloquée)"
    assert served["n"] == 2  # jamais de 3e problème demandé

    playing_states = [d for s, d in sent_states if s == "lichess_puzzle_playing"]
    assert [d["puzzle_index"] for d in playing_states] == [1, 2]
    assert [d["puzzle_total"] for d in playing_states] == [2, 2]

    summary_states = [d for s, d in sent_states if s == "lichess_puzzle_session_summary"]
    assert len(summary_states) == 1
    summary = summary_states[0]
    assert summary["solved"] == 1
    assert summary["failed"] == 1
    assert summary["failed_puzzles"] == [{"puzzle_id": "pzl2", "rating": 1510}]
    assert summary["rating_diff_total"] == 2  # 5 (résolu) - 3 (raté)


def test_retour_menu_en_cours_de_seance_ne_montre_jamais_le_bilan(monkeypatch):
    """Retour au menu après le 1er problème (sur une séance de 3) — direct,
    sans bilan (comportement demandé par l'énoncé)."""
    events, actions = _make_recorder(monkeypatch, patch_launcher_get_action=True)
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_token": "lip_test_token", "lichess_puzzle_session_size": 3,
    })
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)

    import nicsoft.modes.lichess.client as lichess_client
    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "has_puzzle_read": True, "has_puzzle_write": True,
    })

    puzzle1 = _puzzle(["e2e4"], puzzle_id="pzl1")

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {
        "status": "ok", **puzzle1,
    })
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **k: {
        "status": "ok", "rating_diff": 2, "new_rating": 1502,
    })

    import nicsoft.modes.lichess.game_log as game_log_mod
    monkeypatch.setattr(game_log_mod, "GameLog", _FakeGameLog)

    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        assert _wait_until(lambda: _events_of(events, "lichess_puzzle_your_turn"))
        actions.put({"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4"})
        assert _wait_until(lambda: any(
            r.get("win") is True for r in _events_of(events, "lichess_puzzle_result")
        ))
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
        lichess_launcher.web_server._app_state = "menu"

    assert not errors, errors
    assert not launcher_thread.is_alive(), "launch_lichess_puzzle n'est jamais revenu"
    assert not any(s == "lichess_puzzle_session_summary" for s, _ in sent_states)
