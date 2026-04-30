import chess
from nicsoft.play_human.__main__ import Game

class DummyNL:
    def get_fen(self):
        return None

def make_game():
    return Game(DummyNL(), "Blanc", "Noir")

def test_find_d4_from_initial_position():
    game = make_game()
    move = game.get_legal_move_matching_hardware("rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR")
    assert move is not None
    assert move.uci() == "d2d4"

def test_find_e4_from_initial_position():
    game = make_game()
    move = game.get_legal_move_matching_hardware("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR")
    assert move is not None
    assert move.uci() == "e2e4"

def test_illegal_position_returns_none():
    game = make_game()
    move = game.get_legal_move_matching_hardware("rnbqkbnr/pppppppp/8/8/8/8/PPP1PPPP/RNBQKBNR")
    assert move is None
