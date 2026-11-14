"""
nicsoft/modes/lichess/game_client.py — AlChess

Client de partie Lichess (issue #307, étape L1) : créer une partie contre
l'IA, lire le flux d'une partie en cours, jouer un coup, abandonner,
annuler, répondre à une proposition de nulle. Couche de communication
seule — aucun mode de jeu, aucun moteur, aucun écran de partie ici.

Transport réseau injectable (voir transport.py) : les tests passent un
faux transport scénarisé, jamais de vrai réseau. N'importe jamais
nicsoft.web (ARC-001).

Le jeton n'est jamais journalisé ni inclus dans une exception — seuls les
codes HTTP et les messages déjà renvoyés par Lichess le sont (voir
errors.py).

Une seule requête "ordinaire" (hors lecture de flux) à la fois par
instance, via un verrou — ne bloque jamais la lecture du flux, qui est un
générateur indépendant.
"""

import json
import threading
import time

from nicsoft.modes.lichess.errors import (
    LichessApiError,
    LichessAuthError,
    LichessNetworkError,
    LichessRateLimitError,
    extract_api_message,
)
from nicsoft.modes.lichess.transport import (
    TransportHTTPError,
    TransportNetworkError,
    TransportTimeoutError,
    UrllibTransport,
)

API_BASE = "https://lichess.org/api"

# Statuts de partie terminée (documentation officielle Lichess).
FINISHED_STATUSES = frozenset({
    "aborted", "mate", "resign", "stalemate", "timeout", "draw", "outoftime",
    "cheat", "noStart", "unknownFinish", "insufficientMaterialClaim", "variantEnd",
})

_KNOWN_EVENT_TYPES = frozenset({"gameFull", "gameState", "chatLine", "opponentGone"})

# Attentes croissantes de reprise après une coupure (secondes) — jamais de
# boucle sans attente.
RECONNECT_DELAYS_S = (1, 2, 4, 8, 30)


def _raise_for_transport_error(exc) -> None:
    """Traduit une erreur de transport en erreur typée Lichess. Ne lève
    jamais rien contenant le jeton (le transport ne le lui a pas transmis)."""
    if isinstance(exc, TransportHTTPError):
        if exc.status_code in (401, 403):
            raise LichessAuthError(exc.status_code) from None
        if exc.status_code == 429:
            raise LichessRateLimitError(exc.retry_after_s or 60) from None
        raise LichessApiError(exc.status_code, extract_api_message(exc.body)) from None
    raise LichessNetworkError("réseau indisponible") from None


def _url_tail(url: str) -> str:
    """Partie de l'URL après API_BASE, pour le journal dédié de partie —
    jamais le jeton (envoyé uniquement dans l'en-tête, jamais dans l'URL)."""
    return url[len(API_BASE):] if url.startswith(API_BASE) else url


_LOG_BODY_TRUNCATE = 500


def _describe_transport_error(exc) -> str:
    """Détail à écrire dans le journal de partie dédié (issue #329, point
    1, catégorie "requête") — code HTTP, Retry-After s'il existe, corps
    tronqué à ~500 caractères (jamais au-delà, jamais le jeton — absent de
    ce corps, envoyé uniquement dans l'en-tête Authorization). Pour une
    erreur réseau pure (pas de réponse HTTP de Lichess), seul le type
    d'exception est disponible."""
    if isinstance(exc, TransportHTTPError):
        detail = f"erreur HTTP {exc.status_code}"
        if exc.retry_after_s is not None:
            detail += f" (Retry-After={exc.retry_after_s}s)"
        body = (exc.body or "")[:_LOG_BODY_TRUNCATE].replace("\n", " ").replace("\r", " ").strip()
        detail += f" corps={body or '(vide)'}"
        return detail
    return f"erreur {type(exc).__name__}"


