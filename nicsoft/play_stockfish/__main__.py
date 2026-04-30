import argparse
import datetime
import json
import logging
import logging.handlers
import os
import pathlib
import random
import shutil
import signal
import sys
import threading
import time

import chess
import chess.pgn
from stockfish import Stockfish

from nicsoft.game.display import (
    display_move,
    display_turn,
    display_board_diff,
    check_tab_press,
)
from nicsoft.game.pgn_manager import (
    build_tmp_path,
    ask_save_pgn,
    finalize_pgn,
    save_game,
)
from nicsoft.niclink import NicLinkManager
from nicsoft.game.board_utils import wait_for_initial_position
from nicsoft.game.players import load_players, save_players
from nicsoft.utils.backup_manager import run_backup
from nicsoft.utils.input_helpers import ask_int, parse_player_input

CONFIG_FILE = pathlib.Path.home() / "NicLink" / "data" / "config.json"
DEFAULT_CONFIG = {
    "stockfish_level": 5,
    "game_type": "serieuse",
    "turn_signal": "both",
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
        except Exception as e:
            logger_pre.warning(f"config.json illisible ({e}), valeurs par défaut utilisées.")
    else:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"config.json créé avec les valeurs par défaut : {CONFIG_FILE}")
    return dict(DEFAULT_CONFIG)

import logging as _logging
logger_pre = _logging.getLogger("NL config")

logger = logging.getLogger("NL play Fish")
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(name)s - %(levelname)s | %(message)s"))
logger.addHandler(ch)


def _display_position_error(
    expected_board: chess.Board,
    actual_board: chess.Board,
    diff_count: int,
    context: str = "fish",
    fish_move: str = "",
) -> None:
    if diff_count <= 2:
        missing_sq, missing_piece, extra_sq, extra_piece = None, None, None, None
        for sq in chess.SQUARES:
            exp = expected_board.piece_at(sq)
            act = actual_board.piece_at(sq)
            if exp != act:
                if exp and not act:
                    missing_sq, missing_piece = sq, exp
                elif act and not exp:
                    extra_sq, extra_piece = sq, act
                elif exp and act:
                    missing_sq, missing_piece = sq, exp
                    extra_sq,   extra_piece   = sq, act

        from nicsoft.game.display import _piece_symbol, _piece_name_fr
        print()
        if missing_sq and extra_sq and missing_sq != extra_sq:
            sym_m = _piece_symbol(missing_piece)
            sym_e = _piece_symbol(extra_piece)
            print(
                f"⚠  Mauvaise case — {sym_e} {_piece_name_fr(extra_piece)} "
                f"posé en {chess.square_name(extra_sq)} "
                f"au lieu de {chess.square_name(missing_sq)}."
            )
            print(
                f"   Replacez le {sym_m} {_piece_name_fr(missing_piece)} "
                f"en {chess.square_name(missing_sq)}."
            )
        elif missing_sq:
            sym = _piece_symbol(missing_piece)
            print(
                f"⚠  Pièce manquante — replacez {sym} "
                f"{_piece_name_fr(missing_piece)} en {chess.square_name(missing_sq)}."
            )
        elif extra_sq:
            sym = _piece_symbol(extra_piece)
            print(
                f"⚠  Pièce en trop — retirez {sym} "
                f"{_piece_name_fr(extra_piece)} de {chess.square_name(extra_sq)}."
            )
        if context == "fish" and fish_move:
            print(f"   Puis exécutez le coup : {fish_move}")
    else:
        display_board_diff(expected_board, actual_board)
        if context == "fish" and fish_move:
            print(f"   Une fois remis en ordre, exécutez le coup : {fish_move}")
        elif context == "human":
            print("   Une fois remis en ordre, jouez votre coup.")
    print()


