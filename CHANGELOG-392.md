# Changelog — Issue #392

## Lichess : resynchronisation après coupure réseau, partie orpheline, attente de position (suite de l'étude #391)

Trois correctifs réels observés le 26/11/2026 avec le vrai compte (étude #391) : retour forcé au menu pendant une attente légitime, partie classée orpheline laissée ouverte après l'annulation d'une recherche, et position/pendules figées après une coupure réseau trop courte pour l'ancien seuil de détection.

### Point 1 — Attente bornée : états actifs complets (`nicsoft/core/game_manager_modes/lichess.py`)

- `_LICHESS_ACTIVE_STATES` couvre désormais aussi `"position_initiale"` et `"lichess_wait_first_move"` (omis jusqu'ici) — un fil de lanceur Lichess qui attend légitimement la position physique ou le premier coup n'est plus jamais abandonné après 15s (`_LICHESS_STOP_TIMEOUT_S`) ni renvoyé au menu avec « l'arrêt de la session a pris trop de temps ».
- Nouvelle `_LICHESS_EXIT_STATES` (`"menu"`/`"config_lichess"`/`"game_over"`) — c'est leur apparition, et elle seule, qui démarre le compte à rebours.
- Garde statique (`test_issue392_point1_lichess_active_states_guard.py`) : relit par expression régulière tous les états posés par les quatre lanceurs (`game_manager_modes/lichess.py`, `modes/lichess/game.py`, `puzzle_game.py`, `seek.py`) et échoue si l'un n'appartient ni à `_LICHESS_ACTIVE_STATES` ni à `_LICHESS_EXIT_STATES` — plus un futur état ajouté sans être classé.

### Point 2 — Partie orpheline après annulation d'une recherche (`nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/modes/lichess/client.py`)

Essai réel : une partie classée créée par Lichess 21ms avant la fermeture du flux de recherche n'a jamais signalé `gameStart` (seulement `seek_closed`) — la récupération étroite de #383 point 3 (`_reap_late_found_game`, 1s après `cancel()`, draine un `"found"` déjà dans la file) n'avait rien à traiter.

- Liste des identifiants de parties déjà en cours mémorisée juste avant chaque recherche humaine (`pre_search_game_ids`, réutilise `_fetch_ongoing_games` déjà appelé par le garde-fou « une seule partie à la fois »).
- Nouveau balayage ÉLARGI en arrière-plan (`_start_orphan_sweep_after_cancel`/`_orphan_sweep_worker`), démarré à chaque annulation (les deux sorties « menu » de `_run_lichess_human`) en plus du mécanisme étroit existant (conservé, inchangé) : revérifie la liste des parties en cours à 1/2/4/6s (`_ORPHAN_SWEEP_CHECKPOINTS_S`) ; toute partie dont l'identifiant n'était pas dans `pre_search_game_ids` et qui compte moins de 2 demi-coups (`_ply_count_from_fen`, déduit du FEN — `_ORPHAN_SWEEP_MAX_PLIES`) est annulée (`abort()`, **jamais** `resign()` — si refusée, la partie et le bandeau de reprise restent, message bref à l'utilisateur).
- Comparaison toujours par identifiant, jamais par comptage ; une partie présente avant la recherche n'est jamais touchée.
- Compteur de génération (`_lichess_launch_generation`, `_bump_launch_generation()` appelé par les trois lanceurs publics) : le balayage s'arrête dès qu'un nouveau lancement commence, pour ne jamais annuler une partie légitime d'une recherche ultérieure.
- `client.get_ongoing_games()` renvoie désormais aussi le FEN courant de chaque partie (`"fen"`, nécessaire au comptage de demi-coups) — jamais affiché ni utilisé ailleurs.
- Nouvelles clés i18n (fr/en/de) : `toast.lichess_orphan_game_annulee`, `toast.lichess_orphan_game_laissee`.
- Tests : `test_issue392_point2_orphan_sweep.py` (fonctions pures, balayage isolé, bout en bout via `_run_lichess_human` sur le scénario exact de l'étude).

### Point 3 — Coupure réseau pendant une partie : resynchronisation, bandeau, seuil (`nicsoft/modes/lichess/game.py`, `game_client.py`, `transport.py`)

a) **Resynchronisation active** (`LichessGame._resync_from_lichess`) : relit l'état complet de la partie (`GameClient.peek_game_full`, UNE SEULE tentative — sans la reprise à délais croissants de `stream_game()`, qui ne renoncerait jamais) et l'applique par le chemin **normal** des coups reçus (`_apply_game_state`, jamais `_apply_game_full` qui rejouerait tout en silence) : coups manqués affichés/bipés/avec LED comme un coup reçu en direct, pendules repoussées.

b) Un refus ambigu (« Not your turn, or game already over », #377/#384 inchangés) déclenche cette resynchronisation si la relecture du flux déjà ouvert ne suffit pas à conclure : coup déjà appliqué → succès silencieux (inchangé) ; position toujours différente de l'échiquier physique une fois resynchronisée → cases rouges (`_awaiting_resync_reset`/`_check_resync_reset`, réutilise l'affichage existant `_activate_illegal_position`) avec la position Lichess déjà corrigée comme cible — **plus jamais** le texte générique « remettez la pièce à sa place » (`_awaiting_piece_reset`, toujours utilisé ailleurs pour le recalage de reconnexion échiquier, #314, inchangé).

c) Resynchronisation elle-même en échec (réseau toujours indisponible) : ni succès silencieux ni vraie erreur affichés, réessai en arrière-plan avec les délais déjà documentés (`_start_resync_retry_loop`/`_resync_retry_worker`, `GameClient.RECONNECT_DELAYS_S` = 1/2/4/8/30s), jamais d'abandon automatique.

d) `_report_network_error()`/`_clear_network_error_if_active()` déclenchent et retirent désormais aussi le bandeau persistant `#378` (`lichess_reconnecting`/`lichess_reconnected`) — pas seulement l'exception du flux : un échec réseau ponctuel (coup, nulle, abandon, réclamation) le mérite tout autant, plus visible qu'un simple toast.

e) Nouveau `transport.py::GAME_STREAM_READ_TIMEOUT_S` (20s) dédié au flux de PARTIE (`stream_lines`, seul appelant `GameClient.stream_game`/`peek_game_full`) — l'ancien `STREAM_READ_TIMEOUT_S` (90s, conservé pour `open_stream`/recherche/évènements, aucune preuve de maintien de connexion régulier pour ceux-là) laissait passer une coupure réelle de 25-37s **sans la moindre exception**. Valeur retenue : recherche web du 26/11/2026 (aucune documentation officielle primaire trouvée pour l'intervalle exact) — sources communautaires indépendantes convergentes (BotLi, lichess-bot, miroirs de la doc officielle) estimant un maintien de connexion Lichess de 7 à 9s pour les flux NDJSON, cohérent avec l'estimation déjà présente dans le code (#309, ~9s). 20s = plus du double de marge, détecte la coupure bien avant 90s et avant même la durée observée le 26/11/2026, sans risquer de fausse reconnexion sur un simple aller-retour lent.

- Tests : `test_issue392_point3_lichess_resync.py` (seuil dédié via faux serveur HTTP local, resynchronisation seule/multi-coups/échec/réessai, intégration complète de `_handle_move_rejected`). Tests existants adaptés sans changer leur intention (`test_issue347_lichess_ambiguous_move_rejection.py`, `test_issue368_lichess_game_network_loss.py`) : la resynchronisation (mockée, sans réseau) remplace l'ancien "remettez la pièce" par les cases rouges pour le cas "vraie erreur" ambigu.

### Non-régression

Suite complète `pytest nicsoft/tests -m "not hardware"` : 2082 réussis, 88 ignorés, 1 désélectionné (deux exécutions identiques). Suite Lichess ciblée (1067 tests) verte. Tests statiques fair-play (#333) et i18n (#310) inchangés et verts.
