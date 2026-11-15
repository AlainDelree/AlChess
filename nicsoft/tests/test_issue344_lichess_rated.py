"""
nicsoft/tests/test_issue344_lichess_rated.py — AlChess

Issue #344 (étape L4) : parties Lichess classées contre un humain, humain
présélectionné sur l'écran de configuration, signal de début de partie
distinct, affichage classée/amicale (+ variation de cote en meilleur
effort), journal enrichi, et cas rares passés en revue avec `rated=True`.

Entièrement hors ligne (faux transport Lichess scripté, faux plateau USB) —
voir nicsoft/tests/conftest.py::_guard_no_real_lichess_network pour le test
de garde explicite. Les défauts d'affichage de l'écran de configuration
(bouton présélectionné, case cochée/masquée) sont couverts côté navigateur
par test_issue344_lichess_rated_e2e.py — ce fichier couvre le serveur.
"""
import sys
import time

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.game import LichessGame, _GAME_START_SIG_NUM
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.game_log import GameLog
from nicsoft.modes.lichess.seek import SeekSession
from nicsoft.tests.test_issue309_lichess_l2a import FakeStreamHandle, _make_recorder
from nicsoft.tests.test_issue309_lichess_l2a import _make_game as _make_bare_game309
from nicsoft.tests.test_issue327_lichess_human import _FakeHandleForClient, _gamestart_line, _HumanGameClient
from nicsoft.tests.test_issue331_lichess_opponent_alerts import (
    _AlertBoard, _make_game, _started, isolated_config,
)
from nicsoft.tests.test_issue311_lichess_sequencing import INITIAL_FEN_W, _ScriptedBoard


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


class _SignalRecordingBoard(_AlertBoard):
    """Comme _AlertBoard, mais enregistre aussi les appels à
    signal_lights() (jamais fait par _AlertBoard elle-même) — nécessaire
    pour vérifier le signal de début de partie (issue #344, point 3bis)."""

    def __init__(self):
        super().__init__()
        self.signal_calls = []

    def signal_lights(self, sig_num, stop=None):
        self.signal_calls.append(sig_num)


