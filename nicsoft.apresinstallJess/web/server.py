"""
nicsoft/web/server.py — Serveur Flask-SocketIO pour l'interface pédagogique NicLink.

Ce serveur tourne en parallèle du module play_pedagogique.
Il reçoit les événements de jeu via une queue Python et les transmet
au navigateur via SocketIO. Les actions du navigateur remontent
via SocketIO à Python.
"""

import logging
import os
import pathlib
import queue
import threading
from flask import Flask, render_template, send_file, abort
from flask_socketio import SocketIO, emit

logger = logging.getLogger("niclink.server")
LOG_FILE = pathlib.Path.home() / "NicLink" / "logs" / "niclink.log"

app = Flask(__name__)
app.config["SECRET_KEY"] = "niclink_pedagogique"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Queue pour recevoir les événements du module Python
event_queue: queue.Queue = queue.Queue()

# Queue pour recevoir les actions du navigateur vers Python
action_queue: queue.Queue = queue.Queue()

# Dernier état connu — renvoyé au navigateur qui se (re)connecte
_game_state: dict = {}

# État de l application : menu / config / playing / game_over
_app_state: str = "menu"

# Queue pour les actions du menu (choix mode, config joueur, etc.)
menu_queue: queue.Queue = queue.Queue()

# Statut de la connexion échiquier — renvoyé au navigateur qui se connecte
# None = pas encore vérifié, "ok" = connecté, "error" = non détecté
_board_status: str = None
_board_error_message: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/logs")
def get_logs():
    """Sert le fichier de log pour téléchargement/consultation."""
    if LOG_FILE.exists():
        return send_file(str(LOG_FILE), mimetype="text/plain", as_attachment=False)
    return "Aucun log disponible.", 404


# ── SocketIO events ───────────────────────────────────────────────────────────



def _get_game_folders():
    import os
    base = os.path.expanduser("~/NicLink/games")
    folders = []
    try:
        for mode in sorted(os.listdir(base)):
            mode_path = os.path.join(base, mode)
            if not os.path.isdir(mode_path) or mode in ("tmp", "externe"):
                continue
            for game_type in sorted(os.listdir(mode_path)):
                type_path = os.path.join(mode_path, game_type)
                if os.path.isdir(type_path):
                    folders.append({"mode": mode, "type": game_type})
    except Exception as e:
        print(f"[WEB] Erreur listage dossiers: {e}")
    return folders

@socketio.on("connect")
def on_connect():
    global _disconnect_timer
    # Annuler le timer de déconnexion si le navigateur revient
    if _disconnect_timer and _disconnect_timer.is_alive():
        _disconnect_timer.cancel()
        _disconnect_timer = None
    print("[WEB] Navigateur connecté")
    emit("status", {"message": "Connecté au serveur NicLink"})
    emit("app_state", {"state": _app_state})
    emit("game_folders", {"folders": _get_game_folders()})
    # Renvoyer le statut échiquier au navigateur qui arrive/rafraîchit
    if _board_status == "ok":
        emit("board_ok", {})
    elif _board_status == "error":
        emit("board_error", {"message": _board_error_message})
    # Renvoyer l'état courant au navigateur qui arrive/rafraîchit
    if _game_state.get("fen"):
        emit("init",  _game_state.get("init", {}))
        if _game_state.get("history"):
            emit("history", {"moves": _game_state["history"]})
        if _game_state.get("move"):
            emit("move",  _game_state["move"])
        if _game_state.get("turn"):
            emit("turn",  _game_state["turn"])
        if _game_state.get("feedback"):
            emit("feedback", _game_state["feedback"])


# Délai avant fermeture après déconnexion (secondes)
_DISCONNECT_TIMEOUT = 5.0
_disconnect_timer: threading.Timer = None

@socketio.on("disconnect")
def on_disconnect():
    global _disconnect_timer
    print("[WEB] Navigateur déconnecté")
    # Annuler le timer précédent si existe
    if _disconnect_timer and _disconnect_timer.is_alive():
        _disconnect_timer.cancel()
    # Lancer un timer — si pas de reconnexion dans le délai, quitter
    def _shutdown():
        print("[WEB] Aucune reconnexion — fermeture du programme.")
        import os, signal
        os.kill(os.getpid(), signal.SIGINT)
    _disconnect_timer = threading.Timer(_DISCONNECT_TIMEOUT, _shutdown)
    _disconnect_timer.daemon = True
    _disconnect_timer.start()


