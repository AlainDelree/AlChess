"""
nicsoft/exercices/explore_book_display.py — NicLink
Affichage terminal pour l'explorateur de livre Polyglot (issue #281, découpage
de explore_book.py) : barre de poids, échiquier ASCII, ligne de coups jouée.
"""

import chess

from nicsoft.modes.exercices._catalogue import _c, dim


def weight_bar(weight: int, max_weight: int, width: int = 12) -> str:
    if max_weight == 0:
        return " " * width
    filled = round(weight / max_weight * width)
    return "█" * filled + "░" * (width - filled)


# ── Affichage échiquier terminal ──────────────────────────────────────────────

_PIECES_TERM = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
}

def print_board(board: chess.Board, last_move: chess.Move = None) -> None:
    print()
    lm_squares = {last_move.from_square, last_move.to_square} if last_move else set()
    print("    a  b  c  d  e  f  g  h")
    print("  ┌" + "──┬" * 7 + "──┐")
    for rank in range(7, -1, -1):
        row = f"{rank+1} │"
        for file in range(8):
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            sym = _PIECES_TERM.get(piece.symbol(), "·") if piece else "·"
            light = (rank + file) % 2 == 1
            if sq in lm_squares:
                cell = _c("43", f" {sym} ")   # fond jaune = dernier coup
            elif light:
                cell = _c("2",  f" {sym} ")   # case claire = grisé
            else:
                cell = f" {sym} "
            row += cell + "│"
        print(row + f" {rank+1}")
        if rank > 0:
            print("  ├" + "──┼" * 7 + "──┤")
    print("  └" + "──┴" * 7 + "──┘")
    print("    a  b  c  d  e  f  g  h")
    print()


# ── Affichage ligne de coups ──────────────────────────────────────────────────

def format_move_line(board_history: list, san_history: list) -> str:
    """Formate la ligne de coups jouée ex: 1.d4 d5 2.c4 e6"""
    if not san_history:
        return dim("(position initiale)")
    result = []
    # Reconstituer la numérotation depuis le board initial
    move_num = 1
    # board_history[0] = position initiale, san_history[i] = coup i+1
    # Déterminer qui a commencé (blanc ou noir) depuis board_history[0]
    white_to_move = board_history[0].turn == chess.WHITE if board_history else True
    i = 0
    if not white_to_move:
        result.append(f"1…{san_history[0]}")
        i = 1
        move_num = 2
    while i < len(san_history):
        if i < len(san_history):
            result.append(f"{move_num}.{san_history[i]}")
            i += 1
        if i < len(san_history):
            result.append(san_history[i])
            i += 1
        move_num += 1
    return " ".join(result)
