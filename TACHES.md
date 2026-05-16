# AlChess — Tâches et bugs

---

## ⚡ Prioritaire

- **Créer une branche `dev`** — travailler sur `dev` au quotidien, merger vers `master` uniquement quand stable. `master` reste toujours la version fonctionnelle sur GitHub.
  ```bash
  git checkout -b dev
  git push -u origin dev
  ```

---

## 🐛 Bugs actifs

### En veille (peu prioritaires)
- **2 bips au démarrage** — réduit de 4 à 2 (commit 216cd09). Même nature que la race condition LEDs. Plus gênant en pratique.
- **Race condition LEDs** — synchronisation des camps LED parfois incorrecte. Rare, cause probable hardware/USB. À surveiller si ça s'aggrave.
- **WAIT_FISH lent intermittent** — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente).

### À corriger


---

## ✅ Bugs résolus récemment

- **Menu — split button Pédagogique/Labo/Exercices** — bouton coupé en deux : moitié gauche ♟ (physique, grisée si board absent), moitié droite 🖥 Virtuel (toujours active). Checkbox "mode sans échiquier" supprimée. (commit 55a985c)
- **Menu — descriptions en tooltip** — bulles d'explication masquées par défaut, visibles au survol uniquement (évite le chevauchement). (commit e419851)
- **Corbeille renommée en Panier (FR)** — "corbeille" évoquait la poubelle. 3 clés fr.json mises à jour (`common.corbeille_vide`, `retrans.btn.corbeille`, `toast.corbeille`). EN inchangé ("basket" déjà correct). (commit df53509)
- **HH — Reprendre la partie ne réagit pas** — `_handle_pause()` attendait `"reprendre"` mais le bouton envoie `"resume_pause"`. Ajout du handler manquant. (commit a6c4a53)
- **HH — See best move grisé pendant pause** — Stockfish lancé au moment de la pause pour calculer le meilleur coup et activer le bouton. (commit b0ec04a)
- **HH — combobox game_type vide en test random** — Valeurs françaises obsolètes dans `_randomizeConfigHH()`, remplacées par les valeurs anglaises. (commit db17977)
- **Maia 1400/1600 introuvable** — `find_maia_weights()` cherchait dans une liste théorique ; réécrite pour scanner le disque. 6 poids téléchargés (1200–1800). (commits 26ca08f + 1c40209)
- **Combobox pause pédagogique non grisée** — `_refreshDynamicLabels()` grise `cfg-pause` selon l'état de la checkbox analyse. (commit 7a875e1)
- **Pédagogique — retour menu après rangement pièce** — Cause racine : poids Maia 1600 manquants (réglé ci-dessus). Amélioration du gestionnaire d'erreurs dans `_run_pedagogique()` : erreur hardware → `board_error`, erreur moteur → popup avec vrai message + retour immédiat au menu. (commit 5bb4ca7)
- **Labo — échiquier non centré** — Ajout `justify-content:center` + `height` explicite sur la colonne centre, suppression `width:100%` sur `labo-board-align`. (commit 20b4eb5)
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
  - ✅ Phase 7f : Finitions visuelles — historique retranscription en tableau Blancs/Noirs, 14 textes clairs sur fond bleu corrigés (retrans-status, ex-run-status/moves-count, labo-turn-info/last-move/pgn-san, cartes variantes, HH subtitle, etc.).
  - Phase 7 reste : corrections i18n résiduelles au fil des tests.

---
## 🧪 Tests automatisés

- **Niveau 1** — Checklist manuelle : `TESTS.md` (smoke 5 min / régression 20 min)
- **Niveau 2** — `nicsoft/tests/test_app_state.py` — 25 tests pytest (`python -m pytest nicsoft/tests/test_app_state.py -v`)
- **Niveau 3** — `nicsoft/tests/e2e/` — 42 tests Playwright headless (`python -m pytest nicsoft/tests/e2e/ -v`)
- **Mode test aléatoire** — `NICLINK_TEST=random python -m nicsoft.web` + bouton 🎲 save → `logs/Test config/`

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation `.so` depuis `src/`. Voir `INSTALLATION_ALCHESS.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, fonctionnalité de reprise. Ne traiter que sur l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git push` pour synchroniser GitHub.
- **GitHub** : https://github.com/AlainDelree/AlChess
- **Logs** : bouton 📋 en haut à droite du programme.