@socketio.on("action")
def on_action(data):
    """Reçoit une action du navigateur et la route selon l état."""
    print(f"[WEB] Action reçue : {data}")
    atype = data.get("type", "")
    # Retour menu — traité ici directement pour playing et game_over
    if atype == "back_menu":
        set_app_state("menu")
        action_queue.put(data)  # aussi dans la queue pour que Python sorte de sa boucle
        return
    if _app_state in ("playing", "connecting", "game_over", "paused", "labo", "exercice_running"):
        action_queue.put(data)
    else:
        # menu, config, exercices, exercice_running → boucle principale
        menu_queue.put(data)

@socketio.on("save_pgn_externe")
def on_save_pgn_externe(data):
    from nicsoft.game.pgn_manager import build_final_path
    white     = data.get("white", "Blanc")
    black     = data.get("black", "Noir")
    result    = data.get("result", "*")
    moves_pgn = data.get("moves_pgn", "")
    save_type = data.get("save_type", "sf-pedagogique")
    # save_type = "Stockfish-Pedagogique" ou "Humain-Club" etc.
    parts = save_type.split("-", 1)
    mode_dir  = parts[0] if len(parts) == 2 else "Stockfish"
    type_dir  = parts[1] if len(parts) == 2 else "Pedagogique"
    final_path = build_final_path(mode_dir, type_dir, white, black)
    pgn_content = f'[White "{white}"]\n[Black "{black}"]\n[Result "{result}"]\n\n{moves_pgn}\n'
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(pgn_content)
    print(f"[WEB] PGN externe sauvegardé : {final_path}")
    socketio.emit("pgn_sauvegarde", {"path": final_path})

@socketio.on("analyser_pgn")
def on_analyser_pgn(data):
    """Reçoit une liste de coups UCI et les analyse via EngineManager."""
    import threading, json, pathlib
    from nicsoft.game.engine_manager import EngineManager, find_stockfish

    print(f"[WEB] analyser_pgn reçu: {len(data.get('moves', []))} coups")
    moves_uci  = data.get("moves", [])
    engine_elo = data.get("engine_elo", 1500)

    # Lire le chemin moteur depuis config.json
    cfg_path = pathlib.Path.home() / "NicLink" / "data" / "config.json"
    engine_path = ""
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_path = cfg.get("engine_path", "")
            engine_elo  = cfg.get("engine_elo", engine_elo)
        except Exception:
            pass
    if not engine_path:
        engine_path = find_stockfish() or "stockfish"

    def run():
        total = len(moves_uci)
        manager = None
        try:
            manager = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=True)
            seq_moves = data.get("seq_moves", 3)
            def callback(idx, total, res):
                print(f"[ANALYSE] coup {idx+1}/{total}: {res['qualite']}")
                socketio.emit("analyse_coup", {
                    "index":           idx,
                    "total":           total,
                    "qualite":         res["qualite"],
                    "delta_cp":        res["delta_cp"],
                    "best_move":       res["best_move"],
                    "punishment_line": res.get("punishment_line", []),
                    "fen_avant_coup":  res.get("fen_avant_coup", ""),
                })
            manager.analyser_partie(moves_uci, callback=callback, seq_moves=seq_moves)
            socketio.emit("analyse_terminee", {"total": total})
        except Exception as e:
            print(f"[ANALYSE] Erreur : {e}")
            logger.error(f"Erreur analyse PGN: {e}", exc_info=True)
            socketio.emit("analyse_terminee", {"total": total, "error": str(e)})
        finally:
            if manager:
                manager.quit()

    threading.Thread(target=run, daemon=True).start()

# ── Thread de dispatch des événements ────────────────────────────────────────

