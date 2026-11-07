"""
nicsoft/tests/test_issue296_security_suppressions.py — NicLink
Garde-fou (issue #296) : toute directive de suppression de sécurité ajoutée
dans nicsoft/ ou scripts/ — un « noqa » portant un code de sécurité ruff
(famille flake8-bandit, préfixe S + chiffres, ex. S310/S311/S603/S605/S607)
ou un « nosec » bandit (toujours sécurité, quel que soit le code B porté) —
doit respecter la forme imposée par Alain pour l'issue #296 : un code
explicite (jamais « noqa »/« nosec » seul), et une ligne de commentaire
expliquant la raison en clair (au moins deux mots), juste au-dessus ou juste
après la ligne de code portant la directive.

N'impose rien aux suppressions qui ne portent AUCUN code de sécurité (ex.
un futur « noqa: E501 » de pure forme) : seules les directives de sécurité
sont concernées, le reste — y compris les suppressions de style déjà
présentes ailleurs dans le projet — n'est pas touché par ce test.

Analyse purement textuelle des fichiers sources, sans aucun accès réseau.
"""
import re
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CE_FICHIER = pathlib.Path(__file__).resolve()

DOSSIERS_ANALYSES = ["nicsoft", "scripts"]

_NOQA_RE = re.compile(
    r'#\s*noqa\b(?:\s*:\s*(?P<codes>[A-Za-z0-9]+(?:[,\s]+[A-Za-z0-9]+)*))?',
    re.IGNORECASE,
)
_NOSEC_RE = re.compile(
    r'#\s*nosec\b(?![\w])(?:[ \t]+(?P<codes>[A-Za-z0-9]+(?:[,\s]+[A-Za-z0-9]+)*))?',
    re.IGNORECASE,
)
_CODE_SECURITE_RUFF_RE = re.compile(r'^S\d+$', re.IGNORECASE)
_MOT_RE = re.compile(r'[A-Za-zÀ-ÿ]+')


def _decouvrir_fichiers_py() -> list:
    """Tous les .py de nicsoft/ et scripts/, sauf __pycache__ et ce fichier
    lui-même (ses motifs de détection, écrits en toutes lettres, se
    signaleraient sinon eux-mêmes)."""
    fichiers = []
    for dossier in DOSSIERS_ANALYSES:
        racine = REPO_ROOT / dossier
        for chemin in racine.rglob("*.py"):
            if "__pycache__" in chemin.parts:
                continue
            if chemin.resolve() == CE_FICHIER:
                continue
            fichiers.append(chemin.relative_to(REPO_ROOT).as_posix())
    return sorted(fichiers)


def _codes_ou_none(texte_codes):
    if texte_codes is None:
        return None
    return [c for c in re.split(r'[,\s]+', texte_codes.strip()) if c]


def _ligne_de_raison_adjacente(lignes, idx) -> bool:
    """Vrai si la ligne juste au-dessus OU juste après `idx` (0-indexée) est
    un commentaire autonome (ligne entière) d'au moins deux mots."""
    for voisin in (idx - 1, idx + 1):
        if 0 <= voisin < len(lignes):
            texte = lignes[voisin].strip()
            if texte.startswith("#") and len(_MOT_RE.findall(texte[1:])) >= 2:
                return True
    return False


def _violations_securite(source: str) -> list:
    """Retourne [(lineno, message), ...] pour chaque directive noqa/nosec
    de sécurité mal formée (sans code, ou sans raison adjacente)."""
    lignes = source.splitlines()
    violations = []
    for i, ligne in enumerate(lignes):
        for m in _NOQA_RE.finditer(ligne):
            codes = _codes_ou_none(m.group("codes"))
            if codes is None:
                violations.append((i + 1, "noqa sans code (jamais de noqa seul)"))
                continue
            if any(_CODE_SECURITE_RUFF_RE.match(c) for c in codes):
                if not _ligne_de_raison_adjacente(lignes, i):
                    violations.append(
                        (i + 1, f"noqa de sécurité {codes} sans ligne de raison juste au-dessus/après")
                    )
        for m in _NOSEC_RE.finditer(ligne):
            codes = _codes_ou_none(m.group("codes"))
            if codes is None:
                violations.append((i + 1, "nosec sans code (jamais de nosec seul)"))
                continue
            if not _ligne_de_raison_adjacente(lignes, i):
                violations.append(
                    (i + 1, f"nosec {codes} sans ligne de raison juste au-dessus/après")
                )
    return violations


_FICHIERS = _decouvrir_fichiers_py()


@pytest.mark.parametrize("chemin_relatif", _FICHIERS)
def test_suppressions_securite_bien_formees(chemin_relatif):
    """Toute directive noqa/nosec de sécurité doit porter un code précis et
    une ligne de raison d'au moins deux mots juste au-dessus ou juste après
    (issue #296 — forme imposée pour les faux positifs justifiés en ligne)."""
    chemin = REPO_ROOT / chemin_relatif
    source = chemin.read_text(encoding="utf-8")
    violations = _violations_securite(source)
    assert violations == [], f"{chemin_relatif} : {violations}"


def test_decouverte_non_vide():
    """Garde-fou : une découverte cassée (chemin faux, dossier qui ne se
    parcourt plus) ne doit jamais passer inaperçue en retournant une liste
    vide."""
    assert _FICHIERS, "découverte de fichiers .py vide — vérifier DOSSIERS_ANALYSES/REPO_ROOT"
    assert any(f.startswith("nicsoft/web/") for f in _FICHIERS)
    assert any(f.startswith("scripts/") for f in _FICHIERS)
