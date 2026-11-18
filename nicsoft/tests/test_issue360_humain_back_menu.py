"""
nicsoft/tests/test_issue360_humain_back_menu.py — NicLink
Issue #360, partie 1 : retour au menu du mode Humain contre Humain aligné
sur le schéma déjà en place dans modes/pedagogique/pedagogique.py —
BackMenuExit levée par GameWeb._traiter_abandon() (branche back_menu) au
lieu de sys.exit(0), capturée dans le lanceur (core/game_manager_modes/
humain.py) — et le except Exception autour de await_move() ne doit plus
avaler ExitNicLink indistinctement.

Faux échiquier (VirtualBoard) uniquement, aucun matériel ni serveur Flask
réel — GAMES_DIR isolé vers tmp_path par le fixture autouse de conftest.py.
"""
import logging
import queue
import threading
import time

import nicsoft.core.game_manager_modes.humain as humain_launcher
from nicsoft.core import ihm_port
from nicsoft.modes.humain.human import GameWeb
from nicsoft.niclink.nl_exceptions import ExitNicLink
from nicsoft.niclink.virtual_board import VirtualBoard


class _TestBackend(ihm_port._NullBackend):
    """Backend de test — _NullBackend.get_action() ignore action_queue ;
    ce backend le lit réellement pour simuler l'arrivée d'une action
    navigateur (back_menu) pendant l'attente d'un coup."""

    def __init__(self):
        super().__init__()
        self.events = []

    def get_action(self, timeout=0.0):
        try:
            return self.action_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def send_event(self, event_type, data):
        self.events.append((event_type, data))


def test_retour_menu_hh_thread_de_jeu_se_termine_proprement(monkeypatch):
    """Chemin réel : launch_humain() démarre le thread de jeu (GameWeb via
    VirtualBoard), un back_menu survient pendant l'attente du coup — le
    thread se termine proprement (BackMenuExit n'est pas traitée comme un
    crash) et launch_humain() reprend la main avec l'état menu."""
    backend = _TestBackend()
    monkeypatch.setattr(ihm_port, "_backend", backend)
    monkeypatch.setattr(humain_launcher, "get_virtual_mode", lambda: True)

    def _inject_back_menu():
        deadline = time.time() + 5.0
        while time.time() < deadline and backend.get_app_state() != "playing":
            time.sleep(0.02)
        backend.action_queue.put({"type": "back_menu"})

    injector = threading.Thread(target=_inject_back_menu, daemon=True)
    injector.start()

    humain_launcher.launch_humain({"white": "Alice", "black": "Bob", "color": "white"})
    injector.join(timeout=5.0)

    assert not injector.is_alive(), "l'injection du back_menu n'a jamais vu l'état 'playing'"
    assert backend.get_app_state() == "menu", (
        "launch_humain() doit reprendre la main avec l'état menu après un back_menu"
    )
    assert not any(ev == "board_error" for ev, _ in backend.events), (
        "le retour au menu HH ne doit jamais être signalé comme une erreur d'échiquier "
        "(régression : BackMenuExit tombant dans le except Exception générique du lanceur)"
    )


def test_except_await_move_ne_classe_plus_exitniclink_via_kill_switch(caplog):
    """GameWeb._handle_turn() : l'exception ExitNicLink venant de
    await_move() doit être reconnue par son type (except ExitNicLink dédié),
    pas en relisant kill_switch.is_set() après coup dans un except Exception
    générique — sinon une ExitNicLink levée alors que kill_switch est déjà
    retombé à False serait journalisée comme un échec générique au lieu
    d'une interruption normale."""
    vb = VirtualBoard()

    class _NeverSetKillSwitch:
        def is_set(self):
            return False  # délibérément False — l'ancien code se basait sur cet état

    vb.kill_switch = _NeverSetKillSwitch()

    def _raise_exit_niclink():
        raise ExitNicLink("test : interruption simulée")

    vb.await_move = _raise_exit_niclink

    game = GameWeb(vb, white_name="Alice", black_name="Bob")

    with caplog.at_level(logging.INFO, logger="NL play Human"):
        result = game._handle_turn()

    assert result is None
    messages = [r.message for r in caplog.records]
    assert any("interrompu" in m for m in messages), (
        "ExitNicLink doit être journalisée comme une interruption normale"
    )
    assert not any("a echoue, coup non detecte" in m for m in messages), (
        "ExitNicLink ne doit plus être avalée/classée par le except Exception générique"
    )
