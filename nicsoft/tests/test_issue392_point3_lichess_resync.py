"""
nicsoft/tests/test_issue392_point3_lichess_resync.py — AlChess

Issue #392, point 3 (étude #391, point 3) : coupure réseau de ~25 à 37s en
pleine partie classée le 26/11/2026 — les coups 2.c4 et 3.e4 d'Alain ont
été réellement envoyés et acceptés par Lichess, mais le flux d'évènements
de la partie est resté silencieux SANS lever d'exception (coupure plus
courte que l'ancien seuil de 90s, transport.py::STREAM_READ_TIMEOUT_S).
Aucun coup adverse (e6, Nxe4) n'a été affiché ; les refus suivants
(« Not your turn, or game already over », coup physique refusé) sont la
conséquence d'une position locale périmée de 4 demi-coups. Alain a même
été invité à « remettre la pièce à sa place » alors que Lichess avait déjà
accepté son coup.

Ce fichier teste :
  a) GAME_STREAM_READ_TIMEOUT_S (20s, transport.py) — dédié au flux de
     PARTIE, distinct de STREAM_READ_TIMEOUT_S (90s, recherche/évènements)
     — faux serveur HTTP local (jamais lichess.org), comme #383 point 2.
  b) LichessGame._resync_from_lichess() — relit l'état complet et
     l'applique par le chemin normal des coups reçus (_apply_game_state) :
     coups manqués affichés/bipés/LED comme des coups reçus en direct,
     pendules corrigées ; échec réseau → bandeau #378 + réessai croissant
     (_start_resync_retry_loop/_resync_retry_worker).
  c) LichessGame._handle_move_rejected() — refus ambigu : succès silencieux
     si la resynchronisation montre le coup déjà appliqué (#384 inchangé),
     cases rouges (position Lichess resynchronisée) si elle montre un vrai
     désaccord avec l'échiquier physique (jamais plus "remettez la pièce"),
     bandeau (sans "coup refusé") si la resynchronisation échoue.

Entièrement sans réseau réel (FakeTransport / faux serveur HTTP local
127.0.0.1) et sans matériel (FakeBoard) — même conventions que
test_issue309_lichess_l2a.py / test_issue383_point2_stream_close.py.
"""
import http.client
import http.server
import json
import threading
import time

import chess
import pytest

import nicsoft.modes.lichess.game as game_mod
import nicsoft.modes.lichess.transport as transport_mod
from nicsoft.modes.lichess.errors import LichessApiError
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.transport import TransportNetworkError, TransportTimeoutError, UrllibTransport
from nicsoft.tests.test_issue309_lichess_l2a import (
    FakeBoard,
    FakeTransport,
    _events_of,
    _line,
    _make_game,
    _make_recorder,
    _settle_physical_move,
)


# ═══════════════════════════════════════════════════════════════════════
# a) Seuil dédié du flux de PARTIE — faux serveur HTTP local, jamais
#    lichess.org (même principe que test_issue383_point2_stream_close.py).
# ═══════════════════════════════════════════════════════════════════════

