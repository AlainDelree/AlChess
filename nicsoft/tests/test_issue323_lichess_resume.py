"""
nicsoft/tests/test_issue323_lichess_resume.py — AlChess

Issue #323 (étape L2b) : reprise d'une partie Lichess en cours depuis le
menu — détection (/api/account/playing), proposition dans le menu, écran
de mise en place (cases rouges + LED) jusqu'à ce que la position physique
reconstruite corresponde à celle de Lichess, puis reprise du jeu normal
(LichessGame, réutilisé tel quel). Livraison limitée au cas le plus simple
(partie amicale contre l'IA Lichess, variante standard) — voir le rapport
de clôture pour le reste.

Entièrement sans réseau (urllib.request.urlopen mocké pour le client,
faux transport scénarisé pour le flux de partie — voir test_issue307/309)
et sans matériel (FakeBoard, voir test_issue309).

Retrait du message éphémère « Nulle refusée » (point 7) : testé dans
test_issue310_lichess_corrections.py (clés i18n) — les nouveaux tests ici
se concentrent sur la reprise elle-même ; voir aussi les ajustements faits
directement dans test_issue310_lichess_corrections.py.
"""
import json
import queue
import threading
import time
from pathlib import Path

import chess
import pytest

import nicsoft.core.game_manager as gm
import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.game as game_mod
from nicsoft.modes.lichess import client as lichess_client
from nicsoft.modes.lichess.errors import (
    LichessApiError,
    LichessAuthError,
    LichessNetworkError,
    LichessRateLimitError,
)
from nicsoft.modes.lichess.game import LichessGame
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.tests.test_issue309_lichess_l2a import (
    FakeBoard,
    FakeTransport,
    _events_of,
    _line,
    _make_game,
    _make_recorder,
    _ok,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── Fixtures ──────────────────────────────────────────────────────────────────

class _FakeUrlResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=None):
        return self._body


def _fake_urlopen(body: dict):
    payload = json.dumps(body).encode("utf-8")
    return lambda req, timeout=None: _FakeUrlResponse(payload)


def _nowplaying_ai_standard(game_id="aBcD1234", color="white", opponent_ai=2,
                             speed="blitz", is_my_turn=True, seconds_left=580):
    return {
        "gameId": game_id, "fullId": game_id + color[0], "color": color,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
        "hasMoved": True, "isMyTurn": is_my_turn, "lastMove": "e2e4",
        "opponent": {"id": None, "username": f"Stockfish level {opponent_ai}", "ai": opponent_ai},
        "perf": speed, "rated": False, "rating": 1500, "secondsLeft": seconds_left,
        "source": "ai", "speed": speed, "variant": {"key": "standard", "name": "Standard"},
    }


# ═══════════════════════════════════════════════════════════════════════
# 1. client.get_ongoing_games() — détection (issue #323, point 1)
# ═══════════════════════════════════════════════════════════════════════

def test_get_ongoing_games_sans_jeton():
    assert lichess_client.get_ongoing_games("") == {"status": "invalid"}


def test_get_ongoing_games_401_est_invalide(monkeypatch):
    import urllib.error
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert lichess_client.get_ongoing_games("lip_x") == {"status": "invalid"}


def test_get_ongoing_games_429_est_rate_limited(monkeypatch):
    import urllib.error
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "too many", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert lichess_client.get_ongoing_games("lip_x") == {"status": "rate_limited"}


def test_get_ongoing_games_coupure_reseau(monkeypatch):
    import urllib.error
    def boom(req, timeout=None):
        raise urllib.error.URLError("pas de réseau")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert lichess_client.get_ongoing_games("lip_x") == {"status": "network_error"}


def test_get_ongoing_games_reponse_illisible_est_network_error(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeUrlResponse(b"pas du json"))
    assert lichess_client.get_ongoing_games("lip_x") == {"status": "network_error"}


def test_get_ongoing_games_aucune_partie_en_cours(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"nbMyTurn": 0, "nowPlaying": []}))
    result = lichess_client.get_ongoing_games("lip_x")
    assert result == {"status": "ok", "game": None, "total_candidates": 0}


