"""
nicsoft/tests/test_issue311_lichess_sequencing.py — AlChess

Issue #311 : nouvel ordre de lancement du mode Lichess (plus de pression de
temps avant le premier coup), compte à rebours du premier coup (noirs),
fin de partie jamais silencieuse, message d'attente de réponse à une
proposition de nulle, journal visible par défaut.

Entièrement sans réseau (faux transport/client, voir test_issue309) et sans
matériel (faux plateau exposant get_fen(), comme nl_inst.get_fen() réel).
"""
import logging
import queue

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.game import LichessGame, first_move_deadline_s
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport, _make_recorder, _ok


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ── Double de plateau exposant get_fen() (utilisé par les attentes du lanceur) ─

class _ScriptedBoard:
    """Simule nl_inst : une liste de FEN (ou d'exceptions) consommée dans
    l'ordre par get_fen(), le dernier élément étant répété indéfiniment une
    fois la liste épuisée — pas de limite de temps à simuler, le test avance
    seul par consommation d'appels, jamais par un vrai délai."""

    def __init__(self, fen_sequence):
        self._sequence = list(fen_sequence)
        self._idx = 0
        self.led_calls = []
        self.leds_off_count = 0
        self.beeped = 0
        self.disconnected = False

    def get_fen(self):
        if self._idx < len(self._sequence):
            item = self._sequence[self._idx]
            self._idx += 1
        else:
            item = self._sequence[-1]
        if isinstance(item, Exception):
            raise item
        return item

    def set_led(self, square, status):
        self.led_calls.append((square, status))

    def turn_off_all_leds(self):
        self.leds_off_count += 1

    def signal_lights(self, sig):
        pass

    def beep(self):
        self.beeped += 1

    def disconnect(self):
        self.disconnected = True


INITIAL_FEN_W = chess.STARTING_BOARD_FEN + " w - - 0 1"
_E2E4 = chess.Board()
_E2E4.push_uci("e2e4")
AFTER_E2E4_W = _E2E4.board_fen() + " w - - 0 1"


class _RecordingClient:
    """Double de GameClient — capture les paramètres de create_ai_game() et
    de play_move(), jamais de réseau (aucun transport sous-jacent).
    `user_color` pilote le gameFull simulé par stream_game() (déduit du
    coup effectivement envoyé par play_move() pour les blancs, fourni
    directement pour les noirs puisque l'IA joue avant tout envoi)."""

    def __init__(self, game_id="gid311", user_color="white", ai_first_move=""):
        self.created_with = None
        self.moves_sent = []
        self.game_id = game_id
        self.user_color = user_color
        self.ai_first_move = ai_first_move

    def create_ai_game(self, **kwargs):
        self.created_with = dict(kwargs)
        return {"id": self.game_id}

    def play_move(self, game_id, uci, offer_draw=False):
        self.moves_sent.append(uci)

    def stream_game(self, game_id, sleep=None):
        # Un seul événement, aussitôt consommé par LichessGame._main_loop
        # puis fin de partie — suffisant pour exercer tout le chemin du
        # lanceur sans dépendre du minutage d'un vrai thread de flux.
        moves = " ".join(self.moves_sent) if self.user_color == "white" else self.ai_first_move
        user_side = {"id": "alain"}
        ai_side = {"aiLevel": 1}
        white_side, black_side = (user_side, ai_side) if self.user_color == "white" else (ai_side, user_side)
        yield {
            "type": "gameFull", "white": white_side, "black": black_side,
            "state": {"status": "aborted", "winner": "", "moves": moves},
        }


# ── 6a. Création après confirmation de position + premier coup (blancs) ──────

def test_blancs_partie_creee_seulement_apres_le_premier_coup_physique(monkeypatch):
    """Même après un long délai (ici simulé par de nombreuses lectures de
    position initiale avant le premier coup), create_ai_game() n'est jamais
    appelé tant que l'utilisateur n'a pas joué physiquement — aucune partie
    n'existe, donc aucune pression de temps (issue #311, point 1)."""
    board = _ScriptedBoard([INITIAL_FEN_W] * 50 + [AFTER_E2E4_W])
    client = _RecordingClient()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "white", "15+10", "Alain", _error)

    assert client.created_with is not None
    assert client.created_with["color"] == "white"
    assert client.moves_sent == ["e2e4"]
    assert _error["occurred"] is False


