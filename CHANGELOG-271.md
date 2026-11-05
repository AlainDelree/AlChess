# Changelog — Issue #271

## Exercices : l'erreur "livre introuvable" reste affichée jusqu'à une action de l'utilisateur

Suite de #270. Le message d'erreur (livre Polyglot introuvable) était bien
émis mais `ExerciceSession.run()` terminait aussitôt après (`return`
immédiat) : le lanceur d'exercice (`game_manager._run_exercice`) voyait
alors la session se terminer et exécutait son nettoyage normal de fin
d'exercice, qui renvoie aussitôt la liste des ouvertures — l'écran d'erreur
disparaissait donc en moins d'une seconde, le rendant inutilisable en
pratique.

- `nicsoft/modes/exercices/exercices.py` (`ExerciceSession.run()`) : le cas
  « livre manquant » affiche désormais la position de départ de l'exercice
  demandé (`self._send_position()` — plus l'échiquier de l'exercice
  précédent) puis attend une action utilisateur via `_wait_action_end()`,
  exactement comme à la fin normale d'une ligne (mêmes actions possibles :
  retour au menu, choisir une autre ouverture, recommencer). Sur
  « recommencer », l'erreur est simplement réaffichée (le livre est
  toujours manquant) sans relancer `_restart()` ni repasser par la boucle
  de jeu normale — pas de boucle infinie (bloqué sur l'action utilisateur)
  ni de nouveau log (le log d'absence du livre reste unique, à la
  construction de la session). Seule la méthode `run()` a été modifiée ;
  le nettoyage de fin de session dans `game_manager._run_exercice` est
  inchangé, et le mécanisme d'attente/actions (`_wait_action_end`) est
  celui déjà utilisé pour la fin de ligne théorique normale.
- Cas inchangés vérifiés : livre présent et cas « pièces mal placées »
  (`exercice_sync_error` hors livre manquant).
- `nicsoft/tests/test_exercices_book_missing.py` : test existant mis à jour
  (fournit désormais une action de retour pour débloquer `run()`) et deux
  nouveaux tests — la session reste en attente tant qu'aucune action n'est
  reçue puis se termine proprement sur un retour, sans jamais émettre
  `exercice_end_of_line` ; et "recommencer" avec le livre toujours
  manquant réaffiche l'erreur (au moins 2 occurrences) sans log
  supplémentaire ni `exercice_end_of_line`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 125 passed,
  10 skipped.

### Reproduction manuelle

1. Renommer temporairement le fichier du livre d'ouvertures attendu (ex.
   `data/books/gm2001.bin` → `gm2001.bin.bak`), ou renommer le dossier
   `data/books/` lui-même.
2. Lancer un exercice d'ouverture quelconque depuis l'interface.
3. Observer : le message « Livre d'ouvertures introuvable : <chemin> »
   reste affiché tant qu'aucune action n'est prise — pas de retour
   automatique à la liste, l'échiquier affiché est celui de la position de
   départ de l'exercice choisi (pas celui d'un exercice précédent).
4. Cliquer « ↺ Recommencer l'exercice » : l'erreur est réaffichée à
   l'identique (toujours pas de retour à la liste).
5. Cliquer « ← Choisir autre ouverture » ou « ← Retour au menu » : retour
   normal à la liste des ouvertures / au menu.
6. Restaurer le fichier/dossier renommé à l'étape 1.
