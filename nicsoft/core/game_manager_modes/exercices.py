"""
nicsoft/core/game_manager_modes/exercices.py — NicLink
Lanceurs des modes exercices et drill (entraînement ouvertures), extraits
de l'ancien nicsoft/core/game_manager.py (issue #278).

L'état de session (_exercice_running, _ex_thread, _exercice_session,
_exercice_lock) est propre à ce mode et ne quitte jamais ce module.
"""

import threading

from nicsoft.config import DATA_DIR
from nicsoft.core.config_manager import validated_engine_path
from nicsoft.engine.engine_manager import RODENT_ELO_DEFAUT, RODENT_PERSONALITY_DEFAUT
from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import (
    send_event, set_app_state, set_virtual_board, app_state_proxy as web_server,
)
from nicsoft.core.game_manager_modes.state import logger, get_virtual_mode, set_nl_inst_ref

# ── État propre au mode exercices/drill ─────────────────────────────────────────
_exercice_running = False
_ex_thread        = None
_exercice_session = 0
_exercice_lock    = threading.Lock()


# ── Mode exercices ─────────────────────────────────────────────────────────────
def launch_exercices():
    from nicsoft.modes.exercices.exercices import get_ouvertures, get_mes_lignes
    web_server._app_state = "exercices"
    set_app_state("exercices", {
        "ouvertures": get_ouvertures(),
        "mes_lignes": get_mes_lignes(),
    })


def start_exercice(config: dict) -> None:
    global _ex_thread, _exercice_running
    if _ex_thread and _ex_thread.is_alive():
        _ex_thread.join(timeout=3.0)
        if _ex_thread.is_alive():
            logger.warning("[EXERCICE] Thread précédent encore vivant après join — force reset")
            _exercice_running = False
    _ex_thread = threading.Thread(target=_run_exercice, args=(config,), daemon=True)
    _ex_thread.start()


def start_drill(config: dict) -> None:
    global _ex_thread
    if _ex_thread and _ex_thread.is_alive():
        _ex_thread.join(timeout=3.0)
    _ex_thread = threading.Thread(target=_run_drill, args=(config,), daemon=True)
    _ex_thread.start()


def _run_exercice(config: dict) -> None:
    global _exercice_running, _exercice_session
    with _exercice_lock:
        if _exercice_running:
            return
        _exercice_running = True
        _exercice_session += 1
        my_session = _exercice_session

    from nicsoft.modes.exercices.exercices import ExerciceSession, OUVERTURES, get_mes_lignes

    ouverture_id = config.get("ouverture_id", "")
    ouverture = next((o for o in OUVERTURES if o["id"] == ouverture_id), None)
    if ouverture is None:
        ouverture = next((o for o in get_mes_lignes() if o["id"] == ouverture_id), None)
    if not ouverture:
        send_event("board_error", {"message": f"Ouverture '{ouverture_id}' introuvable."})
        _exercice_running = False
        return

    human_color = config.get("human_color", "white")
    variete     = int(config.get("variete", 3))
    nl_inst     = None
    engine      = None

    try:
        virtual_mode = get_virtual_mode()
        nl_inst = create_board(virtual=virtual_mode, logger_name="NicLink_exercice")
        if virtual_mode:
            set_virtual_board(nl_inst)
            logger.info("VirtualBoard OK — Exercice")
        else:
            logger.info("NicLink OK — Exercice ouverture")

        set_nl_inst_ref(nl_inst)

        web_server._app_state = "exercice_running"
        set_app_state("exercice_running")

        send_event("exercice_init", {
            "ouverture":   ouverture,
            "human_color": human_color,
            "variete":     variete,
        })

        session = ExerciceSession(nl_inst, ouverture, human_color, variete)

        try:
            from nicsoft.engine.engine_manager import EngineManager, find_stockfish
            import json
            cfg_path    = DATA_DIR / "config.json"
            engine_elo  = 1500
            engine_path = ""
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                engine_elo  = cfg.get("engine_elo", 1500)
                engine_path = validated_engine_path(cfg)
            if not engine_path:
                engine_path = find_stockfish() or "stockfish"
            engine = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=False)
            session._engine = engine
        except Exception as e:
            logger.warning(f"[EXERCICE] Moteur non disponible pour mode libre : {e}")

        if virtual_mode:
            nl_inst.game_board = session.board.copy()

        session.run()

    except Exception as e:
        logger.error(f"[EXERCICE] Erreur : {e}")
        import traceback; traceback.print_exc()
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
        with _exercice_lock:
            _exercice_running = False
        set_virtual_board(None)
        if engine:
            try: engine.quit()
            except Exception as e:
                logger.warning(f"[EXERCICE] Fermeture du moteur échouée (processus potentiellement orphelin) : {e}")
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass  # extinction LED best-effort — sans conséquence fonctionnelle
            try: nl_inst.disconnect()
            except Exception as e:
                logger.warning(f"[EXERCICE] Déconnexion échiquier échouée : {e}")
        if my_session == _exercice_session and web_server._app_state not in ("menu", "exercices"):
            from nicsoft.modes.exercices.exercices import get_ouvertures, get_mes_lignes
            web_server._app_state = "exercices"
            set_app_state("exercices", {
                "ouvertures": get_ouvertures(),
                "mes_lignes": get_mes_lignes(),
            })


