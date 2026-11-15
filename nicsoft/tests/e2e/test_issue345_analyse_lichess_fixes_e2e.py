"""
Test e2e (issue #345) — trois défauts constatés par Alain sur l'écran
d'analyse après une partie Lichess gagnée avec les Noirs (échiquier
retourné) :

1. Barre d'évaluation absente (écran de fin de partie ET écran « Révision
   PGN ») — cause : `_reviewUpdateEvalBar()` masquait inconditionnellement
   la barre dès que `_gameSource === "lichess"` (introduit par #341), une
   garde pensée pour la règle de fair-play Lichess (#333, "jamais de moteur
   PENDANT une partie en ligne") mais appliquée à tort sur l'écran
   d'analyse, qui n'est de toute façon atteint qu'une fois la partie
   terminée. Voir aussi test_issue341_review_eval_bar_e2e.py::
   test_presente_apres_partie_lichess_terminee (même cause, chemin "Coller
   PGN" direct).

2. Analyse complète jamais lancée après une partie Lichess terminée —
   cause : `socket.on("app_state")` passait `data.source === "lichess"`
   comme `skip` à `_reviewMaybeAutoAnalyse()`, qui désactivait l'analyse
   automatique introduite par #342 même une fois la partie terminée (la
   garde n'aurait dû s'appliquer qu'à une partie Lichess EN COURS, jamais
   atteinte sur cet écran). Voir aussi test_issue342_auto_analyse_e2e.py::
   test_demarre_juste_apres_fin_de_partie_lichess.

3. Noms de joueurs qui ne suivent pas l'orientation retournée de
   l'échiquier après un chargement de PGN (parsePgn()) — cause :
   affectation inconditionnelle `top=Noir / bottom=Blanc`, sans tenir
   compte de `_boardFlipped`. Les pièces capturées (`updateMaterial()`),
   elles, suivaient déjà correctement l'orientation (régression absente
   sur ce point) — seul le nom affiché était en cause.

Même chemin que test_issue341_review_eval_bar_e2e.py / test_issue342_
auto_analyse_e2e.py pour atteindre l'écran de revue sans échiquier et SANS
AUCUN MOTEUR réel (serveur de test lancé avec ALCHESS_SKIP_AUTO_ANALYSE=1,
voir nicsoft/tests/e2e/conftest.py) : menu "Analyse" → "Coller PGN", ou
simulation directe de l'événement "app_state" pour le chemin "partie
Lichess qui vient de se terminer" (même procédé que #342,
`socket.listeners(event).forEach(h => h(data))`).
"""
import pytest

pytestmark = pytest.mark.slow

# Alain joue les Noirs, gagne 0-1 — reproduit l'observation de l'issue
# ("tomatoloss vs Vous", 0-1).
_PGN_NOIRS = (
    '[White "tomatoloss"]\n[Black "Vous"]\n[Result "0-1"]\n\n'
    "1. e4 e5 2. Qh5 Ke7 0-1"
)


def _charger_pgn_colle(page, pgn):
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def _reset_state(page):
    """Remet l'état JS flèches/barre/orientation à son défaut — la page
    Playwright est partagée (session-scoped) entre tous les tests."""
    page.evaluate(
        """() => {
            _reviewArrowsEnabled = true;
            document.getElementById('review-arrows-toggle').checked = true;
            _reviewLinesCache = {};
            _reviewLinesPending = {};
            _gameSource = 'niclink';
            if (_boardFlipped) { flipBoard(); }
        }"""
    )


def _retour_menu(page):
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _bar_display(page):
    return page.evaluate(
        "() => document.getElementById('review-eval-bar').style.display"
    )


def _top_bottom_names(page):
    return page.evaluate(
        """() => ({
            top: document.getElementById('player-top-name').textContent,
            bottom: document.getElementById('player-bottom-name').textContent,
        })"""
    )


def _top_bottom_material_html(page):
    return page.evaluate(
        """() => ({
            top: document.getElementById('material-top').innerHTML,
            bottom: document.getElementById('material-bottom').innerHTML,
        })"""
    )


def _flip(page):
    page.locator("button[data-action=\"flip_board\"]").click()


# ── Point 1 : barre d'évaluation toujours présente sur « Révision PGN » ────
# (même après chargement direct d'un PGN marqué de source Lichess dans
# l'historique client — reproduit le second constat d'Alain : la barre
# reste absente même quand l'analyse, elle, fonctionne).

