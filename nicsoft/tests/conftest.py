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
import socket as _socket

import pytest

import nicsoft.config as _config
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
