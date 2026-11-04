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

import socket
import urllib.error
from unittest.mock import patch

import chess
import pytest

from nicsoft.engine.engine_manager import (
    find_rodent,
    rodent_available,
    RODENT_PERSONALITIES,
    RODENT_PERSONALITY_DEFAUT,
    RODENT_ELO_DEFAUT,
)
from nicsoft.web.server import _telecharger_fichier_rodent, _RODENT_WIN_SHA256

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


# ── Téléchargement Windows (issue #256) : délai d'attente + intégrité ──────────

def test_telecharger_fichier_rodent_delai_depasse(tmp_path):
    """Un serveur injoignable (délai dépassé) lève une erreur, sans fichier créé."""
    dest = tmp_path / "rodent-iv-x64.exe"
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError(socket.timeout("timed out")),
    ):
        with pytest.raises(urllib.error.URLError):
            _telecharger_fichier_rodent("https://example.invalid/rodent-iv-x64.exe", dest)
    assert not dest.exists()


def test_telecharger_fichier_rodent_empreinte_invalide(tmp_path):
    """Un contenu téléchargé dont l'empreinte ne correspond pas à la référence
    est supprimé et signalé en erreur — jamais installé."""
    dest = tmp_path / "rodent-iv-x64.exe"

    class _FakeResponse:
        def __init__(self, data):
            self._data = data

        def read(self, _n):
            data, self._data = self._data, b""
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("urllib.request.urlopen", return_value=_FakeResponse(b"contenu altere")):
        with pytest.raises(ValueError, match="[Ee]mpreinte"):
            _telecharger_fichier_rodent("https://example.invalid/rodent-iv-x64.exe", dest)
    assert not dest.exists()


def test_telecharger_fichier_rodent_sans_reference_connue(tmp_path):
    """Un nom de fichier sans empreinte de référence connue est refusé d'emblée,
    sans requête réseau (on ne doit jamais installer sans vérification possible)."""
    dest = tmp_path / "fichier-inconnu.dll"
    with patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(ValueError, match="[Aa]ucune empreinte"):
            _telecharger_fichier_rodent("https://example.invalid/fichier-inconnu.dll", dest)
    mock_urlopen.assert_not_called()
    assert not dest.exists()


def test_telecharger_fichier_rodent_empreinte_valide(tmp_path):
    """Un contenu dont l'empreinte correspond à la référence est accepté et écrit."""
    dest = tmp_path / "rodent-iv-x64.exe"
    # Contenu fabriqué pour matcher une référence de test dédiée (évite de
    # dépendre du vrai binaire, volumineux et non lisible dans ce test).
    contenu = b"binaire de test"
    import hashlib
    empreinte = hashlib.sha256(contenu).hexdigest()

    class _FakeResponse:
        def __init__(self, data):
            self._data = data

        def read(self, _n):
            data, self._data = self._data, b""
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch.dict(_RODENT_WIN_SHA256, {"rodent-iv-x64.exe": empreinte}):
        with patch("urllib.request.urlopen", return_value=_FakeResponse(contenu)):
            _telecharger_fichier_rodent("https://example.invalid/rodent-iv-x64.exe", dest)
    assert dest.read_bytes() == contenu
