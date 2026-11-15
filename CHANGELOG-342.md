# Changelog — issue #342

## Analyse après partie : lancer l'analyse complète d'office, suppression du bouton « Analyser la partie »

Le bouton « Analyser la partie » (`btn-analyser`) avait été prévu quand l'analyse prenait beaucoup de temps. Tant qu'il n'était pas cliqué, l'historique n'avait aucune coloration et le bouton « Voir le meilleur coup » restait grisé en permanence — constaté par Alain sur une partie Lichess chargée en « Révision PGN ». L'analyse complète démarre désormais d'elle-même dès qu'une partie non encore analysée est affichée sur l'écran d'analyse.

### Point 1 — Lancement automatique

`app.js::_reviewMaybeAutoAnalyse(skip)` est appelée à la fin de chaque chemin qui peuple l'écran de revue :
- le handler `app_state`/`game_over` (partie pédagogique/HH qui vient de se terminer, ou entrée directe dans « Analyse » depuis le menu) ;
- `parsePgn()` — donc aussi, par construction, « Coller PGN », l'import de fichier PGN, la bibliothèque PGN personnelle (`pgn_lib_game_loaded` appelle `parsePgn()`) et le classeur de session (`basketLoadToAnalyse()` appelle aussi `parsePgn()`).

Même paramètres qu'avant : profondeur moteur inchangée (codée en dur côté serveur), longueur de séquence punitive lue dans le sélecteur « Séquence » (`#rv-seq-moves`, désormais toujours visible tant qu'une partie est chargée, pour pouvoir la régler avant de charger la partie suivante).

### Point 2 — Détection « déjà analysée », jamais de relance

Inchangée dans son principe (`_isAnalysed` : au moins un coup avec une qualité reçue différente de "bon", ou qualités déjà reçues en direct pendant une partie HH analysée coup par coup) — élargie dans `parsePgn()` pour couvrir le cas d'une partie *parfaite* déjà analysée (sinon indistinguable d'une partie jamais analysée, puisque tous les coups sont "bon" dans les deux cas) : un commentaire PGN avec évaluation chiffrée (`cp`) sur CHAQUE coup compte aussi comme « déjà analysée ». Une analyse déjà en cours pour la MÊME partie (clé = liste des coups UCI) n'est jamais relancée non plus (`_analyseInProgressKey`).

### Point 3 — Indicateur de progression discret

