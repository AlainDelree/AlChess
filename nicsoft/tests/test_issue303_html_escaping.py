"""
nicsoft/tests/test_issue303_html_escaping.py — NicLink

Issue #303 : tout texte venu de l'extérieur (serveur, joueur, fichier PGN,
réponse LLM — demain Lichess) doit être échappé (esc()) ou inséré via
textContent avant d'atterrir dans le DOM. Garde-fou SANS NAVIGATEUR (analyse
statique du source, sur le modèle de test_css_extraction_hidden_elements.py
et test_retrans_resume_banner_display.py) — aucune dépendance à Node.

Ce fichier verrouille trois choses :
  (a) toute interpolation ${...} dans un template litéral contenant du HTML
      (un `<`) utilisé pour .innerHTML/.innerHTML+=/insertAdjacentHTML doit
      être soit un appel esc(...), soit un appel t("clé") sans second
      argument, soit une entrée documentée de la liste blanche ci-dessous
      (nombre, couleur/flag interne, identifiant interne reconnu sûr) ;
  (b) markdownToHtml() appelle esc( avant son premier .replace( ;
  (c) esc() échappe bien les cinq caractères & < > " ' et traite
      null/undefined comme une chaîne vide.

Toute NOUVELLE interpolation ajoutée dans un template HTML qui ne correspond
à aucune de ces règles fera échouer le test : c'est volontaire, elle doit
être enveloppée dans esc() (cas normal) ou, si elle est authentiquement
interne/sûre, ajoutée à la liste blanche ci-dessous avec sa raison.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JS_PATH = REPO_ROOT / "nicsoft" / "web" / "static" / "app.js"


# ── (a) Extraction des template litéraux et de leurs interpolations ────────
#
# On parcourt le source caractère par caractère pour repérer les chaînes
# entre backticks (en ignorant backticks dans '...'/"..."/commentaires), en
# suivant la profondeur des accolades à l'intérieur de ${...} (nécessaire
# car un paramètre t("clé", {n: x}) contient lui-même des accolades). On ne
# retient que les templates contenant un "<" (fragments HTML) : les
# ${...} qui construisent un simple texte sans balise (assigné via
# textContent, ou un sélecteur CSS, etc.) sont hors du périmètre de cette
# issue, qui porte sur l'insertion HTML brute.

_REGEX_PRECEDING_RE = re.compile(
    r'(return|typeof|instanceof|in|of|new|delete|void|yield|case)\s*$'
)


def _regex_literal_may_start_here(source, i):
    """Heuristique classique de tokenizer JS pour distinguer un literal
    regex (/.../ ) d'une simple division : on regarde le dernier token
    non-blanc avant le "/". Un "/" précédé d'une parenthèse/virgule/
    opérateur ouvrante ou d'un mot-clé comme "return" démarre un regex ;
    précédé d'un identifiant/nombre/")"/"]" c'est une division.
    Nécessaire ici car app.js contient des literals regex avec des
    guillemets à l'intérieur (ex: /"/g, /'/g dans esc() lui-même), qui
    sans cette heuristique sont pris pour l'ouverture d'une chaîne et
    désynchronisent tout le reste de l'analyse (faux négatifs silencieux).
    """
    j = i - 1
    while j >= 0 and source[j] in " \t":
        j -= 1
    if j < 0:
        return True
    prev = source[j]
    if prev in "([{,;=:!&|?+-*%^~<>":
        return True
    # mot-clé juste avant (return, typeof, case, ...)
    k = j
    while k >= 0 and (source[k].isalnum() or source[k] == "_"):
        k -= 1
    word = source[k + 1:j + 1]
    if word and _REGEX_PRECEDING_RE.search(word):
        return True
    return False


def _skip_regex_literal(source, i):
    """i pointe sur le "/" d'ouverture ; retourne l'offset juste après les
    drapeaux (g, i, m, ...) qui suivent le "/" de fermeture."""
    n = len(source)
    j = i + 1
    in_class = False
    while j < n:
        ch = source[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            j += 1
            break
        elif ch == "\n":
            # Pas de regex multi-ligne en JS : si on arrive ici, ce n'était
            # pas un regex (repli : traiter le "/" initial comme un simple
            # caractère pour ne pas avaler toute la ligne).
            return i + 1
        j += 1
    while j < n and source[j].isalpha():
        j += 1
    return j


def _extract_backtick_templates(source):
    templates = []
    i, n = 0, len(source)
    in_line_comment = in_block_comment = in_single = in_double = False
    while i < n:
        c = source[i]
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if c == "*" and source[i + 1:i + 2] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_single:
            if c == "\\":
                i += 2
                continue
            if c == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_double = False
            i += 1
            continue
        if c == "/" and source[i + 1:i + 2] == "/":
            in_line_comment = True
            i += 2
            continue
        if c == "/" and source[i + 1:i + 2] == "*":
            in_block_comment = True
            i += 2
            continue
        if c == "/" and _regex_literal_may_start_here(source, i):
            new_i = _skip_regex_literal(source, i)
            i = new_i
            continue
        if c == "'":
            in_single = True
            i += 1
            continue
        if c == '"':
            in_double = True
            i += 1
            continue
        if c == "`":
            start = i
            i += 1
            depth = 0
            while i < n:
                ch = source[i]
                if ch == "\\":
                    i += 2
                    continue
                if depth == 0 and ch == "`":
                    i += 1
                    break
                if depth == 0 and ch == "$" and source[i + 1:i + 2] == "{":
                    depth = 1
                    i += 2
                    continue
                if depth > 0:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                i += 1
            templates.append((start, source[start:i]))
            continue
        i += 1
    return templates


def _extract_interpolations(template_text):
    """${...} de premier niveau d'un template litéral (backticks inclus)."""
    exprs = []
    i, n = 0, len(template_text)
    while i < n:
        if template_text[i] == "\\":
            i += 2
            continue
        if template_text[i] == "$" and template_text[i + 1:i + 2] == "{":
            j = i + 2
            depth = 1
            start = j
            while j < n and depth > 0:
                ch = template_text[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                elif ch == "`":
                    j += 1
                    while j < n and template_text[j] != "`":
                        if template_text[j] == "\\":
                            j += 1
                        j += 1
                j += 1
            exprs.append(template_text[start:j - 1])
            i = j
            continue
        i += 1
    return exprs


# ── Liste blanche ────────────────────────────────────────────────────────
#
# t("clé", {...}) dont tous les paramètres sont des nombres/longueurs déjà
# calculés côté client (jamais du texte libre) — revus un par un pour
# l'issue #303.
SAFE_T_CALLS = {
    't("common.n_coups", {n: nb})',
    't("exercices.n_lignes", {n: items.length})',
    't("exercices.n_ouvertures", {n: totalItems})',
    't("outils.eco_ignorees", {n: data.skipped.length})',
    't("outils.eco_importees", {n: data.imported.length})',
    't("outils.label.nom").trim()',
    't("outils.livre_count", {count: b.count, next: b.next})',
    't("outils.livre_count", {count: data.book_options[0].count, next: data.book_options[0].next})',
    't("outils.n_demi_coups", {n: data.moves.length})',
    't("outils.pgn_import_ok", {n: data.imported, total: data.total})',
    't("outils.wiki_codes_eco", {n: data.total})',
    't("outils.wiki_noms_article", {n: data.with_name})',
    't("outils.wiki_parents", {n: data.with_parent})',
    't("outils.wiki_sauvegarde", {path: esc(data.output)})',
    't("retrans.coups_non_affiches", {n: moves.length - 8})',
    't(nbVariants > 1 ? "exercices.variantes" : "exercices.variante")',
}

# Identifiants/expressions internes revus un par un : jamais de texte libre
# venu du serveur/joueur/PGN, seulement des nombres, couleurs calculées,
# drapeaux booléens ou identifiants déjà restreints à un alphabet sûr.
SAFE_IDENTIFIERS = {
    # Coordonnées/tailles numériques (SVG mini-échiquier, flèches LLM, etc.)
    "x", "y", "sq", "SQ", "SQ*8", "SQ-6", "sq*0.82", "x + sq/2", "y + sq*0.78",
    "bar", "i", "i+1", "moveNum",
    # Couleurs/traits calculés à partir de tables internes (jamais de texte)
    "fill", "color", "stroke", "col", "bg",
    # Glyphes/flags internes (toujours une valeur d'un ensemble fixe)
    "sym", "star", "side", "isOpen ? \"▲\" : \"▼\"",
    "isVariant ? \"#1a2a3a\" : \"#e0e0e0\"", "isVariant ? \"cc\" : \"88\"",
    "m.star?700:400", "campIcon", "disabled", "r.doublon ? \"\" : \"\"",
    # Fragments HTML déjà construits en amont à partir de sources sûres
    "badge", "miniBoard", "img", "initInfo", "status", "campLabel", "label",
    "parent",  # déjà esc() en amont (voir _exBuildCard / outils_wiki_done)
    # Nombres reçus du serveur dont le type est garanti numérique (JSON)
    "nbVariants", "m.pct", "r.nb_coups", "data.errors.length",
    # Identifiant interne restreint à [a-z0-9_] par make_unique_id() côté
    # Python (add_ouverture.py / eco_import*.py / import_lignes.py) —
    # jamais de guillemet ni de chevron possible.
    "o.id",
    # groupId = esc-free car construit par un slug restreint à
    # [a-zA-Z0-9_-] (voir exRenderMesLignes) — jamais de texte libre brut.
    "groupId",
    # Enum interne "white"/"black" (jamais de texte libre, cf. add_ouverture.py)
    "r.camp",
    # Tableau figé de lettres, pas de donnée externe
    '"abcdefgh".split("").map(c=>`<span>${c}</span>`).join("")',
    # Table de correspondance interne (clé FEN -> nom de fichier SVG fixe) ;
    # pas de "|| p" de repli donc aucune valeur brute ne peut s'insérer.
    "_EXPLORE_PIECE[p]",
    # Retourne toujours une couleur hex d'une palette interne fixe (jamais
    # le texte du panier lui-même) — voir _basketOptionColor().
    "_basketOptionColor(e.label)",
    # Constante interne "/static/pieces/" (PIECES, table figée des glyphes
    # d'échiquier) — jamais de donnée externe.
    "BASE",
    # Pré-échappés par leur propre déclaration (`const wh = esc(...)`,
    # `const bl = esc(...)` juste au-dessus dans init_hh) — re-échapper au
    # site d'interpolation serait redondant, pas incorrect.
    "wh", "bl",
    # sym[...] || "" : jamais de repli sur la valeur brute (contrairement à
    # PIECES[piece] || piece) donc toujours "" ou un glyphe fixe.
    "wsym", "bsym",
    # Couleur/poids/indice calculés dans renderReview/_laboRenderPgnHistory :
    # littéral hex, résultat de qualiteColor()/qualiteSymbole() (switch à
    # palette figée), chaîne CSS statique, ou index numérique (_idx).
    "colorW", "colorB", "activeW", "activeB", "idxW", "idxB", "cwW", "cwB",
    # Constante numérique locale (taille de case SVG) et timestamp HH:MM:SS
    # généré par Date()/toTimeString() — jamais de texte externe.
    "SZ", "hms",
    # updateMaterial() : symW/symB sont des tables figées {P:'wP',...},
    # p vient des clés fixes de initW/initB ({P,N,B,R,Q}) ; diff est un
    # nombre (différentiel matériel).
    "symW[p]", "symB[p]", "diff", "Math.abs(diff)",
    # Bibliothèque PGN perso : index numérique et compteur numérique reçus
    # du serveur (jamais du texte).
    "g.index", "c.game_count",
    # Index numériques (coup pair/impair *2) du journal PGN Labo.
    "wIdx+1", "bIdx+1",
    # Table de couleurs interne (_COLORS) avec repli sur un littéral figé ;
    # cat est restreint à coups/alertes/analyse/config (voir _journalFiltres).
    '_COLORS[cat] || "#aaa"',
    # _lichessFormatClock() (issue #309) : mm/ss sont des entiers calculés
    # par Math.floor/modulo à partir d'une durée en ms reçue de Lichess —
    # jamais du texte libre.
    "mm", "ss",
}

# Préfixes d'appel équivalents à esc( : _pgnLibEsc délègue littéralement à
# esc() (voir app.js) ; qualiteColor/qualiteSymbole sont des switch/default
# qui ne retournent JAMAIS leur argument tel quel (palette/glyphes figés),
# donc sûrs même si leur paramètre est une donnée externe.
_ESC_EQUIVALENT_PREFIXES = ("esc(", "_pgnLibEsc(", "qualiteColor(", "qualiteSymbole(")

_BARE_T_RE = re.compile(r'^t\(\s*(["\'])[\w.]+\1\s*\)$')
_ESC_FALLBACK_RE = re.compile(r'^(esc|_pgnLibEsc)\(.*\)\s*\|\|\s*(".*"|\'.*\')$')
_T_WITH_VARS_RE = re.compile(r'^t\(\s*(["\'])[\w.]+\1\s*,\s*(\{.*\})\s*\)$', re.S)
_STRING_LITERAL_RE = re.compile(r'^(".*"|\'.*\')$', re.S)


def _split_ternary(expr):
    """Repère le PREMIER "?" de premier niveau (pas "?." ni dans une sous-
    expression entre parenthèses/accolades/crochets/guillemets) et le ":"
    de premier niveau qui le referme. Retourne (cond, vrai, faux) ou None."""
    depth, i, n = 0, 0, len(expr)
    in_single = in_double = False
    q_pos = None
    while i < n:
        c = expr[i]
        if in_single:
            if c == "\\":
                i += 2
                continue
            if c == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_double = False
            i += 1
            continue
        if c == "'":
            in_single = True
        elif c == '"':
            in_double = True
        elif c in "([{":
            depth += 1
        elif c in ")}]":
            depth -= 1
        elif c == "?" and expr[i + 1:i + 2] != "." and depth == 0 and q_pos is None:
            q_pos = i
        elif c == ":" and depth == 0 and q_pos is not None:
            return expr[:q_pos], expr[q_pos + 1:i], expr[i + 1:]
        i += 1
    return None


def _split_top_level(s, sep):
    """Découpe s sur sep en ignorant les occurrences imbriquées dans
    (), {}, [] ou une chaîne '...'/"...". """
    parts, depth, buf, i, n = [], 0, [], 0, len(s)
    in_single = in_double = False
    while i < n:
        c = s[i]
        if in_single:
            buf.append(c)
            if c == "\\":
                i += 1
                if i < n:
                    buf.append(s[i])
            elif c == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            buf.append(c)
            if c == "\\":
                i += 1
                if i < n:
                    buf.append(s[i])
            elif c == '"':
                in_double = False
            i += 1
            continue
        if c == "'":
            in_single = True
        elif c == '"':
            in_double = True
        elif c in "({[":
            depth += 1
        elif c in ")}]":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _is_safe_t_object_literal(obj_literal, _depth):
    """{n: x, path: esc(y)} : chaque valeur doit être elle-même sûre."""
    inner = obj_literal.strip()
    if not (inner.startswith("{") and inner.endswith("}")):
        return False
    inner = inner[1:-1]
    if not inner.strip():
        return True
    for pair in _split_top_level(inner, ","):
        if not pair.strip():
            continue
        key_value = _split_top_level(pair, ":")
        if len(key_value) < 2:
            return False
        value = ":".join(key_value[1:])
        if not _is_safe(value, _depth + 1):
            return False
    return True


def _is_safe(expr, _depth=0):
    expr = expr.strip()
    if any(expr.startswith(p) and expr.endswith(")") for p in _ESC_EQUIVALENT_PREFIXES):
        return True
    if _ESC_FALLBACK_RE.match(expr):
        return True
    if _BARE_T_RE.match(expr):
        return True
    if _STRING_LITERAL_RE.match(expr):
        return True
    if expr in SAFE_T_CALLS or expr in SAFE_IDENTIFIERS:
        return True
    if _depth >= 4:
        return False
    m = _T_WITH_VARS_RE.match(expr)
    if m and _is_safe_t_object_literal(m.group(2), _depth):
        return True
    ternary = _split_ternary(expr)
    if ternary:
        _, vrai, faux = ternary
        if _is_safe(vrai, _depth + 1) and _is_safe(faux, _depth + 1):
            return True
    if "+" in expr:
        parts = _split_top_level(expr, "+")
        if len(parts) > 1 and all(_is_safe(p, _depth + 1) for p in parts):
            return True
    if "`" in expr:
        # Template litéral imbriqué (ex: dans une branche de ternaire déjà
        # traitée ci-dessus, ou isolé) : valider récursivement ses propres
        # interpolations plutôt que le texte brut de l'expression entière.
        nested = _extract_backtick_templates(expr)
        if nested:
            return all(
                _is_safe(sub, _depth + 1)
                for _, txt in nested
                for sub in _extract_interpolations(txt)
            )
    return False


def _unsafe_interpolations():
    source = JS_PATH.read_text(encoding="utf-8")
    templates = _extract_backtick_templates(source)
    html_templates = [(start, txt) for start, txt in templates if "<" in txt]
    unsafe = []
    for start, txt in html_templates:
        lineno = source.count("\n", 0, start) + 1
        for expr in _extract_interpolations(txt):
            if not _is_safe(expr):
                unsafe.append((lineno, expr.strip()))
    return unsafe


def test_toute_interpolation_html_est_echappee_ou_whitelistee():
    unsafe = _unsafe_interpolations()
    assert not unsafe, (
        "app.js : interpolation(s) ${...} non échappée(s) dans un template "
        "HTML (ni esc(...), ni t(\"clé\") sans paramètre externe, ni entrée "
        "documentée de SAFE_T_CALLS/SAFE_IDENTIFIERS) :\n"
        + "\n".join(f"  app.js:{ln} -> {e}" for ln, e in unsafe)
        + "\nSi le texte vient de l'extérieur (serveur/joueur/PGN/LLM), "
          "enveloppe-le dans esc(...). S'il est authentiquement interne, "
          "ajoute-le à SAFE_IDENTIFIERS/SAFE_T_CALLS avec sa raison."
    )


# ── (b) markdownToHtml : esc( avant le premier .replace( ──────────────────

def test_markdown_to_html_echappe_avant_la_mise_en_forme():
    source = JS_PATH.read_text(encoding="utf-8")
    m = re.search(r"function markdownToHtml\([^)]*\)\s*\{(.*?)\n\}", source, re.S)
    assert m, "app.js : fonction markdownToHtml introuvable"
    body = m.group(1)
    esc_pos = body.find("esc(")
    first_replace_pos = body.find(".replace(")
    assert esc_pos != -1, "markdownToHtml n'appelle pas esc("
    assert first_replace_pos != -1, "markdownToHtml ne fait plus de mise en forme (.replace)"
    assert esc_pos < first_replace_pos, (
        "markdownToHtml doit appeler esc( AVANT son premier .replace( "
        "(échapper le texte brut avant d'appliquer les remplacements de "
        "mise en forme markdown)"
    )


# ── (c) esc() échappe les cinq caractères et traite null/undefined ────────

def test_esc_echappe_les_cinq_caracteres_et_gere_null_undefined():
    source = JS_PATH.read_text(encoding="utf-8")
    m = re.search(r"function esc\(str\)\s*\{(.*?)\n\}", source, re.S)
    assert m, "app.js : fonction esc(str) introuvable"
    body = m.group(1)
    for char, pattern in [
        ("&", r"replace\(/&/g"),
        ("<", r"replace\(/</g\s*,\s*\"&lt;\"\)|replace\(/</g"),
        (">", r"replace\(/>/g"),
        ('"', r'replace\(/"/g'),
        ("'", r"replace\(/'/g"),
    ]:
        assert re.search(pattern, body), f"esc() n'échappe pas le caractère {char!r}"
    assert re.search(r"(===|==)\s*null", body) or "undefined" in body, (
        "esc() ne semble pas traiter explicitement null/undefined"
    )


def test_esc_retourne_chaine_vide_pour_null_et_undefined():
    """Double vérification par analyse du corps : esc(null) et
    esc(undefined) doivent toutes deux produire une chaîne vide, pas
    'null'/'undefined' littéral."""
    source = JS_PATH.read_text(encoding="utf-8")
    m = re.search(r"function esc\(str\)\s*\{(.*?)\n\}", source, re.S)
    assert m
    body = m.group(1)
    assert re.search(r"str\s*===\s*null\s*\|\|\s*str\s*===\s*undefined", body), (
        "esc() doit tester explicitement str === null || str === undefined "
        "et retourner \"\" dans ce cas (pas de coercition implicite qui "
        "produirait les chaînes 'null'/'undefined')"
    )
