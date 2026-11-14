"""
nicsoft/tests/test_issue325_lichess_single_game.py — AlChess

Issue #325 : une seule partie Lichess en cours à la fois. Couvre ce qui
n'est pas déjà couvert par test_issue323_lichess_resume.py (mis à jour pour
la nouvelle forme de get_ongoing_games()/check_lichess_resumable()) :

  - garde-fou juste avant la création d'une nouvelle partie (point 4) ;
  - abandon depuis la liste des parties en cours, avant toute reprise
    (point 3) ;
  - temps restant : seed initial depuis l'aperçu de reprise, "inconnu"
    plutôt qu'une valeur fausse quand le champ horloge manque (point 7) ;
  - abandon utilisable dès l'écran de mise en place d'une reprise,
    indépendamment du tour/position (point 5) ;
  - journal (point 8).

Entièrement sans réseau (faux transport/client, voir test_issue307/309) et
sans matériel (FakeBoard/_ScriptedBoard, voir test_issue309/311).
"""
import json

import chess
import pytest

import nicsoft.core.game_manager as gm
import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.modes.lichess.errors import LichessApiError, LichessNetworkError
from nicsoft.modes.lichess.game import LichessGame
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, FakeTransport, _make_recorder
from nicsoft.tests.test_issue311_lichess_sequencing import (
    AFTER_E2E4_W,
    INITIAL_FEN_W,
    _RecordingClient,
    _ScriptedBoard,
)
from nicsoft.tests.test_issue323_lichess_resume import _make_resuming_game


# ═══════════════════════════════════════════════════════════════════════
# 1. Garde-fou juste avant la création d'une nouvelle partie (point 4)
# ═══════════════════════════════════════════════════════════════════════

def test_refuse_create_if_games_ongoing_bloque_si_liste_non_vide(monkeypatch):
    games = [{"game_id": "existant1", "color": "white", "opponent": "bob",
              "ai_level": None, "speed": "blitz", "is_my_turn": True,
              "seconds_left": 300, "resumable": False}]
    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", lambda token: games)
    assert lichess_launcher._refuse_create_if_games_ongoing("lip_x") == games


def test_refuse_create_if_games_ongoing_laisse_demarrer_si_vide(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", lambda token: [])
    assert lichess_launcher._refuse_create_if_games_ongoing("lip_x") is None


def test_refuse_create_if_games_ongoing_laisse_demarrer_si_liste_impossible(monkeypatch):
    """Si la liste est impossible à obtenir (réseau), on laisse démarrer
    comme avant (issue #325, point 4) — _fetch_ongoing_games renvoie déjà
    None dans ce cas (voir check_lichess_resumable)."""
    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", lambda token: None)
    assert lichess_launcher._refuse_create_if_games_ongoing("lip_x") is None


def test_run_lichess_noirs_refuse_la_creation_si_partie_en_cours(monkeypatch, caplog):
    """Pour les noirs (création juste après confirmation de position, avant
    tout coup physique) : la création est refusée, aucun appel réseau de
    création n'est fait, retour à l'écran de configuration (réglages
    conservés)."""
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _RecordingClient(user_color="black", ai_first_move="e2e4")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    monkeypatch.setattr(lichess_launcher, "_refuse_create_if_games_ongoing",
                         lambda token: [{"game_id": "dejaLa1"}])

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    with caplog.at_level("INFO"):
        lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)

    assert client.created_with is None  # jamais appelé
    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_partie_en_cours_refus"
    assert _error["return_to"] == "config_lichess"
    assert "dejaLa1" in caplog.text


def test_run_lichess_blancs_refuse_la_creation_apres_le_premier_coup(monkeypatch):
    """Pour les blancs, le garde-fou arrive APRÈS le premier coup physique
    (déjà joué, irréversible) — attrape aussi une partie créée ailleurs
    entre l'ouverture de l'écran et ce premier coup (issue #325, point 4)."""
    board = _ScriptedBoard([INITIAL_FEN_W, AFTER_E2E4_W])
    client = _RecordingClient(user_color="white")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    monkeypatch.setattr(lichess_launcher, "_refuse_create_if_games_ongoing",
                         lambda token: [{"game_id": "dejaLa2"}])

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "white", "15+10", "Alain", _error)

    assert client.created_with is None
    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_partie_en_cours_refus"
    assert _error["return_to"] == "config_lichess"


