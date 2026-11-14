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
