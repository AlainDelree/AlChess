"""
nicsoft/tests/test_issue340_lichess_opponent_signal.py — AlChess

Issue #340 : lors d'une vraie partie contre un humain (15/11/2026, Alain
jouait les noirs), trois défauts sont apparus dans les signaux « adversaire
parti » posés par #334 (qui réutilisent eux-mêmes les primitives LED/bip de
#331) :

  1. aucun signal n'était donné au simple DÉPART de l'adversaire (seulement
     à la réclamation possible, 85s plus tard) — Alain ne voyait rien sur
     l'échiquier physique pendant cette attente ;
  8. la mauvaise moitié de l'échiquier s'allumait pour le signal (celle de
     l'utilisateur plutôt que celle de l'adversaire) — bug d'inversion des
     constantes _RANKS_1_4_LIT/_RANKS_5_8_LIT, pas d'orientation ;
  9. le signal « réclamable » a été redonné trois fois de suite (au lieu
     d'une) parce que chaque événement `opponentGone` répété (Lichess en
     renvoie environ toutes les 5s, y compris après que le délai affiché a
     atteint 0) réarmait à tort `_opponent_gone_claimable` ;
 10. la réclamation réussie d'Alain a ensuite, à tort, redonné le signal
     « fin de partie provoquée par l'adversaire » (LED + bip double) alors
     que c'est lui qui avait provoqué cette fin.

Ce fichier couvre, sans réseau ni échiquier réel (même infrastructure que
test_issue331/test_issue334, garde-fou réseau actif via conftest.py) :

  1. signal de départ (bip simple + LED PARTIELLE), une seule fois ;
  5. priorité au coup adverse affiché par LED sur le signal, puis
     rétablissement du signal une fois le coup confirmé ;
  9. unicité du signal malgré des événements `opponentGone` répétés
     (y compris plusieurs à 0 seconde) ;
 10. aucun signal « adversaire » après une réclamation réussie par
     l'utilisateur lui-même (victoire ou nulle) ;
  4. extinction complète au retour de l'adversaire même si la réclamation
     n'est jamais devenue possible (signal de départ seul).

Le point 8 (bonne moitié selon l'orientation, départ ET réclamable) est
couvert dans test_issue334_lichess_opponent_claim.py (constantes corrigées
partagées par les deux fichiers).
"""
import pytest

import nicsoft.core.config_manager as cm
from nicsoft.modes.lichess.game import _RANKS_1_4_LIT, _RANKS_5_6_LIT, _RANKS_5_8_LIT
from nicsoft.tests.test_issue309_lichess_l2a import FakeTransport, _ok
from nicsoft.tests.test_issue331_lichess_opponent_alerts import _AlertBoard, _make_game, _started
from nicsoft.tests.test_issue334_lichess_opponent_claim import _wait_double_beep


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg_file)
    return cfg_file


# ═══════════════════════════════════════════════════════════════════════
# 1. Signal de départ — une seule fois, pattern partiel, bip simple.
# ═══════════════════════════════════════════════════════════════════════

def test_signal_de_depart_une_seule_fois_meme_a_zero_seconde(isolated_config, monkeypatch):
    """Issue #340, point 9 (volet départ) : Lichess peut annoncer un délai
    déjà à 0 (ou très court) dès le premier événement — le signal de départ
    (distinct du signal réclamable) ne doit quand même être donné qu'une
    fois, pas une fois par événement répété."""
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 85})
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 80})
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 75})

    assert board.beep_count == 1
    assert board.all_leds_calls == [list(_RANKS_5_6_LIT)]
    assert game._opponent_gone_departure_signaled is True


# ═══════════════════════════════════════════════════════════════════════
# 9. Un seul signal « réclamable » par période, malgré des événements
#    répétés (y compris plusieurs à 0 seconde) — bug observé trois fois
#    de suite dans la partie réelle (06:04:41/42/47).
# ═══════════════════════════════════════════════════════════════════════

