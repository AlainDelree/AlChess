"""
nicsoft/game/analyse.py — NicLink
Fonctions d'analyse partagées entre play_pedagogique et le serveur web.

Délègue tout à EngineManager — ce module reste pour la compatibilité
des imports existants.
"""

import logging

from nicsoft.engine.engine_manager import (
    EngineManager,
    classifier_coup,
    score_to_cp,
    SEUIL_BON,
    SEUIL_IMPRECISION,
    SEUIL_ERREUR,
)

logger = logging.getLogger(__name__)

__all__ = [
    "classifier_coup",
    "score_to_cp",
    "analyser_partie",
    "analyser_partie_avec_manager",
    "SEUIL_BON",
    "SEUIL_IMPRECISION",
    "SEUIL_ERREUR",
]


def analyser_partie(moves_uci: list, niveau: int = 5, callback=None) -> list:
    """
    Analyse une liste de coups UCI.
    Compatibilité avec l'ancienne API — crée un EngineManager temporaire.
    Préférer analyser_partie_avec_manager() si un EngineManager existe déjà.
    """
    from nicsoft.engine.engine_manager import find_stockfish
    from nicsoft.core.config_manager import CONFIG_FILE, DEFAULT_CONFIG, read_json_with_defaults, validated_engine_path

    config = read_json_with_defaults(
        CONFIG_FILE, DEFAULT_CONFIG,
        on_error=lambda e: logger.debug(f"analyser_partie: lecture config.json échouée, fallback find_stockfish() : {e}"),
    )
    engine_path = validated_engine_path(config)

    if not engine_path:
        engine_path = find_stockfish() or "stockfish"

    # Convertir niveau 1-20 en Elo approximatif pour compatibilité
    elo_map = {
        1: 1320, 2: 1350, 3: 1400, 4: 1450, 5: 1500,
        6: 1600, 7: 1700, 8: 1800, 9: 1900, 10: 2000,
        11: 2100, 12: 2150, 13: 2200, 14: 2250, 15: 2300,
        16: 2400, 17: 2500, 18: 2600, 19: 2700, 20: 3190,
    }
    engine_elo = elo_map.get(niveau, 1500)

    manager = None
    try:
        manager = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=True)
        return manager.analyser_partie(moves_uci, callback=callback)
    finally:
        if manager:
            manager.quit()


def analyser_partie_avec_manager(manager: EngineManager,
                                  moves_uci: list,
                                  callback=None) -> list:
    """
    Analyse une liste de coups UCI en utilisant un EngineManager existant.
    Plus efficace car réutilise le moteur déjà lancé.
    """
    return manager.analyser_partie(moves_uci, callback=callback)
