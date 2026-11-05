"""
Test issue #283 — verrou ciblé sur le bandeau « Session en cours » de la
retranscription (id `retrans-resume-banner`).

Contexte (voir aussi `test_css_extraction_hidden_elements.py`, le garde-fou
générique de l'issue #279) : ce bandeau était caché par un style EN LIGNE
que le JS révélait en l'effaçant (`style.display = ""`). L'issue #230 a
déplacé le masquage par défaut vers une règle CSS (`.retrans-resume-banner
{ display:none }`) sans changer le JS, qui ne révélait donc plus rien
(l'effacement d'un style en ligne ne supprime pas une règle CSS). Le
correctif (fait à la main, à ne pas refaire) donne une valeur explicite
("block"/"none") à chaque endroit où ce bandeau change de visibilité.

Ce test, statique et sans navigateur, verrouille spécifiquement CE bandeau
(complément ciblé au garde-fou générique) : il échoue si un futur changement
réintroduit l'effacement du style en ligne (`style.display = ""`) pour cet
id précis.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS_PATH = REPO_ROOT / "nicsoft/web/static/css/main.css"
JS_PATH = REPO_ROOT / "nicsoft/web/static/app.js"

BANNER_ID = "retrans-resume-banner"


def test_css_cache_le_bandeau_par_defaut():
    """Pré-requis du scénario : la règle CSS cache bien le bandeau par
    défaut (sinon le test suivant n'aurait pas de sens)."""
    css_text = CSS_PATH.read_text(encoding="utf-8")
    m = re.search(r"\.retrans-resume-banner\s*\{([^}]*)\}", css_text)
    assert m, "règle CSS .retrans-resume-banner introuvable"
    assert re.search(r"display\s*:\s*none", m.group(1)), (
        "le scénario suppose que .retrans-resume-banner cache l'élément "
        "par défaut (display:none) — sinon ce test ne couvre plus rien"
    )


def test_js_ne_cache_ni_ne_revele_le_bandeau_en_effacant_son_style():
    """Chaque affectation `.style.display = ...` visant ce bandeau (par id
    direct ou par variable issue de `getElementById("retrans-resume-banner")`)
    doit porter une valeur explicite ("block", "none"...), jamais la chaîne
    vide ("" ou '') qui ne réviderait rien tant que la règle CSS cache
    l'élément."""
    js_text = JS_PATH.read_text(encoding="utf-8")
    lines = js_text.splitlines()

    assignments = []  # [(lineno, expr)]

    direct_re = re.compile(
        r'document\.getElementById\(\s*["\']' + BANNER_ID + r'["\']\s*\)\.style\.display\s*=\s*([^;]+);'
    )
    for lineno, line in enumerate(lines, 1):
        for m in direct_re.finditer(line):
            assignments.append((lineno, m.group(1)))

    decl_re = re.compile(
        r'(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(\s*["\']' + BANNER_ID + r'["\']\s*\)'
    )
    for lineno, line in enumerate(lines, 1):
        m = decl_re.search(line)
        if not m:
            continue
        var_name = m.group(1)
        window = lines[lineno - 1: lineno - 1 + 6]
        use_re = re.compile(r'\b' + re.escape(var_name) + r'\.style\.display\s*=\s*([^;]+);')
        for offset, wline in enumerate(window):
            for um in use_re.finditer(wline):
                assignments.append((lineno + offset, um.group(1)))

    assert assignments, (
        f"aucune affectation de style.display trouvée pour #{BANNER_ID} dans app.js — "
        "le test n'a rien pu vérifier, l'id a-t-il changé ?"
    )

    violations = [
        (lineno, expr) for lineno, expr in assignments
        if expr.strip() in ('""', "''")
    ]
    assert not violations, (
        f"app.js efface le style en ligne de #{BANNER_ID} (style.display = \"\") "
        "au lieu de lui donner une valeur explicite, alors que la règle CSS "
        "cache cet élément par défaut (régression des issues #230/#279) :\n" +
        "\n".join(f"  app.js:{lineno} -> {expr}" for lineno, expr in violations)
    )
