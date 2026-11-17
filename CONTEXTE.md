# AlChess — Contexte projet

Briefing CCL. Ce fichier tient entièrement dans l'injection de prompt — le détail par domaine est dans `docs/contexte/<domaine>.md`, à lire à la demande selon la nature de la tâche.

## Règles
Transverses (binaires tiers lecture seule, `ALCHESS_SKIP_BOARD`/`NO_BROWSER`, suppressions sécurité, pas de push) injectées en CONSIGNES. Archi/dépendances/conventions modifiées : mets à jour ce fichier ou le fichier de domaine, même commit — état réel, pas l'historique (→ `CHANGELOG-<N>.md`). `TACHES.md` : privé (gitignoré), ne jamais le modifier. CONTEXTE.md : reste sous 3700 car. (`wc -m`), test dédié.

## Projet
**AlChess** (ex-NicLink) : app Python/Flask-SocketIO reliant un échiquier Chessnut USB (ou virtuel) à une UI web pédagogique. Front vanilla JS. Ubuntu + support Windows. Local `~/NicLink/` (venv) ; GitHub public AlainDelree/AlChess. Dév : Alain (non-dev).

## Architecture (`nicsoft/`)
- `niclink/` : `hid_backend.py` (USB hidapi pur), `driver.py` (thread FEN, LEDs, bip), `virtual_board.py`, `nl_exceptions.py`.
- `web/` : `alchess.py` (orchestre), `server.py` (Flask-SocketIO, `_app_state`, détection moteurs), `single_instance.py`, `launcher.py`, `static/app.js`, `templates/index.html`.
- `core/` : `game_manager.py` (façade ; lanceurs par mode dans `core/game_manager_modes/`), `board_adapter.py`, `config_manager.py`, `ihm_port.py` (port neutre jeu↔IHM).
- `engine/` : `engine_manager` (façade Stockfish/Maia/Rodent), `players`, `pgn_manager`, `board_utils`, `display`, `analyse`.
- `modes/` (`pedagogique humain exercices retranscription labo opening_explorer lichess`).
- `config.py`, `platform_utils.py`, `utils/` (timing, LEDs, `net_safety.py`).

**`_app_state`** : `menu`→`config`/`config_humain`/`retranscription`/`exercices`/`labo`→`connecting`→`playing`/`paused`→`game_over`. **Queues** : `event_queue` Py→nav ; `action_queue` nav→Py (partie) ; `menu_queue` nav→Py (menu).

## Conventions
Début session : `git status`, branche `master`, `TESTS.md`. Tests : `python -m pytest nicsoft/tests -m "not hardware"`.

## Index des fichiers de contexte (`docs/contexte/<domaine>.md`)
- `architecture.md` — invariants généraux (imports, FEN/move_stack, i18n, XSS, secrets, arrêt process, instance unique). Lire avant toute tâche touchant plusieurs modes ou l'infra serveur.
- `echiquier_usb_led.md` — accès USB, convention LED, quirk matériel. Lire avant toute tâche sur `driver.py`/`hid_backend.py`.
- `lichess.md` — fair-play, déroulement, réseau, LED adversaire, cote, problèmes. Lire avant toute tâche sur `modes/lichess/`.
- `analyse_post_partie.md` — calcul flèches/éval, orientation des noms. Lire avant toute tâche sur `review_multipv.py`/écran d'analyse.
- `moteurs.md` — détection Stockfish/Maia/Rodent. Lire avant toute tâche sur `engine_manager.py`.
- `gros_fichiers_audit.md` — règle ARC-004 (pas de découpage pour la taille seule), `.audit.json`. Lire avant de proposer une exception d'audit.

Fichiers de référence (cités par section) : `TESTS.md`, `INSTALLATION_ALCHESS.md`, `I18N.md`, `THIRD_PARTY_NOTICES.md`, `CLAUDE.md` (auto-chargé).

## État actuel
Dernière release **v1.3.2** (18 août 2026) ; `master` en avance, sans nouvelle release. **Bugs connus** (matériel/Windows, non revérifiés) : rangement HH ignoré si déconnexion USB silencieuse `[Win]` ; race LEDs rare `[Linux]` ; WAIT_FISH lent intermittent. **À traiter** : DLL Visual C++ 2013 de `rodent-iv-win/` toujours présentes (`msvcp120.dll`/`msvcr120.dll`), à retirer avec le téléchargement et ses empreintes.
