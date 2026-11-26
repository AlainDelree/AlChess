"""
nicsoft/tests/test_issue347_lichess_ambiguous_move_rejection.py — AlChess

Issue #347, partie 2, point 2 : cas réel constaté par Alain le 15/11/2026,
en partie contre un humain (noirs) — journal des parties Lichess du
15/11/2026 (recherche commencée à 20:14) :

  20:30:45       dernier coup de l'adversaire reçu
  20:30:52.906   coup physique d'Alain (échec et mat) reconnu et envoyé
  20:30:52.977   nouvel état de partie reçu (l'adversaire a abandonné)
  20:30:53.028   réponse Lichess au coup : HTTP 400 « Not your turn, or
                 game already over »
  20:30:53.030   partie terminée — statut=resign, vainqueur=black

L'adversaire a abandonné quelques dizaines de millisecondes avant que
Lichess reçoive le coup physique d'Alain : il a GAGNÉ, mais l'écran ne l'a
montré que comme un coup refusé (toast bref, vite disparu) — l'écran
d'analyse ne montrait pas ce dernier coup (jamais poussé sur self.board
avant confirmation du flux, comportement préexistant et correct : il n'a
en effet jamais été accepté par Lichess).

Diagnostic : LichessGame._submit_move() (nicsoft/modes/lichess/game.py)
affichait, sur toute LichessApiError, le toast générique « Lichess a
refusé ce coup » SANS jamais vérifier si la partie était entre-temps
terminée — alors que l'événement de fin (gameState, flux SSE) était ici
déjà disponible dans self._stream_event_queue au moment du refus HTTP
(51 ms d'écart dans le journal réel ci-dessus, bien avant que la réponse
HTTP n'arrive).

Correctif : _handle_move_rejected() distingue le message HTTP 400 ambigu
« Not your turn, or game already over » (is_ambiguous_turn_or_over_error,
errors.py) d'une vraie erreur, et — seulement dans ce cas — relit l'état
réel de la partie en traitant tout événement déjà disponible dans le flux
(_drain_pending_stream_events, attente bornée à
LichessGame.AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S = 2.0 s). Si la partie est
confirmée terminée : aucun toast « coup refusé », le déroulement normal de
fin de partie prend le relais (_finalize), et
self._last_move_rejected_after_game_over (payload game_over,
"last_move_rejected") permet à l'écran d'indiquer que ce dernier coup
physique n'a pas été accepté. Sinon (vraie erreur, ou partie toujours en
cours après le délai d'attente) : comportement inchangé (toast + remise en
place demandée).

Entièrement sans réseau (FakeTransport/GameClient, voir test_issue309) et
sans matériel (FakeBoard).
"""
import json

import chess

from nicsoft.modes.lichess.errors import is_ambiguous_turn_or_over_error
from nicsoft.modes.lichess.transport import TransportHTTPError
from nicsoft.tests.test_issue309_lichess_l2a import (
    FakeBoard,
    FakeTransport,
    _events_of,
    _make_game,
    _make_recorder,
    _settle_physical_move,
)
from nicsoft.tests.test_issue311_lichess_sequencing import AFTER_E2E4_W

_AMBIGUOUS_BODY = json.dumps({"error": "Not your turn, or game already over"})


# ═══════════════════════════════════════════════════════════════════════
# 1. Fonction pure de détection du message ambigu (errors.py).
# ═══════════════════════════════════════════════════════════════════════

def test_is_ambiguous_turn_or_over_error_detecte_le_message_exact():
    assert is_ambiguous_turn_or_over_error("Not your turn, or game already over") is True
    assert is_ambiguous_turn_or_over_error("NOT YOUR TURN, OR GAME ALREADY OVER") is True


def test_is_ambiguous_turn_or_over_error_ignore_un_autre_message():
    assert is_ambiguous_turn_or_over_error("This move is illegal") is False
    assert is_ambiguous_turn_or_over_error("") is False
    assert is_ambiguous_turn_or_over_error(None) is False


# ═══════════════════════════════════════════════════════════════════════
# 2. Cas réel : adversaire abandonne, coup refusé <100ms plus tard.
# ═══════════════════════════════════════════════════════════════════════

def _setup_black_after_e4(monkeypatch, transport):
    """Partie contre un humain, utilisateur noir, blancs ont joué e4 et
    l'utilisateur vient de le reproduire physiquement — c'est son tour."""
    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, client, _ = _make_game(nl_inst=board, transport=transport, known_user_color="black")
    game._apply_game_full({
        "white": {"id": "opp", "name": "Adversaire"}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()
    assert game._awaiting_physical_replication is False
    return game, board, events, states, actions


def test_coup_refuse_apres_abandon_adversaire_affiche_la_victoire_sans_toast_erreur(monkeypatch):
    """Reproduit le cas réel du journal : l'événement de fin (adversaire a
    abandonné) est déjà dans le flux au moment du refus HTTP ambigu — en
    moins de 100ms, comme dans la vraie partie."""
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, _AMBIGUOUS_BODY),
    ])
    game, board, events, states, actions = _setup_black_after_e4(monkeypatch, transport)
    monkeypatch.setattr(game, "_save_pgn", lambda result: None)

    # L'adversaire (blancs) a abandonné — l'événement est déjà disponible
    # dans le flux de partie (reader thread indépendant) AVANT que la
    # réponse HTTP (ci-dessus, 400 ambigu) ne revienne.
    game._stream_event_queue.put({
        "type": "gameState", "status": "resign", "winner": "black", "moves": "e2e4",
    })

    # Coup physique de l'utilisateur (noir) — n'importe quel coup légal
    # suffit à déclencher _submit_move ; la partie réelle était un mat,
    # jamais vérifié ici (sans effet sur le code testé).
    board.current_fen = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR").board_fen() + " b - - 0 1"
    import time as _time
    t0 = _time.monotonic()
    _settle_physical_move(game)
    elapsed_s = _time.monotonic() - t0
    assert elapsed_s < 0.1  # relecture quasi instantanée : l'événement était déjà en file

    assert game.game_over is True
    assert game._status == "resign"
    assert game._winner == "black"
    assert game._last_move_rejected_after_game_over is True

    # Aucun toast « coup refusé » — la victoire s'affiche normalement.
    assert _events_of(events, "lichess_move_refused") == []
    refused_toasts = [
        d for d in _events_of(events, "lichess_toast")
        if "refuse" in (d.get("message_key") or "")
    ]
    assert refused_toasts == []

    game._finalize()
    over_events = _events_of(events, "game_over")
    assert over_events
    payload = over_events[-1]
    assert payload["result"] == "0-1"
    assert payload["opponent_caused_end"] is True
    assert payload["opponent_cause_key"] == "lichess.cause.resign"
    assert payload["last_move_rejected"] is True
    # Le PGN ne doit jamais contenir ce dernier coup physique — jamais
    # poussé sur self.board avant confirmation du flux (comportement
    # préexistant, confirmé ici toujours vrai).
    assert len(game.board.move_stack) == 1  # seulement e2e4


