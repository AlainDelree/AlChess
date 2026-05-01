# NicLink — Tâches et bugs

---

## 🐛 Bugs connus

### Priorité haute
- **Retour menu depuis partie en cours** — cliquer "Retour au menu" pendant une partie pédagogique ne stoppe pas la partie côté serveur. La partie continue en arrière-plan. Bloque le démarrage d'un autre mode sans redémarrer le programme.

- **Écran HH vide** — l'écran Humain vs Humain s'affiche vide dans certaines conditions (état résiduel ?). À reproduire et investiguer.

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

### Étape 2 — Renommage des `__main__.py` internes
- [ ] Chaque module garde `__main__.py` comme point d'entrée minimal
- [ ] La logique est déplacée dans un fichier au nom explicite (ex: `game.py`, `session.py`)

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

### Étape 5 — JS commenté par sections
- [ ] Ajouter des séparateurs clairs dans `app.js` par écran

---

## 💡 Fonctionnalités à venir

- **Quit button** dans le menu principal
- **Analyse libre** — Stockfish suggère les meilleurs coups pour les deux camps sans auto-play
- **Maia Chess** intégration (plus long terme)
- **Intégrer `manage.py`** dans l'interface web pour faciliter la gestion des ouvertures
- **Supprimer les `[DEBUG]` prints** une fois le programme stable

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : nécessite quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation du `.so` depuis `src/`. Voir `INSTALLATION_NICLINK.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, c'est la fonctionnalité de reprise. Ne doit être traité que quand on accède à l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git checkout .` pour annuler les changements non commités.
