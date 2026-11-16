# Changelog — issue #355

## Ménage de CONTEXTE.md : archive de l'historique des issues, compactage des invariants

`CONTEXTE.md` pesait 81206 octets (98 lignes), dont 76252 octets (76252/81206 ≈ 94 %) dans la seule section « Principes techniques » — 48 lignes, chacune le paragraphe narratif (essai réel / cause / correctif / tests) d'une ou plusieurs issues Lichess/analyse-après-partie. Lu intégralement par l'agent en début de session, ce coût de lecture croissait à chaque issue, et deux affirmations (#341/#342) étaient devenues fausses tant qu'on ne lisait pas aussi la correction inline de #345 qui les suivait.

### Archive sans perte — `docs/HISTORIQUE_CONTEXTE.md` (nouveau)

Les 48 lignes retirées de « Principes techniques » (lignes 30 à 77 de l'ancien fichier) y sont copiées **mot pour mot**, chacune sous un en-tête `## Issue <NNN>` portant son numéro d'origine et son numéro de ligne. Vérifié automatiquement par script (comparaison caractère près entre les lignes retirées et le corps de chaque entrée de l'archive) : **0 écart sur 28 entrées non vides**. Ce fichier n'est pas dans la liste des fichiers lus automatiquement par l'agent (`CLAUDE.md` § Fichiers de suivi) — il reste consultable à la demande.

### CONTEXTE.md compacté

Sections gardées telles quelles : Règles impératives, Projet, Conventions, Moteurs, Gros fichiers conservés, Bridge inter-agents. « Architecture » n'avait pas de paragraphe narratif à compacter (déjà factuelle) — inchangée. « Principes techniques » : les 48 lignes-paragraphes ont été relues et remplacées par 16 entrées courtes (3 à 6 lignes chacune), regroupées par thème (invariants généraux, puis Lichess : fair-play, déroulement de partie, réseau/robustesse, échiquier et LED, classé/cote, problèmes ; puis Analyse après partie : architecture/calcul, orientation des noms) — chaque entrée garde son ou ses numéros d'issue et un renvoi `CHANGELOG.md (#NNN)`. Les corrections déjà faites *en place* dans l'ancien texte (ex. #345 corrigeant #341/#342) ont été fondues dans l'état final plutôt que reproduites comme un historique.

**Point d'écart avec la consigne, à signaler à Alain** : la consigne demandait un renvoi vers `CHANGELOG-NNN.md` et de ne pas compacter une entrée si ce fichier n'existe pas. Vérifié dans ce worktree : **aucun fichier `CHANGELOG-NNN.md` n'existe actuellement, pour aucune des ~30 issues citées** — `fusionner_changelog.py` les intègre dans `CHANGELOG.md` puis les supprime (confirmé : `CHANGELOG-354.md` créé par le commit `a629667`, disparu au commit de fusion suivant `31e47f2`). Le renvoi a donc été fait vers `CHANGELOG.md` (grep sur `#NNN`, vérifié présent pour chacun des 37 numéros cités) plutôt que vers un fichier qui n'existe jamais dans ce dépôt après fusion — aucune information n'est perdue (elle est dans `CHANGELOG.md` ET dans l'archive), mais ce n'est pas littéralement ce que demandait la consigne. Voir la proposition de texte pour `consignes/projet_alchess.md` plus bas, qui tient compte de ce fonctionnement réel.

### Corrections factuelles (État actuel)

- **Retiré** : « dépendances en retard (setuptools, chess, wheel, Flask-SocketIO avec python-socketio ensemble) ». Vérifié stale pour la partie vérifiable : `requirements.txt` porte `setuptools==84.1.0`, `wheel==0.46.2`, `python-socketio==5.16.2`, `Werkzeug==3.1.9` — correspond exactement à l'entrée `CHANGELOG.md` « Dépendances : correctifs de sécurité... » qui a déjà fait ces montées de version il y a longtemps. La partie « chess » du constat n'a pas pu être vérifiée (pas d'accès réseau PyPI depuis cette tâche) — retirée avec le reste plutôt que laissée à moitié fausse ; signalée ci-dessous comme point à revérifier par Alain si besoin.
- **Gardé inchangé** : date de release v1.3.2 (tag git confirmé au 18/08/2026), bugs connus matériel/Windows (aucune preuve de correction trouvée dans `CHANGELOG.md`), DLL Visual C++ 2013 de `rodent-iv-win/` (fichiers toujours présents sur disque).

### Entrées douteuses ou à revérifier (liste pour relecture d'Alain, rien corrigé en silence au-delà de ce qui précède)

1. **Version du paquet `chess`** — citée comme « en retard » dans l'ancien texte, retirée par prudence (voir ci-dessus) faute de pouvoir vérifier une version PyPI actuelle depuis ce worktree sans réseau. Actuellement `chess==1.10.0`.
2. **Renvoi `CHANGELOG-NNN.md`** — voir le point d'écart ci-dessus : tous les renvois du fichier compacté pointent vers `CHANGELOG.md` au lieu de fichiers par issue, qui n'existent plus après la fusion automatique. Décision prise unilatéralement pour ne pas bloquer tout le compactage ; à valider par Alain.
3. **Bugs connus non revérifiés** (rangement HH, race LEDs, WAIT_FISH) — laissés tels quels, aucune mention de correction trouvée dans `CHANGELOG.md`, mais nécessitent le matériel/Windows pour être revérifiés, hors de portée de cette tâche.

### Vérifications « rien ne doit casser »

- `grep -rl "CONTEXTE" --include=*.py .` et `grep -rl "CONTEXTE\.md" nicsoft/` : aucune correspondance — aucun test, script ou outil du dépôt ne lit `CONTEXTE.md` par le code. Seule `CLAUDE.md` le mentionne comme documentation.
- Tous les fichiers de test et modules cités dans le texte compacté existent réellement (`test_no_web_import.py`, `test_issue303_html_escaping.py`, `test_issue304_security.py`, `test_issue320_single_instance.py`, `test_issue333_lichess_no_engine.py`, `review_multipv.py`, etc.).
- Suite de tests complète rejouée (`python -m pytest nicsoft/tests -m "not hardware"`) : **1635 passed, 86 skipped** en 200.78s, aucune régression (aucun fichier Python modifié par cette tâche).

### Mesures finales

| | Avant | Après |
|---|---|---|
| `CONTEXTE.md` (octets) | 81206 | 16871 |
| `CONTEXTE.md` (lignes) | 98 | 85 |
| Section « Principes techniques » (octets) | 76252 | 12015 |
| Entrées d'issues (paragraphes) | 48 (28 non vides après fusion des lignes consécutives) | 16 entrées groupées par thème, 28 numéros d'issue tous cités |
| `docs/HISTORIQUE_CONTEXTE.md` | — (nouveau) | 77031 octets, 28 entrées, 0 écart vérifié avec le texte retiré |

Objectif indicatif de 20-25 Ko non atteint exactement (16871 octets) — le compactage par thème a permis de descendre sous la cible sans qu'aucun invariant cité dans la liste de contraintes (fair-play, jeton, `esc()`, https, pièges USB/LED/FEN) n'ait été sacrifié ; chacun est toujours présent, avec son renvoi vers le détail.

### Fichiers modifiés

- `CONTEXTE.md` — section « Principes techniques » réécrite (compactée, groupée par thème) ; « État actuel » corrigé (dépendances déjà à jour retirées).
- `docs/HISTORIQUE_CONTEXTE.md` (nouveau) — archive verbatim des 48 lignes retirées.
- `CHANGELOG-355.md` (nouveau, ce fichier).

Aucun fichier Python modifié (`py_compile` : N/A). `driver.py`, `.audit.json`, `configs/*.conf`, `requirements.txt` non touchés. Aucun serveur ni navigateur lancé pendant cette tâche (pas nécessaire — travail de documentation pur). Aucune partie ni recherche Lichess réelle, aucun jeton lu.

### Texte proposé pour `consignes/projet_alchess.md` (à coller par Alain — hors périmètre de cette tâche)

```
## CONTEXTE.md : discipline d'entrée (après le ménage de #355)

- Pour le sujet d'une future issue déjà couvert par une entrée existante dans
  CONTEXTE.md (même thème Lichess/analyse/USB-LED/etc.) : METTRE À JOUR ou
  REMPLACER cette entrée plutôt que d'en ajouter une nouvelle à côté.
- Une entrée neuve ou mise à jour tient en quelques lignes (3 à 6) : seulement
  ce qu'un développeur doit savoir pour ne pas casser quelque chose (règle à
  respecter, piège connu, invariant, fonction/fichier à ne pas contourner) —
  jamais le récit (essai réel, date, cause, mesures, liste de tests), qui va
  entièrement dans CHANGELOG-<N>.md.
- Renvoi de détail à écrire sous la forme « Détail : CHANGELOG.md (#NNN) »
  (pas CHANGELOG-<N>.md : ce fichier par issue est fusionné dans CHANGELOG.md
  puis supprimé par fusionner_changelog.py avant le push — il n'existe plus
  ensuite dans le dépôt).
- Si l'issue en cours rend fausse ou contradictoire une entrée existante
  (constaté, pas supposé) : corriger cette entrée pour refléter l'état réel,
  ne jamais laisser les deux affirmations contradictoires côte à côte.
- Si CONTEXTE.md dépasse 30 Ko après la mise à jour de cette issue : le
  signaler explicitement dans le rapport de clôture (taille avant/après),
  sans ménage automatique — Alain décide.
```
