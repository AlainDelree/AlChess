"""
nicsoft/game/engine_manager.py — NicLink
Couche d'abstraction universelle pour les moteurs d'échecs UCI.

Supporte tout moteur UCI (Stockfish, Maia, etc.) via python-chess.
Expose une interface commune indépendante du moteur utilisé.

Fonctionnalités :
  - Contrôle de force par Elo (UCI_Elo) plutôt que Skill Level 1-20
  - Évaluation WDL (Victoire/Nulle/Défaite) pour la barre d'évaluation
  - MultiPV : plusieurs coups candidats pour l'analyse
  - Mode sans analyse : joueur configure l'analyse_active indépendamment
"""

import chess
import chess.engine
import threading
import logging
from pathlib import Path
from nicsoft.config import ENGINES_DIR

logger = logging.getLogger("EngineManager")

# ── Seuils d'évaluation (centipawns de perte) ────────────────────────────────
SEUIL_BON         =  50   # < 50cp  → bon coup
SEUIL_IMPRECISION = 100   # 50-100  → imprécision
SEUIL_ERREUR      = 300   # 100-300 → erreur
                          # >= 300  → blunder

# Plage Elo supportée par Stockfish via UCI_Elo
ELO_MIN = 1320
ELO_MAX = 3190
ELO_DEFAUT = 1500


def classifier_coup(delta_cp: int) -> str:
    """Classe un coup selon la perte en centipawns."""
    if delta_cp < SEUIL_BON:
        return "bon"
    elif delta_cp < SEUIL_IMPRECISION:
        return "imprecision"
    elif delta_cp < SEUIL_ERREUR:
        return "erreur"
    else:
        return "blunder"


def score_to_cp(score: chess.engine.Score, joueur: chess.Color) -> int | None:
    """
    Convertit un Score python-chess en centipawns du point de vue du joueur.
    Retourne None si c'est un mat.
    """
    if score.is_mate():
        return None
    cp = score.white().score()
    if joueur == chess.WHITE:
        return cp
    else:
        return -cp