def test_run_lichess_cree_normalement_si_aucune_partie_en_cours(monkeypatch):
    """Non-régression : sans partie en cours, la création continue comme
    avant (issue #311)."""
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _RecordingClient(user_color="black", ai_first_move="e2e4")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    monkeypatch.setattr(lichess_launcher, "_refuse_create_if_games_ongoing", lambda token: None)

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)

    assert client.created_with is not None
    assert _error["occurred"] is False


# ═══════════════════════════════════════════════════════════════════════
# 2. Abandon depuis la liste des parties en cours, avant toute reprise
#    (point 3) — aucune instance LichessGame n'existe encore.
# ═══════════════════════════════════════════════════════════════════════

def test_abandon_lichess_game_sans_identifiant_ignore(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda c, gid: calls.append(gid))
    with caplog.at_level("WARNING"):
        lichess_launcher.abandon_lichess_game({"game_id": ""})
    assert calls == []


def test_abandon_lichess_game_sans_jeton_toast(monkeypatch):
    events = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": ""})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    lichess_launcher.abandon_lichess_game({"game_id": "gid1"})
    assert events == [("lichess_toast", {"message_key": "toast.lichess_no_token", "type": "warning"})]


def test_abandon_lichess_game_moins_de_deux_coups_annule(monkeypatch, caplog):
    """Moins de deux coups joués dans la partie visée → annulation
    (abort()), jamais resign() — même règle que LichessGame
    ._request_resign_or_abort(), reproduite ici sans instance de partie."""
    aborted, resigned = [], []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: _AbandonClient(aborted, resigned))
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda c, gid: {
        "state": {"status": "started", "moves": "e2e4"},
    })
    refreshed = []
    monkeypatch.setattr(lichess_launcher, "check_lichess_resumable", lambda: refreshed.append(True))

    with caplog.at_level("INFO"):
        lichess_launcher.abandon_lichess_game({"game_id": "gidAbort"})

    assert aborted == ["gidAbort"]
    assert resigned == []
    assert refreshed == [True]  # la liste est rafraîchie après l'abandon
    assert "gidAbort" in caplog.text


def test_abandon_lichess_game_deux_coups_ou_plus_abandonne(monkeypatch):
    aborted, resigned = [], []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: _AbandonClient(aborted, resigned))
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda c, gid: {
        "state": {"status": "started", "moves": "e2e4 e7e5"},
    })
    monkeypatch.setattr(lichess_launcher, "check_lichess_resumable", lambda: None)

    lichess_launcher.abandon_lichess_game({"game_id": "gidResign"})

    assert aborted == []
    assert resigned == ["gidResign"]


def test_abandon_lichess_game_etat_introuvable_toast_et_pas_de_refresh(monkeypatch):
    events, refreshed = [], []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda c, gid: None)
    monkeypatch.setattr(lichess_launcher, "check_lichess_resumable", lambda: refreshed.append(True))

    lichess_launcher.abandon_lichess_game({"game_id": "gidIntrouvable"})

    assert events and events[-1][0] == "lichess_toast"
    assert refreshed == []


def test_abandon_lichess_game_refuse_par_lichess_toast(monkeypatch):
    events = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda c, gid: {
        "state": {"status": "started", "moves": "e2e4"},
    })

    class _RefusingClient:
        def abort(self, game_id):
            raise LichessApiError(400, "Not your turn")
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: _RefusingClient())

    lichess_launcher.abandon_lichess_game({"game_id": "gidRefuse"})
    assert events and events[-1][0] == "lichess_toast"


class _AbandonClient:
    def __init__(self, aborted, resigned):
        self._aborted = aborted
        self._resigned = resigned

    def abort(self, game_id):
        self._aborted.append(game_id)

    def resign(self, game_id):
        self._resigned.append(game_id)


def test_game_manager_expose_abandon_lichess_game():
    assert gm.abandon_lichess_game is lichess_launcher.abandon_lichess_game


