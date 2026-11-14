"""
nicsoft/modes/lichess/game_log.py — AlChess

Issue #326, point 10 : journal de partie dédié. Aucune vraie partie
Lichess ne peut être rejouée en développement (contre l'IA : coûte une
vraie requête à chaque essai ; contre un humain : jamais reproductible du
tout) — ce module écrit, pour CHAQUE partie Lichess (IA ou humain),
toujours actif (pas de mode de débogage à activer), un fichier dédié dans
LOGS_DIR/lichess/, en plus du journal général (niclink.log, inchangé).

Chaque ligne est horodatée à la milliseconde et écrite sur le disque
immédiatement (`flush()` après chaque écriture) : le fichier reste lisible
même après un arrêt brutal du processus (les données déjà passées au
système d'exploitation ne dépendent plus du processus AlChess lui-même).

Jamais le jeton Lichess (masqué par _mask, qui ne dépend pas de connaître
sa valeur exacte — une regex générique suffit si elle n'est pas fournie) ni
les messages de tchat de l'adversaire (chat() journalise seulement le fait
qu'une ligne a été ignorée, jamais son contenu).

N'importe jamais nicsoft.web (ARC-001) — seul nicsoft.config (chemins) est
utilisé en dehors de la bibliothèque standard.
"""

import datetime
import logging
import re
import threading
import time

from nicsoft.config import LOGS_DIR

logger = logging.getLogger("niclink.lichess")

LICHESS_LOGS_DIR = LOGS_DIR / "lichess"

# Nombre de fichiers conservés (issue #326, point 10 : "les 50 plus
# récents") — au-delà, les plus anciens sont supprimés à la création d'un
# nouveau fichier, jamais pendant l'écriture d'une partie en cours.
KEEP_LAST = 50

# Cadence de la ligne de contrôle périodique (voir heartbeat ci-dessous) —
# assez courte pour situer une panne à ~30s près, assez longue pour ne pas
# noyer le fichier (un tick physique a lieu toutes les 50ms, bien plus
# fréquent que cette ligne de contrôle).
HEARTBEAT_INTERVAL_S = 30.0

# Jamais le jeton en clair, même sans sa valeur exacte (_token non fourni,
# ou futur champ inattendu) : préfixe officiel des jetons personnels
# Lichess ("lip_" + suite alphanumérique, cf. doc lichess-org/api) et toute
# valeur d'en-tête Authorization Bearer.
_TOKEN_PATTERN = re.compile(r"lip_[A-Za-z0-9_-]{10,}|Bearer\s+\S+", re.IGNORECASE)

_SAFE_GAME_ID = re.compile(r"[^A-Za-z0-9_-]")


def _sanitize_game_id(game_id: str) -> str:
    return _SAFE_GAME_ID.sub("_", game_id or "partie")[:64] or "partie"


def _prune_old_logs(logs_dir, keep: int) -> None:
    """Supprime les plus anciens fichiers *.log au-delà de `keep` — jamais
    pendant l'écriture d'une partie en cours (appelé uniquement à la
    création d'un nouveau fichier). Les noms commencent par un horodatage
    trié (YYYYMMDD-HHMMSS_...), donc le tri lexicographique suffit."""
    try:
        files = sorted(logs_dir.glob("*.log"))
    except OSError as exc:
        logger.debug("Lichess : purge des anciens journaux de partie échouée (listage) : %s", exc)
        return
    excess = len(files) - keep
    for path in files[:max(0, excess)]:
        try:
            path.unlink()
        except OSError as exc:
            logger.debug("Lichess : suppression ancien journal de partie échouée (%s) : %s", path, exc)


