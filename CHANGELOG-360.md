# Changelog — Issue #360

## Correctifs issus des gardes #359 : retour au menu du mode humain, évènements sans gestionnaire JS, drapeau de reprise Lichess, SAN des problèmes

### 1. Retour au menu du mode humain (HH)

`GameWeb._handle_turn()` (`modes/humain/human.py`) : le `except Exception`
autour de `await_move()` a désormais un `except ExitNicLink` dédié avant
le générique — ne classe plus par `kill_switch.is_set()` après coup.
`GameWeb._traiter_abandon()` (branche `back_menu`) lève `BackMenuExit` au
lieu de `sys.exit(0)` ; capturée dans `core/game_manager_modes/
humain.py::_run_humain()`, même schéma que `modes/pedagogique/
pedagogique.py` (diagnostic #358). Tests ajoutés (VirtualBoard, sans
matériel ni serveur réel) : chemin réel thread de jeu + back_menu + fin
propre, et non-avalement d'`ExitNicLink`.

### 2. Évènements sans gestionnaire JS

`undo_impossible`, `undo_confirmed`, `undo_wait_position` (mode humain) :
gestionnaire JS ajouté (message court sur `#turn-info`, mécanisme déjà
utilisé par `illegal_position`/`board_warning`) + clés i18n fr/en/de +
`message_key` côté Python. `exercice_turn` (exercices) : émission
supprimée — le statut « c'est votre tour » est déjà affiché sans lui par
`exercice_wait_position`/`exercice_adv_move`, aucune information perdue.
Liste blanche de `test_issue359_event_handler_guard.py` vidée.

### 3. Drapeau `_lichessResumeSetupActive`

`app.js` : `_lichessHideStatusBanners()` et le handler `lichess_init` ne
remettaient pas ce drapeau à `false` — une mise en place de reprise
abandonnée pouvait masquer la bannière de décompte du premier coup de la
partie suivante. Corrigé aux deux endroits. Remise à faux manuelle en fin
de `test_issue323_lichess_resume_e2e.py` retirée (vérifié verte en ordre
fixe et en ordre aléatoire `--randomly-seed=1`) + nouveau test e2e dédié.

### 4. SAN des problèmes Lichess

`modes/lichess/puzzle_game.py` (flux live, 3 appels) : `san_ep()` au lieu
de `board.san()` direct. `engine/review_multipv.py` et `web/server.py` (1
occurrence chacun) : même correction, après vérification que la valeur
est uniquement affichée (jamais comparée ni stockée). Outils d'import/
export de livres d'ouvertures (`modes/exercices/*`) non touchés (hors
périmètre). Listes blanches des deux gardes #359 mises à jour.

### docs/contexte/architecture.md

Violations connues corrigées ci-dessus retirées des règles concernées ;
citations par numéro de ligne remplacées par des noms de fonction.

### Suite de tests

`python -m pytest nicsoft/tests -m "not hardware"` rejouée en une seule
fois après toutes les modifications ci-dessus (voir rapport de clôture
pour le résultat détaillé).
