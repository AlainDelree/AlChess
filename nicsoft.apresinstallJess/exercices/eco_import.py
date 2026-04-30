"""
nicsoft/exercices/eco_import.py — NicLink
Explorateur ECO Lichess + import au catalogue.

Usage :
    python -m nicsoft.exercices.eco_import

Workflow :
    1. Filtrer par code(s) ECO  ex: C02  ou  C60-C67  ou  D
    2. Voir les lignes correspondantes avec coups
    3. Sélectionner celles à ajouter
    4. Renseigner camp suggéré + confirmation → insertion catalogue
"""

import chess
import chess.polyglot
import pathlib
import re
import sys

from nicsoft.exercices._catalogue import (
    DATA_DIR, BOOKS_DIR, scan_books, book_moves_for, best_book_for,
    load_existing_ids, load_existing_inits, append_ouverture,
    load_eco_hierarchy, resolve_parent_eco, make_unique_id, pgn_to_uci,
    bold, cyan, green, red, yellow, dim, magenta, ask,
)

ECO_FILES = [DATA_DIR / f"eco_{x}.tsv" for x in "abcde"]

# ── Chargement ECO ────────────────────────────────────────────────────────────

def load_eco() -> list[dict]:
    """Charge tous les fichiers TSV ECO disponibles."""
    entries = []
    for f in ECO_FILES:
        if not f.exists():
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
            for line in lines[1:]:  # skip header
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                eco, name, pgn = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if eco and name and pgn:
                    entries.append({"eco": eco, "name": name, "pgn": pgn})
        except Exception as e:
            print(red(f"Erreur lecture {f.name} : {e}"))
    return entries


# pgn_to_uci → voir _catalogue.py


def parse_filter(text: str) -> callable:
    """Retourne une fonction qui teste si un code ECO correspond au filtre.
    Accepte : 'C02', 'C60-C67', 'D', 'C02,C60-C67,D4'
    """
    parts = [p.strip().upper() for p in text.replace(";", ",").split(",")]
    def match(eco: str) -> bool:
        for part in parts:
            if '-' in part:
                # plage : C60-C67
                lo, hi = part.split('-', 1)
                if lo <= eco <= hi:
                    return True
            else:
                # préfixe : 'C' ou 'C02'
                if eco.startswith(part):
                    return True
        return False
    return match

# best_book_for → voir _catalogue.py

# ── Popularité depuis le livre ───────────────────────────────────────────────

def get_popularity(uci_moves: list, books: list) -> tuple:
    if not uci_moves or not books:
        return 0, 0
    board = chess.Board()
    for uci in uci_moves[:-1]:
        try: board.push(chess.Move.from_uci(uci))
        except Exception: return 0, 0
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
        except Exception:
            pass
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


# ── Catalogue ─────────────────────────────────────────────────────────────────────
# ── Affichage résultats ───────────────────────────────────────────────────────

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

# ── Import d'une entrée ───────────────────────────────────────────────────────

def import_entry(r: dict, books: list[pathlib.Path],
                 existing_ids: list, existing_inits: list) -> bool:
    """Importe une entrée ECO dans le catalogue. Retourne True si ajouté."""
    print()
    print(bold(cyan(f"── {r['eco']} — {r['name']} ─────────────────────────")))
    print(f"  PGN  : {r['pgn']}")
    print(f"  UCI  : {' '.join(r['uci'])}")

    # Doublon séquence ?
    doublon = next((eid for eid, einit in existing_inits
                    if einit == r["uci"]), None)
    if doublon:
        print(magenta(f"  → Déjà dans le catalogue sous '{doublon}' — ignoré."))
        return False

    # Vérifier livre
    board = chess.Board()
    for uci in r["uci"]:
        try: board.push(chess.Move.from_uci(uci))
        except Exception: break

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
            except Exception: pass
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

# make_unique_id → voir _catalogue.py

# ── Mode quick ───────────────────────────────────────────────────────────────


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
        doublon = next((eid for eid, einit in existing_inits
                        if einit == r["uci"]), None)
        if doublon:
            skipped.append((r, f"doublon '{doublon}'"))
            continue

        # Livre
        board = chess.Board()
        for uci in r["uci"]:
            try: board.push(chess.Move.from_uci(uci))
            except Exception: break
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


# ── Boucle principale ─────────────────────────────────────────────────────────

