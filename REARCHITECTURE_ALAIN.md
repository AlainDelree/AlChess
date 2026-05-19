# Plan de réarchitecture AlChess — Version Alain

---

## Pourquoi réarchitecturer ?

Actuellement AlChess est conçu pour Linux uniquement. Pour qu'il tourne aussi sur Windows et Android, il faut séparer clairement ce qui est "universel" de ce qui est "spécifique Linux".

La bonne nouvelle : la logique de jeu (règles, moteurs, PGN) n'a rien de spécifique Linux. Seul le bas niveau USB/Bluetooth l'est.

---

## Ce qui change — vue d'ensemble

```
AVANT (tout mélangé) :
┌─────────────────────────────────────┐
│  alchess.py + server.py + driver.py │
│  Logique jeu + USB + Web + OS       │
│  → Linux uniquement                 │
└─────────────────────────────────────┘

APRÈS (séparé proprement) :
┌─────────────────────────────────────┐
│         CORE (Python pur)           │
│  Logique jeu, moteurs, PGN          │
│  → tourne sur Linux ET Windows      │
└──────────────┬──────────────────────┘
               │ API WebSocket
       ┌───────┴──────────┐
       ▼                  ▼
  Web (HTML/JS)      Flutter (futur)
  Linux + Windows    Android/iOS
       │
  ┌────┴────┐
  ▼         ▼
Driver    Driver
USB/Linux USB/Win
(hidapi)  (hidapi)
```

---

## Prérequis — Avant de commencer

### Créer une VM Windows

Avoir une VM Windows prête avant de démarrer l'étape 1 évite une interruption en cours de route.

1. Télécharger une image VM officielle Microsoft (gratuite, pour développeurs) :
   **https://developer.microsoft.com/windows/downloads/virtual-machines/**
2. L'installer dans VirtualBox (gratuit) : **https://www.virtualbox.org/**
3. Vérifier que la VM démarre et qu'on peut y installer Python

> ℹ️ Pas besoin de licence Windows — l'image gratuite fonctionne avec un watermark
> "Activer Windows" mais c'est sans importance pour tester AlChess.

---

## Les 4 étapes dans l'ordre

### Étape 1 — Remplacer `_niclink.so` par `hidapi` Python
**Ce que c'est :** le fichier `_niclink.so` est un composant compilé en Rust qui communique avec l'échiquier via USB. Il ne fonctionne que sur Linux.

**Ce qu'on fait :** le remplacer par une bibliothèque Python appelée `hidapi` qui fait la même chose mais fonctionne sur Linux ET Windows ET Mac, sans compilation.

**Pour toi :** après cette étape, AlChess fonctionne exactement comme avant sur Linux, mais le composant problématique est supprimé. L'installation sur un nouveau PC devient aussi plus simple (plus besoin de compiler).

**Risque :** il faudra tester soigneusement que la communication avec l'échiquier est identique. C'est l'étape la plus incertaine.

---

### Étape 2 — Séparer la logique de jeu du serveur web
**Ce que c'est :** actuellement `alchess.py` mélange la logique de jeu (règles, tours, moteurs) et le serveur web (Flask). C'est difficile à porter sur d'autres plateformes.

**Ce qu'on fait :** extraire la logique pure dans un module `core/` indépendant, qui ne sait rien de Flask ni de web. Le serveur Flask devient juste une "interface" qui utilise ce core.

**Pour toi :** rien ne change visuellement. Mais le code devient beaucoup plus propre et portable.

---

### Étape 3 — Portage Windows
**Ce que c'est :** une fois les étapes 1 et 2 faites, Windows devient faisable.

**Ce qu'on fait :**
- Adapter les chemins (plus de `/home/alain/` en dur)
- Supprimer les appels Linux-only (ModemManager, udev)
- Tester sur Windows avec un Chessnut Air

**Pour toi :** AlChess tourne sur Windows. Le plus grand public potentiel.

---

### Étape 4 — App Android (futur)
**Ce que c'est :** une application mobile autonome qui se connecte à l'échiquier via Bluetooth.

**Ce qu'on fait :** développer une app Flutter séparée qui utilise le même "core" Python (ou une version équivalente) et se connecte au Chessnut Air via Bluetooth.

**Pour toi :** projet séparé, à envisager quand Linux et Windows sont stables.

---

## Ordre recommandé

| Étape | Durée estimée | Risque | Gain |
|-------|--------------|--------|------|
| 1. hidapi | 1-2 sessions | Moyen (tester USB) | Installation simplifiée + multiplateforme |
| 2. Core séparé | 2-3 sessions | Faible (refactoring) | Code propre + Windows facilité |
| 3. Windows | 2-3 sessions | Faible après étapes 1+2 | Grand public |
| 4. Android | Projet séparé | Nouveau projet | Mobile |

---

## Ce qui NE change PAS

- L'interface web (HTML/JS) — identique
- Les moteurs (Stockfish, Maia, Rodent) — identiques
- La logique de jeu — identique
- Les fichiers PGN, exercices, base SQLite — identiques
- L'expérience utilisateur — identique

---

## Comment travailler

- Chaque étape se fait sur la branche `dev`
- On merge sur `master` uniquement quand l'étape est validée et testée
- Un backup pinné avant chaque étape
- Claude Code s'occupe du code, tu testes après chaque étape
