"""
Test e2e (issue #279) — les contrôles de navigation de l'écran d'analyse
(Précédent / Suivant) réagissent réellement au clic après une fin de partie.

Avant correction : `_setNavControls(true)` ne faisait qu'effacer le style
en ligne `pointer-events` (`el.style.pointerEvents = ""`), ce qui ne
produisait plus aucun effet depuis que `.game-gameover-nav-btn` impose
`pointer-events: none` en CSS (régression des extractions de styles
#230-#248). Les boutons paraissaient actifs (opacité à 1) mais restaient
insensibles à la souris, sans aucune erreur en console — uniquement visible
en test manuel ou via un vrai moteur de rendu (Playwright), jamais par une
lecture du DOM seule.

Chemin utilisé pour atteindre l'écran de revue sans échiquier ni partie
jouée : le menu "Analyse" (déjà utilisé par `test_smoke_e2e.py` comme proxy
de l'état `game_over`) puis "Coller PGN", qui charge une partie minimale
directement côté client (`parsePgn`, dans app.js) — aucun appel socket,
aucune écriture sur disque, donc jamais dans le vrai dossier de données de
l'utilisateur.
"""
import pytest

pytestmark = pytest.mark.slow

_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"


def _charger_pgn_colle(page, pgn):
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def test_boutons_navigation_analyse_actives_et_cliquables(at_menu):
    """Après chargement d'une partie en revue : boutons non-disabled et
    pointer-events autorisés (pas juste l'opacité)."""
    _charger_pgn_colle(at_menu, _PGN)

    prev_btn = at_menu.locator("#btn-review-prev")
    next_btn = at_menu.locator("#btn-review-next")
    assert not prev_btn.is_disabled()
    assert not next_btn.is_disabled()

    pointer_events = at_menu.evaluate(
        "() => getComputedStyle(document.getElementById('btn-review-prev')).pointerEvents"
    )
    assert pointer_events != "none", (
        "pointer-events doit être autorisé (pas 'none') — sinon le bouton "
        "paraît actif mais n'est pas cliquable (régression #230-#248, voir #279)"
    )

    # Retour au menu propre pour ne pas laisser l'état "chargé" aux autres tests.
    at_menu.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    at_menu.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def test_clic_precedent_et_suivant_changent_le_coup_affiche(at_menu):
    """Le clic sur Précédent/Suivant fait réellement réagir l'écran — pas
    seulement un attribut `disabled` levé sans effet (pointer-events bloqués)."""
    _charger_pgn_colle(at_menu, _PGN)

    san_initial = at_menu.locator("#review-move-san").inner_text()
    assert san_initial  # dernier coup chargé (a6)

    at_menu.locator("#btn-review-prev").click()
    at_menu.wait_for_function(
        """(prev) => document.getElementById("review-move-san").innerText !== prev""",
        arg=san_initial,
        timeout=3000,
    )
    san_apres_prev = at_menu.locator("#review-move-san").inner_text()
    assert san_apres_prev != san_initial

    at_menu.locator("#btn-review-next").click()
    at_menu.wait_for_function(
        """(prev) => document.getElementById("review-move-san").innerText !== prev""",
        arg=san_apres_prev,
        timeout=3000,
    )
    san_apres_next = at_menu.locator("#review-move-san").inner_text()
    assert san_apres_next == san_initial

    at_menu.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    at_menu.wait_for_selector("#screen-menu", state="visible", timeout=5000)
