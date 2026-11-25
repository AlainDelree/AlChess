"""
nicsoft/tests/test_issue387_lichess_puzzle_history.py — AlChess

Issue #387, point 1 : historique local des problèmes Lichess (un
enregistrement JSON par ligne, par problème TERMINÉ). Entièrement sans
réseau (submit_puzzle_result monkeypatché, comme test_issue354) et sans
matériel (FakeBoard, même contrat que test_issue309_lichess_l2a.py). Le
fichier d'historique est toujours redirigé vers un dossier temporaire
(monkeypatch de puzzle_history.PUZZLE_HISTORY_FILE) — jamais le vrai
dossier de données de l'utilisateur (voir CONSIGNES, règle de test AlChess).
"""

import json
import queue
import threading
import time

import chess
import pytest

import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod
import nicsoft.modes.lichess.puzzle_history as puzzle_history_mod
from nicsoft.modes.lichess.puzzle_game import PuzzleGame
from nicsoft.modes.lichess.puzzle_history import append_puzzle_history


# ── Doubles de test (mêmes contrats que test_issue354_lichess_puzzles_l3.py) ─

class FakeBoard:
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

    def connect(self):
        pass

    def disconnect(self):
        pass


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
    return events, actions


def _puzzle(solution, fen=None, setup_fen=None, puzzle_id="pzl1", rating=1500, themes=None):
    fen = fen or chess.Board().fen()
    return {
        "puzzle_id": puzzle_id,
        "rating": rating,
        "themes": themes or ["fork", "middlegame"],
        "solution": list(solution),
        "fen": fen,
        "setup_fen": setup_fen or fen,
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


def _read_history_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def history_file(tmp_path, monkeypatch):
    path = tmp_path / "lichess_puzzle_history.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    return path


# ── append_puzzle_history (fonction bas niveau) ─────────────────────────────

def test_append_puzzle_history_ecrit_une_ligne_json(history_file):
    append_puzzle_history({"puzzle_id": "a", "win": True})
    lines = _read_history_lines(history_file)
    assert lines == [{"puzzle_id": "a", "win": True}]


def test_append_puzzle_history_ajoute_en_fin_de_fichier(history_file):
    append_puzzle_history({"puzzle_id": "a"})
    append_puzzle_history({"puzzle_id": "b"})
    lines = _read_history_lines(history_file)
    assert [l["puzzle_id"] for l in lines] == ["a", "b"]


def test_append_puzzle_history_cree_le_dossier_parent(tmp_path, monkeypatch):
    path = tmp_path / "sous_dossier_absent" / "lichess_puzzle_history.jsonl"
    monkeypatch.setattr(puzzle_history_mod, "PUZZLE_HISTORY_FILE", path)
    append_puzzle_history({"puzzle_id": "a"})
    assert path.exists()


def test_append_puzzle_history_echec_ecriture_ne_leve_jamais(history_file, monkeypatch, caplog):
    """Disque plein/droits refusés — simulé en faisant échouer mkdir — ne
    doit jamais lever, seulement journaliser (règle AlChess : un problème/
    une partie ne doit jamais s'interrompre pour ça)."""
    import pathlib

    def _boom(*a, **kw):
        raise OSError("disque plein (simulé)")
    monkeypatch.setattr(pathlib.Path, "mkdir", _boom)
    append_puzzle_history({"puzzle_id": "a"})  # ne doit pas lever


def test_append_puzzle_history_jamais_de_jeton(history_file):
    """Garde-fou explicite — même si un futur appelant fautif glissait un
    jeton dans l'entrée, ce test documente l'attente : aucun champ de ce
    nom n'est jamais écrit par le code actuel (voir PuzzleGame._record_history,
    qui ne construit jamais une entrée avec ces clés)."""
    append_puzzle_history({"puzzle_id": "a", "win": True})
    lines = _read_history_lines(history_file)
    for entry in lines:
        assert "token" not in entry
        assert "lichess_token" not in entry


# ── Intégration : PuzzleGame._finish écrit l'historique ─────────────────────

def test_probleme_resolu_ecrit_une_entree_complete(history_file, monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen(), puzzle_id="pzl_resolu", rating=1500,
                      themes=["opening", "fork"])
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": 7, "new_rating": 1507}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle, player_name="Alain")

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

    lines = _read_history_lines(history_file)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["puzzle_id"] == "pzl_resolu"
    assert entry["win"] is True
    assert entry["setup_fen"] == puzzle["setup_fen"]
    assert entry["themes"] == ["opening", "fork"]
    assert entry["series_theme"] == ""
    assert entry["rating_before"] == 1500
    assert entry["rating_after"] == 1507
    assert entry["rating_diff"] == 7
    assert entry["submit_ok"] is True
    assert isinstance(entry["duration_s"], (int, float)) and entry["duration_s"] >= 0
    assert "timestamp" in entry and entry["timestamp"]
    assert "token" not in entry


def test_probleme_rate_ecrit_resultat_faux(history_file, monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen(), puzzle_id="pzl_rate")
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": -8, "new_rating": 1492}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    wrong = start.copy()
    wrong.push_uci("d2d4")

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = wrong.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome == "failed")
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    game.run()
    driver.join(timeout=1.0)

    lines = _read_history_lines(history_file)
    assert len(lines) == 1
    assert lines[0]["win"] is False
    assert lines[0]["submit_ok"] is True


