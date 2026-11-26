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

Mode virtuel (issue #364) : VirtualPuzzleGame, en bas de ce fichier, hérite
de PuzzleGame et ne redéfinit QUE ce qui dépendait du plateau physique —
tout le suivi de la solution ci-dessus (y compris le mat hors solution)
reste partagé à l'identique entre les deux modes.
"""

import datetime
import logging
import threading
import time

import chess

from nicsoft.config import LOGS_DIR
from nicsoft.core.ihm_port import send_event, get_action
from nicsoft.engine.board_utils import san_ep
from nicsoft.modes.lichess.game import MOVE_STABLE_DELAY_S, legal_move_for_hardware, pending_promotion_move
from nicsoft.modes.lichess.puzzle_client import submit_puzzle_result
from nicsoft.modes.lichess.puzzle_history import append_puzzle_history

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

    def __init__(self, nl_inst, token: str, puzzle: dict, player_name: str = "", game_log=None,
                 series_theme: str = "", series_type: str = "mix"):
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
        # Issue #387, point 2 : thème/angle de la série de la séance à
        # laquelle appartient ce problème — vide tant qu'aucun choix de
        # thème n'existe (comportement actuel, inchangé par cette issue).
        # Reporté dans l'historique local (_record_history ci-dessous),
        # jamais utilisé pour demander un problème d'un thème particulier
        # (get_next_puzzle, puzzle_client.py, n'est pas modifié ici).
        self.series_theme = series_theme
        # Issue #390, point 2 : forme explicite et sans ambiguïté du type
        # de série ("theme"/"phase"/"mix") — reportée dans l'historique
        # local (_record_history) pour le compteur du jour par type
        # (voir puzzle_history.daily_counts_by_type) ; "mix" par défaut,
        # jamais levé d'exception sur une valeur inattendue.
        self.series_type = series_type if series_type in ("theme", "phase", "mix") else "mix"

        self.solved_index = 0
        self.outcome = None          # None | "solved" | "failed"
        self.back_menu_requested = False
        # Issue #387, point 1 : chronométré dès la construction (position
        # de départ déjà confirmée par l'appelant à cet instant, voir
        # game_manager_modes/lichess.py) jusqu'à _finish() — sert à la
        # fois à l'historique local (duration_s) et au bilan de séance.
        self._start_ts = time.monotonic()
        self.duration_s = None

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
        # Issue #386 : coup légal détecté en attente de stabilité (voir
        # _move_is_stable, même mécanisme que LichessGame, game.py).
        self._pending_move_fen = None
        self._pending_move_since = 0.0

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
            self._pending_move_fen = None
            return
        promo = pending_promotion_move(self.board, hw_fen)
        if promo is not None:
            from_sq, to_sq = promo
            self._pending_move_fen = None
            self._pending_promotion = (from_sq, to_sq)
            send_event("lichess_puzzle_promotion_needed", {
                "from": chess.square_name(from_sq), "to": chess.square_name(to_sq),
            })
            return
        move = legal_move_for_hardware(self.board, hw_fen)
        if move is not None:
            if not self._move_is_stable(hw_fen):
                return
            self._pending_move_fen = None
            self._evaluate_user_move(move)
            return
        self._pending_move_fen = None
        self._handle_illegal(hw_fen)

    def _move_is_stable(self, hw_fen: str) -> bool:
        """Issue #386 — même mécanisme que LichessGame._move_is_stable
        (game.py) : exige MOVE_STABLE_DELAY_S de lecture ininterrompue de
        `hw_fen` avant d'accepter le coup légal qu'elle représente, pour ne
        pas valider un coup glissé sur sa case intermédiaire."""
        now = time.monotonic()
        if hw_fen != self._pending_move_fen:
            self._pending_move_fen = hw_fen
            self._pending_move_since = now
            return False
        return now - self._pending_move_since >= MOVE_STABLE_DELAY_S

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

    def _on_solution_rewind(self, target_board: chess.Board) -> None:
        """Point d'extension (issue #364) appelé juste avant d'attendre la
        remise en place de la position d'avant le coup faux — no-op en mode
        échiquier (le joueur reconstruit lui-même cette position
        physiquement, voir _wait_for_board_fen juste après) ; VirtualPuzzleGame
        le surcharge pour l'afficher à l'écran, où rien d'autre ne le ferait."""

    # ── Fin de problème — envoi du résultat ─────────────────────────────

    def _finish(self, win: bool) -> None:
        self.outcome = "solved" if win else "failed"
        self.duration_s = time.monotonic() - self._start_ts
        self._pending_submit = {"win": win}
        self._log(f"problème résolu — issue={self.outcome}, résultat en attente d'envoi (classé).")
        self._try_submit_pending()
        self._record_history()

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

    def _record_history(self) -> None:
        """Issue #387, point 1 : un enregistrement par problème TERMINÉ
        (résultat connu — jamais appelé pour un abandon, voir
        _process_browser_actions/run() : "back_menu" sans passer par
        _finish ne consigne rien). Écrit une seule fois, juste après le
        PREMIER essai d'envoi (réussi ou non) — un réessai ultérieur
        (lichess_puzzle_retry_submit) ne réécrit jamais cette ligne, voir
        le rapport de clôture. Jamais le jeton ni aucune information
        d'authentification ici (absents des champs ci-dessous)."""
        append_puzzle_history({
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "puzzle_id": self.puzzle_id,
            "series_theme": self.series_theme,
            "series_type": self.series_type,
            "setup_fen": self.setup_fen,
            "themes": self.themes,
            "win": self.outcome == "solved",
            "duration_s": round(self.duration_s, 2) if self.duration_s is not None else None,
            "rating_before": self.rating_before,
            "rating_after": self.rating_after,
            "rating_diff": self.rating_diff,
            "submit_ok": self._submit_error_key is None,
        })

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
        self._on_solution_rewind(target_board)
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


# ── Mode virtuel (jouer à l'écran, sans échiquier physique) — issue #364 ────
#
# VirtualPuzzleGame hérite de PuzzleGame et réutilise tel quel tout ce qui ne
# dépend pas du plateau physique : suivi de la solution, détection
# résolu/raté, mat hors solution accepté (_evaluate_user_move), envoi unique
# du résultat (_finish/_try_submit_pending), journal, enchaînement
# ("Voir la solution"/"Problème suivant"/retour au menu) via
# _wait_post_result_decision — AUCUNE de ces méthodes n'est redéfinie ici.
# Seules les méthodes qui touchaient le plateau physique sont remplacées :
# _tick_physical/_light_move/_beep (no-op : rien à lire ni à éclairer),
# _wait_for_board_fen (devient une courte pause interruptible par retour au
# menu — sert à la fois de délai avant le coup adverse affiché, de délai
# entre la réponse du joueur et la réponse adverse forcée, et de délai entre
# chaque coup de "Voir la solution") et _process_browser_actions (ajoute le
# traitement du coup venu du navigateur, déjà complet — départ, arrivée,
# pièce de promotion si besoin — donc jamais besoin du mécanisme
# _pending_promotion/lichess_puzzle_promotion_needed, réservé à
# l'ambiguïté propre à un plateau physique).

_VIRTUAL_PAUSE_S = 0.6
_VIRTUAL_PAUSE_STEP_S = 0.05


def _legal_moves_map(board: chess.Board) -> dict:
    """Coups légaux de `board`, regroupés par case de départ (notation
    algébrique) — jamais calculés par un moteur, seulement par
    python-chess (`board.legal_moves`), déjà la bibliothèque utilisée pour
    toute validation côté serveur dans ce module. Les coups de promotion
    (quatre entrées UCI pour la même case d'arrivée) sont fusionnés en une
    seule destination : le choix de la pièce est un geste distinct côté
    écran (sélecteur affiché une fois la case d'arrivée cliquée), pas une
    case supplémentaire à marquer."""
    moves: dict = {}
    for mv in board.legal_moves:
        frm = chess.square_name(mv.from_square)
        to = chess.square_name(mv.to_square)
        dests = moves.setdefault(frm, [])
        if to not in dests:
            dests.append(to)
    return moves


class VirtualPuzzleGame(PuzzleGame):
    """Variante écran (sans échiquier physique) d'un problème Lichess —
    voir l'en-tête de section ci-dessus pour ce qui est réutilisé tel quel
    depuis PuzzleGame. `nl_inst` n'est jamais utilisé par les méthodes
    surchargées ci-dessous : l'appelant (_run_lichess_puzzle_virtual,
    game_manager_modes/lichess.py) construit cette classe avec `nl_inst=None`."""

    def _tick_physical(self) -> None:
        pass

    def _light_move(self, from_square, to_square) -> None:
        pass

    def _beep(self) -> None:
        pass

    def _wait_for_board_fen(self, target_board_fen: str) -> None:
        """Aucune réplication physique à attendre (la position affichée à
        l'écran est toujours exacte) — devient une courte pause,
        interrompue immédiatement par un retour au menu (même garde que la
        version physique : _drain_back_menu_only, _BackMenuDuringPuzzle)."""
        waited = 0.0
        while waited < _VIRTUAL_PAUSE_S:
            if self._drain_back_menu_only():
                raise _BackMenuDuringPuzzle()
            time.sleep(_VIRTUAL_PAUSE_STEP_S)
            waited += _VIRTUAL_PAUSE_STEP_S

    def _on_solution_rewind(self, target_board: chess.Board) -> None:
        """Rien d'autre n'afficherait la position d'avant le coup faux à
        l'écran (pas de plateau physique que le joueur remettrait lui-même
        en place) — même évènement que pour un coup joué, sans coup à
        marquer (uci omis, déjà un cas géré par app.js::_renderLichessPuzzleBoard)."""
        send_event("lichess_puzzle_move", {"fen": target_board.fen()})

    def animate_opponent_first_move(self) -> None:
        super().animate_opponent_first_move()
        if self.outcome is None:
            self._send_your_turn()

    def _evaluate_user_move(self, move: chess.Move) -> None:
        super()._evaluate_user_move(move)
        if self.outcome is None:
            self._send_your_turn()

    def _send_your_turn(self) -> None:
        """Signale au navigateur que c'est au joueur de jouer et lui fournit
        les coups légaux de la position courante (issue #364 : "les coups
        légaux sont fournis par le serveur, jamais calculés avec un
        moteur") — jamais envoyé en mode échiquier (évènement propre à ce
        module, nouveau, avec son gestionnaire JS dédié, garde #359)."""
        send_event("lichess_puzzle_your_turn", {"legal_moves": _legal_moves_map(self.board)})

    def _process_browser_actions(self) -> bool:
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
            if atype == "lichess_puzzle_virtual_move":
                self._handle_virtual_move(action)

    def _handle_virtual_move(self, action: dict) -> None:
        if self.outcome is not None:
            return
        from_sq = (action.get("from") or "").strip().lower()
        to_sq = (action.get("to") or "").strip().lower()
        promotion = (action.get("promotion") or "").strip().lower()
        promotion = promotion if promotion in ("q", "r", "b", "n") else ""
        uci = from_sq + to_sq + promotion
        try:
            move = self.board.parse_uci(uci)
        except Exception:
            move = None
        if move is None or move not in self.board.legal_moves:
            self._log(f"coup virtuel illégal refusé — {from_sq}{to_sq}{promotion} (aucune pénalité).")
            send_event("lichess_puzzle_virtual_illegal", {"from": from_sq, "to": to_sq})
            return
        self._evaluate_user_move(move)
