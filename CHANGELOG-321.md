# Changelog — Issue #321

# Issue #321 — Lichess : boutons Abandonner et Proposer nulle actifs seulement à son tour, et messages de nulle qui restent affichés

## Contexte

Deux essais réels d'Alain le 13 novembre 2026 (blancs puis noirs) ont révélé plusieurs gênes autour de la nulle et de la reproduction des coups :

1. Les boutons « Abandonner » et « Proposer nulle » étaient actifs en permanence, y compris pendant que l'adversaire réfléchissait ou que l'utilisateur devait encore reproduire son coup sur l'échiquier — séquence vécue : proposition de nulle, puis coup adverse reproduit, puis coup propre joué (aucune indication que l'offre était en attente), puis « Nulle refusée » apparu brusquement.
2. Les messages de nulle (proposée/refusée/acceptée) étaient de brefs toasts éphémères, ratés en alternant le regard entre l'écran et l'échiquier physique.
3. Lecture du journal : l'offre part vers Lichess au clic, mais l'IA ne répond qu'en jouant son propre coup **après** celui de l'utilisateur — source de confusion non expliquée à l'écran.
4. Partie avec les noirs : un pion blanc (d4) joué par erreur à la place du coup noir a laissé affichée la phrase « Jouez votre premier coup, sinon la partie sera annulée par Lichess » sans aucune indication lisible que la position physique était invalide.
5. Le décompte du premier coup n'existe que si Lichess envoie `expiration` — absent lors de cet essai.

## 1. Boutons actifs seulement à son tour (points 1 et 2)

`LichessGame._compute_action_buttons()` (`nicsoft/modes/lichess/game.py`) calcule `(resign_enabled, draw_enabled)` à partir de l'état déjà suivi par la partie — jamais d'un nouvel état dupliqué :
- `resign_enabled` / `draw_enabled` de base = trait de l'utilisateur **ET** position physique alignée (ni réplication du coup adverse, ni recalage après reconnexion, ni promotion en attente, ni position illégale, ni échiquier perdu).
- Exception de sécurité n°1 : `resign_enabled` reste vrai si l'échiquier est perdu (jamais bloquer l'utilisateur).
- Exception de sécurité n°2 (comportement préexistant conservé) : `draw_enabled` reste faux tant qu'une offre de l'utilisateur est déjà en attente de réponse — jamais deux propositions superposées.
- Les boutons de réponse à une offre adverse (accepter/refuser) ne passent jamais par ce calcul : `_process_browser_actions()` les traite sans condition, à tout moment.

`_sync_turn_ready()` envoie l'évènement `lichess_action_buttons` (`{"resign_enabled", "draw_enabled"}`) uniquement quand l'état change (pas de bruit à chaque tick), appelé :
- à chaque tick physique (`_tick_physical()`, ~50ms) — couvre tour adverse, réplication en cours, recalage, promotion, position illégale, échiquier perdu ;
- à chaque transition explicite de fin de partie (abandon, annulation, retour au menu, fin détectée par le flux) — ces chemins quittent la boucle principale avant le tick suivant.

Côté `app.js`, `_lichessSetActionButtons(resignEnabled, drawEnabled, showHint)` est la **seule** fonction qui pose l'attribut `disabled` sur `#btn-resign`/`#btn-nulle` — jamais recalculé côté navigateur à partir d'autres signaux, pour que les exceptions de sécurité restent cohérentes avec la seule source de vérité (le thread `LichessGame`). Désactivés par défaut dès `lichess_init` (y compris pour les deux couleurs, dès le tout début de partie), corrigés par le premier `lichess_action_buttons` qui suit dans la même fonction Python. Un petit texte (`#lichess-actions-hint`, clé `lichess.boutons_actifs_a_votre_tour`) apparaît près des boutons quand l'un des deux est désactivé. `init`/`init_hh` (pédagogique/HH) forcent explicitement les deux boutons actifs — ce mécanisme ne concerne que Lichess.

