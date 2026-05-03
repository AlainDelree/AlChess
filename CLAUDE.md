# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

**AlChess** — Application Python/Flask-SocketIO connectant un échiquier physique Chessnut Air (USB) à une interface web pédagogique.  
GitHub : https://github.com/AlainDelree/AlChess  
Stack : Python 3.12, Flask-SocketIO (backend), vanilla JS + HTML/CSS (frontend), Ubuntu.

## Démarrage de session

Toujours faire en début de session :
1. Lire `TACHES.md` — bugs actifs et fonctionnalités à venir
2. Lire `TESTS.md` — checklist de régression
3. `git status` avant toute modification

## Workflow de travail

- Mettre à jour `TACHES.md` immédiatement après chaque correction (déplacer le bug dans "Bugs résolus récemment", noter le commit).
- Committer après chaque étape stable, avec un message descriptif.
- En cas d'interruption : l'état exact est dans `git log --oneline` (dernière étape stable) et `TACHES.md` (ce qui reste à faire).

## Commandes

```bash
# Activer l'environnement virtuel (requis pour toutes les commandes)
cd ~/NicLink && source venv/bin/activate

# Lancer l'application
python -m nicsoft.web

# Lancer en mode debug (logs détaillés + timing)
NICLINK_LOG=DEBUG python -m nicsoft.web

# Arrêter ModemManager si interference USB (ThinkPad X1 Carbon Gen 7)
sudo systemctl stop ModemManager

# Tests automatisés
cd ~/NicLink && python -m pytest nicsoft/tests/

# Gestion des exercices/ouvertures
python -m nicsoft.modes.exercices.manage
python -m nicsoft.modes.exercices.eco_import

# Sauvegardes
python -m nicsoft.utils.backup_manager                        # backup normal
python -m nicsoft.utils.backup_manager --pin --label "label" # backup pinné (jamais supprimé)
python -m nicsoft.utils.backup_manager --list

# Installation sur nouveau PC
pip install git+https://github.com/AlainDelree/AlChess.git
```

## Architecture

### Flux de données
```
Échiquier USB  →  driver.py (_fen_reader_thread, 50ms)  →  alchess.py  →  server.py  →  navigateur
Navigateur     →  SocketIO action  →  server.py  →  action_queue / menu_queue  →  alchess.py
```

### Fichiers clés
| Fichier | Rôle |
|---------|------|
| `nicsoft/web/alchess.py` | Chef d'orchestre — boucle principale, dispatche selon `_app_state` |
| `nicsoft/web/server.py` | Serveur Flask-SocketIO, expose `event_queue`, `action_queue`, `menu_queue`, `_app_state` |
| `nicsoft/web/static/app.js` | Toute la logique JS frontend |
| `nicsoft/web/templates/index.html` | Interface HTML unique (SPA) |
| `nicsoft/niclink/driver.py` | Driver USB Chessnut Air, thread `_fen_reader_thread` |
| `nicsoft/niclink/_niclink.cpython-*.so` | Extension C++ compilée (EasyLinkSDK) |
| `nicsoft/niclink/virtual_board.py` | Simulation d'échiquier sans hardware |

### Machine d'état (`_app_state`)
```
menu → config / config_humain / retranscription / exercices / labo
     → connecting → playing / paused → game_over → menu
```

### Modes de jeu (dans `nicsoft/modes/`)
- `pedagogique/` — Joueur vs moteur (Stockfish, Maia, Rodent)
- `humain/` — Humain vs Humain
- `exercices/` — Entraînement ouvertures (base SQLite dans `data/`)
- `retranscription/` — Saisie de parties papier
- `labo/` — Analyse libre Stockfish

### Module partagé (`nicsoft/engine/`)
- `engine_manager.py` — Gestion des moteurs UCI (Stockfish, Maia, Rodent)
- `players.py` — Abstraction joueur humain/moteur
- `pgn_manager.py` — Import/export PGN
- `board_utils.py` — Utilitaires python-chess
- `display.py` — Affichage échiquier terminal

### Queues (communication inter-threads)
- `event_queue` : Python → navigateur (événements de jeu)
- `action_queue` : navigateur → Python (actions en cours de partie)
- `menu_queue` : navigateur → Python (choix de mode, config)

## Contraintes techniques critiques

- **USB contention** : tout accès USB passe exclusivement par `_fen_reader_thread`. Ne jamais appeler `get_fen()` depuis un autre thread.
- **`chess.Board(fen)` efface `move_stack`** : reconstruire l'historique depuis `_game_state["history"]` après un tel appel.
- **`move_stack` = source de vérité** pour l'historique des coups.
- **Boucles de polling** : toujours un `time.sleep()` (min 0.05s) pour ne pas monopoliser le GIL.
- **Threads LED en daemon** : ne jamais bloquer la boucle de jeu sur les LEDs.
- **Handler `on_action`** : tout `sendAction({type: X})` en JS doit avoir un `elif atype == "X"` correspondant dans `alchess.py`.

## Workflow Git

```bash
git status                          # avant de commencer
git add <fichiers> && git commit -m "description"   # après chaque étape stable
git push                            # après chaque session stable
git checkout .                      # annuler les modifications non commitées
```

Effectuer un backup pinné avant toute modification importante :
```bash
python -m nicsoft.utils.backup_manager --pin --label "avant-refactoring-X"
```

## Fichiers de suivi

| Fichier | Contenu |
|---------|---------|
| `TACHES.md` | Bugs connus et fonctionnalités à venir |
| `TESTS.md` | Checklist de régression (smoke test + régression complète) |
| `TEST_RESULTATS.md` | Résultats des sessions de test avec dates |
| `HISTORIQUE_BUGS.md` | Bugs résolus avec causes racines |
| `CONTEXTE.md` | Contexte projet (version plus complète de ce fichier) |
| `INSTALLATION_ALCHESS.md` | Guide d'installation (sections 4b/4c pour le quirk USB) |

## Configuration USB (ThinkPad X1 Carbon Gen 7)

Le Chessnut Air nécessite un quirk usbhid :  
`/etc/modprobe.d/chessnut.conf` → `options usbhid quirks=0x2d80:0x8003:0x40`

Le `.so` C++ (`nicsoft/niclink/_niclink.cpython-*.so`) est compilé depuis `src/` avec CMake. Sur nouveau PC, recompiler depuis `src/` selon `INSTALLATION_ALCHESS.md` section 4c.
