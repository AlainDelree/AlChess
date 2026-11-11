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


def _wait_initial_position_lichess(nl_inst) -> None:
    """Variante de _wait_initial_position_web (state.py) sans limite de
    temps et annulable par "back_menu" (issue #311, point 1)."""
    initial_fen = chess.Board().board_fen()
    first_check = True
    consecutive_errors = 0
    while True:
        if get_app_state() == "menu":
            raise _BackMenuDuringWait()
        try:
            raw_fen = nl_inst.get_fen()
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            if consecutive_errors >= 5:
                raise ConnectionError("Échiquier non détecté.")
            time.sleep(0.2)
            continue
        board_fen = raw_fen.strip().split()[0] if raw_fen else ""
        if not board_fen:
            consecutive_errors += 1
            if consecutive_errors >= 5:
                raise ConnectionError("Échiquier non détecté.")
            time.sleep(0.2)
            continue
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
        set_app_state("position_initiale", {"fen": board_fen})
        time.sleep(0.5)


def _wait_first_move_white_lichess(nl_inst, legal_move_for_hardware) -> str:
    """Attend, sans limite de temps, le premier coup physique de
    l'utilisateur (blancs) — aucune partie Lichess n'existe encore à ce
    stade, donc aucune contrainte de temps Lichess ne s'applique (issue
    #311, point 1). Annulable par "back_menu" (voir
    _wait_initial_position_lichess). Retourne le coup détecté en UCI."""
    set_app_state("lichess_wait_first_move")
    start_board = chess.Board()
    while True:
        if get_app_state() == "menu":
            raise _BackMenuDuringWait()
        try:
            raw_fen = nl_inst.get_fen()
        except Exception:
            time.sleep(0.2)
            continue
        hw_fen = raw_fen.strip().split()[0] if raw_fen else ""
        if hw_fen and hw_fen != start_board.board_fen():
            move = legal_move_for_hardware(start_board, hw_fen)
            if move is not None:
                return move.uci()
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
        _wait_initial_position_lichess(nl_inst)
        logger_lichess.info("Lichess : position de départ confirmée.")
        set_nl_inst_ref(nl_inst)

        first_move_uci = None
        if resolved_color == "white":
            first_move_uci = _wait_first_move_white_lichess(nl_inst, legal_move_for_hardware)
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