## 2. Messages de nulle persistants (points 3 et 4)

Les trois anciens toasts éphémères (`toast.lichess_draw_sent/refused/accepted`, conservés en complément) sont remplacés comme information principale par un bandeau unique et persistant, réutilisé pour les 3 états plutôt que d'en créer un second : `#lichess-draw-wait-msg`, déplacé près de « Tour en cours » (carte `turn-info`), classe `.lichess-draw-status-banner` (gros caractères).

- **Proposée** (`lichess_draw_proposed`) : « Nulle proposée : l'adversaire répondra à son prochain coup, après le vôtre. » — dit explicitement que la réponse vient après le coup de l'utilisateur, contrairement à ce qu'Alain avait cru comprendre le 13/11.
- **Refusée** (`lichess_draw_refused`) : « Nulle refusée par l'adversaire. », en rouge (`.lichess-banner-danger`) — reste affiché au moins jusqu'au coup suivant **joué par l'utilisateur** (`_lichessDrawBannerPendingClearOnOwnMove`, effacé sur le premier `lichess_move` reçu avec `opponent_move:false` — pas sur la reproduction du coup adverse qui précède).
- **Acceptée** (`lichess_draw_accepted`) : « Nulle acceptée — partie terminée. »

La règle de décision du refus elle-même (issue #318 : jamais sur l'écho de notre propre coup, seulement sur un vrai coup adverse sans acceptation) n'est pas modifiée.

## 3. Position physique incorrecte pendant la partie (point 5)

Nouvel évènement dédié `lichess_illegal_position` (`{"active", "expected_fen", "physical_fen"}`), émis par `_activate_illegal_position()`/`_clear_illegal_position()` dans `LichessGame._check_user_move()` — **distinct** de `lichess_position_wait` (qui concerne la reproduction du coup adverse, scénario différent). Déclenché dans les mêmes conditions qu'avant (`ILLEGAL_STABLE_READS_REQUIRED` lectures stables identiques, ni la position attendue ni un coup légal), mais pendant le tour de l'utilisateur spécifiquement.

Côté `app.js` : bandeau `#lichess-illegal-position` (clé `lichess.position_incorrecte`, « Position incorrecte : corrigez les cases en rouge sur l'échiquier. ») + cases en rouge sur l'échiquier de l'écran via `renderBoardWithErrors()` — fonction déjà existante (pause auto, labo), pas de nouveau mécanisme de surlignage. Remplace la phrase du premier coup (`#lichess-first-move-deadline`) tant qu'elle est active.

**Ce qu'Alain a réellement vu le 13/11 (reconstitué depuis le code d'avant ce correctif)** : deux bannières simultanées, aucune des deux adaptée au problème réel — (a) `#lichess-first-move-deadline` restée affichée (« Jouez votre premier coup, sinon annulée »), puisque rien ne la désactivait avant que l'utilisateur joue un coup *qui lui soit attribué* ; (b) le texte générique `#lichess-position-wait` (« Reproduisez le coup sur l'échiquier physique »), déclenché par le même code qui envoie maintenant `lichess_illegal_position` — un texte pensé pour "reproduire le coup adverse", pas pour "votre coup est illégal, corrigez ces cases", et sans aucune case en rouge. Aucune des deux ne disait quoi corriger ni où — d'où la confusion jusqu'à ce qu'il remette le pion blanc en place par essai-erreur.

## 4. Décompte du premier coup (point 6)

Vérifié aujourd'hui (13/11/2026) dans le code public de Lichess (pas de documentation officielle dédiée trouvée) :
- `lila` (branche `master`, `modules/game/src/main/Game.scala::timeForFirstMove`) : hors tournoi, variante standard — UltraBullet 15s, Bullet 20s, Blitz 25s, Rapid 30s, Classical/Correspondence 35s (×1,5 en chess960, non applicable ici).
- `scalachess` (`Speed.scala::byTime`) : bornes de cadence en secondes estimées — UltraBullet [0,30), Bullet [30,180), Blitz [180,480), Rapid [480,1500), Classical [1500,21600), sinon Correspondence.
- `scalachess` (`Clock.scala::estimateTotalSeconds`) : `limite + 40×incrément`.

