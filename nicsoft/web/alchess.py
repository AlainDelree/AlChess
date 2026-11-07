"""
nicsoft/web/__main__.py — Point d'entrée principal NicLink.
"""
import os
import time
import sys
import subprocess
import threading
import webbrowser
import socket
import logging
from nicsoft.config import APP_DIR, LOGS_DIR
from nicsoft.platform_utils import stop_modem_manager, start_modem_manager
from nicsoft.web.server import start_server, set_app_state, get_menu_action, send_event, set_virtual_board
from nicsoft.web import server as web_server
import nicsoft.core.game_manager as gm
from nicsoft.core.board_adapter import create_board
from nicsoft.core import ihm_port
from nicsoft.engine.board_utils import pgn_moves_played


class _WebBackend:
    """
    Implémentation concrète du port neutre nicsoft.core.ihm_port, branchée
    sur le serveur Flask-SocketIO (règle ARC-001 — voir ihm_port.py).
    _check_board_at_startup est résolu par son nom au moment de l'appel :
    il n'est défini qu'au bas de ce module, après cette classe.
    """

    def send_event(self, event_type, data):
        web_server.send_event(event_type, data)

    def emit(self, event_type, data):
        web_server.socketio.emit(event_type, data)

    def set_history(self, history, history_fen):
        web_server.set_history(history, history_fen)

    def get_history(self):
        return web_server.get_history()

    def get_init_data(self):
        return web_server.get_init_data()

    def get_action(self, timeout=0.0):
        return web_server.get_action(timeout)

    def set_app_state(self, state, data=None):
        web_server.set_app_state(state, data)

    def get_menu_action(self, timeout=1.0):
        return web_server.get_menu_action(timeout)

    def set_virtual_board(self, vb):
        web_server.set_virtual_board(vb)

    @property
    def action_queue(self):
        return web_server.action_queue

    def get_app_state(self):
        return web_server._app_state

    def set_raw_app_state(self, state):
        web_server._app_state = state

    def check_board_at_startup(self):
        _check_board_at_startup()


ihm_port.register_backend(_WebBackend())

# ── Logger timing ─────────────────────────────────────────────────────────────
# Activer avec : NICLINK_LOG=DEBUG python -m nicsoft.web
_timing_logger = logging.getLogger("niclink.timing")
logger = logging.getLogger("niclink")

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

    # python-chess relaie la sortie stderr des moteurs UCI (lc0/Maia, Stockfish...)
    # en WARNING sur le logger "chess.engine" — ce sont des bannières de démarrage
    # normales (version, backend, poids chargés...), pas de vrais avertissements.
    # Les échecs réels de démarrage/arrêt des moteurs sont déjà journalisés par
    # engine_manager.py via le logger "niclink" (cf. issue #265).
    logging.getLogger("chess.engine").setLevel(logging.ERROR)

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
    """N'arrête jamais ModemManager lors d'un lancement sans échiquier
    (ALCHESS_SKIP_BOARD=1, ex. tests de bout en bout) — un tel lancement n'a
    aucune raison de toucher à un service système."""
    if os.environ.get("ALCHESS_SKIP_BOARD") == "1":
        return
    stop_modem_manager()


def _start_modem_manager():
    """Symétrique de _stop_modem_manager : ne relance pas non plus
    ModemManager en l'absence d'échiquier, puisqu'il n'a jamais été arrêté."""
    if os.environ.get("ALCHESS_SKIP_BOARD") == "1":
        return
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
                port += 1  # port déjà occupé, on tente le suivant
    return start  # fallback


def _run_detect_chessnut():
    """Best-effort, non bloquant : toute erreur est journalisée et ignorée."""
    logger = logging.getLogger("niclink")
    detect_script = APP_DIR / "scripts" / "detect_chessnut.py"
    if not detect_script.exists():
        return
    try:
        result = subprocess.run(
            [sys.executable, str(detect_script)], capture_output=True, text=True, timeout=15
        )
        if result.returncode == 1:
            logger.info("Nouveau modèle Chessnut enregistré. Relancez l'application.")
        elif result.returncode == 0:
            logger.info("Aucun échiquier Chessnut reconnu branché au démarrage.")
        else:
            logger.info(f"detect_chessnut.py — code retour {result.returncode} : {result.stderr.strip()}")
    except Exception as e:
        logger.info(f"detect_chessnut.py — appel best-effort échoué : {e}")


def _maybe_open_browser(url):
    """Ouvre `url` dans le navigateur par défaut, sauf lancement sans
    utilisateur (ALCHESS_SKIP_BOARD=1) ou vérification explicite demandant
    l'absence de navigateur (ALCHESS_NO_BROWSER=1)."""
    if os.environ.get("ALCHESS_SKIP_BOARD") == "1" or os.environ.get("ALCHESS_NO_BROWSER") == "1":
        return
    webbrowser.open(url)


def _check_board_at_startup():
    if os.environ.get("ALCHESS_SKIP_BOARD") == "1":
        return  # tests e2e — pas d'échiquier physique à solliciter
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
                except Exception as e:
                    # arrêt best-effort du lecteur du plateau temporaire : un échec est sans conséquence
                    # (threading.Event.set() ne documente aucune exception en usage normal — ce log
                    # est purement diagnostique si l'attribut venait à manquer dans un cas inattendu)
                    logger.debug("arrêt best-effort du lecteur temporaire échoué : %s", e)
                send_event("board_ok", {})
                return  # succès
            except SystemExit as e:
                if "board connection error" not in str(e):
                    _run_detect_chessnut()
                    send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
                    return
                # board pas encore prêt — réessayer
            except Exception as e:
                # réessayer — échec d'ouverture HID (OSError/IOError, cf. hid.device.open_path()
                # dans hidapi) ou de démarrage d'un thread interne (RuntimeError) ; boucle lente
                # (1 tentative/s, 4 tentatives max) donc une trace de diagnostic est utile ici.
                logger.debug("tentative de connexion au plateau (essai %d/4) échouée : %s", attempt + 1, e)
        _run_detect_chessnut()
        send_event("board_error", {"message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau."})
    finally:
        _board_check_lock.release()