def main():
    print(bold(cyan("\n╔══════════════════════════════════════════════╗")))
    print(bold(cyan("║   NicLink — Import ECO Lichess                ║")))
    print(bold(cyan("╚══════════════════════════════════════════════╝\n")))

    # Charger ECO
    all_eco = load_eco()
    if not all_eco:
        print(red(f"Aucun fichier eco_*.tsv trouvé dans {DATA_DIR}"))
        print(yellow("Téléchargez les fichiers depuis :"))
        print("  https://github.com/lichess-org/chess-openings")
        sys.exit(1)
    print(green(f"✓ {len(all_eco)} lignes ECO chargées\n"))

    # Livres disponibles
    books = sorted(BOOKS_DIR.glob("*.bin")) if BOOKS_DIR.exists() else []
    if not books:
        print(red(f"Aucun livre .bin dans {BOOKS_DIR}")); sys.exit(1)
    print(f"Livres : {', '.join(b.name for b in books)}\n")

    print(bold("── Filtres ──────────────────────────────────────────"))
    print(dim("  C02          code exact"))
    print(dim("  C60-C67      plage ECO"))
    print(dim("  D            toute une lettre"))
    print(dim("  C02,C60-C67  combinaison"))
    print()
    print(bold("── Sélection après résultats ────────────────────────"))
    print(dim("  1 3 5               numéros individuels"))
    print(dim("  1-4                 plage de numéros"))
    print(dim("  C03 C07             par codes ECO"))
    print(dim("  tout                tout ce qui est visible"))
    print(dim("  all                 afficher aussi les absentes du livre"))
    print()
    print(bold("── Mode quick (import sans questions) ───────────────"))
    print(dim("  quick 1-4 black     lignes 1 à 4, camp noir"))
    print(dim("  quick tout white    tout, camp blanc"))
    print(dim("  quick C03 C07 black par codes ECO, camp noir"))
    print(dim("  quick 1 3 5 black   numéros individuels"))
    print(dim("  (camp par défaut : white si non précisé)"))
    print()

    existing_ids   = load_existing_ids()
    existing_inits = load_existing_inits()

    while True:
        try:
            filtre = input(bold("Filtre ECO (ou q pour quitter) : ")).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !"); break

        if filtre.lower() == "q":
            print("Au revoir !"); break
        if not filtre:
            continue

        filtre = filtre.strip().upper()
        match = parse_filter(filtre)

        # Convertir PGN → UCI pour chaque entrée filtrée
        print(dim("Conversion en cours…"))
        results = []
        for entry in all_eco:
            if not match(entry["eco"]):
                continue
            uci = pgn_to_uci(entry["pgn"])
            if uci:
                results.append({**entry, "uci": uci})

        if not results:
            print(red(f"Aucun résultat pour '{filtre}'.")); continue

        # Calculer popularité sur tous les résultats avant de filtrer
        display_results(results, existing_inits, books)
        # Masquer les lignes absentes du livre après calcul
        results_visible = [r for r in results if r.get("_weight", 0) > 0]
        nb_hidden = len(results) - len(results_visible)
        if nb_hidden and results_visible:
            # Réafficher seulement les lignes présentes
            display_results(results_visible, existing_inits, books)
        hint = f"  {len(results_visible)} résultat(s)"
        if nb_hidden:
            hint += dim(f" ({nb_hidden} absentes du livre masquées — tapez 'all' pour les afficher)")
        print(hint)
        print(dim("  Sélection : numéros (ex: 1 3), codes ECO (ex: C03 C07), 'tout', 'all' ou Entrée\n"))

        try:
            sel = input(bold("  Sélection : ")).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !"); break

        sel_lower = sel.lower()
        if not sel or sel_lower == "q":
            if sel_lower == "q": print("Au revoir !"); break
            continue

        if sel_lower == "all":
            display_results(results, existing_inits, books)
            results_visible = results
            continue

        # Mode quick : "quick 1-4 black" ou "quick tout white"
        if sel_lower.startswith("quick"):
            parts = sel_lower.split()
            # Chercher le camp (white/black) dans les tokens
            quick_camp = "white"
            sel_tokens = []
            for p in parts[1:]:
                if p in ("white", "black", "blanc", "noir", "blancs", "noirs"):
                    quick_camp = "black" if p in ("black", "noir", "noirs") else "white"
                else:
                    sel_tokens.append(p.upper())
            # Résoudre les indices depuis les tokens
            quick_indices = []
            for tok in sel_tokens:
                if tok == "TOUT":
                    quick_indices = list(range(len(results_visible))); break
                if re.match(r"^\d+-\d+$", tok):
                    lo, hi = tok.split("-")
                    quick_indices.extend(i for i in range(int(lo)-1, int(hi))
                                         if i < len(results_visible))
                else:
                    try:
                        idx = int(tok) - 1
                        if 0 <= idx < len(results_visible): quick_indices.append(idx)
                    except ValueError:
                        eco_match = parse_filter(tok)
                        quick_indices.extend(i for i, r in enumerate(results_visible)
                                             if eco_match(r["eco"]))
            if not quick_indices:
                print(red("  Aucune ligne sélectionnée pour le mode quick.")); continue
            entries_to_import = [results_visible[i] for i in dict.fromkeys(quick_indices)]
            added = quick_import_batch(entries_to_import, quick_camp, books,
                                       existing_ids, existing_inits)
            if added:
                print()
                print(green(f"✓ {added} ouverture(s) ajoutée(s)."))
                print(yellow("Redémarrez NicLink pour appliquer les changements.\n"))
            continue

        if sel_lower == "tout":
            indices = list(range(len(results_visible)))
        else:
            indices = []
            for tok in sel.upper().split():
                # Plage de numéros : 1-9
                if re.match(r"^\d+-\d+$", tok):
                    lo, hi = tok.split("-")
                    for n in range(int(lo), int(hi) + 1):
                        idx = n - 1
                        if 0 <= idx < len(results_visible):
                            indices.append(idx)
                        else:
                            print(red(f"  Numéro invalide : {n}"))
                    continue
                # Numéro simple
                try:
                    idx = int(tok) - 1
                    if 0 <= idx < len(results_visible):
                        indices.append(idx)
                    else:
                        print(red(f"  Numéro invalide : {tok}"))
                    continue
                except ValueError:
                    pass
                # Code ECO (préfixe ou plage)
                eco_match = parse_filter(tok)
                matched = [i for i, r in enumerate(results_visible) if eco_match(r["eco"])]
                if matched:
                    indices.extend(matched)
                else:
                    print(red(f"  Non trouvé : {tok}"))

        if not indices:
            continue

        added = 0
        for idx in indices:
            ok = import_entry(results[idx], books, existing_ids, existing_inits)
            if ok: added += 1

        if added:
            print()
            print(green(f"✓ {added} ouverture(s) ajoutée(s) au catalogue."))
            print(yellow("Redémarrez NicLink pour que les changements soient pris en compte.\n"))
        print()


if __name__ == "__main__":
    main()
