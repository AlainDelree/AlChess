# Changelog — Issue #293

## Retrait de `.gitmodules` : cinq sous-modules vestigiaux absents du dépôt

`.gitmodules` déclarait cinq sous-modules hérités du projet NicLink
d'origine (`src/thirdparty/libusb-cmake`, `src/thirdparty/pybind11`,
`src/thirdparty/hidapi-git`, `standalone_chessclock`,
`src/thirdparty/chessnutair`) : aucune entrée correspondante n'existait
dans l'index git (aucun sous-module réellement suivi), aucun des chemins
n'existait dans l'arbre, et rien (code, scripts, installateur Windows,
workflow GitHub, documentation) ne s'appuyait dessus. Un `git submodule
update --init` sur un clone neuf échouait à cause de ces entrées fantômes.

- **`.gitmodules`** : supprimé.
- **`CONTEXTE.md`** : section « Moteurs » corrigée — `engines/rodent-iv/`
  et `engines/rodent-iv-win/` sont décrits comme des dossiers ignorés par
  git (binaire compilé/copié localement) et non plus comme un sous-module,
  conformément à l'issue #260.
- **`nicsoft/tests/test_no_orphan_gitmodules.py`** (nouveau) : garde sans
  réseau — si `.gitmodules` existe, chaque chemin déclaré doit correspondre
  à une entrée de sous-module réellement suivie par l'index git (mode
  `160000`), sinon le test échoue ; s'ignore proprement si `.gitmodules`
  est absent (cas normal depuis cette issue) ou si `git` n'est pas
  disponible.
- Non touchés, conformément au périmètre de l'issue : `nicsoft/niclink/`
  (paquet Python du pilote USB, sans rapport avec ces sous-modules), les
  fichiers de règle udev (`99-chessnutair.rules.example` et
  `scripts/detect_chessnut.py`, qui désignent le pilote USB Chessnut et
  non un sous-module), le dossier `engines/`, `.gitignore` et `.audit.json`.
- Aucune référence à un chantier « `git submodule update --init` échoue
  sur clone frais » trouvée dans `CONTEXTE.md` ni ailleurs — rien à
  retirer sur ce point.
- Suite de tests complète (hors `hardware`) : 375 passés, 74 ignorés.