class Game(threading.Thread):
    """Partie d'échecs contre Stockfish, gérée dans son propre thread."""

    def __init__(self, NicLinkManager, playing_white, stockfish_level=5,
                 default_game_type="serieuse", turn_signal="both", **kwargs) -> None:
        super().__init__(**kwargs)
        self.nl_inst = NicLinkManager
        self.playing_white = playing_white
        self.default_game_type = default_game_type

        t0 = time.time()
        self.fish = Stockfish()
        logger.debug(f"Stockfish init took {round(time.time() - t0, 2)}s")

        self.fish.set_skill_level(stockfish_level)
        self.stockfish_level = stockfish_level
        self.moves = []
        self.game_over = False
        self._resignation_pending = False
        self.turn_signal = turn_signal

        self.tmp_path = build_tmp_path()

        # PGN maintenu en mémoire
        self._pgn_game = chess.pgn.Game()
        self._pgn_node = self._pgn_game

    def _update_pgn_headers(self, result: str = "*") -> None:
        player_name = getattr(self, "player_name", "Human")
        self._pgn_game.headers["Event"]       = f'{player_name} vs Stockfish (lvl {self.stockfish_level})'
        self._pgn_game.headers["Site"]        = "Chessnut Air"
        self._pgn_game.headers["Date"]        = datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        self._pgn_game.headers["White"]       = player_name if self.playing_white else "Stockfish"
        self._pgn_game.headers["Black"]       = "Stockfish" if self.playing_white else player_name
        self._pgn_game.headers["Opening"]     = getattr(self, "game_opening", "autre")
        self._pgn_game.headers["Result"]      = result
        self._pgn_game.headers["EngineLevel"] = str(self.stockfish_level)

    def _append_move_to_pgn(self, move: chess.Move, comment: str = "") -> None:
        self._pgn_node = self._pgn_node.add_variation(move)
        if comment:
            self._pgn_node.comment = comment

    def save_pgn_tmp(self, result: str = "*") -> None:
        self._update_pgn_headers(result)
        try:
            save_game(self._pgn_game, self.tmp_path)
        except Exception as e:
            logger.error(f"Erreur sauvegarde tmp: {e}")

    def _end_game(self, result: str, reason: str = "") -> None:
        self.save_pgn_tmp(result)
        player_name = getattr(self, "player_name", "Human")
        white = player_name if self.playing_white else "Stockfish"
        black = "Stockfish" if self.playing_white else player_name
        save, game_type, final_path = ask_save_pgn(
            mode="stockfish", white=white, black=black,
            default_game_type=self.default_game_type,
        )
        finalize_pgn(self.tmp_path, save, final_path)
        self._shutdown_leds()
        self.game_over = True
        sys.exit(0)

    def check_for_game_over(self) -> None:
        over_state = self.nl_inst.is_game_over()
        if not over_state:
            return
        if over_state["winner"] is False:
            winner = "Draw"
            result = "1/2-1/2"
        elif over_state["winner"]:
            winner = "Black"
            result = "0-1"
        else:
            winner = "White"
            result = "1-0"
        print(f"Winner: {winner} reason: {over_state['reason']}\nHave a nice day.")
        self._end_game(result)

    def _ask_king_removed_menu(self, player_name: str, human_color: chess.Color,
                               king_sq: int) -> None:
        try:
            self.nl_inst.beep()
        except Exception:
            pass

        print()
        print(f"  {player_name} a retiré son roi. Que souhaitez-vous ?")
        print("    1. Abandonner")
        print("    2. Proposer nulle à Stockfish")
        print("    3. Continuer la partie")

        try:
            choice = input("  Votre choix [1/2/3] : ").strip()
        except (KeyboardInterrupt, EOFError):
            choice = "3"

        if choice == "1":
            result = "0-1" if human_color == chess.WHITE else "1-0"
            print(f"\n  {player_name} abandonne. Stockfish gagne ! ({result})")
            self._end_game(result)

        elif choice == "2":
            try:
                self.fish.set_fen_position(self.nl_inst.get_game_fen())
                evaluation = self.fish.get_evaluation()
                if evaluation["type"] == "mate":
                    mate_val = evaluation["value"]
                    stockfish_color = not human_color
                    sf_winning_mate = (
                        (stockfish_color == chess.WHITE and mate_val > 0) or
                        (stockfish_color == chess.BLACK and mate_val < 0)
                    )
                    accepts = not sf_winning_mate
                else:
                    cp = evaluation["value"]
                    sf_color = not human_color
                    sf_cp = cp if self.nl_inst.game_board.turn == sf_color else -cp
                    accepts = sf_cp <= 150

                if accepts:
                    print("  Stockfish accepte la nulle.")
                    self._end_game("1/2-1/2")
                else:
                    print("  Stockfish refuse la nulle — la partie continue.")
                    king_name = chess.square_name(king_sq)
                    print(f"  Replacez le roi sur {king_name} pour continuer.")
                    self._wait_for_king_replaced(king_sq, human_color)
                    self._resignation_pending = False

            except Exception as e:
                logger.error(f"Erreur évaluation Stockfish: {e}")
                print("  Impossible d'évaluer la position. Nulle refusée.")
                king_name = chess.square_name(king_sq)
                print(f"  Replacez le roi sur {king_name} pour continuer.")
                self._wait_for_king_replaced(king_sq, human_color)
                self._resignation_pending = False

        else:
            king_name = chess.square_name(king_sq)
            print(f"  Replacez le roi sur {king_name} pour continuer.")
            self._wait_for_king_replaced(king_sq, human_color)
            self._resignation_pending = False

    def check_resignation_main_thread(self) -> None:
        human_color = chess.WHITE if self.playing_white else chess.BLACK
        king_sq     = self.nl_inst.game_board.king(human_color)
        player_name = getattr(self, "player_name", "Human")
        if king_sq is None:
            self._resignation_pending = False
            return
        self._ask_king_removed_menu(player_name, human_color, king_sq)

    def check_resignation(self, hardware_fen: str) -> bool:
        if self._resignation_pending:
            return False
        try:
            hw_board = chess.Board(hardware_fen + " w - - 0 1")
        except Exception:
            return False
        human_color = chess.WHITE if self.playing_white else chess.BLACK
        king_sq = self.nl_inst.game_board.king(human_color)
        if king_sq is None:
            return False
        expected_piece = self.nl_inst.game_board.piece_at(king_sq)
        if expected_piece is None or expected_piece.piece_type != chess.KING:
            return False
        if hw_board.piece_at(king_sq) is not None:
            return False
        self._resignation_pending = True
        return True

    def _wait_for_king_replaced(self, king_sq: int, color: chess.Color) -> None:
        king_name = chess.square_name(king_sq)
        try:
            self.nl_inst.set_led(king_name, True)
        except Exception:
            pass
        while True:
            # Utilise get_fen() directement car await_move() ne tourne pas ici
            try:
                raw = self.nl_inst.get_fen()
                board_fen = raw.strip().split()[0] if raw else ""
                hw_board = chess.Board(board_fen + " w - - 0 1")
                piece = hw_board.piece_at(king_sq)
                if piece and piece.piece_type == chess.KING and piece.color == color:
                    try:
                        self.nl_inst.turn_off_all_leds()
                    except Exception:
                        pass
                    print(f"  Roi replace en {king_name}. La partie continue.")
                    return
            except Exception:
                pass
            time.sleep(0.2)

    def _shutdown_leds(self) -> None:
        try:
            self.nl_inst.turn_off_all_leds()
        except Exception as e:
            logger.debug(f"LED shutdown error: {e}")
    def signal_turn(self):
        if self.turn_signal in ("beep", "both"):
            print("\a", end="", flush=True)
        if self.turn_signal in ("leds", "both"):
            try:
                sig = 3 if self.playing_white else 2
                self.nl_inst.signal_lights(sig)
            except Exception as exc:
                logger.debug(f"signal_turn LEDs failed: {exc}")
    def handle_human_turn(self) -> None:
        """
        Gère le tour du joueur humain.

        Deux threads tournent en parallèle :
        - await_move()  : seul thread qui lit get_fen() → met à jour nl_inst.current_fen
        - watch_board() : lit nl_inst.current_fen sans accéder au port USB
        """
        t0 = time.time()
        logger.debug("\n--- human turn ---\n")

        human_color = "white" if self.playing_white == chess.WHITE else "black"
        display_turn(self.player_name, human_color)
        self.nl_inst.turn_off_all_leds()
        self.signal_turn()
        watch_stop       = threading.Event()
        resignation_flag = threading.Event()

        def watch_board():
            """
            Surveille les pièces renversées et le retrait du roi.
            Lit nl_inst.current_fen mis à jour par await_move() —
            aucun appel direct à get_fen() pour ne pas contester le port USB.
            """
            STABLE_DELAY    = 0.8
            expected_fen    = self.nl_inst.game_board.board_fen()
            bad_fen_since   = None
            last_bad_fen    = None
            warning_shown   = False
            last_tmp_board  = None
            last_diff_count = 0

            # Laisser await_move() démarrer et remplir current_fen
            time.sleep(0.05)

            while not watch_stop.is_set():
                # Lire le FEN depuis la mémoire partagée — pas d'USB
                board_fen = self.nl_inst.current_fen
                if not board_fen:
                    time.sleep(0.05)
                    continue

                # Extraire seulement la partie pièces si FEN complet
                board_fen = board_fen.strip().split()[0]

                if board_fen == expected_fen:
                    if warning_shown:
                        print("\n   Position rétablie — c'est à vous de jouer.")
                    bad_fen_since   = None
                    last_bad_fen    = None
                    warning_shown   = False
                    last_tmp_board  = None
                    last_diff_count = 0
                    time.sleep(0.1)
                    continue

                try:
                    tmp_board = chess.Board(board_fen + " w - - 0 1")
                    diff_count = sum(
                        1 for sq in chess.SQUARES
                        if self.nl_inst.game_board.piece_at(sq) != tmp_board.piece_at(sq)
                    )
                except Exception:
                    time.sleep(0.1)
                    continue

                # ── Détecter retrait du roi EN PREMIER ────────────────────
                if not resignation_flag.is_set():
                    human_color_chess = chess.WHITE if self.playing_white else chess.BLACK
                    king_sq = self.nl_inst.game_board.king(human_color_chess)
                    if king_sq is not None:
                        expected_piece = self.nl_inst.game_board.piece_at(king_sq)
                        hw_piece = tmp_board.piece_at(king_sq)
                        if (expected_piece and
                                expected_piece.piece_type == chess.KING and
                                hw_piece is None):
                            king_absent_start = time.time()
                            king_still_absent = True
                            while time.time() - king_absent_start < 1.0:
                                time.sleep(0.1)
                                if watch_stop.is_set():
                                    return
                                try:
                                    fen2 = self.nl_inst.current_fen.strip().split()[0]
                                    tmp2 = chess.Board(fen2 + " w - - 0 1")
                                    if tmp2.piece_at(king_sq) is not None:
                                        king_still_absent = False
                                        break
                                    if fen2 == expected_fen:
                                        king_still_absent = False
                                        break
                                    for m in self.nl_inst.game_board.legal_moves:
                                        tb = self.nl_inst.game_board.copy()
                                        tb.push(m)
                                        if tb.board_fen() == fen2:
                                            king_still_absent = False
                                            break
                                    if not king_still_absent:
                                        break
                                except Exception:
                                    pass

                            if king_still_absent:
                                try:
                                    self.nl_inst.set_led(
                                        chess.square_name(king_sq), True
                                    )
                                except Exception:
                                    pass
                                resignation_flag.set()
                                self.nl_inst.kill_switch.set()
                                watch_stop.set()
                                return
                            else:
                                bad_fen_since   = None
                                last_bad_fen    = None
                                warning_shown   = False
                                last_diff_count = 0
                                continue

                if diff_count <= 2:
                    bad_fen_since   = None
                    last_bad_fen    = None
                    warning_shown   = False
                    last_diff_count = 0
                    time.sleep(0.1)
                    continue

                now = time.time()
                if board_fen != last_bad_fen:
                    bad_fen_since   = now
                    last_bad_fen    = board_fen
                    last_tmp_board  = tmp_board
                    last_diff_count = diff_count
                    warning_shown   = False
                elif now - bad_fen_since >= STABLE_DELAY and not warning_shown:
                    warning_shown   = True
                    last_tmp_board  = tmp_board
                    last_diff_count = diff_count
                    _display_position_error(
                        self.nl_inst.game_board, tmp_board, diff_count,
                        context="human"
                    )
                    try:
                        self.nl_inst.show_board_diff(
                            self.nl_inst.game_board, tmp_board
                        )
                    except Exception:
                        pass

                if check_tab_press() and warning_shown and last_tmp_board:
                    _display_position_error(
                        self.nl_inst.game_board, last_tmp_board, last_diff_count,
                        context="human"
                    )

                time.sleep(0.1)

        watcher = threading.Thread(target=watch_board, daemon=True)
        watcher.start()

        move = None
        try:
            move = self.nl_inst.await_move()
        except KeyboardInterrupt:
            watch_stop.set()
            self._shutdown_leds()
            print("\nBye!")
            sys.exit(0)
        except Exception as e:
            if resignation_flag.is_set():
                self.nl_inst.kill_switch.clear()
            else:
                raise
        finally:
            watch_stop.set()
            watcher.join(timeout=1.0)


        if resignation_flag.is_set():
            self.check_resignation_main_thread()
            return

        if move is None:
            return

        move_obj = chess.Move.from_uci(move)
        san = self.nl_inst.game_board.san(move_obj)

        self.nl_inst.opponent_moved(move)
        self.nl_inst.make_move_game_board(move)

        display_move(self.player_name, human_color, san)

        now = time.time()
        gap = round(now - getattr(self, "last_move_time", now), 2)
        self.move_gaps.append(gap)
        self.last_move_time = now

        self._append_move_to_pgn(move_obj, comment=f"gap={gap}s")
        self.save_pgn_tmp()
        self.check_for_game_over()

    def handle_fish_turn(self) -> None:
        """Gère le tour de Stockfish."""
        t0 = time.time()

        engine_color = "black" if self.playing_white == chess.WHITE else "white"
        display_turn("Stockfish", engine_color)

        self.fish.set_fen_position(self.nl_inst.get_game_fen())
        fish_move = self.fish.get_best_move()

        fish_move_obj = chess.Move.from_uci(fish_move)
        san = self.nl_inst.game_board.san(fish_move_obj)

        self.nl_inst.make_move_game_board(fish_move)
        display_move("Stockfish", engine_color, san)

        now = time.time()
        gap = round(now - getattr(self, "last_move_time", now), 2)
        self.move_gaps.append(gap)
        self.last_move_time = now

        self._append_move_to_pgn(fish_move_obj, comment=f"gap={gap}s")
        self.save_pgn_tmp()
        self.check_for_game_over()

        self._wait_for_fish_move_on_board(fish_move)

    def _wait_for_fish_move_on_board(self, fish_move: str) -> None:
        """
        Allume les LEDs et attend que le joueur déplace la pièce de Stockfish.
        Lit nl_inst.current_fen mis à jour par await_move() du tour précédent.
        Ici await_move() ne tourne pas, donc on lit get_fen() directement
        mais via current_fen qui est mis à jour par check_for_move().
        
        Comme await_move() ne tourne pas pendant cette phase, on lit
        get_fen() directement — c'est le seul endroit où c'est acceptable
        car il n'y a pas de contention USB.
        """
        t0 = time.time()
        STABLE_DELAY = 0.8

        expected_fen = self.nl_inst.game_board.board_fen()
        self.nl_inst.set_move_leds(fish_move)
        print(f"   Exécutez le coup de Stockfish sur l'échiquier ({fish_move})...")

        bad_fen_since   = None
        last_bad_fen    = None
        warning_shown   = False
        last_diff_count = 0

        while True:
            try:
                raw_fen = self.nl_inst.get_fen()
            except Exception:
                time.sleep(0.1)
                continue

            board_fen = raw_fen.strip().split()[0] if raw_fen else ""

            # Mettre à jour current_fen pour cohérence
            self.nl_inst.current_fen = raw_fen

            if board_fen == expected_fen:
                if warning_shown:
                    print("   Position rétablie. Continuez.")
                return

            try:
                tmp_board = chess.Board(board_fen + " w - - 0 1")
                diff_count = sum(
                    1 for sq in chess.SQUARES
                    if self.nl_inst.game_board.piece_at(sq) != tmp_board.piece_at(sq)
                )
            except Exception:
                diff_count = 0

            if diff_count <= 2:
                bad_fen_since   = None
                last_bad_fen    = None
                warning_shown   = False
                last_diff_count = 0
                self.nl_inst.set_move_leds(fish_move)
                time.sleep(0.1)
                continue

            now = time.time()

            if board_fen != last_bad_fen:
                bad_fen_since   = now
                last_bad_fen    = board_fen
                last_diff_count = diff_count
                warning_shown   = False

            elif now - bad_fen_since >= STABLE_DELAY and not warning_shown:
                warning_shown   = True
                last_diff_count = diff_count
                _display_position_error(
                    self.nl_inst.game_board, tmp_board, diff_count,
                    context="fish", fish_move=fish_move
                )
                try:
                    self.nl_inst.show_board_diff(self.nl_inst.game_board, tmp_board)
                except Exception:
                    self.nl_inst.set_move_leds(fish_move)

            if check_tab_press() and warning_shown:
                _display_position_error(
                    self.nl_inst.game_board, tmp_board, diff_count,
                    context="fish", fish_move=fish_move
                )

            time.sleep(0.1)

    def ensure_updated_board(self) -> None:
        return

    def start(self) -> None:
        self.nl_inst.turn_off_all_leds()
        self.run()

    def run(self) -> None:
        while True:
            if self.nl_inst.game_board.turn == self.playing_white:
                self.handle_human_turn()
            else:
                self.handle_fish_turn()


