"""
nicsoft/tests/e2e/test_issue342_auto_analyse_e2e.py — AlChess

Issue #342 : l'écran d'analyse après partie lance désormais l'analyse
complète d'office — plus de bouton « Analyser la partie ». Même chemin que
test_issue335_review_arrows_e2e.py / test_issue338_review_same_position_e2e.py
pour atteindre l'écran de revue sans échiquier : menu "Analyse" → "Coller
PGN".

Le serveur de test (nicsoft/tests/e2e/conftest.py) tourne avec
ALCHESS_SKIP_AUTO_ANALYSE=1 : il répond toujours sainement à une demande
"analyser_pgn" (elle est ignorée, voir server.py::on_analyser_pgn) mais ne
démarre JAMAIS de vrai moteur — ce fichier teste donc exclusivement le
comportement CÔTÉ CLIENT (déclenchement automatique, anti-relance,
annulation, progression, activation des couleurs/du bouton meilleur coup),
en simulant les réponses serveur avec le même procédé que #338/#341 :
`socket.listeners(event).forEach(h => h(data))`, jamais une requête réelle
au moteur.
"""
import pytest

pytestmark = pytest.mark.slow

# 4 coups, sans aucun commentaire — partie jamais analysée.
_PGN = "1. e4 e5 2. Nf3 Nc6"

# Même partie, mais entièrement annotée comme déjà analysée (un commentaire
# avec "cp" sur chaque coup) — ne doit jamais relancer l'analyse.
_PGN_DEJA_ANALYSE = (
    "1. e4 { ✓ 0cp } e5 { ✓ 0cp } 2. Nf3 { ✓ 0cp } Nc6 { ✓ 0cp }"
)


def _charger_pgn_colle(page, pgn):
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def _retour_menu(page):
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _progress_state(page):
    return page.evaluate(
        """() => ({
            width: document.getElementById('review-analyse-progress-bar').style.width,
            text:  document.getElementById('review-analyse-progress-text').textContent,
        })"""
    )


def _simulate_analyse_coup(page, index, total, gen, qualite="bon", best_move=None):
    page.evaluate(
        """(data) => { socket.listeners('analyse_coup').forEach(h => h(data)); }""",
        {
            "index": index, "total": total, "qualite": qualite, "delta_cp": 0,
            "best_move": best_move, "punishment_line": [], "fen_avant_coup": "",
            "gen": gen,
        },
    )


def _simulate_analyse_terminee(page, total, gen):
    page.evaluate(
        """(data) => { socket.listeners('analyse_terminee').forEach(h => h(data)); }""",
        {"total": total, "gen": gen},
    )


# ── Bouton supprimé ─────────────────────────────────────────────────────────

