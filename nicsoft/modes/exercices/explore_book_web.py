"""
nicsoft/exercices/explore_book_web.py — NicLink
Fonctions appelées par le serveur web (server.py) pour l'explorateur de
livre Polyglot (issue #281, découpage de explore_book.py).
"""

import chess
import logging

logger = logging.getLogger("NL explore_book")

from nicsoft.modes.exercices._catalogue import (
    BOOKS_DIR, scan_books, book_moves_for, load_existing_inits, trouve_doublon,
)


def list_books_for_web() -> list:
    """Retourne la liste des livres Polyglot disponibles."""
    books = scan_books()
    return [{"name": b.name, "size_kb": round(b.stat().st_size / 1024)} for b in books]


def get_moves_from_web(data: dict) -> dict:
    """
    Retourne la position et les coups disponibles dans un livre.
    data: {book, moves: [uci, ...]}
    """
    book_name = data.get("book", "")
    uci_moves = data.get("moves", [])

    book_path = BOOKS_DIR / book_name
    if not book_path.exists():
        return {"ok": False, "error": f"Livre introuvable : {book_name}"}

    board = chess.Board()
    san_history = []
    valid_moves = []
    for uci in uci_moves:
        try:
            mv = chess.Move.from_uci(uci)
            if mv not in board.legal_moves:
                break
            san_history.append(board.san(mv))
            board.push(mv)
            valid_moves.append(uci)
        except Exception as e:
            logger.warning(f"get_moves_from_web : revalidation du coup '{uci}' échouée : {e}")
            break

    entries = book_moves_for(board, book_path)
    total_weight = sum(e.weight for e in entries) or 1

    moves_out = []
    for i, e in enumerate(entries[:9]):
        try:
            san = board.san(e.move)
        except Exception as e2:
            logger.debug(f"get_moves_from_web : SAN indisponible pour {e.move.uci()}, fallback UCI : {e2}")
            san = e.move.uci()
        moves_out.append({
            "san":    san,
            "uci":    e.move.uci(),
            "weight": e.weight,
            "pct":    round(e.weight / total_weight * 100),
            "star":   i == 0,
        })

    existing_inits = load_existing_inits()
    in_catalogue = trouve_doublon(valid_moves, existing_inits)

    last_from = last_to = None
    if valid_moves:
        u = valid_moves[-1]
        if len(u) >= 4:
            last_from, last_to = u[:2], u[2:4]

    return {
        "ok":          True,
        "fen":         board.fen(),
        "moves":       moves_out,
        "san_history": san_history,
        "valid_moves": valid_moves,
        "in_catalogue": in_catalogue,
        "last_from":   last_from,
        "last_to":     last_to,
        "depth":       len(valid_moves),
    }
