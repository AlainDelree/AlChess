"""
nicsoft/exercices/explore_book_import.py — NicLink
Ajout interactif au catalogue depuis l'explorateur de livre Polyglot
(issue #281, découpage de explore_book.py).
"""

import chess
import logging
import pathlib

logger = logging.getLogger("NL explore_book")

from nicsoft.modes.exercices._catalogue import (
    check_books, load_existing_ids, load_existing_inits, append_ouverture,
    resolve_parent_eco, trouve_doublon,
    bold, cyan, green, red, yellow, ask,
)
from nicsoft.modes.exercices.explore_book_display import format_move_line


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
    doublon = trouve_doublon(uci_history, existing_inits)
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
    found = check_books(board, books)

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
            except Exception as e2: logger.debug(f"do_import : construction SAN pour affichage (1 livre) : {e2}")
        print(green(f"✓ {len(entries)} coups dans {chosen_book} : {', '.join(sans)}"))
    else:
        book_list = list(found.items())
        for i, (bp, entries) in enumerate(book_list):
            sans = []
            tmp = board.copy()
            for e in entries[:5]:
                try: sans.append(tmp.san(e.move))
                except Exception as e2: logger.debug(f"do_import : construction SAN pour affichage (plusieurs livres) : {e2}")
            print(f"  [{i+1}] {bp.name} — {len(entries)} coups : {', '.join(sans)}")
        while True:
            choice = ask(f"Quel livre ? (1-{len(book_list)})")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(book_list):
                    chosen_book = book_list[idx][0].name
                    break
            except ValueError:
                pass  # Saisie interactive : choix non numérique ignoré, redemande
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