def test_bouton_analyser_absent_de_linterface(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    assert at_menu.locator("#btn-analyser").count() == 0
    _retour_menu(at_menu)


# ── Lancement automatique ────────────────────────────────────────────────────

def test_lancement_automatique_sur_partie_collee(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    actif = at_menu.evaluate("() => _analyseActive")
    assert actif is True
    moves = at_menu.evaluate("() => reviewMoves.map(m => m.uci)")
    assert len(moves) == 4
    _retour_menu(at_menu)


def test_pas_de_relance_si_partie_deja_analysee(at_menu):
    _charger_pgn_colle(at_menu, _PGN_DEJA_ANALYSE)
    actif = at_menu.evaluate("() => _analyseActive")
    deja = at_menu.evaluate("() => _isAnalysed")
    assert deja is True
    assert actif is False
    _retour_menu(at_menu)


# ── Point 4 : jamais PENDANT une partie Lichess, mais oui après (#345) ──────

def test_demarre_juste_apres_fin_de_partie_lichess(at_menu):
    """Issue #345 : avant ce correctif, l'écran d'analyse passait
    `data.source === "lichess"` comme `skip` à _reviewMaybeAutoAnalyse(),
    ce qui désactivait l'analyse automatique même une fois la partie
    terminée (régression). La règle de fair-play (#333) n'interdit un
    moteur que PENDANT une partie Lichess en cours — jamais atteinte ici,
    cet écran n'existant que depuis l'état serveur "game_over" (garde
    explicite côté serveur, voir test_issue342_auto_analyse.py::
    test_analyser_pgn_refuse_si_partie_lichess_en_cours). Une fois la
    partie terminée, l'analyse doit démarrer d'office comme pour toute
    autre source."""
    at_menu.evaluate("() => { _gameMode = 'lichess'; }")
    at_menu.evaluate(
        """(data) => { socket.listeners('app_state').forEach(h => h(data)); }""",
        {
            "state": "game_over", "source": "lichess",
            "history_fen": [
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            ],
            "history_moves": [{"san": "e4", "uci": "e2e4", "color": "white", "qualite": None}],
        },
    )
    actif = at_menu.evaluate("() => _analyseActive")
    assert actif is True
    at_menu.evaluate("() => { _gameMode = ''; }")
    _retour_menu(at_menu)


# ── Progression, coloration, bouton "Voir le meilleur coup" ────────────────

def test_progression_puis_terminee_et_activation_couleurs(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    gen = at_menu.evaluate("() => _analyseGen")

    etat0 = _progress_state(at_menu)
    assert etat0["width"] == "0%"

    _simulate_analyse_coup(at_menu, 0, 4, gen, qualite="bon")
    etat1 = _progress_state(at_menu)
    assert etat1["width"] == "25%"

    # Coup d'indice 1 (Nf3 ... en fait reviewMoves[1] ici = e5 côté Noir) —
    # marqué "blunder" avec un meilleur coup différent pour vérifier la
    # coloration ET l'activation de "Voir le meilleur coup".
    _simulate_analyse_coup(at_menu, 1, 4, gen, qualite="blunder", best_move="e7e6")
    _simulate_analyse_coup(at_menu, 2, 4, gen, qualite="bon")
    _simulate_analyse_coup(at_menu, 3, 4, gen, qualite="bon")
    _simulate_analyse_terminee(at_menu, 4, gen)

    etat_final = _progress_state(at_menu)
    assert etat_final["width"] == "100%"
    assert at_menu.evaluate("() => _isAnalysed") is True

    # Naviguer sur le coup marqué "blunder" (reviewIdx=2 affiche le coup
    # d'indice 1) et vérifier l'activation du bouton "Voir le meilleur coup".
    at_menu.evaluate("() => { reviewIdx = 2; renderReview(); }")
    btn = at_menu.locator("#btn-review-best")
    assert btn.is_enabled()

    _retour_menu(at_menu)


# ── Résultat tardif d'une autre partie ignoré (#338) ───────────────────────

def test_resultat_tardif_dune_autre_partie_est_ignore(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    ancien_gen = at_menu.evaluate("() => _analyseGen")

    # Changement de partie pendant l'analyse : un nouveau PGN est chargé —
    # le jeton de génération doit changer.
    at_menu.evaluate(
        """(pgn) => parsePgn(pgn)""",
        "1. d4 d5 2. c4 c6",
    )
    nouveau_gen = at_menu.evaluate("() => _analyseGen")
    assert nouveau_gen != ancien_gen

    etat_avant = _progress_state(at_menu)
    # Résultat tardif de l'ANCIENNE analyse (ancien_gen) — doit être ignoré.
    _simulate_analyse_coup(at_menu, 0, 4, ancien_gen, qualite="blunder")
    etat_apres = _progress_state(at_menu)
    assert etat_apres == etat_avant

    _retour_menu(at_menu)


# ── Arrêt propre : changement de partie et retour au menu ──────────────────

def test_changement_de_partie_annule_lanalyse_precedente(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    cle_avant = at_menu.evaluate("() => _analyseInProgressKey")
    assert cle_avant is not None

    at_menu.evaluate("""(pgn) => parsePgn(pgn)""", "1. d4 d5 2. c4 c6")
    cle_apres = at_menu.evaluate("() => _analyseInProgressKey")
    assert cle_apres != cle_avant
    assert at_menu.evaluate("() => _analyseActive") is True

    _retour_menu(at_menu)


def test_retour_menu_arrete_lanalyse_en_cours(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    assert at_menu.evaluate("() => _analyseActive") is True

    _retour_menu(at_menu)

    assert at_menu.evaluate("() => _analyseActive") is False
    assert at_menu.evaluate("() => _analyseInProgressKey") is None


# ── "Vider l'analyse" : fonctionne, ne relance jamais en boucle ───────────

def test_vider_analyse_fonctionne_et_ne_relance_pas(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    gen_avant = at_menu.evaluate("() => _analyseGen")

    at_menu.locator("button[data-action=\"vider_analyse\"]").click()

    assert at_menu.evaluate("() => reviewMoves.length") == 0
    assert at_menu.evaluate("() => _analyseActive") is False
    # Aucune nouvelle analyse n'a été déclenchée par le vidage lui-même.
    assert at_menu.evaluate("() => _analyseGen") == gen_avant

    _retour_menu(at_menu)
