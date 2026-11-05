"""
nicsoft/engine/engine_detection.py — NicLink
Détection des binaires et chemins de chaque moteur (Stockfish, lc0/Maia,
Rodent IV) sur le système.
"""

import logging
import sys
import shutil
from pathlib import Path

from nicsoft.config import ENGINES_DIR

logger = logging.getLogger("EngineManager")


def find_stockfish() -> str | None:
    """
    Cherche l'exécutable Stockfish sur le système.
    Retourne le chemin ou None si introuvable.
    """
    # Windows : glob stockfish*.exe dans engines/
    if sys.platform == "win32":
        for p in sorted(ENGINES_DIR.rglob("stockfish*.exe")):
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


def find_lc0() -> str | None:
    """
    Cherche l'exécutable lc0 sur le système, selon la plateforme.

    Les deux binaires (lc0 et lc0.exe) coexistent souvent dans engines/maia/
    (release multi-plateforme) : il est impératif de ne considérer le .exe
    que sous Windows, sinon Linux tente d'exécuter un PE et échoue (issue #197).
    """
    if sys.platform == "win32":
        candidates = [
            shutil.which("lc0"),
            str(ENGINES_DIR / "maia" / "lc0.exe"),
        ]
    else:
        candidates = [
            shutil.which("lc0"),
            str(ENGINES_DIR / "maia" / "lc0"),
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


def _ensure_executable(path: str) -> None:
    """
    S'assure que le binaire à `path` a le bit exécutable (Linux/Mac).
    No-op sous Windows et si le bit est déjà positionné. Couvre les
    installations où l'extraction (zip, clone) n'a pas préservé les
    permissions d'origine (issue #197).
    """
    if sys.platform == "win32":
        return
    import os
    import stat
    try:
        mode = os.stat(path).st_mode
        if not (mode & stat.S_IXUSR):
            os.chmod(path, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as e:
        logger.warning(f"Impossible de positionner le bit exécutable sur {path} : {e}")


# ── Moteur Rodent IV ──────────────────────────────────────────────────────────

def find_rodent() -> str | None:
    """Cherche l'exécutable Rodent IV selon la plateforme."""
    if sys.platform == "win32":
        # Chemin 1 : installation ZIP (make_release.sh renomme le binaire)
        path = ENGINES_DIR / "rodent-iv" / "rodentIV.exe"
        if path.exists():
            return str(path)
        # Chemin 2 : installation SyncGitRepo (binaire dans rodent-iv-win/)
        path = ENGINES_DIR / "rodent-iv-win" / "rodent-iv-x64.exe"
        return str(path) if path.exists() else None
    else:
        path = ENGINES_DIR / "rodent-iv" / "rodentIV"
        return str(path) if path.exists() else None
