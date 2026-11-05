"""
nicsoft/core/ihm_port.py — NicLink
Port neutre entre les modules de jeu (core, modes, niclink, utils, engine)
et l'IHM. Règle ARC-001 : le moteur ne connaît pas l'interface — aucun de
ces modules n'importe nicsoft.web.

Les modules de jeu passent exclusivement par les fonctions de ce fichier
(send_event, get_action, set_app_state, ...). Au démarrage réel de
l'application, nicsoft.web.alchess fournit l'implémentation concrète via
register_backend() ; tant qu'aucun backend n'est branché (import des
modules de jeu en test, en bibliothèque, etc.), un backend neutre
(_NullBackend) répond sans effet de bord.
"""

import queue


class _NullBackend:
    """Backend par défaut avant branchement de la couche web."""

    def __init__(self):
        self.action_queue = queue.Queue()
        self._app_state = "menu"

    def send_event(self, event_type, data):
        pass

    def emit(self, event_type, data):
        pass

    def set_history(self, history, history_fen):
        pass

    def get_history(self):
        return [], []

    def get_init_data(self):
        return {}

    def get_action(self, timeout=0.0):
        return None

    def set_app_state(self, state, data=None):
        self._app_state = state

    def get_menu_action(self, timeout=1.0):
        return None

    def set_virtual_board(self, vb):
        pass

    def get_app_state(self):
        return self._app_state

    def set_raw_app_state(self, state):
        self._app_state = state

    def check_board_at_startup(self):
        pass


_backend = _NullBackend()


def register_backend(backend) -> None:
    """Branché par nicsoft.web.alchess au démarrage — bascule le port vers
    l'implémentation Flask-SocketIO réelle."""
    global _backend
    _backend = backend


def send_event(event_type: str, data: dict) -> None:
    """Envoie un événement de jeu au navigateur."""
    _backend.send_event(event_type, data)


def emit(event_type: str, data: dict) -> None:
    """Émission SocketIO directe (hors event_queue), ex. popups ponctuels."""
    _backend.emit(event_type, data)


def set_history(history: list, history_fen: list) -> None:
    """Remplace atomiquement l'historique de partie côté IHM."""
    _backend.set_history(history, history_fen)


def get_history() -> tuple:
    """Lit atomiquement (history, history_fen) depuis l'IHM."""
    return _backend.get_history()


def get_init_data() -> dict:
    """Lit le payload envoyé par le dernier événement 'init' (fen, player,
    color, ... — voir game_manager._run_pedagogique). Utilisé pour
    recomposer l'état de fin de partie (titre, historique...)."""
    return _backend.get_init_data()


def get_action(timeout: float = 0.0):
    """Récupère une action du joueur (navigateur). None si aucune."""
    return _backend.get_action(timeout)


def set_app_state(state: str, data: dict = None) -> None:
    """Change l'état de l'application et notifie le navigateur."""
    _backend.set_app_state(state, data)


def get_menu_action(timeout: float = 1.0):
    """Récupère une action du menu. None si timeout."""
    return _backend.get_menu_action(timeout)


def set_virtual_board(vb) -> None:
    """Déclare l'échiquier virtuel courant à l'IHM (mode sans hardware)."""
    _backend.set_virtual_board(vb)


def get_action_queue() -> queue.Queue:
    """File d'actions navigateur → jeu brute — utilisée là où le code
    gère lui-même la queue (vidage, get_nowait, compteurs d'annulation)."""
    return _backend.action_queue


def get_app_state() -> str:
    """Lecture brute de l'état d'application (sans passer par set_app_state)."""
    return _backend.get_app_state()


def set_raw_app_state(state: str) -> None:
    """Écriture brute de l'état d'application, sans notifier le navigateur —
    même sémantique que l'ancien accès direct à web.server._app_state."""
    _backend.set_raw_app_state(state)


def check_board_at_startup() -> None:
    """Relance la vérification de présence du plateau physique."""
    _backend.check_board_at_startup()


class _AppStateProxy:
    """Façade compatible avec l'ancien accès direct au module
    nicsoft.web.server (`web_server._app_state`, `web_server.action_queue`)
    — permet de migrer les sites d'usage existants sans les réécrire."""

    @property
    def _app_state(self):
        return _backend.get_app_state()

    @_app_state.setter
    def _app_state(self, value):
        _backend.set_raw_app_state(value)

    @property
    def action_queue(self):
        return _backend.action_queue


app_state_proxy = _AppStateProxy()
