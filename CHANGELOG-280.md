# Changelog — Issue #280

## Suppression de cinq fichiers morts découverts par les tests de garde ARC-001

Suite de l'élargissement de la découverte ARC-001 à tous les fichiers de
`core`, `modes`, `niclink`, `utils` et `engine` (issue #272), qui avait mis
en évidence cinq fichiers cassés et jamais appelés, documentés comme
exclusions avec test miroir plutôt que supprimés sur le moment.

- Vérification à jour par recherche dans tout le dépôt (code, scripts,
  packaging, documentation, hors changelogs) : aucune référence réelle à
  l'un des cinq fichiers (seules les occurrences de `light_board` sont le
  nom d'un paramètre dans `driver.py`/`virtual_board.py`, sans rapport).
- **Fichiers supprimés** :
  - `nicsoft/utils/light_board.py`
  - `nicsoft/utils/turn_out_all_lights.py`
  - `nicsoft/modes/exercices/__main__.py`
  - `nicsoft/modes/labo/__main__.py`
  - `nicsoft/modes/retranscription/__main__.py`
- `nicsoft/tests/test_no_web_import.py` : retrait de
  `MODULES_NON_IMPORTABLES_SEULS` (les 5 exclusions) et de son test miroir
  `test_modules_non_importables_restent_documentes` ; tous les modules
  découverts passent désormais par les tests normaux.
- `nicsoft/tests/test_no_undefined_names.py` : retrait de l'exclusion
  `nicsoft/utils/light_board.py` (`FICHIERS_AVEC_NOMS_NON_DEFINIS_CONNUS`)
  et de son test miroir `test_fichiers_exclus_restent_documentes`.
- `.audit.json` non touché, comme demandé.
- Suite complète (`pytest -m "not hardware"`) : 293 passed, 60 skipped,
  0 failed — même niveau de protection, aucun fichier supplémentaire
  ignoré.