def _dispatch_loop():
    """
    Tourne en arrière-plan.
    Lit les événements de event_queue et les envoie au navigateur.
    """
    while True:
        try:
            event = event_queue.get(timeout=0.1)
            # Ne pas dispatcher un game_over avec skip=True (back_menu)
            if event["type"] == "game_over" and event["data"].get("skip"):
                continue
            if event["type"] not in ("board_fen_update", "labo_position"):
                print(f"[DISPATCH] {event['type']}")
            socketio.emit(event["type"], event["data"])
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[WEB] Erreur dispatch: {e}")
            logger.error(f"Erreur dispatch event {event.get('type','?')}: {e}", exc_info=True)


def send_event(event_type: str, data: dict) -> None:
    """
    API publique — appelée par le module pédagogique pour envoyer
    un événement au navigateur.
    """
    global _board_status, _board_error_message
    # Mettre à jour le statut échiquier
    if event_type == "board_ok":
        _board_status = "ok"
        _board_error_message = ""
    elif event_type == "board_error":
        _board_status = "error"
        _board_error_message = data.get("message", "")
    # Mettre à jour l'état courant
    if event_type == "init":
        _game_state["fen"] = data.get("fen")
        _game_state["init"] = data
        _game_state["history"] = []
        _game_state["history_fen"] = ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"]
        _game_state.pop("feedback", None)
    elif event_type == "move":
        _game_state["fen"] = data.get("fen")
        _game_state["move"] = data
        _game_state.pop("feedback", None)
        _game_state.setdefault("history", []).append(data)
        _game_state.setdefault("history_fen", ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"]).append(data.get("fen", ""))
    elif event_type == "undo_move":
        # Retirer le dernier coup de l'historique
        if _game_state.get("history"):
            _game_state["history"].pop()
        if _game_state.get("history_fen") and len(_game_state["history_fen"]) > 1:
            _game_state["history_fen"].pop()
        _game_state["fen"] = data.get("fen", _game_state.get("fen"))
    elif event_type == "turn":
        _game_state["turn"] = data
    elif event_type == "qualite":
        # Mettre à jour la qualité du dernier coup dans l historique
        hist = _game_state.get("history", [])
        if hist and hist[-1].get("san") == data.get("san"):
            hist[-1]["qualite"] = data.get("qualite")
    elif event_type == "feedback":
        _game_state["feedback"] = data
    elif event_type == "game_over":
        _game_state.pop("feedback", None)
    event_queue.put({"type": event_type, "data": data})


def get_action(timeout: float = 0.0):
    """
    API publique — appelée par le module pédagogique pour récupérer
    une action du navigateur. Retourne None si aucune action.
    """
    try:
        return action_queue.get(timeout=timeout)
    except queue.Empty:
        return None


def set_app_state(state: str, data: dict = None) -> None:
    """Change l état de l application et notifie le navigateur."""
    global _app_state
    # Ne pas écraser "menu" avec "game_over" si skip=True (back_menu)
    if state == "game_over" and data and data.get("skip") and _app_state == "menu":
        socketio.emit("app_state", {"state": state, **(data or {})})
        return
    _app_state = state
    payload = {"state": state}
    if data:
        payload.update(data)
    socketio.emit("app_state", payload)
    # Au retour menu, renvoyer le statut échiquier pour réactiver les boutons
    if state == "menu":
        if _board_status == "ok":
            socketio.emit("board_ok", {})
        elif _board_status == "error":
            socketio.emit("board_error", {"message": _board_error_message})


def get_menu_action(timeout: float = 1.0):
    """Récupère une action du menu. Retourne None si timeout."""
    try:
        return menu_queue.get(timeout=timeout)
    except queue.Empty:
        return None


def start_server(host="127.0.0.1", port=5000, debug=False) -> threading.Thread:
    """
    Démarre le serveur Flask-SocketIO dans un thread daemon.
    Retourne le thread pour référence.
    """
    dispatch_thread = threading.Thread(target=_dispatch_loop, daemon=True)
    dispatch_thread.start()

    server_thread = threading.Thread(
        target=lambda: socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True),
        daemon=True,
    )
    server_thread.start()
    print(f"[WEB] Serveur démarré sur http://{host}:{port}")
    return server_thread
