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
import random
import threading
import time

import chess

from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import (
    send_event, set_app_state, get_app_state, check_board_presence_silent,
    app_state_proxy as web_server,
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
from nicsoft.modes.lichess.game_client import GameClient

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
        nl_inst = create_board(virtual=False, logger_name="NicLink_lichess")
        logger_lichess.info("Lichess : échiquier physique ouvert.")
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
            try:
                nl_inst.disconnect()
                logger_lichess.info("Lichess : échiquier physique libéré.")
            except Exception as e:
                logger.warning(f"Déconnexion échiquier échouée (Lichess) : {e}")
        if web_server._app_state not in ("game_over", "menu"):
            web_server._app_state = "menu"
