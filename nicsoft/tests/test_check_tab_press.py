"""
nicsoft/tests/test_check_tab_press.py — NicLink
Vérifie que check_tab_press() (nicsoft/engine/display.py) ne lève jamais
hors terminal — bug introduit par l'issue #288 (resserrement en
`(ImportError, OSError)`, alors que `termios.error` n'est PAS une
sous-classe d'OSError : il dérive directement d'Exception). Reproduit
sans aucun matériel ni réseau : entrée standard redirigée vers le
périphérique nul, fermée, ou absente (sys.stdin = None), les trois cas
réels évoqués par l'issue #290 (raccourci graphique, processus sans
terminal, tests lancés par un automate).
"""
import io
import sys

import pytest

from nicsoft.engine.display import check_tab_press


def test_entree_standard_redirigee_vers_null_ne_leve_pas(monkeypatch):
    with open("/dev/null") as devnull:
        monkeypatch.setattr(sys, "stdin", devnull)
        assert check_tab_press() is False


def test_entree_standard_fermee_ne_leve_pas(monkeypatch):
    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(sys, "stdin", closed)
    assert check_tab_press() is False


def test_entree_standard_absente_ne_leve_pas(monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    assert check_tab_press() is False


def test_entree_standard_sans_fileno_ne_leve_pas(monkeypatch):
    class _SansFileno:
        pass

    monkeypatch.setattr(sys, "stdin", _SansFileno())
    assert check_tab_press() is False


def test_termios_error_pendant_tcgetattr_ne_leve_pas(monkeypatch):
    """Simule un terminal qui réussit isatty() mais où termios échoue
    quand même (cas réel historique du bug : termios.error n'est pas
    une sous-classe d'OSError)."""
    import termios

    monkeypatch.setattr("os.isatty", lambda fd: True)

    def _tcgetattr_leve(fd):
        raise termios.error("simulate: Inappropriate ioctl for device")

    monkeypatch.setattr(termios, "tcgetattr", _tcgetattr_leve)
    assert check_tab_press() is False
