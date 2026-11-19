"""
nicsoft/tests/e2e/test_issue361_puzzle_mise_en_place_e2e.py — AlChess

Issue #361, partie 0 : pendant la mise en place d'un problème Lichess, les
cases rouges de l'écran "#screen-pos-init" doivent se mettre à jour au fil
du placement physique des pièces — avant ce correctif,
_wait_initial_position_lichess_puzzle envoyait toujours la position CIBLE
(figée) comme "fen", jamais la lecture physique courante : l'écran restait
figé avec toutes les cases rouges du départ (voir rapport de clôture #361).

Issue #362 (ce correctif) : ce test ne vérifiait QUE le nombre de cases
rouges, jamais QUELLES pièces sont dessinées — il a donc laissé passer une
régression introduite par #361 lui-même : renderBoardPosInit() dessinait
les pièces à partir de "fen" (désormais la lecture physique courante),
jamais de "expected_fen" (la cible). Résultat en réel : l'écran de mise en
place d'un problème montrait la position de départ standard rangée sur
l'échiquier physique, jamais la position du problème à atteindre. Ajouté
ici : une vérification explicite des pièces dessinées sur quelques cases
clés, à chaque étape du placement.

Même procédé que test_issue310_lichess_e2e.py : aucune vraie partie/problème
Lichess ni échiquier réel — l'événement socket "app_state" normalement
envoyé par le serveur (set_app_state) est simulé en invoquant directement
les callbacks déjà enregistrés par `socket.on(...)` dans app.js. Les
payloads eux-mêmes sont obtenus en appelant la fonction Python réelle
(_wait_initial_position_lichess_puzzle) avec un faux échiquier, plutôt
qu'écrits à la main — mêmes clés, mêmes valeurs que ce qu'émet réellement
le serveur.
"""
import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher

pytestmark = pytest.mark.slow

# Position cible ARBITRAIRE du problème simulé (après 1.e4) — volontairement
# différente de la position de départ standard, pour vérifier que le dessin
# comme la comparaison utilisent bien "expected_fen" et non la valeur par
# défaut (standard) de renderBoardPosInit.
TARGET_BOARD_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"

# Lecture physique "cas réel" (échiquier rangé par l'utilisateur à son état
# naturel de repos) : position de départ standard, strictement différente
# de la cible sur deux cases (e2, e4).
STANDARD_START_BOARD_FEN = chess.STARTING_BOARD_FEN

# Deuxième lecture physique : le coup e2-e4 a été posé, seul le cavalier g1
# manque encore à l'appel (un seul écart restant).
_READING_UN_ECART = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKB1R"


class _FakeBoardProgressif:
    """Renvoie une lecture différente à chaque appel de get_fen() — simule
    un placement de pièces progressif sur l'échiquier physique (même
    contrat que test_issue354_lichess_puzzles_l3.py::_FakeBoardProgressif)."""

    def __init__(self, readings):
        self._readings = readings
        self._i = 0

    def get_fen(self):
        fen = self._readings[min(self._i, len(self._readings) - 1)]
        self._i += 1
        return fen + " w - - 0 1"

    def turn_off_all_leds(self):
        pass

    def signal_lights(self, n):
        pass


