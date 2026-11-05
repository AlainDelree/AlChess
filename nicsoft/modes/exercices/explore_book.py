"""
nicsoft/exercices/explore_book.py — NicLink
Explorateur interactif de livre Polyglot + import au catalogue. Le contenu a
été découpé en modules cohérents (issue #281) :

  - explore_book_display.py : affichage terminal (échiquier, ligne de coups)
  - explore_book_import.py  : ajout interactif au catalogue (do_import)
  - explore_book_cli.py     : boucle interactive en ligne de commande (main)
  - explore_book_web.py     : fonctions appelées par le serveur web

Ce module réexporte les mêmes objets qu'avant le découpage pour que tous
les imports existants (manage.py, server.py) continuent de fonctionner
sans modification.

Usage :
    python -m nicsoft.modes.exercices.explore_book
    (ou via : python -m nicsoft.modes.exercices.manage)
"""

from nicsoft.modes.exercices.explore_book_display import (
    weight_bar, print_board, format_move_line,
)
from nicsoft.modes.exercices.explore_book_import import do_import
from nicsoft.modes.exercices.explore_book_cli import main
from nicsoft.modes.exercices.explore_book_web import list_books_for_web, get_moves_from_web

__all__ = [
    "weight_bar", "print_board", "format_move_line",
    "do_import", "main",
    "list_books_for_web", "get_moves_from_web",
]


if __name__ == "__main__":
    main()
