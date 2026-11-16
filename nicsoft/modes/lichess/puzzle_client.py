"""
nicsoft/modes/lichess/puzzle_client.py — AlChess

Lecture du problème (puzzle) Lichess suivant et envoi de son résultat
(issue #351, étape L3 — plan Lichess). Deux appels ponctuels, jamais un
flux : implémenté en urllib direct, comme client.py, plutôt que via
transport.py (réservé aux échanges de game_client.py). Mêmes règles que le
reste du module Lichess : https uniquement (ensure_https), délais
d'attente courts, jeton jamais journalisé ni inclus dans une exception,
erreurs réseau/HTTP toujours renvoyées comme un statut clair, jamais une
exception brute qui remonterait jusqu'à l'appelant.

Documentation officielle consultée le 16/11/2026 (aucun appel réel,
lecture seule) : spec OpenAPI https://lichess.org/openapi.yaml, dépôt
GitHub lichess-org/api (doc/specs/tags/puzzles/*.yaml,
doc/specs/schemas/Puzzle*.yaml) :

  - GET /api/puzzle/next (operationId apiPuzzleNext, security
    puzzle:read) : "If authenticated, only returns puzzles that the user
    has never seen before." Paramètres facultatifs : angle, difficulty
    (easiest/easier/normal/harder/hardest — relatif à la cote de
    problèmes de l'utilisateur), color. Réponse : {"game": {...}, "puzzle":
    {...}} — voir parse_puzzle_payload() ci-dessous pour le détail exact
    des champs utilisés.
  - POST /api/puzzle/batch/{angle} (operationId apiPuzzleBatchSolve,
    security puzzle:write) : corps JSON {"solutions": [{"id", "win",
    "rated"}], "nb": int}. "nb" contrôle le nombre de NOUVEAUX problèmes
    renvoyés dans la même réponse (0 ici : AlChess redemande toujours un
    problème séparément via /next, jamais par ce lot). Réponse :
    {"rounds": [{"id","win","ratingDiff"}], "glicko": {"rating",
    "deviation","provisional"}, "puzzles": [...]}. `angle="mix"` (tous
    thèmes) — seul le type de problème attendu par ce chemin, pas son
    thème réel (soumis via l'id).
  - Aucune mention officielle du comportement attendu en cas d'ABANDON
    d'un problème (pas de route/paramètre "give up"/"abandon" dans la
    spec) : voir le rapport de clôture — AlChess choisit de ne JAMAIS
    appeler cette route tant que le problème n'est pas réellement résolu
    ou raté (jamais de résultat inventé), ce qui est cohérent avec
    l'absence de toute route dédiée à l'abandon.
  - Les thèmes (`puzzle.themes`) sont déjà présents dans la réponse de
    /next : c'est à AlChess de les cacher à l'écran avant résolution
    (l'API ne les masque jamais elle-même).
"""

import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import chess
import chess.pgn

from nicsoft.utils.net_safety import ensure_https

logger = logging.getLogger("niclink.lichess")

PUZZLE_NEXT_URL = "https://lichess.org/api/puzzle/next"
PUZZLE_BATCH_SOLVE_URL = "https://lichess.org/api/puzzle/batch/mix"

_TIMEOUT_S = 10
_MAX_RESPONSE_BYTES = 65536


def _user_agent() -> str:
    try:
        from importlib.metadata import version
        return f"AlChess/{version('alchess')}"
    except Exception:
        return "AlChess/0.0.0"


