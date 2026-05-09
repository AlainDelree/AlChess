"""
nicsoft/web/__main__.py — Point d'entrée principal NicLink.
"""
import os
import re
import time
import random
import sys
import subprocess
import threading
import webbrowser
import socket
import chess
import logging
import pathlib
from nicsoft.web.server import start_server, set_app_state, get_menu_action, send_event, set_virtual_board
from nicsoft.web import server as web_server

# ── Logger timing ─────────────────────────────────────────────────────────────
# Activer avec : NICLINK_LOG=DEBUG python -m nicsoft.web
_timing_logger = logging.getLogger("niclink.timing")

LOG_FILE = pathlib.Path.home() / "NicLink" / "logs" / "niclink.log"

def _setup_logging():
    # Créer le dossier logs si besoin
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Handler fichier rotatif : 1MB max, 3 fichiers conservés
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        str(LOG_FILE), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Attacher à la racine pour capturer tous les modules
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.WARNING)

    # Capturer les exceptions non gérées
    import sys, traceback
    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("niclink.crash").critical(
            "Exception non gérée",
            exc_info=(exc_type, exc_value, exc_tb)
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _excepthook

    # Logger timing debug (inchangé)
    level = os.environ.get("NICLINK_LOG", "").upper()
    if level == "DEBUG":
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        _timing_logger.addHandler(handler)
        _timing_logger.setLevel(logging.DEBUG)
        _timing_logger.propagate = False
        print("[LOG] Mode DEBUG activé — timings visibles")
    else:
        _timing_logger.setLevel(logging.CRITICAL)

    from datetime import datetime
    debug_tag = " [DEBUG]" if level == "DEBUG" else ""
    marker = f"\n{'='*60}\n=== DÉMARRAGE{debug_tag} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n{'='*60}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(marker)
    logging.getLogger("niclink").info(f"NicLink démarré — log: {LOG_FILE}")


def _stop_modem_manager():
    """Stoppe ModemManager s'il tourne — évite les interférences USB avec l'échiquier."""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "stop", "ModemManager"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            print("[NicLink] ModemManager arrêté.")
    except Exception:
        pass  # pas de sudo configuré ou ModemManager absent — pas bloquant


def _start_modem_manager():
    """Relance ModemManager à la fin de NicLink."""
    try:
        subprocess.run(
            ["sudo", "systemctl", "start", "ModemManager"],
            capture_output=True, timeout=5
        )
    except Exception:
        pass


_nl_inst_ref = None  # référence globale pour extinction LEDs au Ctrl+C
_virtual_mode = False  # True si l'utilisateur a choisi le mode sans échiquier physique
_board_check_lock = threading.Lock()  # empêche plusieurs _check_board_at_startup simultanés

def _find_free_port(start=5000):
    """Trouve le premier port libre à partir de start."""
    port = start
    while port < 5100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    return start  # fallback


def main():
    _setup_logging()
    _stop_modem_manager()
    print("=== NicLink ===")
    _port = _find_free_port(5000)
    threading.Thread(target=start_server, kwargs={"host": "127.0.0.1", "port": _port}, daemon=True).start()
    time.sleep(0.5)  # laisser Flask démarrer
    webbrowser.open(f"http://127.0.0.1:{_port}")
    time.sleep(1.5)  # laisser la page charger avant d'envoyer app_state
    set_app_state("menu")
    threading.Thread(target=_check_board_at_startup, daemon=True).start()
    # Vérifier si une retranscription est en cours
    _retrans_save = pathlib.Path.home() / "NicLink" / "data" / "retranscription_en_cours.json"
    if _retrans_save.exists():
        import json as _json
        try:
            _saved = _json.loads(_retrans_save.read_text(encoding="utf-8"))
            nb = len(_saved.get("moves", []))
            send_event("retranscription_en_cours", {
                "white": _saved.get("white", "?"),
                "black": _saved.get("black", "?"),
                "moves": nb,
            })
        except Exception:
            pass
    try:
        while True:
            action = get_menu_action(timeout=1.0)
            if action is None:
                continue
            global _virtual_mode
            atype = action.get("type", "")
            if atype == "mode" and action.get("value") == "pedagogique":
                set_app_state("config")
            elif atype == "mode" and action.get("value") == "humain":
                set_app_state("config_humain")
            elif atype == "mode" and action.get("value") == "retranscription":
                set_app_state("retranscription")
            elif atype == "set_virtual_mode":
                _virtual_mode = action.get("virtual", False)
                print(f"[MENU] Mode virtuel : {_virtual_mode}")
                # Pas besoin de vérifier l'échiquier en mode virtuel
                if _virtual_mode:
                    web_server._board_status = "virtual"
                    send_event("virtual_mode_active", {})
                else:
                    # Retour mode physique → relancer la détection
                    threading.Thread(target=_check_board_at_startup, daemon=True).start()
            elif atype == "mode" and action.get("value") == "analyse":
                set_app_state("game_over", {
                    "title": "Analyse de partie",
                    "result": "Importez un fichier PGN",
                    "history_fen": [],
                    "history_moves": [],
                    "init": {},
                    "mode": "analyse",
                })
            elif atype == "mode" and action.get("value") == "analyse_libre":
                _launch_labo()
            elif atype == "mode" and action.get("value") == "exercices":
                _launch_exercices()
            elif atype == "mode" and action.get("value") == "outils_exercices":
                set_app_state("outils_exercices")
            elif atype == "start_exercice":
                global _ex_thread, _exercice_running
                if _ex_thread and _ex_thread.is_alive():
                    _ex_thread.join(timeout=3.0)
                    if _ex_thread.is_alive():
                        print("[EXERCICE] Thread précédent encore vivant après join — force reset")
                        _exercice_running = False
                _ex_thread = threading.Thread(target=_run_exercice, args=(action,), daemon=True)
                _ex_thread.start()
            elif atype == "start_drill":
                if _ex_thread and _ex_thread.is_alive():
                    _ex_thread.join(timeout=3.0)
                _ex_thread = threading.Thread(target=_run_drill, args=(action,), daemon=True)
                _ex_thread.start()
            elif atype in ("exercice_back",):
                set_app_state("exercices")
                send_event("exercice_back", {})
            elif atype == "start_analyse_libre":
                _launch_analyse_libre(action)
            elif atype == "back":
                set_app_state("menu")
            elif atype == "start":
                _launch_pedagogique(action)
            elif atype == "start_humain":
                _launch_humain(action)
            elif atype == "start_retranscription":
                _launch_retranscription(action)
            elif atype == "back_menu":
                set_app_state("menu")
            elif atype == "reconnect_board":
                threading.Thread(target=_check_board_at_startup, daemon=True).start()
            elif atype == "quit":
                print("\nAu revoir !")
                if _nl_inst_ref is not None:
                    try: _nl_inst_ref.turn_off_all_leds()
                    except Exception: pass
                _start_modem_manager()
                sys.exit(0)
    except KeyboardInterrupt:
        print("\nAu revoir !")
        if _nl_inst_ref is not None:
            try:
                _nl_inst_ref.turn_off_all_leds()
            except Exception:
                pass
        _start_modem_manager()
        sys.exit(0)


def _check_board_at_startup():
    if not _board_check_lock.acquire(blocking=False):
        return  # une vérification est déjà en cours
    try:
        for _ in range(100):
            time.sleep(0.1)
            if web_server._app_state == "menu":
                break
        time.sleep(1.0)
        if web_server._app_state != "menu":
            return  # l'utilisateur a navigué ailleurs — ne pas connecter le hardware
        from nicsoft.niclink import NicLinkManager
        _logger = logging.getLogger("NicLink_startup")
        for attempt in range(4):
            if attempt > 0:
                time.sleep(1.0)
            try:
                devnull_fd = os.open(os.devnull, os.O_WRONLY)
                old_fd = os.dup(1)
                try:
                    os.dup2(devnull_fd, 1)
                    nl = NicLinkManager(refresh_delay=0.1, logger=_logger, thread_sleep_delay=0.1)
                finally:
                    os.dup2(old_fd, 1)
                    os.close(devnull_fd)
                    os.close(old_fd)
                try:
                    nl._fen_reader_stop.set()
                except Exception:
                    pass
                send_event("board_ok", {})
                return  # succès
            except SystemExit as e:
                if "board connection error" not in str(e):
                    send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
                    return
                # board pas encore prêt — réessayer
            except Exception:
                pass  # réessayer
        send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    finally:
        _board_check_lock.release()


def _launch_pedagogique(config):
    import json, pathlib
    player  = config.get("player", "Anonyme") or "Anonyme"
    color   = config.get("color", "white")
    level   = int(config.get("level", 5))
    pause   = config.get("pause", "blunder")
    analyse = config.get("analyse_active", True)
    bip     = config.get("bip_active", False)
    engine_type = config.get("engine_type", "stockfish")
    maia_elo    = int(config.get("maia_elo", 1500))
    rodent_elo  = int(config.get("rodent_elo", 800))
    rodent_simple = config.get("rodent_simple", False)
    if color == "random":
        color = random.choice(["white", "black"])
    playing_white = (color == "white")

    # Lire engine_elo et engine_path depuis config.json
    cfg_path = pathlib.Path.home() / "NicLink" / "data" / "config.json"
    engine_elo  = 1500
    engine_path = ""
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_elo  = cfg.get("engine_elo", 1500)
            engine_path = cfg.get("engine_path", "")
        except Exception:
            pass

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = [False]
    t = threading.Thread(
        target=_run_pedagogique,
        args=(player, playing_white, level, pause, analyse, bip,
              engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_simple, _error),
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


def _launch_retranscription(config):
    """Lance le mode retranscription — délègue au module nicsoft.modes.retranscription."""
    from nicsoft.modes.retranscription.retranscription import run_retranscription
    from nicsoft.web.server import get_action as _get_action
    import queue as _queue

    # Vider les actions résiduelles avant de lancer le thread
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



def _launch_humain(config):
    white = config.get("white", "Anonyme1") or "Anonyme1"
    black = config.get("black", "Anonyme2") or "Anonyme2"
    if config.get("color") == "random":
        if random.random() < 0.5:
            white, black = black, white
    game_type = config.get("game_type", "serieuse")
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
        pass  # fin normale : laisser l'écran game_over visible
    else:
        # back_menu ou autre fin — toujours revenir au menu et renvoyer board_ok
        web_server._app_state = "menu"
        set_app_state("menu")


def _run_pedagogique(player_name, playing_white, level, pause, analyse_active, bip_active,
                     engine_elo, engine_path, engine_type="stockfish", maia_elo=1500,
                     rodent_elo=800, rodent_simple=False, _error=None, virtual=False):
    from nicsoft.modes.pedagogique.pedagogique import Game, load_config, BackMenuExit
    from nicsoft.web.server import get_action

    config = load_config()
    config["pedagogique_pause"] = pause
    nl_inst = None
    try:
        if virtual:
            from nicsoft.niclink.virtual_board import VirtualBoard
            nl_inst = VirtualBoard()
            set_virtual_board(nl_inst)
            print("VirtualBoard OK")
        else:
            from nicsoft.niclink import NicLinkManager
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            old_fd = os.dup(1)
            try:
                os.dup2(devnull_fd, 1)
                _logger = logging.getLogger("NicLink")
                nl_inst = NicLinkManager(refresh_delay=0.1, logger=_logger, thread_sleep_delay=0.1)
            finally:
                os.dup2(old_fd, 1)
                os.close(devnull_fd)
                os.close(old_fd)
            print("NicLink OK")
        global _nl_inst_ref
        _nl_inst_ref = nl_inst
        if not virtual:
            _wait_initial_position_web(nl_inst)

        if engine_type == "maia":
            engine_label = f"Maia {maia_elo}"
        elif engine_type == "rodent":
            engine_label = f"Rodent {rodent_elo}" + (" (Simple)" if rodent_simple else "")
        else:
            engine_label = f"Stockfish ~{engine_elo}elo"

        # Initialiser le moteur AVANT de basculer en "playing" — le démarrage de
        # Stockfish (2 processus, ~0.5-1s) ne sera plus visible pour le joueur.
        game = Game(
            nl_inst, playing_white,
            stockfish_level=level,
            default_game_type="pedagogique",
            turn_signal=config.get("turn_signal", "both"),
            pedagogique_pause=pause,
            engine_elo=engine_elo,
            analyse_active=analyse_active,
            bip_active=bip_active,
            engine_path=engine_path,
            engine_type=engine_type,
            maia_elo=maia_elo,
            rodent_elo=rodent_elo,
            rodent_simple=rodent_simple,
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
        print(f"Partie : {player_name} vs {engine_label}")
        game.start()
    except BackMenuExit:
        pass  # retour menu propre — le processus continue
    except SystemExit as e:
        if "board connection error" in str(e):
            print("Erreur : échiquier non détecté.")
            if _error: _error[0] = True
            send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    except Exception as e:
        print(f"Erreur connexion échiquier : {e}")
        import traceback; traceback.print_exc()
        if _error: _error[0] = True
        send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    finally:
        set_virtual_board(None)
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass
        if web_server._app_state != "game_over":
            web_server._app_state = "menu"


def _run_humain(white_name, black_name, game_type, _error=None, virtual=False):
    from nicsoft.modes.humain.human import GameWeb
    nl_inst = None
    try:
        if virtual:
            from nicsoft.niclink.virtual_board import VirtualBoard
            nl_inst = VirtualBoard()
            set_virtual_board(nl_inst)
            print("VirtualBoard OK — Humain")
        else:
            from nicsoft.niclink import NicLinkManager
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            old_fd = os.dup(1)
            try:
                os.dup2(devnull_fd, 1)
                _logger = logging.getLogger("NicLink_humain")
                nl_inst = NicLinkManager(refresh_delay=0.1, logger=_logger, thread_sleep_delay=0.1)
            finally:
                os.dup2(old_fd, 1)
                os.close(devnull_fd)
                os.close(old_fd)
        if not virtual:
            _wait_initial_position_web(nl_inst)
        global _nl_inst_ref
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
        print(f"Partie : {white_name} vs {black_name}")
        game.start()
        if game.game_over and web_server._app_state != "game_over":
            web_server._app_state = "game_over"

    except SystemExit:
        pass  # fin normale via sys.exit(0) dans _traiter_abandon ou _end_game
    except Exception as e:
        print(f"Erreur : {e}")
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


def _wait_initial_position_web(nl_inst, timeout: float = 300.0):
    import chess as _chess
    INITIAL_FEN = _chess.Board().board_fen()
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


def _launch_exercices():
    """Affiche l'écran de sélection des exercices — initialise NicLink si besoin."""
    from nicsoft.modes.exercices.exercices import get_ouvertures, get_mes_lignes
    web_server._app_state = "exercices"
    set_app_state("exercices", {
        "ouvertures":  get_ouvertures(),
        "mes_lignes":  get_mes_lignes(),
    })





_exercice_running = False  # guard contre les lancements multiples
_ex_thread = None          # thread exercice courant
_exercice_session = 0      # numéro de session — protège le finally des vieux threads


def _run_exercice(config: dict) -> None:
    """Lance une session d'exercice — même pattern que pédagogique."""
    global _exercice_running, _nl_inst_ref, _exercice_session
    if _exercice_running:
        return
    _exercice_running = True
    _exercice_session += 1
    my_session = _exercice_session

    from nicsoft.modes.exercices.exercices import ExerciceSession, OUVERTURES, get_mes_lignes
    import logging as _log

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
        if _virtual_mode:
            from nicsoft.niclink.virtual_board import VirtualBoard
            nl_inst = VirtualBoard()
            set_virtual_board(nl_inst)
            print("VirtualBoard OK — Exercice")
        else:
            from nicsoft.niclink import NicLinkManager
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            old_fd = os.dup(1)
            try:
                os.dup2(devnull_fd, 1)
                nl_inst = NicLinkManager(refresh_delay=0.1,
                                         logger=_log.getLogger("NicLink_exercice"),
                                         thread_sleep_delay=0.1)
            finally:
                os.dup2(old_fd, 1)
                os.close(devnull_fd)
                os.close(old_fd)
            print("NicLink OK — Exercice ouverture")

        _nl_inst_ref = nl_inst

        web_server._app_state = "exercice_running"
        set_app_state("exercice_running")

        send_event("exercice_init", {
            "ouverture":   ouverture,
            "human_color": human_color,
            "variete":     variete,
        })

        session = ExerciceSession(nl_inst, ouverture, human_color, variete)

        # Créer un moteur pour le mode "continuer après livre"
        engine = None
        try:
            from nicsoft.engine.engine_manager import EngineManager, find_stockfish
            import json, pathlib
            cfg_path = pathlib.Path.home() / "NicLink" / "data" / "config.json"
            engine_elo  = 1500
            engine_path = ""
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                engine_elo  = cfg.get("engine_elo", 1500)
                engine_path = cfg.get("engine_path", "")
            if not engine_path:
                engine_path = find_stockfish() or "stockfish"
            engine = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=False)
            session._engine = engine
        except Exception as e:
            print(f"[EXERCICE] Moteur non disponible pour mode libre : {e}")

        # En mode virtuel : synchroniser le game_board avec la position d'init
        # pour que current_fen retourne le bon FEN lors de sync_from_physical()
        if _virtual_mode:
            nl_inst.game_board = session.board.copy()

        session.run()

    except Exception as e:
        print(f"[EXERCICE] Erreur : {e}")
        import traceback; traceback.print_exc()
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
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
    """Lance une session de drill multi-lignes depuis mes_lignes."""
    global _exercice_running, _nl_inst_ref, _exercice_session
    if _exercice_running:
        return
    _exercice_running = True
    _exercice_session += 1
    my_session = _exercice_session

    from nicsoft.modes.exercices.exercices import DrillSession, get_mes_lignes
    import logging as _log

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
        if _virtual_mode:
            from nicsoft.niclink.virtual_board import VirtualBoard
            nl_inst = VirtualBoard()
            set_virtual_board(nl_inst)
        else:
            from nicsoft.niclink import NicLinkManager
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            old_fd = os.dup(1)
            try:
                os.dup2(devnull_fd, 1)
                nl_inst = NicLinkManager(refresh_delay=0.1,
                                         logger=_log.getLogger("NicLink_drill"),
                                         thread_sleep_delay=0.1)
            finally:
                os.dup2(old_fd, 1)
                os.close(devnull_fd)
                os.close(old_fd)

        _nl_inst_ref = nl_inst

        web_server._app_state = "exercice_running"
        set_app_state("exercice_running")

        # Construire l'ouverture synthétique pour exercice_init
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
            import json, pathlib
            cfg_path = pathlib.Path.home() / "NicLink" / "data" / "config.json"
            engine_elo = 1500
            engine_path = find_stockfish() or "stockfish"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text())
                engine_path = cfg.get("engine_path", engine_path)
                engine_elo  = cfg.get("engine_elo", engine_elo)
            engine = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=False)
            session._engine = engine
        except Exception as e:
            print(f"[DRILL] Moteur non chargé : {e}")

        # Sync plateau avant de lancer
        nl_inst.game_board = session.board.copy()
        session.run()

    except Exception as e:
        print(f"[DRILL] Erreur : {e}")
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
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


