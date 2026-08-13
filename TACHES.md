# AlChess — Tâches et bugs

---

## ⚡ Prioritaire

- **Release v1.3.1 à packager** `[Linux/Windows]` — regrouper les correctifs depuis v1.3.0 (dont issue #96) : `./make_release.sh 1.3.1` + tag + `gh release create`.
- **ACTION ALAIN — Valider installeur standalone** `[Windows]` — lancer `AlChess_Setup.exe` seul (sans ZIP), vérifier clone GitHub dans `%LOCALAPPDATA%\AlChess` et raccourci bureau fonctionnel.
- **Tester une partie réelle Rodent sur Windows** `[Windows]` — sur portable physique (jeu + changement d'Elo + redémarrage).
- **Tester vc_redist sur un Windows sans le runtime VC++** `[Windows]` — la VM actuelle a déjà le runtime, il faut un Windows propre.

---

## 🐛 Bugs actifs

### À corriger
- **HH — écran de rangement ignoré si échiquier déconnecté silencieusement** `[Windows]`

### En veille (peu prioritaires)
- **Race condition LEDs** `[Linux]`
- **WAIT_FISH lent intermittent** `[Les deux]`
- **`git submodule update --init` échoue sur clone frais** `[Les deux]`
- **Pédagogique — boucle infinie de double-bip si pièce mal jouée puis corrigée manuellement** `[Linux]`
- **Numéros de lignes échiquier mal alignés (rendu police Windows)** `[Windows]`

### Bugs résolus récemment
- **`_board_menu_watcher` — `get_fen()` ne détecte pas un débranchement sur Linux** `[Linux]` — issue #110, commit `bc87bc5`. Le fix #108 appelait `hid_backend.get_fen()` pour forcer une lecture USB, mais sur Linux `_dev.read()` ne lève pas d'`OSError` au débranchement — il retourne `[]` après le timeout, donc `_connected` ne passait jamais à `False`. Ajout de `hid_backend.check_physically_present()`, qui interroge directement `hid.enumerate()` pour confirmer la présence du périphérique dans le sous-système USB (sans dépendre d'une lecture FEN) ; remplace l'appel `get_fen()` + `is_connected()` dans le watcher.
- **Bouton Connecter clignotant (schéma SVG)** `[Linux]` — issue #109, commit `2e16190`. `_board_menu_watcher` ré-émettait `board_error` toutes les 3s tant que le plateau restait déconnecté, ce qui redéclenchait `_applyBoardBadge()` côté JS à chaque poll → clignotement du schéma/bouton. Ajout d'un flag local `_already_notified` : `board_error` n'est émis qu'une seule fois par déconnexion, remis à `False` à la reconnexion (`else` du `is_connected()`) et en sortie de l'état `menu`.
- **`_board_menu_watcher` ne détectait jamais la déconnexion au menu** `[Linux]` — issue #108, commit `694d877`. Le watcher n'appelait que `hid_backend.is_connected()`, qui lit le flag `_connected` — flag mis à `False` uniquement par un `OSError` levé dans `get_fen()`. Or personne n'appelait `get_fen()` au menu, donc le flag ne changeait jamais. Ajout de `hid_backend.get_fen()` (dans le `try/except` existant) juste avant le test, pour forcer une lecture USB réelle à chaque poll de 3s.
- **Schéma SVG connexion — collé au menu-grid au lieu d'être à gauche du titre** `[Linux]` — issue #107, commit `15d8188`. `.schema-connexion` sorti du wrapper flex (qui ne contient plus que `.menu-grid`) et placé directement dans `#screen-menu`, juste avant `.menu-title`. CSS : `#screen-menu` passe en `position:relative` ; `.schema-connexion` passe en `position:absolute; left:20px; top:0` (aligné avec le haut du titre AlChess), `margin-right:8px` supprimé.
- **Schéma SVG connexion — bandeau horizontal trop large, remplacé par colonne verticale étroite** `[Linux]` — issue #106, commit `9a36804`. `.schema-connexion` déplacé dans `#screen-menu` juste avant `.menu-grid`, enveloppé avec `.menu-grid` dans un div flex ; SVG repensé en viewBox verticale `0 0 50 200` (ordinateur ~36×24, câble ~80px, échiquier ~36×36) ; CSS réduite à `width:60px` ; bouton "Connecter" repositionné en `top:48%`/`width:44px`.
- **Icônes 🖥 résiduelles sur Analyse/Retranscrire + déconnexion plateau en session non détectée** `[Linux]` — issue #102, commit `fcb51e1`. `hid_backend.get_fen()` avalait les `OSError` de lecture USB sans jamais le signaler ; ajout de `is_connected()`/`_connected` côté backend, comptage des échecs consécutifs dans `_fen_reader_loop` (driver.py), callback `_board_lost_cb` câblé sur `board_error` dans `board_adapter.create_board()`, et `reconnect_board` intercepté dans `server.py::on_action` pour fonctionner aussi bien au menu qu'en cours de partie.
- **Déconnexion plateau non détectée au menu + retours menu forcés silencieux** `[Linux]` — issue #103. Thread daemon `_board_menu_watcher` (alchess.py) qui poll `hid_backend.is_connected()` toutes les 3s tant que `_app_state == "menu"` ; retour menu depuis HH re-déclenche `_check_board_at_startup()`. Toasts d'erreur (`toast_message_key`/`toast_message`/`toast_type` dans `set_app_state("menu", ...)`) ajoutés dans `game_manager.py` pour `launch_pedagogique`/`launch_humain`/`launch_labo_libre` (échiquier non détecté, timeout position, moteur KO, exception non catégorisée) ; affichage côté `app.js` (handler `app_state`) déjà en place. **Non traité** : la perte du plateau en cours de partie active (`_board_lost_cb`) n'entraîne toujours pas de retour menu forcé — le thread `_fen_reader_loop` s'arrête et notifie `board_error`, mais les boucles de jeu (human.py/pedagogique.py) ne consomment pas ce signal pour interrompre `game.start()`. Corriger proprement nécessiterait un flag d'abandon consulté par la boucle de jeu ; risque de régression trop élevé pour être fait sans test matériel dans cette session.

---

## 💡 Fonctionnalités à venir

- **Chantier « l'UI reflète l'état réel du système »** `[Les deux]` — détection de la déconnexion en cours de session faite (issue #102), et au menu (issue #103) ; reste : (1) griser les boutons `data-needs-board` sur réception de `board_error` en cours de partie (aujourd'hui seul `board_ok` les réactive) ; (2) forcer un retour menu (avec toast `toast.board_lost`, clé déjà en place) quand le plateau est perdu **pendant une partie active**, ce qui suppose de faire consulter un flag d'abandon par les boucles de jeu `human.py`/`pedagogique.py`.
- **Tutoriels utilisateur** `[Les deux]` — autres aides in-app à ajouter au fil des besoins.
- **Nettoyer le dossier Rodent dans le packaging** — trier par OS (`mac/`, `sources/`, `books/` volumineux inutiles au paquet final).
- **Réduire la taille des ZIP** (~210/215 Mo) — élagage `books/`/`exe/`/`docs/` de Rodent à valider avec Alain.
- **i18n — corrections résiduelles au fil des tests DE** (edge cases, `eco_import.py`).
- **Améliorer la visibilité moteurs de recherche** `[Les deux]` — image de prévisualisation sociale, communautés (r/chess, forums Chessnut).

---

## 🧪 Tests automatisés

- **Niveau 1** — Checklist manuelle : `TESTS.md` (smoke 5 min / régression 20 min)
- **Niveau 2** — `nicsoft/tests/test_app_state.py` (25 tests pytest)
- **Niveau 3** — `nicsoft/tests/e2e/` (42 tests Playwright headless)
- **Mode test aléatoire** — `NICLINK_TEST=random python -m nicsoft.web` + bouton 🎲

---

## 📝 Notes techniques

- **USB Chessnut** : quirk `/etc/modprobe.d/chessnut.conf` — voir `INSTALLATION_ALCHESS.md` section 4b.
- **`retranscription_en_cours`** au démarrage : normal (reprise), ne traiter que sur l'écran Retranscription.
- **Bridge mode écriture** : label GitHub `mode_write` arme l'écriture ; détail dans `BRIDGE_AGENT_DOC.md`.
- **Runtime VC++ (Windows)** : `lc0.exe` (Maia) exige `MSVCP140.dll`, sinon crash `0xC0000135`.
- **VM Windows (VirtualBox)** : `AlChess-Win11`, EFI+TPM 2.0, 6 Go RAM, 2 CPU, compte local (`Maj+F10` → `start ms-cxh:localonly`).
