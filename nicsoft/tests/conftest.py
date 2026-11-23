"""
nicsoft/tests/conftest.py — AlChess

Fixture commune à toute la suite de tests en process (hors nicsoft/tests/e2e,
qui lance un sous-processus séparé) : redirige le dossier des parties
(GAMES_DIR) vers un répertoire temporaire, pour tous les tests, sans qu'ils
aient besoin de le demander explicitement — issue #310, point 8 (deux
fichiers PGN factices avaient fui dans le vrai dossier de parties de
l'utilisateur lors des tests de l'issue #309).

Ne touche pas DATA_DIR/APP_DIR : plusieurs tests (exercices, ouvertures)
lisent de vraies données utilisateur (ECO, livres d'ouvertures) via
ALCHESS_DIR — seul GAMES_DIR n'a aucun contenu préexistant à lire, juste des
parties écrites par le code sous test. L'isolation de la configuration
(jeton Lichess, etc.) reste gérée au cas par cas par les fixtures locales
existantes (ex. `isolated_config` de test_issue306_lichess.py).
"""
import os as _os
import socket as _socket
import subprocess as _subprocess

import hid as _hid
import pytest

import nicsoft.config as _config
import nicsoft.core.game_manager_modes.humain as _humain_launcher
import nicsoft.core.game_manager_modes.lichess as _lichess_launcher
import nicsoft.engine.pgn_manager as _pgn_manager
import nicsoft.web.server as _server
import nicsoft.modes.humain.human as _human
import nicsoft.modes.retranscription.retranscription as _retranscription

# Garde-fou réseau Lichess (issue #327, point 8) : toute la suite Lichess
# passe par un transport injectable (FakeTransport, jamais UrllibTransport
# en test — voir transport.py) ; cette fixture détecte le jour où un test
# oublierait d'injecter son faux transport et laisserait échapper une vraie
# requête vers lichess.org. `socket.create_connection` est le bon point
# d'interception : `http.client.HTTPConnection.__init__` capture
# `socket.create_connection` comme attribut D'INSTANCE au moment de la
# construction (`self._create_connection = socket.create_connection`),
# donc patcher l'attribut du MODULE `socket` avant toute connexion (ce que
# fait monkeypatch, exécuté avant le corps du test) suffit à intercepter
# l'appel réel — vérifié ici avec une vraie tentative de connexion TCP vers
# lichess.org:443 (ce bac à sable a un accès réseau sortant). Ne couvre que
# la suite EN PROCESS (nicsoft/tests, hors nicsoft/tests/e2e qui lance un
# sous-processus séparé) — ce dernier reste protégé par construction
# (jeton Lichess toujours vide dans son ALCHESS_DIR isolé, voir #326 :
# aucun appel réseau n'est même tenté).
_REAL_CREATE_CONNECTION = _socket.create_connection