def test_barre_presente_apres_chargement_pgn_noirs_echiquier_retourne(at_menu):
    _charger_pgn_colle(at_menu, _PGN_NOIRS)
    _reset_state(at_menu)
    # Simule le cas réel observé : la source est restée "lichess" depuis la
    # partie précédente (voir docstring du fichier, cause n°1) — la barre
    # doit malgré tout être présente.
    at_menu.evaluate("() => { _gameSource = 'lichess'; renderReview(); }")
    assert _bar_display(at_menu) != "none"

    _flip(at_menu)
    assert _bar_display(at_menu) != "none"

    at_menu.evaluate("() => { _gameSource = 'niclink'; }")
    _retour_menu(at_menu)


# ── Point 2 : analyse automatique lancée après une vraie fin de partie
# Lichess (chemin socket.on("app_state"), pas "Coller PGN") ────────────────

def test_analyse_demarre_apres_vraie_fin_de_partie_lichess(at_menu):
    at_menu.evaluate("() => { _gameMode = 'lichess'; }")
    at_menu.evaluate(
        """(data) => { socket.listeners('app_state').forEach(h => h(data)); }""",
        {
            "state": "game_over", "source": "lichess", "result": "0-1",
            "history_fen": [
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
            ],
            "history_moves": [
                {"san": "e4", "uci": "e2e4", "color": "white", "qualite": None},
                {"san": "e5", "uci": "e7e5", "color": "black", "qualite": None},
            ],
        },
    )
    try:
        assert at_menu.evaluate("() => _analyseActive") is True
        # La barre d'évaluation doit elle aussi être présente sur cet écran
        # (point 1, chemin "vraie fin de partie" cette fois).
        assert _bar_display(at_menu) != "none"
    finally:
        at_menu.evaluate("() => { _gameMode = ''; }")
        _retour_menu(at_menu)


# ── Point 3 : noms des joueurs suivant l'orientation après chargement PGN ──

def test_noms_suivent_orientation_apres_chargement_pgn(at_menu):
    """Reproduit l'observation d'Alain : PGN "tomatoloss vs Vous" (Alain
    Noir, victoire des Noirs), échiquier resté retourné (Noirs en bas)
    depuis la partie Lichess précédente — "Vous" (Noir) doit être en bas,
    "tomatoloss" (Blanc) en haut. Avant #345, parsePgn() affectait
    toujours top=Noir/bottom=Blanc sans regarder _boardFlipped."""
    # Échiquier non flippé d'abord, pour vérifier aussi le cas par défaut
    # (déjà chargé par _charger_pgn_colle, orientation par défaut).
    _charger_pgn_colle(at_menu, _PGN_NOIRS)
    _reset_state(at_menu)
    at_menu.evaluate("(pgn) => parsePgn(pgn)", _PGN_NOIRS)
    noms_non_flip = _top_bottom_names(at_menu)
    assert noms_non_flip == {"top": "Vous", "bottom": "tomatoloss"}

    # Puis retourné (Noirs en bas) — recharger le même PGN doit afficher
    # "tomatoloss" en haut et "Vous" en bas.
    _flip(at_menu)
    at_menu.evaluate("(pgn) => parsePgn(pgn)", _PGN_NOIRS)
    noms_flip = _top_bottom_names(at_menu)
    assert noms_flip == {"top": "tomatoloss", "bottom": "Vous"}

    _reset_state(at_menu)
    _retour_menu(at_menu)


# ── Pièces capturées : déjà correctes avant #345, non-régression ──────────

def test_pieces_capturees_suivent_deja_lorientation(at_menu):
    """updateMaterial() (appelée par renderBoard()/renderReview() à chaque
    affichage) recalculait déjà top/bottom depuis `_boardFlipped` avant
    #345 — ce test garde la preuve que ce point n'a jamais régressé et ne
    casse pas avec le correctif des noms."""
    # Partie avec une capture dès le premier coup pour un contenu non vide
    # des deux côtés (Blancs perdent un pion : bxc6 capture le cavalier).
    pgn_capture = (
        '[White "tomatoloss"]\n[Black "Vous"]\n[Result "0-1"]\n\n'
        "1. e4 e5 2. Nf3 Nc6 3. Nxe5 Nxe5 0-1"
    )
    _charger_pgn_colle(at_menu, pgn_capture)
    _reset_state(at_menu)
    mat_non_flip = _top_bottom_material_html(at_menu)

    _flip(at_menu)
    mat_flip = _top_bottom_material_html(at_menu)

    # Le flip échange bien le contenu matériel affiché de chaque côté.
    assert mat_flip == {"top": mat_non_flip["bottom"], "bottom": mat_non_flip["top"]}

    _reset_state(at_menu)
    _retour_menu(at_menu)
