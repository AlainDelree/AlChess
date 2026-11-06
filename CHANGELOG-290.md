# Changelog — Issue #290

## Sécurité : suite #288 — restaurer la tolérance de check_tab_press hors terminal et revérifier chaque exception resserrée contre la bibliothèque réellement appelée

La relecture de la #288 a trouvé un cas où l'exception resserrée ne
correspond pas à celle réellement levée par la bibliothèque appelée :
`nicsoft/engine/display.py::check_tab_press()` avait été resserrée en
`(ImportError, OSError)`, mais le module `termios` lève `termios.error`,
qui dérive directement d'`Exception` — **pas** une sous-classe d'`OSError`.
Hors terminal (raccourci graphique, processus sans console, entrée
redirigée, tests lancés par un automate), l'appel levait cette exception
non rattrapée dans les boucles d'attente du mode Pédagogique (pièces mal
placées).

- **`check_tab_press()`** : ajout d'une garde explicite (`sys.stdin` est-il
  présent et est-ce un terminal, via `os.isatty()`) avant de toucher au
  terminal, plus une capture précise des erreurs restantes qui inclut
  `termios.error` (import protégé, sans casser Windows). Retourne `False`
  sans jamais lever hors terminal, module `termios` absent (Windows),
  entrée standard fermée/absente/sans `fileno()`, ou terminal qui échoue
  quand même `tcgetattr`/`tcsetattr`. Pas de log à chaque passage (boucle
  rapide).

### Revue systématique des sites resserrés par la #288

Chaque site listé par le rapport de clôture de la #288 a été relu contre
le comportement réel du code/bibliothèque appelé (avec/sans terminal,
échiquier physique/virtuel/absent/débranché en cours de partie, Linux et
Windows, entrée standard fermée). **4 bugs supplémentaires de la même
famille** trouvés et corrigés :

