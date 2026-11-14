"""
nicsoft/modes/lichess/game.py — AlChess

Issue #309 (étape L2a) : boucle de jeu d'une partie amicale contre l'IA de
Lichess, jouée sur l'échiquier physique. Aucun moteur, aucune aide : ce
module n'importe jamais nicsoft.engine.engine_manager ni aucun moteur UCI
(règle de fair-play Lichess — voir CLAUDE.md).

État de la partie : l'état de vérité vient de Lichess (liste de coups UCI
du flux de jeu) ; `self.board` est reconstruit à partir de cette liste à
chaque événement, jamais poussé de façon optimiste depuis un coup physique
avant confirmation.

Deux threads par partie :
  - celui qui exécute `run()` (boucle principale, non bloquante : actions
    navigateur, événements Lichess, lecture plateau physique) ;
  - un thread de lecture du flux (`_stream_reader_loop`), qui alimente une
    file d'événements — jamais de blocage réseau pendant que l'utilisateur
    réfléchit à son coup (aucune limite de temps côté AlChess).
"""

import datetime
import logging
import queue
import threading
import time

import chess

from nicsoft.core.ihm_port import send_event, get_action, set_app_state
from nicsoft.engine.board_utils import san_ep
from nicsoft.engine.pgn_manager import build_and_save_pgn, build_final_path
from nicsoft.modes.lichess.errors import (
    LichessApiError,
    LichessAuthError,
    LichessNetworkError,
    LichessRateLimitError,
)
from nicsoft.modes.lichess.game_client import is_game_over, moves_from_state, side_to_move

logger = logging.getLogger("niclink.lichess")

_FINISHED_WITH_WINNER = frozenset({
    "mate", "resign", "timeout", "outoftime", "cheat", "variantEnd", "unknownFinish",
})
_FINISHED_DRAW = frozenset({"draw", "stalemate", "insufficientMaterialClaim"})

_OTHER_MODE_ACTIONS = frozenset({
    "mode", "start", "start_humain", "start_retranscription", "start_lichess",
    "start_exercice", "start_drill",
})

# Statuts de fin de partie non demandés par l'utilisateur et jamais
# silencieux (issue #311, point 3) — _request_resign_or_abort() (abandon/
# annulation voulus par l'utilisateur) en est exclu via _user_initiated_end.
_UNEXPECTED_END_STATUSES = frozenset({"aborted", "noStart", "unknownFinish"})
_ABORT_CAUSE_KEYS = {
    "aborted": "lichess.annulee_premier_coup_trop_tard",
}
_ABORT_CAUSE_DEFAULT_KEY = "lichess.annulee_cause_inconnue"


# ── Fonctions pures ──────────────────────────────────────────────────────────

def legal_move_for_hardware(board: chess.Board, hardware_board_fen: str):
    """Coup légal (hors promotion) dont la position d'arrivée correspond à
    `hardware_board_fen`, ou None. Les promotions sont gérées séparément
    (choix explicite de la pièce côté navigateur — voir pending_promotion_move)."""
    for move in board.legal_moves:
        if move.promotion is not None:
            continue
        test = board.copy(stack=False)
        test.push(move)
        if test.board_fen() == hardware_board_fen:
            return move
    return None


def pending_promotion_move(board: chess.Board, hardware_board_fen: str):
    """Retourne (from_square, to_square) si la position physique correspond
    à une promotion en attente de choix de pièce : toutes les cases hors
    départ/arrivée correspondent, le départ est vide côté physique, et
    l'arrivée porte n'importe quelle pièce du bon camp (le plateau physique
    ne permet pas de distinguer la pièce choisie — on la demande à l'écran).
    None si aucune promotion en attente."""
    try:
        hw = chess.Board(hardware_board_fen + " w - - 0 1")
    except ValueError:
        return None
    promotion_from_to = set()
    for move in board.legal_moves:
        if move.promotion is not None:
            promotion_from_to.add((move.from_square, move.to_square))
    for from_sq, to_sq in promotion_from_to:
        matches = True
        for sq in chess.SQUARES:
            if sq in (from_sq, to_sq):
                continue
            if board.piece_at(sq) != hw.piece_at(sq):
                matches = False
                break
        if not matches:
            continue
        if hw.piece_at(from_sq) is not None:
            continue
        dest_piece = hw.piece_at(to_sq)
        mover_color = board.piece_at(from_sq).color
        if dest_piece is None or dest_piece.color != mover_color:
            continue
        return from_sq, to_sq
    return None


def compute_clock_ms(white_ms: float, black_ms: float, turn_color: str, elapsed_s: float) -> tuple:
    """Temps restant (ms) pour chaque camp, `elapsed_s` secondes après le
    dernier recalage reçu de Lichess — déduit du seul camp au trait.
    Fonction pure : l'affichage se recalcule à partir d'heures, jamais par
    accumulation d'un minuteur JS (issue #309, point 4)."""
    elapsed_ms = max(0.0, elapsed_s) * 1000.0
    if turn_color == "black":
        return white_ms, max(0.0, black_ms - elapsed_ms)
    return max(0.0, white_ms - elapsed_ms), black_ms


def pgn_result(status: str, winner: str) -> str:
    """Score PGN ("1-0"/"0-1"/"1/2-1/2"/"*") déduit du statut Lichess."""
    if status in _FINISHED_WITH_WINNER and winner:
        return "1-0" if winner == "white" else "0-1"
    if status in _FINISHED_DRAW:
        return "1/2-1/2"
    return "*"


def pgn_time_control(clock_limit_s: int, clock_increment_s: int) -> str:
    return f"{clock_limit_s}+{clock_increment_s}"


def first_move_deadline_s(expiration: dict, elapsed_s: float):
    """Secondes restantes avant l'annulation Lichess du premier coup,
    lues dans le champ `expiration` (idleMillis/millisToMove) d'un message
    de partie — None si absent (issue #311, point 2)."""
    if not expiration:
        return None
    millis = expiration.get("millisToMove")
    if millis is None:
        return None
    return max(0.0, millis / 1000.0 - max(0.0, elapsed_s))


# Reproduction de modules/game/src/main/Game.scala::timeForFirstMove (lila,
# branche master lue le 2026-11-13 via `gh search code`/`curl raw.githubusercontent.com`)
# — délai (hors tournoi, variante standard) avant annulation automatique du
# premier coup, selon la cadence déduite de chess.Speed (scalachess,
# core/src/main/scala/Speed.scala::byTime, bornes en secondes). Utilisé
# UNIQUEMENT quand Lichess n'envoie pas le champ `expiration` (issue #321,
# point 6) ET pour une partie contre un humain seulement (issue #322, point
# 1 : contre son IA, Lichess ne menace jamais d'annulation du premier coup
# ni n'en affiche de décompte — confirmé par l'essai réel d'Alain du
# 13/11/2026, partie non annulée après plus de 28s) : l'estimation reste
# approximative (dépend du code Lichess au moment de la lecture, non
# versionné ici) — jamais présentée comme exacte côté interface (voir
# app.js, "premier_coup_decompte_estime").
_FIRST_MOVE_TIMEOUT_BY_SPEED = {
    "ultraBullet": 15.0, "bullet": 20.0, "blitz": 25.0, "rapid": 30.0,
}
_FIRST_MOVE_TIMEOUT_DEFAULT_S = 35.0  # classical / correspondence


