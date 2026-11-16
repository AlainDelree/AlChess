"""
nicsoft/tests/test_issue352_harmonisation_marques_fleches.py — AlChess

Issue #352 : harmoniser les marques de coups (?!/?/??) de l'écran d'analyse
après partie avec les flèches des meilleurs coups — une seule analyse
(même profondeur, même méthode) doit faire foi pour les deux, en chances de
gain plutôt qu'en pions bruts. Aucun vrai moteur ni réseau ici : évaluations
simulées (chess.engine.PovScore / faux objets get_multipv), comme les tests
déjà en place pour review_multipv.py (#335/#341).

Couvre :
  - move_quality.classifier_coup_winrate : écart commun ECART_BON (un coup
    classé 2e à moins de l'écart n'est jamais marqué), mat forcé gardé
    jamais marqué, mat forcé perdu toujours une gaffe ;
  - EngineAnalysisMixin.evaluate_move : réutilise get_multipv (même
    profondeur que les flèches), jamais un calcul séparé pour le coup joué
    hors du top N (recherche root_moves à la même profondeur), perte vue du
    point de vue du joueur qui a joué pour les Blancs ET les Noirs ;
  - review_multipv._compute : les lignes 2/3 hors de l'écart commun portent
    within_gap=False (flèches/légende masquées côté client), la ligne 1 est
    toujours within_gap=True ;
  - REVIEW_DEPTH/REVIEW_N_LINES : une seule source (move_quality.py) pour
    engine_analysis.py et review_multipv.py.
"""

import chess
import chess.engine
import pytest

from nicsoft.engine import engine_analysis, review_multipv
from nicsoft.engine.engine_analysis import EngineAnalysisMixin
from nicsoft.engine.move_quality import (
    ECART_BON,
    REVIEW_DEPTH,
    REVIEW_N_LINES,
    SEUIL_ERREUR_PCT,
    SEUIL_IMPRECISION_PCT,
    classifier_coup_winrate,
    winrate_from_eval,
)
from nicsoft.engine.review_multipv import ReviewMultiPVService


# ── Une seule source pour la profondeur/le nombre de lignes ────────────────

def test_review_depth_et_n_lines_partages_entre_les_deux_modules():
    assert engine_analysis.REVIEW_DEPTH is REVIEW_DEPTH
    assert engine_analysis.REVIEW_N_LINES is REVIEW_N_LINES
    assert review_multipv.DEPTH == REVIEW_DEPTH
    assert review_multipv.N_LINES == REVIEW_N_LINES


# ── classifier_coup_winrate : écart commun, mat gardé/perdu ────────────────

def test_coup_2e_a_moins_de_l_ecart_jamais_marque():
    # +0.99 (meilleur) vs +0.91 (coup joué, 2e ligne) — l'écart observé par
    # Alain sur la partie réelle (issue #352) : 0,08 pion doit rester "bon".
    best_cp, played_cp = 99, 91
    perte = winrate_from_eval(best_cp, None) - winrate_from_eval(played_cp, None)
    assert perte < ECART_BON
    qualite, _ = classifier_coup_winrate(best_cp, None, played_cp, None)
    assert qualite == "bon"


def test_perte_de_quelques_dixiemes_dans_position_gagnante_reste_bon():
    # Position déjà à +1 pion : perdre 0.3 pion (comme dans l'observation
    # d'Alain, +0,91 -> +0,68) ne doit jamais être classé "erreur".
    qualite, perte = classifier_coup_winrate(100, None, 68, None)
    assert qualite in ("bon", "imprecision")
    assert qualite != "erreur"
    assert qualite != "blunder"


def test_grosse_perte_en_position_equilibree_est_une_gaffe():
    # Position équilibrée (0.00) -> coup qui perd une pièce entière (-300) :
    # perte énorme en chances de gain, doit être une gaffe.
    qualite, perte = classifier_coup_winrate(0, None, -300, None)
    assert qualite == "blunder"
    assert perte >= SEUIL_ERREUR_PCT


@pytest.mark.parametrize("best_cp,played_cp,attendu", [
    (0, -40, "bon"),           # perte ~3.7 points de gain : < ECART_BON (5)
    (0, -75, "imprecision"),   # perte ~6.9 points de gain : entre ECART_BON et SEUIL_IMPRECISION_PCT (10)
])
def test_paliers_imprecision_erreur_coherents_avec_les_seuils(best_cp, played_cp, attendu):
    qualite, perte = classifier_coup_winrate(best_cp, None, played_cp, None)
    assert qualite == attendu


