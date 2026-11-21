"""
nicsoft/tests/e2e/test_issue365_lichess_sans_echiquier_e2e.py — AlChess

Issue #365 : le rapport de clôture de l'issue #364 (mode virtuel des
problèmes Lichess) affirmait que le menu ne bloquait pas l'accès sans
échiquier — faux pour le bouton du menu PRINCIPAL : `data-needs-board
data-physical-only` le grisait exactement comme Humain contre Humain (pas
de repli virtuel), rendant l'écran contenant la carte « Problèmes » (donc
le mode virtuel lui-même) inaccessible sans échiquier. #364 n'avait vérifié
que le bouton DANS la carte, jamais l'entrée du menu qui y mène.

Ce fichier vérifie, sans échiquier ni Lichess réels (serveur lancé avec
ALCHESS_SKIP_BOARD=1, voir conftest.py — jamais de board_ok/board_error
réel, jeton toujours vide) :
  - l'entrée menu Lichess n'est plus conditionnée à l'échiquier (seul le
    jeton la conditionne, comme avant) ;
  - les autres entrées (Humain contre Humain) restent inchangées ;
  - à l'intérieur de l'écran Lichess sans échiquier : le mode problèmes
    « Sur l'écran » reste utilisable, le mode « Échiquier » et la partie
    Lichess réelle sont grisés avec une explication visible ;
  - ces états se mettent à jour EN DIRECT (sans recharger la page) quand
    l'échiquier se (dé)connecte pendant que l'écran reste ouvert.

États simulés en invoquant directement les callbacks socket.io déjà
enregistrés par app.js — même technique que test_issue310_lichess_e2e.py
— jamais un vrai échiquier, un vrai jeton ni une vraie partie/problème
Lichess. `page` est partagée par toute la session (conftest.py) : le vrai
gestionnaire socket.io de "config_data" est détaché pour tout ce module
(restauré à la fin) pour que la vraie réponse serveur à un "config_get"
déclenché en arrière-plan (ex. par un retour au menu) — toujours un jeton
réellement vide dans l'environnement e2e isolé — n'écrase jamais, de façon
non déterministe, le jeton SIMULÉ par ces tests. Chaque test remet l'état
simulé à sa valeur de base avant de rendre la main, pour ne pas affecter
les tests suivants.

Lancer : pytest nicsoft/tests/e2e/test_issue365_lichess_sans_echiquier_e2e.py -v
"""
import pytest

pytestmark = pytest.mark.slow


def _declencher_evenement_socket_client(page, event, data):
    """Invoque directement, côté navigateur, les callbacks déjà enregistrés
    par `socket.on(event, ...)` dans app.js — sans réseau ni serveur réel."""
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _declencher_config_data(page, data):
    """Variante dédiée à "config_data" (voir _detacher_config_data_reel) —
    invoque le VRAI gestionnaire app.js (capturé avant détachement), sans
    jamais passer par `socket.listeners()` (vidé par `socket.off`)."""
    page.evaluate(
        "([data]) => { "
        "const cbs = window.__realConfigDataHandlers365 || []; "
        "if (cbs.length === 0) throw new Error('aucun gestionnaire config_data capturé'); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [data],
    )


@pytest.fixture(scope="module", autouse=True)
def _detacher_config_data_reel(page):
    """Détache le vrai gestionnaire socket.io de "config_data" pour toute
    la durée de ce module — restauré à la fin pour les fichiers de tests
    e2e suivants, qui en ont réellement besoin (écran Paramètres, etc.)."""
    page.evaluate(
        "() => { "
        "window.__realConfigDataHandlers365 = socket.listeners('config_data').slice(); "
        "socket.off('config_data'); "
        "}"
    )
    yield
    page.evaluate(
        "() => { "
        "(window.__realConfigDataHandlers365 || []).forEach((cb) => socket.on('config_data', cb)); "
        "delete window.__realConfigDataHandlers365; "
        "}"
    )


def go_menu(page):
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _reset_base(page):
    """Revient à la base de référence de la session e2e : pas d'échiquier,
    pas de jeton, mode problème "Échiquier" (défaut) — jamais de fuite d'un
    test simulé vers le suivant. Humain contre Humain se regrise seul via
    `board_error` (mécanisme générique `_applyBoardBadge()`, issue #366)."""
    _declencher_evenement_socket_client(page, "board_error", {})
    _declencher_config_data(page, {"has_lichess_token": False})
    page.evaluate("() => { selectPuzzleModeLichess('board'); }")
    go_menu(page)


