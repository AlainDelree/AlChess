# Changelog — Issue #255

# Changelog — Issue #263

## Découplage de la logique de jeu : plus d'import de nicsoft.web depuis core/modes/niclink/utils/engine (règle ARC-001)

Recensement complet refait avant correction (l'audit initial, limité à
`nicsoft/modes`, comptait 32 sites) : **34 sites réels** répartis sur 7
fichiers — `nicsoft/core/game_manager.py` (11), `nicsoft/modes/humain/human.py` (7),
`nicsoft/modes/pedagogique/pedagogique.py` (7), `nicsoft/modes/exercices/exercices.py` (5),
`nicsoft/niclink/virtual_board.py` (3), `nicsoft/modes/labo/labo.py` (1),
`nicsoft/core/board_adapter.py` (1). (`nicsoft/utils/debug.py` et
`nicsoft/utils/timing.py` ne mentionnaient `nicsoft.web` que dans un
commentaire/docstring — aucun import réel.) `nicsoft/modes/retranscription/retranscription.py`
était déjà découplé : il reçoit `web_server` en paramètre (injection de
dépendance) plutôt que de l'importer — c'est le motif qui a inspiré la
solution retenue pour les autres fichiers.

**Solution retenue** : un port neutre, **`nicsoft/core/ihm_port.py`**, expose
aux modules de jeu les primitives dont ils ont besoin (`send_event`,
`get_action`, `set_app_state`, `set_virtual_board`, `get_history`/`set_history`,
`get_action_queue`, `get_app_state`/`set_raw_app_state`, `check_board_at_startup`,
`emit`). Tant qu'aucun backend n'est branché (import isolé, tests), un
backend neutre (`_NullBackend`) répond sans effet de bord — permet d'importer
n'importe quel module de jeu sans lancer le serveur web. Au démarrage réel,
`nicsoft/web/alchess.py` branche l'implémentation Flask-SocketIO via
`ihm_port.register_backend()`.

Les très nombreux sites qui accédaient directement au module
`nicsoft.web.server` (`web_server._app_state = ...`, `web_server.action_queue...`)
— notamment dans `game_manager.py` et `human.py`, pour la course critique
SocketIO qui écrit `_app_state` silencieusement avant d'appeler `set_app_state()`
(pour éviter une fenêtre de race pendant la notification navigateur) — n'ont
*pas* été réécrits un par un : `ihm_port.app_state_proxy` reproduit exactement
le même objet dupliqué (property `_app_state` + `action_queue`), ce qui a
permis de ne changer que la ligne d'import sur ces sites et de garder le reste
du code strictement identique. Seul `game_manager.py:304` (import différé de
`nicsoft.web.alchess._check_board_at_startup`, seul cas de cycle réel —
`alchess.py` importe `game_manager` au niveau module) devient
`ihm_port.check_board_at_startup()`.

Migration faite mode par mode, un commit par étape (points de retour arrière) :
port neutre → `niclink/virtual_board.py` → `core/board_adapter.py` →
`modes/labo/labo.py` → `modes/exercices/exercices.py` →
`modes/pedagogique/pedagogique.py` → `modes/humain/human.py` →
`core/game_manager.py` → test d'isolation.

Ajout de `server.emit()` (émission SocketIO directe, hors `event_queue`) pour
couvrir un site (`pedagogique.py`) qui faisait `socketio.emit()` directement
pour un popup ponctuel, sans passer par `send_event()`.

Un site a changé de forme sans changer de résultat : `pedagogique.py` lisait
`_game_state["history"]` directement (sans le verrou), remplacé par
`get_history()[0]`, l'accesseur déjà prévu par `server.py` pour cet usage
précis d'après sa propre docstring ("à utiliser par tout module hors
server.py").