class _RatedCapturingHumanGameClient(_HumanGameClient):
    """Enregistre les arguments reçus par open_seek_stream (issue #344,
    point 2) — _HumanGameClient se contente de les ignorer (*a, **kw)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seek_calls = []

    def open_seek_stream(self, *a, **kw):
        self.seek_calls.append((a, kw))
        return _FakeHandleForClient([""])


# ═══════════════════════════════════════════════════════════════════════
# 1. Recherche humaine — `rated` transmis à board/seek (point 2).
# ═══════════════════════════════════════════════════════════════════════

def test_recherche_classee_transmet_rated_true_a_open_seek_stream(monkeypatch):
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _RatedCapturingHumanGameClient()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human(
        "lip_x", 900, 10, "white", "15+10", "Alain", _error, rated=True,
    )
    assert _error["occurred"] is False
    assert client.seek_calls, "open_seek_stream jamais appelé"
    args, kwargs = client.seek_calls[0]
    assert (True in args) or (kwargs.get("rated") is True), (
        f"rated=True non transmis à open_seek_stream (args={args}, kwargs={kwargs})"
    )


def test_recherche_amicale_transmet_rated_false_par_defaut(monkeypatch):
    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _RatedCapturingHumanGameClient()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    # rated omis — défaut prudent (jamais une partie classée involontaire).
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)
    args, kwargs = client.seek_calls[0]
    assert (True not in args) and (kwargs.get("rated") is not True)


def test_launch_lichess_lit_le_champ_rated_de_la_config(monkeypatch):
    """launch_lichess() (le vrai point d'entrée depuis server.py) lit bien
    config["rated"] et l'achemine jusqu'à _run_lichess_human — pas
    seulement _run_lichess_human() appelé directement comme ci-dessus."""
    captured = {}

    def _fake_run(token, clock_limit_s, clock_increment_s, chosen_color, cadence_key,
                   player_name, _error=None, rated=False):
        captured["rated"] = rated
        if _error is not None:
            _error["occurred"] = True  # évite toute suite (écran, réseau...)

    monkeypatch.setattr(lichess_launcher, "_run_lichess_human", _fake_run)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "config_lichess", raising=False)
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda *a, **kw: None)

    lichess_launcher.launch_lichess({
        "opponent_type": "human", "cadence": "15+10", "color": "white",
        "player": "Alain", "rated": True,
    })
    assert captured["rated"] is True


def test_seek_session_start_transmet_rated_a_open_seek_stream():
    class _CapturingClient(GameClient):
        pass

    class _CapturingTransport:
        def __init__(self):
            self.seek_fields = None

        def open_stream(self, method, url, token, fields=None):
            if url.endswith("/stream/event"):
                return FakeStreamHandle([""] * 3)
            self.seek_fields = fields
            return FakeStreamHandle([""] * 3)

    transport = _CapturingTransport()
    client = GameClient("lip_test", transport=transport)
    session = SeekSession(client)
    session.start(15.0, 10, "", rated=True)
    assert transport.seek_fields["rated"] == "true"


# ═══════════════════════════════════════════════════════════════════════
# 2. `game.rated` toujours lu depuis le gameFull confirmé par Lichess —
#    jamais deviné (point 3).
# ═══════════════════════════════════════════════════════════════════════

def test_apply_game_full_lit_rated_depuis_gamefull_vrai(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Bob", "rating": 1700},
        "rated": True,
        "state": {"status": "started", "moves": ""},
    })
    assert game.rated is True
    init_payload = [d for t, d in events if t == "lichess_init"][-1]
    assert init_payload["rated"] is True


def test_apply_game_full_rated_absent_vaut_false():
    game, client, _ = _make_bare_game309()
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    assert game.rated is False


def test_partie_contre_ia_jamais_classee(monkeypatch):
    """Même si (par erreur) `rated: true` apparaissait un jour dans un
    gameFull contre l'IA, ce n'est pas testé ici (Lichess ne l'envoie
    jamais pour l'IA, voir /api/challenge/ai) — ce test vérifie plutôt que
    le lanceur IA n'a tout simplement aucun moyen d'envoyer `rated`."""
    import inspect
    sig = inspect.signature(lichess_launcher.launch_lichess)
    src = inspect.getsource(lichess_launcher.launch_lichess)
    # La branche IA (après le `if ... == "human": return`) ne mentionne
    # jamais "rated" — seule create_ai_game (sans ce paramètre) est utilisée.
    ai_branch = src.split('_launch_lichess_human(config, token)\n        return\n', 1)[-1]
    assert "rated" not in ai_branch


def test_game_over_payload_contient_rated_true(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game.rated = True
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["rated"] is True


def test_game_over_payload_contient_rated_false_pour_partie_amicale(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["rated"] is False


# ═══════════════════════════════════════════════════════════════════════
# 3. Signal de début de partie (point 3bis) — bip + LED distincts
#    (sig_num 7), une seule fois, jamais à une reprise ni à une
#    reconnexion, pour toute partie (IA/humain, classée/amicale).
# ═══════════════════════════════════════════════════════════════════════

def test_signal_debut_partie_blancs(monkeypatch):
    board = _SignalRecordingBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp"},
        "state": {"status": "started", "moves": ""},
    })
    assert board.signal_calls == [_GAME_START_SIG_NUM]
    assert board.beep_count == 1
    assert game._game_start_signal_sent is True


def test_signal_debut_partie_noirs_avant_affichage_du_premier_coup(monkeypatch):
    """Pour les noirs, le signal doit être posté AVANT l'affichage normal du
    premier coup adverse (voir le commentaire de _GAME_START_SIG_NUM) — ici
    vérifié indirectement : le signal est bien émis, et le bip du premier
    coup IA (préexistant, #311) s'ajoute au sien (2 bips au total)."""
    board = _SignalRecordingBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    game._apply_game_full({
        "white": {"aiLevel": 1}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game.user_color == "black"
    assert board.signal_calls == [_GAME_START_SIG_NUM]
    assert board.beep_count == 2  # 1 (début de partie) + 1 (premier coup IA, #311)


def test_signal_absent_a_la_reprise(monkeypatch):
    board = _SignalRecordingBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board, resuming=True)
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp"},
        "state": {"status": "started", "moves": "e2e4 e7e5"},
    })
    assert board.signal_calls == []
    assert board.beep_count == 0
    assert game._game_start_signal_sent is False


def test_signal_pas_repete_sur_un_second_gamefull_reconnexion(monkeypatch):
    """Une reconnexion réseau mi-partie peut faire revenir un nouveau
    gameFull complet (voir game_client.py, docstring de stream_game) — le
    signal ne doit jamais être posté deux fois pour la même partie."""
    board = _SignalRecordingBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    game._known_user_color = "white"
    full = {
        "white": {"id": "alain"}, "black": {"id": "opp"},
        "state": {"status": "started", "moves": ""},
    }
    game._apply_game_full(full)
    game._apply_game_full(full)
    assert board.signal_calls == [_GAME_START_SIG_NUM]


def test_signal_emis_pour_partie_classee_comme_amicale(monkeypatch):
    for rated in (True, False):
        board = _SignalRecordingBoard()
        game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
        game._known_user_color = "white"
        game._apply_game_full({
            "white": {"id": "alain"}, "black": {"id": "opp"}, "rated": rated,
            "state": {"status": "started", "moves": ""},
        })
        assert board.signal_calls == [_GAME_START_SIG_NUM]


# ═══════════════════════════════════════════════════════════════════════
# 4. Nouvelle cote en fin de partie classée (point 3) — meilleur effort,
#    jamais inventée si absente. La lecture elle-même (GameClient.
#    fetch_my_rating, lecture publique /api/user/<id>) et son orchestration
#    (LichessGame._maybe_fetch_new_rating, court délai + une seule
#    nouvelle tentative) ont été entièrement REMPLACÉES par l'issue #349,
#    partie 1, point 3 — voir son rapport de clôture pour la discussion
#    garder/remplacer/compléter, et
#    nicsoft/tests/test_issue349_lichess_rating_cadence.py pour la
#    couverture détaillée de la nouvelle implémentation. Ce qui reste ici
#    ne couvre plus que le déclenchement depuis _finalize() (classée vs
#    amicale), avec la cote de départ connue (voir _apply_game_full).
# ═══════════════════════════════════════════════════════════════════════

def test_finalize_classee_terminee_declenche_fetch_et_pousse_l_evenement(monkeypatch):
    from nicsoft.modes.lichess.game import LichessGame
    monkeypatch.setattr(LichessGame, "_NEW_RATING_INITIAL_DELAY_S", 0.01)
    monkeypatch.setattr(LichessGame, "_NEW_RATING_RETRY_DELAY_S", 0.01)
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain", "rating": 1400}, "black": {"id": "opp"}, "rated": True,
        "state": {"status": "started", "moves": ""},
    })
    monkeypatch.setattr(client, "fetch_my_rating", lambda username, speed_key: 1412)
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()

    for _ in range(100):
        if any(t == "lichess_new_rating" for t, _ in events):
            break
        time.sleep(0.02)
    new_rating_events = [d for t, d in events if t == "lichess_new_rating"]
    assert new_rating_events and new_rating_events[-1] == {"new_rating": 1412, "rating_diff": 12}


