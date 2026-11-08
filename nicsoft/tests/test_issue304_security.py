"""
nicsoft/tests/test_issue304_security.py — NicLink

Issue #304 (suite de #302/#303) :
  (1) la clé API LLM n'est plus jamais envoyée au navigateur — config_get
      ne renvoie qu'un indicateur de présence (has_llm_api_key) et, si la
      clé fait au moins 12 caractères, ses 4 derniers caractères comme
      indice (llm_api_key_hint) ; config_save traite un champ vide comme
      "clé inchangée" et llm_api_key_delete=True comme suppression
      explicite.
  (2) les routes HTTP à effet de bord (POST /toggle-autoupdate,
      POST /test/save-config) exigent un en-tête Origin autorisé (même
      règle que Socket.IO, _is_allowed_origin) ; ces deux routes et les
      routes de lecture sensibles (/logs, /debug/*) exigent un en-tête Host
      égal à 127.0.0.1 ou localhost sur le port du serveur — sans quoi 403.

Tests sans matériel, client de test Flask — aucun échiquier requis.
"""
import pytest
import nicsoft.web.server as server
from nicsoft.core import config_manager as cm


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _server_port(monkeypatch):
    """Fixe un port connu pour _is_allowed_host(), restauré après chaque test."""
    server.set_server_port(5000)
    yield
    server.set_server_port(None)


@pytest.fixture
def client():
    return server.app.test_client()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirige config.json vers un fichier temporaire — n'écrit jamais dans
    la vraie data/config.json d'Alain pendant les tests."""
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg_file)
    return cfg_file


# ── _is_allowed_host ──────────────────────────────────────────────────────────

def test_is_allowed_host_127():
    assert server._is_allowed_host("127.0.0.1:5000")


def test_is_allowed_host_localhost():
    assert server._is_allowed_host("localhost:5000")


def test_is_allowed_host_etranger_refuse():
    assert not server._is_allowed_host("evil.example.com")


def test_is_allowed_host_mauvais_port_refuse():
    assert not server._is_allowed_host("127.0.0.1:5001")


def test_is_allowed_host_absent_refuse():
    assert not server._is_allowed_host("")


def test_is_allowed_host_sans_port_serveur_refuse():
    server.set_server_port(None)
    assert not server._is_allowed_host("127.0.0.1:5000")


# ── Routes de lecture sensibles : /logs, /debug/* ────────────────────────────

