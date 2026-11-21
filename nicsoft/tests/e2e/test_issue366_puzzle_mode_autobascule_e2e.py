"""
nicsoft/tests/e2e/test_issue366_puzzle_mode_autobascule_e2e.py — AlChess

Issue #366, partie 2 : dans la carte « Problèmes » de l'écran Lichess, sans
échiquier connecté, le mode « Échiquier » restait le mode sélectionné par
défaut (ou mémorisé) et « Jouer un problème » restait grisé avec une
explication jusqu'à ce que l'utilisateur clique lui-même sur « Sur
l'écran ». Alain préfère que l'écran bascule seul sur « Sur l'écran »
quand aucun échiquier n'est connecté, pour que le problème reste jouable
tout de suite.

Corrigé en distinguant, dans app.js : `_lichessPuzzlePreferredMode`
(préférence mémorisée dans localStorage, changée uniquement par un clic
explicite — `selectPuzzleModeLichess()`) et `_lichessPuzzleMode` (mode
effectif, affiché et utilisé pour lancer un problème). Sans échiquier,
`_lichessPuzzleSyncDisplayMode()` bascule temporairement l'effectif sur
"virtual" (jamais écrit dans localStorage) ; à la (re)connexion, elle
rétablit l'effectif sur la préférence mémorisée. Un clic manuel reste
toujours respecté et mémorisé comme avant #366 (`selectPuzzleModeLichess`
inchangée sur ce point).

États simulés en invoquant directement les callbacks socket.io déjà
enregistrés par app.js (même procédé que test_issue365_lichess_sans_
echiquier_e2e.py) — jamais un vrai échiquier ni un vrai jeton. localStorage
remis à sa valeur de base ("board", comme au tout premier chargement) à la
fin de chaque test, pour ne pas affecter les tests suivants (y compris
d'autres fichiers e2e partageant la même page de session).
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
        "const cbs = window.__realConfigDataHandlers366 || []; "
        "if (cbs.length === 0) throw new Error('aucun gestionnaire config_data capturé'); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [data],
    )


@pytest.fixture(scope="module", autouse=True)
def _detacher_config_data_reel(page):
    """Même procédé que test_issue365_lichess_sans_echiquier_e2e.py : détache
    le vrai gestionnaire "config_data" pour tout ce module, pour qu'une
    vraie réponse réseau tardive du serveur de test (jeton réellement vide)
    n'écrase jamais, de façon non déterministe, le jeton SIMULÉ ici."""
    page.evaluate(
        "() => { "
        "window.__realConfigDataHandlers366 = socket.listeners('config_data').slice(); "
        "socket.off('config_data'); "
        "}"
    )
    yield
    page.evaluate(
        "() => { "
        "(window.__realConfigDataHandlers366 || []).forEach((cb) => socket.on('config_data', cb)); "
        "delete window.__realConfigDataHandlers366; "
        "}"
    )


def go_menu(page):
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _preference_memorisee(page):
    return page.evaluate("() => localStorage.getItem('niclink_lichess_puzzle_mode')")


def _reset_base(page):
    """Revient à la préférence de base ("board", celle du tout premier
    chargement) sans échiquier ni jeton — jamais de fuite d'un test simulé
    vers le suivant."""
    page.evaluate("() => { selectPuzzleModeLichess('board'); }")
    _declencher_evenement_socket_client(page, "board_error", {})
    _declencher_config_data(page, {"has_lichess_token": False})
    go_menu(page)


@pytest.fixture
def at_config_lichess_sans_board(at_menu):
    page = at_menu
    go_menu(page)
    _declencher_evenement_socket_client(page, "board_error", {})
    _declencher_config_data(page, {"has_lichess_token": True})
    page.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    page.evaluate(
        "() => { "
        "if (!window.__realLichessResumableHandlers366) { "
        "window.__realLichessResumableHandlers366 = socket.listeners('lichess_resumable').slice(); "
        "socket.off('lichess_resumable'); "
        "} "
        "}"
    )
    yield page
    _reset_base(page)


