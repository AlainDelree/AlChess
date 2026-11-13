"""
nicsoft/web/server.py — Serveur Flask-SocketIO pour l'interface pédagogique NicLink.

Ce serveur tourne en parallèle du module play_pedagogique.
Il reçoit les événements de jeu via une queue Python et les transmet
au navigateur via SocketIO. Les actions du navigateur remontent
via SocketIO à Python.
"""

import hashlib
import logging
import os
import pathlib
import queue
import re
import secrets
import shutil
import sys
import threading
from nicsoft.config import APP_DIR, DATA_DIR, ENGINES_DIR, GAMES_DIR, LOGS_DIR
from nicsoft.modes.opening_explorer.tts_engine import stop_speaking
from nicsoft.modes.opening_explorer import tts_engine
from flask import Flask, render_template, send_file, abort, request
from flask_socketio import SocketIO, emit

logger = logging.getLogger("niclink.server")
LOG_FILE = LOGS_DIR / "niclink.log"

# Fichier sentinelle : sa presence desactive la verification des mises a
# jour automatiques faite par 2-Lancer_AlChess.bat au demarrage (issue #91).
NO_UPDATE_FILE = APP_DIR / "no-update.txt"

# Mode debug — activé via variable d'environnement NICLINK_LOG=DEBUG
DEBUG_MODE = os.environ.get("NICLINK_LOG", "").upper() == "DEBUG"

# Mode test — activé via variable d'environnement NICLINK_TEST=random
TEST_MODE = os.environ.get("NICLINK_TEST", "")

# Clé secrète Flask — générée aléatoirement au premier lancement puis
# persistée dans data/ (hors dépôt, voir .gitignore) pour rester stable
# entre les redémarrages (issue #202).
SECRET_KEY_FILE = DATA_DIR / "secret_key.txt"


def _get_or_create_secret_key() -> str:
    try:
        if SECRET_KEY_FILE.exists():
            key = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if key:
                return key
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        SECRET_KEY_FILE.write_text(key, encoding="utf-8")
        return key
    except OSError as e:
        logger.warning(f"[WEB] Impossible de lire/écrire {SECRET_KEY_FILE} : {e}. Clé générée en mémoire uniquement.")
        return secrets.token_hex(32)


# Origines autorisées pour les connexions SocketIO — le serveur ne sert
# l'interface qu'en local (127.0.0.1/localhost), donc pas besoin d'ouvrir le
# CORS à "*" (issue #202). Le port est choisi dynamiquement au démarrage
# (voir alchess._find_free_port), donc validé par motif plutôt que par une
# liste figée sur 5000 — sinon toute connexion SocketIO est rejetée dès que
# le port par défaut est occupé (issue #205).
_ALLOWED_ORIGIN_RE = re.compile(r"^https?://(127\.0\.0\.1|localhost):\d+$")


def _is_allowed_origin(origin: str) -> bool:
    return bool(origin) and bool(_ALLOWED_ORIGIN_RE.match(origin))


# Port d'écoute réel du serveur — fixé par start_server()/set_server_port()
# (le port est choisi dynamiquement, voir alchess._find_free_port). Utilisé
# pour valider l'en-tête Host des routes HTTP sensibles : un Host différent
# de 127.0.0.1/localhost sur ce port indique une attaque par réaffectation de
# nom de domaine (DNS rebinding) — un domaine public pointé vers 127.0.0.1
# forcerait le navigateur à envoyer ce domaine-là en Host (issue #304).
_server_port: int | None = None


def set_server_port(port: int) -> None:
    """API publique — fixe le port utilisé par _is_allowed_host(). Appelée par
    start_server() ; exposée séparément pour les tests (pas de socket réel)."""
    global _server_port
    _server_port = port


def _is_allowed_host(host: str) -> bool:
    return bool(host) and _server_port is not None and host in (
        f"127.0.0.1:{_server_port}", f"localhost:{_server_port}",
    )


def _require_allowed_origin() -> None:
    """Pour les routes POST à effet de bord — Origin absent ou non autorisé → 403."""
    if not _is_allowed_origin(request.headers.get("Origin", "")):
        abort(403)


def _require_allowed_host() -> None:
    """Pour les routes de lecture sensibles et les routes à effet de bord —
    Host différent de 127.0.0.1/localhost sur le port du serveur → 403."""
    if not _is_allowed_host(request.headers.get("Host", "")):
        abort(403)


app = Flask(__name__)
app.config["SECRET_KEY"] = _get_or_create_secret_key()
socketio = SocketIO(app, cors_allowed_origins=_is_allowed_origin, async_mode="threading", )

# Queue pour recevoir les événements du module Python
event_queue: queue.Queue = queue.Queue()

# Queue pour recevoir les actions du navigateur vers Python
action_queue: queue.Queue = queue.Queue()

# Dernier état connu — renvoyé au navigateur qui se (re)connecte
_game_state: dict = {}

# Protège les séquences composées sur _game_state : send_event() y fait des
# lecture-modification-écriture (setdefault+append, pop conditionnel,
# lecture de hist[-1] avant mutation dans la branche "qualite") et
# on_connect() lit plusieurs clés (fen/history/move/turn/feedback) qui
# doivent rester cohérentes entre elles à un instant donné. Ce verrou
# n'englobe jamais un emit()/put() — uniquement la mutation du dict.
# Note : _game_state est aussi importé et lu directement (par référence,
# hors verrou) par human.py et pedagogique.py pour des lectures multi-clés
# (history + history_fen) — voir get_history() ci-dessous, qui protège ces
# accès sous _game_state_lock. Les écritures directes (human.py,
# game_manager.py) passent par set_history().
_game_state_lock = threading.RLock()

# État de l application : menu / config / playing / game_over
# Simple chaîne remplacée par affectation atomique (GIL) ; aucune séquence
# composée locale à server.py ne la manipule (le "prev_state = _app_state"
# de on_action() est un instantané local volontaire, pas une race) — pas de
# verrou nécessaire ici.
_app_state: str = "menu"

# Queue pour les actions du menu (choix mode, config joueur, etc.)
menu_queue: queue.Queue = queue.Queue()

# Statut de la connexion échiquier — renvoyé au navigateur qui se connecte
# None = pas encore vérifié, "ok" = connecté, "error" = non détecté,
# "reconnecting" = périphérique présent sur le bus USB mais module de
# lecture perdu, reconnexion automatique en cours (issue #314, point 4).
_board_status: str | None = None
_board_error_message: str = ""

# Protège le couple (_board_status, _board_error_message) : toujours écrits
# ensemble dans send_event() et lus ensemble dans on_connect() et
# set_app_state() — sans verrou, un lecteur pourrait observer un statut
# "error" combiné à l'ancien message (ou l'inverse).
_board_status_lock = threading.Lock()

# Référence vers le VirtualBoard actif — None si mode physique
# Assignée par __main__.py via set_virtual_board() avant le lancement d'une partie
# Simple pointeur (affectation atomique sous le GIL) : on_virtual_move() le
# lit une seule fois dans une variable locale avant usage pour éviter un
# TOCTOU si set_virtual_board(None) survient entre la vérification et
# l'appel post_move() — pas besoin de verrou pour ça.
_virtual_board_ref = None

