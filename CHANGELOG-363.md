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
