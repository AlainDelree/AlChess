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
