"""
nicsoft/engine/maia_engine.py — NicLink
Moteur Maia Chess via lc0.
"""

import re
import logging
import threading
from pathlib import Path

import chess
import chess.engine

from nicsoft.engine.uci_engine import EngineManager
from nicsoft.engine.engine_detection import _ensure_executable

logger = logging.getLogger("EngineManager")


class MaiaEngine(EngineManager):
    """
    Moteur Maia Chess via lc0.

    Différences avec EngineManager (Stockfish) :
    - Le niveau est défini par le fichier de poids (maia-1100 à maia-1900)
    - get_move() utilise nodes=1 au lieu d'un temps de réflexion
    - evaluate() et evaluate_move() utilisent Stockfish pour l'analyse
      (Maia n'est pas fait pour évaluer, seulement pour jouer)
    """

    def __init__(self, lc0_path: str, weights_path: str,
                 maia_elo: int = 1100,
                 stockfish_path: str | None = None,
                 analyse_active: bool = True) -> None:

        self._lc0_path      = lc0_path
        self._weights_path  = weights_path
        self._analyse_active = analyse_active
        self._lock_play     = threading.Lock()
        self._lock_eval     = threading.Lock()

        self._engine_play: chess.engine.SimpleEngine | None = None
        self._engine_eval: chess.engine.SimpleEngine | None = None

        self._supports_wdl       = False
        self._supports_elo_limit = False

        # Extraire le niveau réel depuis le nom du fichier de poids
        m = re.search(r'maia-(\d+)', str(weights_path))
        self._maia_elo   = int(m.group(1)) if m else maia_elo
        self._engine_name = f"Maia {self._maia_elo}"

        self._init_maia(lc0_path, weights_path, stockfish_path)

    def _init_maia(self, lc0_path: str, weights_path: str,
                   stockfish_path: str | None) -> None:
        """Lance lc0 avec les poids Maia + Stockfish pour l'analyse."""
        _ensure_executable(lc0_path)
        try:
            # Moteur de jeu : lc0 + poids Maia
            self._engine_play = chess.engine.SimpleEngine.popen_uci(
                [lc0_path, f"--weights={weights_path}"]
            )
            self._engine_name = f"Maia {self._maia_elo}"
            logger.info(f"Maia lancé : {weights_path}")

            # Moteur d'évaluation : Stockfish si disponible, sinon lc0
            if stockfish_path and Path(stockfish_path).exists():
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(stockfish_path)
                self._supports_wdl = "UCI_ShowWDL" in self._engine_eval.options
                if self._supports_wdl:
                    self._engine_eval.configure({"UCI_ShowWDL": True})
                logger.info(f"Stockfish pour analyse : {stockfish_path}")
            else:
                # Fallback : deuxième instance lc0 pour l'analyse
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(
                    [lc0_path, f"--weights={weights_path}"]
                )
                logger.warning("Stockfish non trouvé — analyse via lc0 (limité)")

        except Exception as e:
            logger.error(f"Impossible de lancer Maia : {e}")
            raise

    def get_move(self, board: chess.Board,
                 think_time: float = 1.0) -> chess.Move | None:
        """
        Demande un coup à Maia — nodes=1 (pas de recherche, réseau pur).
        think_time est ignoré pour Maia.
        """
        with self._lock_play:
            if not self._engine_play:
                return None
            try:
                result = self._engine_play.play(
                    board,
                    chess.engine.Limit(nodes=1),
                )
                return result.move
            except Exception as e:
                logger.error(f"Erreur Maia get_move : {e}")
                return None

    # evaluate(), evaluate_move(), get_punishment_line(), wdl_to_bar()
    # sont héritées d'EngineManager et utilisent _engine_eval (Stockfish)
    # → pas besoin de les surcharger

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def engine_elo(self) -> int:
        return self._maia_elo
