"""
nicsoft/tests/test_issue368_lichess_game_network_loss.py — AlChess

Issue #368, partie 2 : perte de connexion en pleine partie Lichess
(inspection bornée au code existant, `nicsoft/modes/lichess/game.py` et
`game_client.py`).

Constat (détail dans le rapport de clôture) :
  - Flux de partie (lecture des coups adverses, pendules...) : déjà bien
    géré, INCHANGÉ ici — `GameClient.stream_game()` reprend automatiquement
    avec des attentes croissantes (RECONNECT_DELAYS_S, déjà testé par
    test_issue307_lichess_l1.py::test_stream_game_coupure_puis_reprise_*),
    et `LichessGame` affiche un bandeau PERMANENT dédié
    ("lichess-reconnecting-banner", piloté par les évènements
    "lichess_reconnecting"/"lichess_reconnected") tant que la reconnexion
    n'a pas réussi — jamais testé jusqu'ici à ce niveau (bout en bout,
    LichessGame complet) : couvert par ce fichier.
  - Coup physique envoyé pendant une coupure (_submit_move) : jamais perdu
    (le coup reste détecté comme non confirmé à chaque tick suivant,
    ~50ms, et donc réessayé automatiquement sans action de l'utilisateur
    tant que self.board ne reflète pas encore le coup) ni dupliqué (un
    double envoi accidentel est rejeté par Lichess avec le même message
    ambigu déjà traité sans fausse alarme par _handle_move_rejected). Bug
    RÉEL corrigé par cette issue : le toast persistant « réseau
    indisponible » affiché par _submit_move/_safe_client_call/
    _safe_claim_call/_safe_draw_offer_call ne disparaissait jamais tout
    seul au retour du réseau — corrigé par _report_network_error()/
    _clear_network_error_if_active() (ce fichier teste cette correction).
  - Fin de partie pendant/après une coupure : aucun changement nécessaire,
    déjà couvert par les tests existants de fin de partie (_finalize) —
    non retesté ici.
  - Faux « coup refusé » (réponse HTTP perdue après un envoi en fait
    accepté) : documenté ci-dessous comme « gap connu » jusqu'à l'issue
    #377, qui l'a corrigé (_handle_move_rejected::_move_already_applied) —
    voir test_double_envoi_apres_reponse_perdue_confirmee_pendant_la_relecture_najamais_de_faux_refus
    et test_vrai_refus_apres_relecture_sans_confirmation_affiche_toujours_lerreur
    ci-dessous.

Entièrement sans réseau (FakeTransport) et sans matériel (FakeBoard), sur
le même modèle que test_issue309_lichess_l2a.py.
"""
import json
import queue

import chess
import pytest

import nicsoft.modes.lichess.game as game_mod
from nicsoft.modes.lichess.errors import LichessNetworkError
from nicsoft.modes.lichess.game import LichessGame
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.transport import TransportNetworkError


# ── Doubles de test (mêmes contrats que test_issue309_lichess_l2a.py) ──────

class FakeStreamHandle:
    def __init__(self, lines):
        self._lines = list(lines)
        self.closed = False

    def close(self):
        self.closed = True

    def lines(self):
        for item in self._lines:
            if self.closed:
                return
            if isinstance(item, Exception):
                raise item
            yield item


class FakeTransport:
    """Même contrat que test_issue307/test_issue309 — jamais de connexion
    réelle. `stream_batches` : listes de lignes (ou Exception, levée AU
    FIL de la lecture — c'est précisément ce que coupe un faux client qui
    simule une coupure réseau en cours de partie) consommées dans l'ordre
    à chaque appel de `stream_lines`."""

    def __init__(self, requests=None, stream_batches=None):
        self._requests = list(requests or [])
        self._stream_batches = list(stream_batches or [])

    def request(self, method, url, token, fields=None):
        handler = self._requests.pop(0)
        result = handler(method, url, token, fields)
        if isinstance(result, Exception):
            raise result
        return result

    def stream_lines(self, url, token):
        batch = self._stream_batches.pop(0)
        for item in batch:
            if isinstance(item, Exception):
                raise item
            yield item

    def open_stream(self, method, url, token, fields=None):
        raise AssertionError("open_stream non attendu dans ces tests")


