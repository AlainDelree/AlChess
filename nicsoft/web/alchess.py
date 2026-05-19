"""
nicsoft/web/__main__.py — Point d'entrée principal NicLink.
"""
import os
import time
import sys
import threading
import webbrowser
import socket
import logging
from nicsoft.config import DATA_DIR, LOGS_DIR
from nicsoft.platform_utils import stop_modem_manager, start_modem_manager
from nicsoft.web.server import start_server, set_app_state, get_menu_action, send_event, set_virtual_board
from nicsoft.web import server as web_server
import nicsoft.core.game_manager as gm
from nicsoft.core.board_adapter import create_board

# ── Logger timing ─────────────────────────────────────────────────────────────
# Activer avec : NICLINK_LOG=DEBUG python -m nicsoft.web
_timing_logger = logging.getLogger("niclink.timing")

LOG_FILE = LOGS_DIR / "niclink.log"

def _setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        str(LOG_FILE), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.WARNING)

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
    stop_modem_manager()


def _start_modem_manager():
    start_modem_manager()


_board_check_lock = threading.Lock()


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
            return  # l'utilisateur a navigué ailleurs
        for attempt in range(4):
            if attempt > 0:
                time.sleep(1.0)
            try:
                nl = create_board(virtual=False, logger_name="NicLink_startup")
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
    _retrans_save = DATA_DIR / "retranscription_en_cours.json"
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
            atype = action.get("type", "")

            if atype == "mode" and action.get("value") == "pedagogique":
                gm.set_virtual_mode(action.get("virtual", False))
                set_app_state("config")
            elif atype == "mode" and action.get("value") == "humain":
                set_app_state("config_humain")
            elif atype == "mode" and action.get("value") == "retranscription":
                set_app_state("retranscription")
            elif atype == "set_virtual_mode":
                gm.set_virtual_mode(action.get("virtual", False))
                print(f"[MENU] Mode virtuel : {gm._virtual_mode}")
                if gm._virtual_mode:
                    web_server._board_status = "virtual"
                    send_event("virtual_mode_active", {})
                else:
                    threading.Thread(target=_check_board_at_startup, daemon=True).start()
            elif atype == "mode" and action.get("value") == "analyse":
                set_app_state("game_over", {
                    "title_key":    "analyse.titre",
                    "result_key":   "analyse.importer_pgn",
                    "history_fen":  [],
                    "history_moves": [],
                    "init":         {},
                    "mode":         "analyse",
                })
            elif atype == "mode" and action.get("value") == "analyse_libre":
                gm.set_virtual_mode(action.get("virtual", False))
                gm.launch_labo()
            elif atype == "mode" and action.get("value") == "exercices":
                gm.set_virtual_mode(action.get("virtual", False))
                gm.launch_exercices()
            elif atype == "mode" and action.get("value") == "outils_exercices":
                set_app_state("outils_exercices")
            elif atype == "start_exercice":
                gm.start_exercice(action)
            elif atype == "start_drill":
                gm.start_drill(action)
            elif atype in ("exercice_back",):
                set_app_state("exercices")
                send_event("exercice_back", {})
            elif atype == "start_analyse_libre":
                gm.launch_analyse_libre(action)
            elif atype == "back":
                set_app_state("menu")
            elif atype == "start":
                gm.launch_pedagogique(action)
            elif atype == "start_humain":
                gm.launch_humain(action)
            elif atype == "start_retranscription":
                gm.launch_retranscription(action)
            elif atype == "back_menu":
                set_app_state("menu")
            elif atype == "reconnect_board":
                threading.Thread(target=_check_board_at_startup, daemon=True).start()
            elif atype == "quit":
                print("\nAu revoir !")
                nl = gm.get_nl_inst_ref()
                if nl is not None:
                    try: nl.turn_off_all_leds()
                    except Exception: pass
                _start_modem_manager()
                sys.exit(0)
    except KeyboardInterrupt:
        print("\nAu revoir !")
        nl = gm.get_nl_inst_ref()
        if nl is not None:
            try: nl.turn_off_all_leds()
            except Exception: pass
        _start_modem_manager()
        sys.exit(0)


if __name__ == "__main__":
    main()
