"""
nicsoft/tests/test_issue309_lichess_l2a.py — AlChess

Issue #309 (étape L2a) : partie amicale contre l'IA de Lichess jouée sur
l'échiquier physique — aides coupées, pendules, abandon/nulle/annulation.

Entièrement sans réseau (faux transport du client, voir test_issue307) et
sans matériel (faux plateau — double léger imitant l'interface utilisée
par LichessGame : current_fen, set_led, turn_off_all_leds).
"""
import json
import queue
import threading
import time

import chess
import pytest

import nicsoft.core.game_manager as gm
import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.game as game_mod
from nicsoft.modes.lichess.errors import LichessApiError, LichessAuthError, LichessNetworkError, LichessRateLimitError
from nicsoft.modes.lichess.game import (
    LichessGame,
    build_pgn_headers,
    compute_clock_ms,
    legal_move_for_hardware,
    opponent_pgn_name,
    pending_promotion_move,
    pgn_result,
    pgn_time_control,
)
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.transport import TransportHTTPError


# ── Doubles de test ──────────────────────────────────────────────────────────

class FakeTransport:
    """Même contrat que le faux transport de test_issue307 — aucune
    connexion réseau réelle. requests: callables consommées dans l'ordre ;
    stream_batches: listes de lignes consommées dans l'ordre par appel."""

    def __init__(self, requests=None, stream_batches=None):
        self._requests = list(requests or [])
        self._stream_batches = list(stream_batches or [])

    def request(self, method, url, token, fields=None):
        handler = self._requests.pop(0)
        result = handler(method, url, token, fields)
        if isinstance(result, Exception):
            raise result
        return result

    def stream_lines(self, url, token):
        batch = self._stream_batches.pop(0)
        for item in batch:
            if isinstance(item, Exception):
                raise item
            yield item


def _ok(body):
    return lambda method, url, token, fields: json.dumps(body).encode("utf-8")


def _line(d):
    return json.dumps(d)


class FakeBoard:
    """Double léger du plateau physique — current_fen est un attribut brut
    (comme driver.py), mis à jour directement par le test."""

    def __init__(self, initial_fen=chess.STARTING_BOARD_FEN):
        self.current_fen = initial_fen + " w - - 0 1"
        self.led_calls = []
        self.leds_off_count = 0

    def set_led(self, square, status):
        self.led_calls.append((square, status))

    def turn_off_all_leds(self):
        self.leds_off_count += 1

    def signal_lights(self, sig):
        pass

    def beep(self):
        pass

    def disconnect(self):
        pass


def _make_recorder(monkeypatch):
    """Monkeypatch send_event/set_app_state/get_action dans le module
    nicsoft.modes.lichess.game — retourne (events, states, action_queue)."""
    events = []
    states = []
    actions = queue.Queue()

    def fake_send_event(event_type, data):
        events.append((event_type, data))

    def fake_set_app_state(state, data=None):
        states.append((state, data))

    def fake_get_action(timeout=0.0):
        try:
            return actions.get(timeout=timeout)
        except queue.Empty:
            return None

    monkeypatch.setattr(game_mod, "send_event", fake_send_event)
    monkeypatch.setattr(game_mod, "set_app_state", fake_set_app_state)
    monkeypatch.setattr(game_mod, "get_action", fake_get_action)
    return events, states, actions


def _events_of(events, etype):
    return [d for t, d in events if t == etype]


def _make_game(nl_inst=None, **kwargs):
    nl_inst = nl_inst or FakeBoard()
    transport = kwargs.pop("transport", FakeTransport())
    client = GameClient("lip_test_token", transport=transport)
    game = LichessGame(
        nl_inst, client, kwargs.pop("game_id", "gid1"),
        level=kwargs.pop("level", 1), player_name=kwargs.pop("player_name", "Alain"),
        clock_limit_s=kwargs.pop("clock_limit_s", 900), clock_increment_s=kwargs.pop("clock_increment_s", 10),
    )
    return game, client, transport


# ── Fonctions pures ──────────────────────────────────────────────────────────

def test_legal_move_for_hardware_detecte_coup_simple():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    test_board = board.copy()
    test_board.push(move)
    found = legal_move_for_hardware(board, test_board.board_fen())
    assert found == move


def test_legal_move_for_hardware_gere_roque():
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    move = chess.Move.from_uci("e1g1")  # petit roque blanc
    test_board = board.copy()
    test_board.push(move)
    found = legal_move_for_hardware(board, test_board.board_fen())
    assert found == move


