# Changelog — Issue #364

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
