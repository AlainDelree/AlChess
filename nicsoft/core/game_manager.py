"""
nicsoft/core/game_manager.py — NicLink
Orchestration des modes de jeu, extrait de nicsoft/web/alchess.py.
Sépare la logique de jeu (Core) du transport Flask/SocketIO.
"""

import time
import random
import threading
import chess
import logging

from pathlib import Path
from nicsoft.config import DATA_DIR
from nicsoft.engine.engine_manager import RODENT_ELO_DEFAUT, RODENT_PERSONALITY_DEFAUT
from nicsoft.core.board_adapter import create_board
from nicsoft.web.server import send_event, set_app_state, get_action, set_virtual_board
from nicsoft.web import server as web_server


def _validated_engine_path(cfg: dict, key: str = "engine_path", default: str = "") -> str:
    """Retourne le path moteur sauvegardé seulement s'il existe sur cette plateforme."""
    p = cfg.get(key, default)
    if p and Path(p).exists():
        return p
    return default

# ── État global ────────────────────────────────────────────────────────────────
_nl_inst_ref      = None   # échiquier courant (pour éteindre LEDs au quit)
_virtual_mode     = False  # True si mode sans échiquier physique
_exercice_running = False
_ex_thread        = None
_exercice_session = 0
_copy_cancel      = threading.Event()
_exercice_lock    = threading.Lock()

logger = logging.getLogger("niclink.game_manager")

# ── Accesseurs ─────────────────────────────────────────────────────────────────
def set_virtual_mode(val: bool) -> None:
    global _virtual_mode
    _virtual_mode = val


def get_nl_inst_ref():
    return _nl_inst_ref


# ── Attente position ───────────────────────────────────────────────────────────
def _wait_initial_position_web(nl_inst, timeout: float = 300.0):
    INITIAL_FEN = chess.Board().board_fen()
    first_check = True
    consecutive_errors = 0
    t_start = time.time()
    while True:
        try:
            raw_fen = nl_inst.get_fen()
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            if consecutive_errors >= 5 or (time.time() - t_start) >= timeout:
                raise ConnectionError("Échiquier non détecté.")
            time.sleep(0.2)
            continue
        board_fen = raw_fen.strip().split()[0] if raw_fen else ""
        if not board_fen:
            consecutive_errors += 1
            if consecutive_errors >= 5 or (time.time() - t_start) >= timeout:
                raise ConnectionError("Échiquier non détecté.")
            time.sleep(0.2)
            continue
        if board_fen == INITIAL_FEN:
            nl_inst.turn_off_all_leds()
            set_app_state("connecting")
            time.sleep(0.3)
            return
        if first_check:
            first_check = False
            try: nl_inst.signal_lights(1)
            except Exception: pass
        set_app_state("position_initiale", {"fen": board_fen})
        time.sleep(0.5)


def _wait_position_web(nl_inst, target_fen: str, timeout: float = 300.0):
    """Attend que le plateau physique corresponde au FEN cible."""
    target = target_fen.strip().split()[0] if " " in target_fen else target_fen
    t_start = time.time()
    first_check = True
    while True:
        try:
            raw = nl_inst.get_fen()
            board_fen = raw.strip().split()[0] if raw else ""
        except Exception:
            time.sleep(0.2)
            continue
        if board_fen == target:
            nl_inst.turn_off_all_leds()
            return
        if first_check:
            first_check = False
        send_event("position_error", {
            "expected_fen": target,
            "physical_fen": board_fen,
        })
        if (time.time() - t_start) >= timeout:
            raise ConnectionError("Timeout — position non atteinte.")
        time.sleep(0.5)


# ── Mode pédagogique ───────────────────────────────────────────────────────────
def launch_pedagogique(config):
    import json
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

    cfg_path    = DATA_DIR / "config.json"
    engine_elo  = 1500
    engine_path = ""
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_elo  = cfg.get("engine_elo", 1500)
            engine_path = _validated_engine_path(cfg)
        except Exception:
            pass

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = [False]
    t = threading.Thread(
        target=_run_pedagogique,
        args=(player, playing_white, level, pause, analyse, bip,
              engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_perso, _error),
        kwargs={"virtual": _virtual_mode},
        daemon=True,
    )
    t.start()
    t.join()
    if _error[0]:
        time.sleep(3.0)
        web_server._app_state = "menu"
        set_app_state("menu")
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")


