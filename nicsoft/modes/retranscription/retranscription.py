"""
nicsoft/retranscription/__main__.py — NicLink
Module de retranscription PGN.
Extrait de nicsoft/web/__main__.py pour une meilleure organisation.

Deux modes :
- "partie"   : retranscription d'une partie de club → ~/NicLink/games/Retranscription/
- "exercice" : création d'une ligne personnelle     → ~/NicLink/data/mes_lignes/<nom>/
"""

import chess
import json
import pathlib
import re

# ── Chemins ───────────────────────────────────────────────────────────────────

SAVE_PATH  = pathlib.Path.home() / "NicLink" / "data" / "retranscription_en_cours.json"
GAMES_DIR  = pathlib.Path.home() / "NicLink" / "games" / "Retranscription"
LIGNES_DIR = pathlib.Path.home() / "NicLink" / "data" / "mes_lignes"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', s).strip('_')


def _next_filepath(directory: pathlib.Path, base: str) -> pathlib.Path:
    """Retourne le prochain chemin disponible : base_1.pgn, base_2.pgn..."""
    directory.mkdir(parents=True, exist_ok=True)
    i = 1
    while True:
        path = directory / f"{base}_{i}.pgn"
        if not path.exists():
            return path
        i += 1


def _build_pgn(moves_uci: list, headers: dict) -> str:
    """Construit le contenu PGN depuis une liste de coups UCI."""
    import chess.pgn as _pgn
    import io
    game = _pgn.Game()
    for k, v in headers.items():
        game.headers[k] = v
    node = game
    b = chess.Board()
    for uci in moves_uci:
        move = chess.Move.from_uci(uci)
        node = node.add_variation(move)
        b.push(move)
    buf = io.StringIO()
    print(game, file=buf)
    return buf.getvalue()


def export_partie(moves_uci: list, white: str, black: str,
                  date: str, event: str, result: str) -> str:
    """Sauvegarde une partie de club. Retourne le chemin du fichier."""
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    base = _safe(event) if event and event != "?" else _safe(f"{white}_vs_{black}")
    if not base:
        base = "Partie"
    filepath = _next_filepath(GAMES_DIR, base)
    headers = {
        "Event":  event  or "?",
        "Date":   date   or "????.??.??",
        "White":  white,
        "Black":  black,
        "Result": result,
    }
    filepath.write_text(_build_pgn(moves_uci, headers), encoding="utf-8")
    print(f"[RETRANSCRIPTION] Partie sauvegardée : {filepath}")
    return str(filepath)


def export_exercice(moves_uci: list, nom: str,
                    camp_suggere: str, init_moves: list) -> str:
    """
    Sauvegarde une ligne personnelle dans mes_lignes/<nom>/.
    Retourne le chemin du fichier.
    """
    safe_nom = _safe(nom) if nom else "Exercice"
    dest_dir = LIGNES_DIR / safe_nom
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = _next_filepath(dest_dir, safe_nom)
    init_str = " ".join(init_moves) if init_moves else ""
    headers = {
        "Event":        nom or "Exercice",
        "CampSuggere":  camp_suggere or "white",
    }
    if init_str:
        headers["InitMoves"] = init_str
    pgn = _build_pgn(moves_uci, headers)
    filepath.write_text(pgn, encoding="utf-8")
    print(f"[RETRANSCRIPTION] Exercice sauvegardé : {filepath}")
    return str(filepath)


def save_session(moves_uci: list, config: dict) -> None:
    """Sauvegarde l'état courant pour reprise."""
    SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAVE_PATH.write_text(
        json.dumps({**config, "moves": moves_uci}, ensure_ascii=False),
        encoding="utf-8"
    )


