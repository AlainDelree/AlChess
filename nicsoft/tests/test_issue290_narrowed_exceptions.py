"""
nicsoft/tests/test_issue290_narrowed_exceptions.py — NicLink
Issue #290 (suite #288) : revue de tous les resserrements d'exception
de l'issue #288 contre le comportement réel de la bibliothèque/du code
appelé. Couvre les sites où un resserrement ne couvrait pas tout ce qui
peut réellement se produire (hors matériel, hors réseau) :

- `nicsoft/modes/labo/labo.py::LaboSession.quit()` — `turn_off_all_leds()`
  peut lever `ValueError` (course `Queue.task_done()` avec le thread
  `_led_worker_loop`, comme partout ailleurs où cette méthode est
  appelée) ; seul `AttributeError` était couvert.
- `nicsoft/modes/exercices/exercices.py::ExerciceSession._wait_position`
  et `._wait_placement_adv` — l'idiome `raw.strip().split()[0] if raw
  else ""` lève `IndexError` si `raw` est non vide mais composé
  uniquement d'espaces ; seul `(NoNicLinkFen, ValueError)`/`AttributeError`
  étaient couverts (incohérent avec le même idiome dans labo.py, déjà
  corrigé par la #288 avec `(AttributeError, IndexError)`).
- `nicsoft/niclink/hid_backend.py::get_fen()`/`disconnect()` — le binding
  hidapi (`hid.pyx`) lève `ValueError('not open')`, qui n'est PAS une
  sous-classe d'OSError, quand le handle a déjà été fermé par un autre
  thread ; seul `(OSError, IOError)` était couvert.

`nicsoft/modes/humain/human.py::GameWeb._handle_turn.watch_position`
(fermeture imbriquée dans une méthode de ~200 lignes, threads/SocketIO)
utilise le même idiome, corrigé de la même façon, mais n'est pas
exerçable isolément sans reconstruire tout l'environnement de thread —
vérifié par lecture (même motif que labo.py, testé directement
ci-dessous) ; limitation déjà documentée par la #288 pour
`web/launcher.py`.
"""
import queue

import chess
import pytest

from nicsoft.modes.exercices.exercices import ExerciceSession


def _make_bare_exercice_session() -> ExerciceSession:
    """ExerciceSession sans __init__ (pas de livre Polyglot à charger)."""
    session = ExerciceSession.__new__(ExerciceSession)
    session.board = chess.Board()
    return session


class _FakeNlLedsRace:
    """nl_inst dont turn_off_all_leds() lève ValueError, comme le ferait
    le driver réel en cas de course avec _led_worker_loop sur la queue LED."""

    def turn_off_all_leds(self):
        raise ValueError("task_done() called too many times")


class _FakeEngineOk:
    def quit(self):
        pass


# ── labo.py::LaboSession.quit() — turn_off_all_leds() ValueError absorbée ──

def test_labo_quit_absorbe_value_error_de_turn_off_all_leds():
    from nicsoft.modes.labo.labo import LaboSession

    session = LaboSession.__new__(LaboSession)
    session.engine = _FakeEngineOk()
    session.nl_inst = _FakeNlLedsRace()
    session.quit()  # ne doit pas lever


# ── exercices.py::_wait_position — IndexError absorbée (FEN blanc ESPACE) ──

class _FakeNlGetFenBlanc:
    def get_fen(self):
        return "   "  # non vide, mais .strip().split() == []


def test_wait_position_absorbe_indexerror_sur_fen_blanc():
    session = _make_bare_exercice_session()
    session._running = False  # pas de boucle principale : seul le bloc initial est exercé
    session.nl_inst = _FakeNlGetFenBlanc()
    assert session._wait_position("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR") is False


# ── exercices.py::_wait_placement_adv — IndexError absorbée (current_fen blanc) ──

class _FakeNlCurrentFenBlanc:
    current_fen = "   "


def test_wait_placement_adv_absorbe_indexerror_sur_current_fen_blanc(monkeypatch):
    import nicsoft.modes.exercices.exercices as exercices_module

    session = _make_bare_exercice_session()
    session._running = True
    session.nl_inst = _FakeNlCurrentFenBlanc()

    def _stop_apres_une_iteration(_):
        session._running = False

    monkeypatch.setattr(exercices_module.time, "sleep", _stop_apres_une_iteration)
    assert session._wait_placement_adv("e2e4") is False
