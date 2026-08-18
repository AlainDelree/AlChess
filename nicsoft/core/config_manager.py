"""
config_manager.py — AlChess

Point d'accès centralisé à data/config.json.

Ne remplace PAS les load_config() locaux existants (pedagogique.py,
game_manager.py) — ceux-ci restent en place pour l'instant (hors scope).
Ce module sert de base commune pour les nouveaux consommateurs (Opening
Explorer, panneau Paramètres) et regroupe notamment les champs LLM/TTS.
"""

import json
import os

from nicsoft.config import DATA_DIR

CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "stockfish_level": 5,
    "game_type": "Pedagogical",
    "turn_signal": "both",
    "pedagogique_pause": "blunder",
    "llm_provider": "claude",   # "claude" | "openai"
    "llm_api_key": "",
    "llm_model": "",            # optionnel, laisser vide = modèle par défaut
    "tts_enabled": False,
    "tts_rate": 150,            # débit pyttsx3, mots par minute
    "tts_volume": 80,           # volume mpg123, 0-100
}


def load_config() -> dict:
    """Lit data/config.json avec fallback sur DEFAULT_CONFIG."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(data: dict) -> dict:
    """
    Fusionne `data` avec la config existante et l'écrit sur disque.
    Écriture atomique (fichier temporaire + os.replace) pour éviter
    la corruption de config.json en cas de crash pendant l'écriture.
    """
    merged = {**load_config(), **data}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = CONFIG_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, CONFIG_FILE)

    return merged
