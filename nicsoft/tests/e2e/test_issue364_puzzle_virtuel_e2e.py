"""
nicsoft/tests/e2e/test_issue364_puzzle_virtuel_e2e.py — AlChess

Issue #364, partie 2 : interaction à l'écran du mode virtuel des problèmes
Lichess (clic en deux temps, promotion, marquage des coups) — sans
échiquier ni Lichess réels, mêmes évènements socket simulés que
test_issue363_puzzle_fin_e2e.py / test_issue361_puzzle_*_e2e.py. Le serveur
lui-même n'est jamais exercé ici (couvert par
test_issue364_lichess_puzzle_virtuel.py, en process) : seul le
JavaScript (sélection, surbrillance, dialogue de promotion, action envoyée)
est vérifié, via une capture de `sendAction` posée avant chaque clic."""
import pytest

pytestmark = pytest.mark.slow

FEN_DEPART = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FEN_PROMOTION = "8/P7/8/8/8/8/k6K/8 w - - 0 1"


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _capturer_actions(page):
    """Enregistre chaque appel à sendAction() dans window._actionsCapturees,
    SANS perdre le comportement réel (socket.emit) — la page Playwright est
    partagée par toute la session (voir conftest.py::page) : un remplacement
    sec de sendAction() casserait "back_menu" pour les tests suivants (la
    fixture at_menu l'utilise elle-même pour revenir au menu)."""
    page.evaluate(
        "() => { "
        "window._actionsCapturees = []; "
        "if (!window._sendActionOriginal) window._sendActionOriginal = window.sendAction; "
        "window.sendAction = (a) => { window._actionsCapturees.push(a); window._sendActionOriginal(a); }; "
        "}"
    )


def _dernieres_actions(page):
    return page.evaluate("() => window._actionsCapturees")


def _click_case(page, file_, rank):
    page.locator(f"#lp-{file_}-{rank}").click()


@pytest.fixture
def at_puzzle_virtuel(at_menu):
    _declencher_evenement_socket_client(at_menu, "app_state", {
        "state": "lichess_puzzle_playing", "virtual": True,
        "fen": FEN_DEPART, "color": "white", "puzzle_id": "pzl1", "rating": 1500,
    })
    at_menu.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    _capturer_actions(at_menu)
    return at_menu


def test_instructions_virtuelles_affichees_sans_invitation_physique(at_puzzle_virtuel):
    page = at_puzzle_virtuel
    assert page.locator("#lichess-puzzle-virtual-instructions").is_visible()
    assert not page.locator("#lichess-puzzle-wait-replication").is_visible()


def test_coup_joue_a_la_souris_jusqu_a_probleme_resolu(at_puzzle_virtuel):
    page = at_puzzle_virtuel
    _declencher_evenement_socket_client(page, "lichess_puzzle_your_turn", {
        "legal_moves": {"e2": ["e3", "e4"]},
    })
    # 1er clic : sélectionne le pion e2 — case d'arrivée signalée.
    _click_case(page, 4, 1)  # e2 → coord interne "4-1"
    assert page.locator("#lp-4-1").evaluate("el => el.classList.contains('virt-selected')")
    assert page.locator("#lp-4-3").evaluate("el => el.classList.contains('virt-legal')")  # e4

    # 2e clic : case d'arrivée légale — envoie le coup, désactive l'échiquier.
    _click_case(page, 4, 3)
    actions = _dernieres_actions(page)
    assert actions == [{"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4", "promotion": ""}]
    assert not page.locator("#lp-4-1").evaluate("el => el.classList.contains('virt-selected')")

    # Le serveur confirme le coup puis le résultat (problème résolu dès ce coup).
    fen_apres = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    _declencher_evenement_socket_client(page, "lichess_puzzle_move", {
        "fen": fen_apres, "uci": "e2e4", "san": "e4", "color": "white",
    })
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": True, "themes": ["fork"], "rating": 1500,
        "rating_before": 1500, "rating_after": 1504, "rating_diff": 4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": False,
    })
    page.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    assert page.locator("[data-action='lichess_puzzle_next']").is_visible()


def test_coup_joue_a_la_souris_probleme_rate(at_puzzle_virtuel):
    page = at_puzzle_virtuel
    _declencher_evenement_socket_client(page, "lichess_puzzle_your_turn", {
        "legal_moves": {"d2": ["d3", "d4"]},
    })
    _click_case(page, 3, 1)  # d2
    _click_case(page, 3, 3)  # d4 — légal mais pas la solution
    actions = _dernieres_actions(page)
    assert actions == [{"type": "lichess_puzzle_virtual_move", "from": "d2", "to": "d4", "promotion": ""}]

    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": False, "themes": [], "rating": 1500,
        "rating_before": 1500, "rating_after": 1496, "rating_diff": -4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": True,
    })
    page.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    assert page.locator("#lichess-puzzle-btn-solution").is_visible()


def test_coup_illegal_refuse_sans_penalite_puis_bon_coup(at_puzzle_virtuel):
    """Garde-fou serveur (toujours revalidé même si l'écran ne propose que
    des destinations légales) : le joueur réessaie avec les MÊMES coups
    légaux, sans qu'aucun résultat de problème n'ait été affiché."""
    page = at_puzzle_virtuel
    _declencher_evenement_socket_client(page, "lichess_puzzle_your_turn", {
        "legal_moves": {"e2": ["e3", "e4"]},
    })
    _click_case(page, 4, 1)  # e2
    _click_case(page, 4, 3)  # e4
    assert _dernieres_actions(page) == [{"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4", "promotion": ""}]

    # Le serveur refuse exceptionnellement ce coup (garde-fou) — aucune
    # bannière de résultat ne doit apparaître, et l'échiquier redevient
    # cliquable avec les mêmes coups légaux.
    _declencher_evenement_socket_client(page, "lichess_puzzle_virtual_illegal", {"from": "e2", "to": "e4"})
    assert not page.locator("#lichess-puzzle-result").is_visible()
    page.wait_for_selector("#toast.show", timeout=3000)

    # Réessai — accepté cette fois.
    _click_case(page, 4, 1)
    _click_case(page, 4, 3)
    actions = _dernieres_actions(page)
    assert actions[-1] == {"type": "lichess_puzzle_virtual_move", "from": "e2", "to": "e4", "promotion": ""}


def test_promotion_choix_de_piece_a_l_ecran(at_menu):
    page = at_menu
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "lichess_puzzle_playing", "virtual": True,
        "fen": FEN_PROMOTION, "color": "white", "puzzle_id": "pzl2", "rating": 1500,
    })
    page.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    _capturer_actions(page)
    _declencher_evenement_socket_client(page, "lichess_puzzle_your_turn", {
        "legal_moves": {"a7": ["a8"]},
    })

    _click_case(page, 0, 6)  # a7 → coord interne "0-6"
    _click_case(page, 0, 7)  # a8 — seule destination légale, c'est une promotion

    # "♛" (dame/queen/Dame) — seul repère indépendant de la langue active du
    # navigateur (le dialogue de promotion est générique, _virtAskPromotion,
    # texte localisé via pieces.dame).
    page.locator("button:has-text('♛')").click()
    actions = _dernieres_actions(page)
    assert actions == [{"type": "lichess_puzzle_virtual_move", "from": "a7", "to": "a8", "promotion": "q"}]
