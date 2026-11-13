# Changelog — Issue #323

# Issue #323 — Lichess : reprendre une partie en cours depuis le menu (reconstruction de la position avec cases rouges et LED), retrait du message éphémère « Nulle refusée » en double

## Contexte

Une partie Lichess continue même si AlChess s'arrête (plantage, coupure réseau, extinction de l'ordinateur) : la pendule de Lichess tourne et l'adversaire peut réclamer la victoire. Cette issue ajoute la possibilité de **reprendre la partie** depuis le menu, en reconstruisant la position physique sur l'échiquier guidé par l'écran et les LED — le mode jouable existant (`LichessGame`, validé en essais réels) est réutilisé tel quel pour le déroulement du jeu lui-même.

Livraison limitée au cas le plus simple explicitement permis par la consigne de repli : **reprise d'une partie amicale contre l'IA Lichess, variante standard**. Les parties humain-humain et de correspondance ne sont pas encore proposées — voir « Ce qui reste à faire » en fin de document.

## 1. Détection d'une partie en cours (point 1)

`nicsoft/modes/lichess/client.py::get_ongoing_games(token)` interroge `GET /api/account/playing` (délai court, 6s — ne doit jamais retarder l'ouverture du menu). Vérifié dans la spécification officielle `lichess-org/api` (dépôt GitHub, `doc/specs/tags/games/api-account-playing.yaml`, lu le 13/11/2026) : cette route ne déclare que `security: [{OAuth2: []}]`, sans scope nommé — même jeton, aucun droit supplémentaire, contrairement à `/api/challenge/ai` qui exige `board:play`.

La réponse (`nowPlaying`) est filtrée pour ne garder que les parties `source=ai` + `variant.key=standard` — seul cas que l'interface « échiquiers » (Board API, déjà utilisée par `GameClient`) permet de rejouer dans cette livraison. Lichess classe `nowPlaying` par urgence (« most urgent games are listed first », doc officielle) ; en l'absence d'horodatage de création dans cette réponse, la partie la plus urgente (première de la liste filtrée) est prise comme meilleure approximation disponible de « la plus récente », et une seule est proposée même s'il y en a plusieurs (`total_candidates` journalisé pour le savoir).

Pas de jeton, jeton refusé, limite de requêtes, ou coupure réseau → aucun message alarmant : `{"status": "invalid"/"rate_limited"/"network_error"}` fait simplement disparaître la proposition de reprise (`check_lichess_resumable()`, `core/game_manager_modes/lichess.py`), journalisé en WARNING sans jamais le jeton.

Appelé une seule fois à l'ouverture du menu Lichess (`alchess.py`, action `mode:lichess`, en thread démon — jamais en boucle), pas à chaque rafraîchissement.

## 2. Proposition dans le menu (point 2)

Nouveau bandeau `#lichess-resume-banner` (fond contrasté, en tête de `#screen-config-lichess`) affiché sur réception de l'évènement `lichess_resumable` : adversaire, couleur, cadence approximative (`speed` Lichess traduit — l'API ne renvoie pas la cadence exacte initial+incrément sur cette route), trait, et minutes restantes **côté utilisateur uniquement** (`secondsLeft` de `/api/account/playing` est le temps du point de vue du compte authentifié — confirmé en lisant `lila/modules/core/src/main/game/Pov.scala::remainingSeconds` — le temps de l'adversaire n'est disponible qu'une fois le flux de partie rouvert, affiché ensuite par les pendules normales de l'écran de jeu). Nom d'adversaire et tout texte Lichess insérés exclusivement via `textContent` (jamais interpolés dans du HTML — gardé par test e2e dédié avec un nom piégé `<img onerror=...>`).

## 3. Reprise — écran de mise en place (point 3)

Au clic (`launch_lichess_resume()`), `_peek_game_full()` ouvre le flux de la partie juste le temps de lire le premier `gameFull` (couleur, niveau IA, cadence réelle via `clock.initial`/`clock.increment`, coups déjà joués, statut), puis referme cette connexion avant que `LichessGame` n'ouvre la sienne pour jouer réellement (deux connexions courtes et indépendantes, plus simple et robuste qu'un partage de flux entre les deux modules).

`LichessGame` gagne un paramètre `resuming: bool` : si vrai, `self._resume_pending` reste actif jusqu'à ce que la position physique (relue en continu) corresponde à `self.board.board_fen()` — qui reste la cible à jour même si l'adversaire joue pendant la reconstruction (coups appliqués par le flux normal, dans la même boucle `_main_loop()`). Nouvelle méthode `_tick_resume_setup()` (appelée par `_tick_physical()` tant que `_resume_pending`) : compare position physique/cible, allume les LED des cases qui diffèrent (`_update_resume_setup_leds()`, jamais testé sur le vrai plateau — aucun matériel disponible pour cette issue), et émet l'évènement dédié `lichess_resume_setup` (`active`, `expected_fen`, `physical_fen`). Côté navigateur, ce nouvel évènement réutilise `renderBoardWithErrors()` (déjà utilisée par `lichess_illegal_position`, la pause auto et le labo) pour les cases rouges sur `#board`, orienté comme le reste de la partie (couleur déjà connue via `lichess_init`), plus un bandeau dédié `#lichess-resume-setup` indiquant que la partie et la pendule continuent.

