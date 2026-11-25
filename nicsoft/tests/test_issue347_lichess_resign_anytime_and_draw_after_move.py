"""
nicsoft/tests/test_issue347_lichess_resign_anytime_and_draw_after_move.py
— AlChess

Issue #347, partie 1 : deux demandes d'Alain après une partie réelle contre
un HUMAIN (cadence longue, 15-20 min de réflexion par coup) :

  1. Abandonner ne pouvait être cliqué que pendant SON tour (issue #321) —
     impossible d'abandonner pendant que l'adversaire réfléchit, alors que
     Lichess le permet à tout moment. Contre l'IA de Lichess (qui répond en
     quelques secondes), le comportement de #321 convenait et reste
     inchangé.
  2. Proposer nulle devait suivre l'usage FIDE (on propose nulle APRÈS
     avoir joué son coup, pendant que l'adversaire réfléchit — jamais
     avant) plutôt que « mon tour » (#321), pour supprimer la confusion
     d'une offre faite pendant le coup adverse jugée refusée au coup
     suivant. Contre l'IA, rien ne change (toujours « mon tour », #321).

Corrections dans LichessGame (nicsoft/modes/lichess/game.py) :
  - _compute_action_buttons() : deux branches distinctes selon
    self._opponent_is_ai (comportement #321 inchangé pour l'IA ; pour
    l'humain, resign_enabled toujours vrai, draw_enabled piloté par
    self._human_draw_window_open).
  - _human_draw_window_open : posé à True par _submit_move() dès l'envoi
    réussi du coup (et confirmé par _apply_new_moves() à l'écho du flux),
    remis à False par _apply_new_moves() dès qu'un coup adverse est
    appliqué.
  - _safe_draw_offer_call() : message dédié (jamais « coup refusé ») si
    Lichess refuse une nouvelle offre de nulle.

Entièrement sans réseau (FakeTransport/GameClient, voir test_issue309) et
sans matériel (FakeBoard).
"""
import json

import chess

from nicsoft.modes.lichess.game import LichessGame
from nicsoft.modes.lichess.game_client import GameClient
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
from nicsoft.tests.test_issue323_lichess_resume import _make_resuming_game


# ═══════════════════════════════════════════════════════════════════════
# 1. Abandonner reste actif à tout moment contre un HUMAIN.
# ═══════════════════════════════════════════════════════════════════════

