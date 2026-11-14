"""
nicsoft/core/game_manager_modes/lichess.py — AlChess

Lanceur du mode Lichess (issue #309, étape L2a ; réordonnancement issue
#311). Sur le modèle du lanceur Humain contre Humain
(game_manager_modes/humain.py) : thread, état d'application, événements
vers l'interface, nettoyage en fin de session.

Ordre de lancement (issue #311, point 1) — jamais de pression de temps
avant que l'utilisateur ne soit prêt : la couleur "aléatoire" est résolue
localement avant tout appel à Lichess ; la partie n'est créée chez
Lichess qu'après confirmation de la position de départ (sans limite de
temps, bouton de retour au menu toujours disponible) et, si l'utilisateur
joue les blancs, qu'après son premier coup physique (là encore sans
limite de temps — aucune partie Lichess n'existe avant cet instant, la
contrainte de premier coup de Lichess ne s'applique donc jamais aux
blancs). Si l'utilisateur joue les noirs, la partie est créée
immédiatement après la confirmation de la position : l'IA joue aussitôt
son premier coup (signal sonore + LED + compte à rebours, voir
modes/lichess/game.py) et c'est alors à l'utilisateur de répondre dans le
délai imposé par Lichess.

Pas de mode virtuel pour Lichess (l'échiquier physique est requis) et
aucun moteur d'échecs n'est importé ici ni dans nicsoft.modes.lichess.game
(règle de fair-play Lichess).
"""

import logging
import queue
import random
import threading
import time

import chess

from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import (
    send_event, set_app_state, get_app_state, check_board_presence_silent,
    get_action_queue, app_state_proxy as web_server,
)
from nicsoft.core.game_manager_modes.state import (
    logger, set_nl_inst_ref, _menu_toast_data,
)
from nicsoft.core.config_manager import load_config
from nicsoft.modes.lichess.errors import (
    LichessApiError,
    LichessAuthError,
    LichessNetworkError,
    LichessRateLimitError,
)
from nicsoft.modes.lichess.game_client import GameClient, is_game_over, moves_from_state

logger_lichess = logging.getLogger("niclink.lichess")

# Préréglages de cadence proposés à l'écran de configuration — issue #309,
# point 1 (dont 90+30 pour les parties longues visées par Alain).
CLOCK_PRESETS = {
    "10+0":  (600, 0),
    "15+10": (900, 10),
    "30+0":  (1800, 0),
    "60+0":  (3600, 0),
    "90+30": (5400, 30),
}
DEFAULT_CLOCK_PRESET = "15+10"


def _fetch_ongoing_games(token: str):
    """Appel réseau partagé par check_lichess_resumable() et le garde-fou de
    création (_refuse_create_if_games_ongoing ci-dessous) — jamais
    d'exception propagée : None si l'appel échoue ou si le statut n'est pas
    "ok" (jeton absent/refusé, réseau, limite de requêtes), liste (possibly
    vide) sinon. Jamais de message alarmant à l'appelant dans le cas None
    (issue #323, point 1 ; étendu issue #325)."""
    try:
        from nicsoft.modes.lichess.client import get_ongoing_games
        result = get_ongoing_games(token)
    except Exception as exc:
        logger_lichess.warning(
            "Lichess : détection de partie(s) en cours échouée (%s).", type(exc).__name__,
        )
        return None
    if result.get("status") != "ok":
        logger_lichess.info(
            "Lichess : liste des parties en cours indisponible (statut=%s).",
            result.get("status"),
        )
        return None
    return result.get("games") or []


def check_lichess_resumable() -> None:
    """Détecte les parties Lichess en cours du compte (issue #323, point 1 ;
    étendu à toutes les parties — pas seulement la plus urgente — par
    l'issue #325, points 1 et 2) — appelée à l'ouverture du menu Lichess
    (jamais en boucle), jamais bloquante pour l'écran (délai court côté
    get_ongoing_games), et à nouveau après un abandon depuis la liste
    (abandon_lichess_game) pour rafraîchir l'écran. Jamais de message
    alarmant si pas de jeton, pas de réseau ou erreur : simplement aucune
    partie affichée (le formulaire de nouvelle partie reste accessible)."""
    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        send_event("lichess_resumable", {"available": False, "games": []})
        return
    games = _fetch_ongoing_games(token)
    if games is None:
        send_event("lichess_resumable", {"available": False, "games": []})
        return
    if not games:
        logger_lichess.info("Lichess : aucune partie en cours (compte).")
        send_event("lichess_resumable", {"available": False, "games": []})
        return
    logger_lichess.info(
        "Lichess : %d partie(s) en cours détectée(s) (%s).",
        len(games), ", ".join(g["game_id"] for g in games),
    )
    send_event("lichess_resumable", {"available": True, "games": games})


def _refuse_create_if_games_ongoing(token: str) -> list | None:
    """Garde-fou juste avant de créer une nouvelle partie (issue #325, point
    4) : redemande la liste des parties en cours — y compris celles créées
    ailleurs (lichess.org, téléphone) depuis l'ouverture de l'écran Lichess,
    pas seulement celles déjà connues côté AlChess. Ce n'est pas un doublon
    de l'instance unique du serveur (#320, single_instance.py) : il s'agit
    de l'état du compte chez Lichess, pas du nombre de processus AlChess.

    Retourne la liste (non vide) des parties qui font refuser la création,
    ou None si la création peut continuer (aucune partie en cours, ou liste
    impossible à obtenir — dans ce dernier cas, on laisse démarrer comme
    avant plutôt que de bloquer sur une panne réseau, voir rapport de
    clôture)."""
    games = _fetch_ongoing_games(token)
    if not games:
        return None
    return games


