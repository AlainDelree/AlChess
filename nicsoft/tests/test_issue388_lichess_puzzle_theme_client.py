"""
nicsoft/tests/test_issue388_lichess_puzzle_theme_client.py — AlChess

Issue #388, point 1 : client Lichess pour le choix du thème/de la phase de
partie des problèmes — angle transmis à `get_next_puzzle` (validé contre
une liste fixe), lecture du tableau de bord par thème
(`get_puzzle_dashboard`/`parse_puzzle_dashboard`), et calcul pur du thème
par défaut (`puzzle_themes.compute_default_theme`). Aucun réseau réel :
`urllib.request.urlopen` mocké, même technique que
test_issue351_lichess_puzzles.py. Jamais le vrai jeton d'Alain, jamais le
vrai Lichess."""

import json
import urllib.error

import pytest

from nicsoft.modes.lichess import puzzle_client
from nicsoft.modes.lichess import puzzle_themes


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=None):
        return self._body


# ── get_next_puzzle : paramètre angle ───────────────────────────────────────

def test_angle_connu_est_transmis_dans_l_adresse(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(json.dumps({
            "game": {"id": "g1", "pgn": "", "rated": True, "players": []},
            "puzzle": {"id": "p1", "solution": ["e2e4"], "themes": ["fork"]},
        }).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    puzzle_client.get_next_puzzle("lip_test", angle="fork")
    assert "angle=fork" in captured["url"]


def test_angle_phase_connue_est_transmise(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(json.dumps({
            "game": {"id": "g1", "pgn": "", "rated": True, "players": []},
            "puzzle": {"id": "p1", "solution": ["e2e4"], "themes": ["middlegame"]},
        }).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    puzzle_client.get_next_puzzle("lip_test", angle="middlegame")
    assert "angle=middlegame" in captured["url"]


def test_angle_inconnu_jamais_insere_dans_l_adresse(monkeypatch):
    """Comportement « mélange » inchangé pour toute valeur hors de la
    liste fixe — jamais une chaîne arbitraire dans l'adresse."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(json.dumps({
            "game": {"id": "g1", "pgn": "", "rated": True, "players": []},
            "puzzle": {"id": "p1", "solution": ["e2e4"], "themes": ["fork"]},
        }).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    for bogus in ("'; DROP TABLE", "<script>", "../../etc/passwd", "mix", "", None):
        captured.clear()
        puzzle_client.get_next_puzzle("lip_test", angle=bogus)
        assert "angle=" not in captured["url"]


def test_angle_absent_se_combine_avec_difficulty(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(json.dumps({
            "game": {"id": "g1", "pgn": "", "rated": True, "players": []},
            "puzzle": {"id": "p1", "solution": ["e2e4"], "themes": ["fork"]},
        }).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    puzzle_client.get_next_puzzle("lip_test", difficulty="easier", angle="pin")
    assert "angle=pin" in captured["url"]
    assert "difficulty=easier" in captured["url"]


# ── get_puzzle_dashboard / parse_puzzle_dashboard ──────────────────────────

def _dashboard_body(themes):
    return json.dumps({
        "days": 30,
        "global": {"nb": 1, "firstWins": 1, "replayWins": 0, "puzzleRatingAvg": 1500, "performance": 1500},
        "themes": themes,
    }).encode("utf-8")


def test_parse_puzzle_dashboard_extrait_nb_first_wins_performance():
    data = {
        "days": 30,
        "global": {"nb": 1, "firstWins": 1, "replayWins": 0, "puzzleRatingAvg": 1500, "performance": 1500},
        "themes": {
            "fork": {"theme": "Fork", "results": {
                "nb": 12, "firstWins": 6, "replayWins": 0, "puzzleRatingAvg": 1600, "performance": 1550,
            }},
        },
    }
    parsed = puzzle_client.parse_puzzle_dashboard(data)
    assert parsed == {"themes": {"fork": {"nb": 12, "first_wins": 6, "performance": 1550}}}


def test_parse_puzzle_dashboard_sans_themes_retourne_none():
    assert puzzle_client.parse_puzzle_dashboard({}) is None
    assert puzzle_client.parse_puzzle_dashboard("pas un dict") is None


def test_parse_puzzle_dashboard_entree_malformee_ignoree_sans_planter():
    data = {"days": 30, "global": {}, "themes": {
        "fork": {"theme": "Fork", "results": {"nb": "pas un nombre", "firstWins": 1, "performance": 1500}},
        "pin": {"theme": "Pin"},  # "results" absent
        "mateIn1": "pas un dict",
        "skewer": {"theme": "Skewer", "results": {
            "nb": 5, "firstWins": 2, "replayWins": 0, "puzzleRatingAvg": 1400, "performance": 1400,
        }},
    }}
    parsed = puzzle_client.parse_puzzle_dashboard(data)
    assert parsed == {"themes": {"skewer": {"nb": 5, "first_wins": 2, "performance": 1400}}}


def test_get_puzzle_dashboard_ok(monkeypatch):
    body = _dashboard_body({
        "fork": {"theme": "Fork", "results": {
            "nb": 12, "firstWins": 6, "replayWins": 0, "puzzleRatingAvg": 1600, "performance": 1550,
        }},
    })
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = puzzle_client.get_puzzle_dashboard("lip_test")
    assert result == {"status": "ok", "themes": {"fork": {"nb": 12, "first_wins": 6, "performance": 1550}}}


def test_get_puzzle_dashboard_url_utilise_les_jours_demandes(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(_dashboard_body({}))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    puzzle_client.get_puzzle_dashboard("lip_test", days=7)
    assert captured["url"].endswith("/api/puzzle/dashboard/7")


def test_get_puzzle_dashboard_sans_jeton():
    assert puzzle_client.get_puzzle_dashboard("") == {"status": "invalid"}


def test_get_puzzle_dashboard_jeton_invalide_401(monkeypatch):
    def raise_401(req, timeout=None):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_401)
    assert puzzle_client.get_puzzle_dashboard("lip_test")["status"] == "invalid"


def test_get_puzzle_dashboard_droit_manquant_403(monkeypatch):
    def raise_403(req, timeout=None):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_403)
    assert puzzle_client.get_puzzle_dashboard("lip_test")["status"] == "missing_scope"


def test_get_puzzle_dashboard_limite_requetes_429(monkeypatch):
    def raise_429(req, timeout=None):
        raise urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_429)
    assert puzzle_client.get_puzzle_dashboard("lip_test")["status"] == "rate_limited"


def test_get_puzzle_dashboard_reseau_coupe(monkeypatch):
    def raise_url_error(req, timeout=None):
        raise urllib.error.URLError("pas de réseau")
    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    assert puzzle_client.get_puzzle_dashboard("lip_test")["status"] == "network_error"


def test_get_puzzle_dashboard_reponse_illisible_ne_plante_pas(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(b"pas du json"))
    assert puzzle_client.get_puzzle_dashboard("lip_test")["status"] == "network_error"


def test_get_puzzle_dashboard_refuse_adresse_non_https(monkeypatch):
    monkeypatch.setattr(puzzle_client, "PUZZLE_DASHBOARD_URL_TEMPLATE", "http://lichess.org/api/puzzle/dashboard/{days}")
    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: called.append(1))
    with pytest.raises(Exception):
        puzzle_client.get_puzzle_dashboard("lip_test")
    assert not called


def test_get_puzzle_dashboard_jeton_jamais_dans_l_url_ou_les_logs(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        return _FakeResponse(_dashboard_body({}))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    puzzle_client.get_puzzle_dashboard("lip_super_secret_token")
    assert "lip_super_secret_token" not in captured["url"]
    assert captured["headers"].get("Authorization") == "Bearer lip_super_secret_token"


# ── puzzle_themes.compute_default_theme — pur, sans réseau ─────────────────

def test_compute_default_theme_choisit_la_performance_la_plus_basse():
    themes = {
        "fork":   {"nb": 20, "first_wins": 10, "performance": 1600},
        "pin":    {"nb": 15, "first_wins": 5, "performance": 1400},
        "skewer": {"nb": 30, "first_wins": 20, "performance": 1700},
    }
    assert puzzle_themes.compute_default_theme(themes) == "pin"


def test_compute_default_theme_exclut_les_themes_sous_le_seuil():
    themes = {
        "fork": {"nb": 9, "first_wins": 0, "performance": 900},   # sous le seuil (10)
        "pin":  {"nb": 10, "first_wins": 5, "performance": 1500},
    }
    assert puzzle_themes.compute_default_theme(themes) == "pin"


def test_compute_default_theme_exclut_les_phases_de_partie():
    themes = {
        "middlegame": {"nb": 50, "first_wins": 10, "performance": 900},  # phase, jamais choisie
        "fork":       {"nb": 20, "first_wins": 10, "performance": 1600},
    }
    assert puzzle_themes.compute_default_theme(themes) == "fork"


def test_compute_default_theme_egalite_departagee_par_le_taux_de_reussite():
    themes = {
        "fork": {"nb": 20, "first_wins": 4, "performance": 1500},   # 20% de réussite
        "pin":  {"nb": 20, "first_wins": 10, "performance": 1500},  # 50% de réussite
    }
    assert puzzle_themes.compute_default_theme(themes) == "fork"


def test_compute_default_theme_sans_theme_eligible_retourne_chaine_vide():
    assert puzzle_themes.compute_default_theme({}) == ""
    assert puzzle_themes.compute_default_theme({"fork": {"nb": 3, "first_wins": 1, "performance": 1500}}) == ""


def test_compute_default_theme_entree_invalide_ne_plante_pas():
    assert puzzle_themes.compute_default_theme(None) == ""
    assert puzzle_themes.compute_default_theme("pas un dict") == ""
    assert puzzle_themes.compute_default_theme({"fork": "pas un dict"}) == ""
    assert puzzle_themes.compute_default_theme({"inconnu123": {"nb": 50, "first_wins": 1, "performance": 100}}) == ""


# ── Garde de cohérence des listes fixes ─────────────────────────────────────

def test_listes_fixes_sans_recoupement():
    assert not (set(puzzle_themes.PUZZLE_THEME_KEYS) & set(puzzle_themes.PUZZLE_PHASE_KEYS))
    assert puzzle_themes.PUZZLE_MIX_ANGLE not in puzzle_themes.ALL_PUZZLE_ANGLES
    assert puzzle_themes.DEFAULT_PUZZLE_PHASE in puzzle_themes.PUZZLE_PHASE_KEYS


def test_toutes_les_cles_sont_des_identifiants_simples():
    """Jamais d'espace, de ponctuation ou de caractère spécial dans une
    clé fixe (sécurité de get_next_puzzle : l'appartenance à cette liste
    suffit à autoriser l'insertion dans l'adresse)."""
    for key in puzzle_themes.ALL_PUZZLE_ANGLES:
        assert key.isalnum(), key
