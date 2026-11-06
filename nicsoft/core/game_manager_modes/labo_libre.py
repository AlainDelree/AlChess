"""
nicsoft/core/game_manager_modes/labo_libre.py — NicLink
Lanceur du mode labo libre (position de départ personnalisée), extrait de
l'ancien nicsoft/core/game_manager.py (issue #278).
"""

import time
import random
import threading
import chess

from nicsoft.engine.engine_manager import RODENT_ELO_DEFAUT, RODENT_PERSONALITY_DEFAUT
from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import (
    send_event, set_app_state, get_action_queue, app_state_proxy as web_server,
)
from nicsoft.core.game_manager_modes.state import (
    logger, set_nl_inst_ref, _read_engine_elo_and_path, _menu_toast_data,
    _wait_position_web,
)


# ── Labo libre ─────────────────────────────────────────────────────────────────
def launch_labo_libre(config):
    player        = config.get("player", "Anonyme") or "Anonyme"
    color         = config.get("color", "white")
    start_fen     = config.get("fen", chess.STARTING_FEN)
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
        target=_run_labo_libre,
        args=(player, playing_white, start_fen, pause, analyse, bip,
              engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_perso, _error),
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


def _run_labo_libre(player_name, playing_white, start_fen, pause, analyse_active, bip_active,
                       engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_personality,
                       _error=None):
    from nicsoft.modes.labo.labo import LaboSession
    nl_inst = None
    try:
        nl_inst = create_board(virtual=False, logger_name="NicLink_libre")
        logger.info("NicLink OK")
        set_nl_inst_ref(nl_inst)

        _wait_position_web(nl_inst, start_fen)

        web_server._app_state = "labo"
        set_app_state("labo")

        if engine_type == "maia":
            engine_label = f"Maia {maia_elo}"
        elif engine_type == "rodent":
            engine_label = f"Rodent {rodent_elo}"
        else:
            engine_label = f"Stockfish ~{engine_elo}elo"

        fen_short = start_fen.split()[0] if " " in start_fen else start_fen

        session = LaboSession(
            nl_inst,
            human_color   = "white" if playing_white else "black",
            start_fen     = start_fen,
            engine_elo    = engine_elo,
            analyse_active = analyse_active,
            engine_path   = engine_path,
            engine_type   = engine_type,
            maia_elo      = maia_elo,
            rodent_elo    = rodent_elo,
            rodent_personality = rodent_personality,
        )

        _aq = get_action_queue()
        while not _aq.empty():
            try: _aq.get_nowait()
            except Exception: break  # vidage de la queue avant le début de session — queue déjà vide, rien à tracer

        send_event("labo_init", {
            "fen":          fen_short,
            "player":       player_name,
            "human_color":  "white" if playing_white else "black",
            "engine_label": engine_label,
            "analyse":      analyse_active,
        })

        logger.info(f"Labo : {player_name} — {engine_label} depuis {fen_short[:30]}...")
        session.start()

    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("[LABO] Erreur : échiquier non détecté.")
            if _error is not None:
                _error["occurred"]  = True
                _error["toast_key"] = "toast.board_not_found"
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except ConnectionError as e:
        logger.error(f"[LABO] Erreur de connexion échiquier : {e}")
        if _error is not None:
            _error["occurred"]  = True
            _error["toast_key"] = "toast.position_timeout" if "Timeout" in str(e) else "toast.board_not_found"
        send_event("board_error", {"message": str(e)})
    except Exception as e:
        logger.error(f"Erreur labo : {e}")
        import traceback; traceback.print_exc()
        if _error is not None:
            _error["occurred"]  = True
            _error["toast_key"] = "toast.engine_error"
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except ValueError: pass  # extinction LED best-effort — task_done() de la queue LED
            # peut être appelé en trop par une course avec le worker LED (driver.py), sans
            # conséquence fonctionnelle (voir Queue.task_done())
        if web_server._app_state not in ("menu",):
            web_server._app_state = "menu"
