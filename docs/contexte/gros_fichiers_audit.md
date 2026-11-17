# AlChess — Gros fichiers conservés et audit (ARC-004)

Lire avant toute tâche touchant `driver.py`, `server.py`, ou tout fichier volumineux de `nicsoft/modes/` — et avant de proposer une exception dans `.audit.json`.

Pas d'exception dans `.audit.json` : on ne découpe pas un gros fichier pour réduire sa taille, seulement le long de coutures naturelles, quand on le modifie déjà pour une autre raison, un fichier par issue, avec tests. `driver.py` (~850 l., code NicLink, matériel non testable) : ne pas toucher sauf raison fonctionnelle. Ordre de découpe privilégié : code commun human/pedagogique, `human.py`, `pedagogique.py`, `server.py`, `exercices.py` (parties pures d'abord), `labo.py` (tests de non-régression d'abord).

`.audit.json` liste les exceptions déjà accordées (MAN-003, MAN-004) avec leur raison et leur date — toute nouvelle exception doit suivre le même format et être motivée. Ne jamais modifier ce fichier sans ordre explicite d'Alain.
