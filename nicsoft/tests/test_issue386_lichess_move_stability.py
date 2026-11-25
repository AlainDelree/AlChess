"""
nicsoft/tests/test_issue386_lichess_move_stability.py — AlChess

Issue #386 (suite de l'étude #381) : un coup glissé sans lever la pièce sur
l'échiquier physique — ex. e2-e4 glissé — était jusqu'ici reconnu et envoyé
à Lichess dès la PREMIÈRE lecture légale, qui peut être celle d'une case
intermédiaire (e2-e3) plutôt que la case finale réellement visée. Les modes
pédagogique/humain/exercices exigent déjà une position stable pendant
driver.py::NicLinkManager.STABLE_DELAY (0.35s) avant de valider un coup —
ce fichier vérifie que la partie Lichess (LichessGame._check_user_move) ET
les problèmes Lichess (PuzzleGame._tick_physical) exigent désormais la même
durée de stabilité (MOVE_STABLE_DELAY_S, nicsoft/modes/lichess/game.py)
avant tout premier envoi d'un coup physique détecté — sans toucher à
driver.py, au mécanisme de renvoi réseau (#368/#377) ni à la stabilité par
nombre de lectures (8) déjà en place pour les positions illégales.

Horloge entièrement simulée (time.monotonic monkeypatché par une horloge
contrôlable) — aucun des tests ci-dessous ne dépend d'un vrai délai, pour
rester rapides et déterministes même répétés en boucle.

Entièrement sans réseau (FakeTransport/GameClient, voir test_issue309) et
sans matériel (FakeBoard, voir test_issue309 pour la partie et
test_issue354 pour les problèmes).
"""
import time

import chess

import nicsoft.modes.lichess.game as game_mod
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod
from nicsoft.modes.lichess.puzzle_game import PuzzleGame
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, _make_game, _make_recorder
from nicsoft.tests.test_issue354_lichess_puzzles_l3 import FakeBoard as PuzzleFakeBoard
from nicsoft.tests.test_issue354_lichess_puzzles_l3 import _make_recorder as _make_puzzle_recorder
from nicsoft.tests.test_issue354_lichess_puzzles_l3 import _puzzle


# ── Horloge monotone contrôlable (jamais de sleep réel) ──────────────────────

class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _install_fake_clock(monkeypatch, start=1000.0):
    clock = _FakeClock(start)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    return clock


# ── Double léger — partie Lichess (LichessGame, utilisateur blanc, IA noire) ─

def _make_lichess_game_white(monkeypatch):
    _make_recorder(monkeypatch)
    board = FakeBoard()
    sent = []
    game, client, _ = _make_game(nl_inst=board)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append(uci))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    return game, board, sent


# ── Double léger — problème Lichess (PuzzleGame) ─────────────────────────────

def _make_puzzle_game(monkeypatch, fen=None):
    start = chess.Board(fen) if fen else chess.Board()
    puzzle = _puzzle(solution=["e2e4"], fen=start.fen())
    _make_puzzle_recorder(monkeypatch)
    board = PuzzleFakeBoard(initial_fen=start.board_fen())
    game = PuzzleGame(board, "lip_x", puzzle, player_name="Alain")
    accepted = []
    # Isole la détection physique (seule chose testée ici) de la logique de
    # résolution du problème (comparaison à la solution, envoi du résultat) —
    # déjà couverte par test_issue354_lichess_puzzles_l3.py.
    monkeypatch.setattr(game, "_evaluate_user_move", lambda move: accepted.append(move.uci()))
    return game, board, accepted


# ═══════════════════════════════════════════════════════════════════════
# 1. Pion deux cases glissé : case intermédiaire vue brièvement, seul le
#    coup final est envoyé.
# ═══════════════════════════════════════════════════════════════════════

