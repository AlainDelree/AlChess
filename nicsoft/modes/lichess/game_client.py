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
            raise LichessRateLimitError() from None
        raise LichessApiError(exc.status_code, _extract_api_message(exc.body)) from None
    raise LichessNetworkError("réseau indisponible") from None


def _extract_api_message(body: str) -> str:
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return ""
    if isinstance(data, dict):
        return str(data.get("error", "") or "")
    return ""


class GameClient:
    """Client de partie pour un jeton donné. `transport` est injectable
    (faux transport dans les tests, `UrllibTransport()` en production)."""

    def __init__(self, token: str, transport=None):
        self._token = token
        self._transport = transport or UrllibTransport()
        self._lock = threading.Lock()

    def _request(self, method: str, url: str, fields: dict | None = None) -> bytes:
        with self._lock:
            try:
                return self._transport.request(method, url, self._token, fields)
            except (TransportHTTPError, TransportNetworkError, TransportTimeoutError) as exc:
                _raise_for_transport_error(exc)

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
                        yield {"type": "reconnected"}
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
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