def test_noirs_partie_creee_immediatement_apres_la_position(monkeypatch):
    """Pour les noirs, la partie est créée dès la position confirmée, sans
    attendre un coup physique (l'IA joue aussitôt)."""
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _RecordingClient(user_color="black", ai_first_move="e2e4")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)

    assert client.created_with is not None
    assert client.created_with["color"] == "black"
    assert client.moves_sent == []  # rien à envoyer : c'est l'IA (blancs) qui a joué


@pytest.mark.parametrize("force_choice,expected", [("white", "white"), ("black", "black")])
def test_couleur_aleatoire_resolue_localement_avant_create_ai_game(monkeypatch, force_choice, expected):
    """chosen_color="random" : la couleur est tirée côté AlChess (jamais
    "random" ni "" envoyé à Lichess) — issue #311, point 1 et 6a."""
    monkeypatch.setattr(lichess_launcher.random, "choice", lambda seq: force_choice)
    if expected == "white":
        board = _ScriptedBoard([INITIAL_FEN_W, AFTER_E2E4_W])
        client = _RecordingClient(user_color="white")
    else:
        board = _ScriptedBoard([INITIAL_FEN_W])
        client = _RecordingClient(user_color="black", ai_first_move="e2e4")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "random", "15+10", "Alain", _error)

    assert client.created_with["color"] == expected


def test_echec_de_creation_apres_premier_coup_blancs_revient_a_config_lichess(monkeypatch):
    """Si create_ai_game() échoue après que l'utilisateur a déjà joué son
    premier coup physique (blancs), le retour se fait vers l'écran de
    configuration Lichess (réglages conservés), pas vers le menu générique
    (issue #311, point 1)."""
    from nicsoft.modes.lichess.errors import LichessNetworkError

    board = _ScriptedBoard([INITIAL_FEN_W, AFTER_E2E4_W])

    class _FailingClient:
        def create_ai_game(self, **kwargs):
            raise LichessNetworkError("injoignable")

    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: _FailingClient())
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "white", "15+10", "Alain", _error)

    assert _error["occurred"] is True
    assert _error["return_to"] == "config_lichess"


# ── 6c. Deux parties enchaînées, la seconde avec un échiquier mal rangé ───────

def test_deux_parties_enchainees_seconde_echiquier_mal_range(monkeypatch):
    """La seconde partie (noirs, plus simple à enchaîner) démarre avec un
    échiquier mal rangé : l'attente de position fonctionne encore
    normalement (pas de régression par le passage à une attente sans
    limite de temps) puis la partie se crée une fois la position correcte."""
    mauvaise_position = "8/8/8/8/8/8/8/8 w - - 0 1"

    def _run_once(board):
        client = _RecordingClient(user_color="black")
        monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
        monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
        monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
        monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
        _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
        lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)
        return client, _error

    board1 = _ScriptedBoard([INITIAL_FEN_W])
    client1, error1 = _run_once(board1)
    assert error1["occurred"] is False
    assert client1.created_with["color"] == "black"
    assert board1.disconnected is True  # l'échiquier du premier plateau est libéré avant le second

    board2 = _ScriptedBoard([mauvaise_position] * 10 + [INITIAL_FEN_W])
    client2, error2 = _run_once(board2)
    assert error2["occurred"] is False
    assert client2.created_with["color"] == "black"


# ── 6b. Jamais de fin silencieuse ─────────────────────────────────────────────

def _make_bare_game(monkeypatch, nl_inst=None, transport=None):
    events, states, actions = _make_recorder(monkeypatch)
    client = GameClient("lip_test", transport=transport or FakeTransport())
    game = LichessGame(nl_inst or _ScriptedBoard([INITIAL_FEN_W]), client, "gid311",
                        level=2, player_name="Alain", clock_limit_s=900, clock_increment_s=10,
                        chosen_color_setting="random", cadence_key="15+10")
    return game, events, states, actions