def test_abandon_actif_pendant_le_tour_adverse_humain(monkeypatch):
    """Les blancs (utilisateur) viennent de jouer e4 — c'est le tour de
    l'adversaire humain, qui réfléchit (pas encore de coup physique à
    reproduire). Abandonner doit rester actif (issue #347, point 1)."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board, known_user_color="white")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "state": {"status": "started", "moves": ""},
    })
    game.board.push_uci("e2e4")  # simule le coup déjà confirmé par le flux
    game._moves_applied = 1
    resign_enabled, _ = game._compute_action_buttons()
    assert resign_enabled is True


def test_abandon_actif_pendant_reproduction_du_coup_adverse_humain(monkeypatch):
    """L'adversaire humain vient de jouer (coup reçu via le flux) — en
    attente de reproduction physique par l'utilisateur. Abandonner doit
    rester actif (issue #347, point 1), contrairement au comportement
    d'avant cette issue (grisé tant que le coup n'était pas reproduit)."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board, known_user_color="black")
    game._apply_game_full({
        "white": {"id": "opp", "name": "Adversaire"}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game._awaiting_physical_replication is True
    resign_enabled, draw_enabled = game._compute_action_buttons()
    assert resign_enabled is True
    assert draw_enabled is False  # l'utilisateur n'a pas encore joué son coup


def test_abandon_actif_pendant_une_reprise_humaine(monkeypatch):
    """Reprise d'une partie contre un humain (étape L2b) : Abandonner doit
    rester actif dès l'écran de mise en place, avant même la reconstruction
    de la position (comportement de #325 déjà vrai, confirmé ici pour un
    adversaire humain avec les nouvelles règles de #347)."""
    game, board, events = _make_resuming_game(monkeypatch, opponent_is_ai=False)
    assert game._resume_pending is True
    resign_enabled, draw_enabled = game._compute_action_buttons()
    assert resign_enabled is True
    assert draw_enabled is False


def test_abandon_actif_en_position_illegale_contre_un_humain(monkeypatch):
    """Contrairement à l'IA (où une position illégale grise les deux
    boutons), Abandonner reste actif contre un humain même en position
    illégale (issue #347 : plus aucune dépendance à l'état physique pour
    ce bouton, contre un humain)."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board, known_user_color="black")
    game._apply_game_full({
        "white": {"id": "opp", "name": "Adversaire"}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()
    after_e4 = chess.Board()
    after_e4.push_uci("e2e4")
    wrong_board = after_e4.copy()
    wrong_board.remove_piece_at(chess.D2)
    wrong_board.set_piece_at(chess.D4, chess.Piece(chess.PAWN, chess.WHITE))
    board.current_fen = wrong_board.board_fen() + " w - - 0 1"
    for _ in range(game.ILLEGAL_STABLE_READS_REQUIRED):
        game._tick_physical()
    assert game._illegal_position_active is True
    resign_enabled, _ = game._compute_action_buttons()
    assert resign_enabled is True


def test_abandon_toujours_grise_hors_tour_contre_l_ia(monkeypatch):
    """Contre l'IA de Lichess, le comportement de #321 reste exactement
    inchangé (issue #347 : « rien ne change contre l'IA ») — Abandonner
    grisé hors tour et hors échiquier perdu."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    # Pas le tour de l'utilisateur (blanc) — IA (noir) au trait.
    assert game.board.turn == chess.BLACK
    resign_enabled, draw_enabled = game._compute_action_buttons()
    assert (resign_enabled, draw_enabled) == (False, False)


def test_abandon_pendant_tour_adverse_humain_fonctionne_de_bout_en_bout(monkeypatch):
    """Issue #347, point 3 : vérifie que l'action lichess_resign envoyée
    PENDANT le tour de l'adversaire (humain) aboutit normalement — ordre
    réseau envoyé, partie terminée, aucune aide/moteur en jeu (ce module
    n'importe jamais engine_manager — vérifié par ARC-001 ailleurs)."""
    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    resign_calls = []
    transport = FakeTransport()
    game, client, _ = _make_game(nl_inst=board, transport=transport, known_user_color="white")
    monkeypatch.setattr(client, "resign", lambda gid: resign_calls.append(gid))
    monkeypatch.setattr(game, "_save_pgn", lambda result: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        # Au moins 2 coups joués, pour que _request_resign_or_abort()
        # choisisse resign() plutôt qu'abort() (annulation, réservée aux
        # tout premiers coups — comportement inchangé par #347).
        "state": {"status": "started", "moves": "e2e4 e7e5 g1f3"},
    })
    # C'est le tour de l'adversaire (noir) — pas celui de l'utilisateur.
    assert game.board.turn == chess.BLACK
    actions.put({"type": "lichess_resign"})
    game._process_browser_actions()
    assert resign_calls == ["gid1"]
    assert game.game_over is True
    assert game._status == "resign"
    assert game._winner == "black"
    game._finalize()
    over_events = _events_of(events, "game_over")
    assert over_events and over_events[-1]["result"] == "0-1"
    assert over_events[-1]["skip"] is False


# ═══════════════════════════════════════════════════════════════════════
# 2. Proposer nulle : usage FIDE contre un humain, #321 inchangé contre l'IA.
# ═══════════════════════════════════════════════════════════════════════

def test_nulle_grisee_avant_le_premier_coup_pour_les_blancs(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board, known_user_color="white")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "state": {"status": "started", "moves": ""},
    })
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is False


