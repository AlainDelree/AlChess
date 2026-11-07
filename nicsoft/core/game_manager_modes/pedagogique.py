"""
nicsoft/core/game_manager_modes/pedagogique.py — NicLink
Lanceur du mode pédagogique (joueur vs moteur), extrait de l'ancien
nicsoft/core/game_manager.py (issue #278).
"""

import time
import random
import threading
import chess

from nicsoft.engine.engine_manager import RODENT_ELO_DEFAUT, RODENT_PERSONALITY_DEFAUT
from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import (
    send_event, set_app_state, set_virtual_board, get_action_queue,
    app_state_proxy as web_server,
)
from nicsoft.core.game_manager_modes.state import (
    logger, get_virtual_mode, set_nl_inst_ref,
    _read_engine_elo_and_path, _menu_toast_data, _wait_initial_position_web,
)


# ── Mode pédagogique ───────────────────────────────────────────────────────────
def launch_pedagogique(config):
    player        = config.get("player", "Anonyme") or "Anonyme"
    color         = config.get("color", "white")
    level         = int(config.get("level", 5))
    pause         = config.get("pause", "blunder")
    analyse       = config.get("analyse_active", True)
    bip           = config.get("bip_active", False)
    engine_type   = config.get("engine_type", "stockfish")
    maia_elo      = int(config.get("maia_elo", 1500))
    rodent_elo    = int(config.get("rodent_elo", RODENT_ELO_DEFAUT))
    rodent_perso  = config.get("rodent_personality", RODENT_PERSONALITY_DEFAUT)
    if color == "random":
        color = random.choice(["white", "black"])
    playing_white = (color == "white")

    engine_elo, engine_path = _read_engine_elo_and_path()

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = {"occurred": False, "toast_key": None}
    t = threading.Thread(
        target=_run_pedagogique,
        args=(player, playing_white, level, pause, analyse, bip,
              engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_perso, _error),
        kwargs={"virtual": get_virtual_mode()},
        daemon=True,
    )
    t.start()
    t.join()
    if _error["occurred"]:
        time.sleep(3.0)
        web_server._app_state = "menu"
        set_app_state("menu", _menu_toast_data(_error["toast_key"] or "toast.engine_error"))
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")


def _run_pedagogique(player_name, playing_white, level, pause, analyse_active, bip_active,
                     engine_elo, engine_path, engine_type="stockfish", maia_elo=1500,
                     rodent_elo=RODENT_ELO_DEFAUT,
                     rodent_personality=RODENT_PERSONALITY_DEFAUT,
                     _error=None, virtual=False):
    from nicsoft.modes.pedagogique.pedagogique import Game, load_config, BackMenuExit

    config = load_config()
    config["pedagogique_pause"] = pause
    nl_inst = None
    try:
        nl_inst = create_board(virtual=virtual, logger_name="NicLink")
        if virtual:
            set_virtual_board(nl_inst)
            logger.info("VirtualBoard OK")
        else:
            logger.info("NicLink OK")
        set_nl_inst_ref(nl_inst)
        if not virtual:
            _wait_initial_position_web(nl_inst)

        if engine_type == "maia":
            engine_label = f"Maia {maia_elo}"
        elif engine_type == "rodent":
            engine_label = f"Rodent {rodent_elo} ({rodent_personality})"
        else:
            engine_label = f"Stockfish ~{engine_elo}elo"

        game = Game(
            nl_inst, playing_white,
            stockfish_level=level,
            default_game_type="Pedagogical",
            turn_signal=config.get("turn_signal", "both"),
            pedagogique_pause=pause,
            engine_elo=engine_elo,
            analyse_active=analyse_active,
            bip_active=bip_active,
            engine_path=engine_path,
            engine_type=engine_type,
            maia_elo=maia_elo,
            rodent_elo=rodent_elo,
            rodent_personality=rodent_personality,
        )
        game.player_name    = player_name
        game.opponent_label = engine_label
        game.move_gaps      = []
        game.last_move_time = time.time()

        web_server._app_state = "playing"
        set_app_state("playing")
        send_event("init", {
            "fen":         chess.STARTING_FEN,
            "player":      player_name,
            "color":       "white" if playing_white else "black",
            "level":       level,
            "elo":         maia_elo if engine_type == "maia" else (rodent_elo if engine_type == "rodent" else engine_elo),
            "pause":       pause,
            "analyse":     analyse_active,
            "opponent":    engine_label,
            "engine_type": engine_type,
        })
        _aq = get_action_queue()
        while not _aq.empty():
            try: _aq.get_nowait()
            except Exception: break  # vidage de la queue avant le début de partie — queue déjà vide, rien à tracer
        game.save_pgn_tmp()
        logger.info(f"Partie : {player_name} vs {engine_label}")
        game.start()
    except BackMenuExit:
        pass  # retour au menu demandé par l'utilisateur — pas une erreur
    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("Erreur : échiquier non détecté.")
            if _error is not None:
                _error["occurred"]  = True
                _error["toast_key"] = "toast.board_not_found"
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except ConnectionError as e:
        logger.error(f"Erreur de connexion échiquier (pédagogique) : {e}")
        if _error is not None:
            _error["occurred"]  = True
            _error["toast_key"] = "toast.position_timeout" if "Timeout" in str(e) else "toast.board_not_found"
        send_event("board_error", {"message": str(e)})
    except Exception as e:
        logger.error(f"Erreur inattendue mode pédagogique : {e}")
        import traceback; traceback.print_exc()
        if _error is not None:
            _error["occurred"]  = True
            _error["toast_key"] = "toast.engine_error"
        send_event("popup", {"message": f"Erreur : {e}"})
    finally:
        set_virtual_board(None)
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except ValueError: pass  # extinction LED best-effort — task_done() de la queue LED
            # peut être appelé en trop par une course avec le worker LED (driver.py), sans
            # conséquence fonctionnelle (voir Queue.task_done())
            # Arrêter le fil de lecture USB (fen_reader) et libérer le périphérique
            # avant qu'une prochaine partie n'en crée un nouveau — sinon l'ancien fil
            # continue d'appeler hid_backend.get_fen() en parallèle de la connexion
            # suivante (issue #292 : 'NoneType' object has no attribute 'read').
            try: nl_inst.disconnect()
            except Exception as e:
                logger.warning(f"Déconnexion échiquier échouée : {e}")
        if web_server._app_state != "game_over":
            web_server._app_state = "menu"
