"""
nicsoft/tests/test_issue354_lichess_puzzles_l3.py — AlChess

Issue #354 (Lichess L3, suite) : déroulement complet d'un problème Lichess
sur l'échiquier physique — étapes A (entrée/mise en place), B (coups,
promotion, coup faux, mat alternatif), C (enchaînement, journal,
robustesse). Entièrement sans réseau (submit_puzzle_result/get_next_puzzle
et test_token monkeypatchés) et sans matériel (faux plateau, comme
test_issue309_lichess_l2a.py::FakeBoard).
"""

import queue
import threading
import time

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod
from nicsoft.modes.lichess.puzzle_game import (
    PuzzleGame,
    first_move_squares,
    solver_color_for_fen,
)
from nicsoft.web import single_instance


# ── Doubles de test ──────────────────────────────────────────────────────────

class FakeBoard:
    """Double léger du plateau physique — même contrat que
    test_issue309_lichess_l2a.py::FakeBoard."""

    def __init__(self, initial_fen=chess.STARTING_BOARD_FEN):
        self.current_fen = initial_fen + " w - - 0 1"
        self.led_calls = []
        self.leds_off_count = 0
        self.beep_count = 0
        self.connect_count = 0

    def get_fen(self):
        return self.current_fen

    def set_led(self, square, status):
        self.led_calls.append((square, status))

    def turn_off_all_leds(self):
        self.leds_off_count += 1

    def signal_lights(self, sig):
        pass

    def beep(self):
        self.beep_count += 1

    def connect(self):
        self.connect_count += 1

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


def _events_of(events, etype):
    return [d for t, d in events if t == etype]


