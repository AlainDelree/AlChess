"""
nicsoft/exercices/explore_book.py — NicLink
Explorateur interactif de livre Polyglot + import au catalogue.

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
import chess.polyglot
import pathlib
import sys
from nicsoft.modes.exercices._catalogue import (
    _c, BOOKS_DIR, scan_books, book_moves_for,
    load_existing_ids, load_existing_inits, append_ouverture, resolve_parent_eco,
    bold, cyan, green, red, yellow, dim, magenta, ask,
)


def weight_bar(weight: int, max_weight: int, width: int = 12) -> str:
    if max_weight == 0:
        return " " * width
    filled = round(weight / max_weight * width)
    return "█" * filled + "░" * (width - filled)


# ── Affichage échiquier terminal ──────────────────────────────────────────────

_PIECES_TERM = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
}

def print_board(board: chess.Board, last_move: chess.Move = None) -> None:
    print()
    lm_squares = {last_move.from_square, last_move.to_square} if last_move else set()
    print("    a  b  c  d  e  f  g  h")
    print("  ┌" + "──┬" * 7 + "──┐")
    for rank in range(7, -1, -1):
        row = f"{rank+1} │"
        for file in range(8):
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            sym = _PIECES_TERM.get(piece.symbol(), "·") if piece else "·"
            light = (rank + file) % 2 == 1
            if sq in lm_squares:
                cell = _c("43", f" {sym} ")   # fond jaune = dernier coup
            elif light:
                cell = _c("2",  f" {sym} ")   # case claire = grisé
            else:
                cell = f" {sym} "
            row += cell + "│"
        print(row + f" {rank+1}")
        if rank > 0:
            print("  ├" + "──┼" * 7 + "──┤")
    print("  └" + "──┴" * 7 + "──┘")
    print("    a  b  c  d  e  f  g  h")
    print()


# ── Affichage ligne de coups ──────────────────────────────────────────────────

def format_move_line(board_history: list, san_history: list) -> str:
    """Formate la ligne de coups jouée ex: 1.d4 d5 2.c4 e6"""
    if not san_history:
        return dim("(position initiale)")
    result = []
    # Reconstituer la numérotation depuis le board initial
    move_num = 1
    # board_history[0] = position initiale, san_history[i] = coup i+1
    # Déterminer qui a commencé (blanc ou noir) depuis board_history[0]
    white_to_move = board_history[0].turn == chess.WHITE if board_history else True
    i = 0
    if not white_to_move:
        result.append(f"1…{san_history[0]}")
        i = 1
        move_num = 2
    while i < len(san_history):
        if i < len(san_history):
            result.append(f"{move_num}.{san_history[i]}")
            i += 1
        if i < len(san_history):
            result.append(san_history[i])
            i += 1
        move_num += 1
    return " ".join(result)


# ── Catalogue : voir _catalogue.py ──────────────────────────────────────────


# ── Import au catalogue ───────────────────────────────────────────────────────

def do_import(board: chess.Board, uci_history: list, san_history: list,
              book_path: pathlib.Path, books: list[pathlib.Path]) -> None:
    """Interactivement ajouter la position courante au catalogue."""
    print()
    print(bold(cyan("── Ajout au catalogue ───────────────────────────")))

    line = format_move_line(
        [chess.Board()] + [None] * len(san_history),  # simplifié
        san_history
    )
    print(f"  Ligne : {yellow(line)}")
    print(f"  Coups UCI : {' '.join(uci_history)}")
    print()

    existing_ids   = load_existing_ids()
    existing_inits = load_existing_inits()

    # Vérifier doublon de séquence
    doublon = next((eid for eid, einit in existing_inits if einit == uci_history), None)
    if doublon:
        print(red(f"⚠ Cette séquence est déjà dans le catalogue sous l'ID '{doublon}'."))
        return

    # Saisie
    while True:
        oid = ask("ID unique (ex: d4_gambit_dame_refuse)").lower().replace(" ", "_")
        if not oid:
            print(red("L'ID ne peut pas être vide.")); continue
        if oid in existing_ids:
            print(red(f"L'ID '{oid}' existe déjà.")); continue
        break

    eco  = ask("Code ECO")
    nom  = ask("Nom")
    desc = ask("Description courte")
    camp = ask("Camp suggéré (white/black)", default="white").lower()
    if camp not in ("white", "black"):
        camp = "white"

    # Vérifier présence dans les livres
    print()
    found = {}
    for b in books:
        entries = book_moves_for(board, b)
        if entries:
            found[b] = entries

    if not found:
        print(red("⚠ Position absente de tous les livres — l'exercice sera vide."))
        if ask("Ajouter quand même ? (oui/non)", "non").lower() != "oui":
            print("Annulé."); return
        chosen_book = book_path.name
    elif len(found) == 1:
        chosen_book = list(found.keys())[0].name
        entries = list(found.values())[0]
        sans = []
        tmp = board.copy()
        for e in entries[:5]:
            try: sans.append(tmp.san(e.move))
            except Exception: pass
        print(green(f"✓ {len(entries)} coups dans {chosen_book} : {', '.join(sans)}"))
    else:
        book_list = list(found.items())
        for i, (bp, entries) in enumerate(book_list):
            sans = []
            tmp = board.copy()
            for e in entries[:5]:
                try: sans.append(tmp.san(e.move))
                except Exception: pass
            print(f"  [{i+1}] {bp.name} — {len(entries)} coups : {', '.join(sans)}")
        while True:
            choice = ask(f"Quel livre ? (1-{len(book_list)})")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(book_list):
                    chosen_book = book_list[idx][0].name
                    break
            except Exception:
                pass
            print(red("Choix invalide."))

    print()
    print(bold("── Récapitulatif ────────────────────────────────"))
    print(f"  ID    : {green(oid)}")
    print(f"  ECO   : {eco}  |  Nom : {nom}")
    print(f"  Coups : {' '.join(uci_history)}")
    print(f"  Camp  : {camp}  |  Livre : {chosen_book}")
    print()

    if ask("Confirmer l'ajout ? (oui/non)", "non").lower() != "oui":
        print("Annulé."); return

    parent_eco = resolve_parent_eco(eco)
    append_ouverture({
        "id": oid, "eco": eco, "nom": nom, "desc": desc,
        "init": uci_history, "camp_suggere": camp,
        "book": chosen_book, "parent_eco": parent_eco,
    })
    print(green(f"\n✓ '{nom}' ajoutée au catalogue !"))
    print(yellow("Redémarrez NicLink pour que le changement soit pris en compte."))


# ── Boucle principale ─────────────────────────────────────────────────────────

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
            except Exception:
                pass
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
                except Exception:
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
        doublon = next((eid for eid, einit in existing_inits if einit == uci_history), None)
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
            except Exception:
                san = move.uci()
            board_stack.append(board.copy())
            uci_history.append(move.uci())
            san_history.append(san)
            board.push(move)

        else:
            print(red("  Commande invalide. Entrez un numéro, b, r, a ou q."))


if __name__ == "__main__":
    main()
