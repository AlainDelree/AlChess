"""NicLink driver for ChessNut air"""

#  NicLink is free software: you can redistribute it and/or modify it under
#  the terms of the gnu general public license as published by the free
#  software foundation, either version 3 of the license, or (at your option)
#  any later version.
#
#  NicLink is distributed in the hope that it will be useful, but without any
#  warranty; without even the implied warranty of merchantability or fitness
#  for a particular purpose.
#  see the gnu general public license for more details.
#
#  you should have received a copy of the gnu general public license along with
#  NicLink. if not, see <https://www.gnu.org/licenses/>.

import logging

# system
import sys
import threading
import time

# pip libraries
import chess
import numpy as np
import numpy.typing as npt

from . import _niclink

# mine
from .nl_exceptions import ExitNicLink, IllegalMove, NoMove, NoNicLinkFen

### CONSTANTS ###
ONES = np.array(
    [
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
    ],
    dtype=np.str_,
)
ZEROS = np.array(
    [
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
    ],
    dtype=np.str_,
)

FILES = np.array(["a", "b", "c", "d", "e", "f", "g", "h"])

NO_MOVE_DELAY = 0.005  # I think having a logger delay makes board unresponsive

LIGHT_THREAD_DELAY = 0.2

# Délai entre deux lectures USB dans le thread fen_reader.
# 0.05s = 20 lectures/sec — assez réactif sans saturer le port USB.
FEN_READER_DELAY = 0.05

# get a logger, should have structured the module better
logger = logging.getLogger(__name__)


