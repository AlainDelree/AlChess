"""
Test issues #270 et #271 — livre d'ouvertures introuvable en mode Exercices.

Avant le fix #270 : si le fichier du livre Polyglot n'existe pas (ex. dossier
data/ absent), `_get_book_moves` avalait l'exception et retournait [],
indistinguable d'une vraie fin de ligne théorique — l'IHM annonçait alors
"Ligne terminée ! Bravo" alors que le livre n'avait jamais pu être lu, et
le serveur loggait l'erreur à chaque coup.

Avant le fix #271 (suite de #270) : `run()` émettait bien l'erreur mais
terminait aussitôt (return immédiat) — le lanceur d'exercice
(`game_manager._run_exercice`) voyait alors la session se terminer et
exécutait son nettoyage de fin d'exercice, qui renvoyait aussitôt la liste
des ouvertures : l'écran d'erreur disparaissait en moins d'une seconde.

Ce test vérifie, sans interface ni matériel :
1. livre absent  → `exercice_sync_error` (erreur IHM déjà utilisée ailleurs
   dans l'application) est émis, PAS `exercice_end_of_line` ; un seul log.
2. livre absent  → la session reste en attente d'une action utilisateur
   (pas de retour automatique) puis se termine proprement sur une action
   de retour, sans jamais émettre `exercice_end_of_line`.
3. livre absent  → "recommencer" réaffiche l'erreur (pas de boucle infinie,
   pas de log supplémentaire) puis un retour termine la session normalement.
4. livre présent → comportement inchangé (le coup du livre est bien trouvé).
5. vraie fin de ligne théorique (livre présent mais vide pour la position)
   → toujours traitée comme une fin de ligne normale, pas comme une erreur.
"""
import logging
import queue
import struct
import threading

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
    """Backend de test — trace tous les send_event() et sert les actions
    utilisateur depuis action_queue (comme web/server.py:get_action), pour
    pouvoir piloter _wait_action_end() depuis le test."""

    def __init__(self):
        super().__init__()
        self.events = []

    def send_event(self, event_type, data):
        self.events.append((event_type, data))

    def get_action(self, timeout=0.0):
        try:
            return self.action_queue.get(timeout=timeout)
        except queue.Empty:
            return None


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
    # Simule l'action "retour" déjà en attente — run() ne doit pas bloquer
    # indéfiniment ici, on vérifie juste le contenu de l'erreur émise.
    backend.action_queue.put({"type": "exercice_back"})

    session.run()

    event_types = [e for e, _ in backend.events]
    assert "exercice_sync_error" in event_types
    assert "exercice_end_of_line" not in event_types

    _, data = next(e for e in backend.events if e[0] == "exercice_sync_error")
    assert data["message_key"] == "exercices.book_missing_msg"
    assert data["show_sync_btn"] is False
    assert str(livre_absent) in data["message"]


def test_livre_absent_attend_action_puis_retour_propre(monkeypatch, tmp_path, caplog):
    """Issue #271 : l'erreur ne doit plus disparaître automatiquement — la
    session attend une action utilisateur (comme à la fin normale d'une
    ligne) avant de se terminer, et n'émet jamais de fausse fin de ligne."""
    livre_absent = tmp_path / "introuvable.bin"
    monkeypatch.setattr(exercices_mod, "BOOK_DEFAULT", livre_absent)

    with caplog.at_level(logging.ERROR, logger="NL exercices"):
        session = ExerciceSession(_FakeBoard(), OUVERTURE, "white", 3)

    backend = _RecordingBackend()
    monkeypatch.setattr(ihm_port, "_backend", backend)

    thread = threading.Thread(target=session.run, daemon=True)
    thread.start()
    try:
        # Aucune action fournie : la session doit rester en attente, pas de
        # retour automatique.
        thread.join(timeout=0.3)
        assert thread.is_alive()
        assert session._running is True

        # L'utilisateur choisit de revenir (retour au menu ou choisir une
        # autre ouverture — même mécanisme, même file d'action).
        backend.action_queue.put({"type": "exercice_back"})
        thread.join(timeout=2.0)
        assert not thread.is_alive()
    finally:
        session._running = False
        thread.join(timeout=2.0)

    event_types = [e for e, _ in backend.events]
    assert "exercice_sync_error" in event_types
    assert "exercice_end_of_line" not in event_types
    # Un seul log d'erreur au total, malgré l'attente.
    assert sum(1 for r in caplog.records if r.name == "NL exercices") == 1


