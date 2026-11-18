"""
nicsoft/tests/e2e/test_issue361_puzzle_camp_e2e.py — AlChess

Issue #361, partie 2 : le panneau du problème Lichess affichait « À vous
de jouer — Noirs » alors que le joueur avait les Blancs. Cause : le
gestionnaire socket.on("lichess_puzzle_move", ...) (app.js) recalculait
#lichess-puzzle-turn-text à partir de `data.color`, qui désigne le camp
qui vient de JOUER ce coup précis (ex. l'adversaire pour son premier coup
forcé) — pas le camp fixe du joueur. Dès que ce coup s'affichait (juste
après le démarrage), l'étiquette basculait donc sur le camp adverse. Le
camp du joueur ne doit plus être recalculé que par l'évènement app_state
(lichess_puzzle_playing), qui l'envoie correctement une fois pour toutes.

Même procédé que les autres tests e2e de ce fichier (#361, parties 0/1) :
aucune vraie partie/problème Lichess, évènements socket simulés en
invoquant directement les callbacks déjà enregistrés par `socket.on(...)`.
"""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

I18N_DIR = Path(__file__).resolve().parents[2] / "web" / "static" / "i18n"


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


def _turn_text(page):
    return page.locator("#lichess-puzzle-turn-text").text_content()


def test_camp_blancs_reste_affiche_apres_le_coup_adverse(at_menu):
    """Joueur aux Blancs : le panneau annonce « Blancs » dès le démarrage,
    et le reste après l'affichage du premier coup adverse (joué par les
    Noirs) — reproduction directe du bug #361."""
    _declencher_evenement_socket_client(at_menu, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        "color": "white", "puzzle_id": "pzl1", "rating": 1500,
    })
    at_menu.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    assert _turn_text(at_menu) in _i18n_values("lichess.puzzle.a_vous_de_jouer_blancs")

    # Premier coup adverse (Noir) affiché — data.color="black" désigne le
    # camp qui VIENT DE JOUER, jamais le camp du joueur.
    _declencher_evenement_socket_client(at_menu, "lichess_puzzle_move", {
        "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        "uci": "e7e5", "color": "black",
    })
    assert _turn_text(at_menu) in _i18n_values("lichess.puzzle.a_vous_de_jouer_blancs")


def test_camp_noirs_reste_affiche_apres_le_coup_adverse(at_menu):
    """Inverse : joueur aux Noirs, premier coup adverse joué par les
    Blancs (data.color="white") — l'étiquette doit rester « Noirs »."""
    _declencher_evenement_socket_client(at_menu, "app_state", {
        "state": "lichess_puzzle_playing",
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        "color": "black", "puzzle_id": "pzl2", "rating": 1500,
    })
    at_menu.wait_for_selector("#screen-lichess-puzzle", state="visible", timeout=5000)
    assert _turn_text(at_menu) in _i18n_values("lichess.puzzle.a_vous_de_jouer_noirs")

    _declencher_evenement_socket_client(at_menu, "lichess_puzzle_move", {
        "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        "uci": "e2e4", "color": "white",
    })
    assert _turn_text(at_menu) in _i18n_values("lichess.puzzle.a_vous_de_jouer_noirs")