def test_signal_reclamable_une_seule_fois_malgre_evenements_repetes_a_zero(isolated_config, monkeypatch):
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    # Premier événement : délai déjà écoulé -> réclamable dès le départ.
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    assert game._opponent_gone_claimable is True
    _wait_double_beep()
    beep_after_first = board.beep_count
    leds_after_first = len(board.all_leds_calls)
    assert beep_after_first == 1 + 2  # 1 (départ) + 2 (réclamable, double)

    # Lichess répète l'événement « parti » à 0 seconde (observé en
    # pratique, toutes les ~5s) — AVANT cette correction, ceci remettait
    # _opponent_gone_claimable à False puis le repoussait à True au même
    # instant, ce qui redéclenchait le signal.
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    _wait_double_beep()

    assert board.beep_count == beep_after_first  # jamais un bip de plus
    assert len(board.all_leds_calls) == leds_after_first  # jamais une LED de plus
    assert game._opponent_gone_claimable is True


def test_signal_reclamable_une_seule_fois_decompte_qui_diminue_puis_zero_repete(isolated_config, monkeypatch):
    """Variante plus réaliste : le délai diminue d'abord normalement
    (85 -> 80 -> ... -> 5), puis Lichess envoie plusieurs événements à 0 de
    suite — un seul signal réclamable au total."""
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    for seconds in (20, 15, 10, 5):
        game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": seconds})
        assert game._opponent_gone_claimable is False
    # 1 seul signal de départ pour toute cette séquence (même période).
    assert board.beep_count == 1

    for _ in range(3):
        game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    _wait_double_beep()

    assert game._opponent_gone_claimable is True
    assert board.beep_count == 1 + 2  # départ (1) + réclamable (2, une seule fois)


def test_nouveau_depart_apres_retour_redeclenche_bien_le_signal(isolated_config, monkeypatch):
    """Issue #340, point 9 : « un nouveau départ après un retour de
    l'adversaire est une nouvelle période » — l'unicité ne doit jamais
    empêcher un VRAI second départ de signaler à nouveau."""
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 30})
    assert board.beep_count == 1
    game._handle_stream_event({"type": "opponentGone", "gone": False})
    assert game._opponent_gone_departure_signaled is False

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 30})
    assert board.beep_count == 2  # un nouveau bip de départ pour la nouvelle période


# ═══════════════════════════════════════════════════════════════════════
# 4. Extinction complète au retour de l'adversaire, même si la
#    réclamation n'est jamais devenue possible (signal de départ seul).
# ═══════════════════════════════════════════════════════════════════════

def test_retour_pendant_la_phase_depart_eteint_quand_meme_les_led(isolated_config, monkeypatch):
    """Avant cette issue, l'extinction au retour de l'adversaire n'avait
    lieu que si la réclamation était déjà devenue possible — la LED du
    simple signal de départ serait restée allumée indéfiniment si
    l'adversaire revenait avant ce délai."""
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 60})
    assert game._opponent_gone_claimable is False
    off_before = board.leds_off_count

    game._handle_stream_event({"type": "opponentGone", "gone": False})
    assert board.leds_off_count == off_before + 1
    assert game._opponent_gone_departure_signaled is False


# ═══════════════════════════════════════════════════════════════════════
# 5. Priorité au coup adverse affiché par LED — le signal est différé
#    pendant l'affichage, puis rétabli une fois le coup confirmé.
# ═══════════════════════════════════════════════════════════════════════

