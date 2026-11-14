# Changelog — Issue #328

## Lichess humain : adversaire trouvé retrouvé après fermeture de la recherche, fermeture ordonnée des flux, compteur de temps corrigé

Essai réel du 14/11/2026 (recherche d'adversaire humain, 10+0, blancs) :
un adversaire avait bien été apparié chez Lichess (partie terminée
manuellement sur lichess.org par Alain) alors qu'AlChess concluait à tort
à un échec réseau, perdait la trace de la partie, et levait une exception
non interceptée dans un fil secondaire. Cette issue corrige la cause et
ajoute les garde-fous demandés.

**Règle absolue respectée à la lettre** : aucune recherche d'adversaire,
aucune partie, aucun défi réel sur lichess.org à aucun moment. Le jeton
réel d'Alain n'a jamais été lu ni utilisé. Tous les tests utilisent soit
un transport scripté (`FakeTransport`/`_FakeHandleForClient`), soit un
serveur HTTP local (127.0.0.1, jamais lichess.org) — jamais de connexion
réelle. Le test de garde réseau de #327 reste actif et inchangé.

### Point 1 — Cause établie par lecture du code et de la documentation

- Établi par lecture du code (fait, pas une hypothèse) : `seek.py`
  traitait la fermeture du flux `board/seek` (`seek_closed`) comme un
  échec immédiat. Le lanceur (`_run_lichess_human`) réagissait en
  appelant `seek_session.cancel()`, qui fermait aussitôt le flux général
  d'évènements (`/api/stream/event`) — alors que son propre fil de
  lecture (`_read_event_stream`) pouvait être encore bloqué en train
  d'attendre la ligne suivante, dans l'espoir de lire `gameStart`.
  Fermer une connexion HTTP depuis un AUTRE fil pendant une lecture
  bloquante lève une exception dont le type exact dépend du point
  précis de l'interruption et de la version de Python
  (`ValueError` déjà observé par le passé, `AttributeError` observé
  cette fois : `'NoneType' object has no attribute 'peek'`) —
  `transport.py::StreamHandle.lines()` n'interceptait QUE `ValueError`,
  jamais les autres cas : l'exception remontait non interceptée hors du
  générateur, hors de `_read_event_stream` (qui n'attrapait que
  `TransportNetworkError`/`TransportTimeoutError`), jusqu'au hook
  d'exception par défaut des fils — visible UNIQUEMENT dans le
  terminal, jamais journalisée (ni `niclink.log`, ni le journal dédié de
  la recherche).
- Reste une hypothèse (non vérifiable sans vraie partie, interdit par
  consigne) : l'ORDRE et le DÉLAI réels, côté Lichess, entre la fermeture
  de `board/seek` (appariement) et l'arrivée de `gameStart` sur
  `/api/stream/event`. La documentation officielle lichess-org/api
  (`doc/specs/tags/board/api-board-seek.yaml`, `api-stream-event.yaml`,
  relues le 14/11/2026) ne garantit ni l'un ni l'autre. L'essai réel du
  14/11/2026 est cohérent avec « `board/seek` se ferme avant que
  `gameStart` ne soit lu par AlChess » (aucune ligne « partie créée »
  dans le journal, alors qu'une partie existait bien) — mais rien ne
  prouve si `gameStart` est arrivé juste après (et a été perdu par la
  fermeture prématurée du flux) ou plus tard. La correction ci-dessous
  est robuste dans les deux cas : elle ne ferme plus jamais le flux
  d'évènements tant que l'appelant n'a pas renoncé à attendre.

### Point 2 — Ne plus jamais conclure à un échec dès `seek_closed`

- `nicsoft/modes/lichess/seek.py` : `_read_seek_stream` ne change pas de
  comportement côté détection (toujours `seek_closed` si ni annulée ni
  trouvée), mais **ne ferme jamais** le flux d'évènements — c'était déjà
  le cas, le bug venait de l'appelant.
- `nicsoft/core/game_manager_modes/lichess.py::_run_lichess_human` :
  sur `seek_closed`, nouvelle attente `_SEEK_CLOSED_GRACE_S` (5s) de
  l'évènement `found` (en continuant à lire la file d'évènements de la
  session, sans fermer quoi que ce soit). Si `gameStart` arrive dans ce
  délai : la recherche se termine normalement, comme si `seek_closed`
  n'avait jamais eu lieu. Sinon : appel à `_fetch_ongoing_games` (même
  fonction que le garde-fou « une seule partie à la fois », déjà
  existant) — une partie en temps réel trouvée y est **adoptée** :
  évènement `lichess_resumable` envoyé au navigateur (réaffiche l'écran
  des parties en cours de #325, avec son bouton « Abandonner » puisque
  la reprise d'une partie humaine n'est pas encore livrée — fera l'objet
  d'une issue suivante, non tentée ici) et toast dédié
  `toast.lichess_seek_partie_non_ouverte` (« Un adversaire a été trouvé,
  mais la partie n'a pas pu s'ouvrir normalement »). Une annulation
  utilisateur reçue PENDANT cette courte attente ne fait pas non plus
  perdre une partie déjà créée : la liste des parties en cours est quand
  même consultée avant de conclure (comportement voulu, non couvert par
  un test automatique dédié — fragile à reproduire de façon
  déterministe avec des doubles sans délai réel, voir rapport de
  clôture).

### Point 3 — Message distinct si vraiment aucune partie

- Nouveau toast `toast.lichess_seek_sans_adversaire` (« La recherche
  s'est arrêtée sans adversaire. ») — utilisé uniquement quand la liste
  des parties en cours confirme qu'aucune partie n'a été créée. Le
  toast `toast.lichess_network_error` (« Connexion à Lichess impossible
  — vérifiez le réseau. ») reste réservé à une vraie panne réseau
  (échec d'ouverture d'un flux, coupure en cours de lecture) — jamais
  utilisé pour `seek_closed`.

### Point 4 — Annulation et fermeture ordonnées

- `nicsoft/modes/lichess/transport.py::StreamHandle.lines()` : toute
  exception levée pendant l'itération est désormais traitée comme une
  fin normale du générateur SI `self._closed` est déjà vrai (fermeture
  volontaire en cours depuis un autre fil — `close()` positionne ce
  drapeau AVANT de fermer la réponse) ; sinon elle est relevée telle
  quelle (jamais avalée en silence si ce n'est pas une fermeture
  volontaire).
- `nicsoft/modes/lichess/seek.py` : `_read_event_stream`/
  `_read_seek_stream` encapsulent désormais tout leur corps dans un
  `except Exception` qui journalise systématiquement (`logger.error` +
  `GameLog.exception(exc, context=...)`, jamais seulement le terminal)
  et pousse un évènement `error` à l'appelant si la session n'est pas
  déjà résolue — même traitement que `LichessGame._stream_reader_loop`
  (#326, `game.py`), qui n'avait jamais été étendu à ce module.
- `SeekSession.cancel()` (annulation utilisateur explicite, bouton
  « Annuler la recherche ») et la nouvelle `SeekSession.close()` (toute
  autre conclusion — trouvé, erreur, décision après l'attente de
  `seek_closed`) sont maintenant deux méthodes distinctes : seule
  `cancel()` journalise « recherche d'adversaire annulée par
  l'utilisateur » ; `close()` ne le fait pas (le journal avait
  auparavant ce message FAUX dans tous les autres cas — exactement ce
  qu'on a vu dans l'essai réel du 14/11/2026, « recherche annulée par
  l'utilisateur » alors qu'Alain n'avait rien cliqué). Le lanceur
  (`_run_lichess_human`, bloc `finally`) appelle désormais `close()`
  plutôt que `cancel()`.
- Petit raffinement de robustesse (défense en profondeur, pas un bug
  confirmé) : `_read_seek_stream` relit `_cancelled`/`_found` sous le
  même verrou que `_mark_found` juste avant de pousser `seek_closed`,
  pour réduire la fenêtre d'une fausse notification en cas de
  coïncidence de minutage exacte entre les deux fils.

### Point 5 — Compteur de temps écoulé

- `nicsoft/core/game_manager_modes/lichess.py::_run_lichess_human` :
  `search_start` est désormais capturé immédiatement après la
  confirmation de la position physique, AVANT le garde-fou « une seule
  partie à la fois » et avant l'ouverture des deux flux
  (`seek_session.start()`) — trois appels HTTP séquentiels bloquants
  dont la durée n'était pas comptée auparavant (le compteur ne démarrait
  qu'après leur retour). Cause probable (établie par lecture du code,
  cohérente avec l'écart observé — « 0:03 » affiché neuf secondes après
  la position confirmée) de l'écart signalé dans l'essai réel.

### Point 6 — Journal de partie

- `nicsoft/modes/lichess/seek.py::_read_event_stream` : chaque ligne non
  vide reçue sur le flux d'évènements pendant la recherche est
  désormais journalisée via `GameLog.raw()` (jamais de tchat possible à
  ce stade, aucune partie n'existant encore).
- `_run_lichess_human` journalise désormais, via `GameLog.state_change`,
  chaque étape de la nouvelle logique : fermeture de `board/seek`
  signalée, attente de `gameStart`, consultation de la liste des
  parties en cours, et la décision finale prise (trouvée / adoptée /
  aucune partie).

### Point 7 — Tests (sans aucune connexion réelle)

Nouveau fichier `nicsoft/tests/test_issue328_lichess_seek_recovery.py` :

- **Fermeture pendant une lecture bloquante, sans trace d'erreur** :
  serveur HTTP local (127.0.0.1, jamais lichess.org) + vrai socket +
  vrai fil de lecture ; `close()` appelé depuis le fil de test pendant
  que le fil de lecture est bloqué sur la ligne suivante ; capture du
  hook d'exception des fils (`threading.excepthook`) pour prouver
  qu'aucune exception ne s'en échappe (reproduction directe du bug réel).
- **`found` arrivant après `seek_closed`** (le flux de recherche se
  ferme avant que `gameStart` n'arrive) : double à délai réel
  (`time.sleep`) pour forcer cet ordre de façon déterministe — les
  doubles purement synchrones ne garantissent aucun ordre entre les deux
  fils. Caractérise le mécanisme exact sur lequel repose la correction.
- **Exception imprévue d'un fil secondaire** : double dont `lines()`
  lève directement une `AttributeError`, vérifie la journalisation
  (`caplog` + fichier dédié) et l'évènement `error` poussé à l'appelant.
- **`cancel()` vs `close()`** : seul `cancel()` journalise « annulée par
  l'utilisateur ».
- **Lanceur `_run_lichess_human`** : `seek_closed` puis `gameStart`
  pendant l'attente → partie rejointe normalement ; `seek_closed` sans
  `gameStart` mais partie présente dans la liste des parties en cours →
  adoptée (évènement `lichess_resumable` + toast dédié) ; `seek_closed`
  sans `gameStart` et sans aucune partie → message distinct ; messages
  toast réseau / sans-adversaire / partie-non-ouverte vérifiés distincts
  textuellement ; compteur de temps vérifié en rendant le garde-fou
  réseau artificiellement lent et en contrôlant que le premier
  `lichess_seek_tick` en tient compte.
- **Non ajouté** : un test automatique de l'annulation utilisateur
  PENDANT la courte fenêtre d'attente qui suit `seek_closed` (voir point
  2) — timing trop fragile à reproduire de façon déterministe avec des
  doubles sans délai réel ; le comportement général d'annulation (hors
  de cette fenêtre) reste couvert par le test existant de #327
  (`test_lanceur_humain_annulation_recherche_sur_back_menu`), toujours
  vert, inchangé.
- Le test de garde réseau de #327
  (`conftest.py::_guard_no_real_lichess_network`) reste actif, inchangé,
  et a été revérifié : toujours vert.

### Non vérifié sans vraie partie (interdit par consigne)

- L'ordre et le délai réels, côté Lichess, entre la fermeture de
  `board/seek` et l'arrivée de `gameStart` (voir point 1) — reste une
  hypothèse ; la correction est conçue pour être correcte dans les deux
  ordres possibles.
- Le rendu réel de l'écran des parties en cours (#325) dans le cas
  « adopté » avec une vraie réponse Lichess (`get_ongoing_games`) — testé
  uniquement avec une liste construite à la main côté test.

### Fichiers modifiés

- `nicsoft/modes/lichess/transport.py` — `StreamHandle.lines()`.
- `nicsoft/modes/lichess/seek.py` — journalisation des lignes brutes,
  encapsulation `except Exception` des deux fils, `cancel()`/`close()`.
- `nicsoft/core/game_manager_modes/lichess.py` — `_SEEK_CLOSED_GRACE_S`,
  attente + adoption sur `seek_closed`, `search_start` déplacé,
  `finally` utilise `close()`.
- `nicsoft/core/game_manager_modes/state.py` — deux nouveaux messages
  toast (`_TOAST_MESSAGES`).
- `nicsoft/web/static/i18n/fr.json`/`en.json`/`de.json` — deux nouvelles
  clés (`toast.lichess_seek_sans_adversaire`,
  `toast.lichess_seek_partie_non_ouverte`), ajoutées simultanément dans
  les trois langues.
- `nicsoft/tests/test_issue328_lichess_seek_recovery.py` (nouveau).
- `CONTEXTE.md` — paragraphe dédié ajouté à la suite de celui de #327.