def ask_player_and_color(players, default_level=5):
    print("\n=== NicLink — Humain vs Stockfish ===")
    if players:
        print("\nJoueurs enregistrés :")
        for i, p in enumerate(players, 1):
            print(f"  {i}. {p}")
    else:
        print("\n(aucun joueur enregistré)")
    print("  N. Nouveau joueur")
    print("\nAstuce : '1b' = joueur 1 blancs, '2n' = joueur 2 noir")
    print(f"         Entrée seule = Anonyme, couleur aléatoire, Niveau Stockfish par défaut = {default_level}")

    choice = input("\nVotre choix : ").strip()

    if not choice:
        return "Anonyme", "a", players, False

    if choice.lower() == "n":
        name = input("Nom du nouveau joueur : ").strip()
        if not name:
            name = "Human"
        if name != "Human" and name not in players:
            players.append(name)
            players.sort(key=lambda x: x.casefold())
            save_players(players)
            print(f"Joueur enregistré : {name}")
        return name, None, players, True

    parsed = parse_player_input(choice, players)
    player_name = parsed["name"] if parsed["name"] else "Human"
    parsed_color = parsed["color"]
    return player_name, parsed_color, players, False


def ask_color(parsed_color):
    if parsed_color == "b":
        return True
    if parsed_color == "n":
        return False
    if parsed_color == "a":
        return random.choice([True, False])

    while True:
        print("\nCouleur :")
        print("1. Blanc")
        print("2. Noir")
        print("3. Aléatoire")
        raw = input("Choix [1-3, b/n/a, Entrée = Blanc] : ").strip().lower()

        if raw in ("", "1", "b", "blanc", "blancs"):
            return True
        if raw in ("2", "n", "noir", "noirs"):
            return False
        if raw in ("3", "a", "aleatoire", "aléatoire"):
            return random.choice([True, False])
        print("Choix invalide.")


