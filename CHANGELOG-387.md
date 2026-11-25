# Changelog — Issue #387

## Problèmes Lichess : historique local des problèmes résolus (point 1, suite de #385)

L'étude #385 a établi que chaque problème Lichess résolu/raté est déjà envoyé à Lichess comme classé (faisant évoluer la cote du compte), mais qu'AlChess ne garde de trace que d'un journal texte par session, purgé automatiquement et inexploitable par programme. Ce point ajoute un historique local structuré, un enregistrement par problème **terminé**.

### Nouveau fichier (`nicsoft/modes/lichess/puzzle_history.py`)

- `PUZZLE_HISTORY_FILE = DATA_DIR / "lichess_puzzle_history.jsonl"` (DATA_DIR : dossier de données déjà gitignoré, voir `config.py`/`.gitignore` — jamais LOGS_DIR, purgé automatiquement, jamais `config.json`).
- `append_puzzle_history(entry: dict)` : ajoute une ligne JSON (JSON Lines) en fin de fichier, crée le dossier parent si besoin. Ne lève **jamais** — un échec (disque plein, droits) est journalisé en `warning` et silencieusement ignoré, pour ne jamais interrompre un problème/une partie en cours.
- Aucune rotation ni limite de taille : un enregistrement par problème résolu reste de l'ordre de quelques centaines d'octets — documenté dans `docs/contexte/lichess.md`.

### Correctif (`nicsoft/modes/lichess/puzzle_game.py`)

