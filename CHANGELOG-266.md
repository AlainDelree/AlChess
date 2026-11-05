# CHANGELOG-266 (issue #266)

## Retrait de l'outil de sauvegarde backup_manager

- Suppression de `nicsoft/utils/backup_manager.py` et de `nicsoft/utils/Lancer et autre outil Backup.txt`.
- Retrait de toutes les références (commandes, consignes de backup épinglé) dans `CLAUDE.md`, `CONTEXTE.md`, `SPECIFICATIONS.md`, `TESTS.md`, `ETAT_PROJET.md` et `INSTALLATION/CONFIGURATION_SYSTEME.md`.
- Là où la consigne de backup épinglé disparaît, remplacement par un rappel explicite : la protection du travail repose sur git (commits ciblés, retour arrière par git, push fait par Alain après revue).
- `CONTEXTE.md` : suppression de l'affirmation périmée selon laquelle CCL travaille exclusivement dans `~/NicLink` (devenu faux depuis le passage aux worktrees isolés par issue).
- Aucun code Python n'importait cet outil ; suite de tests (`pytest -m "not hardware"`) : 96 passed, 4 skipped.