def test_game_pion_deux_cases_glisse_seul_coup_final_envoye(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, sent = _make_lichess_game_white(monkeypatch)
    e3 = chess.Board()
    e3.push_uci("e2e3")
    e4 = chess.Board()
    e4.push_uci("e2e4")

    board.current_fen = e3.board_fen() + " w - - 0 1"
    game._tick_physical()  # case intermédiaire lue brièvement
    assert sent == []

    board.current_fen = e4.board_fen() + " w - - 0 1"
    game._tick_physical()  # la pièce continue de glisser jusqu'à e4
    assert sent == []  # nouvelle lecture : l'attente recommence

    clock.advance(game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert sent == ["e2e4"]


def test_puzzle_pion_deux_cases_glisse_seul_coup_final_envoye(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, accepted = _make_puzzle_game(monkeypatch)
    e3 = chess.Board()
    e3.push_uci("e2e3")
    e4 = chess.Board()
    e4.push_uci("e2e4")

    board.current_fen = e3.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert accepted == []

    board.current_fen = e4.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert accepted == []

    clock.advance(puzzle_game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert accepted == ["e2e4"]


# ═══════════════════════════════════════════════════════════════════════
# 2. Glissement lent : la case intermédiaire reste lue plusieurs fois mais
#    moins longtemps que la durée de stabilité, puis la position finale
#    devient stable — jamais de coup intermédiaire envoyé.
# ═══════════════════════════════════════════════════════════════════════

def test_game_glissement_lent_jamais_de_coup_intermediaire(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, sent = _make_lichess_game_white(monkeypatch)
    e3 = chess.Board()
    e3.push_uci("e2e3")
    e4 = chess.Board()
    e4.push_uci("e2e4")

    board.current_fen = e3.board_fen() + " w - - 0 1"
    game._tick_physical()
    clock.advance(0.2)
    game._tick_physical()
    assert sent == []
    clock.advance(0.1)  # 0.3s cumulés : toujours sous MOVE_STABLE_DELAY_S
    game._tick_physical()
    assert sent == []

    board.current_fen = e4.board_fen() + " w - - 0 1"
    game._tick_physical()  # nouvelle lecture : l'attente recommence
    assert sent == []
    clock.advance(game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert sent == ["e2e4"]


def test_puzzle_glissement_lent_jamais_de_coup_intermediaire(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, accepted = _make_puzzle_game(monkeypatch)
    e3 = chess.Board()
    e3.push_uci("e2e3")
    e4 = chess.Board()
    e4.push_uci("e2e4")

    board.current_fen = e3.board_fen() + " w - - 0 1"
    game._tick_physical()
    clock.advance(0.2)
    game._tick_physical()
    assert accepted == []
    clock.advance(0.1)
    game._tick_physical()
    assert accepted == []

    board.current_fen = e4.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert accepted == []
    clock.advance(puzzle_game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert accepted == ["e2e4"]


# ═══════════════════════════════════════════════════════════════════════
# 3. Pièce levée puis reposée à sa place : aucun coup, quel que soit le
#    temps passé pièce en main.
# ═══════════════════════════════════════════════════════════════════════

def test_game_piece_levee_puis_reposee_aucun_coup(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, sent = _make_lichess_game_white(monkeypatch)
    start_fen = game.board.board_fen()

    lifted = chess.Board()
    lifted.remove_piece_at(chess.E2)  # pion en main, aucune case nouvellement occupée
    board.current_fen = lifted.board_fen() + " w - - 0 1"
    game._tick_physical()
    clock.advance(1.0)
    game._tick_physical()
    assert sent == []

    board.current_fen = start_fen + " w - - 0 1"
    game._tick_physical()
    assert sent == []


def test_puzzle_piece_levee_puis_reposee_aucun_coup(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, accepted = _make_puzzle_game(monkeypatch)
    start_fen = game.board.board_fen()

    lifted = chess.Board()
    lifted.remove_piece_at(chess.E2)
    board.current_fen = lifted.board_fen() + " w - - 0 1"
    game._tick_physical()
    clock.advance(1.0)
    game._tick_physical()
    assert accepted == []

    board.current_fen = start_fen + " w - - 0 1"
    game._tick_physical()
    assert accepted == []


# ═══════════════════════════════════════════════════════════════════════
# 4. Coup réellement joué sur la case courte (e2-e3 voulu, pas un glissé) :
#    accepté une fois la durée de stabilité écoulée.
# ═══════════════════════════════════════════════════════════════════════

def test_game_coup_sur_case_courte_accepte_apres_stabilite(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, sent = _make_lichess_game_white(monkeypatch)
    e3 = chess.Board()
    e3.push_uci("e2e3")

    board.current_fen = e3.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert sent == []
    clock.advance(game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert sent == ["e2e3"]


def test_puzzle_coup_sur_case_courte_accepte_apres_stabilite(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, accepted = _make_puzzle_game(monkeypatch)
    e3 = chess.Board()
    e3.push_uci("e2e3")

    board.current_fen = e3.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert accepted == []
    clock.advance(puzzle_game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert accepted == ["e2e3"]


# ═══════════════════════════════════════════════════════════════════════
# 5. Capture intermédiaire pendant un glissement : jamais envoyée si la
#    position finale (non capturante sur cette case) devient stable avant
#    la fin de la durée de stabilité.
# ═══════════════════════════════════════════════════════════════════════

def _capture_slide_position():
    """Position arbitraire (jamais atteinte en partie réelle, non testée ici
    pour sa légalité d'ensemble) où un pion blanc en e4 a deux captures
    légales distinctes (d5 et f5) — simule un glissement diagonal dont la
    case intermédiaire lue serait une capture différente de la case finale
    réellement visée."""
    board = chess.Board(None)
    board.set_piece_at(chess.E4, chess.Piece(chess.PAWN, chess.WHITE))
    board.set_piece_at(chess.D5, chess.Piece(chess.PAWN, chess.BLACK))
    board.set_piece_at(chess.F5, chess.Piece(chess.PAWN, chess.BLACK))
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
    board.turn = chess.WHITE
    return board


def test_game_capture_intermediaire_jamais_envoyee(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    game, board, sent = _make_lichess_game_white(monkeypatch)
    custom = _capture_slide_position()
    game.board = custom
    intermediate = custom.copy()
    intermediate.push_uci("e4d5")
    final = custom.copy()
    final.push_uci("e4f5")

    board.current_fen = intermediate.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert sent == []

    board.current_fen = final.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert sent == []

    clock.advance(game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert sent == ["e4f5"]


def test_puzzle_capture_intermediaire_jamais_envoyee(monkeypatch):
    clock = _install_fake_clock(monkeypatch)
    custom = _capture_slide_position()
    game, board, accepted = _make_puzzle_game(monkeypatch, fen=custom.fen())
    intermediate = custom.copy()
    intermediate.push_uci("e4d5")
    final = custom.copy()
    final.push_uci("e4f5")

    board.current_fen = intermediate.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert accepted == []

    board.current_fen = final.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert accepted == []

    clock.advance(puzzle_game_mod.MOVE_STABLE_DELAY_S + 0.05)
    game._tick_physical()
    assert accepted == ["e4f5"]


# ═══════════════════════════════════════════════════════════════════════
# 6. Non-régression : promotion (aucune attente de stabilité, choix de la
#    pièce fait à l'écran) et position illégale (stabilité par NOMBRE de
#    lectures, inchangée — jamais par le temps).
# ═══════════════════════════════════════════════════════════════════════

def test_game_promotion_toujours_detectee_sans_attente_de_stabilite(monkeypatch):
    _install_fake_clock(monkeypatch)
    game, board, sent = _make_lichess_game_white(monkeypatch)
    game.board = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")
    board.current_fen = "N7/8/8/8/8/8/8/k6K w - - 0 1"  # pièce quelconque en a8
    game._tick_physical()
    assert game._pending_promotion == (chess.A7, chess.A8)
    game._submit_promotion("q")
    assert sent == ["a7a8q"]


def test_puzzle_promotion_toujours_detectee_sans_attente_de_stabilite(monkeypatch):
    _install_fake_clock(monkeypatch)
    start = chess.Board("8/P7/8/8/8/8/k6K/8 w - - 0 1")
    game, board, accepted = _make_puzzle_game(monkeypatch, fen=start.fen())
    board.current_fen = "Q7/8/8/8/8/8/k6K/8 w - - 0 1"
    game._tick_physical()
    assert game._pending_promotion == (chess.A7, chess.A8)
    assert accepted == []  # pas encore soumise : choix de la pièce en attente


def test_game_position_illegale_par_nombre_de_lectures_jamais_par_le_temps(monkeypatch):
    _install_fake_clock(monkeypatch)
    game, board, sent = _make_lichess_game_white(monkeypatch)
    # Deux pions avancés à la fois depuis le départ : ne correspond à aucun
    # coup légal unique (contrairement à un simple d2-d4, qui en serait un).
    wrong = chess.Board()
    wrong.remove_piece_at(chess.E2)
    wrong.set_piece_at(chess.E4, chess.Piece(chess.PAWN, chess.WHITE))
    wrong.remove_piece_at(chess.D2)
    wrong.set_piece_at(chess.D4, chess.Piece(chess.PAWN, chess.WHITE))
    board.current_fen = wrong.board_fen() + " w - - 0 1"

    # Horloge JAMAIS avancée ici : si la détection dépendait du temps, elle
    # ne se déclencherait jamais — elle doit pourtant s'activer exactement
    # au nombre de lectures déjà en place (ILLEGAL_STABLE_READS_REQUIRED).
    for _ in range(game.ILLEGAL_STABLE_READS_REQUIRED - 1):
        game._tick_physical()
    assert game._illegal_position_active is False
    game._tick_physical()
    assert game._illegal_position_active is True
    assert sent == []


def test_puzzle_position_illegale_par_nombre_de_lectures_jamais_par_le_temps(monkeypatch):
    _install_fake_clock(monkeypatch)
    game, board, accepted = _make_puzzle_game(monkeypatch)
    board.current_fen = "rnbqkbnr/pppppppp/8/8/8/8/8/RNBQKBNR w - - 0 1"

    for _ in range(puzzle_game_mod.ILLEGAL_STABLE_READS_REQUIRED - 1):
        game._tick_physical()
    assert game._illegal_position_active is False
    game._tick_physical()
    assert game._illegal_position_active is True
    assert accepted == []
