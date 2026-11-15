"""
Test e2e (issue #339) — écran d'analyse post-partie (#335) : quand le coup
réellement joué coïncide avec une des 3 meilleures lignes moteur, toute la
flèche concernée (corps + pointe) doit recevoir un contour orange, pas
seulement le petit numéro.

Même chemin que test_issue335_review_arrows_e2e.py pour atteindre l'écran de
revue sans échiquier, sans partie jouée et SANS AUCUN MOTEUR : menu
"Analyse" → "Coller PGN", puis résultat moteur simulé directement en
écrivant `_reviewLinesCache[fen]` côté client avant de rappeler
`renderReview()`.
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


def _simuler_lignes(page, idx, coincide_rang=None):
    """Injecte un résultat déjà calculé (3 lignes fictives) pour la position
    `idx`. `coincide_rang` (1, 2 ou 3) fait correspondre la ligne de ce rang
    au coup réellement joué depuis cette position (reviewMoves[idx]) ;
    `None` = aucune coïncidence (coup joué différent des 3 lignes)."""
    return page.evaluate(
        """({idx, coincideRang}) => {
            reviewIdx = idx;
            const fen = reviewFens[idx];
            const playedUci = reviewMoves[idx] ? reviewMoves[idx].uci : null;
            const moves = ["a2a3", "b2b3", "c2c3"];
            if (coincideRang && playedUci) moves[coincideRang - 1] = playedUci;
            _reviewLinesCache[fen] = {
                lines: [
                    { move: moves[0], san: "L1", cp: 50, mate: null },
                    { move: moves[1], san: "L2", cp: 10, mate: null },
                    { move: moves[2], san: "L3", cp: -5, mate: null },
                ],
                error: null,
            };
            renderReview();
            return { fen, playedUci };
        }""",
        {"idx": idx, "coincideRang": coincide_rang},
    )


def _arrow_svg_info(page):
    """Compte les flèches, les halos de coïncidence (review-arrow-line-
    outline) et associe chaque halo à son numéro de rang via sa position
    (même milieu de segment que la flèche colorée du même rang)."""
    return page.evaluate(
        """() => {
            const svg = document.getElementById('board-arrows');
            const lines   = Array.from(svg.querySelectorAll('line.review-arrow-line'));
            const outlines = Array.from(svg.querySelectorAll('line.review-arrow-line-outline'));
            const numbers = Array.from(svg.querySelectorAll('text.board-arrow-number'));
            // Pour chaque halo, le rang de la flèche qu'il entoure = celui
            // dont le trait coloré partage les mêmes extrémités.
            const outlinedRanks = outlines.map(o => {
                const match = lines.find(l =>
                    l.getAttribute('x1') === o.getAttribute('x1') &&
                    l.getAttribute('y1') === o.getAttribute('y1') &&
                    l.getAttribute('x2') === o.getAttribute('x2') &&
                    l.getAttribute('y2') === o.getAttribute('y2')
                );
                if (!match) return null;
                // Le numéro le plus proche du milieu du trait correspondant.
                const mx = (parseFloat(match.getAttribute('x1')) + parseFloat(match.getAttribute('x2'))) / 2;
                const my = (parseFloat(match.getAttribute('y1')) + parseFloat(match.getAttribute('y2'))) / 2;
                let best = null, bestDist = Infinity;
                for (const n of numbers) {
                    const dx = parseFloat(n.getAttribute('x')) - mx;
                    const dy = parseFloat(n.getAttribute('y')) - my;
                    const dist = dx * dx + dy * dy;
                    if (dist < bestDist) { bestDist = dist; best = n.textContent; }
                }
                return best;
            });
            return {
                lineCount: lines.length,
                outlineCount: outlines.length,
                rings: svg.querySelectorAll('circle.board-arrow-badge-played').length,
                numbers: numbers.map(n => n.textContent),
                outlinedRanks,
            };
        }"""
    )


def _retour_menu(page):
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


@pytest.mark.parametrize("rang", [1, 2, 3])
def test_contour_sur_la_bonne_fleche_pour_chaque_rang(at_menu, rang):
    """Coup joué == ligne de rang `rang` → un seul halo de contour orange,
    et il entoure précisément la flèche numérotée `rang` (pas une autre)."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    _simuler_lignes(at_menu, 0, coincide_rang=rang)

    info = _arrow_svg_info(at_menu)
    assert info["lineCount"] == 3, info          # jamais de 4e flèche dupliquée
    assert info["outlineCount"] == 1, info        # un seul halo
    assert info["rings"] == 1, info                # contour du numéro conservé (#335)
    assert info["outlinedRanks"] == [str(rang)], info

    _retour_menu(at_menu)


def test_aucun_contour_sans_coincidence(at_menu):
    """Coup joué différent des 3 lignes moteur → aucun halo de contour,
    comportement #335 inchangé (4 flèches, dont une orange séparée)."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    _simuler_lignes(at_menu, 0, coincide_rang=None)

    info = _arrow_svg_info(at_menu)
    assert info["lineCount"] == 4, info
    assert info["outlineCount"] == 0, info
    assert info["rings"] == 0, info

    _retour_menu(at_menu)


def test_contour_avec_echiquier_retourne(at_menu):
    """L'échiquier retourné (noirs en bas) ne doit pas faire disparaître le
    halo : toujours présent, toujours associé à la flèche du bon rang."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)

    at_menu.locator("#btn-flip").click()
    _simuler_lignes(at_menu, 0, coincide_rang=2)

    info = _arrow_svg_info(at_menu)
    assert info["outlineCount"] == 1, info
    assert info["outlinedRanks"] == ["2"], info

    at_menu.locator("#btn-flip").click()  # remet l'orientation par défaut
    _retour_menu(at_menu)


def test_contour_fleche_courte_et_longue(at_menu):
    """Le halo doit s'afficher aussi bien pour une flèche courte (coup
    joué d'une case) que pour une flèche longue (traversée du plateau) —
    deux positions différentes de la même partie, chacune avec coïncidence."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    assert n_coups >= 2

    for idx in (0, 1):
        _simuler_lignes(at_menu, idx, coincide_rang=1)
        info = _arrow_svg_info(at_menu)
        assert info["outlineCount"] == 1, (idx, info)
        assert info["outlinedRanks"] == ["1"], (idx, info)

    _retour_menu(at_menu)


def test_legende_contour_affichee_dans_les_trois_langues(at_menu):
    """La légende mentionne le contour orange, dans les 3 langues actives
    (fr/en/de) — chargées via i18n.load() (comme le sélecteur de langue réel)
    puis lues dans le DOM de la légende elle-même."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    _simuler_lignes(at_menu, 0, coincide_rang=1)

    legend_visible = at_menu.evaluate(
        "() => document.getElementById('review-arrows-legend').style.display !== 'none'"
    )
    assert legend_visible

    locale_initiale = at_menu.evaluate("() => i18n.locale()")
    try:
        for locale in ("fr", "en", "de"):
            label = at_menu.evaluate(
                """async (l) => { await i18n.load(l); return t('game.legende.fleche_contour'); }""",
                locale,
            )
            assert label, locale
            legend_text = at_menu.locator("#review-arrows-legend").inner_text()
            assert label in legend_text, (locale, label, legend_text)
    finally:
        at_menu.evaluate("(l) => i18n.load(l)", locale_initiale)

    _retour_menu(at_menu)
