"""
nicsoft/tests/test_issue300_hh_board_required_ui.py — NicLink
Issue #300 (suite #299), garde-fou SANS NAVIGATEUR (analyse statique, sur le
modèle de test_issue299_board_absent_ui.py) verrouillant :
  (a) l'écran de préparation Humain contre Humain utilise la nouvelle clé de
      bande banner.board_absent_hh (texte « échiquier physique obligatoire »),
      tandis que Pédagogique et Exercices gardent banner.board_absent_session ;
  (b) les deux nouvelles clés (bande HH + indication bouton Connecter)
      existent dans fr.json/en.json/de.json ;
  (c) le bouton de démarrage Humain contre Humain a la logique de
      désactivation/réactivation selon l'état de l'échiquier ;
  (d) l'indication near le bouton Connecter existe, est cachée par défaut,
      pilotée par l'état de l'échiquier, et ne capte pas les clics.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n"
HTML_PATH = REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html"
CSS_PATH = REPO_ROOT / "nicsoft" / "web" / "static" / "css" / "main.css"
JS_PATH = REPO_ROOT / "nicsoft" / "web" / "static" / "app.js"

NOUVELLES_CLES = ["banner.board_absent_hh", "menu.hint.connecter"]


def _load(locale):
    return json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


# ── Clés de traduction ──────────────────────────────────────────────────

def test_nouvelles_cles_presentes_dans_les_trois_locales():
    for locale in ("fr", "en", "de"):
        data = _load(locale)
        for cle in NOUVELLES_CLES:
            assert cle in data, f"{locale}.json n'a pas la clé {cle}"
            assert data[cle].strip(), f"{locale}.json : {cle} est vide"


def test_coherence_des_cles_entre_les_trois_locales():
    fr, en, de = _load("fr"), _load("en"), _load("de")
    assert set(fr) == set(en), f"clés fr/en divergentes : {set(fr) ^ set(en)}"
    assert set(fr) == set(de), f"clés fr/de divergentes : {set(fr) ^ set(de)}"


# ── Bande d'alerte : HH a sa propre clé, Pédagogique/Exercices gardent l'ancienne ──

def test_bande_hh_utilise_la_nouvelle_cle():
    html = HTML_PATH.read_text(encoding="utf-8")
    bloc = re.search(r'id="board-warning-banner-config-humain"[^>]*data-i18n="([^"]+)"', html)
    assert bloc and bloc.group(1) == "banner.board_absent_hh", (
        "la bande Humain contre Humain doit utiliser banner.board_absent_hh "
        "(ce mode n'a pas de repli virtuel)"
    )


def test_bandes_pedagogique_et_exercices_gardent_l_ancienne_cle():
    html = HTML_PATH.read_text(encoding="utf-8")
    for banner_id in ("board-warning-banner-config", "board-warning-banner-exercices"):
        bloc = re.search(rf'id="{re.escape(banner_id)}"[^>]*data-i18n="([^"]+)"', html)
        assert bloc and bloc.group(1) == "banner.board_absent_session", (
            f"{banner_id} doit rester sur banner.board_absent_session (mode avec repli virtuel)"
        )


# ── Bouton de démarrage Humain contre Humain ────────────────────────────

def test_bouton_start_hh_desactive_par_defaut_dans_le_html():
    html = HTML_PATH.read_text(encoding="utf-8")
    bloc = re.search(r'<button[^>]*id="btn-start-hh"[^>]*>', html)
    assert bloc, "bouton #btn-start-hh introuvable dans index.html"
    assert "disabled" in bloc.group(0), "le bouton de démarrage HH doit être inactif par défaut"
    assert 'data-action="start_game_hh"' in bloc.group(0)


def test_js_pilote_l_activation_du_bouton_start_hh_selon_l_echiquier():
    js = JS_PATH.read_text(encoding="utf-8")
    assert 'getElementById("btn-start-hh")' in js
    assert "btnStartHH.disabled" in js
    assert "menu.hh.requiert_echiquier" in js


# ── Indication (flèche) à côté du bouton Connecter ──────────────────────

def test_indication_connecter_presente_cachee_par_defaut():
    html = HTML_PATH.read_text(encoding="utf-8")
    bloc = re.search(r'<div[^>]*id="connect-hint"[^>]*>', html)
    assert bloc, "indication #connect-hint introuvable dans index.html"
    assert "hidden" in bloc.group(0), "l'indication doit être cachée par défaut"
    assert 'data-i18n="menu.hint.connecter"' in bloc.group(0)


def test_indication_connecter_pilotee_par_l_etat_echiquier_en_js():
    js = JS_PATH.read_text(encoding="utf-8")
    assert 'getElementById("connect-hint")' in js
    assert 'connectHint.classList.toggle("hidden", !_boardError)' in js


def test_indication_connecter_ne_capte_pas_les_clics():
    css = CSS_PATH.read_text(encoding="utf-8")
    bloc = re.search(r"\.connect-hint\s*\{[^}]*\}", css)
    assert bloc, "règle CSS .connect-hint introuvable"
    assert "pointer-events: none" in bloc.group(0), (
        "l'indication ne doit jamais intercepter les clics (le bouton Connecter "
        "doit rester cliquable à travers elle)"
    )
    assert ".connect-hint.hidden" in css