def _board_menu_watcher():
    """
    Surveille la connexion physique du plateau tant que l'app est au menu.
    Ne fait rien en cours de partie (surveillance déjà assurée par
    _fen_reader_loop côté driver.py) — couvre uniquement la déconnexion
    détectée alors que l'utilisateur est resté sur l'écran menu.
    """
    from nicsoft.niclink import hid_backend
    _already_notified = False
    while True:
        time.sleep(3.0)
        if web_server._app_state != "menu":
            _already_notified = False
            continue
        try:
            if not hid_backend.check_physically_present():
                if web_server._board_status == "ok" and not _already_notified:
                    send_event("board_error", {
                        "message": "Échiquier déconnecté — vérifiez l'USB et reconnectez le plateau.",
                        "message_key": "error.board.deconnecte",
                    })
                    _already_notified = True
            else:
                _already_notified = False  # plateau reconnecté
        except Exception as e:
            logger.debug(f"[WATCHER] Vérification présence plateau échouée : {e}")


def _check_retranscription_session():
    """Relit la session de retranscription sauvegardée et notifie le
    navigateur si elle existe. Appelée à chaque ouverture de l'écran
    retranscription (pas seulement au démarrage du programme) pour que le
    bandeau de reprise soit proposé même en cas de retour après un premier
    passage par ce mode au cours de la même exécution."""
    from nicsoft.modes.retranscription.retranscription import load_session
    saved = load_session()
    if not saved:
        return  # pas de session en attente — le frontend masque le bandeau par défaut
    nb_demi_coups = len(saved.get("moves", []))
    send_event("retranscription_en_cours", {
        "white": saved.get("white", "?"),
        "black": saved.get("black", "?"),
        "moves": pgn_moves_played(nb_demi_coups),
    })


def main():
    _setup_logging()
    _stop_modem_manager()
    print("=== NicLink ===")
    _port = _find_free_port(5000)
    threading.Thread(target=start_server, kwargs={"host": "127.0.0.1", "port": _port}, daemon=True).start()
    time.sleep(0.5)  # laisser Flask démarrer
    _maybe_open_browser(f"http://127.0.0.1:{_port}")
    time.sleep(1.5)  # laisser la page charger avant d'envoyer app_state
    set_app_state("menu")
    if os.environ.get("ALCHESS_SKIP_BOARD") != "1":
        threading.Thread(target=_check_board_at_startup, daemon=True).start()
        threading.Thread(target=_board_menu_watcher, daemon=True).start()
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
                _check_retranscription_session()
            elif atype == "set_virtual_mode":
                gm.set_virtual_mode(action.get("virtual", False))
                print(f"[MENU] Mode virtuel : {gm.get_virtual_mode()}")
                if gm.get_virtual_mode():
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
            elif atype == "mode" and action.get("value") == "labo":
                gm.set_virtual_mode(action.get("virtual", False))
                gm.launch_labo()
            elif atype == "mode" and action.get("value") == "exercices":
                gm.set_virtual_mode(action.get("virtual", False))
                gm.launch_exercices()
            elif atype == "mode" and action.get("value") == "ouvertures":
                set_app_state("ouvertures")
            elif atype == "mode" and action.get("value") == "outils_exercices":
                set_app_state("outils_exercices")
            elif atype == "mode" and action.get("value") == "parametres":
                set_app_state("parametres")
            elif atype == "mode" and action.get("value") == "opening_explorer":
                virtual = action.get("virtual", False) or (web_server._board_status != "ok")
                gm.set_virtual_mode(virtual)
                set_app_state("opening_explorer")
            elif atype == "start_exercice":
                gm.start_exercice(action)
            elif atype == "start_drill":
                gm.start_drill(action)
            elif atype in ("exercice_back",):
                set_app_state("exercices")
                send_event("exercice_back", {})
            elif atype == "start_labo_libre":
                gm.launch_labo_libre(action)
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
            elif atype == "quit":
                print("\nAu revoir !")
                nl = gm.get_nl_inst_ref()
                if nl is not None:
                    try: nl.turn_off_all_leds()
                    except ValueError as e:
                        # nettoyage best-effort en fin de programme — ValueError : course possible
                        # entre ce vidage de _led_queue et le thread _led_worker_loop qui consomme
                        # la même queue (task_done() appelé en double, cf. driver.py ~l.234).
                        logger.debug("extinction des LEDs best-effort échouée : %s", e)
                _start_modem_manager()
                sys.exit(0)
    except KeyboardInterrupt:
        print("\nAu revoir !")
        nl = gm.get_nl_inst_ref()
        if nl is not None:
            try: nl.turn_off_all_leds()
            except ValueError as e:
                # nettoyage best-effort en fin de programme — ValueError : course possible
                # entre ce vidage de _led_queue et le thread _led_worker_loop qui consomme
                # la même queue (task_done() appelé en double, cf. driver.py ~l.234).
                logger.debug("extinction des LEDs best-effort échouée : %s", e)
        _start_modem_manager()
        sys.exit(0)


if __name__ == "__main__":
    main()