def _payloads_reels_mise_en_place(monkeypatch):
    """Capture les payloads "position_initiale" RÉELLEMENT émis par
    _wait_initial_position_lichess_puzzle (code Python de production), au
    lieu de les écrire à la main — garantit les mêmes clés et les mêmes
    valeurs que ce que le serveur envoie réellement (issue #362)."""
    monkeypatch.setattr(lichess_launcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    sent = []
    monkeypatch.setattr(
        lichess_launcher, "set_app_state", lambda state, data=None: sent.append((state, data)),
    )
    readings = [STANDARD_START_BOARD_FEN, _READING_UN_ECART, TARGET_BOARD_FEN]
    board = _FakeBoardProgressif(readings)
    target_fen = TARGET_BOARD_FEN + " b - - 0 1"

    lichess_launcher._wait_initial_position_lichess_puzzle(board, target_fen, "white")

    payloads = [d for (state, d) in sent if state == "position_initiale"]
    # La 3e lecture (readings[2]) est déjà strictement égale à la cible :
    # la fonction retourne alors sans émettre (transition d'état directe,
    # voir test_issue354_lichess_puzzles_l3.py). Les 2 lectures en écart
    # restent seules capturées ici.
    assert len(payloads) == 2
    return payloads


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _nb_cases_rouges(page):
    return page.locator("#board-pos-init .pos-init-error").count()


def _piece_html(page, file, rank):
    """Contenu HTML de la case `pi-{file}-{rank}` (vide si aucune pièce)."""
    return page.locator(f"#pi-{file}-{rank}").inner_html().strip()


@pytest.fixture
def payloads_mise_en_place(monkeypatch):
    return _payloads_reels_mise_en_place(monkeypatch)


@pytest.fixture
def at_puzzle_mise_en_place(at_menu, payloads_mise_en_place):
    """Écran de mise en place d'un problème Lichess, avec le payload réel
    du "cas réel" décrit par l'issue #362 : échiquier physique rangé en
    position de départ standard, cible = position arbitraire du problème."""
    _declencher_evenement_socket_client(at_menu, "app_state", {
        "state": "position_initiale", **payloads_mise_en_place[0],
    })
    at_menu.wait_for_selector("#screen-pos-init", state="visible", timeout=5000)
    return at_menu, payloads_mise_en_place


def test_puzzle_mise_en_place_affiche_des_cases_rouges(at_puzzle_mise_en_place):
    """Deux cases diffèrent de la cible (e2 et e4) : les deux doivent être
    signalées en rouge."""
    page, _payloads = at_puzzle_mise_en_place
    assert _nb_cases_rouges(page) == 2


def test_puzzle_mise_en_place_dessine_la_cible_jamais_la_lecture_physique(at_puzzle_mise_en_place):
    """Cœur de la régression #362 : l'écran doit dessiner les pièces de la
    position CIBLE du problème (expected_fen), jamais la lecture physique
    courante (fen) — même quand celle-ci est la position de départ standard
    rangée par l'utilisateur (le "cas réel" signalé par Alain)."""
    page, _payloads = at_puzzle_mise_en_place
    # e4 : vide dans la lecture physique (standard), pion blanc dans la
    # cible — avant le correctif, la case restait vide à l'écran.
    assert "wP.svg" in _piece_html(page, 4, 3)
    # e2 : pion blanc dans la lecture physique (standard), vide dans la
    # cible — avant le correctif, un pion y était affiché à tort.
    assert _piece_html(page, 4, 1) == ""


def test_puzzle_mise_en_place_cases_rouges_disparaissent_au_placement(at_puzzle_mise_en_place):
    """Reproduction directe du bug #361 (cases rouges figées) combinée à la
    régression #362 (pièces dessinées) : au fur et à mesure que la lecture
    physique se rapproche de la cible, les cases rouges disparaissent ET
    les pièces dessinées restent celles de la cible à chaque étape."""
    page, payloads = at_puzzle_mise_en_place
    avant = _nb_cases_rouges(page)
    assert avant == 2

    # Le pion e2-e4 est désormais placé correctement (pièce physiquement
    # déplacée) ; le cavalier g1 reste absent de l'échiquier physique — un
    # seul écart restant, contre deux avant ce coup.
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "position_initiale", **payloads[1],
    })
    apres = _nb_cases_rouges(page)
    assert apres < avant
    assert apres == 1
    # g1 : vide dans la lecture physique à cette étape, cavalier blanc dans
    # la cible — toujours la cible qui est dessinée, pas la lecture.
    assert "wN.svg" in _piece_html(page, 6, 0)

    # Position physique désormais strictement identique à la cible — ce
    # dernier payload n'est jamais émis par le code Python réel (il
    # retourne sans émettre dès que board_fen == target, voir
    # _payloads_reels_mise_en_place ci-dessus) ; construit ici seulement
    # pour vérifier la convergence finale de l'écran vers zéro case rouge.
    _declencher_evenement_socket_client(page, "app_state", {
        "state": "position_initiale", "fen": TARGET_BOARD_FEN,
        "expected_fen": TARGET_BOARD_FEN, "color": "white", "puzzle": True,
    })
    assert _nb_cases_rouges(page) == 0
    assert "wP.svg" in _piece_html(page, 4, 3)
