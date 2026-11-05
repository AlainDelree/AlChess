"""
Test de garde (issue #279) — régression des extractions de styles en ligne
vers le CSS (issues #230 à #248).

Contexte du défaut : plusieurs éléments étaient cachés/désactivés par un
style EN LIGNE (`style="display:none"` etc.) et le JS les "révélait" en
effaçant ce style (`el.style.display = ""`). Une série d'extractions a
déplacé ces styles figés vers des classes CSS (`.ma-classe { display:none }`).
Depuis, effacer le style en ligne ne supprime plus la règle CSS : l'élément
reste caché. Cinq cas confirmés (plus un trouvé par ce test pendant l'issue
#279 : les messages `cfg-*-unavailable`) ont dû être corrigés en donnant une
valeur explicite (ex. "block", "auto") plutôt que "".

Ce test est un garde-fou SANS NAVIGATEUR : il analyse statiquement
`templates/index.html` (association id → classes), `static/css/main.css`
(règles de classe qui cachent par défaut) et `static/app.js` (code qui
efface un style en ligne cachant). Il échoue si ce défaut réapparaît.

Portée volontairement restreinte (pour éviter les faux positifs) :
- seules les règles CSS de sélecteur de classe SIMPLE sont prises en compte
  (`.foo { display:none }`) — un sélecteur combiné (`.foo:hover`,
  `.foo.open`, `.foo .bar`, liste avec un membre complexe) n'affirme pas que
  la classe cache l'élément *par défaut*, donc n'est pas retenu : une bascule
  de classe d'état (`classList.toggle`) est une solution légitime (voir
  `.game-gameover-coller-pgn-zone.is-open` par ex.) et ne doit pas être
  signalée ;
- seules les règles CSS au premier niveau (hors `@media`) sont prises en
  compte — une règle responsive ne doit pas être signalée automatiquement,
  elle demande un jugement au cas par cas ;
- seul le motif "efface le style en ligne" (`.style.PROP = ...""...`) est
  signalé, jamais une valeur explicite (`"block"`, `"flex"`, `"auto"`,
  `"none"`, `"0.4"`, ...) qui ne dépend pas de la règle CSS pour produire le
  bon résultat visible ;
- seuls les éléments atteints par `document.getElementById("id")` sont
  couverts (c'est le motif exact du défaut rapporté). Les éléments atteints
  autrement (`querySelector`, délégation sur une classe commune) ont été
  vérifiés manuellement lors de la recherche systématique de l'issue #279
  et ne sont pas re-vérifiés automatiquement ici.

Exceptions documentées (aucune à ce jour) : si un futur cas correspond au
motif détecté mais est un faux positif légitime, l'ajouter à
`EXCEPTIONS_ID_PROP` ci-dessous avec un commentaire expliquant pourquoi
l'effacement du style en ligne fonctionne malgré tout (ex. la classe n'est
en réalité jamais appliquée à cet élément au moment où le JS s'exécute).
"""
import re
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = REPO_ROOT / "nicsoft/web/templates/index.html"
CSS_PATH = REPO_ROOT / "nicsoft/web/static/css/main.css"
JS_PATH = REPO_ROOT / "nicsoft/web/static/app.js"

# CSS property (kebab-case) -> propriété JS correspondante (camelCase),
# limité aux propriétés "cachantes" visées par le défaut de l'issue #279.
CSS_TO_JS_PROP = {
    "display": "display",
    "pointer-events": "pointerEvents",
    "visibility": "visibility",
    "opacity": "opacity",
}

# (id, propriété JS) à ignorer malgré une correspondance détectée —
# aucun cas connu à ce jour. Documenter la raison ici si un cas légitime
# apparaît (ex. la classe hiding n'est jamais réellement portée par cet
# élément au moment de l'effacement du style, ou la valeur "" est voulue
# parce qu'aucune autre règle ne s'applique dans ce contexte précis).
EXCEPTIONS_ID_PROP = set()


def _opacity_is_hiding(value: str) -> bool:
    """Une opacité strictement < 1 est considérée "cachante" (atténuation)."""
    try:
        return float(value.strip()) < 1
    except ValueError:
        return False


def _is_simple_class_selector(selector: str) -> bool:
    """Sélecteur de classe simple : `.foo`, sans combinateur ni pseudo-classe."""
    return bool(re.fullmatch(r"\.[A-Za-z0-9_-]+", selector.strip()))


class _IdClassParser(HTMLParser):
    """Associe chaque id HTML à l'ensemble de ses classes."""

    def __init__(self):
        super().__init__()
        self.id_to_classes = {}

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        el_id = d.get("id")
        if not el_id:
            return
        classes = (d.get("class") or "").split()
        self.id_to_classes.setdefault(el_id, set()).update(classes)


def _parse_id_to_classes(html_text: str) -> dict:
    parser = _IdClassParser()
    parser.feed(html_text)
    return parser.id_to_classes


def _strip_css_comments(css_text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)


def _top_level_rules(css_text: str):
    """Itère les règles CSS au premier niveau (hors blocs @media/@keyframes...).

    Les accolades sont appariées correctement (profondeur), donc un bloc
    @media entier (avec ses règles imbriquées) est consommé en un seul
    saut et jamais exposé comme règle "au premier niveau" — une règle
    responsive ne doit pas être signalée automatiquement par ce garde-fou
    (voir docstring du module).
    """
    n = len(css_text)
    i = 0
    while i < n:
        brace_idx = css_text.find("{", i)
        if brace_idx == -1:
            break
        selector = css_text[i:brace_idx].strip()
        depth = 1
        j = brace_idx + 1
        while j < n and depth > 0:
            if css_text[j] == "{":
                depth += 1
            elif css_text[j] == "}":
                depth -= 1
            j += 1
        body = css_text[brace_idx + 1:j - 1]
        if selector and not selector.startswith("@"):
            yield selector, body
        i = j


