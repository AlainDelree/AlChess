"""
nicsoft/tests/e2e/test_issue377_lichess_clock_unreliable_e2e.py — AlChess

Issue #377, point 1 : pendant une coupure réseau en pleine partie Lichess,
l'horloge continue d'être extrapolée localement alors que l'adversaire,
toujours connecté à lichess.org, peut jouer et changer le trait — rien
n'avertit alors l'utilisateur que les pendules affichées ne sont plus
fiables. Les deux pendules sont marquées visuellement non fiables
(classe CSS `clock-unreliable` + infobulle) dès "lichess_reconnecting",
retirées dès "lichess_reconnected", et jamais bloquées (retour menu en
pleine coupure, resynchronisation par un nouveau gameFull, fin de partie).

Pure logique DOM/CSS côté navigateur, non vérifiable côté Python — même
technique que test_issue340_lichess_opponent_signal_e2e.py : évènements
socket simulés en invoquant directement les callbacks déjà enregistrés par
`socket.on(...)`, sans réseau ni partie Lichess réelle, sans jamais lire ni
utiliser le vrai jeton d'Alain.

Lancer : pytest nicsoft/tests/e2e/test_issue377_lichess_clock_unreliable_e2e.py -v
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import FEN_DEPART, _declencher_evenement_socket_client

pytestmark = pytest.mark.slow


def _clock_classes(page, elem_id):
    return page.evaluate(
        "(id) => { const el = document.getElementById(id); "
        "return el ? Array.from(el.classList) : []; }",
        elem_id,
    )


def _clock_title(page, elem_id):
    return page.evaluate(
        "(id) => { const el = document.getElementById(id); return el ? el.title : null; }",
        elem_id,
    )


@pytest.fixture
def at_game_lichess(at_menu):
    """Écran de partie Lichess simulé (utilisateur blanc), sans requête
    réseau ni jeton — même fixture que test_issue340_lichess_opponent_signal_e2e.py."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART, "color": "white", "level": 3, "player": "Testeur e2e"},
    )
    return at_menu


def test_aucun_marquage_par_defaut(at_game_lichess):
    page = at_game_lichess
    assert "clock-unreliable" not in _clock_classes(page, "clock-top")
    assert "clock-unreliable" not in _clock_classes(page, "clock-bottom")


def test_reconnecting_marque_les_deux_pendules_puis_reconnected_les_retire(at_game_lichess):
    page = at_game_lichess

    _declencher_evenement_socket_client(page, "lichess_reconnecting", {"attempt": 1})
    assert "clock-unreliable" in _clock_classes(page, "clock-top")
    assert "clock-unreliable" in _clock_classes(page, "clock-bottom")
    # Infobulle explicative, non vide, dans les trois langues (contenu exact
    # non vérifié ici — test_issue357-style de garde i18n ailleurs).
    assert _clock_title(page, "clock-top")
    assert _clock_title(page, "clock-bottom")

    _declencher_evenement_socket_client(page, "lichess_reconnected", {})
    assert "clock-unreliable" not in _clock_classes(page, "clock-top")
    assert "clock-unreliable" not in _clock_classes(page, "clock-bottom")
    assert _clock_title(page, "clock-top") == ""
    assert _clock_title(page, "clock-bottom") == ""


def test_marquage_disparait_au_retour_menu_en_pleine_coupure(at_game_lichess):
    """Le marquage ne doit jamais rester bloqué si l'utilisateur quitte
    l'écran de partie pendant une coupure (jamais de "lichess_reconnected"
    reçu)."""
    page = at_game_lichess

    _declencher_evenement_socket_client(page, "lichess_reconnecting", {"attempt": 1})
    assert "clock-unreliable" in _clock_classes(page, "clock-top")

    page.evaluate("sendAction({type: 'back_menu'})")
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    assert "clock-unreliable" not in _clock_classes(page, "clock-top")
    assert "clock-unreliable" not in _clock_classes(page, "clock-bottom")


def test_marquage_disparait_a_la_resynchronisation_par_un_nouveau_gamefull(at_game_lichess):
    """Un nouveau "lichess_init" (resynchronisation après reconnexion du
    flux, nouveau gameFull côté serveur) doit aussi retirer le marquage,
    même sans "lichess_reconnected" explicite reçu avant."""
    page = at_game_lichess

    _declencher_evenement_socket_client(page, "lichess_reconnecting", {"attempt": 1})
    assert "clock-unreliable" in _clock_classes(page, "clock-top")

    _declencher_evenement_socket_client(
        page, "lichess_init",
        {"fen": FEN_DEPART, "color": "white", "level": 3, "player": "Testeur e2e"},
    )
    assert "clock-unreliable" not in _clock_classes(page, "clock-top")
    assert "clock-unreliable" not in _clock_classes(page, "clock-bottom")


def test_marquage_disparait_en_fin_de_partie(at_game_lichess):
    page = at_game_lichess

    _declencher_evenement_socket_client(page, "lichess_reconnecting", {"attempt": 1})
    assert "clock-unreliable" in _clock_classes(page, "clock-top")

    _declencher_evenement_socket_client(page, "game_over", {
        "skip": False, "source": "lichess", "title": "Partie terminée", "result": "1-0",
    })
    assert "clock-unreliable" not in _clock_classes(page, "clock-top")
    assert "clock-unreliable" not in _clock_classes(page, "clock-bottom")

    # Retour menu : base de référence de la session e2e restaurée.
    page.evaluate("sendAction({type: 'back_menu'})")
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)
