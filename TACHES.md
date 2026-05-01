# NicLink — Tâches et bugs

---

## 🐛 Bugs connus

### Priorité haute
- **Retour menu depuis partie en cours** — cliquer "Retour au menu" pendant une partie pédagogique ne stoppe pas la partie côté serveur. La partie continue en arrière-plan. Bloque le démarrage d'un autre mode sans redémarrer le programme.

- **Écran HH vide** — l'écran Humain vs Humain s'affiche vide dans certaines conditions (état résiduel ?). À reproduire et investiguer. --> Piste à suivre, lors de la creations des menus virtuel on a ajouter HH  mais en virtuel c'est pas vraiment intéressant donc on n'a jamais rien développer.  Le menu HH devait même etre suprimer du mode virtuel (il y est encore)  Peut-etre qu'il y a confusion entre HH physique qui est developpé et HH virtuel qui ne l'est pas

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

- **Quit button** dans le menu principal--> existe deja
- **Analyse libre** — Stockfish suggère les meilleurs coups pour les deux camps sans auto-play
- **Maia Chess** intégration (plus long terme)--> deja fait sauf si c'est pour autre chose que je ne sais pas
- **Intégrer `manage.py`** dans l'interface web pour faciliter la gestion des ouvertures
- **Supprimer les `[DEBUG]` prints** une fois le programme stable

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : nécessite quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation du `.so` depuis `src/`. Voir `INSTALLATION_NICLINK.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, c'est la fonctionnalité de reprise. Ne doit être traité que quand on accède à l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git checkout .` pour annuler les changements non commités.

//Nouveaux bugs ( il faut penser à consulter le fichier log en haut a droite dans le programme)
- Lorsqu'on retourne à l'ecran des menus depuis un module(pedagogique HH ou autre) le clic sur un moment ne réagit pas

//Questions
- Ne peut-on pas créer des Unit Test pour nous aider dans la recherche et résolution de bug?  Ou établir une sorte de procédure.  J'ai l'impression de chercher au hasard