def _run_pedagogique(player_name, playing_white, level, pause, analyse_active, bip_active,
                     engine_elo, engine_path, engine_type="stockfish", maia_elo=1500,
                     rodent_elo=RODENT_ELO_DEFAUT,
                     rodent_personality=RODENT_PERSONALITY_DEFAUT,
                     _error=None, virtual=False):
    from nicsoft.modes.pedagogique.pedagogique import Game, load_config, BackMenuExit
    from nicsoft.web.server import get_action

    config = load_config()
    config["pedagogique_pause"] = pause
    global _nl_inst_ref
    nl_inst = None
    try:
        nl_inst = create_board(virtual=virtual, logger_name="NicLink")
        if virtual:
            set_virtual_board(nl_inst)
            logger.info("VirtualBoard OK")
        else:
            logger.info("NicLink OK")
        _nl_inst_ref = nl_inst
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
        from nicsoft.web.server import action_queue as _aq
        while not _aq.empty():
            try: _aq.get_nowait()
            except Exception: break
        game.save_pgn_tmp()
        logger.info(f"Partie : {player_name} vs {engine_label}")
        game.start()
    except BackMenuExit:
        pass
    except SystemExit as e:
        if "board connection error" in str(e):
            logger.error("Erreur : échiquier non détecté.")
            if _error: _error[0] = True
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except Exception as e:
        logger.error(f"Erreur inattendue mode pédagogique : {e}")
        import traceback; traceback.print_exc()
        send_event("popup", {"message": f"Erreur : {e}"})
    finally:
        set_virtual_board(None)
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass
        if web_server._app_state != "game_over":
            web_server._app_state = "menu"


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
    _error = [False]
    t = threading.Thread(target=_run_humain, args=(white, black, game_type, _error),
                         kwargs={"virtual": _virtual_mode}, daemon=True)
    t.start()
    t.join()
    if _error[0]:
        time.sleep(3.0)
        web_server._app_state = "menu"
        set_app_state("menu")
    elif web_server._app_state == "game_over":
        pass
    else:
        web_server._app_state = "menu"
        set_app_state("menu")


def _run_humain(white_name, black_name, game_type, _error=None, virtual=False):
    from nicsoft.modes.humain.human import GameWeb
    global _nl_inst_ref
    nl_inst = None
    try:
        nl_inst = create_board(virtual=virtual, logger_name="NicLink_humain")
        if virtual:
            set_virtual_board(nl_inst)
            logger.info("VirtualBoard OK — Humain")
        if not virtual:
            _wait_initial_position_web(nl_inst)
        _nl_inst_ref = nl_inst
        web_server._game_state["history"]     = []
        web_server._game_state["history_fen"] = ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"]

        game = GameWeb(nl_inst, white_name=white_name, black_name=black_name,
                       default_game_type=game_type)
        game.move_gaps      = []
        game.last_move_time = time.time()

        send_event("init_hh", {"fen": chess.STARTING_FEN, "white": white_name, "black": black_name})
        set_app_state("playing")

        from nicsoft.web.server import action_queue as _aq
        while not _aq.empty():
            try: _aq.get_nowait()
            except Exception: break

        game.save_pgn_tmp()
        logger.info(f"Partie : {white_name} vs {black_name}")
        game.start()
        if game.game_over and web_server._app_state != "game_over":
            web_server._app_state = "game_over"

    except SystemExit:
        pass
    except Exception as e:
        logger.error(f"Erreur mode humain : {e}")
        import traceback; traceback.print_exc()
        if _error: _error[0] = True
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
        set_virtual_board(None)
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass
        if web_server._app_state not in ("game_over", "menu"):
            web_server._app_state = "menu"