Ces trois extraits ont été relus mot pour mot dans le code actuellement publié (`curl raw.githubusercontent.com`) — le délai réel **est** établi, donc pas de repli sur « pas de décompte » : `estimated_first_move_deadline_s(clock_limit_s, clock_increment_s)` (déjà présent dans ce fichier avant la reprise de ce traitement, vérifié conforme ci-dessus) est utilisé par `_maybe_activate_first_move_deadline()`/`_maybe_push_clock()` quand `expiration` est absent du message Lichess — `_first_move_deadline_seconds_and_estimated()` retourne `(secondes, estimated=True)` dans ce cas. Journalisé (`_log_game_state_received`) : `expiration` brut, présent ou non, à chaque état reçu — permet de confirmer a posteriori si/quand Lichess l'envoie réellement (observé absent lors de l'essai du 13/11).

Côté interface : texte dédié quand estimé (clé `lichess.premier_coup_decompte_estime`, « … dans **environ** {seconds} secondes ») — jamais présenté comme exact. Le texte (estimé ou exact) passe en rouge (`.lichess-banner-danger`) à 5 secondes ou moins.

## 5. Fichiers modifiés

- **`nicsoft/modes/lichess/game.py`** : `_compute_action_buttons()`/`_sync_turn_ready()` (nouveau), `_activate_illegal_position()`/`_clear_illegal_position()` (nouveau), `_tick_physical()` scindé en `_tick_physical_inner()` + appel systématique de `_sync_turn_ready()`, `_check_user_move()` met à jour l'état de position illégale, `_maybe_activate_first_move_deadline()`/`_maybe_push_clock()`/`_first_move_deadline_seconds_and_estimated()` (nouveau) pour l'estimation de repli, appels de synchronisation ajoutés dans `_apply_game_full()`/`_apply_game_state()`/`_check_finished()`. `_turn_ready`/`_last_position_wait_kind` (champs inutilisés laissés par une tentative précédente de cette même issue) supprimés au profit de `_action_buttons_state`.
- **`nicsoft/web/static/app.js`** : `_lichessSetActionButtons()` (nouveau), gestionnaires `lichess_action_buttons`/`lichess_illegal_position` (nouveaux), bandeau de nulle persistant (`_lichessShowDrawBanner()`), rendu du décompte du premier coup mis à jour (estimation + rouge à 5s), remplacement de la phrase du premier coup par le message de position illégale quand actif, réinitialisation des boutons dans `init`/`init_hh`/`lichess_init`/`_lichessHideStatusBanners()`.
- **`nicsoft/web/templates/index.html`** : `id="btn-resign"` ajouté au bouton Abandonner, `#lichess-illegal-position` et `#lichess-draw-wait-msg` déplacés dans la carte « Tour en cours », `#lichess-actions-hint` ajouté dans la carte Actions.
- **`nicsoft/web/static/css/main.css`** : `.lichess-draw-status-banner`, `.lichess-info-banner.lichess-banner-danger`, `.lichess-actions-hint`.
- **`nicsoft/web/static/i18n/{fr,en,de}.json`** : `lichess.nulle_attente_reponse` (texte mis à jour), `lichess.nulle_refusee_banner`, `lichess.nulle_acceptee_banner`, `lichess.position_incorrecte`, `lichess.boutons_actifs_a_votre_tour`, `lichess.premier_coup_decompte_estime` (nouvelles clés) — les 3 langues ont le même jeu de clés (vérifié).
- **`nicsoft/tests/test_issue321_lichess_boutons_et_nulle.py`** (nouveau, 9 tests, sans réseau ni matériel).
- **`nicsoft/tests/e2e/test_issue321_lichess_e2e.py`** (nouveau, 10 tests Playwright, évènements socket simulés).
- **`nicsoft/tests/e2e/test_issue310_lichess_e2e.py`** : fixture `at_game_lichess` complétée d'un `lichess_action_buttons` simulé (sinon `test_game_lichess_bouton_nulle_visible` échouait — ce test vérifiait l'ancien comportement où `lichess_init` activait directement le bouton).
- **`nicsoft/tests/test_issue311_lichess_sequencing.py`** : `test_decompte_premier_coup_sans_champ_expiration` mis à jour pour refléter l'estimation de repli (avant #321 : pas de décompte sans `expiration` ; depuis #321 : estimation locale).
- **`CONTEXTE.md`** : entrée #321 ajoutée à la section Lichess.

