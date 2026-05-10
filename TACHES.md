# AlChess — Tâches et bugs

---

## 🐛 Bugs actifs

### En veille (hardware/USB — peu prioritaires)
- **2 bips au démarrage** — réduit de 4 à 2 (commit 216cd09). Même nature que la race condition LEDs. Plus gênant en pratique.
- **Race condition LEDs** — synchronisation des camps LED parfois incorrecte. Rare, cause probable hardware/USB. À surveiller si ça s'aggrave.
- **WAIT_FISH lent intermittent** — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente).

### À corriger
- **`test_pgn.py` en erreur** — import `build_output_path` disparu. À corriger séparément.
- **Mode sans échiquier — choisissez un mode** - Message au dessus des menus.  Ca n'est pas clair pour moi.  Je propose Mode sans échiquier — choisissez un menu
---

## 💡 Fonctionnalités à venir

- **Changer les icônes du programme** — Remplacer les pions (logo) par une tour pour cohérence avec la favicon.
- **Corbeille dans Outils Exercices** — Pour "Importer mes lignes" et "Convertir SAN en UCI".
- **Labo — mode virtuel** — ✅ Terminé (commits d4b1779→43bc11f). Undo, auto, PGN, promotions validés.

---

## 🧪 Tests automatisés

- **Niveau 1** — Checklist manuelle : `TESTS.md` (smoke 5 min / régression 20 min)
- **Niveau 2** — `nicsoft/tests/test_app_state.py` — 25 tests pytest (`python -m pytest nicsoft/tests/test_app_state.py -v`)
- **Niveau 3** — `nicsoft/tests/e2e/` — 35 tests Playwright headless (`python -m pytest nicsoft/tests/e2e/ -v`)
- **Mode test aléatoire** — `NICLINK_TEST=random python -m nicsoft.web` + bouton 🎲 save → `logs/Test config/`

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : quirk usbhid (`/etc/modprobe.d/chessnut.conf`) + recompilation `.so` depuis `src/`. Voir `INSTALLATION_ALCHESS.md` sections 4b et 4c.
- **`retranscription_en_cours`** au démarrage : normal, fonctionnalité de reprise. Ne traiter que sur l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git push` pour synchroniser GitHub.
- **GitHub** : https://github.com/AlainDelree/AlChess
- **Logs** : bouton 📋 en haut à droite du programme.