# Disponibilité des moteurs — mise en cache pour éviter les vérifications
# répétées à chaque reconnexion du navigateur. None = pas encore vérifié.
# Lecture-teste-calcule-écrit non protégée, volontairement : la
# computation (vérif fichier / handshake UCI) est idempotente et sans
# effet de bord partagé, donc une course au premier appel ne fait au pire
# que la recalculer deux fois — jamais d'état incohérent. Un verrou
# obligerait à le tenir pendant l'appel bloquant (handshake UCI/subprocess),
# ce qui est proscrit ici.
_stockfish_available_cache: bool | None = None
_maia_available_cache: bool | None = None
_rodent_available_cache: bool | None = None

def _get_stockfish_available() -> bool:
    """Retourne (et mémorise) si Stockfish est présent."""
    global _stockfish_available_cache
    if _stockfish_available_cache is None:
        try:
            from nicsoft.engine.engine_manager import stockfish_available
            _stockfish_available_cache = stockfish_available()
        except Exception as e:
            logger.warning(f"[WEB] Vérification disponibilité Stockfish échouée : {e}")
            _stockfish_available_cache = False
    return _stockfish_available_cache


def _get_maia_available() -> bool:
    """Retourne (et mémorise) si Maia (lc0 + poids) est disponible."""
    global _maia_available_cache
    if _maia_available_cache is None:
        try:
            from nicsoft.engine.engine_manager import maia_available
            _maia_available_cache = maia_available()
        except Exception as e:
            logger.warning(f"[WEB] Vérification disponibilité Maia échouée : {e}")
            _maia_available_cache = False
    return _maia_available_cache


def _get_rodent_available() -> bool:
    """Retourne (et mémorise) si Rodent IV répond au handshake UCI."""
    global _rodent_available_cache
    if _rodent_available_cache is None:
        try:
            from nicsoft.engine.engine_manager import rodent_available
            _rodent_available_cache = rodent_available()
        except Exception as e:
            logger.warning(f"[WEB] Vérification disponibilité Rodent échouée : {e}")
            _rodent_available_cache = False
    return _rodent_available_cache


# URL des binaires Rodent IV Windows sur GitHub — utilisée par download_rodent
# quand SyncGitRepo n'a pas récupéré ces fichiers (installation NSIS standalone).
_RODENT_WIN_BASE_URL = "https://raw.githubusercontent.com/AlainDelree/AlChess/master/engines/rodent-iv-win/"
_RODENT_WIN_FILES = ["rodent-iv-x64.exe", "msvcr120.dll", "msvcp120.dll"]

# Délai d'attente par requête réseau (secondes) — évite de figer le thread de
# téléchargement si le serveur GitHub est injoignable (issue #256, EXP-013).
_RODENT_WIN_DOWNLOAD_TIMEOUT = 15

# Empreintes SHA-256 de référence pour chaque binaire Rodent IV Windows.
# Source : fichiers identiques déjà versionnés dans ce dépôt
# (engines/rodent-iv-win/), qui sont exactement la même release que celle
# re-téléchargée ici pour les installations NSIS standalone n'embarquant pas
# ces fichiers — calculées localement, jamais dérivées d'un téléchargement
# (issue #256, SEC-022).
_RODENT_WIN_SHA256 = {
    "rodent-iv-x64.exe": "39c879b2dfdaf0252e94db547397d95422fee76ea8bafa584bfdc03e4d648de5",
    "msvcr120.dll": "ad32240bb1de55c3f5fcac8789f583a17057f9d14914c538c2a7a5ad346b341c",
    "msvcp120.dll": "81fbc2824e73f0d101d91854694a52e79db0ffaadbb2a10deaaf47b3b7f9b2b0",
}


def _telecharger_fichier_rodent(url: str, dest_path: pathlib.Path) -> None:
    """Télécharge un fichier avec délai d'attente, vérifie son empreinte SHA-256
    contre la référence connue, et supprime le fichier en cas d'écart.

    `dest_path` doit toujours pointer dans le dossier temporaire de
    téléchargement (jamais dans le dossier définitif du moteur) : l'ouverture
    en écriture ci-dessous tronque le fichier dès l'appel, et un fichier
    tronqué ne doit jamais apparaître là où une installation existante
    fonctionne déjà (SEC-025) — c'est `_installer_rodent_depuis_temp` qui se
    charge de la mise en place finale, une fois tous les fichiers vérifiés.
    """
    import urllib.request

    attendu = _RODENT_WIN_SHA256.get(dest_path.name)
    if attendu is None:
        raise ValueError(f"Aucune empreinte de référence connue pour {dest_path.name}")

    if not url.startswith("https://"):
        raise ValueError(f"Adresse de téléchargement refusée (https:// requis) : {url}")

    hasher = hashlib.sha256()
    with (
        # URL construite depuis une base https constante, vérifiée ci-dessus
        urllib.request.urlopen(url, timeout=_RODENT_WIN_DOWNLOAD_TIMEOUT) as response,  # noqa: S310  # nosec B310
        open(dest_path, "wb") as out,
    ):
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
            out.write(chunk)

    obtenu = hasher.hexdigest()
    if obtenu != attendu:
        dest_path.unlink(missing_ok=True)
        raise ValueError(f"Empreinte invalide pour {dest_path.name} (intégrité compromise)")


def _nettoyer_dossier_temp_rodent(tmp_dir: pathlib.Path) -> None:
    """Supprime le dossier temporaire de téléchargement Rodent s'il existe —
    que ce soit un résidu d'un arrêt brutal (crash, kill) ou le nettoyage de
    fin de tentative. Sans effet si absent."""
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _installer_rodent_depuis_temp(tmp_dir: pathlib.Path, dest_dir: pathlib.Path) -> None:
    """Met en place atomiquement (tout-ou-rien) les fichiers déjà vérifiés de
    `tmp_dir` vers `dest_dir`, sur le même volume (les deux sont dans
    ENGINES_DIR). Si la mise en place échoue en cours de route (dossier
    verrouillé par le moteur en cours d'exécution, disque plein...), restaure
    `dest_dir` dans l'état exact où il était avant l'appel et propage
    l'erreur : une installation existante qui fonctionne n'est jamais
    perdue (SEC-025).
    """
    backup_dir = dest_dir.parent / (dest_dir.name + ".bak")
    shutil.rmtree(backup_dir, ignore_errors=True)
    dest_existait = dest_dir.exists()
    try:
        if dest_existait:
            os.replace(dest_dir, backup_dir)
        os.replace(tmp_dir, dest_dir)
    except OSError:
        if dest_existait and not dest_dir.exists() and backup_dir.exists():
            os.replace(backup_dir, dest_dir)
        raise
    else:
        if dest_existait:
            shutil.rmtree(backup_dir, ignore_errors=True)


