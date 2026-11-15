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