@pytest.mark.parametrize("status,expected_key", [
    ("aborted", "lichess.annulee_premier_coup_trop_tard"),
    ("noStart", "lichess.annulee_cause_inconnue"),
    ("unknownFinish", "lichess.annulee_cause_inconnue"),
])
def test_statut_inattendu_non_demande_produit_message_explicite(monkeypatch, status, expected_key):
    """Un flux qui annonce un statut d'annulation inattendu (pas demandé
    par l'utilisateur) produit l'événement lichess_aborted avec le bon
    message, et ne déclenche jamais l'écran d'analyse normal en silence
    (skip=True, set_app_state("game_over", ...) jamais appelé)."""
    game, events, states, _ = _make_bare_game(monkeypatch)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},
    })
    game._status = status
    game._winner = ""
    game._aborted = status == "aborted"
    game._finalize()

    aborted_events = [d for t, d in events if t == "lichess_aborted"]
    assert aborted_events, "lichess_aborted jamais émis — fin de partie silencieuse"
    assert aborted_events[0]["message_key"] == expected_key
    assert aborted_events[0]["replay_settings"]["color"] == "random"
    assert aborted_events[0]["replay_settings"]["cadence"] == "15+10"
    game_over_events = [d for t, d in events if t == "game_over"]
    assert game_over_events and game_over_events[-1]["skip"] is True
    game_over_states = [d for s, d in states if s == "game_over"]
    assert game_over_states == []  # jamais affiché comme un game_over normal


def test_annulation_demandee_par_l_utilisateur_garde_son_comportement(monkeypatch):
    """Un abandon/annulation demandé par l'utilisateur (bouton Abandonner)
    garde le comportement existant — pas de lichess_aborted, écran d'analyse
    normal affiché (issue #311, point 3 : "garde son message actuel")."""
    game, events, states, actions = _make_bare_game(
        monkeypatch, transport=FakeTransport(requests=[_ok({"ok": True})]))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},
    })
    actions.put({"type": "lichess_resign"})
    game._process_browser_actions()
    assert game.game_over is True
    assert game._aborted is True
    game._finalize()

    assert [d for t, d in events if t == "lichess_aborted"] == []
    game_over_events = [d for t, d in events if t == "game_over"]
    assert game_over_events and game_over_events[-1]["skip"] is False
    assert [d for s, d in states if s == "game_over"]


def test_retour_menu_pendant_la_partie_garde_son_comportement(monkeypatch):
    """Un retour menu explicite pendant la partie reste silencieux côté
    écran d'analyse (skip=True, comportement déjà existant) mais ne doit
    pas non plus déclencher la fenêtre d'annulation Lichess (ce n'est pas
    une annulation Lichess)."""
    game, events, states, actions = _make_bare_game(
        monkeypatch, transport=FakeTransport(requests=[_ok({"ok": True})]))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},
    })
    actions.put({"type": "back_menu"})
    game._process_browser_actions()
    assert game._back_menu_requested is True
    game._status = "aborted"
    game._aborted = True
    game._finalize()
    assert [d for t, d in events if t == "lichess_aborted"] == []


# ── 6d. Compte à rebours du premier coup (noirs) ──────────────────────────────

def test_first_move_deadline_s_pure():
    assert first_move_deadline_s(None, 0.0) is None
    assert first_move_deadline_s({}, 0.0) is None
    assert first_move_deadline_s({"millisToMove": 20000}, 5.0) == 15.0
    assert first_move_deadline_s({"millisToMove": 2000}, 5.0) == 0.0  # jamais négatif


def test_decompte_premier_coup_apparait_avec_expiration(monkeypatch):
    game, events, _, _ = _make_bare_game(monkeypatch)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4", "expiration": {"idleMillis": 15000, "millisToMove": 20000}},
    })
    deadline_events = [d for t, d in events if t == "lichess_first_move_deadline"]
    assert deadline_events and deadline_events[-1]["active"] is True
    assert deadline_events[-1]["seconds"] == 20.0


def test_decompte_premier_coup_sans_champ_expiration_contre_ia_reste_informatif(monkeypatch):
    """Depuis l'issue #322 (point 1) : contre l'IA de Lichess, en l'absence
    du champ `expiration`, aucune estimation locale n'est faite (Lichess ne
    menace jamais d'annulation ni n'affiche de décompte dans ce cas précis
    — confirmé par l'essai réel d'Alain du 13/11/2026, partie non annulée
    après plus de 28s). Avant l'issue #321 (point 6) ce cas produisait déjà
    `seconds=None` ; l'issue #321 avait introduit à tort une estimation
    locale même contre l'IA, corrigée ici."""
    game, events, _, _ = _make_bare_game(monkeypatch)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    deadline_events = [d for t, d in events if t == "lichess_first_move_deadline"]
    assert deadline_events and deadline_events[-1]["active"] is True
    assert deadline_events[-1]["seconds"] is None
    assert deadline_events[-1]["estimated"] is False


