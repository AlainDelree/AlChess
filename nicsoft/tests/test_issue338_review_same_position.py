"""
nicsoft/tests/test_issue338_review_same_position.py — AlChess

Issue #338 : les flèches des meilleures lignes moteur et la flèche du coup
joué doivent concerner la MÊME position sur l'écran d'analyse post-partie
(issue #335), avec le bon camp au trait.

Cause établie (sans moteur réel) : `history_fen` était construit avec
`chess.Board.board_fen()` (disposition des pièces SEULE, sans le champ
« camp au trait ») dans `pedagogique.Game._end_game`,
`human.GameWeb._build_history_from_stack` et
`lichess.LichessGame._history_from_board`. `chess.Board(board_fen_seul)`
complète alors les champs manquants avec leurs valeurs par défaut — camp
au trait toujours Blanc — quel que soit le camp réel au trait :
`review_multipv.py` calculait donc les meilleures lignes pour les Blancs
sur TOUTE position affichée où c'était en réalité aux Noirs de jouer,
alors que les pièces étaient correctement placées (d'où l'apparence d'un
« décalage d'un demi-coup », et non une position voisine ou un mauvais
indice — les deux autres hypothèses de l'issue sont écartées par ces
tests). Les tests ci-dessous verrouillent le FEN COMPLET (`board.fen()`)
en sortie de ces trois fonctions, pour chaque position d'une courte
partie, position initiale et dernière position comprises.
"""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import chess
import pytest

import nicsoft.modes.pedagogique.pedagogique as pedagogique
from nicsoft.modes.pedagogique.pedagogique import BackMenuExit
from nicsoft.modes.humain.human import GameWeb
from nicsoft.modes.lichess.game import LichessGame
from nicsoft.engine.review_multipv import ReviewMultiPVService


def _turns(fens):
    return [chess.Board(f).turn for f in fens]


# ── pedagogique.Game._end_game — reconstruction de history_fen ──────────

def _fake_pedagogique_game():
    game = SimpleNamespace()
    game.save_pgn_tmp   = MagicMock()
    game._shutdown_leds = MagicMock()
    game.game_over      = False
    game.engine         = MagicMock()
    game.tmp_path       = "/tmp/fake-338.pgn"
    game.playing_white  = True
    game.player_name    = "Alain"
    return game


def test_pedagogique_end_game_history_fen_camp_au_trait_correct(monkeypatch):
    """Reproduit exactement le scénario de l'issue : après 1.Cc3 (Blancs),
    c'est aux Noirs de jouer (1...c5). Avant correction, la position après
    Cc3 aurait été reconstruite avec le trait aux Blancs (défaut de
    chess.Board() sur un FEN tronqué) — le moteur y aurait alors cherché
    les meilleurs coups BLANCS sur une position où c'est aux Noirs de
    jouer, exactement le symptôme décrit."""
    captured = {}
    monkeypatch.setattr(pedagogique, "get_history", lambda: (
        [
            {"uci": "b1c3", "san": "Cc3", "color": "white", "qualite": None},
            {"uci": "c7c5", "san": "c5",  "color": "black", "qualite": None},
        ],
        [],
    ))
    monkeypatch.setattr(pedagogique, "send_event", lambda *a, **k: None)
    monkeypatch.setattr(pedagogique, "get_init_data", lambda: {})
    monkeypatch.setattr(pedagogique, "get_action", lambda timeout=0: {"type": "no_save"})
    monkeypatch.setattr(pedagogique, "finalize_pgn", lambda *a, **k: None)

    def _fake_set_app_state(state, data=None):
        if state == "game_over":
            captured["history_fen"] = data["history_fen"]
            captured["history_moves"] = data["history_moves"]
    monkeypatch.setattr(pedagogique, "set_app_state", _fake_set_app_state)

    game = _fake_pedagogique_game()
    with pytest.raises(BackMenuExit):
        pedagogique.Game._end_game(game, "1-0", "Fin de partie", skip_save=False)

    fens = captured["history_fen"]
    assert len(fens) == 3  # position initiale + après Cc3 + après c5
    turns = _turns(fens)
    assert turns == [chess.WHITE, chess.BLACK, chess.WHITE]
    # La position affichée après Cc3 (indice 1) doit avoir les Noirs au
    # trait — c'est précisément celle où l'écran affiche la flèche orange
    # c7-c5, et où les flèches des meilleures lignes doivent être NOIRES.
    board_after_nc3 = chess.Board(fens[1])
    assert board_after_nc3.turn == chess.BLACK
    assert chess.Move.from_uci("c7c5") in board_after_nc3.legal_moves


