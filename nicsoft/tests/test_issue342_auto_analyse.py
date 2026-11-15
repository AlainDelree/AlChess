"""
nicsoft/tests/test_issue342_auto_analyse.py — AlChess

Issue #342 : l'écran d'analyse après partie lance désormais l'analyse
complète d'office (plus de bouton « Analyser la partie ») — ces tests
couvrent la partie serveur/moteur, sans jamais lancer de vrai moteur
(faux EngineManager injecté) ni ouvrir de navigateur :

  - le garde-fou explicite qui refuse toute demande d'analyse hors de
    l'état serveur `game_over` — notamment le cas demandé par l'issue,
    point 4 : une partie Lichess EN COURS, qui partage le même état
    `_app_state == "playing"` que les autres modes (aucun état dédié) ;
  - le chemin normal (happy path), avec jeton de génération repris tel
    quel dans les événements émis ;
  - l'arrêt propre en cours de route (should_continue), le moteur bien
    fermé (quit()), et l'absence d'« analyse_terminee » pour une analyse
    interrompue (jamais enregistrée comme complète) ;
  - la priorité cédée au service de lignes à la demande (#335) quand une
    requête y est en attente ;
  - l'arrêt précoce de EngineManager.analyser_partie via `should_continue`
    (nicsoft/engine/engine_analysis.py).
"""
import threading

import pytest

from nicsoft.engine.engine_analysis import EngineAnalysisMixin
from nicsoft.web import server


# ── Fixtures communes ───────────────────────────────────────────────────────

class _FakeEngineManager:
    """Remplace EngineManager — jamais de vrai process moteur. Enregistre
    ses appels pour les assertions ; chaque coup est classé "bon" par
    défaut (délai nul : la version de test n'a pas besoin d'observer un
    vrai temps de calcul)."""
    instances = []

    def __init__(self, engine_path, engine_elo=1500, analyse_active=True):
        self.engine_path = engine_path
        self.engine_elo = engine_elo
        self.quit_called = False
        self.moves_seen = []
        _FakeEngineManager.instances.append(self)

    def analyser_partie(self, moves_uci, callback=None, seq_moves=3, should_continue=None):
        resultats = []
        for idx, uci in enumerate(moves_uci):
            if should_continue is not None and not should_continue():
                break
            self.moves_seen.append(uci)
            res = {
                "qualite": "bon", "delta_cp": 0, "best_move": None,
                "punishment_line": [], "fen_avant_coup": "",
            }
            resultats.append(res)
            if callback:
                callback(idx, len(moves_uci), res)
        return resultats

    def quit(self):
        self.quit_called = True


