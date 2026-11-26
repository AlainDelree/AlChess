# Changelog — Issue #393

## Lichess : tableau de bord des thèmes, messages traduits, libellé de l'adversaire, analyse orientée, compteurs lisibles (suite de l'étude #391)

Cinq correctifs d'affichage et de textes observés lors des essais réels du 26/11/2026 (étude #391, rapport lu par Alain) — la robustesse réseau/partie orpheline de la même étude est traitée par une issue séparée (#392), non touchée ici.

### Point 1 — Tableau de bord des thèmes (`nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/web/static/app.js`, `nicsoft/web/templates/index.html`)

- `check_lichess_puzzle_dashboard()` ne confondait jamais « indisponible » (jeton absent, réseau coupé, droit manquant) et « disponible mais vide » côté serveur (`available` déjà distingué) — mais côté écran, `_lichessPuzzleRenderThemeOptions()` (app.js) annotait TOUS les thèmes « jamais joué » dans les deux cas, faute de lire ce drapeau.
- `_lichessPuzzleRenderThemeOptions()` affiche désormais le libellé nu (sans annotation) pour chaque thème si `available !== true`, et une mention unique en tête de liste (`#cfg-lichess-puzzle-stats-indisponibles`, data-i18n `config.lichess.probleme_stats_indisponibles`) plutôt qu'un « jamais joué » répété — l'annotation « jamais joué »/« peu joué »/stat normale ne s'applique plus que si le tableau de bord a réellement répondu.
- `_lichessPuzzleApplyThemeSelection()` ne tente plus d'appliquer un thème par défaut si le tableau de bord est indisponible (garde locale, en plus du serveur qui n'en calcule déjà jamais dans ce cas).
- Journalisation (INFO, jamais le jeton ni le contenu complet) ajoutée pour une lecture RÉUSSIE du tableau de bord (statut, nombre de thèmes, période demandée) — un échec était déjà journalisé avant cette issue, un succès ne laissait aucune trace.
- Vérification de la lecture de la réponse contre la spécification publique de l'API Lichess (dépôt `lichess-org/api`, schémas `PuzzleDashboard`/`PuzzlePerformance`) : les champs lus (`results.nb`/`results.firstWins`/`results.performance`) correspondent exactement au schéma — aucun défaut de lecture trouvé, rien à corriger sur ce point.
- Tests : `test_issue393_point1_lichess_dashboard_indisponible.py` (journalisation), `test_issue393_point1_lichess_dashboard_indisponible_e2e.py` (libellés distincts, thème par défaut non appliqué) ; les deux tests existants de `test_issue389_puzzle_theme_sort_e2e.py` qui comparaient `{}`/`null` avec la même attente de tri ont été commentés pour expliquer que l'ordre reste intentionnellement identique (aucune statistique connue dans les deux cas) — la distinction porte sur le LIBELLÉ, pas le tri, désormais couverte par les nouveaux tests e2e.

### Point 2 — Messages de Lichess traduits (`nicsoft/modes/lichess/errors.py`, `nicsoft/modes/lichess/game.py`, `nicsoft/core/game_manager_modes/lichess.py`, `nicsoft/web/static/app.js`)

- Nouvelle fonction pure `errors.py::translate_api_detail(message)` : reconnaît les messages bruts connus de l'API Lichess (« Not your turn, or game already over », « Piece on X cannot move to Y », « Game is already over ») et retourne une clé i18n (+ variables neutres comme des cases, jamais de texte anglais) ; message inconnu -> `lichess.detail.generique`.
- Quatre points d'envoi mis à jour pour transmettre `detail_key`/`detail_vars` au lieu d'un texte anglais brut inséré dans `vars.detail` : coup refusé (`_move_refused_payload`, événement `lichess_move_refused`), réclamation refusée, offre de nulle refusée (`game.py`), recherche d'adversaire/équilibre des couleurs refusée (`_classify_seek_error_event`, `game_manager_modes/lichess.py`).
- Côté navigateur, `_lichessResolveToastVars()` (nouvelle fonction, app.js) résout `detail_key`/`detail_vars` en texte traduit via `t()` avant affichage (seul endroit qui connaît la langue choisie) ; le handler `lichess_move_refused` fait de même directement. Message inconnu -> phrase générique traduite, jamais l'anglais brut ; le texte brut original reste disponible au journal serveur (déjà écrit avant cet appel, inchangé).
- Le refus d'équilibre des couleurs (`toast.lichess_refus_equilibre_couleur`) n'ajoute plus le détail de Lichess (toujours « must also play some games as ... », déjà expliqué par la phrase elle-même) — `{detail}` retiré du gabarit dans les 3 langues.
- Nouvelles clés i18n `lichess.detail.pas_votre_tour_ou_terminee`, `lichess.detail.partie_terminee`, `lichess.detail.piece_ne_peut_aller`, `lichess.detail.generique` (fr/en/de).
- Tests adaptés (vars désormais `{detail_key, detail_vars}` au lieu de texte brut) : `test_issue330_lichess_random_color.py`, `test_issue329_lichess_http_errors.py`, `test_issue334_lichess_opponent_claim.py`, `test_issue347_lichess_resign_anytime_and_draw_after_move.py`. Nouveaux tests : `test_issue393_point2_lichess_detail_translation.py` (Python), `test_issue393_point2_lichess_messages_traduits.py` (e2e, fr/en/de).