def _compute_setup_fen(pgn_text: str, initial_ply, puzzle_fen, last_move_uci) -> str | None:
    """Position physique à mettre en place AVANT le premier coup de
    l'adversaire (`last_move_uci`) — rejoue `pgn_text` depuis le début
    jusqu'à `initial_ply` demi-coups (python-chess), ce qui donne la
    position exacte juste avant ce coup, avec tout l'historique
    nécessaire (roque, prise en passant...). Jamais une tentative de
    "défaire" `last_move_uci` depuis `puzzle_fen` seul : la pièce prise
    (s'il y en a une) et les droits perdus ne sont pas récupérables à
    partir du seul FEN final.

    Retourne `None` sans exception si le PGN est absent/invalide ou trop
    court pour `initial_ply` (ex. #347-style donnée corrompue) — à
    l'appelant de se replier alors sur `puzzle_fen` directement, sans
    étape "premier coup de l'adversaire" (voir le rapport de clôture,
    point 4 : "quand le problème en comporte un")."""
    if not pgn_text or not isinstance(initial_ply, int) or initial_ply < 0:
        return None
    try:
        parsed = chess.pgn.read_game(io.StringIO(pgn_text))
    except Exception as e:
        logger.warning("Lichess puzzle : PGN illisible pour calculer la position de mise en place : %s", e)
        return None
    if parsed is None:
        return None
    try:
        moves = list(parsed.mainline_moves())
    except Exception as e:
        logger.warning("Lichess puzzle : coups du PGN illisibles : %s", e)
        return None
    if initial_ply >= len(moves):
        return None

    board = chess.Board()
    try:
        for move in moves[:initial_ply]:
            board.push(move)
    except Exception as e:
        logger.warning("Lichess puzzle : coup illégal en rejouant le PGN : %s", e)
        return None
    setup_fen = board.fen()

    # Vérification best-effort (jamais bloquante) : le coup suivant du PGN
    # doit correspondre à last_move_uci et amener à puzzle_fen.
    try:
        opponent_move = moves[initial_ply]
        if last_move_uci and opponent_move.uci() != last_move_uci:
            logger.warning(
                "Lichess puzzle : lastMove (%s) ne correspond pas au coup %s du PGN rejoué.",
                last_move_uci, opponent_move.uci(),
            )
        board.push(opponent_move)
        if puzzle_fen and board.board_fen() != chess.Board(puzzle_fen).board_fen():
            logger.warning("Lichess puzzle : position rejouée différente du FEN annoncé par Lichess.")
    except Exception as e:
        logger.warning("Lichess puzzle : vérification du premier coup adverse impossible : %s", e)

    return setup_fen


def parse_puzzle_payload(data: dict) -> dict | None:
    """Extrait les champs utiles de la réponse de /api/puzzle/next, sans
    jamais lever d'exception sur une donnée inattendue — `None` si la
    structure minimale (id + solution non vide) est absente, à
    l'appelant de traiter ce cas comme network_error (donnée
    exploitable). Pure, sans effet de bord réseau : testable directement
    avec un dict construit à la main."""
    if not isinstance(data, dict):
        return None
    puzzle = data.get("puzzle")
    game = data.get("game")
    if not isinstance(puzzle, dict) or not isinstance(game, dict):
        return None
    puzzle_id = puzzle.get("id")
    solution_raw = puzzle.get("solution")
    if not puzzle_id or not isinstance(solution_raw, list) or not solution_raw:
        return None
    solution = [m for m in solution_raw if isinstance(m, str) and m]
    if not solution:
        return None

    puzzle_fen = puzzle.get("fen")
    puzzle_fen = puzzle_fen if isinstance(puzzle_fen, str) and puzzle_fen else None
    last_move = puzzle.get("lastMove")
    last_move = last_move if isinstance(last_move, str) and last_move else None
    initial_ply = puzzle.get("initialPly")
    pgn_text = game.get("pgn") if isinstance(game.get("pgn"), str) else ""

    setup_fen = _compute_setup_fen(pgn_text, initial_ply, puzzle_fen, last_move) if last_move else None

    themes_raw = puzzle.get("themes")
    themes = [t for t in themes_raw if isinstance(t, str)] if isinstance(themes_raw, list) else []

    rating = puzzle.get("rating")
    rating = rating if isinstance(rating, int) else None

    players_raw = game.get("players")
    players = players_raw if isinstance(players_raw, list) else []

    return {
        "puzzle_id": str(puzzle_id),
        "rating": rating,
        "plays": puzzle.get("plays") if isinstance(puzzle.get("plays"), int) else None,
        "themes": themes,
        "solution": solution,
        "fen": puzzle_fen,
        # Position physique de départ : avant le premier coup de
        # l'adversaire si calculable, sinon la position du problème
        # elle-même (pas d'étape "premier coup" affichée dans ce cas).
        "setup_fen": setup_fen or puzzle_fen,
        "opponent_first_move": last_move if setup_fen else None,
        "game_id": game.get("id", "") if isinstance(game.get("id"), str) else "",
        "rated": bool(game.get("rated", True)),
        "players": players,
    }