def test_legal_move_for_hardware_gere_prise_en_passant():
    board = chess.Board("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3")
    move = chess.Move.from_uci("e5d6")
    test_board = board.copy()
    test_board.push(move)
    found = legal_move_for_hardware(board, test_board.board_fen())
    assert found == move


def test_legal_move_for_hardware_ignore_les_promotions():
    board = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")
    # Aucune pièce (hors promotion) placée sur a8 → aucun coup non-promotion ne correspond.
    hw_fen = "Q7/8/8/8/8/8/8/k6K"
    assert legal_move_for_hardware(board, hw_fen) is None


def test_pending_promotion_move_detecte_n_importe_quelle_piece_du_bon_camp():
    board = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")
    hw_fen = "N7/8/8/8/8/8/8/k6K"  # n'importe quelle pièce blanche posée en a8
    result = pending_promotion_move(board, hw_fen)
    assert result == (chess.A7, chess.A8)


def test_pending_promotion_move_refuse_piece_du_mauvais_camp():
    board = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")
    hw_fen = "n7/8/8/8/8/8/8/k6K"  # pièce noire posée — camp incorrect
    assert pending_promotion_move(board, hw_fen) is None


def test_pending_promotion_move_none_si_position_normale():
    board = chess.Board()
    assert pending_promotion_move(board, board.board_fen()) is None


@pytest.mark.parametrize("turn,white_ms,black_ms,elapsed,expected", [
    ("white", 10000.0, 20000.0, 3.0, (7000.0, 20000.0)),
    ("black", 10000.0, 20000.0, 5.0, (10000.0, 15000.0)),
    ("white", 1000.0, 20000.0, 5.0, (0.0, 20000.0)),  # ne descend jamais sous zéro
])
def test_compute_clock_ms(turn, white_ms, black_ms, elapsed, expected):
    assert compute_clock_ms(white_ms, black_ms, turn, elapsed) == expected


def test_pgn_result_victoire_defaite_nulle_annulation():
    assert pgn_result("mate", "white") == "1-0"
    assert pgn_result("mate", "black") == "0-1"
    assert pgn_result("resign", "black") == "0-1"
    assert pgn_result("outoftime", "white") == "1-0"
    assert pgn_result("draw", "") == "1/2-1/2"
    assert pgn_result("stalemate", "") == "1/2-1/2"
    assert pgn_result("aborted", "") == "*"


def test_pgn_time_control():
    assert pgn_time_control(900, 10) == "900+10"


def test_opponent_pgn_name_jamais_vide():
    assert opponent_pgn_name(3) == "Lichess AI level 3"


def test_build_pgn_headers_utilisateur_blanc():
    headers = build_pgn_headers("abcd1234", "Alain", "white", 1, 900, 10, "1-0", "2026.11.09")
    assert headers["White"] == "Alain"
    assert headers["Black"] == "Lichess AI level 1"
    assert headers["Site"] == "https://lichess.org/abcd1234"
    assert headers["Result"] == "1-0"
    assert headers["TimeControl"] == "900+10"
    assert "Alain" not in headers["Black"]
    assert "None" not in headers["White"] and "None" not in headers["Black"]


def test_build_pgn_headers_nom_utilisateur_vide_jamais_none():
    headers = build_pgn_headers("gid", "", "black", 2, 600, 0, "0-1", "2026.11.09")
    assert headers["Black"] == "Vous"
    assert "None" not in headers["Black"]


# ── LichessGame — scénarios boîte blanche (sans threading) ──────────────────

def test_apply_game_full_identifie_couleur_et_niveau_ia(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    game, _, _ = _make_game()
    game._apply_game_full({
        "white": {"aiLevel": 3},
        "black": {"id": "alain", "name": "alain"},
        "state": {"status": "started", "moves": ""},
    })
    assert game.user_color == "black"
    assert game.level == 3
    init_events = _events_of(events, "lichess_init")
    assert init_events and init_events[0]["color"] == "black" and init_events[0]["level"] == 3


def test_opponent_move_affiche_et_allume_leds_puis_attend_replication(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"aiLevel": 1},
        "black": {"id": "alain"},
        "state": {"status": "started", "moves": ""},
    })
    # L'IA (blancs) joue e2e4 — coup envoyé par Lichess.
    game._apply_game_state({"status": "started", "moves": "e2e4"})
    moves = _events_of(events, "lichess_move")
    assert moves and moves[-1]["opponent_move"] is True and moves[-1]["uci"] == "e2e4"
    assert game._awaiting_physical_replication is True
    assert ("e2", True) in board.led_calls and ("e4", True) in board.led_calls

    # Tant que le physique ne correspond pas, pas de coup utilisateur détecté.
    board.current_fen = chess.STARTING_BOARD_FEN + " w - - 0 1"
    game._tick_physical()
    assert game._awaiting_physical_replication is True

    # L'utilisateur reproduit le coup sur l'échiquier.
    replicated = chess.Board()
    replicated.push_uci("e2e4")
    board.current_fen = replicated.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert game._awaiting_physical_replication is False
    assert board.leds_off_count >= 1


