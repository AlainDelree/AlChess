"""
nicsoft/tests/test_issue390_puzzle_player_rating.py — AlChess

Issue #390, point 1 : cote du joueur affichée dans le panneau de problème
dès le début de la séance, mise à jour après chaque résultat.

Entièrement sans réseau (GameClient monkeypatché) et sans matériel —
l'historique local est toujours redirigé vers un dossier temporaire
(monkeypatch de puzzle_history.PUZZLE_HISTORY_FILE), jamais le vrai
dossier de données de l'utilisateur (voir CONSIGNES, règle de test
AlChess)."""

import queue
import time

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_history as puzzle_history_mod
from nicsoft.core.game_manager_modes.lichess import (
    _PuzzleSeriesSpec,
    _PuzzleSessionTracker,
    _init_puzzle_session_rating,
)
from nicsoft.modes.lichess.puzzle_history import append_puzzle_history, last_known_puzzle_rating


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _FakeGame:
    def __init__(self, outcome, rating_after=None):
        self.outcome = outcome
        self.puzzle_id = "pzl1"
        self.rating = 1500
        self.duration_s = 1.0
        self.rating_diff = None
        self.rating_after = rating_after


# ── puzzle_history.last_known_puzzle_rating ──────────────────────────────

def test_last_known_puzzle_rating_fichier_absent_renvoie_none(tmp_path, monkeypatch):
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", tmp_path / "absent.jsonl")
    assert last_known_puzzle_rating() is None


def test_last_known_puzzle_rating_fichier_vide_renvoie_none(tmp_path, monkeypatch):
    path = tmp_path / "vide.jsonl"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    assert last_known_puzzle_rating() is None


def test_last_known_puzzle_rating_lignes_illisibles_ignorees(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history({"puzzle_id": "a", "rating_after": 1500})
    with open(path, "a", encoding="utf-8") as f:
        f.write("ceci n'est pas du JSON\n")
        f.write("[1, 2, 3]\n")  # JSON valide mais pas un objet
    append_puzzle_history({"puzzle_id": "b", "rating_after": 1520})
    assert last_known_puzzle_rating() == 1520


def test_last_known_puzzle_rating_remonte_en_arriere_jusqu_a_une_valeur_connue(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history({"puzzle_id": "a", "rating_after": 1500})
    append_puzzle_history({"puzzle_id": "b", "rating_after": None})  # envoi échoué
    assert last_known_puzzle_rating() == 1500


# ── _PuzzleSessionTracker.record : mise à jour de player_rating ─────────

def test_record_met_a_jour_player_rating_si_connue():
    session = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="", count=0)])
    assert session.player_rating is None
    session.record(_FakeGame("solved", rating_after=1507))
    assert session.player_rating == 1507
    session.record(_FakeGame("failed", rating_after=None))
    assert session.player_rating == 1507  # inchangé — pas de valeur devinée
    session.record(_FakeGame("solved", rating_after=1499))
    assert session.player_rating == 1499


# ── _init_puzzle_session_rating ──────────────────────────────────────────

def test_init_session_rating_utilise_l_historique_local_immediatement(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history({"puzzle_id": "a", "rating_after": 1480})
    session = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="", count=0)])
    _init_puzzle_session_rating(session, token="", username="")
    assert session.player_rating == 1480


def test_init_session_rating_sans_token_ni_compte_ne_lance_aucun_fil(tmp_path, monkeypatch):
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", tmp_path / "absent.jsonl")
    session = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="", count=0)])
    _init_puzzle_session_rating(session, token="", username="")
    assert session.player_rating is None


def test_init_session_rating_met_a_jour_en_arriere_plan_sans_bloquer(tmp_path, monkeypatch):
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", tmp_path / "absent.jsonl")
    events = queue.Queue()
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: events.put((etype, data)))

    class _FakeGameClient:
        def __init__(self, token):
            self.token = token

        def fetch_my_rating(self, username, speed_key):
            assert username == "alain_id"
            assert speed_key == "puzzle"
            return 1620

    monkeypatch.setattr(lichess_launcher, "GameClient", _FakeGameClient)
    session = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="", count=0)])
    _init_puzzle_session_rating(session, token="lip_x", username="alain_id")
    # Jamais bloquant : la valeur locale (absente ici) est déjà en place en
    # sortie, la mise à jour réseau arrive ensuite dans un fil séparé.
    assert _wait_until(lambda: session.player_rating == 1620)
    etype, data = events.get(timeout=1.0)
    assert etype == "lichess_puzzle_player_rating"
    assert data == {"rating": 1620}


def test_init_session_rating_valeur_introuvable_ne_change_rien(tmp_path, monkeypatch):
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", tmp_path / "absent.jsonl")
    sent = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent.append((etype, data)))

    class _FakeGameClient:
        def __init__(self, token):
            pass

        def fetch_my_rating(self, username, speed_key):
            return None

    monkeypatch.setattr(lichess_launcher, "GameClient", _FakeGameClient)
    session = _PuzzleSessionTracker([_PuzzleSeriesSpec(theme="", count=0)])
    _init_puzzle_session_rating(session, token="lip_x", username="alain_id")
    time.sleep(0.3)
    assert session.player_rating is None
    assert sent == []
