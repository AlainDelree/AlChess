# AlChess — Tâches et bugs

---

## 🐛 Bugs actifs

### En veille (peu prioritaires)
- **2 bips au démarrage** — réduit de 4 à 2 (commit 216cd09). Même nature que la race condition LEDs. Plus gênant en pratique.
- **Race condition LEDs** — synchronisation des camps LED parfois incorrecte. Rare, cause probable hardware/USB. À surveiller si ça s'aggrave.
- **WAIT_FISH lent intermittent** — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente).

### À corriger

- **Combobox pause pédagogique non grisée** — Quand l'analyse est désactivée, la combobox "pause pédagogique" devrait se griser automatiquement (et se dégriser si on réactive l'analyse).
- **Maia 1400 introuvable** — `RuntimeError: Poids Maia 1400 introuvables dans ~/NicLink/engines/maia/`. Le modèle maia-1400.pb.gz est absent. Vérifier les poids disponibles et adapter la sélection de niveau Maia en conséquence.
- ~~**Historique de Retranscrire**~~ ✅ Résolu (commit 074b8de) — tableau Blancs/Noirs avec move-chip, contraste correct.
-  **HH continuer la partie**  Dans HH, je fais deux coups, en suite clic pause, clic sur "Reprendre la partie" ne reagit pas.
- **Dans pédagogique retour menu apres rangement piece** Apres l'ecran config, l'ecran de correction de position s'affiche, je corrige et la retour menu.  Reproduction bug, 1er tentative pas de bug, 2eme bug.  Parametres: 
[Pédagogique]  Joueur: Arjun  Couleur: black  Moteur: maia  ELO SF: 1500  ELO Maia: 1600  ELO Rodent: 1800  Rodent simple: non  Pause: toujours  Analyse: on  Bip: on  Coups légaux: off
- **Labo, centrer verticalement et horizontalement l'echiquier**
- **Changer le nom Corbeille**  J'aimerai changer le nom Corbeille car ca évoque la poubelle.  Voir en anglais ce qu'il convient de faire.
---

## 💡 Fonctionnalités à venir

- **Labo — mode virtuel** — ✅ Terminé (commits d4b1779→43bc11f). Undo, auto, PGN, promotions validés.
- **Version de AlChess en anglais** — i18n en cours :
  - ✅ Phase 1 : infrastructure (i18n.js, JSON, sélecteur FR/EN)
  - ✅ Phase 2 : HTML statique — 136 clés data-i18n sur tous les écrans (commit 6e52812)
  - ✅ Phase 3 : JS dynamique — t() dans app.js (commit 69f1bb8)
  - ✅ Phase 4 : Backend Python — message_key/title_key dans tous les modes
  - ✅ Phase 5 : JS dynamique complet — ELO_LABELS, retranscription, labo, flip, delta_cp
  - ✅ Phase 6 : Corrections i18n menu + pédagogique (CORRECTION_TRADUCTION.md).
  - ✅ Phase 6b : Finitions — panel-playing-title (conflit data-i18n/JS), label "Pause :", _refreshDynamicLabels au chargement config.
  - ✅ Phase 6c : btn-reconnect, cfg-pause options, bouton "Changer de couleur".
  - ✅ Phase 6d : Écran Analyse — title_key game_over, btn-analyser, corbeille vide, Séquence:, status-text, combobox PGN save (pgn.mode.*/pgn.type.*), Blancs/Noirs HISTORY, combobox séquence n_coups.
  - ✅ Phase 7a : Labo — journal, toggles camp/tour, labo-turn-info, labo-last-move, labo-pgn-info, spinner, auto on/off, synced.
  - ✅ Phase 7b : Retranscription — titre config, tour "Move 1 — White to play", couleur joueur au-dessus échiquier.
  - ✅ Phase 7c : Outils Exercices — sous-titres (data-i18n-html), placeholders textarea/input, labels formulaires (Nom, Camp, Coups UCI…), options Camp Blancs/Noirs dans les selects.
  - ✅ Phase 7d : Écran Analyse — titre "Analyse de partie" et invite "Importez un fichier PGN" (fix côté serveur : title_key/result_key + _analyseEmpty flag côté client).
  - ✅ Phase 7e : Corrections ciblées — labels joueurs Analyse (_localPlayerName), HH config boutons/combobox, dossiers PGN renommés en anglais (Serious/Casual/Pedagogical/Human/Transcription), HH vérification position, exercice sync error, outils exercices entêtes colonnes, bouton "Continuer avec Stockfish", badge/titre variantes exercices, labels Labo Noir/Blanc supprimés.
  - Phase 7 reste : corrections i18n résiduelles au fil des tests.

---
## 🧪 Tests automatisés

- **Niveau 1** — Checklist manuelle : `TESTS.md` (smoke 5 min / régression 20 min)
- **Niveau 2** — `nicsoft/tests/test_app_state.py` — 25 tests pytest (`python -m pytest nicsoft/tests/test_app_state.py -v`)
- **Niveau 3** — `nicsoft/tests/e2e/` — 42 tests Playwright headless (`python -m pytest nicsoft/tests/e2e/ -v`)
- **Mode test aléatoire** — `NICLINK_TEST=random python -m nicsoft.web` + bouton 🎲 save → `logs/Test config/`

### GitHub Actions — à améliorer
- **Matrix multi-versions** — tester automatiquement sur plusieurs configs à chaque push :
  - Python 3.10, 3.11, 3.12 en parallèle
  - Ubuntu 22.04 et 24.04
  - Modifier `.github/workflows/python-app.yml` : remplacer `python-version: "3.12"` par une `matrix` strategy

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation `.so` depuis `src/`. Voir `INSTALLATION_ALCHESS.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, fonctionnalité de reprise. Ne traiter que sur l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git push` pour synchroniser GitHub.
- **GitHub** : https://github.com/AlainDelree/AlChess
- **Logs** : bouton 📋 en haut à droite du programme.
