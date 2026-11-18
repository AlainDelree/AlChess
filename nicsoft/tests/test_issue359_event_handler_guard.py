"""
nicsoft/tests/test_issue359_event_handler_guard.py — AlChess

Issue #359 : tout évènement émis par le serveur vers le navigateur
(`send_event(...)`, `emit(...)`, `socketio.emit(...)`) doit avoir un
gestionnaire JS correspondant (`socket.on("...")` ou `socket.once("...")`
dans app.js) — sinon il est ignoré en silence côté client (bugs passés :
bouton « Continuer » des exercices, affichage du coup adverse sans FEN,
cf. ancien historique_bugs.md, trié par #358).

Garde-fou SANS NAVIGATEUR ni matériel (analyse statique du source, sur le
modèle de test_issue303_html_escaping.py). Les quatre violations connues à
la date de #359 (voir CHANGELOG-359.md) ont été corrigées par #360 :
`undo_confirmed`/`undo_impossible`/`undo_wait_position` ont désormais un
gestionnaire JS (message court sur #turn-info, clés i18n fr/en/de) ;
`exercice_turn` n'est plus émis (statut déjà affiché par les évènements
voisins `exercice_wait_position`/`exercice_adv_move`, aucune information
supplémentaire perdue). Liste blanche vide à ce jour. Ce test échoue
désormais si un NOUVEL évènement est émis sans gestionnaire JS.

Ne couvre que les évènements désignés par une chaîne littérale au premier
argument (le cas réel de tout le code actuel) — un nom construit
dynamiquement échapperait à cette analyse statique, comme à toute analyse
de ce type.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NICSOFT_DIR = REPO_ROOT / "nicsoft"
APP_JS = NICSOFT_DIR / "web" / "static" / "app.js"

# Violations connues à la date de l'issue #359, toutes corrigées par #360
# (détail : CHANGELOG-360.md) — liste blanche vide, conservée pour accueillir
# une future violation authentiquement sans usage côté client.
_EVENEMENTS_EN_LISTE_BLANCHE = set()

_EMIT_RE = re.compile(r"(?:send_event|emit)\(\s*\"([a-zA-Z_0-9]+)\"")
_JS_HANDLER_RE = re.compile(r"socket\.(?:on|once)\(\s*[\"']([a-zA-Z_0-9]+)[\"']")


def _evenements_emis_par_python():
    noms = set()
    for path in NICSOFT_DIR.rglob("*.py"):
        if "tests" in path.relative_to(NICSOFT_DIR).parts:
            continue
        src = path.read_text(encoding="utf-8")
        noms.update(_EMIT_RE.findall(src))
    return noms


def _evenements_geres_par_js():
    src = APP_JS.read_text(encoding="utf-8")
    return set(_JS_HANDLER_RE.findall(src))


def test_tout_evenement_emis_a_un_gestionnaire_js():
    emis = _evenements_emis_par_python()
    geres = _evenements_geres_par_js()
    sans_gestionnaire = sorted(
        nom for nom in emis if nom not in geres and nom not in _EVENEMENTS_EN_LISTE_BLANCHE
    )
    assert not sans_gestionnaire, (
        f"Évènement(s) émis côté serveur sans socket.on/socket.once correspondant dans "
        f"app.js : {sans_gestionnaire} — ajouter le gestionnaire JS, ou mettre "
        "l'évènement en liste blanche de ce test avec une raison s'il est "
        "authentiquement sans usage côté client."
    )


def test_liste_blanche_toujours_a_jour():
    """Un évènement de la liste blanche qui a depuis reçu un gestionnaire JS
    (ou qui n'est plus émis) doit en être retiré — sinon la liste blanche
    masquerait une régression future sur ce même évènement."""
    emis = _evenements_emis_par_python()
    geres = _evenements_geres_par_js()
    perimes = [
        nom for nom in _EVENEMENTS_EN_LISTE_BLANCHE
        if nom not in emis or nom in geres
    ]
    assert not perimes, f"Entrées de liste blanche périmées (à retirer) : {perimes}"
