"""
nicsoft/tests/e2e/test_issue393_point1_lichess_dashboard_indisponible_e2e.py
— AlChess

Issue #393, point 1 (suite de l'étude #391) : l'écran de réglages des
problèmes Lichess annotait TOUS les thèmes "jamais joué" quand le tableau
de bord était simplement indisponible (jeton absent, réseau coupé, droit
manquant) — jamais distingué d'un thème réellement jamais joué sur la
période (`available: true, themes: {}`). Ce fichier vérifie, sur l'écran
réel, que les deux cas produisent des libellés DIFFÉRENTS et qu'aucun
thème par défaut n'est appliqué dans le cas indisponible — même procédé
de détachement des évènements réels que test_issue389_puzzle_theme_sort_e2e.py."""
import pytest

pytestmark = pytest.mark.slow


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const attaches = socket.listeners(event) || []; "
        "const cbs = attaches.length ? attaches : (window['__real393_' + event] || []); "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


@pytest.fixture(scope="module", autouse=True)
def _detacher_dashboard_et_config_data_reels(page):
    page.evaluate(
        "() => { "
        "['lichess_puzzle_dashboard', 'config_data'].forEach((ev) => { "
        "window['__real393_' + ev] = socket.listeners(ev).slice(); "
        "socket.off(ev); "
        "}); "
        "}"
    )
    yield
    page.evaluate(
        "() => { "
        "['lichess_puzzle_dashboard', 'config_data'].forEach((ev) => { "
        "(window['__real393_' + ev] || []).forEach((cb) => socket.on(ev, cb)); "
        "delete window['__real393_' + ev]; "
        "}); "
        "}"
    )


def go_menu(page):
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


@pytest.fixture
def at_config_lichess(at_menu):
    page = at_menu
    page.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    _declencher_evenement_socket_client(page, "config_data", {
        "lichess_puzzle_series_mode": "mix", "lichess_puzzle_theme": "", "lichess_puzzle_phase": "middlegame",
    })
    yield page
    go_menu(page)


def _option_texts(page):
    return page.eval_on_selector_all(
        "#cfg-lichess-puzzle-theme option", "opts => opts.map(o => o.textContent)"
    )


def _hint_hidden(page):
    return page.eval_on_selector(
        "#cfg-lichess-puzzle-stats-indisponibles", "(el) => el.classList.contains('hidden')"
    )


def test_tableau_de_bord_indisponible_aucun_jamais_joue_mention_visible(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": False, "themes": {}, "default_theme": "",
    })
    texts = _option_texts(page)
    assert texts, "la liste reste complète et utilisable"
    label_fork = page.evaluate("() => t('lichess.puzzle_theme.fork')")
    jamais_joue_fork = page.evaluate(
        "(label) => t('lichess.puzzle.stat_jamais_joue', {label})", label_fork,
    )
    # Aucune option n'affiche l'annotation "jamais joué" quand le tableau
    # de bord est indisponible — seulement le libellé nu du thème.
    assert jamais_joue_fork not in texts
    assert label_fork in texts
    assert not _hint_hidden(page)  # mention "indisponible" affichée


def test_tableau_de_bord_disponible_mais_vide_annote_jamais_joue(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": True, "themes": {}, "default_theme": "",
    })
    texts = _option_texts(page)
    assert texts
    label_fork = page.evaluate("() => t('lichess.puzzle_theme.fork')")
    expected = page.evaluate(
        "(label) => t('lichess.puzzle.stat_jamais_joue', {label})", label_fork,
    )
    assert expected in texts
    assert _hint_hidden(page)  # mention masquée : le tableau de bord a bien répondu


def test_indisponible_et_disponible_vide_donnent_des_libelles_differents(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": False, "themes": {}, "default_theme": "",
    })
    textes_indisponible = set(_option_texts(page))

    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": True, "themes": {}, "default_theme": "",
    })
    textes_disponible_vide = set(_option_texts(page))

    assert textes_indisponible != textes_disponible_vide


def test_theme_par_defaut_jamais_applique_si_indisponible(at_config_lichess):
    page = at_config_lichess
    page.eval_on_selector("#cfg-lichess-puzzle-theme", "(sel) => { sel.value = ''; }")
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": False, "themes": {}, "default_theme": "fork",  # ne devrait jamais être calculé par le serveur
    })
    selected = page.eval_on_selector("#cfg-lichess-puzzle-theme", "sel => sel.value")
    # Même si (par hypothèse d'école) un default_theme non-vide arrivait
    # avec available=false, _lichessPuzzleApplyThemeSelection ne doit pas
    # l'appliquer : seule une valeur déjà mémorisée compte.
    assert selected != "fork"
