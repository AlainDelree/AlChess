"""
nicsoft/exercices/manage.py — NicLink
Menu central de gestion du catalogue d'ouvertures.

Usage :
    python -m nicsoft.modes.exercices.manage
"""

import sys
from nicsoft.modes.exercices._catalogue import bold, cyan, dim, green, red, yellow

MENU = [
    ("1", "Ajouter une ouverture manuellement",       "add"),
    ("2", "Importer depuis ECO Lichess (TSV)",         "eco"),
    ("3", "Explorer un livre Polyglot",                "explore"),
    ("4", "Modifier une ouverture existante",          "edit"),
    ("5", "Mettre à jour eco_hierarchy.json (Wikipedia)", "wiki"),
    ("6", "Importer mes lignes PGN",                   "import_lignes"),
    ("7", "Convertir SAN → UCI (pour InitMoves)",      "show_uci"),
    ("q", "Quitter",                                   None),
]

def print_menu():
    print(bold(cyan("\n╔══════════════════════════════════════════════╗")))
    print(bold(cyan("║   NicLink — Gestion des ouvertures            ║")))
    print(bold(cyan("╚══════════════════════════════════════════════╝\n")))
    for key, label, _ in MENU:
        if key == "q":
            print(f"  {dim(key)}  {dim(label)}")
        else:
            print(f"  {cyan(key)}  {label}")
    print()

def main():
    while True:
        print_menu()
        try:
            choice = input(bold("Choix : ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !"); sys.exit(0)

        if choice == "q":
            print("Au revoir !"); sys.exit(0)

        action = next((a for k, _, a in MENU if k == choice), None)
        if not action:
            print(red("Choix invalide.\n")); continue

        if action == "add":
            from nicsoft.modes.exercices.add_ouverture import main as run
            run()
        elif action == "eco":
            from nicsoft.modes.exercices.eco_import import main as run
            run()
        elif action == "explore":
            from nicsoft.modes.exercices.explore_book import main as run
            run()
        elif action == "edit":
            from nicsoft.modes.exercices.edit_ouverture import main as run
            run()
        elif action == "wiki":
            from nicsoft.modes.exercices.download_eco_wiki import main as run
            run()
        elif action == "import_lignes":
            from nicsoft.modes.exercices.import_lignes import main as run
            run()
        elif action == "show_uci":
            from nicsoft.modes.exercices.import_lignes import show_uci
            show_uci()

        print()

if __name__ == "__main__":
    main()
