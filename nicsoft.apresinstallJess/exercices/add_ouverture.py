"""
nicsoft/exercices/add_ouverture.py — NicLink
Ajout manuel d'une ouverture au catalogue.

Usage :
    python -m nicsoft.exercices.add_ouverture
    (ou via : python -m nicsoft.exercices.manage)
"""

import chess
import sys
from nicsoft.exercices._catalogue import (
    BOOKS_DIR, scan_books, check_books, load_existing_ids, load_existing_inits,
    append_ouverture, resolve_parent_eco,
    bold, cyan, green, red, yellow, ask,
)


def main():
    print(bold(cyan("\n╔══════════════════════════════════════════╗")))
    print(bold(cyan("║   NicLink — Ajout manuel d'ouverture        ║")))
    print(bold(cyan("╚══════════════════════════════════════════╝\n")))

    books = scan_books()
    if not books:
        print(red(f"Aucun fichier .bin trouvé dans {BOOKS_DIR}"))
        sys.exit(1)
    print(f"Livres : {', '.join(b.name for b in books)}\n")

    existing_ids   = load_existing_ids()
    existing_inits = load_existing_inits()

    print(bold("── Informations ──────────────────────────────────"))

    while True:
        oid = ask("ID unique (ex: e4_moderne)").lower().replace(" ", "_")
        if not oid: print(red("L'ID ne peut pas être vide.")); continue
        if oid in existing_ids: print(red(f"L'ID '{oid}' existe déjà.")); continue
        break

    eco  = ask("Code ECO (ex: B06)")
    nom  = ask("Nom")
    desc = ask("Description courte")
    camp = ask("Camp suggéré (white/black)", "white").lower()
    if camp not in ("white", "black"): camp = "white"

    print()
    print(bold("── Séquence de coups UCI ────────────────────────"))
    print(yellow("  Format : coups séparés par des espaces, ex: e2e4 g7g6"))
    print()

    while True:
        raw = ask("Coups UCI")
        if not raw: print(red("Entrez au moins un coup.")); continue
        board = chess.Board()
        valid_moves, ok = [], True
        for uci in raw.strip().split():
            try:
                mv = chess.Move.from_uci(uci)
                if mv not in board.legal_moves:
                    print(red(f"Coup illégal : {uci}")); ok = False; break
                board.push(mv); valid_moves.append(uci)
            except Exception:
                print(red(f"Format invalide : {uci}")); ok = False; break
        if not ok: print(yellow("Corrigez et réessayez.\n")); continue
        doublon = next((eid for eid, ei in existing_inits if ei == valid_moves), None)
        if doublon:
            print(red(f"Séquence identique à '{doublon}' déjà dans le catalogue."))
            continue
        break

    print()
    print(bold("── Vérification livres ──────────────────────────"))
    found = check_books(board, books)
    if not found:
        print(red("⚠ Position absente de tous les livres."))
        if ask("Ajouter quand même ? (oui/non)", "non").lower() != "oui":
            print("Annulé."); return
        chosen_book = books[0].name
    else:
        book_list = list(found.items())
        for i, (bp, entries) in enumerate(book_list):
            sans = []
            tmp = board.copy()
            for e in entries[:5]:
                try: sans.append(tmp.san(e.move))
                except Exception: pass
            print(f"  [{i+1}] {bp.name} — {len(entries)} coup(s) : {', '.join(sans)}")
        if len(book_list) == 1:
            chosen_book = book_list[0][0].name
            print(green(f"Livre sélectionné : {chosen_book}"))
        else:
            while True:
                choice = ask(f"Quel livre ? (1-{len(book_list)})")
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(book_list): chosen_book = book_list[idx][0].name; break
                except Exception: pass
                print(red("Choix invalide."))

    parent_eco = resolve_parent_eco(eco)

    print()
    print(bold("── Récapitulatif ────────────────────────────────"))
    print(f"  ID    : {green(oid)}")
    print(f"  ECO   : {eco}  |  Nom : {nom}")
    print(f"  Coups : {' '.join(valid_moves)}")
    print(f"  Camp  : {camp}  |  Livre : {chosen_book}")
    if parent_eco: print(f"  Parent: {parent_eco}")
    print()

    if ask("Ajouter ? (oui/non)", "non").lower() != "oui":
        print("Annulé."); return

    append_ouverture({
        "id": oid, "eco": eco, "nom": nom, "desc": desc,
        "init": valid_moves, "camp_suggere": camp,
        "book": chosen_book, "parent_eco": parent_eco,
    })
    print(green(f"\n✓ '{nom}' ajoutée !"))
    print(yellow("Redémarrez NicLink pour appliquer les changements."))


if __name__ == "__main__":
    main()
