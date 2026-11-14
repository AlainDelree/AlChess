# Changelog — Issue #329

## Lichess : erreur HTTP exacte journalisée et affichée à l'ouverture de la recherche d'adversaire

Essais réels d'Alain le 14/11/2026 : une recherche d'adversaire humain en
15+10 (blancs) échouait dès l'ouverture, deux fois de suite, avec l'écran
affichant « Connexion à Lichess impossible — vérifiez le réseau » alors
que le réseau et le jeton fonctionnaient (une partie contre l'IA avait
réussi quelques minutes plus tôt, et une recherche 10+0 avait réussi un
peu plus tôt dans la session). Le journal ne portait que
« TransportHTTPError », sans le code de réponse HTTP ni le corps renvoyé
par Lichess (qui explique la cause du refus) : la cause réelle restait
invisible.

**Règle absolue respectée à la lettre** : aucune recherche, aucune partie,
aucun défi réel sur lichess.org à aucun moment de ce travail. Le vrai
jeton d'Alain n'a jamais été lu ni utilisé — tous les tests utilisent un
transport scripté (`FakeTransport`) ou `urllib.request.urlopen` remplacé
par monkeypatch, jamais une connexion réelle. Le garde réseau de
`conftest.py::_guard_no_real_lichess_network` reste actif et inchangé.

### Point 1 — Journalisation de toute erreur HTTP Lichess