class EngineManager:
    """
    Gestionnaire universel de moteur UCI.

    Utilise python-chess pour communiquer avec n'importe quel moteur UCI.
    Deux instances internes :
      - _engine_play  : pour calculer les coups (Elo limité)
      - _engine_eval  : pour évaluer les positions (pleine force, rapide)
    """

    def __init__(self, engine_path: str, engine_elo: int = ELO_DEFAUT,
                 analyse_active: bool = True) -> None:
        self._engine_path   = engine_path
        self._engine_elo    = max(ELO_MIN, min(ELO_MAX, engine_elo))
        self._analyse_active = analyse_active
        self._lock_play     = threading.Lock()
        self._lock_eval     = threading.Lock()

        self._engine_play: chess.engine.SimpleEngine | None = None
        self._engine_eval: chess.engine.SimpleEngine | None = None

        self._supports_wdl     = False
        self._supports_elo_limit = False
        self._engine_name      = "Moteur UCI"

        self._init_engines()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_engines(self) -> None:
        """Lance les deux instances du moteur et détecte les capacités."""
        try:
            self._engine_play = chess.engine.SimpleEngine.popen_uci(self._engine_path)
            self._engine_eval = chess.engine.SimpleEngine.popen_uci(self._engine_path)
            self._engine_name = self._engine_play.id.get("name", "Moteur UCI")

            # Détecter les options supportées
            options = self._engine_play.options
            self._supports_elo_limit = (
                "UCI_LimitStrength" in options and "UCI_Elo" in options
            )
            self._supports_wdl = "UCI_ShowWDL" in options

            # Configurer le moteur de jeu (Elo limité)
            self._apply_elo(self._engine_play)

            # Configurer le moteur d'évaluation (pleine force, rapide)
            if self._supports_wdl:
                self._engine_eval.configure({"UCI_ShowWDL": True})

            logger.info(f"Moteur : {self._engine_name}")
            logger.info(f"Elo limité : {self._supports_elo_limit} | WDL : {self._supports_wdl}")

        except Exception as e:
            logger.error(f"Impossible de lancer le moteur : {e}")
            raise

    def _apply_elo(self, engine: chess.engine.SimpleEngine) -> None:
        """Applique la limitation de force Elo sur une instance du moteur."""
        if self._supports_elo_limit:
            engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": self._engine_elo,
            })
            if self._supports_wdl:
                engine.configure({"UCI_ShowWDL": True})
        else:
            # Fallback : moteur sans UCI_Elo → pas de limitation de force
            logger.warning(f"{self._engine_name} ne supporte pas UCI_Elo.")

    # ── API publique ──────────────────────────────────────────────────────────

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def engine_elo(self) -> int:
        return self._engine_elo

    @property
    def analyse_active(self) -> bool:
        return self._analyse_active

    @analyse_active.setter
    def analyse_active(self, value: bool) -> None:
        self._analyse_active = value

    def set_elo(self, elo: int) -> None:
        """Change le niveau Elo du moteur de jeu à chaud."""
        self._engine_elo = max(ELO_MIN, min(ELO_MAX, elo))
        with self._lock_play:
            if self._engine_play:
                self._apply_elo(self._engine_play)

    def get_move(self, board: chess.Board, think_time: float = 1.0) -> chess.Move | None:
        """
        Demande le meilleur coup au moteur de jeu (Elo limité).

        Paramètres :
          board      : position actuelle
          think_time : temps de réflexion en secondes

        Retourne le coup ou None en cas d'erreur.
        """
        with self._lock_play:
            if not self._engine_play:
                return None
            try:
                result = self._engine_play.play(
                    board,
                    chess.engine.Limit(time=think_time),
                )
                return result.move
            except Exception as e:
                logger.error(f"Erreur get_move : {e}")
                return None

    def evaluate(self, board: chess.Board, depth: int = 8) -> dict:
        """
        Évalue une position avec le moteur d'évaluation (pleine force).

        Retourne un dict :
          {
            "cp"      : int | None,   # centipawns du point de vue du joueur actif
            "mate"    : int | None,   # coups avant mat (négatif = on se fait mater)
            "wdl"     : (int, int, int) | None,  # (victoire, nulle, défaite) /1000
            "best_move": str | None,  # meilleur coup UCI
          }
        """
        with self._lock_eval:
            if not self._engine_eval:
                return {"cp": None, "mate": None, "wdl": None, "best_move": None}
            try:
                info = self._engine_eval.analyse(
                    board,
                    chess.engine.Limit(depth=depth),
                    info=chess.engine.INFO_ALL,
                )
                score = info.get("score")
                pv    = info.get("pv", [])

                cp   = None
                mate = None
                wdl  = None

                if score:
                    pov_score = score.pov(board.turn)
                    if pov_score.is_mate():
                        mate = pov_score.mate()
                    else:
                        cp = pov_score.score()
                    # WDL du point de vue du joueur actif
                    if self._supports_wdl and score.wdl():
                        w = score.wdl().pov(board.turn)
                        wdl = (w.wins, w.draws, w.losses)

                best_move = pv[0].uci() if pv else None

                return {"cp": cp, "mate": mate, "wdl": wdl, "best_move": best_move}

            except Exception as e:
                logger.error(f"Erreur evaluate : {e}")
                return {"cp": None, "mate": None, "wdl": None, "best_move": None}

    def evaluate_move(self, board: chess.Board, move: chess.Move,
                      depth: int = 8) -> tuple[str, int, str | None]:
        """
        Évalue la qualité d'un coup joué.

        Retourne (qualite, delta_cp, best_move_uci) :
          - qualite    : "bon" / "imprecision" / "erreur" / "blunder"
          - delta_cp   : perte en centipawns (0 = parfait)
          - best_move  : meilleur coup UCI si différent du coup joué, sinon None
        """
        if not self._analyse_active:
            return "bon", 0, None

        try:
            joueur = board.turn

            # Évaluation AVANT le coup
            eval_avant = self.evaluate(board, depth=depth)
            cp_avant   = eval_avant["cp"]
            best_move  = eval_avant["best_move"]


            if cp_avant is None:
                # Position de mat → bon coup par défaut
                return "bon", 0, None

            # Évaluation APRÈS le coup
            board_apres = board.copy()
            board_apres.push(move)
            eval_apres = self.evaluate(board_apres, depth=depth)
            cp_apres   = eval_apres["cp"]

            if cp_apres is None:
                # Mat après le coup → excellent
                return "bon", 0, None

            # La perte est vue du point de vue du joueur AVANT son coup
            # cp_avant = score pour joueur avant coup
            # cp_apres = score pour l'adversaire après coup → on l'inverse
            delta = max(0, cp_avant - (-cp_apres))

            qualite = classifier_coup(delta)
            best    = best_move if best_move and best_move != move.uci() else None

            # Si coup mauvais mais pas de meilleur coup alternatif trouvé,
            # relancer en MultiPV=2 pour obtenir le vrai meilleur coup
            if qualite != "bon" and best is None:
                try:
                    with self._lock_eval:
                        info_mpv = self._engine_eval.analyse(
                            board,
                            chess.engine.Limit(depth=depth),
                            multipv=2,
                        )
                    if isinstance(info_mpv, list):
                        for entry in info_mpv:
                            pv = entry.get("pv", [])
                            if pv and pv[0].uci() != move.uci():
                                best = pv[0].uci()
                                break
                except Exception as e:
                    logger.warning(f"MultiPV fallback échoué : {e}")

            return qualite, delta, best

        except Exception as e:
            logger.error(f"Erreur evaluate_move : {e}")
            return "bon", 0, None

    def get_punishment_line(self, board: chess.Board, move: chess.Move,
                             depth: int = 12, max_moves: int = 3) -> list[str]:
        """
        Retourne la ligne punitive après un coup humain.
        """
        with self._lock_eval:
            if not self._engine_eval:
                return []
            try:
                board_after = board.copy()
                board_after.push(move)
                info = self._engine_eval.analyse(
                    board_after,
                    chess.engine.Limit(depth=depth),
                    info=chess.engine.INFO_PV,
                )
                pv = info.get("pv", [])
                result = [m.uci() for m in pv[:max_moves]]
                logger.debug(f"get_punishment_line: {result}")
                return result
            except Exception as e:
                logger.error(f"Erreur get_punishment_line : {e}")
                return []

    def get_multipv(self, board: chess.Board, n: int = 3,
                    depth: int = 12) -> list[dict]:
        """
        Retourne les n meilleurs coups avec leur évaluation.
        Utile pour l'écran d'analyse.

        Retourne une liste de dict :
          [{"move": str (UCI), "cp": int, "mate": int | None}, ...]
        """
        with self._lock_eval:
            if not self._engine_eval:
                return []
            try:
                infos = self._engine_eval.analyse(
                    board,
                    chess.engine.Limit(depth=depth),
                    multipv=n,
                    info=chess.engine.INFO_ALL,
                )
                result = []
                for info in infos:
                    pv    = info.get("pv", [])
                    score = info.get("score")
                    if not pv:
                        continue
                    move_uci = pv[0].uci()
                    cp   = None
                    mate = None
                    if score:
                        pov = score.pov(board.turn)
                        if pov.is_mate():
                            mate = pov.mate()
                        else:
                            cp = pov.score()
                    result.append({"move": move_uci, "cp": cp, "mate": mate})
                return result
            except Exception as e:
                logger.error(f"Erreur get_multipv : {e}")
                return []

    def analyser_partie(self, moves_uci: list[str],
                        callback=None,
                        seq_moves: int = 3) -> list[dict]:
        """
        Analyse une liste de coups UCI.

        Paramètres :
          moves_uci : liste de coups UCI
          callback  : fonction(idx, total, résultat) appelée après chaque coup
          seq_moves : nombre de coups de la séquence punitive (3-5)

        Retourne une liste de dict :
          [{"qualite": str, "delta_cp": int, "best_move": str | None,
            "punishment_line": list[str], "fen_avant_coup": str}, ...]
        """
        board     = chess.Board()
        resultats = []
        total     = len(moves_uci)

        for idx, uci in enumerate(moves_uci):
            try:
                move = chess.Move.from_uci(uci)
                fen_avant = board.fen()
                qualite, delta, best = self.evaluate_move(board, move, depth=8)
                # Calculer la séquence punitive pour les coups non-bons
                punishment_line = []
                if qualite != "bon" and best:
                    punishment_line = self.get_punishment_line(
                        board, move, depth=12, max_moves=seq_moves
                    )
                res = {
                    "qualite":          qualite,
                    "delta_cp":         delta,
                    "best_move":        best,
                    "punishment_line":  punishment_line,
                    "fen_avant_coup":   fen_avant,
                }
                board.push(move)
            except Exception:
                res = {
                    "qualite":         "bon",
                    "delta_cp":        0,
                    "best_move":       None,
                    "punishment_line": [],
                    "fen_avant_coup":  board.fen(),
                }

            resultats.append(res)
            if callback:
                callback(idx, total, res)

        return resultats

    def wdl_to_bar(self, wdl: tuple[int, int, int] | None) -> dict:
        """
        Convertit un tuple WDL en pourcentages pour la barre d'affichage.

        Retourne :
          {"win": float, "draw": float, "loss": float}
          ou None si WDL non disponible.
        """
        if not wdl:
            return None
        w, d, l = wdl
        total = w + d + l
        if total == 0:
            return None
        return {
            "win":  round(w / total * 100, 1),
            "draw": round(d / total * 100, 1),
            "loss": round(l / total * 100, 1),
        }

    def quit(self) -> None:
        """Arrête proprement les deux instances du moteur."""
        for engine in [self._engine_play, self._engine_eval]:
            if engine:
                try:
                    engine.quit()
                except Exception:
                    pass
        self._engine_play = None
        self._engine_eval = None


