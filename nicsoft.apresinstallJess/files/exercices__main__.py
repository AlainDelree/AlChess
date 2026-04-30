"""
nicsoft/exercices/__main__.py — NicLink
Module d'entraînement aux ouvertures via livre Polyglot (gm2001.bin).

Flux :
  1. Joueur choisit une ouverture, son camp, la variété adversaire
  2. Position initiale sur le plateau physique
  3. Joueur joue un coup → vérifié dans le livre
     - Dans la théorie : accepté, adversaire répond (tiré parmi les N premiers)
     - Hors théorie : signal + proposition de reprendre
  4. Fin de ligne (plus de coups dans le livre) → message + option rejouer
"""

import chess
import chess.polyglot
import logging
import pathlib
import threading
import time

from nicsoft.web.server import send_event, get_action, set_app_state

logger = logging.getLogger("NL exercices")
logger.setLevel(logging.INFO)
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter("%(name)s | %(message)s"))
logger.addHandler(_ch)

# Chemin vers le livre Polyglot
BOOK_PATH = pathlib.Path.home() / "NicLink" / "data" / "books" / "gm2001.bin"

# ── Catalogue des ouvertures ──────────────────────────────────────────────────
# Chaque entrée : (eco, nom, description, moves_blancs_suggestion)
OUVERTURES = [
    {
        "id":   "e4_sicilienne",
        "eco":  "B20-B99",
        "nom":  "Défense Sicilienne",
        "desc": "1.e4 c5 — La défense la plus populaire contre 1.e4. Jeu déséquilibré.",
        "init": ["e2e4", "c7c5"],
        "camp_suggere": "white",
    },
    {
        "id":   "e4_francaise",
        "eco":  "C00-C19",
        "nom":  "Défense Française",
        "desc": "1.e4 e6 — Solide et fermée. Bon choix défensif pour les Noirs.",
        "init": ["e2e4", "e7e6"],
        "camp_suggere": "white",
    },
    {
        "id":   "e4_caro_kann",
        "eco":  "B10-B19",
        "nom":  "Défense Caro-Kann",
        "desc": "1.e4 c6 — Très solide. Les Noirs visent une structure de pions saine.",
        "init": ["e2e4", "c7c6"],
        "camp_suggere": "white",
    },
    {
        "id":   "e4_italienne",
        "eco":  "C50-C59",
        "nom":  "Partie Italienne",
        "desc": "1.e4 e5 2.Nf3 Nc6 3.Bc4 — Ouverture classique, développement rapide.",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"],
        "camp_suggere": "black",
    },
    {
        "id":   "e4_ruy_lopez",
        "eco":  "C60-C99",
        "nom":  "Partie Espagnole (Ruy Lopez)",
        "desc": "1.e4 e5 2.Nf3 Nc6 3.Bb5 — L'une des ouvertures les plus étudiées.",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"],
        "camp_suggere": "black",
    },
    {
        "id":   "e4_petroff",
        "eco":  "C42-C43",
        "nom":  "Défense Petroff",
        "desc": "1.e4 e5 2.Nf3 Nf6 — Très solide, mène souvent à l'égalité.",
        "init": ["e2e4", "e7e5", "g1f3", "g8f6"],
        "camp_suggere": "white",
    },
    {
        "id":   "d4_gambit_dame",
        "eco":  "D06-D69",
        "nom":  "Gambit Dame",
        "desc": "1.d4 d5 2.c4 — Blanc offre un pion pour le contrôle du centre.",
        "init": ["d2d4", "d7d5", "c2c4"],
        "camp_suggere": "black",
    },
    {
        "id":   "d4_indienne_roi",
        "eco":  "E60-E99",
        "nom":  "Défense Indienne du Roi",
        "desc": "1.d4 Nf6 2.c4 g6 — Jeu hypermoderne, contrôle indirect du centre.",
        "init": ["d2d4", "g8f6", "c2c4", "g7g6"],
        "camp_suggere": "white",
    },
    {
        "id":   "d4_nimzo",
        "eco":  "E20-E59",
        "nom":  "Défense Nimzo-Indienne",
        "desc": "1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 — Très populaire à haut niveau.",
        "init": ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4"],
        "camp_suggere": "white",
    },
    {
        "id":   "d4_hollandaise",
        "eco":  "A80-A99",
        "nom":  "Défense Hollandaise",
        "desc": "1.d4 f5 — Ouverture agressive pour les Noirs, vise l'attaque.",
        "init": ["d2d4", "f7f5"],
        "camp_suggere": "white",
    },
    {
        "id":   "nf3_anglaise",
        "eco":  "A10-A39",
        "nom":  "Partie Anglaise",
        "desc": "1.c4 — Ouverture de flanchetto, jeu flexible et positionnelle.",
        "init": ["c2c4"],
        "camp_suggere": "black",
    },
]


def get_ouvertures() -> list:
    return OUVERTURES


# ── Session d'exercice ────────────────────────────────────────────────────────

