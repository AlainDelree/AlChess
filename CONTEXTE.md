# AlChess — Contexte projet

Briefing CCL. Vérifié 5 nov. 2026 (branche `worktree-issue-263`).

## Maintenance de ce fichier
Si ta tâche modifie l'architecture, les dépendances, les conventions ou l'avancement majeur, mets à jour ce CONTEXTE.md dans le même commit.

## Projet
**AlChess** (ex-NicLink) : app Python/Flask-SocketIO reliant un échiquier Chessnut Air USB (ou virtuel) à une UI web pédagogique. Front vanilla JS (`app.js`/`index.html`/CSS). Ubuntu + support Windows. Local `~/NicLink/` (venv) ; GitHub public AlainDelree/AlChess. Dév : Alain (non-dev).

## Architecture (`nicsoft/`)
- `niclink/` : `hid_backend.py` (USB hidapi pur), `driver.py` (Chessnut : thread FEN dédié, LEDs, beep), `virtual_board.py`, `nl_exceptions.py`.
- `web/` : `alchess.py` orchestre ; `server.py` Flask-SocketIO + `_app_state` + détection moteurs (caches/events `*_status`) ; `static/app.js`, `templates/index.html`.
- `core/` : `game_manager.py`, `board_adapter.py`, `ihm_port.py` (port neutre jeu↔IHM, voir ARC-001 ci-dessous). `engine/` UCI : `engine_manager players pgn_manager board_utils display analyse`.
- `config.py` (`APP_DIR` auto), `platform_utils.py`, `modes/`, `utils/` (timing, LEDs).

**`_app_state`** : `menu`→`config`/`config_humain`/`retranscription`/`exercices`/`labo`→`connecting`→`playing`/`paused`→`game_over`.
**Queues** : `event_queue` Py→nav ; `action_queue` nav→Py (partie) ; `menu_queue` nav→Py (menu).

## Moteurs (`engine_manager.py`)
`find_stockfish/lc0/maia_weights(elo)/rodent()` + `*_available()` ; `server.py` cache au boot, émet `*_status` ; front grise/replie sur 1er dispo.
- **Stockfish** : Linux système/PATH/`engines/stockfish`, Win `engines/stockfish*.exe`. Détection=présence.
- **Maia** : `lc0`/`engines/maia/lc0.exe` + poids `engines/maia/maia-*.pb.gz`.
- **Rodent IV** : Linux **sous-module** `engines/rodent-iv/` ; Win `engines/rodent-iv-win/` (hors sous-module). Détection=handshake UCI ; `setoption` **Personality→UCI_LimitStrength→UCI_Elo**.

## Bridge inter-agents
Tâches via **GitHub Issues** (repo AlChess) label `for-linux` ; CCL travaille dans un worktree git isolé par issue. Lecture seule par défaut ; `mode_write` → protection du travail par git (commits ciblés, retour arrière par git), **jamais `git push`** (Alain pousse après revue), rien de destructeur sans demande. Détail : `BRIDGE_AGENT_DOC.md`.

## Conventions
Début session : lire `TACHES.md`+`TESTS.md`, `git status`, branche `master`. Commits ciblés ; `git checkout .` annule. Lancer `cd ~/NicLink && python -m nicsoft.web`. USB (ThinkPad X1 Gen 7) : quirk `/etc/modprobe.d/chessnut.conf` = `options usbhid quirks=0x2d80:0x8003:0x40` ; launcher `/usr/bin/python3` ; udev `autosuspend=-1`. Voir `INSTALLATION_ALCHESS.md`.

## Principes techniques
- **ARC-001 — le moteur ne connaît pas l'interface** : `core/modes/niclink/utils/engine` n'importent jamais `nicsoft.web`. Ils passent par `nicsoft/core/ihm_port.py` (send_event, get_action, set_app_state, set_virtual_board, get/set_history, get_action_queue, get/set_raw_app_state, check_board_at_startup ; `app_state_proxy` reproduit l'ancien accès direct `web_server._app_state`/`.action_queue`). `nicsoft.web.alchess` branche l'implémentation réelle via `ihm_port.register_backend()` au démarrage ; sans branchement (tests, import isolé), un backend neutre répond sans effet de bord. Verrouillé par `nicsoft/tests/test_no_web_import.py`.
- **Contention USB** : accès uniquement via le thread de lecture du driver.
- **`board.move_stack`=source de vérité** ; `chess.Board(fen)` l'efface → reconstruire depuis l'historique.
- Polling `time.sleep()`≥0.05 s ; threads LED daemon.
- **`on_action`** : chaque `sendAction({type:X})` JS a son `elif` Python.
- **i18n** : clé ajoutée **simultanément** dans `fr/en/de.json` (`static/i18n/`) ; allemand incertain → valeur anglaise, jamais absente.
- `python3 -c` plutôt que `sed`.

## Fichiers de suivi
`TACHES.md`, `TESTS.md`, `TEST_RESULTATS.md`, `HISTORIQUE_BUGS.md`, `INSTALLATION_ALCHESS.md`, `I18N.md`, `CLAUDE.md` (auto-chargé).

## État actuel (21 juil. 2026)
**Stable Linux+Win**, Release **v1.0.0** (ZIP) : tous les modes (Pédagogique Stockfish/Maia/Rodent, Humain, Analyse PGN, Exercices, Retranscription, Labo, virtuel) ; i18n FR/EN/DE.
**Bugs** : rangement HH ignoré si déconnexion USB silencieuse `[Win]` ; race LEDs rare `[Linux]` ; WAIT_FISH lent intermittent (hardware).
**Chantiers** : statut « Connected » trompeur (Socket.IO ≠ échiquier) ; finitions Win ; `git submodule update --init` échoue sur clone frais.