def _launch_labo():
    """Lance le labo — polling plateau physique ou VirtualBoard selon le mode."""
    import queue as _queue
    _copy_cancel.set()  # annuler tout thread copy en cours
    while True:
        try:
            web_server.action_queue.get_nowait()
        except _queue.Empty:
            break
    web_server._app_state = "labo"
    set_app_state("labo")
    if _virtual_mode:
        # En mode virtuel : créer le VirtualBoard ici, pas de polling USB
        from nicsoft.niclink.virtual_board import VirtualBoard
        vb = VirtualBoard()
        set_virtual_board(vb)
        global _nl_inst_ref
        _nl_inst_ref = vb
        threading.Thread(target=_run_labo_session, daemon=True).start()
    else:
        threading.Thread(target=_poll_board_fen_labo, daemon=True).start()
        threading.Thread(target=_run_labo_session, daemon=True).start()


def _poll_board_fen_labo():
    """Envoie le FEN physique au navigateur toutes les 300ms pendant le labo."""
    from nicsoft.niclink import NicLinkManager
    import logging as _log
    nl = None
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        old_fd = os.dup(1)
        try:
            os.dup2(devnull_fd, 1)
            nl = NicLinkManager(refresh_delay=0.1, logger=_log.getLogger("NL_labo_poll"),
                                thread_sleep_delay=0.1)
        finally:
            os.dup2(old_fd, 1)
            os.close(devnull_fd)
            os.close(old_fd)
        global _nl_inst_ref
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
        print(f"[LABO POLL] Erreur : {e}")
    finally:
        if nl:
            try: nl._fen_reader_stop.set()
            except Exception: pass


