"""
nicsoft/engine/engine_analysis.py — NicLink
Méthodes d'analyse de position/coup pour EngineManager (évaluation, qualité
des coups joués, ligne punitive, MultiPV). Regroupées dans un mixin pour que
EngineManager (nicsoft/engine/uci_engine.py) reste lisible — comportement et
API inchangés par rapport à l'ancien engine_manager.py monolithique.
"""

import logging

import chess
import chess.engine

from nicsoft.engine.move_quality import (
    classifier_coup_winrate,
    REVIEW_DEPTH,
    REVIEW_N_LINES,
)

logger = logging.getLogger("EngineManager")

# Valeur conventionnelle (centipions) représentant un mat, pour
# l'affichage seulement — jamais utilisée pour classer un coup (la
# classification se fait en chances de gain, voir move_quality.py). Même
# plafond que la barre d'évaluation de l'écran d'analyse (10 pions,
# EVAL_BAR_CAP_PAWNS dans review_multipv.py) plutôt qu'une valeur énorme et
# artificielle — un "999cp" reste lisible, un "99455cp" ressemblerait à un bug.
_MATE_CP_AFFICHAGE = 1_000


def _cp_equiv_affichage(cp: int | None, mate: int | None) -> int:
    if mate is not None:
        return (_MATE_CP_AFFICHAGE - abs(mate)) if mate > 0 else -(_MATE_CP_AFFICHAGE - abs(mate))
    return cp if cp is not None else 0


def _delta_cp_affichage(best_cp, best_mate, played_cp, played_mate) -> int:
    """Perte approximative en centipions, pour l'affichage seulement (ex.
    "123cp" à côté du symbole ?!/?/??) — jamais la base de la
    classification elle-même, qui se fait en chances de gain."""
    return max(0, _cp_equiv_affichage(best_cp, best_mate) - _cp_equiv_affichage(played_cp, played_mate))


