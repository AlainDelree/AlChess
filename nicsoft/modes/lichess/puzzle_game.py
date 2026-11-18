"""
nicsoft/modes/lichess/puzzle_game.py — AlChess

Issue #354 (Lichess L3, étapes B et C) : déroulement d'un problème (puzzle)
Lichess sur l'échiquier physique, une fois la position de départ confirmée
par le lanceur (voir game_manager_modes/lichess.py::_run_lichess_puzzle).
Aucun moteur, aucune aide : ce module n'importe jamais nicsoft.engine.*
(sauf board_utils/pgn_manager, génériques) ni chess.engine — même garde
AST que le reste du mode Lichess (test_issue333_lichess_no_engine.py).

État de vérité : contrairement à une vraie partie (dont la vérité vient du
flux Lichess), la solution complète est connue dès la réponse de
GET /api/puzzle/next (voir puzzle_client.py) — `self.board` est donc mis à
jour directement par ce module au fil des coups (du joueur comme de la
réponse adverse forcée), jamais par un flux externe.

Coup qui mate accepté même hors solution (point B, décision retenue) :
établi par lecture du code source public de lila (dépôt lichess-org/lila,
branche master, lu le 16/11/2026) — `ui/puzzle/src/moveTest.ts` :
    if (nodes[i].checkmate) return (ctrl.node.puzzle = 'win');
évalué AVANT toute comparaison avec `puzzle.solution[i]` : un coup qui met
échec et mat est donc toujours gagnant pour Lichess, quelle que soit sa
correspondance avec la solution attendue. Reproduit ci-dessous (voir
_evaluate_user_move) : `board_after.is_checkmate()` prime sur la
comparaison UCI. Point non repris (jugé hors de portée, voir rapport de
clôture) : l'équivalence de notation de roque "altCastles" du même fichier
(ex. "e1h1" vs "e1g1") — un artefact du client web (bibliothèque chessops),
qui n'a pas de raison de s'appliquer à la réponse JSON de l'API REST
publique (notation UCI standard, sans ambiguïté).
"""

import logging
import threading
import time

import chess

from nicsoft.config import LOGS_DIR
from nicsoft.core.ihm_port import send_event, get_action
from nicsoft.engine.board_utils import san_ep
from nicsoft.modes.lichess.game import legal_move_for_hardware, pending_promotion_move
from nicsoft.modes.lichess.puzzle_client import submit_puzzle_result

logger = logging.getLogger("niclink.lichess")

PUZZLE_LOGS_DIR = LOGS_DIR / "lichess_puzzles"

POLL_DELAY_S = 0.05
ILLEGAL_STABLE_READS_REQUIRED = 8
POSITION_ERROR_THROTTLE_S = 1.0
BOARD_LOST_STRIKES = 40  # ~2s de lectures en échec consécutives
RECONNECT_FAST_INTERVAL_S = 2.0
RECONNECT_FAST_DURATION_S = 30.0
RECONNECT_SLOW_INTERVAL_S = 5.0

_OTHER_MODE_ACTIONS = frozenset({
    "mode", "start", "start_humain", "start_retranscription", "start_lichess",
    "start_lichess_puzzle", "start_exercice", "start_drill",
})

_SUBMIT_ERROR_TOAST_KEYS = {
    "invalid": "toast.lichess_invalid_token",
    "missing_scope": "toast.lichess_puzzle_missing_scope",
    "rate_limited": "toast.lichess_rate_limited",
    "network_error": "toast.lichess_network_error",
}


class _BackMenuDuringPuzzle(Exception):
    """Retour au menu demandé pendant une attente bloquante de réplication
    physique (_wait_for_board_fen) — remonte jusqu'à PuzzleGame.run()."""