class FakeBoard:
    def __init__(self, initial_fen=chess.STARTING_BOARD_FEN):
        self.current_fen = initial_fen + " w - - 0 1"
        self.led_calls = []
        self.leds_off_count = 0

    def set_led(self, square, status):
        self.led_calls.append((square, status))

    def turn_off_all_leds(self):
        self.leds_off_count += 1

    def signal_lights(self, sig):
        pass

    def beep(self):
        pass

    def disconnect(self):
        pass


def _line(d):
    return json.dumps(d)


def _make_recorder(monkeypatch):
    events = []
    actions = queue.Queue()

    def fake_send_event(event_type, data):
        events.append((event_type, data))

    def fake_get_action(timeout=0.0):
        try:
            return actions.get(timeout=timeout)
        except queue.Empty:
            return None

    monkeypatch.setattr(game_mod, "send_event", fake_send_event)
    monkeypatch.setattr(game_mod, "set_app_state", lambda *a, **k: None)
    monkeypatch.setattr(game_mod, "get_action", fake_get_action)
    return events, actions


def _events_of(events, etype):
    return [d for t, d in events if t == etype]


def _make_game(transport, nl_inst=None, **kwargs):
    nl_inst = nl_inst or FakeBoard()
    client = GameClient("lip_test_token", transport=transport)
    game = LichessGame(
        nl_inst, client, kwargs.pop("game_id", "gid1"),
        level=kwargs.pop("level", 1), player_name=kwargs.pop("player_name", "Alain"),
        clock_limit_s=kwargs.pop("clock_limit_s", 900), clock_increment_s=kwargs.pop("clock_increment_s", 10),
        **kwargs,
    )
    return game, client


# ═══════════════════════════════════════════════════════════════════════
# 1. Coup physique pendant une coupure réseau : ni perdu, ni dupliqué —
#    retry automatique au tick suivant, toast d'erreur puis de
#    rétablissement (correction de cette issue).
# ═══════════════════════════════════════════════════════════════════════

def test_coup_physique_en_coupure_affiche_erreur_persistante_puis_se_retablit(monkeypatch):
    """Simule exactement le scénario demandé : un faux client dont
    play_move() échoue une fois (réseau coupé) puis réussit (réseau
    revenu, l'utilisateur n'a rien eu à refaire)."""
    events, _actions = _make_recorder(monkeypatch)
    game, client = _make_game(FakeTransport())

    attempts = []

    def fake_play_move(game_id, uci, offer_draw=False):
        attempts.append(uci)
        if len(attempts) == 1:
            raise LichessNetworkError("coupure simulée par le faux client")
        return None  # succès au second essai (réseau revenu)

    monkeypatch.setattr(client, "play_move", fake_play_move)

    # Premier essai : échoue (réseau coupé) — toast persistant affiché,
    # AUCUN plantage, le coup n'est PAS appliqué à self.board (attendu : il
    # ne revient que confirmé par le flux).
    game._submit_move("e2e4")
    toasts = _events_of(events, "lichess_toast")
    assert len(toasts) == 1
    assert toasts[0]["message_key"] == "lichess.erreur_reseau"
    assert toasts[0]["persistent"] is True
    assert game.board.fen().split()[0] == chess.STARTING_BOARD_FEN  # inchangé

    # Le tick suivant (~50ms plus tard, _check_user_move) détecterait le
    # même coup physique toujours non confirmé et réessaierait — simulé
    # ici directement par un second appel à _submit_move avec le MÊME uci,
    # sans aucune action supplémentaire de l'utilisateur.
    game._submit_move("e2e4")
    assert attempts == ["e2e4", "e2e4"]  # jamais deux coups différents envoyés par erreur

    toasts = _events_of(events, "lichess_toast")
    assert len(toasts) == 2
    # Le second toast REMPLACE le premier par un message de rétablissement
    # — c'est la correction de cette issue (avant : le toast d'erreur
    # restait affiché indéfiniment, même après un envoi réussi).
    assert toasts[1]["message_key"] == "lichess.erreur_reseau_retablie"
    assert toasts[1].get("persistent") is not True


