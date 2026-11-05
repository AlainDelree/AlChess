"""
nicsoft/exercices/eco_import_display.py — NicLink
Popularité d'une ligne dans les livres Polyglot et affichage des résultats
de recherche ECO (issue #281, découpage de eco_import.py).
"""

import chess
import chess.polyglot
import logging

logger = logging.getLogger("NL eco_import")

from nicsoft.modes.exercices._catalogue import bold, cyan, green, yellow, dim, magenta


def get_popularity(uci_moves: list, books: list) -> tuple:
    if not uci_moves or not books:
        return 0, 0
    board = chess.Board()
    for uci in uci_moves[:-1]:
        try: board.push(chess.Move.from_uci(uci))
        except Exception as e:
            logger.debug(f"get_popularity : UCI invalide ({uci!r}), popularité forcée à 0 : {e}")
            return 0, 0
    last_uci    = uci_moves[-1]
    best_weight = 0
    max_weight  = 0
    for book_path in books:
        try:
            with chess.polyglot.open_reader(str(book_path)) as reader:
                entries = list(reader.find_all(board))
            if not entries: continue
            entries.sort(key=lambda e: e.weight, reverse=True)
            total = sum(e.weight for e in entries)
            if total > max_weight:
                max_weight  = total
                best_weight = next(
                    (e.weight for e in entries if e.move.uci() == last_uci), 0)
        except Exception as e:
            logger.debug(f"get_popularity : lecture livre '{book_path}' échouée : {e}")
    return best_weight, max_weight


def pop_bar(weight, max_weight, width=8):
    if max_weight == 0 or weight == 0:
        return dim("░" * width)
    pct    = weight / max_weight
    filled = round(pct * width)
    if pct >= 0.30:   cfn = green
    elif pct >= 0.10: cfn = yellow
    else:             cfn = dim
    return cfn("█" * filled) + dim("░" * (width - filled))


def pop_label(weight, max_weight):
    if max_weight == 0 or weight == 0:
        return dim("absent   ")
    pct = weight / max_weight * 100
    if pct >= 30:  return green(f"{pct:4.0f}% ★★★")
    if pct >= 10:  return yellow(f"{pct:4.0f}% ★★ ")
    if pct >= 3:   return yellow(f"{pct:4.0f}% ★  ")
    return dim(f"{pct:4.0f}% —  ")


def display_results(results, existing_inits, books) -> None:
    existing_uci_sets = {tuple(einit) for _, einit in existing_inits}
    # Calculer popularité seulement si pas déjà fait
    todo = [r for r in results if "_weight" not in r]
    if todo:
        print(dim(f"  Calcul popularité ({len(todo)} lignes)…"))
        for i, r in enumerate(todo):
            w, mw = get_popularity(r["uci"], books)
            r["_weight"] = w
            r["_maxw"]   = mw
            done = round((i + 1) / len(todo) * 30)
            print(f"\r  [{chr(9608)*done}{chr(9617)*(30-done)}] {i+1}/{len(todo)}", end="", flush=True)
        print()
    # Normaliser par rapport au poids absolu maximum global
    global_max = max((r["_weight"] for r in results), default=1) or 1
    results.sort(key=lambda r: r["_weight"], reverse=True)
    for i, r in enumerate(results):
        r["_idx"] = i + 1
    print()
    hdr = f"  {'#':>3}  {'ECO':<6}  {'Nom':<40}  {'Cp':>3}  {'Popularité':<20}  Statut"
    print(bold(hdr))
    print("  " + chr(9472) * 85)
    for r in results:
        already = tuple(r["uci"]) in existing_uci_sets
        status  = magenta("✓") if already else ""
        nb      = len(r["uci"])
        name_tr = r["name"][:39]
        bar     = pop_bar(r["_weight"], global_max)
        lbl     = pop_label(r["_weight"], global_max)
        print(f"  {r['_idx']:>3}  {cyan(r['eco']):<15}  {name_tr:<40}  {nb:>3}  {bar} {lbl}  {status}")
    print()