# ═══════════════════════════════════════════════════════════════════════
# 3. Temps restant : seed réel depuis l'aperçu, "inconnu" si absent (pt. 7)
# ═══════════════════════════════════════════════════════════════════════

def test_run_lichess_resume_seed_le_temps_reel_restant(monkeypatch):
    """Le temps RESTANT (state.wtime/btime), pas la cadence de départ, sert
    de valeur initiale à LichessGame — reproduit le mécanisme corrigé de la
    « pendule 0:00 » constatée par Alain (issue #325, point 7)."""
    full_event = {
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "clock": {"initial": 900000, "increment": 0},
        "state": {"status": "started", "moves": "e2e4", "wtime": 900000, "btime": 742000},
    }
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda client, gid: full_event)
    monkeypatch.setattr(lichess_launcher, "_open_board_with_retry", lambda name: FakeBoard())

    captured = {}
    real_init = LichessGame.__init__

    def _spy_init(self, *a, **kw):
        captured.update(kw)
        real_init(self, *a, **kw)
        # Empêcher game.start() de vraiment démarrer une partie — seul le
        # seed des pendules nous intéresse ici.
        self.game_over = True

    monkeypatch.setattr(LichessGame, "__init__", _spy_init)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess_resume("lip_x", "gidClock1", "Alain", _error)

    assert captured["initial_wtime_ms"] == 900000
    assert captured["initial_btime_ms"] == 742000
    assert captured["clock_known"] is True


def test_run_lichess_resume_champ_horloge_absent_temps_inconnu(monkeypatch, caplog):
    """Partie par correspondance qui aurait échappé au filtre de la liste
    (ou toute réponse Lichess inattendue) : pas de champ `clock`, pas de
    wtime/btime → temps affiché comme inconnu plutôt qu'un 0 par défaut
    (issue #325, point 7)."""
    full_event = {
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    }
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda client, gid: full_event)
    monkeypatch.setattr(lichess_launcher, "_open_board_with_retry", lambda name: FakeBoard())

    captured = {}
    real_init = LichessGame.__init__

    def _spy_init(self, *a, **kw):
        captured.update(kw)
        real_init(self, *a, **kw)
        self.game_over = True

    monkeypatch.setattr(LichessGame, "__init__", _spy_init)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    with caplog.at_level("WARNING"):
        lichess_launcher._run_lichess_resume("lip_x", "gidClock2", "Alain", _error)

    assert captured["initial_wtime_ms"] is None
    assert captured["initial_btime_ms"] is None
    assert captured["clock_known"] is False
    assert "gidClock2" in caplog.text


def test_lichessgame_clock_known_false_seed_puis_corrige_par_le_flux(monkeypatch):
    """LichessGame elle-même : clock_known=False au départ → lichess_clock
    porte known=False (jamais un 0:00 affiché comme réel) ; dès qu'un vrai
    état avec wtime/btime arrive par le flux, known repasse à True."""
    events, _, _ = _make_recorder(monkeypatch)
    board = FakeBoard()
    transport = FakeTransport()
    client = GameClient("lip_test", transport=transport)
    game = LichessGame(
        board, client, "gid1", level=1, player_name="Alain",
        clock_limit_s=0, clock_increment_s=0, chosen_color_setting="white",
        clock_known=False,
    )
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    # Pas de wtime/btime dans cet état → _reset_clock_from_state() revient
    # sans rien pousser (voir game.py) : known reste donc False tel que seedé.
    assert game._clock_known is False
    game._maybe_push_clock(force=True)
    clock_events = [d for (t, d) in events if t == "lichess_clock"]
    assert clock_events and clock_events[-1]["known"] is False

    # Un vrai état (wtime/btime) arrive ensuite — known devient True.
    game._apply_game_state({"status": "started", "moves": "e2e4", "wtime": 900000, "btime": 900000})
    clock_events = [d for (t, d) in events if t == "lichess_clock"]
    assert clock_events[-1]["known"] is True
    assert clock_events[-1]["white_ms"] == 900000


