"""
nicsoft/core/game_manager_modes/lichess.py — AlChess

Lanceur du mode Lichess (issue #309, étape L2a) : partie amicale contre
l'IA de Lichess, jouée sur l'échiquier physique. Sur le modèle du lanceur
Humain contre Humain (game_manager_modes/humain.py) : thread, état
d'application, événements vers l'interface, nettoyage en fin de session.

Pas de mode virtuel pour Lichess (l'échiquier physique est requis) et
aucun moteur d'échecs n'est importé ici ni dans nicsoft.modes.lichess.game
(règle de fair-play Lichess).
"""

import logging
import threading
import time

from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import send_event, set_app_state, app_state_proxy as web_server
from nicsoft.core.game_manager_modes.state import (
    logger, set_nl_inst_ref, _wait_initial_position_web, _menu_toast_data,
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


def launch_lichess(config: dict) -> None:
    token = (load_config().get("lichess_token") or "").strip()
    if not token:
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data("toast.lichess_no_token"))
        return

    level = max(1, min(8, int(config.get("level", 1) or 1)))
    cadence = config.get("cadence", DEFAULT_CLOCK_PRESET)
    clock_limit_s, clock_increment_s = CLOCK_PRESETS.get(cadence, CLOCK_PRESETS[DEFAULT_CLOCK_PRESET])
    color = config.get("color", "random")
    lichess_color = "" if color not in ("white", "black") else color
    player_name = (config.get("player") or "Vous").strip() or "Vous"

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None}
    t = threading.Thread(
        target=_run_lichess,
        args=(token, level, clock_limit_s, clock_increment_s, lichess_color, player_name, _error),
        daemon=True,
    )
    t.start()
    t.join()
    if _error["occurred"]:
        time.sleep(1.0)
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data(_error["toast_key"] or "toast.lichess_error"))
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")


def _run_lichess(token, level, clock_limit_s, clock_increment_s, color, player_name, _error=None):
    from nicsoft.modes.lichess.game import LichessGame

    nl_inst = None
    try:
        nl_inst = create_board(virtual=False, logger_name="NicLink_lichess")
        _wait_initial_position_web(nl_inst)
        set_nl_inst_ref(nl_inst)

        client = GameClient(token)
        created = client.create_ai_game(
            level=level, clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s, color=color,
        )
        game_id = created.get("id", "")
        if not game_id:
            raise LichessNetworkError("réponse Lichess sans identifiant de partie")

        game = LichessGame(
            nl_inst, client, game_id, level=level, player_name=player_name,
            clock_limit_s=clock_limit_s, clock_increment_s=clock_increment_s,
        )
        web_server._app_state = "playing"
        set_app_state("playing")
        logger.info(f"Partie Lichess : {player_name} vs IA niveau {level} ({game_id})")
        game.start()
        game.join()

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
            except Exception as e:
                logger.warning(f"Déconnexion échiquier échouée (Lichess) : {e}")
        if web_server._app_state not in ("game_over", "menu"):
            web_server._app_state = "menu"
