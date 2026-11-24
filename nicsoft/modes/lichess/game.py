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

from nicsoft.core.config_manager import load_config
from nicsoft.core.ihm_port import send_event, get_action, set_app_state
from nicsoft.engine.board_utils import san_ep
from nicsoft.engine.pgn_manager import build_and_save_pgn, build_final_path
from nicsoft.modes.lichess.errors import (
    LichessApiError,
    LichessAuthError,
    LichessNetworkError,
    LichessRateLimitError,
    is_ambiguous_turn_or_over_error,
)
from nicsoft.modes.lichess.game_client import is_game_over, moves_from_state, side_to_move
from nicsoft.modes.lichess.game_log import GameLog

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
# Issue #370 : l'API Lichess ne communique, pour "aborted"/"noStart", QUE le
# statut "partie annulée avant son début" — jamais la raison (adversaire
# parti, premier coup non joué à temps, ou autre) : ne jamais affirmer une
# cause que Lichess ne donne pas. Les deux sont exclus de
# _maybe_fetch_new_rating() (voir _finalize/_is_unexpected_end) : confirmé
# jamais rated, d'où la mention « aucune cote n'est modifiée » dans le
# texte. "unknownFinish" reste à part (_FINISHED_WITH_WINNER, cote
# potentiellement affectée) : garde le message générique, sans cette
# affirmation.
_ABORT_CAUSE_KEYS = {
    "aborted": "lichess.annulee_avant_debut",
    "noStart": "lichess.annulee_avant_debut",
}
_ABORT_CAUSE_DEFAULT_KEY = "lichess.annulee_cause_inconnue"

# Issue #331, point 3 : signal LED persistant (abandon/nulle proposée/fin de
# partie provoquée par l'adversaire) — mêmes 8 chaînes binaires (une par
# rangée) que NicLinkManager.signal_lights() (driver.py, sig_num 2 et 3,
# non modifié ici), mais postées via nl_inst.set_all_leds() plutôt que
# signal_lights() : ce dernier éteint toujours tout seul après 1.5s, alors
# que ces LED doivent rester allumées jusqu'à acquittement de l'utilisateur
# (voir _wait_for_game_over_ack ci-dessous). set_all_leds() poste un seul
# paquet USB (confirmé par lecture de driver.py/hid_backend.py) — aucun
# second accès USB n'est nécessaire pour allumer plusieurs cases à la fois.
#
# Issue #340, point 8 : ces deux patterns étaient INVERSÉS depuis #331 —
# l'indice i d'une chaîne du tableau correspond physiquement à la rangée
# (i+1), convention confirmée par trois lectures indépendantes et
# concordantes du code existant : hid_backend.set_all_leds(r1..r8)
# ("r1..r8 = rangées 1 à 8"), driver.py::_led_worker_loop (arr[0]->r1,
# ..., arr[7]->r8) et build_led_map_for_move/square_cords (led_map[rang-1],
# déjà utilisé pour l'affichage normal des coups, jamais mis en cause).
# Avec cette convention, les anciennes valeurs allumaient en réalité
# l'INVERSE de ce que leur nom et leur commentaire annonçaient
# (_RANKS_1_4_LIT allumait les rangs 5-8, _RANKS_5_8_LIT les rangs 1-4) :
# c'est ce qui a fait allumer, lors de la partie réelle du 15/11/2026 où
# Alain jouait les noirs, les LED de SON propre camp (rangs 5-8) au lieu
# de celles de l'adversaire (rangs 1-4) — opponent_half_led_pattern()
# demandait pourtant la bonne constante ; seul le contenu des deux
# constantes était faux. Corrigé ci-dessous (contenu échangé, noms
# inchangés) — non ré-testé sur le vrai échiquier (aucun matériel
# disponible pour cette issue), voir rapport de clôture.
_RANKS_1_4_LIT = ["11111111"] * 4 + ["00000000"] * 4  # moitié blancs (rangs 1-4)
_RANKS_5_8_LIT = ["00000000"] * 4 + ["11111111"] * 4  # moitié noirs (rangs 5-8)

# Issue #340, point 1/2 : pattern PARTIEL (seulement les 2 rangs du centre
# du camp adverse, les plus proches du milieu de l'échiquier) pour le
# signal de simple DÉPART de l'adversaire — volontairement moins étendu
# que le pattern COMPLET (4 rangs, _RANKS_1_4_LIT/_RANKS_5_8_LIT) réservé
# au signal « réclamation possible » (point 2), pour qu'on distingue les
# deux sans lire l'écran. Pas de clignotement : la seule primitive
# matérielle disponible pour un affichage persistant (set_all_leds)
# affiche un pattern statique — un clignotement aurait exigé un fil dédié
# gérant lui-même l'alternance marche/arrêt, jamais testé sur le vrai
# échiquier pour cette issue (voir rapport de clôture).
_RANKS_3_4_LIT = ["00000000"] * 2 + ["11111111"] * 2 + ["00000000"] * 4  # centre, côté blancs
_RANKS_5_6_LIT = ["00000000"] * 4 + ["11111111"] * 2 + ["00000000"] * 2  # centre, côté noirs

# Délai (s) entre les deux bips du signal « distinct » (nulle proposée par
# l'adversaire / fin de partie provoquée par l'adversaire) — jamais testé
# sur le vrai échiquier (aucun matériel disponible pour cette issue), voir
# rapport de clôture.
_DOUBLE_BEEP_GAP_S = 0.3

# Issue #344, point 3bis : signal bip/LED de DÉBUT de partie — distinct des
# signaux « adversaire parti »/« réclamation possible » (#331/#340, qui
# réutilisent set_all_leds() avec des patterns persistants) et des
# indicateurs de tour (sig_num 2/3, driver.py, jamais utilisés par ce
# module). Posté via nl_inst.signal_lights() (driver.py) plutôt qu'un fil
# minuté séparé : la file LED est unique et ordonnée (un seul fil
# travailleur, voir driver.py::_led_worker_loop) — poster ce signal juste
# avant un éventuel affichage normal du premier coup adverse (cas des
# noirs, _apply_new_moves appelé juste après dans _apply_game_full) le fait
# attendre son tour plutôt que d'effacer prématurément l'affichage suivant,
# ce qu'un minuteur sur un fil séparé ne garantirait pas. Jamais testé sur
# le vrai échiquier (aucun matériel disponible pour cette issue), voir
# rapport de clôture.
_GAME_START_SIG_NUM = 7

# Clé i18n de la cause affichée sur le bandeau de fin de partie provoquée
# par l'adversaire (issue #331, point 4) — statut Lichess brut -> clé.
_OPPONENT_END_CAUSE_KEYS = {
    "resign": "lichess.cause.resign",
    "timeout": "lichess.cause.timeout",
    "outoftime": "lichess.cause.timeout",
    "mate": "lichess.cause.mate",
    "draw": "lichess.cause.draw",
    "stalemate": "lichess.cause.draw",
    "insufficientMaterialClaim": "lichess.cause.draw",
}
_OPPONENT_END_CAUSE_DEFAULT_KEY = "lichess.cause.default"


def opponent_half_led_pattern(user_color: str) -> list:
    """Pattern LED (8 rangées) de la moitié de l'échiquier côté adversaire,
    quelle que soit l'orientation de l'utilisateur (issue #331, point 3)."""
    return _RANKS_5_8_LIT if user_color == "white" else _RANKS_1_4_LIT


def opponent_gone_departure_led_pattern(user_color: str) -> list:
    """Pattern LED du signal de simple DÉPART de l'adversaire (issue #340,
    point 1) — partiel (2 rangs centraux du camp adverse), distinct du
    pattern complet d'opponent_half_led_pattern() réservé à la réclamation
    possible (point 2)."""
    return _RANKS_5_6_LIT if user_color == "white" else _RANKS_3_4_LIT


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


def pgn_cadence_folder_name(clock_limit_s: int, clock_increment_s: int) -> str:
    """Nom de sous-dossier « <minutes>+<incrément en secondes> » (issue
    #349, partie 2, point 1) — ex. "10+0", "15+10", "90+30". Chiffres et
    "+" seulement : sûr pour tous les systèmes de fichiers (y compris
    Windows, qui interdit `< > : " / \\ | ? *` mais accepte "+"). Dérivé
    directement de la cadence confirmée de la partie (`clock_limit_s`/
    `clock_increment_s`, jamais de `cadence_key`, qui peut être vide pour
    une reprise — voir LichessGame.__init__)."""
    minutes = max(0, int(clock_limit_s)) // 60
    increment = max(0, int(clock_increment_s))
    return f"{minutes}+{increment}"


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
                       date_utc: str, opponent_name: str = "", event_label: str = "",
                       user_rating=None, opponent_rating=None) -> dict:
    """`opponent_name`/`event_label` (issue #327, point 6) permettent de
    nommer un adversaire HUMAIN réel (nom Lichess) au lieu du nom d'IA par
    défaut — jamais fournis pour une partie contre l'IA (comportement
    inchangé, voir game_manager_modes/lichess.py et _save_pgn ci-dessous).

    `user_rating`/`opponent_rating` (issue #349, partie 1, point 2) :
    en-têtes standard WhiteElo/BlackElo, écrits seulement quand la cote
    correspondante est connue (jamais "0" ni une valeur devinée) — affectés
    au bon en-tête selon `user_color`, pour que l'écran « Révision PGN »
    les retrouve dans l'ordre standard quelle que soit l'orientation de
    l'échiquier au moment de l'affichage."""
    opp_name = opponent_name or opponent_pgn_name(level)
    user_name = user_name or "Vous"
    white = user_name if user_color == "white" else opp_name
    black = opp_name if user_color == "white" else user_name
    white_rating = user_rating if user_color == "white" else opponent_rating
    black_rating = opponent_rating if user_color == "white" else user_rating
    headers = {
        "Event": event_label or f"Lichess, amicale contre l'IA niveau {level}",
        "Site": f"https://lichess.org/{game_id}",
        "Date": date_utc,
        "White": white,
        "Black": black,
        "Result": result,
        "TimeControl": pgn_time_control(clock_limit_s, clock_increment_s),
    }
    if white_rating is not None:
        headers["WhiteElo"] = str(white_rating)
    if black_rating is not None:
        headers["BlackElo"] = str(black_rating)
    return headers


# ── Boucle de jeu ────────────────────────────────────────────────────────────

