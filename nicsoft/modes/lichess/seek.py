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

Issue #328 (essai réel du 14/11/2026) : la documentation officielle
n'indique AUCUN ordre ni délai garanti entre la fermeture du flux de
recherche (appariement) et l'arrivée de `gameStart` sur le flux
d'évènements — établi par lecture du code, resté une hypothèse pour la
suite (non vérifiable sans vraie partie, voir rapport de clôture). Ce
module se contente donc de ne JAMAIS fermer le flux d'évènements tant que
l'appelant n'a pas renoncé à attendre `gameStart` (voir "seek_closed"
ci-dessous, et l'attente côté appelant dans
game_manager_modes/lichess.py::_run_lichess_human) ; c'est cette attente,
pas ce module, qui décidait trop tôt à l'échec et interrompait la lecture
en cours, provoquant l'exception non interceptée qui a fait perdre la
partie créée côté Lichess ce jour-là (seek.py ne fermait déjà le flux
d'évènements qu'après avoir lu gameStart ou reçu cancel()/close()).

N'importe jamais nicsoft.web (ARC-001).
"""

import json
import logging
import queue
import threading

from nicsoft.modes.lichess.errors import extract_api_message
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
    `cancel()`/`close()` ferment les deux flux sans attendre leur fin
    naturelle — `cancel()` pour une annulation utilisateur explicite (son
    propre message de journal), `close()` pour toute autre conclusion déjà
    journalisée par l'appelant (issue #328, point 4)."""

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
        """Journalise puis signale l'échec à l'appelant — le détail HTTP
        (code, Retry-After, corps déjà journalisé en entier par
        transport.py au journal général) est repris ici dans l'évènement
        poussé, pour que l'appelant (game_manager_modes/lichess.py) affiche
        le message exact attendu plutôt qu'un message réseau générique
        (issue #329, point 2) — jamais le jeton, absent de tout ce qui suit."""
        status_code = getattr(exc, "status_code", None)
        retry_after_s = getattr(exc, "retry_after_s", None)
        api_message = extract_api_message(getattr(exc, "body", "") or "") if status_code is not None else ""
        detail = f"HTTP {status_code}" if status_code is not None else type(exc).__name__
        logger.warning("Lichess : recherche d'adversaire — %s échouée (%s).", context, detail)
        if self._game_log is not None:
            self._game_log.connectivity(
                f"recherche d'adversaire — {context} échouée : {detail}"
                + (f" ({api_message})" if api_message else "") + "."
            )
        self._events.put({
            "type": "error",
            "reason": type(exc).__name__,
            "status_code": status_code,
            "retry_after_s": retry_after_s,
            "detail": api_message,
        })

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
                if self._game_log is not None and line.strip():
                    # Lignes brutes du flux d'évènements pendant la
                    # recherche (issue #328, point 6) — jamais de tchat sur
                    # ce flux à ce stade (aucune partie n'existe encore),
                    # donc toujours sans risque via raw() directement.
                    self._game_log.raw(line)
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
        except Exception as exc:
            # Toute autre exception imprévue dans ce fil secondaire (ex. la
            # fermeture de StreamHandle depuis un autre fil pendant une
            # lecture bloquante, en principe déjà absorbée par
            # transport.py::StreamHandle.lines() — défense en profondeur) ne
            # doit jamais rester seulement visible dans le terminal (issue
            # #328, point 4 ; même traitement que
            # LichessGame._stream_reader_loop, game.py) — et ne doit jamais
            # non plus laisser l'appelant attendre indéfiniment un "found"
            # qui ne viendra plus : un évènement "error" est poussé, sauf si
            # la session est déjà résolue (cancel()/close()/found), où elle
            # est sans effet pour l'appelant.
            logger.error(
                "Lichess : exception imprévue dans le fil de lecture du flux d'évènements (recherche).",
                exc_info=True,
            )
            if self._game_log is not None:
                self._game_log.exception(exc, context="fil de lecture du flux d'évènements (recherche)")
            if not self._cancelled and not self._found:
                self._events.put({"type": "error", "reason": type(exc).__name__})

    def _read_seek_stream(self) -> None:
        try:
            for _line in self._seek_handle.lines():
                self._events.put({"type": "waiting"})
        except (TransportNetworkError, TransportTimeoutError) as exc:
            if not self._cancelled and not self._found:
                self._push_error(exc, "flux de recherche (coupure)")
            return
        except Exception as exc:
            logger.error(
                "Lichess : exception imprévue dans le fil de lecture du flux de recherche.",
                exc_info=True,
            )
            if self._game_log is not None:
                self._game_log.exception(exc, context="fil de lecture du flux de recherche")
            if not self._cancelled and not self._found:
                self._events.put({"type": "error", "reason": type(exc).__name__})
            return
        # Flux de recherche fermé par Lichess — appariement (le flux
        # d'évènements porte alors gameStart, déjà géré ci-dessus, mais rien
        # ne garantit qu'il soit déjà arrivé à cet instant précis, voir
        # en-tête de module) ou recherche annulée par cancel()/close()
        # (self._cancelled déjà vrai dans ce cas). Si ni l'un ni l'autre,
        # c'est Lichess qui a clos la recherche de son côté — appariement
        # dont gameStart n'est pas encore arrivé, ou réellement aucun
        # adversaire : à l'appelant de patienter puis de trancher (issue
        # #328, point 2 ; _run_lichess_human, game_manager_modes/lichess.py)
        # — ce module ne ferme jamais lui-même le flux d'évènements ici, pour
        # ne jamais manquer un gameStart encore en transit.
        with self._lock:
            already_resolved = self._cancelled or self._found
        if not already_resolved:
            logger.info("Lichess : flux de recherche fermé par Lichess sans appariement signalé.")
            self._events.put({"type": "seek_closed"})

    def next_event(self, timeout: float = 0.2):
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def cancel(self) -> None:
        """Annulation explicite demandée par l'utilisateur (bouton
        "Annuler la recherche") — ferme les deux flux et le journalise
        comme telle. Idempotent, sans effet si déjà close()/cancel()ée ou
        si un adversaire a déjà été trouvé."""
        if self._cancelled or self._found:
            return
        self._cancelled = True
        logger.info("Lichess : recherche d'adversaire annulée par l'utilisateur.")
        if self._game_log is not None:
            self._game_log.state_change("recherche d'adversaire annulée par l'utilisateur.")
        self._close_streams()

    def close(self) -> None:
        """Fermeture interne des deux flux — fin normale (adversaire
        trouvé), erreur, ou conclusion décidée par l'appelant après la
        période d'attente qui suit un "seek_closed" (adversaire adopté
        depuis la liste des parties en cours, ou recherche vraiment
        terminée sans adversaire, issue #328 point 2). Contrairement à
        cancel(), ne journalise PAS "annulée par l'utilisateur" : chaque
        appelant a déjà journalisé la cause réelle avec son propre message
        (point 4) avant d'appeler close(). Idempotent."""
        if self._cancelled or self._found:
            return
        self._cancelled = True
        self._close_streams()

    def _close_streams(self) -> None:
        if self._seek_handle is not None:
            self._seek_handle.close()
        if self._event_handle is not None:
            self._event_handle.close()
