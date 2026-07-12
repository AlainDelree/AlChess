# AlChess — État du projet
_Généré le 2026-05-22_

---

## 1. Structure des fichiers principaux

### Backend Python (`nicsoft/`)

| Fichier | Rôle | Modifié le |
|---------|------|------------|
| `nicsoft/config.py` | Chemins centralisés (`ALCHESS_DIR`, `APP_DIR`) | 2026-05-21 |
| `nicsoft/platform_utils.py` | Isolation ModemManager / appels OS | 2026-05-19 |
| `nicsoft/web/alchess.py` | Chef d'orchestre — boucle principale, dispatch `_app_state` | 2026-05-19 |
| `nicsoft/web/server.py` | Flask-SocketIO, `_app_state`, toutes les routes/events | 2026-05-21 |
| `nicsoft/web/launcher.py` | Splash GTK au démarrage (ignoré sur Windows) | 2026-05-10 |
| `nicsoft/core/game_manager.py` | Gestion des parties, validation moteurs | 2026-05-21 |
| `nicsoft/core/board_adapter.py` | Adaptateur plateau physique/virtuel | 2026-05-19 |
| `nicsoft/engine/engine_manager.py` | UCI engines : Stockfish, Maia, Rodent | 2026-05-21 |
| `nicsoft/engine/players.py` | Abstraction joueur humain/moteur | 2026-05-19 |
| `nicsoft/engine/pgn_manager.py` | Import/export PGN | 2026-05-19 |
| `nicsoft/engine/board_utils.py` | Utilitaires python-chess | 2026-05-19 |
| `nicsoft/engine/analyse.py` | Analyse Stockfish post-partie | 2026-05-19 |
| `nicsoft/modes/pedagogique/pedagogique.py` | Mode vs moteur (1880 lignes) | 2026-05-21 |
| `nicsoft/modes/humain/human.py` | Mode Humain vs Humain (1217 lignes) | 2026-05-19 |
| `nicsoft/modes/exercices/exercices.py` | Entraînement ouvertures (1313 lignes) | 2026-05-19 |
| `nicsoft/modes/labo/labo.py` | Analyse libre Stockfish | 2026-05-21 |
| `nicsoft/modes/retranscription/retranscription.py` | Saisie parties papier | 2026-05-19 |
| `nicsoft/niclink/driver.py` | Driver USB Chessnut Air, thread 50ms (824 lignes) | 2026-05-19 |
| `nicsoft/niclink/hid_backend.py` | Backend hidapi Python pur (remplace `.so`) | 2026-05-19 |
| `nicsoft/niclink/virtual_board.py` | Simulation échiquier sans hardware | 2026-05-08 |
| `nicsoft/utils/debug.py` | `DEBUG_MODE` via `NICLINK_LOG=DEBUG` | 2026-05-08 |
| `nicsoft/utils/timing.py` | `tlog()` — timings (DEBUG seulement) | 2026-05-02 |
| `nicsoft/utils/backup_manager.py` | Sauvegardes pinnées/auto | 2026-05-02 |

### Frontend

| Fichier | Taille | Modifié le |
|---------|--------|------------|
| `nicsoft/web/static/app.js` | 5716 lignes | 2026-05-21 |
| `nicsoft/web/templates/index.html` | 1447 lignes | 2026-05-21 |
| `nicsoft/web/static/css/main.css` | 642 lignes | 2026-05-21 |
| `nicsoft/web/static/i18n.js` | — | 2026-05-19 |
| `nicsoft/web/static/i18n/fr.json` | 606 clés | 2026-05-21 |
| `nicsoft/web/static/i18n/en.json` | 606 clés | 2026-05-21 |
| `nicsoft/web/static/i18n/de.json` | 606 clés | 2026-05-21 |

### Windows

| Fichier | Rôle | Modifié le |
|---------|------|------------|
| `install_alchess.ps1` | Installateur PowerShell complet (+ raccourci bureau) | 2026-07-13 |
| `1-Installer.bat` | Wrapper BAT pour lancer l'installateur PS1 | 2026-07-13 |
| `2-Lancer_AlChess.bat` | Wrapper BAT pour lancer AlChess (start_alchess.ps1) | 2026-07-13 |
| `start_alchess.ps1` | Lanceur Windows (chemin auto-détecté) | 2026-05-21 |

### Moteurs (`engines/`)