def test_lichessgame_clock_known_true_par_defaut():
    """Une partie lancée normalement (pas une reprise) a toujours un
    clock_limit_s réel (> 0, choisi par l'utilisateur) — jamais affichée
    comme « inconnue » (non-régression du point 7)."""
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    game = LichessGame(
        board, client, "gid1", level=1, player_name="Alain",
        clock_limit_s=900, clock_increment_s=10, chosen_color_setting="white",
    )
    assert game._clock_known is True
    assert game._clock_white_ms == 900000
    assert game._clock_black_ms == 900000


# ═══════════════════════════════════════════════════════════════════════
# 4. Abandon dès l'écran de mise en place d'une reprise (point 5)
# ═══════════════════════════════════════════════════════════════════════

def test_lichess_resign_pendant_resume_pending_fonctionne(monkeypatch):
    """Depuis l'écran de mise en place (_resume_pending=True), l'action
    "lichess_resign" aboutit normalement — abandon/annulation réel, sans
    attendre la reconstruction de la position (issue #325, point 5)."""
    aborted = []
    game, board, events = _make_resuming_game(monkeypatch, moves="e2e4")
    monkeypatch.setattr(game.client, "abort", lambda gid: aborted.append(gid))
    monkeypatch.setattr(game.client, "resign", lambda gid: pytest.fail("resign() appelé — moins de 2 coups attendu"))

    actions = iter([{"type": "lichess_resign"}, None])
    monkeypatch.setattr("nicsoft.modes.lichess.game.get_action", lambda timeout=0.0: next(actions))

    assert game._resume_pending is True
    game._process_browser_actions()

    assert aborted == ["gid1"]
    assert game.game_over is True


def test_action_buttons_pendant_resume_pending_puis_normal(monkeypatch):
    """(resign_enabled, draw_enabled) pendant la mise en place : (True,
    False) quel que soit le tour — puis bascule sur la logique normale une
    fois la position reconstruite."""
    game, board, events = _make_resuming_game(monkeypatch, moves="e2e4", user_color_is_black=False)
    # Tour de l'adversaire (noir) ici — resign quand même actif pendant la
    # mise en place (contrairement à la logique normale hors reprise, qui
    # exigerait le trait de l'utilisateur).
    assert game.board.turn == chess.BLACK
    assert game._compute_action_buttons() == (True, False)

    board.current_fen = game.board.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert game._resume_pending is False
    # Position confirmée, mais c'est le tour de l'adversaire : les deux
    # boutons repassent par la logique normale (inactifs tant que ce n'est
    # pas le tour de l'utilisateur).
    assert game._compute_action_buttons() == (False, False)


# ═══════════════════════════════════════════════════════════════════════
# 5. Journal (point 8) — lignes INFO, rien de secret
# ═══════════════════════════════════════════════════════════════════════

def test_check_lichess_resumable_journal_nombre_et_identifiants(monkeypatch, caplog):
    events = []
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_secret_xyz"})
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))
    games = [
        {"game_id": "logid001", "color": "white", "opponent": "bob", "ai_level": None,
         "speed": "blitz", "is_my_turn": True, "seconds_left": 300, "resumable": False},
        {"game_id": "logid002", "color": "black", "opponent": "Stockfish level 2", "ai_level": 2,
         "speed": "rapid", "is_my_turn": False, "seconds_left": 900, "resumable": True},
    ]
    import nicsoft.modes.lichess.client as client_mod
    monkeypatch.setattr(client_mod, "get_ongoing_games",
                         lambda token: {"status": "ok", "games": games, "total": 2})
    with caplog.at_level("INFO"):
        lichess_launcher.check_lichess_resumable()
    assert "2" in caplog.text
    assert "logid001" in caplog.text and "logid002" in caplog.text
    assert "lip_secret_xyz" not in caplog.text


def test_refus_creation_journal_identifiants_sans_secret(monkeypatch, caplog):
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _RecordingClient(user_color="black", ai_first_move="e2e4")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    monkeypatch.setattr(lichess_launcher, "_refuse_create_if_games_ongoing",
                         lambda token: [{"game_id": "refusLog1"}])

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    with caplog.at_level("INFO"):
        lichess_launcher._run_lichess("lip_secret_abc123", 1, 900, 10, "black", "15+10", "Alain", _error)

    assert "refusLog1" in caplog.text
    assert "lip_secret_abc123" not in caplog.text
