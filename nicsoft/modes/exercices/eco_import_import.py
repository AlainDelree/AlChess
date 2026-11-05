"""
nicsoft/exercices/eco_import_import.py — NicLink
Import d'une entrée ECO (interactif ou en lot) dans le catalogue (issue
#281, découpage de eco_import.py).
"""

import chess
import logging
import pathlib
import re

logger = logging.getLogger("NL eco_import")

from nicsoft.modes.exercices._catalogue import (
    best_book_for, append_ouverture, resolve_parent_eco, make_unique_id,
    trouve_doublon,
    bold, cyan, green, red, yellow, dim, magenta, ask,
)


def import_entry(r: dict, books: list[pathlib.Path],
                 existing_ids: list, existing_inits: list) -> bool:
    """Importe une entrée ECO dans le catalogue. Retourne True si ajouté."""
    print()
    print(bold(cyan(f"── {r['eco']} — {r['name']} ─────────────────────────")))
    print(f"  PGN  : {r['pgn']}")
    print(f"  UCI  : {' '.join(r['uci'])}")

    # Doublon séquence ?
    doublon = trouve_doublon(r["uci"], existing_inits)
    if doublon:
        print(magenta(f"  → Déjà dans le catalogue sous '{doublon}' — ignoré."))
        return False

    # Vérifier livre
    board = chess.Board()
    for uci in r["uci"]:
        try: board.push(chess.Move.from_uci(uci))
        except Exception as e:
            logger.warning(f"import_entry : reconstruction board interrompue ({uci!r}) : {e}")
            break

    book_path, entries = best_book_for(board, books)
    if not entries:
        print(red("  ⚠ Position absente de tous les livres."))
        if ask("  Ajouter quand même ? (oui/non)", "non").lower() != "oui":
            return False
        chosen_book = books[0].name if books else "gm2001.bin"
    else:
        sans = []
        tmp = board.copy()
        for e in entries[:4]:
            try: sans.append(tmp.san(e.move))
            except Exception as e2: logger.debug(f"import_entry : construction SAN pour affichage : {e2}")
        print(green(f"  ✓ {len(entries)} coups dans {book_path.name} : {', '.join(sans)}"))
        chosen_book = book_path.name

    # Saisie
    # ID suggéré depuis le nom
    id_suggest = re.sub(r'[^a-z0-9]+', '_',
                        r["name"].lower().replace("é","e").replace("è","e")
                        .replace("ê","e").replace("à","a").replace("ç","c"))[:40].strip('_')

    while True:
        oid = ask(f"  ID unique", id_suggest).lower().replace(" ", "_")
        if not oid: print(red("  ID vide.")); continue
        if oid in existing_ids: print(red(f"  '{oid}' existe déjà.")); continue
        break

    eco_val = ask("  Code ECO", r["eco"])
    nom     = ask("  Nom", r["name"])
    desc    = ask("  Description courte")
    camp    = ask("  Camp suggéré (white/black)", "white").lower()
    if camp not in ("white", "black"): camp = "white"

    print()
    print(f"  {bold('Récap')} : {green(oid)} | {eco_val} | {nom} | {camp} | {chosen_book}")

    if ask("  Confirmer ? (oui/non)", "oui").lower() != "oui":
        print("  Annulé."); return False

    parent_eco = resolve_parent_eco(r["eco"])
    append_ouverture({
        "id": oid, "eco": eco_val, "nom": nom, "desc": desc or nom,
        "init": r["uci"], "camp_suggere": camp, "book": chosen_book,
        "parent_eco": parent_eco,
    })
    existing_ids.append(oid)
    existing_inits.append((oid, r["uci"]))
    print(green(f"  ✓ '{nom}' ajoutée !"))
    return True


def quick_import_batch(entries: list, camp: str, books: list,
                       existing_ids: list, existing_inits: list) -> int:
    """Import rapide sans questions — tout est pré-rempli.
    Affiche un récap et demande une seule confirmation globale.
    Retourne le nombre d'entrées ajoutées."""

    # Préparer les données pour chaque entrée
    prepared = []
    skipped  = []

    for r in entries:
        # Doublon ?
        doublon = trouve_doublon(r["uci"], existing_inits)
        if doublon:
            skipped.append((r, f"doublon '{doublon}'"))
            continue

        # Livre
        board = chess.Board()
        for uci in r["uci"]:
            try: board.push(chess.Move.from_uci(uci))
            except Exception as e:
                logger.warning(f"quick_import_batch : reconstruction board interrompue ({uci!r}) : {e}")
                break
        book_path, book_entries = best_book_for(board, books)
        if not book_entries:
            skipped.append((r, "absent du livre"))
            continue

        oid = make_unique_id(r["name"], existing_ids + [p["id"] for p in prepared])

        prepared.append({
            "id":          oid,
            "eco":         r["eco"],
            "nom":         r["name"],
            "desc":        r["name"],
            "init":        r["uci"],
            "camp_suggere": camp,
            "book":        book_path.name,
        })

    if not prepared:
        print(red("  Aucune entrée à importer (doublons ou absentes du livre)."))
        return 0

    # Récap
    print()
    print(bold(f"  {'ID':<42}  {'ECO':<6}  Camp"))
    print("  " + "─" * 60)
    for p in prepared:
        print(f"  {green(p['id']):<51}  {cyan(p['eco']):<15}  {p['camp_suggere']}")
    if skipped:
        print()
        for r, reason in skipped:
            print(dim(f"  ↷ Ignoré {r['eco']} — {r['name'][:40]} ({reason})"))
    print()

    confirm = ask(f"  Importer ces {len(prepared)} ouverture(s) ? (oui/non)", "oui").lower()
    if confirm != "oui":
        print("  Annulé."); return 0

    added = 0
    for p in prepared:
        p["parent_eco"] = resolve_parent_eco(p["eco"])
        append_ouverture(p)
        existing_ids.append(p["id"])
        existing_inits.append((p["id"], p["init"]))
        print(green(f"  ✓ {p['nom'][:50]}"))
        added += 1

    return added