| Dossier/Fichier | Contenu |
|-----------------|---------|
| `engines/stockfish-windows-x86-64-avx2.exe` | Stockfish Windows (109 Mo) |
| `engines/stockfish-windows-x86-64-avx2/` | Stockfish Windows extrait |
| `engines/rodent-iv/` | Rodent IV (multi-niveaux) |
| `engines/maia/` | Poids Maia 1200–1800 + lc0 |

### Tests

| Fichier | Type | Modifié le |
|---------|------|------------|
| `nicsoft/tests/test_app_state.py` | pytest — 25 tests états machine | 2026-05-07 |
| `nicsoft/tests/test_pgn.py` | pytest — PGN | 2026-05-07 |
| `nicsoft/tests/test_players.py` | pytest — joueurs | 2026-05-02 |
| `nicsoft/tests/test_move_matching.py` | pytest — coups | 2026-05-02 |
| `nicsoft/tests/e2e/test_smoke_e2e.py` | Playwright E2E | 2026-05-12 |
| `nicsoft/tests/e2e/test_outils_exercices_e2e.py` | Playwright E2E | 2026-05-11 |

---

## 2. Fonctionnalités — État

| Fonctionnalité | État | Notes |
|----------------|------|-------|
| Mode Pédagogique (vs Stockfish) | ✅ Stable | |
| Mode Pédagogique (vs Maia 1200–1800) | ✅ Stable | 6 poids téléchargés |
| Mode Pédagogique (vs Rodent) | ✅ Stable | |
| Mode Pédagogique — mode virtuel | ✅ Stable | Sans échiquier physique |
| Mode Pédagogique — feedback WAIT_FISH | ✅ Stable | Cadre orange si pièce mal placée |
| Mode Humain vs Humain | ✅ Stable | |
| Mode Humain vs Humain — mode virtuel | ⚠️ Partiel | Bouton grisé, mais déconnexion silencieuse non détectée (bug Windows) |
| Analyse de partie (import PGN, navigation, Stockfish) | ✅ Stable | |
| Exercices / Ouvertures | ✅ Stable | |
| Retranscription de parties | ✅ Stable | Reprise session incluse |
| Laboratoire (analyse libre) | ✅ Stable | Mode virtuel inclus |
| Driver USB Chessnut Air (hidapi Python pur) | ✅ Stable | Remplace `.so` C++ |
| Mode virtuel (sans échiquier) | ✅ Stable | `virtual_board.py` |
| Internationalisation FR | ✅ Stable | 606 clés |
| Internationalisation EN | ✅ Stable | 606 clés |
| Internationalisation DE | ⚠️ Partiel | 606 clés présentes — corrections résiduelles au fil tests |
| Split-button menu physique/virtuel | ✅ Stable | |
| Sauvegarde / backup pinné | ✅ Stable | `backup_manager.py` |
| Logs structurés | ✅ Stable | `niclink.log`, bouton 📋 UI |
| Réarchitecture multiplateforme | ✅ Stable | Mergée master (commit 9618efc) |
| Portage Windows — driver hidapi | ✅ Stable | 16/16 tests Windows 11 (commit 4c78247) |
| Portage Windows — application complète | ✅ Stable | Modes validés sur VM |
| Installateur Windows `install_alchess.ps1` | ⏳ En attente de test | Écrit (commit 3c21705), à tester sur VM avant merge master |

---

## 3. TODO et DEBUG dans le code

### `HACK` — workarounds actifs

| Fichier | Ligne | Contenu |
|---------|-------|---------|
| `nicsoft/niclink/driver.py` | 93 | `# HACK: delay for how long threads should sleep, letting threads work` |

### `TODO` — à faire explicitement

| Fichier | Ligne | Contenu |
|---------|-------|---------|
| `nicsoft/niclink/nl_bluetooth/__init__.py` | 212 | `# TODO: this global variable is a derty trick` |
| `nicsoft/niclink/nl_bluetooth/main.py` | 111 | `# TODO: this global variable is a derty trick` |
| `nicsoft/test/__main__.py` | 105 | `# TODO: make sure await move work's` |

> **Note** : les modules `nl_bluetooth` et `test/` sont hérités de l'ancienne architecture NicLink, non utilisés dans l'app active.

### `DEBUG_MODE` — logs conditionnels

Le mécanisme est propre : `DEBUG_MODE = os.environ.get("NICLINK_LOG", "").upper() == "DEBUG"` (`utils/debug.py`).  
Utilisé avec `if DEBUG_MODE: print(...)` dans :

