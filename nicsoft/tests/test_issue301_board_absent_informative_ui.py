"""
nicsoft/tests/test_issue301_board_absent_informative_ui.py — NicLink
Issue #301 (suite #299/#300), garde-fou SANS NAVIGATEUR (analyse statique,
sur le modèle de test_issue299_board_absent_ui.py) verrouillant :
  (a) les textes des bandes d'information et de l'indication du bouton
      Connecter restent des clés i18n cohérentes entre fr/en/de ;
  (b) aucune de ces clés ne contient plus un ton d'alerte : ni le mot
      « erreur »/« error » ni le symbole d'avertissement ⚠ ;
  (c) le CSS n'utilise plus les anciennes couleurs d'alerte (rouge) pour
      l'indicateur d'en-tête, les bandes et l'indication du bouton
      Connecter — remplacées par la palette bleutée déjà utilisée ailleurs
      dans main.css.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n"
CSS_PATH = REPO_ROOT / "nicsoft" / "web" / "static" / "css" / "main.css"

CLES_INFORMATIVES = [
    "banner.board_absent_menu",
    "banner.board_absent_session",
    "banner.board_absent_hh",
    "menu.hint.connecter",
    "status.board.non_detecte",
]

MOTS_ALERTE = ("erreur", "error")
SYMBOLE_ALERTE = "⚠"


def _load(locale):
    return json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def test_aucune_cle_informative_ne_contient_un_ton_d_alerte():
    for locale in ("fr", "en", "de"):
        data = _load(locale)
        for cle in CLES_INFORMATIVES:
            assert cle in data, f"{locale}.json n'a pas la clé {cle}"
            texte = data[cle]
            texte_bas = texte.lower()
            for mot in MOTS_ALERTE:
                assert mot not in texte_bas, (
                    f"{locale}.json::{cle} contient le mot d'alerte « {mot} » : {texte!r}"
                )
            assert SYMBOLE_ALERTE not in texte, (
                f"{locale}.json::{cle} contient le symbole d'avertissement : {texte!r}"
            )
            assert "!" not in texte, (
                f"{locale}.json::{cle} contient un point d'exclamation : {texte!r}"
            )


def test_coherence_des_cles_entre_les_trois_locales():
    fr, en, de = _load("fr"), _load("en"), _load("de")
    assert set(fr) == set(en), f"clés fr/en divergentes : {set(fr) ^ set(en)}"
    assert set(fr) == set(de), f"clés fr/de divergentes : {set(fr) ^ set(de)}"


# ── CSS — plus aucune teinte rouge d'alerte pour l'état « échiquier absent » ──

ANCIENNES_COULEURS_ALERTE = ("#fbdede", "#8a1f1f", "#e94560")


def test_css_pill_board_absent_sans_couleur_d_alerte():
    css = CSS_PATH.read_text(encoding="utf-8")
    bloc = re.search(r"\.pill-disconnected\.pill-board-absent\s*\{[^}]*\}", css)
    assert bloc, "règle CSS .pill-disconnected.pill-board-absent introuvable"
    for couleur in ANCIENNES_COULEURS_ALERTE:
        assert couleur not in bloc.group(0), (
            f".pill-board-absent utilise encore une couleur d'alerte ({couleur})"
        )


def test_css_board_warning_banner_sans_couleur_d_alerte():
    css = CSS_PATH.read_text(encoding="utf-8")
    bloc = re.search(r"\.board-warning-banner\s*\{[^}]*\}", css)
    assert bloc, "règle CSS .board-warning-banner introuvable"
    for couleur in ANCIENNES_COULEURS_ALERTE:
        assert couleur not in bloc.group(0), (
            f".board-warning-banner utilise encore une couleur d'alerte ({couleur})"
        )


def test_css_connect_hint_sans_couleur_d_alerte():
    css = CSS_PATH.read_text(encoding="utf-8")
    bloc = re.search(r"\.connect-hint\s*\{[^}]*\}", css)
    assert bloc, "règle CSS .connect-hint introuvable"
    for couleur in ANCIENNES_COULEURS_ALERTE:
        assert couleur not in bloc.group(0), (
            f".connect-hint utilise encore une couleur d'alerte ({couleur})"
        )
    # La flèche (::before) ne doit plus pointer en rouge non plus.
    bloc_fleche = re.search(r"\.connect-hint::before\s*\{[^}]*\}", css)
    assert bloc_fleche, "règle CSS .connect-hint::before (flèche) introuvable"
    assert "#e94560" not in bloc_fleche.group(0)
