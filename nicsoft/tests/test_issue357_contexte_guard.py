"""
nicsoft/tests/test_issue357_contexte_guard.py — AlChess

Issue #357 : l'issue #356 a ramené CONTEXTE.md à 3681 caractères (le watcher
n'injecte dans le prompt de CCL que les 4000 premiers) — il ne restait que
19 caractères de marge et rien ne surveillait la taille. Une prochaine
tâche qui ajouterait quelques lignes ferait couper silencieusement la fin
du fichier (l'index des fichiers de domaine, en dernière section) sans que
personne ne le voie avant le prochain agent mal informé.

Ce test, dans le même esprit que les autres gardes du dépôt (ex.
test_issue333_lichess_no_engine.py pour le fair-play), ne lit que des
fichiers du dépôt lui-même — jamais un dossier réel de l'utilisateur,
jamais le réseau, jamais de matériel — et échoue si :
  1. CONTEXTE.md dépasse 3700 caractères (compté en caractères, comme
     `wc -m`, pas en octets — un accent ou un caractère multi-octet ne
     doit pas fausser la mesure) ;
  2. un fichier présent dans docs/contexte/ n'est cité dans aucun chemin
     de l'index de CONTEXTE.md ;
  3. un chemin `docs/contexte/<domaine>.md` cité dans l'index n'existe pas
     sur disque.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXTE_MD = REPO_ROOT / "CONTEXTE.md"
DOCS_CONTEXTE_DIR = REPO_ROOT / "docs" / "contexte"

TAILLE_MAX = 3700

_INDEX_BULLET_RE = re.compile(r"^- `([\w-]+\.md)`", re.MULTILINE)


def _fichiers_cites_dans_index(contexte_src: str) -> set:
    """Noms de fichiers (sans chemin) cités en puce sous la section
    "## Index des fichiers de contexte" — CONTEXTE.md cite chaque fichier
    par son seul nom (ex. `` `architecture.md` ``), le préfixe
    `docs/contexte/` étant donné une fois dans le titre de section."""
    return set(_INDEX_BULLET_RE.findall(contexte_src))


def test_contexte_md_reste_sous_la_limite_d_injection():
    contenu = CONTEXTE_MD.read_text(encoding="utf-8")
    taille = len(contenu)
    assert taille <= TAILLE_MAX, (
        f"CONTEXTE.md fait {taille} caractères (wc -m) — dépasse la limite "
        f"de {TAILLE_MAX}. Le watcher n'injecte dans le prompt de CCL que "
        f"les 4000 premiers caractères du fichier : au-delà de cette "
        f"limite, la marge devient trop faible et une future modification "
        f"ferait couper silencieusement la fin du fichier (l'index des "
        f"fichiers de domaine, en dernière section) sans que personne ne "
        f"le voie. Déplace le détail en trop dans le fichier de domaine "
        f"concerné sous docs/contexte/<domaine>.md plutôt que de grossir "
        f"CONTEXTE.md."
    )


def test_chaque_fichier_de_docs_contexte_est_cite_dans_l_index():
    contexte_src = CONTEXTE_MD.read_text(encoding="utf-8")
    cites = _fichiers_cites_dans_index(contexte_src)
    fichiers_disque = {p.name for p in DOCS_CONTEXTE_DIR.glob("*.md")}
    orphelins = sorted(fichiers_disque - cites)
    assert not orphelins, (
        f"Fichier(s) de docs/contexte/ absent(s) de l'index de CONTEXTE.md : "
        f"{orphelins} — un futur agent ne saura pas qu'il existe ni quand le "
        f"lire. Ajoute une ligne d'index (chemin + moment où le lire)."
    )


def test_chaque_fichier_cite_dans_l_index_existe_sur_disque():
    contexte_src = CONTEXTE_MD.read_text(encoding="utf-8")
    cites = _fichiers_cites_dans_index(contexte_src)
    manquants = sorted(
        nom for nom in cites if not (DOCS_CONTEXTE_DIR / nom).is_file()
    )
    assert not manquants, (
        f"Fichier(s) cité(s) dans l'index de CONTEXTE.md mais absent(s) de "
        f"docs/contexte/ : {manquants} — l'index pointe vers un fichier "
        f"renommé, déplacé ou supprimé ; corrige le nom ou retire la ligne."
    )
