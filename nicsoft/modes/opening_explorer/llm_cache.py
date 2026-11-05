"""
nicsoft/modes/opening_explorer/llm_cache.py — NicLink
Cache disque des explications LLM de l'Opening Explorer (issue #275, extrait
de llm_explainer.py) : évite de refaire un appel réseau pour une même
ligne/coup/langue déjà expliquée.
"""

import json
import logging
import os

from nicsoft.config import DATA_DIR

logger = logging.getLogger("niclink.opening_explorer.llm")

CACHE_FILE = DATA_DIR / "explorer_cache.json"


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"load_cache(): cache JSON '{CACHE_FILE}' corrompu, ignoré: {e}")
            return {}
    return {}


def save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, CACHE_FILE)
