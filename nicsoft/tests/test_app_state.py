"""
Tests Niveau 2 — Transitions d'état serveur

Teste les transitions _app_state, le routage des queues et la mise à jour
de _game_state en Python pur, sans navigateur ni échiquier physique.
"""
import pytest
from unittest.mock import patch
import nicsoft.web.server as server


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_state():
    """Remet le serveur dans un état propre entre chaque test."""
    server._app_state = "menu"
    server._game_state = {}
    server._board_status = None
    server._board_error_message = ""
    for q in (server.action_queue, server.menu_queue, server.event_queue):
        while not q.empty():
            q.get_nowait()
    yield
    for q in (server.action_queue, server.menu_queue, server.event_queue):
        while not q.empty():
            q.get_nowait()


# ── set_app_state ─────────────────────────────────────────────────────────────

def test_set_app_state_change():
    with patch.object(server.socketio, "emit"):
        server.set_app_state("playing")
    assert server._app_state == "playing"


def test_set_app_state_retour_menu():
    server._app_state = "playing"
    with patch.object(server.socketio, "emit"):
        server.set_app_state("menu")
    assert server._app_state == "menu"


def test_set_app_state_game_over_skip_ne_crase_pas_menu():
    """game_over avec skip=True ne doit pas écraser _app_state si déjà 'menu'."""
    server._app_state = "menu"
    with patch.object(server.socketio, "emit"):
        server.set_app_state("game_over", {"skip": True})
    assert server._app_state == "menu"


def test_set_app_state_game_over_sans_skip_ecrase():
    server._app_state = "playing"
    with patch.object(server.socketio, "emit"):
        server.set_app_state("game_over", {})
    assert server._app_state == "game_over"


# ── on_action — back_menu ─────────────────────────────────────────────────────

ETATS_ACTIFS = [
    "playing", "connecting", "game_over", "paused",
    "labo", "exercice_running", "retrans_playing",
]

@pytest.mark.parametrize("etat", ETATS_ACTIFS)
def test_back_menu_depuis_etat_actif(etat):
    """back_menu depuis un état actif → _app_state='menu' + événement dans action_queue."""
    server._app_state = etat
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": "back_menu"})
    assert server._app_state == "menu"
    assert not server.action_queue.empty()
    assert server.action_queue.get_nowait()["type"] == "back_menu"


def test_back_menu_depuis_menu_ne_met_pas_dans_action_queue():
    """back_menu depuis 'menu' → rien dans action_queue."""
    server._app_state = "menu"
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": "back_menu"})
    assert server._app_state == "menu"
    assert server.action_queue.empty()


def test_exercice_back_depuis_exercice_running():
    """exercice_back → _app_state='exercices' + action dans action_queue."""
    server._app_state = "exercice_running"
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": "exercice_back"})
    assert server._app_state == "exercices"
    assert not server.action_queue.empty()


# ── on_action — routage action_queue vs menu_queue ───────────────────────────

@pytest.mark.parametrize("etat", ["playing", "connecting", "game_over", "paused", "labo"])
def test_action_en_cours_de_partie_va_dans_action_queue(etat):
    server._app_state = etat
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": "reprendre"})
    assert not server.action_queue.empty()
    assert server.menu_queue.empty()


def test_action_depuis_menu_va_dans_menu_queue():
    server._app_state = "menu"
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": "start_pedagogique"})
    assert server.action_queue.empty()
    assert not server.menu_queue.empty()


# ── send_event — mise à jour _game_state ─────────────────────────────────────

def test_send_event_init_reinitialise_historique():
    server._game_state = {
        "fen": "fen_ancienne",
        "history": [{"san": "e4"}, {"san": "e5"}],
        "feedback": {"type": "bon"},
    }
    server.send_event("init", {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"})
    assert server._game_state["history"] == []
    assert "feedback" not in server._game_state


def test_send_event_move_ajoute_dans_historique():
    server._game_state = {"fen": "debut", "history": []}
    server.send_event("move", {"fen": "fen2", "san": "e4"})
    server.send_event("move", {"fen": "fen3", "san": "e5"})
    assert len(server._game_state["history"]) == 2
    assert server._game_state["history"][0]["san"] == "e4"
    assert server._game_state["history"][1]["san"] == "e5"


def test_send_event_undo_move_retire_n_coups():
    server._game_state = {
        "fen": "fen3",
        "history": [{"san": "e4"}, {"san": "e5"}, {"san": "d4"}],
        "history_fen": ["start", "fen1", "fen2", "fen3"],
    }
    server.send_event("undo_move", {"count": 2, "fen": "fen1"})
    assert len(server._game_state["history"]) == 1
    assert server._game_state["history"][0]["san"] == "e4"
    assert server._game_state["fen"] == "fen1"


def test_send_event_undo_move_count_1():
    server._game_state = {
        "fen": "fen2",
        "history": [{"san": "e4"}, {"san": "e5"}],
        "history_fen": ["start", "fen1", "fen2"],
    }
    server.send_event("undo_move", {"count": 1, "fen": "fen1"})
    assert len(server._game_state["history"]) == 1
    assert server._game_state["history"][0]["san"] == "e4"


def test_send_event_undo_move_historique_vide_ne_plante_pas():
    server._game_state = {"history": [], "history_fen": ["start"], "fen": "start"}
    server.send_event("undo_move", {"count": 3, "fen": "start"})
    assert server._game_state["history"] == []


def test_send_event_game_over_supprime_feedback():
    server._game_state = {"feedback": {"type": "bon"}, "history": []}
    server.send_event("game_over", {})
    assert "feedback" not in server._game_state
