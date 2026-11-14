# Changelog — Issue #326

## Lichess humain : livraison partielle (sécurité des tests + journal de partie dédié)

Tâche beaucoup trop large pour un seul passage (recherche d'adversaire
humain, écran de recherche, événements de partie humaine, reprise des
parties humaines, journal dédié, correctif de sécurité des tests — 10
points). Conformément à la consigne de repli de l'issue, ce passage livre
en priorité le correctif de sécurité critique (point 9, partie) et le
journal de partie dédié (point 10, complet), plus la recherche documentaire
exacte sur les cadences acceptées (point 1). **Aucune recherche
d'adversaire humain, aucun écran de choix IA/humain, aucune reprise de
partie humaine n'a été codé dans ce passage** — voir « Ce qui reste à
faire » ci-dessous.

### Point 9 (partiel, critique) — plus aucun test de navigateur n'appelle le vrai Lichess

- **Cause confirmée par lecture du code et mesure réelle** : `nicsoft/tests/e2e/conftest.py::server_url` pointait `ALCHESS_DIR` directement sur `~/NicLink` (dossier réel d'Alain) pour que les tests non-Lichess disposent des données ECO/livres réelles (non versionnées). Tout test e2e qui ouvrait l'écran de menu Lichess (`sendAction({type:'mode', value:'lichess'})`) déclenchait alors, côté serveur, `check_lichess_resumable()` (`nicsoft/web/alchess.py`) avec le VRAI jeton lu dans `~/NicLink/data/config.json` — un vrai appel à `/api/account/playing` chez Lichess. Confirmé par lecture directe : `~/NicLink/data/config.json` contient bien un jeton réel (`lichess_token` non vide) ; tous les fichiers `test_issue31{0,6}_lichess_e2e.py`, `test_issue32{1,2,3,5}*_e2e.py` ouvrent cet écran. Mesuré avant/après le correctif : `~/NicLink/logs/niclink.log` n'est plus touché par une exécution complète de la suite e2e (horodatage de modification inchangé).
- **Correctif** : `_build_isolated_alchess_dir()` (nouveau, `conftest.py`) construit un `ALCHESS_DIR` isolé par session de tests (`tmp_path_factory`) — liens symboliques en lecture seule vers les données réelles non versionnées dont certains tests non-Lichess ont besoin (ECO, livres, mes_lignes, pgn_library, players.json), mais `data/config.json` et `logs/` toujours neufs. Le `config.json` isolé a `lichess_token=""` explicitement — avec un jeton vide, `check_lichess_resumable()` s'arrête avant tout appel réseau (retour immédiat dans `game_manager_modes/lichess.py`), donc aucun test ne contacte plus jamais le vrai Lichess, avec ou sans jeton.
- **Garde** : `nicsoft/tests/e2e/test_issue326_e2e_isolation_guard.py` (nouveau, 3 tests) — vérifie que `config.json` isolé n'est jamais un lien symbolique et a toujours `lichess_token=""`, que `logs/` démarre vide et n'est jamais le vrai dossier, et que les données ECO réelles restent accessibles pour les autres tests.
- **Vérifié** : suite e2e complète (109 tests) toujours verte après le correctif ; `~/NicLink/logs/niclink.log` et `~/NicLink/data/config.json` non modifiés par l'exécution (horodatages vérifiés avant/après).
- Non traité dans ce point (hors périmètre du bug trouvé) : aucun autre appel réseau réel n'a été détecté dans la suite e2e (aucun test ne déclenche `start_lichess`, `lichess_test_connection` ni `lichess_test_game`) — seul `check_lichess_resumable()` était concerné.

### Point 10 (complet) — journal de partie Lichess dédié

- **Nouveau module `nicsoft/modes/lichess/game_log.py`** (`GameLog`) : un fichier dédié par partie (IA ou futur humain), toujours actif, créé dans `LOGS_DIR/lichess/<horodatage>_<game_id>.log`, en plus de `niclink.log` (inchangé). Chaque ligne est horodatée à la milliseconde et suivie d'un `flush()` immédiat (lisible même après un arrêt brutal du processus — testé en relisant le fichier sans jamais appeler `close()`). Catégories de lignes : `INIT`, `RAW` (lignes brutes du flux Lichess, sauf tchat), `REQUEST` (requêtes envoyées + durée + résultat), `BOARD` (coup/cases/décision), `STATE` (changements d'état, raison des boutons), `CLOCK` (pendules + source), `CONN` (pertes/reprises échiquier et réseau), `EXC` (exceptions avec trace complète), `HEARTBEAT` (ligne de contrôle ~30s). Le jeton n'est jamais écrit : masquage par motif générique (préfixe `lip_` + suite alphanumérique, ou tout en-tête `Bearer ...`) même sans connaître sa valeur, plus masquage littéral si le jeton exact est fourni à la construction. Le tchat n'est jamais écrit : `chat_ignored()` journalise seulement le fait qu'une ligne de tchat est arrivée, jamais son contenu. Rétention : 50 fichiers les plus récents conservés (purge des plus anciens à la création d'un nouveau fichier, jamais pendant une partie en cours).
- **Câblage dans `game_client.py`** : `GameClient` accepte un `game_log` optionnel (`attach_game_log()`) — `_request()` journalise chaque requête ordinaire (méthode, chemin après `/api`, résultat, durée) ; `stream_game()` journalise chaque ligne brute reçue (sauf `chatLine`, redirigée vers `chat_ignored()`) et chaque reconnexion/déconnexion du flux. Rétro-compatible : sans `game_log` (défaut `None`), comportement strictement inchangé — tous les tests existants de `GameClient` passent sans modification.
- **Câblage dans `game.py`** : `LichessGame` crée automatiquement son propre `GameLog` si l'appelant n'en fournit pas (« toujours actif », y compris pour un futur appelant qui l'oublierait) et l'attache au client s'il n'en a pas déjà un. Journalisation ajoutée : coup physique reconnu/promotion/position illégale (`BOARD`), partie démarrée/terminée/boutons actifs-grisés (`STATE`), pendule affichée + sa source — flux Lichess figé, flux + décompte local, ou inconnue (`CLOCK`), perte/reprise de l'échiquier physique avec durée (`CONN`), toute exception du fil principal (`run()`) et du fil de lecture du flux (`_stream_reader_loop`, auparavant silencieux pour une exception imprévue — c'était la lacune la plus utile à combler : avant ce correctif, un bug dans ce fil secondaire mourait sans aucune trace), ligne de contrôle périodique (`_maybe_log_heartbeat()`, appelée à chaque tour de la boucle principale mais ne journalisant réellement qu'au rythme de `HEARTBEAT_INTERVAL_S`).
- **Tests** : `nicsoft/tests/test_issue326_lichess_game_log.py` (nouveau, 14 tests) — création/nommage du fichier, masquage du jeton (littéral et générique), tchat jamais journalisé, lisibilité sans fermeture explicite, horodatage milliseconde, respect de l'intervalle de la ligne de contrôle, purge de rétention, câblage réel `GameClient` (requêtes + lignes brutes + tchat d'une partie scénarisée complète), câblage réel `LichessGame` (coup/boutons/pendule), création automatique si l'appelant n'en fournit pas, exception du fil de lecture journalisée avec sa trace complète.
- **Extrait réel** (partie simulée, voir rapport de clôture pour la méthode) :
  ```
  13:54:51.867 [INIT] Journal de partie Lichess ouvert — game_id=demoGame123
  13:54:51.867 [STATE] Partie démarrée — game_id=demoGame123, niveau=1.
  13:54:51.867 [RAW] {"type": "gameFull", "white": {"id": "alain"}, "black": {"aiLevel": 1}, "state": {"status": "started", "moves": ""}}
  13:54:51.867 [REQUEST] POST /board/game/demoGame123/move/e2e4 -> ok (84 ms)
  13:54:51.867 [BOARD] coup physique reconnu e2e4 — décision : coup envoyé.
  13:54:51.867 [CLOCK] blancs=5400000 noirs=5400000 trait=black source=flux Lichess (figée, avant les deux premiers coups)
  13:54:51.867 [CONN] échiquier perdu — tentatives de reconnexion vont démarrer.
  13:54:51.867 [RAW] (ligne de tchat adverse reçue — ignorée, contenu jamais journalisé)
  ```

