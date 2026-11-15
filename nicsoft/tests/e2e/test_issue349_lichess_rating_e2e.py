"""
nicsoft/tests/e2e/test_issue349_lichess_rating_e2e.py — AlChess

Issue #349, partie 1 : affichage de la cote de l'utilisateur (comme celle
de l'adversaire déjà existante), cote provisoire (point d'interrogation,
comme lichess.org), absence de cote, cotes dans l'écran « Révision PGN »
(en-têtes WhiteElo/BlackElo, bon ordre selon l'orientation de l'échiquier),
et nouvelle cote affichée en fin de partie classée.

Même procédé que test_issue316_lichess_e2e.py / test_issue345_analyse_
lichess_fixes_e2e.py : aucune vraie partie Lichess, les événements socket
normalement envoyés par le serveur sont simulés en invoquant directement
les callbacks déjà enregistrées par `socket.on(...)` dans app.js.
"""
import pytest

pytestmark = pytest.mark.slow

FEN_DEPART = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _top_bottom_names(page):
    return page.evaluate(
        """() => ({
            top: document.getElementById('player-top-name').textContent,
            bottom: document.getElementById('player-bottom-name').textContent,
        })"""
    )


def _retour_menu(page):
    # sendAction direct (comme test_issue340_lichess_opponent_signal_e2e.py)
    # plutôt qu'un clic sur un bouton — ces tests laissent la page sur
    # l'écran de jeu (#screen-game), jamais sur le panneau de fin de partie
    # (#panel-gameover), donc aucun bouton "back_menu" n'y est visible.
    page.evaluate("() => { sendAction({type: 'back_menu'}); }")
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _lichess_init(page, color, user_rating=None, user_provisional=False,
                   opponent_rating=None, opponent_provisional=False,
                   opponent_name="Adversaire", rated=True):
    _declencher_evenement_socket_client(page, "app_state", {"state": "playing"})
    page.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(page, "lichess_init", {
        "fen": FEN_DEPART, "color": color, "level": 1, "player": "Testeur e2e",
        "opponent_name": opponent_name, "opponent_rating": opponent_rating,
        "opponent_provisional": opponent_provisional, "opponent_is_ai": False,
        "user_rating": user_rating, "user_provisional": user_provisional,
        "rated": rated,
    })
    return page


# ── Ma cote affichée, comme celle de l'adversaire — deux orientations ─────

@pytest.mark.parametrize("color", ["white", "black"])
def test_ma_cote_et_celle_de_ladversaire_affichees(at_menu, color):
    page = _lichess_init(
        at_menu, color, user_rating=1400, opponent_rating=1500, opponent_name="tomatoloss",
    )
    noms = _top_bottom_names(page)
    # haut = adversaire, bas = utilisateur, quelle que soit la couleur
    # jouée (convention #315/#327, inchangée par cette issue).
    assert noms["top"] == "tomatoloss (1500)"
    assert noms["bottom"] == "Testeur e2e (1400)"
    _retour_menu(page)


def test_cote_provisoire_affichee_avec_point_dinterrogation(at_menu):
    page = _lichess_init(
        at_menu, "white", user_rating=900, user_provisional=True,
        opponent_rating=1500, opponent_provisional=True, opponent_name="tomatoloss",
    )
    noms = _top_bottom_names(page)
    assert noms["top"] == "tomatoloss (1500?)"
    assert noms["bottom"] == "Testeur e2e (900?)"
    _retour_menu(page)


def test_cote_absente_aucune_parenthese(at_menu):
    page = _lichess_init(at_menu, "white", opponent_name="tomatoloss")
    noms = _top_bottom_names(page)
    assert noms["top"] == "tomatoloss"
    assert noms["bottom"] == "Testeur e2e"
    _retour_menu(page)


# ── Révision PGN : WhiteElo/BlackElo affichés, bon ordre selon orientation ──

_PGN_AVEC_COTES = (
    '[White "tomatoloss"]\n[Black "Vous"]\n[WhiteElo "1500"]\n[BlackElo "1400"]\n'
    '[Result "0-1"]\n\n1. e4 e5 2. Qh5 Ke7 0-1'
)


def _charger_pgn_colle(page, pgn):
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def _reset_orientation(page):
    page.evaluate("() => { if (_boardFlipped) { flipBoard(); } }")


def test_revision_pgn_affiche_les_cotes_whiteelo_blackelo(at_menu):
    page = at_menu
    _reset_orientation(page)
    _charger_pgn_colle(page, _PGN_AVEC_COTES)
    noms = _top_bottom_names(page)
    # Non retourné par défaut : haut=Noir, bas=Blanc (convention #345,
    # inchangée par cette issue) — ici Blanc="tomatoloss" (1500),
    # Noir="Vous" (1400).
    assert noms == {"top": "Vous (1400)", "bottom": "tomatoloss (1500)"}
    _retour_menu(page)


def test_revision_pgn_cotes_suivent_lorientation_retournee(at_menu):
    page = at_menu
    _reset_orientation(page)
    _charger_pgn_colle(page, _PGN_AVEC_COTES)
    page.locator("button[data-action=\"flip_board\"]").click()
    page.evaluate("(pgn) => parsePgn(pgn)", _PGN_AVEC_COTES)
    noms = _top_bottom_names(page)
    assert noms == {"top": "tomatoloss (1500)", "bottom": "Vous (1400)"}
    _reset_orientation(page)
    _retour_menu(page)


# ── Nouvelle cote en fin de partie classée ─────────────────────────────────
# Le badge classée/amicale + nouvelle cote (_lichessRatedInfo) est peuplé
# par le handler socket.on("app_state") pour state="game_over" (c'est aussi
# cet évènement qui affiche #panel-gameover — voir app.js) ; le "game_over"
# émis séparément par le serveur ne fait que renseigner l'historique/les
# bannières, jamais ce badge.

def _game_over_classee(page):
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "game_over", "source": "lichess", "rated": True,
        "title": "Victoire", "result": "1-0",
    })
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)


def test_nouvelle_cote_affichee_en_fin_de_partie_classee(at_menu):
    page = _lichess_init(at_menu, "white", user_rating=1400, opponent_rating=1500, rated=True)
    _game_over_classee(page)
    el = page.locator("#rv-lichess-rated-info")
    assert el.is_visible()
    _declencher_evenement_socket_client(page, "lichess_new_rating", {
        "new_rating": 1413, "rating_diff": 13,
    })
    assert "1413" in el.text_content()
    assert "+13" in el.text_content()
    _retour_menu(page)


def test_nouvelle_cote_absente_rien_dinvente(at_menu):
    """Si Lichess ne fournit jamais la nouvelle cote (événement jamais
    reçu), seul le badge classée/amicale reste affiché — jamais de valeur
    inventée."""
    page = _lichess_init(at_menu, "white", user_rating=1400, opponent_rating=1500, rated=True)
    _game_over_classee(page)
    el = page.locator("#rv-lichess-rated-info")
    text = el.text_content()
    assert "1413" not in text
    assert "nouvelle" not in text.lower()
    _retour_menu(page)
