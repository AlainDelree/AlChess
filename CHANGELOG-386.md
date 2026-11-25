# Changelog — Issue #386

## Coup glissé en partie et en problèmes Lichess : exiger une position stable avant l'envoi (suite de #381)

Dernier défaut connu du chantier Lichess (étude #381) : sur l'échiquier réel, un coup glissé sans lever la pièce (ex. e2-e4) pouvait être enregistré et envoyé à Lichess sur une case intermédiaire (e2-e3), parce que le coup était validé dès la PREMIÈRE lecture de position légale, sans aucun délai de stabilité — contrairement aux modes pédagogique/humain/exercices, qui exigent déjà 0.35s de position stable (driver.py::NicLinkManager.STABLE_DELAY). Le point « faux coup refusé » (#384) n'est pas concerné et n'a pas été touché.

### Correctif (`nicsoft/modes/lichess/game.py`, `nicsoft/modes/lichess/puzzle_game.py`)

- Nouvelle constante partagée `MOVE_STABLE_DELAY_S = 0.35` (`game.py`, importée par `puzzle_game.py`) — horloge monotone (`time.monotonic`), donc indépendante de la cadence de lecture (~50ms) ; documentée par un commentaire renvoyant à `driver.py::NicLinkManager.STABLE_DELAY`, **jamais modifié ni mocké** par cette issue.
- `LichessGame._check_user_move()` et `PuzzleGame._tick_physical()` : quand la position physique correspond à un coup légal, celui-ci n'est plus envoyé/accepté immédiatement — une nouvelle méthode `_move_is_stable(hardware_fen)` (identique dans les deux classes) exige que la MÊME lecture se répète sans interruption pendant `MOVE_STABLE_DELAY_S` avant d'appeler `_submit_move()`/`_evaluate_user_move()`. Toute lecture différente (y compris un retour à la position attendue ou une position illégale) réinitialise l'attente (`_pending_move_fen`/`_pending_move_since`).
- Ce qui ne change PAS : le mécanisme de renvoi après erreur réseau (#368/#377), le traitement des positions illégales (stabilité par **nombre** de lectures, 8, inchangée — jamais par le temps), la détection de promotion (choix de la pièce fait à l'écran, sans délai supplémentaire — c'est un geste explicite du navigateur, pas une lecture physique glissée), et la reconnaissance du coup déjà appliqué (#384). Les signaux LED/bip liés au coup suivant (réponse forcée en problème, par exemple) ne sont pas cassés : simplement décalés de la même durée, puisqu'ils ne se déclenchent qu'après l'acceptation du coup.

### Tests

- `nicsoft/tests/test_issue386_lichess_move_stability.py` (nouveau, 14 tests, horloge entièrement simulée — `time.monotonic` monkeypatché par une horloge contrôlable, aucun sleep réel) : les 6 scénarios demandés, pour la partie **et** pour les problèmes — pion deux cases glissé, glissement lent (position intermédiaire maintenue plusieurs lectures mais moins que la durée de stabilité), pièce levée puis reposée, coup réellement joué sur la case courte, capture intermédiaire pendant un glissement, non-régression promotion/position illégale (démontrée en bloquant l'horloge : la détection illégale s'active quand même au bout de 8 lectures).
- Tests existants adaptés à la nouvelle fenêtre de stabilité (comportement changé intentionnellement, jamais une régression) : `test_issue309_lichess_l2a.py` (+ nouvel helper `_settle_physical_move()`, réutilisé par les fichiers suivants), `test_issue323_lichess_resume.py`, `test_issue347_lichess_ambiguous_move_rejection.py`, `test_issue347_lichess_resign_anytime_and_draw_after_move.py` — chaque tick unique qui attendait un envoi immédiat du coup physique de l'utilisateur est remplacé par `_settle_physical_move()` (démarre le chronométrage puis le recule au-delà de `MOVE_STABLE_DELAY_S`, sans sleep réel). Vérifié qu'aucun autre test (réplication du coup adverse, retour à la position attendue, promotion, position illégale, scénarios déjà threadés avec budget de plusieurs secondes) n'était affecté par ce changement de comportement.

### Documentation

`docs/contexte/lichess.md` : nouvelle ligne « Coup glissé pris pour une case intermédiaire (#386...) » dans la section « Réseau et robustesse », décrivant la constante partagée, les exclusions (promotion, position illégale) et la limite connue. `docs/contexte/echiquier_usb_led.md` : non modifié — aucune règle USB/LED/quirk matériel n'est concernée, et `driver.py` reste intouché.

### Limite connue (rappel demandé par l'issue)

Un glissement dont la pièce reste physiquement plus de 0.35s posée sur une case intermédiaire (geste anormalement lent et marqué) peut encore tromper le contrôle — avec la même rareté qu'aujourd'hui dans les modes pédagogique/humain/exercices, qui partagent la même limite de principe (délai fixe plutôt que détection de mouvement). Non traitée ici, comme demandé par l'énoncé.

### Vérification

- `test_issue386_lichess_move_stability.py` : 14/14, répété 12 fois de suite sans échec (> 10 demandés).
- Suite complète `-m "not hardware"` : verte deux fois de suite, **1858 passed, 86 skipped, 1 deselected** (référence avant cette issue, clôture #384 : 1843 passed, 86 skipped, 1 deselected — écart expliqué par les 14 nouveaux tests de ce fichier plus l'écart déjà présent dans ce worktree avant le début de la tâche). Aucune occurrence du flake isolé `test_issue366_regrisage_echiquier_e2e.py` signalé par #384 sur ces deux passages.
- Garde fair-play (`test_issue333_lichess_no_engine.py`) et garde de taille de `CONTEXTE.md` (`test_issue357_contexte_guard.py`) : vertes, non affectées.

### À vérifier à la main (jamais testé sur le vrai matériel pour cette issue)

Glisser e2-e4 plusieurs fois à vitesse normale en partie Lichess réelle : le coup envoyé doit toujours être e2-e4 (jamais e2-e3), et la réactivité d'un coup normal (joué sans glisser) doit rester perceptiblement identique à avant cette issue — le délai ajouté (0.35s) est le même que celui déjà en place en mode pédagogique, déjà jugé acceptable par Alain.
