"""
Test bonus (issue #264, suite #263) — démarrage du mode Humain contre Humain
avec un échiquier virtuel, jusqu'après l'enregistrement de l'historique
initial. Verrouille la régression #264 (web_server.set_history inexistant
sur app_state_proxy) de bout en bout, sans matériel ni serveur Flask-SocketIO.

GameWeb est remplacé par un double léger : le test ne porte pas sur la
logique de partie HH, mais sur le câblage game_manager → ihm_port avant la
création de la partie (création du plateau virtuel, set_history, init_hh,
set_app_state).
"""
import nicsoft.core.game_manager as gm
import nicsoft.modes.humain.human as human_mod
from nicsoft.core import ihm_port

FEN_INITIALE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


class _RecordingBackend(ihm_port._NullBackend):
    """Backend de test — hérite du backend neutre, trace set_history()."""

    def __init__(self):
        super().__init__()
        self.history_calls = []

    def set_history(self, history, history_fen):
        self.history_calls.append((list(history), list(history_fen)))


class _FakeGameWeb:
    """Double de GameWeb — ne crée aucun thread, aucun fichier PGN."""

    def __init__(self, nl_inst, white_name="Anonyme1", black_name="Anonyme2",
                 default_game_type="Serious", **kwargs):
        self.nl_inst = nl_inst
        self.white_name = white_name
        self.black_name = black_name
        self.default_game_type = default_game_type
        self.game_over = False

    def save_pgn_tmp(self, *args, **kwargs):
        pass

    def start(self):
        self.game_over = True


def test_run_humain_virtuel_enregistre_historique_initial(monkeypatch):
    """_run_humain(virtual=True) doit appeler set_history([], [FEN_INITIALE])
    via le port — sans lever AttributeError — avant de démarrer la partie."""
    backend = _RecordingBackend()
    monkeypatch.setattr(ihm_port, "_backend", backend)
    monkeypatch.setattr(human_mod, "GameWeb", _FakeGameWeb)

    _error = {"occurred": False, "toast_key": None}
    gm._run_humain("Alice", "Bob", "Serious", _error, virtual=True)

    assert _error["occurred"] is False, _error
    assert backend.history_calls == [([], [FEN_INITIALE])]
    assert backend.get_app_state() == "game_over"
