"""
nicsoft/utils/timing.py — Logger de timing partagé.

Utilisation dans le code :
    from nicsoft.utils.timing import tlog
    tlog("await_move: %.2fs", elapsed)

Activation :
    NICLINK_LOG=DEBUG python -m nicsoft.web
"""

import logging

tlog_logger = logging.getLogger("niclink.timing")


def tlog(msg: str, *args) -> None:
    """Log un message de timing (visible uniquement si NICLINK_LOG=DEBUG)."""
    tlog_logger.debug(msg, *args)
