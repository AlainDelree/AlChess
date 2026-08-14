"""
nicsoft/modes/opening_explorer/explorer_session.py — NicLink
Session de navigation Opening Explorer : position courante, historique de
coups (pour Prev), source active. Aucune interaction humaine — next_move()
et prev_move() sont déclenchés uniquement par les boutons Prev/Next de l'UI.
"""

import logging

import chess

from nicsoft.engine.board_utils import san_ep

logger = logging.getLogger("niclink.opening_explorer")


class ExplorerSession:
    """
    nl_inst : échiquier connecté (physique ou VirtualBoard) — peut être None.
    source  : PolyglotSource ou PGNLineSource, assignée par load().
    """

    def __init__(self, nl_inst=None):
        self.nl_inst = nl_inst
        self.board   = chess.Board()
        self.source  = None
        self.line_id = ""
        # Coups joués après les init_moves — (chess.Move, san) — pile pour prev_move().
        # Les init_moves eux-mêmes ne sont jamais dépilés (position plancher de la navigation).
        self._history: list = []

    def load(self, source, line_id: str = "") -> dict:
        """Charge une source, rejoue ses init_moves (sans pause), émet l'état initial."""
        self.source   = source
        self.line_id  = line_id
        self.board    = chess.Board()
        self._history = []
        for uci in getattr(source, "init_moves", []):
            try:
                move = chess.Move.from_uci(uci)
            except Exception:
                continue
            if move in self.board.legal_moves:
                self.board.push(move)
        self._update_board_display()
        return self.get_state()

    def next_move(self) -> dict:
        """Applique le prochain coup de la source. No-op si la ligne est terminée."""
        if not self.has_more():
            return self.get_state()
        move = self.source.get_main_move(self.board)
        if move is None:
            return self.get_state()
        san = san_ep(self.board, move)
        self.board.push(move)
        self._history.append((move, san))
        self._update_board_display()
        return self.get_state()

    def prev_move(self) -> dict:
        """Dépile le dernier coup joué. No-op si déjà à la position post-init."""
        if self.is_at_start():
            return self.get_state()
        self._history.pop()
        self.board.pop()
        self._update_board_display()
        return self.get_state()

    def is_at_start(self) -> bool:
        return len(self._history) == 0

    def has_more(self) -> bool:
        return self.source is not None and self.source.has_more(self.board)

    def get_state(self) -> dict:
        if self._history:
            last_move, last_san = self._history[-1]
            last_move_uci = last_move.uci()
            move_san      = last_san
        else:
            last_move_uci = None
            move_san      = None
        alternatives = []
        if self.source is not None:
            try:
                alternatives = self.source.get_alternatives(self.board)
            except Exception:
                alternatives = []
        return {
            "fen":            self.board.fen(),
            "last_move_uci":  last_move_uci,
            "move_index":     len(self._history),
            "move_san":       move_san,
            "opening_name":   getattr(self.source, "nom", "") if self.source else "",
            "camp":           getattr(self.source, "camp_suggere", "white") if self.source else "white",
            "alternatives":   alternatives,
            "line_id":        self.line_id,
        }

    # ── Plateau Chessnut (physique ou virtuel) ─────────────────────────────────

    def _update_board_display(self) -> None:
        """Reproduit le mécanisme LED utilisé par pédagogique/exercices (set_move_leds)."""
        if self.nl_inst is None:
            return
        try:
            self.nl_inst.set_game_board(self.board.copy())
        except Exception as e:
            logger.debug(f"set_game_board échoué : {e}")
        try:
            if self._history:
                last_move, _ = self._history[-1]
                self.nl_inst.set_move_leds(last_move.uci())
            else:
                self.nl_inst.turn_off_all_leds()
        except Exception as e:
            logger.debug(f"mise à jour LEDs échouée : {e}")
