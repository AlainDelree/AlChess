# AlChess — Tâches et bugs

---

## ⚡ Prioritaire

- **Committer le travail de la session 2026-07-03** — plusieurs fichiers modifiés non commités : `install.sh` (venv+chmod), `start_alchess.sh` (nouveau), `make_release.sh` (nouveau), `backup_manager.py` (exclude dist), `nicsoft/modes/pedagogique/pedagogique.py` (déjà commité `09b6c6e`), et les binaires `engines/maia/lc0.exe` + DLL. Décider commit vs gitignore pour les binaires (~22 Mo). Relire, committer par lots propres, push manuel.
- **vc_redist auto-install dans `install_alchess.ps1`** `[Windows]` — En cours via bridge (issue armée `mode_write`). Ajoute `Install-VCRedist` (modèle `Install-Stockfish`) : skip si `MSVCP140.dll` présent, test connexion internet avant download, install silencieux `/install /quiet /norestart`, messages **en anglais**, non bloquant, propose « Continue without Maia support? (Y/N) » en cas d'échec. À re-tester en VM SANS le runtime.
- **Visibilité du projet** (objectif initial) — une fois la base propre : (1) créer la **première Release publique** avec les ZIP (bouton Download), (2) déployer le **README amélioré** (déjà rédigé, orienté téléchargement + captures + tableau moteurs corrigé), (3) ajouter les **topics** GitHub (`chess`, `chessnut-air`, `stockfish`, `maia`, `lc0`, `chess-training`, `electronic-chessboard`, `python`, `flask`…).

---

## 🐛 Bugs actifs

### En veille (peu prioritaires)
- **Race condition LEDs** `[Linux]` — synchronisation des camps LED parfois incorrecte. Rare, cause probable hardware/USB. À surveiller si ça s'aggrave.
- **WAIT_FISH lent intermittent** `[Les deux]` — Occasionnellement le plateau met très longtemps (>30s) à reconnaître une position après un coup Stockfish. Cause probable : hardware Chessnut Air (stabilisation lente).

### À corriger

