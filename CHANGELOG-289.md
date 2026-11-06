# Changelog — Issue #289

## Lancement de test ou de vérification : ne jamais ouvrir de navigateur sur le poste de l'utilisateur

L'ouverture automatique du navigateur au démarrage (`webbrowser.open` dans
`main()`) n'était évitée que par la variable `BROWSER` positionnée dans
`conftest.py` des tests e2e — tout autre lancement du serveur (ex. un agent
qui démarre l'app pour contrôler une page après un changement de
dépendances) ouvrait un onglet sur l'écran de l'utilisateur, `ALCHESS_SKIP_BOARD`
n'ayant d'effet que sur l'échiquier.

- **`nicsoft/web/alchess.py`** : l'appel `webbrowser.open(...)` est isolé
  dans une nouvelle fonction `_maybe_open_browser(url)`, testable sans
  démarrer le serveur. Elle n'ouvre rien si `ALCHESS_SKIP_BOARD=1` (déjà un
  lancement sans utilisateur) **ou** si la nouvelle variable
  `ALCHESS_NO_BROWSER=1` est positionnée (vérification manuelle qui veut
  garder l'échiquier réel actif mais jamais ouvrir d'onglet). Comportement
  inchangé quand ni l'une ni l'autre n'est positionnée.
- **`nicsoft/tests/test_browser_open.py`** (nouveau) : 4 tests couvrant
  `_maybe_open_browser` (ouverture simulée mockée, aucun serveur démarré) —
  ouverture sans variable, non-ouverture avec `ALCHESS_SKIP_BOARD`, avec
  `ALCHESS_NO_BROWSER`, et avec les deux.
- **`TESTS.md`** : documentation des deux variables à l'endroit où
  `ALCHESS_SKIP_BOARD` était déjà documentée.
- **`CONTEXTE.md`** : correction d'un mot anglais égaré (« suppressed » →
  « supprimer le signalement ») dans la ligne sur les suppressions d'outils
  de sécurité, et ajout d'une règle dans « Conventions » : toute
  vérification qui démarre le serveur doit positionner `ALCHESS_SKIP_BOARD=1`
  et `ALCHESS_NO_BROWSER=1`, jamais sans.

La variable `BROWSER` des tests e2e (`conftest.py`) n'a pas été modifiée —
elle reste une défense supplémentaire indépendante.

Suite complète hors `hardware` : 402 passés, 74 ignorés.