# ── Fonction utilitaire ───────────────────────────────────────────────────────

def find_stockfish() -> str | None:
    """
    Cherche l'exécutable Stockfish sur le système.
    Retourne le chemin ou None si introuvable.
    """
    import sys
    import shutil
    # Windows : glob stockfish*.exe dans engines/
    if sys.platform == "win32":
        for p in sorted(ENGINES_DIR.glob("stockfish*.exe")):
            return str(p)
    candidates = [
        shutil.which("stockfish"),
        str(ENGINES_DIR / "stockfish"),
        "/usr/games/stockfish",
        "/usr/bin/stockfish",
        "/usr/local/bin/stockfish",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


# ── Moteur Maia ───────────────────────────────────────────────────────────────

# Niveaux Maia disponibles et fichiers de poids correspondants
MAIA_LEVELS = {
    1100: "maia-1100.pb.gz",
    1200: "maia-1200.pb.gz",
    1300: "maia-1300.pb.gz",
    1400: "maia-1400.pb.gz",
    1500: "maia-1500.pb.gz",
    1600: "maia-1600.pb.gz",
    1700: "maia-1700.pb.gz",
    1800: "maia-1800.pb.gz",
    1900: "maia-1900.pb.gz",
}

def find_rodent() -> str | None:
    """Cherche l'exécutable Rodent IV selon la plateforme."""
    import sys
    exe = "rodentIV.exe" if sys.platform == "win32" else "rodentIV"
    path = ENGINES_DIR / "rodent-iv" / exe
    return str(path) if path.exists() else None


def rodent_available() -> bool:
    """
    Détermine si Rodent IV peut être proposé comme moteur.

    Ne se contente pas de vérifier la présence du binaire : le lance réellement
    et exige que le handshake UCI aboutisse (`uci` + `isready`, effectués par
    `popen_uci`) ET que les options attendues soient exposées (`Personality`,
    `UCI_Elo`) — garantie qu'il s'agit bien de Rodent IV et non d'un binaire
    corrompu ou incompatible. À appeler côté UI/menu avant d'offrir le moteur.
    """
    path = find_rodent()
    if not path:
        return False
    engine = None
    try:
        engine = chess.engine.SimpleEngine.popen_uci(path)
        return "Personality" in engine.options and "UCI_Elo" in engine.options
    except Exception as e:
        logger.warning(f"Rodent IV présent mais ne répond pas au handshake UCI : {e}")
        return False
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass


# ── Rodent IV : personnalités et bornes ──────────────────────────────────────
# Valeurs EXACTES de l'option UCI combo "Personality" du binaire Rodent IV 0.33
# (relevées via `uci`). Le sélecteur UI doit envoyer une de ces valeurs telles
# quelles ; toute autre valeur est refusée par le moteur. "Bosboom.txt" porte
# bien l'extension dans la déclaration UCI (quirk du binaire).
RODENT_PERSONALITIES = [
    "Alekhine", "Amanda", "Ampere", "Anand", "Anderssen", "Bosboom.txt",
    "Botvinnik", "Cloe", "Deborah", "Defender", "Dynamic", "Fischer",
    "Grumpy", "Karpov", "Kasparov", "Kortchnoi", "Larsen", "Lasker",
    "Marshall", "Morphy", "Nimzowitsch", "Partisan", "Pawnsacker", "Pedrita",
    "Petrosian", "Preston", "Reti", "Rubinstein", "Simple", "Spassky",
    "Spitfire", "Steinitz", "Strangler", "Tarrasch", "Tal", "Topalov",
]
RODENT_ELO_MIN            = 800
RODENT_ELO_MAX            = 2800
RODENT_ELO_DEFAUT         = 1200
RODENT_PERSONALITY_DEFAUT = "Tal"


def find_lc0() -> str | None:
    """Cherche l'exécutable lc0 sur le système."""
    import shutil
    candidates = [
        shutil.which("lc0"),
        str(ENGINES_DIR / "maia" / "lc0.exe"),  # Windows
        str(ENGINES_DIR / "maia" / "lc0"),       # Linux/Mac
        str(Path.home() / "lc0" / "build" / "release" / "lc0"),
        "/usr/local/bin/lc0",
        "/usr/bin/lc0",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def find_maia_weights(elo: int) -> str | None:
    """
    Cherche le fichier de poids Maia pour un niveau Elo donné.
    Sélectionne le niveau disponible le plus proche parmi les fichiers présents sur disque.
    """
    maia_dir = ENGINES_DIR / "maia"
    available = {
        level: str(maia_dir / filename)
        for level, filename in MAIA_LEVELS.items()
        if (maia_dir / filename).exists()
    }
    if not available:
        return None
    closest = min(available.keys(), key=lambda x: abs(x - elo))
    return available[closest]


class MaiaEngine(EngineManager):
    """
    Moteur Maia Chess via lc0.

    Différences avec EngineManager (Stockfish) :
    - Le niveau est défini par le fichier de poids (maia-1100 à maia-1900)
    - get_move() utilise nodes=1 au lieu d'un temps de réflexion
    - evaluate() et evaluate_move() utilisent Stockfish pour l'analyse
      (Maia n'est pas fait pour évaluer, seulement pour jouer)
    """

    def __init__(self, lc0_path: str, weights_path: str,
                 maia_elo: int = 1100,
                 stockfish_path: str | None = None,
                 analyse_active: bool = True) -> None:

        self._lc0_path      = lc0_path
        self._weights_path  = weights_path
        self._analyse_active = analyse_active
        self._lock_play     = threading.Lock()
        self._lock_eval     = threading.Lock()

        self._engine_play: chess.engine.SimpleEngine | None = None
        self._engine_eval: chess.engine.SimpleEngine | None = None

        self._supports_wdl       = False
        self._supports_elo_limit = False

        # Extraire le niveau réel depuis le nom du fichier de poids
        import re as _re
        m = _re.search(r'maia-(\d+)', str(weights_path))
        self._maia_elo   = int(m.group(1)) if m else maia_elo
        self._engine_name = f"Maia {self._maia_elo}"

        self._init_maia(lc0_path, weights_path, stockfish_path)

    def _init_maia(self, lc0_path: str, weights_path: str,
                   stockfish_path: str | None) -> None:
        """Lance lc0 avec les poids Maia + Stockfish pour l'analyse."""
        try:
            # Moteur de jeu : lc0 + poids Maia
            self._engine_play = chess.engine.SimpleEngine.popen_uci(
                [lc0_path, f"--weights={weights_path}"]
            )
            self._engine_name = f"Maia {self._maia_elo}"
            logger.info(f"Maia lancé : {weights_path}")

            # Moteur d'évaluation : Stockfish si disponible, sinon lc0
            if stockfish_path and Path(stockfish_path).exists():
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(stockfish_path)
                self._supports_wdl = "UCI_ShowWDL" in self._engine_eval.options
                if self._supports_wdl:
                    self._engine_eval.configure({"UCI_ShowWDL": True})
                logger.info(f"Stockfish pour analyse : {stockfish_path}")
            else:
                # Fallback : deuxième instance lc0 pour l'analyse
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(
                    [lc0_path, f"--weights={weights_path}"]
                )
                logger.warning("Stockfish non trouvé — analyse via lc0 (limité)")

        except Exception as e:
            logger.error(f"Impossible de lancer Maia : {e}")
            raise

    def get_move(self, board: chess.Board,
                 think_time: float = 1.0) -> chess.Move | None:
        """
        Demande un coup à Maia — nodes=1 (pas de recherche, réseau pur).
        think_time est ignoré pour Maia.
        """
        with self._lock_play:
            if not self._engine_play:
                return None
            try:
                result = self._engine_play.play(
                    board,
                    chess.engine.Limit(nodes=1),
                )
                return result.move
            except Exception as e:
                logger.error(f"Erreur Maia get_move : {e}")
                return None

    # evaluate(), evaluate_move(), get_punishment_line(), wdl_to_bar()
    # sont héritées d'EngineManager et utilisent _engine_eval (Stockfish)
    # → pas besoin de les surcharger

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def engine_elo(self) -> int:
        return self._maia_elo


# ── Moteur Rodent IV ──────────────────────────────────────────────────────────

class RodentEngine(EngineManager):
    """
    Moteur Rodent IV — adversaire faible pensé pour les débutants.

    Spécificités (cf. investigation issue #12) :
      - L'ordre d'envoi des `setoption` est IMPÉRATIF :
          Personality → UCI_LimitStrength → UCI_Elo  (Elo TOUJOURS en dernier).
        Chaque option est envoyée dans son propre `configure()` pour garantir
        l'ordre indépendamment de l'implémentation de python-chess. Si l'Elo
        n'est pas envoyé en dernier, le moteur retombe à pleine puissance.
      - L'analyse (barre d'évaluation, qualité des coups) est déléguée à
        Stockfish : Rodent n'est pas conçu pour évaluer objectivement.
    """

    def __init__(self, rodent_path: str,
                 personality: str = RODENT_PERSONALITY_DEFAUT,
                 rodent_elo: int = RODENT_ELO_DEFAUT,
                 stockfish_path: str | None = None,
                 analyse_active: bool = True) -> None:
        self._rodent_path    = rodent_path
        self._personality    = personality if personality in RODENT_PERSONALITIES \
                                            else RODENT_PERSONALITY_DEFAUT
        self._engine_elo     = max(RODENT_ELO_MIN, min(RODENT_ELO_MAX, rodent_elo))
        self._analyse_active = analyse_active
        self._lock_play      = threading.Lock()
        self._lock_eval      = threading.Lock()

        self._engine_play: chess.engine.SimpleEngine | None = None
        self._engine_eval: chess.engine.SimpleEngine | None = None

        self._supports_wdl       = False
        self._supports_elo_limit = True
        self._engine_name        = f"Rodent {self._engine_elo}"

        self._init_rodent(rodent_path, stockfish_path)

    def _apply_rodent_options(self, engine: chess.engine.SimpleEngine) -> None:
        """
        Envoie les options dans l'ordre impératif Personality → LimitStrength → Elo.
        Un `configure()` distinct par option = un `setoption` distinct, ordre garanti.

        Note (vérifié via logs UCI, issue #13) : python-chess n'émet PAS un
        `setoption` quand la valeur demandée égale la valeur par défaut déclarée
        par le moteur. Rodent IV déclare `UCI_LimitStrength` avec le défaut
        `true` → la ligne LimitStrength n'apparaît pas dans les logs (no-op),
        l'option étant déjà active. L'ordre réellement envoyé reste donc
        Personality → UCI_Elo (Elo en dernier), ce qui satisfait la contrainte
        de l'issue #12. Robuste : si un build avait le défaut `false`,
        python-chess enverrait la ligne (valeur ≠ défaut).
        """
        engine.configure({"Personality": self._personality})
        engine.configure({"UCI_LimitStrength": True})
        engine.configure({"UCI_Elo": self._engine_elo})

    def _init_rodent(self, rodent_path: str, stockfish_path: str | None) -> None:
        try:
            # Moteur de jeu : Rodent (Elo limité, personnalité choisie)
            self._engine_play = chess.engine.SimpleEngine.popen_uci(rodent_path)
            self._apply_rodent_options(self._engine_play)
            logger.info(f"Rodent : Personality={self._personality}, Elo={self._engine_elo}")

            # Moteur d'évaluation : Stockfish si disponible, sinon Rodent (limité)
            if stockfish_path and Path(stockfish_path).exists():
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(stockfish_path)
                if "UCI_ShowWDL" in self._engine_eval.options:
                    self._engine_eval.configure({"UCI_ShowWDL": True})
                    self._supports_wdl = True
                logger.info(f"Rodent : analyse déléguée à Stockfish ({stockfish_path})")
            else:
                self._engine_eval = chess.engine.SimpleEngine.popen_uci(rodent_path)
                logger.warning("Rodent : Stockfish introuvable — analyse via Rodent (limitée)")

        except Exception as e:
            logger.error(f"Impossible de lancer Rodent : {e}")
            raise

    def set_elo(self, elo: int) -> None:
        """Change l'Elo à chaud en respectant l'ordre Personality → LimitStrength → Elo."""
        self._engine_elo  = max(RODENT_ELO_MIN, min(RODENT_ELO_MAX, elo))
        self._engine_name = f"Rodent {self._engine_elo}"
        with self._lock_play:
            if self._engine_play:
                self._apply_rodent_options(self._engine_play)

    @property
    def personality(self) -> str:
        return self._personality

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def engine_elo(self) -> int:
        return self._engine_elo