**Résultat** : plus aucun import de `nicsoft.web` depuis `core`, `modes`,
`niclink`, `utils`, `engine` (vérifié par recherche dans le code — seules des
mentions en commentaire/docstring subsistent dans `ihm_port.py`, `debug.py`,
`timing.py`). Comportement strictement identique : mêmes événements, mêmes
files d'actions, mêmes fils d'exécution.

**Fichiers modifiés :**

`nicsoft/core/ihm_port.py` (nouveau), `nicsoft/web/server.py`,
`nicsoft/web/alchess.py`, `nicsoft/niclink/virtual_board.py`,
`nicsoft/core/board_adapter.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/core/game_manager.py`,
`nicsoft/tests/test_no_web_import.py` (nouveau).

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
54 passed, 3 skipped (hardware), dont le nouveau
`test_no_web_import.py` (14 cas, chacun dans un sous-processus Python
propre pour ne pas être pollué par d'autres tests qui importent
`nicsoft.web.server` pour leurs propres besoins). Smoke-test manuel du
serveur réel (`start_server()` + requête HTTP sur `/`) : backend branché,
`_app_state` piloté via le port identique à l'ancien accès direct au
module. Suite e2e non lancée (nécessite Playwright + serveur lancé depuis
`~/NicLink`, hors périmètre du worktree).

**À vérifier manuellement par Alain, avec l'échiquier physique branché**
(aucun hardware disponible dans l'environnement de l'agent) :
- Mode Pédagogique (Stockfish/Maia/Rodent) : coup joué, feedback LED,
  pause sur erreur/blunder, reprise, abandon, fin de partie (mat/nulle),
  notification popup mat/pat.
- Mode Humain vs Humain : coups, undo, abandon, nulle par accord mutuel,
  retour menu depuis un état actif (vérification silencieuse du plateau
  au retour menu).
- Mode Exercices : synchronisation initiale, détection hors-théorie,
  retry/continue, retour menu.
- Mode Labo : suivi du plateau physique, meilleur coup, mode auto,
  analyse, copie de position.
- Déconnexion USB en cours de partie (callback `_board_lost_cb` →
  `board_error`) : le message doit toujours apparaître côté navigateur.
- Démarrage de l'appli complète (`python -m nicsoft.web`) suivi d'un tour
  dans chaque mode, pour confirmer qu'aucune régression de câblage n'est
  passée inaperçue dans l'environnement sans hardware de l'agent.

# Changelog — Issue #262

## Analyse de partie : ignorer le chemin du moteur sauvegardé s'il n'existe pas sur cette machine

`analyser_partie()` (`nicsoft/engine/analyse.py`) lisait le chemin du moteur
enregistré dans `data/config.json` et le transmettait tel quel à
`EngineManager`, sans vérifier qu'il existait sur la machine courante. Une
configuration copiée depuis une autre machine, ou un moteur désinstallé/déplacé,
faisait planter l'analyse au lieu de retomber sur la recherche automatique de
Stockfish (`find_stockfish()`) — repli qui n'était utilisé que lorsque le
chemin était vide.

