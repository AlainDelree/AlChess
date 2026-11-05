# Changelog — Issue #263

## Découplage de la logique de jeu : plus d'import de nicsoft.web depuis core/modes/niclink/utils/engine (règle ARC-001)

Recensement complet refait avant correction (l'audit initial, limité à
`nicsoft/modes`, comptait 32 sites) : **34 sites réels** répartis sur 7
fichiers — `nicsoft/core/game_manager.py` (11), `nicsoft/modes/humain/human.py` (7),
`nicsoft/modes/pedagogique/pedagogique.py` (7), `nicsoft/modes/exercices/exercices.py` (5),
`nicsoft/niclink/virtual_board.py` (3), `nicsoft/modes/labo/labo.py` (1),
`nicsoft/core/board_adapter.py` (1). (`nicsoft/utils/debug.py` et
`nicsoft/utils/timing.py` ne mentionnaient `nicsoft.web` que dans un
commentaire/docstring — aucun import réel.) `nicsoft/modes/retranscription/retranscription.py`
était déjà découplé : il reçoit `web_server` en paramètre (injection de
dépendance) plutôt que de l'importer — c'est le motif qui a inspiré la
solution retenue pour les autres fichiers.

**Solution retenue** : un port neutre, **`nicsoft/core/ihm_port.py`**, expose
aux modules de jeu les primitives dont ils ont besoin (`send_event`,
`get_action`, `set_app_state`, `set_virtual_board`, `get_history`/`set_history`,
`get_action_queue`, `get_app_state`/`set_raw_app_state`, `check_board_at_startup`,
`emit`). Tant qu'aucun backend n'est branché (import isolé, tests), un
backend neutre (`_NullBackend`) répond sans effet de bord — permet d'importer
n'importe quel module de jeu sans lancer le serveur web. Au démarrage réel,
`nicsoft/web/alchess.py` branche l'implémentation Flask-SocketIO via
`ihm_port.register_backend()`.

Les très nombreux sites qui accédaient directement au module
`nicsoft.web.server` (`web_server._app_state = ...`, `web_server.action_queue...`)
— notamment dans `game_manager.py` et `human.py`, pour la course critique
SocketIO qui écrit `_app_state` silencieusement avant d'appeler `set_app_state()`
(pour éviter une fenêtre de race pendant la notification navigateur) — n'ont
*pas* été réécrits un par un : `ihm_port.app_state_proxy` reproduit exactement
le même objet dupliqué (property `_app_state` + `action_queue`), ce qui a
permis de ne changer que la ligne d'import sur ces sites et de garder le reste
du code strictement identique. Seul `game_manager.py:304` (import différé de
`nicsoft.web.alchess._check_board_at_startup`, seul cas de cycle réel —
`alchess.py` importe `game_manager` au niveau module) devient
`ihm_port.check_board_at_startup()`.

Migration faite mode par mode, un commit par étape (points de retour arrière) :
port neutre → `niclink/virtual_board.py` → `core/board_adapter.py` →
`modes/labo/labo.py` → `modes/exercices/exercices.py` →
`modes/pedagogique/pedagogique.py` → `modes/humain/human.py` →
`core/game_manager.py` → test d'isolation.

Ajout de `server.emit()` (émission SocketIO directe, hors `event_queue`) pour
couvrir un site (`pedagogique.py`) qui faisait `socketio.emit()` directement
pour un popup ponctuel, sans passer par `send_event()`.

Un site a changé de forme sans changer de résultat : `pedagogique.py` lisait
`_game_state["history"]` directement (sans le verrou), remplacé par
`get_history()[0]`, l'accesseur déjà prévu par `server.py` pour cet usage
précis d'après sa propre docstring ("à utiliser par tout module hors
server.py").

**Résultat** : plus aucun import de `nicsoft.web` depuis `core`, `modes`,
`niclink`, `utils`, `engine` (vérifié par recherche dans le code — seules des
mentions en commentaire/docstring subsistent dans `ihm_port.py`, `debug.py`,
`timing.py`). Comportement strictement identique : mêmes événements, mêmes
files d'actions, mêmes fils d'exécution.

**Fichiers modifiés :**

`nicsoft/core/ihm_port.py` (nouveau), `nicsoft/web/server.py`,
`nicsoft/web/alchess.py`, `nicsoft/niclink/virtual_board.py`,
`nicsoft/core/board_adapter.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/core/game_manager.py`,
`nicsoft/tests/test_no_web_import.py` (nouveau).

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
54 passed, 3 skipped (hardware), dont le nouveau
`test_no_web_import.py` (14 cas, chacun dans un sous-processus Python
propre pour ne pas être pollué par d'autres tests qui importent
`nicsoft.web.server` pour leurs propres besoins). Smoke-test manuel du
serveur réel (`start_server()` + requête HTTP sur `/`) : backend branché,
`_app_state` piloté via le port identique à l'ancien accès direct au
module. Suite e2e non lancée (nécessite Playwright + serveur lancé depuis
`~/NicLink`, hors périmètre du worktree).

**À vérifier manuellement par Alain, avec l'échiquier physique branché**
(aucun hardware disponible dans l'environnement de l'agent) :
- Mode Pédagogique (Stockfish/Maia/Rodent) : coup joué, feedback LED,
  pause sur erreur/blunder, reprise, abandon, fin de partie (mat/nulle),
  notification popup mat/pat.
- Mode Humain vs Humain : coups, undo, abandon, nulle par accord mutuel,
  retour menu depuis un état actif (vérification silencieuse du plateau
  au retour menu).
- Mode Exercices : synchronisation initiale, détection hors-théorie,
  retry/continue, retour menu.
- Mode Labo : suivi du plateau physique, meilleur coup, mode auto,
  analyse, copie de position.
- Déconnexion USB en cours de partie (callback `_board_lost_cb` →
  `board_error`) : le message doit toujours apparaître côté navigateur.
- Démarrage de l'appli complète (`python -m nicsoft.web`) suivi d'un tour
  dans chaque mode, pour confirmer qu'aucune régression de câblage n'est
  passée inaperçue dans l'environnement sans hardware de l'agent.