class EngineAnalysisMixin:
    """
    Méthodes d'analyse — attendent sur self : _lock_eval, _engine_eval,
    _analyse_active (fournis par EngineManager.__init__).
    """

    def evaluate(self, board: chess.Board, depth: int = 8) -> dict:
        """
        Évalue une position avec le moteur d'évaluation (pleine force).

        Retourne un dict :
          {
            "cp"      : int | None,   # centipawns du point de vue du joueur actif
            "mate"    : int | None,   # coups avant mat (négatif = on se fait mater)
            "wdl"     : (int, int, int) | None,  # (victoire, nulle, défaite) /1000
            "best_move": str | None,  # meilleur coup UCI
          }
        """
        with self._lock_eval:
            if not self._engine_eval:
                return {"cp": None, "mate": None, "wdl": None, "best_move": None}
            try:
                info = self._engine_eval.analyse(
                    board,
                    chess.engine.Limit(depth=depth),
                    info=chess.engine.INFO_ALL,
                )
                score = info.get("score")
                pv    = info.get("pv", [])

                cp   = None
                mate = None
                wdl  = None

                if score:
                    pov_score = score.pov(board.turn)
                    if pov_score.is_mate():
                        mate = pov_score.mate()
                    else:
                        cp = pov_score.score()
                    # WDL du point de vue du joueur actif
                    if self._supports_wdl and score.wdl():
                        w = score.wdl().pov(board.turn)
                        wdl = (w.wins, w.draws, w.losses)

                best_move = pv[0].uci() if pv else None

                return {"cp": cp, "mate": mate, "wdl": wdl, "best_move": best_move}

            except Exception as e:
                logger.error(f"Erreur evaluate : {e}")
                return {"cp": None, "mate": None, "wdl": None, "best_move": None}

    def evaluate_move(self, board: chess.Board, move: chess.Move,
                      depth: int = 8, n_lines: int = REVIEW_N_LINES,
                      ) -> tuple[str, int, str | None]:
        """
        Évalue la qualité d'un coup joué — issue #352 : réutilise EXACTEMENT
        la même recherche que les flèches de l'écran d'analyse
        (`get_multipv`, même profondeur), jamais un calcul séparé à une
        profondeur différente. Si le coup joué ne fait pas partie des
        `n_lines` meilleures lignes, il est évalué par une recherche
        restreinte à ce seul coup (`root_moves`) à la MÊME profondeur —
        toujours la même méthode, jamais un raccourci moins profond.

        La perte est mesurée en chances de gain (voir
        `move_quality.classifier_coup_winrate`), du point de vue du joueur
        qui a joué (blancs comme noirs) : `get_multipv` renvoie déjà ses
        évaluations du point de vue du camp au trait sur la position AVANT
        le coup, donc aucune inversion de signe n'est nécessaire ni risquée
        ici (contrairement à l'ancienne implémentation, qui évaluait la
        position après coup puis inversait le signe à la main).

        Retourne (qualite, delta_cp, best_move_uci) :
          - qualite    : "bon" / "imprecision" / "erreur" / "blunder"
          - delta_cp   : perte approximative en centipawns (0 = parfait),
                         pour l'affichage seulement — un mat gagné ou perdu
                         y est représenté par une valeur conventionnelle
                         très grande, jamais la vraie classification (qui
                         se fait sur la perte en chances de gain, pas sur
                         ce nombre)
          - best_move  : meilleur coup UCI si différent du coup joué, sinon None
        """
        if not self._analyse_active:
            return "bon", 0, None

        try:
            joueur = board.turn
            lines = self.get_multipv(board, n=n_lines, depth=depth)
            if not lines:
                return "bon", 0, None

            best_cp, best_mate = lines[0]["cp"], lines[0]["mate"]
            best_move_uci = lines[0]["move"]

            played_cp = played_mate = None
            for line in lines:
                if line["move"] == move.uci():
                    played_cp, played_mate = line["cp"], line["mate"]
                    break

            if played_cp is None and played_mate is None:
                # Coup joué hors des n_lines meilleures lignes : même
                # profondeur, même méthode (recherche restreinte à ce seul
                # coup), pas un calcul séparé plus rapide/moins profond.
                with self._lock_eval:
                    if not self._engine_eval:
                        return "bon", 0, None
                    try:
                        info = self._engine_eval.analyse(
                            board, chess.engine.Limit(depth=depth),
                            root_moves=[move], info=chess.engine.INFO_SCORE,
                        )
                        score = info.get("score")
                    except Exception as e:
                        logger.warning(f"evaluate_move (root_moves) échoué : {e}")
                        score = None
                if score is not None:
                    pov = score.pov(joueur)
                    if pov.is_mate():
                        played_mate = pov.mate()
                    else:
                        played_cp = pov.score()

            qualite, _perte = classifier_coup_winrate(best_cp, best_mate, played_cp, played_mate)
            best = best_move_uci if best_move_uci != move.uci() else None
            delta_cp = _delta_cp_affichage(best_cp, best_mate, played_cp, played_mate)

            return qualite, delta_cp, best

        except Exception as e:
            logger.error(f"Erreur evaluate_move : {e}")
            return "bon", 0, None

    def get_punishment_line(self, board: chess.Board, move: chess.Move,
                             depth: int = 12, max_moves: int = 3) -> list[str]:
        """
        Retourne la ligne punitive après un coup humain.
        """
        with self._lock_eval:
            if not self._engine_eval:
                return []
            try:
                board_after = board.copy()
                board_after.push(move)
                info = self._engine_eval.analyse(
                    board_after,
                    chess.engine.Limit(depth=depth),
                    info=chess.engine.INFO_PV,
                )
                pv = info.get("pv", [])
                result = [m.uci() for m in pv[:max_moves]]
                logger.debug(f"get_punishment_line: {result}")
                return result
            except Exception as e:
                logger.error(f"Erreur get_punishment_line : {e}")
                return []

    def get_multipv(self, board: chess.Board, n: int = REVIEW_N_LINES,
                    depth: int = REVIEW_DEPTH) -> list[dict]:
        """
        Retourne les n meilleurs coups avec leur évaluation.
        Utile pour l'écran d'analyse.

        Retourne une liste de dict :
          [{"move": str (UCI), "cp": int, "mate": int | None}, ...]
        """
        with self._lock_eval:
            if not self._engine_eval:
                return []
            try:
                infos = self._engine_eval.analyse(
                    board,
                    chess.engine.Limit(depth=depth),
                    multipv=n,
                    info=chess.engine.INFO_ALL,
                )
                result = []
                for info in infos:
                    pv    = info.get("pv", [])
                    score = info.get("score")
                    if not pv:
                        continue
                    move_uci = pv[0].uci()
                    cp   = None
                    mate = None
                    if score:
                        pov = score.pov(board.turn)
                        if pov.is_mate():
                            mate = pov.mate()
                        else:
                            cp = pov.score()
                    result.append({"move": move_uci, "cp": cp, "mate": mate})
                return result
            except Exception as e:
                logger.error(f"Erreur get_multipv : {e}")
                return []

    def analyser_partie(self, moves_uci: list[str],
                        callback=None,
                        seq_moves: int = 3,
                        should_continue=None) -> list[dict]:
        """
        Analyse une liste de coups UCI.

        Paramètres :
          moves_uci       : liste de coups UCI
          callback        : fonction(idx, total, résultat) appelée après chaque coup
          seq_moves       : nombre de coups de la séquence punitive (3-5)
          should_continue : fonction() -> bool, vérifiée avant chaque coup
                            (issue #342) ; un retour False arrête l'analyse
                            avant le coup courant (partie incomplète, jamais
                            marquée comme terminée par l'appelant) — permet
                            d'arrêter proprement une analyse automatique
                            quand l'utilisateur change de partie ou quitte
                            l'écran, sans attendre la fin complète.

        Retourne une liste de dict :
          [{"qualite": str, "delta_cp": int, "best_move": str | None,
            "punishment_line": list[str], "fen_avant_coup": str}, ...]
        """
        board     = chess.Board()
        resultats = []
        total     = len(moves_uci)

        for idx, uci in enumerate(moves_uci):
            if should_continue is not None and not should_continue():
                break
            try:
                move = chess.Move.from_uci(uci)
                fen_avant = board.fen()
                # Issue #352 : même profondeur que les flèches (REVIEW_DEPTH)
                # — c'est cette analyse qui alimente les marques ?!/?/?? de
                # l'écran d'analyse après partie, affichées en même temps
                # que les flèches/la barre d'évaluation (review_multipv.py).
                qualite, delta, best = self.evaluate_move(board, move, depth=REVIEW_DEPTH)
                # Calculer la séquence punitive pour les coups non-bons
                punishment_line = []
                if qualite != "bon" and best:
                    punishment_line = self.get_punishment_line(
                        board, move, depth=12, max_moves=seq_moves
                    )
                res = {
                    "qualite":          qualite,
                    "delta_cp":         delta,
                    "best_move":        best,
                    "punishment_line":  punishment_line,
                    "fen_avant_coup":   fen_avant,
                }
                board.push(move)
            except Exception as e:
                logger.warning(f"analyser_partie: coup #{idx} ({uci}) non évaluable, classé 'bon' par défaut : {e}")
                res = {
                    "qualite":         "bon",
                    "delta_cp":        0,
                    "best_move":       None,
                    "punishment_line": [],
                    "fen_avant_coup":  board.fen(),
                }

            resultats.append(res)
            if callback:
                callback(idx, total, res)

        return resultats

    def wdl_to_bar(self, wdl: tuple[int, int, int] | None) -> dict:
        """
        Convertit un tuple WDL en pourcentages pour la barre d'affichage.

        Retourne :
          {"win": float, "draw": float, "loss": float}
          ou None si WDL non disponible.
        """
        if not wdl:
            return None
        w, d, l = wdl
        total = w + d + l
        if total == 0:
            return None
        return {
            "win":  round(w / total * 100, 1),
            "draw": round(d / total * 100, 1),
            "loss": round(l / total * 100, 1),
        }
