"""
nicsoft/exercices/eco_import_web.py — NicLink
Fonctions appelées par le serveur web (server.py) pour la recherche et
l'import ECO Lichess (issue #281, découpage de eco_import.py).
"""

import chess
import logging

logger = logging.getLogger("NL eco_import")

from nicsoft.modes.exercices._catalogue import (
    DATA_DIR, scan_books, best_book_for, load_existing_ids, load_existing_inits,
    append_ouverture, resolve_parent_eco, make_unique_id, pgn_to_uci, trouve_doublon,
)
from nicsoft.modes.exercices.eco_import_data import load_eco, parse_filter


def search_eco_from_web(data: dict) -> dict:
    """
    Recherche dans les fichiers ECO Lichess selon un filtre.
    data: {filter: "C60-C67"}
    Retourne jusqu'à 300 résultats avec statut doublon.
    """
    filtre = data.get("filter", "").strip().upper()
    if not filtre:
        return {"ok": False, "error": "Filtre vide."}

    all_eco = load_eco()
    if not all_eco:
        return {"ok": False, "error": f"Aucun fichier eco_*.tsv trouvé dans {DATA_DIR}"}

    try:
        match = parse_filter(filtre)
    except Exception as e:
        return {"ok": False, "error": f"Filtre invalide : {e}"}

    existing_inits = load_existing_inits()
    existing_uci_sets = {tuple(ei) for _, ei in existing_inits}
    existing_map = {tuple(ei): eid for eid, ei in existing_inits}

    MAX = 300
    results = []
    total_matched = 0
    for entry in all_eco:
        if not match(entry["eco"]):
            continue
        total_matched += 1
        if len(results) >= MAX:
            continue
        uci = pgn_to_uci(entry["pgn"])
        if not uci:
            continue
        doublon_id = existing_map.get(tuple(uci))
        results.append({
            "eco":       entry["eco"],
            "name":      entry["name"],
            "uci":       uci,
            "nb_coups":  len(uci),
            "doublon":   doublon_id or "",
        })

    return {
        "ok":            True,
        "results":       results,
        "total_matched": total_matched,
        "truncated":     total_matched > MAX,
    }


def import_eco_from_web(data: dict) -> dict:
    """
    Importe une liste d'entrées ECO depuis le navigateur.
    data: {entries: [{eco, name, uci}], camp: "white"}
    """
    entries = data.get("entries", [])
    camp    = data.get("camp", "white").lower()
    if camp not in ("white", "black"):
        camp = "white"

    books          = scan_books()
    existing_ids   = load_existing_ids()
    existing_inits = load_existing_inits()

    imported = []
    skipped  = []

    for e in entries:
        uci  = e.get("uci", [])
        name = e.get("name", "")
        eco  = e.get("eco", "")

        # Doublon séquence
        doublon = trouve_doublon(uci, existing_inits)
        if doublon:
            skipped.append({"name": name, "reason": f"doublon '{doublon}'"})
            continue

        # Trouver le meilleur livre
        board = chess.Board()
        for mv_uci in uci:
            try:
                board.push(chess.Move.from_uci(mv_uci))
            except Exception as e2:
                logger.warning(f"import_eco_from_web : reconstruction board interrompue ({mv_uci!r}) : {e2}")
                break
        book_path, book_entries = best_book_for(board, books)

        if not book_entries:
            skipped.append({"name": name, "reason": "absent des livres"})
            continue

        oid        = make_unique_id(name, existing_ids + [x["id"] for x in imported])
        parent_eco = resolve_parent_eco(eco)

        append_ouverture({
            "id":          oid,
            "eco":         eco,
            "nom":         name,
            "desc":        name,
            "init":        uci,
            "camp_suggere": camp,
            "book":        book_path.name,
            "parent_eco":  parent_eco,
        })
        existing_ids.append(oid)
        existing_inits.append((oid, uci))
        imported.append({"id": oid, "name": name, "eco": eco})

    return {
        "ok":       True,
        "imported": imported,
        "skipped":  skipped,
        "total":    len(entries),
    }