def _puzzle(solution, fen=None, setup_fen=None, opponent_first_move=None,
            puzzle_id="pzl1", rating=1500, themes=None):
    fen = fen or chess.Board().fen()
    return {
        "puzzle_id": puzzle_id,
        "rating": rating,
        "themes": themes or ["fork", "middlegame"],
        "solution": list(solution),
        "fen": fen,
        "setup_fen": setup_fen or fen,
        "opponent_first_move": opponent_first_move,
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


# ── Fonctions pures ──────────────────────────────────────────────────────────

def test_solver_color_for_fen_blancs():
    fen = chess.Board().fen()  # trait aux blancs
    assert solver_color_for_fen(fen) == "white"


def test_solver_color_for_fen_noirs():
    board = chess.Board()
    board.push_uci("e2e4")
    assert solver_color_for_fen(board.fen()) == "black"


def test_first_move_squares_absent():
    assert first_move_squares(chess.Board().fen(), None) is None


def test_first_move_squares_present():
    setup_fen = chess.Board().fen()
    sq = first_move_squares(setup_fen, "e2e4")
    assert sq == (chess.E2, chess.E4)


def test_first_move_squares_illisible_ne_leve_pas():
    assert first_move_squares(chess.Board().fen(), "z9z9") is None


# ── Étape A : mise en place et premier coup adverse ─────────────────────────

def test_animate_opponent_first_move_attend_la_replication_physique(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    setup_board = chess.Board()
    puzzle = _puzzle(
        solution=["d8h4"], fen=None, setup_fen=setup_board.fen(), opponent_first_move="g2g4",
    )
    # fen "réel" du problème = position après g2g4 (coup adverse initial).
    after = chess.Board()
    after.push_uci("g2g4")
    puzzle["fen"] = after.fen()
    board = FakeBoard()
    game = PuzzleGame(board, "lip_x", puzzle, player_name="Alain")

    def _drive():
        assert _wait_until(lambda: len(board.led_calls) > 0)
        board.current_fen = after.board_fen() + " w - - 0 1"

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    game.animate_opponent_first_move()
    driver.join(timeout=1.0)

    assert board.beep_count == 1
    moves = _events_of(events, "lichess_puzzle_move")
    assert moves and moves[0]["uci"] == "g2g4"


def test_animate_opponent_first_move_noop_si_absent(monkeypatch):
    events, _actions = _make_recorder(monkeypatch)
    puzzle = _puzzle(solution=["d8h4"])
    board = FakeBoard()
    game = PuzzleGame(board, "lip_x", puzzle)
    game.animate_opponent_first_move()
    assert board.beep_count == 0
    assert _events_of(events, "lichess_puzzle_move") == []


# ── Étape B : coups, promotion, coup faux, mat alternatif ───────────────────

def test_coup_correct_puis_reponse_adverse_forcee_puis_victoire(monkeypatch):
    """Mat du berger (côté noir, pour varier des tests existants) : 1.e4 e5
    2.Qh5 ... — scénario simplifié à 2 coups utilisateur + 1 réponse forcée
    avant le mat, pour vérifier l'alternance correct/réponse adverse/
    victoire et l'envoi du résultat classé avec cote avant/après."""
    start = chess.Board()
    start.push_uci("e2e4")
    start.push_uci("e7e5")
    start.push_uci("f1c4")
    # À ce point trait aux noirs : solution = [Nc6 (solveur), Qh5 (forcé,
    # adverse), Nf6?? (solveur, erreur volontaire ici absente — on construit
    # un mat réel) ... simplifié : solveur joue Nc6 puis un second coup qui
    # mate après la réponse forcée Qh5-like. Pour un test déterministe, on
    # construit directement une solution à 3 demi-coups se terminant en mat.
    board_after_solver1 = start.copy()
    board_after_solver1.push_uci("b8c6")
    board_after_opponent = board_after_solver1.copy()
    board_after_opponent.push_uci("d1h5")  # réponse adverse forcée (dame)
    # Coup final du solveur : pas nécessairement un mat réel ici (le test de
    # mat alternatif est couvert séparément) — on vise juste la fin normale
    # de solution (solved_index atteint sa longueur).
    board_final = board_after_opponent.copy()
    board_final.push_uci("g8f6")

    puzzle = _puzzle(
        solution=["b8c6", "d1h5", "g8f6"],
        fen=start.fen(),
    )
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        assert win is True
        assert rated is True
        return {"status": "ok", "rating_diff": 7, "new_rating": 1507}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)

    game = PuzzleGame(board, "lip_x", puzzle, player_name="Alain")

    def _drive():
        # 1) L'utilisateur joue physiquement le coup du solveur attendu.
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = board_after_solver1.board_fen() + " w - - 0 1"
        # 2) Le jeu applique aussitôt la réponse adverse forcée à sa propre
        #    logique (self.board) et attend sa réplication physique.
        assert _wait_until(lambda: game.board.board_fen() == board_after_opponent.board_fen())
        board.current_fen = board_after_opponent.board_fen() + " w - - 0 1"
        # Attendre que le jeu ait bien observé cette réplication (évènement
        # "lichess_puzzle_position_ok") avant d'écraser current_fen avec le
        # coup suivant — sinon la boucle de _wait_for_board_fen pourrait ne
        # jamais lire board_after_opponent (course bénigne, propre au double
        # de test — voir le même commentaire dans test_issue309_lichess_l2a.py).
        assert _wait_until(lambda: _events_of(events, "lichess_puzzle_position_ok"))
        # 3) L'utilisateur joue le dernier coup du solveur — plus de coup
        #    attendu ensuite : le problème est résolu.
        board.current_fen = board_final.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome == "solved")
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=1.0)

    assert outcome == "back_menu"
    assert game.outcome == "solved"
    # Vérifie l'alternance : coup du solveur (b8c6), réponse adverse forcée
    # (d1h5) rejouée automatiquement, puis dernier coup du solveur (g8f6) —
    # trois évènements lichess_puzzle_move, dans cet ordre.
    moves = _events_of(events, "lichess_puzzle_move")
    assert [m["uci"] for m in moves] == ["b8c6", "d1h5", "g8f6"]
    assert moves[1]["color"] != moves[0]["color"]


