"""
nicsoft/modes/lichess/errors.py — AlChess

Erreurs typées du client de partie Lichess (issue #307, étape L1). Aucun
message d'exception ne doit jamais contenir le jeton — ces classes ne
reçoivent que des codes HTTP et des messages déjà filtrés par Lichess
(coup illégal, partie terminée, etc.), jamais le jeton lui-même.
"""


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
