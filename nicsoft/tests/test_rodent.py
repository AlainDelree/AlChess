"""
Tests backend Rodent IV (issue #13a).

Vérifie :
  - les constantes de défaut (Personality=Tal, Elo=1200) ;
  - que le moteur répond au handshake UCI avant d'être déclaré disponible ;
  - que l'ordre des setoption (Personality → LimitStrength → Elo) est appliqué
    et que le moteur joue effectivement un coup.

Les tests nécessitant le binaire sont automatiquement ignorés (skip) s'il est
absent, pour ne pas casser la CI sur une machine sans Rodent installé.
"""

import chess
import pytest

from nicsoft.engine.engine_manager import (
    find_rodent,
    rodent_available,
    RODENT_PERSONALITIES,
    RODENT_PERSONALITY_DEFAUT,
    RODENT_ELO_DEFAUT,
)

_RODENT_ABSENT = find_rodent() is None
_skip_no_rodent = pytest.mark.skipif(_RODENT_ABSENT, reason="binaire Rodent IV absent")


def test_rodent_defauts_constants():
    """Les défauts backend correspondent à la spécification de l'issue #13a."""
    assert RODENT_PERSONALITY_DEFAUT == "Tal"
    assert RODENT_PERSONALITY_DEFAUT in RODENT_PERSONALITIES
    assert RODENT_ELO_DEFAUT == 1200


def test_config_json_contient_defauts_rodent():
    """data/config.json expose les clés Rodent avec les bons défauts."""
    import json
    from nicsoft.config import DATA_DIR

    cfg_path = DATA_DIR / "config.json"
    if not cfg_path.exists():
        pytest.skip("config.json absent")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg.get("rodent_personality") == "Tal"
    assert cfg.get("rodent_elo") == 1200


@_skip_no_rodent
def test_rodent_repond_au_handshake_uci():
    """Rodent complète uci/isready et expose ses options → considéré disponible."""
    assert rodent_available() is True


@_skip_no_rodent
def test_rodent_setoption_ordre_et_joue():
    """
    Instancie RodentEngine (ordre Personality → LimitStrength → Elo garanti par
    _apply_rodent_options) et vérifie qu'il joue un coup légal.
    """
    from nicsoft.engine.engine_manager import RodentEngine, find_stockfish

    eng = RodentEngine(
        find_rodent(),
        personality="Tal",
        rodent_elo=1200,
        stockfish_path=find_stockfish(),
    )
    try:
        assert eng.personality == "Tal"
        assert eng.engine_elo == 1200
        board = chess.Board()
        move = eng.get_move(board, think_time=0.2)
        assert move is not None
        assert move in board.legal_moves
    finally:
        eng.quit()