def _class_hiding_rules(css_text: str) -> dict:
    """Retourne {classe: {prop_js: valeur_cachante}} pour les sélecteurs de
    classe simples au premier niveau dont une déclaration cache l'élément."""
    css_text = _strip_css_comments(css_text)
    result = {}
    for selector, body in _top_level_rules(css_text):
        parts = [p.strip() for p in selector.split(",")]
        if not all(_is_simple_class_selector(p) for p in parts):
            continue
        hiding = {}
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            prop, _, value = decl.partition(":")
            prop = prop.strip().lower()
            value = value.replace("!important", "").strip()
            if prop not in CSS_TO_JS_PROP:
                continue
            js_prop = CSS_TO_JS_PROP[prop]
            if prop == "opacity":
                if _opacity_is_hiding(value):
                    hiding[js_prop] = value
            elif prop == "display" and value == "none":
                hiding[js_prop] = value
            elif prop == "pointer-events" and value == "none":
                hiding[js_prop] = value
            elif prop == "visibility" and value == "hidden":
                hiding[js_prop] = value
        if not hiding:
            continue
        for p in parts:
            cls = p[1:]  # enlève le "."
            result.setdefault(cls, {}).update(hiding)
    return result


# Repère `document.getElementById("id")`, éventuellement affecté à une
# variable, et le `.style.PROP = EXPR;` qui le suit à proximité (toujours
# sur la même ligne ou dans les quelques lignes suivantes dans ce fichier —
# voir docstring du module pour la portée retenue).
_GETBYID_RE = re.compile(
    r'(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(\s*["\'](\w[\w-]*)["\']\s*\)'
    r'|document\.getElementById\(\s*["\'](\w[\w-]*)["\']\s*\)\.style\.(\w+)\s*=\s*([^;]+);'
)

_WINDOW_LINES = 6


def _find_cleared_inline_styles(js_text: str) -> list:
    """Retourne [(id, prop_js, ligne)] pour chaque `.style.PROP = EXPR;` où
    EXPR contient la chaîne vide `""`/`''` comme branche possible, et où
    PROP est l'une des propriétés surveillées."""
    lines = js_text.splitlines()
    findings = []

    # Cas direct : document.getElementById("id").style.PROP = EXPR;
    direct_re = re.compile(
        r'document\.getElementById\(\s*["\'](\w[\w-]*)["\']\s*\)\.style\.(\w+)\s*=\s*([^;]+);'
    )
    for lineno, line in enumerate(lines, 1):
        for m in direct_re.finditer(line):
            el_id, prop, expr = m.group(1), m.group(2), m.group(3)
            if _expr_has_empty_string_branch(expr):
                findings.append((el_id, prop, lineno))

    # Cas via variable : const v = document.getElementById("id"); ... v.style.PROP = EXPR;
    decl_re = re.compile(
        r'(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(\s*["\'](\w[\w-]*)["\']\s*\)'
    )
    for lineno, line in enumerate(lines, 1):
        m = decl_re.search(line)
        if not m:
            continue
        var_name, el_id = m.group(1), m.group(2)
        window = lines[lineno - 1: lineno - 1 + _WINDOW_LINES]
        use_re = re.compile(
            r'\b' + re.escape(var_name) + r'\.style\.(\w+)\s*=\s*([^;]+);'
        )
        for offset, wline in enumerate(window):
            for um in use_re.finditer(wline):
                prop, expr = um.group(1), um.group(2)
                if _expr_has_empty_string_branch(expr):
                    findings.append((el_id, prop, lineno + offset))

    return findings


def _expr_has_empty_string_branch(expr: str) -> bool:
    """True si l'expression affectée est, ou contient comme branche de
    ternaire, la chaîne vide ("" ou '')."""
    expr = expr.strip()
    if expr in ('""', "''"):
        return True
    # Ternaire `cond ? A : B` — on inspecte A et B littéralement.
    m = re.match(r'.*\?\s*(.+?)\s*:\s*(.+)$', expr)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        return a in ('""', "''") or b in ('""', "''")
    return False


def test_aucune_regression_css_extraction_sur_style_efface():
    """Échoue si un élément id=X a une classe qui le cache par défaut en CSS
    (display:none / pointer-events:none / opacity<1 / visibility:hidden) et
    que app.js se contente d'effacer le style en ligne correspondant (= "")
    au lieu de lui donner une valeur explicite."""
    html_text = HTML_PATH.read_text(encoding="utf-8")
    css_text = CSS_PATH.read_text(encoding="utf-8")
    js_text = JS_PATH.read_text(encoding="utf-8")

    id_to_classes = _parse_id_to_classes(html_text)
    class_hiding = _class_hiding_rules(css_text)
    cleared = _find_cleared_inline_styles(js_text)

    violations = []
    for el_id, prop, lineno in cleared:
        if (el_id, prop) in EXCEPTIONS_ID_PROP:
            continue
        classes = id_to_classes.get(el_id, set())
        for cls in classes:
            hiding_props = class_hiding.get(cls, {})
            if prop in hiding_props:
                violations.append(
                    f"  app.js:{lineno} — #{el_id}.style.{prop} = \"\" (ou branche"
                    f" de ternaire) alors que .{cls} impose "
                    f"{prop}: {hiding_props[prop]!r} en CSS"
                )
                break

    assert not violations, (
        "Défaut des extractions de styles (issues #230-#248, voir #279) : "
        "effacer un style en ligne ne révèle plus l'élément si la règle "
        "CSS de sa classe le cache toujours. Donner une valeur explicite "
        "(ex. \"block\", \"auto\") au lieu de \"\".\n" + "\n".join(violations)
    )
