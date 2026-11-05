"""
nicsoft/tests/test_llm_prompts.py — NicLink
Test des fonctions de construction des consignes LLM et d'extraction des
flèches (issue #275, découpage de llm_explainer.py en modules cohérents).
Fonctions pures, aucun accès réseau.
"""
from nicsoft.modes.opening_explorer.llm_prompts import (
    build_analyse_context_text,
    build_chat_prompt,
    build_user_prompt,
    extract_arrows,
)

_FEN_NOIRS_A_JOUER = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def test_build_user_prompt_contient_fen_coup_et_ouverture():
    prompt = build_user_prompt(
        fen=_FEN_NOIRS_A_JOUER,
        move_san="e4",
        opening_name="Ouverture du pion roi",
        alternatives=[],
    )
    assert "Ouverture du pion roi" in prompt
    assert "e4" in prompt
    assert "Blancs" in prompt  # trait aux noirs -> coup joué par les blancs


def test_build_user_prompt_avec_alternatives():
    prompt = build_user_prompt(
        fen=_FEN_NOIRS_A_JOUER,
        move_san="e4",
        opening_name="Ouverture du pion roi",
        alternatives=[{"san": "e5"}, {"san": "c5"}],
    )
    assert "e5" in prompt and "c5" in prompt


def test_build_user_prompt_fen_invalide_fallback_neutre():
    prompt = build_user_prompt(
        fen="fen-invalide", move_san="e4", opening_name="X", alternatives=[],
    )
    assert "le joueur" in prompt


def test_build_chat_prompt_inclut_question_et_etat():
    prompt = build_chat_prompt(
        "Pourquoi ce coup ?",
        {"opening_name": "Défense sicilienne", "fen": "fen", "move_san": "c4", "move_index": 2},
    )
    assert "Pourquoi ce coup ?" in prompt
    assert "Défense sicilienne" in prompt
    assert "c4" in prompt


def test_build_chat_prompt_etat_absent():
    prompt = build_chat_prompt("Question ?", None)
    assert "Question ?" in prompt


def test_build_analyse_context_text_champs_presents():
    text = build_analyse_context_text({"fen": "fen1", "move": "e4", "pgn": "1.e4 e5"})
    assert "fen1" in text and "e4" in text and "1.e4 e5" in text


def test_build_analyse_context_text_vide():
    assert build_analyse_context_text({}) == ""
    assert build_analyse_context_text(None) == ""


def test_extract_arrows_supprime_la_ligne_et_retourne_les_fleches():
    clean, arrows = extract_arrows("Bonne idée.\n[FLECHES: e2-e4, d7-d5]")
    assert clean == "Bonne idée."
    assert arrows == [("e2", "e4"), ("d7", "d5")]


def test_extract_arrows_variantes_en_de():
    _, arrows_en = extract_arrows("Good move.\n[ARROWS: e2-e4]")
    assert arrows_en == [("e2", "e4")]
    _, arrows_de = extract_arrows("Guter Zug.\n[PFEILE: e2-e4]")
    assert arrows_de == [("e2", "e4")]


def test_extract_arrows_sans_ligne_fleches():
    clean, arrows = extract_arrows("Juste du texte.")
    assert clean == "Juste du texte."
    assert arrows == []


def test_extract_arrows_ignore_cases_invalides_et_identiques():
    _, arrows = extract_arrows("Texte.\n[FLECHES: e2-e4, z9-z8, a1-a1]")
    assert arrows == [("e2", "e4")]


def test_extract_arrows_limite_a_quatre():
    _, arrows = extract_arrows(
        "Texte.\n[FLECHES: a1-a2, b1-b2, c1-c2, d1-d2, e1-e2]"
    )
    assert len(arrows) == 4
