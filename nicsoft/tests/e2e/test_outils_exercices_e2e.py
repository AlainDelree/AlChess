"""
Tests e2e — Outils Exercices (7 outils).

Couvre : navigation, ordre des cartes, Convertir SAN→UCI, Ajouter (auto-ID + vérifier),
Import ECO (recherche), Explorer Polyglot (livres), Modifier (liste + filtre),
Import PGN (dropzone), Corbeille dans Import PGN et Convertir SAN→UCI.

Non couvert : Wikipedia update (nécessite internet), upload fichier PGN réel.

Lancer : pytest nicsoft/tests/e2e/test_outils_exercices_e2e.py -v
"""
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect


I18N_DIR = Path(__file__).resolve().parents[2] / "web" / "static" / "i18n"


def _i18n_values(cle):
    """Traductions connues (fr/en/de) d'une clé i18n — sert à vérifier du texte
    affiché sans dépendre de la locale par défaut de Playwright (issue #211)."""
    valeurs = set()
    for lang in ("fr", "en", "de"):
        data = json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        if cle in data:
            valeurs.add(data[cle])
    return valeurs


TITRES_CLES = [
    "outils.import_pgn.titre",
    "outils.convertir.titre",
    "outils.eco.titre",
    "outils.polyglot.titre",
    "outils.ajouter.titre",
    "outils.modifier.titre",
    "outils.wiki.titre",
]


@pytest.fixture
def at_outils(page):
    """Navigue vers l'écran Outils Exercices (depuis n'importe quel état)."""
    if page.locator("#screen-outils-exercices").is_visible():
        return page
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=10000)
    # Ciblage par attribut data-mode, indépendant de la locale (issue #211, cf. #208 ;
    # bouton du menu passé de onclick= à data-action/data-mode par l'issue #220)
    page.locator("button[data-mode=\"outils_exercices\"]").click()
    page.wait_for_selector("#screen-outils-exercices", state="visible", timeout=8000)
    return page


# ── Navigation ─────────────────────────────────────────────────────────────────

def test_outils_exercices_accessible(at_menu):
    """Clic Outils Exercices → écran visible."""
    # Ciblage par attribut data-mode, indépendant de la locale (issue #211, cf. #208 ;
    # bouton du menu passé de onclick= à data-action/data-mode par l'issue #220)
    at_menu.locator("button[data-mode=\"outils_exercices\"]").click()
    at_menu.wait_for_selector("#screen-outils-exercices", state="visible", timeout=8000)
    assert at_menu.locator("#screen-outils-exercices").is_visible()


def test_retour_menu_depuis_outils(at_outils):
    """Outils Exercices → Retour au menu → menu propre."""
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #245 partie 1/4)
    at_outils.locator("#screen-outils-exercices button[data-action=\"back_menu\"]").click()
    at_outils.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    assert at_outils.locator("#screen-menu").is_visible()


# ── Structure ──────────────────────────────────────────────────────────────────

def test_sept_cartes_visibles(at_outils):
    """7 cartes outil-card présentes à l'écran."""
    assert at_outils.locator("#screen-outils-exercices .outil-card").count() == 7


def test_ordre_des_outils(at_outils):
    """Les 7 titres sont dans le bon ordre."""
    # Comparaison via les traductions connues (fr/en/de), indépendant de la
    # locale par défaut de Playwright (issue #211).
    titres = at_outils.locator("#screen-outils-exercices .outil-title").all_text_contents()
    assert len(titres) == len(TITRES_CLES)
    for titre, cle in zip(titres, TITRES_CLES):
        assert titre in _i18n_values(cle)


# ── Convertir SAN → UCI ────────────────────────────────────────────────────────

def test_convertir_san_uci_valide(at_outils):
    """SAN valide '1. e4 e5 2. Nf3 Nc6 3. Bb5' → résultat UCI contient 'e2e4'."""
    at_outils.locator("#outils-uci-input").fill("1. e4 e5 2. Nf3 Nc6 3. Bb5")
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #245 partie 1/4)
    at_outils.locator("button[data-action=\"outils_san_to_uci\"]").click()
    result = at_outils.locator("#outils-uci-result")
    result.wait_for(state="visible", timeout=5000)
    # Attendre la réponse socket (le div montre "Conversion…" pendant le traitement)
    expect(result).to_contain_text("e2e4", timeout=5000)