def _telecharger_et_installer_rodent(dest_dir: pathlib.Path, tmp_dir: pathlib.Path, on_progress=None) -> None:
    """Télécharge les trois binaires Rodent IV Windows dans `tmp_dir`, vérifie
    chacun, puis les met en place tout-ou-rien dans `dest_dir` (voir
    `_installer_rodent_depuis_temp`). Nettoie `tmp_dir` avant de commencer
    (résidu d'un arrêt brutal précédent) et après, que la tentative réussisse
    ou échoue — isolée du handler SocketIO pour pouvoir être testée
    directement, sans dépendre de la plateforme (issue #286).

    `on_progress(index, total, filename)`, si fourni, est appelé juste avant
    chaque téléchargement.
    """
    _nettoyer_dossier_temp_rodent(tmp_dir)
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        total = len(_RODENT_WIN_FILES)
        for index, filename in enumerate(_RODENT_WIN_FILES, start=1):
            if on_progress is not None:
                on_progress(index, total, filename)
            _telecharger_fichier_rodent(_RODENT_WIN_BASE_URL + filename, tmp_dir / filename)
        _installer_rodent_depuis_temp(tmp_dir, dest_dir)
    finally:
        _nettoyer_dossier_temp_rodent(tmp_dir)


@socketio.on("download_rodent")
def on_download_rodent(_data):
    """Télécharge les binaires Rodent IV Windows depuis GitHub (issue #131).

    SyncGitRepo ne récupère pas les binaires sur une installation NSIS
    standalone ; ce handler les télécharge directement depuis la branche
    master du dépôt public. Chaque requête est bornée dans le temps et
    chaque fichier est vérifié par empreinte SHA-256 (issue #256).

    Installation tout-ou-rien (issue #286, SEC-025) : les trois fichiers sont
    d'abord téléchargés et vérifiés dans un dossier temporaire à côté du
    dossier définitif (même volume), et ne sont mis en place dans
    ENGINES_DIR/rodent-iv-win/ qu'une fois les trois conformes. Le moindre
    échec (réseau, délai dépassé, empreinte invalide, disque plein, dossier
    verrouillé) supprime le dossier temporaire et laisse le dossier définitif
    strictement inchangé — une installation existante qui fonctionne n'est
    jamais tronquée ni détruite par une tentative ratée.
    """
    if sys.platform != "win32":
        emit("rodent_download_result", {"ok": False, "error": "Téléchargement disponible uniquement sous Windows"})
        return

    def run():
        global _rodent_available_cache
        dest_dir = ENGINES_DIR / "rodent-iv-win"
        tmp_dir = ENGINES_DIR / "rodent-iv-win.tmp"
        try:
            _telecharger_et_installer_rodent(
                dest_dir, tmp_dir,
                on_progress=lambda index, total, filename: socketio.emit(
                    "rodent_download_progress", {"file": filename, "index": index, "total": total},
                ),
            )
            _rodent_available_cache = None
            socketio.emit("rodent_download_result", {"ok": True})
            socketio.emit("rodent_status", {"available": _get_rodent_available(), "downloadable": True})
        except Exception as e:
            logger.error(f"[WEB] Téléchargement Rodent IV échoué : {e}")
            socketio.emit("rodent_download_result", {"ok": False, "error": str(e)})

    threading.Thread(target=run, daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", test_mode=TEST_MODE, autoupdate_active=not NO_UPDATE_FILE.exists())

@app.route("/logs")
def get_logs():
    """Sert le fichier de log pour téléchargement/consultation."""
    _require_allowed_host()
    if LOG_FILE.exists():
        return send_file(str(LOG_FILE), mimetype="text/plain", as_attachment=False)
    return "Aucun log disponible.", 404

@app.route("/debug/mark")
def debug_mark():
    """Insère un marqueur dans les logs — mode debug uniquement."""
    _require_allowed_host()
    if not DEBUG_MODE:
        abort(403)
    from datetime import datetime
    marker = f"\n{'='*60}\n=== DEBUG MARK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n{'='*60}\n"
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(marker)
        logger.info(marker)
        return "Marqueur ajouté.", 200
    except Exception as e:
        return f"Erreur : {e}", 500

@app.route("/debug/mode")
def debug_mode_status():
    """Retourne si le mode debug est actif — utilisé par le JS au démarrage."""
    _require_allowed_host()
    from flask import jsonify
    return jsonify({"debug": DEBUG_MODE})

@app.route("/instance_status")
def instance_status():
    """Statut minimal de cette instance — interrogé en local par une
    nouvelle instance qui démarre (issue #320), pour décider si une partie
    est en cours ici avant de la remplacer. Aucun secret exposé."""
    _require_allowed_host()
    from flask import jsonify
    return jsonify({"pid": os.getpid(), "port": _server_port, "state": _app_state})

@app.route("/toggle-autoupdate", methods=["POST"])
def toggle_autoupdate():
    """Active/désactive les mises à jour automatiques du launcher (issue #91).

    Bascule via la présence de NO_UPDATE_FILE à la racine du projet,
    lu par 2-Lancer_AlChess.bat au démarrage.
    """
    _require_allowed_origin()
    _require_allowed_host()
    from flask import jsonify
    if NO_UPDATE_FILE.exists():
        NO_UPDATE_FILE.unlink()
        active = True
    else:
        NO_UPDATE_FILE.write_text("Presence de ce fichier = mises a jour automatiques desactivees.\n", encoding="utf-8")
        active = False
    return jsonify({"active": active})

TEST_CONFIG_DIR = LOGS_DIR / "Test config"

@app.route("/test/save-config", methods=["POST"])
def test_save_config():
    """Sauvegarde la config de test courante dans logs/Test config/test_config_YYYY-MM-DD.log."""
    _require_allowed_origin()
    _require_allowed_host()
    from flask import request, jsonify
    from datetime import datetime
    if TEST_MODE != "random":
        return jsonify({"ok": False, "error": "test mode inactif"}), 403
    data = request.get_json(silent=True) or {}
    TEST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    log_file = TEST_CONFIG_DIR / f"test_config_{now.strftime('%Y-%m-%d')}.log"
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"\n{'='*50}", f"Config test — {ts}", f"{'='*50}"]
    for section, fields in data.items():
        lines.append(f"\n[{section}]")
        for k, v in fields.items():
            lines.append(f"  {k}: {v}")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return jsonify({"ok": True})


# ── SocketIO events ───────────────────────────────────────────────────────────



def _get_game_folders():
    import os
    base = str(GAMES_DIR)
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
        logger.error(f"[WEB] Erreur listage dossiers: {e}")
    return folders

@socketio.on("connect")
def on_connect():
    global _disconnect_timer
    # Annuler le timer de déconnexion si le navigateur revient
    with _disconnect_timer_lock:
        if _disconnect_timer and _disconnect_timer.is_alive():
            _disconnect_timer.cancel()
            _disconnect_timer = None
    logger.info("[WEB] Navigateur connecté")
    emit("status", {"message": "Connecté au serveur NicLink", "message_key": "status.connecte"})
    emit("app_state", {"state": _app_state})
    emit("game_folders", {"folders": _get_game_folders()})
    # Disponibilité des moteurs → l'UI grise ceux qui ne sont pas disponibles
    emit("stockfish_status", {"available": _get_stockfish_available()})
    emit("maia_status", {"available": _get_maia_available()})
    emit("rodent_status", {"available": _get_rodent_available(), "downloadable": sys.platform == "win32"})
    # Renvoyer le statut échiquier au navigateur qui arrive/rafraîchit —
    # instantané sous verrou pour ne jamais associer un statut à l'ancien
    # message (ou l'inverse).
    with _board_status_lock:
        board_status, board_error_message = _board_status, _board_error_message
    if board_status == "ok":
        emit("board_ok", {})
    elif board_status == "error":
        emit("board_error", {"message": board_error_message})
    elif board_status == "reconnecting":
        emit("board_reconnecting", {"message": board_error_message})
    # Renvoyer l'état courant au navigateur qui arrive/rafraîchit —
    # instantané sous verrou pour que fen/history/move/turn/feedback
    # restent cohérents entre eux même si send_event() mute _game_state
    # en parallèle depuis un autre thread.
    with _game_state_lock:
        fen      = _game_state.get("fen")
        init     = _game_state.get("init", {})
        history  = _game_state.get("history")
        move     = _game_state.get("move")
        turn     = _game_state.get("turn")
        feedback = _game_state.get("feedback")
    if fen:
        emit("init", init)
        if history:
            emit("history", {"moves": history})
        if move:
            emit("move", move)
        if turn:
            emit("turn", turn)
        if feedback:
            emit("feedback", feedback)


