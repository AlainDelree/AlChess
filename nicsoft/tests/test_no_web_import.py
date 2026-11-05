"""
Test d'isolation (issue #263, découverte automatique #272) — verrouille la
règle ARC-001 : les modules de jeu (core, modes, niclink, utils, engine) ne
doivent jamais importer nicsoft.web, à aucun niveau (import de module, ni au
niveau fonction).

Exécuté en sous-processus propre à chaque cas : si ce test tournait dans le
même interpréteur que test_app_state.py ou test_rodent.py (qui importent
nicsoft.web.server pour leurs propres besoins), sys.modules contiendrait
déjà nicsoft.web pour une raison indépendante du jeu, et le test ne
prouverait plus rien.

La liste des modules est découverte automatiquement (_arc001_discovery.py)
plutôt qu'écrite à la main, pour qu'un fichier ajouté — notamment lors d'un
découpage d'un gros fichier — soit couvert sans y penser.
"""
import subprocess
import sys

import pytest

from nicsoft.tests._arc001_discovery import (
    chemin_vers_module,
    decouvrir_fichiers_py,
    verifier_decouverte_non_cassee,
)

_FICHIERS = decouvrir_fichiers_py()
verifier_decouverte_non_cassee(_FICHIERS)

MODULES_SANS_WEB = sorted({chemin_vers_module(f) for f in _FICHIERS})


def _import_sans_web(module_names):
    code = "import sys\n" + "\n".join(f"import {m}" for m in module_names) + (
        "\nassert 'nicsoft.web' not in sys.modules, "
        "'nicsoft.web a été chargé — règle ARC-001 violée'\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30,
    )


def test_decouverte_couvre_les_dossiers_de_jeu():
    """Garde-fou (#272) : la découverte ne doit jamais retourner une liste
    vide ni perdre silencieusement un fichier connu."""
    verifier_decouverte_non_cassee(_FICHIERS)
    assert len(MODULES_SANS_WEB) >= 20


@pytest.mark.parametrize("module_name", MODULES_SANS_WEB)
def test_import_module_de_jeu_sans_nicsoft_web(module_name):
    """Importer ce module de jeu ne doit jamais charger nicsoft.web (ARC-001)."""
    result = _import_sans_web([module_name])
    assert result.returncode == 0, result.stderr


def test_import_tous_les_modules_de_jeu_ensemble_sans_nicsoft_web():
    """Même tous importés ensemble dans un seul process, nicsoft.web ne doit jamais apparaître."""
    result = _import_sans_web(MODULES_SANS_WEB)
    assert result.returncode == 0, result.stderr
