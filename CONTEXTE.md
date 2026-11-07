# AlChess — Contexte projet

Briefing CCL. Vérifié 5 nov. 2026 (branche `worktree-issue-284`).

## Maintenance de ce fichier
Si ta tâche modifie l'architecture, les dépendances, les conventions ou l'avancement majeur, mets à jour ce CONTEXTE.md dans le même commit.

## Projet
**AlChess** (ex-NicLink) : app Python/Flask-SocketIO reliant un échiquier Chessnut Air USB (ou virtuel) à une UI web pédagogique. Front vanilla JS (`app.js`/`index.html`/CSS). Ubuntu + support Windows. Local `~/NicLink/` (venv) ; GitHub public AlainDelree/AlChess. Dév : Alain (non-dev).

## Architecture (`nicsoft/`)
- `niclink/` : `hid_backend.py` (USB hidapi pur), `driver.py` (Chessnut : thread FEN dédié, LEDs, beep), `virtual_board.py`, `nl_exceptions.py`.
- `web/` : `alchess.py` orchestre ; `server.py` Flask-SocketIO + `_app_state` + détection moteurs (caches/events `*_status`) ; `static/app.js`, `templates/index.html`.
- `core/` : `game_manager.py` (façade, réexporte les lanceurs par mode depuis `core/game_manager_modes/` — `pedagogique humain retranscription exercices labo` + `state.py` pour l'état partagé, découpé issue #278), `board_adapter.py`, `config_manager.py`, `ihm_port.py` (port neutre jeu↔IHM, voir ARC-001 ci-dessous). `engine/` UCI : `engine_manager` (point d'entrée réexportant `move_quality engine_analysis uci_engine engine_detection engine_availability maia_engine rodent_engine`, découpé issue #276) `players pgn_manager board_utils display analyse`.
- `modes/` (`pedagogique humain exercices retranscription labo`) : dans `exercices/`, `explore_book.py` et `eco_import.py` sont des façades réexportant des modules par rôle (`*_cli/_display/_import/_web`, + `eco_import_data.py`) ; `opening_explorer/llm_explainer.py` façade réexportant `llm_prompts llm_cache llm_functions llm_provider tts_engine sources explorer_session`.
- `config.py` (`APP_DIR` auto), `platform_utils.py`, `utils/` (timing, LEDs, `net_safety.py` — vérification de schéma avant ouverture d'une adresse distante avec urllib, n'importe jamais `nicsoft.web`, issue #288).

**`_app_state`** : `menu`→`config`/`config_humain`/`retranscription`/`exercices`/`labo`→`connecting`→`playing`/`paused`→`game_over`.
**Queues** : `event_queue` Py→nav ; `action_queue` nav→Py (partie) ; `menu_queue` nav→Py (menu).

## Moteurs (`engine_manager.py`)
`find_stockfish/lc0/maia_weights(elo)/rodent()` + `*_available()` ; `server.py` cache au boot, émet `*_status` ; front grise/replie sur 1er dispo.
- **Stockfish** : Linux système/PATH/`engines/stockfish`, Win `engines/stockfish*.exe`. Détection=présence.
- **Maia** : `lc0`/`engines/maia/lc0.exe` + poids `engines/maia/maia-*.pb.gz`.
- **Rodent IV** : Linux `engines/rodent-iv/` — binaire compilé localement, dossier ignoré par git (`.gitignore`, pas un sous-module depuis l'issue #260) ; Win `engines/rodent-iv-win/` (copié localement, même régime). Détection=handshake UCI ; `setoption` **Personality→UCI_LimitStrength→UCI_Elo**.

## Bridge inter-agents
Tâches via **GitHub Issues** (repo AlChess) label `for-linux` ; CCL travaille dans un worktree git isolé par issue. Lecture seule par défaut ; `mode_write` → protection du travail par git (commits ciblés, retour arrière par git), **jamais `git push`** (Alain pousse après revue), rien de destructeur sans demande. Détail : `BRIDGE_AGENT_DOC.md`.

## Conventions
Début session : lire `TACHES.md`+`TESTS.md`, `git status`, branche `master`. Commits ciblés ; `git checkout .` annule. Lancer `cd ~/NicLink && python -m nicsoft.web`. USB (ThinkPad X1 Gen 7) : quirk `/etc/modprobe.d/chessnut.conf` = `options usbhid quirks=0x2d80:0x8003:0x40` ; launcher `/usr/bin/python3` ; udev `autosuspend=-1`. Voir `INSTALLATION_ALCHESS.md`.
- **Pas de `noqa`/`nosec`** (avec ou sans code) tant qu'Alain n'a pas confirmé l'évolution de l'outil d'audit (liste des suppressions justifiées au lieu de les cacher) : corriger plutôt que supprimer (exception précisée et resserrée, ou trace `debug` pour un `except` voulu ; vérifier qu'une adresse est en `https` avant de l'ouvrir plutôt que de supprimer le signalement). Forme future : un commentaire au-dessus qui dit pourquoi, puis le code précis sur la ligne elle-même — jamais une suppression sans code.
- **Toute vérification qui démarre le serveur** (test automatisé, contrôle manuel par un agent) doit positionner `ALCHESS_SKIP_BOARD=1` **et** `ALCHESS_NO_BROWSER=1`, jamais sans — sinon elle ouvre un onglet et sollicite l'échiquier sur le poste de l'utilisateur. `ALCHESS_SKIP_BOARD=1` empêche aussi tout arrêt/relance de ModemManager. Détail : `TESTS.md`.

## Principes techniques
- **ARC-001 — le moteur ne connaît pas l'interface** : `core/modes/niclink/utils/engine` n'importent jamais `nicsoft.web`. Ils passent par `nicsoft/core/ihm_port.py` (send_event, get_action, set_app_state, set_virtual_board, get/set_history, get_action_queue, get/set_raw_app_state, check_board_at_startup ; `app_state_proxy` reproduit l'ancien accès direct `web_server._app_state`/`.action_queue`). `nicsoft.web.alchess` branche l'implémentation réelle via `ihm_port.register_backend()` au démarrage ; sans branchement (tests, import isolé), un backend neutre répond sans effet de bord. Verrouillé par `nicsoft/tests/test_no_web_import.py`.
- **Contention USB** : accès uniquement via le thread de lecture du driver.
- **`board.move_stack`=source de vérité** ; `chess.Board(fen)` l'efface → reconstruire depuis l'historique.
- Polling `time.sleep()`≥0.05 s ; threads LED daemon.
- **`on_action`** : chaque `sendAction({type:X})` JS a son `elif` Python.
- **i18n** : clé ajoutée **simultanément** dans `fr/en/de.json` (`static/i18n/`) ; allemand incertain → valeur anglaise, jamais absente.
- `python3 -c` plutôt que `sed`.

## Gros fichiers conservés (ARC-004)
Pas d'exception dans `.audit.json` (le mécanisme est par règle, pas par fichier) : on ne découpe pas pour réduire la taille. Le couplage jeu↔interface est déjà réglé (`ihm_port.py`, aucun import de `nicsoft.web` depuis le jeu, gardé par les tests ARC-001). Ces quatre fichiers restent grands volontairement :
- `driver.py` (~850 l.) : code issu de NicLink, matériel non testable sans la planche → ne pas toucher sauf raison fonctionnelle.
- `pedagogique.py` (~1580 l.) et `human.py` (~1220 l.) : état d'instance et fils partagés. On les découpe seulement le long de coutures naturelles, au moment où on les modifie pour une autre raison, un fichier par issue, avec leurs tests.
- `server.py` (~1250 l.) : ancrage du port neutre (`_WebBackend`). Même règle ; coutures : détection moteurs, routes HTTP, handlers par domaine.
- `exercices.py` (~1350 l.) : même règle ; coutures : parties pures d'abord (données du catalogue, sélection d'un coup dans le livre), puis la session et l'enchaînement des lignes avec son fil d'exécution.
- `labo.py` (~450 l.) : même règle ; aucun test de comportement n'existe et plusieurs fils d'exécution y partagent de l'état — ajouter des tests de non-régression avant toute extraction.
Ordre : (1) code commun pause/abandon/undo/historique PGN de human et pedagogique, (2) human, (3) pedagogique, (4) server, (5) exercices (parties pures puis session/fil), (6) labo (tests de non-régression d'abord) ; driver hors liste.

## Fichiers de suivi
`TACHES.md`, `TESTS.md`, `TEST_RESULTATS.md`, `HISTORIQUE_BUGS.md`, `INSTALLATION_ALCHESS.md`, `I18N.md`, `CLAUDE.md` (auto-chargé).

## État actuel (5 nov. 2026)
Dernière release taguée **v1.3.2** (18 août 2026) ; dépôt ~220 commits plus avancé depuis, pas de nouvelle release taguée. Depuis juillet : dépendances à jour et épinglées (correctifs de sécurité + versions figées, `requirements.txt`) ; découplage jeu/interface via `ihm_port.py` (aucun import de `nicsoft.web` depuis le jeu, gardé par les tests ARC-001) ; outil de sauvegarde `backup_manager` retiré (protection = git) ; journalisation des erreurs auparavant silencieuses (règle PRO-012) ; tests de garde ARC-001 découvrant seuls les fichiers de `core/modes/niclink/utils/engine` ; hook git pre-push lançant la suite complète (~40 s) ; découpages en façades de `game_manager`, `engine_manager`, `explore_book`/`eco_import`, `llm_explainer` ; reprise de session de retranscription proposée à chaque ouverture ; régressions d'affichage dues à l'extraction des styles en ligne corrigées (issue #279).
**Bugs connus** (non revérifiés depuis juillet — matériel/Windows) : rangement HH ignoré si déconnexion USB silencieuse `[Win]` ; race LEDs rare `[Linux]` ; WAIT_FISH lent intermittent (hardware).
**Chantiers** : statut « Connected » trompeur, Socket.IO ≠ échiquier (non revérifié) ; finitions Win (non revérifié) ; éléments d'interface morts signalés mais non traités — bouton d'abandon de la pause (`#btn-pause-abandonner`), compte à rebours (`#countdown`), id dupliqué du labo (`#labo-feedback`) (issue #279) ; gros fichiers conservés volontairement — voir section ARC-004 ci-dessous.