# Délai avant fermeture après déconnexion (secondes)
_DISCONNECT_TIMEOUT = 5.0
_disconnect_timer: threading.Timer = None

# Protège _disconnect_timer : on_connect() et on_disconnect() font tous les
# deux un cycle vérifier-vivant → annuler → (re)créer/remettre à None ; un
# enchaînement rapide déconnexion/reconnexion (ex. rafraîchissement de page)
# peut faire tourner les deux handlers sur des threads différents en même
# temps, ce qui pourrait laisser courir un timer qu'on croyait annulé.
# Timer.cancel()/.start() ne bloquent pas — tenir ce verrou pendant l'appel
# est donc sans risque de contention.
_disconnect_timer_lock = threading.Lock()

@socketio.on("disconnect")
def on_disconnect():
    global _disconnect_timer
    logger.info("[WEB] Navigateur déconnecté")
    with _disconnect_timer_lock:
        # Annuler le timer précédent si existe
        if _disconnect_timer and _disconnect_timer.is_alive():
            _disconnect_timer.cancel()
        # Lancer un timer — si pas de reconnexion dans le délai, quitter
        def _shutdown():
            logger.info("[WEB] Aucune reconnexion — fermeture du programme.")
            import os
            os._exit(0)
        _disconnect_timer = threading.Timer(_DISCONNECT_TIMEOUT, _shutdown)
        _disconnect_timer.daemon = True
        _disconnect_timer.start()


def _reconnect_board() -> None:
    """
    Tente une reconnexion USB au plateau physique, appelée en arrière-plan
    depuis on_action (action "reconnect_board" — bouton "Connecter").

    Si une partie/session a une instance NicLinkManager physique active
    (game_manager._nl_inst_ref), on la réutilise : reconnexion + redémarrage
    de son thread fen_reader, pour reprendre exactement là où elle en était.
    Sinon (menu, aucune session), simple vérification de connexion comme
    au démarrage. Émet board_ok en cas de succès, board_error sinon.
    """
    try:
        from nicsoft.core.game_manager import get_nl_inst_ref
        nl_inst = get_nl_inst_ref()
        if nl_inst is not None and hasattr(nl_inst, "nl_interface"):
            nl_inst.connect()
            nl_inst._start_fen_reader()
        else:
            from nicsoft.core.board_adapter import create_board
            nl = create_board(virtual=False, logger_name="NicLink_reconnect")
            try:
                nl._fen_reader_stop.set()
            except Exception as e:
                logger.debug(f"[WEB] Arrêt du thread fen_reader (connexion de secours) échoué : {e}")
        send_event("board_ok", {})
    except Exception as e:
        logger.info(f"[WEB] Reconnexion échiquier échouée : {e}")
        send_event("board_error", {
            "message": "Échiquier non détecté — vérifiez l'USB et allumez le plateau.",
        })


@socketio.on("action")
def on_action(data):
    """Reçoit une action du navigateur et la route selon l état."""
    logger.debug(f"[WEB] Action reçue : {data}")
    atype = data.get("type", "")
    # Retour menu — traité ici directement pour playing et game_over
    if atype == "back_menu":
        prev_state = _app_state  # sauvegarder AVANT de changer
        set_app_state("menu")
        if prev_state == "opening_explorer":
            from nicsoft.core.game_manager import explorer_cleanup
            explorer_cleanup()
        # Mettre dans action_queue seulement si un thread actif écoute
        if prev_state in ("playing", "connecting", "game_over", "paused", "labo",
                          "exercice_running", "retrans_playing"):
            action_queue.put(data)
        return
    # Retour sélection exercices — même pattern que back_menu
    if atype == "exercice_back" and _app_state == "exercice_running":
        set_app_state("exercices")
        action_queue.put(data)  # arrêter le thread exercice proprement
        return
    # Reconnexion échiquier — traitée directement, quel que soit l état
    # (menu, ou en cours de session si le plateau a été débranché).
    if atype == "reconnect_board":
        threading.Thread(target=_reconnect_board, daemon=True).start()
        return
    if _app_state in ("playing", "connecting", "game_over", "paused", "labo", "exercice_running", "retrans_playing"):
        action_queue.put(data)
    else:
        # menu, config, exercices, exercice_running → boucle principale
        menu_queue.put(data)

@socketio.on("virtual_move")
def on_virtual_move(data):
    """
    Reçoit un coup du navigateur en mode virtuel.
    data = {"uci": "e2e4"}
    Transmis au VirtualBoard actif via post_move().
    """
    uci = data.get("uci", "")
    if not uci:
        logger.warning("virtual_move reçu sans UCI")
        return
    # Une seule lecture du global dans une variable locale : évite un TOCTOU
    # si set_virtual_board(None) survient entre la vérification et l'appel.
    vb = _virtual_board_ref
    if vb is None:
        logger.warning("virtual_move reçu mais aucun VirtualBoard actif")
        return
    logger.debug("virtual_move reçu : %s", uci)
    vb.post_move(uci)


def set_virtual_board(vb) -> None:
    """
    API publique — appelée par __main__.py pour enregistrer le VirtualBoard actif.
    Passer None pour désactiver (retour au mode physique ou fin de partie).
    """
    global _virtual_board_ref
    _virtual_board_ref = vb


@socketio.on("save_pgn_externe")
def on_save_pgn_externe(data):
    from nicsoft.engine.pgn_manager import build_final_path
    white     = data.get("white", "Blanc")
    black     = data.get("black", "Noir")
    result    = data.get("result", "*")
    moves_pgn = data.get("moves_pgn", "")
    save_type = data.get("save_type", "Stockfish-Pedagogical")
    # save_type = "Stockfish-Pedagogical" ou "Human-Club" etc.
    parts = save_type.split("-", 1)
    mode_dir  = parts[0] if len(parts) == 2 else "Stockfish"
    type_dir  = parts[1] if len(parts) == 2 else "Pedagogical"
    final_path = build_final_path(mode_dir, type_dir, white, black)
    pgn_content = f'[White "{white}"]\n[Black "{black}"]\n[Result "{result}"]\n\n{moves_pgn}\n'
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(pgn_content)
    logger.info(f"[WEB] PGN externe sauvegardé : {final_path}")
    socketio.emit("pgn_sauvegarde", {"path": final_path})

