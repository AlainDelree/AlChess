"""
nicsoft/tests/test_issue390_puzzle_daily_counts.py — AlChess

Issue #390, point 2 : compteur du jour par type de série (Thème/Phase de
partie/Mélange), affiché dans l'écran de réglages des problèmes Lichess.
Purement local (aucun réseau) — l'historique local est toujours redirigé
vers un dossier temporaire (monkeypatch de puzzle_history.PUZZLE_HISTORY_FILE),
jamais le vrai dossier de données de l'utilisateur (voir CONSIGNES, règle
de test AlChess)."""

import datetime
import queue
import threading
import time

import chess

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod
import nicsoft.modes.lichess.puzzle_history as puzzle_history_mod
from nicsoft.core.game_manager_modes.lichess import (
    _PuzzleSeriesSpec,
    _build_puzzle_session,
    check_lichess_puzzle_daily_counts,
)
from nicsoft.modes.lichess.puzzle_game import PuzzleGame
from nicsoft.modes.lichess.puzzle_history import append_puzzle_history, daily_counts_by_type


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _FakeBoard:
    def __init__(self, initial_fen=chess.STARTING_BOARD_FEN):
        self.current_fen = initial_fen + " w - - 0 1"

    def get_fen(self):
        return self.current_fen

    def set_led(self, square, status):
        pass

    def turn_off_all_leds(self):
        pass

    def signal_lights(self, sig):
        pass

    def beep(self):
        pass

TODAY = datetime.date(2026, 11, 26)
YESTERDAY = datetime.date(2026, 11, 25)


def _entry(day, series_type=None, win=True, **extra):
    ts = datetime.datetime.combine(day, datetime.time(14, 30)).isoformat(timespec="seconds")
    entry = {"timestamp": ts, "puzzle_id": "p", "win": win}
    if series_type is not None:
        entry["series_type"] = series_type
    entry.update(extra)
    return entry


# ── puzzle_history.daily_counts_by_type ─────────────────────────────────

def test_fichier_absent_renvoie_zero_pour_les_trois_types(tmp_path, monkeypatch):
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", tmp_path / "absent.jsonl")
    counts = daily_counts_by_type(today=TODAY)
    assert counts == {
        "theme": {"done": 0, "solved": 0, "failed": 0},
        "phase": {"done": 0, "solved": 0, "failed": 0},
        "mix": {"done": 0, "solved": 0, "failed": 0},
    }


