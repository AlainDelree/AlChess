"""
nicsoft/tests/test_issue320_single_instance.py — AlChess

Issue #320 : une seule instance AlChess à la fois — la nouvelle remplace
l'ancienne sauf si une partie y est en cours.

Tous les tests utilisent de faux processus lancés par le test lui-même
(simples boucles `time.sleep`, jamais un vrai serveur AlChess) et un
DATA_DIR isolé (tmp_path, via monkeypatch de `single_instance.DATA_DIR` —
jamais le dossier réel de l'utilisateur). Aucun arrêt par nom de programme :
chaque arrêt se fait par le PID exact capturé à la création du
sous-processus, qu'il soit déclenché par le code sous test ou par le
nettoyage du test lui-même.
"""
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from nicsoft.tests.e2e.conftest import _kill_process, _start_line_reader, wait_for_server_url
from nicsoft.web import server
from nicsoft.web import single_instance

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(single_instance, "DATA_DIR", tmp_path)
    yield tmp_path


def _spawn_fake_process(with_alchess_marker: bool) -> int:
    """Lance un faux processus (simple boucle de sommeil) et retourne son
    PID. `with_alchess_marker=True` glisse la sous-chaîne "nicsoft.web" dans
    sa ligne de commande, pour simuler un vrai processus AlChess sans en
    lancer un — la détection ne doit jamais se fier au seul nom "python"."""
    tag = "nicsoft.web fake instance" if with_alchess_marker else "programme etranger sans lien"
    script = f"import time  # {tag}\ntime.sleep(60)\n"
    # Exécutable et script fixes, écrits par ce test, sans entrée externe.
    proc = subprocess.Popen([sys.executable, "-c", script])  # noqa: S603  # nosec B603
    return proc


def _wait_until(predicate, timeout_s=5.0, interval_s=0.1) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return predicate()


def _cleanup_pid(pid: int) -> None:
    """Nettoyage de fin de test — toujours par ce PID précis."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    _wait_until(lambda: not single_instance._pid_alive(pid), timeout_s=5.0)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# ── Cas 1 : aucune ancienne instance ───────────────────────────────────────────

def test_aucune_ancienne_instance_demarre():
    can_start, message = single_instance.resolve_startup()
    assert can_start is True
    assert message is None


# ── Cas 2 : marqueur périmé — processus mort ───────────────────────────────────

def test_fichier_perime_processus_mort():
    # Exécutable fixe, script trivial, sans entrée externe.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])  # noqa: S603  # nosec B603
    proc.wait(timeout=5)
    assert not single_instance._pid_alive(proc.pid)

    single_instance.write_marker(proc.pid, 5000, "2026-01-01T00:00:00")
    can_start, message = single_instance.resolve_startup()
    assert can_start is True
    assert message is None


# ── Cas 3 : PID réutilisé par un programme étranger — jamais touché ───────────

def test_pid_reutilise_par_programme_etranger_non_touche():
    proc = _spawn_fake_process(with_alchess_marker=False)
    try:
        single_instance.write_marker(proc.pid, 5999, "2026-01-01T00:00:00")
        can_start, message = single_instance.resolve_startup()
        assert can_start is True
        assert message is None
        # Le processus étranger ne doit jamais avoir été touché.
        assert proc.poll() is None
    finally:
        _cleanup_pid(proc.pid)


# ── Cas 4 : ancienne instance inactive → remplacée ─────────────────────────────

def test_ancienne_instance_inactive_remplacee(monkeypatch):
    proc = _spawn_fake_process(with_alchess_marker=True)
    try:
        single_instance.write_marker(proc.pid, 6001, "2026-01-01T00:00:00")
        monkeypatch.setattr(single_instance, "_query_state", lambda port: {"state": "menu"})

        can_start, message = single_instance.resolve_startup()

        assert can_start is True
        assert message is None
        assert _wait_until(lambda: proc.poll() is not None, timeout_s=8.0), (
            "l'ancienne instance inactive aurait dû être arrêtée par son PID"
        )
    finally:
        _cleanup_pid(proc.pid)


# ── Cas 5 : ancienne instance en partie → refusée, non touchée ────────────────

def test_ancienne_instance_en_partie_refusee(monkeypatch):
    proc = _spawn_fake_process(with_alchess_marker=True)
    try:
        single_instance.write_marker(proc.pid, 6002, "2026-01-01T00:00:00")
        monkeypatch.setattr(single_instance, "_query_state", lambda port: {"state": "playing"})

        can_start, message = single_instance.resolve_startup()

        assert can_start is False
        assert "6002" in message
        assert proc.poll() is None, "une partie en cours ne doit jamais être interrompue"
    finally:
        _cleanup_pid(proc.pid)


@pytest.mark.parametrize("etat", sorted(single_instance.BUSY_STATES))
def test_tous_les_etats_de_partie_refusent(monkeypatch, etat):
    proc = _spawn_fake_process(with_alchess_marker=True)
    try:
        single_instance.write_marker(proc.pid, 6003, "2026-01-01T00:00:00")
        monkeypatch.setattr(single_instance, "_query_state", lambda port: {"state": etat})

        can_start, message = single_instance.resolve_startup()

        assert can_start is False
        assert proc.poll() is None
    finally:
        _cleanup_pid(proc.pid)


# ── Cas 6 : état de l'ancienne instance impossible à confirmer → prudence ─────

def test_etat_impossible_a_confirmer_refuse_par_precaution(monkeypatch):
    proc = _spawn_fake_process(with_alchess_marker=True)
    try:
        single_instance.write_marker(proc.pid, 6004, "2026-01-01T00:00:00")
        monkeypatch.setattr(single_instance, "_query_state", lambda port: None)

        can_start, message = single_instance.resolve_startup()

        assert can_start is False
        assert message is not None
        assert proc.poll() is None
    finally:
        _cleanup_pid(proc.pid)


# ── write_marker / remove_marker ───────────────────────────────────────────────

def test_write_puis_remove_marker_round_trip(tmp_path):
    single_instance.write_marker(4242, 5001, "2026-01-01T00:00:00")
    marker_file = tmp_path / single_instance.MARKER_FILENAME
    assert marker_file.exists()
    data = json.loads(marker_file.read_text(encoding="utf-8"))
    assert data == {"pid": 4242, "port": 5001, "started_at": "2026-01-01T00:00:00"}

    single_instance.remove_marker(4242)
    assert not marker_file.exists()


def test_remove_marker_ne_supprime_pas_si_pid_different(tmp_path):
    """Une instance qui s'arrête ne doit pas effacer le marqueur d'une
    instance plus récente qui l'aurait déjà remplacée."""
    single_instance.write_marker(4242, 5001, "2026-01-01T00:00:00")
    single_instance.write_marker(9999, 5002, "2026-01-01T00:01:00")  # remplacement

    single_instance.remove_marker(4242)  # l'ancienne instance termine après coup

    marker_file = tmp_path / single_instance.MARKER_FILENAME
    assert marker_file.exists()
    data = json.loads(marker_file.read_text(encoding="utf-8"))
    assert data["pid"] == 9999


