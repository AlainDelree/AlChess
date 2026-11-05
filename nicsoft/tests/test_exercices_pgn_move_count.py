"""
Test issue #274 — numéros et nombres de coups des exercices selon la
convention des échecs (un coup = un déplacement blanc + un déplacement noir).

Avant le fix : les champs envoyés au navigateur (`move_num`, `move_count`,
`moves`) contenaient le nombre brut de demi-coups (`len(board.move_stack)`
ou `len(init_moves)`), affiché tel quel avec les libellés "coup(s)"/
"move(s)" — d'où "Move 25" au lieu de "Coup 13", ou "4 coups joués" au lieu
de "2 coups joués".

Ce test vérifie, sans interface ni matériel, les deux fonctions de
conversion demi-coups → coups PGN introduites dans `exercices.py` :
- `pgn_move_number` : numéro du coup en cours (celui que les blancs
  commencent ou que les noirs doivent répondre).
- `pgn_moves_played` : nombre de coups complets joués ; pour un nombre
  impair de demi-coups, compte le coup commencé comme joué.
"""
from nicsoft.modes.exercices.exercices import pgn_move_number, pgn_moves_played


def test_pgn_move_number():
    # 0 demi-coup : le coup 1 n'a pas encore commencé.
    assert pgn_move_number(0) == 1
    assert pgn_move_number(1) == 1   # 1.e4 joué, coup 1 en cours (noirs à répondre)
    assert pgn_move_number(2) == 2   # 1.e4 e6 joué, coup 2 commence
    assert pgn_move_number(4) == 3   # 1.e4 e6 2.d4 d5 joué, coup 3 commence
    assert pgn_move_number(5) == 3   # + 3.Nc3 joué, coup 3 en cours
    assert pgn_move_number(24) == 13  # 12 coups complets joués, coup 13 commence
    assert pgn_move_number(25) == 13  # 13e coup des blancs joué, coup 13 en cours


def test_pgn_moves_played():
    assert pgn_moves_played(0) == 0
    assert pgn_moves_played(1) == 1   # coup 1 commencé -> compté joué
    assert pgn_moves_played(2) == 1   # 1.e4 e6 -> 1 coup joué
    assert pgn_moves_played(4) == 2   # 1.e4 e6 2.d4 d5 -> 2 coups joués
    assert pgn_moves_played(5) == 3   # + 3.Nc3 -> 3e coup commencé -> 3 coups
    assert pgn_moves_played(24) == 12
    assert pgn_moves_played(25) == 13