def test_finalize_amicale_ne_declenche_jamais_le_fetch(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    called = []
    monkeypatch.setattr(client, "fetch_my_rating", lambda *a, **kw: called.append(1))
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()
    time.sleep(0.15)
    assert called == []
    assert not any(t == "lichess_new_rating" for t, _ in events)


# ═══════════════════════════════════════════════════════════════════════
# 5. Cas rares (point 4) rejoués avec `rated=True` — mêmes mécanismes que
#    les issues précédentes (#318/#331/#334/#328), jamais de comportement
#    différent selon classée/amicale, hors affichage et journal.
# ═══════════════════════════════════════════════════════════════════════

def test_rated_adversaire_parti_puis_reclamation(isolated_config, monkeypatch):
    import nicsoft.core.config_manager as cm
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game.rated = True
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    assert game._opponent_gone_claimable is True
    assert board.beep_count >= 1


def test_rated_nulle_proposee_puis_refusee(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=board)
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)
    game._known_user_color = "white"
    game.rated = True
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp", "name": "Adversaire"},
        "rated": True,
        "state": {"status": "started", "moves": ""},
    })
    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True
    # L'utilisateur joue son propre coup (nulle toujours en attente), puis
    # l'adversaire répond sans accepter -> nulle refusée (même mécanisme
    # que #311/#318).
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": True, "bdraw": False})
    assert game._my_draw_offer_pending is True
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_refused", {}) in events


