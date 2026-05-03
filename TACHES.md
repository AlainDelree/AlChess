# AlChess — Tâches et bugs

---

## 🐛 Bugs connus

### Priorité haute
- **Écran HH vide** — piste identifiée : confusion entre HH physique (développé) et HH virtuel (non développé). Le bouton HH est visible en mode virtuel mais ne mène nulle part. À corriger : masquer HH en mode virtuel.

### Priorité moyenne

- **Spinner bloqué au démarrage** — occasionnellement, l'écran "Démarrage de NicLink" reste bloqué avec le spinner malgré `board_ok` reçu. Non reproductible de façon fiable.

- **Écran Exercices vide** — s'affiche vide dans certaines conditions (état résiduel d'un mode précédent ?). Semble se corriger au redémarrage.

- **2 bips au démarrage** — réduit de 4 à 2 (commit 216cd09). Le 1er bip vient du `connect()` USB initial qui échoue (plateau pas encore prêt), le 2e vient du retry 1s plus tard qui réussit. Piste : éviter le double appel `_niclink.connect()` en séparant connect et get_fen dans `_check_board_at_startup`.

### Priorité basse (existants avant refactoring)
- **Beep timing** — le bip sonore se déclenche sur la correction plutôt que sur l'erreur
- **En passant** — notation `exd6 e.p.` pas encore implémentée
- **Race condition LEDs** — synchronisation des camps LED parfois incorrecte
- **Pièces clouées** — pas de signal pour coup illégal sur pièce clouée

---

## 💡 Fonctionnalités à venir

- **Labo — à terminer** — mode non finalisé : Stockfish ne joue pas dans tous les cas (voir bug "Labo Stockfish ne joue pas"), comportement des toggles à revoir
- **Analyse libre** — Stockfish suggère les meilleurs coups pour les deux camps sans auto-play (Labo existe mais à confirmer si c'est ça)
- **Intégrer `manage.py`** dans l'interface web pour faciliter la gestion des ouvertures
- **Supprimer les `[DEBUG]` prints** une fois le programme stable
- **Time logs permanents** — remplacer `tlog()` (DEBUG only) par logging structuré toujours actif, timings `await_move` et `WAIT_FISH` dans le fichier log sans polluer le terminal

## 🧪 Stratégie de tests

### Niveau 1 — Checklist de régression manuelle (à faire maintenant)
Créer `TESTS.md` avec les séquences critiques à vérifier après chaque modification :
- Menu → Pédagogique → 2 coups → Retour menu → HH → Démarrer
- Menu → Exercices → ligne complète → Retour → même ligne → réaction ?
- Menu → Analyse → importer PGN → naviguer → Retour menu
- Menu → Retranscription → saisir coups → sauvegarder → reprendre
- Redémarrage programme → vérifier état propre

### Niveau 2 — Tests d'état serveur (moyen terme)
Tester les transitions `_app_state` en Python pur, sans navigateur.
Ex : vérifier que menu → config → playing → back_menu ramène bien à "menu".
Faisable avec `pytest` dans le dossier `tests/` existant.

### Niveau 3 — Tests end-to-end automatisés (long terme)
Utiliser **Playwright** ou **Selenium** pour piloter un vrai navigateur par code.
Simule les clics et vérifie les résultats automatiquement.
Infrastructure plus lourde — à envisager quand le programme est stable et distribué.

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : nécessite quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation du `.so` depuis `src/`. Voir `INSTALLATION_ALCHESS.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, c'est la fonctionnalité de reprise. Ne doit être traité que quand on accède à l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git checkout .` pour annuler les changements non commités. `git push` pour synchroniser avec GitHub.
- **GitHub** : https://github.com/AlainDelree/AlChess — `git push` après chaque session stable.
- **Logs** : consulter via le bouton 📋 en haut à droite du programme.

## ✅ Bugs résolus récemment

- **Retour menu depuis partie en cours** *(commit 0f43aab + 216cd09, 2026-05-03)* — Le retour menu pendant une partie pédagogique est maintenant fonctionnel dans tous les cas : tour humain, tour Stockfish, et pendant l'attente de placement physique (WAIT_FISH). Corrections : kill_switch testé dans les 4 boucles bloquantes ; thread dédié `_poll_abort` dans WAIT_FISH ; check `_abandon_demande` après WAIT_FISH dans `handle_fish_turn` ; `kill_switch.clear()` après `_check_web_abandon` pour neutraliser les résidus de `nulle`.

- **Back_menu bloqué pendant WAIT_FISH** *(commit 216cd09, 2026-05-03)* — Résolu dans le même lot que ci-dessus.

- **Bips multiples au démarrage** *(commit 216cd09, 2026-05-03)* — Réduit de 4 à 2. Cause : 3 appels simultanés à `_check_board_at_startup` (déclenchés par les 3 events `set_virtual_mode: False` du navigateur) en plus de l'appel initial. Fix : verrou `_board_check_lock` + retries internes séquentiels.

---

## 🐛 Bugs récents

- **L'ecriture sur la modale est trop pale lors du clic sur "Retour menu" de partie pédagogique virtuel** (pas vérifié les autres)
- **Retour exercices bloqué** — Exercices → Mes lignes → Chigorine ligne 1 → ligne complète → Retour menu → re-cliquer Chigorine ligne 1 → aucune réaction. Bug lié au bouton "retour" en général, apparaît avec d'autres écrans.
- **Annuler Coup Pédagogique** — Partie pédagogique → Pas de bouton reprendre coup. Si → Bouton pause → pas de bouton reprendre le coup et si on recule avec l'historique, ça reprend quand même au coup sans apporter de modification.
- **Labo Stockfish ne joue pas** — Mode Auto ON (libellé Auto OFF) partie déjà entamée. Toggle laissé : Je Joue et Tour = blanc et blanc. Après c4xc5, toggle : Je Joue reste Blanc mais Tour devient Noir. Aucune réaction de Stockfish.
- **Exercice avec échiquier physique** — Le coup de l'ordinateur est montré via des LEDs sur le plateau mais n'apparaît sur l'écran que quand le coup est joué sur l'échiquier.
- **HH délai avant d'afficher le coup des blancs** — À vérifier.
- **Partie pédagogique** — Délai avant d'afficher le 1er coup blanc.
- **WAIT_FISH lent intermittent** — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente). À diagnostiquer via time logs permanents.
- **Écran init de pédagogique illisible** — Le nom de joueur dans l'écran init de pédagogique (quand on commence le jeu avec un échiquier non rangé) n'est pas suffisamment visible.