def test_get_ongoing_games_filtre_hors_ia_et_hors_standard(monkeypatch):
    """Une partie humain-humain (source=friend) et une partie variante
    (chess960) ne sont jamais proposées dans cette livraison (issue #323 —
    cas le plus simple, voir rapport)."""
    non_ai = _nowplaying_ai_standard(game_id="human0001")
    non_ai["source"] = "friend"
    non_ai["opponent"] = {"id": "bob", "username": "bob"}
    variant = _nowplaying_ai_standard(game_id="var00001")
    variant["variant"] = {"key": "chess960", "name": "Chess960"}
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({
        "nbMyTurn": 2, "nowPlaying": [non_ai, variant],
    }))
    result = lichess_client.get_ongoing_games("lip_x")
    assert result == {"status": "ok", "game": None, "total_candidates": 0}


def test_get_ongoing_games_propose_la_partie_ia_standard(monkeypatch):
    game = _nowplaying_ai_standard(game_id="aBcD1234", color="black", opponent_ai=4,
                                    speed="rapid", is_my_turn=False, seconds_left=742)
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"nbMyTurn": 0, "nowPlaying": [game]}))
    result = lichess_client.get_ongoing_games("lip_x")
    assert result["status"] == "ok"
    assert result["total_candidates"] == 1
    assert result["game"] == {
        "game_id": "aBcD1234", "color": "black", "opponent": "Stockfish level 4",
        "ai_level": 4, "speed": "rapid", "is_my_turn": False, "seconds_left": 742,
    }


def test_get_ongoing_games_plusieurs_parties_propose_la_plus_urgente(monkeypatch):
    first = _nowplaying_ai_standard(game_id="first0001")
    second = _nowplaying_ai_standard(game_id="second002")
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({
        "nbMyTurn": 2, "nowPlaying": [first, second],
    }))
    result = lichess_client.get_ongoing_games("lip_x")
    assert result["total_candidates"] == 2
    assert result["game"]["game_id"] == "first0001"  # ordre Lichess conservé (la plus urgente)


# ═══════════════════════════════════════════════════════════════════════
# 2. check_lichess_resumable() — ouverture du menu Lichess, jamais alarmant
# ═══════════════════════════════════════════════════════════════════════

def test_check_lichess_resumable_sans_jeton_ne_propose_rien(monkeypatch):
    events = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": ""})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    lichess_launcher.check_lichess_resumable()
    assert events == [("lichess_resumable", {"available": False})]


def test_check_lichess_resumable_erreur_reseau_silencieuse(monkeypatch, caplog):
    events = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_secret_abcdef"})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))

    def boom(token):
        raise RuntimeError("panne réseau simulée")
    import nicsoft.modes.lichess.client as client_mod
    monkeypatch.setattr(client_mod, "get_ongoing_games", boom)

    with caplog.at_level("WARNING"):
        lichess_launcher.check_lichess_resumable()
    assert events == [("lichess_resumable", {"available": False})]
    assert "lip_secret_abcdef" not in caplog.text


def test_check_lichess_resumable_aucune_partie(monkeypatch):
    events = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    import nicsoft.modes.lichess.client as client_mod
    monkeypatch.setattr(client_mod, "get_ongoing_games",
                         lambda token: {"status": "ok", "game": None, "total_candidates": 0})
    lichess_launcher.check_lichess_resumable()
    assert events == [("lichess_resumable", {"available": False})]


def test_check_lichess_resumable_propose_la_partie_detectee(monkeypatch):
    events = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    game = {"game_id": "aBcD1234", "color": "white", "opponent": "Stockfish level 2",
            "ai_level": 2, "speed": "blitz", "is_my_turn": True, "seconds_left": 580}
    import nicsoft.modes.lichess.client as client_mod
    monkeypatch.setattr(client_mod, "get_ongoing_games",
                         lambda token: {"status": "ok", "game": game, "total_candidates": 1})
    lichess_launcher.check_lichess_resumable()
    assert events == [("lichess_resumable", {"available": True, "game": game})]


# ═══════════════════════════════════════════════════════════════════════
# 3. LichessGame(resuming=True) — écran de mise en place (issue #323, point 3)
# ═══════════════════════════════════════════════════════════════════════

