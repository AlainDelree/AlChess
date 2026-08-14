"""
nicsoft/modes/opening_explorer/sources.py — NicLink
Sources de coups pour l'Opening Explorer : livre Polyglot (catalogue
OUVERTURES) ou ligne PGN personnelle figée (mes_lignes.json).

Interface commune (duck typing) utilisée par ExplorerSession :
  get_main_move(board)    → chess.Move | None
  get_alternatives(board) → list[{"uci": str, "weight": int}]
  has_more(board)         → bool
Attributs communs : nom, camp_suggere, init_moves.
"""

import chess
import chess.polyglot


class PolyglotSource:
    """Coups théoriques tirés d'un livre Polyglot pour une entrée du catalogue OUVERTURES."""

    def __init__(self, ouverture: dict, book_path: str):
        self.ouverture    = ouverture
        self.book_path    = book_path
        self.nom          = ouverture.get("nom", "")
        self.camp_suggere = ouverture.get("camp_suggere", "white")
        self.init_moves   = ouverture.get("init", [])

    def _entries(self, board: chess.Board) -> list:
        try:
            with chess.polyglot.open_reader(self.book_path) as reader:
                entries = list(reader.find_all(board))
        except Exception:
            return []
        entries.sort(key=lambda e: e.weight, reverse=True)
        return entries

    def get_main_move(self, board: chess.Board):
        entries = self._entries(board)
        return entries[0].move if entries else None

    def get_alternatives(self, board: chess.Board) -> list:
        return [{"uci": e.move.uci(), "weight": e.weight} for e in self._entries(board)]

    def has_more(self, board: chess.Board) -> bool:
        return self.get_main_move(board) is not None


class PGNLineSource:
    """Ligne fixe importée depuis mes_lignes.json — aucune alternative."""

    def __init__(self, ligne: dict):
        self.ligne        = ligne
        self.nom          = ligne.get("nom", "")
        self.camp_suggere = ligne.get("camp_suggere", "white")
        self.init_moves   = ligne.get("init", [])
        # "line" inclut déjà les init_moves en préfixe (format mes_lignes.json) —
        # l'indexation se fait directement sur len(board.move_stack), comme
        # dans ExerciceSession._get_book_moves (mode init_only).
        self.line         = ligne.get("line", self.init_moves)

    def get_main_move(self, board: chess.Board):
        idx = len(board.move_stack)
        if idx >= len(self.line):
            return None
        try:
            move = chess.Move.from_uci(self.line[idx])
        except Exception:
            return None
        return move if move in board.legal_moves else None

    def get_alternatives(self, board: chess.Board) -> list:
        return []

    def has_more(self, board: chess.Board) -> bool:
        return self.get_main_move(board) is not None
