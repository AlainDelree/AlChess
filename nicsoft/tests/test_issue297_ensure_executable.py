"""
nicsoft/tests/test_issue297_ensure_executable.py — NicLink
Vérifie que _ensure_executable() ne donne le bit exécutable qu'au
propriétaire (issue #297 — application locale mono-utilisateur, le droit
d'exécution n'a pas besoin d'être étendu au groupe ni aux autres).

Purement local (fichiers temporaires), sans réseau ni matériel. Ignoré sous
Windows, où la fonction est un no-op (bits POSIX non pertinents).
"""
import os
import stat
import sys

import pytest

from nicsoft.engine.engine_detection import _ensure_executable

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bits POSIX non pertinents sous Windows")


def test_ajoute_seulement_le_bit_proprietaire(tmp_path):
    """Un fichier sans aucun droit d'exécution reçoit S_IXUSR mais ni
    S_IXGRP ni S_IXOTH."""
    chemin = tmp_path / "binaire"
    chemin.write_text("faux binaire")
    os.chmod(chemin, stat.S_IRUSR | stat.S_IWUSR)

    _ensure_executable(str(chemin))

    mode = os.stat(chemin).st_mode
    assert mode & stat.S_IXUSR
    assert not (mode & stat.S_IXGRP)
    assert not (mode & stat.S_IXOTH)


def test_ne_modifie_pas_si_proprietaire_deja_executable(tmp_path):
    """Un fichier qui a déjà le droit du propriétaire n'est pas modifié."""
    chemin = tmp_path / "binaire"
    chemin.write_text("faux binaire")
    os.chmod(chemin, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    mode_avant = os.stat(chemin).st_mode

    _ensure_executable(str(chemin))

    assert os.stat(chemin).st_mode == mode_avant


def test_chemin_inexistant_sans_exception(tmp_path):
    """Un chemin inexistant n'élève pas d'exception (juste un avertissement loggé)."""
    chemin = tmp_path / "absent"
    _ensure_executable(str(chemin))
