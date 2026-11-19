"""
nicsoft/tests/e2e/test_issue363_puzzle_fin_e2e.py — AlChess

Issue #363, partie 2 : après un problème raté puis « Voir la solution »,
rien n'indiquait que le problème était terminé une fois la solution
démontrée — l'écran gardait le titre « Problème raté » et masquait
seulement le bouton de solution, sans aucun signal de fin distinct.

Comportement constaté par lecture du code avant correctif (voir rapport de
clôture) : `puzzle_game.py::_show_solution()` rejoue chaque coup de la
solution un par un, en ATTENDANT sa réplication physique sur l'échiquier
avant de passer au suivant (`_wait_for_board_fen`, même mécanique qu'un
coup adverse de partie) — ce n'est donc pas un simple affichage. Une fois
la boucle terminée (dernier coup physiquement reproduit),
`_wait_post_result_decision()` émet déjà un second évènement
`lichess_puzzle_result` (avec `can_view_solution` retombé à False) — rien
n'était donc à ajouter côté serveur ni côté envoi à Lichess (déjà fait une
seule fois par `_try_submit_pending()` lors du premier `_finish()`) :
seul le texte affiché côté client manquait d'un signal de fin explicite.

Correctif : un bandeau `#lichess-puzzle-end-banner`, dérivé uniquement de
`data.win`/`data.can_view_solution` du payload déjà reçu — "Problème
terminé" pour les cas résolu et raté (pas encore vu la solution), "Solution
terminée" une fois la solution entièrement rejouée (can_view_solution
retombé à False sans victoire). Ce test couvre les 3 cas, sans vraie
partie/problème Lichess ni échiquier réel — évènements socket simulés
(même procédé que test_issue361_puzzle_camp_e2e.py).
"""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

I18N_DIR = Path(__file__).resolve().parents[2] / "web" / "static" / "i18n"

FEN_DEPART = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


def _i18n_values(cle):
    valeurs = set()
    for lang in ("fr", "en", "de"):
        data = json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        if cle in data:
            valeurs.add(data[cle])
    return valeurs


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _end_banner_text(page):
    return page.locator("#lichess-puzzle-end-banner").text_content()


@pytest.fixture
def at_puzzle_playing(at_menu):
    _declencher_evenement_socket_client(at_menu, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": FEN_DEPART, "color": "white", "puzzle_id": "pzl1", "rating": 1500,
    })
    at_menu.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    return at_menu


def test_probleme_resolu_indique_la_fin(at_puzzle_playing):
    """Cas 1 — résolu : le bandeau de fin apparaît, texte "Problème
    terminé" (jamais "Solution terminée", il n'y a pas eu de solution à
    démontrer)."""
    page = at_puzzle_playing
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": True, "themes": ["fork"], "rating": 1500,
        "rating_before": 1500, "rating_after": 1504, "rating_diff": 4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": False,
    })
    page.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    assert _end_banner_text(page) in _i18n_values("lichess.puzzle.termine")
    # Le bouton "Problème suivant" reste disponible dans tous les cas.
    assert page.locator("[data-action='lichess_puzzle_next']").is_visible()


def test_probleme_rate_sans_solution_indique_la_fin(at_puzzle_playing):
    """Cas 2 — raté, solution pas encore demandée : déjà terminé (plus
    aucun coup attendu du joueur pour ce problème) — même texte "Problème
    terminé", bien que le bouton "Voir la solution" reste proposé."""
    page = at_puzzle_playing
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": False, "themes": [], "rating": 1500,
        "rating_before": 1500, "rating_after": 1496, "rating_diff": -4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": True,
    })
    page.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    assert _end_banner_text(page) in _i18n_values("lichess.puzzle.termine")
    assert page.locator("#lichess-puzzle-btn-solution").is_visible()
    assert page.locator("[data-action='lichess_puzzle_next']").is_visible()


def test_probleme_rate_puis_solution_montree_indique_la_fin_distincte(at_puzzle_playing):
    """Cas 3 — raté puis « Voir la solution » entièrement rejouée (dernier
    coup reproduit physiquement, voir _show_solution côté serveur) :
    bandeau distinct "Solution terminée", bouton de solution disparu,
    "Problème suivant" toujours disponible — reproduction directe du
    manque signalé par Alain (l'écran restait sur "Problème raté" sans
    aucun signal de fin après la démonstration)."""
    page = at_puzzle_playing
    # Premier résultat : raté, solution pas encore vue.
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": False, "themes": [], "rating": 1500,
        "rating_before": 1500, "rating_after": 1496, "rating_diff": -4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": True,
    })
    page.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    assert _end_banner_text(page) in _i18n_values("lichess.puzzle.termine")

    # Coup(s) de la solution rejoués sur l'échiquier physique (simulation du
    # rejeu coup par coup avec réplication attendue, voir _show_solution).
    _declencher_evenement_socket_client(page, "lichess_puzzle_solution_move", {
        "fen": FEN_DEPART, "san": "Qh5", "uci": "d1h5", "color": "white", "done": True,
    })
    assert page.locator("#lichess-puzzle-solution-banner").is_visible()

    # Dernier coup physiquement reproduit : le serveur réémet le résultat,
    # cette fois can_view_solution=False (solution entièrement rejouée).
    _declencher_evenement_socket_client(page, "lichess_puzzle_result", {
        "win": False, "themes": [], "rating": 1500,
        "rating_before": 1500, "rating_after": 1496, "rating_diff": -4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": False,
    })
    assert _end_banner_text(page) in _i18n_values("lichess.puzzle.solution_terminee")
    assert not page.locator("#lichess-puzzle-btn-solution").is_visible()
    assert not page.locator("#lichess-puzzle-solution-banner").is_visible()
    assert page.locator("[data-action='lichess_puzzle_next']").is_visible()
