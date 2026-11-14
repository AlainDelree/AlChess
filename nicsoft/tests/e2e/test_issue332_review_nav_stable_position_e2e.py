"""
Test e2e (issue #332) — sur l'écran d'analyse après partie, les boutons de
navigation (Précédent / Suivant) ne doivent JAMAIS se déplacer quand le
bouton « Voir le meilleur coup » apparaît ou disparaît d'un coup à l'autre.

Avant correction : `_updateReviewBestMoveBtn()` (app.js) faisait
`row.style.display = hasBest ? "block" : "none"` sur `#review-best-move-row`
— ce bloc étant positionné juste au-dessus de la ligne Précédent/Suivant
dans le même flux de mise en page, le retirer/remettre changeait la hauteur
du panneau et poussait les boutons de navigation vers le haut ou le bas.
Correction : la ligne reste toujours affichée (place réservée), seul
l'état actif/grisé du bouton change.

Chemin pour atteindre l'écran de revue sans échiquier ni partie jouée, ni
moteur : menu "Analyse" → "Coller PGN" (déjà utilisé par
test_review_nav_279_e2e.py), identique à ce test. Comme aucun vrai moteur
ne doit tourner dans les tests, la présence/absence de « meilleur coup »
est simulée directement côté client (écriture de `reviewMoves[i].best_move`
et `_isAnalysed` en JS via `page.evaluate`, puis `renderReview()`) — sans
aucun appel socket ni serveur d'analyse.
"""
import pytest

pytestmark = pytest.mark.slow

_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7"


def _charger_pgn_colle(page, pgn):
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def _simuler_analyse_alternee(page):
    """Marque la partie comme analysée et alterne, coup par coup, la
    présence d'un meilleur coup différent du coup joué — exactement le
    scénario décrit dans l'issue (le bouton apparaît/disparaît d'un coup à
    l'autre). Aucun moteur n'est appelé : simple écriture des variables JS
    déjà peuplées par parsePgn()."""
    page.evaluate(
        """() => {
            _isAnalysed = true;
            for (let i = 0; i < reviewMoves.length; i++) {
                if (i % 2 === 0) {
                    reviewMoves[i].best_move = "a2a3";  // forcément != uci joué
                } else {
                    delete reviewMoves[i].best_move;
                }
            }
            renderReview();
        }"""
    )


def _goto_review_idx(page, index):
    page.evaluate("(i) => { reviewIdx = i; renderReview(); }", index)


def _box(page, selector):
    box = page.locator(selector).bounding_box()
    assert box is not None, f"{selector} introuvable ou invisible"
    return box


def _retour_menu(page):
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def test_bouton_suivant_position_stable_avec_et_sans_meilleur_coup(at_menu):
    """Position (top/left/width/height) de #btn-review-next strictement
    identique sur plusieurs coups consécutifs, que #review-best-move-row
    affiche un bouton actif ou grisé."""
    _charger_pgn_colle(at_menu, _PGN)
    _simuler_analyse_alternee(at_menu)

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    assert n_coups >= 4

    boxes = []
    for idx in range(1, n_coups + 1):
        _goto_review_idx(at_menu, idx)
        has_best = at_menu.evaluate(
            "() => !document.getElementById('btn-review-best').disabled"
        )
        # Vérifie que le scénario alterne bien actif/grisé (sinon le test
        # ne couvrirait pas le cas qui causait le déplacement).
        assert has_best == (idx % 2 == 1), (
            f"coup {idx}: état du bouton meilleur coup inattendu "
            f"(actif={has_best}) — la simulation ne reproduit pas le "
            f"scénario d'alternance de l'issue"
        )
        boxes.append(_box(at_menu, "#btn-review-next"))

    reference = boxes[0]
    for idx, box in enumerate(boxes[1:], start=2):
        assert box == reference, (
            f"#btn-review-next a changé de position au coup {idx} "
            f"(attendu {reference}, obtenu {box}) — la navigation ne doit "
            f"jamais se déplacer selon l'état du bouton « meilleur coup »"
        )

    _retour_menu(at_menu)


def test_bouton_suivant_position_stable_echiquier_retourne(at_menu):
    """Même vérification après avoir retourné l'échiquier (orientation
    noirs en bas) — le retournement ne doit pas non plus déplacer la nav."""
    _charger_pgn_colle(at_menu, _PGN)
    _simuler_analyse_alternee(at_menu)
    at_menu.locator("#btn-flip").click()

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    boxes = []
    for idx in range(1, n_coups + 1):
        _goto_review_idx(at_menu, idx)
        boxes.append(_box(at_menu, "#btn-review-next"))

    reference = boxes[0]
    for idx, box in enumerate(boxes[1:], start=2):
        assert box == reference, (
            f"#btn-review-next a changé de position au coup {idx} "
            f"(échiquier retourné) — attendu {reference}, obtenu {box}"
        )

    # Remettre l'orientation par défaut pour les autres tests de la session.
    at_menu.locator("#btn-flip").click()
    _retour_menu(at_menu)


def test_bouton_suivant_position_stable_petite_fenetre(at_menu):
    """Même vérification sur une taille de fenêtre plus petite (portable
    bas de gamme / fenêtre réduite) — pas seulement la taille courante."""
    at_menu.set_viewport_size({"width": 1024, "height": 700})
    try:
        _charger_pgn_colle(at_menu, _PGN)
        _simuler_analyse_alternee(at_menu)

        n_coups = at_menu.evaluate("() => reviewMoves.length")
        boxes = []
        for idx in range(1, n_coups + 1):
            _goto_review_idx(at_menu, idx)
            boxes.append(_box(at_menu, "#btn-review-next"))

        reference = boxes[0]
        for idx, box in enumerate(boxes[1:], start=2):
            assert box == reference, (
                f"#btn-review-next a changé de position au coup {idx} "
                f"(petite fenêtre 1024x700) — attendu {reference}, "
                f"obtenu {box}"
            )

        _retour_menu(at_menu)
    finally:
        at_menu.set_viewport_size({"width": 1400, "height": 900})
