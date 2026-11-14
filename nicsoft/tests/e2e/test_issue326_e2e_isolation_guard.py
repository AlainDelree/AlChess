"""
nicsoft/tests/e2e/test_issue326_e2e_isolation_guard.py — AlChess

Issue #326, point 9 : avant ce correctif, `server_url` (conftest.py)
pointait ALCHESS_DIR directement sur le dossier utilisateur réel d'Alain
(~/NicLink). Tout test e2e qui ouvrait l'écran de menu Lichess déclenchait
alors, côté serveur, un vrai appel réseau à Lichess avec le VRAI jeton lu
dans data/config.json (check_lichess_resumable(), nicsoft/web/alchess.py) —
constaté dans le journal réel d'Alain le 14/11/2026 (parties en cours
détectées sur son vrai compte) — et le serveur de test écrivait dans son
vrai niclink.log (LOGS_DIR, lui aussi dérivé d'ALCHESS_DIR).

Ce test ne lance pas le serveur (pas besoin pour vérifier la construction
du dossier isolé) : il appelle directement _build_isolated_alchess_dir()
et vérifie qu'elle ne peut plus jamais reproduire ce scénario, même si les
données ECO/livres réelles restent accessibles en lecture pour les tests
e2e non-Lichess qui en dépendent (test_outils_exercices_e2e.py).
"""
import json
import os

from nicsoft.tests.e2e.conftest import _build_isolated_alchess_dir, REAL_USER_DIR


def test_config_json_isole_sans_jeton_lichess(tmp_path_factory):
    base = _build_isolated_alchess_dir(tmp_path_factory)
    config_path = base / "data" / "config.json"
    assert config_path.exists()
    assert not config_path.is_symlink(), "config.json ne doit jamais être un lien vers le vrai fichier"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data.get("lichess_token", "") == "", "le jeton Lichess isolé doit toujours être vide (jamais le vrai)"


def test_logs_isoles_jamais_le_vrai_journal(tmp_path_factory):
    base = _build_isolated_alchess_dir(tmp_path_factory)
    logs_dir = base / "logs"
    assert logs_dir.is_dir()
    assert not logs_dir.is_symlink()
    assert list(logs_dir.iterdir()) == [], "le dossier logs isolé doit démarrer vide (jamais le vrai journal)"
    real_logs_dir = os.path.join(REAL_USER_DIR, "logs")
    assert os.path.realpath(str(logs_dir)) != os.path.realpath(real_logs_dir)


def test_donnees_eco_restent_accessibles_en_lecture(tmp_path_factory):
    """Les tests e2e non-Lichess (ex. explorateur d'ouvertures) ont besoin
    des données réelles non versionnées (data/ dans .gitignore) : ce
    correctif ne doit pas les leur retirer, seulement isoler config.json
    et logs/."""
    base = _build_isolated_alchess_dir(tmp_path_factory)
    real_data_dir = os.path.join(REAL_USER_DIR, "data")
    if not os.path.isdir(real_data_dir):
        return  # poste sans données réelles (hors machine d'Alain) — rien à vérifier ici
    for name in ("eco_a.tsv", "books"):
        real_path = os.path.join(real_data_dir, name)
        if os.path.exists(real_path):
            assert (base / "data" / name).exists()
