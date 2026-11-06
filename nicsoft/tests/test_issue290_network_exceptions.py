"""
nicsoft/tests/test_issue290_network_exceptions.py — NicLink
Issue #290 (suite #288) : les resserrements réseau de la #288 ne
couvraient que `(urllib.error.URLError, urllib.error.HTTPError, KeyError,
ValueError, TimeoutError)` autour des appels LLM (Claude/OpenAI). Une
coupure de connexion en cours de réponse (reset réseau, proxy,
load-balancer) lève `http.client.RemoteDisconnected`, qui dérive de
`ConnectionResetError` + `http.client.BadStatusLine` — ni l'un ni
l'autre n'est une sous-classe des types listés. Sans accès réseau réel :
`call_claude`/`call_openai` sont simplement remplacées par une fonction
qui lève l'exception concernée.

`nicsoft/web/launcher.py` a le même défaut (boucle d'attente du
démarrage de Flask), mais ce module importe `gi` (PyGObject, dépendance
desktop GTK) absent de cet environnement — déjà non testable
automatiquement avant cette issue (limitation documentée par la #288) ;
vérifié par lecture uniquement.
"""
import http.client

import pytest

from nicsoft.modes.opening_explorer import llm_functions

_CONFIG = {"llm_api_key": "fake-key-not-a-real-secret", "llm_provider": "claude"}


def _leve_remote_disconnected(*_args, **_kwargs):
    raise http.client.RemoteDisconnected("le serveur a fermé la connexion")


def test_get_explanation_absorbe_remote_disconnected(monkeypatch):
    monkeypatch.setattr(llm_functions, "call_claude", _leve_remote_disconnected)
    text, arrows = llm_functions.get_explanation(
        "issue290_test_explanation_never_cached", 0, "fen", "e4",
        "Ouverture test", "white", [], "fr", _CONFIG,
    )
    assert (text, arrows) == ("", [])


def test_get_chat_response_absorbe_remote_disconnected(monkeypatch):
    monkeypatch.setattr(llm_functions, "call_claude", _leve_remote_disconnected)
    text, arrows = llm_functions.get_chat_response("Pourquoi ce coup ?", {}, "fr", _CONFIG)
    assert (text, arrows) == ("", [])


def test_get_analyse_response_absorbe_remote_disconnected(monkeypatch):
    monkeypatch.setattr(llm_functions, "call_claude", _leve_remote_disconnected)
    response, erreur = llm_functions.get_analyse_response(
        [{"role": "user", "content": "Explique la position"}], {}, "fr", _CONFIG,
    )
    assert response is None
    assert "fermé la connexion" in erreur
