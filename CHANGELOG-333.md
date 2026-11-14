# Changelog — Issue #333

## Lichess : reprendre une partie en cours contre un humain, y compris depuis le menu principal, avec reconnexion rapide des flux

**Règle absolue respectée à la lettre** : aucune recherche d'adversaire, aucune partie, aucun défi réel sur lichess.org à aucun moment de ce travail. Le vrai jeton d'Alain n'a jamais été lu ni utilisé, ni dans les tests ni dans les essais — faux serveur local uniquement (`FakeTransport`/`FakeBoard`, garde réseau `conftest.py::_guard_no_real_lichess_network` de #327, revérifié encore actif). Le réseau n'a servi qu'à lire la documentation publique de Lichess (`lichess-org/api`) et le code source public de `lichess-org/lila` via `gh api`/`gh search` (lecture seule, GitHub public).

### Contexte important découvert avant de coder

La reprise contre l'IA (#323/#325) avait déjà construit un `LichessGame` entièrement **générique** IA/humain : écran de mise en place (cases rouges + LED, cible recalculée à chaque tick même si l'adversaire joue), nulle (désactivée en permanence seulement contre l'IA, réponse à une offre adverse toujours possible), décompte du premier coup (seulement si `user_color == "black"` et `moves_applied == 1`), pendules figées jusqu'aux deux premiers coups — tout cela avait été rendu générique dès #327 pour servir la recherche d'adversaire humain. Le vrai verrou pour la REPRISE d'une partie humaine n'était donc **pas** dans `LichessGame` mais dans deux endroits précis : (1) `client.py::get_ongoing_games()` marquait `resumable=False` pour toute partie dont `source != "ai"`, et (2) `_run_lichess_resume()` déduisait la couleur utilisateur uniquement via la présence d'`aiLevel` — impossible pour un humain. Ce diagnostic a permis une livraison beaucoup plus ciblée que redouté.

### Point 1 — Parties humaines reprenables (établi par lecture de doc + code public)

Lu le 14/11/2026 via `gh api`/`gh search` (lecture seule, dépôts publics) :
- `doc/specs/lichess-api.yaml` (lichess-org/api), tag Board : « Time controls: Rapid, Classical and Correspondence only » — confirme que la cadence, pas l'origine (site web, application mobile, API), est le facteur déterminant.
- `app/controllers/PlayApi.scala::WithPovAsBoard` (lichess-org/lila) : `if !lila.game.Game.isBoardCompatible(pov.game) then BadRequest(jsonError("This game cannot be played with the Board API."))` — appliqué à TOUTE partie du compte, sans distinction d'origine.
- `modules/game/src/main/Game.scala::isBoardCompatible` + `modules/core/src/main/game/misc.scala` : `game.clockConfig.forall(c => Speed(c) >= Speed.Rapid || ((game.hasAi || sourceIs(Friend) || sourceIs(Api)) && Speed(c) >= Speed.Blitz))`.

**Établi** : une partie contre un humain créée directement sur lichess.org ou depuis le téléphone est reprenable par l'interface des échiquiers de Lichess dans les mêmes conditions qu'une partie créée par AlChess — rien ne distingue le site web de l'application mobile. Règle exacte retenue (`modes/lichess/client.py::_is_board_compatible`) :
- rapide/classique : toujours reprenable, quelle que soit la source ;
- blitz : reprenable seulement si créée par un défi direct (« Jouer avec un ami », `source="friend"`) ou via l'API (`source="api"`), ou contre l'IA — **jamais** si appariée par le lobby/un pool/un tournoi/arena/swiss à cette cadence ;
- bullet/ultra-bullet : **jamais** reprenable, aucune exception.
- variante non standard (Chess960...) : jamais reprenable aujourd'hui (LichessGame ne sait pas la rejouer), indépendamment de la cadence/source.

Chaque partie de `get_ongoing_games()` porte désormais, en plus de `resumable`, un `unresumable_reason` (`"variant"` / `"speed"` / `None`) — explication exacte distincte côté interface (`lichess.reprise_non_reprenable_variante` / `_cadence`, nouvelles clés i18n fr/en/de), jamais le message générique devenu trompeur. Correction d'une hypothèse erronée de #325 : un test existant (`test_get_ongoing_games_partie_humain_humain_reste_listee_non_reprenable`) affirmait qu'une partie blitz humaine par défi direct n'était pas reprenable — faux d'après la règle ci-dessus ; corrigé et remplacé par 5 tests couvrant chaque cas (défi direct blitz reprenable, appariement blitz non reprenable, bullet jamais, rapide humain toujours, variante non standard).

### Point 2 — Reprise (même chemin que l'IA, règles humaines respectées)

Comme établi ci-dessus, `LichessGame` n'a nécessité **aucune modification** pour les règles de jeu (nulle, décompte, pendules, mise en place, orientation) — déjà génériques. Seul `core/game_manager_modes/lichess.py::_run_lichess_resume()` a changé :
- Nouveau paramètre `known_color` (transmis par `launch_lichess_resume()`, lui-même nourri par le navigateur — voir point 3).
- Si `white`/`black` ne porte `aiLevel` ni l'un ni l'autre (partie humaine) : `known_color` devient `user_color` et `known_user_color` transmis à `LichessGame` ; sans `known_color` valide, **refus explicite** (jamais de couleur devinée au hasard — jouer/orienter le camp adverse serait pire qu'un refus).
- Journal dédié (`GameLog(game_id)`) créé **avant** le premier appel réseau (auparavant, la reprise n'avait aucun journal dédié avant la construction de `LichessGame` — seul le journal général) : couvre désormais « reprise demandée », « position cible lue », en plus de ce que `LichessGame`/`GameClient` y écrivent déjà (coups, boutons, pendule, connectivité, reconnexions — inchangé).

Non modifié, vérifié toujours correct par lecture : réponse à une offre de nulle de l'adversaire toujours traitée même pendant la mise en place (`_process_browser_actions`, jamais gardée par `_resume_pending`) ; cible de la mise en place recalculée à chaque tick (`self.board.board_fen()`) donc jamais perdue si l'adversaire joue pendant la reconstruction ; pendule poussée à chaque tour de boucle principale indépendamment de la mise en place (`_maybe_push_clock()` hors du bloc `_tick_resume_setup`) — donc visible et à jour pendant tout l'écran de mise en place, y compris celle de l'utilisateur si c'est son tour.

### Point 3 — Bandeau du menu principal

Nouveau conteneur `#lichess-menu-banner`/`#lichess-menu-banner-list` directement dans `#screen-menu` (`index.html`), rendu avec le **même** composant que l'écran Lichess (`_lichessOngoingGameCard()`, réutilisé tel quel — même boutons Reprendre/Abandonner). Alimenté par le **même** évènement `lichess_resumable` (aucune seconde détection ajoutée) — mais seulement rempli quand `#screen-menu` est réellement affiché (sinon duplication de boutons avec la liste de l'écran `config_lichess`, détecté et corrigé pendant les tests e2e). Déclenchement : `app.js` envoie l'action `lichess_menu_check` une seule fois par arrivée réelle sur le menu (débounce `_lichessMenuBannerChecked`, réarmé à la sortie du menu) ; `alchess.py` route cette action vers `check_lichess_resumable()` (fonction inchangée, déjà silencieuse sans jeton/réseau, délai court `_PLAYING_TIMEOUT_S=6s`). Le bandeau ne bloque jamais les autres modes (élément indépendant du reste du menu, masqué dès qu'un autre écran s'affiche).

### Point 4 — Reconnexion des flux (déjà existant, vérifié)

Vérifié par lecture du code AVANT de coder, comme demandé : `modes/lichess/game_client.py::GameClient.stream_game()` implémente déjà une reconnexion automatique (`RECONNECT_DELAYS_S=(1,2,4,8,30)` — essais rapprochés puis espacés), sans aucune limite d'essais (jamais d'abandon automatique), avec journalisation dédiée (`game_log.connectivity(...)`) et évènements `reconnecting`/`reconnected` déjà relayés au navigateur (`lichess_reconnecting`/`lichess_reconnected`) vers une bannière déjà présente et persistante (`#lichess-reconnecting-banner`, « Connexion à Lichess perdue, reconnexion… »). Un nouveau `gameFull` reçu à la reconnexion (toujours le premier évènement d'une connexion, doc officielle) resynchronise entièrement position et pendules côté `LichessGame` (`_apply_game_full` reconstruit `self.board` et rejoue tous les coups connus). **Rien n'a donc été codé pour ce point** — uniquement vérifié et couvert par un nouveau test de régression dédié (`test_reconnexion_flux_pendant_partie_reprise_sans_coup_perdu_ni_rejoue`) qui prouve qu'un coup joué par l'adversaire PENDANT une coupure, au niveau d'une partie REPRISE contre un humain, est appliqué exactement une fois (ni perdu ni rejoué) et déclenche la réplication physique (LED) exactement une fois pour le bon coup.

### Point 5 — Fair-play inchangé + test manquant ajouté

Aucune règle de fair-play modifiée (menu verrouillé, pas d'aide pendant la partie, jeton jamais journalisé/envoyé au navigateur, textes Lichess échappés — tout inchangé, déjà vérifié par les gardes existantes `test_issue303_html_escaping.py`/`test_issue304_security.py`). **Test manquant ajouté** (signalé par le rapport de clôture de #327) : nouveau fichier `nicsoft/tests/test_issue333_lichess_no_engine.py` — analyse **statique** (module `ast`, pas dynamique) de chaque fichier du mode Lichess (`modes/lichess/*.py` + `core/game_manager_modes/lichess.py`), qui échoue si une instruction d'import référence un module moteur (`nicsoft.engine.{engine_manager,uci_engine,maia_engine,rodent_engine,engine_detection,engine_availability,engine_analysis,move_quality,analyse}` ou `chess.engine`), **y compris nichée dans le corps d'une fonction** (couvre la reprise, `_run_lichess_resume`, sans avoir besoin de l'exécuter réellement) ou `subprocess` (voie alternative de lancement). Exclut volontairement `nicsoft.engine.{board_utils,pgn_manager,players,display}` — purs utilitaires python-chess/PGN déjà importés par `game.py`, sans rapport avec un moteur (vérifié par lecture de chacun de ces fichiers, aucun n'importe `chess.engine`).

### Point 6 — Journal de partie dédié

Voir point 2 : la reprise écrit désormais « reprise demandée » et « position cible lue » (couleur, statut, nombre de coups, adversaire IA ou non) dans le journal dédié **avant** la construction de `LichessGame`, en plus de tout ce qui y était déjà écrit (coups, boutons, pendule, connectivité/reconnexions, exceptions — inchangé, voir #326/#329). Jamais le jeton ni le tchat (inchangé).

### Point 7 — Tests exécutés

Entièrement sans connexion réelle (`FakeTransport`/`FakeBoard`, garde réseau de #327 toujours actif et revérifié vert) :
- `nicsoft/tests/test_issue333_lichess_no_engine.py` (11 tests) — aucun import moteur, y compris dans le corps des fonctions.
- `nicsoft/tests/test_issue333_lichess_human_resume.py` (21 tests) — couleur humaine blancs/noirs transmise correctement, refus sans couleur connue, non-régression IA, journal dédié couvre la demande/position cible, câblage `launch_lichess_resume`→`_run_lichess_resume`, nulle adverse pendant la mise en place toujours traitée, reconnexion du flux pendant une reprise humaine sans coup perdu ni rejoué, câblage du bandeau menu (`alchess.py`/`app.js`), clés i18n présentes dans les 3 langues.
- `nicsoft/tests/test_issue323_lichess_resume.py` — 2 tests ajustés (signature `_error=` en mot-clé après l'ajout de `known_color`), 1 assertion de dict étendue (`unresumable_reason`), 1 test corrigé + 4 tests ajoutés pour la règle de reprenabilité exacte (point 1).
- `nicsoft/tests/e2e/test_issue333_lichess_menu_banner_e2e.py` (5 tests, **dossier de navigateur réel** — Playwright, serveur AlChess en subprocess isolé, `~/NicLink/venv`) : bandeau affiché/absent, partie non reprenable (bouton Abandonner seul + explication), bandeau n'empêchant pas la navigation vers un autre mode, une seule requête par arrivée sur le menu. A révélé puis fait corriger un vrai défaut (boutons dupliqués dans le DOM, même `data-game-id`, quand le bandeau menu et la liste de l'écran Lichess étaient tous deux peuplés simultanément) — corrigé en ne remplissant le bandeau menu que lorsque `#screen-menu` est réellement affiché.

**Suites complètes exécutées** (aucune régression) :
- `python3 -m pytest nicsoft/tests --ignore=nicsoft/tests/e2e` → 1172 passed, 82 skipped.
- `~/NicLink/venv/bin/python -m pytest nicsoft/tests/e2e` → 117 passed, 1 skipped (dossier de navigateur Playwright, exécuté avec succès).

**Aucune exception dans les fils secondaires** : vérifié par lecture — `_stream_reader_loop` (game.py) encapsule déjà tout dans un `except Exception` large, journalise (`game_log.exception`) et ne laisse jamais rien remonter non intercepté (mécanisme de #326, inchangé, confirmé toujours actif par la suite de tests existante).

### Non vérifié sans vraie partie (interdit par consigne)

- Rendu réel côté Lichess d'un défi direct blitz entre amis repris par AlChess (la règle serveur est établie par lecture du code source, jamais exercée avec une vraie partie).
- Comportement exact d'une VRAIE coupure réseau pendant une VRAIE partie humaine reprise (le mécanisme de reconnexion est simulé via `FakeTransport`, jamais une vraie connexion Lichess interrompue).
- Rendu exact du bandeau menu avec un VRAI jeton et une VRAIE partie en cours (testé avec des données simulées, jamais avec un compte réel).

### Fichiers modifiés

- `nicsoft/modes/lichess/client.py` — `_is_board_compatible()` (nouveau), `get_ongoing_games()` étendu (`unresumable_reason`).
- `nicsoft/core/game_manager_modes/lichess.py` — `launch_lichess_resume()` (transmet `color`), `_run_lichess_resume()` (couleur humaine, journal dédié précoce).
- `nicsoft/web/alchess.py` — nouvelle action `lichess_menu_check`.
- `nicsoft/web/static/app.js` — `lichessResumeGame()` (transmet `color`), rendu de la raison exacte de non-reprenabilité, bandeau du menu principal (peuplement conditionnel, débounce d'arrivée sur le menu).
- `nicsoft/web/templates/index.html` — nouveau bandeau `#lichess-menu-banner`/`#lichess-menu-banner-list` dans `#screen-menu`.
- `nicsoft/web/static/i18n/{fr,en,de}.json` — 3 nouvelles clés (`lichess.reprise_non_reprenable_variante`, `_cadence`, `lichess.menu_banner_titre`), ajoutées simultanément dans les 3 langues.
- `nicsoft/tests/test_issue323_lichess_resume.py` — corrections/ajouts pour la règle de reprenabilité exacte, ajustement de signature.
- `nicsoft/tests/test_issue333_lichess_no_engine.py` (nouveau).
- `nicsoft/tests/test_issue333_lichess_human_resume.py` (nouveau).
- `nicsoft/tests/e2e/test_issue333_lichess_menu_banner_e2e.py` (nouveau).
- `CONTEXTE.md` — paragraphe #333 ajouté.

Aucune modification de `driver.py`, d'aucun moteur, d'`.audit.json` ni des dépendances ; aucun arrêt de processus par nom (les serveurs e2e sont arrêtés par leur PID exact via le mécanisme déjà existant de `conftest.py`) ; serveur de test lancé uniquement via le subprocess e2e déjà prévu (`ALCHESS_SKIP_BOARD=1`, `BROWSER=/bin/true`, `ALCHESS_DIR` isolé — variables déjà câblées dans `nicsoft/tests/e2e/conftest.py`, jamais modifiées) ; aucun push.
