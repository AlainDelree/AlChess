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

> **Issue #357** : BUG-001 à BUG-010 vérifiés dans le code actuel (novembre 2026) — toutes les corrections tiennent toujours, et chaque piège encore généralisable (état résiduel au retour menu, balise HTML non fermée) est devenu une ligne de règle dans `architecture.md` ; le récit détaillé de ces dix bugs a donc été retiré d'ici. BUG-011 reste ci-dessous : son récit cite `sys.exit(0)` dans un thread de jeu comme cause d'arrêt de tout le processus Flask, mais `nicsoft/modes/humain/human.py` utilise aujourd'hui encore `sys.exit(0)` pour son propre retour menu sans avoir été converti en `BackMenuExit` — sans pouvoir relancer un serveur réel pour trancher, impossible de confirmer si ce `sys.exit(0)`-là est sans danger (vrai thread `threading.Thread`, `async_mode="threading"`) ou si le risque décrit est toujours vivant. Laissé pour décision d'Alain.

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
