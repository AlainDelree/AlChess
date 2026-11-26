"""
nicsoft/tests/test_issue390_puzzle_fen_actions.py — AlChess

Issue #390, point 3 : copie du FEN / analyse externe après la fin d'un
problème Lichess — boutons visibles/utilisables UNIQUEMENT une fois le
problème terminé (fair-play : aucune aide pendant la résolution).

Ce fichier couvre la partie serveur (le FEN de départ — `setup_fen` —
transmis dans le payload "lichess_puzzle_playing", déjà connu avant la
fin, mais les boutons qui s'en servent restent cachés côté client jusqu'au
résultat) et des gardes statiques sur index.html/app.js pour la partie
client (emplacement des boutons, encodage de l'adresse). Entièrement sans
réseau (get_next_puzzle/submit_puzzle_result monkeypatchés) et sans
matériel (mode virtuel, comme test_issue387_lichess_puzzle_session.py)."""

import pathlib
import queue
import re
import threading
import time

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.puzzle_game as puzzle_game_mod

HTML_PATH = pathlib.Path(__file__).parent.parent / "web" / "templates" / "index.html"
APP_JS_PATH = pathlib.Path(__file__).parent.parent / "web" / "static" / "app.js"


def _html():
    return HTML_PATH.read_text(encoding="utf-8")


def _app_js():
    return APP_JS_PATH.read_text(encoding="utf-8")


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _FakeGameLog:
    def __init__(self, *a, **k):
        pass

    def state_change(self, *a, **k):
        pass

    def exception(self, *a, **k):
        pass

    def close(self):
        pass


# ── Garde statique : boutons FEN uniquement dans le panneau de résultat ──

def test_boutons_fen_sont_dans_le_panneau_de_resultat_cache_par_defaut():
    html = _html()
    match = re.search(r'<div id="lichess-puzzle-result"[^>]*>', html)
    assert match, "#lichess-puzzle-result introuvable"
    assert 'style="display:none;"' in match.group(0), (
        "#lichess-puzzle-result doit être caché par défaut (affiché seulement "
        "au résultat, voir socket.on('lichess_puzzle_result'))"
    )
    result_start = match.start()
    # Les boutons FEN doivent être situés APRÈS le début de ce bloc caché et
    # avant sa fermeture (donc jamais visibles/actifs hors de cet état).
    end = html.index("</div>", html.index('id="lichess-puzzle-result-actions"'))
    block = html[result_start:end]
    assert 'id="lichess-puzzle-btn-copy-fen"' in block
    assert 'id="lichess-puzzle-btn-analyse-lichess"' in block


def test_boutons_fen_absents_du_panneau_pendant_le_jeu():
    """Rien de tel ailleurs dans l'écran #screen-lichess-puzzle, en
    particulier pas dans les bandeaux affichés PENDANT la résolution
    (lichess-puzzle-turn-banner, promotion, illégal...)."""
    html = _html()
    screen_start = html.index('id="screen-lichess-puzzle"')
    result_start = html.index('id="lichess-puzzle-result"', screen_start)
    before_result = html[screen_start:result_start]
    assert "lichess-puzzle-btn-copy-fen" not in before_result
    assert "lichess-puzzle-btn-analyse-lichess" not in before_result


def test_fonctions_fen_utilisent_encodeuri_jamais_encodeuricomponent_sur_le_fen():
    js = _app_js()
    func = js[js.index("function _lichessPuzzleAnalyseOnLichess"):]
    func = func[:func.index("\n}\n") + 3]
    assert "encodeURI(fen)" in func
    assert "encodeURIComponent(fen)" not in func


def test_copie_fen_valide_avant_utilisation():
    js = _app_js()
    func = js[js.index("function _lichessPuzzleCopyFen"):]
    func = func[:func.index("\n}\n") + 3]
    assert "_isLikelyValidFen(fen)" in func
    func2 = js[js.index("function _lichessPuzzleAnalyseOnLichess"):]
    func2 = func2[:func2.index("\n}\n") + 3]
    assert "_isLikelyValidFen(fen)" in func2


# ── Intégration serveur : setup_fen transmis dès le début du problème ───

def test_setup_fen_transmis_dans_lichess_puzzle_playing_mode_virtuel(monkeypatch):
    events = []
    actions = queue.Queue()
    sent_states = []

    def fake_get_action(timeout=0.0):
        try:
            return actions.get(timeout=timeout)
        except queue.Empty:
            return None

    monkeypatch.setattr(puzzle_game_mod, "send_event", lambda e, d: events.append((e, d)))
    monkeypatch.setattr(puzzle_game_mod, "get_action", fake_get_action)
    monkeypatch.setattr(lichess_launcher, "get_action", fake_get_action)
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_token": "lip_test_token", "lichess_puzzle_session_size": 1,
    })
    monkeypatch.setattr(lichess_launcher, "check_board_presence_silent", lambda: None)

    import nicsoft.modes.lichess.client as lichess_client
    monkeypatch.setattr(lichess_client, "test_token", lambda token: {
        "status": "ok", "account": "", "has_puzzle_read": True, "has_puzzle_write": True,
    })

    start = chess.Board()
    setup_fen = start.fen()  # distinct de "fen" ci-dessous (position après le 1er coup adverse)
    tactical = start.copy()
    tactical.push_uci("e2e4")
    puzzle = {
        "puzzle_id": "pzl_fen", "rating": 1500, "themes": ["fork"], "solution": ["d7d5"],
        "fen": tactical.fen(), "setup_fen": setup_fen, "opponent_first_move": "e2e4",
        "game_id": "g1", "rated": True, "players": [],
    }

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_next_puzzle", lambda token, difficulty=None, angle=None: {
        "status": "ok", **puzzle,
    })
    monkeypatch.setattr(puzzle_game_mod, "submit_puzzle_result", lambda *a, **kw: {
        "status": "ok", "rating_diff": 3, "new_rating": 1503,
    })
    import nicsoft.modes.lichess.game_log as game_log_mod
    monkeypatch.setattr(game_log_mod, "GameLog", _FakeGameLog)

    lichess_launcher.web_server._app_state = "config_lichess"

    def _drive():
        assert _wait_until(lambda: lichess_launcher.web_server._app_state == "lichess_puzzle_playing")
        assert _wait_until(lambda: any(e == "lichess_puzzle_your_turn" for e, _ in events))
        actions.put({"type": "lichess_puzzle_virtual_move", "from": "d7", "to": "d5"})
        assert _wait_until(lambda: any(d.get("win") is True for e, d in events if e == "lichess_puzzle_result"))
        actions.put({"type": "back_menu"})

    driver = threading.Thread(target=_drive, daemon=True)
    launcher_thread = threading.Thread(
        target=lambda: lichess_launcher.launch_lichess_puzzle({"player": "Alain", "puzzle_mode": "virtual"}),
        daemon=True,
    )
    driver.start()
    launcher_thread.start()
    try:
        launcher_thread.join(timeout=5.0)
    finally:
        driver.join(timeout=1.0)
        lichess_launcher.web_server._app_state = "menu"

    assert not launcher_thread.is_alive()
    playing_states = [d for s, d in sent_states if s == "lichess_puzzle_playing"]
    assert len(playing_states) == 1
    assert playing_states[0]["setup_fen"] == setup_fen
    assert playing_states[0]["fen"] != setup_fen  # bien la position du problème, pas la mise en place
