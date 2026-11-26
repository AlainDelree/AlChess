"""
nicsoft/tests/e2e/test_issue364_puzzle_virtuel_fin_e2e.py — AlChess

Issue #364, partie 3 : fin de problème et "Voir la solution" en mode
virtuel — le bandeau de fin et "Voir la solution" eux-mêmes sont du code
PARTAGÉ avec le mode échiquier (déjà couvert par
test_issue363_puzzle_fin_e2e.py, inchangé) ; ce fichier vérifie ce qui est
SPÉCIFIQUE au mode virtuel : le rejeu de la solution met bien à jour
l'échiquier cliquable, "Problème suivant" relance dans le MÊME mode
(virtual) avec un échiquier de nouveau actif, et "Retour au menu" reste
disponible et fonctionnel pendant l'affichage de la solution. Sans
échiquier ni Lichess réels — évènements socket simulés, même procédé que
test_issue364_puzzle_virtuel_e2e.py."""
import pytest

pytestmark = pytest.mark.slow

FEN_DEPART = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


@pytest.fixture
def at_puzzle_virtuel_rate(at_menu):
    """Problème virtuel déjà raté (sans passer par les clics — couvert par
    test_issue364_puzzle_virtuel_e2e.py), prêt pour "Voir la solution"."""
    page = at_menu
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "lichess_puzzle_playing", "virtual": True,
        "fen": FEN_DEPART, "color": "white", "puzzle_id": "pzl1", "rating": 1500,
    })
    page.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": False, "themes": [], "rating": 1500,
        "rating_before": 1500, "rating_after": 1496, "rating_diff": -4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": True,
    })
    page.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    return page


def test_voir_la_solution_met_a_jour_l_echiquier_virtuel(at_puzzle_virtuel_rate):
    page = at_puzzle_virtuel_rate
    # Rejeu : coup par coup, sans jamais attendre de réplication physique
    # (côté serveur, VirtualPuzzleGame._wait_for_board_fen est une simple
    # pause — voir test_issue364_lichess_puzzle_virtuel.py pour ce point,
    # hors de portée du navigateur). Ici, seul le rendu de l'échiquier
    # (#board-lichess-puzzle, partagé avec le mode échiquier) est vérifié.
    _declencher_evenement_socket_client(page, "lichess_puzzle_solution_move", {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR", "san": "e4",
        "uci": "e2e4", "color": "white", "done": True,
    })
    assert page.locator("#lp-4-3").evaluate("el => el.classList.contains('last-move-to')")
    assert page.locator("#lichess-puzzle-solution-banner").is_visible()

    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": False, "themes": [], "rating": 1500,
        "rating_before": 1500, "rating_after": 1496, "rating_diff": -4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": False,
    })
    assert not page.locator("#lichess-puzzle-btn-solution").is_visible()


def test_retour_aux_reglages_disponible_pendant_la_solution(at_puzzle_virtuel_rate):
    """Issue #389 : ce bouton ramène désormais aux réglages des problèmes
    (config_lichess), jamais au menu principal — toujours disponible et
    fonctionnel pendant l'affichage de la solution, comme avant."""
    page = at_puzzle_virtuel_rate
    _declencher_evenement_socket_client(page, "lichess_puzzle_solution_move", {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR", "san": "e4",
        "uci": "e2e4", "color": "white", "done": False,
    })
    back_btn = page.locator("#screen-lichess-puzzle [data-action='back_config_lichess']")
    assert back_btn.is_visible()
    back_btn.click()
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    page.evaluate("sendAction({type: 'back_menu'})")
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def test_probleme_suivant_relance_en_mode_virtuel_avec_echiquier_actif(at_puzzle_virtuel_rate):
    """"Problème suivant" relance dans le MÊME mode que le précédent (issue
    #364) : le serveur renvoie un nouvel app_state avec virtual=True, et le
    nouvel échiquier doit redevenir cliquable (nouveau "your_turn")."""
    page = at_puzzle_virtuel_rate
    page.locator("[data-action='lichess_puzzle_next']").click()

    _declencher_evenement_socket_client(page, "app_state", {
        "state": "lichess_puzzle_playing", "virtual": True,
        "fen": FEN_DEPART, "color": "white", "puzzle_id": "pzl2", "rating": 1496,
    })
    page.wait_for_selector("#lichess-puzzle-result", state="hidden", timeout=5000)
    assert page.locator("#lichess-puzzle-virtual-instructions").is_visible()

    page.evaluate("() => { window._cap=[]; window._orig=window.sendAction; window.sendAction=(a)=>{window._cap.push(a); window._orig(a);} }")
    _declencher_evenement_socket_client(page, "lichess_puzzle_your_turn", {
        "legal_moves": {"e2": ["e3", "e4"]},
    })
    page.locator("#lp-4-1").click()
    page.locator("#lp-4-3").click()
    assert page.evaluate("() => window._cap") == [
        {"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4", "promotion": ""}
    ]
