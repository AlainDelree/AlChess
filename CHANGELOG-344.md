# Changelog — issue #344

## Lichess L4 : parties classées contre un humain, humain présélectionné, signal de début, finitions

Étape suivante du mode Lichess (après #327/#333, recherche d'adversaire humain) : les parties classées, transmises de bout en bout jusqu'à Lichess, affichées clairement pendant et après la partie, accompagnées d'un signal physique de début de partie et d'un journal enrichi — sans jamais ouvrir de vraie recherche/partie sur lichess.org pendant le développement (faux serveur local uniquement, comme pour toutes les issues Lichess précédentes).

### 1. Écran de choix (point 1)

`nicsoft/web/templates/index.html` / `nicsoft/web/static/app.js` :

- « Contre un humain » (`#cfg-lichess-opponent-human`) est désormais présélectionné à l'ouverture de l'écran — `app.js::_lichessOpponentType` vaut `"human"` par défaut, et `selectOpponentTypeLichess("human")` est réaffirmé explicitement à **chaque** entrée sur `config_lichess` (pas seulement au premier chargement de la page), pour ne jamais hériter d'un état laissé par une session précédente.
- Nouvelle case « Partie classée » (`#cfg-lichess-rated`), cochée par défaut (`_lichessRated = true`), dans la carte « Adversaire ». Sans objet contre l'IA : masquée et désactivée (`disabled`) dès qu'on bascule sur « Contre l'IA » (`#cfg-lichess-rated-row`), rétablie cochée et visible dès qu'on revient sur « Contre un humain ».
- L'ancienne légende « Partie amicale seulement pour l'instant — les parties classées viendront plus tard » (contre un humain) est remplacée par une légende symétrique, affichée contre l'IA : « Contre l'IA : toujours une partie amicale, Lichess ne classe pas les parties contre son ordinateur » (`#cfg-lichess-opponent-ai-note`).
- Disclaimer de l'écran (aides désactivées) reformulé pour ne plus affirmer « sans classement » (qui n'est plus vrai).
- Clés i18n ajoutées/modifiées simultanément dans `fr/en/de.json` : `config.lichess.classee`, `config.lichess.ia_jamais_classee`, `lichess.badge_classee`, `lichess.badge_amicale` (ajoutées) ; `config.lichess.disclaimer`, `config.titre.lichess` (reformulées — ce dernier servait aussi de titre en cours de partie, affichait à tort « partie amicale ») ; `config.lichess.rated_plus_tard` retirée (plus utilisée).

### 2. Recherche d'adversaire classée (point 2)