- `transport.py::UrllibTransport` journalise désormais, pour TOUS ses
  appels (`request`, `stream_lines`, `open_stream` — la recherche
  d'adversaire comme les autres), une ligne dans le journal général
  (`niclink.lichess`) à chaque réponse d'erreur HTTP : méthode + chemin
  (sans paramètres), code de réponse, en-tête `Retry-After` s'il existe,
  corps de la réponse tronqué à ~500 caractères. Jamais le jeton (absent
  de la méthode, du chemin et du corps — il n'est envoyé que dans
  l'en-tête `Authorization`, jamais journalisé).
- `TransportHTTPError` porte désormais un attribut `retry_after_s` (`int`
  ou `None`), lu depuis l'en-tête `Retry-After` de la réponse.
- `game_client.py::GameClient` écrit le même détail (tronqué) dans le
  journal de partie dédié (`GameLog`, catégorie `REQUEST`), y compris pour
  `open_event_stream()`/`open_seek_stream()` — ces deux méthodes ne
  passaient auparavant par aucune journalisation de ce type (nouvel
  enrobage interne `_open_stream_logged`, qui ne traduit jamais
  l'exception : `seek.py` a besoin de la forme brute pour distinguer les
  causes).
- `errors.py::extract_api_message()` (nouvelle fonction, factorisée
  depuis `game_client.py::_extract_api_message`) extrait le texte
  explicatif du corps JSON renvoyé par Lichess (champ `error`).

### Point 2 — Messages exacts à l'écran, persistants

- `seek.py::SeekSession._push_error()` reprend `status_code`,
  `retry_after_s` et le texte Lichess dans l'évènement `{"type": "error",
  ...}` poussé à l'appelant (auparavant : seulement le nom de la classe
  d'exception).
- Nouvelle fonction `core/game_manager_modes/lichess.py::_classify_seek_error_event()`
  traduit ce détail en message distinct :
  - 400 → texte renvoyé par Lichess (`toast.lichess_refus_requete`) ;
  - 401 ou 403 → message unifié « jeton refusé ou droit manquant »
    (`toast.lichess_jeton_refuse`), tel que demandé par l'issue ;
  - 404 → `toast.lichess_404` ;
  - 429 → `toast.lichess_rate_limited_detail`, avec le délai reçu
    (`Retry-After`, repli 60s s'il est absent) ;
  - 5xx → `toast.lichess_indisponible` ;
  - **seule l'absence de code HTTP** (coupure réseau réelle, résolution de
    nom, délai dépassé — `TransportNetworkError`/`TransportTimeoutError`)
    garde `toast.lichess_network_error` (« vérifiez le réseau »).
- Ces messages sont désormais affichés de façon **persistante** (ne
  disparaissent plus seuls après quelques secondes) : `_menu_toast_data()`
  (`state.py`) accepte `vars`/`persistent`, relayés dans le payload
  `state_update` (`toast_vars`/`toast_persistent`) ; `afficherToast()`
  (`app.js`) accepte un 3ᵉ paramètre `persistent` qui désactive le
  minuteur de 4s et ajoute un bouton de fermeture (`×`, classe CSS
  `.toast-persistent`, `main.css`).
- Jamais de relance automatique de la recherche après une erreur : le
  lanceur retourne simplement à l'écran de configuration, à l'utilisateur
  de recliquer (vérifié par un test dédié).
- Nouvelles clés i18n (`fr`/`en`/`de`, simultanément) :
  `toast.lichess_rate_limited_detail`, `toast.lichess_jeton_refuse`,
  `toast.lichess_404`, `toast.lichess_refus_requete`,
  `toast.lichess_indisponible`.

### Point 3 — Pas de régression de la requête d'ouverture de la recherche

- Comparaison par lecture de l'historique git (`git diff` entre le commit
  d'introduction de #327 et celui de #328) : **aucun changement** des
  paramètres envoyés à `POST /api/board/seek` (`time`, `increment`,
  `rated`, `color`) ni de leur construction — confirmé identique à la
  version actuelle (HEAD avant cette issue).
- `time` est envoyé comme un nombre à virgule flottante (ex. `15.0` pour
  15 minutes) — conforme à la documentation officielle (`type: number`,
  pas `integer`) ; `increment` en secondes entières ; `rated` toujours
  `"false"` (partie amicale) ; `color` toujours `"white"`/`"black"`
  (jamais `"random"` : résolu localement avant l'appel, comme pour l'IA).
- Nouveau test paramétré (`test_parametres_exacts_par_cadence_et_couleur`,
  `nicsoft/tests/test_issue329_lichess_http_errors.py`) qui enregistre,
  via un faux transport, la requête exacte envoyée pour **chaque**
  préréglage de cadence (`10+0`/`15+10`/`30+0`/`60+0`/`90+30`) et
  **chaque** couleur (`white`/`black`) — fige ce comportement pour la
  suite.
- La cause du refus réel du 14/11/2026 reste donc côté serveur Lichess
  (état du compte, limite de débit, ou autre condition non reproductible
  sans vraie recherche — interdit par la règle de cette issue), pas une
  régression de la requête envoyée par AlChess.

### Point 4 — Comparaison avec la documentation officielle

Lu le 14/11/2026 (`lichess-org/api`, `doc/specs/tags/board/api-board-seek.yaml`
et `doc/specs/lichess-api.yaml`) :
- `time` : nombre, 0 à 180 minutes ; `increment` : entier, 0 à 180
  secondes — 15+10 est largement dans ces bornes, donc pas la cause d'un
  refus 400 pour ce cas précis.
- 400 : « The creation of the seek failed », corps `{"error": "..."}`
  (texte libre, pas d'énumération officielle des causes possibles).
- 429 : limite de débit générale de l'API (« Only make one request at a
  time » ; « waiting one minute before retrying will be sufficient, but
  some limits may require longer ») — plausible si l'enchaînement des
  deux flux (événements puis recherche) a été perçu comme trop rapproché
  d'une recherche précédente, ou si une recherche/partie antérieure
  n'était pas encore totalement résolue côté serveur.
- Aucune mention officielle d'un refus explicite « recherche déjà
  ouverte » ou « partie déjà en cours » dans ce fichier — AlChess s'en
  protège déjà en amont via le garde-fou existant
  (`_refuse_create_if_games_ongoing`, `/api/account/playing`), qui
  n'aurait pas vu une RECHERCHE en cours sans partie créée (distinction
  non couverte par cette route).
- **Non vérifiable sans vraie recherche** (interdit par la règle de cette
  issue) : code HTTP et corps exacts renvoyés par Lichess lors de l'échec
  réel du 14/11/2026 — désormais capturés si l'incident se reproduit
  (journal général + journal de partie dédié).

### Point 5 — Tests sans connexion réelle

Nouveau fichier `nicsoft/tests/test_issue329_lichess_http_errors.py` (41
tests) :
- `transport.py` : capture et journalisation de 400/401/403/404/500/503
  (code, chemin, jamais le jeton), `Retry-After` présent/absent pour 429,
  troncature du corps à ~500 caractères, connexion refusée → pas de ligne
  "erreur HTTP" journalisée, délai dépassé → `TransportTimeoutError`.
- `seek.py`/`game_client.py` : l'évènement `"error"` et le journal de
  partie dédié portent le code 429 et le délai reçu, jamais le jeton.
- `_classify_seek_error_event` : un message par code connu, 401/403
  unifiés intentionnellement, réseau réel seul cas gardant le message
  réseau, toutes les clés présentes dans `_TOAST_MESSAGES`.
- `_run_lichess_human` bout en bout (double de client levant chaque
  exception au point exact de l'échec réel du 14/11/2026 — dès
  l'ouverture) : message et variables attendus pour 400/401/403/404/429/5xx/
  réseau, persistance (`toast_persistent is True`), pas de relance
  automatique (compteur d'appels).
- Paramètres exacts de `POST /api/board/seek` par cadence × couleur (10
  cas).

Un test existant (`test_issue327_lichess_human.py`, assertion exacte sur
l'évènement `"error"`) a été ajusté pour accepter les nouveaux champs
(`status_code`/`retry_after_s`/`detail`) sans changer ce qu'il vérifiait
réellement.

**Suite complète** : `python3 -m pytest nicsoft/tests --ignore=nicsoft/tests/e2e`
→ 1087 passed, 82 skipped (hors un test isolé, `test_is_alchess_process_par_cmdline`,
qui flaky sous charge complète de la suite — passe systématiquement seul,
avant et après cette modification ; sans lien avec Lichess, non modifié
par cette issue). Suite e2e non lancée (nécessite un navigateur de test,
hors périmètre réseau/risque de cette tâche — voir rapport de clôture).

### Non vérifiable sans vraie partie (interdit par la règle de cette issue)

- Le code HTTP et le corps exacts renvoyés par Lichess lors de l'échec
  réel du 14/11/2026.
- Si une vraie recherche 15+10 échouerait encore aujourd'hui pour la même
  raison (état du compte/serveur au moment de l'essai, non reproductible).

### Fichiers modifiés

`nicsoft/modes/lichess/transport.py`, `errors.py`, `game_client.py`,
`seek.py` ; `nicsoft/core/game_manager_modes/lichess.py`, `state.py` ;
`nicsoft/web/static/app.js`, `css/main.css`, `i18n/{fr,en,de}.json` ;
`nicsoft/tests/test_issue329_lichess_http_errors.py` (nouveau),
`test_issue327_lichess_human.py` (ajustement) ; `CONTEXTE.md`.
