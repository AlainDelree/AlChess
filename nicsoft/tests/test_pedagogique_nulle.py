"""
Tests du traitement de la proposition de nulle en mode pédagogique
(issue #282).

Avant correction, `Game._traiter_nulle` englobait dans un seul bloc
`except Exception` à la fois l'évaluation de la position ET l'appel à
`_end_game(...)` qui termine la partie en levant `BackMenuExit` (exception
de contrôle de flux). Ce bloc avalait `BackMenuExit`, empêchant la partie de
se terminer et laissant le fil de surveillance de l'échiquier tourner
indéfiniment, tout en annonçant à tort un refus de nulle.

Ces tests appellent `Game._traiter_nulle` sur un objet minimal simulant une
partie (moteur et échiquier physique tous deux simulés), sans aucun
matériel ni thread réel.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import chess
import pytest

import nicsoft.modes.pedagogique.pedagogique as pedagogique
from nicsoft.modes.pedagogique.pedagogique import BackMenuExit, SEUIL_ACCEPTATION_NULLE_CP


def _fake_game(opponent_label="Rodent 1200 (Tal)", cp=None, mate=None,
               eval_erreur=False, playing_white=True):
    """Objet minimal portant les seuls attributs lus par `_traiter_nulle`."""
    game = SimpleNamespace()
    game.playing_white = chess.WHITE if playing_white else chess.BLACK
    game.opponent_label = opponent_label
    game.nl_inst = MagicMock()
    if eval_erreur:
        game.engine = MagicMock(evaluate=MagicMock(side_effect=RuntimeError("moteur indisponible")))
    else:
        game.engine = MagicMock(evaluate=MagicMock(return_value={"cp": cp, "mate": mate}))
    # _end_game réel : lève BackMenuExit, comme en production (acceptation = fin de partie).
    game._end_game = MagicMock(side_effect=lambda *a, **k: (_ for _ in ()).throw(BackMenuExit()))
    return game


@pytest.fixture
def board_black_to_move():
    """Position où c'est aux Noirs de jouer (sf_color = Noir si l'humain joue Blanc)."""
    board = chess.Board()
    board.push_san("e4")
    assert board.turn == chess.BLACK
    return board


def test_nulle_acceptee_leve_backmenuexit_sans_refus(monkeypatch, board_black_to_move):
    """Nulle acceptée (adversaire pas gagnant) : BackMenuExit remonte, aucun événement de refus."""
    sent = []
    monkeypatch.setattr(pedagogique, "send_event", lambda etype, data=None: sent.append((etype, data)))
    game = _fake_game(cp=0)  # position équilibrée → l'adversaire accepte

    with pytest.raises(BackMenuExit):
        pedagogique.Game._traiter_nulle(game, board=board_black_to_move)

    game._end_game.assert_called_once_with("1/2-1/2", "Nulle acceptée")
    assert sent == []  # aucun "nulle_refusee" n'a dû être émis


def test_nulle_refusee_adversaire_trop_bien_place(monkeypatch, board_black_to_move):
    """L'adversaire a plus d'un pion et demi d'avance → refus, la partie continue."""
    sent = []
    monkeypatch.setattr(pedagogique, "send_event", lambda etype, data=None: sent.append((etype, data)))
    game = _fake_game(cp=SEUIL_ACCEPTATION_NULLE_CP + 50, opponent_label="Maia 1200")

    pedagogique.Game._traiter_nulle(game, board=board_black_to_move)  # ne lève rien

    game._end_game.assert_not_called()
    assert len(sent) == 1
    etype, data = sent[0]
    assert etype == "nulle_refusee"
    assert data["reason_key"] == "toast.nulle_refusee_default"
    assert data["vars"]["opponent"] == "Maia 1200"
    assert "Maia 1200" in data["reason"]


def test_evaluation_impossible_refuse_avec_message_dedie_et_partie_continue(monkeypatch, board_black_to_move):
    """Évaluation impossible (moteur en erreur) : refus avec le message dédié, pas de fin de partie."""
    sent = []
    monkeypatch.setattr(pedagogique, "send_event", lambda etype, data=None: sent.append((etype, data)))
    game = _fake_game(eval_erreur=True)

    pedagogique.Game._traiter_nulle(game, board=board_black_to_move)  # ne lève rien

    game._end_game.assert_not_called()
    assert len(sent) == 1
    etype, data = sent[0]
    assert etype == "nulle_refusee"
    assert data["reason_key"] == "toast.nulle_refusee_eval"


@pytest.mark.parametrize("cp, doit_accepter", [
    (SEUIL_ACCEPTATION_NULLE_CP, True),       # juste à la limite → accepté
    (SEUIL_ACCEPTATION_NULLE_CP + 1, False),  # juste au-dessus → refusé
])
def test_seuil_acceptation_valeurs_limites(monkeypatch, board_black_to_move, cp, doit_accepter):
    sent = []
    monkeypatch.setattr(pedagogique, "send_event", lambda etype, data=None: sent.append((etype, data)))
    game = _fake_game(cp=cp)

    if doit_accepter:
        with pytest.raises(BackMenuExit):
            pedagogique.Game._traiter_nulle(game, board=board_black_to_move)
        game._end_game.assert_called_once()
        assert sent == []
    else:
        pedagogique.Game._traiter_nulle(game, board=board_black_to_move)
        game._end_game.assert_not_called()
        assert len(sent) == 1 and sent[0][0] == "nulle_refusee"


def test_nom_adversaire_transmis_dans_le_refus(monkeypatch, board_black_to_move):
    """Le nom affiché dans le refus est bien celui transmis par le lanceur (opponent_label)."""
    sent = []
    monkeypatch.setattr(pedagogique, "send_event", lambda etype, data=None: sent.append((etype, data)))
    game = _fake_game(cp=SEUIL_ACCEPTATION_NULLE_CP + 1, opponent_label="Stockfish ~1500elo")

    pedagogique.Game._traiter_nulle(game, board=board_black_to_move)

    _, data = sent[0]
    assert data["vars"]["opponent"] == "Stockfish ~1500elo"
    assert "Stockfish ~1500elo" in data["reason"]
