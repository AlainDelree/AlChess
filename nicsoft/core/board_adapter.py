"""
nicsoft/core/board_adapter.py — NicLink
Crée un échiquier connecté (physique ou virtuel) sans dup2.
Centralise l'instanciation de NicLinkManager / VirtualBoard.
"""

import logging


def create_board(virtual: bool = False, logger_name: str = "NicLink"):
    """Retourne un échiquier connecté.

    virtual=True  → VirtualBoard (aucun hardware requis)
    virtual=False → NicLinkManager via hid_backend (pur Python, pas de dup2)
    """
    if virtual:
        from nicsoft.niclink.virtual_board import VirtualBoard
        return VirtualBoard()

    from nicsoft.niclink import NicLinkManager
    _logger = logging.getLogger(logger_name)
    return NicLinkManager(refresh_delay=0.1, logger=_logger, thread_sleep_delay=0.1)
