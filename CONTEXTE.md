# AlChess — Contexte projet

Briefing CCL. Seuls les ~4000 premiers caractères sont injectés dans ton prompt ; le reste du fichier reste lisible à la demande (outil de lecture) : garde l'essentiel en haut, le détail plus bas.

## Règles impératives
Elles te sont injectées automatiquement, avec ton prompt, dans la section CONSIGNES (binaires tiers en lecture seule, serveur démarré uniquement avec `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`, suppressions de sécurité, pas de push). Ici : si ta tâche change l'architecture, les dépendances, les conventions ou l'avancement, mets à jour ce fichier dans le même commit — l'état réel, pas l'historique (l'historique va dans `CHANGELOG-<N>.md`).

## Projet
**AlChess** (ex-NicLink) : app Python/Flask-SocketIO reliant un échiquier Chessnut USB (ou virtuel) à une UI web pédagogique. Front vanilla JS. Ubuntu + support Windows. Local `~/NicLink/` (venv) ; GitHub public AlainDelree/AlChess. Dév : Alain (non-dev).

## Architecture (`nicsoft/`)
- `niclink/` : `hid_backend.py` (USB hidapi pur), `driver.py` (thread FEN, LEDs, bip), `virtual_board.py`, `nl_exceptions.py`.
- `web/` : `alchess.py` (orchestre), `server.py` (Flask-SocketIO, `_app_state`, détection moteurs), `launcher.py`, `static/app.js`, `templates/index.html`.
- `core/` : `game_manager.py` (façade ; lanceurs par mode dans `core/game_manager_modes/`, état partagé dans `state.py`), `board_adapter.py`, `config_manager.py`, `ihm_port.py` (port neutre jeu↔IHM).
- `engine/` : `engine_manager` (façade réexportant `move_quality`, `engine_analysis`, `uci_engine`, `engine_detection`, `engine_availability`, `maia_engine`, `rodent_engine`), `players`, `pgn_manager`, `board_utils`, `display`, `analyse`.
- `modes/` (`pedagogique humain exercices retranscription labo opening_explorer`) : `explore_book`, `eco_import`, `llm_explainer` sont des façades réexportant des modules par rôle.
- `config.py` (`APP_DIR` auto), `platform_utils.py`, `utils/` (timing, LEDs, `net_safety.py` : schéma https vérifié avant urllib).

**`_app_state`** : `menu`→`config`/`config_humain`/`retranscription`/`exercices`/`labo`→`connecting`→`playing`/`paused`→`game_over`. **Queues** : `event_queue` Py→nav ; `action_queue` nav→Py (partie) ; `menu_queue` nav→Py (menu).

## Principes techniques
- **ARC-001** : `core/modes/niclink/utils/engine` n'importent jamais `nicsoft.web` ; ils passent par `core/ihm_port.py` (backend branché au démarrage par `nicsoft.web.alchess`, neutre sinon). Garde : `test_no_web_import.py`.
- **USB** : un seul accès ouvert à la fois (`connect()` ferme l'ancien) ; chaque mode appelle `disconnect()` en fin de session ; la présence physique se lit par `hid.enumerate()`, indépendamment de la connexion.
- `board.move_stack` = source de vérité ; `chess.Board(fen)` l'efface → reconstruire depuis l'historique.
- Polling `time.sleep()` ≥ 0.05 s ; threads LED daemon.
- `on_action` : chaque `sendAction({type:X})` JS a son `elif` Python.
- i18n : clé ajoutée **simultanément** dans `fr/en/de.json` (`static/i18n/`) ; allemand incertain → valeur anglaise, jamais absente.
- Tout texte externe (PGN, noms, messages serveur, réponses LLM, Lichess) → `esc()` ou `textContent`, jamais brut dans `innerHTML`. Garde : `test_issue303_html_escaping.py`.
- Aucun secret n'est envoyé au navigateur (clé LLM, jeton Lichess) : le serveur ne renvoie qu'un indicateur de présence (+ indice 4 derniers caractères si valeur ≥ 12). Garde : `test_issue304_security.py`.
- Lichess (`modes/lichess/`, issue #306 étape L0 jeton, issue #307 étape L1 client de partie) : jeton toujours côté serveur, jamais envoyé au navigateur ni journalisé ; client de partie (`game_client.py`, `transport.py`, `errors.py`) à transport réseau injectable (tests sans réseau), une requête ordinaire à la fois par verrou (jamais bloquant pour la lecture du flux), aucun moteur/aide/livre d'ouvertures ne doit tourner pendant une partie Lichess (fair-play Lichess) ; aucun mode de jeu ni écran de partie encore ajouté.

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
Dernière release taguée **v1.3.2** (18 août 2026) ; `master` est nettement en avance, sans nouvelle release. **Bugs connus** (non revérifiés, matériel/Windows) : rangement HH ignoré si déconnexion USB silencieuse `[Win]` ; race LEDs rare `[Linux]` ; WAIT_FISH lent intermittent. **À traiter** : dépendances en retard (setuptools, chess, wheel, Flask-SocketIO avec python-socketio ensemble) ; DLL Visual C++ 2013 de `rodent-iv-win/` inutiles, à retirer avec le téléchargement et ses empreintes.