class NicLinkManager(threading.Thread):
    """manage ChessNut air external board in it's own thread"""

    def __init__(
        self,
        refresh_delay: float,
        logger: logging.Logger | None,
        thread_sleep_delay=1,
        bluetooth: bool = False,
    ):
        """initialize the link to the chessboard, and set up NicLink"""

        # initialize the thread, as a daemon
        threading.Thread.__init__(self, daemon=True)

        # HACK: delay for how long threads should sleep, letting threads work
        self.thread_sleep_delay = thread_sleep_delay

        # ensure we have a logger
        if logger is None:
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logger

        # connect with the external board usb
        self.nl_interface = _niclink

        self.refresh_delay = refresh_delay

        # FEN partagé : mis à jour exclusivement par _fen_reader_thread.
        self.current_fen        = ""
        self._fen_reader_stop   = threading.Event()
        self._fen_lock          = threading.Lock()  # exclusif à get_fen()

        # Queue LED fire-and-forget.
        # Toutes les commandes LED postent ici et retournent immédiatement.
        # Le _led_worker les consomme dans son thread — jamais de blocage USB
        # dans le thread principal.
        import queue as _queue_mod
        self._led_queue         = _queue_mod.Queue()
        self._led_cancel        = threading.Event()  # annule la commande en cours
        self._led_worker_thread = None

        self._usb_lock          = threading.Lock()  # alias de compatibilité (beep legacy)
        self._fen_reader_thread = None

        try:
            self.connect()
        except RuntimeError:
            print(
                "Error: Can not connect to the chess board. Is it connected \
and turned on?"
            )
            sys.exit("board connection error.")

        # set NicLink values to defaults
        self.reset()

        # threading lock
        self.lock = threading.Lock()

        # Démarrer le thread de lecture USB
        self._start_fen_reader()
        # Démarrer le worker LED
        self._start_led_worker()

    # ──────────────────────────────────────────────
    # Thread LED worker fire-and-forget
    # ──────────────────────────────────────────────

    def _start_led_worker(self) -> None:
        self._led_worker_thread = threading.Thread(
            target=self._led_worker_loop,
            daemon=True,
            name="led_worker",
        )
        self._led_worker_thread.start()

    def _led_worker_loop(self) -> None:
        """Consomme les commandes LED une par une.
        
        Commandes :
          ("lights_out",)           — éteindre tout (prioritaire)
          ("set_all", array)        — allumer un pattern
          ("set_led", row, col, v)  — allumer une case
          ("signal", array, delay)  — allumer pattern puis éteindre après delay
          ("beep",)                 — bip
          
        Pour "signal" : le worker allume le pattern, puis attend `delay` secondes
        en dormant par petits intervalles. Si une commande "lights_out" arrive
        pendant l'attente, il éteint immédiatement et passe à la suite.
        L'attente n'utilise pas de lock USB — elle est purement Python.
        """
        import queue as _queue_mod
        while True:
            try:
                cmd = self._led_queue.get(timeout=1.0)
            except _queue_mod.Empty:
                continue
            try:
                kind = cmd[0]
                if kind == "lights_out":
                    self._led_cancel.set()   # annule tout signal en cours
                    self.nl_interface.lights_out()
                    self._led_cancel.clear()
                elif kind == "set_all":
                    arr = cmd[1]
                    self.nl_interface.set_all_leds(
                        str(arr[0]), str(arr[1]), str(arr[2]), str(arr[3]),
                        str(arr[4]), str(arr[5]), str(arr[6]), str(arr[7]),
                    )
                elif kind == "set_led":
                    self.nl_interface.set_led(cmd[1], cmd[2], cmd[3])
                elif kind == "signal":
                    arr, delay = cmd[1], cmd[2]
                    self._led_cancel.clear()
                    # 1. Allumer le pattern (appel USB — peut être lent)
                    self.nl_interface.set_all_leds(
                        str(arr[0]), str(arr[1]), str(arr[2]), str(arr[3]),
                        str(arr[4]), str(arr[5]), str(arr[6]), str(arr[7]),
                    )
                    # 2. Attendre delay en dormant par petits pas
                    #    Si lights_out arrive entre-temps → _led_cancel est set
                    #    et on sort sans éteindre (lights_out le fera lui-même)
                    deadline = time.time() + delay
                    while time.time() < deadline:
                        if self._led_cancel.is_set():
                            break
                        # Vérifier si un lights_out prioritaire est en queue
                        try:
                            peek = self._led_queue.get_nowait()
                            if peek[0] == "lights_out":
                                self._led_cancel.set()
                                self._led_queue.put(peek)  # remettre pour traitement
                            else:
                                self._led_queue.put(peek)
                        except _queue_mod.Empty:
                            pass
                        time.sleep(0.05)
                    else:
                        # Délai écoulé sans interruption → éteindre
                        if not self._led_cancel.is_set():
                            self.nl_interface.lights_out()
                elif kind == "beep":
                    self.nl_interface.beep()
            except Exception as e:
                self.logger.debug("led_worker error: %s", e)
            finally:
                try:
                    self._led_queue.task_done()
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # Thread de lecture USB dédié
    # ──────────────────────────────────────────────

    def _start_fen_reader(self) -> None:
        """Démarre le thread qui lit get_fen() en continu."""
        self._fen_reader_stop.clear()
        self._fen_reader_thread = threading.Thread(
            target=self._fen_reader_loop,
            daemon=True,
            name="fen_reader",
        )
        self._fen_reader_thread.start()
        self.logger.debug("fen_reader thread started")

    def _stop_fen_reader(self) -> None:
        """Arrête le thread de lecture USB."""
        self._fen_reader_stop.set()
        if self._fen_reader_thread is not None:
            self._fen_reader_thread.join(timeout=2.0)
            self._fen_reader_thread = None

    def _fen_reader_loop(self) -> None:
        """
        Boucle principale du thread de lecture USB.
        Seul endroit où nl_interface.get_fen() est appelé pendant une partie.
        Met à jour self.current_fen après chaque lecture réussie.
        """
        from nicsoft.utils.timing import tlog
        _slow_count = 0
        _lock_wait_count = 0
        while not self._fen_reader_stop.is_set():
            try:
                _t_lock = time.time()
                with self._fen_lock:
                    _lock_wait = time.time() - _t_lock
                    if _lock_wait > 0.1:
                        _lock_wait_count += 1
                        tlog("[DRIVER] fen_lock attendu: %.3fs (total: %d)", _lock_wait, _lock_wait_count)
                    _t = time.time()
                    fen = self.nl_interface.get_fen()
                    _elapsed = time.time() - _t
                    if _elapsed > 0.1:
                        _slow_count += 1
                        tlog("[DRIVER] get_fen lent: %.3fs (total slow: %d)", _elapsed, _slow_count)
                    if fen is not None:
                        self.current_fen = fen
            except Exception:
                pass
            time.sleep(FEN_READER_DELAY)

    def start_960(self, starting_fen: str) -> None:
        """Start a chess 960 game"""
        self.reset()
        self.starting_fen = starting_fen
        self.game_board = chess.Board(self.starting_fen)
        self.logger.info("start_960(...): 960 game started. Initial fen: %s", self.starting_fen)

    def run(self) -> None:
        """run and wait for a game to begin"""
        while not self.kill_switch.is_set():
            if self.start_game.is_set():
                self.logger.info("_run_game is set. (run)")
                self._run_game()
            time.sleep(self.thread_sleep_delay)

        self.disconnect()
        raise ExitNicLink("Thank you for using NicLink (raised in NicLinkManager.run()")

    def _run_game(self) -> None:
        """handle a chess game over NicLink"""
        self.game_over.wait()
        self.reset()
        self.logger.info("\n\n _run_game(...): game_over event set, resetting NicLink\n")

    def connect(self, bluetooth: bool = False) -> None:
        """connect to the chessboard"""
        if bluetooth:
            raise NotImplementedError

        self.nl_interface.connect()

        # FIX: give time for NL to connect
        time.sleep(self.thread_sleep_delay)
        test_fen = self.nl_interface.get_fen()
        time.sleep(self.thread_sleep_delay)
        test_fen = self.nl_interface.get_fen()

        if test_fen == "":
            raise RuntimeError(
                "Board initialization error. '' or None for fen. "
                "Is the board connected and turned on?"
            )

        self.logger.debug("Board initialized. initial fen: |%s|" % test_fen)

    def disconnect(self) -> None:
        """disconnect from the chessboard"""
        self._stop_fen_reader()
        self.nl_interface.disconnect()
        self.logger.info("\n-- Board disconnected --\n")

    def beep(self) -> None:
        """make the chessboard beep"""
        with self._usb_lock:
            self.nl_interface.beep()

    def reset(self) -> None:
        """reset NicLink"""
        self.starting_fen = None
        self.game_board = chess.Board()
        self.last_move = None
        self.turn_off_all_leds()

        # Threading Events
        self.game_over   = threading.Event()
        self.has_moved   = threading.Event()
        self.kill_switch = threading.Event()
        self.start_game  = threading.Event()

        self.logger.debug("NicLinkManager reset\n")

    def set_led(self, square: str, status: bool) -> None:
        """set an led at a given square to a status — fire-and-forget"""
        found = False
        letter = square[0]
        file_num = 0
        while file_num < 8:
            if letter == FILES[file_num]:
                found = True
                break
            file_num += 1
        num = int(square[1]) - 1
        if not found:
            raise ValueError(f"{square[1]} is not a valid file")
        self._led_queue.put(("set_led", 7 - num, 7 - file_num, status))

    def set_move_leds(self, move: str) -> None:
        """highlight a move — fire-and-forget"""
        self.logger.debug("man.set_move_leds( %s ) called\n", move)
        move_led_map = build_led_map_for_move(move)
        self.set_all_leds(move_led_map)

    def turn_off_all_leds(self) -> None:
        """Vider la queue LED et poster lights_out en priorité — retour immédiat."""
        import queue as _queue_mod
        # Vider les commandes en attente (sauf lights_out déjà postés)
        while True:
            try:
                self._led_queue.get_nowait()
                self._led_queue.task_done()
            except _queue_mod.Empty:
                break
        self._led_queue.put(("lights_out",))

    def set_all_leds(self, light_board: npt.NDArray[np.str_]) -> None:
        """Poster un pattern LED — retour immédiat."""
        self.logger.debug("set_all_leds called")
        log_led_map(light_board, self.logger)
        self._led_queue.put(("set_all", light_board.copy()))

    def signal_lights(self, sig_num: int, stop=None) -> None:
        """Poster un signal LED (allume ~1.5s puis éteint) — retour immédiat."""
        if sig_num == 1:
            sig = np.array(["11111111","10000001","10111101","10100101",
                            "10100101","10111101","10000001","11111111"], dtype=np.str_)
        elif sig_num == 2:
            sig = np.array(["00000000","00000000","00000000","00000000",
                            "11111111","11111111","11111111","11111111"], dtype=np.str_)
        elif sig_num == 3:
            sig = np.array(["11111111","11111111","11111111","11111111",
                            "00000000","00000000","00000000","00000000"], dtype=np.str_)
        elif sig_num == 4:
            sig = np.array(["11111111","00000000","00000000","11111111",
                            "11111111","00000000","00000000","11111111"], dtype=np.str_)
        elif sig_num == 5:
            sig = np.array(["00011000","01011010","00011000","11111111",
                            "11111111","00011000","01011010","00011000"], dtype=np.str_)
        elif sig_num == 6:
            sig = np.array(["11000011","11011011","00011000","01100110",
                            "01100110","00011000","11011011","11000011"], dtype=np.str_)
        else:
            return
        self._led_queue.put(("signal", sig, 1.5))

    def beep(self) -> None:
        """make the chessboard beep — fire-and-forget"""
        self._led_queue.put(("beep",))

    def get_fen(self) -> str:
        """get the board fen from chessboard.
        
        Utilisé uniquement pour les opérations ponctuelles hors partie
        (connexion, wait_for_initial_position, wait_for_king_replaced...).
        Pendant une partie, utiliser current_fen mis à jour par _fen_reader.
        """
        fen = self.nl_interface.get_fen()
        if fen is not None:
            return fen
        raise NoNicLinkFen("No fen got from board")

    def put_board_fen_on_board(self, board_fen: str) -> chess.Board:
        """Return a chess.Board built from board_fen for logging purposes."""
        tmp_board = chess.Board()
        tmp_board.set_board_fen(board_fen)
        return tmp_board

    def find_move_from_fen_change(self, new_fen: str) -> str:
        """get the move that occurred to change the game_board fen into new_fen."""
        old_fen = self.game_board.board_fen()
        if new_fen == old_fen:
            self.logger.debug("no fen difference. fen was %s", old_fen)
            raise NoMove("No fen difference")

        self.logger.debug("new_fen %s", new_fen)
        self.logger.debug("old fen %s", old_fen)

        legal_moves = list(self.game_board.legal_moves)
        tmp_board = self.game_board.copy()

        # find move by brute force
        for move in legal_moves:
            tmp_board.push(move)
            if tmp_board.board_fen() == new_fen:
                self.logger.debug("move was found to be: %s", move)
                return move.uci()
            tmp_board.pop()

        error_board = chess.Board()
        error_board.set_board_fen(new_fen)
        message = (
            f"Board we see:\n{str(error_board)}\nis not a possible "
            f"result from a legal move on:\n{str(self.game_board)}\n"
        )
        raise IllegalMove(message)

    def check_game_board_against_external(self) -> bool:
        """check if the external board matches the game board"""
        return self.game_board.board_fen() == self.current_fen.strip().split()[0] if self.current_fen else False

    # Stabilisation FEN — mémorisé entre les appels à check_for_move
    _stable_fen: str = ""
    _stable_since: float = 0.0
    _illegal_fen: str = ""   # dernier FEN rejeté comme illégal
    STABLE_DELAY: float = 0.35  # secondes de stabilité requises avant validation

    def check_for_move(self) -> bool | str:
        """check if there has been a move on the chessboard.

        Utilise current_fen mis à jour par _fen_reader_thread.
        Aucun appel USB direct — plus de contention.
        Attend STABLE_DELAY secondes de stabilité avant de valider le coup.
        """
        new_fen = self.current_fen
        if not new_fen:
            return False

        # Extraire seulement la partie pièces du FEN
        new_fen = new_fen.strip().split()[0]

        try:
            # will cause an index error if game_board has no moves
            last_move = self.game_board.pop()

            # check if you just have not moved the opponent's piece
            if new_fen == self.game_board.board_fen():
                self.logger.debug(
                    "board fen is the board fen before opponent move made on chessboard. Returning"
                )
                self.game_board.push(last_move)
                self._stable_fen = ""
                return False

            self.game_board.push(last_move)
        except IndexError:
            last_move = False

        if new_fen == self.game_board.board_fen():
            self.logger.debug("no change in fen.")
            self._stable_fen = ""
            return False

        if self.game_over.is_set():
            return False

        # Stabilisation : attendre que le FEN soit stable pendant STABLE_DELAY
        now = time.time()
        if new_fen != self._stable_fen:
            self._stable_fen = new_fen
            self._stable_since = now
            return False
        if now - self._stable_since < self.STABLE_DELAY:
            return False

        # FEN stable depuis assez longtemps — tenter la validation
        # Mais si c'est le même FEN qu'on a déjà rejeté, inutile de retenter
        if new_fen == self._illegal_fen:
            return False

        try:
            self.last_move = self.find_move_from_fen_change(new_fen)
        except IllegalMove as err:
            from nicsoft.utils.timing import tlog
            tlog("[DRIVER] IllegalMove après stabilisation: %s", new_fen[:20])
            log_handled_exception(err)
            self.logger.debug(
                "\n===== move not valid, undo it and try again. "
                "it is white's turn? %s =====\n board:\n%s\n",
                self.game_board.turn,
                self.game_board,
            )
            # Mémoriser ce FEN illégal — on ne retentera que quand le FEN changera
            self._illegal_fen = new_fen
            return False

        self._stable_fen = ""
        self._illegal_fen = ""
        with self.lock:
            return self.last_move

    def await_move(self) -> str | None:
        """wait for legal move, and return it in coordinate notation."""
        attempts = 0
        while not self.kill_switch.is_set():
            self.logger.debug(
                "is game_over threading event set? %s", self.game_over.is_set()
            )
            try:
                move = False
                if self.game_over.is_set():
                    return None
                if self.check_for_move():
                    move = self.get_last_move()
                if move:
                    self.logger.debug(
                        "move %s made on external board. there where %s attempts to get",
                        move, attempts,
                    )
                    self.last_move = None  # éviter affichage parasite des LEDs
                    return move
                self.logger.debug("no move")
                time.sleep(NO_MOVE_DELAY)
                continue

            except NoMove:
                attempts += 1
                self.logger.debug("NoMove from chessboard. Attempt: %s", attempts)
                time.sleep(NO_MOVE_DELAY)
                continue

            except IllegalMove as err:
                attempts += 1
                self.logger.error(
                    "\nIllegal Move: %s | waiting NO_MOVE_DELAY= %s and checking again.\n",
                    err, NO_MOVE_DELAY,
                )
                time.sleep(NO_MOVE_DELAY)
                continue

        raise ExitNicLink(
            f"in await_move():\nkill_switch.is_set: {self.kill_switch.is_set()}"
        )

    def get_last_move(self) -> str:
        """get the last move played on the chessboard"""
        with self.lock:
            if self.last_move is None:
                raise ValueError("ERROR: last move is None")
            return self.last_move

    def make_move_game_board(self, move: str) -> None:
        """make a move on the internal rep. of the game_board."""
        self.logger.debug("move made on game board. move %s", move)
        self.game_board.push_uci(move)
        self.logger.debug(
            "made move on internal nl game board, BOARD POST MOVE:\n%s",
            self.game_board,
        )

    def set_board_fen(self, board: chess.Board, fen: str) -> None:
        """set a board up according to a fen"""
        chess.Board.set_board_fen(board, fen=fen)

    def set_game_board_fen(self, fen: str) -> None:
        """set the internal game board fen"""
        self.set_board_fen(self.game_board, fen)

    def show_fen_on_board(self, fen: str) -> chess.Board:
        """print a fen on a chessboard"""
        board = chess.Board()
        self.set_board_fen(board, fen)
        print(board)
        return board

    def show_board_state(self) -> None:
        """show the state of the real world board"""
        curfen = self.get_fen()
        self.show_fen_on_board(curfen)

    def show_game_board(self) -> None:
        """print the internal game_board."""
        print(self.game_board)

    def set_game_board(self, board: chess.Board) -> None:
        """set the game board"""
        with self.lock:
            self.game_board = board

    def square_in_last_move(self, square: str) -> bool:
        """is the square in the last move?"""
        if self.last_move:
            if square in self.last_move:
                return True
        return False

    def show_board_diff(self, board1: chess.Board, board2: chess.Board) -> bool:
        """show the difference between two boards on the chessboard LEDs"""
        self.logger.debug(
            "man.show_board_diff entered w board's \n%s\nand\n%s",
            board1, board2,
        )

        diff = False
        zeros = "00000000"
        diff_squares = []
        diff_map = np.copy(ZEROS)

        for n in range(0, 8):
            for a in range(ord("a"), ord("h")):
                square = chr(a) + str(n + 1)
                py_square = chess.parse_square(square)
                if board1.piece_at(py_square) != board2.piece_at(py_square):
                    if not self.square_in_last_move(square):
                        diff = True
                        self.logger.debug(
                            "man.show_board_diff(...): Diff found at square %s", square
                        )
                    diff_cords = square_cords(square)
                    diff_squares.append(square)
                    diff_map[diff_cords[1]] = (
                        zeros[: diff_cords[0]] + "1" + zeros[diff_cords[0] :]
                    )

        if diff:
            self.set_all_leds(diff_map)
            self.logger.debug(
                "show_board_diff: diff found --> diff_squares: %s\n", diff_squares
            )

        return diff

    def get_game_fen(self) -> str:
        """get the game board fen"""
        return self.game_board.fen()

    def is_game_over(self) -> dict | bool:
        """is the internal game over?"""
        if self.game_board.is_checkmate():
            return {
                "over": True,
                "winner": not self.game_board.turn,
                "reason": "checkmate",
            }
        if self.game_board.is_stalemate():
            return {"over": True, "winner": False, "reason": "Is a stalemate"}
        if self.game_board.is_insufficient_material():
            return {"over": True, "winner": False, "reason": "Is insufficient material"}
        if self.game_board.is_fivefold_repetition():
            return {"over": True, "winner": False, "reason": "Is fivefold repetition."}
        if self.game_board.is_seventyfive_moves():
            return {
                "over": True,
                "winner": False,
                "reason": (
                    "A game is automatically drawn if the half-move clock "
                    "since a capture or pawn move is equal to or greater "
                    "than 150. Other means to end a game take precedence."
                ),
            }
        return False

    def opponent_moved(self, move: str) -> None:
        """the other player moved in a chess game."""
        self.logger.debug("opponent moved %s", move)
        self.last_move = move
        # Ne pas allumer les LEDs ici — la couche supérieure décide

    def gameover_lights(self) -> None:
        """show some fireworks"""
        self.nl_interface.gameover_lights()