def _run_drill(config: dict) -> None:
    global _exercice_running, _exercice_session
    with _exercice_lock:
        if _exercice_running:
            return
        _exercice_running = True
        _exercice_session += 1
        my_session = _exercice_session

    from nicsoft.modes.exercices.exercices import DrillSession, get_mes_lignes

    ligne_ids   = config.get("ligne_ids", [])
    human_color = config.get("human_color", "white")
    lignes      = [l for l in get_mes_lignes() if l["id"] in ligne_ids]

    if not lignes:
        send_event("board_error", {"message": "Aucune ligne sélectionnée."})
        _exercice_running = False
        return

    nl_inst = None
    engine  = None

    try:
        virtual_mode = get_virtual_mode()
        nl_inst = create_board(virtual=virtual_mode, logger_name="NicLink_drill")
        if virtual_mode:
            set_virtual_board(nl_inst)

        set_nl_inst_ref(nl_inst)

        web_server._app_state = "exercice_running"
        set_app_state("exercice_running")

        from nicsoft.modes.exercices.exercices import common_init_moves
        init = common_init_moves(lignes)
        camp = lignes[0].get("camp_suggere", human_color)
        ouverture_synth = {
            "id": "drill_multi", "nom": f"Drill ({len(lignes)} lignes)",
            "init": init, "camp_suggere": camp,
        }

        send_event("exercice_init", {
            "ouverture":   ouverture_synth,
            "human_color": human_color,
            "variete":     len(lignes),
        })

        session = DrillSession(nl_inst, lignes, human_color)

        try:
            from nicsoft.engine.engine_manager import EngineManager, find_stockfish
            import json
            cfg_path    = DATA_DIR / "config.json"
            engine_elo  = 1500
            engine_path = find_stockfish() or "stockfish"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text())
                engine_path = validated_engine_path(cfg, default=engine_path)
                engine_elo  = cfg.get("engine_elo", engine_elo)
            engine = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=False)
            session._engine = engine
        except Exception as e:
            logger.warning(f"[DRILL] Moteur non chargé : {e}")

        nl_inst.game_board = session.board.copy()
        session.run()

    except Exception as e:
        logger.error(f"[DRILL] Erreur : {e}")
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
        with _exercice_lock:
            _exercice_running = False
        set_virtual_board(None)
        if engine:
            try: engine.quit()
            except Exception as e:
                logger.warning(f"[DRILL] Fermeture du moteur échouée (processus potentiellement orphelin) : {e}")
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass  # extinction LED best-effort — sans conséquence fonctionnelle
            try: nl_inst.disconnect()
            except Exception as e:
                logger.warning(f"[DRILL] Déconnexion échiquier échouée : {e}")
        if my_session == _exercice_session and web_server._app_state not in ("menu", "exercices"):
            from nicsoft.modes.exercices.exercices import get_ouvertures, get_mes_lignes
            web_server._app_state = "exercices"
            set_app_state("exercices", {
                "ouvertures": get_ouvertures(),
                "mes_lignes": get_mes_lignes(),
            })
