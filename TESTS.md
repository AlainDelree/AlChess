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

## 🔬 Tests à automatiser (futur)

Ces séquences sont candidates pour des tests d'état serveur (`pytest`) :

- `_app_state` après `back_menu` depuis chaque mode → doit valoir `"menu"`
- `_app_state` après `start` pédagogique → doit valoir `"connecting"` puis `"playing"`
- `action_queue` vide après retour menu → pas d'actions en attente

---

## 📋 Comment utiliser ce fichier

**Smoke test** : cocher après chaque commit avant de continuer.  
**Régression complète** : cocher avant chaque backup pinné "stable" ou distribution.  
**Nouveau bug trouvé** : ajouter dans `HISTORIQUE_BUGS.md` + ajouter le test correspondant ici.
