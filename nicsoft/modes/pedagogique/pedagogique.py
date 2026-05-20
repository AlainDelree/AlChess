"""
play_pedagogique/__main__.py — NicLink
Mode pédagogique : partie contre Stockfish avec feedback LED après chaque coup.

Feedback visuel après chaque coup humain :
  ✓  Bon coup     → LED destination allumée 1.5s
  ?  Imprécision  → LED destination clignote lentement (50cp-100cp)
  !  Erreur       → LED destination clignote rapidement (100cp-300cp)
  !! Blunder      → LEDs autour de la destination clignotent (>300cp)

En cas d'erreur/blunder (selon config "pedagogique_pause") :
  - Proposition de voir le meilleur coup (LEDs départ+arrivée)
  - Proposition de reprendre le coup

Historique affiché dans le terminal après chaque coup.
"""

import argparse
import datetime
import json
import logging
import os
import pathlib
from nicsoft.config import DATA_DIR, ENGINES_DIR
import random
import signal
import sys
import threading
import time

import chess
import chess.pgn
import numpy as np

from nicsoft.engine.engine_manager import EngineManager, find_stockfish, find_rodent
from nicsoft.utils.timing import tlog
from nicsoft.utils.debug import DEBUG_MODE
from nicsoft.engine.display import (
    display_move,
    display_turn,
    display_board_diff,
    check_tab_press,
)
from nicsoft.engine.pgn_manager import (
    build_tmp_path,
    ask_save_pgn,
    build_final_path,
    finalize_pgn,
    save_game,
)
from nicsoft.niclink import NicLinkManager
from nicsoft.engine.board_utils import wait_for_initial_position, san_ep

class BackMenuExit(Exception):
    """Levée pour sortir proprement vers le menu sans tuer le processus."""
    pass
from nicsoft.engine.players import load_players, save_players
from nicsoft.utils.backup_manager import run_backup
from nicsoft.utils.input_helpers import ask_int, parse_player_input
from nicsoft.web.server import send_event, get_action, start_server
from nicsoft.niclink.nl_exceptions import ExitNicLink
from nicsoft.engine.engine_manager import (
    classifier_coup as _classifier_coup,
    score_to_cp     as _score_to_cp,
    SEUIL_BON, SEUIL_IMPRECISION, SEUIL_ERREUR,
)

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

