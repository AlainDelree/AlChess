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
- **`nicsoft/web/alchess.py`** — chef d'orchestre principal (ex-`web/__main__.py`)
- **`nicsoft/web/server.py`** — serveur Flask-SocketIO, machine d'état `_app_state`
- **`nicsoft/web/static/app.js`** — toute la logique JS frontend
- **`nicsoft/web/templates/index.html`** — interface HTML
- **`nicsoft/play_pedagogique/pedagogique.py`** — mode pédagogique vs Stockfish
- **`nicsoft/play_human/human.py`** — mode Humain vs Humain
- **`nicsoft/retranscription/retranscription.py`** — saisie de parties papier
- **`nicsoft/labo/labo.py`** — analyse libre Stockfish
- **`nicsoft/exercices/exercices.py`** — entraînement aux ouvertures

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

**Démarrer le programme :**
```bash
sudo systemctl stop ModemManager   # si pas automatique
cd ~/NicLink && python -m nicsoft.web
```

**Prérequis USB Chessnut sur ce PC (ThinkPad X1 Carbon Gen 7) :**
- Quirk usbhid : `/etc/modprobe.d/chessnut.conf` → `options usbhid quirks=0x2d80:0x8003:0x40`
- Driver recompilé depuis `~/NicLink/src/`
- Voir `INSTALLATION_NICLINK.md` sections 4b et 4c

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
| `INSTALLATION_NICLINK.md` | Guide d'installation sur nouveau PC |

---

## État actuel (mis à jour le 2 mai 2026)

**Stable et fonctionnel :**
- Mode Pédagogique (vs Stockfish, Maia, Rodent)
- Mode Humain vs Humain
- Analyse de partie (import PGN, navigation, Stockfish)
- Exercices / Ouvertures
- Retranscription de parties
- Laboratoire (analyse libre)
- Mode virtuel (sans échiquier physique)

**Refactoring en cours :**
- ✅ Étape 1 : modules anciens supprimés, `__main__.py` allégés
- ✅ Étape 5 : `app.js` commenté par sections
- ⏳ Étape 2 : restructuration des dossiers (core/, modes/, engine/)
- ⏳ Étape 3 : extraction du CSS
- ⏳ Renommer NicLink → AlChess dans le code et l'interface

**Bugs actifs prioritaires :**
- Retour menu depuis partie en cours ne stoppe pas le thread serveur
- Retour exercices bloqué (re-cliquer même ligne → aucune réaction)
- Écran HH vide en mode virtuel (bouton HH à masquer en mode virtuel)
