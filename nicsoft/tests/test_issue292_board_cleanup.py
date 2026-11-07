"""
nicsoft/tests/test_issue292_board_cleanup.py — NicLink
Issue #292 : échiquier physique inutilisable après un abandon en « pièces
mal placées » — fils de la partie précédente encore actifs et connexion USB
non protégée.

Mécanisme reproduit ici sans matériel (hid_backend.hid remplacé par un faux
module hidapi) :
  1. nicsoft/core/game_manager_modes/pedagogique.py ne fermait jamais
     l'ancien NicLinkManager à la fin d'une partie (nettoyage limité à
     turn_off_all_leds()) : le fil fen_reader restait vivant, le périphérique
     USB jamais libéré.
  2. nicsoft/niclink/hid_backend.py relisait la variable partagée _dev à
     chaque itération de connect()/get_fen() au lieu de travailler sur une
     référence locale : si le fil fen_reader orphelin (point 1) remettait
     _dev à None pendant qu'une nouvelle partie se connectait, connect()
     levait AttributeError('NoneType' object has no attribute 'read').

Corrections couvertes par ces tests :
  (a) disconnect() arrête bien le fil fen_reader et libère le périphérique ;
      le lanceur pédagogique appelle désormais disconnect() dans son nettoyage.
  (b) connect() ne lève plus jamais AttributeError même si un fil orphelin
      continue d'appeler get_fen() pendant l'établissement de la connexion.
  (c) une perte de connexion pendant l'établissement lève l'exception
      RuntimeError que NicLinkManager.__init__ sait déjà afficher comme
      « échiquier non détecté », jamais une erreur d'attribut.
  (d) après un échec de connexion, un nouvel essai réussit sans redémarrage.
  (+) les boucles d'attente de position (await_move) respectent déjà
      kill_switch même si le plateau affiche une position qui ne
      correspondra jamais à celle attendue par la partie.

Aucun matériel ni réseau requis.
"""
import threading
import time

import chess
import pytest

from nicsoft.niclink import hid_backend
from nicsoft.niclink.driver import NicLinkManager
from nicsoft.niclink.nl_exceptions import ExitNicLink


# ── Faux hidapi ──────────────────────────────────────────────────────────────

class _FakeDevice:
    """Remplace hid.device() : pas d'USB réel, comportement configurable.

    open_path()/close() simulent l'ouverture exclusive du vrai Chessnut Air
    (issue #295, défaut 1) : tant qu'un _FakeDevice créé par le même
    _FakeHidModule reste ouvert, toute nouvelle tentative d'open_path() sur
    ce module échoue avec OSError('open failed'), comme le périphérique
    réel. L'instance ne sait rien de son module tant que _FakeHidModule.device()
    ne l'y a pas rattachée via `_hid_module` — voir plus bas."""

    def __init__(self, fail_reads=False, fail_after=None, read_delay=0.0):
        self.closed = False
        self._reads = 0
        self._fail_reads = fail_reads
        self._fail_after = fail_after
        self._read_delay = read_delay
        self._hid_module = None  # rattaché par _FakeHidModule.device()
        self._is_opener = False  # True si CETTE instance tient le verrou d'exclusivité

    def open_path(self, path):
        hm = self._hid_module
        if hm is not None:
            if hm._is_open:
                raise OSError("open failed")
            hm._is_open = True
            self._is_opener = True

    def write(self, data):
        pass

    def read(self, size, timeout_ms=50):
        self._reads += 1
        if self._read_delay:
            time.sleep(self._read_delay)
        if self._fail_reads:
            raise OSError("device lost")
        if self._fail_after is not None and self._reads > self._fail_after:
            raise OSError("device lost")
        return b"\x01\x00" + bytes(32)  # longueur > 1, décodage neutralisé par la fixture

    def close(self):
        self.closed = True
        if self._is_opener and self._hid_module is not None:
            self._hid_module._is_open = False
            self._is_opener = False


class _FakeHidModule:
    """Remplace le module `hid` (hidapi) importé par hid_backend.py.

    `_is_open` simule l'état d'ouverture exclusive du vrai périphérique USB :
    device() rattache chaque _FakeDevice créé à ce module (`_hid_module`) pour
    que son open_path()/close() sache contre quel verrou jouer."""

    def __init__(self, device_factory, present=True):
        self._device_factory = device_factory
        self.present = present
        self._is_open = False

    def enumerate(self, vendor_id, product_id):
        if not self.present:
            return []
        return [{"path": b"/fake/chessnut", "product_id": 0x8003, "usage_page": 0xFF00}]

    def device(self):
        dev = self._device_factory()
        dev._hid_module = self
        return dev


