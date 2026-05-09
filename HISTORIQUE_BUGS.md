# AlChess — Historique des bugs résolus

Ce fichier sert à trois choses :
1. Ne pas réintroduire des bugs déjà résolus
2. Identifier les patterns récurrents
3. Générer des tests de régression ciblés

---

## Format

**ID** : BUG-NNN  
**Date** : approximative  
**Fichiers touchés** : liste  
**Symptôme** : ce que l'utilisateur voyait  
**Cause racine** : pourquoi ça cassait  
**Correction** : ce qui a été fait  
**Test de régression** : séquence à rejouer pour vérifier

---

## Bugs résolus

### BUG-001 — Écran position initiale vide (écran bleu)
**Date** : mars 2026  
**Fichiers** : `index.html`  
**Symptôme** : Au démarrage d'une partie pédagogique avec erreur de position, écran bleu vide au lieu de l'échiquier avec pièces mal placées en rouge.  
**Cause racine** : `#screen-pos-init` était imbriqué à l'intérieur de `#screen-game` qui avait `display:none`. Un `</div>` manquant faisait que la div de position héritait du `display:none` parent.  
**Correction** : Ajout du `</div>` manquant pour fermer `#screen-game` avant `#screen-pos-init`.  
**Test** : Démarrer partie pédagogique avec pièces mal placées → vérifier que l'échiquier avec cases rouges s'affiche.

---

### BUG-002 — Bouton "Analyser" engloutissait les boutons suivants
**Date** : mars 2026  
**Fichiers** : `index.html`  
**Symptôme** : Les boutons après "Analyser" dans l'écran game_over ne répondaient pas aux clics.  
**Cause racine** : `<button id="btn-analyser">` n'était pas fermé — il englobait silencieusement tous les éléments suivants.  
**Correction** : Ajout du `</button>` manquant.  
**Test** : Fin de partie → écran game_over → vérifier que tous les boutons (Analyser, Retour, Sauvegarder) répondent.

---

### BUG-003 — Flash de l'écran pédagogique au lancement
**Date** : mars 2026  
**Fichiers** : `web/__main__.py` (maintenant `alchess.py`), `app.js`, `index.html`  
**Symptôme** : L'écran de jeu apparaissait brièvement avant que l'échiquier soit prêt, puis disparaissait.  
**Cause racine** : `_launch_pedagogique` émettait `"playing"` immédiatement, avant `wait_for_initial_position`.  
**Correction** : Ajout de l'état `"connecting"` — le navigateur affiche un spinner pendant que le plateau s'initialise. `"playing"` n'est émis qu'après `wait_for_initial_position`.  
**Test** : Lancer une partie pédagogique → vérifier que le spinner s'affiche, puis l'écran de jeu sans flash.

---

### BUG-004 — Dialogue de confirmation affichait l'URL (127.0.0.1:5000)
**Date** : mars 2026  
**Fichiers** : `index.html`, `app.js`  
**Symptôme** : `window.confirm()` affichait "127.0.0.1:5000 dit : Abandonner ?" — titre peu professionnel.  
**Cause racine** : Utilisation de `window.confirm()` natif du navigateur.  
**Correction** : Remplacement par une modal HTML custom avec `ouvrirModal()` / `fermerModal()`.  
**Test** : Cliquer "Abandonner" en cours de partie → vérifier que la modal s'affiche proprement.

---

### BUG-005 — Retour au menu depuis analyse réouvre la partie précédente
**Date** : mars-avril 2026  
**Fichiers** : `app.js`  
**Symptôme** : Après une partie, retour au menu, puis clic sur "Analyse de partie" → la partie précédente s'affiche au lieu d'un écran vierge.  
**Cause racine** : `_gameSource` restait à `"niclink"` au retour menu, ce qui empêchait l'appel à `_viderAnalyse()`.  
**Correction** : Réinitialiser `_gameSource = "externe"` systématiquement au retour menu, puis appeler `_viderAnalyse()`.  
**Test** : Partie pédagogique → Retour menu → cliquer "Analyse de partie" → vérifier écran vide.

---

### BUG-006 — Dégriser les boutons du menu non fiable (~4/10)
**Date** : mars 2026  
**Fichiers** : `app.js`, `index.html`  
**Symptôme** : Après connexion de l'échiquier, les boutons du menu restaient grisés environ 6 fois sur 10.  
**Cause racine** : Race condition dans la détection USB — difficile à éliminer proprement.  
**Correction** : Ajout d'un bouton "⟳ Reconnecter l'échiquier" visible en cas d'échec, qui relance `_check_board_at_startup`. Approche UX plutôt que correction de la race condition.  
**Test** : Démarrer sans échiquier → brancher → vérifier dégrisation OU cliquer "Reconnecter".

---

