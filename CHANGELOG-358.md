# Changelog — issue #358

## Diagnostic de sys.exit(0) dans human.py, fin du tri de historique_bugs.md, section Lichess dans SPECIFICATIONS.md

### Diagnostic BUG-011 (human.py)

`sys.exit(0)` en `nicsoft/modes/humain/human.py:1085` (`GameWeb._traiter_abandon()`, branche `back_menu`) est **sans danger** dans la configuration réelle (`async_mode="threading"`). Preuve : `GameWeb.start()` appelle `self.run()` en synchrone (pas un vrai `Thread.start()`) — toute la boucle de jeu s'exécute dans le thread créé par `launch_humain()` (`core/game_manager_modes/humain.py`, `t = threading.Thread(target=_run_humain, ...)`). Ce `SystemExit` est systématiquement capté par `except SystemExit as e:` (`core/game_manager_modes/humain.py:89`) qui l'absorbe sans le relancer (le test `"board connection error" in str(e)` est faux pour `str(SystemExit(0)) == "0"`, mais l'exception reste consommée) — `_run_humain` termine normalement, le thread `t` se termine normalement, `t.join()` revient normalement. Vérifié par une expérience isolée hors dépôt (`/tmp`, aucun fichier du dépôt touché) : un `sys.exit(0)` profond, catché par un `except SystemExit` même partiellement inutile, ne tue jamais le thread appelant ni le process — et, filet de sécurité supplémentaire, `threading.excepthook` (Python ≥3.8) ignore silencieusement tout `SystemExit` non capté levé hors thread principal. Seule la classe CLI `Game` (lignes 260/591, script autonome `python -m nicsoft.modes.humain.human`, jamais importée par le serveur web — confirmé par recherche d'imports) utilise `sys.exit()` pour terminer réellement le process, ce qui y est le comportement voulu.

Point de fragilité signalé pour une issue séparée (non corrigé ici, consigne de l'issue) : ce `sys.exit(0)` n'est sans danger que par coïncidence — il dépend d'un `except SystemExit` dont le rôle premier est de détecter une erreur de connexion échiquier, pas de servir de garde-fou pour le retour menu. `modes/pedagogique/pedagogique.py` a déjà été corrigé après un incident réel similaire (BUG-011 d'origine) en remplaçant son propre `sys.exit(0)` par une exception dédiée `BackMenuExit`, explicitement catchée dans `_run_pedagogique`. Suggestion : aligner `human.py` sur le même pattern (remplacer le `sys.exit(0)` de `_traiter_abandon()` par une exception dédiée, ou au moins par un simple `return`/flag propagé), pour ne plus dépendre d'un `except` à vocation différente. Aucun test actuel n'exerce ce chemin précis (thread réel + `back_menu` + assertion de survie du process) — à envisager si l'issue séparée corrige le code.

### docs/contexte/historique_bugs.md — supprimé

Fichier entièrement vidé puis supprimé (`git rm`) :
- **BUG-011** : conclusion « sans danger » ci-dessus → récit retiré, aucune règle ajoutée (le correctif suggéré reste à la charge d'une issue séparée, pas d'un invariant à documenter ici).
- **Lot 2** (18 entrées, hash de commit) : chacune revérifiée dans le code et/ou les tests actuels — toutes confirmées toujours corrigées. Les pièges génériques encore valables aujourd'hui ont été promus en règles dans les fichiers de domaine (voir ci-dessous) ; le reste (corrections ponctuelles sans piège généralisable : doublon UI, notation en passant, prints debug, pièces clouées, handlers manquants, etc.) a simplement vu son récit retiré, l'historique détaillé restant disponible via `CHANGELOG.md`/git.

Références mises à jour en conséquence : `CONTEXTE.md` (ligne d'index retirée), `CLAUDE.md` (ligne de tableau retirée), `TESTS.md` (consigne « nouveau bug trouvé » réorientée vers les fichiers de domaine), `SPECIFICATIONS.md` §11 (ligne de tableau retirée).

### docs/contexte/architecture.md

Règle « Retour au menu » enrichie de deux pièges tirés du lot 2 encore généralisables : ne jamais écraser un choix persistant de l'utilisateur par une valeur par défaut codée en dur au retour menu ; ne jamais réinitialiser un état de session JS dans un handler `socket.on("connect")` (il tourne à chaque reconnexion, pas qu'au chargement de page). Nouvelle règle : toujours émettre l'évènement UI avant toute I/O disque bloquante.

### docs/contexte/echiquier_usb_led.md

Nouvelle règle (2 pièges du lot 2) : verrou non bloquant obligatoire pour toute fonction de détection/connexion matérielle appelable depuis plusieurs threads ; revérifier `_app_state` après tout `sleep` précédant une action matérielle.

### SPECIFICATIONS.md

Nouvelle section §5.8 « Lichess » (point de vue produit, fondée sur `docs/contexte/lichess.md` et le code réel de `core/game_manager_modes/lichess.py`/`modes/lichess/`) : adversaire IA ou humain, classée ou amicale, cadences proposées (10+0 à 90+30), échiquier physique requis, aucune aide pendant la partie, abandon/nulle, cote affichée en fin de partie classée, PGN rangée par cadence, problèmes Lichess avec cote. Aucune autre section modifiée.

### Suite de tests

`python -m pytest nicsoft/tests -m "not hardware"` : verte avant et après ces modifications (aucun fichier Python touché). Expérience de diagnostic faite exclusivement dans `/tmp`, hors dépôt.
