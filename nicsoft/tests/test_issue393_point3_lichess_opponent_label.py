"""
nicsoft/tests/test_issue393_point3_lichess_opponent_label.py — AlChess

Issue #393, point 3 (suite de l'étude #391) : le panneau « Tour en cours »
affichait "IA de Lichess (niveau 1)" même pour un coup d'un adversaire
HUMAIN — `LichessGame._apply_new_moves` n'envoyait jamais `opponent_is_ai`/
`opponent_name` dans l'évènement `lichess_move` (contrairement à
`lichess_init`), et app.js supposait toujours l'IA pour un coup adverse.
Ce fichier vérifie le côté serveur (le côté navigateur — app.js — est
couvert par test_issue393_point3_lichess_opponent_label_e2e.py)."""
import chess
import pytest

from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport
from nicsoft.tests.test_issue331_lichess_opponent_alerts import _AlertBoard, _make_game, _started


def _last(events, etype):
    matches = [d for t, d in events if t == etype]
    assert matches, f"aucun évènement {etype!r}"
    return matches[-1]


def test_coup_ia_porte_opponent_is_ai_vrai(monkeypatch):
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(monkeypatch, nl_inst=board, transport=FakeTransport())
    _started(game, "black", opponent_is_ai=True)
    assert game._opponent_is_ai is True

    game._apply_game_state({"status": "started", "moves": "e2e4"})
    move = _last(events, "lichess_move")
    assert move["opponent_move"] is True
    assert move["opponent_is_ai"] is True
    assert move["opponent_name"] == game.opponent_name


def test_coup_humain_porte_opponent_is_ai_faux_et_son_nom(monkeypatch):
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(monkeypatch, nl_inst=board, transport=FakeTransport())
    _started(game, "black", opponent_is_ai=False)
    assert game._opponent_is_ai is False
    assert game.opponent_name == "opp"

    game._apply_game_state({"status": "started", "moves": "e2e4"})
    move = _last(events, "lichess_move")
    assert move["opponent_move"] is True
    # Un humain n'est JAMAIS présenté comme une IA (bug réel établi par #391).
    assert move["opponent_is_ai"] is False
    assert move["opponent_name"] == "opp"


def test_coup_de_lutilisateur_lui_meme_nest_jamais_marque_opponent_is_ai(monkeypatch):
    """`opponent_is_ai` décrit l'ADVERSAIRE de la partie, pas l'auteur du
    coup — toujours présent, même pour notre propre coup (app.js ne s'en
    sert que si `opponent_move` est vrai, voir le commentaire d'app.js)."""
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(monkeypatch, nl_inst=board, transport=FakeTransport())
    _started(game, "white", opponent_is_ai=False)

    game._apply_game_state({"status": "started", "moves": "e2e4"})
    move = _last(events, "lichess_move")
    assert move["opponent_move"] is False
    assert move["opponent_is_ai"] is False


def test_initialisation_lichess_init_inchangee(monkeypatch):
    """Garde-fou de non-régression : lichess_init transmettait déjà
    opponent_is_ai/opponent_name avant cette issue — inchangé."""
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(monkeypatch, nl_inst=board, transport=FakeTransport())
    _started(game, "white", opponent_is_ai=False)
    init = _last(events, "lichess_init")
    assert init["opponent_is_ai"] is False
    assert init["opponent_name"] == "opp"
