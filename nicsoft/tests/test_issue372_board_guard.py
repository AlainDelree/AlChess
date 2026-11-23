"""
nicsoft/tests/test_issue372_board_guard.py — AlChess

Issue #372 : l'échiquier Chessnut réel bippait pendant la suite de tests
(hook pre-push, issues CCL) alors qu'AlChess était fermé — preuve qu'au
moins un test atteignait le vrai périphérique USB. Ce fichier vérifie le
garde ajouté dans conftest.py (`_guard_no_real_board_access`) : toute
tentative d'ouverture/énumération réelle (hid.device()/hid.enumerate(),
seul point d'entrée de nicsoft/niclink/hid_backend.py vers le matériel)
doit faire échouer le test fautif avec un message qui le nomme, et les
tests marqués "hardware" doivent en rester exemptés.

Jamais d'accès matériel réel ici, même pour "vérifier" : la vérification
se fait entièrement par logiciel (l'exception levée par le garde, ou une
comparaison d'identité pour l'exemption "hardware").
"""
import subprocess

import hid
import pytest

from nicsoft.niclink import hid_backend
from nicsoft.tests import conftest
from nicsoft.tests.conftest import (
    ORIGINAL_HID_DEVICE,
    ORIGINAL_HID_ENUMERATE,
    RealBoardAccessError,
)


def test_hid_device_bloque_hors_marqueur_hardware():
    with pytest.raises(RealBoardAccessError, match=r"hid\.device\(\)"):
        hid.device()


def test_hid_enumerate_bloque_hors_marqueur_hardware():
    with pytest.raises(RealBoardAccessError, match=r"hid\.enumerate\(\)"):
        hid.enumerate(0x2d80, 0)


def test_message_du_garde_nomme_le_test_fautif(request):
    with pytest.raises(RealBoardAccessError) as exc_info:
        hid.device()
    assert request.node.nodeid in str(exc_info.value)


def test_connect_hid_backend_bloque_par_le_garde():
    """Le chemin réel (hid_backend.connect(), appelé par NicLinkManager via
    board_adapter.create_board(virtual=False)) doit lui aussi échouer — pas
    seulement un appel direct à hid.device(). connect() énumère d'abord les
    chemins USB (hid.enumerate()) avant d'ouvrir un handle : c'est donc ce
    premier appel que le garde intercepte ici."""
    with pytest.raises(RealBoardAccessError, match=r"hid\.enumerate\(\)"):
        hid_backend.connect()


def test_check_physically_present_ne_peut_pas_absorber_le_garde():
    """hid_backend.check_physically_present() attrape `except Exception`
    autour de hid.enumerate() — le garde (BaseException, pas Exception)
    doit malgré tout traverser cet attrape-tout générique plutôt que de se
    laisser réduire silencieusement à False."""
    with pytest.raises(RealBoardAccessError):
        hid_backend.check_physically_present()


def test_guard_subprocess_force_alchess_skip_board_env_fourni(monkeypatch):
    """Filet de sécurité subprocess (issue #372) : ALCHESS_SKIP_BOARD=1 est
    posé dans l'env de tout sous-processus, même si le test fournit déjà un
    env explicite sans cette clé — jamais de vrai sous-processus lancé ici,
    `subprocess.Popen` réel est lui-même remplacé par un faux qui capture
    ses kwargs."""
    captured = {}

    def _fake_original_popen(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(conftest, "_ORIGINAL_POPEN", _fake_original_popen)
    subprocess.Popen(["true"], env={"FOO": "bar"})
    assert captured["env"]["ALCHESS_SKIP_BOARD"] == "1"
    assert captured["env"]["FOO"] == "bar"


def test_guard_subprocess_force_alchess_skip_board_sans_env(monkeypatch):
    """Même garde, env=None (héritage de l'environnement du process de
    test) : la clé doit malgré tout être posée dans la copie transmise au
    sous-processus."""
    captured = {}

    def _fake_original_popen(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(conftest, "_ORIGINAL_POPEN", _fake_original_popen)
    subprocess.Popen(["true"])
    assert captured["env"]["ALCHESS_SKIP_BOARD"] == "1"


@pytest.mark.hardware
def test_marqueur_hardware_exempte_du_garde():
    """Un test marqué "hardware" n'est pas neutralisé par le garde — vérifié
    par comparaison d'identité avec les objets hidapi capturés avant tout
    monkeypatch, jamais par un vrai appel hid.device()/hid.enumerate() (ce
    test n'est de toute façon jamais exécuté en suite normale ni en CI,
    voir pytest.ini). Même vérification pour le filet de sécurité
    subprocess (issue #372) : `subprocess.Popen` reste le vrai, jamais
    remplacé par la version qui force ALCHESS_SKIP_BOARD=1."""
    assert hid.device is ORIGINAL_HID_DEVICE
    assert hid.enumerate is ORIGINAL_HID_ENUMERATE
    assert subprocess.Popen is conftest._ORIGINAL_POPEN
