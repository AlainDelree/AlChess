"""
nicsoft/tests/test_issue295_mode_cleanup.py — NicLink
Issue #295, point 3 : observation non traitée de l'issue #292 — les modes
Humain contre Humain et Labo ne fermaient jamais la connexion de
l'échiquier à la fin de leur session (contrairement aux modes
Pédagogique, Exercices et Explorateur, déjà corrigés), avec le même risque
de fil de lecture USB (fen_reader) orphelin.

Ces tests vérifient, sans matériel, que chacun de ces modes appelle
désormais nl_inst.disconnect() en fin de session — y compris sur un
abandon (sortie par exception) et pas seulement en fin de partie normale.
"""
import chess
import pytest

import nicsoft.core.game_manager_modes.humain as humain_launcher
import nicsoft.core.game_manager_modes.labo as labo_launcher
import nicsoft.core.game_manager_modes.labo_session as labo_session_mod
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode


class _FakeNl:
    """Double léger d'un échiquier connecté — trace turn_off_all_leds()/disconnect()."""

    def __init__(self):
        self.leds_off = False
        self.disconnected = False

    def turn_off_all_leds(self):
        self.leds_off = True

    def disconnect(self):
        self.disconnected = True

    def get_fen(self):
        return chess.STARTING_FEN


@pytest.fixture(autouse=True)
def _reset_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ── Mode Humain contre Humain ────────────────────────────────────────────────

class _FakeGameWeb:
    def __init__(self, nl_inst, white_name="Anonyme1", black_name="Anonyme2",
                 default_game_type="Serious", **kwargs):
        self.nl_inst = nl_inst
        self.game_over = False

    def save_pgn_tmp(self, *a, **kw):
        pass

    def start(self):
        self.game_over = True


class _FakeGameWebAbandon(_FakeGameWeb):
    """Simule un abandon (pièces mal placées) : start() lève une exception,
    comme le ferait await_move() sur une position qui ne correspondra
    jamais à celle attendue par la partie."""

    def start(self):
        raise ConnectionError("Timeout — position non atteinte.")


def test_run_humain_disconnecte_echiquier_fin_normale(monkeypatch):
    nl = _FakeNl()
    monkeypatch.setattr(humain_launcher, "create_board", lambda **kw: nl)
    monkeypatch.setattr(humain_launcher, "_wait_initial_position_web", lambda nl_inst: None)
    import nicsoft.modes.humain.human as human_mod
    monkeypatch.setattr(human_mod, "GameWeb", _FakeGameWeb)

    _error = {"occurred": False, "toast_key": None}
    humain_launcher._run_humain("Alice", "Bob", "Serious", _error, virtual=False)

    assert nl.leds_off is True
    assert nl.disconnected is True
    assert _error["occurred"] is False


def test_run_humain_disconnecte_echiquier_sur_abandon(monkeypatch):
    """Abandon (pièces mal placées → ConnectionError levée pendant la
    partie) : la fermeture de l'échiquier doit avoir lieu quand même."""
    nl = _FakeNl()
    monkeypatch.setattr(humain_launcher, "create_board", lambda **kw: nl)
    monkeypatch.setattr(humain_launcher, "_wait_initial_position_web", lambda nl_inst: None)
    import nicsoft.modes.humain.human as human_mod
    monkeypatch.setattr(human_mod, "GameWeb", _FakeGameWebAbandon)

    _error = {"occurred": False, "toast_key": None}
    humain_launcher._run_humain("Alice", "Bob", "Serious", _error, virtual=False)

    assert nl.disconnected is True
    assert _error["occurred"] is True


# ── Mode Labo ────────────────────────────────────────────────────────────────

class _FakeLaboFullSession:
    """Double de LaboSession utilisé via _make_labo_session dans _run_labo_session."""

    def __init__(self, nl_inst, config):
        self.nl_inst = nl_inst
        self.board = chess.Board()
        self.engine_label = "Stockfish ~1500elo"
        self._auto_on = False
        self._engine_busy = False
        self.engine_color = chess.BLACK
        self.quit_called = False

    def board_watcher(self):
        pass

    def sync_from_physical(self, *a, **kw):
        pass

    def _send_position(self, *a, **kw):
        pass

    def quit(self):
        self.quit_called = True


