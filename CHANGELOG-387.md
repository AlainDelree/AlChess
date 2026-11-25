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
