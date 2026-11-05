"""
Test issue #270 — livre d'ouvertures introuvable en mode Exercices.

Avant le fix : si le fichier du livre Polyglot n'existe pas (ex. dossier
data/ absent), `_get_book_moves` avalait l'exception et retournait [],
indistinguable d'une vraie fin de ligne théorique — l'IHM annonçait alors
"Ligne terminée ! Bravo" alors que le livre n'avait jamais pu être lu, et
le serveur loggait l'erreur à chaque coup.

Ce test vérifie, sans interface ni matériel :
1. livre absent  → `exercice_sync_error` (erreur IHM déjà utilisée ailleurs
   dans l'application) est émis, PAS `exercice_end_of_line` ; un seul log.
2. livre présent → comportement inchangé (le coup du livre est bien trouvé).
3. vraie fin de ligne théorique (livre présent mais vide pour la position)
   → toujours traitée comme une fin de ligne normale, pas comme une erreur.
"""
import logging
import struct

import chess
import chess.polyglot
import pytest

import nicsoft.modes.exercices.exercices as exercices_mod
from nicsoft.core import ihm_port
from nicsoft.modes.exercices.exercices import ExerciceSession

ENTRY_FMT = ">QHHI"


def _write_polyglot_book(path, entries):
    """entries : liste de (key:int, move:chess.Move, weight:int)."""
    packed = []
    for key, move, weight in entries:
        promotion_part = (move.promotion - 1) if move.promotion else 0
        raw_move = move.to_square | (move.from_square << 6) | (promotion_part << 12)
        packed.append((key, struct.pack(ENTRY_FMT, key, raw_move, weight, 0)))
    packed.sort(key=lambda t: t[0])
    with open(path, "wb") as f:
        for _, data in packed:
            f.write(data)


class _FakeBoard:
    """Double minimal de l'échiquier — seule turn_off_all_leds est appelée
    avant le retour anticipé en cas de livre manquant."""

    def turn_off_all_leds(self):
        pass


class _RecordingBackend(ihm_port._NullBackend):
    """Backend de test — trace tous les send_event()."""

    def __init__(self):
        super().__init__()
        self.events = []

    def send_event(self, event_type, data):
        self.events.append((event_type, data))


OUVERTURE = {"id": "test_ouverture", "nom": "Test", "init": [], "book": ""}


def test_livre_absent_signale_erreur_pas_fin_de_ligne(monkeypatch, tmp_path, caplog):
    livre_absent = tmp_path / "introuvable.bin"
    monkeypatch.setattr(exercices_mod, "BOOK_DEFAULT", livre_absent)

    with caplog.at_level(logging.ERROR, logger="NL exercices"):
        session = ExerciceSession(_FakeBoard(), OUVERTURE, "white", 3)

    assert session._book_missing is True
    # Un seul log d'erreur, au moment de la construction — pas à chaque coup.
    assert sum(1 for r in caplog.records if r.name == "NL exercices") == 1

    backend = _RecordingBackend()
    monkeypatch.setattr(ihm_port, "_backend", backend)

    session.run()

    event_types = [e for e, _ in backend.events]
    assert "exercice_sync_error" in event_types
    assert "exercice_end_of_line" not in event_types

    _, data = next(e for e in backend.events if e[0] == "exercice_sync_error")
    assert data["message_key"] == "exercices.book_missing_msg"
    assert data["show_sync_btn"] is False
    assert str(livre_absent) in data["message"]


def test_livre_present_comportement_inchange(monkeypatch, tmp_path):
    livre = tmp_path / "gm2001.bin"
    board = chess.Board()
    key = chess.polyglot.zobrist_hash(board)
    move = chess.Move.from_uci("e2e4")
    _write_polyglot_book(livre, [(key, move, 10)])
    monkeypatch.setattr(exercices_mod, "BOOK_DEFAULT", livre)

    session = ExerciceSession(_FakeBoard(), OUVERTURE, "white", 3)

    assert session._book_missing is False
    assert session._is_in_book(session.board) is True
    entries = session._get_book_moves(session.board)
    assert [e.move for e in entries] == [move]


def test_vraie_fin_de_ligne_reste_fin_de_ligne(monkeypatch, tmp_path):
    """Livre présent mais sans entrée pour cette position : fin de ligne
    théorique normale, à ne pas confondre avec un livre manquant."""
    livre_vide = tmp_path / "vide.bin"
    _write_polyglot_book(livre_vide, [])
    monkeypatch.setattr(exercices_mod, "BOOK_DEFAULT", livre_vide)

    session = ExerciceSession(_FakeBoard(), OUVERTURE, "white", 3)

    assert session._book_missing is False
    assert session._is_in_book(session.board) is False