@socketio.on("analyser_pgn")
def on_analyser_pgn(data):
    """Reçoit une liste de coups UCI et les analyse via EngineManager."""
    import threading, json, pathlib
    from nicsoft.engine.engine_manager import EngineManager, find_stockfish

    logger.info(f"[WEB] analyser_pgn reçu: {len(data.get('moves', []))} coups")
    moves_uci  = data.get("moves", [])
    engine_elo = data.get("engine_elo", 1500)

    # Lire le chemin moteur depuis config.json
    cfg_path = DATA_DIR / "config.json"
    engine_path = ""
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_path = cfg.get("engine_path", "")
            engine_elo  = cfg.get("engine_elo", engine_elo)
        except Exception as e:
            logger.debug(f"[WEB] Lecture config.json pour le chemin moteur échouée : {e}")
    if not engine_path:
        engine_path = find_stockfish() or "stockfish"

    def run():
        total = len(moves_uci)
        manager = None
        try:
            manager = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=True)
            seq_moves = data.get("seq_moves", 3)
            def callback(idx, total, res):
                logger.debug(f"[ANALYSE] coup {idx+1}/{total}: {res['qualite']}")
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
            logger.error(f"Erreur analyse PGN: {e}", exc_info=True)
            socketio.emit("analyse_terminee", {"total": total, "error": str(e)})
        finally:
            if manager:
                manager.quit()

    threading.Thread(target=run, daemon=True).start()

@socketio.on("outils_pgn_preview")
def on_outils_pgn_preview(data):
    """Aperçu d'un fichier PGN uploadé depuis le navigateur."""
    from nicsoft.modes.exercices.import_lignes import preview_from_web
    result = preview_from_web(data.get("name", "inconnu.pgn"), data.get("content", ""))
    emit("outils_pgn_preview_result", result)


@socketio.on("outils_pgn_import")
def on_outils_pgn_import(data):
    """Importe une liste de fichiers PGN uploadés depuis le navigateur."""
    from nicsoft.modes.exercices.import_lignes import import_from_web
    result = import_from_web(data.get("files", []))
    emit("outils_pgn_import_result", result)


@socketio.on("outils_wiki_update")
def on_outils_wiki_update(_data):
    """Télécharge et reconstruit eco_hierarchy.json depuis Wikipedia."""
    import threading
    from nicsoft.modes.exercices.download_eco_wiki import run_from_web

    def run():
        def progress(step, message, vars=None):
            event = {"step": step, "message": message, "message_key": f"outils.wiki.step.{step}"}
            if vars:
                event["vars"] = vars
            socketio.emit("outils_wiki_progress", event)
        result = run_from_web(progress)
        socketio.emit("outils_wiki_done", result)

    threading.Thread(target=run, daemon=True).start()
    emit("outils_wiki_progress", {"step": "start", "message": "Démarrage…", "message_key": "outils.wiki.step.start"})


@socketio.on("outils_eco_search")
def on_outils_eco_search(data):
    """Recherche dans les fichiers ECO Lichess."""
    from nicsoft.modes.exercices.eco_import import search_eco_from_web
    emit("outils_eco_search_result", search_eco_from_web(data))


@socketio.on("outils_eco_import")
def on_outils_eco_import(data):
    """Importe des entrées ECO sélectionnées dans le catalogue."""
    from nicsoft.modes.exercices.eco_import import import_eco_from_web
    emit("outils_eco_import_result", import_eco_from_web(data))


@socketio.on("outils_edit_list")
def on_outils_edit_list(_data):
    """Retourne toutes les ouvertures du catalogue."""
    from nicsoft.modes.exercices.edit_ouverture import list_from_web
    emit("outils_edit_list_result", {"ouvertures": list_from_web()})


@socketio.on("outils_edit_save")
def on_outils_edit_save(data):
    """Sauvegarde les modifications d'une ouverture."""
    from nicsoft.modes.exercices.edit_ouverture import save_from_web
    emit("outils_edit_save_result", save_from_web(data))


@socketio.on("outils_explore_list")
def on_outils_explore_list(_data):
    """Retourne la liste des livres Polyglot disponibles."""
    from nicsoft.modes.exercices.explore_book import list_books_for_web
    emit("outils_explore_list_result", {"books": list_books_for_web()})


@socketio.on("outils_explore_moves")
def on_outils_explore_moves(data):
    """Retourne position + coups disponibles dans un livre."""
    from nicsoft.modes.exercices.explore_book import get_moves_from_web
    emit("outils_explore_moves_result", get_moves_from_web(data))


@socketio.on("outils_add_verify")
def on_outils_add_verify(data):
    """Valide le formulaire d'ajout d'ouverture."""
    from nicsoft.modes.exercices.add_ouverture import verify_from_web
    emit("outils_add_verify_result", verify_from_web(data))


@socketio.on("outils_add_save")
def on_outils_add_save(data):
    """Enregistre une nouvelle ouverture dans le catalogue."""
    from nicsoft.modes.exercices.add_ouverture import save_from_web
    emit("outils_add_save_result", save_from_web(data))


@socketio.on("outils_san_to_uci")
def on_outils_san_to_uci(data):
    """Convertit une ligne PGN SAN → liste UCI."""
    import io as _io, sys as _sys
    import chess, chess.pgn
    pgn_text = data.get("pgn", "")
    _cap = _io.StringIO()
    _old = _sys.stderr
    _sys.stderr = _cap
    try:
        game = chess.pgn.read_game(_io.StringIO(pgn_text))
    finally:
        _sys.stderr = _old
    if game is None:
        emit("outils_san_to_uci_result", {"ok": False, "error": "PGN invalide"})
        return
    board = game.board()
    moves = []
    node = game
    while node.variations:
        node = node.variations[0]
        moves.append({"san": board.san(node.move), "uci": node.move.uci()})
        board.push(node.move)
    emit("outils_san_to_uci_result", {"ok": True, "moves": moves})


# ── Corbeille de session ─────────────────────────────────────────────────────

_session_basket: list[dict] = []
_BASKET_MAX = 10

# Protège _session_basket : on_basket_add() fait append() + vérification de
# longueur + pop(0) conditionnel, et on_basket_load() fait une vérification
# de borne suivie d'un accès par index — deux handlers déclenchés
# indépendamment par le navigateur, qui peuvent s'entrelacer (ex. un
# basket_load() lisant un index pendant qu'un basket_add() concurrent fait
# déborder la corbeille et décale les indices).
_session_basket_lock = threading.Lock()


@socketio.on("basket_add")
def on_basket_add(data):
    label = data.get("label", "partie.pgn")
    pgn   = data.get("pgn", "").strip()
    if not pgn:
        return
    with _session_basket_lock:
        _session_basket.append({"label": label, "pgn": pgn})
        if len(_session_basket) > _BASKET_MAX:
            _session_basket.pop(0)
        entries = [{"label": e["label"]} for e in _session_basket]
    socketio.emit("basket_updated", {"entries": entries})


