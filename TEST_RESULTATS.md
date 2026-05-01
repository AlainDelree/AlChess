# AlChess — Résultats des tests

Format : ✅ OK  ❌ Échec  ⏭ Non testé  🔄 Partiel

---

## 2026-05-02 — Tests manuels post-refactoring étape 1

**Type** : Régression partielle (échiquier physique disponible)  
**Version** : commit "refactoring : web/__main__.py → alchess.py"

### Démarrage
✅ Programme démarre → menu visible  
✅ Échiquier détecté après quirk usbhid + recompilation .so  

### Mode Pédagogique
✅ Démarrer → spinner → écran de jeu  
✅ Jouer 2 coups de part et d'autre  
✅ Signal de tour fonctionnel  

### Mode Humain vs Humain
✅ Panneau config s'affiche (bug BUG-009 corrigé ce soir)  
✅ Partie démarre correctement  

### Analyse de partie
✅ Accessible via game_over après partie nulle  
⏭ Import PGN externe non testé  

### Exercices
✅ Chigorine ligne 1 complétée sans problème  
❌ Retour menu → re-cliquer même ligne → aucune réaction (bug noté dans TACHES.md)  

### Retranscription
⏭ Non testé  

### Labo
⏭ Non testé  

### Transitions critiques
❌ Pédagogique → retour menu → HH → écran vide dans certaines conditions  
✅ Redémarrage programme → état propre  

**Notes** : Tests effectués avec échiquier physique Chessnut Air sur ThinkPad X1 Carbon Gen 7, kernel 6.8.0-55, quirk usbhid actif.
