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

from nicsoft.engine.move_quality import classifier_coup

logger = logging.getLogger("EngineManager")


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
                      depth: int = 8) -> tuple[str, int, str | None]:
        """
        Évalue la qualité d'un coup joué.

        Retourne (qualite, delta_cp, best_move_uci) :
          - qualite    : "bon" / "imprecision" / "erreur" / "blunder"
          - delta_cp   : perte en centipawns (0 = parfait)
          - best_move  : meilleur coup UCI si différent du coup joué, sinon None
        """
        if not self._analyse_active:
            return "bon", 0, None

        try:
            joueur = board.turn

            # Évaluation AVANT le coup
            eval_avant = self.evaluate(board, depth=depth)
            cp_avant   = eval_avant["cp"]
            best_move  = eval_avant["best_move"]


            if cp_avant is None:
                # Position de mat → bon coup par défaut
                return "bon", 0, None

            # Évaluation APRÈS le coup
            board_apres = board.copy()
            board_apres.push(move)
            eval_apres = self.evaluate(board_apres, depth=depth)
            cp_apres   = eval_apres["cp"]

            if cp_apres is None:
                # Mat après le coup → excellent
                return "bon", 0, None

            # La perte est vue du point de vue du joueur AVANT son coup
            # cp_avant = score pour joueur avant coup
            # cp_apres = score pour l'adversaire après coup → on l'inverse
            delta = max(0, cp_avant - (-cp_apres))

            qualite = classifier_coup(delta)
            best    = best_move if best_move and best_move != move.uci() else None

            # Si coup mauvais mais pas de meilleur coup alternatif trouvé,
            # relancer en MultiPV=2 pour obtenir le vrai meilleur coup
            if qualite != "bon" and best is None:
                try:
                    with self._lock_eval:
                        info_mpv = self._engine_eval.analyse(
                            board,
                            chess.engine.Limit(depth=depth),
                            multipv=2,
                        )
                    if isinstance(info_mpv, list):
                        for entry in info_mpv:
                            pv = entry.get("pv", [])
                            if pv and pv[0].uci() != move.uci():
                                best = pv[0].uci()
                                break
                except Exception as e:
                    logger.warning(f"MultiPV fallback échoué : {e}")

            return qualite, delta, best

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

    def get_multipv(self, board: chess.Board, n: int = 3,
                    depth: int = 12) -> list[dict]:
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
                        seq_moves: int = 3) -> list[dict]:
        """
        Analyse une liste de coups UCI.

        Paramètres :
          moves_uci : liste de coups UCI
          callback  : fonction(idx, total, résultat) appelée après chaque coup
          seq_moves : nombre de coups de la séquence punitive (3-5)

        Retourne une liste de dict :
          [{"qualite": str, "delta_cp": int, "best_move": str | None,
            "punishment_line": list[str], "fen_avant_coup": str}, ...]
        """
        board     = chess.Board()
        resultats = []
        total     = len(moves_uci)

        for idx, uci in enumerate(moves_uci):
            try:
                move = chess.Move.from_uci(uci)
                fen_avant = board.fen()
                qualite, delta, best = self.evaluate_move(board, move, depth=8)
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
