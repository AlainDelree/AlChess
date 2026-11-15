"""
nicsoft/engine/review_multipv.py — AlChess

Calcul à la demande des N meilleures lignes moteur pour l'écran d'analyse
post-partie (issue #335). Objectifs : ne jamais bloquer l'interface,
mémoriser les résultats par FEN (reparcourir les coups ne recalcule rien),
traiter la position affichée en priorité et précalculer les positions
voisines (coup précédent/suivant) en arrière-plan.

Reste hors du mode Lichess (jamais importé par nicsoft/modes/lichess/* ni
nicsoft/core/game_manager_modes/lichess.py — voir
test_issue333_lichess_no_engine.py, qui interdit ce module explicitement) :
l'écran d'analyse post-partie est un écran commun qui ne s'ouvre qu'une
fois la partie terminée, jamais pendant une partie Lichess en cours.
"""

import logging
import threading
from collections import deque

import chess

logger = logging.getLogger("ReviewMultiPV")

# Nombre de lignes et profondeur alignés sur get_multipv()/get_punishment_line()
# (nicsoft/engine/engine_analysis.py, déjà utilisés par l'écran d'analyse) —
# pas de nouveau réglage utilisateur.
N_LINES = 3
DEPTH = 12


class ReviewMultiPVService:
    """
    engine_factory() -> objet exposant get_multipv(board, n, depth) et
    quit() (typiquement un EngineManager) — construit à la demande au
    premier calcul, un seul moteur réutilisé ensuite pour tous les calculs.

    on_result(fen, result) est appelé depuis le fil de calcul interne,
    seulement quand `fen` est encore la position "au premier plan" au
    moment où le calcul se termine (voir `request()`) — un changement de
    position pendant le calcul ne l'annule pas réellement (python-chess
    n'offre pas d'interruption propre d'une analyse en cours) mais son
    résultat est alors ignoré plutôt qu'affiché, et reste en cache pour un
    retour ultérieur sur cette position.
    """

    def __init__(self, engine_factory, on_result=None):
        self._engine_factory = engine_factory
        self._on_result = on_result
        self._engine = None
        self._cv = threading.Condition()
        self._queue = deque()      # fens en attente de calcul
        self._queued = set()       # anti-doublon dans _queue
        self._cache = {}           # fen -> résultat ({"lines": [...]} ou {"lines": [], "error": str})
        self._current_fen = None   # dernière position demandée au premier plan
        self._worker = None
        self._stopped = False

    # -- API publique --------------------------------------------------

    def request(self, fen, neighbor_fens=()):
        """
        Demande le calcul de `fen` en priorité et précalcule en
        arrière-plan les positions de `neighbor_fens` (typiquement le coup
        précédent et le coup suivant de l'écran d'analyse).

        Retourne le résultat immédiatement s'il est déjà en cache (aucun
        recalcul), sinon None — le résultat arrivera plus tard via
        `on_result`, seulement s'il concerne encore la position "au
        premier plan" à ce moment.
        """
        with self._cv:
            self._current_fen = fen
            cached = self._cache.get(fen)
            if cached is None and fen not in self._queued:
                self._queue.appendleft(fen)
                self._queued.add(fen)
            for nf in neighbor_fens:
                if nf and nf not in self._cache and nf not in self._queued:
                    self._queue.append(nf)
                    self._queued.add(nf)
            self._cv.notify_all()
            self._ensure_worker()
            return cached

    def get_cached(self, fen):
        with self._cv:
            return self._cache.get(fen)

    def stop(self):
        """Arrête le fil de calcul et ferme le moteur. Non appelé
        automatiquement — le service vit tant que le processus serveur vit,
        comme les autres instances EngineManager (Labo, Pédagogique)."""
        with self._cv:
            self._stopped = True
            self._cv.notify_all()
        if self._worker is not None:
            self._worker.join(timeout=2)
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception as e:
                logger.debug(f"Fermeture moteur review_multipv : {e}")
            self._engine = None

    # -- Interne ---------------------------------------------------------

    def _ensure_worker(self):
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def _run(self):
        while True:
            with self._cv:
                while not self._queue and not self._stopped:
                    self._cv.wait()
                if self._stopped:
                    return
                fen = self._queue.popleft()
                self._queued.discard(fen)
            result = self._compute(fen)
            with self._cv:
                self._cache[fen] = result
                is_current = (fen == self._current_fen)
            if is_current and self._on_result:
                try:
                    self._on_result(fen, result)
                except Exception as e:
                    logger.error(f"Erreur callback review_multipv : {e}")

    def _compute(self, fen):
        try:
            board = chess.Board(fen)
        except Exception as e:
            logger.warning(f"FEN invalide pour review_multipv : {e}")
            return {"lines": [], "error": str(e)}
        try:
            engine = self._ensure_engine()
        except Exception as e:
            logger.error(f"Moteur indisponible pour review_multipv : {e}")
            return {"lines": [], "error": str(e)}
        try:
            lines = engine.get_multipv(board, n=N_LINES, depth=DEPTH)
        except Exception as e:
            logger.error(f"Erreur get_multipv (review_multipv) : {e}")
            return {"lines": [], "error": str(e)}
        # Garde-fou (issue #338) : si un coup renvoyé par le moteur n'est
        # pas jouable par le camp au trait dans la position affichée (FEN
        # erroné en amont, position voisine mélangée...), ne tracer AUCUNE
        # flèche de meilleur coup plutôt que des flèches fausses — jamais
        # un sous-ensemble partiel, qui laisserait croire que le reste est
        # fiable.
        for line in lines:
            try:
                move = chess.Move.from_uci(line["move"])
            except Exception:
                move = None
            if move is None or move not in board.legal_moves:
                logger.warning(
                    f"review_multipv : coup {line.get('move')} illégal pour le "
                    f"camp au trait de {fen} — flèches des meilleurs coups ignorées."
                )
                return {"lines": [], "error": "coup illégal pour la position affichée"}
        for line in lines:
            try:
                line["san"] = board.san(chess.Move.from_uci(line["move"]))
            except Exception:
                line["san"] = line["move"]
        return {"lines": lines}

    def _ensure_engine(self):
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine
