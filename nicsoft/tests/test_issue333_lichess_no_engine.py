"""
nicsoft/tests/test_issue333_lichess_no_engine.py — AlChess

Test manquant signalé par le rapport de clôture de l'issue #327 (« Point 7
— Fair-play ») : « Non ajouté : un test dédié « le mode Lichess ne démarre
aucun moteur » — un tel test générique n'existait pas avant cette issue (à
vérifier/ajouter dans une issue de suivi si souhaité) ; test_no_web_import.py
(ARC-001) couvre déjà l'absence d'import de nicsoft.web mais pas
spécifiquement l'absence d'import moteur. » L'issue #333, point 5, demande
explicitement de l'ajouter — y compris pour la reprise de partie.

Analyse STATIQUE (module ast) plutôt que dynamique : inspecte TOUTES les
instructions d'import de chaque fichier du mode Lichess, y compris celles
situées dans le corps d'une fonction (ex. `_run_lichess_resume`,
`_run_lichess_human`) ou d'un bloc try/except — sans avoir besoin
d'exécuter réellement un cycle de reprise/partie pour les atteindre. Couvre
donc "démarre" (aucun code capable de lancer un moteur n'est même
accessible) et "importe" (aucune instruction d'import, prise ou non)
à la fois, et pour la reprise comme pour une partie normale.

Aucun import de `subprocess` non plus (voie alternative pour lancer un
exécutable moteur, ex. Rodent/Maia, sans passer par nicsoft.engine) —
confirmé absent aujourd'hui (voir rapport de clôture), gardé ainsi.
"""
import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

LICHESS_DIR = REPO_ROOT / "nicsoft" / "modes" / "lichess"
LICHESS_LAUNCHER = REPO_ROOT / "nicsoft" / "core" / "game_manager_modes" / "lichess.py"

LICHESS_FILES = sorted(LICHESS_DIR.glob("*.py")) + [LICHESS_LAUNCHER]

# Sous-modules de nicsoft.engine qui démarrent ou pilotent réellement un
# moteur d'échecs (Stockfish, lc0/Maia, Rodent) — PAS tout le paquet
# `nicsoft.engine` : `board_utils`/`pgn_manager`/`players`/`display` y
# vivent aussi (voir CLAUDE.md) mais sont de purs utilitaires python-chess/
# PGN, sans rapport avec un moteur, et DÉJÀ importés par game.py (coups,
# historique) — les bloquer serait un faux positif. Liste établie par
# lecture de chaque fichier de nicsoft/engine/ (grep de leurs imports,
# 14/11/2026) : seuls ceux-ci importent `chess.engine` ou localisent un
# exécutable moteur (`engine_detection.find_stockfish/find_lc0/find_rodent`).
# `review_multipv` (issue #335, écran d'analyse post-partie commun) ajouté
# en défense : il construit un EngineManager, jamais utilisé ni importable
# depuis le mode Lichess (l'écran d'analyse ne s'ouvre qu'une fois la
# partie terminée, jamais pendant une partie Lichess en cours).
_FORBIDDEN_ENGINE_SUBMODULES = (
    "nicsoft.engine.analyse",
    "nicsoft.engine.engine_analysis",
    "nicsoft.engine.engine_availability",
    "nicsoft.engine.engine_detection",
    "nicsoft.engine.engine_manager",
    "nicsoft.engine.maia_engine",
    "nicsoft.engine.move_quality",
    "nicsoft.engine.review_multipv",
    "nicsoft.engine.rodent_engine",
    "nicsoft.engine.uci_engine",
)
# Wrapper UCI de python-chess lui-même — distinct de `chess` (utilisé
# partout ici pour la seule logique d'échecs : board, coups, FEN).
_FORBIDDEN_MODULE_PREFIXES = _FORBIDDEN_ENGINE_SUBMODULES + ("chess.engine",)
# Voie alternative pour lancer un exécutable moteur sans passer par un
# import Python dédié — jamais utilisée aujourd'hui dans ce mode (voir
# docstring ci-dessus) ; bloquée en défense.
_FORBIDDEN_MODULE_EXACT = ("subprocess",)


def _garde_fou_decouverte_non_cassee():
    assert len(LICHESS_FILES) >= 7, (
        f"découverte de fichiers Lichess suspecte ({len(LICHESS_FILES)} trouvé(s)) — "
        "chemin déplacé ou dossier vide ?"
    )
    assert LICHESS_LAUNCHER.is_file()


_garde_fou_decouverte_non_cassee()


def _tous_les_noms_importes(fichier: Path) -> list:
    """Tous les noms de modules apparaissant dans une instruction d'import
    de ce fichier, À N'IMPORTE QUEL NIVEAU (module, fonction, try/except,
    branche conditionnelle) — via ast.walk, qui descend dans tout le corps
    de l'arbre, pas seulement le niveau module."""
    source = fichier.read_text(encoding="utf-8")
    arbre = ast.parse(source, filename=str(fichier))
    noms = []
    for node in ast.walk(arbre):
        if isinstance(node, ast.Import):
            noms.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                noms.append(node.module)
            # `from nicsoft import engine` (sans "nicsoft.engine" comme
            # module direct) — couvert en inspectant aussi les noms importés
            # eux-mêmes lorsque le module parent est "nicsoft".
            if node.module == "nicsoft":
                noms.extend(f"nicsoft.{alias.name}" for alias in node.names)
    return noms


@pytest.mark.parametrize("fichier", LICHESS_FILES, ids=lambda f: f.name)
def test_fichier_lichess_n_importe_aucun_moteur(fichier):
    """Issue #327 (test manquant signalé) / #333 point 5 : aucune
    instruction d'import de ce fichier du mode Lichess ne référence un
    module moteur, qu'elle soit au niveau module ou nichée dans une
    fonction (ex. la reprise, _run_lichess_resume)."""
    noms = _tous_les_noms_importes(fichier)
    fautifs = [
        n for n in noms
        if n in _FORBIDDEN_MODULE_EXACT
        or any(n == p or n.startswith(p + ".") for p in _FORBIDDEN_MODULE_PREFIXES)
    ]
    assert not fautifs, (
        f"{fichier.relative_to(REPO_ROOT)} importe un module moteur interdit : {fautifs}"
    )


def test_aucun_fichier_lichess_n_importe_de_moteur_ensemble():
    """Garde-fou global : même vérification, un seul test qui échoue avec
    le détail complet si plusieurs fichiers étaient fautifs à la fois
    (plus lisible qu'une liste de tests individuels échoués)."""
    fautifs_par_fichier = {}
    for fichier in LICHESS_FILES:
        noms = _tous_les_noms_importes(fichier)
        fautifs = [
            n for n in noms
            if n in _FORBIDDEN_MODULE_EXACT
            or any(n == p or n.startswith(p + ".") for p in _FORBIDDEN_MODULE_PREFIXES)
        ]
        if fautifs:
            fautifs_par_fichier[str(fichier.relative_to(REPO_ROOT))] = fautifs
    assert not fautifs_par_fichier, f"import(s) moteur interdits : {fautifs_par_fichier}"


def test_decouverte_fichiers_lichess_couvre_le_lanceur_et_le_module_metier():
    """Garde-fou (même esprit que _arc001_discovery.py) : la découverte ne
    doit jamais silencieusement perdre le lanceur ou le module métier."""
    noms_relatifs = {f.relative_to(REPO_ROOT).as_posix() for f in LICHESS_FILES}
    assert "nicsoft/core/game_manager_modes/lichess.py" in noms_relatifs
    assert "nicsoft/modes/lichess/game.py" in noms_relatifs
    assert "nicsoft/modes/lichess/client.py" in noms_relatifs
