# AlChess — Spécifications du projet

> Document de référence décrivant le comportement attendu de l'application.  
> Dernière mise à jour : 2026-05-19

---

## 1. Vue d'ensemble

**AlChess** est une application locale Python/Flask-SocketIO qui connecte un échiquier physique **Chessnut Air** (USB) à une interface web servie sur `localhost`. Elle offre plusieurs modes d'entraînement aux échecs : jouer contre un moteur, jouer à deux sur le même échiquier, s'entraîner aux ouvertures, analyser des parties et retranscrire des parties papier.

**Utilisateur cible** : joueur d'échecs amateur souhaitant utiliser son échiquier physique avec des outils d'analyse et d'entraînement, sans connexion internet.

**Philosophie** :
- Tout se passe en local (pas de serveur distant, pas de compte).
- L'échiquier physique est la source de vérité pour les coups joués.
- Un mode virtuel (sans échiquier physique) est disponible pour tous les modes sauf Humain vs Humain.

---

## 2. Environnement et matériel

### Système requis
- Ubuntu 22.04 ou 24.04 (x86_64)
- Python 3.12+
- Navigateur web moderne (Chrome/Firefox)

### Matériel supporté
- **Chessnut Air** — `idVendor=2d80`, `idProduct=8003` (USB)
- Chessnut Air+ : `idProduct` différent, à vérifier avec `lsusb | grep 2d80`

### Démarrage
```bash
cd ~/NicLink && source venv/bin/activate
python -m nicsoft.web          # normal
NICLINK_LOG=DEBUG python -m nicsoft.web  # mode debug
```

L'application s'ouvre automatiquement dans le navigateur sur `http://localhost:5000`.

---

## 3. Architecture technique

### Flux de données
```
Échiquier USB  →  driver.py (thread 50ms)  →  alchess.py  →  server.py  →  navigateur
Navigateur     →  SocketIO action           →  server.py   →  queues     →  alchess.py
```

### Composants principaux

| Fichier | Rôle |
|---------|------|
| `nicsoft/web/alchess.py` | Chef d'orchestre — boucle principale, dispatch par `_app_state` |
| `nicsoft/web/server.py` | Serveur Flask-SocketIO, expose les queues et l'état global |
| `nicsoft/web/static/app.js` | Toute la logique frontend (SPA vanilla JS) |
| `nicsoft/web/templates/index.html` | Interface HTML unique |
| `nicsoft/niclink/driver.py` | Driver USB Chessnut Air — thread `_fen_reader_thread` |
| `nicsoft/niclink/_niclink.cpython-*.so` | Extension C++ compilée (EasyLinkSDK) |
| `nicsoft/niclink/virtual_board.py` | Simulation d'échiquier sans hardware |

### Machine d'état (`_app_state`)
```
menu
  ├─ config           → connecting → playing ↔ paused → game_over → menu
  ├─ config_humain    → connecting → playing ↔ paused → game_over → menu
  ├─ retranscription  → (retranscription en cours) → menu
  ├─ exercices        → (exercice en cours) → menu
  ├─ labo             → (analyse libre) → menu
  └─ outils_exercices → (outils) → menu
```

### Queues (communication inter-threads)
- `event_queue` : Python → navigateur (événements de jeu)
- `action_queue` : navigateur → Python (actions en cours de partie)
- `menu_queue` : navigateur → Python (choix de mode, configuration)

### Contraintes techniques critiques
- **USB** : tout accès à l'échiquier passe exclusivement par `_fen_reader_thread`. Ne jamais appeler `get_fen()` depuis un autre thread.
- **`chess.Board(fen)`** efface `move_stack` — reconstruire l'historique depuis `_game_state["history"]` après un tel appel.
- **`move_stack`** est la source de vérité pour l'historique des coups.
- Toute boucle de polling doit contenir un `time.sleep()` (min 0.05s) pour ne pas monopoliser le GIL.
- Les threads LED sont des daemons — ils ne bloquent pas la boucle de jeu.

