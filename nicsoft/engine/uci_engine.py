"""
nicsoft/engine/uci_engine.py — NicLink
Gestionnaire générique d'un moteur UCI (Stockfish et compatibles), via
python-chess. MaiaEngine et RodentEngine (nicsoft/engine/maia_engine.py,
nicsoft/engine/rodent_engine.py) en héritent pour leurs spécificités.
"""

import chess
import chess.engine
import threading
import logging

from nicsoft.engine.engine_analysis import EngineAnalysisMixin

logger = logging.getLogger("EngineManager")

# Plage Elo supportée par Stockfish via UCI_Elo
ELO_MIN = 1320
ELO_MAX = 3190
ELO_DEFAUT = 1500


class EngineManager(EngineAnalysisMixin):
    """
    Gestionnaire universel de moteur UCI.

    Utilise python-chess pour communiquer avec n'importe quel moteur UCI.
    Deux instances internes :
      - _engine_play  : pour calculer les coups (Elo limité)
      - _engine_eval  : pour évaluer les positions (pleine force, rapide)
    """

    def __init__(self, engine_path: str, engine_elo: int = ELO_DEFAUT,
                 analyse_active: bool = True) -> None:
        self._engine_path   = engine_path
        self._engine_elo    = max(ELO_MIN, min(ELO_MAX, engine_elo))
        self._analyse_active = analyse_active
        self._lock_play     = threading.Lock()
        self._lock_eval     = threading.Lock()

        self._engine_play: chess.engine.SimpleEngine | None = None
        self._engine_eval: chess.engine.SimpleEngine | None = None

        self._supports_wdl     = False
        self._supports_elo_limit = False
        self._engine_name      = "Moteur UCI"

        self._init_engines()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_engines(self) -> None:
        """Lance les deux instances du moteur et détecte les capacités."""
        try:
            self._engine_play = chess.engine.SimpleEngine.popen_uci(self._engine_path)
            self._engine_eval = chess.engine.SimpleEngine.popen_uci(self._engine_path)
            self._engine_name = self._engine_play.id.get("name", "Moteur UCI")

            # Détecter les options supportées
            options = self._engine_play.options
            self._supports_elo_limit = (
                "UCI_LimitStrength" in options and "UCI_Elo" in options
            )
            self._supports_wdl = "UCI_ShowWDL" in options

            # Configurer le moteur de jeu (Elo limité)
            self._apply_elo(self._engine_play)

            # Configurer le moteur d'évaluation (pleine force, rapide)
            if self._supports_wdl:
                self._engine_eval.configure({"UCI_ShowWDL": True})

            logger.info(f"Moteur : {self._engine_name}")
            logger.info(f"Elo limité : {self._supports_elo_limit} | WDL : {self._supports_wdl}")

        except Exception as e:
            logger.error(f"Impossible de lancer le moteur : {e}")
            raise

    def _apply_elo(self, engine: chess.engine.SimpleEngine) -> None:
        """Applique la limitation de force Elo sur une instance du moteur."""
        if self._supports_elo_limit:
            engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": self._engine_elo,
            })
            if self._supports_wdl:
                engine.configure({"UCI_ShowWDL": True})
        else:
            # Fallback : moteur sans UCI_Elo → pas de limitation de force
            logger.warning(f"{self._engine_name} ne supporte pas UCI_Elo.")

    # ── API publique ──────────────────────────────────────────────────────────

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def engine_elo(self) -> int:
        return self._engine_elo

    @property
    def analyse_active(self) -> bool:
        return self._analyse_active

    @analyse_active.setter
    def analyse_active(self, value: bool) -> None:
        self._analyse_active = value

    def set_elo(self, elo: int) -> None:
        """Change le niveau Elo du moteur de jeu à chaud."""
        self._engine_elo = max(ELO_MIN, min(ELO_MAX, elo))
        with self._lock_play:
            if self._engine_play:
                self._apply_elo(self._engine_play)

    def get_move(self, board: chess.Board, think_time: float = 1.0) -> chess.Move | None:
        """
        Demande le meilleur coup au moteur de jeu (Elo limité).

        Paramètres :
          board      : position actuelle
          think_time : temps de réflexion en secondes

        Retourne le coup ou None en cas d'erreur.
        """
        with self._lock_play:
            if not self._engine_play:
                return None
            try:
                result = self._engine_play.play(
                    board,
                    chess.engine.Limit(time=think_time),
                )
                return result.move
            except Exception as e:
                logger.error(f"Erreur get_move : {e}")
                return None

    def quit(self) -> None:
        """Arrête proprement les deux instances du moteur."""
        for engine in [self._engine_play, self._engine_eval]:
            if engine:
                try:
                    engine.quit()
                except Exception:
                    pass  # nettoyage best-effort en fin de vie
        self._engine_play = None
        self._engine_eval = None
