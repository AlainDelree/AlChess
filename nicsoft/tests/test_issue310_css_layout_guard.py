"""
nicsoft/tests/test_issue310_css_layout_guard.py — AlChess

Issue #310, point 7 : l'écran de configuration Lichess (#screen-config-lichess)
s'affichait vide au premier essai réel — la règle de mise en page de
main.css le concernant manquait, ce qui rejetait tout son contenu hors de
l'écran (barre de défilement horizontale). Aucun test ne regardait le rendu
dans un navigateur, donc rien ne l'a détecté avant l'essai sur le vrai
matériel. L'utilisateur a corrigé main.css à la main (#screen-config-lichess
ajouté aux deux endroits qui concernaient déjà #screen-config-humain).

Ce test généralise la garde : chaque écran que app.js bascule en
"display: flex" ou "display: grid" doit avoir AU MOINS une règle de mise en
page dans main.css — soit sur son #id, soit sur une classe CSS qu'il porte
dans index.html (plusieurs écrans, ex. #screen-connecting, utilisent
`display:none` par défaut sur leur classe et laissent app.js basculer vers
"flex" en style inline — ce n'est pas un défaut, exiger le mot "flex" dans
la règle CSS elle-même donnerait de faux positifs sur ce pattern légitime).
Un futur écran sans AUCUNE règle nulle part (ni sur l'id, ni sur une classe)
reproduirait exactement le défaut de #screen-config-lichess.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_CONST_GETBYID_RE = re.compile(r'const\s+(\w+)\s*=\s*document\.getElementById\("([\w-]+)"\)')
_DISPLAY_TOGGLE_RE = re.compile(
    r'(?:document\.getElementById\("([\w-]+)"\)|(\w+))\.style\.display\s*=\s*[^;\n]*\?\s*"(flex|grid)"'
)
_DIV_TAG_RE = re.compile(r'<div\b[^>]*>')
_ID_ATTR_RE = re.compile(r'\bid="([\w-]+)"')
_CLASS_ATTR_RE = re.compile(r'\bclass="([^"]*)"')


def _screens_toggled_flex_or_grid(appjs_src: str) -> dict:
    """{id_ecran: "flex"|"grid"} pour chaque écran/panneau (#screen-*,
    #panel-*) dont app.js bascule le display, que ce soit en une ligne
    (getElementById(...).style.display = ...) ou en deux (const v =
    getElementById(...); ... v.style.display = ...)."""
    var_to_id = dict(_CONST_GETBYID_RE.findall(appjs_src))
    screens = {}
    for direct_id, var_name, mode in _DISPLAY_TOGGLE_RE.findall(appjs_src):
        elem_id = direct_id or var_to_id.get(var_name)
        if elem_id and (elem_id.startswith("screen-") or elem_id.startswith("panel-")):
            screens[elem_id] = mode
    return screens


def _element_classes_from_html(html_src: str) -> dict:
    """{id: [classes]} déduit de chaque balise <div id="..."> d'index.html
    (ordre des attributs indifférent)."""
    classes_by_id = {}
    for tag in _DIV_TAG_RE.findall(html_src):
        id_match = _ID_ATTR_RE.search(tag)
        if not id_match:
            continue
        class_match = _CLASS_ATTR_RE.search(tag)
        classes_by_id[id_match.group(1)] = class_match.group(1).split() if class_match else []
    return classes_by_id


def _css_selector_present(css_src: str, token: str) -> bool:
    """`token` (ex. "#screen-config-lichess" ou ".screen-parametres") est
    présent comme sélecteur — pas seulement comme préfixe d'un autre id/
    classe plus long (ex. "#screen-config" ne doit pas matcher dans
    "#screen-config-humain")."""
    return re.search(re.escape(token) + r'(?![\w-])', css_src) is not None


def test_extraction_trouve_bien_des_ecrans_connus():
    """Garde-fou sur l'extraction elle-même."""
    appjs = (REPO_ROOT / "nicsoft" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    screens = _screens_toggled_flex_or_grid(appjs)
    for attendu in ("screen-menu", "screen-config-lichess", "screen-config-humain", "screen-game"):
        assert attendu in screens, f"extraction incomplète : {attendu!r} non trouvé"


def test_chaque_ecran_flex_ou_grid_a_une_regle_de_mise_en_page_css():
    appjs = (REPO_ROOT / "nicsoft" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    css = (REPO_ROOT / "nicsoft" / "web" / "static" / "css" / "main.css").read_text(encoding="utf-8")

    screens = _screens_toggled_flex_or_grid(appjs)
    classes_by_id = _element_classes_from_html(html)

    sans_regle = []
    for screen_id in sorted(screens):
        has_id_rule = _css_selector_present(css, f"#{screen_id}")
        classes = classes_by_id.get(screen_id, [])
        has_class_rule = any(_css_selector_present(css, f".{c}") for c in classes)
        if not has_id_rule and not has_class_rule:
            sans_regle.append(screen_id)

    assert not sans_regle, (
        f"Écran(s) basculé(s) en flex/grid par app.js sans aucune règle de mise en "
        f"page dans main.css (ni sur leur #id, ni sur une de leurs classes) : {sans_regle} "
        f"— même défaut que #screen-config-lichess avant correction (issue #310)."
    )