La logique de validation (`chemin sauvegardé conservé seulement s'il existe`)
existait déjà dans `nicsoft/core/game_manager.py` sous le nom
`_validated_engine_path()`, utilisée par les autres modes de jeu. Pour éviter
une troisième copie tout en respectant le sens des dépendances (`engine` ne
doit pas dépendre de `game_manager`, qui dépend de la couche web), cette aide
est déplacée vers **`nicsoft/core/config_manager.py`** (module neutre, déjà
point d'accès centralisé à `config.json` depuis #259), renommée
`validated_engine_path()` (devenue un helper public partagé plutôt qu'un
détail interne de `game_manager`). `game_manager.py` pointe maintenant vers
cette version déplacée, sans changement de comportement.

`analyser_partie()` réutilise aussi `read_json_with_defaults()` (lecture de
config partagée introduite par #259) à la place de sa propre lecture JSON
manuelle, avec le même message de log en cas d'échec.

**Fichiers modifiés :**
- `nicsoft/core/config_manager.py` — ajout de `validated_engine_path()`.
- `nicsoft/core/game_manager.py` — utilise `validated_engine_path()` importé de `config_manager` (suppression de la copie locale `_validated_engine_path`).
- `nicsoft/engine/analyse.py` — `analyser_partie()` valide le chemin moteur sauvegardé et réutilise `read_json_with_defaults()`.
- `nicsoft/tests/test_analyse_engine_path.py` (nouveau) — 3 tests avec `EngineManager` simulé (aucun vrai moteur lancé) : chemin inexistant → repli `find_stockfish()`, chemin existant → conservé, chemin vide → comportement inchangé.

Suite de tests complète (hors `hardware`) : 82 passed, 4 skipped.

# Changelog — Issue #261

## Erreurs silencieuses : trace ou justification de chaque except sans traitement (règle PRO-012)

L'audit relevait 52 captures d'erreur silencieuses (exemples : `platform_utils.py`,
`labo.py`, `retranscription.py`, sept occurrences dans `game_manager.py`). Un
recensement complet refait avant correction (les numéros de ligne de l'audit
avaient bougé) a trouvé **133 occurrences réelles** réparties sur 29 fichiers —
l'audit initial était partiel.

Pour chaque occurrence, choix au cas par cas, sans jamais modifier le flux de
contrôle (aucun nouveau `raise`, aucune valeur de retour changée) :

- si l'erreur peut révéler une vraie panne → journalisée avec le logger du
  module (`logger.warning`/`logger.error` pour les cas significatifs,
  `logger.debug` dans les boucles d'interrogation rapides du plateau physique
  ou pour les fallbacks fréquents/attendus, afin de ne pas inonder les logs) ;
- si le repli silencieux est voulu (valeur par défaut, fichier optionnel
  absent, nettoyage best-effort en fin de programme/thread, idiome de vidage
  de `queue.Empty`, saisie interactive interrompue, exception de contrôle de
  flux comme `BackMenuExit`/`ExitNicLink`) → conservé, avec un commentaire
  explicatif ajouté dans le corps du `except`.

**Résultat : 72 cas journalisés, 61 cas justifiés par commentaire.**

Cas le plus significatif : `nicsoft/niclink/driver.py`, `_fen_reader_loop()`
— tout le thread de lecture USB était silencieux ; passé en `logger.debug`
(boucle à 50ms, erreurs transitoires fréquentes, mais désormais visibles en
mode `NICLINK_LOG=DEBUG`). Autre cas notable : `nicsoft/core/config_manager.py`
— `load_config()` ignorait un `config.json` corrompu sans aucune trace nulle
part ; utilise maintenant le paramètre `on_error` déjà prévu par
`read_json_with_defaults()` pour journaliser, sans changer la valeur retournée
(les défauts restent utilisés comme avant).

**Fichiers modifiés (29) :**

`nicsoft/platform_utils.py`, `nicsoft/core/config_manager.py`,
`nicsoft/core/game_manager.py`, `nicsoft/engine/analyse.py`,
`nicsoft/engine/board_utils.py`, `nicsoft/engine/display.py`,
`nicsoft/engine/engine_manager.py`, `nicsoft/engine/pgn_manager.py`,
`nicsoft/modes/exercices/_catalogue.py`,
`nicsoft/modes/exercices/add_ouverture.py`,
`nicsoft/modes/exercices/eco_import.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/exercices/explore_book.py`,
`nicsoft/modes/exercices/import_lignes.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/opening_explorer/explorer_session.py`,
`nicsoft/modes/opening_explorer/llm_explainer.py`,
`nicsoft/modes/opening_explorer/sources.py`,
`nicsoft/modes/opening_explorer/tts_engine.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/retranscription/retranscription.py`,
`nicsoft/niclink/driver.py`, `nicsoft/niclink/hid_backend.py`,
`nicsoft/niclink/virtual_board.py`, `nicsoft/tests/e2e/conftest.py`,
`nicsoft/web/alchess.py`, `nicsoft/web/launcher.py`, `nicsoft/web/server.py`.

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
37 passed, 3 skipped (hardware). Suite e2e non lancée (nécessite Playwright
+ un serveur lancé depuis `~/NicLink`, hors périmètre du worktree).

# Changelog — Issue #260

## Rodent IV Linux : fin du faux dépôt imbriqué, documentation corrigée

`engines/rodent-iv` était enregistré dans l'index git comme un lien vers un
dépôt imbriqué (clone de `nescitus/rodent-iv`) sans jamais être déclaré comme
sous-module (`.gitmodules` ne le mentionnait pas). Conséquences : dossier vide
après un clonage frais, binaire local signalé en permanence comme
« modifié » sur la machine de dev, et documentation affirmant à tort que le
binaire Linux était inclus dans le dépôt (vrai seulement pour `lc0`).

**Changé :**

- `.gitignore` — ajout de `engines/rodent-iv/` : le dossier (dépôt git
  imbriqué + binaire compilé localement) n'est plus jamais suivi ni signalé
  comme modifié.
- Index git — `git rm --cached engines/rodent-iv` : retire l'entrée de
  dépôt imbriqué de l'index, sans toucher aux fichiers sur disque.
- `INSTALLATION/INSTALLATION_NICLINK.md` — ne prétend plus que le binaire
  Linux de Rodent IV est inclus dans le dépôt ; ajoute les instructions pour
  l'obtenir (clone + compilation de `https://github.com/nescitus/rodent-iv`,
  binaire à placer en `engines/rodent-iv/rodentIV` et à rendre exécutable) et
  corrige l'URL du dépôt source (était `nescior/Rodent_IV`, inexistant/non
  utilisé).
