# Changelog — Issue #384

## Faux « coup refusé » Lichess : reconnaissance par place attendue, pas par fin de liste (suite de #368/#375/#377)

Point 1 — Depuis #377, un coup refusé par Lichess avec le message ambigu HTTP 400 « Not your turn, or game already over » n'affichait plus de faux « coup refusé » si le coup tenté était déjà le DERNIER coup de `self.board.move_stack`. Mais si l'adversaire répond déjà pendant la relecture bornée du flux (très probable contre l'IA Lichess, qui répond presque aussitôt), le dernier coup de la liste est celui de l'adversaire, pas le nôtre : le faux refus réapparaissait.

### Correctif (`nicsoft/modes/lichess/game.py`)

- `_submit_move()` capture désormais `expected_ply = len(self.board.move_stack)` **avant** l'envoi — le demi-coup où le joueur devait jouer (toujours le sien, puisque `_check_user_move` n'appelle `_submit_move` que pendant son tour). Un retry automatique du même uci (réseau revenu) retrouve la même place, `self.board` n'avançant que par l'écho confirmé du flux.
- `_move_already_applied(uci, expected_ply)` (anciennement sans paramètre) compare désormais `self.board.move_stack[expected_ply]` à `uci` — jamais `move_stack[-1]`, et jamais une recherche de `uci` n'importe où dans l'historique (piège inverse : un même uci peut avoir été joué plus tôt, par exemple un cavalier qui part et revient — un coup identique à une autre place ne doit jamais être pris pour la confirmation).
- `_handle_move_rejected()` transmet `expected_ply` à `_move_already_applied` ; le mécanisme de renvoi, la logique de réclamation et la gestion d'une partie déjà terminée restent inchangés.

### Tests (`nicsoft/tests/test_issue368_lichess_game_network_loss.py`)

- `test_confirmation_et_reponse_adverse_pendant_la_relecture_najamais_de_faux_refus` : le flux confirme le coup du joueur ET apporte la réponse de l'adversaire pendant la relecture bornée — aucun message d'erreur (reproduit le scénario exact signalé par l'énoncé : échouait avec l'ancien `move_stack[-1]`).
- `test_coup_identique_joue_plus_tot_najamais_pris_pour_la_confirmation` : un coup identique (même uci) joué plus tôt dans la partie n'est jamais pris pour la confirmation — le refus reste affiché.
- Tests existants de #377 (`test_double_envoi_apres_reponse_perdue_confirmee_pendant_la_relecture_najamais_de_faux_refus`, `test_vrai_refus_apres_relecture_sans_confirmation_affiche_toujours_lerreur`) : inchangés, toujours verts.

### Documentation

`docs/contexte/lichess.md` : ligne « Coup refusé ambigu » mise à jour pour décrire la comparaison par place attendue (`expected_ply`) plutôt que par dernier coup de la liste.

### Vérification

- `test_issue368_lichess_game_network_loss.py` + `test_issue347_lichess_ambiguous_move_rejection.py` : 14 passed.
- Suite complète `-m "not hardware"` : verte deux fois de suite, **1843 passed, 86 skipped, 1 deselected** (référence avant cette issue : 1778 passed, 86 skipped — écart dû aux issues #368/#375/#377/#383 déjà présentes dans ce worktree avant le début de cette tâche, et aux 2 nouveaux tests de ce point 1). Un premier passage complet a signalé un échec isolé sur `test_issue366_regrisage_echiquier_e2e.py::test_connecte_puis_deconnecte_puis_reconnecte` (fichier non touché par cette issue, dernière modification #366) ; rejoué seul il passe, et les deux passages complets suivants sont intégralement verts — flake e2e préexistant, sans rapport avec cette correction.
- Garde fair-play (`test_issue333_lichess_no_engine.py`) : verte (comprise dans la suite complète), non affectée (aucun import ajouté, aucune nouvelle dépendance).
