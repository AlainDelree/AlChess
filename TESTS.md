# AlChess — Checklist de régression

---

## 🚀 Smoke test (5 min — après chaque modification)

Les vérifications minimales avant de continuer à travailler.

```
□ Programme démarre → menu visible, pas de spinner bloqué
□ Échiquier détecté → boutons dégrisés (ou bouton Reconnecter visible)
□ Mode Pédagogique → démarrer → 1 coup joué → pas d'erreur
□ Retour menu → menu visible et propre
```

---

## 🔁 Régression complète (20 min — avant chaque distribution ou grosse modification)

### Démarrage
```
□ Démarrer avec échiquier branché → spinner → menu
□ Démarrer sans échiquier → message "non détecté" → bouton Reconnecter visible
□ Brancher échiquier après → cliquer Reconnecter → boutons dégrisés
□ Redémarrer programme après une partie non terminée → état propre
```

### Mode Pédagogique
```
□ Configurer → démarrer → spinner connecting → écran de jeu (BUG-003)
□ Démarrer avec pièces mal placées → écran position initiale avec cases rouges (BUG-001)
□ Jouer 3 coups → signal de tour en < 2s (BUG-007)
□ Cliquer Abandonner → modal de confirmation (pas d'URL dans le titre) (BUG-004)
□ Fin de partie → écran game_over → tous les boutons répondent (BUG-002)
□ Retour menu depuis game_over → menu propre
□ Retour menu EN COURS de partie → menu propre (pas de partie en arrière-plan)
```

### Mode Humain vs Humain
```
□ Cliquer HH → panneau config s'affiche (BUG-009)
□ Remplir noms → Démarrer → partie commence
□ Jouer 2 coups → retour menu → menu propre
□ HH en mode virtuel → bouton HH absent ou désactivé (TODO)
```

### Analyse de partie
```
□ Menu → Analyse → écran vierge (pas de résidu de partie précédente) (BUG-005)
□ Importer PGN → navigation coup par coup → boutons prev/next fonctionnent
□ Lancer analyse Stockfish → symboles qualité s'affichent
□ Sauvegarder PGN → toast de confirmation s'affiche
□ Retour menu → menu propre
□ Partie pédagogique → retour menu → cliquer Analyse → écran vierge (BUG-005)
```

### Exercices
```
□ Menu → Exercices → liste s'affiche
□ Chigorine ligne 1 → compléter la ligne → retour menu
□ Retourner dans Exercices → re-cliquer Chigorine ligne 1 → réaction (BUG récent)
□ Exercice drill → compléter → retour → même drill → réaction
```

### Retranscription
```
□ Menu → Retranscrire → formulaire s'affiche
□ Saisir coups → sauvegarder
□ Redémarrer programme → proposer de reprendre → accepter → coups retrouvés
□ Redémarrer programme → refuser reprise → formulaire vierge
```

### Labo
```
□ Menu → Laboratoire → échiquier labo s'affiche
□ Demander meilleur coup → Stockfish répond
□ Copier position → "Reproduisez cette position" s'affiche SEUL (BUG-008)
□ Synchroniser → "Synchronisé" s'affiche SEUL (BUG-008)
```

### Transitions critiques (patterns de bugs récurrents)
```
□ Pédagogique → retour menu → HH → démarrer (pas de résidu d'état)
□ HH → retour menu → Pédagogique → démarrer (pas de résidu d'état)
□ Exercices → retour menu → Analyse → écran vierge
□ Labo → retour menu → Pédagogique → démarrer
```

---


---

## 🔌 Test driver échiquier — après remplacement hidapi

À effectuer manuellement avec le Chessnut Air branché, après l'étape 1 de réarchitecture.

```
□ Détection USB → lsusb montre 2d80:8003
□ get_fen() réactif — position reconnue en < 500ms après déplacement d'une pièce
□ LEDs s'allument aux bonnes cases après coup moteur
□ turn_off_all_leds() éteint tout
□ Beep audible au début du tour
□ Signal de tour (LEDs + beep) en < 2s
□ Déconnecter/rebrancher échiquier → reconnexion automatique
□ 10 coups consécutifs sans décrochage USB
```

> ℹ️ Ces tests ne peuvent pas être automatisés — ils nécessitent un humain avec l'échiquier physique.
> Durée estimée : 5 minutes.

## 🧪 Suite automatisée (pytest)

Les tests vivent dans `nicsoft/tests/` (pas de dossier `tests/` à la racine). Deux marqueurs sont déclarés dans `pytest.ini` :

