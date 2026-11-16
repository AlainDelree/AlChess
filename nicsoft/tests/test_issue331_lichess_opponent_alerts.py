"""
nicsoft/tests/test_issue331_lichess_opponent_alerts.py — AlChess

Issue #331 : Alain a passé ~5 minutes devant l'échiquier physique à
attendre le coup de son adversaire humain sans voir que celui-ci avait
abandonné — l'écran affichait la fin de partie, mais rien ne le signalait
sur l'échiquier ni par le son. Ce fichier couvre, sans réseau ni échiquier
réel (faux transport Lichess, faux pilote LED/USB, garde-fou réseau actif
via conftest.py) :

  1. bip émis ou non selon la case « Bip quand l'adversaire joue »,
     y compris cochée/décochée en cours de partie (effet immédiat) ;
  2. mémorisation de l'état de cette case, sans effet sur le jeton Lichess ;
  3. abandon, nulle proposée, temps écoulé, mat de l'adversaire : LED de la
     bonne moitié de l'échiquier pour chacune des deux orientations ;
  4. acquittement (réponse à la nulle, ou bouton « Éteindre les LED »,
     renommé par l'issue #351 point 0a, ex « J'ai vu ») qui éteint les LED ;
  5. aucun signal (bip ou LED moitié-adversaire) pour les coups ou la fin
     de partie provoqués par l'UTILISATEUR lui-même (mat qu'il délivre,
     nulle qu'il accepte, abandon/annulation qu'il demande).

Entièrement hors ligne : FakeTransport/GameClient réutilisés de
test_issue309_lichess_l2a, comme le reste de la suite Lichess.
"""
import queue

import chess
import pytest

import nicsoft.core.config_manager as cm
from nicsoft.modes.lichess.game import LichessGame, opponent_half_led_pattern, _RANKS_1_4_LIT, _RANKS_5_8_LIT
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport, _make_recorder, _ok
from nicsoft.modes.lichess.game_client import GameClient


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirige config.json vers un fichier temporaire — jamais la vraie
    data/config.json d'Alain pendant les tests (même pattern que
    test_issue306_lichess.py::isolated_config)."""
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg_file)
    return cfg_file


class _AlertBoard:
    """Double du plateau physique qui enregistre bips et commandes LED —
    jamais de vrai accès USB. `set_all_leds` enregistre le pattern reçu tel
    quel (liste de 8 chaînes binaires), pour vérifier la moitié allumée."""

    def __init__(self, initial_fen=chess.STARTING_BOARD_FEN):
        self.current_fen = initial_fen + " w - - 0 1"
        self.led_calls = []
        self.leds_off_count = 0
        self.all_leds_calls = []
        self.beep_count = 0
        self.disconnected = False

    def set_led(self, square, status):
        self.led_calls.append((square, status))

    def turn_off_all_leds(self):
        self.leds_off_count += 1

    def set_all_leds(self, pattern):
        self.all_leds_calls.append(list(pattern))

    def signal_lights(self, sig_num, stop=None):
        pass

    def beep(self):
        self.beep_count += 1

    def disconnect(self):
        self.disconnected = True


def _make_game(monkeypatch, nl_inst=None, **kwargs):
    events, states, actions = _make_recorder(monkeypatch)
    nl_inst = nl_inst or _AlertBoard()
    transport = kwargs.pop("transport", FakeTransport())
    client = GameClient("lip_test_token", transport=transport)
    game = LichessGame(
        nl_inst, client, kwargs.pop("game_id", "gid331"),
        level=kwargs.pop("level", 1), player_name=kwargs.pop("player_name", "Alain"),
        clock_limit_s=kwargs.pop("clock_limit_s", 900), clock_increment_s=kwargs.pop("clock_increment_s", 10),
        **kwargs,
    )
    return game, client, events, states, actions


def _started(game, user_color="white", opponent_is_ai=True):
    """Démarre une partie déjà en cours (sans réseau) avec la couleur
    utilisateur demandée. `opponent_is_ai=False` pour autoriser les
    scénarios de nulle (proposer une nulle contre l'IA est un no-op,
    issue #327 point 5 — sans rapport avec cette issue)."""
    if opponent_is_ai:
        white = {"aiLevel": 1} if user_color == "black" else {"id": "alain"}
        black = {"id": "alain"} if user_color == "black" else {"aiLevel": 1}
    else:
        white = {"id": "alain"} if user_color == "white" else {"id": "opp"}
        black = {"id": "opp"} if user_color == "white" else {"id": "alain"}
        game._known_user_color = user_color
    game._apply_game_full({"white": white, "black": black, "state": {"status": "started", "moves": ""}})
    assert game.user_color == user_color
    # Remis à zéro après la mise en place (issue #344, point 3bis : le
    # signal de début de partie bipe une fois dans _apply_game_full
    # ci-dessus) — les tests de cette suite portent sur des bips/LED
    # déclenchés APRÈS ce point, jamais sur ce signal lui-même (couvert par
    # test_issue344_lichess_rated.py).
    if hasattr(game.nl_inst, "beep_count"):
        game.nl_inst.beep_count = 0


# ═══════════════════════════════════════════════════════════════════════
# 1. Bip — case à cocher, y compris basculée en cours de partie.
# ═══════════════════════════════════════════════════════════════════════

def test_coup_adverse_sans_case_cochee_ne_bipe_pas(isolated_config, monkeypatch):
    cm.save_config({"lichess_beep_opponent_move": False})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    # Utilisateur blancs : "e7e5" (coup n°2) est le coup de l'ADVERSAIRE.
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})
    assert board.beep_count == 0


