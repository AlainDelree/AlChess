"""
nicsoft/tests/test_issue299_board_absent_ui.py — NicLink
Issue #299, point 1 : garde-fou SANS NAVIGATEUR (analyse statique, sur le
modèle de test_css_extraction_hidden_elements.py) verrouillant :
  (c) les nouvelles clés de traduction (bande d'alerte échiquier absent)
      existent dans fr.json/en.json/de.json et sont cohérentes entre elles ;
  (d) les éléments HTML (bandes d'alerte) et les classes CSS (bande +
      indicateur rouge) ajoutés pour rendre l'absence d'échiquier visible
      sont bien présents dans templates/index.html / static/css/main.css /
      static/app.js.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n"
HTML_PATH = REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html"
CSS_PATH = REPO_ROOT / "nicsoft" / "web" / "static" / "css" / "main.css"
JS_PATH = REPO_ROOT / "nicsoft" / "web" / "static" / "app.js"

NOUVELLES_CLES = ["banner.board_absent_menu", "banner.board_absent_session"]

BANNER_IDS = [
    "board-warning-banner-menu",
    "board-warning-banner-config",
    "board-warning-banner-config-humain",
    "board-warning-banner-exercices",
]


# ── (c) Clés de traduction ──────────────────────────────────────────────────

def _load(locale):
    return json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def test_nouvelles_cles_presentes_dans_les_trois_locales():
    for locale in ("fr", "en", "de"):
        data = _load(locale)
        for cle in NOUVELLES_CLES:
            assert cle in data, f"{locale}.json n'a pas la clé {cle}"
            assert data[cle].strip(), f"{locale}.json : {cle} est vide"


def test_coherence_des_cles_entre_les_trois_locales():
    """Garde-fou de cohérence générale (pas seulement les clés ajoutées ici) :
    les trois fichiers i18n doivent exposer exactement le même jeu de clés."""
    fr, en, de = _load("fr"), _load("en"), _load("de")
    assert set(fr) == set(en), f"clés fr/en divergentes : {set(fr) ^ set(en)}"
    assert set(fr) == set(de), f"clés fr/de divergentes : {set(fr) ^ set(de)}"


# ── (d) Éléments HTML statiques ─────────────────────────────────────────────

def test_bandes_alerte_presentes_dans_index_html():
    html = HTML_PATH.read_text(encoding="utf-8")
    for banner_id in BANNER_IDS:
        pattern = rf'id="{re.escape(banner_id)}"[^>]*class="board-warning-banner hidden"'
        assert re.search(pattern, html), f"bande {banner_id} absente ou mal classée dans index.html"


def test_bandes_alerte_utilisent_les_bonnes_cles_i18n():
    html = HTML_PATH.read_text(encoding="utf-8")
    bloc_menu = re.search(r'id="board-warning-banner-menu"[^>]*data-i18n="([^"]+)"', html)
    assert bloc_menu and bloc_menu.group(1) == "banner.board_absent_menu"
    for banner_id in ("board-warning-banner-config", "board-warning-banner-config-humain",
                      "board-warning-banner-exercices"):
        bloc = re.search(rf'id="{re.escape(banner_id)}"[^>]*data-i18n="([^"]+)"', html)
        assert bloc and bloc.group(1) == "banner.board_absent_session", (
            f"{banner_id} doit utiliser banner.board_absent_session (mention écran virtuel)"
        )


def test_pill_statut_echiquier_toujours_present():
    """La bande ne remplace pas l'indicateur d'en-tête existant (#board-status-pill)."""
    html = HTML_PATH.read_text(encoding="utf-8")
    assert 'id="board-status-pill"' in html


# ── (d) CSS — coloration rouge de l'indicateur + style de la bande ─────────

def test_css_pill_board_error_rouge():
    css = CSS_PATH.read_text(encoding="utf-8")
    assert ".pill-board-error" in css


def test_css_board_warning_banner():
    css = CSS_PATH.read_text(encoding="utf-8")
    assert ".board-warning-banner" in css
    assert ".board-warning-banner.hidden" in css


# ── (d) JS — bascule effective selon l'état d'erreur de l'échiquier ────────

def test_js_applique_la_classe_erreur_et_le_titre_sur_le_pill():
    js = JS_PATH.read_text(encoding="utf-8")
    assert 'pill.classList.toggle("pill-board-error", _boardError)' in js
    assert "pill.title" in js


def test_js_bascule_les_bandes_selon_boarderror():
    js = JS_PATH.read_text(encoding="utf-8")
    assert '.board-warning-banner' in js
    assert '"hidden", !_boardError' in js
