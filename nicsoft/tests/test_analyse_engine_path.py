"""
Teste que analyser_partie() ignore un chemin de moteur sauvegardé qui
n'existe pas sur cette machine et retombe sur find_stockfish() (issue #262).
"""

import json

import nicsoft.core.config_manager as config_manager
import nicsoft.engine.analyse as analyse_module
import nicsoft.engine.engine_manager as engine_manager_module


class _FakeEngineManager:
    """Remplace EngineManager pour ne jamais lancer de vrai moteur."""

    last_engine_path = None

    def __init__(self, engine_path, engine_elo=1500, analyse_active=True):
        _FakeEngineManager.last_engine_path = engine_path

    def analyser_partie(self, moves_uci, callback=None):
        return []

    def quit(self):
        pass


def _write_config(tmp_path, monkeypatch, engine_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"engine_path": engine_path}), encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_FILE", config_path)


def _patch_moteur(monkeypatch):
    monkeypatch.setattr(analyse_module, "EngineManager", _FakeEngineManager)
    monkeypatch.setattr(engine_manager_module, "find_stockfish", lambda: "/fake/stockfish")


def test_chemin_sauvegarde_inexistant_retombe_sur_find_stockfish(tmp_path, monkeypatch):
    _patch_moteur(monkeypatch)
    _write_config(tmp_path, monkeypatch, "/chemin/qui/n/existe/pas/stockfish")

    analyse_module.analyser_partie([], niveau=5)

    assert _FakeEngineManager.last_engine_path == "/fake/stockfish"


def test_chemin_sauvegarde_existant_est_conserve(tmp_path, monkeypatch):
    _patch_moteur(monkeypatch)
    real_engine = tmp_path / "stockfish_bin"
    real_engine.write_text("", encoding="utf-8")
    _write_config(tmp_path, monkeypatch, str(real_engine))

    analyse_module.analyser_partie([], niveau=5)

    assert _FakeEngineManager.last_engine_path == str(real_engine)


def test_chemin_vide_comportement_inchange(tmp_path, monkeypatch):
    _patch_moteur(monkeypatch)
    _write_config(tmp_path, monkeypatch, "")

    analyse_module.analyser_partie([], niveau=5)

    assert _FakeEngineManager.last_engine_path == "/fake/stockfish"