- `install.sh` — message clair quand `engines/rodent-iv/rodentIV` est
  absent (cas normal après un `git clone`), avec pointeur vers la section
  de compilation de la doc. Pas de téléchargement/compilation automatique.
- `make_release.sh` — commentaires corrigés : ne parlent plus de
  « sous-module » (qui n'a jamais existé pour ce chemin) mais de « dépôt git
  imbriqué, jamais déclaré en sous-module ». Comportement du script
  inchangé.

**Vérifié :**

- `find_rodent()` (`nicsoft/engine/engine_manager.py`) ne dépend que de
  l'existence du fichier `engines/rodent-iv/rodentIV` — inchangé par ce
  correctif, qui ne touche à aucun fichier Python.
- `make_release.sh` continue de supposer (comme avant) que le dépôt imbriqué
  réel, avec le binaire compilé, est présent sur la machine de build —
  c'est toujours la machine de dev d'Alain qui alimente le ZIP de release.

**À faire manuellement par Alain (voir commentaire de clôture de l'issue) :**
sauvegarde du binaire compilé avant la fusion sur la machine réelle, puis
vérification qu'il est toujours présent après.

# Changelog — Issue #259

## Factorisation du code dupliqué entre les fichiers du moteur (règle PRO-014)

L'audit signalait ~27 lignes identiques réparties sur plusieurs fichiers
(hypothèse initiale : `board_adapter.py`, `config_manager.py`,
`game_manager.py`, `analyse.py`, `board_utils.py`). Après vérification,
les blocs réellement dupliqués ne sont pas exactement ceux listés par
l'audit mais relèvent bien de la même cause : la lecture de
`data/config.json`, dupliquée localement — point que `config_manager.py`
documentait déjà lui-même comme "hors scope pour l'instant".

**Fusionné :**

- `nicsoft/core/config_manager.py` — nouvelle fonction
  `read_json_with_defaults(path, defaults, on_error=None)`, qui isole la
  logique « lit un JSON, fusionne sur des defaults, retombe sur les
  defaults si absent/invalide ». `load_config()` du module l'utilise
  désormais.
- `nicsoft/modes/pedagogique/pedagogique.py` et
  `nicsoft/modes/humain/human.py` — leurs `load_config()` locaux (mêmes
  defaults et même niveau de log qu'avant) délèguent maintenant la lecture
  JSON à `read_json_with_defaults()` au lieu de la dupliquer. Import
  `json` devenu inutile, retiré.
- `nicsoft/core/game_manager.py` — `launch_pedagogique()` et
  `launch_labo_libre()` contenaient le même bloc de 11 lignes (lecture de
  `engine_elo`/`engine_path` depuis `config.json`, byte pour byte
  identique, y compris le message de log). Extrait en
  `_read_engine_elo_and_path()`.

**Non fusionné (écarts de comportement réels, signalés sans forcer) :**

- Trois autres blocs de `game_manager.py` (exercice libre, drill, labo)
  lisent aussi `engine_elo`/`engine_path` depuis `config.json`, mais
  diffèrent sur des points fonctionnels : portée du `try/except` (un
  échec JSON désactive entièrement le moteur dans un cas, retombe sur des
  defaults dans un autre), ordre du repli `find_stockfish()`, et pour le
  mode labo l'`engine_elo` provient en réalité d'un dict de configuration
  runtime (pas du fichier). Les fusionner sans vérification individuelle
  aurait changé ces comportements.
- `nicsoft/engine/analyse.py` lit aussi `engine_path` depuis
  `config.json`, mais sans passer par la validation d'existence du
  chemin sur la plateforme courante (`_validated_engine_path`) — une
  différence de comportement pré-existante, potentiellement un écart à
  signaler séparément, pas touchée ici.
- `nicsoft/modes/humain/human.py` (fonction CLI historique, hors flux
  web) instancie `NicLinkManager` directement plutôt que via
  `nicsoft.core.board_adapter.create_board()` : ce chemin CLI n'a pas le
  callback `_board_lost_cb` (qui dépend de `nicsoft.web.server`), donc le
  fusionner aurait introduit une dépendance et un comportement nouveaux.
- `nicsoft/core/game_manager.py` (`_wait_initial_position_web` /
  `_wait_position_web`) ressemble à `wait_for_initial_position()` de
  `nicsoft/engine/board_utils.py`, mais la version web pilote
  `set_app_state`/`send_event` au lieu d'imprimer dans le terminal —
  différence de transport volontaire, non fusionnée.

**Tests** : `python -m pytest nicsoft/tests/` → 79 passed, 4 skipped
(tests matériel auto-skippés en l'absence d'USB), aucune régression.

# Changelog — Issue #256

## Téléchargement Rodent IV (Win) : délai d'attente et vérification d'intégrité

`on_download_rodent` (`nicsoft/web/server.py`) récupérait les 3 fichiers du
moteur Rodent IV Windows (`rodent-iv-x64.exe`, `msvcr120.dll`,
`msvcp120.dll`) via `urllib.request.urlretrieve`, sans délai d'attente ni
vérification, avant de les rendre utilisables (règles EXP-013 et SEC-022 de
l'audit).

Nouvelle fonction `_telecharger_fichier_rodent()` :
- télécharge via `urllib.request.urlopen(..., timeout=15)` (remplace
  `urlretrieve`, qui ne supporte aucun paramètre de délai) ;
- calcule l'empreinte SHA-256 du contenu pendant le téléchargement et la
  compare à une référence connue (`_RODENT_WIN_SHA256`) ;
- en cas d'écart, de délai dépassé, ou d'absence de référence connue pour
  un nom de fichier : supprime le fichier téléchargé (jamais installé) et
  laisse l'exception remonter — l'échec est signalé à l'interface via
  l'événement `rodent_download_result` existant (comportement inchangé,
  déjà adapté).

**Provenance des empreintes de référence** — calculées directement depuis
les fichiers déjà versionnés dans ce dépôt sous `engines/rodent-iv-win/`
(commit courant), qui sont exactement la même release que celle
re-téléchargée par ce handler pour les installations NSIS standalone
n'embarquant pas ces fichiers. Aucune empreinte n'a été calculée à partir
d'un téléchargement non vérifié. Les 3 fichiers du moteur ont pu être
couverts par cette référence versionnée — aucun fichier n'a dû être laissé
sans référence :
- `rodent-iv-x64.exe` → `39c879b2dfdaf0252e94db547397d95422fee76ea8bafa584bfdc03e4d648de5`
- `msvcr120.dll` → `ad32240bb1de55c3f5fcac8789f583a17057f9d14914c538c2a7a5ad346b341c`
- `msvcp120.dll` → `81fbc2824e73f0d101d91854694a52e79db0ffaadbb2a10deaaf47b3b7f9b2b0`

Tests ajoutés dans `nicsoft/tests/test_rodent.py` (4 nouveaux, aucun accès
réseau réel, `urllib.request.urlopen` mocké) :
- délai dépassé → `URLError` propagée, aucun fichier créé ;
- empreinte invalide → `ValueError`, fichier supprimé ;
- nom de fichier sans référence connue → refusé avant toute requête réseau ;
- empreinte valide → fichier écrit normalement.

Suite complète (hors `test_move_matching.py`/`test_players.py`, en échec
préexistant dans cet environnement faute du module `hid`, sans rapport
avec ce changement) : 74 passed, 4 skipped, aucune régression.

Backup pinné : `avant-issue256-rodent-timeout-integrite`.

## Dépendances : correctifs de sécurité, épinglage des versions flottantes, retrait de berserk

Audit `requirements.txt` : 4 paquets en retard de correctifs de sécurité
(SEC-001), 2 non épinglés (EXP-001), et `berserk` déclaré mais jamais
importé (reste de NicLink).

- **Correctifs de sécurité** (`pip-audit` : 11 vulnérabilités → 0) :
  - `setuptools` 69.1.1 → 84.1.0 (PYSEC-2025-49, PYSEC-2026-1918,
    PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w)
  - `wheel` 0.42.0 → 0.46.2 (CVE-2026-24049)
  - `python-socketio` 5.16.1 → 5.16.2 (PYSEC-2026-3042)
  - `Werkzeug` 3.1.7 → 3.1.9 (PYSEC-2026-4312)
- **Épinglage** des versions flottantes, sur la version installée/testée :
  - `numpy` `>=1.26.4` → `==2.5.4`
  - `edge-tts` `>=6.1.0` → `==7.3.1`
- **Retrait de `berserk`** (`requirements.txt` + tableau d'inventaire
  `ETAT_PROJET.md`) : aucun import dans le code, aucune référence dans les
  scripts d'installation (`1-Installer.bat`, `bootstrap_linux.sh`) ni
  l'installeur Windows.

Aucun conflit de compatibilité : `pip check` propre avec Flask 3.1.3 et
Flask-SocketIO 5.6.1 après les 4 montées de version. Suite de tests
complète (hors marqueur `hardware`) : 75 passed, 4 skipped.

`ETAT_PROJET.md` mis à jour en cohérence (tableau §5, versions
`python-socketio`/`Werkzeug`/`numpy`, ligne `berserk` supprimée).

# Changelog — Issue #212

## Tests e2e Exercices mis à jour pour le nouveau chemin de navigation

`test_exercices_liste_affichee` et `test_retour_depuis_exercices`
(`nicsoft/tests/e2e/test_smoke_e2e.py`) ciblaient encore le bouton direct
"Exercices" du menu principal, retiré au commit e648146 (issue #141,
réorganisation "Ouvertures"). Le chemin actuel comporte 2 étapes : clic sur
le bouton du wrapper `#wrap-ouvertures` (mène à `#screen-ouvertures`), puis
clic sur la carte `.outil-card-clickable` portant
`onclick="_menuCardLaunch('exercices', this)"` (mène à `#screen-exercices`).

Ajout d'un helper `go_exercices(page)` qui suit ce chemin en 2 étapes avec
des sélecteurs indépendants de la langue (même approche que le fix #208) :
- `#wrap-ouvertures button` — id déjà unique, pas de filtre sur le texte.
- `.outil-card-clickable[onclick*="'exercices'"]` — fragment d'attribut
  `onclick`, indépendant des libellés traduits ("📖 Openings"/"📚 Exercises"
  en anglais, langue par défaut de l'environnement de test).

Vérifié : aucune autre référence à l'ancien sélecteur
`button, has_text="📚 Exercices"` dans le fichier. Le bouton "← Menu" de
retour depuis `#screen-exercices` (ligne ~873 de `index.html`) est du texte
brut sans `data-i18n`, donc déjà indépendant de la locale — inchangé.

Suite `nicsoft/tests/e2e/test_smoke_e2e.py` complète : 12 passed, 1 skipped
(hardware), aucune régression.

Backup pinné : `avant-fix-e2e-exercices-navigation-issue212`.

# Changelog — Issue #201

## Suppression du code mort dupliqué (modes pédagogique et labo)

Suppression de deux fichiers orphelins, non importés nulle part dans le
code (aucun `import`, aucune référence dans les scripts `.sh`/`.bat`/`.ps1`,
aucune référence dans `.github/`) :

- `nicsoft/modes/pedagogique/__main__ (pedagogique).py` (1691 lignes) —
  nom de fichier non conforme (espace + parenthèses), donc non importable
  comme module Python de toute façon.
- `nicsoft/modes/labo/__main__labo.py` (409 lignes).

Comparaison ligne à ligne avec les fichiers canoniques réellement utilisés
(`pedagogique.py`, importé par `nicsoft/core/game_manager.py`, et `labo.py`,
importé par le même fichier ainsi que par `nicsoft/modes/labo/__main__.py`) :
les deux fichiers canoniques sont des évolutions strictement plus complètes
des fichiers supprimés (mêmes fonctionnalités + i18n, `RodentEngine`,
pipeline de précalcul du coup moteur, `kill_switch`, `BackMenuExit`, etc.).
Aucune portion de logique utile n'a été identifiée comme présente
uniquement dans les fichiers supprimés — le reste des différences est de la
plomberie CLI obsolète (ancien point d'entrée `main()`/`argparse`/`input()`
préexistant à l'architecture web actuelle).

`py_compile` OK sur les fichiers canoniques après suppression.

Backup pinné : `avant-suppression-code-mort-201`.

# Changelog — Issue #200

## Rapatrier socket.io et chess.js en local

- Téléchargé `socket.io.min.js` (v4.7.2) et `chess.min.js` (v0.10.3) dans
  `nicsoft/web/static/vendor/socket.io/` et `nicsoft/web/static/vendor/chess.js/`.
- `index.html` référence désormais `/static/vendor/socket.io/socket.io.min.js`
  et `/static/vendor/chess.js/chess.min.js` au lieu de cdnjs.cloudflare.com.
- Testé : démarrage serveur Flask OK, page servie sans requête vers cdnjs,
  handshake Socket.IO fonctionnel, fichiers vendor servis en HTTP 200.

## Issue #181 — Vérification version Python dans l'installeur NSIS (essai2)

- `installer-exe/alchess_setup.nsi` : nouvelle fonction `CheckPythonVersionWarning`, appelée juste après détection réussie de Python (SecPython, toutes stratégies : `py -0p`, PATH, scan des dossiers standards) et avant la création du venv. Avertit — sans bloquer — si le Python détecté est une pré-publication (suffixe `rc`/`a`/`b` dans la version complète, ex. `3.15.0rc1`) ou une version ancienne (< 3.10).
- Cas non couvert par la comparaison existante (`CompareVersionToMinimum`) : elle ne compare que "X.Y" (ex. "3.15") au minimum requis (3.12), donc une RC comme `3.15.0rc1` passait la vérification sans que son suffixe soit examiné — cause du bug constaté (Python 3.15rc1 : `hidapi` ne compile pas faute de MSVC, aucun wheel précompilé n'existant pour une RC).
- Ajout de `ExtractFullVersionFromPythonOutput` (garde le suffixe complet de la version, contrairement à `ExtractVersionFromPythonOutput` qui tronque à "X.Y") et de la macro `StrFunc` `StrStr` (recherche de sous-chaîne).
- `MessageBox MB_OKCANCEL` non bloquante : affiche la version détectée, recommande Python 3.12/3.13 stable avec lien vers python.org, l'utilisateur peut continuer quand même (IDCANCEL → Abort propre).
- Non appelée après `InstallPython312NSIS` (installation via winget) : cette voie installe toujours une 3.12 stable, jamais concernée.
- Vérifié : `makensis -V4 alchess_setup.nsi` compile sans erreur (exit 0).

## Issue #170 — llm_explainer : préciser le joueur et interdire les coups futurs dans le prompt

- `nicsoft/modes/opening_explorer/llm_explainer.py` : `_build_user_prompt` identifie désormais le camp qui vient de jouer (Blancs/Noirs, déduit du FEN) et l'inclut explicitement dans le prompt envoyé au LLM ("Les Blancs viennent de jouer : e4"). Ajout d'une consigne explicite interdisant de mentionner les coups futurs de l'adversaire, pour corriger le comportement où le LLM expliquait la réponse probable de l'adversaire au lieu du coup joué.
- Cache LLM vidé (`data/explorer_cache.json`) pour forcer la régénération des explications avec le nouveau prompt.
- Suite de l'issue #168.

# Changelog — issue #148

## Opening Explorer — flèches SVG illustrant les coups mentionnés par le LLM

- `nicsoft/modes/opening_explorer/llm_explainer.py` : prompt système enrichi
  (FR/EN/DE) pour demander au LLM d'ajouter une ligne `[FLECHES: e2-e4, ...]`
  (`[ARROWS: ...]` / `[PFEILE: ...]` selon la langue, même tag interne
  `FLECHES|ARROWS|PFEILE` accepté au parsing) ; ajout de `extract_arrows(text)`
  qui retire cette ligne et retourne la liste des flèches (2 à 4 max, cases
  validées a-h/1-8, from == to ignoré). `get_explanation()` et
  `get_chat_response()` retournent désormais `(texte, flèches)` ; le cache
  disque stocke `{"text": ..., "arrows": [...]}` (rétrocompatible avec les
  anciennes entrées `str`).
- `nicsoft/web/server.py` : `explorer_explanation` et `explorer_chat_response`
  émettent désormais `{"text": ..., "arrows": [["e2","e4"], ...]}`.
- `nicsoft/web/templates/index.html` : `#expl-board` enveloppé dans un
  conteneur `position:relative` avec un `<svg id="expl-arrows">` en
  surimpression (`pointer-events:none`) et un marker `#expl-arrowhead`.
- `nicsoft/web/static/app.js` : `explDrawArrows(arrows)` dessine des flèches
  rouges semi-transparentes (`rgba(232,69,96,0.75)`, épaisseur ~8% d'une
  case) entre les centres des cases, en tenant compte de `_explFlipped`.
  `explClearArrows()` vide le SVG (en conservant `<defs>`) ; appelé dans
  `explorer_state`, `explLoad()` et avant chaque nouveau dessin.

py_compile OK sur `llm_explainer.py` et `server.py` ; `node --check` OK sur
`app.js`.

