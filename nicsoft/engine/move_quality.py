"""
nicsoft/engine/move_quality.py — NicLink
Classification de la qualité d'un coup, indépendante de tout moteur.
"""

import math

import chess
import chess.engine

# ── Issue #352 : profondeur/nombre de lignes de référence, UNE seule
# analyse pour toute l'écran d'analyse après partie (flèches, barre
# d'évaluation, marques ?!/?/??) — importées à la fois par
# EngineAnalysisMixin (nicsoft/engine/engine_analysis.py, get_multipv/
# evaluate_move/analyser_partie) et par ReviewMultiPVService
# (nicsoft/engine/review_multipv.py). Avant l'issue #352, les marques
# étaient calculées séparément à depth=8 alors que les flèches l'étaient à
# depth=12 : deux recherches à profondeur différente sur la même position
# pouvaient donner des évaluations différentes, d'où des marques
# contredisant les flèches (CHANGELOG-352.md).
REVIEW_DEPTH   = 12
REVIEW_N_LINES = 3

# ── Seuils d'évaluation (centipawns de perte) ────────────────────────────────
# Historique — conservé pour compatibilité (réexporté par engine_manager.py
# et nicsoft/engine/analyse.py), non utilisé par EngineAnalysisMixin.
# evaluate_move() depuis l'issue #352 : voir classifier_coup_winrate()
# ci-dessous, seule classification utilisée pour les marques ?!/?/?? et les
# flèches de l'écran d'analyse après partie.
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


# ── Issue #352 : classification en chances de gain, une seule référence ────
# pour les marques (?!/?/??) ET les flèches de l'écran d'analyse après
# partie. Remplace les seuils bruts en centipions ci-dessus pour ce chemin :
# un même delta de pions ne doit pas peser pareil selon que la position est
# déjà décidée ou équilibrée (cause de l'incohérence observée par Alain —
# voir CHANGELOG-352.md).

# Constante de la courbe centipions → % de chances de gain utilisée par
# Lichess (lila) — un seul repère partagé par toute l'application plutôt
# qu'une formule maison.
WINRATE_K = 0.00368208

# Écart commun (point 5 de l'issue #352) : au-delà, un coup n'est plus
# considéré "bon" par rapport au meilleur — ni marqué comme tel, ni
# recommandé par une flèche secondaire. Exprimé en points de % de chances
# de gain (0..1), pas en pions bruts, pour qu'une perte de quelques dixièmes
# de pion dans une position déjà gagnante ou équilibrée ne soit jamais une
# erreur.
ECART_BON          = 0.05   # < 5 points  → bon coup / flèche affichée
SEUIL_IMPRECISION_PCT = 0.10   # 5-10 points → imprécision (?!)
SEUIL_ERREUR_PCT      = 0.20   # 10-20 points → erreur (?)
                               # >= 20 points → blunder (??)


def cp_to_winrate(cp: int) -> float:
    """Pourcentage de chances de gain (0..1) du camp dont `cp` est le point
    de vue, formule Lichess (lila) — courbe sigmoïde, jamais linéaire."""
    return 1.0 / (1.0 + math.exp(-WINRATE_K * cp))


def winrate_from_eval(cp: int | None, mate: int | None) -> float:
    """Chances de gain (0..1) du camp dont `cp`/`mate` sont le point de vue.
    Un mat forcé en sa faveur vaut 1.0 (victoire certaine) quel que soit le
    nombre de coups ; un mat forcé contre lui vaut 0.0. Aucune évaluation
    disponible → 0.5 (neutre)."""
    if mate is not None:
        return 1.0 if mate > 0 else 0.0
    if cp is None:
        return 0.5
    return cp_to_winrate(cp)


def classifier_coup_winrate(
    best_cp: int | None, best_mate: int | None,
    played_cp: int | None, played_mate: int | None,
) -> tuple[str, float]:
    """Classe un coup joué en comparant sa perte en chances de gain à celle
    du meilleur coup trouvé par la MÊME recherche (mêmes lignes, même
    profondeur) — jamais un calcul séparé. `best_*`/`played_*` sont tous du
    point de vue du joueur qui a joué (blancs comme noirs).

    Un mat forcé qui disparaît (le joueur avait un mat forcé et le coup
    joué ne le garde pas) reste toujours une gaffe, quelle que soit la
    perte en chances de gain (qui peut rester minime près de 100%). Un coup
    qui garde un mat forcé en sa faveur (même plus lent) n'est jamais
    marqué.

    Retourne (qualite, perte) où perte est la perte en chances de gain
    (0..1, jamais négative)."""
    garde_mat_force  = (
        best_mate is not None and best_mate > 0
        and played_mate is not None and played_mate > 0
    )
    perd_mat_force = (
        best_mate is not None and best_mate > 0 and not garde_mat_force
    )
    if garde_mat_force:
        return "bon", 0.0
    if perd_mat_force:
        return "blunder", 1.0

    perte = max(0.0, winrate_from_eval(best_cp, best_mate) - winrate_from_eval(played_cp, played_mate))
    if perte < ECART_BON:
        return "bon", perte
    elif perte < SEUIL_IMPRECISION_PCT:
        return "imprecision", perte
    elif perte < SEUIL_ERREUR_PCT:
        return "erreur", perte
    else:
        return "blunder", perte