def test_rated_demande_reprise_de_coup_refusee(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    refused = []
    monkeypatch.setattr(client, "answer_takeback", lambda game_id, accept: refused.append(accept))
    _started(game, "white", opponent_is_ai=False)
    game.rated = True
    game._apply_game_state({"status": "started", "moves": "e2e4", "btakeback": True})
    assert refused == [False]  # toujours refusée (l'échiquier physique ne peut pas défaire un coup)


def test_rated_temps_ecoule_fin_de_partie(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game.rated = True
    game._apply_game_state({"status": "outoftime", "moves": "e2e4 e7e5", "winner": "black"})
    game._finalize()
    assert game.opponent_caused_end is True
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["rated"] is True
    assert game_over["opponent_cause_key"] == "lichess.cause.timeout"


def test_rated_abandon_de_l_adversaire(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game.rated = True
    game._apply_game_state({"status": "resign", "moves": "", "winner": "white"})
    game._finalize()
    assert game.opponent_caused_end is True
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["rated"] is True
    assert game_over["opponent_cause_key"] == "lichess.cause.resign"


def test_rated_abandon_demande_par_l_utilisateur(monkeypatch):
    """L'utilisateur abandonne lui-même — jamais le signal « provoquée par
    l'adversaire », classée comme amicale (mécanisme inchangé, #310/#311)."""
    board = _AlertBoard()
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=board)
    # Aucun coup encore joué après _started() -> _request_resign_or_abort()
    # tente abort() avant resign() (une partie sans coup s'annule, elle ne
    # s'abandonne pas — règle Lichess inchangée par cette issue).
    monkeypatch.setattr(client, "abort", lambda game_id: None)
    monkeypatch.setattr(client, "resign", lambda game_id: None)
    _started(game, "white", opponent_is_ai=False)
    game.rated = True
    actions.put({"type": "lichess_resign"})
    game._process_browser_actions()
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()
    assert game.opponent_caused_end is False
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["rated"] is True


def test_rated_partie_interrompue_avant_le_premier_coup_aborted(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "black", opponent_is_ai=False)
    game.rated = True
    game._apply_game_state({"status": "aborted", "moves": ""})
    game._finalize()
    aborted_events = [d for t, d in events if t == "lichess_aborted"]
    assert aborted_events
    assert aborted_events[-1]["message_key"] == "lichess.annulee_premier_coup_trop_tard"


def test_rated_deconnexion_reseau_puis_reconnexion_mi_partie(monkeypatch):
    """Déconnexion réseau en cours de partie (flux général, #309) : le
    signal de début de partie ne doit jamais se répéter même si un nouveau
    gameFull complet revient à la reconnexion (voir aussi la section 3)."""
    board = _SignalRecordingBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game.rated = True
    board.signal_calls.clear()  # ne garder que ce qui suit la reconnexion
    board.beep_count = 0

    game._handle_stream_event({"type": "reconnecting", "attempt": 1})
    assert ("lichess_reconnecting", {"attempt": 1}) in events
    game._handle_stream_event({"type": "reconnected"})
    assert ("lichess_reconnected", {}) in events
    game._handle_stream_event({
        "type": "gameFull",
        "white": {"id": "alain"}, "black": {"id": "opp"}, "rated": True,
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert board.signal_calls == []  # pas un second signal de début de partie
    assert game.rated is True


# ═══════════════════════════════════════════════════════════════════════
# 6. Reprise (L2b) d'une partie classée (point 4).
# ═══════════════════════════════════════════════════════════════════════

def test_reprise_partie_classee_lit_bien_rated(monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board, resuming=True)
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp"}, "rated": True,
        "state": {"status": "started", "moves": "e2e4 e7e5", "wtime": 800000, "btime": 800000},
    })
    assert game.rated is True
    assert game._resume_pending is True
    init_payload = [d for t, d in events if t == "lichess_init"][-1]
    assert init_payload["rated"] is True


# ═══════════════════════════════════════════════════════════════════════
# 7. Journal (point 5) — "classée"/"rated" présent, jamais le jeton.
# ═══════════════════════════════════════════════════════════════════════

def test_journal_recherche_mentionne_classee(tmp_path):
    class _CapturingTransport:
        def open_stream(self, method, url, token, fields=None):
            return FakeStreamHandle([""] * 3)

    client = GameClient("lip_secrettoken1234", transport=_CapturingTransport())
    log = GameLog("recherche", token="lip_secrettoken1234", logs_dir=tmp_path)
    client.attach_game_log(log)
    session = SeekSession(client, game_log=log)
    session.start(15.0, 10, "", rated=True)
    session.next_event(timeout=0.1)
    session.cancel()
    log.close()
    content = log.path.read_text(encoding="utf-8")
    assert "classée=True" in content
    assert "lip_secrettoken1234" not in content


def test_journal_gamefull_mentionne_classee(monkeypatch, tmp_path):
    board = _AlertBoard()
    log = GameLog("gid344", logs_dir=tmp_path)
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board, game_log=log)
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp"}, "rated": True,
        "state": {"status": "started", "moves": ""},
    })
    log.close()
    content = log.path.read_text(encoding="utf-8")
    assert "classée=True" in content
    assert "signal de début de partie émis" in content


