"""
Test de noms non définis (issue #264, suite #263 ; découverte automatique
#272) — équivalent restreint de l'outil pyflakes ("undefined name"),
implémenté avec le seul module standard ast (pas de nouvelle dépendance de
test).

Principe : pour chaque fichier des dossiers de jeu (découverts
automatiquement par _arc001_discovery.py), on collecte TOUTES les identités
liées n'importe où dans le fichier (imports, def/class, paramètres, cibles
d'assignation/for/with/except, walrus, ...) et on vérifie que chaque
identifiant simplement lu (ast.Name en contexte Load) appartient à cet
ensemble ou aux builtins. Ce test n'effectue pas de résolution de portée
fine comme pyflakes (il ne peut donc pas détecter une variable utilisée hors
de sa portée réelle alors qu'elle existe ailleurs dans le fichier) — mais il
détecte exactement la régression visée : un nom qui n'est lié NULLE PART
dans le fichier (reste d'une variable interne de l'ancien nicsoft.web après
découplage), comme l'a été `_game_state` dans pedagogique.py (issue #264).
"""
import ast
import builtins

import pytest

from nicsoft.tests._arc001_discovery import (
    REPO_ROOT,
    decouvrir_fichiers_py,
    verifier_decouverte_non_cassee,
)

_TOUS_LES_FICHIERS = decouvrir_fichiers_py()
verifier_decouverte_non_cassee(_TOUS_LES_FICHIERS)

# Noms disponibles implicitement dans tout module, sans liaison explicite.
NOMS_IMPLICITES = {
    "__name__", "__file__", "__doc__", "__package__", "__builtins__",
    "__spec__", "__loader__", "__cached__", "__annotations__", "__class__",
    "__path__", "__dict__", "__module__", "__qualname__",
}
BUILTINS_NAMES = set(dir(builtins))


def _collect_arg_names(args: ast.arguments):
    names = set()
    for group in (args.posonlyargs, args.args, args.kwonlyargs):
        names.update(a.arg for a in group)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _noms_non_definis(source: str, filename: str) -> list:
    """Retourne la liste des (nom, lineno) lus mais liés nulle part dans le fichier."""
    tree = ast.parse(source, filename=filename)

    bound = set(NOMS_IMPLICITES)
    loaded = []  # (name, lineno)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node.ctx, ast.Load):
                loaded.append((node.id, node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            bound.update(_collect_arg_names(node.args))
        elif isinstance(node, ast.Lambda):
            bound.update(_collect_arg_names(node.args))
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            bound.update(node.names)
        # match/case (3.10+) : capture de motifs — bonus, sans effet si absent du fichier.
        elif node.__class__.__name__ == "MatchAs" and getattr(node, "name", None):
            bound.add(node.name)
        elif node.__class__.__name__ == "MatchStar" and getattr(node, "name", None):
            bound.add(node.name)
        elif node.__class__.__name__ == "MatchMapping" and getattr(node, "rest", None):
            bound.add(node.rest)

    undefined = [
        (name, lineno) for name, lineno in loaded
        if name not in bound and name not in BUILTINS_NAMES
    ]
    return undefined


@pytest.mark.parametrize("chemin_relatif", _TOUS_LES_FICHIERS)
def test_pas_de_nom_non_defini(chemin_relatif):
    """Aucun identifiant lu dans le fichier ne doit être totalement non lié
    (reste d'une référence à nicsoft.web supprimée par la #263)."""
    chemin = REPO_ROOT / chemin_relatif
    source = chemin.read_text(encoding="utf-8")
    undefined = _noms_non_definis(source, str(chemin))
    assert undefined == [], (
        f"{chemin_relatif} : nom(s) non défini(s) détecté(s) — {undefined}"
    )


def test_decouverte_couvre_les_dossiers_de_jeu():
    """Garde-fou (#272) : la découverte ne doit jamais retourner une liste
    vide ni perdre silencieusement un fichier connu."""
    verifier_decouverte_non_cassee(_TOUS_LES_FICHIERS)
    assert len(_TOUS_LES_FICHIERS) >= 20