def test_livre_absent_recommencer_reaffiche_erreur_sans_boucle(monkeypatch, tmp_path, caplog):
    """"Recommencer" avec un livre toujours manquant doit réafficher
    l'erreur (pas de retour silencieux à la liste), sans boucle infinie ni
    répétition du log, puis se terminer normalement sur un retour."""
    livre_absent = tmp_path / "introuvable.bin"
    monkeypatch.setattr(exercices_mod, "BOOK_DEFAULT", livre_absent)

    with caplog.at_level(logging.ERROR, logger="NL exercices"):
        session = ExerciceSession(_FakeBoard(), OUVERTURE, "white", 3)

    backend = _RecordingBackend()
    monkeypatch.setattr(ihm_port, "_backend", backend)
    backend.action_queue.put({"type": "exercice_retry"})
    backend.action_queue.put({"type": "exercice_back"})

    thread = threading.Thread(target=session.run, daemon=True)
    thread.start()
    thread.join(timeout=2.0)
    assert not thread.is_alive()

    sync_errors = [d for e, d in backend.events if e == "exercice_sync_error"]
    assert len(sync_errors) >= 2
    assert all(d["message_key"] == "exercices.book_missing_msg" for d in sync_errors)
    assert "exercice_end_of_line" not in [e for e, _ in backend.events]
    # Toujours un seul log, malgré le "recommencer".
    assert sum(1 for r in caplog.records if r.name == "NL exercices") == 1


def test_nouvelle_session_apres_restauration_du_livre(monkeypatch, tmp_path, caplog):
    """Issue #273 (suite #271) : après un retour depuis l'erreur "livre
    manquant", une nouvelle session créée une fois le livre restauré ne doit
    signaler aucune erreur et ne doit pas se terminer immédiatement — comme
    quand on revient dans un exercice après avoir remis le livre en place."""
    livre = tmp_path / "gm2001.bin"

    # 1) Session avec livre manquant, sortie par une action de retour.
    with caplog.at_level(logging.ERROR, logger="NL exercices"):
        session1 = ExerciceSession(_FakeBoard(), OUVERTURE, "white", 3)
    assert session1._book_missing is True

    backend = _RecordingBackend()
    monkeypatch.setattr(ihm_port, "_backend", backend)

    thread1 = threading.Thread(target=session1.run, daemon=True)
    thread1.start()
    try:
        thread1.join(timeout=0.3)
        assert thread1.is_alive()
        backend.action_queue.put({"type": "exercice_back"})
        thread1.join(timeout=2.0)
        assert not thread1.is_alive()
    finally:
        session1._running = False
        thread1.join(timeout=2.0)

    # 2) Livre restauré (livre minimal construit pour le test), nouvelle
    # session — comme le fait le lanceur en relançant l'exercice.
    key = chess.polyglot.zobrist_hash(chess.Board())
    move = chess.Move.from_uci("e2e4")
    _write_polyglot_book(livre, [(key, move, 10)])
    monkeypatch.setattr(exercices_mod, "BOOK_DEFAULT", livre)

    session2 = ExerciceSession(_FakeBoard(), OUVERTURE, "white", 3)
    assert session2._book_missing is False

    backend.events.clear()
    thread2 = threading.Thread(target=session2.run, daemon=True)
    thread2.start()
    try:
        thread2.join(timeout=0.3)
        # Ne se termine pas immédiatement : en attente de la synchro initiale.
        assert thread2.is_alive()
        event_types = [e for e, _ in backend.events]
        assert "exercice_sync_error" not in event_types
        assert "exercice_wait_position" in event_types
    finally:
        session2._running = False
        thread2.join(timeout=2.0)


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