class _ImmediateThread:
    """Remplace threading.Thread — exécute la cible tout de suite, dans le
    fil du test, pour pouvoir asserter juste après l'appel sans course."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch, tmp_path):
    _FakeEngineManager.instances.clear()
    monkeypatch.setattr(server, "_analyse_cancel_event", None)
    monkeypatch.setattr(server, "SKIP_AUTO_ANALYSE", False)
    monkeypatch.setattr(server, "_app_state", "game_over")
    monkeypatch.setattr(server, "_review_multipv_service", None)
    # DATA_DIR non isolé par le conftest commun (il lit de vraies données
    # utilisateur pour d'autres tests) — ici on force un dossier vide pour
    # qu'aucun vrai config.json ne soit lu pendant ce test.
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(threading, "Thread", _ImmediateThread)
    import nicsoft.engine.engine_manager as engine_manager_module
    monkeypatch.setattr(engine_manager_module, "EngineManager", _FakeEngineManager)
    monkeypatch.setattr(engine_manager_module, "find_stockfish", lambda: "stockfish-factice")
    yield


def _emitted(monkeypatch):
    """Capture tous les socketio.emit() faits pendant le test."""
    events = []
    monkeypatch.setattr(server.socketio, "emit", lambda name, data=None: events.append((name, data)))
    return events


# ── Point 4 : jamais pendant une partie Lichess en cours ───────────────────

def test_analyser_pgn_refuse_si_partie_lichess_en_cours(monkeypatch):
    """Lichess utilise le même état serveur générique "playing" que les
    autres modes (aucun état dédié, voir nicsoft/core/game_manager_modes/
    lichess.py) — simuler une partie Lichess en cours revient donc à
    simuler _app_state="playing". Aucune analyse ne doit être demandée au
    moteur dans ce cas (issue #342, point 4 / #333)."""
    monkeypatch.setattr(server, "_app_state", "playing")
    events = _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4", "e7e5"], "gen": 1})

    assert _FakeEngineManager.instances == []
    assert events == []


@pytest.mark.parametrize("state", ["menu", "connecting", "paused", "config_lichess"])
def test_analyser_pgn_refuse_hors_ecran_analyse(monkeypatch, state):
    monkeypatch.setattr(server, "_app_state", state)
    events = _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4"], "gen": 1})

    assert _FakeEngineManager.instances == []
    assert events == []


def test_analyser_pgn_ignore_si_skip_auto_analyse(monkeypatch):
    """Garde-fou dédié au serveur de test e2e (nicsoft/tests/e2e/conftest.py)
    — vérifie que le drapeau coupe bien tout avant même la construction du
    moteur."""
    monkeypatch.setattr(server, "SKIP_AUTO_ANALYSE", True)
    events = _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4", "e7e5"], "gen": 1})

    assert _FakeEngineManager.instances == []
    assert events == []


# ── Chemin normal ───────────────────────────────────────────────────────────

def test_analyser_pgn_chemin_normal_emet_coup_puis_termine(monkeypatch):
    events = _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4", "e7e5", "g1f3"], "seq_moves": 4, "gen": 7})

    assert len(_FakeEngineManager.instances) == 1
    manager = _FakeEngineManager.instances[0]
    assert manager.moves_seen == ["e2e4", "e7e5", "g1f3"]
    assert manager.quit_called is True

    noms = [e[0] for e in events]
    assert noms.count("analyse_coup") == 3
    assert noms[-1] == "analyse_terminee"
    # Le jeton de génération envoyé par le client est repris tel quel —
    # permet au client d'ignorer un résultat tardif d'une autre partie
    # (leçon #338).
    assert all(data["gen"] == 7 for (name, data) in events)
    assert events[-1][1]["total"] == 3


def test_analyser_pgn_relit_engine_path_et_elo_depuis_config(monkeypatch, tmp_path):
    import json
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"engine_path": "/opt/stockfish-alain", "engine_elo": 2200}), encoding="utf-8")
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4"], "gen": 1})

    assert _FakeEngineManager.instances[0].engine_path == "/opt/stockfish-alain"
    assert _FakeEngineManager.instances[0].engine_elo == 2200


# ── Point 5 : arrêt propre, jamais une analyse partielle marquée complète ──

def test_annulation_arrete_avant_la_fin_et_ferme_le_moteur(monkeypatch):
    """Le faux moteur annule lui-même après le premier coup — simule un
    changement de partie/retour au menu pendant l'analyse (sendAction côté
    client -> annuler_analyse_pgn)."""

    class _CancellingEngineManager(_FakeEngineManager):
        def analyser_partie(self, moves_uci, callback=None, seq_moves=3, should_continue=None):
            resultats = []
            for idx, uci in enumerate(moves_uci):
                if should_continue is not None and not should_continue():
                    break
                if idx == 0:
                    # Simule l'annulation déclenchée par le client pendant
                    # le calcul du premier coup.
                    server.on_annuler_analyse_pgn({})
                self.moves_seen.append(uci)
                res = {"qualite": "bon", "delta_cp": 0, "best_move": None,
                       "punishment_line": [], "fen_avant_coup": ""}
                resultats.append(res)
                if callback:
                    callback(idx, len(moves_uci), res)
            return resultats

    import nicsoft.engine.engine_manager as engine_manager_module
    monkeypatch.setattr(engine_manager_module, "EngineManager", _CancellingEngineManager)
    events = _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4", "e7e5", "g1f3", "b8c6"], "gen": 3})

    manager = _FakeEngineManager.instances[0]
    # Un seul coup traité (le deuxième aurait dû être bloqué par should_continue).
    assert manager.moves_seen == ["e2e4"]
    assert manager.quit_called is True
    noms = [e[0] for e in events]
    assert "analyse_terminee" not in noms, (
        "une analyse interrompue ne doit jamais être annoncée comme terminée"
    )


