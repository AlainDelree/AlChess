"""
Découverte automatique des fichiers Python soumis à la règle ARC-001
(issue #272, suite #263/#264). Partagé par test_no_web_import.py,
test_ihm_port_contract.py et test_no_undefined_names.py pour qu'un nouveau
fichier ajouté dans un dossier de jeu (par ex. lors d'un découpage de
fichier) soit automatiquement couvert, sans mise à jour manuelle d'une
liste écrite à la main.
"""
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Dossiers soumis à ARC-001 : le moteur ne doit jamais importer nicsoft.web.
# La couche web elle-même (nicsoft/web/) est exclue, ainsi que les tests.
DOSSIERS_SURVEILLES = ["core", "modes", "niclink", "utils", "engine"]

# Garde-fou (demande #272, point 3) : quelques fichiers connus pour qu'une
# découverte cassée (chemin faux, dossier qui ne se parcourt plus, liste
# vide) ne passe jamais inaperçue.
FICHIERS_CONNUS_ATTENDUS = [
    "nicsoft/core/game_manager.py",
    "nicsoft/niclink/virtual_board.py",
]


def _chemin_relatif_posix(chemin: pathlib.Path) -> str:
    return chemin.relative_to(REPO_ROOT).as_posix()


def decouvrir_fichiers_py() -> list:
    """Tous les .py des dossiers de jeu, triés, en chemins relatifs posix
    (ex. "nicsoft/core/game_manager.py"). Exclut __pycache__ et tout ce qui
    n'est pas un fichier source (pas de .pyc, pas de fichiers générés)."""
    fichiers = []
    for dossier in DOSSIERS_SURVEILLES:
        racine = REPO_ROOT / "nicsoft" / dossier
        for chemin in racine.rglob("*.py"):
            if "__pycache__" in chemin.parts:
                continue
            fichiers.append(_chemin_relatif_posix(chemin))
    return sorted(fichiers)


def chemin_vers_module(chemin_relatif: str) -> str:
    """Convertit un chemin relatif ("nicsoft/core/game_manager.py") en nom
    de module pointé importable ("nicsoft.core.game_manager"). Un
    __init__.py désigne le paquet lui-même ("nicsoft/niclink/__init__.py"
    -> "nicsoft.niclink")."""
    sans_ext = chemin_relatif[: -len(".py")]
    parties = sans_ext.split("/")
    if parties[-1] == "__init__":
        parties = parties[:-1]
    return ".".join(parties)


def verifier_decouverte_non_cassee(fichiers: list) -> None:
    """Une découverte qui retourne une liste vide, ou qui perd un dossier
    entier en silence, ne doit jamais passer inaperçue (demande #272,
    point 3)."""
    assert fichiers, (
        "découverte ARC-001 vide — vérifier DOSSIERS_SURVEILLES et REPO_ROOT "
        "dans nicsoft/tests/_arc001_discovery.py"
    )
    manquants = [f for f in FICHIERS_CONNUS_ATTENDUS if f not in fichiers]
    assert not manquants, (
        f"découverte ARC-001 cassée — fichiers connus absents du résultat : {manquants}"
    )