def test_coup_utilisateur_detecte_et_envoye_sans_maj_optimiste(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    sent = []
    board = FakeBoard()
    transport = FakeTransport(requests=[_ok({"ok": True})])
    game, client, _ = _make_game(nl_inst=board, transport=transport)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append(uci))
    game._apply_game_full({
        "white": {"id": "alain"},
        "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    assert game.user_color == "white"
    # L'utilisateur joue physiquement e2e4.
    after = chess.Board()
    after.push_uci("e2e4")
    board.current_fen = after.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert sent == ["e2e4"]
    # Pas de mise à jour optimiste : le plateau logique reste en position initiale
    # jusqu'à la confirmation Lichess (gameState).
    assert game.board.board_fen() == chess.STARTING_BOARD_FEN
    game._apply_game_state({"status": "started", "moves": "e2e4"})
    assert game.board.board_fen() == after.board_fen()


def test_promotion_demande_a_l_ecran_puis_soumise(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    sent = []
    board = FakeBoard("8/P7/8/8/8/8/8/k6K")
    transport = FakeTransport(requests=[_ok({"ok": True})])
    game, client, _ = _make_game(nl_inst=board, transport=transport)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append(uci))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    # Le plateau logique vient de Lichess (toujours la position de départ ici,
    # aucun coup joué) — on le force directement à une position de promotion
    # pour tester uniquement la détection physique.
    game.board = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")
    board.current_fen = "N7/8/8/8/8/8/8/k6K w - - 0 1"  # n'importe quelle pièce en a8
    game._tick_physical()
    promo_events = _events_of(events, "lichess_promotion_needed")
    assert promo_events == [{"from": "a7", "to": "a8"}]
    assert game._pending_promotion == (chess.A7, chess.A8)
    game._submit_promotion("q")
    assert sent == ["a7a8q"]
    assert game._pending_promotion is None


def test_lichess_refuse_le_coup_demande_de_remettre_la_piece(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, json.dumps({"error": "This move is illegal"})),
    ])
    game, client, _ = _make_game(nl_inst=board, transport=transport)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    before_fen = game.board.board_fen()
    after = chess.Board()
    after.push_uci("e2e4")
    board.current_fen = after.board_fen() + " w - - 0 1"
    game._tick_physical()
    refused = _events_of(events, "lichess_move_refused")
    assert refused and "illegal" in refused[0]["message"]
    assert game._awaiting_piece_reset is True
    # Le navigateur demande de remettre la pièce à sa place avant de reprendre.
    board.current_fen = before_fen + " w - - 0 1"
    game._tick_physical()
    assert game._awaiting_piece_reset is False


def test_proposition_nulle_des_deux_cotes(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    game, _, _ = _make_game()
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    # L'IA (noirs) propose la nulle.
    game._apply_game_state({"status": "started", "moves": "", "bdraw": True})
    offers = _events_of(events, "lichess_draw_offered")
    assert offers[-1]["offered"] is True
    # L'offre est retirée.
    game._apply_game_state({"status": "started", "moves": "", "bdraw": False})
    assert offers_last_cleared(events)


def offers_last_cleared(events):
    offers = _events_of(events, "lichess_draw_offered")
    return offers[-1]["offered"] is False


def test_abandon_moins_de_deux_coups_devient_annulation(monkeypatch):
    events, _, actions = _make_recorder(monkeypatch)
    aborted = []
    game, client, _ = _make_game()
    monkeypatch.setattr(client, "abort", lambda gid: aborted.append(gid))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    actions.put({"type": "lichess_resign"})
    game._process_browser_actions()
    assert aborted == ["gid1"]
    assert game.game_over is True
    assert game._aborted is True


def test_abandon_apres_deux_coups_devient_resign(monkeypatch):
    events, _, actions = _make_recorder(monkeypatch)
    resigned = []
    game, client, _ = _make_game()
    monkeypatch.setattr(client, "resign", lambda gid: resigned.append(gid))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4 e7e5"},
    })
    actions.put({"type": "lichess_resign"})
    game._process_browser_actions()
    assert resigned == ["gid1"]
    assert game.game_over is True
    assert game._aborted is False
    assert game._winner == "black"  # l'utilisateur (blancs) abandonne


