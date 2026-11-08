"""
nicsoft/tests/test_issue299_modem_manager_shutdown.py — NicLink
Issue #299, point 2 : ModemManager doit être relancé à TOUTE sortie du
processus (quitter, Ctrl+C, signal de terminaison SIGTERM/SIGHUP), pas
seulement aux deux sorties « propres » déjà couvertes par
test_modem_manager_skip_board.py. Aucun matériel ni réseau requis — tous
les appels système (sudo/systemctl) sont mockés.

Limite documentée dans le code (nicsoft/web/alchess.py,
_ensure_modem_manager_restarted) et non testée ici : un arrêt brutal
(SIGKILL) ne peut être intercepté par aucun code Python.
"""
import signal as signal_module

import pytest
from unittest.mock import patch

from nicsoft.web import alchess


@pytest.fixture(autouse=True)
def _reset_modem_restart_flag():
    """Le drapeau anti-double-relance est un état de module — le remettre à
    zéro avant et après chaque test pour ne pas contaminer les suivants."""
    alchess._modem_restarted = False
    yield
    alchess._modem_restarted = False


# ── Relance garantie, une seule fois ────────────────────────────────────────

def test_ensure_restart_appelle_start_modem_manager(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    with patch("nicsoft.web.alchess.start_modem_manager") as mock_start:
        alchess._ensure_modem_manager_restarted()
    mock_start.assert_called_once()


def test_ensure_restart_pas_de_double_relance(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    with patch("nicsoft.web.alchess.start_modem_manager") as mock_start:
        alchess._ensure_modem_manager_restarted()
        alchess._ensure_modem_manager_restarted()
    mock_start.assert_called_once()


def test_ensure_restart_sans_effet_avec_alchess_skip_board(monkeypatch):
    monkeypatch.setenv("ALCHESS_SKIP_BOARD", "1")
    with patch("nicsoft.web.alchess.start_modem_manager") as mock_start:
        alchess._ensure_modem_manager_restarted()
    mock_start.assert_not_called()


# ── Signal de terminaison simulé ────────────────────────────────────────────

def test_handle_termination_signal_relance_puis_sort(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    with patch("nicsoft.web.alchess.start_modem_manager") as mock_start:
        with pytest.raises(SystemExit) as exc_info:
            alchess._handle_termination_signal(signal_module.SIGTERM, None)
        mock_start.assert_called_once()
    assert exc_info.value.code == 0


def test_handle_termination_signal_ne_relance_pas_deux_fois_apres_sortie_propre(monkeypatch):
    """Simule une sortie « propre » (quitter/Ctrl+C) suivie d'un signal de
    terminaison pour la même exécution — ne doit relancer qu'une fois."""
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    with patch("nicsoft.web.alchess.start_modem_manager") as mock_start:
        alchess._ensure_modem_manager_restarted()  # sortie propre déjà exécutée
        with pytest.raises(SystemExit):
            alchess._handle_termination_signal(signal_module.SIGTERM, None)
    mock_start.assert_called_once()


# ── Enregistrement à l'arrêt normal de l'interpréteur (atexit) et sur les signaux

def test_register_shutdown_handlers_enregistre_atexit_et_signaux():
    with patch("nicsoft.web.alchess.atexit.register") as mock_atexit, \
         patch("nicsoft.web.alchess.signal.signal") as mock_signal:
        alchess._register_modem_manager_shutdown_handlers()

    mock_atexit.assert_called_once_with(alchess._ensure_modem_manager_restarted)
    appels = {c.args[0]: c.args[1] for c in mock_signal.call_args_list}
    assert appels.get(signal_module.SIGTERM) is alchess._handle_termination_signal
    if hasattr(signal_module, "SIGHUP"):
        assert appels.get(signal_module.SIGHUP) is alchess._handle_termination_signal