def test_resolution_complete_envoie_resultat_classe_et_cote_avant_apres(monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    submitted = {}

    def fake_submit(token, puzzle_id, win, rated=True):
        submitted["args"] = (token, puzzle_id, win, rated)
        return {"status": "ok", "rating_diff": -5, "new_rating": 1495}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle, player_name="Alain")

    after = start.copy()
    after.push_uci("e2e4")

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = after.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome == "solved")
        actions.put({"type": "lichess_puzzle_next"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=1.0)

    assert outcome == "next_puzzle"
    assert submitted["args"] == ("lip_x", "pzl1", True, True)
    assert game.rating_after == 1495
    assert game.rating_before == 1500  # 1495 - (-5)
    assert game.rating_diff == -5
    results = _events_of(events, "lichess_puzzle_result")
    assert results and results[-1]["win"] is True
    assert results[-1]["rating_before"] == 1500
    assert results[-1]["rating_after"] == 1495


def test_coup_legal_mais_faux_echoue_le_probleme(monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        assert win is False
        return {"status": "ok", "rating_diff": -8, "new_rating": 1492}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    wrong = start.copy()
    wrong.push_uci("d2d4")  # légal, mais pas la solution

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = wrong.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome == "failed")
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=1.0)

    assert outcome == "back_menu"
    assert game.outcome == "failed"
    assert game._fail_point_fen == start.fen()
    assert game._fail_remaining == ["e2e4"]


def test_coup_qui_mate_accepte_meme_hors_solution(monkeypatch):
    """Décision retenue (voir docstring de puzzle_game.py) : un coup qui
    met échec et mat est toujours gagnant, même s'il diffère du coup de
    solution attendu — reproduit du comportement public de lila."""
    fen = "6pk/6p1/8/8/8/8/5Q2/7K w - - 0 1"
    start = chess.Board(fen)
    # Deux coups de mat existent (f2h4 et f2h2) — la solution déclare l'un,
    # l'utilisateur joue physiquement l'AUTRE.
    puzzle = _puzzle(solution=["f2h4"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        assert win is True
        return {"status": "ok", "rating_diff": 6, "new_rating": 1506}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    actual_mate = start.copy()
    actual_mate.push_uci("f2h2")

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = actual_mate.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome is not None)
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    game.run()
    driver.join(timeout=1.0)

    assert game.outcome == "solved"


def test_promotion_demande_puis_choix_applique(monkeypatch):
    fen = "8/P7/8/8/8/8/k6K/8 w - - 0 1"  # pion blanc en a7, promotion imminente
    start = chess.Board(fen)
    puzzle = _puzzle(solution=["a7a8q"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": 1, "new_rating": 1501}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    # Position physique : pion disparu de a7, une pièce quelconque posée en
    # a8 (le plateau ne distingue pas laquelle — d'où la question à l'écran).
    promo_board_fen = "Q7/8/8/8/8/8/k6K/8"

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = promo_board_fen + " w - - 0 1"
        assert _wait_until(lambda: _events_of(events, "lichess_puzzle_promotion_needed"))
        actions.put({"type": "lichess_puzzle_promotion_choice", "piece": "q"})
        assert _wait_until(lambda: game.outcome is not None)
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    game.run()
    driver.join(timeout=1.0)

    assert game.outcome == "solved"
    promo_events = _events_of(events, "lichess_puzzle_promotion_needed")
    assert promo_events and promo_events[0]["from"] == "a7" and promo_events[0]["to"] == "a8"


def test_position_illegale_detectee_apres_lectures_stables(monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())
    game = PuzzleGame(board, "lip_x", puzzle)

    # Position qui ne correspond à aucun coup légal depuis le départ.
    illegal_fen = "rnbqkbnr/pppppppp/8/8/8/8/8/RNBQKBNR"
    board.current_fen = illegal_fen + " w - - 0 1"

    for _ in range(puzzle_game_mod.ILLEGAL_STABLE_READS_REQUIRED + 2):
        game._tick_physical()

    active = _events_of(events, "lichess_puzzle_illegal_position")
    assert any(e.get("active") for e in active)


def test_illegal_disparait_quand_position_redevient_correcte(monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())
    game = PuzzleGame(board, "lip_x", puzzle)
    board.current_fen = "rnbqkbnr/pppppppp/8/8/8/8/8/RNBQKBNR w - - 0 1"
    for _ in range(puzzle_game_mod.ILLEGAL_STABLE_READS_REQUIRED + 1):
        game._tick_physical()
    assert game._illegal_position_active is True
    board.current_fen = start.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert game._illegal_position_active is False
    inactive = [e for e in _events_of(events, "lichess_puzzle_illegal_position") if e.get("active") is False]
    assert inactive


# ── Étape C : retour au menu, voir la solution, robustesse réseau ──────────

def test_retour_menu_pendant_attente_ne_soumet_jamais_de_resultat(monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(*a, **k):
        raise AssertionError("submit_puzzle_result ne doit jamais être appelé ici")

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested)
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=1.0)

    assert outcome == "back_menu"
    assert game.outcome is None


def test_voir_la_solution_rejoue_les_coups_restants(monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
    events, actions = _make_recorder(monkeypatch)
    board = FakeBoard(initial_fen=start.board_fen())

    def fake_submit(token, puzzle_id, win, rated=True):
        return {"status": "ok", "rating_diff": -3, "new_rating": 1497}

    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", fake_submit)
    game = PuzzleGame(board, "lip_x", puzzle)

    wrong = start.copy()
    wrong.push_uci("d2d4")
    correct = start.copy()
    correct.push_uci("e2e4")

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = wrong.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome == "failed")
        actions.put({"type": "lichess_puzzle_view_solution"})
        # La démonstration attend la remise en place de la position de
        # départ (avant le coup faux), puis la réplication du coup e2e4 —
        # l'échiquier double est déjà en attente de "start" (aucune course
        # possible : _wait_for_board_fen relit en continu, pas sur évènement).
        board.current_fen = start.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: board.beep_count >= 1, timeout=2.0)
        board.current_fen = correct.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game._solution_shown)
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=2.0)

    assert outcome == "back_menu"
    assert game._solution_shown is True
    solution_moves = _events_of(events, "lichess_puzzle_solution_move")
    assert solution_moves and solution_moves[-1]["uci"] == "e2e4"
    assert solution_moves[-1]["done"] is True