class LichessGame(threading.Thread):
    """Partie amicale contre l'IA de Lichess sur l'échiquier physique.
    `start()` exécute `run()` de façon synchrone (comme GameWeb — le vrai
    threading vit dans le lanceur, voir game_manager_modes/lichess.py)."""

    POLL_DELAY_S = 0.05
    CLOCK_PUSH_INTERVAL_S = 1.0
    CLOCK_LOG_MIN_INTERVAL_S = 30.0
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
                 clock_known: bool = True, game_log=None, known_user_color: str = "", **kwargs):
        super().__init__(daemon=True, **kwargs)
        self.nl_inst = nl_inst
        self.client = client
        self.game_id = game_id
        self.level = level
        # Journal dédié de partie (issue #326, point 10) — toujours actif :
        # si l'appelant n'en fournit pas (ex. game_manager_modes/lichess.py
        # n'a pas encore attaché le sien), LichessGame crée le sien ici,
        # pour qu'une partie construite directement (tests, futur appelant)
        # ne reste jamais sans journal dédié. Attaché au client existant
        # seulement s'il n'en a pas déjà un (le lanceur attache en général
        # le sien, créé plus tôt, avant même que ce coup-ci ne joigne la
        # partie — voir game_manager_modes/lichess.py).
        self._game_log = game_log if game_log is not None else GameLog(game_id)
        attach = getattr(self.client, "attach_game_log", None)
        if callable(attach) and getattr(self.client, "_game_log", None) is None:
            attach(self._game_log)
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
        # Couleur connue AVANT même le premier gameFull (issue #327, point
        # 4) — pour une partie contre un humain, aucun des deux côtés ne
        # porte `aiLevel` : la couleur de l'utilisateur ne peut donc plus
        # être déduite de la présence de l'IA (seul moyen utilisé jusqu'ici,
        # voir _apply_game_full) et doit être transmise explicitement par
        # l'appelant (depuis l'évènement gameStart du flux général
        # d'évènements, voir seek.py/game_manager_modes/lichess.py). Jamais
        # utilisée pour une partie contre l'IA (déduite comme avant).
        self._known_user_color = known_user_color if known_user_color in ("white", "black") else ""
        self.opponent_name = ""
        self.opponent_rating = None
        self.opponent_provisional = False
        # Issue #349, partie 1, point 1 : ma propre cote — toujours lue
        # dans le gameFull (champ `rating` de MON côté, white/black selon
        # `user_color`), jamais devinée ; absente contre un adversaire
        # anonyme ou si Lichess ne la fournit pas (ex. compte sans cote
        # dans cette cadence). `user_provisional` suit la même convention
        # que `opponent_provisional` ci-dessus (point d'interrogation
        # affiché côté interface, jamais calculé ici).
        self.user_rating = None
        self.user_provisional = False
        # Identifiant Lichess (champ `id`, minuscules canonique) de
        # l'utilisateur, lu dans ce même gameFull — utilisé UNIQUEMENT pour
        # la lecture publique de la nouvelle cote en fin de partie classée
        # (issue #349, partie 1, point 3 : /api/user/<id>, aucun jeton
        # nécessaire) ; jamais affiché, jamais journalisé au-delà de ce qui
        # l'est déjà pour l'adversaire.
        self._my_username = ""
        # Vrai pour une partie classée — lu dans le champ `rated` du
        # premier gameFull, jamais une valeur devinée localement (issue
        # #344, point 3 : toujours confirmé par Lichess, qu'il s'agisse
        # d'une partie contre un humain ou contre l'IA, où il reste
        # toujours faux).
        self.rated = False

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
        # Issue #347, partie 2, point 2 : vrai quand le DERNIER coup
        # physique envoyé a été refusé par Lichess (HTTP 400 ambigu) parce
        # que la partie venait de se terminer côté serveur (adversaire
        # abandon/temps écoulé/nulle...) — posé par _handle_move_rejected,
        # lu par _finalize() pour que l'écran de fin précise que ce coup
        # n'a pas été accepté. Jamais remis à False ensuite : la partie se
        # termine immédiatement après (comme _user_just_accepted_draw).
        self._last_move_rejected_after_game_over = False

        # Boutons Abandonner/Proposer nulle (issue #321, point 1) : état
        # (resign_enabled, draw_enabled) poussé côté interface par
        # _sync_turn_ready() à chaque changement — jamais recalculé côté
        # navigateur, pour que les exceptions de sécurité (point 2) restent
        # cohérentes avec la seule source de vérité du déroulement de la
        # partie (ce thread).
        self._action_buttons_state = (False, False)

        self._draw_offered_by_opponent = False
        self._my_draw_offer_pending = False
        # Issue #347, point 2 : contre un HUMAIN seulement, « Proposer
        # nulle » suit désormais l'usage FIDE (on propose après avoir joué
        # son coup, pendant que l'adversaire réfléchit) plutôt que « mon
        # tour » (règle de #321, conservée telle quelle contre l'IA, voir
        # _compute_action_buttons). Vrai dès que le coup de l'utilisateur
        # part vers Lichess (_submit_move) jusqu'au coup suivant de
        # l'adversaire (_apply_new_moves) — jamais recalculé à partir du
        # trait courant, pour que le bouton reste actif pendant toute la
        # réflexion de l'adversaire. Sans effet contre l'IA (bouton
        # toujours grisé, _compute_action_buttons ne lit pas ce drapeau
        # dans ce cas).
        self._human_draw_window_open = False
        # Issue #334, points 1-4 : adversaire parti (événement `opponentGone`
        # du flux) — `_opponent_gone_claim_win_in_seconds`/`_ref_monotonic`
        # mémorisent le délai annoncé et l'instant de réception (horloge
        # monotone locale, jamais une minuterie JS qui repartirait de zéro à
        # chaque re-rendu) ; `_opponent_gone_claimable` devient vrai une fois
        # ce délai écoulé (recalculé à chaque poussée, voir
        # _push_opponent_gone_state) — c'est à cet instant, et seulement à
        # cet instant, que le signal bip/LED de #331 est déclenché (jamais
        # dès le départ de l'adversaire). `_opponent_gone_signal_acked`
        # (bouton « J'ai vu » dédié à CE bandeau, distinct de
        # lichess_ack_game_over) n'éteint que le signal, jamais le bandeau
        # ni les boutons de réclamation.
        self._opponent_gone = False
        self._opponent_gone_claim_win_in_seconds = None
        self._opponent_gone_ref_monotonic = None
        self._opponent_gone_claimable = False
        self._opponent_gone_signal_acked = False
        # Issue #340, point 1 : vrai dès que le signal de simple départ a
        # été donné UNE FOIS pour la période d'absence en cours — remis à
        # faux seulement au retour de l'adversaire ou à un NOUVEAU départ
        # (jamais par un événement `opponentGone` répété de la même
        # période, voir _apply_opponent_gone, point 9 de cette issue).
        self._opponent_gone_departure_signaled = False
        # Issue #334, point 5 : vrai tant qu'une demande de reprise de coup
        # de l'adversaire (wtakeback/btakeback, cf. doc lichess-org/api
        # GameStateEvent.yaml) reste active côté Lichess — sert à ne la
        # refuser qu'UNE SEULE fois par demande (jamais en boucle à chaque
        # état reçu), tout en acceptant une NOUVELLE demande plus tard (le
        # champ redevient absent/faux entre deux demandes, voir
        # _check_opponent_takeback).
        self._takeback_request_active = False
        # Issue #331, point 3 : vrai juste après que l'utilisateur a
        # explicitement répondu « Accepter » à une offre de nulle de
        # l'adversaire — exempte la fin de partie qui en découle du signal
        # LED/bip « provoquée par l'adversaire » (l'utilisateur vient déjà
        # d'agir explicitement, jamais une double alerte pour la même
        # réponse). Jamais remis à False ensuite : la partie se termine
        # immédiatement après une acceptation, aucun autre coup ne peut
        # suivre dans cette même partie.
        self._user_just_accepted_draw = False
        # Calculé par _finalize(), lu par run() pour savoir s'il faut
        # bloquer sur _wait_for_game_over_ack() (issue #331, point 3) —
        # jamais vrai tant que la partie n'est pas terminée.
        self.opponent_caused_end = False
        # Renvoi unique de l'offre (issue #327, point 5) — voir
        # _apply_game_state : si l'état reçu juste après notre propre coup
        # (offre jointe via offeringDraw=true) ne montre toujours pas notre
        # indicateur, on retente UNE SEULE fois (jamais en boucle), réinitialisé
        # chaque fois qu'une nouvelle offre démarre (_process_browser_actions).
        self._my_draw_offer_resent = False

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
        # Issue #344, point 3bis : vrai dès que le signal de début de
        # partie (bip + LED distincts) a été émis — jamais émis à une
        # reprise (_resume_pending) ni répété si un gameFull revient (ex.
        # reconnexion réseau mi-partie, voir _apply_game_full) : une seule
        # fois par VRAIE partie lancée par ce lanceur.
        self._game_start_signal_sent = False

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
        # Auteur du tout dernier coup appliqué (issue #331, point 3) — sert
        # uniquement à distinguer un mat délivré par l'utilisateur lui-même
        # (son propre coup physique, pas une fin « provoquée par
        # l'adversaire ») d'un mat subi par lui ; voir _finalize().
        self._last_move_mover_color = None

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
        # Débit du JOURNAL DÉDIÉ de pendule, distinct de celui de l'envoi au
        # navigateur ci-dessus (issue #327, point 6) — une ligne par seconde
        # noierait les lignes utiles d'une partie de 90+30 : le journal
        # n'écrit qu'au recalage Lichess (force=True), au changement de
        # trait/source, ou au plus toutes les _CLOCK_LOG_MIN_INTERVAL_S
        # (filet de sécurité, comme le heartbeat général) — voir
        # _maybe_log_clock. Le flux envoyé au navigateur n'est pas concerné.
        self._last_clock_log_turn = None
        self._last_clock_log_source = None
        self._last_clock_log_ts = 0.0
        # Les pendules Lichess restent figées à leur valeur de départ tant
        # que les deux camps n'ont pas chacun joué leur premier coup — jamais
        # décomptées par une minuterie locale avant ça (issue #322, point 2).
        self._clock_running = False

        self._stream_event_queue = queue.Queue()
        self._stream_stop = threading.Event()
        self._stream_error = None
        self._last_board_read_ts = time.monotonic()
        # Issue #368, partie 2 : un échec réseau lors d'un coup/une action
        # (_submit_move, _safe_client_call, _safe_claim_call,
        # _safe_draw_offer_call) affiche un toast PERSISTANT (inchangé) —
        # mais rien ne le remplaçait auparavant une fois le réseau revenu :
        # il restait affiché indéfiniment même après une reprise réussie.
        # Ce drapeau mémorise qu'un tel toast est affiché, pour le
        # remplacer par un message de rétablissement à la prochaine action
        # réseau réussie (_report_network_error/_clear_network_error_if_active).
        self._network_error_active = False

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
        self._game_log.state_change(f"Partie démarrée — game_id={self.game_id}, niveau={self.level}.")
        try:
            self._main_loop()
        except Exception as exc:
            self._game_log.exception(exc, context="fil principal (_main_loop)")
            raise
        finally:
            self._stream_stop.set()
            self._finalize()
            # Issue #331, point 3 : bloque ICI (fil du lanceur — jamais
            # _finalize() elle-même, pour qu'elle reste rapide et non
            # bloquante pour les appelants directs, notamment les tests qui
            # l'invoquent isolément) tant que la fin de partie provoquée par
            # l'adversaire n'a pas été acquittée — voir
            # _wait_for_game_over_ack(). Avant la fermeture du journal dédié
            # ci-dessous, pour que la ligne d'acquittement y soit bien écrite.
            if self.opponent_caused_end:
                self._wait_for_game_over_ack()
                self._clear_opponent_alert_leds("fin de partie acquittée")
            try:
                reader.join(timeout=2.0)
            except RuntimeError:
                pass  # jointure best-effort — le thread est daemon de toute façon
            self._game_log.close()

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
            self._maybe_log_heartbeat()

    def _maybe_log_heartbeat(self) -> None:
        """Ligne de contrôle périodique du journal dédié (issue #326,
        point 10, (g) fin) — appelée à chaque tour de boucle principale
        (~50ms), mais ne journalise réellement qu'au rythme de
        HEARTBEAT_INTERVAL_S (voir GameLog.maybe_heartbeat)."""
        now = time.monotonic()
        elapsed_s = 0.0 if (self.game_over or not self._clock_running) else max(0.0, now - self._clock_ref_monotonic)
        white_ms, black_ms = compute_clock_ms(self._clock_white_ms, self._clock_black_ms,
                                               self._clock_turn, elapsed_s)
        last_read_age_s = max(0.0, now - getattr(self, "_last_board_read_ts", now))
        self._game_log.maybe_heartbeat(
            self._clock_turn, white_ms, black_ms, not self._board_lost, last_read_age_s,
        )

    def _stream_reader_loop(self):
        try:
            for event in self.client.stream_game(self.game_id):
                self._stream_event_queue.put(event)
                if self._stream_stop.is_set():
                    return
        except (LichessApiError, LichessAuthError, LichessNetworkError, LichessRateLimitError) as exc:
            self._stream_error = exc
        except Exception as exc:
            # Toute autre exception imprévue dans ce fil secondaire ne
            # remontait auparavant nulle part — journalisée ici en entier
            # (issue #326, point 10, (g)) plutôt que de laisser le fil
            # mourir silencieusement (le flux de partie s'arrête alors
            # normalement via le "_stream_closed" ci-dessous).
            self._stream_error = exc
            self._game_log.exception(exc, context="fil de lecture du flux (_stream_reader_loop)")
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
                if self._opponent_is_ai:
                    # Défense en profondeur (issue #327, point 5) : le
                    # bouton reste grisé en permanence contre l'IA
                    # (_compute_action_buttons) — si une action arrive
                    # malgré tout, ne jamais envoyer la requête (Lichess
                    # l'ignorerait silencieusement, voir game.py en-tête) ni
                    # faire croire qu'une offre est en cours.
                    logger.info("Lichess : proposition de nulle ignorée (adversaire IA, %s).", self.game_id)
                    send_event("lichess_toast", {"message_key": "lichess.nulle_impossible_ia", "type": "warning"})
                elif self._safe_draw_offer_call():
                    self._my_draw_offer_pending = True
                    self._my_draw_offer_resent = False
                    logger.info("Lichess : nulle proposée par %s.", self.player_name)
                    self._game_log.state_change(f"nulle proposée par {self.player_name} — requête envoyée (draw/yes).")
                    send_event("lichess_draw_proposed", {})
            elif atype == "lichess_draw_accept":
                self._draw_offered_by_opponent = False
                self._user_just_accepted_draw = True
                self._clear_opponent_alert_leds("nulle acceptée par l'utilisateur")
                if self._safe_client_call(lambda: self.client.answer_draw(self.game_id, True)):
                    logger.info("Lichess : nulle acceptée par %s (offre de l'adversaire).", self.player_name)
                    self._game_log.state_change(f"nulle acceptée par {self.player_name} (offre de l'adversaire).")
            elif atype == "lichess_draw_refuse":
                self._draw_offered_by_opponent = False
                self._clear_opponent_alert_leds("nulle refusée par l'utilisateur")
                if self._safe_client_call(lambda: self.client.answer_draw(self.game_id, False)):
                    logger.info("Lichess : nulle refusée par %s (offre de l'adversaire).", self.player_name)
                    self._game_log.state_change(f"nulle refusée par {self.player_name} (offre de l'adversaire).")
            elif atype == "lichess_promotion_choice" and self._pending_promotion is not None:
                self._submit_promotion(action.get("piece", "q"))
            elif atype == "lichess_claim_victory":
                self._handle_claim_action(
                    claim_fn=lambda: self.client.claim_victory(self.game_id),
                    request_label="réclamation de victoire (adversaire parti)",
                )
            elif atype == "lichess_claim_draw":
                self._handle_claim_action(
                    claim_fn=lambda: self.client.claim_draw(self.game_id),
                    request_label="réclamation de nulle (adversaire parti)",
                )
            elif atype == "lichess_opponent_gone_ack":
                # Issue #334, point 4 : éteint seulement le signal bip/LED
                # (bandeau et boutons de réclamation restent affichés tant
                # que l'adversaire n'est pas revenu — voir _apply_opponent_gone).
                self._opponent_gone_signal_acked = True
                self._clear_opponent_alert_leds("signal « adversaire parti » acquitté par l'utilisateur")
                self._game_log.state_change("signal « adversaire parti » (bip/LED) acquitté par l'utilisateur.")

    def _handle_claim_action(self, claim_fn, request_label: str) -> None:
        """Réclamation de victoire/nulle (issue #334, points 2/3) —
        `request_label` distingue les deux dans le journal dédié et les
        messages de log. Jamais déclenché automatiquement : toujours en
        réponse à `lichess_claim_victory`/`lichess_claim_draw`, envoyés par
        le navigateur seulement sur un clic utilisateur (le bouton y reste
        grisé tant que le délai annoncé par Lichess n'est pas écoulé — voir
        app.js). Défense en profondeur : si l'état connu ici dit que la
        réclamation n'est pas (ou plus) possible, la requête réseau n'est
        même pas envoyée."""
        logger.info("Lichess : %s demandée par l'utilisateur (%s).", request_label, self.game_id)
        if not (self._opponent_gone and self._opponent_gone_claimable):
            send_event("lichess_toast", {
                "message_key": "lichess.reclamation_pas_encore_possible", "type": "warning",
            })
            return
        if self._safe_claim_call(claim_fn, request_label):
            # Issue #340, point 10 : une réclamation réussie termine la
            # partie à l'initiative de l'UTILISATEUR, exactement comme un
            # abandon/une annulation (_request_resign_or_abort) — sans ce
            # marquage, _finalize() ne pouvait pas distinguer ce cas d'une
            # fin VRAIMENT causée par l'adversaire (le statut Lichess qui en
            # résulte, ex. "timeout", est le même dans les deux cas) et
            # rallumait à tort le signal LED/bip « fin de partie provoquée
            # par l'adversaire » — observé dans la partie réelle du
            # 15/11/2026 (réclamation acceptée à 06:04:48, LED et double bip
            # « fin de partie » redonnés juste après, comme si l'adversaire
            # l'avait provoquée).
            self._user_initiated_end = True

    def _report_network_error(self) -> None:
        """Toast persistant « réseau indisponible » (inchangé, voir
        lichess.md) — mémorise qu'il est affiché pour pouvoir le remplacer
        par un message de rétablissement (issue #368, partie 2)."""
        self._network_error_active = True
        send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning", "persistent": True})

    def _clear_network_error_if_active(self) -> None:
        """Remplace le toast « réseau indisponible » par un message de
        rétablissement dès la prochaine action réseau réussie (issue #368,
        partie 2) — sans ce remplacement, le toast persistant restait
        affiché indéfiniment même après une reprise réussie, laissant
        croire à une coupure toujours en cours."""
        if self._network_error_active:
            self._network_error_active = False
            send_event("lichess_toast", {"message_key": "lichess.erreur_reseau_retablie", "type": "success"})

    def _safe_client_call(self, fn) -> bool:
        try:
            fn()
            self._clear_network_error_if_active()
            return True
        except LichessApiError as exc:
            send_event("lichess_move_refused", {"message": exc.api_message or str(exc)})
        except (LichessNetworkError, LichessRateLimitError):
            self._report_network_error()
        return False

    def _safe_claim_call(self, fn, request_label: str) -> bool:
        """Comme _safe_client_call, mais pour claim-victory/claim-draw
        (issue #334, points 2/3) — jamais le message générique « coup
        refusé » (celui de _safe_client_call parlerait à tort d'un coup).
        Un refus de Lichess (délai pas encore écoulé côté serveur,
        adversaire revenu entre-temps, partie déjà terminée) affiche son
        message exact, de façon PERSISTANTE (jamais un toast qui disparaît
        tout seul avant que l'utilisateur ait pu le lire) ; aucun verrou
        local n'est posé ici après un refus — le bouton reste cliquable
        tant que l'état connu (_opponent_gone_claimable) dit la réclamation
        possible, pour que l'utilisateur puisse réessayer sans attendre."""
        try:
            fn()
        except LichessApiError as exc:
            detail = exc.api_message or str(exc)
            logger.info("Lichess : %s refusée par Lichess : %s.", request_label, detail)
            self._game_log.state_change(f"{request_label} — refusée par Lichess : {detail}.")
            send_event("lichess_toast", {
                "message_key": "lichess.reclamation_refusee", "vars": {"detail": detail},
                "type": "warning", "persistent": True,
            })
            return False
        except (LichessNetworkError, LichessRateLimitError):
            self._report_network_error()
            return False
        self._clear_network_error_if_active()
        logger.info("Lichess : %s envoyée — acceptée par Lichess.", request_label)
        self._game_log.state_change(f"{request_label} — envoyée, acceptée par Lichess.")
        return True

    def _safe_draw_offer_call(self) -> bool:
        """Envoi d'une offre de nulle de l'utilisateur (issue #347, partie
        1, point 2) — comme _safe_claim_call ci-dessus, jamais le message
        générique « Lichess a refusé ce coup » (_safe_client_call) pour un
        refus qui ne concerne pas un coup : un clic répété pendant la
        même fenêtre (offre déjà active) doit afficher un message clair
        plutôt qu'un texte parlant d'un coup, et ne jamais planter."""
        try:
            self.client.answer_draw(self.game_id, True)
        except LichessApiError as exc:
            detail = exc.api_message or str(exc)
            logger.info("Lichess : offre de nulle refusée par Lichess : %s.", detail)
            self._game_log.state_change(f"offre de nulle — refusée par Lichess : {detail}.")
            send_event("lichess_toast", {
                "message_key": "lichess.nulle_requete_refusee", "vars": {"detail": detail},
                "type": "warning", "persistent": True,
            })
            return False
        except (LichessNetworkError, LichessRateLimitError):
            self._report_network_error()
            return False
        self._clear_network_error_if_active()
        return True

    def _request_resign_or_abort(self, reason: str = "demande utilisateur") -> bool:
        """`reason` (issue #319, point 3) : raison écrite dans le journal
        avec le résultat — distincte de l'instant de la demande, déjà
        journalisé par l'appelant (_process_browser_actions) avant l'appel
        réseau abort()/resign() ci-dessous, qui peut prendre du temps.

        Issue #347, partie 1, point 5 : ligne dédiée du journal de partie
        AVANT l'appel réseau (heure automatique de GameLog._write, état de
        la partie, type d'adversaire) — la réponse effective de Lichess
        est déjà journalisée séparément par GameClient._request (appelée
        par _safe_client_call ci-dessous), jamais le jeton (masqué par
        GameLog._mask, indépendamment de ces deux lignes)."""
        aborting = len(self.board.move_stack) < 2
        adversaire = "IA" if self._opponent_is_ai else "humain"
        action_label = "annulation (moins de 2 coups)" if aborting else "abandon"
        self._game_log.state_change(
            f"{action_label} demandé par l'utilisateur — raison={reason}, adversaire={adversaire}, "
            f"coups_joues={len(self.board.move_stack)}, statut_avant={self._status}."
        )
        if aborting:
            ok = self._safe_client_call(lambda: self.client.abort(self.game_id))
        else:
            ok = self._safe_client_call(lambda: self.client.resign(self.game_id))
        if not ok:
            self._game_log.state_change(f"{action_label} — refusé ou en erreur (voir ligne REQUEST ci-dessus).")
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
        self._game_log.state_change(
            f"{action_label} — acceptée par Lichess, statut_apres={self._status}, "
            f"vainqueur={self._winner or '(aucun)'}."
        )
        return True

    # ── Alertes « l'adversaire a joué/proposé/terminé » (issue #331) ──────
    # Bip (case à cocher, config.json::lichess_beep_opponent_move) + LED
    # (toujours, indépendamment de la case) quand l'adversaire joue, propose
    # la nulle ou termine la partie — pour rester perceptible sans regarder
    # l'écran, y compris onglet navigateur en arrière-plan (bip matériel de
    # l'échiquier, jamais le navigateur : seul mécanisme déjà existant et
    # réutilisé — nl_inst.beep(), voir driver.py — qui ne dépend d'aucun
    # état de focus/premier-plan du navigateur).

    def _hardware_beep(self, reason: str, double: bool = False) -> None:
        """Bip matériel de l'échiquier physique — `double` pour un signal
        distinct (nulle proposée / fin de partie provoquée par l'adversaire),
        deux bips espacés de _DOUBLE_BEEP_GAP_S émis par un fil dédié pour ne
        jamais bloquer la boucle de jeu (jamais de time.sleep() dans le fil
        principal pour un simple signal sonore)."""
        total = 2 if double else 1

        def _emit_one(n: int) -> None:
            try:
                self.nl_inst.beep()
            except Exception as exc:
                logger.debug("Bip matériel (%s, %d/%d) échoué : %s", reason, n, total, exc)
            self._game_log.state_change(f"bip émis — {reason} ({n}/{total}).")

        if double:
            def _twice():
                _emit_one(1)
                time.sleep(_DOUBLE_BEEP_GAP_S)
                _emit_one(2)
            threading.Thread(target=_twice, daemon=True, name="lichess_beep").start()
        else:
            _emit_one(1)

    def _maybe_beep_opponent(self, reason: str, double: bool = False) -> None:
        """N'émet le bip que si la case « Bip quand l'adversaire joue » est
        cochée — relu à chaque appel (jamais mis en cache) pour un effet
        immédiat si l'utilisateur la coche/décoche en cours de partie
        (issue #331, point 1)."""
        if load_config().get("lichess_beep_opponent_move"):
            self._hardware_beep(reason, double=double)

    def _signal_game_start(self) -> None:
        """Issue #344, point 3bis : signal bip/LED de DÉBUT de partie —
        appelé une seule fois par vraie partie (voir _game_start_signal_sent
        dans _apply_game_full, jamais à une reprise ni à une reconnexion),
        pour toute partie Lichess (IA ou humain, classée ou amicale). Ni la
        case « Bip quand l'adversaire joue » (_maybe_beep_opponent, qui ne
        concerne que les coups adverses) ni l'acquittement utilisateur ne
        s'appliquent ici : toujours émis, jamais conditionnel. Signification
        selon la couleur de l'utilisateur (aucune pièce n'a encore été
        déplacée à cet instant — même position initiale pour les deux
        camps) : Blancs, « à vous de jouer » (rien d'autre à l'écran avant
        votre premier coup) ; Noirs, « la partie a commencé » (le premier
        coup adverse, déjà présent ou imminent, suit normalement via
        _apply_new_moves — voir le commentaire de _GAME_START_SIG_NUM pour
        l'ordre d'affichage)."""
        try:
            self.nl_inst.beep()
            self.nl_inst.signal_lights(_GAME_START_SIG_NUM)
        except Exception as exc:
            logger.debug("Signal de début de partie (bip/LED) échoué : %s", exc)
        self._game_log.state_change(
            f"signal de début de partie émis (bip + LED) — couleur_utilisateur={self.user_color}, "
            f"classée={self.rated}."
        )

    def _set_opponent_alert_leds(self, pattern: list, desc: str, reason: str) -> None:
        """Poste un pattern LED d'alerte persistant (jamais d'extinction
        automatique) — factorise ce que faisait _light_opponent_half() pour
        le pattern complet (issue #331) et ce que fait maintenant
        _light_opponent_departure() pour le pattern partiel (issue #340,
        point 1)."""
        try:
            self.nl_inst.turn_off_all_leds()
            self.nl_inst.set_all_leds(pattern)
        except Exception as exc:
            logger.debug("LED alerte adversaire (%s) échouée : %s", reason, exc)
        logger.info("Lichess : LED alerte adversaire allumées (%s, %s).", reason, desc)
        self._game_log.state_change(f"LED allumées — {desc} — déclencheur={reason}.")

    def _light_opponent_half(self, reason: str) -> None:
        """Allume en LED, de façon persistante, la moitié COMPLÈTE de
        l'échiquier côté adversaire — toujours, indépendamment de la case à
        cocher (issue #331, point 3). Reste allumé jusqu'à
        _clear_opponent_alert_leds() (réponse à la nulle, acquittement de
        fin de partie, ou acquittement/retour du signal « adversaire
        parti »)."""
        if self.user_color is None:
            return
        pattern = opponent_half_led_pattern(self.user_color)
        half_desc = "moitié adversaire (rangs 5-8 (noirs))" if self.user_color == "white" \
            else "moitié adversaire (rangs 1-4 (blancs))"
        self._set_opponent_alert_leds(pattern, half_desc, reason)

    def _light_opponent_departure(self, reason: str) -> None:
        """Issue #340, point 1 : allume en LED, de façon persistante, le
        pattern PARTIEL (2 rangs centraux du camp adverse) du simple départ
        de l'adversaire — distinct du pattern complet de
        _light_opponent_half(), réservé à la réclamation possible."""
        if self.user_color is None:
            return
        pattern = opponent_gone_departure_led_pattern(self.user_color)
        half_desc = "départ adversaire (rangs 5-6, centre côté noir)" if self.user_color == "white" \
            else "départ adversaire (rangs 3-4, centre côté blanc)"
        self._set_opponent_alert_leds(pattern, half_desc, reason)

    def _clear_opponent_alert_leds(self, reason: str) -> None:
        """Éteint le signal LED posé par _light_opponent_half()/
        _light_opponent_departure() — réponse à la nulle (accepter/
        refuser), acquittement de fin de partie, ou acquittement/retour du
        signal « adversaire parti »."""
        try:
            self.nl_inst.turn_off_all_leds()
        except Exception as exc:
            logger.debug("Extinction LED alerte adversaire (%s) échouée : %s", reason, exc)
        self._game_log.state_change(f"LED éteintes — acquittement ({reason}).")

    def _apply_opponent_gone_led_state(self, reason: str) -> None:
        """Issue #340, point 5 : pose en LED l'alerte « adversaire parti »
        actuellement due (réclamable > simple départ), SAUF si un coup
        adverse est en cours d'affichage sur l'échiquier
        (self._awaiting_physical_replication, posé par
        _start_opponent_replication_wait via des set_led() additifs non
        encore confirmés) : priorité au coup, le signal est alors différé —
        _check_replication() rappelle cette même méthode juste après avoir
        confirmé le coup et éteint ses LED, ce qui rétablit le signal à ce
        moment-là. N'affecte jamais le bip, émis indépendamment (il ne
        partage aucune ressource avec l'affichage LED)."""
        if self._awaiting_physical_replication:
            self._game_log.state_change(f"LED alerte différée (coup adverse affiché) — {reason}.")
            return
        if not self._opponent_gone or self._opponent_gone_signal_acked:
            return
        if self._opponent_gone_claimable:
            self._light_opponent_half(reason)
        else:
            self._light_opponent_departure(reason)

    def _signal_opponent_gone_departure(self) -> None:
        """Issue #340, point 1 : signal donné UNE SEULE fois par période
        d'absence, dès le départ de l'adversaire (jamais seulement à la
        réclamation possible, comme avant cette issue) — bip simple (case
        à cocher) + LED partielle persistante, distincte du pattern complet
        de _signal_opponent_claimable(). La garde d'unicité (une seule fois
        par période) est faite par l'appelant (_apply_opponent_gone,
        is_new_period) — _opponent_gone_departure_signaled n'est positionné
        qu'ici, pour que _apply_opponent_gone_led_state() sache ensuite
        quel pattern réafficher après un éventuel coup adverse."""
        self._opponent_gone_departure_signaled = True
        self._maybe_beep_opponent("adversaire parti", double=False)
        self._apply_opponent_gone_led_state("adversaire parti")

    def _signal_opponent_claimable(self) -> None:
        """Issue #334, point 4 : réutilise le mécanisme de signaux de #331
        dès que la réclamation devient possible (jamais dès le simple
        départ de l'adversaire, voir _push_opponent_gone_state et, depuis
        l'issue #340 point 1, _signal_opponent_gone_departure) — bip
        double (case à cocher) + LED persistante de la moitié adverse
        COMPLÈTE (pattern distinct de celui du simple départ), jusqu'à
        acquittement (lichess_opponent_gone_ack), retour de l'adversaire ou
        réclamation. N'émet rien si déjà acquitté pour cette absence
        (self._opponent_gone_signal_acked)."""
        if self._opponent_gone_signal_acked:
            return
        self._maybe_beep_opponent("réclamation possible (adversaire parti)", double=True)
        self._apply_opponent_gone_led_state("réclamation possible (adversaire parti)")

    def _wait_for_game_over_ack(self) -> None:
        """Bloque (fil du lanceur de cette partie — jamais le fil socketio
        ni la boucle menu, voir game_manager_modes/lichess.py) jusqu'à ce
        que l'utilisateur acquitte la fin de partie provoquée par
        l'adversaire : bouton « J'ai vu » (action lichess_ack_game_over) ou
        tout retour au menu/changement de mode, qui vaut acquittement
        implicite (issue #331, point 3). Les LED restent allumées pendant
        toute cette attente, sans limite de durée — comme les autres
        attentes sans limite de temps de ce module (voir
        _wait_initial_position_lichess dans le lanceur) ; au plus tard,
        elles sont de toute façon éteintes par le lanceur à la libération
        de l'échiquier (nl_inst.turn_off_all_leds() dans le `finally` de
        _run_lichess/_run_lichess_human) ou par le prochain
        NicLinkManager.reset() au début de la partie suivante."""
        while True:
            action = get_action(timeout=0.2)
            if action is None:
                continue
            atype = action.get("type", "")
            if atype == "lichess_ack_game_over" or atype == "back_menu" or atype in _OTHER_MODE_ACTIONS:
                logger.info("Lichess : fin de partie (adversaire) acquittée (%s).", atype or "?")
                self._game_log.state_change(f"fin de partie — acquittement reçu ({atype or '?'}).")
                return

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
        elif etype == "opponentGone":
            self._apply_opponent_gone(event)
        # chatLine : rien à afficher à cette étape.

    def _apply_opponent_gone(self, event: dict) -> None:
        """Issue #334, points 1/4 — étendu par l'issue #340 : événement
        `opponentGone` du flux (gone + claimWinInSeconds, doc lichess-org/api
        doc/specs/schemas/OpponentGoneEvent.yaml, lue le 14/11/2026), reçu
        environ toutes les 5s TANT QUE l'adversaire reste parti (observé
        dans la partie réelle du 15/11/2026 : des événements répétés
        arrivent même une fois le délai à 0, jusqu'à ce que l'adversaire
        revienne ou que la réclamation ait lieu).

        Issue #340, point 9 : un événement répété de la MÊME période
        d'absence ne doit jamais réarmer un signal déjà donné — avant ce
        correctif, `_opponent_gone_claimable`/`_opponent_gone_signal_acked`
        étaient remis à faux à CHAQUE événement `gone=true`, ce qui faisait
        croire à _push_opponent_gone_state() qu'on venait juste de
        redevenir réclamable et relançait le signal (bip double + LED) —
        observé trois fois de suite (06:04:41/42/47) dans la partie réelle
        au lieu d'une. Seule une NOUVELLE période (transition
        non-parti -> parti) réarme ces indicateurs ; `claim_win_in_seconds`
        reste mis à jour à chaque événement de la même période (c'est le
        countdown légitime envoyé par Lichess, pas un signal).

        Issue #340, point 1 : le signal de simple départ
        (_signal_opponent_gone_departure) est déclenché ici, une seule fois
        par période, dès la détection d'une NOUVELLE période — jamais de
        signal bip/LED « réclamable » ici : c'est toujours
        _push_opponent_gone_state(), rappelée à chaque seconde par
        _maybe_push_clock, qui recalcule le temps restant et déclenche ce
        second signal une fois le délai écoulé."""
        gone = bool(event.get("gone"))
        claim_win_in_seconds = event.get("claimWinInSeconds")
        logger.info(
            "Lichess : opponentGone reçu (gone=%s, claimWinInSeconds=%s, %s).",
            gone, claim_win_in_seconds, self.game_id,
        )
        self._game_log.state_change(
            f"opponentGone reçu — gone={gone}, claimWinInSeconds={claim_win_in_seconds}."
        )
        if gone:
            is_new_period = not self._opponent_gone
            self._opponent_gone = True
            if is_new_period:
                self._opponent_gone_signal_acked = False
                self._opponent_gone_claimable = False
                self._opponent_gone_departure_signaled = False
            if claim_win_in_seconds is not None:
                self._opponent_gone_claim_win_in_seconds = max(0.0, float(claim_win_in_seconds))
                self._opponent_gone_ref_monotonic = time.monotonic()
            elif self._opponent_gone_ref_monotonic is None:
                # Lichess n'a jamais annoncé de délai (champ absent dès le
                # premier événement) — jamais vu en pratique d'après la
                # doc (toujours présent quand gone=true), mais jamais de
                # blocage silencieux ici : réclamable immédiatement plutôt
                # que bloqué sans fin (voir rapport de clôture).
                self._opponent_gone_claim_win_in_seconds = 0.0
                self._opponent_gone_ref_monotonic = time.monotonic()
            if is_new_period:
                self._signal_opponent_gone_departure()
            self._push_opponent_gone_state()
        else:
            was_signaled = self._opponent_gone_departure_signaled or self._opponent_gone_claimable
            self._opponent_gone = False
            self._opponent_gone_claim_win_in_seconds = None
            self._opponent_gone_ref_monotonic = None
            self._opponent_gone_claimable = False
            self._opponent_gone_signal_acked = False
            self._opponent_gone_departure_signaled = False
            if was_signaled:
                self._clear_opponent_alert_leds("adversaire de retour")
            send_event("lichess_opponent_gone", {"gone": False})

    def _push_opponent_gone_state(self) -> None:
        """Recalcule le temps restant avant réclamation possible depuis
        l'instant de réception mémorisé (horloge monotone locale, jamais
        un décompte JS qui repartirait de zéro à chaque rendu — issue
        #334, point 1) et le pousse au navigateur. Déclenche le signal de
        #331 (_signal_opponent_claimable) exactement à la transition vers
        « réclamable », jamais à chaque poussée."""
        if not self._opponent_gone:
            return
        now = time.monotonic()
        if self._opponent_gone_claim_win_in_seconds is None or self._opponent_gone_ref_monotonic is None:
            remaining = 0.0
        else:
            elapsed = max(0.0, now - self._opponent_gone_ref_monotonic)
            remaining = max(0.0, self._opponent_gone_claim_win_in_seconds - elapsed)
        became_claimable = remaining <= 0.0 and not self._opponent_gone_claimable
        self._opponent_gone_claimable = remaining <= 0.0
        send_event("lichess_opponent_gone", {
            "gone": True,
            "seconds": remaining,
            # Issue #334, point 3 : même décompte Lichess (opponentGone ne
            # porte qu'un seul délai) pour la victoire et pour la nulle —
            # voir rapport de clôture.
            "claimable": self._opponent_gone_claimable,
            "draw_claimable": self._opponent_gone_claimable,
        })
        if became_claimable:
            self._signal_opponent_claimable()

    def _check_opponent_takeback(self, state: dict) -> None:
        """Issue #334, point 5 : détecte une demande de reprise de coup de
        l'adversaire (wtakeback/btakeback — doc lichess-org/api
        doc/specs/schemas/GameStateEvent.yaml, lue le 14/11/2026 : "true if
        <color> is proposing takeback, else omitted") et la refuse
        explicitement, UNE SEULE FOIS par demande (jamais en boucle si le
        même état est reçu/relu plusieurs fois) — `_takeback_request_active`
        ne redevient faux que si l'indicateur disparaît à son tour,
        permettant de refuser une NOUVELLE demande plus tard. Appelé à la
        fois par _apply_game_full (une demande peut déjà être active dès le
        premier état reçu — issue #334, point 6) et _apply_game_state."""
        if self.user_color is None:
            return
        requested = bool(state.get("btakeback") if self.user_color == "white" else state.get("wtakeback"))
        if requested and not self._takeback_request_active:
            self._takeback_request_active = True
            logger.info("Lichess : demande de reprise de coup de l'adversaire — refus automatique (%s).", self.game_id)
            self._game_log.state_change(
                "demande de reprise de coup reçue (adversaire) — refus automatique envoyé (takeback/no)."
            )
            if self._safe_client_call(lambda: self.client.answer_takeback(self.game_id, False)):
                send_event("lichess_toast", {
                    "message_key": "lichess.reprise_refusee", "type": "info", "persistent": True,
                })
        elif not requested and self._takeback_request_active:
            self._takeback_request_active = False
            self._game_log.state_change("demande de reprise de coup (adversaire) retirée/traitée.")

    def _handle_stream_closed(self) -> None:
        if self.game_over:
            return
        if self._stream_error is not None:
            send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning", "persistent": True})
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
        wdraw = bool(state.get("wdraw"))
        bdraw = bool(state.get("bdraw"))
        logger.info(
            "Lichess : état reçu (coups=%d, statut=%s, wdraw=%s, bdraw=%s, expiration=%s).",
            len(moves_from_state(state)),
            state.get("status", self._status),
            wdraw, bdraw,
            state.get("expiration"),
        )
        # Issue #327, point 6 : présence/absence des deux indicateurs de
        # nulle à CHAQUE état reçu, sans throttle (contrairement aux
        # pendules ci-dessus) — distinct du journal général, c'est le
        # journal dédié de CETTE partie qu'Alain relit après un essai réel.
        self._game_log.state_change(f"état reçu — indicateurs nulle : blancs={wdraw}, noirs={bdraw}.")

    def _apply_game_full(self, event: dict) -> None:
        white = event.get("white") or {}
        black = event.get("black") or {}
        white_is_ai = white.get("aiLevel") is not None
        black_is_ai = black.get("aiLevel") is not None
        self._opponent_is_ai = white_is_ai or black_is_ai
        if white_is_ai:
            self.user_color = "black"
            self.level = white.get("aiLevel", self.level)
        elif black_is_ai:
            self.user_color = "white"
            self.level = black.get("aiLevel", self.level)
        elif self._known_user_color:
            # Partie contre un humain (issue #327, point 4) : ni white ni
            # black ne porte `aiLevel`, donc notre couleur ne peut plus être
            # déduite de l'IA — transmise par l'appelant (voir __init__ et
            # game_manager_modes/lichess.py, résolue depuis l'évènement
            # gameStart du flux général d'évènements AVANT ce premier
            # gameFull).
            self.user_color = self._known_user_color
        else:
            # Repli, ne devrait jamais arriver en pratique (humain sans
            # couleur connue à l'avance) — garder une valeur plutôt que
            # planter ; conserve la couleur déjà connue si elle existe.
            self.user_color = self.user_color or "white"
        opponent_dict = black if self.user_color == "white" else white
        self_dict = white if self.user_color == "white" else black
        if self._opponent_is_ai:
            self.opponent_name = opponent_pgn_name(self.level)
            self.opponent_rating = None
            self.opponent_provisional = False
        else:
            self.opponent_name = opponent_dict.get("name") or opponent_dict.get("id") or ""
            self.opponent_rating = opponent_dict.get("rating")
            self.opponent_provisional = bool(opponent_dict.get("provisional"))
        # Issue #349, partie 1, point 1 : MA cote — toujours lue du côté
        # qui est le mien dans ce gameFull (jamais devinée), qu'il
        # s'agisse d'une partie classée/amicale contre un humain OU contre
        # l'IA (mon côté porte toujours `rating`/`provisional`, seul le
        # côté adverse porte `aiLevel` à la place). None si absente (ex.
        # compte sans cote dans cette cadence) — jamais affiché comme 0.
        self.user_rating = self_dict.get("rating")
        self.user_provisional = bool(self_dict.get("provisional"))
        self._my_username = (self_dict.get("id") or self_dict.get("name") or "").strip()
        # Issue #344, point 3 : `rated` vient toujours de Lichess (champ
        # requis du schéma GameFullEvent), jamais deviné localement — faux
        # pour toute partie contre l'IA (confirmé par la lecture de la doc
        # officielle, aucun paramètre "rated" sur /api/challenge/ai).
        self.rated = bool(event.get("rated"))
        self._game_log.state_change(
            f"gameFull reçu — couleur_utilisateur={self.user_color}, adversaire_ia={self._opponent_is_ai}, "
            f"adversaire={self.opponent_name!r} (cote={self.opponent_rating}), ma_cote={self.user_rating}, "
            f"classée={self.rated}, niveau={self.level}, "
            f"cadence={self.clock_limit_s}+{self.clock_increment_s}."
        )
        if not self._resume_pending and not self._game_start_signal_sent:
            self._game_start_signal_sent = True
            self._signal_game_start()
        state = event.get("state") or {}
        self._log_game_state_received(state)
        # Issue #334, point 6 : une demande de reprise de coup de
        # l'adversaire déjà active au moment de la reprise (wtakeback/
        # btakeback déjà présent dans ce premier état) est détectée et
        # refusée dès la fin de la mise en place, pas seulement au
        # prochain gameState — voir _check_opponent_takeback. Pour
        # l'adversaire déjà parti (opponentGone), voir en revanche le
        # rapport de clôture : Lichess ne réémet pas cet événement à la
        # (re)connexion du flux (limitation confirmée côté Lichess,
        # lila#18664/#18665, lue le 14/11/2026) — AlChess ne peut donc pas
        # le savoir avant un futur changement d'état réel (ex. retour de
        # l'adversaire).
        self._check_opponent_takeback(state)
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
            # Issue #327, point 4 : nom et cote de l'adversaire, échappés
            # côté navigateur comme tout texte venu de Lichess (esc()) —
            # jamais inséré en HTML brut ici. None pour la cote si inconnue
            # (IA, ou compte anonyme côté Lichess).
            "opponent_name": self.opponent_name,
            "opponent_rating": self.opponent_rating,
            "opponent_provisional": self.opponent_provisional,
            "opponent_is_ai": self._opponent_is_ai,
            # Issue #349, partie 1, point 1 : MA cote, même convention que
            # ci-dessus (None si inconnue — jamais devinée ; point
            # d'interrogation affiché côté interface si provisoire).
            "user_rating": self.user_rating,
            "user_provisional": self.user_provisional,
            "rated": self.rated,
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
        self._check_opponent_takeback(event)
        last_mover_color = self._apply_new_moves(event)
        self._reset_clock_from_state(event)
        self._maybe_activate_first_move_deadline(event)
        opponent_offered = event.get("bdraw") if self.user_color == "white" else event.get("wdraw")
        opponent_offered = bool(opponent_offered)
        if opponent_offered != self._draw_offered_by_opponent:
            self._draw_offered_by_opponent = opponent_offered
            if opponent_offered:
                logger.info("Lichess : nulle proposée par l'adversaire.")
                self._game_log.state_change("nulle proposée par l'adversaire (indicateur reçu).")
                # LED/bip (issue #331, point 3) — jamais ici de
                # turn_off_all_leds() dans la branche inverse (offre
                # retirée/déjà répondue) : ce coup adverse réutilise la même
                # mise à jour d'état et pourrait coïncider avec les LED
                # d'affichage normal du coup (_start_opponent_replication_wait,
                # juste au-dessus dans cette même méthode) — jamais perturbées
                # par ce signal. L'extinction se fait sur réponse explicite
                # (lichess_draw_accept/refuse) ou, si l'offre s'éteint sans
                # réponse, au cycle normal de LED du coup suivant
                # (_check_replication/_check_piece_reset éteignent déjà tout
                # une fois la position reproduite).
                self._light_opponent_half("nulle proposée par l'adversaire")
                self._maybe_beep_opponent("nulle proposée par l'adversaire", double=True)
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
                self._game_log.state_change(
                    f"nulle refusée — proposée par {self.player_name}, adversaire a joué sans accepter."
                )
                send_event("lichess_draw_refused", {})
        # Renvoi unique de l'offre si son écho n'apparaît pas (issue #327,
        # point 5) — contre un humain seulement : établi par lecture du code
        # public de lila (modules/bot/src/main/BotPlayer.scala::offerDraw,
        # modules/round/src/main/Drawer.scala::yes, lus le 14/11/2026) que
        # renvoyer une offre déjà active (isOfferingDraw déjà vrai) retombe
        # sur `case _ => ReloadOwner` — un no-op sans erreur, jamais un
        # second vrai envoi — donc sans risque même si l'offre était déjà
        # bien passée. Seulement juste après NOTRE propre coup
        # (my_just_moved), jamais après un coup adverse, et une seule fois
        # par offre (_my_draw_offer_resent). Non vérifié avec une vraie
        # partie contre un humain (interdit pendant cette issue, voir
        # rapport de clôture) — repose sur la lecture du code ci-dessus.
        my_just_moved = last_mover_color is not None and last_mover_color == self.user_color
        if (
            self._my_draw_offer_pending and my_just_moved and not self._opponent_is_ai
            and not self._my_draw_offer_resent
        ):
            my_offered_now = event.get("wdraw") if self.user_color == "white" else event.get("bdraw")
            if not bool(my_offered_now):
                self._my_draw_offer_resent = True
                logger.info(
                    "Lichess : offre de nulle non reflétée juste après notre coup — renvoi unique (draw/yes)."
                )
                self._game_log.state_change(
                    "nulle — offre non reflétée dans l'état reçu juste après notre coup ; "
                    "renvoi unique par précaution (jamais en boucle)."
                )
                self._safe_client_call(lambda: self.client.answer_draw(self.game_id, True))
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
            self._game_log.state_change(f"nulle acceptée par l'adversaire (offre de {self.player_name}).")
            send_event("lichess_draw_accepted", {})
        self._status = status
        self._winner = winner
        self._aborted = status == "aborted"
        self.game_over = True
        self._game_log.state_change(f"partie terminée — statut={status}, vainqueur={winner or '(aucun)'}.")
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
            self._last_move_mover_color = mover_color
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
                # Bip court à chaque coup de l'adversaire SEULEMENT (jamais
                # pour les coups de l'utilisateur) — case à cocher, issue
                # #331 point 2. Le tout premier coup de l'IA (utilisateur
                # noirs, avant même ce coup-ci) garde son bip existant,
                # inconditionnel, déclenché séparément par
                # _apply_game_full — voir rapport de clôture.
                if mover_color != self.user_color:
                    self._maybe_beep_opponent("coup de l'adversaire")
        self._moves_applied = len(moves)
        if last_mover_color is None:
            return None
        if last_mover_color != self.user_color:
            # Issue #347, point 2 : le coup de l'adversaire referme la
            # fenêtre « Proposer nulle » (contre un humain) — y compris à
            # la lecture initiale d'une reprise (initial=True), pour
            # refléter correctement l'historique déjà joué.
            self._human_draw_window_open = False
            self._start_opponent_replication_wait(new_moves[-1])
        else:
            self._awaiting_piece_reset = False
            # Issue #347, point 2 : l'écho (confirmé par le flux) de notre
            # propre coup rouvre/confirme la fenêtre — en complément de
            # l'ouverture immédiate faite par _submit_move() à l'envoi
            # (jamais d'attente du flux pour activer le bouton), ceci
            # couvre aussi la lecture initiale d'une reprise où le dernier
            # coup joué était déjà le nôtre.
            self._human_draw_window_open = True
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
        source = (
            "inconnue (jamais confirmée par le flux)" if not self._clock_known else
            "flux Lichess + décompte local" if self._clock_running else
            "flux Lichess (figée, avant les deux premiers coups)"
        )
        self._maybe_log_clock(white_ms, black_ms, self._clock_turn, source, force=force)
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
        # Issue #334, point 1 : même cadence (1x/s) que le compte à rebours
        # du premier coup ci-dessus — recalculé depuis l'instant de
        # réception mémorisé, jamais une minuterie JS qui repartirait de
        # zéro à chaque rendu.
        if self._opponent_gone:
            self._push_opponent_gone_state()

    def _maybe_log_clock(self, white_ms: float, black_ms: float, turn: str, source: str, force: bool) -> None:
        """Écrit dans le journal dédié seulement au recalage reçu de
        Lichess (`force=True`, voir _reset_clock_from_state), au changement
        de trait ou de source depuis la dernière ligne écrite, ou au plus
        toutes les CLOCK_LOG_MIN_INTERVAL_S — jamais à chaque appel (issue
        #327, point 6 : une ligne par seconde noierait les lignes utiles
        d'une partie de 90+30). Valeurs arrondies à la milliseconde entière
        (point 6)."""
        now = time.monotonic()
        turn_changed = turn != self._last_clock_log_turn
        source_changed = source != self._last_clock_log_source
        stale = (now - self._last_clock_log_ts) >= self.CLOCK_LOG_MIN_INTERVAL_S
        if not (force or turn_changed or source_changed or stale):
            return
        self._last_clock_log_turn = turn
        self._last_clock_log_source = source
        self._last_clock_log_ts = now
        self._game_log.clock(round(white_ms), round(black_ms), turn, source)

    # ── Plateau physique ─────────────────────────────────────────────────

    def _read_hardware_fen(self):
        self._last_board_read_ts = time.monotonic()
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
            self._game_log.connectivity("échiquier perdu — tentatives de reconnexion vont démarrer.")
            send_event("lichess_board_lost", {})

    def _register_board_present(self) -> None:
        if self._board_lost_strikes or self._board_lost:
            self._board_lost_strikes = 0
            if self._board_lost:
                lost_duration_s = time.monotonic() - (self._board_lost_since or time.monotonic())
                self._board_lost = False
                self._board_lost_since = None
                self._game_log.connectivity(f"échiquier reconnecté (perdu pendant {lost_duration_s:.1f}s).")
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
        attempt_start = time.monotonic()
        try:
            self.nl_inst.connect()
            restart = getattr(self.nl_inst, "_start_fen_reader", None)
            if restart is not None:
                restart()
        except Exception as e:
            logger.debug("Lichess : tentative de reconnexion échiquier échouée (%s) : %s", self.game_id, e)
            self._game_log.connectivity(
                f"tentative de reconnexion échiquier échouée ({time.monotonic() - attempt_start:.2f}s) : {e}"
            )
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
        """(resign_enabled, draw_enabled) — issues #321, #327 et #347.

        Contre l'IA de Lichess (#321, points 1 et 2, INCHANGÉ par #347) :
        Abandonner/Proposer nulle ne sont actifs que trait de l'utilisateur
        ET position physique alignée (ni réplication/recalage/promotion en
        attente, ni position illégale, ni échiquier perdu) ; Abandonner
        reste actif si l'échiquier est perdu ; Proposer nulle reste grisé
        en PERMANENCE (#327, point 5 : no-op silencieux côté serveur contre
        l'IA — lila, modules/game/src/main/Game.scala::playerCanOfferDraw
        exige `!opponent.isAi`, lu le 14/11/2026).

        Contre un HUMAIN (#347) :
        - Abandonner reste actif à TOUT moment du déroulement de la partie
          (tour adverse, reproduction du coup adverse sur l'échiquier,
          reprise) — Alain a signalé ne pouvoir abandonner que pendant son
          propre tour, impossible en cadence longue (15-20 min de
          réflexion adverse) alors que Lichess le permet à tout moment.
          L'appel réseau (_request_resign_or_abort) ne dépend lui-même
          d'aucun état physique.
        - Proposer nulle suit désormais l'usage FIDE (on propose nulle
          APRÈS avoir joué son coup, pendant que l'adversaire réfléchit,
          jamais avant) au lieu de « mon tour » : actif dès que le coup de
          l'utilisateur est parti vers Lichess (_human_draw_window_open,
          posé par _submit_move) jusqu'au coup suivant de l'adversaire
          (_apply_new_moves le referme), y compris pendant la reproduction
          de ce coup et pendant le tour de l'utilisateur avant qu'il ne
          rejoue. Ancienne confusion (#321) : une offre faite pendant le
          coup adverse était jugée refusée dès le coup suivant — supprimée
          en proposant seulement après son propre coup (#318 inchangé par
          ailleurs : le refus n'est lui-même déclaré qu'après un vrai coup
          de l'adversaire, voir _apply_game_state).

        Issue #325, point 5 : pendant la mise en place d'une reprise
        (_resume_pending), Abandonner reste actif SANS attendre la
        reconstruction de la position, pour les deux types d'adversaire —
        comportement antérieur à #347, inchangé ici. Proposer nulle reste
        inactif pendant cette mise en place, quel que soit l'adversaire."""
        if self.game_over or self.user_color is None:
            return False, False
        if self._resume_pending:
            return True, False
        if self._opponent_is_ai:
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
            draw_enabled = False
        else:
            resign_enabled = True
            draw_enabled = self._human_draw_window_open
        return resign_enabled, draw_enabled

    def _sync_turn_ready(self) -> None:
        state = self._compute_action_buttons()
        if state == self._action_buttons_state:
            return
        self._action_buttons_state = state
        resign_enabled, draw_enabled = state
        self._game_log.state_change(
            f"boutons abandon={'actif' if resign_enabled else 'grisé'} "
            f"nulle={'actif' if draw_enabled else 'grisé'} — "
            f"trait_utilisateur={self.user_color is not None and self.board.turn == (chess.WHITE if self.user_color == 'white' else chess.BLACK)}, "
            f"reprise_en_cours={self._resume_pending}, replication_attendue={self._awaiting_physical_replication}, "
            f"recalage_attendu={self._awaiting_piece_reset}, promotion_attendue={self._pending_promotion is not None}, "
            f"position_illegale={self._illegal_position_active}, echiquier_perdu={self._board_lost}, "
            f"offre_nulle_en_attente={self._my_draw_offer_pending}, "
            f"fenetre_nulle_humain_ouverte={self._human_draw_window_open}, adversaire_ia={self._opponent_is_ai}"
        )
        send_event("lichess_action_buttons", {
            "resign_enabled": resign_enabled, "draw_enabled": draw_enabled,
            # Issue #327, point 5 : permet à l'interface d'afficher une
            # explication courte (« Lichess n'accepte pas les nulles contre
            # l'ordinateur ») plutôt qu'un bouton grisé sans raison.
            "draw_disabled_vs_ai": self._opponent_is_ai,
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
            # Issue #340, point 5 : le coup adverse vient de finir d'être
            # montré (priorité au coup, voir _apply_opponent_gone_led_state)
            # — si un signal « adversaire parti » reste dû (pas encore
            # acquitté, adversaire toujours parti), le rétablir maintenant
            # que turn_off_all_leds() ci-dessus vient de l'effacer.
            self._apply_opponent_gone_led_state("coup adverse affiché — signal rétabli")
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
            self._game_log.board_change(
                f"promotion détectée {chess.square_name(promo[0])}{chess.square_name(promo[1])} — "
                f"décision : choix de la pièce demandé à l'utilisateur."
            )
            send_event("lichess_promotion_needed", {
                "from": chess.square_name(promo[0]), "to": chess.square_name(promo[1]),
            })
            return
        move = legal_move_for_hardware(self.board, hardware_fen)
        if move is not None:
            self._illegal_stable_count = 0
            self._clear_illegal_position()
            self._game_log.board_change(
                f"coup physique reconnu {move.uci()} — position lue {hardware_fen} — décision : coup envoyé."
            )
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
        self._game_log.board_change(
            f"position physique illégale — lue {hardware_fen}, attendue {expected_fen} — "
            f"décision : case(s) à corriger affichée(s)."
        )
        send_event("lichess_illegal_position", {
            "active": True, "expected_fen": expected_fen, "physical_fen": hardware_fen,
        })

    def _clear_illegal_position(self) -> None:
        if self._illegal_position_active:
            self._illegal_position_active = False
            self._last_illegal_position_sent_fen = None
            self._game_log.board_change("position illégale résolue — case(s) à corriger masquée(s).")
            send_event("lichess_illegal_position", {"active": False})

    def _submit_promotion(self, piece_letter: str) -> None:
        from_sq, to_sq = self._pending_promotion
        piece_letter = piece_letter if piece_letter in ("q", "r", "b", "n") else "q"
        uci = chess.square_name(from_sq) + chess.square_name(to_sq) + piece_letter
        self._pending_promotion = None
        self._submit_move(uci)

    def _submit_move(self, uci: str) -> None:
        offer_draw = self._my_draw_offer_pending
        # Issue #384, point 1 : demi-coup attendu pour CE coup — sa place
        # dans self.board.move_stack si Lichess l'accepte (_check_user_move
        # n'appelle _submit_move que pendant le tour de l'utilisateur, donc
        # cette place correspond toujours à self.user_color, jamais besoin
        # de vérifier l'auteur séparément). Capturé AVANT l'envoi : un
        # retry automatique du même uci (réseau revenu, voir plus bas)
        # retrouve la même place puisque self.board n'avance que par l'écho
        # confirmé du flux, jamais ici.
        expected_ply = len(self.board.move_stack)
        try:
            # Une offre de nulle en attente doit partir AVEC ce coup
            # (paramètre offeringDraw) pour rester valable : sans lui,
            # Lichess annule silencieusement notre propre offre dès que
            # nous jouons, et le prochain gameState (wdraw/bdraw à False)
            # serait alors interprété à tort comme un refus de l'adversaire
            # (issue #316, point 1).
            self.client.play_move(self.game_id, uci, offer_draw=offer_draw)
            self._clear_network_error_if_active()
            now = time.monotonic()
            elapsed_ms = int((now - self._last_move_event_ts) * 1000)
            self._last_move_event_ts = now
            logger.info(
                "Lichess : coup envoyé %s (délai %d ms, offre_nulle_jointe=%s).",
                uci, elapsed_ms, offer_draw,
            )
            self._game_log.state_change(
                f"coup physique envoyé {uci} — offre_nulle_jointe={offer_draw} — accepté par Lichess."
            )
            # Issue #347, point 1 (partie 2) : contre un humain, l'envoi
            # réussi de notre propre coup rouvre immédiatement la fenêtre
            # « Proposer nulle » — sans attendre l'écho du flux (confirmé
            # en plus par _apply_new_moves, voir plus haut), pour que le
            # bouton devienne actif dès l'instant où le coup part vers
            # Lichess, comme demandé (« dès que l'utilisateur a joué son
            # coup »).
            if not self._opponent_is_ai:
                self._human_draw_window_open = True
        except LichessApiError as exc:
            self._handle_move_rejected(uci, exc, expected_ply)
        except (LichessNetworkError, LichessRateLimitError) as exc:
            # Issue #368, partie 2 : le coup physique n'est PAS perdu — il
            # reste détecté comme "différent de self.board" à chaque tick
            # suivant (~50ms, _check_user_move) tant qu'il n'a pas été
            # confirmé, donc réessayé automatiquement sans action de
            # l'utilisateur jusqu'à ce que le réseau revienne (ou que la
            # partie soit quittée). Un double envoi accidentel (réponse
            # perdue après un envoi en réalité accepté) est sans risque :
            # Lichess refuse le second essai (déjà son tour), et ce refus
            # ambigu est déjà géré sans afficher de faux « coup refusé »
            # (voir _handle_move_rejected/is_ambiguous_turn_or_over_error).
            self._game_log.state_change(f"coup physique {uci} — erreur réseau : {exc}.")
            self._report_network_error()
        # Le coup confirmé revient par le flux (gameState) et sera appliqué
        # par _apply_new_moves — jamais de mise à jour optimiste ici.

    # Délai maximal (s) d'attente d'un événement de fin de partie déjà en
    # route dans le flux, avant de conclure qu'un refus ambigu est une
    # vraie erreur — voir _handle_move_rejected ci-dessous. Jamais une
    # attente réseau : ce délai ne fait qu'attendre ce qui est peut-être
    # déjà en chemin dans le flux ouvert (StreamReader), jamais une
    # nouvelle requête. Issue réelle du 15/11/2026 (Alain, noirs) :
    # l'événement de fin (adversaire abandonne) était déjà arrivé 51ms
    # avant la réponse HTTP d'erreur du coup — largement sous ce délai.
    AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S = 2.0

    def _move_already_applied(self, uci: str, expected_ply: int) -> bool:
        """Issue #377, point 2, corrigé par #384 point 1 : vrai si `uci` a
        bien été appliqué à self.board (seule source de vérité de ce
        module) par le flux, À SA PLACE ATTENDUE `expected_ply` — le demi-
        coup où le joueur devait jouer au moment de l'envoi (voir
        _submit_move) — c'est-à-dire si l'envoi initial avait en réalité
        réussi et que seule la réponse HTTP s'est perdue (coupure juste
        après l'envoi). Vérifier CETTE place précise (jamais seulement le
        dernier coup de la liste) couvre le cas où l'adversaire a déjà
        répondu pendant la relecture bornée du flux (très probable contre
        l'IA Lichess) ET écarte le piège inverse : un coup identique
        (même notation uci) joué plus tôt dans la partie, à une autre
        place, ne doit jamais être pris pour cette confirmation. Comme
        _submit_move n'est appelé que pendant le tour de l'utilisateur
        (self.board.turn == self.user_color à ce moment), cette place
        correspond toujours à l'utilisateur — inutile de revérifier
        l'auteur séparément."""
        if expected_ply >= len(self.board.move_stack):
            return False
        return self.board.move_stack[expected_ply].uci() == uci

    def _handle_move_rejected(self, uci: str, exc: LichessApiError, expected_ply: int) -> None:
        """Issue #347, point 2 (partie 2) : un coup refusé par Lichess avec
        le message HTTP 400 ambigu « Not your turn, or game already over »
        (doc officielle lichess-org/api — un seul message pour deux causes
        très différentes) ne doit jamais s'afficher comme une simple
        erreur « Lichess a refusé ce coup » SI la vraie cause est que la
        partie vient de se terminer (adversaire qui abandonne, temps
        écoulé, nulle acceptée...) : cas réel constaté par Alain le
        15/11/2026 (parties noirs) — il avait livré un mat sur l'échiquier
        physique, mais l'adversaire avait abandonné quelques dizaines de
        millisecondes avant que Lichess reçoive son coup ; Alain a gagné,
        mais l'écran n'a montré qu'un coup refusé.

        Issue #377, point 2 (suite de #368) : le même refus ambigu couvre
        aussi un troisième cas, jamais distingué avant cette issue — notre
        propre envoi avait en fait été accepté par Lichess, mais seule la
        réponse HTTP s'est perdue (coupure juste après l'envoi) ; _submit_move
        réessaie alors automatiquement le même uci, que Lichess refuse (déjà
        son tour) avec ce même message ambigu. Si la partie continue
        (l'adversaire n'a pas encore rejoué), l'ancien code concluait à tort
        à une vraie erreur après le délai d'attente ci-dessous — documenté
        comme « gap connu » par test_issue368_lichess_game_network_loss.py
        avant cette correction. Le renvoi lui-même ne change pas (Lichess
        refuse toujours le doublon, jamais de risque de rejouer le coup) :
        c'est uniquement l'affichage qui est corrigé, en testant si `uci` est
        déjà appliqué à self.board à sa place attendue `expected_ply` (voir
        _move_already_applied — corrigé par #384 point 1 : ne dépend plus
        de la position du coup en fin de liste, car l'adversaire a pu
        répondre entre-temps pendant la relecture) — si oui, succès
        silencieux, aucun message d'erreur, aucune demande de remettre la
        pièce en place.

        Message non ambigu (coup réellement illégal, position désynchro-
        nisée, etc.) : comportement inchangé (toast + remise en place
        physique demandée). Message ambigu : on relit l'état réel de la
        partie — seule source de vérité de ce module (voir l'en-tête du
        fichier) — en traitant tout événement déjà en route dans le flux
        ouvert, avec une attente bornée (jamais indéfinie, voir
        AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S) pour couvrir le cas où
        l'événement de fin (ou la confirmation de notre propre coup) n'est
        pas encore arrivé. Si la partie est confirmée terminée, le
        déroulement normal de fin de partie prend le relais (_finalize,
        déclenché par _main_loop dès que self.game_over devient vrai) —
        AUCUN toast « coup refusé » n'est affiché dans ce cas, mais
        self._last_move_rejected_after_game_over est posé pour que l'écran
        de fin précise que ce dernier coup physique n'a pas été accepté (le
        PGN enregistré ne le contient de toute façon jamais : _submit_move
        ne pousse jamais le coup sur self.board avant confirmation par le
        flux)."""
        message = exc.api_message or str(exc)
        self._game_log.state_change(
            f"coup physique {uci} — refusé par Lichess (HTTP {exc.status_code}) : {message}."
        )
        ambiguous = is_ambiguous_turn_or_over_error(message)
        if ambiguous and not self.game_over:
            self._drain_pending_stream_events(self.AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S)
        if ambiguous and self._move_already_applied(uci, expected_ply):
            self._game_log.state_change(
                f"coup physique {uci} — relecture du flux : déjà appliqué (réponse HTTP perdue "
                f"après acceptation réelle par Lichess) — succès silencieux, aucune erreur affichée."
            )
            return
        if ambiguous and self.game_over:
            self._last_move_rejected_after_game_over = True
            self._game_log.state_change(
                f"coup physique {uci} — relecture du flux : partie déjà terminée "
                f"(statut={self._status}) — dernier coup non accepté, aucune erreur affichée."
            )
            return
        if ambiguous:
            self._game_log.state_change(
                f"coup physique {uci} — relecture du flux : partie toujours en cours "
                f"après {self.AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S:.1f}s — vraie erreur, coup refusé affiché."
            )
        self._reset_target_fen = self.board.board_fen()
        self._awaiting_piece_reset = True
        send_event("lichess_move_refused", {"message": message})

    def _drain_pending_stream_events(self, timeout_s: float) -> None:
        """Traite, dans la limite de `timeout_s`, tout événement du flux de
        partie déjà disponible (ou arrivant pendant l'attente) — jamais de
        nouvelle requête réseau ici, seulement la lecture de ce qui est
        déjà en route. S'arrête dès que la partie est marquée terminée
        (self.game_over) ou que le délai est dépassé."""
        deadline = time.monotonic() + timeout_s
        while not self.game_over:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                event = self._stream_event_queue.get(timeout=min(remaining, 0.2))
            except queue.Empty:
                continue
            self._handle_stream_event(event)

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
        """FEN complet (pas board_fen()) : l'écran d'analyse commun envoie
        ces positions au moteur pour les flèches des meilleurs coups
        (#335), qui a besoin du bon camp au trait — issue #338. Sans
        impact sur la règle de fair-play (#333) : le moteur n'est jamais
        sollicité pendant une partie Lichess en cours, seulement sur cet
        écran d'analyse ouvert une fois la partie terminée."""
        b = chess.Board()
        fens = [b.fen()]
        moves = []
        for mv in self.board.move_stack:
            san = san_ep(b, mv)
            col = "white" if b.turn == chess.WHITE else "black"
            b.push(mv)
            fens.append(b.fen())
            moves.append({"san": san, "uci": mv.uci(), "color": col, "qualite": None})
        return fens, moves

    def _save_pgn(self, result: str) -> None:
        date_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y.%m.%d")
        # Issue #327, point 6 : vrai nom/cote de l'adversaire humain dans le
        # PGN — jamais pour l'IA (opponent_name vide alors, build_pgn_headers
        # retombe sur l'ancien nom d'IA par défaut).
        opponent_name = "" if self._opponent_is_ai else self.opponent_name
        cadence_folder_name = pgn_cadence_folder_name(self.clock_limit_s, self.clock_increment_s)
        # Issue #349, partie 2, points 1/3 : une partie classée est rangée
        # à part (Lichess/Classée/<cadence>/, jamais mêlée aux amicales) et
        # son en-tête Event le dit explicitement — jamais "amicale" pour
        # une partie classée (c'était le cas avant cette issue : l'en-tête
        # disait toujours "amicale", `self.rated` n'étant pas encore
        # consulté ici). Toujours amicale pour l'IA (jamais classée côté
        # Lichess, voir `self.rated` ci-dessus dans _apply_game_full).
        if self.rated:
            game_type = f"Classée/{cadence_folder_name}"
            event_label = f"Lichess, classée ({cadence_folder_name}) contre un humain"
        elif self._opponent_is_ai:
            game_type = "Amicale"
            event_label = f"Lichess, amicale contre l'IA niveau {self.level}"
        else:
            game_type = "Amicale"
            event_label = "Lichess, amicale contre un humain"
        headers = build_pgn_headers(
            self.game_id, self.player_name, self.user_color or "white", self.level,
            self.clock_limit_s, self.clock_increment_s, result, date_utc,
            opponent_name=opponent_name, event_label=event_label,
            user_rating=self.user_rating, opponent_rating=self.opponent_rating,
        )
        final_path = build_final_path("Lichess", game_type, headers["White"], headers["Black"])
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
        avant la libération de l'échiquier (faite par l'appelant).

        Issue #331, point 3 : si la fin de partie est provoquée par
        l'adversaire (abandon, temps écoulé, mat, nulle acceptée — jamais
        pour un abandon/une annulation demandés par l'utilisateur, ni pour
        une offre de nulle que l'utilisateur vient lui-même d'accepter, ni
        pour un mat délivré par le propre coup physique de l'utilisateur
        (son dernier coup joué est alors la cause directe et visible de la
        fin, pas un évènement Lichess passif), ni pour une fin non
        demandée/silencieuse déjà traitée autrement (voir `skip`), la
        moitié de l'échiquier côté adversaire reste allumée : cette méthode
        se contente de calculer `self.opponent_caused_end` (jamais bloquant
        ici — des appelants directs, notamment les tests, invoquent cette
        méthode isolément et doivent toujours la voir retourner
        immédiatement) ; c'est run() qui bloque ensuite sur
        _wait_for_game_over_ack() avant de rendre la main à l'appelant (qui
        libère alors l'échiquier) — sinon le `finally` du lanceur
        (game_manager_modes/lichess.py, nl_inst.turn_off_all_leds() juste
        avant nl_inst.disconnect()) éteindrait le signal en quelques
        millisecondes, bien avant que l'utilisateur ne l'ait vu."""
        result = pgn_result(self._status, self._winner)
        logger.info("Lichess : partie terminée (statut=%s, résultat=%s).", self._status, result)
        if not self._aborted:
            try:
                self._save_pgn(result)
            except Exception as exc:
                logger.warning("Sauvegarde PGN Lichess échouée (hors _save_pgn) : %s", exc)

        unexpected = self._is_unexpected_end()
        skip = self._back_menu_requested or unexpected
        ended_by_users_own_mate = (
            self._status == "mate" and self._last_move_mover_color == self.user_color
        )
        # self._status doit être un statut de fin RÉEL (mat/abandon/temps
        # écoulé/nulle...) — jamais "created"/"started" : certains tests
        # (et, en théorie, un fil interrompu avant toute vraie fin) forcent
        # game_over=True sans faire transiter _status, ce qui ne doit
        # jamais déclencher l'attente d'acquittement (issue #331, point 3).
        is_real_end_status = self._status in (_FINISHED_WITH_WINNER | _FINISHED_DRAW)
        self.opponent_caused_end = (
            is_real_end_status
            and not self._user_initiated_end
            and not self._user_just_accepted_draw
            and not ended_by_users_own_mate
            and not skip
        )
        if self.opponent_caused_end:
            self._light_opponent_half(f"fin de partie — statut={self._status}")
            self._maybe_beep_opponent(f"fin de partie — statut={self._status}", double=True)
        else:
            try:
                self.nl_inst.turn_off_all_leds()
            except Exception as exc:
                logger.debug("Extinction LEDs (fin partie Lichess) échouée : %s", exc)

        try:
            title_key, title_vars = self._title_for_status()
            hist_fens, hist_moves = self._history_from_board()
            payload = {
                "title_key": title_key, "title_vars": title_vars,
                "result": result, "source": "lichess", "skip": skip,
                "history_fen": hist_fens, "history_moves": hist_moves,
                "opponent_caused_end": self.opponent_caused_end,
                "opponent_cause_key": (
                    _OPPONENT_END_CAUSE_KEYS.get(self._status, _OPPONENT_END_CAUSE_DEFAULT_KEY)
                    if self.opponent_caused_end else None
                ),
                "rated": self.rated,
                # Issue #347, partie 2, point 2 : le dernier coup physique
                # n'a pas été accepté par Lichess (partie déjà terminée
                # côté serveur à sa réception) — jamais dans le PGN
                # enregistré ci-dessus (_submit_move ne pousse jamais le
                # coup localement avant confirmation du flux).
                "last_move_rejected": self._last_move_rejected_after_game_over,
            }
            send_event("game_over", payload)
            if not skip:
                set_app_state("game_over", payload)
            if unexpected:
                self._notify_unexpected_end()
            if self.rated and is_real_end_status:
                self._maybe_fetch_new_rating()
        except Exception as exc:
            logger.error("Lichess : notification de fin de partie échouée : %s", exc)
            self._game_log.exception(exc, context="_finalize (notification de fin de partie)")

    # Délais (s) de la lecture de la nouvelle cote ci-dessous — "court
    # délai d'attente" demandé par l'issue #349, partie 1, point 3 : un
    # premier essai après un court délai (le temps que Lichess recalcule
    # les deux cotes côté serveur), puis UNE seule nouvelle tentative si la
    # cote lue est encore identique à celle de départ.
    _NEW_RATING_INITIAL_DELAY_S = 1.5
    _NEW_RATING_RETRY_DELAY_S = 4.0

    def _maybe_fetch_new_rating(self) -> None:
        """Issue #349, partie 1, point 3 : « nouvelle cote » et variation
        par rapport à la cote de départ, en fin de partie classée, en
        meilleur effort. Remplace entièrement l'ancienne lecture ajoutée
        par #344 (GameClient.fetch_rating_diff, retirée — voir rapport de
        clôture #349 pour la discussion garder/remplacer/compléter) : celle-
        ci rouvrait le flux général d'évènements et attendait un évènement
        `gameFinish` dont la doc officielle ne garantit ni l'arrivée ni le
        délai — Alain avait déjà constaté qu'elle manquait souvent. Cette
        version-ci lit `GameClient.fetch_my_rating` (lecture PUBLIQUE de
        /api/user/<id>, aucun jeton ni scope supplémentaire nécessaire),
        pour la cote de la cadence jouée — une opération bien plus simple
        à réessayer. Tentative dans un fil dédié (jamais bloquant pour
        _finalize ni pour l'écran de fin de partie déjà affiché par
        send_event("game_over", ...) ci-dessus) ; rien n'est envoyé au
        navigateur si la valeur n'arrive pas, reste douteuse (jamais
        d'entier), ou si `self.user_rating`/`self._my_username` sont
        inconnus — jamais de valeur devinée."""
        username = self._my_username
        start_rating = self.user_rating
        if not username or start_rating is None:
            self._game_log.state_change(
                "nouvelle cote non tentée (identifiant ou cote de départ inconnus)."
            )
            return
        speed_key = speed_key_for_clock(self.clock_limit_s, self.clock_increment_s)

        def _worker():
            try:
                time.sleep(self._NEW_RATING_INITIAL_DELAY_S)
                new_rating = self.client.fetch_my_rating(username, speed_key)
                if new_rating == start_rating:
                    time.sleep(self._NEW_RATING_RETRY_DELAY_S)
                    new_rating = self.client.fetch_my_rating(username, speed_key)
            except Exception as exc:
                # fetch_my_rating() ne devrait jamais lever (meilleur
                # effort déjà garanti en interne) — défense en profondeur
                # identique à seek.py::_read_event_stream : une exception
                # imprévue dans ce fil secondaire ne doit jamais rester
                # seulement visible dans le terminal, ni faire planter quoi
                # que ce soit (l'écran de fin de partie est déjà affiché).
                logger.error(
                    "Lichess : exception imprévue pendant la lecture de la nouvelle cote.",
                    exc_info=True,
                )
                self._game_log.exception(exc, context="fil de lecture de la nouvelle cote")
                return
            if not isinstance(new_rating, int):
                self._game_log.state_change(
                    "nouvelle cote non obtenue (absente, réseau, ou délai dépassé)."
                )
                return
            diff = new_rating - start_rating
            self._game_log.state_change(
                f"nouvelle cote reçue — {new_rating} (variation {diff:+d})."
            )
            send_event("lichess_new_rating", {"new_rating": new_rating, "rating_diff": diff})
        threading.Thread(target=_worker, daemon=True, name="lichess_new_rating").start()

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
