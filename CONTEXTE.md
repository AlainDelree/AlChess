# AlChess — Contexte projet

Briefing CCL. Seuls les ~4000 premiers caractères sont injectés dans ton prompt ; le reste du fichier reste lisible à la demande (outil de lecture) : garde l'essentiel en haut, le détail plus bas.

## Règles impératives
Elles te sont injectées automatiquement, avec ton prompt, dans la section CONSIGNES (binaires tiers en lecture seule, serveur démarré uniquement avec `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`, suppressions de sécurité, pas de push). Ici : si ta tâche change l'architecture, les dépendances, les conventions ou l'avancement, mets à jour ce fichier dans le même commit — l'état réel, pas l'historique (l'historique va dans `CHANGELOG-<N>.md`).

## Projet
**AlChess** (ex-NicLink) : app Python/Flask-SocketIO reliant un échiquier Chessnut USB (ou virtuel) à une UI web pédagogique. Front vanilla JS. Ubuntu + support Windows. Local `~/NicLink/` (venv) ; GitHub public AlainDelree/AlChess. Dév : Alain (non-dev).

## Architecture (`nicsoft/`)
- `niclink/` : `hid_backend.py` (USB hidapi pur), `driver.py` (thread FEN, LEDs, bip), `virtual_board.py`, `nl_exceptions.py`.
- `web/` : `alchess.py` (orchestre), `server.py` (Flask-SocketIO, `_app_state`, détection moteurs), `single_instance.py` (une seule instance à la fois, #320), `launcher.py`, `static/app.js`, `templates/index.html`.
- `core/` : `game_manager.py` (façade ; lanceurs par mode dans `core/game_manager_modes/`, état partagé dans `state.py`), `board_adapter.py`, `config_manager.py`, `ihm_port.py` (port neutre jeu↔IHM).
- `engine/` : `engine_manager` (façade réexportant `move_quality`, `engine_analysis`, `uci_engine`, `engine_detection`, `engine_availability`, `maia_engine`, `rodent_engine`), `players`, `pgn_manager`, `board_utils`, `display`, `analyse`.
- `modes/` (`pedagogique humain exercices retranscription labo opening_explorer`) : `explore_book`, `eco_import`, `llm_explainer` sont des façades réexportant des modules par rôle.
- `config.py` (`APP_DIR` auto), `platform_utils.py`, `utils/` (timing, LEDs, `net_safety.py` : schéma https vérifié avant urllib).

**`_app_state`** : `menu`→`config`/`config_humain`/`retranscription`/`exercices`/`labo`→`connecting`→`playing`/`paused`→`game_over`. **Queues** : `event_queue` Py→nav ; `action_queue` nav→Py (partie) ; `menu_queue` nav→Py (menu).

## Principes techniques

### Invariants généraux
- **ARC-001** : `core/modes/niclink/utils/engine` n'importent jamais `nicsoft.web` ; ils passent par `core/ihm_port.py` (backend branché au démarrage par `nicsoft.web.alchess`, neutre sinon). Garde : `test_no_web_import.py`.
- **USB** : un seul accès ouvert à la fois (`connect()` ferme l'ancien) ; chaque mode appelle `disconnect()` en fin de session ; la présence physique se lit par `hid.enumerate()`, indépendamment de la connexion.
- `board.move_stack` = source de vérité ; `chess.Board(fen)` l'efface → reconstruire depuis l'historique. Le FEN transmis doit toujours être **complet** (`board.fen()`), jamais la seule disposition des pièces (`board.board_fen()`) — un FEN tronqué remet le trait aux Blancs par défaut et fait calculer un moteur pour le mauvais camp (bug réel, #338). Détail : CHANGELOG.md (#338).
- Polling `time.sleep()` ≥ 0.05 s ; threads LED daemon.
- `on_action` : chaque `sendAction({type:X})` JS a son `elif` Python.
- i18n : clé ajoutée **simultanément** dans `fr/en/de.json` (`static/i18n/`) ; allemand incertain → valeur anglaise, jamais absente.
- Tout texte externe (PGN, noms, messages serveur, réponses LLM, Lichess) → `esc()` ou `textContent`, jamais brut dans `innerHTML`. Garde : `test_issue303_html_escaping.py`.
- Aucun secret n'est envoyé au navigateur (clé LLM, jeton Lichess) : le serveur ne renvoie qu'un indicateur de présence (+ indice 4 derniers caractères si valeur ≥ 12). Garde : `test_issue304_security.py`.
- Démarrage serveur : ne jamais abaisser le niveau du `file_handler` partagé du root logger sans donner à `werkzeug` son propre handler console (sinon `Running on http://...` disparaît) ; `server.py::start_server()` affiche toujours l'adresse via `print(..., flush=True)`. Détail : CHANGELOG.md (#312).
- Arrêt du processus : un seul chemin de sortie — tout arrêt interne envoie SIGTERM au process lui-même (jamais `os._exit()` depuis un fil daemon), pour toujours traverser `_handle_termination_signal` (`alchess.py`) et ses `atexit` (ModemManager, marqueur d'instance). Jamais deux chemins de sortie concurrents. Détail : CHANGELOG.md (#337).
- **Instance unique** : `alchess.py::main()` appelle `single_instance.resolve_startup()` en premier geste. Marqueur `DATA_DIR/server_instance.json` (pid/port), supprimé à la sortie si le PID correspond encore. Reconnaissance d'un process AlChess : PID vivant **ET** ligne de commande contenant `nicsoft.web` (jamais le seul nom du programme). Partie en cours = `GET /instance_status` sur `_app_state` ∈ `single_instance.BUSY_STATES` ; état non confirmable → refus par précaution. Arrêt toujours par PID exact (jamais par nom). `ALCHESS_SKIP_SINGLE_INSTANCE=1` désactive tout ça pour les serveurs de test. Garde : `test_issue320_single_instance.py`. Détail : CHANGELOG.md (#320,#324).

### Lichess — fair-play et sécurité
- Aucun moteur, livre d'ouvertures, explorateur, exercice ni indication de coup ne tourne ni n'est accessible pendant une partie Lichess **EN COURS** (fair-play) — vérifié par test **statique** (AST) sur tout fichier de `modes/lichess/*` + `core/game_manager_modes/lichess.py`, y compris un import niché dans une fonction (`test_issue333_lichess_no_engine.py`) ; étendu aux problèmes Lichess. Jeton toujours côté serveur, jamais journalisé ; pseudos/messages Lichess toujours via `esc()`/`textContent`. **Cette règle ne s'applique jamais à l'écran d'analyse post-partie** (confusion réelle corrigée par #345 — voir « Analyse après partie » plus bas). Détail : CHANGELOG.md (#306,#307,#309,#333,#351).

### Lichess — déroulement de partie
- **Ordre de lancement** : couleur précise (blancs/noirs) résolue localement avant tout appel Lichess ; couleur « aléatoire » **n'est jamais résolue localement** — envoyée vide à `board/seek`/`challenge/ai` pour que Lichess choisisse lui-même (sinon soumise à tort à sa règle d'équilibre des couleurs, établi par lecture du code source public de lila — #330 corrigeant #327). Position physique confirmée avant toute création de partie. Côté blancs : partie créée seulement après le 1er coup physique de l'utilisateur. Côté noirs : création immédiate. Détail : CHANGELOG.md (#311,#327,#330).
- **Boutons d'action et nulle** : seule `app.js::_lichessSetActionButtons()` (dés)active Abandonner/Proposer nulle — jamais recalculé côté navigateur. Contre l'IA : nulle toujours grisée (Lichess l'ignore silencieusement contre l'IA, confirmé par lecture de `lila`). Contre un humain : Abandonner toujours actif ; Proposer nulle suit l'usage FIDE (`_human_draw_window_open`, actif après son propre coup jusqu'au coup adverse suivant). Le refus de nulle ne doit être évalué que sur l'écho du coup **adverse**, jamais sur l'écho de son propre coup (bug réel #316/#318). Un coup physique refusé avec le message ambigu « Not your turn, or game already over » (400) doit faire relire l'état déjà disponible dans le flux avant de conclure — peut cacher une fin de partie déjà arrivée (#347). Détail : CHANGELOG.md (#316,#318,#321,#327,#347).
- **File d'actions globale** : `action_queue` (serveur) est partagée par tous les modes — toujours la vider (`_discard_stale_browser_actions()`) juste avant `game.start()`, sinon une action « back_menu » laissée par l'écran précédent annule la partie suivante à tort (#319). Détail : CHANGELOG.md (#319).

### Lichess — réseau et robustesse
- Reconnexion de l'échiquier physique : essais 2s/30s puis 5s (`hid_backend._connect_lock`, un seul essai à la fois), jamais de partie créée ni d'abandon automatique avant lecture rétablie. Reconnexion du flux réseau : délais croissants (1/2/4/8/30s), jamais d'abandon automatique ; un nouveau `gameFull` à la reconnexion resynchronise sans perdre ni rejouer de coup. `StreamHandle.lines()` ne doit traiter une exception comme fin normale **que** si le flux a été fermé volontairement par nous (`self._closed`) — sinon la relever, pour ne jamais masquer une vraie coupure (#328, corrige une exception jamais journalisée). Ne jamais fermer un flux d'évènements pendant qu'un autre fil y lit encore. Détail : CHANGELOG.md (#314,#328,#333).
- Erreurs HTTP : `transport.py::UrllibTransport` journalise systématiquement méthode+chemin+code+`Retry-After`+corps tronqué (jamais le jeton) sur chaque appel. Les messages affichés distinguent 400/401-403/404/429/5xx (jamais un message générique réseau si un code HTTP existe réellement) et restent **persistants** via `afficherToastLichess()` — distincte d'`afficherToast()` (inchangée, 4s, pour les autres modes). Détail : CHANGELOG.md (#329,#347).
- Une seule partie Lichess active à la fois : revérifié juste avant toute création (`_refuse_create_if_games_ongoing()`) ; liste impossible à obtenir → laisse démarrer. Reprenabilité établie par lecture du code source public de lila : rapide/classique toujours reprenable, blitz seulement si défi direct/API ou IA, bullet/ultraBullet jamais. Reprise contre un humain nécessite une couleur transmise explicitement par le navigateur (`known_color`) — un humain ne porte pas `aiLevel`, seul indice utilisé jusqu'ici pour la déduire. Détail : CHANGELOG.md (#320,#323,#325,#333).

### Lichess — échiquier et LED
- Convention LED : indice i du tableau de rangées = rangée i+1 (`hid_backend.set_all_leds`) — un bug d'inversion (#340) a longtemps allumé le camp de l'utilisateur à la place de l'adversaire quand il jouait les noirs ; vérifier ce sens avant toute nouvelle pose de pattern. Le signal « adversaire parti » (bip+LED) ne doit se réarmer qu'à une **vraie** transition non-parti→parti — Lichess renvoie l'événement `opponentGone` toutes les ~5s même sans changement, le réarmer à chaque fois redéclenche le signal en boucle (#340). Jamais de signal après une réclamation faite par l'utilisateur lui-même. Pose LED toujours différée tant qu'un coup adverse est en cours d'affichage physique. Détail : CHANGELOG.md (#331,#334,#340).
- Demandes de reprise de coup (`takeback`) de l'adversaire : toujours refusées automatiquement, une seule fois par demande — aucune action de l'interface ne permet à l'utilisateur d'en proposer une lui-même. Limitation confirmée côté Lichess (lila#18664/#18665) : l'événement `opponentGone` n'est jamais réémis à une reconnexion — un adversaire déjà parti au moment d'une reprise reste indétectable jusqu'au prochain changement d'état réel. Détail : CHANGELOG.md (#334).

### Lichess — parties classées et cote
- `LichessGame.rated` est **toujours** lu depuis le champ `rated` du `gameFull` confirmé par Lichess — jamais deviné localement, même après reconnexion. Partie classée → rangée sous `Lichess/Classée/<cadence>/` ; amicale → `Lichess/Amicale/`. Nouvelle cote de fin de partie : lecture **publique** de `GET /api/user/<id>` (aucun jeton/scope requis), un essai puis une seule relance si la valeur n'a pas encore changé — jamais une valeur inventée si l'appel échoue. Détail : CHANGELOG.md (#344,#349).

### Lichess — problèmes (puzzles)
- Aucune route officielle pour abandonner un problème (« give up ») — ne jamais appeler `POST /api/puzzle/batch/mix` tant que le problème n'est pas réellement résolu ou raté. La position à mettre en place avant le dernier coup adverse se retrouve en rejouant `puzzle.game.pgn` jusqu'à `initialPly` demi-coups avec python-chess — jamais en tentant de « défaire » `lastMove` depuis le seul FEN final (pièce prise / droits perdus non récupérables). Un coup qui mate est accepté même hors solution officielle (lila). Détail : CHANGELOG.md (#351,#354).

### Analyse après partie — architecture et calcul
- `nicsoft/engine/review_multipv.py` (flèches/barre d'évaluation) n'est **jamais** importé par `modes/lichess/*` — gardé par le même test AST que le fair-play. Si un coup renvoyé par le moteur n'est pas légal pour le camp au trait reçu, aucune flèche n'est renvoyée (jamais un sous-ensemble partiel). Positions terminales (mat/pat/nulle) détectées via `board.outcome()` **avant** tout appel moteur. Évaluation toujours convertie du point de vue des **Blancs** avant affichage (le moteur renvoie par défaut du point de vue du camp au trait). Barre d'évaluation calculée et affichée indépendamment de la case « Afficher les flèches ». Détail : CHANGELOG.md (#335,#338,#341).
- Analyse automatique complète lancée d'office à l'ouverture de l'écran (plus de bouton « Analyser »), annulable, jamais pendant une partie Lichess **en cours** (garde serveur : refuse si `_app_state != "game_over"`) — **mais** la barre/l'analyse automatique restent toujours actives sur l'écran d'analyse d'une partie Lichess **terminée** (la règle de fair-play ne vaut que pendant une partie en cours — confusion corrigée par #345). `ALCHESS_SKIP_AUTO_ANALYSE=1` désactive l'analyse automatique pour les tests (sinon un vrai Stockfish serait lancé). Les marques ?!/?/?? et les flèches partagent une seule recherche moteur (`evaluate_move` réutilise `get_multipv`/`REVIEW_DEPTH`/`REVIEW_N_LINES`), jamais deux calculs séparés (#352). Détail : CHANGELOG.md (#341,#342,#345,#352).

### Analyse après partie — orientation des noms
- Tout code qui affecte `player-top-name`/`player-bottom-name` doit passer par `_reviewSetTopBottomNames()`/`_reviewWhiteBlackFromTopBottom()` (app.js) — jamais assigner Blancs=bas/Noirs=haut en dur. Bug récurrent trouvé et corrigé à chaque fois dans un nouvel endroit : `parsePgn()` (#345), modal d'abandon HH + `swap_color_hh` (#348), mode Pédagogique `init`/`swap_color`/nulle (#350) — le résultat de partie/PGN n'est jamais affecté (dérivé côté serveur), seul l'affichage l'était. Vérifier ce point pour tout nouveau code qui affiche un nom de joueur. Détail : CHANGELOG.md (#345,#348,#350).

## Conventions
Début de session : `git status`, branche `master`, `TESTS.md`. Tests : `python -m pytest nicsoft/tests -m "not hardware"`. Commits ciblés. USB (ThinkPad X1 Gen 7) : quirk `/etc/modprobe.d/chessnut.conf` = `options usbhid quirks=0x2d80:0x8003:0x40`, udev `autosuspend=-1`, launcher `/usr/bin/python3` (voir `INSTALLATION_ALCHESS.md`).

## Moteurs (`engine_manager.py`)
`find_stockfish/lc0/maia_weights(elo)/rodent()` + `*_available()` ; `server.py` met en cache au démarrage et émet `*_status` ; le front grise ou replie sur le premier disponible.
- **Stockfish** : Linux système/PATH/`engines/stockfish`, Win `engines/stockfish*.exe` ; détection = présence.
- **Maia** : `engines/maia/lc0` et `lc0.exe` + poids `maia-*.pb.gz` (suivis par git).
- **Rodent IV** : Linux `engines/rodent-iv/` ignoré par git (binaire compilé localement, plus un sous-module depuis #260) ; Win `engines/rodent-iv-win/` : 3 fichiers **suivis par git**, téléchargement tout-ou-rien vérifié par SHA-256 (#286). Détection = handshake UCI ; `setoption` Personality→UCI_LimitStrength→UCI_Elo.

## Gros fichiers conservés (ARC-004)
Pas d'exception dans `.audit.json` : on ne découpe pas pour réduire la taille, seulement le long de coutures naturelles, quand on modifie le fichier pour une autre raison, un fichier par issue, avec tests. `driver.py` (~850 l., code NicLink, matériel non testable) : ne pas toucher sauf raison fonctionnelle. Ordre : code commun human/pedagogique, `human.py`, `pedagogique.py`, `server.py`, `exercices.py` (parties pures d'abord), `labo.py` (tests de non-régression d'abord).

## Bridge inter-agents
Tâches via GitHub Issues (label `for-linux`) ; CCL travaille dans un worktree git isolé par issue ; lecture seule par défaut, `mode_write` avec commits ciblés ; Alain pousse après revue. Détail : `BRIDGE_AGENT_DOC.md`.

## Suivi
`TESTS.md`, `HISTORIQUE_BUGS.md`, `INSTALLATION_ALCHESS.md`, `I18N.md`, `THIRD_PARTY_NOTICES.md`, `CLAUDE.md` (auto-chargé). `TACHES.md` est privé (gitignoré) : ne pas le modifier.

## État actuel
Dernière release taguée **v1.3.2** (18 août 2026) ; `master` est nettement en avance, sans nouvelle release. **Bugs connus** (non revérifiés, matériel/Windows) : rangement HH ignoré si déconnexion USB silencieuse `[Win]` ; race LEDs rare `[Linux]` ; WAIT_FISH lent intermittent. **À traiter** : DLL Visual C++ 2013 de `rodent-iv-win/` inutiles, à retirer avec le téléchargement et ses empreintes.