def test_coup_refuse_vraie_erreur_hors_tour_reste_un_toast_erreur(monkeypatch):
    """Le même message ambigu, mais la partie n'est PAS terminée (aucun
    événement de fin dans le flux dans le délai imparti) : toast « coup
    refusé » toujours affiché. Issue #392, point 3b : la resynchronisation
    active (déclenchée depuis cette issue, mockée ici pour rester sans
    réseau) confirme que la position reste en désaccord — l'affichage
    bascule sur les cases rouges (position Lichess comme cible), plus
    jamais sur l'ancien "remettez la pièce" (_awaiting_piece_reset)."""
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, _AMBIGUOUS_BODY),
    ])
    game, board, events, states, actions = _setup_black_after_e4(monkeypatch, transport)
    # Délai d'attente du flux raccourci pour ne pas ralentir le test —
    # aucun événement ne sera posé, le cas doit retomber sur la vraie
    # erreur après ce court délai.
    game.AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S = 0.05
    # Resynchronisation (nouvelle requête réseau, #392 point 3a) mockée —
    # simule un contact Lichess réussi qui ne change rien (aucun coup
    # manquant, position toujours en désaccord) : jamais de vrai réseau
    # dans ce test, voir la règle absolue du dossier.
    monkeypatch.setattr(game, "_resync_from_lichess", lambda reason: True)

    board.current_fen = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR").board_fen() + " b - - 0 1"
    _settle_physical_move(game)

    assert game.game_over is False
    assert game._last_move_rejected_after_game_over is False
    refused = _events_of(events, "lichess_move_refused")
    assert refused and "Not your turn" in refused[0]["message"]
    assert game._awaiting_resync_reset is True
    assert game._resync_target_fen == game.board.board_fen()


def test_coup_refuse_message_non_ambigu_reste_inchange(monkeypatch):
    """Un vrai coup illégal (message non ambigu) ne déclenche jamais la
    relecture du flux — comportement de #309, inchangé."""
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, json.dumps({"error": "This move is illegal"})),
    ])
    game, board, events, states, actions = _setup_black_after_e4(monkeypatch, transport)
    game._stream_event_queue.put({
        "type": "gameState", "status": "resign", "winner": "black", "moves": "e2e4",
    })
    board.current_fen = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR").board_fen() + " b - - 0 1"
    _settle_physical_move(game)
    assert game.game_over is False  # l'événement en file n'a jamais été lu
    refused = _events_of(events, "lichess_move_refused")
    assert refused and "illegal" in refused[0]["message"]


def test_journal_dedie_trace_coup_envoye_refus_et_relecture(monkeypatch, tmp_path):
    """Issue #347, partie 2, point 3 : heure précise (horodatage de
    GameLog._write), coup envoyé, réponse de Lichess (code + raison) et
    état relu ensuite — jamais le jeton."""
    from nicsoft.modes.lichess.game_log import GameLog

    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, _AMBIGUOUS_BODY),
    ])
    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    from nicsoft.modes.lichess.game import LichessGame
    from nicsoft.modes.lichess.game_client import GameClient
    client = GameClient("lip_secret_token_value", transport=transport)
    game_log = GameLog("gid_journal347", token="lip_secret_token_value", logs_dir=tmp_path)
    client.attach_game_log(game_log)
    game = LichessGame(
        board, client, "gid_journal347", level=1, player_name="Alain",
        clock_limit_s=900, clock_increment_s=10, known_user_color="black", game_log=game_log,
    )
    game._apply_game_full({
        "white": {"id": "opp", "name": "Adversaire"}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()
    game._stream_event_queue.put({
        "type": "gameState", "status": "resign", "winner": "black", "moves": "e2e4",
    })
    board.current_fen = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR").board_fen() + " b - - 0 1"
    _settle_physical_move(game)
    game_log.close()

    content = game_log.path.read_text(encoding="utf-8")
    assert "lip_secret_token_value" not in content
    assert "e7e5" in content  # coup envoyé journalisé
    assert "HTTP 400" in content and "Not your turn" in content  # réponse Lichess
    assert "partie déjà terminée" in content  # état relu ensuite
    # Heure précise : chaque ligne commence par HH:MM:SS.mmm
    first_line = content.splitlines()[0]
    assert first_line[2] == ":" and first_line[5] == ":" and first_line[8] == "."
