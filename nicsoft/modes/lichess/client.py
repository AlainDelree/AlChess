"""
nicsoft/modes/lichess/client.py — AlChess
Client HTTP minimal pour Lichess (étape L0, issue #306) : vérifie qu'un
jeton personnel est valide et quels droits (scopes) il porte, via la route
officielle de test des jetons. Base pour les étapes suivantes de
communication avec Lichess (parties, etc.) — n'importe jamais nicsoft.web.

Le jeton n'apparaît jamais dans un journal ni dans un message d'exception :
seules les constantes ci-dessous (adresse, statuts) sont journalisées/
retournées, jamais le contenu de `token`.
"""

import json
import urllib.error
import urllib.request

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
