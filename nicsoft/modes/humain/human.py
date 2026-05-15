import argparse
import datetime
import json
import logging
import os
import pathlib
import signal
import sys
import threading
import time

import chess
import chess.pgn
from nicsoft.utils.timing import tlog
from nicsoft.engine.display import display_move, display_turn, display_check_status
from nicsoft.engine.pgn_manager import (
    build_tmp_path,
    build_and_save_pgn,
    ask_save_pgn,
    finalize_pgn,
)
from nicsoft.engine.players import (
    load_players,
    save_players,
    find_existing_player,
    normalize_player_name,
)
from nicsoft.engine.board_utils import wait_for_initial_position, san_ep
from nicsoft.web.server import send_event, get_action, set_app_state, _game_state
from nicsoft.niclink import NicLinkManager

logger = logging.getLogger("NL play Human")
ch = logging.StreamHandler()
formatter = logging.Formatter("%(name)s - %(levelname)s | %(message)s")
ch.setFormatter(formatter)
logger.handlers.clear()
logger.addHandler(ch)
logger.setLevel(logging.INFO)

CONFIG_FILE = pathlib.Path.home() / "NicLink" / "data" / "config.json"
DEFAULT_CONFIG = {"turn_signal": "beep", "game_type": "Serious"}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


class Game(threading.Thread):
    def __init__(self, nl_inst, white_name="Blanc", black_name="Noir",
                 poll_delay=0.1, output_dir=None,
                 turn_signal="beep", default_game_type="Serious", **kwargs):
        super().__init__(daemon=True, **kwargs)
        self.nl_inst = nl_inst
        self.white_name = white_name
        self.black_name = black_name
        self.poll_delay = poll_delay
        self.turn_signal = turn_signal
        self.default_game_type = default_game_type

        self.board = chess.Board()
        self.game = chess.pgn.Game()
        self.node = self.game

        self.game.headers["Event"] = "Human vs Human"
        self.game.headers["Site"] = "Chessnut Air"
        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["White"] = white_name
        self.game.headers["Black"] = black_name
        self.game.headers["Result"] = "*"

        self.game_over = False
        self.output_dir = output_dir or os.path.expanduser("~/NicLink/games")
        os.makedirs(self.output_dir, exist_ok=True)

        # Fichier temporaire cree au demarrage de la partie
        self.tmp_path = build_tmp_path()

        self._last_raw_fen = None
        self._stable_count = 0
        self.illegal_stable_reads_required = 8
        self._leds_showing_turn = False
        self._resignation_pending = False
        self._king_absent_since = None   # timestamp du début du retrait du roi

    # ── Signaux ───────────────────────────────────────────────────────────

    def signal_turn(self):
        if self.turn_signal in ("beep", "both"):
            print("\a", end="", flush=True)
        if self.turn_signal in ("leds", "both"):
            try:
                sig = 3 if self.board.turn == chess.WHITE else 2
                self.nl_inst.signal_lights(sig)
                self._leds_showing_turn = True
            except Exception as exc:
                logger.debug(f"signal_turn LEDs failed: {exc}")

    def beep_illegal(self):
        try:
            self.nl_inst.beep()
        except Exception:
            print("\a\a", end="", flush=True)

    # ── Lecture plateau ───────────────────────────────────────────────────

    def get_hardware_piece_placement(self):
        try:
            raw_fen = self.nl_inst.current_fen
        except Exception as exc:
            logger.error(f"Erreur lecture échiquier: {exc}")
            return None
        if not raw_fen:
            return None
        return raw_fen.strip().split()[0]

    def get_legal_move_matching_hardware(self, hardware_piece_placement):
        for move in self.board.legal_moves:
            test_board = self.board.copy()
            test_board.push(move)
            if test_board.board_fen() == hardware_piece_placement:
                return move
        return None

    # ── Abandon ───────────────────────────────────────────────────────────

    def check_resignation(self, hardware_fen: str) -> bool:
        """
        Detecte si un joueur a retire son roi, quel que soit son tour.
        Affiche un menu : abandonner / proposer nulle / continuer.
        """
        if self._resignation_pending:
            return False

        try:
            hw_board = chess.Board(hardware_fen + " w - - 0 1")
        except Exception:
            return False

        # Verifier les deux rois — n'importe qui peut retirer son roi
        for color in (chess.WHITE, chess.BLACK):
            king_sq = self.board.king(color)
            if king_sq is None:
                continue
            expected_piece = self.board.piece_at(king_sq)
            if expected_piece is None or expected_piece.piece_type != chess.KING:
                continue
            if hw_board.piece_at(king_sq) is not None:
                continue

            # Ce roi est absent — déclencher le menu
            self._resignation_pending = True
            player_name   = self.white_name if color == chess.WHITE else self.black_name
            opponent_name = self.black_name if color == chess.WHITE else self.white_name

            self.beep_illegal()
            print()
            print(f"  {player_name} a retiré son roi. Que souhaitez-vous ?")
            print("    1. Abandonner")
            print(f"   2. Proposer nulle à {opponent_name}")
            print("    3. Continuer la partie")

            try:
                choice = input("  Votre choix [1/2/3] : ").strip()
            except (KeyboardInterrupt, EOFError):
                choice = "3"

            if choice == "1":
                result = "0-1" if color == chess.WHITE else "1-0"
                print(f"\n  {player_name} abandonne. {opponent_name} gagne ! ({result})")
                if self.node:
                    self.node.comment = f"{player_name} abandonne"
                self._end_game(result)
                return True

            elif choice == "2":
                print(f"\n  {opponent_name}, acceptez-vous la nulle ?")
                try:
                    answer = input("  (o/n) : ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    answer = "n"

                if answer == "o":
                    print(f"\n  Nulle acceptée ! (1/2-1/2)")
                    if self.node:
                        self.node.comment = "Nulle par accord mutuel"
                    self._end_game("1/2-1/2")
                    return True
                else:
                    print(f"  {opponent_name} refuse la nulle. La partie continue.")
                    king_name = chess.square_name(king_sq)
                    print(f"  Replacez le roi sur {king_name} pour continuer.")
                    self._resignation_pending = False
                    self._wait_for_king_replaced(king_sq, color)
                    return False

            else:
                king_name = chess.square_name(king_sq)
                print(f"  Replacez le roi sur {king_name} pour continuer.")
                self._resignation_pending = False
                self._wait_for_king_replaced(king_sq, color)
                return False

        return False

    def _wait_for_king_replaced(self, king_sq: int, color: chess.Color) -> None:
        king_name = chess.square_name(king_sq)
        try:
            self.nl_inst.set_led(king_name, True)
        except Exception:
            pass
        while True:
            hardware = self.get_hardware_piece_placement()
            if hardware:
                try:
                    hw_board = chess.Board(hardware + " w - - 0 1")
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

    # ── Fin de partie ─────────────────────────────────────────────────────

    def _end_game(self, result: str) -> None:
        """
        Gere la fin de partie : sauvegarde PGN avec demande a l'utilisateur.
        """
        # Sauvegarder d'abord dans le tmp avec le resultat final
        self.save_pgn_tmp(result)

        # Demander si on veut sauvegarder
        save, game_type, final_path = ask_save_pgn(
            mode="Human",
            white=self.white_name,
            black=self.black_name,
            default_game_type=self.default_game_type,
        )

        finalize_pgn(self.tmp_path, save, final_path)

        try:
            self.nl_inst.turn_off_all_leds()
        except Exception:
            pass

        self.game_over = True
        sys.exit(0)

    def check_for_game_over(self):
        if not self.board.is_game_over():
            return
        result = self.board.result()
        if result == "1-0":
            winner = self.white_name
        elif result == "0-1":
            winner = self.black_name
        else:
            winner = "Nulle"
        print(f"\nPartie terminee -- {winner}  ({result})")
        self._end_game(result)

    # ── Sauvegarde PGN ────────────────────────────────────────────────────

    def save_pgn_tmp(self, result="*"):
        """Sauvegarde dans le fichier temporaire (appelee a chaque coup)."""
        headers = {
            "Event": "Human vs Human",
            "Site": "Chessnut Air",
            "Date": datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S"),
            "White": self.white_name,
            "Black": self.black_name,
            "Result": result,
        }
        moves = list(self.game.mainline_moves())
        try:
            build_and_save_pgn(
                headers=headers,
                moves=moves,
                output_path=self.tmp_path,
            )
        except Exception as e:
            logger.error(f"Erreur sauvegarde tmp: {e}")

    # ── Tour ──────────────────────────────────────────────────────────────

    def ensure_updated_board(self):
        hardware = self.get_hardware_piece_placement()
        if not hardware:
            return None

        expected = self.board.board_fen()
        move = self.get_legal_move_matching_hardware(hardware)

        if hardware == expected:
            if getattr(self, "illegal_warning_active", False):
                self.clear_illegal_warning()
                print("Position retablie. Reprenez la partie.")
            else:
                self.clear_illegal_warning()
            self._stable_count = 0
            self._last_raw_fen = hardware
            self._king_absent_since = None
            return None

        if move is not None:
            self._stable_count = 0
            self._last_raw_fen = None
            self.clear_illegal_warning()
            return move

        # Verifier abandon avant de signaler coup illegal
        # Délai 1 seconde : évite de déclencher le menu quand le joueur
        # bouge son roi légalement (il pose puis soulève brièvement)
        if not self._resignation_pending:
            # Vérifier si un roi est absent
            king_absent = False
            absent_color = None
            absent_sq = None
            try:
                hw_board = chess.Board(hardware + " w - - 0 1")
                for color in (chess.WHITE, chess.BLACK):
                    ksq = self.board.king(color)
                    if ksq is None:
                        continue
                    ep = self.board.piece_at(ksq)
                    if ep and ep.piece_type == chess.KING and hw_board.piece_at(ksq) is None:
                        king_absent = True
                        absent_color = color
                        absent_sq = ksq
                        break
            except Exception:
                pass

            if king_absent:
                if self._king_absent_since is None:
                    self._king_absent_since = time.time()
                elif time.time() - self._king_absent_since >= 1.0:
                    # Roi absent depuis 1 seconde → déclencher le menu
                    self._king_absent_since = None
                    if self.check_resignation(hardware):
                        return None
            else:
                self._king_absent_since = None

        if self._leds_showing_turn:
            try:
                self.nl_inst.turn_off_all_leds()
            except Exception:
                pass
            self._leds_showing_turn = False

        if hardware == self._last_raw_fen:
            self._stable_count += 1
        else:
            self._last_raw_fen = hardware
            self._stable_count = 1

        if self._stable_count >= self.illegal_stable_reads_required:
            self.report_illegal_position(hardware)

        return None

    def handle_turn(self):
        while not self.game_over:
            move = self.ensure_updated_board()
            if move is None:
                time.sleep(self.poll_delay)
                continue

            if self._leds_showing_turn:
                try:
                    self.nl_inst.turn_off_all_leds()
                except Exception:
                    pass
                self._leds_showing_turn = False

            is_white_turn = (self.board.turn == chess.WHITE)
            san = san_ep(self.board, move)
            self.board.push(move)
            self.node = self.node.add_variation(move)

            player_name = self.white_name if is_white_turn else self.black_name
            color = "white" if is_white_turn else "black"

            display_move(player_name, color, san)
            display_check_status(self.board)
            # Sauvegarde intermediaire dans le tmp
            self.save_pgn_tmp()
            self.check_for_game_over()
            return

    def report_illegal_position(self, hardware, reason="Position illegale"):
        if getattr(self, "illegal_warning_active", False):
            return
        self.illegal_warning_active = True
        self.last_illegal_piece_placement = hardware
        self.beep_illegal()
        print()
        expected = self.board.board_fen()
        diffs = sum(1 for a, b in zip(expected, hardware) if a != b)
        try:
            hw_board = chess.Board(hardware + " w - - 0 1")
        except Exception:
            hw_board = None
        if self.board.is_check():
            print("⚠  Echec au roi ! Parez l'echec avant de jouer.")
            if hw_board:
                try:
                    self.nl_inst.show_board_diff(self.board, hw_board)
                    king_sq = chess.square_name(self.board.king(self.board.turn))
                    self.nl_inst.set_led(king_sq, True)
                except Exception:
                    pass
        elif diffs > 4:
            print("⚠  Plusieurs pieces ont bouge -- remettez l'échiquier en ordre.")
            if hw_board:
                try:
                    self.nl_inst.show_board_diff(self.board, hw_board)
                except Exception:
                    pass
        else:
            print("⚠  Coup illegal -- remettez la piece a sa place.")
            if hw_board:
                try:
                    self.nl_inst.show_board_diff(self.board, hw_board)
                except Exception:
                    pass
        print(f"   Position attendue : {expected}")
        print(f"   Position detectee : {hardware}")
        print()

    def clear_illegal_warning(self):
        try:
            self.nl_inst.turn_off_all_leds()
        except Exception as exc:
            logger.debug(f"LED clear failed: {exc}")
        self._leds_showing_turn = False
        self.illegal_warning_active = False
        self.last_illegal_piece_placement = None

    def run(self):
        print("Partie demarree")
        print(f"  Blancs : {self.white_name}")
        print(f"  Noirs  : {self.black_name}")
        if self.turn_signal != "none":
            sig_desc = {
                "beep": "Début de tour -> Bip / Coup illégal -> Bip Echiquier",
                "leds": "Début de tour -> Leds / Coup illégal -> Bip Echiquier",
                "both": "Début de tour -> Bip + Leds / Coup illégal -> Bip Echiquier",
            }.get(self.turn_signal, "")
            print(f"  Signaux : {sig_desc}")
        print("  Abandon : retirez votre roi de l'échiquier")
        print()

        while not self.game_over:
            color = "white" if self.board.turn == chess.WHITE else "black"
            player = self.white_name if self.board.turn == chess.WHITE else self.black_name
            display_turn(player, color)
            self.signal_turn()
            self.handle_turn()


# ──────────────────────────────────────────────
# Menu joueurs
# ──────────────────────────────────────────────

def prompt_player(color_label, players, forbidden_name=None):
    forbidden_norm = normalize_player_name(forbidden_name) if forbidden_name else None
    while True:
        print()
        print(f"Choix du joueur {color_label} :")
        if players:
            for i, player in enumerate(players, start=1):
                print(f"{i}. {player}")
        else:
            print("(aucun joueur enregistre)")
        print("N. Nouveau joueur")
        choice = input("Votre choix : ").strip()
        if not choice:
            continue
        if choice.lower() == "n":
            name = input("Nom du joueur : ").strip()
            if not name:
                print("Nom vide, recommence.")
                continue
            existing = find_existing_player(players, name)
            if existing:
                if forbidden_norm and normalize_player_name(existing) == forbidden_norm:
                    print("Ce joueur est deja choisi de l'autre cote.")
                    continue
                print(f"Joueur deja existant : {existing}")
                return existing, players
            if forbidden_norm and normalize_player_name(name) == forbidden_norm:
                print("Ce joueur est deja choisi de l'autre cote.")
                continue
            save_choice = input("Enregistrer ce joueur ? (o/n) : ").strip().lower()
            final_name = " ".join(name.split())
            if save_choice == "o":
                players.append(final_name)
                players.sort(key=lambda x: x.casefold())
                save_players(players)
                print(f"Joueur enregistre : {final_name}")
            return final_name, players
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(players):
                selected = players[idx]
                if forbidden_norm and normalize_player_name(selected) == forbidden_norm:
                    print("Ce joueur est deja choisi de l'autre cote.")
                    continue
                return selected, players
        print("Choix invalide, recommence.")


# ──────────────────────────────────────────────
# Point d'entree
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--white", help="Nom du joueur blanc")
    parser.add_argument("--black", help="Nom du joueur noir")
    args = parser.parse_args()

    config = load_config()
    players = load_players()

    if args.white:
        existing_white = find_existing_player(players, args.white)
        white = existing_white if existing_white else " ".join(args.white.strip().split())
    else:
        print("\n=== NicLink — Humain vs Humain ===")
        if players:
            for i, p in enumerate(players, start=1):
                print(f"{i}. {p}")
        else:
            print("(aucun joueur enregistré)")
        print("N. Nouveau joueur")
        print("Entrée seule = partie anonyme")
        quick = input("\nJoueur blanc : ").strip()
        if not quick:
            white = "Anonyme"
            black = "Anonyme"
            args_black_skip = True
        else:
            args_black_skip = False
            existing = find_existing_player(players, quick)
            white = existing if existing else quick

    if locals().get("args_black_skip"):
        pass  # black déjà défini comme "Anonyme"
    elif args.black:
        existing_black = find_existing_player(players, args.black)
        black = existing_black if existing_black else " ".join(args.black.strip().split())
        if normalize_player_name(black) == normalize_player_name(white):
            print("Le joueur noir ne peut pas etre identique au joueur blanc.")
            return
    else:
        black, players = prompt_player("noir", players, forbidden_name=white)
    _nl_ref = [None]
    _game_ref = [None]
    
    def _emergency_shutdown(signum, frame):
        print("\nArret demande par l'utilisateur.")
        if _nl_ref[0] is not None:
            try:
                _nl_ref[0].turn_off_all_leds()
            except Exception:
                pass
        # Nettoyage du fichier tmp si la partie n'a pas ete sauvegardee
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
        nl_inst = NicLinkManager(refresh_delay=0.1, logger=logger, thread_sleep_delay=0.1)
        _nl_ref[0] = nl_inst

        wait_for_initial_position(nl_inst)

        game = Game(
            nl_inst, white, black,
            turn_signal=config.get("turn_signal", "beep"),
            default_game_type=config.get("game_type", "Serious"),
        )
        _game_ref[0] = game
        game.start()

        while game.is_alive():
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nArret demande par l'utilisateur.")

    finally:
        if nl_inst is not None:
            try:
                nl_inst.turn_off_all_leds()
            except Exception:
                pass



class GameWeb(threading.Thread):
    """
    Partie Humain vs Humain avec :
    - Interface web (SocketIO)
    - Module pause (navigation, changement de camp)
    """

    def __init__(self, nl_inst, white_name="Anonyme1", black_name="Anonyme2",
                 default_game_type="Serious", **kwargs):
        super().__init__(daemon=True, **kwargs)
        self.nl_inst          = nl_inst
        self.white_name       = white_name
        self.black_name       = black_name
        self.default_game_type = default_game_type

        self.board            = chess.Board()
        nl_inst.game_board    = chess.Board()  # synchroniser dès le départ
        self._pgn_game        = chess.pgn.Game()
        self._pgn_node        = self._pgn_game
        self._pgn_game.headers["Event"] = "Humain vs Humain"
        self._pgn_game.headers["White"] = white_name
        self._pgn_game.headers["Black"] = black_name

        self.game_over        = False
        self.tmp_path         = build_tmp_path()

        # Analyse Stockfish (non bloquante)
        # Pas d'analyse Stockfish en HH — les joueurs jouent rapidement

        # Flags
        self._abandon_demande   = False
        self._abandon_couleur   = None
        self._nulle_hh_demandee = False
        self._back_menu_demande = False
        self._pause_demandee    = False
        self._stockfish_resumes_after_pause = False
        self._human_resumes_after_pause     = False
        self._undo_pending      = False   # True = en attente de confirmation undo

        self.move_gaps      = []
        self.last_move_time = time.time()

    # ── Sauvegarde temporaire ──────────────────────────────────────────────

    def save_pgn_tmp(self, result="*"):
        import os
        self._pgn_game.headers["Result"] = result
        os.makedirs(os.path.dirname(self.tmp_path), exist_ok=True)
        with open(self.tmp_path, "w", encoding="utf-8") as f:
            f.write(str(self._pgn_game))

    # ── Analyse background ────────────────────────────────────────────────



    # ── Tour humain ───────────────────────────────────────────────────────

    def _handle_turn(self):
        """Attend et valide le coup du joueur courant."""
        is_white = self.board.turn == chess.WHITE
        player   = self.white_name if is_white else self.black_name
        color    = "white" if is_white else "black"

        send_event("turn", {"color": color, "player": player, "is_human": True})
        self.nl_inst.turn_off_all_leds()
        # Signal LED (plus discret que le bip en HH)
        try:
            sig = 3 if is_white else 2
            self.nl_inst.signal_lights(sig)
        except Exception:
            pass

        fen_avant = self.board.fen()
        expected  = self.board.board_fen()

        watch_stop = threading.Event()

        def watch_actions():
            while not watch_stop.is_set():
                action = get_action(timeout=0.05)
                if action is None:
                    continue
                atype = action.get("type", "")
                if atype == "pause":
                    self._pause_demandee = True
                    self.nl_inst.kill_switch.set()
                    return
                elif atype == "abandonner":
                    self._abandon_demande   = True
                    self._abandon_couleur   = action.get("couleur", None)
                    self.nl_inst.kill_switch.set()
                    return
                elif atype == "nulle_hh":
                    self._nulle_hh_demandee = True
                    self.nl_inst.kill_switch.set()
                    return
                elif atype == "undo_move":
                    # Annuler le dernier coup si possible
                    if len(self.board.move_stack) > 0:
                        last_move = self.board.peek()
                        from_sq = chess.square_name(last_move.from_square)
                        to_sq   = chess.square_name(last_move.to_square)
                        self.board.pop()
                        # Remonter le nœud PGN
                        if self._pgn_node.parent is not None:
                            self._pgn_node = self._pgn_node.parent
                        self.nl_inst.game_board = self.board.copy()
                        # LEDs sur les cases du coup annulé
                        try:
                            self.nl_inst.set_led(from_sq, True)
                            self.nl_inst.set_led(to_sq, True)
                        except Exception:
                            pass
                        self.save_pgn_tmp()
                        send_event("undo_move", {
                            "fen":     self.board.board_fen(),
                            "from_sq": from_sq,
                            "to_sq":   to_sq,
                        })
                        self._undo_pending = True
                        self.nl_inst.kill_switch.set()
                    else:
                        send_event("undo_impossible", {"message": "Pas de coup à annuler."})
                    return
                elif atype == "back_menu":
                    self._abandon_demande    = True
                    self._back_menu_demande  = True
                    self.nl_inst.kill_switch.set()
                    return

        watcher = threading.Thread(target=watch_actions, daemon=True)
        watcher.start()

        # Watcher de position illégale : informe le navigateur si position anormale
        _illegal_reported = [False]

        def watch_position():
            import time as _time
            stable_count = 0
            last_fen = None
            STABLE_NEEDED = 32  # ~1.6s de stabilité avant de signaler
            while not watch_stop.is_set():
                _time.sleep(0.05)
                try:
                    raw = self.nl_inst.current_fen
                    phys = raw.strip().split()[0] if raw else ""
                except Exception:
                    continue
                if phys == expected:
                    # Position correcte — effacer avertissement si actif
                    if _illegal_reported[0]:
                        _illegal_reported[0] = False
                        is_white2 = self.board.turn == chess.WHITE
                        player2   = self.white_name if is_white2 else self.black_name
                        color2    = "white" if is_white2 else "black"
                        from nicsoft.engine.board_utils import analyser_position_illegale as _a
                        send_event("turn", {
                            "color":    color2,
                            "player":   player2,
                            "is_human": True,
                            "in_check": self.board.is_check(),
                        })
                    stable_count = 0
                    last_fen = phys
                    continue
                if phys == last_fen:
                    stable_count += 1
                else:
                    stable_count = 1
                    last_fen = phys
                if stable_count >= STABLE_NEEDED and not _illegal_reported[0]:
                    _illegal_reported[0] = True
                    try:
                        from nicsoft.engine.board_utils import analyser_position_illegale
                        msg = analyser_position_illegale(self.board, phys)
                    except Exception:
                        msg = "⚠ Position illégale — remettez la pièce à sa place."
                    # Deux bips rapprochés
                    try:
                        self.nl_inst.beep()
                        time.sleep(0.15)
                        self.nl_inst.beep()
                    except Exception:
                        pass
                    send_event("illegal_position", {"message": msg})

        pos_watcher = threading.Thread(target=watch_position, daemon=True)
        pos_watcher.start()

        # Synchroniser nl_inst.game_board avec self.board AVANT await_move
        # (await_move compare le physique avec game_board en interne)
        self.nl_inst.game_board = self.board.copy()

        move = None
        _t_await = time.time()
        try:
            move = self.nl_inst.await_move()
            tlog("[TIMING] await_move: %.2fs — move=%s", time.time()-_t_await, move)
        except Exception:
            pass
        finally:
            watch_stop.set()
            watcher.join(timeout=1.0)
            pos_watcher.join(timeout=1.0)

        if self._abandon_demande or self._pause_demandee:
            return None

        if move is None:
            return None

        # Valider le coup
        try:
            move_obj = chess.Move.from_uci(move)
            if move_obj not in self.board.legal_moves:
                return None
            san = san_ep(self.board, move_obj)
        except Exception:
            return None

        self.board.push(move_obj)
        self.nl_inst.game_board = self.board.copy()  # garder game_board synchro
        self._pgn_node = self._pgn_node.add_variation(move_obj)

        # Envoyer le coup avant save_pgn_tmp (I/O disque ne doit pas retarder l'affichage)
        _t_send = time.time()
        send_event("move", {
            "fen":    self.board.board_fen(),
            "san":    san,
            "uci":    move,
            "color":  color,
            "player": player,
            "qualite": None,
        })
        tlog("[TIMING] send_event+traitement: %.2fs", time.time()-_t_send)

        self.save_pgn_tmp()

        now = time.time()
        self.move_gaps.append(round(now - self.last_move_time, 2))
        self.last_move_time = now

        return move_obj

    # ── Pause ─────────────────────────────────────────────────────────────

    def _handle_pause(self):
        """Gère la pause interactive. Retourne changer_couleur (bool)."""
        self.nl_inst.turn_off_all_leds()
        set_app_state("paused", {
            "history_fen":   _game_state.get("history_fen", []),
            "history_moves": _game_state.get("history", []),
        })
        send_event("pause", {
            "playing_white": self.board.turn == chess.WHITE,
            "player": f"{self.white_name} / {self.black_name}",
        })

        changer_couleur = False
        target_fen      = None

        while True:
            action = get_action(timeout=1.0)
            if action is None:
                continue
            atype = action.get("type", "")
            if atype == "reprendre":
                changer_couleur = action.get("changer_couleur", False)
                target_fen      = action.get("fen", None)
                break
            elif atype == "resume_pause":
                break
            elif atype in ("abandonner", "back_menu"):
                self._abandon_demande   = True
                self._back_menu_demande = (atype == "back_menu")
                self._abandon_couleur   = action.get("couleur", None)
                self._traiter_abandon()
                return False

        # Tronquer historique si navigation
        if target_fen and target_fen != self.board.board_fen():
            board_tmp  = chess.Board()
            move_stack = list(self.board.move_stack)
            fens_seen  = [board_tmp.board_fen()]
            for mv in move_stack:
                board_tmp.push(mv)
                fens_seen.append(board_tmp.board_fen())
            if target_fen in fens_seen:
                idx = fens_seen.index(target_fen)
                # Reconstruire self.board
                self.board = chess.Board()
                for mv in move_stack[:idx]:
                    self.board.push(mv)
                # Reconstruire _pgn_game et _pgn_node depuis les coups tronqués
                self._pgn_game = chess.pgn.Game()
                self._pgn_game.headers["Event"] = "Humain vs Humain"
                self._pgn_game.headers["White"] = self.white_name
                self._pgn_game.headers["Black"] = self.black_name
                self._pgn_node = self._pgn_game
                replay_board = chess.Board()
                for mv in move_stack[:idx]:
                    self._pgn_node = self._pgn_node.add_variation(mv)
                    replay_board.push(mv)

        # Changer les noms si changement de camp
        if changer_couleur:
            self.white_name, self.black_name = self.black_name, self.white_name
            self._pgn_game.headers["White"] = self.white_name
            self._pgn_game.headers["Black"] = self.black_name
            send_event("swap_color_hh", {
                "white": self.white_name,
                "black": self.black_name,
            })

        # Vérifier position physique
        expected = self.board.board_fen()
        current  = (self.nl_inst.current_fen or "").strip().split()[0]
        if current != expected:
            from nicsoft.web.server import action_queue as _aq
            while not _aq.empty():
                try: _aq.get_nowait()
                except Exception: break
            send_event("pause_wait_position", {
                "fen": expected, "physical_fen": current,
                "message": "Reproduisez la position sur l'échiquier.",
            })
            while True:
                phys = (self.nl_inst.current_fen or "").strip().split()[0]
                if phys == expected:
                    break
                send_event("position_error", {"expected_fen": expected, "physical_fen": phys})
                time.sleep(0.2)
            send_event("position_ok", {"fen": expected})

        # Historique tronqué → envoyer resume
        board_tmp2 = chess.Board()
        resume_fens  = [board_tmp2.board_fen()]
        resume_moves = []
        for mv in self.board.move_stack:
            san_mv = san_ep(board_tmp2, mv)
            col    = "white" if board_tmp2.turn == chess.WHITE else "black"
            plr    = self.white_name if board_tmp2.turn == chess.WHITE else self.black_name
            board_tmp2.push(mv)
            resume_fens.append(board_tmp2.board_fen())
            resume_moves.append({"san": san_mv, "uci": mv.uci(), "color": col, "qualite": "bon"})

        set_app_state("playing")
        # Resynchroniser _game_state avec move_stack (source de vérité)
        _game_state["history"]     = list(resume_moves)
        _game_state["history_fen"] = list(resume_fens)
        set_app_state("playing")
        send_event("resume", {"history_fen": resume_fens, "history_moves": resume_moves})
        return changer_couleur

    # ── Abandon ───────────────────────────────────────────────────────────


    def _build_history_from_stack(self):
        """Reconstruit history_fen et history_moves depuis self.board.move_stack."""
        b = chess.Board()
        fens  = [b.board_fen()]
        moves = []
        for mv in self.board.move_stack:
            san = san_ep(b, mv)
            col = "white" if b.turn == chess.WHITE else "black"
            b.push(mv)
            fens.append(b.board_fen())
            moves.append({"san": san, "uci": mv.uci(), "color": col, "qualite": None})
        return fens, moves

    def _traiter_abandon(self):
        skip = self._back_menu_demande
        if self._back_menu_demande:
            result = "*"
            gagnant = ""
        elif self._abandon_couleur == "blanc":
            result  = "0-1"
            gagnant = self.black_name
        elif self._abandon_couleur == "noir":
            result  = "1-0"
            gagnant = self.white_name
        else:
            result  = "0-1" if self.board.turn == chess.WHITE else "1-0"
            gagnant = self.black_name if self.board.turn == chess.WHITE else self.white_name
        title = f"{gagnant} gagne" if gagnant else "Partie terminée"
        title_key  = "game.titre_gagne" if gagnant else "game.fin_partie_default"
        title_vars = {"winner": gagnant} if gagnant else {}
        self.game_over = True
        self.save_pgn_tmp(result)
        _hist_fens, _hist_moves = self._build_history_from_stack()
        send_event("game_over", {
            "result": result,
            "reason": "Abandon",
            "source": "niclink",
            "title":      title,
            "title_key":  title_key,
            "title_vars": title_vars,
            "skip":   skip,
        })
        from nicsoft.web import server as _web_server
        if not skip:
            _web_server._app_state = "game_over"
            set_app_state("game_over", {
                "title":         title,
                "result":        result,
                "source":        "niclink",
                "skip":          False,
                "history_fen":   _hist_fens,
                "history_moves": _hist_moves,
            })
        else:
            # back_menu : sortie immédiate, le menu est déjà affiché
            sys.exit(0)

    # ── Fin de partie ─────────────────────────────────────────────────────

    def _check_game_over(self):
        if self.board.is_checkmate():
            winner = "Noirs" if self.board.turn == chess.WHITE else "Blancs"
            winner_key = "config.noirs" if self.board.turn == chess.WHITE else "config.blancs"
            result = "0-1" if self.board.turn == chess.WHITE else "1-0"
            self.game_over = True
            self.save_pgn_tmp(result)
            send_event("game_over", {
                "result": result, "reason": f"Échec et mat — {winner} gagnent",
                "source": "niclink", "title": "Fin de partie",
                "title_key": "game.fin_partie_default",
            })
            from nicsoft.web import server as _web_server
            _web_server._app_state = "game_over"
            _hist_fens, _hist_moves = self._build_history_from_stack()
            set_app_state("game_over", {
                "title": "Fin de partie", "result": result,
                "source": "niclink",
                "history_fen":   _hist_fens,
                "history_moves": _hist_moves,
            })
        elif self.board.is_stalemate() or self.board.is_insufficient_material():
            self.game_over = True
            self.save_pgn_tmp("1/2-1/2")
            send_event("game_over", {
                "result": "1/2-1/2", "reason": "Nulle",
                "source": "niclink", "title": "Nulle",
                "title_key": "game.titre_nulle",
            })
            from nicsoft.web import server as _web_server
            _web_server._app_state = "game_over"
            _hist_fens2, _hist_moves2 = self._build_history_from_stack()
            set_app_state("game_over", {
                "title": "Nulle", "result": "1/2-1/2",
                "source": "niclink",
                "history_fen":   _hist_fens2,
                "history_moves": _hist_moves2,
            })

    # ── Boucle principale ─────────────────────────────────────────────────

    def start(self):
        """Lance la partie (appelé depuis web/__main__.py)."""
        self.run()

    def run(self):
        while not self.game_over:
            if self._pause_demandee:
                self._pause_demandee = False
                self._handle_pause()
                # Réarmer le kill_switch pour que await_move fonctionne à nouveau
                try:
                    self.nl_inst.kill_switch.clear()
                except Exception:
                    pass
                continue

            if self._abandon_demande:
                self._traiter_abandon()
                return

            if self._nulle_hh_demandee:
                self._nulle_hh_demandee = False
                self.game_over = True
                self.save_pgn_tmp("1/2-1/2")
                send_event("game_over", {
                    "result": "1/2-1/2", "reason": "Nulle par accord mutuel",
                    "source": "niclink", "title": "Nulle",
                })
                from nicsoft.web import server as _web_server
                _web_server._app_state = "game_over"
                _hist_fens, _hist_moves = self._build_history_from_stack()
                set_app_state("game_over", {
                    "title": "Nulle", "result": "1/2-1/2",
                    "source": "niclink",
                    "history_fen":   _hist_fens,
                    "history_moves": _hist_moves,
                })
                return

            # _handle_turn retourne le coup joué ou None si interruption
            move = self._handle_turn()
            if self._abandon_demande:
                self._traiter_abandon()
                return
            if self.game_over:
                break

            # Undo demandé — attendre confirmation physique avant de reprendre
            if self._undo_pending:
                self._undo_pending = False
                try:
                    self.nl_inst.kill_switch.clear()
                except Exception:
                    pass
                # Attendre que le joueur replace la pièce et clique Confirmer
                expected = self.board.board_fen()
                from nicsoft.web.server import action_queue as _aq
                while not _aq.empty():
                    try: _aq.get_nowait()
                    except Exception: break
                confirmed = False
                while not confirmed and not self.game_over:
                    action = get_action(timeout=0.5)
                    if action is None:
                        continue
                    atype = action.get("type", "")
                    if atype == "undo_confirm":
                        # Vérifier que la position physique correspond
                        phys = (self.nl_inst.current_fen or "").strip().split()[0]
                        if phys == expected:
                            self.nl_inst.turn_off_all_leds()
                            send_event("undo_confirmed", {"fen": expected})
                            confirmed = True
                        else:
                            send_event("undo_wait_position", {
                                "fen": expected,
                                "message": "Position incorrecte — replacez la pièce d'abord.",
                            })
                    elif atype == "back_menu":
                        self._abandon_demande   = True
                        self._back_menu_demande = True
                        self._traiter_abandon()
                        return
                    elif atype == "abandonner":
                        self._abandon_demande = True
                        self._abandon_couleur = action.get("couleur", None)
                        self._traiter_abandon()
                        return
                continue

            if move is not None:
                self._check_game_over()
            # Si move is None (pause, abandon, erreur) : reboucler sans rien faire

if __name__ == "__main__":
    main()