def test_nulle_sactive_des_lenvoi_du_coup_blanc(monkeypatch):
    """Dès que play_move() réussit (sans attendre l'écho du flux), la
    fenêtre s'ouvre — issue #347, point 2 : « dès que l'utilisateur a joué
    son coup (envoyé à Lichess) »."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    sent = []
    game, client, _ = _make_game(nl_inst=board, known_user_color="white")
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append(uci))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "state": {"status": "started", "moves": ""},
    })
    board.current_fen = AFTER_E2E4_W
    _settle_physical_move(game)
    assert sent == ["e2e4"]
    assert game._human_draw_window_open is True
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is True


def test_nulle_reste_active_pendant_que_ladversaire_reflechit(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, client, _ = _make_game(nl_inst=board, known_user_color="white")
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "state": {"status": "started", "moves": ""},
    })
    board.current_fen = AFTER_E2E4_W
    _settle_physical_move(game)
    for _ in range(10):
        game._tick_physical()
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is True


def test_nulle_regrisee_au_coup_suivant_de_ladversaire(monkeypatch):
    """Dès que le coup adverse arrive (gameState), la fenêtre se referme —
    y compris pendant la reproduction physique de ce coup et pendant le
    tour de l'utilisateur avant qu'il ne rejoue (issue #347, point 2)."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, client, _ = _make_game(nl_inst=board, known_user_color="white")
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "state": {"status": "started", "moves": ""},
    })
    board.current_fen = AFTER_E2E4_W
    _settle_physical_move(game)
    assert game._human_draw_window_open is True
    # L'adversaire (noir) répond e7e5.
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})
    assert game._human_draw_window_open is False
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is False
    # Toujours grisé pendant la reproduction physique de ce coup adverse.
    assert game._awaiting_physical_replication is True
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is False
    # Et pendant le tour de l'utilisateur, avant qu'il n'ait rejoué.
    board.current_fen = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR").board_fen() + " w - - 0 1"
    game._tick_physical()
    assert game._awaiting_physical_replication is False
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is False


def test_nulle_valable_pour_les_noirs_apres_leur_coup(monkeypatch):
    """Même règle pour les noirs — l'issue précise « valable pour les
    blancs comme pour les noirs, y compris après le tout premier coup »."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, client, _ = _make_game(nl_inst=board, known_user_color="black")
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)
    game._apply_game_full({
        "white": {"id": "opp", "name": "Adversaire"}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()  # reproduit e4
    assert game._awaiting_physical_replication is False
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is False  # pas encore joué son propre coup
    after_e5 = chess.Board()
    after_e5.push_uci("e2e4")
    after_e5.push_uci("e7e5")
    board.current_fen = after_e5.board_fen() + " b - - 0 1"
    _settle_physical_move(game)
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is True


def test_nulle_toujours_grisee_contre_l_ia(monkeypatch):
    """Issue #347 : « contre l'IA de Lichess, rien ne change » — le
    comportement de #327/#321 reste identique."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, client, _ = _make_game(nl_inst=board)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()
    _, draw_enabled = game._compute_action_buttons()
    assert draw_enabled is False


def test_message_persistant_nulle_et_refus_apres_coup_adverse(monkeypatch):
    """Garde le comportement de #321 (bandeau persistant) et #318 (refus
    déclaré seulement après un vrai coup de l'adversaire) — inchangés par
    #347, qui ne touche qu'à l'activation du bouton."""
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, client, _ = _make_game(nl_inst=board, known_user_color="white")
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)
    monkeypatch.setattr(client, "answer_draw", lambda gid, accept: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "state": {"status": "started", "moves": ""},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()
    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True
    assert _events_of(events, "lichess_draw_proposed")
    # L'adversaire répond par un coup (sans accepter) — refus déclaré
    # SEULEMENT maintenant (#318), jamais sur l'écho de notre propre coup.
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})
    assert game._my_draw_offer_pending is False
    assert _events_of(events, "lichess_draw_refused")


def test_nouvelle_offre_refusee_par_lichess_message_clair_sans_planter(monkeypatch):
    """Issue #347, point 2 : si Lichess refuse une nouvelle offre (ex. une
    offre déjà active), le message est clair (pas « coup refusé ») et rien
    ne plante."""
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    transport = FakeTransport(requests=[
        lambda m, u, t, f: TransportHTTPError(400, json.dumps({"error": "You already have an offer"})),
    ])
    game, client, _ = _make_game(nl_inst=board, transport=transport, known_user_color="white")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "state": {"status": "started", "moves": ""},
    })
    game._human_draw_window_open = True
    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()  # ne doit jamais lever
    toasts = _events_of(events, "lichess_toast")
    assert toasts and toasts[-1]["message_key"] == "lichess.nulle_requete_refusee"
    assert toasts[-1]["persistent"] is True
    assert "already have an offer" in toasts[-1]["vars"]["detail"]
    refused_events = _events_of(events, "lichess_move_refused")
    assert refused_events == []  # jamais le message générique « coup refusé »