Nouvelle ligne `#review-analyse-progress-row` dans la carte Navigation (`card-nav-save`, juste sous l'en-tête) : barre fine + texte (clés i18n `labo.btn.analyse_pct`/`labo.btn.analyse_ok`, réutilisées). Hauteur TOUJOURS réservée (jamais `display:none`, seul le contenu change) pour ne jamais déplacer la navigation, la barre d'évaluation ni aucun bouton (régression #332). Les colorations de l'historique et le bouton « Voir le meilleur coup » s'activent au fur et à mesure, comme avant (`socket.on("analyse_coup")` met à jour `reviewMoves[idx]` puis appelle `renderReview()`).

### Point 4 — Jamais pendant une partie Lichess en cours

Deux gardes indépendantes :
- **Client** : `_reviewMaybeAutoAnalyse(skip)` reçoit `skip=true` si `data.source === "lichess"` dans le handler `game_over` — même garde inconditionnelle que #335/#341 (toute partie de source Lichess, pas seulement « en cours », par symétrie avec l'existant).
- **Serveur, en défense** : `on_analyser_pgn` refuse toute demande si `_app_state != "game_over"`. Lichess utilise le même état générique `"playing"` que les autres modes pendant la partie (aucun état dédié) — simuler une partie Lichess en cours revient donc à simuler `_app_state="playing"`, testé directement (`test_analyser_pgn_refuse_si_partie_lichess_en_cours`).
- Garantie architecturale inchangée en toile de fond : l'écran d'analyse n'est de toute façon jamais atteint pendant une partie Lichess en cours (`test_issue333_lichess_no_engine.py`, inchangé, toujours vert).

### Point 5 — Navigation et arrêt propre

Nouvel event socket `annuler_analyse_pgn` : positionne un `threading.Event` serveur (un seul à la fois, `server.py::_analyse_cancel_event`), vérifié par `EngineManager.analyser_partie(..., should_continue=...)` (nouveau paramètre optionnel dans `nicsoft/engine/engine_analysis.py`) avant chaque coup. Le moteur est fermé (`manager.quit()`) dans tous les cas via `finally`, qu'il y ait eu annulation ou non. Une analyse interrompue n'émet JAMAIS `analyse_terminee` — jamais enregistrée comme complète. Appelée par `_viderAnalyse()` (couvre donc aussi le retour au menu, qui l'appelait déjà) et par `_reviewMaybeAutoAnalyse()` elle-même dès qu'une AUTRE partie se charge pendant qu'une analyse tourne.

Jeton de génération `gen` (compteur client incrémenté à chaque nouvelle analyse, envoyé dans `analyser_pgn`, renvoyé tel quel par `analyse_coup`/`analyse_terminee`) : le client ignore tout résultat dont le `gen` ne correspond plus à l'analyse courante — même leçon que #338 (résultat tardif d'une autre position/partie jamais appliqué).

### Point 6 — Cohabitation avec les lignes à la demande (#335)

**Observé** : les deux fonctionnalités construisent chacune leur PROPRE `EngineManager` (jamais partagé) — l'analyse complète automatique et le service de lignes à la demande peuvent donc, en théorie, faire tourner deux process moteur en même temps dès que l'utilisateur navigue dans l'historique pendant que l'analyse complète tourne encore en arrière-plan.

**Décision** : ne pas fusionner les deux moteurs (risque de régression trop élevé sur #335/#338/#341, qui dépendent tous du comportement actuel de `ReviewMultiPVService`) — priorité coopérative seulement. `server.py::_review_lines_pending()` lit `ReviewMultiPVService.has_pending()` (nouvelle méthode, sans jamais instancier son moteur comme effet de bord) ; le callback de l'analyse complète cède une pause de 0.2s avant d'émettre le résultat d'un coup si une ligne à la demande est en attente — jamais plus qu'une pause de ce type par coup analysé, jamais de blocage total. Non mesuré avec un vrai moteur (interdit en test) : l'effet réel sur la charge processeur en conditions réelles (deux vrais Stockfish actifs quelques secondes) n'a pas pu être observé, seul le déclenchement de la pause est testé (`test_cede_la_priorite_si_une_ligne_a_la_demande_est_en_attente`, faux moteur).

### Point 7 — Durée

Mesuré avec un faux moteur à coût nul (`EngineAnalysisMixin.analyser_partie` sur 40 coups aléatoires, sans aucun appel moteur réel) : ~2ms, ce qui n'établit que le coût d'orchestration Python (négligeable), pas une durée réelle. Un vrai Stockfish est bien présent sur cette machine (`/usr/games/stockfish`) mais n'a jamais été exécuté (interdit par les consignes du projet et par cette issue, point 8) : la durée réelle d'une analyse complète automatique sur une longue partie n'a donc **pas pu être établie empiriquement**. Par lecture de code : un appel `evaluate_move(depth=8)` par coup, plus un `get_punishment_line(depth=12)` supplémentaire uniquement pour les coups non-"bon" — le coût croît linéairement avec le nombre de coups, et uniquement les coups imprécis/erronés/gaffes ajoutent le calcul de séquence punitive. Le changement de comportement réel introduit par cette issue n'est pas la charge de calcul elle-même (strictement identique à un clic manuel sur l'ancien bouton) mais sa systématisation : CHAQUE partie chargée sur l'écran d'analyse déclenche maintenant ce calcul en arrière-plan, alors qu'avant il fallait un clic explicite — pas de problème identifié dans le code (toujours en arrière-plan, jamais bloquant, annulable), mais à garder à l'œil sur une très longue partie (100+ coups) en conditions réelles, faute de mesure possible ici.

### Point 8 — Tests

Aucun moteur réel, aucun réseau, comme pour #335/#338/#339/#341/#333.

**`nicsoft/tests/test_issue342_auto_analyse.py`** (nouveau, 15 tests, faux `EngineManager` injecté, thread rendu synchrone par un `threading.Thread` monkeypatché) : refus hors écran d'analyse (dont la simulation d'une partie Lichess en cours, `_app_state="playing"`, point 4 de l'issue), refus si `ALCHESS_SKIP_AUTO_ANALYSE=1`, chemin normal (jeton `gen` repris tel quel, moteur fermé), lecture `engine_path`/`engine_elo` depuis `config.json`, annulation en cours de route (moteur fermé, jamais `analyse_terminee` pour une analyse partielle), annulation sans analyse en cours (pas d'exception), nouvelle analyse qui annule la précédente pour une autre partie, priorité cédée au service de lignes à la demande, garde contre toute construction paresseuse involontaire de ce service, arrêt précoce de `EngineAnalysisMixin.analyser_partie` via `should_continue`.

**`nicsoft/tests/e2e/test_issue342_auto_analyse_e2e.py`** (nouveau, 9 tests Playwright, même chemin « Coller PGN » que #335/#338 — événements `analyse_coup`/`analyse_terminee` simulés via `socket.listeners()`, comme #338/#341, jamais de vraie requête serveur ayant d'effet) : absence du bouton supprimé, lancement automatique sur une partie collée, absence de relance sur une partie déjà analysée (commentaires complets), absence de déclenchement en mode Lichess, progression affichée puis terminée + activation de la coloration et du bouton « Voir le meilleur coup », résultat tardif d'une autre partie ignoré, changement de partie pendant l'analyse (annulation), retour au menu pendant l'analyse (arrêt), bouton « Vider l'analyse » (fonctionne, ne relance jamais en boucle).

**Garde-fou critique découvert en écrivant ces tests** : un vrai Stockfish est installé par le système sur cette machine (`/usr/games/stockfish`, trouvé par `find_stockfish()`). Sans intervention, le lancement automatique aurait fait tourner un VRAI moteur en arrière-plan pour CHAQUE test e2e existant qui charge un PGN (#335/#338/#339/#341 utilisent tous « Coller PGN »), jamais voulu en test automatisé. Corrigé par une nouvelle variable d'environnement `ALCHESS_SKIP_AUTO_ANALYSE=1` (même idiome que `ALCHESS_SKIP_BOARD`), lue par `server.py::on_analyser_pgn` (retour immédiat si définie) et ajoutée à la fixture partagée `nicsoft/tests/e2e/conftest.py::server_url` pour TOUS les tests e2e — jamais définie en usage normal, aucun effet en production.

Tests de non-régression exécutés et verts : suite complète hors e2e (`nicsoft/tests/ -m "not slow" --ignore=nicsoft/tests/e2e`, 1265 passed, 83 skipped) et suite e2e complète (`nicsoft/tests/e2e/`, 163 passed, 1 skipped) — en particulier `test_issue333_lichess_no_engine.py`, `test_issue333_lichess_human_resume.py`, `test_issue335_review_multipv.py`, `test_issue335_review_arrows_e2e.py`, `test_issue338_review_same_position.py`, `test_issue338_review_same_position_e2e.py`, `test_issue339_review_arrow_outline_e2e.py`, `test_issue341_review_eval_pov.py`, `test_issue341_review_eval_bar_e2e.py`, `test_analyse_engine_path.py`.

### Fichiers modifiés

- `nicsoft/web/templates/index.html` — suppression du bouton `btn-analyser` (seule occurrence, dans `#panel-gameover`) ; nouvelle ligne `#review-analyse-progress-row` dans `#card-nav-save`.
- `nicsoft/web/static/css/main.css` — styles `.game-gameover-analyse-progress-*` (hauteur fixe, jamais `display:none`).
- `nicsoft/web/static/app.js` — suppression de `lancerAnalyse()`/case `"lancer_analyse"` et de toutes les références à `btn-analyser`/`_movesUci` ; nouvelles fonctions `_reviewMaybeAutoAnalyse()`, `_reviewAnnulerAnalyseEnCours()`, `_reviewGameKey()`, `_reviewSetProgress()` ; appels ajoutés dans le handler `game_over` et dans `parsePgn()` ; `_viderAnalyse()` et `_updateActionButtons()` adaptés (sélecteur séquence toujours visible tant qu'une partie est chargée) ; `socket.on("analyse_coup"/"analyse_terminee")` réécrits (jeton `gen`, barre de progression).
- `nicsoft/web/static/i18n/fr.json`, `en.json`, `de.json` — suppression de `labo.btn.analyser`/`labo.btn.analyse_en_cours` (devenues inutiles), parité des 3 langues vérifiée.
- `nicsoft/web/server.py` — `on_analyser_pgn` : garde `ALCHESS_SKIP_AUTO_ANALYSE`, garde `_app_state != "game_over"`, jeton `gen`, annulation (`_analyse_cancel_event`), priorité aux lignes à la demande (`_review_lines_pending()`) ; nouveau handler `on_annuler_analyse_pgn`.
- `nicsoft/engine/engine_analysis.py` — `EngineAnalysisMixin.analyser_partie()` : nouveau paramètre optionnel `should_continue`.
- `nicsoft/engine/review_multipv.py` — `ReviewMultiPVService.has_pending()` (nouveau).
- `nicsoft/tests/e2e/conftest.py` — `ALCHESS_SKIP_AUTO_ANALYSE=1` ajoutée à la fixture `server_url`.
- `nicsoft/tests/test_issue342_auto_analyse.py` (nouveau), `nicsoft/tests/e2e/test_issue342_auto_analyse_e2e.py` (nouveau).
- `CONTEXTE.md` — entrée #342.
