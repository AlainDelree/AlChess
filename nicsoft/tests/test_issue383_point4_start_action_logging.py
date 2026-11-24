"""
nicsoft/tests/test_issue383_point4_start_action_logging.py — AlChess

Issue #383, point 4 : symptôme secondaire NON établi par l'étude #382 — un
clic sur "Démarrer la partie" Lichess n'avait laissé aucune trace dans les
journaux après un redémarrage, et les journaux disponibles ne permettaient
pas de savoir si le clic était arrivé côté serveur ni dans quelle file
(action_queue/menu_queue) il avait fini.

Examen (point 4, sans matériel ni réseau) : `on_action()` (server.py)
route déjà "start_lichess"/"start_lichess_puzzle"/"start_lichess_resume"
vers `menu_queue` dès que `_app_state` vaut "menu" OU "config_lichess" —
les deux seuls états sous lesquels l'écran de configuration Lichess peut
légitimement afficher son bouton "Démarrer la partie" (le changement
d'écran côté navigateur suit l'évènement `app_state` émis par le serveur,
jamais un affichage optimiste local — voir app.js::socket.on("app_state")).
Aucune mauvaise file identifiée pour ce cas précis : les tests ci-dessous
le vérifient explicitement (garde de non-régression), et couvrent aussi le
nouveau log de réception ajouté dans tous les cas, comme demandé par le
point 4, pour qu'un futur blocage soit diagnostiquable sans avoir à
relancer en NICLINK_LOG=DEBUG.
"""
import logging

import pytest
from unittest.mock import patch

import nicsoft.web.server as server


@pytest.fixture(autouse=True)
def clean_state():
    server._app_state = "menu"
    for q in (server.action_queue, server.menu_queue, server.event_queue):
        while not q.empty():
            q.get_nowait()
    yield
    server._app_state = "menu"
    for q in (server.action_queue, server.menu_queue, server.event_queue):
        while not q.empty():
            q.get_nowait()


_START_ACTION_TYPES = ["start_lichess", "start_lichess_puzzle", "start_lichess_resume"]


@pytest.mark.parametrize("atype", _START_ACTION_TYPES)
@pytest.mark.parametrize("etat", ["menu", "config_lichess"])
def test_action_demarrage_depuis_menu_ou_config_lichess_va_dans_menu_queue(atype, etat):
    """Garde de non-régression (point 4) : les deux seuls états sous lesquels
    l'écran de configuration Lichess peut légitimement afficher son bouton
    de démarrage routent bien vers menu_queue, lue par la boucle
    d'orchestration (alchess.py::main()) qui sait traiter ces trois types
    d'action — jamais vers action_queue, où elles seraient ignorées sans
    trace par la boucle de jeu en cours (qui n'en existe d'ailleurs pas à
    ce stade)."""
    server._app_state = etat
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": atype})
    assert server.action_queue.empty(), (
        f"{atype} depuis {etat} a fini dans action_queue — jamais lue par la boucle "
        "d'orchestration, perdue sans trace."
    )
    assert not server.menu_queue.empty()
    assert server.menu_queue.get_nowait()["type"] == atype


@pytest.mark.parametrize("atype", _START_ACTION_TYPES)
@pytest.mark.parametrize("etat", ["playing", "connecting", "game_over", "paused", "labo",
                                   "exercice_running", "retrans_playing", "lichess_puzzle_playing"])
def test_action_demarrage_pendant_une_session_active_va_dans_action_queue(atype, etat):
    """Une partie/session déjà active (état "actif") fait au contraire
    router vers action_queue — comportement voulu (on ne démarre jamais une
    seconde partie par-dessus celle en cours), désormais accompagné du log
    de réception ci-dessous pour que ce cas se distingue clairement d'une
    perte accidentelle dans les journaux."""
    server._app_state = etat
    with patch.object(server.socketio, "emit"):
        server.on_action({"type": atype})
    assert not server.action_queue.empty()
    assert server.menu_queue.empty()


@pytest.mark.parametrize("atype", _START_ACTION_TYPES)
def test_reception_action_demarrage_est_journalisee_avec_etat_et_file(atype, caplog):
    """Point 4 : log dédié systématique à la réception d'une action de
    démarrage Lichess — état de l'application et file choisie, jamais le
    jeton (absent de `data` pour ces trois types d'action)."""
    server._app_state = "config_lichess"
    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        with patch.object(server.socketio, "emit"):
            server.on_action({"type": atype})
    matching = [r for r in caplog.records if atype in r.message and "config_lichess" in r.message]
    assert matching, f"aucun log de réception pour {atype} (état=config_lichess) : {[r.message for r in caplog.records]}"
    assert "menu_queue" in matching[0].message


def test_reception_action_demarrage_pendant_partie_active_journalise_action_queue(caplog):
    server._app_state = "playing"
    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        with patch.object(server.socketio, "emit"):
            server.on_action({"type": "start_lichess"})
    matching = [r for r in caplog.records if "start_lichess" in r.message]
    assert matching
    assert "action_queue" in matching[0].message
    assert "playing" in matching[0].message


def test_action_sans_rapport_avec_lichess_najoute_aucun_log_dedie(caplog):
    """Garde-fou : le nouveau log de réception ne doit concerner QUE les
    trois types d'action de démarrage Lichess — pas une régression qui
    journaliserait toute action du menu dans le logger Lichess."""
    server._app_state = "menu"
    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        with patch.object(server.socketio, "emit"):
            server.on_action({"type": "start_pedagogique"})
    assert not any("action de démarrage reçue" in r.message for r in caplog.records)
