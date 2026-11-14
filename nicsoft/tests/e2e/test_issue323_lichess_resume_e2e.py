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
    _declencher_lichess_resumable,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def at_config_lichess(at_menu):
    at_menu.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    at_menu.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    # Détache le vrai gestionnaire socket.io avant de poser un état de
    # départ déterministe (issue #325) — voir
    # test_issue310_lichess_e2e.py::_declencher_lichess_resumable pour la
    # raison (réponse réseau réelle tardive, racé avec l'état simulé du
    # test en cours).
    at_menu.evaluate(
        "() => { "
        # Idempotent — voir test_issue310_lichess_e2e.py, même garde.
        "if (!window.__realLichessResumableHandlers) { "
        "window.__realLichessResumableHandlers = socket.listeners('lichess_resumable').slice(); "
        "socket.off('lichess_resumable'); "
        "} "
        "}"
    )
    _declencher_lichess_resumable(at_menu, {"available": False, "games": []})
    return at_menu


# ═══════════════════════════════════════════════════════════════════════
# 1. Bandeau de reprise dans l'écran de configuration Lichess
# ═══════════════════════════════════════════════════════════════════════

def test_aucune_partie_en_cours_aucun_bandeau(at_config_lichess):
    page = at_config_lichess
    _declencher_lichess_resumable(page, {"available": False, "games": []})
    assert page.locator("#lichess-resume-banner").is_hidden()
    # Issue #325, point 2 : sans partie en cours, le formulaire normal reste
    # accessible.
    assert page.locator("#lichess-new-game-form").is_visible()


def test_partie_en_cours_affiche_le_bandeau_avec_les_bonnes_infos(at_config_lichess):
    page = at_config_lichess
    _declencher_lichess_resumable(page, {
        "available": True,
        "games": [{
            "game_id": "aBcD1234", "color": "black", "opponent": "Stockfish level 4",
            "ai_level": 4, "speed": "blitz", "is_my_turn": True, "seconds_left": 480,
            "resumable": True,
        }],
    })
    banner = page.locator("#lichess-resume-banner")
    assert banner.is_visible()
    # Issue #325, point 2 : le formulaire de nouvelle partie est caché tant
    # qu'une partie est en cours.
    assert page.locator("#lichess-new-game-form").is_hidden()
    detail = (page.locator("#lichess-ongoing-games-list .lichess-resume-detail").text_content() or "")
    assert "Stockfish level 4" in detail
    assert "8" in detail  # 480s → 8 minutes restantes


def test_nom_adversaire_echappe_jamais_execute_comme_html(at_config_lichess):
    """Nom d'adversaire contenant des caractères HTML — doit apparaître tel
    quel en texte, jamais interprété (issue #323, point 2 : échappement
    habituel pour tout texte venu de Lichess)."""
    page = at_config_lichess
    nom_piege = "<img src=x onerror=alert(1)>Méchant"
    _declencher_lichess_resumable(page, {
        "available": True,
        "games": [{
            "game_id": "zZyY9876", "color": "white", "opponent": nom_piege,
            "ai_level": None, "speed": "rapid", "is_my_turn": False, "seconds_left": 120,
            "resumable": False,
        }],
    })
    detail = page.locator("#lichess-ongoing-games-list .lichess-resume-detail")
    assert detail.is_visible()
    # Si le texte avait été injecté en innerHTML, la balise <img> serait un
    # vrai élément DOM — ici elle ne doit jamais apparaître comme tel.
    assert page.locator("#lichess-ongoing-games-list img").count() == 0
    assert nom_piege in (detail.text_content() or "")
    # source=friend (non-IA) : pas de bouton Reprendre, explication affichée.
    assert page.locator("#lichess-ongoing-games-list button[data-action=\"lichess_resume_game\"]").count() == 0
    assert page.locator("#lichess-ongoing-games-list .lichess-ongoing-game-note").count() == 1


