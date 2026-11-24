# Changelog — Issue #383

## Annulation d'une recherche Lichess : ne plus bloquer l'application

Suite de l'étude #382 (incident réel : AlChess resté bloqué ~30s après l'annulation d'une recherche Lichess contre un humain classée — journaux arrêtés net après « recherche d'adversaire annulée par l'utilisateur », boutons « Annuler la recherche » / « Retour menu principal » envoyant le même geste). Quatre points, un commit par point.

### Point 1 — Attente bornée de l'arrêt des fils de partie Lichess (`fix(383)`, 7a4983d, repris tel quel de la tentative précédente — vérifié, inchangé)

`_join_lichess_launcher_thread()` (`game_manager_modes/lichess.py`) ne borne **jamais** la partie elle-même (peut durer des heures, tant que `_app_state` reste dans un état actif — `connecting`/`lichess_seeking`/`playing`/`paused`/`lichess_puzzle_playing`) : la borne (15s, `_LICHESS_STOP_TIMEOUT_S`) ne démarre qu'à l'instant où l'état quitte ces valeurs (sortie demandée ou fin de partie). Au-delà : erreur journalisée (lanceur, durée, état), fil abandonné (toujours `daemon=True` — sans effet sur Ctrl+C/SIGTERM), état forcé à `menu`, référence échiquier effacée, toast persistant. Valeur 15s justifiée par la seule mesure réelle disponible (poignée de main USB 2,2s + libération, <5s, essai du 13/11/2026, issue #319) multipliée par une marge large pour couvrir aussi la fermeture des flux réseau (point 2). Tests : `test_issue383_point1_stop_timeout.py`.

### Point 2 — Fermeture fiable des flux (`fix(383)`, déjà présent dans le commit de sauvegarde 02aa626 — vérifié, aucune modification nécessaire)

`StreamHandle.close()` (`modes/lichess/transport.py`) coupe désormais la connexion TCP sous-jacente (`socket.shutdown(SHUT_RDWR)`, jamais d'exception — best-effort) **avant** la fermeture habituelle (`response.close()`) : un `close()` seul, appelé depuis un autre fil pendant une lecture bloquante dans `lines()`, ne réveillait pas toujours ce fil (verrou interne de tampon `io.BufferedReader` partagé) et pouvait même bloquer `close()` lui-même. Identique Linux/Windows (API Winsock). Testé sans réseau extérieur (serveur HTTP local silencieux) : lecteur libéré dans un délai borné. Garde ajoutée : « Annuler la recherche » et « Retour au menu principal » envoient le même `data-action="back_menu"`. Tests : `test_issue383_point2_stream_close.py`.

### Point 3 — Partie orpheline après annulation (`fix(383)`, 447c612)

Course structurelle dans `seek.py::SeekSession` : `_mark_found()` (fil de lecture du flux d'évènements) ne dépend jamais de `_cancelled` — si ce fil a déjà lu `gameStart` au moment où le fil principal traite un retour au menu, `cancel()` devient un no-op et l'évènement `"found"` reste dans la file sans jamais être consommé (risque établi par lecture du code, non reproduit). `_cancel_seek_and_reap_orphan()` (nouveau, appelé aux deux points de sortie "menu" de `_run_lichess_human`) draine la file pendant une fenêtre bornée (1s) après `cancel()` ; un `"found"` tardif déclenche `_abandon_orphan_game_after_cancel()` (`abort()`, repli `resign()` — même principe "moins de 2 coups" que `abandon_lichess_game`, #325). Tests (doublures, aucun réseau réel) : `test_issue383_point3_orphan_game.py` — helpers isolés + bout en bout avec un double de `SeekSession` reproduisant la course de façon déterministe, et garde de non-régression (annulation normale → aucun `abort()`/`resign()`).

### Point 4 — Visibilité du symptôme secondaire (`diag(383)`, 7c72aca)

Examen (sans matériel ni réseau) : `on_action()` route déjà `start_lichess`/`start_lichess_puzzle`/`start_lichess_resume` vers `menu_queue` dès que `_app_state` vaut `menu` ou `config_lichess` — les deux seuls états sous lesquels l'écran de configuration Lichess peut légitimement afficher son bouton de démarrage (changement d'écran côté navigateur piloté par l'évènement `app_state` du serveur, jamais un affichage optimiste local). **Aucune mauvaise file identifiée** pour ce cas précis — vérifié par test de non-régression explicite (`test_issue383_point4_start_action_logging.py`).

Ajouté dans tous les cas (comme demandé) pour qu'un futur blocage soit diagnostiquable sans `NICLINK_LOG=DEBUG` :
- `on_action()` (server.py) journalise systématiquement (logger `niclink.lichess`, INFO) la réception de ces trois types d'action — état applicatif et file choisie — jamais le jeton (absent de ces actions) ;
- chaque lanceur Lichess (`launch_lichess`, `_launch_lichess_human`, `launch_lichess_resume`, `launch_lichess_puzzle`) journalise désormais son entrée de façon inconditionnelle, avant tout garde d'état.

`_ACTIVE_GAME_STATES` factorisé dans server.py (jusqu'ici dupliqué deux fois dans `on_action`, nécessaire de toute façon pour le nouveau log).

### Documentation (`docs(383)`, 0ab1d7a)

`docs/contexte/lichess.md` : règle d'arrêt borné (15s, jamais pendant une partie), fermeture fiable des flux (`socket.shutdown` avant `close()`), partie orpheline annulée côté Lichess.

### Vérification

- Suite complète `-m "not hardware"` : verte deux fois de suite, **1841 passed, 86 skipped, 1 deselected** (contre la référence 1788/86/1 avant cette issue — 14 tests déjà présents dans le worktree repris (points 1+2) + 42 nouveaux (points 3+4)).
- Tests de concurrence (points 1/2/3) : 10 passages consécutifs sans échec, dont 3 sous charge CPU (4 processus de calcul en continu en parallèle) — aucune instabilité observée.
- Garde fair-play (`test_issue333_lichess_no_engine.py`) et parité i18n : vertes, non affectées (aucune nouvelle clé i18n introduite par cette issue).

### Vérification manuelle restant à faire par Alain (échiquier réel)

Lancer une recherche de partie humaine classée, l'annuler après ~30s avec « Annuler la recherche », répéter 3 fois — à chaque fois l'écran Lichess doit pouvoir être rouvert et une nouvelle recherche doit démarrer ; aucune partie ne doit apparaître sur le profil Lichess.
