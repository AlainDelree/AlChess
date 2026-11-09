"""
nicsoft/tests/test_issue306_lichess.py — AlChess

Issue #306 (étape L0 — jeton personnel Lichess uniquement, aucune partie) :
  (1) nicsoft/modes/lichess/client.py : test_token() interroge
      /api/token/test (urllib, https vérifié par ensure_https) et retourne
      un statut structuré (ok/invalid/rate_limited/network_error) — jamais
      une exception brute, jamais le jeton dans un journal ou un message.
  (2) config_manager : lichess_token, défaut vide, même mécanisme que
      llm_api_key (issue #304 par symétrie).
  (3) server.py : config_get ne renvoie jamais le jeton (indicateur +
      indice 4 derniers caractères si ≥ 12 car.) ; config_save conserve si
      champ vide, remplace si valeur (espaces retirés), supprime si
      lichess_token_delete=True ; lichess_test_connection utilise le jeton
      tapé non enregistré en priorité, sinon celui en config, et ne
      journalise jamais le jeton même en cas d'exception inattendue.
  (4) i18n : nouvelles clés présentes dans fr/en/de.

Tests sans réseau (urllib.request.urlopen mocké) et sans matériel.
"""
import json
import logging
import time
import urllib.error

import pytest

import nicsoft.web.server as server
from nicsoft.core import config_manager as cm
from nicsoft.modes.lichess import client as lichess_client


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirige config.json vers un fichier temporaire — n'écrit jamais dans
    la vraie data/config.json d'Alain pendant les tests."""
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg_file)
    return cfg_file


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=None):
        return self._body


def _fake_token_test_body(token: str, scopes: str, user_id: str = "alain"):
    return json.dumps({token: {"scopes": scopes, "userId": user_id}}).encode("utf-8")


# ── config_manager : défaut ──────────────────────────────────────────────────

def test_default_config_lichess_token_vide():
    assert cm.DEFAULT_CONFIG["lichess_token"] == ""


# ── nicsoft/modes/lichess/client.py : test_token() ──────────────────────────

def test_test_token_valide_avec_board_play(monkeypatch):
    body = _fake_token_test_body("lip_test1234567890abcd", "board:play,email:read")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = lichess_client.test_token("lip_test1234567890abcd")
    assert result == {
        "status": "ok",
        "account": "alain",
        "scopes": ["board:play", "email:read"],
        "has_board_play": True,
    }


def test_test_token_valide_sans_board_play(monkeypatch):
    body = _fake_token_test_body("lip_test1234567890abcd", "email:read")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = lichess_client.test_token("lip_test1234567890abcd")
    assert result["status"] == "ok"
    assert result["has_board_play"] is False


def test_test_token_invalide(monkeypatch):
    body = json.dumps({"lip_bidon": None}).encode("utf-8")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(body))
    result = lichess_client.test_token("lip_bidon")
    assert result == {"status": "invalid"}


def test_test_token_reseau_coupe(monkeypatch):
    def raise_url_error(req, timeout=None):
        raise urllib.error.URLError("pas de réseau")
    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    result = lichess_client.test_token("lip_quelconque")
    assert result == {"status": "network_error"}


def test_test_token_limite_requetes_429(monkeypatch):
    def raise_429(req, timeout=None):
        raise urllib.error.HTTPError("https://lichess.org/api/token/test", 429, "Too Many Requests", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_429)
    result = lichess_client.test_token("lip_quelconque")
    assert result == {"status": "rate_limited"}


def test_test_token_autre_erreur_http(monkeypatch):
    def raise_500(req, timeout=None):
        raise urllib.error.HTTPError("https://lichess.org/api/token/test", 500, "Internal Error", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_500)
    result = lichess_client.test_token("lip_quelconque")
    assert result == {"status": "network_error"}


def test_test_token_refuse_adresse_non_https_urlopen_jamais_appele(monkeypatch):
    monkeypatch.setattr(lichess_client, "TOKEN_TEST_URL", "http://lichess.org/api/token/test")
    called = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: called.append(1))
    with pytest.raises(ValueError, match="https"):
        lichess_client.test_token("lip_quelconque")
    assert not called


