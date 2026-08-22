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
