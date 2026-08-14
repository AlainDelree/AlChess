"""
nicsoft/modes/opening_explorer/llm_explainer.py — NicLink
Génère une courte explication pédagogique d'un coup d'ouverture via un LLM
externe (Claude ou OpenAI), avec cache disque pour éviter les appels
réseau répétés sur une même ligne/coup/langue.
"""

import json
import logging
import os
import urllib.error
import urllib.request

from nicsoft.config import DATA_DIR

logger = logging.getLogger("niclink.opening_explorer.llm")

CACHE_FILE = DATA_DIR / "explorer_cache.json"

_SYSTEM_PROMPTS = {
    "fr": (
        "Tu es un entraîneur d'échecs pédagogue. Explique les coups d'une "
        "ouverture à un joueur débutant. Sois concis (3-4 phrases maximum), "
        "clair et encourageant. Réponds uniquement en français."
    ),
    "en": (
        "You are a friendly chess coach. Explain opening moves to a "
        "beginner player. Be concise (3-4 sentences maximum), clear and "
        "encouraging. Answer only in English."
    ),
    "de": (
        "Du bist ein pädagogischer Schachtrainer. Erkläre die Züge einer "
        "Eröffnung einem Anfänger. Sei prägnant (maximal 3-4 Sätze), klar "
        "und ermutigend. Antworte ausschließlich auf Deutsch."
    ),
}


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, CACHE_FILE)


def _build_user_prompt(fen, move_san, opening_name, alternatives) -> str:
    if alternatives:
        alt_text = ", ".join(a.get("uci", "") for a in alternatives[:2])
    else:
        alt_text = "aucune"
    return (
        f"Ouverture : {opening_name}. Le coup vient d'être joué : {move_san}.\n"
        f"Position FEN : {fen}.\n"
        f"Alternatives connues : {alt_text}.\n"
        f"Explique pourquoi ce coup est joué ici."
    )


def _call_claude(prompt_sys: str, prompt_user: str, api_key: str, model: str) -> str:
    body = json.dumps({
        "model": model or "claude-haiku-4-5",
        "max_tokens": 300,
        "system": prompt_sys,
        "messages": [{"role": "user", "content": prompt_user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
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


def _call_openai(prompt_sys: str, prompt_user: str, api_key: str, model: str) -> str:
    body = json.dumps({
        "model": model or "gpt-4o-mini",
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": prompt_sys},
            {"role": "user", "content": prompt_user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
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


def get_explanation(line_id, move_index, fen, move_san, opening_name, camp,
                     alternatives, language, config) -> str:
    """Retourne une explication pédagogique du coup, via cache ou appel LLM.
    Retourne "" silencieusement en cas d'absence de clé API ou d'erreur réseau.
    """
    api_key = (config or {}).get("llm_api_key", "")
    if not api_key:
        return ""

    cache_key = f"{line_id}_{move_index}_{language}"
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    provider = (config or {}).get("llm_provider", "claude")
    model    = (config or {}).get("llm_model", "")
    prompt_sys  = _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS["fr"])
    prompt_user = _build_user_prompt(fen, move_san, opening_name, alternatives)

    try:
        if provider == "openai":
            explanation = _call_openai(prompt_sys, prompt_user, api_key, model)
        else:
            explanation = _call_claude(prompt_sys, prompt_user, api_key, model)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError) as e:
        logger.warning(f"[LLM_EXPLAINER] Appel {provider} échoué : {e}")
        return ""

    explanation = (explanation or "").strip()
    if explanation:
        cache[cache_key] = explanation
        _save_cache(cache)
    return explanation
