"""
nicsoft/tests/e2e/test_issue393_point5_lichess_compteurs_jour_e2e.py —
AlChess

Issue #393, point 5 : les compteurs du jour de l'écran de réglages des
problèmes Lichess étaient présentés en phrases longues et peu lisibles
("Thème : 2 réalisés — 1 réussis, 1 ratés. (3 restants pour atteindre
5)"), avec un accord toujours au pluriel même pour "1 restant". Remplacé
par un petit tableau (une ligne par type, colonnes Réalisés/Réussis/
Ratés/Reste) — ce fichier vérifie sa structure réelle, l'absence de la
colonne Reste quand la taille de séance est 0, et les accords."""
import pytest

pytestmark = pytest.mark.slow


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const attaches = socket.listeners(event) || []; "
        "const cbs = attaches.length ? attaches : (window['__real393p5_' + event] || []); "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


@pytest.fixture(scope="module", autouse=True)
def _detacher_evenements_reels(page):
    events = ["lichess_puzzle_daily_counts", "lichess_puzzle_dashboard", "config_data"]
    page.evaluate(
        "(events) => { events.forEach((ev) => { "
        "window['__real393p5_' + ev] = socket.listeners(ev).slice(); "
        "socket.off(ev); "
        "}); }",
        events,
    )
    yield
    page.evaluate(
        "(events) => { events.forEach((ev) => { "
        "(window['__real393p5_' + ev] || []).forEach((cb) => socket.on(ev, cb)); "
        "delete window['__real393p5_' + ev]; "
        "}); }",
        events,
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
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": False, "themes": {}, "default_theme": "",
    })
    yield page
    go_menu(page)


_COUNTS = {
    "theme": {"done": 2, "solved": 1, "failed": 1},
    "phase": {"done": 0, "solved": 0, "failed": 0},
    "mix": {"done": 4, "solved": 3, "failed": 1},
}


def _set_session_size(page, size):
    page.eval_on_selector(
        "#cfg-lichess-puzzle-session-size", "(el, v) => { el.value = v; }", size,
    )
    page.evaluate("() => _lichessPuzzleOnSessionSizeInput()")


def test_structure_une_ligne_par_type_et_colonnes_attendues(at_config_lichess):
    page = at_config_lichess
    _set_session_size(page, 5)
    _declencher_evenement_socket_client(page, "lichess_puzzle_daily_counts", _COUNTS)

    for row_id in ("lichess-puzzle-daily-counts-theme", "lichess-puzzle-daily-counts-phase", "lichess-puzzle-daily-counts-mix"):
        assert page.locator(f"#{row_id}").count() == 1

    theme_done = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='done']", "el => el.textContent"
    )
    theme_solved = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='solved']", "el => el.textContent"
    )
    theme_failed = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='failed']", "el => el.textContent"
    )
    assert (theme_done, theme_solved, theme_failed) == ("2", "1", "1")
    # Valeurs insérées comme texte uniquement.
    inner_html = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='done']", "el => el.innerHTML"
    )
    assert inner_html == "2"


def test_colonne_reste_absente_quand_taille_zero(at_config_lichess):
    page = at_config_lichess
    _set_session_size(page, 0)
    _declencher_evenement_socket_client(page, "lichess_puzzle_daily_counts", _COUNTS)
    table_classes = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-table", "el => el.className"
    )
    assert "lichess-puzzle-daily-counts-no-reste" in table_classes
    reste_header_visible = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-table thead th:last-child",
        "el => getComputedStyle(el).display !== 'none'",
    )
    assert reste_header_visible is False


def test_colonne_reste_presente_quand_taille_reglee(at_config_lichess):
    page = at_config_lichess
    _set_session_size(page, 5)
    _declencher_evenement_socket_client(page, "lichess_puzzle_daily_counts", _COUNTS)
    table_classes = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-table", "el => el.className"
    )
    assert "lichess-puzzle-daily-counts-no-reste" not in table_classes
    reste_theme = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='reste']", "el => el.textContent"
    )
    assert reste_theme == "3"  # 5 - 2 déjà réalisés


def test_serie_selectionnee_mise_en_valeur(at_config_lichess):
    page = at_config_lichess
    _set_session_size(page, 5)
    _declencher_evenement_socket_client(page, "lichess_puzzle_daily_counts", _COUNTS)
    page.evaluate("() => selectPuzzleSeriesModeLichess('phase')")
    assert "selected" in page.eval_on_selector(
        "#lichess-puzzle-daily-counts-phase", "el => el.className"
    )
    assert "selected" not in page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme", "el => el.className"
    )


def test_accord_singulier_pour_un_seul_restant(at_config_lichess):
    page = at_config_lichess
    _set_session_size(page, 3)  # mix : done=4 >= 3 -> reste = 0 ; theme : done=2 -> reste=1
    _declencher_evenement_socket_client(page, "lichess_puzzle_daily_counts", _COUNTS)
    reste_theme = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='reste']", "el => el.textContent"
    )
    assert reste_theme == "1"
    titre = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='reste']", "el => el.title"
    )
    attendu_singulier = page.evaluate(
        "() => t('config.lichess.probleme_compteur_reste_titre_un', {reste: 1, taille: 3})"
    )
    assert titre == attendu_singulier


def test_accord_pluriel_pour_plusieurs_ou_zero_restants(at_config_lichess):
    page = at_config_lichess
    _set_session_size(page, 3)
    _declencher_evenement_socket_client(page, "lichess_puzzle_daily_counts", _COUNTS)
    titre_mix = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-mix [data-field='reste']", "el => el.title"
    )
    attendu_pluriel_zero = page.evaluate(
        "() => t('config.lichess.probleme_compteur_reste_titre', {reste: 0, taille: 3})"
    )
    assert titre_mix == attendu_pluriel_zero

    _set_session_size(page, 10)  # theme : done=2 -> reste=8 (pluriel)
    _declencher_evenement_socket_client(page, "lichess_puzzle_daily_counts", _COUNTS)
    titre_theme = page.eval_on_selector(
        "#lichess-puzzle-daily-counts-theme [data-field='reste']", "el => el.title"
    )
    attendu_pluriel_huit = page.evaluate(
        "() => t('config.lichess.probleme_compteur_reste_titre', {reste: 8, taille: 10})"
    )
    assert titre_theme == attendu_pluriel_huit
