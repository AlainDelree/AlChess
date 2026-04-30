"""
board_utils.py — NicLink
Utilitaires partagés liés au plateau physique.
"""

import chess
import time
import logging

logger = logging.getLogger(__name__)

INITIAL_FEN = chess.Board().board_fen()


def analyser_position_illegale(board: chess.Board, fen_physique: str) -> str:
    """
    Analyse pourquoi une position physique est illégale par rapport à board.
    Retourne un message d'erreur adapté au contexte.

    Cas couverts :
    - Roi en échec non paré
    - Coup met le roi en échec (clouage ou auto-échec)
    - Plusieurs pièces déplacées simultanément
    - Pièce déplacée sur une case invalide pour son type
    - Pièce manquante ou en trop
    """
    try:
        hw_board = chess.Board(fen_physique + " w - - 0 1")
    except Exception:
        return "⚠ Position illégale — remettez les pièces à leur place."

    expected = board.board_fen()

    # Compter les cases différentes
    diff_squares = []
    for sq in chess.SQUARES:
        if board.piece_at(sq) != hw_board.piece_at(sq):
            diff_squares.append(sq)

    # Cas 1 : Roi en échec non paré
    if board.is_check():
        return "⚠ Vous êtes en échec — parez l'échec avant de jouer."

    # Cas 2 : Plusieurs pièces déplacées (> 2 cases différentes = pas un coup simple)
    if len(diff_squares) > 4:
        return "⚠ Plusieurs pièces déplacées — remettez l'échiquier en ordre."

    # Cas 3 : Tenter d'identifier le coup joué et pourquoi il est illégal
    if len(diff_squares) >= 2:
        # Trouver la pièce qui a bougé (case vide dans physique mais occupée dans attendu)
        moved_from = [sq for sq in diff_squares
                      if board.piece_at(sq) is not None
                      and hw_board.piece_at(sq) != board.piece_at(sq)]
        moved_to   = [sq for sq in diff_squares
                      if hw_board.piece_at(sq) is not None
                      and hw_board.piece_at(sq) != board.piece_at(sq)]

        if moved_from and moved_to:
            sq_from = moved_from[0]
            sq_to   = moved_to[0]
            piece   = board.piece_at(sq_from)

            if piece:
                # Vérifier si ce coup mettrait le roi en échec (clouage)
                test_board = board.copy()
                try:
                    move = chess.Move(sq_from, sq_to)
                    if move in board.pseudo_legal_moves and move not in board.legal_moves:
                        return f"⚠ Ce coup met votre roi en échec — pièce clouée."
                    elif move not in board.pseudo_legal_moves:
                        piece_name = {
                            chess.PAWN:   "Le pion",
                            chess.KNIGHT: "Le cavalier",
                            chess.BISHOP: "Le fou",
                            chess.ROOK:   "La tour",
                            chess.QUEEN:  "La dame",
                            chess.KING:   "Le roi",
                        }.get(piece.piece_type, "Cette pièce")
                        return f"⚠ {piece_name} ne peut pas aller là."
                except Exception:
                    pass

    return "⚠ Coup illégal — remettez la pièce à sa place."


def wait_for_initial_position(nl_inst, timeout: float = 10.0) -> None:
    """
    Bloque jusqu'a ce que le plateau physique soit en position initiale.
    Lève ConnectionError si le plateau ne répond pas après timeout secondes.
    """
    first_check = True
    last_message_time = 0.0
    consecutive_errors = 0
    t_start = time.time()

    while True:
        try:
            raw_fen = nl_inst.get_fen()
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors >= 5 or (time.time() - t_start) >= timeout:
                raise ConnectionError(
                    "Échiquier non détecté. Vérifiez l'USB et que le plateau est allumé."
                )
            time.sleep(0.2)
            continue

        board_fen = raw_fen.strip().split()[0] if raw_fen else ""

        if not board_fen:
            consecutive_errors += 1
            if consecutive_errors >= 5 or (time.time() - t_start) >= timeout:
                raise ConnectionError(
                    "Échiquier non détecté. Vérifiez l'USB et que le plateau est allumé."
                )
            time.sleep(0.2)
            continue

        if board_fen == INITIAL_FEN:
            nl_inst.turn_off_all_leds()
            if not first_check:
                print("Plateau pret. Demarrage de la partie.")
            return

        if first_check:
            first_check = False
            print()
            print("⚠  Le plateau n'est pas en position initiale.")
            print("   Rangez toutes les pieces, la partie demarrera automatiquement.")
            try:
                nl_inst.signal_lights(1)
            except Exception:
                pass
            last_message_time = time.time()
        elif time.time() - last_message_time >= 3.0:
            print("   En attente de la position initiale...")
            last_message_time = time.time()

        time.sleep(0.3)
