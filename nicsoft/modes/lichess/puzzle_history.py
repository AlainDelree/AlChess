"""
nicsoft/modes/lichess/puzzle_history.py — AlChess

Issue #387, point 1 : historique local des problèmes (puzzles) Lichess
résolus — un enregistrement par problème TERMINÉ (résultat connu),
ajouté en fin de fichier au format « un objet JSON par ligne » (JSON
Lines), dans DATA_DIR (dossier de données déjà gitignoré, voir
nicsoft/config.py et .gitignore) — jamais dans LOGS_DIR (purgé
automatiquement) ni dans config.json. Jamais le jeton Lichess ni aucune
information d'authentification dans ce fichier (absent des champs
enregistrés ci-dessous, voir PuzzleGame._record_history, puzzle_game.py).

Aucune rotation ni limite de taille : un enregistrement par problème
résolu reste de l'ordre de quelques centaines d'octets, le fichier reste
petit même après des années d'usage (voir docs/contexte/lichess.md).

Un échec d'écriture (disque plein, droits) est journalisé et NE DOIT
JAMAIS interrompre ni faire échouer la partie/le problème en cours —
`append_puzzle_history` n'est donc jamais autorisée à lever d'exception.
"""

import json
import logging

from nicsoft.config import DATA_DIR

logger = logging.getLogger("niclink.lichess")

PUZZLE_HISTORY_FILE = DATA_DIR / "lichess_puzzle_history.jsonl"


def append_puzzle_history(entry: dict) -> None:
    """Ajoute `entry` (déjà prêt, voir PuzzleGame._record_history) comme
    une ligne JSON en fin de PUZZLE_HISTORY_FILE. Ne lève jamais —
    disque plein/droits refusés : journalisé en warning, silencieusement
    ignoré, le problème/la partie en cours continue normalement."""
    try:
        PUZZLE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        with open(PUZZLE_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:
        logger.warning("Lichess problème : écriture de l'historique local échouée : %s", exc)
