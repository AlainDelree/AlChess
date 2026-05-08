"""
nicsoft/exercices/edit_ouverture.py — NicLink
Modifier une ouverture existante dans le catalogue.

Usage :
    python -m nicsoft.modes.exercices.edit_ouverture [--id ID]
    (ou via : python -m nicsoft.modes.exercices.manage)
"""

import sys
from nicsoft.modes.exercices._catalogue import (
    parse_ouvertures, save_ouverture,
    bold, cyan, green, red, yellow, dim, ask,
)

EDITABLE_FIELDS = [
    ("eco",          "Code ECO"),
    ("nom",          "Nom"),
    ("desc",         "Description"),
    ("camp_suggere", "Camp suggéré (white/black)"),
    ("book",         "Livre (.bin)"),
    ("parent_eco",   "Parent ECO"),
]

def edit_ouverture(o: dict) -> None:
    print()
    print(bold(cyan(f"── Édition : {o['id']} ──────────────────────────────")))
    print(dim("  Entrée vide = garder la valeur actuelle | '-' = effacer le champ"))
    print(dim("  Les modifications seront affichées avant confirmation."))
    print()
    updated = {}
    for field, label in EDITABLE_FIELDS:
        current = o.get(field, "")
        val = ask(f"  {label}", current)
        if val == "-": val = ""
        if val != current: updated[field] = val
    if not updated:
        print(yellow("  Aucune modification.")); return
    print()
    print(bold("  Modifications :"))
    for field, new_val in updated.items():
        old_val = o.get(field, "")
        label = next(l for f, l in EDITABLE_FIELDS if f == field)
        print(f"    {label} : {red(old_val or '(vide)')} → {green(new_val or '(vide)')}")
    print()
    if ask("  Confirmer ? (oui/non)", "oui").lower() != "oui":
        print("  Annulé."); return
    save_ouverture(o, updated)
    print(yellow("  Redémarrez NicLink pour appliquer les changements."))

def list_ouvertures(ouvertures: list) -> None:
    print()
    print(bold(f"  {'ID':<45}  {'ECO':<10}  Nom"))
    print("  " + "─" * 80)
    for o in ouvertures:
        print(f"  {cyan(o['id']):<54}  {o.get('eco',''):<10}  {o.get('nom','')[:40]}")
    print()

def main():
    print(bold(cyan("\n╔══════════════════════════════════════════════╗")))
    print(bold(cyan("║   NicLink — Édition d'ouverture               ║")))
    print(bold(cyan("╚══════════════════════════════════════════════╝")))
    ouvertures = parse_ouvertures()
    if not ouvertures:
        print(red("Aucune ouverture trouvée.")); sys.exit(1)
    oid = None
    if "--id" in sys.argv:
        idx = sys.argv.index("--id")
        if idx + 1 < len(sys.argv): oid = sys.argv[idx + 1]
    if not oid:
        list_ouvertures(ouvertures)
        try:
            oid = input(bold("ID à éditer (ou q) : ")).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !"); sys.exit(0)
        if oid.lower() == "q": sys.exit(0)
    o = next((x for x in ouvertures if x["id"] == oid), None)
    if not o:
        print(red(f"ID '{oid}' introuvable.")); sys.exit(1)
    edit_ouverture(o)

if __name__ == "__main__":
    main()


def list_from_web() -> list:
    """Retourne toutes les ouvertures du catalogue pour l'interface web."""
    return [
        {
            "id":           o["id"],
            "eco":          o.get("eco", ""),
            "nom":          o.get("nom", ""),
            "desc":         o.get("desc", ""),
            "camp_suggere": o.get("camp_suggere", ""),
            "book":         o.get("book", ""),
            "parent_eco":   o.get("parent_eco", ""),
            "init":         o.get("init", []),
        }
        for o in parse_ouvertures()
    ]


def save_from_web(data: dict) -> dict:
    """Sauvegarde les modifications d'une ouverture depuis l'interface web."""
    oid     = data.get("id", "")
    updated = {k: v for k, v in data.get("updated", {}).items() if k in dict(EDITABLE_FIELDS)}

    ouvertures = parse_ouvertures()
    o = next((x for x in ouvertures if x["id"] == oid), None)
    if not o:
        return {"ok": False, "error": f"ID '{oid}' introuvable."}

    if "camp_suggere" in updated:
        camp = updated["camp_suggere"].lower()
        if camp not in ("white", "black"):
            return {"ok": False, "error": "Camp doit être 'white' ou 'black'."}
        updated["camp_suggere"] = camp

    if not updated:
        return {"ok": True, "message": "Aucune modification."}

    save_ouverture(o, updated)
    return {"ok": True, "message": f"'{oid}' mis à jour."}
