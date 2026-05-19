"""Chemins centralisés pour AlChess.

Toujours importer depuis ici plutôt que de construire les chemins à la main.
La variable d'environnement ALCHESS_DIR permet de relocaliser l'application
sans modifier le code (utile pour le portage Windows ou les tests).
"""

import os
import pathlib

_default = pathlib.Path.home() / "NicLink"
APP_DIR = pathlib.Path(os.environ.get("ALCHESS_DIR", str(_default)))

DATA_DIR    = APP_DIR / "data"
GAMES_DIR   = APP_DIR / "games"
LOGS_DIR    = APP_DIR / "logs"
ENGINES_DIR = APP_DIR / "engines"
