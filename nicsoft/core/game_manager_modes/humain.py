"""
nicsoft/core/game_manager_modes/humain.py — NicLink
Lanceur du mode Humain contre Humain, extrait de l'ancien
nicsoft/core/game_manager.py (issue #278).
"""

import time
import random
import threading
import chess

from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import (
    send_event, set_app_state, get_action, set_virtual_board, get_action_queue,
    check_board_at_startup, set_history, app_state_proxy as web_server,
)
from nicsoft.core.game_manager_modes.state import (
    logger, get_virtual_mode, set_nl_inst_ref, _wait_initial_position_web,
    _menu_toast_data,
)


# ── Mode humain ────────────────────────────────────────────────────────────────
def launch_humain(config):
    white = config.get("white", "Anonyme1") or "Anonyme1"
    black = config.get("black", "Anonyme2") or "Anonyme2"
    if config.get("color") == "random":
        if random.random() < 0.5:
            white, black = black, white
    game_type = config.get("game_type", "Serious")
    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None}
    t = threading.Thread(target=_run_humain, args=(white, black, game_type, _error),
                         kwargs={"virtual": get_virtual_mode()}, daemon=True)
    t.start()
    t.join()
    if _error["occurred"]:
        time.sleep(3.0)
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data(_error["toast_key"] or "toast.board_not_found"))
    elif web_server._app_state == "game_over":
        pass
    else:
        web_server._app_state = "menu"
        set_app_state("menu")
    if web_server._app_state == "menu" and not get_virtual_mode():
        # Re-vérifier l'état réel du plateau au retour menu depuis HH
        # (déconnexion silencieuse pendant la partie non détectée jusqu'ici).
        threading.Thread(target=check_board_at_startup, daemon=True).start()


def _run_humain(white_name, black_name, game_type, _error=None, virtual=False):
    from nicsoft.modes.humain.human import GameWeb
    nl_inst = None
    try:
        nl_inst = create_board(virtual=virtual, logger_name="NicLink_humain")
        if virtual:
            set_virtual_board(nl_inst)
            logger.info("VirtualBoard OK — Humain")
        if not virtual:
            _wait_initial_position_web(nl_inst)
        set_nl_inst_ref(nl_inst)
        set_history([], ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"])

        game = GameWeb(nl_inst, white_name=white_name, black_name=black_name,
                       default_game_type=game_type)
        game.move_gaps      = []
        game.last_move_time = time.time()

        send_event("init_hh", {"fen": chess.STARTING_FEN, "white": white_name, "black": black_name})
        set_app_state("playing")

        _aq = get_action_queue()
        while not _aq.empty():
            try: _aq.get_nowait()
            except Exception: break  # vidage de la queue avant le début de partie — queue déjà vide, rien à tracer

        game.save_pgn_tmp()
        logger.info(f"Partie : {white_name} vs {black_name}")
        game.start()
        if game.game_over and web_server._app_state != "game_over":
            web_server._app_state = "game_over"

    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("Erreur mode humain : échiquier non détecté.")
            if _error is not None:
                _error["occurred"]  = True
                _error["toast_key"] = "toast.board_not_found"
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except ConnectionError as e:
        logger.error(f"Erreur de connexion échiquier (humain) : {e}")
        if _error is not None:
            _error["occurred"]  = True
            _error["toast_key"] = "toast.position_timeout" if "Timeout" in str(e) else "toast.board_not_found"
        send_event("board_error", {"message": str(e)})
    except Exception as e:
        logger.error(f"Erreur mode humain : {e}")
        import traceback; traceback.print_exc()
        if _error is not None:
            _error["occurred"]  = True
            _error["toast_key"] = "toast.board_not_found"
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
        set_virtual_board(None)
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except ValueError: pass  # extinction LED best-effort — task_done() de la queue LED
            # peut être appelé en trop par une course avec le worker LED (driver.py), sans
            # conséquence fonctionnelle (voir Queue.task_done())
        if web_server._app_state not in ("game_over", "menu"):
            web_server._app_state = "menu"
