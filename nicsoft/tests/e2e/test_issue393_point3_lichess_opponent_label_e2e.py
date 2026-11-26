"""
nicsoft/tests/e2e/test_issue393_point3_lichess_opponent_label_e2e.py —
AlChess

Issue #393, point 3 (suite de l'étude #391) : le panneau « Tour en cours »
affichait "IA de Lichess (niveau 1)" pour un coup d'un adversaire HUMAIN.
Côté serveur (test_issue393_point3_lichess_opponent_label.py),
`lichess_move` transmet désormais `opponent_is_ai`/`opponent_name` — ce
fichier vérifie que socket.on("lichess_move") (app.js) s'en sert
correctement, sans passer par une vraie partie Lichess."""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import _declencher_evenement_socket_client

pytestmark = pytest.mark.slow


@pytest.fixture
def at_game_lichess(at_menu):
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    return at_menu


def test_coup_adverse_ia_affiche_ia_de_lichess(at_game_lichess):
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_move", {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR", "san": "e4", "uci": "e2e4",
        "color": "white", "level": 3, "opponent_move": True,
        "opponent_is_ai": True, "opponent_name": "",
    })
    texte = page.locator("#turn-info").inner_text()
    attendu = page.evaluate("() => t('lichess.ia_niveau', {level: 3})")
    assert attendu in texte


def test_coup_adverse_humain_affiche_son_nom_jamais_ia(at_game_lichess):
    """Bug réel établi par #391 : un adversaire humain était affiché
    "IA de Lichess (niveau N)" — ne doit plus jamais se produire."""
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_move", {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR", "san": "e4", "uci": "e2e4",
        "color": "white", "level": 3, "opponent_move": True,
        "opponent_is_ai": False, "opponent_name": "Adversaire Test",
    })
    texte = page.locator("#turn-info").inner_text()
    assert "Adversaire Test" in texte
    ia_label = page.evaluate("() => t('lichess.ia_niveau', {level: 3})")
    assert ia_label not in texte


def test_coup_propre_reste_vous_quel_que_soit_opponent_is_ai(at_game_lichess):
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_move", {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR", "san": "e4", "uci": "e2e4",
        "color": "white", "level": 3, "opponent_move": False,
        "opponent_is_ai": False, "opponent_name": "Adversaire Test",
    })
    texte = page.locator("#turn-info").inner_text()
    assert "Adversaire Test" not in texte
