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
