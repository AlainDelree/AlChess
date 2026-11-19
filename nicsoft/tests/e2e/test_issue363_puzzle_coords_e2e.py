"""
nicsoft/tests/e2e/test_issue363_puzzle_coords_e2e.py — AlChess

Issue #363, partie 1 : les échiquiers du mode problèmes Lichess (mise en
place #board-pos-init, problème en cours/écran de fin #board-lichess-
puzzle) n'affichaient aucune coordonnée (lettres de colonnes, numéros de
rangées) — repéré en réel par Alain après #361/#362, qui a placé ses
pièces en miroir sans s'en rendre compte quand il avait les Noirs
(échiquier retourné).

Correctif : même mécanisme que les coordonnées existantes (#coord-rank/
#coord-file du jeu normal, .coord-rank/.coord-file des exercices/labo) —
étiquettes a-h / 1-8 en marge, orientées comme l'échiquier (camp du
joueur en bas). Ce test vérifie le TEXTE et l'ORDRE de ces étiquettes
pour un problème aux Blancs et un problème aux Noirs, à la mise en place
et pendant le problème — aucune vraie partie/problème Lichess ni
échiquier réel : évènements socket simulés (même procédé que
test_issue361_puzzle_board_e2e.py).
"""
import pytest

pytestmark = pytest.mark.slow

FEN_APRES_PREMIER_COUP = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _textes(page, selector):
    return page.locator(f"{selector} span").all_text_contents()


@pytest.fixture
def at_puzzle_flow(at_menu):
    return at_menu


@pytest.mark.parametrize("color", ["white", "black"])
def test_mise_en_place_coordonnees_orientation(at_puzzle_flow, color):
    """Mise en place d'un problème : les coordonnées suivent l'orientation
    du camp du joueur — Blancs en bas (a..h de gauche à droite, 1..8 de
    bas en haut) ou Noirs en bas (ordre inverse)."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "position_initiale",
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
        "expected_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR",
        "color": color, "puzzle": True,
    })
    at_puzzle_flow.wait_for_selector("#screen-pos-init", state="visible", timeout=5000)
    at_puzzle_flow.wait_for_selector("#pi-coord-rank", state="visible", timeout=5000)

    ranks = _textes(at_puzzle_flow, "#pi-coord-rank")
    files = _textes(at_puzzle_flow, "#pi-coord-file")
    if color == "white":
        assert ranks == ["8", "7", "6", "5", "4", "3", "2", "1"]
        assert files == ["a", "b", "c", "d", "e", "f", "g", "h"]
    else:
        assert ranks == ["1", "2", "3", "4", "5", "6", "7", "8"]
        assert files == ["h", "g", "f", "e", "d", "c", "b", "a"]


def test_mise_en_place_coordonnees_masquees_hors_puzzle(at_puzzle_flow):
    """L'écran de mise en place est partagé avec les autres modes (#315) —
    les coordonnées ne doivent jamais apparaître quand data.puzzle est
    absent/faux (ne pas toucher les échiquiers des autres modes)."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "position_initiale",
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
        "color": "white",
    })
    at_puzzle_flow.wait_for_selector("#screen-pos-init", state="visible", timeout=5000)
    assert not at_puzzle_flow.locator("#pi-coord-rank").is_visible()
    assert not at_puzzle_flow.locator("#pi-coord-file").is_visible()


@pytest.mark.parametrize("color", ["white", "black"])
def test_puzzle_en_cours_coordonnees_orientation(at_puzzle_flow, color):
    """Problème en cours : mêmes vérifications sur l'échiquier
    #board-lichess-puzzle (préfixe de cellule "lp")."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": FEN_APRES_PREMIER_COUP, "color": color,
        "puzzle_id": "pzl1", "rating": 1500,
    })
    at_puzzle_flow.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)

    ranks = _textes(at_puzzle_flow, "#lp-coord-rank")
    files = _textes(at_puzzle_flow, "#lp-coord-file")
    if color == "white":
        assert ranks == ["8", "7", "6", "5", "4", "3", "2", "1"]
        assert files == ["a", "b", "c", "d", "e", "f", "g", "h"]
    else:
        assert ranks == ["1", "2", "3", "4", "5", "6", "7", "8"]
        assert files == ["h", "g", "f", "e", "d", "c", "b", "a"]


def test_puzzle_ecran_de_fin_coordonnees_toujours_visibles(at_puzzle_flow):
    """L'écran de fin est le même écran que le problème en cours (#board-
    lichess-puzzle inchangé) — les coordonnées doivent y rester visibles."""
    _declencher_evenement_socket_client(at_puzzle_flow, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": FEN_APRES_PREMIER_COUP, "color": "black",
        "puzzle_id": "pzl1", "rating": 1500,
    })
    at_puzzle_flow.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    _declencher_evenement_socket_client(at_puzzle_flow, "lichess_puzzle_result", {
        "win": True, "themes": ["fork"], "rating": 1500,
        "rating_before": 1500, "rating_after": 1504, "rating_diff": 4,
        "submit_pending": False, "submit_error_key": None, "can_view_solution": False,
    })
    at_puzzle_flow.wait_for_selector("#lichess-puzzle-result", state="visible", timeout=5000)
    assert at_puzzle_flow.locator("#lp-coord-rank").is_visible()
    assert _textes(at_puzzle_flow, "#lp-coord-rank") == ["1", "2", "3", "4", "5", "6", "7", "8"]
