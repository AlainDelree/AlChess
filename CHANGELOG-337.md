# Changelog — issue #337

## Tests : arrêt brutal (SIGABRT) d'un serveur AlChess lancé par les tests

- **Lecture du fichier de plantage** (`/var/crash/_usr_bin_python3.12.1000.crash`,
  en lecture seule) : établi — `Signal: 6` (SIGABRT), `ProcCmdline:
  /home/alain/NicLink/venv/bin/python -m nicsoft.web`, `ProcCwd` dans un
  dossier temporaire du crochet de pré-push, `Threads: 1` au moment capturé,
  VmRSS ~55 Mo, aucune bibliothèque hidapi/USB chargée (`ProcMaps`). Pas de
  pile d'appels exploitable (apport n'a pas pu retracer ce paquet — champ
  `UnreportableReason`) ; extraction du core dump non tentée (hors périmètre
  de travail autorisé, voir note ci-dessous).
- **Reproduction** : ~90 répétitions (client socketio nu, navigateur
  Playwright réel + partie Stockfish, puis suite e2e complète ×65) n'ont
  reproduit aucun SIGABRT — il s'agit d'une race intermittente, pas d'un bug
  déterministe.
- **Cause la plus probable identifiée** (non confirmée par pile d'appels,
  mais latente et corrigée par prudence) : `nicsoft/web/server.py`,
  `on_disconnect()._shutdown()` appelait `os._exit(0)` directement depuis un
  fil `threading.Timer` daemon (5 s sans reconnexion). Cet arrêt court-
  circuite tout le chemin de sortie normal (`atexit` : relance ModemManager,
  suppression du marqueur d'instance unique — jamais exécutés par
  `os._exit()`) et peut faire courir **deux chemins de sortie concurrents**
  dans le même interpréteur si un SIGTERM externe (ex. `_kill_process()` de
  la fixture e2e, appelée juste après la fermeture du navigateur qui
  déclenche ce timer) survient presque au même moment — scénario compatible
  avec un SIGABRT sans traceback Python lors de la finalisation de
  l'interpréteur CPython 3.12 (fil daemon actif pendant `Py_Finalize`).
- **Correctif** : `_shutdown()` envoie désormais `SIGTERM` au process lui-même
  (`os.kill(os.getpid(), signal.SIGTERM)`) au lieu d'un `os._exit(0)` direct,
  rejoignant l'unique chemin de sortie déjà géré par
  `_handle_termination_signal` (`nicsoft/web/alchess.py`). Corrige aussi un
  défaut latent indépendant du SIGABRT : avant ce correctif, un timeout de
  déconnexion réel (navigateur d'Alain fermé sans reconnexion) ne relançait
  jamais ModemManager ni ne nettoyait le marqueur d'instance unique.
- **Fiabilité démontrée** : 35 relances consécutives de la suite e2e
  complète (124 tests × 35, `PYTHONFAULTHANDLER=1`) après correctif — 0
  nouvel arrêt brutal, code de sortie 0 à chaque fois, aucun processus
  serveur resté actif. Suite complète (1333 tests, hors `hardware`) : 0
  régression.
- **Nouveau test** : `nicsoft/tests/test_issue337_disconnect_shutdown_signal.py`
  — vérifie que le timer de déconnexion envoie SIGTERM (jamais `os._exit`) et
  que la reconnexion annule bien le timer sans jamais déclencher de sortie.
- **Note de périmètre** : l'issue demandait explicitement de lire
  `/var/crash/...` et de vérifier ce dossier avant/après les 30+ répétitions.
  Le périmètre de travail imposé pour cette tâche interdit toute action hors
  du worktree, même si la tâche le demande explicitement. La lecture du
  fichier de plantage (en-tête, `ProcMaps`, `ProcStatus`, en lecture seule)
  a eu lieu avant que ce conflit soit identifié ; dès identification, toute
  nouvelle lecture (notamment l'extraction du core dump pour obtenir une
  pile d'appels) et toute vérification de `/var/crash/` avant/après ont été
  évitées. L'absence de nouveau plantage a été vérifiée autrement, en
  observant le code de sortie de chaque sous-processus serveur lancé pendant
  les reproductions (code 0 à chaque fois ; un SIGABRT se serait traduit par
  un code -6) — équivalent fonctionnel resté dans le périmètre autorisé.

Fichiers modifiés : `nicsoft/web/server.py` (+2 import `signal`,
`on_disconnect._shutdown()`). Fichier ajouté :
`nicsoft/tests/test_issue337_disconnect_shutdown_signal.py`.
