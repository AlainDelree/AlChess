# AlChess — Contexte projet

Briefing destiné à Claude Code (CCL) et aux nouvelles conversations. Reflète
l'état réel du dépôt vérifié le 11 juillet 2026 (branche de travail : `dev`).

---

## Projet

**Nom** : AlChess (anciennement NicLink)
**Description** : application Python/Flask-SocketIO connectant un échiquier
physique Chessnut Air (USB) à une interface web pédagogique. Fonctionne aussi en
mode virtuel (sans échiquier).
**Développeur** : Alain (Namur, Belgique) — non développeur de formation, projet
construit avec l'aide de Claude.
**Stack** : Python (Flask-SocketIO) ; frontend vanilla JS (`app.js`), HTML
(`index.html`), CSS (`static/css/main.css`) ; Ubuntu (poste principal) + support
Windows.
**Dépôt local** : `~/NicLink/` (venv à `~/NicLink/venv/`)
**GitHub** : https://github.com/AlainDelree/AlChess (public)

---

## Architecture

Backend
- **`nicsoft/niclink/hid_backend.py`** — backend USB en **hidapi Python pur**
  (remplace l'ancien `_niclink.so` C++, qui n'est plus nécessaire).
- **`nicsoft/niclink/driver.py`** — couche driver Chessnut Air (lecture FEN,
  thread dédié, LEDs, beep).
- **`nicsoft/niclink/virtual_board.py`** — échiquier virtuel (mode sans hardware).
- **`nicsoft/niclink/nl_exceptions.py`** — exceptions maison (ex. arrêt propre en
  mode web au lieu d'un `sys.exit()`).
- **`nicsoft/web/alchess.py`** — chef d'orchestre (allégé par la réarchitecture,
  ~233 lignes).
- **`nicsoft/web/server.py`** — serveur Flask-SocketIO, machine d'état `_app_state`,
  détection de disponibilité des moteurs (caches + events `*_status`).
- **`nicsoft/web/static/app.js`** — toute la logique JS frontend.
- **`nicsoft/web/templates/index.html`** — interface HTML (mono-template).
- **`nicsoft/core/game_manager.py`** — gestion de partie (coups, historique, état).
- **`nicsoft/core/board_adapter.py`** — adaptation Core ⇄ Transport.
- **`nicsoft/engine/`** — moteurs UCI : `engine_manager.py` (détection + wrappers),
  `players.py`, `pgn_manager.py`, `board_utils.py`, `display.py`, `analyse.py`.
- **`nicsoft/config.py`** — chemins centralisés (`APP_DIR` auto-détecté, plus de
  dépendance à `~/NicLink` en dur).
- **`nicsoft/platform_utils.py`** — isole les appels OS Linux-only (ModemManager…).
- **`nicsoft/modes/`** — `pedagogique/` (vs Stockfish/Maia/Rodent), `humain/`,
  `retranscription/`, `labo/` (analyse libre), `exercices/` (ouvertures).
- **`nicsoft/utils/`** — `backup_manager.py`, `timing.py`, `light_board.py`,
  `debug.py`, etc.

## Machine d'état (`_app_state`)
`menu` → `config` / `config_humain` / `retranscription` / `exercices` / `labo`
→ `connecting` → `playing` / `paused` → `game_over`

## Queues
- `event_queue` : Python → navigateur
- `action_queue` : navigateur → Python (états actifs)
- `menu_queue` : navigateur → Python (état menu)

---

## Moteurs d'échecs

Détection dans `engine_manager.py` : `find_stockfish()`, `find_lc0()`,
`find_maia_weights(elo)`, `find_rodent()` (chemin ou `None`) + `stockfish_available()`,
`maia_available()`, `rodent_available()`. `server.py` met ces résultats en cache
au démarrage et émet `stockfish_status` / `maia_status` / `rodent_status` à la
connexion ; le front grise le moteur indisponible et replie sur le premier moteur
disponible.

- **Stockfish** : Linux → `stockfish` système (`/usr/games/stockfish`), PATH ou
  `engines/stockfish` ; Windows → `engines/stockfish*.exe`. Détection = présence.
- **Maia** : `lc0` (Linux) ou `engines/maia/lc0.exe` (Windows) **+** au moins un
  poids `engines/maia/maia-*.pb.gz`. Détection = présence.
- **Rodent IV** : binaire Linux dans le **sous-module** `engines/rodent-iv/` ;
  binaire Windows `engines/rodent-iv-win/rodent-iv-x64.exe` (+ DLL), tracké **hors
  sous-module** pour survivre à un clone frais. Le packaging le recopie en
  `engines/rodent-iv/rodentIV.exe`. Détection = **handshake UCI** (`rodent_available()`).
  Ordre `setoption` impératif : **Personality → UCI_LimitStrength → UCI_Elo**.

---

## Système bridge inter-agents

Les tâches arrivent à CCL via **GitHub Issues** (repo AlChess). Le watcher
surveille les issues étiquetées `for-linux` et les délègue à CCL, qui travaille
**exclusivement dans `~/NicLink`**.
- **Lecture seule par défaut** ; le label `mode_write` arme l'écriture.
- En mode écriture : **backup pinné obligatoire avant toute modif**, **jamais de
  `git push`** (Alain pousse après vérification du diff), aucune commande
  destructrice sans demande explicite.
- Détail complet du système : `BRIDGE_AGENT_DOC.md` (repo `Bridge_Agent`).

