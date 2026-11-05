"""
Test de contrat du port neutre (issue #264, suite #263 ; découverte
automatique #272).

La #263 a découplé les modules de jeu de nicsoft.web via nicsoft/core/ihm_port.py
et un objet `app_state_proxy` imitant l'ancien accès direct à web_server.
Le test d'isolation de la #263 (test_no_web_import.py) verrouille l'absence
d'import de nicsoft.web, mais pas que chaque appel migré trouve bien sa
cible : c'est exactement ce qui a provoqué la régression du mode Humain
(`web_server.set_history(...)` sur un objet qui n'exposait pas set_history).

Ce test vérifie, par analyse statique (ast) de tous les fichiers des dossiers
de jeu (découverts automatiquement par _arc001_discovery.py, pas listés à la
main) :
1. que chaque nom importé depuis nicsoft.core.ihm_port existe réellement
   dans ce module ;
2. que chaque attribut accédé sur l'alias local de `app_state_proxy`
   (import `... as web_server` / `... as _web_server`) existe réellement
   sur `_AppStateProxy` ;
3. que le backend réel (_WebBackend, nicsoft.web.alchess) et le backend
   neutre (_NullBackend, nicsoft.core.ihm_port) exposent chacun toutes les
   méthodes utilisées par les fonctions de module de ihm_port.py.

Les fichiers qui n'importent rien de ihm_port (la grande majorité) passent
trivialement les vérifications 1 et 2 — ce n'est pas une liste de fichiers
« migrés », mais toute la surface où une migration future pourrait se
produire.
"""
import ast

import pytest

from nicsoft.core import ihm_port
from nicsoft.tests._arc001_discovery import (
    REPO_ROOT,
    decouvrir_fichiers_py,
    verifier_decouverte_non_cassee,
)

FICHIERS_MIGRES = decouvrir_fichiers_py()
verifier_decouverte_non_cassee(FICHIERS_MIGRES)


def _parse(chemin_relatif):
    chemin = REPO_ROOT / chemin_relatif
    return ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))


# ── 1. Les imports depuis ihm_port existent réellement ──────────────────────

def _noms_importes_de_ihm_port(tree):
    """Retourne {nom_local: nom_reel} pour chaque import depuis nicsoft.core.ihm_port."""
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "nicsoft.core.ihm_port":
            for alias in node.names:
                result[alias.asname or alias.name] = alias.name
    return result


@pytest.mark.parametrize("chemin_relatif", FICHIERS_MIGRES)
def test_imports_depuis_ihm_port_existent_reellement(chemin_relatif):
    tree = _parse(chemin_relatif)
    for nom_local, nom_reel in _noms_importes_de_ihm_port(tree).items():
        assert hasattr(ihm_port, nom_reel), (
            f"{chemin_relatif} importe `{nom_reel}` depuis nicsoft.core.ihm_port, "
            f"qui n'existe pas dans ce module (alias local : {nom_local})"
        )


# ── 2. Les attributs accédés sur l'alias de app_state_proxy existent ───────

def _alias_locaux_de_app_state_proxy(tree):
    """Noms locaux liés à `app_state_proxy` via `from ... import app_state_proxy as X`,
    ou passés en paramètre d'une fonction sous un nom conventionnel (web_server)."""
    alias = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "nicsoft.core.ihm_port":
            for a in node.names:
                if a.name == "app_state_proxy":
                    alias.add(a.asname or a.name)
    return alias


def _attributs_acc_sur_alias(tree, alias_names):
    attrs = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in alias_names
        ):
            attrs.add(node.attr)
    return attrs


@pytest.mark.parametrize("chemin_relatif", FICHIERS_MIGRES)
def test_appels_sur_app_state_proxy_existent_reellement(chemin_relatif):
    tree = _parse(chemin_relatif)
    alias_names = _alias_locaux_de_app_state_proxy(tree)
    if not alias_names:
        pytest.skip(f"{chemin_relatif} n'importe pas app_state_proxy")
    attrs = _attributs_acc_sur_alias(tree, alias_names)
    manquants = [a for a in attrs if not hasattr(ihm_port.app_state_proxy, a)]
    assert manquants == [], (
        f"{chemin_relatif} appelle sur l'alias de app_state_proxy des attributs "
        f"inexistants : {manquants} — c'est exactement la régression #264 "
        f"(web_server.set_history inexistant sur _AppStateProxy)"
    )


# ── 3. Les backends (neutre + web réel) exposent les mêmes méthodes ────────

def _methodes_backend_utilisees_par_ihm_port():
    """Analyse ihm_port.py lui-même : chaque fonction de module qui délègue
    à `_backend.xxx(...)` ou `_backend.xxx` (property) exige que xxx soit
    implémenté par tout backend branché."""
    tree = _parse("nicsoft/core/ihm_port.py")
    methodes = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "_backend"
        ):
            methodes.add(node.attr)
    return methodes


def test_null_backend_expose_toutes_les_methodes_utilisees():
    methodes = _methodes_backend_utilisees_par_ihm_port()
    manquantes = [m for m in methodes if not hasattr(ihm_port._NullBackend(), m)]
    assert manquantes == [], f"_NullBackend n'implémente pas : {manquantes}"


def test_web_backend_expose_toutes_les_methodes_utilisees():
    from nicsoft.web.alchess import _WebBackend

    methodes = _methodes_backend_utilisees_par_ihm_port()
    manquantes = [m for m in methodes if not hasattr(_WebBackend, m)]
    assert manquantes == [], f"_WebBackend (nicsoft.web.alchess) n'implémente pas : {manquantes}"


def test_decouverte_couvre_les_dossiers_de_jeu():
    """Garde-fou (#272) : la découverte ne doit jamais retourner une liste
    vide ni perdre silencieusement un fichier connu."""
    verifier_decouverte_non_cassee(FICHIERS_MIGRES)
    assert len(FICHIERS_MIGRES) >= 20
