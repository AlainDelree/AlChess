"""
players.py — NicLink
Gestion de la liste des joueurs enregistrés (partagée entre tous les modes).

Utilisé par play_human et play_stockfish.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

PLAYERS_FILE = os.path.expanduser("~/NicLink/data/players.json")


def normalize_player_name(name: str) -> str:
    return " ".join(name.strip().split()).casefold()


def load_players() -> list:
    os.makedirs(os.path.dirname(PLAYERS_FILE), exist_ok=True)

    if not os.path.exists(PLAYERS_FILE):
        return []

    try:
        with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception as exc:
        logger.error(f"Impossible de charger les joueurs: {exc}")

    return []


def save_players(players: list) -> None:
    os.makedirs(os.path.dirname(PLAYERS_FILE), exist_ok=True)
    with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)


def find_existing_player(players: list, name: str) -> str | None:
    target = normalize_player_name(name)
    for player in players:
        if normalize_player_name(player) == target:
            return player
    return None