## 6. Tests

**Python** (`test_issue321_lichess_boutons_et_nulle.py`, sans réseau ni matériel — `FakeBoard`/`FakeTransport` comme le reste de la suite Lichess) :
- boutons grisés au tout début de partie pour les noirs, avant et pendant la reproduction du coup adverse (2 tests) ;
- boutons actifs dès le début pour les blancs, et pour les noirs une fois le coup reproduit (2 tests) ;
- position illégale (reproduction exacte du scénario réel : pion blanc d2-d4 joué à la place du coup noir) → boutons grisés, évènement avec les bonnes cases, puis réactivation une fois la pièce remise en place (1 test) ;
- abandon possible échiquier perdu même hors tour, accepter/refuser une offre adverse toujours possible boutons désactivés, pas de double offre de nulle (4 tests).

**Navigateur** (`test_issue321_lichess_e2e.py`, Playwright réel, évènements socket simulés comme `test_issue310_lichess_e2e.py` — sans réseau ni partie Lichess réelle) :
- boutons désactivés par défaut puis activés par `lichess_action_buttons`, exception Abandonner seul actif (3 tests) ;
- bandeau de nulle : texte « après »/« after »/« nach », persistance jusqu'au coup de l'utilisateur, bandeau dédié pour l'acceptation (3 tests) ;
- position incorrecte : remplace la phrase du premier coup, case(s) rouge(s) sur l'échiquier, réapparition de la phrase une fois corrigée (1 test) ;
- décompte du premier coup : pas rouge au-dessus de 5s, rouge à 5s ou moins, mention « environ »/« approximately »/« etwa » quand estimé (3 tests).

Suite complète (`pytest nicsoft/tests/`) : 993 passed, 81 skipped (tests `hardware`, non exécutés sans échiquier physique) — aucune régression.

**Non testable sans le matériel réel** : le ressenti visuel exact sur l'échiquier physique Chessnut (LED, cases rouges perçues en conditions réelles de luminosité), et la confirmation sur une vraie partie Lichess que `expiration` est bien absent pour toutes les cadences (seul observé pour la cadence de l'essai du 13/11) — le journal enrichi (`_log_game_state_received`) permettra de le confirmer lors du prochain essai réel.

## 7. Reprise de travail

Ce traitement est une **reprise d'un worktree d'une tentative précédente de cette même issue #321** (commits `avant-321-...` déjà présents en double dans l'historique local avant cette session). Le travail déjà présent se limitait à une ébauche incomplète dans `nicsoft/modes/lichess/game.py` : les fonctions pures d'estimation du délai du premier coup (`speed_key_for_clock`, `estimated_first_move_deadline_s`, constantes `_FIRST_MOVE_TIMEOUT_BY_SPEED`) — vérifiées exactes contre le code source actuel de `lila`/`scalachess` et conservées sans modification — et un champ `_turn_ready`/un appel à une méthode `_sync_turn_ready()` non définie (aurait levé `AttributeError` dès le premier abandon/retour au menu). Aucun autre point de la tâche (boutons, messages de nulle persistants, position illégale, interface) n'était ébauché.
