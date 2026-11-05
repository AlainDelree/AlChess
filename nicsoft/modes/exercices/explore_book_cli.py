"""
nicsoft/exercices/explore_book_cli.py — NicLink
Boucle interactive en ligne de commande de l'explorateur de livre Polyglot
(issue #281, découpage de explore_book.py).

Usage :
    python -m nicsoft.modes.exercices.explore_book
    (ou via : python -m nicsoft.modes.exercices.manage)

Navigation :
    [1-9]  Jouer le coup numéroté
    b      Reculer d'un coup
    r      Retour à la position initiale
    a      Ajouter la position courante au catalogue
    q      Quitter
"""

import chess
import logging
import sys

logger = logging.getLogger("NL explore_book")

from nicsoft.modes.exercices._catalogue import (
    BOOKS_DIR, book_moves_for, load_existing_inits, trouve_doublon,
    bold, cyan, green, red, yellow, dim, magenta, ask,
)
from nicsoft.modes.exercices.explore_book_display import print_board, format_move_line, weight_bar
from nicsoft.modes.exercices.explore_book_import import do_import


def main():
    print(bold(cyan("\n╔══════════════════════════════════════════════╗")))
    print(bold(cyan("║   NicLink — Explorateur de livre Polyglot     ║")))
    print(bold(cyan("╚══════════════════════════════════════════════╝\n")))

    # Choisir le livre
    books = sorted(BOOKS_DIR.glob("*.bin")) if BOOKS_DIR.exists() else []
    if not books:
        print(red(f"Aucun fichier .bin dans {BOOKS_DIR}")); sys.exit(1)

    if len(books) == 1:
        book_path = books[0]
        print(f"Livre : {bold(book_path.name)}\n")
    else:
        print("Livres disponibles :")
        for i, b in enumerate(books):
            print(f"  [{i+1}] {b.name}")
        while True:
            choice = ask(f"Choisir un livre (1-{len(books)})")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(books):
                    book_path = books[idx]
                    break
            except ValueError:
                pass  # Saisie interactive : choix non numérique ignoré, redemande
            print(red("Choix invalide."))
        print()

    # État de navigation
    board        = chess.Board()
    uci_history  = []   # coups UCI joués
    san_history  = []   # coups SAN joués
    board_stack  = []   # boards précédents pour reculer

    print(dim("Commandes : [1-9] jouer un coup  |  b = reculer  |  r = début  |  a = ajouter au catalogue  |  q = quitter"))
    print()

    while True:
        # Afficher échiquier
        last_move = chess.Move.from_uci(uci_history[-1]) if uci_history else None
        print_board(board, last_move)

        # Ligne courante
        line_str = format_move_line(board_stack + [board], san_history)
        print(f"  {bold('Ligne :')} {yellow(line_str)}")

        # Coups disponibles dans le livre
        entries = book_moves_for(board, book_path)
        total_weight = sum(e.weight for e in entries) or 1

        if entries:
            print(f"\n  {bold('Coups du livre')} ({len(entries)} coups) :\n")
            for i, e in enumerate(entries[:9], 1):
                try:
                    san = board.san(e.move)
                except Exception as e2:
                    logger.debug(f"main : SAN indisponible pour {e.move.uci()}, fallback UCI : {e2}")
                    san = e.move.uci()
                pct  = round(e.weight / total_weight * 100)
                bar  = weight_bar(e.weight, entries[0].weight)
                star = "★ " if i == 1 else "  "
                color_fn = green if i == 1 else (yellow if pct >= 15 else dim)
                print(f"    [{i}] {color_fn(star + san.ljust(8))}  {bar}  {pct:3d}%  (poids {e.weight})")
            if len(entries) > 9:
                print(dim(f"    … et {len(entries)-9} autres coups"))
        else:
            print(f"\n  {red('Fin du livre — aucun coup disponible depuis cette position.')}")

        # Vérifier si déjà dans le catalogue
        existing_inits = load_existing_inits()
        doublon = trouve_doublon(uci_history, existing_inits)
        if doublon and uci_history:
            print(magenta(f"\n  ✓ Déjà dans le catalogue : '{doublon}'"))

        # Profondeur
        print(dim(f"\n  Profondeur : {len(uci_history)} coup{'s' if len(uci_history) != 1 else ''}"))
        print()

        # Saisie commande
        try:
            cmd = input(bold("  > ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !"); break

        if cmd == "q":
            print("Au revoir !"); break

        elif cmd == "b":
            if uci_history:
                board = board_stack.pop()
                uci_history.pop()
                san_history.pop()
                print(green("  ← Retour en arrière"))
            else:
                print(red("  Déjà à la position initiale."))

        elif cmd == "r":
            board       = chess.Board()
            uci_history = []
            san_history = []
            board_stack = []
            print(green("  ↺ Retour au début"))

        elif cmd == "a":
            if not uci_history:
                print(red("  Jouez au moins un coup avant d'ajouter."))
            else:
                do_import(board, uci_history, san_history, book_path, books)

        elif cmd.isdigit() and 1 <= int(cmd) <= min(9, len(entries)):
            idx   = int(cmd) - 1
            move  = entries[idx].move
            try:
                san = board.san(move)
            except Exception as e:
                logger.debug(f"main : SAN indisponible pour {move.uci()}, fallback UCI : {e}")
                san = move.uci()
            board_stack.append(board.copy())
            uci_history.append(move.uci())
            san_history.append(san)
            board.push(move)

        else:
            print(red("  Commande invalide. Entrez un numéro, b, r, a ou q."))


if __name__ == "__main__":
    main()
