"""
nicsoft/tests/test_issue318_lichess_draw_refusal.py — AlChess

Issue #318 : lors d'un essai réel (12 novembre 2026), une offre de nulle
envoyée avec le coup (issue #316) déclenchait malgré tout un faux refus dans
la même seconde que la confirmation de notre propre coup par Lichess —
avant que l'adversaire ait eu l'occasion de répondre. Cause mesurée dans ce
dépôt (voir rapport de clôture pour le détail de la lecture du source
lichess-org/lila et de la spec lichess-org/api) : rien n'empêchait
auparavant un simple écho de gameState contenant NOTRE PROPRE coup tout
juste envoyé d'être interprété comme un changement d'état déclenchant le
refus.

Correction dans LichessGame._apply_new_moves()/._apply_game_state()
(nicsoft/modes/lichess/game.py) : une offre de nulle de l'utilisateur n'est
désormais jamais considérée comme refusée sauf si l'adversaire a joué un
coup après l'offre sans l'avoir acceptée (seul signal fiable disponible via
le flux Board API — voir rapport : aucun signal de refus explicite distinct
n'existe dans gameState pour ce cas). Un changement d'état provoqué par le
coup de l'utilisateur lui-même (y compris l'écho de ce coup par Lichess)
n'est jamais compté comme un refus, et le journal (niveau INFO) indique
désormais, pour chaque coup envoyé, si l'offre y était jointe, et pour
chaque état reçu, le statut, le nombre de coups et les deux indicateurs de
nulle bruts (rien de secret).

Entièrement sans réseau ni matériel, comme les autres tests du mode
Lichess (faux transport/client, faux plateau, événements simulés).
"""
import logging

import chess

from nicsoft.tests.test_issue311_lichess_sequencing import _make_bare_game


def _started_white(game, client, monkeypatch):
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": ""},
    })
    assert game.user_color == "white"
    assert game.board.turn == chess.WHITE


# ═══════════════════════════════════════════════════════════════════════
# 1. Offre puis coup de l'utilisateur : jamais de faux refus, même si
#    l'écho du coup montre déjà un indicateur de nulle à False.
# ═══════════════════════════════════════════════════════════════════════

def test_echo_du_propre_coup_sans_indicateur_ne_declenche_pas_de_refus(monkeypatch, caplog):
    """Reproduit exactement le scénario réel rapporté : l'état reçu juste
    après notre propre coup (c4c5) montre déjà wdraw=False — ce n'était
    pas mesuré avant l'issue #318, c'est maintenant une hypothèse que le
    code ne doit plus jamais traiter comme un refus."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True

    game._submit_move("c2c4")
    assert game._my_draw_offer_pending is True

    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        # Écho de notre propre coup : wdraw déjà retombé à False, comme
        # observé en situation réelle — ne doit PAS être un refus.
        game._apply_game_state({"status": "started", "moves": "c2c4", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is True
    assert ("lichess_draw_refused", {}) not in events

    # Seule la réponse réelle de l'adversaire (son propre coup, sans avoir
    # accepté) doit déclencher le refus.
    game._apply_game_state({"status": "started", "moves": "c2c4 g7g6", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_refused", {}) in events


def test_offre_puis_coup_sans_refus_affiche_meme_sur_plusieurs_coups(monkeypatch):
    """Le refus ne doit pas apparaître après le coup suivant de
    l'utilisateur non plus — tant que l'adversaire n'a pas répondu, l'offre
    reste en attente, y compris à travers un deuxième coup propre si (pour
    une raison quelconque) l'adversaire n'a toujours pas joué."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()

    game._submit_move("c2c4")
    game._apply_game_state({"status": "started", "moves": "c2c4", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is True
    assert ("lichess_draw_refused", {}) not in events


# ═══════════════════════════════════════════════════════════════════════
# 2. Coup de l'adversaire sans acceptation = refus réel.
# ═══════════════════════════════════════════════════════════════════════

def test_coup_adversaire_sans_acceptation_est_un_refus(monkeypatch):
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    game._submit_move("e2e4")
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": True, "bdraw": False})
    assert game._my_draw_offer_pending is True

    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_refused", {}) in events


# ═══════════════════════════════════════════════════════════════════════
# 3. Acceptation de l'adversaire : jamais traitée comme un refus.
# ═══════════════════════════════════════════════════════════════════════

def test_acceptation_par_l_adversaire_n_est_jamais_un_refus(monkeypatch):
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True

    game._apply_game_state({"status": "draw", "moves": "", "wdraw": True, "bdraw": True, "winner": ""})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_accepted", {}) in events
    assert ("lichess_draw_refused", {}) not in events


# ═══════════════════════════════════════════════════════════════════════
# 4. Offre de l'adversaire : comportement inchangé par cette correction.
# ═══════════════════════════════════════════════════════════════════════

def test_offre_de_l_adversaire_toujours_signalee_normalement(monkeypatch):
    game, events, _, _ = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)

    game._apply_game_state({"status": "started", "moves": "", "bdraw": True})
    assert game._draw_offered_by_opponent is True
    assert ("lichess_draw_offered", {"offered": True}) in events

    # Notre propre coup suivant ne doit pas faire disparaître ce signal
    # tant que Lichess ne le retire pas lui-même.
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)
    game._submit_move("e2e4")
    game._apply_game_state({"status": "started", "moves": "e2e4", "bdraw": True})
    assert game._draw_offered_by_opponent is True


# ═══════════════════════════════════════════════════════════════════════
# 5. Journal de diagnostic (niveau INFO) — rien de secret.
# ═══════════════════════════════════════════════════════════════════════

def test_journal_indique_si_l_offre_est_jointe_au_coup(monkeypatch, caplog):
    game, _, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()

    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        game._submit_move("e2e4")
    joined = [r.message for r in caplog.records if "coup envoyé" in r.getMessage()]
    assert joined, "aucune ligne de journal pour le coup envoyé"
    assert "offre_nulle_jointe=True" in caplog.records[-1].getMessage()


def test_journal_indique_les_deux_indicateurs_de_nulle_le_statut_et_les_coups(monkeypatch, caplog):
    game, _, _, _ = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)

    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": True, "bdraw": False})
    lines = [r.getMessage() for r in caplog.records if "état reçu" in r.getMessage()]
    assert lines, "aucune ligne de journal pour l'état reçu"
    line = lines[-1]
    assert "coups=1" in line
    assert "statut=started" in line
    assert "wdraw=True" in line
    assert "bdraw=False" in line


def test_journal_etat_recu_ne_contient_aucun_jeton(monkeypatch, caplog):
    """Garde-fou (consigne projet) : le journal de diagnostic ne doit
    jamais faire fuiter le jeton Lichess, même indirectement."""
    game, _, _, _ = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)

    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": True, "bdraw": False})
    for record in caplog.records:
        assert "lip_test" not in record.getMessage()