def _make_resuming_game(monkeypatch, moves="e2e4", user_color_is_black=True, board=None):
    events, _, _ = _make_recorder(monkeypatch)
    board = board or FakeBoard()
    transport = FakeTransport()
    client = GameClient("lip_test", transport=transport)
    game = LichessGame(
        board, client, "gid1", level=2, player_name="Alain",
        clock_limit_s=300, clock_increment_s=0, chosen_color_setting="black",
        resuming=True,
    )
    white = {"id": "alain"} if not user_color_is_black else {"aiLevel": 2}
    black = {"aiLevel": 2} if not user_color_is_black else {"id": "alain"}
    game._apply_game_full({
        "white": white, "black": black,
        "state": {"status": "started", "moves": moves},
    })
    return game, board, events


def test_resume_pending_desactive_les_boutons_meme_au_bon_tour(monkeypatch):
    game, board, events = _make_resuming_game(monkeypatch)
    assert game._resume_pending is True
    resign_enabled, draw_enabled = game._compute_action_buttons()
    assert (resign_enabled, draw_enabled) == (False, False)


def test_tick_resume_setup_signale_les_cases_en_erreur_et_allume_les_led(monkeypatch):
    game, board, events = _make_resuming_game(monkeypatch)
    target = game.board.board_fen()
    # Position physique vide (échiquier rangé) — tout diffère de la cible.
    board.current_fen = "8/8/8/8/8/8/8/8 w - - 0 1"
    game._tick_physical()
    setup_events = _events_of(events, "lichess_resume_setup")
    assert setup_events and setup_events[-1]["active"] is True
    assert setup_events[-1]["expected_fen"] == target
    assert setup_events[-1]["physical_fen"] == "8/8/8/8/8/8/8/8"
    assert game._resume_pending is True
    # Toutes les cases occupées dans la cible doivent être signalées en LED.
    lit_squares = {sq for sq, status in board.led_calls if status}
    expected_board = chess.Board(target + " w - - 0 1")
    expected_squares = {chess.square_name(sq) for sq in chess.SQUARES if expected_board.piece_at(sq)}
    assert expected_squares <= lit_squares


def test_tick_resume_setup_position_deja_correcte_reprend_immediatement(monkeypatch):
    game, board, events = _make_resuming_game(monkeypatch)
    board.current_fen = game.board.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert game._resume_pending is False
    assert not any(e["active"] for e in _events_of(events, "lichess_resume_setup"))
    # Noir au trait ici (1 coup joué par les blancs), utilisateur noir :
    # c'est à lui de jouer, position confirmée → boutons actifs.
    assert game._compute_action_buttons() == (True, True)


def test_tick_resume_setup_match_puis_coup_utilisateur_detecte(monkeypatch):
    """Une fois la position reconstruite, le jeu normal reprend : le coup
    suivant de l'utilisateur est détecté comme en partie ordinaire."""
    sent = []
    game, board, events = _make_resuming_game(monkeypatch, user_color_is_black=True)
    monkeypatch.setattr(game.client, "play_move", lambda gid, uci, offer_draw=False: sent.append(uci))
    target = game.board.board_fen()
    board.current_fen = "8/8/8/8/8/8/8/8 w - - 0 1"
    game._tick_physical()
    assert game._resume_pending is True

    board.current_fen = target + " w - - 0 1"
    game._tick_physical()
    assert game._resume_pending is False
    assert _events_of(events, "lichess_resume_setup")[-1] == {"active": False}

    # Coup noir (réponse) détecté au tick suivant.
    after = chess.Board()
    after.push_uci("e2e4")
    after.push_uci("e7e5")
    board.current_fen = after.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert sent == ["e7e5"]


