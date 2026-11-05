"""
Test issue #277 — règle de conversion demi-coups -> coups PGN, partagée.

`pgn_move_number` et `pgn_moves_played` ont été introduites dans
`nicsoft.modes.exercices.exercices` par le fix de l'issue #274, puis
déplacées ici (`nicsoft.engine.board_utils`, module neutre qui n'importe
jamais `nicsoft.web` — voir ARC-001) pour que la Retranscription puisse les
réutiliser sans dépendre du module des exercices. `exercices.py` les
réimporte désormais depuis ce module ; son propre test
(`test_exercices_pgn_move_count.py`) continue de passer sans modification.
"""
from nicsoft.engine.board_utils import pgn_move_number, pgn_moves_played


def test_pgn_move_number_quelques_valeurs():
    assert pgn_move_number(0) == 1
    assert pgn_move_number(1) == 1
    assert pgn_move_number(2) == 2
    assert pgn_move_number(5) == 3
    assert pgn_move_number(24) == 13


def test_pgn_moves_played_quelques_valeurs():
    assert pgn_moves_played(0) == 0
    assert pgn_moves_played(1) == 1
    assert pgn_moves_played(2) == 1
    assert pgn_moves_played(5) == 3
    assert pgn_moves_played(24) == 12


def test_pgn_moves_played_session_retranscription_reprise():
    """
    Valeur envoyée dans l'événement `retranscription_en_cours` (champ
    `moves`) pour une session reprise : nicsoft/web/alchess.py calcule
    `pgn_moves_played(len(saved["moves"]))` où `saved["moves"]` est la
    liste de coups UCI persistée par `retranscription.save_session`.
    """
    saved_moves_uci = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]  # 5 demi-coups
    assert pgn_moves_played(len(saved_moves_uci)) == 3
