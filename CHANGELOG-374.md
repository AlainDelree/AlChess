# Changelog — Issue #374

## Tests e2e : restauration du gestionnaire `lichess_resumable` dans test_issue333

Suite au rapport de clôture de l'issue #373 : `test_issue333_lichess_menu_banner_e2e.py` était le seul fichier, parmi les cinq suites e2e Lichess partageant la page de session, à détacher le vrai gestionnaire socket.io `lichess_resumable` sans jamais le restaurer — documenté à l'époque comme un choix délibéré laissé hors périmètre de #373.

### Correction

`nicsoft/tests/e2e/test_issue333_lichess_menu_banner_e2e.py` : ajout d'une fixture `scope="module", autouse=True` (`_detacher_lichess_resumable_reel`), identique à la convention adoptée par #373 pour `test_issue310/323/344_lichess_*_e2e.py` — détache une seule fois pour tout le module, restaure (`socket.on`) à la fin, même garde `if (!window...)` pour réutiliser une référence déjà laissée par un fichier antérieur n'ayant pas restauré. Le détachement inline, répété auparavant dans la fixture par-test `at_menu_resumable_ready`, est supprimé (déjà fait au niveau du module) ; cette fixture devient un simple alias de `at_menu`. Comportement des tests inchangé (gestionnaire toujours détaché pendant leur exécution).

`test_issue310_lichess_e2e.py`, `test_issue323_lichess_resume_e2e.py`, `test_issue344_lichess_rated_e2e.py` : mise à jour des docstrings/commentaires qui décrivaient `test_issue333_*` comme l'exception délibérée ne restaurant jamais — n'est plus le cas, la garde `if (!window...)` reste conservée à titre défensif (couvre un futur fichier qui omettrait de restaurer), pas pour ce cas précis.

### Vérification de la cohérence (point 2 de l'issue)

Les cinq fichiers (310, 323, 333, 344, 366) exécutés ensemble, dans l'ordre alphabétique par défaut, avec 333 en premier, et avec 333 en dernier : chaque module détache puis restaure correctement, sans détachement sauté ni gestionnaire posé en double, quel que soit l'ordre.

### Point 3 — autres états non restaurés

Aucun autre cas trouvé : `test_issue365_lichess_sans_echiquier_e2e.py` et `test_issue368_lichess_network_e2e.py` détachent/restaurent déjà `config_data` (et `lichess_resumable` pour 365) correctement à l'échelle du module. `test_issue366_puzzle_mode_autobascule_e2e.py` utilise ses propres variables suffixées (`...366`, indépendantes de la chaîne partagée 310/323/333/344) et restaure déjà correctement les deux gestionnaires qu'il détache, ainsi que `localStorage` (via `_reset_base`) à la fin de chaque test.

Observation mineure, non corrigée (hors périmètre de cette issue — pas de détachement sans restauration constaté) : `test_issue365_lichess_sans_echiquier_e2e.py::_detacher_lichess_resumable_reel` réutilise la même variable globale partagée `window.__realLichessResumableHandlers` que 310/323/333/344, mais sans la garde défensive `if (!window...)` avant de stasher. Sans conséquence actuelle (chaque fichier restaure désormais correctement avant que 365 ne s'exécute), mais plus fragile en cas de futur réordonnancement.

### Suite complète

`pytest nicsoft -m "not hardware"` : 1770 réussis, 86 ignorés — identique à la référence d'avant correction. Une défaillance intermittente pré-existante a été observée pendant l'investigation (`test_issue344_lichess_rated_e2e.py::test_case_classee_masquee_contre_ia` et, séparément, `test_issue366_puzzle_mode_autobascule_e2e.py::test_clic_manuel_echiquier_respecte_et_memorise`), reproduite à l'identique sur le code d'avant cette correction (plusieurs essais comparatifs) — non liée à ce correctif, non traitée ici.