### Point 3 — Libellé de l'adversaire (`nicsoft/modes/lichess/game.py`, `nicsoft/web/static/app.js`)

- L'événement `lichess_move` transmet désormais `opponent_is_ai`/`opponent_name` (comme `lichess_init` depuis #327) — `_apply_new_moves()` les lit sur `self._opponent_is_ai`/`self.opponent_name`.
- app.js (`socket.on("lichess_move")`) n'affiche plus inconditionnellement « IA de Lichess (niveau N) » pour un coup adverse : utilise `data.opponent_is_ai` pour choisir entre ce libellé et le nom de l'adversaire humain (`data.opponent_name`, ou le libellé « adversaire inconnu » si absent).
- Écart signalé par #391 (FEN de ce même événement = `board_fen()` seul, sans trait ni droits de roque) vérifié mais NON corrigé : `fenToBoard()` (app.js) suppose un FEN SANS espaces (`split("/")` sur la chaîne entière) — lui passer un FEN complet casserait visiblement le rendu de la dernière rangée. Rien changé sur ce point, documenté ici et dans `docs/contexte/lichess.md`.
- Tests : `test_issue393_point3_lichess_opponent_label.py` (serveur), `test_issue393_point3_lichess_opponent_label_e2e.py` (navigateur) — coup adverse IA/humain, coup propre, initialisation inchangée.

### Point 4 — Analyse orientée (`nicsoft/web/static/app.js`, `nicsoft/web/templates/index.html`)

- Paramètre d'adresse confirmé par lecture du code source public de lila (`app/controllers/UserAnalysis.scala::load` -> `getColor()`, défini dans `modules/web/src/main/RequestGetter.scala` avec le nom par défaut `"color"`) et de scalachess (`Color.scala::fromName`, strictement `"white"`/`"black"` en minuscules, toute autre valeur ignorée côté Lichess, repli sur la couleur au trait du FEN).
- `_lichessPuzzleAnalyseOnLichess()` ajoute `?color=white|black` à l'adresse selon `_puzzleSetupColor` (nouvelle variable, mémorisée en même temps que `_puzzleSetupFen` — la couleur jouée par l'utilisateur dans CE problème) via la nouvelle fonction pure `_lichessAnalysisColorParam()` qui valide strictement ces deux valeurs.
- `_lichessPuzzleCopyFen()` inchangée (le FEN ne porte aucune orientation) — note ajoutée sous les deux boutons (`lichess.puzzle.fen_orientation_note`, fr/en/de) précisant que l'orientation est reprise par « Analyser sur Lichess ».
- Tests : `test_issue393_point4_lichess_analyse_orientee_e2e.py` — adresse construite avec la bonne orientation (Blancs/Noirs), valeur invalide refusée, absence de couleur si inconnue, FEN copié non modifié.

### Point 5 — Compteurs du jour lisibles (`nicsoft/web/static/app.js`, `nicsoft/web/templates/index.html`, `nicsoft/web/static/css/main.css`)

- Les trois lignes de phrase (« Thème : 2 réalisés — 1 réussis, 1 ratés. (3 restants pour atteindre 5) », toujours au pluriel même pour "1 restant") remplacées par un tableau (`#lichess-puzzle-daily-counts-table`) : une ligne par type (Thème/Phase/Mélange), colonnes Réalisés/Réussis/Ratés/Reste.
- Colonne Reste (en-tête ET cellule, toujours la dernière) masquée entièrement via la classe `lichess-puzzle-daily-counts-no-reste` sur le tableau quand la taille de séance réglée est 0 (CSS `:last-child`).
- La ligne du type de série actuellement sélectionné est mise en valeur (classe `.selected`) — `selectPuzzleSeriesModeLichess()` et l'arrivée de `config_data` déclenchent désormais aussi `_lichessPuzzleRenderDailyCounts()` (réordonné après la restauration de `_lichessPuzzleSeriesMode`, qui arrivait trop tard pour la mise en valeur initiale).
- Accord singulier/pluriel correct sur l'infobulle « Reste » (`title`, seule phrase restante) — clé `_un` dédiée pour `reste === 1`, comme ailleurs dans l'application (ex. `exercices.end_of_line_feedback_un`) ; données et règles de calcul (#390) inchangées.
- Anciennes clés i18n `config.lichess.probleme_compteur_ligne`/`probleme_compteur_reste` retirées (plus utilisées), remplacées par `probleme_compteur_col_*` et `probleme_compteur_reste_titre(_un)`.
- Tests : `test_issue393_point5_lichess_compteurs_jour_e2e.py` — structure (une ligne par type, valeurs en texte), absence de la colonne Reste à taille 0, mise en valeur de la série sélectionnée, accords singulier/pluriel.

### Documentation

- `docs/contexte/lichess.md` mis à jour (paragraphe dédié #393, état réel).
- `CONTEXTE.md` non modifié (aucune nouvelle règle d'architecture, de convention ou de dépendance — ces cinq correctifs restent internes au domaine Lichess déjà indexé).
