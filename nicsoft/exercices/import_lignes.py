"""
nicsoft/exercices/import_lignes.py — NicLink
Importe des fichiers PGN simples (une ligne par fichier) depuis
~/NicLink/data/mes_lignes/ et les sauvegarde dans mes_lignes.json.

Usage :
    python -m nicsoft.exercices.import_lignes

Format PGN attendu (un fichier = une ligne) :
    [Event "Ruy Lopez — ligne principale"]
    [White "Blancs"]
    [Black "Noirs"]
    1. e4 e5 2. Nf3 Nc6 3. Bb5

Les champs Event, White/Black (camp_suggere), ECO sont lus si présents.
"""

import json
import pathlib
import re
import chess
import chess.pgn
import io

from nicsoft.exercices._catalogue import (
    bold, cyan, green, red, yellow, dim, make_unique_id, pgn_to_uci
)

MES_LIGNES_DIR  = pathlib.Path.home() / "NicLink" / "data" / "mes_lignes"
MES_LIGNES_JSON = pathlib.Path.home() / "NicLink" / "data" / "mes_lignes.json"


def _parse_pgn_file(path: pathlib.Path) -> dict | None:
    """
    Lit un fichier PGN simple et retourne un dict compatible OUVERTURES.
    Retourne None si le fichier est invalide.
    """
    try:
        content = path.read_text(encoding="utf-8")
        import sys as _sys
        _stderr_cap = io.StringIO()
        _old_stderr = _sys.stderr
        _sys.stderr = _stderr_cap
        try:
            game = chess.pgn.read_game(io.StringIO(content))
        finally:
            _sys.stderr = _old_stderr

        if game is None:
            return None

        # Headers
        event      = game.headers.get("Event", "")
        eco        = game.headers.get("ECO", "")
        white      = game.headers.get("White", "")
        black      = game.headers.get("Black", "")
        camp       = game.headers.get("CampSuggere", "")
        init_moves_str = game.headers.get("InitMoves", "")

        # Deviner camp_suggere depuis White/Black si pas explicite
        if not camp:
            if white and white.lower() not in ("blancs", "white", "?", ""):
                camp = "white"
            elif black and black.lower() not in ("noirs", "black", "?", ""):
                camp = "black"
            else:
                camp = "white"  # défaut

        # Nom : Event ou nom du fichier sans extension
        nom = event if event and event != "?" else path.stem.replace("_", " ")

        # Description : chercher un commentaire dans le premier nœud
        desc = ""
        node = game
        while node.variations:
            node = node.variations[0]
            if node.comment:
                desc = node.comment.strip()
                break
        if not desc and game.comment:
            desc = game.comment.strip()

        # Compter les coups attendus dans le texte brut
        # Un coup SAN commence par une lettre majuscule de pièce ou une lettre de colonne
        _SAN_TOKEN = re.compile(
            r'^([KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8]|O-O-O|O-O)'
        )
        _raw = re.sub(r'\{[^}]*\}', '', content)  # retirer commentaires
        _raw = re.sub(r'\[[^\]]*\]', '', _raw)    # retirer headers
        _raw_tokens = [t.rstrip('+#!?=') for t in _raw.split()]
        expected_moves = sum(1 for t in _raw_tokens if _SAN_TOKEN.match(t))

        # Extraire tous les coups UCI de la ligne
        board = game.board()
        all_uci = []
        node = game
        while node.variations:
            node = node.variations[0]
            move = node.move
            all_uci.append(move.uci())
            board.push(move)

        if not all_uci:
            print(red(f"  ✗ {path.name} — aucun coup trouvé dans la ligne"))
            print(dim("    Vérifiez la notation SAN (anglaise) et la syntaxe PGN."))
            return None

        # Vérifier si des coups ont été ignorés (python-chess s'arrête sur un coup illégal)
        if len(all_uci) < expected_moves:
            print(red(f"  ✗ {path.name} — coup illégal au coup #{len(all_uci)+1}"))
            print(dim(f"    Ligne tronquée : {len(all_uci)} coups parsés / {expected_moves} attendus"))
            print(dim("    Corrigez le coup et réimportez."))
            return None

        # Déterminer les coups d'init (position de départ)
        if init_moves_str:
            # Convertir InitMoves UCI en liste validée
            init_uci = []
            b = chess.Board()
            for uci in init_moves_str.split():
                try:
                    mv = chess.Move.from_uci(uci)
                    if mv in b.legal_moves:
                        init_uci.append(uci)
                        b.push(mv)
                except Exception:
                    break
        else:
            # Pas d'InitMoves → position de départ = vide (tous les coups sont la ligne)
            init_uci = []

        # ID basé sur le nom du fichier
        base_id = re.sub(
            r'[^a-z0-9]+', '_',
            path.stem.lower()
            .replace("é","e").replace("è","e").replace("ê","e")
            .replace("à","a").replace("ç","c").replace("ô","o")
            .replace("î","i").replace("û","u").replace("â","a")
        )[:38].strip('_')

        return {
            "id":           base_id,
            "eco":          eco,
            "nom":          nom,
            "desc":         desc or f"Ligne importée depuis {path.name}",
            "init":         init_uci,    # coups de départ (position initiale)
            "line":         all_uci,     # tous les coups de la ligne
            "camp_suggere": camp,
            "book":         "",
            "source":       path.name,
        }

    except Exception as e:
        print(red(f"  ✗ {path.name} — erreur : {e}"))
        return None


