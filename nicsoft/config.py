"""Chemins centralisés pour AlChess.

Toujours importer depuis ici plutôt que de construire les chemins à la main.
La variable d'environnement ALCHESS_DIR permet de forcer le répertoire.
Par défaut, on remonte depuis la position de ce fichier (nicsoft/config.py →
parent = projet), ce qui fonctionne quelle que soit la lettre de lecteur ou
le dossier d'installation (Linux, Windows, clé USB…).
"""

import os
import pathlib

# nicsoft/config.py → parent = nicsoft/ → parent.parent = racine projet
_pkg_root = pathlib.Path(__file__).parent.parent

if os.environ.get("ALCHESS_DIR"):
    APP_DIR = pathlib.Path(os.environ["ALCHESS_DIR"])
elif (_pkg_root / "nicsoft").exists():
    APP_DIR = _pkg_root
else:
    APP_DIR = pathlib.Path.home() / "NicLink"

DATA_DIR    = APP_DIR / "data"
GAMES_DIR   = APP_DIR / "games"
LOGS_DIR    = APP_DIR / "logs"
ENGINES_DIR = APP_DIR / "engines"