def test_coup_adverse_affiche_pendant_signal_actif_puis_signal_retabli(isolated_config, monkeypatch):
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 60})
    assert board.all_leds_calls  # signal de départ déjà affiché
    leds_calls_before = len(board.all_leds_calls)

    # Un coup adverse arrive à montrer par LED (set_led additif) — priorité
    # au coup : simulé directement comme le ferait _apply_new_moves.
    game._start_opponent_replication_wait("e7e5")
    assert game._awaiting_physical_replication is True
    # Aucune nouvelle pose de pattern complet pendant l'affichage du coup.
    assert len(board.all_leds_calls) == leds_calls_before

    # La position physique confirme le coup -> _check_replication éteint
    # ses LED puis doit rétablir le signal encore dû (toujours parti, pas
    # encore acquitté).
    game._replication_target_fen = game.board.board_fen()
    leds_off_before = board.leds_off_count
    game._check_replication(game.board.board_fen())
    # +1 pour effacer le coup (_check_replication), +1 pour la pose du
    # pattern rétabli (_set_opponent_alert_leds éteint avant de rallumer).
    assert board.leds_off_count == leds_off_before + 2
    assert len(board.all_leds_calls) == leds_calls_before + 1  # signal rétabli
    assert board.all_leds_calls[-1] == list(_RANKS_5_6_LIT)


def test_signal_devenant_du_pendant_coup_affiche_est_differe_puis_pose(isolated_config, monkeypatch):
    """Variante où la transition « réclamable » tombe PENDANT l'affichage
    du coup adverse : la LED complète ne doit apparaître qu'après, jamais
    pendant (priorité au coup)."""
    cm.save_config({"lichess_beep_opponent_move": True})
    board = _AlertBoard()
    game, client, events, _, _ = _make_game(monkeypatch, nl_inst=board)
    _started(game, "white", opponent_is_ai=False)

    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 30})
    leds_calls_before = len(board.all_leds_calls)

    game._start_opponent_replication_wait("e7e5")
    game._opponent_gone_ref_monotonic -= 30.0
    game._push_opponent_gone_state()  # devient réclamable ICI, pendant le coup affiché
    assert game._opponent_gone_claimable is True
    # Le bip n'est pas concerné par la priorité au coup (aucune ressource
    # LED partagée) — mais la LED complète ne doit pas être posée tout de
    # suite.
    assert len(board.all_leds_calls) == leds_calls_before

    game._replication_target_fen = game.board.board_fen()
    game._check_replication(game.board.board_fen())
    assert board.all_leds_calls[-1] == list(_RANKS_5_8_LIT)  # pattern complet, rétabli après le coup


# ═══════════════════════════════════════════════════════════════════════
# 10. Aucun signal « adversaire » après une réclamation réussie par
#     l'utilisateur lui-même.
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("atype,client_attr,status", [
    ("lichess_claim_victory", "claim_victory", "timeout"),
    ("lichess_claim_draw", "claim_draw", "draw"),
])
def test_reclamation_reussie_par_l_utilisateur_n_alerte_pas(isolated_config, monkeypatch, atype, client_attr, status):
    board = _AlertBoard()
    game, client, events, _, actions = _make_game(
        monkeypatch, nl_inst=board, transport=FakeTransport(requests=[_ok({"ok": True})]),
    )
    _started(game, "white", opponent_is_ai=False)
    game._handle_stream_event({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0})
    assert game._opponent_gone_claimable is True
    leds_off_before = board.leds_off_count
    beep_count_before = board.beep_count

    actions.put({"type": atype})
    game._process_browser_actions()
    assert game._user_initiated_end is True  # issue #340, point 10

    # Le flux confirme ensuite la fin de partie (même statut que si
    # l'adversaire avait lui-même provoqué la fin — Lichess ne distingue
    # pas la cause dans le statut brut).
    game._apply_game_state({"status": status, "moves": "", "winner": "white"})
    game._finalize()

    assert game.opponent_caused_end is False
    game_over = events_last(events, "game_over")
    assert game_over["opponent_caused_end"] is False
    assert game_over["opponent_cause_key"] is None
    # Les LED encore allumées (signal réclamable) sont éteintes, aucun
    # nouveau signal « fin de partie adversaire » n'est posé.
    assert board.leds_off_count == leds_off_before + 1
    assert board.beep_count == beep_count_before  # aucun bip supplémentaire


def events_last(events, etype):
    matches = [d for t, d in events if t == etype]
    return matches[-1] if matches else None
