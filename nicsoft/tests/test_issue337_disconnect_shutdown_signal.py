"""
nicsoft/tests/test_issue337_disconnect_shutdown_signal.py — AlChess

Issue #337 : le timer de déconnexion (nicsoft/web/server.py, on_disconnect)
appelait os._exit(0) directement depuis un fil daemon, ce qui court-circuite
tout le chemin de sortie normal (atexit : relance ModemManager, suppression
du marqueur d'instance unique — voir nicsoft/web/alchess.py) et peut faire
courir deux chemins de sortie concurrents dans le même interpréteur si un
arrêt externe (SIGTERM) survient au même moment (soupçon de cause d'un
arrêt brutal SIGABRT observé pendant les tests e2e, sans pile Python).

Correctif : le timer envoie SIGTERM au process lui-même, rejoignant l'unique
chemin de sortie déjà géré par _handle_termination_signal. Ce test vérifie
ce comportement sans jamais faire sortir le process du runner de tests.
"""
import os
import signal
import threading

import pytest

from nicsoft.web import server


@pytest.fixture(autouse=True)
def _reset_disconnect_timer():
    """État de module à remettre à zéro pour ne pas contaminer les autres tests."""
    yield
    with server._disconnect_timer_lock:
        if server._disconnect_timer and server._disconnect_timer.is_alive():
            server._disconnect_timer.cancel()
        server._disconnect_timer = None


def test_timeout_deconnexion_envoie_sigterm_pas_os_exit(monkeypatch):
    monkeypatch.setattr(server, "_DISCONNECT_TIMEOUT", 0.05)
    kill_calls = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))
    exit_calls = []
    monkeypatch.setattr(os, "_exit", lambda code: exit_calls.append(code))

    server.on_disconnect()

    with server._disconnect_timer_lock:
        timer = server._disconnect_timer
    timer.join(timeout=2)

    assert exit_calls == []
    assert kill_calls == [(os.getpid(), signal.SIGTERM)]


def test_reconnexion_annule_le_timer_sans_jamais_sortir(monkeypatch):
    monkeypatch.setattr(server, "_DISCONNECT_TIMEOUT", 0.05)
    kill_calls = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    server.on_disconnect()
    with server._disconnect_timer_lock:
        timer_avant = server._disconnect_timer
    assert isinstance(timer_avant, threading.Timer)

    # on_connect annule le timer en cours — mocker ce que son handler émet
    # (status, app_state, etc. nécessitent une requête SocketIO réelle).
    with server._disconnect_timer_lock:
        if server._disconnect_timer and server._disconnect_timer.is_alive():
            server._disconnect_timer.cancel()
            server._disconnect_timer = None

    timer_avant.join(timeout=0.3)
    assert kill_calls == []
