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
# Issue #351, étape L3 : droits exigés par l'API Puzzle (doc officielle
# lichess-org/api, spec OpenAPI https://lichess.org/openapi.yaml, lue le
# 16/11/2026 — operationId apiPuzzleNext : security puzzle:read ;
# apiPuzzleBatchSolve : security puzzle:write). Distincts de board:play —
# le jeton d'Alain (droit de jouer seulement) doit être recréé avec ces
# deux droits supplémentaires pour accéder aux problèmes (voir
# puzzle_client.py et le rapport de clôture).
PUZZLE_READ_SCOPE = "puzzle:read"
PUZZLE_WRITE_SCOPE = "puzzle:write"

_TIMEOUT_S = 10
# Délai court (issue #323, point 1) : cet appel se fait à l'ouverture du
# menu Lichess (une seule fois, jamais en boucle) et ne doit jamais retarder
# longtemps l'affichage de l'écran si Lichess répond lentement.
_PLAYING_TIMEOUT_S = 6
_MAX_RESPONSE_BYTES = 65536

# Issue #325, point 1 : seul le type de cadence ("speed", distinct de la
# source ou de la variante) distingue de façon fiable une partie en temps
# réel — même très longue (ex. classique 90+30, cadence qu'Alain veut
# surtout jouer) — d'une partie par correspondance (délai en jours par
# coup, qui durerait des jours et bloquerait AlChess indéfiniment si elle
# comptait comme « en cours »). Valeurs officielles du champ `speed`
# (doc/specs/schemas/Speed.yaml, dépôt lichess-org/api, lu le 14/11/2026via
# `gh api search/code` + lecture du fichier) : ultraBullet, bullet, blitz,
# rapid, classical, correspondence — seule la dernière est ignorée ici.
_IGNORED_SPEED = "correspondence"

# "Reprenable" (issue #325 point 3 ; étendu aux parties humaines par
# l'issue #333, point 1) : seule la variante standard est reprise par
# LichessGame aujourd'hui — les autres (Chess960, Horde...) restent
# listées (pour qu'Alain les termine) mais affichées avec l'explication
# « variante non standard » côté interface, jamais masquées.
_RESUMABLE_VARIANT = "standard"

# Compatibilité avec l'API Board (issue #333, point 1) : établie par
# lecture du code source public de lila (dépôt GitHub lichess-org/lila,
# lu le 14/11/2026) — `app/controllers/PlayApi.scala::WithPovAsBoard`
# refuse (HTTP 400, "This game cannot be played with the Board API.")
# toute partie pour laquelle `lila.game.Game.isBoardCompatible(game)` est
# faux, AVANT d'exécuter le moindre coup ou flux Board — cette règle
# s'applique donc à TOUTE partie du compte, quelle que soit son origine
# (AlChess, lichess.org, téléphone), site ou application : rien dans le
# code ni la documentation officielle (lichess-org/api,
# doc/specs/lichess-api.yaml, tag Board : « Time controls: Rapid,
# Classical and Correspondence only ») ne distingue le site web de
# l'application mobile — seules la CADENCE et, pour le blitz, la SOURCE
# de la partie comptent. Règle exacte lue dans
# `modules/game/src/main/Game.scala::isBoardCompatible` +
# `modules/core/src/main/game/misc.scala::isBoardCompatible(Clock.Config)` :
#
#   game.clockConfig.forall(c =>
#     Speed(c) >= Speed.Rapid
#     || ((game.hasAi || source == Friend || source == Api) && Speed(c) >= Speed.Blitz)
#   )
#
# — une partie SANS pendule (correspondance) satisfait toujours ce test
# (`forall` sur `None`), mais ces parties sont déjà écartées plus haut
# (_IGNORED_SPEED) : hors sujet ici. Pour les parties à pendule restantes :
#   - rapid/classical  : toujours reprenable, quelle que soit la source ;
#   - blitz            : reprenable seulement si créée par un défi direct
#                         ("friend") ou via l'API ("api") — PAS depuis le
#                         lobby/un pool/un tournoi/arena/swiss ;
#   - bullet/ultraBullet : jamais reprenable (aucune exception, même IA).
_BOARD_SPEEDS_ALWAYS = frozenset({"rapid", "classical"})
_BOARD_SPEED_AT_BLITZ = "blitz"
_BOARD_SOURCES_AT_BLITZ = frozenset({"friend", "api"})


def _is_board_compatible(speed: str, source: str, is_ai: bool) -> bool:
    """`True` si Lichess accepterait un coup/flux Board API pour une
    partie de cette cadence/source — voir commentaire ci-dessus pour les
    références exactes. Pure, sans effet de bord, testable sans réseau."""
    if speed in _BOARD_SPEEDS_ALWAYS:
        return True
    if speed == _BOARD_SPEED_AT_BLITZ:
        return bool(is_ai) or source in _BOARD_SOURCES_AT_BLITZ
    return False


