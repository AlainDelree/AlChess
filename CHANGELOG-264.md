# Changelog — Issue #264

## Suite #263 : correction des régressions du découplage (Humain contre Humain + abandon Pédagogique)

Le test manuel avec échiquier physique a révélé deux régressions introduites
par le découplage nicsoft.web de la #263, non détectées par
`test_no_web_import.py` (qui ne vérifie que l'absence d'import de
`nicsoft.web`, pas que chaque appel migré trouve bien sa cible).

### Régression 1 — mode Humain contre Humain

`nicsoft/core/game_manager.py:320` appelait `web_server.set_history(...)` où
`web_server` est l'alias local de `ihm_port.app_state_proxy`
(`_AppStateProxy`). Cet objet n'expose que `_app_state` et `action_queue`
(façade volontairement limitée à l'ancien accès direct `web_server._app_state`
/ `.action_queue`) — pas `set_history`, qui est une fonction de module de
`ihm_port.py`, pas une méthode du proxy. Résultat : `AttributeError`
immédiatement après la création du plateau virtuel/physique → retour menu,
déconnexion/reconnexion visible côté échiquier.

**Fix** : `game_manager.py` importe désormais `set_history` directement
depuis `nicsoft.core.ihm_port` (même motif que `human.py`, qui l'importait
déjà correctement) et l'appelle sans passer par le proxy.

### Régression 2 — abandon en mode Pédagogique

`nicsoft/modes/pedagogique/pedagogique.py:376` (`Game._end_game`) lisait
`_game_state.get("init", {})`. `_game_state` était un dict interne de
`nicsoft.web.server`, importé localement avant la #263
(`from nicsoft.web.server import set_app_state, _game_state`). L'étape 6/8 de
la #263 a retiré cet import (remplacé par `get_history()` pour la lecture de
l'historique) mais a laissé cette seconde référence orpheline → `NameError:
name '_game_state' is not defined` au clic sur « Abandonner », juste avant
l'envoi de l'état `game_over` → retour menu avec popup d'erreur.

**Fix** : ajout d'un accesseur dédié `get_init_data()` — dans
`nicsoft/web/server.py` (lecture verrouillée de `_game_state["init"]`, miroir
de `get_history()`), exposé par `_WebBackend` (`nicsoft/web/alchess.py`) et
`_NullBackend`/module `nicsoft/core/ihm_port.py`. `pedagogique.py` l'importe
et l'appelle au lieu de lire `_game_state` directement.

### Recensement systématique (point 3 de la demande)

Vérification exhaustive, par analyse statique, de tous les fichiers migrés
par la #263 (`game_manager`, `human`, `pedagogique`, `exercices`, `labo`,
`virtual_board`, `board_adapter`, `retranscription`) :

- **Appels sur l'objet d'interface (`ihm_port`/`app_state_proxy`)** : les deux
  régressions ci-dessus sont les **deux seuls** cas trouvés où un appel migré
  ne correspond à aucun élément réellement fourni par le port ou par le
  proxy. Tous les autres imports depuis `ihm_port` et tous les autres appels
  sur l'alias de `app_state_proxy` (`web_server`/`_web_server`) correspondent
  à un élément réel.
- **Noms non définis (reste de l'ancien `nicsoft.web`)** : `_game_state`
  (régression 2) est le **seul** nom non lié trouvé sur l'ensemble des
  fichiers migrés (vérifié avec `pyflakes` et avec le test
  `test_no_undefined_names.py` ci-dessous).

### Tests ajoutés (point 4)

- `nicsoft/tests/test_ihm_port_contract.py` — analyse statique (ast) : chaque
  nom importé depuis `nicsoft.core.ihm_port` dans les fichiers migrés existe
  réellement dans ce module ; chaque attribut accédé sur l'alias local de
  `app_state_proxy` existe réellement sur `_AppStateProxy` ; `_NullBackend` et
  `_WebBackend` exposent chacun toutes les méthodes utilisées par les
  fonctions de module de `ihm_port.py`.
- `nicsoft/tests/test_no_undefined_names.py` — équivalent restreint de
  pyflakes ("undefined name"), implémenté avec le seul module standard `ast`
  (pas de nouvelle dépendance de test) : pour chaque fichier migré, vérifie
  qu'aucun nom lu n'est totalement non lié dans le fichier.
- `nicsoft/tests/test_humain_startup_virtuel.py` (bonus) — exécute
  `game_manager._run_humain(virtual=True)` avec un plateau virtuel et un
  double léger de `GameWeb`, jusqu'après l'enregistrement de l'historique
  initial via le port — sans matériel ni serveur Flask-SocketIO.

Les trois nouveaux tests ont été vérifiés manuellement contre l'état d'avant
correction (`git stash`) : ils échouent bien sur les deux régressions
(`AttributeError` et `NameError`) et passent après le fix.

### Comportement

Strictement identique à avant la #263 — aucun changement de motif de thread
SocketIO, aucune nouvelle dépendance.

### Vérifications manuelles à refaire avec l'échiquier physique

- Mode Humain contre Humain : lancer une partie, vérifier que l'échiquier
  s'affiche et reste connecté (pas de retour menu / déconnexion-reconnexion).
- Mode Pédagogique : lancer une partie, cliquer sur « Abandonner », vérifier
  qu'aucune popup d'erreur n'apparaît et que l'écran de fin de partie
  (historique, titre) s'affiche normalement avant le retour menu.
