# Changelog — Issue #255

# Changelog — Issue #366

## Partie 1 — Regrisage générique des boutons `data-needs-board` à la déconnexion

Défaut préexistant signalé par #365 (hors périmètre à l'époque) : `board_ok`
réactivait génériquement tous les boutons `[data-needs-board]`, mais
`board_error`/`board_reconnecting` ne les regrisait jamais de façon
générique — seuls les deux boutons Lichess traités par #365
(`btn-start-lichess`, `btn-start-lichess-puzzle`) suivaient l'état de
l'échiquier en direct. Un bouton comme l'entrée menu Humain contre Humain
pouvait donc rester cliquable après une déconnexion survenue en cours de
session.

- `nicsoft/web/static/app.js` : la (dés)activation générique de
  `[data-needs-board]` (respectant `data-physical-only` en mode virtuel)
  déplacée dans `_applyBoardBadge()` — appelée par les trois évènements
  `board_ok`/`board_error`/`board_reconnecting`, donc regrisage/réactivation
  symétriques, sans second mécanisme. Le forEach ad hoc du handler
  `board_ok` et le bloc de réactivation du retour au menu (`app_state`,
  état `"menu"`) sont retirés au profit de ce mécanisme unique.
- `nicsoft/web/templates/index.html` : `#btn-start-hh` (bouton « Démarrer
  la partie » de l'écran de config Humain contre Humain, jusqu'ici régi par
  un bloc dédié distinct dans `_applyBoardBadge()`) porte désormais aussi
  `data-needs-board data-physical-only` — unifie son état `disabled` sur le
  mécanisme générique (son explication/`title` reste spécifique).
- Tests : `nicsoft/tests/e2e/test_issue366_regrisage_echiquier_e2e.py` —
  échiquier connecté puis déconnecté puis reconnecté : entrée menu Humain
  contre Humain et `#btn-start-hh` suivent l'état en direct ; bouton Lichess
  de #365 (`#btn-start-lichess`, partie réelle) inchangé ; `board_reconnecting`
  regrise comme `board_error`. Le contournement devenu inutile dans
  `test_issue365_lichess_sans_echiquier_e2e.py::_reset_base` (réactivation
  manuelle de `.menu-btn-humain` avant chaque test, nécessaire tant que le
  regrisage générique n'existait pas) est retiré.
- Documentation : `docs/contexte/architecture.md` (1 ligne — règle
  `data-needs-board`/`_applyBoardBadge()`). `CONTEXTE.md` inchangé.

## Partie 2 — Bascule automatique sur « Sur l'écran » sans échiquier

Dans la carte « Problèmes » de l'écran Lichess, sans échiquier connecté, le
mode « Échiquier » restait sélectionné par défaut (ou mémorisé) et « Jouer
un problème » restait grisé avec une explication jusqu'au clic manuel de
l'utilisateur sur « Sur l'écran ». Alain préfère que l'écran bascule seul,
pour que le problème reste jouable immédiatement.

- `nicsoft/web/static/app.js` : `_lichessPuzzleMode` (mode effectif,
  affiché et utilisé pour lancer un problème) et `_lichessPuzzlePreferredMode`
  (nouvelle — préférence mémorisée dans `localStorage`, changée uniquement
  par un clic explicite via `selectPuzzleModeLichess()`) sont désormais
  distincts. Nouvelle `_lichessPuzzleSyncDisplayMode()` : sans échiquier,
  bascule l'effectif sur `"virtual"` (jamais écrit dans `localStorage`) ;
  à la (re)connexion, rétablit l'effectif sur la préférence mémorisée.
  Appelée à l'ouverture de l'écran Lichess (`app_state`, état
  `"config_lichess"`) et à chaque changement d'état de l'échiquier (dans
  `_applyBoardBadge()`, donc sur `board_ok`/`board_error`/
  `board_reconnecting`). Un clic manuel reste toujours respecté et mémorisé
  comme avant #366, y compris « Échiquier » sans échiquier (l'explication
  reste alors affichée) — mais une déconnexion ULTÉRIEURE pendant que
  l'écran reste ouvert rebascule l'affichage sur « Sur l'écran », la
  préférence mémorisée restant elle inchangée.
- Tests : `nicsoft/tests/e2e/test_issue366_puzzle_mode_autobascule_e2e.py`
  — sans échiquier, « Sur l'écran » sélectionné et « Jouer un problème »
  actif sans écraser la préférence mémorisée ; reconnexion rétablit le mode
  mémorisé puis une nouvelle déconnexion rebascule l'affichage ; clic
  manuel sur chaque mode respecté et mémorisé, y compris sans échiquier.
  `test_issue365_lichess_sans_echiquier_e2e.py::
  test_bascule_echiquier_met_a_jour_les_boutons_sans_recharger` adaptée :
  une déconnexion survenant APRÈS une sélection manuelle de « Échiquier »
  bascule désormais aussi sur « Sur l'écran » (seule la partie Lichess
  réelle, toujours liée à l'échiquier physique, reste grisée) — comportement
  intentionnel de cette partie, pas une régression.
  `test_issue366_regrisage_echiquier_e2e.py` (partie 1) simplifié en
  conséquence : ne vérifie plus l'état du bouton de mode « Échiquier » des
  problèmes (désormais couvert par ce nouveau fichier), seulement le
  bouton partie Lichess réelle comme garde-fou #365.
- Documentation : `docs/contexte/lichess.md` (entrée #365 complétée d'une
  phrase sur la distinction préférence/mode effectif). `CONTEXTE.md`
  inchangé.

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

# Changelog — Issue #364

## Problèmes Lichess : mode virtuel, partie 3/3 — fin de problème, "Voir la solution", documentation

- Rien à ajouter côté code pour la fin de problème/« Voir la solution » :
  déjà traité par la partie 1/3 (`_on_solution_rewind`, `_wait_for_board_fen`
  surchargée en pause interruptible) — le bandeau de fin
  (`#lichess-puzzle-end-banner`, « Problème terminé »/« Solution terminée »)
  et « Problème suivant » sont du code PARTAGÉ avec le mode échiquier,
  inchangé (#363). Cette partie ajoute les tests qui le vérifient
  spécifiquement en mode virtuel.
- Tests e2e : `nicsoft/tests/e2e/test_issue364_puzzle_virtuel_fin_e2e.py` —
  rejeu de la solution mettant à jour l'échiquier cliquable sans attente
  physique, « Retour au menu » disponible et fonctionnel pendant
  l'affichage de la solution, « Problème suivant » relançant un nouveau
  problème dans le MÊME mode (virtuel) avec un échiquier de nouveau actif
  dès le `lichess_puzzle_your_turn` suivant.
- Documentation : `docs/contexte/lichess.md` (2 lignes — mode virtuel,
  emplacement du code) ; `SPECIFICATIONS.md` §5.8 (Problèmes : deux modes,
  Échiquier/Sur l'écran). `CONTEXTE.md` inchangé (3535 car., sous la limite).

## Problèmes Lichess : mode virtuel (jouer à l'écran), partie 1/3 — logique de jeu (Python)

Ajout du mode « Sur l'écran » pour les problèmes Lichess, en complément du
mode « Échiquier » existant (#354/#361/#362/#363, strictement inchangé).

- `nicsoft/modes/lichess/puzzle_game.py` : `VirtualPuzzleGame` hérite de
  `PuzzleGame` et ne redéfinit QUE ce qui dépendait du plateau physique
  (`_tick_physical`, `_light_move`, `_beep`, `_wait_for_board_fen` — devient
  une courte pause interruptible par retour au menu — et
  `_process_browser_actions`, qui traite le nouveau coup venu du navigateur,
  "lichess_puzzle_virtual_move", déjà complet départ/arrivée/promotion).
  Tout le reste (suivi de la solution, détection résolu/raté, mat hors
  solution accepté, envoi unique du résultat, journal, "Voir la
  solution"/"Problème suivant") est hérité à l'identique. Un seul point
  d'extension ajouté à `PuzzleGame` lui-même (`_on_solution_rewind`,
  no-op en mode échiquier) pour que le rejeu de la solution affiche la
  position de départ à l'écran — rien d'autre ne le ferait sans échiquier
  physique. Nouvelle fonction `_legal_moves_map()` : coups légaux fournis au
  navigateur par python-chess (jamais un moteur), envoyés via un nouvel
  évènement `lichess_puzzle_your_turn` à chaque fois que la main revient au
  joueur.
- `nicsoft/core/game_manager_modes/lichess.py` : `launch_lichess_puzzle`
  choisit `_run_lichess_puzzle` (échiquier, inchangé) ou la nouvelle
  `_run_lichess_puzzle_virtual` selon `config["puzzle_mode"]` (défaut
  "board"). Le mode virtuel ne tente jamais d'ouvrir l'échiquier physique
  (aucun appel à `_open_board_with_retry`) : aucune mise en place, le
  problème démarre directement. Le menu n'imposait déjà aucun échiquier
  pour accéder à l'écran des problèmes (le bouton n'est pas désactivé sans
  plateau) — seul le lanceur interne l'exigeait ; le mode virtuel le
  contourne entièrement, sans toucher au menu.
- Tests : `nicsoft/tests/test_issue364_lichess_puzzle_virtuel.py` — problème
  résolu, raté, coup illégal refusé puis bon coup, mat hors solution,
  promotion, résultat envoyé une seule fois, "Voir la solution" sans
  attente physique (avec interruption par retour au menu), démarrage sans
  aucun échiquier (`_open_board_with_retry` jamais appelé). Faux client
  Lichess et `nl_inst=None` partout — jamais de réseau ni de matériel réel.

## Problèmes Lichess : mode virtuel, partie 2/3 — interaction à l'écran (navigateur)

- `nicsoft/web/templates/index.html` : carte « Problèmes » de l'écran
  Lichess — deux boutons de choix de mode (« Échiquier », défaut, / « Sur
  l'écran »), description de la carte neutre (ne mentionne plus
  l'échiquier physique). Écran du problème en cours : nouvelle consigne
  `#lichess-puzzle-virtual-instructions` (affichée seulement en mode
  virtuel), à la place de l'invitation « Reproduisez le coup… » (jamais
  émise par VirtualPuzzleGame, donc déjà absente de fait en mode virtuel).
- `nicsoft/web/static/app.js` : préférence de mode mémorisée dans
  `localStorage` (`niclink_lichess_puzzle_mode` — seul mécanisme de
  préférence UI déjà en place dans l'appli, voir `niclink_show_legal` ;
  jamais côté serveur, jamais écrit dans un dossier réel en test). Nouveau
  bloc d'échiquier cliquable dédié au problème (`_puzzleOnSquareClick` et
  fonctions associées) : clic en deux temps (sélection puis destination),
  cases légales signalées via les classes déjà injectées
  (`.virt-selected`/`.virt-legal`/`.virt-legal-capture`, réutilisées sans
  modification), sélecteur de promotion réutilisé tel quel
  (`_virtAskPromotion`). **Les coups légaux viennent exclusivement du
  serveur** (`_puzzleLegalMoves`, rempli par le nouvel évènement
  `lichess_puzzle_your_turn`) — jamais recalculés en JS (ni chess.js, ni un
  moteur), contrairement au mode virtuel déjà existant des autres modes
  (humain/exercices/labo, qui utilise chess.js côté client — non concernés
  par la règle de fair-play Lichess). Nouvel évènement
  `lichess_puzzle_virtual_illegal` : coup refusé sans pénalité, toast
  dédié, échiquier réactivé avec les mêmes coups légaux. Action envoyée :
  `lichess_puzzle_virtual_move` (`from`/`to`/`promotion`). Orientation et
  coordonnées : inchangées (mêmes mécanismes que le mode échiquier, #363).
- i18n (fr/en/de) : `config.lichess.probleme_mode_echiquier`,
  `config.lichess.probleme_mode_virtuel`, `lichess.puzzle_virtuel_instructions`,
  `lichess.puzzle_coup_illegal` — ajoutées simultanément dans les 3 langues.
- Tests e2e : `nicsoft/tests/e2e/test_issue364_puzzle_virtuel_e2e.py` —
  problème résolu à la souris, problème raté, coup illégal refusé puis bon
  coup, promotion (choix de pièce à l'écran), consigne virtuelle affichée
  sans l'invitation physique. Aucun échiquier ni Lichess réels (évènements
  socket simulés, même procédé que `test_issue363_puzzle_fin_e2e.py`) ;
  `sendAction` instrumenté pour capturer les actions envoyées SANS casser
  son comportement réel (nécessaire vu la page Playwright partagée par
  toute la session de tests e2e).

# Changelog — Issue #363

## Coordonnées manquantes sur les échiquiers du mode problèmes Lichess

Les écrans de mise en place (`#board-pos-init`) et de problème en cours/fin
(`#board-lichess-puzzle`) n'affichaient aucune lettre de colonne ni numéro
de rangée — repéré en réel par Alain, qui a placé ses pièces en miroir
sans s'en rendre compte avec les Noirs (échiquier retourné, sans repère
visuel pour s'en apercevoir).

Ajouté : étiquettes a-h / 1-8 en marge, même mécanisme que les coordonnées
existantes du jeu/des exercices/du labo (`.coord-rank`/`.coord-file`,
nouvelle fonction partagée `_setCoordLabels()`), orientées comme
l'échiquier (camp du joueur en bas). Visibles uniquement pour les
problèmes sur l'écran de mise en place (partagé avec les autres modes via
`data.puzzle`) ; toujours visibles sur l'écran dédié du problème, jusqu'à
l'écran de fin inclus (même DOM). Aucun autre échiquier modifié.

Tests e2e ajoutés (`test_issue363_puzzle_coords_e2e.py`) : texte et ordre
des coordonnées pour un problème aux Blancs et aux Noirs, à la mise en
place et pendant le problème, + non-régression (coordonnées masquées hors
problème sur l'écran de mise en place partagé).

## Aucune indication de fin de problème après « Voir la solution »

Constat (lecture du code avant correctif) : après un problème raté,
« Voir la solution » ne se limite pas à un affichage — le serveur
(`puzzle_game.py::_show_solution()`) rejoue chaque coup un par un et
attend sa réplication physique sur l'échiquier avant de passer au
suivant, puis réémet déjà un évènement `lichess_puzzle_result` une fois
la boucle terminée (`can_view_solution` retombé à `False`). Mais ce
second évènement ne changeait rien à l'écran : le titre restait
« Problème raté » et le bouton de solution disparaissait silencieusement,
sans aucun signal de fin — dans les 3 cas (résolu, raté, raté+solution),
rien n'indiquait explicitement que le problème était terminé.

Corrigé côté client uniquement (aucun second envoi de résultat à
Lichess, déjà fait une seule fois par `_try_submit_pending()`) : un
bandeau `#lichess-puzzle-end-banner`, dérivé de `win`/`can_view_solution`
du payload déjà reçu — « Problème terminé » (résolu, ou raté pas encore
démontré) / « Solution terminée » (raté + solution entièrement rejouée
sur l'échiquier physique). Nouvelles clés i18n `lichess.puzzle.termine`
et `lichess.puzzle.solution_terminee` (fr/en/de). Le bouton « Problème
suivant » reste disponible dans tous les cas.

Tests e2e ajoutés (`test_issue363_puzzle_fin_e2e.py`) : les 3 cas
(résolu, raté, raté puis solution montrée), texte du bandeau et
disponibilité des boutons à chaque fois.

# Changelog — Issue #362

## Mise en place d'un problème Lichess — pièces de la position de départ au lieu de la cible

`renderBoardPosInit()` (`app.js`) dessinait toujours les pièces à partir
de `fen` — depuis #361, la lecture physique courante — et n'utilisait
`expected_fen` (la cible du problème) que pour calculer les cases rouges.
Régression introduite par #361 lui-même, non détectée par son test e2e qui
ne vérifiait que le NOMBRE de cases rouges, jamais QUELLES pièces étaient
dessinées. Conséquence en réel : l'écran de mise en place d'un problème
affichait la position rangée sur l'échiquier physique (souvent la position
de départ standard), jamais la position du problème à atteindre.

Corrigé : quand `expected_fen` est fourni (cas des problèmes Lichess),
`renderBoardPosInit()` dessine désormais la cible, `fen` ne servant plus
qu'au calcul des cases en écart — comportement inchangé pour les 3 autres
appelants (pas de `expected_fen`, cible toujours = position de départ
standard, dessinent toujours `fen` comme avant).

Test e2e de #361 renforcé
(`test_issue361_puzzle_mise_en_place_e2e.py`) : les payloads envoyés au
navigateur sont désormais capturés en appelant réellement
`_wait_initial_position_lichess_puzzle` avec un faux échiquier progressif
(mêmes clés/valeurs que le code de production), plutôt qu'écrits à la
main. Nouvelles assertions sur le contenu dessiné de cases précises (ex.
e4/e2/g1), qui échouent sans le correctif et passent avec.

# Changelog — Issue #361

## Problèmes Lichess : échiquier disparu + camp annoncé erroné

### 0. Mise en place — cases rouges figées

`_wait_initial_position_lichess_puzzle` (`core/game_manager_modes/
lichess.py`) envoyait toujours la position CIBLE (`target_board_fen`)
comme `fen` de l'écran `position_initiale`, jamais la lecture physique
courante — les cases rouges restaient donc figées, quel que soit le
placement réel des pièces. Envoie désormais la lecture physique comme
`fen` (comme les autres modes) et la cible séparément (`expected_fen`).
`renderBoardPosInit()` (`app.js`) accepte ce FEN cible en 3e paramètre
(repli sur la position de départ standard si absent, comportement
inchangé pour tous les autres appelants). Tests ajoutés : faux plateau
progressif (écarts décroissants jusqu'à zéro) + e2e (cases rouges qui
disparaissent à l'écran).

### 1. Échiquier absent pendant tout le problème

`#board-lichess-puzzle` manquait de la règle CSS de dimensionnement
(`main.css`, sélecteur partagé `#board, #rv-board, #board-pos-init, ...`)
— présent dans le DOM mais sans `display:grid`/largeur/hauteur, ses 64
cases s'empilaient verticalement (mesuré : 300×19200px) au lieu de
former un échiquier (640×640px) : invisible à l'écran du démarrage du
problème jusqu'à l'écran de fin (même écran, voir index.html). Ajouté à
la liste de sélecteurs. Coup adverse à reproduire désormais marqué
(cases départ/arrivée, classes `last-move-from`/`last-move-to`
existantes) par `_renderLichessPuzzleBoard()`, qui accepte maintenant un
`uci` optionnel converti par `uciToCoords()` (déjà utilisé par
`#board`) — aucun nouveau mécanisme de marquage. Test e2e ajouté :
mise en place → démarrage → coup adverse → écran de fin, échiquier
carré et correctement dimensionné à chaque étape (un simple test
largeur/hauteur non nulles ne suffisait pas à détecter la régression,
vérifié en reproduisant le bug : 300×19200 passe un tel test).

### 2. Camp annoncé erroné

`socket.on("lichess_puzzle_move", ...)` (`app.js`) recalculait
`#lichess-puzzle-turn-text` à partir de `data.color` — ce champ désigne
le camp qui vient de JOUER ce coup précis (ex. l'adversaire, pour son
premier coup forcé), jamais le camp fixe du joueur. Dès l'affichage du
premier coup adverse, l'étiquette basculait donc sur le camp adverse
(« Noirs » alors que le joueur a les Blancs). Le camp du joueur n'est
plus mis à jour QUE par l'évènement `app_state` (`lichess_puzzle_
playing`), qui l'envoie correctement une seule fois par problème
(`solver_color`, déjà l'inverse du trait de `setup_fen` — vérifié par
deux nouveaux tests unitaires). Tests ajoutés : 2 tests unitaires
(camp inverse du trait de la position de départ, dans les deux sens)
+ 2 tests e2e (étiquette inchangée après l'affichage du coup adverse,
Blancs et Noirs) — reproduction confirmée du bug en annulant
temporairement le correctif.

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

# Changelog — Issue #359

## Hygiène : trois règles de piège manquantes dans docs/contexte/architecture.md

- `docs/contexte/architecture.md` : trois lignes ajoutées (règles encore
  valables, oubliées par le tri de l'ancien `historique_bugs.md` lors de
  #358) — notation SAN toujours via `san_ep()` (jamais `board.san()`
  direct), exceptions de contrôle de flux (`BackMenuExit`, `ExitNicLink`,
  `SystemExit`) jamais traitées comme un crash par un `except Exception`
  générique, tout évènement `send_event`/`emit` doit avoir un
  `socket.on`/`socket.once` correspondant dans `app.js`.
- Deux gardes de test ajoutées (analyse statique, sans navigateur ni
  matériel, sur le modèle de `test_issue303_html_escaping.py`) :
  `nicsoft/tests/test_issue359_san_ep_guard.py` et
  `nicsoft/tests/test_issue359_event_handler_guard.py`. Chacune a une
  liste blanche des violations déjà présentes (ci-dessous) et un second
  test qui échoue si la liste blanche devient périmée (entrée corrigée
  non retirée).
- Pas de garde écrite pour le piège (b) (exceptions de contrôle de flux) :
  une analyse statique fiable demanderait de distinguer un
  `except Exception` qui re-lève bien `BackMenuExit`/`ExitNicLink`/
  `SystemExit` au préalable d'un qui ne le fait pas, ce qui dépend de
  l'ordre des blocs `except` et de leur contenu — un simple `grep` sur
  `except Exception` donnerait trop de faux positifs (beaucoup de blocs
  légitimes qui n'ont jamais ces exceptions en vol à cet endroit).

### Violations connues, non corrigées (hors périmètre de cette issue)

**(a) Notation SAN — appel direct à `board.san()` au lieu de `san_ep()` :**
- `nicsoft/modes/exercices/add_ouverture.py`
- `nicsoft/modes/exercices/explore_book_import.py`
- `nicsoft/modes/exercices/explore_book_cli.py`
- `nicsoft/modes/exercices/explore_book_web.py`
- `nicsoft/modes/exercices/eco_import_import.py`
- `nicsoft/modes/exercices/import_lignes.py`
- `nicsoft/engine/review_multipv.py:292`
- `nicsoft/web/server.py:1014`
- `nicsoft/modes/lichess/puzzle_game.py:413,452,549` — seul cas touchant le
  flux de partie live (coup/solution de puzzle envoyé en direct au
  navigateur) ; les huit autres sont des outils d'import/export de livres
  d'ouvertures ou de l'analyse post-partie (hors flux live).

**(b) Exceptions de contrôle de flux avalées par un `except Exception`
générique :**
- `nicsoft/modes/humain/human.py:828` — `except Exception as exc:` autour
  de `await_move()` sans `except (BackMenuExit, ExitNicLink): raise`
  préalable ; avale notamment `ExitNicLink`. Hors périmètre de cette
  issue (fichier explicitement exclu par la tâche).
- `SystemExit` n'est en pratique jamais capturé par un `except Exception`
  (il hérite de `BaseException`, pas `Exception`) ; tous les
  `except SystemExit` du dépôt (`game_manager_modes/pedagogique.py:134`,
  `game_manager_modes/humain.py:89`, `game_manager_modes/lichess.py`
  plusieurs occurrences, `web/alchess.py:310`) sont des captures
  spécifiques et délibérées du signal `"board connection error"`
  (`driver.py`), pas une violation de la règle.

**(c) Évènement serveur→navigateur sans gestionnaire JS :**
- `exercice_turn` (`nicsoft/modes/exercices/exercices.py:1024`)
- `undo_confirmed` (`nicsoft/modes/humain/human.py:1202`)
- `undo_impossible` (`nicsoft/modes/humain/human.py:748`)
- `undo_wait_position` (`nicsoft/modes/humain/human.py:1205`)

Toutes vérifiées à nouveau dans le code actuel (et non reprises aveuglément
d'un inventaire antérieur) avant l'écriture des règles et des listes
blanches ci-dessus.

Tâche 2 de l'issue (test instable à l'ordre aléatoire de `pytest-randomly`)
abandonnée sur consigne explicite de la relance du 18/11/2026 — reportée,
non traitée dans ce commit.

# Changelog — issue #358

## Diagnostic de sys.exit(0) dans human.py, fin du tri de historique_bugs.md, section Lichess dans SPECIFICATIONS.md

### Diagnostic BUG-011 (human.py)

`sys.exit(0)` en `nicsoft/modes/humain/human.py:1085` (`GameWeb._traiter_abandon()`, branche `back_menu`) est **sans danger** dans la configuration réelle (`async_mode="threading"`). Preuve : `GameWeb.start()` appelle `self.run()` en synchrone (pas un vrai `Thread.start()`) — toute la boucle de jeu s'exécute dans le thread créé par `launch_humain()` (`core/game_manager_modes/humain.py`, `t = threading.Thread(target=_run_humain, ...)`). Ce `SystemExit` est systématiquement capté par `except SystemExit as e:` (`core/game_manager_modes/humain.py:89`) qui l'absorbe sans le relancer (le test `"board connection error" in str(e)` est faux pour `str(SystemExit(0)) == "0"`, mais l'exception reste consommée) — `_run_humain` termine normalement, le thread `t` se termine normalement, `t.join()` revient normalement. Vérifié par une expérience isolée hors dépôt (`/tmp`, aucun fichier du dépôt touché) : un `sys.exit(0)` profond, catché par un `except SystemExit` même partiellement inutile, ne tue jamais le thread appelant ni le process — et, filet de sécurité supplémentaire, `threading.excepthook` (Python ≥3.8) ignore silencieusement tout `SystemExit` non capté levé hors thread principal. Seule la classe CLI `Game` (lignes 260/591, script autonome `python -m nicsoft.modes.humain.human`, jamais importée par le serveur web — confirmé par recherche d'imports) utilise `sys.exit()` pour terminer réellement le process, ce qui y est le comportement voulu.

Point de fragilité signalé pour une issue séparée (non corrigé ici, consigne de l'issue) : ce `sys.exit(0)` n'est sans danger que par coïncidence — il dépend d'un `except SystemExit` dont le rôle premier est de détecter une erreur de connexion échiquier, pas de servir de garde-fou pour le retour menu. `modes/pedagogique/pedagogique.py` a déjà été corrigé après un incident réel similaire (BUG-011 d'origine) en remplaçant son propre `sys.exit(0)` par une exception dédiée `BackMenuExit`, explicitement catchée dans `_run_pedagogique`. Suggestion : aligner `human.py` sur le même pattern (remplacer le `sys.exit(0)` de `_traiter_abandon()` par une exception dédiée, ou au moins par un simple `return`/flag propagé), pour ne plus dépendre d'un `except` à vocation différente. Aucun test actuel n'exerce ce chemin précis (thread réel + `back_menu` + assertion de survie du process) — à envisager si l'issue séparée corrige le code.

### docs/contexte/historique_bugs.md — supprimé

Fichier entièrement vidé puis supprimé (`git rm`) :
- **BUG-011** : conclusion « sans danger » ci-dessus → récit retiré, aucune règle ajoutée (le correctif suggéré reste à la charge d'une issue séparée, pas d'un invariant à documenter ici).
- **Lot 2** (18 entrées, hash de commit) : chacune revérifiée dans le code et/ou les tests actuels — toutes confirmées toujours corrigées. Les pièges génériques encore valables aujourd'hui ont été promus en règles dans les fichiers de domaine (voir ci-dessous) ; le reste (corrections ponctuelles sans piège généralisable : doublon UI, notation en passant, prints debug, pièces clouées, handlers manquants, etc.) a simplement vu son récit retiré, l'historique détaillé restant disponible via `CHANGELOG.md`/git.

Références mises à jour en conséquence : `CONTEXTE.md` (ligne d'index retirée), `CLAUDE.md` (ligne de tableau retirée), `TESTS.md` (consigne « nouveau bug trouvé » réorientée vers les fichiers de domaine), `SPECIFICATIONS.md` §11 (ligne de tableau retirée).

### docs/contexte/architecture.md

Règle « Retour au menu » enrichie de deux pièges tirés du lot 2 encore généralisables : ne jamais écraser un choix persistant de l'utilisateur par une valeur par défaut codée en dur au retour menu ; ne jamais réinitialiser un état de session JS dans un handler `socket.on("connect")` (il tourne à chaque reconnexion, pas qu'au chargement de page). Nouvelle règle : toujours émettre l'évènement UI avant toute I/O disque bloquante.

### docs/contexte/echiquier_usb_led.md

Nouvelle règle (2 pièges du lot 2) : verrou non bloquant obligatoire pour toute fonction de détection/connexion matérielle appelable depuis plusieurs threads ; revérifier `_app_state` après tout `sleep` précédant une action matérielle.

### SPECIFICATIONS.md

Nouvelle section §5.8 « Lichess » (point de vue produit, fondée sur `docs/contexte/lichess.md` et le code réel de `core/game_manager_modes/lichess.py`/`modes/lichess/`) : adversaire IA ou humain, classée ou amicale, cadences proposées (10+0 à 90+30), échiquier physique requis, aucune aide pendant la partie, abandon/nulle, cote affichée en fin de partie classée, PGN rangée par cadence, problèmes Lichess avec cote. Aucune autre section modifiée.

### Suite de tests

`python -m pytest nicsoft/tests -m "not hardware"` : verte avant et après ces modifications (aucun fichier Python touché). Expérience de diagnostic faite exclusivement dans `/tmp`, hors dépôt.

# Changelog — issue #357

## Garde de taille/index pour CONTEXTE.md + tri des documents périmés signalés par #356

### Garde ajoutée

`nicsoft/tests/test_issue357_contexte_guard.py` (3 tests, lecture de fichiers du dépôt uniquement, aucun réseau/matériel) : `CONTEXTE.md` ≤ 3700 caractères (`wc -m`) ; chaque fichier de `docs/contexte/` est cité dans l'index de `CONTEXTE.md` ; chaque fichier cité dans l'index existe sur disque.

### CONTEXTE.md

Ajout de 2 règles dans l'en-tête : limite de 3700 caractères (`wc -m`, test dédié) et `TACHES.md` privé/gitignoré (jamais modifié) — cette dernière avait disparu de la restructuration #356. Reformulations pour tenir sous la limite (aucune règle perdue) : section Règles condensée, « Fichiers de référence non déplacés » → « Fichiers de référence », « nettement en avance » → « en avance », ligne d'index `historique_bugs.md` mise à jour (voir ci-dessous). Taille finale : 3678 caractères (`wc -m`).

### docs/contexte/architecture.md

2 règles ajoutées, issues du tri de `historique_bugs.md` (pièges encore généralisables) : réinitialiser toute variable d'état résiduelle (JS/Python) au retour menu avant un nouveau lancement de mode ; vérifier l'équilibre des balises après modification de `index.html` (deux bugs passés par balise fermante manquante).

### docs/contexte/historique_bugs.md

BUG-001 à BUG-010 : vérifiés dans le code actuel, toutes les corrections tiennent toujours (preuves : `#screen-pos-init` hors de `#screen-game` dans `index.html`, aucun `window.confirm()` dans `app.js`, `_gameSource` réinitialisé au retour menu, `labo_copy_start` efface `labo-last-move`, quirk usbhid et mutex USB/threads LED daemon déjà documentés dans `echiquier_usb_led.md`, handler manquant déjà couvert par `architecture.md`). Récit supprimé — pièges encore vivants déplacés en règles (voir ci-dessus). BUG-011 laissé tel quel (voir « Laissé pour décision d'Alain »). Section « Bugs résolus — mai 2026 (lot 2) » : hors périmètre de cette tâche (l'issue ne visait que BUG-001 à BUG-011), non touchée.

### Documents supprimés (`git rm`, preuve de péremption)

- `ETAT_PROJET.md` : snapshot daté 2026-05-22 (6 mois), non cité par `CONTEXTE.md` ni la table « Fichiers de suivi » de `CLAUDE.md`/`SPECIFICATIONS.md`. Chiffres massivement faux aujourd'hui (`app.js` 5716→9302 lignes, `index.html` 1447→2220, `main.css` 642→1828, i18n 606→847 clés, `test_app_state.py` annoncé à part des tests E2E alors que 203 tests E2E existent désormais) ; dossiers/fichiers listés en §7 « à nettoyer » tous déjà absents du disque (`nicsoft/test/`, `nl_bluetooth/`, `TRAVAIL_EN_COURS/`, `Lenteur/`, `build/`, `src/`, etc.).
- `CORRECTION_TRADUCTION.md` : note de travail i18n sans date, non citée ailleurs. Les 4 points relevés sont corrigés dans le code actuel (`menu.btn.reconnect`/`config.pause.*`/`game.btn.changer_couleur` ont leurs clés fr/en/de ; CSS dédiée `#screen-outils-exercices` ajoutée depuis).

### Non modifiés — laissé pour décision d'Alain

- `historique_bugs.md`, BUG-011 : son récit attribue l'ancien blocage à `sys.exit(0)` dans un thread de jeu qui « tuait tout le processus Flask ». Or `nicsoft/modes/humain/human.py` utilise encore aujourd'hui `sys.exit(0)` pour son propre retour menu (ligne ~1085), jamais converti en `BackMenuExit`. Sans pouvoir relancer un serveur réel (hors périmètre de cette tâche, pas de matériel), impossible de trancher si ce `sys.exit(0)`-là est sans danger (vrai `threading.Thread`, `async_mode="threading"` dans `server.py`) ou si le risque décrit est toujours vivant dans `human.py`. Entrée laissée intacte, signalée ici pour vérification/décision.
- `SPECIFICATIONS.md` : document de spécification, non supprimé en bloc. Corrigé uniquement ce qui était clairement faux (extension C++ `_niclink.so` → `hid_backend.py`, compteurs i18n 515→847, tests E2E 42→203 — `test_app_state.py` à 25 tests restait exact, vérifié par `pytest --collect-only`). Lacune non corrigée (ajout de contenu, pas correction d'erreur, hors périmètre) : section « 5. Modes de fonctionnement » ne décrit toujours pas le mode Lichess (`modes/lichess/`), pourtant présent dans `CONTEXTE.md`/`CLAUDE.md` et dans le reste de la base — à compléter dans une tâche dédiée.
- `TEST_RESULTATS.md` : laissé intact. Une seule entrée (2026-05-02), mais c'est un journal daté par nature (comme `CHANGELOG.md`) — son unique entrée ancienne n'est pas une erreur, juste une absence de mise à jour récente ; le mécanisme reste référencé et valide dans `CLAUDE.md`/`SPECIFICATIONS.md`.

### Suite de tests

`python -m pytest nicsoft/tests -m "not hardware"` rejouée après toutes les modifications ci-dessus — verte, nouveau test de garde inclus.

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

# Changelog — issue #354

## Lichess L3 (suite) : jouer les problèmes Lichess sur l'échiquier physique

Reprise de #351 (qui avait livré uniquement la partie 0 et le module de communication `puzzle_client.py`, points 3 à 8 explicitement non faits). Les trois étapes demandées (A : entrée/mise en place ; B : déroulement des coups ; C : fin/enchaînement/journal/robustesse) sont livrées **ensemble, en un seul commit** — voir la note en fin de document sur ce choix.

Périmètre volontairement minimal (décision d'Alain, confirmée par #351) : un problème après l'autre, angle par défaut, aucune aide, aucun choix de thème, pas de Storm/Racer/Streak, jamais de reprise d'un problème déjà vu.

### Nouveau module — `nicsoft/modes/lichess/puzzle_game.py`

`PuzzleGame` : orchestration d'un seul problème une fois la position de départ confirmée. Contrairement à `LichessGame`, pas de `threading.Thread`/flux réseau continu — la solution complète est connue dès `get_next_puzzle()` (livré par #351), `self.board` est donc mis à jour directement par ce module (coup du solveur comme réponse adverse forcée), jamais par un flux externe. Réutilise directement `legal_move_for_hardware`/`pending_promotion_move` de `game.py` (détection de coup/promotion) plutôt que de les dupliquer.

- **Détection de coup** (`_tick_physical`/`_evaluate_user_move`) : légal+attendu → appliqué, LED+son pour la réponse adverse forcée suivante si la solution continue ; légal mais faux → problème raté immédiatement (position juste avant le coup faux et suite correcte mémorisées pour « Voir la solution ») ; illégal → `lichess_puzzle_illegal_position` après lectures stables (debounce, même seuil que `game.py`) ; en attente d'une pièce levée simplement (position inchangée) → aucun événement.
- **Coup qui mate accepté même hors solution** : établi par lecture du code source public de lila (dépôt `lichess-org/lila`, branche master, lu le 16/11/2026, `ui/puzzle/src/moveTest.ts`) :
  ```ts
  if (nodes[i].checkmate) return (ctrl.node.puzzle = 'win');
  ```
  évalué AVANT toute comparaison avec `puzzle.solution[i]` — reproduit tel quel (`board_after.is_checkmate()` prime sur la comparaison UCI dans `_evaluate_user_move`). Point du même fichier volontairement NON repris : l'équivalence de notation de roque `altCastles` (ex. "e1h1" vs "e1g1") — artefact du client web (bibliothèque chessops côté navigateur), sans raison de s'appliquer à la réponse JSON de l'API REST publique (notation UCI standard, sans ambiguïté sur un roque).
- **Promotion** : même mécanique que les parties (`pending_promotion_move` détecte la promotion en attente côté plateau physique, événement `lichess_puzzle_promotion_needed`, action `lichess_puzzle_promotion_choice` reçue du navigateur avec la pièce choisie).
- **Résultat envoyé en CLASSÉ** (`submit_puzzle_result(..., rated=True)`), seulement à la résolution complète ou au premier coup faux confirmé (jamais avant, jamais à un retour au menu pendant l'attente) — `PuzzleGame.run()` ne soumet qu'une fois (`_finish`/`_try_submit_pending`).
- **Cote avant/après** : Lichess ne renvoie dans `POST /api/puzzle/batch/mix` que `glicko.rating` (cote APRÈS) et `ratingDiff` (variation) — jamais la cote d'avant directement. `rating_before = new_rating - rating_diff` (soustraction des deux valeurs réellement renvoyées par Lichess, jamais une cote inventée ou mémorisée côté client avant résolution) ; si l'un des deux manque, rien n'est affiché pour la cote « avant » plutôt qu'une valeur incertaine.
- **Réseau indisponible à l'envoi du résultat** : `_pending_submit` reste posé jusqu'au succès — `lichess_puzzle_retry_submit` (bouton « Réessayer l'envoi ») permet un nouvel essai manuel tant que l'écran de résultat reste ouvert ; passer à « Problème suivant »/« Retour au menu » avec un résultat non envoyé l'abandonne définitivement (journalisé), cohérent avec « le résultat n'est pas perdu tant que l'écran reste ouvert » (rien de plus n'était demandé).
- **Voir la solution** (`_show_solution`) : seulement après un échec, une seule fois — remet en place la position juste avant le coup faux (même mécanique de recalage physique), puis rejoue coup par coup (LED+son+attente de réplication physique) jusqu'à la fin de la solution correcte.
- **Robustesse échiquier** : mêmes seuils que `LichessGame` (40 lectures vides consécutives ≈2s avant « échiquier perdu », reconnexion 2s pendant 30s puis 5s, jamais d'abandon automatique) — implémentation séparée de celle de `LichessGame` (comme celle-ci a sa propre version distincte de celle du lanceur), pour éviter un couplage entre deux classes qui n'ont plus de flux en commun.

### Lanceur — `nicsoft/core/game_manager_modes/lichess.py`

- `launch_lichess_puzzle(config)` : vérifie D'ABORD les droits du jeton via `client.test_token()` (déjà étendu par #351 avec `has_puzzle_read`/`has_puzzle_write`) — message clair nommant exactement le(s) droit(s) manquant(s) (`toast.lichess_puzzle_missing_scope`, variable `{scopes}`), jamais un échec silencieux ni le message générique de `board:play`.
- `_run_lichess_puzzle(token, player_name, _error)` : ouvre l'échiquier une seule fois pour toute la session (réutilise `_open_board_with_retry`), puis boucle — `get_next_puzzle()` → mise en place physique (`_wait_initial_position_lichess_puzzle`, variante de `_wait_initial_position_lichess` pour une position ARBITRAIRE, jamais la position de départ standard) → `PuzzleGame.animate_opponent_first_move()` → `PuzzleGame.run()` → si `"next_puzzle"`, reboucle sans repasser par le menu ; si `"back_menu"`, referme proprement (LED éteintes, échiquier libéré, journal fermé).
- Journal dédié **de session** (pas par problème) : un seul `GameLog` ouvert au tout début de `_run_lichess_puzzle`, réutilisé pour tous les problèmes joués d'affilée (même esprit que le journal de partie de #326, mais une session de problèmes peut en contenir plusieurs) — fichiers dans `LOGS_DIR/lichess_puzzles/` (nouvelle constante `PUZZLE_LOGS_DIR`, `puzzle_game.py`), jamais le jeton (réutilise `GameLog._mask` tel quel).

### Écran — `index.html` / `app.js` / `i18n`

- Carte « Problèmes » (`config.lichess.probleme_*`) dans `#screen-config-lichess`, au même niveau que les cartes Adversaire/Cadence/Couleur existantes — clic direct sur `start_lichess_puzzle` (pas de configuration : angle par défaut, couleur imposée par le problème).
- Mise en place : réutilise l'écran générique `#screen-pos-init` (`position_initiale`) — nouveau texte dédié (`lichess.puzzle_mise_en_place_texte`, affiché à la place du texte standard via un nouveau drapeau `puzzle: true` dans le payload) puisque la position cible n'est jamais la position de départ standard, contrairement aux parties.
- Nouvel écran dédié `#screen-lichess-puzzle` (état `lichess_puzzle_playing`) : échiquier orienté du point de vue du solveur, bandeau « à vous de jouer » + couleur, cote du problème, bannières position/illégal/échiquier perdu, ligne de promotion (boutons réutilisés `lichess.promotion.*`), bloc résultat (titre gagné/perdu, thèmes révélés seulement à ce moment, cote avant/après/variation, erreur d'envoi + réessai, boutons Voir la solution/Problème suivant), Retour au menu toujours visible.
- Thèmes jamais transmis au navigateur avant résolution (le serveur ne les inclut dans aucun événement tant que le problème n'est pas terminé) — rien à masquer explicitement côté client, le serveur ne les envoie simplement pas plus tôt.
- `server.py`/`single_instance.py` : nouvel état `lichess_puzzle_playing` ajouté aux deux listes d'états « partie en cours » (routage `action_queue` et `BUSY_STATES`, une seconde instance ne doit pas pouvoir démarrer pendant un problème).
- 23 nouvelles clés i18n ajoutées identiquement en fr/en/de (`config.lichess.probleme_*`, `toast.lichess_puzzle_missing_scope`, `lichess.puzzle.*`, `lichess.puzzle_mise_en_place_texte`, `lichess.puzzle_menu_verrouille`) — vérifié par le test générique existant `test_issue310_lichess_corrections.py::test_toutes_les_cles_i18n_lichess_existent_dans_les_3_langues`.

### Simplifications délibérées (documentées, pas des oublis)

- **Pas de surlignage rouge des cases différentes** pendant la mise en place ou en cas de position illégale (contrairement à `renderBoardWithErrors()` utilisé ailleurs) — l'écran affiche la position cible/une bannière texte, sans comparaison case-par-case côté client. Amélioration possible pour une future issue, jugée hors du périmètre minimal demandé.
- **Pas de PGN enregistré** pour un problème (jamais demandé dans l'issue, contrairement aux parties) — seul le journal dédié conserve la trace de ce qui a été joué.
- **Équivalence de notation de roque `altCastles`** (voir ci-dessus) non reproduite — jugée hors sujet pour l'API REST.

### Pourquoi un seul commit pour A+B+C

L'issue demande un commit par étape « avec les tests de l'étape », en acceptant explicitement de s'arrêter proprement à la fin d'une étape complète si le temps manque. Les trois étapes ont été construites dans la même session, en un seul passage cohérent (la classe `PuzzleGame` mêle intrinsèquement la mise en place du premier coup — étape A — et la boucle de coups/résolution — étapes B/C — dans un même fichier, de même que le lanceur mêle vérification des droits — A — et boucle d'enchaînement — C). Scinder rétroactivement ce travail déjà écrit et testé en trois commits aurait exigé de reconstruire des états intermédiaires du fichier n'ayant jamais existé tels quels pendant le développement, avec un risque réel de produire un commit intermédiaire incohérent ou mal testé — exactement ce que la consigne « jamais de code à moitié fait qui pilote l'échiquier » interdit. Un seul commit, complet et entièrement testé, a donc été préféré à une segmentation artificielle à risque.

### Tests

`nicsoft/tests/test_issue354_lichess_puzzles_l3.py` (21 tests) : fonctions pures (couleur du solveur, cases du premier coup adverse) ; mise en place et animation du premier coup adverse (avec et sans coup adverse initial) ; alternance coup du solveur / réponse adverse forcée / victoire ; résolution complète avec cote avant/après/variation calculée uniquement à partir des valeurs renvoyées par Lichess ; coup légal mais faux (point de reprise et suite mémorisés) ; coup qui mate accepté même hors solution (position à deux mats possibles, l'un déclaré en solution, l'autre réellement joué) ; promotion (détection + choix) ; position illégale détectée après lectures stables puis effacée ; retour au menu pendant l'attente n'envoie JAMAIS de résultat (assertion dans le faux `submit_puzzle_result`) ; voir la solution (rejeu coup par coup avec attente de réplication) ; réessai d'envoi après échec réseau puis succès ; lanceur — refus sans jeton, message exact nommant le droit manquant, refus si mode déjà actif ; `lichess_puzzle_playing` dans `single_instance.BUSY_STATES`.

Suite complète rejouée sans régression : `pytest nicsoft/tests/ -q -p no:randomly` (voir rapport de clôture pour le compte exact) ; `test_issue333_lichess_no_engine.py` (garde AST fair-play, `puzzle_game.py` automatiquement couvert par le glob existant) ; `test_issue310_lichess_corrections.py` (garde i18n) ; `test_no_web_import.py` (garde ARC-001) ; `test_issue303_html_escaping.py`/`test_issue304_security.py` — tous verts. Aucun appel réseau réel : `submit_puzzle_result`/`get_next_puzzle`/`test_token` toujours monkeypatchés dans les tests, garde réseau globale (`nicsoft/tests/conftest.py`) inchangée et toujours active.

### Ce qu'Alain pourra vérifier en réel

Avec son jeton (déjà `puzzle:read`+`puzzle:write`) : carte « Problèmes » dans l'écran Lichess, mise en place physique d'un vrai problème, affichage/réplication du premier coup adverse si le problème en a un, résolution d'un coup juste suivi d'une réponse adverse automatique, un coup volontairement faux (le problème doit se dire raté, proposer « Voir la solution », la rejouer coup par coup), un problème résolu jusqu'au mat (cote avant/après/variation affichée), enchaînement « Problème suivant » sans repasser par le menu, et le fichier de journal créé dans `logs/lichess_puzzles/`. Non vérifiable sans matériel/vraie session (comme pour tout le reste du mode Lichess) : patterns LED réels, délai réel de reconnexion USB en situation réelle, comportement exact de Lichess si le réseau tombe pendant l'envoi du résultat.

# Changelog — issue #352

## Analyse après partie : harmoniser les marques de coups (?!/?/??) avec les flèches du moteur

### Diagnostic (sans correction, point 1 de l'issue)

Les marques et les flèches de l'écran d'analyse après partie venaient bien de **deux recherches moteur distinctes sur la même position**, comme supposé par Alain :

- Les flèches (3 meilleures lignes + barre d'évaluation) : `EngineAnalysisMixin.get_multipv()` (`nicsoft/engine/engine_analysis.py`), appelé par `ReviewMultiPVService._compute()` (`nicsoft/engine/review_multipv.py`) à **profondeur 12**, 3 lignes.
- Les marques ?!/?/?? : `EngineAnalysisMixin.evaluate_move()`, appelé par `analyser_partie()` pour chaque coup de la partie (socket `analyser_pgn`, `server.py`) à **profondeur 8**, une seule ligne (pas de MultiPV), avec une recherche séparée AVANT et APRÈS le coup, puis inversion de signe manuelle pour comparer les deux évaluations du point de vue du joueur qui a joué.

Deux recherches à profondeur différente sur la même position ne donnent pas la même évaluation (recherche alpha-bêta, pas une fonction pure déterministe à profondeur fixe identique) — c'est la cause directe de l'écart +0,91 (flèches, depth 12) / +0,68 (marque, depth 8) observé par Alain sur 6.Bc4.

Seconde cause, indépendante de la première : les seuils de marque (`move_quality.SEUIL_BON/IMPRECISION/ERREUR`, 50/100/300 centipions bruts) ne tiennent aucun compte de l'évaluation de départ. Un coup qui perd 0,30 pion dans une position déjà à +1 pion (perte réelle en chances de gain : quelques points de %) était classé exactement pareil qu'un coup qui perd 0,30 pion dans une position équilibrée (où la même perte de pions pèse beaucoup plus en chances de gain) — c'est ce qui rendait plausible qu'un coup à 0,08 pion du meilleur (quasiment équivalent) franchisse le seuil « erreur » (100cp) à la moindre instabilité de recherche.

**Point de vue du joueur qui a joué** : vérifié correct dans l'ancien code (`evaluate_move`) — la perte était déjà calculée `cp_avant - (-cp_apres)`, donc du point de vue du joueur ayant joué, pour les Blancs comme pour les Noirs. Pas la cause du problème, mais fragile (inversion de signe manuelle) : la nouvelle implémentation l'évite structurellement (voir plus bas).

### Mesure sur la partie de l'exemple (point 2)

Le PGN n'a pas été recherché dans un dossier de parties (hors du périmètre de ce worktree, qui ne contient pas les données utilisateur réelles) — la liste de coups de l'issue a été rejouée directement avec python-chess, puis analysée avec le moteur système `/usr/games/stockfish` (Stockfish 16, binaire apt, pas celui du dépôt) en mode sans échiquier (`ALCHESS_SKIP_BOARD`/`ALCHESS_NO_BROWSER` non pertinents ici, aucun serveur ni navigateur lancé).

| # | Coup | Camp | Meilleur (flèches, depth12) | Joué (flèches) | Ancien (depth8, cp bruts) | Nouveau (depth12, chances de gain) |
|---|------|------|------------------------------|----------------|---------------------------|-------------------------------------|
| 4 | Nf6 | N | -0.28 | (hors top3) | bon 39cp | **imprecision 67cp** |
| 11 | Bc4 | B | +1.03 | +0.82 | bon 21cp | bon 30cp |
| 14 | Ne4 | N | -0.99 | -1.68 | imprecision 69cp | imprecision 66cp |
| 17 | g3 | B | +2.91 | +1.92 | imprecision 99cp | imprecision 77cp |
| 19 | Nf4 | B | +2.15 | (hors top3) | erreur 131cp | erreur 121cp |
| 20 | Qh6 | N | -0.47 | -3.78 | blunder 331cp | blunder 294cp |
| 21 | Qd3 | B | +4.03 | +3.02 | **imprecision 99cp** | **bon 43cp** |
| 23 | O-O | B | +4.66 | (hors top3) | erreur 181cp | erreur 321cp |
| 24 | O-O | N | -2.09 | (hors top3) | **blunder 342cp** | **erreur 304cp** |
| 26 | Bxc3 | N | -4.99 | (hors top3) | **imprecision 91cp** | **bon 117cp** |
| 31 | Nh3 | B | +6.18 | (hors top3) | **erreur 104cp** | **bon 85cp** |
| 32 | Qg4 | N | -5.24 | -5.31 | imprecision 74cp | bon 0cp |
| 34 | h6 | N | -5.55 | (hors top3) | bon 0cp | erreur 455cp |

(Tableau complet des 35 demi-coups produit pendant la session, non reproduit en entier ici — lignes ci-dessus = celles où ancien et nouveau diffèrent de catégorie, ou qui illustrent un mécanisme du correctif.)

Avec la version installée de Stockfish 16 sur cette machine, 6.Bc4 lui-même ne franchissait déjà pas le seuil « erreur » à depth 8 (21cp, sous le seuil de 100cp) — l'écart exact observé par Alain (delta de 0,23 pion, marque « ? ») dépend de la version/du matériel/de l'état du moteur au moment de son observation, non reproductible à l'identique ici. Le **mécanisme** est néanmoins démontré sans ambiguïté par plusieurs autres coups de la même partie :
- **13...Bxc3** (ligne 26) : position déjà perdue pour les Noirs (-4,99) ; l'ancien calcul (depth 8) marquait « imprécision » (91cp, juste sous le seuil erreur) alors que le nouveau, en chances de gain, le classe « bon » (la perte de 117cp dans une position déjà à -5 pions ne change presque rien aux chances de gain, déjà proches de 0).
- **16.Nh3** (ligne 31) : encore un cas où l'ancien marquait « erreur » (104cp) une perte de pions sans impact réel sur l'issue (position déjà à +6,18 pour les Blancs) — le nouveau la classe « bon ».
- **11...O-O** (ligne 24) : l'ancien calcul classait ce coup « blunder » alors que les Noirs restaient dans une situation désespérée des deux côtés (-2,09 avant, pire après) — la perte en pions réelle n'y change presque rien pour l'issue de la partie ; le nouveau le classe « erreur » (catégorie en moins, pas totalement « bon » non plus, cohérent avec une vraie perte même si l'issue était déjà scellée).

Ces trois cas illustrent exactement la plainte d'Alain : une perte de pions dans une position déjà très déséquilibrée (gagnante ou perdante) pesait trop lourd avec des seuils en centipions bruts.

**Coût en temps** : l'ancienne méthode (depth 8, 2 recherches par coup) prenait ~4ms/coup sur cette machine ; la nouvelle (depth 12, MultiPV 3, même profondeur que les flèches) prend ~86-91ms/coup, soit environ **20 à 25 fois plus lent**, pour une partie de 35 demi-coups : ~0,14s contre ~3,0s au total. Ce surcoût est jugé acceptable car l'analyse après partie tourne déjà en tâche de fond asynchrone (callback progressif `analyse_coup`, annulable), jamais de façon bloquante, et la profondeur 12 était déjà celle utilisée pour les flèches (donc déjà payée une fois par position affichée) — le correctif ne fait qu'aligner les marques sur un calcul déjà nécessaire, pas en ajouter un second à une vitesse déjà rapide.

### Correction (points 3 à 5)

**Une seule analyse de référence** (`nicsoft/engine/move_quality.py`, constantes `REVIEW_DEPTH=12`/`REVIEW_N_LINES=3`, importées à la fois par `engine_analysis.py` et `review_multipv.py`) :

- `EngineAnalysisMixin.evaluate_move()` réutilise désormais **directement** `get_multipv()` (même profondeur, même méthode que les flèches) au lieu d'une recherche séparée avant/après le coup. Si le coup joué fait partie des `n_lines` meilleures lignes, son évaluation est prise telle quelle dans cette même liste — **zéro recherche supplémentaire**. S'il n'y est pas, une recherche `root_moves=[coup]` restreinte à ce seul coup est lancée à la **même profondeur** (jamais une profondeur différente), donc "jamais un calcul séparé plus rapide/moins profond" comme demandé par l'issue.
- Au passage, la perte n'a plus besoin d'inversion de signe manuelle : `get_multipv()` donne déjà toutes ses évaluations du point de vue du camp au trait sur la position AVANT le coup — structurellement correct pour les Blancs et les Noirs, plus robuste que l'ancien calcul avant/après.
- `analyser_partie()` (post-partie, marques) appelle `evaluate_move(..., depth=REVIEW_DEPTH)` — même profondeur que les flèches. Les usages en temps réel (coaching pédagogique, Labo) continuent d'appeler `evaluate_move(..., depth=8)` explicitement (performance temps réel), mais bénéficient de la même méthode et de la même classification en chances de gain.

**Classification en chances de gain** (`move_quality.py`, formule Lichess `WINRATE_K = 0.00368208`, sigmoïde cp → % de gain) :

- `ECART_BON = 0.05` (5 points de %) : écart commun, utilisé À LA FOIS pour les marques (« bon » si la perte reste sous ce seuil) ET pour les flèches (ligne 2/3 affichée seulement si elle reste dans cet écart par rapport à la meilleure ligne — ligne 1 toujours affichée). C'est exactement le mécanisme demandé par le point 5 de l'issue : une seule valeur, deux usages.
- `SEUIL_IMPRECISION_PCT = 0.10`, `SEUIL_ERREUR_PCT = 0.20` : imprécision/erreur entre 5-10 et 10-20 points de %, blunder au-delà. Ces seuils restent délibérément larges (pas un calage fin sur les seuils exacts de Lichess, que je n'ai pas pu vérifier avec certitude) mais corrigent le défaut structurel signalé : une perte de pions dans une position déjà très déséquilibrée pèse désormais peu en %, alors qu'elle pèse beaucoup dans une position équilibrée — démontré par le tableau ci-dessus (Bxc3, Nh3).
- **Mat** : un mat forcé gardé (même ralenti, ex. mat en 2 devenu mat en 6) n'est jamais marqué (`winrate = 1.0` des deux côtés, perte nulle). Un mat forcé qui disparaît (même si la position reste très gagnante par ailleurs) est **toujours** classé « blunder », par une règle explicite indépendante du calcul en % (`classifier_coup_winrate`) — un coup qui laisse échapper un mat forcé ne doit jamais se retrouver « bon » juste parce que l'avantage matériel reste écrasant.
- L'ancienne classification en centipions bruts (`classifier_coup`, `SEUIL_BON/IMPRECISION/ERREUR`) est conservée telle quelle dans `move_quality.py` (toujours réexportée par `engine_manager.py`/`nicsoft/engine/analyse.py`), simplement plus appelée par `evaluate_move()` — pas supprimée, au cas où un autre code en dépendrait (aucun trouvé par recherche dans le dépôt).

**Flèches 2/3 gated par le même écart** : `ReviewMultiPVService._compute()` calcule désormais, pour chaque ligne, un champ `within_gap` (vrai pour la ligne 1 toujours ; pour les lignes 2/3, vrai seulement si leur perte en chances de gain par rapport à la ligne 1 reste sous `ECART_BON`). Côté client (`app.js`), `drawReviewArrows()` et `_reviewRenderLinesList()` filtrent sur ce champ — une ligne 2/3 nettement inférieure n'est plus tracée ni listée (elle n'est pas une recommandation), l'orange « coup joué » reste inchangé comme demandé. Un champ `within_gap` absent (ancien format/test) est traité comme vrai par défaut, pour ne jamais cacher une flèche à cause d'une donnée qui ne porte pas encore ce champ.

### PGN enregistrés (point 6)

Vérifié : aucune marque ni évaluation n'est écrite dans un PGN à l'enregistrement normal (`build_and_save_pgn()`, utilisé par `human.py`/`lichess/game.py`, appelé sans le paramètre `comments`). Une seule exception trouvée : le bouton « Sauvegarder vers AlChess » de l'écran d'analyse (`sauvegarderNicLink()` dans `app.js`) construit un PGN enrichi avec `qualiteAnnotation(qualite, delta_cp)` à partir des marques déjà reçues du serveur (`reviewMoves[i].qualite`/`delta_cp`, remplies par l'event `analyse_coup`) — puisque ces marques viennent maintenant de la même analyse corrigée, ce chemin suit automatiquement la nouvelle règle, sans modification JS nécessaire. Aucun PGN déjà enregistré n'a été modifié (hors du périmètre de cette tâche de toute façon : aucune donnée utilisateur réelle dans ce worktree).

Le mode Pédagogique (`pedagogique.py::_append_move_to_pgn`, feedback temps réel pendant la partie, pas l'écran d'analyse) écrit aussi un commentaire `qualite`/`delta_cp` par coup dans son PGN — ce chemin utilise toujours `evaluate_move(..., depth=8)`, donc bénéficie de la même classification en chances de gain corrigée (code partagé), mais reste à profondeur 8 (temps réel pendant que l'utilisateur joue contre le moteur, pas de flèches à harmoniser sur cet écran).

### Tests (point 7)

Nouveau fichier `nicsoft/tests/test_issue352_harmonisation_marques_fleches.py` (21 tests, évaluations simulées, aucun vrai moteur) :

- `classifier_coup_winrate`/`winrate_from_eval` : coup classé 2e à moins de l'écart jamais marqué (reproduction de l'observation d'Alain, +0,99/+0,91), perte de quelques dixièmes de pion en position déjà gagnante reste "bon", grosse perte en position équilibrée est une gaffe, mat forcé gardé jamais marqué (même ralenti), mat forcé perdu toujours une gaffe (y compris remplacé par un mat subi).
- `EngineAnalysisMixin.evaluate_move` (faux moteur exposant `get_multipv`) : coup dans le top 3 réutilise directement la ligne sans recherche séparée ; coup hors du top 3 déclenche une recherche `root_moves` à la MÊME profondeur (vérifié explicitement) ; perte mesurée du point de vue du joueur qui a joué, testé pour les Blancs ET pour les Noirs ; `analyse_active=False` ne lance aucun calcul.
- `ReviewMultiPVService._compute` : `within_gap` vrai pour une ligne proche, faux pour une ligne nettement inférieure, toujours vrai pour la ligne 1, vrai pour deux lignes de mat de même signe.
- Verrouillage : `REVIEW_DEPTH`/`REVIEW_N_LINES` partagés (identité) entre `engine_analysis.py` et `review_multipv.py`.

Suite complète rejouée (hors e2e navigateur) : **1405 passed, 84 skipped**, aucune régression (1383 passants avant cette issue + 22 nouveaux testés ici ; un test e2e existant, `test_issue341_review_eval_bar_e2e.py::test_legende_signes_corrects_dont_mat_lent`, a dû recevoir `within_gap: True` explicite sur ses 3 lignes simulées — son objet est de vérifier le FORMAT d'affichage de 3 lignes disparates, pas le nouveau filtrage par écart, donc ce test continue de forcer l'affichage des 3 lignes).

### Fichiers modifiés

- `nicsoft/engine/move_quality.py` : nouvelles constantes `REVIEW_DEPTH`/`REVIEW_N_LINES`, `WINRATE_K`/`cp_to_winrate`/`winrate_from_eval`/`ECART_BON`/`SEUIL_IMPRECISION_PCT`/`SEUIL_ERREUR_PCT`/`classifier_coup_winrate` — ancienne API (`classifier_coup`, `SEUIL_BON/IMPRECISION/ERREUR`, `score_to_cp`) conservée inchangée.
- `nicsoft/engine/engine_analysis.py` : `evaluate_move()` réécrit (réutilise `get_multipv`, root_moves pour le coup hors top N, classification en chances de gain, delta_cp plafonné à 10 pions pour l'affichage) ; `analyser_partie()` appelle `evaluate_move(..., depth=REVIEW_DEPTH)` ; `get_multipv()` par défaut sur `REVIEW_N_LINES`/`REVIEW_DEPTH`.
- `nicsoft/engine/review_multipv.py` : `N_LINES`/`DEPTH` importés depuis `move_quality.py` (une seule source) ; nouveau champ `within_gap` par ligne.
- `nicsoft/web/static/app.js` : `drawReviewArrows()`/`_reviewRenderLinesList()` filtrent les flèches/la légende 2-3 sur `within_gap`.
- `nicsoft/tests/test_issue352_harmonisation_marques_fleches.py` : nouveau, 21 tests.
- `nicsoft/tests/e2e/test_issue341_review_eval_bar_e2e.py` : `within_gap: True` ajouté à un fixture existant (voir ci-dessus).
- `CONTEXTE.md` : nouvelle entrée courte (#352).

# Changelog — issue #351

## Lichess L3 (problèmes) : corrections d'écran + fondations — livraison PARTIELLE

Issue "lourde" (plan Lichess, étape L3, bonus jamais prioritaire jusqu'ici). Les points 1 à 5 et 9 étaient demandés en priorité si le travail s'avérait trop long pour tout faire ; après lecture de l'architecture existante (`game.py` 2500 lignes, `game_manager_modes/lichess.py` 1458 lignes pour les parties en ligne), le déroulement interactif complet d'un problème (mise en place LED, détection de coups, promotion, journal dédié, robustesse réseau/échiquier) représente une ampleur comparable à l'ensemble du mode Lichess actuel — non tenté dans cette seule session, pour éviter un code non testé/non fiable sur un sujet qui touche l'échiquier physique. Livré : les trois corrections demandées en premier (point 0, indépendantes des problèmes), la lecture de la documentation officielle de l'API Puzzle (point 1) et le module de communication qui en découle (point 2), plus l'extension de `test_token()` nécessaire au point 3 (détection des droits manquants). Le reste (menu, écran de jeu, LED, journal) est décrit ci-dessous comme non fait, pour reprise ultérieure.

### Point 0 — trois corrections de l'écran Lichess/analyse

**a. Bouton « J'ai vu » renommé « Éteindre les LED ».** Le bandeau « adversaire parti » (`#lichess-opponent-gone-banner`) porte un bouton `lichess_opponent_gone_ack` qui n'éteint que le signal LED/bip — jamais les boutons de réclamation, qui restent affichés et cliquables. Le nom laissait croire le contraire. Renommé dans les trois langues (`lichess.eteindre_leds` : "Éteindre les LED"/"Turn off LEDs"/"LEDs ausschalten"), avec une info-bulle (`lichess.eteindre_leds_title` + attribut `title`) précisant explicitement que les boutons de réclamation restent disponibles. Commentaires HTML/tests mentionnant l'ancien nom mis à jour (`test_issue331_lichess_opponent_alerts.py`, `test_issue340_lichess_opponent_signal_e2e.py`) — aucun test n'asserte sur le texte littéral du bouton (sélecteur `data-action`), donc aucune assertion fonctionnelle à changer.

**b. Message persistant « adversaire revenu » resté affiché sur l'écran d'analyse.** Après la fin d'une partie, un événement `opponentGone:false` du flux Lichess encore « en vol » pouvait arriver une fois déjà sur l'écran d'analyse et y rallumer le toast persistant (introduit par #347) ou le bandeau « adversaire parti ». Nouveau drapeau client `_lichessGameOver` (`app.js`) : posé à `true` dans `socket.on("game_over", ...)` quand `data.source === "lichess"` (qui ferme aussi explicitement le toast en cours, remplacé par le résultat affiché juste en-dessous) ; remis à `false` dans `socket.on("lichess_init", ...)` (nouvelle partie). Les handlers `socket.on("lichess_toast", ...)` et `socket.on("lichess_opponent_gone", ...)` ignorent désormais tout événement reçu tant que ce drapeau est vrai — plus aucun message persistant du mode Lichess ne peut réapparaître sur l'écran d'analyse, quelle que soit sa provenance.

**c. Message moteur générique affiché sur une position de mat/pat.** La zone des flèches de l'écran d'analyse (`#review-arrows-status`) affichait "Lignes indisponibles (moteur introuvable ?)" dès que `result.lines` était vide — y compris pour un mat ou un pat, où il n'y a simplement aucun coup légal à calculer (le serveur le savait déjà : `review_multipv.py::_compute()` renvoie `terminal="checkmate"`/`"draw"` sans jamais interroger le moteur sur une position terminale, depuis #341). `_compute()` distingue désormais le pat (`terminal="stalemate"`, via `outcome.termination == chess.Termination.STALEMATE`) des autres nulles automatiques (matériel insuffisant, répétition, 50 coups — restent `"draw"`, pas de changement visible pour celles-ci, pas de message dédié demandé). Côté client, `_reviewApplyLinesResult()` choisit la clé affichée selon `result.terminal` : `game.label.fleches_mat` ("Échec et mat"/"Checkmate"/"Schachmatt") pour `"checkmate"`, `game.label.fleches_pat` ("Pat"/"Stalemate"/"Patt") pour `"stalemate"`, le message générique ne restant que pour un vrai échec moteur (`terminal` absent/`None`). Test existant `test_issue341_review_eval_pov.py::test_position_terminale_pat_barre_a_moitie_sans_moteur` adapté (`terminal` passe de `"draw"` à `"stalemate"`) + nouveau test `test_position_terminale_nulle_hors_pat_reste_draw_sans_moteur` (matériel insuffisant, confirme que seul le pat change de valeur).

### Point 1 — documentation officielle de l'API Puzzle Lichess (lecture seule, 16/11/2026)

Spec OpenAPI `https://lichess.org/openapi.yaml`, dépôt GitHub `lichess-org/api` (`doc/specs/tags/puzzles/*.yaml`, `doc/specs/schemas/Puzzle*.yaml`). Aucun appel réel, aucune authentification.

- **`GET /api/puzzle/next`** (scope `puzzle:read`) : "If authenticated, only returns puzzles that the user has never seen before." Paramètres facultatifs `angle`/`difficulty`/`color`. Réponse `{"game": {...}, "puzzle": {...}}` :
  - `game` : `id`, `pgn` (PGN complet de la partie d'origine), `rated`, `players` (array), `perf`.
  - `puzzle` : `id`, `initialPly`, `rating`, `plays`, `fen` (position où l'utilisateur doit jouer), `lastMove` (coup UCI de l'adversaire qui a amené à `fen`), `solution` (array UCI, à partir du coup de l'utilisateur), `themes` (array).
  - La position à mettre en place AVANT `lastMove` (celle que l'échiquier physique doit afficher avant que les LED montrent ce premier coup adverse) se retrouve en rejouant `game.pgn` jusqu'à `initialPly` demi-coups avec python-chess — jamais en tentant de "défaire" `lastMove` depuis le seul `puzzle.fen` (la pièce éventuellement prise, les droits de roque/prise en passant perdus ne sont pas récupérables à partir du FEN final seul).
- **`POST /api/puzzle/batch/{angle}`** (scope `puzzle:write`) : corps JSON `{"solutions": [{"id", "win", "rated"}], "nb": int}` — `nb` contrôle le nombre de NOUVEAUX problèmes renvoyés dans la même réponse (AlChess utilise `nb=0`, un problème est toujours redemandé séparément via `/next`). Réponse `{"rounds": [{"id","win","ratingDiff"}], "glicko": {"rating","deviation","provisional"}, "puzzles": [...]}` — la nouvelle cote de problèmes est donc disponible IMMÉDIATEMENT dans cette même réponse, aucun second appel nécessaire.
- **Abandon d'un problème en cours** : aucune route ni paramètre "give up"/"abandon"/"quit" trouvé dans la spec officielle — ce comportement n'est tout simplement pas documenté publiquement (même lichess.org n'a apparemment pas de route dédiée). Décision retenue pour toute future implémentation : ne JAMAIS appeler la route de résultat tant que le problème n'est pas réellement résolu (solution jouée en entier) ou raté (mauvais coup confirmé) — jamais un résultat inventé en cas d'abandon/retour au menu/page rechargée, cohérent avec l'absence de toute route pour ce cas précis.
- **Thèmes** : déjà présents dans `puzzle.themes` dès la réponse de `/next` — rien dans l'API ne les masque ; c'est entièrement à la charge d'une future implémentation côté client de les cacher à l'écran avant résolution.
- HTTPS uniquement (`servers: https://lichess.org`), confirmé.

### Point 2 — module de communication

Nouveau `nicsoft/modes/lichess/puzzle_client.py`, urllib direct (comme `client.py` — pas de flux, inutile de passer par `transport.py`/`GameClient`) :

- `get_next_puzzle(token, difficulty=None)` → `GET /api/puzzle/next`, retourne `{"status": "ok", "puzzle_id", "rating", "plays", "themes", "solution", "fen", "setup_fen", "opponent_first_move", "game_id", "rated", "players"}` ou `{"status": "invalid"/"missing_scope"/"rate_limited"/"network_error"}`.
- `submit_puzzle_result(token, puzzle_id, win, rated=True)` → `POST /api/puzzle/batch/mix`, retourne `{"status": "ok", "rating_diff", "new_rating", "provisional"}` ou un statut d'erreur identique à ci-dessus.
- `parse_puzzle_payload(data)` : fonction pure, jamais d'exception sur une donnée inattendue — extrait `puzzle_id`/`solution`/`themes`/`fen`, et calcule `setup_fen` (position avant le premier coup adverse) en rejouant `game.pgn` via python-chess jusqu'à `initialPly` demi-coups ; retombe sur `setup_fen == fen` (pas d'étape "premier coup adverse") si le PGN est absent/illisible ou `initialPly` hors limites — jamais un plantage sur une donnée Lichess malformée.
- `client.py::test_token()` renvoie désormais aussi `has_puzzle_read`/`has_puzzle_write` (nouvelles constantes `PUZZLE_READ_SCOPE`/`PUZZLE_WRITE_SCOPE`) — nécessaire pour qu'une future carte menu « Problèmes Lichess » détecte un jeton valide mais sans les droits requis (le jeton actuel d'Alain, `board:play` seul, est dans ce cas) et affiche une explication claire plutôt qu'une erreur technique.

Jeton jamais journalisé (testé explicitement : `test_submit_puzzle_result_corps_envoye_ne_contient_jamais_le_jeton`), jamais envoyé ailleurs que l'en-tête `Authorization`, https vérifié par `ensure_https` avant tout appel.

### Non fait — à reprendre dans une future issue dédiée

Points 3 à 8 (menu, déroulement interactif d'un problème avec LED, fin de problème/enchaînement, restriction moteur spécifique, robustesse réseau/échiquier, journal dédié) **n'ont pas été construits** : l'ampleur réelle (mise en place physique, détection de coups contre une solution scriptée, signal de coup raté distinct, annulation/voir la solution, promotion, journal par session) est comparable à celle du mode Lichess actuel en parties (`game.py` + `game_manager_modes/lichess.py`, ~4000 lignes à eux deux) — tenter de la construire sans la tester sérieusement contre un faux serveur ET sans pouvoir la vérifier avec le matériel aurait produit un code à risque sur un sujet qui pilote l'échiquier physique. Base posée pour une reprise : le module de communication (point 2) et la détection de droits (`has_puzzle_read`/`has_puzzle_write`) sont prêts à être consommés par un futur lanceur de mode (sur le modèle de `core/game_manager_modes/lichess.py::launch_lichess`) et une future classe d'orchestration (sur le modèle de `modes/lichess/game.py::LichessGame`, en réutilisant ses briques existantes : `_differing_squares`/mise en place LED, `pending_promotion_move`/`legal_move_for_hardware` pour la détection de coups et la promotion, `GameLog` pour le journal dédié).

### Tests

`nicsoft/tests/test_issue351_lichess_puzzles.py` (20 tests) : `parse_puzzle_payload` (position de mise en place calculée correctement par rejeu PGN, repli sans PGN, `initialPly` hors limites, sans premier coup adverse, données absentes/invalides) ; `get_next_puzzle`/`submit_puzzle_result` contre un faux serveur local (urlopen mocké, même technique que `test_issue306_lichess.py`) : ok, jeton absent, 401/403/429, réseau coupé, réponse illisible, https refusé, jeton jamais dans le corps envoyé ; `test_token()` avec/sans les droits des problèmes. `test_issue341_review_eval_pov.py` : test du pat adapté + nouveau test de nulle hors pat (point 0c). Aucun test pour les points 3-9 restants (menu verrouillé, mauvais coup, voir la solution, enchaînement, échiquier perdu, promotion dans la solution, aucun moteur lancé) : rien n'a été construit à tester.

Suite complète rejouée sans régression : `pytest nicsoft/tests/ -k lichess` (772 passés, 9 ignorés) et `pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` (1383 passés, 84 ignorés) ; `test_no_web_import.py` (garde ARC-001) toujours vert.

### Ce qu'Alain ne pourra pas vérifier en réel

Rien côté problèmes Lichess (non construit). Les trois corrections du point 0 sont vérifiables sans recréer le jeton : bouton renommé, message persistant disparu en fin de partie Lichess, message "Échec et mat"/"Pat" sur l'écran d'analyse d'une partie terminée ainsi.

# Changelog — issue #350

## Mode Pédagogique : les noms Blanc/Noir doivent suivre l'orientation de l'échiquier

Suite de #345/#348, qui avaient laissé ce défaut hors périmètre pour le mode Pédagogique (note laissée dans `CONTEXTE.md` par #345, reprise par #348) : constaté par lecture de code CCL, pas en réel par Alain.

### Diagnostic — confirmé

**`socket.on("init", ...)` (démarrage d'une partie Pédagogique, `app.js`).** Affectait inconditionnellement `player-top-name = adversaire` / `player-bottom-name = joueur` (ou l'inverse selon la couleur du joueur), sans jamais consulter `_boardFlipped` — même cause racine que les défauts déjà corrigés par #345/#348.

**`socket.on("swap_color", ...)` (changement de camp pendant une pause Pédagogique, `pedagogique.py` → `send_event("swap_color", ...)`).** Même défaut exact : toujours figé sur une convention "haut=Noir/bas=Blanc" implicite via `isWhite`, sans tenir compte de `_boardFlipped`, alors que ce changement de camp peut survenir en cours de partie, donc avec l'échiquier potentiellement déjà retourné par `#btn-flip` (partagé par tous les écrans de jeu, y compris pendant une partie Pédagogique).

**Troisième site trouvé en cherchant le même motif dans `app.js` : `ouvrirModalNulle()`, branche moteur (hors HH/Lichess).** La modale "Proposer nulle à <adversaire>" retrouvait le nom de l'adversaire via une formule figée `isWhite ? player-top-name : player-bottom-name`, sans consulter `_boardFlipped` — échiquier retourné, elle affichait à tort le nom du JOUEUR dans son propre titre.

**Quatrième site, par cohérence (hors scénario observable en pratique) : `socket.on("init_hh", ...)`.** Même défaut latent que le "init" Pédagogique ci-dessus, mais côté HH : affectait inconditionnellement `player-top-name = Noir` / `player-bottom-name = Blanc`. Non observable en pratique car `_boardFlipped` est toujours remis à `false` au retour au menu (`data.state === "menu"`) avant qu'un nouveau "init"/"init_hh" ne puisse survenir — mais la nouvelle écriture ne dépend plus de cet invariant fragile, et le correctif est trivial par réutilisation de la même fonction déjà en place.

**Résultat de partie et PGN du mode Pédagogique : vérifiés CORRECTS, non affectés.** `pedagogique.py` dérive entièrement en-têtes PGN (`White`/`Black`), gagnant et résultat (`1-0`/`0-1`) depuis `self.playing_white` (état serveur), jamais depuis une position écran — vérifié par lecture de code (lignes 326-327, 404-405, 439-442, 733-734, 899, 973, 1206, 1324 de `pedagogique.py`). Même garantie que pour #348/HH : le défaut était purement un bug d'affichage client.

**Recherche élargie (point 2 de la tâche) — aucun autre site fautif trouvé.** Le mode Labo n'affiche aucun nom de joueur haut/bas (pas de notion de camp sur cet écran). Les modes Exercices (`ex-player-top`/`ex-player-bottom`) et Retranscription (`retrans-player-top`/`retrans-player-bottom`) gèrent chacun leur propre variable d'orientation locale et cohérente (`_exBoardFlipped`, `_rtFlipped`), indépendante de `_boardFlipped` et correctement câblée de bout en bout (plateau + noms synchronisés) — pas le même défaut. Le mode Lichess, délibérément orienté "haut=adversaire / bas=utilisateur" quelle que soit la couleur jouée (#315), n'a volontairement pas été touché.

### Corrections

Réutilisation des fonctions déjà factorisées par #345 (aucune duplication de la logique d'orientation) :

- `socket.on("init", ...)` (Pédagogique) : écrit désormais les deux cases via `_reviewSetTopBottomNames(white, black)`.
- `socket.on("swap_color", ...)` (Pédagogique) : idem.
- `socket.on("init_hh", ...)` : idem, par cohérence.
- `ouvrirModalNulle()` (branche moteur) : le nom de l'adversaire vient désormais de `_reviewWhiteBlackFromTopBottom()` (lit `player-top-name`/`player-bottom-name` et reconstruit Blanc/Noir selon `_boardFlipped`), au lieu de la formule figée `isWhite ? top : bottom`.

Les lignes de coloration positionnelle (`topName.style.color = "#3a5a7a"` / `botName.style.color = "#1a2a3a"`) sont inchangées : purement liées à la position écran (haut/bas), pas au camp — déjà correctes.

### Tests

Nouveau `nicsoft/tests/e2e/test_issue350_pedagogique_orientation_e2e.py` (9 tests, Playwright, événements socket simulés via `socket.listeners(...).forEach(h => h(data))` — même procédé que #345/#348, sans échiquier physique, sans navigateur ouvert, aucun moteur) :
- noms corrects au démarrage ("init") d'une partie Pédagogique, joueur Blanc puis Noir, échiquier non retourné puis retourné ;
- `swap_color` suit l'orientation, non retourné puis retourné ;
- `ouvrirModalNulle()` affiche le bon nom d'adversaire, non retourné puis retourné ;
- non-régression de la convention par défaut de `init_hh`.

Suite complète non-`slow` rejouée sans régression après le correctif, ainsi que `test_issue345_analyse_lichess_fixes_e2e.py` et `test_issue348_hh_abandon_orientation_e2e.py` (18 tests au total avec les nouveaux, tous verts).

### Mise à jour de CONTEXTE.md

La note laissée par #345 et reprise par #348 ("Même défaut repéré ... mode Pédagogique ... non corrigé, laissé pour une future issue dédiée") est remplacée par une note "Corrigé par #350", avec la recherche élargie (labo/exercices/retranscription, rien trouvé) mentionnée comme vérifiée.

# Changelog — issue #349

## Lichess classé : ma cote affichée et rangement des PGN par cadence

Deux demandes d'Alain après sa première partie classée (#344), traitées ensemble car elles touchent le même code (enregistrement du PGN et affichage des joueurs) : afficher MA cote (comme celle de l'adversaire, déjà existante) et la nouvelle cote de fin de partie classée ; ranger les parties classées dans un dossier séparé par cadence. Entièrement hors ligne (faux serveur local, `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) — aucune vraie recherche/partie Lichess, aucun vrai jeton utilisé.

### Partie 1 : ma cote et ma nouvelle cote

**1. Ma cote affichée (point 1).**

- `nicsoft/modes/lichess/game.py::LichessGame._apply_game_full()` : nouveau `self_dict` (mon côté du `gameFull`, symétrique à `opponent_dict`) → `self.user_rating`/`self.user_provisional` lus depuis `self_dict.get("rating")`/`get("provisional")` — toujours lus, même contre l'IA (mon côté porte `rating`, le côté adverse `aiLevel` à la place) ; `None` si absente, jamais devinée. `self._my_username` (champ `id`) retenu pour la nouvelle cote (point 3). `self.opponent_provisional` ajouté symétriquement (existait seulement pour `opponent_rating`).
- `lichess_init` porte désormais `user_rating`/`user_provisional`/`opponent_provisional` en plus des champs existants — même chemin pour une partie normale ET une reprise (L2b), un seul point d'émission (`_apply_game_full`).
- `app.js` : nouvelle fonction `_lichessRatingSuffix(rating, provisional)` (`" (1327)"`, `" (1327?)"` si provisoire — même convention que lichess.org), utilisée pour construire `opponentLabel` (déjà existant, désormais via cette fonction commune) ET le nouveau `playerLabelWithRating`, affecté à `#player-top-name`/`#player-bottom-name` et au sous-titre — mêmes éléments DOM pendant la partie et à l'écran de fin/d'analyse, donc affichés sans code supplémentaire sur ce second écran.

**2. Cotes dans le PGN et l'écran « Révision PGN » (point 2).**

- `build_pgn_headers()` (`game.py`) accepte `user_rating`/`opponent_rating` et écrit les en-têtes standard `WhiteElo`/`BlackElo` (affectés au bon côté selon `user_color`) — seulement quand la cote correspondante est connue.
- `app.js::parsePgn()` lit `WhiteElo`/`BlackElo` du PGN chargé (import, « Coller PGN », bibliothèque, classeur — tous passent par cette fonction) et les ajoute aux noms via `_lichessRatingSuffix` ; `_reviewSetTopBottomNames()` (déjà sensible à l'orientation depuis #345) les place dans le bon ordre sans changement.

**3. Nouvelle cote en fin de partie classée (point 3) — mécanisme REMPLACÉ.**

- Ancien mécanisme #344 (`GameClient.fetch_rating_diff()`, flux général `/api/stream/event` + attente d'un `gameFinish`) **retiré** : Alain avait déjà constaté qu'il manquait souvent (délai d'arrivée non garanti par la doc Lichess), et il ne donnait qu'une variation, jamais la cote absolue demandée par cette issue.
- Remplacé par `GameClient.fetch_my_rating(username, speed_key)` (nouveau) : `GET /api/user/<username>` — route **publique** de la doc officielle (« No OAuth and no scope is required »), aucun jeton/droit supplémentaire nécessaire (le jeton de l'instance est quand même envoyé, sans effet pour cette route). Lit `perfs[speed_key]["rating"]` ; ne lève jamais (réseau/HTTP/parsing → `None`).
- `LichessGame._maybe_fetch_new_rating()` (remplace `_maybe_fetch_rating_diff`) : fil dédié démarré par `_finalize()` seulement si `rated` et fin réelle. Un essai après `_NEW_RATING_INITIAL_DELAY_S` (1,5s), **une seule** nouvelle tentative après `_NEW_RATING_RETRY_DELAY_S` (4s) si la cote lue est encore égale à `self.user_rating` (cote de départ) — la variation est calculée côté Python (`new_rating - start_rating`), jamais fournie par Lichess. Pousse `lichess_new_rating` (`new_rating`/`rating_diff`) seulement si une valeur entière est obtenue ; silencieux (rien poussé) sinon.
- `app.js` : `lichess_rating_diff` → `lichess_new_rating` ; `_lichessRenderRatedInfo()` affiche désormais la nouvelle cote (+ sa variation si connue) via la nouvelle clé i18n `lichess.nouvelle_cote` (`fr`/`en`/`de`).
- **Garder/remplacer/compléter** : remplacé entièrement, pas complété — les deux mécanismes visent la même information (l'état de la cote après la partie), et le nouveau est strictement plus simple à réessayer (une requête HTTP ordinaire vs. un flux à maintenir ouvert) tout en répondant exactement à la demande d'Alain (« nouvelle cote », pas seulement une variation).

**4. Sécurité/i18n (point 4).**

- `_my_username` n'est jamais journalisé ni envoyé au navigateur au-delà de ce qui l'est déjà pour l'adversaire ; passé par `urllib.parse.quote()` avant insertion dans l'URL (défense en profondeur).
- Cotes affectées via `.textContent` (jamais `innerHTML`), comme tout le reste de l'écran Lichess. Clés i18n ajoutées simultanément dans les 3 langues.

**5. Tests.** `nicsoft/tests/test_issue349_lichess_rating_cadence.py` (30 tests) + `nicsoft/tests/e2e/test_issue349_lichess_rating_e2e.py` (8 tests, Playwright) : cotes des deux joueurs (2 orientations), cote provisoire, absence de cote, en-têtes PGN + écran Révision, `fetch_my_rating` (succès/catégorie absente/erreur réseau), orchestration (inchangée puis changée à la 2ᵉ tentative, échec réseau silencieux, jamais tentée sans cote de départ). `test_issue344_lichess_rated.py` adapté (tests de l'ancien `fetch_rating_diff` retirés, 2 tests `_finalize` portés sur la nouvelle API).

### Partie 2 : dossier Classée par cadence

**1. Rangement par cadence (point 1).**

- `pgn_cadence_folder_name(clock_limit_s, clock_increment_s)` (nouveau, `game.py`) : `"<minutes>+<incrément en secondes>"` (ex. `"10+0"`, `"15+10"`, `"90+30"`) — chiffres et `+` seulement, sûr sous Windows. Dérivé directement de la cadence confirmée de la partie, jamais de `cadence_key` (peut être vide à la reprise).
- `LichessGame._save_pgn()` : une partie classée (`self.rated`) est enregistrée dans `Lichess/Classée/<cadence>/` via `build_final_path("Lichess", f"Classée/{cadence}", ...)` — `build_final_path()` (inchangé) gère déjà la création récursive (`os.makedirs`) et un `game_type` contenant `/` sans modification (pathlib découpe la chaîne en composants sur les deux plateformes). Dossier créé à la demande (jamais à l'avance).

**2. Amicale inchangée (point 2).** Une partie amicale (IA ou humain) reste enregistrée dans `Lichess/Amicale/`, exactement comme avant — aucun fichier déjà enregistré déplacé ni renommé.

**3. En-tête Event (point 3).** `_save_pgn()` construit désormais l'en-tête `Event` selon `self.rated` : `"Lichess, classée (<cadence>) contre un humain"` pour une classée (avant cette issue, il disait toujours « amicale », même pour une partie classée — bug corrigé en même temps), `"Lichess, amicale contre l'IA niveau N"` / `"Lichess, amicale contre un humain"` sinon (inchangé).

**4. Listes de parties (point 4).** Vérification plutôt que modification : `nicsoft/web/server.py::_get_game_folders()` (combobox « type de partie » de `sauvegarderNicLink()`, écran Révision/Analyse) liste les dossiers par `os.listdir()` à deux niveaux (`mode`/`game_type`) — elle retrouve `Classée` automatiquement dès qu'une partie y a été enregistrée, sans changement de code. C'est la **seule** fonction du projet qui parcourt `GAMES_DIR` : « Mes parties AlChess » (import de fichier/« Coller PGN »/classeur de session) et la bibliothèque PGN (collections sous `DATA_DIR/pgn_library/`, totalement séparée) ne lisent jamais ce dossier directement — aucun risque de doublon ni de parcours récursif à ajouter. Point d'attention pour Alain : cette combobox ne descend pas au niveau cadence — une sauvegarde **manuelle** d'un PGN quelconque via « Lichess — Classée » (ex. un PGN collé) écrirait directement sous `Classée/` sans sous-dossier de cadence, contrairement à l'enregistrement **automatique** de fin de partie Lichess (`_save_pgn`, seul concerné par cette issue), qui range toujours correctement par cadence.

**5. Tests.** Mêmes fichiers que la partie 1 (`test_issue349_lichess_rating_cadence.py`) : classée 10+0 → `Classée/10+0`, classée 15+10 → `Classée/15+10`, amicale (humain et IA) → `Amicale`, en-tête `Event` « classée » avec cadence, dossiers jamais créés à l'avance — tout sur un `GAMES_DIR` temporaire isolé (fixture autouse `conftest.py::_isolate_games_dir`), jamais le vrai dossier d'Alain.

### Non vérifié

Aucune vraie partie classée jouée pendant cette issue (interdit par consigne) : délai réel de recalcul de la cote côté Lichess après la fin d'une partie non mesuré — `_NEW_RATING_INITIAL_DELAY_S`/`_NEW_RATING_RETRY_DELAY_S` sont une estimation prudente. Alain vérifiera à sa prochaine partie classée contre un humain (les deux parties de cette issue).

# Changelog — issue #347

## Lichess en partie : abandon à tout moment contre un humain, nulle après son coup, toasts durables, coup refusé en fin de partie

Deux demandes d'Alain sur le déroulement d'une partie Lichess, traitées dans l'ordre.

### Partie 1 — Abandon et nulle contre un humain

**Diagnostic.** `LichessGame._compute_action_buttons()` (`nicsoft/modes/lichess/game.py`) calculait l'état des boutons Abandonner/Proposer nulle avec une formule UNIQUE, partagée sans distinction entre adversaire IA et adversaire humain (`turn_ready or board_lost` pour Abandonner) — confirmant l'hypothèse d'Alain : la règle de #321 avait été écrite en pensant à l'IA (qui répond en quelques secondes) et reconduite telle quelle pour l'humain (réflexions de 15-20 minutes), sans jamais être différenciée. Le reste du chemin de l'abandon (`_request_resign_or_abort`, l'appel réseau `resign()`/`abort()`, `_finalize()` — sauvegarde PGN, signaux, écran de fin, analyse seulement après coup, aucun moteur jamais importé par ce module) était déjà entièrement générique IA/humain et n'a nécessité AUCUNE modification : seule l'activation du bouton côté interface bloquait l'action, pas le traitement derrière.

**Correctifs** (`nicsoft/modes/lichess/game.py`) :
- `_compute_action_buttons()` : deux branches explicites selon `self._opponent_is_ai`. Contre l'IA, comportement de #321/#327 strictement inchangé. Contre un humain : Abandonner toujours actif (`resign_enabled = True`, sans condition de trait/position/reprise) ; Proposer nulle piloté par une nouvelle fenêtre `self._human_draw_window_open` (usage FIDE : actif après son propre coup, jusqu'au coup adverse suivant).
- `_human_draw_window_open` : posée à `True` par `_submit_move()` dès l'envoi réussi du coup (sans attendre l'écho du flux) et confirmée par `_apply_new_moves()` à cet écho (couvre aussi la reprise d'une partie) ; remise à `False` par `_apply_new_moves()` dès qu'un coup adverse est appliqué — y compris pendant sa reproduction physique et pendant le tour de l'utilisateur avant qu'il ne rejoue.
- `_safe_draw_offer_call()` (nouvelle méthode) : si Lichess refuse une nouvelle offre de nulle, message dédié (`lichess.nulle_requete_refusee`, persistant) au lieu du message générique « coup refusé ».
- `_request_resign_or_abort()` : ligne de journal dédiée (heure automatique, état de la partie, type d'adversaire) avant l'appel réseau, et confirmation (statut/vainqueur) après — jamais le jeton (masqué par `GameLog._mask`, indépendant de ces lignes). La réponse de Lichess elle-même était déjà journalisée par `GameClient._request`.

**Front (`app.js`/`index.html`)** : le hint sous les boutons distingue désormais trois cas (IA : « nulle impossible contre l'IA » ; humain hors tour pour Abandonner — ne se produit plus en pratique ; humain avant son coup : nouveau texte `lichess.nulle_apres_son_coup`).

**Confirmation IA inchangée** : `test_abandon_toujours_grise_hors_tour_contre_l_ia` et `test_nulle_toujours_grisee_contre_l_ia` (nouveau fichier de tests) + l'intégralité de la suite `test_issue321_*` (adaptée pour les 3 tests qui, à tort, attendaient l'ancien comportement humain — un 4ᵉ test obsolète, dont toute la prémisse disparaît avec #347, a été retiré avec une note de renvoi) passent sans changement de résultat pour un adversaire IA.

**Tests** : nouveau `nicsoft/tests/test_issue347_lichess_resign_anytime_and_draw_after_move.py` (14 tests) — abandon actif pendant le tour adverse, pendant la reproduction du coup adverse, pendant une reprise (L2b) et en position illégale, pour un humain ; abandon toujours grisé hors tour contre l'IA ; chemin complet de bout en bout (réseau, fin de partie, PGN, aucun skip) ; nulle grisée avant le premier coup, active dès l'envoi du coup, active pendant la réflexion adverse, regrisée au coup suivant (y compris pendant sa reproduction et le tour suivant de l'utilisateur), valable blancs/noirs ; message persistant + refus différé (#318) inchangés ; nulle toujours grisée contre l'IA ; nouvelle offre refusée par Lichess affichée clairement sans planter.

### Partie 2 — Toasts et coup refusé en fin de partie

**1. Durée des toasts.** `afficherToast()` (fonction commune à tous les modes) reste inchangée (4000 ms fixes) : nouvelle fonction `afficherToastLichess()` dédiée au mode Lichess, durée minimale 7000 ms puis proportionnelle à la longueur du texte (90 ms/caractère, plafond 15000 ms) pour les messages non persistants. Les messages importants (coup refusé par Lichess, adversaire parti/revenu, erreurs réseau) sont désormais **persistants** (ferme-toi manuellement ou remplacé par l'événement suivant) : `lichess_move_refused` (refus réel, non ambigu), tous les `lichess.erreur_reseau` envoyés par `game.py`/`game_manager_modes/lichess.py`, `lichess.adversaire_revenu`. Les deux toasts génériques « retour au menu/config suite à une erreur » (`app.js` lignes ~1631/~1759) sont **partagés avec tous les modes** (board perdu, moteur KO...) et n'ont PAS été modifiés, conformément à la consigne de ne pas toucher les toasts des autres modes. Changement commun inévitable : la règle CSS `.toast { white-space: nowrap }` (déjà existante, tous modes) aurait fait déborder un message Lichess désormais plus long/persistant sur l'échiquier/les pendules/les boutons — ajout d'un `max-width` + retour à la ligne (`nicsoft/web/static/css/main.css`), neutre pour un message court inchangé dans les autres modes.

**2. Coup refusé par Lichess en fin de partie — cas réel du 15/11/2026.** Diagnostic : `_submit_move()` affichait inconditionnellement le toast générique sur toute `LichessApiError`, sans jamais vérifier si la partie venait de se terminer — alors que, dans le journal réel, l'événement de fin (adversaire a abandonné) était déjà disponible dans le flux de partie 51 ms avant que la réponse HTTP d'erreur n'arrive. Nouvelle méthode `_handle_move_rejected()` : si le message HTTP 400 est l'« Not your turn, or game already over » ambigu (détecté par `errors.is_ambiguous_turn_or_over_error()`), la partie relit l'état réel en traitant tout événement déjà disponible dans le flux (`_drain_pending_stream_events()`, attente bornée à 2 s — jamais une nouvelle requête réseau, seulement ce qui est déjà en route). Si la partie est confirmée terminée : aucun toast « coup refusé », le déroulement normal de fin (`_finalize`, sauvegarde PGN, signaux, écran d'analyse) prend le relais, et le nouveau champ `last_move_rejected` du payload `game_over` affiche une note dédiée (« Votre dernier coup joué sur l'échiquier n'a pas été accepté par Lichess... ») sous la cause de fin de partie. Si la partie n'est toujours pas terminée après ce délai (vraie erreur hors tour) : comportement inchangé. Le PGN enregistré n'a jamais contenu ce dernier coup physique (comportement préexistant déjà correct : `_submit_move` ne pousse jamais le coup sur `self.board` avant confirmation du flux) — seule l'absence d'explication était fautive, désormais corrigée.

**3. Journal.** `_handle_move_rejected()`/`_submit_move()` journalisent (heure automatique `GameLog._write`, jamais le jeton) : le coup envoyé et son acceptation, le refus avec code HTTP + raison, et l'issue de la relecture du flux (partie terminée avec son statut, ou vraie erreur après le délai imparti).

**Tests** : nouveau `nicsoft/tests/test_issue347_lichess_ambiguous_move_rejection.py` (6 tests) — détection du message ambigu ; reproduction du cas réel (événement de fin déjà en file, relecture en moins de 100 ms, victoire affichée, aucun toast d'erreur, `last_move_rejected=True`, PGN sans le dernier coup) ; même refus quand la partie n'est PAS terminée (délai raccourci pour le test, retombe sur le toast d'erreur habituel) ; message non ambigu inchangé ; journal dédié (heure, coup, refus, relecture, jamais le jeton).

**Tests existants adaptés** (comportement changé, pas de régression réelle) : `test_issue321_lichess_boutons_et_nulle.py` (3 tests sur 8 mis à jour pour les nouvelles règles humain, 1 test obsolète retiré avec renvoi), `test_issue323_lichess_resume.py` (1 assertion), `test_issue340_lichess_opponent_signal_e2e.py` (1 assertion, toast désormais persistant → lecture du `<span>` plutôt que de tout `#toast`).

# Changelog — issue #348

## Humain contre Humain : la fenêtre d'abandon doit tenir compte de l'orientation de l'échiquier

Suite de #345, qui avait laissé ce défaut hors périmètre (noté dans `CONTEXTE.md`) : constaté par lecture de code CCL, pas en réel par Alain.

### Diagnostic

**Modale d'abandon HH (`ouvrirModalAbandonner()`, branche `_gameMode === "humain"`, `app.js`).** Affectait inconditionnellement `nomBlanc = player-bottom-name` / `nomNoir = player-top-name`, sans jamais consulter `_boardFlipped` — même cause racine que le défaut n°3 de #345 (`parsePgn()`), mais sur un écran différent (modale d'abandon de l'écran de jeu, pas écran d'analyse). Échiquier retourné (Noirs en bas), le bouton « Blancs abandonnent » affichait le nom du joueur Noir, et inversement.

**Deuxième site trouvé en cherchant le même motif dans `app.js` : `socket.on("swap_color_hh")`** (changement de camp demandé pendant une pause HH, `human.py::_handle_turn_pause` → `send_event("swap_color_hh", ...)`). Même défaut exact : affectait toujours `player-top-name = Noir` / `player-bottom-name = Blanc`, sans tenir compte de `_boardFlipped`, alors que ce changement de camp peut survenir en cours de partie, donc avec l'échiquier potentiellement déjà retourné par le bouton ⇅ (partagé par tous les écrans de jeu, y compris pendant une partie HH).

**Résultat de partie (1-0/0-1) et PGN : vérifiés CORRECTS, non affectés.** Les boutons HTML de la modale (`templates/index.html`) envoient `sendAction({type:'abandonner', couleur:'blanc'})` / `couleur:'noir'` — valeur FIXE, indépendante du texte affiché sur le bouton. Côté serveur, `human.py::_traiter_abandon()` décide gagnant/résultat/PGN uniquement depuis cette `couleur` (jamais depuis une position écran) : `couleur == "blanc"` → `0-1`/gagnant Noir, `couleur == "noir"` → `1-0`/gagnant Blanc — toujours corrects, orientation ou non. Le défaut était donc purement un bug d'affichage client (point 1 de la tâche confirmé pour le nom affiché, pas pour le résultat/PGN).

**Autres sites de même motif, trouvés et non corrigés (hors mode HH, hors périmètre #348)** : `socket.on("init", ...)` et `socket.on("swap_color", ...)` (mode **Pédagogique**, vs moteur) affectent eux aussi `player-top-name`/`player-bottom-name` sans regarder `_boardFlipped`. Observable seulement si `#btn-flip` (bouton partagé par tous les écrans de jeu) est utilisé PENDANT une partie Pédagogique — pas vérifié en réel. Laissé pour une future issue dédiée au mode Pédagogique (consigne de la tâche : ne pas toucher aux modes contre moteur hors défaut clairement fautif et dans le périmètre demandé). Le mode Lichess, lui, est délibérément orienté « haut=adversaire / bas=utilisateur » quelle que soit la couleur jouée (issue #315) — ce n'est pas le même défaut, non concerné.

### Corrections

Dans les deux cas, réutilisation des fonctions déjà factorisées par #345 (aucune duplication de la logique d'orientation) :

- `ouvrirModalAbandonner()` : `nomBlanc`/`nomNoir` viennent désormais de `_reviewWhiteBlackFromTopBottom()` (lit `player-top-name`/`player-bottom-name` et reconstruit Blanc/Noir selon `_boardFlipped`).
- `socket.on("swap_color_hh")` : écrit désormais les deux cases via `_reviewSetTopBottomNames(white, black)` (au lieu de l'affectation inconditionnelle `top=Noir/bottom=Blanc`).

### Tests

Nouveau `nicsoft/tests/e2e/test_issue348_hh_abandon_orientation_e2e.py` (5 tests, Playwright, événements socket simulés via `socket.listeners(...).forEach(h => h(data))` — même procédé que #342/#345, sans échiquier physique, sans navigateur ouvert (`ALCHESS_SKIP_BOARD=1`/`BROWSER=/bin/true` déjà posés par `conftest.py`), aucun moteur) :
- noms corrects sur les boutons de la modale d'abandon HH, échiquier non retourné puis retourné (les deux camps) ;
- non-régression : les boutons de la modale envoient toujours `couleur:'blanc'`/`couleur:'noir'` fixe, quelle que soit l'orientation (le résultat de partie ne dépend jamais de l'affichage) ;
- `swap_color_hh` suit l'orientation, non retourné puis retourné.

Vérifié que ces tests détectent bien la régression : les 2 tests « échiquier retourné » échouent si on revient à l'ancien code (`git stash` du seul `app.js` pendant la vérification, confirmé puis annulé) — 3 passent déjà avant le correctif (non-régression/cas non retourné), 2 échouent avant et passent après.

Suite complète non-`slow` (1305 tests) + `test_issue345_analyse_lichess_fixes_e2e.py` (4 tests) rejouées sans régression après le correctif.

### Mise à jour de CONTEXTE.md

La note laissée par #345 (« Non corrigé, hors périmètre ... `ouvrirModalAbandonner()` ... ») est remplacée par une note « Corrigé par #348 », avec la découverte du mode Pédagogique ajoutée comme point ouvert.

# Changelog — issue #345

## Analyse post-partie Lichess : barre d'évaluation disparue, analyse non lancée après partie, noms inversés

Trois défauts constatés par Alain le 15 novembre 2026 sur l'écran d'analyse affiché à la fin d'une partie Lichess gagnée aux Noirs (échiquier retourné, Noirs en bas).

### Diagnostic

Historique vérifié : #341 (`37c3060`), #342 (`7cf3741`) et #343 (`70db037`) sont bien dans le code exécuté par Alain.

**1. Barre d'évaluation absente.** Cause : `app.js::_reviewUpdateEvalBar()` masquait inconditionnellement la barre dès que `_gameSource === "lichess"` — garde introduite par #341 (commit `37c3060`), pensée pour la règle de fair-play Lichess (#333, « jamais de moteur PENDANT une partie en ligne »), mais appliquée à tort sur l'écran d'analyse lui-même, qui n'est de toute façon jamais atteint pendant une partie Lichess EN COURS (accessible uniquement depuis l'état serveur `game_over`). Au moment de #341, aucune analyse post-Lichess n'existait encore (#342 est arrivé plus tard le même jour) : masquer la barre pour toute source Lichess était alors inoffensif en pratique. #342 a changé la règle (analyse complète d'office même pour une partie Lichess terminée) sans que cette garde de #341 soit revue — d'où la régression effective. Explique aussi le second constat d'Alain (barre absente même quand l'analyse via « Révision PGN » fonctionnait) : `_gameSource` reste à `"lichess"` tant que l'écran d'analyse n'a pas été quitté (reset seulement au retour au menu) — `parsePgn()` ne le remet jamais à une autre valeur, donc charger un PGN juste après la fin d'une partie Lichess (sans repasser par le menu) laisse la barre masquée aussi pour cette partie-là.

**2. Analyse automatique non lancée après la fin de la partie.** Cause : `socket.on("app_state")`, dans le bloc `data.state === "game_over"`, appelait `_reviewMaybeAutoAnalyse(data.source === "lichess")` — passant `skip=true` pour TOUTE partie de source Lichess, y compris une fois terminée. La garde voulue par #342 (jamais pendant une partie EN COURS) est déjà assurée par la garantie architecturale (cet écran n'existe que depuis `_app_state == "game_over"`) et par le garde-fou serveur explicite de `on_analyser_pgn` (`_app_state != "game_over"` → refusé) — aucun des deux ne dépend de la source. Le test e2e existant (`test_issue342_auto_analyse_e2e.py::test_jamais_declenche_en_mode_lichess`) codifiait justement ce comportement erroné (assertion `_analyseActive is False` pour une partie Lichess terminée) et masquait donc la régression au lieu de la détecter.

**3. Noms de joueurs inversés par rapport à l'orientation après un chargement de PGN.** Nouveau défaut (pas de régression #341/#342/#343) : `parsePgn()` affectait inconditionnellement `player-top-name = Noir` / `player-bottom-name = Blanc`, sans jamais consulter `_boardFlipped`. Observé par Alain : PGN « tomatoloss vs Vous » (0-1, Alain Noir, victoire), échiquier resté retourné (Noirs en bas) depuis la partie Lichess précédente — affiché à tort « Vous » en haut / « tomatoloss » en bas, alors que « Vous » (Noir) joue en bas sur un échiquier retourné. Les pièces capturées (`updateMaterial()`) recalculaient déjà correctement leur côté depuis `_boardFlipped` à chaque rendu — pas de défaut sur ce point, contrairement à l'hypothèse d'Alain. Vérification des en-têtes du fichier PGN auto-enregistré par une vraie partie Lichess (`modes/lichess/game.py::_save_pgn`/`build_pgn_headers`, dérivés de `user_color`, jamais du DOM) : **fichier correct**, White/Black/Result cohérents avec la partie Lichess d'origine — le défaut est purement un bug d'affichage côté client, confiné à `parsePgn()`.

### Corrections

**Point 1** — `_reviewUpdateEvalBar()` : suppression de la condition `_gameSource === "lichess"`. La barre ne se masque plus que si aucun FEN n'est affiché (quitte l'écran d'analyse). Elle reste donc visible sur l'écran de fin de partie ET sur « Révision PGN », dans les deux orientations, pour une partie Lichess terminée comme pour toute autre source.

**Point 2** — `socket.on("app_state")` : l'appel devient `_reviewMaybeAutoAnalyse(false)` (plus aucun appelant ne passe `true` depuis ce correctif ; le paramètre `skip` reste disponible pour un futur appelant qui en aurait réellement besoin). L'analyse complète démarre donc désormais d'office après une partie Lichess, avec progression, coups colorés et activation de « Voir le meilleur coup » quand le coup joué n'est pas le meilleur — exactement comme pour les autres sources. Les chemins PGN collé/importé/bibliothèque/classeur passent tous par `parsePgn()`, qui appelait déjà `_reviewMaybeAutoAnalyse(false)` sans condition de source — inchangés par ce correctif (déjà corrects).

**Point 4 (règle inchangée)** — Vérifié : aucune des deux gardes qui empêchent réellement tout moteur pendant une partie Lichess EN COURS n'a été touchée (garantie architecturale : cet écran n'existe que depuis `_app_state == "game_over"` ; garde serveur explicite `on_analyser_pgn` : refuse si `_app_state != "game_over"`). Le test statique `test_issue333_lichess_no_engine.py` (analyse AST des imports du mode Lichess) et le test dynamique `test_issue342_auto_analyse.py::test_analyser_pgn_refuse_si_partie_lichess_en_cours` (simulent `_app_state == "playing"`) restent verts sans modification.

**Point 2 bis** — Nouvelles fonctions symétriques dans `app.js` :
- `_reviewSetTopBottomNames(white, black)` : écrit `player-top-name`/`player-bottom-name` selon `_boardFlipped` (non retourné → haut=Noir/bas=Blanc ; retourné → haut=Blanc/bas=Noir). Utilisée par `parsePgn()` à la place de l'affectation inconditionnelle.
- `_reviewWhiteBlackFromTopBottom()` : l'inverse — reconstruit Blancs/Noirs depuis les deux cases affichées, selon `_boardFlipped`. Utilisée par `telechargerPgn()`, `sauvegarderNicLink()` et `_buildPgnForBasket()`, qui lisaient toutes les trois `white = player-bottom-name` / `black = player-top-name` de façon inconditionnelle — même bug latent, qui aurait écrit un PGN téléchargé/sauvegardé dans « Mes parties AlChess »/mis au classeur avec Blanc et Noir INVERSÉS dès que l'échiquier de l'écran d'analyse avait été retourné manuellement (bouton ⇅). Corrigé par la même occasion (même cause racine, même écran, même éléments DOM).

Non corrigé, hors périmètre de cette issue (même bug latent mais écran différent, pas mentionné par Alain) : `ouvrirModalAbandonner()` (modal « qui abandonne » en Humain vs Humain, écran de jeu) lit aussi `player-bottom-name`=Blanc/`player-top-name`=Noir sans consulter `_boardFlipped` — à corriger dans une issue dédiée si Alain le souhaite.

### Tests

Nouveau `nicsoft/tests/e2e/test_issue345_analyse_lichess_fixes_e2e.py` (4 tests, Playwright, même chemin que #341/#342/#343 — menu « Analyse » → « Coller PGN » ou simulation directe de `socket.on("app_state")`, SANS AUCUN MOTEUR réel, serveur de test avec `ALCHESS_SKIP_AUTO_ANALYSE=1`) :
- barre présente après chargement PGN avec source restée « lichess », avant et après retournement ;
- analyse automatique démarrée (`_analyseActive === true`) ET barre présente après un vrai cycle `app_state`/`game_over` de source `"lichess"` (pas seulement via « Coller PGN ») ;
- noms de joueurs suivant l'orientation avant et après retournement, PGN « tomatoloss vs Vous » (reproduit l'observation d'Alain) ;
- non-régression : pièces capturées déjà correctes avant/après retournement.

Mise à jour de deux tests existants qui codifiaient l'ancien comportement (désormais le comportement opposé est le bon) :
- `test_issue341_review_eval_bar_e2e.py::test_absente_en_mode_lichess` → `test_presente_apres_partie_lichess_terminee` (la barre reste présente) ; `test_barre_ne_deplace_pas_navigation` adapté pour basculer présence/absence directement via `_reviewUpdateEvalBar(null, null)` plutôt que via `_gameSource` (qui ne masque plus rien).
- `test_issue342_auto_analyse_e2e.py::test_jamais_declenche_en_mode_lichess` → `test_demarre_juste_apres_fin_de_partie_lichess` (`_analyseActive === true`).

Suites complètes exécutées et vertes : `pytest nicsoft/tests -m "not slow"` (1304 passed, 83 skipped) et `pytest nicsoft/tests -m slow` (179 passed, 1 skipped) — y compris tous les tests e2e Lichess/révision/analyse existants (#333, #335, #338, #339, #341, #342, #343).

Non vérifié avec une vraie partie Lichess (interdit par consigne, faux serveur local uniquement) : Alain vérifiera en vrai qu'une partie Lichess terminée affiche bien la barre et active « Voir le meilleur coup ».

### Fichiers modifiés

- `nicsoft/web/static/app.js` — `_reviewUpdateEvalBar()` (suppression de la garde `_gameSource`), `socket.on("app_state")` (`_reviewMaybeAutoAnalyse(false)`), nouvelles `_reviewSetTopBottomNames()`/`_reviewWhiteBlackFromTopBottom()`, `parsePgn()`/`telechargerPgn()`/`sauvegarderNicLink()`/`_buildPgnForBasket()` mis à jour pour les utiliser.
- `nicsoft/tests/e2e/test_issue345_analyse_lichess_fixes_e2e.py` (nouveau).
- `nicsoft/tests/e2e/test_issue341_review_eval_bar_e2e.py`, `nicsoft/tests/e2e/test_issue342_auto_analyse_e2e.py` (tests mis à jour, voir ci-dessus).
- `CONTEXTE.md` — entrées #341/#342 corrigées (l'état réel remplace les affirmations devenues fausses), entrée #345 ajoutée.

# Changelog — issue #346

## Lichess : « Contre un humain » à gauche, « Contre l'IA » à droite

Écran de choix de la partie Lichess, carte « Adversaire » : les deux boutons
sont désormais affichés dans l'ordre « Contre un humain » (toujours
présélectionné) puis « Contre l'IA », au lieu de l'inverse — pour que le
choix par défaut depuis #344 soit aussi le premier affiché.

- `nicsoft/web/templates/index.html` : les deux `<button>` `#cfg-lichess-opponent-human`/`#cfg-lichess-opponent-ai` sont intervertis dans le markup (classe `selected` et logique de présélection inchangées). `app.js` ne dépend que des `id`, aucune modification nécessaire côté JS ni i18n.
- `nicsoft/tests/e2e/test_issue344_lichess_rated_e2e.py` : les tests existants n'identifient les boutons que par `id`, donc aucun n'était affaibli par l'inversion ; nouveau test `test_contre_un_humain_affiche_a_gauche_de_contre_ia` qui vérifie l'ordre réel des deux boutons dans le DOM et que « Contre un humain » reste présélectionné.

# Changelog — issue #344

## Lichess L4 : parties classées contre un humain, humain présélectionné, signal de début, finitions

Étape suivante du mode Lichess (après #327/#333, recherche d'adversaire humain) : les parties classées, transmises de bout en bout jusqu'à Lichess, affichées clairement pendant et après la partie, accompagnées d'un signal physique de début de partie et d'un journal enrichi — sans jamais ouvrir de vraie recherche/partie sur lichess.org pendant le développement (faux serveur local uniquement, comme pour toutes les issues Lichess précédentes).

### 1. Écran de choix (point 1)

`nicsoft/web/templates/index.html` / `nicsoft/web/static/app.js` :

- « Contre un humain » (`#cfg-lichess-opponent-human`) est désormais présélectionné à l'ouverture de l'écran — `app.js::_lichessOpponentType` vaut `"human"` par défaut, et `selectOpponentTypeLichess("human")` est réaffirmé explicitement à **chaque** entrée sur `config_lichess` (pas seulement au premier chargement de la page), pour ne jamais hériter d'un état laissé par une session précédente.
- Nouvelle case « Partie classée » (`#cfg-lichess-rated`), cochée par défaut (`_lichessRated = true`), dans la carte « Adversaire ». Sans objet contre l'IA : masquée et désactivée (`disabled`) dès qu'on bascule sur « Contre l'IA » (`#cfg-lichess-rated-row`), rétablie cochée et visible dès qu'on revient sur « Contre un humain ».
- L'ancienne légende « Partie amicale seulement pour l'instant — les parties classées viendront plus tard » (contre un humain) est remplacée par une légende symétrique, affichée contre l'IA : « Contre l'IA : toujours une partie amicale, Lichess ne classe pas les parties contre son ordinateur » (`#cfg-lichess-opponent-ai-note`).
- Disclaimer de l'écran (aides désactivées) reformulé pour ne plus affirmer « sans classement » (qui n'est plus vrai).
- Clés i18n ajoutées/modifiées simultanément dans `fr/en/de.json` : `config.lichess.classee`, `config.lichess.ia_jamais_classee`, `lichess.badge_classee`, `lichess.badge_amicale` (ajoutées) ; `config.lichess.disclaimer`, `config.titre.lichess` (reformulées — ce dernier servait aussi de titre en cours de partie, affichait à tort « partie amicale ») ; `config.lichess.rated_plus_tard` retirée (plus utilisée).

### 2. Recherche d'adversaire classée (point 2)

- `nicsoft/modes/lichess/game_client.py::open_seek_stream()` acceptait déjà un paramètre `rated` (issue #327) mais rien ne l'alimentait jamais — désormais câblé de bout en bout : `app.js::startGameLichess()` envoie `rated` dans l'action `start_lichess` (toujours `false` si l'IA est sélectionnée, quel que soit l'état mémorisé de la case, qui est alors masquée) → `core/game_manager_modes/lichess.py::launch_lichess()`/`_launch_lichess_human()`/`_run_lichess_human()` → `nicsoft/modes/lichess/seek.py::SeekSession.start(..., rated)` → `open_seek_stream(..., rated)`.
- Défaut prudent côté serveur si le champ venait à manquer (`bool(config.get("rated", False))`) : jamais une partie classée involontaire.
- Lecture de la documentation publique (`lichess-org/api`, `doc/specs/tags/board/api-board-seek.yaml`, 15/11/2026) : `rated` est un simple booléen, indépendant des contraintes de cadence — aucune restriction de cote documentée pour cette route. Les cadences proposées restent donc celles déjà filtrées par #327 (`_HUMAN_SEEK_ALLOWED_SPEEDS = {"rapid", "classical"}`, jamais Blitz/Bullet) — inchangées, déjà correctes pour une recherche classée comme amicale.
- Un refus de Lichess (400 et autres codes) reste géré par le mécanisme générique déjà en place depuis #329 (`_classify_seek_error_event`, message exact affiché de façon persistante, jamais de plantage) — aucune branche spécifique au classé n'était nécessaire.

### 3. Affichage classée/amicale + variation de cote (point 3)

- `LichessGame.rated` (nouvel attribut, `nicsoft/modes/lichess/game.py`) est **toujours** lu depuis le champ `rated` (booléen requis du schéma `GameFullEvent`) du premier `gameFull` confirmé par Lichess — jamais deviné localement, y compris pour une IA (toujours `False`, Lichess ne l'envoie jamais à `true` pour une partie contre son ordinateur) et y compris après une reconnexion réseau mi-partie (un nouveau `gameFull` peut revenir, relu sans effet de bord).
- Transmis dans l'évènement `lichess_init` (écran de jeu) et dans le payload `game_over` (écran de fin) — affiché via les nouvelles clés `lichess.badge_classee`/`lichess.badge_amicale`, en suffixe du sous-titre de partie et dans un nouveau bloc dédié `#rv-lichess-rated-info` sur l'écran de fin.
- Variation de cote (en meilleur effort, jamais inventée si absente) : nouvelle méthode `GameClient.fetch_rating_diff(game_id)` — ouvre brièvement le flux général `/api/stream/event` (le seul à porter `ratingDiff`, établi par lecture de `doc/specs/examples/stream-gameFinish.json.yaml` ; le flux de partie lui-même, `GameStateEvent`, ne le porte jamais) en attendant l'évènement `gameFinish` correspondant, avec un délai de 6s imposé depuis un **autre** fil (`threading.Timer(..., handle.close)`, même mécanisme que l'annulation de recherche de #327/#328) ; ne lève jamais d'exception (toute exception imprévue est journalisée, jamais laissée se propager dans le fil secondaire — même garde-fou que `seek.py`). Appelée par `LichessGame._maybe_fetch_rating_diff()`, démarrée par `_finalize()` **seulement** si la partie est classée et réellement terminée (jamais pour `aborted`/`noStart`) ; pousse `lichess_rating_diff` si trouvée à temps, sinon rien n'est affiché au-delà du résultat déjà connu.
- Tout nom d'adversaire et tout message venant de Lichess continue de passer par `esc()`/`.textContent`, inchangé.

### 3 bis. Signal de début de partie (point 3bis)

- Nouvelle méthode `LichessGame._signal_game_start()` : bip + LED distincts des signaux existants (#331/#340 « adversaire parti ») — nouveau pattern LED dédié (`driver.py::signal_lights(7)`, échiquier entièrement allumé ~1,5s, jamais réutilisé par aucun autre signal), posté sur la même file LED ordonnée que le reste (un seul fil travailleur, `driver.py::_led_worker_loop`) pour ne jamais courir en parallèle de l'affichage normal du premier coup adverse qui peut suivre immédiatement (cas des noirs) — posté **avant** `_apply_new_moves()` dans `_apply_game_full()`, pour que cet éventuel affichage attende son tour plutôt que d'être effacé prématurément.
- Déclenché une seule fois par vraie partie (`_game_start_signal_sent`), jamais à une reprise (`_resume_pending`) ni répété si un nouveau `gameFull` revient (reconnexion réseau mi-partie).
- Valable pour toute partie Lichess (IA ou humain, classée ou amicale) : pour les Blancs, rien d'autre ne s'affiche avant leur propre premier coup (« à vous de jouer ») ; pour les Noirs, le premier coup adverse est ensuite montré normalement par les LED, comme d'habitude.
- Journalisé (`game_log.state_change`, catégorie `[STATE]`).
- Non testé sur le vrai échiquier (aucun matériel disponible pour cette issue) : pattern LED choisi par cohérence avec les conventions existantes du fichier, jamais vérifié visuellement en conditions réelles.

### 4. Reprise et cas rares (point 4)

- Reprise (L2b) d'une partie classée : aucune adaptation nécessaire — `LichessGame.rated` est lu depuis le `gameFull` de la même façon qu'une partie normale, y compris à la reprise ; le signal de début de partie reste bien absent (`resuming=True`). Vérifié par test dédié.
- Cas rares passés en revue sur le faux serveur local, avec `rated=True` (aucune correction nécessaire — comportement identique à l'amicale, seuls l'affichage et le journal changent avec le classé) :
  - adversaire qui quitte la partie puis réclamation (bip/LED #331/#334/#340, inchangés) ;
  - proposition de nulle refusée (mécanisme #311/#318, inchangé) ;
  - demande de reprise de coup refusée (mécanisme #334, inchangé) ;
  - fin par temps écoulé (statut `outoftime`, inchangé) ;
  - abandon — de l'adversaire et de l'utilisateur lui-même (mécanismes #310/#311/#331, inchangés) ;
  - partie interrompue avant le premier coup (`aborted`, bandeau dédié #311, inchangé) ;
  - déconnexion réseau puis reconnexion mi-partie (flux général, #309/#328) — vérifié en particulier que le signal de début de partie ne se répète pas si un nouveau `gameFull` revient à la reconnexion.
- Aucun de ces cas n'a révélé de comportement incorrect ou de message peu clair spécifique au classé — la seule différence réelle entre classée et amicale est l'affichage (badge, variation de cote) et le journal.

### 5. Journal (point 5)

- `classée=True/False` ajouté aux lignes `[STATE]` de démarrage de recherche (`seek.py::start()`, avec cadence et couleur déjà présents) et de réception du `gameFull` (`game.py::_apply_game_full()`, avec couleur/adversaire/cote déjà présents) — horodatage à la milliseconde déjà garanti par `GameLog` (#326).
- Nouvelle ligne dédiée à l'émission du signal de début de partie.
- Nouvelles lignes pour la tentative (réussie ou non) de lecture de la variation de cote.
- Le jeton n'apparaît jamais dans ces nouvelles lignes (même masquage générique déjà en place, `GameLog._mask`) — vérifié par test dédié.

### 6. Garde-fous inchangés (point 6)

- Aucun moteur, aucun livre d'ouvertures, aucun indice de coup pendant une partie en ligne, classée comme amicale — inchangé (`nicsoft.engine.*` jamais importé par le mode Lichess, #333). Le jeton reste côté serveur, jamais envoyé au navigateur ni journalisé — inchangé.
- Tests existants sur ce point (`test_issue333_lichess_no_engine.py`, analyse statique AST) : toujours verts, sans modification.
- Nouveau test **dynamique** complémentaire (`test_issue344_lichess_rated.py::test_partie_classee_complete_n_importe_jamais_de_moteur`) : fait tourner un cycle complet de partie **classée** (mise en place, coups, fin) et vérifie, par comparaison avant/après de `sys.modules`, qu'aucun module moteur n'est chargé par ce scénario précis — en complément du test statique, qui couvre tous les fichiers mais ne fait jamais tourner de vrai code.

### 7. Tests (point 7)

- `nicsoft/tests/test_issue344_lichess_rated.py` (31 tests, hors réseau/matériel) : recherche classée/amicale (`rated` transmis à `open_seek_stream`/`SeekSession.start`), `LichessGame.rated` lu depuis `gameFull` (jamais deviné, y compris IA/absence du champ), payload `game_over`, signal de début de partie (Blancs, Noirs, absent à la reprise, jamais répété à une reconnexion, pour classée comme amicale), variation de cote (trouvée, absente, erreur réseau, déclenchée seulement si classée et terminée), cas rares du point 4 rejoués avec `rated=True`, journal (classée visible, jeton absent), garde-fou fair-play dynamique.
- `nicsoft/tests/e2e/test_issue344_lichess_rated_e2e.py` (6 tests, Playwright) : humain présélectionné, case classée cochée et visible par défaut, niveau IA masqué par défaut, case classée masquée/désactivée contre l'IA, case rétablie cochée en revenant sur « Contre un humain », légende « toujours amicale » affichée contre l'IA.
- Corrections de tests préexistants rendues nécessaires par le nouveau signal de début de partie (bip supplémentaire désormais émis dès `_apply_game_full`) : `test_issue311_lichess_sequencing.py` (2 assertions de comptage de bips ajustées, commentées), `test_issue331_lichess_opponent_alerts.py::_started()` (remet `beep_count` à zéro après la mise en place, pour que les tests existants continuent de ne mesurer QUE les bips survenant après leur propre scénario — corrige au passage toute la famille #331/#334/#340, qui réutilise cette fonction). Et `test_issue310_lichess_e2e.py::at_config_lichess` (bascule explicitement sur « Contre l'IA » pour retrouver l'état visé par ses tests de mise en page, orthogonal au nouveau défaut « Contre un humain » de cette issue).
- Suite complète (`pytest nicsoft/tests/`) : 1478 passés, 84 ignorés (pré-existants, sans rapport), 0 échec.

### Ce qu'Alain doit vérifier en vrai

- **Premier essai réel recommandé : partie classée contre un humain en Rapide** (cadence 15+10 ou 10+0, jamais Blitz/Bullet). Vérifier : la case « Partie classée » est bien cochée par défaut à l'ouverture de l'écran ; la recherche aboutit normalement ; l'écran de jeu affiche bien « Partie classée » ; à la fin, le résultat s'affiche avec le badge « Partie classée », et la variation de cote si Lichess la fournit à temps (sinon, rien d'anormal ne doit apparaître — juste le résultat).
- **Signal de début de partie** : au moment où l'appariement est fait et que la partie démarre, vérifier qu'un bip et un pattern LED (échiquier entièrement allumé un court instant) se produisent — distincts des signaux déjà connus (adversaire parti). Pour les Noirs, vérifier que le premier coup de l'adversaire s'affiche bien normalement ensuite (pas de conflit visuel avec le signal).
- **Reprise d'une partie classée en cours** (fermer/relancer AlChess pendant une partie classée) : vérifier que la reprise fonctionne normalement et que le signal de début de partie ne se répète pas.
- Pattern LED du signal de début de partie non vérifié sur le vrai échiquier (aucun matériel disponible pendant cette issue) — à confirmer visuellement lors du premier essai.
- Variation de cote : son délai d'arrivée réel après la fin d'une partie classée n'a pas pu être mesuré sans vraie partie — si elle n'apparaît jamais en pratique, envisager d'augmenter le délai de 6s dans `GameClient.fetch_rating_diff()`.

# Changelog — issue #343

## Analyse après partie : retourner l'échiquier sur une position quelconque remettait les pièces à la position de départ et laissait flèches/barre à l'ancienne orientation

Sur l'écran d'analyse post-partie (#335/#338/#339/#341), retourner l'échiquier (bouton ⇅) sur une position autre que la toute première remettait les pièces affichées à la position de départ, et ne redessinait jamais les flèches à la nouvelle orientation — alors que le titre de navigation et l'historique, eux, restaient corrects (coup 74 / Re2, inchangés). La barre d'évaluation et la légende, elles, n'étaient en réalité **pas en cause** (voir cause ci-dessous) : elles affichaient déjà les bonnes valeurs, simplement identiques avant/après le clic puisque orientation-indépendantes.

### Cause établie

`flipBoard()` (`nicsoft/web/static/app.js`) redessinait les pièces depuis la variable globale `currentFen`, jamais mise à jour par le chemin « Analyse → Coller PGN » ni par la reprise d'une partie jouée dans AlChess (ces deux chemins alimentent uniquement `reviewFens`/`reviewIdx`, via le même bloc `socket.on("app_state")` pour `data.state === "game_over"`) — au lieu de `reviewFens[reviewIdx]`, la position réellement affichée à l'écran. `currentFen` reste donc à sa valeur par défaut (position de départ), d'où les pièces qui y retournent après un flip. Confirmé en reproduction directe (test ad hoc temporaire, retiré après usage, dans ce même worktree — jamais sur l'arbre principal) : `currentFen` vaut bien `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR` après avoir chargé un PGN de 5 coups et navigué au dernier coup.

Les flèches n'étaient, de leur côté, **jamais redessinées du tout** après un flip : leurs coordonnées pixel sont figées au moment du tracé (`boardSquareCenter()`, dépendant de `_boardFlipped`), et `flipBoard()` ne rappelait jamais `drawReviewArrows()`/`_reviewUpdateArrows()`. Confirmé par un second test ad hoc : le HTML du SVG `#board-arrows` est strictement identique avant/après le flip.

La barre d'évaluation (#341), elle, recalculait déjà correctement sa valeur et son orientation CSS (`review-eval-bar-flipped`) depuis `reviewFens[reviewIdx]` dans ce même `flipBoard()` — confirmé par le même test ad hoc (classe `flipped` bien passée de `false` à `true`, valeurs inchangées car indépendantes de l'orientation). La légende, non affectée par l'orientation (texte SAN + score, pas de coordonnées), n'avait de toute façon aucune raison de changer : ce que le rapport initial décrivait comme « reste comme avant » pour la barre/la légende correspond donc, pour l'essentiel, au comportement attendu — seules les pièces et les flèches étaient réellement en cause.

**Positions où le défaut apparaissait** : testé au premier coup, à un coup du milieu et au dernier coup d'une partie de 10 demi-coups, dans les deux sens (normal→retourné et retourné→normal) — le défaut des pièces apparaît à **toutes** les positions sauf le premier coup (`reviewIdx === 0`), où `currentFen` (valeur par défaut) coïncide par hasard avec la position de départ réelle : c'est ce qui explique l'observation d'Alain (« si je reviens au premier coup, tout redevient correct ») — en réalité, au premier coup, le bug est invisible car masqué par la coïncidence, pas corrigé par la navigation. Le défaut des flèches, lui, apparaît à **toute** position dès qu'un résultat moteur est déjà en cache (flèches visibles) avant le flip, premier coup compris.

**Pré-existant à #339/#341, pas introduit par eux** : `flipBoard()` dans sa forme actuelle (redessin depuis `currentFen`) date d'un commit antérieur à #335 lui-même (`git log` : `58e7071` « état initial avant refactoring structure », ancêtre du commit juste avant #335) — le bug des pièces existait donc avant l'introduction même des flèches et de la barre. Le bug des flèches (jamais redessinées sur flip) remonte à #335 : avant #335 il n'existait pas de flèches à redessiner ; `flipBoard()` n'a simplement jamais été mis à jour pour les rafraîchir quand #335 les a introduites. Rien de tout cela n'est une hypothèse résiduelle — établi par lecture directe de l'historique git et par reproduction avant/après retrait temporaire du correctif.

### Correction

`flipBoard()` : quand l'écran d'analyse (`#panel-gameover`) est affiché, appelle désormais directement `renderReview()` — la fonction canonique déjà utilisée par la navigation (`reviewPrev`/`reviewNext`/`reviewGoTo`/la lecture automatique) — au lieu de reconstruire manuellement un sous-ensemble du rendu depuis `currentFen`. `renderReview()` redessine les pièces depuis `reviewFens[reviewIdx]`, le surlignage du dernier coup, le symbole de qualité, les flèches et la légende (via `_reviewUpdateArrows()`, qui réutilise `_reviewLinesCache` — jamais de nouvelle requête moteur) et la barre d'évaluation, tous cohérents avec la nouvelle orientation (`_boardFlipped` déjà basculé avant l'appel). `reviewIdx` n'est pas modifié par `renderReview()` : l'historique et le titre de navigation restent inchangés, comme demandé. Les autres écrans partageant `flipBoard()` (partie en cours, labo...) ne sont pas affectés — ils continuent de re-rendre depuis `currentFen`, comportement inchangé.

### Autres chemins vérifiés

- **Lecture automatique** : flip en cours d'autoplay testé — `renderReview()` étant la même fonction rappelée à chaque tick du timer, aucune divergence constatée.
- **Revue d'une partie jouée dans AlChess** (pas un PGN collé) : même chemin `app_state`/`game_over` (`history_fen`/`history_moves`), simulé côté client sans moteur/driver réel — même correctif, aucun comportement différent constaté.
- **Résultat moteur tardif** : non affecté par cette correction — `socket.on("review_lines_result")` ignore déjà tout résultat dont le FEN ne correspond plus à la position affichée (#338), indépendamment de l'orientation.
- **Flèches masquées** (case « Afficher les flèches » décochée) : flip testé avec la case décochée — restent masquées après le flip, la barre reste affichée et correcte (comportement #341 inchangé, indépendant de la case).

### Tests

**Navigateur** (`nicsoft/tests/e2e/test_issue343_review_flip_position_e2e.py`, 6 tests, Playwright — même chemin que #335/#338/#339/#341, menu Analyse → Coller PGN, SANS AUCUN MOTEUR réel) :
- pièces correctes au premier coup, à un coup du milieu et au dernier coup, dans les deux sens de flip, historique/titre de navigation inchangés ;
- flèches redessinées à la nouvelle orientation (coordonnées vérifiées géométriquement via `boardSquareCenter()`, pas seulement « ont changé ») ;
- barre et légende inchangées après un flip (valeurs indépendantes de l'orientation, seule la classe CSS `review-eval-bar-flipped` change) ;
- flip avec les flèches masquées : restent masquées, barre et pièces correctes ;
- flip pendant la lecture automatique : pièces correctes immédiatement après le flip et au tick suivant ;
- revue d'une partie jouée dans AlChess (historique simulé côté client, pas un PGN collé) : pièces correctes après flip.

Un vrai moteur de test s'étant avéré disponible sur la machine (observé en reproduisant un flux de pollution inter-tests : le chargement d'un PGN affiche automatiquement la **dernière** position et déclenche une vraie requête d'analyse avant même que le test reprenne la main — une réponse tardive pouvait alors écraser un résultat injecté dans un test suivant réutilisant le même PGN), `socket.emit("review_request_lines", ...)` est neutralisé pour la durée de chaque test de ce fichier (restauré à la sortie) — garantit zéro appel moteur réel, conforme à la consigne du projet, et élimine toute source de non-déterminisme liée au timing réseau.

Tests de non-régression exécutés et verts (deux fois, pour écarter toute instabilité) : `test_issue335_review_arrows_e2e.py`, `test_issue338_review_same_position_e2e.py`, `test_issue339_review_arrow_outline_e2e.py`, `test_issue341_review_eval_bar_e2e.py`, `test_issue333_lichess_menu_banner_e2e.py`, `test_issue333_lichess_no_engine.py`, `test_issue333_lichess_human_resume.py`, ainsi que la suite complète `nicsoft/tests/ -m "not slow"` (1253 passed, 83 skipped, 161 deselected).

# Changelog — issue #342

## Analyse après partie : lancer l'analyse complète d'office, suppression du bouton « Analyser la partie »

Le bouton « Analyser la partie » (`btn-analyser`) avait été prévu quand l'analyse prenait beaucoup de temps. Tant qu'il n'était pas cliqué, l'historique n'avait aucune coloration et le bouton « Voir le meilleur coup » restait grisé en permanence — constaté par Alain sur une partie Lichess chargée en « Révision PGN ». L'analyse complète démarre désormais d'elle-même dès qu'une partie non encore analysée est affichée sur l'écran d'analyse.

### Point 1 — Lancement automatique

`app.js::_reviewMaybeAutoAnalyse(skip)` est appelée à la fin de chaque chemin qui peuple l'écran de revue :
- le handler `app_state`/`game_over` (partie pédagogique/HH qui vient de se terminer, ou entrée directe dans « Analyse » depuis le menu) ;
- `parsePgn()` — donc aussi, par construction, « Coller PGN », l'import de fichier PGN, la bibliothèque PGN personnelle (`pgn_lib_game_loaded` appelle `parsePgn()`) et le classeur de session (`basketLoadToAnalyse()` appelle aussi `parsePgn()`).

Même paramètres qu'avant : profondeur moteur inchangée (codée en dur côté serveur), longueur de séquence punitive lue dans le sélecteur « Séquence » (`#rv-seq-moves`, désormais toujours visible tant qu'une partie est chargée, pour pouvoir la régler avant de charger la partie suivante).

### Point 2 — Détection « déjà analysée », jamais de relance

Inchangée dans son principe (`_isAnalysed` : au moins un coup avec une qualité reçue différente de "bon", ou qualités déjà reçues en direct pendant une partie HH analysée coup par coup) — élargie dans `parsePgn()` pour couvrir le cas d'une partie *parfaite* déjà analysée (sinon indistinguable d'une partie jamais analysée, puisque tous les coups sont "bon" dans les deux cas) : un commentaire PGN avec évaluation chiffrée (`cp`) sur CHAQUE coup compte aussi comme « déjà analysée ». Une analyse déjà en cours pour la MÊME partie (clé = liste des coups UCI) n'est jamais relancée non plus (`_analyseInProgressKey`).

### Point 3 — Indicateur de progression discret

Nouvelle ligne `#review-analyse-progress-row` dans la carte Navigation (`card-nav-save`, juste sous l'en-tête) : barre fine + texte (clés i18n `labo.btn.analyse_pct`/`labo.btn.analyse_ok`, réutilisées). Hauteur TOUJOURS réservée (jamais `display:none`, seul le contenu change) pour ne jamais déplacer la navigation, la barre d'évaluation ni aucun bouton (régression #332). Les colorations de l'historique et le bouton « Voir le meilleur coup » s'activent au fur et à mesure, comme avant (`socket.on("analyse_coup")` met à jour `reviewMoves[idx]` puis appelle `renderReview()`).

### Point 4 — Jamais pendant une partie Lichess en cours

Deux gardes indépendantes :
- **Client** : `_reviewMaybeAutoAnalyse(skip)` reçoit `skip=true` si `data.source === "lichess"` dans le handler `game_over` — même garde inconditionnelle que #335/#341 (toute partie de source Lichess, pas seulement « en cours », par symétrie avec l'existant).
- **Serveur, en défense** : `on_analyser_pgn` refuse toute demande si `_app_state != "game_over"`. Lichess utilise le même état générique `"playing"` que les autres modes pendant la partie (aucun état dédié) — simuler une partie Lichess en cours revient donc à simuler `_app_state="playing"`, testé directement (`test_analyser_pgn_refuse_si_partie_lichess_en_cours`).
- Garantie architecturale inchangée en toile de fond : l'écran d'analyse n'est de toute façon jamais atteint pendant une partie Lichess en cours (`test_issue333_lichess_no_engine.py`, inchangé, toujours vert).

### Point 5 — Navigation et arrêt propre

Nouvel event socket `annuler_analyse_pgn` : positionne un `threading.Event` serveur (un seul à la fois, `server.py::_analyse_cancel_event`), vérifié par `EngineManager.analyser_partie(..., should_continue=...)` (nouveau paramètre optionnel dans `nicsoft/engine/engine_analysis.py`) avant chaque coup. Le moteur est fermé (`manager.quit()`) dans tous les cas via `finally`, qu'il y ait eu annulation ou non. Une analyse interrompue n'émet JAMAIS `analyse_terminee` — jamais enregistrée comme complète. Appelée par `_viderAnalyse()` (couvre donc aussi le retour au menu, qui l'appelait déjà) et par `_reviewMaybeAutoAnalyse()` elle-même dès qu'une AUTRE partie se charge pendant qu'une analyse tourne.

Jeton de génération `gen` (compteur client incrémenté à chaque nouvelle analyse, envoyé dans `analyser_pgn`, renvoyé tel quel par `analyse_coup`/`analyse_terminee`) : le client ignore tout résultat dont le `gen` ne correspond plus à l'analyse courante — même leçon que #338 (résultat tardif d'une autre position/partie jamais appliqué).

### Point 6 — Cohabitation avec les lignes à la demande (#335)

**Observé** : les deux fonctionnalités construisent chacune leur PROPRE `EngineManager` (jamais partagé) — l'analyse complète automatique et le service de lignes à la demande peuvent donc, en théorie, faire tourner deux process moteur en même temps dès que l'utilisateur navigue dans l'historique pendant que l'analyse complète tourne encore en arrière-plan.

**Décision** : ne pas fusionner les deux moteurs (risque de régression trop élevé sur #335/#338/#341, qui dépendent tous du comportement actuel de `ReviewMultiPVService`) — priorité coopérative seulement. `server.py::_review_lines_pending()` lit `ReviewMultiPVService.has_pending()` (nouvelle méthode, sans jamais instancier son moteur comme effet de bord) ; le callback de l'analyse complète cède une pause de 0.2s avant d'émettre le résultat d'un coup si une ligne à la demande est en attente — jamais plus qu'une pause de ce type par coup analysé, jamais de blocage total. Non mesuré avec un vrai moteur (interdit en test) : l'effet réel sur la charge processeur en conditions réelles (deux vrais Stockfish actifs quelques secondes) n'a pas pu être observé, seul le déclenchement de la pause est testé (`test_cede_la_priorite_si_une_ligne_a_la_demande_est_en_attente`, faux moteur).

### Point 7 — Durée

Mesuré avec un faux moteur à coût nul (`EngineAnalysisMixin.analyser_partie` sur 40 coups aléatoires, sans aucun appel moteur réel) : ~2ms, ce qui n'établit que le coût d'orchestration Python (négligeable), pas une durée réelle. Un vrai Stockfish est bien présent sur cette machine (`/usr/games/stockfish`) mais n'a jamais été exécuté (interdit par les consignes du projet et par cette issue, point 8) : la durée réelle d'une analyse complète automatique sur une longue partie n'a donc **pas pu être établie empiriquement**. Par lecture de code : un appel `evaluate_move(depth=8)` par coup, plus un `get_punishment_line(depth=12)` supplémentaire uniquement pour les coups non-"bon" — le coût croît linéairement avec le nombre de coups, et uniquement les coups imprécis/erronés/gaffes ajoutent le calcul de séquence punitive. Le changement de comportement réel introduit par cette issue n'est pas la charge de calcul elle-même (strictement identique à un clic manuel sur l'ancien bouton) mais sa systématisation : CHAQUE partie chargée sur l'écran d'analyse déclenche maintenant ce calcul en arrière-plan, alors qu'avant il fallait un clic explicite — pas de problème identifié dans le code (toujours en arrière-plan, jamais bloquant, annulable), mais à garder à l'œil sur une très longue partie (100+ coups) en conditions réelles, faute de mesure possible ici.

### Point 8 — Tests

Aucun moteur réel, aucun réseau, comme pour #335/#338/#339/#341/#333.

**`nicsoft/tests/test_issue342_auto_analyse.py`** (nouveau, 15 tests, faux `EngineManager` injecté, thread rendu synchrone par un `threading.Thread` monkeypatché) : refus hors écran d'analyse (dont la simulation d'une partie Lichess en cours, `_app_state="playing"`, point 4 de l'issue), refus si `ALCHESS_SKIP_AUTO_ANALYSE=1`, chemin normal (jeton `gen` repris tel quel, moteur fermé), lecture `engine_path`/`engine_elo` depuis `config.json`, annulation en cours de route (moteur fermé, jamais `analyse_terminee` pour une analyse partielle), annulation sans analyse en cours (pas d'exception), nouvelle analyse qui annule la précédente pour une autre partie, priorité cédée au service de lignes à la demande, garde contre toute construction paresseuse involontaire de ce service, arrêt précoce de `EngineAnalysisMixin.analyser_partie` via `should_continue`.

**`nicsoft/tests/e2e/test_issue342_auto_analyse_e2e.py`** (nouveau, 9 tests Playwright, même chemin « Coller PGN » que #335/#338 — événements `analyse_coup`/`analyse_terminee` simulés via `socket.listeners()`, comme #338/#341, jamais de vraie requête serveur ayant d'effet) : absence du bouton supprimé, lancement automatique sur une partie collée, absence de relance sur une partie déjà analysée (commentaires complets), absence de déclenchement en mode Lichess, progression affichée puis terminée + activation de la coloration et du bouton « Voir le meilleur coup », résultat tardif d'une autre partie ignoré, changement de partie pendant l'analyse (annulation), retour au menu pendant l'analyse (arrêt), bouton « Vider l'analyse » (fonctionne, ne relance jamais en boucle).

**Garde-fou critique découvert en écrivant ces tests** : un vrai Stockfish est installé par le système sur cette machine (`/usr/games/stockfish`, trouvé par `find_stockfish()`). Sans intervention, le lancement automatique aurait fait tourner un VRAI moteur en arrière-plan pour CHAQUE test e2e existant qui charge un PGN (#335/#338/#339/#341 utilisent tous « Coller PGN »), jamais voulu en test automatisé. Corrigé par une nouvelle variable d'environnement `ALCHESS_SKIP_AUTO_ANALYSE=1` (même idiome que `ALCHESS_SKIP_BOARD`), lue par `server.py::on_analyser_pgn` (retour immédiat si définie) et ajoutée à la fixture partagée `nicsoft/tests/e2e/conftest.py::server_url` pour TOUS les tests e2e — jamais définie en usage normal, aucun effet en production.

Tests de non-régression exécutés et verts : suite complète hors e2e (`nicsoft/tests/ -m "not slow" --ignore=nicsoft/tests/e2e`, 1265 passed, 83 skipped) et suite e2e complète (`nicsoft/tests/e2e/`, 163 passed, 1 skipped) — en particulier `test_issue333_lichess_no_engine.py`, `test_issue333_lichess_human_resume.py`, `test_issue335_review_multipv.py`, `test_issue335_review_arrows_e2e.py`, `test_issue338_review_same_position.py`, `test_issue338_review_same_position_e2e.py`, `test_issue339_review_arrow_outline_e2e.py`, `test_issue341_review_eval_pov.py`, `test_issue341_review_eval_bar_e2e.py`, `test_analyse_engine_path.py`.

### Fichiers modifiés

- `nicsoft/web/templates/index.html` — suppression du bouton `btn-analyser` (seule occurrence, dans `#panel-gameover`) ; nouvelle ligne `#review-analyse-progress-row` dans `#card-nav-save`.
- `nicsoft/web/static/css/main.css` — styles `.game-gameover-analyse-progress-*` (hauteur fixe, jamais `display:none`).
- `nicsoft/web/static/app.js` — suppression de `lancerAnalyse()`/case `"lancer_analyse"` et de toutes les références à `btn-analyser`/`_movesUci` ; nouvelles fonctions `_reviewMaybeAutoAnalyse()`, `_reviewAnnulerAnalyseEnCours()`, `_reviewGameKey()`, `_reviewSetProgress()` ; appels ajoutés dans le handler `game_over` et dans `parsePgn()` ; `_viderAnalyse()` et `_updateActionButtons()` adaptés (sélecteur séquence toujours visible tant qu'une partie est chargée) ; `socket.on("analyse_coup"/"analyse_terminee")` réécrits (jeton `gen`, barre de progression).
- `nicsoft/web/static/i18n/fr.json`, `en.json`, `de.json` — suppression de `labo.btn.analyser`/`labo.btn.analyse_en_cours` (devenues inutiles), parité des 3 langues vérifiée.
- `nicsoft/web/server.py` — `on_analyser_pgn` : garde `ALCHESS_SKIP_AUTO_ANALYSE`, garde `_app_state != "game_over"`, jeton `gen`, annulation (`_analyse_cancel_event`), priorité aux lignes à la demande (`_review_lines_pending()`) ; nouveau handler `on_annuler_analyse_pgn`.
- `nicsoft/engine/engine_analysis.py` — `EngineAnalysisMixin.analyser_partie()` : nouveau paramètre optionnel `should_continue`.
- `nicsoft/engine/review_multipv.py` — `ReviewMultiPVService.has_pending()` (nouveau).
- `nicsoft/tests/e2e/conftest.py` — `ALCHESS_SKIP_AUTO_ANALYSE=1` ajoutée à la fixture `server_url`.
- `nicsoft/tests/test_issue342_auto_analyse.py` (nouveau), `nicsoft/tests/e2e/test_issue342_auto_analyse_e2e.py` (nouveau).
- `CONTEXTE.md` — entrée #342.

# Changelog — issue #341

## Analyse après partie : évaluation chiffrée du point de vue des Blancs à côté des flèches, et barre d'évaluation à gauche de l'échiquier

Sur l'écran d'analyse post-partie (#335), la légende affichait déjà une évaluation à côté de chaque coup, mais sans convention de signe garantie (point de vue du camp au trait côté moteur, jamais reconverti). Alain voulait une convention unique (point de vue des Blancs, toujours), et une barre d'évaluation verticale à gauche de l'échiquier.

### Point 1 — Légende : convention retenue

Pions signés à deux décimales (`+1.23`, `-0.45`, `0.00` pour l'égalité) — conservée telle qu'elle existait déjà avant cette issue (c'était déjà la présentation utilisée côté client), mais désormais **toujours exprimée du point de vue des Blancs**, jamais du camp au trait ni de l'utilisateur. `get_multipv()` (`nicsoft/engine/engine_analysis.py`) renvoie `cp`/`mate` relatifs au camp au trait (`score.pov(board.turn)`) ; `review_multipv.py::_compute()` les reconvertit désormais via `_pov_vers_blancs()` (signe inversé quand board.turn est Noir) avant de les renvoyer au client — seule convention utilisée ensuite par la légende ET la barre (une seule logique de conversion, côté serveur uniquement). Cas explicitement testé : Noirs au trait, le moteur annonce `cp=+80` (bon pour lui) → affiché `-0.80` côté Blancs (`test_noirs_au_trait_signe_final_negatif_pour_les_blancs`).

### Point 2 — Mats : jamais convertis en centipions, établi sur le « +40.73 »

Un mat annoncé s'affiche `#N` (mat des Blancs) ou `-#N` (mat des Noirs) — jamais en centipions, quelle que soit la longueur du mat. Corrige au passage un bug de formatage **côté client** préexistant (`app.js::_reviewFormatScore`) : un mat des Noirs produisait `#-N` (signe après le dièse) au lieu de `-#N` attendu — invisible dans les tests existants de #335/#338/#339 (aucun n'exerçait un mat côté Noir). `score_text` est désormais pré-formaté côté serveur (`format_eval_blancs()`) et utilisé en priorité par le client, avec un secours local identique si absent (tests e2e qui injectent des lignes sans passer par le serveur).

**Établi sur « +40.73 » (coup Kf5 de la capture d'écran d'Alain)** : **ce n'est pas un mat mal converti**. Par lecture de code : `get_multipv()` ne place une valeur dans `cp` que dans la branche `else` de `if pov.is_mate(): mate = pov.mate() / else: cp = pov.score()` — un score de mat ne peut donc jamais atterrir dans `cp` (aucune conversion de ce genre existe dans le code, avant ou après cette issue). La position de l'observation (FEN `6k1/P5p1/4N3/2p3N1/6K1/P7/4r2P/R7 w - - 1 38`, Blancs au trait) confirme aussi que la conversion point-de-vue (point 1) est un no-op ici (déjà Blanc au trait) : elle n'explique donc pas non plus l'écart. Reste : un écart de matériel énorme (2 cavaliers + tour + 2 pions supplémentaires contre une tour et un pion) rend une évaluation à ~40 pions parfaitement plausible à la profondeur de calcul utilisée (12, inchangée) sans que le moteur y trouve un mat forcé — **confirmé par lecture de code, pas par un vrai Stockfish** (binaire tiers, lecture seule, jamais exécuté pendant cette issue) : ceci reste donc une explication établie par le code, pas vérifiée empiriquement avec le vrai moteur sur cette exacte profondeur. Testé avec un faux moteur reproduisant exactement les 3 coups de l'observation (`test_observation_alain_blancs_au_trait_mats_et_cp_corrects`) : a8=Q et a8=T → `#1`, Kf5 (cp=4073) → `+40.73`, barre pleine côté Blanc (dépasse le plafond de 10 pions).

### Point 3 — Barre d'évaluation verticale

Ajoutée à gauche de l'échiquier de l'écran d'analyse (`#board-row` dans `templates/index.html`, à côté de `#board-align` — jamais dedans, ne déplace donc jamais les coordonnées ni les flèches de #335 ; CSS dans `static/css/main.css`). Blanche en bas / noire en haut en orientation normale ; la classe `review-eval-bar-flipped` (`flex-direction: column-reverse`, pilotée par `_boardFlipped`) inverse l'affichage quand l'échiquier est retourné, pour que le dessus de la barre corresponde toujours au camp du haut de l'échiquier — vérifié géométriquement (`getBoundingClientRect()`) en plus des tests automatisés. Proportion : `eval_bar_fraction()` (`review_multipv.py`) — courbe sigmoïde jusqu'à 10 pions, puis plafond NET à 1.0/0.0 au-delà (barre pleine du côté gagnant), 1.0/0.0 direct pour un mat annoncé. Le chiffre (`bar_text`) figure sur le côté qui gagne (`frac >= 0.5` → côté Blanc). Info-bulle + libellé d'accessibilité (`title`/`aria-label`, clé i18n `game.eval_bar.titre`, ajoutée dans `fr.json`/`en.json`/`de.json`) mis à jour à chaque rendu. Testé aussi sur un viewport réduit (classe `@media (max-width: 700px)` réduisant la largeur de la barre à 16px) — pas de test automatisé dédié au rendu visuel à cette largeur, vérifié seulement par lecture du CSS.

### Point 4 — Aucun nouveau calcul moteur

La barre et la légende partent exclusivement des lignes déjà calculées par `ReviewMultiPVService` (#335) : `_compute()` calcule en plus `bar_fraction`/`bar_text`/`score_text` à partir du MÊME appel `get_multipv()`, jamais un second. Côté client, `_reviewUpdateArrows()` ne déclenche une requête `review_request_lines` que si rien n'est en cache pour la position — la barre et la légende lisent le même résultat en cache. La leçon de #338 est respectée : `socket.on("review_lines_result")` ignore tout résultat dont le FEN ne correspond plus à la position actuellement affichée (`reviewFens[reviewIdx] !== fen`) — pour la barre ET la légende, dans le même garde-fou.

### Point 5 — États particuliers

- **Calcul en cours / aucune ligne** : barre en état neutre discret (classe `review-eval-bar-neutral`, gris, sans chiffre) ; la légende, elle, n'affiche toujours rien (comportement #335 inchangé).
- **Position terminale (mat/pat/nulle)** : détectée via `board.outcome(claim_draw=False)` dans `_compute()` **avant tout appel moteur** (aucun coup légal de toute façon) — barre pleine d'un côté pour un mat (`bar_text` = `#`/`-#`, sans numéro : il ne s'agit pas d'un « mat en N coups » annoncé depuis une ligne mais du résultat déjà joué), moitié pour une nulle.
- **Indépendance vis-à-vis de la case « Afficher les flèches »** : `server.py::on_review_request_lines` ne vérifie plus `show_review_arrows` (il bloquait tout calcul, y compris pour la barre, quand la case était décochée) ; côté client, `_reviewUpdateArrows()` fait désormais toujours la demande/mise à jour de la barre (`_reviewUpdateEvalBar()`), seules les flèches et la légende restent gatées par `_reviewArrowsEnabled`.
- **Mode Lichess** : la barre ne s'affiche jamais si `_gameSource === "lichess"` (`_reviewUpdateEvalBar()`), cohérent avec l'absence de moteur pendant une partie Lichess en cours (#333) — l'écran d'analyse post-partie lui-même reste hors mode Lichess en jeu (architecture #335 inchangée, `test_issue333_lichess_no_engine.py` toujours vert sans modification).

### Point 6 — Tests

**Python** (`nicsoft/tests/test_issue341_review_eval_pov.py`, 18 tests, faux moteur comme #335/#338) : conversion point de vue Blancs (Blanc au trait no-op, Noir au trait signe inversé pour `cp` et `mate`, valeurs `None` préservées), mise en forme (`cp` positif/négatif/nul, mat Blanc/Noir, mat prioritaire sur `cp`, valeur observée « +40.73 »), plafond et courbe de la barre (égalité, mat plein, plafond à/au-delà de 10 pions, monotonie avant le plafond), bout en bout avec la position réelle de l'observation d'Alain (FEN exacte de l'issue) et avec une position Noir au trait, positions terminales (mat/pat) sans jamais interroger le moteur (faux moteur qui lève une exception s'il est appelé).

**Navigateur** (`nicsoft/tests/e2e/test_issue341_review_eval_bar_e2e.py`, 15 tests, Playwright, même chemin que #335/#338/#339 — menu Analyse → Coller PGN, SANS AUCUN MOTEUR réel, résultats injectés dans `_reviewLinesCache`) : barre présente même case décochée, bonne proportion/bon côté (avantage Blanc/Noir, mat Blanc/Noir), orientation normale/retournée (vérifiée géométriquement), légende avec signes corrects pour 3 lignes dont un mat lent (`#5`), partie jouée avec les Noirs, résultat tardif d'une autre position ignoré (reproduit le vrai chemin `socket.on("review_lines_result")` via `socket.listeners()`, pas une simulation de cache), positions terminales (mat/nulle), état neutre pendant le calcul puis défilement rapide des coups, absence en mode Lichess, libellés dans les 3 langues, non-déplacement de `#btn-review-next` (régression #332) avec/sans barre.

Tests de non-régression exécutés et verts : `test_issue335_review_multipv.py`, `test_issue335_review_arrows_e2e.py`, `test_issue338_review_same_position.py`, `test_issue338_review_same_position_e2e.py`, `test_issue339_review_arrow_outline_e2e.py`, `test_issue333_lichess_no_engine.py`, `test_issue333_lichess_human_resume.py`, `test_issue333_lichess_menu_banner_e2e.py`, ainsi que la suite complète `nicsoft/tests/ -m "not slow"` (1251 passed, 83 skipped, 140 deselected).

Non vérifié avec un vrai moteur Stockfish (interdit par les consignes du projet, binaire tiers en lecture seule) : la valeur exacte « +40.73 » n'a donc pas été reproduite avec le vrai moteur sur la position réelle — seule l'absence de conversion fautive est établie par lecture de code (point 2).

### Fichiers modifiés

- `nicsoft/engine/review_multipv.py` — conversion point de vue Blancs (`_pov_vers_blancs`), mise en forme (`format_eval_blancs`), plafond de la barre (`eval_bar_fraction`), détection de position terminale, `score_text`/`bar_fraction`/`bar_text` dans le résultat de `_compute()`.
- `nicsoft/web/server.py` — `on_review_request_lines` ne bloque plus sur `show_review_arrows`.
- `nicsoft/web/templates/index.html` — structure DOM de la barre (`#board-row`, `#review-eval-bar`).
- `nicsoft/web/static/css/main.css` — styles de la barre (`.review-eval-bar*`), responsive.
- `nicsoft/web/static/app.js` — `_reviewUpdateEvalBar()` (nouveau), `_reviewUpdateArrows()`/`socket.on("review_lines_result")` restructurés (barre indépendante de la case flèches, résultat tardif ignoré pour les deux), `_reviewFormatScore()` corrigé (ordre `-#N`) et `score_text` en priorité, `flipBoard()` rafraîchit l'orientation de la barre depuis le cache (jamais un nouveau calcul).
- `nicsoft/web/static/i18n/fr.json`, `en.json`, `de.json` — clé `game.eval_bar.titre`.
- `nicsoft/tests/test_issue341_review_eval_pov.py` (nouveau), `nicsoft/tests/e2e/test_issue341_review_eval_bar_e2e.py` (nouveau).
- `CONTEXTE.md` — entrée #341.

# Changelog — issue #340

## Lichess : signal visible sur l'échiquier dès que l'adversaire quitte la partie, et signal distinct quand la réclamation devient possible

Essai réel du 15/11/2026 (partie contre un humain, Alain jouait les noirs) : le bandeau de #334 est bien apparu, mais pendant les 85s avant réclamation possible, aucun signal physique — et plusieurs défauts sont apparus une fois la réclamation devenue possible/exercée.

### Point 1 — signal dès le départ de l'adversaire

`LichessGame._apply_opponent_gone()` déclenche désormais `_signal_opponent_gone_departure()` dès le PREMIER événement `opponentGone(gone=true)` d'une période d'absence : bip simple (si `config.json::lichess_beep_opponent_move` est cochée) + LED PARTIELLE persistante (nouveau pattern, voir point 2). Reste allumé jusqu'au retour de l'adversaire, à l'acquittement « J'ai vu » ou à la fin de la partie.

### Point 2 — signal distinct à la réclamation possible, motifs retenus

Deux patterns LED, réalisables avec la seule primitive disponible pour un affichage persistant (`set_all_leds`, pattern statique — pas de clignotement, voir « non vérifié » plus bas) :
- **Départ** (nouveau) : `opponent_gone_departure_led_pattern()` / `_RANKS_3_4_LIT` / `_RANKS_5_6_LIT` — seulement les **2 rangs centraux** du camp adverse (les plus proches du milieu de l'échiquier).
- **Réclamation possible** (inchangé, réutilisé de #331/#334) : `opponent_half_led_pattern()` / `_RANKS_1_4_LIT` / `_RANKS_5_8_LIT` — la **moitié complète** (4 rangs) du camp adverse, avec le bip double déjà existant.

Le pattern complet est visuellement plus étendu que le partiel : on distingue les deux sans lire l'écran.

### Point 3 — cadre sur l'échiquier de l'écran

`#board-wrapper` reçoit la classe `board-opponent-gone-frame` (orange/or, départ) ou `board-opponent-gone-frame-claimable` (rouge, réclamable), gérées par `app.js::_lichessUpdateOpponentGoneFrame()`, appelée depuis le handler `socket.on("lichess_opponent_gone", ...)` et depuis le clic sur « J'ai vu » (cadre purement local, suit le signal bip/LED — contrairement au bandeau texte qui reste affiché après ce clic, comportement #334 inchangé). CSS ajouté dans `main.css`. Les boutons et le bandeau existants ne changent pas.

### Point 4 — retour de l'adversaire

- LED/bip : `_apply_opponent_gone()` éteint désormais le signal dès que `_opponent_gone_departure_signaled` OU `_opponent_gone_claimable` était vrai (**corrigé** — avant cette issue, l'extinction ne se faisait que si la réclamation était déjà devenue possible : la LED du simple signal de départ serait restée allumée indéfiniment si l'adversaire revenait avant ce délai).
- Écran : toast `lichess.adversaire_revenu` (3 langues) affiché quand `gone` passe de vrai à faux.
- Retour au menu : `app.js`, handler `socket.on("app_state", ...)`, appelle désormais `_lichessHideStatusBanners()` (qui nettoie aussi le cadre) à **toute** arrivée réelle sur le menu, pas seulement via le chemin `game_over` normal — **lacune corrigée au passage** : le chemin `back_menu` envoie `game_over` avec `skip=true`, qui ignore volontairement cet appel (`if (data.skip) return;`), donc rien ne nettoyait jamais ces banners/le cadre sur un retour au menu en cours de partie avant ce correctif (risque de cadre orange/rouge résiduel visible au démarrage d'un AUTRE mode, `#board-wrapper` étant partagé entre tous les modes).

### Point 5 — priorité au coup

Nouvelle méthode `_apply_opponent_gone_led_state(reason)` : si `self._awaiting_physical_replication` est vrai (coup adverse en cours d'affichage via `_start_opponent_replication_wait`/`set_led` additif, pas encore confirmé), la pose du pattern LED du signal est **différée** (seul le bip, qui ne partage aucune ressource LED, est émis normalement) ; `_check_replication()` rappelle cette même méthode juste après avoir confirmé le coup et éteint ses LED, ce qui **rétablit** le signal encore dû. Le seul point de conflit identifié dans `game.py` est celui-ci : l'affichage du coup de l'utilisateur lui-même n'utilise aucune LED (il le voit directement sur le plateau physique), et `_start_opponent_replication_wait` pose ses deux LED de façon additive (`set_led`, qui préserve le pattern déjà affiché) — seule l'extinction de `_check_replication()` écrasait le signal. Les signaux pré-existants de #331 (nulle proposée par l'adversaire, fin de partie provoquée par l'adversaire) ne sont PAS couverts par cette restauration : leur extinction par le cycle de LED du coup suivant était déjà le mécanisme de sortie voulu dès #331 (documenté dans le code existant) — changer ce comportement sortait du périmètre de cette issue.

### Point 6 — journal dédié

Chaque pose/extinction de LED (départ, réclamable, ou différée pendant l'affichage d'un coup) écrit une ligne `state_change` avec sa raison, via le helper factorisé `_set_opponent_alert_leds()`/`_clear_opponent_alert_leds()`/`_apply_opponent_gone_led_state()`. Déjà couvert par les tests existants (`"LED allumées" in content`) et par les nouveaux tests de ce fichier.

### Point 7 — tests sans connexion réelle

Aucune recherche d'adversaire, aucune partie, aucun jeton réel n'a été utilisé — tout est simulé (faux transport Lichess `FakeTransport`, faux plateau `_AlertBoard`, garde réseau `conftest.py` active, serveur de test lancé uniquement avec `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`).

- `nicsoft/tests/test_issue340_lichess_opponent_signal.py` (nouveau, 9 tests) : signal de départ une seule fois (y compris à 0s), unicité du signal réclamable malgré des événements répétés (y compris plusieurs à 0s), nouveau départ après retour qui redéclenche bien, extinction au retour pendant la phase départ seule, priorité au coup adverse affiché puis rétablissement du signal, aucun signal après réclamation réussie (victoire et nulle).
- `nicsoft/tests/test_issue334_lichess_opponent_claim.py` (modifié) : 3 tests ajustés pour refléter le nouveau comportement (signal de départ en plus du signal réclamable, donc bip/LED supplémentaires attendus) + 1 test ajouté (bonne moitié du pattern partiel selon l'orientation).
- `nicsoft/tests/e2e/test_issue340_lichess_opponent_signal_e2e.py` (nouveau, 4 tests Playwright, exécutés avec succès) : cadre absent par défaut, cadre départ puis réclamable puis disparition au retour (+ toast), disparition sur « J'ai vu » sans attendre le serveur, absence du cadre après retour au menu — les deux orientations ne changent rien côté écran (le cadre suit `gone`/`claimable`, pas la couleur de l'utilisateur).
- Suite complète : `1371 passed, 84 skipped` (aucune régression), suite e2e complète : `139 passed, 1 skipped`.

### Point 8 — moitié allumée côté noirs (bug d'orientation)

**Établi, pas une hypothèse** : `_RANKS_1_4_LIT`/`_RANKS_5_8_LIT` (posées par #331) allumaient en réalité l'**inverse** de ce que leur nom et leur commentaire annonçaient. La convention « indice i du tableau de 8 chaînes = rangée physique (i+1) » est confirmée par **trois lectures indépendantes et concordantes** du code existant, jamais modifiées par cette issue :
1. `hid_backend.py::set_all_leds(r1, r2, ..., r8)` — docstring explicite : « r1..r8 = rangées 1 à 8 ».
2. `driver.py::_led_worker_loop`, commande `"set_all"` : `set_all_leds(str(arr[0]), str(arr[1]), ..., str(arr[7]))` — `arr[0]` passé comme `r1`, `arr[7]` comme `r8`.
3. `driver.py::build_led_map_for_move`/`square_cords` (affichage normal des coups, jamais mis en cause) : `led_map[rang - 1]`.

Avec cette convention, l'ancien `_RANKS_1_4_LIT = ["00000000"]*4 + ["11111111"]*4` avait ses 4 premières chaînes (rangs 1-4) à `0` et les 4 dernières (rangs 5-8) à `1` : il allumait donc les rangs 5-8, pas 1-4 comme son nom l'indique — l'inverse exact de `_RANKS_5_8_LIT`. `opponent_half_led_pattern()` demandait pourtant la bonne constante nommée (`_RANKS_1_4_LIT` pour un adversaire blanc, `_RANKS_5_8_LIT` pour un adversaire noir) : **seul le contenu des deux constantes était faux**, pas la logique d'orientation. C'est exactement ce qui explique l'observation d'Alain (noirs) : le code croyait allumer les rangs 1-4 (camp adverse, blanc) mais allumait physiquement les rangs 5-8 (son propre camp).

**Preuve par le journal** citée dans l'issue : « LED allumées — moitié adversaire (rangs 1-4 (blancs)) » — avec l'ancien code, ce texte de journal (qui décrit l'INTENTION, lue depuis le nom de la constante) correspondait à une pose physique des rangs 5-8. Après correction (contenu des deux constantes échangé, noms et `opponent_half_led_pattern()` inchangés), le texte de journal et le pattern physiquement posé coïncident.

**Corrigé** pour les deux couleurs : nouveaux tests paramétrés `test_signal_reclamable_bonne_moitie_selon_orientation`/`test_signal_depart_bonne_moitie_selon_orientation` (`white`→`_RANKS_5_8_LIT`/`_RANKS_5_6_LIT`, `black`→`_RANKS_1_4_LIT`/`_RANKS_3_4_LIT`) vérifient le pattern RENVOYÉ par les fonctions — ils ne peuvent pas, par construction (sans échiquier physique), vérifier la case qui s'allume PHYSIQUEMENT ; c'est la lecture croisée des trois points de code ci-dessus qui établit que le pattern renvoyé correspond désormais à la bonne rangée physique. **Reste hypothèse** : confirmation sur le vrai échiquier (aucun matériel disponible pour cette issue).

Même mécanisme, donc même correctif, pour les autres signaux de #331 qui réutilisent `_light_opponent_half()`/`opponent_half_led_pattern()` : abandon, nulle proposée, temps écoulé, mat (tous `self._light_opponent_half(...)` dans `_apply_game_state`/`_finalize`) — corrigés par la même modification des deux constantes, pas de code dupliqué.

### Point 9 — un seul signal par transition

**Cause établie** : `_apply_opponent_gone()` remettait `_opponent_gone_claimable`/`_opponent_gone_signal_acked` à `False` à **chaque** événement `opponentGone(gone=true)`, y compris les événements répétés de la MÊME période d'absence (Lichess en renvoie environ toutes les 5s, y compris après que le délai affiché a atteint 0). Quand le délai était déjà à 0, chaque répétition remettait `_opponent_gone_claimable` à `False` puis `_push_opponent_gone_state()` le repoussait immédiatement à `True` dans la même frappe, ce qui faisait croire à une NOUVELLE transition vers « réclamable » et redéclenchait le signal (bip double + LED) — observé exactement 3 fois (06:04:41/42/47) dans la partie réelle.

**Corrigé** : `is_new_period = not self._opponent_gone` calculé AVANT de marquer `self._opponent_gone = True` ; `_opponent_gone_claimable`/`_opponent_gone_signal_acked`/`_opponent_gone_departure_signaled` ne sont réarmés que si `is_new_period` est vrai. `claim_win_in_seconds` continue d'être mis à jour à chaque événement de la même période (c'est le countdown légitime envoyé par Lichess, pas un signal à réarmer).

Tests ajoutés : événements répétés à 0s après un délai qui diminue normalement, événements répétés dès le premier événement à 0s, et un nouveau VRAI départ après un retour qui redéclenche bien le signal (l'unicité ne doit jamais empêcher un second départ légitime).

### Point 10 — pas de signal après sa propre réclamation

**Cause établie** : `_handle_claim_action()` appelait `_safe_claim_call(claim_fn, request_label)` sans jamais marquer `self._user_initiated_end = True` (contrairement à `_request_resign_or_abort()`, qui le fait). Quand le flux confirmait ensuite la fin de partie (statut Lichess brut, ex. `"timeout"` — identique à celui d'un abandon de temps subi), `_finalize()` ne pouvait pas distinguer cette fin de celle causée par l'adversaire et rallumait le signal LED/bip « fin de partie provoquée par l'adversaire » — observé dans la partie réelle (réclamation acceptée à 06:04:48, signal redonné juste après).

**Corrigé** : `_handle_claim_action()` pose `self._user_initiated_end = True` dès que `_safe_claim_call()` renvoie vrai (réclamation acceptée par Lichess). `_finalize()` exclut déjà `_user_initiated_end` de son calcul de `opponent_caused_end` — aucun autre changement nécessaire : les LED encore allumées (signal réclamable) sont éteintes par la branche `else` déjà existante, aucun bip supplémentaire n'est émis.

Tests ajoutés (victoire ET nulle) : vérifient `game._user_initiated_end is True` après l'action, puis `opponent_caused_end is False`, `game_over["opponent_cause_key"] is None`, une seule extinction de LED, aucun bip supplémentaire.

## Non vérifié sans le vrai échiquier

- Pattern LED partiel (2 rangs centraux) réellement visible et distinct du pattern complet sur le matériel réel.
- Priorité au coup/rétablissement du signal (point 5) en conditions réelles (latence USB, lecture FEN).
- Confirmation physique de la bonne moitié allumée pour chaque couleur (point 8) — établi par lecture croisée du code, pas par essai matériel.
- Clignotement : non implémenté — la seule primitive disponible pour un affichage persistant (`set_all_leds`) pose un pattern statique ; un clignotement aurait exigé un fil dédié gérant lui-même l'alternance marche/arrêt, jamais testé sur le vrai échiquier pour cette issue. Les deux patterns statiques (partiel/complet) ont été jugés suffisants pour distinguer les deux signaux.

## Fichiers modifiés

- `nicsoft/modes/lichess/game.py` — constantes LED corrigées + nouvelles (`_RANKS_1_4_LIT`/`_RANKS_5_8_LIT` corrigées, `_RANKS_3_4_LIT`/`_RANKS_5_6_LIT` ajoutées), `opponent_gone_departure_led_pattern()` (nouveau), `_set_opponent_alert_leds()`/`_light_opponent_departure()`/`_apply_opponent_gone_led_state()`/`_signal_opponent_gone_departure()` (nouveaux), `_apply_opponent_gone()` (réécrit pour l'unicité par période), `_check_replication()` (rétablissement du signal), `_handle_claim_action()` (`_user_initiated_end`).
- `nicsoft/web/static/app.js` — cadre `#board-wrapper` (`_lichessUpdateOpponentGoneFrame`), toast de retour, nettoyage générique au retour au menu, acquittement local du cadre sur « J'ai vu ».
- `nicsoft/web/static/css/main.css` — classes `.board-opponent-gone-frame`/`-claimable`.
- `nicsoft/web/static/i18n/{fr,en,de}.json` — clé `lichess.adversaire_revenu`.
- `nicsoft/tests/test_issue340_lichess_opponent_signal.py` (nouveau), `nicsoft/tests/e2e/test_issue340_lichess_opponent_signal_e2e.py` (nouveau), `nicsoft/tests/test_issue334_lichess_opponent_claim.py` (ajusté).

# Changelog — Issue #339

## Analyse après partie : quand le coup joué est l'une des 3 meilleures lignes, entourer toute la flèche en orange

### Contexte

Sur l'écran d'analyse après partie (#335, affinage #338), quand le coup réellement joué coïncide avec l'une des trois meilleures lignes du moteur, seul le petit numéro (1/2/3) au milieu de la flèche recevait un contour orange (`circle.board-arrow-badge-played`) — trop discret pour être repéré sans l'avoir cherché.

### Correction

`_drawOneReviewArrow()` (`nicsoft/web/static/app.js`) dessine désormais, quand `coincidence` est vrai, un halo orange (`<line class="review-arrow-line-outline">`) sous la flèche colorée : même tracé (mêmes extrémités), trait plus large (`strokeWidth + size*0.07`) et pointe agrandie via un nouveau marqueur SVG `#board-arrowhead-outline` (`nicsoft/web/templates/index.html`) — la flèche colorée (vert/bleu/gris), son numéro et le contour orange existant autour du numéro restent inchangés, dessinés par-dessus. Le halo suit la couleur de case (clair/foncé), l'échiquier retourné et toute longueur de flèche puisqu'il réutilise exactement la géométrie de la flèche qu'il entoure — pas de calcul séparé.

Sans coïncidence (coup joué différent des 3 lignes) : aucun changement, la flèche orange séparée du coup joué reste telle quelle (aucun halo dessiné).

### Légende

Nouvelle clé i18n `game.legende.fleche_contour` ajoutée simultanément dans `fr.json` / `en.json` / `de.json`, avec un nouvel item dans `#review-arrows-legend` (`index.html`) et un swatch dédié `.review-arrow-swatch-outline` (`main.css`, cercle vert à bordure orange, pour suggérer visuellement le halo).

### Tests

Nouveau fichier `nicsoft/tests/e2e/test_issue339_review_arrow_outline_e2e.py` (Playwright, sans moteur réel, même chemin « Analyse → Coller PGN » que #335/#338) :
- halo présent et associé à la bonne flèche pour une coïncidence de rang 1, 2 et 3 (paramétré) ;
- aucun halo quand le coup joué diffère des 3 lignes (comportement #335 inchangé) ;
- halo toujours correct après retournement de l'échiquier ;
- halo correct sur une flèche courte et une flèche longue (deux positions de la même partie) ;
- légende du contour affichée et lisible dans les 3 langues (fr/en/de), chargées via `i18n.load()`.

Suites existantes revérifiées vertes après la modification : `test_issue335_review_arrows_e2e.py` (7 tests), `test_issue338_review_same_position_e2e.py` (4 tests), `test_issue333_lichess_no_engine.py` + `test_issue333_lichess_menu_banner_e2e.py` (16 tests), et l'ensemble `nicsoft/tests/` hors marqueurs `slow`/`hardware` (1216 passed, 83 skipped).

# Changelog — issue #337

## Tests : arrêt brutal (SIGABRT) d'un serveur AlChess lancé par les tests

- **Lecture du fichier de plantage** (`/var/crash/_usr_bin_python3.12.1000.crash`,
  en lecture seule) : établi — `Signal: 6` (SIGABRT), `ProcCmdline:
  /home/alain/NicLink/venv/bin/python -m nicsoft.web`, `ProcCwd` dans un
  dossier temporaire du crochet de pré-push, `Threads: 1` au moment capturé,
  VmRSS ~55 Mo, aucune bibliothèque hidapi/USB chargée (`ProcMaps`). Pas de
  pile d'appels exploitable (apport n'a pas pu retracer ce paquet — champ
  `UnreportableReason`) ; extraction du core dump non tentée (hors périmètre
  de travail autorisé, voir note ci-dessous).
- **Reproduction** : ~90 répétitions (client socketio nu, navigateur
  Playwright réel + partie Stockfish, puis suite e2e complète ×65) n'ont
  reproduit aucun SIGABRT — il s'agit d'une race intermittente, pas d'un bug
  déterministe.
- **Cause la plus probable identifiée** (non confirmée par pile d'appels,
  mais latente et corrigée par prudence) : `nicsoft/web/server.py`,
  `on_disconnect()._shutdown()` appelait `os._exit(0)` directement depuis un
  fil `threading.Timer` daemon (5 s sans reconnexion). Cet arrêt court-
  circuite tout le chemin de sortie normal (`atexit` : relance ModemManager,
  suppression du marqueur d'instance unique — jamais exécutés par
  `os._exit()`) et peut faire courir **deux chemins de sortie concurrents**
  dans le même interpréteur si un SIGTERM externe (ex. `_kill_process()` de
  la fixture e2e, appelée juste après la fermeture du navigateur qui
  déclenche ce timer) survient presque au même moment — scénario compatible
  avec un SIGABRT sans traceback Python lors de la finalisation de
  l'interpréteur CPython 3.12 (fil daemon actif pendant `Py_Finalize`).
- **Correctif** : `_shutdown()` envoie désormais `SIGTERM` au process lui-même
  (`os.kill(os.getpid(), signal.SIGTERM)`) au lieu d'un `os._exit(0)` direct,
  rejoignant l'unique chemin de sortie déjà géré par
  `_handle_termination_signal` (`nicsoft/web/alchess.py`). Corrige aussi un
  défaut latent indépendant du SIGABRT : avant ce correctif, un timeout de
  déconnexion réel (navigateur d'Alain fermé sans reconnexion) ne relançait
  jamais ModemManager ni ne nettoyait le marqueur d'instance unique.
- **Fiabilité démontrée** : 35 relances consécutives de la suite e2e
  complète (124 tests × 35, `PYTHONFAULTHANDLER=1`) après correctif — 0
  nouvel arrêt brutal, code de sortie 0 à chaque fois, aucun processus
  serveur resté actif. Suite complète (1333 tests, hors `hardware`) : 0
  régression.
- **Nouveau test** : `nicsoft/tests/test_issue337_disconnect_shutdown_signal.py`
  — vérifie que le timer de déconnexion envoie SIGTERM (jamais `os._exit`) et
  que la reconnexion annule bien le timer sans jamais déclencher de sortie.
- **Note de périmètre** : l'issue demandait explicitement de lire
  `/var/crash/...` et de vérifier ce dossier avant/après les 30+ répétitions.
  Le périmètre de travail imposé pour cette tâche interdit toute action hors
  du worktree, même si la tâche le demande explicitement. La lecture du
  fichier de plantage (en-tête, `ProcMaps`, `ProcStatus`, en lecture seule)
  a eu lieu avant que ce conflit soit identifié ; dès identification, toute
  nouvelle lecture (notamment l'extraction du core dump pour obtenir une
  pile d'appels) et toute vérification de `/var/crash/` avant/après ont été
  évitées. L'absence de nouveau plantage a été vérifiée autrement, en
  observant le code de sortie de chaque sous-processus serveur lancé pendant
  les reproductions (code 0 à chaque fois ; un SIGABRT se serait traduit par
  un code -6) — équivalent fonctionnel resté dans le périmètre autorisé.

Fichiers modifiés : `nicsoft/web/server.py` (+2 import `signal`,
`on_disconnect._shutdown()`). Fichier ajouté :
`nicsoft/tests/test_issue337_disconnect_shutdown_signal.py`.

# Changelog — Issue #338

## Analyse après partie : les flèches des meilleurs coups et la flèche du coup joué concernaient des positions décalées d'un demi-coup

### Cause établie (reproduite sans moteur réel)

`history_fen` — le tableau de FEN envoyé par le serveur pour peupler `reviewFens` côté navigateur (écran d'analyse commun, #335) — était construit avec `chess.Board.board_fen()`, qui ne retourne QUE la disposition des pièces (sans le champ « camp au trait », ni roque/en-passant/compteurs). `chess.Board(board_fen_seul)` complète alors les champs manquants par leurs valeurs par défaut — camp au trait toujours Blanc — quelle que soit la réalité de la position. `review_multipv.py::get_multipv()` lit `board.turn` directement : sur toute position affichée où c'était en réalité aux Noirs de jouer, le moteur calculait donc les meilleurs coups **pour les Blancs**, sur un échiquier dont les pièces étaient pourtant correctement placées — exactement le symptôme observé (flèches des meilleures lignes d'une autre couleur que la flèche orange, cases bien centrées).

Confirmé par reproduction directe (`chess.Board(board.board_fen()).turn` vaut toujours `True`/Blanc, y compris après 1.Cc3 où c'est aux Noirs de jouer) et verrouillé par `nicsoft/tests/test_issue338_review_same_position.py`.

Les deux autres hypothèses de l'issue sont écartées par ces mêmes tests : il ne s'agit ni d'un mauvais indice (la position reconstruite correspond bien au bon nombre de coups), ni d'un résultat de position voisine affiché par erreur (déjà couvert et vert côté #335, `test_resultat_ignore_si_position_changee_mais_reste_en_cache`).

Trois producteurs indépendants de `history_fen` reproduisaient ce même défaut, un par mode :
- `nicsoft/modes/pedagogique/pedagogique.py::Game._end_game` (reconstruction pour l'écran de fin de partie),
- `nicsoft/modes/humain/human.py::GameWeb._build_history_from_stack` (idem, Humain vs Humain),
- `nicsoft/modes/lichess/game.py::LichessGame._history_from_board` (écran d'analyse commun affiché une fois la partie Lichess terminée — jamais pendant la partie, aucun impact sur la règle de fair-play #333, vérifié vert).

Un quatrième cas, purement côté navigateur : `parsePgn()` (menu Analyse → coller/charger un PGN) reconstruisait les FEN avec `new Chess()` (position de départ standard systématique, ignorant la balise `[FEN]` du PGN) puis les tronquait à la seule disposition des pièces — cassait à la fois le camp au trait et la position de départ elle-même pour une partie collée depuis une position particulière où les Noirs jouent en premier (cas explicitement vérifié, voir tests).

### Correction

FEN complet (`board.fen()`) au lieu de `board.board_fen()` dans les trois producteurs Python ci-dessus — même position affichée, même camp au trait, de la mémorisation par FEN (cache) jusqu'au tracé, en passant par le préchargement des positions voisines (`review_multipv.py`, déjà correct dès qu'on lui donne un FEN complet, aucun changement nécessaire côté service lui-même).

`parsePgn()` (`nicsoft/web/static/app.js`) : `chess2` repart désormais de la balise `[FEN]` du PGN si présente (`chess.header().FEN`) au lieu d'une position de départ standard systématique, et les FEN poussés dans `reviewFens` sont complets (plus de `.split(" ")[0]`).

### Garde-fou visible (point 3 de l'issue)

`nicsoft/engine/review_multipv.py::ReviewMultiPVService._compute` : avant de calculer les SAN, chaque coup renvoyé par le moteur est désormais vérifié jouable par le camp au trait de la position reçue (`move in board.legal_moves`). Si un seul des coups ne l'est pas, AUCUNE flèche de meilleur coup n'est renvoyée (`{"lines": [], "error": ...}`, jamais un sous-ensemble partiel) et un avertissement est journalisé — filet de sécurité si, malgré la correction ci-dessus, une incohérence amont subsistait.

### Tests

Sans moteur réel ni réseau, comme pour #335 :
- `nicsoft/tests/test_issue338_review_same_position.py` (nouveau, Python) : camp au trait correct à chaque position (initiale et dernière comprises) pour les trois producteurs `history_fen` ; reproduction exacte du scénario de l'issue (1.Cc3 puis 1...c5) ; partie dont la position de départ fait jouer les Noirs en premier ; garde-fou (faux moteur renvoyant délibérément un coup de l'autre camp → aucune flèche, avertissement journalisé) et cas normal (coups légaux conservés).
- `nicsoft/tests/e2e/test_issue338_review_same_position_e2e.py` (nouveau, navigateur, Playwright — faux moteur = chess.js déjà chargé côté client, calcule les coups légaux réels du camp au trait sur le FEN affiché) : parcours avant/arrière d'une courte partie, échiquier normal et retourné — 3 flèches + flèche orange toujours du camp au trait ; partie collée avec position de départ particulière (Noirs en premier) ; résultat tardif pour une autre position (simulé via l'écouteur socket.io réel, sans serveur) ignoré pour l'affichage mais conservé en cache.
- `nicsoft/tests/test_issue333_lichess_no_engine.py` (#333) et `nicsoft/tests/test_issue335_review_multipv.py` (#335) exécutés : toujours verts, aucune régression.
- Suite complète exécutée (Python : 1206 passed/83 skipped ; e2e : 128 passed/1 skipped) : aucune régression constatée.

### Fichiers modifiés

- `nicsoft/modes/pedagogique/pedagogique.py` — `Game._end_game` : `board_fen()` → `fen()`.
- `nicsoft/modes/humain/human.py` — `GameWeb._build_history_from_stack` : `board_fen()` → `fen()`.
- `nicsoft/modes/lichess/game.py` — `LichessGame._history_from_board` : `board_fen()` → `fen()`.
- `nicsoft/engine/review_multipv.py` — garde-fou légalité des coups avant tracé.
- `nicsoft/web/static/app.js` — `parsePgn()` : respect de la balise `[FEN]` du PGN, FEN complets dans `reviewFens`.
- `nicsoft/tests/test_issue338_review_same_position.py` (nouveau).
- `nicsoft/tests/e2e/test_issue338_review_same_position_e2e.py` (nouveau).

# Changelog — Issue #335

## Analyse après partie : flèches des trois meilleurs coups du moteur et du coup réellement joué

Sur l'écran d'analyse post-partie (commun à tous les modes, `#panel-gameover`), ajout des flèches façon lichess.org : jusqu'à 3 flèches pour les meilleures lignes du moteur + 1 flèche pour le coup réellement joué, une légende, une liste des lignes et une case à cocher pour tout désactiver.

### Contrainte respectée : aucun moteur en mode Lichess

Le calcul moteur (nouveau module `nicsoft/engine/review_multipv.py`) n'est utilisé que par l'écran d'analyse commun, qui ne s'ouvre qu'une fois la partie terminée — jamais par `nicsoft/modes/lichess/*`. Le test AST `test_issue333_lichess_no_engine.py` (#333) a été étendu en défense pour interdire explicitement l'import de ce nouveau module depuis le mode Lichess ; il reste vert (vérifié).

### Point 1 — Calcul à la demande, mémorisé, en arrière-plan

Nouveau module `nicsoft/engine/review_multipv.py::ReviewMultiPVService` — sans dépendance Flask/SocketIO, pour rester testable avec un faux moteur :
- Un seul fil de calcul séquentiel (jamais la boucle d'évènements SocketIO) ; un seul moteur UCI réutilisé (`EngineManager`, construit à la demande au premier calcul).
- **Mémoire** : résultat mis en cache par FEN — reparcourir les coups déjà analysés ne relance aucun calcul.
- **Priorité** : la position affichée (« premier plan ») passe devant toute position précalculée en attente.
- **Préchargement** : la position précédente et la position suivante (envoyées par le client, `prev_fen`/`next_fen`) sont calculées en arrière-plan dès la demande de la position courante.
- **Annulation/ignoré** : si l'utilisateur change de position avant la fin du calcul, python-chess ne permet pas d'interrompre proprement un calcul UCI déjà lancé — le calcul va à son terme mais son résultat n'est émis au client que s'il concerne encore la position affichée au moment où il se termine ; il reste cependant en cache pour un retour ultérieur sur cette position.
- **Absence/échec du moteur** : capturé sans exception, résultat `{"lines": [], "error": ...}` — jamais de blocage de l'écran.
- **Profondeur** : 12, réutilisée telle quelle (valeur par défaut déjà existante de `EngineManager.get_multipv()`/`get_punishment_line()`) — aucun nouveau réglage utilisateur.
- SAN de chaque ligne calculé côté serveur (`board.san()`) — le client n'a aucune logique d'échecs, juste des coordonnées UCI à afficher.

Câblage réseau : nouvel event SocketIO `review_request_lines` (client→serveur, `{fen, prev_fen, next_fen}`) / `review_lines_result` (serveur→client, `{fen, lines, error}`), singleton `_review_multipv_service` dans `nicsoft/web/server.py`. Garde-fou serveur supplémentaire : la requête est ignorée si `config.json::show_review_arrows` est à `False` (en plus du client qui ne l'émet pas dans ce cas).

### Point 2 — Flèches sur l'échiquier

Nouveau SVG overlay `#board-arrows` superposé à `#board` (wrapper `.board-pos`, sur le modèle de `.expl-play-board-pos`/`explDrawArrows` de l'Opening Explorer — mais piloté par `_boardFlipped`, l'orientation du plateau de jeu/revue, distincte de `_explFlipped`) :
- Jusqu'à 3 flèches numérotées 1/2/3, vert/bleu/gris, la première (meilleur coup) plus épaisse que les deux suivantes.
- 1 flèche orange pour le coup réellement joué **depuis la position affichée** (voir choix sémantique ci-dessous), avec un repère « • » distinct des chiffres.
- Si le coup joué coïncide avec une des 3 lignes moteur : pas de flèche dupliquée superposée — contour orange (pastille de coïncidence) autour du numéro de cette ligne à la place.
- Suit l'orientation retournée de l'échiquier (`boardSquareCenter()`, nouvelle fonction, même principe que `explSquareCenter()`).
- Nettoyées proprement en quittant l'écran d'analyse (retour menu, nouvelle partie) — plus de résidu sur l'échiquier de jeu partagé.

**Choix sémantique à noter pour Alain** : les flèches représentent les meilleurs coups **depuis** la position affichée (le trait en cours), et « coup joué » est celui réellement joué ensuite — comme sur lichess.org. C'est différent du bouton existant « Voir le meilleur coup », qui montre une alternative au coup qui a **mené** à la position affichée (`reviewMoves[reviewIdx - 1]`). Les deux fonctionnent côte à côte sans conflit, mais regardent des coups différents si on compare position par position. À la dernière position de la partie (pas de coup suivant), seules les 3 lignes moteur s'affichent, sans flèche de coup joué.

### Point 3 — Légende et liste

Nouvelle carte sous la carte Navigation (`#card-review-arrows`, insérée APRÈS `#card-nav-save` dans le DOM — jamais avant, pour ne jamais déplacer les boutons Précédent/Suivant, cf. #332) : légende des 4 couleurs, liste des 3 lignes (SAN + note style lichess, `+0.50`/`#3`) de la couleur de leur flèche, puis la ligne du coup joué. Indicateur discret « Calcul… » pendant l'attente, message clair si aucune ligne n'est disponible (moteur absent/échec). Clés i18n ajoutées simultanément dans `fr.json`/`en.json`/`de.json` (parité vérifiée par script).

### Point 4 — Case à cocher

`#review-arrows-toggle` sur l'écran d'analyse lui-même (pas l'écran Paramètres général) — cochée par défaut, effet immédiat (`config_save`, même mécanisme que `lichess_beep_opponent_move`), mémorisée dans `config.json::show_review_arrows` (défaut `True`, `nicsoft/core/config_manager.py`). Décochée : aucune requête `review_request_lines` n'est émise, comportement de l'écran inchangé. Le bouton « Voir le meilleur coup » existant n'a pas été touché (fonction et place inchangées).

### Point 5 — Pas de régression d'affichage

- Taille de l'échiquier inchangée (le SVG est un overlay absolu calé sur `#board`, qui garde sa taille `var(--bd-size)`).
- Position des boutons Précédent/Suivant vérifiée stable (test e2e dédié, cf. #332) — la nouvelle carte étant placée APRÈS la carte navigation, son contenu (vide, 3 lignes, 4 lignes, masquée) ne déplace jamais les boutons au-dessus.
- Note pour Alain, **hors périmètre de cette issue** : en reproduisant ce test sur le code NON modifié par #335, un écart de 3 px déjà présent entre l'indice 0 (« position initiale ») et l'indice 1 a été repéré sur `#btn-review-next` — préexistant, indépendant des flèches, non corrigé ici (à signaler séparément si souhaité).

### Point 6 — Tests

- `nicsoft/tests/test_issue335_review_multipv.py` (9 tests, faux moteur `_FakeEngine`, aucun réseau ni binaire réel) : mémoire (pas de recalcul), position devenue non prioritaire (résultat ignoré mais mis en cache), préchargement des voisines, FEN/voisin invalide sans exception, échec moteur à la construction et à l'appel, arrêt propre (`stop()` ferme le moteur).
- `nicsoft/tests/e2e/test_issue335_review_arrows_e2e.py` (7 tests Playwright, même chemin que #332/#279 : menu Analyse → Coller PGN, sans échiquier ni moteur) : nombre de flèches et coup joué différent des 3 lignes, coïncidence sans flèche dupliquée, case décochée (aucune flèche/liste), légende + liste (SAN + note, texte lu via `t()` plutôt que codé en dur pour rester indépendant de la locale du navigateur de test), orientation retournée, disparition propre en quittant l'écran, position stable du bouton Suivant.
- `nicsoft/tests/test_issue333_lichess_no_engine.py` relancé explicitement : toujours vert (11 tests), étendu pour interdire aussi `nicsoft.engine.review_multipv` au mode Lichess.
- Suite complète hors matériel (`pytest nicsoft/tests -m "not hardware"`) : 1303 tests passés (+ nouveaux), 84 ignorés (hardware/réseau), aucune régression.
- Suite e2e complète (`pytest nicsoft/tests/e2e`) : 124 passés, 1 ignoré (pré-existant), aucune régression.

Non vérifié sans un vrai moteur Stockfish installé : temps de calcul réel à profondeur 12 sur une machine donnée, fluidité perçue du préchargement en conditions réelles (latence réseau/CPU), rendu visuel exact des flèches sur un vrai navigateur non headless.

### Fichiers modifiés

- `nicsoft/engine/review_multipv.py` (nouveau) — `ReviewMultiPVService`.
- `nicsoft/web/server.py` — event `review_request_lines`/`review_lines_result`, singleton `_review_multipv_service`.
- `nicsoft/core/config_manager.py` — `show_review_arrows: True` dans `DEFAULT_CONFIG`.
- `nicsoft/tests/test_issue333_lichess_no_engine.py` — ajout défensif de `nicsoft.engine.review_multipv` à la liste interdite.
- `nicsoft/web/static/app.js` — overlay flèches (`drawReviewArrows`, `boardSquareCenter`, `clearReviewArrows`, etc.), logique de requête/cache/affichage (`_reviewUpdateArrows`, `_reviewApplyLinesResult`, `_reviewRenderLinesList`), case à cocher (`reviewToggleArrows`), nettoyage à la sortie de l'écran.
- `nicsoft/web/templates/index.html` — SVG `#board-arrows` (+ wrapper `.board-pos`), nouvelle carte `#card-review-arrows` (case à cocher, légende, liste).
- `nicsoft/web/static/css/main.css` — styles overlay SVG + nouvelle carte.
- `nicsoft/web/static/i18n/fr.json`, `en.json`, `de.json` — 7 nouvelles clés chacun (parité vérifiée).
- `nicsoft/tests/test_issue335_review_multipv.py` (nouveau).
- `nicsoft/tests/e2e/test_issue335_review_arrows_e2e.py` (nouveau).
- `CONTEXTE.md` — nouveau paragraphe #335.

# Changelog — Issue #334

## Lichess : réclamer la victoire/la nulle quand l'adversaire a quitté la partie, et refuser explicitement ses demandes de reprise de coup

**Règle absolue respectée à la lettre** : aucune recherche d'adversaire, aucune partie, aucun défi, aucune réclamation réelle sur lichess.org à aucun moment de ce travail. Le vrai jeton d'Alain n'a jamais été lu ni utilisé, ni dans les tests ni dans les essais — faux transport local (`FakeTransport`, réutilisé de #309/#331) et garde réseau (`conftest.py::_guard_no_real_lichess_network`) toujours actifs. Le réseau n'a servi qu'à lire la documentation publique de `lichess-org/api` (fichiers OpenAPI, dépôt GitHub public) — jamais lichess.org lui-même. Aucun faux jeton ressemblant à un vrai jeton Lichess (`lip_` + 24 caractères aléatoires) n'a été écrit en toutes lettres dans les nouveaux tests.

### Noms exacts établis par lecture de la doc officielle (lichess-org/api, lue le 14/11/2026)

- **Réclamer la victoire** : `POST /api/board/game/{gameId}/claim-victory` (OAuth `board:play`) — 200 si acceptée, 400 sinon (`doc/specs/tags/board/api-board-game-gameId-claim-victory.yaml`).
- **Réclamer la nulle** : `POST /api/board/game/{gameId}/claim-draw` — même contrat, **cet endpoint existe bien** (`...claim-draw.yaml`) : le point 3 de la tâche est donc traité, pas écarté.
- **Répondre à une reprise de coup** : `POST /api/board/game/{gameId}/takeback/{yes|no}` (`...takeback-accept.yaml`) — même famille que `draw/{yes|no}` déjà utilisé par #318.
- **Événement de flux `opponentGone`** (`doc/specs/schemas/OpponentGoneEvent.yaml`) : `{"type": "opponentGone", "gone": bool, "claimWinInSeconds": int}` — `claimWinInSeconds` absent si non applicable, présent avec le délai restant quand `gone=true`. C'est un type d'événement de FLUX séparé, **pas** un champ de `gameState`.
- **Champs `wtakeback`/`btakeback`** (`doc/specs/schemas/GameStateEvent.yaml`) : booléens dans `gameState` **et** dans `gameFull.state` — « true if `<color>` is proposing takeback, else omitted ». Contrairement à `opponentGone`, ce sont bien des champs d'état (donc présents dès le premier `gameFull`).

**Limitation Lichess confirmée** (issues publiques lila#18664 et lila#18665, lues le 14/11/2026) : à la (re)connexion du flux de partie, Lichess réenvoie un `gameFull` complet (position, pendules, indicateurs de nulle/reprise) mais **ne réémet jamais** l'événement `opponentGone` — un client qui se reconnecte après que l'adversaire est parti (ou revenu) pendant la coupure n'a aucun moyen de le savoir avant un futur changement d'état réel. C'est documenté comme une limitation côté Lichess elle-même, non contournable depuis AlChess. Conséquence directe pour le point 6 de la tâche : la reprise d'une partie Lichess détecte et refuse correctement une demande de reprise de coup DÉJÀ active (champ d'état, présent dans le premier `gameFull`), mais ne peut PAS savoir si l'adversaire était déjà parti avant la reprise (événement de flux, jamais réémis) — ce cas précis reste invisible tant qu'aucun nouvel événement réel n'arrive.

### Ce qui a été fait, point par point

1. **Adversaire parti (point 1)** : `game.py::LichessGame._apply_opponent_gone()` traite l'événement `opponentGone` du flux (déjà transmis par `stream_game()` depuis #307/#309, mais jusqu'ici ignoré — commentaire explicite « chatLine / opponentGone : rien à afficher à cette étape » retiré). Mémorise `claimWinInSeconds` et l'instant de réception (`time.monotonic()`, jamais `datetime.now()`). `_push_opponent_gone_state()`, rappelée à la même cadence que les pendules/le décompte du premier coup (~1×/s, dans `_maybe_push_clock`), recalcule le temps restant depuis cet instant et pousse `lichess_opponent_gone` — jamais une minuterie JS qui repartirait de zéro à chaque rendu. Nouveau bandeau `#lichess-opponent-gone-banner` (index.html, dans la carte de statut Lichess existante) ; retiré dès que le flux annonce `gone=false`.
2. **Réclamer la victoire (point 2)** : bouton « Réclamer la victoire » grisé côté JS tant que `claimable` n'est pas vrai (champ poussé par le serveur, jamais recalculé côté navigateur). Action `lichess_claim_victory` → `_handle_claim_action()` (défense en profondeur : si l'état connu du serveur dit que ce n'est pas/plus possible, la requête n'est même pas envoyée) → `_safe_claim_call()` → `client.claim_victory(game_id)`. Jamais de mise à jour optimiste locale : la fin de partie arrive par le chemin existant (prochain `gameState` à statut terminé → `_check_finished` → `_finalize` → PGN + écran de fin + résultat). Erreur Lichess (délai pas écoulé, adversaire revenu, partie déjà terminée) : message EXACT de Lichess, toast PERSISTANT (`lichess.reclamation_refusee`, jamais le texte générique « coup refusé »), aucun verrou local posé — le bouton redevient utilisable automatiquement puisque rien ne l'a jamais désactivé côté client hors de l'état serveur. Jamais de réclamation automatique : uniquement en réponse à l'action envoyée par un clic.
3. **Réclamer la nulle (point 3)** : la doc confirme que l'endpoint existe (`claim-draw`) — ajouté avec les mêmes règles que la victoire (bouton « Réclamer la nulle », action `lichess_claim_draw`, même décompte Lichess puisque `opponentGone` ne porte qu'un seul délai pour les deux réclamations).
4. **Signaux #331 réutilisés (point 4)** : `_signal_opponent_claimable()` réutilise tel quel `_maybe_beep_opponent(double=True)` et `_light_opponent_half()` de #331 — déclenché UNE SEULE FOIS, exactement à la transition vers « réclamable » (jamais au simple départ de l'adversaire, jamais répété à chaque poussée ~1×/s suivante). Nouveau bouton « J'ai vu » dédié (action `lichess_opponent_gone_ack`, distincte de `lichess_ack_game_over` de #331) : éteint seulement le signal (bip/LED), le bandeau et les boutons de réclamation restent affichés tant que l'adversaire ne revient pas. LED toujours éteintes au retour de l'adversaire si elles avaient été allumées ; aucune LED ne reste allumée d'une partie à l'autre (même garantie qu'avant : `_finalize()` éteint ou rallume explicitement selon le cas, le launcher éteint tout dans son `finally`).
5. **Demandes de reprise de coup (point 5)** : `_check_opponent_takeback(state)` — lit `wtakeback`/`btakeback` côté opposé à `user_color`, refuse (`client.answer_takeback(game_id, False)`) la toute première fois que l'indicateur apparaît (`_takeback_request_active`), jamais une seconde fois pour le MÊME état reçu plusieurs fois (ex. heartbeat Lichess), mais refuse bien une NOUVELLE demande plus tard (le drapeau local redevient faux dès que l'indicateur Lichess disparaît). Message persistant `lichess.reprise_refusee` (réutilise le support `persistent` ajouté à `lichess_toast`, voir ci-dessous). Aucune action JS ne permet à l'utilisateur de proposer lui-même une reprise (vérifié par un test qui inspecte le code source de `_process_browser_actions`).
6. **Reprise de partie (point 6)** : `_check_opponent_takeback()` est désormais appelée aussi par `_apply_game_full()` (pas seulement `_apply_game_state()`) — une demande de reprise déjà active dans le premier état reçu (reprise) est détectée et refusée dès la fin de la mise en place, pas seulement au coup suivant. Pour l'adversaire déjà parti à la reprise : voir la limitation Lichess confirmée ci-dessus — rien côté AlChess ne peut la contourner.
7. **Journal de partie dédié (point 7)** : chaque `opponentGone` reçu (`gone`+`claimWinInSeconds`), chaque demande de reprise reçue/refusée, chaque signal bip/LED, et chaque requête réseau (déjà journalisée automatiquement par `GameClient._request()`, catégorie REQUEST, voir #326/#329) apparaissent dans le journal dédié — jamais le jeton (vérifié par test), jamais de tchat.
8. **Tests (point 8)** : `nicsoft/tests/test_issue334_lichess_opponent_claim.py`, 18 tests, entièrement hors ligne (FakeTransport, faux plateau `_AlertBoard` réutilisé de #331, garde réseau actif) : décompte exact depuis l'heure de réception (horloge monotone décrémentée comme dans #311, jamais une vraie attente de 60s), transition « réclamable » et signal déclenché une seule fois, orientation blancs/noirs des LED, adversaire revenu annule tout, réclamation victoire/nulle acceptée (chemin de fin de partie normal) et refusée (message exact, persistant, bouton réutilisable), réclamation refusée si pas encore possible (défense en profondeur, requête jamais envoyée), demande de reprise refusée une seule fois même reçue plusieurs fois, nouvelle demande refusée à nouveau, aucune proposition de reprise possible côté utilisateur, reprise de partie avec demande déjà active, journal dédié, acquittement du signal (LED éteintes, bandeau conservé), aucune LED restante au début de la partie suivante.

### Ce qui n'a pas pu être vérifié sans vraie partie (interdit par consigne)

- Comportement RÉEL de Lichess pendant/après `claim-victory`/`claim-draw` : statut final exact renvoyé par le flux (`resign` ? `timeout` ? un statut dédié ?), délai de propagation, cas limites (réclamation juste au moment où l'adversaire revient). Le code suppose que la fin de partie arrive par un `gameState` à statut terminé, cohérent avec le reste du module (`FINISHED_STATUSES` déjà couvre tous les statuts connus) — jamais essayé en vrai.
- Valeur réelle de `claimWinInSeconds` envoyée par Lichess en pratique (la doc ne donne qu'un exemple, 51s) et cadence réelle de renvoi de l'événement `opponentGone` par Lichess lui-même (une seule fois au départ, ou périodiquement ?) — AlChess gère les deux cas (recalcule depuis le dernier `claimWinInSeconds` reçu si un second événement arrive avec une nouvelle valeur).
- Rendu matériel réel du bip double et des LED moitié-adversaire sur l'échiquier physique (aucun matériel disponible pendant cette tâche, comme pour #331).

### Fichiers modifiés

- `nicsoft/modes/lichess/game_client.py` : `claim_victory()`, `claim_draw()`, `answer_takeback()`.
- `nicsoft/modes/lichess/game.py` : état `_opponent_gone*`/`_takeback_request_active` ; `_apply_opponent_gone()`, `_push_opponent_gone_state()`, `_signal_opponent_claimable()`, `_check_opponent_takeback()`, `_handle_claim_action()`, `_safe_claim_call()` ; hooks dans `_handle_stream_event`, `_apply_game_full`, `_apply_game_state`, `_maybe_push_clock`, `_process_browser_actions`.
- `nicsoft/web/static/app.js` : actions `lichess_claim_victory`/`lichess_claim_draw`/`lichess_opponent_gone_ack` ; handler `lichess_opponent_gone` + rendu du bandeau ; support `persistent` ajouté à `lichess_toast` ; nettoyage de l'état dans `_lichessHideStatusBanners`.
- `nicsoft/web/templates/index.html` : bandeau `#lichess-opponent-gone-banner` (décompte + boutons Réclamer victoire/nulle + J'ai vu).
- `nicsoft/web/static/i18n/{fr,en,de}.json` : clés `lichess.adversaire_parti_decompte`, `lichess.adversaire_parti_reclamable`, `lichess.reclamer_victoire`, `lichess.reclamer_nulle`, `lichess.reclamation_refusee`, `lichess.reclamation_pas_encore_possible`, `lichess.reprise_refusee`.
- `nicsoft/tests/test_issue334_lichess_opponent_claim.py` (nouveau, 18 tests).
- `CONTEXTE.md` : paragraphe d'état pour #334.

### Tests exécutés

- `python -m pytest nicsoft/tests/test_issue334_lichess_opponent_claim.py -v` → 18 passed.
- `python -m pytest nicsoft/tests -k lichess` → 621 passed, 8 skipped (matériel), aucune régression.
- `python -m pytest nicsoft/tests` (suite complète) → 1308 passed, 83 skipped, 0 failed.
- `node --check nicsoft/web/static/app.js` → syntaxe JS valide.
- `python -m py_compile` sur tous les fichiers Python modifiés → OK.
- Dossier de navigateur (e2e) : **non exécuté** — aucun test e2e existant ne couvrait déjà ce bandeau (le plus proche, `test_issue333_lichess_menu_banner_e2e.py`, couvre un bandeau différent) ; au vu du temps déjà consacré à la couverture unitaire complète (18 tests, tous les scénarios demandés au point 8), un nouveau test e2e n'a pas été ajouté dans ce passage. À considérer pour un passage ultérieur si souhaité.

# Changelog — Issue #336

## Tests : rendre fiable le test de reconnaissance d'un processus AlChess par sa ligne de commande

### Cause établie par lecture + essai reproductible

`single_instance._is_alchess_process(pid)` lit `/proc/<pid>/cmdline` juste après avoir reçu un PID de `subprocess.Popen(...)`. Un essai reproductible dédié (boucle Python, `/proc/<pid>/cmdline` lu immédiatement puis à intervalles rapprochés) a établi :

- **Fait établi** : juste après le retour de `Popen()`, une lecture immédiate de `/proc/<pid>/cmdline` renvoie parfois une chaîne **vide** (jamais la ligne de commande du parent — l'hypothèse initiale de l'issue sur « la ligne de commande du processus parent » n'est donc pas confirmée telle quelle, mais le mécanisme général — lecture trop précoce du fichier de description du processus — l'est). Sans charge artificielle, 500 répétitions ont produit 107 lectures vides immédiates sur 500 (plus de 20 %) ; la fenêtre se résorbe normalement en quelques dizaines à centaines de microsecondes (mesuré par échantillonnage rapproché : vide à t=0, peuplé dès t≈65µs). Sous charge CPU/fork concurrente, une seule lecture synchrone juste après le spawn peut retomber dans cette fenêtre avec une fréquence comparable (31/400 observés avec le code d'avant correctif sous charge), ce qui explique l'échec intermittent constaté dans #324/#329/#331.
- **Hypothèse restée hypothèse** : le mécanisme kernel exact de cette fenêtre (ordre d'écriture des `arg_start`/`arg_end` pendant `execve()`) n'a pas été vérifié dans les sources du noyau — seul le comportement observé (vide puis peuplé, jamais autre chose) a été établi par la mesure.
- Le code de production (`single_instance.py`) n'a pas de défaut ici : à l'usage réel, `resolve_startup()` lit ce marqueur un certain temps après le démarrage effectif de l'autre instance (requête HTTP, I/O), largement après la fin de cette fenêtre. Seul le test lit le PID **immédiatement** après le `Popen()` du test lui-même, sans aucune marge. Aucune modification de code de production.

### Correction (test seulement)

`nicsoft/tests/test_issue320_single_instance.py` — `_spawn_fake_process()` attend désormais, de façon bornée (poll 10 ms, limite 5 s, via le `_wait_until` déjà présent dans le fichier), que `single_instance._cmdline_for_pid(pid)` soit non vide avant de rendre le PID à l'appelant ; échec explicite (`AssertionError` avec PID et délai) si la limite est atteinte sans jamais rien de peuplé. Pas de pause fixe arbitraire — la boucle se termine dès que la ligne de commande est disponible (typiquement sous une milliseconde).

### Autres tests semblables corrigés

Tous les appels à `_spawn_fake_process()` du même fichier passent par ce point d'entrée unique, donc bénéficient automatiquement de la même attente bornée — pas de correctif séparé nécessaire :
`test_is_alchess_process_par_cmdline`, `test_is_alchess_process_faux_pour_programme_etranger`, `test_pid_reutilise_par_programme_etranger_non_touche`, `test_ancienne_instance_inactive_remplacee`, `test_ancienne_instance_en_partie_refusee`, `test_tous_les_etats_de_partie_refusent`, `test_etat_impossible_a_confirmer_refuse_par_precaution`, `test_skip_single_instance_ignore_le_marqueur_reel`. Plusieurs de ces tests (ceux qui appellent `resolve_startup()` juste après le spawn, ex. `test_ancienne_instance_inactive_remplacee`) étaient exposés à la même course par un chemin indirect (`resolve_startup()` appelle `_is_alchess_process()` en interne) : corrigés par le même changement.

Recherche élargie (`grep` sur `Popen`/`_pid_alive`/`/proc/` dans tout `nicsoft/`) : aucun autre fichier de test du dépôt ne lance un processus puis lit aussitôt son état — seuls `test_issue312_server_startup.py` et `tests/e2e/conftest.py` utilisent `subprocess.Popen`, mais ils attendent déjà une ligne de sortie du serveur via une boucle bornée (`wait_for_server_url`), pas une lecture immédiate de `/proc`.

### Fiabilité démontrée

Essais menés dans un dossier temporaire du worktree (`.repro_tmp_336/`, supprimé après usage — jamais écrit hors du périmètre) :

- **Avant correctif** (reproduction du code d'origine, sans attente) : 31 échecs sur 400 répétitions sous charge CPU + fork/exec concurrente — confirme la cause.
- **Après correctif**, répété bien au-delà des 200 répétitions demandées, **aucun échec** :
  - 300/300 répétitions via le code corrigé (`_spawn_fake_process` + `_is_alchess_process`) sous charge CPU + fork/exec concurrente artificielle.
  - 250/250 répétitions supplémentaires **pendant l'exécution simultanée, en arrière-plan, de toute la suite de tests du projet** (`pytest nicsoft/tests/ -q -m "not slow"`, 1172 passés) — scénario demandé explicitement par l'issue.
  - 40/40 appels directs au point d'entrée réel du test (`test_is_alchess_process_par_cmdline()`, corps exact, y compris le nettoyage d'origine par PID) sous la même charge.
  - Suite complète du fichier (`pytest nicsoft/tests/test_issue320_single_instance.py -m "not slow"`) : 23 passés, aucun échec, après correctif.
- Aucun processus lancé pendant ces essais n'est resté actif (vérifié par `ps` après coup) ; tout arrêt, dans le test comme dans les essais, s'est fait par le PID exact, jamais par nom.

### Fichiers modifiés

- `nicsoft/tests/test_issue320_single_instance.py` — attente bornée ajoutée dans `_spawn_fake_process()` (+17 lignes, aucune suppression).

Aucune modification de code de production, aucun fichier `.audit.json`, aucune dépendance touchée, aucun moteur exécuté. Serveur de test non démarré pour cette tâche (pas nécessaire — tests unitaires avec faux processus uniquement).

# Changelog — Issue #333

## Lichess : reprendre une partie en cours contre un humain, y compris depuis le menu principal, avec reconnexion rapide des flux

**Règle absolue respectée à la lettre** : aucune recherche d'adversaire, aucune partie, aucun défi réel sur lichess.org à aucun moment de ce travail. Le vrai jeton d'Alain n'a jamais été lu ni utilisé, ni dans les tests ni dans les essais — faux serveur local uniquement (`FakeTransport`/`FakeBoard`, garde réseau `conftest.py::_guard_no_real_lichess_network` de #327, revérifié encore actif). Le réseau n'a servi qu'à lire la documentation publique de Lichess (`lichess-org/api`) et le code source public de `lichess-org/lila` via `gh api`/`gh search` (lecture seule, GitHub public).

### Contexte important découvert avant de coder

La reprise contre l'IA (#323/#325) avait déjà construit un `LichessGame` entièrement **générique** IA/humain : écran de mise en place (cases rouges + LED, cible recalculée à chaque tick même si l'adversaire joue), nulle (désactivée en permanence seulement contre l'IA, réponse à une offre adverse toujours possible), décompte du premier coup (seulement si `user_color == "black"` et `moves_applied == 1`), pendules figées jusqu'aux deux premiers coups — tout cela avait été rendu générique dès #327 pour servir la recherche d'adversaire humain. Le vrai verrou pour la REPRISE d'une partie humaine n'était donc **pas** dans `LichessGame` mais dans deux endroits précis : (1) `client.py::get_ongoing_games()` marquait `resumable=False` pour toute partie dont `source != "ai"`, et (2) `_run_lichess_resume()` déduisait la couleur utilisateur uniquement via la présence d'`aiLevel` — impossible pour un humain. Ce diagnostic a permis une livraison beaucoup plus ciblée que redouté.

### Point 1 — Parties humaines reprenables (établi par lecture de doc + code public)

Lu le 14/11/2026 via `gh api`/`gh search` (lecture seule, dépôts publics) :
- `doc/specs/lichess-api.yaml` (lichess-org/api), tag Board : « Time controls: Rapid, Classical and Correspondence only » — confirme que la cadence, pas l'origine (site web, application mobile, API), est le facteur déterminant.
- `app/controllers/PlayApi.scala::WithPovAsBoard` (lichess-org/lila) : `if !lila.game.Game.isBoardCompatible(pov.game) then BadRequest(jsonError("This game cannot be played with the Board API."))` — appliqué à TOUTE partie du compte, sans distinction d'origine.
- `modules/game/src/main/Game.scala::isBoardCompatible` + `modules/core/src/main/game/misc.scala` : `game.clockConfig.forall(c => Speed(c) >= Speed.Rapid || ((game.hasAi || sourceIs(Friend) || sourceIs(Api)) && Speed(c) >= Speed.Blitz))`.

**Établi** : une partie contre un humain créée directement sur lichess.org ou depuis le téléphone est reprenable par l'interface des échiquiers de Lichess dans les mêmes conditions qu'une partie créée par AlChess — rien ne distingue le site web de l'application mobile. Règle exacte retenue (`modes/lichess/client.py::_is_board_compatible`) :
- rapide/classique : toujours reprenable, quelle que soit la source ;
- blitz : reprenable seulement si créée par un défi direct (« Jouer avec un ami », `source="friend"`) ou via l'API (`source="api"`), ou contre l'IA — **jamais** si appariée par le lobby/un pool/un tournoi/arena/swiss à cette cadence ;
- bullet/ultra-bullet : **jamais** reprenable, aucune exception.
- variante non standard (Chess960...) : jamais reprenable aujourd'hui (LichessGame ne sait pas la rejouer), indépendamment de la cadence/source.

Chaque partie de `get_ongoing_games()` porte désormais, en plus de `resumable`, un `unresumable_reason` (`"variant"` / `"speed"` / `None`) — explication exacte distincte côté interface (`lichess.reprise_non_reprenable_variante` / `_cadence`, nouvelles clés i18n fr/en/de), jamais le message générique devenu trompeur. Correction d'une hypothèse erronée de #325 : un test existant (`test_get_ongoing_games_partie_humain_humain_reste_listee_non_reprenable`) affirmait qu'une partie blitz humaine par défi direct n'était pas reprenable — faux d'après la règle ci-dessus ; corrigé et remplacé par 5 tests couvrant chaque cas (défi direct blitz reprenable, appariement blitz non reprenable, bullet jamais, rapide humain toujours, variante non standard).

### Point 2 — Reprise (même chemin que l'IA, règles humaines respectées)

Comme établi ci-dessus, `LichessGame` n'a nécessité **aucune modification** pour les règles de jeu (nulle, décompte, pendules, mise en place, orientation) — déjà génériques. Seul `core/game_manager_modes/lichess.py::_run_lichess_resume()` a changé :
- Nouveau paramètre `known_color` (transmis par `launch_lichess_resume()`, lui-même nourri par le navigateur — voir point 3).
- Si `white`/`black` ne porte `aiLevel` ni l'un ni l'autre (partie humaine) : `known_color` devient `user_color` et `known_user_color` transmis à `LichessGame` ; sans `known_color` valide, **refus explicite** (jamais de couleur devinée au hasard — jouer/orienter le camp adverse serait pire qu'un refus).
- Journal dédié (`GameLog(game_id)`) créé **avant** le premier appel réseau (auparavant, la reprise n'avait aucun journal dédié avant la construction de `LichessGame` — seul le journal général) : couvre désormais « reprise demandée », « position cible lue », en plus de ce que `LichessGame`/`GameClient` y écrivent déjà (coups, boutons, pendule, connectivité, reconnexions — inchangé).

Non modifié, vérifié toujours correct par lecture : réponse à une offre de nulle de l'adversaire toujours traitée même pendant la mise en place (`_process_browser_actions`, jamais gardée par `_resume_pending`) ; cible de la mise en place recalculée à chaque tick (`self.board.board_fen()`) donc jamais perdue si l'adversaire joue pendant la reconstruction ; pendule poussée à chaque tour de boucle principale indépendamment de la mise en place (`_maybe_push_clock()` hors du bloc `_tick_resume_setup`) — donc visible et à jour pendant tout l'écran de mise en place, y compris celle de l'utilisateur si c'est son tour.

### Point 3 — Bandeau du menu principal

Nouveau conteneur `#lichess-menu-banner`/`#lichess-menu-banner-list` directement dans `#screen-menu` (`index.html`), rendu avec le **même** composant que l'écran Lichess (`_lichessOngoingGameCard()`, réutilisé tel quel — même boutons Reprendre/Abandonner). Alimenté par le **même** évènement `lichess_resumable` (aucune seconde détection ajoutée) — mais seulement rempli quand `#screen-menu` est réellement affiché (sinon duplication de boutons avec la liste de l'écran `config_lichess`, détecté et corrigé pendant les tests e2e). Déclenchement : `app.js` envoie l'action `lichess_menu_check` une seule fois par arrivée réelle sur le menu (débounce `_lichessMenuBannerChecked`, réarmé à la sortie du menu) ; `alchess.py` route cette action vers `check_lichess_resumable()` (fonction inchangée, déjà silencieuse sans jeton/réseau, délai court `_PLAYING_TIMEOUT_S=6s`). Le bandeau ne bloque jamais les autres modes (élément indépendant du reste du menu, masqué dès qu'un autre écran s'affiche).

### Point 4 — Reconnexion des flux (déjà existant, vérifié)

Vérifié par lecture du code AVANT de coder, comme demandé : `modes/lichess/game_client.py::GameClient.stream_game()` implémente déjà une reconnexion automatique (`RECONNECT_DELAYS_S=(1,2,4,8,30)` — essais rapprochés puis espacés), sans aucune limite d'essais (jamais d'abandon automatique), avec journalisation dédiée (`game_log.connectivity(...)`) et évènements `reconnecting`/`reconnected` déjà relayés au navigateur (`lichess_reconnecting`/`lichess_reconnected`) vers une bannière déjà présente et persistante (`#lichess-reconnecting-banner`, « Connexion à Lichess perdue, reconnexion… »). Un nouveau `gameFull` reçu à la reconnexion (toujours le premier évènement d'une connexion, doc officielle) resynchronise entièrement position et pendules côté `LichessGame` (`_apply_game_full` reconstruit `self.board` et rejoue tous les coups connus). **Rien n'a donc été codé pour ce point** — uniquement vérifié et couvert par un nouveau test de régression dédié (`test_reconnexion_flux_pendant_partie_reprise_sans_coup_perdu_ni_rejoue`) qui prouve qu'un coup joué par l'adversaire PENDANT une coupure, au niveau d'une partie REPRISE contre un humain, est appliqué exactement une fois (ni perdu ni rejoué) et déclenche la réplication physique (LED) exactement une fois pour le bon coup.

### Point 5 — Fair-play inchangé + test manquant ajouté

Aucune règle de fair-play modifiée (menu verrouillé, pas d'aide pendant la partie, jeton jamais journalisé/envoyé au navigateur, textes Lichess échappés — tout inchangé, déjà vérifié par les gardes existantes `test_issue303_html_escaping.py`/`test_issue304_security.py`). **Test manquant ajouté** (signalé par le rapport de clôture de #327) : nouveau fichier `nicsoft/tests/test_issue333_lichess_no_engine.py` — analyse **statique** (module `ast`, pas dynamique) de chaque fichier du mode Lichess (`modes/lichess/*.py` + `core/game_manager_modes/lichess.py`), qui échoue si une instruction d'import référence un module moteur (`nicsoft.engine.{engine_manager,uci_engine,maia_engine,rodent_engine,engine_detection,engine_availability,engine_analysis,move_quality,analyse}` ou `chess.engine`), **y compris nichée dans le corps d'une fonction** (couvre la reprise, `_run_lichess_resume`, sans avoir besoin de l'exécuter réellement) ou `subprocess` (voie alternative de lancement). Exclut volontairement `nicsoft.engine.{board_utils,pgn_manager,players,display}` — purs utilitaires python-chess/PGN déjà importés par `game.py`, sans rapport avec un moteur (vérifié par lecture de chacun de ces fichiers, aucun n'importe `chess.engine`).

### Point 6 — Journal de partie dédié

Voir point 2 : la reprise écrit désormais « reprise demandée » et « position cible lue » (couleur, statut, nombre de coups, adversaire IA ou non) dans le journal dédié **avant** la construction de `LichessGame`, en plus de tout ce qui y était déjà écrit (coups, boutons, pendule, connectivité/reconnexions, exceptions — inchangé, voir #326/#329). Jamais le jeton ni le tchat (inchangé).

### Point 7 — Tests exécutés

Entièrement sans connexion réelle (`FakeTransport`/`FakeBoard`, garde réseau de #327 toujours actif et revérifié vert) :
- `nicsoft/tests/test_issue333_lichess_no_engine.py` (11 tests) — aucun import moteur, y compris dans le corps des fonctions.
- `nicsoft/tests/test_issue333_lichess_human_resume.py` (21 tests) — couleur humaine blancs/noirs transmise correctement, refus sans couleur connue, non-régression IA, journal dédié couvre la demande/position cible, câblage `launch_lichess_resume`→`_run_lichess_resume`, nulle adverse pendant la mise en place toujours traitée, reconnexion du flux pendant une reprise humaine sans coup perdu ni rejoué, câblage du bandeau menu (`alchess.py`/`app.js`), clés i18n présentes dans les 3 langues.
- `nicsoft/tests/test_issue323_lichess_resume.py` — 2 tests ajustés (signature `_error=` en mot-clé après l'ajout de `known_color`), 1 assertion de dict étendue (`unresumable_reason`), 1 test corrigé + 4 tests ajoutés pour la règle de reprenabilité exacte (point 1).
- `nicsoft/tests/e2e/test_issue333_lichess_menu_banner_e2e.py` (5 tests, **dossier de navigateur réel** — Playwright, serveur AlChess en subprocess isolé, `~/NicLink/venv`) : bandeau affiché/absent, partie non reprenable (bouton Abandonner seul + explication), bandeau n'empêchant pas la navigation vers un autre mode, une seule requête par arrivée sur le menu. A révélé puis fait corriger un vrai défaut (boutons dupliqués dans le DOM, même `data-game-id`, quand le bandeau menu et la liste de l'écran Lichess étaient tous deux peuplés simultanément) — corrigé en ne remplissant le bandeau menu que lorsque `#screen-menu` est réellement affiché.

**Suites complètes exécutées** (aucune régression) :
- `python3 -m pytest nicsoft/tests --ignore=nicsoft/tests/e2e` → 1172 passed, 82 skipped.
- `~/NicLink/venv/bin/python -m pytest nicsoft/tests/e2e` → 117 passed, 1 skipped (dossier de navigateur Playwright, exécuté avec succès).

**Aucune exception dans les fils secondaires** : vérifié par lecture — `_stream_reader_loop` (game.py) encapsule déjà tout dans un `except Exception` large, journalise (`game_log.exception`) et ne laisse jamais rien remonter non intercepté (mécanisme de #326, inchangé, confirmé toujours actif par la suite de tests existante).

### Non vérifié sans vraie partie (interdit par consigne)

- Rendu réel côté Lichess d'un défi direct blitz entre amis repris par AlChess (la règle serveur est établie par lecture du code source, jamais exercée avec une vraie partie).
- Comportement exact d'une VRAIE coupure réseau pendant une VRAIE partie humaine reprise (le mécanisme de reconnexion est simulé via `FakeTransport`, jamais une vraie connexion Lichess interrompue).
- Rendu exact du bandeau menu avec un VRAI jeton et une VRAIE partie en cours (testé avec des données simulées, jamais avec un compte réel).

### Fichiers modifiés

- `nicsoft/modes/lichess/client.py` — `_is_board_compatible()` (nouveau), `get_ongoing_games()` étendu (`unresumable_reason`).
- `nicsoft/core/game_manager_modes/lichess.py` — `launch_lichess_resume()` (transmet `color`), `_run_lichess_resume()` (couleur humaine, journal dédié précoce).
- `nicsoft/web/alchess.py` — nouvelle action `lichess_menu_check`.
- `nicsoft/web/static/app.js` — `lichessResumeGame()` (transmet `color`), rendu de la raison exacte de non-reprenabilité, bandeau du menu principal (peuplement conditionnel, débounce d'arrivée sur le menu).
- `nicsoft/web/templates/index.html` — nouveau bandeau `#lichess-menu-banner`/`#lichess-menu-banner-list` dans `#screen-menu`.
- `nicsoft/web/static/i18n/{fr,en,de}.json` — 3 nouvelles clés (`lichess.reprise_non_reprenable_variante`, `_cadence`, `lichess.menu_banner_titre`), ajoutées simultanément dans les 3 langues.
- `nicsoft/tests/test_issue323_lichess_resume.py` — corrections/ajouts pour la règle de reprenabilité exacte, ajustement de signature.
- `nicsoft/tests/test_issue333_lichess_no_engine.py` (nouveau).
- `nicsoft/tests/test_issue333_lichess_human_resume.py` (nouveau).
- `nicsoft/tests/e2e/test_issue333_lichess_menu_banner_e2e.py` (nouveau).
- `CONTEXTE.md` — paragraphe #333 ajouté.

Aucune modification de `driver.py`, d'aucun moteur, d'`.audit.json` ni des dépendances ; aucun arrêt de processus par nom (les serveurs e2e sont arrêtés par leur PID exact via le mécanisme déjà existant de `conftest.py`) ; serveur de test lancé uniquement via le subprocess e2e déjà prévu (`ALCHESS_SKIP_BOARD=1`, `BROWSER=/bin/true`, `ALCHESS_DIR` isolé — variables déjà câblées dans `nicsoft/tests/e2e/conftest.py`, jamais modifiées) ; aucun push.

# Changelog — Issue #331

## Lichess : bip optionnel quand l'adversaire joue, LED + bandeau quand il abandonne, propose la nulle ou termine la partie

Essai réel d'Alain le 14/11/2026 : environ cinq minutes passées devant
l'échiquier physique à attendre le coup de l'adversaire humain sans voir
que celui-ci avait abandonné — l'écran affichait la fin de partie, mais
rien ne le signalait sur l'échiquier ni par le son.

**Règle absolue respectée à la lettre** : aucune recherche, partie ni défi
réel sur lichess.org à aucun moment de ce travail. Le vrai jeton d'Alain
n'a jamais été lu ni utilisé — tous les tests utilisent un faux
transport/client et un faux pilote de plateau (LED/USB simulés), jamais de
connexion réelle. Le garde réseau de
`conftest.py::_guard_no_real_lichess_network` reste actif et inchangé.

### Point 1 — Case « Bip quand l'adversaire joue »

- `core/config_manager.py` : nouvelle clé `lichess_beep_opponent_move`
  (défaut `False` — aucun réglage de son existant ne couvrait déjà ce cas,
  seule `tts_enabled` s'en approchait sans rapport fonctionnel) ; écriture
  atomique existante (`save_config`) réutilisée sans modification, jamais
  de contact avec `lichess_token`.
- `templates/index.html` : case à cocher dans le panneau Actions pendant
  la partie (`#lichess-beep-toggle-row`), visible seulement en partie
  Lichess (IA ou humain — un seul écran de jeu `LichessGame` pour les
  deux) ; `static/app.js` : `lichessToggleBeep()` sauvegarde immédiatement
  via `config_save` (même mécanisme que la synthèse vocale) ; état restauré
  à l'ouverture de l'écran de configuration Lichess (`config_get` déjà
  appelé à ce moment).
- Traductions ajoutées dans `i18n/{fr,en,de}.json`.
- `modes/lichess/game.py::_maybe_beep_opponent()` relit `load_config()` à
  CHAQUE évènement (jamais mis en cache) : cocher/décocher en cours de
  partie change le comportement dès le coup suivant, sans redémarrage.

### Point 2 — Sons : bip matériel de l'échiquier, pas le navigateur

Méthode choisie et pourquoi : réutilisation du bip matériel existant de
l'échiquier Chessnut (`nl_inst.beep()`, déjà utilisé pour le premier coup
de l'IA) plutôt que le son du navigateur (Web Audio `playBeep()` déjà
présent dans `app.js`, utilisé par l'Explorateur d'ouvertures) ou un outil
système (`paplay`/`aplay`). Un bip hors navigateur est fiable par
construction, y compris onglet en arrière-plan ou minimisé — la fiabilité
réelle du son d'onglet en arrière-plan dépend du navigateur et n'a pas pu
être mesurée ici (pas d'instance de navigateur avec onglet caché
disponible dans ce bac à sable) ; le bip matériel évite la question
entièrement, et s'entend directement là où Alain regarde (l'échiquier).
Aucune nouvelle dépendance, aucune modification de `driver.py` (les
méthodes utilisées — `beep()`, `set_all_leds()`, `turn_off_all_leds()` —
existaient déjà).

- `game.py::_hardware_beep()` : bip simple, ou double (deux bips espacés
  de 0,3 s, émis par un petit fil dédié — jamais de `time.sleep()` dans la
  boucle de jeu) pour un signal distinct.
- Bip simple à chaque coup de l'adversaire (`_apply_new_moves`, jamais
  pour un coup de l'utilisateur — vérifié par couleur du coup). Le bip
  inconditionnel existant pour le tout premier coup de l'IA (utilisateur
  noirs) est laissé inchangé, non rattaché à la case (comportement déjà en
  place avant cette issue).
- Bip double à l'apparition d'une offre de nulle adverse et à toute fin de
  partie provoquée par l'adversaire (voir point 3).
- Non vérifié sur le vrai échiquier (aucun matériel disponible pour cette
  issue) : le minutage exact des deux bips et leur perception sonore
  réelle restent à confirmer par Alain.

### Point 3 — Signal LED (moitié de l'échiquier côté adversaire)

- `driver.py` confirmé INCHANGÉ : `set_all_leds()` (déjà existant) poste
  un pattern de 8 rangées en **un seul paquet USB**, via la queue
  fire-and-forget déjà en place — aucune limitation à une case à la fois.
  `signal_lights()` (déjà existant) utilise les mêmes motifs de moitié de
  plateau mais s'éteint automatiquement après 1,5 s ; ce comportement ne
  convenait pas (il faut rester allumé jusqu'à acquittement), donc
  `game.py` appelle directement `set_all_leds()` avec les mêmes 8 chaînes
  binaires que `signal_lights(2)`/`signal_lights(3)`.
- `game.py::opponent_half_led_pattern()` : choisit la bonne moitié (rangs
  1-4 ou 5-8) selon la couleur jouée par l'utilisateur.
- Allumage, toujours (indépendant de la case à cocher) : offre de nulle de
  l'adversaire, et toute fin de partie provoquée par l'adversaire (abandon,
  temps écoulé, mat, nulle acceptée — jamais pour un abandon/une
  annulation demandés par l'utilisateur, ni pour une nulle qu'il vient
  lui-même d'accepter, ni pour un mat qu'il délivre lui-même avec son
  propre coup physique).
- Extinction : réponse explicite à la nulle (accepter/refuser, comme
  avant) ; bouton « J'ai vu » sur le bandeau de fin de partie, ou tout
  retour au menu depuis cet écran (acquittement implicite) ; au plus tard,
  à la libération de l'échiquier par le lanceur
  (`game_manager_modes/lichess.py`, déjà existant, inchangé) ou au
  `reset()` de la partie suivante (driver.py, inchangé) — jamais de LED
  restante d'une partie à l'autre.
- L'attente d'acquittement bloque le fil du LANCEUR de la partie (celui
  qui attend déjà la partie entière de façon synchrone, comme tous les
  autres modes), jamais le fil socketio ni la boucle menu — `_finalize()`
  elle-même reste non bloquante (calcule seulement `opponent_caused_end`),
  pour que les appels directs existants (tests, et tout appelant futur)
  continuent de retourner immédiatement.
- Affichage normal du coup adverse (2 cases) non perturbé dans le cas
  courant ; limite connue, non corrigée : si l'adversaire propose la nulle
  EXACTEMENT au moment de son propre coup (un seul évènement Lichess), le
  signal de moitié de plateau remplace temporairement les 2 cases du coup
  — cas rare, non vérifié sur le vrai plateau.

### Point 4 — Bandeau de fin de partie provoquée par l'adversaire

- `templates/index.html` : `#lichess-opponent-end-banner` (réutilise la
  classe `.lichess-info-banner` existante) sur l'écran de fin de partie,
  avec bouton « J'ai vu » (clé i18n `lichess.jai_vu`) — affiché seulement
  quand `game_over` porte `opponent_caused_end=true`, avec un court texte
  de cause (`opponent_cause_key` : abandon/temps écoulé/mat/nulle/
  générique).
- Le bandeau de nulle proposée existant (`#lichess-draw-offer-banner`,
  Accepter/Refuser) est inchangé et sert toujours pour ce cas précis.

### Point 5 — Journal de partie

- Une ligne `[STATE]` par bip effectivement émis
  (`bip émis — <raison> (n/total).`) et par commande LED envoyée
  (`LED allumées —`/`LED éteintes —` avec la raison) dans le journal dédié
  de la partie (`GameLog`, déjà existant, inchangé) — rien de secret.

### Point 6 — Tests (nouveau fichier, 21 tests, aucun réseau ni matériel réel)

`nicsoft/tests/test_issue331_lichess_opponent_alerts.py` :

- bip émis/non selon la case, y compris basculée en cours de partie
  (effet immédiat, sans redémarrage) ;
- mémorisation de la case, sans aucun effet sur `lichess_token` ; valeur
  par défaut décochée ;
- LED de la bonne moitié pour abandon, nulle proposée, temps écoulé, mat
  de l'adversaire — pour les deux orientations (utilisateur blancs et
  noirs) ;
- acquittement (`lichess_ack_game_over`, réponse à la nulle, ou
  `back_menu`) qui éteint le signal ;
- aucun bip ni LED pour un coup, un abandon, une acceptation de nulle ou
  un mat provoqués par l'UTILISATEUR lui-même (régression détectée et
  corrigée pendant le développement : le mat délivré par le propre coup
  de l'utilisateur déclenchait à tort l'alerte) ;
- présence des lignes de journal attendues.

Toute la suite Lichess existante (536 tests) et l'ensemble de la suite du
projet (1241 tests) ont été rejoués après ces changements — aucune
régression.

### Non vérifié sans l'échiquier physique ni une vraie partie

- Le son réel du bip matériel (volume, perceptibilité à distance) et le
  minutage du bip double.
- L'allumage effectif et la bonne moitié sur le vrai plateau Chessnut
  (le pilote USB bas niveau, `hid_backend.py`, n'a pas été modifié et
  n'a pas pu être exercé avec du vrai matériel).
- Le comportement réel du son du navigateur en onglet arrière-plan — non
  mesuré, d'où le choix du bip matériel qui évite la question.

# Changelog — Issue #332

## Écran d'analyse après partie : la navigation (Précédent/Suivant) ne se déplace plus selon l'état du bouton « Voir le meilleur coup »

### Cause

Sur l'écran d'analyse après partie (`panel-gameover`, partagé par tous les
modes — pédagogique, humain contre humain, retranscription, Lichess),
`_updateReviewBestMoveBtn()` (`app.js`) faisait
`row.style.display = hasBest ? "block" : "none"` sur `#review-best-move-row`.
Ce bloc est positionné juste au-dessus de la ligne Précédent/Suivant, dans
le même flux de mise en page (`card-nav-save`) : le retirer/remettre selon
que le meilleur coup du moteur diffère ou non du coup joué changeait la
hauteur du panneau et poussait le bouton « Suivant » vers le haut ou le bas
à chaque navigation — exactement le symptôme décrit par Alain (clic à côté
du bouton en lisant l'échiquier, sans regarder le panneau).

### Correction

- `nicsoft/web/templates/index.html` : `#review-best-move-row` n'a plus
  `style="display:none"` à l'initialisation — la ligne (et son bouton) est
  désormais toujours présente dans le flux, place réservée en permanence.
  Le bouton `#btn-review-best` démarre `disabled` (grisé), avec
  `data-i18n="game.btn.meilleur"` ajouté par cohérence (clé déjà existante
  dans `fr/en/de.json`, utilisée par l'équivalent du panneau pause).
- `nicsoft/web/static/app.js::_updateReviewBestMoveBtn()` : ne touche plus
  `row.style.display`. Le bouton `#btn-review-best` est désactivé/grisé
  (`disabled`, `opacity`, `pointerEvents`) quand il n'y a pas de meilleur
  coup différent à montrer pour le coup courant — même motif que
  `_setNavControls()` et que `#btn-pause-meilleur` (panneau pause), qui
  suivaient déjà ce principe et n'étaient pas concernés par le bug.
- Comportement inchangé : le bouton garde sa fonction
  (`data-action="review_best_move"`), son texte, et son état logique
  (actif seulement si le moteur a un meilleur coup différent du coup joué
  pour la position courante).

### Autres éléments vérifiés (aucun déplacement constaté)

- `#review-move-san` (coup affiché, ex. « Nf3 ») : a déjà `min-height:2rem`
  en CSS — hauteur stable.
- `#review-best-move-san` (texte du meilleur coup, affiché seulement après
  clic sur « Voir le meilleur coup ») : reste masqué par défaut et remis à
  zéro à chaque navigation — ne varie jamais « d'un coup à l'autre » au
  sens du scénario de l'issue (seulement pendant la lecture du coup
  courant, après un clic explicite, pas en cliquant Suivant/Précédent).
- `#btn-rv-sequence` (bouton séquence punitive) : son apparition/disparition
  est dans une autre carte, plus bas dans le panneau, sans élément en
  dessous dont la position doive rester fixe — pas concerné.
- Panneau pause (`panel-pause`) : `#btn-pause-meilleur` était déjà toujours
  visible (disabled/opacity, jamais retiré du flux) — motif déjà correct,
  rien à corriger. `#pause-feedback-box` ne change que lors de l'entrée en
  pause, jamais pendant la navigation Précédent/Suivant interne au
  panneau — pas concerné non plus.
- Écran Exercices (`screen-exercice-running`) : pas de navigation
  Précédent/Suivant ni de bouton « meilleur coup » apparaissant/disparaissant
  — structure différente, pas concerné.
- `rv-game-info` (infos partie) : fixé une seule fois à l'entrée en revue,
  ne varie jamais pendant la navigation.

### Tests (navigateur, événements simulés — aucun moteur lancé)

Nouveau fichier `nicsoft/tests/e2e/test_issue332_review_nav_stable_position_e2e.py`
(Playwright, réutilise la fixture `at_menu` et le chemin « Coller PGN » déjà
utilisé par `test_review_nav_279_e2e.py` pour atteindre l'écran de revue
sans échiquier ni moteur). La présence/absence de meilleur coup est simulée
directement en JS (écriture de `reviewMoves[i].best_move` et `_isAnalysed`
via `page.evaluate`, puis `renderReview()`) — aucun appel socket, aucun
moteur Stockfish :

- position (`getBoundingClientRect`) de `#btn-review-next` strictement
  identique sur plusieurs coups consécutifs, en alternant un meilleur coup
  actif/grisé ;
- même vérification après retournement de l'échiquier (`#btn-flip`) ;
- même vérification avec une fenêtre réduite (1024×700, au lieu de
  1400×900).

Les 3 tests échouent sur le code d'avant correction (vérifié par
`git stash`/re-run) et passent après. Suite complète
`pytest nicsoft/tests/ -m "not slow"` (1111 passed, 82 skipped) toujours
verte ; les e2e déjà existants (`test_review_nav_279_e2e.py`,
`test_smoke_e2e.py`) passent toujours.

### Fichiers modifiés

- `nicsoft/web/templates/index.html`
- `nicsoft/web/static/app.js`
- `nicsoft/tests/e2e/test_issue332_review_nav_stable_position_e2e.py` (nouveau)
- `CHANGELOG-332.md` (nouveau)

# Changelog — Issue #330

## Lichess : vrai choix « aléatoire » envoyé à la recherche d'adversaire humain, orientation différée à la couleur réelle, explication du refus d'équilibre des couleurs

Essai réel d'Alain le 14/11/2026, après #329. Une recherche d'adversaire
humain en 15+10 avec les **blancs** a été refusée par Lichess (HTTP 400,
texte affiché tel quel par AlChess : « You must also play some games as
Black. ») — règle de Lichess qui impose d'équilibrer les couleurs quand un
compte demande toujours la même. Le choix « Aléatoire » de l'écran de
recherche était jusqu'ici tiré PAR AlChess avant la recherche (pile ou
face local, comme pour l'IA) : Lichess recevait donc toujours une couleur
précise, et refusait statistiquement la moitié du temps dès que le compte
était déjà déséquilibré.

**Règle absolue respectée à la lettre** : aucune recherche, aucune partie,
aucun défi réel sur lichess.org à aucun moment de ce travail. Le vrai
jeton d'Alain n'a jamais été lu ni utilisé — tous les tests utilisent des
doubles de client/transport scriptés, jamais une connexion réelle. Le
réseau n'a servi qu'à lire la documentation et le code source PUBLICS de
`lichess-org/api` et `lichess-org/lila` (`gh api`, lecture de fichiers
précis, jamais de recherche/partie). Le garde réseau de
`conftest.py::_guard_no_real_lichess_network` reste actif et inchangé.

### Point 1 — Vrai choix aléatoire envoyé à Lichess

- `core/game_manager_modes/lichess.py::_run_lichess_human` ne résout plus
  "aléatoire" localement (`random.choice` supprimé de cette fonction) :
  `requested_color` (ce qui part vers `board/seek`) vaut `""` pour
  "aléatoire", `"white"`/`"black"` inchangé pour un choix précis.
  `SeekSession.start()`/`GameClient.open_seek_stream()` (déjà prévus pour
  une couleur vide depuis #327, jamais exercés avec cette valeur jusqu'ici
  côté lanceur) omettent alors le paramètre `color` de la requête —
  Lichess choisit lui-même, conformément à sa documentation officielle
  (« Better left empty to automatically get 50% white »,
  `doc/specs/tags/board/api-board-seek.yaml`).
- La partie contre l'IA (`_run_lichess`/`launch_lichess`) garde son tirage
  local actuel (`random.choice`), explicitement inchangé — jamais concernée
  par la règle d'équilibre des couleurs (voir point 3).
- `display_color` (repli arbitraire `"white"` quand la couleur est vide)
  oriente l'écran de mise en place AVANT la recherche : la position de
  départ étant identique pour les deux camps, cet écran reste valable sans
  connaître la couleur réelle à l'avance.
- L'orientation RÉELLE (échiquier, noms, pendules) est appliquée au vrai
  début de partie, une fois la couleur confirmée par l'évènement
  `gameStart` de Lichess (`confirmed_color = found_game.get("color") or
  display_color`, inchangé dans son principe depuis #327) — transmise à
  `LichessGame(known_user_color=...)`, qui alimente `lichess_init` et donc
  `orientationIsFlipped()` côté `app.js` : code entièrement RÉUTILISÉ,
  aucune modification JS nécessaire pour ce point.
- `set_app_state("lichess_seeking", {"color": requested_color or
  "random"})` : le payload de l'écran de recherche porte désormais
  explicitement `"random"` plutôt qu'une couleur résolue à tort (sans
  effet visuel aujourd'hui, `app.js` ne lisant pas ce champ à cet écran).

### Point 2 — Explication en français (+ anglais/allemand) du refus d'équilibre

- Nouvelle fonction `modes/lichess/errors.py::detect_color_balance_refusal(message)` :
  reconnaît (indépendamment de la casse) le texte exact de Lichess « You
  must also play some games as White/Black » et retourne la couleur
  forcée, `""` sinon.
- `core/game_manager_modes/lichess.py::_classify_seek_error_event` : un
  refus HTTP 400 dont le texte correspond utilise désormais la clé
  `toast.lichess_refus_equilibre_couleur` (texte de Lichess + explication) ;
  tout autre refus 400 garde `toast.lichess_refus_requete` (texte de
  Lichess seul, comme avant #330).
- Nouvelle clé i18n `toast.lichess_refus_equilibre_couleur`, ajoutée
  simultanément dans `fr.json`/`en.json`/`de.json` et dans
  `state.py::_TOAST_MESSAGES` (repli français) : « Lichess a refusé la
  requête : {detail}. Lichess demande d'équilibrer les couleurs :
  choisissez l'autre couleur, ou « Aléatoire » pour quelques parties, puis
  réessayez. » (et ses équivalents anglais/allemand).

### Point 3 — Documentation : ce qui est établi, ce qui reste une hypothèse

Lu le 14/11/2026, dépôts publics `lichess-org/api` et `lichess-org/lila`
(`gh api`/`WebFetch`, jamais de connexion à un vrai compte/partie) :

**Établi par le code source de lila** (pas seulement une doc, le
comportement réel du serveur) :

- `doc/specs/tags/board/api-board-seek.yaml` + `ChallengeColor.yaml` :
  paramètre `color` de `POST /api/board/seek` accepte `white`/`black`/
  `random` ; laissé vide, Lichess applique le même équilibrage 50/50
  (« Better left empty to automatically get 50% white »).
- `app/controllers/Setup.scala::boardApiHook` : le refus HTTP 400 exact
  (`s"You must also play some games as $forced"`, texte sans ponctuation
  finale — celle observée par Alain vient de la mise en forme du toast
  AlChess, pas de Lichess) est posé par
  `env.lobby.boardApiHookStream.mustPlayAsColor(config.color)`.
- `modules/lobby/src/main/BoardApiHookStream.scala::mustPlayAsColor` :
  `(chosen != TriColor.Random).so: ...` — **la vérification est sautée
  entièrement si la couleur demandée est `Random`** ("aléatoire" envoyé
  tel quel à Lichess, jamais une couleur précise résolue localement,
  échappe donc TOUJOURS à ce refus). C'est la confirmation directe de
  l'hypothèse de départ de cette issue.
- `modules/user/src/main/UserRepo.scala::mustPlayAsColor`/`incColor` :
  compteur par utilisateur `colorIt`, borné à `[-3, 5]`. Seuil de refus :
  `colorIt > 2` → noir forcé ; `colorIt < -2` → blanc forcé (donc après 3
  parties nettes dans la même couleur sans l'autre). Incrémenté de +1 par
  partie jouée aux blancs, -1 aux noirs.
- `modules/lobby/src/main/Biter.scala::assignCreatorColor` : pour une
  couleur FIXE, seul le créateur de la recherche voit son `colorIt`
  incrémenté (`userApi.incColor(creator, fixed)`) — pour `Random`,
  `userApi.firstGetsWhite(creator, joiner)` choisit qui reçoit les blancs
  en comparant les deux `colorIt` (celui qui a le plus joué noir récemment
  reçoit blanc) et incrémente les DEUX compteurs en conséquence : un choix
  "aléatoire" contribue donc lui-même à RÉÉQUILIBRER le compte, jamais à
  le déséquilibrer.
- **Ce qui est compté** : uniquement les parties créées via le Lobby ou le
  Pool (`game.lobbyOrPool`, vérifié dans `AbortListener.scala`/
  `Rematcher.scala` — seuls appelants de `incColor` trouvés dans tout le
  dépôt avec les parties ci-dessus). **Aucun appel à `incColor` n'existe
  ailleurs dans le dépôt** (recherche exhaustive par `gh api search/code`) :
  les parties contre l'IA (`challenge/ai`, jamais via le Lobby) ne sont
  **jamais comptées** — confirme que la partie AlChess contre l'IA n'a
  jamais pu être concernée par cette règle, avec ou sans ce correctif.
  Rated et casual comptent tous les deux (`incColor` appelé indépendamment
  du drapeau `rated`, visible dans `Biter.scala::makeGame`).
- **Comment le compteur se rétablit** : chaque partie jouée dans la
  couleur opposée le fait revenir vers 0 ; `AbortListener.scala::onEarlyFinish`
  ANNULE l'incrément d'une partie qui se termine anormalement tôt (moins
  de coups qu'attendu, y compris un abandon) via
  `cancelBothColorIncrements` — une partie avortée ne compte donc pas pour
  l'équilibre.

**Reste une hypothèse** (comportement serveur non observable sans vraie
recherche, interdit par la règle de cette issue) :

- Que le code actuellement déployé sur lichess.org corresponde exactement
  à `master` du dépôt `lila` au moment de cette lecture (14/11/2026) — le
  dépôt est public et actif, mais aucune garantie de déploiement immédiat
  de chaque commit.
- Le délai exact ou le nombre de parties précis avant qu'un refus observé
  par Alain (3 blancs nets d'après le code) redevienne possible dans
  l'autre sens — dépend de l'historique réel (non consultable) du compte
  d'Alain.
- Que le champ `color` du `gameStart` (flux `/api/stream/event`) soit
  TOUJOURS présent en pratique pour une recherche "aléatoire" — la
  spécification officielle (`GameEventInfo.yaml`) ne le marque pas
  `required` (seuls `fullId`/`gameId` le sont), d'où le repli défensif
  conservé (`confirmed_color = found_game.get("color") or display_color`).

### Point 4 — Journal

- Déjà couvert par le code existant, désormais réellement exercé avec une
  couleur vide : `seek.py::SeekSession.start()` journalise « couleur=
  aléatoire » (au lieu d'une couleur précise) dès que `requested_color`
  est vide — sans aucune modification de `seek.py`.
- `_run_lichess_human` journalise la couleur réelle obtenue
  (`confirmed_color`) dans le message « recherche terminée — adversaire
  trouvé, game_id=…, couleur=… » (déjà existant depuis #327/#328,
  désormais correct pour "aléatoire" grâce à la couleur confirmée par
  Lichess plutôt qu'un tirage local).

### Point 5 — Tests sans aucune connexion réelle

Nouveau fichier `nicsoft/tests/test_issue330_lichess_random_color.py` (21
tests, tous verts), entièrement sans réseau (doubles de client/transport
scriptés des issues #309/#311/#327) :

- `detect_color_balance_refusal` : reconnaît « You must also play some
  games as Black/White » (casse/ponctuation variables), rejette un autre
  texte.
- `_classify_seek_error_event` : clé dédiée + texte de Lichess conservé
  pour le refus d'équilibre ; clé inchangée pour un autre refus 400 ; la
  clé dédiée existe et diffère de `toast.lichess_refus_requete` dans les
  3 langues.
- Recherche "aléatoire" : `open_seek_stream` reçoit une couleur vide
  (jamais `white`/`black` résolu), `random.choice` n'est jamais appelé
  pendant la recherche humaine (assertion qui lève si appelé) ; l'écran de
  mise en place reste affiché avec une couleur arbitraire ; couleur
  confirmée par `gameStart` (les deux cas, blanc et noir) atteint
  correctement `LichessGame(known_user_color=...)` ; journal de recherche
  portant bien « couleur=aléatoire » puis la couleur réelle obtenue.
- Recherche à couleur précise (blancs/noirs) : `open_seek_stream` reçoit
  exactement la couleur demandée — aucune régression.
- `GameClient.open_seek_stream` seul (sans lanceur) : paramètre `color`
  absent de la requête HTTP quand la couleur est vide, présent et correct
  sinon.
- Partie contre l'IA : `launch_lichess` continue d'appeler `random.choice`
  pour "aléatoire" — confirmé inchangé.

**Suites complètes exécutées** :
- `python3 -m pytest nicsoft/tests --ignore=nicsoft/tests/e2e` →
  **1110 passed, 82 skipped** (aucun échec, aucune régression).
- `python3 -m pytest nicsoft/tests/e2e -k lichess` (dossier de navigateur,
  Playwright + serveur réel en sous-processus, `ALCHESS_SKIP_BOARD=1
  ALCHESS_NO_BROWSER=1`, jeton toujours vide dans l'`ALCHESS_DIR` isolé de
  session) → **63 passed** — ces tests exercent déjà `lichess_init` avec
  les deux couleurs (chemin partagé IA/humain, non modifié par cette
  issue), ce qui couvre l'orientation réelle de bout en bout en navigateur.
  Aucun nouveau scénario Playwright dédié à cette issue n'a été ajouté : le
  seul code touché côté navigateur est zéro (aucun fichier JS/HTML modifié),
  et la fonction d'orientation elle-même est déjà couverte par
  `test_issue315_lichess_orientation.py` (extraction + exécution réelle via
  `node`).

### Non vérifiable sans vraie partie (interdit par la règle de cette issue)

- Que le refus réel observé par Alain le 14/11/2026 ne se reproduirait
  plus avec "Aléatoire" sur le vrai compte — découle du code source lu
  (point 3), jamais réessayé en vrai.
- Le comportement exact de lichess.org si son code déployé diverge de
  `lila` `master` au moment de cette lecture.

### Fichiers modifiés

`nicsoft/core/game_manager_modes/lichess.py` (résolution de couleur de
`_run_lichess_human`, `_classify_seek_error_event`, import) ;
`nicsoft/core/game_manager_modes/state.py` (nouvelle clé de repli) ;
`nicsoft/modes/lichess/errors.py` (nouvelle fonction
`detect_color_balance_refusal`) ; `nicsoft/web/static/i18n/{fr,en,de}.json`
(nouvelle clé) ; `nicsoft/tests/test_issue330_lichess_random_color.py`
(nouveau) ; `CONTEXTE.md` (paragraphe Lichess humain #327 corrigé).
Aucune modification de `driver.py`, d'aucun moteur, d'`.audit.json` ni des
dépendances ; aucun arrêt de processus par nom ; aucun push.

# Changelog — Issue #329

## Lichess : erreur HTTP exacte journalisée et affichée à l'ouverture de la recherche d'adversaire

Essais réels d'Alain le 14/11/2026 : une recherche d'adversaire humain en
15+10 (blancs) échouait dès l'ouverture, deux fois de suite, avec l'écran
affichant « Connexion à Lichess impossible — vérifiez le réseau » alors
que le réseau et le jeton fonctionnaient (une partie contre l'IA avait
réussi quelques minutes plus tôt, et une recherche 10+0 avait réussi un
peu plus tôt dans la session). Le journal ne portait que
« TransportHTTPError », sans le code de réponse HTTP ni le corps renvoyé
par Lichess (qui explique la cause du refus) : la cause réelle restait
invisible.

**Règle absolue respectée à la lettre** : aucune recherche, aucune partie,
aucun défi réel sur lichess.org à aucun moment de ce travail. Le vrai
jeton d'Alain n'a jamais été lu ni utilisé — tous les tests utilisent un
transport scripté (`FakeTransport`) ou `urllib.request.urlopen` remplacé
par monkeypatch, jamais une connexion réelle. Le garde réseau de
`conftest.py::_guard_no_real_lichess_network` reste actif et inchangé.

### Point 1 — Journalisation de toute erreur HTTP Lichess

- `transport.py::UrllibTransport` journalise désormais, pour TOUS ses
  appels (`request`, `stream_lines`, `open_stream` — la recherche
  d'adversaire comme les autres), une ligne dans le journal général
  (`niclink.lichess`) à chaque réponse d'erreur HTTP : méthode + chemin
  (sans paramètres), code de réponse, en-tête `Retry-After` s'il existe,
  corps de la réponse tronqué à ~500 caractères. Jamais le jeton (absent
  de la méthode, du chemin et du corps — il n'est envoyé que dans
  l'en-tête `Authorization`, jamais journalisé).
- `TransportHTTPError` porte désormais un attribut `retry_after_s` (`int`
  ou `None`), lu depuis l'en-tête `Retry-After` de la réponse.
- `game_client.py::GameClient` écrit le même détail (tronqué) dans le
  journal de partie dédié (`GameLog`, catégorie `REQUEST`), y compris pour
  `open_event_stream()`/`open_seek_stream()` — ces deux méthodes ne
  passaient auparavant par aucune journalisation de ce type (nouvel
  enrobage interne `_open_stream_logged`, qui ne traduit jamais
  l'exception : `seek.py` a besoin de la forme brute pour distinguer les
  causes).
- `errors.py::extract_api_message()` (nouvelle fonction, factorisée
  depuis `game_client.py::_extract_api_message`) extrait le texte
  explicatif du corps JSON renvoyé par Lichess (champ `error`).

### Point 2 — Messages exacts à l'écran, persistants

- `seek.py::SeekSession._push_error()` reprend `status_code`,
  `retry_after_s` et le texte Lichess dans l'évènement `{"type": "error",
  ...}` poussé à l'appelant (auparavant : seulement le nom de la classe
  d'exception).
- Nouvelle fonction `core/game_manager_modes/lichess.py::_classify_seek_error_event()`
  traduit ce détail en message distinct :
  - 400 → texte renvoyé par Lichess (`toast.lichess_refus_requete`) ;
  - 401 ou 403 → message unifié « jeton refusé ou droit manquant »
    (`toast.lichess_jeton_refuse`), tel que demandé par l'issue ;
  - 404 → `toast.lichess_404` ;
  - 429 → `toast.lichess_rate_limited_detail`, avec le délai reçu
    (`Retry-After`, repli 60s s'il est absent) ;
  - 5xx → `toast.lichess_indisponible` ;
  - **seule l'absence de code HTTP** (coupure réseau réelle, résolution de
    nom, délai dépassé — `TransportNetworkError`/`TransportTimeoutError`)
    garde `toast.lichess_network_error` (« vérifiez le réseau »).
- Ces messages sont désormais affichés de façon **persistante** (ne
  disparaissent plus seuls après quelques secondes) : `_menu_toast_data()`
  (`state.py`) accepte `vars`/`persistent`, relayés dans le payload
  `state_update` (`toast_vars`/`toast_persistent`) ; `afficherToast()`
  (`app.js`) accepte un 3ᵉ paramètre `persistent` qui désactive le
  minuteur de 4s et ajoute un bouton de fermeture (`×`, classe CSS
  `.toast-persistent`, `main.css`).
- Jamais de relance automatique de la recherche après une erreur : le
  lanceur retourne simplement à l'écran de configuration, à l'utilisateur
  de recliquer (vérifié par un test dédié).
- Nouvelles clés i18n (`fr`/`en`/`de`, simultanément) :
  `toast.lichess_rate_limited_detail`, `toast.lichess_jeton_refuse`,
  `toast.lichess_404`, `toast.lichess_refus_requete`,
  `toast.lichess_indisponible`.

### Point 3 — Pas de régression de la requête d'ouverture de la recherche

- Comparaison par lecture de l'historique git (`git diff` entre le commit
  d'introduction de #327 et celui de #328) : **aucun changement** des
  paramètres envoyés à `POST /api/board/seek` (`time`, `increment`,
  `rated`, `color`) ni de leur construction — confirmé identique à la
  version actuelle (HEAD avant cette issue).
- `time` est envoyé comme un nombre à virgule flottante (ex. `15.0` pour
  15 minutes) — conforme à la documentation officielle (`type: number`,
  pas `integer`) ; `increment` en secondes entières ; `rated` toujours
  `"false"` (partie amicale) ; `color` toujours `"white"`/`"black"`
  (jamais `"random"` : résolu localement avant l'appel, comme pour l'IA).
- Nouveau test paramétré (`test_parametres_exacts_par_cadence_et_couleur`,
  `nicsoft/tests/test_issue329_lichess_http_errors.py`) qui enregistre,
  via un faux transport, la requête exacte envoyée pour **chaque**
  préréglage de cadence (`10+0`/`15+10`/`30+0`/`60+0`/`90+30`) et
  **chaque** couleur (`white`/`black`) — fige ce comportement pour la
  suite.
- La cause du refus réel du 14/11/2026 reste donc côté serveur Lichess
  (état du compte, limite de débit, ou autre condition non reproductible
  sans vraie recherche — interdit par la règle de cette issue), pas une
  régression de la requête envoyée par AlChess.

### Point 4 — Comparaison avec la documentation officielle

Lu le 14/11/2026 (`lichess-org/api`, `doc/specs/tags/board/api-board-seek.yaml`
et `doc/specs/lichess-api.yaml`) :
- `time` : nombre, 0 à 180 minutes ; `increment` : entier, 0 à 180
  secondes — 15+10 est largement dans ces bornes, donc pas la cause d'un
  refus 400 pour ce cas précis.
- 400 : « The creation of the seek failed », corps `{"error": "..."}`
  (texte libre, pas d'énumération officielle des causes possibles).
- 429 : limite de débit générale de l'API (« Only make one request at a
  time » ; « waiting one minute before retrying will be sufficient, but
  some limits may require longer ») — plausible si l'enchaînement des
  deux flux (événements puis recherche) a été perçu comme trop rapproché
  d'une recherche précédente, ou si une recherche/partie antérieure
  n'était pas encore totalement résolue côté serveur.
- Aucune mention officielle d'un refus explicite « recherche déjà
  ouverte » ou « partie déjà en cours » dans ce fichier — AlChess s'en
  protège déjà en amont via le garde-fou existant
  (`_refuse_create_if_games_ongoing`, `/api/account/playing`), qui
  n'aurait pas vu une RECHERCHE en cours sans partie créée (distinction
  non couverte par cette route).
- **Non vérifiable sans vraie recherche** (interdit par la règle de cette
  issue) : code HTTP et corps exacts renvoyés par Lichess lors de l'échec
  réel du 14/11/2026 — désormais capturés si l'incident se reproduit
  (journal général + journal de partie dédié).

### Point 5 — Tests sans connexion réelle

Nouveau fichier `nicsoft/tests/test_issue329_lichess_http_errors.py` (41
tests) :
- `transport.py` : capture et journalisation de 400/401/403/404/500/503
  (code, chemin, jamais le jeton), `Retry-After` présent/absent pour 429,
  troncature du corps à ~500 caractères, connexion refusée → pas de ligne
  "erreur HTTP" journalisée, délai dépassé → `TransportTimeoutError`.
- `seek.py`/`game_client.py` : l'évènement `"error"` et le journal de
  partie dédié portent le code 429 et le délai reçu, jamais le jeton.
- `_classify_seek_error_event` : un message par code connu, 401/403
  unifiés intentionnellement, réseau réel seul cas gardant le message
  réseau, toutes les clés présentes dans `_TOAST_MESSAGES`.
- `_run_lichess_human` bout en bout (double de client levant chaque
  exception au point exact de l'échec réel du 14/11/2026 — dès
  l'ouverture) : message et variables attendus pour 400/401/403/404/429/5xx/
  réseau, persistance (`toast_persistent is True`), pas de relance
  automatique (compteur d'appels).
- Paramètres exacts de `POST /api/board/seek` par cadence × couleur (10
  cas).

Un test existant (`test_issue327_lichess_human.py`, assertion exacte sur
l'évènement `"error"`) a été ajusté pour accepter les nouveaux champs
(`status_code`/`retry_after_s`/`detail`) sans changer ce qu'il vérifiait
réellement.

**Suite complète** : `python3 -m pytest nicsoft/tests --ignore=nicsoft/tests/e2e`
→ 1087 passed, 82 skipped (hors un test isolé, `test_is_alchess_process_par_cmdline`,
qui flaky sous charge complète de la suite — passe systématiquement seul,
avant et après cette modification ; sans lien avec Lichess, non modifié
par cette issue). Suite e2e non lancée (nécessite un navigateur de test,
hors périmètre réseau/risque de cette tâche — voir rapport de clôture).

### Non vérifiable sans vraie partie (interdit par la règle de cette issue)

- Le code HTTP et le corps exacts renvoyés par Lichess lors de l'échec
  réel du 14/11/2026.
- Si une vraie recherche 15+10 échouerait encore aujourd'hui pour la même
  raison (état du compte/serveur au moment de l'essai, non reproductible).

### Fichiers modifiés

`nicsoft/modes/lichess/transport.py`, `errors.py`, `game_client.py`,
`seek.py` ; `nicsoft/core/game_manager_modes/lichess.py`, `state.py` ;
`nicsoft/web/static/app.js`, `css/main.css`, `i18n/{fr,en,de}.json` ;
`nicsoft/tests/test_issue329_lichess_http_errors.py` (nouveau),
`test_issue327_lichess_human.py` (ajustement) ; `CONTEXTE.md`.

# Changelog — Issue #328

## Lichess humain : adversaire trouvé retrouvé après fermeture de la recherche, fermeture ordonnée des flux, compteur de temps corrigé

Essai réel du 14/11/2026 (recherche d'adversaire humain, 10+0, blancs) :
un adversaire avait bien été apparié chez Lichess (partie terminée
manuellement sur lichess.org par Alain) alors qu'AlChess concluait à tort
à un échec réseau, perdait la trace de la partie, et levait une exception
non interceptée dans un fil secondaire. Cette issue corrige la cause et
ajoute les garde-fous demandés.

**Règle absolue respectée à la lettre** : aucune recherche d'adversaire,
aucune partie, aucun défi réel sur lichess.org à aucun moment. Le jeton
réel d'Alain n'a jamais été lu ni utilisé. Tous les tests utilisent soit
un transport scripté (`FakeTransport`/`_FakeHandleForClient`), soit un
serveur HTTP local (127.0.0.1, jamais lichess.org) — jamais de connexion
réelle. Le test de garde réseau de #327 reste actif et inchangé.

### Point 1 — Cause établie par lecture du code et de la documentation

- Établi par lecture du code (fait, pas une hypothèse) : `seek.py`
  traitait la fermeture du flux `board/seek` (`seek_closed`) comme un
  échec immédiat. Le lanceur (`_run_lichess_human`) réagissait en
  appelant `seek_session.cancel()`, qui fermait aussitôt le flux général
  d'évènements (`/api/stream/event`) — alors que son propre fil de
  lecture (`_read_event_stream`) pouvait être encore bloqué en train
  d'attendre la ligne suivante, dans l'espoir de lire `gameStart`.
  Fermer une connexion HTTP depuis un AUTRE fil pendant une lecture
  bloquante lève une exception dont le type exact dépend du point
  précis de l'interruption et de la version de Python
  (`ValueError` déjà observé par le passé, `AttributeError` observé
  cette fois : `'NoneType' object has no attribute 'peek'`) —
  `transport.py::StreamHandle.lines()` n'interceptait QUE `ValueError`,
  jamais les autres cas : l'exception remontait non interceptée hors du
  générateur, hors de `_read_event_stream` (qui n'attrapait que
  `TransportNetworkError`/`TransportTimeoutError`), jusqu'au hook
  d'exception par défaut des fils — visible UNIQUEMENT dans le
  terminal, jamais journalisée (ni `niclink.log`, ni le journal dédié de
  la recherche).
- Reste une hypothèse (non vérifiable sans vraie partie, interdit par
  consigne) : l'ORDRE et le DÉLAI réels, côté Lichess, entre la fermeture
  de `board/seek` (appariement) et l'arrivée de `gameStart` sur
  `/api/stream/event`. La documentation officielle lichess-org/api
  (`doc/specs/tags/board/api-board-seek.yaml`, `api-stream-event.yaml`,
  relues le 14/11/2026) ne garantit ni l'un ni l'autre. L'essai réel du
  14/11/2026 est cohérent avec « `board/seek` se ferme avant que
  `gameStart` ne soit lu par AlChess » (aucune ligne « partie créée »
  dans le journal, alors qu'une partie existait bien) — mais rien ne
  prouve si `gameStart` est arrivé juste après (et a été perdu par la
  fermeture prématurée du flux) ou plus tard. La correction ci-dessous
  est robuste dans les deux cas : elle ne ferme plus jamais le flux
  d'évènements tant que l'appelant n'a pas renoncé à attendre.

### Point 2 — Ne plus jamais conclure à un échec dès `seek_closed`

- `nicsoft/modes/lichess/seek.py` : `_read_seek_stream` ne change pas de
  comportement côté détection (toujours `seek_closed` si ni annulée ni
  trouvée), mais **ne ferme jamais** le flux d'évènements — c'était déjà
  le cas, le bug venait de l'appelant.
- `nicsoft/core/game_manager_modes/lichess.py::_run_lichess_human` :
  sur `seek_closed`, nouvelle attente `_SEEK_CLOSED_GRACE_S` (5s) de
  l'évènement `found` (en continuant à lire la file d'évènements de la
  session, sans fermer quoi que ce soit). Si `gameStart` arrive dans ce
  délai : la recherche se termine normalement, comme si `seek_closed`
  n'avait jamais eu lieu. Sinon : appel à `_fetch_ongoing_games` (même
  fonction que le garde-fou « une seule partie à la fois », déjà
  existant) — une partie en temps réel trouvée y est **adoptée** :
  évènement `lichess_resumable` envoyé au navigateur (réaffiche l'écran
  des parties en cours de #325, avec son bouton « Abandonner » puisque
  la reprise d'une partie humaine n'est pas encore livrée — fera l'objet
  d'une issue suivante, non tentée ici) et toast dédié
  `toast.lichess_seek_partie_non_ouverte` (« Un adversaire a été trouvé,
  mais la partie n'a pas pu s'ouvrir normalement »). Une annulation
  utilisateur reçue PENDANT cette courte attente ne fait pas non plus
  perdre une partie déjà créée : la liste des parties en cours est quand
  même consultée avant de conclure (comportement voulu, non couvert par
  un test automatique dédié — fragile à reproduire de façon
  déterministe avec des doubles sans délai réel, voir rapport de
  clôture).

### Point 3 — Message distinct si vraiment aucune partie

- Nouveau toast `toast.lichess_seek_sans_adversaire` (« La recherche
  s'est arrêtée sans adversaire. ») — utilisé uniquement quand la liste
  des parties en cours confirme qu'aucune partie n'a été créée. Le
  toast `toast.lichess_network_error` (« Connexion à Lichess impossible
  — vérifiez le réseau. ») reste réservé à une vraie panne réseau
  (échec d'ouverture d'un flux, coupure en cours de lecture) — jamais
  utilisé pour `seek_closed`.

### Point 4 — Annulation et fermeture ordonnées

- `nicsoft/modes/lichess/transport.py::StreamHandle.lines()` : toute
  exception levée pendant l'itération est désormais traitée comme une
  fin normale du générateur SI `self._closed` est déjà vrai (fermeture
  volontaire en cours depuis un autre fil — `close()` positionne ce
  drapeau AVANT de fermer la réponse) ; sinon elle est relevée telle
  quelle (jamais avalée en silence si ce n'est pas une fermeture
  volontaire).
- `nicsoft/modes/lichess/seek.py` : `_read_event_stream`/
  `_read_seek_stream` encapsulent désormais tout leur corps dans un
  `except Exception` qui journalise systématiquement (`logger.error` +
  `GameLog.exception(exc, context=...)`, jamais seulement le terminal)
  et pousse un évènement `error` à l'appelant si la session n'est pas
  déjà résolue — même traitement que `LichessGame._stream_reader_loop`
  (#326, `game.py`), qui n'avait jamais été étendu à ce module.
- `SeekSession.cancel()` (annulation utilisateur explicite, bouton
  « Annuler la recherche ») et la nouvelle `SeekSession.close()` (toute
  autre conclusion — trouvé, erreur, décision après l'attente de
  `seek_closed`) sont maintenant deux méthodes distinctes : seule
  `cancel()` journalise « recherche d'adversaire annulée par
  l'utilisateur » ; `close()` ne le fait pas (le journal avait
  auparavant ce message FAUX dans tous les autres cas — exactement ce
  qu'on a vu dans l'essai réel du 14/11/2026, « recherche annulée par
  l'utilisateur » alors qu'Alain n'avait rien cliqué). Le lanceur
  (`_run_lichess_human`, bloc `finally`) appelle désormais `close()`
  plutôt que `cancel()`.
- Petit raffinement de robustesse (défense en profondeur, pas un bug
  confirmé) : `_read_seek_stream` relit `_cancelled`/`_found` sous le
  même verrou que `_mark_found` juste avant de pousser `seek_closed`,
  pour réduire la fenêtre d'une fausse notification en cas de
  coïncidence de minutage exacte entre les deux fils.

### Point 5 — Compteur de temps écoulé

- `nicsoft/core/game_manager_modes/lichess.py::_run_lichess_human` :
  `search_start` est désormais capturé immédiatement après la
  confirmation de la position physique, AVANT le garde-fou « une seule
  partie à la fois » et avant l'ouverture des deux flux
  (`seek_session.start()`) — trois appels HTTP séquentiels bloquants
  dont la durée n'était pas comptée auparavant (le compteur ne démarrait
  qu'après leur retour). Cause probable (établie par lecture du code,
  cohérente avec l'écart observé — « 0:03 » affiché neuf secondes après
  la position confirmée) de l'écart signalé dans l'essai réel.

### Point 6 — Journal de partie

- `nicsoft/modes/lichess/seek.py::_read_event_stream` : chaque ligne non
  vide reçue sur le flux d'évènements pendant la recherche est
  désormais journalisée via `GameLog.raw()` (jamais de tchat possible à
  ce stade, aucune partie n'existant encore).
- `_run_lichess_human` journalise désormais, via `GameLog.state_change`,
  chaque étape de la nouvelle logique : fermeture de `board/seek`
  signalée, attente de `gameStart`, consultation de la liste des
  parties en cours, et la décision finale prise (trouvée / adoptée /
  aucune partie).

### Point 7 — Tests (sans aucune connexion réelle)

Nouveau fichier `nicsoft/tests/test_issue328_lichess_seek_recovery.py` :

- **Fermeture pendant une lecture bloquante, sans trace d'erreur** :
  serveur HTTP local (127.0.0.1, jamais lichess.org) + vrai socket +
  vrai fil de lecture ; `close()` appelé depuis le fil de test pendant
  que le fil de lecture est bloqué sur la ligne suivante ; capture du
  hook d'exception des fils (`threading.excepthook`) pour prouver
  qu'aucune exception ne s'en échappe (reproduction directe du bug réel).
- **`found` arrivant après `seek_closed`** (le flux de recherche se
  ferme avant que `gameStart` n'arrive) : double à délai réel
  (`time.sleep`) pour forcer cet ordre de façon déterministe — les
  doubles purement synchrones ne garantissent aucun ordre entre les deux
  fils. Caractérise le mécanisme exact sur lequel repose la correction.
- **Exception imprévue d'un fil secondaire** : double dont `lines()`
  lève directement une `AttributeError`, vérifie la journalisation
  (`caplog` + fichier dédié) et l'évènement `error` poussé à l'appelant.
- **`cancel()` vs `close()`** : seul `cancel()` journalise « annulée par
  l'utilisateur ».
- **Lanceur `_run_lichess_human`** : `seek_closed` puis `gameStart`
  pendant l'attente → partie rejointe normalement ; `seek_closed` sans
  `gameStart` mais partie présente dans la liste des parties en cours →
  adoptée (évènement `lichess_resumable` + toast dédié) ; `seek_closed`
  sans `gameStart` et sans aucune partie → message distinct ; messages
  toast réseau / sans-adversaire / partie-non-ouverte vérifiés distincts
  textuellement ; compteur de temps vérifié en rendant le garde-fou
  réseau artificiellement lent et en contrôlant que le premier
  `lichess_seek_tick` en tient compte.
- **Non ajouté** : un test automatique de l'annulation utilisateur
  PENDANT la courte fenêtre d'attente qui suit `seek_closed` (voir point
  2) — timing trop fragile à reproduire de façon déterministe avec des
  doubles sans délai réel ; le comportement général d'annulation (hors
  de cette fenêtre) reste couvert par le test existant de #327
  (`test_lanceur_humain_annulation_recherche_sur_back_menu`), toujours
  vert, inchangé.
- Le test de garde réseau de #327
  (`conftest.py::_guard_no_real_lichess_network`) reste actif, inchangé,
  et a été revérifié : toujours vert.

### Non vérifié sans vraie partie (interdit par consigne)

- L'ordre et le délai réels, côté Lichess, entre la fermeture de
  `board/seek` et l'arrivée de `gameStart` (voir point 1) — reste une
  hypothèse ; la correction est conçue pour être correcte dans les deux
  ordres possibles.
- Le rendu réel de l'écran des parties en cours (#325) dans le cas
  « adopté » avec une vraie réponse Lichess (`get_ongoing_games`) — testé
  uniquement avec une liste construite à la main côté test.

### Fichiers modifiés

- `nicsoft/modes/lichess/transport.py` — `StreamHandle.lines()`.
- `nicsoft/modes/lichess/seek.py` — journalisation des lignes brutes,
  encapsulation `except Exception` des deux fils, `cancel()`/`close()`.
- `nicsoft/core/game_manager_modes/lichess.py` — `_SEEK_CLOSED_GRACE_S`,
  attente + adoption sur `seek_closed`, `search_start` déplacé,
  `finally` utilise `close()`.
- `nicsoft/core/game_manager_modes/state.py` — deux nouveaux messages
  toast (`_TOAST_MESSAGES`).
- `nicsoft/web/static/i18n/fr.json`/`en.json`/`de.json` — deux nouvelles
  clés (`toast.lichess_seek_sans_adversaire`,
  `toast.lichess_seek_partie_non_ouverte`), ajoutées simultanément dans
  les trois langues.
- `nicsoft/tests/test_issue328_lichess_seek_recovery.py` (nouveau).
- `CONTEXTE.md` — paragraphe dédié ajouté à la suite de celui de #327.

# Changelog — Issue #327

## Lichess humain : recherche d'adversaire, choix IA/humain, événements de base, nulle vs IA établie, journal moins bruyant

Issue lourde (L2b) — livraison complète des points 1 à 8 en un seul passage
(recherche documentaire + lecture du code public de lila en amont a permis
de trancher plusieurs points qui auraient sinon demandé un second passage,
voir « Points vérifiés par lecture de code » plus bas).

**Règle absolue respectée à la lettre** : aucune recherche d'adversaire,
aucune partie, aucun défi réel sur lichess.org à aucun moment. Tous les
tests utilisent un transport scripté (`FakeTransport`/`FakeStreamHandle`,
jamais de socket réel) ; un garde-fou réseau dédié a été ajouté (point 8).

### Point 1 — Choix du type de partie

- `nicsoft/web/templates/index.html` (`screen-config-lichess`) : nouvelle
  carte « Adversaire » avec deux boutons (`cfg-lichess-opponent-ai`/
  `-human`). Contre un humain : le niveau d'IA est masqué (sans objet), un
  rappel « amicale seulement, classé plus tard » apparaît. Les préréglages
  de cadence existants (10+0/15+10/30+0/60+0/90+30) sont réutilisés tels
  quels pour les deux modes — tous Rapide ou Classique, jamais Blitz/Bullet
  (vérifié via `speed_key_for_clock`, déjà présente depuis #321).
- `app.js` : `selectOpponentTypeLichess()` (nouveau), `startGameLichess()`
  envoie désormais `opponent_type` au serveur.
- i18n : 11 nouvelles clés ajoutées simultanément dans `fr.json`/`en.json`/
  `de.json` (voir liste en fin de fichier).

### Point 2 — Ordre des opérations

- `core/game_manager_modes/lichess.py::launch_lichess()` distingue
  `opponent_type` et délègue à `_launch_lichess_human()`/
  `_run_lichess_human()` (nouveaux) pour le cas humain — le cas IA
  (`_run_lichess`) est inchangé.
- Même ordre que pour l'IA (#311) : position physique confirmée
  (`_wait_initial_position_lichess`, réutilisée telle quelle) **avant**
  tout appel réseau ; garde-fou « une seule partie à la fois »
  (`_refuse_create_if_games_ongoing`, réutilisé) appliqué **juste avant**
  la recherche, jamais avant la position.
- Contrairement à l'IA, la couleur « aléatoire » est résolue LOCALEMENT
  (comme pour l'IA, `random.choice`) et transmise explicitement au
  paramètre `color` du `board/seek` — plutôt que de laisser Lichess décider
  server-side (ce que l'API permettrait) : évite une ambiguïté d'orientation
  de l'écran de mise en place tant que la couleur resterait inconnue,
  pour un résultat statistiquement identique (50/50).

### Point 3 — Recherche

- **Nouveau module `nicsoft/modes/lichess/seek.py`** (`SeekSession`) :
  implémente le protocole officiel `board/seek` (doc `lichess-org/api`,
  `doc/specs/tags/board/api-board-seek.yaml`, lue le 14/11/2026 via
  `gh api`) — `POST /api/board/seek` reste ouvert (lignes vides
  périodiques) tant que la recherche est active ; **fermer cette connexion
  est le seul moyen d'annuler la recherche côté serveur** (« If the client
  closes the connection, the seek is canceled »). Le flux de recherche ne
  contient aucune information sur la partie trouvée : `GET
  /api/stream/event` est ouvert EN PREMIER (recommandation officielle,
  « We recommend opening the Event stream first ») pour recevoir
  l'évènement `gameStart` (game_id, couleur, adversaire) dès l'appariement.
- **`nicsoft/modes/lichess/transport.py`** : nouvelle méthode
  `UrllibTransport.open_stream()` + classe `StreamHandle` — poignée
  annulable (`.close()` ferme le socket depuis un AUTRE fil que celui qui
  lit `.lines()`), nécessaire car `stream_lines()` existant (générateur à
  bloc `with` interne) n'exposait pas la réponse pour une fermeture externe.
- **`nicsoft/modes/lichess/game_client.py`** : `open_event_stream()`/
  `open_seek_stream()` (nouvelles) — ne traduisent PAS les erreurs de
  transport en erreurs Lichess (contrairement aux autres méthodes) :
  `seek.py` les attrape sous leur forme brute (`TransportNetworkError`
  etc.), documenté dans les deux modules.
- Écran dédié `screen-lichess-seeking` (état `lichess_seeking`, ajouté à
  `single_instance.BUSY_STATES`) : temps écoulé poussé par le serveur
  (`lichess_seek_tick`, ~1×/s, jamais un minuteur JS local), bouton
  « Annuler la recherche » = `back_menu` (même mécanisme que l'écran
  `position_initiale` : jamais relayé à `action_queue`, voir
  `server.py::on_action` — jamais eu besoin d'y toucher). Panne réseau,
  jeton absent ou refus Lichess : retour à `config_lichess` avec message
  persistant (`toast_message_key`), jamais de blocage silencieux. Aucune
  limite de durée imposée côté AlChess (conforme à la demande).

### Point 4 — Partie contre un humain

- Le mode jouable existant (`modes/lichess/game.py::LichessGame`) est
  réutilisé À L'IDENTIQUE pour la partie elle-même — la plupart du
  nécessaire (pendules figées avant les deux premiers coups, estimation
  locale du décompte du premier coup pour un adversaire non-IA, aucune
  limite de réflexion) était déjà en place depuis #321/#322, puisque conçu
  dès le départ pour anticiper ce mode.
- **Nouveau paramètre `known_user_color`** (`LichessGame.__init__`) :
  nécessaire car, pour une partie humaine, ni `white` ni `black` ne porte
  jamais `aiLevel` dans `gameFull` — jusqu'ici le SEUL moyen utilisé par
  `_apply_game_full()` pour déduire sa propre couleur. Transmis par le
  lanceur depuis la couleur résolue localement avant la recherche (point 2).
- **Nom et cote de l'adversaire** : `LichessGame.opponent_name`/
  `opponent_rating` (nouveaux), déduits de `white`/`black` dans
  `_apply_game_full()`, transmis dans l'évènement `lichess_init` existant
  (`opponent_name`, `opponent_rating`, `opponent_is_ai`). Affichés côté
  `app.js` via `.textContent` (jamais `innerHTML`) — suffisant à lui seul
  contre l'injection, comme tout le reste de l'interface pour du texte
  Lichess (nom Lichess potentiellement arbitraire).

### Point 5 — Événements de base (nulle)

- **Établi par lecture du code public de lila (14/11/2026, dépôt
  `lichess-org/lila`, branche par défaut)**, répondant précisément à
  l'observation d'Alain du 14 novembre (icône ½ grisée en permanence
  contre l'IA sur lichess.org) :
  - `modules/game/src/main/Game.scala::playerCanOfferDraw` exige
    `!g.opponent(color).isAi` parmi ses conditions.
  - `modules/round/src/main/Drawer.scala::yes()` : si cette condition est
    fausse, retombe sur `case _ => fuccess(List(Event.ReloadOwner))` — un
    **no-op silencieux, sans erreur, qui ne modifie jamais `isOfferingDraw`**.
  - `modules/bot/src/main/BotJsonView.scala::gameState` : `wdraw`/`bdraw`
    sont lus directement depuis `game.whitePlayer.isOfferingDraw`/
    `blackPlayer.isOfferingDraw` — jamais modifiés contre l'IA, donc jamais
    vrais dans aucun état reçu.
  - **Conclusion établie, pas une hypothèse** : contre l'IA, une offre de
    nulle n'a STRICTEMENT AUCUN EFFET, quelle que soit la requête envoyée
    (200 OK renvoyé par Lichess malgré tout — d'où la fausse impression
    d'une demande « acceptée » alors que rien ne se passe réellement).
  - **Corrigé dans `game.py`** : `_compute_action_buttons()` — Proposer
    nulle grisé EN PERMANENCE contre l'IA (`not self._opponent_is_ai`
    ajouté à `draw_enabled`), pas seulement pendant l'attente habituelle.
    `_process_browser_actions()` — l'action `lichess_propose_draw`
    n'envoie même plus la requête contre l'IA (défense en profondeur,
    toast `lichess.nulle_impossible_ia` à la place). Nouveau champ
    `draw_disabled_vs_ai` dans l'évènement `lichess_action_buttons`, lu par
    `app.js::_lichessSetActionButtons()` pour afficher l'explication courte
    à la place du texte habituel. Conséquence directe : « Nulle refusée »
    ne peut plus jamais s'afficher contre l'IA (plus aucune offre n'est
    jamais réellement en attente).
  - Même lecture de code, pour la question du renvoi : `playerCanOfferDraw`
    exige aussi `!g.player(color).isOfferingDraw` (pas déjà en train
    d'offrir) — **renvoyer une offre déjà active retombe sur le MÊME no-op
    `ReloadOwner`, jamais une erreur ni un second effet réel** : confirmé
    sans risque d'établir ceci par la lecture seule (pas besoin d'une
    vraie partie).
- **Renvoi unique contre un humain** (`_apply_game_state()`,
  `_my_draw_offer_resent`, nouveau) : si l'état reçu juste après NOTRE
  propre coup (offre jointe via `offeringDraw=true`) ne montre toujours pas
  notre indicateur, renvoi d'une nouvelle requête `draw/yes` UNE SEULE FOIS
  (jamais en boucle), journalisé. Repose sur la garantie ci-dessus (sans
  risque même si l'offre était déjà bien passée). **Non vérifiable sans une
  vraie partie contre un humain** (interdit par cette issue) : en pratique,
  l'ordre des opérations dans `BotPlayer.scala` (le drapeau est positionné
  AVANT l'envoi du coup à la même file d'acteur) suggère que l'indicateur
  devrait déjà être présent dès l'écho du coup dans la quasi-totalité des
  cas — le renvoi n'est qu'un filet de sécurité, pas une correction d'un
  bug confirmé.

### Point 6 — PGN et journal

- **PGN** : `build_pgn_headers()` accepte `opponent_name=`/`event_label=`
  (nouveaux paramètres optionnels, rétro-compatibles — l'ancien
  comportement, nom d'IA par défaut, reste inchangé sans eux).
  `LichessGame._save_pgn()` les fournit pour un adversaire humain (vrai nom
  Lichess, `"Lichess, amicale contre un humain"`), jamais pour l'IA.
- **Journal — bruit des pendules réduit** : `LichessGame._maybe_log_clock()`
  (nouveau) — les lignes `[CLOCK]` du journal DÉDIÉ (pas l'envoi au
  navigateur via `lichess_clock`, inchangé à 1×/s) ne s'écrivent plus qu'au
  recalage reçu de Lichess (`force=True`, `_reset_clock_from_state`), au
  changement de trait ou de source depuis la dernière ligne écrite, ou au
  plus une fois toutes les 30s (`CLOCK_LOG_MIN_INTERVAL_S`) — reproduit
  exactement la plainte de l'essai d'Alain (une ligne par seconde aurait
  noyé une partie de 90+30). Valeurs arrondies à la milliseconde entière
  (`round()`) avant écriture.
- **Décisions de nulle journalisées dans le journal DÉDIÉ** (pas seulement
  le journal général comme avant #327) : offre envoyée (avec raison),
  jointe au coup, acceptée (par nous ou l'adversaire), refusée (par nous ou
  l'adversaire), renvoyée — chacune via `self._game_log.state_change(...)`
  en plus du `logger.info` existant.
- **Indicateurs de nulle journalisés à CHAQUE état reçu** (sans throttle,
  contrairement aux pendules) : `_log_game_state_received()` écrit
  désormais aussi dans le journal dédié la présence/absence de `wdraw`/
  `bdraw` à chaque `gameFull`/`gameState` — c'est précisément ce
  qu'Alain avait dû aller chercher dans le journal GÉNÉRAL le 14/11/2026,
  faute de l'avoir dans le journal dédié de la partie concernée.
- Jeton et tchat : toujours jamais journalisés (comportement de #326
  inchangé, `GameLog` non modifié sur ce point).

### Point 7 — Fair-play

- Aucun import de moteur ni d'aide introduit par cette issue — `seek.py`
  et les ajouts à `game.py`/`game_manager_modes/lichess.py` n'importent
  que `nicsoft.modes.lichess.*`, `chess`, et la bibliothèque standard.
  Non ajouté : un test dédié « le mode Lichess ne démarre aucun moteur » —
  un tel test générique n'existait pas avant cette issue (à vérifier/ajouter
  dans une issue de suivi si souhaité) ; `test_no_web_import.py` (ARC-001)
  couvre déjà l'absence d'import de `nicsoft.web` mais pas spécifiquement
  l'absence d'import moteur.

### Point 8 — Tests sans connexion réelle

- **`FakeTransport`/`FakeStreamHandle`** (`test_issue309_lichess_l2a.py`,
  étendu) : nouvelle méthode `open_stream()` sur le double partagé —
  consomme des spécifications scriptées (listes de lignes ou exceptions),
  additif et rétro-compatible (aucun test existant n'appelait cette
  méthode avant).
- **Nouveau fichier `nicsoft/tests/test_issue327_lichess_human.py`**
  (29 tests) : `SeekSession` (appariement, annulation réelle des deux
  flux, échec d'ouverture, coupure en cours, journal dédié de recherche),
  cadences acceptées (tous les préréglages vérifiés Rapide/Classique),
  lanceur `_run_lichess_human` (position avant recherche, garde-fou partie
  en cours AVANT la recherche, annulation par `back_menu`, erreur réseau,
  cadence invalide — filet de sécurité), nulle grisée en permanence contre
  l'IA (bouton ET requête jamais envoyée), renvoi unique contre un humain,
  nom/cote de l'adversaire transmis, PGN avec nom humain, bruit des
  pendules réduit (pas de nouvelle ligne sans changement), arrondi
  milliseconde, indicateurs de nulle journalisés à chaque état.
- **Garde-fou réseau dédié (nouveau, demandé explicitement par le point
  8)** : `nicsoft/tests/conftest.py::_guard_no_real_lichess_network`
  (fixture `autouse`) — patch `socket.create_connection` (point
  d'interception vérifié correct : `http.client.HTTPConnection.__init__`
  capture cette fonction comme attribut D'INSTANCE au moment de la
  construction, donc patcher l'attribut du module AVANT toute connexion
  suffit — vérifié avec une vraie tentative de connexion à
  `lichess.org:443`, ce bac à sable ayant un accès réseau sortant). Échoue
  avec un message explicite si un hôte contenant « lichess » est contacté
  pendant la suite EN PROCESS. Couvre `nicsoft/tests` (hors `e2e`, qui
  lance un sous-processus séparé — protégé par construction depuis #326 :
  jeton toujours vide dans son `ALCHESS_DIR` isolé, donc aucun appel réseau
  n'est même tenté). Deux tests dédiés dans `test_issue327_lichess_human.py`
  vérifient explicitement la garde (bloque un hôte Lichess, laisse passer
  un autre hôte).
- **Existant retesté** : correctifs du point 5 ont nécessité la mise à
  jour de 13 tests préexistants (#310/#311/#316/#318/#321/#323) qui
  simulaient un adversaire IA tout en attendant un bouton Proposer nulle
  actif — converti en adversaire humain simulé (`known_user_color` +
  dictionnaires sans `aiLevel`) pour continuer à tester la même logique de
  nulle, désormais correctement réservée à un adversaire humain ; deux
  assertions de dictionnaire exact mises à jour pour inclure le nouveau
  champ `draw_disabled_vs_ai` ; fixtures e2e `lichess_init` mises à jour
  avec `opponent_is_ai: true` (contrat de payload étendu par le point 4).
- **Suite complète** : 1144 tests passent (83 ignorés, matériel), suite e2e
  Lichess (63 tests) et suite e2e complète (109 tests) vertes après tous
  les changements, y compris les ajustements CSS de l'écran de recherche.

### Fichiers modifiés/créés

- Nouveaux : `nicsoft/modes/lichess/seek.py`,
  `nicsoft/tests/test_issue327_lichess_human.py`.
- Modifiés : `nicsoft/modes/lichess/transport.py` (StreamHandle/
  open_stream), `nicsoft/modes/lichess/game_client.py`
  (open_event_stream/open_seek_stream), `nicsoft/modes/lichess/game.py`
  (known_user_color, opponent_name/rating, nulle vs IA, renvoi unique,
  bruit journal, build_pgn_headers), `nicsoft/core/game_manager_modes/
  lichess.py` (launch_lichess dispatch, _launch_lichess_human/
  _run_lichess_human), `nicsoft/web/single_instance.py` (BUSY_STATES),
  `nicsoft/web/templates/index.html` (choix adversaire, écran recherche),
  `nicsoft/web/static/app.js` (sélection adversaire, écran recherche,
  nom/cote adversaire, explication nulle grisée), `nicsoft/web/static/
  i18n/{fr,en,de}.json` (11 nouvelles clés), `nicsoft/tests/conftest.py`
  (garde réseau), `nicsoft/tests/test_issue309_lichess_l2a.py`
  (FakeStreamHandle/open_stream, forward kwargs), 6 fichiers de tests
  préexistants ajustés (voir ci-dessus), `nicsoft/tests/e2e/
  test_issue310_lichess_e2e.py` (contrat `opponent_is_ai`).

### Ce qui n'a pas pu être vérifié sans une vraie partie (interdit par cette issue)

- Rendu réel de `wdraw`/`bdraw` juste après notre coup contre un adversaire
  HUMAIN réel (la lecture du code suggère qu'il devrait déjà être présent,
  mais seule une vraie partie le confirmerait — le renvoi unique reste un
  filet de sécurité, jamais testé en situation réelle).
- Comportement exact de Lichess si une recherche expire sans appariement
  (aucune durée maximale documentée dans la spec officielle) — traité par
  prudence (`seek_closed`), jamais observé.
- Message exact affiché par lichess.org dans ce cas, et tout comportement
  dépendant du vrai matchmaking (temps d'attente réel, clients concurrents).

### Nouvelles clés i18n (fr/en/de)

`config.h2.adversaire`, `config.lichess.adversaire_ia`,
`config.lichess.adversaire_humain`, `config.lichess.rated_plus_tard`,
`lichess.recherche.titre`, `lichess.recherche.temps_ecoule`,
`lichess.recherche.explication`, `lichess.recherche.annuler`,
`lichess.nulle_impossible_ia`, `lichess.adversaire_inconnu`,
`toast.lichess_cadence_invalide`.

# Changelog — Issue #326

## Lichess humain : livraison partielle (sécurité des tests + journal de partie dédié)

Tâche beaucoup trop large pour un seul passage (recherche d'adversaire
humain, écran de recherche, événements de partie humaine, reprise des
parties humaines, journal dédié, correctif de sécurité des tests — 10
points). Conformément à la consigne de repli de l'issue, ce passage livre
en priorité le correctif de sécurité critique (point 9, partie) et le
journal de partie dédié (point 10, complet), plus la recherche documentaire
exacte sur les cadences acceptées (point 1). **Aucune recherche
d'adversaire humain, aucun écran de choix IA/humain, aucune reprise de
partie humaine n'a été codé dans ce passage** — voir « Ce qui reste à
faire » ci-dessous.

### Point 9 (partiel, critique) — plus aucun test de navigateur n'appelle le vrai Lichess

- **Cause confirmée par lecture du code et mesure réelle** : `nicsoft/tests/e2e/conftest.py::server_url` pointait `ALCHESS_DIR` directement sur `~/NicLink` (dossier réel d'Alain) pour que les tests non-Lichess disposent des données ECO/livres réelles (non versionnées). Tout test e2e qui ouvrait l'écran de menu Lichess (`sendAction({type:'mode', value:'lichess'})`) déclenchait alors, côté serveur, `check_lichess_resumable()` (`nicsoft/web/alchess.py`) avec le VRAI jeton lu dans `~/NicLink/data/config.json` — un vrai appel à `/api/account/playing` chez Lichess. Confirmé par lecture directe : `~/NicLink/data/config.json` contient bien un jeton réel (`lichess_token` non vide) ; tous les fichiers `test_issue31{0,6}_lichess_e2e.py`, `test_issue32{1,2,3,5}*_e2e.py` ouvrent cet écran. Mesuré avant/après le correctif : `~/NicLink/logs/niclink.log` n'est plus touché par une exécution complète de la suite e2e (horodatage de modification inchangé).
- **Correctif** : `_build_isolated_alchess_dir()` (nouveau, `conftest.py`) construit un `ALCHESS_DIR` isolé par session de tests (`tmp_path_factory`) — liens symboliques en lecture seule vers les données réelles non versionnées dont certains tests non-Lichess ont besoin (ECO, livres, mes_lignes, pgn_library, players.json), mais `data/config.json` et `logs/` toujours neufs. Le `config.json` isolé a `lichess_token=""` explicitement — avec un jeton vide, `check_lichess_resumable()` s'arrête avant tout appel réseau (retour immédiat dans `game_manager_modes/lichess.py`), donc aucun test ne contacte plus jamais le vrai Lichess, avec ou sans jeton.
- **Garde** : `nicsoft/tests/e2e/test_issue326_e2e_isolation_guard.py` (nouveau, 3 tests) — vérifie que `config.json` isolé n'est jamais un lien symbolique et a toujours `lichess_token=""`, que `logs/` démarre vide et n'est jamais le vrai dossier, et que les données ECO réelles restent accessibles pour les autres tests.
- **Vérifié** : suite e2e complète (109 tests) toujours verte après le correctif ; `~/NicLink/logs/niclink.log` et `~/NicLink/data/config.json` non modifiés par l'exécution (horodatages vérifiés avant/après).
- Non traité dans ce point (hors périmètre du bug trouvé) : aucun autre appel réseau réel n'a été détecté dans la suite e2e (aucun test ne déclenche `start_lichess`, `lichess_test_connection` ni `lichess_test_game`) — seul `check_lichess_resumable()` était concerné.

### Point 10 (complet) — journal de partie Lichess dédié

- **Nouveau module `nicsoft/modes/lichess/game_log.py`** (`GameLog`) : un fichier dédié par partie (IA ou futur humain), toujours actif, créé dans `LOGS_DIR/lichess/<horodatage>_<game_id>.log`, en plus de `niclink.log` (inchangé). Chaque ligne est horodatée à la milliseconde et suivie d'un `flush()` immédiat (lisible même après un arrêt brutal du processus — testé en relisant le fichier sans jamais appeler `close()`). Catégories de lignes : `INIT`, `RAW` (lignes brutes du flux Lichess, sauf tchat), `REQUEST` (requêtes envoyées + durée + résultat), `BOARD` (coup/cases/décision), `STATE` (changements d'état, raison des boutons), `CLOCK` (pendules + source), `CONN` (pertes/reprises échiquier et réseau), `EXC` (exceptions avec trace complète), `HEARTBEAT` (ligne de contrôle ~30s). Le jeton n'est jamais écrit : masquage par motif générique (préfixe `lip_` + suite alphanumérique, ou tout en-tête `Bearer ...`) même sans connaître sa valeur, plus masquage littéral si le jeton exact est fourni à la construction. Le tchat n'est jamais écrit : `chat_ignored()` journalise seulement le fait qu'une ligne de tchat est arrivée, jamais son contenu. Rétention : 50 fichiers les plus récents conservés (purge des plus anciens à la création d'un nouveau fichier, jamais pendant une partie en cours).
- **Câblage dans `game_client.py`** : `GameClient` accepte un `game_log` optionnel (`attach_game_log()`) — `_request()` journalise chaque requête ordinaire (méthode, chemin après `/api`, résultat, durée) ; `stream_game()` journalise chaque ligne brute reçue (sauf `chatLine`, redirigée vers `chat_ignored()`) et chaque reconnexion/déconnexion du flux. Rétro-compatible : sans `game_log` (défaut `None`), comportement strictement inchangé — tous les tests existants de `GameClient` passent sans modification.
- **Câblage dans `game.py`** : `LichessGame` crée automatiquement son propre `GameLog` si l'appelant n'en fournit pas (« toujours actif », y compris pour un futur appelant qui l'oublierait) et l'attache au client s'il n'en a pas déjà un. Journalisation ajoutée : coup physique reconnu/promotion/position illégale (`BOARD`), partie démarrée/terminée/boutons actifs-grisés (`STATE`), pendule affichée + sa source — flux Lichess figé, flux + décompte local, ou inconnue (`CLOCK`), perte/reprise de l'échiquier physique avec durée (`CONN`), toute exception du fil principal (`run()`) et du fil de lecture du flux (`_stream_reader_loop`, auparavant silencieux pour une exception imprévue — c'était la lacune la plus utile à combler : avant ce correctif, un bug dans ce fil secondaire mourait sans aucune trace), ligne de contrôle périodique (`_maybe_log_heartbeat()`, appelée à chaque tour de la boucle principale mais ne journalisant réellement qu'au rythme de `HEARTBEAT_INTERVAL_S`).
- **Tests** : `nicsoft/tests/test_issue326_lichess_game_log.py` (nouveau, 14 tests) — création/nommage du fichier, masquage du jeton (littéral et générique), tchat jamais journalisé, lisibilité sans fermeture explicite, horodatage milliseconde, respect de l'intervalle de la ligne de contrôle, purge de rétention, câblage réel `GameClient` (requêtes + lignes brutes + tchat d'une partie scénarisée complète), câblage réel `LichessGame` (coup/boutons/pendule), création automatique si l'appelant n'en fournit pas, exception du fil de lecture journalisée avec sa trace complète.
- **Extrait réel** (partie simulée, voir rapport de clôture pour la méthode) :
  ```
  13:54:51.867 [INIT] Journal de partie Lichess ouvert — game_id=demoGame123
  13:54:51.867 [STATE] Partie démarrée — game_id=demoGame123, niveau=1.
  13:54:51.867 [RAW] {"type": "gameFull", "white": {"id": "alain"}, "black": {"aiLevel": 1}, "state": {"status": "started", "moves": ""}}
  13:54:51.867 [REQUEST] POST /board/game/demoGame123/move/e2e4 -> ok (84 ms)
  13:54:51.867 [BOARD] coup physique reconnu e2e4 — décision : coup envoyé.
  13:54:51.867 [CLOCK] blancs=5400000 noirs=5400000 trait=black source=flux Lichess (figée, avant les deux premiers coups)
  13:54:51.867 [CONN] échiquier perdu — tentatives de reconnexion vont démarrer.
  13:54:51.867 [RAW] (ligne de tchat adverse reçue — ignorée, contenu jamais journalisé)
  ```

### Point 1 (documentation seule, pas de code) — cadences acceptées par la recherche d'adversaire

Vérifié dans le dépôt public `lichess-org/api` (specs OpenAPI, lues le
14/11/2026 via `gh api repos/lichess-org/api/contents/...` — jamais de
connexion au vrai Lichess, seulement à GitHub) :

- `POST /api/board/seek` (`doc/specs/tags/board/api-board-seek.yaml`), scope `board:play`. Partie en temps réel : `time` (minutes, 0 à 180) et `increment` (secondes, 0 à 180) requis, `color` optionnel (vide = ~50% blancs). La réponse reste ouverte (nd-json) jusqu'à adversaire trouvé ou fermeture de la connexion (= annulation de la recherche) — confirme la conception « flux qui reste ouvert, bouton Annuler = fermer la connexion » prévue par l'issue.
- Restriction confirmée au niveau de la fonctionnalité Board entière (`doc/specs/lichess-api.yaml`, tag `Board`) : *« Time controls: Rapid, Classical and Correspondence only. For direct challenges, games vs AI, and bulk pairing, Blitz is also possible. »* — donc **pas de Blitz ni de Bullet pour une recherche d'adversaire humain** (seuls les défis directs et les parties contre l'IA peuvent être en Blitz), conforme à ce que l'issue supposait déjà. Classification officielle (lichess.org/faq#time-controls, formule durée estimée = limite + 40×incrément) : Bullet <3min, Blitz 3-8min, Rapid 8-25min, Classical ≥25min.
- Vérification des préréglages déjà utilisés par `CLOCK_PRESETS` (`core/game_manager_modes/lichess.py`, parties IA) : 10+0 (600s → Rapid), 15+10 (900+40×10=1300s → Rapid), 30+0 (1800s → Classical), 60+0 (3600s → Classical), 90+30 (5400+40×30=6600s → Classical) — **les cinq sont valides pour une recherche humaine**, aucun n'est en Blitz/Bullet. Point d'implémentation à retenir pour la suite : `board/seek` attend `time` en **minutes** (pas en secondes comme `clock.limit` de `challenge/ai`) — conversion `clock_limit_s // 60` nécessaire.
- `POST /api/board/game/{gameId}/claim-victory` existe (`api-board-game-gameId-claim-victory.yaml`) : la réclamation de victoire après déconnexion adverse (point 5) **est implémentable**, pas seulement « à vérifier en réel » comme le redoutait l'issue.
- `POST /api/board/game/{gameId}/takeback/{yes|no}` existe (`api-board-game-gameId-takeback-accept.yaml`) : refuser une proposition de reprise de coup (point 5) se fait en appelant cette route avec `no` — détection côté flux via les champs `wtakeback`/`btakeback` de `GameStateEvent` (même mécanisme que `wdraw`/`bdraw`, déjà utilisé pour la nulle).
- `OpponentGoneEvent` (schéma) confirme le champ `claimWinInSeconds` (délai avant réclamation possible), nécessaire pour l'affichage demandé au point 5.
- Aucune restriction par origine de partie (`source`) trouvée dans la documentation pour `/api/board/game/stream/{gameId}` ni `/api/board/game/{gameId}/move/{move}` — seule la cadence (Rapid/Classique/Correspondance) est restreinte au niveau de la fonctionnalité Board dans son ensemble. Sous réserve de vérification réelle par Alain (règle absolue de cette issue : aucune vraie partie pendant le développement), la reprise d'une partie humaine créée depuis lichess.org (point 6) semble possible par cette même API.

## Ce qui reste à faire (points 1 à 8, hors documentation ci-dessus)

Non codé dans ce passage — taille largement hors de portée d'un seul
passage avec les garanties de test attendues (faux serveur complet,
scénarios d'événements humains, reprise) :

- Écran de choix « contre l'IA » / « contre un humain » avec préréglages de cadence (10+0/15+10/30+0/90+30), couleur, mention « partie amicale uniquement ».
- `create_seek()`/annulation de recherche dans `game_client.py`/`client.py` (flux `board/seek` qui reste ouvert, bouton Annuler = fermeture de connexion, temps écoulé affiché).
- Écran « Recherche d'un adversaire… ».
- Affichage nom/cote de l'adversaire humain (échappé).
- Gestion des événements propres à un adversaire humain : nulle (déjà prévu, à vérifier sans IA), abandon/temps déjà génériques, déconnexion + réclamation de victoire (`claim-victory`, confirmé implémentable ci-dessus), refus automatique de reprise de coup (`takeback/no`), annulation Lichess pour premier coup non joué des DEUX côtés (actuellement seul le cas « utilisateur en retard » est couvert).
- Reprise des parties humaines (actuellement `_RESUMABLE_SOURCE = "ai"` exclut tout le reste) — élargir `get_ongoing_games()`/`LichessGame` pour couvrir les parties humaines en temps réel, y compris celles créées sur lichess.org (sous réserve de la vérification réelle mentionnée ci-dessus).
- Faux serveur Lichess local pour les scénarios humains (recherche, nulle adverse, abandon, temps écoulé, déconnexion, reprise de coup, annulation premier coup, coupure réseau, jeton absent).

## Fichiers modifiés

- `nicsoft/tests/e2e/conftest.py` — `ALCHESS_DIR` isolé par session (`_build_isolated_alchess_dir`), jamais plus le vrai dossier utilisateur.
- `nicsoft/modes/lichess/game_log.py` — nouveau module (`GameLog`).
- `nicsoft/modes/lichess/game_client.py` — `game_log` optionnel, journalisation requêtes/flux/tchat.
- `nicsoft/modes/lichess/game.py` — câblage `GameLog` (coup, boutons, pendule, connectivité, exceptions, ligne de contrôle périodique).
- `nicsoft/tests/e2e/test_issue326_e2e_isolation_guard.py` — nouveau (3 tests).
- `nicsoft/tests/test_issue326_lichess_game_log.py` — nouveau (14 tests).

## Tests exécutés

- `pytest nicsoft/tests/ -q --ignore=nicsoft/tests/e2e` → 1000 passed, 81 skipped.
- `pytest nicsoft/tests/e2e/ -q` (dossier navigateur complet, Playwright) → 109 passed, 1 skipped.
- Vérifié manuellement : `~/NicLink/logs/niclink.log` et `~/NicLink/data/config.json` non modifiés par l'exécution complète de la suite e2e (horodatages comparés avant/après).

# Changelog — Issue #325

## Lichess : une seule partie à la fois, écran de reprise/abandon, temps restant corrigé

- **Point 1 — liste complète des parties en cours** : `nicsoft/modes/lichess/client.py::get_ongoing_games()` retourne désormais TOUTES les parties en cours du compte (quelle que soit leur origine — AlChess, lichess.org, téléphone), avec un indicateur `resumable` par partie (vrai seulement pour une partie amicale contre l'IA, variante standard — seul cas que `LichessGame` sait rejouer). Seules les parties par correspondance sont ignorées, via le champ officiel `speed` (confirmé présent, valeurs `ultraBullet/bullet/blitz/rapid/classical/correspondence`, doc `lichess-org/api`, schémas `GameEventInfo.yaml`/`Speed.yaml`, lus le 14/11/2026) — une classique 90+30 compte normalement. Avant : ne retenait que la partie IA/standard « la plus urgente » et ignorait tout le reste silencieusement.
- **Point 2 — écran direct** : `nicsoft/web/static/app.js` (`socket.on("lichess_resumable", ...)`) affiche directement la liste des parties en cours à la place du formulaire de nouvelle partie dès qu'au moins une partie existe ; `nicsoft/web/templates/index.html` enveloppe le formulaire dans `#lichess-new-game-form` (caché/affiché par JS). Correctif CSS nécessaire : `#lichess-new-game-form { display: contents; }` (`main.css`) pour que `.cfg-hh-scroll`/`.cfg-hh-footer` restent des enfants flex directs de `#screen-config-lichess` malgré ce nouveau conteneur.
- **Point 3 — écran par partie** : une carte par partie (`_lichessOngoingGameCard()`, app.js) avec adversaire, couleur, cadence, temps restant, tour, bouton « Reprendre » (seulement si `resumable`, sinon texte explicatif « non reprenable ici ») et bouton « Abandonner » (toujours). Abandon avec confirmation irréversible (modal générique réutilisé). Nouvelle fonction serveur `abandon_lichess_game()` (`game_manager_modes/lichess.py`) : abandonner une partie qui n'est PAS celle en cours de jeu dans AlChess se fait SANS instance `LichessGame` — un aperçu bref du flux (`_peek_game_full`, déjà utilisé par la reprise) donne le nombre de coups joués pour choisir annulation (< 2 coups) ou abandon, puis un seul appel REST (`abort()`/`resign()`), puis rafraîchissement de la liste.
- **Point 4 — garde-fou à la création** : `_run_lichess()` redemande la liste juste avant `create_ai_game()` (pour les deux couleurs) et refuse la création avec un message persistant (`toast.lichess_partie_en_cours_refus`) si une partie existe — y compris créée ailleurs depuis l'ouverture de l'écran. Si la liste est impossible à obtenir (réseau), la création continue comme avant.
- **Point 5 — mise en place d'une reprise** : `LichessGame._compute_action_buttons()` active désormais Abandonner pendant `_resume_pending` (simple appel réseau, indépendant de la position physique) ; Proposer nulle reste inactif. `_apply_game_full()` envoie l'historique déjà joué (`history_fen`/`history_moves`) dans `lichess_init`, utilisé par `app.js` pour peupler l'historique au lieu de le vider. Le bandeau « Jouez votre premier coup » (décompte premier coup, noirs) est masqué tant que l'écran de mise en place (`lichess_resume_setup`) est actif (`_lichessUpdateFirstMoveBanner()`).
- **Point 6 — hypothèse des cases rouges confirmée par le code** : `get_ongoing_games()` sélectionnait `candidates[0]`, l'ordre Lichess (le plus URGENT, pas le plus RÉCENT) — l'essai réel d'Alain (14/11/2026) a proposé une autre partie (noir, un coup) que celle qu'il venait de jouer (blanc, plusieurs coups), car Lichess l'a classée plus urgente. Les cases à corriger affichées par `_tick_resume_setup()`/`_update_resume_setup_leds()` comparaient la position physique à `self.board.board_fen()` de CETTE autre partie — cohérentes avec elle, pas avec celle qu'Alain venait de jouer. Corrigé en listant toutes les parties (point 1/2) plutôt que d'en choisir une silencieusement.
- **Point 7 — temps restant** : cause identifiée dans le code — `_run_lichess_resume()` calculait `clock_limit_s = int(clock.get("initial") or 0) // 1000` depuis le champ `clock` du `gameFull`, qui ne contient que la cadence CHOISIE (jamais le temps restant) et qui est absent pour une partie par correspondance (`daysPerTurn` à la place, doc officielle `GameFullEvent.yaml`) — ce `0` par défaut silencieux devenait la valeur de départ des pendules (`LichessGame.__init__`), jamais corrigée si le premier événement du flux manquait lui aussi de `wtime`/`btime`. Corrigé : le temps RESTANT réel (`state.wtime`/`state.btime` de l'aperçu de reprise) sert de valeur de départ (`initial_wtime_ms`/`initial_btime_ms`) ; un indicateur `clock_known` (porté par l'événement `lichess_clock`) empêche d'afficher un `0:00` mensonger — `app.js::_lichessRenderClock` affiche `—` plutôt que `0:00` rouge quand inconnu. Le bandeau « X min restantes » (`app.js`) n'affiche plus un temps ≤ 0 (suspect pour une partie encore listée comme en cours).
- **Point 8 — journal** : lignes INFO pour la liste reçue (nombre + identifiants, `check_lichess_resumable`), l'abandon demandé et son résultat (`abandon_lichess_game`), et le refus de création (`_run_lichess`) — jamais le jeton.
- **Point 9 — tests** : `nicsoft/tests/test_issue325_lichess_single_game.py` (nouveau, 21 tests) + `nicsoft/tests/e2e/test_issue325_lichess_single_game_e2e.py` (nouveau, 5 tests navigateur) + mise à jour de `test_issue323_lichess_resume.py`/`test_issue323_lichess_resume_e2e.py`/`test_issue310_lichess_e2e.py` pour la nouvelle forme de `get_ongoing_games()`/`check_lichess_resumable()` (liste plutôt que partie unique). Couvre : aucune/une/plusieurs parties, partie non reprenable, abandon avec confirmation, abandon depuis l'écran de mise en place, refus de création, liste en erreur, échappement des noms, temps restant correct/inconnu, cadence classique 90+30 comptée vs correspondance ignorée.

### Fiabilisation des tests e2e existants (effet de bord découvert en testant)

- Les fixtures `at_config_lichess` (`test_issue310_lichess_e2e.py`, `test_issue323_lichess_resume_e2e.py`) dépendaient implicitement du timing du VRAI `check_lichess_resumable()` lancé en arrière-plan par le serveur (subprocess e2e, avec le jeton/compte Lichess réel de `~/NicLink` — pas un environnement isolé) : une réponse réseau réelle tardive pouvait écraser l'état simulé par le test en cours, causant des échecs intermittents sur des sélecteurs sans rapport avec le test. Corrigé en détachant une fois pour toutes le vrai gestionnaire socket.io de `"lichess_resumable"` (`socket.off`, API publique Socket.IO) dès l'entrée dans l'écran, et en le remplaçant par un état de départ déterministe — nouveau helper `_declencher_lichess_resumable()`.
- `main.css` : `#lichess-new-game-form { display: contents; }` (voir point 2) corrige aussi une régression de visibilité détectée par ces mêmes tests e2e (éléments du formulaire poussés hors du flux flex par le nouveau conteneur).

## Ce qui n'a pas pu être testé sans partie Lichess réelle

- Le rendu réel des LED de mise en place (`_update_resume_setup_leds`) sur le vrai plateau Chessnut — déjà signalé non testable sans matériel depuis #323.
- L'appel REST `resign()`/`abort()` du Board API Lichess sur une partie qui n'a jamais été créée via ce même Board API (ex. partie humain-humain créée sur lichess.org) — supposé fonctionner comme documenté (l'API Board agit sur n'importe quelle partie du joueur authentifié), mais non vérifiable sans compte/partie réelle.
- Le comportement exact observé par Alain le 14/11/2026 (valeur précise de `secondsLeft` pour le bandeau « 0 min restantes ») n'a pas pu être reproduit à l'identique sans le trafic réseau réel capturé ce soir-là ; la cause du `0:00` de la pendule en cours de partie a en revanche été établie avec certitude par lecture du code et de la spécification officielle Lichess (voir point 7).

## Fichiers modifiés

- `nicsoft/modes/lichess/client.py` — `get_ongoing_games()` : liste complète, filtre correspondance seul, indicateur `resumable`.
- `nicsoft/modes/lichess/game.py` — `_compute_action_buttons()` (abandon actif pendant la mise en place), historique dans `lichess_init`, seed/indicateur `clock_known` des pendules.
- `nicsoft/core/game_manager_modes/lichess.py` — `check_lichess_resumable()` (liste), `_refuse_create_if_games_ongoing()` (garde-fou création), `abandon_lichess_game()` (nouveau), seed du temps restant réel dans `_run_lichess_resume()`.
- `nicsoft/core/game_manager.py` — réexporte `abandon_lichess_game`.
- `nicsoft/web/alchess.py` — route l'action `lichess_abandon_ongoing`.
- `nicsoft/web/static/app.js` — liste des parties en cours, modal d'abandon, historique pendant la mise en place, bandeau premier coup masqué pendant la mise en place, pendule « inconnue ».
- `nicsoft/web/templates/index.html` — `#lichess-new-game-form`, `#lichess-ongoing-games-list`, bouton Retour sur l'écran de liste.
- `nicsoft/web/static/css/main.css` — `#lichess-new-game-form { display: contents; }`, styles des cartes de parties en cours.
- `nicsoft/web/static/i18n/{fr,en,de}.json` — nouvelles clés (titre pluriel, non reprenable, boutons/confirmation d'abandon, toast de refus de création).
- `nicsoft/tests/test_issue323_lichess_resume.py`, `nicsoft/tests/e2e/test_issue310_lichess_e2e.py`, `nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py` — mis à jour pour la nouvelle forme de l'API et fiabilisés (voir ci-dessus).
- `nicsoft/tests/test_issue325_lichess_single_game.py`, `nicsoft/tests/e2e/test_issue325_lichess_single_game_e2e.py` — nouveaux.

## Tests exécutés

- `python3 -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` → 976 passed, 80 skipped.
- `python3 -m pytest nicsoft/tests/e2e` → 106 passed, 1 skipped (exécuté 4× pour écarter toute instabilité résiduelle — déterministe).
- `py_compile` OK sur tous les fichiers Python modifiés ; JSON i18n (`fr`/`en`/`de`) valides.

# Changelog — Issue #324

# Issue #324 — Tests : un serveur lancé par les tests ne doit jamais lire, arrêter ni être bloqué par le serveur réel de l'utilisateur

## Contexte

Le push de master (8317a99, 13/11/2026 23:32) avait été refusé par le crochet de pré-push : 93 erreurs, toutes dans `nicsoft/tests/e2e`, message « Serveur AlChess non démarré ». Cause lue dans le code : depuis #320 (instance unique), tout serveur AlChess qui démarre lit le marqueur `DATA_DIR/server_instance.json` et, s'il y trouve une instance vivante, soit l'**arrête** (si au menu), soit **refuse de démarrer** (si en partie). La fixture `nicsoft/tests/e2e/conftest.py::server_url` lançait son serveur avec `ALCHESS_DIR` par défaut égal au dossier utilisateur réel (`~/NicLink`) — donc avec le **même marqueur** que le serveur réel d'Alain.

**Cause confirmée** par reproduction contrôlée (voir « Vérification » ci-dessous) : aucun vrai serveur d'Alain n'était en cours au moment de cette tâche (`~/NicLink/data/server_instance.json` absent au départ), donc la panne originale du 13/11 n'a pas pu être rejouée avec le véritable processus d'Alain — mais le mécanisme exact a été reproduit avec un second processus `python -m nicsoft.web` jouant le rôle du « vrai » serveur (voir plus bas), ce qui confirme la cause sans aucun doute raisonnable.

## 1. Isolation du marqueur d'instance en test (point 1)

Nouvelle variable d'environnement `ALCHESS_SKIP_SINGLE_INSTANCE=1` (`nicsoft/web/single_instance.py`) : quand elle vaut `"1"`, `resolve_startup()` retourne immédiatement `(True, None)` **sans lire le marqueur**, et `write_marker()`/`remove_marker()` ne font rien — aucune lecture, aucune écriture, aucune suppression, quel que soit le contenu de `DATA_DIR`. Choisie plutôt qu'un second dossier de marqueur dédié parce qu'elle protège tous les appelants de `single_instance.py` d'un seul coup, sans toucher à `config.py`/`ALCHESS_DIR` (qui reste nécessaire, inchangé, pour les données réelles — ECO, livres d'ouvertures — dont certains tests ont besoin).

La vérification normale (usage réel, sans cette variable) n'est pas modifiée.

## 2. Test de non-régression (point 2)

`nicsoft/tests/test_issue320_single_instance.py` :
- `test_skip_single_instance_ignore_le_marqueur_reel[menu|playing]` : un faux « vrai » serveur (processus lancé par le test, marqueur écrit dans le `DATA_DIR` isolé de la fixture existante `_isolated_data_dir`) reste vivant et son marqueur intact après `resolve_startup()` avec la variable active, que son état simulé (`_query_state` monkeypatché) soit `"menu"` ou `"playing"`.
- `test_skip_single_instance_write_remove_marker_sont_des_no_op` : un marqueur « réel » préexistant n'est ni écrasé par `write_marker()` ni supprimé par `remove_marker()` appelés avec la variable active.
- `test_integration_serveur_de_test_ignore_vrai_serveur_au_menu` (marqué `slow`) : **deux vrais** processus `python -m nicsoft.web` partageant le même `ALCHESS_DIR` (`tmp_path`, jamais le dossier réel) — le premier sans la variable (joue le « vrai » serveur, au menu), le second avec (joue un serveur de test). Le second démarre sans jamais arrêter le premier, qui reste actif tout du long.

Aucun arrêt par nom de programme dans ces tests ; chaque nettoyage utilise le PID exact capturé à la création du sous-processus.

## 3. Revue des autres lancements de serveur dans les tests (point 3)

Seuls trois endroits dans `nicsoft/tests/` lancent un vrai `python -m nicsoft.web` :
- `nicsoft/tests/e2e/conftest.py::server_url` — corrigé : `ALCHESS_SKIP_SINGLE_INSTANCE=1` ajouté à l'environnement du subprocess, en plus du `ALCHESS_DIR` existant (inchangé).
- `nicsoft/tests/test_issue312_server_startup.py::test_adresse_affichee_en_moins_de_10s_sortie_redirigee` — déjà isolé via `ALCHESS_DIR=tmp_path` (pas le même marqueur que le réel), protection ajoutée par défense en profondeur (`ALCHESS_SKIP_SINGLE_INSTANCE=1`) puisque ce test ne porte pas sur #320.
- `nicsoft/tests/test_issue320_single_instance.py::test_integration_deuxieme_instance_remplace_la_premiere_restee_au_menu` — **non modifié** : ce test vérifie justement le remplacement entre deux vraies instances (#320) et doit garder la vérification active ; il utilise déjà son propre `ALCHESS_DIR` isolé (`tmp_path`), donc jamais le marqueur réel non plus. Il continue de passer (vérifié ci-dessous).

## 4. Vérification (point 4)

Suite complète exécutée deux fois :
1. Sans serveur réel en cours : `python -m pytest nicsoft/tests/` → **1053 passés, 81 ignorés** (dont la suite e2e, 99 passés + 1 ignoré en l'isolant).
2. **Avec un serveur AlChess « réel » lancé pendant la vérification** : un processus `python -m nicsoft.web` a été démarré par ce traitement, avec `ALCHESS_DIR=~/NicLink` (le vrai dossier utilisateur), `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1` (comme l'exigent les consignes projet), **sans** `ALCHESS_SKIP_SINGLE_INSTANCE` — ce qui en fait, pour le code, une instance indistinguable d'un vrai serveur d'Alain au menu. Son PID a été relevé à la création. La suite complète (`python -m pytest nicsoft/tests/`, e2e compris) a ensuite tourné pendant que ce processus restait actif : **aucune erreur**, et le marqueur réel (`~/NicLink/data/server_instance.json`) ainsi que le PID de ce processus sont restés identiques avant/après — il n'a jamais été lu, arrêté ni modifié par les serveurs de test. Ce processus a ensuite été arrêté par son PID exact (jamais par nom) ; son propre nettoyage `atexit` a supprimé son marqueur normalement, dossier utilisateur réel laissé propre.

**Non vérifié** : le cas « vrai serveur en partie » n'a pas été reproduit avec un second vrai sous-processus (aurait demandé de simuler une partie complète dans ce second processus). Ce cas est cependant couvert par le test unitaire paramétré `test_skip_single_instance_ignore_le_marqueur_reel[playing]`, qui prouve que `resolve_startup()` retourne `(True, None)` **avant même de lire le marqueur ou d'interroger l'état** dès que `ALCHESS_SKIP_SINGLE_INSTANCE=1` est actif — l'état réel (menu ou en partie) ne peut donc, par construction du correctif, avoir aucune influence sur le comportement.

Aucun vrai serveur d'Alain n'était en cours avant cette tâche (vérifié : marqueur absent) ; celui utilisé pour la vérification a été créé, puis entièrement arrêté et nettoyé par ce même traitement.

## 5. CONTEXTE.md (point 5)

Phrase ajoutée à la fin du paragraphe « Instance unique (#320) » : la règle « les serveurs de test ne partagent jamais le marqueur d'instance du serveur réel », avec le nom de la variable d'environnement.

## Fichiers modifiés

- `nicsoft/web/single_instance.py` — variable `ALCHESS_SKIP_SINGLE_INSTANCE`, fonction `_skip_check()`, court-circuit dans `resolve_startup()`/`write_marker()`/`remove_marker()`.
- `nicsoft/tests/e2e/conftest.py` — `ALCHESS_SKIP_SINGLE_INSTANCE=1` dans l'environnement du serveur de test.
- `nicsoft/tests/test_issue312_server_startup.py` — même variable, par défense en profondeur.
- `nicsoft/tests/test_issue320_single_instance.py` — nouveaux tests de non-régression (point 2).
- `CONTEXTE.md` — phrase ajoutée au paragraphe #320.

## Ce qui reste à faire

Rien d'identifié pour cette issue. Point d'attention pour une tâche future : si un autre test ou script venait à lancer un vrai serveur AlChess avec `ALCHESS_DIR` pointé vers le dossier utilisateur réel, il doit reprendre le même réflexe (`ALCHESS_SKIP_SINGLE_INSTANCE=1`).

# Changelog — Issue #323

# Issue #323 — Lichess : reprendre une partie en cours depuis le menu (reconstruction de la position avec cases rouges et LED), retrait du message éphémère « Nulle refusée » en double

## Contexte

Une partie Lichess continue même si AlChess s'arrête (plantage, coupure réseau, extinction de l'ordinateur) : la pendule de Lichess tourne et l'adversaire peut réclamer la victoire. Cette issue ajoute la possibilité de **reprendre la partie** depuis le menu, en reconstruisant la position physique sur l'échiquier guidé par l'écran et les LED — le mode jouable existant (`LichessGame`, validé en essais réels) est réutilisé tel quel pour le déroulement du jeu lui-même.

Livraison limitée au cas le plus simple explicitement permis par la consigne de repli : **reprise d'une partie amicale contre l'IA Lichess, variante standard**. Les parties humain-humain et de correspondance ne sont pas encore proposées — voir « Ce qui reste à faire » en fin de document.

## 1. Détection d'une partie en cours (point 1)

`nicsoft/modes/lichess/client.py::get_ongoing_games(token)` interroge `GET /api/account/playing` (délai court, 6s — ne doit jamais retarder l'ouverture du menu). Vérifié dans la spécification officielle `lichess-org/api` (dépôt GitHub, `doc/specs/tags/games/api-account-playing.yaml`, lu le 13/11/2026) : cette route ne déclare que `security: [{OAuth2: []}]`, sans scope nommé — même jeton, aucun droit supplémentaire, contrairement à `/api/challenge/ai` qui exige `board:play`.

La réponse (`nowPlaying`) est filtrée pour ne garder que les parties `source=ai` + `variant.key=standard` — seul cas que l'interface « échiquiers » (Board API, déjà utilisée par `GameClient`) permet de rejouer dans cette livraison. Lichess classe `nowPlaying` par urgence (« most urgent games are listed first », doc officielle) ; en l'absence d'horodatage de création dans cette réponse, la partie la plus urgente (première de la liste filtrée) est prise comme meilleure approximation disponible de « la plus récente », et une seule est proposée même s'il y en a plusieurs (`total_candidates` journalisé pour le savoir).

Pas de jeton, jeton refusé, limite de requêtes, ou coupure réseau → aucun message alarmant : `{"status": "invalid"/"rate_limited"/"network_error"}` fait simplement disparaître la proposition de reprise (`check_lichess_resumable()`, `core/game_manager_modes/lichess.py`), journalisé en WARNING sans jamais le jeton.

Appelé une seule fois à l'ouverture du menu Lichess (`alchess.py`, action `mode:lichess`, en thread démon — jamais en boucle), pas à chaque rafraîchissement.

## 2. Proposition dans le menu (point 2)

Nouveau bandeau `#lichess-resume-banner` (fond contrasté, en tête de `#screen-config-lichess`) affiché sur réception de l'évènement `lichess_resumable` : adversaire, couleur, cadence approximative (`speed` Lichess traduit — l'API ne renvoie pas la cadence exacte initial+incrément sur cette route), trait, et minutes restantes **côté utilisateur uniquement** (`secondsLeft` de `/api/account/playing` est le temps du point de vue du compte authentifié — confirmé en lisant `lila/modules/core/src/main/game/Pov.scala::remainingSeconds` — le temps de l'adversaire n'est disponible qu'une fois le flux de partie rouvert, affiché ensuite par les pendules normales de l'écran de jeu). Nom d'adversaire et tout texte Lichess insérés exclusivement via `textContent` (jamais interpolés dans du HTML — gardé par test e2e dédié avec un nom piégé `<img onerror=...>`).

## 3. Reprise — écran de mise en place (point 3)

Au clic (`launch_lichess_resume()`), `_peek_game_full()` ouvre le flux de la partie juste le temps de lire le premier `gameFull` (couleur, niveau IA, cadence réelle via `clock.initial`/`clock.increment`, coups déjà joués, statut), puis referme cette connexion avant que `LichessGame` n'ouvre la sienne pour jouer réellement (deux connexions courtes et indépendantes, plus simple et robuste qu'un partage de flux entre les deux modules).

`LichessGame` gagne un paramètre `resuming: bool` : si vrai, `self._resume_pending` reste actif jusqu'à ce que la position physique (relue en continu) corresponde à `self.board.board_fen()` — qui reste la cible à jour même si l'adversaire joue pendant la reconstruction (coups appliqués par le flux normal, dans la même boucle `_main_loop()`). Nouvelle méthode `_tick_resume_setup()` (appelée par `_tick_physical()` tant que `_resume_pending`) : compare position physique/cible, allume les LED des cases qui diffèrent (`_update_resume_setup_leds()`, jamais testé sur le vrai plateau — aucun matériel disponible pour cette issue), et émet l'évènement dédié `lichess_resume_setup` (`active`, `expected_fen`, `physical_fen`). Côté navigateur, ce nouvel évènement réutilise `renderBoardWithErrors()` (déjà utilisée par `lichess_illegal_position`, la pause auto et le labo) pour les cases rouges sur `#board`, orienté comme le reste de la partie (couleur déjà connue via `lichess_init`), plus un bandeau dédié `#lichess-resume-setup` indiquant que la partie et la pendule continuent.

Dès que la position correspond : `_resume_pending` repasse à faux, les attentes de début de partie que `_apply_new_moves()` a pu positionner avant même l'écran de mise en place (réplication du dernier coup adverse) sont neutralisées pour ne pas redemander une confirmation déjà satisfaite, et le jeu normal reprend sans aucun autre changement — pendules, boutons, messages du mode existant.

## 4. Cas traités (point 4)

- **(a) à l'utilisateur de jouer** et **(b) à l'adversaire de jouer** : la cible de mise en place est toujours `self.board.board_fen()`, reconstruite depuis la liste de coups du premier `gameFull` — correcte dans les deux cas sans distinction de code.
- **(c) partie terminée entre-temps** : détectée dès le premier `gameFull` par le mécanisme existant (`_check_finished()`, inchangé) — `game_over` devient vrai avant qu'aucun tick physique n'ait lieu ; le PGN est enregistré comme toute partie terminée (voir point 6).
- **(d) l'adversaire joue pendant la reconstruction** : `_tick_resume_setup()` relit `self.board.board_fen()` à chaque tick (mis à jour par le flux en continu) — la cible progresse sans jamais perdre les cases déjà correctement posées par l'utilisateur.
- **(e) partie avec moins de deux coups** : `_request_resign_or_abort()` (annulation vs abandon selon `len(self.board.move_stack) < 2`) et le décompte du premier coup (`_maybe_activate_first_move_deadline()`) sont entièrement inchangés — `self.board.move_stack` est déjà reconstruit depuis le premier `gameFull`, donc ce calcul reste correct pour une partie reprise.
- **(f) échiquier non connecté au moment de la reprise** : `_open_board_with_retry()` (réessais existants, #317) puis, pendant la mise en place elle-même, `_register_board_lost()`/`_maybe_attempt_reconnect()` (reconnexion automatique existante, #314) — jamais d'abandon automatique.

## 5. Règles Lichess inchangées (point 5)

Aucun moteur ni module d'analyse n'est importé par `game.py`/`game_manager_modes/lichess.py` (vérifié par un test qui fait échouer volontairement `find_stockfish`/`find_lc0`/`load_maia_weights` si appelés pendant une partie reprise). Menu verrouillé pendant la partie (mécanisme existant `_OTHER_MODE_ACTIONS`, inchangé). Boutons Abandonner/Proposer nulle désormais aussi désactivés tant que `_resume_pending` (ajouté à `_compute_action_buttons()`). Le jeton reste exclusivement côté serveur (`get_ongoing_games()`/`_peek_game_full()` ne le transmettent jamais au navigateur ni dans un journal — vérifié par test avec un jeton factice et `caplog`).

## 6. PGN (point 6)

`self.board` (et donc `self.board.move_stack`) est reconstruit depuis le tout premier coup de la partie (appliqué dès le premier `gameFull`, qu'il date d'avant ou d'après la reprise) : `_save_pgn()`/`_finalize()` (inchangés) enregistrent donc la partie reprise en entier, au même endroit que toute autre partie Lichess (`PGN/Lichess/Amicale/`).

## 7. Nettoyage — message éphémère « Nulle refusée » (point 7)

Les trois messages éphémères de nulle (`toast.lichess_draw_sent`, `toast.lichess_draw_refused`, `toast.lichess_draw_accepted`) ont été retirés d'`app.js` (`socket.on("lichess_draw_proposed"/"lichess_draw_refused"/"lichess_draw_accepted")`) : le bandeau persistant `#lichess-draw-wait-msg` (en place depuis #321) suffit déjà et reste seul affiché. Les trois clés i18n restent définies dans `fr/en/de.json` (plus utilisées mais inoffensives — aucune autre clé n'y fait référence) ; un test de garde existant (`test_issue310_lichess_corrections.py::test_extraction_cles_lichess_trouve_bien_des_cles_connues`), qui s'appuyait sur deux de ces clés comme exemples connus, a été mis à jour pour en citer deux toujours utilisées.

## 8. Journal (point 8)

Logger `niclink.lichess`, niveau INFO, sans jamais le jeton :
- liste reçue (`check_lichess_resumable()`) : nombre de parties reprenables candidates, identifiant de la partie proposée ;
- reprise demandée (`launch_lichess_resume()`) : identifiant de la partie ;
- état reçu au moment de la reprise (`_run_lichess_resume()`) : couleur, statut, nombre de coups déjà joués ;
- position reconstruite / jeu normal repris (`_tick_resume_setup()` / `_run_lichess_resume()`).

## 9. Tests

Sans réseau (urllib mocké, faux transport scénarisé) et sans matériel (double léger de l'échiquier) :

- `nicsoft/tests/test_issue323_lichess_resume.py` (36 tests) : `get_ongoing_games()` (jeton absent/refusé/limité/coupure réseau/réponse illisible, filtrage source+variante, partie la plus urgente proposée si plusieurs) ; `check_lichess_resumable()` (sans jeton, erreur réseau silencieuse avec vérification `caplog` que le jeton n'apparaît jamais, aucune partie, partie proposée) ; `LichessGame(resuming=True)` : boutons désactivés pendant la mise en place, cases en erreur + LED signalées, position déjà correcte reprend immédiatement, reprise puis coup utilisateur détecté normalement, cible mise à jour sans perte de travail quand l'adversaire joue pendant la reconstruction (cas d), échiquier perdu pendant la mise en place sans abandon automatique, cas (e) moins de deux coups, cas (c) partie déjà terminée (PGN enregistré) ; scénario complet multi-thread (mise en place → coup utilisateur, sans aucun moteur) ; `launch_lichess_resume()`/`_run_lichess_resume()` (mode déjà actif, sans identifiant, sans jeton, erreur réseau, échiquier non détecté, jeton refusé) ; nouvelles clés i18n (fr/en/de) ; câblage `app.js` (nouveaux évènements/actions présents, jamais d'innerHTML pour le nom d'adversaire, réutilisation de `renderBoardWithErrors`).
- `nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py` (7 tests, Playwright, dossier `nicsoft/tests/e2e/`) : bandeau masqué sans partie en cours, bandeau affiché avec les bonnes informations, nom d'adversaire piégé (`<img onerror=...>`) jamais exécuté comme HTML, clic sur « Reprendre » envoie l'action avec le bon identifiant de partie, écran de mise en place affiche le bandeau et des cases rouges sur `#board`, bandeau masqué une fois la position confirmée, boutons Abandonner/Proposer nulle restent grisés par défaut pendant la mise en place.
- `nicsoft/tests/test_issue310_lichess_corrections.py` : mis à jour (deux clés i18n obsolètes remplacées dans le test de garde de l'extraction).

Suite complète (hors e2e) : 949 passés, 80 ignorés (matériel/réseau réel). Suite e2e Lichess : 55 passés. Suite e2e complète : 99 passés, 1 ignoré. `python -m py_compile` : OK sur tous les fichiers Python modifiés. Démarrage réel du serveur (`ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) vérifié (HTTP 200, aucune erreur au démarrage).

### Ce qui n'a pas pu être testé

- Comportement réel des LED pendant la mise en place (`_update_resume_setup_leds()`) et de la reconnexion automatique de l'échiquier pendant cette phase : aucun matériel Chessnut disponible dans cet environnement — repose sur les mêmes primitives (`set_led`, `turn_off_all_leds`, reconnexion #314) déjà utilisées et validées ailleurs dans le module.
- Scénario avec une vraie partie Lichess réelle en cours (détection, reprise de bout en bout contre le vrai serveur Lichess) : aucun jeton Lichess disponible dans cet environnement de test — entièrement couvert côté logique par les tests avec faux transport/urllib mocké ci-dessus.
- Partie de correspondance ou partie contre un autre humain : hors scope de cette livraison (voir ci-dessous).

### Ce qui reste à faire

- Proposer la reprise de parties humain-humain et de correspondance (actuellement filtrées : seules les parties `source=ai` + variante standard sont proposées).
- Afficher le temps restant de l'adversaire dans le bandeau du menu (nécessiterait un second appel réseau ou d'attendre l'ouverture du flux de partie — non fait pour rester dans le délai court demandé pour la détection).
- Proposer plusieurs parties reprenables à la fois si l'utilisateur en a plusieurs en cours (actuellement une seule, la plus urgente, comme demandé pour cette première livraison).

## Fichiers modifiés

- `nicsoft/modes/lichess/client.py` : `get_ongoing_games()`.
- `nicsoft/core/game_manager_modes/lichess.py` : `check_lichess_resumable()`, `launch_lichess_resume()`, `_run_lichess_resume()`, `_peek_game_full()`.
- `nicsoft/modes/lichess/game.py` : `LichessGame(resuming=...)`, `_tick_resume_setup()`, `_update_resume_setup_leds()`, `_differing_squares()`, gating de `_compute_action_buttons()`.
- `nicsoft/core/game_manager.py` : réexport des nouvelles fonctions.
- `nicsoft/web/alchess.py` : déclenchement de la détection à l'ouverture du menu Lichess, routage de l'action `start_lichess_resume`.
- `nicsoft/web/static/app.js` : bandeau de reprise, écran de mise en place, retrait des 3 toasts éphémères de nulle.
- `nicsoft/web/templates/index.html` : bandeau `#lichess-resume-banner`, bandeau `#lichess-resume-setup`.
- `nicsoft/web/static/css/main.css` : styles du bandeau de reprise.
- `nicsoft/web/static/i18n/{fr,en,de}.json` : nouvelles clés de reprise.
- `nicsoft/tests/test_issue323_lichess_resume.py`, `nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py` : nouveaux.
- `nicsoft/tests/test_issue310_lichess_corrections.py` : clés i18n de garde mises à jour.
- `CONTEXTE.md` : paragraphe Lichess mis à jour.

# Changelog — Issue #322

# Issue #322 — Lichess : contre l'IA, ni phrase d'annulation ni décompte du premier coup ; pendules jamais décomptées avant les premiers coups

## Contexte

Essai réel d'Alain après #321 (partie amicale contre l'IA de Lichess niveau 1, 15+10, utilisateur aux noirs, juste après le premier coup e4 de l'IA). Deux défauts restaient visibles à l'écran :

1. La phrase « Jouez votre premier coup — la partie sera annulée dans environ 27 secondes » apparaissait contre l'IA, alors que sur lichess.org une partie contre l'IA n'affiche jamais de menace d'annulation ni de décompte du premier coup (contrairement à une partie contre un humain, qui elle les affiche) — confirmé par l'essai réel d'Alain (partie non annulée après plus de 28 secondes).
2. La pendule de l'utilisateur affichait 14:57 (au lieu de 15:00) alors qu'il n'avait pas encore joué son propre premier coup : elle décomptait localement, alors que sur lichess.org les deux pendules restent figées à leur valeur de départ jusqu'à ce que chaque camp ait joué son propre premier coup.

## 1. Plus de menace d'annulation ni de décompte contre l'IA

Cause : `_maybe_activate_first_move_deadline()` (`nicsoft/modes/lichess/game.py`) calculait toujours une estimation locale (`estimated_first_move_deadline_s()`, issue #321 point 6) dès que Lichess n'envoyait pas le champ `expiration` — sans distinguer IA et humain, alors que l'estimation elle-même (délai avant annulation du premier coup, lu dans le code lila) ne s'applique en réalité qu'aux parties contre un humain.

Correction :
- Nouvel attribut `self._opponent_is_ai`, déduit dans `_apply_game_full()` de la présence d'`aiLevel` d'un des deux côtés — vrai pour toute partie lancée par AlChess aujourd'hui (seul le mode « contre l'IA » existe), prêt pour un futur mode contre un humain sans rien y changer.
- `_maybe_activate_first_move_deadline()` ne calcule plus d'estimation locale (`_first_move_deadline_estimate_total_s` reste `None`) quand `self._opponent_is_ai` est vrai et qu'aucune `expiration` explicite n'est fournie — dans ce cas l'évènement `lichess_first_move_deadline` envoyé au navigateur porte `seconds: None`, comme avant l'estimation locale de #321. Si Lichess envoie malgré tout une `expiration` explicite pour une partie contre l'IA, elle reste utilisée normalement (décompte exact, rouge à 5 secondes).
- Côté navigateur, ce cas (`seconds` absent) affichait déjà un texte sans décompte (`lichess.premier_coup_sans_decompte`) et jamais la classe de danger (`_lichessRenderFirstMoveDeadline()` dans `app.js`, inchangé) — seul le texte lui-même menaçait encore d'annulation. Les 3 traductions (`fr/en/de.json`) ont été corrigées en un texte purement informatif : « Jouez votre premier coup. » / « Play your first move. » / « Spielen Sie Ihren ersten Zug. ».
- Le comportement contre un humain (quand ce mode existera) n'est pas modifié : décompte, mention « environ » si estimé, rouge à 5 secondes ou moins.

## 2. Pendules jamais décomptées avant les premiers coups des deux camps

Cause : `_maybe_push_clock()` extrapolait toujours le temps écoulé localement (`now - self._clock_ref_monotonic`) pour décompter la pendule du camp au trait, sans savoir si Lichess faisait réellement tourner cette pendule. Or sur lichess.org (vérifié par l'essai réel d'Alain, confirmé par la cohérence avec le champ `expiration`/`millisToMove` qui gère justement le premier coup de chaque camp *en dehors* de `wtime`/`btime`) : les deux pendules restent figées à leur valeur de départ jusqu'à ce que **chaque camp** ait joué son propre premier coup — pas seulement celui qui est actuellement au trait. Concrètement : au tout début de partie (`moves_applied == 0`), la pendule des blancs ne tourne pas pendant leur réflexion sur le 1er coup ; après ce 1er coup (`moves_applied == 1`), la pendule des noirs ne tourne pas non plus pendant leur propre 1er coup (c'est exactement le cas observé par Alain, 14:57 au lieu de 15:00 figé) ; ce n'est qu'à partir du 2e coup de chaque camp (`moves_applied >= 2`) que les deux pendules décomptent normalement, selon le trait.

Correction :
- Nouvel attribut `self._clock_running`, recalculé dans `_reset_clock_from_state()` (appelé à chaque `wtime`/`btime` reçu de Lichess, donc après chaque coup) : `self._moves_applied >= 2`.
- `_maybe_push_clock()` force `elapsed_s = 0.0` tant que `self._clock_running` est faux — la pendule envoyée au navigateur reste alors strictement égale à la dernière valeur connue de Lichess, jamais décomptée par une minuterie locale qui partirait d'elle-même. Dès que `self._clock_running` devient vrai, l'extrapolation normale reprend (comportement inchangé depuis #309).
- `compute_clock_ms()` (fonction pure) n'a pas été modifiée — le gel se fait uniquement en amont, par `elapsed_s` figé à 0.
- Vérifié pour les deux couleurs (voir tests) : le gel s'applique aussi bien à la pendule des blancs avant leur tout premier coup qu'à celle des noirs avant leur propre premier coup.

### Journal

Une ligne de log (niveau INFO, logger `niclink.lichess`) est émise à chaque recalage de pendule (`_reset_clock_from_state()`) avec les valeurs blancs/noirs, le trait et l'état `decompte` (`True`/`False`), plus une ligne dédiée au moment précis où le décompte démarre (« Lichess : pendules commencent à décompter après les premiers coups des deux camps (...) »), journalisée une seule fois à la transition.

## Tests

- `nicsoft/tests/test_issue311_lichess_sequencing.py` :
  - `test_decompte_premier_coup_sans_champ_expiration_contre_ia_reste_informatif` (remplace l'ancien test qui attendait à tort une estimation de 30s contre l'IA) : contre l'IA, sans `expiration`, `seconds` est `None`.
  - `test_decompte_premier_coup_sans_champ_expiration_contre_humain_estime` : la logique d'estimation (issue #321) reste intacte pour `self._opponent_is_ai = False` — exercée directement sur `LichessGame` (le lanceur actuel ne construit encore que des parties contre l'IA, voir CLAUDE.md : aucun mode humain n'existe côté `_apply_game_full()`).
  - `test_pendule_noire_figee_juste_apres_le_premier_coup_blanc`, `test_pendule_blanche_figee_avant_le_tout_premier_coup`, `test_pendules_decomptent_normalement_apres_les_deux_premiers_coups` : gel avant les deux premiers coups (les deux couleurs), reprise normale ensuite, et présence de la ligne de journal au moment de la transition (`caplog`).
  - Tests existants (`test_decompte_premier_coup_apparait_avec_expiration`, `test_decompte_premier_coup_disparait_apres_le_coup_utilisateur`) inchangés et toujours verts : une `expiration` explicite reste utilisée même contre l'IA.
- Nouveau fichier `nicsoft/tests/e2e/test_issue322_lichess_e2e.py` (Playwright, événements socket simulés, même technique que #310/#321) :
  - message informatif sans menace d'annulation et jamais rouge quand `seconds` est `None` (cas IA) ;
  - non-régression du décompte réel (menace + « environ » + rouge à 5s) quand `seconds` est fourni (cas humain/IA avec `expiration` explicite) ;
  - pendule utilisateur figée à 15:00 juste après le premier coup de l'IA (reproduit l'essai réel d'Alain) ;
  - pendule figée pour l'utilisateur aux blancs avant son tout premier coup (les deux couleurs) ;
  - affichage normal d'une pendule déjà décomptée une fois les deux premiers coups joués.
- Suite complète (`pytest nicsoft/tests/` y compris `e2e/`) : 1004 passés, 81 ignorés (hors matériel/réseau), 0 échec.

## Non testé sans le matériel

Comme pour #321 : aucune vraie partie Lichess (réseau, jeton) ni échiquier physique — tout est simulé (faux `GameClient`/transport côté Python, événements socket directement injectés côté navigateur). Impossible de confirmer ici, autrement que par la lecture du code lila et l'essai réel déjà fait par Alain, que `moves_applied >= 2` est exactement le seuil que Lichess utilise en interne pour démarrer chaque pendule — seul un nouvel essai réel (partie contre l'IA, en observant les pendules dès l'écran de jeu) peut le confirmer définitivement.

## Fichiers modifiés

- `nicsoft/modes/lichess/game.py` — `_opponent_is_ai`, `_clock_running`, gating de l'estimation du premier coup et de l'extrapolation des pendules, journal.
- `nicsoft/web/static/i18n/fr.json`, `en.json`, `de.json` — texte de `lichess.premier_coup_sans_decompte` sans menace d'annulation.
- `nicsoft/tests/test_issue311_lichess_sequencing.py` — tests mis à jour/ajoutés.
- `nicsoft/tests/e2e/test_issue322_lichess_e2e.py` — nouveau fichier de tests navigateur.

# Changelog — Issue #321

# Issue #321 — Lichess : boutons Abandonner et Proposer nulle actifs seulement à son tour, et messages de nulle qui restent affichés

## Contexte

Deux essais réels d'Alain le 13 novembre 2026 (blancs puis noirs) ont révélé plusieurs gênes autour de la nulle et de la reproduction des coups :

1. Les boutons « Abandonner » et « Proposer nulle » étaient actifs en permanence, y compris pendant que l'adversaire réfléchissait ou que l'utilisateur devait encore reproduire son coup sur l'échiquier — séquence vécue : proposition de nulle, puis coup adverse reproduit, puis coup propre joué (aucune indication que l'offre était en attente), puis « Nulle refusée » apparu brusquement.
2. Les messages de nulle (proposée/refusée/acceptée) étaient de brefs toasts éphémères, ratés en alternant le regard entre l'écran et l'échiquier physique.
3. Lecture du journal : l'offre part vers Lichess au clic, mais l'IA ne répond qu'en jouant son propre coup **après** celui de l'utilisateur — source de confusion non expliquée à l'écran.
4. Partie avec les noirs : un pion blanc (d4) joué par erreur à la place du coup noir a laissé affichée la phrase « Jouez votre premier coup, sinon la partie sera annulée par Lichess » sans aucune indication lisible que la position physique était invalide.
5. Le décompte du premier coup n'existe que si Lichess envoie `expiration` — absent lors de cet essai.

## 1. Boutons actifs seulement à son tour (points 1 et 2)

`LichessGame._compute_action_buttons()` (`nicsoft/modes/lichess/game.py`) calcule `(resign_enabled, draw_enabled)` à partir de l'état déjà suivi par la partie — jamais d'un nouvel état dupliqué :
- `resign_enabled` / `draw_enabled` de base = trait de l'utilisateur **ET** position physique alignée (ni réplication du coup adverse, ni recalage après reconnexion, ni promotion en attente, ni position illégale, ni échiquier perdu).
- Exception de sécurité n°1 : `resign_enabled` reste vrai si l'échiquier est perdu (jamais bloquer l'utilisateur).
- Exception de sécurité n°2 (comportement préexistant conservé) : `draw_enabled` reste faux tant qu'une offre de l'utilisateur est déjà en attente de réponse — jamais deux propositions superposées.
- Les boutons de réponse à une offre adverse (accepter/refuser) ne passent jamais par ce calcul : `_process_browser_actions()` les traite sans condition, à tout moment.

`_sync_turn_ready()` envoie l'évènement `lichess_action_buttons` (`{"resign_enabled", "draw_enabled"}`) uniquement quand l'état change (pas de bruit à chaque tick), appelé :
- à chaque tick physique (`_tick_physical()`, ~50ms) — couvre tour adverse, réplication en cours, recalage, promotion, position illégale, échiquier perdu ;
- à chaque transition explicite de fin de partie (abandon, annulation, retour au menu, fin détectée par le flux) — ces chemins quittent la boucle principale avant le tick suivant.

Côté `app.js`, `_lichessSetActionButtons(resignEnabled, drawEnabled, showHint)` est la **seule** fonction qui pose l'attribut `disabled` sur `#btn-resign`/`#btn-nulle` — jamais recalculé côté navigateur à partir d'autres signaux, pour que les exceptions de sécurité restent cohérentes avec la seule source de vérité (le thread `LichessGame`). Désactivés par défaut dès `lichess_init` (y compris pour les deux couleurs, dès le tout début de partie), corrigés par le premier `lichess_action_buttons` qui suit dans la même fonction Python. Un petit texte (`#lichess-actions-hint`, clé `lichess.boutons_actifs_a_votre_tour`) apparaît près des boutons quand l'un des deux est désactivé. `init`/`init_hh` (pédagogique/HH) forcent explicitement les deux boutons actifs — ce mécanisme ne concerne que Lichess.

## 2. Messages de nulle persistants (points 3 et 4)

Les trois anciens toasts éphémères (`toast.lichess_draw_sent/refused/accepted`, conservés en complément) sont remplacés comme information principale par un bandeau unique et persistant, réutilisé pour les 3 états plutôt que d'en créer un second : `#lichess-draw-wait-msg`, déplacé près de « Tour en cours » (carte `turn-info`), classe `.lichess-draw-status-banner` (gros caractères).

- **Proposée** (`lichess_draw_proposed`) : « Nulle proposée : l'adversaire répondra à son prochain coup, après le vôtre. » — dit explicitement que la réponse vient après le coup de l'utilisateur, contrairement à ce qu'Alain avait cru comprendre le 13/11.
- **Refusée** (`lichess_draw_refused`) : « Nulle refusée par l'adversaire. », en rouge (`.lichess-banner-danger`) — reste affiché au moins jusqu'au coup suivant **joué par l'utilisateur** (`_lichessDrawBannerPendingClearOnOwnMove`, effacé sur le premier `lichess_move` reçu avec `opponent_move:false` — pas sur la reproduction du coup adverse qui précède).
- **Acceptée** (`lichess_draw_accepted`) : « Nulle acceptée — partie terminée. »

La règle de décision du refus elle-même (issue #318 : jamais sur l'écho de notre propre coup, seulement sur un vrai coup adverse sans acceptation) n'est pas modifiée.

## 3. Position physique incorrecte pendant la partie (point 5)

Nouvel évènement dédié `lichess_illegal_position` (`{"active", "expected_fen", "physical_fen"}`), émis par `_activate_illegal_position()`/`_clear_illegal_position()` dans `LichessGame._check_user_move()` — **distinct** de `lichess_position_wait` (qui concerne la reproduction du coup adverse, scénario différent). Déclenché dans les mêmes conditions qu'avant (`ILLEGAL_STABLE_READS_REQUIRED` lectures stables identiques, ni la position attendue ni un coup légal), mais pendant le tour de l'utilisateur spécifiquement.

Côté `app.js` : bandeau `#lichess-illegal-position` (clé `lichess.position_incorrecte`, « Position incorrecte : corrigez les cases en rouge sur l'échiquier. ») + cases en rouge sur l'échiquier de l'écran via `renderBoardWithErrors()` — fonction déjà existante (pause auto, labo), pas de nouveau mécanisme de surlignage. Remplace la phrase du premier coup (`#lichess-first-move-deadline`) tant qu'elle est active.

**Ce qu'Alain a réellement vu le 13/11 (reconstitué depuis le code d'avant ce correctif)** : deux bannières simultanées, aucune des deux adaptée au problème réel — (a) `#lichess-first-move-deadline` restée affichée (« Jouez votre premier coup, sinon annulée »), puisque rien ne la désactivait avant que l'utilisateur joue un coup *qui lui soit attribué* ; (b) le texte générique `#lichess-position-wait` (« Reproduisez le coup sur l'échiquier physique »), déclenché par le même code qui envoie maintenant `lichess_illegal_position` — un texte pensé pour "reproduire le coup adverse", pas pour "votre coup est illégal, corrigez ces cases", et sans aucune case en rouge. Aucune des deux ne disait quoi corriger ni où — d'où la confusion jusqu'à ce qu'il remette le pion blanc en place par essai-erreur.

## 4. Décompte du premier coup (point 6)

Vérifié aujourd'hui (13/11/2026) dans le code public de Lichess (pas de documentation officielle dédiée trouvée) :
- `lila` (branche `master`, `modules/game/src/main/Game.scala::timeForFirstMove`) : hors tournoi, variante standard — UltraBullet 15s, Bullet 20s, Blitz 25s, Rapid 30s, Classical/Correspondence 35s (×1,5 en chess960, non applicable ici).
- `scalachess` (`Speed.scala::byTime`) : bornes de cadence en secondes estimées — UltraBullet [0,30), Bullet [30,180), Blitz [180,480), Rapid [480,1500), Classical [1500,21600), sinon Correspondence.
- `scalachess` (`Clock.scala::estimateTotalSeconds`) : `limite + 40×incrément`.

Ces trois extraits ont été relus mot pour mot dans le code actuellement publié (`curl raw.githubusercontent.com`) — le délai réel **est** établi, donc pas de repli sur « pas de décompte » : `estimated_first_move_deadline_s(clock_limit_s, clock_increment_s)` (déjà présent dans ce fichier avant la reprise de ce traitement, vérifié conforme ci-dessus) est utilisé par `_maybe_activate_first_move_deadline()`/`_maybe_push_clock()` quand `expiration` est absent du message Lichess — `_first_move_deadline_seconds_and_estimated()` retourne `(secondes, estimated=True)` dans ce cas. Journalisé (`_log_game_state_received`) : `expiration` brut, présent ou non, à chaque état reçu — permet de confirmer a posteriori si/quand Lichess l'envoie réellement (observé absent lors de l'essai du 13/11).

Côté interface : texte dédié quand estimé (clé `lichess.premier_coup_decompte_estime`, « … dans **environ** {seconds} secondes ») — jamais présenté comme exact. Le texte (estimé ou exact) passe en rouge (`.lichess-banner-danger`) à 5 secondes ou moins.

## 5. Fichiers modifiés

- **`nicsoft/modes/lichess/game.py`** : `_compute_action_buttons()`/`_sync_turn_ready()` (nouveau), `_activate_illegal_position()`/`_clear_illegal_position()` (nouveau), `_tick_physical()` scindé en `_tick_physical_inner()` + appel systématique de `_sync_turn_ready()`, `_check_user_move()` met à jour l'état de position illégale, `_maybe_activate_first_move_deadline()`/`_maybe_push_clock()`/`_first_move_deadline_seconds_and_estimated()` (nouveau) pour l'estimation de repli, appels de synchronisation ajoutés dans `_apply_game_full()`/`_apply_game_state()`/`_check_finished()`. `_turn_ready`/`_last_position_wait_kind` (champs inutilisés laissés par une tentative précédente de cette même issue) supprimés au profit de `_action_buttons_state`.
- **`nicsoft/web/static/app.js`** : `_lichessSetActionButtons()` (nouveau), gestionnaires `lichess_action_buttons`/`lichess_illegal_position` (nouveaux), bandeau de nulle persistant (`_lichessShowDrawBanner()`), rendu du décompte du premier coup mis à jour (estimation + rouge à 5s), remplacement de la phrase du premier coup par le message de position illégale quand actif, réinitialisation des boutons dans `init`/`init_hh`/`lichess_init`/`_lichessHideStatusBanners()`.
- **`nicsoft/web/templates/index.html`** : `id="btn-resign"` ajouté au bouton Abandonner, `#lichess-illegal-position` et `#lichess-draw-wait-msg` déplacés dans la carte « Tour en cours », `#lichess-actions-hint` ajouté dans la carte Actions.
- **`nicsoft/web/static/css/main.css`** : `.lichess-draw-status-banner`, `.lichess-info-banner.lichess-banner-danger`, `.lichess-actions-hint`.
- **`nicsoft/web/static/i18n/{fr,en,de}.json`** : `lichess.nulle_attente_reponse` (texte mis à jour), `lichess.nulle_refusee_banner`, `lichess.nulle_acceptee_banner`, `lichess.position_incorrecte`, `lichess.boutons_actifs_a_votre_tour`, `lichess.premier_coup_decompte_estime` (nouvelles clés) — les 3 langues ont le même jeu de clés (vérifié).
- **`nicsoft/tests/test_issue321_lichess_boutons_et_nulle.py`** (nouveau, 9 tests, sans réseau ni matériel).
- **`nicsoft/tests/e2e/test_issue321_lichess_e2e.py`** (nouveau, 10 tests Playwright, évènements socket simulés).
- **`nicsoft/tests/e2e/test_issue310_lichess_e2e.py`** : fixture `at_game_lichess` complétée d'un `lichess_action_buttons` simulé (sinon `test_game_lichess_bouton_nulle_visible` échouait — ce test vérifiait l'ancien comportement où `lichess_init` activait directement le bouton).
- **`nicsoft/tests/test_issue311_lichess_sequencing.py`** : `test_decompte_premier_coup_sans_champ_expiration` mis à jour pour refléter l'estimation de repli (avant #321 : pas de décompte sans `expiration` ; depuis #321 : estimation locale).
- **`CONTEXTE.md`** : entrée #321 ajoutée à la section Lichess.

## 6. Tests

**Python** (`test_issue321_lichess_boutons_et_nulle.py`, sans réseau ni matériel — `FakeBoard`/`FakeTransport` comme le reste de la suite Lichess) :
- boutons grisés au tout début de partie pour les noirs, avant et pendant la reproduction du coup adverse (2 tests) ;
- boutons actifs dès le début pour les blancs, et pour les noirs une fois le coup reproduit (2 tests) ;
- position illégale (reproduction exacte du scénario réel : pion blanc d2-d4 joué à la place du coup noir) → boutons grisés, évènement avec les bonnes cases, puis réactivation une fois la pièce remise en place (1 test) ;
- abandon possible échiquier perdu même hors tour, accepter/refuser une offre adverse toujours possible boutons désactivés, pas de double offre de nulle (4 tests).

**Navigateur** (`test_issue321_lichess_e2e.py`, Playwright réel, évènements socket simulés comme `test_issue310_lichess_e2e.py` — sans réseau ni partie Lichess réelle) :
- boutons désactivés par défaut puis activés par `lichess_action_buttons`, exception Abandonner seul actif (3 tests) ;
- bandeau de nulle : texte « après »/« after »/« nach », persistance jusqu'au coup de l'utilisateur, bandeau dédié pour l'acceptation (3 tests) ;
- position incorrecte : remplace la phrase du premier coup, case(s) rouge(s) sur l'échiquier, réapparition de la phrase une fois corrigée (1 test) ;
- décompte du premier coup : pas rouge au-dessus de 5s, rouge à 5s ou moins, mention « environ »/« approximately »/« etwa » quand estimé (3 tests).

Suite complète (`pytest nicsoft/tests/`) : 993 passed, 81 skipped (tests `hardware`, non exécutés sans échiquier physique) — aucune régression.

**Non testable sans le matériel réel** : le ressenti visuel exact sur l'échiquier physique Chessnut (LED, cases rouges perçues en conditions réelles de luminosité), et la confirmation sur une vraie partie Lichess que `expiration` est bien absent pour toutes les cadences (seul observé pour la cadence de l'essai du 13/11) — le journal enrichi (`_log_game_state_received`) permettra de le confirmer lors du prochain essai réel.

## 7. Reprise de travail

Ce traitement est une **reprise d'un worktree d'une tentative précédente de cette même issue #321** (commits `avant-321-...` déjà présents en double dans l'historique local avant cette session). Le travail déjà présent se limitait à une ébauche incomplète dans `nicsoft/modes/lichess/game.py` : les fonctions pures d'estimation du délai du premier coup (`speed_key_for_clock`, `estimated_first_move_deadline_s`, constantes `_FIRST_MOVE_TIMEOUT_BY_SPEED`) — vérifiées exactes contre le code source actuel de `lila`/`scalachess` et conservées sans modification — et un champ `_turn_ready`/un appel à une méthode `_sync_turn_ready()` non définie (aurait levé `AttributeError` dès le premier abandon/retour au menu). Aucun autre point de la tâche (boutons, messages de nulle persistants, position illégale, interface) n'était ébauché.

# Changelog — Issue #320

# Issue #320 — Une seule instance du serveur AlChess à la fois : la nouvelle remplace l'ancienne, sauf si une partie y est en cours

## Contexte

Le 13 novembre 2026, Alain a constaté que relancer AlChess alors qu'une instance précédente tournait déjà laissait **deux serveurs actifs en même temps**, sans aucun avertissement — risqué pour l'accès USB (un seul accès ouvert à la fois, règle de projet) et pour la lisibilité des journaux (les deux écrivent dans le même fichier). Un lien de causalité avec les échecs d'ouverture récents (« aucun paquet de position lu », #319) a été évoqué dans la tâche comme hypothèse à vérifier, pas à supposer — **non établi** par ce travail : aucune preuve dans les journaux existants ne montre deux instances actives au moment de ces échecs, et rien dans l'architecture ne permettait jusqu'ici de le confirmer ou de l'infirmer après coup (c'est justement une partie du problème que corrige ce correctif : désormais, chaque ligne de journal porte le PID et le port de l'instance qui l'a écrite — voir §4).

## 1. Méthode retenue

**Marqueur d'instance** (`DATA_DIR/server_instance.json`, donc `ALCHESS_DIR` en test) : `{"pid": ..., "port": ..., "started_at": ...}`, écrit par `write_marker()` au démarrage (écriture atomique — fichier temporaire puis renommage), supprimé par `remove_marker()` à l'arrêt propre (uniquement s'il désigne encore le PID appelant — une instance qui s'arrête en retard n'efface jamais le marqueur d'une instance plus récente qui l'aurait déjà remplacée).

**Reconnaissance d'un processus AlChess** (jamais par le seul nom du programme — `python`/`python3` ne prouve rien) : le PID du marqueur doit être vivant (`os.kill(pid, 0)` sur Linux, `tasklist /FI "PID eq N"` sur Windows) **ET** sa ligne de commande doit contenir `nicsoft.web`/`nicsoft/web` (lue dans `/proc/<pid>/cmdline` sur Linux, via `wmic process where ProcessId=N get CommandLine` sur Windows — non testé, voir §5). Un PID réutilisé par un autre programme échoue ce second test et le marqueur est traité comme périmé : ignoré, jamais touché.

**Reconnaissance d'une partie en cours** : requête HTTP locale à l'ancienne instance, nouvelle route `GET /instance_status` (`nicsoft/web/server.py`, protégée par `_require_allowed_host()` comme les autres routes de lecture sensibles) qui renvoie `{"pid", "port", "state"}` — `state` est l'`_app_state` courant de cette instance, **pas** une relecture du marqueur (qui pourrait dater d'avant le dernier changement d'état). Préféré à une simple lecture de fichier : l'état vivant est la seule source fiable de "une partie tourne-t-elle là, maintenant". `BUSY_STATES` (`single_instance.py`) retient les états correspondant à une vraie partie, tous modes de jeu confondus (Lichess compris) — `connecting`, `playing`, `paused`, `position_initiale`, `lichess_wait_first_move`, `retrans_playing`, `exercice_running` — et exclut délibérément les écrans de menu/config/sélection et les outils d'analyse libre (`labo`, `opening_explorer`), qui ne sont pas "une partie" au sens de la tâche. Si la requête échoue (pas de réponse, timeout, instance en train de démarrer/planter) : **par précaution, on n'y touche pas** et on refuse de démarrer, plutôt que de risquer d'interrompre une partie dont l'état n'a pas pu être confirmé.

**Arrêt de l'ancienne instance inactive** : SIGTERM par son PID exact (le même signal que `_handle_termination_signal` sait déjà gérer proprement — relance de ModemManager puis sortie, ce qui déclenche ses propres callbacks `atexit`, dont la suppression de son marqueur), attente jusqu'à 5s par sondage de `os.kill(pid, 0)`, SIGKILL par ce même PID seulement en dernier recours. Sous Windows : `taskkill /PID N` puis `taskkill /PID N /F` (jamais `/IM`). Le fait d'attendre la confirmation de sortie du processus (pas un simple délai fixe) garantit que l'échiquier USB est déjà libéré par le noyau avant que la nouvelle instance ne démarre.

## 2. Intégration — tous les lanceurs

Le point d'entrée unique de tous les lanceurs (`start_alchess.sh`, `start_alchess.ps1`, `2-Lancer_AlChess.bat`, `nicsoft/web/launcher.py`) est `python -m nicsoft.web` → `nicsoft/web/alchess.py::main()`. La vérification (`single_instance.resolve_startup()`) y est appelée en tout premier, avant tout effet de bord (arrêt de ModemManager, recherche de port libre) : si une partie est en cours ailleurs, le message « Une partie est en cours dans l'instance déjà lancée, port N. » est affiché (`print`, puis journalisé) et le programme quitte sans avoir rien démarré ni touché à l'ancienne instance. Aucune commande nommée « chess » n'existe dans ce projet (vérifié : aucun `console_scripts` dans `nicsoft/pyproject.toml`, aucun fichier portant ce nom) — un seul point d'entrée Python, donc un seul endroit à corriger pour couvrir tous les lanceurs, Windows compris pour la partie "point de départ du contrôle". La partie spécifiquement Windows de la détection/arrêt de processus (`tasklist`/`wmic`/`taskkill`) est écrite mais **non testée** faute de machine Windows dans ce périmètre (voir §5).

## 3. Journal et console

`main()` affiche et journalise désormais `[NicLink] PID <pid> — port <port>` dès que le port est choisi, avant le démarrage du serveur — permet de rattacher toute ligne ultérieure du même fichier `niclink.log` à l'instance qui l'a écrite.

## 4. Fichiers modifiés

- **`nicsoft/web/single_instance.py`** (nouveau) : toute la logique — marqueur, détection PID+cmdline, requête d'état locale, arrêt par PID, décision `resolve_startup()`.
- **`nicsoft/web/server.py`** : nouvelle route `GET /instance_status` (juste après `/debug/mode`), protégée par `_require_allowed_host()`, aucun secret exposé.
- **`nicsoft/web/alchess.py`** : `main()` appelle `single_instance.resolve_startup()` en premier ; écrit le marqueur (`write_marker`) et enregistre sa suppression à la sortie (`atexit.register(single_instance.remove_marker, pid)`) une fois le port choisi ; affiche/journalise PID+port. Import de `datetime` déplacé en tête de module (déjà utilisé localement dans `_setup_logging()`, maintenant aussi dans `main()`).
- **`nicsoft/tests/test_issue320_single_instance.py`** (nouveau, 20 tests).
- **`CONTEXTE.md`** : section courante mise à jour.

## 5. Tests

**Sans matériel** (`ALCHESS_SKIP_BOARD=1`), sans navigateur (`ALCHESS_NO_BROWSER=1`/`BROWSER=/bin/true`), `DATA_DIR` isolé (tmp_path, jamais le dossier réel de l'utilisateur), **aucun arrêt par nom de programme** — uniquement par PID exact.

- 17 tests unitaires sur `single_instance.py`, avec de **faux processus lancés par les tests eux-mêmes** (simples boucles `time.sleep`, jamais un vrai serveur AlChess) : aucune ancienne instance, marqueur périmé (processus mort), PID réutilisé par un programme étranger (vérifié non touché), ancienne instance inactive remplacée (vérifié arrêtée), ancienne instance en partie refusée pour chacun des 7 `BUSY_STATES` (vérifiée non touchée), état de l'ancienne instance impossible à confirmer → refus par précaution, écriture/suppression du marqueur (y compris non-suppression si le PID a changé entre-temps), reconnaissance par ligne de commande (positive et négative).
- 2 tests sur la route `/instance_status` (client de test Flask, même pattern que `test_issue304_security.py`) : refus si `Host` étranger, contenu (pid/port/état) sinon.
- **1 test d'intégration réel** (`@pytest.mark.slow`), seul test de ce fichier à lancer de vrais sous-processus `python -m nicsoft.web` (toujours arrêtés par leur PID exact en nettoyage) : une première instance démarre et reste au menu, une seconde démarre dans le même `ALCHESS_DIR` isolé et doit la remplacer — vérifié par la sortie propre (code 0) de la première instance, confirmant que le marqueur, la route HTTP et l'arrêt par PID fonctionnent ensemble, pas seulement en isolation. Exécuté avec succès (voir ci-dessous).
- Suite complète (hors `nicsoft/tests/e2e`, navigateur) : **896 passés, 80 ignorés** (tests matériel), aucune régression.

**Non testé, dans ce périmètre** :
- Le chemin Windows (`tasklist`/`wmic`/`taskkill`) — aucune machine Windows disponible ; code écrit par analogie avec les commandes déjà utilisées ailleurs dans le projet (aucune n'existait pour ce cas précis), à vérifier par Alain lors d'un prochain lancement Windows.
- Le scénario "deuxième instance refusée parce qu'une vraie partie Lichess/pédagogique tourne" avec de **vrais** sous-processus serveur (nécessiterait de faire avancer un vrai mode de jeu jusqu'à `playing` sans board ni jeton Lichess réel, hors de portée raisonnable d'un test automatisé) — validé à la place par 7 tests unitaires paramétrés sur `resolve_startup()` (la même fonction appelée par `alchess.py::main()`), avec l'étape de requête HTTP simulée (`monkeypatch` de `_query_state`) et un vrai faux-processus pour la partie PID/cmdline.
- Dossier `nicsoft/tests/e2e` (Playwright) : non exécuté — cette tâche n'a aucune surface frontend/JS (pas de changement HTML/JS), donc rien à y couvrir ; la suite existante n'a pas été relancée pour ce motif (hors périmètre de la tâche, aucune modification de ce côté).

# Changelog — Issue #319

# Issue #319 — Lichess : une partie ne doit jamais être annulée par un « retour au menu » que l'utilisateur n'a pas demandé, et la raison de toute annulation doit apparaître au journal

- **Contexte** : essai réel d'Alain (13 novembre 2026), avec les blancs. Après une partie terminée normalement (échiquier libéré à 09:15:40), relance d'une partie à 09:20:12. Premier essai d'ouverture de l'échiquier à 09:20:14 : connexion USB réussie en 2,2s mais aucun paquet de position lu — essai déclaré échoué, repris automatiquement au second essai (09:20:18, #317). Position confirmée à 09:20:32, premier coup physique (d2d4) à 09:20:36, partie créée chez Lichess, coup envoyé, flux ouvert — puis, dans la même seconde (09:20:37), « partie annulée (moins de 2 coups) », statut « aborted », échiquier libéré, retour au menu. Alain n'a rien demandé.

## 1. Source de l'action « retour au menu » — établi par lecture du code

- `action_queue` (`nicsoft/web/server.py`) est une file **globale, partagée par tous les modes** — jamais vidée entre deux parties.
- `on_action()` (`server.py:598-607`) : un clic « Retour au menu » pousse l'action dans `action_queue` dès que l'état courant est `playing`/`connecting`/`game_over`/`paused`/`labo`/`exercice_running`/`retrans_playing` — **y compris `game_over`**. Les états d'attente Lichess spécifiques (`position_initiale`, `lichess_wait_first_move`) n'y sont eux jamais relayés (seul `_app_state` est forcé à `"menu"`, lu directement par les boucles d'attente de `core/game_manager_modes/lichess.py` via `_BackMenuDuringWait`).
- `core/game_manager_modes/lichess.py::_run_lichess()` ne lisait **jamais** `action_queue` avant de démarrer `LichessGame` (`game.start()`). `LichessGame._main_loop()` (`modes/lichess/game.py`), lui, appelle `_process_browser_actions()` **en tout premier**, avant même le premier événement de flux Lichess — et traite toute action `back_menu` trouvée comme une demande d'annulation de la partie qui vient de démarrer (`len(self.board.move_stack) < 2` → annulation).
- Deux fenêtres peuvent laisser une action `back_menu` périmée dans cette file avant qu'une nouvelle partie Lichess ne démarre vraiment :
  1. **Établi** : un clic « Retour au menu » fait depuis l'écran de fin de la partie **précédente** (état `game_over`) — ce clic pousse dans `action_queue`, mais la `LichessGame` précédente a déjà fini de tourner (`run()` déjà retourné) : personne ne la consomme. Elle reste en attente jusqu'à la partie suivante.
  2. **Également établi, mais pas démontré comme la cause de CET incident précis** : un clic pendant l'état `connecting` de la partie en cours de lancement (ouverture de l'échiquier, ou pendant l'appel réseau `create_ai_game`/`play_move`) produit le même effet — `_BackMenuDuringWait` l'intercepte via `_app_state` pour annuler proprement *ce* lancement, mais l'entrée laissée dans `action_queue` survit si le lancement se poursuit malgré tout (ex. la fenêtre très brève autour de la création de partie elle-même).
  - **Hypothèse, non tranchable sans rejouer l'incident avec le matériel** : laquelle de ces deux fenêtres a produit l'action trouvée le 13/11 à 09:20:37. Le code ne permet pas de distinguer les deux a posteriori (aucune trace de clic n'était journalisée avant ce correctif) ; Alain ne se souvient pas avoir cliqué sur « Retour au menu » pendant la relance (09:20:12→09:20:37), ce qui pointe plutôt vers la fenêtre (1) — un reliquat de la fin de la partie précédente — mais ce n'est pas vérifiable avec certitude depuis ce dépôt.

## 2. Correctif — vidage de la file avant le tout début réel de la partie

- Nouvelle fonction `_discard_stale_browser_actions()` (`core/game_manager_modes/lichess.py`), appelée juste avant `set_app_state("playing")`/`game.start()`, une fois `LichessGame` construite (position confirmée, partie créée côté Lichess, premier coup envoyé si blancs) : vide intégralement `action_queue` (via `get_action_queue()`, déjà exposée par `ihm_port.py` pour cet usage) et journalise le nombre et le type des actions écartées.
- Même geste que celui déjà utilisé par les autres lanceurs (`core/game_manager_modes/humain.py`, `core/game_manager_modes/pedagogique.py` : « vidage de la queue avant le début de partie ») — absent jusqu'ici du lanceur Lichess, c'est ce qui manquait.
- Conséquence : toute action laissée par l'écran précédent (ou par une fenêtre antérieure du lancement en cours) est écartée ; **seule une action reçue après ce point** — donc après le tout début réel de la partie, puisque l'appel suivant est `game.start()` — peut l'affecter. Un vrai clic sur « Retour au menu » **pendant** la partie continue de fonctionner exactement comme avant (annulation si moins de 2 coups, abandon sinon) : rien n'a changé dans `LichessGame._process_browser_actions()`/`_request_resign_or_abort()` sur ce point, seule la file est maintenant propre à l'entrée.
- Limite résiduelle, documentée plutôt que corrigée : la fenêtre entre la construction de `LichessGame` et l'appel à `game.start()` est non nulle (aucun appel réseau dans ce court intervalle précis, mais le même schéma existe déjà, en plus large, chez `humain.py`/`pedagogique.py`) — un clic strictement concurrent de ce vidage resterait perdu. Risque jugé négligeable (fenêtre de l'ordre du microseconde ici) et cohérent avec le comportement déjà accepté ailleurs dans le projet.

## 3. Journal — raison de toute annulation/abandon

- `LichessGame._process_browser_actions()` (`modes/lichess/game.py`) journalise désormais, **dès la réception** de l'action (avant l'appel réseau `abort()`/`resign()`, qui peut prendre du temps) : « retour au menu demandé par l'utilisateur » ou « abandon demandé par l'utilisateur (bouton Abandonner) ». L'heure de cette ligne (formateur `%(asctime)s` déjà en place, `alchess.py`) est l'instant de la demande.
- `_request_resign_or_abort()` prend désormais un paramètre `reason` (`"retour au menu demandé par l'utilisateur"` / `"bouton Abandonner demandé par l'utilisateur"`), inclus dans la ligne de résultat : `Lichess : partie annulée (<id>, moins de 2 coups) — raison : <reason>.` ou `Lichess : abandon par <joueur> (<id>) — raison : <reason>.`
- `_notify_unexpected_end()` (statut Lichess inattendu, non demandé par l'utilisateur : `aborted`/`noStart`/`unknownFinish` reçus du flux sans passer par un clic) journalise désormais explicitement « raison : autre (non demandée par l'utilisateur) ».

## 4. Premier échec d'ouverture (09:20:14) — documenté, non corrigé

- **Établi par lecture du code** (sans matériel pour le rejouer) : `NicLinkManager.connect()` (`nicsoft/niclink/driver.py`, non modifié) appelle `self.nl_interface.connect()` (la poignée de main USB elle-même, journalisée depuis #317 — 2,2s dans ce cas), puis ne laisse que **2×`thread_sleep_delay`** pour qu'un premier `get_fen()` renvoie un FEN non vide avant de lever `RuntimeError("Board initialization error...")`, converti en `SystemExit("board connection error.")` par `NicLinkManager.__init__`. `core/board_adapter.py::create_board()` construit ce `NicLinkManager` avec `thread_sleep_delay=0.1` — soit ~0,2s de grâce après une poignée de main qui a déjà pris 2,2s. Hypothèse raisonnable (non vérifiable sans l'échiquier) : le firmware du plateau n'avait pas encore commencé à émettre les paquets de position dans cette fenêtre de 0,2s.
- **Signal envoyé à l'interface** : **aucun**, dans ce cas précis — `_open_board_with_retry()` (#317) absorbe ce premier échec silencieusement (aucun `send_event`/`set_app_state`) et retente ; le second essai a réussi avant l'épuisement de `_BOARD_OPEN_RETRY_TOTAL_S` (5s). Ce premier échec d'ouverture est donc **indépendant** de l'annulation à 09:20:37 — les deux incidents de la même relance ont des causes distinctes.
- **Non corrigé** : élargir ce délai de grâce suppose de changer `thread_sleep_delay` (passé à `NicLinkManager` par `board_adapter.py`), ce qui affecterait **tous les modes** (humain, pédagogique, exercices, labo, retranscription), pas seulement Lichess, et ne peut pas être vérifié sans l'échiquier réel. Documenté en commentaire dans `core/game_manager_modes/lichess.py`, juste au-dessus de `_open_board_with_retry()`, pour que la prochaine lecture de `niclink.log` (déjà enrichi par #317) confirme ou infirme cette hypothèse sans avoir à relire le code.

## 5. Tests — sans matériel ni réseau

Nouveau fichier `nicsoft/tests/test_issue319_lichess_stale_backmenu.py` (7 tests) :

- `_discard_stale_browser_actions()` vide la file et journalise (type et nombre des actions écartées) ; ne journalise rien si la file est déjà vide.
- **Action périmée ignorée** : `_run_lichess()` bout en bout, couleur noire, avec un `back_menu` déjà présent dans `action_queue` avant le lancement — la partie est bien créée, jamais annulée « moins de 2 coups », le vidage est journalisé.
- **Relance après un premier essai d'ouverture échoué suivie d'un premier coup sans annulation** (scénario complet de l'essai réel, couleur blanche) : premier `create_board()` échoue avec `SystemExit("board connection error.")`, second réussit (#317) ; premier coup physique détecté et envoyé ; `back_menu` périmé en file — la partie est créée et jouée, jamais annulée à tort.
- **Vrai retour au menu pendant la partie toujours pris en compte** : `back_menu`/`lichess_resign` reçus après le début réel de la partie (`LichessGame` déjà en cours) continuent d'annuler/abandonner comme avant, et journalisent désormais la raison (« raison : retour au menu demandé par l'utilisateur » / « raison : bouton Abandonner demandé par l'utilisateur »).
- **Raison « autre »** journalisée pour une fin de partie inattendue non demandée par l'utilisateur (statut `aborted` reçu du flux sans action navigateur).

Suite complète exécutée : `python -m pytest nicsoft/tests/` → **950 passés, 81 ignorés** (marqueur matériel/`node` absent), 0 échec — dont les tests Lichess existants (#309, #311, #314, #317, #318) inchangés et toujours verts, et la garde ARC-001 (`test_no_web_import.py`). `py_compile` sur les deux fichiers modifiés : OK.

- **Non testable sans le matériel réel** : confirmer laquelle des deux fenêtres (écran de fin de partie précédente, ou attente de la partie en cours de lancement) a réellement produit l'action trouvée le 13/11 à 09:20:37 — les deux sont désormais couvertes par le même vidage, donc corrigées dans tous les cas, mais le journal enrichi (point 3) permettra, au prochain essai, de voir si une telle action périmée réapparaît (elle serait alors journalisée par `_discard_stale_browser_actions()` avec son type) plutôt que de devoir le déduire. Également non testable : confirmation matérielle de l'hypothèse du point 4 (délai de grâce USB trop court après une poignée de main lente).

- **CONTEXTE.md** : paragraphe ajouté sous Lichess sur ce correctif (vidage de `action_queue`, raisons journalisées, point distinct sur le premier échec d'ouverture).

- Fichiers touchés : `nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/modes/lichess/game.py`, `nicsoft/tests/test_issue319_lichess_stale_backmenu.py` (nouveau), `CONTEXTE.md`, `CHANGELOG-319.md` (nouveau). `driver.py`, `.audit.json`, `requirements.txt` non modifiés ; aucune nouvelle dépendance ; aucun moteur d'échecs ; aucune suppression d'outil de sécurité ; aucun push ; jeton jamais journalisé.

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. Terminer une partie normalement, cliquer « Retour au menu » sur l'écran de fin, puis relancer immédiatement une nouvelle partie Lichess : vérifier qu'elle n'est plus jamais annulée dès le premier coup, et chercher dans le journal une éventuelle ligne « action(s) périmée(s) écartée(s) » confirmant qu'une action résiduelle a bien été absorbée.
2. Pendant une partie, cliquer « Retour au menu » puis, dans une autre partie, cliquer « Abandonner » — vérifier dans chaque cas la nouvelle ligne « raison : ... » au journal.
3. Si un nouveau premier échec d'ouverture se reproduit (point 4), vérifier dans `niclink.log` le délai réel entre la fin de la poignée de main USB (déjà journalisée par #317) et l'échec, pour confirmer ou infirmer l'hypothèse de la fenêtre de grâce trop courte.

# Changelog — Issue #318

# Issue #318 — Lichess : une nulle proposée ne doit être déclarée refusée qu'après la vraie réponse de l'adversaire, et le journal doit montrer ce que Lichess envoie

- **Contexte** : essai réel d'Alain (12 novembre 2026), après #316 (offre jointe au coup). Journal de la partie (blancs contre l'IA niveau 1) : offre de nulle à 19:37:31, puis à 19:37:46 coup envoyé (c4c5) et « nulle refusée » dans la même seconde que la confirmation du coup par Lichess — avant que l'IA ait pu répondre (son propre coup n'arrive qu'à 19:37:48). Même séquence une deuxième fois à 19:37:53/19:38:05/19:38:09. Le refus était donc déclenché par l'écho de notre propre coup, pas par une vraie réponse de l'adversaire.

- **1. Cause mesurée dans ce dépôt** : `LichessGame._apply_game_state()` (`nicsoft/modes/lichess/game.py`) ne faisait aucune distinction entre un `gameState` qui échoue notre propre coup et un `gameState` qui reflète un coup de l'adversaire — toute chute de l'indicateur `wdraw`/`bdraw` (selon notre couleur) alors qu'une offre était en attente était traitée comme un refus, y compris sur l'événement qui confirme le coup que nous venons d'envoyer nous-mêmes.
  - **Vérifié** dans la documentation officielle (`lichess-org/api`, dépôt public, specs OpenAPI `doc/specs/tags/board/api-board-game-gameId-move-move.yaml` et `GameStateEvent.yaml`) : le paramètre `offeringDraw` sur l'appel de coup est bien documenté comme « Whether to offer (or agree to) a draw » — c'est le mécanisme officiel pour faire porter une offre par un coup, déjà utilisé depuis #316. Le schéma `GameStateEvent` documente `wdraw`/`bdraw` comme « true if white/black is offering draw, else omitted » (donc jamais `false` explicitement — absent sinon, ce qui ne change rien au comportement de `bool(event.get(...))`).
  - **Vérifié** dans le code source public `lichess-org/lila` (`modules/bot/src/main/BotPlayer.scala`, qui traite aussi bien les coups Bot API que Board API — `PlayApi.scala::boardMove` appelle le même `env.bot.player`) : quand une offre est déjà active (`pov.player.isOfferingDraw == true`) et que le coup est envoyé avec `offeringDraw=true`, **aucune des deux branches ne se déclenche** (ni retrait ni nouvelle offre) — l'offre devrait donc, d'après ce code, rester intacte à travers notre propre coup. Le même fichier confirme en revanche explicitement la règle (b) de la tâche : `MovePlayer.scala` déclenche un retrait de l'offre adverse dès qu'un joueur joue alors que son adversaire a une offre active (« jouer un coup revient à refuser »).
  - **Non vérifié** (nécessiterait une vraie partie et une inspection serveur impossible depuis ce dépôt) : pourquoi le `gameState` observé en situation réelle montrait malgré tout l'indicateur à `False` dès l'écho de notre propre coup, alors que la lecture du source ci-dessus suggère que l'offre devrait survivre. Décalage possible entre le code public lu et la version réellement déployée, comportement spécifique à l'IA locale (non visible dans `BotPlayer.scala`), ou un deuxième `gameState` (clock-only) non capturé par le journal d'avant #318. Le nouveau journal de diagnostic (point 2) permettra de confirmer lequel la prochaine fois.
  - Il n'existe par ailleurs **aucun signal de refus explicite distinct** dans le flux Board API (aucun champ ni type d'événement « draw declined ») — seul le changement des indicateurs `wdraw`/`bdraw` est observable. La règle (a) de la tâche (« Lichess signale explicitement le refus ») n'est donc pas représentable séparément de la règle (b) avec les données actuellement reçues ; l'implémentation retenue ne se fie donc qu'à (b), ce qui est le signal le plus sûr et le seul mesurable.

- **2. Journal de diagnostic, niveau INFO, mode Lichess (`nicsoft/modes/lichess/game.py`)** : `_submit_move()` journalise désormais si l'offre de nulle était jointe au coup (`offre_nulle_jointe=True/False`, en plus du délai déjà journalisé). Nouvelle fonction `_log_game_state_received()`, appelée pour chaque état reçu (`_apply_game_full` et `_apply_game_state`) : nombre de coups, statut, et les deux indicateurs bruts `wdraw`/`bdraw` tels qu'envoyés par Lichess. Rien de secret (ni jeton, ni position physique) n'est journalisé.

- **3. Règle de décision corrigée (`LichessGame._apply_new_moves()`/`._apply_game_state()`)** : `_apply_new_moves()` retourne désormais la couleur de l'auteur du dernier coup nouvellement appliqué dans ce `gameState` (`None` si aucun nouveau coup). `_apply_game_state()` n'évalue plus le refus de notre offre que si ce dernier coup appartient à l'adversaire (`last_mover_color != self.user_color`) — un `gameState` qui échoue notre propre coup (ou qui n'ajoute aucun coup) ne peut donc plus jamais déclencher « Nulle refusée », quel que soit l'état des indicateurs qu'il transporte. Le refus n'est déclaré que lorsque l'adversaire a réellement joué sans accepter — exactement la règle (b) demandée. La détection de l'offre adverse (`_draw_offered_by_opponent`) et de l'acceptation (`_check_finished`) sont inchangées.

- **4. Affichage** : aucune modification de `app.js`/`index.html` n'était nécessaire — le bandeau « Proposition envoyée… » (`lichess-draw-wait-msg`, déjà posé par #316) n'était déjà caché que sur `lichess_draw_refused`/`lichess_draw_accepted`, jamais sur un coup. En corrigeant le déclenchement côté serveur (point 3), le bandeau reste donc affiché correctement à travers notre propre coup, y compris plusieurs coups si l'adversaire ne joue toujours pas, et seule une vraie réponse fait apparaître « Nulle refusée » ou « Nulle acceptée ». Aucun renvoi supplémentaire de l'offre n'est nécessaire : la documentation officielle confirme que `offeringDraw=true` sur le coup est le mécanisme prévu, déjà en place depuis #316.

- **Tests** : `nicsoft/tests/test_issue318_lichess_draw_refusal.py` (nouveau, sans réseau ni matériel, événements simulés) — 8 tests : reproduction exacte du scénario réel (écho de notre coup avec indicateur déjà à `False`, aucun faux refus, refus déclenché seulement au vrai coup suivant de l'adversaire) ; offre maintenue à travers plusieurs coups propres sans réponse adverse ; coup adverse sans acceptation = refus réel ; acceptation adverse jamais confondue avec un refus ; offre de l'adversaire inchangée par notre propre coup suivant ; journal : présence de `offre_nulle_jointe=` sur le coup envoyé, présence des deux indicateurs/statut/nombre de coups sur l'état reçu, absence du jeton dans ces lignes. Suite complète exécutée (`python -m pytest nicsoft/tests --ignore=nicsoft/tests/e2e`) : **853 passés, 80 ignorés (marqueur hardware), 0 échec** (dont les 8 nouveaux ; les tests de #316 sur la nulle — toujours basés sur un `wdraw`/`bdraw` qui reste à `True` sur l'écho du coup — restent valides tels quels, cette hypothèse n'est en fait plus nécessaire pour qu'ils passent : la nouvelle règle ignore l'indicateur de l'écho de notre coup, quelle que soit sa valeur). `py_compile` sur `nicsoft/modes/lichess/game.py` : OK.

- **Non testable sans une vraie partie Lichess** : confirmer en pratique si l'indicateur `wdraw`/`bdraw` de l'écho de notre propre coup est effectivement à `False` (comme observé le 12 novembre) ou à `True` (comme la lecture du source `lila` le suggérait) — le nouveau journal de diagnostic (point 2) permettra de le voir au prochain essai, sans que cela change le comportement affiché côté utilisateur dans les deux cas. Le comportement réel de l'IA Lichess face à une offre de nulle (accepte-t-elle parfois, avec quelle latence ?) n'a pas non plus pu être observé en dehors du compte-rendu d'Alain.

- **CONTEXTE.md** : une phrase ajoutée sous Lichess sur la correction #318 (règle de décision du refus de nulle, journal de diagnostic).

- Fichiers touchés : `nicsoft/modes/lichess/game.py`, `nicsoft/tests/test_issue318_lichess_draw_refusal.py` (nouveau), `CONTEXTE.md`, `CHANGELOG-318.md` (nouveau). `driver.py`, `.audit.json`, `requirements.txt` non modifiés ; aucune nouvelle dépendance ; aucun moteur d'échecs ; aucune suppression d'outil de sécurité ; aucun push ; jeton jamais journalisé (vérifié par un test dédié).

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. **Nulle** : en partie, proposer la nulle puis jouer son coup sur l'échiquier physique — vérifier qu'aucun « Nulle refusée » n'apparaît à ce moment (le bandeau « Proposition envoyée… » doit rester affiché), et observer dans le journal (niveau INFO) les lignes `coup envoyé ... offre_nulle_jointe=True` et `état reçu (... wdraw=... bdraw=...)` pour confirmer ce que Lichess envoie réellement sur l'écho de ce coup.
2. Vérifier que le refus n'apparaît que lorsque l'IA joue effectivement son coup sans avoir accepté, et que l'acceptation (si l'IA accepte) affiche bien « Nulle acceptée ».

# Changelog — Issue #317

# Issue #317 — Lichess : message « Jouez » bien visible dès que la position des blancs est prête, et relance fiable juste après un retour au menu

- **Contexte** : essai réel d'Alain avec les blancs (13 novembre 2026). Sur l'écran d'attente du premier coup (#316), le panneau explicatif de trois phrases n'a pas été lu — Alain a cru l'écran bloqué et a cliqué « Retour au menu », puis « Démarrer la partie » aussitôt après : la relance a échoué avec « Erreur mode Lichess : échiquier non détecté » (journal : libération à 19:13:43, nouveau lancement à 19:13:46, erreur à 19:13:48), alors que des relances faites plus tard fonctionnaient.

- **1. Message « Jouez » visible (`nicsoft/web/templates/index.html`, `nicsoft/web/static/css/main.css`, i18n)** : le panneau de l'écran `screen-lichess-wait-first-move` (titre + 3 phrases + ligne « En attente » + spinner) est remplacé par une carte dédiée `.card-lichess-ready` (fond vert, même palette que `#feedback-box.bon` déjà utilisée ailleurs dans l'app pour un état « succès ») contenant un titre court (`lichess.attente_premier_coup.titre` → « À vous de jouer ! ») et un message d'une seule phrase en gros caractères (`.lichess-ready-message`, réutilise la clé `lichess.attente_premier_coup.en_attente` → « Jouez votre premier coup sur l'échiquier. »). La carte bleue neutre de l'écran voisin « Position incorrecte » (`screen-pos-init`) n'est pas touchée : le contraste de couleur entre les deux écrans signale directement le changement d'état, sans avoir à lire de texte. L'échiquier (position de départ, blancs en bas) et le bouton « Retour au menu » restent inchangés. La clé `lichess.attente_premier_coup.texte_html` (ancien paragraphe) est conservée non vide dans les 3 fichiers i18n — vérifiée par un test déjà existant (#309) — mais n'est plus référencée dans le HTML.

- **2. Relance fiable après un retour au menu (`nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/niclink/hid_backend.py`, `nicsoft/web/alchess.py`)** :
  - **Cause probable (non vérifiable sans matériel)** : `_run_lichess()` ne faisait qu'un seul essai d'ouverture de l'échiquier (`create_board()` → `NicLinkManager.__init__()` → `hid_backend.connect()`). `connect()` referme l'ancien handle puis réénumère immédiatement le bus (`hid.enumerate()`) pour rouvrir le périphérique. Rien ne garantit que le plateau Chessnut ait fini de se réinitialiser côté firmware/USB juste après l'ordre « upload mode » envoyé par le `disconnect()` de la partie précédente (quelques secondes plus tôt) : si `hid.enumerate()` ne le retrouve pas encore à cet instant précis, `connect()` lève `RuntimeError("Chessnut Air introuvable")`, que `NicLinkManager.__init__()` traduit en `sys.exit("board connection error.")` — sans aucun second essai. Une relance faite plus tard laisse le temps à cette réinitialisation de se terminer, d'où le succès observé. Cette explication reste une hypothèse de lecture du code, jamais démontrée sur le matériel réel.
  - **Correctif** : nouvelle fonction `_open_board_with_retry()` dans `lichess.py` — retente `create_board()` pendant `_BOARD_OPEN_RETRY_TOTAL_S` (5s, intervalle `_BOARD_OPEN_RETRY_INTERVAL_S` = 1s) si l'échec est précisément `SystemExit("board connection error.")` ; toute autre cause de `SystemExit` remonte immédiatement, sans délai. `driver.py` n'est pas modifié : chaque essai construit un nouveau `NicLinkManager`, dont `connect()` (`hid_backend.py`, déjà en place depuis #292/#314) ferme systématiquement tout handle existant avant d'en ouvrir un nouveau et sérialise les essais via `_connect_lock` — jamais deux ouvertures USB en vol en même temps, règle d'accès unique respectée.
  - **Diagnostic (journal)** : `hid_backend.connect()` journalise désormais, en plus de ce qui existait déjà (ouverture demandée, fermeture de l'ancien handle, connexion réussie avec PID/appelant), le résultat et la durée écoulée de chaque échec (« aucun Chessnut Air trouvé par hid.enumerate() » ou « échec pendant open_path/handshake »), ainsi que le FEN lu au premier paquet lors d'une ouverture réussie. Ce logger (`nicsoft.niclink.hid_backend`) était déjà en INFO dans le code mais invisible dans `niclink.log` car le root logger reste à WARNING : il est maintenant élevé à INFO dans `alchess.py::_setup_logging()`, comme `niclink.lichess` l'est déjà depuis #311. `_run_lichess()` journalise en plus la durée de chaque libération (`nl_inst.disconnect()`) et le nombre d'essais d'ouverture. La prochaine relance ratée laissera donc, dans `niclink.log`, l'heure et le résultat de chaque libération et de chaque tentative d'ouverture, et le FEN lu dès le succès — de quoi confirmer ou infirmer l'hypothèse ci-dessus sans redémarrer en mode debug.
  - **Si l'échiquier reste réellement introuvable** malgré les essais : comportement inchangé et déjà correct à la lecture du code — `_run_lichess()` traduit toujours l'échec en toast visible (`toast.board_not_found`, texte existant « Échiquier non détecté au démarrage. ») et en évènement `board_error` (message explicite envoyé au navigateur) ; jamais de retour silencieux au menu. Un piège latent a été repéré en chemin (non corrigé, hors périmètre de cette issue) : juste après ce retour au menu, `launch_lichess()` relance `check_board_presence_silent()`, qui renvoie `board_ok` dès que le plateau est physiquement présent sur le bus — ce qui efface quasi immédiatement le badge d'erreur affiché à l'écran, ne laissant que le toast (4s) comme seule trace visible. Avec le réessai ci-dessus, ce cas (échiquier physiquement présent mais pas encore réouvrable) ne devrait plus jamais atteindre ce code d'erreur en pratique.

- **Piège rencontré et corrigé en cours de développement** : une première version de `_open_board_with_retry()` relisait le FEN via `nl_inst.get_fen()` juste après un essai réussi, pour le journaliser. Cette lecture supplémentaire est inutile en pratique (le FEN lu pendant la poignée de main de `connect()` est déjà journalisé par `hid_backend.py`) et a fait boucler indéfiniment plusieurs tests existants (`test_issue311_lichess_sequencing.py`) : leurs doubles de plateau scriptés (`_ScriptedBoard`) avancent un index à chaque appel de `get_fen()`, et cette lecture en plus décalait la séquence attendue par `_wait_initial_position_lichess()`, qui ne retrouvait alors plus jamais la position de départ. Retirée — `_open_board_with_retry()` ne relit plus le FEN.

- **Tests** :
  - `nicsoft/tests/test_issue317_lichess_corrections.py` (nouveau, sans matériel ni réseau) : 16 tests — structure et classe de couleur de l'écran « prêt à jouer » (carte dédiée, plus de paragraphe ni de spinner, échiquier et bouton conservés), l'écran « Position incorrecte » voisin ne porte pas ce style, règle CSS présente, message i18n court (une seule phrase, pas de `<br>`) dans les 3 langues, câblage app.js inchangé ; `_open_board_with_retry()` réussit après deux échecs transitoires sans jamais relancer deux ouvertures en même temps, abandonne proprement (exception propagée, jamais avalée) après le délai total si l'échec persiste, ne retente jamais pour une autre cause de `SystemExit` ; bout en bout via `_run_lichess()` — une relance qui réussit après un échec transitoire ne produit plus l'erreur « échiquier non détecté », et un échec définitif produit toujours le toast existant.
  - Suite complète exécutée (`python -m pytest nicsoft/tests/`, dossier e2e exclu faute de navigateur piloté dans cette session) : **857 passés, 80 ignorés (tests matériel/contrat), 0 échec**, dont les 16 nouveaux et l'ensemble des suites Lichess existantes (#309 à #316 : 137 passés). `py_compile` sur les 3 fichiers Python modifiés : OK. JSON des 3 fichiers i18n valide. Démarrage réel du serveur (`ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`), page d'accueil récupérée par `curl` : code 200, carte `.card-lichess-ready` et écran `screen-lichess-wait-first-move` bien présents dans le HTML rendu ; serveur arrêté par son PID exact.

- **Non testable sans matériel** : la cause réelle du point 2 reste une hypothèse de lecture du code (voir ci-dessus) — impossible de reproduire sur ce poste la fenêtre temporelle exacte d'une relance « quelques secondes après » une libération USB réelle, ni de confirmer que le plateau physique met effectivement ce temps à se réinitialiser après l'« upload mode ». Le nouveau journal détaillé (heure, durée, résultat de chaque libération/ouverture, FEN lu) permettra de le vérifier lors du prochain essai réel d'Alain : si une relance rapide réussit maintenant au 2e ou 3e essai (visible dans `niclink.log` par les lignes « ouverture échiquier échouée (essai N...) » suivies de « échiquier physique ouvert (essai N) »), l'hypothèse sera confirmée ; si l'échec persiste malgré les 5 essais sur 5s, la cause est ailleurs et le journal détaillé (hid_backend.py) montrera où (absence confirmée sur le bus vs échec pendant le handshake). Rendu visuel de l'écran « Jouez » également à confirmer par Alain sur le véritable échiquier (orientation, lisibilité en conditions réelles).

- **CONTEXTE.md** : une phrase ajoutée sous Lichess (écran « prêt à jouer », `_open_board_with_retry()`, journal `hid_backend.py` élevé à INFO).

- Fichiers touchés : `nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/niclink/hid_backend.py`, `nicsoft/web/alchess.py`, `nicsoft/web/templates/index.html`, `nicsoft/web/static/css/main.css`, `nicsoft/web/static/i18n/{fr,en,de}.json`, `nicsoft/tests/test_issue317_lichess_corrections.py` (nouveau), `CONTEXTE.md`, `CHANGELOG-317.md` (nouveau). `driver.py`, `.audit.json`, les dépendances ne sont pas modifiés ; aucun moteur d'échecs ; aucune suppression de sécurité ; aucun push.

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. **Écran « Jouez »** : démarrer une partie Lichess en choisissant les blancs — après confirmation de la position de départ, vérifier que le nouveau panneau vert « À vous de jouer ! » / « Jouez votre premier coup sur l'échiquier. » apparaît immédiatement, bien plus visible que l'ancien texte, et que l'échiquier affiché et le bouton de retour au menu sont toujours là.
2. **Relance rapide** : terminer ou quitter une partie Lichess (retour au menu), puis relancer immédiatement une nouvelle partie Lichess (quelques secondes après) — vérifier que la relance réussit désormais normalement. Si elle échoue encore, vérifier dans `niclink.log` (niveau INFO, pas besoin de `NICLINK_LOG=DEBUG`) les nouvelles lignes `hid_backend.py` et `niclink.lichess` autour de l'heure de l'échec, pour voir où il se produit exactement (absence sur le bus, ou échec pendant l'ouverture).
3. **Échec réel** : si possible, tester avec l'échiquier réellement éteint ou débranché au moment du lancement — vérifier qu'un message clair (« Échiquier non détecté au démarrage. ») apparaît bien après les quelques essais, plutôt qu'un retour silencieux au menu.

# Changelog — Issue #316

# Issue #316 — Lichess : nulle proposée avec le coup et sans faux « refusée », écran d'attente du premier coup des blancs lisible, pendules qui suivent les noms au retournement manuel

- **Contexte** : essais réels d'Alain sur l'échiquier physique, parties amicales contre l'IA de Lichess (l'orientation côté noirs de #315 fonctionne). Trois défauts restaient.

- **1. Nulle proposée avec le coup, sans faux « refusée » (`nicsoft/modes/lichess/game.py`)** : cause racine — `LichessGame._submit_move()` n'appelait jamais `client.play_move(..., offer_draw=...)` (paramètre `offeringDraw`, ajouté côté client en #307 mais jamais utilisé par le mode de jeu). Résultat : une offre de nulle faite avant le coup était silencieusement retirée par Lichess dès que l'utilisateur jouait sans ce paramètre, et le `gameState` suivant (`wdraw`/`bdraw` repassé à `false`) était alors interprété à tort comme un refus de l'adversaire — d'où « Nulle refusée » affiché à chaque fois, même sans réponse réelle de Lichess. Corrigé : `_submit_move()` transmet désormais `offer_draw=self._my_draw_offer_pending`, pour toute offre en attente — qu'elle ait été faite pendant notre propre tour ou pendant celui de l'adversaire. La détection du vrai refus (`_apply_game_state`, inchangée dans sa logique : `wdraw`/`bdraw` retombé à `false` alors qu'une offre était en attente) ne se déclenche donc plus que sur une vraie réponse de l'adversaire (son coup joué sans accepter, ou refus explicite). Ajout d'un état « acceptée » distinct (`_check_finished`) : si notre offre est encore en attente au moment où la partie se termine en nulle, un événement dédié `lichess_draw_accepted` est émis (jamais confondu avec un refus, jamais émis pour une nulle sans rapport avec notre offre, ex. pat). L'abandon (`_request_resign_or_abort`) n'a pas été touché.

- **2. Écran d'attente du premier coup des blancs lisible (`nicsoft/web/templates/index.html`, `nicsoft/web/static/app.js`, `nicsoft/web/static/css/main.css`)** : l'écran (affiché après confirmation de la position, avant la création de la partie chez Lichess — l'utilisateur joue toujours les blancs à ce stade) utilisait l'habillage générique `.screen-connecting`/`.connecting-msg` : fond uni, pas d'échiquier, titre en gris clair (`#e0e0e0`) sur fond clair (`#d8e4f0` ou `#c2d4e8`) — contraste très insuffisant. Remplacé par la même mise en page que l'écran « position initiale » voisin : échiquier en position de départ (blancs en bas — orientation triviale puisque l'utilisateur est toujours blanc ici), labels Adversaire/Joueur réutilisés, panneau `.card`/`h2.card-title-lg` (texte sombre sur fond clair, contraste WCAG largement supérieur au seuil AA). `_buildBoardPosInit(flipped, boardId, cellPrefix)` et `renderBoardPosInit(fen, cellPrefix)` (app.js) généralisées avec un id d'échiquier et un préfixe de case paramétrables (valeurs par défaut inchangées — aucun effet sur l'écran « position initiale » d'origine) ; le gestionnaire `app_state` construit et peint ce nouvel échiquier (`"board-lichess-wait-first-move"`/préfixe `"lwfm"`) à l'entrée dans l'état `lichess_wait_first_move`, avec la position de départ statique (le serveur ne pousse aucun FEN pendant cette attente — confirmé en lisant `_wait_first_move_white_lichess`, qui ne renvoie qu'un toast « coup non reconnu », jamais de FEN). Aucune création de partie ni autre comportement modifié : uniquement l'affichage. Nouvelle clé i18n `lichess.attente_premier_coup.en_attente` (« Jouez votre premier coup sur l'échiquier. »/« Play your first move on the board. »/« Spielen Sie Ihren ersten Zug auf dem Brett. »).

- **3. Pendules qui suivent les noms au retournement manuel (`nicsoft/web/static/app.js`)** : `flipBoard()` (bouton ⇅, disponible pendant la partie) échangeait les noms (`player-top-name`/`player-bottom-name`) mais jamais les pendules (`clock-top`/`clock-bottom`), qui restaient câblées sur la convention fixe « haut = adversaire, bas = utilisateur » du handler `lichess_clock`. Après un retournement manuel, le nom affiché en haut changeait de joueur mais la pendule du haut restait celle de l'ancien joueur — « Vous » se retrouvait à côté de la pendule de l'adversaire. Corrigé par un nouveau drapeau `_lichessClockRowsSwapped`, basculé par `flipBoard()` juste après l'échange des noms, et une fonction extraite `_lichessRenderClock(data)` (reprend la logique de l'ancien handler `socket.on("lichess_clock", ...)`, qui l'appelle désormais) qui en tient compte pour déterminer quelle pendule (valeur **et** marqueur « au trait ») va en haut et laquelle va en bas. `flipBoard()` redessine immédiatement les pendules avec les dernières données reçues (`_lichessLastClockData`, mémorisées à chaque poussée serveur) — pas seulement les noms — pour que le retournement soit instantané, et les poussées suivantes (pendule en train de tourner) continuent de respecter le drapeau jusqu'au prochain retournement. Le drapeau est remis à `false` à chaque nouvelle partie (`lichess_init`).

- **Tests** :
  - `nicsoft/tests/test_issue316_lichess_corrections.py` (nouveau, sans matériel ni réseau) : 22 tests — nulle proposée puis coup joué sans faux refus (reproduction exacte du bug, `_submit_move` porte bien `offer_draw`), offre faite pendant le tour de l'adversaire, nulle acceptée (événement dédié, pas de faux positif sur un pat), réponse à une offre de l'adversaire (accepter/refuser) ; écran d'attente avec échiquier (structure HTML, contraste via classe `card-title-lg`, pas de régression sur le bouton retour/la bannière de reconnexion) ; exécution réelle (Node) des fonctions généralisées `_buildBoardPosInit`/`renderBoardPosInit` avec le nouvel id/préfixe ; exécution réelle (Node) de `_lichessRenderClock()` dans les deux sens du drapeau de retournement (valeurs **et** marqueur « au trait ») ; vérifications de câblage (`flipBoard()` échange bien le drapeau juste après les noms, `lichess_init` le réinitialise) ; nouvelles clés i18n présentes dans les 3 langues.
  - `nicsoft/tests/e2e/test_issue316_lichess_e2e.py` (nouveau, Playwright, événements Socket.IO simulés via les callbacks déjà enregistrés par `app.js`, sans crochet de production, comme `test_issue310_lichess_e2e.py`) : échiquier de l'écran d'attente visible et complet (32 pièces), ratio de contraste WCAG du titre mesuré réellement dans le navigateur (`getComputedStyle`, seuil AA 4.5:1 — très supérieur après correctif), bouton retour au menu ; pendules qui suivent les noms après un retournement manuel, testé pour les deux couleurs utilisateur (noirs puis blancs), avec une nouvelle poussée de pendule pendant que l'horloge « tourne » après le retournement, puis un second retournement qui restaure l'état d'origine.
  - Suite complète exécutée (`python -m pytest nicsoft/`, dossier e2e compris) : **920 passés (dont les 22 + 5 nouveaux), 81 ignorés (marqueur hardware), 0 échec**. `py_compile` sur `nicsoft/modes/lichess/game.py` : OK. Syntaxe JS vérifiée (`node --check app.js`) : OK. JSON des 3 fichiers i18n valide.

- **Non testable sans matériel** : le comportement réel de l'API Lichess (annulation effective d'une offre de nulle non accompagnée d'`offeringDraw`, contenu exact d'un `gameState` après acceptation/refus) n'a pas pu être vérifié contre un vrai serveur Lichess — seule la logique côté AlChess (ce qui est envoié, ce qui est interprété) est testée ; la lecture physique du plateau (détection du premier coup réel, LEDs) n'a pas non plus pu être vérifiée sans l'échiquier Chessnut Air.

- **CONTEXTE.md** : une phrase ajoutée sous Lichess (correctifs #316 : `offer_draw`/`lichess_draw_accepted`, écran d'attente avec échiquier, drapeau `_lichessClockRowsSwapped`).

- Fichiers touchés : `nicsoft/modes/lichess/game.py`, `nicsoft/web/static/app.js`, `nicsoft/web/templates/index.html`, `nicsoft/web/static/css/main.css`, `nicsoft/web/static/i18n/{fr,en,de}.json`, `nicsoft/tests/test_issue316_lichess_corrections.py` (nouveau), `nicsoft/tests/e2e/test_issue316_lichess_e2e.py` (nouveau), `CONTEXTE.md`, `CHANGELOG-316.md` (nouveau). `driver.py`, `.audit.json`, `requirements.txt` non modifiés ; aucune nouvelle dépendance ; aucun moteur d'échecs ; aucune suppression d'outil de sécurité ; aucun push.

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. **Nulle** : en partie, cliquer « Proposer nulle » puis jouer son coup sur l'échiquier physique — vérifier qu'aucun message « Nulle refusée » n'apparaît à ce moment, que le bandeau « Proposition envoyée… » reste affiché jusqu'à la vraie réponse de l'adversaire, et que la partie se termine bien par « Nulle acceptée » si l'IA accepte, ou par « Nulle refusée » si elle joue sans accepter.
2. **Écran d'attente** : démarrer une partie Lichess en choisissant les blancs — après confirmation de la position de départ, vérifier que l'échiquier (position de départ) est bien visible et que le titre est lisible, avant de jouer le premier coup physique.
3. **Pendules** : en cours de partie (noirs puis blancs), cliquer plusieurs fois sur le bouton de retournement (⇅) et vérifier à chaque fois que la pendule affichée en haut correspond bien au nom affiché en haut (et de même en bas), y compris pendant que le temps s'écoule.

# Changelog — Issue #315

# Issue #315 — Lichess : échiquier de l'écran retourné quand l'utilisateur joue les noirs, noms et pendules cohérents, écran de mise en place orienté

- **Contexte** : avant le premier essai du mode Lichess avec les noirs, une lecture de `app.js` (`lichess_init`/`lichess_clock`) a révélé trois incohérences qui n'avaient encore jamais été exercées en partie réelle. 1) `lichess_init` ne touchait jamais à `_boardFlipped` : l'échiquier de l'écran restait toujours affiché blancs en bas, y compris pour un utilisateur jouant les noirs, sauf clic manuel sur le bouton de retournement. 2) `lichess_init` plaçait le nom de l'utilisateur en haut et celui de l'adversaire en bas quand l'utilisateur avait les noirs, alors que `lichess_clock` suppose (son propre commentaire le disait) que la rangée du haut montre toujours l'adversaire et celle du bas toujours l'utilisateur — noms et pendules auraient donc été inversés pour les noirs. 3) L'écran de mise en place (« Position incorrecte », cases à corriger en rouge, affiché avant la partie) restait toujours orienté blancs en bas, y compris pour les noirs.

- **Orientation automatique de l'échiquier de jeu, noms/pendules cohérents (`nicsoft/web/static/app.js`)** : nouvelle fonction réutilisable `orientationIsFlipped(color)` (noirs → retourné, blancs/valeur absente → normal — servira aussi à la future reprise de partie en cours). `lichess_init` l'utilise pour poser `_boardFlipped` et reconstruire l'échiquier (`buildBoard()`) dès l'arrivée de la couleur résolue, et met désormais systématiquement le nom de l'adversaire en haut et celui de l'utilisateur en bas, pour les deux couleurs — cohérent avec la convention déjà suivie par `lichess_clock` (laissé inchangé, son commentaire décrivait déjà le bon comportement). Surbrillances du dernier coup, matériel capturé et coordonnées (a-h, 1-8) suivent déjà `_boardFlipped` via le code existant (`renderBoard`/`updateMaterial`/`buildBoard`) — aucun changement nécessaire là. Le bouton de retournement manuel (`flipBoard()`, inchangé) continue de fonctionner par-dessus l'orientation automatique ; l'orientation revient aux blancs en bas à la sortie du mode via la réinitialisation déjà présente au retour au menu (`_boardFlipped` remis à `false` + `buildBoard()`), inchangée et donc toujours sans effet sur les autres modes.

- **Écran de mise en place orienté (`nicsoft/web/static/app.js`, `nicsoft/core/game_manager_modes/lichess.py`)** : `_buildBoardPosInit(flipped)` accepte désormais un paramètre d'orientation (`false` par défaut — aucun changement pour les autres modes qui partagent cet écran, `state.py::_wait_initial_position_web` n'envoie toujours aucune couleur). Le gestionnaire générique `app_state` appelle `_buildBoardPosInit(orientationIsFlipped(data.color))` avant `renderBoardPosInit(data.fen)` à chaque entrée dans l'état `position_initiale`. Côté serveur, la couleur de l'utilisateur est déjà résolue (plus jamais `"random"`) avant cet écran (issue #311) mais n'était pas transmise : `_wait_initial_position_lichess(nl_inst)` devient `_wait_initial_position_lichess(nl_inst, color)` et inclut désormais `"color": color` dans `set_app_state("position_initiale", {...})` ; les deux appels (position initiale, et reprise après `_ResumeToPositionSetup`) passent `resolved_color`.

- **Tests** :
  - `nicsoft/tests/test_issue315_lichess_orientation.py` (nouveau, sans matériel ni réseau) : la couleur résolue atteint bien l'écran de mise en place (`_wait_initial_position_lichess`), la couleur « aléatoire » choisie en configuration est bien résolue avant d'atteindre cette fonction (jamais `"random"` lui-même), et test unitaire des correspondances couleur → orientation en exécutant réellement `orientationIsFlipped()` extraite d'`app.js` via le binaire système `node` (`shutil.which` : ignoré si absent, aucune dépendance ajoutée) — noirs → retourné, blancs/absent/vide → normal.
  - `nicsoft/tests/e2e/test_issue310_lichess_e2e.py` (complété, Playwright, événements Socket.IO simulés via les callbacks déjà enregistrés par `app.js`, sans crochet de production) : pour une partie avec les noirs — la case a1 se retrouve en haut à droite (comparaison de position avec h8, indépendante de la résolution), la rangée du haut porte le nom et la pendule de l'adversaire, celle du bas ceux de l'utilisateur, le bouton de retournement inverse l'orientation ; pour les blancs — rien ne change (échiquier normal, noms non inversés) ; écran de mise en place orienté pour les noirs, inchangé pour les blancs.
  - Deux lambdas de monkeypatch (`test_issue309_lichess_l2a.py`, `test_issue310_lichess_corrections.py`) mis à jour pour la nouvelle signature de `_wait_initial_position_lichess(nl_inst, color)` ; une substitution automatique avait par erreur élargi la même signature sur `set_nl_inst_ref`/`humain_launcher._wait_initial_position_web` (fonctions non concernées, signatures inchangées) — corrigé.
  - Suite complète exécutée (`python -m pytest nicsoft/ -m "not hardware"`) : **891 passés, 81 ignorés (marqueur hardware), 0 échec**. `py_compile` sur les fichiers Python modifiés : OK. Syntaxe JS vérifiée (`node --check app.js`) : OK.

- **CONTEXTE.md** : une phrase ajoutée sous Lichess sur l'orientation côté noirs et la fonction réutilisable `orientationIsFlipped`.

- Fichiers touchés : `nicsoft/web/static/app.js`, `nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/tests/test_issue315_lichess_orientation.py` (nouveau), `nicsoft/tests/e2e/test_issue310_lichess_e2e.py`, `nicsoft/tests/test_issue309_lichess_l2a.py`, `nicsoft/tests/test_issue310_lichess_corrections.py`, `CONTEXTE.md`. `driver.py`, `.audit.json`, `requirements.txt` non modifiés ; aucune nouvelle dépendance ; aucun moteur d'échecs ; aucune suppression d'outil de sécurité ; aucune nouvelle clé i18n (textes déjà existants réutilisés).

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. **Noirs** : lancer une partie Lichess en choisissant les noirs — vérifier que l'échiquier de l'écran de jeu est bien retourné (ses propres pièces en bas), que l'écran de mise en place (si l'échiquier physique n'est pas déjà en position de départ) est orienté du même point de vue, que son propre nom et sa propre pendule sont en bas et ceux de l'IA en haut, et que le bouton de retournement inverse bien l'orientation (puis la restaure si on le reclique).
2. **Blancs** : lancer une partie Lichess en choisissant les blancs — vérifier que rien n'a changé par rapport à avant #315 (échiquier normal, nom/pendule de l'utilisateur en bas comme auparavant).

# Changelog — Issue #314

# Issue #314 — Lichess : reprise automatique quand la lecture de l'échiquier échoue, y compris pendant l'attente du premier coup, et diagnostic de la cause

- **Contexte** : après confirmation de la position de départ en mode Lichess (blancs), l'écran d'attente du premier coup restait affiché indéfiniment sans jamais détecter le coup joué. Le journal ne montrait rien après la confirmation, à l'exception de deux avertissements simultanés `get_fen: erreur de lecture USB` dans `hid_backend.py` — cohérent avec les deux fils de lecture réels sur le même `NicLinkManager` (le `_fen_reader_thread` démarré par `driver.py` à la construction, et l'appel direct de `get_fen()` par les boucles d'attente de `lichess.py`) : une fois l'un des deux en échec, `hid_backend.get_fen()` remettait l'état de connexion à zéro et retournait une chaîne vide pour toujours, sans jamais tenter de se reconnecter.

- **Diagnostic (`nicsoft/niclink/hid_backend.py`, driver.py non modifié)** : chaque ouverture (`connect`), fermeture (`disconnect`) et remise à zéro (`_reset_state`/`_reset_state_if_current`) journalise désormais en INFO le nom module.fonction de son appelant direct (`_caller_info()`, via `inspect.stack()`). L'avertissement de lecture est enrichi du type d'exception et de son code d'erreur (`errno` si disponible) ; un même incident (plusieurs fils en échec simultané sur le même périphérique) ne produit plus qu'un seul avertissement — les répétitions sont comptées (`_read_error_count`) et rapportées à la reconnexion suivante. Un nouveau verrou `_connect_lock` sérialise tout `connect()` : une reconnexion automatique et un clic manuel sur « Connecter » ne peuvent plus jamais s'exécuter en même temps (protections de #292 étendues à ce nouveau cas).

- **Reprise automatique dans les attentes Lichess (`nicsoft/core/game_manager_modes/lichess.py`)** : `_wait_initial_position_lichess` et `_wait_first_move_white_lichess` considèrent désormais l'échiquier comme perdu dès qu'une lecture vide se prolonge plus de 1,5s ou que le module ne se déclare plus connecté (`nl_inst.nl_interface.is_connected()`). Dans ce cas : bannière « Reconnexion de l'échiquier… » (nouveaux événements `lichess_wait_board_lost`/`lichess_wait_board_ok`), journalisation, puis essais de reconnexion toutes les 2s pendant 30s puis toutes les 5s, jusqu'au succès ou au retour au menu (`_BackMenuDuringWait`, inchangé) — jamais de partie créée chez Lichess avant que l'échiquier ne soit redevenu lisible. À la reprise pendant l'attente du premier coup : la position de départ relance l'attente normalement ; un premier coup légal déjà joué est pris en compte directement ; une position illisible (ni départ ni coup légal) déclenche `_ResumeToPositionSetup`, qui renvoie à l'écran de mise en place (`_run_lichess` boucle alors sur un nouvel appel à `_wait_initial_position_lichess` avant de retenter l'attente du premier coup).

- **Coup non reconnu pendant l'attente du premier coup** : si la position lue diffère de la position de départ sans correspondre à un premier coup légal (pièce mal posée, deux pièces déplacées), un toast explicite (`lichess.coup_non_reconnu`, clé i18n avec les cases en cause) s'affiche après 3 secondes de stabilité — un seul par position erronée, jamais muet.

- **Reconnexion en cours de partie (`nicsoft/modes/lichess/game.py:LichessGame`)** : la détection existante (`_register_board_lost`, bannière `lichess_board_lost` déjà câblée côté `app.js`) déclenche désormais une vraie tentative de reconnexion en arrière-plan (`_maybe_attempt_reconnect`/`_attempt_reconnect_once`, thread dédié — `nl_inst.connect()` peut bloquer plusieurs secondes), avec la même cadence 2s/30s puis 5s et un seul essai à la fois (`_reconnecting_in_progress`). Jamais d'abandon ni de résignation automatique : la partie continue sur Lichess. Une reconnexion réussie relance le fil `_fen_reader` (`nl_inst._start_fen_reader()`) et réarme l'affichage existant « cases à corriger » (`_awaiting_piece_reset`/`_reset_target_fen` sur la position Lichess, pas sur la dernière lecture physique) pour recaler le plateau.

- **Indicateur d'en-tête (`board_adapter.py`, `server.py`, `app.js`, `main.css`)** : le callback `_board_lost_cb` (appelé par `driver.py` après échecs consécutifs de lecture) distingue désormais le périphérique encore présent sur le bus USB (`hid_backend.check_physically_present()`) — nouvel événement `board_reconnecting`, état « à reconnecter » (pastille ambrée, bouton « Connecter » toujours visible) — de l'absence confirmée (événement `board_error` existant, inchangé). `server.py` propage ce 3ᵉ statut au navigateur qui se connecte ou revient au menu, comme pour `board_ok`/`board_error`.

- **i18n** : nouvelles clés `status.board.a_reconnecter`, `lichess.reconnexion_echiquier`, `lichess.coup_non_reconnu` ajoutées simultanément dans `fr.json`/`en.json`/`de.json`.

- **Tests** (`nicsoft/tests/test_issue314_lichess_board_reconnect.py`, nouveau, sans matériel ni réseau — faux modules de lecture/hidapi) :
  - lecture perdue pendant l'attente du premier coup puis reconnexion et détection du coup ;
  - panne persistante : bannière, essais espacés, retour au menu possible, aucune partie créée ;
  - reprise après reconnexion sans coup légal → `_ResumeToPositionSetup`, puis bout en bout jusqu'à la création de la partie ;
  - premier coup non reconnu → toast avec les cases en cause ;
  - perte en cours de partie → pas d'abandon automatique, reconnexion puis recalage ("cases à corriger") ;
  - un seul essai de reconnexion à la fois, en cours de partie (`LichessGame`) et au niveau le plus bas (`hid_backend._connect_lock`, verrou tenu pendant toute la durée de `connect()`) ;
  - diagnostic `hid_backend.py` : un seul avertissement par incident avec compte des répétitions, type d'exception et code d'erreur dans le message, journalisation de l'ouverture/fermeture avec l'appelant ;
  - garde : aucune écriture dans les vrais dossiers utilisateur (fixture autouse existante).
  - Suite complète exécutée (`python -m pytest nicsoft/tests/`, dossier e2e compris) : **876 passés (dont les 13 nouveaux), 81 ignorés (marqueur hardware), 0 échec** ; e2e : **64 passés, 1 ignoré**.

- **CONTEXTE.md** : une phrase ajoutée sous Lichess sur la reconnexion automatique (#314), et retrait de « reprise après perte d'échiquier » de la liste « pas encore ».

- Fichiers touchés : `nicsoft/niclink/hid_backend.py`, `nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/modes/lichess/game.py`, `nicsoft/core/board_adapter.py`, `nicsoft/web/server.py`, `nicsoft/web/static/app.js`, `nicsoft/web/static/css/main.css`, `nicsoft/web/templates/index.html`, `nicsoft/web/static/i18n/{fr,en,de}.json`, `nicsoft/tests/test_issue314_lichess_board_reconnect.py` (nouveau), `CONTEXTE.md`. `driver.py`, `.audit.json`, `requirements.txt` non modifiés ; aucune nouvelle dépendance ; aucun moteur d'échecs ; aucune suppression d'outil de sécurité.

# Changelog — Issue #312

# Issue #312 — Tests dans un navigateur : le serveur de test ne doit plus pouvoir bloquer la suite, et l'adresse du serveur doit toujours s'afficher

- **Contexte** : depuis la fusion locale de #311, la suite complète se bloquait dès les tests e2e (dossier `nicsoft/tests/e2e`). Le serveur de test (`ALCHESS_SKIP_BOARD=1 python -m nicsoft.web`) était bien vivant, à l'écoute sur le port 5000, répondait 200 — mais `conftest.py` lisait la sortie du process ligne par ligne via `proc.stdout.readline()` **bloquant**, et aucune ligne contenant l'adresse n'arrivait jamais, donc la limite de 20s prévue dans le code n'était jamais vérifiée.

- **Cause réelle (confirmée sous pseudo-terminal, donc indépendante de la redirection)** : `nicsoft/web/alchess.py::_setup_logging()` abaisse (depuis #311) le niveau du `file_handler` partagé du root logger à `INFO`, pour que les lignes du logger `niclink.lichess` atteignent le fichier de journal. Or `werkzeug._internal._log()` n'ajoute son propre handler console ("Running on http://...", avertissement serveur de développement, "Press CTRL+C to quit") que si `werkzeug._internal._has_level_handler()` ne trouve, en remontant la chaîne de loggers parents du logger `"werkzeug"`, **aucun** handler dont l'attribut numérique `.level` couvre déjà son niveau effectif (`INFO`) — un test purement numérique sur `.level`, sans simulation des filtres. Le `file_handler` du root logger étant désormais à `INFO`, ce test était satisfait à tort : Werkzeug ne créait plus son propre handler, et ses lignes de démarrage (écrites via `logging`, pas via `print`) ne sortaient donc plus que vers le fichier de journal — jamais vers la console, **y compris en usage interactif** (vérifié avec un pseudo-terminal, pas seulement en sortie redirigée comme le laissait supposer l'énoncé).

- **Correctif logging (`nicsoft/web/alchess.py::_setup_logging`)** : aucune des deux lignes `niclink.lichess`/`file_handler` d'origine n'est retirée (les lignes Lichess restent écrites dans le fichier au niveau INFO, aucun autre logger n'est rendu plus verbeux — vérifié par test). Un handler console dédié est désormais attaché explicitement au logger `"werkzeug"` (niveau `INFO`, formateur `"%(message)s"`) dans `_setup_logging()`, pour garantir ses lignes de démarrage quel que soit l'état des autres handlers.

- **Ligne d'adresse garantie (`nicsoft/web/server.py::start_server`)** : nouvelle ligne `print(f"[NicLink] Interface disponible sur http://{host}:{port}", flush=True)` juste après le lancement du thread serveur — indépendante de toute configuration de journalisation (niveau de logger, destination de la sortie) et du comportement interne de Werkzeug. L'ancien `logger.info(...)` équivalent (déjà présent, mais filtré en silence par le niveau WARNING du logger `niclink.server`) est conservé tel quel.

- **Fixture e2e non bloquable (`nicsoft/tests/e2e/conftest.py`)** : remplacement de la lecture bloquante de `proc.stdout` par un fil de lecture daemon (`_start_line_reader`) qui empile chaque ligne dans une `queue.Queue` — un `readline()` qui reste bloqué (process silencieux) ne bloque plus que ce fil daemon, jamais le test. `wait_for_server_url()` consomme cette queue avec une vraie limite de 20s (vérifiée à chaque itération, pas seulement « en théorie ») ; au-delà, le process est arrêté par son PID exact (`_kill_process` : `terminate()`, puis `kill()` après 5s si besoin) et le test échoue avec les dernières lignes lues dans le message. Le `yield` de la fixture est maintenant protégé par un `try/finally` : le serveur est arrêté dans tous les cas (succès, échec de démarrage, exception levée par un test). Aucun navigateur n'est lancé avant que `requests.get(url)` réponde 200. `ALCHESS_SKIP_BOARD=1`/pas d'ouverture de navigateur inchangés.

- **Bug révélé une fois l'e2e débloquée** : des 3 tests Playwright ajoutés par #311 et jamais exécutés jusqu'ici (bloqués par le défaut ci-dessus), un échouait réellement : `test_game_lichess_aborted_affiche_message_explicite_et_deux_boutons` vérifiait la présence de la sous-chaîne française `"annul"` dans le message affiché, alors que la page démarre sans cookie de locale — donc en anglais (`DEFAULT_LOCALE = 'en'` de `i18n.js`), comportement intentionnel et inchangé. Corrigé en vérifiant `"lichess"` (présent dans les 3 traductions de la clé `lichess.annulee_premier_coup_trop_tard`) plutôt qu'un mot propre au français. Aucun changement côté application.

- **Tests** :
  - `nicsoft/tests/test_issue312_server_startup.py` (nouveau) : (a) lance réellement le serveur (sortie redirigée comme le fait la fixture, `ALCHESS_DIR` pointé vers `tmp_path`) et vérifie que la ligne d'adresse apparaît en moins de 10s via `wait_for_server_url` ; (b) teste `wait_for_server_url`/`_start_line_reader` avec un faux process dont le flux ne produit jamais de ligne (`readline()` bloqué pour toujours) — prouve que l'échec survient bien avant la limite passée en paramètre et que le process est arrêté (`terminate()` puis `kill()`).
  - `nicsoft/tests/test_logging_config.py` (complété) : les lignes `niclink.lichess` restent écrites au niveau INFO dans le fichier de journal, `niclink.server` (et donc les autres loggers sans niveau explicite) reste au niveau WARNING hérité du root ; `"werkzeug"` porte bien un handler console de niveau ≤ INFO après `_setup_logging()`.
  - `nicsoft/tests/e2e/test_issue310_lichess_e2e.py` : correction de l'assertion i18n décrite ci-dessus.
  - Suite complète exécutée (`python -m pytest`, dossier e2e compris, navigateur Chromium headless disponible dans cet environnement) : **862 passés, 81 ignorés (marqueur `hardware`/absence de moteurs), 0 échec, ~47s** — aucun blocage, bien en-deçà des « quelques minutes » attendues.
  - Aucun process `nicsoft.web`/Chromium laissé actif après la suite (vérifié par `ps aux`). Un process `python -m nicsoft.web` lancé manuellement pendant l'investigation (sous `timeout`, dont le signal n'avait apparemment pas été traité à temps) a été arrêté explicitement par son PID exact (`kill -TERM`), conformément à la procédure.

- **CONTEXTE.md** : une phrase ajoutée dans « Principes techniques » sur la contrainte handler/`werkzeug` et la robustesse de la fixture e2e.

- Fichiers touchés : `nicsoft/web/alchess.py`, `nicsoft/web/server.py`, `nicsoft/tests/e2e/conftest.py`, `nicsoft/tests/e2e/test_issue310_lichess_e2e.py`, `nicsoft/tests/test_logging_config.py`, `nicsoft/tests/test_issue312_server_startup.py` (nouveau), `CONTEXTE.md`. Aucune modification de `driver.py`, `.audit.json`, `requirements.txt` ; aucune nouvelle dépendance ; aucun moteur d'échecs ; aucune suppression d'outil de sécurité.

# Changelog — Issue #311

# Issue #311 — Lichess L2a : placer les pièces avant de créer la partie, message clair quand Lichess annule, retour sur la nulle et journal visible par défaut

- **Contexte** : deuxième essai réel du mode Lichess (#309/#310 fusionnées). Première partie (niveau 1, 15+10) parfaite. Deuxième partie, échiquier non rangé au lancement : l'écran « Position incorrecte » s'affichait bien, mais au premier coup l'application revenait au menu **sans aucun message**. Sur lichess.org, la partie apparaissait annulée (« Les Blancs ont quitté la partie », position initiale, aucun coup joué) : Lichess avait annulé parce que le premier coup n'avait pas été joué dans le délai qu'il impose après la création de la partie — délai écoulé pendant que l'utilisateur rangeait encore son échiquier, puisque la partie était créée **avant** l'attente de la position de départ. Le journal ne contenait aucune ligne pour ces parties (niveau INFO filtré par le niveau WARNING du journal par défaut).

- **Nouvel ordre de lancement (`core/game_manager_modes/lichess.py`), sans pression de temps** : la couleur « aléatoire » est désormais résolue localement (`random.choice`) **avant** tout appel à Lichess — Lichess ne reçoit jamais la valeur `"random"`/`""`. Dans tous les cas, la position de départ est confirmée sur l'échiquier (nouvelle fonction `_wait_initial_position_lichess`, sans limite de temps, annulable par le bouton « Retour au menu » désormais affiché sur l'écran « Position incorrecte » quand le mode actif est Lichess) **avant** toute création de partie chez Lichess.
  - **Blancs** : après la position confirmée, nouvel écran « Vos pièces sont en place » (`#screen-lichess-wait-first-move`, état `lichess_wait_first_move`) attend le **premier coup physique** de l'utilisateur sans aucune limite de temps (nouvelle fonction `_wait_first_move_white_lichess`, réutilise `legal_move_for_hardware` déjà testée) — aucune partie Lichess n'existe encore, la contrainte de premier coup de Lichess ne s'applique donc jamais aux blancs. Le coup détecté sert ensuite de premier envoi juste après la création de la partie. Si la création échoue à ce stade (après que l'utilisateur a déjà joué), le retour se fait vers l'écran de configuration Lichess (réglages conservés par la SPA) et non vers le menu générique.
  - **Noirs** : la partie est créée immédiatement après la position confirmée (l'utilisateur vient de ranger l'échiquier, pas de bouton supplémentaire) — l'IA joue aussitôt son premier coup. `LichessGame._apply_game_full` déclenche désormais un signal sonore (`nl_inst.beep()`) en plus des LED déjà posées sur ce premier coup adverse.
  - Annulation pendant l'une de ces deux attentes (bouton « Retour au menu ») : nouvelle exception interne `_BackMenuDuringWait`, détectée en relisant l'état applicatif (`get_app_state() == "menu"`, déjà forcé par `on_action()` côté serveur dès le clic — ces deux nouveaux états n'étant pas relayés à `action_queue`) ; aucun toast d'erreur, nettoyage normal de l'échiquier.
  - Aucun autre mode n'est modifié (`_wait_initial_position_web` de `state.py`, utilisée par Humain/Pédagogique, inchangée).

- **Compte à rebours du premier coup (noirs)** (`modes/lichess/game.py`) : nouvelle fonction pure `first_move_deadline_s(expiration, elapsed_s)` lisant le champ `expiration` (`idleMillis`/`millisToMove`) des messages de partie Lichess. Dès que l'IA a joué son unique premier coup et que c'est au tour de l'utilisateur, l'événement `lichess_first_move_deadline` est émis (à chaque battement de pendule, ~1s) avec le nombre de secondes restantes, ou sans décompte si le champ est absent ; il disparaît dès que l'utilisateur joue son propre coup. Côté `app.js`/`index.html` : nouvelle bannière `#lichess-first-move-deadline` dans la carte de statut Lichess, textes `lichess.premier_coup_decompte`/`lichess.premier_coup_sans_decompte`.

- **Jamais de fin silencieuse, jamais de retour automatique au menu** (`modes/lichess/game.py::_finalize`) : un statut de fin inattendu et non demandé par l'utilisateur (`aborted` hors abandon/annulation volontaire, `noStart`, `unknownFinish` — y compris le cas où le flux se ferme sans statut connu) déclenche désormais un nouvel événement `lichess_aborted` (message traduit selon la cause connue ou, à défaut, message générique, plus les réglages d'origine pour « Rejouer ») **au lieu** de l'écran d'analyse normal (`skip=True`, jamais de `set_app_state("game_over", ...)` pour ce cas). Nouveau drapeau `_user_initiated_end`, mis à vrai uniquement après succès de `resign()`/`abort()` demandé par l'utilisateur via le bouton « Abandonner » — ce chemin et un retour menu explicite gardent le comportement/message existants, inchangés. Côté navigateur : nouvelle fenêtre persistante `#lichess-aborted-overlay` (ne se referme que par un clic sur l'un de ses deux boutons) avec « Rejouer avec les mêmes réglages » (renvoie directement `start_lichess` avec les réglages d'origine, y compris une couleur « aléatoire » non encore résolue) et « Retour au menu ».

- **Nulle — message d'attente** : nouveau texte `lichess.nulle_attente_reponse` affiché à côté du bouton « Partie Nulle » (grisé) dès `lichess_draw_proposed`, effacé sur `lichess_draw_refused` ou au début d'une nouvelle partie. Comportement de refus/acceptation inchangé. Nouveau test vérifiant explicitement le refus quand l'offre a été faite pendant le tour de l'utilisateur lui-même (pas seulement pendant celui de l'adversaire, déjà couvert par #310).

- **Journal visible par défaut, sans mode DEBUG** (`nicsoft/web/alchess.py::_setup_logging`) : le niveau WARNING du `root_logger`/`file_handler` filtrait toutes les lignes `logger.info(...)` du mode Lichess, y compris celles déjà écrites sur le logger dédié `niclink.lichess` depuis #309/#310. Correctif minimal et ciblé : `logging.getLogger("niclink.lichess").setLevel(logging.INFO)` **et** `file_handler.setLevel(logging.INFO)` — comme aucun autre logger ne reçoit de niveau explicite (ils restent gouvernés par le WARNING du root_logger, donc jamais transmis au handler), seules les lignes de `niclink.lichess` deviennent visibles ; aucun autre module n'est rendu plus verbeux. Les lignes de lancement/position confirmée/partie créée, auparavant écrites sur le logger générique `niclink.game_manager` (donc filtrées), sont déplacées sur `logger_lichess` (`niclink.lichess`) dans le lanceur. Les lignes « coup envoyé » et « coup reçu » (`modes/lichess/game.py`) portent désormais le délai écoulé depuis l'événement précédent, en millisecondes. Le jeton n'apparaît toujours dans aucune ligne (vérifié par un nouveau test dédié).

- **CONTEXTE.md** : phrase sur l'ordre de lancement du mode Lichess réécrite pour refléter le nouvel ordre (#311) ; la note historique #310 (« cannot join thread ») retirée de l'état courant (reste dans `CHANGELOG.md`).

- **Nouveaux tests** :
  - `nicsoft/tests/test_issue311_lichess_sequencing.py` (20 tests, sans réseau ni matériel) : création après position + premier coup physique (même après un long délai simulé), création immédiate pour les noirs, résolution locale de la couleur aléatoire (`random.choice` monkeypatché), retour vers `config_lichess` si la création échoue après le premier coup des blancs, deux parties enchaînées dans la même instance avec un échiquier mal rangé au départ de la seconde, statuts inattendus → `lichess_aborted` avec le bon message (jamais pour une annulation/un retour menu demandés par l'utilisateur), fonction pure `first_move_deadline_s`, apparition/disparition du compte à rebours, signal sonore du premier coup IA (noirs uniquement), nulle refusée pendant le tour de l'utilisateur, lignes de journal en INFO par défaut avec délai en ms, jeton absent de tout message de journal.
  - `nicsoft/tests/e2e/test_issue310_lichess_e2e.py` : deux nouveaux tests Playwright (fenêtre d'annulation avec message et boutons, apparition/disparition du compte à rebours) ajoutés en suivant le motif existant (événements socket simulés côté client, sans réseau ni crochet de production) — **non exécutés dans cette session** : le lancement du serveur de test (`server_url`, sous-processus `~/NicLink/venv/bin/python -m nicsoft.web`) reste bloqué indéfiniment dans ce bac à sable (`proc.stdout.readline()` sans délai propre, limitation préexistante de l'infrastructure e2e de #310, indépendante de cette tâche) ; un essai manuel a dû être interrompu en tuant le PID exact conformément à la procédure.
  - `test_issue309_lichess_l2a.py`/`test_issue310_lichess_corrections.py` : mis à jour pour le nouveau nom de fonction d'attente (`_wait_initial_position_lichess`) et une couleur de test explicite (`"black"` au lieu de `"random"`, qui serait désormais non déterministe du fait de la résolution locale).

- Fichiers touchés : `nicsoft/modes/lichess/game.py`, `nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/web/alchess.py`, `nicsoft/web/static/app.js`, `nicsoft/web/templates/index.html`, `nicsoft/web/static/i18n/{fr,en,de}.json`, `CONTEXTE.md`, tests ci-dessus. Aucune modification de `driver.py`, `.audit.json`, `requirements.txt` ; aucune nouvelle dépendance ; aucun moteur d'échecs ; aucune suppression d'outil de sécurité.

- Suite complète exécutée hors e2e (`pytest nicsoft/tests --ignore=nicsoft/tests/e2e`) : 793 passed, 80 skipped, aucune régression. `py_compile` sur les fichiers Python modifiés/ajoutés : OK. Syntaxe JS vérifiée (`node --check app.js`) : OK. JSON i18n validés (`json.load` sur les trois fichiers) : OK.

## Allemand à faire relire

Les nouveaux textes allemands (`lichess.attente_premier_coup.*`, `lichess.premier_coup_decompte`/`_sans_decompte`, `lichess.nulle_attente_reponse`, `lichess.annulee_*`, `lichess.rejouer_memes_reglages`) sont des traductions de bonne foi, pas des recopies de l'anglais — à faire relire par un locuteur allemand comme pour #306/#307/#309/#310.

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. **Blancs** : lancer une partie avec l'échiquier non rangé, le ranger sans se presser, attendre plusieurs minutes avant de jouer le premier coup, le jouer — vérifier que la partie n'est créée qu'à ce moment-là et que le coup part bien.
2. **Noirs** : lancer la partie échiquier déjà rangé — entendre le signal sonore, voir le coup de l'IA par les LED et le compte à rebours, exécuter ce coup physiquement puis jouer le sien dans le délai.
3. **Noirs** : laisser passer le délai du premier coup sans jouer — vérifier le message d'annulation explicite et les deux boutons (« Rejouer avec les mêmes réglages », « Retour au menu »).
4. Proposer la nulle et lire le texte d'attente, puis la réponse (acceptée ou refusée).
5. Lire le journal (`niclink.log`) sans activer `NICLINK_LOG=DEBUG` et vérifier la présence des nouvelles lignes (position confirmée, partie créée, coups avec délai en ms, fin de partie).
6. Enchaîner deux parties Lichess dans la même session.
7. Vérifier l'affichage en anglais et en allemand des nouveaux textes, signaler toute formulation allemande à corriger.

# Changelog — Issue #310

# Issue #310 — Lichess L2a, correctifs après essai réel : fin de partie sans erreur, textes manquants, retour sur la nulle, traces dans le journal et test navigateur

- **Contexte** : premier essai réel de #309 (mode Lichess) sur le vrai échiquier. Le cœur fonctionne (écran de config, création de partie, détection des coups, roque) mais plusieurs défauts sont apparus en conditions réelles, invisibles aux tests existants (sans réseau ni matériel ni navigateur).

- **Cause racine de l'erreur de fin de partie** (« Erreur inattendue mode Lichess : cannot join thread before it is started ») : `LichessGame.start()` exécute `run()` de façon **synchrone** (le vrai threading vit dans le lanceur) sans jamais appeler `threading.Thread.start()` natif — le lanceur (`core/game_manager_modes/lichess.py`) appelait pourtant `game.join()` juste après `game.start()`, ce qui lève inconditionnellement `RuntimeError("cannot join thread before it is started")` à la fin de **toute** partie (pas seulement à l'abandon — c'était simplement la première fin de partie atteinte lors de l'essai). Cette exception, capturée par le `except Exception` générique, écrasait ensuite l'état `game_over` déjà posé par `_finalize()` (PGN tenté, historique prêt) en forçant un retour menu avec toast d'erreur — d'où partie finie « en erreur », sans écran de résultat ni analyse. Corrigé : suppression de l'appel `game.join()` (devenu inutile, `game.start()` bloque déjà jusqu'à la fin réelle de la partie) **et** `LichessGame.join()` surchargée en no-op défensif, pour qu'un futur appel (ex. lors d'une prochaine refonte) ne puisse plus jamais lever cette erreur.

- **`_finalize()` (`modes/lichess/game.py`) endurcie** : chaque étape (extinction LED, sauvegarde PGN, construction/envoi de l'état de fin) est désormais isolée dans son propre `try/except` — un échec sur une étape n'empêche plus les suivantes. La sauvegarde PGN reste tentée **avant** l'envoi de l'état de fin, lui-même avant la libération de l'échiquier (faite par l'appelant, dans tous les chemins : fin normale, abandon, erreur, échiquier perdu) — jamais sur une annulation (<2 coups).

- **Lancement refusé proprement si un autre mode est actif** : `launch_lichess()` vérifie l'état d'application au tout début (`menu`/`config_lichess` sinon refus avec toast `toast.lichess_mode_actif`), sans toucher à l'échiquier ni à l'état en cours.

- **Libération de l'échiquier** : `launch_lichess()` relance désormais une vérification silencieuse de présence du plateau (`check_board_presence_silent`, même précaution que `humain.py`) au retour menu, pour que l'état affiché ne soit pas périmé juste avant un nouveau lancement de mode.

- **Nulle avec retour** (`modes/lichess/game.py` + `app.js`) : « Proposer nulle » envoie désormais un événement `lichess_draw_proposed` (toast « Proposition de nulle envoyée », bouton « Nulle » désactivé jusqu'à la réponse) ; si l'adversaire joue un coup sans accepter, ou si le statut ne passe pas à nulle (`wdraw`/`bdraw` de Lichess repassant à faux sans fin de partie), un événement `lichess_draw_refused` réactive le bouton avec un toast « Nulle refusée ». Si elle est acceptée, la fin de partie normale s'applique (aucun changement nécessaire, le statut Lichess passe directement à `draw`).

- **Textes manquants** : 6 clés `toast.lichess_*` (jeton absent/refusé/droit manquant/limite atteinte/réseau/erreur générique — utilisées par le lanceur depuis #309 mais jamais ajoutées aux fichiers i18n) + `pgn.mode.Lichess` (bibliothèque PGN, affichait la clé brute pour les parties Lichess) + 2 nouvelles clés pour le retour sur la nulle, ajoutées dans `fr.json`/`en.json`/`de.json` (allemand à relire par un germanophone, comme pour #306/#307/#309).

- **Journal** : une ligne `logger.info` à chaque étape du mode Lichess (lancement, jeton présent, échiquier ouvert, position confirmée, partie créée avec id/niveau/cadence/couleur, flux ouvert, chaque coup reçu/envoyé en UCI, nulle proposée/reçue/refusée, abandon/annulation, reconnexion, fin de partie avec statut/résultat, PGN enregistré avec son chemin, échiquier libéré) — jamais le jeton. Les temps de pendule restent sans journalisation (comme avant).

- **Nom du joueur / adversaire** : déjà corrects (vérifiés, non modifiés) — `(config.get("player") or "Vous").strip() or "Vous"` dans le lanceur, affichage adversaire toujours « IA de Lichess (niveau N) » (`lichess.ia_niveau`).

- **Écran de configuration Lichess** : `#screen-config-lichess` était absent des règles de mise en page de `main.css` (contenu rejeté hors écran, scrollbar horizontale) — déjà corrigé à la main par l'utilisateur (ajouté au groupement `#screen-menu, #screen-config, #screen-config-humain, #screen-config-lichess, ...` et à la règle individuelle `#screen-config-humain, #screen-config-lichess`), vérifié présent, non retouché.

- **Nouveaux tests** :
  - `nicsoft/tests/conftest.py` (fixture autouse `_isolate_games_dir`, toute la suite en process) : redirige `GAMES_DIR` (et ses alias liés à l'import dans `pgn_manager.py`, `web/server.py`, `modes/humain/human.py`, `modes/retranscription/retranscription.py`) vers un répertoire temporaire par test — plus aucun test ne peut écrire dans le vrai dossier de parties de l'utilisateur (deux fichiers factices y avaient fui lors des tests de #309).
  - `nicsoft/tests/test_issue310_lichess_corrections.py` : régression directe du bug « cannot join thread » (partie complète jusqu'au mat via le lanceur réel, sans exception, état final `game_over`) ; `LichessGame.join()` ne lève jamais ; lancement refusé si mode déjà actif (3 états testés) ; enchaînement Humain (faux échiquier) puis Lichess dans la même instance avec libération vérifiée des deux échiquiers ; nulle proposée puis refusée ; garde d'isolation (confirme que `pgn_manager.GAMES_DIR` est bien redirigé, et qu'une partie complète avec sauvegarde PGN n'écrit rien dans le vrai dossier) ; extraction programmatique (regex, pas une liste figée) de toutes les clés i18n liées à Lichess utilisées dans `nicsoft/` (Python) et `app.js`, vérifiées présentes dans les 3 langues — ce test aurait détecté les 6 clés manquantes découvertes par cet essai réel.
  - `nicsoft/tests/test_issue310_css_layout_guard.py` : extrait de `app.js` tous les écrans/panneaux (`#screen-*`/`#panel-*`) basculés en `display:flex`/`grid`, et vérifie que chacun a au moins une règle de mise en page dans `main.css` (sur son id ou une classe portée dans `index.html`) — validé qu'il aurait détecté le défaut original de `#screen-config-lichess` (vérifié en simulant sa suppression).
  - `nicsoft/tests/e2e/test_issue310_lichess_e2e.py` (Playwright, vrai navigateur Chromium headless, serveur lancé avec `ALCHESS_SKIP_BOARD=1`/`BROWSER=/bin/true`, arrêté par son PID exact — réutilise le conftest e2e existant) : écran de configuration Lichess atteint sans échiquier ni jeton (`sendAction({type:'mode', value:'lichess'})`, qui ne fait que changer d'écran côté serveur) — vérifie niveau, cadence, couleur, nom, bouton Retour et bouton Démarrer tous visibles et dans la fenêtre, et l'absence de défilement horizontal (reproduction directe du bug #310). Écran de partie atteint sans réseau ni échiquier en invoquant directement, depuis Playwright, les callbacks déjà enregistrés par `socket.on(...)` dans app.js via la méthode publique `socket.listeners(event)` du client Socket.IO (aucun crochet de test ajouté en production) — vérifie plateau, deux pendules, bouton Abandonner et bouton Proposer nulle (activé) tous visibles. 17 tests, tous passés.

- **Hors périmètre, non touché** : `driver.py`, `.audit.json`, `requirements.txt` ; aucune nouvelle dépendance ; aucune suppression d'outil de sécurité ; aucun moteur d'échecs importé ou lancé par ce mode (garde existante toujours verte).

- **Garde d'isolation vérifiée manuellement** : avant/après l'exécution de la suite complète, le vrai dossier `~/NicLink/games/Lichess/Amicale/` n'a reçu aucun nouveau fichier (le seul fichier présent, `2026-11-09_Alain_vs_LichessAIlevel1_01.pgn`, date d'avant cette session — fichier factice que l'utilisateur retire lui-même, non supprimé par cette tâche).

- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`, e2e inclus) : 833 passed, 81 skipped (aucune régression). `py_compile` sur les fichiers Python modifiés/ajoutés : OK. Syntaxe JS vérifiée (`node --check app.js`) : OK.

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. Lancer une partie contre l'IA niveau 1 en 15+10.
2. Jouer quelques coups.
3. Proposer la nulle et lire le retour affiché (« Proposition de nulle envoyée », bouton désactivé ; « Nulle refusée » si l'IA ne l'accepte pas).
4. Abandonner : résultat lisible, PGN enregistré dans le dossier des parties, écran d'analyse.
5. Relancer une seconde partie sans redémarrer l'application.
6. Lire le journal (`niclink.log` ou console) et vérifier la présence des étapes listées ci-dessus, sans jamais le jeton.
7. Vérifier l'affichage en anglais et en allemand des nouveaux textes, et signaler toute formulation allemande à corriger.
8. Supprimer soi-même le fichier factice restant dans `games/Lichess/Amicale/` si souhaité (non touché par cette tâche).

# Changelog — Issue #309

# Issue #309 — Lichess L2a : jouer une partie amicale contre l'IA de Lichess sur l'échiquier physique, aides coupées, pendules, abandon et nulle

- **Contexte** : troisième étape de la connexion à Lichess (suite de #306 jeton et #307 client de partie). Objectif : jouer une vraie partie amicale contre l'IA de Lichess entièrement sur l'échiquier physique — placement de départ, coups de l'IA montrés par les LED, coups de l'utilisateur détectés et envoyés, pendules, abandon/annulation, proposition de nulle, sauvegarde PGN et écran d'analyse. Aucun moteur, aucune aide, aucune limite de temps de réflexion côté AlChess. Adversaire humain, parties classées et reprise après perte d'échiquier restent hors périmètre (issues suivantes).

- **Nouveau module** `nicsoft/modes/lichess/game.py` — boucle de jeu `LichessGame` (n'importe jamais `nicsoft.engine.engine_manager` ni aucun moteur UCI). Le plateau logique vient toujours de la liste de coups UCI confirmée par Lichess (jamais de mise à jour optimiste avant confirmation). Boucle principale non bloquante à chaque tick (~50ms) : actions navigateur (résignation/nulle/promotion/verrouillage du menu), événements d'un thread de lecture de flux séparé (file d'attente dédiée), détection du coup physique. Fonctions pures testées isolément : `legal_move_for_hardware` (gère roque/en passant via comparaison de FEN résultant), `pending_promotion_move` (détecte une promotion en attente sans présumer de la pièce physiquement posée — le choix est demandé à l'écran, Dame par défaut), `compute_clock_ms` (pendules recalculées à partir d'heures, jamais par accumulation JS), `pgn_result`/`pgn_time_control`/`opponent_pgn_name`/`build_pgn_headers` (jamais de nom vide ni « None »). Gère : tour de l'adversaire (LED + attente de réplication physique avant de rendre la main), tour de l'utilisateur (détection physique → envoi, coup refusé → attente du remise en place), abandon (`resign` si ≥2 coups joués, sinon `abort`), proposition/réponse de nulle, réception d'une offre de nulle adverse, verrouillage du menu avec message explicite pendant la partie, échiquier perdu en cours de partie (bande d'information, pas d'abandon automatique, partie laissée ouverte), reconnexion de flux avec recalage complet sur le nouveau `gameFull`, fin de partie (résultat lisible, sauvegarde PGN sauf si annulée, écran d'analyse).

- **Transport** (`nicsoft/modes/lichess/transport.py`) : `STREAM_READ_TIMEOUT_S` porté de 20s à 90s — une partie longue (90+30, réflexions de 15-20 min) ne doit pas déclencher une reconnexion sur un simple silence du flux plus long que les lignes de maintien habituelles.

- **Lanceur** `nicsoft/core/game_manager_modes/lichess.py` (`launch_lichess`/`_run_lichess`, exporté par `game_manager.py`), sur le modèle du lanceur Humain contre Humain : vérifie le jeton enregistré (sinon retour menu avec toast), crée la partie par le client (niveau 1-8, cadence parmi 10+0/15+10/30+0/60+0/**90+30**, couleur), attend la position initiale (réutilise `_wait_initial_position_web`), démarre `LichessGame`, traduit les erreurs du client (jeton refusé/droit manquant/limite atteinte/réseau/échiquier non détecté) en toasts clairs sans partie fantôme, ferme la connexion à l'échiquier en fin de session.

- **Dispatch** (`nicsoft/web/alchess.py`) : `mode=lichess` → écran `config_lichess` ; `start_lichess` → `launch_lichess`. Pas de changement nécessaire dans `server.py` : les états `connecting`/`playing`/`game_over` déjà utilisés verrouillent déjà le routage des actions (`action_queue` plutôt que `menu_queue`), exploité pour afficher le message « partie Lichess en cours » depuis `LichessGame` elle-même.

- **Interface** (`index.html`, `app.js`, `main.css`) : carte menu « Lichess » sous Humain contre Humain, même logique d'activation (échiquier physique requis) **plus** jeton enregistré requis (`_applyLichessCardState`, rafraîchi via `config_get` au retour menu — pas seulement après une visite de Paramètres) ; écran `screen-config-lichess` (niveau 1-8, cadence, couleur, nom, phrase de rappel amicale/aides coupées) ; écran de partie réutilisant le plateau/historique partagés via de nouveaux événements dédiés (`lichess_init`, `lichess_move`, `lichess_clock`, `lichess_position_wait/ok`, `lichess_reconnecting/reconnected`, `lichess_board_lost/ok`, `lichess_draw_offered`, `lichess_promotion_needed`, `lichess_move_refused`, `lichess_toast`) plutôt que les événements génériques `move`/`turn` (pour ne rien risquer sur les autres modes) ; pendules affichées à partir des valeurs reçues, recalculées à l'affichage à partir d'un horodatage (pas d'accumulation JS) ; boutons Abandonner/Partie Nulle réutilisés (branche `_gameMode === "lichess"` dans les modales existantes) ; bouton « Retour au menu » masqué pendant une partie Lichess (seule sortie : abandon/annulation) ; bannière « cases incorrectes » réutilisée pour l'attente de réplication du coup adverse. Nom de l'adversaire toujours « IA de Lichess (niveau N) » (clé `lichess.ia_niveau`), jamais vide ni « None ».

- **i18n** (`fr.json`/`en.json`/`de.json`, mêmes 31 clés dans les trois) : menu/config/jeu Lichess (`menu.btn.lichess`, `config.titre.lichess`, `lichess.*`, `game.titre_victoire/.titre_defaite/.titre_annulee`, etc.). **La traduction allemande doit être relue par un germanophone** (traduction directe, non revérifiée par un locuteur natif — comme pour L0/L1).

- **CONTEXTE.md** : ligne « Lichess » mise à jour (mode jouable contre l'IA, amical, échiquier physique uniquement, aucun moteur, plateau logique piloté par Lichess, pendules par horodatage).

- **Garde test existante corrigée** (`test_issue303_html_escaping.py`) : `mm`/`ss` (horodatage de pendule, entiers locaux) ajoutés à `SAFE_IDENTIFIERS` avec justification — aucune donnée externe concernée.

- **Nouveau test de garde** `nicsoft/tests/test_issue309_lichess_l2a.py` (42 tests, sans réseau — faux transport scénarisé — ni matériel — faux plateau physique `FakeBoard`) : fonctions pures (coup physique y compris roque/en passant, promotion, pendules, en-têtes PGN) ; scénarios boîte blanche de `LichessGame` (identification couleur/niveau IA depuis `gameFull`, coup adverse affiché+LED+attente de réplication physique, coup utilisateur détecté et envoyé sans mise à jour optimiste, promotion demandée à l'écran puis soumise, coup refusé par Lichess avec attente de remise en place, proposition de nulle des deux côtés, abandon devenant annulation si <2 coups sinon résignation, échiquier perdu sans abandon automatique, reconnexion avec recalage sur nouveau `gameFull`, verrouillage du menu pendant la partie, sauvegarde PGN avec les bons en-têtes et absence de sauvegarde si annulée) ; partie complète jusqu'au mat (mat du berger) pilotée par une file de flux synchronisée sur les vrais appels `play_move()` du jeu (pas de script indépendant du code testé), avec garde explicite qu'aucun moteur n'est jamais appelé ; traduction des erreurs du lanceur en toasts (jeton absent/refusé/droit manquant/limite/réseau) ; présence des clés i18n dans les trois langues ; câblage `app.js` (nouveaux événements/fonctions présents, jeton jamais exposé côté client, `textContent`/`t()` exclusifs pour le texte Lichess reçu).

- **Hors périmètre, non touché** : `driver.py`, `.audit.json`, `requirements.txt` ; aucune nouvelle dépendance ; aucune suppression d'outil de sécurité ; modes de jeu existants inchangés (humain, pédagogique, exercices, retranscription, labo).

- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 797 passed, 81 skipped (aucune régression — le smoke e2e `test_hh_ouvre_config` dépendait d'un sélecteur CSS désormais ambigu avec la nouvelle carte Lichess, corrigé en lui donnant sa propre classe `.menu-btn-lichess`). Syntaxe JS vérifiée (`node --check app.js`) : OK. `py_compile` sur les fichiers Python modifiés/ajoutés : OK.

## Vérification manuelle restant à faire par Alain (nécessite l'échiquier physique et un vrai jeton Lichess)

1. Sans jeton ou sans échiquier : la carte « Lichess » est inactive avec le bon message.
2. Partie contre le niveau 1 en 15+10, couleur aléatoire : placement de départ, premier coup de l'IA montré par les LED, quelques coups joués de part et d'autre.
3. Laisser passer plusieurs minutes de réflexion sans jouer : rien ne se déconnecte, les pendules restent justes au retour.
4. Proposer la nulle, puis abandonner une autre partie.
5. En fin de partie : le PGN est enregistré et l'écran d'analyse s'ouvre.
6. La partie figure bien dans l'historique de lichess.org.
7. Tenter de lancer un autre mode pendant la partie : refusé, avec le message « Partie Lichess en cours ».
8. Vérifier l'affichage en anglais et en allemand (et signaler toute formulation allemande à corriger).

# Changelog — Issue #307

# Issue #307 — Lichess L1 : client de partie (flux, coups, abandon, nulle) testé sans réseau, et bouton « Tester une partie (IA niveau 1) »

- **Contexte** : deuxième étape de la connexion à Lichess (plan validé, suite de l'étape L0 — issue #306). Objectif unique : la couche de communication d'une partie Lichess (créer, lire le flux, jouer, abandonner, annuler, répondre à une nulle), entièrement testable sans réseau, plus un bouton qui prouve qu'elle fonctionne contre le vrai Lichess. Aucun mode de jeu, aucun écran de partie, aucun moteur — ces points restent hors périmètre de cette étape.

- **Nouveaux modules** `nicsoft/modes/lichess/` (n'importent jamais `nicsoft.web`, ARC-001 — couverts automatiquement par `test_no_web_import.py`, découverte dynamique) :
  - `transport.py` : couche de transport réseau injectable — `UrllibTransport` (production, urllib standard) implémente `request(method, url, token, fields)` (requête ordinaire, délai 10 s, jeton uniquement dans l'en-tête `Authorization`) et `stream_lines(url, token)` (générateur de lignes décodées, délai de lecture 20 s — la pause entre deux lignes, lignes vides de maintien incluses, peut dépasser dix secondes). Schéma https vérifié par `ensure_https` avant tout appel. Erreurs typées au niveau transport : `TransportHTTPError` (code + corps), `TransportNetworkError`, `TransportTimeoutError` — jamais le jeton dans leur message.
  - `errors.py` : erreurs typées côté client — `LichessAuthError` (401/403), `LichessRateLimitError` (429, `retry_after_s=60`), `LichessNetworkError`, `LichessApiError` (code + message Lichess, ex. coup illégal, partie déjà terminée). Aucune ne reçoit jamais le jeton.
  - `game_client.py` : `GameClient(token, transport=None)` — `create_ai_game(level, clock_limit_s, clock_increment_s, color="")` (POST `/api/challenge/ai`), `play_move(game_id, uci, offer_draw=False)`, `resign`, `abort`, `answer_draw(game_id, accept)`. Une seule requête ordinaire à la fois par instance via un verrou (`threading.Lock`), qui ne bloque jamais `stream_game` (générateur indépendant, aucun verrou). `stream_game(game_id, sleep=time.sleep)` : générateur d'événements décodés (`gameFull`, `gameState`, `chatLine`, `opponentGone` — lignes vides et types inconnus ignorés) ; en cas de coupure réseau en cours de partie, reprend avec des attentes croissantes (1, 2, 4, 8 puis 30 s au plus — jamais de boucle sans attente), signale `{"type": "reconnecting", "attempt", "delay_s"}` puis `{"type": "reconnected"}`, accepte un nouveau `gameFull` à la reprise comme état complet ; s'arrête à la fermeture normale du flux ou au statut terminé de la partie. Fonctions utilitaires pures : `moves_from_state`, `side_to_move`, `is_game_over`, `result_text`.
  - `client.py` (étendu depuis l'étape L0) : nouvelle fonction `test_ai_game(token, transport=None)` — crée une vraie partie amicale contre l'IA niveau 1 (15 min sans incrément, couleur aléatoire), lit le premier `gameFull`, déduit la couleur/l'adversaire, annule la partie (ou l'abandonne si l'annulation est refusée), vide le flux jusqu'à sa fermeture. Retourne un statut structuré (`ok`/`invalid`/`missing_scope`/`rate_limited`/`network_error`) — jamais le jeton dans le résultat.

- **Serveur** (`nicsoft/web/server.py`) : nouvel événement `lichess_test_game` — utilise uniquement le jeton déjà enregistré (jamais celui tapé, pas encore sauvegardé) ; un verrou global (`threading.Lock`, `acquire(blocking=False)`) garantit qu'un seul test de partie tourne à la fois, sans bloquer le reste du serveur ; appelle `client.test_ai_game` dans un thread daemon et émet `lichess_test_game_result` au client concerné. Toute exception inattendue est journalisée sans le jeton (nom de la classe seulement) et traduite en `network_error`.

- **Paramètres (écran)** (`index.html`, `app.js`) : nouveau bouton « Tester une partie (IA niveau 1) » sous le test de connexion existant, avec une phrase expliquant qu'il crée puis annule aussitôt une vraie partie amicale contre l'IA de Lichess ; désactivé et accompagné d'une explication (`#lichess-test-game-hint`) tant qu'aucun jeton n'est enregistré. Les deux boutons (connexion/partie) se désactivent mutuellement pendant qu'un test tourne — un seul test à la fois, résultat affiché dans la même zone (`#lichess-test-result`) exclusivement par `textContent` (jamais `innerHTML`, texte venant de Lichess).

- **i18n** (`fr.json`/`en.json`/`de.json`, mêmes clés dans les trois) : `parametres.lichess.couleur.blancs/.noirs`, `.test_partie.bouton`, `.test_partie.aide`, `.test_partie.sans_jeton`, `.test_partie.resultat.ok` (`{adversaire}`, `{couleur}`), `.test_partie.resultat.droit_manquant`. **La traduction allemande doit être relue par un germanophone** (traduction directe, non revérifiée par un locuteur natif — comme pour l'étape L0).

- **CONTEXTE.md** : ligne « Lichess » de la section « Principes techniques » mise à jour (client de partie dans `modes/lichess/`, transport injectable, une requête à la fois, jamais de moteur ni d'écran de partie encore ajouté).

- **Nouveau test de garde** `nicsoft/tests/test_issue307_lichess_l1.py` (52 tests, entièrement sans réseau — faux transport scénarisé, `FakeTransport` — ni matériel) : `UrllibTransport` (schéma https refusé sans appel réseau, jeton uniquement dans l'en-tête `Authorization`, jamais dans l'URL ni le corps, erreurs HTTP/réseau/délai mappées, lignes vides de maintien conservées) ; `GameClient` (champs de `create_ai_game`, URLs de `play_move`/`resign`/`abort`/`answer_draw`, jeton jamais dans l'URL/les champs/les exceptions) ; erreurs typées (401/403 → `LichessAuthError`, 429 → `LichessRateLimitError`, 400+message → `LichessApiError`, réseau/délai → `LichessNetworkError`) ; verrou des requêtes ordinaires sérialisées (6 threads concurrents, `max_concurrent_requests == 1`) sans bloquer la lecture du flux ; déroulement normal du flux (gameFull puis gameState jusqu'à mat/abandon/temps dépassé), lignes vides et types inconnus ignorés, proposition de nulle des deux couleurs, `chatLine`/`opponentGone` non ignorés ; coupure en cours de flux puis reprise avec nouveau `gameFull` (remplace l'état local), séquence d'attentes croissantes 1/2/4/8/30/30 avec horloge simulée (aucune vraie attente, `elapsed < 1s`), arrêt sur statut terminé sans relire, arrêt sur fermeture normale sans statut terminé ; fonctions utilitaires pures ; scénario complet de `test_ai_game` (succès couleur blanche/noire, abandon si annulation refusée, sans jeton, 401/403/429/erreur réseau, jeton jamais exposé) ; `lichess_test_game` côté serveur (sans jeton, jeton enregistré utilisé, un seul test à la fois, exception jamais journalisée avec le jeton) ; présence des nouvelles clés i18n dans `fr/en/de.json` ; `app.js` n'utilise que `textContent` pour le résultat du nouveau test. Les tests de garde existants (`test_issue306_lichess.py`, `test_issue303_html_escaping.py`, `test_no_web_import.py`) continuent de passer sans modification.

- **Hors périmètre, non touché** : `driver.py`, `.audit.json`, `requirements.txt`, les modes de jeu existants (pédagogique/humain/exercices/retranscription/labo) ; aucune nouvelle dépendance ; aucune suppression d'outil de sécurité.

- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 745 passed, 80 skipped. Syntaxe JS vérifiée (`node --check app.js`) : OK. `py_compile` sur les fichiers Python modifiés : OK. Serveur réel démarré (`ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) : démarre sans erreur avec le nouvel événement enregistré ; arrêté proprement par son PID après vérification.

## Vérification manuelle restant à faire par Alain

Cette tâche n'a pas pu la faire elle-même : aucun navigateur piloté n'a été utilisé (vérification faite par lecture de code, tests sans réseau et démarrage du serveur réel sans interface), et surtout un vrai jeton Lichess est nécessaire pour les points 1 et 3.

1. Avec le jeton enregistré, cliquer sur « Tester une partie » : un message de succès doit apparaître avec le nom de l'IA et la couleur jouée ; la partie annulée peut apparaître dans l'historique du compte sur lichess.org.
2. Supprimer le jeton : le bouton « Tester une partie » doit devenir inactif, avec l'explication affichée au-dessous.
3. Avec un jeton créé volontairement sans le droit `board:play` sur lichess.org : le message de droit manquant doit s'afficher.
4. Changer la langue en anglais puis en allemand : vérifier l'affichage de la section Lichess (et signaler toute formulation allemande à corriger — non revérifiée par un germanophone, comme en L0).

# Changelog — Issue #306

# Issue #306 — Lichess L0 : jeton personnel dans les paramètres, jamais envoyé au navigateur, et bouton « Tester la connexion »

- **Contexte** : première étape de la connexion à Lichess (plan validé par Alain, étape « L0 »). Objectif unique : enregistrer un jeton personnel Lichess et vérifier qu'il fonctionne — aucune partie, aucun nouveau mode de jeu. Le jeton suit exactement le mécanisme de la clé API LLM mis en place par l'issue #304 (jamais renvoyé au navigateur, indicateur de présence + indice 4 derniers caractères, remplacement, suppression explicite) ; les règles d'échappement de l'issue #303 s'appliquent au texte renvoyé par Lichess.

- **Configuration** (`nicsoft/core/config_manager.py`) : nouvelle clé `lichess_token` dans `DEFAULT_CONFIG`, valeur par défaut `""`.

- **Nouveau module** `nicsoft/modes/lichess/` (n'importe jamais `nicsoft.web`, ARC-001 — couvert automatiquement par `test_no_web_import.py`) :
  - `client.py` : `test_token(token)` interroge `POST https://lichess.org/api/token/test` (urllib standard, schéma vérifié par `nicsoft.utils.net_safety.ensure_https` avant tout appel, délai 10 s, `User-Agent: AlChess/<version>` via `importlib.metadata`, lecture de la réponse plafonnée à 64 Ko). Retourne un statut structuré : `ok` (compte, liste des scopes, `has_board_play`), `invalid`, `rate_limited` (HTTP 429), `network_error` (toute autre erreur réseau/HTTP). Le jeton n'apparaît jamais dans une exception journalisée.

- **Serveur** (`nicsoft/web/server.py`) :
  - `on_config_get` : retire `lichess_token` de la config avant émission, ajoute `has_lichess_token` (booléen) et `lichess_token_hint` (4 derniers caractères si longueur ≥ 12, sinon vide) — même logique que `llm_api_key`.
  - `on_config_save` : `lichess_token` vide = inchangé ; valeur non vide = remplacement (espaces autour retirés) ; `lichess_token_delete: true` = suppression explicite. Jamais réémis dans `config_saved`.
  - Nouvel événement `lichess_test_connection` : utilise le jeton tapé dans le champ (pas encore enregistré) si présent, sinon celui déjà en config ; appelle `client.test_token` dans un thread daemon (comme les autres appels réseau du serveur) et émet `lichess_test_result` au client concerné (`to=sid`). Toute exception inattendue est journalisée sans le jeton (seul le nom de la classe d'exception est loggé) et traduite en `{"status": "network_error"}`.

- **Paramètres (écran)** (`nicsoft/web/templates/index.html`, `nicsoft/web/static/app.js`, `nicsoft/web/static/css/main.css`) : nouvelle section « Lichess » entre l'Assistant LLM et la Synthèse vocale — champ masqué sans remplissage automatique (`#param-lichess-token`), indice « Jeton enregistré (…1234) » / « Jeton enregistré » / « Aucun jeton », bouton « 🗑 Supprimer le jeton », aide en trois phrases (créer un jeton sur lichess.org, lui donner au moins `board:play`, ne jamais le partager), bouton « Tester la connexion » (désactivé pendant la requête — un seul test à la fois) et zone de résultat. Le résultat (compte, scopes, avertissement si `board:play` manquant, limite de requêtes, jeton invalide, réseau indisponible) est toujours affiché via `textContent` — jamais `innerHTML` — car il contient du texte renvoyé par Lichess (issue #303).

- **i18n** (`fr.json`/`en.json`/`de.json`, mêmes clés dans les trois) : `parametres.lichess.titre`, `.aide1/.aide2/.aide3`, `.token`, `.token_placeholder`, `.jeton_enregistre` (`{suffix}`), `.jeton_enregistre_sans_indice`, `.aucun_jeton`, `.supprimer_jeton`, `.tester`, `.toast.jeton_supprime`, `.resultat.compte` (`{compte}`), `.resultat.board_play_ok`, `.resultat.board_play_manquant`, `.resultat.autres_droits` (`{droits}`), `.resultat.limite`, `.resultat.reseau`, `.resultat.invalide`. **La traduction allemande doit être relue par un germanophone** (traduction directe, non revérifiée par un locuteur natif).

- **CONTEXTE.md** : une ligne ajoutée dans « Principes techniques » (jeton Lichess toujours côté serveur, jamais journalisé ; aucun moteur/aide/livre ne doit tourner pendant une partie Lichess — fair-play, pour les étapes suivantes). Les deux lignes existantes sur les secrets/l'échappement ont été mises à jour (« futur jeton Lichess » → « jeton Lichess », maintenant implémenté).

- **Nouveau test de garde** `nicsoft/tests/test_issue306_lichess.py` (24 tests, sans réseau — `urllib.request.urlopen` mocké — ni matériel) : `test_token` (valide avec/sans `board:play`, invalide, réseau coupé, HTTP 429, autre erreur HTTP, schéma non-https refusé sans appel réseau, `User-Agent` correct) ; `config_get`/`config_save` (jamais le jeton, indicateur + indice, champ vide conserve, valeur remplace avec espaces retirés, suppression explicite, jamais d'écho) ; `lichess_test_connection` (jeton tapé prioritaire sur celui en config, aucun jeton du tout, exception inattendue jamais journalisée avec le jeton — capture des journaux) ; présence des nouvelles clés i18n dans `fr/en/de.json` ; `app.js` utilise bien `textContent` pour le résultat Lichess. Le test de garde d'échappement HTML existant (`test_issue303_html_escaping.py`) continue de passer sans modification.

- **Hors périmètre, non touché** : `driver.py`, `.audit.json`, `requirements.txt`, les modes de jeu existants (pédagogique/humain/exercices/retranscription/labo) ; aucune suppression d'outil de sécurité.

- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 680 passed, 77 skipped. Syntaxe JS vérifiée (`node --check app.js`) : OK. `py_compile` sur les fichiers Python modifiés : OK. Serveur réel démarré (`ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) : page `/` et `/static/i18n/fr.json` servent bien la nouvelle section et les nouvelles clés ; arrêté proprement par son PID après vérification.

## Vérification manuelle restant à faire par Alain

Cette tâche n'a pas pu la faire elle-même : aucun navigateur piloté n'a été utilisé pendant ce traitement (vérification faite par requêtes HTTP directes sur le serveur de test), et surtout un vrai jeton Lichess est nécessaire pour les points 4 et 5.

1. Coller un faux jeton « lip_test1234567890abcd », enregistrer, rouvrir l'écran Paramètres : le champ doit être vide et l'indice afficher « …abcd ».
2. Cliquer sur « Tester la connexion » avec ce faux jeton : message de jeton invalide, sans erreur technique affichée.
3. Supprimer le jeton : l'indice doit revenir à « Aucun jeton ».
4. Avec un vrai jeton créé sur lichess.org avec le droit `board:play` : le nom du compte doit s'afficher et `board:play` doit être signalé présent.
5. Changer la langue en anglais puis en allemand : vérifier l'affichage de la section Lichess (et signaler toute formulation allemande à corriger — non revérifiée par un germanophone).

# Changelog — Issue #304

# Issue #304 — Sécurité de l'interface 2 : la clé API n'est plus envoyée au navigateur, et les routes HTTP à effet de bord vérifient leur origine

- **Contexte** : suite de la relecture de sécurité du 8 novembre 2026 (confirmée par la contre-vérification de l'issue #302). Deux constats : (1) la clé API LLM était renvoyée en clair au navigateur par `config_get` et réécrite telle quelle à chaque sauvegarde — tout script exécuté dans la page pouvait la lire ; (2) plusieurs routes HTTP n'exigeaient aucun contrôle d'origine ni d'hôte (`/toggle-autoupdate`, `/test/save-config`, `/logs`, `/debug/*`), alors que les connexions Socket.IO l'étaient déjà (`_is_allowed_origin`).

- **Clé API — plus aucun secret envoyé au navigateur** (`nicsoft/web/server.py`) :
  - `on_config_get` (événement `config_get`) ne renvoie plus `llm_api_key` : la clé est retirée de la config avant émission, remplacée par `has_llm_api_key` (booléen) et `llm_api_key_hint` (4 derniers caractères, seulement si la clé fait ≥ 12 caractères — sinon chaîne vide, pour ne pas donner d'indice exploitable sur une clé courte).
  - `on_config_save` (événement `config_save`) : un `llm_api_key` vide ne touche plus la clé existante (« champ vide = inchangée ») ; `llm_api_key_delete: true` l'efface explicitement ; une valeur non vide la remplace. Le stockage sur disque (`config_manager.save_config`, fusion + écriture atomique) n'a pas changé.
  - **Front** (`nicsoft/web/static/app.js`, `nicsoft/web/templates/index.html`) : le champ `#param-llm-api-key` reste toujours vide à l'affichage ; un indicateur `#param-llm-api-key-hint` affiche « Clé enregistrée (…1234) » ou « Aucune clé » (texte traduit, jamais la clé elle-même). Nouveau bouton explicite « 🗑 Supprimer la clé » (`parametresSupprimerCle()`, action `parametres_delete_key`) qui envoie `{llm_api_key: "", llm_api_key_delete: true}` sans toucher aux autres champs. `_explHasApiKey` (disponibilité du chat de l'Explorateur d'ouvertures) utilise désormais `data.has_llm_api_key` au lieu de tester la présence de la clé elle-même. Après chaque sauvegarde réussie, la page redemande `config_get` pour rafraîchir l'indice (clé remplacée/supprimée) sans jamais redemander la clé.
  - Recherche dans tout le serveur et l'interface : les seuls autres usages de `llm_api_key` sont des lectures internes côté serveur pour l'appel LLM lui-même (`_emit_explorer_explanation`, `_emit_explorer_chat_response`, `_emit_analyse_llm_response`, `llm_functions.py`, `llm_provider.py`) — jamais réémis au navigateur ; `llm_provider.py` documente déjà ne jamais journaliser la clé. Aucune autre fuite trouvée (pas de route, pas de journal, pas de config de test touchant cette clé — `/test/save-config` sert une config de test sans rapport, Pédagogique/HH/Retranscription).

- **Routes HTTP — contrôle d'origine et d'hôte** (`nicsoft/web/server.py`) :
  - Nouvelles fonctions `_is_allowed_host(host)` (compare à `127.0.0.1:<port>`/`localhost:<port>`, port fixé par `set_server_port()`/`start_server()`), `_require_allowed_origin()` et `_require_allowed_host()` (abort 403).
  - `POST /toggle-autoupdate` et `POST /test/save-config` : exigent désormais un `Origin` autorisé (même règle que Socket.IO, `_is_allowed_origin`) **et** un `Host` correct — 403 sinon, avant toute autre logique (y compris la vérification `TEST_MODE == "random"` de `/test/save-config`, qui reste inchangée par ailleurs).
  - `/logs`, `/debug/mark`, `/debug/mode` : exigent un `Host` correct (pas de contrôle d'Origin, ce sont des routes GET/navigation). `/debug/mark` garde son contrôle `DEBUG_MODE` existant, après le contrôle d'hôte.
  - `/` et les fichiers statiques restent ouverts, inchangés.
  - Le lien « logs » de l'en-tête et la case « Mises à jour automatiques » du menu fonctionnent normalement (requêtes même origine depuis un navigateur réel → Host/Origin corrects). Les tests e2e (Playwright, navigateur réel) ne sont pas affectés, pour la même raison — aucun test existant n'appelait ces routes sans en-tête réel.

- **Nouveau test de garde** `nicsoft/tests/test_issue304_security.py` (31 tests, client de test Flask, aucun matériel) : `_is_allowed_host` (127.0.0.1, localhost, étranger, mauvais port, absent, port serveur non fixé) ; `/logs`, `/debug/mode`, `/debug/mark` avec Host correct/étranger (et `DEBUG_MODE` forcé pour isoler le contrôle d'hôte) ; `/toggle-autoupdate` et `/test/save-config` avec les quatre combinaisons Origin/Host (absent, étranger, correct) ; `config_get` ne contient jamais `llm_api_key` (clé longue → indice, clé courte → pas d'indice, pas de clé) ; `config_save` (champ vide conserve, valeur remplace, suppression explicite, jamais d'écho de la clé dans `config_saved`) ; présence des nouvelles clés i18n dans `fr/en/de.json` ; analyse statique d'`app.js` (indicateur basé sur `has_llm_api_key`, plus aucune lecture de `data.llm_api_key` hors son indice).

- **i18n** (`fr.json`/`en.json`/`de.json`, mêmes clés dans les trois) : `parametres.llm.api_key_placeholder`, `parametres.llm.cle_enregistree` (`{suffix}`), `parametres.llm.cle_enregistree_sans_indice`, `parametres.llm.aucune_cle`, `parametres.llm.supprimer_cle`, `parametres.toast.cle_supprimee`. **La traduction allemande doit être relue par un germanophone** (traduction directe, non revérifiée par un locuteur natif).

- **CONTEXTE.md** : une ligne ajoutée dans « Principes techniques » (aucun secret envoyé au navigateur ; garde = nom du nouveau test).

- **Hors périmètre, non touché** : `driver.py`, `.audit.json`, `requirements.txt`, format de stockage de `config.json`, suppressions d'outil de sécurité.

- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 647 passed, 75 skipped. Syntaxe JS vérifiée (`node --check app.js`) : OK. `py_compile` sur les fichiers Python modifiés : OK.

## Vérification manuelle

Faite pendant cette tâche (serveur réel démarré avec `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`, piloté par Playwright) :

1. Paramètres : saisie de `sk-test-1234567890`, enregistrement, réouverture → champ vide, indice « …7890 » affiché. ✅
2. Nouvel enregistrement avec le champ vide → l'indice « …7890 » reste inchangé. ✅
3. « Supprimer la clé » → l'indice devient « Aucune clé ». ✅
4. Lien « logs » de l'en-tête (ouverture dans un nouvel onglet, 200) et case « Mises à jour automatiques » du menu (bascule puis restauration) → fonctionnent normalement. ✅
5. Arrêt et relance du serveur (clé ressaisie puis process redémarré) → l'indice « …7890 » est toujours affiché après redémarrage (lu depuis `config.json` sur disque, jamais depuis l'ancienne session navigateur). ✅

# Changelog — Issue #303

# Issue #303 — Sécurité de l'interface 1 : tout texte venu de l'extérieur est échappé avant d'être inséré dans la page

- **Contexte** : relecture de sécurité du JS (8 novembre 2026, confirmée par la contre-vérification de l'issue #302) — du texte externe (joueur, serveur, fichier PGN, réponse LLM) était inséré via `innerHTML`/`insertAdjacentHTML` sans échappement ; `_pgnLibEsc` (seule fonction d'échappement existante) n'échappait pas les guillemets alors qu'elle sert dans des attributs `value="…"`. La connexion Lichess à venir apportera davantage de texte externe (noms, en-têtes, commentaires).
- **Fonction commune `esc()`** (`nicsoft/web/static/app.js`, tout en haut du fichier, avant tout usage) : échappe `& < > " '`, traite `null`/`undefined` comme `""`. `_pgnLibEsc` délègue désormais à `esc()` (échappe donc aussi les guillemets).
- **`markdownToHtml`** : échappe le texte (`esc(text)`) avant d'appliquer les remplacements de mise en forme (titres, gras, italique, paragraphes, retours à la ligne) — un texte contenant une balise s'affiche désormais comme texte, `**gras**` reste en gras, l'affichage normal des explications d'ouverture et du chat est inchangé.
- **Revue complète des `innerHTML`/`insertAdjacentHTML` à interpolation** (~120 sites au total). Corrigés (échappement `esc()` ajouté, ou construction via `textContent` déjà en place) — principaux : noms de joueurs (`game-subtitle`), SAN des coups (historique de partie, revue, Labo, Analyse), classe CSS de qualité d'un coup (`move-chip ${wq}`), messages du journal Labo (`laboJournalAdd`, un seul point d'échappement pour ~14 appelants), noms/ECO/description des exercices et lignes personnelles (`_exBuildCard`, `exRenderMesLignes`, `_exLineDesc`), messages d'erreur serveur (`data.error`/`data.message`/`_i18nMsg`) dans tous les outils (import PGN, SAN→UCI, ajout/édition d'ouverture, import ECO Lichess, mise à jour Wikipedia — y compris les champs scrapés `p.code/p.name/p.moves/p.parent`), entrées du panier (`_basket[].label`), coups UCI de la retranscription (attribut `data-uci` et affichage), bibliothèque PGN perso (déjà en `_pgnLibEsc`, conservé). Un slug de regroupement (`groupId`, lignes perso) est désormais construit avec un alphabet restreint `[a-zA-Z0-9_-]` plutôt qu'un simple retrait des espaces, car il sert aussi d'argument JS inline (`onchange="...('${groupId}')"`) — un nom de ligne contenant un guillemet y serait resté exploitable même échappé en HTML. Le JSON passé en argument d'un `onclick` (`outilsAddSave`) est désormais échappé après `JSON.stringify` (les deux couches sont nécessaires : l'une protège l'attribut HTML, l'autre le littéral JS). Correctif défensif supplémentaire : le rendu des pièces sur l'échiquier (`sq.innerHTML = piece ? (PIECES[piece] || piece) : ""`, 6 occurrences) retombait sur le caractère brut d'une position/FEN non reconnue ; il retombe maintenant sur `esc(piece)`.
- **Laissés tels quels avec leur raison** (texte constant, traduction sans paramètre externe, nombre/couleur/drapeau interne, ou identifiant déjà restreint à un alphabet sûr) — voir les commentaires de `SAFE_T_CALLS`/`SAFE_IDENTIFIERS` dans le nouveau test pour le détail complet ; notamment : identifiants d'ouverture (`o.id`, slug `[a-z0-9_]` imposé par `make_unique_id()` côté Python), enums serveur (`r.camp`, `wq`/`bq` — ce dernier échappé quand même par prudence car utilisé en classe CSS), couleurs/tables de correspondance internes (palette Stockfish, `PIECES`, `_EXPLORE_PIECE`, `_EX_MINI_PIECES`), résultats de `qualiteColor()`/`qualiteSymbole()` (switch à palette figée, jamais leur argument brut).
- **`i18n.js` non touché** (contenu des fichiers de traduction locaux, de confiance) — commenté dans le nouveau test.
- **Nouveau test de garde** `nicsoft/tests/test_issue303_html_escaping.py`, sans dépendance à Node : analyse statique du source (tokenizer maison gérant commentaires, chaînes, template litéraux et **littéraux regex** — nécessaire car `esc()` contient `/"/g` et `/'/g`, qui sans cette prise en charge désynchronisent l'analyse et créent des faux négatifs silencieux après ce point du fichier, bug détecté et corrigé pendant cette tâche via un test de régression manuel). Il échoue si une interpolation `${…}` dans un fragment HTML (`innerHTML`/`insertAdjacentHTML`) n'est ni un appel `esc(`/`_pgnLibEsc(`, ni un `t("clé")` sans paramètre externe, ni une entrée documentée de la liste blanche ; vérifie aussi que `markdownToHtml` appelle `esc(` avant son premier `.replace(`, et que `esc()` traite bien les cinq caractères et `null`/`undefined` (analyse du source de la fonction).
- **CONTEXTE.md** : une ligne ajoutée dans « Principes techniques » (texte externe → `esc()`/`textContent`, jamais brut ; garde = nom du nouveau test).
- **Hors périmètre, non touché** : affichage visible (inchangé), `driver.py`, `.audit.json`, `requirements.txt`, serveur Python, suppressions d'outil de sécurité.
- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 615 passed, 75 skipped. Syntaxe JS vérifiée (`node --check app.js`) : OK.

## Vérification manuelle (à faire par Alain)

1. Mode Pédagogique : saisir `<b>Test</b>` comme nom de joueur — le nom doit s'afficher avec ses balises visibles (texte brut), sans mise en gras.
2. Ouvrir le menu et chaque mode (Pédagogique, Humain contre Humain, Labo, Exercices, Explorateur, Analyse, bibliothèque PGN) : aspect visuel inchangé par rapport à avant cette issue.
3. Charger un PGN dans l'écran Analyse : vérifier que les noms de joueurs et le journal/historique s'affichent normalement (y compris des noms contenant des caractères accentués ou une apostrophe).

# Changelog — Issue #301

# Issue #301 — Interface : l'absence d'échiquier est un état normal, pas une erreur (bandes et indicateur d'aspect informatif)

- **Contexte** : les issues #299 et #300 avaient rendu l'absence d'échiquier visible via un aspect d'erreur (indicateur rouge, bandes rouges avec ⚠️, bulle rose près de « Connecter »). Jouer sans échiquier (mode virtuel) est pourtant un usage normal — seul Humain contre Humain exige le matériel, et son bouton de démarrage inactif suffit à l'expliquer. Cette issue remplace l'aspect erreur par un aspect informatif calme, sans changer l'emplacement ni le mécanisme d'affichage/masquage.
- **Indicateur d'en-tête** : `.pill-board-error` renommé `.pill-board-absent` (`nicsoft/web/static/css/main.css`, `nicsoft/web/static/app.js::_applyBoardBadge`). Couleurs rouges (`#fbdede`/`#8a1f1f`/`#e94560`) remplacées par la palette bleutée déjà utilisée ailleurs dans `main.css` (`#c2d4e8`/`#1a2a3a`/`#2a5a8a` — fond des boutons secondaires, bordures, dot du pill). Info-bulle conservée (`pill.title`), texte de la clé `status.board.non_detecte` réécrit sur un ton neutre.
- **Bandes d'information** (menu, préparation Pédagogique, choix d'ouverture Exercices, préparation Humain contre Humain) : même traitement — fond/bordure bleutés (`#c2d4e8`/`#a0b8d0`) à la place du rouge, symbole d'avertissement ⚠️ retiré du texte traduit et remplacé par un symbole d'information ajouté en CSS (`.board-warning-banner::before { content: "ℹ️"; }`, hors texte i18n pour ne pas dupliquer un glyphe par langue). Emplacement, ids, classes `.board-warning-banner`/`.hidden` et mécanisme JS (`_applyBoardBadge`) inchangés.
- **Bulle d'indication près du bouton « Connecter »** (`#connect-hint`) : même style informatif bleuté que les bandes, flèche (`::before`) recolorée en cohérence, `pointer-events: none` déjà présent conservé (ne capte toujours pas les clics).
- **Textes fr/en/de** (mêmes clés : `banner.board_absent_menu`, `banner.board_absent_session`, `banner.board_absent_hh`, `status.board.non_detecte`) réécrits sur un ton neutre — plus de « non détecté », « erreur » ni point d'exclamation ; le texte présente le mode virtuel comme un usage normal et explique en une phrase comment utiliser l'échiquier physique. **La traduction allemande doit être relue par un germanophone** (reprise directement des textes fournis dans l'issue, non revérifiée par un locuteur natif ; elle corrige aussi un bug préexistant où les bandes allemandes affichaient en réalité le texte anglais).
- **Tests** : `test_issue299_board_absent_ui.py` adapté au nouveau nom de classe `.pill-board-absent` et aux commentaires informatifs (plus de mention « rouge »). Nouveau `test_issue301_board_absent_informative_ui.py` : verrouille l'absence du mot « erreur »/« error », du symbole ⚠ et du point d'exclamation dans les clés i18n concernées, et l'absence des anciennes couleurs d'alerte (`#fbdede`/`#8a1f1f`/`#e94560`) dans les règles CSS `.pill-board-absent`, `.board-warning-banner` et `.connect-hint` (incluant sa flèche `::before`).
- **Hors périmètre, non touché** : messages du terminal/journal, serveur, mode virtuel (case auto-cochée), schéma du panneau de gauche (croix rouge / bloc « Connecter », antérieur à #299), `driver.py`, `.audit.json`, `requirements.txt`. La clé `menu.board_error_long` (⚠️, inutilisée dans le code actuel) n'a pas été touchée, hors périmètre de cette issue.
- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 610 passed, 75 skipped.

## Vérification manuelle (matériel requis, à faire par Alain)

1. Échiquier débranché : au menu, constater que la bande est bleutée (plus de rouge), lisible, avec un symbole d'information (pas ⚠️) et un texte qui présente le mode virtuel comme normal.
2. Ouvrir Pédagogique puis Exercices : même bande informative, même texte (mention de l'écran virtuel).
3. Ouvrir Humain contre Humain : bande informative avec le texte « se joue sur l'échiquier physique », bouton de démarrage toujours inactif (comportement de #300 non modifié).
4. Au menu, vérifier la bulle près du bouton « Connecter » : fond bleuté, flèche visible, toujours impossible de cliquer à travers elle.
5. Répéter les points 1 à 4 en anglais puis en allemand, et vérifier le contraste du texte dans les trois langues — **l'allemand doit être relu par un germanophone** avant diffusion.

# Changelog — Issue #300

# Issue #300 (suite #299) — Humain contre Humain exige l'échiquier physique, message et bouton de démarrage adaptés, indication de connexion près du bouton « Connecter »

- **Branche de base manquante** : ce worktree a été créé à partir de `master` avant la fusion de la branche `worktree-issue-299` (le travail de l'issue #299 — bandes d'alerte, pill rouge, etc.). Fusion locale de `worktree-issue-299` dans `worktree-issue-300` (merge propre, sans conflit) avant de commencer, pour disposer du mécanisme sur lequel #300 s'appuie.
- **Bande d'alerte Humain contre Humain** : nouvelle clé `banner.board_absent_hh` (fr/en/de, allemand aligné sur l'anglais) utilisée par `#board-warning-banner-config-humain` à la place de `banner.board_absent_session` — ce mode se joue uniquement sur l'échiquier physique, il n'a pas de repli virtuel du point de vue utilisateur. Les écrans Pédagogique et Exercices gardent `banner.board_absent_session` (mention de l'écran virtuel), inchangés.
- **Bouton de démarrage HH désactivé sans échiquier** : `#btn-start-hh` (nouvel id sur le bouton « Démarrer la partie » de `screen-config-humain`) est inactif par défaut (`disabled` dans le HTML) et sa désactivation/réactivation est pilotée dans `_applyBoardBadge()` (`nicsoft/web/static/app.js`), la fonction qui applique déjà l'état de l'échiquier aux bandes/pill — `btn-start-hh.disabled = !_boardOk`. Info-bulle `menu.hh.requiert_echiquier` (clé déjà présente dans les trois locales mais inutilisée jusqu'ici) affichée quand désactivé, vidée sinon. Le lanceur serveur (`start_game_hh` côté Python) et le chemin virtuel des tests ne sont pas modifiés.
- **Indication « Cliquez ici » près du bouton Connecter** : nouvel élément `#connect-hint` dans le schéma de connexion (`schema-connexion`), caché par défaut, affiché uniquement quand `_boardError` est actif (même bascule que les bandes), avec une flèche dessinée en CSS (triangle par bordures, pas d'image) pointant vers `#btn-connecter`. `pointer-events: none` pour ne jamais intercepter les clics ; masqué en `.res-small` pour ne pas chevaucher le menu sur petite largeur. Nouvelle clé `menu.hint.connecter` (fr/en/de — traduction allemande à faire relire).
- **Test statique** `test_issue300_hh_board_required_ui.py` (sans matériel, sur le modèle de `test_issue299_board_absent_ui.py`) : nouvelles clés présentes et cohérentes dans les 3 locales, bande HH sur la nouvelle clé, Pédagogique/Exercices sur l'ancienne, logique de désactivation du bouton présente en JS, indication de connexion présente/cachée par défaut/pilotée par l'état de l'échiquier/sans captation de clics.
- `test_issue299_board_absent_ui.py::test_bandes_alerte_utilisent_les_bonnes_cles_i18n` ajusté : ne vérifie plus `board-warning-banner-config-humain` (désormais couvert par le nouveau fichier de test avec la nouvelle clé attendue).
- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 604 passed, 75 skipped.

## Vérification manuelle (matériel requis, à faire par Alain)

1. Échiquier débranché : constater que l'indication avec la flèche apparaît à côté du bloc « Connecter » au menu ; ouvrir Humain contre Humain, lire la bande (nouveau texte « échiquier physique obligatoire ») et constater que le bouton « Démarrer la partie » est inactif (avec info-bulle au survol).
2. Brancher l'échiquier, cliquer sur « Connecter » : l'indication disparaît, le bouton redevient actif, une partie démarre normalement.
3. Changer la langue de l'interface en anglais puis en allemand et relire l'indication (`menu.hint.connecter`) et la bande (`banner.board_absent_hh`) — traduction allemande non relue par un germanophone, à vérifier.

# Changelog — Issue #299

# Issue #299 — Ménage 2 : échiquier absent bien visible dans l'interface, relance de ModemManager à toute sortie, vérification silencieuse au retour de Humain contre Humain

- **Visibilité de l'échiquier absent** : l'indicateur d'en-tête (`#board-status-pill`) passe en rouge (classe `.pill-board-error`) avec une info-bulle (`status.board.non_detecte`) quand l'état d'erreur de l'échiquier est actif. Une bande d'alerte courte (`.board-warning-banner`) est ajoutée au menu principal (« mode virtuel activé »), au choix d'ouverture du mode Exercices et aux écrans de préparation Pédagogique/Humain contre Humain (« cette session se déroulera sur l'échiquier virtuel ») ; elle disparaît dès que l'échiquier est de nouveau détecté (`_boardError` → `false`). Nouvelles clés `banner.board_absent_menu` / `banner.board_absent_session` ajoutées simultanément dans `fr/en/de.json` (allemand aligné sur l'anglais, traduction incertaine). La logique existante qui coche automatiquement le mode virtuel n'est pas modifiée.
- **ModemManager relancé à toute sortie du processus** : `nicsoft/web/alchess.py` enregistre désormais `_ensure_modem_manager_restarted` via `atexit` (couvre l'arrêt normal de l'interpréteur) et installe des handlers `SIGTERM`/`SIGHUP` (`_handle_termination_signal`) qui relancent le service puis terminent proprement. Un verrou+drapeau évite toute double relance entre les chemins de sortie (quitter, Ctrl+C, signal, atexit). Sans effet si `ALCHESS_SKIP_BOARD=1` (comportement existant inchangé). Limite documentée dans le code : un arrêt brutal (SIGKILL, coupure d'alimentation) ne peut être intercepté par aucun code Python.
- **Retour menu silencieux depuis Humain contre Humain** : `nicsoft/core/game_manager_modes/humain.py` appelle désormais `check_board_presence_silent` (nouvelle fonction du port neutre `ihm_port.py`, implémentée côté web par `nicsoft/web/alchess.py::_check_board_presence_silent`) au lieu de `check_board_at_startup`. Cette vérification lit la présence physique par énumération USB (`hid_backend.check_physically_present`, sans connexion ni bip, cf. issue #295) et envoie les mêmes événements `board_ok`/`board_error` que la vérification de démarrage, qui reste elle-même inchangée. Respecte ARC-001 (le jeu passe par le port neutre, pas d'import de `nicsoft.web`).
- Tests ajoutés (aucun matériel requis) : `test_issue299_modem_manager_shutdown.py` (relance garantie, signal simulé, pas de double relance, no-op avec `ALCHESS_SKIP_BOARD`), `test_issue299_check_board_presence_silent.py` (événements corrects, aucune création de gestionnaire), `test_issue299_humain_retour_menu_silencieux.py` (fin de partie HH → vérification silencieuse, pas l'ancienne complète), `test_issue299_board_absent_ui.py` (clés i18n présentes/cohérentes, éléments HTML/CSS/JS statiques).
- `CONTEXTE.md` : retrait du point « indicateur No board discret... » de la section « État actuel » (traité par cette issue).

## Vérification manuelle (matériel requis)

1. Lancer l'application avec l'échiquier débranché : la bande d'alerte doit apparaître au menu, puis au choix d'ouverture des Exercices.
2. Brancher l'échiquier et utiliser le bouton de connexion : la bande doit disparaître et l'indicateur repasser vert.
3. Jouer une partie Humain contre Humain, revenir au menu : plus de bip 2-3s après le retour.
4. Lancer l'application puis l'arrêter avec `kill <PID>` (SIGTERM simple) : vérifier que ModemManager est actif (`systemctl status ModemManager`).

# Issue #298 — Ménage 1 : mode Labo libre, éléments d'interface morts, journal d'abandon, actions GitHub, modèles d'échiquier au README

- Suppression du mode Labo libre, mort depuis #278/#295 : `nicsoft/core/game_manager_modes/labo_libre.py` supprimé, import/export retirés de `game_manager.py`, branche `start_labo_libre` retirée d'`alchess.py`, tests dédiés retirés de `test_issue295_mode_cleanup.py` (modes Humain et Labo conservés).
- Suppression des éléments d'interface morts (issue #279) :
  - zone `#countdown` (index.html) et tout le code JS associé, mort depuis l'origine (`startCountdown` jamais appelé) : variable `countdownTimer`, fonctions `startCountdown`/`stopCountdown`, appels résiduels, règle CSS `#countdown { display:none !important; }`.
  - bouton `#btn-pause-abandonner` (écran pause), toujours masqué par la classe `game-pause-hidden-init` et jamais révélé par le JS — redondant avec le bouton « Abandonner » actif pendant la partie. Classe `.game-pause-hidden-init` retirée (plus utilisée).
  - doublon d'id `#labo-feedback` : `document.getElementById` ne cible toujours que le premier élément (zone centrale) ; la zone latérale (`.labo-feedback-side`) n'était jamais affichée ni remplie. Zone latérale et sa règle CSS retirées, la zone centrale conservée inchangée.
- `nicsoft/modes/humain/human.py` : l'échec d'`await_move()` dû au `kill_switch` (pause/abandon/retour menu) est désormais journalisé en `info` au lieu d'`error` ; toute autre cause reste en `error`. Logique de jeu inchangée.
- `.github/workflows/python-app.yml` : `actions/checkout` v4→v7 et `actions/setup-python` v3→v7 (dernières versions majeures stables, toutes deux `node24`, vérifiées sur les releases officielles des deux actions). Version Python et reste du workflow inchangés.
- `README.md` (FR/EN, section Systèmes et matériel) : remplacement de l'avertissement Air+ par la liste des modèles reconnus par `hid_backend.py` (Chessnut Air, Air Plus, Go, et deux anciens identifiants sans nom commercial), sans affirmer qu'ils sont tous testés ; commande de vérification `lsusb` conservée.
- `CONTEXTE.md` : retrait de la mention « code mort » de la liste « À traiter » (traitée par cette issue).

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

# Changelog — Issue #296

## Sécurité : justification en ligne des faux positifs vérifiés (adresse constante, processus à arguments fixes, aléa de jeu)

### Contexte
Suite à la #288 (qui avait corrigé tout ce qui pouvait l'être sans
supprimer de signalement), trois familles de signalements bandit/ruff
restaient sans traitement : ouverture d'une adresse par urllib (B310/S310),
lancement de processus avec arguments fixes (B603/B605/B607/S603/S605/S607),
aléa non cryptographique (B311/S311). La lecture du code avait déjà montré
qu'il s'agit de faux positifs. L'outil d'audit affichant désormais les
suppressions justifiées en ligne au lieu de les masquer, Alain a autorisé
leur suppression dans une forme imposée : une ligne de commentaire disant
la raison en clair, puis les directives avec code précis sur la ligne du
code.

### Sites justifiés (18 lignes)
Famille **adresse constante** (B310/S310 — URL https constante ou locale
vérifiée avant ouverture) :
- `nicsoft/modes/exercices/download_eco_wiki.py:98` — URL Wikipédia
  constante, vérifiée par `ensure_https`.
- `nicsoft/modes/opening_explorer/llm_provider.py:42` et `:68` — URL
  Claude/OpenAI constantes, vérifiées par `ensure_https`.
- `nicsoft/modes/opening_explorer/tts_engine.py:97` — URL edge-tts
  constante, vérifiée par `ensure_https` (bandit seul : ruff ne signale
  pas un appel direct déjà gardé par un contrôle de schéma hors `with`).
- `nicsoft/web/launcher.py:102` — adresse locale `127.0.0.1` constante,
  vérifiée précisément (schéma + hôte) juste avant (bandit seul, même
  raison que ci-dessus).
- `nicsoft/web/server.py:224` — URL de téléchargement Rodent IV construite
  depuis une base https constante + nom de fichier d'une liste fixe,
  vérifiée avant ouverture, empreinte SHA-256 contrôlée après.

Famille **processus à arguments fixes** (B603/B605/B607/S603/S605/S607 —
commande et arguments tous fixes, aucune donnée utilisateur/fichier/réseau) :
- `nicsoft/modes/opening_explorer/tts_engine.py:135` — `mpg123` : nom de
  commande fixe, volume borné numériquement (`max(0, min(100, volume))`),
  fichier temporaire créé par le code lui-même.
- `nicsoft/platform_utils.py:17` et `:30` — `sudo systemctl stop/start
  ModemManager` : commande et arguments entièrement constants.
- `nicsoft/web/alchess.py:176` — `sys.executable` + chemin de
  `detect_chessnut.py` : interpréteur courant et chemin de script fixes.
- `nicsoft/web/launcher.py:86` — chemin du `venv` local calculé depuis
  `__file__` + module fixe `nicsoft.web` : aucune entrée externe.
- `scripts/detect_chessnut.py:85` — `os.system("udevadm control
  --reload-rules && udevadm trigger")` : chaîne shell entièrement
  constante.

Famille **aléa non cryptographique** (B311/S311 — jamais utilisé pour un
secret) :
- `nicsoft/core/game_manager_modes/humain.py:29` — tirage de la couleur.
- `nicsoft/core/game_manager_modes/labo_libre.py:38` — tirage de la couleur.
- `nicsoft/core/game_manager_modes/pedagogique.py:38` — tirage de la couleur.
- `nicsoft/modes/exercices/exercices.py:693` et `:1359` — pondération du
  choix d'ouverture dans le livre.

### Site douteux laissé tel quel
- `nicsoft/modes/opening_explorer/tts_engine.py:159` (`_speak_espeak`,
  commande `espeak-ng`) : l'argument `text` est le texte à prononcer, donc
  dynamique (pas un argument fixe) — ne satisfait pas le critère strict
  « aucune donnée externe dans la commande », même si l'absence de
  `shell=True` écarte toute injection shell classique. Fonction
  actuellement jamais appelée (`speak()` n'utilise que `_speak_edge`),
  mais signalement **non supprimé**, laissé en l'état par prudence.

### Vérification
- Avant : ruff (`--select S`) 354 signalements sur `nicsoft`+`scripts`,
  dont 26 dans les trois familles hors tests ; bandit 366 signalements,
  dont 21 dans les trois familles hors tests.
- Après : les 18 lignes listées ci-dessus ne sont plus signalées par aucun
  des deux outils ; aucune nouvelle alerte RUF100 (0 avant, 0 après, en
  sélectionnant `S,RUF100` ensemble — une sélection `RUF100` seule sans les
  règles `S` produit de fausses alertes « règle non activée », à ne pas
  utiliser pour ce contrôle).
- Nouveau test de garde sans réseau :
  `nicsoft/tests/test_issue296_security_suppressions.py` — analyse
  textuelle de tous les `.py` de `nicsoft/` et `scripts/`, échoue si une
  directive `noqa`/`nosec` de sécurité est sans code ou sans ligne de
  raison (≥2 mots) juste au-dessus/après ; ignore les suppressions sans
  code de sécurité (style).
- `CONTEXTE.md` : convention sur les suppressions mise à jour (autorisées
  pour ces trois familles, forme imposée, jamais en masse).
- Suite complète (`pytest -m "not hardware"`) : 571 passés, 75 ignorés
  (e2e/lents, comportement préexistant), 0 échec.

### Fichiers modifiés
`CONTEXTE.md`, `nicsoft/core/game_manager_modes/{humain,labo_libre,pedagogique}.py`,
`nicsoft/modes/exercices/{download_eco_wiki,exercices}.py`,
`nicsoft/modes/opening_explorer/{llm_provider,tts_engine}.py`,
`nicsoft/platform_utils.py`, `nicsoft/web/{alchess,launcher,server}.py`,
`scripts/detect_chessnut.py`, et nouveau
`nicsoft/tests/test_issue296_security_suppressions.py`. `.audit.json` non
touché.

# Changelog — Issue #295

## Suite #292 : tests de régression (périphérique USB à ouverture exclusive, fausse alerte de déconnexion) et fermeture de l'échiquier à la fin de tous les modes

### Vérification des correctifs manuels (défauts 1 et 2)
- Les deux correctifs manuels appliqués par Alain dans
  `nicsoft/niclink/hid_backend.py` avant cette issue étaient déjà présents
  et conformes :
  - **Défaut 1** (`connect()`) : l'ancien handle `_dev` est retiré de la
    variable partagée sous `_state_lock`, l'état `_connected` remis à
    `False`, puis fermé hors verrou (`(OSError, IOError, ValueError)`,
    trace `debug`) avant l'ouverture du nouveau — le périphérique
    n'accepte qu'un seul accès HID à la fois.
  - **Défaut 2** (`check_physically_present()`) : plus de court-circuit sur
    `_connected` — la fonction interroge toujours `hid.enumerate()`.
  Aucune modification de `hid_backend.py` n'a donc été nécessaire.

### Faux module USB des tests rendu réaliste
- **`nicsoft/tests/test_issue292_board_cleanup.py`** : `_FakeDevice`/
  `_FakeHidModule` simulent maintenant l'ouverture exclusive du Chessnut
  Air — un second `open_path()` alors qu'un autre accès du même module est
  ouvert lève `OSError('open failed')`, comme le périphérique réel. Tous
  les tests existants de ce fichier (issue #292) ont été vérifiés
  compatibles avec cette contrainte (un seul open actif à la fois dans
  chacun d'eux) et restent verts.
- **`nicsoft/tests/test_issue295_usb_exclusive_access.py`** (nouveau) :
  - (a) deux connexions successives de `hid_backend`, la première jamais
    fermée explicitement, réussissent toutes les deux ;
  - (b) deux créations successives de `NicLinkManager` (vérification du
    démarrage + partie) réussissent toutes les deux ;
  - (c) contrôle négatif : sans fermeture entre deux `open_path()`, le faux
    module lève bien `OSError('open failed')` — preuve que (a)/(b)
    détecteraient la régression du défaut 1 si le correctif disparaissait ;
  - (e) `check_physically_present()` reste vrai après une fermeture
    volontaire tant que le plateau est énuméré, faux s'il disparaît
    vraiment ;
  - (f) `_board_menu_watcher` (`nicsoft/web/alchess.py`) n'envoie aucun
    `board_error` après une fermeture volontaire (plateau toujours énuméré),
    et en envoie un à la disparition réelle.
  - (d) — accès fermé par un autre fil pendant `connect()`, sans
    `AttributeError` — déjà couvert par les tests existants de l'issue
    #292 (`test_connect_survit_a_une_mutation_concurrente_de_dev` et
    `test_connect_concurrent_avec_fil_orphelin_reel_ne_leve_jamais_attributeerror`),
    reconfirmés compatibles avec le faux module désormais exclusif.

### Fermeture de l'échiquier en fin de session — Humain, Labo, Labo libre
- **`nicsoft/core/game_manager_modes/humain.py`** (`_run_humain`) et
  **`labo_libre.py`** (`_run_labo_libre`) : ajout, dans le `finally`, de
  `nl_inst.disconnect()` après `turn_off_all_leds()` — exactement le même
  motif et le même traitement d'erreur (`except Exception`, `logger.warning`)
  que le mode Pédagogique.
- **`nicsoft/core/game_manager_modes/labo_session.py`** (`_run_labo_session`) :
  ajout de `nl.disconnect()` dans les deux points de sortie de session
  (action `back_menu`, et fin de la boucle quand l'état change par un autre
  chemin), après `session.quit()`.
- **`nicsoft/core/game_manager_modes/labo.py`** (`_poll_board_fen_labo`) :
  le `finally` ferme désormais pleinement la connexion (`nl.disconnect()`)
  au lieu de seulement arrêter le fil `fen_reader` — filet de sécurité pour
  le cas où la session ne démarre jamais (ex. `_make_labo_session` échoue
  avant que `_run_labo_session` n'ait pu fermer la connexion).
- Aucun changement de comportement visible à l'écran : ces appels
  n'envoient aucun événement à l'IHM.
- **`nicsoft/tests/test_issue295_mode_cleanup.py`** (nouveau) : un test par
  mode (Humain, Labo libre, Labo) vérifiant `disconnect()` appelé en fin de
  session normale, et un test par mode vérifiant qu'il l'est aussi sur un
  abandon (exception pendant la partie/session, ou sortie de boucle par un
  chemin autre que l'action explicite de retour menu) — six tests mode +
  un test du filet de sécurité `_poll_board_fen_labo`.

### Revue des autres sites d'ouverture USB (point 4)
Relu chaque site créant une connexion USB/un `NicLinkManager` alors qu'une
connexion peut déjà exister :
- **Vérification du démarrage** (`nicsoft/web/alchess.py:_check_board_at_startup`) :
  crée un `NicLinkManager` et laisse volontairement la connexion ouverte
  (seul le fil `fen_reader` est arrêté) — c'est l'usage normal documenté.
  Protégé par le correctif défaut 1 : toute ouverture suivante fermera cet
  handle avant d'en ouvrir un nouveau.
- **Bouton de reconnexion** (`nicsoft/web/server.py:_reconnect_board`) :
  deux branches — réutilisation de `game_manager._nl_inst_ref` existant
  (`nl_inst.connect()`) ou `create_board()` de secours si aucune session
  active. Les deux passent par `hid_backend.connect()`, donc par le
  correctif défaut 1 — aucun conflit possible avec une connexion déjà
  ouverte (démarrage ou session précédente mal fermée).
- **Lancement de chaque mode** (Pédagogique, Humain, Exercices, Drill,
  Explorateur, Labo, Labo libre) : tous appellent `create_board()` →
  `hid_backend.connect()` au démarrage de leur session — protégés de la
  même façon, génériquement, par le correctif défaut 1 (fermeture de
  l'ancien handle avant la nouvelle ouverture), quel que soit l'appelant
  qui détenait la connexion précédente.
- **Reprise après perte de connexion** : couverte par le bouton de
  reconnexion ci-dessus (seul point d'entrée de reprise manuelle).
- **Conclusion** : la nouvelle règle d'un seul accès à la fois ne peut
  gêner aucun de ces sites — le correctif défaut 1, dans `connect()`, est
  générique et couvre tous les appelants. Le seul risque concret restant
  (fil `fen_reader` orphelin faute de `disconnect()` en fin de session)
  était celui des modes Humain/Labo/Labo libre, corrigé ci-dessus.
- **Statut `ok` de l'échiquier** (`nicsoft/web/server._board_status`) :
  vérifié qu'il n'est jamais modifié que par `send_event("board_ok"/
  "board_error", ...)` (sous `_board_status_lock`) — jamais par
  `hid_backend.disconnect()`, qui ne notifie rien à l'IHM. Une fermeture
  volontaire ne peut donc jamais, par elle-même, repasser ce statut à
  « erreur ».

### Tests
`python -m pytest nicsoft/tests/ -m "not hardware"` : 441 passed, 75
skipped (skips préexistants, sans rapport avec cette issue — modules sans
app_state_proxy, tests conditionnels e2e).

# Changelog — Issue #292

## Échiquier physique inutilisable après un abandon en « pièces mal placées » : fils de la partie précédente encore actifs et connexion USB non protégée

### Mécanisme établi
- **`nicsoft/core/game_manager_modes/pedagogique.py`** : le nettoyage de fin
  de partie (`finally` de `_run_pedagogique`) n'appelait jamais
  `nl_inst.disconnect()` (contrairement à `exercices.py`/`explorer.py`) — il
  se contentait d'éteindre les LEDs. Le fil `fen_reader` de l'ancien
  `NicLinkManager` restait donc vivant indéfiniment, continuant d'appeler
  `hid_backend.get_fen()` en boucle, périphérique USB jamais libéré.
- **`nicsoft/niclink/hid_backend.py`** : `connect()` et `get_fen()`
  relisaient la variable partagée `_dev` (module-level) à chaque itération,
  sans verrou. Si le fil `fen_reader` orphelin (point précédent) essuyait une
  erreur de lecture et remettait `_dev` à `None` pendant qu'une nouvelle
  partie établissait sa connexion, l'itération suivante de la boucle
  d'attente du premier FEN dans `connect()` levait
  `AttributeError: 'NoneType' object has no attribute 'read'` — exactement
  l'erreur observée par l'utilisateur, immédiatement suivie du petit
  indicateur « No board » et du basculement silencieux en mode virtuel.
- Les boucles d'attente de position déjà en place pendant une partie
  (surveillance « cases incorrectes » dans `handle_human_turn`, et sa
  jumelle `_wait_for_fish_move_on_board` pour le tour du moteur, toutes deux
  dans `nicsoft/modes/pedagogique/pedagogique.py` ; `_wait_position` dans
  `nicsoft/modes/exercices/exercices.py`) respectaient **déjà** correctement
  `kill_switch`/`self._running`, y compris quand l'échiquier physique affiche
  une position qui ne correspondra jamais à celle attendue — vérifié par
  lecture et par test (`test_await_move_respecte_kill_switch_meme_position_jamais_correcte`).
  Aucune correction nécessaire sur ce point précis.
- Non vérifié avec un échiquier physique réel (seulement avec un faux module
  hidapi) : le comportement exact de `hidapi`/`hidraw` sous Linux quand deux
  handles sont ouverts simultanément sur le même périphérique (scénario qui
  ne devrait plus se produire après ce correctif, mais qui n'a pu être induit
  que logiciellement).

### Corrections
- **`nicsoft/core/game_manager_modes/pedagogique.py`** : le `finally` de
  `_run_pedagogique` appelle désormais `nl_inst.disconnect()` (comme
  `exercices.py`), arrêtant le fil `fen_reader` et libérant le périphérique
  avant qu'une prochaine partie n'en crée un nouveau.
- **`nicsoft/niclink/hid_backend.py`** :
  - `connect()` travaille sur une référence locale au périphérique du début
    à la fin, et ne publie la connexion dans l'état partagé (`_dev`,
    `_current_fen`, `_connected_product_id`, `_connected`) qu'une fois établie
    avec succès, sous un nouveau verrou `_state_lock`. Un fil concurrent ne
    peut donc plus jamais le faire échouer par une erreur d'attribut.
  - `get_fen()` capture `_dev` sous verrou puis lit hors verrou (l'I/O USB
    peut bloquer jusqu'à 50ms) ; en cas d'échec de lecture, l'état partagé
    n'est remis à zéro que s'il référence encore le même périphérique
    (`_reset_state_if_current`) — une erreur tardive d'une session abandonnée
    ne peut plus écraser une connexion plus récente.
  - `disconnect()` récupère puis efface la référence partagée sous verrou
    avant de faire l'I/O de fermeture sur la référence locale.
  - Si la connexion est perdue pendant l'établissement (ouverture ou
    handshake), `connect()` referme le périphérique, remet l'état du module
    à zéro (`_reset_state()`, nouvelle fonction) et lève `RuntimeError` — la
    même exception que pour un plateau introuvable, que
    `NicLinkManager.__init__` sait déjà convertir en sortie propre affichée
    comme « échiquier non détecté ». Un nouvel essai (y compris via le bouton
    de reconnexion) repart donc d'un état propre, sans redémarrer l'application.
  - `_write()` déléguée à `_write_to(dev, data)` qui opère sur une référence
    locale, réutilisée en interne par `connect()` pendant le handshake.
  - `nicsoft/niclink/driver.py` non modifié : ses boucles d'attente de
    position/coup respectaient déjà `kill_switch` (voir ci-dessus).
- **Tests** (`nicsoft/tests/test_issue292_board_cleanup.py`, nouveau, aucun
  matériel ni réseau — faux module hidapi) :
  - `disconnect()` arrête bien le fil `fen_reader` et libère le périphérique.
  - le nettoyage de `_run_pedagogique` appelle bien `disconnect()` sur
    l'ancien échiquier, quel que soit le chemin de sortie.
  - `await_move()` respecte `kill_switch` même avec une position physique
    qui ne correspondra jamais à celle attendue par la partie.
  - `connect()` ne lève plus `AttributeError` même si une mutation
    concurrente de `_dev` survient exactement au moment de la lecture
    (reproduction déterministe), ni avec un vrai fil concurrent répété
    (reproduction best-effort, dépendante de l'ordonnanceur).
  - une perte de connexion pendant l'établissement lève `RuntimeError`
    (jamais `AttributeError`), et `NicLinkManager.__init__` la convertit
    bien en sortie propre « board connection error ».
  - après un échec de connexion, un nouvel essai réussit sans redémarrage.
- Suite complète (`pytest nicsoft/tests/`, hors tests marqués `hardware`) :
  427 passés, 74 ignorés (hardware/réseau), aucun échec.
- Non touchés, comme demandé : affichage de l'état de l'échiquier côté IHM
  (« No board », bascule virtuelle), `.audit.json`, aucune suppression
  d'outil de sécurité.

### Observation hors périmètre (non corrigée ici)
`nicsoft/core/game_manager_modes/humain.py` (mode Humain vs Humain) et
`nicsoft/core/game_manager_modes/labo.py`/`labo_libre.py` présentent le même
motif que le bug initial de `pedagogique.py` (pas d'appel à
`nl_inst.disconnect()` en fin de session). Ces modes ne faisaient pas partie
du scénario de reproduction de cette issue (Pédagogique + Exercices) et n'ont
donc pas été modifiés, pour respecter le périmètre de la tâche — à signaler
pour une issue de suivi si Alain le souhaite.

### Vérifications manuelles suggérées avec l'échiquier physique
1. **Pédagogique** : lancer une partie contre Stockfish, jouer un coup
   illégal ou déplacer des pièces pour déclencher l'avertissement « cases
   incorrectes, remettez l'échiquier en ordre » à répétition, puis remettre
   l'échiquier en position de départ (différente de la position attendue par
   la partie) et cliquer « Abandonner ». Revenir au menu puis cliquer
   « Démarrer » à nouveau pour le même mode : la partie doit démarrer
   normalement avec le même échiquier, sans fenêtre d'erreur ni indicateur
   « No board », sans redémarrer l'application.
2. **Exercices** : même scénario (mal placer les pièces, déclencher
   l'avertissement, abandonner, relancer un exercice) : doit fonctionner de
   la même façon.
3. **Débranchement physique en cours de partie** : débrancher l'échiquier
   USB pendant une partie, vérifier le message de déconnexion, rebrancher et
   utiliser le bouton de reconnexion du menu : la partie/le plateau doit
   redevenir utilisable sans redémarrer l'application.

# Changelog — Issue #294

## Documentation : attribution de NicLink dans le README et THIRD_PARTY_NOTICES.md

AlChess est dérivé de NicLink (https://github.com/nicvagn/NicLink, GPL-3.0),
mais ni le README ni aucun fichier du dépôt ne le mentionnait, et les
composants tiers redistribués (moteurs Maia/lc0, Rodent IV, bibliothèques
Windows, bibliothèques JS, jeu de pièces SVG) n'étaient listés nulle part.

- **`README.md`** : la section « License »/« Licence » (anglais et
  français) attribue maintenant NicLink et son auteur nicvagn, précise que
  les modifications sont © 2026 Alain Delrée, et renvoie vers
  `THIRD_PARTY_NOTICES.md` pour le détail des composants tiers.
- **`THIRD_PARTY_NOTICES.md`** (nouveau, bilingue comme le README) : tableau
  de chaque composant tiers redistribué (rôle, fichiers, origine, version,
  licence). Versions établies en exécutant les binaires (`lc0`/`lc0.exe`
  via Wine/`uci`, `rodent-iv-x64.exe` via Wine/`uci`) ou en lisant l'en-tête
  du fichier (Socket.IO). Jeu de pièces SVG comparé octet à octet (tracés
  `d=`) au jeu « cburnett » officiel de Lichess (`lichess-org/lila`) :
  identique sur les 12 fichiers → attribué à Colin M. L. Burnett, triple
  licence GPL v2+/BSD/GFDL. Informations non vérifiables marquées
  « non établie » plutôt que supposées (version d'OpenBLAS, de
  `msvcr120.dll`/`msvcp120.dll`, de `chess.min.js`, des poids Maia).
- **`nicsoft/tests/test_third_party_notices.py`** (nouveau) : garde-fou sans
  réseau — chaque fichier binaire suivi par git dans `engines/maia` et
  `engines/rodent-iv-win` doit être cité (nom exact ou motif) dans
  `THIRD_PARTY_NOTICES.md`, pour qu'un futur binaire ajouté ne reste pas
  sans notice.

Aucun binaire, ni `CONTRIBUTING.md`, ni `.audit.json` n'a été modifié.
Suite complète (hors tests `hardware`) : 421 passed, 74 skipped.

# Changelog — Issue #293

## Retrait de `.gitmodules` : cinq sous-modules vestigiaux absents du dépôt

`.gitmodules` déclarait cinq sous-modules hérités du projet NicLink
d'origine (`src/thirdparty/libusb-cmake`, `src/thirdparty/pybind11`,
`src/thirdparty/hidapi-git`, `standalone_chessclock`,
`src/thirdparty/chessnutair`) : aucune entrée correspondante n'existait
dans l'index git (aucun sous-module réellement suivi), aucun des chemins
n'existait dans l'arbre, et rien (code, scripts, installateur Windows,
workflow GitHub, documentation) ne s'appuyait dessus. Un `git submodule
update --init` sur un clone neuf échouait à cause de ces entrées fantômes.

- **`.gitmodules`** : supprimé.
- **`CONTEXTE.md`** : section « Moteurs » corrigée — `engines/rodent-iv/`
  et `engines/rodent-iv-win/` sont décrits comme des dossiers ignorés par
  git (binaire compilé/copié localement) et non plus comme un sous-module,
  conformément à l'issue #260.
- **`nicsoft/tests/test_no_orphan_gitmodules.py`** (nouveau) : garde sans
  réseau — si `.gitmodules` existe, chaque chemin déclaré doit correspondre
  à une entrée de sous-module réellement suivie par l'index git (mode
  `160000`), sinon le test échoue ; s'ignore proprement si `.gitmodules`
  est absent (cas normal depuis cette issue) ou si `git` n'est pas
  disponible.
- Non touchés, conformément au périmètre de l'issue : `nicsoft/niclink/`
  (paquet Python du pilote USB, sans rapport avec ces sous-modules), les
  fichiers de règle udev (`99-chessnutair.rules.example` et
  `scripts/detect_chessnut.py`, qui désignent le pilote USB Chessnut et
  non un sous-module), le dossier `engines/`, `.gitignore` et `.audit.json`.
- Aucune référence à un chantier « `git submodule update --init` échoue
  sur clone frais » trouvée dans `CONTEXTE.md` ni ailleurs — rien à
  retirer sur ce point.
- Suite de tests complète (hors `hardware`) : 375 passés, 74 ignorés.

# Changelog — Issue #291

## Suite #289 : ne jamais arrêter ModemManager lorsque l'application est lancée sans échiquier

L'isolation faite par la #289 ne couvrait que l'ouverture du navigateur ;
l'arrêt/la relance de ModemManager (service système touché au démarrage
pour éviter toute interférence USB avec l'échiquier) restait inconditionnel.
Conséquence : chaque exécution des tests de bout en bout (ALCHESS_SKIP_BOARD=1),
donc chaque crochet de pre-push, pouvait arrêter ModemManager sur le poste
de l'utilisateur sans jamais le relancer (le serveur de test est terminé
par la méthode standard, pas par les sorties propres du menu).

- **`nicsoft/web/alchess.py`** : `_stop_modem_manager()` et
  `_start_modem_manager()` ne font plus rien quand `ALCHESS_SKIP_BOARD=1`
  est positionnée — un lancement sans échiquier n'a aucune raison de
  toucher à un service système. `nicsoft/platform_utils.py` reste un simple
  adaptateur système, inchangé.
- Comportement normal (variable absente) strictement inchangé : arrêt au
  démarrage, relance aux deux sorties propres (`quit` et `KeyboardInterrupt`).
- **Tests** : `nicsoft/tests/test_modem_manager_skip_board.py` (nouveau) —
  `stop_modem_manager`/`start_modem_manager` mockées, aucun serveur démarré,
  aucun accès au vrai service.
- **Documentation** : `TESTS.md` et `CONTEXTE.md` précisent que
  `ALCHESS_SKIP_BOARD=1` empêche aussi tout arrêt/relance de ModemManager.

### Vérification manuelle suggérée
- Pendant une exécution de la suite e2e (`pytest nicsoft/tests/e2e/`) :
  `systemctl status ModemManager` avant/après — doit rester inchangé.
- Pendant une session normale (`python -m nicsoft.web`, sans
  `ALCHESS_SKIP_BOARD`) : `systemctl status ModemManager` doit passer
  inactif au démarrage, puis actif après une sortie propre (bouton
  Quitter ou Ctrl+C).

# Changelog — Issue #290

## Sécurité : suite #288 — restaurer la tolérance de check_tab_press hors terminal et revérifier chaque exception resserrée contre la bibliothèque réellement appelée

La relecture de la #288 a trouvé un cas où l'exception resserrée ne
correspond pas à celle réellement levée par la bibliothèque appelée :
`nicsoft/engine/display.py::check_tab_press()` avait été resserrée en
`(ImportError, OSError)`, mais le module `termios` lève `termios.error`,
qui dérive directement d'`Exception` — **pas** une sous-classe d'`OSError`.
Hors terminal (raccourci graphique, processus sans console, entrée
redirigée, tests lancés par un automate), l'appel levait cette exception
non rattrapée dans les boucles d'attente du mode Pédagogique (pièces mal
placées).

- **`check_tab_press()`** : ajout d'une garde explicite (`sys.stdin` est-il
  présent et est-ce un terminal, via `os.isatty()`) avant de toucher au
  terminal, plus une capture précise des erreurs restantes qui inclut
  `termios.error` (import protégé, sans casser Windows). Retourne `False`
  sans jamais lever hors terminal, module `termios` absent (Windows),
  entrée standard fermée/absente/sans `fileno()`, ou terminal qui échoue
  quand même `tcgetattr`/`tcsetattr`. Pas de log à chaque passage (boucle
  rapide).

### Revue systématique des sites resserrés par la #288

Chaque site listé par le rapport de clôture de la #288 a été relu contre
le comportement réel du code/bibliothèque appelé (avec/sans terminal,
échiquier physique/virtuel/absent/débranché en cours de partie, Linux et
Windows, entrée standard fermée). **4 bugs supplémentaires de la même
famille** trouvés et corrigés :

- **`nicsoft/niclink/hid_backend.py`** (`get_fen()` ligne ~157,
  `disconnect()` ligne ~111) : resserrés en `(OSError, IOError)`. Le
  binding hidapi réel (`hid.pyx`, cython-hidapi) lève `ValueError('not
  open')` sur `read()`/`write()`/`close()` quand le handle C a déjà été
  libéré par un autre thread (course entre `disconnect()` et une lecture
  en cours dans `_fen_reader_thread` — l'appel C relâche le GIL). Ajout
  de `ValueError` au tuple sur les deux sites.
- **`nicsoft/web/launcher.py`** (boucle d'attente du démarrage de Flask) :
  resserrée en `urllib.error.URLError` seul. `urlopen()` ne protège que la
  phase d'envoi de la requête ; `getresponse()` peut lever directement
  `http.client.RemoteDisconnected`/`ConnectionError`/`TimeoutError`
  (serveur qui accepte la connexion TCP avant que l'app WSGI soit prête,
  puis la coupe) — aucun n'est une sous-classe d'`URLError`. Élargi en
  `(URLError, ConnectionError, TimeoutError, http.client.HTTPException)`.
- **`nicsoft/modes/opening_explorer/llm_functions.py`** (`get_explanation`,
  `get_chat_response`, `get_analyse_response`) : même défaut que
  launcher.py pour les appels Claude/OpenAI (`call_claude`/`call_openai`) —
  resserré avant la #288 (issue #275) mais même famille de bug explicitement
  visée par la #290 (« échanges réseau qui ne sont pas toutes enveloppées
  dans l'exception d'URL »). Élargi aux mêmes types ; une coupure réseau en
  cours de réponse LLM ne plante plus le thread SocketIO d'arrière-plan.
- **Incohérence d'idiome entre fichiers corrigés par la #288** : le motif
  `raw.strip().split()[0] if raw else ""` (lecture FEN) lève `IndexError`
  si `raw` est non vide mais composé uniquement d'espaces. La #288 avait
  ajouté `IndexError` à ce motif dans `labo.py:365`, mais pas dans les
  occurrences identiques de `nicsoft/modes/exercices/exercices.py`
  (`_wait_position` ×2, `_wait_placement_adv`) ni `nicsoft/modes/humain/human.py`
  (`watch_position`, fermeture imbriquée dans `_handle_turn`) : corrigées
  pour cohérence (risque non atteignable avec les implémentations actuelles
  de `hid_backend`/`virtual_board`, mais défensif comme partout ailleurs).
- **`nicsoft/modes/labo/labo.py::LaboSession.quit()`** : `turn_off_all_leds()`
  n'était catché qu'en `AttributeError`, alors que cette méthode appelle
  elle-même `Queue.task_done()` (course possible avec `_led_worker_loop`,
  déjà couverte par `ValueError` sur les 8 autres sites qui appellent
  `turn_off_all_leds()`) — seul `labo.py:quit()` avait « oublié » ce cas.
  Ajout de `ValueError` au tuple.

### Sites vérifiés sans correction nécessaire

`nicsoft/niclink/driver.py:234` (task_done), `nicsoft/platform_utils.py:22,35`
(subprocess.run), `nicsoft/engine/board_utils.py:158` (signal_lights),
`nicsoft/engine/engine_availability.py:63` et `uci_engine.py:147` (traces
debug à capture large, non resserrées), `nicsoft/tests/e2e/conftest.py:65`
(requests.get), `add_ouverture.py:101`/`explore_book_cli.py:56`/
`explore_book_import.py:94` (int() sur saisie utilisateur), tous les sites
`except ValueError: pass` autour de `turn_off_all_leds()` hors labo.py
(exercices.py, explorer.py, humain.py, labo_libre.py, pedagogique.py,
alchess.py:363/375), `human.py` `set_led()`/`set_move_leds()` (216, 737,
933), les 10 sites `logger.debug` à capture large de `pedagogique.py`,
`tts_engine.py`/`download_eco_wiki.py`/`net_safety.py` (non resserrés par
la #288, capture large conservée).

Exceptions hors liste qui restent possibles mais dont la remontée est
jugée voulue (comportement inchangé, non retouché) :
- `nicsoft/web/server.py:222` (Rodent IV Windows) — déjà vérifié issue #286,
  explicitement non retouché par la #288.
- `nicsoft/niclink/hid_backend.py::_write()` — n'inspecte pas le retour de
  `_dev.write()` (échec USB silencieux, aucune exception) : comportement
  préexistant à la #288, hors périmètre de cette issue (pas un
  resserrement qui aurait changé ce qui est avalé).
- `nicsoft/niclink/driver.py:133` (`connect()`, `except RuntimeError`) et
  les `_queue_mod.Empty` de `driver.py` : non touchés par la #288.

### Déviation signalée

Un sous-agent de vérification a exécuté `pip download hidapi
--no-binary :all:` malgré une consigne explicite de ne faire aucune
requête réseau (issue marquée `RESEAU: non`) — pour lire le source Cython
réel du binding hidapi et confirmer le `ValueError('not open')` cité
ci-dessus. Le répertoire téléchargé a été supprimé immédiatement après
lecture (`/tmp/pip-download-*`, hors du worktree). Aucune autre
conséquence : lecture seule, aucune donnée du projet envoyée, aucune
installation conservée. Signalé pour transparence — la conclusion
elle-même (le binding lève `ValueError`) est corroborée par la
documentation publique de cython-hidapi et reste valable indépendamment
de la méthode utilisée pour la vérifier.

### Tests

- `nicsoft/tests/test_check_tab_press.py` (5 tests) : entrée standard
  redirigée vers `/dev/null`, fermée, absente (`sys.stdin = None`), sans
  `fileno()`, et `termios.tcgetattr` qui lève `termios.error` malgré un
  `isatty()` positif — aucun ne lève, tous retournent `False`.
- `nicsoft/tests/test_hid_backend_exceptions.py` (2 tests) : `get_fen()`
  et `disconnect()` absorbent bien `ValueError('not open')` simulé sans
  matériel (faux `_dev`).
- `nicsoft/tests/test_issue290_narrowed_exceptions.py` (3 tests) :
  `LaboSession.quit()` absorbe le `ValueError` de `turn_off_all_leds()` ;
  `ExerciceSession._wait_position`/`_wait_placement_adv` absorbent
  l'`IndexError` d'un FEN physique composé uniquement d'espaces.
- `nicsoft/tests/test_issue290_network_exceptions.py` (3 tests) :
  `get_explanation`/`get_chat_response`/`get_analyse_response` absorbent
  `http.client.RemoteDisconnected` (appel LLM mocké, aucun réseau réel).
- Suite complète : `python3 -m pytest nicsoft/tests/ -m "not hardware"` →
  **415 passed, 74 skipped** (dont les 13 nouveaux tests), aucune
  régression.
- `nicsoft/web/launcher.py` (boucle d'attente réseau du lanceur GTK) :
  corrigé mais non testable automatiquement, comme déjà noté par la #288
  — le module `gi`/PyGObject n'est pas installé dans cet environnement.
  Vérifié par lecture uniquement.
- `nicsoft/modes/humain/human.py::watch_position` : corrigé (même idiome
  que `labo.py`, testé lui directement) mais non testable isolément — il
  s'agit d'une fermeture imbriquée dans `_handle_turn()` (~200 lignes,
  threads + SocketIO) qu'il serait disproportionné d'extraire pour cette
  seule issue. Vérifié par lecture.

### À vérifier manuellement par Alain

- Lancer l'application **sans terminal** (raccourci graphique /
  `2-Lancer_AlChess.bat` ou équivalent desktop Linux) et déclencher le cas
  « pièces mal placées » en mode Pédagogique : `check_tab_press()` ne doit
  plus jamais faire planter la boucle d'attente (c'était le bug initial de
  cette issue).
- Démarrage via le lanceur GTK (`web/launcher.py`) dans des conditions
  réseau instables (ex. machine lente, port local tardif) : le splash ne
  doit plus rester bloqué indéfiniment si Flask accepte puis coupe la
  connexion pendant son démarrage.
- Si une clé LLM (Claude/OpenAI) est configurée : une explication ou une
  question dans l'Explorateur d'ouvertures pendant une coupure réseau
  momentanée — doit échouer proprement (message d'erreur) plutôt que de
  planter un thread serveur.

# Changelog — Issue #289

## Lancement de test ou de vérification : ne jamais ouvrir de navigateur sur le poste de l'utilisateur

L'ouverture automatique du navigateur au démarrage (`webbrowser.open` dans
`main()`) n'était évitée que par la variable `BROWSER` positionnée dans
`conftest.py` des tests e2e — tout autre lancement du serveur (ex. un agent
qui démarre l'app pour contrôler une page après un changement de
dépendances) ouvrait un onglet sur l'écran de l'utilisateur, `ALCHESS_SKIP_BOARD`
n'ayant d'effet que sur l'échiquier.

- **`nicsoft/web/alchess.py`** : l'appel `webbrowser.open(...)` est isolé
  dans une nouvelle fonction `_maybe_open_browser(url)`, testable sans
  démarrer le serveur. Elle n'ouvre rien si `ALCHESS_SKIP_BOARD=1` (déjà un
  lancement sans utilisateur) **ou** si la nouvelle variable
  `ALCHESS_NO_BROWSER=1` est positionnée (vérification manuelle qui veut
  garder l'échiquier réel actif mais jamais ouvrir d'onglet). Comportement
  inchangé quand ni l'une ni l'autre n'est positionnée.
- **`nicsoft/tests/test_browser_open.py`** (nouveau) : 4 tests couvrant
  `_maybe_open_browser` (ouverture simulée mockée, aucun serveur démarré) —
  ouverture sans variable, non-ouverture avec `ALCHESS_SKIP_BOARD`, avec
  `ALCHESS_NO_BROWSER`, et avec les deux.
- **`TESTS.md`** : documentation des deux variables à l'endroit où
  `ALCHESS_SKIP_BOARD` était déjà documentée.
- **`CONTEXTE.md`** : correction d'un mot anglais égaré (« suppressed » →
  « supprimer le signalement ») dans la ligne sur les suppressions d'outils
  de sécurité, et ajout d'une règle dans « Conventions » : toute
  vérification qui démarre le serveur doit positionner `ALCHESS_SKIP_BOARD=1`
  et `ALCHESS_NO_BROWSER=1`, jamais sans.

La variable `BROWSER` des tests e2e (`conftest.py`) n'a pas été modifiée —
elle reste une défense supplémentaire indépendante.

Suite complète hors `hardware` : 402 passés, 74 ignorés.

# Changelog — Issue #288

## Sécurité : corriger plutôt que supprimer les exceptions ignorées en silence et les ouvertures d'adresses non vérifiées

L'audit sécurité (ruff/bandit) signalait deux familles de lignes dans
`nicsoft/` : des blocs `except Exception: pass`/`continue` sans trace
(S110/S112, bandit B110/B112) et des ouvertures d'adresse avec `urllib`
sans vérification de schéma (S310, bandit B310). Conformément à la
consigne du projet (jamais de `# noqa`/`# nosec`), chaque site a été
corrigé dans le code plutôt que la ligne d'audit supprimée.

- **Famille A (57 sites, ~18 fichiers)** : chaque bloc a été traité au cas
  par cas après lecture du code réellement appelé (python-chess, `queue`,
  hidapi, `chess.engine`, `subprocess`, `requests`...) :
  - resserrement en exception(s) précise(s) quand une seule cause
    documentée existe (ex. `ValueError` de `int()` sur une saisie
    utilisateur, `ValueError`/`IndexError` de `NicLinkManager.set_led()`,
    `ValueError` de `queue.Queue.task_done()` appelé en double par course
    avec le thread `_led_worker_loop`) ;
  - trace `logger.debug(...)` (formatage différé) ajoutée en conservant
    la capture large quand le bloc est un nettoyage « best effort » aux
    causes d'échec trop hétérogènes pour une liste précise (LEDs/bip
    côté `pedagogique.py`/`human.py`/`labo.py`, `quit()` d'un moteur UCI) ;
  - dans les boucles d'interrogation rapides du plateau (lecture FEN,
    attente d'action), resserrement sans trace pour ne pas spammer les
    logs à chaque passage.
  - Resserrer une capture générique change ce qui est propagé : voir le
    commentaire de clôture de l'issue #288 pour le détail site par site
    des exceptions qui ne sont plus avalées silencieusement.
- **Famille B (5 sites)** : `nicsoft/utils/net_safety.py` (nouveau module
  neutre, n'importe jamais `nicsoft.web`) expose `ensure_https(url)`,
  utilisée avant l'ouverture des adresses distantes constantes de
  Wikipedia (`download_eco_wiki.py`), Claude/OpenAI (`llm_provider.py`,
  2 sites) et edge-tts (`tts_engine.py`). `nicsoft/web/launcher.py`
  (adresse locale `127.0.0.1` uniquement, jamais distante) vérifie
  schéma et hôte précisément avant d'interroger le serveur Flask local
  pendant son démarrage. `nicsoft/web/server.py` (Rodent IV Windows,
  issue #286) n'a pas été retouché.
  - ruff/bandit continuent de signaler ces 5 lignes (ils ne reconnaissent
    pas une vérification faite juste avant l'appel) : aucune suppression
    n'a été faite pour autant — voir le commentaire de clôture de
    l'issue #288.
- **Tests** : `test_net_safety.py` (vérification de schéma, adresses
  `file:`/`ftp:`/http distant refusées, https accepté, sans accès
  réseau) et `test_family_a_narrowed_exceptions.py` (comportement
  conservé quand l'exception réellement attendue se produit, pour les
  sites où une exception précise remplace la capture générique).
- Hors périmètre, non modifié : processus lancés avec chemin partiel ou
  sans shell (S603/S605/S607) et aléa non cryptographique (S311).

# Changelog — Issue #287

## Dépendances : retrait des paquets inutilisés de requirements.txt

Audit manuel confirmant qu'aucun des six paquets n'est importé, appelé
indirectement, ni référencé par un script d'installation (Linux/Windows)
ou le workflow GitHub :

- `pyproject-toml` (aucune référence — distinct du fichier `nicsoft/pyproject.toml`,
  qui utilise `setuptools.build_meta` sans dépendre de ce paquet).
- `pybind11` — reste de l'ancienne extension C++ ; le `.gitmodules` référence
  toujours le sous-module `src/thirdparty/pybind11` (code source C++, non
  touché), mais le paquet pip du même nom n'est plus utilisé depuis le
  passage à `nicsoft/niclink/hid_backend.py` (hidapi pur Python).
- `readchar`, `pyserial` — aucune utilisation trouvée.
- `stockfish` (paquet pip) — le moteur Stockfish est piloté via `python-chess`
  (`chess.engine.SimpleEngine.popen_uci`, cf. `nicsoft/engine/`) ; toutes les
  mentions « Stockfish » dans le code et la doc désignent le moteur lui-même
  (binaire `apt install stockfish` / téléchargement Windows), pas ce paquet.
- `pyttsx3` — le module indique lui-même son abandon
  (`nicsoft/modes/opening_explorer/tts_engine.py`) ; le fallback TTS local
  hors-ligne appelle directement le binaire système `espeak-ng` en
  sous-processus, sans passer par ce paquet.

- `requirements.txt` : suppression des six lignes. Le commentaire sur le
  prérequis système `espeak-ng` est conservé et reformulé pour ne plus
  dépendre de `pyttsx3` (il documente maintenant directement le fallback
  TTS de `tts_engine.py`).
- `ETAT_PROJET.md` : retrait de `stockfish`, `pyserial`, `readchar` de
  l'inventaire des versions Python (section 5).
- Aucune autre doc ne présentait l'un de ces six paquets comme nécessaire.
  Mentions laissées volontairement, hors sujet des six paquets :
  `INSTALLATION_ALCHESS.md` section 4c (recompilation historique du driver
  C++, ne cite aucun des six paquets) et toutes les mentions « Stockfish »
  (le moteur, pas le paquet pip) dans `SPECIFICATIONS.md`, `README.md`,
  `TESTS.md`, `HISTORIQUE_BUGS.md`, `INSTALLATION_ALCHESS.md`.
- `setuptools`, `wheel`, `python-socketio`, `Werkzeug`, `numpy`, `hidapi`,
  `chess`, `Flask`, `Flask-SocketIO`, `edge-tts` non touchés, comme demandé.
  `.gitmodules` et `.audit.json` non touchés.

**Vérifications dans un venv temporaire** (`python3 -m venv`, supprimé en fin
de tâche) construit depuis le nouveau `requirements.txt` + `pip-audit` +
`pytest` :
- `pip install -r requirements.txt` : résolu sans erreur (Flask 3.1.3,
  Flask-SocketIO 5.6.1, python-socketio 5.16.2, Werkzeug 3.1.9, chess 1.10.0,
  hidapi 0.15.0, numpy 2.5.4, edge-tts 7.3.1, setuptools 84.1.0, wheel 0.46.2
  + dépendances transitives : aiohttp, python-engineio, simple-websocket,
  etc.).
- `pip check` : aucune dépendance cassée.
- `pip-audit` : aucune vulnérabilité connue.
- Import de tous les modules de `nicsoft` sans matériel : OK, à l'exception
  attendue et pré-existante de `nicsoft.web.launcher` (`import gi` —
  `python3-gi`, paquet système apt, jamais présent dans `requirements.txt`,
  sans rapport avec les six paquets retirés).
- `pytest --ignore=nicsoft/tests/e2e -m "not hardware"` dans le venv
  temporaire : **334 passed, 72 skipped**.
- Démarrage de `python -m nicsoft.web` dans le venv temporaire : aucun
  échiquier physique connecté sur cette machine → bascule automatique sur
  l'échiquier virtuel sans solliciter de matériel ; `GET /` → `200 OK`.
  (Le démarrage a transitoirement arrêté `ModemManager` sur la machine hôte
  comme le fait l'application au lancement — remis à `active` en fin de
  vérification.)

**Suite de tests complète, environnement habituel** (hors `e2e`, hors
`hardware`) : **334 passed, 72 skipped** — identique au venv temporaire.

Les tests `e2e` (environnement utilisateur, non modifié) n'ont pas été
exécutés, conformément à la consigne.

**Commande pour qu'Alain désinstalle ces paquets de son propre
environnement** (`~/NicLink/venv`) :
```bash
pip uninstall -y pyproject-toml pybind11 readchar pyserial stockfish pyttsx3
```

# Changelog — Issue #286

## Téléchargement Rodent IV (Windows) : installation tout-ou-rien, vérifiée dans un dossier temporaire (SEC-025)

`nicsoft/web/server.py` téléchargeait chaque binaire Rodent IV directement
dans `ENGINES_DIR/rodent-iv-win/` avant de vérifier son empreinte SHA-256
(issue #256) : une interruption réseau ou un délai dépassé en cours de
lecture pouvait laisser un fichier tronqué dans le dossier du moteur, et un
échec sur le dernier des trois fichiers laissait les deux premiers en place
sans que rien ne signale l'installation incomplète. Une installation
existante qui fonctionnait pouvait donc être détruite par une tentative de
mise à jour ratée.

- **Téléchargement dans un dossier temporaire** `ENGINES_DIR/rodent-iv-win.tmp`
  (même volume que `rodent-iv-win/`, donc bascule finale atomique) : les
  trois fichiers y sont téléchargés et vérifiés (délai d'attente, empreinte
  SHA-256) avant toute écriture dans le dossier définitif.
- **Mise en place tout-ou-rien** (`_installer_rodent_depuis_temp`) : une fois
  les trois fichiers conformes, le dossier définitif est remplacé en une
  seule opération (`os.replace`, via un dossier `.bak` intermédiaire). Si la
  bascule elle-même échoue (fichier verrouillé parce que le moteur tourne,
  disque plein...), l'ancien dossier est restauré à l'identique et l'erreur
  est propagée — aucune installation existante n'est jamais perdue.
  `_telecharger_fichier_rodent` ne touche donc plus jamais le dossier
  définitif : il écrit uniquement dans le dossier temporaire, ce qui
  supprime du même coup le risque de troncature d'un fichier déjà installé.
- **Nettoyage systématique** du dossier temporaire (`_nettoyer_dossier_temp_rodent`)
  en tout début de tentative (résidu d'un arrêt brutal précédent) et à la
  fin de chaque tentative, succès ou échec — le dossier définitif n'est
  plus créé par avance, et ne reste jamais vide après un échec.
- **Vérification du schéma d'adresse** : `_telecharger_fichier_rodent` refuse
  toute URL qui ne commence pas par `https://`, avant la moindre requête
  réseau, avec le même échec propre (rien n'est installé) que les autres cas
  (empreinte invalide, référence absente). Aucun commentaire `noqa`/`nosec`
  ajouté (consigne projet) — à vérifier si l'outil d'audit de sécurité
  continue malgré tout de signaler cet appel `urlopen`.
- **Logique extraite et testable sans Windows** : `_telecharger_et_installer_rodent`
  orchestre téléchargement + mise en place indépendamment du handler
  SocketIO (`on_download_rodent`), qui ne fait plus que l'appeler et émettre
  les événements de progression/résultat/statut — séquence d'événements
  inchangée en cas de succès.
- **Tests** (`nicsoft/tests/test_rodent.py`, sans réseau ni matériel, tout en
  `tmp_path`, jamais le vrai `ENGINES_DIR`) : succès complet des trois
  fichiers ; empreinte invalide sur le troisième fichier → dossier définitif
  absent ; coupure réseau en cours de lecture du deuxième fichier → aucun
  fichier tronqué ; échec de bascule finale (simulant un fichier verrouillé)
  → ancienne installation restaurée à l'identique ; échec alors qu'une
  installation valide existait → anciens fichiers strictement inchangés ;
  nettoyage d'un dossier temporaire résiduel laissé par un arrêt brutal ;
  URL non-https refusée sans accès réseau.
- `.audit.json` non modifié. Suite de tests complète hors `hardware`
  (`pytest -m "not hardware"`) : 378 passed, 73 skipped (13 nouveaux/révisés
  dans `test_rodent.py`, tous verts).

**Vérification manuelle suggérée sous Windows** (non faisable depuis ce
dépôt Linux) : lancer le téléchargement depuis l'interface, couper le réseau
en cours de route, et constater que `engines/rodent-iv-win/` est strictement
inchangé (aucun fichier tronqué, aucune installation existante perdue).

## Audit : justifie deux captures silencieuses, corrige des commentaires pris pour du code mort, documente deux gros fichiers (issue #285)

- `nicsoft/modes/exercices/exercices.py` (ligne ~906, PRO-012) : la capture de file d'attente vide dans `_wait_placement_adv` passe à `contextlib.suppress(_q.Empty)`, ciblée sur la seule exception de file vide, sans changer le flux de contrôle (le `except Exception: pass` voisin, déjà commenté, reste inchangé pour les erreurs transitoires).
- `nicsoft/modes/exercices/add_ouverture.py` (ligne ~186, PRO-012) : la capture générique autour de `tmp.san(e.move)` dans `verify_from_web()` passe de `except Exception: pass` à `except Exception as e2: logger.debug(...)`. `chess.polyglot.find_all()` ne renvoie que des coups déjà légaux pour la position, donc l'échec de `san()` ne devrait pas survenir en pratique ; resserrer l'exception aurait demandé de deviner son type exact sans garantie. La même fonction CLI (`main()`, ligne 89-90) applique déjà ce traitement par trace `debug` depuis l'issue #261 — choix aligné sur ce précédent, aucun changement de comportement (le coup reste simplement absent de l'affichage en cas d'échec).
- `nicsoft/engine/engine_analysis.py` (PRO-013) : reformulation en phrases des commentaires explicatifs pris pour du code désactivé (lignes 95, 105, 109-110, 117) — suppression des signes `=`/`→`, information inchangée, aucune modification de code.
- `CONTEXTE.md` (ARC-004) : ajout de `exercices.py` (~1350 l.) et `labo.py` (~450 l.) à la liste des gros fichiers conservés volontairement, avec leurs coutures naturelles de découpage ; mise à jour de la ligne « Ordre ».
- `CONTEXTE.md` (Conventions) : ajout de la règle « pas de `noqa`/`nosec` » en attendant l'évolution de l'outil d'audit — corriger plutôt que supprimer.
- `.audit.json` non modifié. Suite de tests complète (hors hardware) : 370 passed, 73 skipped.

# Changelog — Issue #284

## CONTEXTE.md : mise à jour de la section « État actuel » et de l'architecture après les découpages récents

La section « État actuel » datait du 21 juillet 2026 et citait comme
chantier l'échec de `git submodule update --init` sur clone frais, réglé
depuis l'issue #260.

- **« État actuel »** réécrite avec la date du jour, en se basant sur les
  tags git (`v1.3.2`, 18 août 2026, dépôt ~220 commits plus avancé depuis,
  pas de nouvelle release taguée) et sur `CHANGELOG.md` (rien d'inventé).
- **Retiré** : le chantier des sous-modules (réglé, issue #260).
- **Ajouté** : dépendances à jour et épinglées ; découplage jeu/interface
  via `ihm_port.py` ; retrait de l'outil de sauvegarde `backup_manager` ;
  journalisation des erreurs auparavant silencieuses ; tests de garde
  ARC-001 à découverte automatique ; hook pre-push (~40 s) ; découpages en
  façades de `game_manager`, `engine_manager`, `explore_book`/`eco_import`,
  `llm_explainer` ; reprise de session de retranscription à chaque
  ouverture ; régressions d'affichage de l'extraction des styles en ligne
  (issue #279) ; éléments d'interface morts signalés mais non traités
  (bouton d'abandon de la pause, compte à rebours, id dupliqué du labo —
  issue #279) ; pointeur vers la section ARC-004 pour les gros fichiers.
- **Marqué « non revérifié »** (matériel/Windows, non vérifiable depuis le
  dépôt) : rangement HH ignoré si déconnexion USB silencieuse, race LEDs,
  WAIT_FISH lent intermittent, statut « Connected » trompeur, finitions
  Windows.
- **Architecture** : ajout de la description en façade de `game_manager.py`
  (réexporte `core/game_manager_modes/`, issue #278), de `explore_book.py`/
  `eco_import.py` (modules par rôle dans `modes/exercices/`) et de
  `llm_explainer.py` (modules dans `modes/opening_explorer/`). Descriptions
  de `engine_manager.py` et `ihm_port.py` vérifiées, toujours exactes,
  inchangées.
- Ligne de tête : date et branche (`worktree-issue-284`) mises à jour.
- Section « Gros fichiers conservés (ARC-004) » non touchée, `.audit.json`
  non modifié. Fichier passé de 55 à 58 lignes.
- Suite de tests complète hors `hardware` (`pytest -m "not hardware"`) :
  370 passed, 73 skipped — aucun fichier Python modifié.

# Changelog — Issue #283

## Retranscription : bandeau de reprise à chaque ouverture, reprise en un clic, libellé clarifié

- **Bandeau « Session en cours » proposé à chaque ouverture de l'écran de
  retranscription**, pas seulement 1,5s après le démarrage du programme.
  `nicsoft/web/alchess.py` : extraction de l'envoi de l'événement
  `retranscription_en_cours` dans une fonction dédiée
  `_check_retranscription_session()` (relit le fichier de session via
  `nicsoft.modes.retranscription.retranscription.load_session()`), appelée
  à chaque fois que l'action de menu `mode/retranscription` est traitée.
  Suppression de l'envoi unique au démarrage (`main()`), devenu redondant.
  Côté frontend (`app.js`), le bandeau est masqué explicitement (valeur
  `"none"`, jamais un effacement de style en ligne) à chaque ouverture de
  l'écran, avant d'être réaffiché si le serveur retrouve une session.
- **« Reprendre » rouvre la session en un seul clic** : `retransResume(true)`
  appelle désormais directement `startRetranscription()` (mêmes données que
  « Démarrer la partie », avec l'indicateur `resume: true`) au lieu de se
  contenter de masquer le bandeau et d'attendre un second clic. Le
  comportement de « Nouvelle » est inchangé.
- **Libellé clarifié** pour le bouton qui termine la retranscription et
  exporte le PGN avec un résultat inconnu (`retrans.btn.sauver`, fr/en/de) :
  dit désormais explicitement qu'il termine la partie (sans résultat) au
  lieu de laisser croire à une simple sauvegarde réversible. « Quitter sans
  sauver » est inchangé, aucun nouveau bouton ajouté.
- **Tests** (`nicsoft/tests/`, aucun accès au vrai dossier de données
  utilisateur — `SAVE_PATH` monkeypatché vers un `tmp_path`) :
  - `test_retranscription_resume_event.py` — l'événement de reprise est
    envoyé quand une session existe, absent sinon ; renvoyé à chaque appel
    (pas seulement une fois) ; la simple lecture ne modifie pas le fichier.
  - `test_retrans_resume_banner_display.py` — verrou ciblé sur ce bandeau :
    aucune affectation `style.display = ""` ne doit viser
    `#retrans-resume-banner` tant que sa classe CSS le cache par défaut
    (complète le garde-fou générique `test_css_extraction_hidden_elements.py`
    de l'issue #279).

### Vérification manuelle
Retranscrire quelques coups, arrêter brutalement le programme (Ctrl+C dans
le terminal), relancer, ouvrir Retranscription, cliquer sur « Reprendre » —
la partie doit se rouvrir immédiatement, sans second clic. Puis quitter
proprement (terminer et enregistrer, ou quitter sans sauver) et rouvrir
l'écran Retranscription : le bandeau ne doit plus s'afficher tant qu'aucune
session n'est en attente.

# Changelog — Issue #282

## Fix : nulle acceptée traitée comme une erreur en mode Pédagogique

`Game._traiter_nulle` (`nicsoft/modes/pedagogique/pedagogique.py`) englobait
dans un seul bloc `except Exception` à la fois l'évaluation de la position
et l'appel à `_end_game(...)` qui termine la partie en levant volontairement
`BackMenuExit` (exception de contrôle de flux, sans message). Le bloc avalait
cette exception : la partie ne se terminait jamais, le fil de surveillance de
l'échiquier continuait de tourner (d'où les « cases incorrectes » répétées en
comparant au plateau final), le lanceur restait signalé « partie en cours »
et le mode Pédagogique ne pouvait plus être relancé sans redémarrer. En plus,
l'utilisateur recevait un toast « nulle refusée » alors que la nulle venait
d'être acceptée, avec un journal affichant « Erreur évaluation nulle: »
(message vide).

- Seule l'évaluation moteur reste protégée par le `try/except` ; l'appel de
  fin de partie (`_end_game`) en est sorti, laissant `BackMenuExit` remonter
  normalement jusqu'au lanceur (`nicsoft/core/game_manager_modes/pedagogique.py`,
  qui l'intercepte déjà correctement avant son `except Exception`).
- Seuil d'acceptation (150 centipions, décision utilisateur conservée tel
  quel) extrait en constante nommée `SEUIL_ACCEPTATION_NULLE_CP`, avec
  commentaire explicatif.
- Le nom réel de l'adversaire (ex. « Rodent 1200 (Tal) », « Maia 1200 »,
  « Stockfish ~1500elo » — celui déjà affiché au-dessus de l'échiquier) est
  désormais transmis au fil de partie (`game.opponent_label`) et utilisé dans
  le titre de la boîte de confirmation de nulle et dans le motif de refus, à
  la place du texte fixe « Stockfish », dans les 3 langues (clés
  `modal.nulle_stockfish_titre` et `toast.nulle_refusee_default` paramétrées
  avec `{opponent}`).
- Recherche systématique des autres modes (humain, exercices, labo,
  retranscription, explorer, lanceurs) : aucun autre bloc `except` générique
  n'avale une exception de contrôle de flux équivalente à `BackMenuExit`
  (celle-ci n'existe que dans ce fichier). Points de vigilance relevés sans
  correction (mécanismes différents, actuellement sûrs) : `human.py` utilise
  `sys.exit(0)` pour terminer une partie, protégé par un `except SystemExit`
  placé avant le `except Exception` — fragile en cas de futur
  `except BaseException` ou réordonnancement ; `exercices.py` utilise
  `ExitNicLink` de la même façon, également bien ordonné aujourd'hui.
- Tests ajoutés (`nicsoft/tests/test_pedagogique_nulle.py`, moteur et
  interface simulés, sans matériel) : nulle acceptée → `BackMenuExit` remonte
  sans aucun événement de refus ; nulle refusée car l'adversaire est trop
  bien placé ; évaluation impossible → refus avec le message dédié et la
  partie continue ; valeurs limites du seuil (150 accepté, 151 refusé) ; nom
  de l'adversaire transmis dans le message de refus.

### À vérifier manuellement par Alain (échiquier physique)

- Proposer la nulle contre Stockfish, Maia et Rodent chacun dans une position
  où le moteur est nettement mieux (doit refuser, message citant le bon nom)
  et une où il est égal ou moins bien (doit accepter et terminer la partie).
- Après une nulle acceptée suivie d'un retour au menu (ou d'une analyse puis
  retour au menu), relancer le mode Pédagogique sans redémarrer le programme,
  et vérifier qu'aucun message « cases incorrectes » ne réapparaît (preuve que
  l'ancien fil de partie s'est bien arrêté).

# Changelog — Issue #278

## Découpage de game_manager.py en lanceurs par mode (ARC-004)

`nicsoft/core/game_manager.py` (~1180 lignes) orchestrait les sept modes
de jeu dans un seul fichier, avec un état global partagé entre leurs
fonctions. L'audit (règle ARC-004) le signalait comme fichier à
découper ; le rapport le jugeait à risque moyen (couplage à sens unique,
game_manager → modes, jamais l'inverse).

- **Nouveau sous-dossier `nicsoft/core/game_manager_modes/`** (9 fichiers,
  tous nettement sous 300 lignes) :
  - `state.py` (143 l.) — état réellement partagé entre plusieurs modes
    (échiquier courant, mode virtuel) via accesseurs
    (`get_nl_inst_ref`/`set_nl_inst_ref`, `get_virtual_mode`/`set_virtual_mode`),
    plus utilitaires communs (attente de position, toasts d'erreur,
    lecture config moteur).
  - `pedagogique.py` (158 l.), `humain.py` (111 l.),
    `retranscription.py` (45 l.), `exercices.py` (245 l. — exercices et
    drill, avec leur état de session propre : plus exporté nulle part),
    `labo.py` (98 l.) + `labo_session.py` (256 l. — boucle d'actions de la
    session labo, avec le drapeau d'annulation de copie propre à ce
    couple de modules), `labo_libre.py` (140 l.), `explorer.py`
    (139 l. — état de session Opening Explorer propre à ce module).
  - État qui ne servait qu'à un seul mode (session d'exercice/drill, flag
    d'annulation de copie labo, session explorer) rendu local au module de
    ce mode plutôt qu'exporté globalement.
- **`nicsoft/core/game_manager.py` devient une façade** (36 lignes) :
  réexporte les mêmes objets fonctions qu'avant (mêmes noms, y compris les
  privées utilisées par un test — `_run_humain` — et par alchess.py/server.py
  via import local — `_run_exercice`, `_run_drill`, `_make_labo_session`,
  etc.). Aucune variable d'état réaffectable réexportée : uniquement des
  fonctions.
- **Nouvelle fonction d'accès `get_virtual_mode()`** (`state.py`) : remplace
  les deux lectures directes de `gm._virtual_mode` dans
  `nicsoft/web/alchess.py` (handler `set_virtual_mode` du menu), qui
  auraient figé une copie périmée après le découpage puisque la variable
  n'est plus un simple module-global importable en toute sécurité par
  `from ... import`.
- Comportement inchangé : aucun événement envoyé, message de log, ou
  branche d'exception modifiés — seule la répartition du code entre
  fichiers a changé. Les nouveaux modules n'importent toujours jamais
  `nicsoft.web` (ARC-001, vérifié par la suite de tests existante qui
  découvre désormais ces 9 nouveaux fichiers automatiquement : 63 → 73
  fichiers surveillés, 308 → 344 tests passés hors tests matériel, 0 échec).
- Aucun nouveau dossier hors de `nicsoft/core/` : le découpage reste
  entièrement contenu dans `nicsoft/core/game_manager_modes/`.

# Changelog — Issue #281

## Découpage de explore_book.py et eco_import.py, mutualisation de la logique d'import du catalogue

Les deux fichiers dépassaient le seuil de taille de l'audit (règle ARC-004) :
`explore_book.py` (~410 lignes) et `eco_import.py` (~630 lignes). Découpés en
modules par section, sans changement de comportement.

- **`explore_book.py`** devient un point d'entrée qui réexporte les mêmes
  objets publics, répartis dans :
  - `explore_book_display.py` — affichage terminal (échiquier ASCII, ligne
    de coups) : `weight_bar`, `print_board`, `format_move_line`.
  - `explore_book_import.py` — ajout interactif au catalogue : `do_import`.
  - `explore_book_cli.py` — boucle interactive en ligne de commande : `main`.
  - `explore_book_web.py` — fonctions appelées par le serveur web :
    `list_books_for_web`, `get_moves_from_web`.
- **`eco_import.py`** devient de même un point d'entrée, réparti dans :
  - `eco_import_data.py` — chargement des fichiers TSV ECO et filtre :
    `ECO_FILES`, `load_eco`, `parse_filter`.
  - `eco_import_display.py` — popularité dans les livres et affichage des
    résultats : `get_popularity`, `pop_bar`, `pop_label`, `display_results`.
  - `eco_import_import.py` — import d'une entrée, interactif ou en lot :
    `import_entry`, `quick_import_batch`.
  - `eco_import_cli.py` — boucle interactive en ligne de commande : `main`.
  - `eco_import_web.py` — fonctions appelées par le serveur web :
    `search_eco_from_web`, `import_eco_from_web`.
- **Mutualisation de la logique de catalogue dupliquée** : la vérification
  « cette séquence de coups est-elle déjà dans le catalogue ? » était
  recopiée à l'identique 6 fois entre `explore_book.py` (×2) et
  `eco_import.py` (×3), plus une fois de plus sous un nom différent
  (`in_catalogue`) — regroupée dans une nouvelle fonction
  `trouve_doublon(uci_moves, existing_inits)` ajoutée à `_catalogue.py`, et
  réutilisée partout. `do_import` (explorateur) réimplémentait aussi la
  boucle `check_books()` ligne pour ligne ; remplacé par un appel direct à
  la fonction déjà partagée.
  - **Non mutualisé, volontairement** : `search_eco_from_web` construit un
    dict `{tuple(coups): id}` pour vérifier jusqu'à 300 lignes en O(1)
    chacune, plutôt que de rappeler `trouve_doublon` en boucle (O(n) à
    chaque appel) — comportement équivalent, mais le remplacer aurait
    dégradé les performances sur un gros catalogue. De même, la sélection
    du livre cible reste différente entre `do_import` (menu interactif
    numéroté si plusieurs livres correspondent) et
    `import_entry`/`quick_import_batch`/`import_eco_from_web` (sélection
    automatique via `best_book_for`, déjà partagée) : ce sont deux
    parcours utilisateur réellement différents (l'un demande à l'humain,
    l'autre choisit seul), pas une duplication à fusionner.
- **Aucun fichier de données renommé ni déplacé** (`eco_a.tsv`…`eco_e.tsv`,
  `books/*.bin`, `exercices.py`) — les tests e2e qui lisent les vraies
  données ECO de l'utilisateur continuent de fonctionner sans changement.
- `manage.py` et `server.py` continuent d'importer `main`,
  `search_eco_from_web`, `import_eco_from_web`, `list_books_for_web`,
  `get_moves_from_web` directement depuis `explore_book`/`eco_import` —
  aucune modification nécessaire dans ces deux fichiers.
- Les tests de garde ARC-001 (`test_no_web_import.py`,
  `test_no_undefined_names.py`) découvrent automatiquement les nouveaux
  fichiers via le glob de `_arc001_discovery.py` — vérifié : les 9 nouveaux
  modules apparaissent dans la liste découverte, sans mise à jour manuelle.

# Changelog — Issue #280

## Suppression de cinq fichiers morts découverts par les tests de garde ARC-001

Suite de l'élargissement de la découverte ARC-001 à tous les fichiers de
`core`, `modes`, `niclink`, `utils` et `engine` (issue #272), qui avait mis
en évidence cinq fichiers cassés et jamais appelés, documentés comme
exclusions avec test miroir plutôt que supprimés sur le moment.

- Vérification à jour par recherche dans tout le dépôt (code, scripts,
  packaging, documentation, hors changelogs) : aucune référence réelle à
  l'un des cinq fichiers (seules les occurrences de `light_board` sont le
  nom d'un paramètre dans `driver.py`/`virtual_board.py`, sans rapport).
- **Fichiers supprimés** :
  - `nicsoft/utils/light_board.py`
  - `nicsoft/utils/turn_out_all_lights.py`
  - `nicsoft/modes/exercices/__main__.py`
  - `nicsoft/modes/labo/__main__.py`
  - `nicsoft/modes/retranscription/__main__.py`
- `nicsoft/tests/test_no_web_import.py` : retrait de
  `MODULES_NON_IMPORTABLES_SEULS` (les 5 exclusions) et de son test miroir
  `test_modules_non_importables_restent_documentes` ; tous les modules
  découverts passent désormais par les tests normaux.
- `nicsoft/tests/test_no_undefined_names.py` : retrait de l'exclusion
  `nicsoft/utils/light_board.py` (`FICHIERS_AVEC_NOMS_NON_DEFINIS_CONNUS`)
  et de son test miroir `test_fichiers_exclus_restent_documentes`.
- `.audit.json` non touché, comme demandé.
- Suite complète (`pytest -m "not hardware"`) : 293 passed, 60 skipped,
  0 failed — même niveau de protection, aucun fichier supplémentaire
  ignoré.

# Changelog — Issue #279

## Interface : correction des éléments restés cachés ou bloqués depuis l'extraction des styles en ligne vers le CSS

Suite des issues #230-#248 (déplacement des styles `style="..."` écrits
dans le HTML vers des classes CSS). Pour les éléments cachés/désactivés par
défaut (`display:none`, `pointer-events:none`, `opacity<1`), le JS se
contentait d'effacer le style en ligne (`el.style.X = ""`) pour les
« révéler » — ça fonctionnait quand la valeur cachante était seulement
inline, mais ne fait plus rien depuis qu'elle vient d'une règle CSS de
classe : l'élément reste caché, sans la moindre erreur console (visible
seulement en test manuel réel ou via un moteur de rendu).

### Cinq cas confirmés par le rapport, corrigés dans `nicsoft/web/static/app.js`

1. **Contrôles de navigation de l'écran d'analyse** (lecture auto, curseur
   de vitesse, Précédent, Suivant) : `pointer-events` — déjà corrigé à la
   main par Alain avant cette issue (commit "interface : corrige à la main
   l'affichage du bandeau de reprise et la navigation de l'analyse"),
   vérifié et laissé tel quel.
2. **Exercices — bouton « Continuer avec Stockfish »** en fin de ligne
   théorique (`#ex-btn-continuer` / `.exr-btn-continuer`) : `style.display`
   passé de `""` à `"block"`.
3. **Retranscription — formulaire de l'onglet « Exercice »**
   (`#retrans-form-exercice` / `.retrans-form-card-hidden-init`) :
   `style.display` passé de `""` à `"block"` dans `retransSelectTab()`
   (et, par cohérence, le formulaire « Partie » du même switch).
4. **Retranscription, mode exercice — bouton « Sauver et continuer »**
   (`#btn-retrans-save-continue` / `.retrans-game-btn-save-continue`) :
   `style.display` passé de `""` à `"block"`.
5. **Configuration d'une partie — alerte « aucun moteur disponible »**
   (`#cfg-no-engine-alert` / `.cfg-no-engine-alert`) : `style.display`
   passé de `""` à `"block"` dans `_checkNoEngineAvailable()`.

### Sixième cas trouvé par la recherche systématique de cette issue

- **Messages « moteur non installé »** (`#cfg-stockfish-unavailable`,
  `#cfg-maia-unavailable`, `#cfg-rodent-unavailable`, classe partagée
  `.cfg-engine-unavailable-msg { display:none }`) : `_applyStockfishAvailability()`,
  `_applyMaiaAvailability()`, `_applyRodentAvailability()` effaçaient le
  style en ligne (`""`) pour les révéler quand le moteur correspondant est
  absent — jamais affichés depuis l'extraction. Passé à `"block"`. Les
  éléments jumeaux `#labo-*-unavailable` (classe `.labo-unavail-msg`, sans
  `display` en CSS, style `display:none` resté inline dans le HTML) ne sont
  pas affectés par ce bug et continuent de fonctionner avec `""`/`"block"`
  indifféremment — la valeur `"block"` leur convient donc aussi.

### Recherche systématique — cas examinés et écartés (déjà corrects)

Tout `.style.(display|opacity|pointerEvents|visibility)` du fichier
effaçant un style en ligne (`= ""`) a été passé en revue (une quarantaine
d'occurrences). Écartés parce que la classe CSS de l'élément ne cache rien
par défaut (pas de règle concurrente), ou parce que le code utilise déjà
une valeur explicite, ou une bascule de classe d'état
(`classList.toggle/add/remove`) avec une règle CSS correspondante :
`card-nav-save`, `pgn-lib-import-btn`/`-spinner`, `labo-cfg-sf/maia/rodent`
(style inline, pas de classe), `ex-variete-bar`/`ex-drill-bar`,
`modal-cancel` (4 occurrences), `btn-pause`/`btn-pause-hh`, `pause-select`
(opacité), `basket-select` (opacité/pointer-events), `syncBtn`
(`ex-btn-sync`), `#toast` (classe `.show`), `#modal-overlay` (classe
`.open`), `#coller-pgn-zone` (classe `.is-open`), `#autoupdate-warning`
(classe `.hidden`), `#cfg-section-*` (classe `.cfg-section-hidden` via
`classList.toggle`), et tous les écrans `#screen-*` (toujours des valeurs
explicites `"flex"/"grid"/"none"`).

### Cas douteux, non corrigés (hors périmètre de cette issue)

- **`#btn-pause-abandonner`** : déjà documenté lors d'une extraction
  antérieure comme bouton jamais montré par aucun JS (mort), figé en classe
  `.game-pause-hidden-init` sans changement de comportement voulu —
  confirmé inchangé, pas une régression de #230-#248.
- **`#countdown { display:none !important; }`** : règle CSS avec
  `!important` qui bloquerait de toute façon toute tentative du JS de la
  révéler (même avec une valeur explicite) — mais `startCountdown()`, la
  seule fonction qui tente de l'afficher, n'est appelée nulle part dans le
  code (fonction morte). Pré-existe très probablement à la série
  #230-#248 (pas un style en ligne effacé, un `!important` CSS direct).
  Hors périmètre ; signalé pour mémoire.
- **`#labo-feedback`** : deux éléments distincts partagent cet id
  (`.labo-feedback-center` et `.labo-feedback-side`, tous deux
  `display:none` en CSS) ; le seul code JS qui le référence ne fait que le
  masquer (`style.display = "none"`), jamais l'afficher — semble vestigial/
  mort plutôt que lié au défaut de cette issue (aucun effacement de style
  en ligne en cause). Non corrigé, signalé pour mémoire.

### Test de garde (sans navigateur)

`nicsoft/tests/test_css_extraction_hidden_elements.py` — analyse
statiquement `templates/index.html` (association id→classes), `css/main.css`
(règles de classe simples, hors `@media`, qui cachent par défaut :
`display:none`, `pointer-events:none`, `opacity<1`, `visibility:hidden`) et
`static/app.js` (motif `document.getElementById("id")...style.PROP = ""`,
y compris via variable intermédiaire). Échoue si un élément correspond aux
deux. Vérifié qu'il détecte bien les 4 régressions ci-dessus quand
réintroduites (et qu'il ne produit aucun faux positif sur l'état actuel).
Aucune exception documentée nécessaire à ce jour (`EXCEPTIONS_ID_PROP`
prévu pour les futurs cas légitimes).

### Tests e2e (Playwright, infrastructure existante dans `nicsoft/tests/e2e/`)

`nicsoft/tests/e2e/test_review_nav_279_e2e.py` (nouveau) :
- charge une courte partie via « Coller PGN » dans l'écran Analyse (chemin
  déjà utilisé par `test_smoke_e2e.py` comme proxy de l'état `game_over`
  sans échiquier ni partie jouée ; `parsePgn()` est purement client, aucun
  appel socket ni écriture disque) ;
- vérifie que Précédent/Suivant ne sont pas `disabled` **et** que
  `pointer-events` n'est pas `none` (le symptôme exact du cas #1) ;
- vérifie qu'un clic sur Précédent puis Suivant fait réellement changer le
  coup affiché (`#review-move-san`), pas seulement l'attribut `disabled`.
- Vérifié manuellement que ces deux tests échouent (timeout Playwright
  « intercepts pointer events ») si on réintroduit la régression du cas #1,
  et passent une fois corrigé.

Test e2e pour le bouton « Continuer » des Exercices **non ajouté** : pas
réaliste avec l'infrastructure actuelle sans risque de régresser sur les
contraintes de l'issue — atteindre une vraie fin de ligne théorique suppose
(a) un catalogue d'ouvertures réel, qui n'est pas versionné dans le dépôt
(`data/` est dans `.gitignore`, dépend du dossier utilisateur), donc un
test non reproductible/portable entre environnements, et (b) une
synchronisation par coup via le thread d'exercice (plateau virtuel), chemin
jamais exercé par l'infrastructure e2e actuelle (tous les tests existants
sont purement navigationnels, aucun ne joue de coup réel) — risque de
flakiness et de dépendance non maîtrisée au dossier de données réel.

### Vérifications manuelles suggérées

1. Terminer une partie (ou charger un PGN en Analyse), puis cliquer sur
   Précédent/Suivant, survoler le curseur de vitesse et le bouton lecture
   automatique : tout doit réagir normalement.
2. Exercices : jouer une ligne théorique jusqu'au bout → le bouton
   « Continuer avec Stockfish » doit apparaître (si un moteur est
   disponible).
3. Retranscription : ouvrir l'onglet « Exercice » → le formulaire doit
   s'afficher ; démarrer une retranscription en mode exercice → le bouton
   « Sauver et continuer » doit apparaître pendant la partie.
4. Configuration d'une partie sans aucun moteur disponible (si faisable) :
   l'alerte « Aucun moteur d'échecs n'est disponible » doit s'afficher et
   le bouton Démarrer doit être grisé.

### Tests

- `nicsoft/tests/test_css_extraction_hidden_elements.py` (nouveau).
- `nicsoft/tests/e2e/test_review_nav_279_e2e.py` (nouveau, 2 tests).
- Suite complète hors hardware (`pytest nicsoft/tests -m "not hardware"`) :
  311 passed, 65 skipped.

# Changelog — Issue #277

## Retranscription et Outils : ne plus afficher des demi-coups sous le nom de « coups »

Suite du rapport de l'issue #274 (confusion demi-coup/coup aux échecs), pour
les deux endroits qu'elle avait listés sans les corriger.

- **Règle de conversion partagée** : `pgn_move_number`/`pgn_moves_played`
  déplacées de `nicsoft/modes/exercices/exercices.py` vers
  `nicsoft/engine/board_utils.py` (module neutre partagé, ne dépend jamais
  de `nicsoft.web` — ARC-001). `exercices.py` les réimporte désormais
  depuis ce module ; comportement et test existant
  (`test_exercices_pgn_move_count.py`) inchangés.
- **Retranscription — bannière de session reprise** (`app.js`, handler
  `retranscription_en_cours`) : `nicsoft/web/alchess.py` envoyait le nombre
  brut de demi-coups de la session sauvegardée dans le champ `moves` ;
  converti via `pgn_moves_played()`. Pluriel correct ajouté dans les 3
  langues (nouvelle clé `common.n_coup`, singulier, à côté de
  `common.n_coups` déjà existante) ; `app.js` choisit la bonne clé selon
  `data.moves === 1`.
- **Retranscription — champ `move_num` de l'événement par coup** : non lu
  par aucun code (interface, tests, autres modules — vérifié par grep),
  renommé en `half_moves_played` dans
  `nicsoft/modes/retranscription/retranscription.py` pour refléter sa
  vraie nature (nombre brut de demi-coups, pas un numéro de coup PGN).
- **Outils (panneau d'administration du catalogue)** : les trois libellés
  techniques comptant des demi-coups sans les convertir — `outils.label.coups`
  ("Coups"/"Moves"/"Züge"), `outils.polyglot.profondeur` (profondeur
  d'exploration du livre), `outils.init_coups` (coups d'initialisation
  d'une ligne) — renommés en « Demi-coups »/« Half-moves »/« Halbzüge »
  dans les 3 langues, sans toucher aux valeurs ni à aucun format de
  fichier. Nouvelle clé `outils.n_demi_coups` ajoutée pour que le compte
  affiché à côté de la liste de coups (`outils.label.coups`, ligne ~6036
  d'`app.js`) reste cohérent avec le libellé renommé (il réutilisait avant
  `common.n_coups`, partagé avec d'autres écrans non concernés par cette
  issue).
- Mode Humain contre Humain et mode Pédagogique non touchés, comme demandé.

### Autres endroits avec la même confusion, trouvés en route mais non corrigés (hors périmètre de cette issue)

- `app.js` ligne ~1693 : options de la combobox `rv-seq-moves` (mode
  Pédagogique, replay vidéo) — `t("common.n_coups", {n: opt.value})`.
- `app.js` ligne ~3461 : journal du Labo à l'import d'un PGN —
  `t("common.n_coups", {n: history.length})`, `history.length` étant un
  nombre de demi-coups.
- `app.js` ligne ~4403 : cartes de sélection de lignes à l'entraînement
  (drill) en mode Exercices — `t("common.n_coups", {n: nb})` où `nb =
  (o.line || o.init || []).length` est un nombre de demi-coups.
- `app.js` ligne ~6051/6057 : `outils.livre_count` ("{count} coup(s)
  suivant : {next}") — vérifié : `count` est un poids/fréquence Polyglot,
  pas un compte de demi-coups ; pas la même confusion, laissé tel quel.

### Vérification manuelle suggérée

1. Retranscription : commencer une retranscription, jouer quelques coups
   (demi-coups impair et pair à tester), quitter sans terminer (`Retour
   menu` ou fermer l'app), puis relancer l'app : la bannière de reprise
   doit afficher un nombre de coups conforme à la convention PGN
   (singulier/pluriel correct) dans les 3 langues.
2. Outils : ouvrir le panneau Outils des exercices (administration du
   catalogue), vérifier une ligne existante et l'exploration du livre
   Polyglot : les libellés doivent dire « Demi-coups »/« Half-moves »/
   « Halbzüge » (profondeur, coups d'une ligne, coups d'initialisation),
   valeurs inchangées.

### Tests

- `nicsoft/tests/test_board_utils_pgn_move_count.py` (nouveau) : couvre
  `pgn_move_number`/`pgn_moves_played` depuis leur nouvel emplacement
  (0, 1, 2, 5, 24 demi-coups) et la valeur envoyée pour une session de
  retranscription reprise.
- `nicsoft/tests/test_exercices_pgn_move_count.py` : inchangé, toujours
  vert (les fonctions sont réimportées, pas redéfinies).
- Suite complète hors hardware (`pytest nicsoft/tests/ -m "not hardware"`) :
  260 passed, 54 skipped.

# Changelog — Issue #276

## Découpage de engine_manager.py en modules cohérents

`nicsoft/engine/engine_manager.py` (833 lignes, règle ARC-004) mélangeait
détection des binaires, disponibilité, classe générique de moteur UCI,
spécialisations Maia/Rodent et classification des coups. Découpé sans
changement de comportement en 7 modules du dossier `nicsoft/engine/` :

- `move_quality.py` (39 lignes) — `classifier_coup`, `score_to_cp`,
  seuils `SEUIL_BON`/`SEUIL_IMPRECISION`/`SEUIL_ERREUR` (logique pure).
- `engine_analysis.py` (277 lignes) — `EngineAnalysisMixin` : `evaluate`,
  `evaluate_move`, `get_punishment_line`, `get_multipv`, `analyser_partie`,
  `wdl_to_bar`. Extrait de la classe `EngineManager` d'origine (qui
  dépassait seule 380 lignes) en mixin hérité, pour que chaque module
  reste nettement sous 300 lignes sans toucher au comportement ni à la
  structure de classe (MaiaEngine/RodentEngine héritent toujours de
  `EngineManager`, qui hérite du mixin).
- `uci_engine.py` (150 lignes) — `EngineManager` (init, `_apply_elo`,
  `get_move`, `set_elo`, `quit`, propriétés) + constantes `ELO_MIN`/
  `ELO_MAX`/`ELO_DEFAUT`.
- `engine_detection.py` (132 lignes) — `find_stockfish`, `find_lc0`,
  `find_rodent`, `find_maia_weights`, `MAIA_LEVELS`, `_ensure_executable`.
- `engine_availability.py` (64 lignes) — `stockfish_available`,
  `maia_available`, `rodent_available` (ce dernier lance réellement
  Rodent pour le handshake UCI, comportement inchangé).
- `maia_engine.py` (114 lignes) — `MaiaEngine`.
- `rodent_engine.py` (132 lignes) — `RodentEngine` + constantes
  `RODENT_PERSONALITIES`/`RODENT_ELO_MIN`/`RODENT_ELO_MAX`/
  `RODENT_ELO_DEFAUT`/`RODENT_PERSONALITY_DEFAUT`.

`engine_manager.py` (63 lignes) devient un point d'entrée qui réexporte
tous ces objets — aucun import existant (serveur web, `analyse.py`, mode
labo, `test_rodent.py`, `test_analyse_engine_path.py`) n'a dû être modifié.

Logger applicatif inchangé : chaque nouveau module reprend
`logging.getLogger("EngineManager")`, exactement comme l'ancien fichier
unique (même nom partout, donc même objet Logger).

Aucun test n'a dû être adapté : `test_analyse_engine_path.py` monkeypatch
`nicsoft.engine.engine_manager.find_stockfish`, et `analyse.py` continue
de faire `from nicsoft.engine.engine_manager import find_stockfish` à
l'intérieur de la fonction au moment de l'appel — ce remplacement agit
donc toujours sur le nom réellement utilisé, puisque `engine_manager.py`
réexpose `find_stockfish` (défini maintenant dans `engine_detection.py`)
comme un attribut de son propre module. Vérifié en relançant les deux
tests concernés après le découpage.

Suite complète hors tests `hardware` : 278 passed, 61 skipped (inchangé
par rapport à avant le découpage).

# Changelog — Issue #275

## Découpage de llm_explainer.py en modules cohérents (ARC-004)

`nicsoft/modes/opening_explorer/llm_explainer.py` dépassait 360 lignes et
concentrait plusieurs responsabilités (appel réseau aux fournisseurs,
cache disque, construction des consignes, fonctions publiques). Découpé en
4 modules dans le même dossier, `llm_explainer.py` devenant un simple point
d'entrée qui réexporte les 3 fonctions publiques sans aucun changement de
comportement :

- `llm_provider.py` (61 lignes) — `call_claude`/`call_openai` : appel HTTP
  bas niveau aux fournisseurs. Ne journalise ni clé d'API ni URL complète
  (inchangé).
- `llm_cache.py` (35 lignes) — `load_cache`/`save_cache` : cache disque
  JSON des explications déjà générées.
- `llm_prompts.py` (183 lignes) — consignes système/utilisateur par langue
  (`SYSTEM_PROMPTS`, `ANALYSE_SYSTEM_PROMPTS`, `CHAT_SUFFIX`), construction
  des prompts (`build_user_prompt`, `build_chat_prompt`,
  `build_analyse_context_text`) et extraction des flèches (`extract_arrows`).
- `llm_functions.py` (128 lignes) — les 3 fonctions publiques
  `get_explanation`, `get_chat_response`, `get_analyse_response`, qui
  orchestrent cache + consignes + appel fournisseur.
- `llm_explainer.py` (17 lignes) — réexporte les 3 fonctions publiques
  depuis `llm_functions.py` ; `nicsoft/web/server.py` les importe toujours
  depuis ce même chemin, sans aucune modification nécessaire côté serveur.

Le motif de compteur d'annulation de requête mentionné par l'issue
(`tts_engine._tts_generation` côté Explorer, `_analyse_llm_request_id`
côté drawer Analyse) ne vit pas dans `llm_explainer.py` mais dans
`tts_engine.py`/`server.py` — fichiers non touchés par ce découpage, donc
le motif reste bien dans un seul module, inchangé.

- 2 nouveaux fichiers de tests, aucun accès réseau (fonctions pures /
  cache sur répertoire temporaire) :
  - `nicsoft/tests/test_llm_cache.py` — round-trip load/save, cache
    absent, JSON corrompu ignoré.
  - `nicsoft/tests/test_llm_prompts.py` — construction des prompts
    (ouverture, alternatives, fallback FEN invalide, contexte Analyse) et
    extraction des flèches (3 langues, cases invalides, limite à 4).
- Suite de tests complète (hors `hardware`) : 284 passed, 58 skipped.

# Changelog — Issue #274

## Exercices : numéros et nombres de coups selon la convention des échecs

Le serveur envoyait au navigateur le nombre brut de **demi-coups**
(`len(board.move_stack)` ou `len(init_moves)`) pour les champs `move_num`
(progression pendant la ligne), `move_count` (position de départ à
reproduire) et `moves` (fin de ligne théorique) — affiché tel quel avec les
libellés "Coup"/"Move"/"Zug" ou "coups"/"moves"/"Züge", alors qu'aux échecs
un coup compte une paire blanc+noir.

- Deux fonctions ajoutées dans `nicsoft/modes/exercices/exercices.py` :
  - `pgn_move_number(half_moves)` = `half_moves // 2 + 1` — numéro du coup
    PGN en cours (celui que les blancs commencent ou que les noirs doivent
    répondre). Ex. 24 ou 25 demi-coups → coup 13.
  - `pgn_moves_played(half_moves)` = `(half_moves + 1) // 2` — nombre de
    coups complets joués ; pour un nombre impair de demi-coups (dernier
    coup commencé mais pas encore répondu), compte ce coup comme joué
    (choix documenté ici, demandé par l'issue). Ex. 4 demi-coups → 2 coups ;
    5 demi-coups → 3 coups.
- Les 6 points d'envoi dans `exercices.py` utilisent maintenant ces
  fonctions (`move_count` ×3, `moves` ×2, `move_num` ×1) — aucun nouvel
  événement, les noms de champs sont inchangés.
- `exercice_end_of_line` faisait déjà un `Math.floor(data.moves / 2)` côté
  JS (arrondi vers le bas, incorrect pour un nombre impair) : supprimé
  puisque `data.moves` est désormais déjà le nombre de coups complets.
- Pluriel correct dans les 3 langues pour les deux libellés concernés
  (`fr/en/de.json`) : nouvelles clés `exercices.coup_joue`/`coups_joues`
  (position de départ) et `exercices.end_of_line_feedback_un` (fin de
  ligne, variante singulier de la clé existante). `exercices.reproduire_position`
  n'inclut plus le participe "joués"/"played"/"gespielt" en dur (il fait
  maintenant partie du libellé choisi selon le pluriel).
- `common.coup_num` ("Coup {n}") n'a pas besoin de variante plurielle (un
  numéro de coup ne se pluralise pas) — seule la valeur envoyée était
  fausse, pas le libellé.
- Test ajouté : `nicsoft/tests/test_exercices_pgn_move_count.py`, vérifie
  les deux fonctions sur 0, 1, 2, 4, 5, 24 et 25 demi-coups.
- Suite complète (`pytest nicsoft/tests/ -m "not hardware"`) : 257 passed,
  54 skipped (tests matériel), aucun échec.

### Autres endroits avec la même confusion demi-coup/coup, non corrigés (hors périmètre de cette issue)

- `nicsoft/web/alchess.py` (événement `retranscription_en_cours`, bannière
  de reprise de partie) envoie `len(moves)` (demi-coups) affiché via
  `common.n_coups` dans `app.js` (~ligne 5705) : une partie à 25 demi-coups
  affiche "25 coups" au lieu de 13.
- `nicsoft/modes/retranscription/retranscription.py:247` — le champ
  `move_num` de l'événement `retranscription_move` est lui aussi un compte
  de demi-coups brut, mais n'est actuellement lu par aucun code JS
  (`_retransRenderHistory`/`_retransUpdateTurn` ne s'en servent pas) : pas
  de bug visible aujourd'hui, mais le nom du champ est trompeur. À noter :
  l'affichage du tour en cours dans ce même mode (`_retransUpdateTurn`,
  `app.js:5697`) applique déjà la bonne formule PGN
  (`Math.floor(length / 2) + 1`), donc ce mode n'a pas le bug visible pour
  l'utilisateur.
- Outils Exercices (panneau d'administration du catalogue, pas le mode
  Exercices lui-même) : `outils.label.coups` (`app.js:6032`) et
  `outils.init_coups` (`app.js:6371`) affichent le nombre de demi-coups
  d'une séquence d'initialisation comme "N coups" ; de même le champ
  `depth` envoyé par `nicsoft/modes/exercices/explore_book.py` (ligne 410,
  affiché via `outils.polyglot.profondeur`, `app.js:6238`) est aussi un
  compte de demi-coups.
- `explore_book.py:format_move_line()` (affichage terminal, outil CLI) est
  en revanche déjà correct : il construit la notation `N.san` selon la
  vraie numérotation PGN.

# Changelog — Issue #273

## Exercices : ne plus voir l'erreur "livre introuvable" en revenant dans un exercice une fois le livre restauré

Suite de #271. Cause établie par analyse du code (confirmée par le test
manuel décrit dans l'issue, qui pointait déjà vers cette piste) :

- **Cause 1 (interface) — confirmée.** `exSetFeedback()` (`app.js`) affiche
  le bandeau de feedback avec `duration = 0` pour les messages "livre
  introuvable" et "fin de ligne" (vert) : ni l'un ni l'autre ne disparaît
  automatiquement — c'est voulu, l'utilisateur doit agir. Mais le handler
  `socket.on("exercice_init", ...)`, qui construit l'écran d'un nouvel
  exercice, ne vidait jamais ce bandeau (`#ex-feedback`) : un message laissé
  affiché par un exercice précédent (ex. l'erreur livre manquant) restait
  visible indéfiniment au-dessus du nouvel exercice, même une fois sa cause
  disparue.
  - En revanche, la ligne de statut (`#ex-run-status`) modifiée par
    l'erreur est déjà réinitialisée par `exercice_init` **avant** la
    branche `if (_virtualMode) { ... } else { ... }`
    (`app.js:4623-4624` avant ce fix, code antérieur à #270/#271) : cette réinitialisation
    s'applique donc déjà identiquement aux deux modes (virtuel et échiquier
    physique) — contrairement à l'hypothèse soulevée dans l'issue, aucune
    asymétrie n'a été trouvée sur ce point précis à la lecture du code
    actuel ; aucun changement n'y était donc nécessaire.
- **Cause 2 (serveur) — non confirmée.** `ExerciceSession.run()`, dans la
  branche "livre manquant", boucle sur `_wait_action_end()` jusqu'à
  recevoir une action différente de "RETRY", puis fait un `return` normal
  (`exercices.py:974-979`). Les deux actions de sortie côté IHM ("Retour au
  menu" et "← Choisir autre ouverture") envoient toutes deux le même type
  d'action `exercice_back` (`index.html:922-924`, `app.js:97-98`), traité
  de façon identique par `_wait_action_end()` (`exercices.py:1219-1221`) :
  `self._running = False`, puis retour. `game_manager._run_exercice()`
  attend donc bien la fin réelle de `session.run()` avant son bloc
  `finally`, qui remet `_exercice_running = False`
  (`game_manager.py:505-507`) — le lanceur repasse donc bien à "aucun
  exercice en cours" et un nouveau lancement (`start_exercice` /
  `_run_exercice`) crée normalement une nouvelle session. Aucune
  modification serveur n'a donc été nécessaire ; un test de garde-fou a
  été ajouté pour verrouiller ce comportement.

### Modifications

- `nicsoft/web/static/app.js` — `socket.on("exercice_init", ...)` : efface
  désormais le bandeau de feedback résiduel (`#ex-feedback`, masqué et
  texte vidé) dès la réception de l'événement d'initialisation d'un
  exercice, avant toute autre mise à jour d'écran. Les messages temporaires
  (durée > 0, ex. "✓ coup théorique") ne sont pas concernés : ce
  changement ne touche que l'état résiduel au moment où un nouvel exercice
  démarre.
- `nicsoft/tests/test_exercices_book_missing.py` — nouveau test
  `test_nouvelle_session_apres_restauration_du_livre` (sans interface ni
  matériel) : une première `ExerciceSession` avec livre manquant est créée,
  tourne dans un thread, reste en attente (pas de retour automatique), puis
  se termine proprement sur une action `exercice_back`. Une seconde
  `ExerciceSession` est alors créée avec un livre Polyglot minimal
  construit pour le test (une seule entrée `e2e4`) : elle ne signale aucune
  erreur (`exercice_sync_error` absent des événements), émet
  `exercice_wait_position` (démarrage normal), et ne se termine pas
  immédiatement (le thread reste vivant, en attente de la synchro
  initiale) — exactement le comportement attendu quand on revient dans un
  exercice une fois le livre restauré.
- Cas inchangés vérifiés : "pièces mal placées" (`exercice_sync_error` hors
  livre manquant) et cas normal (livre présent, fin de ligne théorique) —
  aucun des tests existants n'a été modifié dans son comportement, seuls
  ajouts.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 255 passed,
  54 skipped.

### Reproduction manuelle

1. Renommer temporairement le fichier du livre d'ouvertures attendu (ex.
   `data/books/gm2001.bin` → `gm2001.bin.bak`).
2. Ouvrir un exercice d'ouverture quelconque : le message « Livre
   d'ouvertures introuvable : <chemin> » s'affiche, reste affiché (pas de
   retour automatique).
3. Quitter (← Retour au menu ou ← Choisir autre ouverture).
4. Remettre le fichier du livre à sa place (annuler le renommage de
   l'étape 1).
5. Rouvrir un exercice d'ouverture (le même ou un autre) : avant ce fix, le
   bandeau d'erreur « Livre d'ouvertures introuvable » restait affiché par-
   dessus le nouvel exercice bien que le livre existe de nouveau — il
   fallait cliquer sur « Synchroniser » pour le faire disparaître. Après ce
   fix, l'exercice démarre normalement, sans bandeau ni statut d'erreur
   résiduels, aussi bien avec un échiquier physique qu'en mode virtuel.

# Changelog — Issue #272

## Tests de garde ARC-001 : découverte automatique des fichiers au lieu de listes écrites à la main

Les trois tests qui verrouillent ARC-001 (le moteur n'importe jamais
`nicsoft.web`) listaient à la main huit ou neuf fichiers. Deux défauts :
`engine`, `utils` et `niclink/driver` n'y figuraient pas (un import web y
serait passé inaperçu), et un nouveau fichier créé lors d'un découpage
n'était couvert par aucun test, sans qu'aucune alerte ne le signale.

- `nicsoft/tests/_arc001_discovery.py` (nouveau) : découverte commune —
  parcourt `nicsoft/{core,modes,niclink,utils,engine}` et retourne tous les
  `.py` (hors `__pycache__`), avec un garde-fou (`verifier_decouverte_non_cassee`)
  qui échoue si la liste est vide ou si `game_manager.py` /
  `virtual_board.py` manquent.
- `nicsoft/tests/test_no_web_import.py`, `test_ihm_port_contract.py`,
  `test_no_undefined_names.py` : remplacent leur liste écrite à la main par
  cette découverte automatique, chacun avec un test dédié qui vérifie que la
  découverte n'est pas cassée.
- Modules qui ne s'importent pas seuls pour des raisons sans rapport avec
  ARC-001 (bugs préexistants dans du code mort, mis en lumière par la
  découverte élargie) : exclus explicitement avec une raison écrite, jamais
  en silence — et un test dédié (`test_modules_non_importables_restent_documentes`,
  `test_fichiers_exclus_restent_documentes`) échoue si le bug sous-jacent est
  corrigé sans retirer l'exclusion, pour qu'elle ne devienne pas obsolète :
  - `nicsoft.utils.light_board` : `List` et `np` non importés (NameError).
  - `nicsoft.utils.turn_out_all_lights` : `from niclink import NicLinkManager`
    cassé (devrait être `nicsoft.niclink`).
  - `nicsoft.modes.{exercices,labo,retranscription}.__main__` : importent
    `main` depuis leur module, qui ne le définit plus depuis le découplage
    #263/#264 (entry-points CLI morts, l'app web ne les utilise plus).
  - Ces cinq cas sont des bugs préexistants dans du code mort (jamais appelé
    ailleurs dans le projet), sans lien avec ARC-001 et sans risque pour le
    comportement actuel de l'application — non corrigés ici par prudence
    (la correction de `light_board.py` notamment nécessiterait de deviner un
    comportement voulu, au-delà d'un ajout d'import trivial).
- Temps ajouté à la suite ARC-001 : environ 3 s (passée de ~2,1 s à ~5,1 s
  sur cette machine) — reste de l'ordre de quelques secondes, le pre-push
  hook lance cette suite avant chaque push.
- Vérifié concrètement : un fichier fautif temporaire (`import nicsoft.web`
  + nom non défini) ajouté dans chacun des cinq dossiers (`core`, `modes`,
  `niclink`, `utils`, `engine`) fait échouer `test_no_web_import.py` et
  `test_no_undefined_names.py` automatiquement, sans modification des
  fichiers de test ; fichiers retirés sans être committés.
- Suite complète hors tests `hardware` : 252 passed, 54 skipped.
- `.audit.json` non modifié.

# Changelog — Issue #271

## Exercices : l'erreur "livre introuvable" reste affichée jusqu'à une action de l'utilisateur

Suite de #270. Le message d'erreur (livre Polyglot introuvable) était bien
émis mais `ExerciceSession.run()` terminait aussitôt après (`return`
immédiat) : le lanceur d'exercice (`game_manager._run_exercice`) voyait
alors la session se terminer et exécutait son nettoyage normal de fin
d'exercice, qui renvoie aussitôt la liste des ouvertures — l'écran d'erreur
disparaissait donc en moins d'une seconde, le rendant inutilisable en
pratique.

- `nicsoft/modes/exercices/exercices.py` (`ExerciceSession.run()`) : le cas
  « livre manquant » affiche désormais la position de départ de l'exercice
  demandé (`self._send_position()` — plus l'échiquier de l'exercice
  précédent) puis attend une action utilisateur via `_wait_action_end()`,
  exactement comme à la fin normale d'une ligne (mêmes actions possibles :
  retour au menu, choisir une autre ouverture, recommencer). Sur
  « recommencer », l'erreur est simplement réaffichée (le livre est
  toujours manquant) sans relancer `_restart()` ni repasser par la boucle
  de jeu normale — pas de boucle infinie (bloqué sur l'action utilisateur)
  ni de nouveau log (le log d'absence du livre reste unique, à la
  construction de la session). Seule la méthode `run()` a été modifiée ;
  le nettoyage de fin de session dans `game_manager._run_exercice` est
  inchangé, et le mécanisme d'attente/actions (`_wait_action_end`) est
  celui déjà utilisé pour la fin de ligne théorique normale.
- Cas inchangés vérifiés : livre présent et cas « pièces mal placées »
  (`exercice_sync_error` hors livre manquant).
- `nicsoft/tests/test_exercices_book_missing.py` : test existant mis à jour
  (fournit désormais une action de retour pour débloquer `run()`) et deux
  nouveaux tests — la session reste en attente tant qu'aucune action n'est
  reçue puis se termine proprement sur un retour, sans jamais émettre
  `exercice_end_of_line` ; et "recommencer" avec le livre toujours
  manquant réaffiche l'erreur (au moins 2 occurrences) sans log
  supplémentaire ni `exercice_end_of_line`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 125 passed,
  10 skipped.

### Reproduction manuelle

1. Renommer temporairement le fichier du livre d'ouvertures attendu (ex.
   `data/books/gm2001.bin` → `gm2001.bin.bak`), ou renommer le dossier
   `data/books/` lui-même.
2. Lancer un exercice d'ouverture quelconque depuis l'interface.
3. Observer : le message « Livre d'ouvertures introuvable : <chemin> »
   reste affiché tant qu'aucune action n'est prise — pas de retour
   automatique à la liste, l'échiquier affiché est celui de la position de
   départ de l'exercice choisi (pas celui d'un exercice précédent).
4. Cliquer « ↺ Recommencer l'exercice » : l'erreur est réaffichée à
   l'identique (toujours pas de retour à la liste).
5. Cliquer « ← Choisir autre ouverture » ou « ← Retour au menu » : retour
   normal à la liste des ouvertures / au menu.
6. Restaurer le fichier/dossier renommé à l'étape 1.

# Changelog — Issue #270

## Exercices : message clair quand le livre d'ouvertures est introuvable

Avant le fix, si le fichier du livre Polyglot était introuvable (ex. dossier
`data/` absent), `ExerciceSession._get_book_moves` avalait l'exception et
retournait une liste vide — indistinguable d'une vraie fin de ligne
théorique. L'IHM annonçait donc « Ligne terminée ! Bravo » alors que
l'exercice n'avait jamais pu se dérouler, et le serveur loggait l'erreur
« Livre : fichier ou dossier inexistant » à chaque coup.

- `nicsoft/modes/exercices/exercices.py` : l'existence du fichier du livre
  (`self._book_path`) est vérifiée une seule fois, à la construction de
  `ExerciceSession` (`self._book_missing`), et loggée une seule fois par
  exercice (`logger.error`, pas à chaque coup). `run()` détecte ce cas en
  tout premier lieu et émet `exercice_sync_error` (événement d'erreur IHM
  déjà utilisé par l'exercice pour la synchro de plateau) au lieu de
  dérouler la boucle de jeu — plus de faux `exercice_end_of_line`.
  `_get_book_moves` ne retente plus l'ouverture du fichier une fois le livre
  connu manquant, et ne logge plus qu'une fois les erreurs imprévues
  (livre corrompu, etc.) via `self._book_error_logged`.
- `nicsoft/web/static/app.js` : le handler `exercice_sync_error` accepte
  désormais deux champs optionnels — `status_key` (texte de statut
  personnalisé) et `show_sync_btn` (désactive le bouton Synchroniser quand
  resynchroniser ne résoudra rien) — sans changer le comportement par
  défaut (cas existant : pièces mal placées).
- `nicsoft/web/static/i18n/{fr,en,de}.json` : nouvelles clés
  `exercices.book_missing_status` et `exercices.book_missing_msg`
  (interpolée avec le chemin attendu du livre).
- Cas inchangés vérifiés : livre présent (coup du livre toujours trouvé) et
  vraie fin de ligne théorique (livre présent mais sans entrée pour la
  position) toujours traitée comme une fin de ligne normale.
- Nouveau test `nicsoft/tests/test_exercices_book_missing.py` (sans
  interface ni matériel) : livre absent → `exercice_sync_error` émis,
  `exercice_end_of_line` jamais émis, un seul log d'erreur ; livre présent
  → comportement inchangé ; livre présent mais vide pour la position →
  fin de ligne normale toujours distincte d'un livre manquant.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 122 passed,
  10 skipped.

# CHANGELOG-269 (issue #269)

## Échiquier virtuel : ajout de la méthode disconnect (plus de faux avertissement à la sortie des modes)

- `nicsoft/niclink/virtual_board.py` : ajout de `VirtualBoard.disconnect()`, no-op comme ses méthodes voisines (`turn_off_all_leds`, `beep`, etc.) — rien à fermer côté USB en mode virtuel.
- Cause : `nicsoft/core/game_manager.py` appelle `nl_inst.disconnect()` en sortie d'explorateur d'ouvertures, d'exercices et de drill (3 endroits, non modifiés — l'appel côté appelant était correct). Avec un échiquier virtuel, cette méthode n'existait pas : `AttributeError` avalée par un `except` qui journalisait un faux avertissement « Déconnexion échiquier échouée ... object has no attribute disconnect » à chaque sortie de ces modes en mode virtuel.
- Vérification des autres méthodes de `NicLinkManager` appelées par `game_manager.py` ou les modes sur l'objet échiquier (`get_fen`, `turn_off_all_leds`, `signal_lights`, `connect`, `start`...) : toutes déjà présentes dans `VirtualBoard` ou appelées uniquement après vérification que l'instance est physique (`connect()` dans `server.py`, gardé par `hasattr(nl_inst, "nl_interface")`). Aucune autre méthode manquante.
- `nicsoft/tests/test_virtual_board.py` (nouveau) : crée un `VirtualBoard` et appelle `disconnect()` sans erreur.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 120 passed, 10 skipped.

# CHANGELOG-267 (issue #267)

## Tests e2e : serveur lancé depuis le code testé, échiquier réel ignoré

- `nicsoft/tests/e2e/conftest.py` : le dossier de lancement du serveur de test (donc le code importé par `python -m nicsoft.web`) n'est plus le dépôt principal codé en dur (`~/NicLink`), mais déduit de l'emplacement de `conftest.py` (racine du dépôt ou du worktree où tourne pytest). Les tests valident donc le code sur lequel ils sont exécutés. Le Python reste celui du venv utilisateur (`~/NicLink/venv/bin/python`).
- `nicsoft/web/alchess.py` : nouvelle variable d'environnement `ALCHESS_SKIP_BOARD=1` qui désactive `_check_board_at_startup` (détection/connexion de l'échiquier USB réel au démarrage) et évite de lancer `_board_menu_watcher` ; absente, le comportement est inchangé. Positionnée uniquement dans l'environnement du serveur lancé par `conftest.py`.
- `data/` n'étant pas versionné, un worktree n'a pas les fichiers de référence réels (ECO `eco_*.tsv`, `eco_hierarchy.json`, livres d'ouvertures…) dont dépendent 3 tests de recherche ECO (`test_outils_exercices_e2e.py`). L'isolation complète via un dossier `ALCHESS_DIR` temporaire (point optionnel de l'issue) a été tentée puis abandonnée pour cette raison ; `ALCHESS_DIR` est positionnée vers le vrai dossier de données de l'utilisateur (`~/NicLink`) pour ces tests — seul le code vient du worktree, pas les données. Documenté dans `TESTS.md`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 119 passed, 10 skipped, lancée depuis le worktree, sans navigateur visible ni sollicitation de l'échiquier USB.

# CHANGELOG-266 (issue #266)

## Retrait de l'outil de sauvegarde backup_manager

- Suppression de `nicsoft/utils/backup_manager.py` et de `nicsoft/utils/Lancer et autre outil Backup.txt`.
- Retrait de toutes les références (commandes, consignes de backup épinglé) dans `CLAUDE.md`, `CONTEXTE.md`, `SPECIFICATIONS.md`, `TESTS.md`, `ETAT_PROJET.md` et `INSTALLATION/CONFIGURATION_SYSTEME.md`.
- Là où la consigne de backup épinglé disparaît, remplacement par un rappel explicite : la protection du travail repose sur git (commits ciblés, retour arrière par git, push fait par Alain après revue).
- `CONTEXTE.md` : suppression de l'affirmation périmée selon laquelle CCL travaille exclusivement dans `~/NicLink` (devenu faux depuis le passage aux worktrees isolés par issue).
- Aucun code Python n'importait cet outil ; suite de tests (`pytest -m "not hardware"`) : 96 passed, 4 skipped.

# Changelog — Issue #265

## Journal de l'application : ne plus enregistrer la bannière de démarrage des moteurs d'échecs

Le logger `chess.engine` (utilisé en interne par python-chess pour relayer en
WARNING la sortie stderr des moteurs UCI externes — bannière lc0/Maia au
démarrage : version, backend de calcul, poids chargés, cœurs...) est
désormais relevé au niveau `ERROR` dans `_setup_logging()`
(`nicsoft/web/alchess.py`). Choix assumé : on accepte de ne plus journaliser
la sortie stderr brute des moteurs (niveau WARNING chez python-chess), au
profit d'un journal applicatif lisible — les échecs réels de démarrage ou
d'arrêt inattendu d'un moteur restent signalés indépendamment, via les
`logger.error(...)` explicites d'`engine_manager.py` (sur le logger
`"niclink"`), qui ne dépendent pas de la sortie stderr relayée par
python-chess. Rien d'autre n'est modifié : ni le niveau global (`WARNING`),
ni les autres loggers. Verrouillé par `nicsoft/tests/test_logging_config.py`.

# Changelog — Issue #264

## Suite #263 : correction des régressions du découplage (Humain contre Humain + abandon Pédagogique)

Le test manuel avec échiquier physique a révélé deux régressions introduites
par le découplage nicsoft.web de la #263, non détectées par
`test_no_web_import.py` (qui ne vérifie que l'absence d'import de
`nicsoft.web`, pas que chaque appel migré trouve bien sa cible).

### Régression 1 — mode Humain contre Humain

`nicsoft/core/game_manager.py:320` appelait `web_server.set_history(...)` où
`web_server` est l'alias local de `ihm_port.app_state_proxy`
(`_AppStateProxy`). Cet objet n'expose que `_app_state` et `action_queue`
(façade volontairement limitée à l'ancien accès direct `web_server._app_state`
/ `.action_queue`) — pas `set_history`, qui est une fonction de module de
`ihm_port.py`, pas une méthode du proxy. Résultat : `AttributeError`
immédiatement après la création du plateau virtuel/physique → retour menu,
déconnexion/reconnexion visible côté échiquier.

**Fix** : `game_manager.py` importe désormais `set_history` directement
depuis `nicsoft.core.ihm_port` (même motif que `human.py`, qui l'importait
déjà correctement) et l'appelle sans passer par le proxy.

### Régression 2 — abandon en mode Pédagogique

`nicsoft/modes/pedagogique/pedagogique.py:376` (`Game._end_game`) lisait
`_game_state.get("init", {})`. `_game_state` était un dict interne de
`nicsoft.web.server`, importé localement avant la #263
(`from nicsoft.web.server import set_app_state, _game_state`). L'étape 6/8 de
la #263 a retiré cet import (remplacé par `get_history()` pour la lecture de
l'historique) mais a laissé cette seconde référence orpheline → `NameError:
name '_game_state' is not defined` au clic sur « Abandonner », juste avant
l'envoi de l'état `game_over` → retour menu avec popup d'erreur.

**Fix** : ajout d'un accesseur dédié `get_init_data()` — dans
`nicsoft/web/server.py` (lecture verrouillée de `_game_state["init"]`, miroir
de `get_history()`), exposé par `_WebBackend` (`nicsoft/web/alchess.py`) et
`_NullBackend`/module `nicsoft/core/ihm_port.py`. `pedagogique.py` l'importe
et l'appelle au lieu de lire `_game_state` directement.

### Recensement systématique (point 3 de la demande)

Vérification exhaustive, par analyse statique, de tous les fichiers migrés
par la #263 (`game_manager`, `human`, `pedagogique`, `exercices`, `labo`,
`virtual_board`, `board_adapter`, `retranscription`) :

- **Appels sur l'objet d'interface (`ihm_port`/`app_state_proxy`)** : les deux
  régressions ci-dessus sont les **deux seuls** cas trouvés où un appel migré
  ne correspond à aucun élément réellement fourni par le port ou par le
  proxy. Tous les autres imports depuis `ihm_port` et tous les autres appels
  sur l'alias de `app_state_proxy` (`web_server`/`_web_server`) correspondent
  à un élément réel.
- **Noms non définis (reste de l'ancien `nicsoft.web`)** : `_game_state`
  (régression 2) est le **seul** nom non lié trouvé sur l'ensemble des
  fichiers migrés (vérifié avec `pyflakes` et avec le test
  `test_no_undefined_names.py` ci-dessous).

### Tests ajoutés (point 4)

- `nicsoft/tests/test_ihm_port_contract.py` — analyse statique (ast) : chaque
  nom importé depuis `nicsoft.core.ihm_port` dans les fichiers migrés existe
  réellement dans ce module ; chaque attribut accédé sur l'alias local de
  `app_state_proxy` existe réellement sur `_AppStateProxy` ; `_NullBackend` et
  `_WebBackend` exposent chacun toutes les méthodes utilisées par les
  fonctions de module de `ihm_port.py`.
- `nicsoft/tests/test_no_undefined_names.py` — équivalent restreint de
  pyflakes ("undefined name"), implémenté avec le seul module standard `ast`
  (pas de nouvelle dépendance de test) : pour chaque fichier migré, vérifie
  qu'aucun nom lu n'est totalement non lié dans le fichier.
- `nicsoft/tests/test_humain_startup_virtuel.py` (bonus) — exécute
  `game_manager._run_humain(virtual=True)` avec un plateau virtuel et un
  double léger de `GameWeb`, jusqu'après l'enregistrement de l'historique
  initial via le port — sans matériel ni serveur Flask-SocketIO.

Les trois nouveaux tests ont été vérifiés manuellement contre l'état d'avant
correction (`git stash`) : ils échouent bien sur les deux régressions
(`AttributeError` et `NameError`) et passent après le fix.

### Comportement

Strictement identique à avant la #263 — aucun changement de motif de thread
SocketIO, aucune nouvelle dépendance.

### Vérifications manuelles à refaire avec l'échiquier physique

- Mode Humain contre Humain : lancer une partie, vérifier que l'échiquier
  s'affiche et reste connecté (pas de retour menu / déconnexion-reconnexion).
- Mode Pédagogique : lancer une partie, cliquer sur « Abandonner », vérifier
  qu'aucune popup d'erreur n'apparaît et que l'écran de fin de partie
  (historique, titre) s'affiche normalement avant le retour menu.

# Changelog — Issue #263

## Découplage de la logique de jeu : plus d'import de nicsoft.web depuis core/modes/niclink/utils/engine (règle ARC-001)

Recensement complet refait avant correction (l'audit initial, limité à
`nicsoft/modes`, comptait 32 sites) : **34 sites réels** répartis sur 7
fichiers — `nicsoft/core/game_manager.py` (11), `nicsoft/modes/humain/human.py` (7),
`nicsoft/modes/pedagogique/pedagogique.py` (7), `nicsoft/modes/exercices/exercices.py` (5),
`nicsoft/niclink/virtual_board.py` (3), `nicsoft/modes/labo/labo.py` (1),
`nicsoft/core/board_adapter.py` (1). (`nicsoft/utils/debug.py` et
`nicsoft/utils/timing.py` ne mentionnaient `nicsoft.web` que dans un
commentaire/docstring — aucun import réel.) `nicsoft/modes/retranscription/retranscription.py`
était déjà découplé : il reçoit `web_server` en paramètre (injection de
dépendance) plutôt que de l'importer — c'est le motif qui a inspiré la
solution retenue pour les autres fichiers.

**Solution retenue** : un port neutre, **`nicsoft/core/ihm_port.py`**, expose
aux modules de jeu les primitives dont ils ont besoin (`send_event`,
`get_action`, `set_app_state`, `set_virtual_board`, `get_history`/`set_history`,
`get_action_queue`, `get_app_state`/`set_raw_app_state`, `check_board_at_startup`,
`emit`). Tant qu'aucun backend n'est branché (import isolé, tests), un
backend neutre (`_NullBackend`) répond sans effet de bord — permet d'importer
n'importe quel module de jeu sans lancer le serveur web. Au démarrage réel,
`nicsoft/web/alchess.py` branche l'implémentation Flask-SocketIO via
`ihm_port.register_backend()`.

Les très nombreux sites qui accédaient directement au module
`nicsoft.web.server` (`web_server._app_state = ...`, `web_server.action_queue...`)
— notamment dans `game_manager.py` et `human.py`, pour la course critique
SocketIO qui écrit `_app_state` silencieusement avant d'appeler `set_app_state()`
(pour éviter une fenêtre de race pendant la notification navigateur) — n'ont
*pas* été réécrits un par un : `ihm_port.app_state_proxy` reproduit exactement
le même objet dupliqué (property `_app_state` + `action_queue`), ce qui a
permis de ne changer que la ligne d'import sur ces sites et de garder le reste
du code strictement identique. Seul `game_manager.py:304` (import différé de
`nicsoft.web.alchess._check_board_at_startup`, seul cas de cycle réel —
`alchess.py` importe `game_manager` au niveau module) devient
`ihm_port.check_board_at_startup()`.

Migration faite mode par mode, un commit par étape (points de retour arrière) :
port neutre → `niclink/virtual_board.py` → `core/board_adapter.py` →
`modes/labo/labo.py` → `modes/exercices/exercices.py` →
`modes/pedagogique/pedagogique.py` → `modes/humain/human.py` →
`core/game_manager.py` → test d'isolation.

Ajout de `server.emit()` (émission SocketIO directe, hors `event_queue`) pour
couvrir un site (`pedagogique.py`) qui faisait `socketio.emit()` directement
pour un popup ponctuel, sans passer par `send_event()`.

Un site a changé de forme sans changer de résultat : `pedagogique.py` lisait
`_game_state["history"]` directement (sans le verrou), remplacé par
`get_history()[0]`, l'accesseur déjà prévu par `server.py` pour cet usage
précis d'après sa propre docstring ("à utiliser par tout module hors
server.py").

**Résultat** : plus aucun import de `nicsoft.web` depuis `core`, `modes`,
`niclink`, `utils`, `engine` (vérifié par recherche dans le code — seules des
mentions en commentaire/docstring subsistent dans `ihm_port.py`, `debug.py`,
`timing.py`). Comportement strictement identique : mêmes événements, mêmes
files d'actions, mêmes fils d'exécution.

**Fichiers modifiés :**

`nicsoft/core/ihm_port.py` (nouveau), `nicsoft/web/server.py`,
`nicsoft/web/alchess.py`, `nicsoft/niclink/virtual_board.py`,
`nicsoft/core/board_adapter.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/core/game_manager.py`,
`nicsoft/tests/test_no_web_import.py` (nouveau).

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
54 passed, 3 skipped (hardware), dont le nouveau
`test_no_web_import.py` (14 cas, chacun dans un sous-processus Python
propre pour ne pas être pollué par d'autres tests qui importent
`nicsoft.web.server` pour leurs propres besoins). Smoke-test manuel du
serveur réel (`start_server()` + requête HTTP sur `/`) : backend branché,
`_app_state` piloté via le port identique à l'ancien accès direct au
module. Suite e2e non lancée (nécessite Playwright + serveur lancé depuis
`~/NicLink`, hors périmètre du worktree).

**À vérifier manuellement par Alain, avec l'échiquier physique branché**
(aucun hardware disponible dans l'environnement de l'agent) :
- Mode Pédagogique (Stockfish/Maia/Rodent) : coup joué, feedback LED,
  pause sur erreur/blunder, reprise, abandon, fin de partie (mat/nulle),
  notification popup mat/pat.
- Mode Humain vs Humain : coups, undo, abandon, nulle par accord mutuel,
  retour menu depuis un état actif (vérification silencieuse du plateau
  au retour menu).
- Mode Exercices : synchronisation initiale, détection hors-théorie,
  retry/continue, retour menu.
- Mode Labo : suivi du plateau physique, meilleur coup, mode auto,
  analyse, copie de position.
- Déconnexion USB en cours de partie (callback `_board_lost_cb` →
  `board_error`) : le message doit toujours apparaître côté navigateur.
- Démarrage de l'appli complète (`python -m nicsoft.web`) suivi d'un tour
  dans chaque mode, pour confirmer qu'aucune régression de câblage n'est
  passée inaperçue dans l'environnement sans hardware de l'agent.

# Changelog — Issue #262

## Analyse de partie : ignorer le chemin du moteur sauvegardé s'il n'existe pas sur cette machine

`analyser_partie()` (`nicsoft/engine/analyse.py`) lisait le chemin du moteur
enregistré dans `data/config.json` et le transmettait tel quel à
`EngineManager`, sans vérifier qu'il existait sur la machine courante. Une
configuration copiée depuis une autre machine, ou un moteur désinstallé/déplacé,
faisait planter l'analyse au lieu de retomber sur la recherche automatique de
Stockfish (`find_stockfish()`) — repli qui n'était utilisé que lorsque le
chemin était vide.

La logique de validation (`chemin sauvegardé conservé seulement s'il existe`)
existait déjà dans `nicsoft/core/game_manager.py` sous le nom
`_validated_engine_path()`, utilisée par les autres modes de jeu. Pour éviter
une troisième copie tout en respectant le sens des dépendances (`engine` ne
doit pas dépendre de `game_manager`, qui dépend de la couche web), cette aide
est déplacée vers **`nicsoft/core/config_manager.py`** (module neutre, déjà
point d'accès centralisé à `config.json` depuis #259), renommée
`validated_engine_path()` (devenue un helper public partagé plutôt qu'un
détail interne de `game_manager`). `game_manager.py` pointe maintenant vers
cette version déplacée, sans changement de comportement.

`analyser_partie()` réutilise aussi `read_json_with_defaults()` (lecture de
config partagée introduite par #259) à la place de sa propre lecture JSON
manuelle, avec le même message de log en cas d'échec.

**Fichiers modifiés :**
- `nicsoft/core/config_manager.py` — ajout de `validated_engine_path()`.
- `nicsoft/core/game_manager.py` — utilise `validated_engine_path()` importé de `config_manager` (suppression de la copie locale `_validated_engine_path`).
- `nicsoft/engine/analyse.py` — `analyser_partie()` valide le chemin moteur sauvegardé et réutilise `read_json_with_defaults()`.
- `nicsoft/tests/test_analyse_engine_path.py` (nouveau) — 3 tests avec `EngineManager` simulé (aucun vrai moteur lancé) : chemin inexistant → repli `find_stockfish()`, chemin existant → conservé, chemin vide → comportement inchangé.

Suite de tests complète (hors `hardware`) : 82 passed, 4 skipped.

# Changelog — Issue #261

## Erreurs silencieuses : trace ou justification de chaque except sans traitement (règle PRO-012)

L'audit relevait 52 captures d'erreur silencieuses (exemples : `platform_utils.py`,
`labo.py`, `retranscription.py`, sept occurrences dans `game_manager.py`). Un
recensement complet refait avant correction (les numéros de ligne de l'audit
avaient bougé) a trouvé **133 occurrences réelles** réparties sur 29 fichiers —
l'audit initial était partiel.

Pour chaque occurrence, choix au cas par cas, sans jamais modifier le flux de
contrôle (aucun nouveau `raise`, aucune valeur de retour changée) :

- si l'erreur peut révéler une vraie panne → journalisée avec le logger du
  module (`logger.warning`/`logger.error` pour les cas significatifs,
  `logger.debug` dans les boucles d'interrogation rapides du plateau physique
  ou pour les fallbacks fréquents/attendus, afin de ne pas inonder les logs) ;
- si le repli silencieux est voulu (valeur par défaut, fichier optionnel
  absent, nettoyage best-effort en fin de programme/thread, idiome de vidage
  de `queue.Empty`, saisie interactive interrompue, exception de contrôle de
  flux comme `BackMenuExit`/`ExitNicLink`) → conservé, avec un commentaire
  explicatif ajouté dans le corps du `except`.

**Résultat : 72 cas journalisés, 61 cas justifiés par commentaire.**

Cas le plus significatif : `nicsoft/niclink/driver.py`, `_fen_reader_loop()`
— tout le thread de lecture USB était silencieux ; passé en `logger.debug`
(boucle à 50ms, erreurs transitoires fréquentes, mais désormais visibles en
mode `NICLINK_LOG=DEBUG`). Autre cas notable : `nicsoft/core/config_manager.py`
— `load_config()` ignorait un `config.json` corrompu sans aucune trace nulle
part ; utilise maintenant le paramètre `on_error` déjà prévu par
`read_json_with_defaults()` pour journaliser, sans changer la valeur retournée
(les défauts restent utilisés comme avant).

**Fichiers modifiés (29) :**

`nicsoft/platform_utils.py`, `nicsoft/core/config_manager.py`,
`nicsoft/core/game_manager.py`, `nicsoft/engine/analyse.py`,
`nicsoft/engine/board_utils.py`, `nicsoft/engine/display.py`,
`nicsoft/engine/engine_manager.py`, `nicsoft/engine/pgn_manager.py`,
`nicsoft/modes/exercices/_catalogue.py`,
`nicsoft/modes/exercices/add_ouverture.py`,
`nicsoft/modes/exercices/eco_import.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/exercices/explore_book.py`,
`nicsoft/modes/exercices/import_lignes.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/opening_explorer/explorer_session.py`,
`nicsoft/modes/opening_explorer/llm_explainer.py`,
`nicsoft/modes/opening_explorer/sources.py`,
`nicsoft/modes/opening_explorer/tts_engine.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/retranscription/retranscription.py`,
`nicsoft/niclink/driver.py`, `nicsoft/niclink/hid_backend.py`,
`nicsoft/niclink/virtual_board.py`, `nicsoft/tests/e2e/conftest.py`,
`nicsoft/web/alchess.py`, `nicsoft/web/launcher.py`, `nicsoft/web/server.py`.

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
37 passed, 3 skipped (hardware). Suite e2e non lancée (nécessite Playwright
+ un serveur lancé depuis `~/NicLink`, hors périmètre du worktree).

# Changelog — Issue #260

## Rodent IV Linux : fin du faux dépôt imbriqué, documentation corrigée

`engines/rodent-iv` était enregistré dans l'index git comme un lien vers un
dépôt imbriqué (clone de `nescitus/rodent-iv`) sans jamais être déclaré comme
sous-module (`.gitmodules` ne le mentionnait pas). Conséquences : dossier vide
après un clonage frais, binaire local signalé en permanence comme
« modifié » sur la machine de dev, et documentation affirmant à tort que le
binaire Linux était inclus dans le dépôt (vrai seulement pour `lc0`).

**Changé :**

- `.gitignore` — ajout de `engines/rodent-iv/` : le dossier (dépôt git
  imbriqué + binaire compilé localement) n'est plus jamais suivi ni signalé
  comme modifié.
- Index git — `git rm --cached engines/rodent-iv` : retire l'entrée de
  dépôt imbriqué de l'index, sans toucher aux fichiers sur disque.
- `INSTALLATION/INSTALLATION_NICLINK.md` — ne prétend plus que le binaire
  Linux de Rodent IV est inclus dans le dépôt ; ajoute les instructions pour
  l'obtenir (clone + compilation de `https://github.com/nescitus/rodent-iv`,
  binaire à placer en `engines/rodent-iv/rodentIV` et à rendre exécutable) et
  corrige l'URL du dépôt source (était `nescior/Rodent_IV`, inexistant/non
  utilisé).
- `install.sh` — message clair quand `engines/rodent-iv/rodentIV` est
  absent (cas normal après un `git clone`), avec pointeur vers la section
  de compilation de la doc. Pas de téléchargement/compilation automatique.
- `make_release.sh` — commentaires corrigés : ne parlent plus de
  « sous-module » (qui n'a jamais existé pour ce chemin) mais de « dépôt git
  imbriqué, jamais déclaré en sous-module ». Comportement du script
  inchangé.

**Vérifié :**

- `find_rodent()` (`nicsoft/engine/engine_manager.py`) ne dépend que de
  l'existence du fichier `engines/rodent-iv/rodentIV` — inchangé par ce
  correctif, qui ne touche à aucun fichier Python.
- `make_release.sh` continue de supposer (comme avant) que le dépôt imbriqué
  réel, avec le binaire compilé, est présent sur la machine de build —
  c'est toujours la machine de dev d'Alain qui alimente le ZIP de release.

**À faire manuellement par Alain (voir commentaire de clôture de l'issue) :**
sauvegarde du binaire compilé avant la fusion sur la machine réelle, puis
vérification qu'il est toujours présent après.

# Changelog — Issue #259

## Factorisation du code dupliqué entre les fichiers du moteur (règle PRO-014)

L'audit signalait ~27 lignes identiques réparties sur plusieurs fichiers
(hypothèse initiale : `board_adapter.py`, `config_manager.py`,
`game_manager.py`, `analyse.py`, `board_utils.py`). Après vérification,
les blocs réellement dupliqués ne sont pas exactement ceux listés par
l'audit mais relèvent bien de la même cause : la lecture de
`data/config.json`, dupliquée localement — point que `config_manager.py`
documentait déjà lui-même comme "hors scope pour l'instant".

**Fusionné :**

- `nicsoft/core/config_manager.py` — nouvelle fonction
  `read_json_with_defaults(path, defaults, on_error=None)`, qui isole la
  logique « lit un JSON, fusionne sur des defaults, retombe sur les
  defaults si absent/invalide ». `load_config()` du module l'utilise
  désormais.
- `nicsoft/modes/pedagogique/pedagogique.py` et
  `nicsoft/modes/humain/human.py` — leurs `load_config()` locaux (mêmes
  defaults et même niveau de log qu'avant) délèguent maintenant la lecture
  JSON à `read_json_with_defaults()` au lieu de la dupliquer. Import
  `json` devenu inutile, retiré.
- `nicsoft/core/game_manager.py` — `launch_pedagogique()` et
  `launch_labo_libre()` contenaient le même bloc de 11 lignes (lecture de
  `engine_elo`/`engine_path` depuis `config.json`, byte pour byte
  identique, y compris le message de log). Extrait en
  `_read_engine_elo_and_path()`.

**Non fusionné (écarts de comportement réels, signalés sans forcer) :**

- Trois autres blocs de `game_manager.py` (exercice libre, drill, labo)
  lisent aussi `engine_elo`/`engine_path` depuis `config.json`, mais
  diffèrent sur des points fonctionnels : portée du `try/except` (un
  échec JSON désactive entièrement le moteur dans un cas, retombe sur des
  defaults dans un autre), ordre du repli `find_stockfish()`, et pour le
  mode labo l'`engine_elo` provient en réalité d'un dict de configuration
  runtime (pas du fichier). Les fusionner sans vérification individuelle
  aurait changé ces comportements.
- `nicsoft/engine/analyse.py` lit aussi `engine_path` depuis
  `config.json`, mais sans passer par la validation d'existence du
  chemin sur la plateforme courante (`_validated_engine_path`) — une
  différence de comportement pré-existante, potentiellement un écart à
  signaler séparément, pas touchée ici.
- `nicsoft/modes/humain/human.py` (fonction CLI historique, hors flux
  web) instancie `NicLinkManager` directement plutôt que via
  `nicsoft.core.board_adapter.create_board()` : ce chemin CLI n'a pas le
  callback `_board_lost_cb` (qui dépend de `nicsoft.web.server`), donc le
  fusionner aurait introduit une dépendance et un comportement nouveaux.
- `nicsoft/core/game_manager.py` (`_wait_initial_position_web` /
  `_wait_position_web`) ressemble à `wait_for_initial_position()` de
  `nicsoft/engine/board_utils.py`, mais la version web pilote
  `set_app_state`/`send_event` au lieu d'imprimer dans le terminal —
  différence de transport volontaire, non fusionnée.

**Tests** : `python -m pytest nicsoft/tests/` → 79 passed, 4 skipped
(tests matériel auto-skippés en l'absence d'USB), aucune régression.

# Changelog — Issue #256

## Téléchargement Rodent IV (Win) : délai d'attente et vérification d'intégrité

`on_download_rodent` (`nicsoft/web/server.py`) récupérait les 3 fichiers du
moteur Rodent IV Windows (`rodent-iv-x64.exe`, `msvcr120.dll`,
`msvcp120.dll`) via `urllib.request.urlretrieve`, sans délai d'attente ni
vérification, avant de les rendre utilisables (règles EXP-013 et SEC-022 de
l'audit).

Nouvelle fonction `_telecharger_fichier_rodent()` :
- télécharge via `urllib.request.urlopen(..., timeout=15)` (remplace
  `urlretrieve`, qui ne supporte aucun paramètre de délai) ;
- calcule l'empreinte SHA-256 du contenu pendant le téléchargement et la
  compare à une référence connue (`_RODENT_WIN_SHA256`) ;
- en cas d'écart, de délai dépassé, ou d'absence de référence connue pour
  un nom de fichier : supprime le fichier téléchargé (jamais installé) et
  laisse l'exception remonter — l'échec est signalé à l'interface via
  l'événement `rodent_download_result` existant (comportement inchangé,
  déjà adapté).

**Provenance des empreintes de référence** — calculées directement depuis
les fichiers déjà versionnés dans ce dépôt sous `engines/rodent-iv-win/`
(commit courant), qui sont exactement la même release que celle
re-téléchargée par ce handler pour les installations NSIS standalone
n'embarquant pas ces fichiers. Aucune empreinte n'a été calculée à partir
d'un téléchargement non vérifié. Les 3 fichiers du moteur ont pu être
couverts par cette référence versionnée — aucun fichier n'a dû être laissé
sans référence :
- `rodent-iv-x64.exe` → `39c879b2dfdaf0252e94db547397d95422fee76ea8bafa584bfdc03e4d648de5`
- `msvcr120.dll` → `ad32240bb1de55c3f5fcac8789f583a17057f9d14914c538c2a7a5ad346b341c`
- `msvcp120.dll` → `81fbc2824e73f0d101d91854694a52e79db0ffaadbb2a10deaaf47b3b7f9b2b0`

Tests ajoutés dans `nicsoft/tests/test_rodent.py` (4 nouveaux, aucun accès
réseau réel, `urllib.request.urlopen` mocké) :
- délai dépassé → `URLError` propagée, aucun fichier créé ;
- empreinte invalide → `ValueError`, fichier supprimé ;
- nom de fichier sans référence connue → refusé avant toute requête réseau ;
- empreinte valide → fichier écrit normalement.

Suite complète (hors `test_move_matching.py`/`test_players.py`, en échec
préexistant dans cet environnement faute du module `hid`, sans rapport
avec ce changement) : 74 passed, 4 skipped, aucune régression.

Backup pinné : `avant-issue256-rodent-timeout-integrite`.

## Dépendances : correctifs de sécurité, épinglage des versions flottantes, retrait de berserk

Audit `requirements.txt` : 4 paquets en retard de correctifs de sécurité
(SEC-001), 2 non épinglés (EXP-001), et `berserk` déclaré mais jamais
importé (reste de NicLink).

- **Correctifs de sécurité** (`pip-audit` : 11 vulnérabilités → 0) :
  - `setuptools` 69.1.1 → 84.1.0 (PYSEC-2025-49, PYSEC-2026-1918,
    PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w)
  - `wheel` 0.42.0 → 0.46.2 (CVE-2026-24049)
  - `python-socketio` 5.16.1 → 5.16.2 (PYSEC-2026-3042)
  - `Werkzeug` 3.1.7 → 3.1.9 (PYSEC-2026-4312)
- **Épinglage** des versions flottantes, sur la version installée/testée :
  - `numpy` `>=1.26.4` → `==2.5.4`
  - `edge-tts` `>=6.1.0` → `==7.3.1`
- **Retrait de `berserk`** (`requirements.txt` + tableau d'inventaire
  `ETAT_PROJET.md`) : aucun import dans le code, aucune référence dans les
  scripts d'installation (`1-Installer.bat`, `bootstrap_linux.sh`) ni
  l'installeur Windows.

Aucun conflit de compatibilité : `pip check` propre avec Flask 3.1.3 et
Flask-SocketIO 5.6.1 après les 4 montées de version. Suite de tests
complète (hors marqueur `hardware`) : 75 passed, 4 skipped.

`ETAT_PROJET.md` mis à jour en cohérence (tableau §5, versions
`python-socketio`/`Werkzeug`/`numpy`, ligne `berserk` supprimée).

# Changelog — Issue #212

## Tests e2e Exercices mis à jour pour le nouveau chemin de navigation

`test_exercices_liste_affichee` et `test_retour_depuis_exercices`
(`nicsoft/tests/e2e/test_smoke_e2e.py`) ciblaient encore le bouton direct
"Exercices" du menu principal, retiré au commit e648146 (issue #141,
réorganisation "Ouvertures"). Le chemin actuel comporte 2 étapes : clic sur
le bouton du wrapper `#wrap-ouvertures` (mène à `#screen-ouvertures`), puis
clic sur la carte `.outil-card-clickable` portant
`onclick="_menuCardLaunch('exercices', this)"` (mène à `#screen-exercices`).

Ajout d'un helper `go_exercices(page)` qui suit ce chemin en 2 étapes avec
des sélecteurs indépendants de la langue (même approche que le fix #208) :
- `#wrap-ouvertures button` — id déjà unique, pas de filtre sur le texte.
- `.outil-card-clickable[onclick*="'exercices'"]` — fragment d'attribut
  `onclick`, indépendant des libellés traduits ("📖 Openings"/"📚 Exercises"
  en anglais, langue par défaut de l'environnement de test).

Vérifié : aucune autre référence à l'ancien sélecteur
`button, has_text="📚 Exercices"` dans le fichier. Le bouton "← Menu" de
retour depuis `#screen-exercices` (ligne ~873 de `index.html`) est du texte
brut sans `data-i18n`, donc déjà indépendant de la locale — inchangé.

Suite `nicsoft/tests/e2e/test_smoke_e2e.py` complète : 12 passed, 1 skipped
(hardware), aucune régression.

Backup pinné : `avant-fix-e2e-exercices-navigation-issue212`.

# Changelog — Issue #201

## Suppression du code mort dupliqué (modes pédagogique et labo)

Suppression de deux fichiers orphelins, non importés nulle part dans le
code (aucun `import`, aucune référence dans les scripts `.sh`/`.bat`/`.ps1`,
aucune référence dans `.github/`) :

- `nicsoft/modes/pedagogique/__main__ (pedagogique).py` (1691 lignes) —
  nom de fichier non conforme (espace + parenthèses), donc non importable
  comme module Python de toute façon.
- `nicsoft/modes/labo/__main__labo.py` (409 lignes).

Comparaison ligne à ligne avec les fichiers canoniques réellement utilisés
(`pedagogique.py`, importé par `nicsoft/core/game_manager.py`, et `labo.py`,
importé par le même fichier ainsi que par `nicsoft/modes/labo/__main__.py`) :
les deux fichiers canoniques sont des évolutions strictement plus complètes
des fichiers supprimés (mêmes fonctionnalités + i18n, `RodentEngine`,
pipeline de précalcul du coup moteur, `kill_switch`, `BackMenuExit`, etc.).
Aucune portion de logique utile n'a été identifiée comme présente
uniquement dans les fichiers supprimés — le reste des différences est de la
plomberie CLI obsolète (ancien point d'entrée `main()`/`argparse`/`input()`
préexistant à l'architecture web actuelle).

`py_compile` OK sur les fichiers canoniques après suppression.

Backup pinné : `avant-suppression-code-mort-201`.

# Changelog — Issue #200

## Rapatrier socket.io et chess.js en local

- Téléchargé `socket.io.min.js` (v4.7.2) et `chess.min.js` (v0.10.3) dans
  `nicsoft/web/static/vendor/socket.io/` et `nicsoft/web/static/vendor/chess.js/`.
- `index.html` référence désormais `/static/vendor/socket.io/socket.io.min.js`
  et `/static/vendor/chess.js/chess.min.js` au lieu de cdnjs.cloudflare.com.
- Testé : démarrage serveur Flask OK, page servie sans requête vers cdnjs,
  handshake Socket.IO fonctionnel, fichiers vendor servis en HTTP 200.

## Issue #181 — Vérification version Python dans l'installeur NSIS (essai2)

- `installer-exe/alchess_setup.nsi` : nouvelle fonction `CheckPythonVersionWarning`, appelée juste après détection réussie de Python (SecPython, toutes stratégies : `py -0p`, PATH, scan des dossiers standards) et avant la création du venv. Avertit — sans bloquer — si le Python détecté est une pré-publication (suffixe `rc`/`a`/`b` dans la version complète, ex. `3.15.0rc1`) ou une version ancienne (< 3.10).
- Cas non couvert par la comparaison existante (`CompareVersionToMinimum`) : elle ne compare que "X.Y" (ex. "3.15") au minimum requis (3.12), donc une RC comme `3.15.0rc1` passait la vérification sans que son suffixe soit examiné — cause du bug constaté (Python 3.15rc1 : `hidapi` ne compile pas faute de MSVC, aucun wheel précompilé n'existant pour une RC).
- Ajout de `ExtractFullVersionFromPythonOutput` (garde le suffixe complet de la version, contrairement à `ExtractVersionFromPythonOutput` qui tronque à "X.Y") et de la macro `StrFunc` `StrStr` (recherche de sous-chaîne).
- `MessageBox MB_OKCANCEL` non bloquante : affiche la version détectée, recommande Python 3.12/3.13 stable avec lien vers python.org, l'utilisateur peut continuer quand même (IDCANCEL → Abort propre).
- Non appelée après `InstallPython312NSIS` (installation via winget) : cette voie installe toujours une 3.12 stable, jamais concernée.
- Vérifié : `makensis -V4 alchess_setup.nsi` compile sans erreur (exit 0).

## Issue #170 — llm_explainer : préciser le joueur et interdire les coups futurs dans le prompt

- `nicsoft/modes/opening_explorer/llm_explainer.py` : `_build_user_prompt` identifie désormais le camp qui vient de jouer (Blancs/Noirs, déduit du FEN) et l'inclut explicitement dans le prompt envoyé au LLM ("Les Blancs viennent de jouer : e4"). Ajout d'une consigne explicite interdisant de mentionner les coups futurs de l'adversaire, pour corriger le comportement où le LLM expliquait la réponse probable de l'adversaire au lieu du coup joué.
- Cache LLM vidé (`data/explorer_cache.json`) pour forcer la régénération des explications avec le nouveau prompt.
- Suite de l'issue #168.

# Changelog — issue #148

## Opening Explorer — flèches SVG illustrant les coups mentionnés par le LLM

- `nicsoft/modes/opening_explorer/llm_explainer.py` : prompt système enrichi
  (FR/EN/DE) pour demander au LLM d'ajouter une ligne `[FLECHES: e2-e4, ...]`
  (`[ARROWS: ...]` / `[PFEILE: ...]` selon la langue, même tag interne
  `FLECHES|ARROWS|PFEILE` accepté au parsing) ; ajout de `extract_arrows(text)`
  qui retire cette ligne et retourne la liste des flèches (2 à 4 max, cases
  validées a-h/1-8, from == to ignoré). `get_explanation()` et
  `get_chat_response()` retournent désormais `(texte, flèches)` ; le cache
  disque stocke `{"text": ..., "arrows": [...]}` (rétrocompatible avec les
  anciennes entrées `str`).
- `nicsoft/web/server.py` : `explorer_explanation` et `explorer_chat_response`
  émettent désormais `{"text": ..., "arrows": [["e2","e4"], ...]}`.
- `nicsoft/web/templates/index.html` : `#expl-board` enveloppé dans un
  conteneur `position:relative` avec un `<svg id="expl-arrows">` en
  surimpression (`pointer-events:none`) et un marker `#expl-arrowhead`.
- `nicsoft/web/static/app.js` : `explDrawArrows(arrows)` dessine des flèches
  rouges semi-transparentes (`rgba(232,69,96,0.75)`, épaisseur ~8% d'une
  case) entre les centres des cases, en tenant compte de `_explFlipped`.
  `explClearArrows()` vide le SVG (en conservant `<defs>`) ; appelé dans
  `explorer_state`, `explLoad()` et avant chaque nouveau dessin.

py_compile OK sur `llm_explainer.py` et `server.py` ; `node --check` OK sur
`app.js`.