def test_sans_echiquier_sur_ecran_selectionne_et_jouable(at_config_lichess_sans_board):
    """Cœur de la demande #366, partie 2 : à l'affichage, sans échiquier,
    « Sur l'écran » est sélectionné et « Jouer un problème » utilisable
    tout de suite — sans écraser la préférence mémorisée ("board", celle
    du tout premier chargement, jamais modifiée dans ce test)."""
    page = at_config_lichess_sans_board
    assert page.locator("#cfg-lichess-puzzle-mode-virtual").evaluate("el => el.classList.contains('selected')")
    assert not page.locator("#cfg-lichess-puzzle-mode-board").evaluate("el => el.classList.contains('selected')")
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert not page.locator("#lichess-puzzle-board-hint").is_visible()
    assert _preference_memorisee(page) == "board"


def test_reconnexion_retablit_le_mode_memorise(at_config_lichess_sans_board):
    """La bascule est un état d'affichage temporaire : à la reconnexion,
    l'écran revient au mode mémorisé par l'utilisateur ("board", inchangé
    ici) — jamais mémorisé lui-même à "virtual"."""
    page = at_config_lichess_sans_board
    assert page.locator("#cfg-lichess-puzzle-mode-virtual").evaluate("el => el.classList.contains('selected')")

    _declencher_evenement_socket_client(page, "board_ok", {})
    assert page.locator("#cfg-lichess-puzzle-mode-board").evaluate("el => el.classList.contains('selected')")
    assert not page.locator("#cfg-lichess-puzzle-mode-virtual").evaluate("el => el.classList.contains('selected')")
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert not page.locator("#lichess-puzzle-board-hint").is_visible()
    assert _preference_memorisee(page) == "board"

    # Nouvelle déconnexion pendant que l'écran reste ouvert : la bascule
    # automatique s'applique de nouveau.
    _declencher_evenement_socket_client(page, "board_error", {})
    assert page.locator("#cfg-lichess-puzzle-mode-virtual").evaluate("el => el.classList.contains('selected')")
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()


def test_clic_manuel_echiquier_respecte_et_memorise(at_config_lichess_sans_board):
    """Un clic manuel sur « Échiquier », même sans échiquier connecté,
    reste respecté (bouton grisé, explication affichée) et mémorisé comme
    avant #366 — jamais réécrasé par la bascule automatique elle-même."""
    page = at_config_lichess_sans_board
    page.locator("#cfg-lichess-puzzle-mode-board").click()
    assert page.locator("#cfg-lichess-puzzle-mode-board").evaluate("el => el.classList.contains('selected')")
    assert page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert page.locator("#lichess-puzzle-board-hint").is_visible()
    assert _preference_memorisee(page) == "board"

    # Reconnexion : le mode mémorisé (désormais "board", identique au clic)
    # reste actif, cette fois utilisable.
    _declencher_evenement_socket_client(page, "board_ok", {})
    assert page.locator("#cfg-lichess-puzzle-mode-board").evaluate("el => el.classList.contains('selected')")
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert not page.locator("#lichess-puzzle-board-hint").is_visible()


def test_clic_manuel_sur_ecran_respecte_et_memorise_meme_sans_echiquier(at_config_lichess_sans_board):
    """Un clic manuel sur « Sur l'écran » met à jour la préférence mémorisée
    comme avant #366, qu'il coïncide ou non avec la bascule automatique déjà
    en place faute d'échiquier."""
    page = at_config_lichess_sans_board
    assert _preference_memorisee(page) == "board"  # préférence de base, pas encore "virtual"

    page.locator("#cfg-lichess-puzzle-mode-virtual").click()
    assert page.locator("#cfg-lichess-puzzle-mode-virtual").evaluate("el => el.classList.contains('selected')")
    assert _preference_memorisee(page) == "virtual"
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()

    # Reconnexion : reste sur "Sur l'écran", désormais la préférence réelle.
    _declencher_evenement_socket_client(page, "board_ok", {})
    assert page.locator("#cfg-lichess-puzzle-mode-virtual").evaluate("el => el.classList.contains('selected')")
    assert _preference_memorisee(page) == "virtual"
