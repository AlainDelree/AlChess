"""
nicsoft/modes/opening_explorer/llm_explainer.py — NicLink
Génère une courte explication pédagogique d'un coup d'ouverture via un LLM
externe (Claude ou OpenAI), avec cache disque pour éviter les appels
réseau répétés sur une même ligne/coup/langue.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request

from nicsoft.config import DATA_DIR

logger = logging.getLogger("niclink.opening_explorer.llm")

CACHE_FILE = DATA_DIR / "explorer_cache.json"

_ARROWS_INSTRUCTION = {
    "fr": (
        " À la fin de ta réponse, ajoute obligatoirement une ligne exactement "
        "de cette forme : [FLECHES: e2-e4, d7-d5] listant en notation "
        "algébrique les cases de départ et d'arrivée des coups que tu "
        "mentionnes (2 à 4 flèches maximum). Cette ligne sera retirée avant "
        "affichage."
    ),
    "en": (
        " At the end of your response, always add a line exactly like this: "
        "[ARROWS: e2-e4, d7-d5] listing the start and end squares of the "
        "moves you mention (2 to 4 arrows maximum). This line will be "
        "removed before display."
    ),
    "de": (
        " Füge am Ende deiner Antwort unbedingt eine Zeile genau in dieser "
        "Form hinzu: [PFEILE: e2-e4, d7-d5] mit den Start- und Zielfeldern "
        "der von dir erwähnten Züge (maximal 2 bis 4 Pfeile). Diese Zeile "
        "wird vor der Anzeige entfernt."
    ),
}

_SYSTEM_PROMPTS = {
    "fr": (
        "Tu es un entraîneur d'échecs. Explique les coups d'une ouverture à "
        "un joueur débutant en 2-3 phrases maximum. Sois direct et factuel, "
        "sans flatterie, sans titre, sans émoji. Ne commence pas par le nom "
        "de l'ouverture ni par une formule d'accroche. Utilise les termes "
        "français : Blancs, Noirs, cavalier, fou, tour, dame, roi. Réponds "
        "uniquement en français."
        + _ARROWS_INSTRUCTION["fr"]
    ),
    "en": (
        "You are a chess coach. Explain the moves of an opening to a "
        "beginner player in 2-3 sentences maximum. Be direct and factual, "
        "without flattery, without a title, without emoji. Do not start "
        "with the name of the opening or a catchy opening line. Answer "
        "only in English."
        + _ARROWS_INSTRUCTION["en"]
    ),
    "de": (
        "Du bist ein Schachtrainer. Erkläre die Züge einer Eröffnung einem "
        "Anfänger in maximal 2-3 Sätzen. Sei direkt und sachlich, ohne "
        "Schmeicheleien, ohne Titel, ohne Emoji. Beginne nicht mit dem "
        "Namen der Eröffnung oder einer einleitenden Floskel. Antworte "
        "ausschließlich auf Deutsch."
        + _ARROWS_INSTRUCTION["de"]
    ),
}

_ARROW_LINE_RE = re.compile(r'\[(?:FLECHES|ARROWS|PFEILE):\s*([^\]]+)\]')
_SQUARE_RE = re.compile(r'^[a-h][1-8]$')


def extract_arrows(text):
    """Retire du texte la ligne [FLECHES: e2-e4, d7-d5] (ou ARROWS/PFEILE selon
    la langue) ajoutée par le LLM et retourne les flèches qu'elle décrit.

    Retourne (texte_nettoye, flèches) où flèches est une liste de tuples
    (case_depart, case_arrivee), au maximum 4, avec cases invalides ou
    identiques ignorées. Si aucune ligne ne correspond, retourne le texte
    tel quel et une liste vide.
    """
    text = text or ""
    lines = text.splitlines()
    match = None
    line_index = None
    for i in range(len(lines) - 1, -1, -1):
        m = _ARROW_LINE_RE.search(lines[i])
        if m:
            match = m
            line_index = i
            break
    if match is None:
        return text.strip(), []

    arrows = []
    for pair in match.group(1).split(","):
        pair = pair.strip()
        if "-" not in pair:
            continue
        start, end = pair.split("-", 1)
        start, end = start.strip().lower(), end.strip().lower()
        if _SQUARE_RE.match(start) and _SQUARE_RE.match(end) and start != end:
            arrows.append((start, end))
    arrows = arrows[:4]

    clean_lines = lines[:line_index] + lines[line_index + 1:]
    clean_text = "\n".join(clean_lines).strip()
    return clean_text, arrows

_CHAT_SUFFIX = {
    "fr": " Tu réponds aussi aux questions libres de l'utilisateur sur la position.",
    "en": " You also answer the user's free-form questions about the position.",
    "de": " Du beantwortest auch die freien Fragen des Benutzers zur Stellung.",
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
    import chess as _chess
    try:
        board = _chess.Board(fen)
        player = "Noirs" if board.turn == _chess.WHITE else "Blancs"
    except Exception:
        player = "le joueur"
    if alternatives:
        alt_text = ", ".join(a.get("san", a.get("uci", "")) for a in alternatives[:3])
        alt_line = f"Réponses probables de l'adversaire : {alt_text}.\n"
    else:
        alt_line = ""
    return (
        f"Ouverture : {opening_name}. Les {player} viennent de jouer : {move_san}.\n"
        f"Position FEN : {fen}.\n"
        f"{alt_line}"
        f"Explique en 2-3 phrases pourquoi les {player} ont joué {move_san} ici. "
        f"Parle uniquement de ce coup. Ne mentionne pas les coups futurs de l'adversaire."
    )


def _call_claude(prompt_sys: str, messages, api_key: str, model: str) -> str:
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


def _call_openai(prompt_sys: str, messages, api_key: str, model: str) -> str:
    """messages : liste de {"role": "user"|"assistant", "content": str}, ou une
    simple chaîne (raccourci équivalent à [{"role": "user", "content": messages}])."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    body = json.dumps({
        "model": model or "gpt-4o-mini",
        "max_tokens": 300,
        "messages": [{"role": "system", "content": prompt_sys}] + messages,
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
                     alternatives, language, config):
    """Retourne (explication, flèches) pédagogique du coup, via cache ou appel LLM.
    Retourne ("", []) silencieusement en cas d'absence de clé API ou d'erreur réseau.
    """
    api_key = (config or {}).get("llm_api_key", "")
    if not api_key:
        return "", []

    cache_key = f"{line_id}_{move_index}_{language}"
    cache = _load_cache()
    if cache_key in cache:
        cached = cache[cache_key]
        if isinstance(cached, dict):
            return cached.get("text", ""), [tuple(a) for a in cached.get("arrows", [])]
        return cached, []  # entrées de cache créées avant l'ajout des flèches

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
        return "", []

    explanation, arrows = extract_arrows((explanation or "").strip())
    if explanation:
        cache[cache_key] = {"text": explanation, "arrows": [list(a) for a in arrows]}
        _save_cache(cache)
    return explanation, arrows


