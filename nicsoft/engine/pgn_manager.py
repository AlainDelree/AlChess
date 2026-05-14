"""
pgn_manager.py — NicLink
Gestion des fichiers PGN.

Nouvelle logique de sauvegarde :
- Pendant la partie : fichier temporaire dans ~/NicLink/games/tmp/
- En fin de partie  : demande si on veut sauvegarder
  - oui -> choix du type, copie dans l'arborescence finale, suppression du tmp
  - non -> suppression du tmp

Arborescence finale :
  ~/NicLink/games/
    humaine/
      serieuse/    2026-03-22_Alain_vs_Jessica_01.pgn
      pedagogique/
      amusement/
    stockfish/
      serieuse/
      pedagogique/
      amusement/
"""

import datetime
import os
import shutil
import chess
import chess.pgn


# ──────────────────────────────────────────────
# Chemin temporaire
# ──────────────────────────────────────────────

TMP_DIR = os.path.expanduser("~/NicLink/games/tmp")

GAME_TYPES = {
    "1": "Serious",
    "2": "Pedagogical",
    "3": "Casual",
}


def build_tmp_path() -> str:
    """Cree un chemin de fichier temporaire pour la partie en cours."""
    os.makedirs(TMP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(TMP_DIR, f"partie_en_cours_{timestamp}.pgn")


def build_final_path(mode: str, game_type: str, white: str, black: str) -> str:
    """
    Construit le chemin final avec nom lisible et increment.

    mode      : "Human" ou "Stockfish"
    game_type : "Serious", "Pedagogical", "Casual"
    white/black : noms des joueurs

    Resultat : ~/NicLink/games/Human/Serious/2026-03-22_Alain_vs_Jessica_01.pgn
    """
    base = os.path.expanduser(f"~/NicLink/games/{mode}/{game_type}")
    os.makedirs(base, exist_ok=True)

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Nettoyer les noms pour le nom de fichier
    def clean(name):
        return "".join(c for c in name if c.isalnum() or c in "-_").strip()

    w = clean(white) or "White"
    b = clean(black) or "Black"
    prefix = f"{date_str}_{w}_vs_{b}"

    # Trouver le prochain increment disponible
    n = 1
    while True:
        filename = f"{prefix}_{n:02d}.pgn"
        path = os.path.join(base, filename)
        if not os.path.exists(path):
            return path
        n += 1


def ask_save_pgn(mode: str, white: str, black: str, default_game_type: str = "Serious") -> tuple:
    """
    Pose les questions de fin de partie et retourne (sauvegarder, game_type, final_path).

    Retourne :
      (True,  game_type, final_path) si on sauvegarde
      (False, None,      None)       si on ne sauvegarde pas
    """
    print()
    print("─" * 40)

    try:
        answer = input("  Sauvegarder la partie ? (o/n) : ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return False, None, None

    if answer != "o":
        return False, None, None

    # Trouver la cle par defaut
    default_key = next((k for k, v in GAME_TYPES.items() if v == default_game_type), "1")

    print()
    print("  Type de partie :")
    for k, v in GAME_TYPES.items():
        marker = " (defaut)" if k == default_key else ""
        print(f"    {k}. {v}{marker}")

    try:
        raw = input(f"  Choix [1-3, Entree = {default_key}] : ").strip()
    except (KeyboardInterrupt, EOFError):
        raw = ""

    game_type = GAME_TYPES.get(raw, GAME_TYPES.get(default_key, "Serious"))
    final_path = build_final_path(mode, game_type, white, black)

    return True, game_type, final_path


def finalize_pgn(tmp_path: str, save: bool, final_path: str = None) -> str | None:
    """
    Finalise le PGN en fin de partie.

    save=True  -> copie tmp vers final_path, supprime tmp, retourne final_path
    save=False -> supprime tmp, retourne None
    """
    if not tmp_path or not os.path.exists(tmp_path):
        return None

    if save and final_path:
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        shutil.copy2(tmp_path, final_path)
        os.remove(tmp_path)
        print(f"  Partie sauvegardee : {final_path}")
        return final_path
    else:
        os.remove(tmp_path)
        print("  Partie non sauvegardee.")
        return None


# ──────────────────────────────────────────────
# Fonctions de construction PGN
# ──────────────────────────────────────────────

def build_game_from_moves(headers=None, moves=None, comments=None):
    """
    Construit un objet chess.pgn.Game à partir d'une liste de coups.
    Sans vérification de légalité — les coups viennent du game_board
    déjà validé par python-chess.
    """
    game = chess.pgn.Game()

    if headers:
        for key, value in headers.items():
            if value is not None:
                game.headers[key] = str(value)

    node = game
    board = chess.Board()
    moves = moves or []
    comments = comments or []

    for idx, move in enumerate(moves):
        if isinstance(move, str):
            move = chess.Move.from_uci(move)
        node = node.add_variation(move)
        board.push(move)
        if idx < len(comments) and comments[idx]:
            node.comment = str(comments[idx])

    return game


def save_game(game, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        exporter = chess.pgn.FileExporter(f)
        game.accept(exporter)
    return output_path


def build_and_save_pgn(headers=None, moves=None, comments=None,
                       base_dir=None, mode="human", prefix="game",
                       output_path=None):
    """
    Construit et sauvegarde un PGN.
    Rapide : pas de vérification de légalité, les coups viennent
    directement du game_board validé par python-chess.
    """
    game = build_game_from_moves(headers=headers, moves=moves, comments=comments)

    if output_path is None:
        # Fallback legacy
        root = os.path.expanduser(base_dir or "~/NicLink/games")
        output_dir = os.path.join(root, mode)
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = os.path.join(output_dir, f"{prefix}_{ts}.pgn")

    return save_game(game, output_path)
