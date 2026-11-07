"""
nicsoft/tests/test_modem_manager_skip_board.py — NicLink
Suite #289 (issue #291) : un lancement sans échiquier (ALCHESS_SKIP_BOARD=1,
ex. tests de bout en bout) ne doit jamais toucher à ModemManager — ni
l'arrêter au démarrage, ni le relancer aux sorties propres. Sans la
variable, comportement strictement inchangé. Aucun serveur n'est démarré et
le vrai service n'est jamais sollicité : stop_modem_manager/
start_modem_manager sont systématiquement mockées.
"""
from unittest.mock import patch

from nicsoft.web.alchess import _stop_modem_manager, _start_modem_manager


def test_stop_appele_sans_variable_positionnee(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    with patch("nicsoft.web.alchess.stop_modem_manager") as mock_stop:
        _stop_modem_manager()
    mock_stop.assert_called_once()


def test_stop_non_appele_avec_alchess_skip_board(monkeypatch):
    monkeypatch.setenv("ALCHESS_SKIP_BOARD", "1")
    with patch("nicsoft.web.alchess.stop_modem_manager") as mock_stop:
        _stop_modem_manager()
    mock_stop.assert_not_called()


def test_start_appele_sans_variable_positionnee(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    with patch("nicsoft.web.alchess.start_modem_manager") as mock_start:
        _start_modem_manager()
    mock_start.assert_called_once()


def test_start_non_appele_avec_alchess_skip_board(monkeypatch):
    monkeypatch.setenv("ALCHESS_SKIP_BOARD", "1")
    with patch("nicsoft.web.alchess.start_modem_manager") as mock_start:
        _start_modem_manager()
    mock_start.assert_not_called()
