"""
nicsoft/engine/engine_manager.py — NicLink
Point d'entrée de la couche d'abstraction moteurs UCI (Stockfish, Maia,
Rodent IV). Le contenu a été découpé en modules cohérents (issue #276) :

  - move_quality.py         : classification de la qualité d'un coup (pure)
  - engine_analysis.py      : évaluation/analyse d'une position via un moteur
  - uci_engine.py           : EngineManager, gestion générique d'un moteur UCI
  - engine_detection.py     : détection des binaires (Stockfish, lc0, Rodent)
  - engine_availability.py : disponibilité de chaque moteur
  - maia_engine.py          : MaiaEngine (spécialisation Maia Chess via lc0)
  - rodent_engine.py        : RodentEngine (spécialisation Rodent IV)

Ce module réexporte les mêmes objets qu'avant le découpage pour que tous
les imports existants (serveur web, analyse, mode labo, tests) continuent
de fonctionner sans modification.
"""

from nicsoft.engine.move_quality import (
    SEUIL_BON,
    SEUIL_IMPRECISION,
    SEUIL_ERREUR,
    classifier_coup,
    score_to_cp,
)
from nicsoft.engine.uci_engine import (
    ELO_MIN,
    ELO_MAX,
    ELO_DEFAUT,
    EngineManager,
)
from nicsoft.engine.engine_detection import (
    find_stockfish,
    find_lc0,
    find_rodent,
    find_maia_weights,
    MAIA_LEVELS,
)
from nicsoft.engine.engine_availability import (
    stockfish_available,
    maia_available,
    rodent_available,
)
from nicsoft.engine.maia_engine import MaiaEngine
from nicsoft.engine.rodent_engine import (
    RodentEngine,
    RODENT_PERSONALITIES,
    RODENT_ELO_MIN,
    RODENT_ELO_MAX,
    RODENT_ELO_DEFAUT,
    RODENT_PERSONALITY_DEFAUT,
)

__all__ = [
    "SEUIL_BON", "SEUIL_IMPRECISION", "SEUIL_ERREUR",
    "classifier_coup", "score_to_cp",
    "ELO_MIN", "ELO_MAX", "ELO_DEFAUT", "EngineManager",
    "find_stockfish", "find_lc0", "find_rodent", "find_maia_weights", "MAIA_LEVELS",
    "stockfish_available", "maia_available", "rodent_available",
    "MaiaEngine",
    "RodentEngine", "RODENT_PERSONALITIES",
    "RODENT_ELO_MIN", "RODENT_ELO_MAX", "RODENT_ELO_DEFAUT", "RODENT_PERSONALITY_DEFAUT",
]