def test_coup_physique_reussi_sans_coupure_najamais_toast_de_retablissement(monkeypatch):
    """Non-régression : si aucune erreur réseau n'a eu lieu, un envoi
    réussi ne déclenche jamais le toast de rétablissement (rien à
    rétablir)."""
    events, _actions = _make_recorder(monkeypatch)
    game, client = _make_game(FakeTransport())
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)

    game._submit_move("e2e4")

    assert _events_of(events, "lichess_toast") == []


def test_double_envoi_apres_reponse_perdue_confirmee_pendant_la_relecture_najamais_de_faux_refus(monkeypatch):
    """Issue #377, point 2 (suite de #368) — correction du « gap connu »
    documenté auparavant ici : si la réponse HTTP d'un coup en fait accepté
    par Lichess se perd (coupure juste après l'envoi), le coup est réessayé
    avec le même uci ; Lichess refuse ce second essai (déjà son tour) avec
    le message ambigu HTTP 400. Si le flux confirme ce même coup PENDANT la
    relecture bornée (AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S) — ici simulé en
    plaçant directement le coup déjà appliqué à self.board et son auteur
    avant l'appel, comme le ferait _apply_new_moves en traitant un
    événement du flux déjà en route — aucun message d'erreur ni aucune
    demande de remettre la pièce en place ne doit s'afficher : succès
    silencieux, le coup n'est pas perdu."""
    import chess as _chess
    from nicsoft.modes.lichess.errors import LichessApiError
    events, _actions = _make_recorder(monkeypatch)
    game, client = _make_game(FakeTransport())
    monkeypatch.setattr(game, "AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S", 0.05)  # délai réel réduit, test rapide
    game.user_color = "white"

    def fake_play_move(game_id, uci, offer_draw=False):
        raise LichessApiError(400, "Not your turn, or game already over")

    monkeypatch.setattr(client, "play_move", fake_play_move)

    def fake_drain(timeout_s):
        # Simule le flux confirmant notre coup pendant la relecture bornée
        # (comme le ferait un vrai gameState traité par _apply_new_moves).
        game.board.push(_chess.Move.from_uci("e2e4"))
        game._last_move_mover_color = "white"

    monkeypatch.setattr(game, "_drain_pending_stream_events", fake_drain)

    game._submit_move("e2e4")

    assert _events_of(events, "lichess_move_refused") == []
    assert game.board.move_stack[-1].uci() == "e2e4"


def test_vrai_refus_apres_relecture_sans_confirmation_affiche_toujours_lerreur(monkeypatch):
    """Non-régression de la correction ci-dessus : si la relecture bornée
    ne confirme JAMAIS notre coup (ni une fin de partie) — vrai refus,
    position réellement désynchronisée ou coup réellement illégal — le
    comportement existant reste inchangé : message d'erreur affiché,
    remise en place physique demandée."""
    from nicsoft.modes.lichess.errors import LichessApiError
    events, _actions = _make_recorder(monkeypatch)
    game, client = _make_game(FakeTransport())
    monkeypatch.setattr(game, "AMBIGUOUS_ERROR_REQUERY_TIMEOUT_S", 0.05)  # délai réel réduit, test rapide
    game.user_color = "white"

    def fake_play_move(game_id, uci, offer_draw=False):
        raise LichessApiError(400, "Not your turn, or game already over")

    monkeypatch.setattr(client, "play_move", fake_play_move)

    game._submit_move("e2e4")

    refused = _events_of(events, "lichess_move_refused")
    assert len(refused) == 1
    assert game._awaiting_piece_reset is True
    assert game.board.move_stack == []


