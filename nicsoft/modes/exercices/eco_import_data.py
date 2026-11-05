"""
nicsoft/exercices/eco_import_data.py — NicLink
Chargement des fichiers TSV ECO Lichess et filtrage par code (issue #281,
découpage de eco_import.py).
"""

from nicsoft.modes.exercices._catalogue import DATA_DIR, red

ECO_FILES = [DATA_DIR / f"eco_{x}.tsv" for x in "abcde"]


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