def test_adversaire_joue_pendant_la_mise_en_place_met_a_jour_la_cible(monkeypatch):
    """Cas (d) : l'adversaire joue alors que l'utilisateur est en train de
    reconstruire la position — la cible (self.board.board_fen(), relue à
    chaque tick) se met à jour pour inclure ce nouveau coup, sans perdre de
    vue les cases déjà demandées."""
    # Utilisateur blanc, 1.e4 déjà joué avant la reprise : c'est au tour de
    # l'adversaire (noir) de répondre.
    game, board, events = _make_resuming_game(monkeypatch, moves="e2e4", user_color_is_black=False)
    first_target = game.board.board_fen()

    # Échiquier rangé (vide) au moment de la reprise — rien n'est encore posé.
    board.current_fen = "8/8/8/8/8/8/8/8 w - - 0 1"
    game._tick_physical()
    assert game._resume_pending is True
    first_squares = set(game._resume_led_squares)
    assert "e4" in first_squares  # la cible attend un pion blanc en e4

    # L'adversaire (noir) répond pendant que l'utilisateur reconstruit —
    # appliqué via le flux, pas via le plateau physique.
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})
    new_target = game.board.board_fen()
    assert new_target != first_target

    # Sans que l'utilisateur n'ait touché le plateau (toujours vide), la
    # cible a changé : la case e5 nouvellement occupée doit être signalée
    # EN PLUS de e4, qui reste demandée — rien n'est perdu. (Throttle
    # d'envoi contourné ici — voir POSITION_ERROR_THROTTLE_S — pour ne pas
    # dépendre d'un vrai délai dans ce test.)
    game._last_position_error_ts = 0.0
    game._tick_physical()
    assert game._resume_pending is True
    squares = set(game._resume_led_squares)
    assert "e4" in squares and "e5" in squares


def test_echiquier_perdu_pendant_la_mise_en_place_ne_declenche_pas_abandon(monkeypatch):
    game, board, events = _make_resuming_game(monkeypatch)

    # Même convention que _read_hardware_fen() en échec réel (driver.py) :
    # retourne None, ne lève jamais (voir game.py::_read_hardware_fen).
    monkeypatch.setattr(game, "_read_hardware_fen", lambda: None)
    monkeypatch.setattr(game, "_maybe_attempt_reconnect", lambda: None)

    for _ in range(game.BOARD_LOST_STRIKES + 1):
        game._tick_physical()
    assert game._board_lost is True
    assert game.game_over is False
    assert _events_of(events, "lichess_board_lost")


def test_cas_e_moins_de_deux_coups_abandon_devient_annulation(monkeypatch):
    """Cas (e) : partie reprise avec moins de deux coups — le comportement
    (annulation plutôt qu'abandon) reste celui déjà en place, inchangé par
    la reprise."""
    aborted = []
    game, board, events = _make_resuming_game(monkeypatch, moves="")
    monkeypatch.setattr(game.client, "abort", lambda gid: aborted.append(gid))
    monkeypatch.setattr(game.client, "resign", lambda gid: pytest.fail("resign() appelé au lieu de abort()"))
    ok = game._request_resign_or_abort(reason="test")
    assert ok is True
    assert aborted == ["gid1"]
    assert game._aborted is True