### BUG-007 — LEDs lentes (4-10s par tour)
**Date** : avril 2026  
**Fichiers** : `driver.py`, `play_pedagogique/pedagogique.py`  
**Symptôme** : Signal de début de tour (bip + LEDs) prenait 4 à 10 secondes.  
**Cause racine** : USB Chessnut Air intrinsèquement lent pour les LEDs (8 appels USB ~0.5-1s chacun). De plus, `turn_off_all_leds` et `signal_lights` se chevauchaient via le `_led_lock`.  
**Correction** : Ajout d'un mutex USB dans `driver.py` + flag `_leds_stop` pour interrompre `signal_lights` dès que le coup arrive. Appels LED en thread daemon.  
**Test** : Jouer 3 coups en partie pédagogique → vérifier que le signal de tour arrive en < 2s.

---

### BUG-008 — Messages contradictoires dans le Labo
**Date** : avril 2026  
**Fichiers** : `app.js`  
**Symptôme** : "Reproduisez cette position sur le plateau ✓ Synchronisé avec le plateau physique." — les deux messages s'affichaient simultanément.  
**Cause racine** : `labo_copy_start` n'effaçait pas `labo-last-move` avant d'afficher le nouveau message.  
**Correction** : Ajout de `lastEl.textContent = ""` dans le handler `labo_copy_start`.  
**Test** : Labo → copier position → vérifier qu'un seul message s'affiche à la fois.

---

### BUG-009 — Écran HH vide / HH ne démarrait pas
**Date** : mai 2026  
**Fichiers** : `index.html`, `app.js`, `web/alchess.py`  
**Symptôme** : Cliquer sur "Humain vs Humain" affichait un écran vide.  
**Cause racine** : Triple problème — (1) `<div id="screen-config-humain">` manquant dans `index.html`, (2) état `config_humain` non géré dans `app.js`, (3) handler `start_humain` manquant dans `alchess.py`.  
**Correction** : Restauration du panneau HTML depuis backup, ajout de la ligne `config_humain` dans le handler `app_state`, ajout de `elif atype == "start_humain": _launch_humain(action)`.  
**Test** : Menu → HH → vérifier que le panneau config s'affiche → remplir noms → Démarrer → vérifier que la partie commence.

---

### BUG-010 — Driver Chessnut non reconnu comme HID sur nouveau PC
**Date** : mai 2026  
**Fichiers** : `/etc/modprobe.d/chessnut.conf` (config système)  
**Symptôme** : `Error: Can not connect to the chess board` malgré `lsusb` qui voit le Chessnut. Absent de `/sys/bus/hid/devices/`.  
**Cause racine** : Le kernel ne bindait pas automatiquement le Chessnut comme device HID (interface déclarée comme "Keyboard" avec `bDeviceClass 0`).  
**Correction** : Quirk usbhid `0x40` + recompilation du `.so` depuis les sources C.  
**Commande** : `echo 'options usbhid quirks=0x2d80:0x8003:0x40' | sudo tee /etc/modprobe.d/chessnut.conf && sudo update-initramfs -u`  
**Test** : Reboot → brancher Chessnut → `ls /sys/bus/hid/devices/ | grep 2D80` doit retourner un résultat.

---

## Patterns identifiés

1. **État non nettoyé au retour menu** — BUG-005, BUG-009, BUG-011. Pattern récurrent : une variable JS ou Python conserve l'état d'une session précédente, ou un thread reste bloqué. → Tester systématiquement les transitions retour menu.

5. **`sys.exit()` dans un thread tue tout le processus** — BUG-011. Utiliser des exceptions custom (`BackMenuExit`) pour sortir proprement d'un thread sans tuer Flask. → Ne jamais appeler `sys.exit()` dans un thread de jeu, sauf pour erreur fatale.

2. **HTML structural** — BUG-001, BUG-002. Des `</div>` ou `</button>` manquants causent des bugs silencieux difficiles à diagnostiquer. → Valider le HTML avec les DevTools après chaque modification de `index.html`.

3. **Race conditions USB/threading** — BUG-006, BUG-007. L'USB du Chessnut est lent et partagé entre threads. → Toujours passer par le thread dédié, jamais d'appel USB direct.

4. **Handler manquant côté serveur** — BUG-009. Une action JS envoyée sans handler Python correspondant est ignorée silencieusement. → Vérifier que tout `sendAction({type: X})` a un `elif atype == "X"` dans `alchess.py`.

---