def test_board_lost_n_abandonne_pas_automatiquement(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })

    class _BrokenBoard:
        @property
        def current_fen(self):
            raise OSError("plateau déconnecté")

    game.nl_inst = _BrokenBoard()
    for _ in range(game.BOARD_LOST_STRIKES + 1):
        game._tick_physical()
    assert game._board_lost is True
    assert game.game_over is False  # la partie reste ouverte — pas d'abandon automatique
    assert _events_of(events, "lichess_board_lost")


def test_reconnexion_recalibre_sur_nouveau_gamefull(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    game, _, _ = _make_game()
    game._handle_stream_event({"type": "reconnecting", "attempt": 1})
    assert _events_of(events, "lichess_reconnecting") == [{"attempt": 1}]
    game._handle_stream_event({"type": "reconnected"})
    assert _events_of(events, "lichess_reconnected") == [{}]
    game._handle_stream_event({
        "type": "gameFull",
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game.board.board_fen() != chess.STARTING_BOARD_FEN
    assert game._moves_applied == 1


def test_menu_verrouille_pendant_la_partie(monkeypatch):
    events, _, actions = _make_recorder(monkeypatch)
    game, _, _ = _make_game()
    actions.put({"type": "mode", "value": "humain"})
    game._process_browser_actions()
    toasts = _events_of(events, "lichess_toast")
    assert toasts and toasts[0]["message_key"] == "lichess.menu_verrouille"
    assert game.game_over is False  # le mode n'a pas changé


def test_pgn_sauvegarde_avec_bons_entetes_et_pas_sur_annulation(monkeypatch, tmp_path):
    events, states, _ = _make_recorder(monkeypatch)
    saved = []
    game, _, _ = _make_game(player_name="Alain", level=4, clock_limit_s=600, clock_increment_s=0)
    monkeypatch.setattr(game_mod, "build_final_path", lambda mode, gtype, white, black: str(tmp_path / "out.pgn"))

    def fake_save(headers=None, moves=None, output_path=None):
        saved.append((dict(headers), output_path))
    monkeypatch.setattr(game_mod, "build_and_save_pgn", fake_save)

    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 4},
        "state": {"status": "started", "moves": "e2e4"},
    })
    game._status = "resign"
    game._winner = "black"
    game._aborted = False
    game._finalize()
    assert len(saved) == 1
    headers, _ = saved[0]
    assert headers["White"] == "Alain"
    assert headers["Black"] == "Lichess AI level 4"
    assert headers["Result"] == "0-1"
    assert headers["TimeControl"] == "600+0"
    assert states and states[-1][0] == "game_over"


def test_pas_de_pgn_si_partie_annulee(monkeypatch, tmp_path):
    events, states, _ = _make_recorder(monkeypatch)
    saved = []
    monkeypatch.setattr(game_mod, "build_and_save_pgn", lambda **kw: saved.append(kw))
    game, _, _ = _make_game()
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    game._status = "aborted"
    game._aborted = True
    game._finalize()
    assert saved == []


# ── Partie complète bout-en-bout (threadée, courte) ─────────────────────────

