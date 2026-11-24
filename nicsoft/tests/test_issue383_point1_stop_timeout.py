"""
nicsoft/tests/test_issue383_point1_stop_timeout.py — AlChess

Issue #383, point 1 : les lanceurs Lichess (recherche humaine, IA, reprise,
problèmes) attendaient la fin de leur fil dédié sans aucune limite
(`t.join()`). Étude #382 : après annulation d'une recherche d'adversaire
humain, le nettoyage ne se terminait jamais (voir point 2, fermeture des
flux) — plus aucune action menu n'était alors traitée, la boucle
d'orchestration (alchess.py) étant bloquée dans ce join().

`_join_lichess_launcher_thread()` (game_manager_modes/lichess.py) borne
désormais seulement la phase d'ARRÊT (après une demande de sortie ou la
fin de la partie) — JAMAIS la partie elle-même, qui peut durer des heures.
Règle absolue de cette issue : aucun réseau réel, aucun accès à
l'échiquier physique — ces deux tests n'utilisent que des fils Python
nus, sans aucune dépendance Lichess/USB.
"""
import inspect
import logging
import re
import threading
import time

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher


@pytest.fixture(autouse=True)
def _reset_app_state():
    lichess_launcher.web_server._app_state = "menu"
    yield
    lichess_launcher.web_server._app_state = "menu"


def test_fil_bloque_apres_sortie_nabandonne_plus_lorchestration(monkeypatch, caplog):
    """(a) Un fil qui ne revient jamais après une demande de sortie ne doit
    plus bloquer indéfiniment l'appelant — il est abandonné (toujours
    daemon=True côté appelant, donc sans effet sur l'arrêt du programme) au
    bout du délai borné, l'état applicatif est remis à "menu", et l'erreur
    est journalisée de façon explicite (nom du lanceur, délai, état)."""
    monkeypatch.setattr(lichess_launcher, "_LICHESS_STOP_TIMEOUT_S", 0.3)

    never_set = threading.Event()
    t = threading.Thread(target=never_set.wait, daemon=True)
    # La sortie a déjà été demandée (back_menu bascule _app_state à "menu"
    # dès le clic, voir server.py::on_action, avant même que ce fil ne
    # termine son nettoyage) — la borne doit donc s'appliquer dès l'appel.
    lichess_launcher.web_server._app_state = "menu"
    t.start()

    t0 = time.monotonic()
    with caplog.at_level(logging.ERROR, logger="niclink.lichess"):
        completed = lichess_launcher._join_lichess_launcher_thread(t, "test_lanceur_bloque")
    elapsed = time.monotonic() - t0

    assert completed is False
    assert elapsed < 2.0, f"l'appelant est resté bloqué {elapsed:.2f}s — la borne n'a pas été respectée"
    assert lichess_launcher.web_server._app_state == "menu"
    assert any(
        "test_lanceur_bloque" in r.message and "abandon" in r.message
        for r in caplog.records
    ), f"aucune erreur explicite journalisée : {[r.message for r in caplog.records]}"
    assert t.is_alive(), "le fil orphelin doit continuer d'exister (daemon) — il n'est jamais tué"

    # Nettoyage : libère le fil orphelin pour ne pas polluer les tests suivants.
    never_set.set()
    t.join(timeout=2.0)


def test_fil_actif_sans_demande_de_sortie_nest_jamais_abandonne(monkeypatch):
    """(b) Un fil de partie qui dure longtemps SANS demande de sortie (état
    applicatif resté actif, ex. "playing") ne doit JAMAIS être abandonné —
    même si sa durée dépasse largement la borne configurée pour la phase
    d'arrêt : cette borne ne s'applique qu'APRÈS la sortie de l'état actif."""
    monkeypatch.setattr(lichess_launcher, "_LICHESS_STOP_TIMEOUT_S", 0.3)
    lichess_launcher.web_server._app_state = "playing"

    finished = threading.Event()

    def _long_running_game():
        # Dépasse largement _LICHESS_STOP_TIMEOUT_S (0.3s) tout en restant
        # dans un état actif pendant toute sa durée — jamais de "menu"/
        # "game_over" avant la toute fin, comme une vraie partie en cours.
        time.sleep(1.0)
        finished.set()

    t = threading.Thread(target=_long_running_game, daemon=True)
    t.start()

    completed = lichess_launcher._join_lichess_launcher_thread(t, "test_partie_longue")

    assert completed is True
    assert finished.is_set(), "le fil a été abandonné avant sa fin naturelle alors qu'aucune sortie n'a été demandée"
    assert not t.is_alive()


def test_les_quatre_lanceurs_restent_tous_daemon():
    """Un fil abandonné ne doit jamais empêcher l'arrêt du programme par
    Ctrl+C/SIGTERM — garanti par `daemon=True` sur chaque Thread() des
    quatre lanceurs (jamais joint sans borne par le reste du programme :
    seul _join_lichess_launcher_thread(), lui-même borné, les attend). Garde
    statique plutôt qu'un test d'arrêt réel du processus (hors de portée
    d'un test unitaire) : relit le source de chaque fonction de lancement
    et vérifie que son seul `threading.Thread(...)` porte `daemon=True`."""
    for fn in (
        lichess_launcher.launch_lichess,
        lichess_launcher._launch_lichess_human,
        lichess_launcher.launch_lichess_resume,
        lichess_launcher.launch_lichess_puzzle,
    ):
        src = inspect.getsource(fn)
        nb_threads = len(re.findall(r"threading\.Thread\(", src))
        assert nb_threads >= 1, f"{fn.__name__} : aucun threading.Thread(...) trouvé"
        nb_daemon = len(re.findall(r"daemon=True", src))
        assert nb_daemon >= nb_threads, (
            f"{fn.__name__} : {nb_threads} Thread(...) mais seulement {nb_daemon} daemon=True "
            "— un fil non-démon pourrait bloquer l'arrêt du programme"
        )