def _make_labo_session(nl_inst, config: dict):
    """Crée une LaboSession depuis la config courante."""
    from nicsoft.modes.labo.labo import LaboSession
    from nicsoft.engine.engine_manager import find_stockfish
    engine_path = ""
    try:
        import json, pathlib
        cfg_path = pathlib.Path.home() / "NicLink" / "data" / "config.json"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = json.load(f)
            engine_path = cfg.get("engine_path", "")
    except Exception:
        pass
    if not engine_path:
        engine_path = find_stockfish() or "stockfish"

    # camp moteur = opposé du camp humain
    human = config.get("human_color", "white")
    engine_color = "black" if human == "white" else "white"

    return LaboSession(
        nl_inst,
        engine_color   = engine_color,
        engine_elo     = config.get("engine_elo", 1500),
        analyse_active = config.get("analyse", True),
        engine_path    = engine_path,
        engine_type    = config.get("engine_type", "stockfish"),
        maia_elo       = config.get("maia_elo", 1500),
        rodent_elo     = config.get("rodent_elo", 800),
    )


def _run_labo_session():
    """Boucle principale du labo."""
    from nicsoft.web.server import get_action as _get_action

    # Attendre que nl_inst_ref soit disponible
    for _ in range(50):
        if _nl_inst_ref is not None:
            break
        time.sleep(0.1)

    nl = _nl_inst_ref
    if nl is None:
        print("[LABO] Échiquier non disponible")
        return

    labo_config = {
        "human_color": "white",
        "engine_type": "stockfish",
        "engine_elo":  1500,
        "maia_elo":    1500,
        "rodent_elo":  800,
        "analyse":     True,
    }

    try:
        session = _make_labo_session(nl, labo_config)
    except Exception as e:
        print(f"[LABO] Erreur création session : {e}")
        return

    # Lancer le watcher plateau (physique uniquement — inutile en mode virtuel)
    session._running = True
    if not _virtual_mode:
        threading.Thread(target=session.board_watcher, daemon=True).start()
        # Synchroniser avec le plateau physique actuel
        session.sync_from_physical()
    else:
        # Mode virtuel : watcher qui lit les coups depuis la _move_queue du VirtualBoard
        nl.make_virtual_board_watcher(session).start()
        session._send_position()

    # Envoyer init
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
            for k in ("human_color", "engine_type", "engine_elo", "maia_elo", "rodent_elo", "analyse"):
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
                # Si auto ON et c'est maintenant au moteur → jouer
                if session._auto_on and session.board.turn == new_ec and not session._engine_busy:
                    session.do_engine_play()

            elif engine_changed:
                old_board   = session.board
                old_history = session._fen_history[:]
                session._running = False
                time.sleep(0.2)
                try:
                    session = _make_labo_session(nl, labo_config)
                    session.board         = old_board
                    session._fen_history  = old_history
                    nl.game_board         = session.board.copy()
                    session._running      = True
                    threading.Thread(target=session.board_watcher, daemon=True).start()
                    send_event("labo_init", {
                        "fen":          session.board.board_fen(),
                        "human_color":  labo_config["human_color"],
                        "engine_label": session.engine_label,
                        "analyse":      labo_config["analyse"],
                    })
                    session._send_position()
                except Exception as e:
                    print(f"[LABO] Erreur recréation : {e}")

        elif atype == "best_move":
            # Vider les best_move en attente dans la queue (clics multiples)
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
                # Toujours synchroniser depuis le plateau physique au démarrage Auto
                session.sync_from_physical(turn=labo_config.get("active_turn", session.active_turn))
                time.sleep(0.1)
                # Drainer les toggles Auto en attente (clic rapide ON→OFF)
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
            time.sleep(0.1)  # laisser le board se mettre à jour
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
                        session.set_board_from_fen(target_fen)   # envoie labo_position
                        send_event("position_ok", {"fen": fen_clean})
                    except Exception as e:
                        print(f"[LABO] set_board_from_fen virtuel : {e}")
                else:
                    _copy_cancel.set()  # annuler tout copy précédent
                    time.sleep(0.1)     # laisser l'ancien thread s'arrêter
                    def _copy_thread(fen=target_fen):
                        _do_copy_to_board(fen)
                        if not _copy_cancel.is_set():
                            try:
                                session.set_board_from_fen(fen)
                            except Exception as e:
                                print(f"[LABO] set_board_from_fen : {e}")
                    threading.Thread(target=_copy_thread, daemon=True).start()

    _copy_cancel.set()  # annuler tout copy en cours à la sortie du labo
    session.quit()
    web_server._app_state = "menu"
    set_app_state("menu")


