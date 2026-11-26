"""
nicsoft/tests/test_issue392_point2_orphan_sweep.py — AlChess

Issue #392, point 2 (étude #391, point 2) : essai réel du 26/11/2026—
recherche d'adversaire classée annulée après ~2s. Lichess avait quand même
créé une partie classée, 21ms avant la fermeture du flux de recherche et
22ms avant l'annulation effective — mais le flux n'a JAMAIS signalé
"found" (seulement la fermeture, "seek_closed"), donc la récupération de
partie orpheline étroite de #383 point 3 (_reap_late_found_game, fenêtre
de 1s qui draine un "found" DÉJÀ DANS LA FILE) n'avait rien à drainer. Une
vraie partie classée est restée ouverte chez Lichess, jamais jouée par
personne — Alain l'a reprise plus tard via le bandeau de reprise, l'a
jouée et perdue.

Correction : un balayage ÉLARGI (_start_orphan_sweep_after_cancel/
_orphan_sweep_worker, game_manager_modes/lichess.py), démarré en
arrière-plan à chaque annulation de recherche humaine, revérifie la liste
des parties en cours à quelques reprises espacées (1/2/4/6s,
_ORPHAN_SWEEP_CHECKPOINTS_S) — toute partie dont l'identifiant n'était PAS
dans la liste mémorisée juste avant la recherche (`pre_search_game_ids`)
et qui compte moins de 2 demi-coups est annulée (abort(), jamais
resign()).

Règle absolue de ce fichier : AUCUNE connexion réseau réelle, AUCUNE
recherche/partie réelle sur lichess.org — entièrement doublé.
"""
import logging
import threading
import time

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
    lichess_launcher._lichess_launch_generation = 0
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    lichess_launcher._lichess_launch_generation = 0


# ═══════════════════════════════════════════════════════════════════════
# 1. Fonctions pures isolées.
# ═══════════════════════════════════════════════════════════════════════

def test_ply_count_from_fen_position_initiale():
    assert lichess_launcher._ply_count_from_fen(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    ) == 0


def test_ply_count_from_fen_un_demi_coup():
    assert lichess_launcher._ply_count_from_fen(
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    ) == 1


def test_ply_count_from_fen_deux_demi_coups():
    assert lichess_launcher._ply_count_from_fen(
        "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    ) == 2


def test_ply_count_from_fen_absent_ou_malforme_renvoie_none():
    assert lichess_launcher._ply_count_from_fen("") is None
    assert lichess_launcher._ply_count_from_fen("pas un fen") is None


def test_generation_counter_augmente_a_chaque_appel():
    g1 = lichess_launcher._bump_launch_generation()
    g2 = lichess_launcher._bump_launch_generation()
    assert g2 == g1 + 1
    assert lichess_launcher._current_launch_generation() == g2


# ═══════════════════════════════════════════════════════════════════════
# 2. _orphan_sweep_worker / _start_orphan_sweep_after_cancel — isolés,
#    checkpoints réduits pour rester rapides.
# ═══════════════════════════════════════════════════════════════════════

class _TrackingSweepClient:
    def __init__(self, abort_exc=None):
        self.aborted = []
        self._abort_exc = abort_exc

    def abort(self, game_id):
        if self._abort_exc is not None:
            raise self._abort_exc
        self.aborted.append(game_id)


def _run_sweep_sync(monkeypatch, fetch_results, pre_search_game_ids, generation=None,
                     abort_exc=None, checkpoints=(0.01, 0.01, 0.01)):
    """Exécute _orphan_sweep_worker directement (pas de vrai fil) avec une
    liste de résultats scriptés pour chaque checkpoint (un par appel de
    _fetch_ongoing_games). `generation` par défaut = génération courante
    (aucun nouveau lancement entre-temps)."""
    if generation is None:
        generation = lichess_launcher._current_launch_generation()
    monkeypatch.setattr(lichess_launcher, "_ORPHAN_SWEEP_CHECKPOINTS_S", checkpoints)
    client = _TrackingSweepClient(abort_exc=abort_exc)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    calls = {"n": 0}

    def _fake_fetch(token):
        idx = calls["n"]
        calls["n"] += 1
        return fetch_results[idx] if idx < len(fetch_results) else fetch_results[-1]

    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", _fake_fetch)
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda t, d: events.append((t, d)))

    lichess_launcher._orphan_sweep_worker("lip_x", pre_search_game_ids, generation)
    return client, events


def test_partie_apparue_dans_la_liste_moins_de_2_demi_coups_est_annulee(monkeypatch):
    """Scénario exact de l'étude #391, point 2 : seulement "seek_closed",
    aucune partie annoncée, annulation immédiate — la partie née de cette
    recherche (jamais dans la liste mémorisée avant) est annulée."""
    client, events = _run_sweep_sync(
        monkeypatch,
        fetch_results=[[{
            "game_id": "orphan_classee_1",
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        }]],
        pre_search_game_ids=frozenset(),
    )
    assert client.aborted == ["orphan_classee_1"]
    toasts = [d for t, d in events if t == "lichess_toast"]
    assert any(d["message_key"] == "toast.lichess_orphan_game_annulee" for d in toasts)