# ── Mode retranscription ───────────────────────────────────────────────────────
def launch_retranscription(config):
    from nicsoft.modes.retranscription.retranscription import run_retranscription
    from nicsoft.web.server import get_action as _get_action
    import queue as _queue

    while True:
        try:
            web_server.action_queue.get_nowait()
        except _queue.Empty:
            break

    web_server._app_state = "retranscription"
    set_app_state("retranscription", {
        "white": config.get("white", "Blancs"),
        "black": config.get("black", "Noirs"),
        "date":  config.get("date", ""),
        "event": config.get("event", ""),
        "mode":  config.get("mode", "partie"),
        "nom":   config.get("nom", ""),
    })
    t = threading.Thread(
        target=run_retranscription,
        args=(config, send_event, _get_action, set_virtual_board, web_server),
        daemon=True,
    )
    t.start()
    t.join()
    if web_server._app_state not in ("game_over", "menu"):
        web_server._app_state = "menu"
        set_app_state("menu")


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
    global _exercice_running, _nl_inst_ref, _exercice_session
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
        nl_inst = create_board(virtual=_virtual_mode, logger_name="NicLink_exercice")
        if _virtual_mode:
            set_virtual_board(nl_inst)
            logger.info("VirtualBoard OK — Exercice")
        else:
            logger.info("NicLink OK — Exercice ouverture")

        _nl_inst_ref = nl_inst

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
                engine_path = _validated_engine_path(cfg)
            if not engine_path:
                engine_path = find_stockfish() or "stockfish"
            engine = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=False)
            session._engine = engine
        except Exception as e:
            logger.warning(f"[EXERCICE] Moteur non disponible pour mode libre : {e}")

        if _virtual_mode:
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
            except Exception: pass
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass
            try: nl_inst.disconnect()
            except Exception: pass
        if my_session == _exercice_session and web_server._app_state not in ("menu", "exercices"):
            from nicsoft.modes.exercices.exercices import get_ouvertures, get_mes_lignes
            web_server._app_state = "exercices"
            set_app_state("exercices", {
                "ouvertures": get_ouvertures(),
                "mes_lignes": get_mes_lignes(),
            })


def _run_drill(config: dict) -> None:
    global _exercice_running, _nl_inst_ref, _exercice_session
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
        nl_inst = create_board(virtual=_virtual_mode, logger_name="NicLink_drill")
        if _virtual_mode:
            set_virtual_board(nl_inst)

        _nl_inst_ref = nl_inst

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
                engine_path = _validated_engine_path(cfg, default=engine_path)
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
            except Exception: pass
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass
            try: nl_inst.disconnect()
            except Exception: pass
        if my_session == _exercice_session and web_server._app_state not in ("menu", "exercices"):
            from nicsoft.modes.exercices.exercices import get_ouvertures, get_mes_lignes
            web_server._app_state = "exercices"
            set_app_state("exercices", {
                "ouvertures": get_ouvertures(),
                "mes_lignes": get_mes_lignes(),
            })


# ── Labo ───────────────────────────────────────────────────────────────────────
def launch_labo():
    global _nl_inst_ref
    import queue as _queue
    _copy_cancel.set()
    while True:
        try:
            web_server.action_queue.get_nowait()
        except _queue.Empty:
            break
    web_server._app_state = "labo"
    set_app_state("labo")
    if _virtual_mode:
        from nicsoft.niclink.virtual_board import VirtualBoard
        vb = VirtualBoard()
        set_virtual_board(vb)
        _nl_inst_ref = vb
        threading.Thread(target=_run_labo_session, daemon=True).start()
    else:
        threading.Thread(target=_poll_board_fen_labo, daemon=True).start()
        threading.Thread(target=_run_labo_session, daemon=True).start()


def _poll_board_fen_labo():
    global _nl_inst_ref
    nl = None
    try:
        nl = create_board(virtual=False, logger_name="NL_labo_poll")
        _nl_inst_ref = nl
        while web_server._app_state == "labo":
            try:
                raw = nl.get_fen()
                fen = raw.strip().split()[0] if raw else ""
                if fen:
                    send_event("board_fen_update", {"fen": fen})
            except Exception:
                pass
            time.sleep(0.3)
    except Exception as e:
        logger.error(f"[LABO POLL] Erreur : {e}")
    finally:
        if nl:
            try: nl._fen_reader_stop.set()
            except Exception: pass


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
            engine_path = _validated_engine_path(cfg)
    except Exception:
        pass
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


