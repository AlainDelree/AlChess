import chess
import chess.pgn
from pathlib import Path

from nicsoft.engine.pgn_manager import build_and_save_pgn, save_game


def test_build_and_save_pgn_creates_human_pgn_path(tmp_path):
    output_path = build_and_save_pgn(
        headers={"White": "Alain", "Black": "Noir"},
        moves=["e2e4"],
        base_dir=str(tmp_path),
        mode="human",
        prefix="human_vs_human",
    )
    p = Path(output_path)
    assert p.exists()
    assert str(p).startswith(str(tmp_path))
    assert "human" in str(p)
    assert p.suffix == ".pgn"


def test_save_game_writes_file_with_headers_and_moves(tmp_path):
    game = chess.pgn.Game()
    game.headers["Event"] = "Human vs Human"
    game.headers["Site"] = "Chessnut Air"
    game.headers["Date"] = "2026.03.17"
    game.headers["White"] = "Alain"
    game.headers["Black"] = "Jessica"
    game.headers["Result"] = "*"

    board = chess.Board()
    node = game

    for uci in ["d2d4", "d7d5", "e2e4"]:
        move = chess.Move.from_uci(uci)
        assert move in board.legal_moves
        san_move = board.san(move)
        board.push(move)
        node = node.add_variation(move)
        assert san_move

    output_path = save_game(game, str(tmp_path / "test_game.pgn"))

    p = Path(output_path)
    assert p.exists()

    content = p.read_text(encoding="utf-8")
    assert '[Event "Human vs Human"]' in content
    assert '[White "Alain"]' in content
    assert '[Black "Jessica"]' in content
    assert "1. d4 d5 2. e4" in content
