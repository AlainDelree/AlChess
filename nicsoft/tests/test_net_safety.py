"""
nicsoft/tests/test_net_safety.py — NicLink
Test de la vérification de schéma avant ouverture d'une adresse distante
avec urllib (issue #288, famille B de l'audit sécurité : bandit B310 /
ruff S310). Aucun accès réseau — `urllib.request.urlopen` est systématiquement
mocké pour garantir qu'aucune requête n'est tentée quand l'adresse est
refusée.
"""
from unittest.mock import patch

import pytest

from nicsoft.utils.net_safety import ensure_https


def test_ensure_https_accepte_une_adresse_https():
    ensure_https("https://example.com/api")  # ne lève rien


@pytest.mark.parametrize("url", [
    "http://example.com/api",   # http distant — refusé, seule l'adresse locale y a droit
    "file:///etc/passwd",
    "ftp://example.com/api",
    "example.com/api",          # sans schéma
])
def test_ensure_https_refuse_les_schemas_non_https(url):
    with pytest.raises(ValueError, match="https"):
        ensure_https(url)


def test_download_wikitext_refuse_une_adresse_non_https(monkeypatch):
    from nicsoft.modes.exercices import download_eco_wiki

    monkeypatch.setattr(download_eco_wiki, "API_URL", "http://en.wikipedia.org/w/api.php")
    with patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(ValueError, match="https"):
            download_eco_wiki.download_wikitext()
    mock_urlopen.assert_not_called()


def test_call_claude_adresse_https_constante_acceptee(monkeypatch):
    from nicsoft.modes.opening_explorer import llm_provider

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"content": [{"text": "ok"}]}'

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as mock_urlopen:
        result = llm_provider.call_claude("sys", "bonjour", "fake-key", "claude-haiku-4-5")
    mock_urlopen.assert_called_once()
    assert result == "ok"


def test_call_claude_refuse_si_l_adresse_constante_devient_non_https(monkeypatch):
    from nicsoft.modes.opening_explorer import llm_provider

    monkeypatch.setattr(llm_provider, "_CLAUDE_URL", "http://api.anthropic.com/v1/messages")
    with patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(ValueError, match="https"):
            llm_provider.call_claude("sys", "bonjour", "fake-key", "claude-haiku-4-5")
    mock_urlopen.assert_not_called()


def test_check_internet_refuse_si_l_adresse_edge_tts_devient_non_https(monkeypatch):
    from nicsoft.modes.opening_explorer import tts_engine

    def fake_urlopen(url, timeout=None):
        raise AssertionError("ne doit jamais être appelé quand le schéma est refusé")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(tts_engine, "ensure_https", lambda url: (_ for _ in ()).throw(ValueError("https requis")))
    monkeypatch.setattr("socket.socket.connect", lambda self, addr: (_ for _ in ()).throw(OSError("pas de réseau en test")))
    assert tts_engine.check_internet() is False