class GameLog:
    """Journal dédié d'une partie Lichess — un fichier par partie, créé dès
    que `game_id` est connu. `token`, si fourni, est en plus masqué
    littéralement (défense supplémentaire à la regex générique
    _TOKEN_PATTERN, qui suffit déjà seule à ne jamais l'écrire)."""

    def __init__(self, game_id: str, token: str = "", logs_dir=None):
        self._game_id = game_id or "partie"
        self._token = (token or "").strip()
        self._lock = threading.Lock()
        self._last_heartbeat_ts = time.monotonic()
        self._fh = None

        directory = logs_dir if logs_dir is not None else LICHESS_LOGS_DIR
        try:
            directory.mkdir(parents=True, exist_ok=True)
            _prune_old_logs(directory, KEEP_LAST - 1)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"{stamp}_{_sanitize_game_id(self._game_id)}.log"
            self.path = directory / filename
            # buffering=1 (ligne par ligne) : chaque write() ci-dessous appelle
            # quand même flush() explicitement, qui est la garantie réelle
            # (buffering=1 ne suffirait pas si write() n'était jamais suivi
            # d'un flush, cf. documentation io — défense en profondeur).
            self._fh = open(self.path, "a", buffering=1, encoding="utf-8")
        except OSError as exc:
            logger.warning("Lichess : journal dédié de partie non créé (%s) : %s", self._game_id, exc)
            self.path = None
            return

        self._write("INIT", f"Journal de partie Lichess ouvert — game_id={self._game_id}")

    # ── Interne ──────────────────────────────────────────────────────────

    def _mask(self, text: str) -> str:
        text = _TOKEN_PATTERN.sub("***", text)
        if self._token and len(self._token) >= 8:
            text = text.replace(self._token, "***")
        return text

    def _write(self, category: str, message: str) -> None:
        if self._fh is None:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"{ts} [{category}] {self._mask(message)}\n"
        try:
            with self._lock:
                self._fh.write(line)
                self._fh.flush()
        except OSError as exc:
            logger.debug("Lichess : écriture journal dédié de partie échouée (%s) : %s", self._game_id, exc)

    # ── API publique — voir en-tête de module pour le détail attendu ─────

    def raw(self, line: str) -> None:
        """(a) Ligne brute reçue de Lichess pendant la partie, telle quelle
        — sauf un événement de tchat, jamais journalisé (voir chat_ignored,
        appelé par le code qui détecte le type "chatLine" avant de passer
        la ligne ici)."""
        self._write("RAW", line)

    def chat_ignored(self) -> None:
        """Remplace raw() pour une ligne de type "chatLine" — jamais son
        contenu, seulement le fait qu'un message de tchat est arrivé et a
        été ignoré."""
        self._write("RAW", "(ligne de tchat adverse reçue — ignorée, contenu jamais journalisé)")

    def request(self, action: str, detail: str, result: str, duration_s: float) -> None:
        """(b) Requête envoyée à Lichess (coup, offre de nulle, abandon,
        réponse à une offre) avec son résultat et sa durée."""
        self._write("REQUEST", f"{action} {detail} -> {result} ({duration_s * 1000:.0f} ms)")

    def board_change(self, message: str) -> None:
        """(c) Coup/cases modifiées, position lue, décision prise."""
        self._write("BOARD", message)

    def state_change(self, message: str) -> None:
        """(d) Changement d'état de l'application, raison des boutons actifs/grisés."""
        self._write("STATE", message)

    def clock(self, white_ms, black_ms, turn: str, source: str) -> None:
        """(e) Pendules affichées et leur source."""
        self._write("CLOCK", f"blancs={white_ms} noirs={black_ms} trait={turn} source={source}")

    def connectivity(self, message: str) -> None:
        """(f) Perte/reprise de l'échiquier ou du réseau, tentatives de
        reconnexion et leur durée."""
        self._write("CONN", message)

    def exception(self, exc: BaseException, context: str = "") -> None:
        """(g) Exception avec trace complète — y compris pour les fils
        d'exécution secondaires (l'appelant passe `context` pour identifier
        lequel)."""
        import traceback
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        prefix = f"{context} — " if context else ""
        self._write("EXC", f"{prefix}{type(exc).__name__}: {exc}\n{trace}")

    def maybe_heartbeat(self, turn: str, white_ms, black_ms, board_connected: bool, last_read_age_s: float) -> None:
        """(g, fin) Ligne de contrôle périodique (~30s) — trait, pendules,
        échiquier connecté, âge de la dernière lecture — pour voir où une
        panne a commencé même sans aucun autre événement entre-temps."""
        now = time.monotonic()
        if now - self._last_heartbeat_ts < HEARTBEAT_INTERVAL_S:
            return
        self._last_heartbeat_ts = now
        self._write(
            "HEARTBEAT",
            f"trait={turn} blancs={white_ms} noirs={black_ms} "
            f"echiquier_connecte={board_connected} derniere_lecture_il_y_a={last_read_age_s:.1f}s",
        )

    def close(self) -> None:
        if self._fh is None:
            return
        try:
            self._write("INIT", "Journal de partie Lichess fermé.")
            with self._lock:
                self._fh.close()
        except OSError:
            pass
        finally:
            self._fh = None
