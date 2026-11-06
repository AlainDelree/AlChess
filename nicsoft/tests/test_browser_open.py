"""
nicsoft/tests/test_browser_open.py — NicLink
Test de `_maybe_open_browser` (issue #289) : aucun lancement sans
utilisateur (ALCHESS_SKIP_BOARD) ni vérification explicite sans navigateur
(ALCHESS_NO_BROWSER) ne doit ouvrir d'onglet. Aucun serveur n'est démarré —
`webbrowser.open` est systématiquement mocké.
"""
from unittest.mock import patch

from nicsoft.web.alchess import _maybe_open_browser


def test_ouvre_le_navigateur_sans_variable_positionnee(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    monkeypatch.delenv("ALCHESS_NO_BROWSER", raising=False)
    with patch("webbrowser.open") as mock_open:
        _maybe_open_browser("http://127.0.0.1:5000")
    mock_open.assert_called_once_with("http://127.0.0.1:5000")


def test_n_ouvre_rien_avec_alchess_skip_board(monkeypatch):
    monkeypatch.setenv("ALCHESS_SKIP_BOARD", "1")
    monkeypatch.delenv("ALCHESS_NO_BROWSER", raising=False)
    with patch("webbrowser.open") as mock_open:
        _maybe_open_browser("http://127.0.0.1:5000")
    mock_open.assert_not_called()


def test_n_ouvre_rien_avec_alchess_no_browser(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    monkeypatch.setenv("ALCHESS_NO_BROWSER", "1")
    with patch("webbrowser.open") as mock_open:
        _maybe_open_browser("http://127.0.0.1:5000")
    mock_open.assert_not_called()


def test_n_ouvre_rien_avec_les_deux_variables(monkeypatch):
    monkeypatch.setenv("ALCHESS_SKIP_BOARD", "1")
    monkeypatch.setenv("ALCHESS_NO_BROWSER", "1")
    with patch("webbrowser.open") as mock_open:
        _maybe_open_browser("http://127.0.0.1:5000")
    mock_open.assert_not_called()
