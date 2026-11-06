"""
nicsoft/tests/test_family_a_narrowed_exceptions.py — NicLink
Vérifie que le comportement est conservé quand l'exception réellement
attendue se produit, pour les sites de l'audit sécurité (issue #288,
famille A) où un `except Exception` générique a été resserré en
exception(s) précise(s) — plutôt que deviné, ces types ont été identifiés
en lisant le code source réel appelé à chaque site (nicsoft/niclink/driver.py,
module stdlib `queue`). Aucun accès réseau ni matériel : `NicLinkManager`
est instancié sans passer par `__init__` (qui exige un échiquier connecté),
seul le `_led_queue` nécessaire aux méthodes testées est posé à la main.
"""
import queue

import pytest

from nicsoft.niclink.driver import NicLinkManager, build_led_map_for_move, square_cords


def _make_bare_manager() -> NicLinkManager:
    """Instance de NicLinkManager sans __init__ (donc sans connexion USB),
    juste assez construite pour exercer set_led()/turn_off_all_leds()."""
    nl = NicLinkManager.__new__(NicLinkManager)
    nl._led_queue = queue.Queue()
    return nl


# ── human.py:216 / human.py:737 — `except (ValueError, IndexError): pass` ──
# autour de nl_inst.set_led(square, ...)

def test_set_led_case_invalide_leve_bien_value_error():
    nl = _make_bare_manager()
    with pytest.raises(ValueError):
        nl.set_led("z9", True)  # colonne hors a-h


def test_set_led_case_trop_courte_leve_bien_index_error():
    nl = _make_bare_manager()
    with pytest.raises(IndexError):
        nl.set_led("a", True)  # pas de numéro de rangée


def test_set_led_case_valide_ne_leve_rien_et_poste_sur_la_queue():
    nl = _make_bare_manager()
    nl.set_led("e4", True)  # ne doit pas lever — comportement conservé
    assert nl._led_queue.get_nowait()[0] == "set_led"


# ── human.py:933 — `except (ValueError, IndexError): pass` autour de
# nl_inst.set_move_leds(bm), qui délègue à build_led_map_for_move/square_cords

def test_square_cords_case_invalide_leve_value_error():
    with pytest.raises(ValueError):
        square_cords("j1")


def test_build_led_map_for_move_case_invalide_leve_value_error():
    with pytest.raises(ValueError):
        build_led_map_for_move("j1e4")


def test_build_led_map_for_move_coup_valide_ne_leve_rien():
    led_map = build_led_map_for_move("e2e4")  # ne doit pas lever
    assert led_map.shape == (8,)


# ── core/game_manager_modes/*.py, modes/labo/labo.py, web/alchess.py —
# `except ValueError: pass` autour de nl_inst.turn_off_all_leds(), qui peut
# lever ValueError via Queue.task_done() en cas de course avec le thread
# _led_worker_loop qui consomme la même queue (comportement documenté par
# la stdlib : « raises ValueError if called more times than there were
# items placed in the queue »).

def test_queue_task_done_appele_en_trop_leve_value_error():
    q = queue.Queue()
    with pytest.raises(ValueError):
        q.task_done()  # aucun item jamais retiré — comportement conservé


def test_turn_off_all_leds_vide_la_queue_et_poste_lights_out():
    nl = _make_bare_manager()
    nl._led_queue.put(("set_led", 0, 0, True))
    nl.turn_off_all_leds()  # ne doit pas lever en usage normal
    assert nl._led_queue.get_nowait() == ("lights_out",)