def test_decompte_premier_coup_sans_champ_expiration_contre_humain_estime(monkeypatch):
    """Depuis l'issue #321 (point 6), restreint à une partie contre un
    humain par l'issue #322 (point 1) : en l'absence du champ `expiration`
    ET d'adversaire IA, le décompte utilise une estimation locale déduite
    de la cadence (ici 900s+10 => "rapid" => 30s, voir
    _FIRST_MOVE_TIMEOUT_BY_SPEED dans nicsoft/modes/lichess/game.py, vérifié
    contre lila/scalachess master).

    Aucun mode "contre un humain" n'existe encore côté lanceur AlChess
    (voir CLAUDE.md) — `_apply_game_full()` déduit aujourd'hui la couleur de
    l'utilisateur de la seule présence d'`aiLevel`, ce qui ne permet pas de
    produire `user_color == "black"` avec un adversaire non-IA. Ce test
    positionne donc directement `_opponent_is_ai`/`user_color`/
    `_moves_applied` avant d'appeler `_maybe_activate_first_move_deadline()`,
    pour vérifier que la logique de décompte elle-même est prête pour ce
    mode futur, indépendamment de ce futur lanceur."""
    game, events, _, _ = _make_bare_game(monkeypatch)
    game._opponent_is_ai = False
    game.user_color = "black"
    game._moves_applied = 1
    game._maybe_activate_first_move_deadline({"status": "started", "moves": "e2e4"})
    deadline_events = [d for t, d in events if t == "lichess_first_move_deadline"]
    assert deadline_events and deadline_events[-1]["active"] is True
    assert deadline_events[-1]["seconds"] == 30.0
    assert deadline_events[-1]["estimated"] is True


def test_decompte_premier_coup_disparait_apres_le_coup_utilisateur(monkeypatch):
    game, events, _, _ = _make_bare_game(monkeypatch)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4", "expiration": {"millisToMove": 20000}},
    })
    assert game._first_move_deadline_active is True
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})
    assert game._first_move_deadline_active is False
    deadline_events = [d for t, d in events if t == "lichess_first_move_deadline"]
    assert deadline_events[-1] == {"active": False}


def test_signal_sonore_premier_coup_ia_pour_les_noirs(monkeypatch):
    board = _ScriptedBoard([INITIAL_FEN_W])
    game, _, _, _ = _make_bare_game(monkeypatch, nl_inst=board)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert board.beeped == 1


# ── 6e. Pendules figées avant les premiers coups des deux camps (#322) ───────
# Issue #322, point 2 : sur lichess.org, aucune pendule ne décompte avant que
# chaque camp ait joué son propre premier coup (le champ `expiration` gère ce
# premier coup à part, hors de wtime/btime) — jamais un minuteur local qui
# parte de lui-même dès qu'un camp a le trait.

def test_pendule_noire_figee_juste_apres_le_premier_coup_blanc(monkeypatch, caplog):
    """Utilisateur aux noirs : l'IA (blancs) a joué son premier coup, c'est
    au tour des noirs (utilisateur) — scénario réel d'Alain du 13/11/2026.
    Avant le propre premier coup des noirs, la pendule ne doit pas décompter
    même si du temps réel s'écoule."""
    game, events, _, _ = _make_bare_game(monkeypatch)
    with caplog.at_level("INFO", logger="niclink.lichess"):
        game._apply_game_full({
            "white": {"aiLevel": 1}, "black": {"id": "alain"},
            "state": {"status": "started", "moves": "e2e4", "wtime": 900000, "btime": 900000},
        })
    assert game._clock_running is False
    assert game._clock_turn == "black"
    assert "pendules commencent à décompter" not in caplog.text
    game._clock_ref_monotonic -= 5.0  # 5s d'horloge réelle, simulées sans nouvel événement Lichess
    game._maybe_push_clock(force=True)
    clock_events = [d for t, d in events if t == "lichess_clock"]
    assert clock_events[-1]["black_ms"] == 900000.0
    assert clock_events[-1]["white_ms"] == 900000.0


def test_pendule_blanche_figee_avant_le_tout_premier_coup(monkeypatch):
    """Utilisateur aux blancs (aucun `aiLevel` côté blancs) : avant même le
    tout premier coup de la partie, la pendule blanche ne doit pas
    décompter non plus (les deux couleurs sont concernées)."""
    game, events, _, _ = _make_bare_game(monkeypatch)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "", "wtime": 900000, "btime": 900000},
    })
    assert game._clock_running is False
    assert game._clock_turn == "white"
    game._clock_ref_monotonic -= 5.0
    game._maybe_push_clock(force=True)
    clock_events = [d for t, d in events if t == "lichess_clock"]
    assert clock_events[-1]["white_ms"] == 900000.0


