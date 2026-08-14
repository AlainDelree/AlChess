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
        # Tous les coups joués depuis la position de départ réelle —
        # (chess.Move, san) — pile pour prev_move(). Inclut les init_moves,
        # qui sont donc entièrement navigables (aucun plancher).
        self._history: list = []
        # Init_moves pré-calculés à load() sous forme (chess.Move, san),
        # appliqués un par un par next_move() comme le reste de la ligne.
        self._init_moves_list: list = []

    def load(self, source, line_id: str = "") -> dict:
        """Charge une source : le board reste en position de départ, les
        init_moves sont pré-calculés (SAN inclus) mais appliqués coup par
        coup via next_move(), pour rester navigables comme le reste de la
        ligne."""
        self.source   = source
        self.line_id  = line_id
        self.board    = chess.Board()
        self._history = []
        self._init_moves_list = []
        scratch = chess.Board()
        for uci in getattr(source, "init_moves", []):
            try:
                move = chess.Move.from_uci(uci)
            except Exception:
                continue
            if move not in scratch.legal_moves:
                break
            san = san_ep(scratch, move)
            scratch.push(move)
            self._init_moves_list.append((move, san))
        self._update_board_display()
        return self.get_state()

    def next_move(self) -> dict:
        """Applique le prochain coup — d'abord les init_moves pré-stockés,
        puis les coups de la source. No-op si la ligne est terminée."""
        if not self.has_more():
            return self.get_state()
        if len(self._history) < len(self._init_moves_list):
            move, san = self._init_moves_list[len(self._history)]
        else:
            move = self.source.get_main_move(self.board)
            if move is None:
                return self.get_state()
            san = san_ep(self.board, move)
        self.board.push(move)
        self._history.append((move, san))
        self._update_board_display()
        return self.get_state()

    def choose_move(self, uci: str) -> dict:
        """Applique un coup spécifique (UCI) au lieu du coup principal.
        Utilisé quand l'utilisateur clique sur une alternative du tableau.
        Le coup doit être légal sur le board courant. Retourne get_state()
        après application, ou get_state() inchangé si le coup est illégal."""
        try:
            move = chess.Move.from_uci(uci)
        except Exception:
            return self.get_state()
        if move not in self.board.legal_moves:
            return self.get_state()
        san = san_ep(self.board, move)
        self.board.push(move)
        self._history.append((move, san))
        self._update_board_display()
        return self.get_state()

    def prev_move(self) -> dict:
        """Dépile le dernier coup joué. No-op si déjà à la position de départ."""
        if self.is_at_start():
            return self.get_state()
        self._history.pop()
        self.board.pop()
        self._update_board_display()
        return self.get_state()

    def is_at_start(self) -> bool:
        return len(self._history) == 0

    def has_more(self) -> bool:
        if len(self._history) < len(self._init_moves_list):
            return True
        return self.source is not None and self.source.has_more(self.board)

    def get_state(self) -> dict:
        if self._history:
            last_move, last_san = self._history[-1]
            last_move_uci = last_move.uci()
            move_san      = last_san
        else:
            last_move_uci = None
            move_san      = None
        # Les alternatives représentent les coups candidats DEPUIS la position
        # avant le dernier coup joué (pour expliquer ce choix) — pas depuis la
        # position courante. On rejoue donc sur un board temporaire dépilé.
        alternatives = []
        if self.source is not None:
            try:
                alt_board = self.board.copy()
                if self._history:
                    alt_board.pop()
                for alt in self.source.get_alternatives(alt_board):
                    try:
                        san = san_ep(alt_board, chess.Move.from_uci(alt["uci"]))
                    except Exception:
                        san = alt["uci"]
                    alternatives.append({"uci": alt["uci"], "san": san, "weight": alt.get("weight", 0)})
            except Exception:
                alternatives = []
        if not alternatives and last_move_uci is not None:
            # Source sans alternatives (ex. PGNLineSource) : le coup joué
            # reste la seule entrée du tableau, à 100%.
            alternatives = [{"uci": last_move_uci, "san": move_san, "weight": 1}]
        return {
            "fen":            self.board.fen(),
            "last_move_uci":  last_move_uci,
            "main_move_uci":  last_move_uci,
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
