# AlChess — Tâches et bugs

---

## 🐛 Bugs connus

### Priorité basse (existants avant refactoring)
- **2 bips au démarrage** *(en veille)* — réduit de 4 à 2 (commit 216cd09) en espaçant la reconnexion d'1s. Plus gênant en pratique. Même nature que la race condition LEDs (hardware/USB).
- **Race condition LEDs** *(en veille)* — synchronisation des camps LED parfois incorrecte. Rare, se produit même après redémarrage du programme → cause probable hardware/USB, pas logicielle. À surveiller si ça s'aggrave.

---

## 💡 Fonctionnalités à venir

- **Exercices : choix moteur/force pour mode libre** — après fin de ligne, le bouton "Continuer" lance Stockfish à la force de config.json. À faire : proposer un choix de moteur (Stockfish/Maia/Rodent) et de niveau au moment du clic.

- **Labo — mode virtuel non conçu** — l'écran s'affiche (échiquier + composants visibles), mais le mode virtuel n'a pas encore été conçu : aucune interaction ne fonctionne.
- **Intégrer `manage.py`** dans l'interface web pour faciliter la gestion des ouvertures

## 🧪 Stratégie de tests

### Niveau 1 — Checklist de régression manuelle ✅ FAIT
`TESTS.md` créé avec smoke test (5 min) et régression complète (20 min).

### Niveau 2 — Tests d'état serveur ✅ FAIT (commit f68d591, 2026-05-07)
`nicsoft/tests/test_app_state.py` — 25 tests pytest couvrant :
- `set_app_state` : transitions simples, game_over+skip, retour menu
- `on_action` : back_menu depuis tous les états actifs, routage action_queue/menu_queue
- `send_event` : init (reset historique), move (append), undo_move (pop N), game_over
- Lancer : `python -m pytest nicsoft/tests/test_app_state.py -v`
- Note : `test_pgn.py` en erreur (import `build_output_path` disparu) — à corriger séparément

### Niveau 3 — Tests end-to-end Playwright ✅ FAIT (commit c004ffc, 2026-05-07)
`nicsoft/tests/e2e/` — Playwright + Chromium headless, serveur lancé en subprocess, mode virtuel.
12 tests : menu, navigation pédagogique (config→jeu→retour), analyse, exercices, retranscription, transitions.
- Lancer : `python -m pytest nicsoft/tests/e2e/ -v`
- Non couvert : bips hardware, détection position physique (nécessite échiquier réel)

### Niveau 3 — Tests end-to-end Playwright ✅ FAIT (commit c004ffc, 2026-05-07)
`nicsoft/tests/e2e/` — Playwright + Chromium headless, serveur lancé en subprocess, mode virtuel.
12 tests : menu, navigation pédagogique (config→jeu→retour), analyse, exercices, retranscription, transitions.
- Lancer : `python -m pytest nicsoft/tests/e2e/ -v`
- Non couvert : bips hardware, détection position physique (nécessite échiquier réel)

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : nécessite quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation du `.so` depuis `src/`. Voir `INSTALLATION_ALCHESS.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, c'est la fonctionnalité de reprise. Ne doit être traité que quand on accède à l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git checkout .` pour annuler les changements non commités. `git push` pour synchroniser avec GitHub.
- **GitHub** : https://github.com/AlainDelree/AlChess — `git push` après chaque session stable.
- **Logs** : consulter via le bouton 📋 en haut à droite du programme.

## ✅ Bugs résolus récemment

- **Pièces clouées** *(résolu)* — `analyser_position_illegale()` dans `board_utils.py` retourne `"⚠ Ce coup met votre roi en échec — pièce clouée."` pour les coups pseudo-légaux non légaux. ✓

- **Prints debug silencieux** *(commit 33c7b89, 2026-05-08)* — 15 prints informatifs entourés de `if DEBUG_MODE` via `nicsoft/utils/debug.py`. Réactivation : `NICLINK_LOG=DEBUG python -m nicsoft.web`. ✓

- **Beep timing** *(non reproductible, 2026-05-08)* — Le bip sonne maintenant au moment de la gaffe en pédagogique. Probablement résolu par les refactorings récents. ✓ Validé sur plateau physique.

- **En passant** *(commit ae1c6ef, 2026-05-08)* — Notation `exd6 e.p.` ajoutée via `san_ep()` dans `board_utils.py`, remplace `board.san()` dans les 6 fichiers actifs (24 occurrences). ✓

- **Labo — spinner démarrage** *(commit 82b53de, 2026-05-08)* — Overlay "Connexion à l'échiquier…" affiché sur le board jusqu'au 1er FEN USB. Invisible en mode virtuel. ✓ Validé.

- **Labo Stockfish ne joue pas** *(résolu, 2026-05-08)* — Mode Auto ON, Stockfish muet après échange de couleur via toggle. ✓ Résolu.

- **Bips inutiles à l'entrée des écrans** *(non reproductible, 2026-05-07)* — Probablement résolu par les refactorings récents. À surveiller.

- **Écran Exercices vide** *(résolu récemment)* — Non reproductible après tests physique + virtuel (2026-05-06). Probablement lié à un état résiduel qui ne se produit plus après les refactorings récents.

- **Écran HH vide** *(résolu récemment)* — Triple problème : `<div id="screen-config-humain">` manquant dans index.html, état `config_humain` non géré dans app.js, handler `start_humain` manquant dans alchess.py. Voir BUG-009 dans HISTORIQUE_BUGS.md.

