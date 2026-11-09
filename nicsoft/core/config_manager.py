"""
config_manager.py — AlChess

Point d'accès centralisé à data/config.json.

load_config()/save_config() servent de base commune pour les nouveaux
consommateurs (Opening Explorer, panneau Paramètres) et regroupent
notamment les champs LLM/TTS. pedagogique.py et human.py gardent leurs
propres load_config() locaux (defaults et niveau de log différents) mais
délèguent la lecture/fusion JSON à read_json_with_defaults() ci-dessous.
"""

import json
import logging
import os

from pathlib import Path

from nicsoft.config import DATA_DIR

logger = logging.getLogger("NL config_manager")

CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "stockfish_level": 5,
    "game_type": "Pedagogical",
    "turn_signal": "both",
    "pedagogique_pause": "blunder",
    "llm_provider": "claude",   # "claude" | "openai"
    "llm_api_key": "",
    "llm_model": "",            # optionnel, laisser vide = modèle par défaut
    "lichess_token": "",        # jeton personnel Lichess (issue #306) — même mécanisme que llm_api_key
    "tts_enabled": False,
    "tts_rate": 150,            # débit pyttsx3, mots par minute
    "tts_volume": 80,           # volume mpg123, 0-100
}


def read_json_with_defaults(path, defaults: dict, on_error=None) -> dict:
    """
    Lit `path` (JSON) et fusionne sur `defaults`.
    Retombe sur `defaults` si le fichier est absent ou invalide ;
    `on_error(exc)`, si fourni, est appelé dans ce cas (ex. pour logger).
    """
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**defaults, **data}
        except Exception as exc:
            if on_error:
                on_error(exc)
    return dict(defaults)


def load_config() -> dict:
    """Lit data/config.json avec fallback sur DEFAULT_CONFIG."""
    return read_json_with_defaults(
        CONFIG_FILE, DEFAULT_CONFIG,
        on_error=lambda exc: logger.warning(f"config.json illisible, valeurs par défaut utilisées : {exc}"),
    )


def validated_engine_path(cfg: dict, key: str = "engine_path", default: str = "") -> str:
    """Retourne le path moteur sauvegardé seulement s'il existe sur cette plateforme."""
    p = cfg.get(key, default)
    if p and Path(p).exists():
        return p
    return default


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
