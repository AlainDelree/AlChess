"""
nicsoft/tests/e2e/test_issue361_puzzle_mise_en_place_e2e.py — AlChess

Issue #361, partie 0 : pendant la mise en place d'un problème Lichess, les
cases rouges de l'écran "#screen-pos-init" doivent se mettre à jour au fil
du placement physique des pièces — avant ce correctif,
_wait_initial_position_lichess_puzzle envoyait toujours la position CIBLE
(figée) comme "fen", jamais la lecture physique courante : l'écran restait
figé avec toutes les cases rouges du départ (voir rapport de clôture).

Même procédé que test_issue310_lichess_e2e.py : aucune vraie partie/problème
Lichess ni échiquier réel — l'événement socket "app_state" normalement
envoyé par le serveur (set_app_state) est simulé en invoquant directement
les callbacks déjà enregistrés par `socket.on(...)` dans app.js.
"""
import pytest

pytestmark = pytest.mark.slow

# Position cible ARBITRAIRE du problème simulé (après 1.e4) — volontairement
# différente de la position de départ standard, pour vérifier que la
# comparaison utilise bien "expected_fen" et non la valeur par défaut
# (standard) de renderBoardPosInit.
TARGET_BOARD_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _nb_cases_rouges(page):
    return page.locator("#board-pos-init .pos-init-error").count()


@pytest.fixture
def at_puzzle_mise_en_place(at_menu):
    """Écran de mise en place d'un problème Lichess, avec deux pièces
    encore mal placées (e2 et e4) par rapport à la cible du problème."""
    physical_fen_incomplete = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    _declencher_evenement_socket_client(at_menu, "app_state", {
        "state": "position_initiale", "fen": physical_fen_incomplete,
        "expected_fen": TARGET_BOARD_FEN, "color": "white", "puzzle": True,
    })
    at_menu.wait_for_selector("#screen-pos-init", state="visible", timeout=5000)
    return at_menu


def test_puzzle_mise_en_place_affiche_des_cases_rouges(at_puzzle_mise_en_place):
    """Deux cases diffèrent de la cible (e2 et e4) : les deux doivent être
    signalées en rouge."""
    assert _nb_cases_rouges(at_puzzle_mise_en_place) == 2


def test_puzzle_mise_en_place_cases_rouges_disparaissent_au_placement(at_puzzle_mise_en_place):
    """Reproduction directe du bug #361 : au fur et à mesure que la
    lecture physique se rapproche de la cible, les cases rouges
    disparaissent — avant le correctif, le "fen" envoyé restait toujours
    celui de la cible (figé), donc l'affichage ne changeait jamais."""
    avant = _nb_cases_rouges(at_puzzle_mise_en_place)
    assert avant == 2

    # Le pion e2-e4 est désormais placé correctement (pièce physiquement
    # déplacée) ; le cavalier g1 reste absent de l'échiquier physique — un
    # seul écart restant, contre deux avant ce coup.
    physical_fen_une_piece = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKB1R"
    _declencher_evenement_socket_client(at_puzzle_mise_en_place, "app_state", {
        "state": "position_initiale", "fen": physical_fen_une_piece,
        "expected_fen": TARGET_BOARD_FEN, "color": "white", "puzzle": True,
    })
    apres = _nb_cases_rouges(at_puzzle_mise_en_place)
    assert apres < avant

    # Position physique désormais strictement identique à la cible.
    _declencher_evenement_socket_client(at_puzzle_mise_en_place, "app_state", {
        "state": "position_initiale", "fen": TARGET_BOARD_FEN,
        "expected_fen": TARGET_BOARD_FEN, "color": "white", "puzzle": True,
    })
    assert _nb_cases_rouges(at_puzzle_mise_en_place) == 0
