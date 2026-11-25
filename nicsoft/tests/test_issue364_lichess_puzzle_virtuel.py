"""
nicsoft/tests/test_issue364_lichess_puzzle_virtuel.py — AlChess

Issue #364, partie 1 : mode virtuel (jouer à l'écran, sans échiquier
physique) des problèmes Lichess — VirtualPuzzleGame (modes/lichess/
puzzle_game.py) et son lanceur (_run_lichess_puzzle_virtual,
core/game_manager_modes/lichess.py). Même esprit que
test_issue354_lichess_puzzles_l3.py (faux client Lichess, jamais de
réseau/matériel réel) mais sans aucun double de plateau physique : les
coups du joueur sont injectés directement comme le ferait le navigateur
(action "lichess_puzzle_virtual_move"), jamais par polling d'un FEN
matériel — ce mode n'en a aucun besoin (nl_inst=None partout ici)."""

import queue
import threading
import time

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod
from nicsoft.modes.lichess.puzzle_game import VirtualPuzzleGame, _legal_moves_map


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


@pytest.fixture(autouse=True)
def _fast_virtual_pause(monkeypatch):
    """Les pauses du mode virtuel (_wait_for_board_fen surchargée) n'ont
    aucune raison de ralentir les tests — raccourcies ici, jamais côté
    produit (valeurs réelles inchangées, voir puzzle_game.py)."""
    monkeypatch.setattr(puzzle_game_mod, "_VIRTUAL_PAUSE_S", 0.03)
    monkeypatch.setattr(puzzle_game_mod, "_VIRTUAL_PAUSE_STEP_S", 0.01)


# ── Coups légaux fournis par le serveur (jamais un moteur) ──────────────────

def test_legal_moves_map_regroupe_par_case_de_depart():
    board = chess.Board()
    moves = _legal_moves_map(board)
    assert sorted(moves["e2"]) == ["e3", "e4"]
    assert "a8" not in moves  # case noire, pas de coup légal depuis là


def test_legal_moves_map_fusionne_les_quatre_promotions():
    board = chess.Board("8/P7/8/8/8/8/k6K/8 w - - 0 1")
    moves = _legal_moves_map(board)
    assert moves["a7"] == ["a8"]  # une seule destination, pas 4 (q/r/b/n)


# ── Démarrage, coup adverse initial et annonce "à vous de jouer" ───────────