class GameClient:
    """Client de partie pour un jeton donné. `transport` est injectable
    (faux transport dans les tests, `UrllibTransport()` en production).

    `game_log` (issue #326, point 10) : journal dédié de la partie en
    cours — optionnel (None par défaut, aucun effet), attaché via
    `attach_game_log()` dès que l'identifiant de partie est connu
    (game_manager_modes/lichess.py). Journalise chaque requête envoyée
    (coup, nulle, abandon...) et chaque ligne brute du flux, jamais le
    jeton ni le tchat (voir game_log.py)."""

    def __init__(self, token: str, transport=None, game_log=None):
        self._token = token
        self._transport = transport or UrllibTransport()
        self._lock = threading.Lock()
        self._game_log = game_log

    def attach_game_log(self, game_log) -> None:
        self._game_log = game_log

    def _request(self, method: str, url: str, fields: dict | None = None) -> bytes:
        start = time.monotonic()
        try:
            with self._lock:
                result = self._transport.request(method, url, self._token, fields)
        except (TransportHTTPError, TransportNetworkError, TransportTimeoutError) as exc:
            if self._game_log is not None:
                self._game_log.request(
                    method, _url_tail(url), _describe_transport_error(exc), time.monotonic() - start,
                )
            _raise_for_transport_error(exc)
        else:
            if self._game_log is not None:
                self._game_log.request(method, _url_tail(url), "ok", time.monotonic() - start)
            return result

    # ── Actions ──────────────────────────────────────────────────────────

    def create_ai_game(self, level: int, clock_limit_s: int, clock_increment_s: int, color: str = "") -> dict:
        """POST /api/challenge/ai — retourne le JSON de réponse (contient
        au moins `id`)."""
        fields = {
            "level": level,
            "clock.limit": clock_limit_s,
            "clock.increment": clock_increment_s,
        }
        if color:
            fields["color"] = color
        body = self._request("POST", f"{API_BASE}/challenge/ai", fields)
        return json.loads(body.decode("utf-8"))

    def play_move(self, game_id: str, uci: str, offer_draw: bool = False) -> None:
        url = f"{API_BASE}/board/game/{game_id}/move/{uci}"
        if offer_draw:
            url += "?offeringDraw=true"
        self._request("POST", url)

    def resign(self, game_id: str) -> None:
        self._request("POST", f"{API_BASE}/board/game/{game_id}/resign")

    def abort(self, game_id: str) -> None:
        self._request("POST", f"{API_BASE}/board/game/{game_id}/abort")

    def answer_draw(self, game_id: str, accept: bool) -> None:
        choice = "yes" if accept else "no"
        self._request("POST", f"{API_BASE}/board/game/{game_id}/draw/{choice}")

    def answer_takeback(self, game_id: str, accept: bool) -> None:
        """POST /api/board/game/{gameId}/takeback/{yes|no} (issue #334,
        point 5) — l'échiquier physique ne peut pas défaire un coup :
        AlChess n'appelle jamais ceci avec accept=True pour une demande
        venant de l'adversaire (voir game.py::_check_opponent_takeback)."""
        choice = "yes" if accept else "no"
        self._request("POST", f"{API_BASE}/board/game/{game_id}/takeback/{choice}")

    def claim_victory(self, game_id: str) -> None:
        """POST /api/board/game/{gameId}/claim-victory (issue #334, point
        2) — doc officielle lichess-org/api (doc/specs/tags/board/
        api-board-game-gameId-claim-victory.yaml, lue le 14/11/2026) :
        valable seulement après qu'un événement `opponentGone` du flux a
        annoncé `gone=true` et que `claimWinInSeconds` secondes se sont
        écoulées depuis — Lichess répond 400 sinon (voir game.py)."""
        self._request("POST", f"{API_BASE}/board/game/{game_id}/claim-victory")

    def claim_draw(self, game_id: str) -> None:
        """POST /api/board/game/{gameId}/claim-draw (issue #334, point 3) —
        même doc que claim_victory ci-dessus, même condition de délai."""
        self._request("POST", f"{API_BASE}/board/game/{game_id}/claim-draw")

    # ── Recherche d'un adversaire humain (issue #327, points 2/3) ────────

    def _open_stream_logged(self, method: str, url: str, fields: dict | None = None):
        """Enveloppe open_stream() pour écrire, en plus du journal général
        (déjà fait par transport.py), le détail dans le journal de partie
        dédié (issue #329, point 1, catégorie "requête") — seule
        différence avec `_request()` : la StreamHandle, pas un contenu lu
        en entier, est retournée en cas de succès ; relève l'exception de
        transport telle quelle en cas d'échec (seek.py en a besoin pour
        distinguer les causes — jamais la version traduite LichessApiError
        ici, contrairement à `_request()`)."""
        start = time.monotonic()
        try:
            handle = self._transport.open_stream(method, url, self._token, fields)
        except (TransportHTTPError, TransportNetworkError, TransportTimeoutError) as exc:
            if self._game_log is not None:
                self._game_log.request(
                    method, _url_tail(url), _describe_transport_error(exc), time.monotonic() - start,
                )
            raise
        if self._game_log is not None:
            self._game_log.request(method, _url_tail(url), "ok (flux ouvert)", time.monotonic() - start)
        return handle

    def open_event_stream(self):
        """GET /api/stream/event — flux général d'évènements du compte
        (gameStart/gameFinish/challenge...), à ouvrir AVANT le flux de
        recherche (voir open_seek_stream) pour ne jamais manquer un
        appariement immédiat (recommandation officielle de la doc board/
        seek). Retourne une StreamHandle annulable (transport.py)."""
        return self._open_stream_logged("GET", f"{API_BASE}/stream/event")

    def open_seek_stream(self, clock_limit_minutes, clock_increment_s: int, color: str = "", rated: bool = False):
        """POST /api/board/seek — recherche publique d'un adversaire humain
        en temps réel. La réponse reste ouverte (lignes vides périodiques)
        tant que la recherche est active ; fermer la StreamHandle retournée
        (voir transport.py) annule réellement la recherche côté Lichess.
        `clock_limit_minutes` est en MINUTES (paramètre `time` de l'API,
        contrairement au reste de ce module qui travaille en secondes) —
        voir doc/specs/tags/board/api-board-seek.yaml, lue le 14/11/2026."""
        fields = {
            "time": clock_limit_minutes,
            "increment": clock_increment_s,
            "rated": "true" if rated else "false",
        }
        if color:
            fields["color"] = color
        return self._open_stream_logged("POST", f"{API_BASE}/board/seek", fields)

    # ── Flux ─────────────────────────────────────────────────────────────

    def stream_game(self, game_id: str, sleep=time.sleep):
        """Générateur d'événements décodés (gameFull, gameState, chatLine,
        opponentGone) — lignes vides et types inconnus ignorés.

        En cas de coupure réseau en cours de partie, reprend la lecture
        avec des attentes croissantes (RECONNECT_DELAYS_S), en signalant
        {"type": "reconnecting", "attempt": n, "delay_s": d} puis
        {"type": "reconnected"} dès qu'une ligne arrive à nouveau ; un
        nouveau gameFull reçu à la reprise est un état complet qui
        remplace tout l'état local côté appelant. S'arrête quand le flux
        se ferme normalement ou quand le statut de la partie est terminé
        — ne boucle jamais sans attente."""
        url = f"{API_BASE}/board/game/stream/{game_id}"
        last_status = None
        attempt = 0
        while True:
            try:
                for line in self._transport.stream_lines(url, self._token):
                    if attempt > 0:
                        attempt = 0
                        if self._game_log is not None:
                            self._game_log.connectivity("flux de partie reconnecté.")
                        yield {"type": "reconnected"}
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        if self._game_log is not None:
                            self._game_log.raw(line)
                        continue
                    if self._game_log is not None:
                        if event.get("type") == "chatLine":
                            self._game_log.chat_ignored()
                        else:
                            self._game_log.raw(line)
                    etype = event.get("type")
                    if etype not in _KNOWN_EVENT_TYPES:
                        continue
                    if etype == "gameFull":
                        last_status = (event.get("state") or {}).get("status")
                    elif etype == "gameState":
                        last_status = event.get("status")
                    yield event
                    if last_status in FINISHED_STATUSES:
                        return
                return  # flux fermé normalement par Lichess
            except TransportHTTPError as exc:
                _raise_for_transport_error(exc)
            except (TransportNetworkError, TransportTimeoutError):
                if last_status in FINISHED_STATUSES:
                    return
                delay = RECONNECT_DELAYS_S[min(attempt, len(RECONNECT_DELAYS_S) - 1)]
                attempt += 1
                if self._game_log is not None:
                    self._game_log.connectivity(
                        f"flux de partie coupé — tentative {attempt}, nouvel essai dans {delay}s."
                    )
                yield {"type": "reconnecting", "attempt": attempt, "delay_s": delay}
                sleep(delay)
                continue


