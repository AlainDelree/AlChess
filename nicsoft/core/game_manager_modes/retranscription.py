"""
nicsoft/core/game_manager_modes/retranscription.py — NicLink
Lanceur du mode retranscription (saisie de parties papier), extrait de
l'ancien nicsoft/core/game_manager.py (issue #278).
"""

import threading
import queue as _queue

from nicsoft.core.ihm_port import (
    send_event, set_app_state, get_action, set_virtual_board,
    app_state_proxy as web_server,
)


# ── Mode retranscription ───────────────────────────────────────────────────────
def launch_retranscription(config):
    from nicsoft.modes.retranscription.retranscription import run_retranscription
    _get_action = get_action

    while True:
        try:
            web_server.action_queue.get_nowait()
        except _queue.Empty:
            break  # queue vidée — fin normale du drain avant de démarrer la session

    web_server._app_state = "retranscription"
    set_app_state("retranscription", {
        "white": config.get("white", "Blancs"),
        "black": config.get("black", "Noirs"),
        "date":  config.get("date", ""),
        "event": config.get("event", ""),
        "mode":  config.get("mode", "partie"),
        "nom":   config.get("nom", ""),
    })
    t = threading.Thread(
        target=run_retranscription,
        args=(config, send_event, _get_action, set_virtual_board, web_server),
        daemon=True,
    )
    t.start()
    t.join()
    if web_server._app_state not in ("game_over", "menu"):
        web_server._app_state = "menu"
        set_app_state("menu")
