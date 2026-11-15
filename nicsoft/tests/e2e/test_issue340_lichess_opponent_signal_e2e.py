"""
nicsoft/tests/e2e/test_issue340_lichess_opponent_signal_e2e.py — AlChess

Issue #340, point 3/7 : cadre visible autour de l'échiquier de l'écran tant
que l'adversaire est parti — couleur distincte dès que la réclamation
devient possible, disparition avec le signal (retour de l'adversaire ou
acquittement « J'ai vu »), et court message au retour de l'adversaire.
Ceci ne peut pas être vérifié côté Python (pure logique DOM/CSS côté
navigateur) — même technique que test_issue310/321_lichess_e2e.py :
événements socket "lichess_opponent_gone" simulés en invoquant directement
les callbacks déjà enregistrés par `socket.on(...)`, sans réseau ni partie
Lichess réelle, sans jamais lire ni utiliser le vrai jeton d'Alain.

Lancer : pytest nicsoft/tests/e2e/test_issue340_lichess_opponent_signal_e2e.py -v
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import FEN_DEPART, _declencher_evenement_socket_client

pytestmark = pytest.mark.slow


def _frame_classes(page):
    return page.evaluate(
        "() => { const w = document.getElementById('board-wrapper'); "
        "return w ? Array.from(w.classList) : []; }"
    )


@pytest.fixture
def at_game_lichess(at_menu):
    """Écran de partie Lichess simulé (utilisateur blanc), sans requête
    réseau ni jeton — comme at_game_lichess_noir de test_issue321_lichess_e2e."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART, "color": "white", "level": 3, "player": "Testeur e2e"},
    )
    return at_menu


def test_aucun_cadre_par_defaut(at_game_lichess):
    page = at_game_lichess
    classes = _frame_classes(page)
    assert "board-opponent-gone-frame" not in classes
    assert "board-opponent-gone-frame-claimable" not in classes


def test_cadre_depart_puis_reclamable_puis_disparait_au_retour(at_game_lichess):
    page = at_game_lichess

    _declencher_evenement_socket_client(
        page, "lichess_opponent_gone", {"gone": True, "seconds": 60, "claimable": False, "draw_claimable": False},
    )
    classes = _frame_classes(page)
    assert "board-opponent-gone-frame" in classes
    assert "board-opponent-gone-frame-claimable" not in classes
    assert page.locator("#lichess-opponent-gone-banner").is_visible()

    _declencher_evenement_socket_client(
        page, "lichess_opponent_gone", {"gone": True, "seconds": 0, "claimable": True, "draw_claimable": True},
    )
    classes = _frame_classes(page)
    assert "board-opponent-gone-frame" not in classes
    assert "board-opponent-gone-frame-claimable" in classes

    # Retour de l'adversaire (issue #340, point 4) : cadre et bandeau
    # disparaissent, court message affiché.
    _declencher_evenement_socket_client(page, "lichess_opponent_gone", {"gone": False})
    classes = _frame_classes(page)
    assert "board-opponent-gone-frame" not in classes
    assert "board-opponent-gone-frame-claimable" not in classes
    assert page.locator("#lichess-opponent-gone-banner").is_hidden()
    toast_text = page.locator("#toast").inner_text()
    expected = page.evaluate("() => t('lichess.adversaire_revenu')")
    assert toast_text == expected


def test_cadre_disparait_sur_j_ai_vu_sans_attendre_le_serveur(at_game_lichess):
    """Le bandeau reste affiché après « J'ai vu » (comportement #334
    inchangé), mais le cadre — qui suit le signal bip/LED, pas le bandeau —
    doit disparaître immédiatement, localement, sans attendre un
    événement serveur dédié (issue #340, point 3)."""
    page = at_game_lichess

    _declencher_evenement_socket_client(
        page, "lichess_opponent_gone", {"gone": True, "seconds": 30, "claimable": False, "draw_claimable": False},
    )
    assert "board-opponent-gone-frame" in _frame_classes(page)

    page.locator('[data-action="lichess_opponent_gone_ack"]').click()
    classes = _frame_classes(page)
    assert "board-opponent-gone-frame" not in classes
    assert "board-opponent-gone-frame-claimable" not in classes
    # Le bandeau, lui, reste affiché (seul le signal/cadre s'éteint).
    assert page.locator("#lichess-opponent-gone-banner").is_visible()


def test_cadre_absent_apres_retour_au_menu(at_game_lichess):
    """Issue #340, point 4 : aucun cadre ne doit rester affiché au retour
    au menu (même garde que pour les LED physiques, côté écran)."""
    page = at_game_lichess

    _declencher_evenement_socket_client(
        page, "lichess_opponent_gone", {"gone": True, "seconds": 30, "claimable": True, "draw_claimable": True},
    )
    assert _frame_classes(page)  # au moins une des deux classes posée

    page.evaluate("sendAction({type: 'back_menu'})")
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    classes = _frame_classes(page)
    assert "board-opponent-gone-frame" not in classes
    assert "board-opponent-gone-frame-claimable" not in classes