# === helper functions ===
def square_cords(square) -> tuple[int, int]:
    """find coordinates for a given square on the chess board."""
    rank = int(square[1]) - 1

    found = False
    letter = square[0]
    file_num = 0
    while file_num < 8:
        if letter == FILES[file_num]:
            found = True
            break
        file_num += 1

    if not found:
        raise ValueError(f"{square[0]} is not a valid file")

    return (file_num, rank)


def log_led_map(led_map: npt.NDArray[np.str_], loggr) -> None:
    """log led map pretty 8th file to the top"""
    loggr.debug("\nLOG LED map:\n")
    loggr.debug(str(led_map[7]))
    loggr.debug(str(led_map[6]))
    loggr.debug(str(led_map[5]))
    loggr.debug(str(led_map[4]))
    loggr.debug(str(led_map[3]))
    loggr.debug(str(led_map[2]))
    loggr.debug(str(led_map[1]))
    loggr.debug(str(led_map[0]))


def build_led_map_for_move(move: str) -> npt.NDArray[np.str_]:
    """build the led_map for a given uci move"""
    zeros = "00000000"
    logger.debug("build_led_map_for_move(%s)", move)

    led_map = np.copy(ZEROS)

    s1 = move[:2]
    s2 = move[2:]
    s1_cords = square_cords(s1)
    s2_cords = square_cords(s2)

    if s1_cords[1] != s2_cords[1]:
        led_map[s1_cords[1]] = zeros[: s1_cords[0]] + "1" + zeros[s1_cords[0] :]
        logger.debug("map after 1st move cord (cord): %s", s1_cords)
        log_led_map(led_map, logger)
        led_map[s2_cords[1]] = zeros[: s2_cords[0]] + "1" + zeros[s2_cords[0] :]
        logger.debug("led map made for move: %s\n", move)
        log_led_map(led_map, logger)
    else:
        rank = list(zeros)
        rank[s1_cords[0]] = "1"
        rank[s2_cords[0]] = "1"
        logger.debug("led rank computed: %s", rank)
        rank_str = "".join(rank)
        led_map[s1_cords[1]] = np.str_(rank_str)

    return led_map


# ==== logger setup ====
def set_up_logger() -> None:
    """Only run when this module is run as __main__"""
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(module)s %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.ERROR)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler("NicLink.log")
    logger.addHandler(file_handler)

    debug = False
    if debug:
        logger.info("DEBUG is set.")
        logger.setLevel(logging.DEBUG)
        file_handler.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
    else:
        logger.info("DEBUG not set")
        file_handler.setLevel(logging.INFO)
        logger.setLevel(logging.ERROR)
        console_handler.setLevel(logging.ERROR)


#  === exception logging ===
def log_except_hook(exc_type, exc_value, traceback):
    """catch all the thrown exceptions for logging"""
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, traceback))


def log_handled_exception(exception: Exception) -> None:
    """log a handled exception"""
    logger.debug("Exception handled: %s", exception)


# setup except hook
sys.excepthook = log_except_hook