@socketio.on("basket_load")
def on_basket_load(data):
    idx = data.get("idx", -1)
    with _session_basket_lock:
        entry = dict(_session_basket[idx]) if 0 <= idx < len(_session_basket) else None
    if entry is not None:
        emit("basket_load_result", {"pgn": entry["pgn"], "label": entry["label"]})
    else:
        emit("basket_load_result", {"pgn": "", "label": ""})


# ── Bibliothèque PGN personnelle ─────────────────────────────────────────────

@socketio.on("pgn_lib_list_collections")
def on_pgn_lib_list_collections(_data):
    """Retourne la liste des collections de la bibliothèque PGN personnelle."""
    from nicsoft.modes.pgn_library import library_manager
    try:
        emit("pgn_lib_collections", {"collections": library_manager.list_collections()})
    except Exception as e:
        emit("pgn_lib_error", {"message": str(e)})


@socketio.on("pgn_lib_create_collection")
def on_pgn_lib_create_collection(data):
    """Crée une nouvelle collection."""
    from nicsoft.modes.pgn_library import library_manager
    try:
        library_manager.create_collection(data.get("name", ""))
        emit("pgn_lib_collections", {"collections": library_manager.list_collections()})
    except Exception as e:
        emit("pgn_lib_error", {"message": str(e)})


@socketio.on("pgn_lib_delete_collection")
def on_pgn_lib_delete_collection(data):
    """Supprime une collection."""
    from nicsoft.modes.pgn_library import library_manager
    try:
        library_manager.delete_collection(data.get("collection_id", ""))
        emit("pgn_lib_collections", {"collections": library_manager.list_collections()})
    except Exception as e:
        emit("pgn_lib_error", {"message": str(e)})


@socketio.on("pgn_lib_import_pgn")
def on_pgn_lib_import_pgn(data):
    """Importe un fichier PGN (une ou plusieurs parties) dans une collection."""
    from nicsoft.modes.pgn_library import library_manager
    try:
        result = library_manager.import_pgn(data.get("collection_id", ""), data.get("content", ""))
        emit("pgn_lib_games", {
            "collection_id": data.get("collection_id", ""),
            "games":          library_manager.list_games(data.get("collection_id", "")),
            "import_result":  result,
        })
    except Exception as e:
        emit("pgn_lib_error", {"message": str(e)})


@socketio.on("pgn_lib_list_games")
def on_pgn_lib_list_games(data):
    """Retourne l'index des parties d'une collection."""
    from nicsoft.modes.pgn_library import library_manager
    try:
        collection_id = data.get("collection_id", "")
        emit("pgn_lib_games", {"collection_id": collection_id, "games": library_manager.list_games(collection_id)})
    except Exception as e:
        emit("pgn_lib_error", {"message": str(e)})


@socketio.on("pgn_lib_load_game")
def on_pgn_lib_load_game(data):
    """Charge le PGN d'une seule partie d'une collection."""
    from nicsoft.modes.pgn_library import library_manager
    try:
        collection_id = data.get("collection_id", "")
        index = data.get("index", -1)
        pgn = library_manager.load_game(collection_id, index)
        emit("pgn_lib_game_loaded", {"collection_id": collection_id, "index": index, "pgn": pgn})
    except Exception as e:
        emit("pgn_lib_error", {"message": str(e)})


# ── Paramètres (config.json centralisé) ──────────────────────────────────────

@socketio.on("config_get")
def on_config_get(_data):
    """Retourne la config courante (champs LLM/Lichess/TTS) — jamais la clé
    API ni le jeton Lichess eux-mêmes (issues #304/#306) : seulement un
    indicateur de présence et, si la valeur fait au moins 12 caractères,
    ses 4 derniers caractères comme indice."""
    from nicsoft.core.config_manager import load_config
    cfg = dict(load_config())
    api_key = cfg.pop("llm_api_key", "")
    cfg["has_llm_api_key"] = bool(api_key)
    cfg["llm_api_key_hint"] = api_key[-4:] if len(api_key) >= 12 else ""
    token = cfg.pop("lichess_token", "")
    cfg["has_lichess_token"] = bool(token)
    cfg["lichess_token_hint"] = token[-4:] if len(token) >= 12 else ""
    emit("config_data", cfg)


@socketio.on("config_save")
def on_config_save(data):
    """Fusionne et sauvegarde la config reçue du navigateur.

    La clé API et le jeton Lichess ne sont jamais renvoyés au navigateur
    (issues #304/#306) : un champ laissé vide par la page ne doit donc pas
    écraser la valeur déjà enregistrée. *_delete=True (action explicite
    "Supprimer") l'efface ; sinon une valeur non vide la remplace (jeton
    Lichess : espaces autour retirés avant comparaison/remplacement).
    """
    from nicsoft.core.config_manager import save_config
    try:
        data = dict(data or {})
        if data.pop("llm_api_key_delete", False):
            data["llm_api_key"] = ""
        elif not data.get("llm_api_key"):
            data.pop("llm_api_key", None)
        if "lichess_token" in data:
            data["lichess_token"] = str(data["lichess_token"] or "").strip()
        if data.pop("lichess_token_delete", False):
            data["lichess_token"] = ""
        elif not data.get("lichess_token"):
            data.pop("lichess_token", None)
        save_config(data)
        emit("config_saved", {"ok": True})
    except Exception as e:
        emit("config_saved", {"ok": False, "error": str(e)})


@socketio.on("lichess_test_connection")
def on_lichess_test_connection(data):
    """Teste la validité d'un jeton Lichess (issue #306, étape L0) : utilise
    le jeton fourni par la page s'il vient d'être saisi (pas encore
    enregistré), sinon celui déjà enregistré dans la config. Le jeton
    n'apparaît jamais dans les journaux ni dans le résultat émis."""
    from nicsoft.core.config_manager import load_config
    sid = request.sid
    typed = ((data or {}).get("token") or "").strip()
    token = typed or load_config().get("lichess_token", "")
    if not token:
        socketio.emit("lichess_test_result", {"status": "invalid"}, to=sid)
        return

    def run():
        from nicsoft.modes.lichess.client import test_token
        try:
            result = test_token(token)
        except Exception as exc:
            # Jamais le jeton ni le détail de l'exception dans les journaux.
            logger.warning(f"Échec du test de connexion Lichess ({type(exc).__name__})")
            result = {"status": "network_error"}
        socketio.emit("lichess_test_result", result, to=sid)

    threading.Thread(target=run, daemon=True).start()


_lichess_test_game_running = threading.Lock()


@socketio.on("lichess_test_game")
def on_lichess_test_game(_data):
    """Teste une vraie partie contre l'IA Lichess niveau 1 (issue #307,
    étape L1) : crée une partie amicale (niveau 1, 15 min sans incrément,
    couleur aléatoire), lit le premier gameFull, puis l'annule (abandon si
    l'annulation est refusée). Utilise uniquement le jeton déjà enregistré
    (bouton désactivé côté page sans jeton). Un seul test de partie à la
    fois ; le jeton n'apparaît jamais dans le résultat émis ni dans les
    journaux."""
    from nicsoft.core.config_manager import load_config
    sid = request.sid
    token = load_config().get("lichess_token", "")
    if not token:
        socketio.emit("lichess_test_game_result", {"status": "invalid"}, to=sid)
        return

    if not _lichess_test_game_running.acquire(blocking=False):
        return  # un test de partie est déjà en cours

    def run():
        from nicsoft.modes.lichess.client import test_ai_game
        try:
            result = test_ai_game(token)
        except Exception as exc:
            # Jamais le jeton ni le détail de l'exception dans les journaux.
            logger.warning(f"Échec du test de partie Lichess ({type(exc).__name__})")
            result = {"status": "network_error"}
        finally:
            _lichess_test_game_running.release()
        socketio.emit("lichess_test_game_result", result, to=sid)

    threading.Thread(target=run, daemon=True).start()