- **HH — écran de rangement ignoré si échiquier déconnecté silencieusement** `[Windows]` — Au lancement d'une partie HH avec l'échiquier physique, l'écran de vérification de position initiale ne s'est pas affiché malgré des pièces mal placées, et la partie a démarré directement. Cause probable : l'échiquier s'était déconnecté sans que le programme le détecte (pas d'événement de déconnexion reçu). La reconnexion du programme résout le problème. À investiguer : vérifier si `driver.py` détecte bien la perte de connexion USB et la signale à `alchess.py` pour bloquer le démarrage.

---

## ✅ Bugs résolus récemment

### Packaging, release & bridge (session 2026-07-03)

- **Système de packaging `make_release.sh`** `[Les deux]` — Script de build produisant des ZIP propres par OS (Linux/Windows) via **liste blanche** (copie uniquement le nécessaire ; exclut docs de dev, `.claude`, logs, `.git` imbriqués, caches). Corrections successives : exclusion des `.git` imbriqués (Rodent = dépôt git imbriqué de ~46 Mo) et `.pytest_cache` ; validateur rendu **déterministe** (here-string au lieu de tube `echo | grep`, qui provoquait un faux négatif via SIGPIPE + pipefail — garder `grep -E`, pas `-F`) ; `games/` livré **vide** (pas de données perso). Détecteur d'intrus intégré. Non commité (fichier de build).
- **`install.sh` — `python3-venv` manquant** `[Linux]` — Absent de la liste `PKGS`, ce qui faisait échouer la création du venv sur machine neuve (« ensurepip is not available »). Ajouté. Ajout aussi d'une étape `chmod +x` sur les moteurs après extraction ZIP (le bit exécutable peut être perdu). (à committer)
- **`start_alchess.sh`** `[Linux]` — Nouveau lanceur Linux, symétrique de `start_alchess.ps1`. (à committer)
- **Bug mode Pédagogique — `ImportError: load_config`** `[Les deux]` — Reliquat de refactoring : `load_config` n'avait pas été reportée dans `pedagogique.py` lors de l'extraction depuis l'ancien module monolithique, alors que `game_manager.py:163` l'importe → le thread pédagogique plantait au démarrage (retour menu, Stockfish comme Maia). Fix : rétablissement de `load_config` + `CONFIG_FILE`/`DEFAULT_CONFIG` (identique à `human.py`, lit `data/config.json` partagé). Validé en dev ET depuis ZIP extrait. Issue #7. (commit `09b6c6e`)
- **Données personnelles purgées du dépôt** — `games/` (parties de club avec noms réels de tiers + PGN de test) retiré du suivi ET **de tout l'historique** via `git filter-repo` (force-push dev + master). Fichiers conservés sur disque, `games/` ajouté au `.gitignore`. (commit `e955fec` + réécriture historique)
- **`backup_manager.py` — backups géants (420 Mo)** — `dist/` (les ZIP) n'était pas dans `EXCLUDES` alors que `build` y était → chaque backup avalait les ZIP. Ajout de `"dist"`. Backups de test reretombés à ~1 Mo. (à committer)

### Portage Windows — Maia validé (session 2026-07-03)

- **Installateur Windows testé de bout en bout en VM** `[Windows]` — VM Win11 recréée (VirtualBox, EFI+TPM 2.0, 6 Go RAM). `installer.bat` → Python 3.12, venv, dépendances, Stockfish OK. Appli lancée, **Stockfish + Maia fonctionnels**, partie jouée. Gel de VM récurrent tracé à la charge CPU (2 cœurs + Edge) — mitigé en fermant le navigateur pendant les commandes.
- **`lc0.exe` (Maia) manquant sous Windows** `[Windows]` — Résolu : téléchargé lc0 v0.31.2 windows-cpu-openblas, placé `lc0.exe` + `libopenblas.dll` + 2× `mimalloc*.dll` dans `engines/maia/`. (à committer / à décider : commit du binaire vs gitignore)
- **lc0.exe crash `0xC0000135` (MSVCP140.dll)** `[Windows]` — lc0 mourait au démarrage faute du runtime Visual C++. Résolu manuellement en VM via `vc_redist.x64.exe`. → automatisation en cours (voir Fonctionnalités à venir).

### Portage Windows — installateur (session 2026-05-24)

- **MissingEndCurlyBrace dans `install_alchess.ps1`** `[Windows]` — L'em-dash `—` (UTF-8 : `E2 80 94`) contient le byte `0x94` qui en CP1252 (encodage Windows par défaut sans BOM) correspond au guillemet typographique droit `"` (U+201D), que PowerShell 5.1 traite comme délimiteur de chaîne. Sans BOM, PS 5.1 lit le fichier en CP1252 → fermeture prématurée des strings aux lignes 21/118/177/205 → tous les `}` suivants avalés → `MissingEndCurlyBrace` sur toutes les fonctions. Fix : remplacement de tous les `—` par ` -` dans les strings et de tous les `─` (box drawing, même problème sur le 2e byte) par `--` dans les commentaires. Fichier 100% ASCII-safe. Validé sur Windows 11 / PS 5.1 via bridge inter-agents (issue #4). (commit `bfbcec9`)

### Nettoyage technique (session 2026-05-22)

- **Suppression fichiers obsolètes** — `nicsoft.apresinstallJess/`, anciens tests hardware, `nl_bluetooth/`, `debug_*.txt`, `test_windows.py`, `build/`, `src/`, `src_niclink/`. (commit `9f5a6a1`)
- **Fix `beep()` double définition dans `driver.py`** — Deux méthodes `beep()` coexistaient : l'ancienne bloquante (avec `_usb_lock`) et la nouvelle fire-and-forget (via `_led_queue`). Suppression de l'ancienne + `_usb_lock` devenu inutile. (commit `9fe929b`)
- **`print()` → `logger.*()` dans `server.py` et `game_manager.py`** — 13 conversions dans `server.py` (logger déjà présent) ; 22 conversions dans `game_manager.py` (+ ajout `logger = logging.getLogger("niclink.game_manager")`). Aucun `if DEBUG_MODE` touché. (commit `7ebad2d`)
- **Nettoyage complet `pedagogique.py`** — 44 `print()` CLI résiduels supprimés (Groupe A) ; 6 doublons de `tlog()` supprimés (Groupe B) ; 3 conversions → `logger.debug`/`error` ; `_print_historique()`, `_print_historique_inline()`, `ask_player_and_color()`, `ask_color()`, `main()`, `__main__.py` supprimés ; imports inutiles nettoyés (`argparse`, `signal`, `json`, `random`, `os`, `pathlib`, etc.). −328 lignes. (commit `2c34791`)

---

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

- **Chantier « l'UI reflète l'état réel du système »** `[Les deux]` — Regroupe plusieurs points de la même famille, à concevoir ensemble :
  - **Statut « Connected » trompeur** — le point vert + « Connected » reflète UNIQUEMENT la connexion Socket.IO navigateur↔serveur, PAS l'échiquier (diagnostic bridge confirmé : `index.html:28-29`, `app.js:584-603`, `server.py:138-145`). L'état échiquier est séparé (`_board_status`, `board_ok`/`board_error`, `alchess.py:172`). **Option A retenue** : renommer le libellé (ex. « Serveur connecté » / « Server connected ») dans les 3 i18n (`status.connecte`/`status.deconnecte`, ~ligne 371-372). Justif. : l'écran menu affiche déjà une phrase rouge quand l'échiquier est absent.
  - **Griser les moteurs non disponibles** — détecter au démarrage quels moteurs sont réellement lançables (lc0/rodent/stockfish présents et fonctionnels) et griser dans l'UI ceux qui manquent, + alerte claire. Nécessite détection back + événement Socket.IO + logique front + i18n.
- **Rodent IV pour Windows** `[Windows]` — Pas de binaire Windows dans le dépôt (dossier `exe/` ne contient que des `.bin`). Pas de release GitHub officielle propre (que du source, ou variantes NNUE non officielles / liens Dropbox-Mega). Deux voies : compiler depuis `engines/rodent-iv/sources/` sur la VM (VS/MinGW), ou récupérer un binaire Ablett manuellement. Le code attend exactement `engines/rodent-iv/rodentIV.exe`. Reporté (Stockfish + Maia suffisent pour une v1.0).
- **Nettoyer le dossier Rodent dans le packaging** — `engines/rodent-iv/` embarque `mac/` (binaire macOS), `sources/` (code C++), qui gonflent le ZIP et n'ont rien à faire dans un paquet utilisateur. À trier par OS dans `make_release.sh`.
- **Harmoniser la langue de `install_alchess.ps1`** `[Windows]` — Actuellement mixte (FR + bloc VC++ en EN). À terme, tout passer en anglais pour l'homogénéité (utilisateurs Windows).
- **Lancement Windows plus ergonomique** `[Windows]` — Créer un raccourci sur le bureau lançant `start_alchess.ps1` d'un double-clic (comme le raccourci que `install.sh` crée sous Linux), plutôt que de passer par le terminal.
- **Taille des ZIP (~210 Mo/OS)** — Surtout dû aux `books/` de Rodent. Élaguer si nécessaire (garder l'essentiel) — optimisation, non bloquant.

- **Installateur Windows** `install_alchess.ps1` `[Windows]` ✅ — Écrit (commit 3c21705). Testé et validé en VM (Stockfish + Maia, session 2026-07-03). Reste : merge master quand prêt.
  - ✅ Vérifie Windows 10+ (build < 10240 → arrêt propre)
  - ✅ Détecte Python 3.12+ via `py -3.12` ou `python`
  - ✅ Si absent : installe via winget (non-destructif) ou guide vers python.org
  - ✅ Crée le venv, installe les dépendances pip
  - ✅ Stockfish : propose téléchargement (O/N) si absent, skip si déjà présent
  - ✅ `start_alchess.ps1` généralisé (chemin auto-détecté, plus de hardcode)

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
    - ✅ HH : bouton grisé en mode virtuel — `board_ok` respecte `data-physical-only` (commit 3c21705)
    - ✅ Lancement : `start_alchess.ps1` généralisé (commit 3c21705)
    - [x] Cosmétique Windows (passe CSS dédiée) :
        - ✅ Taille échiquier variable : `clamp(350px, 100vh-200px, vw-cap)` + breakpoint `innerWidth` + listener `resize` (commits 2fc4be4, 4040492)
        - ✅ Icône bouton Abandonner : `🏳` (U+1F3F3, hors BMP) → `⚐` (U+2690, BMP, universel) (commit 4040492)
        - Numéros de lignes échiquier mal alignés (rendu police Windows) — en veille
    - ✅ `launcher.py` (GTK splash) : ignoré sur Windows — on lance directement via `start_alchess.ps1`
    - ✅ **`install_alchess.ps1` testé et validé sur VM Windows** (session 2026-05-24)

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
- **Bridge — mode écriture** : le watcher (`~/bridge-agent/watcher.py`) lance CCL en **lecture seule par défaut** (diagnostic uniquement). Le label GitHub **`mode_write`** (rouge) arme le mode écriture (`--dangerously-skip-permissions`), avec garde-fous inscrits dans le prompt : backup pinné obligatoire, **jamais de `git push`** (push manuel), pas de commande destructrice. Le mode est visible (log `MODE ÉCRITURE ARMÉ` + ACK sur l'issue). Modèles d'issues dans `TACHES-ISSUES.md`. Validé le 2026-07-03 (issue #10). Ne PAS lancer le watcher en root (`--dangerously-skip-permissions` refusé).
- **Runtime Visual C++ requis (Windows)** : `lc0.exe` (Maia) exige `MSVCP140.dll` (runtime VC++). Absent d'un Windows neuf → crash `0xC0000135` / exit code `3221225781`. Corrigé via `vc_redist.x64.exe` (https://aka.ms/vs/17/release/vc_redist.x64.exe). Automatisation dans l'installateur en cours.
- **VM Windows (VirtualBox)** : `AlChess-Win11`, EFI + TPM 2.0, 6 Go RAM, 2 CPU, compte **local** (contourner le compte MS à l'install : `Maj+F10` → `start ms-cxh:localonly`). Gel possible si CPU saturé (Edge + commandes en //) — fermer le navigateur pendant les opérations lourdes. Transfert de fichiers : dossier partagé (`VBoxManage sharedfolder add`, VM éteinte) ou glisser-déposer (capricieux).
