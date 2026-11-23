# Changelog — Issue #373

## Tests e2e : rattachement de `lichess_resumable` dans 4 fichiers + stabilisation de #309

Suite au rapport de clôture de l'issue #372 : deux défauts restants, volontairement laissés hors périmètre à l'époque.

### 1. `lichess_resumable` jamais rattaché dans 4 fichiers e2e

Même défaut que celui corrigé par #372 pour `test_issue365_lichess_sans_echiquier_e2e.py` (et par #371 pour `config_data`) : ces fichiers détachaient le vrai gestionnaire socket.io `lichess_resumable` de la page e2e partagée (scope session, `conftest.py`) sans jamais le rattacher à la fin, laissant la page détachée pour tous les fichiers e2e suivants.

- `nicsoft/tests/e2e/test_issue310_lichess_e2e.py`
- `nicsoft/tests/e2e/test_issue323_lichess_resume_e2e.py`
- `nicsoft/tests/e2e/test_issue344_lichess_rated_e2e.py`
- `nicsoft/tests/e2e/test_issue366_puzzle_mode_autobascule_e2e.py`

Correction, identique dans les 4 fichiers : ajout d'une fixture `scope="module", autouse=True` (`_detacher_lichess_resumable_reel`) qui détache une seule fois pour tout le module et rattache (`socket.on`) à la fin — même convention que `config_data` (#365/#368/#371). Le détachement inline, répété dans la fixture par-test de chacun de ces fichiers, est supprimé (déjà fait au niveau du module).

Pour les trois fichiers qui partagent le même nom de variable globale `window.__realLichessResumableHandlers` (310, 323, 344 — via `_declencher_lichess_resumable` importé de 310), la garde `if (!window...)` déjà présente avant le correctif est conservée : elle permet de réutiliser une référence déjà capturée par un fichier antérieur qui ne l'aurait pas restaurée (seul cas restant : `test_issue333_lichess_menu_banner_e2e.py`, voir ci-dessous), au lieu de la perdre en stashant un tableau vide. `test_issue366_*` utilise sa propre variable suffixée (`...366`), indépendante de cette chaîne.

Vérifié : `grep -rn "socket.off" nicsoft/tests/e2e/` ne laisse plus aucun fichier détachant sans rattacher, à une exception documentée comme délibérée près :

- `test_issue333_lichess_menu_banner_e2e.py` documente explicitement (docstring) qu'il s'appuie sur un détachement antérieur « irréversible pour le reste de la session » et ne restaure jamais lui-même — confirmé hors périmètre par l'énoncé de cette issue, non touché. Comme il réutilise la même variable globale que 310/323/344, le prochain de ces trois fichiers qui s'exécute après lui dans la session nettoie son reliquat (restaure le vrai gestionnaire à son propre rattachement de module), donc ce choix délibéré ne casse plus la chaîne pour les fichiers suivants.
- Inspection rapide (sans chasse ouverte) des autres fichiers e2e pour un `socket.off`, une classe ou un attribut modifiés sur la page sans restauration : rien d'autre trouvé. `test_issue366_regrisage_echiquier_e2e.py` et `test_issue332_review_nav_stable_position_e2e.py` ne détachent ni ne mutent d'état partagé non restauré.

### 2. Stabilisation de `test_issue309_lichess_l2a.py::test_partie_complete_jusqu_au_mat_sans_aucun_moteur`

Diagnostic : le thread `_drive_physical_board()` du test calculait un **seul** `deadline = time.monotonic() + 5.0` avant sa boucle `for`, partagé entre **toutes** les étapes séquentielles (attente de position avant chaque coup utilisateur, attente du coup IA, attente de la réplication physique — jusqu'à 10 attentes pour cette partie). Un simple retard d'ordonnancement sous charge sur l'une des premières étapes grignotait le budget des étapes suivantes, pouvant faire échouer le test (timeout du thread principal, `game_thread.join(timeout=8.0)`) sans qu'aucune étape individuelle n'ait jamais été réellement bloquée — exactement la sensibilité au timing déjà documentée dans le test (issue #359).

Correction (test uniquement, aucun changement de comportement applicatif ni du garde #372) :

- Nouvelle fonction `_attendre(predicate, timeout=5.0, message=...)` : chaque attente dispose désormais de son propre budget de 5s, qui ne commence à courir qu'à son propre appel — plus de budget cumulé partagé entre les étapes. Lève une `AssertionError` explicite (plutôt que de sortir silencieusement de la boucle, comme avant) si une étape précise n'a jamais été atteinte.
- Le thread `_drive_physical_board()` capture cette exception (`erreurs_driver`) au lieu de la laisser remonter sans contrôle dans le thread (ce qui, avec `filterwarnings = error::pytest.PytestUnhandledThreadExceptionWarning` dans `pytest.ini`, aurait transformé toute étape manquée en erreur peu lisible) ; le thread principal la relève ensuite avec un message précis identifiant l'étape fautive.
- Budget de secours du thread principal relevé de 8.0s à 15.0s (`game_thread.join`), et du rejoin de secours après arrêt forcé de 2.0s à 5.0s — filet de sécurité borné, le vrai gain de fiabilité venant du passage aux budgets par étape ci-dessus. Le mécanisme d'arrêt forcé (`game.game_over = True`) introduit par #359 est inchangé.
- Ce que le test vérifie n'a pas changé : une partie complète (mat du berger, 4 coups utilisateur) jouée jusqu'au mat sans qu'aucun moteur d'échecs ne soit jamais importé ni appelé.

#### Chiffres (comparaison avant/après, même machine, même worktree)

- **Avant correctif**, test seul : 5/5 réussites isolées, puis 5/5 réussites avec 3 processus Python en busy-loop CPU concurrents (8 cœurs) — aucun échec reproduit avec cette charge synthétique (le défaut est une sensibilité au timing, pas une garantie d'échec systématique sous charge modeste).
- **Après correctif**, test seul : 5/5 réussites isolées, 5/5 sous charge CPU synthétique (3 processus concurrents), puis 5/5 pendant que la suite complète tournait en parallèle en arrière-plan sur la même machine (charge réelle, pas synthétique) — **15/15 exécutions consécutives réussies**, 0 échec.
- Suite complète (`pytest nicsoft/tests -m "not hardware"`) :
  - Avant correctif (référence) : `1770 passed, 86 skipped, 1 deselected in 223.23s`.
  - Après correctif : `1770 passed, 86 skipped, 1 deselected in 214.93s`.
  - Nombre de tests inchangé ; toujours verte.

### Reste éventuellement à traiter (hors périmètre de cette issue)

- `test_issue333_lichess_menu_banner_e2e.py` reste délibérément sans fixture de rattachement — choix déjà documenté dans son propre fichier, non remis en cause ici.
- Le test #309 reste sensible, en théorie, à une charge extrême qui ferait dépasser 15s à l'ensemble de la séquence (budget de secours borné, pas un événement de fin) ; non observé en pratique sur cette machine, y compris sous charge réelle de la suite complète.