def test_convertir_san_uci_resultat_complet(at_outils):
    """Conversion '1. d4 d5' → résultat contient d2d4 et d7d5."""
    at_outils.locator("#outils-uci-input").fill("1. d4 d5")
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #245 partie 1/4)
    at_outils.locator("button[data-action=\"outils_san_to_uci\"]").click()
    result = at_outils.locator("#outils-uci-result")
    result.wait_for(state="visible", timeout=5000)
    expect(result).to_contain_text("d2d4", timeout=5000)
    expect(result).to_contain_text("d7d5", timeout=5000)


def test_convertir_san_uci_sans_coups(at_outils):
    """PGN non reconnu → résultat chargé mais InitMoves vide (pas de coups UCI)."""
    at_outils.locator("#outils-uci-input").fill("xxx yyy zzz")
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #245 partie 1/4)
    at_outils.locator("button[data-action=\"outils_san_to_uci\"]").click()
    result = at_outils.locator("#outils-uci-result")
    result.wait_for(state="visible", timeout=5000)
    # Attendre que "Conversion…" disparaisse (réponse reçue)
    expect(result).not_to_contain_text("Conversion…", timeout=5000)
    # Aucun coup UCI généré
    assert "e2e4" not in result.text_content()


# ── Ajouter une ouverture ──────────────────────────────────────────────────────

def test_ajouter_autoid_genere(at_outils):
    """Saisir un nom → ID auto-généré non vide et en minuscules."""
    at_outils.locator("#add-nom").fill("Ruy Lopez Berlin")
    at_outils.locator("#add-nom").dispatch_event("input")
    auto_id = at_outils.locator("#add-id").input_value()
    assert len(auto_id) > 0
    assert auto_id == auto_id.lower()


def test_ajouter_autoid_caracteres_speciaux(at_outils):
    """Nom avec accents → ID sans accents ni espaces."""
    at_outils.locator("#add-nom").fill("Défense Française — Variante")
    at_outils.locator("#add-nom").dispatch_event("input")
    auto_id = at_outils.locator("#add-id").input_value()
    assert " " not in auto_id
    assert "é" not in auto_id and "ç" not in auto_id


def test_ajouter_verifier_preview(at_outils):
    """Formulaire complet → Vérifier → zone preview affichée."""
    at_outils.locator("#add-nom").fill("Test Ouverture e2e")
    at_outils.locator("#add-nom").dispatch_event("input")
    at_outils.locator("#add-eco").fill("C65")
    at_outils.locator("#add-moves").fill("e2e4 e7e5 g1f3 b8c6 f1b5")
    # Ciblage par attribut onclick, indépendant de la locale (issue #211, cf. #208)
    at_outils.locator("button[onclick=\"outilsAddVerify()\"]").click()
    preview = at_outils.locator("#outils-add-preview")
    preview.wait_for(state="visible", timeout=5000)
    assert preview.is_visible()


def test_ajouter_effacer_remet_a_zero(at_outils):
    """Bouton ✕ Effacer vide les champs Ajouter."""
    at_outils.locator("#add-nom").fill("Test Effacer")
    at_outils.locator("#add-moves").fill("e2e4 e7e5")
    # Ciblage par attribut onclick, indépendant de la locale (issue #211, cf. #208)
    at_outils.locator("button[onclick=\"outilsAddReset()\"]").click()
    assert at_outils.locator("#add-nom").input_value() == ""
    assert at_outils.locator("#add-moves").input_value() == ""


# ── Import ECO Lichess ─────────────────────────────────────────────────────────

def test_eco_search_c65_renvoie_resultats(at_outils):
    """Recherche 'C65' → au moins une ligne dans le tableau."""
    at_outils.locator("#eco-filter").fill("C65")
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #246 partie 2/4)
    at_outils.locator("button[data-action=\"outils_eco_search\"]").click()
    # eco-results-wrap peut être déjà visible d'un test précédent — attendre une ligne
    at_outils.locator("#eco-results-body tr").first.wait_for(state="visible", timeout=8000)
    assert at_outils.locator("#eco-results-body tr").count() > 0


def test_eco_search_plage_renvoie_resultats(at_outils):
    """Recherche 'C60-C67' → plusieurs lignes."""
    at_outils.locator("#eco-filter").fill("C60-C67")
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #246 partie 2/4)
    at_outils.locator("button[data-action=\"outils_eco_search\"]").click()
    # eco-results-wrap peut être déjà visible d'un test précédent —
    # attendre qu'au moins une ligne soit présente plutôt que la visibilité du wrap
    at_outils.locator("#eco-results-body tr").first.wait_for(state="visible", timeout=8000)
    assert at_outils.locator("#eco-results-body tr").count() > 1