def test_envoi_echoue_consigne_quand_meme_avec_cotes_absentes_et_indicateur_faux(history_file, monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen(), puzzle_id="pzl_reseau")
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "network_error"}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

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

    lines = _read_history_lines(history_file)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["win"] is True
    assert entry["submit_ok"] is False
    assert entry["rating_before"] is None
    assert entry["rating_after"] is None
    assert entry["rating_diff"] is None


def test_reessai_reussi_ne_reecrit_pas_une_seconde_ligne(history_file, monkeypatch):
    """Décision retenue (voir rapport de clôture) : une seule écriture, au
    premier essai d'envoi — un réessai manuel réussi plus tard
    (lichess_puzzle_retry_submit) ne produit jamais de seconde ligne."""
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen(), puzzle_id="pzl_retry")
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    calls = {"n": 0}

    def fake_submit(token, puzzle_id, win, rated=True):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"status": "network_error"}
        return {"status": "ok", "rating_diff": 4, "new_rating": 1504}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    after = start.copy()
    after.push_uci("e2e4")

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = after.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game._submit_error_key is not None)
        actions.put({"type": "lichess_puzzle_retry_submit"})
        assert _wait_until(lambda: game._pending_submit is None)
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    game.run()
    driver.join(timeout=1.0)

    lines = _read_history_lines(history_file)
    assert len(lines) == 1
    assert lines[0]["submit_ok"] is False
    assert lines[0]["rating_diff"] is None


def test_abandon_avant_resultat_ne_consigne_rien(history_file, monkeypatch):
    """Retour au menu pendant un problème EN COURS (aucun résultat connu) —
    aucune ligne d'historique (voir run()/_process_browser_actions : la
    sortie "back_menu" ici ne passe jamais par _finish)."""
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen(), puzzle_id="pzl_abandon")
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        raise AssertionError("submit_puzzle_result ne doit jamais être appelé ici")

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=1.0)

    assert outcome == "back_menu"
    assert game.outcome is None
    assert _read_history_lines(history_file) == []


def test_series_theme_transmis_au_constructeur_est_reporte(history_file, monkeypatch):
    """Vide par défaut aujourd'hui (aucun choix de thème, voir le rapport de
    clôture) mais déjà transmissible — préparation du point 2 (séance =
    liste de séries, chacune avec son thème)."""
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen(), puzzle_id="pzl_theme")
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": 1, "new_rating": 1501}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle, series_theme="middlegame")

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

    lines = _read_history_lines(history_file)
    assert lines[0]["series_theme"] == "middlegame"
