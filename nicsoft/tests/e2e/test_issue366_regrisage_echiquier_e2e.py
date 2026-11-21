"""
nicsoft/tests/e2e/test_issue366_regrisage_echiquier_e2e.py — AlChess

Issue #366, partie 1 : défaut préexistant signalé par #365 (hors périmètre
à l'époque) — `board_ok` réactive génériquement tous les boutons
`[data-needs-board]`, mais `board_error`/`board_reconnecting` ne les
regrisait jamais de façon générique : seuls les deux boutons Lichess
traités par #365 (`btn-start-lichess`, `btn-start-lichess-puzzle`, via
`_applyLichessPuzzleBoardState()`) suivaient l'état de l'échiquier en
direct. Un bouton `data-needs-board` resté hors de ce traitement spécial
(ex. l'entrée menu Humain contre Humain) pouvait donc rester cliquable
après une déconnexion survenue en cours de session.

Corrigé en déplaçant la (dé)activation générique de `[data-needs-board]`
dans `_applyBoardBadge()` elle-même (appelée par les trois événements
`board_ok`/`board_error`/`board_reconnecting`) — plus de second mécanisme
ad hoc. `btn-start-hh` (bouton "Démarrer la partie" de l'écran de
configuration Humain contre Humain, jusque-là régi par un bloc dédié
distinct) porte désormais aussi `data-needs-board data-physical-only`,
unifiant les deux boutons qui exigeaient l'échiquier sur le même
mécanisme — ce qui donne un second bouton générique pour ce test, en plus
de l'entrée menu Humain contre Humain.

États simulés en invoquant directement les callbacks socket.io déjà
enregistrés par app.js (même procédé que test_issue365_lichess_sans_
echiquier_e2e.py) — jamais un vrai échiquier. Les éléments testés existent
dans le DOM même quand leur écran n'est pas affiché (`getElementById`),
donc aucune navigation d'écran n'est nécessaire ici.
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


@pytest.fixture
def board_buttons_state(at_menu):
    page = at_menu
    yield page
    # Base de référence pour les tests suivants (page partagée pour toute la
    # session e2e) : pas d'échiquier, comme au chargement initial.
    _declencher_evenement_socket_client(page, "board_error", {})


def test_connecte_puis_deconnecte_puis_reconnecte(board_buttons_state):
    """Cœur de la demande #366 : la (dé)connexion en cours de session
    regrise/réactive génériquement tous les boutons `[data-needs-board]`,
    pas seulement les deux boutons Lichess déjà traités par #365."""
    page = board_buttons_state
    btn_hh_menu  = page.locator("button.menu-btn-humain")
    btn_hh_start = page.locator("#btn-start-hh")

    # Simule aussi un écran Lichess avec jeton et mode problème "Échiquier"
    # sélectionné, sans naviguer vers l'écran (élément présent dans le DOM
    # indépendamment de l'écran affiché) — garde-fou de non-régression #365.
    page.evaluate("() => { _lichessHasToken = true; _lichessPuzzleMode = 'board'; }")
    btn_lichess_real   = page.locator("#btn-start-lichess")
    btn_lichess_puzzle = page.locator("#btn-start-lichess-puzzle")
    # L'écran Lichess n'est pas ouvert ici (aucune navigation, voir
    # docstring) : son visuel (classe "hidden" de l'explication) est déjà
    # entièrement couvert par test_issue365_lichess_sans_echiquier_e2e.py
    # en contexte réel ; on vérifie ici seulement l'état `disabled`, commun
    # aux deux mécanismes et indépendant de la visibilité de l'écran.
    hint_puzzle_board_hidden = lambda: page.evaluate(
        "() => document.getElementById('lichess-puzzle-board-hint').classList.contains('hidden')"
    )

    # Échiquier connecté : tout actif.
    _declencher_evenement_socket_client(page, "board_ok", {})
    assert not btn_hh_menu.is_disabled()
    assert not btn_hh_start.is_disabled()
    assert not btn_lichess_real.is_disabled()
    assert not btn_lichess_puzzle.is_disabled()
    assert hint_puzzle_board_hidden()

    # Déconnexion en cours de session : tout se regrise, pas seulement les
    # boutons Lichess déjà couverts par #365.
    _declencher_evenement_socket_client(page, "board_error", {})
    assert btn_hh_menu.is_disabled()
    assert btn_hh_start.is_disabled()
    assert btn_lichess_real.is_disabled()
    assert btn_lichess_puzzle.is_disabled()
    assert not hint_puzzle_board_hidden()

    # Reconnexion : tout se réactive à nouveau.
    _declencher_evenement_socket_client(page, "board_ok", {})
    assert not btn_hh_menu.is_disabled()
    assert not btn_hh_start.is_disabled()
    assert not btn_lichess_real.is_disabled()
    assert not btn_lichess_puzzle.is_disabled()
    assert hint_puzzle_board_hidden()


def test_reconnexion_perdue_board_reconnecting_regrise_aussi(board_buttons_state):
    """`board_reconnecting` (module de lecture perdu, périphérique encore
    présent, issue #314) doit regriser les boutons génériques comme
    `board_error` — l'échiquier n'est, dans les deux cas, pas utilisable."""
    page = board_buttons_state
    btn_hh_menu  = page.locator("button.menu-btn-humain")
    btn_hh_start = page.locator("#btn-start-hh")

    _declencher_evenement_socket_client(page, "board_ok", {})
    assert not btn_hh_menu.is_disabled()
    assert not btn_hh_start.is_disabled()

    _declencher_evenement_socket_client(page, "board_reconnecting", {})
    assert btn_hh_menu.is_disabled()
    assert btn_hh_start.is_disabled()