def load_session() -> dict | None:
    """Charge une session en cours. Retourne None si absente."""
    if not SAVE_PATH.exists():
        return None
    try:
        return json.loads(SAVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_session() -> None:
    """Supprime la sauvegarde temporaire."""
    if SAVE_PATH.exists():
        SAVE_PATH.unlink()


# ── Session principale ────────────────────────────────────────────────────────

def run_retranscription(config: dict,
                        send_event,
                        get_action,
                        set_virtual_board,
                        web_server) -> None:
    """
    Boucle principale de retranscription.
    Appelée depuis nicsoft/web/__main__.py dans un thread dédié.
    """
    from nicsoft.niclink.virtual_board import VirtualBoard
    import chess

    mode = config.get("mode", "partie")  # "partie" ou "exercice"

    # Champs communs
    white  = config.get("white", "Blancs")
    black  = config.get("black", "Noirs")
    date   = config.get("date", "")
    event  = config.get("event", "")
    result = config.get("result", "*")
    nom    = config.get("nom", "")
    camp   = config.get("camp_suggere", "white")

    # Reprendre une session en cours si demandé
    board = chess.Board()
    moves_uci = []
    if config.get("resume"):
        saved = load_session()
        if saved:
            white  = saved.get("white", white)
            black  = saved.get("black", black)
            date   = saved.get("date", date)
            event  = saved.get("event", event)
            result = saved.get("result", result)
            nom    = saved.get("nom", nom)
            camp   = saved.get("camp_suggere", camp)
            mode   = saved.get("mode", mode)
            for uci in saved.get("moves", []):
                try:
                    board.push_uci(uci)
                    moves_uci.append(uci)
                except Exception:
                    break
            print(f"[RETRANSCRIPTION] Session reprise — {len(moves_uci)} coups")

    vb = VirtualBoard()
    vb.game_board = board.copy()
    set_virtual_board(vb)

    def _save():
        save_session(moves_uci, {
            "mode": mode, "white": white, "black": black,
            "date": date, "event": event, "result": result,
            "nom": nom, "camp_suggere": camp,
        })

    def _export(final_result, init_moves=None):
        if mode == "exercice":
            return export_exercice(moves_uci, nom, camp, init_moves or [])
        else:
            return export_partie(moves_uci, white, black, date, event, final_result)

    # État initial → frontend
    web_server._app_state = "retrans_playing"
    send_event("app_state", {"state": "retrans_playing"})
    send_event("retranscription_init", {
        "mode": mode,
        "white": white, "black": black,
        "date": date, "event": event, "result": result,
        "nom": nom, "camp_suggere": camp,
        "moves": moves_uci,
        "fen": board.fen(),
    })

    # Boucle principale
    running = True
    while running:
        action = get_action(timeout=0.2)

        # Coups virtuels
        uci = vb._move_queue.get(timeout=0.0) if not vb._move_queue.empty() else None
        if uci:
            try:
                move = chess.Move.from_uci(uci)
                if move in board.legal_moves:
                    san = board.san(move)
                    board.push(move)
                    vb.game_board = board.copy()
                    moves_uci.append(uci)
                    _save()
                    color = "white" if board.turn == chess.BLACK else "black"
                    send_event("retranscription_move", {
                        "uci": uci, "san": san, "color": color,
                        "fen": board.fen(),
                        "move_num": len(moves_uci),
                        "moves_uci_line": " ".join(moves_uci),
                    })
                    if board.is_checkmate():
                        r = "0-1" if board.turn == chess.WHITE else "1-0"
                        send_event("retranscription_end", {"reason": "checkmate", "result": r})
                    elif board.is_stalemate():
                        send_event("retranscription_end", {"reason": "stalemate", "result": "1/2-1/2"})
                    elif board.is_insufficient_material():
                        send_event("retranscription_end", {"reason": "material", "result": "1/2-1/2"})
                else:
                    send_event("virtual_move_illegal", {"uci": uci})
            except Exception:
                pass

        if action is None:
            continue

        atype = action.get("type", "")

        if atype == "retranscription_undo":
            if moves_uci:
                moves_uci.pop()
                board.pop()
                vb.game_board = board.copy()
                _save()
                send_event("retranscription_undo", {
                    "fen": board.fen(),
                    "moves_uci_line": " ".join(moves_uci),
                })

        elif atype == "retranscription_save_continue":
            final_result = action.get("result", "*")
            init_moves   = action.get("init_moves", [])
            filepath = _export(final_result, init_moves)
            send_event("retranscription_saved_continue", {
                "path": filepath, "result": final_result
            })
            # Garder la position — ne pas quitter

        elif atype == "retranscription_end":
            final_result = action.get("result", result)
            init_moves   = action.get("init_moves", [])
            filepath = _export(final_result, init_moves)
            delete_session()
            send_event("retranscription_saved", {"path": filepath, "result": final_result})
            running = False

        elif atype == "retrans_quit_no_save":
            # Quitter sans sauver — supprimer la session temporaire
            delete_session()
            running = False

        elif atype == "back_menu":
            _save()
            running = False

    set_virtual_board(None)
    web_server._app_state = "menu"
    send_event("app_state", {"state": "menu"})