- **Modal Retranscription "Sauver et Quitter"** *(résolu récemment)* — bouton Annuler inutile supprimé, texte du chemin PGN affiché directement dans la modal.

- **Mode virtuel réinitialisé au retour menu** *(commit c958300, 2026-05-03)* — `_viderAnalyse()` appelait `toggleVirtualMode(false)` à chaque retour au menu, écrasant le choix de l'utilisateur. Remplacé par `toggleVirtualMode(_virtualMode)` pour conserver l'état courant.

- **Annuler coup pédagogique** *(commit 2d46db3, 2026-05-03)* — Bouton "↩ Annuler le dernier coup" visible dès qu'un tour complet est joué ; "Reprendre" dans la pause manuelle propagé correctement ; `undo_move` met à jour l'historique JS.

- **Contraste modal et écran pos-init** *(commit 4f0b748, 2026-05-03)* — Titre modal en `#e0e0e0` (quasi invisible sur fond `#c2d4e8`) → `#1a2a3a`. Labels "Adversaire"/"Joueur" de l'écran init pédagogique en `#666`/`#ccc` (pale sur `#d8e4f0`) → `#1a2a3a`.



- **Retour menu depuis partie en cours** *(commit 0f43aab + 216cd09, 2026-05-03)* — Le retour menu pendant une partie pédagogique est maintenant fonctionnel dans tous les cas : tour humain, tour Stockfish, et pendant l'attente de placement physique (WAIT_FISH). Corrections : kill_switch testé dans les 4 boucles bloquantes ; thread dédié `_poll_abort` dans WAIT_FISH ; check `_abandon_demande` après WAIT_FISH dans `handle_fish_turn` ; `kill_switch.clear()` après `_check_web_abandon` pour neutraliser les résidus de `nulle`.

- **Back_menu bloqué pendant WAIT_FISH** *(commit 216cd09, 2026-05-03)* — Résolu dans le même lot que ci-dessus.

- **Bips multiples au démarrage** *(commit 216cd09, 2026-05-03)* — Réduit de 4 à 2. Cause : 3 appels simultanés à `_check_board_at_startup` (déclenchés par les 3 events `set_virtual_mode: False` du navigateur) en plus de l'appel initial. Fix : verrou `_board_check_lock` + retries internes séquentiels.

- **[CRASH] BackMenuExit faux positif** *(commit 8b46117, 2026-05-06)* — `BackMenuExit` (exception de contrôle de flux) était catchée par `except Exception` dans la boucle principale péda et loggée comme `[CRASH]`. Aucun crash réel, mais log alarmant. Fix : ajoutée au `except (ExitNicLink, SystemExit, BackMenuExit): raise`.

- **HH délai affichage coup** *(commit 8b46117, 2026-05-06)* — `save_pgn_tmp()` (écriture disque) était appelé avant `send_event("move")`, retardant l'affichage. Fix : send_event en premier, save_pgn ensuite — comme en pédagogique. ✓ Validé.

- **Exercices : bouton Continuer avec Stockfish** *(commit 17dd515, 2026-05-06)* — Après fin de ligne, bouton "Continuer avec Stockfish" apparaît. Le Python (`_run_free`) était déjà complet ; il manquait le JS. Ajout des handlers `exercice_free_mode` / `exercice_free_gameover`, activation de l'échiquier virtuel dans `_exHandlePosition`, garde `_exLaunching` contre les double-clics. ✓ Validé virtuel et physique.

- **Exercice : impossible de relancer après Retour** *(commits fc9a94f→c8a93b2, 2026-05-06)* — Série de bugs imbriqués : (1) `_app_state` restait sur `"exercice_running"` après retour ; (2) race condition `kill_switch.clear()` vs `_watch_actions` bloquait le thread ; (3) le `finally` d'un vieux thread écrasait l'état de la nouvelle session ; (4) `_wait_placement_adv()` ignorait `back_menu` (pas de `_watch_actions` actif pendant le placement adverse). Fix final : lecture directe de `action_queue` dans `_wait_placement_adv`. ✓ Validé.

- **Exercice physique — coup adversaire affiché immédiatement** *(commit 2a8ff6f, 2026-05-06)* — `exercice_adv_move` ne contenait pas le FEN, le JS n'appelait pas `exRenderBoard()`. Fix : fen/from/to ajoutés au event Python, board rendu immédiatement côté JS. ✓ Validé.

---

## 🐛 Bugs récents
- **Partie Nulle Pedagogique physique** *(commits 976188c + 297a687 + 8ad3c7f, 2026-05-07)* — Bouton Nulle grisé pendant WAIT_FISH + pas de feedback si clic sans placer la pièce. Fix : `abandon_nulle_ok` dès le début du tour moteur (élimine clignotement) ; nulle pendant WAIT_FISH évalue immédiatement avec le board interne (sans attendre le placement) ; si refusée, WAIT_FISH reprend. ✓ Validé sur plateau physique.
- **HH délai avant d'afficher le coup** — *(commit 8b46117, 2026-05-06)* — `save_pgn_tmp()` était appelé avant `send_event("move")`, l'I/O disque retardait l'affichage. Corrigé : send_event en premier. ✓ Validé sur plateau physique.
- **Partie pédagogique** — Délai avant d'afficher le 1er coup blanc. *(confirmé résolu en test, 2026-05-06)*
- **WAIT_FISH lent intermittent** — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente). À diagnostiquer via time logs permanents.