class _BackMenuDuringWait(Exception):
    """L'utilisateur a demandé le retour au menu pendant l'attente de la
    position ou du premier coup physique — aucune partie Lichess n'existe
    encore à ce stade (issue #311, point 1). on_action() (server.py) force
    déjà _app_state à "menu" dès ce clic (les états "position_initiale" et
    "lichess_wait_first_move" ne sont pas relayés à action_queue) : rien
    d'autre à annuler côté Lichess."""


class _ResumeToPositionSetup(Exception):
    """Après une reconnexion de l'échiquier pendant l'attente du premier
    coup (blancs), la position relue n'est ni la position de départ ni un
    premier coup légal — retour à l'écran de mise en place (issue #314,
    point 2)."""


# Seuil (secondes) de lectures vides consécutives avant de considérer
# l'échiquier perdu pendant une attente Lichess sans partie encore créée
# (issue #314, point 2) — distinct du seuil en cours de partie (game.py).
_BOARD_LOST_EMPTY_S = 1.5
_RECONNECT_FAST_INTERVAL_S = 2.0
_RECONNECT_FAST_DURATION_S = 30.0
_RECONNECT_SLOW_INTERVAL_S = 5.0
_RECONNECT_POLL_STEP_S = 0.2
# Délai de stabilisation avant d'afficher "coup non reconnu" (issue #314,
# point 3) — laisse le temps à l'utilisateur de finir de poser sa pièce.
_UNRECOGNIZED_MOVE_DELAY_S = 3.0

# Délai total de réessai d'ouverture de l'échiquier physique avant de
# conclure à son absence (issue #317, point 2). Essai réel d'Alain : une
# relance quelques secondes après un retour au menu depuis l'écran
# d'attente échouait avec "échiquier non détecté" alors que le plateau
# était bien présent et qu'une relance faite plus tard fonctionnait — un
# seul essai immédiat, sans aucun délai de grâce après la libération
# précédente. Cause probable (non vérifiable sans matériel) : rien ne
# garantit que le plateau Chessnut ait fini de se réinitialiser côté
# firmware/USB juste après le "upload mode" envoyé par disconnect()
# (hid_backend.py) — connect() peut alors ne pas (encore) le retrouver via
# hid.enumerate(). Retenter pendant quelques secondes couvre ce cas sans
# modifier driver.py ni la règle d'accès USB unique : chaque essai crée un
# nouveau NicLinkManager, dont connect() (hid_backend.py) ferme déjà tout
# handle existant avant d'en ouvrir un nouveau, sérialisé par son propre
# verrou — jamais deux essais d'ouverture en même temps.
_BOARD_OPEN_RETRY_TOTAL_S = 5.0
_BOARD_OPEN_RETRY_INTERVAL_S = 1.0

# Essai réel d'Alain (13/11/2026, 09:20:14, issue #319, point 4) : le tout
# premier essai d'ouverture échoue avec "board connection error." alors que
# hid_backend.connect() (la poignée de main USB elle-même, journalisée
# depuis #317) a bien réussi en 2,2s — établi par lecture du code (sans
# matériel pour le rejouer) : NicLinkManager.connect() (driver.py, non
# modifié ici) ne laisse ensuite que 2×thread_sleep_delay pour qu'un
# premier get_fen() renvoie un FEN non vide avant de lever RuntimeError
# (→ ce SystemExit) ; create_board() (board_adapter.py) construit ce
# NicLinkManager avec thread_sleep_delay=0.1, donc ~0,2s de grâce après une
# poignée de main qui a déjà pris 2,2s — probablement trop court pour que le
# firmware du plateau ait fini de démarrer l'envoi des paquets de position.
# Signal envoyé à l'interface par cet échec : AUCUN — _open_board_with_retry()
# (ci-dessous) l'avale silencieusement et retente ; aucun send_event ni
# set_app_state n'est déclenché avant l'épuisement de
# _BOARD_OPEN_RETRY_TOTAL_S (atteint ici au second essai, 09:20:18). Ce
# premier échec est donc indépendant de l'annulation observée à 09:20:37
# (voir _discard_stale_browser_actions ci-dessous pour cette dernière).
# Non corrigé ici (documentation seule, conformément à la consigne « ne pas
# toucher driver.py ») : élargir le délai de grâce changerait
# thread_sleep_delay pour tous les modes (humain, pédagogique, exercices...),
# pas seulement Lichess, sans pouvoir le vérifier sans l'échiquier réel.


