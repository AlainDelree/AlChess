"""
nicsoft/labo/__main__.py — NicLink
Outil d'exploration : le plateau physique est toujours la source de vérité.

Principes :
  - Le watcher suit le plateau physique en continu
  - Meilleur coup : Stockfish montre le meilleur coup (LEDs + affichage) sans le jouer
  - Auto : Stockfish joue automatiquement les coups du camp configuré
  - Analyse : évaluation de la position courante
  - Source virtuelle : naviguer dans un PGN et reproduire sur le physique
"""

import chess
from nicsoft.utils.debug import DEBUG_MODE
from nicsoft.engine.board_utils import san_ep
import logging
import threading
import time

from nicsoft.engine.engine_manager import EngineManager, find_stockfish
from nicsoft.web.server import send_event

logger = logging.getLogger("NL labo")
logger.setLevel(logging.INFO)
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter("%(name)s | %(message)s"))
logger.addHandler(_ch)


class LaboSession:

    def __init__(self, nl_inst,
                 engine_color: str = "black",
                 engine_elo: int = 1500,
                 analyse_active: bool = True,
                 engine_path: str = "",
                 engine_type: str = "stockfish",
                 maia_elo: int = 1500,
                 rodent_elo: int = 800,
                 rodent_simple: bool = False) -> None:

        self.nl_inst        = nl_inst
        self.engine_color   = chess.BLACK if engine_color == "black" else chess.WHITE
        self.analyse_active = analyse_active
        self.engine_type    = engine_type

        self.board = chess.Board()
        self._fen_history: list[str] = [chess.STARTING_FEN]
        self._auto_on              = False
        self._engine_busy          = False
        self._running              = False
        self._placement_in_progress = False
        self.active_turn            = "white"


        # ── Moteur ───────────────────────────────────────────────────────
        if engine_type == "maia":
            from nicsoft.engine.engine_manager import MaiaEngine, find_lc0, find_maia_weights
            lc0_path     = find_lc0()
            weights_path = find_maia_weights(maia_elo)
            sf_path      = find_stockfish() or "stockfish"
            if not lc0_path:     raise RuntimeError("lc0 introuvable.")
            if not weights_path: raise RuntimeError(f"Poids Maia {maia_elo} introuvables.")
            self.engine = MaiaEngine(lc0_path=lc0_path, weights_path=weights_path,
                                     maia_elo=maia_elo, stockfish_path=sf_path,
                                     analyse_active=analyse_active)
            self.engine_elo   = maia_elo
            self.engine_label = f"Maia {maia_elo}"

        elif engine_type == "rodent":
            from pathlib import Path as _Path
            rodent_path = str(_Path.home() / "NicLink" / "engines" / "rodent-iv" / "rodentIV")
            if not _Path(rodent_path).exists():
                raise RuntimeError(f"Rodent introuvable : {rodent_path}")
            self.engine = EngineManager(rodent_path, engine_elo=rodent_elo, analyse_active=analyse_active)
            if rodent_simple and self.engine._engine_play:
                try: self.engine._engine_play.configure({"Personality": "Simple"})
                except Exception: pass
            sf_path = find_stockfish() or "stockfish"
            try:
                import chess.engine as _ce
                sf_eval = _ce.SimpleEngine.popen_uci(sf_path)
                if "UCI_ShowWDL" in sf_eval.options:
                    sf_eval.configure({"UCI_ShowWDL": True})
                    self.engine._supports_wdl = True
                if self.engine._engine_eval:
                    try: self.engine._engine_eval.quit()
                    except Exception: pass
                self.engine._engine_eval = sf_eval
            except Exception as e:
                logger.warning(f"Stockfish analyse Rodent : {e}")
            self.engine_elo   = rodent_elo
            self.engine_label = f"Rodent {rodent_elo}"

        else:
            if not engine_path:
                engine_path = find_stockfish() or "stockfish"
            self.engine = EngineManager(engine_path, engine_elo=engine_elo, analyse_active=analyse_active)
            self.engine_elo   = engine_elo
            self.engine_label = f"Stockfish ~{engine_elo}elo"

    # ── Helpers ───────────────────────────────────────────────────────────

    def _fen_short(self) -> str:
        return self.board.fen().split()[0]

    def _send_position(self, last_uci: str = None) -> None:
        files = "abcdefgh"
        from_sq = to_sq = None
        if last_uci and len(last_uci) >= 4:
            from_sq = f"{files.index(last_uci[0])}-{int(last_uci[1])-1}"
            to_sq   = f"{files.index(last_uci[2])}-{int(last_uci[3])-1}"
        send_event("labo_position", {
            "fen":          self._fen_short(),
            "from":         from_sq,
            "to":           to_sq,
            "turn":         "white" if self.board.turn == chess.WHITE else "black",
            "auto":         self._auto_on,
            "can_undo":     len(self._fen_history) > 1,
            "in_check":     self.board.is_check(),
            "engine_turn":  self.board.turn == self.engine_color,
        })

    def _check_end(self, signal_check: bool = True) -> bool:
        if self.board.is_checkmate():
            w = "Noirs" if self.board.turn == chess.WHITE else "Blancs"
            send_event("labo_info", {"type": "checkmate", "message": f"♚ Échec et mat — {w} gagnent"})
            self._auto_on = False
            return True
        if self.board.is_stalemate():
            send_event("labo_info", {"type": "stalemate", "message": "Pat — nulle"})
            self._auto_on = False
            return True
        if self.board.is_insufficient_material():
            send_event("labo_info", {"type": "draw", "message": "Matériel insuffisant"})
            self._auto_on = False
            return True
        if signal_check and self.board.is_check():
            c = "Blancs" if self.board.turn == chess.WHITE else "Noirs"
            send_event("labo_info", {"type": "check", "message": f"⚠ Échec aux {c} !"})
        return False

    # ── Actions ───────────────────────────────────────────────────────────

    def do_best_move(self) -> None:
        """Calcule et affiche le meilleur coup sur la position physique courante."""
        if self._engine_busy:
            return
        def _run():
            self._engine_busy = True
            try:
                # Utiliser le FEN physique courant pour être à jour
                raw  = self.nl_inst.current_fen
                phys = raw.strip().split()[0] if raw else ""
                if phys:
                    t = "w" if self.active_turn == "white" else "b"
                    try:
                        board_copy = chess.Board(f"{phys} {t} - - 0 1")
                    except Exception:
                        board_copy = self.board.copy()
                else:
                    board_copy = self.board.copy()
                eval_info  = self.engine.evaluate(board_copy, depth=18)
                bm = eval_info.get("best_move")
                if not bm:
                    return
                try:
                    best_san = san_ep(board_copy, chess.Move.from_uci(bm))
                except Exception:
                    best_san = bm
                self.nl_inst.set_move_leds(bm)
                send_event("labo_best_move", {
                    "uci":  bm,
                    "san":  best_san,
                    "cp":   eval_info.get("cp"),
                    "mate": eval_info.get("mate"),
                    "wdl":  self.engine.wdl_to_bar(eval_info.get("wdl")),
                })
            except Exception as e:
                logger.error(f"do_best_move : {e}")
            finally:
                self._engine_busy = False
        threading.Thread(target=_run, daemon=True).start()

    def do_engine_play(self) -> None:
        """Fait jouer le moteur un coup (Auto)."""
        if self._engine_busy or self.board.is_game_over():
            return
        def _run():
            self._engine_busy = True
            try:
                board_copy = self.board.copy()
                # Forcer le tour à engine_color avant de jouer
                if board_copy.turn != self.engine_color:
                    fen_parts = board_copy.fen().split()
                    fen_parts[1] = "b" if self.engine_color == chess.BLACK else "w"
                    board_copy = chess.Board(" ".join(fen_parts))
                    if DEBUG_MODE: print(f"[LABO] Tour forcé à {'noir' if self.engine_color == chess.BLACK else 'blanc'} pour le moteur")
                try:
                    move = self.engine.get_move(board_copy, think_time=1.0)
                except Exception as engine_err:
                    logger.warning(f"Moteur : position illégale ou incohérente — {engine_err}")
                    send_event("labo_info", {"type": "error",
                        "message": "⚠ Position incohérente — synchronisez le plateau"})
                    self._placement_in_progress = False
                    return
                if move is None:
                    return
                uci = move.uci()
                san = san_ep(self.board, move)
                self._placement_in_progress = True  # bloquer le watcher avant push
                self.board.push(move)
                self.active_turn = "white" if self.board.turn == chess.WHITE else "black"
                self._fen_history.append(self.board.fen())
                self.nl_inst.game_board = self.board.copy()
                self.nl_inst.set_move_leds(uci)
                engine_color = "black" if self.engine_color == chess.BLACK else "white"
                send_event("move", {
                    "fen": self._fen_short(), "san": san, "uci": uci,
                    "color": engine_color, "player": self.engine_label, "qualite": None,
                })
                send_event("labo_engine_played", {"san": san, "engine": self.engine_label})
                self._send_position(uci)
                self._wait_placement(uci)
                self._check_end(signal_check=False)  # échec signalé par le watcher
            except Exception as e:
                logger.error(f"do_engine_play : {e}")
            finally:
                self._engine_busy = False
        threading.Thread(target=_run, daemon=True).start()

    def do_analyse(self) -> None:
        """Évalue la position courante."""
        def _run():
            try:
                board_copy = self.board.copy()
                eval_info  = self.engine.evaluate(board_copy, depth=14)
                bm  = eval_info.get("best_move")
                wdl = self.engine.wdl_to_bar(eval_info.get("wdl"))
                best_san = None
                if bm:
                    try: best_san = san_ep(board_copy, chess.Move.from_uci(bm))
                    except Exception: best_san = bm
                    self.nl_inst.set_move_leds(bm)
                send_event("labo_analyse", {
                    "cp": eval_info.get("cp"), "mate": eval_info.get("mate"),
                    "best_move": bm, "best_san": best_san, "wdl": wdl,
                    "turn": "white" if board_copy.turn == chess.WHITE else "black",
                })
            except Exception as e:
                logger.error(f"do_analyse : {e}")
        threading.Thread(target=_run, daemon=True).start()


    def set_board_from_fen(self, fen: str) -> None:
        """Réinitialise le board depuis un FEN (après copie physique réussie)."""
        try:
            self.board = chess.Board(fen)
            self._fen_history = [fen]
            self.nl_inst.game_board = self.board.copy()
            self._send_position()
        except Exception as e:
            logger.error(f"set_board_from_fen : {e}")

    def sync_from_physical(self, turn: str = None) -> None:
        """Synchronise le board depuis le plateau physique. turn='white'|'black'."""
        if turn:
            self.active_turn = turn
        try:
            raw  = self.nl_inst.current_fen
            phys = raw.strip().split()[0] if raw else ""
            if phys:
                t = "w" if self.active_turn == "white" else "b"
                full_fen = f"{phys} {t} - - 0 1"
                self.board = chess.Board(full_fen)
                self._fen_history = [self.board.fen()]
                self.nl_inst.game_board = self.board.copy()
                self.nl_inst.turn_off_all_leds()
                self._send_position()
                send_event("labo_info", {"type": "sync", "message": "✓ Synchronisé avec le plateau physique"})
        except Exception as e:
            logger.error(f"sync_from_physical : {e}")

    # ── Attente placement moteur ──────────────────────────────────────────

    def _wait_placement(self, uci: str) -> None:
        # _placement_in_progress déjà True (activé dans do_engine_play avant board.push)
        expected  = self.board.board_fen()
        raw_init  = self.nl_inst.current_fen
        fen_avant = raw_init.strip().split()[0] if raw_init else ""
        last_bad  = None
        bad_since = None
        STABLE    = 0.8
        while self._running:
            # Si auto désactivé pendant l'attente → sortir proprement
            if not self._auto_on:
                self.nl_inst.turn_off_all_leds()
                self._placement_in_progress = False
                send_event("labo_placement_cancelled", {})
                return
            # Si le board a été resynchronisé depuis l'extérieur → annuler
            if self.board.board_fen() != expected:
                self.nl_inst.turn_off_all_leds()
                self._placement_in_progress = False
                return
            raw  = self.nl_inst.current_fen
            phys = raw.strip().split()[0] if raw else ""
            if phys == expected:
                self.nl_inst.turn_off_all_leds()
                self._placement_in_progress = False
                send_event("position_ok", {"fen": expected})
                return
            if phys == fen_avant:
                time.sleep(0.1)
                continue
            now = time.time()
            if phys != last_bad:
                last_bad  = phys
                bad_since = now
            elif phys and now - bad_since >= STABLE:
                send_event("position_error", {"expected_fen": expected, "physical_fen": phys})
            time.sleep(0.1)

    # ── Watcher plateau physique ──────────────────────────────────────────

    def board_watcher(self) -> None:
        """
        Suit le plateau physique en continu.
        Accepte les coups des deux camps (sauf en auto où le moteur joue lui-même).
        Gère aussi les positions libres (pièces déplacées sans suivre les règles).
        """
        STABLE_DELAY  = 0.4
        last_fen      = self.board.board_fen()
        candidate_fen = None
        candidate_t   = None

        while self._running:
            time.sleep(0.1)
            try:
                raw  = self.nl_inst.current_fen
                phys = raw.strip().split()[0] if raw else ""
            except Exception:
                continue

            if not phys or phys == last_fen:
                candidate_fen = None
                continue

            if phys != candidate_fen:
                candidate_fen = phys
                candidate_t   = time.time()
                continue

            if time.time() - candidate_t < STABLE_DELAY:
                continue

            # En auto, ignorer les coups du camp moteur
            if self._auto_on and self.board.turn == self.engine_color:
                candidate_fen = None
                continue

            if self._engine_busy or self._placement_in_progress:
                candidate_fen = None
                continue

            # Chercher un coup légal correspondant
            move_found = None
            for move in self.board.legal_moves:
                test = self.board.copy()
                test.push(move)
                if test.board_fen() == phys:
                    move_found = move
                    break

            if move_found is None:
                # Position libre — afficher sans changer le board interne
                # Éteindre les LEDs (peuvent rester d'un best_move)
                self.nl_inst.turn_off_all_leds()
                send_event("labo_free_position", {"fen": phys})
                last_fen      = phys
                candidate_fen = None
                continue

            # Coup légal
            uci   = move_found.uci()
            san   = san_ep(self.board, move_found)
            color = "white" if self.board.turn == chess.WHITE else "black"
            fen_avant = self.board.fen()

            self.board.push(move_found)
            # Mettre à jour active_turn pour refléter le nouveau tour
            self.active_turn = "white" if self.board.turn == chess.WHITE else "black"
            self._fen_history.append(self.board.fen())
            self.nl_inst.game_board = self.board.copy()
            last_fen      = phys
            candidate_fen = None

            send_event("move", {
                "fen": self._fen_short(), "san": san, "uci": uci,
                "color": color, "player": "Joueur", "qualite": None,
            })

            # Analyse qualité non bloquante
            if self.analyse_active:
                def _eval(fa=fen_avant, mv=move_found, s=san):
                    try:
                        board_av = chess.Board(fa)
                        qualite, delta, _ = self.engine.evaluate_move(board_av, mv, depth=8)
                        if qualite != "bon":
                            LABELS = {"imprecision":"?! Imprécision","erreur":"? Erreur","blunder":"?? Gaffe"}
                            send_event("labo_feedback", {
                                "qualite": qualite, "delta_cp": delta,
                                "san": s, "label": LABELS.get(qualite, qualite),
                            })
                    except Exception: pass
                threading.Thread(target=_eval, daemon=True).start()

            self._send_position(uci)
            self._check_end()

            # Auto : moteur joue après le coup humain
            if self._auto_on and self.board.turn == self.engine_color and not self._engine_busy:
                self.do_engine_play()

    def quit(self) -> None:
        self._running = False
        try: self.engine.quit()
        except Exception: pass
        try: self.nl_inst.turn_off_all_leds()
        except Exception: pass
