"""
nicsoft/core/game_manager_modes/state.py — NicLink
État partagé entre plusieurs lanceurs de mode (échiquier courant, mode
virtuel) et utilitaires communs (attente de position, toasts d'erreur,
lecture config moteur). Vit à un seul endroit : les autres modules de
game_manager_modes lisent/écrivent cet état exclusivement via les
fonctions ci-dessous — jamais par "from state import _nl_inst_ref" ou
"from state import _virtual_mode", qui figerait une copie périmée à
l'import.

L'état propre à un seul mode (session d'exercice, drapeau d'annulation de
copie labo, session Opening Explorer...) reste local au module de ce mode.
"""

import json
import logging
import time

import chess

from nicsoft.config import DATA_DIR
from nicsoft.core.config_manager import validated_engine_path
from nicsoft.core.ihm_port import send_event, set_app_state

logger = logging.getLogger("niclink.game_manager")

# ── État global ────────────────────────────────────────────────────────────────
_nl_inst_ref  = None   # échiquier courant (pour éteindre LEDs au quit)
_virtual_mode = False  # True si mode sans échiquier physique


def get_nl_inst_ref():
    return _nl_inst_ref


def set_nl_inst_ref(nl_inst) -> None:
    global _nl_inst_ref
    _nl_inst_ref = nl_inst


def get_virtual_mode() -> bool:
    return _virtual_mode


def set_virtual_mode(val: bool) -> None:
    global _virtual_mode
    _virtual_mode = val


def _read_engine_elo_and_path() -> tuple:
    """Lit engine_elo/engine_path depuis data/config.json (defaults si absent/invalide)."""
    cfg_path    = DATA_DIR / "config.json"
    engine_elo  = 1500
    engine_path = ""
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_elo  = cfg.get("engine_elo", 1500)
            engine_path = validated_engine_path(cfg)
        except Exception as e:
            logger.debug(f"Lecture config.json échouée, valeurs par défaut conservées : {e}")
    return engine_elo, engine_path


# ── Toasts d'erreur au retour menu ───────────────────────────────────────────────
_TOAST_MESSAGES = {
    "toast.board_not_found":  "Échiquier non détecté au démarrage.",
    "toast.position_timeout": "Position initiale non atteinte (timeout).",
    "toast.engine_error":     "Moteur d'échecs indisponible.",
}


def _menu_toast_data(toast_key: str) -> dict:
    """Construit le payload set_app_state("menu", ...) pour un retour menu forcé par une erreur."""
    return {
        "toast_message_key": toast_key,
        "toast_message":     _TOAST_MESSAGES.get(toast_key, "Une erreur est survenue."),
        "toast_type":        "warning",
    }


# ── Attente position ───────────────────────────────────────────────────────────
def _wait_initial_position_web(nl_inst, timeout: float = 300.0):
    INITIAL_FEN = chess.Board().board_fen()
    first_check = True
    consecutive_errors = 0
    t_start = time.time()
    while True:
        try:
            raw_fen = nl_inst.get_fen()
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            if consecutive_errors >= 5 or (time.time() - t_start) >= timeout:
                raise ConnectionError("Échiquier non détecté.")
            time.sleep(0.2)
            continue
        board_fen = raw_fen.strip().split()[0] if raw_fen else ""
        if not board_fen:
            consecutive_errors += 1
            if consecutive_errors >= 5 or (time.time() - t_start) >= timeout:
                raise ConnectionError("Échiquier non détecté.")
            time.sleep(0.2)
            continue
        if board_fen == INITIAL_FEN:
            nl_inst.turn_off_all_leds()
            set_app_state("connecting")
            time.sleep(0.3)
            return
        if first_check:
            first_check = False
            try: nl_inst.signal_lights(1)
            except Exception: pass  # signal LED cosmétique — échec sans conséquence fonctionnelle
        set_app_state("position_initiale", {"fen": board_fen})
        time.sleep(0.5)


def _wait_position_web(nl_inst, target_fen: str, timeout: float = 300.0):
    """Attend que le plateau physique corresponde au FEN cible."""
    target = target_fen.strip().split()[0] if " " in target_fen else target_fen
    t_start = time.time()
    first_check = True
    while True:
        try:
            raw = nl_inst.get_fen()
            board_fen = raw.strip().split()[0] if raw else ""
        except Exception:
            # lecture FEN momentanément indisponible — boucle rapide (0.2s), on retente sans tracer à chaque itération
            time.sleep(0.2)
            continue
        if board_fen == target:
            nl_inst.turn_off_all_leds()
            return
        if first_check:
            first_check = False
        send_event("position_error", {
            "expected_fen": target,
            "physical_fen": board_fen,
        })
        if (time.time() - t_start) >= timeout:
            raise ConnectionError("Timeout — position non atteinte.")
        time.sleep(0.5)
