"""
nicsoft/tests/test_llm_cache.py — NicLink
Test du cache disque des explications LLM (issue #275, découpage de
llm_explainer.py en modules cohérents) : round-trip load/save, cache
absent, JSON corrompu ignoré sans lever d'exception. Aucun accès réseau ;
CACHE_FILE/DATA_DIR sont remplacés par un répertoire temporaire pour ne
jamais toucher le cache réel de l'application.
"""
from nicsoft.modes.opening_explorer import llm_cache


def test_load_cache_fichier_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_cache, "CACHE_FILE", tmp_path / "explorer_cache.json")
    assert llm_cache.load_cache() == {}


def test_save_puis_load_cache_round_trip(tmp_path, monkeypatch):
    cache_file = tmp_path / "explorer_cache.json"
    monkeypatch.setattr(llm_cache, "CACHE_FILE", cache_file)
    monkeypatch.setattr(llm_cache, "DATA_DIR", tmp_path)
    data = {"line1_0_fr": {"text": "Explication.", "arrows": [["e2", "e4"]]}}
    llm_cache.save_cache(data)
    assert cache_file.exists()
    assert llm_cache.load_cache() == data


def test_load_cache_json_corrompu_ignore(tmp_path, monkeypatch):
    cache_file = tmp_path / "explorer_cache.json"
    cache_file.write_text("{ceci n'est pas du JSON", encoding="utf-8")
    monkeypatch.setattr(llm_cache, "CACHE_FILE", cache_file)
    assert llm_cache.load_cache() == {}
