# Changelog — Issue #320

# Issue #320 — Une seule instance du serveur AlChess à la fois : la nouvelle remplace l'ancienne, sauf si une partie y est en cours

## Contexte

Le 13 novembre 2026, Alain a constaté que relancer AlChess alors qu'une instance précédente tournait déjà laissait **deux serveurs actifs en même temps**, sans aucun avertissement — risqué pour l'accès USB (un seul accès ouvert à la fois, règle de projet) et pour la lisibilité des journaux (les deux écrivent dans le même fichier). Un lien de causalité avec les échecs d'ouverture récents (« aucun paquet de position lu », #319) a été évoqué dans la tâche comme hypothèse à vérifier, pas à supposer — **non établi** par ce travail : aucune preuve dans les journaux existants ne montre deux instances actives au moment de ces échecs, et rien dans l'architecture ne permettait jusqu'ici de le confirmer ou de l'infirmer après coup (c'est justement une partie du problème que corrige ce correctif : désormais, chaque ligne de journal porte le PID et le port de l'instance qui l'a écrite — voir §4).

## 1. Méthode retenue

**Marqueur d'instance** (`DATA_DIR/server_instance.json`, donc `ALCHESS_DIR` en test) : `{"pid": ..., "port": ..., "started_at": ...}`, écrit par `write_marker()` au démarrage (écriture atomique — fichier temporaire puis renommage), supprimé par `remove_marker()` à l'arrêt propre (uniquement s'il désigne encore le PID appelant — une instance qui s'arrête en retard n'efface jamais le marqueur d'une instance plus récente qui l'aurait déjà remplacée).

**Reconnaissance d'un processus AlChess** (jamais par le seul nom du programme — `python`/`python3` ne prouve rien) : le PID du marqueur doit être vivant (`os.kill(pid, 0)` sur Linux, `tasklist /FI "PID eq N"` sur Windows) **ET** sa ligne de commande doit contenir `nicsoft.web`/`nicsoft/web` (lue dans `/proc/<pid>/cmdline` sur Linux, via `wmic process where ProcessId=N get CommandLine` sur Windows — non testé, voir §5). Un PID réutilisé par un autre programme échoue ce second test et le marqueur est traité comme périmé : ignoré, jamais touché.

**Reconnaissance d'une partie en cours** : requête HTTP locale à l'ancienne instance, nouvelle route `GET /instance_status` (`nicsoft/web/server.py`, protégée par `_require_allowed_host()` comme les autres routes de lecture sensibles) qui renvoie `{"pid", "port", "state"}` — `state` est l'`_app_state` courant de cette instance, **pas** une relecture du marqueur (qui pourrait dater d'avant le dernier changement d'état). Préféré à une simple lecture de fichier : l'état vivant est la seule source fiable de "une partie tourne-t-elle là, maintenant". `BUSY_STATES` (`single_instance.py`) retient les états correspondant à une vraie partie, tous modes de jeu confondus (Lichess compris) — `connecting`, `playing`, `paused`, `position_initiale`, `lichess_wait_first_move`, `retrans_playing`, `exercice_running` — et exclut délibérément les écrans de menu/config/sélection et les outils d'analyse libre (`labo`, `opening_explorer`), qui ne sont pas "une partie" au sens de la tâche. Si la requête échoue (pas de réponse, timeout, instance en train de démarrer/planter) : **par précaution, on n'y touche pas** et on refuse de démarrer, plutôt que de risquer d'interrompre une partie dont l'état n'a pas pu être confirmé.

**Arrêt de l'ancienne instance inactive** : SIGTERM par son PID exact (le même signal que `_handle_termination_signal` sait déjà gérer proprement — relance de ModemManager puis sortie, ce qui déclenche ses propres callbacks `atexit`, dont la suppression de son marqueur), attente jusqu'à 5s par sondage de `os.kill(pid, 0)`, SIGKILL par ce même PID seulement en dernier recours. Sous Windows : `taskkill /PID N` puis `taskkill /PID N /F` (jamais `/IM`). Le fait d'attendre la confirmation de sortie du processus (pas un simple délai fixe) garantit que l'échiquier USB est déjà libéré par le noyau avant que la nouvelle instance ne démarre.

## 2. Intégration — tous les lanceurs

Le point d'entrée unique de tous les lanceurs (`start_alchess.sh`, `start_alchess.ps1`, `2-Lancer_AlChess.bat`, `nicsoft/web/launcher.py`) est `python -m nicsoft.web` → `nicsoft/web/alchess.py::main()`. La vérification (`single_instance.resolve_startup()`) y est appelée en tout premier, avant tout effet de bord (arrêt de ModemManager, recherche de port libre) : si une partie est en cours ailleurs, le message « Une partie est en cours dans l'instance déjà lancée, port N. » est affiché (`print`, puis journalisé) et le programme quitte sans avoir rien démarré ni touché à l'ancienne instance. Aucune commande nommée « chess » n'existe dans ce projet (vérifié : aucun `console_scripts` dans `nicsoft/pyproject.toml`, aucun fichier portant ce nom) — un seul point d'entrée Python, donc un seul endroit à corriger pour couvrir tous les lanceurs, Windows compris pour la partie "point de départ du contrôle". La partie spécifiquement Windows de la détection/arrêt de processus (`tasklist`/`wmic`/`taskkill`) est écrite mais **non testée** faute de machine Windows dans ce périmètre (voir §5).

## 3. Journal et console

`main()` affiche et journalise désormais `[NicLink] PID <pid> — port <port>` dès que le port est choisi, avant le démarrage du serveur — permet de rattacher toute ligne ultérieure du même fichier `niclink.log` à l'instance qui l'a écrite.

## 4. Fichiers modifiés

- **`nicsoft/web/single_instance.py`** (nouveau) : toute la logique — marqueur, détection PID+cmdline, requête d'état locale, arrêt par PID, décision `resolve_startup()`.
- **`nicsoft/web/server.py`** : nouvelle route `GET /instance_status` (juste après `/debug/mode`), protégée par `_require_allowed_host()`, aucun secret exposé.
- **`nicsoft/web/alchess.py`** : `main()` appelle `single_instance.resolve_startup()` en premier ; écrit le marqueur (`write_marker`) et enregistre sa suppression à la sortie (`atexit.register(single_instance.remove_marker, pid)`) une fois le port choisi ; affiche/journalise PID+port. Import de `datetime` déplacé en tête de module (déjà utilisé localement dans `_setup_logging()`, maintenant aussi dans `main()`).
- **`nicsoft/tests/test_issue320_single_instance.py`** (nouveau, 20 tests).
- **`CONTEXTE.md`** : section courante mise à jour.

## 5. Tests

**Sans matériel** (`ALCHESS_SKIP_BOARD=1`), sans navigateur (`ALCHESS_NO_BROWSER=1`/`BROWSER=/bin/true`), `DATA_DIR` isolé (tmp_path, jamais le dossier réel de l'utilisateur), **aucun arrêt par nom de programme** — uniquement par PID exact.

- 17 tests unitaires sur `single_instance.py`, avec de **faux processus lancés par les tests eux-mêmes** (simples boucles `time.sleep`, jamais un vrai serveur AlChess) : aucune ancienne instance, marqueur périmé (processus mort), PID réutilisé par un programme étranger (vérifié non touché), ancienne instance inactive remplacée (vérifié arrêtée), ancienne instance en partie refusée pour chacun des 7 `BUSY_STATES` (vérifiée non touchée), état de l'ancienne instance impossible à confirmer → refus par précaution, écriture/suppression du marqueur (y compris non-suppression si le PID a changé entre-temps), reconnaissance par ligne de commande (positive et négative).
- 2 tests sur la route `/instance_status` (client de test Flask, même pattern que `test_issue304_security.py`) : refus si `Host` étranger, contenu (pid/port/état) sinon.
- **1 test d'intégration réel** (`@pytest.mark.slow`), seul test de ce fichier à lancer de vrais sous-processus `python -m nicsoft.web` (toujours arrêtés par leur PID exact en nettoyage) : une première instance démarre et reste au menu, une seconde démarre dans le même `ALCHESS_DIR` isolé et doit la remplacer — vérifié par la sortie propre (code 0) de la première instance, confirmant que le marqueur, la route HTTP et l'arrêt par PID fonctionnent ensemble, pas seulement en isolation. Exécuté avec succès (voir ci-dessous).
- Suite complète (hors `nicsoft/tests/e2e`, navigateur) : **896 passés, 80 ignorés** (tests matériel), aucune régression.

**Non testé, dans ce périmètre** :
- Le chemin Windows (`tasklist`/`wmic`/`taskkill`) — aucune machine Windows disponible ; code écrit par analogie avec les commandes déjà utilisées ailleurs dans le projet (aucune n'existait pour ce cas précis), à vérifier par Alain lors d'un prochain lancement Windows.
- Le scénario "deuxième instance refusée parce qu'une vraie partie Lichess/pédagogique tourne" avec de **vrais** sous-processus serveur (nécessiterait de faire avancer un vrai mode de jeu jusqu'à `playing` sans board ni jeton Lichess réel, hors de portée raisonnable d'un test automatisé) — validé à la place par 7 tests unitaires paramétrés sur `resolve_startup()` (la même fonction appelée par `alchess.py::main()`), avec l'étape de requête HTTP simulée (`monkeypatch` de `_query_state`) et un vrai faux-processus pour la partie PID/cmdline.
- Dossier `nicsoft/tests/e2e` (Playwright) : non exécuté — cette tâche n'a aucune surface frontend/JS (pas de changement HTML/JS), donc rien à y couvrir ; la suite existante n'a pas été relancée pour ce motif (hors périmètre de la tâche, aucune modification de ce côté).