# ═══════════════════════════════════════════════════════════════════════
# 2. Flux de partie coupé puis reconnecté — bout en bout (LichessGame
#    complet, pas seulement le générateur stream_game isolé) : bandeau
#    permanent affiché puis masqué, jamais d'abandon automatique, jamais
#    de coup perdu ou rejoué pendant la coupure.
# ═══════════════════════════════════════════════════════════════════════

def test_flux_coupe_puis_reconnecte_affiche_bandeau_permanent_puis_le_masque(monkeypatch):
    """Jamais vérifié avant cette issue (voir l'énoncé) : le flux complet
    gameFull → coupure → reconnexion → gameState, lu par LichessGame via
    son fil de lecture dédié (_stream_reader_loop/_stream_event_queue),
    produit bien les évènements "lichess_reconnecting" puis
    "lichess_reconnected" — jamais un abandon automatique, jamais la
    partie marquée terminée par la seule coupure."""
    events, _actions = _make_recorder(monkeypatch)
    # Deux lots : le premier s'interrompt par une coupure réseau en plein
    # milieu (après le gameFull) — stream_game() rappelle alors
    # stream_lines() pour la reprise, qui consomme le second lot.
    transport = FakeTransport(stream_batches=[
        [
            _line({
                "type": "gameFull", "id": "gid1", "rated": False,
                "white": {"aiLevel": 1}, "black": {"name": "Alain"},
                "state": {"status": "started", "moves": ""},
            }),
            TransportNetworkError("coupure simulée"),
        ],
        [_line({"type": "gameState", "status": "started", "moves": "e2e4"})],
    ])
    game, _client = _make_game(transport, known_user_color="black")

    game._stream_reader_loop()  # exécuté en synchrone ici (pas de vrai fil) — même méthode que le fil réel
    # _stream_reader_loop ne fait que remplir la file (comme le vrai fil) —
    # _main_loop est ce qui la dépile normalement ; reproduit ici pour
    # vérifier ce que LichessGame complet afficherait réellement. S'arrête
    # dès "reconnected" vu : la suite (fermeture normale du flux factice,
    # qui ne fournit qu'une seule ligne après la reprise) est un artefact
    # du test, pas le scénario vérifié ici.
    seen_reconnected = False
    while not seen_reconnected:
        try:
            event = game._stream_event_queue.get_nowait()
        except queue.Empty:
            break
        if event.get("type") == "_stream_closed":
            break
        game._handle_stream_event(event)
        if event.get("type") == "reconnected":
            seen_reconnected = True

    types = [t for t, _ in events]
    assert "lichess_reconnecting" in types
    assert "lichess_reconnected" in types
    # L'ordre doit respecter : reconnecting AVANT reconnected (jamais l'inverse).
    assert types.index("lichess_reconnecting") < types.index("lichess_reconnected")
    # Jamais d'abandon ni de fin de partie provoqués par la seule coupure réseau
    # (vérifié juste après la reconnexion, avant la fermeture normale du
    # flux factice qui suit dans ce scénario de test).
    assert game.game_over is False
    assert game._status != "unknownFinish"


def test_flux_qui_echoue_definitivement_signale_erreur_reseau_persistante_et_termine(monkeypatch):
    """Si le flux finit par s'arrêter en erreur (toutes les tentatives de
    stream_game elles-mêmes épuisées avant que le statut ne soit confirmé
    terminé — cas théorique, RECONNECT_DELAYS_S n'a en pratique pas de
    limite de tentatives), LichessGame affiche le toast persistant réseau
    (inchangé) et termine proprement la partie (statut "unknownFinish"),
    sans jamais planter."""
    from nicsoft.modes.lichess.errors import LichessNetworkError as _LNE
    events, _actions = _make_recorder(monkeypatch)
    game, _client = _make_game(FakeTransport())
    game._stream_error = _LNE("flux définitivement perdu")
    game._status = "started"

    game._handle_stream_closed()

    toasts = _events_of(events, "lichess_toast")
    assert toasts and toasts[-1]["persistent"] is True
    assert toasts[-1]["message_key"] == "lichess.erreur_reseau"
    assert game.game_over is True
    assert game._status == "unknownFinish"