- `hardware` : nécessite un échiquier Chessnut Air physiquement connecté (jamais exécuté en CI).
- `slow` : test lent (de l'ordre de plusieurs secondes), typiquement les tests e2e qui démarrent un vrai serveur AlChess + un navigateur Playwright. Tout `nicsoft/tests/e2e/` est marqué `slow` : ces fichiers paient le coût d'un lancement serveur + navigateur (~5-6 s) alors que le reste de la suite s'exécute en moins d'une seconde.

```bash
# Suite rapide (itération courante) — ignore slow et hardware
python -m pytest nicsoft/tests -m "not slow and not hardware"

# Seulement les tests lents (e2e)
python -m pytest nicsoft/tests -m slow

# Suite complète hors tests hardware (ce qui tourne en CI)
python -m pytest nicsoft/tests -m "not hardware"
```

Durées mesurées (04/11/2026, poste de dev) :
- Sans `slow` (33 tests + skips) : ~0,5 s.
- `slow` seul (42 tests e2e) : ~20,5 s.
- Suite complète hors `hardware` : ~20,5 s (le temps est dominé par les tests e2e).

### Tests e2e (`nicsoft/tests/e2e/`)

Ces tests démarrent un vrai serveur AlChess en sous-processus et le pilotent via Playwright (navigateur headless, aucun onglet visible). Le dossier de lancement du serveur (`cwd`, donc le code importé) est déduit de l'emplacement de `conftest.py` : c'est la racine du dépôt ou du worktree où tourne pytest, pas un chemin figé — les tests valident donc le code sur lequel ils sont lancés. Le Python reste celui du venv utilisateur (`~/NicLink/venv/bin/python`), seul le code vient du dossier testé.

Deux variables d'environnement sont positionnées par `conftest.py` dans l'environnement du serveur lancé (sans effet sur une exécution normale de l'application, où elles sont absentes) :
- `ALCHESS_SKIP_BOARD=1` — désactive la détection et la connexion à l'échiquier Chessnut Air réel au démarrage (`_check_board_at_startup`, `_board_menu_watcher`) et empêche aussi l'ouverture automatique du navigateur (`_maybe_open_browser`). Sans elle, le serveur de test sollicite l'échiquier USB physique s'il est branché (bips) et ouvre un onglet sur l'écran de l'utilisateur. Les tests restent en mode virtuel, qui ne dépend pas de cette détection.
- `ALCHESS_NO_BROWSER=1` — empêche uniquement l'ouverture automatique du navigateur (`_maybe_open_browser`), sans désactiver la détection de l'échiquier. Utile pour une vérification manuelle (ex. un agent qui démarre le serveur pour contrôler une page) qui veut garder l'échiquier réel actif mais ne doit jamais ouvrir d'onglet sur le poste de l'utilisateur. `ALCHESS_SKIP_BOARD=1` seul produit déjà cet effet ; cette variable sert quand on veut l'un sans l'autre.
- `ALCHESS_DIR=~/NicLink` — `data/` n'est pas versionné (`.gitignore`) : un worktree de test n'a pas les fichiers de référence réels (ECO `eco_a.tsv`…`eco_e.tsv`, `eco_hierarchy.json`, livres d'ouvertures dans `books/`, `mes_lignes.json`, `players.json`, `config.json`). Les tests de recherche ECO (`test_outils_exercices_e2e.py`) en ont besoin pour avoir des résultats non vides ; cette variable pointe donc le serveur de test vers le vrai dossier de données de l'utilisateur plutôt que vers un dossier temporaire isolé ou vide. Le code testé reste celui du dépôt/worktree ; seules les données sont partagées avec l'installation principale. L'isolation complète dans un dossier temporaire (sans dépendre de `~/NicLink`) a été tentée mais abandonnée : elle fait échouer les 3 tests de recherche ECO, faute de ces fichiers de référence. La suite e2e actuelle ne fait que lire ces données (aucun test n'exerce une sauvegarde/export) ; si un futur test e2e sauvegarde quelque chose, il écrira dans le vrai dossier de données tant que cette isolation reste incomplète.

## 🔬 Tests à automatiser (futur)

Ces séquences sont candidates pour des tests d'état serveur (`pytest`) :

- `_app_state` après `back_menu` depuis chaque mode → doit valoir `"menu"`
- `_app_state` après `start` pédagogique → doit valoir `"connecting"` puis `"playing"`
- `action_queue` vide après retour menu → pas d'actions en attente

---

## 📋 Comment utiliser ce fichier

**Smoke test** : cocher après chaque commit avant de continuer.  
**Régression complète** : cocher avant chaque version "stable" ou distribution.  
**Nouveau bug trouvé** : ajouter dans `HISTORIQUE_BUGS.md` + ajouter le test correspondant ici.