Dès que la position correspond : `_resume_pending` repasse à faux, les attentes de début de partie que `_apply_new_moves()` a pu positionner avant même l'écran de mise en place (réplication du dernier coup adverse) sont neutralisées pour ne pas redemander une confirmation déjà satisfaite, et le jeu normal reprend sans aucun autre changement — pendules, boutons, messages du mode existant.

## 4. Cas traités (point 4)

- **(a) à l'utilisateur de jouer** et **(b) à l'adversaire de jouer** : la cible de mise en place est toujours `self.board.board_fen()`, reconstruite depuis la liste de coups du premier `gameFull` — correcte dans les deux cas sans distinction de code.
- **(c) partie terminée entre-temps** : détectée dès le premier `gameFull` par le mécanisme existant (`_check_finished()`, inchangé) — `game_over` devient vrai avant qu'aucun tick physique n'ait lieu ; le PGN est enregistré comme toute partie terminée (voir point 6).
- **(d) l'adversaire joue pendant la reconstruction** : `_tick_resume_setup()` relit `self.board.board_fen()` à chaque tick (mis à jour par le flux en continu) — la cible progresse sans jamais perdre les cases déjà correctement posées par l'utilisateur.
- **(e) partie avec moins de deux coups** : `_request_resign_or_abort()` (annulation vs abandon selon `len(self.board.move_stack) < 2`) et le décompte du premier coup (`_maybe_activate_first_move_deadline()`) sont entièrement inchangés — `self.board.move_stack` est déjà reconstruit depuis le premier `gameFull`, donc ce calcul reste correct pour une partie reprise.
- **(f) échiquier non connecté au moment de la reprise** : `_open_board_with_retry()` (réessais existants, #317) puis, pendant la mise en place elle-même, `_register_board_lost()`/`_maybe_attempt_reconnect()` (reconnexion automatique existante, #314) — jamais d'abandon automatique.

## 5. Règles Lichess inchangées (point 5)

Aucun moteur ni module d'analyse n'est importé par `game.py`/`game_manager_modes/lichess.py` (vérifié par un test qui fait échouer volontairement `find_stockfish`/`find_lc0`/`load_maia_weights` si appelés pendant une partie reprise). Menu verrouillé pendant la partie (mécanisme existant `_OTHER_MODE_ACTIONS`, inchangé). Boutons Abandonner/Proposer nulle désormais aussi désactivés tant que `_resume_pending` (ajouté à `_compute_action_buttons()`). Le jeton reste exclusivement côté serveur (`get_ongoing_games()`/`_peek_game_full()` ne le transmettent jamais au navigateur ni dans un journal — vérifié par test avec un jeton factice et `caplog`).

## 6. PGN (point 6)

`self.board` (et donc `self.board.move_stack`) est reconstruit depuis le tout premier coup de la partie (appliqué dès le premier `gameFull`, qu'il date d'avant ou d'après la reprise) : `_save_pgn()`/`_finalize()` (inchangés) enregistrent donc la partie reprise en entier, au même endroit que toute autre partie Lichess (`PGN/Lichess/Amicale/`).

## 7. Nettoyage — message éphémère « Nulle refusée » (point 7)

Les trois messages éphémères de nulle (`toast.lichess_draw_sent`, `toast.lichess_draw_refused`, `toast.lichess_draw_accepted`) ont été retirés d'`app.js` (`socket.on("lichess_draw_proposed"/"lichess_draw_refused"/"lichess_draw_accepted")`) : le bandeau persistant `#lichess-draw-wait-msg` (en place depuis #321) suffit déjà et reste seul affiché. Les trois clés i18n restent définies dans `fr/en/de.json` (plus utilisées mais inoffensives — aucune autre clé n'y fait référence) ; un test de garde existant (`test_issue310_lichess_corrections.py::test_extraction_cles_lichess_trouve_bien_des_cles_connues`), qui s'appuyait sur deux de ces clés comme exemples connus, a été mis à jour pour en citer deux toujours utilisées.

## 8. Journal (point 8)

Logger `niclink.lichess`, niveau INFO, sans jamais le jeton :
- liste reçue (`check_lichess_resumable()`) : nombre de parties reprenables candidates, identifiant de la partie proposée ;
- reprise demandée (`launch_lichess_resume()`) : identifiant de la partie ;
- état reçu au moment de la reprise (`_run_lichess_resume()`) : couleur, statut, nombre de coups déjà joués ;
- position reconstruite / jeu normal repris (`_tick_resume_setup()` / `_run_lichess_resume()`).

## 9. Tests

Sans réseau (urllib mocké, faux transport scénarisé) et sans matériel (double léger de l'échiquier) :

- `nicsoft/tests/test_issue323_lichess_resume.py` (36 tests) : `get_ongoing_games()` (jeton absent/refusé/limité/coupure réseau/réponse illisible, filtrage source+variante, partie la plus urgente proposée si plusieurs) ; `check_lichess_resumable()` (sans jeton, erreur réseau silencieuse avec vérification `caplog` que le jeton n'apparaît jamais, aucune partie, partie proposée) ; `LichessGame(resuming=True)` : boutons désactivés pendant la mise en place, cases en erreur + LED signalées, position déjà correcte reprend immédiatement, reprise puis coup utilisateur détecté normalement, cible mise à jour sans perte de travail quand l'adversaire joue pendant la reconstruction (cas d), échiquier perdu pendant la mise en place sans abandon automatique, cas (e) moins de deux coups, cas (c) partie déjà terminée (PGN enregistré) ; scénario complet multi-thread (mise en place → coup utilisateur, sans aucun moteur) ; `launch_lichess_resume()`/`_run_lichess_resume()` (mode déjà actif, sans identifiant, sans jeton, erreur réseau, échiquier non détecté, jeton refusé) ; nouvelles clés i18n (fr/en/de) ; câblage `app.js` (nouveaux évènements/actions présents, jamais d'innerHTML pour le nom d'adversaire, réutilisation de `renderBoardWithErrors`).
- `nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py` (7 tests, Playwright, dossier `nicsoft/tests/e2e/`) : bandeau masqué sans partie en cours, bandeau affiché avec les bonnes informations, nom d'adversaire piégé (`<img onerror=...>`) jamais exécuté comme HTML, clic sur « Reprendre » envoie l'action avec le bon identifiant de partie, écran de mise en place affiche le bandeau et des cases rouges sur `#board`, bandeau masqué une fois la position confirmée, boutons Abandonner/Proposer nulle restent grisés par défaut pendant la mise en place.
- `nicsoft/tests/test_issue310_lichess_corrections.py` : mis à jour (deux clés i18n obsolètes remplacées dans le test de garde de l'extraction).

Suite complète (hors e2e) : 949 passés, 80 ignorés (matériel/réseau réel). Suite e2e Lichess : 55 passés. Suite e2e complète : 99 passés, 1 ignoré. `python -m py_compile` : OK sur tous les fichiers Python modifiés. Démarrage réel du serveur (`ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) vérifié (HTTP 200, aucune erreur au démarrage).

### Ce qui n'a pas pu être testé

- Comportement réel des LED pendant la mise en place (`_update_resume_setup_leds()`) et de la reconnexion automatique de l'échiquier pendant cette phase : aucun matériel Chessnut disponible dans cet environnement — repose sur les mêmes primitives (`set_led`, `turn_off_all_leds`, reconnexion #314) déjà utilisées et validées ailleurs dans le module.
- Scénario avec une vraie partie Lichess réelle en cours (détection, reprise de bout en bout contre le vrai serveur Lichess) : aucun jeton Lichess disponible dans cet environnement de test — entièrement couvert côté logique par les tests avec faux transport/urllib mocké ci-dessus.
- Partie de correspondance ou partie contre un autre humain : hors scope de cette livraison (voir ci-dessous).

### Ce qui reste à faire

- Proposer la reprise de parties humain-humain et de correspondance (actuellement filtrées : seules les parties `source=ai` + variante standard sont proposées).
- Afficher le temps restant de l'adversaire dans le bandeau du menu (nécessiterait un second appel réseau ou d'attendre l'ouverture du flux de partie — non fait pour rester dans le délai court demandé pour la détection).
- Proposer plusieurs parties reprenables à la fois si l'utilisateur en a plusieurs en cours (actuellement une seule, la plus urgente, comme demandé pour cette première livraison).

## Fichiers modifiés

- `nicsoft/modes/lichess/client.py` : `get_ongoing_games()`.
- `nicsoft/core/game_manager_modes/lichess.py` : `check_lichess_resumable()`, `launch_lichess_resume()`, `_run_lichess_resume()`, `_peek_game_full()`.
- `nicsoft/modes/lichess/game.py` : `LichessGame(resuming=...)`, `_tick_resume_setup()`, `_update_resume_setup_leds()`, `_differing_squares()`, gating de `_compute_action_buttons()`.
- `nicsoft/core/game_manager.py` : réexport des nouvelles fonctions.
- `nicsoft/web/alchess.py` : déclenchement de la détection à l'ouverture du menu Lichess, routage de l'action `start_lichess_resume`.
- `nicsoft/web/static/app.js` : bandeau de reprise, écran de mise en place, retrait des 3 toasts éphémères de nulle.
- `nicsoft/web/templates/index.html` : bandeau `#lichess-resume-banner`, bandeau `#lichess-resume-setup`.
- `nicsoft/web/static/css/main.css` : styles du bandeau de reprise.
- `nicsoft/web/static/i18n/{fr,en,de}.json` : nouvelles clés de reprise.
- `nicsoft/tests/test_issue323_lichess_resume.py`, `nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py` : nouveaux.
- `nicsoft/tests/test_issue310_lichess_corrections.py` : clés i18n de garde mises à jour.
- `CONTEXTE.md` : paragraphe Lichess mis à jour.
