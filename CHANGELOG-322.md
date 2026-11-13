# Changelog — Issue #322

# Issue #322 — Lichess : contre l'IA, ni phrase d'annulation ni décompte du premier coup ; pendules jamais décomptées avant les premiers coups

## Contexte

Essai réel d'Alain après #321 (partie amicale contre l'IA de Lichess niveau 1, 15+10, utilisateur aux noirs, juste après le premier coup e4 de l'IA). Deux défauts restaient visibles à l'écran :

1. La phrase « Jouez votre premier coup — la partie sera annulée dans environ 27 secondes » apparaissait contre l'IA, alors que sur lichess.org une partie contre l'IA n'affiche jamais de menace d'annulation ni de décompte du premier coup (contrairement à une partie contre un humain, qui elle les affiche) — confirmé par l'essai réel d'Alain (partie non annulée après plus de 28 secondes).
2. La pendule de l'utilisateur affichait 14:57 (au lieu de 15:00) alors qu'il n'avait pas encore joué son propre premier coup : elle décomptait localement, alors que sur lichess.org les deux pendules restent figées à leur valeur de départ jusqu'à ce que chaque camp ait joué son propre premier coup.

## 1. Plus de menace d'annulation ni de décompte contre l'IA

Cause : `_maybe_activate_first_move_deadline()` (`nicsoft/modes/lichess/game.py`) calculait toujours une estimation locale (`estimated_first_move_deadline_s()`, issue #321 point 6) dès que Lichess n'envoyait pas le champ `expiration` — sans distinguer IA et humain, alors que l'estimation elle-même (délai avant annulation du premier coup, lu dans le code lila) ne s'applique en réalité qu'aux parties contre un humain.

Correction :
- Nouvel attribut `self._opponent_is_ai`, déduit dans `_apply_game_full()` de la présence d'`aiLevel` d'un des deux côtés — vrai pour toute partie lancée par AlChess aujourd'hui (seul le mode « contre l'IA » existe), prêt pour un futur mode contre un humain sans rien y changer.
- `_maybe_activate_first_move_deadline()` ne calcule plus d'estimation locale (`_first_move_deadline_estimate_total_s` reste `None`) quand `self._opponent_is_ai` est vrai et qu'aucune `expiration` explicite n'est fournie — dans ce cas l'évènement `lichess_first_move_deadline` envoyé au navigateur porte `seconds: None`, comme avant l'estimation locale de #321. Si Lichess envoie malgré tout une `expiration` explicite pour une partie contre l'IA, elle reste utilisée normalement (décompte exact, rouge à 5 secondes).
- Côté navigateur, ce cas (`seconds` absent) affichait déjà un texte sans décompte (`lichess.premier_coup_sans_decompte`) et jamais la classe de danger (`_lichessRenderFirstMoveDeadline()` dans `app.js`, inchangé) — seul le texte lui-même menaçait encore d'annulation. Les 3 traductions (`fr/en/de.json`) ont été corrigées en un texte purement informatif : « Jouez votre premier coup. » / « Play your first move. » / « Spielen Sie Ihren ersten Zug. ».
- Le comportement contre un humain (quand ce mode existera) n'est pas modifié : décompte, mention « environ » si estimé, rouge à 5 secondes ou moins.

## 2. Pendules jamais décomptées avant les premiers coups des deux camps

Cause : `_maybe_push_clock()` extrapolait toujours le temps écoulé localement (`now - self._clock_ref_monotonic`) pour décompter la pendule du camp au trait, sans savoir si Lichess faisait réellement tourner cette pendule. Or sur lichess.org (vérifié par l'essai réel d'Alain, confirmé par la cohérence avec le champ `expiration`/`millisToMove` qui gère justement le premier coup de chaque camp *en dehors* de `wtime`/`btime`) : les deux pendules restent figées à leur valeur de départ jusqu'à ce que **chaque camp** ait joué son propre premier coup — pas seulement celui qui est actuellement au trait. Concrètement : au tout début de partie (`moves_applied == 0`), la pendule des blancs ne tourne pas pendant leur réflexion sur le 1er coup ; après ce 1er coup (`moves_applied == 1`), la pendule des noirs ne tourne pas non plus pendant leur propre 1er coup (c'est exactement le cas observé par Alain, 14:57 au lieu de 15:00 figé) ; ce n'est qu'à partir du 2e coup de chaque camp (`moves_applied >= 2`) que les deux pendules décomptent normalement, selon le trait.