def ask_game_type(default: str) -> str:
    types = {"1": "serieuse", "2": "detendue", "3": "amis", "4": "test"}
    default_key = next((k for k, v in types.items() if v == default), "1")
    print("\nType de partie :")
    for k, v in types.items():
        marker = " ◀ défaut" if k == default_key else ""
        print(f"  {k}. {v}{marker}")
    choice = ask_int(
        f"Choix [1-4, Entrée = {default_key}] : ",
        min_value=1, max_value=4, default=int(default_key),
    )
    return types[str(choice)]


def ask_game_name():
    name = input("\nNom de la partie [Entrée = game] : ").strip()
    return name if name else "game"


def main():
    global logger

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Active les logs détaillés")
    parser.add_argument("--backup", action="store_true", help="Crée un backup et quitte")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")

    if args.backup:
        run_backup()
        return

    config = load_config()

    _nl_ref = [None]
    _game_ref = [None]

    def _emergency_shutdown(signum, frame):
        print("\nInterruption utilisateur. Bye!")
        if _nl_ref[0] is not None:
            try:
                _nl_ref[0].turn_off_all_leds()
            except Exception:
                pass
        g = _game_ref[0]
        if g and os.path.exists(g.tmp_path):
            try:
                os.remove(g.tmp_path)
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _emergency_shutdown)

    nl_inst = None

    try:
        players = load_players()

        player_name, parsed_color, players, is_new_player = ask_player_and_color(players, default_level=config['stockfish_level'])
        playing_white = ask_color(parsed_color)

        if is_new_player:
            game_type = ask_game_type(config["game_type"])
            game_name = ask_game_name()
            level     = ask_int(
                f"Niveau Stockfish [1-20, Entrée = {config['stockfish_level']}] : ",
                min_value=1, max_value=20, default=config["stockfish_level"],
            )
        else:
            game_type = config["game_type"]
            game_name = "game"
            level     = config["stockfish_level"]

        import io as _io
        import os as _os
        devnull_fd = _os.open(_os.devnull, _os.O_WRONLY)
        old_fd = _os.dup(1)
        _os.dup2(devnull_fd, 1)
        nl_inst = NicLinkManager(refresh_delay=0.1, logger=logger, thread_sleep_delay=0.1)
        _os.dup2(old_fd, 1)
        _os.close(devnull_fd)
        _os.close(old_fd)
        print("\nChargement... OK")
        _nl_ref[0] = nl_inst

        wait_for_initial_position(nl_inst)

        game = Game(nl_inst, playing_white, stockfish_level=level,
                    default_game_type=game_type,
                    turn_signal=config.get("turn_signal", "both"))
        game.player_name    = player_name
        game.game_type      = game_type
        game.game_opening   = "autre"
        game.move_gaps      = []
        game.last_move_time = time.time()
        _game_ref[0] = game

        print(f"\nPartie  : {player_name} vs Stockfish niveau {level}")
        print(f"Couleur : {'Blancs' if playing_white else 'Noirs'}")
        sig_desc = {
            "beep": "Bip",
            "leds": "LEDs de camp",
            "both": "Bip + LEDs",
            "none": "aucun",
        }.get(config.get("turn_signal", "both"), "bip + LEDs")
        print(f"Signaux : Début de tour -> {sig_desc} / Coup illégal -> Bip Echiquier")
        print(f"Pour abandonner ou proposer nulle : retirez votre roi de l'échiquier")

        game.save_pgn_tmp()

        print("\nPartie démarrée !")

        game.start()

    except KeyboardInterrupt:
        print("\nInterruption utilisateur. Bye!")

    finally:
        if nl_inst is not None:
            try:
                nl_inst.turn_off_all_leds()
            except Exception:
                pass


if __name__ == "__main__":
    main()