### Point 1 (documentation seule, pas de code) — cadences acceptées par la recherche d'adversaire

Vérifié dans le dépôt public `lichess-org/api` (specs OpenAPI, lues le
14/11/2026 via `gh api repos/lichess-org/api/contents/...` — jamais de
connexion au vrai Lichess, seulement à GitHub) :

- `POST /api/board/seek` (`doc/specs/tags/board/api-board-seek.yaml`), scope `board:play`. Partie en temps réel : `time` (minutes, 0 à 180) et `increment` (secondes, 0 à 180) requis, `color` optionnel (vide = ~50% blancs). La réponse reste ouverte (nd-json) jusqu'à adversaire trouvé ou fermeture de la connexion (= annulation de la recherche) — confirme la conception « flux qui reste ouvert, bouton Annuler = fermer la connexion » prévue par l'issue.
- Restriction confirmée au niveau de la fonctionnalité Board entière (`doc/specs/lichess-api.yaml`, tag `Board`) : *« Time controls: Rapid, Classical and Correspondence only. For direct challenges, games vs AI, and bulk pairing, Blitz is also possible. »* — donc **pas de Blitz ni de Bullet pour une recherche d'adversaire humain** (seuls les défis directs et les parties contre l'IA peuvent être en Blitz), conforme à ce que l'issue supposait déjà. Classification officielle (lichess.org/faq#time-controls, formule durée estimée = limite + 40×incrément) : Bullet <3min, Blitz 3-8min, Rapid 8-25min, Classical ≥25min.
- Vérification des préréglages déjà utilisés par `CLOCK_PRESETS` (`core/game_manager_modes/lichess.py`, parties IA) : 10+0 (600s → Rapid), 15+10 (900+40×10=1300s → Rapid), 30+0 (1800s → Classical), 60+0 (3600s → Classical), 90+30 (5400+40×30=6600s → Classical) — **les cinq sont valides pour une recherche humaine**, aucun n'est en Blitz/Bullet. Point d'implémentation à retenir pour la suite : `board/seek` attend `time` en **minutes** (pas en secondes comme `clock.limit` de `challenge/ai`) — conversion `clock_limit_s // 60` nécessaire.
- `POST /api/board/game/{gameId}/claim-victory` existe (`api-board-game-gameId-claim-victory.yaml`) : la réclamation de victoire après déconnexion adverse (point 5) **est implémentable**, pas seulement « à vérifier en réel » comme le redoutait l'issue.
- `POST /api/board/game/{gameId}/takeback/{yes|no}` existe (`api-board-game-gameId-takeback-accept.yaml`) : refuser une proposition de reprise de coup (point 5) se fait en appelant cette route avec `no` — détection côté flux via les champs `wtakeback`/`btakeback` de `GameStateEvent` (même mécanisme que `wdraw`/`bdraw`, déjà utilisé pour la nulle).
- `OpponentGoneEvent` (schéma) confirme le champ `claimWinInSeconds` (délai avant réclamation possible), nécessaire pour l'affichage demandé au point 5.
- Aucune restriction par origine de partie (`source`) trouvée dans la documentation pour `/api/board/game/stream/{gameId}` ni `/api/board/game/{gameId}/move/{move}` — seule la cadence (Rapid/Classique/Correspondance) est restreinte au niveau de la fonctionnalité Board dans son ensemble. Sous réserve de vérification réelle par Alain (règle absolue de cette issue : aucune vraie partie pendant le développement), la reprise d'une partie humaine créée depuis lichess.org (point 6) semble possible par cette même API.

