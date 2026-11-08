# Changelog — Issue #297

## Sécurité : droit d'exécution limité au propriétaire sur les moteurs détectés, suppression du repli espeak-ng inutilisé

### Contexte
Deux restes du troisième audit, sans lien entre eux. SEC-003 (motifs
dangereux d'analyse statique) signalait `_ensure_executable()` dans
`nicsoft/engine/engine_detection.py` : seul appel de changement de droits du
code, il ajoutait le bit exécutable au propriétaire, au groupe et aux
autres, alors que l'application est locale et mono-utilisateur. L'audit
signalait aussi `_speak_espeak()` dans
`nicsoft/modes/opening_explorer/tts_engine.py` (lancement d'espeak-ng par
chemin partiel) ; cette fonction n'avait plus aucun appelant depuis le
passage à edge-tts, et Alain a choisi de la supprimer plutôt que de la
justifier.

### Changements
- `engine_detection.py::_ensure_executable()` : ne donne plus que
  `stat.S_IXUSR` (bit exécutable du propriétaire), au lieu de
  `S_IEXEC | S_IXGRP | S_IXOTH`. Comportement inchangé pour le reste :
  no-op sous Windows, no-op si le bit du propriétaire est déjà présent,
  avertissement sans exception si `os.chmod` échoue.
- Nouveau test `nicsoft/tests/test_issue297_ensure_executable.py` (3 cas,
  fichiers temporaires, ignoré sous Windows) : ajout du seul bit
  propriétaire, non-modification si déjà exécutable, chemin inexistant
  sans exception.
- `tts_engine.py` : suppression de `_speak_espeak()` et de la table
  `VOICE_MAP_ESPEAK` (aucun autre appelant trouvé dans le dépôt — code,
  tests, scripts). Aucun import devenu inutile (`subprocess` reste
  nécessaire à `_speak_edge()` pour `mpg123`). Docstring du module et de
  `speak()` reformulées pour ne plus mentionner espeak-ng comme repli
  disponible.
- `requirements.txt` : suppression du commentaire présentant espeak-ng
  comme prérequis du repli TTS (le repli n'existe plus) ; aucune version
  de paquet modifiée.
- `bootstrap_linux.sh` : installation d'espeak-ng conservée telle quelle
  (sujet reporté), commentaire de la section mis à jour pour indiquer
  qu'elle n'est plus utilisée par Opening Explorer depuis cette issue.

### Non traité (hors périmètre de cette issue)
- Mentions restantes d'espeak-ng : uniquement dans `bootstrap_linux.sh`
  (installateur Linux), désormais signalées comme obsolètes en commentaire.
- Versions de `requirements.txt`, bibliothèques runtime Visual C++ 2013 de
  `engines/rodent-iv-win/`, téléchargement de Rodent IV et ses empreintes,
  `.audit.json` : non touchés, sujets explicitement reportés.

### Vérification
- `ruff check --select S` sur les deux fichiers : avant correction,
  S103 (chmod permissif) et S603/S607 (espeak-ng, chemin partiel) ;
  après correction, aucun signalement (« All checks passed! »).
- `bandit -r` sur les deux fichiers : les mêmes deux sites disparaissent ;
  seul reste un B404 (import du module `subprocess`, bas niveau,
  préexistant pour `_speak_edge()`/mpg123, hors périmètre).
- Suite complète hors tests `hardware` : 575 passés, 75 ignorés (réseau,
  matériel, plateforme).

### À vérifier manuellement (Alain)
- Lancer l'application et confirmer qu'un moteur détecté se lance toujours
  (Stockfish, lc0/Maia, Rodent IV).
- Confirmer que la synthèse vocale de l'explorateur d'ouvertures fonctionne
  comme avant (edge-tts) si un accès réseau est disponible.
