"""
nicsoft/tests/test_issue312_server_startup.py — AlChess

Issue #312 : le serveur de test (nicsoft/tests/e2e/conftest.py) pouvait
rester bloqué indéfiniment en lisant la sortie du serveur AlChess de façon
bloquante — la ligne d'adresse ("[NicLink] Interface disponible sur
http://...") avait en plus disparu de la sortie Werkzeug, redirigée ou non,
à cause d'un effet de bord du logger "niclink.lichess" (#311).

(a) lance réellement le serveur (sortie redirigée, comme le fait la
    fixture e2e) et vérifie que la ligne d'adresse apparaît en moins de
    10s, via une lecture à limite de temps réelle (pas de stdout.readline()
    bloquant hors timeout).
(b) teste wait_for_server_url()/_start_line_reader() avec un faux process
    silencieux : l'échec doit survenir avant la limite passée en paramètre,
    et le process doit être arrêté (terminate() puis kill()).

Sans matériel (ALCHESS_SKIP_BOARD=1), sans navigateur (ALCHESS_NO_BROWSER=1,
BROWSER=/bin/true), sans écriture dans les vrais dossiers de l'utilisateur
(ALCHESS_DIR pointé vers tmp_path). ALCHESS_SKIP_SINGLE_INSTANCE=1 en plus
(#324) : ce test ne porte pas sur la vérification d'instance unique (#320),
qui n'a donc pas à s'exécuter ici.
"""
import os
import subprocess
import sys
import threading
import time

import pytest

from nicsoft.tests.e2e.conftest import _kill_process, _start_line_reader, wait_for_server_url

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.slow
def test_adresse_affichee_en_moins_de_10s_sortie_redirigee(tmp_path):
    env = os.environ.copy()
    env["BROWSER"] = "/bin/true"
    env["ALCHESS_SKIP_BOARD"] = "1"
    env["ALCHESS_NO_BROWSER"] = "1"
    env["ALCHESS_DIR"] = str(tmp_path)  # jamais le dossier réel de l'utilisateur
    env["ALCHESS_SKIP_SINGLE_INSTANCE"] = "1"  # ne teste pas #320 — protection #324

    proc = subprocess.Popen(
        [sys.executable, "-m", "nicsoft.web"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_DIR,
        env=env,
    )
    try:
        line_queue = _start_line_reader(proc.stdout)
        start = time.time()
        url, lines = wait_for_server_url(proc, line_queue, timeout_s=10)
        elapsed = time.time() - start

        assert elapsed < 10
        assert url.startswith("http://127.0.0.1:")
        assert any("[NicLink] Interface disponible sur" in l for l in lines)
    finally:
        _kill_process(proc)


class _SilentStream:
    """Simule la sortie d'un process qui ne produit jamais de ligne — son
    readline() bloque pour toujours (comme un pipe ouvert sans écriture)."""

    def __init__(self):
        self._never = threading.Event()

    def readline(self):
        self._never.wait()
        return ""


class _FakeSilentProcess:
    """Faux subprocess.Popen qui ne se termine que lorsqu'on l'y force
    (terminate() seul ne suffit pas — il faut kill()), pour prouver que
    _kill_process()/wait_for_server_url() vont bien jusqu'au kill()."""

    def __init__(self):
        self.terminate_called = False
        self.kill_called = False
        self._exited = False

    def poll(self):
        return 0 if self._exited else None

    def terminate(self):
        self.terminate_called = True

    def kill(self):
        self.kill_called = True
        self._exited = True

    def wait(self, timeout=None):
        if not self._exited:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        return 0


def test_wait_for_server_url_echoue_avant_la_limite_et_arrete_le_process():
    proc = _FakeSilentProcess()
    line_queue = _start_line_reader(_SilentStream())

    start = time.time()
    with pytest.raises(RuntimeError, match="non trouvée"):
        wait_for_server_url(proc, line_queue, timeout_s=0.5)
    elapsed = time.time() - start

    # échoue vite (proche de la limite passée en paramètre), jamais bloqué
    # jusqu'à un vrai timeout de plusieurs minutes.
    assert elapsed < 2.0
    assert proc.terminate_called
    assert proc.kill_called