# ── Identification par ligne de commande (jamais par le seul nom) ─────────────

@pytest.mark.skipif(sys.platform == "win32", reason="lecture /proc — Linux uniquement")
def test_is_alchess_process_par_cmdline():
    proc = _spawn_fake_process(with_alchess_marker=True)
    try:
        assert single_instance._is_alchess_process(proc.pid) is True
    finally:
        _cleanup_pid(proc.pid)


@pytest.mark.skipif(sys.platform == "win32", reason="lecture /proc — Linux uniquement")
def test_is_alchess_process_faux_pour_programme_etranger():
    proc = _spawn_fake_process(with_alchess_marker=False)
    try:
        assert single_instance._is_alchess_process(proc.pid) is False
    finally:
        _cleanup_pid(proc.pid)


# ── Route /instance_status — interrogée par une nouvelle instance ────────────

@pytest.fixture
def client():
    server.set_server_port(5000)
    yield server.app.test_client()
    server.set_server_port(None)


def test_instance_status_host_etranger_refuse(client):
    r = client.get("/instance_status", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_instance_status_renvoie_pid_port_etat(client, monkeypatch):
    monkeypatch.setattr(server, "_app_state", "playing")
    r = client.get("/instance_status", headers={"Host": "127.0.0.1:5000"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["pid"] == os.getpid()
    assert data["port"] == 5000
    assert data["state"] == "playing"


# ── Intégration — deux vraies instances `python -m nicsoft.web` ──────────────
# Seul test de ce fichier à lancer de vrais sous-processus AlChess (toujours
# arrêtés par leur PID exact, jamais par leur nom) — sans matériel
# (ALCHESS_SKIP_BOARD=1), sans navigateur (ALCHESS_NO_BROWSER=1,
# BROWSER=/bin/true), dans un ALCHESS_DIR isolé (tmp_path), jamais le
# dossier réel de l'utilisateur.

@pytest.mark.slow
def test_integration_deuxieme_instance_remplace_la_premiere_restee_au_menu(tmp_path):
    env = os.environ.copy()
    env["BROWSER"] = "/bin/true"
    env["ALCHESS_SKIP_BOARD"] = "1"
    env["ALCHESS_NO_BROWSER"] = "1"
    env["ALCHESS_DIR"] = str(tmp_path)

    proc1 = subprocess.Popen(
        [sys.executable, "-m", "nicsoft.web"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        cwd=REPO_DIR, env=env,
    )
    proc2 = None
    try:
        queue1 = _start_line_reader(proc1.stdout)
        wait_for_server_url(proc1, queue1, timeout_s=20)
        time.sleep(1.5)  # laisser la première instance atteindre l'état "menu"
        assert proc1.poll() is None, "la première instance aurait dû rester active au menu"

        proc2 = subprocess.Popen(
            [sys.executable, "-m", "nicsoft.web"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            cwd=REPO_DIR, env=env,
        )
        queue2 = _start_line_reader(proc2.stdout)
        wait_for_server_url(proc2, queue2, timeout_s=20)

        # La première instance, inactive (menu), doit avoir été arrêtée par
        # la seconde — par son PID exact (proc1.wait réussit, pas de timeout).
        assert proc1.wait(timeout=10) == 0
    finally:
        _kill_process(proc1)
        if proc2 is not None:
            _kill_process(proc2)
