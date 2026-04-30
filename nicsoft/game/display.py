"""
display.py — NicLink
Fonctions d'affichage terminal pour les parties d'échecs.

Inclut display_board_diff() qui affiche un plateau visuel quand des pièces
sont déplacées/renversées, avec deux modes d'affichage :
  - Symboles Unicode ♔♕♖♗♘♙ (par défaut)
  - Lettres ASCII  K Q R B N P  (fallback ou préférence utilisateur)

L'utilisateur peut basculer entre les deux en appuyant sur Tab.
"""

import sys
import chess

# ──────────────────────────────────────────────
# Préférences d'affichage (modifiable via Tab)
# ──────────────────────────────────────────────

# True = symboles Unicode, False = lettres ASCII
_use_unicode = True


def toggle_display_mode() -> bool:
    """Bascule entre Unicode et ASCII. Retourne le nouveau mode."""
    global _use_unicode
    _use_unicode = not _use_unicode
    mode = "symboles ♟" if _use_unicode else "lettres (K/Q/R/B/N/P)"
    print(f"   [Affichage basculé → {mode}]")
    return _use_unicode


# ──────────────────────────────────────────────
# Tables de symboles
# ──────────────────────────────────────────────

# Symboles Unicode standard pour les pièces d'échecs
_UNICODE = {
    (chess.KING,   chess.WHITE): "♔",
    (chess.QUEEN,  chess.WHITE): "♕",
    (chess.ROOK,   chess.WHITE): "♖",
    (chess.BISHOP, chess.WHITE): "♗",
    (chess.KNIGHT, chess.WHITE): "♘",
    (chess.PAWN,   chess.WHITE): "♙",
    (chess.KING,   chess.BLACK): "♚",
    (chess.QUEEN,  chess.BLACK): "♛",
    (chess.ROOK,   chess.BLACK): "♜",
    (chess.BISHOP, chess.BLACK): "♝",
    (chess.KNIGHT, chess.BLACK): "♞",
    (chess.PAWN,   chess.BLACK): "♟",
}

# Fallback ASCII : majuscule = blanc, minuscule = noir
_ASCII = {
    (chess.KING,   chess.WHITE): "K",
    (chess.QUEEN,  chess.WHITE): "Q",
    (chess.ROOK,   chess.WHITE): "R",
    (chess.BISHOP, chess.WHITE): "B",
    (chess.KNIGHT, chess.WHITE): "N",
    (chess.PAWN,   chess.WHITE): "P",
    (chess.KING,   chess.BLACK): "k",
    (chess.QUEEN,  chess.BLACK): "q",
    (chess.ROOK,   chess.BLACK): "r",
    (chess.BISHOP, chess.BLACK): "b",
    (chess.KNIGHT, chess.BLACK): "n",
    (chess.PAWN,   chess.BLACK): "p",
}

_PIECE_NAMES_FR = {
    chess.KING:   ("Roi",     "Roi"),
    chess.QUEEN:  ("Dame",    "Dame"),
    chess.ROOK:   ("Tour",    "Tour"),
    chess.BISHOP: ("Fou",     "Fou"),
    chess.KNIGHT: ("Cavalier","Cavalier"),
    chess.PAWN:   ("Pion",    "Pion"),
}


def _piece_symbol(piece: chess.Piece) -> str:
    """Retourne le symbole d'une pièce selon le mode actif."""
    table = _UNICODE if _use_unicode else _ASCII
    return table.get((piece.piece_type, piece.color), "?")


def _piece_name_fr(piece: chess.Piece) -> str:
    """Retourne le nom français d'une pièce avec sa couleur."""
    name = _PIECE_NAMES_FR.get(piece.piece_type, ("?", "?"))[0]
    color = "blanc" if piece.color == chess.WHITE else "noir"
    return f"{name} {color}"


# ──────────────────────────────────────────────
# Affichage du plateau de récupération
# ──────────────────────────────────────────────

def display_board_diff(expected_board: chess.Board, actual_board: chess.Board) -> None:
    """Affiche les pièces à replacer/retirer sans dessin du plateau."""
    missing = {}
    extra   = {}
    for sq in chess.SQUARES:
        exp = expected_board.piece_at(sq)
        act = actual_board.piece_at(sq)
        if exp != act:
            if exp is not None:
                missing[sq] = exp
            if act is not None:
                extra[sq] = act

    if not missing and not extra:
        return

    total = len(set(missing) | set(extra))
    print()
    print(f"⚠  {total} case(s) incorrecte(s) — remettez l'échiquier en ordre :")
    print()

    all_squares = sorted(set(missing) | set(extra),
                         key=lambda sq: (chess.square_rank(sq), chess.square_file(sq)),
                         reverse=True)

    if missing:
        print("  Pièces à replacer :")
        for sq in all_squares:
            if sq in missing:
                piece = missing[sq]
                sym  = _piece_symbol(piece)
                name = _piece_name_fr(piece)
                print(f"    {chess.square_name(sq)} ← {sym}  {name}")

    if extra:
        print("  Pièces à retirer :")
        for sq in all_squares:
            if sq in extra:
                piece = extra[sq]
                sym  = _piece_symbol(piece)
                name = _piece_name_fr(piece)
                print(f"    {chess.square_name(sq)} → {sym}  ({name} en trop)")

    print()

def check_tab_press() -> bool:
    """
    Vérifie de façon non-bloquante si Tab a été pressé.
    Si oui, bascule le mode d'affichage et retourne True.
    Fonctionne sur Linux/Mac. Sur Windows, retourne toujours False.

    À appeler dans les boucles d'attente (wait_for_fish_move_on_board,
    wait_for_initial_position, etc.)
    """
    try:
        import select
        import tty
        import termios

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                ch = sys.stdin.read(1)
                if ch == "\t":
                    toggle_display_mode()
                    return True
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass
    return False


# ──────────────────────────────────────────────
# Fonctions d'affichage existantes (inchangées)
# ──────────────────────────────────────────────

def display_move(player_name, color, move_text):
    color_str = "Blancs" if color == "white" else "Noirs"
    print(f"{player_name} ({color_str}) a joué {move_text}")

    # saut de ligne après le coup des Noirs
    if color == "black":
        print()


def display_turn(player_name, color):
    """Annonce le tour du joueur suivant."""
    color_str = "Blancs" if color == "white" else "Noirs"
    print(f"--- Au tour des {color_str} ({player_name}) ---")


def display_check_status(board):
    """Affiche un message si le roi est en échec (pas mat — géré séparément)."""
    if board.is_check():
        print("⚠  Échec au roi !")
