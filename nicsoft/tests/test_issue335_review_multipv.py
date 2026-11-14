"""
nicsoft/tests/test_issue335_review_multipv.py — AlChess

Tests du calcul à la demande des 3 meilleures lignes pour l'écran
d'analyse post-partie (issue #335), sans moteur réel ni réseau — faux
moteur (FakeEngine) qui renvoie des lignes prédéfinies ou échoue sur
commande.

Couvre : mémoire des résultats déjà calculés (une position déjà calculée
n'est jamais recalculée), calcul d'avance des positions voisines
(prev_fen/next_fen), position devenue non prioritaire → résultat ignoré à
l'arrivée (mais reste en cache), absence/échec du moteur → message clair
sans exception.
"""

import threading
import time

import chess
import pytest

from nicsoft.engine.review_multipv import ReviewMultiPVService

FEN_START = chess.Board().fen()
FEN_AFTER_E4 = chess.Board().fen()


def _board_after(moves_uci):
    board = chess.Board()
    for uci in moves_uci:
        board.push_uci(uci)
    return board.fen()


FEN_A = _board_after([])              # position de départ
FEN_B = _board_after(["e2e4"])        # après 1.e4
FEN_C = _board_after(["d2d4"])        # après 1.d4


class _FakeEngine:
    """Remplace EngineManager — jamais de vrai moteur lancé."""

    def __init__(self, lines_by_fen=None, gates=None, fail_fens=None):
        self.lines_by_fen = lines_by_fen or {}
        self.gates = gates or {}       # fen -> threading.Event à attendre avant de répondre
        self.fail_fens = fail_fens or set()
        self.calls = []
        self.quit_called = False

    def get_multipv(self, board, n=3, depth=12):
        fen = board.fen()
        self.calls.append(fen)
        gate = self.gates.get(fen)
        if gate is not None:
            assert gate.wait(timeout=5), f"gate jamais libérée pour {fen}"
        if fen in self.fail_fens:
            raise RuntimeError("moteur en panne (simulé)")
        return [dict(line) for line in self.lines_by_fen.get(fen, [])]

    def quit(self):
        self.quit_called = True


