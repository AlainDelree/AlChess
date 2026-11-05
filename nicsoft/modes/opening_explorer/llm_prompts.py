"""
nicsoft/modes/opening_explorer/llm_prompts.py — NicLink
Construction des consignes (system/user prompts) envoyées au LLM pour
l'Opening Explorer, et extraction des flèches qu'il renvoie en fin de
réponse (issue #275, extrait de llm_explainer.py).
"""

import logging
import re

logger = logging.getLogger("niclink.opening_explorer.llm")

ARROWS_INSTRUCTION = {
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

SYSTEM_PROMPTS = {
    "fr": (
        "Tu es un entraîneur d'échecs. Explique les coups d'une ouverture à "
        "un joueur débutant en 2-3 phrases maximum. Sois direct et factuel, "
        "sans flatterie, sans titre, sans émoji. Ne commence pas par le nom "
        "de l'ouverture ni par une formule d'accroche. Utilise les termes "
        "français : Blancs, Noirs, cavalier, fou, tour, dame, roi. Réponds "
        "uniquement en français."
        + ARROWS_INSTRUCTION["fr"]
    ),
    "en": (
        "You are a chess coach. Explain the moves of an opening to a "
        "beginner player in 2-3 sentences maximum. Be direct and factual, "
        "without flattery, without a title, without emoji. Do not start "
        "with the name of the opening or a catchy opening line. Answer "
        "only in English."
        + ARROWS_INSTRUCTION["en"]
    ),
    "de": (
        "Du bist ein Schachtrainer. Erkläre die Züge einer Eröffnung einem "
        "Anfänger in maximal 2-3 Sätzen. Sei direkt und sachlich, ohne "
        "Schmeicheleien, ohne Titel, ohne Emoji. Beginne nicht mit dem "
        "Namen der Eröffnung oder einer einleitenden Floskel. Antworte "
        "ausschließlich auf Deutsch."
        + ARROWS_INSTRUCTION["de"]
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


CHAT_SUFFIX = {
    "fr": " Tu réponds aussi aux questions libres de l'utilisateur sur la position.",
    "en": " You also answer the user's free-form questions about the position.",
    "de": " Du beantwortest auch die freien Fragen des Benutzers zur Stellung.",
}


def build_user_prompt(fen, move_san, opening_name, alternatives) -> str:
    import chess as _chess
    try:
        board = _chess.Board(fen)
        player = "Noirs" if board.turn == _chess.WHITE else "Blancs"
    except Exception as e:
        logger.debug(f"build_user_prompt(): détermination du genre grammatical échouée, fallback neutre: {e}")
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


def build_chat_prompt(question, state) -> str:
    state = state or {}
    return (
        f"Ouverture : {state.get('opening_name', '')}. "
        f"Position actuelle (FEN) : {state.get('fen', '')}.\n"
        f"Dernier coup joué : {state.get('move_san', '')} "
        f"(coup {state.get('move_index', 0)}).\n"
        f"Question de l'élève : {question}"
    )


# ── Écran Analyse de partie — conversation multi-tours (issue #196) ─────────

ANALYSE_SYSTEM_PROMPTS = {
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


def build_analyse_context_text(context) -> str:
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
