"""
nicsoft/tests/test_issue378_lichess_reconnect_banner_text.py — AlChess

Issue #378 : le bandeau de reconnexion Lichess ("lichess-reconnecting-banner",
clé i18n "lichess.reconnexion") rappelle désormais que la partie reste
gérable directement sur lichess.org (jouer, réclamer, abandonner),
indépendamment d'AlChess — solution purement textuelle conclue par l'étude
#376 (limitation Lichess confirmée pour la réclamation en cas de longue
panne réseau, point ouvert de #368).

Garde-fou SANS NAVIGATEUR (analyse statique, sur le modèle de
test_issue299_board_absent_ui.py) : la clé existe et est cohérente dans
fr.json/en.json/de.json, mentionne bien lichess.org dans les trois langues,
et le bandeau HTML utilise toujours la même clé sans logique nouvelle.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n"
HTML_PATH = REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html"

CLE_RECONNEXION = "lichess.reconnexion"


def _load(locale):
    return json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def test_cle_reconnexion_presente_et_non_vide_dans_les_trois_locales():
    for locale in ("fr", "en", "de"):
        data = _load(locale)
        assert CLE_RECONNEXION in data, f"{locale}.json n'a pas la clé {CLE_RECONNEXION}"
        assert data[CLE_RECONNEXION].strip(), f"{locale}.json : {CLE_RECONNEXION} est vide"


def test_coherence_des_cles_entre_les_trois_locales():
    """Les trois fichiers i18n doivent exposer exactement le même jeu de
    clés — aucune clé ajoutée ou retirée par cette tâche purement
    textuelle."""
    fr, en, de = _load("fr"), _load("en"), _load("de")
    assert set(fr) == set(en), f"clés fr/en divergentes : {set(fr) ^ set(en)}"
    assert set(fr) == set(de), f"clés fr/de divergentes : {set(fr) ^ set(de)}"


def test_bandeau_mentionne_lichess_org_dans_les_trois_locales():
    """Rappel demandé par #378 : la partie reste gérable sur lichess.org
    dans un navigateur, indépendamment d'AlChess."""
    for locale in ("fr", "en", "de"):
        texte = _load(locale)[CLE_RECONNEXION]
        assert "lichess.org" in texte, f"{locale}.json : {CLE_RECONNEXION} ne mentionne pas lichess.org"


def test_bandeau_reste_court_et_lisible():
    """Le bandeau reste une courte phrase, pas un paragraphe."""
    for locale in ("fr", "en", "de"):
        texte = _load(locale)[CLE_RECONNEXION]
        assert len(texte) <= 160, f"{locale}.json : {CLE_RECONNEXION} trop long ({len(texte)} caractères)"


def test_bandeau_html_utilise_toujours_la_meme_cle_sans_nouvelle_logique():
    """Le bandeau garde son comportement actuel (même id, même clé i18n,
    toujours masqué par défaut) : seul le texte a changé."""
    html = HTML_PATH.read_text(encoding="utf-8")
    pattern = (
        r'<div id="lichess-reconnecting-banner" class="lichess-info-banner" '
        r'style="display:none;" data-i18n="lichess\.reconnexion">'
    )
    assert re.search(pattern, html), "bandeau lichess-reconnecting-banner absent ou modifié au-delà du texte"


def test_fallback_html_coherent_avec_le_texte_francais():
    """Le texte de repli statique dans index.html (affiché avant le chargement
    de i18n.js) doit rester synchronisé avec fr.json pour éviter un flash de
    texte obsolète."""
    html = HTML_PATH.read_text(encoding="utf-8")
    fr_texte = _load("fr")[CLE_RECONNEXION]
    bloc = re.search(
        r'<div id="lichess-reconnecting-banner"[^>]*>([^<]*)</div>', html
    )
    assert bloc is not None
    assert bloc.group(1) == fr_texte