def _run_labo_session():
    from nicsoft.web.server import get_action as _get_action

    for _ in range(50):
        if _nl_inst_ref is not None:
            break
        time.sleep(0.1)

    nl = _nl_inst_ref
    if nl is None:
        logger.error("[LABO] Échiquier non disponible")
        return

    labo_config = {
        "human_color": "white",
        "engine_type": "stockfish",
        "engine_elo":  1500,
        "maia_elo":    1500,
        "rodent_elo":  RODENT_ELO_DEFAUT,
        "rodent_personality": RODENT_PERSONALITY_DEFAUT,
        "analyse":     True,
    }

    try:
        session = _make_labo_session(nl, labo_config)
    except Exception as e:
        logger.error(f"[LABO] Erreur création session : {e}")
        return

    session._running = True
    if not _virtual_mode:
        threading.Thread(target=session.board_watcher, daemon=True).start()
        session.sync_from_physical()
    else:
        nl.make_virtual_board_watcher(session).start()
        session._send_position()

    send_event("labo_init", {
        "fen":          session.board.board_fen(),
        "human_color":  labo_config["human_color"],
        "engine_label": session.engine_label,
        "analyse":      labo_config["analyse"],
    })

    while web_server._app_state == "labo":
        action = _get_action(timeout=0.5)
        if action is None:
            continue
        atype = action.get("type", "")

        if atype == "back_menu":
            session.quit()
            set_virtual_board(None)
            web_server._app_state = "menu"
            set_app_state("menu")
            return

        elif atype == "labo_set_config":
            engine_changed = False
            color_changed  = False
            for k in ("human_color", "engine_type", "engine_elo", "maia_elo", "rodent_elo", "rodent_personality", "analyse"):
                if k in action and action[k] != labo_config.get(k):
                    if k == "human_color":
                        color_changed = True
                    else:
                        engine_changed = True
                    labo_config[k] = action[k]

            if color_changed and not engine_changed:
                new_ec = chess.BLACK if labo_config["human_color"] == "white" else chess.WHITE
                session.engine_color = new_ec
                send_event("labo_init", {
                    "fen":          session.board.board_fen(),
                    "human_color":  labo_config["human_color"],
                    "engine_label": session.engine_label,
                    "analyse":      labo_config["analyse"],
                })
                session._send_position()
                if session._auto_on and session.board.turn == new_ec and not session._engine_busy:
                    session.do_engine_play()

            elif engine_changed:
                old_board   = session.board
                old_history = session._fen_history[:]
                session._running = False
                time.sleep(0.2)
                try:
                    session = _make_labo_session(nl, labo_config)
                    session.board        = old_board
                    session._fen_history = old_history
                    nl.game_board        = session.board.copy()
                    session._running     = True
                    if _virtual_mode:
                        nl.make_virtual_board_watcher(session).start()
                    else:
                        threading.Thread(target=session.board_watcher, daemon=True).start()
                    send_event("labo_init", {
                        "fen":          session.board.board_fen(),
                        "human_color":  labo_config["human_color"],
                        "engine_label": session.engine_label,
                        "analyse":      labo_config["analyse"],
                    })
                    session._send_position()
                except Exception as e:
                    logger.error(f"[LABO] Erreur recréation : {e}")

        elif atype == "best_move":
            from nicsoft.web.server import action_queue as _aq
            while not _aq.empty():
                try:
                    peek = _aq.queue[0]
                    if peek.get("type") == "best_move":
                        _aq.get_nowait()
                    else:
                        break
                except Exception:
                    break
            session.do_best_move()

        elif atype == "engine_auto":
            val = action.get("value", not session._auto_on)
            session._auto_on = val
            send_event("labo_auto", {"auto": val})
            if val:
                if not _virtual_mode:
                    session.sync_from_physical(turn=labo_config.get("active_turn", session.active_turn))
                time.sleep(0.1)
                from nicsoft.web.server import action_queue as _aq
                saved = []
                while not _aq.empty():
                    try:
                        pending = _aq.get_nowait()
                        if pending.get("type") == "engine_auto":
                            pval = pending.get("value", not session._auto_on)
                            session._auto_on = pval
                            send_event("labo_auto", {"auto": pval})
                        else:
                            saved.append(pending)
                    except Exception:
                        break
                for a in saved:
                    _aq.put_nowait(a)
                if session._auto_on and session.board.turn == session.engine_color and not session._engine_busy:
                    session.do_engine_play()

        elif atype == "analyse_position":
            session.do_analyse()

        elif atype == "undo_labo":
            session.do_undo()

        elif atype == "source_physique":
            _copy_cancel.set()
            time.sleep(0.1)
            turn = action.get("turn", session.active_turn)
            session.sync_from_physical(turn=turn)
            time.sleep(0.1)
            if session._auto_on and session.board.turn == session.engine_color and not session._engine_busy:
                session.do_engine_play()

        elif atype == "labo_set_turn":
            turn = action.get("turn", "white")
            labo_config["active_turn"] = turn
            session.active_turn = turn

        elif atype == "set_analyse":
            session.analyse_active = action.get("value", True)
            try: session.engine.analyse_active = session.analyse_active
            except Exception: pass

        elif atype == "labo_copy_to_board":
            target_fen = action.get("fen", "")
            if target_fen:
                if _virtual_mode:
                    try:
                        fen_clean = target_fen.strip().split()[0] if " " in target_fen else target_fen
                        session.set_board_from_fen(target_fen)
                        send_event("position_ok", {"fen": fen_clean})
                    except Exception as e:
                        logger.error(f"[LABO] set_board_from_fen virtuel : {e}")
                else:
                    _copy_cancel.set()
                    time.sleep(0.1)
                    def _copy_thread(fen=target_fen):
                        _do_copy_to_board(fen)
                        if not _copy_cancel.is_set():
                            try:
                                session.set_board_from_fen(fen)
                            except Exception as e:
                                logger.error(f"[LABO] set_board_from_fen : {e}")
                    threading.Thread(target=_copy_thread, daemon=True).start()

    _copy_cancel.set()
    session.quit()
    web_server._app_state = "menu"
    set_app_state("menu")


