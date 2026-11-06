"""
nicsoft/engine/engine_availability.py — NicLink
Fonctions de disponibilité de chaque moteur, à appeler côté UI/menu avant de
proposer un moteur. rodent_available() lance réellement le processus moteur
pour vérifier le handshake UCI.
"""

import logging

import chess.engine

from nicsoft.config import ENGINES_DIR
from nicsoft.engine.engine_detection import find_stockfish, find_lc0, find_rodent, MAIA_LEVELS

logger = logging.getLogger("EngineManager")


def stockfish_available() -> bool:
    """Retourne True si Stockfish est présent sur le système (vérification fichier)."""
    return find_stockfish() is not None


def maia_available() -> bool:
    """
    Retourne True si Maia est disponible : lc0 présent ET au moins un poids
    maia-*.pb.gz présent dans engines/maia/.
    """
    if find_lc0() is None:
        return False
    maia_dir = ENGINES_DIR / "maia"
    if not maia_dir.exists():
        return False
    for level, filename in MAIA_LEVELS.items():
        if (maia_dir / filename).exists():
            return True
    return False


def rodent_available() -> bool:
    """
    Détermine si Rodent IV peut être proposé comme moteur.

    Ne se contente pas de vérifier la présence du binaire : le lance réellement
    et exige que le handshake UCI aboutisse (`uci` + `isready`, effectués par
    `popen_uci`) ET que l'option attendue soit exposée (`UCI_Elo`) — garantie
    qu'il s'agit bien de Rodent IV et non d'un binaire corrompu ou
    incompatible. À appeler côté UI/menu avant d'offrir le moteur.
    """
    path = find_rodent()
    if not path:
        return False
    engine = None
    try:
        engine = chess.engine.SimpleEngine.popen_uci(path)
        return "UCI_Elo" in engine.options
    except Exception as e:
        logger.warning(f"Rodent IV présent mais ne répond pas au handshake UCI : {e}")
        return False
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                # nettoyage best-effort en fin de vie : le moteur peut déjà être
                # arrêté/mort (EngineTerminatedError), ne pas répondre à temps
                # (TimeoutError) ou échouer pour une raison OS diverse — sans
                # conséquence fonctionnelle ici, mais tracé pour le debug.
                logger.debug("Échec quit() sur moteur de test Rodent IV", exc_info=True)