def test_eco_tout_selectionner(at_outils):
    """Checkbox 'Tout sélectionner' coche toutes les lignes cochables (hors doublons disabled)."""
    at_outils.locator("#eco-filter").fill("C65")
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #246 partie 2/4)
    at_outils.locator("button[data-action=\"outils_eco_search\"]").click()
    at_outils.locator("#eco-results-body tr").first.wait_for(state="visible", timeout=8000)
    at_outils.locator("#eco-check-all").check()
    total = at_outils.locator("#eco-results-body input[type=checkbox]:not(:disabled)").count()
    coches = at_outils.locator("#eco-results-body input[type=checkbox]:not(:disabled):checked").count()
    assert total > 0 and coches == total


# ── Explorer un livre Polyglot ─────────────────────────────────────────────────

def test_explorer_livres_listes(at_outils):
    """Au démarrage de l'écran, au moins un livre .bin est listé."""
    at_outils.wait_for_timeout(2000)
    no_books = at_outils.locator("#explore-no-books")
    if no_books.is_visible():
        pytest.skip("Aucun livre .bin disponible dans data/books/")
    assert at_outils.locator("#explore-book-list button").count() > 0


def test_explorer_selectionner_livre_ouvre_panel(at_outils):
    """Clic sur un livre → panel explorateur + coups visibles."""
    at_outils.wait_for_timeout(1000)
    if at_outils.locator("#explore-no-books").is_visible():
        pytest.skip("Aucun livre .bin disponible")
    at_outils.locator("#explore-book-list button").first.click()
    panel = at_outils.locator("#explore-panel")
    panel.wait_for(state="visible", timeout=5000)
    assert panel.is_visible()
    # Le nom du livre affiché confirme que la sélection est prise en compte
    expect(at_outils.locator("#explore-book-name")).not_to_have_text("", timeout=5000)


def test_explorer_reset_retour_debut(at_outils):
    """Bouton ↺ Début remet l'explorateur à la position initiale."""
    at_outils.wait_for_timeout(1500)
    if at_outils.locator("#explore-no-books").is_visible():
        pytest.skip("Aucun livre .bin disponible")
    panel = at_outils.locator("#explore-panel")
    if not panel.is_visible():
        # Le panel n'est pas encore ouvert : sélectionner un livre
        at_outils.locator("#explore-book-list button").first.wait_for(state="visible", timeout=5000)
        at_outils.locator("#explore-book-list button").first.click()
        panel.wait_for(state="visible", timeout=5000)
    # Ciblage par attribut data-action, indépendant de la locale (issue #211, cf. #208,
    # migré vers data-action en #246 partie 2/4)
    at_outils.locator("button[data-action=\"explore_reset\"]").click()
    at_outils.wait_for_timeout(500)
    # Après reset, l'historique montre la position initiale (traduite) ou est vide
    # — comparaison indépendante de la locale par défaut de Playwright (issue #211).
    texte = at_outils.locator("#explore-history").text_content().strip()
    assert texte == "" or texte in _i18n_values("common.position_initiale")


# ── Modifier une ouverture ─────────────────────────────────────────────────────

def test_modifier_liste_chargee(at_outils):
    """Liste Modifier chargée automatiquement → au moins une ouverture."""
    at_outils.wait_for_timeout(2000)
    wrap = at_outils.locator("#edit-list-wrap")
    texte = wrap.text_content()
    assert "Chargement" not in texte
    assert len(texte.strip()) > 5


def test_modifier_filtre_reduit_liste(at_outils):
    """Filtre 'ruy' → liste filtrée sans crash."""
    at_outils.wait_for_timeout(1500)
    at_outils.locator("#edit-search").fill("ruy")
    at_outils.wait_for_timeout(500)
    # Pas de crash = succès
    assert at_outils.locator("#screen-outils-exercices").is_visible()


def test_modifier_clic_ouvre_formulaire(at_outils):
    """Cliquer sur une ouverture de la liste → formulaire d'édition visible."""
    # Attendre le chargement socket via JS direct (contourne les limites du count() Playwright)
    at_outils.wait_for_function(
        "document.querySelectorAll('#edit-list-wrap tbody tr').length > 0",
        timeout=5000
    )
    premiere_ligne = at_outils.locator("#edit-list-wrap tbody tr").first
    premiere_ligne.click()
    form = at_outils.locator("#edit-form")
    form.wait_for(state="visible", timeout=3000)
    assert form.is_visible()
    assert len(at_outils.locator("#edit-form-id").text_content()) > 0


