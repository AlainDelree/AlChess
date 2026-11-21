# Changelog — Issue #368

## Partie 1 — Absence de réseau dans l'écran Lichess

Constat : `test_token()` (`client.py`) confondait toute erreur HTTP non-429
(donc une vraie réponse de Lichess, réseau disponible) avec l'absence de
réseau ("network_error") ; `launch_lichess_puzzle()`
(`game_manager_modes/lichess.py`) mappait ensuite tout statut différent de
"ok"/"rate_limited" — "network_error" inclus — sur le message « jeton
refusé » (`toast.lichess_invalid_token`), trompeur sans réseau. Aucun
mécanisme n'affichait un état réseau permanent sur l'écran Lichess
lui-même (seul un bandeau éphémère apparaissait, via ce même bug).

- `nicsoft/modes/lichess/client.py` : `test_token()` distingue désormais
  trois statuts — "network_error" (DNS/connexion/`socket.timeout`,
  désormais aussi capturé, évitant un plantage non intercepté chez un
  appelant sans `try`/`except`), "invalid" (Lichess a répondu, jeton
  refusé), "lichess_error" (Lichess a répondu avec une erreur HTTP
  inattendue, 5xx). Avant : HTTP non-429 → "network_error" à tort.
- `nicsoft/core/game_manager_modes/lichess.py` : nouvelle table partagée
  `_LICHESS_TOKEN_STATUS_TOAST_KEYS` (statut → clé de toast), réutilisée
  par `launch_lichess_puzzle()` (corrigée : ne dit plus « jeton refusé »
  pour un statut réseau) et par `_run_lichess_puzzle`/
  `_run_lichess_puzzle_virtual` (dictionnaires locaux dupliqués
  supprimés). Nouvelle `check_lichess_network_status()` (verrou non
  bloquant, une seule vérification à la fois) émet
  `lichess_network_status` ({"available": bool}) — "invalid"/
  "rate_limited"/"lichess_error" valent `True` (Lichess a répondu, le
  réseau fonctionne), seul "network_error" vaut `False`.
- `nicsoft/web/alchess.py` : nouvelle action `lichess_network_check`
  (déclenche `check_lichess_network_status()` en arrière-plan) ; déclenchée
  aussi à l'ouverture de l'écran Lichess (`mode` → `lichess`).
  `nicsoft/core/game_manager.py` : réexporte `check_lichess_network_status`.
- `nicsoft/web/static/app.js` : `_applyLichessNetworkState()` (bandeau
  `#lichess-network-banner` + grisage générique `[data-needs-network]`,
  même mécanisme que `data-needs-board`/`_applyBoardBadge()`, issue #366) ;
  `btn-start-lichess`/`btn-start-lichess-puzzle` restent gérés par leurs
  calculs dédiés (board + jeton + réseau combinés), jamais par la boucle
  générique (évite un second mécanisme qui écraserait leur état).
  Vérification à l'ouverture de l'écran, minuterie de 20s tant qu'il reste
  ouvert (une seule vérification à la fois, `_lichessNetworkCheckPending`),
  et sur les évènements `online`/`offline` du navigateur — jamais en
  rafale. `lichess_test_result` : nouvelle branche "lichess_error".
- `nicsoft/web/templates/index.html` : bandeau `#lichess-network-banner`
  (même classe `board-warning-banner` que le bandeau échiquier absent,
  caché par défaut) ; `data-needs-network` sur les contrôles de l'écran
  Lichess (hors « Retour », qui reste toujours actif, et hors les deux
  boutons de lancement, gérés à part).
- i18n (fr/en/de) : `banner.lichess_network_absent`,
  `parametres.lichess.resultat.erreur_lichess`.
- Tests : `nicsoft/tests/test_issue306_lichess.py` (statut "lichess_error"
  pour une erreur HTTP 500, `socket.timeout` sans plantage) ;
  `nicsoft/tests/test_issue368_lichess_network.py` (classification
  `launch_lichess_puzzle`/`check_lichess_network_status`, câblage
  alchess.py/app.js/index.html/i18n, verrou non bloquant) ;
  `nicsoft/tests/e2e/test_issue368_lichess_network_e2e.py` (réseau absent
  → bandeau + grisage ; jeton refusé → pas de bandeau réseau ; retour du
  réseau → tout se réactive) — non exécutable dans ce bac à sable (suite
  e2e entière en erreur, limitation d'environnement préexistante et sans
  rapport avec cette issue, voir rapport de clôture).
- Documentation : `docs/contexte/lichess.md` (1 ligne, règle réseau).
  `CONTEXTE.md` inchangé.