def _user_agent() -> str:
    try:
        from importlib.metadata import version
        return f"AlChess/{version('alchess')}"
    except Exception:
        return "AlChess/0.0.0"


def test_token(token: str) -> dict:
    """Interroge /api/token/test avec `token`. Retourne un dict :
      {"status": "ok", "account": str, "scopes": [str, ...], "has_board_play": bool,
       "has_puzzle_read": bool, "has_puzzle_write": bool}
      {"status": "invalid"}
      {"status": "rate_limited"}
      {"status": "network_error"}

    `has_puzzle_read`/`has_puzzle_write` (issue #351, étape L3) : utilisés
    par le menu « Problèmes Lichess » pour détecter un jeton valide mais
    sans les droits des problèmes (voir puzzle_client.py) — jamais un appel
    séparé, ce test de jeton existant suffit à connaître tous les droits.
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
        "has_puzzle_read": PUZZLE_READ_SCOPE in scopes,
        "has_puzzle_write": PUZZLE_WRITE_SCOPE in scopes,
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
    """GET /api/account/playing (issue #323, étape L2b, point 1 ; étendu à
    toutes les parties en cours par l'issue #325, point 1) — détecte les
    parties Lichess en cours du compte, quelle que soit leur origine
    (AlChess, lichess.org, téléphone), à l'ouverture du menu Lichess et
    juste avant la création d'une nouvelle partie (jamais en boucle).

    Même jeton que les autres appels, aucun droit (scope OAuth)
    supplémentaire : la spécification officielle lichess-org/api (dépôt
    GitHub, fichier doc/specs/tags/games/api-account-playing.yaml, lu le
    13/11/2026) ne déclare que `security: [{OAuth2: []}]` sans scope nommé
    sur cette route — contrairement à /api/challenge/ai qui exige
    board:play. Délai d'attente court (_PLAYING_TIMEOUT_S) : cet appel ne
    doit jamais retarder longtemps l'affichage de l'écran de menu.

    Seules les parties par correspondance sont ignorées (_IGNORED_SPEED
    ci-dessus) : une partie en temps réel, même très longue (classique
    90+30, par exemple), reste une candidate normale. Toutes les autres
    parties en cours sont retournées (contre l'IA ou contre un humain,
    créée par AlChess ou ailleurs — lichess.org, téléphone —, variante non
    standard...), avec un indicateur `resumable` (True pour toute partie en
    variante standard que l'interface Board de Lichess accepterait de
    jouer — voir `_is_board_compatible` ci-dessus, issue #333 point 1) et
    `unresumable_reason` ("variant"/"speed"/None) expliquant pourquoi une
    partie non reprenable l'est : à l'appelant de les afficher toutes
    (issue #325, point 2/3) plutôt que d'en masquer certaines
    silencieusement. Lichess classe `nowPlaying` par urgence (« most urgent
    games are listed first », doc officielle) — l'ordre de la liste
    retournée ci-dessous conserve cet ordre.

    Retourne :
      {"status": "ok", "games": [{...}, ...], "total": int}  — total == len(games)
      {"status": "invalid"}        — jeton absent ou refusé (401/403)
      {"status": "rate_limited"}   — 429
      {"status": "network_error"}  — pas de réseau ou réponse inattendue

    Jamais de message alarmant pour l'appelant en cas de "invalid"/
    "rate_limited"/"network_error" (issue #323, point 1) : ces statuts ne
    font simplement apparaître aucune partie en cours.
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
        if isinstance(g, dict) and g.get("gameId") and g.get("speed") != _IGNORED_SPEED
    ]
    games = []
    for g in candidates:
        opponent = g.get("opponent") or {}
        ai_level = opponent.get("ai")
        speed = g.get("speed", "")
        source = g.get("source", "")
        variant_ok = (g.get("variant") or {}).get("key") == _RESUMABLE_VARIANT
        speed_ok = _is_board_compatible(speed, source, ai_level is not None)
        # Raison exacte affichée côté interface (issue #333, point 1) —
        # la variante est vérifiée en premier : une partie en variante non
        # standard reste de toute façon hors de portée de LichessGame,
        # indépendamment de sa cadence.
        if variant_ok and speed_ok:
            reason = None
        elif not variant_ok:
            reason = "variant"
        else:
            reason = "speed"
        games.append({
            "game_id": g.get("gameId", ""),
            "color": g.get("color", ""),
            "opponent": opponent.get("username") or opponent.get("id") or "",
            "ai_level": ai_level,
            "speed": speed,
            "is_my_turn": bool(g.get("isMyTurn")),
            "seconds_left": g.get("secondsLeft"),
            "resumable": reason is None,
            "unresumable_reason": reason,
        })
    return {"status": "ok", "games": games, "total": len(games)}
