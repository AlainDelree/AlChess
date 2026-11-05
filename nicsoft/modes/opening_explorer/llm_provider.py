"""
nicsoft/modes/opening_explorer/llm_provider.py — NicLink
Accès bas niveau aux fournisseurs de LLM externes (Claude, OpenAI) pour
l'Opening Explorer (issue #275, extrait de llm_explainer.py) : construit la
requête HTTP et retourne le texte brut de la réponse. Ne journalise jamais
la clé d'API ni l'adresse complète de la requête.
"""

import json
import urllib.error
import urllib.request

from nicsoft.utils.net_safety import ensure_https

_CLAUDE_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def call_claude(prompt_sys: str, messages, api_key: str, model: str) -> str:
    """messages : liste de {"role": "user"|"assistant", "content": str}, ou une
    simple chaîne (raccourci équivalent à [{"role": "user", "content": messages}])."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    body = json.dumps({
        "model": model or "claude-haiku-4-5",
        "max_tokens": 300,
        "system": prompt_sys,
        "messages": messages,
    }).encode("utf-8")
    ensure_https(_CLAUDE_URL)
    req = urllib.request.Request(
        _CLAUDE_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["content"][0]["text"]


def call_openai(prompt_sys: str, messages, api_key: str, model: str) -> str:
    """messages : liste de {"role": "user"|"assistant", "content": str}, ou une
    simple chaîne (raccourci équivalent à [{"role": "user", "content": messages}])."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    body = json.dumps({
        "model": model or "gpt-4o-mini",
        "max_tokens": 300,
        "messages": [{"role": "system", "content": prompt_sys}] + messages,
    }).encode("utf-8")
    ensure_https(_OPENAI_URL)
    req = urllib.request.Request(
        _OPENAI_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]
