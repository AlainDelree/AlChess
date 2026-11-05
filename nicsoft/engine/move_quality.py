"""
nicsoft/engine/move_quality.py — NicLink
Classification de la qualité d'un coup, indépendante de tout moteur.
"""

import chess
import chess.engine

# ── Seuils d'évaluation (centipawns de perte) ────────────────────────────────
SEUIL_BON         =  50   # < 50cp  → bon coup
SEUIL_IMPRECISION = 100   # 50-100  → imprécision
SEUIL_ERREUR      = 300   # 100-300 → erreur
                          # >= 300  → blunder


def classifier_coup(delta_cp: int) -> str:
    """Classe un coup selon la perte en centipawns."""
    if delta_cp < SEUIL_BON:
        return "bon"
    elif delta_cp < SEUIL_IMPRECISION:
        return "imprecision"
    elif delta_cp < SEUIL_ERREUR:
        return "erreur"
    else:
        return "blunder"


def score_to_cp(score: chess.engine.Score, joueur: chess.Color) -> int | None:
    """
    Convertit un Score python-chess en centipawns du point de vue du joueur.
    Retourne None si c'est un mat.
    """
    if score.is_mate():
        return None
    cp = score.white().score()
    if joueur == chess.WHITE:
        return cp
    else:
        return -cp