def test_pendules_decomptent_normalement_apres_les_deux_premiers_coups(monkeypatch, caplog):
    """Une fois que chaque camp a joué son propre premier coup, la pendule
    du camp au trait décompte normalement (log explicite du moment où elles
    démarrent — issue #322, point 3)."""
    game, events, _, _ = _make_bare_game(monkeypatch)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4", "wtime": 900000, "btime": 900000},
    })
    assert game._clock_running is False
    with caplog.at_level("INFO", logger="niclink.lichess"):
        game._apply_game_state({
            "status": "started", "moves": "e2e4 e7e5", "wtime": 900000, "btime": 900000,
        })
    assert game._clock_running is True
    assert game._clock_turn == "white"  # 2e coup des blancs, désormais décompté
    assert "pendules commencent à décompter" in caplog.text
    game._clock_ref_monotonic -= 5.0
    game._maybe_push_clock(force=True)
    clock_events = [d for t, d in events if t == "lichess_clock"]
    assert clock_events[-1]["white_ms"] == pytest.approx(895000.0, abs=50.0)
    assert clock_events[-1]["black_ms"] == 900000.0


def test_pas_de_signal_sonore_pour_les_blancs(monkeypatch):
    board = _ScriptedBoard([INITIAL_FEN_W])
    game, _, _, _ = _make_bare_game(monkeypatch, nl_inst=board)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    assert board.beeped == 0


# ── Nulle : refus même pendant le tour de l'utilisateur ───────────────────────

def test_nulle_refusee_meme_proposee_pendant_le_tour_de_l_utilisateur(monkeypatch):
    """Comme test_issue310 mais l'offre est faite alors que c'est au tour de
    l'utilisateur de jouer (pas celui de l'adversaire) — le refus doit être
    détecté de la même façon dès que l'adversaire joue sans accepter."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},  # c'est le tour des blancs (l'utilisateur)
    })
    assert game.user_color == "white"
    assert game.board.turn == chess.WHITE

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True

    # L'utilisateur joue son propre coup, puis l'adversaire répond sans accepter.
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": True, "bdraw": False})
    assert game._my_draw_offer_pending is True  # toujours en attente après notre propre coup
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_refused", {}) in events


# ── Journal visible par défaut, sans mode DEBUG (issue #311, point 5) ────────

def test_lignes_lichess_journalisees_en_info_sans_activer_debug(monkeypatch, caplog):
    """Les lignes d'information du mode Lichess utilisent le logger
    "niclink.lichess" — il suffit de lui donner le niveau INFO (fait une
    fois au démarrage par nicsoft.web.alchess._setup_logging, jamais par
    NICLINK_LOG=DEBUG) pour qu'elles soient capturées, contrairement aux
    lignes d'un logger générique resté à son niveau par défaut."""
    logging.getLogger("niclink.lichess").setLevel(logging.INFO)
    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        game, _, _, _ = _make_bare_game(monkeypatch)
        game._apply_game_full({
            "white": {"id": "alain"}, "black": {"aiLevel": 1},
            "state": {"status": "started", "moves": ""},
        })
        game.client.play_move = lambda *a, **kw: None
        game._submit_move("e2e4")
        game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})

    messages = [r.message for r in caplog.records if r.name == "niclink.lichess"]
    assert any("coup envoyé e2e4" in m and "délai" in m and "ms" in m for m in messages)
    assert any("coup reçu e7e5" in m and "délai" in m and "ms" in m for m in messages)


def test_jeton_jamais_dans_les_lignes_de_journal(monkeypatch, caplog):
    """Garde-fou direct : même en journalisant tout le mode Lichess, le
    jeton ne doit jamais apparaître dans un message de journal."""
    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        game, _, _, _ = _make_bare_game(monkeypatch)
        game.client = GameClient("lip_SECRET_TOKEN_VALUE", transport=FakeTransport(requests=[_ok({"ok": True})]))
        game._apply_game_full({
            "white": {"id": "alain"}, "black": {"aiLevel": 1},
            "state": {"status": "started", "moves": ""},
        })
        game._submit_move("e2e4")
    for record in caplog.records:
        assert "lip_SECRET_TOKEN_VALUE" not in record.message
