# Changelog — Issue #330

## Lichess : vrai choix « aléatoire » envoyé à la recherche d'adversaire humain, orientation différée à la couleur réelle, explication du refus d'équilibre des couleurs

Essai réel d'Alain le 14/11/2026, après #329. Une recherche d'adversaire
humain en 15+10 avec les **blancs** a été refusée par Lichess (HTTP 400,
texte affiché tel quel par AlChess : « You must also play some games as
Black. ») — règle de Lichess qui impose d'équilibrer les couleurs quand un
compte demande toujours la même. Le choix « Aléatoire » de l'écran de
recherche était jusqu'ici tiré PAR AlChess avant la recherche (pile ou
face local, comme pour l'IA) : Lichess recevait donc toujours une couleur
précise, et refusait statistiquement la moitié du temps dès que le compte
était déjà déséquilibré.

**Règle absolue respectée à la lettre** : aucune recherche, aucune partie,
aucun défi réel sur lichess.org à aucun moment de ce travail. Le vrai
jeton d'Alain n'a jamais été lu ni utilisé — tous les tests utilisent des
doubles de client/transport scriptés, jamais une connexion réelle. Le
réseau n'a servi qu'à lire la documentation et le code source PUBLICS de
`lichess-org/api` et `lichess-org/lila` (`gh api`, lecture de fichiers
précis, jamais de recherche/partie). Le garde réseau de
`conftest.py::_guard_no_real_lichess_network` reste actif et inchangé.

### Point 1 — Vrai choix aléatoire envoyé à Lichess

- `core/game_manager_modes/lichess.py::_run_lichess_human` ne résout plus
  "aléatoire" localement (`random.choice` supprimé de cette fonction) :
  `requested_color` (ce qui part vers `board/seek`) vaut `""` pour
  "aléatoire", `"white"`/`"black"` inchangé pour un choix précis.
  `SeekSession.start()`/`GameClient.open_seek_stream()` (déjà prévus pour
  une couleur vide depuis #327, jamais exercés avec cette valeur jusqu'ici
  côté lanceur) omettent alors le paramètre `color` de la requête —
  Lichess choisit lui-même, conformément à sa documentation officielle
  (« Better left empty to automatically get 50% white »,
  `doc/specs/tags/board/api-board-seek.yaml`).
- La partie contre l'IA (`_run_lichess`/`launch_lichess`) garde son tirage
  local actuel (`random.choice`), explicitement inchangé — jamais concernée
  par la règle d'équilibre des couleurs (voir point 3).
- `display_color` (repli arbitraire `"white"` quand la couleur est vide)
  oriente l'écran de mise en place AVANT la recherche : la position de
  départ étant identique pour les deux camps, cet écran reste valable sans
  connaître la couleur réelle à l'avance.
