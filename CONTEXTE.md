# AlChess — Contexte projet (à envoyer en début de nouvelle conversation)

---

## Projet

**Nom** : AlChess (anciennement NicLink)  
**Description** : Application Python/Flask-SocketIO connectant un échiquier physique Chessnut Air (USB) à une interface web pédagogique.  
**Développeur** : Alain (Namur, Belgique) — non développeur de formation, projet créé avec l'aide de Claude/ChatGPT.  
**Stack** : Python backend (Flask-SocketIO), vanilla JS (`app.js`), HTML/CSS (`index.html`), Ubuntu.  
**Dépôt** : `~/NicLink/` avec venv à `~/NicLink/venv/`

---

## Architecture

- **`nicsoft/niclink/driver.py`** — driver USB Chessnut Air, thread dédié `_fen_reader_thread` à 50ms
- **`nicsoft/web/alchess.py`** — chef d'orchestre principal
- **`nicsoft/web/server.py`** — serveur Flask-SocketIO, machine d'état `_app_state`
- **`nicsoft/web/static/app.js`** — toute la logique JS frontend
- **`nicsoft/web/templates/index.html`** — interface HTML
- **`nicsoft/core/game_manager.py`** — gestion de partie (coups, historique, état)
- **`nicsoft/engine/`** — moteurs UCI : `engine_manager.py`, `players.py`, `pgn_manager.py`, `board_utils.py`, `display.py`, `analyse.py`
- **`nicsoft/modes/pedagogique/pedagogique.py`** — mode pédagogique vs Stockfish/Maia/Rodent
- **`nicsoft/modes/humain/human.py`** — mode Humain vs Humain
- **`nicsoft/modes/retranscription/retranscription.py`** — saisie de parties papier
- **`nicsoft/modes/labo/labo.py`** — analyse libre Stockfish
- **`nicsoft/modes/exercices/exercices.py`** — entraînement aux ouvertures
- **`nicsoft/utils/`** — utilitaires : `backup_manager.py`, `timing.py`, `light_board.py`, etc.

## États machine (`_app_state`)
`menu` → `config` / `config_humain` / `retranscription` / `exercices` / `labo` → `connecting` → `playing` / `paused` → `game_over`

## Queues
- `event_queue` : Python → navigateur
- `action_queue` : navigateur → Python (états actifs)
- `menu_queue` : navigateur → Python (état menu)

---

## Conventions de travail

**Toujours faire en début de session :**
1. Lire `TACHES.md` — tâches en cours et bugs connus
2. Lire `TESTS.md` — tests à effectuer
3. Vérifier `git status` avant toute modification

**Workflow Git :**
```bash
git status                    # avant de commencer
git add . && git commit -m "description"   # après chaque étape stable
git checkout .                # pour annuler si ça casse
```

**Backup pinné aux jalons importants :**
```bash
python -m nicsoft.utils.backup_manager --pin --label "description-courte"
```
**Backup pinné à chaque début de session :**
```bash
python -m nicsoft.utils.backup_manager --pin --label "Automatique-Date-Heure"
```
**Démarrer le programme :**
```bash
sudo systemctl stop ModemManager   # si pas automatique
cd ~/NicLink && python -m nicsoft.web
```

**Prérequis USB Chessnut sur ce PC (ThinkPad X1 Carbon Gen 7) :**
- Quirk usbhid : `/etc/modprobe.d/chessnut.conf` → `options usbhid quirks=0x2d80:0x8003:0x40`
- Driver recompilé depuis `~/NicLink/src/`
- Voir `INSTALLATION_ALCHESS.md` sections 4b et 4c

---

## Principes techniques importants

- **USB contention** : tout accès USB passe par `_fen_reader_thread`. Jamais d'appel `get_fen()` direct depuis un autre thread.
- **`move_stack` = source de vérité** pour l'historique des coups.
- **`chess.Board(fen)` efface `move_stack`** — reconstruire l'historique depuis `_game_state["history"]` après.
- **Toujours un `time.sleep()`** dans les boucles de polling (min 0.05s) pour ne pas monopoliser le GIL.
- **Threads LED en daemon** pour ne pas bloquer la boucle de jeu.
- **Handler `on_action`** : vérifier que tout `sendAction({type: X})` JS a un `elif atype == "X"` dans `alchess.py`.

---

## Fichiers de suivi

| Fichier | Contenu |
|---------|---------|
| `TACHES.md` | Bugs connus, refactoring en cours, fonctionnalités à venir |
| `TESTS.md` | Checklist de régression (smoke test + régression complète) |
| `TEST_RESULTATS.md` | Résultats des sessions de test avec dates |
| `HISTORIQUE_BUGS.md` | Bugs résolus avec causes racines et tests de régression |
| `INSTALLATION_ALCHESS.md` | Guide d'installation sur nouveau PC |

---

## État actuel (mis à jour le 23 mai 2026)

**Stable et fonctionnel :**
- Mode Pédagogique (vs Stockfish, Maia, Rodent)
- Mode Humain vs Humain
- Analyse de partie (import PGN, navigation, Stockfish)
- Exercices / Ouvertures
- Retranscription de parties
- Laboratoire (analyse libre)
- Mode virtuel (sans échiquier physique)

**Refactoring ✅ terminé :**
- Structure : `modes/`, `engine/`, `utils/`, `niclink/` conservé
- `__main__.py` allégés → `pedagogique.py`, `human.py`, `alchess.py`, etc.
- CSS extrait dans `static/css/main.css`
- `app.js` commenté par sections
- Renommage NicLink → AlChess dans l'interface
- GitHub : https://github.com/AlainDelree/AlChess

**Bugs actifs prioritaires :**
- Back_menu pendant WAIT_FISH bloque le thread (BUG-011 variant)
- Retour exercices bloqué après ligne complète
- Écran HH vide en mode virtuel (bouton HH à masquer)
- WAIT_FISH intermittent très lent (hardware Chessnut Air)

**Prochaine session — time logs permanents :**
- Remplacer `tlog()` (actif seulement en DEBUG) par un logging structuré toujours actif
- Enregistrer les timings `await_move` et `WAIT_FISH` dans le fichier log
- Sans polluer le terminal en mode normal
