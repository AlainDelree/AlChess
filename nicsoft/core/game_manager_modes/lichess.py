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

Pas de mode virtuel pour les PARTIES Lichess (l'échiquier physique est
requis) et aucun moteur d'échecs n'est importé ici ni dans
nicsoft.modes.lichess.game (règle de fair-play Lichess). Les PROBLÈMES
(puzzles, section dédiée plus bas) ont en revanche un mode virtuel depuis
l'issue #364 (_run_lichess_puzzle_virtual, sans échiquier) en plus du mode
échiquier existant (_run_lichess_puzzle, inchangé) — même règle de
fair-play dans les deux cas.
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
    get_action_queue, get_action, app_state_proxy as web_server,
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
    detect_color_balance_refusal,
    translate_api_detail,
)
from nicsoft.modes.lichess.game_client import GameClient, is_game_over, moves_from_state
from nicsoft.modes.lichess.puzzle_themes import (
    PUZZLE_THEME_KEYS, PUZZLE_PHASE_KEYS, DEFAULT_PUZZLE_PHASE, compute_default_theme,
)
from nicsoft.modes.lichess.puzzle_history import last_known_puzzle_rating

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

# Table partagée statut → clé de toast (issue #368, partie 1) — réutilisée
# par launch_lichess_puzzle (vérification du jeton avant lancement),
# _run_lichess_puzzle et _run_lichess_puzzle_virtual (statuts retournés par
# get_next_puzzle en cours de session) : une seule table, jamais un second
# mécanisme de classification par appelant. "network_error" (réseau
# réellement indisponible) et "lichess_error" (réponse HTTP d'erreur de
# Lichess, réseau disponible) restent toujours distincts de "invalid"
# (jeton refusé) — jamais confondus, contrairement au défaut d'avant cette
# issue (voir client.py::test_token).
_LICHESS_TOKEN_STATUS_TOAST_KEYS = {
    "invalid": "toast.lichess_invalid_token",
    "missing_scope": "toast.lichess_puzzle_missing_scope",
    "rate_limited": "toast.lichess_rate_limited",
    "network_error": "toast.lichess_network_error",
    "lichess_error": "toast.lichess_error",
}


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


_lichess_network_check_lock = threading.Lock()


def check_lichess_network_status() -> None:
    """Vérifie si Lichess est joignable (issue #368, partie 1) — appelée à
    l'ouverture de l'écran Lichess, à intervalle raisonnable tant qu'il
    reste ouvert, et sur les évènements de connexion du navigateur (voir
    app.js). Jamais de message de jeton ici : seul le statut RÉSEAU est
    communiqué (`lichess_network_status`), distinct du statut du jeton — un
    jeton refusé (`test_token` -> "invalid") ou une erreur applicative
    Lichess (-> "lichess_error"/"rate_limited") signifient tous deux que le
    réseau fonctionne, donc `available=True` ; seul un vrai échec réseau
    (`test_token` -> "network_error") vaut `available=False`. Verrou non
    bloquant : un appel reçu pendant qu'une vérification est déjà en cours
    est simplement ignoré (jamais de requêtes empilées) — le prochain
    évènement (minuterie ou connexion navigateur, côté JS) en déclenchera
    une nouvelle."""
    if not _lichess_network_check_lock.acquire(blocking=False):
        return
    try:
        token = (load_config().get("lichess_token") or "").strip()
        if not token:
            # Rien à tester (écran normalement inaccessible sans jeton,
            # issue #365) — pas d'alarme réseau sans objet.
            send_event("lichess_network_status", {"available": True})
            return
        from nicsoft.modes.lichess.client import test_token
        result = test_token(token)
        send_event("lichess_network_status", {"available": result.get("status") != "network_error"})
    finally:
        _lichess_network_check_lock.release()


def check_lichess_puzzle_dashboard() -> None:
    """Tableau de bord des problèmes par thème (issue #388, point 2) —
    appelée une seule fois à l'ouverture de l'écran Lichess (comme
    check_lichess_resumable ci-dessus), en arrière-plan, jamais bloquante
    pour l'affichage. Calcule aussi le thème par défaut (point faible —
    voir puzzle_themes.compute_default_theme) côté serveur, pour que
    l'écran n'ait qu'à l'appliquer.

    Toujours un évènement `lichess_puzzle_dashboard` envoyé, même en cas
    d'échec (jeton absent, réseau coupé, droit manquant) : `available`
    distingue alors les deux cas pour l'écran, qui reste utilisable sans
    statistiques ni thème par défaut calculé (jamais de message d'erreur
    bloquant, voir le rapport de clôture). Issue #393, point 1 : le
    résultat de CHAQUE lecture est désormais journalisé (INFO, jamais le
    jeton ni le contenu complet) — succès (nombre de thèmes, période) ET
    échec (statut), pour pouvoir confirmer après coup qu'un appel a
    réellement abouti."""
    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        send_event("lichess_puzzle_dashboard", {"available": False, "themes": {}, "default_theme": ""})
        return
    from nicsoft.modes.lichess.puzzle_client import get_puzzle_dashboard, PUZZLE_DASHBOARD_DEFAULT_DAYS
    try:
        result = get_puzzle_dashboard(token)
    except Exception as exc:
        logger_lichess.warning("Lichess : tableau de bord des problèmes indisponible (%s).", type(exc).__name__)
        send_event("lichess_puzzle_dashboard", {"available": False, "themes": {}, "default_theme": ""})
        return
    if result.get("status") != "ok":
        logger_lichess.info("Lichess : tableau de bord des problèmes indisponible (statut=%s).", result.get("status"))
        send_event("lichess_puzzle_dashboard", {"available": False, "themes": {}, "default_theme": ""})
        return
    themes = result.get("themes") or {}
    # Issue #393, point 1 : journalisation systématique d'une lecture
    # réussie (jamais le contenu complet, seulement un résumé) — avant
    # cette issue, un succès ne laissait AUCUNE trace, rendant impossible
    # de savoir si l'appel avait réellement abouti.
    logger_lichess.info(
        "Lichess : tableau de bord des problèmes lu (statut=ok, thèmes=%d, période=%dj).",
        len(themes), PUZZLE_DASHBOARD_DEFAULT_DAYS,
    )
    default_theme = compute_default_theme(themes)
    send_event("lichess_puzzle_dashboard", {"available": True, "themes": themes, "default_theme": default_theme})


def check_lichess_puzzle_daily_counts() -> None:
    """Compteur du jour par type de série (issue #390, point 2) — appelée
    comme check_lichess_puzzle_dashboard ci-dessus, à chaque ouverture de
    l'écran de réglages des problèmes. Contrairement au tableau de bord,
    purement local (aucun réseau, aucun jeton requis) : lit l'historique
    local des problèmes (puzzle_history.daily_counts_by_type), jamais
    bloquante, jamais d'échec possible (voir cette fonction — fichier
    absent/vide/illisible -> compteurs à zéro, jamais d'exception)."""
    from nicsoft.modes.lichess.puzzle_history import daily_counts_by_type
    send_event("lichess_puzzle_daily_counts", daily_counts_by_type())


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


# Issue #383, point 1 : attente bornée de l'ARRÊT d'un fil de lanceur
# Lichess (recherche humaine, IA, reprise, problèmes) — jamais de la
# partie elle-même : tant que l'état applicatif reste actif ("connecting",
# "lichess_seeking", "playing", "paused"), aucune limite n'est imposée, une
# partie amicale ou classée pouvant durer plusieurs heures. La borne ne
# démarre qu'à l'instant où l'état quitte ces valeurs actives — c'est-à-dire
# après une demande de sortie de l'utilisateur ("back_menu" bascule déjà
# _app_state à "menu" dès le clic, voir server.py::on_action, avant même que
# ce fil n'ait fini son nettoyage) ou la fin naturelle de la partie
# (LichessGame bascule _app_state à "game_over" avant de retourner, voir
# game.py). Valeur choisie (15s) : seule mesure réelle disponible pour ce
# nettoyage (essai du 13/11/2026, issue #319 — poignée de main USB 2,2s +
# libération échiquier, l'ensemble sous 5s), multipliée par une marge large
# pour couvrir aussi la fermeture des flux réseau (point 2 ci-dessous) sans
# laisser l'utilisateur plusieurs dizaines de secondes devant un écran figé.
_LICHESS_STOP_TIMEOUT_S = 15.0
# "lichess_puzzle_session_summary" (issue #387, point 2) : écran de bilan
# affiché sans limite de temps (l'utilisateur peut prendre le temps de le
# lire) — doit rester une attente active au même titre que
# "lichess_puzzle_playing", jamais bornée par _LICHESS_STOP_TIMEOUT_S.
#
# Issue #392, point 1 (étude #391, point 1) : "position_initiale" et
# "lichess_wait_first_move" manquaient ici — essai réel du 26/11/2026,
# lancement d'une partie classée avec l'échiquier physique en désordre :
# le fil attendait normalement la position physique (aucune sortie
# demandée, aucune partie créée côté Lichess), mais le compte à rebours de
# _LICHESS_STOP_TIMEOUT_S démarrait quand même dès l'entrée dans
# "position_initiale" (absent de cette liste) — faux positif, retour forcé
# au menu après 15s avec le message "l'arrêt de la session a pris trop de
# temps". Liste désormais recensée par relecture complète des lanceurs
# (game_manager_modes/lichess.py::_wait_initial_position_lichess(_puzzle)/
# _wait_first_move_white_lichess, chacun des quatre launch_lichess*) :
# TOUT état posé par un fil de lanceur APPARTIENT soit à cette liste (vraie
# attente, jamais bornée), soit à _LICHESS_EXIT_STATES ci-dessous (sortie
# demandée ou fin de partie/session, bornée) — jamais ni l'un ni l'autre
# (garde statique, voir test_issue392_point1_lichess_active_states_guard.py).
_LICHESS_ACTIVE_STATES = ("connecting", "lichess_seeking", "playing", "paused",
                          "position_initiale", "lichess_wait_first_move",
                          "lichess_puzzle_playing", "lichess_puzzle_session_summary")
# États de sortie demandée ou atteinte pendant l'exécution d'un lanceur
# Lichess — c'est précisément LEUR apparition qui doit démarrer le compte à
# rebours de _join_lichess_launcher_thread (jamais une attente légitime) :
# "menu" (retour demandé par l'utilisateur, ou absence de jeton détectée
# avant même le lancement du fil), "config_lichess" (retour aux réglages
# depuis l'écran de mise en place d'un problème, issue #389), "game_over"
# (fin de partie, LichessGame::_finalize, avant de retourner).
_LICHESS_EXIT_STATES = ("menu", "config_lichess", "game_over")


