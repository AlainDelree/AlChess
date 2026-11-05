# CHANGELOG-267 (issue #267)

## Tests e2e : serveur lancé depuis le code testé, échiquier réel ignoré

- `nicsoft/tests/e2e/conftest.py` : le dossier de lancement du serveur de test (donc le code importé par `python -m nicsoft.web`) n'est plus le dépôt principal codé en dur (`~/NicLink`), mais déduit de l'emplacement de `conftest.py` (racine du dépôt ou du worktree où tourne pytest). Les tests valident donc le code sur lequel ils sont exécutés. Le Python reste celui du venv utilisateur (`~/NicLink/venv/bin/python`).
- `nicsoft/web/alchess.py` : nouvelle variable d'environnement `ALCHESS_SKIP_BOARD=1` qui désactive `_check_board_at_startup` (détection/connexion de l'échiquier USB réel au démarrage) et évite de lancer `_board_menu_watcher` ; absente, le comportement est inchangé. Positionnée uniquement dans l'environnement du serveur lancé par `conftest.py`.
- `data/` n'étant pas versionné, un worktree n'a pas les fichiers de référence réels (ECO `eco_*.tsv`, `eco_hierarchy.json`, livres d'ouvertures…) dont dépendent 3 tests de recherche ECO (`test_outils_exercices_e2e.py`). L'isolation complète via un dossier `ALCHESS_DIR` temporaire (point optionnel de l'issue) a été tentée puis abandonnée pour cette raison ; `ALCHESS_DIR` est positionnée vers le vrai dossier de données de l'utilisateur (`~/NicLink`) pour ces tests — seul le code vient du worktree, pas les données. Documenté dans `TESTS.md`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 119 passed, 10 skipped, lancée depuis le worktree, sans navigateur visible ni sollicitation de l'échiquier USB.
