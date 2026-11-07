"""
nicsoft/core/game_manager_modes/labo_session.py — NicLink
Boucle d'actions de la session labo (extrait de l'ancien
nicsoft/core/game_manager.py, issue #278) — voisin de labo.py qui gère
le démarrage (connexion échiquier, poll FEN).

Le drapeau d'annulation de copie (_copy_cancel) est propre au mode labo et
ne quitte jamais ce couple de modules (labo.py, labo_session.py).
"""

import time
import threading
import chess

from nicsoft.engine.engine_manager import RODENT_ELO_DEFAUT, RODENT_PERSONALITY_DEFAUT
from nicsoft.core.ihm_port import (
    send_event, set_app_state, get_action, set_virtual_board, get_action_queue,
    app_state_proxy as web_server,
)
from nicsoft.core.game_manager_modes.state import logger, get_virtual_mode, get_nl_inst_ref

# ── État propre au mode labo ────────────────────────────────────────────────────
_copy_cancel = threading.Event()


def _run_labo_session():
    from nicsoft.core.game_manager_modes.labo import _make_labo_session
    _get_action = get_action

    for _ in range(50):
        if get_nl_inst_ref() is not None:
            break
        time.sleep(0.1)

    nl = get_nl_inst_ref()
    if nl is None:
        logger.error("[LABO] Échiquier non disponible")
        return

    virtual_mode = get_virtual_mode()

    labo_config = {
        "human_color": "white",
        "engine_type": "stockfish",
        "engine_elo":  1500,
        "maia_elo":    1500,
        "rodent_elo":  RODENT_ELO_DEFAUT,
        "rodent_personality": RODENT_PERSONALITY_DEFAUT,
        "analyse":     True,
    }

    try:
        session = _make_labo_session(nl, labo_config)
    except Exception as e:
        logger.error(f"[LABO] Erreur création session : {e}")
        return

    session._running = True
    if not virtual_mode:
        threading.Thread(target=session.board_watcher, daemon=True).start()
        session.sync_from_physical()
    else:
        nl.make_virtual_board_watcher(session).start()
        session._send_position()

    send_event("labo_init", {
        "fen":          session.board.board_fen(),
        "human_color":  labo_config["human_color"],
        "engine_label": session.engine_label,
        "analyse":      labo_config["analyse"],
    })

    while web_server._app_state == "labo":
        action = _get_action(timeout=0.5)
        if action is None:
            continue
        atype = action.get("type", "")

        if atype == "back_menu":
            session.quit()
            try: nl.disconnect()
            except Exception as e:
                logger.warning(f"[LABO] Déconnexion échiquier échouée : {e}")
            set_virtual_board(None)
            web_server._app_state = "menu"
            set_app_state("menu")
            return

        elif atype == "labo_set_config":
            engine_changed = False
            color_changed  = False
            for k in ("human_color", "engine_type", "engine_elo", "maia_elo", "rodent_elo", "rodent_personality", "analyse"):
                if k in action and action[k] != labo_config.get(k):
                    if k == "human_color":
                        color_changed = True
                    else:
                        engine_changed = True
                    labo_config[k] = action[k]

            if color_changed and not engine_changed:
                new_ec = chess.BLACK if labo_config["human_color"] == "white" else chess.WHITE
                session.engine_color = new_ec
                send_event("labo_init", {
                    "fen":          session.board.board_fen(),
                    "human_color":  labo_config["human_color"],
                    "engine_label": session.engine_label,
                    "analyse":      labo_config["analyse"],
                })
                session._send_position()
                if session._auto_on and session.board.turn == new_ec and not session._engine_busy:
                    session.do_engine_play()

            elif engine_changed:
                old_board   = session.board
                old_history = session._fen_history[:]
                session._running = False
                time.sleep(0.2)
                try:
                    session = _make_labo_session(nl, labo_config)
                    session.board        = old_board
                    session._fen_history = old_history
                    nl.game_board        = session.board.copy()
                    session._running     = True
                    if virtual_mode:
                        nl.make_virtual_board_watcher(session).start()
                    else:
                        threading.Thread(target=session.board_watcher, daemon=True).start()
                    send_event("labo_init", {
                        "fen":          session.board.board_fen(),
                        "human_color":  labo_config["human_color"],
                        "engine_label": session.engine_label,
                        "analyse":      labo_config["analyse"],
                    })
                    session._send_position()
                except Exception as e:
                    logger.error(f"[LABO] Erreur recréation : {e}")

        elif atype == "best_move":
            _aq = get_action_queue()
            while not _aq.empty():
                try:
                    peek = _aq.queue[0]
                    if peek.get("type") == "best_move":
                        _aq.get_nowait()
                    else:
                        break
                except Exception:
                    break  # queue modifiée concurremment pendant le peek — on arrête le dédoublonnage, sans conséquence
            session.do_best_move()

        elif atype == "engine_auto":
            val = action.get("value", not session._auto_on)
            session._auto_on = val
            send_event("labo_auto", {"auto": val})
            if val:
                if not virtual_mode:
                    session.sync_from_physical(turn=labo_config.get("active_turn", session.active_turn))
                time.sleep(0.1)
                _aq = get_action_queue()
                saved = []
                while not _aq.empty():
                    try:
                        pending = _aq.get_nowait()
                        if pending.get("type") == "engine_auto":
                            pval = pending.get("value", not session._auto_on)
                            session._auto_on = pval
                            send_event("labo_auto", {"auto": pval})
                        else:
                            saved.append(pending)
                    except Exception:
                        break  # queue modifiée concurremment — on arrête le tri, les actions déjà extraites sont remises ci-dessous
                for a in saved:
                    _aq.put_nowait(a)
                if session._auto_on and session.board.turn == session.engine_color and not session._engine_busy:
                    session.do_engine_play()

        elif atype == "analyse_position":
            session.do_analyse()

        elif atype == "undo_labo":
            session.do_undo()

        elif atype == "source_physique":
            _copy_cancel.set()
            time.sleep(0.1)
            turn = action.get("turn", session.active_turn)
            session.sync_from_physical(turn=turn)
            time.sleep(0.1)
            if session._auto_on and session.board.turn == session.engine_color and not session._engine_busy:
                session.do_engine_play()

        elif atype == "labo_set_turn":
            turn = action.get("turn", "white")
            labo_config["active_turn"] = turn
            session.active_turn = turn

        elif atype == "set_analyse":
            session.analyse_active = action.get("value", True)
            try: session.engine.analyse_active = session.analyse_active
            except Exception as e:
                logger.warning(f"[LABO] Application de analyse_active sur le moteur échouée : {e}")

        elif atype == "labo_copy_to_board":
            target_fen = action.get("fen", "")
            if target_fen:
                if virtual_mode:
                    try:
                        fen_clean = target_fen.strip().split()[0] if " " in target_fen else target_fen
                        session.set_board_from_fen(target_fen)
                        send_event("position_ok", {"fen": fen_clean})
                    except Exception as e:
                        logger.error(f"[LABO] set_board_from_fen virtuel : {e}")
                else:
                    _copy_cancel.set()
                    time.sleep(0.1)
                    def _copy_thread(fen=target_fen):
                        _do_copy_to_board(fen)
                        if not _copy_cancel.is_set():
                            try:
                                session.set_board_from_fen(fen)
                            except Exception as e:
                                logger.error(f"[LABO] set_board_from_fen : {e}")
                    threading.Thread(target=_copy_thread, daemon=True).start()

    _copy_cancel.set()
    session.quit()
    try: nl.disconnect()
    except Exception as e:
        logger.warning(f"[LABO] Déconnexion échiquier échouée : {e}")
    web_server._app_state = "menu"
    set_app_state("menu")


def _do_copy_to_board(target_fen: str) -> None:
    """Guide l'utilisateur pour reproduire un FEN cible sur le plateau physique."""
    nl = get_nl_inst_ref()
    if nl is None:
        return
    target = target_fen.strip().split()[0] if " " in target_fen else target_fen
    _copy_cancel.clear()

    send_event("labo_copy_start", {"target_fen": target})

    prev_fen = None
    while not _copy_cancel.is_set():
        try:
            raw = nl.get_fen()
            board_fen = raw.strip().split()[0] if raw else ""
            if board_fen == prev_fen:
                if board_fen == target:
                    nl.turn_off_all_leds()
                    send_event("position_ok", {"fen": target})
                    return
                send_event("position_error", {
                    "expected_fen": target,
                    "physical_fen": board_fen,
                })
            prev_fen = board_fen
        except Exception as e:
            logger.debug(f"[LABO] Lecture FEN échouée pendant copy_to_board : {e}")
        time.sleep(0.3)
    nl.turn_off_all_leds()