class _SilentAfterFirstLineHandler(http.server.BaseHTTPRequestHandler):
    """N'envoie qu'une seule ligne puis se tait `hold_s` secondes — assez
    longtemps pour dépasser le seuil testé (réduit par monkeypatch), jamais
    assez pour une connexion réelle à lichess.org (serveur local)."""

    first_line_sent = threading.Event()
    hold_s = 5.0

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(b"premiere-ligne\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        type(self).first_line_sent.set()
        time.sleep(type(self).hold_s)

    def log_message(self, *a, **kw):
        pass


@pytest.fixture
def fake_silent_http_server():
    _SilentAfterFirstLineHandler.first_line_sent = threading.Event()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SilentAfterFirstLineHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_stream_lines_utilise_le_seuil_dedie_du_flux_de_partie(monkeypatch, fake_silent_http_server):
    """UrllibTransport.stream_lines() (seul appelant : GameClient.stream_game/
    peek_game_full, flux de PARTIE) doit déclencher TransportTimeoutError
    peu après GAME_STREAM_READ_TIMEOUT_S — jamais attendre les 90s de
    STREAM_READ_TIMEOUT_S (régression exacte de l'étude #391, point 3)."""
    monkeypatch.setattr(transport_mod, "GAME_STREAM_READ_TIMEOUT_S", 0.5)
    port = fake_silent_http_server.server_address[1]
    url = f"http://127.0.0.1:{port}/stream"
    monkeypatch.setattr(transport_mod, "ensure_https", lambda u: None)

    transport = UrllibTransport()
    t0 = time.monotonic()
    with pytest.raises(TransportTimeoutError):
        for _line_ in transport.stream_lines(url, "lip_x"):
            pass
    elapsed = time.monotonic() - t0
    assert elapsed < 3.0, f"a attendu {elapsed:.1f}s — bien au-delà du seuil dédié de 0.5s"


def test_open_stream_reste_sur_lancien_seuil_plus_long(monkeypatch, fake_silent_http_server):
    """Non-régression : open_stream()/StreamHandle (recherche/évènements,
    seek.py) reste sur STREAM_READ_TIMEOUT_S, jamais raccourci par cette
    issue (aucune preuve de maintien de connexion régulier pour ces flux-là
    — voir transport.py)."""
    monkeypatch.setattr(transport_mod, "STREAM_READ_TIMEOUT_S", 0.5)
    monkeypatch.setattr(transport_mod, "GAME_STREAM_READ_TIMEOUT_S", 999)  # ne doit PAS s'appliquer ici
    port = fake_silent_http_server.server_address[1]
    url = f"http://127.0.0.1:{port}/stream"
    monkeypatch.setattr(transport_mod, "ensure_https", lambda u: None)

    transport = UrllibTransport()
    handle = transport.open_stream("GET", url, "lip_x")
    t0 = time.monotonic()
    with pytest.raises(TransportTimeoutError):
        for _line_ in handle.lines():
            pass
    elapsed = time.monotonic() - t0
    assert elapsed < 3.0, f"a attendu {elapsed:.1f}s — le seuil réduit de STREAM_READ_TIMEOUT_S n'a pas été utilisé"


def test_les_deux_seuils_sont_bien_distincts():
    assert transport_mod.GAME_STREAM_READ_TIMEOUT_S < transport_mod.STREAM_READ_TIMEOUT_S


# ═══════════════════════════════════════════════════════════════════════
# b) LichessGame._resync_from_lichess() — resynchronisation active.
# ═══════════════════════════════════════════════════════════════════════

def _gamefull(moves, status="started", white=None, black=None):
    return _line({
        "type": "gameFull", "id": "gid1", "rated": False,
        "white": white or {"id": "alain"}, "black": black or {"aiLevel": 1},
        "state": {"status": status, "moves": moves, "wtime": 500000, "btime": 500000},
    })


def test_resync_applique_le_coup_adverse_manque_comme_un_coup_recu(monkeypatch):
    """Coeur du point 3a : un coup adverse manqué pendant un flux resté
    silencieux (simulation) est appliqué par le chemin NORMAL des coups
    reçus (_apply_game_state) — évènement lichess_move, attente de
    réplication physique (LED), pendules repoussées — jamais une
    resynchronisation silencieuse qui l'escamoterait."""
    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    transport = FakeTransport(stream_batches=[[_gamefull("e2e4 e7e6")]])
    game, client, _ = _make_game(nl_inst=board, transport=transport, game_id="gid1")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game._moves_applied == 1
    events.clear()

    ok = game._resync_from_lichess("silence du flux (simulation)")

    assert ok is True
    assert game._moves_applied == 2
    assert game.board.move_stack[-1].uci() == "e7e6"
    move_events = _events_of(events, "lichess_move")
    assert move_events and move_events[-1]["uci"] == "e7e6" and move_events[-1]["opponent_move"] is True
    assert game._awaiting_physical_replication is True  # attend que le plateau reproduise e7e6
    assert board.led_calls  # LED posées sur les cases du coup adverse
    assert _events_of(events, "lichess_clock")  # pendules repoussées (même traitement qu'un coup reçu)


def test_resync_applique_plusieurs_coups_manques_dans_lordre(monkeypatch):
    """Reproduction exacte de l'incident du 26/11/2026 : deux coups
    adverses manqués pendant la coupure (e6 puis Nxe4, ici simplifié en
    deux coups e7e6/g8f6) sont tous deux rattrapés, dans l'ordre, par un
    seul appel de resynchronisation."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    transport = FakeTransport(stream_batches=[[_gamefull("e2e4 e7e6 g1f3 g8f6")]])
    game, client, _ = _make_game(nl_inst=board, transport=transport, game_id="gid1")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })

    ok = game._resync_from_lichess("silence du flux (simulation, plusieurs coups)")

    assert ok is True
    assert game._moves_applied == 4
    ucis = [m.uci() for m in game.board.move_stack]
    assert ucis == ["e2e4", "e7e6", "g1f3", "g8f6"]


def test_resync_sans_coup_manque_najamais_de_double_traitement(monkeypatch):
    """_apply_new_moves (appelé par _apply_game_state) est déjà sans effet
    si aucun coup n'est manquant — une resynchronisation qui ne révèle rien
    de neuf ne rejoue jamais un coup déjà affiché."""
    events, _, _ = _make_recorder(monkeypatch)
    transport = FakeTransport(stream_batches=[[_gamefull("e2e4")]])
    game, client, _ = _make_game(transport=transport, game_id="gid1")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    events.clear()

    ok = game._resync_from_lichess("rien de neuf")

    assert ok is True
    assert game._moves_applied == 1
    assert _events_of(events, "lichess_move") == []


def test_resync_echec_reseau_declenche_bandeau_378_pas_de_toast_coup_refuse(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    transport = FakeTransport(stream_batches=[[TransportNetworkError("coupure simulée")]])
    game, client, _ = _make_game(transport=transport)

    ok = game._resync_from_lichess("échec réseau simulé")

    assert ok is False
    assert _events_of(events, "lichess_reconnecting")
    toasts = _events_of(events, "lichess_toast")
    assert any(d["message_key"] == "lichess.erreur_reseau" for d in toasts)
    assert _events_of(events, "lichess_move_refused") == []


def test_resync_flux_ferme_sans_gamefull_est_un_echec(monkeypatch):
    transport = FakeTransport(stream_batches=[[_line({"type": "chatLine"})]])
    game, client, _ = _make_game(transport=transport)

    ok = game._resync_from_lichess("pas de gameFull")

    assert ok is False


def test_resync_retry_loop_reessaie_jusquau_succes_avec_delais_croissants(monkeypatch):
    """Issue #392, point 3c : échec puis réessai en arrière-plan, délais
    croissants déjà documentés (RECONNECT_DELAYS_S), jamais d'abandon."""
    game, client, _ = _make_game()
    monkeypatch.setattr(game_mod, "RECONNECT_DELAYS_S", (0.01, 0.01, 0.01))
    attempts = []

    def _fake_resync(reason):
        attempts.append(reason)
        return len(attempts) >= 3

    monkeypatch.setattr(game, "_resync_from_lichess", _fake_resync)

    game._start_resync_retry_loop("test retry")
    deadline = time.monotonic() + 2.0
    while game._resync_retry_active and time.monotonic() < deadline:
        time.sleep(0.01)

    assert len(attempts) == 3
    assert game._resync_retry_active is False


def test_resync_retry_loop_sarrete_a_la_fin_de_partie(monkeypatch):
    """Jamais d'abandon automatique, mais le réessai n'a plus de sens une
    fois la partie terminée (par un autre mécanisme, ex. l'adversaire a
    abandonné pendant la coupure) — la boucle doit s'arrêter proprement."""
    game, client, _ = _make_game()
    monkeypatch.setattr(game_mod, "RECONNECT_DELAYS_S", (0.05, 0.05))
    calls = {"n": 0}

    def _fake_resync(reason):
        calls["n"] += 1
        game.game_over = True  # la partie se termine pendant le 1er essai
        return False

    monkeypatch.setattr(game, "_resync_from_lichess", _fake_resync)

    game._start_resync_retry_loop("test fin de partie")
    deadline = time.monotonic() + 2.0
    while game._resync_retry_active and time.monotonic() < deadline:
        time.sleep(0.01)

    assert calls["n"] == 1
    assert game._resync_retry_active is False


def test_resync_retry_loop_jamais_deux_boucles_a_la_fois(monkeypatch):
    game, client, _ = _make_game()
    monkeypatch.setattr(game_mod, "RECONNECT_DELAYS_S", (0.2,))
    starts = []

    def _fake_resync(reason):
        return True

    monkeypatch.setattr(game, "_resync_from_lichess", _fake_resync)
    game._resync_retry_active = True  # simule une boucle déjà en cours

    t = game._start_resync_retry_loop("ne doit pas démarrer")
    assert t is None


# ═══════════════════════════════════════════════════════════════════════
# c) LichessGame._handle_move_rejected() — intégration complète.
# ═══════════════════════════════════════════════════════════════════════

def _setup_white_to_move(monkeypatch, transport):
    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, client, _ = _make_game(nl_inst=board, transport=transport, game_id="gid1")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    return game, board, events, states, actions


def test_refus_ambigu_resynchronisation_montre_coup_deja_applique_succes_silencieux(monkeypatch):
    """#384 inchangé, mais désormais via la resynchronisation ACTIVE plutôt
    que la seule relecture du flux déjà en route (point 3b) : si la
    resynchronisation applique notre propre coup à sa place attendue,
    succès silencieux, aucun toast « coup refusé »."""
    transport = FakeTransport(requests=[
        lambda m, u, t, f: LichessApiError(400, "Not your turn, or game already over"),
    ])
    game, board, events, states, actions = _setup_white_to_move(monkeypatch, transport)
    monkeypatch.setattr(game, "_drain_pending_stream_events", lambda timeout_s: None)

    def _fake_resync(reason):
        game.board.push(chess.Move.from_uci("e2e4"))
        game._moves_applied = 1
        return True

    monkeypatch.setattr(game, "_resync_from_lichess", _fake_resync)

    game._submit_move("e2e4")

    assert _events_of(events, "lichess_move_refused") == []
    assert game._awaiting_resync_reset is False
    assert game.board.move_stack[-1].uci() == "e2e4"


def test_refus_ambigu_resynchronisation_confirme_vrai_desaccord_cases_rouges(monkeypatch):
    """Point 3b : la resynchronisation réussit (contact Lichess) mais la
    position reste différente de l'échiquier physique — cases rouges avec
    la position Lichess (déjà resynchronisée) comme cible, jamais plus le
    texte générique « remettez la pièce »."""
    transport = FakeTransport(requests=[
        lambda m, u, t, f: LichessApiError(400, "Not your turn, or game already over"),
    ])
    game, board, events, states, actions = _setup_white_to_move(monkeypatch, transport)
    monkeypatch.setattr(game, "_drain_pending_stream_events", lambda timeout_s: None)
    monkeypatch.setattr(game, "_resync_from_lichess", lambda reason: True)  # rien de neuf

    game._submit_move("e2e4")

    refused = _events_of(events, "lichess_move_refused")
    assert len(refused) == 1
    assert game._awaiting_resync_reset is True
    assert game._reset_target_fen is None  # jamais l'ancien mécanisme en parallèle
    target_fen = game._resync_target_fen
    assert target_fen == game.board.board_fen()

    # L'échiquier physique rejoint la position Lichess (déjà resynchronisée)
    # — reprise normale, cases rouges retirées (_check_resync_reset).
    board.current_fen = target_fen + " w - - 0 1"
    game._tick_physical()
    assert game._awaiting_resync_reset is False
    assert _events_of(events, "lichess_position_ok")


def test_refus_ambigu_resynchronisation_echoue_bandeau_sans_toast_coup_refuse(monkeypatch):
    """Point 3c/3d : si la resynchronisation échoue (réseau toujours
    indisponible), ni succès silencieux ni vraie erreur ne sont affichés —
    jamais de toast « coup refusé », le bandeau de coupure et le réessai en
    arrière-plan prennent le relais."""
    transport = FakeTransport(requests=[
        lambda m, u, t, f: LichessApiError(400, "Not your turn, or game already over"),
    ])
    game, board, events, states, actions = _setup_white_to_move(monkeypatch, transport)
    monkeypatch.setattr(game, "_drain_pending_stream_events", lambda timeout_s: None)
    monkeypatch.setattr(game_mod, "RECONNECT_DELAYS_S", (0.05, 0.05, 0.05))
    monkeypatch.setattr(game, "_resync_from_lichess", lambda reason: False)

    game._submit_move("e2e4")

    assert _events_of(events, "lichess_move_refused") == []
    assert game._awaiting_resync_reset is False
    assert game._resync_retry_active is True
    # Nettoyage : la boucle d'arrière-plan tourne avec de vrais délais —
    # jamais d'abandon automatique de la partie.
    game.game_over = True
    deadline = time.monotonic() + 2.0
    while game._resync_retry_active and time.monotonic() < deadline:
        time.sleep(0.01)
    assert game._resync_retry_active is False


def test_message_non_ambigu_najamais_de_resynchronisation(monkeypatch):
    """Non-régression : un message non ambigu (coup réellement illégal) ne
    déclenche jamais la resynchronisation — comportement de #309/#347
    inchangé."""
    transport = FakeTransport(requests=[
        lambda m, u, t, f: LichessApiError(400, "This move is illegal"),
    ])
    game, board, events, states, actions = _setup_white_to_move(monkeypatch, transport)
    resync_called = []
    monkeypatch.setattr(game, "_resync_from_lichess", lambda reason: resync_called.append(reason) or True)

    game._submit_move("e2e4")

    assert resync_called == []
    assert game._awaiting_piece_reset is True
    assert game._awaiting_resync_reset is False