def test_mat_force_garde_nest_jamais_marque_meme_plus_lent():
    # Le joueur avait un mat forcé en 2 coups, le coup joué garde un mat
    # forcé (même en 7 coups, plus lent) : jamais marqué (issue #352, point 4).
    qualite, perte = classifier_coup_winrate(best_cp=None, best_mate=2, played_cp=None, played_mate=7)
    assert qualite == "bon"
    assert perte == 0.0


def test_mat_force_perdu_est_toujours_une_gaffe():
    # Le joueur avait un mat forcé en 3 coups, le coup joué ne mate plus du
    # tout (reste gagnant au sens large, +8 pions) : toujours une gaffe,
    # même si les chances de gain restent très hautes après coup.
    qualite, perte = classifier_coup_winrate(best_cp=None, best_mate=3, played_cp=800, played_mate=None)
    assert qualite == "blunder"


def test_mat_force_perdu_et_remplace_par_mat_subi_est_une_gaffe():
    qualite, perte = classifier_coup_winrate(best_cp=None, best_mate=3, played_cp=None, played_mate=-5)
    assert qualite == "blunder"


def test_winrate_from_eval_mat_sature_a_0_et_1():
    assert winrate_from_eval(None, 1) == 1.0
    assert winrate_from_eval(None, 9) == 1.0
    assert winrate_from_eval(None, -1) == 0.0
    assert winrate_from_eval(None, -9) == 0.0


def test_winrate_from_eval_egalite_est_50_pourcent():
    assert winrate_from_eval(0, None) == pytest.approx(0.5)


# ── EngineAnalysisMixin.evaluate_move : même méthode que les flèches ──────

class _FakeAnalyser(EngineAnalysisMixin):
    """Expose get_multipv() comme un faux moteur (comme _FakeEngine dans
    test_issue335_review_multipv.py) ; evaluate_move() (code réel, non
    surchargé) doit s'appuyer dessus sans jamais relancer une recherche
    séparée pour un coup déjà présent dans les lignes."""

    def __init__(self, lines, root_moves_score=None):
        self._analyse_active = True
        self._lines = lines
        self._root_moves_score = root_moves_score
        self._root_moves_calls = []

    def get_multipv(self, board, n=3, depth=12):
        return [dict(line) for line in self._lines]

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    @property
    def _lock_eval(self):
        return self._FakeLock()

    @property
    def _engine_eval(self):
        return self  # juste pour que "if not self._engine_eval" soit faux

    def analyse(self, board, limit, root_moves=None, info=None):
        self._root_moves_calls.append(root_moves)
        if self._root_moves_score is None:
            return {"score": None}
        return {"score": self._root_moves_score}


def test_evaluate_move_coup_joue_dans_le_top3_reutilise_la_meme_ligne_sans_recalcul():
    # 1. Nf3 (+0,99), 2. Bc4 (+0,91) joué, 3. Bf4 (+0,80) — reproduction de
    # l'observation d'Alain (issue #352) : Bc4 est la 2e ligne, à 0,08 pion
    # du meilleur, ne doit JAMAIS être marqué, sans recherche root_moves
    # supplémentaire puisqu'il est déjà dans les 3 lignes.
    analyser = _FakeAnalyser(lines=[
        {"move": "g1f3", "cp": 99, "mate": None},
        {"move": "f1c4", "cp": 91, "mate": None},
        {"move": "c1f4", "cp": 80, "mate": None},
    ])
    board = chess.Board()
    qualite, delta_cp, best = analyser.evaluate_move(board, chess.Move.from_uci("f1c4"), depth=12)
    assert qualite == "bon"
    assert best == "g1f3"
    assert analyser._root_moves_calls == []  # aucun calcul séparé


def test_evaluate_move_coup_hors_top3_evalue_a_la_meme_profondeur_root_moves():
    analyser = _FakeAnalyser(
        lines=[
            {"move": "g1f3", "cp": 50, "mate": None},
            {"move": "f1c4", "cp": 40, "mate": None},
            {"move": "c1f4", "cp": 30, "mate": None},
        ],
        root_moves_score=chess.engine.PovScore(chess.engine.Cp(-200), chess.WHITE),
    )
    board = chess.Board()
    move = chess.Move.from_uci("a2a3")  # hors du top 3 simulé
    qualite, delta_cp, best = analyser.evaluate_move(board, move, depth=12)
    # Un seul calcul séparé, restreint à ce coup, à la MÊME profondeur
    # (depth=12 transmis tel quel) — jamais une profondeur différente.
    assert analyser._root_moves_calls == [[move]]
    assert qualite == "blunder"  # +0.50 -> -2.00 du point de vue du joueur


