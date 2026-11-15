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