| Module | Occurrences |
|--------|-------------|
| `pedagogique.py` | 10 |
| `exercices.py` | 2 |
| `labo.py` | 1 |
| `retranscription.py` | 2 |

Aucun `print()` DEBUG hors condition `DEBUG_MODE` dans le code actif.

---

## 4. Tests automatisés — Résultat courant

Commande : `python -m pytest nicsoft/tests/ -q --tb=no`

```
32 passed, 43 errors
```

| Suite | Résultat | Raison |
|-------|----------|--------|
| `test_app_state.py` (25 tests) | ✅ Passent | Tests unitaires purs |
| `test_pgn.py`, `test_players.py`, `test_move_matching.py` | ✅ Passent | Tests unitaires purs |
| `test_smoke_e2e.py` (Playwright) | ❌ 19 erreurs | Serveur non démarré — normal hors CI |
| `test_outils_exercices_e2e.py` (Playwright) | ❌ 6 erreurs | Serveur non démarré — normal hors CI |

> Les erreurs E2E sont attendues : Playwright nécessite que le serveur tourne sur `localhost:5000` (lancer d'abord `python -m nicsoft.web`).

---

## 5. Dépendances et versions

### Python : `requirements.txt`

| Package | Version |
|---------|---------|
| `Flask` | 3.1.3 |
| `Flask-SocketIO` | 5.6.1 |
| `python-socketio` | 5.16.1 |
| `Werkzeug` | 3.1.7 |
| `chess` | 1.10.0 |
| `stockfish` | 3.28.0 |
| `hidapi` | 0.15.0 |
| `requests` | 2.33.1 |
| `berserk` | 0.13.2 |
| `numpy` | 1.26.4 |
| `pyserial` | 3.5 |
| `readchar` | 4.0.5 |

### Tests

| Package | Version |
|---------|---------|
| `pytest` | 9.0.3 |
| `playwright` | 1.59.0 |
| `pytest-playwright` | 0.7.2 |
| `pytest-base-url` | 2.1.0 |

### Python runtime

| Item | Version |
|------|---------|
| Python | 3.12+ (requis) |
| OS Linux testé | Ubuntu, kernel 6.17.0-29 |
| OS Windows testé | Windows 11 VM |

### Moteurs UCI

| Moteur | Version/Note |
|--------|-------------|
| Stockfish | `stockfish-windows-x86-64-avx2.exe` (Windows) ; installé via apt/pip sur Linux |
| Maia | lc0 + poids 1200/1300/1400/1500/1600/1700/1800 |
| Rodent IV | Binaire dans `engines/rodent-iv/` |

---

## 6. Bugs connus et points en suspens

### Priorité normale

| Bug | Plateforme | Description |
|-----|-----------|-------------|
| **HH — déconnexion silencieuse** | Windows | Échiquier déconnecté sans événement USB → écran rangement ignoré au démarrage HH. `driver.py` ne détecte pas la perte de connexion. |
| **Race condition LEDs** | Linux | Synchronisation camps LED parfois incorrecte. Rare, cause probable hardware. |
| **WAIT_FISH lent intermittent** | Les deux | >30s pour reconnaître une position après coup moteur. Cause probable : hardware Chessnut Air. |
| **Numéros de lignes échiquier** | Windows | Mauvais alignement sur police Windows. En veille. |
| **i18n DE — corrections résiduelles** | Les deux | Quelques edge cases DE (eco_import.py erreurs) au fil des tests. |

### Tâche bloquante avant merge master

- [ ] **Tester `install_alchess.ps1` sur VM Windows** — installateur écrit mais non validé.

---

## 7. Fichiers à nettoyer (hors `nicsoft/`)

Ces dossiers/fichiers sont des archives de l'ancienne architecture ou des artefacts de debug, non utilisés en production :

| Chemin | Nature |
|--------|--------|
| `nicsoft.apresinstallJess/` | Snapshot archive (ancienne archi) |
| `nicsoft/test/` (vs `nicsoft/tests/`) | Anciens tests NicLink hardware — non intégrés pytest |
| `nicsoft/niclink/nl_bluetooth/` | Module Bluetooth non utilisé |
| `debug_engine.txt`, `debug_find_stockfish.txt` | Fichiers debug temporaires |
| `test_windows.py`, `test_windows_result.txt` | Tests ponctuels Windows |
| `Lenteur/` | Logs d'investigation perf |
| `TRAVAIL_EN_COURS/` | Notes de session en cours |
| `build/`, `src/`, `src_niclink/` | CMake pour ancien `.so` C++ (obsolète depuis hidapi) |