# ── Opening Explorer ──────────────────────────────────────────────────────────

@socketio.on("explorer_get_list")
def on_explorer_get_list(_data):
    """Retourne catalogue Polyglot + mes_lignes groupées pour le sélecteur."""
    from nicsoft.core.game_manager import explorer_get_list
    emit("explorer_list", explorer_get_list())


def _emit_explorer_explanation(sid, state, language, my_gen=0):
    """Génère l'explication LLM du coup en arrière-plan et l'émet au client concerné.

    my_gen : génération TTS (tts_engine._tts_generation) capturée juste après le
    stop_speaking() qui a lancé ce thread. Si elle a changé entre-temps (navigation
    plus récente → clics rapides Suivant/Précédent), on abandonne silencieusement,
    y compris avant l'appel LLM pour ne pas gaspiller un appel devenu obsolète.
    """
    from nicsoft.modes.opening_explorer.llm_explainer import get_explanation
    from nicsoft.core.config_manager import load_config
    from nicsoft.modes.opening_explorer.tts_engine import speak

    if not state or state.get("error") or not state.get("move_san"):
        return
    if tts_engine._tts_generation != my_gen:
        return  # navigation plus récente, on abandonne avant l'appel LLM
    cfg = load_config()
    expl, arrows = get_explanation(
        line_id=state.get("line_id", ""),
        move_index=state.get("move_index", 0),
        fen=state.get("fen", ""),
        move_san=state.get("move_san", ""),
        opening_name=state.get("opening_name", ""),
        camp=state.get("camp", "white"),
        alternatives=state.get("alternatives", []),
        language=language,
        config=cfg,
    )
    if expl:
        if tts_engine._tts_generation != my_gen:
            return  # navigation plus récente, on abandonne
        socketio.emit("explorer_explanation", {"text": expl, "arrows": [list(a) for a in arrows]}, to=sid)
        if cfg.get("tts_enabled", False):
            if tts_engine._tts_generation != my_gen:
                return
            socketio.emit("explorer_tts_start", {}, to=sid)
            def on_playing():
                socketio.emit("explorer_tts_playing", {}, to=sid)
            tts_ok = speak(expl, rate=cfg.get("tts_rate", 150), enabled=True, language=language, volume=cfg.get("tts_volume", 80), on_playback_start=on_playing)
            socketio.emit("explorer_tts_end", {}, to=sid)
            if not tts_ok:
                socketio.emit("explorer_tts_fallback", {"text": expl}, to=sid)


def _emit_explorer_chat_response(sid, question, state, language):
    """Génère la réponse du LLM à une question libre en arrière-plan et l'émet au client."""
    from nicsoft.modes.opening_explorer.llm_explainer import get_chat_response
    from nicsoft.core.config_manager import load_config
    from nicsoft.modes.opening_explorer.tts_engine import speak

    cfg = load_config()
    response, arrows = get_chat_response(question, state, language, cfg)
    if response:
        socketio.emit("explorer_chat_response", {"text": response, "arrows": [list(a) for a in arrows]}, to=sid)
        if cfg.get("tts_enabled", False):
            socketio.emit("explorer_tts_start", {}, to=sid)
            def on_playing():
                socketio.emit("explorer_tts_playing", {}, to=sid)
            tts_ok = speak(response, rate=cfg.get("tts_rate", 150), enabled=True, language=language, volume=cfg.get("tts_volume", 80), on_playback_start=on_playing)
            socketio.emit("explorer_tts_end", {}, to=sid)
            if not tts_ok:
                socketio.emit("explorer_tts_fallback", {"text": response}, to=sid)


@socketio.on("explorer_load")
def on_explorer_load(data):
    """Charge une ouverture (catalogue ou ligne perso) — connexion échiquier en arrière-plan."""
    stop_speaking()  # invalide (tts_engine._tts_generation) toute explication LLM encore en vol
    source_type   = data.get("source_type", "polyglot")
    opening_id    = data.get("opening_id", "")
    variant_index = data.get("variant_index")

    def run():
        from nicsoft.core.game_manager import explorer_load
        state = explorer_load(source_type, opening_id, variant_index)
        socketio.emit("explorer_state", state)
        socketio.emit("explorer_explanation", {"text": "", "arrows": []})

    threading.Thread(target=run, daemon=True).start()


@socketio.on("explorer_next")
def on_explorer_next(data):
    stop_speaking()
    my_gen = tts_engine._tts_generation
    from nicsoft.core.game_manager import explorer_next
    state = explorer_next()
    emit("explorer_state", state)
    language = (data or {}).get("language", "fr")
    sid = request.sid
    threading.Thread(target=_emit_explorer_explanation, args=(sid, state, language, my_gen), daemon=True).start()


@socketio.on("explorer_prev")
def on_explorer_prev(data):
    stop_speaking()
    my_gen = tts_engine._tts_generation
    from nicsoft.core.game_manager import explorer_prev
    state = explorer_prev()
    emit("explorer_state", state)
    language = (data or {}).get("language", "fr")
    sid = request.sid
    threading.Thread(target=_emit_explorer_explanation, args=(sid, state, language, my_gen), daemon=True).start()


@socketio.on("explorer_choose_move")
def on_explorer_choose_move(data):
    stop_speaking()
    my_gen = tts_engine._tts_generation
    uci = (data or {}).get("uci", "")
    if not uci:
        return
    from nicsoft.core.game_manager import explorer_choose_move
    state = explorer_choose_move(uci)
    emit("explorer_state", state)
    language = (data or {}).get("language", "fr")
    sid = request.sid
    threading.Thread(
        target=_emit_explorer_explanation,
        args=(sid, state, language, my_gen),
        daemon=True
    ).start()


@socketio.on("explorer_chat")
def on_explorer_chat(data):
    """Question libre de l'utilisateur sur la position courante — réponse LLM en arrière-plan."""
    question = (data or {}).get("question", "").strip()
    language = (data or {}).get("language", "fr")
    sid = request.sid
    if not question:
        return
    from nicsoft.core.game_manager import explorer_get_state
    state = explorer_get_state()
    if not state:
        emit("explorer_chat_response", {"text": "", "arrows": []})
        return
    threading.Thread(
        target=_emit_explorer_chat_response,
        args=(sid, question, state, language),
        daemon=True
    ).start()


@socketio.on("explorer_back")
def on_explorer_back(_data):
    """Referme la connexion échiquier de l'Opening Explorer (retour sélecteur ou menu)."""
    from nicsoft.core.game_manager import explorer_cleanup
    explorer_cleanup()


@socketio.on("explorer_tts_stop")
def on_explorer_tts_stop(_data):
    """Arrête immédiatement la lecture TTS en cours (toggle 🔇 pendant lecture)."""
    stop_speaking()


