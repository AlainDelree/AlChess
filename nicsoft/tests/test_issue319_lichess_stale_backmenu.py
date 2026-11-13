"""
nicsoft/tests/test_issue319_lichess_stale_backmenu.py — AlChess

Issue #319 — essai réel d'Alain (13 novembre 2026, 09:20:37) : une relance
de partie Lichess (blancs) a été annulée dès son premier coup physique
("partie annulée, moins de 2 coups") sans qu'Alain n'ait rien demandé.

Cause établie par lecture du code (sans matériel pour la rejouer) :
action_queue (nicsoft.web.server) est globale et partagée par tous les
modes. on_action() y met une action "back_menu" dès qu'elle est cliquée
pendant un état "connecting"/"playing"/"game_over"/... — y compris depuis
l'écran de fin de partie PRÉCÉDENTE (où personne ne relit plus la queue,
cette partie-là étant déjà finalisée), ou pendant l'attente de la partie
EN COURS de lancement (état "connecting", avant que l'attente de position
ne passe à "position_initiale"/"lichess_wait_first_move" — ces deux états
ne sont eux jamais relayés à action_queue). _run_lichess ne vidait jamais
cette file avant de démarrer LichessGame : son premier appel à
_process_browser_actions() (game.py), avant même le premier événement de
flux, lisait donc cette action périmée et l'interprétait comme une
annulation voulue pour LA NOUVELLE partie.

Correction : _discard_stale_browser_actions() (game_manager_modes/
lichess.py) vide action_queue juste avant game.start() — même geste déjà
fait par humain.py/pedagogique.py pour la même classe de bug. Le journal
indique désormais, pour toute annulation/abandon, la raison (demandé par
l'utilisateur via back_menu/bouton Abandonner, ou autre) — voir game.py.

Entièrement sans réseau (faux transport/client, voir test_issue309) et
sans matériel (faux plateau) — driver.py n'est jamais modifié ni mocké à
un niveau plus bas que nécessaire.
"""
import logging
import queue

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.game as game_mod
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport, _make_recorder, _ok
from nicsoft.tests.test_issue311_lichess_sequencing import (
    AFTER_E2E4_W,
    INITIAL_FEN_W,
    _RecordingClient,
    _ScriptedBoard,
    _make_bare_game,
)

LOGGER_NAME = "niclink.lichess"


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


def _wire_shared_action_queue(monkeypatch, *stale_actions):
    """Un seul queue.Queue partagé entre lichess_launcher.get_action_queue()
    (utilisé par _discard_stale_browser_actions) et game_mod.get_action()
    (utilisé par LichessGame._process_browser_actions) — comme en
    production, où les deux lisent la même action_queue globale
    (nicsoft.web.server)."""
    shared = queue.Queue()
    for action in stale_actions:
        shared.put(action)

    def fake_get_action(timeout=0.0):
        try:
            return shared.get(timeout=timeout)
        except queue.Empty:
            return None

    monkeypatch.setattr(game_mod, "get_action", fake_get_action)
    monkeypatch.setattr(lichess_launcher, "get_action_queue", lambda: shared)
    return shared


# ═══════════════════════════════════════════════════════════════════════
# 1. _discard_stale_browser_actions() — vidage et journalisation
# ═══════════════════════════════════════════════════════════════════════

def test_discard_stale_browser_actions_vide_et_journalise(monkeypatch, caplog):
    shared = queue.Queue()
    shared.put({"type": "back_menu"})
    shared.put({"type": "lichess_resign"})
    monkeypatch.setattr(lichess_launcher, "get_action_queue", lambda: shared)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        lichess_launcher._discard_stale_browser_actions()

    assert shared.empty()
    assert "2 action(s) périmée(s)" in caplog.text
    assert "back_menu" in caplog.text
    assert "lichess_resign" in caplog.text


def test_discard_stale_browser_actions_queue_vide_ne_journalise_rien(monkeypatch, caplog):
    monkeypatch.setattr(lichess_launcher, "get_action_queue", lambda: queue.Queue())
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        lichess_launcher._discard_stale_browser_actions()
    assert "périmée" not in caplog.text


