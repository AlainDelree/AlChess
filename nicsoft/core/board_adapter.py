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
    from nicsoft.web.server import send_event
    _logger = logging.getLogger(logger_name)
    manager = NicLinkManager(refresh_delay=0.1, logger=_logger, thread_sleep_delay=0.1)
    # Notifie le navigateur si le plateau est perdu en cours de session
    # (5 lectures USB en échec consécutives — voir NicLinkManager._fen_reader_loop).
    manager._board_lost_cb = lambda: send_event(
        "board_error",
        {"message": "Échiquier déconnecté — vérifiez l'USB et reconnectez le plateau."},
    )
    return manager