Correction :
- Nouvel attribut `self._clock_running`, recalculé dans `_reset_clock_from_state()` (appelé à chaque `wtime`/`btime` reçu de Lichess, donc après chaque coup) : `self._moves_applied >= 2`.
- `_maybe_push_clock()` force `elapsed_s = 0.0` tant que `self._clock_running` est faux — la pendule envoyée au navigateur reste alors strictement égale à la dernière valeur connue de Lichess, jamais décomptée par une minuterie locale qui partirait d'elle-même. Dès que `self._clock_running` devient vrai, l'extrapolation normale reprend (comportement inchangé depuis #309).
- `compute_clock_ms()` (fonction pure) n'a pas été modifiée — le gel se fait uniquement en amont, par `elapsed_s` figé à 0.
- Vérifié pour les deux couleurs (voir tests) : le gel s'applique aussi bien à la pendule des blancs avant leur tout premier coup qu'à celle des noirs avant leur propre premier coup.

### Journal

Une ligne de log (niveau INFO, logger `niclink.lichess`) est émise à chaque recalage de pendule (`_reset_clock_from_state()`) avec les valeurs blancs/noirs, le trait et l'état `decompte` (`True`/`False`), plus une ligne dédiée au moment précis où le décompte démarre (« Lichess : pendules commencent à décompter après les premiers coups des deux camps (...) »), journalisée une seule fois à la transition.

## Tests

- `nicsoft/tests/test_issue311_lichess_sequencing.py` :
  - `test_decompte_premier_coup_sans_champ_expiration_contre_ia_reste_informatif` (remplace l'ancien test qui attendait à tort une estimation de 30s contre l'IA) : contre l'IA, sans `expiration`, `seconds` est `None`.
  - `test_decompte_premier_coup_sans_champ_expiration_contre_humain_estime` : la logique d'estimation (issue #321) reste intacte pour `self._opponent_is_ai = False` — exercée directement sur `LichessGame` (le lanceur actuel ne construit encore que des parties contre l'IA, voir CLAUDE.md : aucun mode humain n'existe côté `_apply_game_full()`).
  - `test_pendule_noire_figee_juste_apres_le_premier_coup_blanc`, `test_pendule_blanche_figee_avant_le_tout_premier_coup`, `test_pendules_decomptent_normalement_apres_les_deux_premiers_coups` : gel avant les deux premiers coups (les deux couleurs), reprise normale ensuite, et présence de la ligne de journal au moment de la transition (`caplog`).
  - Tests existants (`test_decompte_premier_coup_apparait_avec_expiration`, `test_decompte_premier_coup_disparait_apres_le_coup_utilisateur`) inchangés et toujours verts : une `expiration` explicite reste utilisée même contre l'IA.
- Nouveau fichier `nicsoft/tests/e2e/test_issue322_lichess_e2e.py` (Playwright, événements socket simulés, même technique que #310/#321) :
  - message informatif sans menace d'annulation et jamais rouge quand `seconds` est `None` (cas IA) ;
  - non-régression du décompte réel (menace + « environ » + rouge à 5s) quand `seconds` est fourni (cas humain/IA avec `expiration` explicite) ;
  - pendule utilisateur figée à 15:00 juste après le premier coup de l'IA (reproduit l'essai réel d'Alain) ;
  - pendule figée pour l'utilisateur aux blancs avant son tout premier coup (les deux couleurs) ;
  - affichage normal d'une pendule déjà décomptée une fois les deux premiers coups joués.
- Suite complète (`pytest nicsoft/tests/` y compris `e2e/`) : 1004 passés, 81 ignorés (hors matériel/réseau), 0 échec.

## Non testé sans le matériel

Comme pour #321 : aucune vraie partie Lichess (réseau, jeton) ni échiquier physique — tout est simulé (faux `GameClient`/transport côté Python, événements socket directement injectés côté navigateur). Impossible de confirmer ici, autrement que par la lecture du code lila et l'essai réel déjà fait par Alain, que `moves_applied >= 2` est exactement le seuil que Lichess utilise en interne pour démarrer chaque pendule — seul un nouvel essai réel (partie contre l'IA, en observant les pendules dès l'écran de jeu) peut le confirmer définitivement.

## Fichiers modifiés

- `nicsoft/modes/lichess/game.py` — `_opponent_is_ai`, `_clock_running`, gating de l'estimation du premier coup et de l'extrapolation des pendules, journal.
- `nicsoft/web/static/i18n/fr.json`, `en.json`, `de.json` — texte de `lichess.premier_coup_sans_decompte` sans menace d'annulation.
- `nicsoft/tests/test_issue311_lichess_sequencing.py` — tests mis à jour/ajoutés.
- `nicsoft/tests/e2e/test_issue322_lichess_e2e.py` — nouveau fichier de tests navigateur.
