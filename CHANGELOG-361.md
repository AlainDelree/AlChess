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