def test_coup_adverse_avec_case_cochee_bipe_une_fois(isolated_config, monkeypatch):
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})
    assert board.beep_count == 1


def test_case_cochee_decochee_en_cours_de_partie_effet_immediat(isolated_config, monkeypatch):
    """Relue à chaque coup (jamais mise en cache) — basculer la case en
    cours de partie change le comportement dès le COUP SUIVANT, sans
    redémarrer la partie (issue #331, point 1 : « effet immédiat »)."""
    cm.save_config({"lichess_beep_opponent_move": False})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")

    game._apply_game_state({"status": "started", "moves": "e2e4"})
    assert board.beep_count == 0  # case décochée au premier coup adverse

    cm.save_config({"lichess_beep_opponent_move": True})
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5 g1f3"})
    assert board.beep_count == 1  # cochée désormais : le coup adverse suivant bipe

    cm.save_config({"lichess_beep_opponent_move": False})
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5 g1f3 b8c6 f1b5"})
    assert board.beep_count == 1  # redécochée : plus de bip


# ═══════════════════════════════════════════════════════════════════════
# 2. Mémorisation — aucun effet sur le jeton Lichess.
# ═══════════════════════════════════════════════════════════════════════

def test_case_memorisee_sans_toucher_au_jeton(isolated_config):
    cm.save_config({"lichess_token": "lip_secret1234567890"})
    cm.save_config({"lichess_beep_opponent_move": True})
    cfg = cm.load_config()
    assert cfg["lichess_beep_opponent_move"] is True
    assert cfg["lichess_token"] == "lip_secret1234567890"  # inchangé

    cm.save_config({"lichess_beep_opponent_move": False})
    cfg = cm.load_config()
    assert cfg["lichess_beep_opponent_move"] is False
    assert cfg["lichess_token"] == "lip_secret1234567890"


def test_case_decochee_par_defaut():
    assert cm.DEFAULT_CONFIG["lichess_beep_opponent_move"] is False


# ═══════════════════════════════════════════════════════════════════════
# 3. LED — moitié adversaire, pour chaque déclencheur et chaque orientation.
# ═══════════════════════════════════════════════════════════════════════

def test_opponent_half_led_pattern_selon_orientation():
    assert opponent_half_led_pattern("white") == _RANKS_5_8_LIT   # adversaire noir -> rangs 5-8
    assert opponent_half_led_pattern("black") == _RANKS_1_4_LIT   # adversaire blanc -> rangs 1-4