def test_partie_preexistante_jamais_touchee(monkeypatch):
    """Une partie présente AVANT la recherche (même identifiant dans
    pre_search_game_ids) n'est jamais annulée, quel que soit son nombre de
    coups — comparaison toujours par identifiant."""
    client, _events = _run_sweep_sync(
        monkeypatch,
        fetch_results=[[{
            "game_id": "deja_en_cours",
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        }]],
        pre_search_game_ids=frozenset({"deja_en_cours"}),
    )
    assert client.aborted == []


def test_partie_avec_deux_demi_coups_ou_plus_jamais_abandonnee(monkeypatch):
    """Une partie née de la recherche mais déjà avancée (>= 2 demi-coups —
    donc clairement jouée, pas la partie fraîchement créée observée dans
    l'étude #391) n'est jamais annulée automatiquement."""
    client, _events = _run_sweep_sync(
        monkeypatch,
        fetch_results=[[{
            "game_id": "orphan_avancee",
            "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        }]],
        pre_search_game_ids=frozenset(),
    )
    assert client.aborted == []


def test_annulation_refusee_par_lichess_najamais_resign(monkeypatch, caplog):
    """Si abort() est refusé, jamais de repli sur resign() (contrairement
    à _abandon_orphan_game_after_cancel, #383 point 3) — la partie et le
    bandeau de reprise restent, message bref à l'utilisateur."""
    with caplog.at_level(logging.WARNING, logger="niclink.lichess"):
        client, events = _run_sweep_sync(
            monkeypatch,
            fetch_results=[[{
                "game_id": "orphan_refus",
                "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            }]],
            pre_search_game_ids=frozenset(),
            abort_exc=LichessApiError(400, "refusé"),
        )
    assert not hasattr(client, "resigned")  # jamais de méthode resign() même appelée
    toasts = [d for t, d in events if t == "lichess_toast"]
    assert any(d["message_key"] == "toast.lichess_orphan_game_laissee" for d in toasts)


def test_aucune_partie_apparue_najamais_dappel_abort(monkeypatch):
    client, _events = _run_sweep_sync(monkeypatch, fetch_results=[[]], pre_search_game_ids=frozenset())
    assert client.aborted == []


def test_liste_indisponible_a_un_checkpoint_est_ignoree_sans_planter(monkeypatch):
    """_fetch_ongoing_games peut renvoyer None (réseau) à un checkpoint —
    jamais une exception, simplement ignoré, le balayage continue."""
    client, _events = _run_sweep_sync(
        monkeypatch,
        fetch_results=[None, [{
            "game_id": "orphan_tardif",
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        }]],
        pre_search_game_ids=frozenset(),
        checkpoints=(0.01, 0.01),
    )
    assert client.aborted == ["orphan_tardif"]


def test_nouveau_lancement_pendant_la_verification_larrete(monkeypatch):
    """Dès qu'un nouveau lancement commence (génération différente), le
    balayage s'arrête — jamais d'annulation d'une partie d'une recherche
    ultérieure légitime."""
    monkeypatch.setattr(lichess_launcher, "_ORPHAN_SWEEP_CHECKPOINTS_S", (0.01, 0.05, 0.05))
    client = _TrackingSweepClient()
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)

    call_count = {"n": 0}

    def _fake_fetch(token):
        call_count["n"] += 1
        # 1er checkpoint : rien de neuf, mais un nouveau lancement démarre
        # juste APRÈS (entre les deux checkpoints, comme en situation
        # réelle — jamais pendant l'appel réseau lui-même). Si le 2e
        # checkpoint était quand même atteint, il trouverait l'orpheline —
        # jamais vérifié ici, précisément parce qu'il ne doit pas l'être.
        if call_count["n"] == 1:
            lichess_launcher._bump_launch_generation()
            return []
        return [{
            "game_id": "orphan_devrait_etre_ignoree",
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        }]

    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", _fake_fetch)

    my_generation = lichess_launcher._current_launch_generation()
    lichess_launcher._orphan_sweep_worker("lip_x", frozenset(), my_generation)

    # Le 2e checkpoint n'a jamais été atteint — le contrôle de génération
    # juste avant son propre appel réseau a stoppé le balayage.
    assert call_count["n"] <= 1
    assert client.aborted == []


def test_start_orphan_sweep_sans_base_fiable_ne_demarre_pas(monkeypatch):
    """pre_search_game_ids=None (liste avant la recherche impossible à
    obtenir) : aucune base de comparaison fiable — le balayage ne démarre
    jamais plutôt que de risquer une annulation hasardeuse."""
    started = lichess_launcher._start_orphan_sweep_after_cancel("lip_x", None, 1)
    assert started is None


def test_start_orphan_sweep_demarre_un_fil_en_arriere_plan(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "_ORPHAN_SWEEP_CHECKPOINTS_S", (0.01,))
    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", lambda token: [])
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: _TrackingSweepClient())

    t0 = time.monotonic()
    t = lichess_launcher._start_orphan_sweep_after_cancel("lip_x", frozenset(), 1)
    elapsed = time.monotonic() - t0

    assert isinstance(t, threading.Thread)
    assert elapsed < 0.1, "le démarrage du balayage ne doit jamais bloquer l'appelant"
    t.join(timeout=2.0)
    assert not t.is_alive()


# ═══════════════════════════════════════════════════════════════════════
# 3. Bout en bout — _run_lichess_human() : scénario exact de l'étude #391
#    point 2 (seulement "seek_closed", jamais de "found" signalé).
# ═══════════════════════════════════════════════════════════════════════

class _SeekClosedOnlySeekSessionDouble:
    """Reproduit le scénario de l'étude #391 point 2 : le flux de
    recherche se ferme SANS jamais signaler "found" (aucun évènement de ce
    type n'est jamais poussé dans la file), et aucun "found" tardif
    n'arrive même après cancel() — contrairement à _RacingSeekSessionDouble
    (#383 point 3, course avec un "found" déjà en transit)."""

    def __init__(self, client, game_log=None):
        self.cancel_called = False
        self.close_called = False
        self._events = [{"type": "seek_closed"}]

    def start(self, *a, **kw):
        pass

    def next_event(self, timeout=0.2):
        return self._events.pop(0) if self._events else None

    def cancel(self):
        self.cancel_called = True

    def close(self):
        self.close_called = True


class _TrackingHumanClientWithAbort:
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


def _patch_human_launch_basics(monkeypatch, client, ongoing_sequence):
    """Même convention que test_issue383_point3_orphan_game.py — fils/USB
    entièrement doublés. `ongoing_sequence` : résultats successifs de
    _fetch_ongoing_games (le premier sert de liste mémorisée AVANT la
    recherche, les suivants sont consommés par le balayage en arrière-plan)."""
    board = _ScriptedBoard([INITIAL_FEN_W])
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    calls = {"n": 0}

    def _get_app_state():
        calls["n"] += 1
        # 1er appel : _wait_initial_position_lichess (jamais "menu"). 2e :
        # premier passage de la boucle de recherche (jamais "menu", laisse
        # le "seek_closed" être consommé). 3e, pendant l'attente de grâce
        # après seek_closed : "menu" — annulation immédiate par
        # l'utilisateur, exactement comme dans l'étude #391 point 2.
        return "menu" if calls["n"] >= 3 else "connecting"

    monkeypatch.setattr(lichess_launcher, "get_app_state", _get_app_state)

    fetch_calls = {"n": 0}

    def _fake_fetch(token):
        idx = fetch_calls["n"]
        fetch_calls["n"] += 1
        return ongoing_sequence[idx] if idx < len(ongoing_sequence) else ongoing_sequence[-1]

    monkeypatch.setattr(lichess_launcher, "_fetch_ongoing_games", _fake_fetch)
    monkeypatch.setattr(lichess_launcher, "_ORPHAN_SWEEP_CHECKPOINTS_S", (0.02, 0.02, 0.02))
    return board


def test_seek_closed_sans_found_annulation_immediate_partie_apparue_est_annulee(monkeypatch, caplog):
    """Scénario exact de l'étude #391, point 2 : _reap_late_found_game
    (#383 point 3) n'a rien à drainer (jamais de "found") — c'est le
    balayage élargi qui doit détecter et annuler la partie orpheline."""
    client = _TrackingHumanClientWithAbort()
    sweep_threads = []
    orig_start = lichess_launcher._start_orphan_sweep_after_cancel

    def _tracking_start(*a, **kw):
        t = orig_start(*a, **kw)
        if t is not None:
            sweep_threads.append(t)
        return t

    monkeypatch.setattr(lichess_launcher, "_start_orphan_sweep_after_cancel", _tracking_start)
    _patch_human_launch_basics(monkeypatch, client, ongoing_sequence=[
        [],  # garde-fou "une seule partie à la fois" (avant la recherche) : vide
        [],  # liste mémorisée pour le balayage (avant la recherche) : vide
        [{  # 1er checkpoint du balayage : la partie orpheline est apparue
            "game_id": "orphan_391_point2",
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        }],
    ])
    monkeypatch.setattr(seek_module, "SeekSession", _SeekClosedOnlySeekSessionDouble)
    monkeypatch.setattr(lichess_launcher, "_SEEK_CLOSED_GRACE_S", 10.0)  # non épuisé, sortie par "menu" avant

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human("lip_x", 900, 10, "white", "15+10", "Alain", _error)

    assert sweep_threads, "le balayage élargi n'a jamais été démarré"
    sweep_threads[0].join(timeout=2.0)
    assert not sweep_threads[0].is_alive()
    assert client.aborted == ["orphan_391_point2"]
    assert client.resigned == []
