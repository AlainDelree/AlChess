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


# ── Point 5 : bande des résultats de la série ───────────────────────────

def _pills(page, selector="#lichess-puzzle-series-strip .lichess-puzzle-pill"):
    return page.locator(selector)


def test_pastille_orange_pour_le_probleme_en_cours(at_menu):
    page = _lancer_probleme(at_menu, extra={"puzzle_index": 1, "puzzle_total": 3})
    pills = _pills(page)
    assert pills.count() == 1
    assert "lichess-puzzle-pill-current" in pills.first.get_attribute("class")
    _retour_menu(page)


def test_pastille_devient_verte_avec_variation_apres_reussite(at_menu):
    page = _lancer_probleme(at_menu, extra={"puzzle_index": 1, "puzzle_total": 3})
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": True, "themes": [], "rating": 1766, "rating_before": 1766,
        "rating_after": 1780, "rating_diff": 14, "submit_pending": False,
        "submit_error_key": None, "can_view_solution": False,
    })
    pill = _pills(page).first
    assert "lichess-puzzle-pill-solved" in pill.get_attribute("class")
    assert pill.text_content() == "+14"
    assert "Solved" in pill.get_attribute("title")
    _retour_menu(page)


def test_pastille_devient_rouge_avec_variation_apres_echec(at_menu):
    page = _lancer_probleme(at_menu, extra={"puzzle_index": 1, "puzzle_total": 3})
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": False, "themes": [], "rating": 1766, "rating_before": 1766,
        "rating_after": 1754, "rating_diff": -12, "submit_pending": False,
        "submit_error_key": None, "can_view_solution": False,
    })
    pill = _pills(page).first
    assert "lichess-puzzle-pill-failed" in pill.get_attribute("class")
    assert pill.text_content() == "-12"
    assert "Failed" in pill.get_attribute("title")
    _retour_menu(page)


def test_bande_se_vide_au_debut_d_une_nouvelle_seance(at_menu):
    page = _lancer_probleme(at_menu, extra={"puzzle_index": 1, "puzzle_total": 2})
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": True, "themes": [], "rating": 1766, "rating_before": 1766,
        "rating_after": 1780, "rating_diff": 14, "submit_pending": False,
        "submit_error_key": None, "can_view_solution": False,
    })
    page = _lancer_probleme(page, extra={"puzzle_index": 2, "puzzle_total": 2})
    assert _pills(page).count() == 2  # problème 1 (vert) + problème 2 (orange, en cours)
    # Nouvelle séance : puzzle_index revient à 1 -> la bande repart à zéro.
    page = _lancer_probleme(page, extra={"puzzle_index": 1, "puzzle_total": 5})
    assert _pills(page).count() == 1
    _retour_menu(page)


def test_bande_reutilisee_dans_le_bilan(at_menu):
    page = _lancer_probleme(at_menu, extra={"puzzle_index": 1, "puzzle_total": 1})
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": True, "themes": [], "rating": 1766, "rating_before": 1766,
        "rating_after": 1780, "rating_diff": 14, "submit_pending": False,
        "submit_error_key": None, "can_view_solution": False,
    })
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "lichess_puzzle_session_summary",
        "completed": 1, "solved": 1, "failed": 0, "avg_duration_s": 12.0,
        "rating_diff_total": 14, "failed_puzzles": [], "series_angle": "",
    })
    page.wait_for_selector("#screen-lichess-puzzle-summary", state="visible", timeout=5000)
    summary_pills = _pills(page, "#lichess-puzzle-summary-strip .lichess-puzzle-pill")
    assert summary_pills.count() == 1
    assert "lichess-puzzle-pill-solved" in summary_pills.first.get_attribute("class")
    page.evaluate("() => { sendAction({type: 'back_menu'}); }")
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)
