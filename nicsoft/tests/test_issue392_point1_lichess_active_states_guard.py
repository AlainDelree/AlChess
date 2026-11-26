"""
nicsoft/tests/test_issue392_point1_lichess_active_states_guard.py — AlChess

Issue #392, point 1 (étude #391, point 1) : essai réel du 26/11/2026,
lancement d'une partie classée avec l'échiquier physique en désordre —
retour forcé au menu après 15s avec le message « l'arrêt de la session a
pris trop de temps », alors qu'aucune sortie n'avait été demandée et
qu'aucune partie n'existait encore côté Lichess. Cause : la liste des
états actifs de `_join_lichess_launcher_thread()`
(game_manager_modes/lichess.py::_LICHESS_ACTIVE_STATES) omettait
"position_initiale" et "lichess_wait_first_move" — deux attentes
légitimes, sans aucune limite de durée, posées AVANT même qu'une partie
n'existe (voir _wait_initial_position_lichess/_wait_first_move_white_lichess).

Ce fichier vérifie :
  1. Les deux états manquants sont désormais couverts (jamais abandonnés,
     quelle que soit la durée de l'attente).
  2. Garde statique (pierre angulaire de cette issue) : TOUT état posé par
     un fil de lanceur Lichess (recensé par lecture du code source des
     quatre lanceurs — partie, recherche humaine, reprise, problèmes)
     appartient à _LICHESS_ACTIVE_STATES OU _LICHESS_EXIT_STATES, jamais
     ni l'un ni l'autre — un futur ajout d'état non classé fait échouer ce
     test plutôt que de reproduire silencieusement le bug du 26/11/2026.

Entièrement sans réseau, sans matériel : fils Python nus (comme
test_issue383_point1_stop_timeout.py).
"""
import re
import threading
import time
from pathlib import Path

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fichiers où un fil de lanceur Lichess peut poser _app_state pendant son
# exécution (recensement manuel, voir en-tête) — si un futur fichier en
# pose un nouveau ailleurs, ce test ne le verra pas : à mettre à jour alors.
_SOURCE_FILES = (
    REPO_ROOT / "nicsoft" / "core" / "game_manager_modes" / "lichess.py",
    REPO_ROOT / "nicsoft" / "modes" / "lichess" / "game.py",
    REPO_ROOT / "nicsoft" / "modes" / "lichess" / "puzzle_game.py",
    REPO_ROOT / "nicsoft" / "modes" / "lichess" / "seek.py",
)

_STATE_LITERAL_RE = re.compile(r'(?:set_app_state\(\s*|_app_state\s*=\s*)"([a-z_]+)"')


def _states_posed_in_sources() -> set:
    found = set()
    for path in _SOURCE_FILES:
        src = path.read_text(encoding="utf-8")
        found.update(_STATE_LITERAL_RE.findall(src))
    return found


@pytest.fixture(autouse=True)
def _reset_app_state():
    lichess_launcher.web_server._app_state = "menu"
    yield
    lichess_launcher.web_server._app_state = "menu"


def test_tous_les_etats_poses_sont_classes_actifs_ou_sortie():
    classified = set(lichess_launcher._LICHESS_ACTIVE_STATES) | set(lichess_launcher._LICHESS_EXIT_STATES)
    posed = _states_posed_in_sources()
    unclassified = posed - classified
    assert not unclassified, (
        f"état(s) {sorted(unclassified)} posé(s) par un lanceur Lichess mais jamais classé(s) "
        "actif ni sortie dans _LICHESS_ACTIVE_STATES/_LICHESS_EXIT_STATES — "
        "voir game_manager_modes/lichess.py (issue #392, point 1)"
    )


def test_position_initiale_et_lichess_wait_first_move_sont_actifs():
    assert "position_initiale" in lichess_launcher._LICHESS_ACTIVE_STATES
    assert "lichess_wait_first_move" in lichess_launcher._LICHESS_ACTIVE_STATES


@pytest.mark.parametrize("state", list(lichess_launcher._LICHESS_ACTIVE_STATES))
def test_fil_reste_vivant_longtemps_dans_un_etat_actif_nest_jamais_abandonne(monkeypatch, state):
    """Scénario demandé par l'issue : un fil qui reste vivant longtemps
    dans chacun des états d'attente (dont "position_initiale") n'est
    JAMAIS abandonné ni signalé, même largement au-delà de la borne de la
    phase d'arrêt."""
    monkeypatch.setattr(lichess_launcher, "_LICHESS_STOP_TIMEOUT_S", 0.2)
    lichess_launcher.web_server._app_state = state

    finished = threading.Event()

    def _long_running():
        time.sleep(0.6)  # largement au-delà de la borne de 0.2s ci-dessus
        finished.set()

    t = threading.Thread(target=_long_running, daemon=True)
    t.start()

    completed = lichess_launcher._join_lichess_launcher_thread(t, f"test_etat_{state}")

    assert completed is True, f"fil abandonné à tort pendant l'état actif {state!r}"
    assert finished.is_set()
    assert not t.is_alive()


@pytest.mark.parametrize("state", list(lichess_launcher._LICHESS_EXIT_STATES))
def test_fil_bloque_apres_un_etat_de_sortie_est_borne(monkeypatch, state):
    """Non-régression de #383, point 1 : les états de sortie démarrent
    bien le compte à rebours — sinon ce test deviendrait un faux négatif
    en cas de régression inverse (tout classé "actif" par erreur)."""
    monkeypatch.setattr(lichess_launcher, "_LICHESS_STOP_TIMEOUT_S", 0.2)
    lichess_launcher.web_server._app_state = state

    never_set = threading.Event()
    t = threading.Thread(target=never_set.wait, daemon=True)
    t.start()

    completed = lichess_launcher._join_lichess_launcher_thread(t, f"test_sortie_{state}")

    assert completed is False, f"fil jamais abandonné pendant l'état de sortie {state!r}"
    never_set.set()
    t.join(timeout=2.0)