def test_annuler_sans_analyse_en_cours_ne_fait_rien(monkeypatch):
    # Pas d'exception si "Vider l'analyse" ou le retour au menu annule alors
    # qu'aucune analyse n'est en cours (ex. partie déjà analysée).
    server.on_annuler_analyse_pgn({})


def test_nouvelle_analyse_annule_la_precedente_pour_une_autre_partie(monkeypatch):
    """Changer de partie pendant une analyse en cours doit arrêter la
    première avant de démarrer la seconde — reproduit ce que fait le
    client (_reviewMaybeAutoAnalyse) en appelant on_analyser_pgn deux fois
    de suite sans passer par annuler_analyse_pgn explicitement (cas où le
    thread précédent est encore considéré actif côté serveur)."""
    _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4"], "gen": 1})
    # Le thread tourne de façon synchrone ici (fixture _ImmediateThread) et
    # se termine sans annulation : _analyse_cancel_event est donc déjà remis
    # à None par le "finally" — on le réarme manuellement pour simuler un
    # thread encore réellement actif (cas réel) au moment du second appel.
    monkeypatch.setattr(server, "_analyse_cancel_event", threading.Event())
    ancien_event = server._analyse_cancel_event

    server.on_analyser_pgn({"moves": ["d2d4"], "gen": 2})

    assert ancien_event.is_set(), "l'analyse précédente doit être annulée avant que la nouvelle démarre"


# ── Point 6 : cohabitation avec les lignes à la demande (#335) ────────────

def test_cede_la_priorite_si_une_ligne_a_la_demande_est_en_attente(monkeypatch):
    import time as time_module

    class _FakeReviewService:
        def __init__(self):
            self.calls = 0

        def has_pending(self):
            self.calls += 1
            return self.calls == 1  # en attente seulement pour le premier coup

    fake_service = _FakeReviewService()
    monkeypatch.setattr(server, "_review_multipv_service", fake_service)
    sleeps = []
    monkeypatch.setattr(time_module, "sleep", lambda s: sleeps.append(s))
    _emitted(monkeypatch)

    server.on_analyser_pgn({"moves": ["e2e4", "e7e5"], "gen": 1})

    assert sleeps == [0.2], (
        "une courte pause coopérative doit céder la priorité au service de "
        "lignes à la demande, une seule fois ici (en attente seulement au premier coup)"
    )


def test_review_lines_pending_ne_construit_jamais_le_service(monkeypatch):
    """Ne doit jamais déclencher la construction paresseuse du moteur du
    service de lignes à la demande comme effet de bord."""
    monkeypatch.setattr(server, "_review_multipv_service", None)
    assert server._review_lines_pending() is False


# ── should_continue dans EngineAnalysisMixin.analyser_partie ───────────────

class _FakeAnalyser(EngineAnalysisMixin):
    def evaluate_move(self, board, move, depth=8):
        return ("bon", 0, None)

    def get_punishment_line(self, board, move, depth=12, max_moves=3):
        return []


def test_analyser_partie_should_continue_arrete_avant_le_coup():
    analyser = _FakeAnalyser()
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    vus = []

    def should_continue():
        return len(vus) < 2

    def callback(idx, total, res):
        vus.append(idx)

    resultats = analyser.analyser_partie(moves, callback=callback, should_continue=should_continue)

    assert vus == [0, 1]
    assert len(resultats) == 2


def test_analyser_partie_sans_should_continue_va_jusqu_au_bout():
    analyser = _FakeAnalyser()
    moves = ["e2e4", "e7e5", "g1f3"]
    resultats = analyser.analyser_partie(moves)
    assert len(resultats) == 3