# ── Fonctions utilitaires pures ─────────────────────────────────────────────

def moves_from_state(state: dict) -> list:
    """Liste des coups UCI depuis le champ `moves` (espaces) d'un
    gameState, ou de `state` au sein d'un gameFull."""
    moves = (state or {}).get("moves", "") or ""
    return moves.split() if moves else []


def side_to_move(state: dict) -> str:
    """'white' ou 'black', déduit de la parité du nombre de coups joués."""
    return "black" if len(moves_from_state(state)) % 2 == 1 else "white"


def is_game_over(status: str) -> bool:
    return status in FINISHED_STATUSES


def result_text(status: str, winner: str = "", user_color: str = "") -> str:
    """Texte lisible (français) du résultat d'une partie terminée."""
    if status == "mate":
        if not winner:
            return "Échec et mat"
        return "Victoire par échec et mat" if winner == user_color else "Défaite par échec et mat"
    if status == "resign":
        if not winner:
            return "Abandon"
        return "Victoire par abandon de l'adversaire" if winner == user_color else "Défaite par abandon"
    if status in ("timeout", "outoftime"):
        if not winner:
            return "Temps dépassé"
        return "Victoire au temps" if winner == user_color else "Défaite au temps"
    if status == "stalemate":
        return "Nulle par pat"
    if status == "draw":
        return "Nulle"
    if status == "aborted":
        return "Partie annulée"
    if status == "cheat":
        return "Partie arrêtée (triche détectée)"
    if status == "noStart":
        return "Partie non commencée"
    if status in ("unknownFinish", "insufficientMaterialClaim", "variantEnd"):
        return "Partie terminée"
    return "Partie en cours"