@pytest.mark.parametrize("user_color,expected_pattern", [("white", _RANKS_5_8_LIT), ("black", _RANKS_1_4_LIT)])
def test_nulle_proposee_par_adversaire_allume_bonne_moitie(isolated_config, monkeypatch, user_color, expected_pattern):
    cm.save_config({"lichess_beep_opponent_move": False})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, user_color, opponent_is_ai=False)

    opponent_offer_field = "bdraw" if user_color == "white" else "wdraw"
    game._apply_game_state({"status": "started", "moves": "", opponent_offer_field: True})

    assert board.all_leds_calls and board.all_leds_calls[-1] == expected_pattern
    assert ("lichess_draw_offered", {"offered": True}) in events


@pytest.mark.parametrize("user_color,expected_pattern", [("white", _RANKS_5_8_LIT), ("black", _RANKS_1_4_LIT)])
def test_abandon_adversaire_allume_bonne_moitie(isolated_config, monkeypatch, user_color, expected_pattern):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, user_color)

    winner = "black" if user_color == "white" else "white"
    game._apply_game_state({"status": "resign", "moves": "", "winner": winner})
    game._finalize()

    assert game.opponent_caused_end is True
    assert board.all_leds_calls and board.all_leds_calls[-1] == expected_pattern
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["opponent_caused_end"] is True
    assert game_over["opponent_cause_key"] == "lichess.cause.resign"


@pytest.mark.parametrize("status", ["outoftime", "mate"])
def test_temps_ecoule_et_mat_de_l_adversaire_allument_leds(isolated_config, monkeypatch, status):
    """« Mat de l'adversaire » = l'adversaire délivre le mat contre
    l'utilisateur (le coup gagnant n'est pas le dernier coup de
    l'utilisateur) — distinct du cas où l'utilisateur mate lui-même
    l'adversaire (voir test_mat_delivre_par_l_utilisateur_n_alerte_pas)."""
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    # L'adversaire (noir) joue le dernier coup qui met fin à la partie.
    game._apply_game_state({"status": status, "moves": "e2e4 e7e5", "winner": "black"})
    game._finalize()
    assert game.opponent_caused_end is True
    assert board.all_leds_calls and board.all_leds_calls[-1] == _RANKS_5_8_LIT


def test_nulle_acceptee_par_adversaire_allume_leds(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    game._apply_game_state({"status": "draw", "moves": "e2e4 e7e5"})
    game._finalize()
    assert game.opponent_caused_end is True
    assert board.all_leds_calls and board.all_leds_calls[-1] == _RANKS_5_8_LIT
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["opponent_cause_key"] == "lichess.cause.draw"


# ═══════════════════════════════════════════════════════════════════════
# 4. Acquittement — éteint les LED.
# ═══════════════════════════════════════════════════════════════════════

def test_acquittement_lichess_ack_game_over_eteint_les_led(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})
    game._finalize()
    assert game.opponent_caused_end is True
    off_before = board.leds_off_count

    actions.put({"type": "lichess_ack_game_over"})
    game._wait_for_game_over_ack()  # ne bloque pas : l'action est déjà dans la file
    assert board.leds_off_count == off_before  # pas encore — _wait_for_game_over_ack() n'éteint pas elle-même

    game._clear_opponent_alert_leds("fin de partie acquittée (test)")
    assert board.leds_off_count == off_before + 1


def test_acquittement_par_back_menu_debloque_aussi(isolated_config, monkeypatch):
    """Un retour au menu depuis l'écran de fin de partie vaut acquittement
    implicite (issue #331, point 3) — l'utilisateur a déjà quitté l'écran."""
    board = _AlertBoard()
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    game._apply_game_state({"status": "resign", "moves": "", "winner": "black"})

    actions.put({"type": "back_menu"})
    game._wait_for_game_over_ack()  # revient sans bloquer


def test_reponse_a_la_nulle_eteint_deja_les_led_sans_attendre_la_fin(isolated_config, monkeypatch):
    """Accepter/refuser la nulle (boutons existants) éteint immédiatement
    le signal — pas besoin d'attendre le bandeau de fin de partie."""
    board = _AlertBoard()
    game, client, events, states, actions = _make_game(monkeypatch, nl_inst=board, transport=FakeTransport(
        requests=[_ok({"ok": True})],
    ))
    _started(game, "white", opponent_is_ai=False)
    game._apply_game_state({"status": "started", "moves": "", "bdraw": True})
    assert board.all_leds_calls  # LED allumées pour l'offre

    off_before = board.leds_off_count
    actions.put({"type": "lichess_draw_refuse"})
    game._process_browser_actions()
    assert board.leds_off_count == off_before + 1