def test_animate_premier_coup_puis_your_turn_avec_coups_legaux(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(["e2e4"])
    game = VirtualPuzzleGame(None, "lip_x", puzzle, player_name="Alain")

    game.animate_opponent_first_move()

    assert _events_of(events, "lichess_puzzle_move") == []  # pas de coup adverse ici
    turns = _events_of(events, "lichess_puzzle_your_turn")
    assert len(turns) == 1
    assert sorted(turns[0]["legal_moves"]["e2"]) == ["e3", "e4"]


# ── Coup illégal refusé sans pénalité, puis bon coup ────────────────────────

def test_coup_virtuel_illegal_refuse_sans_penalite_puis_coup_correct(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(["e2e4"])

    def fake_submit(token, puzzle_id, win, rated=True):
        assert win is True
        return {"status": "ok", "rating_diff": 5, "new_rating": 1505}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    game._handle_virtual_move({"from": "e2", "to": "e5"})  # illégal (pas de capture)
    assert game.outcome is None
    illegal = _events_of(events, "lichess_puzzle_virtual_illegal")
    assert illegal and illegal[0] == {"from": "e2", "to": "e5"}
    assert _events_of(events, "lichess_puzzle_result") == []

    game._handle_virtual_move({"from": "e2", "to": "e4"})  # bon coup — réessai sans pénalité
    assert game.outcome == "solved"
    results = _events_of(events, "lichess_puzzle_result")
    assert results and results[-1]["win"] is True


def test_coup_virtuel_mal_forme_refuse(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(["e2e4"])
    game = VirtualPuzzleGame(None, "lip_x", puzzle)
    game._handle_virtual_move({"from": "", "to": "z9"})
    assert game.outcome is None
    assert _events_of(events, "lichess_puzzle_virtual_illegal")


# ── Coup légal mais faux : problème raté ────────────────────────────────────

def test_coup_virtuel_legal_mais_faux_echoue_le_probleme(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(["e2e4"])

    def fake_submit(token, puzzle_id, win, rated=True):
        assert win is False
        return {"status": "ok", "rating_diff": -8, "new_rating": 1492}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    game._handle_virtual_move({"from": "d2", "to": "d4"})  # légal, pas la solution
    assert game.outcome == "failed"
    assert game._fail_point_fen == chess.Board().fen()
    assert game._fail_remaining == ["e2e4"]
    results = _events_of(events, "lichess_puzzle_result")
    assert results[-1]["win"] is False
    assert results[-1]["can_view_solution"] is True


# ── Mat accepté même hors solution ──────────────────────────────────────────

def test_coup_virtuel_qui_mate_accepte_meme_hors_solution(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    fen = "6pk/6p1/8/8/8/8/5Q2/7K w - - 0 1"
    puzzle = _puzzle(["f2h4"], fen=fen)

    def fake_submit(token, puzzle_id, win, rated=True):
        assert win is True
        return {"status": "ok", "rating_diff": 6, "new_rating": 1506}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    game._handle_virtual_move({"from": "f2", "to": "h2"})  # mat réel, différent de la solution
    assert game.outcome == "solved"
    results = _events_of(events, "lichess_puzzle_result")
    assert results[-1]["win"] is True


# ── Promotion (pièce déjà choisie côté navigateur) ──────────────────────────

def test_coup_virtuel_promotion(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    fen = "8/P7/8/8/8/8/k6K/8 w - - 0 1"
    puzzle = _puzzle(["a7a8q"], fen=fen)

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": 1, "new_rating": 1501}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    game._handle_virtual_move({"from": "a7", "to": "a8", "promotion": "q"})
    assert game.outcome == "solved"
    moves = _events_of(events, "lichess_puzzle_move")
    assert moves and moves[0]["uci"] == "a7a8q"


def test_coup_virtuel_promotion_piece_invalide_repliee_sur_dame(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    fen = "8/P7/8/8/8/8/k6K/8 w - - 0 1"
    puzzle = _puzzle(["a7a8q"], fen=fen)
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **k: {"status": "ok"})
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    # Pièce de promotion absente/invalide dans l'action : refusé comme un
    # coup illégal (une dame existe réellement en a8 pour a7a8, mais pas un
    # roi ni l'absence de pièce — "a7a8" seul n'est pas un coup légal, un
    # pion ne peut pas atteindre la dernière rangée sans se promouvoir).
    game._handle_virtual_move({"from": "a7", "to": "a8", "promotion": "k"})
    assert game.outcome is None
    assert _events_of(events, "lichess_puzzle_virtual_illegal")


# ── Résultat envoyé une seule fois (résolu, puis "Problème suivant") ───────

def test_resultat_envoye_une_seule_fois(monkeypatch):
    events, actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(["e2e4"])
    calls = {"n": 0}

    def fake_submit(token, puzzle_id, win, rated=True):
        calls["n"] += 1
        return {"status": "ok", "rating_diff": 4, "new_rating": 1504}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    game._handle_virtual_move({"from": "e2", "to": "e4"})
    assert game.outcome == "solved"
    assert calls["n"] == 1

    actions.put({"type": "lichess_puzzle_next"})
    outcome = game._wait_post_result_decision()
    assert outcome == "next_puzzle"
    assert calls["n"] == 1  # jamais un second envoi


# ── Voir la solution — rejeu automatique, pas d'attente physique ──────────

def test_voir_la_solution_rejoue_sans_attente_physique(monkeypatch):
    events, actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(["e2e4"])
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **k: {"status": "ok"})
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    game._handle_virtual_move({"from": "d2", "to": "d4"})  # faux
    assert game.outcome == "failed"

    def _solution_terminee():
        return any(
            d.get("can_view_solution") is False
            for d in _events_of(events, "lichess_puzzle_result")
        )

    def _drive():
        actions.put({"type": "lichess_puzzle_view_solution"})
        # Attend la fin RÉELLE du rejeu (second "lichess_puzzle_result", avec
        # can_view_solution retombé à False) avant d'envoyer back_menu —
        # jamais _solution_shown seul, mis à True AVANT le rejeu (voir
        # _wait_post_result_decision, inchangé), ce qui enverrait back_menu
        # trop tôt et interromprait le rejeu avant son terme.
        assert _wait_until(_solution_terminee, timeout=2.0)
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=2.0)

    assert outcome == "back_menu"
    assert game._solution_shown is True
    moves = _events_of(events, "lichess_puzzle_move")
    # Le premier évènement rejoue la position d'avant le coup faux (uci absent).
    assert moves and "uci" not in moves[0]
    solution_moves = _events_of(events, "lichess_puzzle_solution_move")
    assert solution_moves and solution_moves[-1]["uci"] == "e2e4"
    assert solution_moves[-1]["done"] is True


def test_retour_menu_pendant_voir_la_solution(monkeypatch):
    """Le retour au menu doit interrompre la pause de rejeu immédiatement,
    sans thread supplémentaire resté actif (tout se passe dans l'appel
    synchrone ci-dessous, un seul fil — celui du test) : back_menu est déjà
    dans la file avant même le premier coup de la solution, donc la toute
    première pause (_on_solution_rewind -> _wait_for_board_fen) l'intercepte."""
    events, actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(["e2e4", "e7e5", "d1h5"])  # solution à 3 coups, assez longue pour interrompre
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **k: {"status": "ok"})
    game = VirtualPuzzleGame(None, "lip_x", puzzle)

    game._handle_virtual_move({"from": "d2", "to": "d4"})  # faux dès le premier coup
    assert game.outcome == "failed"

    actions.put({"type": "lichess_puzzle_view_solution"})
    actions.put({"type": "back_menu"})
    outcome = game.run()
    assert outcome == "back_menu"


# ── Lanceur : le mode virtuel ne requiert jamais d'échiquier physique ──────

def test_launch_lichess_puzzle_virtuel_ne_requiert_aucun_echiquier(monkeypatch):
    events, actions = _make_recorder(monkeypatch)
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token"})
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)

    import nicsoft.modes.lichess.client as lichess_client

    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "account": "alain", "scopes": ["puzzle:read", "puzzle:write"],
        "has_puzzle_read": True, "has_puzzle_write": True,
    })

    def _boom(*a, **k):
        raise AssertionError("le mode virtuel ne doit jamais ouvrir l'échiquier physique")

    monkeypatch.setattr(lichess_launcher, "_open_board_with_retry", _boom)

    puzzle = _puzzle(["e2e4"])

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {"status": "ok", **puzzle})

    class _FakeGameLog:
        def __init__(self, *a, **k):
            pass

        def state_change(self, *a, **k):
            pass

        def exception(self, *a, **k):
            pass

        def close(self):
            pass

    import nicsoft.modes.lichess.game_log as game_log_mod
    monkeypatch.setattr(game_log_mod, "GameLog", _FakeGameLog)

    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain", "puzzle_mode": "virtual"})
    finally:
        driver.join(timeout=2.0)
        final_state = lichess_launcher.web_server._app_state
        lichess_launcher.web_server._app_state = "menu"

    # L'état final est "menu" (fixé directement par _run_lichess_puzzle_virtual
    # dans son `finally`, sans repasser par set_app_state — même mécanisme que
    # _run_lichess_puzzle en mode échiquier, voir lichess.py) : sent_states ne
    # contient donc jamais un second ("menu", ...) après "lichess_puzzle_playing".
    assert final_state == "menu"
    assert _events_of(events, "lichess_puzzle_your_turn")


def test_launch_lichess_puzzle_mode_echiquier_par_defaut_sans_puzzle_mode(monkeypatch):
    """Sans `puzzle_mode` dans la config (ancien appel JS, avant l'issue
    #364), le lanceur choisit toujours _run_lichess_puzzle (échiquier) —
    jamais le mode virtuel par surprise."""
    called = {"target": None}

    def fake_run_board(token, player_name, _error=None):
        called["target"] = "board"

    def fake_run_virtual(token, player_name, _error=None):
        called["target"] = "virtual"

    monkeypatch.setattr(lichess_launcher, "_run_lichess_puzzle", fake_run_board)
    monkeypatch.setattr(lichess_launcher, "_run_lichess_puzzle_virtual", fake_run_virtual)
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: None)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token"})
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)

    import nicsoft.modes.lichess.client as lichess_client
    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "has_puzzle_read": True, "has_puzzle_write": True,
    })

    lichess_launcher.web_server._app_state = "config_lichess"
    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"

    assert called["target"] == "board"