_copy_cancel = threading.Event()  # flag pour annuler _do_copy_to_board


def _do_copy_to_board(target_fen: str) -> None:
    """Guide l'utilisateur pour reproduire un FEN cible sur le plateau physique."""
    global _nl_inst_ref
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
            # N'agir que si le FEN est stable (identique à la lecture précédente)
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
    # Annulé — éteindre les LEDs
    nl.turn_off_all_leds()


def _poll_board_fen():
    """Envoie le FEN physique au navigateur toutes les 500ms pendant config_analyse_libre."""
    from nicsoft.niclink import NicLinkManager
    import logging as _log
    nl = None
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        old_fd = os.dup(1)
        try:
            os.dup2(devnull_fd, 1)
            nl = NicLinkManager(refresh_delay=0.1, logger=_log.getLogger("NL_poll"), thread_sleep_delay=0.1)
        finally:
            os.dup2(old_fd, 1)
            os.close(devnull_fd)
            os.close(old_fd)
        while web_server._app_state == "config_analyse_libre":
            try:
                raw = nl.get_fen()
                fen = raw.strip().split()[0] if raw else ""
                if fen:
                    send_event("board_fen_update", {"fen": fen})
            except Exception:
                pass
            time.sleep(0.5)
    except Exception as e:
        print(f"[POLL] Erreur lecture FEN : {e}")
    finally:
        if nl:
            try:
                nl._fen_reader_stop.set()
            except Exception:
                pass