def _open_board_with_retry(logger_name: str):
    """Ouvre l'échiquier physique (create_board) en retentant pendant
    _BOARD_OPEN_RETRY_TOTAL_S si create_board lève SystemExit("board
    connection error.") — jamais pour une autre cause, qui remonte
    immédiatement (issue #317, point 2). Journalise l'heure (via le
    formateur de log existant) et le résultat de chaque essai, pour que la
    cause d'un échec soit lisible dans niclink.log la prochaine fois sans
    avoir à relancer NICLINK_LOG=DEBUG. Ne relit jamais le FEN elle-même
    après un essai réussi (hid_backend.py::connect() journalise déjà le FEN
    lu pendant la poignée de main) : un appel get_fen() de plus ici
    consommerait une lecture USB inutile — négligeable sur le vrai
    plateau, mais un vrai piège pour les doubles de test scriptés dont
    get_fen() avance un index à chaque appel."""
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            nl_inst = create_board(virtual=False, logger_name=logger_name)
        except SystemExit as e:
            if "board connection error" not in str(e):
                raise
            elapsed = time.monotonic() - start
            if elapsed >= _BOARD_OPEN_RETRY_TOTAL_S:
                logger_lichess.error(
                    f"Lichess : échiquier introuvable après {attempt} essai(s) "
                    f"d'ouverture sur {elapsed:.1f}s — abandon."
                )
                raise
            logger_lichess.warning(
                f"Lichess : ouverture échiquier échouée (essai {attempt}, "
                f"{elapsed:.1f}s écoulées depuis le premier essai) — "
                f"nouvel essai dans {_BOARD_OPEN_RETRY_INTERVAL_S:.0f}s."
            )
            time.sleep(_BOARD_OPEN_RETRY_INTERVAL_S)
            continue
        logger_lichess.info(f"Lichess : échiquier physique ouvert (essai {attempt}).")
        return nl_inst


def _board_module_connected(nl_inst) -> bool:
    """True si le module de lecture se déclare connecté — toujours True si
    l'échiquier (réel ou double de test) n'expose pas cette information,
    pour ne jamais bloquer sur un simple attribut manquant."""
    nl_interface = getattr(nl_inst, "nl_interface", None)
    is_conn = getattr(nl_interface, "is_connected", None)
    if is_conn is None:
        return True
    try:
        return bool(is_conn())
    except Exception:
        return True


def _discard_stale_browser_actions() -> None:
    """Vide action_queue juste avant de démarrer la boucle de jeu Lichess
    (issue #319, point 2) — même geste déjà fait par les autres modes
    (humain.py, pedagogique.py : « vidage de la queue avant le début de
    partie »), jusqu'ici absent du lanceur Lichess.

    action_queue est globale et partagée par tous les modes. on_action()
    (server.py) y met un "back_menu" dès qu'il est cliqué pendant
    "connecting"/"playing"/"game_over"/... — y compris depuis l'écran de
    fin de la partie PRÉCÉDENTE, où plus personne ne lit la queue (cette
    partie-là est déjà finalisée). Sans ce vidage, c'est
    LichessGame._process_browser_actions() de la partie SUIVANTE qui le lit,
    dès son tout premier passage, avant même le premier événement de flux —
    exactement le scénario constaté par Alain le 13/11/2026 à 09:20:37
    (« partie annulée, moins de 2 coups ») sans qu'il ait rien demandé lui-même
    pour CETTE partie. Établi par lecture du code (le code ne permet pas
    d'identifier laquelle des deux fenêtres — écran de fin de partie
    précédente, ou clic pendant l'attente de CETTE partie — a produit l'action
    trouvée ce jour-là ; les deux sont possibles et corrigées par ce vidage).

    Une vraie action reçue APRÈS ce point (donc après le tout début réel de
    la partie, puisque c'est l'appel juste suivant) est seule prise en compte
    par LichessGame — voir game.py::_process_browser_actions()."""
    _aq = get_action_queue()
    discarded_types = []
    while True:
        try:
            stale = _aq.get_nowait()
        except queue.Empty:
            break
        discarded_types.append(stale.get("type", "?"))
    if discarded_types:
        logger_lichess.info(
            "Lichess : %d action(s) périmée(s) écartée(s) avant le début de la "
            "partie (%s) — laissée(s) par l'écran précédent, non demandée(s) "
            "pour cette partie.",
            len(discarded_types), ", ".join(discarded_types),
        )


def _read_board_fen_once(nl_inst) -> str:
    """Lecture ponctuelle du FEN (partie plateau seule), chaîne vide en cas
    d'erreur ou d'absence de données — jamais d'exception propagée."""
    try:
        raw = nl_inst.get_fen()
    except Exception:
        return ""
    return raw.strip().split()[0] if raw else ""


def _squares_differing(board_fen_a: str, board_fen_b: str) -> list:
    """Cases dont la pièce diffère entre deux FEN board-only — utilisé pour
    signaler les cases en cause d'un coup non reconnu (issue #314, point 3)."""
    try:
        a = chess.Board(board_fen_a + " w - - 0 1")
        b = chess.Board(board_fen_b + " w - - 0 1")
    except ValueError:
        return []
    return [chess.square_name(sq) for sq in chess.SQUARES if a.piece_at(sq) != b.piece_at(sq)]


