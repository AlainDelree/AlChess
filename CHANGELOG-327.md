# Changelog — Issue #327

## Lichess humain : recherche d'adversaire, choix IA/humain, événements de base, nulle vs IA établie, journal moins bruyant

Issue lourde (L2b) — livraison complète des points 1 à 8 en un seul passage
(recherche documentaire + lecture du code public de lila en amont a permis
de trancher plusieurs points qui auraient sinon demandé un second passage,
voir « Points vérifiés par lecture de code » plus bas).

**Règle absolue respectée à la lettre** : aucune recherche d'adversaire,
aucune partie, aucun défi réel sur lichess.org à aucun moment. Tous les
tests utilisent un transport scripté (`FakeTransport`/`FakeStreamHandle`,
jamais de socket réel) ; un garde-fou réseau dédié a été ajouté (point 8).

### Point 1 — Choix du type de partie

- `nicsoft/web/templates/index.html` (`screen-config-lichess`) : nouvelle
  carte « Adversaire » avec deux boutons (`cfg-lichess-opponent-ai`/
  `-human`). Contre un humain : le niveau d'IA est masqué (sans objet), un
  rappel « amicale seulement, classé plus tard » apparaît. Les préréglages
  de cadence existants (10+0/15+10/30+0/60+0/90+30) sont réutilisés tels
  quels pour les deux modes — tous Rapide ou Classique, jamais Blitz/Bullet
  (vérifié via `speed_key_for_clock`, déjà présente depuis #321).
- `app.js` : `selectOpponentTypeLichess()` (nouveau), `startGameLichess()`
  envoie désormais `opponent_type` au serveur.
- i18n : 11 nouvelles clés ajoutées simultanément dans `fr.json`/`en.json`/
  `de.json` (voir liste en fin de fichier).

### Point 2 — Ordre des opérations

- `core/game_manager_modes/lichess.py::launch_lichess()` distingue
  `opponent_type` et délègue à `_launch_lichess_human()`/
  `_run_lichess_human()` (nouveaux) pour le cas humain — le cas IA
  (`_run_lichess`) est inchangé.
- Même ordre que pour l'IA (#311) : position physique confirmée
  (`_wait_initial_position_lichess`, réutilisée telle quelle) **avant**
  tout appel réseau ; garde-fou « une seule partie à la fois »
  (`_refuse_create_if_games_ongoing`, réutilisé) appliqué **juste avant**
  la recherche, jamais avant la position.
- Contrairement à l'IA, la couleur « aléatoire » est résolue LOCALEMENT
  (comme pour l'IA, `random.choice`) et transmise explicitement au
  paramètre `color` du `board/seek` — plutôt que de laisser Lichess décider
  server-side (ce que l'API permettrait) : évite une ambiguïté d'orientation
  de l'écran de mise en place tant que la couleur resterait inconnue,
  pour un résultat statistiquement identique (50/50).

### Point 3 — Recherche

- **Nouveau module `nicsoft/modes/lichess/seek.py`** (`SeekSession`) :
  implémente le protocole officiel `board/seek` (doc `lichess-org/api`,
  `doc/specs/tags/board/api-board-seek.yaml`, lue le 14/11/2026 via
  `gh api`) — `POST /api/board/seek` reste ouvert (lignes vides
  périodiques) tant que la recherche est active ; **fermer cette connexion
  est le seul moyen d'annuler la recherche côté serveur** (« If the client
  closes the connection, the seek is canceled »). Le flux de recherche ne
  contient aucune information sur la partie trouvée : `GET
  /api/stream/event` est ouvert EN PREMIER (recommandation officielle,
  « We recommend opening the Event stream first ») pour recevoir
  l'évènement `gameStart` (game_id, couleur, adversaire) dès l'appariement.
- **`nicsoft/modes/lichess/transport.py`** : nouvelle méthode
  `UrllibTransport.open_stream()` + classe `StreamHandle` — poignée
  annulable (`.close()` ferme le socket depuis un AUTRE fil que celui qui
  lit `.lines()`), nécessaire car `stream_lines()` existant (générateur à
  bloc `with` interne) n'exposait pas la réponse pour une fermeture externe.
- **`nicsoft/modes/lichess/game_client.py`** : `open_event_stream()`/
  `open_seek_stream()` (nouvelles) — ne traduisent PAS les erreurs de
  transport en erreurs Lichess (contrairement aux autres méthodes) :
  `seek.py` les attrape sous leur forme brute (`TransportNetworkError`
  etc.), documenté dans les deux modules.
- Écran dédié `screen-lichess-seeking` (état `lichess_seeking`, ajouté à
  `single_instance.BUSY_STATES`) : temps écoulé poussé par le serveur
  (`lichess_seek_tick`, ~1×/s, jamais un minuteur JS local), bouton
  « Annuler la recherche » = `back_menu` (même mécanisme que l'écran
  `position_initiale` : jamais relayé à `action_queue`, voir
  `server.py::on_action` — jamais eu besoin d'y toucher). Panne réseau,
  jeton absent ou refus Lichess : retour à `config_lichess` avec message
  persistant (`toast_message_key`), jamais de blocage silencieux. Aucune
  limite de durée imposée côté AlChess (conforme à la demande).

### Point 4 — Partie contre un humain

- Le mode jouable existant (`modes/lichess/game.py::LichessGame`) est
  réutilisé À L'IDENTIQUE pour la partie elle-même — la plupart du
  nécessaire (pendules figées avant les deux premiers coups, estimation
  locale du décompte du premier coup pour un adversaire non-IA, aucune
  limite de réflexion) était déjà en place depuis #321/#322, puisque conçu
  dès le départ pour anticiper ce mode.
- **Nouveau paramètre `known_user_color`** (`LichessGame.__init__`) :
  nécessaire car, pour une partie humaine, ni `white` ni `black` ne porte
  jamais `aiLevel` dans `gameFull` — jusqu'ici le SEUL moyen utilisé par
  `_apply_game_full()` pour déduire sa propre couleur. Transmis par le
  lanceur depuis la couleur résolue localement avant la recherche (point 2).
- **Nom et cote de l'adversaire** : `LichessGame.opponent_name`/
  `opponent_rating` (nouveaux), déduits de `white`/`black` dans
  `_apply_game_full()`, transmis dans l'évènement `lichess_init` existant
  (`opponent_name`, `opponent_rating`, `opponent_is_ai`). Affichés côté
  `app.js` via `.textContent` (jamais `innerHTML`) — suffisant à lui seul
  contre l'injection, comme tout le reste de l'interface pour du texte
  Lichess (nom Lichess potentiellement arbitraire).

### Point 5 — Événements de base (nulle)

- **Établi par lecture du code public de lila (14/11/2026, dépôt
  `lichess-org/lila`, branche par défaut)**, répondant précisément à
  l'observation d'Alain du 14 novembre (icône ½ grisée en permanence
  contre l'IA sur lichess.org) :
  - `modules/game/src/main/Game.scala::playerCanOfferDraw` exige
    `!g.opponent(color).isAi` parmi ses conditions.
  - `modules/round/src/main/Drawer.scala::yes()` : si cette condition est
    fausse, retombe sur `case _ => fuccess(List(Event.ReloadOwner))` — un
    **no-op silencieux, sans erreur, qui ne modifie jamais `isOfferingDraw`**.
  - `modules/bot/src/main/BotJsonView.scala::gameState` : `wdraw`/`bdraw`
    sont lus directement depuis `game.whitePlayer.isOfferingDraw`/
    `blackPlayer.isOfferingDraw` — jamais modifiés contre l'IA, donc jamais
    vrais dans aucun état reçu.
  - **Conclusion établie, pas une hypothèse** : contre l'IA, une offre de
    nulle n'a STRICTEMENT AUCUN EFFET, quelle que soit la requête envoyée
    (200 OK renvoyé par Lichess malgré tout — d'où la fausse impression
    d'une demande « acceptée » alors que rien ne se passe réellement).
  - **Corrigé dans `game.py`** : `_compute_action_buttons()` — Proposer
    nulle grisé EN PERMANENCE contre l'IA (`not self._opponent_is_ai`
    ajouté à `draw_enabled`), pas seulement pendant l'attente habituelle.
    `_process_browser_actions()` — l'action `lichess_propose_draw`
    n'envoie même plus la requête contre l'IA (défense en profondeur,
    toast `lichess.nulle_impossible_ia` à la place). Nouveau champ
    `draw_disabled_vs_ai` dans l'évènement `lichess_action_buttons`, lu par
    `app.js::_lichessSetActionButtons()` pour afficher l'explication courte
    à la place du texte habituel. Conséquence directe : « Nulle refusée »
    ne peut plus jamais s'afficher contre l'IA (plus aucune offre n'est
    jamais réellement en attente).
  - Même lecture de code, pour la question du renvoi : `playerCanOfferDraw`
    exige aussi `!g.player(color).isOfferingDraw` (pas déjà en train
    d'offrir) — **renvoyer une offre déjà active retombe sur le MÊME no-op
    `ReloadOwner`, jamais une erreur ni un second effet réel** : confirmé
    sans risque d'établir ceci par la lecture seule (pas besoin d'une
    vraie partie).
- **Renvoi unique contre un humain** (`_apply_game_state()`,
  `_my_draw_offer_resent`, nouveau) : si l'état reçu juste après NOTRE
  propre coup (offre jointe via `offeringDraw=true`) ne montre toujours pas
  notre indicateur, renvoi d'une nouvelle requête `draw/yes` UNE SEULE FOIS
  (jamais en boucle), journalisé. Repose sur la garantie ci-dessus (sans
  risque même si l'offre était déjà bien passée). **Non vérifiable sans une
  vraie partie contre un humain** (interdit par cette issue) : en pratique,
  l'ordre des opérations dans `BotPlayer.scala` (le drapeau est positionné
  AVANT l'envoi du coup à la même file d'acteur) suggère que l'indicateur
  devrait déjà être présent dès l'écho du coup dans la quasi-totalité des
  cas — le renvoi n'est qu'un filet de sécurité, pas une correction d'un
  bug confirmé.

### Point 6 — PGN et journal

- **PGN** : `build_pgn_headers()` accepte `opponent_name=`/`event_label=`
  (nouveaux paramètres optionnels, rétro-compatibles — l'ancien
  comportement, nom d'IA par défaut, reste inchangé sans eux).
  `LichessGame._save_pgn()` les fournit pour un adversaire humain (vrai nom
  Lichess, `"Lichess, amicale contre un humain"`), jamais pour l'IA.
- **Journal — bruit des pendules réduit** : `LichessGame._maybe_log_clock()`
  (nouveau) — les lignes `[CLOCK]` du journal DÉDIÉ (pas l'envoi au
  navigateur via `lichess_clock`, inchangé à 1×/s) ne s'écrivent plus qu'au
  recalage reçu de Lichess (`force=True`, `_reset_clock_from_state`), au
  changement de trait ou de source depuis la dernière ligne écrite, ou au
  plus une fois toutes les 30s (`CLOCK_LOG_MIN_INTERVAL_S`) — reproduit
  exactement la plainte de l'essai d'Alain (une ligne par seconde aurait
  noyé une partie de 90+30). Valeurs arrondies à la milliseconde entière
  (`round()`) avant écriture.
- **Décisions de nulle journalisées dans le journal DÉDIÉ** (pas seulement
  le journal général comme avant #327) : offre envoyée (avec raison),
  jointe au coup, acceptée (par nous ou l'adversaire), refusée (par nous ou
  l'adversaire), renvoyée — chacune via `self._game_log.state_change(...)`
  en plus du `logger.info` existant.
- **Indicateurs de nulle journalisés à CHAQUE état reçu** (sans throttle,
  contrairement aux pendules) : `_log_game_state_received()` écrit
  désormais aussi dans le journal dédié la présence/absence de `wdraw`/
  `bdraw` à chaque `gameFull`/`gameState` — c'est précisément ce
  qu'Alain avait dû aller chercher dans le journal GÉNÉRAL le 14/11/2026,
  faute de l'avoir dans le journal dédié de la partie concernée.
- Jeton et tchat : toujours jamais journalisés (comportement de #326
  inchangé, `GameLog` non modifié sur ce point).

### Point 7 — Fair-play

- Aucun import de moteur ni d'aide introduit par cette issue — `seek.py`
  et les ajouts à `game.py`/`game_manager_modes/lichess.py` n'importent
  que `nicsoft.modes.lichess.*`, `chess`, et la bibliothèque standard.
  Non ajouté : un test dédié « le mode Lichess ne démarre aucun moteur » —
  un tel test générique n'existait pas avant cette issue (à vérifier/ajouter
  dans une issue de suivi si souhaité) ; `test_no_web_import.py` (ARC-001)
  couvre déjà l'absence d'import de `nicsoft.web` mais pas spécifiquement
  l'absence d'import moteur.

### Point 8 — Tests sans connexion réelle

- **`FakeTransport`/`FakeStreamHandle`** (`test_issue309_lichess_l2a.py`,
  étendu) : nouvelle méthode `open_stream()` sur le double partagé —
  consomme des spécifications scriptées (listes de lignes ou exceptions),
  additif et rétro-compatible (aucun test existant n'appelait cette
  méthode avant).
- **Nouveau fichier `nicsoft/tests/test_issue327_lichess_human.py`**
  (29 tests) : `SeekSession` (appariement, annulation réelle des deux
  flux, échec d'ouverture, coupure en cours, journal dédié de recherche),
  cadences acceptées (tous les préréglages vérifiés Rapide/Classique),
  lanceur `_run_lichess_human` (position avant recherche, garde-fou partie
  en cours AVANT la recherche, annulation par `back_menu`, erreur réseau,
  cadence invalide — filet de sécurité), nulle grisée en permanence contre
  l'IA (bouton ET requête jamais envoyée), renvoi unique contre un humain,
  nom/cote de l'adversaire transmis, PGN avec nom humain, bruit des
  pendules réduit (pas de nouvelle ligne sans changement), arrondi
  milliseconde, indicateurs de nulle journalisés à chaque état.
- **Garde-fou réseau dédié (nouveau, demandé explicitement par le point
  8)** : `nicsoft/tests/conftest.py::_guard_no_real_lichess_network`
  (fixture `autouse`) — patch `socket.create_connection` (point
  d'interception vérifié correct : `http.client.HTTPConnection.__init__`
  capture cette fonction comme attribut D'INSTANCE au moment de la
  construction, donc patcher l'attribut du module AVANT toute connexion
  suffit — vérifié avec une vraie tentative de connexion à
  `lichess.org:443`, ce bac à sable ayant un accès réseau sortant). Échoue
  avec un message explicite si un hôte contenant « lichess » est contacté
  pendant la suite EN PROCESS. Couvre `nicsoft/tests` (hors `e2e`, qui
  lance un sous-processus séparé — protégé par construction depuis #326 :
  jeton toujours vide dans son `ALCHESS_DIR` isolé, donc aucun appel réseau
  n'est même tenté). Deux tests dédiés dans `test_issue327_lichess_human.py`
  vérifient explicitement la garde (bloque un hôte Lichess, laisse passer
  un autre hôte).
- **Existant retesté** : correctifs du point 5 ont nécessité la mise à
  jour de 13 tests préexistants (#310/#311/#316/#318/#321/#323) qui
  simulaient un adversaire IA tout en attendant un bouton Proposer nulle
  actif — converti en adversaire humain simulé (`known_user_color` +
  dictionnaires sans `aiLevel`) pour continuer à tester la même logique de
  nulle, désormais correctement réservée à un adversaire humain ; deux
  assertions de dictionnaire exact mises à jour pour inclure le nouveau
  champ `draw_disabled_vs_ai` ; fixtures e2e `lichess_init` mises à jour
  avec `opponent_is_ai: true` (contrat de payload étendu par le point 4).
- **Suite complète** : 1144 tests passent (83 ignorés, matériel), suite e2e
  Lichess (63 tests) et suite e2e complète (109 tests) vertes après tous
  les changements, y compris les ajustements CSS de l'écran de recherche.

### Fichiers modifiés/créés

- Nouveaux : `nicsoft/modes/lichess/seek.py`,
  `nicsoft/tests/test_issue327_lichess_human.py`.
- Modifiés : `nicsoft/modes/lichess/transport.py` (StreamHandle/
  open_stream), `nicsoft/modes/lichess/game_client.py`
  (open_event_stream/open_seek_stream), `nicsoft/modes/lichess/game.py`
  (known_user_color, opponent_name/rating, nulle vs IA, renvoi unique,
  bruit journal, build_pgn_headers), `nicsoft/core/game_manager_modes/
  lichess.py` (launch_lichess dispatch, _launch_lichess_human/
  _run_lichess_human), `nicsoft/web/single_instance.py` (BUSY_STATES),
  `nicsoft/web/templates/index.html` (choix adversaire, écran recherche),
  `nicsoft/web/static/app.js` (sélection adversaire, écran recherche,
  nom/cote adversaire, explication nulle grisée), `nicsoft/web/static/
  i18n/{fr,en,de}.json` (11 nouvelles clés), `nicsoft/tests/conftest.py`
  (garde réseau), `nicsoft/tests/test_issue309_lichess_l2a.py`
  (FakeStreamHandle/open_stream, forward kwargs), 6 fichiers de tests
  préexistants ajustés (voir ci-dessus), `nicsoft/tests/e2e/
  test_issue310_lichess_e2e.py` (contrat `opponent_is_ai`).

### Ce qui n'a pas pu être vérifié sans une vraie partie (interdit par cette issue)

- Rendu réel de `wdraw`/`bdraw` juste après notre coup contre un adversaire
  HUMAIN réel (la lecture du code suggère qu'il devrait déjà être présent,
  mais seule une vraie partie le confirmerait — le renvoi unique reste un
  filet de sécurité, jamais testé en situation réelle).
- Comportement exact de Lichess si une recherche expire sans appariement
  (aucune durée maximale documentée dans la spec officielle) — traité par
  prudence (`seek_closed`), jamais observé.
- Message exact affiché par lichess.org dans ce cas, et tout comportement
  dépendant du vrai matchmaking (temps d'attente réel, clients concurrents).

### Nouvelles clés i18n (fr/en/de)

`config.h2.adversaire`, `config.lichess.adversaire_ia`,
`config.lichess.adversaire_humain`, `config.lichess.rated_plus_tard`,
`lichess.recherche.titre`, `lichess.recherche.temps_ecoule`,
`lichess.recherche.explication`, `lichess.recherche.annuler`,
`lichess.nulle_impossible_ia`, `lichess.adversaire_inconnu`,
`toast.lichess_cadence_invalide`.
