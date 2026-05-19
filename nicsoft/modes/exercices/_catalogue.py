"""
nicsoft/exercices/_catalogue.py — NicLink
Fonctions partagées pour la gestion du catalogue d'ouvertures.
Utilisé par manage.py et tous les outils d'édition.
"""

import chess
import chess.polyglot
import json
import pathlib
import re
from nicsoft.config import DATA_DIR

# ── Chemins ───────────────────────────────────────────────────────────────────

CATALOGUE  = pathlib.Path(__file__).parent / "exercices.py"
BOOKS_DIR  = DATA_DIR / "books"
ECO_HIER_F = DATA_DIR / "eco_hierarchy.json"

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
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"{bold(prompt)}{suffix} : ").strip()
    return val if val else default

# ── Livres Polyglot ───────────────────────────────────────────────────────────

def scan_books() -> list[pathlib.Path]:
    if not BOOKS_DIR.exists():
        return []
    return sorted(BOOKS_DIR.glob("*.bin"))


def book_moves_for(board: chess.Board, book_path: pathlib.Path) -> list:
    try:
        with chess.polyglot.open_reader(str(book_path)) as reader:
            entries = list(reader.find_all(board))
        entries.sort(key=lambda e: e.weight, reverse=True)
        return entries
    except Exception:
        return []


def check_books(board: chess.Board, books: list[pathlib.Path]) -> dict:
    """Retourne {book_path: [entries]} pour les livres qui ont des coups."""
    results = {}
    for b in books:
        entries = book_moves_for(board, b)
        if entries:
            results[b] = entries
    return results


def best_book_for(board: chess.Board, books: list[pathlib.Path]) -> tuple:
    """Retourne (book_path, entries) du livre avec le plus de coups."""
    best_path, best_entries = None, []
    for b in books:
        entries = book_moves_for(board, b)
        if len(entries) > len(best_entries):
            best_path, best_entries = b, entries
    return best_path, best_entries

# ── Lecture catalogue ─────────────────────────────────────────────────────────

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


def parse_ouvertures() -> list[dict]:
    """Extrait toutes les ouvertures avec leurs champs et position dans le fichier."""
    content = CATALOGUE.read_text(encoding="utf-8")
    ouvertures = []
    for m in re.finditer(r'(\{[^{}]+\})', content, re.DOTALL):
        block = m.group(1)
        o = {}
        for field in ["id", "eco", "nom", "desc", "camp_suggere", "book", "parent_eco"]:
            fm = re.search(rf'"({field})":\s*"([^"]*)"', block)
            if fm:
                o[field] = fm.group(2)
        im = re.search(r'"init":\s*\[([^\]]*)\]', block)
        if im:
            o["init"] = re.findall(r'"([^"]+)"', im.group(1))
        if o.get("id"):
            o["_start"] = m.start()
            o["_end"]   = m.end()
            o["_block"] = block
            ouvertures.append(o)
    return ouvertures

# ── Écriture catalogue ────────────────────────────────────────────────────────

def append_ouverture(entry: dict) -> None:
    """Insère une nouvelle ouverture dans OUVERTURES."""
    content = CATALOGUE.read_text(encoding="utf-8")
    moves_str = ", ".join(f'"{m}"' for m in entry["init"])
    lines = [
        '    {',
        f'        "id":   "{entry["id"]}",',
        f'        "eco":  "{entry["eco"]}",',
        f'        "nom":  "{entry["nom"]}",',
        f'        "desc": "{entry["desc"]}",',
        f'        "init": [{moves_str}],',
        f'        "camp_suggere": "{entry["camp_suggere"]}",',
        f'        "book": "{entry["book"]}",',
    ]
    if entry.get("parent_eco"):
        lines.append(f'        "parent_eco": "{entry["parent_eco"]}",')
    lines.append("    },")
    block = "\n".join(lines) + "\n"

    marker = "\n]\n"
    idx = content.rfind(marker)
    if idx == -1:
        marker = "\n]\r\n"
        idx = content.rfind(marker)
    if idx == -1:
        print(red("Impossible de trouver la fin de OUVERTURES dans __main__.py"))
        return
    CATALOGUE.write_text(content[:idx] + "\n" + block + content[idx:], encoding="utf-8")


def update_field_in_block(block: str, field: str, new_value: str) -> str:
    """Met à jour ou ajoute un champ dans un bloc dict."""
    pattern = rf'("({field})":\s*)"([^"]*)"'
    new_block, n = re.subn(pattern, rf'\g<1>"{new_value}"', block)
    if n == 0 and new_value:
        new_block = re.sub(
            r'(\s*\},?\s*)$',
            f'\n        "{field}": "{new_value}",\n    }},\n',
            block.rstrip(),
        )
    return new_block


def save_ouverture(o: dict, updated: dict) -> None:
    """Réécrit le bloc d'une ouverture avec les champs modifiés."""
    content  = CATALOGUE.read_text(encoding="utf-8")
    old_block = o["_block"]
    new_block = old_block
    for field, new_val in updated.items():
        new_block = update_field_in_block(new_block, field, new_val)
    if new_block == old_block:
        print(yellow("  Aucun changement."))
        return
    CATALOGUE.write_text(content.replace(old_block, new_block, 1), encoding="utf-8")
    print(green("  ✓ Catalogue mis à jour."))

# ── ECO Hierarchy ─────────────────────────────────────────────────────────────

def load_eco_hierarchy() -> dict:
    if not ECO_HIER_F.exists():
        return {}
    try:
        return json.loads(ECO_HIER_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_parent_eco(eco_code: str) -> str:
    """Retourne le parent_eco d'un code depuis eco_hierarchy.json."""
    hier = load_eco_hierarchy()
    return hier.get(eco_code, {}).get("parent", "") or ""

# ── Utilitaires import ────────────────────────────────────────────────────────

def make_unique_id(base: str, existing_ids: list) -> str:
    base = re.sub(
        r'[^a-z0-9]+', '_',
        base.lower()
        .replace("é","e").replace("è","e").replace("ê","e")
        .replace("à","a").replace("ç","c").replace("ô","o")
        .replace("î","i").replace("û","u").replace("â","a")
    )[:38].strip('_')
    if base not in existing_ids:
        return base
    i = 2
    while f"{base}_{i}" in existing_ids:
        i += 1
    return f"{base}_{i}"


def pgn_to_uci(pgn: str) -> list[str]:
    """Convertit une ligne PGN en liste de coups UCI."""
    board = chess.Board()
    uci_moves = []
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
