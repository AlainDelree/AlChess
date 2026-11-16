"""
nicsoft/tests/test_issue351_lichess_puzzles.py — AlChess

Issue #351, étape L3 (problèmes Lichess) — module de communication
(nicsoft/modes/lichess/puzzle_client.py) : lecture du problème suivant,
envoi du résultat, calcul de la position de mise en place physique
(avant le premier coup de l'adversaire). Aucun réseau réel : urlopen
mocké (même technique que test_issue306_lichess.py), jamais le vrai
jeton d'Alain ni le vrai Lichess.
"""

import json
import urllib.error

import chess
import chess.pgn
import pytest

from nicsoft.modes.lichess import client as lichess_client
from nicsoft.modes.lichess import puzzle_client


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=None):
        return self._body


def _build_pgn(moves_uci):
    game = chess.pgn.Game()
    node = game
    board = chess.Board()
    for uci in moves_uci:
        move = chess.Move.from_uci(uci)
        node = node.add_variation(move)
        board.push(move)
    return str(game), board


def _puzzle_payload(moves_uci, initial_ply, solution, puzzle_id="abcd1", rating=1500, themes=None):
    pgn_text, board_full = _build_pgn(moves_uci)
    # Position après `initial_ply` demi-coups (avant le coup suivant,
    # celui de l'adversaire qui amène au FEN du problème).
    setup_board = chess.Board()
    for uci in moves_uci[:initial_ply]:
        setup_board.push_uci(uci)
    last_move_uci = moves_uci[initial_ply]
    puzzle_board = chess.Board(setup_board.fen())
    puzzle_board.push_uci(last_move_uci)
    return {
        "game": {"id": "gid1", "pgn": pgn_text, "rated": True, "players": [
            {"color": "white", "userId": "joueurA"}, {"color": "black", "userId": "joueurB"},
        ]},
        "puzzle": {
            "id": puzzle_id, "rating": rating, "plays": 1000,
            "initialPly": initial_ply, "fen": puzzle_board.fen(),
            "lastMove": last_move_uci, "solution": solution,
            "themes": themes or ["middlegame", "fork"],
        },
    }, setup_board.fen()


# ── parse_puzzle_payload : calcul de la position de mise en place ─────────

def test_parse_calcule_la_position_avant_le_premier_coup_adverse():
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"]
    payload, expected_setup_fen = _puzzle_payload(moves, initial_ply=4, solution=["a6b5", "f3e5"])
    result = puzzle_client.parse_puzzle_payload(payload)
    assert result is not None
    assert result["puzzle_id"] == "abcd1"
    assert result["rating"] == 1500
    assert result["themes"] == ["middlegame", "fork"]
    assert result["solution"] == ["a6b5", "f3e5"]
    assert result["opponent_first_move"] == "f1b5"
    assert result["setup_fen"] == expected_setup_fen
    assert result["fen"] == payload["puzzle"]["fen"]
    assert result["rated"] is True
    assert result["game_id"] == "gid1"


def test_parse_pgn_absent_replie_sur_le_fen_du_probleme_sans_etape_premier_coup():
    payload, _ = _puzzle_payload(["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"], initial_ply=4,
                                  solution=["a6b5"])
    payload["game"]["pgn"] = ""
    result = puzzle_client.parse_puzzle_payload(payload)
    assert result["setup_fen"] == result["fen"]
    assert result["opponent_first_move"] is None


def test_parse_initial_ply_hors_limites_ne_plante_pas():
    payload, _ = _puzzle_payload(["e2e4", "e7e5"], initial_ply=1, solution=["e7e5"])
    payload["puzzle"]["initialPly"] = 99  # au-delà du nombre de coups du PGN
    result = puzzle_client.parse_puzzle_payload(payload)
    assert result is not None
    assert result["setup_fen"] == result["fen"]


def test_parse_sans_puzzle_ou_sans_solution_retourne_none():
    assert puzzle_client.parse_puzzle_payload({}) is None
    assert puzzle_client.parse_puzzle_payload({"puzzle": {}, "game": {}}) is None
    assert puzzle_client.parse_puzzle_payload({"puzzle": {"id": "x", "solution": []}, "game": {}}) is None
    assert puzzle_client.parse_puzzle_payload("pas un dict") is None


def test_parse_sans_premier_coup_adverse_aucune_etape_de_mise_en_place_supplementaire():
    """Un problème qui commence directement au trait de l'utilisateur
    (`lastMove` absent) : setup_fen == fen, aucune LED de "premier coup
    adverse" à afficher (voir rapport de clôture, point 4)."""
    payload, _ = _puzzle_payload(["e2e4", "e7e5", "g1f3"], initial_ply=2, solution=["g1f3"])
    payload["puzzle"]["lastMove"] = None
    result = puzzle_client.parse_puzzle_payload(payload)
    assert result["opponent_first_move"] is None
    assert result["setup_fen"] == result["fen"]


# ── get_next_puzzle ─────────────────────────────────────────────────────────