---

## 4. Moteurs d'échecs

| Moteur | Description | Source |
|--------|-------------|--------|
| **Stockfish** | Moteur de référence, force configurable par ELO | `apt install stockfish` |
| **Maia** | Réseau de neurones mimant le jeu humain (1200–1800 ELO) | Poids `.pb.gz` inclus |
| **Rodent IV** | Moteur à personnalité configurable | Binaire inclus |

Tous les moteurs sont gérés via le protocole UCI par `nicsoft/engine/engine_manager.py`.

---

## 5. Modes de fonctionnement

### 5.1 Mode Pédagogique (Joueur vs moteur)

**Objectif** : jouer une partie contre un moteur avec feedback pédagogique à chaque coup.

**Configuration** :
- Moteur : Stockfish / Maia (1200–1800) / Rodent IV
- Niveau ELO (Stockfish et Rodent uniquement)
- Couleur du joueur (Blancs / Noirs / Aléatoire)
- Durée de pause entre les coups (0–5s)
- Analyse en temps réel : activable/désactivable

**Comportement en partie** :
- Le joueur joue son coup sur l'échiquier physique (ou virtuel).
- Le moteur calcule et joue son coup → les LEDs indiquent le coup à reproduire sur l'échiquier.
- État `WAIT_FISH` : le programme attend que le joueur reproduise le coup du moteur. Si des pièces sont mal placées, un message d'avertissement doit s'afficher (bug connu : pas de feedback UI actuellement).
- Chaque coup joué par le joueur est analysé (si l'analyse est active) : brillant / bon / imprécision / erreur / blunder.
- Le delta centipawn s'affiche à chaque coup.

**Fin de partie** :
- Échec et mat, abandon, pat, nulle par accord, manque de matériel.
- Écran `game_over` avec résumé (résultat, raison, historique des coups avec qualité).
- Boutons : Analyser / Nouvelle partie / Retour menu.

**Undo** :
- Le joueur peut annuler le dernier coup (commande `undo`).
- Si l'undo concerne un coup du moteur : retirer la pièce déplacée, replacer la pièce capturée.
- Si l'undo concerne un coup du joueur : replacer la pièce.

---

### 5.2 Mode Humain vs Humain (HH)

**Objectif** : deux joueurs physiques s'affrontent sur le même échiquier, avec arbitrage automatique de la légalité des coups.

**Configuration** :
- Noms des deux joueurs (Blancs / Noirs)
- Type de partie (Sérieuse / Détendue)
- Cadence de jeu (optionnel)

**Comportement** :
- Le programme détecte chaque coup joué sur l'échiquier et vérifie sa légalité.
- Tour par tour : indication du camp à jouer.
- Propose le meilleur coup (Stockfish) sur demande — disponible pendant la pause.
- Pause : fige l'état, masque le plateau, protège la position.

**Fin de partie** :
- Même écran `game_over` que le mode pédagogique.
- Accès à l'analyse Stockfish après la partie.

---

### 5.3 Exercices d'ouvertures

**Objectif** : s'entraîner aux ouvertures sur des lignes prédéfinies (catalogue personnel ou livres Polyglot).

**Sources de lignes** :
- Catalogue personnel (`data/mes_lignes.json`) — lignes PGN importées
- Livres Polyglot (`.bin`) — fichiers de coups pondérés

**Comportement** :
- Le joueur choisit une ouverture dans la liste du panneau gauche.
- Il joue les coups sur l'échiquier — le "livre" répond automatiquement.
- En cas de coup hors ligne : signal d'erreur, pas de pénalité, le coup est annulé.
- À la fin d'une ligne : message de félicitation, option de rejouer ou de choisir une autre ligne.

**Drill** : répétition d'une même ligne jusqu'à la maîtriser.

**Catalogue** : géré via le module Outils Exercices (voir §5.6).

---

### 5.4 Analyse de partie

**Objectif** : naviguer coup par coup dans une partie importée ou jouée, avec analyse Stockfish.

**Import** :
- Fichier PGN (depuis Chess.com, Lichess, etc.)
- Partie précédemment jouée dans AlChess

**Navigation** :
- Coup précédent / suivant / premier / dernier
- Flip du plateau (inverser la perspective)

**Analyse** :
- Lancer l'analyse Stockfish sur toute la partie
- Affichage des qualités de coups (brillant / bon / imprécision / erreur / blunder)
- Delta centipawn visible sur chaque coup

**Export** :
- Sauvegarde PGN avec annotations de qualité
- Dossiers : Serious / Casual / Pedagogical / Human / Transcription

---

### 5.5 Retranscription PGN

**Objectif** : retranscrire une partie jouée sur papier (ou de mémoire) en jouant les coups sur l'échiquier virtuel.

**Comportement** :
- Saisie coup par coup via l'échiquier virtuel.
- Historique en tableau Blancs/Noirs en temps réel.
- Reprise automatique proposée au démarrage si une retranscription était en cours.

**Export** : PGN avec métadonnées (joueurs, date, résultat).

---

### 5.6 Laboratoire (analyse libre)

**Objectif** : explorer librement n'importe quelle position avec l'aide de Stockfish.

**Comportement** :
- Échiquier libre — placer les pièces dans n'importe quelle configuration.
- Demander le meilleur coup à Stockfish pour l'un ou l'autre camp.
- Mode auto : Stockfish joue automatiquement pour les deux camps.
- Undo disponible à tout moment.
- Copier la position → affichage "Reproduisez cette position" pour synchroniser l'échiquier physique.

**Mode virtuel** : entièrement fonctionnel sans échiquier physique.

---

### 5.7 Outils Exercices

**Objectif** : gérer le catalogue d'ouvertures personnel.

**Fonctionnalités** :
- **Importer PGN** : importer des fichiers `.pgn` dans `mes_lignes.json`
- **Convertir SAN → UCI** : coller du PGN et obtenir les codes UCI pour le champ `InitMoves`
- **Importer depuis ECO Lichess** : filtrer par code ECO et importer dans le catalogue
- **Explorer un livre Polyglot** : naviguer dans un `.bin`, consulter les coups pondérés
- **Ajouter une ouverture** : formulaire manuel (nom, camp, coups UCI, description)
- **Modifier une ouverture** : rechercher et éditer les champs d'une ouverture existante
- **Mettre à jour eco_hierarchy.json** : télécharger la hiérarchie ECO depuis Wikipedia

---

## 6. Interface utilisateur

### Structure générale
- SPA (Single Page Application) — une seule page HTML, les vues sont affichées/masquées par JS.
- Accès via `http://localhost:5000`.
- Sélecteur de langue en haut à droite (FR / EN / DE).

### Composants permanents
- **Header** : logo AlChess, statut connexion échiquier, sélecteur langue, bouton logs, bouton save
- **Toast** : notifications temporaires (succès, erreur, info) — 4s, coin inférieur
- **Spinner de démarrage** : overlay affiché pendant le chargement initial

### Menu principal
Boutons split (♟ physique | 🖥 virtuel) pour :
- Mode Pédagogique
- Laboratoire
- Exercices

Boutons simples :
- Humain vs Humain (physique uniquement)
- Analyse de partie
- Retranscrire
- Outils Exercices

Les boutons marqués `data-needs-board` sont désactivés si l'échiquier physique n'est pas détecté.

### Panneau de jeu (pendant une partie)
- Échiquier (physique ou virtuel) au centre
- Panneau gauche : informations contextuelles selon le mode
- Panneau droit : actions disponibles (Abandonner, Pause, Undo, Voir meilleur coup…)
- Indicateur de tour et feedback du dernier coup

### Écran game_over
- Résultat (victoire / défaite / nulle)
- Raison (échec et mat / abandon / pat / nulle par accord…)
- Historique des coups avec qualité
- Navigation dans la partie terminée (review)

---

## 7. Internationalisation (i18n)

**Langues** : Français (FR), Anglais (EN), Allemand (DE)  
**Langue par défaut** : Anglais (EN) pour un nouvel utilisateur  
**Persistence** : cookie `alchess_locale` + `localStorage`

### Règles absolues
- HTML : toujours `data-i18n="ma.cle"` (jamais de texte hardcodé)
- JS : toujours `t("ma.cle")` pour le texte dynamique
- Python : toujours `message_key` / `title_key` / `reason_key` en plus du texte de fallback
- Toute nouvelle clé doit être ajoutée simultanément dans `fr.json`, `en.json` et `de.json`
- Si la traduction allemande est incertaine → utiliser la valeur anglaise

### Fichiers de traduction
```
nicsoft/web/static/i18n/
  fr.json   (515 clés)
  en.json   (515 clés)
  de.json   (515 clés)
```

### Notation des coups
La fonction `sanToLang()` traduit la notation SAN en langage naturel :
- FR : "Cavalier en e5", "prend en", "Grand roque"
- EN : "Knight to e5", "takes", "Long castling"
- DE : "Springer nach e5", "nimmt", "Lange Rochade"

---

## 8. Données et persistance

### Fichiers de données
```
data/
  mes_lignes.json         — catalogue d'ouvertures personnel
  eco_hierarchy.json      — hiérarchie ECO (Wikipedia)
  books/                  — livres Polyglot (.bin)
logs/
  *.log                   — logs de parties (JSON structuré)
  Serious/
  Casual/
  Pedagogical/
  Human/
  Transcription/
```

### Sauvegarde
```bash
python -m nicsoft.utils.backup_manager                        # backup automatique
python -m nicsoft.utils.backup_manager --pin --label "label" # backup pinné (jamais supprimé)
python -m nicsoft.utils.backup_manager --list
```

---

## 9. Tests

### Niveaux de test
| Niveau | Type | Durée |
|--------|------|-------|
| Smoke test | Manuel (checklist `TESTS.md`) | 5 min |
| Régression complète | Manuel (checklist `TESTS.md`) | 20 min |
| Tests unitaires état | `pytest nicsoft/tests/test_app_state.py` (25 tests) | automatisé |
| Tests E2E | `pytest nicsoft/tests/e2e/` (42 tests Playwright) | automatisé |

### Mode test aléatoire
```bash
NICLINK_TEST=random python -m nicsoft.web
```
Bouton 🎲 dans le menu → génère une configuration aléatoire → sauvegardée dans `logs/Test config/`.

---

## 10. Bugs connus et limites actuelles

| Bug | Priorité | Description |
|-----|----------|-------------|
| WAIT_FISH sans feedback UI | Haute | Quand le moteur a joué et que le joueur dérange une pièce, rien n'apparaît à l'écran |
| 2 bips au démarrage | Basse | Réduit de 4 à 2 bips, lié à une race condition USB |
| Race condition LEDs | Basse | Synchronisation LED parfois incorrecte, rare |
| WAIT_FISH lent intermittent | Surveillance | Occasionnellement >30s, cause probable hardware Chessnut Air |

---

## 11. Fichiers de suivi du projet

| Fichier | Contenu |
|---------|---------|
| `TACHES.md` | Bugs actifs et fonctionnalités à venir |
| `TESTS.md` | Checklist de régression |
| `TEST_RESULTATS.md` | Résultats des sessions de test avec dates |
| `HISTORIQUE_BUGS.md` | Bugs résolus avec causes racines |
| `CLAUDE.md` | Instructions pour Claude Code |
| `INSTALLATION_ALCHESS.md` | Guide d'installation sur nouveau PC |
| `CONTRIBUTING.md` | Guide de contribution |