def _reconnect_board_or_menu(nl_inst) -> None:
    """Affiche la bannière « Reconnexion de l'échiquier… », journalise, puis
    tente de rouvrir la connexion USB toutes les 2s pendant 30s puis toutes
    les 5s, jusqu'au succès ou au retour au menu demandé par l'utilisateur
    (issue #314, point 2). `nl_inst.connect()` applique déjà les protections
    de #292 (fermeture de l'ancien handle avant la nouvelle ouverture,
    sérialisée par un verrou dans hid_backend — un seul essai à la fois).
    Ne lève jamais d'exception de renoncement : seul _BackMenuDuringWait
    interrompt cette attente."""
    logger_lichess.warning("Lichess : échiquier perdu pendant l'attente — tentative de reconnexion.")
    send_event("lichess_wait_board_lost", {})
    start = time.monotonic()
    try:
        while True:
            if get_app_state() == "menu":
                raise _BackMenuDuringWait()
            try:
                nl_inst.connect()
                restart = getattr(nl_inst, "_start_fen_reader", None)
                if restart is not None:
                    restart()
            except Exception as e:
                logger_lichess.debug(f"Lichess : tentative de reconnexion échiquier échouée : {e}")
            else:
                if _board_module_connected(nl_inst):
                    logger_lichess.info("Lichess : échiquier reconnecté.")
                    return
            elapsed = time.monotonic() - start
            interval = (_RECONNECT_FAST_INTERVAL_S if elapsed < _RECONNECT_FAST_DURATION_S
                        else _RECONNECT_SLOW_INTERVAL_S)
            waited = 0.0
            while waited < interval:
                if get_app_state() == "menu":
                    raise _BackMenuDuringWait()
                time.sleep(_RECONNECT_POLL_STEP_S)
                waited += _RECONNECT_POLL_STEP_S
    finally:
        send_event("lichess_wait_board_ok", {})


def _wait_initial_position_lichess(nl_inst, color: str) -> None:
    """Variante de _wait_initial_position_web (state.py) sans limite de
    temps et annulable par "back_menu" (issue #311, point 1). Une lecture
    vide prolongée (>1.5s) ou un module qui ne se déclare plus connecté
    déclenche une reconnexion automatique plutôt qu'un abandon silencieux
    (issue #314, point 2) : jamais de partie créée avant que l'échiquier
    ne soit de nouveau lisible. `color` (déjà résolue, jamais "random" à ce
    stade) est transmise à l'écran de mise en place pour qu'il s'oriente du
    point de vue de l'utilisateur (issue #315, point 3)."""
    initial_fen = chess.Board().board_fen()
    first_check = True
    empty_since = None
    while True:
        if get_app_state() == "menu":
            raise _BackMenuDuringWait()
        board_fen = _read_board_fen_once(nl_inst)
        board_lost = not board_fen or not _board_module_connected(nl_inst)
        if board_lost:
            if empty_since is None:
                empty_since = time.monotonic()
            elif time.monotonic() - empty_since >= _BOARD_LOST_EMPTY_S:
                _reconnect_board_or_menu(nl_inst)
                empty_since = None
                first_check = True
            else:
                time.sleep(0.2)
            continue
        empty_since = None
        if board_fen == initial_fen:
            nl_inst.turn_off_all_leds()
            set_app_state("connecting")
            time.sleep(0.3)
            return
        if first_check:
            first_check = False
            try:
                nl_inst.signal_lights(1)
            except Exception as e:
                # signal LED cosmétique — best-effort, voir state.py::_wait_initial_position_web.
                logger.debug(f"signal_lights cosmétique a échoué (Lichess) : {e}")
        set_app_state("position_initiale", {"fen": board_fen, "color": color})
        time.sleep(0.5)


def _wait_first_move_white_lichess(nl_inst, legal_move_for_hardware) -> str:
    """Attend, sans limite de temps, le premier coup physique de
    l'utilisateur (blancs) — aucune partie Lichess n'existe encore à ce
    stade, donc aucune contrainte de temps Lichess ne s'applique (issue
    #311, point 1). Annulable par "back_menu" (voir
    _wait_initial_position_lichess). Reconnexion automatique de l'échiquier
    en cas de lecture vide prolongée (issue #314, point 2) ; message « coup
    non reconnu » si la position diffère de la position de départ sans
    correspondre à un premier coup légal (issue #314, point 3). Retourne le
    coup détecté en UCI, ou lève _ResumeToPositionSetup si la reprise après
    reconnexion montre une position qu'il faut remettre en place."""
    set_app_state("lichess_wait_first_move")
    start_board = chess.Board()
    empty_since = None
    unrecognized_since = None
    unrecognized_notified = False
    last_unrecognized_fen = None
    while True:
        if get_app_state() == "menu":
            raise _BackMenuDuringWait()
        hw_fen = _read_board_fen_once(nl_inst)
        board_lost = not hw_fen or not _board_module_connected(nl_inst)
        if board_lost:
            if empty_since is None:
                empty_since = time.monotonic()
            elif time.monotonic() - empty_since >= _BOARD_LOST_EMPTY_S:
                _reconnect_board_or_menu(nl_inst)
                resumed_fen = _read_board_fen_once(nl_inst)
                if resumed_fen == start_board.board_fen():
                    empty_since = None
                    unrecognized_since = None
                    unrecognized_notified = False
                    last_unrecognized_fen = None
                    time.sleep(0.05)
                    continue
                resumed_move = legal_move_for_hardware(start_board, resumed_fen) if resumed_fen else None
                if resumed_move is not None:
                    logger_lichess.info(f"Lichess : premier coup déjà présent après reconnexion ({resumed_move.uci()}).")
                    return resumed_move.uci()
                logger_lichess.info("Lichess : position illisible après reconnexion — retour à la mise en place.")
                raise _ResumeToPositionSetup()
            else:
                time.sleep(0.2)
            continue
        empty_since = None
        if hw_fen == start_board.board_fen():
            unrecognized_since = None
            unrecognized_notified = False
            last_unrecognized_fen = None
            time.sleep(0.05)
            continue
        move = legal_move_for_hardware(start_board, hw_fen)
        if move is not None:
            return move.uci()
        if hw_fen != last_unrecognized_fen:
            last_unrecognized_fen = hw_fen
            unrecognized_since = time.monotonic()
            unrecognized_notified = False
        elif not unrecognized_notified and time.monotonic() - unrecognized_since >= _UNRECOGNIZED_MOVE_DELAY_S:
            squares = _squares_differing(start_board.board_fen(), hw_fen)
            send_event("lichess_toast", {
                "message_key": "lichess.coup_non_reconnu",
                "vars": {"squares": ", ".join(squares) if squares else "?"},
                "type": "warning",
            })
            logger_lichess.info(f"Lichess : coup non reconnu pendant l'attente du premier coup (cases : {squares}).")
            unrecognized_notified = True
        time.sleep(0.05)


