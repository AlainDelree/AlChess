# NicLink — Tâches et bugs

---

## 🐛 Bugs connus

### Priorité haute
- **Retour menu depuis partie en cours** — cliquer "Retour au menu" pendant une partie pédagogique ne stoppe pas la partie côté serveur. La partie continue en arrière-plan. Bloque le démarrage d'un autre mode sans redémarrer le programme.

- **Écran HH vide** — piste identifiée : confusion entre HH physique (développé) et HH virtuel (non développé). Le bouton HH est visible en mode virtuel mais ne mène nulle part. À corriger : masquer HH en mode virtuel.

### Priorité moyenne
- **Contraste visuel** — certains boutons et libellés peu lisibles avec les couleurs actuelles (ex: bouton Pause grisé qui se fond dans le fond). À revoir dans le CSS.

- **Spinner bloqué au démarrage** — occasionnellement, l'écran "Démarrage de NicLink" reste bloqué avec le spinner malgré `board_ok` reçu. Non reproductible de façon fiable.

- **Écran Exercices vide** — s'affiche vide dans certaines conditions (état résiduel d'un mode précédent ?). Semble se corriger au redémarrage.

### Priorité basse (existants avant refactoring)
- **Beep timing** — le bip sonore se déclenche sur la correction plutôt que sur l'erreur
- **En passant** — notation `exd6 e.p.` pas encore implémentée
- **Race condition LEDs** — synchronisation des camps LED parfois incorrecte
- **Pièces clouées** — pas de signal pour coup illégal sur pièce clouée

---

## 🔨 Refactoring structure (chantier en cours)

### Étape 1 — Nettoyage ✅
- [x] Git initialisé
- [x] `play_stockfish/` supprimé
- [x] `play_menu/` supprimé  
- [x] `lichess/` supprimé
- [x] Sources driver C copiées dans `src/`
- [x] `INSTALLATION_NICLINK.md` mis à jour (quirk usbhid + recompilation .so)

### Étape 2 — Renommage des `__main__.py` internes ✅
- [x] `play_human/__main__.py` → `human.py`
- [x] `play_pedagogique/__main__.py` → `pedagogique.py`
- [x] `retranscription/__main__.py` → `retranscription.py`
- [x] `labo/__main__.py` → `labo.py`
- [x] `exercices/__main__.py` → `exercices.py`
- [x] `web/__main__.py` → `alchess.py` (nom du programme)

### Étape 3 — Restructuration des dossiers
Structure cible :
```
nicsoft/
├── core/          (ex-niclink/)
├── modes/
│   ├── pedagogique/
│   ├── humain/
│   ├── analyse/   (ex-retranscription/)
│   ├── exercices/
│   └── labo/
├── engine/        (ex-game/)
├── tools/         (scripts admin ex-exercices/)
├── web/
└── utils/
```

### Étape 4 — CSS extrait
- [ ] Extraire le CSS inline de `index.html` vers `static/css/main.css`

### Étape 5 — JS commenté par sections ✅
- [x] Séparateurs `// ──` harmonisés dans `app.js`

---

## 💡 Fonctionnalités à venir

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

- **USB Chessnut sur nouveau PC** : nécessite quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation du `.so` depuis `src/`. Voir `INSTALLATION_NICLINK.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, c'est la fonctionnalité de reprise. Ne doit être traité que quand on accède à l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git checkout .` pour annuler les changements non commités.
- **Logs** : consulter via le bouton 📋 en haut à droite du programme.

## 🐛 Bugs récents

- **Retour exercices bloqué** — Exercices → Mes lignes → Chigorine ligne 1 → ligne complète → Retour menu → re-cliquer Chigorine ligne 1 → aucune réaction. Bug lié au bouton "retour" en général, apparaît avec d'autres écrans.