def _deduplicate(lignes: list[dict]) -> list[dict]:
    """Assure l'unicité des IDs."""
    seen = []
    result = []
    for ligne in lignes:
        uid = make_unique_id(ligne["id"], seen)
        ligne["id"] = uid
        seen.append(uid)
        result.append(ligne)
    return result


def main():
    print(bold(cyan("\n╔══════════════════════════════════════════════╗")))
    print(bold(cyan("║   NicLink — Import de mes lignes PGN          ║")))
    print(bold(cyan("╚══════════════════════════════════════════════╝\n")))

    # Créer le dossier si besoin
    MES_LIGNES_DIR.mkdir(parents=True, exist_ok=True)

    pgn_files = sorted(MES_LIGNES_DIR.rglob("*.pgn"))
    if not pgn_files:
        print(yellow(f"Aucun fichier .pgn trouvé dans {MES_LIGNES_DIR}"))
        print(dim("Placez vos fichiers PGN dans ce dossier et relancez."))
        return

    print(f"  {len(pgn_files)} fichier(s) trouvé(s) dans {MES_LIGNES_DIR}\n")

    # Étape 1 : afficher la conversion SAN→UCI de chaque fichier
    print(bold("── Vérification des lignes ──────────────────────────────\n"))
    for path in pgn_files:
        print(bold(cyan(f"  {path.name} :")))
        try:
            content = path.read_text(encoding="utf-8")
            show_uci(content)
        except Exception as e:
            print(red(f"  ✗ Erreur lecture : {e}"))
        print()

    # Étape 2 : demander confirmation avant d'importer
    try:
        reponse = input(bold("Procéder à l'import ? [o/N] ")).strip().lower()
        if reponse not in ("o", "oui", "y", "yes"):
            print(dim("Import annulé."))
            return
    except (KeyboardInterrupt, EOFError):
        print("\nImport annulé.")
        return

    print(bold("\n── Import ───────────────────────────────────────────────\n"))
    lignes = []
    for path in pgn_files:
        entry = _parse_pgn_file(path)
        if entry:
            lignes.append(entry)
            nb_init = len(entry["init"])
            nb_line = len(entry["line"])
            init_info = f", init={nb_init} coups" if nb_init else ""
            print(green(f"  ✓ {path.name}") + f" — {entry['nom']} ({nb_line} coups{init_info}, {entry['camp_suggere']})")

    if not lignes:
        print(red("\nAucune ligne valide importée."))
        return

    lignes = _deduplicate(lignes)

    # Sauvegarder
    MES_LIGNES_JSON.write_text(
        json.dumps(lignes, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n{green(bold(f'✓ {len(lignes)} ligne(s) importée(s)'))}")
    print(dim(f"  Sauvegardé dans : {MES_LIGNES_JSON}"))
    print(dim("  Relancez NicLink pour voir vos lignes dans l'onglet 'Mes lignes'."))


if __name__ == "__main__":
    main()


def show_uci(pgn_text: str = None) -> None:
    """
    Affiche les coups d'une partie PGN en notation UCI.
    Utile pour construire le champ [InitMoves].
    """
    import io

    if pgn_text is None:
        print(bold(cyan("\n╔══════════════════════════════════════════════╗")))
        print(bold(cyan("║   NicLink — Convertir SAN → UCI               ║")))
        print(bold(cyan("╚══════════════════════════════════════════════╝\n")))
        print(dim("Collez votre ligne PGN (ex: 1. d4 d5 2. c4 Nc6) puis Entrée deux fois :\n"))
        lines = []
        while True:
            try:
                line = input()
                if line == "":
                    break
                lines.append(line)
            except EOFError:
                break
        pgn_text = "\n".join(lines)

    try:
        import sys as _sys
        _stderr_cap2 = io.StringIO()
        _old_stderr2 = _sys.stderr
        _sys.stderr = _stderr_cap2
        try:
            game = chess.pgn.read_game(io.StringIO(pgn_text))
        finally:
            _sys.stderr = _old_stderr2

        if game is None:
            print(red("PGN invalide."))
            return

        board = game.board()
        uci_list = []
        node = game
        while node.variations:
            node = node.variations[0]
            move = node.move
            san  = board.san(move)
            uci  = move.uci()
            uci_list.append(uci)
            print(f"  {cyan(san):20s} → {green(uci)}")
            board.push(move)

        if uci_list:
            print(f"\n{bold('InitMoves complet :')}")
            print(f'  {yellow(chr(34) + " ".join(uci_list) + chr(34))}')
            print(dim("\nCopiez la portion qui vous intéresse dans [InitMoves]."))

    except Exception as e:
        print(red(f"Erreur : {e}"))
