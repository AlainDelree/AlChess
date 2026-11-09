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
import pytest

import nicsoft.config as _config
import nicsoft.engine.pgn_manager as _pgn_manager
import nicsoft.web.server as _server
import nicsoft.modes.humain.human as _human
import nicsoft.modes.retranscription.retranscription as _retranscription


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