## Ce qui reste à faire (points 1 à 8, hors documentation ci-dessus)

Non codé dans ce passage — taille largement hors de portée d'un seul
passage avec les garanties de test attendues (faux serveur complet,
scénarios d'événements humains, reprise) :

- Écran de choix « contre l'IA » / « contre un humain » avec préréglages de cadence (10+0/15+10/30+0/90+30), couleur, mention « partie amicale uniquement ».
- `create_seek()`/annulation de recherche dans `game_client.py`/`client.py` (flux `board/seek` qui reste ouvert, bouton Annuler = fermeture de connexion, temps écoulé affiché).
- Écran « Recherche d'un adversaire… ».
- Affichage nom/cote de l'adversaire humain (échappé).
- Gestion des événements propres à un adversaire humain : nulle (déjà prévu, à vérifier sans IA), abandon/temps déjà génériques, déconnexion + réclamation de victoire (`claim-victory`, confirmé implémentable ci-dessus), refus automatique de reprise de coup (`takeback/no`), annulation Lichess pour premier coup non joué des DEUX côtés (actuellement seul le cas « utilisateur en retard » est couvert).
- Reprise des parties humaines (actuellement `_RESUMABLE_SOURCE = "ai"` exclut tout le reste) — élargir `get_ongoing_games()`/`LichessGame` pour couvrir les parties humaines en temps réel, y compris celles créées sur lichess.org (sous réserve de la vérification réelle mentionnée ci-dessus).
- Faux serveur Lichess local pour les scénarios humains (recherche, nulle adverse, abandon, temps écoulé, déconnexion, reprise de coup, annulation premier coup, coupure réseau, jeton absent).

## Fichiers modifiés

- `nicsoft/tests/e2e/conftest.py` — `ALCHESS_DIR` isolé par session (`_build_isolated_alchess_dir`), jamais plus le vrai dossier utilisateur.
- `nicsoft/modes/lichess/game_log.py` — nouveau module (`GameLog`).
- `nicsoft/modes/lichess/game_client.py` — `game_log` optionnel, journalisation requêtes/flux/tchat.
- `nicsoft/modes/lichess/game.py` — câblage `GameLog` (coup, boutons, pendule, connectivité, exceptions, ligne de contrôle périodique).
- `nicsoft/tests/e2e/test_issue326_e2e_isolation_guard.py` — nouveau (3 tests).
- `nicsoft/tests/test_issue326_lichess_game_log.py` — nouveau (14 tests).

## Tests exécutés

- `pytest nicsoft/tests/ -q --ignore=nicsoft/tests/e2e` → 1000 passed, 81 skipped.
- `pytest nicsoft/tests/e2e/ -q` (dossier navigateur complet, Playwright) → 109 passed, 1 skipped.
- Vérifié manuellement : `~/NicLink/logs/niclink.log` et `~/NicLink/data/config.json` non modifiés par l'exécution complète de la suite e2e (horodatages comparés avant/après).
