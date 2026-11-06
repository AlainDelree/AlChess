"""
nicsoft/modes/opening_explorer/llm_functions.py — NicLink
Fonctions publiques d'explication/discussion/analyse LLM de l'Opening
Explorer (issue #275, extrait de llm_explainer.py). Réexportées sans
changement depuis llm_explainer.py, point d'entrée utilisé par
nicsoft/web/server.py.
"""

import http.client
import logging
import urllib.error

from nicsoft.modes.opening_explorer.llm_cache import load_cache, save_cache
from nicsoft.modes.opening_explorer.llm_provider import call_claude, call_openai
from nicsoft.modes.opening_explorer.llm_prompts import (
    ANALYSE_SYSTEM_PROMPTS,
    CHAT_SUFFIX,
    SYSTEM_PROMPTS,
    build_analyse_context_text,
    build_chat_prompt,
    build_user_prompt,
    extract_arrows,
)

logger = logging.getLogger("niclink.opening_explorer.llm")


def get_explanation(line_id, move_index, fen, move_san, opening_name, camp,
                     alternatives, language, config):
    """Retourne (explication, flèches) pédagogique du coup, via cache ou appel LLM.
    Retourne ("", []) silencieusement en cas d'absence de clé API ou d'erreur réseau.
    """
    api_key = (config or {}).get("llm_api_key", "")
    if not api_key:
        return "", []

    cache_key = f"{line_id}_{move_index}_{language}"
    cache = load_cache()
    if cache_key in cache:
        cached = cache[cache_key]
        if isinstance(cached, dict):
            return cached.get("text", ""), [tuple(a) for a in cached.get("arrows", [])]
        return cached, []  # entrées de cache créées avant l'ajout des flèches

    provider = (config or {}).get("llm_provider", "claude")
    model    = (config or {}).get("llm_model", "")
    prompt_sys  = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    prompt_user = build_user_prompt(fen, move_san, opening_name, alternatives)

    try:
        if provider == "openai":
            explanation = call_openai(prompt_sys, prompt_user, api_key, model)
        else:
            explanation = call_claude(prompt_sys, prompt_user, api_key, model)
    except (urllib.error.URLError, urllib.error.HTTPError, http.client.HTTPException,
            ConnectionError, KeyError, ValueError, TimeoutError) as e:
        logger.warning(f"[LLM_EXPLAINER] Appel {provider} échoué : {e}")
        return "", []

    explanation, arrows = extract_arrows((explanation or "").strip())
    if explanation:
        cache[cache_key] = {"text": explanation, "arrows": [list(a) for a in arrows]}
        save_cache(cache)
    return explanation, arrows


def get_chat_response(question, state, language, config):
    """Répond à une question libre de l'utilisateur sur la position courante.
    Retourne (réponse, flèches). Pas de cache (questions contextuelles et libres).
    Retourne ("", []) silencieusement en cas d'absence de clé API ou d'erreur réseau.
    """
    api_key = (config or {}).get("llm_api_key", "")
    if not api_key or not question:
        return "", []

    provider = (config or {}).get("llm_provider", "claude")
    model    = (config or {}).get("llm_model", "")
    prompt_sys  = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["fr"])
    prompt_sys += CHAT_SUFFIX.get(language, CHAT_SUFFIX["fr"])
    prompt_user = build_chat_prompt(question, state)

    try:
        if provider == "openai":
            response = call_openai(prompt_sys, prompt_user, api_key, model)
        else:
            response = call_claude(prompt_sys, prompt_user, api_key, model)
    except (urllib.error.URLError, urllib.error.HTTPError, http.client.HTTPException,
            ConnectionError, KeyError, ValueError, TimeoutError) as e:
        logger.warning(f"[LLM_EXPLAINER] Appel chat {provider} échoué : {e}")
        return "", []

    return extract_arrows((response or "").strip())


def get_analyse_response(messages, context, language, config):
    """Répond à un tour de conversation multi-tours sur une position de
    l'écran Analyse de partie. `messages` est l'historique complet
    ([{"role": "user"|"assistant", "content": str}, ...]) ; `context`
    contient fen/move/pgn de la position courante, injecté à chaque appel.
    Retourne (réponse, erreur) — un seul des deux est non vide/non None.
    Pas de cache (conversation libre, contexte changeant à chaque tour).
    """
    api_key = (config or {}).get("llm_api_key", "")
    if not api_key:
        return None, "no_api_key"

    clean_messages = [
        {"role": m.get("role"), "content": (m.get("content") or "").strip()}
        for m in (messages or [])
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ]
    if not clean_messages:
        return None, "empty"

    provider = (config or {}).get("llm_provider", "claude")
    model    = (config or {}).get("llm_model", "")
    prompt_sys = ANALYSE_SYSTEM_PROMPTS.get(language, ANALYSE_SYSTEM_PROMPTS["fr"])
    context_text = build_analyse_context_text(context)
    if context_text:
        prompt_sys = f"{prompt_sys}\n\nContexte de la position en cours :\n{context_text}"

    try:
        if provider == "openai":
            response = call_openai(prompt_sys, clean_messages, api_key, model)
        else:
            response = call_claude(prompt_sys, clean_messages, api_key, model)
    except (urllib.error.URLError, urllib.error.HTTPError, http.client.HTTPException,
            ConnectionError, KeyError, ValueError, TimeoutError) as e:
        logger.warning(f"[LLM_EXPLAINER] Appel analyse {provider} échoué : {e}")
        return None, str(e)

    return (response or "").strip(), None
