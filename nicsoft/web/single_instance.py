"""
nicsoft/web/single_instance.py — Une seule instance AlChess à la fois (#320).

Au démarrage, une instance écrit un petit marqueur (PID, port, heure de
démarrage) dans DATA_DIR. Une nouvelle instance qui démarre lit ce marqueur :

- absent, ou désignant un PID mort, ou un PID réutilisé par un programme
  qui n'est manifestement pas AlChess (vérifié par la ligne de commande,
  jamais par le seul nom du programme) → marqueur périmé, ignoré.
- désignant une instance AlChess vivante → on l'interroge en local
  (route HTTP /instance_status, jamais par une simple lecture du marqueur
  qui pourrait dater d'avant le dernier changement d'état) :
    - partie en cours (état dans BUSY_STATES, ou impossible à confirmer) →
      on NE démarre PAS, on laisse l'ancienne instance intacte.
    - pas de partie en cours → on l'arrête proprement par son PID exact
      (jamais par son nom), on attend sa sortie, on démarre.

Aucune recherche ni arrêt de processus par nom de programme (pgrep/pkill/
taskkill /IM/Stop-Process -Name) : uniquement par PID exact, obtenu depuis
ce marqueur.
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from nicsoft.config import DATA_DIR

MARKER_FILENAME = "server_instance.json"

# Sous-chaînes attendues dans la ligne de commande d'un vrai processus
# AlChess — jamais le nom de l'exécutable (python/python3) seul, qui ne
# prouve rien.
CMDLINE_MARKERS = ("nicsoft.web", "nicsoft/web", "nicsoft\\web")

# États _app_state (server.py) correspondant à une partie en cours (toute
# "mode de jeu", Lichess compris) — distincts des écrans de menu/config/
# sélection et des outils d'analyse libre (labo, opening_explorer), qui ne
# sont pas "une partie".
BUSY_STATES = frozenset({
    "connecting",
    "playing",
    "paused",
    "position_initiale",
    "lichess_wait_first_move",
    "retrans_playing",
    "exercice_running",
})

# Délai d'attente d'un arrêt propre avant de forcer (secondes).
_GRACEFUL_WAIT_S = 5.0
_POLL_INTERVAL_S = 0.25

# Délai max pour interroger l'état de l'ancienne instance en local.
_STATUS_TIMEOUT_S = 2.0


def _marker_path():
    return DATA_DIR / MARKER_FILENAME


def write_marker(pid: int, port: int, started_at: str) -> None:
    """Écrit le marqueur d'instance. Écriture atomique (fichier temporaire
    puis renommage) pour qu'une lecture concurrente ne voie jamais un
    fichier à moitié écrit."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"pid": pid, "port": port, "started_at": started_at}
    tmp_path = _marker_path().with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(_marker_path())


def remove_marker(pid: int) -> None:
    """Supprime le marqueur, seulement s'il désigne encore ce PID — une
    instance qui s'arrête ne doit jamais effacer le marqueur d'une instance
    plus récente qui l'aurait déjà remplacé."""
    existing = _read_marker()
    if existing is None or existing.get("pid") != pid:
        return
    try:
        _marker_path().unlink()
    except FileNotFoundError:
        pass


def _read_marker():
    path = _marker_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("pid"), int) or not isinstance(data.get("port"), int):
        return None
    return data


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # processus existe, appartient à un autre utilisateur
    return True


def _cmdline_for_pid(pid: int):
    if sys.platform == "win32":
        return _cmdline_windows(pid)
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return None
    return raw.replace(b"\x00", b" ").decode(errors="replace")


def _is_alchess_process(pid: int) -> bool:
    """Vérifie par la ligne de commande, jamais par le seul nom du
    programme (un PID réutilisé par un autre script Python ne doit pas être
    pris pour AlChess)."""
    cmdline = _cmdline_for_pid(pid)
    if not cmdline:
        return False
    return any(marker in cmdline for marker in CMDLINE_MARKERS)


def _pid_alive_windows(pid: int) -> bool:
    try:
        # Arguments fixes, filtre par PID numérique précis, jamais par nom.
        result = subprocess.run(  # noqa: S603 S607  # nosec B603 B607
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return str(pid) in result.stdout


def _cmdline_windows(pid: int):
    try:
        # Arguments fixes, filtre par PID numérique précis, jamais par nom.
        result = subprocess.run(  # noqa: S603 S607  # nosec B603 B607
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    lines = [l.strip() for l in result.stdout.splitlines() if l.strip() and l.strip().lower() != "commandline"]
    return lines[0] if lines else None


def _terminate_pid(pid: int) -> None:
    """Arrête l'instance désignée par ce PID exact : demande d'arrêt propre,
    attente, puis arrêt forcé seulement en dernier recours — toujours par ce
    même PID, jamais par nom."""
    if sys.platform == "win32":
        # PID numérique interne en argument fixe, jamais un nom de programme.
        subprocess.run(  # noqa: S603 S607  # nosec B603 B607
            ["taskkill", "/PID", str(pid)], capture_output=True, timeout=5,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return

    deadline = time.monotonic() + _GRACEFUL_WAIT_S
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(_POLL_INTERVAL_S)

    if not _pid_alive(pid):
        return
    if sys.platform == "win32":
        # PID numérique interne en argument fixe, jamais un nom de programme.
        subprocess.run(  # noqa: S603 S607  # nosec B603 B607
            ["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=5,
        )
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _query_state(port: int):
    """Interroge l'ancienne instance en local pour son état courant —
    adresse fixe (127.0.0.1) vérifiée avant tout appel réseau."""
    url = f"http://127.0.0.1:{port}/instance_status"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        return None
    try:
        # Adresse locale fixe (127.0.0.1), schéma http vérifié juste au-dessus.
        with urllib.request.urlopen(url, timeout=_STATUS_TIMEOUT_S) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def resolve_startup():
    """Décide si cette nouvelle instance peut démarrer.

    Retourne (True, None) si le démarrage peut continuer (aucune ancienne
    instance active, marqueur périmé ignoré, ou ancienne instance inactive
    arrêtée avec succès), ou (False, message) si une partie est en cours
    dans l'ancienne instance (ou si son état n'a pas pu être confirmé) et
    qu'il ne faut PAS démarrer ni toucher à cette ancienne instance.
    """
    marker = _read_marker()
    if marker is None:
        return True, None

    pid, port = marker["pid"], marker["port"]
    if not _pid_alive(pid) or not _is_alchess_process(pid):
        return True, None  # marqueur périmé (process mort ou PID réutilisé) — ignoré, sera remplacé

    status = _query_state(port)
    if status is None:
        return False, (
            f"Impossible de confirmer l'état de l'instance déjà lancée "
            f"(PID {pid}, port {port}) — démarrage annulé par précaution."
        )

    state = status.get("state")
    if state in BUSY_STATES:
        return False, f"Une partie est en cours dans l'instance déjà lancée, port {port}."

    _terminate_pid(pid)
    return True, None