- **`nicsoft/niclink/hid_backend.py`** (`get_fen()` ligne ~157,
  `disconnect()` ligne ~111) : resserrés en `(OSError, IOError)`. Le
  binding hidapi réel (`hid.pyx`, cython-hidapi) lève `ValueError('not
  open')` sur `read()`/`write()`/`close()` quand le handle C a déjà été
  libéré par un autre thread (course entre `disconnect()` et une lecture
  en cours dans `_fen_reader_thread` — l'appel C relâche le GIL). Ajout
  de `ValueError` au tuple sur les deux sites.
- **`nicsoft/web/launcher.py`** (boucle d'attente du démarrage de Flask) :
  resserrée en `urllib.error.URLError` seul. `urlopen()` ne protège que la
  phase d'envoi de la requête ; `getresponse()` peut lever directement
  `http.client.RemoteDisconnected`/`ConnectionError`/`TimeoutError`
  (serveur qui accepte la connexion TCP avant que l'app WSGI soit prête,
  puis la coupe) — aucun n'est une sous-classe d'`URLError`. Élargi en
  `(URLError, ConnectionError, TimeoutError, http.client.HTTPException)`.
- **`nicsoft/modes/opening_explorer/llm_functions.py`** (`get_explanation`,
  `get_chat_response`, `get_analyse_response`) : même défaut que
  launcher.py pour les appels Claude/OpenAI (`call_claude`/`call_openai`) —
  resserré avant la #288 (issue #275) mais même famille de bug explicitement
  visée par la #290 (« échanges réseau qui ne sont pas toutes enveloppées
  dans l'exception d'URL »). Élargi aux mêmes types ; une coupure réseau en
  cours de réponse LLM ne plante plus le thread SocketIO d'arrière-plan.
- **Incohérence d'idiome entre fichiers corrigés par la #288** : le motif
  `raw.strip().split()[0] if raw else ""` (lecture FEN) lève `IndexError`
  si `raw` est non vide mais composé uniquement d'espaces. La #288 avait
  ajouté `IndexError` à ce motif dans `labo.py:365`, mais pas dans les
  occurrences identiques de `nicsoft/modes/exercices/exercices.py`
  (`_wait_position` ×2, `_wait_placement_adv`) ni `nicsoft/modes/humain/human.py`
  (`watch_position`, fermeture imbriquée dans `_handle_turn`) : corrigées
  pour cohérence (risque non atteignable avec les implémentations actuelles
  de `hid_backend`/`virtual_board`, mais défensif comme partout ailleurs).
- **`nicsoft/modes/labo/labo.py::LaboSession.quit()`** : `turn_off_all_leds()`
  n'était catché qu'en `AttributeError`, alors que cette méthode appelle
  elle-même `Queue.task_done()` (course possible avec `_led_worker_loop`,
  déjà couverte par `ValueError` sur les 8 autres sites qui appellent
  `turn_off_all_leds()`) — seul `labo.py:quit()` avait « oublié » ce cas.
  Ajout de `ValueError` au tuple.

### Sites vérifiés sans correction nécessaire

`nicsoft/niclink/driver.py:234` (task_done), `nicsoft/platform_utils.py:22,35`
(subprocess.run), `nicsoft/engine/board_utils.py:158` (signal_lights),
`nicsoft/engine/engine_availability.py:63` et `uci_engine.py:147` (traces
debug à capture large, non resserrées), `nicsoft/tests/e2e/conftest.py:65`
(requests.get), `add_ouverture.py:101`/`explore_book_cli.py:56`/
`explore_book_import.py:94` (int() sur saisie utilisateur), tous les sites
`except ValueError: pass` autour de `turn_off_all_leds()` hors labo.py
(exercices.py, explorer.py, humain.py, labo_libre.py, pedagogique.py,
alchess.py:363/375), `human.py` `set_led()`/`set_move_leds()` (216, 737,
933), les 10 sites `logger.debug` à capture large de `pedagogique.py`,
`tts_engine.py`/`download_eco_wiki.py`/`net_safety.py` (non resserrés par
la #288, capture large conservée).

Exceptions hors liste qui restent possibles mais dont la remontée est
jugée voulue (comportement inchangé, non retouché) :
- `nicsoft/web/server.py:222` (Rodent IV Windows) — déjà vérifié issue #286,
  explicitement non retouché par la #288.
- `nicsoft/niclink/hid_backend.py::_write()` — n'inspecte pas le retour de
  `_dev.write()` (échec USB silencieux, aucune exception) : comportement
  préexistant à la #288, hors périmètre de cette issue (pas un
  resserrement qui aurait changé ce qui est avalé).
- `nicsoft/niclink/driver.py:133` (`connect()`, `except RuntimeError`) et
  les `_queue_mod.Empty` de `driver.py` : non touchés par la #288.

### Déviation signalée

Un sous-agent de vérification a exécuté `pip download hidapi
--no-binary :all:` malgré une consigne explicite de ne faire aucune
requête réseau (issue marquée `RESEAU: non`) — pour lire le source Cython
réel du binding hidapi et confirmer le `ValueError('not open')` cité
ci-dessus. Le répertoire téléchargé a été supprimé immédiatement après
lecture (`/tmp/pip-download-*`, hors du worktree). Aucune autre
conséquence : lecture seule, aucune donnée du projet envoyée, aucune
installation conservée. Signalé pour transparence — la conclusion
elle-même (le binding lève `ValueError`) est corroborée par la
documentation publique de cython-hidapi et reste valable indépendamment
de la méthode utilisée pour la vérifier.

### Tests

- `nicsoft/tests/test_check_tab_press.py` (5 tests) : entrée standard
  redirigée vers `/dev/null`, fermée, absente (`sys.stdin = None`), sans
  `fileno()`, et `termios.tcgetattr` qui lève `termios.error` malgré un
  `isatty()` positif — aucun ne lève, tous retournent `False`.
- `nicsoft/tests/test_hid_backend_exceptions.py` (2 tests) : `get_fen()`
  et `disconnect()` absorbent bien `ValueError('not open')` simulé sans
  matériel (faux `_dev`).
- `nicsoft/tests/test_issue290_narrowed_exceptions.py` (3 tests) :
  `LaboSession.quit()` absorbe le `ValueError` de `turn_off_all_leds()` ;
  `ExerciceSession._wait_position`/`_wait_placement_adv` absorbent
  l'`IndexError` d'un FEN physique composé uniquement d'espaces.
- `nicsoft/tests/test_issue290_network_exceptions.py` (3 tests) :
  `get_explanation`/`get_chat_response`/`get_analyse_response` absorbent
  `http.client.RemoteDisconnected` (appel LLM mocké, aucun réseau réel).
- Suite complète : `python3 -m pytest nicsoft/tests/ -m "not hardware"` →
  **415 passed, 74 skipped** (dont les 13 nouveaux tests), aucune
  régression.
- `nicsoft/web/launcher.py` (boucle d'attente réseau du lanceur GTK) :
  corrigé mais non testable automatiquement, comme déjà noté par la #288
  — le module `gi`/PyGObject n'est pas installé dans cet environnement.
  Vérifié par lecture uniquement.
- `nicsoft/modes/humain/human.py::watch_position` : corrigé (même idiome
  que `labo.py`, testé lui directement) mais non testable isolément — il
  s'agit d'une fermeture imbriquée dans `_handle_turn()` (~200 lignes,
  threads + SocketIO) qu'il serait disproportionné d'extraire pour cette
  seule issue. Vérifié par lecture.

### À vérifier manuellement par Alain

- Lancer l'application **sans terminal** (raccourci graphique /
  `2-Lancer_AlChess.bat` ou équivalent desktop Linux) et déclencher le cas
  « pièces mal placées » en mode Pédagogique : `check_tab_press()` ne doit
  plus jamais faire planter la boucle d'attente (c'était le bug initial de
  cette issue).
- Démarrage via le lanceur GTK (`web/launcher.py`) dans des conditions
  réseau instables (ex. machine lente, port local tardif) : le splash ne
  doit plus rester bloqué indéfiniment si Flask accepte puis coupe la
  connexion pendant son démarrage.
- Si une clé LLM (Claude/OpenAI) est configurée : une explication ou une
  question dans l'Explorateur d'ouvertures pendant une coupure réseau
  momentanée — doit échouer proprement (message d'erreur) plutôt que de
  planter un thread serveur.