def test_logs_host_etranger_refuse(client):
    r = client.get("/logs", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_logs_host_127_accepte(client):
    r = client.get("/logs", headers={"Host": "127.0.0.1:5000"})
    assert r.status_code != 403


def test_logs_host_localhost_accepte(client):
    r = client.get("/logs", headers={"Host": "localhost:5000"})
    assert r.status_code != 403


def test_debug_mode_host_etranger_refuse(client):
    r = client.get("/debug/mode", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_debug_mode_host_127_accepte(client):
    r = client.get("/debug/mode", headers={"Host": "127.0.0.1:5000"})
    assert r.status_code == 200


def test_debug_mark_host_etranger_refuse_avant_meme_le_mode_debug(client, monkeypatch):
    monkeypatch.setattr(server, "DEBUG_MODE", True)
    r = client.get("/debug/mark", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_debug_mark_host_ok_mode_debug_actif(client, monkeypatch):
    monkeypatch.setattr(server, "DEBUG_MODE", True)
    r = client.get("/debug/mark", headers={"Host": "127.0.0.1:5000"})
    assert r.status_code == 200


# ── Routes à effet de bord : POST /toggle-autoupdate, POST /test/save-config ─

def test_toggle_autoupdate_sans_origin_refuse(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "NO_UPDATE_FILE", tmp_path / "no-update.txt")
    r = client.post("/toggle-autoupdate", headers={"Host": "127.0.0.1:5000"})
    assert r.status_code == 403


def test_toggle_autoupdate_origin_etranger_refuse(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "NO_UPDATE_FILE", tmp_path / "no-update.txt")
    r = client.post("/toggle-autoupdate", headers={
        "Origin": "https://evil.example.com", "Host": "127.0.0.1:5000",
    })
    assert r.status_code == 403


def test_toggle_autoupdate_origin_ok_host_etranger_refuse(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "NO_UPDATE_FILE", tmp_path / "no-update.txt")
    r = client.post("/toggle-autoupdate", headers={
        "Origin": "http://127.0.0.1:5000", "Host": "evil.example.com",
    })
    assert r.status_code == 403


def test_toggle_autoupdate_origin_et_host_ok_succes(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "NO_UPDATE_FILE", tmp_path / "no-update.txt")
    r = client.post("/toggle-autoupdate", headers={
        "Origin": "http://127.0.0.1:5000", "Host": "127.0.0.1:5000",
    })
    assert r.status_code == 200


def test_test_save_config_sans_origin_refuse(client, monkeypatch):
    monkeypatch.setattr(server, "TEST_MODE", "random")
    r = client.post("/test/save-config", headers={"Host": "127.0.0.1:5000"}, json={})
    assert r.status_code == 403


def test_test_save_config_origin_et_host_ok_succes(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "TEST_MODE", "random")
    monkeypatch.setattr(server, "TEST_CONFIG_DIR", tmp_path / "Test config")
    r = client.post("/test/save-config", headers={
        "Origin": "http://127.0.0.1:5000", "Host": "127.0.0.1:5000",
    }, json={})
    assert r.status_code == 200


def test_test_save_config_mode_inactif_refuse_meme_avec_origin_et_host_ok(client, monkeypatch):
    monkeypatch.setattr(server, "TEST_MODE", "")
    r = client.post("/test/save-config", headers={
        "Origin": "http://127.0.0.1:5000", "Host": "127.0.0.1:5000",
    }, json={})
    assert r.status_code == 403


# ── config_get : jamais la clé API, seulement indicateur + indice ───────────

def test_config_get_cle_longue_indicateur_et_indice(monkeypatch):
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "llm_api_key": "sk-test-1234567890"})
    captured = {}
    monkeypatch.setattr(server, "emit", lambda event, data: captured.update(event=event, data=data))
    server.on_config_get({})
    assert "llm_api_key" not in captured["data"]
    assert captured["data"]["has_llm_api_key"] is True
    assert captured["data"]["llm_api_key_hint"] == "7890"


def test_config_get_cle_courte_aucun_indice(monkeypatch):
    monkeypatch.setattr(cm, "load_config",
                         lambda: {**cm.DEFAULT_CONFIG, "llm_api_key": "sk-123"})
    captured = {}
    monkeypatch.setattr(server, "emit", lambda event, data: captured.update(event=event, data=data))
    server.on_config_get({})
    assert "llm_api_key" not in captured["data"]
    assert captured["data"]["has_llm_api_key"] is True
    assert captured["data"]["llm_api_key_hint"] == ""


def test_config_get_sans_cle(monkeypatch):
    monkeypatch.setattr(cm, "load_config", lambda: dict(cm.DEFAULT_CONFIG))
    captured = {}
    monkeypatch.setattr(server, "emit", lambda event, data: captured.update(event=event, data=data))
    server.on_config_get({})
    assert "llm_api_key" not in captured["data"]
    assert captured["data"]["has_llm_api_key"] is False
    assert captured["data"]["llm_api_key_hint"] == ""


# ── config_save : champ vide = inchangée, valeur = remplacée, suppression ──

def test_config_save_champ_vide_conserve_la_cle(isolated_config, monkeypatch):
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)
    cm.save_config({"llm_api_key": "sk-test-1234567890"})
    server.on_config_save({"llm_api_key": "", "llm_provider": "claude"})
    assert cm.load_config()["llm_api_key"] == "sk-test-1234567890"


def test_config_save_valeur_remplace_la_cle(isolated_config, monkeypatch):
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)
    cm.save_config({"llm_api_key": "sk-old-0000000000"})
    server.on_config_save({"llm_api_key": "sk-new-1111111111"})
    assert cm.load_config()["llm_api_key"] == "sk-new-1111111111"


def test_config_save_suppression_explicite(isolated_config, monkeypatch):
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)
    cm.save_config({"llm_api_key": "sk-test-1234567890"})
    server.on_config_save({"llm_api_key": "", "llm_api_key_delete": True})
    assert cm.load_config()["llm_api_key"] == ""


def test_config_save_ne_renvoie_jamais_la_cle(isolated_config, monkeypatch):
    """config_saved ne doit jamais porter la clé, même en écho."""
    captured = []
    monkeypatch.setattr(server, "emit", lambda event, data: captured.append((event, data)))
    cm.save_config({"llm_api_key": "sk-test-1234567890"})
    server.on_config_save({"llm_api_key": "sk-nouvelle-cle-999999"})
    assert len(captured) == 1
    event, data = captured[0]
    assert event == "config_saved"
    assert "llm_api_key" not in data


# ── i18n : nouvelles clés présentes dans les trois langues ──────────────────

NEW_I18N_KEYS = [
    "parametres.llm.api_key_placeholder",
    "parametres.llm.cle_enregistree",
    "parametres.llm.cle_enregistree_sans_indice",
    "parametres.llm.aucune_cle",
    "parametres.llm.supprimer_cle",
    "parametres.toast.cle_supprimee",
]


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_nouvelles_cles_i18n_presentes(locale):
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in NEW_I18N_KEYS:
        assert key in data, f"{key} absente de {locale}.json"
        assert data[key], f"{key} vide dans {locale}.json"


# ── app.js : l'indicateur de présence de clé utilise le booléen serveur ────

def test_appjs_indicateur_cle_utilise_has_llm_api_key():
    import re
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "nicsoft" / "web" / "static" / "app.js"
    src = path.read_text(encoding="utf-8")
    assert "_explHasApiKey = !!data.has_llm_api_key;" in src
    # La clé elle-même (pas son indicateur/indice) ne doit plus être lue sur
    # l'objet config reçu du serveur.
    assert not re.search(r"data\.llm_api_key\b(?!_)", src)
