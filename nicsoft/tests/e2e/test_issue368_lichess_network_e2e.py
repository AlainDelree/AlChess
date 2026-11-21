"""
nicsoft/tests/e2e/test_issue368_lichess_network_e2e.py — AlChess

Issue #368, partie 1 : écran Lichess sans réseau — bandeau permanent,
boutons/contrôles grisés, jamais confondu avec un jeton refusé, tout se
réactive sans recharger la page au retour du réseau.

Sans échiquier ni Lichess réels (serveur lancé avec ALCHESS_SKIP_BOARD=1,
voir conftest.py), sur le même modèle que
test_issue365_lichess_sans_echiquier_e2e.py : états simulés en invoquant
directement les callbacks socket.io déjà enregistrés par app.js (jamais un
vrai réseau, un vrai jeton ni une vraie coupure).

Lancer : pytest nicsoft/tests/e2e/test_issue368_lichess_network_e2e.py -v
"""
import pytest

pytestmark = pytest.mark.slow


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _declencher_config_data(page, data):
    page.evaluate(
        "([data]) => { "
        "const cbs = window.__realConfigDataHandlers368 || []; "
        "if (cbs.length === 0) throw new Error('aucun gestionnaire config_data capturé'); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [data],
    )


@pytest.fixture(scope="module", autouse=True)
def _detacher_config_data_reel(page):
    page.evaluate(
        "() => { "
        "window.__realConfigDataHandlers368 = socket.listeners('config_data').slice(); "
        "socket.off('config_data'); "
        "}"
    )
    yield
    page.evaluate(
        "() => { "
        "(window.__realConfigDataHandlers368 || []).forEach((cb) => socket.on('config_data', cb)); "
        "delete window.__realConfigDataHandlers368; "
        "}"
    )


def go_menu(page):
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _reset_base(page):
    _declencher_evenement_socket_client(page, "board_ok", {})
    _declencher_evenement_socket_client(page, "lichess_network_status", {"available": True})
    _declencher_config_data(page, {"has_lichess_token": False})
    go_menu(page)


@pytest.fixture
def at_config_lichess(at_menu):
    page = at_menu
    _declencher_evenement_socket_client(page, "board_ok", {})
    _declencher_config_data(page, {"has_lichess_token": True})
    page.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    # Détache les vrais gestionnaires socket.io déclenchés par le serveur de
    # test (jeton réel toujours vide, ALCHESS_DIR isolé) pour qu'une réponse
    # tardive non simulée n'écrase jamais l'état simulé par ces tests — même
    # procédé que test_issue365_lichess_sans_echiquier_e2e.py.
    page.evaluate(
        "() => { "
        "['lichess_resumable', 'lichess_network_status'].forEach((ev) => { "
        "const key = '__real368_' + ev; "
        "if (!window[key]) { window[key] = socket.listeners(ev).slice(); socket.off(ev); } "
        "}); "
        "}"
    )
    # Base : réseau disponible (comme le reste de la session e2e).
    _declencher_evenement_socket_client(page, "lichess_network_status", {"available": True})
    yield page
    _reset_base(page)


# ── Réseau absent : bandeau permanent + boutons grisés ─────────────────────

def test_reseau_absent_affiche_bandeau_permanent(at_config_lichess):
    page = at_config_lichess
    banniere = page.locator("#lichess-network-banner")
    assert not banniere.is_visible()

    _declencher_evenement_socket_client(page, "lichess_network_status", {"available": False})

    assert banniere.is_visible()
    assert banniere.inner_text().strip() != ""


def test_reseau_absent_grise_les_boutons_de_lancement(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_network_status", {"available": False})

    assert page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert page.locator("#btn-start-lichess").is_disabled()
    assert page.locator("#cfg-lichess-puzzle-mode-virtual").is_disabled()
    assert page.locator("#cfg-lichess-opponent-ai").is_disabled()
    assert page.locator("#cfg-lichess-cadence").is_disabled()
    assert page.locator("#cfg-lichess-player").is_disabled()


def test_reseau_absent_retour_reste_actif_et_menu_reste_accessible(at_config_lichess):
    """« Retour » reste actif (pour que l'utilisateur puisse quitter
    l'écran) et l'entrée Lichess du menu principal reste accessible (pour
    qu'il puisse revenir voir le message)."""
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_network_status", {"available": False})

    retour = page.locator('#screen-config-lichess button[data-action="back_menu"]').first
    assert not retour.is_disabled()
    retour.click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)

    btn_lichess = page.locator('.menu-btn-lichess[data-mode="lichess"]')
    assert not btn_lichess.is_disabled(), "l'entrée Lichess du menu doit rester accessible sans réseau"


# ── Jeton refusé : jamais confondu avec l'absence de réseau ────────────────

def test_jeton_refuse_naffiche_jamais_le_bandeau_reseau(at_config_lichess):
    """Cœur du bug corrigé par cette issue : un jeton refusé (Lichess a
    répondu) ne doit jamais afficher le bandeau réseau permanent, ni griser
    les contrôles pour cette raison."""
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "config_lichess", "toast_message_key": "toast.lichess_invalid_token",
    })

    assert not page.locator("#lichess-network-banner").is_visible()
    assert not page.locator("#cfg-lichess-cadence").is_disabled()
    assert not page.locator("#btn-start-lichess").is_disabled()


# ── Retour du réseau : tout se réactive sans recharger ─────────────────────

def test_retour_du_reseau_reactive_tout(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_network_status", {"available": False})
    assert page.locator("#lichess-network-banner").is_visible()
    assert page.locator("#btn-start-lichess-puzzle").is_disabled()

    _declencher_evenement_socket_client(page, "lichess_network_status", {"available": True})

    assert not page.locator("#lichess-network-banner").is_visible()
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert not page.locator("#btn-start-lichess").is_disabled()
    assert not page.locator("#cfg-lichess-cadence").is_disabled()
