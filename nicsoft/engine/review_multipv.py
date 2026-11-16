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

Issue #341 — évaluation point de vue Blancs + barre d'évaluation :
`EngineAnalysisMixin.get_multipv()` (nicsoft/engine/engine_analysis.py)
renvoie `cp`/`mate` relatifs au camp AU TRAIT dans la position analysée
(`score.pov(board.turn)`), jamais absolus. `_compute()` les reconvertit
ici en point de vue des Blancs — seule convention utilisée ensuite par la
légende et la barre — et calcule en plus un texte lisible (`score_text`,
"#N"/"-#N" pour un mat, jamais converti en centipions) et une fraction de
barre (`bar_fraction`, 0..1, part des Blancs) à partir de la meilleure
ligne. Position terminale (mat/pat/nulle automatique) : détectée via
`board.outcome()` avant tout appel moteur — jamais un calcul moteur pour
une position sans coup légal.
"""

import logging
import math
import threading
from collections import deque

import chess

logger = logging.getLogger("ReviewMultiPV")

# Nombre de lignes et profondeur alignés sur get_multipv()/get_punishment_line()
# (nicsoft/engine/engine_analysis.py, déjà utilisés par l'écran d'analyse) —
# pas de nouveau réglage utilisateur.
N_LINES = 3
DEPTH = 12

# Barre d'évaluation (issue #341) : mêmes constantes que la barre déjà
# existante de l'écran Labo (`laboUpdateEvalBar()`, nicsoft/web/static/app.js)
# — plafond à 10 pions, courbe sigmoïde — pour une seule convention visuelle
# dans toute l'application, même si cette barre-ci est calculée côté Python
# (testable sans navigateur) plutôt que côté JS comme celle du Labo.
EVAL_BAR_CAP_PAWNS = 10.0
_EVAL_BAR_SLOPE = 0.004
MATE_SYMBOL = "#"


def _pov_vers_blancs(cp, mate, white_to_move):
    """Reconvertit cp/mate (relatifs au camp au trait) en point de vue des
    Blancs — positif = avantage Blancs, négatif = avantage Noirs."""
    if white_to_move:
        return cp, mate
    return (None if cp is None else -cp), (None if mate is None else -mate)


def format_eval_blancs(cp_white, mate_white):
    """Texte lisible d'une évaluation déjà exprimée point de vue Blancs :
    "#N" pour un mat des Blancs en N coups, "-#N" pour un mat des Noirs —
    jamais un mat converti en centipions — sinon la valeur en pions à deux
    décimales, signée ("+1.23", "-0.45"), "0.00" pour l'égalité exacte.
    Retourne None si aucune évaluation n'est disponible."""
    if mate_white is not None:
        n = abs(mate_white)
        return f"{MATE_SYMBOL}{n}" if mate_white > 0 else f"-{MATE_SYMBOL}{n}"
    if cp_white is None:
        return None
    pawns = cp_white / 100.0
    if cp_white > 0:
        return f"+{pawns:.2f}"
    if cp_white < 0:
        return f"{pawns:.2f}"
    return "0.00"


def eval_bar_fraction(cp_white, mate_white, cap_pawns=EVAL_BAR_CAP_PAWNS):
    """Fraction (0..1) de la hauteur de la barre occupée par les Blancs —
    0.5 égalité, 1.0 Blancs gagnants (mat en leur faveur), 0.0 symétrique
    pour les Noirs. Courbe douce (sigmoïde) jusqu'à `cap_pawns` pions ;
    au-delà (ou mat), plafond net à 1.0/0.0 — barre pleine du côté
    gagnant, comme demandé (issue #341 point 3)."""
    if mate_white is not None:
        return 1.0 if mate_white > 0 else 0.0
    if cp_white is None:
        return 0.5
    cap_cp = cap_pawns * 100.0
    if cp_white >= cap_cp:
        return 1.0
    if cp_white <= -cap_cp:
        return 0.0
    frac = 2.0 / (1.0 + math.exp(-_EVAL_BAR_SLOPE * cp_white)) - 1.0
    return 0.5 + 0.5 * frac


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

    def has_pending(self) -> bool:
        """True si une position attend encore d'être calculée — utilisé
        par l'analyse complète automatique (issue #342) pour lui céder la
        priorité plutôt que de saturer le même cœur CPU que les lignes à
        la demande (issue #335)."""
        with self._cv:
            return bool(self._queue)

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
        empty_no_bar = {"lines": [], "terminal": None, "bar_fraction": None, "bar_text": None}
        try:
            board = chess.Board(fen)
        except Exception as e:
            logger.warning(f"FEN invalide pour review_multipv : {e}")
            return {**empty_no_bar, "error": str(e)}

        # Position terminale (mat/pat/nulle automatique, issue #341 point 5) :
        # la barre montre directement le résultat sans jamais interroger le
        # moteur (aucun coup légal de toute façon pour un mat/pat).
        outcome = board.outcome(claim_draw=False)
        if outcome is not None:
            if outcome.winner is None:
                # Issue #351, point 0c : le pat est distingué des autres
                # nulles automatiques (matériel insuffisant, répétition,
                # 50 coups...) pour que l'écran d'analyse affiche "Pat"
                # plutôt que le message générique "lignes indisponibles".
                terminal = "stalemate" if outcome.termination == chess.Termination.STALEMATE else "draw"
                return {
                    "lines": [], "error": None, "terminal": terminal,
                    "bar_fraction": 0.5, "bar_text": "½",
                }
            white_wins = outcome.winner is True
            return {
                "lines": [], "error": None, "terminal": "checkmate",
                "bar_fraction": 1.0 if white_wins else 0.0,
                "bar_text": MATE_SYMBOL if white_wins else f"-{MATE_SYMBOL}",
            }

        try:
            engine = self._ensure_engine()
        except Exception as e:
            logger.error(f"Moteur indisponible pour review_multipv : {e}")
            return {**empty_no_bar, "error": str(e)}
        try:
            lines = engine.get_multipv(board, n=N_LINES, depth=DEPTH)
        except Exception as e:
            logger.error(f"Erreur get_multipv (review_multipv) : {e}")
            return {**empty_no_bar, "error": str(e)}
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
                return {**empty_no_bar, "error": "coup illégal pour la position affichée"}
        # Issue #341 : get_multipv() renvoie cp/mate relatifs au camp au
        # trait (board.turn) — reconvertis ici en point de vue des Blancs,
        # seule convention utilisée par la légende et la barre, avec le
        # texte déjà formaté ("#N"/"-#N" pour un mat, jamais en centipions).
        white_to_move = board.turn
        for line in lines:
            try:
                line["san"] = board.san(chess.Move.from_uci(line["move"]))
            except Exception:
                line["san"] = line["move"]
            cp_white, mate_white = _pov_vers_blancs(line.get("cp"), line.get("mate"), white_to_move)
            line["cp"] = cp_white
            line["mate"] = mate_white
            line["score_text"] = format_eval_blancs(cp_white, mate_white)
        if lines:
            bar_fraction = eval_bar_fraction(lines[0]["cp"], lines[0]["mate"])
            bar_text = lines[0]["score_text"]
        else:
            bar_fraction = None
            bar_text = None
        return {
            "lines": lines, "error": None, "terminal": None,
            "bar_fraction": bar_fraction, "bar_text": bar_text,
        }

    def _ensure_engine(self):
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine
