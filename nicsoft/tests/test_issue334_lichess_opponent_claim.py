"""
nicsoft/tests/test_issue334_lichess_opponent_claim.py — AlChess

Issue #334 : Alain joue surtout de longues parties contre des humains.
Quand l'adversaire quitte la partie (fermeture du navigateur, coupure
réseau), Lichess permet de réclamer la victoire après un délai — sans
cela, Alain devait quitter AlChess pour aller réclamer sur lichess.org,
pendant que sa pendule tournait. Par ailleurs une demande de reprise de
coup de l'adversaire restait sans réponse (l'échiquier physique ne peut
pas défaire un coup).

Ce fichier couvre, sans réseau ni échiquier réel (FakeTransport/GameClient
réutilisés de test_issue309_lichess_l2a, double de plateau et aide-fixture
de test_issue331_lichess_opponent_alerts, garde-fou réseau actif via
conftest.py) :

  1. opponentGone : décompte exact depuis l'instant de réception (jamais
     repartant de zéro), boutons grisés puis actifs ;
  2. réclamation de victoire : acceptée (chemin de fin de partie normal),
     refusée par Lichess (message exact, persistant, bouton réutilisable),
     pas encore possible (délai), adversaire revenu entre-temps ;
  3. réclamation de nulle : même règles que la victoire ;
  4. signaux #331 réutilisés (bip double + LED, les deux orientations) —
     déclenchés seulement quand la réclamation devient possible, jamais
     au simple départ de l'adversaire ;
  5. demande de reprise de coup de l'adversaire : refusée une seule fois,
     même si l'état est reçu plusieurs fois ; une nouvelle demande plus
     tard est refusée à nouveau ;
  6. reprise de partie : une demande de reprise déjà active au premier
     état reçu (gameFull) est détectée et refusée dès la mise en place ;
  7. journal de partie dédié : une ligne par événement/requête/signal ;
  8. aucune LED restante après acquittement (prête pour la partie suivante).
"""
import time as real_time

import chess
import pytest

import nicsoft.core.config_manager as cm
from nicsoft.modes.lichess.game import (
    _DOUBLE_BEEP_GAP_S, _RANKS_1_4_LIT, _RANKS_3_4_LIT, _RANKS_5_6_LIT, _RANKS_5_8_LIT,
)
from nicsoft.modes.lichess.transport import TransportHTTPError
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport, _ok
from nicsoft.tests.test_issue331_lichess_opponent_alerts import _AlertBoard, _make_game, _started


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg_file)
    return cfg_file


def _http_error(status_code: int, message: str):
    return lambda method, url, token, fields: TransportHTTPError(status_code, f'{{"error": "{message}"}}')


def _last(events, etype):
    matches = [d for t, d in events if t == etype]
    return matches[-1] if matches else None


def _wait_double_beep():
    """Laisse le fil dédié (voir game.py::_hardware_beep) émettre les deux
    bips espacés de _DOUBLE_BEEP_GAP_S avant de vérifier le compteur."""
    real_time.sleep(_DOUBLE_BEEP_GAP_S + 0.15)


# ═══════════════════════════════════════════════════════════════════════
# 1. opponentGone — décompte exact, boutons grisés puis actifs.
# ═══════════════════════════════════════════════════════════════════════

def test_opponent_gone_decompte_exact_depuis_reception(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 60})
    data = _last(events, "lichess_opponent_gone")
    assert data["gone"] is True
    assert data["claimable"] is False
    assert data["draw_claimable"] is False
    assert data["seconds"] == pytest.approx(60.0, abs=0.5)
    # Issue #340, point 1 : signal LED (toujours) dès le simple départ —
    # pattern PARTIEL, distinct du pattern complet de la réclamation
    # possible (vérifié plus loin dans ce fichier). Pas de bip ici : la
    # case « Bip quand l'adversaire joue » n'est pas cochée dans ce test.
    assert board.beep_count == 0
    assert board.all_leds_calls == [list(_RANKS_5_6_LIT)]

    # 40s d'horloge réelle simulées SANS nouvel événement Lichess — même
    # convention que test_issue311_lichess_sequencing (décrémente la
    # référence monotone mémorisée, jamais une minuterie qui repart à zéro).
    game._opponent_gone_ref_monotonic -= 40.0
    game._push_opponent_gone_state()
    data = _last(events, "lichess_opponent_gone")
    assert data["claimable"] is False
    assert data["seconds"] == pytest.approx(20.0, abs=0.5)
    assert board.beep_count == 0  # toujours pas réclamable


def test_opponent_gone_devient_reclamable_declenche_signal_une_fois(isolated_config, monkeypatch):
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 30})
    # Issue #340, point 1 : le simple départ a déjà émis UN bip (case
    # cochée) + la LED partielle, avant même la transition réclamable.
    _wait_double_beep()
    assert board.beep_count == 1
    assert board.all_leds_calls == [list(_RANKS_5_6_LIT)]

    game._opponent_gone_ref_monotonic -= 30.0
    game._push_opponent_gone_state()
    data = _last(events, "lichess_opponent_gone")
    assert data["claimable"] is True
    assert data["draw_claimable"] is True
    assert data["seconds"] == 0.0
    _wait_double_beep()
    assert board.beep_count == 1 + 2  # 1 (départ) + bip DOUBLE (réclamable, #331 réutilisé)
    assert board.all_leds_calls and board.all_leds_calls[-1] == _RANKS_5_8_LIT

    # Rappelé une seconde fois (prochaine poussée ~1x/s) : aucun second
    # signal pour la même absence.
    game._push_opponent_gone_state()
    _wait_double_beep()
    assert board.beep_count == 3


@pytest.mark.parametrize("user_color,expected_pattern", [("white", _RANKS_5_8_LIT), ("black", _RANKS_1_4_LIT)])
def test_signal_reclamable_bonne_moitie_selon_orientation(isolated_config, monkeypatch, user_color, expected_pattern):
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, user_color, opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    assert board.all_leds_calls and board.all_leds_calls[-1] == expected_pattern


@pytest.mark.parametrize("user_color,expected_pattern", [("white", _RANKS_5_6_LIT), ("black", _RANKS_3_4_LIT)])
def test_signal_depart_bonne_moitie_selon_orientation(isolated_config, monkeypatch, user_color, expected_pattern):
    """Issue #340, point 1/8 : pattern PARTIEL du simple départ, pour les
    deux orientations — distinct du pattern complet (réclamable) et
    toujours côté adversaire (jamais le camp de l'utilisateur, voir la
    correction du point 8 sur _RANKS_1_4_LIT/_RANKS_5_8_LIT)."""
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, user_color, opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 60})
    assert board.all_leds_calls == [list(expected_pattern)]


def test_opponent_revenu_avant_la_fin_du_delai_annule_tout(isolated_config, monkeypatch):
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 30})
    game._opponent_gone_ref_monotonic -= 30.0
    game._push_opponent_gone_state()
    _wait_double_beep()
    assert board.beep_count == 3  # 1 (départ, point 1) + 2 (réclamable, double)
    off_before = board.leds_off_count

    game._handle_stream_event({"type": "opponentGone", "gone": False})
    data = _last(events, "lichess_opponent_gone")
    assert data == {"gone": False}
    assert game._opponent_gone is False
    assert game._opponent_gone_claimable is False
    assert board.leds_off_count == off_before + 1  # LED éteintes au retour


# ═══════════════════════════════════════════════════════════════════════
# 2/3. Réclamation de victoire/nulle.
# ═══════════════════════════════════════════════════════════════════════

def test_reclamation_victoire_pas_encore_possible_n_envoie_pas_la_requete(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 30})

    actions.put({"type": "lichess_claim_victory"})
    game._process_browser_actions()
    toast = _last(events, "lichess_toast")
    assert toast["message_key"] == "lichess.reclamation_pas_encore_possible"


@pytest.mark.parametrize("atype,client_attr", [
    ("lichess_claim_victory", "claim_victory"),
    ("lichess_claim_draw", "claim_draw"),
])
def test_reclamation_acceptee_laisse_le_flux_terminer_la_partie(isolated_config, monkeypatch, atype, client_attr):
    """Jamais de mise à jour locale optimiste de la fin de partie (issue
    #334, point 2) : la requête part, mais c'est le PROCHAIN événement du
    flux (gameState avec un statut terminé) qui termine la partie par le
    chemin existant — ici simulé explicitement."""
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(
        monkeypatch, nl_inst=board, transport=FakeTransport(requests=[_ok({"ok": True})]),
    )
    _started(game, "white", opponent_is_ai=False)
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    assert game._opponent_gone_claimable is True

    actions.put({"type": atype})
    game._process_browser_actions()
    assert game.game_over is False  # pas encore — attend le flux

    game._apply_game_state({"status": "resign", "moves": "", "winner": "white"})
    assert game.game_over is True
    # game_over n'est envoyé que par _finalize() (voir run()) — jamais par
    # _check_finished() elle-même ; les tests qui appellent _apply_game_state
    # directement (hors run()) doivent l'appeler explicitement, comme le
    # fait déjà test_issue331_lichess_opponent_alerts.
    game._finalize()
    game_over = _last(events, "game_over")
    assert game_over["result"] == "1-0"


@pytest.mark.parametrize("atype", ["lichess_claim_victory", "lichess_claim_draw"])
def test_reclamation_refusee_message_persistant_bouton_reutilisable(isolated_config, monkeypatch, atype):
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(
        monkeypatch, nl_inst=board,
        transport=FakeTransport(requests=[_http_error(400, "Too soon to claim victory")]),
    )
    _started(game, "white", opponent_is_ai=False)
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})

    actions.put({"type": atype})
    game._process_browser_actions()
    toast = _last(events, "lichess_toast")
    assert toast["message_key"] == "lichess.reclamation_refusee"
    # Issue #393, point 2 : message non reconnu -> clé générique traduite,
    # jamais le texte anglais brut de Lichess affiché.
    assert toast["vars"] == {"detail_key": "lichess.detail.generique", "detail_vars": {}}
    assert toast["persistent"] is True
    assert game.game_over is False
    # Le bouton redevient utilisable : rien n'a verrouillé l'état local —
    # toujours réclamable tant que l'adversaire reste parti.
    assert game._opponent_gone_claimable is True


def test_reclamation_victoire_partie_deja_terminee_cote_lichess(isolated_config, monkeypatch):
    """Erreur Lichess « partie déjà terminée » — même traitement qu'un
    autre refus 400 : message exact, persistant, aucun blocage silencieux."""
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(
        monkeypatch, nl_inst=board,
        transport=FakeTransport(requests=[_http_error(400, "Game is already over")]),
    )
    _started(game, "white", opponent_is_ai=False)
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})

    actions.put({"type": "lichess_claim_victory"})
    game._process_browser_actions()
    toast = _last(events, "lichess_toast")
    # Issue #393, point 2 : reconnu par translate_api_detail -> clé
    # dédiée traduite, jamais le texte anglais brut de Lichess affiché.
    assert toast["vars"] == {"detail_key": "lichess.detail.partie_terminee", "detail_vars": {}}


# ═══════════════════════════════════════════════════════════════════════
# 5. Reprise de coup de l'adversaire — refus unique, nouvelle demande.
# ═══════════════════════════════════════════════════════════════════════

def test_demande_reprise_refusee_une_seule_fois_meme_recue_plusieurs_fois(isolated_config, monkeypatch):
    board = _AlertBoard()
    requests = [_ok({"ok": True})]
    game, client, events, _, _ = _make_game(
        monkeypatch, nl_inst=board, transport=FakeTransport(requests=requests),
    )
    _started(game, "white", opponent_is_ai=False)

    sent = []
    monkeypatch.setattr(client, "answer_takeback", lambda gid, accept: sent.append(accept))

    game._apply_game_state({"status": "started", "moves": "", "btakeback": True})
    assert sent == [False]
    toast = _last(events, "lichess_toast")
    assert toast["message_key"] == "lichess.reprise_refusee"
    assert toast["persistent"] is True

    # Même état reçu une seconde fois (ex. heartbeat Lichess) — jamais de
    # second refus envoyé (jamais en boucle).
    game._apply_game_state({"status": "started", "moves": "", "btakeback": True})
    assert sent == [False]


def test_nouvelle_demande_reprise_plus_tard_refusee_a_nouveau(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    sent = []
    monkeypatch.setattr(client, "answer_takeback", lambda gid, accept: sent.append(accept))

    game._apply_game_state({"status": "started", "moves": "", "btakeback": True})
    assert sent == [False]

    # La demande disparaît (traitée côté Lichess) puis l'adversaire en
    # relance une nouvelle plus tard, après un coup — refusée à nouveau.
    game._apply_game_state({"status": "started", "moves": "e2e4"})
    game._apply_game_state({"status": "started", "moves": "e2e4", "btakeback": True})
    assert sent == [False, False]


def test_demande_reprise_jamais_proposable_par_l_utilisateur(isolated_config, monkeypatch):
    """Aucune action `sendAction` ne permet à l'utilisateur de proposer lui-
    même une reprise : seul le handler de refus existe côté serveur (voir
    _process_browser_actions — aucun atype n'envoie answer_takeback(True))."""
    import inspect

    from nicsoft.modes.lichess import game as game_mod
    source = inspect.getsource(game_mod.LichessGame._process_browser_actions)
    assert "answer_takeback(self.game_id, True)" not in source


# ═══════════════════════════════════════════════════════════════════════
# 6. Reprise de partie — demande de reprise déjà active à la mise en place.
# ═══════════════════════════════════════════════════════════════════════

def test_reprise_avec_demande_de_reprise_deja_active_refusee_a_la_mise_en_place(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(
        monkeypatch, nl_inst=board, resuming=True, known_user_color="white",
    )
    sent = []
    monkeypatch.setattr(client, "answer_takeback", lambda gid, accept: sent.append(accept))

    # Reprise : l'adversaire a DÉJÀ demandé une reprise de coup au moment
    # où le premier gameFull arrive (issue #334, point 6) — AlChess doit
    # la détecter et la refuser dès ce premier état, pas seulement au
    # prochain gameState.
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"id": "opp"},
        "state": {"status": "started", "moves": "e2e4", "btakeback": True},
    })
    assert sent == [False]
    toast = _last(events, "lichess_toast")
    assert toast["message_key"] == "lichess.reprise_refusee"


# ═══════════════════════════════════════════════════════════════════════
# 7/8. Journal dédié, aucune LED restante après acquittement.
# ═══════════════════════════════════════════════════════════════════════

def test_journal_contient_opponent_gone_et_reprise(isolated_config, monkeypatch, tmp_path):
    from nicsoft.modes.lichess.game_log import GameLog

    board = _AlertBoard()
    game, client, events, _, _ = _make_game(
        monkeypatch, nl_inst=board, game_log=GameLog("gid334log", logs_dir=tmp_path),
        transport=FakeTransport(requests=[_ok({"ok": True})]),
    )
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    game._apply_game_state({"status": "started", "moves": "", "btakeback": True})

    log_path = game._game_log.path
    game._game_log.close()
    content = log_path.read_text(encoding="utf-8")
    assert "opponentGone reçu" in content
    assert "demande de reprise de coup reçue" in content
    assert "LED allumées" in content
    assert "lip_" not in content  # jamais le jeton, jamais même son préfixe


def test_acquittement_signal_opponent_gone_eteint_led_mais_garde_bandeau(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    assert board.all_leds_calls
    off_before = board.leds_off_count

    actions.put({"type": "lichess_opponent_gone_ack"})
    game._process_browser_actions()
    assert board.leds_off_count == off_before + 1
    assert game._opponent_gone_signal_acked is True
    # Le bandeau/l'état réclamable restent vrais — seul le signal s'éteint.
    assert game._opponent_gone is True
    assert game._opponent_gone_claimable is True


def test_aucune_led_restante_au_debut_de_la_partie_suivante(isolated_config, monkeypatch):
    """Comme pour #331 : les LED du signal « adversaire parti » sont
    éteintes par le launcher (nl_inst.turn_off_all_leds() dans le `finally`
    de _run_lichess/_run_lichess_human, non modifié ici) avant la partie
    suivante — simulé ici en appelant directement cette même méthode,
    seule garantie dont ce module dispose."""
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    assert board.all_leds_calls

    board.turn_off_all_leds()
    board2 = _AlertBoard()
    game2, _, _, _, _ = _make_game(monkeypatch, nl_inst=board2, game_id="gid334next")
    _started(game2, "white", opponent_is_ai=False)
    assert board2.all_leds_calls == []