def test_partie_deja_terminee_au_moment_de_la_reprise(monkeypatch, tmp_path):
    """Cas (c) : la partie s'est terminée entre-temps — detecté dès le
    premier gameFull, jamais de phase de mise en place (resuming=True mais
    _tick_physical n'est jamais sollicité : game_over devient vrai avant
    tout accès au plateau)."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    transport = FakeTransport()
    client = GameClient("lip_test", transport=transport)
    game = LichessGame(
        board, client, "gid1", level=1, player_name="Alain",
        clock_limit_s=300, clock_increment_s=0, chosen_color_setting="white",
        resuming=True,
    )
    monkeypatch.setattr(game_mod, "build_final_path", lambda *a, **k: tmp_path / "partie.pgn")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "mate", "moves": "e2e4 e7e5 f1c4 b8c6 d1h5 g8f6 h5f7", "winner": "white"},
    })
    assert game.game_over is True
    assert game._resume_pending is True  # jamais consulté : aucun tick physique n'a lieu
    assert board.led_calls == []
    game._finalize()
    assert (tmp_path / "partie.pgn").exists()
    game_over_events = _events_of(events, "game_over")
    assert game_over_events and game_over_events[-1]["result"] == "1-0"


# ═══════════════════════════════════════════════════════════════════════
# 4. Scénario complet (threading réel, comme test_issue309) — reprise noire,
#    mise en place puis jeu normal jusqu'à un coup, sans aucun moteur.
# ═══════════════════════════════════════════════════════════════════════

def test_scenario_complet_reprise_mise_en_place_puis_coup_utilisateur(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("un moteur a été lancé pendant une partie Lichess reprise !")
    import nicsoft.engine.engine_manager as engine_manager
    for name in ("find_stockfish", "find_lc0", "load_maia_weights"):
        if hasattr(engine_manager, name):
            monkeypatch.setattr(engine_manager, name, _boom, raising=False)

    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()

    stream_queue = queue.Queue()

    class _QueueTransport:
        def stream_lines(self, url, token):
            while True:
                line = stream_queue.get()
                if line is None:
                    return
                yield line

        def request(self, *a, **kw):
            raise AssertionError("aucune requête ordinaire attendue via ce transport")

    client = GameClient("lip_x", transport=_QueueTransport())
    sent_moves = []

    def fake_play_move(gid, uci, offer_draw=False):
        sent_moves.append(uci)
        stream_queue.put(_line({"type": "gameState", "moves": "e2e4 " + uci, "status": "started"}))
    monkeypatch.setattr(client, "play_move", fake_play_move)

    game = LichessGame(board, client, "gid1", level=1, player_name="Alain",
                        clock_limit_s=300, clock_increment_s=0, resuming=True)

    # Reprise : l'IA (blancs) a déjà joué 1.e4 avant la reprise — l'utilisateur
    # (noir) doit reconstruire cette position sur l'échiquier physique.
    stream_queue.put(_line({
        "type": "gameFull", "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    }))

    board.current_fen = chess.STARTING_BOARD_FEN + " w - - 0 1"  # position physique périmée

    game_thread = threading.Thread(target=game.start, daemon=True)
    game_thread.start()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not game._resume_pending and game.user_color is None:
        time.sleep(0.01)
    while time.monotonic() < deadline and not any(
        e[0] == "lichess_resume_setup" and e[1].get("active") for e in events
    ):
        time.sleep(0.01)
    assert game._resume_pending is True
    assert not sent_moves  # aucun coup envoyé avant que la position ne soit correcte

    after_e4 = chess.Board()
    after_e4.push_uci("e2e4")
    board.current_fen = after_e4.board_fen() + " w - - 0 1"

    while time.monotonic() < deadline and game._resume_pending:
        time.sleep(0.01)
    assert game._resume_pending is False

    after_e5 = after_e4.copy()
    after_e5.push_uci("e7e5")
    board.current_fen = after_e5.board_fen() + " w - - 0 1"

    while time.monotonic() < deadline and not sent_moves:
        time.sleep(0.01)
    assert sent_moves == ["e7e5"]

    stream_queue.put(None)  # ferme le flux pour que run() se termine
    game_thread.join(timeout=3.0)
    assert not game_thread.is_alive()


# ═══════════════════════════════════════════════════════════════════════
# 5. launch_lichess_resume() / _run_lichess_resume() — lanceur
# ═══════════════════════════════════════════════════════════════════════

class _FakeWebServerResume:
    _app_state = "config_lichess"


def test_launch_lichess_resume_mode_deja_actif(monkeypatch):
    toasts = []
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "playing", raising=False)
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: toasts.append((t, d)))
    lichess_launcher.launch_lichess_resume({"game_id": "gid1"})
    assert toasts and toasts[-1][0] == "lichess_toast"
    assert toasts[-1][1]["message_key"] == "toast.lichess_mode_actif"


def test_launch_lichess_resume_sans_game_id_ne_fait_rien(monkeypatch):
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "config_lichess", raising=False)
    calls = []
    monkeypatch.setattr(lichess_launcher, "_run_lichess_resume", lambda *a, **k: calls.append(a))
    lichess_launcher.launch_lichess_resume({"game_id": ""})
    assert calls == []


def test_launch_lichess_resume_sans_jeton_renvoie_au_menu(monkeypatch):
    toasts = []
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "config_lichess", raising=False)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": ""})

    def fake_set_app_state(state, data=None):
        toasts.append((state, data))
    monkeypatch.setattr(lichess_launcher, "set_app_state", fake_set_app_state)
    lichess_launcher.launch_lichess_resume({"game_id": "gid1"})
    assert toasts and toasts[-1][0] == "menu"
    assert toasts[-1][1]["toast_message_key"] == "toast.lichess_no_token"


def test_run_lichess_resume_erreur_reseau_si_gamefull_absent(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda client, gid: None)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess_resume("lip_x", "gid1", "Alain", _error)
    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_network_error"


def test_run_lichess_resume_echiquier_non_detecte(monkeypatch):
    full_event = {
        "white": {"id": "alain"}, "black": {"aiLevel": 1}, "clock": {"initial": 900000, "increment": 0},
        "state": {"status": "started", "moves": ""},
    }
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda client, gid: full_event)

    def boom(name):
        raise SystemExit("board connection error.")
    monkeypatch.setattr(lichess_launcher, "_open_board_with_retry", boom)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    lichess_launcher._run_lichess_resume("lip_x", "gid1", "Alain", _error)
    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.board_not_found"


def test_run_lichess_resume_jeton_refuse(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "_peek_game_full",
                         lambda client, gid: (_ for _ in ()).throw(LichessAuthError(401)))
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess_resume("lip_x", "gid1", "Alain", _error)
    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_invalid_token"


def test_game_manager_expose_launch_lichess_resume():
    assert gm.launch_lichess_resume is lichess_launcher.launch_lichess_resume
    assert gm.check_lichess_resumable is lichess_launcher.check_lichess_resumable


# ═══════════════════════════════════════════════════════════════════════
# 6. i18n : nouvelles clés présentes dans les trois langues
# ═══════════════════════════════════════════════════════════════════════

NEW_I18N_KEYS = [
    "lichess.reprise_titre", "lichess.reprise_bouton", "lichess.reprise_mise_en_place",
    "lichess.reprise_mon_tour", "lichess.reprise_tour_adverse", "lichess.reprise_minutes_restantes",
    "lichess.vitesse.ultraBullet", "lichess.vitesse.bullet", "lichess.vitesse.blitz",
    "lichess.vitesse.rapid", "lichess.vitesse.classical", "lichess.vitesse.correspondence",
    "lichess.vitesse.inconnue",
]


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_nouvelles_cles_i18n_reprise_presentes(locale):
    path = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in NEW_I18N_KEYS:
        assert key in data, f"{key} absente de {locale}.json"
        assert data[key], f"{key} vide dans {locale}.json"


# ═══════════════════════════════════════════════════════════════════════
# 7. app.js : câblage et échappement (jamais le nom d'adversaire en innerHTML)
# ═══════════════════════════════════════════════════════════════════════

def _read_appjs():
    return (REPO_ROOT / "nicsoft" / "web" / "static" / "app.js").read_text(encoding="utf-8")


def test_appjs_wiring_reprise_present():
    src = _read_appjs()
    for needle in [
        'socket.on("lichess_resumable"', 'socket.on("lichess_resume_setup"',
        '"start_lichess_resume"', "function lichessResumeGame",
        'case "lichess_resume_game"',
    ]:
        assert needle in src, f"{needle!r} absent de app.js"


def test_appjs_nom_adversaire_jamais_en_innerhtml():
    src = _read_appjs()
    start = src.index('socket.on("lichess_resumable"')
    end = src.index("\n});", start)
    bloc = src[start:end]
    code_lines = [line for line in bloc.splitlines() if not line.strip().startswith("//")]
    assert not any(".innerHTML" in line for line in code_lines)
    assert "textContent" in bloc


def test_appjs_lichess_resume_setup_reutilise_renderboardwitherrors():
    src = _read_appjs()
    start = src.index('socket.on("lichess_resume_setup"')
    end = src.index("\n});", start)
    bloc = src[start:end]
    assert "renderBoardWithErrors" in bloc
    assert "innerHTML" not in bloc


def test_index_html_banniere_reprise_presente():
    html = (REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="lichess-resume-banner"' in html
    assert 'id="lichess-resume-setup"' in html
    assert 'data-action="lichess_resume_game"' in html
