"""
nicsoft/tests/test_no_orphan_gitmodules.py — NicLink
Issue #293 : garde contre un .gitmodules qui déclarerait un chemin non
réellement suivi comme sous-module par l'index git — le cas qui a fait
échouer un `git submodule update --init` sur un clone neuf avant la
suppression des cinq entrées vestigiales. Si .gitmodules n'existe pas
(cas normal depuis cette issue), rien à vérifier. Ignoré proprement si
git n'est pas disponible : uniquement du git local, aucun réseau.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GITMODULES = REPO_ROOT / ".gitmodules"


def _declared_submodule_paths():
    # Lu via `git config`, le même parseur que git utilise pour .gitmodules
    # (tolérant aux indentations irrégulières, contrairement à configparser).
    result = subprocess.run(
        ["git", "config", "--file", str(GITMODULES), "--get-regexp", r"\.path$"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.split(" ", 1)[1] for line in result.stdout.splitlines() if line]


@pytest.mark.skipif(shutil.which("git") is None, reason="git non disponible")
def test_gitmodules_paths_sont_des_sous_modules_suivis():
    if not GITMODULES.exists():
        pytest.skip(".gitmodules absent — rien à vérifier")

    result = subprocess.run(
        ["git", "ls-files", "--stage"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("pas un dépôt git exploitable ici")

    tracked_submodule_paths = {
        line.split("\t", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("160000 ")
    }

    for path in _declared_submodule_paths():
        assert path in tracked_submodule_paths, (
            f"{path} déclaré dans .gitmodules mais absent de l'index git "
            "comme sous-module suivi (mode 160000)"
        )