def _do_copy_to_board(target_fen: str) -> None:
    """Guide l'utilisateur pour reproduire un FEN cible sur le plateau physique."""
    nl = _nl_inst_ref
    if nl is None:
        return
    target = target_fen.strip().split()[0] if " " in target_fen else target_fen
    _copy_cancel.clear()

    send_event("labo_copy_start", {"target_fen": target})

    prev_fen = None
    while not _copy_cancel.is_set():
        try:
            raw = nl.get_fen()
            board_fen = raw.strip().split()[0] if raw else ""
            if board_fen == prev_fen:
                if board_fen == target:
                    nl.turn_off_all_leds()
                    send_event("position_ok", {"fen": target})
                    return
                send_event("position_error", {
                    "expected_fen": target,
                    "physical_fen": board_fen,
                })
            prev_fen = board_fen
        except Exception:
            pass
        time.sleep(0.3)
    nl.turn_off_all_leds()


# ── Labo libre ─────────────────────────────────────────────────────────────────
def launch_labo_libre(config):
    import json
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

    cfg_path    = DATA_DIR / "config.json"
    engine_elo  = 1500
    engine_path = ""
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_elo  = cfg.get("engine_elo", 1500)
            engine_path = _validated_engine_path(cfg)
        except Exception:
            pass

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = [False]
    t = threading.Thread(
        target=_run_labo_libre,
        args=(player, playing_white, start_fen, pause, analyse, bip,
              engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_perso, _error),
        daemon=True,
    )
    t.start()
    t.join()
    if _error[0]:
        time.sleep(3.0)
        web_server._app_state = "menu"
        set_app_state("menu")
    elif web_server._app_state != "game_over":
        web_server._app_state = "menu"
        set_app_state("menu")


def _run_labo_libre(player_name, playing_white, start_fen, pause, analyse_active, bip_active,
                       engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_personality,
                       _error=None):
    from nicsoft.modes.labo.labo import LaboSession
    global _nl_inst_ref
    nl_inst = None
    try:
        nl_inst = create_board(virtual=False, logger_name="NicLink_libre")
        logger.info("NicLink OK")
        _nl_inst_ref = nl_inst

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

        from nicsoft.web.server import action_queue as _aq
        while not _aq.empty():
            try: _aq.get_nowait()
            except Exception: break

        send_event("labo_init", {
            "fen":          fen_short,
            "player":       player_name,
            "human_color":  "white" if playing_white else "black",
            "engine_label": engine_label,
            "analyse":      analyse_active,
        })

        logger.info(f"Labo : {player_name} — {engine_label} depuis {fen_short[:30]}...")
        session.start()

    except SystemExit:
        pass
    except Exception as e:
        logger.error(f"Erreur labo : {e}")
        import traceback; traceback.print_exc()
        if _error: _error[0] = True
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass
        if web_server._app_state not in ("menu",):
            web_server._app_state = "menu"