@pytest.fixture
def lichess_state(at_menu):
    go_menu(at_menu)
    yield at_menu
    _reset_base(at_menu)


# ── Entrée du menu principal ──────────────────────────────────────────────

def test_entree_lichess_active_sans_echiquier_avec_jeton(lichess_state):
    page = lichess_state
    _declencher_evenement_socket_client(page, "board_error", {})  # confirme : pas d'échiquier
    _declencher_config_data(page, {"has_lichess_token": True})
    btn = page.locator('.menu-btn-lichess[data-mode="lichess"]')
    assert not btn.is_disabled(), "l'entrée Lichess doit rester active sans échiquier dès qu'un jeton est enregistré"


def test_entree_lichess_grisee_sans_jeton_meme_echiquier_connecte(lichess_state):
    page = lichess_state
    _declencher_evenement_socket_client(page, "board_ok", {})
    _declencher_config_data(page, {"has_lichess_token": False})
    btn = page.locator('.menu-btn-lichess[data-mode="lichess"]')
    assert btn.is_disabled(), "sans jeton personnel, l'entrée Lichess doit rester grisée (comportement inchangé)"


def test_autre_entree_menu_reste_grisee_sans_echiquier(lichess_state):
    """Garde-fou de non-régression : #365 ne doit changer QUE l'entrée
    Lichess — Humain contre Humain (pas de repli virtuel) reste grisé sans
    échiquier, exactement comme avant."""
    page = lichess_state
    _declencher_evenement_socket_client(page, "board_error", {})
    btn_hh = page.locator("button.menu-btn-humain")
    assert btn_hh.is_disabled()


# ── À l'intérieur de l'écran Lichess, sans échiquier ───────────────────────

@pytest.fixture
def at_config_lichess_sans_board(lichess_state):
    page = lichess_state
    _declencher_evenement_socket_client(page, "board_error", {})
    _declencher_config_data(page, {"has_lichess_token": True})
    page.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    # Détache (une seule fois, idempotent) le vrai gestionnaire socket.io de
    # "lichess_resumable" — même procédé que test_issue310_lichess_e2e.py —
    # pour qu'une vraie réponse réseau tardive du serveur de test ne vienne
    # jamais écraser l'état simulé par ce test.
    page.evaluate(
        "() => { "
        "if (!window.__realLichessResumableHandlers) { "
        "window.__realLichessResumableHandlers = socket.listeners('lichess_resumable').slice(); "
        "socket.off('lichess_resumable'); "
        "} "
        "}"
    )
    return page


def test_probleme_sur_ecran_utilisable_et_se_lance_sans_echiquier(at_config_lichess_sans_board):
    """Le mode « Sur l'écran » reste cliquable sans échiquier et déclenche
    bien l'action de lancement attendue. Le jeton réel du serveur de test
    (ALCHESS_DIR isolé, conftest.py) reste vide — jamais un vrai jeton ni
    une vraie session de problèmes : le clic est donc intercepté AVANT
    d'atteindre le serveur (sinon celui-ci refuserait pour absence de jeton
    réel et renverrait le navigateur au menu, parasitant ce test). Le
    lancement réel côté serveur est couvert, en process, par
    test_issue364_lichess_puzzle_virtuel.py."""
    page = at_config_lichess_sans_board
    page.locator("#cfg-lichess-puzzle-mode-virtual").click()
    btn = page.locator("#btn-start-lichess-puzzle")
    assert not btn.is_disabled(), "le mode « Sur l'écran » doit rester utilisable sans échiquier"
    assert not page.locator("#lichess-puzzle-board-hint").is_visible()

    page.evaluate(
        "() => { "
        "window.__sendActionAvant365 = window.sendAction; "
        "window.__captureAction365 = null; "
        "window.sendAction = (a) => { window.__captureAction365 = a; }; "
        "}"
    )
    try:
        btn.click()
        captured = page.evaluate("() => window.__captureAction365")
    finally:
        page.evaluate(
            "() => { "
            "window.sendAction = window.__sendActionAvant365; "
            "delete window.__sendActionAvant365; delete window.__captureAction365; "
            "}"
        )
    assert captured and captured.get("type") == "start_lichess_puzzle"
    assert captured.get("puzzle_mode") == "virtual"

    # Confirme ensuite, côté client seul, que l'écran du problème s'affiche
    # bien une fois la confirmation serveur reçue (ici simulée).
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "lichess_puzzle_playing", "virtual": True,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "color": "white", "puzzle_id": "pzl-365", "rating": 1500,
    })
    page.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    assert page.locator("#screen-lichess-puzzle").is_visible()
    go_menu(page)


