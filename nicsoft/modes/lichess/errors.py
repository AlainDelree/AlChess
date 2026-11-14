"""
nicsoft/modes/lichess/errors.py — AlChess

Erreurs typées du client de partie Lichess (issue #307, étape L1). Aucun
message d'exception ne doit jamais contenir le jeton — ces classes ne
reçoivent que des codes HTTP et des messages déjà filtrés par Lichess
(coup illégal, partie terminée, etc.), jamais le jeton lui-même.
"""

import json
import re

# Issue #330 : refus HTTP 400 d'une recherche d'adversaire humain (board/
# seek) quand la couleur demandée (jamais "random") romprait l'équilibre
# des couleurs du compte — texte exact établi par lecture du code source
# public de lila (app/controllers/Setup.scala, lu le 14/11/2026) :
# `JsonBadRequest(s"You must also play some games as $forced")`, sans
# ponctuation finale ajoutée par lila lui-même. Reconnu indépendamment de
# la casse pour rester robuste à une variante mineure du texte.
_COLOR_BALANCE_REFUSAL_RE = re.compile(
    r"must also play some games as\s+(white|black)\b", re.IGNORECASE,
)


def detect_color_balance_refusal(message: str) -> str:
    """Retourne "white"/"black" si `message` correspond au refus Lichess
    d'équilibre des couleurs (voir _COLOR_BALANCE_REFUSAL_RE ci-dessus) —
    chaîne vide si `message` ne correspond pas (texte différent ou
    inconnu) : l'appelant affiche alors le texte de Lichess seul, comme
    pour tout autre refus 400 (issue #330, point 2)."""
    m = _COLOR_BALANCE_REFUSAL_RE.search(message or "")
    return m.group(1).lower() if m else ""


def extract_api_message(body: str) -> str:
    """Texte explicatif renvoyé par Lichess dans le corps JSON d'une
    réponse d'erreur (champ "error", voir doc/specs/schemas/Error.yaml,
    dépôt lichess-org/api) — chaîne vide si le corps est absent ou n'est
    pas ce JSON attendu (issue #329, point 1 : affiché à l'écran pour un
    refus 400, jamais le jeton, qui n'apparaît jamais dans ce corps)."""
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return ""
    if isinstance(data, dict):
        return str(data.get("error", "") or "")
    return ""


class LichessError(Exception):
    """Base commune — jamais le jeton dans le message."""


class LichessAuthError(LichessError):
    """Jeton refusé par Lichess (401 invalide, 403 droit manquant)."""

    def __init__(self, status_code: int):
        super().__init__(f"Jeton Lichess refusé (HTTP {status_code})")
        self.status_code = status_code


class LichessRateLimitError(LichessError):
    """429 — Lichess demande d'attendre avant de réessayer."""

    def __init__(self, retry_after_s: int = 60):
        super().__init__(f"Limite de requêtes Lichess atteinte — réessayer après {retry_after_s}s")
        self.retry_after_s = retry_after_s


class LichessNetworkError(LichessError):
    """Réseau indisponible ou délai dépassé, hors réponse HTTP de Lichess."""


class LichessApiError(LichessError):
    """Lichess a répondu avec une erreur applicative (400, etc.) et un message
    (coup illégal, partie déjà terminée, annulation refusée...)."""

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(f"Lichess a refusé la requête (HTTP {status_code}) : {message}")
        self.status_code = status_code
        self.api_message = message