# ═══════════════════════════════════════════════════════════════════════
# 8. Garde-fou fair-play (point 6) — le mode classé ne lance aucun moteur.
# ═══════════════════════════════════════════════════════════════════════

_FORBIDDEN_ENGINE_MODULES = (
    "nicsoft.engine.analyse", "nicsoft.engine.engine_analysis",
    "nicsoft.engine.engine_availability", "nicsoft.engine.engine_detection",
    "nicsoft.engine.engine_manager", "nicsoft.engine.maia_engine",
    "nicsoft.engine.move_quality", "nicsoft.engine.review_multipv",
    "nicsoft.engine.rodent_engine", "nicsoft.engine.uci_engine",
)


def test_partie_classee_complete_n_importe_jamais_de_moteur(monkeypatch):
    """Complément DYNAMIQUE au garde-fou statique (test_issue333_lichess_
    no_engine.py, analyse AST de tous les fichiers du mode) : fait
    réellement tourner un cycle complet de partie CLASSÉE (mise en place,
    coups, fin) et vérifie qu'aucun module moteur n'est présent dans
    sys.modules à la fin — un import tardif, caché dans une branche
    conditionnelle jamais visitée par l'analyse statique, serait détecté
    ici."""
    # Diff avant/après plutôt qu'une absence stricte : d'autres fichiers de
    # la suite complète importent déjà certains de ces modules moteur AVANT
    # ce test (collection pytest, même processus) — seul un NOUVEL import
    # causé par CE scénario doit faire échouer ce test.
    before = {m for m in _FORBIDDEN_ENGINE_MODULES if m in sys.modules}

    board = _AlertBoard()
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=board)
    game._known_user_color = "white"
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp"}, "rated": True,
        "state": {"status": "started", "moves": ""},
    })
    assert game.rated is True
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})
    game._apply_game_state({"status": "resign", "moves": "e2e4 e7e5", "winner": "white"})
    game._finalize()

    after = {m for m in _FORBIDDEN_ENGINE_MODULES if m in sys.modules}
    nouveaux = after - before
    assert not nouveaux, f"module(s) moteur nouvellement chargé(s) pendant une partie classée : {nouveaux}"
