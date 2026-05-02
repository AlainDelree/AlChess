# AlChess — Tâches et bugs

---

## 🐛 Bugs connus

### Priorité haute
- **Retour menu depuis partie en cours** — cliquer "Retour au menu" pendant une partie pédagogique ne stoppe pas la partie côté serveur. La partie continue en arrière-plan. Bloque le démarrage d'un autre mode sans redémarrer le programme.

- **Écran HH vide** — piste identifiée : confusion entre HH physique (développé) et HH virtuel (non développé). Le bouton HH est visible en mode virtuel mais ne mène nulle part. À corriger : masquer HH en mode virtuel.

### Priorité moyenne
- **Contraste visuel** — partiellement corrigé. Reste à faire : (1) bouton "Voir la séquence" peu lisible, (2) bouton "← Retour au menu" contours peu visibles, (3) texte blanc dans config pédagogique (boutons Blancs/Noirs/Aléatoire, moteur, options).

- **Spinner bloqué au démarrage** — occasionnellement, l'écran "Démarrage de NicLink" reste bloqué avec le spinner malgré `board_ok` reçu. Non reproductible de façon fiable.

- **Écran Exercices vide** — s'affiche vide dans certaines conditions (état résiduel d'un mode précédent ?). Semble se corriger au redémarrage.

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

## 🐛 Bugs récents

- **Retour exercices bloqué** — Exercices → Mes lignes → Chigorine ligne 1 → ligne complète → Retour menu → re-cliquer Chigorine ligne 1 → aucune réaction. Bug lié au bouton "retour" en général, apparaît avec d'autres écrans.
- **Annuler Coup Pédagogique** - Patie pédagogique-> Pas de bouton reprendre coup. Si ->Bouton pause-> pas de bouton reprendre le coup et si on recule avec l'historique, ca reprend quand meme au coup sans apporter de modification.
- **Labo Stockfish ne joue pas** Mode Auto ON (libelle Auto OFF) partie deja entammé(sur l'echiquier c4, d4 blanc et d5 noir joué.  Normalement a noir de jouer) Toggle laissé: Je Joue et Tour = blanc et blanc.  Du coup, je joue c4xc5, toggle : Je Joue reste Blanc mais Tour devient Noir.  Aucune réaction de stockfish.
- **Exercice avec echiquier physique**  Le coup de l'ordinateur est montré via des led sur le plateau mais n'apparait sur l'ecran de l'ordinateur que quand le coup est joué sur l'echiquier.
- **HH délai avant d'afficher le coup des blancs** A vérifier
- **Partie pédagogique** délai avant d'afficher le 1er coup blanc
- **Back_menu bloqué pendant WAIT_FISH** — Si une gaffe est faite et que le joueur clique "Retour menu" pendant que le coup de Stockfish est en attente de placement physique (`[WAIT_FISH]`), le thread reste bloqué. Même cause que BUG-011 mais dans `wait_for_stockfish_move()` cette fois. À corriger : vérifier `kill_switch` dans la boucle WAIT_FISH.