def test_probleme_mode_echiquier_grise_sans_echiquier_avec_explication(at_config_lichess_sans_board):
    page = at_config_lichess_sans_board
    page.locator("#cfg-lichess-puzzle-mode-board").click()
    btn = page.locator("#btn-start-lichess-puzzle")
    assert btn.is_disabled(), "le mode « Échiquier » ne doit jamais permettre de lancer un problème sans échiquier"
    hint = page.locator("#lichess-puzzle-board-hint")
    assert hint.is_visible()
    assert hint.inner_text().strip() != ""


def test_partie_lichess_reelle_grisee_sans_echiquier_avec_explication(at_config_lichess_sans_board):
    page = at_config_lichess_sans_board
    assert page.locator("#btn-start-lichess").is_disabled()
    banniere = page.locator("#board-warning-banner-config-lichess")
    assert banniere.is_visible()
    assert banniere.inner_text().strip() != ""


def test_bascule_echiquier_met_a_jour_les_boutons_sans_recharger(at_config_lichess_sans_board):
    """Cœur de la demande #365 : (dé)connecter l'échiquier pendant que
    l'écran Lichess reste ouvert met à jour l'état des boutons en direct,
    en réutilisant le mécanisme déjà en place (board_ok/board_error) —
    jamais besoin de recharger la page."""
    page = at_config_lichess_sans_board
    page.locator("#cfg-lichess-puzzle-mode-board").click()
    assert page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert page.locator("#lichess-puzzle-board-hint").is_visible()
    assert page.locator("#btn-start-lichess").is_disabled()

    _declencher_evenement_socket_client(page, "board_ok", {})
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert not page.locator("#lichess-puzzle-board-hint").is_visible()
    assert not page.locator("#btn-start-lichess").is_disabled()
    assert not page.locator("#board-warning-banner-config-lichess").is_visible()

    # Depuis #366 (partie 2), une déconnexion pendant que l'écran reste
    # ouvert bascule l'affichage sur « Sur l'écran » (préférence mémorisée
    # inchangée) : le problème reste donc jouable tout de suite, même si
    # « Échiquier » avait été sélectionné manuellement juste avant — seule
    # la partie Lichess réelle (toujours liée à l'échiquier physique) se
    # regrise.
    _declencher_evenement_socket_client(page, "board_error", {})
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert not page.locator("#lichess-puzzle-board-hint").is_visible()
    assert page.locator("#btn-start-lichess").is_disabled()
    assert page.locator("#board-warning-banner-config-lichess").is_visible()


def test_echiquier_connecte_depuis_le_debut_rien_ne_change(lichess_state):
    """Avec l'échiquier connecté dès l'ouverture de l'écran : mode
    « Échiquier » et partie réelle actifs comme avant #365."""
    page = lichess_state
    _declencher_evenement_socket_client(page, "board_ok", {})
    _declencher_config_data(page, {"has_lichess_token": True})
    page.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    page.evaluate(
        "() => { "
        "if (!window.__realLichessResumableHandlers) { "
        "window.__realLichessResumableHandlers = socket.listeners('lichess_resumable').slice(); "
        "socket.off('lichess_resumable'); "
        "} "
        "}"
    )
    page.locator("#cfg-lichess-puzzle-mode-board").click()
    assert not page.locator("#btn-start-lichess-puzzle").is_disabled()
    assert not page.locator("#lichess-puzzle-board-hint").is_visible()
    assert not page.locator("#btn-start-lichess").is_disabled()
    assert not page.locator("#board-warning-banner-config-lichess").is_visible()
    go_menu(page)