def speed_key_for_clock(clock_limit_s: int, clock_increment_s: int) -> str:
    """Catégorie de cadence Lichess (chess.Speed::byTime) déduite du temps
    total estimé (limite + 40 × incrément, comme Clock.Config::
    estimateTotalSeconds côté scalachess)."""
    estimate_s = clock_limit_s + 40 * clock_increment_s
    if estimate_s < 30:
        return "ultraBullet"
    if estimate_s < 180:
        return "bullet"
    if estimate_s < 480:
        return "blitz"
    if estimate_s < 1500:
        return "rapid"
    return "classical"


def estimated_first_move_deadline_s(clock_limit_s: int, clock_increment_s: int) -> float:
    """Estimation locale (jamais envoyée par Lichess) du délai avant
    annulation automatique du premier coup — voir _FIRST_MOVE_TIMEOUT_BY_SPEED
    ci-dessus pour la source. Toujours présentée comme approximative côté
    interface (issue #321, point 6)."""
    return _FIRST_MOVE_TIMEOUT_BY_SPEED.get(
        speed_key_for_clock(clock_limit_s, clock_increment_s), _FIRST_MOVE_TIMEOUT_DEFAULT_S,
    )


def _differing_squares(fen_a: str, fen_b: str) -> list:
    """Cases (algébriques) où la pièce diffère entre deux FEN board-only —
    utilisé pour guider par LED la reconstruction de position d'une partie
    reprise (issue #323, point 3). Variante locale de ce que
    game_manager_modes/lichess.py appelle _squares_differing — dupliquée
    plutôt qu'importée pour éviter un import circulaire (ce module-ci est
    déjà importé par game_manager_modes/lichess.py)."""
    try:
        a = chess.Board(fen_a + " w - - 0 1")
        b = chess.Board(fen_b + " w - - 0 1")
    except ValueError:
        return []
    return [chess.square_name(sq) for sq in chess.SQUARES if a.piece_at(sq) != b.piece_at(sq)]


def opponent_pgn_name(level: int) -> str:
    """Nom de l'adversaire pour les en-têtes PGN — convention Lichess,
    jamais vide ni « None » (issue #309, point 2)."""
    return f"Lichess AI level {level}"


def build_pgn_headers(game_id: str, user_name: str, user_color: str, level: int,
                       clock_limit_s: int, clock_increment_s: int, result: str,
                       date_utc: str) -> dict:
    ai_name = opponent_pgn_name(level)
    user_name = user_name or "Vous"
    white = user_name if user_color == "white" else ai_name
    black = ai_name if user_color == "white" else user_name
    return {
        "Event": f"Lichess, amicale contre l'IA niveau {level}",
        "Site": f"https://lichess.org/{game_id}",
        "Date": date_utc,
        "White": white,
        "Black": black,
        "Result": result,
        "TimeControl": pgn_time_control(clock_limit_s, clock_increment_s),
    }


# ── Boucle de jeu ────────────────────────────────────────────────────────────