def _join_lichess_launcher_thread(t: threading.Thread, label: str) -> bool:
    """Attend la fin du fil `t` d'un lanceur Lichess — voir le commentaire
    ci-dessus pour la distinction entre partie active (jamais bornée) et
    phase d'arrêt (bornée à _LICHESS_STOP_TIMEOUT_S). Retourne True si le
    fil s'est terminé normalement ; False s'il a été abandonné après le
    délai, auquel cas l'appelant doit s'arrêter immédiatement (l'état
    applicatif, le toast d'erreur et le rafraîchissement de l'échiquier sont
    déjà pris en charge ici) — ne JAMAIS relire `_error` dans ce cas, le fil
    abandonné pouvant encore y écrire. `t` reste toujours daemon=True côté
    appelant : un fil abandonné ne bloque jamais l'arrêt du programme
    (Ctrl+C / SIGTERM)."""
    stop_deadline = None
    while t.is_alive():
        if stop_deadline is None and web_server._app_state not in _LICHESS_ACTIVE_STATES:
            stop_deadline = time.monotonic() + _LICHESS_STOP_TIMEOUT_S
        if stop_deadline is not None and time.monotonic() >= stop_deadline:
            logger_lichess.error(
                "Lichess : arrêt du fil '%s' non terminé %.0fs après la sortie demandée "
                "(état actuel=%s) — abandon du fil, retour forcé au menu.",
                label, _LICHESS_STOP_TIMEOUT_S, web_server._app_state,
            )
            # Libère ce qui peut l'être sans toucher au fil abandonné :
            # jamais d'appel nl_inst.disconnect()/turn_off_all_leds() d'ici
            # (le fil abandonné peut encore le détenir — un second accès
            # concurrent violerait la règle d'accès USB exclusif) ; la
            # référence partagée est simplement effacée pour qu'aucun autre
            # code ne la croie valide, et le prochain create_board() (règle
            # existante de hid_backend.py : la nouvelle connexion ferme
            # l'ancienne) reprendra la main sur l'échiquier physique.
            set_nl_inst_ref(None)
            web_server._app_state = "menu"
            set_app_state("menu", _menu_toast_data("toast.lichess_arret_bloque", persistent=True))
            threading.Thread(target=check_board_presence_silent, daemon=True).start()
            return False
        t.join(timeout=0.2)
    return True


def launch_lichess(config: dict) -> None:
    current_state = web_server._app_state
    # Issue #383, point 4 : log d'entrée inconditionnel (avant tout garde
    # d'état) — pour qu'un futur blocage distingue "jamais appelé" de
    # "appelé puis refusé/bloqué plus loin", sans réactiver NICLINK_LOG=DEBUG.
    logger_lichess.info(
        "Lichess : entrée launch_lichess (état actuel=%s, opponent_type=%s).",
        current_state, config.get("opponent_type") or "ai",
    )
    if current_state not in ("menu", "config_lichess"):
        logger.info(f"Lancement Lichess refusé : mode déjà actif ({current_state}).")
        send_event("lichess_toast", {"message_key": "toast.lichess_mode_actif", "type": "warning"})
        return
    # Issue #392, point 2 : nouveau lancement accepté — arrête tout
    # balayage de partie orpheline encore en cours d'une recherche
    # précédente annulée (voir _start_orphan_sweep_after_cancel), pour ne
    # jamais risquer d'annuler une partie légitime née de CE lancement.
    _bump_launch_generation()

    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data("toast.lichess_no_token"))
        return

    # Issue #327, point 1 : choix du type de partie sur l'écran Lichess —
    # "ai" (comportement inchangé ci-dessous, toujours amicale : Lichess ne
    # classe jamais une partie contre son IA, aucun paramètre "rated" sur
    # /api/challenge/ai) ou "human" (recherche d'un adversaire humain, voir
    # _launch_lichess_human plus bas — classée ou amicale selon le choix de
    # l'écran, issue #344 point 2).
    if (config.get("opponent_type") or "ai") == "human":
        _launch_lichess_human(config, token)
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
    if not _join_lichess_launcher_thread(t, "launch_lichess"):
        return
    if _error["occurred"]:
        time.sleep(1.0)
        target_state = _error.get("return_to") or "menu"
        web_server._app_state = target_state
        set_app_state(target_state, _menu_toast_data(
            _error["toast_key"] or "toast.lichess_error",
            _error.get("toast_vars"), _error.get("toast_persistent", False),
        ))
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


# ── Recherche d'un adversaire humain (issue #327, étape L2b) ────────────────
#
# Réutilise le mode jouable existant (LichessGame, modes/lichess/game.py) tel
# quel : seules la recherche elle-même (seek.py::SeekSession) et l'orientation
# vers ce lanceur sont nouvelles. Ordre (point 2) : position physique
# confirmée D'ABORD (comme pour l'IA), puis recherche — jamais l'inverse.
# Contrairement à la couleur "aléatoire" pour l'IA (résolue localement avant
# tout appel réseau, issue #311, conservée ainsi car la partie contre l'IA
# n'est jamais concernée par l'équilibrage des couleurs ci-dessous), la
# recherche humaine NE résout PLUS "aléatoire" localement (issue #330 :
# essai réel du 14/11/2026, une recherche 15+10 blancs refusée par Lichess
# avec « You must also play some games as Black » — HTTP 400). Un choix
# "aléatoire" local envoyait TOUJOURS une couleur précise à board/seek, donc
# toujours soumise à la règle d'équilibre des couleurs de Lichess (établi
# par lecture du code source public de lila, modules/lobby/src/main/
# BoardApiHookStream.scala::mustPlayAsColor, lu le 14/11/2026 : le refus est
# sauté entièrement quand la couleur demandée est "random" — paramètre
# `color` laissé vide ici, "Better left empty to automatically get 50%
# white" selon doc/specs/tags/board/api-board-seek.yaml du dépôt
# lichess-org/api). La position de départ étant la même pour les deux
# camps, l'écran de mise en place avant la recherche n'a pas besoin de
# connaître la couleur réelle (orientation arbitraire, voir
# `display_color` ci-dessous) : l'orientation réelle (échiquier, noms,
# pendules) n'est appliquée qu'au vrai début de partie, une fois la couleur
# confirmée par Lichess (LichessGame/lichess_init, déjà basé sur cette
# couleur confirmée, inchangé par cette issue).
#
# Issue #344, point 2 : `rated` est transmis tel quel à seek.py/board-seek
# depuis le choix de l'écran (case « Partie classée », cochée par défaut,
# sans objet contre l'IA) — aucune restriction de cadence supplémentaire
# liée au classé (voir seek.py::start()). La valeur réellement confirmée
# par Lichess (champ `rated` du premier gameFull, jamais cette variable
# locale) est celle utilisée partout ailleurs (affichage, journal) — voir
# modes/lichess/game.py::_apply_game_full.

# Vitesses Lichess acceptées pour une recherche humaine (point 1 ; établi
# dans #326, repris ici) — jamais Blitz ni Bullet.
_HUMAN_SEEK_ALLOWED_SPEEDS = frozenset({"rapid", "classical"})

# Issue #328, point 2 : essai réel du 14/11/2026 — une partie avait bien été
# créée chez Lichess alors que le flux de recherche s'était fermé sans
# `gameStart` encore lu par AlChess (ordre/délai entre les deux non garanti
# par la documentation officielle, voir seek.py). Avant de conclure à
# l'absence d'adversaire, on patiente cette durée pour laisser `gameStart`
# arriver, puis — s'il n'est toujours pas là — on consulte la liste des
# parties en cours du compte (même appel que le garde-fou "une seule partie
# à la fois" ci-dessus) : ne jamais laisser une partie ouverte chez Lichess
# sans que l'utilisateur le sache.
_SEEK_CLOSED_GRACE_S = 5.0

# Issue #383, point 3 (étude #382) : course structurelle entre deux fils de
# SeekSession — `_mark_found()` (fil de lecture du flux d'évènements) ne
# dépend jamais de `_cancelled`, par construction (seek.py) : si ce fil a
# déjà lu `gameStart` au moment où CE fil-ci traite une demande de retour
# au menu, `cancel()` devient un no-op (recherche déjà "trouvée") et
# l'évènement "found" reste dans la file sans jamais être consommé — la
# partie existe bel et bien chez Lichess, mais plus personne ne la joue
# (risque établi par l'étude, non reproduit : un adversaire pourrait
# attendre indéfiniment). Fenêtre bornée après cancel() pour repérer ce cas
# précis — pas un délai réseau (déjà couvert par _SEEK_CLOSED_GRACE_S
# ci-dessus, situation distincte) : seulement le temps qu'un évènement déjà
# en cours de traitement dans l'autre fil termine d'être empilé.
_ORPHAN_FOUND_GRACE_S = 1.0
_ORPHAN_FOUND_POLL_STEP_S = 0.1


def _reap_late_found_game(seek_session) -> dict | None:
    """Draine la file d'évènements pendant une courte fenêtre bornée après
    cancel() pour repérer un évènement "found" arrivé malgré l'annulation
    (voir commentaire de _ORPHAN_FOUND_GRACE_S) — retourne le dict `game`
    du gameStart si trouvé, sinon None (cas normal, largement majoritaire)."""
    deadline = time.monotonic() + _ORPHAN_FOUND_GRACE_S
    while time.monotonic() < deadline:
        ev = seek_session.next_event(timeout=_ORPHAN_FOUND_POLL_STEP_S)
        if ev is not None and ev.get("type") == "found":
            return ev.get("game") or {}
    return None


def _abandon_orphan_game_after_cancel(client: GameClient, game: dict, game_log=None) -> None:
    """Une partie a été trouvée par Lichess APRÈS que l'utilisateur a
    annulé sa recherche (issue #383, point 3) — jamais laisser un
    adversaire attendre un joueur qui ne viendra plus. Aucun coup n'a pu
    être joué par personne à ce stade (gameStart précède toujours tout
    coup) : abort() — le même mécanisme "moins de 2 coups" que
    abandon_lichess_game ci-dessous — doit donc toujours réussir ; resign()
    n'est qu'un filet de sécurité si Lichess le refusait malgré tout."""
    game_id = game.get("id") or game.get("gameId") or ""
    if not game_id:
        logger_lichess.error(
            "Lichess : partie trouvée après annulation de la recherche mais sans identifiant "
            "exploitable dans l'évènement — impossible de l'annuler côté Lichess."
        )
        return
    logger_lichess.error(
        "Lichess : partie %s trouvée après annulation de la recherche par l'utilisateur — "
        "annulation immédiate côté Lichess pour ne pas laisser un adversaire sans joueur.",
        game_id,
    )
    if game_log is not None:
        game_log.state_change(
            f"partie {game_id} trouvée après annulation de la recherche — annulation immédiate."
        )
    try:
        client.abort(game_id)
    except (LichessApiError, LichessRateLimitError, LichessNetworkError) as exc:
        logger_lichess.warning(
            "Lichess : annulation de la partie orpheline %s refusée (%s) — tentative d'abandon.",
            game_id, exc,
        )
        try:
            client.resign(game_id)
        except (LichessApiError, LichessRateLimitError, LichessNetworkError) as exc2:
            logger_lichess.error(
                "Lichess : abandon de secours de la partie orpheline %s également refusé (%s).",
                game_id, exc2,
            )


