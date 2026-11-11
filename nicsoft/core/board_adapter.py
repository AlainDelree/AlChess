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
    from nicsoft.niclink import hid_backend
    from nicsoft.core.ihm_port import send_event
    _logger = logging.getLogger(logger_name)
    manager = NicLinkManager(refresh_delay=0.1, logger=_logger, thread_sleep_delay=0.1)

    def _on_board_lost():
        # Notifie le navigateur si le module de lecture est perdu en cours de
        # session (5 lectures USB en échec consécutives — voir
        # NicLinkManager._fen_reader_loop). Distingue (issue #314, point 4) :
        # le périphérique est encore visible sur le bus USB (débranchement
        # pas encore détecté par l'OS, ou erreur de lecture logicielle) →
        # état informatif "à reconnecter" ; sinon, absence confirmée →
        # état d'erreur existant.
        if hid_backend.check_physically_present():
            send_event("board_reconnecting", {
                "message": "Lecture de l'échiquier perdue — reconnexion en cours.",
            })
        else:
            send_event("board_error", {
                "message": "Échiquier déconnecté — vérifiez l'USB et reconnectez le plateau.",
            })

    manager._board_lost_cb = _on_board_lost
    return manager