- `PuzzleGame.__init__` : nouveau paramètre optionnel `series_theme: str = ""` (préparation du point 2 — thème de la série de la séance, vide tant qu'aucun choix de thème n'existe, comportement actuel inchangé) ; chronométrage `self._start_ts`/`self.duration_s` (horloge monotone).
- `_finish()` : calcule `duration_s`, puis — après le premier essai d'envoi du résultat (`_try_submit_pending()`, inchangé) — appelle la nouvelle méthode `_record_history()`, qui construit l'entrée et la passe à `append_puzzle_history()`.
- Champs enregistrés : `timestamp` (date+heure ISO), `puzzle_id`, `series_theme`, `setup_fen` (position de départ du problème), `themes` (fournis par Lichess), `win` (bool), `duration_s`, `rating_before`/`rating_after`/`rating_diff` (absents si l'envoi a échoué), `submit_ok` (bool). **Jamais** le jeton ni aucune information d'authentification.
- Comportement retenu pour un abandon (retour au menu pendant un problème en cours, ou tout autre bouton qui quitte avant résolution) : **aucune ligne n'est écrite** — `_finish()` (donc `_record_history()`) n'est jamais atteint sur ce chemin (voir `run()`/`_process_browser_actions()`, inchangés). Ce comportement s'applique identiquement à `VirtualPuzzleGame` (hérite de `_finish`/`_record_history`, non redéfinis).
- Décision retenue si l'envoi échoue puis réussit sur réessai manuel (`lichess_puzzle_retry_submit`) : l'historique n'est écrit **qu'une seule fois**, au premier essai — jamais réécrit/mis à jour par un réessai ultérieur, même réussi (cotes restent absentes, `submit_ok` reste `false` dans cette ligne). Non demandé explicitement par l'énoncé ; choix fait pour garder un seul point d'écriture, simple et déjà suffisant (l'issue ne demande pas de mettre à jour une ligne déjà écrite).
- Rien d'autre ne change : l'envoi du résultat à Lichess (`submit_puzzle_result`), l'affichage à l'écran (`_result_payload`), et l'enchaînement « problème suivant » restent identiques à avant cette issue.

### Tests (`nicsoft/tests/test_issue387_lichess_puzzle_history.py`, nouveau, 11 tests)

Entièrement sans réseau (`submit_puzzle_result` monkeypatché) et sans matériel (`FakeBoard`), fichier d'historique toujours redirigé vers `tmp_path` (monkeypatch de `puzzle_history.PUZZLE_HISTORY_FILE`) — jamais le vrai dossier de données de l'utilisateur :
- `append_puzzle_history` : écrit une ligne JSON, ajoute en fin de fichier (plusieurs appels), crée le dossier parent manquant, ne lève jamais même si l'écriture échoue (mkdir monkeypatché pour lever `OSError`), jamais de champ `token`/`lichess_token`.
- Intégration `PuzzleGame` : problème résolu (entrée complète, tous les champs attendus), problème raté (`win: false`), envoi réseau échoué (entrée quand même écrite, cotes `None`, `submit_ok: false`), réessai réussi après échec (ne réécrit pas une seconde ligne), abandon avant résultat (aucune ligne), `series_theme` transmis au constructeur correctement reporté dans l'entrée.

### Documentation

`docs/contexte/lichess.md` : nouveau paragraphe dans la section « Problèmes (puzzles) » décrivant le fichier, le point d'écriture unique, le cas de l'abandon, et l'absence de rotation. Pas de changement d'architecture générale : rien dans `docs/contexte/architecture.md`.

### Vérification

- `test_issue387_lichess_puzzle_history.py` : 11/11.
- Non-régression : `test_issue351_lichess_puzzles.py`, `test_issue354_lichess_puzzles_l3.py`, `test_issue364_lichess_puzzle_virtuel.py`, `test_issue333_lichess_no_engine.py` (garde fair-play — fichier nouveau automatiquement couvert par le glob `nicsoft/modes/lichess/*.py`) : tous verts.
- Suite complète : voir la clôture du point 2 ci-dessous (les deux points sont vérifiés ensemble en fin de tâche, comme demandé par l'énoncé).

## Problèmes Lichess : séance de N problèmes avec compteur et bilan (point 2)

Alain veut s'entraîner par séances de N problèmes, voir où il en est (« problème 7 sur 25 »), et obtenir un bilan à la fin. Structure volontairement prête pour une évolution future (choix de thème/phase de partie, puis enchaînement de plusieurs séries) sans l'implémenter encore : la séance est une LISTE de séries (thème, nombre de problèmes), une seule aujourd'hui, thème vide (angle par défaut, comportement actuel de demande du problème suivant, inchangé).

### Nouveau (`nicsoft/core/game_manager_modes/lichess.py`)

- `_PuzzleSeriesSpec(theme, count)` : une série de la séance (`count` = 0 signifie sans limite, valide seulement pour l'unique série d'aujourd'hui).
- `_PuzzleSessionTracker` : comptabilise la séance au fil de la boucle des deux lanceurs (`_run_lichess_puzzle`/`_run_lichess_puzzle_virtual`) — jamais pendant `PuzzleGame` elle-même. `record(game)` n'est appelé que si `game.outcome is not None` (résultat connu) : un abandon (retour au menu en cours de problème, ou tout bouton qui quitte avant résolution) ne compte jamais, ni dans le compteur affiché ni dans le bilan — identique à la décision retenue pour l'historique local (point 1). `is_complete()` : faux en permanence si la série est sans limite. `summary_payload()` : solved/failed/avg_duration_s (None si aucun problème terminé)/rating_diff_total (None si aucune cote connue, résultat jamais envoyé à Lichess)/failed_puzzles (liste ordonnée `{puzzle_id, rating}`).
- `_build_puzzle_session()` : lit `lichess_puzzle_session_size` dans `config.json` (mécanisme de persistance déjà en place) — défaut 25, valeur non entière ou négative repliée sur 25/0.
- `_show_puzzle_session_summary_and_wait(session)` : affiche l'état `lichess_puzzle_session_summary` (`set_app_state`) et bloque sur `get_action` jusqu'à `back_menu` — seul bouton de cet écran. Nouvel état ajouté à `_LICHESS_ACTIVE_STATES` (jamais borné par `_LICHESS_STOP_TIMEOUT_S`, l'utilisateur doit pouvoir lire le bilan sans limite de temps).
- Les deux lanceurs : construisent la session avant la boucle, passent `session.current_theme` à `PuzzleGame`/`VirtualPuzzleGame` (`series_theme`, déjà prévu par le point 1), ajoutent `puzzle_index`/`puzzle_total` au payload `lichess_puzzle_playing`, appellent `session.record(game)` après `game.run()` si un résultat existe, et affichent le bilan (`return` juste après, jamais de nouveau problème) si `session.is_complete()` avant de reboucler sur « problème suivant ».

### Routage (`nicsoft/web/server.py`)

- `lichess_puzzle_session_summary` ajouté à `_ACTIVE_GAME_STATES` : une action émise depuis cet écran (le bouton « Retour au menu ») part en `action_queue`, lue par `_show_puzzle_session_summary_and_wait` — sans cet ajout elle serait partie en `menu_queue`, jamais lue par ce lanceur, et le bouton serait resté sans effet jusqu'à l'expiration du fil (15 s, `_LICHESS_STOP_TIMEOUT_S`) plutôt qu'immédiat.
- `on_action()` : un `back_menu` depuis cet état passe `_app_state` à `"menu"` immédiatement (comportement déjà générique, inchangé).

### Configuration (`nicsoft/core/config_manager.py`)

- `lichess_puzzle_session_size: 25` ajouté à `DEFAULT_CONFIG` — 0 = sans limite (comportement d'avant cette issue).

### Interface (`templates/index.html`, `static/app.js`, `static/css/main.css`)

- Écran de configuration des problèmes : champ numérique « Nombre de problèmes de la séance » (`#cfg-lichess-puzzle-session-size`), sauvegardé immédiatement au changement (`lichessSavePuzzleSessionSize()`, même mécanisme que `lichessToggleBeep`) ; valeur non entière/négative repliée sur 25 côté client avant envoi.
- Écran en jeu : `#lichess-puzzle-counter` affiche « Problème X / N » (`lichess.puzzle.compteur`) ou « Problème X » sans limite (`lichess.puzzle.compteur_illimite`) — même écran partagé par l'échiquier physique et le mode virtuel, pas de distinction à faire.
- Nouvel écran `#screen-lichess-puzzle-summary` (bilan) : réussis/ratés, durée moyenne (si au moins un problème terminé), variation totale de cote (si connue, sinon message explicite), liste des problèmes ratés avec lien `https://lichess.org/training/<puzzle_id>` (`target="_blank" rel="noopener noreferrer"`), bouton unique « Retour au menu » (`data-action="back_menu"`).
- `_renderLichessPuzzleSessionSummary(data)` : toute valeur venue de Lichess (identifiant de problème, cote) insérée en texte (`textContent`/`createElement`, jamais `innerHTML`) — règle de sécurité XSS du projet.
- CSS : `.lichess-puzzle-counter` (style discret, même famille que `.lichess-puzzle-end-banner`).

### i18n (`fr.json`, `en.json`, `de.json`)

9 nouvelles clés ajoutées simultanément dans les 3 fichiers : `config.lichess.probleme_session_taille`, `config.lichess.probleme_session_illimitee`, `lichess.puzzle.compteur`, `lichess.puzzle.compteur_illimite`, `lichess.puzzle.bilan_titre`, `lichess.puzzle.bilan_reussis`, `lichess.puzzle.bilan_rates`, `lichess.puzzle.bilan_duree_moyenne`, `lichess.puzzle.bilan_variation_totale`, `lichess.puzzle.bilan_variation_inconnue`, `lichess.puzzle.bilan_rates_titre`.

### Tests

- `nicsoft/tests/test_app_state.py` : état `lichess_puzzle_session_summary` ajouté aux tests paramétrés existants (jamais dans `menu_queue`) + deux tests dédiés demandés par l'énoncé — `test_lichess_puzzle_session_summary_est_un_etat_actif()` (appartient explicitement à `_ACTIVE_GAME_STATES`, pas seulement « jamais menu_queue ») et `test_back_menu_depuis_bilan_puzzle_route_vers_action_queue_et_passe_au_menu()` (routage précis : `action_queue` + `_app_state == "menu"`).
- `nicsoft/tests/test_issue387_lichess_puzzle_session.py` (nouveau, 24 tests) : unités pures de `_PuzzleSessionTracker` (comptage, bilan, sans limite), `_build_puzzle_session` (défaut/personnalisé/0/valeur invalide/négative), `_show_puzzle_session_summary_and_wait` (affiche puis bloque, une action hors-sujet ne débloque pas), routage de l'état, et deux tests d'intégration bout en bout en mode virtuel (jamais d'échiquier réel, jamais de réseau réel) : une séance de 2 problèmes (1 résolu, 1 raté) affichant le bilan correct sans 3e problème demandé ; un retour au menu après le 1er problème d'une séance de 3 qui ne montre jamais le bilan.

### Vérification

- `test_app_state.py`, `test_issue387_lichess_puzzle_session.py`, `test_issue387_lichess_puzzle_history.py` : tous verts.
- Fair-play (`test_issue333_lichess_no_engine.py`) : vert, aucun nouveau fichier créé hors des dossiers déjà couverts par son glob.
- Suite complète `pytest nicsoft/tests -m "not hardware"` : 1896 passés, 87 ignorés, 1 désélectionné — exécutée deux fois de suite, résultat identique. (Référence #386 : ~1858 passés/86 ignorés/1 désélectionné ; l'écart de +38 tests correspond aux tests ajoutés par les deux points de cette issue, l'écart de +1 ignoré est sans rapport avec cette issue — déjà présent dans l'environnement, non introduit par ces deux points.)

### Vérification manuelle restant à faire (par Alain, avec jeton et réseau réels)

- Régler la séance à 3 dans l'écran de configuration des problèmes, lancer une séance (mode virtuel ou échiquier) : vérifier l'affichage « Problème 1/3 », « 2/3 », « 3/3 », puis l'écran de bilan (réussis/ratés, durée moyenne, variation de cote, liste des ratés avec lien Lichess fonctionnel), puis « Retour au menu ».
- Vérifier que `~/NicLink/data/lichess_puzzle_history.jsonl` (ou l'équivalent de `DATA_DIR` sur la machine d'Alain) contient bien 3 lignes JSON lisibles après cette séance.
- Lancer une nouvelle séance et cliquer « Retour au menu » après le 1er problème : vérifier l'absence de bilan (retour direct au menu) et que ce problème est quand même présent dans le fichier d'historique.