def test_reessai_envoi_apres_echec_reseau(monkeypatch):
    start = chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
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

    correct = start.copy()
    correct.push_uci("e2e4")

    def _drive():
        assert _wait_until(lambda: not game.back_menu_requested and game.outcome is None)
        board.current_fen = correct.board_fen() + " w - - 0 1"
        assert _wait_until(lambda: game.outcome == "solved")
        # Premier essai en échec — le résultat doit rester en attente.
        assert _wait_until(lambda: game._submit_error_key is not None)
        actions.put({"type": "lichess_puzzle_retry_submit"})
        assert _wait_until(lambda: game._pending_submit is None)
        actions.put({"type": "lichess_puzzle_next"})

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    outcome = game.run()
    driver.join(timeout=1.0)

    assert outcome == "next_puzzle"
    assert calls["n"] == 2
    assert game.rating_after == 1504
    results = _events_of(events, "lichess_puzzle_result")
    assert any(r.get("submit_pending") for r in results)
    assert results[-1]["submit_pending"] is False


# ── Lanceur — droits du jeton, verrous (étape A) ────────────────────────────

def test_launch_lichess_puzzle_refuse_sans_jeton(monkeypatch):
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {})
    lichess_launcher.web_server._app_state = "config_lichess"
    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"

    assert sent_states
    state, data = sent_states[-1]
    assert state == "menu"
    assert data["toast_message_key"] == "toast.lichess_no_token"


def test_launch_lichess_puzzle_message_clair_si_droit_manquant(monkeypatch):
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token_12345"})
    lichess_launcher.web_server._app_state = "config_lichess"

    import nicsoft.modes.lichess.client as lichess_client

    def fake_test_token(token):
        return {
            "status": "ok", "account": "alain", "scopes": ["puzzle:read"],
            "has_board_play": True, "has_puzzle_read": True, "has_puzzle_write": False,
        }

    monkeypatch.setattr(lichess_client, "test_token", fake_test_token)

    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"

    assert sent_states
    state, data = sent_states[-1]
    assert state == "config_lichess"
    assert data["toast_message_key"] == "toast.lichess_puzzle_missing_scope"
    assert data["toast_vars"] == {"scopes": "puzzle:write"}
    assert data["toast_persistent"] is True


def test_launch_lichess_puzzle_refuse_si_mode_deja_actif(monkeypatch):
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data=None: events.append((etype, data)))
    lichess_launcher.web_server._app_state = "playing"
    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"
    assert any(etype == "lichess_toast" for etype, _ in events)


def test_lichess_puzzle_playing_dans_busy_states():
    assert "lichess_puzzle_playing" in single_instance.BUSY_STATES