def launch_lichess(config: dict) -> None:
    current_state = web_server._app_state
    if current_state not in ("menu", "config_lichess"):
        logger.info(f"Lancement Lichess refusé : mode déjà actif ({current_state}).")
        send_event("lichess_toast", {"message_key": "toast.lichess_mode_actif", "type": "warning"})
        return

    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data("toast.lichess_no_token"))
        return

    level = max(1, min(8, int(config.get("level", 1) or 1)))
    cadence_key = config.get("cadence", DEFAULT_CLOCK_PRESET)
    clock_limit_s, clock_increment_s = CLOCK_PRESETS.get(cadence_key, CLOCK_PRESETS[DEFAULT_CLOCK_PRESET])
    chosen_color = config.get("color", "random")
    player_name = (config.get("player") or "Vous").strip() or "Vous"
    logger_lichess.info(
        f"Lichess : lancement demandé — niveau={level} cadence={cadence_key} "
        f"couleur={chosen_color} joueur={player_name}"
    )

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    t = threading.Thread(
        target=_run_lichess,
        args=(token, level, clock_limit_s, clock_increment_s, chosen_color, cadence_key, player_name, _error),
        daemon=True,
    )
    t.start()
    t.join()
    if _error["occurred"]:
        time.sleep(1.0)
        target_state = _error.get("return_to") or "menu"
        web_server._app_state = target_state
        set_app_state(target_state, _menu_toast_data(_error["toast_key"] or "toast.lichess_error"))
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")
    if web_server._app_state == "menu":
        # Rafraîchit l'état réel du plateau au retour menu (issue #310, point
        # 5) — même précaution que humain.py : la libération USB par
        # nl_inst.disconnect() (plus bas) peut être suivie de peu par un
        # nouveau lancement de mode, mieux vaut que l'état affiché soit à
        # jour plutôt que celui, potentiellement périmé, d'avant la partie.
        threading.Thread(target=check_board_presence_silent, daemon=True).start()