def _launch_analyse_libre(config):
    player       = config.get("player", "Anonyme") or "Anonyme"
    color        = config.get("color", "white")
    start_fen    = config.get("fen", chess.STARTING_FEN)
    pause        = config.get("pause", "blunder")
    analyse      = config.get("analyse_active", True)
    bip          = config.get("bip_active", False)
    engine_type  = config.get("engine_type", "stockfish")
    maia_elo     = int(config.get("maia_elo", 1500))
    rodent_elo   = int(config.get("rodent_elo", 800))
    rodent_simple = config.get("rodent_simple", False)

    if color == "random":
        color = random.choice(["white", "black"])
    playing_white = (color == "white")

    import json, pathlib
    cfg_path = pathlib.Path.home() / "NicLink" / "data" / "config.json"
    engine_elo  = 1500
    engine_path = ""
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_elo  = cfg.get("engine_elo", 1500)
            engine_path = cfg.get("engine_path", "")
        except Exception:
            pass

    web_server._app_state = "connecting"
    set_app_state("connecting")
    _error = [False]
    t = threading.Thread(
        target=_run_analyse_libre,
        args=(player, playing_white, start_fen, pause, analyse, bip,
              engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_simple, _error),
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


def _run_analyse_libre(player_name, playing_white, start_fen, pause, analyse_active, bip_active,
                       engine_elo, engine_path, engine_type, maia_elo, rodent_elo, rodent_simple, _error=None):
    from nicsoft.niclink import NicLinkManager
    from nicsoft.modes.labo.labo import LaboSession

    nl_inst = None
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        old_fd = os.dup(1)
        try:
            os.dup2(devnull_fd, 1)
            _logger = logging.getLogger("NicLink_libre")
            nl_inst = NicLinkManager(refresh_delay=0.1, logger=_logger, thread_sleep_delay=0.1)
        finally:
            os.dup2(old_fd, 1)
            os.close(devnull_fd)
            os.close(old_fd)

        print("NicLink OK")
        global _nl_inst_ref
        _nl_inst_ref = nl_inst

        # Attendre que le plateau corresponde au FEN de départ
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
            human_color="white" if playing_white else "black",
            start_fen=start_fen,
            engine_elo=engine_elo,
            analyse_active=analyse_active,
            engine_path=engine_path,
            engine_type=engine_type,
            maia_elo=maia_elo,
            rodent_elo=rodent_elo,
            rodent_simple=rodent_simple,
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

        print(f"Labo : {player_name} — {engine_label} depuis {fen_short[:30]}...")
        session.start()

    except SystemExit:
        pass
    except Exception as e:
        print(f"Erreur labo : {e}")
        import traceback; traceback.print_exc()
        if _error: _error[0] = True
        send_event("board_error", {"message": "Échiquier non détecté."})
    finally:
        if nl_inst:
            try: nl_inst.turn_off_all_leds()
            except Exception: pass
        if web_server._app_state not in ("menu",):
            web_server._app_state = "menu"


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


if __name__ == "__main__":
    main()