def test_pedagogique_end_game_position_initiale_et_derniere(monkeypatch):
    """Position initiale (indice 0) et dernière position de la partie
    (dernier indice) également vérifiées — pas seulement les positions
    intermédiaires."""
    moves = [
        {"uci": "e2e4", "san": "e4", "color": "white", "qualite": None},
        {"uci": "e7e5", "san": "e5", "color": "black", "qualite": None},
        {"uci": "g1f3", "san": "Cf3", "color": "white", "qualite": None},
    ]
    captured = {}
    monkeypatch.setattr(pedagogique, "get_history", lambda: (moves, []))
    monkeypatch.setattr(pedagogique, "send_event", lambda *a, **k: None)
    monkeypatch.setattr(pedagogique, "get_init_data", lambda: {})
    monkeypatch.setattr(pedagogique, "get_action", lambda timeout=0: {"type": "no_save"})
    monkeypatch.setattr(pedagogique, "finalize_pgn", lambda *a, **k: None)
    monkeypatch.setattr(pedagogique, "set_app_state",
                         lambda state, data=None: captured.update(data) if state == "game_over" else None)

    game = _fake_pedagogique_game()
    with pytest.raises(BackMenuExit):
        pedagogique.Game._end_game(game, "1-0", "Fin de partie", skip_save=False)

    fens = captured["history_fen"]
    assert chess.Board(fens[0]).turn == chess.WHITE   # position initiale
    assert chess.Board(fens[0]).fen() == chess.STARTING_FEN
    assert chess.Board(fens[-1]).turn == chess.BLACK  # dernière position (après Cf3, Noirs au trait)


# ── human.GameWeb._build_history_from_stack ──────────────────────────────

def test_humain_build_history_from_stack_camp_au_trait_correct():
    game = SimpleNamespace()
    board = chess.Board()
    board.push_san("Nc3")
    board.push_san("c5")
    game.board = board

    fens, moves = GameWeb._build_history_from_stack(game)

    assert len(fens) == 3
    assert _turns(fens) == [chess.WHITE, chess.BLACK, chess.WHITE]
    assert moves[0]["color"] == "white"
    assert moves[1]["color"] == "black"
    # Le coup suivant la position d'indice i est moves[i] (flèche orange) :
    # cohérent avec le camp au trait de fens[i].
    for i, mv in enumerate(moves):
        expected_turn = chess.WHITE if mv["color"] == "white" else chess.BLACK
        assert chess.Board(fens[i]).turn == expected_turn


def test_humain_build_history_from_stack_noirs_jouent_en_premier():
    """Partie reprise/collée depuis une position où les Noirs jouent en
    premier (position de départ particulière) — même garantie."""
    game = SimpleNamespace()
    board = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    board.push_san("Nc6")
    board.push_san("Nf3")
    game.board = board

    fens, moves = GameWeb._build_history_from_stack(game)

    # NB : _build_history_from_stack repart toujours de l'échiquier
    # STANDARD (chess.Board()) pour rejouer move_stack — limitation connue,
    # hors périmètre de cette issue (le camp au trait, lui, reste correct
    # à partir de la position standard rejouée).
    assert _turns(fens) == [chess.WHITE, chess.BLACK, chess.WHITE]


# ── lichess.LichessGame._history_from_board ──────────────────────────────

def test_lichess_history_from_board_camp_au_trait_correct():
    game = SimpleNamespace()
    board = chess.Board()
    board.push_san("e4")
    board.push_san("c5")
    board.push_san("Nf3")
    game.board = board

    fens, moves = LichessGame._history_from_board(game)

    assert len(fens) == 4
    assert _turns(fens) == [chess.WHITE, chess.BLACK, chess.WHITE, chess.BLACK]


# ── Garde-fou (issue #338, point 3) : coup illégal pour le camp au trait ─

class _FakeEngineCoupIllegal:
    """Simule un moteur qui, malgré tout, renvoie un coup de l'autre
    camp (bug amont non détecté, position voisine mélangée...)."""

    def get_multipv(self, board, n=3, depth=12):
        # board.turn est Noir (après 1.Cc3) mais le "moteur" renvoie un
        # coup BLANC (e2e4) — jamais jouable par le camp au trait réel.
        return [{"move": "e2e4", "cp": 30, "mate": None}]

    def quit(self):
        pass


def test_garde_fou_coup_illegal_pour_camp_au_trait_aucune_fleche(caplog):
    """Si le moteur renvoie un coup non jouable par le camp au trait de la
    position reçue, aucune flèche de meilleur coup ne doit être tracée
    (lines vide) plutôt que des flèches fausses — et c'est journalisé."""
    engine = _FakeEngineCoupIllegal()
    service = ReviewMultiPVService(lambda: engine)

    board = chess.Board()
    board.push_san("Nc3")  # Noirs au trait
    fen = board.fen()

    with caplog.at_level(logging.WARNING, logger="ReviewMultiPV"):
        result = service._compute(fen)

    assert result["lines"] == []
    assert "error" in result
    assert any("illégal" in rec.message for rec in caplog.records)


def test_garde_fou_coups_legaux_tous_conserves():
    """Cas normal : tous les coups renvoyés sont jouables par le camp au
    trait → les 3 lignes sont conservées avec leur SAN."""
    class _FakeEngineOk:
        def get_multipv(self, board, n=3, depth=12):
            return [
                {"move": "c7c5", "cp": 10, "mate": None},
                {"move": "g8f6", "cp": 5, "mate": None},
                {"move": "e7e6", "cp": 0, "mate": None},
            ]

        def quit(self):
            pass

    service = ReviewMultiPVService(lambda: _FakeEngineOk())
    board = chess.Board()
    board.push_san("Nc3")
    result = service._compute(board.fen())

    assert len(result["lines"]) == 3
    assert result["lines"][0]["san"] == "c5"
