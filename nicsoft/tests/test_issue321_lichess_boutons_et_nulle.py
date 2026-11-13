"""
nicsoft/tests/test_issue321_lichess_boutons_et_nulle.py — AlChess

Issue #321 : essais réels d'Alain (13 novembre 2026, blancs puis noirs) —
les boutons Abandonner/Proposer nulle étaient actifs à tout moment, y
compris pendant que l'adversaire réfléchissait ou que l'utilisateur devait
encore reproduire son coup sur l'échiquier physique ; un coup noir illégal
(d4 joué par erreur à la place du coup noir) n'affichait qu'une bannière
générique sans indiquer quelles cases corriger, avec la phrase du premier
coup toujours affichée par-dessus.

Corrections dans LichessGame (nicsoft/modes/lichess/game.py) :
  - _compute_action_buttons()/_sync_turn_ready() : état (resign_enabled,
    draw_enabled) poussé côté interface via l'événement
    lichess_action_buttons, recalculé à chaque tick physique et à chaque
    transition de partie.
  - _activate_illegal_position()/_clear_illegal_position() : événement
    lichess_illegal_position dédié (expected_fen/physical_fen) quand la
    position physique n'est, pendant le tour de l'utilisateur, ni la
    position attendue ni un coup légal.

Entièrement sans réseau (faux transport/client, voir test_issue309) et sans
matériel (FakeBoard — double exposant current_fen, comme nl_inst réel).
"""
import chess

from nicsoft.modes.lichess.game import LichessGame
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, FakeTransport, _events_of, _make_game, _make_recorder
from nicsoft.tests.test_issue311_lichess_sequencing import AFTER_E2E4_W


# ═══════════════════════════════════════════════════════════════════════
# 1. Boutons grisés pendant le tour adverse / la reproduction de son coup.
# ═══════════════════════════════════════════════════════════════════════

