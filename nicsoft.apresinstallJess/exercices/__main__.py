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

# Dossier des livres Polyglot
BOOKS_DIR    = pathlib.Path.home() / "NicLink" / "data" / "books"
BOOK_DEFAULT = BOOKS_DIR / "gm2001.bin"

# ── Catalogue des ouvertures ──────────────────────────────────────────────────
# Chaque entrée : (eco, nom, description, moves_blancs_suggestion)
OUVERTURES = [
    {
        "id":   "e4_sicilienne",
        "eco":  "B20-B99",
        "nom":  "Défense Sicilienne",
        "desc": "1.e4 c5 — La défense la plus populaire contre 1.e4. Jeu déséquilibré.",
        "init": ["e2e4", "c7c5"],
        "camp_suggere": "black",
    },
    {
        "id":   "e4_francaise",
        "eco":  "C00-C19",
        "nom":  "Défense Française",
        "desc": "1.e4 e6 — Solide et fermée. Bon choix défensif pour les Noirs.",
        "init": ["e2e4", "e7e6"],
        "camp_suggere": "black",
    },
    {
        "id":   "e4_caro_kann",
        "eco":  "B10-B19",
        "nom":  "Défense Caro-Kann",
        "desc": "1.e4 c6 — Très solide. Les Noirs visent une structure de pions saine.",
        "init": ["e2e4", "c7c6"],
        "camp_suggere": "black",
    },
    {
        "id":   "e4_italienne",
        "eco":  "C50-C59",
        "nom":  "Partie Italienne",
        "desc": "1.e4 e5 2.Nf3 Nc6 3.Bc4 — Ouverture classique, développement rapide.",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"],
        "camp_suggere": "white",
    },
    {
        "id":   "e4_ruy_lopez",
        "eco":  "C60-C99",
        "nom":  "Partie Espagnole (Ruy Lopez)",
        "desc": "1.e4 e5 2.Nf3 Nc6 3.Bb5 — L'une des ouvertures les plus étudiées.",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"],
        "camp_suggere": "white",
    },
    {
        "id":   "e4_petroff",
        "eco":  "C42-C43",
        "nom":  "Défense Petroff",
        "desc": "1.e4 e5 2.Nf3 Nf6 — Très solide, mène souvent à l'égalité.",
        "init": ["e2e4", "e7e5", "g1f3", "g8f6"],
        "camp_suggere": "black",
    },
    {
        "id":   "d4_gambit_dame",
        "eco":  "D06-D69",
        "nom":  "Gambit Dame",
        "desc": "1.d4 d5 2.c4 — Blanc offre un pion pour le contrôle du centre.",
        "init": ["d2d4", "d7d5", "c2c4"],
        "camp_suggere": "white",
    },
    {
        "id":   "d4_indienne_roi",
        "eco":  "E60-E99",
        "nom":  "Défense Indienne du Roi",
        "desc": "1.d4 Nf6 2.c4 g6 — Jeu hypermoderne, contrôle indirect du centre.",
        "init": ["d2d4", "g8f6", "c2c4", "g7g6"],
        "camp_suggere": "black",
    },
    {
        "id":   "d4_nimzo",
        "eco":  "E20-E59",
        "nom":  "Défense Nimzo-Indienne",
        "desc": "1.d4 Nf6 2.c4 e6 3.Nc3 Bb4 — Très populaire à haut niveau.",
        "init": ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4"],
        "camp_suggere": "black",
    },
    {
        "id":   "d4_hollandaise",
        "eco":  "A80-A99",
        "nom":  "Défense Hollandaise",
        "desc": "1.d4 f5 — Ouverture agressive pour les Noirs, vise l'attaque.",
        "init": ["d2d4", "f7f5"],
        "camp_suggere": "black",
    },
    {
        "id":   "nf3_anglaise",
        "eco":  "A10-A39",
        "nom":  "Partie Anglaise",
        "desc": "1.c4 — Ouverture de flanchetto, jeu flexible et positionnelle.",
        "init": ["c2c4"],
        "camp_suggere": "white",
    },
    {
        "id":   "e4_moderne",
        "eco":  "B06",
        "nom":  "Défense Moderne",
        "desc": "La défense moderne est une ouverture d'échecs hypermoderne (noirs) caractérisée par 1...g6 et le développement du Fou en g7 (fianchetto)",
        "init": ["e2e4", "g7g6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "french_defense_normal_variation",
        "eco":  "C00",
        "nom":  "French Defense: Normal Variation",
        "desc": "French Defense: Normal Variation",
        "init": ["e2e4", "e7e6", "d2d4"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "french_defense",
        "eco":  "C00",
        "nom":  "French Defense",
        "desc": "French Defense",
        "init": ["e2e4", "e7e6", "d2d4", "d7d5"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "french_defense_tarrasch_variation",
        "eco":  "C03",
        "nom":  "French Defense: Tarrasch Variation",
        "desc": "French Defense: Tarrasch Variation",
        "init": ["e2e4", "e7e6", "d2d4", "d7d5", "b1d2"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "king_s_gambit",
        "eco":  "C30",
        "nom":  "King's Gambit",
        "desc": "King's Gambit",
        "init": ["e2e4", "e7e5", "f2f4"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
    },

    {
        "id":   "king_s_gambit_accepted",
        "eco":  "C33",
        "parent_eco": "C30",
        "nom":  "King's Gambit Accepted",
        "desc": "King's Gambit Accepted",
        "init": ["e2e4", "e7e5", "f2f4", "e5f4"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
    },

    {
        "id":   "king_s_gambit_accepted_king_s_knight_s",
        "eco":  "C34",
        "parent_eco": "C30",
        "nom":  "King's Gambit Accepted: King's Knight's Gambit",
        "desc": "King's Gambit Accepted: King's Knight's Gambit",
        "init": ["e2e4", "e7e5", "f2f4", "e5f4", "g1f3"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
    },

    {
        "id":   "king_s_gambit_accepted_modern_defense",
        "eco":  "C36",
        "parent_eco": "C30",
        "nom":  "King's Gambit Accepted: Modern Defense",
        "desc": "King's Gambit Accepted: Modern Defense",
        "init": ["e2e4", "e7e5", "f2f4", "e5f4", "g1f3", "d7d5", "e4d5"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_morphy_defense",
        "eco":  "C78",
        "nom":  "Ruy Lopez: Morphy Defense",
        "desc": "Ruy Lopez: Morphy Defense",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_morphy_defense_2",
        "eco":  "C70",
        "nom":  "Ruy Lopez: Morphy Defense",
        "desc": "Ruy Lopez: Morphy Defense",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_closed",
        "eco":  "C88",
        "nom":  "Ruy Lopez: Closed",
        "desc": "Ruy Lopez: Closed",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7", "f1e1", "b7b5", "a4b3"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_closed_2",
        "eco":  "C84",
        "nom":  "Ruy Lopez: Closed",
        "desc": "Ruy Lopez: Closed",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_berlin_defense",
        "eco":  "C65",
        "nom":  "Ruy Lopez: Berlin Defense",
        "desc": "Ruy Lopez: Berlin Defense",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_berlin_defense_2",
        "eco":  "C65",
        "nom":  "Ruy Lopez: Berlin Defense",
        "desc": "Ruy Lopez: Berlin Defense",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6", "e1g1"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_berlin_defense_rio_gambit_ac",
        "eco":  "C67",
        "nom":  "Ruy Lopez: Berlin Defense, Rio Gambit Accepted",
        "desc": "Ruy Lopez: Berlin Defense, Rio Gambit Accepted",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6", "e1g1", "f6e4"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_closed_3",
        "eco":  "C88",
        "nom":  "Ruy Lopez: Closed",
        "desc": "Ruy Lopez: Closed",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7", "f1e1", "b7b5", "a4b3", "e8g8"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_berlin_defense_l_hermet_vari",
        "eco":  "C67",
        "nom":  "Ruy Lopez: Berlin Defense, l'Hermet Variation",
        "desc": "Ruy Lopez: Berlin Defense, l'Hermet Variation",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6", "e1g1", "f6e4", "d2d4", "e4d6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "ruy_lopez_berlin_defense_l_hermet_vari_2",
        "eco":  "C67",
        "nom":  "Ruy Lopez: Berlin Defense, l'Hermet Variation, Berlin Wall Defense",
        "desc": "Ruy Lopez: Berlin Defense, l'Hermet Variation, Berlin Wall Defense",
        "init": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6", "e1g1", "f6e4", "d2d4", "e4d6", "b5c6", "d7c6", "d4e5", "d6f5", "d1d8", "e8d8"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "queen_s_pawn_game",
        "eco":  "A40",
        "nom":  "London System",
        "desc": "Queen's Pawn Game",
        "init": ["d2d4"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
    },

    {
        "id":   "dutch_defense_fianchetto_attack",
        "eco":  "A81",
        "nom":  "Dutch Defense: Fianchetto Attack",
        "desc": "Dutch Defense: Fianchetto Attack",
        "init": ["d2d4", "f7f5", "g2g3"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A80",
    },

    {
        "id":   "dutch_defense_semi_leningrad_variation",
        "eco":  "A81",
        "nom":  "Dutch Defense: Semi-Leningrad Variation",
        "desc": "Dutch Defense: Semi-Leningrad Variation",
        "init": ["d2d4", "f7f5", "g2g3", "g8f6", "f1g2", "g7g6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A80",
    },

    {
        "id":   "dutch_defense",
        "eco":  "A84",
        "nom":  "Dutch Defense",
        "desc": "Dutch Defense",
        "init": ["d2d4", "f7f5", "c2c4"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A80",
    },

    {
        "id":   "dutch_defense_raphael_variation",
        "eco":  "A80",
        "nom":  "Dutch Defense: Raphael Variation",
        "desc": "Dutch Defense: Raphael Variation",
        "init": ["d2d4", "f7f5", "b1c3"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "dutch_defense_queen_s_knight_variation",
        "eco":  "A85",
        "nom":  "Dutch Defense: Queen's Knight Variation",
        "desc": "Dutch Defense: Queen's Knight Variation",
        "init": ["d2d4", "f7f5", "c2c4", "g8f6", "b1c3"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A84",
    },

    {
        "id":   "dutch_defense_leningrad_variation_wars",
        "eco":  "A88",
        "nom":  "Dutch Defense: Leningrad Variation, Warsaw Variation",
        "desc": "Dutch Defense: Leningrad Variation, Warsaw Variation",
        "init": ["d2d4", "f7f5", "g2g3", "g8f6", "f1g2", "g7g6", "g1f3", "f8g7", "e1g1", "e8g8", "c2c4", "d7d6", "b1c3", "c7c6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A87",
    },

    {
        "id":   "dutch_defense_normal_variation",
        "eco":  "A84",
        "nom":  "Dutch Defense: Normal Variation",
        "desc": "Dutch Defense: Normal Variation",
        "init": ["d2d4", "f7f5", "c2c4", "g8f6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A80",
    },

    {
        "id":   "dutch_defense_rubinstein_variation",
        "eco":  "A84",
        "nom":  "Dutch Defense: Rubinstein Variation",
        "desc": "Dutch Defense: Rubinstein Variation",
        "init": ["d2d4", "f7f5", "c2c4", "e7e6", "b1c3"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A80",
    },

    {
        "id":   "london_system",
        "eco":  "A48",
        "nom":  "London System",
        "desc": "London System",
        "init": ["d2d4", "g8f6", "g1f3", "g7g6", "c1f4"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A40",
    },

    {
        "id":   "london_system_2",
        "eco":  "A48",
        "nom":  "London System",
        "desc": "London System",
        "init": ["d2d4", "g8f6", "g1f3", "g7g6", "c1f4", "f8g7", "e2e3"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A40",
    },

    {
        "id":   "london_system_3",
        "eco":  "A48",
        "nom":  "London System",
        "desc": "London System",
        "init": ["d2d4", "g8f6", "g1f3", "g7g6", "c1f4", "f8g7", "e2e3", "d7d6"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A40",
    },

    {
        "id":   "english_opening_caro_kann_defensive_sy",
        "eco":  "A11",
        "nom":  "English Opening: Caro-Kann Defensive System",
        "desc": "English Opening: Caro-Kann Defensive System",
        "init": ["c2c4", "c7c6"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A10",
    },

    {
        "id":   "reti_opening_anglo_slav_variation_gure",
        "eco":  "A11",
        "nom":  "Réti Opening: Anglo-Slav Variation, Gurevich System",
        "desc": "Réti Opening: Anglo-Slav Variation, Gurevich System",
        "init": ["c2c4", "c7c6", "g1f3", "d7d5", "e2e3"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
        "parent_eco": "A10",
    },

    {
        "id":   "english_opening_anglo_indian_defense",
        "eco":  "A15",
        "nom":  "English Opening: Anglo-Indian Defense",
        "desc": "English Opening: Anglo-Indian Defense",
        "init": ["c2c4", "g8f6"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A10",
    },

    {
        "id":   "english_opening_anglo_indian_defense_q",
        "eco":  "A16",
        "nom":  "English Opening: Anglo-Indian Defense, Queen's Knight Variation",
        "desc": "English Opening: Anglo-Indian Defense, Queen's Knight Variation",
        "init": ["c2c4", "g8f6", "b1c3"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A15",
    },

    {
        "id":   "english_opening_king_s_english_variati",
        "eco":  "A20",
        "nom":  "English Opening: King's English Variation",
        "desc": "English Opening: King's English Variation",
        "init": ["c2c4", "e7e5"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
    },

    {
        "id":   "english_opening_anglo_indian_defense_k",
        "eco":  "A15",
        "nom":  "English Opening: Anglo-Indian Defense, King's Indian Formation",
        "desc": "English Opening: Anglo-Indian Defense, King's Indian Formation",
        "init": ["c2c4", "g8f6", "g1f3", "g7g6"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A10",
    },

    {
        "id":   "english_opening_king_s_english_variati_2",
        "eco":  "A21",
        "nom":  "English Opening: King's English Variation, Reversed Sicilian",
        "desc": "English Opening: King's English Variation, Reversed Sicilian",
        "init": ["c2c4", "e7e5", "b1c3"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A20",
    },

    {
        "id":   "english_opening_agincourt_defense",
        "eco":  "A13",
        "nom":  "English Opening: Agincourt Defense",
        "desc": "English Opening: Agincourt Defense",
        "init": ["c2c4", "e7e6"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A10",
    },

    {
        "id":   "english_opening_king_s_english_variati_3",
        "eco":  "A28",
        "nom":  "English Opening: King's English Variation, Four Knights Variation",
        "desc": "English Opening: King's English Variation, Four Knights Variation",
        "init": ["c2c4", "e7e5", "b1c3", "g8f6", "g1f3", "b8c6"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A27",
    },

    {
        "id":   "english_opening_king_s_english_variati_4",
        "eco":  "A29",
        "nom":  "English Opening: King's English Variation, Four Knights Variation, Fianchetto Line",
        "desc": "English Opening: King's English Variation, Four Knights Variation, Fianchetto Line",
        "init": ["c2c4", "e7e5", "b1c3", "g8f6", "g1f3", "b8c6", "g2g3"],
        "camp_suggere": "white",
        "book": "gm2001.bin",
        "parent_eco": "A28",
    },

    {
        "id":   "king_s_pawn_game",
        "eco":  "C20",
        "nom":  "King's Pawn Game",
        "desc": "King's Pawn Game",
        "init": ["e2e4", "e7e5"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
    },

    {
        "id":   "french_defense_paulsen_variation",
        "eco":  "C10",
        "nom":  "French Defense: Paulsen Variation",
        "desc": "French Defense: Paulsen Variation",
        "init": ["e2e4", "e7e6", "d2d4", "d7d5", "b1c3"],
        "camp_suggere": "black",
        "book": "gm2001.bin",
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
        # Livre associé à l'ouverture (champ 'book') ou fallback gm2001.bin
        book_name = ouverture.get('book', '')
        if book_name:
            book_candidate = BOOKS_DIR / book_name
            self._book_path = str(book_candidate if book_candidate.exists() else BOOK_DEFAULT)
        else:
            self._book_path = str(BOOK_DEFAULT)

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

    def sync_from_physical(self) -> bool:
        """Synchronise self.board depuis le plateau physique.
        
        On repart depuis la position initiale et on repousse les coups d'init
        pour conserver les droits de roque et le hash Zobrist correct pour le livre.
        Si le plateau physique correspond à la position d'init → on utilise self._init_board.
        Sinon on tente de repartir des coups d'init sur board frais.
        """
        try:
            raw  = self.nl_inst.current_fen
            phys = raw.strip().split()[0] if raw else ""
            if not phys:
                return False

            # Reconstruire depuis position initiale + coups d'init
            # pour garder les droits de roque et le hash Polyglot correct
            board_fresh = chess.Board()
            for mv in self._init_moves:
                board_fresh.push(mv)

            # Vérifier que la position physique correspond EXACTEMENT aux coups d'init
            if board_fresh.board_fen() != phys:
                send_event("exercice_sync_error", {
                    "message":      "Pièces mal placées — corrigez et resynchronisez",
                    "expected_fen": board_fresh.board_fen(),
                    "physical_fen": phys,
                })
                print(f"[EX] Sync refusée — FEN physique ≠ init")
                return False

            self.board = board_fresh
            self.nl_inst.game_board = self.board.copy()
            self._send_position()
            send_event("exercice_synced", {"fen": phys, "turn": "w" if self.board.turn == chess.WHITE else "b"})
            print(f"[EX] Synchro plateau → {phys[:40]}")
            return True
        except Exception as e:
            logger.warning(f"sync_from_physical : {e}")
            return False

    def _wait_position(self, target_fen: str, initial_delay: float = 0.0) -> bool:
        """Attend que le plateau corresponde au FEN cible via get_fen()."""
        # Vérifier d'abord si déjà correct
        try:
            raw = self.nl_inst.get_fen()
            if raw and raw.strip().split()[0] == target_fen:
                self.nl_inst.turn_off_all_leds()
                return True
        except Exception:
            pass

        # Délai initial avant d'afficher les cases rouges
        if initial_delay > 0:
            t_start = time.time()
            while self._running and time.time() - t_start < initial_delay:
                time.sleep(0.2)
                try:
                    raw = self.nl_inst.get_fen()
                    if raw and raw.strip().split()[0] == target_fen:
                        self.nl_inst.turn_off_all_leds()
                        return True
                except Exception:
                    pass

        last_bad  = None
        bad_since = None
        STABLE    = 0.8

        while self._running:
            try:
                raw  = self.nl_inst.get_fen()
                phys = raw.strip().split()[0] if raw else ""
            except Exception:
                time.sleep(0.2)
                continue

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
            time.sleep(0.3)
        return False

    def _wait_human_move(self) -> chess.Move | None:
        """Attend un coup légal via await_move() — même méthode que pédagogique."""
        from nicsoft.niclink.nl_exceptions import ExitNicLink
        from nicsoft.web.server import action_queue as _aq

        # Watcher actions web dans un thread séparé
        stop_watch = threading.Event()

        def _watch_actions():
            while not stop_watch.is_set():
                try:
                    if not _aq.empty():
                        action = _aq.get_nowait()
                        atype = action.get("type", "")
                        if atype in ("exercice_back", "back_menu"):
                            self._running = False
                            self.nl_inst.kill_switch.set()
                        elif atype == "exercice_retry":
                            self._retry_requested = True
                            self.nl_inst.kill_switch.set()
                        elif atype == "exercice_sync":
                            self.sync_from_physical()
                            # Pas d'interruption — juste mettre à jour game_board
                            self.nl_inst.kill_switch.set()
                            self._sync_requested = True
                except Exception:
                    pass
                time.sleep(0.2)

        self._retry_requested = False
        self._sync_requested  = False
        watcher = threading.Thread(target=_watch_actions, daemon=True)
        watcher.start()

        move_uci = None
        while self._running:
            try:
                self.nl_inst.game_board = self.board.copy()
                self.nl_inst.kill_switch.clear()
                move_uci = self.nl_inst.await_move()
            except ExitNicLink:
                pass
            except Exception as e:
                logger.warning(f"await_move : {e}")

            if self._retry_requested:
                break
            if self._sync_requested:
                # Sync effectué — relancer await_move avec le nouveau board
                self._sync_requested = False
                self.nl_inst.kill_switch.clear()
                continue
            # Coup reçu ou interruption
            break

        stop_watch.set()
        self.nl_inst.kill_switch.clear()
        watcher.join(timeout=1.0)

        if self._retry_requested:
            return "RETRY"
        if not self._running or move_uci is None:
            return None

        # Convertir en Move — chercher dans les coups légaux depuis self.board
        try:
            move = chess.Move.from_uci(move_uci)
            if move in self.board.legal_moves:
                return move
            # Essayer aussi depuis la position physique
            # (le FEN physique peut avoir plus de contexte)
        except Exception:
            pass

        # Chercher le coup par comparaison de FEN
        try:
            raw = self.nl_inst.get_fen()
            phys = raw.strip().split()[0] if raw else ""
            if phys:
                for m in self.board.legal_moves:
                    test = self.board.copy()
                    test.push(m)
                    if test.board_fen() == phys:
                        return m
        except Exception:
            pass

        return None

    def _wait_placement_adv(self, uci: str) -> bool:
        """Attend que le joueur place la pièce adverse — lecture passive du FEN."""
        expected = self.board.board_fen()
        while self._running:
            try:
                raw  = self.nl_inst.current_fen
                phys = raw.strip().split()[0] if raw else ""
                if phys == expected:
                    return True
            except Exception:
                pass
            time.sleep(0.15)
        return False

    # ── Boucle principale ─────────────────────────────────────────────────────

    def _wait_initial_sync(self) -> None:
        """Attend l'action exercice_sync du joueur avant de démarrer la boucle.
        Gère aussi exercice_back/back_menu/exercice_retry."""
        from nicsoft.web.server import action_queue as _aq
        while self._running:
            try:
                action = _aq.get(timeout=0.5)
            except Exception:
                continue
            atype = action.get("type", "")
            if atype == "exercice_sync":
                synced = self.sync_from_physical()
                if synced:
                    return
                # Sync refusée (mauvaise position) — rester en attente
            elif atype == "exercice_retry":
                # Recommencer demandé depuis l'écran d'attente — remettre la position
                self.board = chess.Board()
                for mv in self._init_moves:
                    self.board.push(mv)
                self.nl_inst.game_board = self.board.copy()
                self.nl_inst.turn_off_all_leds()
                self._send_position()
                send_event("exercice_wait_position", {
                    "fen":        self.board.board_fen(),
                    "nom":        self.ouverture["nom"],
                    "move_count": len(self._init_moves),
                })
                # Rester en attente de sync
            elif atype in ("exercice_back", "back_menu"):
                self._running = False
                return

    def run(self) -> None:
        self._running = True
        self.nl_inst.turn_off_all_leds()

        # Envoyer la position de départ — juste l'afficher, pas vérifier
        self._send_position()
        send_event("exercice_wait_position", {
            "fen":        self.board.board_fen(),
            "nom":        self.ouverture["nom"],
            "move_count": len(self._init_moves),
        })
        # Attendre la synchro explicite du joueur avant de démarrer
        # (obligatoire si le premier tour est celui de l'adversaire)
        self._wait_initial_sync()

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
                    # Construire la liste des coups valides
                    valid_moves = []
                    for e in book_moves[:5]:
                        try: valid_moves.append({"san": self.board.san(e.move), "uci": e.move.uci()})
                        except Exception: pass
                    send_event("exercice_out_of_book", {
                        "san":         san,
                        "uci":         move.uci(),
                        "best_san":    best_san,
                        "best_uci":    book_moves[0].move.uci() if book_moves else "",
                        "valid_moves": valid_moves,
                    })
                    # Attendre que le joueur replace la pièce (via await_move)
                    # NicLink détectera le retour à la position correcte

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

                # Attendre placement physique via await_move
                # Les LEDs guident le joueur — await_move détecte le placement
                if not self._wait_placement_adv(uci):
                    return
                self.nl_inst.turn_off_all_leds()
                send_event("position_ok", {"fen": self.board.board_fen()})

        self.nl_inst.turn_off_all_leds()

    def _restart(self) -> None:
        """Recommencer depuis la position de départ de l'ouverture."""
        self.board = chess.Board()
        for mv in self._init_moves:
            self.board.push(mv)
        self.nl_inst.game_board = self.board.copy()
        self.nl_inst.turn_off_all_leds()
        self._send_position()
        send_event("exercice_wait_position", {
            "fen":        self.board.board_fen(),
            "nom":        self.ouverture["nom"],
            "move_count": len(self._init_moves),
        })
        self._wait_initial_sync()

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
        book_moves = []
        for e in book_entries[:5]:
            try:
                book_moves.append({
                    "san": self.board.san(e.move),
                    "uci": e.move.uci(),
                })
            except Exception:
                pass
        send_event("exercice_position", {
            "fen":        self.board.board_fen(),
            "from":       from_sq,
            "to":         to_sq,
            "turn":       "white" if self.board.turn == chess.WHITE else "black",
            "human_turn": self.board.turn == self.human_color,
            "book_moves": book_moves,
            "move_num":   len(self.board.move_stack),
        })