def test_partie_complete_jusqu_au_mat_sans_aucun_moteur(monkeypatch):
    """Mat du berger : vérifie le câblage complet run()/thread de flux/
    plateau physique, et qu'aucun module moteur n'est jamais importé ni
    appelé (fair-play Lichess). Le flux est piloté par une file que le
    test alimente au rythme des vrais appels play_move() du jeu — jamais
    de scénario pré-écrit indépendant de ce que le code sous test fait
    réellement, pour ne pas masquer un défaut de synchronisation."""
    def _boom(*a, **k):
        raise AssertionError("un moteur a été lancé pendant une partie Lichess !")

    import nicsoft.engine.engine_manager as engine_manager
    for name in ("find_stockfish", "find_lc0", "load_maia_weights"):
        if hasattr(engine_manager, name):
            monkeypatch.setattr(engine_manager, name, _boom, raising=False)

    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()

    # Scholar's mate : 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6?? 4.Qxf7# — utilisateur
    # blancs (4 coups), IA noirs (3 coups, aiLevel=1).
    user_moves = ["e2e4", "f1c4", "d1h5", "h5f7"]
    ai_moves = ["e7e5", "b8c6", "g8f6"]

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
    all_moves = []
    ai_iter = iter(ai_moves)

    def fake_play_move(gid, uci, offer_draw=False):
        sent_moves.append(uci)
        all_moves.append(uci)
        is_last = uci == user_moves[-1]
        status = "mate" if is_last else "started"
        winner = "white" if is_last else None
        stream_queue.put(_line({"type": "gameState", "moves": " ".join(all_moves),
                                 "status": status, "winner": winner}))
        if not is_last:
            ai_uci = next(ai_iter)
            all_moves.append(ai_uci)
            stream_queue.put(_line({"type": "gameState", "moves": " ".join(all_moves), "status": "started"}))

    monkeypatch.setattr(client, "play_move", fake_play_move)

    game = LichessGame(board, client, "gid1", level=1, player_name="Alain",
                        clock_limit_s=300, clock_increment_s=0)

    stream_queue.put(_line({
        "type": "gameFull", "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    }))

    def _drive_physical_board():
        """Simule la main de l'utilisateur : joue chaque coup blanc dès que
        la position logique du jeu l'attend, puis reproduit physiquement la
        réponse de l'IA avant le coup blanc suivant (position physique
        exigée avant de laisser passer son propre tour — issue #309, point 3)."""
        board_sim = chess.Board()
        deadline = time.monotonic() + 5.0
        for i, user_uci in enumerate(user_moves):
            while time.monotonic() < deadline and game.board.board_fen() != board_sim.board_fen():
                time.sleep(0.01)
            board_sim.push_uci(user_uci)
            board.current_fen = board_sim.board_fen() + " w - - 0 1"
            if i < len(ai_moves):
                target_after_ai = board_sim.copy()
                target_after_ai.push_uci(ai_moves[i])
                while time.monotonic() < deadline and game.board.board_fen() != target_after_ai.board_fen():
                    time.sleep(0.01)
                board_sim.push_uci(ai_moves[i])
                board.current_fen = board_sim.board_fen() + " w - - 0 1"
                # Attendre que _tick_physical() ait bien observé la réplication
                # avant de rejouer le coup suivant — sinon la prochaine écriture
                # de board.current_fen pourrait écraser la position avant que
                # le jeu n'ait eu la main pour la lire (course bénigne, propre
                # au double de test : le vrai plateau physique, lui, reste
                # stable tout seul entre deux lectures).
                while time.monotonic() < deadline and game._awaiting_physical_replication:
                    time.sleep(0.01)

    driver = threading.Thread(target=_drive_physical_board, daemon=True)
    driver.start()
    game_thread = threading.Thread(target=game.start, daemon=True)
    game_thread.start()
    game_thread.join(timeout=8.0)
    driver.join(timeout=1.0)

    assert not game_thread.is_alive(), "la partie ne s'est pas terminée à temps"
    assert game.game_over is True
    assert game._status == "mate"
    assert sent_moves == user_moves
    game_over_events = _events_of(events, "game_over")
    assert game_over_events and game_over_events[-1]["result"] == "1-0"
    assert game_over_events[-1]["title_key"] == "game.titre_victoire"


# ── Lanceur : traduction des erreurs Lichess en messages clairs ────────────

class _FakeWebServerLichess:
    _app_state = "connecting"


def test_launch_lichess_sans_jeton_renvoie_au_menu_avec_toast(monkeypatch):
    toasts = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": ""})
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "menu", raising=False)

    def fake_set_app_state(state, data=None):
        toasts.append((state, data))
    monkeypatch.setattr(lichess_launcher, "set_app_state", fake_set_app_state)

    lichess_launcher.launch_lichess({"level": 1, "cadence": "15+10", "color": "random"})
    assert toasts and toasts[-1][0] == "menu"
    assert toasts[-1][1]["toast_message_key"] == "toast.lichess_no_token"


@pytest.mark.parametrize("exc,expected_key", [
    (LichessAuthError(401), "toast.lichess_invalid_token"),
    (LichessAuthError(403), "toast.lichess_missing_scope"),
    (LichessRateLimitError(), "toast.lichess_rate_limited"),
    (LichessNetworkError("x"), "toast.lichess_network_error"),
])
def test_run_lichess_traduit_les_erreurs_client_en_toast(monkeypatch, exc, expected_key):
    class _FakeClient:
        def __init__(self, token, transport=None):
            pass

        def create_ai_game(self, **kwargs):
            raise exc

    monkeypatch.setattr(lichess_launcher, "GameClient", _FakeClient)
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: FakeBoard())
    monkeypatch.setattr(lichess_launcher, "_wait_initial_position_lichess", lambda nl_inst: None)
    monkeypatch.setattr(lichess_launcher, "set_nl_inst_ref", lambda nl_inst: None)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)

    # Couleur explicite "black" : crée la partie immédiatement après la
    # position (comme avant #311) — l'erreur testée ici vient de
    # create_ai_game(), pas de la branche blancs (attente du premier coup
    # physique), qui a son propre test dédié.
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)
    assert _error["occurred"] is True
    assert _error["toast_key"] == expected_key