def _differing_squares(fen_a: str, fen_b: str) -> list:
    """Cases (algébriques) où la pièce diffère entre deux FEN board-only —
    même fonction que game.py::_differing_squares et
    game_manager_modes/lichess.py::_squares_differing, dupliquée ici pour
    éviter un import circulaire (convention déjà en place dans ces deux
    modules)."""
    try:
        a = chess.Board(fen_a + " w - - 0 1")
        b = chess.Board(fen_b + " w - - 0 1")
    except ValueError:
        return []
    return [chess.square_name(sq) for sq in chess.SQUARES if a.piece_at(sq) != b.piece_at(sq)]


def solver_color_for_fen(fen: str) -> str:
    """Couleur qui doit jouer dans la position du problème (celle que le
    solveur doit résoudre, PAS forcément le camp au trait de setup_fen —
    voir parse_puzzle_payload : le premier coup de la liste `solution` est
    toujours joué par ce camp)."""
    return "white" if chess.Board(fen).turn == chess.WHITE else "black"


def first_move_squares(setup_fen: str, opponent_first_move: str):
    """(from_square, to_square) du premier coup adverse affiché à l'écran,
    ou None si absent/illisible — jamais levé d'exception (coup optionnel,
    voir parse_puzzle_payload)."""
    if not opponent_first_move:
        return None
    try:
        board = chess.Board(setup_fen)
        move = board.parse_uci(opponent_first_move)
    except Exception:
        return None
    return move.from_square, move.to_square