def _guarded_create_connection(address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else str(address)
    if "lichess" in str(host).lower():
        raise AssertionError(
            f"Garde réseau (issue #327) : tentative de connexion RÉELLE vers un nom "
            f"d'hôte Lichess pendant les tests ({host!r}) — un faux transport "
            f"(FakeTransport) aurait dû être injecté. Aucune connexion réelle à "
            f"Lichess n'est autorisée pendant les tests."
        )
    return _REAL_CREATE_CONNECTION(address, *args, **kwargs)


@pytest.fixture(autouse=True)
def _guard_no_real_lichess_network(monkeypatch):
    monkeypatch.setattr(_socket, "create_connection", _guarded_create_connection)
    yield


# Garde matériel (issue #372) : le Chessnut Air réel bippait pendant la
# suite de tests (hook pre-push, issues CCL) alors qu'AlChess était fermé —
# preuve qu'au moins un test (ou un sous-processus lancé par un test)
# atteignait le vrai périphérique USB. La seule couche qui ouvre le
# périphérique et envoie des commandes (ouverture, bip, LED, lecture) est
# `nicsoft/niclink/hid_backend.py`, qui fait systématiquement `hid.device()`
# (ouverture) et `hid.enumerate()` (énumération) — jamais touché ici, on
# neutralise le point d'entrée du binding hidapi lui-même, un cran plus bas,
# pour couvrir aussi un futur code de production qui ouvrirait l'échiquier à
# un endroit inattendu.
class RealBoardAccessError(BaseException):
    """Accès RÉEL à l'échiquier USB tenté par un test non marqué "hardware".

    Hérite directement de BaseException (jamais Exception) pour traverser
    sans être absorbée les `except Exception` déjà présents côté production
    (ex. hid_backend.check_physically_present) : l'intention du garde est de
    faire échouer bruyamment le test fautif, jamais de se laisser avaler par
    un `except` qui n'a pas été écrit pour elle.
    """


# Capturées avant tout monkeypatch (import du module, donc toujours les
# vrais objets hidapi) — permet à un test marqué "hardware" de vérifier son
# exemption par une simple comparaison d'identité, sans jamais appeler
# réellement hid.device()/hid.enumerate() pour "vérifier" le garde.
ORIGINAL_HID_DEVICE = _hid.device
ORIGINAL_HID_ENUMERATE = _hid.enumerate


def _board_guard_message(test_id: str, call_name: str) -> str:
    return (
        f"Garde matériel (issue #372) : le test {test_id!r} a tenté un accès "
        f"RÉEL à l'échiquier USB via {call_name} — interdit hors test marqué "
        f"@pytest.mark.hardware. Utilisez VirtualBoard "
        f"(nicsoft/niclink/virtual_board.py) ou un faux plateau/transport "
        f"dédié au test, jamais le périphérique physique."
    )


@pytest.fixture(autouse=True)
def _guard_no_real_board_access(request, monkeypatch):
    """Neutralise `hid.device()`/`hid.enumerate()` pour la durée de chaque
    test non marqué "hardware" — ces deux appels sont l'unique point
    d'entrée par lequel `hid_backend.py` touche le périphérique USB réel
    (ouverture, puis bip/LED/lecture une fois ouvert ; sans ouverture
    réussie, ces commandes restent des no-ops silencieux côté hid_backend).
    Un test marqué "hardware" (jamais exécuté en CI ni en session normale)
    reste exempté."""
    if request.node.get_closest_marker("hardware") is not None:
        yield
        return

    test_id = request.node.nodeid

    def _guarded_enumerate(*args, **kwargs):
        raise RealBoardAccessError(_board_guard_message(test_id, "hid.enumerate()"))

    class _GuardedDevice:
        def __init__(self, *args, **kwargs):
            raise RealBoardAccessError(_board_guard_message(test_id, "hid.device()"))

    monkeypatch.setattr(_hid, "enumerate", _guarded_enumerate)
    monkeypatch.setattr(_hid, "device", _GuardedDevice)
    yield


# Chaque test qui lance un vrai sous-processus `python -m nicsoft.web`
# (nicsoft/tests/e2e/conftest.py, test_issue312_server_startup.py,
# test_issue320_single_instance.py, test_issue369_startup_js_guard.py) pose
# déjà ALCHESS_SKIP_BOARD=1 dans son propre env — mais rien n'empêchait un
# futur test de l'oublier et de laisser un sous-processus ouvrir le vrai
# échiquier. Filet de sécurité : `subprocess.Popen` (dont `subprocess.run`/
# `check_call`/`check_output` se servent tous, dans le même module) pose
# ALCHESS_SKIP_BOARD=1 dans l'environnement de TOUT sous-processus lancé
# pendant un test non "hardware", sans écraser une valeur déjà posée
# explicitement par le test ; `env=None` (héritage de l'environnement du
# process de test) est traité pareil, via une copie explicite d'os.environ.
_ORIGINAL_POPEN = _subprocess.Popen


def _popen_with_skip_board(*args, **kwargs):
    env = kwargs.get("env")
    env = dict(_os.environ) if env is None else dict(env)
    env.setdefault("ALCHESS_SKIP_BOARD", "1")
    kwargs["env"] = env
    return _ORIGINAL_POPEN(*args, **kwargs)


@pytest.fixture(autouse=True)
def _guard_subprocess_skip_board(request, monkeypatch):
    """Filet de sécurité (issue #372) — voir commentaire ci-dessus. Exempte
    les tests "hardware" par symétrie avec `_guard_no_real_board_access`,
    au cas où l'un d'eux aurait un jour besoin de lancer un sous-processus
    qui parle au vrai échiquier."""
    if request.node.get_closest_marker("hardware") is not None:
        yield
        return
    monkeypatch.setattr(_subprocess, "Popen", _popen_with_skip_board)
    yield


@pytest.fixture(autouse=True)
def _stub_check_board_presence_silent(monkeypatch):
    """launch_lichess()/_launch_lichess_human()/launch_lichess_resume()/
    launch_lichess_puzzle() (nicsoft/core/game_manager_modes/lichess.py) et
    _run_humain()/_run_lichess_resume (humain.py) lancent chacun, en fin de
    partie, un fil d'arrière-plan `check_board_presence_silent()` (rafraîchit
    juste le badge "échiquier" du menu, hors toute partie) — révélé par le
    garde ci-dessus (issue #372) comme une source réelle d'accès USB en fil
    séparé, non rattrapée par la plupart des tests qui exercent ces
    lanceurs : le fil se termine après le retour de la fonction testée, hors
    de portée de tout monkeypatch posé APRÈS l'appel, et pytest ne fait que
    l'avertir (`PytestUnhandledThreadExceptionWarning`), jamais échouer le
    test fautif. Neutralisé par défaut ; un test qui vérifie spécifiquement
    ce câblage (ex. test_issue299_check_board_presence_silent.py,
    test_issue299_humain_retour_menu_silencieux.py) repatche la même cible
    avec sa propre fausse implémentation traçante, qui prévaut (même
    fixture `monkeypatch`, dernière écriture gagnante)."""
    monkeypatch.setattr(_lichess_launcher, "check_board_presence_silent", lambda: None)
    monkeypatch.setattr(_humain_launcher, "check_board_presence_silent", lambda: None)
    yield


@pytest.fixture(autouse=True)
def _isolate_games_dir(tmp_path, monkeypatch):
    """Redirige vers tmp_path tous les alias connus de GAMES_DIR — chacun
    lié à l'import dans son module (`from nicsoft.config import GAMES_DIR`
    fige une référence locale ; patcher nicsoft.config.GAMES_DIR seul ne
    suffit pas)."""
    games_dir = tmp_path / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(_config, "GAMES_DIR", games_dir)
    monkeypatch.setattr(_pgn_manager, "GAMES_DIR", games_dir)
    monkeypatch.setattr(_pgn_manager, "TMP_DIR", str(games_dir / "tmp"))
    monkeypatch.setattr(_server, "GAMES_DIR", games_dir)
    monkeypatch.setattr(_human, "GAMES_DIR", games_dir)
    monkeypatch.setattr(_retranscription, "GAMES_DIR", games_dir / "Transcription")

    yield games_dir
