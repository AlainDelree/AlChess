"""
nicsoft/tests/test_issue383_point3_orphan_game.py — AlChess

Issue #383, point 3 (étude #382) : risque NON ÉTABLI par l'étude (aucune
reproduction réelle) mais CONFIRMÉ par lecture du code — course
structurelle entre les deux fils de `SeekSession` (seek.py). Le fil de
lecture du flux d'évènements marque une recherche "trouvée"
(`_mark_found()`) indépendamment de `_cancelled` ; si ce marquage arrive
juste avant que le fil principal ne traite une demande de retour au menu,
`cancel()` devient un no-op et l'évènement "found" reste dans la file sans
jamais être consommé — la partie existe chez Lichess mais personne ne la
joue, et un adversaire pourrait attendre indéfiniment.

Correction : `_cancel_seek_and_reap_orphan()` (game_manager_modes/lichess.py)
draine la file pendant une courte fenêtre bornée après `cancel()` ; si un
"found" tardif apparaît, `_abandon_orphan_game_after_cancel()` annule
immédiatement la partie côté Lichess (abort(), puis resign() en repli) —
même mécanisme "moins de 2 coups" que `abandon_lichess_game` (issue #325).

Règle absolue de cette issue : AUCUNE connexion réseau réelle, AUCUNE
recherche/partie réelle sur lichess.org — entièrement doublé (voir
test_issue327/test_issue328 pour les mêmes conventions de double).
"""
import logging

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.seek as seek_module
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.errors import LichessApiError
from nicsoft.tests.test_issue311_lichess_sequencing import INITIAL_FEN_W, _ScriptedBoard


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ═══════════════════════════════════════════════════════════════════════
# 1. Helpers isolés — aucune dépendance au lanceur complet.
# ═══════════════════════════════════════════════════════════════════════

class _ScriptedEventsSeekSession:
    """Double minimal de SeekSession pour tester _reap_late_found_game en
    isolation — une file d'évènements déjà préparée, aucun vrai fil."""

    def __init__(self, events):
        self._events = list(events)

    def next_event(self, timeout=0.2):
        return self._events.pop(0) if self._events else None


def test_reap_late_found_game_retourne_le_jeu_si_present_dans_la_file():
    session = _ScriptedEventsSeekSession([
        {"type": "waiting"},
        {"type": "found", "game": {"id": "orphan1"}},
    ])
    game = lichess_launcher._reap_late_found_game(session)
    assert game == {"id": "orphan1"}


def test_reap_late_found_game_retourne_none_si_rien_narrive():
    session = _ScriptedEventsSeekSession([])
    game = lichess_launcher._reap_late_found_game(session)
    assert game is None


class _TrackingAbortClient:
    def __init__(self, abort_exc=None):
        self.aborted = []
        self.resigned = []
        self._abort_exc = abort_exc

    def abort(self, game_id):
        if self._abort_exc is not None:
            raise self._abort_exc
        self.aborted.append(game_id)

    def resign(self, game_id):
        self.resigned.append(game_id)


def test_abandon_orphan_game_appelle_abort(caplog):
    client = _TrackingAbortClient()
    with caplog.at_level(logging.ERROR, logger="niclink.lichess"):
        lichess_launcher._abandon_orphan_game_after_cancel(client, {"id": "orphan1"})
    assert client.aborted == ["orphan1"]
    assert client.resigned == []
    assert any("orphan1" in r.message for r in caplog.records)


def test_abandon_orphan_game_replie_sur_resign_si_abort_refuse():
    client = _TrackingAbortClient(abort_exc=LichessApiError("refusé"))
    lichess_launcher._abandon_orphan_game_after_cancel(client, {"gameId": "orphan2"})
    assert client.resigned == ["orphan2"]


def test_abandon_orphan_game_sans_identifiant_najoute_aucun_appel():
    client = _TrackingAbortClient()
    lichess_launcher._abandon_orphan_game_after_cancel(client, {})
    assert client.aborted == []
    assert client.resigned == []


