"""
nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py — AlChess

Issue #323 (étape L2b) : reprise d'une partie Lichess en cours depuis le
menu. Vérifie ici, dans un vrai navigateur (Playwright), uniquement ce qui
ne peut pas l'être côté Python : affichage/masquage du bandeau de reprise
dans l'écran de configuration Lichess (avec échappement du nom
d'adversaire), et l'écran de mise en place (bandeau + cases rouges sur
#board) pendant une reprise. La logique serveur (détection, construction
de la position cible, gestion des cas a-f) est testée sans navigateur dans
nicsoft/tests/test_issue323_lichess_resume.py.

Même technique que test_issue310_lichess_e2e.py / test_issue321_lichess_e2e.py :
événements socket simulés en invoquant directement les callbacks déjà
enregistrés par `socket.on(...)` côté client, sans requête réseau ni
partie Lichess réelle, ni échiquier physique.

Lancer : pytest nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py -v
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import (
    FEN_DEPART,
    _declencher_evenement_socket_client,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def at_config_lichess(at_menu):
    at_menu.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    at_menu.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    return at_menu


# ═══════════════════════════════════════════════════════════════════════
# 1. Bandeau de reprise dans l'écran de configuration Lichess
# ═══════════════════════════════════════════════════════════════════════

def test_aucune_partie_en_cours_aucun_bandeau(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_resumable", {"available": False})
    assert page.locator("#lichess-resume-banner").is_hidden()


def test_partie_en_cours_affiche_le_bandeau_avec_les_bonnes_infos(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_resumable", {
        "available": True,
        "game": {
            "game_id": "aBcD1234", "color": "black", "opponent": "Stockfish level 4",
            "ai_level": 4, "speed": "blitz", "is_my_turn": True, "seconds_left": 480,
        },
    })
    banner = page.locator("#lichess-resume-banner")
    assert banner.is_visible()
    detail = (page.locator("#lichess-resume-detail").text_content() or "")
    assert "Stockfish level 4" in detail
    assert "8" in detail  # 480s → 8 minutes restantes


def test_nom_adversaire_echappe_jamais_execute_comme_html(at_config_lichess):
    """Nom d'adversaire contenant des caractères HTML — doit apparaître tel
    quel en texte, jamais interprété (issue #323, point 2 : échappement
    habituel pour tout texte venu de Lichess)."""
    page = at_config_lichess
    nom_piege = "<img src=x onerror=alert(1)>Méchant"
    _declencher_evenement_socket_client(page, "lichess_resumable", {
        "available": True,
        "game": {
            "game_id": "zZyY9876", "color": "white", "opponent": nom_piege,
            "ai_level": None, "speed": "rapid", "is_my_turn": False, "seconds_left": 120,
        },
    })
    detail = page.locator("#lichess-resume-detail")
    assert detail.is_visible()
    # Si le texte avait été injecté en innerHTML, la balise <img> serait un
    # vrai élément DOM — ici elle ne doit jamais apparaître comme tel.
    assert page.locator("#lichess-resume-detail img").count() == 0
    assert nom_piege in (detail.text_content() or "")


def test_clic_sur_reprendre_envoie_laction_avec_le_bon_identifiant(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_resumable", {
        "available": True,
        "game": {
            "game_id": "idTest01", "color": "white", "opponent": "Stockfish level 1",
            "ai_level": 1, "speed": "blitz", "is_my_turn": True, "seconds_left": 300,
        },
    })
    captured = page.evaluate(
        "() => { "
        "window.__captured = null; "
        "const orig = socket.emit.bind(socket); "
        "socket.emit = (ev, data) => { if (ev === 'action') window.__captured = data; return orig(ev, data); }; "
        "document.getElementById('lichess-resume-btn').click(); "
        "return window.__captured; "
        "}"
    )
    assert captured["type"] == "start_lichess_resume"
    assert captured["game_id"] == "idTest01"


# ═══════════════════════════════════════════════════════════════════════
# 2. Écran de mise en place pendant une reprise (issue #323, point 3)
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def at_game_lichess_resume(at_menu):
    """Simule l'entrée en jeu d'une partie reprise — sans jamais démarrer de
    vraie partie Lichess (pas de requête réseau)."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART.split(" ")[0], "color": "black", "level": 2, "player": "Testeur e2e"},
    )
    return at_menu


def test_mise_en_place_affiche_le_bandeau_et_les_cases_rouges(at_game_lichess_resume):
    page = at_game_lichess_resume
    _declencher_evenement_socket_client(page, "lichess_resume_setup", {
        "active": True,
        "expected_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR",
        "physical_fen": "8/8/8/8/8/8/8/8",
    })
    assert page.locator("#lichess-resume-setup").is_visible()
    assert page.locator("#board .sq-error").count() > 0


def test_mise_en_place_masquee_une_fois_la_position_correcte(at_game_lichess_resume):
    page = at_game_lichess_resume
    _declencher_evenement_socket_client(page, "lichess_resume_setup", {
        "active": True,
        "expected_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR",
        "physical_fen": "8/8/8/8/8/8/8/8",
    })
    assert page.locator("#lichess-resume-setup").is_visible()
    _declencher_evenement_socket_client(page, "lichess_resume_setup", {"active": False})
    assert page.locator("#lichess-resume-setup").is_hidden()


def test_boutons_abandon_nulle_restent_desactives_pendant_la_mise_en_place(at_game_lichess_resume):
    """Aucune action de partie n'est permise avant que la position physique
    ne soit confirmée (issue #323, point 5) — même mécanisme que les autres
    attentes de position (issue #321)."""
    page = at_game_lichess_resume
    # Grisés par défaut dès lichess_init (voir test_issue321_lichess_e2e) ;
    # aucun lichess_action_buttons n'est envoyé tant que _resume_pending est
    # vrai côté serveur (voir _compute_action_buttons, game.py) — jamais
    # simulé ici volontairement, pour vérifier l'état par défaut.
    assert page.locator("#btn-resign").is_disabled()
    assert page.locator("#btn-nulle").is_disabled()
