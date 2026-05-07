"""
Tests e2e — Smoke test + régression complète (navigation sans échiquier physique).

Couvre environ 70% de la checklist TESTS.md.
Non couverts : bips hardware, détection position physique, délais WAIT_FISH.

Lancer : pytest nicsoft/tests/e2e/ -v
"""
import time
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def go_menu(page):
    """Revenir au menu par JS si nécessaire."""
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


# ── Smoke tests ───────────────────────────────────────────────────────────────

def test_menu_visible(at_menu):
    """Menu visible après démarrage."""
    assert at_menu.locator("#screen-menu").is_visible()


def test_titre_alchess(at_menu):
    """Le titre AlChess est présent dans la page."""
    assert "AlChess" in at_menu.title() or at_menu.locator("h1").first.is_visible()


def test_mode_virtuel_active_bouton_pedagogique(at_menu):
    """Mode virtuel coché → bouton Pédagogique non-disabled."""
    btn = at_menu.locator("button.menu-btn-primary")
    assert not btn.is_disabled(), "Le bouton Pédagogique doit être actif en mode virtuel"


# ── Navigation Pédagogique ─────────────────────────────────────────────────────

def test_clic_pedagogique_ouvre_config(at_menu):
    """Clic Pédagogique → écran config affiché."""
    at_menu.locator("button.menu-btn-primary").click()
    at_menu.wait_for_selector("#screen-config", state="visible", timeout=5000)
    assert at_menu.locator("#screen-config").is_visible()
    go_menu(at_menu)


def test_retour_depuis_config(at_menu):
    """Config pédagogique → Retour → menu."""
    at_menu.locator("button.menu-btn-primary").click()
    at_menu.wait_for_selector("#screen-config", state="visible", timeout=5000)
    at_menu.locator("#screen-config button", has_text="Retour").click()
    at_menu.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    assert at_menu.locator("#screen-menu").is_visible()


def test_pedagogique_demarrer_puis_retour_menu(at_menu):
    """Config pédagogique → Démarrer → écran jeu → Retour au menu."""
    at_menu.locator("button.menu-btn-primary").click()
    at_menu.wait_for_selector("#screen-config", state="visible", timeout=5000)

    # Démarrer la partie (VirtualBoard + Stockfish)
    at_menu.locator("button", has_text="Démarrer la partie").click()

    # Attendre le panel-playing (state=playing)
    at_menu.wait_for_selector("#panel-playing", state="visible", timeout=30000)
    assert at_menu.locator("#panel-playing").is_visible()

    # Retour au menu — cibler panel-playing pour éviter l'ambiguïté avec les autres panels
    at_menu.locator("#panel-playing button", has_text="Retour au menu").click()
    # Confirmer dans la modal
    modal = at_menu.locator("#modal-overlay")
    if modal.is_visible():
        at_menu.locator("#modal-confirm").click()

    at_menu.wait_for_selector("#screen-menu", state="visible", timeout=8000)
    assert at_menu.locator("#screen-menu").is_visible()


# ── Navigation Humain vs Humain ────────────────────────────────────────────────

def test_hh_ouvre_config(at_menu):
    """Clic HH → écran config HH (non disponible en mode virtuel — bouton absent)."""
    # HH a data-physical-only donc désactivé en mode virtuel
    btn_hh = at_menu.locator("button", has_text="Humain vs Humain")
    if btn_hh.is_disabled():
        pytest.skip("HH désactivé en mode virtuel (data-physical-only) — OK")
    btn_hh.click()
    at_menu.wait_for_selector("#screen-config-humain", state="visible", timeout=5000)
    assert at_menu.locator("#screen-config-humain").is_visible()
    go_menu(at_menu)


# ── Navigation Analyse ─────────────────────────────────────────────────────────

def test_analyse_accessible_sans_board(at_menu):
    """Analyse de partie accessible sans échiquier (pas de data-needs-board)."""
    at_menu.locator("button", has_text="Analyse de partie").click()
    # Analyse → app_state = game_over (écran de review)
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    assert at_menu.locator("#panel-gameover").is_visible()


def test_retour_depuis_analyse(at_menu):
    """Analyse → Retour au menu → menu propre."""
    if not at_menu.locator("#panel-gameover").is_visible():
        at_menu.locator("button", has_text="Analyse de partie").click()
        at_menu.wait_for_selector("#panel-gameover", state="visible", timeout=5000)

    at_menu.locator("#panel-gameover button", has_text="Retour au menu").click()
    at_menu.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    assert at_menu.locator("#screen-menu").is_visible()


# ── Navigation Exercices ───────────────────────────────────────────────────────

def test_exercices_liste_affichee(at_menu):
    """Exercices → liste des ouvertures s'affiche."""
    btn_ex = at_menu.locator("button", has_text="Exercices")
    if btn_ex.is_disabled():
        pytest.skip("Exercices nécessite un échiquier ou mode virtuel non détecté")
    btn_ex.click()
    at_menu.wait_for_selector("#screen-exercices", state="visible", timeout=5000)
    assert at_menu.locator("#screen-exercices").is_visible()


def test_retour_depuis_exercices(at_menu):
    """Exercices → retour menu propre."""
    if not at_menu.locator("#screen-exercices").is_visible():
        at_menu.locator("button", has_text="Exercices").click()
        at_menu.wait_for_selector("#screen-exercices", state="visible", timeout=5000)

    at_menu.locator("#screen-exercices button", has_text="Menu").first.click()
    at_menu.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    assert at_menu.locator("#screen-menu").is_visible()


# ── Navigation Retranscription ─────────────────────────────────────────────────

def test_retranscription_formulaire(at_menu):
    """Retranscrire → formulaire visible."""
    at_menu.locator("button", has_text="Retranscrire").click()
    at_menu.wait_for_selector("#screen-retranscription", state="visible", timeout=5000)
    assert at_menu.locator("#screen-retranscription").is_visible()
    go_menu(at_menu)


# ── Transitions critiques ──────────────────────────────────────────────────────

def test_transition_analyse_puis_menu(at_menu):
    """Analyse → Retour → Pédagogique config — pas de résidu."""
    # Analyse
    at_menu.locator("button", has_text="Analyse de partie").click()
    at_menu.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    at_menu.locator("#panel-gameover button", has_text="Retour au menu").click()
    at_menu.wait_for_selector("#screen-menu", state="visible", timeout=5000)

    # Pédagogique config → vérifier état propre
    at_menu.locator("button.menu-btn-primary").click()
    at_menu.wait_for_selector("#screen-config", state="visible", timeout=5000)
    assert at_menu.locator("#screen-config").is_visible()
    go_menu(at_menu)
