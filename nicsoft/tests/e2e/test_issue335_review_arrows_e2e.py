"""
Test e2e (issue #335) — écran d'analyse post-partie : flèches des 3
meilleures lignes moteur + coup réellement joué.

Même chemin que test_issue332_review_nav_stable_position_e2e.py /
test_review_nav_279_e2e.py pour atteindre l'écran de revue sans échiquier,
sans partie jouée et surtout SANS AUCUN MOTEUR : menu "Analyse" →
"Coller PGN". Le calcul moteur (ReviewMultiPVService, côté serveur) est
couvert séparément par des tests Python avec faux moteur
(test_issue335_review_multipv.py) — ici, on simule directement le résultat
déjà reçu en écrivant `_reviewLinesCache[fen]` côté client puis en
rappelant `renderReview()`, exactement comme #332 simule `best_move` sans
appeler le serveur d'analyse.
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


def _reset_arrows_state(page):
    """Remet l'état JS des flèches à son défaut (coché, cache vide) — la
    page Playwright est partagée (session-scoped) entre tous les tests."""
    page.evaluate(
        """() => {
            _reviewArrowsEnabled = true;
            document.getElementById('review-arrows-toggle').checked = true;
            _reviewLinesCache = {};
            _reviewLinesPending = {};
        }"""
    )


def _goto_review_idx(page, index):
    page.evaluate("(i) => { reviewIdx = i; renderReview(); }", index)


def _simuler_lignes(page, idx, coincide):
    """Injecte un résultat déjà calculé pour la position `idx` (3 lignes
    fictives) — coincide=True fait correspondre la 1ère ligne au coup
    réellement joué depuis cette position (reviewMoves[idx])."""
    return page.evaluate(
        """({idx, coincide}) => {
            reviewIdx = idx;
            const fen = reviewFens[idx];
            const playedUci = reviewMoves[idx] ? reviewMoves[idx].uci : null;
            const line1 = (coincide && playedUci) ? playedUci : "a2a3";
            _reviewLinesCache[fen] = {
                lines: [
                    { move: line1,  san: "L1", cp: 50, mate: null },
                    { move: "b2b3", san: "L2", cp: 10, mate: null },
                    { move: "c2c3", san: "L3", cp: -5, mate: null },
                ],
                error: null,
            };
            renderReview();
            return { fen, playedUci };
        }""",
        {"idx": idx, "coincide": coincide},
    )


def _arrow_svg_counts(page):
    return page.evaluate(
        """() => {
            const svg = document.getElementById('board-arrows');
            return {
                lines:   svg.querySelectorAll('line.review-arrow-line').length,
                circles: svg.querySelectorAll('circle:not(.board-arrow-badge-played)').length,
                rings:   svg.querySelectorAll('circle.board-arrow-badge-played').length,
                numbers: Array.from(svg.querySelectorAll('text.board-arrow-number')).map(n => n.textContent),
            };
        }"""
    )


def _retour_menu(page):
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def test_trois_flèches_plus_coup_joue_quand_different(at_menu):
    """Coup joué différent des 3 lignes → 4 flèches (3 moteur + 1 jouée),
    numérotées 1/2/3 puis un repère distinct ("•") pour le coup joué."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    assert n_coups >= 1
    _simuler_lignes(at_menu, 0, coincide=False)

    counts = _arrow_svg_counts(at_menu)
    assert counts["lines"] == 4, counts
    assert counts["circles"] == 4, counts
    assert counts["rings"] == 0, counts
    assert sorted(counts["numbers"]) == sorted(["1", "2", "3", "•"]), counts

    _retour_menu(at_menu)


def test_coup_joue_coincidant_avec_meilleure_ligne_pas_de_doublon(at_menu):
    """Coup joué == 1ère ligne moteur → une seule flèche pour ce rang (pas
    de flèche orange superposée), avec un contour de coïncidence autour du
    numéro "1"."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    _simuler_lignes(at_menu, 1, coincide=True)

    counts = _arrow_svg_counts(at_menu)
    assert counts["lines"] == 3, counts       # jamais 4 : pas de flèche jouée dupliquée
    assert counts["rings"] == 1, counts        # pastille de coïncidence
    assert sorted(counts["numbers"]) == sorted(["1", "2", "3"]), counts

    _retour_menu(at_menu)


def test_case_decochee_aucune_fleche_ni_liste(at_menu):
    """Case « Afficher les flèches » décochée → aucune flèche tracée,
    légende et liste masquées, comportement actuel conservé."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    _simuler_lignes(at_menu, 0, coincide=False)
    assert _arrow_svg_counts(at_menu)["lines"] == 4  # état de départ : flèches visibles

    at_menu.locator("#review-arrows-toggle").uncheck()

    counts = _arrow_svg_counts(at_menu)
    assert counts["lines"] == 0, counts
    assert counts["circles"] == 0, counts
    legend_visible = at_menu.evaluate(
        "() => document.getElementById('review-arrows-legend').style.display !== 'none'"
    )
    list_html = at_menu.evaluate("() => document.getElementById('review-arrows-list').innerHTML")
    assert not legend_visible
    assert list_html.strip() == ""

    at_menu.locator("#review-arrows-toggle").check()
    _retour_menu(at_menu)