def test_test_token_user_agent_contient_alchess(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        body = _fake_token_test_body("lip_x", "board:play")
        return _FakeResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    lichess_client.test_token("lip_x")
    assert captured["req"].headers.get("User-agent", "").startswith("AlChess/")


# ── config_get : jamais le jeton, seulement indicateur + indice ────────────

def test_config_get_jeton_long_indicateur_et_indice(monkeypatch):
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "lichess_token": "lip_test1234567890abcd"})
    captured = {}
    monkeypatch.setattr(server, "emit", lambda event, data: captured.update(event=event, data=data))
    server.on_config_get({})
    assert "lichess_token" not in captured["data"]
    assert captured["data"]["has_lichess_token"] is True
    assert captured["data"]["lichess_token_hint"] == "abcd"


def test_config_get_jeton_court_aucun_indice(monkeypatch):
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "lichess_token": "lip_123"})
    captured = {}
    monkeypatch.setattr(server, "emit", lambda event, data: captured.update(event=event, data=data))
    server.on_config_get({})
    assert "lichess_token" not in captured["data"]
    assert captured["data"]["has_lichess_token"] is True
    assert captured["data"]["lichess_token_hint"] == ""


def test_config_get_sans_jeton(monkeypatch):
    monkeypatch.setattr(cm, "load_config", lambda: dict(cm.DEFAULT_CONFIG))
    captured = {}
    monkeypatch.setattr(server, "emit", lambda event, data: captured.update(event=event, data=data))
    server.on_config_get({})
    assert "lichess_token" not in captured["data"]
    assert captured["data"]["has_lichess_token"] is False
    assert captured["data"]["lichess_token_hint"] == ""


# ── config_save : champ vide = inchangé, valeur = remplace, suppression ────

def test_config_save_champ_vide_conserve_le_jeton(isolated_config, monkeypatch):
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)
    cm.save_config({"lichess_token": "lip_test1234567890abcd"})
    server.on_config_save({"lichess_token": ""})
    assert cm.load_config()["lichess_token"] == "lip_test1234567890abcd"


def test_config_save_valeur_remplace_le_jeton(isolated_config, monkeypatch):
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)
    cm.save_config({"lichess_token": "lip_old0000000000000"})
    server.on_config_save({"lichess_token": "lip_new1111111111111"})
    assert cm.load_config()["lichess_token"] == "lip_new1111111111111"


def test_config_save_retire_les_espaces_autour(isolated_config, monkeypatch):
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)
    server.on_config_save({"lichess_token": "  lip_new1111111111111  "})
    assert cm.load_config()["lichess_token"] == "lip_new1111111111111"


def test_config_save_suppression_explicite(isolated_config, monkeypatch):
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)
    cm.save_config({"lichess_token": "lip_test1234567890abcd"})
    server.on_config_save({"lichess_token": "", "lichess_token_delete": True})
    assert cm.load_config()["lichess_token"] == ""


def test_config_save_ne_renvoie_jamais_le_jeton(isolated_config, monkeypatch):
    captured = []
    monkeypatch.setattr(server, "emit", lambda event, data: captured.append((event, data)))
    cm.save_config({"lichess_token": "lip_test1234567890abcd"})
    server.on_config_save({"lichess_token": "lip_nouveau_jeton_999"})
    assert len(captured) == 1
    event, data = captured[0]
    assert event == "config_saved"
    assert "lichess_token" not in data


# ── lichess_test_connection : jeton tapé prioritaire, sinon config ──────────

class _FakeRequest:
    def __init__(self, sid):
        self.sid = sid


class _FakeSocketIO:
    def __init__(self):
        self.emitted = []

    def emit(self, event, data, to=None):
        self.emitted.append((event, data, to))