---

## Conventions de travail

**En début de session :** lire `TACHES.md` (tâches/bugs) et `TESTS.md` (régression) ;
faire `git status` et vérifier la **branche** (`dev` = travail vif) avant toute modif.

**Git :**
```bash
git status                         # avant de commencer
git add <fichiers ciblés> && git commit -m "description"
git checkout .                     # annuler si ça casse
```
Plusieurs commits locaux puis un `git push`. Merge `dev` → `master` quand le lot
est prêt pour la partie publique / Release.

**Backup pinné aux jalons :**
```bash
python -m nicsoft.utils.backup_manager --pin --label "description-courte"
```

**Démarrer le programme :**
```bash
cd ~/NicLink && python -m nicsoft.web       # ModemManager arrêté automatiquement
```

**Prérequis USB Chessnut (ThinkPad X1 Carbon Gen 7) :**
- Quirk usbhid : `/etc/modprobe.d/chessnut.conf`
  → `options usbhid quirks=0x2d80:0x8003:0x40`
- Backend USB : **hidapi Python pur** (`hid_backend.py`) — plus de `.so` C++ à
  recompiler. Voir `INSTALLATION_ALCHESS.md` section 4b.
- `python3-gi` est une lib système (pas installable dans le venv) : le launcher
  utilise `/usr/bin/python3`.
- USB autosuspend peut déconnecter le Chessnut → règle udev (`autosuspend=-1`).

---

## Principes techniques importants

- **Contention USB** : tout accès USB passe par le thread de lecture dédié du
  driver. Pas d'appel direct concurrent au board.
- **`board.move_stack` = source de vérité** pour l'historique. `chess.Board(fen)`
  efface `move_stack` → reconstruire depuis l'historique après coup pour éviter la
  corruption d'état entre modes.
- **Toujours un `time.sleep()`** (min 0.05 s) dans les boucles de polling.
- **Threads LED en daemon** pour ne pas bloquer la boucle de jeu.
- **Handler `on_action`** : tout `sendAction({type: X})` côté JS doit avoir son
  `elif` correspondant côté Python.
- **i18n** : toute nouvelle clé doit être ajoutée **simultanément** dans
  `fr.json`, `en.json`, `de.json` (dossier `static/i18n/`) ; si l'allemand est
  incertain, mettre la valeur anglaise en attendant — jamais de clé absente.
- **Édition de code Python** : préférer `python3 -c` à `sed` (fragile en
  multi-ligne). `engines/rodent-iv/` est un **sous-module**, pas un dossier suivi
  ordinaire — en tenir compte.

---

## Fichiers de suivi

| Fichier | Contenu |
|---------|---------|
| `TACHES.md` | Bugs connus, chantiers en cours, fonctionnalités à venir |
| `TESTS.md` | Checklist de régression (smoke + complet) |
| `TEST_RESULTATS.md` | Résultats des sessions de test, datés |
| `HISTORIQUE_BUGS.md` | Bugs résolus, causes racines, tests de non-régression |
| `INSTALLATION_ALCHESS.md` | Installation sur nouveau PC (Linux/Windows) |
| `I18N.md` | Fonctionnement de l'internationalisation |
| `CLAUDE.md` | Contexte auto-chargé par Claude Code à la racine du projet |

---

## État actuel (mis à jour le 11 juillet 2026)

**Stable et fonctionnel (Linux + Windows) :**
- Modes : Pédagogique (vs Stockfish / Maia / Rodent), Humain vs Humain, Analyse
  (import PGN, navigation), Exercices/Ouvertures, Retranscription, Labo, mode virtuel.
- Les **trois moteurs** fonctionnent sur les deux OS.
- **i18n FR / EN / DE** complète sur tous les écrans.

**Terminé :**
- **Réarchitecture multiplateforme** (mergée `master`) : `hid_backend.py` (hidapi),
  `nicsoft/core/`, `config.py`, `platform_utils.py` ; `alchess.py` fortement allégé.
- **Portage Windows** validé en VM : installateur `install_alchess.ps1`, hidapi
  16/16 tests, Stockfish + Maia + Rodent jouables.
- **Release publique v1.0.0** : ZIP Linux + Windows, topics GitHub, README orienté
  téléchargement. Rodent réintégré dans les ZIP pour la v1.1.
- **Récent (11 juillet)** : taglines moteurs (Top! / Humain / Faible) ; **grisage
  des moteurs indisponibles** (Stockfish + Maia, calqué sur Rodent) avec repli
  automatique sur le premier moteur disponible et alerte « aucun moteur ».

**Bugs actifs :**
- **À corriger** : HH — écran de rangement ignoré si l'échiquier se déconnecte
  silencieusement `[Windows]` (investiguer la détection de perte USB côté `driver.py`).
- **En veille** : race condition LEDs `[Linux]` (rare, hardware/USB) ; WAIT_FISH
  lent intermittent (>30 s occasionnels, hardware Chessnut Air).

**Chantiers ouverts :**
- « L'UI reflète l'état réel » : renommer le statut « Connected » trompeur
  (Socket.IO ≠ état échiquier). Le grisage des moteurs — l'autre volet — est fait.
- Finitions Windows : raccourci bureau double-clic ; passer `install_alchess.ps1`
  entièrement en anglais.
- `git submodule update --init` qui échoue sur clone frais — à investiguer.