def test_compte_uniquement_les_enregistrements_du_jour(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history(_entry(TODAY, series_type="theme", win=True))
    append_puzzle_history(_entry(YESTERDAY, series_type="theme", win=True))
    counts = daily_counts_by_type(today=TODAY)
    assert counts["theme"] == {"done": 1, "solved": 1, "failed": 0}


def test_distingue_les_trois_types_et_solved_failed(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history(_entry(TODAY, series_type="theme", win=True))
    append_puzzle_history(_entry(TODAY, series_type="theme", win=False))
    append_puzzle_history(_entry(TODAY, series_type="phase", win=True))
    append_puzzle_history(_entry(TODAY, series_type="mix", win=False))
    counts = daily_counts_by_type(today=TODAY)
    assert counts["theme"] == {"done": 2, "solved": 1, "failed": 1}
    assert counts["phase"] == {"done": 1, "solved": 1, "failed": 0}
    assert counts["mix"] == {"done": 1, "solved": 0, "failed": 1}


def test_enregistrement_sans_type_compte_comme_melange(tmp_path, monkeypatch):
    """Antérieur à #388/#390 : pas de champ "series_type" du tout."""
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history(_entry(TODAY, series_type=None, win=True))
    counts = daily_counts_by_type(today=TODAY)
    assert counts["mix"] == {"done": 1, "solved": 1, "failed": 0}
    assert counts["theme"]["done"] == 0
    assert counts["phase"]["done"] == 0


def test_type_inattendu_compte_comme_melange(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history(_entry(TODAY, series_type="valeur-inconnue", win=True))
    counts = daily_counts_by_type(today=TODAY)
    assert counts["mix"]["done"] == 1


def test_lignes_illisibles_et_sans_timestamp_ignorees(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history(_entry(TODAY, series_type="theme", win=True))
    with open(path, "a", encoding="utf-8") as f:
        f.write("pas du json\n")
    append_puzzle_history({"puzzle_id": "sans-date", "win": True, "series_type": "theme"})  # sans timestamp
    counts = daily_counts_by_type(today=TODAY)
    assert counts["theme"] == {"done": 1, "solved": 1, "failed": 0}


# ── Intégration : check_lichess_puzzle_daily_counts ──────────────────────

def test_check_daily_counts_envoie_un_evenement_avec_les_compteurs(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history(_entry(datetime.date.today(), series_type="phase", win=True))
    sent = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent.append((etype, data)))
    check_lichess_puzzle_daily_counts()
    assert len(sent) == 1
    etype, data = sent[0]
    assert etype == "lichess_puzzle_daily_counts"
    assert data["phase"]["done"] == 1


def test_check_daily_counts_jamais_de_reseau_meme_sans_jeton(tmp_path, monkeypatch):
    """Purement local : aucune dépendance à load_config/au jeton (à
    l'inverse de check_lichess_puzzle_dashboard) — doit fonctionner même si
    load_config() explose."""
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", tmp_path / "absent.jsonl")

    def _boom():
        raise AssertionError("load_config ne doit jamais être appelée ici")
    monkeypatch.setattr(lichess_launcher, "load_config", _boom)
    sent = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent.append((etype, data)))
    check_lichess_puzzle_daily_counts()  # ne doit pas lever
    assert len(sent) == 1


# ── _build_puzzle_session : série_type résolu explicitement ─────────────

def test_build_puzzle_session_mode_theme(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_puzzle_series_mode": "theme", "lichess_puzzle_theme": "fork",
    })
    session = _build_puzzle_session()
    assert session.current_series_type == "theme"


def test_build_puzzle_session_mode_phase(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_puzzle_series_mode": "phase", "lichess_puzzle_phase": "endgame",
    })
    session = _build_puzzle_session()
    assert session.current_series_type == "phase"


def test_build_puzzle_session_mode_mix_par_defaut(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {})
    session = _build_puzzle_session()
    assert session.current_series_type == "mix"


def test_build_puzzle_session_mode_invalide_replie_sur_mix(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_puzzle_series_mode": "???"})
    session = _build_puzzle_session()
    assert session.current_series_type == "mix"


def test_puzzle_series_spec_series_type_invalide_replie_sur_mix():
    spec = _PuzzleSeriesSpec(theme="", count=0, series_type="n'importe quoi")
    assert spec.series_type == "mix"


# ── PuzzleGame._record_history écrit le champ "series_type" ─────────────

def test_record_history_ecrit_series_type(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    start = chess.Board()
    puzzle = {
        "puzzle_id": "pzl_type", "rating": 1500, "themes": ["fork"], "solution": ["e2e4"],
        "fen": start.fen(), "setup_fen": start.fen(), "opponent_first_move": None,
        "game_id": "g1", "rated": True, "players": [],
    }
    events = []
    actions = queue.Queue()
    monkeypatch.setattr(puzzle_game_mod, "send_event", lambda e, d: events.append((e, d)))

    def fake_get_action(timeout=0.0):
        try:
            return actions.get(timeout=timeout)
        except queue.Empty:
            return None
    monkeypatch.setattr(puzzle_game_mod, "get_action", fake_get_action)

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": 5, "new_rating": 1505}
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)

    board = _FakeBoard(initial_fen=start.board_fen())
    game = PuzzleGame(board, "lip_x", puzzle, series_theme="fork", series_type="theme")

    after = start.copy()
    after.push_uci("e2e4")

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = after.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome == "solved")
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    game.run()
    driver.join(timeout=1.0)

    entries = puzzle_history_mod.read_puzzle_history_entries()
    assert len(entries) == 1
    assert entries[0]["series_type"] == "theme"


def test_puzzle_game_series_type_invalide_replie_sur_mix():
    start = chess.Board()
    puzzle = {
        "puzzle_id": "x", "rating": 1500, "themes": [], "solution": ["e2e4"],
        "fen": start.fen(), "setup_fen": start.fen(), "opponent_first_move": None,
        "game_id": "g1", "rated": True, "players": [],
    }
    game = PuzzleGame(_FakeBoard(), "tok", puzzle, series_type="n'importe quoi")
    assert game.series_type == "mix"
