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

## Partie 2 — Perte de connexion en pleine partie Lichess

Constat (inspection bornée, détail dans le rapport de clôture) : le flux
de partie (lecture des coups adverses) reprend déjà automatiquement avec
des attentes croissantes (`RECONNECT_DELAYS_S`, `game_client.py`,
inchangé) et affiche déjà un bandeau permanent dédié
(`lichess-reconnecting-banner`, piloté par `lichess_reconnecting`/
`lichess_reconnected`) — jamais vérifié bout en bout (LichessGame complet)
avant cette issue. Un coup physique envoyé pendant une coupure n'est
jamais perdu (réessayé automatiquement au tick suivant, ~50ms, tant qu'il
n'est pas confirmé) ni dupliqué dangereusement (un double envoi accidentel
est rejeté par Lichess sans fausse alerte, mécanisme #347 inchangé). Bug
réel corrigé : le toast persistant « réseau indisponible » affiché lors
d'un échec réseau (coup, abandon, nulle, réclamation) ne disparaissait
jamais tout seul au retour du réseau — restait affiché indéfiniment même
après une reprise réussie.

- `nicsoft/modes/lichess/game.py` : `_report_network_error()`/
  `_clear_network_error_if_active()` (nouveau drapeau
  `_network_error_active`) — le toast persistant « réseau indisponible »
  est désormais remplacé par un message de rétablissement
  (`lichess.erreur_reseau_retablie`) dès la prochaine action réseau
  réussie (`_submit_move`, `_safe_client_call`, `_safe_claim_call`,
  `_safe_draw_offer_call`) — mécanisme réutilisé (toast déjà existant),
  jamais un second canal.
- i18n (fr/en/de) : `lichess.erreur_reseau_retablie`.
- Tests : `nicsoft/tests/test_issue368_lichess_game_network_loss.py` —
  coup physique en coupure (toast persistant puis rétablissement, jamais
  deux coups différents envoyés) ; flux coupé puis reconnecté bout en bout
  (bandeau permanent, jamais d'abandon automatique) ; flux définitivement
  perdu (fin de partie propre, sans plantage).
- Gaps identifiés, non corrigés (risque trop élevé pour une correction
  bornée) — voir rapport de clôture pour le détail et une proposition :
  (a) un double envoi après une RÉPONSE perdue (coup en fait accepté) peut
  encore afficher un faux « coup refusé » après le délai de relecture du
  flux si la partie continue (`_handle_move_rejected`) ; (b) pas de reprise
  manuelle/stratégie de réclamation dédiée pour une coupure très longue ;
  (c) pas de gestion du temps de réflexion pendant une coupure prolongée.
- Documentation : aucune (comportement du flux inchangé, seul le
  rattrapage du toast est nouveau — déjà couvert par la ligne de la
  partie 1 dans `docs/contexte/lichess.md`). `CONTEXTE.md` inchangé.