class PuzzleGame:
    """Déroulement d'un seul problème Lichess, une fois la position
    physique de départ (`setup_fen`) déjà confirmée par l'appelant. Pas un
    threading.Thread (contrairement à LichessGame) : aucun flux réseau à
    lire en continu, le seul appel réseau est l'envoi final du résultat —
    piloté de façon synchrone par le lanceur (comme LichessGame.start(),
    qui exécute déjà run() de façon synchrone)."""

    def __init__(self, nl_inst, token: str, puzzle: dict, player_name: str = "", game_log=None):
        self.nl_inst = nl_inst
        self.token = token
        self.puzzle_id = puzzle["puzzle_id"]
        self.rating = puzzle.get("rating")
        self.themes = list(puzzle.get("themes") or [])
        self.solution = list(puzzle.get("solution") or [])
        self.setup_fen = puzzle.get("setup_fen") or puzzle.get("fen")
        self.opponent_first_move = puzzle.get("opponent_first_move")
        fen = puzzle.get("fen") or self.setup_fen
        self.board = chess.Board(fen)
        self.solver_color = "white" if self.board.turn == chess.WHITE else "black"
        self.player_name = player_name or "Vous"
        self._game_log = game_log

        self.solved_index = 0
        self.outcome = None          # None | "solved" | "failed"
        self.back_menu_requested = False

        self._pending_submit = None  # {"win": bool} tant que non envoyé
        self.rating_before = None
        self.rating_after = None
        self.rating_diff = None
        self._submit_error_key = None

        self._fail_point_fen = None       # FEN complet juste avant le coup faux
        self._fail_remaining = []         # solution restante à démontrer
        self._solution_shown = False

        self._pending_promotion = None    # (from_square, to_square)
        self._last_illegal_fen = None
        self._illegal_stable_count = 0
        self._illegal_position_active = False

        self._board_lost = False
        self._board_lost_strikes = 0
        self._reconnecting_in_progress = False
        self._next_reconnect_attempt_ts = 0.0

    # ── Journal ──────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        if self._game_log is not None:
            self._game_log.state_change(message)

    # ── Lecture plateau ──────────────────────────────────────────────────

    def _read_hardware_fen(self) -> str:
        try:
            raw = self.nl_inst.get_fen()
        except Exception:
            return ""
        return raw.strip().split()[0] if raw else ""

    def _board_connected(self) -> bool:
        nl_interface = getattr(self.nl_inst, "nl_interface", None)
        is_conn = getattr(nl_interface, "is_connected", None)
        if is_conn is None:
            return True
        try:
            return bool(is_conn())
        except Exception:
            return True

    # ── Animation d'un coup (adverse, forcé ou rejoué pour la solution) ──

    def _light_move(self, from_square, to_square) -> None:
        try:
            self.nl_inst.turn_off_all_leds()
            self.nl_inst.set_led(chess.square_name(from_square), True)
            self.nl_inst.set_led(chess.square_name(to_square), True)
        except Exception as exc:
            logger.debug("Lichess problème : éclairage du coup échoué : %s", exc)

    def _beep(self) -> None:
        try:
            self.nl_inst.beep()
        except Exception as exc:
            logger.debug("Lichess problème : bip échoué : %s", exc)

    def _wait_for_board_fen(self, target_board_fen: str) -> None:
        """Bloque jusqu'à ce que la position physique corresponde à
        `target_board_fen`, ou jusqu'à `back_menu` (lève
        _BackMenuDuringPuzzle). Gère la reconnexion échiquier comme
        _tick_physical."""
        last_wait_sent = 0.0
        while True:
            if self._drain_back_menu_only():
                raise _BackMenuDuringPuzzle()
            hw_fen = self._read_hardware_fen()
            if not hw_fen or not self._board_connected():
                self._register_board_lost()
                if self._board_lost:
                    self._maybe_attempt_reconnect()
                time.sleep(POLL_DELAY_S)
                continue
            self._register_board_present()
            if hw_fen == target_board_fen:
                try:
                    self.nl_inst.turn_off_all_leds()
                except Exception:
                    pass
                send_event("lichess_puzzle_position_ok", {})
                return
            now = time.monotonic()
            if now - last_wait_sent >= POSITION_ERROR_THROTTLE_S:
                last_wait_sent = now
                send_event("lichess_puzzle_position_wait", {
                    "expected_fen": target_board_fen, "physical_fen": hw_fen,
                })
            time.sleep(POLL_DELAY_S)

    def _drain_back_menu_only(self) -> bool:
        """Consomme une éventuelle action "back_menu" en attente — utilisé
        pendant les attentes bloquantes (réplication) où aucune autre
        action n'a de sens. Même garde "mode déjà actif" que
        _process_browser_actions pour toute autre action hors-sujet reçue
        ici (seul back_menu est traité de façon anticipée pendant une
        attente bloquante — seul bouton affiché à l'écran à ce moment,
        voir index.html)."""
        action = get_action(timeout=0.0)
        if action is None:
            return False
        if action.get("type") == "back_menu":
            self.back_menu_requested = True
            return True
        if action.get("type") in _OTHER_MODE_ACTIONS:
            send_event("lichess_puzzle_toast", {"message_key": "lichess.puzzle_menu_verrouille", "type": "warning"})
        return False

    def _register_board_lost(self) -> None:
        self._board_lost_strikes += 1
        if not self._board_lost and self._board_lost_strikes >= BOARD_LOST_STRIKES:
            self._board_lost = True
            self._log("échiquier perdu pendant le problème (lectures vides répétées).")
            send_event("lichess_puzzle_board_lost", {})

    def _register_board_present(self) -> None:
        self._board_lost_strikes = 0
        if self._board_lost:
            self._board_lost = False
            self._log("échiquier reconnecté pendant le problème.")
            send_event("lichess_puzzle_board_ok", {})

    def _maybe_attempt_reconnect(self) -> None:
        if self._reconnecting_in_progress:
            return
        now = time.monotonic()
        if now < self._next_reconnect_attempt_ts:
            return
        self._reconnecting_in_progress = True
        started_at = now

        def _attempt():
            try:
                self.nl_inst.connect()
                restart = getattr(self.nl_inst, "_start_fen_reader", None)
                if restart is not None:
                    restart()
            except Exception as exc:
                logger.debug("Lichess problème : tentative de reconnexion échouée : %s", exc)
            finally:
                elapsed = time.monotonic() - started_at
                interval = (RECONNECT_FAST_INTERVAL_S if elapsed < RECONNECT_FAST_DURATION_S
                            else RECONNECT_SLOW_INTERVAL_S)
                self._next_reconnect_attempt_ts = time.monotonic() + interval
                self._reconnecting_in_progress = False

        threading.Thread(target=_attempt, daemon=True, name="puzzle_reconnect").start()

    # ── Mise en place du premier coup adverse ───────────────────────────

    def animate_opponent_first_move(self) -> None:
        """Appelé une fois la position de départ (`setup_fen`) confirmée —
        anime le premier coup adverse indiqué par le problème (LED + son,
        comme un coup adverse en partie) et bloque jusqu'à sa réplication
        physique. No-op si le problème n'en a pas (voir
        parse_puzzle_payload : setup_fen == fen dans ce cas)."""
        squares = first_move_squares(self.setup_fen, self.opponent_first_move)
        if squares is None:
            return
        from_sq, to_sq = squares
        self._beep()
        self._light_move(from_sq, to_sq)
        self._log(f"coup adverse initial affiché — {self.opponent_first_move}, en attente de réplication physique.")
        send_event("lichess_puzzle_move", {
            "fen": self.board.fen(), "uci": self.opponent_first_move,
            "color": "white" if self.solver_color == "black" else "black",
        })
        self._wait_for_board_fen(self.board.board_fen())
        self._log("premier coup adverse reproduit physiquement.")

    # ── Boucle principale ────────────────────────────────────────────────

    def run(self) -> str:
        """Boucle jusqu'à résolution ou retour au menu. Retourne
        "back_menu" ou "next_puzzle" (jamais autre chose)."""
        try:
            while not self.back_menu_requested and self.outcome is None:
                if self._process_browser_actions():
                    break
                self._tick_physical()
                time.sleep(POLL_DELAY_S)
            if self.back_menu_requested:
                return "back_menu"
            # Résolu (solved/failed) : attendre la décision de l'utilisateur
            # ("Problème suivant"/"Retour au menu"/"Voir la solution").
            return self._wait_post_result_decision()
        except _BackMenuDuringPuzzle:
            return "back_menu"

    def _process_browser_actions(self) -> bool:
        """Traite les actions en attente ; retourne True si back_menu a été
        demandé (fin immédiate de la boucle principale)."""
        while True:
            action = get_action(timeout=0.0)
            if action is None:
                return False
            atype = action.get("type", "")
            if atype == "back_menu":
                self.back_menu_requested = True
                if self.outcome is None:
                    self._log("retour au menu demandé — problème abandonné, aucun résultat envoyé.")
                return True
            if atype in _OTHER_MODE_ACTIONS:
                send_event("lichess_puzzle_toast", {"message_key": "lichess.puzzle_menu_verrouille", "type": "warning"})
                continue
            if atype == "lichess_puzzle_promotion_choice" and self._pending_promotion is not None:
                self._submit_promotion(action.get("piece", "q"))

    def _tick_physical(self) -> None:
        if self.outcome is not None:
            return
        hw_fen = self._read_hardware_fen()
        if not hw_fen or not self._board_connected():
            self._register_board_lost()
            if self._board_lost:
                self._maybe_attempt_reconnect()
            return
        self._register_board_present()
        if self._pending_promotion is not None:
            return
        if hw_fen == self.board.board_fen():
            self._illegal_stable_count = 0
            self._clear_illegal_position()
            return
        promo = pending_promotion_move(self.board, hw_fen)
        if promo is not None:
            from_sq, to_sq = promo
            self._pending_promotion = (from_sq, to_sq)
            send_event("lichess_puzzle_promotion_needed", {
                "from": chess.square_name(from_sq), "to": chess.square_name(to_sq),
            })
            return
        move = legal_move_for_hardware(self.board, hw_fen)
        if move is not None:
            self._evaluate_user_move(move)
            return
        self._handle_illegal(hw_fen)

    def _handle_illegal(self, hw_fen: str) -> None:
        if hw_fen != self._last_illegal_fen:
            self._last_illegal_fen = hw_fen
            self._illegal_stable_count = 1
            return
        self._illegal_stable_count += 1
        if self._illegal_stable_count >= ILLEGAL_STABLE_READS_REQUIRED and not self._illegal_position_active:
            self._illegal_position_active = True
            squares = _differing_squares(self.board.board_fen(), hw_fen)
            self._log(f"position illégale détectée — cases : {', '.join(squares) if squares else '?'}.")
            send_event("lichess_puzzle_illegal_position", {
                "active": True, "expected_fen": self.board.board_fen(), "physical_fen": hw_fen,
            })

    def _clear_illegal_position(self) -> None:
        if self._illegal_position_active:
            self._illegal_position_active = False
            send_event("lichess_puzzle_illegal_position", {"active": False})
        self._last_illegal_fen = None

    def _submit_promotion(self, piece_letter: str) -> None:
        if piece_letter not in ("q", "r", "b", "n"):
            piece_letter = "q"
        from_sq, to_sq = self._pending_promotion
        self._pending_promotion = None
        uci = chess.square_name(from_sq) + chess.square_name(to_sq) + piece_letter
        try:
            move = self.board.parse_uci(uci)
        except Exception as exc:
            logger.warning("Lichess problème : promotion illisible (%s) : %s", uci, exc)
            return
        self._evaluate_user_move(move)

    # ── Évaluation du coup joué ──────────────────────────────────────────

    def _evaluate_user_move(self, move: chess.Move) -> None:
        san = san_ep(self.board, move)
        uci = move.uci()
        board_before_fen = self.board.fen()
        board_after = self.board.copy(stack=False)
        board_after.push(move)
        is_mate = board_after.is_checkmate()
        expected = self.solution[self.solved_index] if self.solved_index < len(self.solution) else None
        correct = is_mate or (expected is not None and uci == expected)

        if not correct:
            self._log(f"coup faux — joué={uci} ({san}), attendu={expected or '?'}.")
            self._fail_point_fen = board_before_fen
            self._fail_remaining = list(self.solution[self.solved_index:])
            self._finish(win=False)
            return

        self.board = board_after
        self.solved_index += 1
        reason = "coup correct (mat alternatif accepté)" if (is_mate and uci != expected) else "coup correct"
        self._log(f"{reason} — joué={uci} ({san}).")
        send_event("lichess_puzzle_move", {
            "fen": self.board.fen(), "san": san, "uci": uci,
            "color": self.solver_color,
        })

        if is_mate or self.solved_index >= len(self.solution):
            self._finish(win=True)
            return

        # Réponse adverse forcée (déjà connue, voir solution) — jouée sur
        # l'échiquier comme un coup adverse de partie (LED + son), puis
        # réplication physique attendue avant de rendre la main.
        opponent_uci = self.solution[self.solved_index]
        try:
            opponent_move = self.board.parse_uci(opponent_uci)
        except Exception as exc:
            logger.warning("Lichess problème : coup de solution illisible (%s) : %s", opponent_uci, exc)
            self._finish(win=True)
            return
        opponent_san = san_ep(self.board, opponent_move)
        self.board.push(opponent_move)
        self.solved_index += 1
        self._log(f"réponse adverse forcée jouée — {opponent_uci} ({opponent_san}).")
        self._beep()
        self._light_move(opponent_move.from_square, opponent_move.to_square)
        send_event("lichess_puzzle_move", {
            "fen": self.board.fen(), "san": opponent_san, "uci": opponent_uci,
            "color": "white" if self.solver_color == "black" else "black",
        })
        self._wait_for_board_fen(self.board.board_fen())

    # ── Fin de problème — envoi du résultat ─────────────────────────────

    def _finish(self, win: bool) -> None:
        self.outcome = "solved" if win else "failed"
        self._pending_submit = {"win": win}
        self._log(f"problème résolu — issue={self.outcome}, résultat en attente d'envoi (classé).")
        self._try_submit_pending()

    def _try_submit_pending(self) -> None:
        if self._pending_submit is None:
            return
        win = self._pending_submit["win"]
        result = submit_puzzle_result(self.token, self.puzzle_id, win=win, rated=True)
        status = result.get("status")
        if status != "ok":
            self._submit_error_key = _SUBMIT_ERROR_TOAST_KEYS.get(status, "toast.lichess_network_error")
            self._log(f"envoi du résultat échoué — statut={status}.")
            send_event("lichess_puzzle_result", self._result_payload())
            return
        self._pending_submit = None
        self._submit_error_key = None
        diff = result.get("rating_diff")
        new_rating = result.get("new_rating")
        self.rating_diff = diff
        self.rating_after = new_rating
        self.rating_before = (new_rating - diff) if (isinstance(new_rating, int) and isinstance(diff, int)) else None
        self._log(
            f"résultat envoyé — win={win}, cote_avant={self.rating_before}, "
            f"cote_apres={self.rating_after}, variation={self.rating_diff}."
        )
        send_event("lichess_puzzle_result", self._result_payload())

    def _result_payload(self) -> dict:
        return {
            "win": self.outcome == "solved",
            "themes": self.themes,
            "rating": self.rating,
            "rating_before": self.rating_before,
            "rating_after": self.rating_after,
            "rating_diff": self.rating_diff,
            "submit_pending": self._pending_submit is not None,
            "submit_error_key": self._submit_error_key,
            "can_view_solution": self.outcome == "failed" and not self._solution_shown,
        }

    # ── Après résolution : attente de la décision de l'utilisateur ──────

    def _wait_post_result_decision(self) -> str:
        while True:
            action = get_action(timeout=POLL_DELAY_S)
            if action is None:
                continue
            atype = action.get("type", "")
            if atype == "back_menu":
                if self._pending_submit is not None:
                    self._log("retour au menu avec résultat non envoyé (réseau indisponible) — perdu définitivement.")
                return "back_menu"
            if atype in _OTHER_MODE_ACTIONS:
                send_event("lichess_puzzle_toast", {"message_key": "lichess.puzzle_menu_verrouille", "type": "warning"})
                continue
            if atype == "lichess_puzzle_retry_submit":
                self._try_submit_pending()
                continue
            if atype == "lichess_puzzle_next":
                return "next_puzzle"
            if atype == "lichess_puzzle_view_solution" and self.outcome == "failed" and not self._solution_shown:
                self._solution_shown = True
                self._show_solution()
                send_event("lichess_puzzle_result", self._result_payload())
                continue

    def _show_solution(self) -> None:
        """Rejoue la suite correcte depuis la position juste avant le coup
        faux — coup par coup, LED + son, réplication physique attendue
        entre chaque (même mécanique qu'un coup adverse en partie). Jamais
        appelé pour une victoire (self.outcome == "solved")."""
        self._log("affichage de la solution demandé par l'utilisateur.")
        target_board = chess.Board(self._fail_point_fen)
        self._wait_for_board_fen(target_board.board_fen())
        for i, uci in enumerate(self._fail_remaining):
            try:
                move = target_board.parse_uci(uci)
            except Exception as exc:
                logger.warning("Lichess problème : coup de solution illisible (%s) : %s", uci, exc)
                break
            san = san_ep(target_board, move)
            color = "white" if target_board.turn == chess.WHITE else "black"
            target_board.push(move)
            self._beep()
            self._light_move(move.from_square, move.to_square)
            done = (i == len(self._fail_remaining) - 1)
            send_event("lichess_puzzle_solution_move", {
                "fen": target_board.fen(), "san": san, "uci": uci, "color": color, "done": done,
            })
            self._wait_for_board_fen(target_board.board_fen())
        self._log("solution entièrement rejouée sur l'échiquier.")
