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


def read_puzzle_history_entries() -> list:
    """Lit PUZZLE_HISTORY_FILE et retourne la liste des enregistrements
    valides (un `dict` par ligne JSON lisible) — jamais d'exception :
    fichier absent/vide -> liste vide ; ligne illisible (JSON invalide,
    pas un objet) -> ignorée silencieusement, sans faire échouer la
    lecture des autres lignes (issue #390, point 2 — mêmes garanties que
    append_puzzle_history ci-dessus pour l'écriture)."""
    try:
        text = PUZZLE_HISTORY_FILE.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def last_known_puzzle_rating() -> int | None:
    """Dernière cote « Après » connue (`rating_after`) parmi les
    enregistrements de l'historique local, en remontant depuis la fin —
    issue #390, point 1 : repli immédiat (lecture locale, jamais de
    réseau) affiché pendant qu'une lecture plus à jour du profil du
    compte est tentée en arrière-plan (voir
    game_manager_modes/lichess.py::_init_puzzle_session_rating). `None`
    si l'historique est absent/vide ou si aucun enregistrement n'a de
    cote « Après » connue (jamais une valeur inventée)."""
    for entry in reversed(read_puzzle_history_entries()):
        rating = entry.get("rating_after")
        if isinstance(rating, int):
            return rating
    return None