def _wait_until(predicate, timeout=2.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _make_service(engine, on_result=None):
    results = []

    def _on_result(fen, result):
        results.append((fen, result))
        if on_result:
            on_result(fen, result)

    service = ReviewMultiPVService(lambda: engine, on_result=_on_result)
    return service, results


# ── Mémoire des résultats déjà calculés ──────────────────────────────────

def test_fen_deja_calculee_nest_jamais_recalculee():
    engine = _FakeEngine(lines_by_fen={FEN_A: [{"move": "e2e4", "cp": 30, "mate": None}]})
    service, results = _make_service(engine)

    cached = service.request(FEN_A)
    assert cached is None  # pas encore en cache, calcul lancé en arrière-plan

    assert _wait_until(lambda: len(results) == 1)
    assert results[0][0] == FEN_A
    assert results[0][1]["lines"][0]["move"] == "e2e4"
    assert results[0][1]["lines"][0]["san"] == "e4"

    # Reparcourir la même position (ex. retour en arrière puis en avant) :
    # retour synchrone depuis le cache, aucun second appel moteur.
    cached_again = service.request(FEN_A)
    assert cached_again is not None
    assert cached_again["lines"][0]["move"] == "e2e4"
    assert engine.calls.count(FEN_A) == 1


def test_get_cached_sans_requete_prealable_est_none():
    engine = _FakeEngine()
    service, _ = _make_service(engine)
    assert service.get_cached(FEN_A) is None


# ── Position devenue non prioritaire : résultat ignoré mais mémorisé ────

def test_resultat_ignore_si_position_changee_mais_reste_en_cache():
    gate_a = threading.Event()
    engine = _FakeEngine(
        lines_by_fen={
            FEN_A: [{"move": "e2e4", "cp": 20, "mate": None}],
            FEN_B: [{"move": "g8f6", "cp": -10, "mate": None}],
        },
        gates={FEN_A: gate_a},
    )
    service, results = _make_service(engine)

    # Demande la position A (bloquée tant que gate_a n'est pas libérée —
    # simule un calcul moteur encore en cours).
    assert service.request(FEN_A) is None
    assert _wait_until(lambda: FEN_A in engine.calls)

    # L'utilisateur change de position AVANT la fin du calcul de A.
    assert service.request(FEN_B) is None

    # Le calcul de A peut enfin se terminer.
    gate_a.set()

    # B (la position désormais affichée) reçoit bien son résultat.
    assert _wait_until(lambda: any(fen == FEN_B for fen, _ in results))

    # A s'est terminé mais n'a jamais été notifié (ignoré : plus la
    # position courante au moment où son calcul s'est terminé) — son
    # résultat reste néanmoins en cache pour un retour ultérieur.
    assert not any(fen == FEN_A for fen, _ in results)
    assert _wait_until(lambda: service.get_cached(FEN_A) is not None)
    assert service.get_cached(FEN_A)["lines"][0]["move"] == "e2e4"


# ── Calcul d'avance des positions voisines ───────────────────────────────

def test_positions_voisines_precalculees_en_arriere_plan():
    engine = _FakeEngine(
        lines_by_fen={
            FEN_A: [{"move": "e2e4", "cp": 0, "mate": None}],
            FEN_B: [{"move": "e7e5", "cp": 0, "mate": None}],
            FEN_C: [{"move": "d7d5", "cp": 0, "mate": None}],
        },
    )
    service, results = _make_service(engine)

    cached = service.request(FEN_A, neighbor_fens=[FEN_B, FEN_C])
    assert cached is None

    # A (premier plan), B et C (voisins) finissent tous par être en cache,
    # sans nouvelle demande explicite pour B/C.
    assert _wait_until(lambda: service.get_cached(FEN_A) is not None)
    assert _wait_until(lambda: service.get_cached(FEN_B) is not None)
    assert _wait_until(lambda: service.get_cached(FEN_C) is not None)

    # Revenir sur B (déjà précalculée) ne déclenche aucun second calcul.
    calls_before = engine.calls.count(FEN_B)
    assert calls_before == 1
    second = service.request(FEN_B)
    assert second is not None
    assert engine.calls.count(FEN_B) == 1


def test_voisin_fen_vide_ou_none_ignore_sans_erreur():
    engine = _FakeEngine(lines_by_fen={FEN_A: [{"move": "e2e4", "cp": 0, "mate": None}]})
    service, _ = _make_service(engine)
    # prev_fen/next_fen absents (position de départ/fin de partie) —
    # ne doit jamais planter.
    service.request(FEN_A, neighbor_fens=[None, ""])
    assert _wait_until(lambda: service.get_cached(FEN_A) is not None)


# ── Absence ou échec du moteur ────────────────────────────────────────

def test_echec_moteur_donne_un_resultat_clair_sans_exception():
    engine = _FakeEngine(fail_fens={FEN_A})
    service, results = _make_service(engine)

    assert service.request(FEN_A) is None
    assert _wait_until(lambda: len(results) == 1)
    fen, result = results[0]
    assert fen == FEN_A
    assert result["lines"] == []
    assert "error" in result

    # Pas de nouvelle tentative moteur sur une position déjà en échec.
    cached = service.request(FEN_A)
    assert cached is not None
    assert cached["lines"] == []
    assert engine.calls.count(FEN_A) == 1


def test_moteur_absent_a_la_construction_ne_plante_pas():
    def _engine_factory_qui_echoue():
        raise RuntimeError("stockfish introuvable")

    results = []
    service = ReviewMultiPVService(
        _engine_factory_qui_echoue,
        on_result=lambda fen, result: results.append((fen, result)),
    )

    assert service.request(FEN_A) is None
    assert _wait_until(lambda: len(results) == 1)
    fen, result = results[0]
    assert fen == FEN_A
    assert result["lines"] == []
    assert "error" in result


def test_fen_invalide_ne_plante_pas():
    engine = _FakeEngine()
    service, results = _make_service(engine)
    assert service.request("ceci n'est pas un FEN") is None
    assert _wait_until(lambda: len(results) == 1)
    _, result = results[0]
    assert result["lines"] == []
    assert "error" in result
    assert not engine.calls  # jamais atteint get_multipv


# ── Arrêt propre ──────────────────────────────────────────────────────

def test_stop_ferme_le_moteur_et_arrete_le_fil():
    engine = _FakeEngine(lines_by_fen={FEN_A: [{"move": "e2e4", "cp": 0, "mate": None}]})
    service, results = _make_service(engine)
    service.request(FEN_A)
    assert _wait_until(lambda: len(results) == 1)
    service.stop()
    assert engine.quit_called
