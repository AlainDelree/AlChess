"""
nicsoft/tests/test_issue341_review_eval_pov.py — AlChess

Issue #341 : l'évaluation affichée à côté des flèches de l'écran d'analyse
post-partie (issue #335) doit toujours être exprimée du point de vue des
Blancs (signe +/- des Blancs), jamais du camp au trait — alors que
`EngineAnalysisMixin.get_multipv()` (nicsoft/engine/engine_analysis.py)
renvoie `cp`/`mate` relatifs au camp au trait (`score.pov(board.turn)`).
Couvre aussi la mise en forme (mats jamais convertis en centipions) et le
plafond de la barre d'évaluation, sans aucun moteur réel ni réseau — faux
moteur comme dans test_issue335_review_multipv.py / test_issue338_review_
same_position.py.

Position réelle de l'observation d'Alain (partie du 15/11/2026, coup 74,
Blancs au trait) utilisée comme cas de test : a7-a8=D et a7-a8=T sont des
mats en un coup, Kf5 légal mais pas mat en un. Établi ici par lecture du
code (voir docstring plus bas) : la valeur "+40.73" du troisième coup
n'est PAS un mat mal converti — `get_multipv()` ne met jamais un score de
mat dans `cp` (branche `if/else` exclusive sur `pov.is_mate()`) — c'est
une évaluation ordinaire en centipions renvoyée par le moteur à la
profondeur demandée (DEPTH=12), cohérente avec l'écart de matériel énorme
de cette position (loin au-delà du plafond de 10 pions de la barre).
"""
import chess
import pytest

from nicsoft.engine.review_multipv import (
    ReviewMultiPVService,
    _pov_vers_blancs,
    eval_bar_fraction,
    format_eval_blancs,
)

FEN_OBSERVATION = "6k1/P5p1/4N3/2p3N1/6K1/P7/4r2P/R7 w - - 1 38"


# ── _pov_vers_blancs : conversion camp au trait → point de vue Blancs ──────

def test_blancs_au_trait_aucune_conversion():
    assert _pov_vers_blancs(cp=120, mate=None, white_to_move=True) == (120, None)
    assert _pov_vers_blancs(cp=None, mate=2, white_to_move=True) == (None, 2)


def test_noirs_au_trait_signe_inverse():
    # Le moteur dit "+50 pour le camp au trait" alors que les Noirs sont au
    # trait → du point de vue des Blancs, c'est -50 (avantage Noir).
    assert _pov_vers_blancs(cp=50, mate=None, white_to_move=False) == (-50, None)
    # Mat en 3 annoncé pour le camp au trait (Noir) → mat des Noirs, donc
    # négatif du point de vue des Blancs.
    assert _pov_vers_blancs(cp=None, mate=3, white_to_move=False) == (None, -3)


def test_valeurs_nulles_preservees():
    assert _pov_vers_blancs(cp=None, mate=None, white_to_move=True) == (None, None)
    assert _pov_vers_blancs(cp=None, mate=None, white_to_move=False) == (None, None)


# ── format_eval_blancs : mise en forme lisible ──────────────────────────────

def test_format_cp_positif_et_negatif_et_nul():
    assert format_eval_blancs(123, None) == "+1.23"
    assert format_eval_blancs(-45, None) == "-0.45"
    assert format_eval_blancs(0, None) == "0.00"


def test_format_mat_jamais_converti_en_centipions():
    # Mat des Blancs : "#N" (pas de signe moins, pas de centipions).
    assert format_eval_blancs(None, 1) == "#1"
    assert format_eval_blancs(None, 7) == "#7"
    # Mat des Noirs : "-#N".
    assert format_eval_blancs(None, -1) == "-#1"
    assert format_eval_blancs(None, -5) == "-#5"


def test_format_mat_prioritaire_sur_cp_si_les_deux_fournis():
    # Ne devrait jamais arriver en pratique (un seul des deux est fourni par
    # le moteur) mais le mat doit l'emporter si jamais les deux coexistent.
    assert format_eval_blancs(999999, 2) == "#2"


def test_format_aucune_evaluation_disponible():
    assert format_eval_blancs(None, None) is None


def test_format_valeur_observee_dans_le_rapport_alain():
    # Le troisième coup de la capture d'écran d'Alain : "+40.73".
    assert format_eval_blancs(4073, None) == "+40.73"


# ── eval_bar_fraction : plafond et courbe douce ─────────────────────────────

def test_bar_egalite():
    assert eval_bar_fraction(0, None) == 0.5


def test_bar_aucune_evaluation_est_neutre():
    assert eval_bar_fraction(None, None) == 0.5


def test_bar_mat_blanc_pleine_cote_blanc():
    assert eval_bar_fraction(None, 1) == 1.0
    assert eval_bar_fraction(None, 9) == 1.0  # mat lent : plein quand même


def test_bar_mat_noir_pleine_cote_noir():
    assert eval_bar_fraction(None, -1) == 0.0
    assert eval_bar_fraction(None, -9) == 0.0


def test_bar_plafond_au_dela_de_10_pions():
    assert eval_bar_fraction(1000, None) == 1.0   # exactement 10 pions
    assert eval_bar_fraction(4073, None) == 1.0   # valeur observée par Alain
    assert eval_bar_fraction(-1000, None) == 0.0
    assert eval_bar_fraction(-4073, None) == 0.0


