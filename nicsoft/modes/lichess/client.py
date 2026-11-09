"""
nicsoft/modes/lichess/client.py — AlChess
Client HTTP minimal pour Lichess : vérifie qu'un jeton personnel est
valide et quels droits (scopes) il porte, via la route officielle de test
des jetons (étape L0, issue #306). `test_ai_game` (étape L1, issue #307)
fait le même office pour le bouton « Tester une partie » des paramètres :
crée une vraie partie amicale contre l'IA Lichess niveau 1, lit le premier
état complet, puis l'annule — sans lancer aucun moteur ni mode de jeu. La
communication de partie elle-même (créer, lire le flux, jouer, abandonner,
annuler, nulle) vit dans game_client.py ; ce module n'importe jamais
nicsoft.web.

Le jeton n'apparaît jamais dans un journal ni dans un message d'exception :
seules les constantes ci-dessous (adresse, statuts) sont journalisées/
retournées, jamais le contenu de `token`.
"""

import json
import urllib.error
import urllib.request

from nicsoft.modes.lichess.errors import (
    LichessApiError,
    LichessAuthError,
    LichessNetworkError,
    LichessRateLimitError,
)
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.utils.net_safety import ensure_https

TOKEN_TEST_URL = "https://lichess.org/api/token/test"
BOARD_PLAY_SCOPE = "board:play"

_TIMEOUT_S = 10
_MAX_RESPONSE_BYTES = 65536


def _user_agent() -> str:
    try:
        from importlib.metadata import version
        return f"AlChess/{version('alchess')}"
    except Exception:
        return "AlChess/0.0.0"


def test_token(token: str) -> dict:
    """Interroge /api/token/test avec `token`. Retourne un dict :
      {"status": "ok", "account": str, "scopes": [str, ...], "has_board_play": bool}
      {"status": "invalid"}
      {"status": "rate_limited"}
      {"status": "network_error"}
    """
    ensure_https(TOKEN_TEST_URL)
    req = urllib.request.Request(
        TOKEN_TEST_URL,
        data=token.encode("utf-8"),
        headers={
            "Content-Type": "text/plain",
            "User-Agent": _user_agent(),
        },
        method="POST",
    )
    try:
        # Adresse constante en https, vérifiée par ensure_https ci-dessus
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310  # nosec B310
            raw = resp.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return {"status": "rate_limited"}
        return {"status": "network_error"}
    except urllib.error.URLError:
        return {"status": "network_error"}

    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"status": "network_error"}

    entry = data.get(token) if isinstance(data, dict) else None
    if not entry:
        return {"status": "invalid"}

    scopes_raw = entry.get("scopes", "") or ""
    scopes = [s for s in scopes_raw.split(",") if s]
    return {
        "status": "ok",
        "account": entry.get("userId", ""),
        "scopes": scopes,
        "has_board_play": BOARD_PLAY_SCOPE in scopes,
    }


def test_ai_game(token: str, transport=None) -> dict:
    """Crée une vraie partie amicale contre l'IA Lichess (niveau 1, quinze
    minutes sans incrément, couleur aléatoire), lit le premier événement
    gameFull du flux, puis annule la partie (ou l'abandonne si
    l'annulation est refusée), et vide le flux jusqu'à sa fermeture.
    Utilisé uniquement par le bouton « Tester une partie » des paramètres
    (issue #307, étape L1) — jamais appelé pendant une vraie partie.

    `transport` permet d'injecter un faux transport dans les tests
    (jamais de connexion réelle à Lichess depuis la suite de tests).

    Retourne :
      {"status": "ok", "game_id": str, "color": "white"|"black", "opponent": str}
      {"status": "invalid"}        — jeton absent ou refusé (401)
      {"status": "missing_scope"}  — jeton valide mais sans board:play (403)
      {"status": "rate_limited"}
      {"status": "network_error"}
    """
    if not token:
        return {"status": "invalid"}

    client = GameClient(token, transport=transport)
    try:
        created = client.create_ai_game(level=1, clock_limit_s=900, clock_increment_s=0, color="")
        game_id = created.get("id", "")
        stream = client.stream_game(game_id)

        full = None
        for event in stream:
            if event.get("type") == "gameFull":
                full = event
                break
        if full is None:
            return {"status": "network_error"}

        white = full.get("white") or {}
        black = full.get("black") or {}
        if white.get("aiLevel") is not None:
            color, opponent = "black", white.get("name") or white.get("id", "")
        else:
            color, opponent = "white", black.get("name") or black.get("id", "")

        try:
            client.abort(game_id)
        except LichessApiError:
            client.resign(game_id)

        for _event in stream:
            pass  # vide le flux jusqu'à sa fermeture normale (statut terminé)

        return {"status": "ok", "game_id": game_id, "color": color, "opponent": opponent}
    except LichessAuthError as exc:
        return {"status": "missing_scope"} if exc.status_code == 403 else {"status": "invalid"}
    except LichessRateLimitError:
        return {"status": "rate_limited"}
    except (LichessNetworkError, LichessApiError):
        return {"status": "network_error"}