class LichessGame(threading.Thread):
    """Partie amicale contre l'IA de Lichess sur l'échiquier physique.
    `start()` exécute `run()` de façon synchrone (comme GameWeb — le vrai
    threading vit dans le lanceur, voir game_manager_modes/lichess.py)."""

    POLL_DELAY_S = 0.05
    CLOCK_PUSH_INTERVAL_S = 1.0
    BOARD_LOST_STRIKES = 40           # ~2s de lectures en échec consécutives
    POSITION_ERROR_THROTTLE_S = 1.0
    ILLEGAL_STABLE_READS_REQUIRED = 8
    # Reconnexion automatique en cours de partie (issue #314, point 2) :
    # jamais d'abandon automatique, cadence 2s pendant 30s puis 5s.
    RECONNECT_FAST_INTERVAL_S = 2.0
    RECONNECT_FAST_DURATION_S = 30.0
    RECONNECT_SLOW_INTERVAL_S = 5.0

    def __init__(self, nl_inst, client, game_id: str, level: int, player_name: str,
                 clock_limit_s: int, clock_increment_s: int,
                 chosen_color_setting: str = "random", cadence_key: str = "",
                 resuming: bool = False,
                 initial_wtime_ms: float = None, initial_btime_ms: float = None,
                 clock_known: bool = True, **kwargs):
        super().__init__(daemon=True, **kwargs)
        self.nl_inst = nl_inst
        self.client = client
        self.game_id = game_id
        self.level = level
        self.player_name = player_name or "Vous"
        self.clock_limit_s = clock_limit_s
        self.clock_increment_s = clock_increment_s
        # Réglages d'origine (avant résolution de la couleur aléatoire) —
        # réutilisés par "Rejouer avec les mêmes réglages" (issue #311,
        # point 3), jamais pour la logique de la partie elle-même.
        self.chosen_color_setting = chosen_color_setting or "random"
        self.cadence_key = cadence_key

        self.board = chess.Board()
        self.user_color = None
        self.game_over = False

        self._moves_applied = 0
        self._status = "created"
        self._winner = ""
        self._aborted = False
        self._user_initiated_end = False
        self._back_menu_requested = False

        self._board_lost = False
        self._board_lost_strikes = 0
        self._board_lost_since = None
        self._next_reconnect_attempt_ts = 0.0
        self._reconnecting_in_progress = False

        self._awaiting_physical_replication = False
        self._replication_target_fen = None
        self._awaiting_piece_reset = False
        self._reset_target_fen = None
        self._pending_promotion = None
        self._last_position_error_ts = 0.0
        self._last_illegal_fen = None
        self._illegal_stable_count = 0
        self._illegal_position_active = False
        self._last_illegal_position_sent_fen = None

        # Boutons Abandonner/Proposer nulle (issue #321, point 1) : état
        # (resign_enabled, draw_enabled) poussé côté interface par
        # _sync_turn_ready() à chaque changement — jamais recalculé côté
        # navigateur, pour que les exceptions de sécurité (point 2) restent
        # cohérentes avec la seule source de vérité du déroulement de la
        # partie (ce thread).
        self._action_buttons_state = (False, False)

        self._draw_offered_by_opponent = False
        self._my_draw_offer_pending = False

        # Reprise d'une partie en cours (issue #323) : tant que
        # _resume_pending est vrai, _tick_physical() n'attend ni coup
        # adverse à reproduire ni coup utilisateur — il affiche l'écran de
        # mise en place (cases rouges + LED) jusqu'à ce que la position
        # physique corresponde à self.board (recalculée à chaque tick, donc
        # toujours à jour même si l'adversaire joue pendant la
        # reconstruction — voir _tick_resume_setup). Jamais vrai pour une
        # partie lancée normalement (launch_lichess).
        self._resume_pending = resuming
        self._resume_setup_active = False
        self._resume_led_squares = []

        # Déduit de la présence d'`aiLevel` (voir _apply_game_full) — vrai
        # dans toute partie lancée par AlChess aujourd'hui (seul "contre
        # l'IA" existe), prêt pour un futur mode contre un humain (issue
        # #322, point 1) : Lichess n'affiche ni menace d'annulation ni
        # décompte du premier coup contre son IA, contrairement à une
        # partie contre un humain.
        self._opponent_is_ai = True

        self._first_move_expiration = None
        self._first_move_expiration_ref = time.monotonic()
        self._first_move_deadline_active = False
        # Non None seulement quand Lichess n'envoie pas `expiration` ET que
        # l'adversaire n'est pas l'IA (issue #321 point 6, restreint par
        # l'issue #322 point 1) — estimation locale, jamais présentée comme
        # exacte.
        self._first_move_deadline_estimate_total_s = None
        self._last_move_event_ts = time.monotonic()

        # Valeur de départ des pendules (issue #325, point 7) : pour une
        # reprise, `initial_wtime_ms`/`initial_btime_ms` (temps RESTANT réel,
        # lu dans l'aperçu gameFull — voir game_manager_modes/lichess.py)
        # sont préférés à clock_limit_s (temps de DÉPART de la cadence,
        # jamais le temps restant) — sans quoi la pendule afficherait la
        # cadence complète (ou 0, si clock_limit_s vaut 0 par défaut
        # silencieux faute de champ `clock`) au lieu du temps réellement
        # restant, jusqu'à la correction par le premier événement du flux
        # (quasi immédiate pour une partie normale, mais jamais si cet
        # événement manque lui aussi de wtime/btime — voir _clock_known).
        if initial_wtime_ms is not None and initial_btime_ms is not None:
            self._clock_white_ms = float(initial_wtime_ms)
            self._clock_black_ms = float(initial_btime_ms)
        else:
            self._clock_white_ms = float(clock_limit_s * 1000)
            self._clock_black_ms = float(clock_limit_s * 1000)
        # Faux seulement quand ni l'aperçu de reprise ni (plus tard) un vrai
        # événement de flux n'ont fourni de wtime/btime fiables (partie par
        # correspondance qui aurait échappé au filtre du point 1, ou réponse
        # Lichess inattendue) : jamais de valeur fausse affichée dans ce cas
        # (voir _maybe_push_clock et app.js::_lichessRenderClock) — on
        # préfère ne rien afficher plutôt qu'un 0:00 mensonger.
        self._clock_known = bool(clock_known)
        self._clock_turn = "white"
        self._clock_ref_monotonic = time.monotonic()
        self._last_clock_push_ts = 0.0
        # Les pendules Lichess restent figées à leur valeur de départ tant
        # que les deux camps n'ont pas chacun joué leur premier coup — jamais
        # décomptées par une minuterie locale avant ça (issue #322, point 2).
        self._clock_running = False

        self._stream_event_queue = queue.Queue()
        self._stream_stop = threading.Event()
        self._stream_error = None

    def start(self):
        self.run()

    def join(self, timeout=None):
        # start() exécute run() de façon synchrone : à son retour la partie
        # est déjà terminée. Le Thread natif n'est jamais démarré (start()
        # ci-dessus ne fait pas appel à Thread.start()) — Thread.join()
        # lèverait donc toujours "cannot join thread before it is started"
        # (issue #310, point 1). No-op défensif : rien à attendre.
        pass

    # ── Boucle principale ────────────────────────────────────────────────

    def run(self):
        reader = threading.Thread(target=self._stream_reader_loop, daemon=True)
        reader.start()
        logger.info("Lichess : flux de partie ouvert (%s).", self.game_id)
        try:
            self._main_loop()
        finally:
            self._stream_stop.set()
            self._finalize()
            try:
                reader.join(timeout=2.0)
            except RuntimeError:
                pass  # jointure best-effort — le thread est daemon de toute façon

    def _main_loop(self):
        while not self.game_over:
            self._process_browser_actions()
            if self.game_over:
                break
            try:
                event = self._stream_event_queue.get(timeout=self.POLL_DELAY_S)
            except queue.Empty:
                event = None
            if event is not None:
                self._handle_stream_event(event)
                if self.game_over:
                    break
            self._tick_physical()
            self._maybe_push_clock()

    def _stream_reader_loop(self):
        try:
            for event in self.client.stream_game(self.game_id):
                self._stream_event_queue.put(event)
                if self._stream_stop.is_set():
                    return
        except (LichessApiError, LichessAuthError, LichessNetworkError, LichessRateLimitError) as exc:
            self._stream_error = exc
        finally:
            self._stream_event_queue.put({"type": "_stream_closed"})

    # ── Actions navigateur ───────────────────────────────────────────────

    def _process_browser_actions(self):
        while True:
            action = get_action(timeout=0.0)
            if action is None:
                return
            atype = action.get("type", "")
            if atype in _OTHER_MODE_ACTIONS:
                send_event("lichess_toast", {"message_key": "lichess.menu_verrouille", "type": "warning"})
                continue
            if atype == "back_menu":
                # Journalisé dès la réception (issue #319, point 3) — l'heure
                # de cette ligne (formateur %(asctime)s, voir alchess.py) est
                # l'instant de la demande, avant l'éventuel appel réseau
                # abort()/resign() fait par _request_resign_or_abort().
                logger.info("Lichess : retour au menu demandé par l'utilisateur (%s).", self.game_id)
                self._back_menu_requested = True
                if not self.game_over:
                    self._request_resign_or_abort(reason="retour au menu demandé par l'utilisateur")
                self.game_over = True
                self._sync_turn_ready()
                continue
            if self.game_over:
                continue
            if atype == "lichess_resign":
                logger.info(
                    "Lichess : abandon demandé par l'utilisateur (bouton Abandonner, %s).",
                    self.game_id,
                )
                if self._request_resign_or_abort(reason="bouton Abandonner demandé par l'utilisateur"):
                    self.game_over = True
                    self._sync_turn_ready()
            elif atype == "lichess_propose_draw":
                if self._safe_client_call(lambda: self.client.answer_draw(self.game_id, True)):
                    self._my_draw_offer_pending = True
                    logger.info("Lichess : nulle proposée par %s.", self.player_name)
                    send_event("lichess_draw_proposed", {})
            elif atype == "lichess_draw_accept":
                self._draw_offered_by_opponent = False
                self._safe_client_call(lambda: self.client.answer_draw(self.game_id, True))
            elif atype == "lichess_draw_refuse":
                self._draw_offered_by_opponent = False
                self._safe_client_call(lambda: self.client.answer_draw(self.game_id, False))
            elif atype == "lichess_promotion_choice" and self._pending_promotion is not None:
                self._submit_promotion(action.get("piece", "q"))

    def _safe_client_call(self, fn) -> bool:
        try:
            fn()
            return True
        except LichessApiError as exc:
            send_event("lichess_move_refused", {"message": exc.api_message or str(exc)})
        except (LichessNetworkError, LichessRateLimitError):
            send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning"})
        return False

    def _request_resign_or_abort(self, reason: str = "demande utilisateur") -> bool:
        """`reason` (issue #319, point 3) : raison écrite dans le journal
        avec le résultat — distincte de l'instant de la demande, déjà
        journalisé par l'appelant (_process_browser_actions) avant l'appel
        réseau abort()/resign() ci-dessous, qui peut prendre du temps."""
        aborting = len(self.board.move_stack) < 2
        if aborting:
            ok = self._safe_client_call(lambda: self.client.abort(self.game_id))
        else:
            ok = self._safe_client_call(lambda: self.client.resign(self.game_id))
        if not ok:
            return False
        self._user_initiated_end = True
        if aborting:
            self._status = "aborted"
            self._aborted = True
            logger.info(
                "Lichess : partie annulée (%s, moins de 2 coups) — raison : %s.",
                self.game_id, reason,
            )
        else:
            self._status = "resign"
            self._winner = "black" if self.user_color == "white" else "white"
            logger.info(
                "Lichess : abandon par %s (%s) — raison : %s.",
                self.player_name, self.game_id, reason,
            )
        return True

    # ── Événements Lichess ───────────────────────────────────────────────

    def _handle_stream_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "_stream_closed":
            self._handle_stream_closed()
        elif etype == "reconnecting":
            logger.info("Lichess : reconnexion au flux (tentative %s).", event.get("attempt", 1))
            send_event("lichess_reconnecting", {"attempt": event.get("attempt", 1)})
        elif etype == "reconnected":
            logger.info("Lichess : flux reconnecté.")
            send_event("lichess_reconnected", {})
        elif etype == "gameFull":
            self._apply_game_full(event)
        elif etype == "gameState":
            self._apply_game_state(event)
        # chatLine / opponentGone : rien à afficher à cette étape.

    def _handle_stream_closed(self) -> None:
        if self.game_over:
            return
        if self._stream_error is not None:
            send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning"})
        if self._status in ("created", "started"):
            self._status = "unknownFinish"
        self.game_over = True
        self._sync_turn_ready()

    def _log_game_state_received(self, state: dict) -> None:
        """Journal de diagnostic (issue #318) : rien de secret ici — statut,
        nombre de coups et les deux indicateurs de nulle bruts envoyés par
        Lichess, pour pouvoir confirmer a posteriori ce qu'il envoie
        réellement juste après notre propre coup. `expiration` (issue #321,
        point 6) est journalisé brut, présent ou non, pour savoir si/quand
        Lichess l'envoie réellement — observé absent lors de l'essai réel
        d'Alain du 13/11/2026 ayant motivé l'estimation locale de repli."""
        logger.info(
            "Lichess : état reçu (coups=%d, statut=%s, wdraw=%s, bdraw=%s, expiration=%s).",
            len(moves_from_state(state)),
            state.get("status", self._status),
            bool(state.get("wdraw")),
            bool(state.get("bdraw")),
            state.get("expiration"),
        )

    def _apply_game_full(self, event: dict) -> None:
        white = event.get("white") or {}
        black = event.get("black") or {}
        if white.get("aiLevel") is not None:
            self.user_color = "black"
            self.level = white.get("aiLevel", self.level)
        else:
            self.user_color = "white"
            self.level = black.get("aiLevel", self.level)
        # issue #322, point 1 : seule l'absence totale d'`aiLevel` des deux
        # côtés (futur mode contre un humain) désactive la menace
        # d'annulation/le décompte du premier coup propres à Lichess contre
        # un humain — toute partie AlChess actuelle en a un.
        self._opponent_is_ai = white.get("aiLevel") is not None or black.get("aiLevel") is not None
        state = event.get("state") or {}
        self._log_game_state_received(state)
        self.board = chess.Board()
        self._moves_applied = 0
        self._apply_new_moves(state, initial=True)
        # Coups déjà joués avant même l'écran de jeu (issue #325, point 5) —
        # jamais vide pour une reprise : auparavant, lichess_init ne portait
        # pas l'historique et l'écran l'effaçait (voir app.js), laissant
        # l'historique vide pendant toute la mise en place. Sans effet pour
        # une partie normale (toujours vide à ce stade, hors noirs après le
        # premier coup de l'IA).
        hist_fens, hist_moves = self._history_from_board()
        send_event("lichess_init", {
            "fen": self.board.board_fen(),
            "color": self.user_color,
            "player": self.player_name,
            "level": self.level,
            "clock_limit_s": self.clock_limit_s,
            "clock_increment_s": self.clock_increment_s,
            "history_fen": hist_fens,
            "history_moves": hist_moves,
        })
        self._reset_clock_from_state(state)
        if self.user_color == "black" and self._moves_applied >= 1:
            # L'IA (blancs) a déjà joué son premier coup dès la création de
            # la partie — signal sonore de l'échiquier en plus des LED du
            # coup et du compte à rebours (issue #311, point 1).
            try:
                self.nl_inst.beep()
            except Exception as exc:
                logger.debug("Signal sonore (premier coup IA, Lichess) échoué : %s", exc)
        self._maybe_activate_first_move_deadline(state)
        self._check_finished(state.get("status", "started"), state.get("winner", ""))
        self._sync_turn_ready()

    def _apply_game_state(self, event: dict) -> None:
        self._log_game_state_received(event)
        last_mover_color = self._apply_new_moves(event)
        self._reset_clock_from_state(event)
        self._maybe_activate_first_move_deadline(event)
        opponent_offered = event.get("bdraw") if self.user_color == "white" else event.get("wdraw")
        opponent_offered = bool(opponent_offered)
        if opponent_offered != self._draw_offered_by_opponent:
            self._draw_offered_by_opponent = opponent_offered
            if opponent_offered:
                logger.info("Lichess : nulle proposée par l'adversaire.")
            send_event("lichess_draw_offered", {"offered": opponent_offered})
        status = event.get("status", self._status)
        # Une offre de nulle de l'utilisateur n'est considérée comme
        # refusée que si l'adversaire a joué un coup sans l'accepter —
        # jamais sur l'écho de notre propre coup (issue #318 : un faux
        # refus était affiché dès la confirmation de notre coup, avant
        # toute réponse réelle de l'adversaire). Lichess n'offre pas
        # d'autre signal explicite de refus observable côté Board API
        # (vérifié dans la spec officielle lichess-org/api et le source de
        # BotPlayer.scala — voir rapport de clôture) : ce coup adverse non
        # suivi d'une acceptation est donc le seul signal fiable dont nous
        # disposons.
        opponent_just_moved = last_mover_color is not None and last_mover_color != self.user_color
        if self._my_draw_offer_pending and not is_game_over(status) and opponent_just_moved:
            my_offered = event.get("wdraw") if self.user_color == "white" else event.get("bdraw")
            if not bool(my_offered):
                self._my_draw_offer_pending = False
                logger.info(
                    "Lichess : nulle refusée (proposée par %s, adversaire a joué sans accepter).",
                    self.player_name,
                )
                send_event("lichess_draw_refused", {})
        self._check_finished(status, event.get("winner", ""))
        self._sync_turn_ready()

    def _check_finished(self, status: str, winner: str) -> None:
        if self.game_over or not is_game_over(status):
            return
        if self._my_draw_offer_pending and status in _FINISHED_DRAW:
            # Notre propre offre a mené à la nulle (acceptée par
            # l'adversaire) — état distinct du refus, affiché avant l'écran
            # de fin de partie (issue #316, point 1).
            self._my_draw_offer_pending = False
            logger.info("Lichess : nulle acceptée (proposée par %s).", self.player_name)
            send_event("lichess_draw_accepted", {})
        self._status = status
        self._winner = winner
        self._aborted = status == "aborted"
        self.game_over = True
        self._sync_turn_ready()

    def _apply_new_moves(self, state: dict, initial: bool = False):
        """Applique les coups non encore vus. Retourne la couleur de
        l'auteur du dernier coup nouvellement appliqué (None si aucun) —
        utilisé par _apply_game_state() pour distinguer l'écho de notre
        propre coup d'un vrai coup de l'adversaire (issue #318)."""
        moves = moves_from_state(state)
        if len(moves) <= self._moves_applied:
            return None
        new_moves = moves[self._moves_applied:]
        last_mover_color = None
        for idx, uci in enumerate(new_moves, start=self._moves_applied):
            mover_color = "white" if idx % 2 == 0 else "black"
            try:
                move = chess.Move.from_uci(uci)
                san = san_ep(self.board, move) if move in self.board.legal_moves else uci
                self.board.push(move)
            except (ValueError, AssertionError) as exc:
                logger.warning("Coup Lichess inattendu (%s) ignoré : %s", uci, exc)
                continue
            last_mover_color = mover_color
            if not initial:
                now = time.monotonic()
                elapsed_ms = int((now - self._last_move_event_ts) * 1000)
                self._last_move_event_ts = now
                logger.info("Lichess : coup reçu %s (%s, délai %d ms).", uci, mover_color, elapsed_ms)
                send_event("lichess_move", {
                    "fen": self.board.board_fen(), "san": san, "uci": uci,
                    "color": mover_color, "level": self.level,
                    "opponent_move": mover_color != self.user_color,
                })
        self._moves_applied = len(moves)
        if last_mover_color is None:
            return None
        if last_mover_color != self.user_color:
            self._start_opponent_replication_wait(new_moves[-1])
        else:
            self._awaiting_piece_reset = False
            if self._first_move_deadline_active:
                self._first_move_deadline_active = False
                self._first_move_deadline_estimate_total_s = None
                send_event("lichess_first_move_deadline", {"active": False})
        return last_mover_color

    def _first_move_deadline_seconds_and_estimated(self, elapsed_s: float):
        """Secondes restantes et indicateur « estimation » (issue #321,
        point 6) — exact si Lichess envoie `expiration`, sinon déduit de
        `_FIRST_MOVE_TIMEOUT_BY_SPEED` (voir estimated_first_move_deadline_s,
        jamais présenté comme exact côté interface)."""
        seconds = first_move_deadline_s(self._first_move_expiration, elapsed_s)
        if seconds is not None:
            return seconds, False
        if self._first_move_deadline_estimate_total_s is None:
            return None, False
        return max(0.0, self._first_move_deadline_estimate_total_s - elapsed_s), True

    def _maybe_activate_first_move_deadline(self, state: dict) -> None:
        """Compte à rebours du premier coup de l'utilisateur (noirs) après
        création de la partie — lu dans le champ `expiration` de Lichess,
        ou, en son absence, estimé localement depuis la cadence pour une
        partie contre un humain seulement (issue #321, point 6 — observé
        absent lors de l'essai réel d'Alain du 13/11/2026 ayant motivé
        cette estimation de repli). Contre l'IA de Lichess, sans
        `expiration` explicite, aucune estimation locale n'est faite :
        Lichess n'y menace jamais d'annulation ni n'y affiche de décompte
        (issue #322, point 1 — confirmé par l'essai réel d'Alain du
        13/11/2026, partie non annulée après plus de 28s contre l'IA)."""
        if self._first_move_deadline_active or self.game_over:
            return
        if self.user_color != "black" or self._moves_applied != 1:
            return
        expiration = (state or {}).get("expiration")
        self._first_move_expiration = expiration
        self._first_move_expiration_ref = time.monotonic()
        if expiration or self._opponent_is_ai:
            self._first_move_deadline_estimate_total_s = None
        else:
            self._first_move_deadline_estimate_total_s = estimated_first_move_deadline_s(
                self.clock_limit_s, self.clock_increment_s,
            )
        self._first_move_deadline_active = True
        seconds, estimated = self._first_move_deadline_seconds_and_estimated(0.0)
        logger.info(
            "Lichess : compte à rebours premier coup activé (adversaire_ia=%s, expiration=%s, "
            "estimation=%s, secondes≈%s).",
            self._opponent_is_ai, expiration, estimated, seconds,
        )
        send_event("lichess_first_move_deadline", {
            "active": True, "seconds": seconds, "estimated": estimated,
        })

    def _reset_clock_from_state(self, state: dict) -> None:
        wtime = state.get("wtime")
        btime = state.get("btime")
        if wtime is None or btime is None:
            return
        self._clock_white_ms = float(wtime)
        self._clock_black_ms = float(btime)
        if not self._clock_known:
            logger.info("Lichess : temps restant confirmé par le flux (%s) — plus affiché comme inconnu.", self.game_id)
        self._clock_known = True
        self._clock_turn = side_to_move(state)
        self._clock_ref_monotonic = time.monotonic()
        # Lichess laisse les deux pendules figées à leur valeur de départ
        # jusqu'à ce que chaque camp ait joué son propre premier coup (le
        # champ `expiration`/`millisToMove` ci-dessus régit ce premier coup
        # à part, hors de wtime/btime — confirmé par l'essai réel d'Alain du
        # 13/11/2026 : 15:00 encore figé côté noirs juste après 1.e4, pour
        # une partie comme pour une IA) — jamais de décompte local avant la
        # 2e paire de coups (issue #322, point 2).
        was_running = self._clock_running
        self._clock_running = self._moves_applied >= 2
        if self._clock_running and not was_running:
            logger.info(
                "Lichess : pendules commencent à décompter après les premiers coups des "
                "deux camps (blancs=%s, noirs=%s, trait=%s).",
                self._clock_white_ms, self._clock_black_ms, self._clock_turn,
            )
        logger.info(
            "Lichess : pendules (blancs=%s, noirs=%s, trait=%s, decompte=%s).",
            self._clock_white_ms, self._clock_black_ms, self._clock_turn, self._clock_running,
        )
        self._maybe_push_clock(force=True)

    def _maybe_push_clock(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_clock_push_ts) < self.CLOCK_PUSH_INTERVAL_S:
            return
        self._last_clock_push_ts = now
        elapsed_s = 0.0 if (self.game_over or not self._clock_running) else max(0.0, now - self._clock_ref_monotonic)
        white_ms, black_ms = compute_clock_ms(self._clock_white_ms, self._clock_black_ms,
                                               self._clock_turn, elapsed_s)
        send_event("lichess_clock", {
            "white_ms": white_ms, "black_ms": black_ms, "turn": self._clock_turn,
            "known": self._clock_known,
        })
        if self._first_move_deadline_active:
            deadline_elapsed_s = max(0.0, now - self._first_move_expiration_ref)
            seconds, estimated = self._first_move_deadline_seconds_and_estimated(deadline_elapsed_s)
            send_event("lichess_first_move_deadline", {
                "active": True, "seconds": seconds, "estimated": estimated,
            })

    # ── Plateau physique ─────────────────────────────────────────────────

    def _read_hardware_fen(self):
        try:
            raw = self.nl_inst.current_fen
        except Exception as exc:
            logger.debug("Lecture current_fen échouée (Lichess) : %s", exc)
            return None
        if not raw:
            return None
        parts = raw.strip().split()
        return parts[0] if parts else None

    def _register_board_lost(self) -> None:
        self._board_lost_strikes += 1
        if self._board_lost_strikes >= self.BOARD_LOST_STRIKES and not self._board_lost:
            self._board_lost = True
            self._board_lost_since = time.monotonic()
            self._next_reconnect_attempt_ts = self._board_lost_since
            logger.warning("Lichess : échiquier perdu en cours de partie (%s).", self.game_id)
            send_event("lichess_board_lost", {})

    def _register_board_present(self) -> None:
        if self._board_lost_strikes or self._board_lost:
            self._board_lost_strikes = 0
            if self._board_lost:
                self._board_lost = False
                self._board_lost_since = None
                send_event("lichess_board_ok", {})

    def _maybe_attempt_reconnect(self) -> None:
        """Lance une tentative de reconnexion en arrière-plan (jamais dans
        le fil principal — nl_inst.connect() peut bloquer plusieurs
        secondes), espacée selon la cadence 2s/30s puis 5s. Un seul essai à
        la fois (`_reconnecting_in_progress`, et le verrou de hid_backend
        en dessous — protections de #292). Ne résigne et n'abandonne
        jamais : la partie continue sur Lichess, la position est recalée
        à la reprise (issue #314, point 2)."""
        if self._reconnecting_in_progress or not self._board_lost:
            return
        now = time.monotonic()
        if now < self._next_reconnect_attempt_ts:
            return
        self._reconnecting_in_progress = True
        threading.Thread(target=self._attempt_reconnect_once, daemon=True).start()

    def _attempt_reconnect_once(self) -> None:
        try:
            self.nl_inst.connect()
            restart = getattr(self.nl_inst, "_start_fen_reader", None)
            if restart is not None:
                restart()
        except Exception as e:
            logger.debug("Lichess : tentative de reconnexion échiquier échouée (%s) : %s", self.game_id, e)
            elapsed = time.monotonic() - (self._board_lost_since or time.monotonic())
            interval = (self.RECONNECT_FAST_INTERVAL_S if elapsed < self.RECONNECT_FAST_DURATION_S
                        else self.RECONNECT_SLOW_INTERVAL_S)
            self._next_reconnect_attempt_ts = time.monotonic() + interval
        else:
            logger.info("Lichess : échiquier reconnecté en cours de partie (%s).", self.game_id)
            # Recale la position physique sur celle de Lichess (celle du jeu,
            # pas celle lue avant la coupure) via l'affichage existant
            # "cases à corriger" (issue #314, point 2).
            self._awaiting_physical_replication = False
            self._awaiting_piece_reset = True
            self._reset_target_fen = self.board.board_fen()
            self._register_board_present()
        finally:
            self._reconnecting_in_progress = False

    def _compute_action_buttons(self):
        """(resign_enabled, draw_enabled) — issue #321, points 1 et 2.
        Abandonner/Proposer nulle ne sont actifs que trait de l'utilisateur
        ET position physique alignée (ni réplication/recalage/promotion en
        attente, ni position illégale, ni échiquier perdu). Exceptions de
        sécurité : Abandonner reste actif si l'échiquier est perdu (jamais
        bloquer l'utilisateur), Proposer nulle reste inactif tant qu'une
        offre de l'utilisateur est déjà en attente de réponse.

        Issue #325, point 5 : pendant la mise en place d'une reprise
        (_resume_pending), Abandonner reste actif SANS attendre la
        reconstruction de la position — l'abandon est un simple appel
        réseau (voir _request_resign_or_abort), indépendant de l'état
        physique de l'échiquier. Essai réel d'Alain du 14/11/2026 : les
        deux boutons étaient grisés pendant toute la mise en place,
        empêchant d'abandonner une partie sans d'abord la reconstruire.
        Proposer nulle reste inactif ici : contrairement à l'abandon, une
        offre de nulle n'a de sens que si la position/le tour sont déjà
        confirmés."""
        if self.game_over or self.user_color is None:
            return False, False
        if self._resume_pending:
            return True, False
        user_turn = self.board.turn == (chess.WHITE if self.user_color == "white" else chess.BLACK)
        position_ok = not (
            self._awaiting_physical_replication
            or self._awaiting_piece_reset
            or self._pending_promotion is not None
            or self._illegal_position_active
            or self._board_lost
        )
        turn_ready = user_turn and position_ok
        resign_enabled = turn_ready or self._board_lost
        draw_enabled = turn_ready and not self._my_draw_offer_pending
        return resign_enabled, draw_enabled

    def _sync_turn_ready(self) -> None:
        state = self._compute_action_buttons()
        if state == self._action_buttons_state:
            return
        self._action_buttons_state = state
        resign_enabled, draw_enabled = state
        send_event("lichess_action_buttons", {
            "resign_enabled": resign_enabled, "draw_enabled": draw_enabled,
        })

    def _tick_physical(self) -> None:
        if self.user_color is None or self.game_over:
            return
        if self._resume_pending:
            self._tick_resume_setup()
        else:
            self._tick_physical_inner()
        # Recalcule systématiquement l'état des boutons Abandonner/Proposer
        # nulle (issue #321, point 1) — quelle que soit la branche prise
        # ci-dessus (échiquier perdu, réplication en attente, position
        # illégale, tour adverse...), jamais seulement sur les transitions
        # explicites, pour rester vrai à chaque tick (~50ms).
        self._sync_turn_ready()

    def _tick_resume_setup(self) -> None:
        """Écran de mise en place d'une partie reprise (issue #323, point
        3) : compare la position physique à self.board.board_fen(), qui
        reste la cible à jour même si l'adversaire joue pendant que
        l'utilisateur reconstruit la position (les événements de flux sont
        appliqués par _handle_stream_event dans la même boucle, voir
        _main_loop — case (d) du rapport de clôture). Jamais d'abandon
        automatique si l'échiquier est perdu ici : réutilise la même
        reconnexion que le reste de la partie (issue #314)."""
        hardware_fen = self._read_hardware_fen()
        if hardware_fen is None:
            self._register_board_lost()
            if self._board_lost:
                self._maybe_attempt_reconnect()
            return
        self._register_board_present()
        if self._board_lost:
            return
        target_fen = self.board.board_fen()
        if hardware_fen == target_fen:
            self._resume_pending = False
            self._resume_setup_active = False
            self._resume_led_squares = []
            # La position complète (y compris le dernier coup déjà appliqué
            # à self.board, voir _apply_game_full/_apply_new_moves) vient
            # d'être confirmée physiquement : neutralise les attentes
            # normales de début de partie (réplication du premier coup
            # adverse), qui ont pu être positionnées par _apply_new_moves
            # avant même l'écran de mise en place — sans quoi le tick
            # suivant attendrait à tort une réplication déjà satisfaite.
            self._awaiting_physical_replication = False
            self._replication_target_fen = None
            self._awaiting_piece_reset = False
            self._reset_target_fen = None
            try:
                self.nl_inst.turn_off_all_leds()
            except Exception as exc:
                logger.debug(
                    "Extinction LEDs (fin mise en place reprise, %s) échouée : %s",
                    self.game_id, exc,
                )
            logger.info(
                "Lichess : reprise (%s) — position physique reconstruite, jeu normal repris.",
                self.game_id,
            )
            send_event("lichess_resume_setup", {"active": False})
            return
        now = time.monotonic()
        if not self._resume_setup_active:
            self._resume_setup_active = True
            self._last_position_error_ts = 0.0  # envoi immédiat du premier état
        if now - self._last_position_error_ts < self.POSITION_ERROR_THROTTLE_S:
            return
        self._last_position_error_ts = now
        self._update_resume_setup_leds(hardware_fen, target_fen)
        send_event("lichess_resume_setup", {
            "active": True, "expected_fen": target_fen, "physical_fen": hardware_fen,
        })

    def _update_resume_setup_leds(self, hardware_fen: str, target_fen: str) -> None:
        """Allume les LED des cases qui diffèrent entre la position physique
        et la cible — jamais testé sur le vrai plateau (aucun matériel
        disponible pour cette issue), voir rapport de clôture."""
        squares = _differing_squares(target_fen, hardware_fen)
        if squares == self._resume_led_squares:
            return
        self._resume_led_squares = squares
        try:
            self.nl_inst.turn_off_all_leds()
            for sq in squares:
                self.nl_inst.set_led(sq, True)
        except Exception as exc:
            logger.debug(
                "LED mise en place (reprise, %s) échouée : %s", self.game_id, exc,
            )

    def _tick_physical_inner(self) -> None:
        hardware_fen = self._read_hardware_fen()
        if hardware_fen is None:
            self._register_board_lost()
            if self._board_lost:
                self._maybe_attempt_reconnect()
            return
        self._register_board_present()
        if self._board_lost:
            return
        if self._awaiting_physical_replication:
            self._check_replication(hardware_fen)
            return
        if self._awaiting_piece_reset:
            self._check_piece_reset(hardware_fen)
            return
        if self._pending_promotion is not None:
            return
        user_is_white = self.user_color == "white"
        if self.board.turn != (chess.WHITE if user_is_white else chess.BLACK):
            return
        self._check_user_move(hardware_fen)

    def _start_opponent_replication_wait(self, uci: str) -> None:
        self._awaiting_physical_replication = True
        self._replication_target_fen = self.board.board_fen()
        try:
            self.nl_inst.set_led(uci[:2], True)
            self.nl_inst.set_led(uci[2:4], True)
        except (ValueError, IndexError) as exc:
            logger.debug("LED coup adverse (Lichess) échouée : %s", exc)

    def _check_replication(self, hardware_fen: str) -> None:
        if hardware_fen == self._replication_target_fen:
            self._awaiting_physical_replication = False
            self._replication_target_fen = None
            try:
                self.nl_inst.turn_off_all_leds()
            except Exception as exc:
                logger.debug("Extinction LEDs (réplication) échouée : %s", exc)
            send_event("lichess_position_ok", {})
            return
        self._throttled_position_wait(hardware_fen, self._replication_target_fen)

    def _check_piece_reset(self, hardware_fen: str) -> None:
        if hardware_fen == self._reset_target_fen:
            self._awaiting_piece_reset = False
            self._reset_target_fen = None
            send_event("lichess_position_ok", {})
            return
        self._throttled_position_wait(hardware_fen, self._reset_target_fen)

    def _throttled_position_wait(self, hardware_fen: str, expected_fen: str) -> None:
        now = time.monotonic()
        if now - self._last_position_error_ts < self.POSITION_ERROR_THROTTLE_S:
            return
        self._last_position_error_ts = now
        send_event("lichess_position_wait", {"expected_fen": expected_fen, "physical_fen": hardware_fen})

    def _check_user_move(self, hardware_fen: str) -> None:
        expected = self.board.board_fen()
        if hardware_fen == expected:
            self._illegal_stable_count = 0
            self._clear_illegal_position()
            return
        promo = pending_promotion_move(self.board, hardware_fen)
        if promo is not None:
            self._illegal_stable_count = 0
            self._clear_illegal_position()
            self._pending_promotion = promo
            send_event("lichess_promotion_needed", {
                "from": chess.square_name(promo[0]), "to": chess.square_name(promo[1]),
            })
            return
        move = legal_move_for_hardware(self.board, hardware_fen)
        if move is not None:
            self._illegal_stable_count = 0
            self._clear_illegal_position()
            self._submit_move(move.uci())
            return
        if hardware_fen == self._last_illegal_fen:
            self._illegal_stable_count += 1
        else:
            self._last_illegal_fen = hardware_fen
            self._illegal_stable_count = 1
        if self._illegal_stable_count >= self.ILLEGAL_STABLE_READS_REQUIRED:
            self._activate_illegal_position(hardware_fen, expected)

    def _activate_illegal_position(self, hardware_fen: str, expected_fen: str) -> None:
        """Position physique ni attendue ni un coup légal pendant le tour de
        l'utilisateur — jamais le même message que l'attente de réplication
        du coup adverse (issue #321, point 5 : Alain a joué d4 au lieu de
        son coup noir, et n'a vu que la bannière générique « reproduisez le
        coup », sans savoir quelles cases corriger). Réémis (au même débit
        que les autres attentes de position) si les cases en erreur
        changent pendant que l'état reste actif, pour suivre les tentatives
        de correction de l'utilisateur."""
        now = time.monotonic()
        became_active = not self._illegal_position_active
        changed_fen = hardware_fen != self._last_illegal_position_sent_fen
        if not became_active and not changed_fen:
            return
        if not became_active and now - self._last_position_error_ts < self.POSITION_ERROR_THROTTLE_S:
            return
        self._last_position_error_ts = now
        self._illegal_position_active = True
        self._last_illegal_position_sent_fen = hardware_fen
        send_event("lichess_illegal_position", {
            "active": True, "expected_fen": expected_fen, "physical_fen": hardware_fen,
        })

    def _clear_illegal_position(self) -> None:
        if self._illegal_position_active:
            self._illegal_position_active = False
            self._last_illegal_position_sent_fen = None
            send_event("lichess_illegal_position", {"active": False})

    def _submit_promotion(self, piece_letter: str) -> None:
        from_sq, to_sq = self._pending_promotion
        piece_letter = piece_letter if piece_letter in ("q", "r", "b", "n") else "q"
        uci = chess.square_name(from_sq) + chess.square_name(to_sq) + piece_letter
        self._pending_promotion = None
        self._submit_move(uci)

    def _submit_move(self, uci: str) -> None:
        try:
            # Une offre de nulle en attente doit partir AVEC ce coup
            # (paramètre offeringDraw) pour rester valable : sans lui,
            # Lichess annule silencieusement notre propre offre dès que
            # nous jouons, et le prochain gameState (wdraw/bdraw à False)
            # serait alors interprété à tort comme un refus de l'adversaire
            # (issue #316, point 1).
            offer_draw = self._my_draw_offer_pending
            self.client.play_move(self.game_id, uci, offer_draw=offer_draw)
            now = time.monotonic()
            elapsed_ms = int((now - self._last_move_event_ts) * 1000)
            self._last_move_event_ts = now
            logger.info(
                "Lichess : coup envoyé %s (délai %d ms, offre_nulle_jointe=%s).",
                uci, elapsed_ms, offer_draw,
            )
        except LichessApiError as exc:
            self._reset_target_fen = self.board.board_fen()
            self._awaiting_piece_reset = True
            send_event("lichess_move_refused", {"message": exc.api_message or str(exc)})
        except (LichessNetworkError, LichessRateLimitError):
            send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning"})
        # Le coup confirmé revient par le flux (gameState) et sera appliqué
        # par _apply_new_moves — jamais de mise à jour optimiste ici.

    # ── Fin de partie ────────────────────────────────────────────────────

    def _title_for_status(self):
        if self._aborted:
            return "game.titre_annulee", {}
        if self._status in _FINISHED_WITH_WINNER and self._winner:
            won = self._winner == self.user_color
            return ("game.titre_victoire" if won else "game.titre_defaite"), {}
        if self._status in _FINISHED_DRAW:
            return "game.titre_nulle", {}
        return "game.fin_partie_default", {}

    def _history_from_board(self):
        b = chess.Board()
        fens = [b.board_fen()]
        moves = []
        for mv in self.board.move_stack:
            san = san_ep(b, mv)
            col = "white" if b.turn == chess.WHITE else "black"
            b.push(mv)
            fens.append(b.board_fen())
            moves.append({"san": san, "uci": mv.uci(), "color": col, "qualite": None})
        return fens, moves

    def _save_pgn(self, result: str) -> None:
        date_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y.%m.%d")
        headers = build_pgn_headers(
            self.game_id, self.player_name, self.user_color or "white", self.level,
            self.clock_limit_s, self.clock_increment_s, result, date_utc,
        )
        final_path = build_final_path("Lichess", "Amicale", headers["White"], headers["Black"])
        try:
            build_and_save_pgn(headers=headers, moves=list(self.board.move_stack), output_path=final_path)
            logger.info("Lichess : PGN enregistré (%s).", final_path)
        except Exception as exc:
            logger.warning("Sauvegarde PGN Lichess échouée : %s", exc)

    def _finalize(self) -> None:
        """Toujours appelé en fin de partie (quel que soit le chemin de
        sortie) — chaque étape est isolée dans son propre try/except pour
        qu'un échec n'empêche jamais les suivantes (issue #310, point 1) :
        le PGN doit être tenté avant l'envoi de l'état de fin, lui-même
        avant la libération de l'échiquier (faite par l'appelant)."""
        try:
            self.nl_inst.turn_off_all_leds()
        except Exception as exc:
            logger.debug("Extinction LEDs (fin partie Lichess) échouée : %s", exc)

        result = pgn_result(self._status, self._winner)
        logger.info("Lichess : partie terminée (statut=%s, résultat=%s).", self._status, result)
        if not self._aborted:
            try:
                self._save_pgn(result)
            except Exception as exc:
                logger.warning("Sauvegarde PGN Lichess échouée (hors _save_pgn) : %s", exc)

        unexpected = self._is_unexpected_end()
        try:
            title_key, title_vars = self._title_for_status()
            hist_fens, hist_moves = self._history_from_board()
            skip = self._back_menu_requested or unexpected
            payload = {
                "title_key": title_key, "title_vars": title_vars,
                "result": result, "source": "lichess", "skip": skip,
                "history_fen": hist_fens, "history_moves": hist_moves,
            }
            send_event("game_over", payload)
            if not skip:
                set_app_state("game_over", payload)
            if unexpected:
                self._notify_unexpected_end()
        except Exception as exc:
            logger.error("Lichess : notification de fin de partie échouée : %s", exc)

    def _is_unexpected_end(self) -> bool:
        """Vrai pour un statut de fin ni demandé par l'utilisateur
        (abandon/annulation via _request_resign_or_abort) ni par un retour
        menu explicite — jamais de fin silencieuse (issue #311, point 3)."""
        return (
            not self._back_menu_requested
            and not self._user_initiated_end
            and self._status in _UNEXPECTED_END_STATUSES
        )

    def _notify_unexpected_end(self) -> None:
        # Raison explicite dans le journal (issue #319, point 3) : ni
        # back_menu ni abandon/annulation demandés par l'utilisateur ne sont
        # passés par ici (voir _is_unexpected_end) — seul un statut Lichess
        # inattendu (flux coupé, annulation décidée côté Lichess, etc.) mène
        # ici, d'où "raison : autre".
        logger.warning(
            "Lichess : fin de partie inattendue (statut=%s) — raison : autre "
            "(non demandée par l'utilisateur).",
            self._status,
        )
        send_event("lichess_aborted", {
            "message_key": _ABORT_CAUSE_KEYS.get(self._status, _ABORT_CAUSE_DEFAULT_KEY),
            "replay_settings": {
                "level": self.level,
                "cadence": self.cadence_key,
                "color": self.chosen_color_setting,
                "player": self.player_name,
            },
        })