class _FakeWebServerLabo:
    """Remplace app_state_proxy dans labo_session.py pour ces tests."""
    _app_state = "labo"


def _patch_labo_session_io(monkeypatch, nl, actions):
    """Neutralise les sorties IHM utilisées par _run_labo_session et fournit
    une file d'actions scriptée."""
    actions = list(actions)

    def fake_get_action(timeout=0.0):
        return actions.pop(0) if actions else None

    monkeypatch.setattr(labo_session_mod, "get_nl_inst_ref", lambda: nl)
    monkeypatch.setattr(labo_session_mod, "get_virtual_mode", lambda: False)
    monkeypatch.setattr(labo_session_mod, "get_action", fake_get_action)
    monkeypatch.setattr(labo_session_mod, "send_event", lambda *a, **k: None)
    monkeypatch.setattr(labo_session_mod, "set_app_state", lambda *a, **k: None)
    monkeypatch.setattr(labo_session_mod, "set_virtual_board", lambda vb: None)
    monkeypatch.setattr(labo_launcher, "_make_labo_session",
                        lambda nl_inst, config: _FakeLaboFullSession(nl_inst, config))


def test_run_labo_session_disconnecte_echiquier_au_retour_menu(monkeypatch):
    """Retour au menu explicite (action 'back_menu', bouton utilisateur)."""
    nl = _FakeNl()
    web_server = _FakeWebServerLabo()
    web_server._app_state = "labo"
    monkeypatch.setattr(labo_session_mod, "web_server", web_server)
    _patch_labo_session_io(monkeypatch, nl, [{"type": "back_menu"}])

    labo_session_mod._run_labo_session()

    assert nl.disconnected is True
    assert web_server._app_state == "menu"


def test_run_labo_session_disconnecte_echiquier_sur_abandon(monkeypatch):
    """« Abandon » du labo : la session se termine par un changement
    d'état externe (ex. l'utilisateur quitte par un autre chemin que
    l'action back_menu) plutôt que par l'action back_menu elle-même —
    la fermeture de l'échiquier doit avoir lieu dans les deux cas."""
    nl = _FakeNl()
    web_server = _FakeWebServerLabo()
    web_server._app_state = "labo"
    monkeypatch.setattr(labo_session_mod, "web_server", web_server)

    calls = {"n": 0}

    def fake_get_action(timeout=0.0):
        calls["n"] += 1
        if calls["n"] == 2:
            web_server._app_state = "menu"  # abandon : changement d'état hors action back_menu
        return None

    monkeypatch.setattr(labo_session_mod, "get_nl_inst_ref", lambda: nl)
    monkeypatch.setattr(labo_session_mod, "get_virtual_mode", lambda: False)
    monkeypatch.setattr(labo_session_mod, "get_action", fake_get_action)
    monkeypatch.setattr(labo_session_mod, "send_event", lambda *a, **k: None)
    monkeypatch.setattr(labo_session_mod, "set_app_state", lambda *a, **k: None)
    monkeypatch.setattr(labo_session_mod, "set_virtual_board", lambda vb: None)
    monkeypatch.setattr(labo_launcher, "_make_labo_session",
                        lambda nl_inst, config: _FakeLaboFullSession(nl_inst, config))

    labo_session_mod._run_labo_session()

    assert nl.disconnected is True


def test_poll_board_fen_labo_filet_de_securite_disconnecte(monkeypatch):
    """Filet de sécurité de labo.py:_poll_board_fen_labo — si la session ne
    démarre jamais (ex. _make_labo_session échoue avant que
    _run_labo_session n'ait pu fermer la connexion), le fil de poll doit
    tout de même libérer l'échiquier à sa sortie."""
    nl = _FakeNl()
    monkeypatch.setattr(labo_launcher, "create_board", lambda **kw: nl)
    monkeypatch.setattr(labo_launcher, "set_nl_inst_ref", lambda n: None)

    class _ImmediateMenuWebServer:
        _app_state = "menu"  # déjà hors "labo" — la boucle de poll ne s'exécute pas

    monkeypatch.setattr(labo_launcher, "web_server", _ImmediateMenuWebServer)

    labo_launcher._poll_board_fen_labo()

    assert nl.disconnected is True
