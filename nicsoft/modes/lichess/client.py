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
PLAYING_GAMES_URL = "https://lichess.org/api/account/playing"
BOARD_PLAY_SCOPE = "board:play"

_TIMEOUT_S = 10
# Délai court (issue #323, point 1) : cet appel se fait à l'ouverture du
# menu Lichess (une seule fois, jamais en boucle) et ne doit jamais retarder
# longtemps l'affichage de l'écran si Lichess répond lentement.
_PLAYING_TIMEOUT_S = 6
_MAX_RESPONSE_BYTES = 65536

# Issue #323 : source/variante proposées à la reprise dans cette livraison.
# « Cas le plus simple » explicitement permis par la consigne en repli — une
# partie amicale contre l'IA Lichess en échecs standard. Les parties
# humain-humain et de variante restent à faire (voir rapport de clôture).
_RESUMABLE_SOURCE = "ai"
_RESUMABLE_VARIANT = "standard"


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


def get_ongoing_games(token: str) -> dict:
    """GET /api/account/playing (issue #323, étape L2b, point 1) — détecte
    une partie Lichess en cours à reprendre, à l'ouverture du menu Lichess
    uniquement (jamais en boucle).

    Même jeton que les autres appels, aucun droit (scope OAuth)
    supplémentaire : la spécification officielle lichess-org/api (dépôt
    GitHub, fichier doc/specs/tags/games/api-account-playing.yaml, lu le
    13/11/2026) ne déclare que `security: [{OAuth2: []}]` sans scope nommé
    sur cette route — contrairement à /api/challenge/ai qui exige
    board:play. Délai d'attente court (_PLAYING_TIMEOUT_S) : cet appel ne
    doit jamais retarder longtemps l'affichage de l'écran de menu.

    Ne propose à la reprise que les parties amicales contre l'IA Lichess en
    variante standard (_RESUMABLE_SOURCE/_RESUMABLE_VARIANT ci-dessus) —
    seul cas livré dans cette étape (voir rapport de clôture pour les
    parties humain-humain/correspondance, qui restent à faire). Lichess
    classe `nowPlaying` par urgence (« most urgent games are listed first »,
    doc officielle) — en l'absence d'horodatage de création dans cette
    réponse, c'est la meilleure approximation disponible de « la partie la
    plus récente » sans appel réseau supplémentaire (voir rapport).

    Retourne :
      {"status": "ok", "game": {...} | None, "total_candidates": int}
      {"status": "invalid"}        — jeton absent ou refusé (401/403)
      {"status": "rate_limited"}   — 429
      {"status": "network_error"}  — pas de réseau ou réponse inattendue

    Jamais de message alarmant pour l'appelant en cas de "invalid"/
    "rate_limited"/"network_error" (issue #323, point 1) : ces statuts ne
    font simplement pas apparaître de proposition de reprise.
    """
    if not token:
        return {"status": "invalid"}
    ensure_https(PLAYING_GAMES_URL)
    req = urllib.request.Request(
        PLAYING_GAMES_URL,
        headers={"Authorization": f"Bearer {token}", "User-Agent": _user_agent()},
        method="GET",
    )
    try:
        # Adresse constante en https, vérifiée par ensure_https ci-dessus.
        with urllib.request.urlopen(req, timeout=_PLAYING_TIMEOUT_S) as resp:  # noqa: S310  # nosec B310
            raw = resp.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return {"status": "rate_limited"}
        if exc.code in (401, 403):
            return {"status": "invalid"}
        return {"status": "network_error"}
    except urllib.error.URLError:
        return {"status": "network_error"}

    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"status": "network_error"}
    if not isinstance(data, dict):
        return {"status": "network_error"}

    candidates = [
        g for g in (data.get("nowPlaying") or [])
        if isinstance(g, dict)
        and g.get("source") == _RESUMABLE_SOURCE
        and (g.get("variant") or {}).get("key") == _RESUMABLE_VARIANT
        and g.get("gameId")
    ]
    if not candidates:
        return {"status": "ok", "game": None, "total_candidates": 0}

    chosen = candidates[0]  # ordre Lichess : la partie la plus urgente d'abord
    opponent = chosen.get("opponent") or {}
    return {
        "status": "ok",
        "total_candidates": len(candidates),
        "game": {
            "game_id": chosen.get("gameId", ""),
            "color": chosen.get("color", ""),
            "opponent": opponent.get("username") or opponent.get("id") or "",
            "ai_level": opponent.get("ai"),
            "speed": chosen.get("speed", ""),
            "is_my_turn": bool(chosen.get("isMyTurn")),
            "seconds_left": chosen.get("secondsLeft"),
        },
    }
