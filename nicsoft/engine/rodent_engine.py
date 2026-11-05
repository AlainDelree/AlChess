"""
nicsoft/engine/rodent_engine.py — NicLink
Moteur Rodent IV — adversaire faible pensé pour les débutants.
"""

import logging
import threading
from pathlib import Path

import chess
import chess.engine

from nicsoft.engine.uci_engine import EngineManager

logger = logging.getLogger("EngineManager")

# ── Rodent IV : personnalités et bornes ──────────────────────────────────────
# Valeurs EXACTES de l'option UCI combo "Personality" du binaire Rodent IV
# (relevées via `uci`). Le sélecteur UI doit envoyer une de ces valeurs telles
# quelles ; toute autre valeur est refusée par le moteur. "Bosboom.txt" porte
# bien l'extension dans la déclaration UCI (quirk du binaire).
RODENT_PERSONALITIES = [
    "Alekhine", "Amanda", "Ampere", "Anand", "Anderssen", "Bosboom.txt",
    "Botvinnik", "Cloe", "Deborah", "Defender", "Dynamic", "Fischer",
    "Grumpy", "Karpov", "Kasparov", "Kortchnoi", "Larsen", "Lasker",
    "Marshall", "Morphy", "Nimzowitsch", "Partisan", "Pawnsacker", "Pedrita",
    "Petrosian", "Preston", "Reti", "Rubinstein", "Simple", "Spassky",
    "Spitfire", "Steinitz", "Strangler", "Tarrasch", "Tal", "Topalov",
]
RODENT_ELO_MIN            = 800
RODENT_ELO_MAX            = 2800
RODENT_ELO_DEFAUT         = 1200
RODENT_PERSONALITY_DEFAUT = "Tal"


class RodentEngine(EngineManager):
    """
    Moteur Rodent IV — adversaire faible pensé pour les débutants.

    Spécificités (cf. investigation issue #12, corrigé issue #197) :
      - L'ordre d'envoi des `setoption` est IMPÉRATIF :
          Personality → UCI_LimitStrength → UCI_Elo  (Elo TOUJOURS en dernier).
        Chaque option est envoyée dans son propre `configure()` pour garantir
        l'ordre indépendamment de l'implémentation de python-chess. Si l'Elo
        n'est pas envoyé en dernier, le moteur retombe à pleine puissance.
      - L'option UCI s'appelle `Personality` (et non `PersonalityFile` — ce
        binaire Rodent IV rejette ce nom avec "does not support option").
      - L'analyse (barre d'évaluation, qualité des coups) est déléguée à
        Stockfish : Rodent n'est pas conçu pour évaluer objectivement.
    """

    def __init__(self, rodent_path: str,
                 personality: str = RODENT_PERSONALITY_DEFAUT,
                 rodent_elo: int = RODENT_ELO_DEFAUT,
                 stockfish_path: str | None = None,
                 analyse_active: bool = True) -> None:
        self._rodent_path    = rodent_path
        self._personality    = personality if personality in RODENT_PERSONALITIES \
                                            else RODENT_PERSONALITY_DEFAUT
        self._engine_elo     = max(RODENT_ELO_MIN, min(RODENT_ELO_MAX, rodent_elo))
        self._analyse_active = analyse_active
        self._lock_play      = threading.Lock()
        self._lock_eval      = threading.Lock()

        self._engine_play: chess.engine.SimpleEngine | None = None
        self._engine_eval: chess.engine.SimpleEngine | None = None

        self._supports_wdl       = False
        self._supports_elo_limit = True
        self._engine_name        = f"Rodent {self._engine_elo}"

        self._init_rodent(rodent_path, stockfish_path)

    def _apply_rodent_options(self, engine: chess.engine.SimpleEngine) -> None:
        """
        Envoie les options dans l'ordre impératif Personality → LimitStrength → Elo.
        Un `configure()` distinct par option = un `setoption` distinct, ordre garanti.

        Note (vérifié via logs UCI, issue #13) : python-chess n'émet PAS un
        `setoption` quand la valeur demandée égale la valeur par défaut déclarée
        par le moteur. Rodent IV déclare `UCI_LimitStrength` avec le défaut
        `true` → la ligne LimitStrength n'apparaît pas dans les logs (no-op),
        l'option étant déjà active. L'ordre réellement envoyé reste donc
        Personality → UCI_Elo (Elo en dernier), ce qui satisfait la contrainte
        de l'issue #12. Robuste : si un build avait le défaut `false`,
        python-chess enverrait la ligne (valeur ≠ défaut).
        """
        engine.configure({"Personality": self._personality})
        engine.configure({"UCI_LimitStrength": True})
        engine.configure({"UCI_Elo": self._engine_elo})

    def _init_rodent(self, rodent_path: str, stockfish_path: str | None) -> None:
        try:
            # Moteur de jeu : Rodent (Elo limité, personnalité choisie)
            self._engine_play = chess.engine.SimpleEngine.popen_uci(rodent_path)
            self._apply_rodent_options(self._engine_play)
            logger.info(f"Rodent : Personality={self._personality}, Elo={self._engine_elo}")

            # Moteur d'évaluation : Stockfish si disponible, sinon Rodent (limité)
            if stockfish_path and Path(stockfish_path).exists():
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(stockfish_path)
                if "UCI_ShowWDL" in self._engine_eval.options:
                    self._engine_eval.configure({"UCI_ShowWDL": True})
                    self._supports_wdl = True
                logger.info(f"Rodent : analyse déléguée à Stockfish ({stockfish_path})")
            else:
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(rodent_path)
                logger.warning("Rodent : Stockfish introuvable — analyse via Rodent (limitée)")

        except Exception as e:
            logger.error(f"Impossible de lancer Rodent : {e}")
            raise

    def set_elo(self, elo: int) -> None:
        """Change l'Elo à chaud en respectant l'ordre Personality → LimitStrength → Elo."""
        self._engine_elo  = max(RODENT_ELO_MIN, min(RODENT_ELO_MAX, elo))
        self._engine_name = f"Rodent {self._engine_elo}"
        with self._lock_play:
            if self._engine_play:
                self._apply_rodent_options(self._engine_play)

    @property
    def personality(self) -> str:
        return self._personality

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def engine_elo(self) -> int:
        return self._engine_elo