def _run_lichess(token, level, clock_limit_s, clock_increment_s, chosen_color, cadence_key,
                  player_name, _error=None):
    from nicsoft.modes.lichess.game import LichessGame, legal_move_for_hardware

    # Tirage de couleur de jeu (pile ou face) — aucun usage cryptographique.
    resolved_color = chosen_color if chosen_color in ("white", "black") else random.choice(("white", "black"))  # noqa: S311

    nl_inst = None
    try:
        nl_inst = _open_board_with_retry("NicLink_lichess")
        _wait_initial_position_lichess(nl_inst, resolved_color)
        logger_lichess.info("Lichess : position de départ confirmée.")
        set_nl_inst_ref(nl_inst)

        first_move_uci = None
        if resolved_color == "white":
            while True:
                try:
                    first_move_uci = _wait_first_move_white_lichess(nl_inst, legal_move_for_hardware)
                    break
                except _ResumeToPositionSetup:
                    logger_lichess.info(
                        "Lichess : position illisible après reconnexion — retour à l'écran de mise en place."
                    )
                    _wait_initial_position_lichess(nl_inst, resolved_color)
            logger_lichess.info(f"Lichess : premier coup physique détecté ({first_move_uci}), création de la partie.")

        # Garde-fou « une seule partie à la fois » (issue #325, point 4) —
        # juste avant de créer, pas à l'ouverture du menu : attrape aussi
        # une partie créée ailleurs (lichess.org, téléphone) entre-temps.
        # Pour les blancs, ce point arrive APRÈS le premier coup physique
        # (déjà joué, irréversible) — le refus renvoie à l'écran de
        # configuration plutôt que de perdre les réglages choisis.
        ongoing = _refuse_create_if_games_ongoing(token)
        if ongoing:
            logger_lichess.info(
                "Lichess : création refusée — partie(s) en cours détectée(s) (%s).",
                ", ".join(g["game_id"] for g in ongoing),
            )
            if _error is not None:
                _error["occurred"] = True
                _error["toast_key"] = "toast.lichess_partie_en_cours_refus"
                _error["return_to"] = "config_lichess"
            return

        client = GameClient(token)
        if resolved_color == "white":
            # La partie n'existe qu'à partir d'ici : un échec de création ne
            # doit pas renvoyer au menu en perdant les réglages déjà choisis
            # (le premier coup physique vient d'être joué) — retour à
            # l'écran de configuration Lichess (issue #311, point 1).
            try:
                created = client.create_ai_game(
                    level=level, clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s,
                    color="white",
                )
            except (LichessAuthError, LichessRateLimitError, LichessNetworkError, LichessApiError) as e:
                logger_lichess.error(f"Lichess : création de partie échouée après le premier coup : {e}")
                if _error is not None:
                    _error["occurred"] = True
                    _error["toast_key"] = "toast.lichess_error"
                    _error["return_to"] = "config_lichess"
                return
        else:
            created = client.create_ai_game(
                level=level, clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s,
                color="black",
            )
        game_id = created.get("id", "")
        if not game_id:
            raise LichessNetworkError("réponse Lichess sans identifiant de partie")
        logger_lichess.info(
            f"Lichess : partie créée ({game_id}), niveau={level} "
            f"cadence={clock_limit_s}+{clock_increment_s} couleur={resolved_color}"
        )

        if resolved_color == "white":
            client.play_move(game_id, first_move_uci)
            logger_lichess.info(f"Lichess : coup envoyé {first_move_uci} (premier coup, avant ouverture du flux).")

        game = LichessGame(
            nl_inst, client, game_id, level=level, player_name=player_name,
            clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s,
            chosen_color_setting=chosen_color, cadence_key=cadence_key,
        )
        # Vidage juste avant le tout début réel de la partie (issue #319,
        # point 2) : voir _discard_stale_browser_actions ci-dessus — place
        # le vidage au plus près de game.start() pour laisser le moins de
        # place possible à une action réellement concurrente de la création
        # de partie (fenêtre résiduelle, déjà présente dans ce même ordre
        # chez humain.py/pedagogique.py).
        _discard_stale_browser_actions()
        web_server._app_state = "playing"
        set_app_state("playing")
        logger_lichess.info(f"Partie Lichess : {player_name} vs IA niveau {level} ({game_id}), couleur={resolved_color}")
        # LichessGame.start() exécute toute la partie de façon synchrone (le
        # vrai threading vit dans ce thread-ci, voir modes/lichess/game.py) :
        # à son retour la partie est déjà terminée et finalisée (PGN, état
        # game_over). Ne JAMAIS appeler game.join() ensuite — le Thread
        # natif n'a jamais été démarré (start() est surchargée), join()
        # lèverait inconditionnellement "cannot join thread before it is
        # started" (issue #310, point 1).
        game.start()

    except _BackMenuDuringWait:
        pass
    except LichessAuthError as e:
        logger_lichess.error(f"Jeton Lichess refusé (HTTP {e.status_code}).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = ("toast.lichess_missing_scope" if e.status_code == 403
                                    else "toast.lichess_invalid_token")
    except LichessRateLimitError:
        logger_lichess.warning("Limite de requêtes Lichess atteinte.")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_rate_limited"
    except (LichessNetworkError, LichessApiError) as e:
        logger_lichess.error(f"Erreur Lichess au lancement de la partie : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_network_error"
    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("Erreur mode Lichess : échiquier non détecté.")
            if _error is not None:
                _error["occurred"] = True
                _error["toast_key"] = "toast.board_not_found"
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except ConnectionError as e:
        logger.error(f"Erreur de connexion échiquier (Lichess) : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.position_timeout" if "Timeout" in str(e) else "toast.board_not_found"
        send_event("board_error", {"message": str(e)})
    except Exception as e:
        logger.error(f"Erreur inattendue mode Lichess : {e}")
        import traceback
        traceback.print_exc()
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_error"
        send_event("popup", {"message": f"Erreur : {e}"})
    finally:
        if nl_inst:
            try:
                nl_inst.turn_off_all_leds()
            except Exception as e:
                logger.debug(f"Extinction LEDs (fin Lichess) échouée : {e}")
            _disconnect_start = time.monotonic()
            try:
                nl_inst.disconnect()
                logger_lichess.info(
                    f"Lichess : échiquier physique libéré ({time.monotonic() - _disconnect_start:.2f}s)."
                )
            except Exception as e:
                logger.warning(f"Déconnexion échiquier échouée (Lichess) : {e}")
        if web_server._app_state not in ("game_over", "menu"):
            web_server._app_state = "menu"


# ── Reprise d'une partie en cours (issue #323, étape L2b) ───────────────────
#
# Livraison limitée au cas le plus simple, comme permis par la consigne en
# repli (« si la tâche est trop grosse, livrer d'abord la reprise pour une
# partie contre l'IA ») : seules les parties amicales contre l'IA Lichess,
# variante standard, sont proposées (voir client.get_ongoing_games). Le
# mode jouable existant (LichessGame) est réutilisé tel quel pour la partie
# elle-même — seul l'écran de mise en place (reconstruction de la position
# physique) est nouveau, porté par LichessGame(resuming=True) et son
# _tick_resume_setup() (voir modes/lichess/game.py).


def _peek_game_full(client: GameClient, game_id: str):
    """Ouvre le flux de la partie juste le temps de lire le premier
    gameFull (couleur, niveau IA, cadence, coups déjà joués, statut) —
    referme explicitement cette connexion avant que LichessGame n'ouvre la
    sienne pour jouer la partie (deux connexions courtes plutôt qu'une
    tentative de partage d'un même flux entre ce module et game.py, pour
    rester simple et robuste). None si le flux se ferme sans jamais envoyer
    de gameFull (réponse Lichess inattendue)."""
    stream = client.stream_game(game_id)
    try:
        for event in stream:
            if event.get("type") == "gameFull":
                return event
    finally:
        stream.close()
    return None


def launch_lichess_resume(action: dict) -> None:
    """Reprend la partie Lichess en cours proposée par check_lichess_resumable()
    (issue #323, point 3) — même garde d'état et même schéma d'erreurs que
    launch_lichess()."""
    current_state = web_server._app_state
    if current_state not in ("menu", "config_lichess"):
        logger.info(f"Reprise Lichess refusée : mode déjà actif ({current_state}).")
        send_event("lichess_toast", {"message_key": "toast.lichess_mode_actif", "type": "warning"})
        return

    game_id = (action.get("game_id") or "").strip()
    if not game_id:
        logger.warning("Lichess : reprise demandée sans identifiant de partie — ignorée.")
        return

    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data("toast.lichess_no_token"))
        return

    player_name = (action.get("player") or "Vous").strip() or "Vous"
    logger_lichess.info(f"Lichess : reprise demandée ({game_id}).")

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    t = threading.Thread(
        target=_run_lichess_resume, args=(token, game_id, player_name, _error), daemon=True,
    )
    t.start()
    t.join()
    if _error["occurred"]:
        time.sleep(1.0)
        target_state = _error.get("return_to") or "menu"
        web_server._app_state = target_state
        set_app_state(target_state, _menu_toast_data(_error["toast_key"] or "toast.lichess_error"))
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")
    if web_server._app_state == "menu":
        threading.Thread(target=check_board_presence_silent, daemon=True).start()


def _run_lichess_resume(token, game_id, player_name, _error=None):
    from nicsoft.modes.lichess.game import LichessGame

    nl_inst = None
    try:
        client = GameClient(token)
        full_event = _peek_game_full(client, game_id)
        if full_event is None:
            raise LichessNetworkError("réponse Lichess sans état de partie")

        white = full_event.get("white") or {}
        black = full_event.get("black") or {}
        user_color = "black" if white.get("aiLevel") is not None else "white"
        level = (white.get("aiLevel") if user_color == "black" else black.get("aiLevel")) or 1
        # Issue #325, point 7 : le champ `clock` (top-level de gameFull) ne
        # contient que la cadence CHOISIE (initial/increment), jamais le
        # temps RESTANT — et il est absent pour une partie par
        # correspondance (`daysPerTurn` à la place, doc officielle
        # GameFullEvent.yaml, lue le 14/11/2026). L'ancien code faisait
        # `int(clock.get("initial") or 0) // 1000`, qui retombait
        # silencieusement à 0 dans ce cas — exactement le mécanisme du bug
        # observé par Alain (bandeau « 0 min restantes » et pendule 0:00
        # rouge) : ce 0 devenait la valeur de départ des pendules
        # (LichessGame.__init__) et n'était jamais corrigé si l'événement de
        # flux suivant manquait lui aussi de wtime/btime (même absence pour
        # une correspondance). Point 1 ci-dessus exclut déjà ces parties de
        # la liste proposée ; en défense supplémentaire, le temps RESTANT
        # réel (state.wtime/state.btime, déjà présents dans l'aperçu
        # gameFull) est transmis à LichessGame pour servir de valeur de
        # départ fiable — plus jamais un 0 par défaut silencieux.
        clock = full_event.get("clock")
        clock_limit_s = int((clock or {}).get("initial") or 0) // 1000
        clock_increment_s = int((clock or {}).get("increment") or 0) // 1000
        state = full_event.get("state") or {}
        initial_wtime_ms = state.get("wtime")
        initial_btime_ms = state.get("btime")
        clock_known = isinstance(clock, dict) and initial_wtime_ms is not None and initial_btime_ms is not None
        if not clock_known:
            logger_lichess.warning(
                "Lichess : reprise (%s) — champ horloge absent ou incomplet "
                "(clock=%s, wtime=%s, btime=%s) : temps restant affiché comme inconnu plutôt qu'une valeur fausse.",
                game_id, clock, initial_wtime_ms, initial_btime_ms,
            )
        status = state.get("status", "started")
        already_over = is_game_over(status)
        logger_lichess.info(
            "Lichess : reprise (%s) — état reçu (couleur=%s, statut=%s, coups=%d).",
            game_id, user_color, status, len(moves_from_state(state)),
        )

        nl_inst = _open_board_with_retry("NicLink_lichess")
        set_nl_inst_ref(nl_inst)

        game = LichessGame(
            nl_inst, client, game_id, level=level, player_name=player_name,
            clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s,
            chosen_color_setting=user_color, cadence_key="",
            resuming=not already_over,
            initial_wtime_ms=initial_wtime_ms, initial_btime_ms=initial_btime_ms,
            clock_known=clock_known,
        )

        if already_over:
            logger_lichess.info(
                "Lichess : reprise (%s) — partie déjà terminée (statut=%s), enregistrement du PGN final.",
                game_id, status,
            )
        else:
            logger_lichess.info(
                "Lichess : reprise (%s) — écran de mise en place (position cible à reconstruire).",
                game_id,
            )

        _discard_stale_browser_actions()
        web_server._app_state = "playing"
        set_app_state("playing")
        logger_lichess.info(f"Lichess : reprise démarrée ({game_id}), couleur={user_color}, niveau={level}.")
        game.start()
        logger_lichess.info("Lichess : reprise (%s) — jeu normal repris après mise en place.", game_id)

    except _BackMenuDuringWait:
        pass
    except LichessAuthError as e:
        logger_lichess.error(f"Jeton Lichess refusé pendant la reprise (HTTP {e.status_code}).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = ("toast.lichess_missing_scope" if e.status_code == 403
                                    else "toast.lichess_invalid_token")
    except LichessRateLimitError:
        logger_lichess.warning("Limite de requêtes Lichess atteinte (reprise).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_rate_limited"
    except (LichessNetworkError, LichessApiError) as e:
        logger_lichess.error(f"Erreur Lichess pendant la reprise de partie : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_network_error"
    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("Erreur reprise Lichess : échiquier non détecté.")
            if _error is not None:
                _error["occurred"] = True
                _error["toast_key"] = "toast.board_not_found"
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except ConnectionError as e:
        logger.error(f"Erreur de connexion échiquier (reprise Lichess) : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.position_timeout" if "Timeout" in str(e) else "toast.board_not_found"
        send_event("board_error", {"message": str(e)})
    except Exception as e:
        logger.error(f"Erreur inattendue pendant la reprise Lichess : {e}")
        import traceback
        traceback.print_exc()
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_error"
        send_event("popup", {"message": f"Erreur : {e}"})
    finally:
        if nl_inst:
            try:
                nl_inst.turn_off_all_leds()
            except Exception as e:
                logger.debug(f"Extinction LEDs (fin reprise Lichess) échouée : {e}")
            _disconnect_start = time.monotonic()
            try:
                nl_inst.disconnect()
                logger_lichess.info(
                    f"Lichess : échiquier physique libéré ({time.monotonic() - _disconnect_start:.2f}s)."
                )
            except Exception as e:
                logger.warning(f"Déconnexion échiquier échouée (reprise Lichess) : {e}")
        if web_server._app_state not in ("game_over", "menu"):
            web_server._app_state = "menu"


# ── Abandon depuis la liste des parties en cours (issue #325, point 3) ─────
#
# Abandonner une partie qui n'est PAS celle en cours de jeu dans AlChess (cas
# normal ici : aucune LichessGame n'existe encore, l'utilisateur clique
# "Abandonner" depuis l'écran de liste avant toute reprise) ne passe donc
# jamais par LichessGame._request_resign_or_abort() — il n'y a pas
# d'instance. La même logique est reproduite directement avec le client
# Lichess seul : un bref aperçu du flux (_peek_game_full, déjà utilisé par
# la reprise) donne le nombre de coups déjà joués pour choisir entre
# annulation (< 2 coups) et abandon, exactement comme le ferait
# LichessGame une fois la partie chargée ; puis un seul appel REST
# (abort()/resign()). La liste est ensuite rafraîchie (check_lichess_resumable)
# pour que l'écran se mette à jour sans action supplémentaire de
# l'utilisateur.

def abandon_lichess_game(action: dict) -> None:
    game_id = (action.get("game_id") or "").strip()
    if not game_id:
        logger.warning("Lichess : abandon depuis la liste demandé sans identifiant de partie — ignoré.")
        return
    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        send_event("lichess_toast", {"message_key": "toast.lichess_no_token", "type": "warning"})
        return

    logger_lichess.info("Lichess : abandon depuis la liste demandé (%s).", game_id)
    client = GameClient(token)
    try:
        full_event = _peek_game_full(client, game_id)
    except (LichessAuthError, LichessRateLimitError, LichessNetworkError, LichessApiError) as exc:
        logger_lichess.warning(
            "Lichess : abandon depuis la liste — lecture de l'état de partie échouée (%s) : %s.",
            game_id, exc,
        )
        send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning"})
        return
    if full_event is None:
        logger_lichess.warning("Lichess : abandon depuis la liste — état de partie introuvable (%s).", game_id)
        send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning"})
        return

    moves = moves_from_state(full_event.get("state") or {})
    aborting = len(moves) < 2
    try:
        if aborting:
            client.abort(game_id)
        else:
            client.resign(game_id)
    except (LichessApiError, LichessRateLimitError, LichessNetworkError) as exc:
        logger_lichess.warning(
            "Lichess : abandon depuis la liste refusé par Lichess (%s, %s) : %s.",
            game_id, "annulation" if aborting else "abandon", exc,
        )
        send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning"})
        return

    logger_lichess.info(
        "Lichess : partie %s depuis la liste (%s, %d coup(s) joué(s)).",
        "annulée" if aborting else "abandonnée", game_id, len(moves),
    )
    check_lichess_resumable()
