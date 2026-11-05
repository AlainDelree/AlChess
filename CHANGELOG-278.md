# Changelog — Issue #278

## Découpage de game_manager.py en lanceurs par mode (ARC-004)

`nicsoft/core/game_manager.py` (~1180 lignes) orchestrait les sept modes
de jeu dans un seul fichier, avec un état global partagé entre leurs
fonctions. L'audit (règle ARC-004) le signalait comme fichier à
découper ; le rapport le jugeait à risque moyen (couplage à sens unique,
game_manager → modes, jamais l'inverse).

- **Nouveau sous-dossier `nicsoft/core/game_manager_modes/`** (9 fichiers,
  tous nettement sous 300 lignes) :
  - `state.py` (143 l.) — état réellement partagé entre plusieurs modes
    (échiquier courant, mode virtuel) via accesseurs
    (`get_nl_inst_ref`/`set_nl_inst_ref`, `get_virtual_mode`/`set_virtual_mode`),
    plus utilitaires communs (attente de position, toasts d'erreur,
    lecture config moteur).
  - `pedagogique.py` (158 l.), `humain.py` (111 l.),
    `retranscription.py` (45 l.), `exercices.py` (245 l. — exercices et
    drill, avec leur état de session propre : plus exporté nulle part),
    `labo.py` (98 l.) + `labo_session.py` (256 l. — boucle d'actions de la
    session labo, avec le drapeau d'annulation de copie propre à ce
    couple de modules), `labo_libre.py` (140 l.), `explorer.py`
    (139 l. — état de session Opening Explorer propre à ce module).
  - État qui ne servait qu'à un seul mode (session d'exercice/drill, flag
    d'annulation de copie labo, session explorer) rendu local au module de
    ce mode plutôt qu'exporté globalement.
- **`nicsoft/core/game_manager.py` devient une façade** (36 lignes) :
  réexporte les mêmes objets fonctions qu'avant (mêmes noms, y compris les
  privées utilisées par un test — `_run_humain` — et par alchess.py/server.py
  via import local — `_run_exercice`, `_run_drill`, `_make_labo_session`,
  etc.). Aucune variable d'état réaffectable réexportée : uniquement des
  fonctions.
- **Nouvelle fonction d'accès `get_virtual_mode()`** (`state.py`) : remplace
  les deux lectures directes de `gm._virtual_mode` dans
  `nicsoft/web/alchess.py` (handler `set_virtual_mode` du menu), qui
  auraient figé une copie périmée après le découpage puisque la variable
  n'est plus un simple module-global importable en toute sécurité par
  `from ... import`.
- Comportement inchangé : aucun événement envoyé, message de log, ou
  branche d'exception modifiés — seule la répartition du code entre
  fichiers a changé. Les nouveaux modules n'importent toujours jamais
  `nicsoft.web` (ARC-001, vérifié par la suite de tests existante qui
  découvre désormais ces 9 nouveaux fichiers automatiquement : 63 → 73
  fichiers surveillés, 308 → 344 tests passés hors tests matériel, 0 échec).
- Aucun nouveau dossier hors de `nicsoft/core/` : le découpage reste
  entièrement contenu dans `nicsoft/core/game_manager_modes/`.