# ═══════════════════════════════════════════════════════════════════════
# 2. Bout en bout — _run_lichess_human() : un "found" arrivé après que
#    l'utilisateur a demandé le retour au menu ne doit jamais rester
#    orphelin chez Lichess.
# ═══════════════════════════════════════════════════════════════════════

class _RacingSeekSessionDouble:
    """Reproduit la course réelle de SeekSession sans aucun vrai fil :
    cancel() est un no-op du point de vue applicatif (comme le vrai
    SeekSession quand _found est déjà vrai) mais l'évènement "found" — déjà
    lu par "l'autre fil" avant que cancel() ne soit traité — n'apparaît
    dans la file qu'à cet instant précis, pour simuler de façon
    déterministe la fenêtre de course décrite dans l'en-tête de ce
    fichier."""

    def __init__(self, client, game_log=None):
        self.cancel_called = False
        self.close_called = False
        self._events = [{"type": "waiting"}]
        self._orphan_found_event = {
            "type": "found",
            "game": {"id": "orphan_human_1", "color": "white", "opponent": {"username": "Bob"}},
        }

    def start(self, *a, **kw):
        pass

    def next_event(self, timeout=0.2):
        return self._events.pop(0) if self._events else None

    def cancel(self):
        self.cancel_called = True
        self._events.append(self._orphan_found_event)

    def close(self):
        self.close_called = True


class _NonRacingSeekSessionDouble(_RacingSeekSessionDouble):
    """Variante de contrôle : cancel() normal, jamais de "found" tardif —
    garde-fou contre une régression qui annulerait une partie à chaque
    sortie menu, même sans course réelle."""

    def cancel(self):
        self.cancel_called = True


class _TrackingHumanClient:
    def __init__(self):
        self.aborted = []
        self.resigned = []
        self._game_log = None

    def attach_game_log(self, game_log):
        self._game_log = game_log

    def abort(self, game_id):
        self.aborted.append(game_id)

    def resign(self, game_id):
        self.resigned.append(game_id)


def _patch_human_launch_basics(monkeypatch, client):
    board = _ScriptedBoard([INITIAL_FEN_W])
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    calls = {"n": 0}

    def _get_app_state():
        calls["n"] += 1
        # 1er appel : _wait_initial_position_lichess (position déjà initiale,
        # jamais "menu"). 2e appel : premier passage de la boucle de
        # recherche (jamais "menu", laisse next_event() être consommé une
        # fois). À partir du 3e : "menu" — retour au menu demandé par
        # l'utilisateur ("Annuler la recherche").
        return "menu" if calls["n"] >= 3 else "connecting"

    monkeypatch.setattr(lichess_launcher, "get_app_state", _get_app_state)
    return board


def test_partie_trouvee_apres_annulation_est_annulee_cote_lichess(monkeypatch, caplog):
    client = _TrackingHumanClient()
    _patch_human_launch_basics(monkeypatch, client)
    monkeypatch.setattr(seek_module, "SeekSession", _RacingSeekSessionDouble)

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    with caplog.at_level(logging.ERROR, logger="niclink.lichess"):
        lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert client.aborted == ["orphan_human_1"], (
        "la partie trouvée après l'annulation de la recherche n'a pas été annulée côté Lichess"
    )
    assert client.resigned == []
    # Retour au menu silencieux du point de vue utilisateur — l'annulation
    # est volontaire, jamais un message d'erreur pour ce cas.
    assert _error["occurred"] is False
    assert any("orphan_human_1" in r.message for r in caplog.records)


def test_annulation_normale_sans_partie_trouvee_najoute_aucun_abort(monkeypatch):
    """Garde-fou de non-régression : une annulation ordinaire (aucun
    "found" tardif) ne doit jamais déclencher abort()/resign()."""
    client = _TrackingHumanClient()
    _patch_human_launch_basics(monkeypatch, client)
    monkeypatch.setattr(seek_module, "SeekSession", _NonRacingSeekSessionDouble)

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert client.aborted == []
    assert client.resigned == []
    assert _error["occurred"] is False
