# AlChess — Tâches et bugs

---

## ⚡ Prioritaire

- **Release v1.3.1 à packager** `[Linux/Windows]` — regrouper les correctifs depuis v1.3.0 (dont issue #96) : `./make_release.sh 1.3.1` + tag + `gh release create`.
- **ACTION ALAIN — Validation VM NSIS** `[Windows]` — relancer `AlChess_Setup.exe` sur VM Windows et confirmer l'installation/lancement de bout en bout (issues #64–#67, #58).
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