def _cancel_seek_and_reap_orphan(seek_session, client: GameClient, game_log=None) -> None:
    """Point d'appel unique pour les deux sorties "menu" de la recherche
    humaine (boucle principale et attente de gameStart après seek_closed,
    voir _run_lichess_human) — annule la recherche puis couvre la partie
    orpheline éventuelle (issue #383, point 3)."""
    seek_session.cancel()
    orphan_game = _reap_late_found_game(seek_session)
    if orphan_game:
        _abandon_orphan_game_after_cancel(client, orphan_game, game_log)


# ── Issue #392, point 2 : partie orpheline au-delà de la fenêtre étroite
# de #383 point 3 ────────────────────────────────────────────────────────
#
# _reap_late_found_game ci-dessus ne couvre qu'une partie déjà SIGNALÉE
# ("found" dans la file de SeekSession) au moment de l'annulation — essai
# réel du 26/11/2026 : Lichess avait créé une partie classée 21ms avant la
# fermeture du flux de recherche et 22ms avant l'annulation effective, mais
# le flux n'a jamais signalé "found" (seulement "seek_closed"), donc
# _reap_late_found_game n'avait rien à drainer ; _refuse_create_if_games_ongoing
# (le garde-fou "une seule partie à la fois") n'est lui-même revérifié
# qu'AVANT la PROCHAINE recherche, trop tard pour celle qui vient d'être
# annulée. Une vraie partie classée est restée ouverte chez Lichess,
# jamais jouée par personne, perdue par Alain après l'avoir reprise à son
# insu. Ce balayage élargi, lancé en arrière-plan à chaque annulation,
# comble ce trou en revérifiant la liste des parties en cours à quelques
# reprises espacées — jamais en bloquant le retour au menu.
_ORPHAN_SWEEP_CHECKPOINTS_S = (1.0, 2.0, 4.0, 6.0)
# Moins de 2 demi-coups = aucun coup n'a pu être joué par qui que ce soit —
# seuil choisi pour ne jamais toucher une partie où un coup réel a déjà été
# échangé (comparaison TOUJOURS par identifiant par rapport à la liste
# mémorisée avant la recherche, jamais par ce seul comptage — voir
# _orphan_sweep_worker).
_ORPHAN_SWEEP_MAX_PLIES = 2

# Compteur de génération de lancement — incrémenté à CHAQUE lancement
# Lichess accepté (voir launch_lichess/launch_lichess_resume/
# launch_lichess_puzzle), pour que le balayage ci-dessus s'arrête dès
# qu'un nouveau lancement commence (nouvelle recherche, nouvelle partie),
# et ne risque jamais d'annuler une partie légitime née d'une recherche
# ultérieure.
_launch_generation_lock = threading.Lock()
_lichess_launch_generation = 0


def _bump_launch_generation() -> int:
    global _lichess_launch_generation
    with _launch_generation_lock:
        _lichess_launch_generation += 1
        return _lichess_launch_generation


def _current_launch_generation() -> int:
    with _launch_generation_lock:
        return _lichess_launch_generation


def _ply_count_from_fen(fen: str) -> int | None:
    """Nombre de demi-coups déjà joués, déduit des deux derniers champs du
    FEN complet (`<trait> <droits de roque> <case en passant> <demi-coups
    depuis la dernière prise/poussée de pion> <numéro de coup plein>`) —
    évite de rejouer tout l'historique juste pour ce comptage. None si le
    FEN est absent ou mal formé (ne jamais conclure à tort à "moins de 2
    demi-coups" dans ce cas — voir l'appelant)."""
    if not fen:
        return None
    parts = fen.split()
    if len(parts) < 6:
        return None
    side_to_move, fullmove = parts[1], parts[5]
    if side_to_move not in ("w", "b"):
        return None
    try:
        fullmove_n = int(fullmove)
    except ValueError:
        return None
    return 2 * (fullmove_n - 1) + (1 if side_to_move == "b" else 0)


def _start_orphan_sweep_after_cancel(token: str, pre_search_game_ids, generation: int, game_log=None):
    """Démarre, en arrière-plan (jamais attendu par l'appelant — voir
    _ORPHAN_SWEEP_CHECKPOINTS_S), le balayage élargi de partie orpheline
    après une annulation de recherche humaine. Sans effet si la liste des
    parties avant la recherche n'a pas pu être établie (réseau) : pas de
    base de comparaison fiable, donc aucune action risquée. Retourne le
    fil démarré (ou None si non démarré) — utile aux tests pour l'attendre
    explicitement ; jamais joint par l'appelant en production."""
    if pre_search_game_ids is None:
        logger_lichess.info(
            "Lichess : balayage de partie orpheline non démarré — liste des parties "
            "avant la recherche inconnue (réseau indisponible à ce moment-là)."
        )
        return None
    t = threading.Thread(
        target=_orphan_sweep_worker, args=(token, pre_search_game_ids, generation, game_log), daemon=True,
    )
    t.start()
    return t


def _orphan_sweep_worker(token: str, pre_search_game_ids, generation: int, game_log=None) -> None:
    client = GameClient(token)
    handled_ids = set()
    elapsed = 0.0
    for checkpoint in _ORPHAN_SWEEP_CHECKPOINTS_S:
        time.sleep(max(0.0, checkpoint - elapsed))
        elapsed = checkpoint
        if _current_launch_generation() != generation:
            logger_lichess.info(
                "Lichess : balayage de partie orpheline arrêté (nouveau lancement entre-temps)."
            )
            return
        games = _fetch_ongoing_games(token)
        if games is None:
            continue
        for g in games:
            game_id = g.get("game_id") or ""
            if not game_id or game_id in pre_search_game_ids or game_id in handled_ids:
                # Comparaison TOUJOURS par identifiant : une partie déjà
                # présente avant la recherche n'est jamais touchée, quel
                # que soit son nombre de coups.
                continue
            handled_ids.add(game_id)
            plies = _ply_count_from_fen(g.get("fen") or "")
            if plies is not None and plies >= _ORPHAN_SWEEP_MAX_PLIES:
                logger_lichess.info(
                    "Lichess : partie %s... apparue après annulation de recherche mais déjà "
                    "%d demi-coup(s) — jamais touchée (balayage élargi).", game_id[:8], plies,
                )
                continue
            logger_lichess.warning(
                "Lichess : partie %s... apparue après annulation de recherche humaine "
                "(moins de %d demi-coups) — annulation automatique (balayage élargi).",
                game_id[:8], _ORPHAN_SWEEP_MAX_PLIES,
            )
            if game_log is not None:
                game_log.state_change(
                    f"partie {game_id[:8]}... détectée après annulation de recherche "
                    "(balayage élargi) — annulation automatique côté Lichess."
                )
            try:
                client.abort(game_id)
            except (LichessApiError, LichessRateLimitError, LichessNetworkError) as exc:
                # Jamais resign() ici (contrairement à
                # _abandon_orphan_game_after_cancel ci-dessus) : si
                # l'annulation est refusée, la partie et le bandeau de
                # reprise restent — jamais d'abandon automatique d'une
                # partie que l'utilisateur n'a pas choisi de laisser.
                logger_lichess.warning(
                    "Lichess : annulation automatique de la partie %s... refusée (%s) — "
                    "laissée telle quelle (reprenable).", game_id[:8], exc,
                )
                send_event("lichess_toast", {
                    "message_key": "toast.lichess_orphan_game_laissee", "type": "warning",
                })
                continue
            send_event("lichess_toast", {
                "message_key": "toast.lichess_orphan_game_annulee", "type": "info",
            })


def _classify_seek_error_event(ev: dict) -> tuple:
    """Traduit l'évènement "error" poussé par SeekSession (seek.py,
    `_push_error`) en (clé de message, variables pour l'écran) — issue
    #329, point 2 : essai réel du 14/11/2026, une vraie réponse d'erreur
    de Lichess (TransportHTTPError) affichait le même message « vérifiez
    le réseau » qu'une vraie panne réseau, alors que le réseau et le jeton
    fonctionnaient (une partie contre l'IA avait réussi quelques minutes
    plus tôt) — la cause réelle restait donc invisible à l'écran comme au
    journal. "vérifiez le réseau" n'est renvoyé ici QUE si `status_code`
    est absent (TransportNetworkError/TransportTimeoutError : coupure,
    résolution de nom, délai dépassé — jamais une réponse HTTP de
    Lichess, qui est arrivée). Tous les messages renvoyés par cette
    fonction sont affichés de façon persistante par l'appelant (jamais un
    toast éphémère pour cette famille d'erreurs)."""
    status_code = ev.get("status_code")
    if status_code in (401, 403):
        return "toast.lichess_jeton_refuse", {}
    if status_code == 429:
        # Clé dédiée (distincte de toast.lichess_rate_limited, utilisée par
        # les autres appels Lichess sans le délai exact) : {seconds} est
        # TOUJOURS fourni ici — jamais affiché sans substitution.
        return "toast.lichess_rate_limited_detail", {"seconds": ev.get("retry_after_s") or 60}
    if status_code == 404:
        return "toast.lichess_404", {}
    if status_code == 400:
        detail = ev.get("detail") or ""
        # Issue #330 : refus d'équilibre des couleurs (board/seek, choix
        # précis déjà demandé plusieurs fois) — reconnu sur le texte exact
        # de Lichess (voir errors.py::detect_color_balance_refusal, établi
        # par lecture du code source public de lila) ; sinon, texte de
        # Lichess seul comme avant (point 2). Issue #393, point 2 : le
        # détail n'est plus jamais le texte anglais brut — `detail_key`/
        # `detail_vars` (errors.py::translate_api_detail) laissent app.js
        # choisir la traduction dans la langue courante.
        if detect_color_balance_refusal(detail):
            # La phrase dédiée explique déjà la vraie cause — le détail de
            # Lichess (toujours "must also play some games as ...") n'y
            # ajouterait rien, jamais affiché ici.
            return "toast.lichess_refus_equilibre_couleur", {"detail_key": "", "detail_vars": {}}
        detail_key, detail_vars = translate_api_detail(detail)
        return "toast.lichess_refus_requete", {"detail_key": detail_key, "detail_vars": detail_vars}
    if isinstance(status_code, int) and status_code >= 500:
        return "toast.lichess_indisponible", {}
    return "toast.lichess_network_error", {}