def test_legende_et_liste_affichees_avec_notation_et_note(at_menu):
    """Légende (couleurs) et liste (SAN + note de chaque ligne, + coup joué)
    affichées — texte du coup joué lu via t() plutôt que codé en dur, la
    locale de la page de test n'étant pas garantie française."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    info = _simuler_lignes(at_menu, 0, coincide=False)
    assert info["playedUci"]
    coup_joue_label = at_menu.evaluate("() => t('game.legende.fleche_jouee')")

    legend_visible = at_menu.evaluate(
        "() => document.getElementById('review-arrows-legend').style.display !== 'none'"
    )
    assert legend_visible
    list_items = at_menu.locator("#review-arrows-list li")
    assert list_items.count() == 4  # 3 lignes + coup joué
    texts = [list_items.nth(i).inner_text() for i in range(list_items.count())]
    assert any("L1" in t and "+0.50" in t for t in texts)
    assert any("L2" in t and "+0.10" in t for t in texts)
    assert any("L3" in t and "-0.05" in t for t in texts)
    assert any(coup_joue_label in t for t in texts)

    _retour_menu(at_menu)


def test_orientation_retournee_change_les_coordonnees(at_menu):
    """L'échiquier retourné (noirs en bas) doit changer la position des
    flèches — vérifié via boardSquareCenter(), pas de dépendance à un vrai
    rendu pixel du board pour rester robuste en CI headless."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)

    center_normal = at_menu.evaluate("() => boardSquareCenter('e4', 400)")
    at_menu.locator("#btn-flip").click()
    center_flipped = at_menu.evaluate("() => boardSquareCenter('e4', 400)")
    at_menu.locator("#btn-flip").click()  # remet l'orientation par défaut

    assert center_normal != center_flipped

    _retour_menu(at_menu)


def test_fleches_disparaissent_en_quittant_lecran_analyse(at_menu):
    """Retour au menu (ou toute sortie de l'écran game_over) efface
    proprement les flèches — pas de résidu visible au prochain écran."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    _simuler_lignes(at_menu, 0, coincide=False)
    assert _arrow_svg_counts(at_menu)["lines"] == 4

    _retour_menu(at_menu)

    counts = _arrow_svg_counts(at_menu)
    assert counts["lines"] == 0, counts


def test_bouton_suivant_position_stable_avec_carte_fleches(at_menu):
    """Régression #332 : la nouvelle carte (case à cocher + légende +
    liste), insérée APRÈS la carte navigation dans le DOM, ne doit jamais
    déplacer #btn-review-next — qu'elle soit vide, pleine de 4 lignes, ou
    masquée (case décochée)."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)

    # Démarre à l'indice 1 (comme #332) : l'indice 0 ("position initiale",
    # sans coup san affiché) a déjà, sur l'écran existant et indépendamment
    # de toute flèche, une hauteur légèrement différente des indices
    # suivants — confirmé en reproduisant le même écart sur le code non
    # modifié par cette issue. Pas une régression de #335, hors périmètre.
    n_coups = at_menu.evaluate("() => reviewMoves.length")
    boxes = []
    for idx in range(1, n_coups + 1):
        coincide = idx % 2 == 0
        _simuler_lignes(at_menu, idx, coincide=coincide)
        boxes.append(at_menu.locator("#btn-review-next").bounding_box())

    at_menu.locator("#review-arrows-toggle").uncheck()
    boxes.append(at_menu.locator("#btn-review-next").bounding_box())
    at_menu.locator("#review-arrows-toggle").check()

    reference = boxes[0]
    for i, box in enumerate(boxes[1:], start=1):
        assert box == reference, (
            f"#btn-review-next a changé de position à l'étape {i} "
            f"(attendu {reference}, obtenu {box})"
        )

    _retour_menu(at_menu)