def test_boutons_desactives_au_debut_partie_pour_les_noirs_avant_replication(monkeypatch):
    """Dès la création de la partie (issue #321, point 1 : « y compris au
    tout début de partie ») : l'IA (blancs) a déjà joué e4, l'utilisateur
    (noirs) n'a pas encore reproduit ce coup sur l'échiquier — les deux
    boutons doivent être grisés, pas seulement « pas son tour »."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game.user_color == "black"
    assert game._awaiting_physical_replication is True
    assert game._action_buttons_state == (False, False)
    # Aucun événement n'est forcément émis ici : (False, False) est déjà
    # l'état par défaut côté interface dès lichess_init (voir app.js) —
    # seul un CHANGEMENT d'état déclenche lichess_action_buttons.
    for data in _events_of(events, "lichess_action_buttons"):
        assert data == {"resign_enabled": False, "draw_enabled": False}


def test_boutons_restent_desactives_tant_que_le_coup_adverse_nest_pas_reproduit(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    # Le plateau physique montre encore la position de départ (pas encore
    # reproduit e4) : plusieurs ticks ne doivent rien changer.
    for _ in range(3):
        game._tick_physical()
    assert game._awaiting_physical_replication is True
    assert game._action_buttons_state == (False, False)


# ═══════════════════════════════════════════════════════════════════════
# 2. Boutons actifs quand c'est le tour de l'utilisateur ET que la
#    position physique correspond — pour les deux couleurs.
# ═══════════════════════════════════════════════════════════════════════

def test_boutons_actifs_des_le_debut_de_partie_pour_les_blancs(monkeypatch):
    """Les blancs sont au trait dès le début, position physique de départ
    déjà alignée (issue #321, point 1 : actif dès le tout début)."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    assert game.user_color == "white"
    assert game._action_buttons_state == (True, True)
    btn_events = _events_of(events, "lichess_action_buttons")
    assert btn_events and btn_events[-1] == {"resign_enabled": True, "draw_enabled": True}


def test_boutons_sactivent_pour_les_noirs_une_fois_le_coup_reproduit(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()
    assert game._awaiting_physical_replication is False
    assert game._action_buttons_state == (True, True)


# ═══════════════════════════════════════════════════════════════════════
# 3. Position physique illégale pendant le tour de l'utilisateur (issue
#    #321, point 5 — reproduit exactement l'essai réel du 13/11/2026 :
#    pion blanc d2-d4 joué par erreur à la place du coup noir).
# ═══════════════════════════════════════════════════════════════════════

def test_position_illegale_desactive_les_boutons_et_signale_les_cases(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    board.current_fen = AFTER_E2E4_W
    game._tick_physical()
    assert game._action_buttons_state == (True, True)

    after_e4 = chess.Board()
    after_e4.push_uci("e2e4")
    wrong_board = after_e4.copy()
    wrong_board.remove_piece_at(chess.D2)
    wrong_board.set_piece_at(chess.D4, chess.Piece(chess.PAWN, chess.WHITE))
    wrong_fen = wrong_board.board_fen()
    board.current_fen = wrong_fen + " w - - 0 1"

    for _ in range(game.ILLEGAL_STABLE_READS_REQUIRED):
        game._tick_physical()

    assert game._illegal_position_active is True
    assert game._action_buttons_state == (False, False)
    illegal_events = _events_of(events, "lichess_illegal_position")
    assert illegal_events and illegal_events[-1]["active"] is True
    assert illegal_events[-1]["physical_fen"] == wrong_fen
    assert illegal_events[-1]["expected_fen"] == after_e4.board_fen()

    # La pièce est remise en place : le message disparaît et les boutons
    # redeviennent actifs.
    board.current_fen = after_e4.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert game._illegal_position_active is False
    assert _events_of(events, "lichess_illegal_position")[-1] == {"active": False}
    assert game._action_buttons_state == (True, True)


# ═══════════════════════════════════════════════════════════════════════
# 4. Exceptions de sécurité (issue #321, point 2).
# ═══════════════════════════════════════════════════════════════════════

def test_abandon_possible_si_echiquier_perdu_meme_hors_tour(monkeypatch):
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    game, _, _ = _make_game(nl_inst=board)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game.board.turn == chess.BLACK  # pas le tour de l'utilisateur (blanc)
    game._board_lost = True
    game._sync_turn_ready()
    assert game._action_buttons_state == (True, False)
    btn_events = _events_of(events, "lichess_action_buttons")
    assert btn_events[-1] == {"resign_enabled": True, "draw_enabled": False}


def test_accepter_offre_adverse_toujours_possible_boutons_desactives(monkeypatch):
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)
    game = LichessGame(board, client, "gid321a", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game._action_buttons_state == (False, False)  # pas le tour de l'utilisateur
    game._apply_game_state({"status": "started", "moves": "e2e4", "bdraw": True})
    assert game._draw_offered_by_opponent is True
    actions.put({"type": "lichess_draw_accept"})
    game._process_browser_actions()
    assert game._draw_offered_by_opponent is False


def test_refuser_offre_adverse_toujours_possible_boutons_desactives(monkeypatch):
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)
    game = LichessGame(board, client, "gid321r", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game._action_buttons_state == (False, False)
    game._apply_game_state({"status": "started", "moves": "e2e4", "bdraw": True})
    assert game._draw_offered_by_opponent is True
    actions.put({"type": "lichess_draw_refuse"})
    game._process_browser_actions()
    assert game._draw_offered_by_opponent is False


def test_proposer_nulle_desactive_tant_quune_offre_est_en_attente(monkeypatch):
    """Ne fait pas partie des deux exceptions de sécurité de l'issue, mais
    un comportement préexistant à préserver : jamais deux offres de nulle
    de l'utilisateur en même temps."""
    events, _, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)
    game = LichessGame(board, client, "gid321p", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    assert game._action_buttons_state == (True, True)
    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True
    game._tick_physical()
    assert game._action_buttons_state == (True, False)
