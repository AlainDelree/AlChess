"""
nicsoft/tests/e2e/test_issue390_puzzle_labels_e2e.py — AlChess

Issue #390, point 8 : libellés des boutons selon la taille de séance
réglée (écran de réglages) et selon la position dans la séance (panneau
de problème, "Voir le bilan" seulement au dernier problème d'une séance
bornée). Même procédé que les autres tests e2e Lichess : pas de vrai
jeton, pas de vraie partie/problème — seul le vrai écran de réglages est
atteint par navigation réelle (`sendAction({type:'mode', value:'lichess'})`,
comme test_issue365_lichess_sans_echiquier_e2e.py) ; le panneau de
problème est simulé par invocation directe des callbacks `socket.on(...)`
(comme test_issue390_puzzle_fairplay_e2e.py)."""
import pytest

pytestmark = pytest.mark.slow

FEN_PROBLEME = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 2"


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


def _aller_a_config_lichess(page):
    page.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    return page


# ── Libellé du bouton de lancement, selon la taille de séance ──────────

def test_libelle_bouton_lancement_un_problème(at_menu):
    page = _aller_a_config_lichess(at_menu)
    page.locator("#cfg-lichess-puzzle-session-size").fill("1")
    assert page.locator("#btn-start-lichess-puzzle").text_content() == "▶ Play a puzzle"
    _retour_menu(page)


def test_libelle_bouton_lancement_serie_de_n(at_menu):
    page = _aller_a_config_lichess(at_menu)
    page.locator("#cfg-lichess-puzzle-session-size").fill("12")
    assert page.locator("#btn-start-lichess-puzzle").text_content() == "▶ Start the series of 12 puzzles"
    # Mise à jour immédiate à un nouveau changement, sans quitter l'écran.
    page.locator("#cfg-lichess-puzzle-session-size").fill("3")
    assert page.locator("#btn-start-lichess-puzzle").text_content() == "▶ Start the series of 3 puzzles"
    _retour_menu(page)


def test_libelle_bouton_lancement_sans_limite(at_menu):
    page = _aller_a_config_lichess(at_menu)
    page.locator("#cfg-lichess-puzzle-session-size").fill("0")
    assert page.locator("#btn-start-lichess-puzzle").text_content() == "▶ Play puzzles (no limit)"
    _retour_menu(page)


def test_libelle_bouton_lancement_valeur_vide_replie_sur_25(at_menu):
    page = _aller_a_config_lichess(at_menu)
    page.locator("#cfg-lichess-puzzle-session-size").fill("")
    assert page.locator("#btn-start-lichess-puzzle").text_content() == "▶ Start the series of 25 puzzles"
    _retour_menu(page)


def test_libelle_bouton_lancement_valeur_invalide_replie_sur_25(at_menu):
    page = _aller_a_config_lichess(at_menu)
    page.evaluate(
        "() => { const el = document.getElementById('cfg-lichess-puzzle-session-size'); "
        "el.value = 'abc'; el.dispatchEvent(new Event('input')); }"
    )
    assert page.locator("#btn-start-lichess-puzzle").text_content() == "▶ Start the series of 25 puzzles"
    _retour_menu(page)


def test_texte_aide_probleme_ne_mentionne_plus_angle_par_defaut(at_menu):
    page = _aller_a_config_lichess(at_menu)
    desc = page.locator("p.outil-desc").filter(has_text="Lichess puzzles").first.text_content()
    assert "default angle" not in desc
    _retour_menu(page)


# ── Libellé "Voir le bilan" seulement au dernier problème d'une séance bornée ─

def _lancer_probleme(page, puzzle_index, puzzle_total):
    payload = {
        "state": "lichess_puzzle_playing",
        "fen": FEN_PROBLEME, "color": "black",
        "puzzle_id": "pzl_e2e_label", "puzzle_index": puzzle_index, "puzzle_total": puzzle_total,
        "setup_fen": FEN_PROBLEME, "series_theme": "", "series_type": "mix",
    }
    _declencher_evenement_socket_client(page, "app_state", payload)
    page.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    return page


def _terminer_probleme(page, win=True):
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": win, "themes": [], "rating": 1500, "rating_before": 1500,
        "rating_after": 1500, "rating_diff": 0, "submit_pending": False,
        "submit_error_key": None, "can_view_solution": False,
    })
    return page


def test_voir_le_bilan_seulement_au_dernier_probleme_d_une_serie_bornee(at_menu):
    page = _lancer_probleme(at_menu, puzzle_index=2, puzzle_total=5)
    _terminer_probleme(page)
    assert page.locator("#lichess-puzzle-btn-next").text_content() == "▶ Next puzzle"
    _retour_menu(page)

    page = _lancer_probleme(page, puzzle_index=5, puzzle_total=5)
    _terminer_probleme(page)
    assert page.locator("#lichess-puzzle-btn-next").text_content() == "🏁 View summary"
    _retour_menu(page)


def test_voir_le_bilan_jamais_affiche_pour_une_seance_sans_limite(at_menu):
    page = _lancer_probleme(at_menu, puzzle_index=5, puzzle_total=0)
    _terminer_probleme(page)
    assert page.locator("#lichess-puzzle-btn-next").text_content() == "▶ Next puzzle"
    _retour_menu(page)