@pytest.fixture(autouse=True)
def _reset_hid_backend_state(monkeypatch):
    """Isole chaque test : état hid_backend propre, décodage FEN neutralisé
    (la valeur réelle des octets n'importe pas pour ces tests de threading/
    connexion), et délais de connexion raccourcis pour un test rapide."""
    monkeypatch.setattr(hid_backend, "_decode_fen", lambda data: "8/8/8/8/8/8/8/8")
    monkeypatch.setattr(hid_backend.time, "sleep", lambda *a, **k: None)
    hid_backend._reset_state()
    yield
    hid_backend._reset_state()


def _fen_reader_threads():
    return [t for t in threading.enumerate() if t.is_alive() and t.name == "fen_reader"]


# ── (a) Fermeture propre de l'ancien gestionnaire ────────────────────────────

def test_disconnect_arrete_le_fil_fen_reader_et_libere_le_device(monkeypatch):
    dev = _FakeDevice()
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: dev))

    nl_inst = NicLinkManager(refresh_delay=0.1, logger=None, thread_sleep_delay=0.01)
    try:
        assert len(_fen_reader_threads()) == 1
    finally:
        nl_inst.disconnect()

    assert _fen_reader_threads() == []
    assert nl_inst._fen_reader_thread is None
    assert dev.closed is True
    assert hid_backend._dev is None
    assert hid_backend.is_connected() is False


def test_run_pedagogique_disconnecte_lancien_echiquier_au_nettoyage(monkeypatch):
    """Le lanceur pédagogique doit fermer nl_inst dans son `finally`, quel
    que soit le chemin de sortie (ici : une exception levée pendant la
    construction de Game, pour isoler le nettoyage sans dépendre de
    Stockfish)."""
    import nicsoft.core.game_manager_modes.pedagogique as ped_launcher
    import nicsoft.modes.pedagogique.pedagogique as ped_mod

    disconnected = []

    class _FakeNl:
        def turn_off_all_leds(self):
            pass

        def disconnect(self):
            disconnected.append(True)

    class _FakeGame:
        def __init__(self, *a, **kw):
            raise RuntimeError("arrêt volontaire avant la logique moteur/plateau")

    monkeypatch.setattr(ped_launcher, "create_board", lambda **kw: _FakeNl())
    monkeypatch.setattr(ped_launcher, "_wait_initial_position_web", lambda nl: None)
    monkeypatch.setattr(ped_mod, "Game", _FakeGame)

    error = {"occurred": False, "toast_key": None}
    ped_launcher._run_pedagogique(
        "Joueur", True, 5, "blunder", False, False,
        1500, "", _error=error, virtual=False,
    )

    assert disconnected == [True]
    assert error["occurred"] is True


# ── Boucles d'attente de position : respectent déjà kill_switch/abandon ──────

def test_await_move_respecte_kill_switch_meme_position_jamais_correcte(monkeypatch):
    """Scénario de l'issue : l'utilisateur remet l'échiquier en position
    initiale alors que la partie est avancée (cette position ne correspondra
    jamais à ce qu'attend la partie). La boucle d'attente de coup doit malgré
    tout sortir dès que kill_switch est levé (abandon), sans attendre un
    timeout ni une position qui ne viendra jamais."""
    dev = _FakeDevice()
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: dev))
    nl_inst = NicLinkManager(refresh_delay=0.1, logger=None, thread_sleep_delay=0.01)
    try:
        nl_inst.game_board.push_san("e4")  # partie avancée : plus la position initiale
        nl_inst.current_fen = chess.STARTING_FEN  # le plateau ne bougera jamais vers l'attendu

        def _abandon_apres_peu():
            time.sleep(0.1)
            nl_inst.kill_switch.set()

        threading.Thread(target=_abandon_apres_peu, daemon=True).start()
        t0 = time.time()
        with pytest.raises(ExitNicLink):
            nl_inst.await_move()
        assert time.time() - t0 < 2.0
    finally:
        nl_inst.disconnect()


# ── (b) Connexion concurrente à un fil de lecture orphelin ───────────────────

