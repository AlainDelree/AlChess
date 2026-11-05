"""
nicsoft/core/game_manager_modes/explorer.py — NicLink
Explorateur d'ouvertures (Opening Explorer), extrait de l'ancien
nicsoft/core/game_manager.py (issue #278).

Session unique active à la fois — même pattern que l'échiquier courant
des autres modes. Le plateau (physique ou virtuel) est ouvert à
explorer_load() et refermé à explorer_cleanup() (retour sélecteur ou
retour menu). Cet état est propre à ce mode et ne quitte jamais ce module.
"""

from nicsoft.core.board_adapter import create_board
from nicsoft.core.ihm_port import set_virtual_board
from nicsoft.core.game_manager_modes.state import logger, get_virtual_mode

_explorer_nl_inst = None
_explorer_session = None


def explorer_get_list() -> dict:
    """Construit dynamiquement la liste catalogue + mes_lignes pour le sélecteur."""
    from nicsoft.modes.exercices._catalogue import parse_ouvertures
    from nicsoft.modes.exercices.exercices import get_mes_lignes

    catalogue = [
        {"id": o.get("id", ""), "nom": o.get("nom", ""), "eco": o.get("eco", "")}
        for o in parse_ouvertures()
    ]

    groupes: dict = {}
    for l in get_mes_lignes():
        groupes.setdefault(l.get("nom", ""), []).append(l)

    mes_lignes = []
    for nom, lignes in groupes.items():
        variantes = [
            {
                "id":           l.get("id", ""),
                "nom":          f"{nom} {i}" if len(lignes) > 1 else nom,
                "camp_suggere": l.get("camp_suggere", "white"),
            }
            for i, l in enumerate(lignes, start=1)
        ]
        mes_lignes.append({"groupe": nom, "variantes": variantes})

    return {"catalogue": catalogue, "mes_lignes": mes_lignes}


def explorer_load(source_type: str, opening_id: str, variant_index=None) -> dict:
    """Charge une source (catalogue Polyglot ou ligne perso) dans une nouvelle ExplorerSession."""
    global _explorer_nl_inst, _explorer_session
    from nicsoft.modes.opening_explorer.explorer_session import ExplorerSession
    from nicsoft.modes.opening_explorer.sources import PolyglotSource, PGNLineSource
    from nicsoft.modes.exercices._catalogue import parse_ouvertures, BOOKS_DIR
    from nicsoft.modes.exercices.exercices import get_mes_lignes, BOOK_DEFAULT

    explorer_cleanup()  # referme une éventuelle session/connexion précédente

    if source_type == "pgn":
        entry = next((l for l in get_mes_lignes() if l.get("id") == opening_id), None)
        if entry is None:
            return {"error": "Ligne introuvable."}
        source = PGNLineSource(entry)
    else:
        ouverture = next((o for o in parse_ouvertures() if o.get("id") == opening_id), None)
        if ouverture is None:
            return {"error": "Ouverture introuvable."}
        book_name = ouverture.get("book", "")
        book_candidate = BOOKS_DIR / book_name if book_name else None
        book_path = str(book_candidate if book_candidate and book_candidate.exists() else BOOK_DEFAULT)
        source = PolyglotSource(ouverture, book_path)

    used_virtual = get_virtual_mode()
    try:
        nl_inst = create_board(virtual=used_virtual, logger_name="NicLink_explorer")
    except (Exception, SystemExit) as e:
        logger.info(f"[EXPLORER] Échiquier physique indisponible, bascule en mode virtuel : {e}")
        nl_inst = create_board(virtual=True, logger_name="NicLink_explorer")
        used_virtual = True

    if used_virtual:
        set_virtual_board(nl_inst)
    _explorer_nl_inst = nl_inst

    session = ExplorerSession(nl_inst)
    state = session.load(source, line_id=f"{source_type}_{opening_id}")
    _explorer_session = session

    state["end_of_line"] = not session.has_more()
    state["at_start"]    = session.is_at_start()
    return state


def explorer_next() -> dict:
    if _explorer_session is None:
        return {"error": "Aucune session Opening Explorer active."}
    state = _explorer_session.next_move()
    state["end_of_line"] = not _explorer_session.has_more()
    state["at_start"]    = _explorer_session.is_at_start()
    return state


def explorer_prev() -> dict:
    if _explorer_session is None:
        return {"error": "Aucune session Opening Explorer active."}
    state = _explorer_session.prev_move()
    state["end_of_line"] = not _explorer_session.has_more()
    state["at_start"]    = _explorer_session.is_at_start()
    return state


def explorer_choose_move(uci: str) -> dict:
    if _explorer_session is None:
        return {}
    state = _explorer_session.choose_move(uci)
    state["end_of_line"] = not _explorer_session.has_more()
    state["at_start"]    = _explorer_session.is_at_start()
    return state


def explorer_get_state() -> dict:
    """Retourne l'état courant de la session Opening Explorer active, ou None."""
    if _explorer_session is None:
        return None
    return _explorer_session.get_state()


def explorer_cleanup() -> None:
    """Referme la connexion échiquier de l'Opening Explorer (retour sélecteur/menu)."""
    global _explorer_nl_inst, _explorer_session
    if _explorer_nl_inst is not None:
        try: _explorer_nl_inst.turn_off_all_leds()
        except Exception: pass  # extinction LED best-effort — sans conséquence fonctionnelle
        try: _explorer_nl_inst.disconnect()
        except Exception as e:
            logger.warning(f"[EXPLORER] Déconnexion échiquier échouée : {e}")
    set_virtual_board(None)
    _explorer_nl_inst = None
    _explorer_session  = None