def test_get_next_puzzle_ok(monkeypatch):
    payload, _ = _puzzle_payload(["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"], initial_ply=4,
                                  solution=["a6b5", "f3e5"])
    body = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = puzzle_client.get_next_puzzle("lip_test_token")
    assert result["status"] == "ok"
    assert result["puzzle_id"] == "abcd1"
    assert result["solution"] == ["a6b5", "f3e5"]


def test_get_next_puzzle_sans_jeton():
    assert puzzle_client.get_next_puzzle("") == {"status": "invalid"}


def test_get_next_puzzle_jeton_invalide_401(monkeypatch):
    def raise_401(req, timeout=None):
        raise urllib.error.HTTPError(puzzle_client.PUZZLE_NEXT_URL, 401, "Unauthorized", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_401)
    assert puzzle_client.get_next_puzzle("lip_test")["status"] == "invalid"


def test_get_next_puzzle_droit_manquant_403(monkeypatch):
    def raise_403(req, timeout=None):
        raise urllib.error.HTTPError(puzzle_client.PUZZLE_NEXT_URL, 403, "Forbidden", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_403)
    assert puzzle_client.get_next_puzzle("lip_test")["status"] == "missing_scope"


def test_get_next_puzzle_limite_requetes_429(monkeypatch):
    def raise_429(req, timeout=None):
        raise urllib.error.HTTPError(puzzle_client.PUZZLE_NEXT_URL, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_429)
    assert puzzle_client.get_next_puzzle("lip_test")["status"] == "rate_limited"


def test_get_next_puzzle_reseau_coupe(monkeypatch):
    def raise_url_error(req, timeout=None):
        raise urllib.error.URLError("pas de réseau")
    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    assert puzzle_client.get_next_puzzle("lip_test")["status"] == "network_error"


def test_get_next_puzzle_reponse_illisible_ne_plante_pas(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(b"pas du json"))
    assert puzzle_client.get_next_puzzle("lip_test")["status"] == "network_error"


def test_get_next_puzzle_refuse_adresse_non_https(monkeypatch):
    monkeypatch.setattr(puzzle_client, "PUZZLE_NEXT_URL", "http://lichess.org/api/puzzle/next")
    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: called.append(1))
    with pytest.raises(Exception):
        puzzle_client.get_next_puzzle("lip_test")
    assert not called


# ── submit_puzzle_result ────────────────────────────────────────────────────

def test_submit_puzzle_result_ok(monkeypatch):
    body = json.dumps({
        "rounds": [{"id": "abcd1", "win": True, "ratingDiff": 7}],
        "glicko": {"rating": 1534, "deviation": 80, "provisional": False},
        "puzzles": [],
    }).encode("utf-8")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = puzzle_client.submit_puzzle_result("lip_test", "abcd1", win=True)
    assert result == {
        "status": "ok", "rating_diff": 7, "new_rating": 1534, "provisional": False,
    }


def test_submit_puzzle_result_sans_jeton_ou_sans_id():
    assert puzzle_client.submit_puzzle_result("", "abcd1", win=True) == {"status": "invalid"}
    assert puzzle_client.submit_puzzle_result("lip_test", "", win=True) == {"status": "invalid"}


def test_submit_puzzle_result_droit_manquant_403(monkeypatch):
    def raise_403(req, timeout=None):
        raise urllib.error.HTTPError(puzzle_client.PUZZLE_BATCH_SOLVE_URL, 403, "Forbidden", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_403)
    assert puzzle_client.submit_puzzle_result("lip_test", "abcd1", win=False)["status"] == "missing_scope"


def test_submit_puzzle_result_reseau_coupe(monkeypatch):
    def raise_url_error(req, timeout=None):
        raise urllib.error.URLError("pas de réseau")
    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    assert puzzle_client.submit_puzzle_result("lip_test", "abcd1", win=False)["status"] == "network_error"


def test_submit_puzzle_result_corps_envoye_ne_contient_jamais_le_jeton(monkeypatch):
    """Le jeton ne doit apparaître que dans l'en-tête Authorization,
    jamais dans le corps JSON envoyé (garde #304 étendue aux problèmes)."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        captured["headers"] = dict(req.header_items())
        return _FakeResponse(json.dumps({"rounds": [], "glicko": None}).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    puzzle_client.submit_puzzle_result("lip_super_secret_token", "abcd1", win=True)
    assert b"lip_super_secret_token" not in captured["body"]
    assert captured["headers"].get("Authorization") == "Bearer lip_super_secret_token"


# ── test_token : droits des problèmes ───────────────────────────────────────

def test_test_token_signale_les_droits_des_problemes(monkeypatch):
    body = json.dumps({
        "lip_x": {"scopes": "board:play,puzzle:read,puzzle:write", "userId": "alain"},
    }).encode("utf-8")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = lichess_client.test_token("lip_x")
    assert result["has_puzzle_read"] is True
    assert result["has_puzzle_write"] is True


def test_test_token_sans_droits_des_problemes(monkeypatch):
    body = json.dumps({"lip_x": {"scopes": "board:play", "userId": "alain"}}).encode("utf-8")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = lichess_client.test_token("lip_x")
    assert result["has_puzzle_read"] is False
    assert result["has_puzzle_write"] is False