def test_lichess_test_connection_sans_jeton_du_tout(monkeypatch):
    monkeypatch.setattr(cm, "load_config", lambda: dict(cm.DEFAULT_CONFIG))
    monkeypatch.setattr(server, "request", _FakeRequest("sid-1"))
    fake_sio = _FakeSocketIO()
    monkeypatch.setattr(server, "socketio", fake_sio)
    server.on_lichess_test_connection({"token": ""})
    assert fake_sio.emitted == [("lichess_test_result", {"status": "invalid"}, "sid-1")]


def test_lichess_test_connection_utilise_jeton_tape_en_priorite(monkeypatch):
    """Le jeton tapé (non enregistré) doit primer sur celui déjà en config."""
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "lichess_token": "lip_ancien0000000000"})
    monkeypatch.setattr(server, "request", _FakeRequest("sid-1"))
    fake_sio = _FakeSocketIO()
    monkeypatch.setattr(server, "socketio", fake_sio)

    seen_tokens = []

    def fake_test_token(token):
        seen_tokens.append(token)
        return {"status": "ok", "account": "x", "scopes": [], "has_board_play": False}

    monkeypatch.setattr(lichess_client, "test_token", fake_test_token)

    server.on_lichess_test_connection({"token": "lip_nouveau1111111111"})
    for _ in range(50):
        if fake_sio.emitted:
            break
        time.sleep(0.02)

    assert seen_tokens == ["lip_nouveau1111111111"]


def test_lichess_test_connection_exception_inattendue_ne_journalise_pas_le_jeton(monkeypatch, caplog):
    monkeypatch.setattr(cm, "load_config", lambda: dict(cm.DEFAULT_CONFIG))
    monkeypatch.setattr(server, "request", _FakeRequest("sid-1"))
    fake_sio = _FakeSocketIO()
    monkeypatch.setattr(server, "socketio", fake_sio)

    secret_token = "lip_secretsecretsecret"

    def fake_test_token(token):
        raise RuntimeError(f"boom with token {token}")  # ne doit jamais être journalisé tel quel

    monkeypatch.setattr(lichess_client, "test_token", fake_test_token)

    with caplog.at_level(logging.WARNING):
        server.on_lichess_test_connection({"token": secret_token})
        for _ in range(50):
            if fake_sio.emitted:
                break
            time.sleep(0.02)

    assert fake_sio.emitted == [("lichess_test_result", {"status": "network_error"}, "sid-1")]
    for record in caplog.records:
        assert secret_token not in record.getMessage()
        assert secret_token not in str(record.exc_info)


# ── i18n : nouvelles clés présentes dans les trois langues ──────────────────

NEW_I18N_KEYS = [
    "parametres.lichess.titre",
    "parametres.lichess.aide1",
    "parametres.lichess.aide2",
    "parametres.lichess.aide3",
    "parametres.lichess.token",
    "parametres.lichess.token_placeholder",
    "parametres.lichess.jeton_enregistre",
    "parametres.lichess.jeton_enregistre_sans_indice",
    "parametres.lichess.aucun_jeton",
    "parametres.lichess.supprimer_jeton",
    "parametres.lichess.tester",
    "parametres.lichess.toast.jeton_supprime",
    "parametres.lichess.resultat.compte",
    "parametres.lichess.resultat.board_play_ok",
    "parametres.lichess.resultat.board_play_manquant",
    "parametres.lichess.resultat.autres_droits",
    "parametres.lichess.resultat.limite",
    "parametres.lichess.resultat.reseau",
    "parametres.lichess.resultat.invalide",
]


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_nouvelles_cles_i18n_presentes(locale):
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in NEW_I18N_KEYS:
        assert key in data, f"{key} absente de {locale}.json"
        assert data[key], f"{key} vide dans {locale}.json"


# ── app.js : jamais d'innerHTML pour le texte renvoyé par Lichess ──────────

def test_appjs_resultat_lichess_utilise_textcontent():
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "nicsoft" / "web" / "static" / "app.js"
    src = path.read_text(encoding="utf-8")
    assert 'result.textContent = lignes.join(" — ");' in src
