"""
nicsoft/core/game_manager_modes/labo.py — NicLink
Lanceur du mode labo (analyse libre Stockfish), extrait de l'ancien
nicsoft/core/game_manager.py (issue #278). La boucle d'actions de la
session elle-même vit dans labo_session.py (module voisin) — ce fichier-ci
se limite au démarrage (connexion échiquier, poll FEN hors session) et à
la construction d'une LaboSession.
"""

import time
import threading
import queue as _queue

from nicsoft.config import DATA_DIR
from nicsoft.core.config_manager import validated_engine_path
from nicsoft.engine.engine_manager import RODENT_ELO_DEFAUT, RODENT_PERSONALITY_DEFAUT
from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import (
    send_event, set_app_state, set_virtual_board, app_state_proxy as web_server,
)
from nicsoft.core.game_manager_modes.state import logger, get_virtual_mode, set_nl_inst_ref
from nicsoft.core.game_manager_modes.labo_session import _run_labo_session, _copy_cancel


# ── Labo ───────────────────────────────────────────────────────────────────────
def launch_labo():
    _copy_cancel.set()
    while True:
        try:
            web_server.action_queue.get_nowait()
        except _queue.Empty:
            break  # queue vidée — fin normale du drain avant de démarrer la session
    web_server._app_state = "labo"
    set_app_state("labo")
    if get_virtual_mode():
        from nicsoft.niclink.virtual_board import VirtualBoard
        vb = VirtualBoard()
        set_virtual_board(vb)
        set_nl_inst_ref(vb)
        threading.Thread(target=_run_labo_session, daemon=True).start()
    else:
        threading.Thread(target=_poll_board_fen_labo, daemon=True).start()
        threading.Thread(target=_run_labo_session, daemon=True).start()


def _poll_board_fen_labo():
    nl = None
    try:
        nl = create_board(virtual=False, logger_name="NL_labo_poll")
        set_nl_inst_ref(nl)
        while web_server._app_state == "labo":
            try:
                raw = nl.get_fen()
                fen = raw.strip().split()[0] if raw else ""
                if fen:
                    send_event("board_fen_update", {"fen": fen})
            except Exception as e:
                logger.debug(f"[LABO POLL] Lecture FEN échouée : {e}")
            time.sleep(0.3)
    except Exception as e:
        logger.error(f"[LABO POLL] Erreur : {e}")
    finally:
        if nl:
            # Filet de sécurité : _run_labo_session (labo_session.py) ferme déjà nl
            # à la fin normale d'une session (retour menu ou abandon) — disconnect()
            # est sans effet si déjà appelé. Reste nécessaire si la session n'a
            # jamais démarré (ex. échec de _make_labo_session) : sans ce filet, le
            # fil de lecture USB resterait orphelin pour la session suivante.
            try: nl.disconnect()
            except Exception as e:
                logger.warning(f"[LABO POLL] Déconnexion échiquier échouée : {e}")


def _make_labo_session(nl_inst, config: dict):
    from nicsoft.modes.labo.labo import LaboSession
    from nicsoft.engine.engine_manager import find_stockfish
    engine_path = ""
    try:
        import json
        cfg_path = DATA_DIR / "config.json"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = json.load(f)
            engine_path = validated_engine_path(cfg)
    except Exception as e:
        logger.debug(f"[LABO] Lecture config.json échouée, fallback find_stockfish() : {e}")
    if not engine_path:
        engine_path = find_stockfish() or "stockfish"

    human        = config.get("human_color", "white")
    engine_color = "black" if human == "white" else "white"

    return LaboSession(
        nl_inst,
        engine_color   = engine_color,
        engine_elo     = config.get("engine_elo", 1500),
        analyse_active = config.get("analyse", True),
        engine_path    = engine_path,
        engine_type    = config.get("engine_type", "stockfish"),
        maia_elo       = config.get("maia_elo", 1500),
        rodent_elo     = config.get("rodent_elo", RODENT_ELO_DEFAUT),
        rodent_personality = config.get("rodent_personality", RODENT_PERSONALITY_DEFAUT),
    )
