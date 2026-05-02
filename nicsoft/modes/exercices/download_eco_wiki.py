"""
nicsoft/exercices/download_eco_wiki.py — NicLink
Télécharge la liste ECO depuis Wikipedia et construit eco_hierarchy.json.

Usage :
    python -m nicsoft.modes.exercices.download_eco_wiki

Produit : ~/NicLink/data/eco_hierarchy.json
Format :
{
  "A00": {"name": "Irregular openings", "moves": "...", "group": "A00-A09"},
  "C30": {"name": "King's Gambit",       "moves": "1.e4 e5 2.f4", "group": "C30-C39"},
  ...
}
"""

import json
import pathlib
import re
import sys
import urllib.request

OUTPUT = pathlib.Path.home() / "NicLink" / "data" / "eco_hierarchy.json"
API_URL = "https://en.wikipedia.org/w/api.php?action=parse&page=List_of_ECO_codes&prop=wikitext&format=json"

# ── Groupes ECO officiels (dizaines) ─────────────────────────────────────────
# Source : structure de l'ECO — chaque groupe de 10 codes = une famille
# On définit les groupes nommés pour les grandes familles

ECO_GROUPS = {
    # A : ouvertures irrégulières, anglaise, etc.
    "A00": "A00-A09",  "A10": "A10-A19",  "A20": "A20-A29",
    "A30": "A30-A39",  "A40": "A40-A49",  "A50": "A50-A59",
    "A60": "A60-A69",  "A70": "A70-A79",  "A80": "A80-A89",  "A90": "A90-A99",
    # B : semi-ouvertes
    "B00": "B00-B09",  "B10": "B10-B19",  "B20": "B20-B29",
    "B30": "B30-B39",  "B40": "B40-B49",  "B50": "B50-B59",
    "B60": "B60-B69",  "B70": "B70-B79",  "B80": "B80-B89",  "B90": "B90-B99",
    # C : ouvertes
    "C00": "C00-C09",  "C10": "C10-C19",  "C20": "C20-C29",
    "C30": "C30-C39",  "C40": "C40-C49",  "C50": "C50-C59",
    "C60": "C60-C69",  "C70": "C70-C79",  "C80": "C80-C89",  "C90": "C90-C99",
    # D : fermées et semi-fermées
    "D00": "D00-D09",  "D10": "D10-D19",  "D20": "D20-D29",
    "D30": "D30-D39",  "D40": "D40-D49",  "D50": "D50-D59",
    "D60": "D60-D69",  "D70": "D70-D79",  "D80": "D80-D89",  "D90": "D90-D99",
    # E : indiennes
    "E00": "E00-E09",  "E10": "E10-E19",  "E20": "E20-E29",
    "E30": "E30-E39",  "E40": "E40-E49",  "E50": "E50-E59",
    "E60": "E60-E69",  "E70": "E70-E79",  "E80": "E80-E89",  "E90": "E90-E99",
}

def get_group(code: str) -> str:
    """Retourne le groupe dizaine d'un code ECO. Ex: C33 → C30-C39"""
    if len(code) < 3:
        return code
    prefix = code[0] + code[1] + "0"
    return ECO_GROUPS.get(prefix, prefix)


def parse_article_name(raw: str) -> str:
    """Extrait le nom propre depuis un lien wiki [[Nom|Texte]] ou [[Nom]]"""
    if not raw:
        return ""
    # [[Lien|Texte affiché]] → Texte affiché
    m = re.search(r'\[\[([^\]|]+)\|([^\]]+)\]\]', raw)
    if m:
        return m.group(2).strip()
    # [[Lien]] → Lien
    m = re.search(r'\[\[([^\]]+)\]\]', raw)
    if m:
        return m.group(1).strip()
    # Texte brut (sans lien)
    text = re.sub(r'\[\[.*?\]\]', '', raw)
    text = re.sub(r'\{\{.*?\}\}', '', text)
    return text.strip()


def clean_moves(raw: str) -> str:
    """Nettoie les coups PGN en supprimant les références wiki."""
    text = re.sub(r'\{\{sfnp[^}]*\}\}', '', raw)
    text = re.sub(r'\{\{br\}\}.*', '', text, flags=re.DOTALL)
    text = re.sub(r'\[\[.*?\]\]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def download_wikitext() -> str:
    print("Téléchargement depuis Wikipedia...")
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "NicLink/1.0 (chess opening tool; contact via github)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    wikitext = data["parse"]["wikitext"]["*"]
    print(f"✓ {len(wikitext)} caractères téléchargés")
    return wikitext


def parse_eco_table(wikitext: str) -> dict:
    """Parse le wikitext et extrait {code: {name, moves, group}}"""
    entries = {}

    # Chaque ligne ECO : | CODE || Moves || Article
    pattern = re.compile(
        r'^\|\s*([A-E]\d{2})\s*\|\|\s*(.*?)\s*\|\|\s*(.*?)\s*$',
        re.MULTILINE
    )

    for m in pattern.finditer(wikitext):
        code   = m.group(1).strip()
        moves  = clean_moves(m.group(2))
        article = parse_article_name(m.group(3))

        entries[code] = {
            "name":  article or moves[:60],  # si pas de nom d'article, utiliser les coups
            "moves": moves,
            "group": get_group(code),
        }

    return entries


def build_hierarchy(entries: dict) -> dict:
    """Ajoute le champ 'parent' à chaque entrée.

    Règle : le parent d'un code est le code dans le même groupe (dizaine)
    qui a le moins de coups et dont les coups sont un préfixe des coups du fils.
    Ex: C30 (1.e4 e5 2.f4) est parent de C33 (1.e4 e5 2.f4 exf4)
    """
    for code, entry in entries.items():
        moves = entry["moves"]
        group = entry["group"]
        best_parent = None
        best_len    = 0

        for other_code, other in entries.items():
            if other_code == code:
                continue
            if other["group"] != group:
                continue
            omoves = other["moves"]
            if not omoves or not moves:
                continue
            # other est parent si ses coups sont un préfixe strict des coups de entry
            if moves.startswith(omoves) and len(omoves) > best_len:
                best_parent = other_code
                best_len    = len(omoves)

        entry["parent"] = best_parent

    return entries


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    try:
        wikitext = download_wikitext()
    except Exception as e:
        print(f"Erreur téléchargement : {e}")
        sys.exit(1)

    entries = parse_eco_table(wikitext)
    if not entries:
        print("Aucune entrée parsée — structure Wikipedia peut-être changée.")
        sys.exit(1)

    entries = build_hierarchy(entries)

    # Stats
    with_parent    = sum(1 for e in entries.values() if e["parent"])
    with_name      = sum(1 for e in entries.values() if e["name"])
    print(f"✓ {len(entries)} codes ECO parsés")
    print(f"  {with_name} avec nom d'article")
    print(f"  {with_parent} avec parent détecté")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"✓ Sauvegardé → {OUTPUT}")
    print()

    # Aperçu
    print("Aperçu (C30-C36) :")
    for code in ["C30","C31","C32","C33","C34","C35","C36"]:
        if code in entries:
            e = entries[code]
            parent = f"→ parent: {e['parent']}" if e['parent'] else ""
            print(f"  {code}  {e['name'][:40]:<40}  {e['moves'][:40]:<40}  {parent}")


if __name__ == "__main__":
    main()