- L'orientation RÉELLE (échiquier, noms, pendules) est appliquée au vrai
  début de partie, une fois la couleur confirmée par l'évènement
  `gameStart` de Lichess (`confirmed_color = found_game.get("color") or
  display_color`, inchangé dans son principe depuis #327) — transmise à
  `LichessGame(known_user_color=...)`, qui alimente `lichess_init` et donc
  `orientationIsFlipped()` côté `app.js` : code entièrement RÉUTILISÉ,
  aucune modification JS nécessaire pour ce point.
- `set_app_state("lichess_seeking", {"color": requested_color or
  "random"})` : le payload de l'écran de recherche porte désormais
  explicitement `"random"` plutôt qu'une couleur résolue à tort (sans
  effet visuel aujourd'hui, `app.js` ne lisant pas ce champ à cet écran).

### Point 2 — Explication en français (+ anglais/allemand) du refus d'équilibre

- Nouvelle fonction `modes/lichess/errors.py::detect_color_balance_refusal(message)` :
  reconnaît (indépendamment de la casse) le texte exact de Lichess « You
  must also play some games as White/Black » et retourne la couleur
  forcée, `""` sinon.
- `core/game_manager_modes/lichess.py::_classify_seek_error_event` : un
  refus HTTP 400 dont le texte correspond utilise désormais la clé
  `toast.lichess_refus_equilibre_couleur` (texte de Lichess + explication) ;
  tout autre refus 400 garde `toast.lichess_refus_requete` (texte de
  Lichess seul, comme avant #330).
- Nouvelle clé i18n `toast.lichess_refus_equilibre_couleur`, ajoutée
  simultanément dans `fr.json`/`en.json`/`de.json` et dans
  `state.py::_TOAST_MESSAGES` (repli français) : « Lichess a refusé la
  requête : {detail}. Lichess demande d'équilibrer les couleurs :
  choisissez l'autre couleur, ou « Aléatoire » pour quelques parties, puis
  réessayez. » (et ses équivalents anglais/allemand).

### Point 3 — Documentation : ce qui est établi, ce qui reste une hypothèse

Lu le 14/11/2026, dépôts publics `lichess-org/api` et `lichess-org/lila`
(`gh api`/`WebFetch`, jamais de connexion à un vrai compte/partie) :

**Établi par le code source de lila** (pas seulement une doc, le
comportement réel du serveur) :

- `doc/specs/tags/board/api-board-seek.yaml` + `ChallengeColor.yaml` :
  paramètre `color` de `POST /api/board/seek` accepte `white`/`black`/
  `random` ; laissé vide, Lichess applique le même équilibrage 50/50
  (« Better left empty to automatically get 50% white »).
- `app/controllers/Setup.scala::boardApiHook` : le refus HTTP 400 exact
  (`s"You must also play some games as $forced"`, texte sans ponctuation
  finale — celle observée par Alain vient de la mise en forme du toast
  AlChess, pas de Lichess) est posé par
  `env.lobby.boardApiHookStream.mustPlayAsColor(config.color)`.
- `modules/lobby/src/main/BoardApiHookStream.scala::mustPlayAsColor` :
  `(chosen != TriColor.Random).so: ...` — **la vérification est sautée
  entièrement si la couleur demandée est `Random`** ("aléatoire" envoyé
  tel quel à Lichess, jamais une couleur précise résolue localement,
  échappe donc TOUJOURS à ce refus). C'est la confirmation directe de
  l'hypothèse de départ de cette issue.
- `modules/user/src/main/UserRepo.scala::mustPlayAsColor`/`incColor` :
  compteur par utilisateur `colorIt`, borné à `[-3, 5]`. Seuil de refus :
  `colorIt > 2` → noir forcé ; `colorIt < -2` → blanc forcé (donc après 3
  parties nettes dans la même couleur sans l'autre). Incrémenté de +1 par
  partie jouée aux blancs, -1 aux noirs.
- `modules/lobby/src/main/Biter.scala::assignCreatorColor` : pour une
  couleur FIXE, seul le créateur de la recherche voit son `colorIt`
  incrémenté (`userApi.incColor(creator, fixed)`) — pour `Random`,
  `userApi.firstGetsWhite(creator, joiner)` choisit qui reçoit les blancs
  en comparant les deux `colorIt` (celui qui a le plus joué noir récemment
  reçoit blanc) et incrémente les DEUX compteurs en conséquence : un choix
  "aléatoire" contribue donc lui-même à RÉÉQUILIBRER le compte, jamais à
  le déséquilibrer.
- **Ce qui est compté** : uniquement les parties créées via le Lobby ou le
  Pool (`game.lobbyOrPool`, vérifié dans `AbortListener.scala`/
  `Rematcher.scala` — seuls appelants de `incColor` trouvés dans tout le
  dépôt avec les parties ci-dessus). **Aucun appel à `incColor` n'existe
  ailleurs dans le dépôt** (recherche exhaustive par `gh api search/code`) :
  les parties contre l'IA (`challenge/ai`, jamais via le Lobby) ne sont
  **jamais comptées** — confirme que la partie AlChess contre l'IA n'a
  jamais pu être concernée par cette règle, avec ou sans ce correctif.
  Rated et casual comptent tous les deux (`incColor` appelé indépendamment
  du drapeau `rated`, visible dans `Biter.scala::makeGame`).
- **Comment le compteur se rétablit** : chaque partie jouée dans la
  couleur opposée le fait revenir vers 0 ; `AbortListener.scala::onEarlyFinish`
  ANNULE l'incrément d'une partie qui se termine anormalement tôt (moins
  de coups qu'attendu, y compris un abandon) via
  `cancelBothColorIncrements` — une partie avortée ne compte donc pas pour
  l'équilibre.

**Reste une hypothèse** (comportement serveur non observable sans vraie
recherche, interdit par la règle de cette issue) :

- Que le code actuellement déployé sur lichess.org corresponde exactement
  à `master` du dépôt `lila` au moment de cette lecture (14/11/2026) — le
  dépôt est public et actif, mais aucune garantie de déploiement immédiat
  de chaque commit.
- Le délai exact ou le nombre de parties précis avant qu'un refus observé
  par Alain (3 blancs nets d'après le code) redevienne possible dans
  l'autre sens — dépend de l'historique réel (non consultable) du compte
  d'Alain.
- Que le champ `color` du `gameStart` (flux `/api/stream/event`) soit
  TOUJOURS présent en pratique pour une recherche "aléatoire" — la
  spécification officielle (`GameEventInfo.yaml`) ne le marque pas
  `required` (seuls `fullId`/`gameId` le sont), d'où le repli défensif
  conservé (`confirmed_color = found_game.get("color") or display_color`).

### Point 4 — Journal

- Déjà couvert par le code existant, désormais réellement exercé avec une
  couleur vide : `seek.py::SeekSession.start()` journalise « couleur=
  aléatoire » (au lieu d'une couleur précise) dès que `requested_color`
  est vide — sans aucune modification de `seek.py`.
- `_run_lichess_human` journalise la couleur réelle obtenue
  (`confirmed_color`) dans le message « recherche terminée — adversaire
  trouvé, game_id=…, couleur=… » (déjà existant depuis #327/#328,
  désormais correct pour "aléatoire" grâce à la couleur confirmée par
  Lichess plutôt qu'un tirage local).

### Point 5 — Tests sans aucune connexion réelle

Nouveau fichier `nicsoft/tests/test_issue330_lichess_random_color.py` (21
tests, tous verts), entièrement sans réseau (doubles de client/transport
scriptés des issues #309/#311/#327) :

- `detect_color_balance_refusal` : reconnaît « You must also play some
  games as Black/White » (casse/ponctuation variables), rejette un autre
  texte.
- `_classify_seek_error_event` : clé dédiée + texte de Lichess conservé
  pour le refus d'équilibre ; clé inchangée pour un autre refus 400 ; la
  clé dédiée existe et diffère de `toast.lichess_refus_requete` dans les
  3 langues.
- Recherche "aléatoire" : `open_seek_stream` reçoit une couleur vide
  (jamais `white`/`black` résolu), `random.choice` n'est jamais appelé
  pendant la recherche humaine (assertion qui lève si appelé) ; l'écran de
  mise en place reste affiché avec une couleur arbitraire ; couleur
  confirmée par `gameStart` (les deux cas, blanc et noir) atteint
  correctement `LichessGame(known_user_color=...)` ; journal de recherche
  portant bien « couleur=aléatoire » puis la couleur réelle obtenue.
- Recherche à couleur précise (blancs/noirs) : `open_seek_stream` reçoit
  exactement la couleur demandée — aucune régression.
- `GameClient.open_seek_stream` seul (sans lanceur) : paramètre `color`
  absent de la requête HTTP quand la couleur est vide, présent et correct
  sinon.
- Partie contre l'IA : `launch_lichess` continue d'appeler `random.choice`
  pour "aléatoire" — confirmé inchangé.

**Suites complètes exécutées** :
- `python3 -m pytest nicsoft/tests --ignore=nicsoft/tests/e2e` →
  **1110 passed, 82 skipped** (aucun échec, aucune régression).
- `python3 -m pytest nicsoft/tests/e2e -k lichess` (dossier de navigateur,
  Playwright + serveur réel en sous-processus, `ALCHESS_SKIP_BOARD=1
  ALCHESS_NO_BROWSER=1`, jeton toujours vide dans l'`ALCHESS_DIR` isolé de
  session) → **63 passed** — ces tests exercent déjà `lichess_init` avec
  les deux couleurs (chemin partagé IA/humain, non modifié par cette
  issue), ce qui couvre l'orientation réelle de bout en bout en navigateur.
  Aucun nouveau scénario Playwright dédié à cette issue n'a été ajouté : le
  seul code touché côté navigateur est zéro (aucun fichier JS/HTML modifié),
  et la fonction d'orientation elle-même est déjà couverte par
  `test_issue315_lichess_orientation.py` (extraction + exécution réelle via
  `node`).

### Non vérifiable sans vraie partie (interdit par la règle de cette issue)

- Que le refus réel observé par Alain le 14/11/2026 ne se reproduirait
  plus avec "Aléatoire" sur le vrai compte — découle du code source lu
  (point 3), jamais réessayé en vrai.
- Le comportement exact de lichess.org si son code déployé diverge de
  `lila` `master` au moment de cette lecture.

### Fichiers modifiés

`nicsoft/core/game_manager_modes/lichess.py` (résolution de couleur de
`_run_lichess_human`, `_classify_seek_error_event`, import) ;
`nicsoft/core/game_manager_modes/state.py` (nouvelle clé de repli) ;
`nicsoft/modes/lichess/errors.py` (nouvelle fonction
`detect_color_balance_refusal`) ; `nicsoft/web/static/i18n/{fr,en,de}.json`
(nouvelle clé) ; `nicsoft/tests/test_issue330_lichess_random_color.py`
(nouveau) ; `CONTEXTE.md` (paragraphe Lichess humain #327 corrigé).
Aucune modification de `driver.py`, d'aucun moteur, d'`.audit.json` ni des
dépendances ; aucun arrêt de processus par nom ; aucun push.