def _launch_lichess_human(config: dict, token: str) -> None:
    from nicsoft.modes.lichess.game import speed_key_for_clock

    # Issue #383, point 4 : log d'entrée inconditionnel — voir launch_lichess.
    logger_lichess.info(
        "Lichess : entrée _launch_lichess_human (état actuel=%s, cadence=%s).",
        web_server._app_state, config.get("cadence", DEFAULT_CLOCK_PRESET),
    )
    cadence_key = config.get("cadence", DEFAULT_CLOCK_PRESET)
    clock_limit_s, clock_increment_s = CLOCK_PRESETS.get(cadence_key, CLOCK_PRESETS[DEFAULT_CLOCK_PRESET])
    speed = speed_key_for_clock(clock_limit_s, clock_increment_s)
    if speed not in _HUMAN_SEEK_ALLOWED_SPEEDS:
        # Ne devrait jamais arriver avec les préréglages proposés par
        # l'écran (tous Rapide/Classique, voir CLOCK_PRESETS) — filet de
        # sécurité si un préréglage futur ne l'était pas (issue #327, point
        # 1 : jamais Blitz/Bullet pour une recherche humaine).
        logger_lichess.error(
            f"Lichess : recherche humaine refusée — cadence {cadence_key} de vitesse {speed} "
            "(seules Rapide/Classique sont acceptées pour un adversaire humain)."
        )
        web_server._app_state = "menu"
        set_app_state("config_lichess", _menu_toast_data("toast.lichess_cadence_invalide"))
        return

    chosen_color = config.get("color", "random")
    player_name = (config.get("player") or "Vous").strip() or "Vous"
    # Issue #344, point 2 : défaut prudent à False (jamais une partie
    # classée involontaire) si le champ venait à manquer — l'écran envoie
    # toujours ce champ explicitement (case cochée par défaut côté
    # interface, voir app.js::startGameLichess).
    rated = bool(config.get("rated", False))
    logger_lichess.info(
        f"Lichess : recherche d'adversaire humain demandée — cadence={cadence_key} "
        f"couleur={chosen_color} joueur={player_name} classée={rated}"
    )

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    t = threading.Thread(
        target=_run_lichess_human,
        args=(token, clock_limit_s, clock_increment_s, chosen_color, cadence_key, player_name, _error),
        kwargs={"rated": rated},
        daemon=True,
    )
    t.start()
    if not _join_lichess_launcher_thread(t, "_launch_lichess_human"):
        return
    if _error["occurred"]:
        time.sleep(1.0)
        target_state = _error.get("return_to") or "menu"
        web_server._app_state = target_state
        set_app_state(target_state, _menu_toast_data(
            _error["toast_key"] or "toast.lichess_error",
            _error.get("toast_vars"), _error.get("toast_persistent", False),
        ))
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")
    if web_server._app_state == "menu":
        threading.Thread(target=check_board_presence_silent, daemon=True).start()