class ExerciceSession:
    """
    Session d'entraînement aux ouvertures.
    Le livre Polyglot guide les coups théoriques.
    """

    def __init__(self, nl_inst, ouverture: dict,
                 human_color: str = "white",
                 variete: int = 3) -> None:
        """
        ouverture : entrée du catalogue OUVERTURES
        human_color : 'white' ou 'black'
        variete : nombre de réponses adverses parmi lesquelles choisir
        """
        self.nl_inst      = nl_inst
        self.ouverture    = ouverture
        self.human_color  = chess.WHITE if human_color == "white" else chess.BLACK
        self.variete      = max(1, variete)
        self.board        = chess.Board()
        self._running     = False
        self._book_path   = str(BOOK_PATH)

        # Rejouer les coups d'init pour placer la position de départ
        self._init_moves: list[chess.Move] = []
        for uci in ouverture.get("init", []):
            try:
                mv = chess.Move.from_uci(uci)
                if mv in self.board.legal_moves:
                    self.board.push(mv)
                    self._init_moves.append(mv)
            except Exception:
                pass

    # ── Livre Polyglot ────────────────────────────────────────────────────────

    def _get_book_moves(self, board: chess.Board) -> list:
        """Retourne les coups du livre pour la position, triés par poids décroissant."""
        try:
            with chess.polyglot.open_reader(self._book_path) as reader:
                entries = list(reader.find_all(board))
            entries.sort(key=lambda e: e.weight, reverse=True)
            return entries
        except Exception as e:
            logger.warning(f"Livre : {e}")
            return []

    def _pick_book_move(self, board: chess.Board) -> chess.Move | None:
        """Choisit un coup adverse parmi les N premiers coups du livre."""
        import random
        entries = self._get_book_moves(board)
        if not entries:
            return None
        pool = entries[:self.variete]
        # Pondération par poids
        total = sum(e.weight for e in pool)
        if total == 0:
            return pool[0].move
        r = random.randint(0, total - 1)
        cumul = 0
        for e in pool:
            cumul += e.weight
            if r < cumul:
                return e.move
        return pool[0].move

    def _is_in_book(self, board: chess.Board) -> bool:
        """Vérifie si la position courante a des coups dans le livre."""
        return len(self._get_book_moves(board)) > 0

    # ── Attente plateau physique ──────────────────────────────────────────────

    def _wait_position(self, target_fen: str) -> bool:
        """
        Attend que le plateau physique corresponde au FEN cible.
        Retourne False si la session est interrompue.
        """
        last_bad  = None
        bad_since = None
        STABLE    = 0.8
        while self._running:
            raw  = self.nl_inst.current_fen
            phys = raw.strip().split()[0] if raw else ""
            if phys == target_fen:
                self.nl_inst.turn_off_all_leds()
                return True
            now = time.time()
            if phys != last_bad:
                last_bad  = phys
                bad_since = now
            elif phys and bad_since and now - bad_since >= STABLE:
                send_event("position_error", {
                    "expected_fen": target_fen,
                    "physical_fen": phys,
                })
            time.sleep(0.15)
        return False

    def _wait_human_move(self) -> chess.Move | None:
        """
        Attend un coup légal du joueur sur le plateau physique.
        Retourne None si interruption.
        """
        STABLE    = 0.4
        last_fen  = self.board.board_fen()
        candidate = None
        cand_time = None

        while self._running:
            time.sleep(0.1)
            # Vérifier actions web (retour, etc.)
            from nicsoft.web.server import action_queue as _aq
            try:
                if not _aq.empty():
                    action = _aq.get_nowait()
                    atype = action.get("type", "")
                    if atype in ("exercice_back", "back_menu"):
                        self._running = False
                        return None
                    elif atype == "exercice_retry":
                        return "RETRY"
            except Exception:
                pass

            raw  = self.nl_inst.current_fen
            phys = raw.strip().split()[0] if raw else ""

            if not phys or phys == last_fen:
                candidate = None
                continue

            if phys != candidate:
                candidate = phys
                cand_time = time.time()
                continue

            if time.time() - cand_time < STABLE:
                continue

            # Position stable — chercher coup légal
            for move in self.board.legal_moves:
                test = self.board.copy()
                test.push(move)
                if test.board_fen() == phys:
                    return move

            # Pas légal — position libre, accepter comme nouvelle référence
            last_fen = phys
            candidate = None

        return None

    # ── Boucle principale ─────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        self.nl_inst.turn_off_all_leds()

        # Envoyer la position de départ
        self._send_position()

        # Attendre placement sur plateau physique
        target = self.board.board_fen()
        send_event("exercice_wait_position", {
            "fen":  target,
            "nom":  self.ouverture["nom"],
            "move_count": len(self._init_moves),
        })
        if not self._wait_position(target):
            return
        send_event("position_ok", {"fen": target})

        # Boucle coups
        while self._running:
            in_book = self._is_in_book(self.board)

            # Plus de coups dans le livre → fin de ligne
            if not in_book:
                send_event("exercice_end_of_line", {
                    "fen":    self.board.board_fen(),
                    "moves":  len(self.board.move_stack),
                    "nom":    self.ouverture["nom"],
                })
                # Attendre action (rejouer ou retour)
                result = self._wait_action_end()
                if result == "RETRY":
                    self._restart()
                    continue
                return

            # Tour humain ou adversaire ?
            if self.board.turn == self.human_color:
                # Tour humain
                send_event("exercice_turn", {
                    "color": "white" if self.human_color == chess.WHITE else "black",
                    "fen":   self.board.board_fen(),
                    "in_book": True,
                })

                move = self._wait_human_move()
                if move is None:
                    return
                if move == "RETRY":
                    self._restart()
                    continue

                # Vérifier si dans le livre
                book_moves = self._get_book_moves(self.board)
                book_ucis  = [e.move.uci() for e in book_moves]

                if move.uci() in book_ucis:
                    # Coup théorique
                    san = self.board.san(move)
                    self.board.push(move)
                    self.nl_inst.game_board = self.board.copy()
                    send_event("exercice_move_ok", {
                        "san":    san,
                        "uci":    move.uci(),
                        "color":  "white" if not (self.board.turn == chess.WHITE) else "black",
                        "rank":   book_ucis.index(move.uci()) + 1,
                        "total":  len(book_moves),
                    })
                    self._send_position(move.uci())
                else:
                    # Hors théorie
                    san = self.board.san(move)
                    best_san = self.board.san(book_moves[0].move) if book_moves else "?"
                    # Revenir en arrière physiquement (ne pas pousser)
                    send_event("exercice_out_of_book", {
                        "san":      san,
                        "uci":      move.uci(),
                        "best_san": best_san,
                        "best_uci": book_moves[0].move.uci() if book_moves else "",
                    })
                    # Attendre que le joueur replace la pièce
                    if not self._wait_position(self.board.board_fen()):
                        return

            else:
                # Tour adversaire (livre)
                adv_move = self._pick_book_move(self.board)
                if adv_move is None:
                    # Livre vide pour cet adversaire — fin de ligne
                    send_event("exercice_end_of_line", {
                        "fen":   self.board.board_fen(),
                        "moves": len(self.board.move_stack),
                        "nom":   self.ouverture["nom"],
                    })
                    result = self._wait_action_end()
                    if result == "RETRY":
                        self._restart()
                        continue
                    return

                san = self.board.san(adv_move)
                uci = adv_move.uci()
                self.board.push(adv_move)
                self.nl_inst.game_board = self.board.copy()
                self.nl_inst.set_move_leds(uci)

                adv_color = "black" if self.human_color == chess.WHITE else "white"
                send_event("exercice_adv_move", {
                    "san":   san,
                    "uci":   uci,
                    "color": adv_color,
                })
                self._send_position(uci)

                # Attendre placement physique
                if not self._wait_position(self.board.board_fen()):
                    return
                send_event("position_ok", {"fen": self.board.board_fen()})

        self.nl_inst.turn_off_all_leds()

    def _restart(self) -> None:
        """Recommencer depuis la position de départ de l'ouverture."""
        self.board = chess.Board()
        for mv in self._init_moves:
            self.board.push(mv)
        self.nl_inst.game_board = self.board.copy()
        self.nl_inst.turn_off_all_leds()
        target = self.board.board_fen()
        send_event("exercice_wait_position", {
            "fen":        target,
            "nom":        self.ouverture["nom"],
            "move_count": len(self._init_moves),
        })
        self._wait_position(target)
        send_event("position_ok", {"fen": target})

    def _wait_action_end(self) -> str:
        """Attend une action de fin (retry ou back). Retourne 'RETRY' ou None."""
        while self._running:
            from nicsoft.web.server import get_action as _ga
            action = _ga(timeout=1.0)
            if action is None:
                continue
            atype = action.get("type", "")
            if atype == "exercice_retry":
                return "RETRY"
            if atype in ("exercice_back", "back_menu"):
                self._running = False
                return None
        return None

    def _send_position(self, last_uci: str = None) -> None:
        files = "abcdefgh"
        from_sq = to_sq = None
        if last_uci and len(last_uci) >= 4:
            from_sq = f"{files.index(last_uci[0])}-{int(last_uci[1])-1}"
            to_sq   = f"{files.index(last_uci[2])}-{int(last_uci[3])-1}"
        # Coups du livre pour la position courante (pour affichage)
        book_entries = self._get_book_moves(self.board)
        book_sans = []
        for e in book_entries[:5]:
            try:
                book_sans.append(self.board.san(e.move))
            except Exception:
                pass
        send_event("exercice_position", {
            "fen":        self.board.board_fen(),
            "from":       from_sq,
            "to":         to_sq,
            "turn":       "white" if self.board.turn == chess.WHITE else "black",
            "human_turn": self.board.turn == self.human_color,
            "book_moves": book_sans,
            "move_num":   self.board.fullmove_number,
        })
