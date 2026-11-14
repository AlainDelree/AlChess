"""
nicsoft/tests/e2e/test_issue333_lichess_menu_banner_e2e.py — AlChess

Issue #333, point 3 : bandeau "Une partie Lichess est en cours" affiché en
tête du MENU PRINCIPAL (pas seulement de l'écran de configuration Lichess)
dès qu'une partie en temps réel est en cours, avec bouton direct Reprendre/
Abandonner — vérifications qui ne peuvent pas l'être côté Python seul
(rendu DOM réel, visibilité selon l'écran affiché).

Même technique que les autres suites e2e Lichess (#310/#325) :
`_declencher_lichess_resumable` (pas `_declencher_evenement_socket_client`
directement) — `page` est partagée par TOUTE la session de tests e2e
(fixture `page`, scope="session", conftest.py) ; un test antérieur
(`at_config_lichess`, voir #310/#325) détache déjà le vrai gestionnaire
socket.io de "lichess_resumable" pour ses propres besoins, de façon
irréversible pour le reste de la session — utiliser l'appel direct
`socket.listeners('lichess_resumable')` échouerait alors ("aucun listener")
selon l'ordre d'exécution des fichiers de test. Jamais de requête réseau ni
de partie Lichess réelle (le serveur e2e tourne avec un jeton vide, voir
conftest.py::_build_isolated_alchess_dir, issue #326).

Lancer : pytest nicsoft/tests/e2e/test_issue333_lichess_menu_banner_e2e.py -v
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import (
    _declencher_evenement_socket_client,
    _declencher_lichess_resumable,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def at_menu_resumable_ready(at_menu):
    """`at_menu`, avec le vrai gestionnaire "lichess_resumable" détaché une
    fois pour toutes (idempotent, même garde que `at_config_lichess` —
    voir test_issue310_lichess_e2e.py) — nécessaire pour utiliser
    `_declencher_lichess_resumable` depuis le MENU PRINCIPAL (pas seulement
    depuis l'écran de configuration Lichess, qui porte déjà sa propre
    fixture `at_config_lichess`)."""
    at_menu.evaluate(
        "() => { "
        "if (!window.__realLichessResumableHandlers) { "
        "window.__realLichessResumableHandlers = socket.listeners('lichess_resumable').slice(); "
        "socket.off('lichess_resumable'); "
        "} "
        "}"
    )
    return at_menu


def _partie_en_cours(game_id="gid1", color="white", opponent="Bob", resumable=True, reason=None):
    return {
        "game_id": game_id, "color": color, "opponent": opponent, "ai_level": None,
        "speed": "rapid", "is_my_turn": True, "seconds_left": 742,
        "resumable": resumable, "unresumable_reason": reason,
    }


def test_bandeau_menu_affiche_quand_partie_en_cours(at_menu_resumable_ready):
    page = at_menu_resumable_ready
    banner = page.locator("#lichess-menu-banner")
    _declencher_lichess_resumable(page, {"available": True, "games": [_partie_en_cours()]})
    assert banner.is_visible()
    # Bouton direct "Reprendre" — même action que depuis l'écran Lichess.
    resume_btn = page.locator("#lichess-menu-banner-list [data-action='lichess_resume_game']")
    assert resume_btn.count() == 1
    assert resume_btn.get_attribute("data-game-id") == "gid1"


def test_bandeau_menu_absent_sans_partie_en_cours(at_menu_resumable_ready):
    page = at_menu_resumable_ready
    _declencher_lichess_resumable(page, {"available": False, "games": []})
    assert page.locator("#lichess-menu-banner").is_hidden()


def test_bandeau_menu_partie_non_reprenable_affiche_bouton_abandonner_seul(at_menu_resumable_ready):
    """Issue #333, point 1 : une partie non reprenable (ex. cadence trop
    rapide, raison "speed") garde le bouton "Abandonner" mais pas
    "Reprendre", avec l'explication exacte affichée."""
    page = at_menu_resumable_ready
    _declencher_lichess_resumable(page, {
        "available": True,
        "games": [_partie_en_cours(resumable=False, reason="speed")],
    })
    banner = page.locator("#lichess-menu-banner")
    assert banner.is_visible()
    assert banner.locator("[data-action='lichess_resume_game']").count() == 0
    assert banner.locator("[data-action='lichess_abandon_ongoing']").count() == 1
    # Explication exacte liée à la raison "speed" (langue du navigateur de
    # test — peu importe laquelle, voir i18n/*.json) — jamais le message
    # générique "non reprenable ici pour l'instant" ni celui lié à la
    # variante.
    note = banner.locator(".lichess-ongoing-game-note").inner_text()
    assert note.strip() != ""
    assert "variant" not in note.lower() and "chess960" not in note.lower()


def test_bandeau_menu_masque_ne_bloque_pas_les_autres_modes(at_menu_resumable_ready):
    """Le bandeau ne doit jamais empêcher d'accéder à un autre mode — ici,
    la navigation (accueil → mode retranscription) reste fonctionnelle
    pendant que le bandeau est affiché."""
    page = at_menu_resumable_ready
    _declencher_lichess_resumable(page, {"available": True, "games": [_partie_en_cours()]})
    assert page.locator("#lichess-menu-banner").is_visible()
    # Un autre mode reste atteignable normalement (aucun blocage du menu).
    page.evaluate("sendAction({type: 'mode', value: 'retranscription'})")
    _declencher_evenement_socket_client(page, "app_state", {"state": "retranscription"})
    page.wait_for_selector("#screen-retranscription", state="visible", timeout=5000)
    # Le bandeau du menu principal disparaît en quittant le menu (il n'a
    # pas sa place au-dessus d'un autre mode).
    assert page.locator("#lichess-menu-banner").is_hidden()


def test_bandeau_menu_une_seule_requete_par_arrivee(at_menu):
    """Issue #333, point 3 : une seule requête silencieuse par arrivée
    réelle sur le menu — un second évènement "app_state":"menu" redondant
    (ex. pendant un nettoyage de fin de partie) ne déclenche pas de
    nouvelle action "lichess_menu_check"."""
    page = at_menu
    # Sort du menu pour réarmer le débounce côté JS — sinon le drapeau
    # (_lichessMenuBannerChecked) peut déjà être vrai depuis l'arrivée
    # initiale sur le menu faite par la fixture at_menu elle-même.
    _declencher_evenement_socket_client(page, "app_state", {"state": "config_lichess"})
    sent = page.evaluate(
        "() => { "
        "window.__sentActions = []; "
        "const orig = socket.emit.bind(socket); "
        "socket.emit = (...args) => { if (args[0] === 'action') window.__sentActions.push(args[1]); "
        "return orig(...args); }; "
        "return true; }"
    )
    assert sent is True
    _declencher_evenement_socket_client(page, "app_state", {"state": "menu"})
    _declencher_evenement_socket_client(page, "app_state", {"state": "menu"})
    count = page.evaluate(
        "() => window.__sentActions.filter(a => a.type === 'lichess_menu_check').length"
    )
    assert count == 1