# ── Import PGN ────────────────────────────────────────────────────────────────

def test_import_pgn_dropzone_visible(at_outils):
    """Zone de dépôt .pgn visible."""
    assert at_outils.locator("#outils-pgn-dropzone").is_visible()


def test_import_pgn_boutons_caches_initialement(at_outils):
    """Boutons Importer et Effacer masqués avant sélection de fichier."""
    assert not at_outils.locator("#outils-pgn-btn-import").is_visible()
    assert not at_outils.locator("#outils-pgn-btn-clear").is_visible()


# ── Wikipedia (structure seulement) ───────────────────────────────────────────

def test_wikipedia_bouton_present(at_outils):
    """Bouton 'Mettre à jour depuis Wikipedia' présent (pas cliqué — évite appel réseau)."""
    assert at_outils.locator("#wiki-btn").is_visible()
    assert not at_outils.locator("#wiki-result").is_visible()


# ── Corbeille dans Outils Exercices ───────────────────────────────────────────
# IMPORTANT : les 2 premiers tests vérifient l'état corbeille vide — ils doivent
# s'exécuter avant tout ajout en corbeille (aucun autre test de ce fichier n'ajoute).

def test_corbeille_import_pgn_selecteur_present(at_outils):
    """Sélecteur corbeille présent dans la carte 'Importer mes lignes PGN'."""
    assert at_outils.locator("#basket-select-outils-pgn").is_visible()


def test_corbeille_uci_selecteur_present(at_outils):
    """Sélecteur corbeille présent dans la carte 'Convertir SAN → UCI'."""
    assert at_outils.locator("#basket-select-outils-uci").is_visible()


def test_corbeille_labels_vides(at_outils):
    """Les deux sélecteurs affichent le libellé 'corbeille vide' (traduit) quand la corbeille est vide."""
    # Comparaison via les traductions connues (fr/en/de), indépendant de la
    # locale par défaut de Playwright (issue #211).
    valeurs_vides = _i18n_values("common.corbeille_vide")
    label_pgn = at_outils.locator("#basket-select-outils-pgn .basket-sel-label").text_content()
    label_uci = at_outils.locator("#basket-select-outils-uci .basket-sel-label").text_content()
    assert any(v in label_pgn for v in valeurs_vides)
    assert any(v in label_uci for v in valeurs_vides)


def test_corbeille_boutons_charger_desactives_si_vide(at_outils):
    """Boutons 🧺 Charger désactivés quand la corbeille est vide."""
    assert at_outils.locator('button[data-action="basket_load_to_outils_pgn"]').is_disabled()
    assert at_outils.locator('button[data-action="basket_load_to_outils_uci"]').is_disabled()


def test_corbeille_boutons_actives_apres_ajout(at_outils):
    """Après ajout d'une partie en corbeille, les boutons Charger s'activent."""
    at_outils.evaluate("socket.emit('basket_add', {label: 'test_e2e.pgn', pgn: '1. e4 e5 *'})")
    at_outils.wait_for_function("typeof _basket !== 'undefined' && _basket.length > 0", timeout=5000)
    assert not at_outils.locator('button[data-action="basket_load_to_outils_pgn"]').is_disabled()
    assert not at_outils.locator('button[data-action="basket_load_to_outils_uci"]').is_disabled()


def test_corbeille_charger_uci_remplit_textarea(at_outils):
    """Charger depuis corbeille dans 'Convertir SAN → UCI' remplit le textarea."""
    at_outils.locator("#outils-uci-input").fill("")
    at_outils.locator('button[data-action="basket_load_to_outils_uci"]').click()
    at_outils.wait_for_function("document.getElementById('outils-uci-input').value.length > 0", timeout=5000)
    assert len(at_outils.locator("#outils-uci-input").input_value()) > 0


def test_corbeille_charger_pgn_affiche_preview(at_outils):
    """Charger depuis corbeille dans 'Importer mes lignes PGN' affiche la prévisualisation."""
    at_outils.locator('button[data-action="basket_load_to_outils_pgn"]').click()
    at_outils.locator("#outils-pgn-preview-list").wait_for(state="visible", timeout=8000)
    assert at_outils.locator("#outils-pgn-preview-list").is_visible()
