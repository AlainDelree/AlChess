# AlChess — Tâches et bugs

---

## 🐛 Bugs actifs

### En veille (hardware/USB — peu prioritaires)
- **2 bips au démarrage** — réduit de 4 à 2 (commit 216cd09). Même nature que la race condition LEDs. Plus gênant en pratique.
- **Race condition LEDs** — synchronisation des camps LED parfois incorrecte. Rare, cause probable hardware/USB. À surveiller si ça s'aggrave.
- **WAIT_FISH lent intermittent** — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente).

### À corriger

- **Chevauchement textes mode virtuel** — En mode virtuel coché, les descriptions des boutons "Retranscrire" et "Outils Exercices" se chevauchent dans le menu.
- **Checkbox analyse inversée** — L'état "disabled" est coché pour activer l'analyse et décoché pour la désactiver : la logique est inversée. Corriger le sens de la checkbox dans config pédagogique.
- **Combobox pause pédagogique non grisée** — Quand l'analyse est désactivée, la combobox "pause pédagogique" devrait se griser automatiquement (et se dégriser si on réactive l'analyse).
- **Maia 1400 introuvable** — `RuntimeError: Poids Maia 1400 introuvables dans ~/NicLink/engines/maia/`. Le modèle maia-1400.pb.gz est absent. Vérifier les poids disponibles et adapter la sélection de niveau Maia en conséquence.
- **Impossible de jouer les Noirs en virtuel (pédagogique)** — Quand la couleur est "random" et que le joueur obtient les Noirs, il n'arrive pas à jouer. À reproduire et investiguer.

---

## 💡 Fonctionnalités à venir

- **Labo — mode virtuel** — ✅ Terminé (commits d4b1779→43bc11f). Undo, auto, PGN, promotions validés.
- **Version de AlChess en anglais** — i18n en cours :
  - ✅ Phase 1 : infrastructure (i18n.js, JSON, sélecteur FR/EN)
  - ✅ Phase 2 : HTML statique — 136 clés data-i18n sur tous les écrans (commit 6e52812)
  - ✅ Phase 3 : JS dynamique — t() dans app.js (commit 69f1bb8)
  - ✅ Phase 4 : Backend Python — message_key/title_key dans tous les modes
  - ✅ Phase 5 : JS dynamique complet — ELO_LABELS, retranscription, labo, flip, delta_cp
  - ✅ Phase 6 : Corrections i18n menu + pédagogique (CORRECTION_TRADUCTION.md). Reste à parcourir : labo, exercices, retranscription, outils.
  - ✅ Phase 6b : Finitions — panel-playing-title (conflit data-i18n/JS), label "Pause :", _refreshDynamicLabels au chargement config.

---
## 🧪 Tests automatisés

- **Niveau 1** — Checklist manuelle : `TESTS.md` (smoke 5 min / régression 20 min)
- **Niveau 2** — `nicsoft/tests/test_app_state.py` — 25 tests pytest (`python -m pytest nicsoft/tests/test_app_state.py -v`)
- **Niveau 3** — `nicsoft/tests/e2e/` — 35 tests Playwright headless (`python -m pytest nicsoft/tests/e2e/ -v`)
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