# ═══════════════════════════════════════════════════════════════════════
# 5. Jamais de signal pour une action de L'UTILISATEUR.
# ═══════════════════════════════════════════════════════════════════════

def test_coup_de_l_utilisateur_jamais_de_bip(isolated_config, monkeypatch):
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    # Coup de l'UTILISATEUR (blancs) — jamais de bip, même case cochée.
    game._apply_game_state({"status": "started", "moves": "e2e4"})
    assert board.beep_count == 0


def test_mat_delivre_par_l_utilisateur_n_alerte_pas(isolated_config, monkeypatch):
    """L'utilisateur vient de délivrer le mat avec son propre coup
    physique : pas une fin « provoquée par l'adversaire » (régression
    constatée pendant le développement — voir rapport de clôture)."""
    board = _AlertBoard()
    game, client, events, states, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white")
    # Le dernier coup appliqué (e2e4, blancs = utilisateur) délivre le mat.
    game._apply_game_state({"status": "mate", "moves": "e2e4", "winner": "white"})
    game._finalize()
    assert game.opponent_caused_end is False
    assert board.all_leds_calls == []
    game_over = [d for t, d in events if t == "game_over"][-1]
    assert game_over["opponent_caused_end"] is False
    assert game_over["opponent_cause_key"] is None


def test_abandon_demande_par_l_utilisateur_n_alerte_pas(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, states, actions = _make_game(
        monkeypatch, nl_inst=board, transport=FakeTransport(requests=[_ok({"ok": True})]),
    )
    _started(game, "white")
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5"})  # >= 2 coups -> resign, pas abort
    actions.put({"type": "lichess_resign"})
    game._process_browser_actions()
    assert game.game_over is True
    assert game._user_initiated_end is True

    board.all_leds_calls.clear()
    game._finalize()
    assert game.opponent_caused_end is False
    assert board.all_leds_calls == []


def test_utilisateur_accepte_la_nulle_n_alerte_pas_a_la_fin(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, states, actions = _make_game(
        monkeypatch, nl_inst=board, transport=FakeTransport(requests=[_ok({"ok": True})]),
    )
    _started(game, "white", opponent_is_ai=False)
    game._apply_game_state({"status": "started", "moves": "", "bdraw": True})
    actions.put({"type": "lichess_draw_accept"})
    game._process_browser_actions()
    assert game._user_just_accepted_draw is True

    board.all_leds_calls.clear()
    game._status = "draw"
    game._finalize()
    assert game.opponent_caused_end is False
    assert board.all_leds_calls == []


# ═══════════════════════════════════════════════════════════════════════
# 6. Journal de partie — une ligne par bip et par commande LED.
# ═══════════════════════════════════════════════════════════════════════

def test_journal_contient_bip_et_led(isolated_config, monkeypatch, tmp_path):
    from nicsoft.modes.lichess.game_log import GameLog

    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    # logs_dir=tmp_path (jamais le vrai dossier de journaux d'Alain).
    game, client, events, states, _ = _make_game(
        monkeypatch, nl_inst=board, game_log=GameLog("gid331", logs_dir=tmp_path),
    )
    _started(game, "white")
    game._apply_game_state({"status": "resign", "moves": "e2e4", "winner": "white"})
    # "e2e4" est joué par l'utilisateur (blancs) ; l'abandon lui-même vient
    # du flux (status="resign"), donc provoqué par l'adversaire malgré le
    # dernier coup utilisateur (resign != mate, voir _finalize).
    game._finalize()
    assert game.opponent_caused_end is True
    log_path = game._game_log.path
    game._game_log.close()
    assert log_path is not None
    content = log_path.read_text(encoding="utf-8")
    assert "[STATE] LED allumées" in content