def _build_chat_prompt(question, state) -> str:
    state = state or {}
    return (
        f"Ouverture : {state.get('opening_name', '')}. "
        f"Position actuelle (FEN) : {state.get('fen', '')}.\n"
        f"Dernier coup joué : {state.get('move_san', '')} "
        f"(coup {state.get('move_index', 0)}).\n"
        f"Question de l'élève : {question}"
    )


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
    prompt_sys  = _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS["fr"])
    prompt_sys += _CHAT_SUFFIX.get(language, _CHAT_SUFFIX["fr"])
    prompt_user = _build_chat_prompt(question, state)

    try:
        if provider == "openai":
            response = _call_openai(prompt_sys, prompt_user, api_key, model)
        else:
            response = _call_claude(prompt_sys, prompt_user, api_key, model)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError) as e:
        logger.warning(f"[LLM_EXPLAINER] Appel chat {provider} échoué : {e}")
        return "", []

    return extract_arrows((response or "").strip())


# ── Écran Analyse de partie — conversation multi-tours (issue #196) ─────────

_ANALYSE_SYSTEM_PROMPTS = {
    "fr": (
        "Tu es un entraîneur d'échecs qui aide un joueur à analyser une "
        "partie déjà jouée. Réponds aux questions en te basant sur la "
        "position, le coup courant et le PGN fournis en contexte. Sois "
        "direct et factuel, sans flatterie, sans émoji. Réponds uniquement "
        "en français."
    ),
    "en": (
        "You are a chess coach helping a player analyse a game they have "
        "already played. Answer questions based on the position, the "
        "current move and the PGN given as context. Be direct and "
        "factual, without flattery, without emoji. Answer only in English."
    ),
    "de": (
        "Du bist ein Schachtrainer, der einem Spieler hilft, eine bereits "
        "gespielte Partie zu analysieren. Beantworte Fragen anhand der "
        "Stellung, des aktuellen Zuges und des im Kontext angegebenen PGN. "
        "Sei direkt und sachlich, ohne Schmeicheleien, ohne Emoji. "
        "Antworte ausschließlich auf Deutsch."
    ),
}


def _build_analyse_context_text(context) -> str:
    context = context or {}
    fen  = (context.get("fen") or "").strip()
    move = (context.get("move") or "").strip()
    pgn  = (context.get("pgn") or "").strip()
    lines = []
    if fen:
        lines.append(f"Position actuelle (FEN) : {fen}")
    if move:
        lines.append(f"Coup actuel : {move}")
    if pgn:
        lines.append(f"PGN de la partie :\n{pgn}")
    return "\n".join(lines)


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
    prompt_sys = _ANALYSE_SYSTEM_PROMPTS.get(language, _ANALYSE_SYSTEM_PROMPTS["fr"])
    context_text = _build_analyse_context_text(context)
    if context_text:
        prompt_sys = f"{prompt_sys}\n\nContexte de la position en cours :\n{context_text}"

    try:
        if provider == "openai":
            response = _call_openai(prompt_sys, clean_messages, api_key, model)
        else:
            response = _call_claude(prompt_sys, clean_messages, api_key, model)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError) as e:
        logger.warning(f"[LLM_EXPLAINER] Appel analyse {provider} échoué : {e}")
        return None, str(e)

    return (response or "").strip(), None
