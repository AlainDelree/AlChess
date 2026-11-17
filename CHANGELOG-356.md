# Changelog — issue #356

## Restructuration du contexte projet : CONTEXTE.md court + un fichier par domaine dans docs/contexte/

### Problème

`CONTEXTE.md` faisait 16401 caractères (`wc -m`) après le ménage #355, mais le watcher n'injecte dans le prompt de CCL que les 4000 premiers caractères : les sections Conventions, Moteurs, Gros fichiers conservés, Bridge et État actuel (après le caractère ~13900) n'étaient donc jamais vues par l'agent, et le début des « Principes techniques » était coupé en pleine phrase.

### Inventaire

Fichiers candidats au rôle de « fichier de contexte » (recherche de références dans tout le dépôt, y compris scripts d'installation, workflows, tests) :
- `CONTEXTE.md` (16401 car.) — cité par `CLAUDE.md`, `CHANGELOG.md`, `docs/HISTORIQUE_CONTEXTE.md`. Aucun code/script/CI ne le lit par chemin.
- `HISTORIQUE_BUGS.md` (12670 car.) — cité par `CLAUDE.md`, `SPECIFICATIONS.md`, `TESTS.md`, `CONTEXTE.md`, `CHANGELOG.md`. Aucun code ne le lit par chemin.
- `docs/HISTORIQUE_CONTEXTE.md` (74642 car., créé par #355) — cité uniquement par `CHANGELOG.md`.
- `TESTS.md` (8307 car.) — cité par `SPECIFICATIONS.md`, `CLAUDE.md`, `CONTEXTE.md`, `CHANGELOG.md`, et par un commentaire (pas un chemin chargé) dans `nicsoft/tests/e2e/test_smoke_e2e.py`.
- `TEST_RESULTATS.md` (1215 car.) — cité par `SPECIFICATIONS.md`, `CLAUDE.md` seulement ; une seule entrée datée (2026-05-02), rôle de journal plutôt que de contexte d'orientation.
- `SPECIFICATIONS.md`, `ETAT_PROJET.md`, `CORRECTION_TRADUCTION.md` — non cités par `CONTEXTE.md` ni par la table « Fichiers de suivi » de `CLAUDE.md` (sauf SPECIFICATIONS.md, listé mais de nature "document de référence", comme README/INSTALLATION_ALCHESS.md).
- Aucun `configs/*.conf` présent dans ce worktree ; `TACHES.md` absent (privé, non suivi par git) — non touché, conformément à la consigne.
- Aucune valeur sensible trouvée dans les fichiers de contexte (recherche jeton/clé/email/identifiant) : toutes les mentions de "jeton" sont des règles ("jamais le jeton", "jeton toujours côté serveur"), pas des valeurs réelles.

### Déplacé (`git mv`, un seul emplacement sous `docs/contexte/`)

- `HISTORIQUE_BUGS.md` → `docs/contexte/historique_bugs.md`. Références mises à jour dans `CLAUDE.md`, `SPECIFICATIONS.md`, `TESTS.md`.
- Nouveaux fichiers créés (contenu issu du découpage de l'ancien `CONTEXTE.md` par domaine, règles vivantes uniquement) : `docs/contexte/architecture.md`, `docs/contexte/echiquier_usb_led.md`, `docs/contexte/lichess.md`, `docs/contexte/analyse_post_partie.md`, `docs/contexte/moteurs.md`, `docs/contexte/gros_fichiers_audit.md`.
- `CONTEXTE.md` réécrit : 3681 caractères (`wc -m`, sous la limite de 3700), ordre règles → architecture → conventions → index des fichiers de domaine (chacun avec « quand le lire »). Il n'y a plus de contenu coupé : le fichier tient entièrement dans l'injection.

### Supprimé — preuve de couverture

- `docs/HISTORIQUE_CONTEXTE.md` (74642 car., 28 entrées couvrant les issues #306 à #354) : **supprimé en entier**. Vérifié que les 37 numéros d'issue cités (306,307,309,311,312,314,316-323,325-329,331,333-335,337,338,340-342,344,345,347-352,354) ont chacun au moins une entrée `# Changelog — issue #NNN` dédiée dans `CHANGELOG.md` (grep `#NNN`, puis vérification manuelle des occurrences uniques #312/#337/#349/#350/#352/#354) — couverture confirmée à 100 %, aucune perte d'information.

### Non supprimé — pas de preuve de couverture (laissé pour décision d'Alain)

- `docs/contexte/historique_bugs.md` (ex-`HISTORIQUE_BUGS.md`) : contenu antérieur au système d'issues GitHub (BUG-001 à BUG-011, « lot 2 » par hash de commit, dates mars-mai 2026). Recherche des 11 identifiants `BUG-NNN` et de 13 hash de commit cités (`0c78402`, `8b46117`, `c958300`, etc.) dans `CHANGELOG.md` : **0 occurrence** — ce fichier n'était pas encore alimenté à cette époque. Contenu **déplacé tel quel** (pas de suppression, pas de récriture) ; à garder ou à faire fusionner dans `CHANGELOG.md` à la discrétion d'Alain.
- `TEST_RESULTATS.md`, `ETAT_PROJET.md` (6 mois, daté 2026-05-22), `SPECIFICATIONS.md` (mentionne encore `nicsoft/niclink/_niclink.cpython-*.so`, extension C++ remplacée depuis par `hid_backend.py` pur Python), `CORRECTION_TRADUCTION.md` : non modifiés — hors du périmètre strict « fichier de contexte » (ni cités par `CONTEXTE.md`, ni lus automatiquement par CCL), mais `ETAT_PROJET.md` et `SPECIFICATIONS.md` contiennent des informations manifestement périmées. Listés ici pour décision d'Alain plutôt que corrigés en silence.

### Mentions « à venir »/« bugs connus » vérifiées (rien corrigé en silence)

- Release : `git tag` confirme `v1.3.2` toujours la dernière étiquette (18/08/2026, inchangé), `master` 450 commits en avance — toujours exact.
- DLL Visual C++ 2013 : `engines/rodent-iv-win/msvcp120.dll` et `msvcr120.dll` **toujours présentes sur disque** — mention « à retirer » toujours valide, conservée dans `CONTEXTE.md`.
- Bugs connus matériel/Windows (rangement HH, race LEDs, WAIT_FISH) : aucune mention de correction trouvée dans `CHANGELOG.md` (déjà vérifié par #355) — laissés tels quels, nécessitent le matériel pour revérification.

### Vérifications « rien ne doit casser »

- `grep` sur tout le dépôt (y compris fichiers cachés, scripts d'installation, `.github/workflows/`, `bridge/`) : aucun code, test, script d'installation ni workflow ne charge `CONTEXTE.md`, `HISTORIQUE_BUGS.md` ou `docs/HISTORIQUE_CONTEXTE.md` par leur chemin — seules des mentions documentaires, toutes mises à jour.
- Suite de tests complète hors matériel rejouée (`python -m pytest nicsoft/tests -m "not hardware"`) : **1635 passed, 86 skipped** en 198.78s — identique au résultat de #355, aucune régression.

### Mesures finales

| Fichier | Avant | Après |
|---|---|---|
| `CONTEXTE.md` | 16401 car. | 3681 car. (tient entièrement dans l'injection de 4000 car.) |
| `HISTORIQUE_BUGS.md` → `docs/contexte/historique_bugs.md` | 12670 car. | 12670 car. (déplacé, inchangé) |
| `docs/HISTORIQUE_CONTEXTE.md` | 74642 car. | supprimé (0) |
| `docs/contexte/architecture.md` (nouveau) | — | 2768 car. |
| `docs/contexte/lichess.md` (nouveau) | — | 5828 car. |
| `docs/contexte/analyse_post_partie.md` (nouveau) | — | 2213 car. |
| `docs/contexte/echiquier_usb_led.md` (nouveau) | — | 998 car. |
| `docs/contexte/moteurs.md` (nouveau) | — | 819 car. |
| `docs/contexte/gros_fichiers_audit.md` (nouveau) | — | 961 car. |