# ═══════════════════════════════════════════════════════════════════════
# 2. Bout en bout — une action périmée en file ne doit jamais annuler la
#    partie qui démarre (issue #319, point 2 et point 5)
# ═══════════════════════════════════════════════════════════════════════

def test_run_lichess_action_perimee_n_annule_pas_la_partie_noirs(monkeypatch, caplog):
    """Noirs : la partie est créée dès la position confirmée. Un
    "back_menu" déjà présent dans action_queue (laissé par l'écran
    précédent) ne doit pas être lu par LichessGame comme une annulation de
    CETTE partie."""
    _make_recorder(monkeypatch)
    _wire_shared_action_queue(monkeypatch, {"type": "back_menu"})

    board = _ScriptedBoard([INITIAL_FEN_W])
    client = _RecordingClient(user_color="black", ai_first_move="d2d4")
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)

    assert client.created_with is not None  # la partie a bien été créée
    assert "moins de 2 coups" not in caplog.text  # jamais annulée par l'action périmée
    assert "action(s) périmée(s) écartée(s)" in caplog.text  # vidage journalisé


def test_run_lichess_relance_apres_echec_ouverture_avec_action_perimee_blancs(monkeypatch, caplog):
    """Scénario complet de l'essai réel du 13/11/2026 : premier essai
    d'ouverture de l'échiquier échoué (#317), relance réussie, premier coup
    physique détecté, ET une action périmée en file — la partie doit être
    créée et jouée sans annulation (issue #319, point 5)."""
    monkeypatch.setattr(lichess_launcher, "_BOARD_OPEN_RETRY_INTERVAL_S", 0.0)
    _make_recorder(monkeypatch)
    _wire_shared_action_queue(monkeypatch, {"type": "back_menu"})

    board = _ScriptedBoard([INITIAL_FEN_W, AFTER_E2E4_W])
    attempts = []

    def fake_create_board(**kw):
        attempts.append(kw)
        if len(attempts) < 2:
            raise SystemExit("board connection error.")
        return board

    client = _RecordingClient(user_color="white")
    monkeypatch.setattr(lichess_launcher, "create_board", fake_create_board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        lichess_launcher._run_lichess("lip_x", 1, 900, 10, "white", "15+10", "Alain", _error)

    assert len(attempts) == 2  # premier essai échoué, second réussi (issue #317)
    assert client.created_with is not None
    assert client.moves_sent == ["e2e4"]
    assert "moins de 2 coups" not in caplog.text
    assert "action(s) périmée(s) écartée(s)" in caplog.text


# ═══════════════════════════════════════════════════════════════════════
# 3. Un vrai retour au menu / abandon PENDANT la partie reste pris en
#    compte, et la raison est journalisée (issue #319, point 3)
# ═══════════════════════════════════════════════════════════════════════

def test_back_menu_pendant_la_partie_annule_et_journalise_la_raison(monkeypatch, caplog):
    game, events, states, actions = _make_bare_game(
        monkeypatch, transport=FakeTransport(requests=[_ok({"ok": True})]))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},
    })
    actions.put({"type": "back_menu"})
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        game._process_browser_actions()

    assert game._back_menu_requested is True
    assert game._aborted is True  # moins de 2 coups → annulation, pas abandon
    assert "raison : retour au menu demandé par l'utilisateur" in caplog.text


def test_abandon_pendant_la_partie_annule_et_journalise_la_raison(monkeypatch, caplog):
    game, events, states, actions = _make_bare_game(
        monkeypatch, transport=FakeTransport(requests=[_ok({"ok": True})]))
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},
    })
    actions.put({"type": "lichess_resign"})
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        game._process_browser_actions()

    assert game.game_over is True
    assert "raison : bouton Abandonner demandé par l'utilisateur" in caplog.text


def test_fin_inattendue_journalise_raison_autre(monkeypatch, caplog):
    """Un statut de fin ni back_menu ni abandon/annulation demandé par
    l'utilisateur doit écrire "raison : autre" — jamais confondu avec une
    demande explicite."""
    game, events, states, _ = _make_bare_game(monkeypatch)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},
    })
    game._status = "aborted"
    game._winner = ""
    game._aborted = True
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        game._finalize()

    assert "raison : autre" in caplog.text
    assert "non demandée par l'utilisateur" in caplog.text