def test_evaluate_move_perte_vue_du_point_de_vue_du_joueur_qui_a_joue_noirs():
    # Les Noirs jouent ; la perte doit être mesurée de LEUR point de vue
    # (déjà garanti par get_multipv, qui renvoie cp/mate relatifs au camp au
    # trait) — un coup qui profite aux Noirs (meilleure ligne noire moins
    # bonne que le coup joué) ne doit jamais être marqué.
    analyser = _FakeAnalyser(lines=[
        {"move": "e7e5", "cp": 20, "mate": None},   # meilleure ligne (Noirs)
        {"move": "c7c5", "cp": 10, "mate": None},
        {"move": "g8f6", "cp": 5,  "mate": None},
    ])
    board = chess.Board()
    board.push_san("e4")  # Noirs au trait
    qualite, delta_cp, best = analyser.evaluate_move(board, chess.Move.from_uci("c7c5"), depth=12)
    assert qualite == "bon"


def test_evaluate_move_analyse_inactive_retourne_bon_sans_appel_moteur():
    analyser = _FakeAnalyser(lines=[{"move": "g1f3", "cp": 50, "mate": None}])
    analyser._analyse_active = False
    board = chess.Board()
    qualite, delta_cp, best = analyser.evaluate_move(board, chess.Move.from_uci("g1f3"), depth=12)
    assert (qualite, delta_cp, best) == ("bon", 0, None)


def test_evaluate_move_mat_force_disponible_mais_perdu_est_une_gaffe():
    analyser = _FakeAnalyser(lines=[
        {"move": "d1h5", "cp": None, "mate": 3},   # mat forcé disponible
        {"move": "f1c4", "cp": 400, "mate": None},
        {"move": "g1f3", "cp": 50,  "mate": None},
    ])
    board = chess.Board()
    qualite, delta_cp, best = analyser.evaluate_move(board, chess.Move.from_uci("f1c4"), depth=12)
    assert qualite == "blunder"
    assert best == "d1h5"


def test_evaluate_move_garde_le_mat_force_meme_plus_lent_nest_pas_marque():
    analyser = _FakeAnalyser(lines=[
        {"move": "d1h5", "cp": None, "mate": 2},
        {"move": "f1c4", "cp": None, "mate": 6},   # mat aussi, plus lent
        {"move": "g1f3", "cp": 50,   "mate": None},
    ])
    board = chess.Board()
    qualite, delta_cp, best = analyser.evaluate_move(board, chess.Move.from_uci("f1c4"), depth=12)
    assert qualite == "bon"


# ── review_multipv : within_gap partagé avec les marques ──────────────────

class _FakeEngineLignes:
    def __init__(self, lines):
        self._lines = lines

    def get_multipv(self, board, n=3, depth=12):
        return [dict(line) for line in self._lines]

    def quit(self):
        pass


def test_within_gap_observation_alain_ligne2_dans_l_ecart():
    # 1. Nf3 (+0,99), 2. Nc3 (+0,91, coup joué), 3. Nh3 (+0,80) — toutes à
    # moins de 0,40 pion, dans l'écart commun pour cette position (coups
    # légaux depuis la position de départ, requis par le garde-fou #338).
    board = chess.Board()
    service = ReviewMultiPVService(lambda: _FakeEngineLignes([
        {"move": "g1f3", "cp": 99, "mate": None},
        {"move": "b1c3", "cp": 91, "mate": None},
        {"move": "g1h3", "cp": 80, "mate": None},
    ]))
    result = service._compute(board.fen())
    assert [l["within_gap"] for l in result["lines"]] == [True, True, True]


def test_within_gap_ligne_3_nettement_inferieure_est_masquee():
    board = chess.Board()
    service = ReviewMultiPVService(lambda: _FakeEngineLignes([
        {"move": "g1f3", "cp": 100, "mate": None},
        {"move": "b1c3", "cp": 90,  "mate": None},
        {"move": "g1h3", "cp": -300, "mate": None},  # nettement moins bon
    ]))
    result = service._compute(board.fen())
    within = [l["within_gap"] for l in result["lines"]]
    assert within[0] is True   # la flèche 1 est toujours affichée
    assert within[1] is True
    assert within[2] is False


def test_within_gap_premiere_ligne_toujours_vraie():
    board = chess.Board()
    service = ReviewMultiPVService(lambda: _FakeEngineLignes([
        {"move": "g1f3", "cp": -700, "mate": None},
    ]))
    result = service._compute(board.fen())
    assert result["lines"][0]["within_gap"] is True


def test_within_gap_mats_de_meme_signe_restent_dans_l_ecart():
    board = chess.Board()
    service = ReviewMultiPVService(lambda: _FakeEngineLignes([
        {"move": "g1f3", "cp": None, "mate": 2},
        {"move": "b1c3", "cp": None, "mate": 6},
    ]))
    result = service._compute(board.fen())
    assert [l["within_gap"] for l in result["lines"]] == [True, True]
