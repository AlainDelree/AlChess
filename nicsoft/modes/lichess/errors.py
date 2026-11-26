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


# Issue #347, partie 2, point 2 : refus HTTP 400 ambigu d'un coup — un seul
# message pour deux causes très différentes (pas le tour de l'utilisateur,
# OU la partie est déjà terminée côté Lichess). Texte exact établi par
# lecture du code source public de lila (modules/round/src/main/
# RoundSocket.scala / Env.scala, lu le 15/11/2026 — voir rapport de
# clôture) ; reconnu par simple inclusion (insensible à la casse) plutôt
# qu'une regex stricte, pour rester robuste à une variante mineure de
# ponctuation.
_AMBIGUOUS_TURN_OR_OVER_TEXT = "not your turn, or game already over"


def is_ambiguous_turn_or_over_error(message: str) -> bool:
    """Vrai si `message` correspond au refus HTTP 400 ambigu de Lichess
    pour un coup envoyé hors tour OU après la fin de la partie — l'appelant
    doit alors relire l'état réel de la partie avant de choisir son
    message (voir game.py::_handle_move_rejected), jamais conclure « coup
    refusé » sur la seule foi de ce texte."""
    return _AMBIGUOUS_TURN_OR_OVER_TEXT in (message or "").lower()


def detect_color_balance_refusal(message: str) -> str:
    """Retourne "white"/"black" si `message` correspond au refus Lichess
    d'équilibre des couleurs (voir _COLOR_BALANCE_REFUSAL_RE ci-dessus) —
    chaîne vide si `message` ne correspond pas (texte différent ou
    inconnu) : l'appelant affiche alors le texte de Lichess seul, comme
    pour tout autre refus 400 (issue #330, point 2)."""
    m = _COLOR_BALANCE_REFUSAL_RE.search(message or "")
    return m.group(1).lower() if m else ""


# Issue #393, point 2 : refus HTTP 400 d'un coup — texte exact établi par
# essai réel (Alain, 26/11/2026) : "Piece on c2 cannot move to c4" (toujours
# deux cases a-h/1-8, jamais de ponctuation finale observée).
_PIECE_CANNOT_MOVE_RE = re.compile(
    r"piece on ([a-h][1-8]) cannot move to ([a-h][1-8])", re.IGNORECASE,
)

# Texte exact établi par test_issue334_lichess_opponent_claim.py (refus
# d'une réclamation après la fin de partie) — distinct du message ambigu
# ci-dessus (_AMBIGUOUS_TURN_OR_OVER_TEXT, qui contient en plus "not your
# turn, or").
_GAME_ALREADY_OVER_TEXT = "game is already over"


def translate_api_detail(message: str) -> tuple:
    """Reconnaît un message BRUT (toujours en anglais) renvoyé par l'API
    Lichess dans le corps d'une erreur, et retourne (clé i18n, variables)
    pour un affichage traduit par l'appelant côté navigateur (jamais de
    traduction ici : la langue choisie n'est connue que du navigateur,
    voir i18n.js) — issue #393, point 2.

    Retourne ("", {}) si `message` est vide (aucun détail à afficher) ;
    ("lichess.detail.generique", {}) si le message n'est reconnu par
    aucun des cas ci-dessous (jamais le texte anglais brut affiché à
    l'écran — il reste disponible dans le journal, déjà écrit par
    l'appelant avant cet appel)."""
    text = (message or "").strip()
    if not text:
        return "", {}
    if is_ambiguous_turn_or_over_error(text):
        return "lichess.detail.pas_votre_tour_ou_terminee", {}
    m = _PIECE_CANNOT_MOVE_RE.search(text)
    if m:
        return "lichess.detail.piece_ne_peut_aller", {"depart": m.group(1), "arrivee": m.group(2)}
    if _GAME_ALREADY_OVER_TEXT in text.lower():
        return "lichess.detail.partie_terminee", {}
    return "lichess.detail.generique", {}


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
