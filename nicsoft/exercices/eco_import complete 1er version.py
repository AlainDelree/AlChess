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

DATA_DIR  = pathlib.Path.home() / "NicLink" / "data"
BOOKS_DIR = pathlib.Path.home() / "NicLink" / "data" / "books"
CATALOGUE = pathlib.Path(__file__).parent / "__main__.py"
ECO_FILES = [DATA_DIR / f"eco_{x}.tsv" for x in "abcde"]

# ── Couleurs terminal ─────────────────────────────────────────────────────────

def _c(code, text): return f"\033[{code}m{text}\033[0m"
def green(t):   return _c("32", t)
def red(t):     return _c("31", t)
def yellow(t):  return _c("33", t)
def bold(t):    return _c("1",  t)
def cyan(t):    return _c("36", t)
def dim(t):     return _c("2",  t)
def magenta(t): return _c("35", t)

def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{bold(prompt)}{suffix} : ").strip()
    return val if val else default

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


def pgn_to_uci(pgn: str) -> list[str]:
    """Convertit une ligne PGN en liste de coups UCI."""
    board = chess.Board()
    uci_moves = []
    # Nettoyer : retirer numéros de coups et annotations
    tokens = re.sub(r'\d+\.+', '', pgn).split()
    for token in tokens:
        token = token.strip().rstrip('+#!?')
        if not token:
            continue
        try:
            move = board.parse_san(token)
            uci_moves.append(move.uci())
            board.push(move)
        except Exception:
            break
    return uci_moves


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

# ── Vérification livre ────────────────────────────────────────────────────────

def best_book_for(board: chess.Board, books: list[pathlib.Path]) -> tuple:
    """Retourne (book_path, entries) du livre avec le plus de coups pour cette position."""
    best_path, best_entries = None, []
    for b in books:
        try:
            with chess.polyglot.open_reader(str(b)) as reader:
                entries = list(reader.find_all(board))
            if len(entries) > len(best_entries):
                best_path, best_entries = b, entries
        except Exception:
            pass
    return best_path, best_entries

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

def load_existing_ids() -> list[str]:
    content = CATALOGUE.read_text(encoding="utf-8")
    return re.findall(r'"id":\s*"([^"]+)"', content)

def load_existing_inits() -> list[tuple[str, list]]:
    content = CATALOGUE.read_text(encoding="utf-8")
    results = []
    for block in re.finditer(r'\{[^{}]+\}', content, re.DOTALL):
        b = block.group()
        id_m   = re.search(r'"id":\s*"([^"]+)"', b)
        init_m = re.search(r'"init":\s*\[([^\]]*)\]', b)
        if id_m and init_m:
            moves = re.findall(r'"([a-h][1-8][a-h][1-8][qrbn]?)"', init_m.group(1))
            results.append((id_m.group(1), moves))
    return results

def append_ouverture(entry: dict) -> None:
    content = CATALOGUE.read_text(encoding="utf-8")
    moves_str = ", ".join(f'"{m}"' for m in entry["init"])
    block = f"""    {{
        "id":   "{entry['id']}",
        "eco":  "{entry['eco']}",
        "nom":  "{entry['nom']}",
        "desc": "{entry['desc']}",
        "init": [{moves_str}],
        "camp_suggere": "{entry['camp_suggere']}",
        "book": "{entry['book']}",
    }},
"""
    marker = "\n]\n"
    idx = content.rfind(marker)
    if idx == -1:
        marker = "\n]\r\n"
        idx = content.rfind(marker)
    if idx == -1:
        print(red("Impossible de trouver la fin de OUVERTURES.")); return
    CATALOGUE.write_text(content[:idx] + "\n" + block + content[idx:], encoding="utf-8")

# ── Affichage résultats ───────────────────────────────────────────────────────

def display_results(results, existing_inits, books) -> None:
    existing_uci_sets = {tuple(einit) for _, einit in existing_inits}
    print(dim(f"  Calcul popularité ({len(results)} lignes)…"))
    for i, r in enumerate(results):
        w, mw = get_popularity(r["uci"], books)
        r["_weight"] = w
        r["_maxw"]   = mw
        done = round((i + 1) / len(results) * 30)
        print(f"\r  [{chr(9608)*done}{chr(9617)*(30-done)}] {i+1}/{len(results)}", end="", flush=True)
    print()
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
        bar     = pop_bar(r["_weight"], r["_maxw"])
        lbl     = pop_label(r["_weight"], r["_maxw"])
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

    append_ouverture({
        "id": oid, "eco": eco_val, "nom": nom, "desc": desc or nom,
        "init": r["uci"], "camp_suggere": camp, "book": chosen_book,
    })
    existing_ids.append(oid)
    existing_inits.append((oid, r["uci"]))
    print(green(f"  ✓ '{nom}' ajoutée !"))
    return True

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

    print(dim("Exemples de filtres : C02  |  C60-C67  |  D  |  C02,C60-C67,E60"))
    print(dim("Commandes après résultats : numéros à ajouter (ex: 1 3 5), 'tout', ou 'q'"))
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

        display_results(results, existing_inits, books)
        print(f"  {len(results)} résultat(s). Entrez les numéros à ajouter, 'tout', ou Entrée pour nouveau filtre.\n")

        try:
            sel = input(bold("  Sélection : ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !"); break

        if not sel or sel == "q":
            if sel == "q": print("Au revoir !"); break
            continue

        if sel == "tout":
            indices = list(range(len(results)))
        else:
            indices = []
            for tok in sel.split():
                try:
                    idx = int(tok) - 1
                    if 0 <= idx < len(results):
                        indices.append(idx)
                    else:
                        print(red(f"  Numéro invalide : {tok}"))
                except ValueError:
                    print(red(f"  Entrée invalide : {tok}"))

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