def test_connect_survit_a_une_mutation_concurrente_de_dev(monkeypatch):
    """Reproduit de façon déterministe le mécanisme exact de l'issue : au
    moment précis où connect() lit le premier paquet sur son périphérique,
    un autre fil (le fen_reader orphelin d'une session jamais déconnectée)
    échoue sa propre lecture et remet la variable partagée _dev à None.

    Avant le correctif, connect() relisait _dev (global) à chaque itération
    de sa boucle d'attente du premier FEN : si un autre fil la remettait à
    None entre deux itérations, l'itération suivante levait
    AttributeError('NoneType' object has no attribute 'read'). Le correctif
    travaille sur une référence locale au périphérique : cette mutation
    concurrente du global, injectée ici au point exact de la lecture, ne
    doit plus jamais atteindre connect()."""
    hid_backend._reset_state()

    class _MutatingDevice(_FakeDevice):
        def read(self, size, timeout_ms=50):
            # Simule le fil orphelin : juste avant que connect() ne lise,
            # un autre fil vient de remettre la variable partagée à None
            # suite à une erreur de lecture sur sa propre session.
            hid_backend._reset_state_if_current(hid_backend._dev)
            return super().read(size, timeout_ms=timeout_ms)

    dev = _MutatingDevice()
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: dev))

    hid_backend.connect()  # ne doit jamais lever AttributeError

    assert hid_backend._dev is dev
    assert hid_backend.is_connected() is True


def test_connect_concurrent_avec_fil_orphelin_reel_ne_leve_jamais_attributeerror(monkeypatch):
    """Complément au test déterministe ci-dessus : fait tourner un vrai fil
    concurrent (le fen_reader orphelin) pendant l'établissement de plusieurs
    connexions successives. Non garanti de retomber exactement sur la fenêtre
    de course à chaque exécution (dépend de l'ordonnanceur), mais ne doit
    jamais lever AttributeError si la course se produit — répété pour
    maximiser les chances de l'exposer."""
    for attempt in range(30):
        hid_backend._reset_state()
        stale_dev = _FakeDevice()
        monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: stale_dev))
        hid_backend.connect()

        stop = threading.Event()

        def _fil_orphelin():
            while not stop.is_set():
                hid_backend.get_fen()

        t = threading.Thread(target=_fil_orphelin, daemon=True)
        t.start()

        new_dev = _FakeDevice(fail_after=2, read_delay=0.001)
        monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: new_dev))
        try:
            hid_backend.connect()
        except AttributeError as e:
            pytest.fail(f"AttributeError levée pendant connect() concurrent (issue #292, essai {attempt}) : {e}")
        except RuntimeError:
            pass  # lecture perdue pendant l'établissement — traité par ailleurs (test c)
        finally:
            stop.set()
            t.join(timeout=1.0)


# ── (c) Perte de connexion pendant l'établissement ───────────────────────────

def test_connect_perdue_pendant_etablissement_leve_runtimeerror(monkeypatch):
    dev = _FakeDevice(fail_reads=True)
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: dev))

    with pytest.raises(RuntimeError, match="déconnecté"):
        hid_backend.connect()

    assert hid_backend._dev is None
    assert hid_backend.is_connected() is False
    assert dev.closed is True


def test_niclinkmanager_connect_perdu_sort_proprement(monkeypatch):
    """L'exception doit rester celle que NicLinkManager.__init__ sait déjà
    convertir en sortie propre « board connection error » (comme pour un
    plateau introuvable) — jamais une erreur d'attribut non gérée."""
    dev = _FakeDevice(fail_reads=True)
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: dev))

    with pytest.raises(SystemExit, match="board connection error"):
        NicLinkManager(refresh_delay=0.1, logger=None, thread_sleep_delay=0.01)


# ── (d) Nouvel essai après un échec de connexion, sans redémarrage ───────────

def test_retry_apres_echec_connexion_reussit_sans_redemarrage(monkeypatch):
    attempts = {"n": 0}
    good_dev = _FakeDevice()

    def _factory():
        attempts["n"] += 1
        if attempts["n"] == 1:
            return _FakeDevice(fail_reads=True)
        return good_dev

    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(_factory))

    with pytest.raises(RuntimeError):
        hid_backend.connect()
    assert hid_backend._dev is None  # état remis à zéro après l'échec

    hid_backend.connect()  # deuxième essai, même processus — doit réussir
    assert hid_backend._dev is good_dev
    assert hid_backend.is_connected() is True