### BUG-011 — Retour menu bloque le programme (impossible de relancer un mode)
**Date** : mai 2026  
**Fichiers** : `web/server.py`, `modes/pedagogique/pedagogique.py`, `web/alchess.py`  
**Symptôme** : Après "Retour au menu" depuis une partie en cours, impossible de relancer un mode (pédagogique, HH, exercices). Les clics sont ignorés indéfiniment.  
**Cause racine** : Double problème — (1) Dans `server.py`, `on_action` appelait `set_app_state("menu")` AVANT de vérifier si `_app_state` était dans les états actifs. Résultat : `_app_state` valait déjà `"menu"` au moment de la condition, donc `back_menu` n'arrivait jamais dans `action_queue`. Le thread de jeu ne recevait jamais le signal d'arrêt et restait bloqué dans `await_move()`. (2) Dans `pedagogique.py`, `_end_game` appelait `sys.exit(0)` pour le retour menu, ce qui tuait tout le processus Flask au lieu de simplement terminer le thread.  
**Correction** :  
- `server.py` : sauvegarder `prev_state = _app_state` avant `set_app_state("menu")`, puis vérifier `prev_state` dans la condition.  
- `pedagogique.py` : remplacer `sys.exit(0)` par `raise BackMenuExit()` (nouvelle exception custom), exclure `BackMenuExit` du handler `[CRASH]`.  
- `alchess.py` : importer `BackMenuExit` et l'attraper dans `_run_pedagogique` sans relancer.  
**Test** : Partie pédagogique → jouer 2 coups → Retour menu → immédiatement relancer Pédagogique → vérifier que la partie démarre sans délai. Répéter avec HH et Exercices.

---

## Bugs résolus — mai 2026 (lot 2)

- **Bip parasite à l'entrée Retranscription** *(0c78402, 2026-05-09)* — `_check_board_at_startup` ne vérifie plus l'app_state avant de connecter le hardware. Fix : check `_app_state == "menu"` après le sleep d'1s. Cause : race condition entre navigation rapide et reconnexion USB.

- **HH config — doublon aléatoire** *(2026-05-09)* — Case à cocher "aléatoire" redondante avec le bouton Aléatoire dans l'écran config HH. Supprimée.

- **Corbeille Analyse — série de bugs** *(f874bda→0c3291a, 2026-05-09)* — (1) bouton grisé après import PGN ; (2) dropdown clippé par overflow:hidden ; (3) dropdown s'ouvre vers le haut ; (4) label sélectionné invisible ; (5) couleurs illisibles fond sombre ; (6) `_basketSource` réinitialisé par reconnexion SocketIO.

- **Partie Nulle Pédagogique physique** *(976188c+297a687+8ad3c7f, 2026-05-07)* — Bouton Nulle grisé pendant WAIT_FISH. Fix : `abandon_nulle_ok` émis dès le début du tour moteur ; nulle pendant WAIT_FISH évaluée avec le board interne sans attendre le placement.

- **Prints debug silencieux** *(33c7b89, 2026-05-08)* — 15 prints entourés de `if DEBUG_MODE` via `nicsoft/utils/debug.py`. Réactivation : `NICLINK_LOG=DEBUG`.

- **En passant** *(ae1c6ef, 2026-05-08)* — Notation `exd6 e.p.` via `san_ep()` dans `board_utils.py`, remplace `board.san()` (24 occurrences sur 6 fichiers).

- **Labo — spinner démarrage** *(82b53de, 2026-05-08)* — Overlay "Connexion…" affiché jusqu'au 1er FEN USB. Invisible en mode virtuel.

- **Labo Stockfish muet après toggle couleur** *(2026-05-08)* — Mode Auto ON, Stockfish ne jouait plus après échange de couleur.

- **Pièces clouées** — `analyser_position_illegale()` dans `board_utils.py` détecte les coups pseudo-légaux non légaux.

- **[CRASH] BackMenuExit faux positif** *(8b46117, 2026-05-06)* — Exception de contrôle de flux catchée comme crash. Fix : ajoutée au `except (ExitNicLink, SystemExit, BackMenuExit): raise`.

- **HH délai affichage coup** *(8b46117, 2026-05-06)* — `save_pgn_tmp()` avant `send_event("move")` retardait l'affichage. Fix : send_event en premier.

- **Exercices : bouton Continuer avec Stockfish** *(17dd515, 2026-05-06)* — Handlers JS `exercice_free_mode` / `exercice_free_gameover` manquants.

- **Exercice : impossible de relancer après Retour** *(fc9a94f→c8a93b2, 2026-05-06)* — Série de 4 bugs imbriqués (state résiduel, race condition kill_switch, finally vieux thread, wait_placement_adv sourd au back_menu).

- **Exercice physique — coup adversaire non affiché** *(2a8ff6f, 2026-05-06)* — FEN manquant dans `exercice_adv_move`, JS n'appelait pas `exRenderBoard()`.

- **Mode virtuel réinitialisé au retour menu** *(c958300, 2026-05-03)* — `toggleVirtualMode(false)` écrasait le choix utilisateur. Fix : `toggleVirtualMode(_virtualMode)`.

- **Annuler coup pédagogique** *(2d46db3, 2026-05-03)* — Bouton visible dès un tour complet joué ; `undo_move` met à jour l'historique JS.

- **Retour menu depuis partie en cours** *(0f43aab+216cd09, 2026-05-03)* — Fonctionnel dans tous les cas : tour humain, tour Stockfish, WAIT_FISH.

- **Bips multiples au démarrage** *(216cd09, 2026-05-03)* — Réduit de 4 à 2. Fix : verrou `_board_check_lock`.
