"""
nicsoft/tests/e2e/test_issue325_lichess_single_game_e2e.py — AlChess

Issue #325 : vérifications navigateur qui ne peuvent pas l'être côté Python
seul — complète test_issue323_lichess_resume_e2e.py (liste des parties en
cours, abandon depuis la liste) avec les points propres à l'écran de jeu
pendant une reprise : historique affiché pendant la mise en place (point
5), bandeau du premier coup jamais affiché en même temps que la mise en
place (point 5), et pendule affichée comme inconnue plutôt qu'un 0:00
mensonger (point 7).

Même technique que les autres suites e2e Lichess : événements socket
simulés en invoquant directement les callbacks déjà enregistrés par
`socket.on(...)` côté client, sans requête réseau ni partie Lichess réelle.

Lancer : pytest nicsoft/tests/e2e/test_issue325_lichess_single_game_e2e.py -v
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import (
    FEN_DEPART,
    _declencher_evenement_socket_client,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def at_game_lichess(at_menu):
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    return at_menu


# ═══════════════════════════════════════════════════════════════════════
# 1. Historique affiché pendant la mise en place (point 5)
# ═══════════════════════════════════════════════════════════════════════

def test_historique_affiche_des_le_lichess_init_dune_reprise(at_game_lichess):
    """Avant #325, lichess_init effaçait toujours l'historique
    (document.getElementById("historique").innerHTML = "") — resté vide
    pendant toute la mise en place d'une reprise. Il porte désormais
    history_fen/history_moves, utilisés pour le remplir immédiatement."""
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_init", {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR",
        "color": "black", "level": 2, "player": "Testeur e2e",
        "history_fen": [FEN_DEPART.split(" ")[0], "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"],
        "history_moves": [{"san": "e4", "uci": "e2e4", "color": "white", "qualite": None}],
    })
    historique = page.locator("#historique").inner_html()
    assert "e4" in historique


def test_historique_vide_pour_une_partie_normale_sans_historique(at_game_lichess):
    """Non-régression : une partie lancée normalement (jamais de coup joué
    encore) envoie history_fen/history_moves vides — l'historique reste
    vide, comme avant #325."""
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_init", {
        "fen": FEN_DEPART.split(" ")[0], "color": "white", "level": 1, "player": "Testeur e2e",
        "history_fen": [], "history_moves": [],
    })
    assert (page.locator("#historique").inner_html() or "").strip() == ""


# ═══════════════════════════════════════════════════════════════════════
# 2. Bandeau du premier coup jamais affiché pendant la mise en place (pt.5)
# ═══════════════════════════════════════════════════════════════════════

def test_bandeau_premier_coup_masque_pendant_la_mise_en_place(at_game_lichess):
    """Essai réel d'Alain du 14/11/2026 : « Jouez votre premier coup. » et
    le bandeau de reconstruction de position s'affichaient ensemble."""
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_init", {
        "fen": FEN_DEPART.split(" ")[0], "color": "black", "level": 2, "player": "Testeur e2e",
        "history_fen": [], "history_moves": [],
    })
    _declencher_evenement_socket_client(page, "lichess_first_move_deadline", {"active": True, "seconds": None})
    assert page.locator("#lichess-first-move-deadline").is_visible()

    _declencher_evenement_socket_client(page, "lichess_resume_setup", {
        "active": True,
        "expected_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR",
        "physical_fen": "8/8/8/8/8/8/8/8",
    })
    assert page.locator("#lichess-first-move-deadline").is_hidden()
    assert page.locator("#lichess-resume-setup").is_visible()

    # Une fois la position reconstruite, le bandeau peut redevenir visible.
    _declencher_evenement_socket_client(page, "lichess_resume_setup", {"active": False})
    assert page.locator("#lichess-first-move-deadline").is_visible()


# ═══════════════════════════════════════════════════════════════════════
# 3. Pendule affichée comme inconnue plutôt qu'un 0:00 mensonger (point 7)
# ═══════════════════════════════════════════════════════════════════════

def test_pendule_inconnue_naffiche_pas_0_00_rouge(at_game_lichess):
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_init", {
        "fen": FEN_DEPART.split(" ")[0], "color": "black", "level": 2, "player": "Testeur e2e",
        "history_fen": [], "history_moves": [],
    })
    _declencher_evenement_socket_client(page, "lichess_clock", {
        "white_ms": 0, "black_ms": 0, "turn": "white", "known": False,
    })
    top = page.locator("#clock-top")
    bottom = page.locator("#clock-bottom")
    assert top.text_content() == "—"
    assert bottom.text_content() == "—"
    assert "is-low" not in (top.get_attribute("class") or "")
    assert "is-low" not in (bottom.get_attribute("class") or "")


def test_pendule_connue_affiche_le_temps_reel(at_game_lichess):
    page = at_game_lichess
    _declencher_evenement_socket_client(page, "lichess_init", {
        "fen": FEN_DEPART.split(" ")[0], "color": "black", "level": 2, "player": "Testeur e2e",
        "history_fen": [], "history_moves": [],
    })
    _declencher_evenement_socket_client(page, "lichess_clock", {
        "white_ms": 742000, "black_ms": 900000, "turn": "white", "known": True,
    })
    # L'utilisateur joue les noirs : sa propre pendule (900000ms = 15:00)
    # est en bas (voir _lichessRenderClock, convention lichess_init).
    assert page.locator("#clock-bottom").text_content() == "15:00"
