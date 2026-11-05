"""
nicsoft/modes/opening_explorer/llm_explainer.py — NicLink
Point d'entrée des fonctions publiques d'explication/discussion/analyse LLM
de l'Opening Explorer, importées par nicsoft/web/server.py. Implémentation
découpée (issue #275) dans llm_provider.py (accès au fournisseur), llm_cache.py
(cache disque), llm_prompts.py (consignes envoyées au modèle) et
llm_functions.py (fonctions publiques) — ce fichier ne fait que les
réexporter, inchangées, depuis le même chemin qu'avant le découpage.
"""

from nicsoft.modes.opening_explorer.llm_functions import (
    get_analyse_response,
    get_chat_response,
    get_explanation,
)

__all__ = ["get_explanation", "get_chat_response", "get_analyse_response"]
