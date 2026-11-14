"""
nicsoft/modes/lichess/seek.py — AlChess

Issue #327, points 2 et 3 : recherche d'un adversaire humain en partie
amicale. Implémente le protocole officiel board/seek de Lichess (doc
officielle lichess-org/api, doc/specs/tags/board/api-board-seek.yaml et
api-stream-event.yaml, lues le 14/11/2026) :

  - POST /api/board/seek reste ouvert (lignes vides périodiques) tant que
    la recherche est active côté serveur ; FERMER cette connexion est le
    seul moyen d'annuler la recherche (« If the client closes the
    connection, the seek is canceled »). Elle se ferme d'elle-même, sans
    aucune donnée, dès qu'un adversaire est trouvé ou que la recherche
    expire.
  - Le flux de recherche lui-même ne contient AUCUNE information sur la
    partie trouvée : il faut, en parallèle, un flux général d'évènements
    ouvert (GET /api/stream/event, qui porte l'évènement `gameStart` avec
    l'identifiant de la nouvelle partie). La documentation recommande
    d'ouvrir CE flux-là en premier, puis la recherche, pour ne jamais
    manquer un appariement immédiat.

Aucune limite de durée n'est imposée ici (issue #327, point 3) : la
recherche reste active aussi longtemps que les deux flux restent ouverts ;
seule une annulation explicite (cancel()) ou une coupure réseau y met fin
côté AlChess.

N'importe jamais nicsoft.web (ARC-001).
"""

import json
import logging
import queue
import threading

from nicsoft.modes.lichess.transport import (
    TransportHTTPError,
    TransportNetworkError,
    TransportTimeoutError,
)

logger = logging.getLogger("niclink.lichess")


class SeekSession:
    """Une recherche d'adversaire humain à la fois (jamais réutilisée pour
    une seconde recherche — créer une nouvelle instance). `start()` ouvre
    les deux flux et retourne aussitôt (lecture dans deux fils dédiés,
    daemon) ; `next_event(timeout)` consomme les évènements produits ;
    `cancel()` ferme les deux flux sans attendre leur fin naturelle."""

    def __init__(self, client, game_log=None):
        self._client = client
        self._game_log = game_log
        self._events = queue.Queue()
        self._event_handle = None
        self._seek_handle = None
        self._cancelled = False
        self._found = False
        self._lock = threading.Lock()

    def start(self, clock_limit_minutes, clock_increment_s: int, color: str = "") -> None:
        """Tente d'ouvrir les deux flux ; en cas d'échec (réseau, jeton
        refusé...), pousse un seul évènement {"type": "error", ...} et ne
        démarre aucun fil de lecture — jamais de blocage silencieux (issue
        #327, point 3)."""
        try:
            self._event_handle = self._client.open_event_stream()
        except (TransportHTTPError, TransportNetworkError, TransportTimeoutError) as exc:
            self._push_error(exc, "ouverture du flux d'évènements")
            return
        try:
            self._seek_handle = self._client.open_seek_stream(clock_limit_minutes, clock_increment_s, color)
        except (TransportHTTPError, TransportNetworkError, TransportTimeoutError) as exc:
            self._event_handle.close()
            self._push_error(exc, "ouverture de la recherche")
            return
        if self._game_log is not None:
            self._game_log.state_change(
                f"recherche d'adversaire démarrée — cadence={clock_limit_minutes}+{clock_increment_s} min, "
                f"couleur={color or 'aléatoire'}."
            )
        logger.info(
            "Lichess : recherche d'adversaire humain démarrée (cadence=%s+%s, couleur=%s).",
            clock_limit_minutes, clock_increment_s, color or "aléatoire",
        )
        threading.Thread(target=self._read_event_stream, daemon=True).start()
        threading.Thread(target=self._read_seek_stream, daemon=True).start()

    def _push_error(self, exc: Exception, context: str) -> None:
        logger.warning("Lichess : recherche d'adversaire — %s échouée (%s).", context, type(exc).__name__)
        if self._game_log is not None:
            self._game_log.connectivity(f"recherche d'adversaire — {context} échouée : {type(exc).__name__}.")
        self._events.put({"type": "error", "reason": type(exc).__name__})

    def _mark_found(self, game: dict) -> bool:
        """Retourne True si c'est bien cette fois-ci que la partie trouvée
        est signalée (évite un double évènement "found" si, par une
        coïncidence de minutage, les deux fils se terminaient chacun en
        croyant être le premier)."""
        with self._lock:
            if self._found:
                return False
            self._found = True
            return True

    def _read_event_stream(self) -> None:
        try:
            for line in self._event_handle.lines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "gameStart" and self._mark_found(event.get("game") or {}):
                    self._seek_handle.close()
                    self._events.put({"type": "found", "game": event.get("game") or {}})
                    return
        except (TransportNetworkError, TransportTimeoutError) as exc:
            if not self._cancelled and not self._found:
                self._push_error(exc, "flux d'évènements (coupure)")

    def _read_seek_stream(self) -> None:
        try:
            for _line in self._seek_handle.lines():
                self._events.put({"type": "waiting"})
        except (TransportNetworkError, TransportTimeoutError) as exc:
            if not self._cancelled and not self._found:
                self._push_error(exc, "flux de recherche (coupure)")
            return
        # Flux de recherche fermé par Lichess — appariement (le flux
        # d'évènements porte alors gameStart, déjà géré ci-dessus) ou
        # recherche annulée par cancel() (self._cancelled déjà vrai dans ce
        # cas). Si ni l'un ni l'autre, c'est Lichess qui a mis fin à la
        # recherche de son côté sans appariement (aucune durée maximale
        # documentée — cas non observé en pratique, prudence) : le signaler
        # plutôt que de laisser l'appelant attendre indéfiniment un
        # gameStart qui ne viendra jamais.
        if not self._cancelled and not self._found:
            logger.info("Lichess : flux de recherche fermé par Lichess sans appariement signalé.")
            self._events.put({"type": "seek_closed"})

    def next_event(self, timeout: float = 0.2):
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def cancel(self) -> None:
        """Ferme les deux flux — annulation réelle de la recherche côté
        Lichess (voir en-tête de module). Idempotent."""
        if self._cancelled or self._found:
            return
        self._cancelled = True
        logger.info("Lichess : recherche d'adversaire annulée par l'utilisateur.")
        if self._game_log is not None:
            self._game_log.state_change("recherche d'adversaire annulée par l'utilisateur.")
        if self._seek_handle is not None:
            self._seek_handle.close()
        if self._event_handle is not None:
            self._event_handle.close()
