# Changelog — issue #349

## Lichess classé : ma cote affichée et rangement des PGN par cadence

Deux demandes d'Alain après sa première partie classée (#344), traitées ensemble car elles touchent le même code (enregistrement du PGN et affichage des joueurs) : afficher MA cote (comme celle de l'adversaire, déjà existante) et la nouvelle cote de fin de partie classée ; ranger les parties classées dans un dossier séparé par cadence. Entièrement hors ligne (faux serveur local, `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) — aucune vraie recherche/partie Lichess, aucun vrai jeton utilisé.

### Partie 1 : ma cote et ma nouvelle cote

**1. Ma cote affichée (point 1).**

- `nicsoft/modes/lichess/game.py::LichessGame._apply_game_full()` : nouveau `self_dict` (mon côté du `gameFull`, symétrique à `opponent_dict`) → `self.user_rating`/`self.user_provisional` lus depuis `self_dict.get("rating")`/`get("provisional")` — toujours lus, même contre l'IA (mon côté porte `rating`, le côté adverse `aiLevel` à la place) ; `None` si absente, jamais devinée. `self._my_username` (champ `id`) retenu pour la nouvelle cote (point 3). `self.opponent_provisional` ajouté symétriquement (existait seulement pour `opponent_rating`).
- `lichess_init` porte désormais `user_rating`/`user_provisional`/`opponent_provisional` en plus des champs existants — même chemin pour une partie normale ET une reprise (L2b), un seul point d'émission (`_apply_game_full`).
- `app.js` : nouvelle fonction `_lichessRatingSuffix(rating, provisional)` (`" (1327)"`, `" (1327?)"` si provisoire — même convention que lichess.org), utilisée pour construire `opponentLabel` (déjà existant, désormais via cette fonction commune) ET le nouveau `playerLabelWithRating`, affecté à `#player-top-name`/`#player-bottom-name` et au sous-titre — mêmes éléments DOM pendant la partie et à l'écran de fin/d'analyse, donc affichés sans code supplémentaire sur ce second écran.

**2. Cotes dans le PGN et l'écran « Révision PGN » (point 2).**

- `build_pgn_headers()` (`game.py`) accepte `user_rating`/`opponent_rating` et écrit les en-têtes standard `WhiteElo`/`BlackElo` (affectés au bon côté selon `user_color`) — seulement quand la cote correspondante est connue.
- `app.js::parsePgn()` lit `WhiteElo`/`BlackElo` du PGN chargé (import, « Coller PGN », bibliothèque, classeur — tous passent par cette fonction) et les ajoute aux noms via `_lichessRatingSuffix` ; `_reviewSetTopBottomNames()` (déjà sensible à l'orientation depuis #345) les place dans le bon ordre sans changement.

**3. Nouvelle cote en fin de partie classée (point 3) — mécanisme REMPLACÉ.**

- Ancien mécanisme #344 (`GameClient.fetch_rating_diff()`, flux général `/api/stream/event` + attente d'un `gameFinish`) **retiré** : Alain avait déjà constaté qu'il manquait souvent (délai d'arrivée non garanti par la doc Lichess), et il ne donnait qu'une variation, jamais la cote absolue demandée par cette issue.
- Remplacé par `GameClient.fetch_my_rating(username, speed_key)` (nouveau) : `GET /api/user/<username>` — route **publique** de la doc officielle (« No OAuth and no scope is required »), aucun jeton/droit supplémentaire nécessaire (le jeton de l'instance est quand même envoyé, sans effet pour cette route). Lit `perfs[speed_key]["rating"]` ; ne lève jamais (réseau/HTTP/parsing → `None`).
- `LichessGame._maybe_fetch_new_rating()` (remplace `_maybe_fetch_rating_diff`) : fil dédié démarré par `_finalize()` seulement si `rated` et fin réelle. Un essai après `_NEW_RATING_INITIAL_DELAY_S` (1,5s), **une seule** nouvelle tentative après `_NEW_RATING_RETRY_DELAY_S` (4s) si la cote lue est encore égale à `self.user_rating` (cote de départ) — la variation est calculée côté Python (`new_rating - start_rating`), jamais fournie par Lichess. Pousse `lichess_new_rating` (`new_rating`/`rating_diff`) seulement si une valeur entière est obtenue ; silencieux (rien poussé) sinon.
- `app.js` : `lichess_rating_diff` → `lichess_new_rating` ; `_lichessRenderRatedInfo()` affiche désormais la nouvelle cote (+ sa variation si connue) via la nouvelle clé i18n `lichess.nouvelle_cote` (`fr`/`en`/`de`).
- **Garder/remplacer/compléter** : remplacé entièrement, pas complété — les deux mécanismes visent la même information (l'état de la cote après la partie), et le nouveau est strictement plus simple à réessayer (une requête HTTP ordinaire vs. un flux à maintenir ouvert) tout en répondant exactement à la demande d'Alain (« nouvelle cote », pas seulement une variation).

**4. Sécurité/i18n (point 4).**

- `_my_username` n'est jamais journalisé ni envoyé au navigateur au-delà de ce qui l'est déjà pour l'adversaire ; passé par `urllib.parse.quote()` avant insertion dans l'URL (défense en profondeur).
- Cotes affectées via `.textContent` (jamais `innerHTML`), comme tout le reste de l'écran Lichess. Clés i18n ajoutées simultanément dans les 3 langues.

**5. Tests.** `nicsoft/tests/test_issue349_lichess_rating_cadence.py` (30 tests) + `nicsoft/tests/e2e/test_issue349_lichess_rating_e2e.py` (8 tests, Playwright) : cotes des deux joueurs (2 orientations), cote provisoire, absence de cote, en-têtes PGN + écran Révision, `fetch_my_rating` (succès/catégorie absente/erreur réseau), orchestration (inchangée puis changée à la 2ᵉ tentative, échec réseau silencieux, jamais tentée sans cote de départ). `test_issue344_lichess_rated.py` adapté (tests de l'ancien `fetch_rating_diff` retirés, 2 tests `_finalize` portés sur la nouvelle API).

### Partie 2 : dossier Classée par cadence

**1. Rangement par cadence (point 1).**

- `pgn_cadence_folder_name(clock_limit_s, clock_increment_s)` (nouveau, `game.py`) : `"<minutes>+<incrément en secondes>"` (ex. `"10+0"`, `"15+10"`, `"90+30"`) — chiffres et `+` seulement, sûr sous Windows. Dérivé directement de la cadence confirmée de la partie, jamais de `cadence_key` (peut être vide à la reprise).
- `LichessGame._save_pgn()` : une partie classée (`self.rated`) est enregistrée dans `Lichess/Classée/<cadence>/` via `build_final_path("Lichess", f"Classée/{cadence}", ...)` — `build_final_path()` (inchangé) gère déjà la création récursive (`os.makedirs`) et un `game_type` contenant `/` sans modification (pathlib découpe la chaîne en composants sur les deux plateformes). Dossier créé à la demande (jamais à l'avance).

**2. Amicale inchangée (point 2).** Une partie amicale (IA ou humain) reste enregistrée dans `Lichess/Amicale/`, exactement comme avant — aucun fichier déjà enregistré déplacé ni renommé.

**3. En-tête Event (point 3).** `_save_pgn()` construit désormais l'en-tête `Event` selon `self.rated` : `"Lichess, classée (<cadence>) contre un humain"` pour une classée (avant cette issue, il disait toujours « amicale », même pour une partie classée — bug corrigé en même temps), `"Lichess, amicale contre l'IA niveau N"` / `"Lichess, amicale contre un humain"` sinon (inchangé).

**4. Listes de parties (point 4).** Vérification plutôt que modification : `nicsoft/web/server.py::_get_game_folders()` (combobox « type de partie » de `sauvegarderNicLink()`, écran Révision/Analyse) liste les dossiers par `os.listdir()` à deux niveaux (`mode`/`game_type`) — elle retrouve `Classée` automatiquement dès qu'une partie y a été enregistrée, sans changement de code. C'est la **seule** fonction du projet qui parcourt `GAMES_DIR` : « Mes parties AlChess » (import de fichier/« Coller PGN »/classeur de session) et la bibliothèque PGN (collections sous `DATA_DIR/pgn_library/`, totalement séparée) ne lisent jamais ce dossier directement — aucun risque de doublon ni de parcours récursif à ajouter. Point d'attention pour Alain : cette combobox ne descend pas au niveau cadence — une sauvegarde **manuelle** d'un PGN quelconque via « Lichess — Classée » (ex. un PGN collé) écrirait directement sous `Classée/` sans sous-dossier de cadence, contrairement à l'enregistrement **automatique** de fin de partie Lichess (`_save_pgn`, seul concerné par cette issue), qui range toujours correctement par cadence.

**5. Tests.** Mêmes fichiers que la partie 1 (`test_issue349_lichess_rating_cadence.py`) : classée 10+0 → `Classée/10+0`, classée 15+10 → `Classée/15+10`, amicale (humain et IA) → `Amicale`, en-tête `Event` « classée » avec cadence, dossiers jamais créés à l'avance — tout sur un `GAMES_DIR` temporaire isolé (fixture autouse `conftest.py::_isolate_games_dir`), jamais le vrai dossier d'Alain.

### Non vérifié

Aucune vraie partie classée jouée pendant cette issue (interdit par consigne) : délai réel de recalcul de la cote côté Lichess après la fin d'une partie non mesuré — `_NEW_RATING_INITIAL_DELAY_S`/`_NEW_RATING_RETRY_DELAY_S` sont une estimation prudente. Alain vérifiera à sa prochaine partie classée contre un humain (les deux parties de cette issue).
