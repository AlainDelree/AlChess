# AlChess — Tâches et bugs

---

## ⚡ Prioritaire

_(rien pour l'instant)_

---

## 🐛 Bugs actifs

### En veille (peu prioritaires)
- **Race condition LEDs** `[Linux]` — synchronisation des camps LED parfois incorrecte. Rare, cause probable hardware/USB. À surveiller si ça s'aggrave.
- **WAIT_FISH lent intermittent** `[Les deux]` — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente).

### À corriger

- **HH — écran de rangement ignoré si échiquier déconnecté silencieusement** `[Windows]` — Au lancement d'une partie HH avec l'échiquier physique, l'écran de vérification de position initiale ne s'est pas affiché malgré des pièces mal placées, et la partie a démarré directement. Cause probable : l'échiquier s'était déconnecté sans que le programme le détecte (pas d'événement de déconnexion reçu). La reconnexion du programme résout le problème. À investiguer : vérifier si `driver.py` détecte bien la perte de connexion USB et la signale à `alchess.py` pour bloquer le démarrage.

---

## ✅ Bugs résolus récemment

- **Pédagogique — pas de feedback UI pendant WAIT_FISH si plateau dérangé** `[Les deux]` — `_display_position_error` n'émettait rien vers le navigateur. Fix : `send_event("board_warning", ...)` + handler JS `board_warning` qui passe le cadre "tour en cours" en orange avec le coup à exécuter. Distingue "pièce pas encore bougée" (source occupée → texte noir normal) de "pièce bougée au mauvais endroit" (source vide → orange). (commits 7dfc05e, 4a81b1f, c24a3ab)

- **Régression font-family — texte espacé sur Linux** `[Linux]` — Ajout des polices emoji (`Noto Color Emoji`, `Segoe UI Emoji`, `Apple Color Emoji`) dans `body font-family` pour corriger l'icône `🏳` causait l'utilisation de `Noto Color Emoji` sur Ubuntu, entraînant des métriques incorrectes sur tout le texte (lettres très espacées). Fix : retrait des polices emoji du body (le remplacement `🏳` → `⚐` U+2690 les rend inutiles). (commit 4ca8bee)
- **Échiquier Windows VM — taille/forme** `[Windows]` — Viewport VM ~450px rendait l'échiquier trop petit (250px) ; Exercices et Labo en rectangle ; Transcrire trop grand. Fix : `clamp(350px, vh-offset, vw-cap)` + refactoring CSS custom properties `--bd-size`/`--bd-min`/`--bd-max`/`--bd-vw-offset`. (commits 2fc4be4, c361f3a, 6555f64)

- **i18n DE — overlay de démarrage toujours en FR** — script inline synchrone dans l'overlay lit le cookie avant le fetch async ; fallback `'en'` ; `DEFAULT_LOCALE = 'en'` dans i18n.js. (commit 97253f0, c33e5c2, caa1528)
- **i18n DE — labo : message "⚠ Schach" ne se vidait jamais** — comparaison hardcodée `startsWith("⚠ Échec")` remplacée par `_lastLaboLastMove?.data?.type === "check"`. (commit a0c6767)
- **i18n DE — outils Exercices : messages FR dans add/edit/wiki** — `edit_ouverture.py`, `add_ouverture.py`, `download_eco_wiki.py` : ajout `message_key`/`error_key`/`vars` ; erreurs de validation passées de strings à objets `{key, vars}` ; handlers JS utilisent `_i18nMsg()`. (commits 2460ac7, a0c6767, a841dd5)
- **i18n DE — position illégale HH toujours en FR** — `analyser_position_illegale()` retourne maintenant un dict `{message, message_key, vars?}` ; 6 clés `game.illegal.*` + 6 clés `piece.*` (FR/EN/DE) ; `_i18nMsg()` résout `piece_key`. (commit f8b0c5c)

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

- **Installateur Windows** `install_alchess.ps1` `[Windows]` — Requiert Windows 10+ minimum (Python 3.12 et winget non disponibles sur Windows 8/8.1). Script PowerShell d'installation automatique :
  - Vérifie si Python 3.12+ est disponible via `py -3.12` (Windows Launcher)
  - Si absent : installe Python 3.12 via `winget install Python.Python.3.12` (non-destructif, cohabite avec les autres versions)
  - Si version incompatible déjà présente : installe 3.12 en parallèle sans toucher à l'existant
  - Si `winget` indisponible (Windows ancien) : message clair + lien python.org + arrêt propre
  - Crée le venv avec `py -3.12 -m venv venv` (garantit la bonne version)
  - Installe les dépendances pip
  - Télécharge Stockfish si absent

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
  - ✅ Phase 7 (DE) : traduction allemande complète — overlay démarrage, labo, outils exercices (add/edit/wiki/validation), position illégale HH, sanToLang(), exercices, retranscription, split-buttons, game_over.
  - Phase 7 reste : corrections i18n résiduelles au fil des tests DE (eco_import.py erreurs, edge cases).

- **Réarchitecture multiplateforme** (voir `REARCHITECTURE_CLAUDE_CODE.md`) — ✅ **Terminée et mergée sur master** (commit 9618efc) :
  - ✅ Étape 1 : `hid_backend.py` — remplace `_niclink.so` par hidapi Python pur
  - ✅ Étape 2 : `nicsoft/config.py` — centralise les chemins (`ALCHESS_DIR`)
  - ✅ Étape 3 : `nicsoft/platform_utils.py` — isole ModemManager et appels OS Linux-only
  - ✅ Étape 4 : `nicsoft/core/` — sépare Core et Transport ; `alchess.py` : 1337 → 233 lignes
  - **Portage Windows — Phase 1 (hidapi) : terminée ✅** (commits 4c78247, 03f30a9, mergé master) :
    - `test_hidapi_windows.py` : 16/16 sur Windows 11 VM — connexion ✓, FEN ✓, LEDs ✓, beep ✓, latence 0.0ms ✓
    - Interface Col02 (usage_page=0xFF00) utilisée sur Windows ; Col01 (0x0001) muet
    - Deux report IDs alternatifs : 0x01 (position) + 0x2a (statut) — `hid_backend.py` mis à jour (filtre supprimé, bounds check, try/except)
  - **Portage Windows — Phase 2 (application complète) : en cours** :
    - ✅ `find_stockfish()` : glob `stockfish*.exe` sur Windows (fonctionne avec nom long)
    - ✅ `find_rodent()` : nouvelle fonction — `rodentIV.exe` sur Windows, `rodentIV` sinon
    - ✅ `find_lc0()` : cherche aussi `engines/maia/lc0.exe`
    - ✅ `server.py` : `os.kill(SIGINT)` → `os._exit(0)` (cross-platform)
    - ✅ `config.py` : `APP_DIR` détecté depuis `__file__` (plus de dépendance à `~/NicLink`)
    - ✅ `game_manager.py` : `_validated_engine_path()` — ignore path config.json si inexistant sur l'OS courant
    - ✅ Mode pédagogique virtuel fonctionnel sur Windows (screenshot validé)
    - ✅ Labo, Retranscription, Exercices : fonctionnels sur Windows
    - ✅ HH : skip (nécessite échiquier physique, bouton à masquer en mode virtuel — TODO existant)
    - ✅ Lancement : `$env:PYTHONPYCACHEPREFIX="C:\Users\Al\AppData\Local\Temp\alchess_pyc"` puis `python -m nicsoft.web`
    - [x] Cosmétique Windows (passe CSS dédiée) :
        - ✅ Taille échiquier variable : `clamp(350px, 100vh-200px, vw-cap)` + breakpoint `innerWidth` + listener `resize` (commits 2fc4be4, 4040492)
        - ✅ Icône bouton Abandonner : `🏳` (U+1F3F3, hors BMP) → `⚐` (U+2690, BMP, universel) (commit 4040492)
        - Numéros de lignes échiquier mal alignés (rendu police Windows) — en veille
    - [ ] `launcher.py` (GTK splash) : à adapter ou ignorer pour Windows

---
## 🧪 Tests automatisés

- **Niveau 1** — Checklist manuelle : `TESTS.md` (smoke 5 min / régression 20 min)
- **Niveau 2** — `nicsoft/tests/test_app_state.py` — 25 tests pytest (`python -m pytest nicsoft/tests/test_app_state.py -v`)
- **Niveau 3** — `nicsoft/tests/e2e/` — 42 tests Playwright headless (`python -m pytest nicsoft/tests/e2e/ -v`)
- **Mode test aléatoire** — `NICLINK_TEST=random python -m nicsoft.web` + bouton 🎲 save → `logs/Test config/`

---

## 📝 Notes techniques

- **USB Chessnut sur nouveau PC** : quirk usbhid (`/etc/modprobe.d/chessnut.conf`). Le `.so` n'est plus nécessaire — hidapi Python pur depuis l'étape 1 réarchitecture. Voir `INSTALLATION_ALCHESS.md` section 4b.
- **`retranscription_en_cours`** au démarrage : normal, fonctionnalité de reprise. Ne traiter que sur l'écran Retranscription.
- **Git** : committer après chaque étape stable. `git push` pour synchroniser GitHub.
- **GitHub** : https://github.com/AlainDelree/AlChess
- **Logs** : bouton 📋 en haut à droite du programme.