def test_clic_sur_reprendre_envoie_laction_avec_le_bon_identifiant(at_config_lichess):
    page = at_config_lichess
    _declencher_lichess_resumable(page, {
        "available": True,
        "games": [{
            "game_id": "idTest01", "color": "white", "opponent": "Stockfish level 1",
            "ai_level": 1, "speed": "blitz", "is_my_turn": True, "seconds_left": 300,
            "resumable": True,
        }],
    })
    captured = page.evaluate(
        "() => { "
        "window.__captured = null; "
        "const orig = socket.emit.bind(socket); "
        "socket.emit = (ev, data) => { if (ev === 'action') window.__captured = data; return orig(ev, data); }; "
        "document.querySelector('[data-action=\"lichess_resume_game\"]').click(); "
        "return window.__captured; "
        "}"
    )
    assert captured["type"] == "start_lichess_resume"
    assert captured["game_id"] == "idTest01"


def test_plusieurs_parties_en_cours_affichees_lune_sous_lautre(at_config_lichess):
    """Issue #325, point 2 : plusieurs parties en cours (ne peuvent exister
    que créées ailleurs ou laissées ouvertes par un arrêt brutal) sont
    toutes affichées, chacune avec ses propres boutons."""
    page = at_config_lichess
    _declencher_lichess_resumable(page, {
        "available": True,
        "games": [
            {"game_id": "g1", "color": "white", "opponent": "bob", "ai_level": None,
             "speed": "blitz", "is_my_turn": True, "seconds_left": 300, "resumable": False},
            {"game_id": "g2", "color": "black", "opponent": "Stockfish level 3", "ai_level": 3,
             "speed": "rapid", "is_my_turn": False, "seconds_left": 900, "resumable": True},
        ],
    })
    cards = page.locator(".lichess-ongoing-game-card")
    assert cards.count() == 2
    assert page.locator("button[data-action=\"lichess_resume_game\"][data-game-id=\"g2\"]").count() == 1
    assert page.locator("button[data-action=\"lichess_abandon_ongoing\"][data-game-id=\"g1\"]").count() == 1
    assert page.locator("button[data-action=\"lichess_abandon_ongoing\"][data-game-id=\"g2\"]").count() == 1


def test_abandon_ongoing_demande_confirmation_puis_envoie_laction(at_config_lichess):
    """Issue #325, point 3 : abandon depuis la liste — confirmation
    explicite avant tout envoi réseau."""
    page = at_config_lichess
    _declencher_lichess_resumable(page, {
        "available": True,
        "games": [{
            "game_id": "idAband1", "color": "white", "opponent": "bob", "ai_level": None,
            "speed": "blitz", "is_my_turn": True, "seconds_left": 300, "resumable": False,
        }],
    })
    page.locator("button[data-action=\"lichess_abandon_ongoing\"]").click()
    assert page.locator("#modal-overlay.open").is_visible()
    captured = page.evaluate(
        "() => { "
        "window.__captured = null; "
        "const orig = socket.emit.bind(socket); "
        "socket.emit = (ev, data) => { if (ev === 'action') window.__captured = data; return orig(ev, data); }; "
        "document.getElementById('modal-confirm').click(); "
        "return window.__captured; "
        "}"
    )
    assert captured["type"] == "lichess_abandon_ongoing"
    assert captured["game_id"] == "idAband1"
    assert page.locator("#modal-overlay.open").count() == 0


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
    """Par défaut (avant tout lichess_action_buttons), les deux boutons
    restent grisés — même mécanisme que les autres attentes de position
    (issue #321). Voir test_issue325_lichess_single_game_e2e.py pour la
    correction du point 5 (#325) : Abandonner redevient actif dès que le
    serveur l'annonce, sans attendre la reconstruction de la position."""
    page = at_game_lichess_resume
    # Grisés par défaut dès lichess_init (voir test_issue321_lichess_e2e) ;
    # jamais simulé ici volontairement, pour vérifier l'état par défaut
    # avant tout lichess_action_buttons.
    assert page.locator("#btn-resign").is_disabled()
    assert page.locator("#btn-nulle").is_disabled()
