"""
nicsoft/exercices/eco_import_cli.py — NicLink
Boucle interactive en ligne de commande de l'import ECO Lichess (issue
#281, découpage de eco_import.py).

Usage :
    python -m nicsoft.modes.exercices.eco_import

Workflow :
    1. Filtrer par code(s) ECO  ex: C02  ou  C60-C67  ou  D
    2. Voir les lignes correspondantes avec coups
    3. Sélectionner celles à ajouter
    4. Renseigner camp suggéré + confirmation → insertion catalogue
"""

import re
import sys

from nicsoft.modes.exercices._catalogue import (
    DATA_DIR, BOOKS_DIR, load_existing_ids, load_existing_inits,
    pgn_to_uci,
    bold, cyan, green, red, yellow, dim, ask,
)
from nicsoft.modes.exercices.eco_import_data import load_eco, parse_filter
from nicsoft.modes.exercices.eco_import_display import display_results
from nicsoft.modes.exercices.eco_import_import import import_entry, quick_import_batch


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
                        # int() échoue → traiter le token comme un code ECO (idiome intentionnel)
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
                    pass  # int() échoue → traiter le token comme un code ECO (idiome intentionnel)
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