def test_bar_courbe_douce_et_monotone_avant_le_plafond():
    f_200  = eval_bar_fraction(200, None)
    f_500  = eval_bar_fraction(500, None)
    f_900  = eval_bar_fraction(900, None)
    assert 0.5 < f_200 < f_500 < f_900 < 1.0
    f_m200 = eval_bar_fraction(-200, None)
    assert f_m200 == pytest.approx(1.0 - f_200)


# ── Bout en bout avec un faux moteur, position réelle de l'observation ─────

class _FakeEngineObservation:
    """Rejoue l'observation d'Alain : les 3 meilleures lignes renvoyées par
    `get_multipv()` relatives au camp au trait (ici Blanc, board.turn ==
    chess.WHITE pour ce FEN) — a8=Q et a8=T sont mat en 1, Kf5 vaut +40.73
    (4073 centipions, valeur ordinaire, pas un mat)."""

    def get_multipv(self, board, n=3, depth=12):
        assert board.turn is chess.WHITE
        return [
            {"move": "a7a8q", "cp": None, "mate": 1},
            {"move": "a7a8r", "cp": None, "mate": 1},
            {"move": "g4f5",  "cp": 4073, "mate": None},
        ]

    def quit(self):
        pass


def test_observation_alain_blancs_au_trait_mats_et_cp_corrects():
    service = ReviewMultiPVService(lambda: _FakeEngineObservation())
    result = service._compute(FEN_OBSERVATION)

    assert result["error"] is None
    assert result["terminal"] is None
    lines = result["lines"]
    assert len(lines) == 3
    assert lines[0]["score_text"] == "#1"
    assert lines[1]["score_text"] == "#1"
    assert lines[2]["score_text"] == "+40.73"
    assert lines[2]["cp"] == 4073
    # Le plafond de la barre (10 pions) est largement dépassé par la
    # 1ère ligne (mat des Blancs) → barre pleine Blanc.
    assert result["bar_fraction"] == 1.0
    assert result["bar_text"] == "#1"


class _FakeEngineNoirAuTrait:
    """Même position pivotée (Noir au trait) : le moteur annonce un
    avantage pour le camp au trait (Noir) → doit devenir négatif une fois
    reconverti du point de vue des Blancs."""

    def get_multipv(self, board, n=3, depth=12):
        assert board.turn is chess.BLACK
        return [{"move": "e7e5", "cp": 80, "mate": None}]


def test_noirs_au_trait_signe_final_negatif_pour_les_blancs():
    board = chess.Board()
    board.push_san("e4")  # Noirs au trait
    service = ReviewMultiPVService(lambda: _FakeEngineNoirAuTrait())
    result = service._compute(board.fen())

    assert result["lines"][0]["cp"] == -80
    assert result["lines"][0]["score_text"] == "-0.80"
    assert result["bar_fraction"] < 0.5


# ── Positions terminales (mat/pat/nulle) : jamais de calcul moteur ─────────

class _FakeEngineJamaisAppele:
    def get_multipv(self, board, n=3, depth=12):
        raise AssertionError("le moteur ne doit jamais être interrogé sur une position terminale")

    def quit(self):
        pass


def test_position_terminale_mat_des_blancs_barre_pleine_sans_moteur():
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert board.is_checkmate()
    service = ReviewMultiPVService(lambda: _FakeEngineJamaisAppele())
    result = service._compute(board.fen())

    assert result["lines"] == []
    assert result["terminal"] == "checkmate"
    assert result["bar_fraction"] == 0.0  # mat des Blancs au trait → Noirs gagnent
    assert result["bar_text"] == "-#"


def test_position_terminale_pat_barre_a_moitie_sans_moteur():
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert board.is_stalemate()
    service = ReviewMultiPVService(lambda: _FakeEngineJamaisAppele())
    result = service._compute(board.fen())

    assert result["lines"] == []
    # Issue #351, point 0c : le pat est désormais distingué des autres
    # nulles automatiques (matériel insuffisant, répétition, 50 coups...),
    # pour que l'écran d'analyse affiche "Pat" plutôt que "Lignes
    # indisponibles" — voir test_issue351_lichess_corrections.py.
    assert result["terminal"] == "stalemate"
    assert result["bar_fraction"] == 0.5
    assert result["bar_text"] == "½"


def test_position_terminale_nulle_hors_pat_reste_draw_sans_moteur():
    """Nulle automatique qui n'est PAS un pat (ici matériel insuffisant,
    roi seul contre roi seul) : `terminal` reste "draw" — seul le pat
    reçoit sa propre valeur (issue #351, point 0c)."""
    board = chess.Board("8/8/8/4k3/8/4K3/8/8 w - - 0 1")
    outcome = board.outcome(claim_draw=False)
    assert outcome is not None and outcome.winner is None
    assert not board.is_stalemate()
    service = ReviewMultiPVService(lambda: _FakeEngineJamaisAppele())
    result = service._compute(board.fen())

    assert result["lines"] == []
    assert result["terminal"] == "draw"
    assert result["bar_fraction"] == 0.5
