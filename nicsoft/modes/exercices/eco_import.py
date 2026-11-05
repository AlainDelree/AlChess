"""
nicsoft/exercices/eco_import.py — NicLink
Explorateur ECO Lichess + import au catalogue. Le contenu a été découpé en
modules cohérents (issue #281) :

  - eco_import_data.py    : chargement des fichiers TSV ECO et filtre ECO
  - eco_import_display.py : popularité dans les livres et affichage résultats
  - eco_import_import.py  : import d'une entrée (interactif ou en lot)
  - eco_import_cli.py     : boucle interactive en ligne de commande (main)
  - eco_import_web.py     : fonctions appelées par le serveur web

Ce module réexporte les mêmes objets qu'avant le découpage pour que tous
les imports existants (manage.py, server.py) continuent de fonctionner
sans modification.

Usage :
    python -m nicsoft.modes.exercices.eco_import

Workflow :
    1. Filtrer par code(s) ECO  ex: C02  ou  C60-C67  ou  D
    2. Voir les lignes correspondantes avec coups
    3. Sélectionner celles à ajouter
    4. Renseigner camp suggéré + confirmation → insertion catalogue
"""

from nicsoft.modes.exercices.eco_import_data import ECO_FILES, load_eco, parse_filter
from nicsoft.modes.exercices.eco_import_display import (
    get_popularity, pop_bar, pop_label, display_results,
)
from nicsoft.modes.exercices.eco_import_import import import_entry, quick_import_batch
from nicsoft.modes.exercices.eco_import_cli import main
from nicsoft.modes.exercices.eco_import_web import search_eco_from_web, import_eco_from_web

__all__ = [
    "ECO_FILES", "load_eco", "parse_filter",
    "get_popularity", "pop_bar", "pop_label", "display_results",
    "import_entry", "quick_import_batch",
    "main",
    "search_eco_from_web", "import_eco_from_web",
]


if __name__ == "__main__":
    main()
