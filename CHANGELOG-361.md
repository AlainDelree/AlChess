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
