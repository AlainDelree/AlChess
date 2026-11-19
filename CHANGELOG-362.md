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