def _run_lichess_human(token, clock_limit_s, clock_increment_s, chosen_color, cadence_key,
                        player_name, _error=None, rated=False):
    from nicsoft.modes.lichess.game import LichessGame
    from nicsoft.modes.lichess.game_log import GameLog
    from nicsoft.modes.lichess.seek import SeekSession

    # Issue #330 : "aléatoire" n'est plus résolu localement (voir en-tête de
    # section) — `requested_color` est ce qui part réellement vers Lichess
    # (board/seek), vide pour "aléatoire" afin que Lichess choisisse
    # lui-même sans jamais déclencher la règle d'équilibre des couleurs.
    # `display_color` ne sert qu'à l'écran de mise en place avant que la
    # vraie couleur ne soit connue (position de départ identique pour les
    # deux camps — un repli arbitraire n'y change donc rien).
    requested_color = chosen_color if chosen_color in ("white", "black") else ""
    display_color = requested_color or "white"

    nl_inst = None
    seek_session = None
    game_log = None
    try:
        nl_inst = _open_board_with_retry("NicLink_lichess")
        _wait_initial_position_lichess(nl_inst, display_color)
        logger_lichess.info("Lichess : position de départ confirmée (recherche humaine).")
        set_nl_inst_ref(nl_inst)

        # Vrai début de la recherche du point de vue de l'utilisateur (issue
        # #328, point 5) — capturé ICI, avant le garde-fou réseau et avant
        # l'ouverture des deux flux (seek_session.start() ci-dessous, deux
        # appels HTTP bloquants) : essai réel du 14/11/2026, écran affichant
        # "0:03" neuf secondes après la position confirmée — établi par
        # lecture du code, la cause est que le compteur ne démarrait
        # qu'après ces appels réseau (garde-fou "une seule partie" +
        # ouverture des deux flux, trois requêtes séquentielles), sans
        # compter leur propre durée. Compter depuis ICI couvre cette durée
        # de mise en place, cohérent avec "temps écoulé depuis le vrai début
        # de la recherche".
        search_start = time.monotonic()
        # Génération de ce lancement (issue #392, point 2) — figée ICI pour
        # tout le reste de la recherche : un balayage de partie orpheline
        # démarré plus bas compare sa propre génération à la valeur COURANTE
        # (_current_launch_generation()) pour savoir s'il doit s'arrêter —
        # jamais à celle-ci, déjà périmée par construction dès qu'un nouveau
        # lancement commence.
        my_generation = _current_launch_generation()

        # Garde-fou « une seule partie à la fois » (issue #325, point 4 ;
        # repris ici point 2) — juste avant de démarrer la recherche.
        ongoing = _refuse_create_if_games_ongoing(token)
        if ongoing:
            logger_lichess.info(
                "Lichess : recherche humaine refusée — partie(s) en cours détectée(s) (%s).",
                ", ".join(g["game_id"] for g in ongoing),
            )
            if _error is not None:
                _error["occurred"] = True
                _error["toast_key"] = "toast.lichess_partie_en_cours_refus"
                _error["return_to"] = "config_lichess"
            return

        # Liste mémorisée des identifiants déjà en cours AVANT cette
        # recherche (issue #392, point 2) — base de comparaison du balayage
        # de partie orpheline après une éventuelle annulation plus bas
        # (_start_orphan_sweep_after_cancel) : toute partie dont
        # l'identifiant n'y figure pas sera considérée comme née de CETTE
        # recherche. Second appel réseau distinct du garde-fou ci-dessus
        # (qui ne renvoie plus la liste si elle est vide) — None si
        # impossible à obtenir (réseau), auquel cas le balayage ne démarrera
        # pas (aucune base fiable, voir cette fonction).
        pre_search_games = _fetch_ongoing_games(token)
        pre_search_game_ids = (
            frozenset(g["game_id"] for g in pre_search_games) if pre_search_games is not None else None
        )

        client = GameClient(token)
        # Journal dédié (issue #326, point 10 ; étendu ici au cycle de
        # recherche, issue #327 point 6) — créé avant de connaître
        # l'identifiant de partie (inconnu tant qu'aucun adversaire n'est
        # trouvé) : nom de fichier provisoire ("recherche"), mais fichier
        # unique qui couvre déjà démarrage/annulation/appariement puis toute
        # la partie une fois trouvée (passé tel quel à LichessGame).
        game_log = GameLog("recherche")
        client.attach_game_log(game_log)
        seek_session = SeekSession(client, game_log=game_log)

        web_server._app_state = "lichess_seeking"
        set_app_state("lichess_seeking", {
            "cadence": cadence_key, "color": requested_color or "random", "rated": rated,
        })
        seek_session.start(clock_limit_s / 60.0, clock_increment_s, requested_color, rated)

        last_tick_sent = 0.0
        found_game = None
        while found_game is None:
            if get_app_state() == "menu":
                # Annulation demandée par l'utilisateur (bouton "Annuler la
                # recherche") — "lichess_seeking" n'est jamais relayée à
                # action_queue (server.py::on_action, même mécanisme que
                # _BackMenuDuringWait pour position_initiale/
                # lichess_wait_first_move) : seul ce sondage de l'état
                # détecte la demande depuis ce fil.
                _cancel_seek_and_reap_orphan(seek_session, client, game_log)
                _start_orphan_sweep_after_cancel(token, pre_search_game_ids, my_generation, game_log)
                raise _BackMenuDuringWait()
            ev = seek_session.next_event(timeout=0.2)
            now = time.monotonic()
            if now - last_tick_sent >= 1.0:
                last_tick_sent = now
                send_event("lichess_seek_tick", {"elapsed_s": now - search_start})
            if ev is None:
                continue
            etype = ev.get("type")
            if etype == "found":
                found_game = ev.get("game") or {}
            elif etype == "error":
                logger_lichess.warning(
                    "Lichess : recherche humaine interrompue (%s).", ev.get("reason", "?"),
                )
                if _error is not None:
                    toast_key, toast_vars = _classify_seek_error_event(ev)
                    _error["occurred"] = True
                    _error["toast_key"] = toast_key
                    _error["toast_vars"] = toast_vars
                    _error["toast_persistent"] = True
                    _error["return_to"] = "config_lichess"
                return
            elif etype == "seek_closed":
                # Flux de recherche fermé par Lichess sans appariement
                # signalé — NE JAMAIS conclure à un échec ici (issue #328,
                # point 2 : essai réel du 14/11/2026, une partie avait bel
                # et bien été créée chez Lichess alors qu'AlChess concluait
                # à tort à son absence et perdait sa trace). On patiente
                # d'abord _SEEK_CLOSED_GRACE_S pour gameStart (le flux
                # d'évènements reste ouvert, voir seek.py), puis on
                # consulte la liste des parties en cours du compte avant de
                # trancher.
                logger_lichess.info(
                    "Lichess : flux de recherche fermé par Lichess — attente de %.0fs de "
                    "l'évènement de début de partie avant de conclure.", _SEEK_CLOSED_GRACE_S,
                )
                game_log.state_change(
                    "flux de recherche fermé par Lichess sans appariement encore signalé — "
                    f"attente de {_SEEK_CLOSED_GRACE_S:.0f}s de l'évènement gameStart."
                )
                grace_deadline = time.monotonic() + _SEEK_CLOSED_GRACE_S
                while found_game is None and time.monotonic() < grace_deadline:
                    if get_app_state() == "menu":
                        # Même annulation que le sondage principal ci-dessus
                        # (issue #383, point 3) — sort directement plutôt que
                        # de continuer vers la consultation de la liste des
                        # parties en cours, déjà hors sujet pour un retour au
                        # menu explicitement demandé par l'utilisateur.
                        _cancel_seek_and_reap_orphan(seek_session, client, game_log)
                        _start_orphan_sweep_after_cancel(token, pre_search_game_ids, my_generation, game_log)
                        raise _BackMenuDuringWait()
                    ev2 = seek_session.next_event(timeout=0.2)
                    if ev2 is None:
                        continue
                    if ev2.get("type") == "found":
                        found_game = ev2.get("game") or {}
                    elif ev2.get("type") == "error":
                        logger_lichess.warning(
                            "Lichess : flux d'évènements interrompu pendant l'attente de gameStart (%s).",
                            ev2.get("reason", "?"),
                        )
                        break

                if found_game is not None:
                    game_log.state_change("évènement de début de partie reçu pendant l'attente — partie trouvée.")
                    continue  # ré-évalue "while found_game is None" -> sort normalement

                # Toujours pas de gameStart : jamais de conclusion silencieuse
                # (point 2) — même appel que le garde-fou "une seule partie à
                # la fois" plus haut, qui a déjà garanti qu'aucune partie
                # n'existait avant cette recherche.
                game_log.state_change("aucun gameStart reçu — consultation de la liste des parties en cours du compte.")
                ongoing = _fetch_ongoing_games(token)
                if ongoing:
                    logger_lichess.warning(
                        "Lichess : adversaire trouvé mais partie non ouverte normalement — "
                        "%d partie(s) en cours détectée(s) (%s).",
                        len(ongoing), ", ".join(g["game_id"] for g in ongoing),
                    )
                    game_log.state_change(
                        f"partie adoptée depuis la liste des parties en cours ({len(ongoing)}) — "
                        "écran des parties en cours affiché, reprise non proposée (partie humaine, "
                        "issue suivante)."
                    )
                    send_event("lichess_resumable", {"available": True, "games": ongoing})
                    if _error is not None:
                        _error["occurred"] = True
                        _error["toast_key"] = "toast.lichess_seek_partie_non_ouverte"
                        _error["return_to"] = "config_lichess"
                    return

                logger_lichess.info("Lichess : recherche humaine terminée — aucun adversaire trouvé.")
                game_log.state_change(
                    "recherche terminée — aucun adversaire trouvé (confirmé par la liste des parties en cours)."
                )
                if _error is not None:
                    _error["occurred"] = True
                    _error["toast_key"] = "toast.lichess_seek_sans_adversaire"
                    _error["return_to"] = "config_lichess"
                return
            # "waiting" (ligne vide de maintien du flux de recherche) : rien
            # d'autre à faire, la boucle continue (pas de limite de durée).

        game_id = found_game.get("gameId") or found_game.get("id") or ""
        # "color" du gameStart (doc officielle, GameEventInfo.yaml : présent
        # en pratique mais non `required`) porte la vraie couleur assignée
        # par Lichess (fiable même pour une recherche "aléatoire" — c'est
        # précisément ce qui manquait avant cette issue) ; `display_color`
        # n'est qu'un repli défensif si ce champ venait un jour à manquer.
        confirmed_color = found_game.get("color") or display_color
        if not game_id:
            raise LichessNetworkError("évènement gameStart sans identifiant de partie")
        opponent_info = found_game.get("opponent") or {}
        logger_lichess.info(
            "Lichess : adversaire trouvé (%s), couleur=%s, adversaire=%s.",
            game_id, confirmed_color, opponent_info.get("username") or opponent_info.get("id") or "?",
        )
        game_log.state_change(
            f"recherche terminée — adversaire trouvé, game_id={game_id}, couleur={confirmed_color}."
        )

        game = LichessGame(
            nl_inst, client, game_id, level=0, player_name=player_name,
            clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s,
            chosen_color_setting=chosen_color, cadence_key=cadence_key,
            known_user_color=confirmed_color, game_log=game_log,
        )
        _discard_stale_browser_actions()
        web_server._app_state = "playing"
        set_app_state("playing")
        logger_lichess.info(
            "Partie Lichess humaine : %s vs %s (%s), couleur=%s",
            player_name, opponent_info.get("username") or opponent_info.get("id") or "?", game_id, confirmed_color,
        )
        # LichessGame.start() exécute toute la partie de façon synchrone —
        # voir le même commentaire dans _run_lichess ci-dessus (issue #310,
        # point 1) : ne jamais appeler game.join() ensuite.
        game.start()

    except _BackMenuDuringWait:
        pass
    except LichessAuthError as e:
        logger_lichess.error(f"Jeton Lichess refusé pendant la recherche humaine (HTTP {e.status_code}).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = ("toast.lichess_missing_scope" if e.status_code == 403
                                    else "toast.lichess_invalid_token")
    except LichessRateLimitError:
        logger_lichess.warning("Limite de requêtes Lichess atteinte (recherche humaine).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_rate_limited"
    except (LichessNetworkError, LichessApiError) as e:
        logger_lichess.error(f"Erreur Lichess pendant la recherche/partie humaine : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_network_error"
    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("Erreur mode Lichess (humain) : échiquier non détecté.")
            if _error is not None:
                _error["occurred"] = True
                _error["toast_key"] = "toast.board_not_found"
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except ConnectionError as e:
        logger.error(f"Erreur de connexion échiquier (Lichess humain) : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.position_timeout" if "Timeout" in str(e) else "toast.board_not_found"
        send_event("board_error", {"message": str(e)})
    except Exception as e:
        logger.error(f"Erreur inattendue mode Lichess (humain) : {e}")
        import traceback
        traceback.print_exc()
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_error"
        send_event("popup", {"message": f"Erreur : {e}"})
    finally:
        if seek_session is not None:
            # close(), pas cancel() : la cause réelle (trouvé, erreur,
            # annulation utilisateur déjà traitée par son propre cancel()
            # explicite ci-dessus, ou conclusion après la période d'attente)
            # est déjà journalisée par la branche qui a quitté le bloc try —
            # jamais le message "annulée par l'utilisateur" ici, qui serait
            # faux dans tous les cas sauf l'annulation réelle (issue #328,
            # point 4).
            seek_session.close()
        if game_log is not None:
            game_log.close()
        if nl_inst:
            try:
                nl_inst.turn_off_all_leds()
            except Exception as e:
                logger.debug(f"Extinction LEDs (fin Lichess humain) échouée : {e}")
            _disconnect_start = time.monotonic()
            try:
                nl_inst.disconnect()
                logger_lichess.info(
                    f"Lichess : échiquier physique libéré ({time.monotonic() - _disconnect_start:.2f}s)."
                )
            except Exception as e:
                logger.warning(f"Déconnexion échiquier échouée (Lichess humain) : {e}")
        if web_server._app_state not in ("game_over", "menu"):
            web_server._app_state = "menu"


# ── Reprise d'une partie en cours (issue #323, étape L2b ; étendue aux
# parties contre un humain par l'issue #333) ────────────────────────────────
#
# Le mode jouable existant (LichessGame) est réutilisé tel quel pour la
# partie elle-même — règles de nulle, décompte du premier coup, pendules :
# déjà génériques côté IA/humain (voir _apply_game_full/_apply_game_state/
# _compute_action_buttons, pilotés par `_opponent_is_ai`, lui-même déduit
# de `aiLevel` ou, en son absence, de `known_user_color` transmis ici).
# Seul l'écran de mise en place (reconstruction de la position physique)
# est spécifique à la reprise, porté par LichessGame(resuming=True) et son
# _tick_resume_setup() (voir modes/lichess/game.py) — déjà générique lui
# aussi (aucune branche IA/humain).


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
    # Issue #383, point 4 : log d'entrée inconditionnel — voir launch_lichess.
    logger_lichess.info(
        "Lichess : entrée launch_lichess_resume (état actuel=%s, game_id=%s).",
        current_state, (action.get("game_id") or "").strip(),
    )
    if current_state not in ("menu", "config_lichess"):
        logger.info(f"Reprise Lichess refusée : mode déjà actif ({current_state}).")
        send_event("lichess_toast", {"message_key": "toast.lichess_mode_actif", "type": "warning"})
        return
    _bump_launch_generation()  # issue #392, point 2 — voir launch_lichess

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
    # Couleur connue depuis la liste des parties en cours (issue #333,
    # point 2) — champ `color` de chaque entrée de get_ongoing_games(),
    # déjà en possession du navigateur (reçu via l'évènement
    # "lichess_resumable") au moment où l'utilisateur clique "Reprendre" :
    # seul moyen fiable de connaître la couleur d'une partie contre un
    # humain, où ni `white` ni `black` ne porte `aiLevel` (voir
    # _run_lichess_resume). Sans effet pour une partie contre l'IA
    # (déduite comme avant depuis `aiLevel`).
    known_color = (action.get("color") or "").strip()
    logger_lichess.info(f"Lichess : reprise demandée ({game_id}).")

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    t = threading.Thread(
        target=_run_lichess_resume, args=(token, game_id, player_name, known_color, _error), daemon=True,
    )
    t.start()
    if not _join_lichess_launcher_thread(t, "launch_lichess_resume"):
        return
    if _error["occurred"]:
        time.sleep(1.0)
        target_state = _error.get("return_to") or "menu"
        web_server._app_state = target_state
        set_app_state(target_state, _menu_toast_data(
            _error["toast_key"] or "toast.lichess_error",
            _error.get("toast_vars"), _error.get("toast_persistent", False),
        ))
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")
    if web_server._app_state == "menu":
        threading.Thread(target=check_board_presence_silent, daemon=True).start()


def _run_lichess_resume(token, game_id, player_name, known_color="", _error=None):
    from nicsoft.modes.lichess.game import LichessGame
    from nicsoft.modes.lichess.game_log import GameLog

    nl_inst = None
    # Journal dédié (issue #326, point 10 ; étendu au cycle de reprise par
    # l'issue #333, point 6) — créé AVANT même le premier appel réseau
    # (contrairement à LichessGame, qui ne le créerait que plus tard,
    # faute d'appelant lui en fournissant un) : couvre ainsi la demande de
    # reprise et la lecture de la position cible, pas seulement la partie
    # une fois LichessGame construite. Jamais de jeton ni de tchat dedans
    # (GameLog, inchangé).
    game_log = GameLog(game_id)
    game_log.state_change(f"reprise demandée depuis la liste des parties en cours (joueur={player_name}).")
    try:
        client = GameClient(token)
        client.attach_game_log(game_log)
        full_event = _peek_game_full(client, game_id)
        if full_event is None:
            raise LichessNetworkError("réponse Lichess sans état de partie")

        white = full_event.get("white") or {}
        black = full_event.get("black") or {}
        white_ai = white.get("aiLevel")
        black_ai = black.get("aiLevel")
        if white_ai is not None or black_ai is not None:
            # Partie contre l'IA — couleur déduite comme avant #333.
            user_color = "black" if white_ai is not None else "white"
            level = (white_ai if user_color == "black" else black_ai) or 1
        else:
            # Partie contre un humain (issue #333, point 2) : ni `white`
            # ni `black` ne porte `aiLevel` — seul `known_color` (transmis
            # par l'appelant depuis la liste des parties en cours) permet
            # de savoir quel camp est le nôtre. Sans lui, impossible de
            # continuer sans risquer de jouer/orienter le camp adverse :
            # échec contrôlé plutôt qu'une couleur devinée au hasard.
            if known_color not in ("white", "black"):
                logger_lichess.error(
                    "Lichess : reprise (%s) refusée — couleur inconnue pour une partie "
                    "contre un humain (aucune couleur transmise par la liste des parties).",
                    game_id,
                )
                game_log.state_change(
                    "reprise refusée — couleur inconnue pour une partie contre un humain."
                )
                raise LichessNetworkError("couleur inconnue pour une partie contre un humain")
            user_color = known_color
            level = 0
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
        game_log.state_change(
            f"position cible lue — couleur={user_color}, statut={status}, "
            f"coups={len(moves_from_state(state))}, adversaire_ia={white_ai is not None or black_ai is not None}."
        )

        nl_inst = _open_board_with_retry("NicLink_lichess")
        set_nl_inst_ref(nl_inst)

        game = LichessGame(
            nl_inst, client, game_id, level=level, player_name=player_name,
            clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s,
            chosen_color_setting=user_color, cadence_key="",
            resuming=not already_over,
            initial_wtime_ms=initial_wtime_ms, initial_btime_ms=initial_btime_ms,
            clock_known=clock_known, game_log=game_log, known_user_color=user_color,
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
        # Idempotent (GameLog.close(), voir game_log.py) : si game.start()
        # a été atteint, LichessGame.run() a déjà fermé ce même journal —
        # sans effet ici dans ce cas ; ferme-le sinon (échec avant la
        # construction de la partie, voir _run_lichess_human pour le même
        # motif).
        game_log.close()
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
        send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning", "persistent": True})
        return
    if full_event is None:
        logger_lichess.warning("Lichess : abandon depuis la liste — état de partie introuvable (%s).", game_id)
        send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning", "persistent": True})
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
        send_event("lichess_toast", {"message_key": "lichess.erreur_reseau", "type": "warning", "persistent": True})
        return

    logger_lichess.info(
        "Lichess : partie %s depuis la liste (%s, %d coup(s) joué(s)).",
        "annulée" if aborting else "abandonnée", game_id, len(moves),
    )
    check_lichess_resumable()


# ── Problèmes (puzzles) Lichess — issue #354, étape A ───────────────────────
#
# Périmètre volontairement minimal (décision d'Alain) : un problème après
# l'autre, angle par défaut (pas de choix de thème — toujours vrai après
# #387), pas de Storm/Racer/Streak, jamais de reprise d'un problème déjà
# vu. Réutilise le lanceur existant au maximum (_open_board_with_retry,
# _reconnect_board_or_menu, _discard_stale_browser_actions,
# _BackMenuDuringWait, _menu_toast_data) — seule la boucle de jeu elle-même
# (modes/lichess/puzzle_game.py::PuzzleGame) diffère de LichessGame, faute
# d'adversaire/flux réseau continu (toute la solution est connue d'avance,
# voir puzzle_client.py, livré par #351).
#
# Séance de N problèmes avec compteur et bilan (issue #387, point 2) :
# _PuzzleSessionTracker ci-dessous — une séance est une LISTE de séries
# (thème, nombre de problèmes), pour préparer l'enchaînement de plusieurs
# séries d'une future issue ; une seule série existe aujourd'hui.
#
# Choix du thème/de la phase de partie (issue #388, point 2) : `theme` de
# _PuzzleSeriesSpec porte maintenant l'ANGLE RÉELLEMENT résolu à partir des
# réglages mémorisés (lichess_puzzle_series_mode/_theme/_phase,
# config.json) — chaîne vide pour "mix" (mélange, comportement d'avant
# cette issue, inchangé), sinon une clé de puzzle_themes.PUZZLE_THEME_KEYS
# ou PUZZLE_PHASE_KEYS. Cette même valeur sert à la fois d'angle transmis
# à get_next_puzzle() et d'étiquette affichée/historisée (series_theme,
# voir PuzzleGame._record_history) — jamais deux représentations
# distinctes du même réglage.

class _PuzzleSeriesSpec:
    """Une série de la séance — angle résolu (vide = mélange, voir
    ci-dessus), nombre de problèmes (0 = sans limite, valide seulement
    pour l'unique série d'aujourd'hui), et type de série ("theme"/"phase"/
    "mix" — issue #390, point 2) : forme explicite et sans ambiguïté du
    réglage, reportée dans l'historique local (voir PuzzleGame._record_history,
    puzzle_game.py) pour que le compteur du jour par type (voir
    puzzle_history.daily_counts_by_type) n'ait jamais à redériver le type
    depuis `theme` seul (vide pour "mix" ET pour "theme" avec un thème
    absent/invalide — voir _resolve_puzzle_series_angle, deux cas que
    `theme` seul ne permet pas de distinguer)."""

    def __init__(self, theme: str, count: int, series_type: str = "mix"):
        self.theme = theme
        self.count = count
        self.series_type = series_type if series_type in ("theme", "phase", "mix") else "mix"


class _PuzzleSessionTracker:
    """Comptabilise une séance de problèmes au fil de la boucle
    `_run_lichess_puzzle`/`_run_lichess_puzzle_virtual` — jamais pendant
    `PuzzleGame` elle-même (qui ne connaît qu'UN problème à la fois).
    `record()` n'est appelé que pour un problème dont un résultat existe
    (`game.outcome is not None`) — un abandon ne compte jamais, ni dans le
    compteur affiché, ni dans ce bilan (voir le rapport de clôture)."""

    def __init__(self, series):
        self.series = list(series)
        # Total de la séance : 0 (sans limite) si la première série est
        # sans limite — pas de somme avec une série suivante dans ce cas
        # (sans objet aujourd'hui, une seule série).
        self.total = self.series[0].count if self.series else 0
        self.completed = 0
        self.solved = 0
        self.failed = 0
        self._durations = []
        self._rating_diff_total = 0
        self._rating_diff_known = False
        self.failed_puzzles = []  # [{"puzzle_id", "rating"}], dans l'ordre
        # Issue #390, point 1 : cote du joueur affichée dans le panneau de
        # problème — None tant qu'aucune source (historique local, profil
        # du compte) n'a fourni de valeur ; mise à jour après chaque
        # problème terminé par la cote « Après » renvoyée par Lichess (voir
        # record() ci-dessous), jamais recalculée autrement. Voir
        # _init_puzzle_session_rating pour la valeur initiale.
        self.player_rating = None

    @property
    def current_series_type(self) -> str:
        return self.series[0].series_type if self.series else "mix"

    @property
    def current_theme(self) -> str:
        return self.series[0].theme if self.series else ""

    def record(self, game) -> None:
        self.completed += 1
        if game.outcome == "solved":
            self.solved += 1
        else:
            self.failed += 1
            self.failed_puzzles.append({"puzzle_id": game.puzzle_id, "rating": game.rating})
        if game.duration_s is not None:
            self._durations.append(game.duration_s)
        if game.rating_diff is not None:
            self._rating_diff_total += game.rating_diff
            self._rating_diff_known = True
        # Issue #390, point 1 : la cote du joueur affichée pour les
        # problèmes SUIVANTS devient la cote « Après » de celui-ci, dès
        # qu'elle est connue — jamais recalculée autrement (ni par
        # soustraction de rating_diff à une valeur antérieure, qui
        # dupliquerait une logique déjà faite côté Lichess).
        if game.rating_after is not None:
            self.player_rating = game.rating_after

    def is_complete(self) -> bool:
        return self.total > 0 and self.completed >= self.total

    def summary_payload(self) -> dict:
        avg_duration_s = (sum(self._durations) / len(self._durations)) if self._durations else None
        return {
            "completed": self.completed,
            "solved": self.solved,
            "failed": self.failed,
            "avg_duration_s": avg_duration_s,
            "rating_diff_total": self._rating_diff_total if self._rating_diff_known else None,
            "failed_puzzles": self.failed_puzzles,
            # Angle réellement demandé pour cette séance (issue #388, point 3)
            # — vide pour "mélange", sinon une clé de
            # puzzle_themes.PUZZLE_THEME_KEYS/PUZZLE_PHASE_KEYS ; affiché par
            # l'écran de bilan (app.js::_renderLichessPuzzleSessionSummary)
            # exactement comme series_theme dans l'historique local (voir
            # PuzzleGame._record_history, puzzle_game.py) — même valeur,
            # jamais deux représentations distinctes du même réglage.
            "series_angle": self.current_theme,
        }


def _resolve_puzzle_series_angle(cfg: dict) -> str:
    """Résout l'angle réellement demandé à partir des réglages mémorisés
    (issue #388, point 2) — jamais d'exception, jamais une clé hors des
    listes fixes (voir puzzle_themes.py) : une valeur invalide ou absente
    retombe toujours sur "mix" (mode "theme") ou sur
    DEFAULT_PUZZLE_PHASE (mode "phase"), jamais une erreur bloquante."""
    mode = cfg.get("lichess_puzzle_series_mode") or "mix"
    if mode == "theme":
        theme = cfg.get("lichess_puzzle_theme") or ""
        return theme if theme in PUZZLE_THEME_KEYS else ""
    if mode == "phase":
        phase = cfg.get("lichess_puzzle_phase") or ""
        return phase if phase in PUZZLE_PHASE_KEYS else DEFAULT_PUZZLE_PHASE
    return ""


def _build_puzzle_session() -> _PuzzleSessionTracker:
    """Lit `lichess_puzzle_session_size` dans config.json (mécanisme de
    persistance déjà en place, voir config_manager.py — défaut 25, 0 =
    sans limite, comportement actuel d'enchaînement infini), l'angle
    résolu (issue #388, point 2, voir _resolve_puzzle_series_angle) et le
    type de série sous forme explicite (issue #390, point 2) — repli sur
    "mix" pour toute valeur de `lichess_puzzle_series_mode` autre que
    "theme"/"phase" (comme _resolve_puzzle_series_angle ci-dessus)."""
    cfg = load_config()
    size = cfg.get("lichess_puzzle_session_size", 25)
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 25
    size = max(0, size)
    angle = _resolve_puzzle_series_angle(cfg)
    series_type = cfg.get("lichess_puzzle_series_mode") or "mix"
    series_type = series_type if series_type in ("theme", "phase", "mix") else "mix"
    return _PuzzleSessionTracker([_PuzzleSeriesSpec(theme=angle, count=size, series_type=series_type)])


def _init_puzzle_session_rating(session: "_PuzzleSessionTracker", token: str, username: str) -> None:
    """Issue #390, point 1 : cote du joueur affichée dès le début de la
    séance (`session.player_rating`, lue par chaque "lichess_puzzle_playing"
    envoyé par les lanceurs ci-dessous).

    Valeur immédiate (jamais de réseau, jamais de retard) : dernière cote
    « Après » connue de l'historique local des problèmes (voir
    puzzle_history.last_known_puzzle_rating) — `None` si cet historique
    est absent/vide, dans ce cas rien n'est affiché tant que la lecture
    ci-dessous n'a pas répondu.

    Mise à jour en arrière-plan, AU PLUS une requête réseau par séance :
    lecture PUBLIQUE de GET /api/user/<id> (perfs.puzzle.rating — même
    route, même garantie « aucun jeton ni scope requis » que
    game.py::_maybe_fetch_new_rating/GameClient.fetch_my_rating), jamais
    bloquante pour le premier problème (fil dédié). `username` vient de
    test_token() (déjà appelé par launch_lichess_puzzle avant ce point,
    champ "account" — aucun appel supplémentaire pour l'obtenir, aucun
    nouveau droit de jeton). Si cette lecture échoue ou ne répond jamais,
    la valeur affichée reste celle de l'historique local (ou rien) —
    jamais de cote inventée."""
    session.player_rating = last_known_puzzle_rating()
    if not token or not username:
        return

    def _worker():
        try:
            rating = GameClient(token).fetch_my_rating(username, "puzzle")
        except Exception as exc:
            logger_lichess.debug("Lichess : lecture de la cote de problèmes (profil) échouée : %s", exc)
            return
        if isinstance(rating, int):
            session.player_rating = rating
            send_event("lichess_puzzle_player_rating", {"rating": rating})

    threading.Thread(target=_worker, daemon=True, name="lichess_puzzle_rating").start()


def _show_puzzle_session_summary_and_wait(session: _PuzzleSessionTracker) -> None:
    """Fin de séance (dernier problème terminé, voir session.is_complete())
    — affiche l'écran de bilan et bloque jusqu'au clic « Retour au menu »,
    seul bouton de cet écran (index.html). L'état "lichess_puzzle_session_summary"
    est routé en action_queue par on_action() (server.py) exactement comme
    "lichess_puzzle_playing" — un clic "back_menu" y met IMMÉDIATEMENT
    _app_state à "menu" (voir on_action) et dépose l'action ici ; cette
    boucle n'a donc qu'à attendre son arrivée, sans jamais revenir en
    arrière pour un nouveau problème (boucle appelante : "return" juste
    après cet appel, toujours)."""
    set_app_state("lichess_puzzle_session_summary", session.summary_payload())
    while True:
        action = get_action(timeout=0.2)
        if action is None:
            continue
        if action.get("type") == "back_menu":
            return
        # Autres actions (changement de mode, etc.) : sans objet sur cet
        # écran (un seul bouton affiché) — ignorées, comme
        # _drain_back_menu_only ignore tout ce qui n'est pas back_menu
        # pendant une attente bloquante (puzzle_game.py).


def _wait_initial_position_lichess_puzzle(nl_inst, target_fen: str, color: str) -> None:
    """Variante de _wait_initial_position_lichess pour une position de
    départ ARBITRAIRE (celle du problème, jamais la position de départ
    standard) — même mécanique par ailleurs (sans limite de temps,
    annulable par "back_menu", reconnexion automatique sur lecture vide
    prolongée). Comme _wait_initial_position_lichess/_wait_initial_position_web,
    le payload envoyé à l'écran porte la lecture physique COURANTE
    (`board_fen`), pas la position cible figée — sinon les cases rouges de
    l'écran de mise en place ne se mettent jamais à jour au fil du placement
    (bug réel, issue #361). La position cible est transmise séparément
    (`expected_fen`), puisqu'elle est arbitraire ici (pas la position de
    départ standard que `renderBoardPosInit` compare par défaut — voir
    app.js) ; le payload porte aussi `puzzle: True`, pour qu'app.js affiche
    un texte dédié (clé lichess.puzzle_mise_en_place_texte) plutôt que celui
    des parties."""
    target_board_fen = target_fen.strip().split()[0] if target_fen else chess.Board().board_fen()
    first_check = True
    empty_since = None
    while True:
        # Issue #389 : "Retour aux réglages" (back_config_lichess) atterrit
        # sur "config_lichess" plutôt que "menu" — sortie de mise en place
        # tout aussi valable que le retour au menu principal.
        if get_app_state() in ("menu", "config_lichess"):
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
        if board_fen == target_board_fen:
            nl_inst.turn_off_all_leds()
            time.sleep(0.3)
            return
        if first_check:
            first_check = False
            try:
                nl_inst.signal_lights(1)
            except Exception as e:
                logger_lichess.debug(f"signal_lights cosmétique a échoué (problème Lichess) : {e}")
        set_app_state("position_initiale", {
            "fen": board_fen, "expected_fen": target_board_fen, "color": color, "puzzle": True,
        })
        time.sleep(0.5)


def launch_lichess_puzzle(config: dict) -> None:
    """Lance une session de problèmes (carte « Problèmes » de l'écran
    Lichess) — comme launch_lichess, exécute tout de façon synchrone dans
    un thread dédié que ce lanceur attend (t.join()) : à son retour, la
    session est déjà terminée (retour au menu demandé par l'utilisateur ou
    erreur). Vérifie D'ABORD les droits du jeton (puzzle:read/puzzle:write)
    via test_token() — jamais d'échec silencieux si l'un des deux manque
    (issue #354, étape A).

    `config["puzzle_mode"]` ("board", défaut, ou "virtual" — issue #364,
    choix fait à l'écran Lichess, jamais mémorisé côté serveur : voir
    app.js pour la préférence localStorage) sélectionne le lanceur réel —
    _run_lichess_puzzle (échiquier physique, inchangé) ou
    _run_lichess_puzzle_virtual (écran seul, aucun échiquier requis : ne
    tente jamais _open_board_with_retry, contrairement à l'autre)."""
    current_state = web_server._app_state
    # Issue #383, point 4 : log d'entrée inconditionnel — voir launch_lichess.
    logger_lichess.info(
        "Lichess : entrée launch_lichess_puzzle (état actuel=%s, puzzle_mode=%s).",
        current_state, config.get("puzzle_mode") or "board",
    )
    if current_state not in ("menu", "config_lichess"):
        logger.info(f"Lancement problème Lichess refusé : mode déjà actif ({current_state}).")
        send_event("lichess_toast", {"message_key": "toast.lichess_mode_actif", "type": "warning"})
        return
    _bump_launch_generation()  # issue #392, point 2 — voir launch_lichess

    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data("toast.lichess_no_token"))
        return

    from nicsoft.modes.lichess.client import test_token
    check = test_token(token)
    if check.get("status") != "ok":
        # Issue #368, partie 1 : avant cette correction, tout statut différent
        # de "rate_limited" (donc "network_error" aussi) retombait sur le
        # message « jeton refusé », trompeur quand la vraie cause est
        # l'absence de réseau. Repli sur "toast.lichess_error" (jamais à
        # nouveau « jeton refusé » par défaut) pour un statut imprévu.
        key = _LICHESS_TOKEN_STATUS_TOAST_KEYS.get(check.get("status"), "toast.lichess_error")
        web_server._app_state = "config_lichess"
        set_app_state("config_lichess", _menu_toast_data(key))
        return
    missing = []
    if not check.get("has_puzzle_read"):
        missing.append("puzzle:read")
    if not check.get("has_puzzle_write"):
        missing.append("puzzle:write")
    if missing:
        logger_lichess.info(
            "Lichess : problèmes refusés — droit(s) manquant(s) sur le jeton : %s.", ", ".join(missing),
        )
        web_server._app_state = "config_lichess"
        set_app_state("config_lichess", _menu_toast_data(
            "toast.lichess_puzzle_missing_scope", {"scopes": ", ".join(missing)}, persistent=True,
        ))
        return

    player_name = (config.get("player") or "Vous").strip() or "Vous"
    puzzle_mode = "virtual" if config.get("puzzle_mode") == "virtual" else "board"
    # Issue #390, point 1 : identifiant du compte déjà connu de test_token()
    # ci-dessus (champ "account", lecture déjà faite — aucun appel
    # supplémentaire) — seule source d'identifiant transmise aux lanceurs
    # pour la lecture en arrière-plan de la cote de problèmes du compte.
    account = (check.get("account") or "").strip()
    logger_lichess.info(
        f"Lichess : lancement session de problèmes demandé — joueur={player_name} mode={puzzle_mode}."
    )

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    target = _run_lichess_puzzle_virtual if puzzle_mode == "virtual" else _run_lichess_puzzle
    t = threading.Thread(target=target, args=(token, player_name, account, _error), daemon=True)
    t.start()
    if not _join_lichess_launcher_thread(t, "launch_lichess_puzzle"):
        return
    if _error["occurred"]:
        time.sleep(1.0)
        target_state = _error.get("return_to") or "menu"
        web_server._app_state = target_state
        set_app_state(target_state, _menu_toast_data(
            _error["toast_key"] or "toast.lichess_error",
            _error.get("toast_vars"), _error.get("toast_persistent", False),
        ))
    elif web_server._app_state not in ("menu", "config_lichess"):
        web_server._app_state = "menu"
        set_app_state("menu")
    if web_server._app_state in ("menu", "config_lichess"):
        threading.Thread(target=check_board_presence_silent, daemon=True).start()


def _run_lichess_puzzle(token, player_name, account="", _error=None):
    from nicsoft.modes.lichess.puzzle_game import PuzzleGame, solver_color_for_fen, PUZZLE_LOGS_DIR
    from nicsoft.modes.lichess.puzzle_client import get_next_puzzle
    from nicsoft.modes.lichess.game_log import GameLog

    nl_inst = None
    game_log = None
    session = _build_puzzle_session()
    _init_puzzle_session_rating(session, token, account)
    try:
        game_log = GameLog("session", token=token, logs_dir=PUZZLE_LOGS_DIR)
        game_log.state_change(f"Session de problèmes Lichess démarrée — joueur={player_name}.")
        nl_inst = _open_board_with_retry("NicLink_lichess_puzzle")
        while True:
            game_log.state_change("Demande du prochain problème (GET /api/puzzle/next, angle=%s)." % (session.current_theme or "mix"))
            puzzle = get_next_puzzle(token, angle=session.current_theme)
            status = puzzle.get("status")
            if status != "ok":
                game_log.state_change(f"Problème non obtenu — statut={status}.")
                if _error is not None:
                    _error["occurred"] = True
                    _error["toast_key"] = _LICHESS_TOKEN_STATUS_TOAST_KEYS.get(status, "toast.lichess_error")
                    _error["return_to"] = "config_lichess"
                return
            game_log.state_change(
                "Problème reçu — id=%s, cote=%s, nb_coups_solution=%d, position_mise_en_place=%s, "
                "premier_coup_adverse=%s." % (
                    puzzle["puzzle_id"], puzzle.get("rating"), len(puzzle["solution"]),
                    puzzle["setup_fen"], puzzle.get("opponent_first_move") or "(aucun)",
                )
            )
            solver_color = solver_color_for_fen(puzzle.get("fen") or puzzle["setup_fen"])
            _wait_initial_position_lichess_puzzle(nl_inst, puzzle["setup_fen"], solver_color)
            game_log.state_change("Position de mise en place confirmée.")
            set_nl_inst_ref(nl_inst)
            _discard_stale_browser_actions()

            game = PuzzleGame(nl_inst, token, puzzle, player_name=player_name, game_log=game_log,
                               series_theme=session.current_theme, series_type=session.current_series_type)
            web_server._app_state = "lichess_puzzle_playing"
            set_app_state("lichess_puzzle_playing", {
                "fen": game.board.fen(), "color": solver_color,
                "puzzle_id": puzzle["puzzle_id"],
                # Issue #390, point 7 : cote du PROBLEME jamais transmise
                # au navigateur pendant la résolution (indice de difficulté,
                # lichess.org la masque aussi) — absente de ce payload par
                # construction, pas seulement cachée côté client ; connue
                # seulement à la fin, via "lichess_puzzle_result"
                # (PuzzleGame._result_payload, puzzle_game.py, inchangé).
                "puzzle_index": session.completed + 1,
                "puzzle_total": session.total or None,
                # Issue #390, point 1 : cote du joueur (voir
                # _init_puzzle_session_rating/_PuzzleSessionTracker.record) —
                # None tant qu'inconnue, jamais une valeur inventée.
                "player_rating": session.player_rating,
                # Issue #390, point 3 : FEN de départ du problème (celle de
                # l'historique local, voir PuzzleGame._record_history) —
                # jamais saisi par l'utilisateur, utilisé uniquement par les
                # boutons "Copier le FEN"/"Analyser sur Lichess", affichés
                # seulement après la fin du problème (voir index.html/app.js).
                "setup_fen": game.setup_fen,
                # Issue #390, point 4 : thème/phase CHOISI pour la série
                # (jamais les thèmes propres du problème reçu, `puzzle["themes"]`
                # — volontairement absent de ce payload, fair-play : ce
                # serait un indice). "" pour "mix" (mélange, rien affiché).
                "series_theme": session.current_theme,
                "series_type": session.current_series_type,
            })
            game.animate_opponent_first_move()
            outcome = game.run()
            if game.outcome is not None:
                session.record(game)
            if outcome == "back_menu":
                return
            if session.is_complete():
                _show_puzzle_session_summary_and_wait(session)
                return
            # "next_puzzle" : reboucle — nouveau problème, nouvelle mise en
            # place physique, sans jamais repasser par le menu (issue #354,
            # étape C).
    except _BackMenuDuringWait:
        pass
    except LichessAuthError as e:
        logger_lichess.error(f"Jeton Lichess refusé pendant les problèmes (HTTP {e.status_code}).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = ("toast.lichess_puzzle_missing_scope" if e.status_code == 403
                                    else "toast.lichess_invalid_token")
            _error["return_to"] = "config_lichess"
    except LichessRateLimitError:
        logger_lichess.warning("Limite de requêtes Lichess atteinte (problèmes).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_rate_limited"
            _error["return_to"] = "config_lichess"
    except (LichessNetworkError, LichessApiError) as e:
        logger_lichess.error(f"Erreur Lichess pendant les problèmes : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_network_error"
            _error["return_to"] = "config_lichess"
    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("Erreur problèmes Lichess : échiquier non détecté.")
            if _error is not None:
                _error["occurred"] = True
                _error["toast_key"] = "toast.board_not_found"
                _error["return_to"] = "config_lichess"
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except ConnectionError as e:
        logger.error(f"Erreur de connexion échiquier (problèmes Lichess) : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.board_not_found"
            _error["return_to"] = "config_lichess"
        send_event("board_error", {"message": str(e)})
    except Exception as e:
        logger.error(f"Erreur inattendue — problèmes Lichess : {e}")
        import traceback
        traceback.print_exc()
        if game_log is not None:
            game_log.exception(e, context="_run_lichess_puzzle")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_error"
            _error["return_to"] = "config_lichess"
        send_event("popup", {"message": f"Erreur : {e}"})
    finally:
        if nl_inst:
            try:
                nl_inst.turn_off_all_leds()
            except Exception as e:
                logger.debug(f"Extinction LEDs (fin problèmes Lichess) échouée : {e}")
            try:
                nl_inst.disconnect()
                logger_lichess.info("Lichess (problèmes) : échiquier physique libéré.")
            except Exception as e:
                logger.warning(f"Déconnexion échiquier échouée (problèmes Lichess) : {e}")
        # Issue #389 : ne jamais écraser "config_lichess" (retour aux
        # réglages demandé par l'utilisateur, voir on_action::back_config_lichess)
        # — seul un état imprévu doit retomber sur le menu principal.
        if web_server._app_state not in ("menu", "config_lichess"):
            web_server._app_state = "menu"
        if game_log is not None:
            game_log.close()


# ── Problèmes Lichess — mode virtuel (jouer à l'écran) — issue #364 ─────────
#
# Variante de _run_lichess_puzzle SANS aucun échiquier : jamais
# _open_board_with_retry, jamais _wait_initial_position_lichess_puzzle
# (aucune mise en place physique — le problème démarre directement), jamais
# nl_inst (VirtualPuzzleGame n'y touche jamais, voir puzzle_game.py). Tout
# le reste (droits du jeton déjà vérifiés par launch_lichess_puzzle, journal
# dédié, boucle "next_puzzle", traitement des erreurs Lichess) reproduit
# _run_lichess_puzzle à l'identique — dupliqué plutôt que partagé par un
# paramètre, pour que les deux boucles restent indépendantes et que le mode
# échiquier n'ait jamais besoin d'être relu en même temps que le mode
# virtuel (voir rapport de clôture).

def _run_lichess_puzzle_virtual(token, player_name, account="", _error=None):
    from nicsoft.modes.lichess.puzzle_game import VirtualPuzzleGame, solver_color_for_fen, PUZZLE_LOGS_DIR
    from nicsoft.modes.lichess.puzzle_client import get_next_puzzle
    from nicsoft.modes.lichess.game_log import GameLog

    game_log = None
    session = _build_puzzle_session()
    _init_puzzle_session_rating(session, token, account)
    try:
        game_log = GameLog("session", token=token, logs_dir=PUZZLE_LOGS_DIR)
        game_log.state_change(f"Session de problèmes Lichess (mode virtuel) démarrée — joueur={player_name}.")
        while True:
            game_log.state_change("Demande du prochain problème (GET /api/puzzle/next, angle=%s)." % (session.current_theme or "mix"))
            puzzle = get_next_puzzle(token, angle=session.current_theme)
            status = puzzle.get("status")
            if status != "ok":
                game_log.state_change(f"Problème non obtenu — statut={status}.")
                if _error is not None:
                    _error["occurred"] = True
                    _error["toast_key"] = _LICHESS_TOKEN_STATUS_TOAST_KEYS.get(status, "toast.lichess_error")
                    _error["return_to"] = "config_lichess"
                return
            game_log.state_change(
                "Problème reçu (virtuel) — id=%s, cote=%s, nb_coups_solution=%d, "
                "premier_coup_adverse=%s." % (
                    puzzle["puzzle_id"], puzzle.get("rating"), len(puzzle["solution"]),
                    puzzle.get("opponent_first_move") or "(aucun)",
                )
            )
            solver_color = solver_color_for_fen(puzzle.get("fen") or puzzle["setup_fen"])
            _discard_stale_browser_actions()

            game = VirtualPuzzleGame(None, token, puzzle, player_name=player_name, game_log=game_log,
                                      series_theme=session.current_theme, series_type=session.current_series_type)
            web_server._app_state = "lichess_puzzle_playing"
            set_app_state("lichess_puzzle_playing", {
                "fen": game.board.fen(), "color": solver_color,
                "puzzle_id": puzzle["puzzle_id"],
                # Issue #390, point 7 : cote du PROBLEME jamais transmise
                # au navigateur pendant la résolution (indice de difficulté,
                # lichess.org la masque aussi) — absente de ce payload par
                # construction, pas seulement cachée côté client ; connue
                # seulement à la fin, via "lichess_puzzle_result"
                # (PuzzleGame._result_payload, puzzle_game.py, inchangé).
                "virtual": True,
                "puzzle_index": session.completed + 1,
                "puzzle_total": session.total or None,
                "player_rating": session.player_rating,
                "setup_fen": game.setup_fen,
                "series_theme": session.current_theme,
                "series_type": session.current_series_type,
            })
            game.animate_opponent_first_move()
            outcome = game.run()
            if game.outcome is not None:
                session.record(game)
            if outcome == "back_menu":
                return
            if session.is_complete():
                _show_puzzle_session_summary_and_wait(session)
                return
            # "next_puzzle" : reboucle — nouveau problème, toujours en mode
            # virtuel (issue #364 : "Problème suivant" relance dans le même
            # mode que le précédent), sans jamais repasser par le menu.
    except _BackMenuDuringWait:
        pass
    except LichessAuthError as e:
        logger_lichess.error(f"Jeton Lichess refusé pendant les problèmes (virtuel, HTTP {e.status_code}).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = ("toast.lichess_puzzle_missing_scope" if e.status_code == 403
                                    else "toast.lichess_invalid_token")
            _error["return_to"] = "config_lichess"
    except LichessRateLimitError:
        logger_lichess.warning("Limite de requêtes Lichess atteinte (problèmes, virtuel).")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_rate_limited"
            _error["return_to"] = "config_lichess"
    except (LichessNetworkError, LichessApiError) as e:
        logger_lichess.error(f"Erreur Lichess pendant les problèmes (virtuel) : {e}")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_network_error"
            _error["return_to"] = "config_lichess"
    except Exception as e:
        logger.error(f"Erreur inattendue — problèmes Lichess (virtuel) : {e}")
        import traceback
        traceback.print_exc()
        if game_log is not None:
            game_log.exception(e, context="_run_lichess_puzzle_virtual")
        if _error is not None:
            _error["occurred"] = True
            _error["toast_key"] = "toast.lichess_error"
            _error["return_to"] = "config_lichess"
        send_event("popup", {"message": f"Erreur : {e}"})
    finally:
        # Issue #389 : ne jamais écraser "config_lichess" (retour aux
        # réglages demandé par l'utilisateur, voir on_action::back_config_lichess)
        # — seul un état imprévu doit retomber sur le menu principal.
        if web_server._app_state not in ("menu", "config_lichess"):
            web_server._app_state = "menu"
        if game_log is not None:
            game_log.close()