# ── Analyse de partie — panneau IA (drawer, conversation multi-tours, issue #196) ─

# Compteur de génération — incrémenté à chaque nouveau message envoyé depuis le
# drawer. Un thread en vol dont le compteur capturé ne correspond plus à la
# valeur courante abandonne silencieusement sa réponse (nouveau message arrivé
# entre-temps), même mécanisme que tts_engine._tts_generation pour l'Explorateur.
_analyse_llm_request_id: int = 0

# Protège l'incrémentation de _analyse_llm_request_id : deux messages
# envoyés coup sur coup depuis le drawer IA déclenchent deux exécutions
# concurrentes de on_analyse_llm_ask() (un thread par événement SocketIO en
# async_mode="threading") ; un `+= 1` non protégé pourrait faire calculer le
# même my_id aux deux, cassant l'abandon silencieux des réponses obsolètes.
_analyse_llm_lock = threading.Lock()


def _emit_analyse_llm_response(sid, messages, context, language, my_id):
    from nicsoft.modes.opening_explorer.llm_explainer import get_analyse_response
    from nicsoft.core.config_manager import load_config

    cfg = load_config()
    response, error = get_analyse_response(messages, context, language, cfg)
    if _analyse_llm_request_id != my_id:
        return  # nouveau message envoyé entre-temps, réponse obsolète
    if error:
        socketio.emit("analyse_llm_error", {"error": error}, to=sid)
    else:
        socketio.emit("analyse_llm_response", {"text": response}, to=sid)


@socketio.on("analyse_llm_ask")
def on_analyse_llm_ask(data):
    """Message envoyé depuis le drawer IA de l'écran Analyse de partie —
    reçoit l'historique complet de la conversation + le contexte de la
    position courante (fen/move/pgn), lance la génération LLM en arrière-plan."""
    global _analyse_llm_request_id
    data = data or {}
    messages = data.get("messages") or []
    context  = data.get("context") or {}
    language = data.get("language", "fr")
    if not messages:
        return
    with _analyse_llm_lock:
        _analyse_llm_request_id += 1
        my_id = _analyse_llm_request_id
    sid = request.sid
    threading.Thread(
        target=_emit_analyse_llm_response,
        args=(sid, messages, context, language, my_id),
        daemon=True,
    ).start()


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
                logger.debug(f"[DISPATCH] {event['type']}")
            socketio.emit(event["type"], event["data"])
        except queue.Empty:
            # Idiome de vidage de queue — aucun événement disponible, on boucle.
            continue
        except Exception as e:
            logger.error(f"Erreur dispatch event {event.get('type','?')}: {e}", exc_info=True)


def emit(event_type: str, data: dict) -> None:
    """
    API publique — émission SocketIO directe, hors event_queue (ex.
    popups ponctuels qui n'ont pas besoin d'être tracés dans _game_state).
    """
    socketio.emit(event_type, data)


def send_event(event_type: str, data: dict) -> None:
    """
    API publique — appelée par le module pédagogique pour envoyer
    un événement au navigateur.
    """
    global _board_status, _board_error_message
    # Mettre à jour le statut échiquier — sous verrou, le couple
    # statut/message doit rester cohérent pour les lecteurs (on_connect,
    # set_app_state).
    with _board_status_lock:
        if event_type == "board_ok":
            _board_status = "ok"
            _board_error_message = ""
        elif event_type == "board_error":
            _board_status = "error"
            _board_error_message = data.get("message", "")
        elif event_type == "board_reconnecting":
            _board_status = "reconnecting"
            _board_error_message = data.get("message", "")
    # Mettre à jour l'état courant — sous verrou : chaque branche est une
    # séquence composée (setdefault+append, pop conditionnel, lecture de
    # hist[-1] avant mutation) qui doit s'exécuter sans entrelacement avec
    # une autre mutation ou avec la lecture faite par on_connect().
    with _game_state_lock:
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
            count = data.get("count", 1)
            for _ in range(count):
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


def set_history(history: list, history_fen: list) -> None:
    """
    API publique — remplace atomiquement _game_state["history"] et
    _game_state["history_fen"]. À utiliser par tout module hors server.py
    (human.py, game_manager.py) au lieu de muter _game_state directement,
    pour ne pas s'entrelacer avec les séquences composées de send_event()
    ou la lecture multi-clés de on_connect().
    """
    with _game_state_lock:
        _game_state["history"] = history
        _game_state["history_fen"] = history_fen


def get_history() -> tuple:
    """
    API publique — lit atomiquement (history, history_fen) depuis
    _game_state. À utiliser par tout module hors server.py au lieu de
    lire _game_state["history"]/["history_fen"] séparément, pour éviter
    d'observer les deux clés à des instants différents pendant qu'un
    thread SocketIO les mute via send_event().
    """
    with _game_state_lock:
        return _game_state.get("history", []), _game_state.get("history_fen", [])


def get_init_data() -> dict:
    """
    API publique — lit _game_state["init"] (payload du dernier événement
    'init'). À utiliser par tout module hors server.py au lieu de lire
    _game_state["init"] directement.
    """
    with _game_state_lock:
        return _game_state.get("init", {})


def get_action(timeout: float = 0.0):
    """
    API publique — appelée par le module pédagogique pour récupérer
    une action du navigateur. Retourne None si aucune action.
    """
    try:
        return action_queue.get(timeout=timeout)
    except queue.Empty:
        # Idiome de vidage de queue — timeout normal, aucune action en attente.
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
    # Au retour menu, renvoyer le statut échiquier pour réactiver les
    # boutons — instantané sous verrou (cf. _board_status_lock).
    if state == "menu":
        with _board_status_lock:
            board_status, board_error_message = _board_status, _board_error_message
        if board_status == "ok":
            socketio.emit("board_ok", {})
        elif board_status == "error":
            socketio.emit("board_error", {"message": board_error_message})
        elif board_status == "reconnecting":
            socketio.emit("board_reconnecting", {"message": board_error_message})


def get_menu_action(timeout: float = 1.0):
    """Récupère une action du menu. Retourne None si timeout."""
    try:
        return menu_queue.get(timeout=timeout)
    except queue.Empty:
        # Idiome de vidage de queue — timeout normal, aucune action en attente.
        return None


def start_server(host="127.0.0.1", port=5000, debug=False) -> threading.Thread:
    """
    Démarre le serveur Flask-SocketIO dans un thread daemon.
    Retourne le thread pour référence.
    """
    set_server_port(port)

    dispatch_thread = threading.Thread(target=_dispatch_loop, daemon=True)
    dispatch_thread.start()

    server_thread = threading.Thread(
        target=lambda: socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True),
        daemon=True,
    )
    server_thread.start()

    # Ligne garantie, indépendante de la configuration de journalisation
    # (niveau des loggers, destination de la sortie) et du comportement de
    # Werkzeug — toujours affichée, contrairement à logger.info() ci-dessous
    # qui dépend du niveau du logger "niclink.server" (issue #312).
    print(f"[NicLink] Interface disponible sur http://{host}:{port}", flush=True)
    logger.info(f"[WEB] Serveur démarré sur http://{host}:{port}")
    return server_thread
