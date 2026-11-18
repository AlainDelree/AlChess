"""
nicsoft/tests/e2e/test_issue361_puzzle_board_e2e.py — AlChess

Issue #361, partie 1 : l'échiquier de l'écran "Problème Lichess"
(#board-lichess-puzzle) disparaissait dès le démarrage du problème (règle
CSS de dimensionnement absente — #board-lichess-puzzle manquait de la
liste de sélecteurs `#board, #rv-board, #board-pos-init, ...` de
main.css), jusqu'à l'écran de fin inclus (même écran, voir index.html).
Ce test parcourt mise en place → démarrage du problème → coup adverse
affiché → fin, et vérifie la présence RÉELLE de l'échiquier (dimensions
non nulles, pas seulement présence dans le DOM) à chaque étape — sans
échiquier réel ni Lichess réel : tous les évènements socket que le serveur
envoie normalement sont simulés (même procédé que test_issue310_lichess_
e2e.py).
"""
import pytest

pytestmark = pytest.mark.slow

FEN_APRES_PREMIER_COUP = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _board_visible_et_dimensionne(page, selector):
    """True si l'échiquier existe, est visible, et a une mise en page
    d'échiquier normale (carré, taille raisonnable) — pas seulement des
    dimensions non nulles. Sans la règle CSS de dimensionnement
    (`display:grid` + `width`/`height: var(--bd-size)`), l'élément reste
    bien présent et "visible" au sens Playwright, mais ses 64 cases
    s'empilent verticalement sans grille (300×19200 mesuré en pratique
    pour #board-lichess-puzzle avant ce correctif) — un simple test
    largeur>0 et hauteur>0 ne l'aurait pas détecté."""
    loc = page.locator(selector)
    if not loc.is_visible():
        return False
    box = loc.bounding_box()
    if box is None or box["width"] < 100 or box["height"] < 100:
        return False
    return abs(box["width"] - box["height"]) < 50


@pytest.fixture
def at_puzzle_flow(at_menu):
    return at_menu


def test_puzzle_mise_en_place_echiquier_visible(at_puzzle_flow):
    """Étape mise en place (#screen-pos-init, #board-pos-init) : toujours
    fonctionnait avant ce correctif — sert de point de comparaison."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "position_initiale",
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
        "expected_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR",
        "color": "white", "puzzle": True,
    })
    at_puzzle_flow.wait_for_selector("#screen-pos-init", state="visible", timeout=5000)
    assert _board_visible_et_dimensionne(at_puzzle_flow, "#board-pos-init")


def test_puzzle_demarrage_echiquier_visible(at_puzzle_flow):
    """Reproduction directe du bug #361 : dès le démarrage du problème
    (state=lichess_puzzle_playing), l'échiquier doit rester visible et
    dimensionné — avant le correctif CSS, il disparaissait complètement."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": FEN_APRES_PREMIER_COUP, "color": "white",
        "puzzle_id": "pzl1", "rating": 1500,
    })
    at_puzzle_flow.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    assert _board_visible_et_dimensionne(at_puzzle_flow, "#board-lichess-puzzle")


def test_puzzle_coup_adverse_affiche_et_echiquier_toujours_visible(at_puzzle_flow):
    """Le coup adverse à reproduire est marqué (surbrillance départ/arrivée,
    même mécanisme que #board) et l'échiquier reste visible pendant
    l'attente de sa réplication physique."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": FEN_APRES_PREMIER_COUP, "color": "white",
        "puzzle_id": "pzl1", "rating": 1500,
    })
    at_puzzle_flow.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    _declencher_evenement_socket_client(at_puzzle_flow, "lichess_puzzle_move", {
        "fen": FEN_APRES_PREMIER_COUP, "uci": "e2e4", "color": "black",
    })
    assert at_puzzle_flow.locator("#lp-4-1").evaluate("el => el.classList.contains('last-move-from')")
    assert at_puzzle_flow.locator("#lp-4-3").evaluate("el => el.classList.contains('last-move-to')")
    assert _board_visible_et_dimensionne(at_puzzle_flow, "#board-lichess-puzzle")


def test_puzzle_ecran_de_fin_echiquier_toujours_visible(at_puzzle_flow):
    """L'écran de fin (résolu/raté) est le MÊME écran que la partie en
    cours (#lichess-puzzle-result affiché par-dessus, voir index.html) :
    l'échiquier doit donc rester visible jusque là aussi."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": FEN_APRES_PREMIER_COUP, "color": "white",
        "puzzle_id": "pzl1", "rating": 1500,
    })
    at_puzzle_flow.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    _declencher_evenement_socket_client(at_puzzle_flow, "lichess_puzzle_result", {
        "win": True, "themes": ["fork"], "rating": 1500,
        "rating_before": 1500, "rating_after": 1504, "rating_diff": 4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": False,
    })
    at_puzzle_flow.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    assert _board_visible_et_dimensionne(at_puzzle_flow, "#board-lichess-puzzle")
