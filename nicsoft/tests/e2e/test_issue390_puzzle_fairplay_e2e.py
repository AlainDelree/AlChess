"""
nicsoft/tests/e2e/test_issue390_puzzle_fairplay_e2e.py — AlChess

Issue #390 : garanties fair-play affichées pendant la résolution d'un
problème Lichess, vérifiées sur la page réellement rendue (jamais
seulement sur les données envoyées — un test explicite demandé par
l'énoncé). Même procédé que test_issue349_lichess_rating_e2e.py : aucune
vraie partie/problème Lichess, les événements normalement envoyés par le
serveur sont simulés en invoquant directement les callbacks déjà
enregistrées par `socket.on(...)` dans app.js.

Point 4 : seul le thème/la phase CHOISI pour la série est affiché pendant
la résolution — jamais les thèmes propres du problème reçu (un thème
contenant un mot repérable ne doit apparaître nulle part dans la page
avant la fin)."""
import pytest

pytestmark = pytest.mark.slow

FEN_PROBLEME = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 2"
MARQUEUR_THEME_INTERDIT = "MARQUEURTHEMEINTERDIT12345"


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _retour_menu(page):
    page.evaluate("() => { sendAction({type: 'back_menu'}); }")
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _lancer_probleme(page, series_theme="", series_type="mix", extra=None):
    payload = {
        "state": "lichess_puzzle_playing",
        "fen": FEN_PROBLEME, "color": "black",
        "puzzle_id": "pzl_e2e", "rating": 1766,
        "puzzle_index": 1, "puzzle_total": 5,
        "player_rating": 1680,
        "setup_fen": FEN_PROBLEME,
        "series_theme": series_theme, "series_type": series_type,
        # Jamais envoyé en vrai par le serveur pendant la résolution (voir
        # game_manager_modes/lichess.py) — injecté ici uniquement pour
        # prouver que le rendu ne s'en sert JAMAIS, même s'il était présent.
        "themes": [MARQUEUR_THEME_INTERDIT],
    }
    if extra:
        payload.update(extra)
    _declencher_evenement_socket_client(page, "app_state", payload)
    page.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    return page


def test_themes_du_probleme_jamais_visibles_pendant_la_resolution(at_menu):
    page = _lancer_probleme(at_menu, series_theme="fork", series_type="theme")
    assert MARQUEUR_THEME_INTERDIT not in page.content()
    _retour_menu(page)


def test_theme_choisi_affiche_pendant_la_resolution(at_menu):
    page = _lancer_probleme(at_menu, series_theme="fork", series_type="theme")
    label = page.locator("#lichess-puzzle-series-label").text_content()
    assert "Fork" in label  # libellé en de "fork" (langue par défaut des tests e2e), voir i18n/en.json
    assert "Theme" in label
    _retour_menu(page)


def test_phase_choisie_affichee_pendant_la_resolution(at_menu):
    page = _lancer_probleme(at_menu, series_theme="endgame", series_type="phase")
    label = page.locator("#lichess-puzzle-series-label").text_content()
    assert "Endgame" in label
    assert "Phase" in label
    _retour_menu(page)


def test_melange_naffiche_aucun_theme_ni_phase(at_menu):
    page = _lancer_probleme(at_menu, series_theme="", series_type="mix")
    label = page.locator("#lichess-puzzle-series-label").text_content()
    assert label == ""
    _retour_menu(page)


def test_theme_choisi_efface_a_la_fin_du_probleme(at_menu):
    page = _lancer_probleme(at_menu, series_theme="fork", series_type="theme")
    assert "Fork" in page.locator("#lichess-puzzle-series-label").text_content()
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": True, "themes": ["fork", "middlegame"], "rating": 1766,
        "rating_before": 1766, "rating_after": 1780, "rating_diff": 14,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": False,
    })
    assert page.locator("#lichess-puzzle-series-label").text_content() == ""
    _retour_menu(page)
