# Changelog — Issue #270

## Exercices : message clair quand le livre d'ouvertures est introuvable

Avant le fix, si le fichier du livre Polyglot était introuvable (ex. dossier
`data/` absent), `ExerciceSession._get_book_moves` avalait l'exception et
retournait une liste vide — indistinguable d'une vraie fin de ligne
théorique. L'IHM annonçait donc « Ligne terminée ! Bravo » alors que
l'exercice n'avait jamais pu se dérouler, et le serveur loggait l'erreur
« Livre : fichier ou dossier inexistant » à chaque coup.

- `nicsoft/modes/exercices/exercices.py` : l'existence du fichier du livre
  (`self._book_path`) est vérifiée une seule fois, à la construction de
  `ExerciceSession` (`self._book_missing`), et loggée une seule fois par
  exercice (`logger.error`, pas à chaque coup). `run()` détecte ce cas en
  tout premier lieu et émet `exercice_sync_error` (événement d'erreur IHM
  déjà utilisé par l'exercice pour la synchro de plateau) au lieu de
  dérouler la boucle de jeu — plus de faux `exercice_end_of_line`.
  `_get_book_moves` ne retente plus l'ouverture du fichier une fois le livre
  connu manquant, et ne logge plus qu'une fois les erreurs imprévues
  (livre corrompu, etc.) via `self._book_error_logged`.
- `nicsoft/web/static/app.js` : le handler `exercice_sync_error` accepte
  désormais deux champs optionnels — `status_key` (texte de statut
  personnalisé) et `show_sync_btn` (désactive le bouton Synchroniser quand
  resynchroniser ne résoudra rien) — sans changer le comportement par
  défaut (cas existant : pièces mal placées).
- `nicsoft/web/static/i18n/{fr,en,de}.json` : nouvelles clés
  `exercices.book_missing_status` et `exercices.book_missing_msg`
  (interpolée avec le chemin attendu du livre).
- Cas inchangés vérifiés : livre présent (coup du livre toujours trouvé) et
  vraie fin de ligne théorique (livre présent mais sans entrée pour la
  position) toujours traitée comme une fin de ligne normale.
- Nouveau test `nicsoft/tests/test_exercices_book_missing.py` (sans
  interface ni matériel) : livre absent → `exercice_sync_error` émis,
  `exercice_end_of_line` jamais émis, un seul log d'erreur ; livre présent
  → comportement inchangé ; livre présent mais vide pour la position →
  fin de ligne normale toujours distincte d'un livre manquant.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 122 passed,
  10 skipped.
