"""
nicsoft/tests/test_issue388_lichess_puzzle_series_display.py — AlChess

Issue #388, point 3 : l'angle réellement demandé (thème ou phase) est
inscrit dans le bilan de séance (`_PuzzleSessionTracker.summary_payload()`,
game_manager_modes/lichess.py) — déjà inscrit dans l'historique local
depuis #387 (series_theme, voir test_issue387_lichess_puzzle_history.py).
Aucun réseau, aucun échiquier."""

from nicsoft.core.game_manager_modes.lichess import _PuzzleSeriesSpec, _PuzzleSessionTracker


class _FakeGame:
    def __init__(self, outcome="solved", puzzle_id="pzl1", rating=1500, duration_s=1.0, rating_diff=None):
        self.outcome = outcome
        self.puzzle_id = puzzle_id
        self.rating = rating
        self.duration_s = duration_s
        self.rating_diff = rating_diff


def test_summary_payload_porte_l_angle_mix_par_defaut():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="", count=3)])
    tracker.record(_FakeGame())
    assert tracker.summary_payload()["series_angle"] == ""


def test_summary_payload_porte_le_theme_choisi():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="fork", count=3)])
    tracker.record(_FakeGame())
    assert tracker.summary_payload()["series_angle"] == "fork"


def test_summary_payload_porte_la_phase_choisie():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="middlegame", count=3)])
    tracker.record(_FakeGame())
    assert tracker.summary_payload()["series_angle"] == "middlegame"


def test_summary_payload_angle_present_meme_sans_aucun_probleme_termine():
    tracker = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="endgame", count=5)])
    assert tracker.summary_payload()["series_angle"] == "endgame"
