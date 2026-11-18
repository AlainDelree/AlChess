"""
nicsoft/tests/test_issue359_san_ep_guard.py — AlChess

Issue #359 : la notation SAN d'un coup joué/affiché doit toujours passer
par `san_ep()` (`nicsoft/engine/board_utils.py`), jamais par `board.san()`
directement — seul `san_ep` ajoute le suffixe " e.p." pour une prise en
passant (24 occurrences remplacées à l'époque, cf. ancien
historique_bugs.md, trié par #358).

Garde-fou SANS NAVIGATEUR ni matériel (analyse statique du source, sur le
modèle de test_issue303_html_escaping.py). Neuf fichiers appellent déjà
`.san(` directement : huit outils d'import/export de livres d'ouvertures
et utilitaires d'analyse post-partie (hors flux de partie live), et un
neuvième — `modes/lichess/puzzle_game.py` — qui, lui, EST du flux live
(coup/solution d'un puzzle envoyé en direct au navigateur) : ce sont des
violations connues, non corrigées par cette issue (voir CHANGELOG-359.md)
et donc explicitement mises en liste blanche ci-dessous. Ce test échoue
seulement si un NOUVEAU fichier (hors liste blanche, hors `board_utils.py`
lui-même, hors `tests/`) appelle `.san(` directement.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NICSOFT_DIR = REPO_ROOT / "nicsoft"

# Définit san_ep() lui-même : seul endroit autorisé à appeler board.san().
_SAN_EP_DEFINITION_FILE = NICSOFT_DIR / "engine" / "board_utils.py"

# Violations connues à la date de l'issue #359 — outils d'import/export de
# livres d'ouvertures et utilitaires d'analyse post-partie (hors flux de
# partie live), SAUF modes/lichess/puzzle_game.py qui, lui, est du flux
# live (coup/solution d'un puzzle envoyé en direct au navigateur). Listées
# dans le rapport de clôture #359, non corrigées ici (hors périmètre de
# cette issue). Toute diminution de cette liste (fichier corrigé) est
# bienvenue ; toute augmentation doit passer par san_ep() à la place.
_FICHIERS_EN_LISTE_BLANCHE = {
    "modes/exercices/add_ouverture.py",
    "modes/exercices/explore_book_import.py",
    "modes/exercices/explore_book_cli.py",
    "modes/exercices/explore_book_web.py",
    "modes/exercices/eco_import_import.py",
    "modes/exercices/import_lignes.py",
    "modes/lichess/puzzle_game.py",
    "engine/review_multipv.py",
    "web/server.py",
}

_SAN_CALL_RE = re.compile(r"\.san\(")


def _fichiers_py():
    for path in NICSOFT_DIR.rglob("*.py"):
        if path == _SAN_EP_DEFINITION_FILE:
            continue
        if "tests" in path.relative_to(NICSOFT_DIR).parts:
            continue
        yield path


def test_aucun_nouvel_appel_direct_a_board_san_hors_liste_blanche():
    fautifs = []
    for path in _fichiers_py():
        rel = path.relative_to(NICSOFT_DIR).as_posix()
        if rel in _FICHIERS_EN_LISTE_BLANCHE:
            continue
        src = path.read_text(encoding="utf-8")
        if _SAN_CALL_RE.search(src):
            fautifs.append(rel)
    assert not fautifs, (
        "Appel direct à .san() détecté hors san_ep() (nicsoft/engine/board_utils.py) "
        f"dans : {fautifs} — utiliser san_ep(board, move) à la place (suffixe ' e.p.' "
        "pour une prise en passant), ou ajouter le fichier à la liste blanche de ce "
        "test avec une raison si l'appel est authentiquement hors du flux de partie."
    )


def test_liste_blanche_toujours_a_jour():
    """Un fichier de la liste blanche qui n'appelle plus .san( directement
    doit en être retiré — sinon la liste blanche masquerait une régression
    future dans ce même fichier."""
    perimes = []
    for rel in _FICHIERS_EN_LISTE_BLANCHE:
        path = NICSOFT_DIR / rel
        if not path.exists():
            perimes.append(f"{rel} (fichier introuvable)")
            continue
        if not _SAN_CALL_RE.search(path.read_text(encoding="utf-8")):
            perimes.append(rel)
    assert not perimes, f"Entrées de liste blanche périmées (à retirer) : {perimes}"