CONFIG_FILE = DATA_DIR / "config.json"
DEFAULT_CONFIG = {
    "stockfish_level": 5,
    "game_type": "Pedagogical",
    "turn_signal": "both",
    "pedagogique_pause": "blunder",  # toujours / erreur / blunder / jamais
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

import logging as _logging
logger_pre = _logging.getLogger("NL config")

logger = logging.getLogger("NL pedagogique")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(name)s - %(levelname)s | %(message)s"))
logger.addHandler(ch)

# ──────────────────────────────────────────────
# Seuils d'évaluation (centipawns de perte)
# ──────────────────────────────────────────────


SYMBOLES = {
    "bon":        "✓",
    "imprecision": "?",
    "erreur":     "!",
    "blunder":    "!!",
}

COULEURS_LABEL = {
    "bon":        "Bon coup",
    "imprecision": "Imprécision",
    "erreur":     "Erreur",
    "blunder":    "Blunder",
}

# ──────────────────────────────────────────────
# Helpers affichage
# ──────────────────────────────────────────────

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
        from nicsoft.engine.display import _piece_symbol, _piece_name_fr
        print()
        if missing_sq and extra_sq and missing_sq != extra_sq:
            sym_m = _piece_symbol(missing_piece)
            sym_e = _piece_symbol(extra_piece)
            print(f"⚠  Mauvaise case — {sym_e} {_piece_name_fr(extra_piece)} "
                  f"posé en {chess.square_name(extra_sq)} "
                  f"au lieu de {chess.square_name(missing_sq)}.")
            print(f"   Replacez le {sym_m} {_piece_name_fr(missing_piece)} "
                  f"en {chess.square_name(missing_sq)}.")
        elif missing_sq:
            sym = _piece_symbol(missing_piece)
            print(f"⚠  Pièce manquante — replacez {sym} "
                  f"{_piece_name_fr(missing_piece)} en {chess.square_name(missing_sq)}.")
        elif extra_sq:
            sym = _piece_symbol(extra_piece)
            print(f"⚠  Pièce en trop — retirez {sym} "
                  f"{_piece_name_fr(extra_piece)} de {chess.square_name(extra_sq)}.")
        if context == "fish" and fish_move:
            print(f"   Puis exécutez le coup : {fish_move}")
    else:
        display_board_diff(expected_board, actual_board)
        if context == "fish" and fish_move:
            print(f"   Une fois remis en ordre, exécutez le coup : {fish_move}")
        elif context == "human":
            print("   Une fois remis en ordre, jouez votre coup.")
    print()


# ──────────────────────────────────────────────
# LEDs feedback pédagogique
# ──────────────────────────────────────────────

def _led_bon_coup(nl_inst: NicLinkManager, dest_sq: int) -> None:
    """LED destination allumée 1.5 secondes."""
    sq_name = chess.square_name(dest_sq)
    try:
        nl_inst.set_led(sq_name, True)
        time.sleep(1.5)
        nl_inst.turn_off_all_leds()
    except Exception:
        pass


def _led_clignote(nl_inst: NicLinkManager, dest_sq: int,
                  nb_blinks: int, interval: float) -> None:
    """Fait clignoter la LED d'une case."""
    sq_name = chess.square_name(dest_sq)
    try:
        for _ in range(nb_blinks):
            nl_inst.set_led(sq_name, True)
            time.sleep(interval)
            nl_inst.turn_off_all_leds()
            time.sleep(interval)
    except Exception:
        pass


def _led_imprecision(nl_inst: NicLinkManager, dest_sq: int) -> None:
    """Clignote lentement — imprécision."""
    _led_clignote(nl_inst, dest_sq, nb_blinks=3, interval=0.4)


def _led_erreur(nl_inst: NicLinkManager, dest_sq: int) -> None:
    """Clignote rapidement — erreur."""
    _led_clignote(nl_inst, dest_sq, nb_blinks=5, interval=0.15)


def _led_blunder(nl_inst: NicLinkManager, dest_sq: int) -> None:
    """Cases autour de la destination clignotent — blunder."""
    dest_file = chess.square_file(dest_sq)
    dest_rank = chess.square_rank(dest_sq)
    # Cases adjacentes (8 directions)
    adjacent = []
    for df in [-1, 0, 1]:
        for dr in [-1, 0, 1]:
            if df == 0 and dr == 0:
                continue
            f, r = dest_file + df, dest_rank + dr
            if 0 <= f <= 7 and 0 <= r <= 7:
                adjacent.append(chess.square(f, r))

    try:
        zeros = "00000000"
        for _ in range(4):
            # Allumer les cases adjacentes
            led_map = np.copy(np.array(["00000000"] * 8, dtype=np.str_))
            for sq in adjacent:
                f = chess.square_file(sq)
                r = chess.square_rank(sq)
                row = list(led_map[r])
                row[f] = "1"
                led_map[r] = "".join(row)
            nl_inst.set_all_leds(led_map)
            time.sleep(0.2)
            nl_inst.turn_off_all_leds()
            time.sleep(0.2)
    except Exception:
        pass


def _led_meilleur_coup(nl_inst: NicLinkManager, best_move: str) -> None:
    """Allume les deux cases du meilleur coup."""
    try:
        nl_inst.set_move_leds(best_move)
        time.sleep(5.0)
        nl_inst.turn_off_all_leds()
    except Exception:
        pass


# ──────────────────────────────────────────────
# Classe Game pédagogique
# ──────────────────────────────────────────────

class Game(threading.Thread):
    """Partie pédagogique contre Stockfish ou Maia avec feedback LED."""

    def __init__(self, nl_inst, playing_white, stockfish_level=5,
                 default_game_type="Pedagogical", turn_signal="both",
                 pedagogique_pause="blunder", engine_elo=1500,
                 analyse_active=True, engine_path="", bip_active=False,
                 engine_type="stockfish", maia_elo=1500, rodent_elo=800,
                 rodent_simple=False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.nl_inst           = nl_inst
        self.playing_white     = playing_white
        self.default_game_type = default_game_type
        self.turn_signal       = turn_signal
        self.pedagogique_pause = pedagogique_pause
        self.stockfish_level   = stockfish_level
        self.engine_elo        = engine_elo
        self.analyse_active    = analyse_active
        self.bip_active        = bip_active
        self.engine_type       = engine_type

        if engine_type == "maia":
            from nicsoft.engine.engine_manager import MaiaEngine, find_lc0, find_maia_weights
            lc0_path     = find_lc0()
            weights_path = find_maia_weights(maia_elo)
            sf_path      = find_stockfish() or "stockfish"
            if not lc0_path:
                raise RuntimeError("lc0 introuvable — vérifiez l'installation dans ~/NicLink/engines/maia/")
            if not weights_path:
                raise RuntimeError(f"Poids Maia {maia_elo} introuvables dans ~/NicLink/engines/maia/")
            self.engine = MaiaEngine(
                lc0_path=lc0_path,
                weights_path=weights_path,
                maia_elo=maia_elo,
                stockfish_path=sf_path,
                analyse_active=analyse_active,
            )
            self.engine_elo = maia_elo

        elif engine_type == "rodent":
            rodent_path = find_rodent()
            if not rodent_path:
                raise RuntimeError(f"Rodent introuvable dans {ENGINES_DIR / 'rodent-iv'}")
            self.engine = EngineManager(
                rodent_path,
                engine_elo=rodent_elo,
                analyse_active=analyse_active,
            )
            # Appliquer la personnalité "Simple" sur le moteur de jeu uniquement
            if rodent_simple and self.engine._engine_play:
                try:
                    self.engine._engine_play.configure({"Personality": "Simple"})
                except Exception:
                    pass
            # Remplacer _engine_eval par Stockfish pour une analyse objective
            sf_path = find_stockfish() or "stockfish"
            try:
                import chess.engine as _ce
                sf_eval = _ce.SimpleEngine.popen_uci(sf_path)
                if "UCI_ShowWDL" in sf_eval.options:
                    sf_eval.configure({"UCI_ShowWDL": True})
                    self.engine._supports_wdl = True
                if self.engine._engine_eval:
                    try:
                        self.engine._engine_eval.quit()
                    except Exception:
                        pass
                self.engine._engine_eval = sf_eval
                logger.info("Rodent : analyse déléguée à Stockfish")
            except Exception as e:
                logger.warning(f"Impossible de lancer Stockfish pour analyse Rodent : {e}")
            self.engine_elo = rodent_elo

        else:
            # Stockfish (défaut)
            if not engine_path:
                engine_path = find_stockfish() or "stockfish"
            self.engine = EngineManager(
                engine_path,
                engine_elo=engine_elo,
                analyse_active=analyse_active,
            )

        self.game_over            = False
        self._last_best_move      = None
        self._abandon_demande     = False
        self._nulle_demandee      = False
        self._reprendre_demande   = False
        self._reprendre_disponible = False

        self._back_menu_demande   = False
        self._pause_demandee      = False
        self.move_gaps            = []
        self.last_move_time       = time.time()

        self._cancel_led_off = False  # True = annuler le turn_off_all_leds en attente

        # Pipeline : précalcul du coup moteur en parallèle de l'évaluation humaine
        self._prefetched_fish_move: chess.Move | None = None
        self._fish_gen: int = 0
        # Temps de réflexion du moteur — 0.3s suffit avec UCI_LimitStrength actif
        self._think_time: float = 0.3
 
        
        self.tmp_path  = build_tmp_path()
        self._pgn_game = chess.pgn.Game()
        self._pgn_node = self._pgn_game

        # Historique pédagogique : liste de (san, qualite)
        self._historique: list[tuple[str, str]] = []

    # ── PGN ───────────────────────────────────────────────────────────────

    def _update_pgn_headers(self, result: str = "*") -> None:
        player_name = getattr(self, "player_name", "Human")
        elo_label   = f"~{self.engine_elo}elo"
        self._pgn_game.headers["Event"]       = f'{player_name} vs {self.engine.engine_name} ({elo_label})'
        self._pgn_game.headers["Site"]        = "Chessnut Air"
        self._pgn_game.headers["Date"]        = datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        self._pgn_game.headers["White"]       = player_name if self.playing_white else self.engine.engine_name
        self._pgn_game.headers["Black"]       = self.engine.engine_name if self.playing_white else player_name
        self._pgn_game.headers["Result"]      = result
        self._pgn_game.headers["EngineElo"]   = str(self.engine_elo)

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

    # ── Fin de partie ─────────────────────────────────────────────────────

    def _end_game(self, result: str, reason: str = "", skip_save: bool = False) -> None:
        self._print_historique()
        self.save_pgn_tmp(result)
        self._shutdown_leds()
        self.game_over = True
        # Arrêter proprement le moteur
        try:
            self.engine.quit()
        except Exception:
            pass
        # Notifier le navigateur
        send_event("game_over", {"result": result, "reason": reason or "Fin de partie", "source": "niclink", "skip": skip_save})
        from nicsoft.web.server import set_app_state, _game_state
        # Reconstruire l'historique depuis _game_state["history"] — fiable même après chess.Board(fen)
        history = _game_state.get("history", [])
        _hist_board = chess.Board()
        _hist_fens  = [_hist_board.board_fen()]
        _hist_moves = []
        for m in history:
            try:
                mv = chess.Move.from_uci(m.get("uci", ""))
                if mv in _hist_board.legal_moves:
                    _hist_board.push(mv)
                    _hist_fens.append(_hist_board.board_fen())
                    _hist_moves.append({
                        "san":    m.get("san", ""),
                        "uci":    m.get("uci", ""),
                        "color":  m.get("color", "white"),
                        "qualite": m.get("qualite"),
                    })
            except Exception:
                continue
        reason_str = reason or "Fin de partie"
        # Titre adapté selon la raison
        if "checkmate" in reason_str.lower() or "mat" in reason_str.lower():
            title = "Échec et mat !"; title_key = "game.titre_mat"
        elif "stalemate" in reason_str.lower() or "pat" in reason_str.lower():
            title = "Pat !";           title_key = "game.titre_pat"
        else:
            title = "Partie terminée"; title_key = "game.fin_partie_default"
        if not skip_save:
            set_app_state("game_over", {
                "title":     title,
                "title_key": title_key,
                "result": f"{result} — {reason_str}",
                "source": "niclink",
                "skip": False,
                "history_fen":   _hist_fens,
                "history_moves": _hist_moves,
                "init":          _game_state.get("init", {}),
            })
        # Sortie immédiate sans attendre (retour menu, ou partie sans serveur web)
        if skip_save:
            finalize_pgn(self.tmp_path, False, None)
            raise BackMenuExit()
        # Attendre la décision de sauvegarde depuis le navigateur
        player_name = getattr(self, "player_name", "Human")
        white = player_name if self.playing_white else "Stockfish"
        black = "Stockfish" if self.playing_white else player_name
        while True:
            action = get_action(timeout=2.0)
            if action is None:
                continue
            atype = action.get("type", "")
            if atype == "save":
                raw_type  = action.get("save_type", "sf-pedagogique")
                save_mode = action.get("save_mode", "stockfish")
                mode_map  = {"humain": "Human", "stockfish": "Stockfish"}
                mode_dir  = mode_map.get(save_mode, "stockfish")
                game_type = raw_type.split("-", 1)[-1] if "-" in raw_type else raw_type
                final_path = build_final_path(
                    mode=mode_dir, game_type=game_type,
                    white=white, black=black
                )
                finalize_pgn(self.tmp_path, True, final_path)
                print(f"Partie sauvegardée : {final_path}")
                break
            elif atype == "no_save":
                finalize_pgn(self.tmp_path, False, None)
                print("Partie non sauvegardée.")
                break
            elif atype in ("back_menu", "abandonner"):
                finalize_pgn(self.tmp_path, False, None)
                break
        raise BackMenuExit()

    def check_for_game_over(self) -> None:
        over_state = self.nl_inst.is_game_over()
        if not over_state:
            return
        if over_state["winner"] is False:
            winner, result = "Nulle", "1/2-1/2"
            reason = over_state.get("reason", "Nulle")
        elif over_state["winner"]:
            winner, result = "Noirs", "0-1"
            reason = over_state.get("reason", "Fin de partie")
        else:
            winner, result = "Blancs", "1-0"
            reason = over_state.get("reason", "Fin de partie")
        print(f"\n  Fin de partie — {winner} gagnent ({reason})")
        # Envoyer une notification popup avant game_over
        from nicsoft.web.server import socketio as _sio
        try:
            if "checkmate" in reason.lower():
                _sio.emit("popup", {"message": "♚ Échec et mat !", "message_key": "server.popup.mat", "type": "gameover"})
            elif "stalemate" in reason.lower():
                _sio.emit("popup", {"message": "Pat !", "message_key": "server.popup.pat", "type": "gameover"})
        except Exception:
            pass
        self._end_game(result, reason)

    # ── Historique ────────────────────────────────────────────────────────

    def _print_historique(self) -> None:
        """Affiche l'historique des coups avec leur évaluation."""
        if not self._historique:
            return
        print()
        print("─" * 50)
        print("  Historique de la partie :")
        line = "  "
        for i, (san, qualite) in enumerate(self._historique):
            sym = SYMBOLES.get(qualite, "")
            entry = f"{i+1}.{san}{sym}  "
            if len(line) + len(entry) > 50:
                print(line)
                line = "  "
            line += entry
        if line.strip():
            print(line)
        print("─" * 50)
        print()

    def _print_historique_inline(self) -> None:
        """Affiche l'historique sur une ligne courte après chaque coup."""
        if not self._historique:
            return
        parts = []
        for i, (san, qualite) in enumerate(self._historique):
            sym = SYMBOLES.get(qualite, "")
            parts.append(f"{san}{sym}")
        print(f"  [{' '.join(parts)}]")

    # ── Signaux ───────────────────────────────────────────────────────────

    def _start_fish_prefetch(self, board: chess.Board | None = None) -> None:
        """
        Démarre le calcul du prochain coup moteur en background.
        Stocke l'Event dans self._fish_done_event pour que handle_fish_turn
        puisse attendre si besoin.
        Utilise _lock_play (indépendant de _lock_eval) → vraie parallélisation.
        """
        board = board or self.nl_inst.game_board.copy()
        self._fish_gen += 1
        _gen = self._fish_gen
        done = threading.Event()
        self._fish_done_event = done

        def _think():
            result = self.engine.get_move(board, think_time=self._think_time)
            if self._fish_gen == _gen:
                self._prefetched_fish_move = result
            done.set()

        threading.Thread(target=_think, daemon=True).start()

    def signal_turn(self) -> None:
        # Annuler turn_off_all_leds en attente (thread WAIT_FISH) avant d'allumer les LEDs
        self._cancel_led_off = True
        # Bip + LEDs camp humain — fire-and-forget via queue LED
        if self.bip_active:
            print("\a", end="", flush=True)
        try:
            sig = 3 if self.playing_white == chess.WHITE else 2
            self.nl_inst.signal_lights(sig)
        except Exception:
            pass

    def _shutdown_leds(self) -> None:
        try:
            self.nl_inst.turn_off_all_leds()
        except Exception:
            pass

    # ── Analyse et feedback ───────────────────────────────────────────────

    def _evaluer_coup(self, fen_avant: str, move: chess.Move) -> tuple[str, int, str | None]:
        """
        Évalue la qualité d'un coup humain via EngineManager.
        Retourne (qualite, delta_cp, best_move_uci)
        """
        if not self.analyse_active:
            return "bon", 0, None
        board_avant = chess.Board(fen_avant)
        return self.engine.evaluate_move(board_avant, move, depth=8)

    def _feedback_led(self, qualite: str, move: chess.Move) -> None:
        """Feedback sonore uniquement selon la qualité du coup."""
        if qualite != "bon":
            try:
                self.nl_inst.beep()
            except Exception:
                pass

    def _doit_pause(self, qualite: str) -> bool:
        """Détermine si on doit faire une pause interactive."""
        p = self.pedagogique_pause
        if p == "toujours":
            return True
        if p == "imprecision":
            return qualite in ("imprecision", "erreur", "blunder")
        if p == "erreur":
            return qualite in ("erreur", "blunder")
        if p == "blunder":
            return qualite == "blunder"
        return False  # jamais

    def _menu_feedback(self, qualite: str, delta_cp: int,
                       best_move: str | None, san: str) -> bool:
        """
        Menu bloquant : attend une action web OU clavier, sans timeout.
        Retourne True si le joueur veut reprendre le coup.
        """
        label = COULEURS_LABEL.get(qualite, qualite)
        sym   = SYMBOLES.get(qualite, "")
        print()
        print(f"  {sym} {label} — {san}  ({delta_cp}cp de perte)")
        if qualite == "bon":
            return False
        print("  Que voulez-vous faire ? [web ou 1/2/3]")
        print("  1. Voir le meilleur coup  2. Reprendre  3. Continuer")

        def _get_best_san():
            try:
                tmp = chess.Board(self._fen_avant_coup)
                return san_ep(tmp, chess.Move.from_uci(best_move))
            except Exception:
                return best_move

        while True:
            # Vérifier action web
            web_action = get_action(timeout=0.5)
            if web_action:
                atype = web_action.get("type", "")
                if atype == "reprendre":
                    return True
                elif atype == "meilleur" and best_move:
                    best_san = _get_best_san()
                    print(f"  Meilleur coup : {best_san}")
                    _led_meilleur_coup(self.nl_inst, best_move)
                    send_event("best_move", {"uci": best_move, "san": best_san})
                    # Attendre reprendre ou continuer
                    while True:
                        a2 = get_action(timeout=0.5)
                        if a2:
                            return a2.get("type") == "reprendre"
                        # clavier
                        import select
                        r, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if r:
                            c = sys.stdin.readline().strip()
                            return c == "1"
                elif atype == "continuer":
                    return False
                continue
            # Vérifier clavier (non-bloquant)
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0.0)
            if r:
                try:
                    choice = sys.stdin.readline().strip()
                except Exception:
                    return False
                if choice == "1" and best_move:
                    best_san = _get_best_san()
                    print(f"  Meilleur coup : {best_san}")
                    _led_meilleur_coup(self.nl_inst, best_move)
                    send_event("best_move", {"uci": best_move, "san": best_san})
                    print("  1. Reprendre  2. Continuer")
                    while True:
                        a2 = get_action(timeout=0.5)
                        if a2:
                            return a2.get("type") == "reprendre"
                        r2, _, _ = select.select([sys.stdin], [], [], 0.0)
                        if r2:
                            return sys.stdin.readline().strip() == "1"
                elif choice == "2":
                    return True
                else:
                    return False

    def _menu_feedback_non_bloquant(self, qualite: str, delta_cp: int,
                                     best_move: str | None, san: str) -> bool:
        """
        Version non-bloquante : attend une action du navigateur OU une touche clavier
        pendant 15 secondes. Si rien, continue.
        Retourne True si le joueur veut reprendre.
        """
        label = COULEURS_LABEL.get(qualite, qualite)
        sym   = SYMBOLES.get(qualite, "")

        print(f"  {sym} {label} ({delta_cp}cp)" if qualite != "bon" else "  ✓ Bon coup")
        import select, tty, termios
        fd = sys.stdin.fileno()
        old_attr = termios.tcgetattr(fd)
        result = False
        try:
            tty.setraw(fd)
            for i in range(15, 0, -1):
                pass  # countdown géré par le navigateur
                # Vérifier d'abord une action web (non-bloquant)
                web_action = get_action(timeout=0.0)
                if web_action:
                    atype = web_action.get("type", "")
                    print()
                    if atype == "reprendre":
                        result = True
                        break
                    elif atype == "meilleur" and best_move:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
                        try:
                            tmp = chess.Board(self._fen_avant_coup)
                            best_san = san_ep(tmp, chess.Move.from_uci(best_move))
                        except Exception:
                            best_san = best_move
                        print(f"\n  Meilleur coup : {best_san}")
                        _led_meilleur_coup(self.nl_inst, best_move)
                        send_event("best_move", {"uci": best_move, "san": best_san})
                        break
                    elif atype == "continuer":
                        break
                # Puis vérifier clavier (1 seconde)
                r, _, _ = select.select([sys.stdin], [], [], 1.0)
                if r:
                    ch = sys.stdin.read(1).lower()
                    print()
                    if ch == 'r':
                        result = True
                        break
                    elif ch == 'm' and best_move:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
                        try:
                            tmp = chess.Board(self._fen_avant_coup)
                            best_san = san_ep(tmp, chess.Move.from_uci(best_move))
                        except Exception:
                            best_san = best_move
                        print(f"\n  Meilleur coup : {best_san}")
                        _led_meilleur_coup(self.nl_inst, best_move)
                        send_event("best_move", {"uci": best_move, "san": best_san})
                        break
                    elif ch == 'q':
                        break
            print()
        except Exception:
            pass
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
            except Exception:
                pass
        return result
    # ── Abandon ───────────────────────────────────────────────────────────

    def _check_web_abandon(self) -> None:
        """Vérifie si une action web a été demandée depuis le navigateur."""
        action = get_action(timeout=0.0)
        if not action:
            return
        atype = action.get("type")
        if atype == "abandonner":
            self._abandon_demande = True
            self.nl_inst.kill_switch.set()
        elif atype == "nulle":
            self._nulle_demandee = True
            self.nl_inst.kill_switch.set()
        elif atype == "back_menu":
            self._back_menu_demande = True
            self._abandon_demande = True
            self.nl_inst.kill_switch.set()
        elif atype == "set_pause":
            val = action.get("value", "blunder")
            self.pedagogique_pause = val
            if DEBUG_MODE: print(f"[WEB] Pause pédagogique changée : {val}")
        elif atype == "pause":
            self._pause_demandee = True
    def _traiter_nulle(self, board=None) -> None:
        """Traite une proposition de nulle depuis l'interface web."""
        human_color = chess.WHITE if self.playing_white == chess.WHITE else chess.BLACK
        try:
            board_courant = board if board is not None else chess.Board(self.nl_inst.get_game_fen())
            eval_info = self.engine.evaluate(board_courant, depth=10)
            cp   = eval_info["cp"]
            mate = eval_info["mate"]
            sf_color = not human_color
            if mate is not None:
                sf_winning = (mate > 0 and board_courant.turn == sf_color) or \
                             (mate < 0 and board_courant.turn != sf_color)
                accepts = not sf_winning
            elif cp is not None:
                sf_cp = cp if board_courant.turn == sf_color else -cp
                accepts = sf_cp <= 150
            else:
                accepts = False
            if accepts:
                print("  Stockfish accepte la nulle.")
                self._end_game("1/2-1/2", "Nulle acceptée")
            else:
                print("  Stockfish refuse la nulle — la partie continue.")
                send_event("nulle_refusee", {
                    "reason": "Stockfish estime avoir l'avantage.",
                    "reason_key": "toast.nulle_refusee_default",
                })
        except Exception as e:
            logger.error(f"Erreur évaluation nulle: {e}")
            send_event("nulle_refusee", {
                "reason": "Impossible d'évaluer la position.",
                "reason_key": "toast.nulle_refusee_eval",
            })
    def _traiter_abandon(self) -> None:
        """Traite un abandon confirmé (appeler depuis le thread principal)."""
        human_color = chess.WHITE if self.playing_white == chess.WHITE else chess.BLACK
        result = "0-1" if human_color == chess.WHITE else "1-0"
        player = getattr(self, "player_name", "Joueur")
        print(f"\n  {player} abandonne via interface web.")
        # back_menu = sortie immédiate sans proposer sauvegarde
        skip = getattr(self, "_back_menu_demande", False)
        self._back_menu_demande = False
        self._end_game(result, "Abandon", skip_save=skip)

    # ── Pause ─────────────────────────────────────────────────────────────

    def handle_pause(self, qualite: str = None, delta_cp: int = None,
                      best_move: str = None, san: str = None,
                      punishment_line: list = None) -> tuple:
        """
        Gère la pause interactive — manuelle ou automatique (après blunder/erreur).
        Retourne (changer_couleur: bool, reprendre: bool).
        """
        from nicsoft.web.server import set_app_state, _game_state

        auto = qualite is not None
        if DEBUG_MODE: print(f"\n  [PAUSE] Partie suspendue {'(auto: ' + qualite + ')' if auto else '(manuelle)'}.")
        self.nl_inst.turn_off_all_leds()

        bm = best_move or getattr(self, "_last_best_move", None)

        set_app_state("paused", {
            "history_fen":   _game_state.get("history_fen", []),
            "history_moves": _game_state.get("history", []),
        })
        send_event("pause", {
            "playing_white":   self.playing_white,
            "player":          getattr(self, "player_name", "Joueur"),
            "level":           self.stockfish_level,
            "best_move":       bm,
            "auto":            auto,
            "qualite":         qualite,
            "delta_cp":        delta_cp,
            "san":             san,
            "punishment_line": punishment_line or [],
            "fen_avant_coup":  getattr(self, "_fen_avant_coup", None),
        })

        changer_couleur  = False
        reprendre        = False
        target_fen       = None

        # Boucle d'attente : navigation review ou reprendre/changer_couleur
        while True:
            action = get_action(timeout=1.0)
            if action is None:
                continue
            atype = action.get("type", "")

            if atype == "reprendre":
                changer_couleur = action.get("changer_couleur", False)
                target_fen      = action.get("fen", None)
                reprendre       = True
                if DEBUG_MODE: print(f"  [PAUSE] Reprendre le coup — changer_couleur={changer_couleur}")
                break

            elif atype == "continuer":
                # Pause auto : accepter le coup, continuer la partie
                if DEBUG_MODE: print("  [PAUSE] Continuer — coup accepté.")
                break

            elif atype == "resume_pause":
                # Pause manuelle : reprendre la partie sans rien changer
                if DEBUG_MODE: print("  [PAUSE] Reprendre la partie.")
                break

            elif atype == "meilleur":
                if bm:
                    try:
                        tmp = chess.Board(self.nl_inst.game_board.fen())
                        best_san = san_ep(tmp, chess.Move.from_uci(bm))
                    except Exception:
                        best_san = bm
                    if DEBUG_MODE: print(f"  [PAUSE] Meilleur coup : {best_san}")
                    _led_meilleur_coup(self.nl_inst, bm)
                    send_event("best_move", {"uci": bm, "san": best_san})
                continue

            elif atype == "abandonner":
                self._abandon_demande = True
                self._traiter_abandon()
                return False

            elif atype == "back_menu":
                self._back_menu_demande = True
                self._abandon_demande = True
                self._traiter_abandon()
                return False

            elif atype == "set_pause":
                val = action.get("value", "blunder")
                self.pedagogique_pause = val

            # review_prev / review_next / changer_couleur : gérés côté JS uniquement

        # ── Appliquer le FEN cible (tronquer l'historique si navigation arrière) ──
        if target_fen and target_fen != self.nl_inst.game_board.board_fen():
            # Chercher dans l'historique quel demi-coup correspond à ce FEN
            board_tmp = chess.Board()
            move_stack = list(self.nl_inst.game_board.move_stack)
            target_idx = None
            fens_seen = [board_tmp.board_fen()]
            for i, mv in enumerate(move_stack):
                board_tmp.push(mv)
                fens_seen.append(board_tmp.board_fen())
            if target_fen in fens_seen:
                target_idx = fens_seen.index(target_fen)
            if target_idx is not None:
                # Reconstruire le board jusqu'au coup target_idx
                self.nl_inst.game_board = chess.Board()
                for mv in move_stack[:target_idx]:
                    self.nl_inst.game_board.push(mv)
                if DEBUG_MODE: print(f"  [PAUSE] Historique tronqué au coup {target_idx}.")
            else:
                if DEBUG_MODE: print("  [PAUSE] FEN cible introuvable dans l'historique, reprise depuis position courante.")

        # ── Vérifier que le plateau physique correspond à la position cible ──
        expected_fen = self.nl_inst.game_board.board_fen()
        current_raw  = self.nl_inst.current_fen
        current_fen  = current_raw.strip().split()[0] if current_raw else ""

        if current_fen != expected_fen:
            if DEBUG_MODE: print("  [PAUSE] Position incorrecte — attendu :", expected_fen)
            from nicsoft.web.server import action_queue as _aq
            while not _aq.empty():
                try: _aq.get_nowait()
                except Exception: break
            send_event("pause_wait_position", {
                "fen":          expected_fen,
                "physical_fen": current_fen,
                "message":      "Reproduisez la position sur l'échiquier pour reprendre.",
            })
            while True:
                if self.nl_inst.kill_switch.is_set():
                    return False, False
                raw = self.nl_inst.current_fen
                phys = raw.strip().split()[0] if raw else ""
                if phys == expected_fen:
                    break
                # Envoyer les erreurs en temps réel
                if phys != expected_fen:
                    send_event("position_error", {
                        "expected_fen": expected_fen,
                        "physical_fen": phys,
                    })
                time.sleep(0.2)
            send_event("position_ok", {"fen": expected_fen})
            print("  Position rétablie. Reprise de la partie.")

        # playing_white sera inverti par run() si changer_couleur=True
        # reprendre=True uniquement si pause auto et joueur veut rejouer
        # On calcule le nouveau playing_white pour envoyer le bon turn
        new_playing_white = (not self.playing_white) if changer_couleur else self.playing_white
        board_turn_white  = self.nl_inst.game_board.turn == chess.WHITE
        player            = getattr(self, "player_name", "Joueur")

        # ── Utiliser _game_state["history"] comme source de vérité ──
        # (move_stack peut être vide si game_board reconstruit depuis FEN)
        from nicsoft.web.server import _game_state
        resume_moves = list(_game_state.get("history", []))
        resume_fens  = list(_game_state.get("history_fen", ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"]))

        if changer_couleur:
            new_human_color = "black" if self.playing_white else "white"
            send_event("swap_color", {
                "player":   player,
                "color":    new_human_color,
                "level":    self.stockfish_level,
            })

        set_app_state("playing")
        # N'envoyer "resume" que si l'historique a été tronqué (navigation arrière)
        # ou si couleur changée — pas si reprendre=True (undo_move s'en charge)
        if (target_fen or changer_couleur) and not reprendre:
            send_event("resume", {
                "history_fen":   resume_fens,
                "history_moves": resume_moves,
            })
        return changer_couleur, reprendre

    # ── Tour humain ───────────────────────────────────────────────────────

    def _do_reprendre_undo(self) -> bool:
        """
        Annule 2 demi-coups (coup moteur + coup humain), ou 1 si début de partie.
        Attend que le joueur remette les pièces à leur place en envoyant des
        position_error au navigateur. Retourne True pour signaler de rejouer.
        """
        if not self._pgn_node.parent:
            return False
        if self._pgn_node.parent.parent is not None:
            self._pgn_node = self._pgn_node.parent.parent
            count = 2
        else:
            self._pgn_node = self._pgn_node.parent
            count = 1
        self.nl_inst.game_board = self._pgn_node.board()
        for _ in range(count):
            if self._historique: self._historique.pop()
            if self.move_gaps:   self.move_gaps.pop()
        fen_cible = self.nl_inst.game_board.fen()
        expected  = self.nl_inst.game_board.board_fen()
        n_txt = "coups" if count == 2 else "coup"
        print(f"  {count} {n_txt} annulé(s) — remettez les pièces en place.")
        send_event("undo_move", {
            "fen":      fen_cible.split()[0],
            "full_fen": fen_cible,
            "count":    count,
            "message":  "Remettez les pièces à leur place, puis rejouez.",
            "message_key": "game.undo_remettez_pieces",
        })
        phys_now = (self.nl_inst.current_fen or "").strip().split()[0]
        if phys_now and phys_now != expected:
            send_event("position_error", {"expected_fen": expected, "physical_fen": phys_now})
        while True:
            if self.nl_inst.kill_switch.is_set():
                return False
            raw  = self.nl_inst.current_fen
            phys = raw.strip().split()[0] if raw else ""
            if phys == expected:
                send_event("position_ok", {"fen": expected})
                print("  Position rétablie — rejouez.")
                break
            send_event("position_error", {"expected_fen": expected, "physical_fen": phys})
            time.sleep(0.2)
        return True

    def handle_human_turn(self) -> bool:
        """
        Gère le tour du joueur humain avec analyse du coup.
        Retourne True si le joueur veut reprendre son coup (retour arrière).
        """
        # Si reprendre demandé depuis le tour précédent (mode libre)
        if self._reprendre_disponible:
            self._reprendre_disponible = False
            action = get_action(timeout=0.0)
            if action and action.get("type") == "reprendre":
                return self._do_reprendre_undo()

        human_color = "white" if self.playing_white == chess.WHITE else "black"
        display_turn(getattr(self, "player_name", "Joueur"), human_color)
        # Détecter si le roi est en échec
        _in_check = self.nl_inst.game_board.is_check()
        send_event("turn", {
            "color":    human_color,
            "player":   getattr(self, "player_name", "Joueur"),
            "is_human": True,
            "in_check": _in_check,
        })
        tlog("[TURN] send_event turn envoyé")
        # Nulle cliquée pendant WAIT_FISH : traiter immédiatement sans attendre un coup
        if self._nulle_demandee:
            self._nulle_demandee = False
            self._traiter_nulle()
            return False
        # Signal de tour — fire-and-forget via queue LED dans driver.
        # Retour immédiat, l'USB est géré dans le thread led_worker.
        self.signal_turn()

        watch_stop = threading.Event()

        def watch_board():
            # Délai avant signalement "coup illégal" :
            # - 1 case différente (pièce levée, pas encore reposée) → 2s de patience
            # - 2+ cases différentes (pièce reposée illégalement)   → 0.8s
            STABLE_DELAY_LIFTED = 2.0   # pièce en l'air
            STABLE_DELAY_PLACED = 0.8   # pièce posée illégalement
            expected_fen = self.nl_inst.game_board.board_fen()
            bad_fen_since = None
            last_bad_fen  = None
            warning_shown = False
            last_tmp_board  = None
            last_diff_count = 0
            time.sleep(0.05)

            while not watch_stop.is_set():
                board_fen = self.nl_inst.current_fen
                if not board_fen:
                    time.sleep(0.05)
                    continue
                board_fen = board_fen.strip().split()[0]

                if board_fen == expected_fen:
                    if warning_shown:
                        print("\n   Position rétablie — c'est à vous de jouer.")
                        send_event("turn", {
                            "color":    "white" if self.playing_white == chess.WHITE else "black",
                            "player":   getattr(self, "player_name", "Joueur"),
                            "is_human": True,
                            "in_check": self.nl_inst.game_board.is_check(),
                        })
                    bad_fen_since = None; last_bad_fen = None
                    warning_shown = False; last_tmp_board = None; last_diff_count = 0
                    time.sleep(0.1)
                    continue

                try:
                    tmp_board  = chess.Board(board_fen + " w - - 0 1")
                    diff_count = sum(1 for sq in chess.SQUARES
                                     if self.nl_inst.game_board.piece_at(sq) != tmp_board.piece_at(sq))
                except Exception:
                    time.sleep(0.1)
                    continue

                # Vérifier si ce FEN correspond à un coup légal en cours
                # (pièce soulevée puis reposée sur une case légale).
                # NE PAS bypasser si diff_count <= 2 sans vérification :
                # un cavalier cloué déplacé donne exactement diff_count=2
                # mais n'est PAS dans legal_moves → doit être signalé.
                _is_legal_move = False
                for _m in self.nl_inst.game_board.legal_moves:
                    _tb = self.nl_inst.game_board.copy()
                    _tb.push(_m)
                    if _tb.board_fen() == board_fen:
                        _is_legal_move = True
                        break
                if _is_legal_move:
                    bad_fen_since = None; last_bad_fen = None
                    warning_shown = False; last_diff_count = 0
                    time.sleep(0.1)
                    continue

                # Délai adaptatif selon la situation
                stable_delay = STABLE_DELAY_LIFTED if diff_count == 1 else STABLE_DELAY_PLACED

                now = time.time()
                if board_fen != last_bad_fen:
                    bad_fen_since = now; last_bad_fen = board_fen
                    last_tmp_board = tmp_board; last_diff_count = diff_count
                    warning_shown = False
                elif now - bad_fen_since >= stable_delay and not warning_shown:
                    warning_shown = True
                    last_tmp_board = tmp_board; last_diff_count = diff_count
                    _display_position_error(self.nl_inst.game_board, tmp_board,
                                            diff_count, context="human")
                    # Message adapté + 2 bips
                    try:
                        from nicsoft.engine.board_utils import analyser_position_illegale
                        msg = analyser_position_illegale(self.nl_inst.game_board, board_fen)
                    except Exception:
                        msg = "⚠ Coup illégal — remettez la pièce à sa place."
                    try:
                        self.nl_inst.beep()
                        time.sleep(0.15)
                        self.nl_inst.beep()
                    except Exception:
                        pass
                    send_event("illegal_position", {"message": msg})

                if check_tab_press() and warning_shown and last_tmp_board:
                    _display_position_error(self.nl_inst.game_board, last_tmp_board,
                                            last_diff_count, context="human")
                time.sleep(0.1)


        self._abandon_demande = False
        abandon_stop = threading.Event()

        def poll_abandon():
            while not abandon_stop.is_set():
                try:
                    action = get_action(timeout=0.05)
                    if action:
                        atype = action.get("type")
                        if atype == "abandonner":
                            self._abandon_demande = True
                            self.nl_inst.kill_switch.set()
                            return
                        elif atype == "nulle":
                            self._nulle_demandee = True
                            self.nl_inst.kill_switch.set()
                            return
                        elif atype in ("back_menu",):
                            self._back_menu_demande = True
                            self._abandon_demande = True
                            self.nl_inst.kill_switch.set()
                            return
                        elif atype == "reprendre":
                            self._reprendre_demande = True
                            self.nl_inst.kill_switch.set()
                            return
                        elif atype == "pause":
                            self._pause_demandee = True
                            self.nl_inst.kill_switch.set()
                            return
                        elif atype == "set_pause":
                            val = action.get("value", "blunder")
                            self.pedagogique_pause = val
                            print(f"[WEB] Pause pédagogique changée : {val}")
                        else:
                            from nicsoft.web.server import action_queue
                            action_queue.put(action)
                except Exception:
                    pass

        abandon_watcher = threading.Thread(target=poll_abandon, daemon=True)
        abandon_watcher.start()
        watcher = threading.Thread(target=watch_board, daemon=True)
        watcher.start()

        # Synchroniser game_board avec le FEN complet (inclut ep_square pour prise en passant)
        self.nl_inst.game_board = chess.Board(self.nl_inst.game_board.fen())

        # Mémoriser le FEN avant le coup pour l'évaluation
        fen_avant = self.nl_inst.game_board.fen()

        move = None
        _t_await = time.time()
        try:
            move = self.nl_inst.await_move()
            # Annuler le signal de tour dès que le coup est joué
            self.nl_inst.turn_off_all_leds()
            print("[TIMING] await_move: %.2fs — move=%s" % (time.time()-_t_await, move), flush=True)
            tlog("[TIMING] await_move: %.2fs — move=%s", time.time()-_t_await, move)
        except KeyboardInterrupt:
            watch_stop.set()
            self._shutdown_leds()
            print("\nBye!")
            sys.exit(0)
        except ExitNicLink:
            pass  # géré dans le finally + les if après
        except Exception as e:
            if self._abandon_demande or self._nulle_demandee or self._reprendre_demande:
                pass
            else:
                err_msg = str(e).lower()
                if any(k in err_msg for k in ("usb", "serial", "device", "timeout", "fen", "connection")):
                    print("\n⚠  Échiquier déconnecté ou éteint.")
                    print("   Vérifiez l'USB et rallumez le plateau, puis relancez le programme.")
                    send_event("board_error", {"message": "Échiquier déconnecté ou éteint. Relancez le programme.", "message_key": "error.board.deconnecte"})
                    sys.exit(1)
                raise
        finally:
            abandon_stop.set()
            watch_stop.set()
            self.nl_inst.kill_switch.clear()
            watcher.join(timeout=1.0)
            abandon_watcher.join(timeout=1.0)
        if self._abandon_demande:
            self._traiter_abandon()
            return False
        if self._nulle_demandee:
            self._nulle_demandee = False
            self._traiter_nulle()
            return False
        if self._pause_demandee:
            self._pause_demandee = False
            changer_couleur, reprendre_pause = self.handle_pause()
            if changer_couleur:
                self.playing_white = not self.playing_white
            if reprendre_pause:
                self._reprendre_demande = True  # propager vers le handler reprendre ci-dessous
            else:
                return False
        if self._reprendre_demande:
            self._reprendre_demande = False
            return self._do_reprendre_undo()
        if move is None:
            return False

        move_obj = chess.Move.from_uci(move)
        san = san_ep(self.nl_inst.game_board, move_obj)

        self.nl_inst.last_move = None  # pas de LEDs coup humain en pédagogique
        self.nl_inst.make_move_game_board(move)
        display_move(getattr(self, "player_name", "Joueur"), human_color, san)
        # On envoie d'abord le move, la qualite sera mise à jour après évaluation
        _full_fen = self.nl_inst.game_board.fen()
        _move_event = {
            "fen":      _full_fen.split()[0],
            "full_fen": _full_fen,
            "san":    san,
            "uci":    move,
            "color":  "white" if self.playing_white == chess.WHITE else "black",
            "player": getattr(self, "player_name", "Joueur"),
            "qualite": None,  # sera mis à jour après évaluation
        }
        send_event("move", _move_event)

        # Pipeline : démarrer le calcul du coup moteur en parallèle de l'évaluation
        # _lock_play et _lock_eval sont indépendants → exécution vraiment concurrente
        self._start_fish_prefetch(self.nl_inst.game_board.copy())

        now = time.time()
        gap = round(now - getattr(self, "last_move_time", now), 2)
        self.move_gaps.append(gap)
        self.last_move_time = now

        # ── Évaluation du coup ────────────────────────────────────────────
        self._fen_avant_coup = fen_avant
        _t_eval = time.time()
        qualite, delta_cp, best_move = self._evaluer_coup(fen_avant, move_obj)
        self._last_best_move = best_move  # disponible pour la pause
        tlog("[TIMING] evaluer_coup: %.2fs — %s %dcp", time.time()-_t_eval, qualite, delta_cp)

        # WDL après le coup humain
        wdl_bar = None
        if self.analyse_active:
            _t_wdl = time.time()
            eval_info = self.engine.evaluate(self.nl_inst.game_board.copy(), depth=8)
            wdl_bar   = self.engine.wdl_to_bar(eval_info.get("wdl"))
            tlog("[TIMING] wdl_humain: %.2fs", time.time()-_t_wdl)

        send_event("qualite", {"san": san, "qualite": qualite, "delta_cp": delta_cp, "wdl": wdl_bar})

        # Feedback : bip si le coup déclenche une pause selon config
        if self._doit_pause(qualite):
            try:
                self.nl_inst.beep()
            except Exception:
                pass

        # Toujours informer le navigateur (pour activer btn-reprendre et afficher qualité)
        # Calculer la séquence punitive si blunder/erreur
        punishment_line = []
        if self._doit_pause(qualite) and self.analyse_active:
            try:
                board_avant = chess.Board(self._fen_avant_coup)
                punishment_line = self.engine.get_punishment_line(
                    board_avant, move_obj, depth=12, max_moves=3
                )
                tlog("[SEQUENCE] punishment_line calculée: %s", punishment_line)
            except Exception as e:
                tlog("[SEQUENCE] erreur: %s", e)

        send_event("feedback", {
            "qualite":         qualite,
            "delta_cp":        delta_cp,
            "san":             san,
            "best_move_uci":   best_move,
            "best_move_san":   None,
            "pause_mode":      "bloquant" if self._doit_pause(qualite) else "libre",
            "punishment_line": punishment_line,
            "fen_avant_coup":  self._fen_avant_coup,
        })

        # Pause auto si configuré — handle_pause devient le point d'entrée unique
        reprendre = False
        if self._doit_pause(qualite):
            _, reprendre = self.handle_pause(
                qualite=qualite, delta_cp=delta_cp,
                best_move=best_move, san=san,
                punishment_line=punishment_line,
            )
        # Sinon : le jeu continue immédiatement
        else:
            self._reprendre_disponible = True

        if reprendre:
            # Annuler le coup et recommencer ce tour.
            # _pgn_node n'a pas encore été avancé (_append_move_to_pgn est après) :
            # on ne le recule donc pas.
            # Invalider le coup moteur précalculé (position a changé).
            self._fish_gen += 1
            self._prefetched_fish_move = None
            self.nl_inst.game_board.pop()
            if self._historique: self._historique.pop()
            if self.move_gaps:   self.move_gaps.pop()
            fen_cible = self.nl_inst.game_board.fen()
            expected  = self.nl_inst.game_board.board_fen()
            print("  Coup annulé — remettez la pièce à sa position initiale.")
            send_event("undo_move", {
                "fen":      fen_cible.split()[0],
                "full_fen": fen_cible,
                "count":    1,
                "message":  "Remettez la pièce à sa position initiale, puis rejouez.",
            "message_key": "game.undo_remettez_piece",
            })
            phys_now = (self.nl_inst.current_fen or "").strip().split()[0]
            if phys_now and phys_now != expected:
                send_event("position_error", {"expected_fen": expected, "physical_fen": phys_now})
            while True:
                if self.nl_inst.kill_switch.is_set():
                    return False
                raw  = self.nl_inst.current_fen
                phys = raw.strip().split()[0] if raw else ""
                if phys == expected:
                    send_event("position_ok", {"fen": expected})
                    print("  Position rétablie — rejouez.")
                    break
                send_event("position_error", {"expected_fen": expected, "physical_fen": phys})
                time.sleep(0.2)
            return True  # signal : refaire le tour

        self._append_move_to_pgn(move_obj, comment=f"{SYMBOLES.get(qualite,'')} {delta_cp}cp gap={gap}s")
        self.save_pgn_tmp()
        self.check_for_game_over()
        return False

    def handle_fish_turn(self) -> None:
        """Gère le tour du moteur."""
        engine_color = "black" if self.playing_white == chess.WHITE else "white"
        engine_label = self.engine.engine_name
        self._check_web_abandon()
        if self._abandon_demande:
            self._traiter_abandon()
            return
        # kill_switch peut être actif pour nulle/pause arrivés entre les tours :
        # on le réinitialise ici pour ne pas polluer WAIT_FISH.
        self.nl_inst.kill_switch.clear()
        if self._pause_demandee:
            self._pause_demandee = False
            changer_couleur, _ = self.handle_pause()
            if changer_couleur:
                self.playing_white = not self.playing_white
            return
        display_turn(engine_label, engine_color)
        send_event("turn", {"color": engine_color, "player": engine_label, "is_human": False})
        # Maintenir Abandonner + Nulle actifs pendant toute la durée du tour moteur
        send_event("abandon_nulle_ok", {})

        # Utiliser le coup précalculé (pipeline) ou calculer maintenant.
        # Si le prefetch tourne encore (cas rare : eval très rapide + think_time long),
        # _fish_done_event permet d'attendre sans boucle active.
        _t_fish = time.time()
        if self._prefetched_fish_move is None and hasattr(self, '_fish_done_event'):
            self._fish_done_event.wait(timeout=2.0)
        if self._prefetched_fish_move is not None:
            fish_move_obj = self._prefetched_fish_move
            self._prefetched_fish_move = None
            print("[TIMING] get_move: préchargé (%.3fs attente)" % (time.time()-_t_fish), flush=True)
            tlog("[TIMING] get_move: préchargé (%.3fs attente)", time.time()-_t_fish)
        else:
            board_courant = self.nl_inst.game_board.copy()
            fish_move_obj = self.engine.get_move(board_courant, think_time=self._think_time)
            print("[TIMING] get_move: %.2fs" % (time.time()-_t_fish), flush=True)
            tlog("[TIMING] get_move: %.2fs", time.time()-_t_fish)
        if fish_move_obj is None:
            return
        fish_move = fish_move_obj.uci()
        san = san_ep(self.nl_inst.game_board, fish_move_obj)

        _t_step = time.time()
        self.nl_inst.make_move_game_board(fish_move)
        display_move(engine_label, engine_color, san)
        tlog("[TIMING-F] make_move: %.3fs", time.time()-_t_step)

        # Évaluation WDL après le coup du moteur (position du joueur humain)
        wdl_bar = None
        if self.analyse_active:
            _t_wdl = time.time()
            eval_info = self.engine.evaluate(self.nl_inst.game_board.copy(), depth=8)
            wdl_bar   = self.engine.wdl_to_bar(eval_info.get("wdl"))
            self._last_best_move = eval_info.get("best_move")  # disponible pour la pause
            tlog("[TIMING] wdl_moteur: %.2fs", time.time()-_t_wdl)

        _t_send = time.time()
        _engine_full_fen = self.nl_inst.game_board.fen()
        send_event("move", {
            "fen":      _engine_full_fen.split()[0],
            "full_fen": _engine_full_fen,
            "san":      san,
            "uci":      fish_move,
            "color":    engine_color,
            "player":   engine_label,
            "wdl":      wdl_bar,
        })
        tlog("[TIMING] send_event move: %.2fs", time.time()-_t_send)
        # Pendant WAIT_FISH le joueur peut toujours abandonner ou proposer nulle
        send_event("abandon_nulle_ok", {})

        now = time.time()
        gap = round(now - getattr(self, "last_move_time", now), 2)
        self.move_gaps.append(gap)
        self.last_move_time = now

        _t_step = time.time()
        self._append_move_to_pgn(fish_move_obj, comment=f"gap={gap}s")
        tlog("[TIMING-F] append_pgn: %.3fs", time.time()-_t_step)
        _t_step = time.time()
        self.save_pgn_tmp()
        tlog("[TIMING-F] save_pgn: %.3fs", time.time()-_t_step)
        _t_step = time.time()
        self.check_for_game_over()
        tlog("[TIMING-F] game_over_check: %.3fs", time.time()-_t_step)

        while True:
            _t_step = time.time()
            self._wait_for_fish_move_on_board(fish_move)
            print("[TIMING-F] wait_fish_total: %.3fs" % (time.time()-_t_step), flush=True)
            tlog("[TIMING-F] wait_fish_total: %.3fs", time.time()-_t_step)
            if self._abandon_demande:
                self.nl_inst.kill_switch.clear()
                self._traiter_abandon()  # lève BackMenuExit
            if self._nulle_demandee:
                self._nulle_demandee = False
                self.nl_inst.kill_switch.clear()
                self._traiter_nulle(board=self.nl_inst.game_board)
                # acceptée → _end_game lève BackMenuExit (on n'arrive pas ici)
                # refusée → relancer l'attente de placement
                send_event("abandon_nulle_ok", {})
                continue
            break

    def _wait_for_fish_move_on_board(self, fish_move: str) -> None:
        """Attend que le joueur déplace physiquement la pièce de Stockfish."""
        STABLE_DELAY = 0.8
        expected_fen = self.nl_inst.game_board.board_fen()
        self.nl_inst.set_move_leds(fish_move)
        print(f"   Exécutez le coup de Stockfish sur l'échiquier ({fish_move})...")
        _t_wait = time.time()
        print("[WAIT_FISH] début attente placement %s" % fish_move, flush=True)
        tlog("[WAIT_FISH] début attente placement %s", fish_move)

        bad_fen_since = None; last_bad_fen = None
        warning_shown = False; last_diff_count = 0

        # Thread dédié : surveille back_menu/abandonner pendant l'attente physique.
        # Utilise get_action(timeout) pour bloquer sans boucle active.
        _abort_stop = threading.Event()
        def _poll_abort():
            while not _abort_stop.is_set():
                action = get_action(timeout=0.15)
                if action is None:
                    continue
                atype = action.get("type", "")
                if atype == "abandonner":
                    self._abandon_demande = True
                    self.nl_inst.kill_switch.set()
                    return
                elif atype == "back_menu":
                    self._back_menu_demande = True
                    self._abandon_demande = True
                    self.nl_inst.kill_switch.set()
                    return
                elif atype == "nulle":
                    self._nulle_demandee = True
                    self.nl_inst.kill_switch.set()
                    return
                elif atype == "set_pause":
                    self.pedagogique_pause = action.get("value", "blunder")
                # pause et autres actions : ignorées pendant l'attente plateau
        _abort_thread = threading.Thread(target=_poll_abort, daemon=True)
        _abort_thread.start()

        _last_log   = time.time()
        _last_print = time.time()
        _loop_count = 0
        try:
            while True:
                if self.nl_inst.kill_switch.is_set():
                    self.nl_inst.turn_off_all_leds()
                    return
                _loop_count += 1
                raw_fen = self.nl_inst.current_fen
                if not raw_fen:
                    time.sleep(0.05)
                    continue

                board_fen = raw_fen.strip().split()[0]

                if time.time() - _last_log >= 0.5:
                    _last_log = time.time()
                    tlog("[WAIT_FISH] %.1fs (loop=%d) — identique=%s fen=%s",
                         time.time()-_t_wait, _loop_count,
                         board_fen == expected_fen, board_fen[:25])

                if time.time() - _last_print >= 5.0:
                    _last_print = time.time()
                    print("[WAIT_FISH] %.0fs en attente... (%d it.) fen_ok=%s" % (
                        time.time()-_t_wait, _loop_count, board_fen == expected_fen), flush=True)

                if board_fen == expected_fen:
                    print("[WAIT_FISH] confirmé en %.2fs (%d it.)" % (time.time()-_t_wait, _loop_count), flush=True)
                    tlog("[WAIT_FISH] placement confirmé en %.2fs", time.time()-_t_wait)
                    # turn_off_all_leds peut bloquer plusieurs secondes sur USB Chessnut Air
                    # → thread daemon pour ne pas retarder le tour suivant
                    self._cancel_led_off = False
                    def _do_led_off(cancel_ref=self):
                        if not cancel_ref._cancel_led_off:
                            try:
                                cancel_ref.nl_inst.turn_off_all_leds()
                            except Exception:
                                pass
                    threading.Thread(target=_do_led_off, daemon=True).start()
                    if warning_shown:
                        print("   Position rétablie. Continuez.")
                        send_event("turn", {
                            "color":    "white" if self.playing_white == chess.WHITE else "black",
                            "player":   getattr(self, "player_name", "Joueur"),
                            "is_human": True,
                            "in_check": False,
                        })
                    return

                time.sleep(0.05)

                # Promotion
                if len(fish_move) == 5:
                    dest_sq = chess.parse_square(fish_move[2:4])
                    src_sq  = chess.parse_square(fish_move[:2])
                    try:
                        tmp_promo = chess.Board(board_fen + " w - - 0 1")
                        promo_color = chess.WHITE if self.playing_white == chess.BLACK else chess.BLACK
                        if (tmp_promo.piece_at(dest_sq) is not None and
                                tmp_promo.piece_at(dest_sq).color == promo_color and
                                tmp_promo.piece_at(src_sq) is None):
                            return
                    except Exception:
                        pass

                try:
                    tmp_board  = chess.Board(board_fen + " w - - 0 1")
                    diff_count = sum(1 for sq in chess.SQUARES
                                     if self.nl_inst.game_board.piece_at(sq) != tmp_board.piece_at(sq))
                except Exception:
                    diff_count = 0

                if diff_count <= 2:
                    bad_fen_since = None; last_bad_fen = None
                    warning_shown = False; last_diff_count = 0
                    time.sleep(0.05)
                    continue

                now = time.time()
                if board_fen != last_bad_fen:
                    bad_fen_since = now; last_bad_fen = board_fen
                    last_diff_count = diff_count; warning_shown = False
                elif now - bad_fen_since >= STABLE_DELAY and not warning_shown:
                    warning_shown = True; last_diff_count = diff_count
                    _display_position_error(self.nl_inst.game_board, tmp_board,
                                            diff_count, context="fish", fish_move=fish_move)
                    try:
                        self.nl_inst.show_board_diff(self.nl_inst.game_board, tmp_board)
                    except Exception:
                        self.nl_inst.set_move_leds(fish_move)

                if check_tab_press() and warning_shown:
                    _display_position_error(self.nl_inst.game_board, tmp_board,
                                            diff_count, context="fish", fish_move=fish_move)
                time.sleep(0.1)
        finally:
            _abort_stop.set()
            _t_join = time.time()
            _abort_thread.join(timeout=1.0)
            tlog("[WAIT_FISH] abort_join: %.3fs", time.time()-_t_join)

    # ── Boucle principale ─────────────────────────────────────────────────

    def start(self) -> None:
        self.nl_inst.turn_off_all_leds()
        self.run()

    def run(self) -> None:
        # Si le moteur joue en premier, précharger son coup pendant l'initialisation
        if self.nl_inst.game_board.turn != self.playing_white:
            self._start_fish_prefetch()

        _t_tour = time.time()
        while True:
            if self.game_over:
                break
            try:
                if self.nl_inst.game_board.turn == self.playing_white:
                    tlog("[TOUR] début tour HUMAIN (%.2fs depuis dernier tour)", time.time()-_t_tour)
                    _t_tour = time.time()
                    reprendre = self.handle_human_turn()
                    while reprendre:
                        reprendre = self.handle_human_turn()
                    tlog("[TOUR] fin tour HUMAIN: %.2fs", time.time()-_t_tour)
                else:
                    tlog("[TOUR] début tour STOCKFISH (%.2fs depuis dernier tour)", time.time()-_t_tour)
                    _t_tour = time.time()
                    self.handle_fish_turn()
                    tlog("[TOUR] fin tour STOCKFISH: %.2fs", time.time()-_t_tour)
            except (ExitNicLink, SystemExit, BackMenuExit):
                raise  # laisser remonter proprement
            except Exception as e:
                import traceback
                print(f"[CRASH] {type(e).__name__}: {e}")
                traceback.print_exc()
                raise

# ──────────────────────────────────────────────
# Menu et point d'entrée
# ──────────────────────────────────────────────

def ask_player_and_color(players, default_level=5):
    print("\n=== NicLink — Mode Pédagogique ===")
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
        name = input("Nom du joueur : ").strip() or "Joueur"
        if name not in players and name != "Joueur":
            players.append(name)
            players.sort(key=lambda x: x.casefold())
            save_players(players)
            print(f"Joueur enregistré : {name}")
        return name, None, players, True

    parsed = parse_player_input(choice, players)
    return parsed["name"] or "Joueur", parsed["color"], players, False


def ask_color(parsed_color):
    if parsed_color == "b":
        return True
    if parsed_color == "n":
        return False
    if parsed_color == "a":
        return random.choice([True, False])
    while True:
        print("\nCouleur : 1. Blanc  2. Noir  3. Aléatoire")
        raw = input("Choix [1-3] : ").strip().lower()
        if raw in ("", "1", "b", "blanc"):
            return True
        if raw in ("2", "n", "noir"):
            return False
        if raw in ("3", "a"):
            return random.choice([True, False])
        print("Choix invalide.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)

    if args.backup:
        run_backup()
        return

    config = load_config()

    _nl_ref  = [None]
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
        player_name, parsed_color, players, is_new = ask_player_and_color(
            players, default_level=config["stockfish_level"]
        )
        playing_white = ask_color(parsed_color)

        level = ask_int(
            f"Niveau Stockfish [1-20, Entrée = {config['stockfish_level']}] : ",
            min_value=1, max_value=20, default=config["stockfish_level"],
        )

        pause_labels = {
            "toujours": "pause pour tout",
            "erreur":   "pause erreur+blunder",
            "blunder":  "pause blunder seulement",
            "jamais":   "jamais de pause",
        }
        pause_actuel = config.get("pedagogique_pause", "blunder")
        print(f"\nMode feedback : {pause_labels.get(pause_actuel, pause_actuel)}")
        print("  (modifiable dans Paramètres du menu principal)")

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

        game = Game(
            nl_inst, playing_white,
            stockfish_level=level,
            default_game_type=config.get("game_type", "Pedagogical"),
            turn_signal=config.get("turn_signal", "both"),
            pedagogique_pause=pause_actuel,
        )
        game.player_name    = player_name
        game.move_gaps      = []
        game.last_move_time = time.time()
        _game_ref[0] = game

        sig_desc = {"both": "Bip+LEDs", "beep": "Bip",
                    "leds": "LEDs", "none": "Aucun"}.get(
            config.get("turn_signal", "both"), "Bip+LEDs")

        print(f"\nPartie pédagogique : {player_name} vs Stockfish niveau {level}")
        print(f"Couleur : {'Blancs' if playing_white else 'Noirs'}")
        print(f"Signaux : Début de tour -> {sig_desc} / Coup illégal -> Bip échiquier")
        print(f"Feedback coups : {pause_labels.get(pause_actuel, pause_actuel)}")
        print(f"Pour abandonner ou proposer nulle : retirez votre roi de l'échiquier")

        game.save_pgn_tmp()

        # Démarrer le serveur web
        start_server(host="127.0.0.1", port=5000)
        send_event("init", {
            "fen": chess.STARTING_FEN,
            "player": player_name,
            "color": "white" if playing_white else "black",
            "level": level,
            "pause": pause_actuel,
            "opponent": f"Stockfish niv.{level}",
        })
        print("\nInterface web : http://127.0.0.1:5000")
        print("Partie démarrée !")
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
