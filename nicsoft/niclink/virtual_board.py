"""
nicsoft/niclink/virtual_board.py — Implémentation virtuelle du driver NicLink.

Remplace NicLinkManager quand aucun échiquier physique n'est connecté.
Les coups sont reçus via SocketIO (event 'virtual_move') au lieu du plateau USB.

Interface identique à NicLinkManager (duck typing) — les modules de jeu
(play_pedagogique, labo, humain...) n'ont pas besoin de savoir lequel ils utilisent.
"""

import logging
import queue
import threading
import time

import chess
from nicsoft.engine.board_utils import san_ep

from .nl_exceptions import ExitNicLink

logger = logging.getLogger("niclink.virtual_board")


class VirtualBoard:
    """
    Driver virtuel : remplace NicLinkManager sans échiquier physique.

    Coups reçus via post_move() — appelé par le handler SocketIO 'virtual_move'.
    Toutes les méthodes LED sont des no-ops silencieux.
    """

    def __init__(self):
        # État de la partie — miroir de NicLinkManager
        self.game_board   = chess.Board()
        self.last_move    = None

        # Signaux d'arrêt — identiques à NicLinkManager
        self.game_over    = threading.Event()
        self.kill_switch  = threading.Event()
        self.has_moved    = threading.Event()
        self.start_game   = threading.Event()

        # Queue interne : les coups UCI postés par SocketIO
        self._move_queue: queue.Queue = queue.Queue()

        logger.info("VirtualBoard initialisé")

    @property
    def current_fen(self) -> str:
        """
        Miroir de NicLinkManager.current_fen.
        En mode virtuel, le game_board est toujours à jour — on retourne son FEN.
        Utilisé par LaboSession.sync_from_physical(), board_watcher(), do_best_move().
        """
        return self.game_board.board_fen()

    # ── API coups ─────────────────────────────────────────────────────────────

    def post_move(self, uci: str) -> None:
        """
        Appelé par le handler SocketIO 'virtual_move'.
        Poste le coup UCI dans la queue — await_move() le récupèrera.
        """
        self._move_queue.put(uci)
        logger.debug("VirtualBoard.post_move: %s", uci)

    def await_move(self) -> str | None:
        """
        Attend un coup légal du navigateur et le retourne en UCI.
        Bloque jusqu'à réception — identique à NicLinkManager.await_move().

        Retourne None si kill_switch ou game_over est déclenché.
        """
        while not self.kill_switch.is_set():
            if self.game_over.is_set():
                return None

            try:
                uci = self._move_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Valider que le coup est légal sur le game_board courant
            try:
                move = chess.Move.from_uci(uci)
            except ValueError:
                logger.warning("VirtualBoard: coup UCI invalide reçu : %s", uci)
                continue

            if move not in self.game_board.legal_moves:
                logger.warning(
                    "VirtualBoard: coup illégal reçu : %s (position : %s)",
                    uci, self.game_board.fen()
                )
                # Notifier le navigateur que le coup était illégal
                try:
                    from nicsoft.web.server import send_event
                    send_event("virtual_move_illegal", {"uci": uci})
                except Exception:
                    pass
                continue

            self.last_move = uci
            logger.debug("VirtualBoard: coup validé : %s", uci)
            return uci

        raise ExitNicLink("VirtualBoard.await_move(): kill_switch déclenché")

    def get_last_move(self) -> str:
        """Retourne le dernier coup joué."""
        if self.last_move is None:
            raise ValueError("VirtualBoard: last_move est None")
        return self.last_move

    # ── Gestion du game_board ─────────────────────────────────────────────────

    def make_move_game_board(self, move: str) -> None:
        """Joue un coup sur le game_board interne."""
        self.game_board.push_uci(move)

    def set_game_board(self, board: chess.Board) -> None:
        """Remplace le game_board."""
        self.game_board = board

    def get_game_fen(self) -> str:
        """Retourne le FEN du game_board."""
        return self.game_board.fen()

    def is_game_over(self) -> dict | bool:
        """Vérifie si la partie est terminée — identique à NicLinkManager."""
        if self.game_board.is_checkmate():
            return {"over": True, "winner": not self.game_board.turn, "reason": "checkmate"}
        if self.game_board.is_stalemate():
            return {"over": True, "winner": False, "reason": "Is a stalemate"}
        if self.game_board.is_insufficient_material():
            return {"over": True, "winner": False, "reason": "Is insufficient material"}
        if self.game_board.is_fivefold_repetition():
            return {"over": True, "winner": False, "reason": "Is fivefold repetition."}
        if self.game_board.is_seventyfive_moves():
            return {"over": True, "winner": False, "reason": (
                "A game is automatically drawn if the half-move clock "
                "since a capture or pawn move is equal to or greater "
                "than 150."
            )}
        return False

    def opponent_moved(self, move: str) -> None:
        """Notifie que l'adversaire (moteur) a joué."""
        self.last_move = move

    def reset(self) -> None:
        """Remet le VirtualBoard à zéro pour une nouvelle partie."""
        self.game_board   = chess.Board()
        self.last_move    = None
        self.game_over    = threading.Event()
        self.has_moved    = threading.Event()
        self.kill_switch  = threading.Event()
        self.start_game   = threading.Event()
        # Vider la queue de coups
        while not self._move_queue.empty():
            try:
                self._move_queue.get_nowait()
            except queue.Empty:
                break
        logger.debug("VirtualBoard reset")

    # ── LEDs — no-ops ─────────────────────────────────────────────────────────
    # Toutes ces méthodes existent dans NicLinkManager.
    # Elles ne font rien en mode virtuel — pas d'erreur, pas de log parasite.

    def turn_off_all_leds(self) -> None:
        pass

    def set_all_leds(self, light_board) -> None:
        pass

    def set_move_leds(self, move: str) -> None:
        pass

    def set_led(self, square: str, status: bool) -> None:
        pass

    def signal_lights(self, sig_num: int, stop=None) -> None:
        pass

    def beep(self) -> None:
        pass

    def gameover_lights(self) -> None:
        pass

    # ── Méthodes FEN ponctuelles ──────────────────────────────────────────────
    # Utilisées dans _wait_position_web et autres — adaptées pour le virtuel.

    def get_fen(self) -> str:
        """Retourne le FEN du game_board (pas de lecture USB)."""
        return self.game_board.fen()

    def check_game_board_against_external(self) -> bool:
        """Toujours True en mode virtuel — pas de plateau à synchroniser."""
        return True

    def show_board_diff(self, board1: chess.Board, board2: chess.Board) -> bool:
        """No-op en mode virtuel."""
        return False

    # ── Compatibilité thread (NicLinkManager est un Thread) ───────────────────

    def start(self) -> None:
        """No-op — VirtualBoard n'a pas de thread propre."""
        pass

    def make_virtual_board_watcher(self, session) -> threading.Thread:
        """
        Remplaçant de LaboSession.board_watcher() pour le mode virtuel.
        Lit les coups UCI depuis _move_queue et les pousse dans la session labo,
        en reproduisant exactement ce que board_watcher() ferait après réception
        d'un coup légal.

        Usage dans __main__.py :
            t = vb.make_virtual_board_watcher(session)
            t.start()
        """
        def _watcher():
            while session._running:
                try:
                    uci = self._move_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                try:
                    move = chess.Move.from_uci(uci)
                except ValueError:
                    logger.warning("virtual_board_watcher: UCI invalide : %s", uci)
                    continue

                if move not in session.board.legal_moves:
                    logger.warning("virtual_board_watcher: coup illégal : %s", uci)
                    try:
                        from nicsoft.web.server import send_event
                        send_event("virtual_move_illegal", {"uci": uci})
                    except Exception:
                        pass
                    continue

                # En auto, ignorer les coups du camp moteur
                if session._auto_on and session.board.turn == session.engine_color:
                    continue

                if session._engine_busy or session._placement_in_progress:
                    continue

                san   = san_ep(session.board, move)
                color = "white" if session.board.turn == chess.WHITE else "black"
                fen_avant = session.board.fen()

                session.board.push(move)
                session.active_turn = "white" if session.board.turn == chess.WHITE else "black"
                session._fen_history.append(session.board.fen())
                self.game_board = session.board.copy()

                from nicsoft.web.server import send_event
                send_event("move", {
                    "fen":    session.board.board_fen(),
                    "san":    san,
                    "uci":    uci,
                    "color":  color,
                    "player": "Joueur",
                    "qualite": None,
                })

                if session.analyse_active:
                    def _eval(fa=fen_avant, mv=move, s=san):
                        try:
                            board_av = chess.Board(fa)
                            qualite, delta, _ = session.engine.evaluate_move(board_av, mv, depth=8)
                            if qualite != "bon":
                                LABELS = {"imprecision": "?! Imprécision", "erreur": "? Erreur", "blunder": "?? Gaffe"}
                                send_event("labo_feedback", {
                                    "qualite": qualite, "delta_cp": delta,
                                    "san": s, "label": LABELS.get(qualite, qualite),
                                })
                        except Exception:
                            pass
                    threading.Thread(target=_eval, daemon=True).start()

                session._send_position(uci)
                session._check_end()

                if session._auto_on and session.board.turn == session.engine_color and not session._engine_busy:
                    session.do_engine_play()

        return threading.Thread(target=_watcher, daemon=True, name="virtual_board_watcher")
