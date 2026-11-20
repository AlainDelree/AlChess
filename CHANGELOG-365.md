# Changelog — Issue #365

## Menu Lichess accessible sans échiquier connecté (correctif du rapport #364)

Le rapport de clôture de l'issue #364 affirmait que l'accès au mode virtuel
des problèmes n'était pas bloqué sans échiquier — vérifié en réel par
Alain : faux pour l'entrée « Lichess » du menu PRINCIPAL, qui restait grisée
comme Humain contre Humain (`data-needs-board data-physical-only`), rendant
l'écran contenant la carte « Problèmes » — et donc le mode virtuel lui-même
— inaccessible sans échiquier. #364 n'avait vérifié que le bouton à
l'intérieur de la carte, jamais l'entrée du menu qui y mène. Aucun garde
côté serveur ne bloquait quoi que ce soit (confirmé par lecture de
`alchess.py`/`game_manager_modes/lichess.py`) — le blocage était uniquement
côté navigateur.

- `nicsoft/web/templates/index.html` : `.menu-btn-lichess` perd
  `data-needs-board`/`data-physical-only` — ne dépend plus que du jeton
  personnel enregistré, comme avant mais sans l'échiquier. Carte
  « Problèmes » : nouveau `#btn-start-lichess-puzzle` (id ajouté pour le
  cibler) et nouvelle explication `#lichess-puzzle-board-hint`, visible
  seulement quand le mode « Échiquier » est choisi sans échiquier connecté.
  Texte de la bande `banner.board_absent_lichess` reformulé : les parties
  Lichess et le mode « Échiquier » des problèmes nécessitent l'échiquier,
  pas les problèmes « Sur l'écran ».
- `nicsoft/web/static/app.js` : `_applyLichessCardState()` ne teste plus
  `_boardOk`, seulement le jeton. Nouvelle `_applyLichessPuzzleBoardState()`
  grise `#btn-start-lichess-puzzle` (+ affiche l'explication) uniquement si
  mode « Échiquier » ET pas d'échiquier — jamais pour le mode « Sur
  l'écran ». Garde-fou défensif dans `startLichessPuzzle()` (même condition,
  au cas où le bouton serait réactivé par erreur). `_applyBoardBadge()` —
  déjà le mécanisme d'état de l'échiquier en place — appelle désormais aussi
  cette fonction et met à jour `#btn-start-lichess` (partie réelle,
  inchangé dans son exigence, mais maintenant réactif en direct lui aussi) :
  l'écran Lichess se met donc à jour sans recharger la page quand
  l'échiquier se (dé)connecte pendant qu'il reste ouvert.
- i18n (fr/en/de) : nouvelle clé `config.lichess.probleme_requiert_echiquier` ;
  `banner.board_absent_lichess` reformulée dans les 3 langues.
- Tests : `nicsoft/tests/e2e/test_issue365_lichess_sans_echiquier_e2e.py` —
  entrée menu active sans échiquier avec jeton, grisée sans jeton même
  échiquier connecté, Humain contre Humain inchangé (reste grisé sans
  échiquier) ; dans l'écran Lichess sans échiquier : mode « Sur l'écran »
  utilisable et action de lancement correctement envoyée, mode « Échiquier »
  et partie réelle grisés avec explication visible, mise à jour en direct au
  branchement/débranchement simulé de l'échiquier (sans recharger la page) ;
  avec échiquier connecté depuis le début, rien ne change. Jamais de vrai
  jeton, de vraie partie/problème Lichess ni de vrai échiquier — événements
  socket simulés (même technique que `test_issue310_lichess_e2e.py`) ; le
  clic sur « Jouer un problème » en mode « Sur l'écran » est intercepté
  avant d'atteindre le serveur de test (jeton réel vide dans l'environnement
  e2e isolé) pour ne vérifier que l'action envoyée côté navigateur — le
  lancement réel côté serveur est déjà couvert, en process, par
  `test_issue364_lichess_puzzle_virtuel.py`.
  Docstring de `test_issue310_lichess_e2e.py::at_config_lichess` adaptée
  (ne mentionnait plus la réalité : le bouton menu n'est plus conditionné à
  l'échiquier, seulement au jeton).
- Documentation : `docs/contexte/lichess.md` (1 ligne — accès sans
  échiquier, ce qui reste grisé). `CONTEXTE.md` inchangé.