- `nicsoft/modes/lichess/game_client.py::open_seek_stream()` acceptait déjà un paramètre `rated` (issue #327) mais rien ne l'alimentait jamais — désormais câblé de bout en bout : `app.js::startGameLichess()` envoie `rated` dans l'action `start_lichess` (toujours `false` si l'IA est sélectionnée, quel que soit l'état mémorisé de la case, qui est alors masquée) → `core/game_manager_modes/lichess.py::launch_lichess()`/`_launch_lichess_human()`/`_run_lichess_human()` → `nicsoft/modes/lichess/seek.py::SeekSession.start(..., rated)` → `open_seek_stream(..., rated)`.
- Défaut prudent côté serveur si le champ venait à manquer (`bool(config.get("rated", False))`) : jamais une partie classée involontaire.
- Lecture de la documentation publique (`lichess-org/api`, `doc/specs/tags/board/api-board-seek.yaml`, 15/11/2026) : `rated` est un simple booléen, indépendant des contraintes de cadence — aucune restriction de cote documentée pour cette route. Les cadences proposées restent donc celles déjà filtrées par #327 (`_HUMAN_SEEK_ALLOWED_SPEEDS = {"rapid", "classical"}`, jamais Blitz/Bullet) — inchangées, déjà correctes pour une recherche classée comme amicale.
- Un refus de Lichess (400 et autres codes) reste géré par le mécanisme générique déjà en place depuis #329 (`_classify_seek_error_event`, message exact affiché de façon persistante, jamais de plantage) — aucune branche spécifique au classé n'était nécessaire.

### 3. Affichage classée/amicale + variation de cote (point 3)

- `LichessGame.rated` (nouvel attribut, `nicsoft/modes/lichess/game.py`) est **toujours** lu depuis le champ `rated` (booléen requis du schéma `GameFullEvent`) du premier `gameFull` confirmé par Lichess — jamais deviné localement, y compris pour une IA (toujours `False`, Lichess ne l'envoie jamais à `true` pour une partie contre son ordinateur) et y compris après une reconnexion réseau mi-partie (un nouveau `gameFull` peut revenir, relu sans effet de bord).
- Transmis dans l'évènement `lichess_init` (écran de jeu) et dans le payload `game_over` (écran de fin) — affiché via les nouvelles clés `lichess.badge_classee`/`lichess.badge_amicale`, en suffixe du sous-titre de partie et dans un nouveau bloc dédié `#rv-lichess-rated-info` sur l'écran de fin.
- Variation de cote (en meilleur effort, jamais inventée si absente) : nouvelle méthode `GameClient.fetch_rating_diff(game_id)` — ouvre brièvement le flux général `/api/stream/event` (le seul à porter `ratingDiff`, établi par lecture de `doc/specs/examples/stream-gameFinish.json.yaml` ; le flux de partie lui-même, `GameStateEvent`, ne le porte jamais) en attendant l'évènement `gameFinish` correspondant, avec un délai de 6s imposé depuis un **autre** fil (`threading.Timer(..., handle.close)`, même mécanisme que l'annulation de recherche de #327/#328) ; ne lève jamais d'exception (toute exception imprévue est journalisée, jamais laissée se propager dans le fil secondaire — même garde-fou que `seek.py`). Appelée par `LichessGame._maybe_fetch_rating_diff()`, démarrée par `_finalize()` **seulement** si la partie est classée et réellement terminée (jamais pour `aborted`/`noStart`) ; pousse `lichess_rating_diff` si trouvée à temps, sinon rien n'est affiché au-delà du résultat déjà connu.
- Tout nom d'adversaire et tout message venant de Lichess continue de passer par `esc()`/`.textContent`, inchangé.

### 3 bis. Signal de début de partie (point 3bis)

- Nouvelle méthode `LichessGame._signal_game_start()` : bip + LED distincts des signaux existants (#331/#340 « adversaire parti ») — nouveau pattern LED dédié (`driver.py::signal_lights(7)`, échiquier entièrement allumé ~1,5s, jamais réutilisé par aucun autre signal), posté sur la même file LED ordonnée que le reste (un seul fil travailleur, `driver.py::_led_worker_loop`) pour ne jamais courir en parallèle de l'affichage normal du premier coup adverse qui peut suivre immédiatement (cas des noirs) — posté **avant** `_apply_new_moves()` dans `_apply_game_full()`, pour que cet éventuel affichage attende son tour plutôt que d'être effacé prématurément.
- Déclenché une seule fois par vraie partie (`_game_start_signal_sent`), jamais à une reprise (`_resume_pending`) ni répété si un nouveau `gameFull` revient (reconnexion réseau mi-partie).
- Valable pour toute partie Lichess (IA ou humain, classée ou amicale) : pour les Blancs, rien d'autre ne s'affiche avant leur propre premier coup (« à vous de jouer ») ; pour les Noirs, le premier coup adverse est ensuite montré normalement par les LED, comme d'habitude.
- Journalisé (`game_log.state_change`, catégorie `[STATE]`).
- Non testé sur le vrai échiquier (aucun matériel disponible pour cette issue) : pattern LED choisi par cohérence avec les conventions existantes du fichier, jamais vérifié visuellement en conditions réelles.

### 4. Reprise et cas rares (point 4)

- Reprise (L2b) d'une partie classée : aucune adaptation nécessaire — `LichessGame.rated` est lu depuis le `gameFull` de la même façon qu'une partie normale, y compris à la reprise ; le signal de début de partie reste bien absent (`resuming=True`). Vérifié par test dédié.
- Cas rares passés en revue sur le faux serveur local, avec `rated=True` (aucune correction nécessaire — comportement identique à l'amicale, seuls l'affichage et le journal changent avec le classé) :
  - adversaire qui quitte la partie puis réclamation (bip/LED #331/#334/#340, inchangés) ;
  - proposition de nulle refusée (mécanisme #311/#318, inchangé) ;
  - demande de reprise de coup refusée (mécanisme #334, inchangé) ;
  - fin par temps écoulé (statut `outoftime`, inchangé) ;
  - abandon — de l'adversaire et de l'utilisateur lui-même (mécanismes #310/#311/#331, inchangés) ;
  - partie interrompue avant le premier coup (`aborted`, bandeau dédié #311, inchangé) ;
  - déconnexion réseau puis reconnexion mi-partie (flux général, #309/#328) — vérifié en particulier que le signal de début de partie ne se répète pas si un nouveau `gameFull` revient à la reconnexion.
- Aucun de ces cas n'a révélé de comportement incorrect ou de message peu clair spécifique au classé — la seule différence réelle entre classée et amicale est l'affichage (badge, variation de cote) et le journal.

### 5. Journal (point 5)

- `classée=True/False` ajouté aux lignes `[STATE]` de démarrage de recherche (`seek.py::start()`, avec cadence et couleur déjà présents) et de réception du `gameFull` (`game.py::_apply_game_full()`, avec couleur/adversaire/cote déjà présents) — horodatage à la milliseconde déjà garanti par `GameLog` (#326).
- Nouvelle ligne dédiée à l'émission du signal de début de partie.
- Nouvelles lignes pour la tentative (réussie ou non) de lecture de la variation de cote.
- Le jeton n'apparaît jamais dans ces nouvelles lignes (même masquage générique déjà en place, `GameLog._mask`) — vérifié par test dédié.

### 6. Garde-fous inchangés (point 6)

- Aucun moteur, aucun livre d'ouvertures, aucun indice de coup pendant une partie en ligne, classée comme amicale — inchangé (`nicsoft.engine.*` jamais importé par le mode Lichess, #333). Le jeton reste côté serveur, jamais envoyé au navigateur ni journalisé — inchangé.
- Tests existants sur ce point (`test_issue333_lichess_no_engine.py`, analyse statique AST) : toujours verts, sans modification.
- Nouveau test **dynamique** complémentaire (`test_issue344_lichess_rated.py::test_partie_classee_complete_n_importe_jamais_de_moteur`) : fait tourner un cycle complet de partie **classée** (mise en place, coups, fin) et vérifie, par comparaison avant/après de `sys.modules`, qu'aucun module moteur n'est chargé par ce scénario précis — en complément du test statique, qui couvre tous les fichiers mais ne fait jamais tourner de vrai code.

### 7. Tests (point 7)

- `nicsoft/tests/test_issue344_lichess_rated.py` (31 tests, hors réseau/matériel) : recherche classée/amicale (`rated` transmis à `open_seek_stream`/`SeekSession.start`), `LichessGame.rated` lu depuis `gameFull` (jamais deviné, y compris IA/absence du champ), payload `game_over`, signal de début de partie (Blancs, Noirs, absent à la reprise, jamais répété à une reconnexion, pour classée comme amicale), variation de cote (trouvée, absente, erreur réseau, déclenchée seulement si classée et terminée), cas rares du point 4 rejoués avec `rated=True`, journal (classée visible, jeton absent), garde-fou fair-play dynamique.
- `nicsoft/tests/e2e/test_issue344_lichess_rated_e2e.py` (6 tests, Playwright) : humain présélectionné, case classée cochée et visible par défaut, niveau IA masqué par défaut, case classée masquée/désactivée contre l'IA, case rétablie cochée en revenant sur « Contre un humain », légende « toujours amicale » affichée contre l'IA.
- Corrections de tests préexistants rendues nécessaires par le nouveau signal de début de partie (bip supplémentaire désormais émis dès `_apply_game_full`) : `test_issue311_lichess_sequencing.py` (2 assertions de comptage de bips ajustées, commentées), `test_issue331_lichess_opponent_alerts.py::_started()` (remet `beep_count` à zéro après la mise en place, pour que les tests existants continuent de ne mesurer QUE les bips survenant après leur propre scénario — corrige au passage toute la famille #331/#334/#340, qui réutilise cette fonction). Et `test_issue310_lichess_e2e.py::at_config_lichess` (bascule explicitement sur « Contre l'IA » pour retrouver l'état visé par ses tests de mise en page, orthogonal au nouveau défaut « Contre un humain » de cette issue).
- Suite complète (`pytest nicsoft/tests/`) : 1478 passés, 84 ignorés (pré-existants, sans rapport), 0 échec.

### Ce qu'Alain doit vérifier en vrai

- **Premier essai réel recommandé : partie classée contre un humain en Rapide** (cadence 15+10 ou 10+0, jamais Blitz/Bullet). Vérifier : la case « Partie classée » est bien cochée par défaut à l'ouverture de l'écran ; la recherche aboutit normalement ; l'écran de jeu affiche bien « Partie classée » ; à la fin, le résultat s'affiche avec le badge « Partie classée », et la variation de cote si Lichess la fournit à temps (sinon, rien d'anormal ne doit apparaître — juste le résultat).
- **Signal de début de partie** : au moment où l'appariement est fait et que la partie démarre, vérifier qu'un bip et un pattern LED (échiquier entièrement allumé un court instant) se produisent — distincts des signaux déjà connus (adversaire parti). Pour les Noirs, vérifier que le premier coup de l'adversaire s'affiche bien normalement ensuite (pas de conflit visuel avec le signal).
- **Reprise d'une partie classée en cours** (fermer/relancer AlChess pendant une partie classée) : vérifier que la reprise fonctionne normalement et que le signal de début de partie ne se répète pas.
- Pattern LED du signal de début de partie non vérifié sur le vrai échiquier (aucun matériel disponible pendant cette issue) — à confirmer visuellement lors du premier essai.
- Variation de cote : son délai d'arrivée réel après la fin d'une partie classée n'a pas pu être mesuré sans vraie partie — si elle n'apparaît jamais en pratique, envisager d'augmenter le délai de 6s dans `GameClient.fetch_rating_diff()`.
