"""
nicsoft/core/game_manager.py — NicLink
Façade des lanceurs de mode, extraits dans nicsoft/core/game_manager_modes/
(issue #278, suite d'ARC-004). Réexporte les mêmes fonctions (mêmes objets)
qu'avant le découpage, pour que nicsoft.web.alchess, nicsoft.web.server et
les tests continuent d'importer depuis nicsoft.core.game_manager sans
changement. Aucune variable d'état n'est réexportée ici : uniquement des
fonctions — voir game_manager_modes/state.py pour l'état partagé
(échiquier courant, mode virtuel) et sa justification.
"""

from nicsoft.core.game_manager_modes.state import get_nl_inst_ref, get_virtual_mode, set_virtual_mode
from nicsoft.core.game_manager_modes.pedagogique import launch_pedagogique, _run_pedagogique
from nicsoft.core.game_manager_modes.humain import launch_humain, _run_humain
from nicsoft.core.game_manager_modes.lichess import launch_lichess, _run_lichess
from nicsoft.core.game_manager_modes.retranscription import launch_retranscription
from nicsoft.core.game_manager_modes.exercices import (
    launch_exercices, start_exercice, start_drill, _run_exercice, _run_drill,
)
from nicsoft.core.game_manager_modes.labo import (
    launch_labo, _poll_board_fen_labo, _make_labo_session,
)
from nicsoft.core.game_manager_modes.labo_session import _run_labo_session, _do_copy_to_board
from nicsoft.core.game_manager_modes.explorer import (
    explorer_get_list, explorer_load, explorer_next, explorer_prev,
    explorer_choose_move, explorer_get_state, explorer_cleanup,
)

__all__ = [
    "get_nl_inst_ref", "get_virtual_mode", "set_virtual_mode",
    "launch_pedagogique", "launch_humain", "launch_lichess", "launch_retranscription",
    "launch_exercices", "start_exercice", "start_drill",
    "launch_labo",
    "explorer_get_list", "explorer_load", "explorer_next", "explorer_prev",
    "explorer_choose_move", "explorer_get_state", "explorer_cleanup",
]