def test_game_manager_expose_launch_lichess():
    assert gm.launch_lichess is lichess_launcher.launch_lichess


# ── i18n : nouvelles clés présentes dans les trois langues ──────────────────

NEW_I18N_KEYS = [
    "menu.btn.lichess", "menu.desc.lichess", "menu.lichess.requiert_jeton",
    "config.titre.lichess", "config.h2.niveau_ia", "config.h2.cadence", "config.h2.couleur",
    "config.lichess.disclaimer", "banner.board_absent_lichess",
    "lichess.vous", "lichess.ia_niveau", "lichess.reconnexion", "lichess.echiquier_perdu",
    "lichess.reproduisez_coup", "lichess.nulle_proposee", "lichess.accepter", "lichess.refuser",
    "lichess.choisir_promotion", "lichess.promotion.dame", "lichess.promotion.tour",
    "lichess.promotion.fou", "lichess.promotion.cavalier", "lichess.proposer_nulle_titre",
    "lichess.menu_verrouille", "lichess.erreur_reseau", "lichess.coup_refuse",
    "lichess.coup_refuse_detail", "game.titre_victoire", "game.titre_defaite", "game.titre_annulee",
    "lichess.attente_premier_coup.titre", "lichess.attente_premier_coup.texte_html",
    "lichess.premier_coup_decompte", "lichess.premier_coup_sans_decompte",
    "lichess.nulle_attente_reponse", "lichess.annulee_titre",
    "lichess.annulee_premier_coup_trop_tard", "lichess.annulee_cause_inconnue",
    "lichess.rejouer_memes_reglages",
]


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_nouvelles_cles_i18n_presentes(locale):
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in NEW_I18N_KEYS:
        assert key in data, f"{key} absente de {locale}.json"
        assert data[key], f"{key} vide dans {locale}.json"


# ── app.js : jamais le jeton, jamais d'innerHTML pour du texte Lichess ─────

def _read_appjs():
    from pathlib import Path
    return Path(__file__).resolve().parents[2].joinpath(
        "nicsoft", "web", "static", "app.js"
    ).read_text(encoding="utf-8")


def test_appjs_wiring_present():
    src = _read_appjs()
    for needle in [
        'socket.on("lichess_init"', 'socket.on("lichess_move"', 'socket.on("lichess_clock"',
        'socket.on("lichess_reconnecting"', 'socket.on("lichess_board_lost"',
        'socket.on("lichess_draw_offered"', 'socket.on("lichess_promotion_needed"',
        'socket.on("lichess_move_refused"', 'socket.on("lichess_toast"',
        "function startGameLichess", "function selectColorLichess", "function lichessSubmitPromotion",
        '"start_lichess"', '"lichess_resign"', '"lichess_propose_draw"',
    ]:
        assert needle in src, f"{needle!r} absent de app.js"


def test_appjs_jamais_de_jeton_lichess_cote_client():
    import re
    src = _read_appjs()
    assert "lichess_token" in src  # présence/suppression de jeton (indice), jamais sa valeur
    # Aucune constante ressemblant à un vrai jeton Lichess ("lip_...") ne doit apparaître
    # (distinct de mots comme "flip_board" : on exige la frontière "lip_" précédée d'un
    # caractère non alphabétique ou du début de chaîne).
    assert re.search(r"(?<![A-Za-z])lip_[A-Za-z0-9]", src) is None


def test_appjs_lichess_move_refuse_utilise_textcontent_ou_t():
    src = _read_appjs()
    start = src.index('socket.on("lichess_move_refused"')
    end = src.index("\n});", start)
    bloc = src[start:end]
    assert "innerHTML" not in bloc


def test_appjs_lichess_toast_utilise_textcontent_ou_t():
    src = _read_appjs()
    start = src.index('socket.on("lichess_toast"')
    end = src.index("\n});", start)
    bloc = src[start:end]
    assert "innerHTML" not in bloc