def get_next_puzzle(token: str, difficulty: str | None = None) -> dict:
    """GET /api/puzzle/next (scope puzzle:read). Retourne :
      {"status": "ok", "puzzle_id":, "rating":, "themes": [...],
       "solution": [...], "fen":, "setup_fen":, "opponent_first_move":,
       "game_id":, "rated":, "players": [...]}
      {"status": "invalid"}        — jeton absent ou refusé (401)
      {"status": "missing_scope"}  — jeton valide mais sans puzzle:read (403)
      {"status": "rate_limited"}   — 429
      {"status": "network_error"}  — pas de réseau ou réponse inattendue
    """
    if not token:
        return {"status": "invalid"}
    url = PUZZLE_NEXT_URL
    if difficulty:
        url += "?" + urllib.parse.urlencode({"difficulty": difficulty})
    ensure_https(url)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": _user_agent()},
        method="GET",
    )
    try:
        # Adresse en https, vérifiée par ensure_https ci-dessus.
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310  # nosec B310
            raw = resp.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return {"status": "rate_limited"}
        if exc.code == 401:
            return {"status": "invalid"}
        if exc.code == 403:
            return {"status": "missing_scope"}
        return {"status": "network_error"}
    except urllib.error.URLError:
        return {"status": "network_error"}

    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"status": "network_error"}

    parsed = parse_puzzle_payload(data)
    if parsed is None:
        return {"status": "network_error"}
    return {"status": "ok", **parsed}


def submit_puzzle_result(token: str, puzzle_id: str, win: bool, rated: bool = True) -> dict:
    """POST /api/puzzle/batch/mix (scope puzzle:write) — envoie le
    résultat RÉEL (réussi/raté) d'un problème déjà entièrement résolu ou
    raté ; jamais appelé pour un problème abandonné en cours (aucun
    résultat n'est alors connu — voir le rapport de clôture). `nb=0` :
    jamais de nouveau lot de problèmes récupéré par cet appel, AlChess
    redemande toujours séparément via get_next_puzzle().

    Retourne :
      {"status": "ok", "rating_diff": int|None, "new_rating": int|None,
       "provisional": bool|None}
      {"status": "invalid"}        — jeton absent ou refusé (401)
      {"status": "missing_scope"}  — jeton valide mais sans puzzle:write (403)
      {"status": "rate_limited"}   — 429
      {"status": "network_error"}  — pas de réseau ou réponse inattendue
    """
    if not token or not puzzle_id:
        return {"status": "invalid"}
    ensure_https(PUZZLE_BATCH_SOLVE_URL)
    body = json.dumps({
        "solutions": [{"id": puzzle_id, "win": bool(win), "rated": bool(rated)}],
        "nb": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        PUZZLE_BATCH_SOLVE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": _user_agent(),
        },
        method="POST",
    )
    try:
        # Adresse constante en https, vérifiée par ensure_https ci-dessus.
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310  # nosec B310
            raw = resp.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return {"status": "rate_limited"}
        if exc.code == 401:
            return {"status": "invalid"}
        if exc.code == 403:
            return {"status": "missing_scope"}
        return {"status": "network_error"}
    except urllib.error.URLError:
        return {"status": "network_error"}

    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"status": "network_error"}
    if not isinstance(data, dict):
        return {"status": "network_error"}

    rounds = data.get("rounds")
    rating_diff = None
    if isinstance(rounds, list):
        for r in rounds:
            if isinstance(r, dict) and str(r.get("id")) == str(puzzle_id):
                diff = r.get("ratingDiff")
                rating_diff = diff if isinstance(diff, int) else None
                break

    glicko = data.get("glicko")
    new_rating = None
    provisional = None
    if isinstance(glicko, dict):
        rating = glicko.get("rating")
        new_rating = int(rating) if isinstance(rating, (int, float)) else None
        provisional = glicko.get("provisional") if isinstance(glicko.get("provisional"), bool) else None

    return {
        "status": "ok",
        "rating_diff": rating_diff,
        "new_rating": new_rating,
        "provisional": provisional,
    }
