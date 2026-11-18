# Changelog — Issue #359

## Hygiène : trois règles de piège manquantes dans docs/contexte/architecture.md

- `docs/contexte/architecture.md` : trois lignes ajoutées (règles encore
  valables, oubliées par le tri de l'ancien `historique_bugs.md` lors de
  #358) — notation SAN toujours via `san_ep()` (jamais `board.san()`
  direct), exceptions de contrôle de flux (`BackMenuExit`, `ExitNicLink`,
  `SystemExit`) jamais traitées comme un crash par un `except Exception`
  générique, tout évènement `send_event`/`emit` doit avoir un
  `socket.on`/`socket.once` correspondant dans `app.js`.
- Deux gardes de test ajoutées (analyse statique, sans navigateur ni
  matériel, sur le modèle de `test_issue303_html_escaping.py`) :
  `nicsoft/tests/test_issue359_san_ep_guard.py` et
  `nicsoft/tests/test_issue359_event_handler_guard.py`. Chacune a une
  liste blanche des violations déjà présentes (ci-dessous) et un second
  test qui échoue si la liste blanche devient périmée (entrée corrigée
  non retirée).
- Pas de garde écrite pour le piège (b) (exceptions de contrôle de flux) :
  une analyse statique fiable demanderait de distinguer un
  `except Exception` qui re-lève bien `BackMenuExit`/`ExitNicLink`/
  `SystemExit` au préalable d'un qui ne le fait pas, ce qui dépend de
  l'ordre des blocs `except` et de leur contenu — un simple `grep` sur
  `except Exception` donnerait trop de faux positifs (beaucoup de blocs
  légitimes qui n'ont jamais ces exceptions en vol à cet endroit).

### Violations connues, non corrigées (hors périmètre de cette issue)

**(a) Notation SAN — appel direct à `board.san()` au lieu de `san_ep()` :**
- `nicsoft/modes/exercices/add_ouverture.py`
- `nicsoft/modes/exercices/explore_book_import.py`
- `nicsoft/modes/exercices/explore_book_cli.py`
- `nicsoft/modes/exercices/explore_book_web.py`
- `nicsoft/modes/exercices/eco_import_import.py`
- `nicsoft/modes/exercices/import_lignes.py`
- `nicsoft/engine/review_multipv.py:292`
- `nicsoft/web/server.py:1014`
- `nicsoft/modes/lichess/puzzle_game.py:413,452,549` — seul cas touchant le
  flux de partie live (coup/solution de puzzle envoyé en direct au
  navigateur) ; les huit autres sont des outils d'import/export de livres
  d'ouvertures ou de l'analyse post-partie (hors flux live).

**(b) Exceptions de contrôle de flux avalées par un `except Exception`
générique :**
- `nicsoft/modes/humain/human.py:828` — `except Exception as exc:` autour
  de `await_move()` sans `except (BackMenuExit, ExitNicLink): raise`
  préalable ; avale notamment `ExitNicLink`. Hors périmètre de cette
  issue (fichier explicitement exclu par la tâche).
- `SystemExit` n'est en pratique jamais capturé par un `except Exception`
  (il hérite de `BaseException`, pas `Exception`) ; tous les
  `except SystemExit` du dépôt (`game_manager_modes/pedagogique.py:134`,
  `game_manager_modes/humain.py:89`, `game_manager_modes/lichess.py`
  plusieurs occurrences, `web/alchess.py:310`) sont des captures
  spécifiques et délibérées du signal `"board connection error"`
  (`driver.py`), pas une violation de la règle.

**(c) Évènement serveur→navigateur sans gestionnaire JS :**
- `exercice_turn` (`nicsoft/modes/exercices/exercices.py:1024`)
- `undo_confirmed` (`nicsoft/modes/humain/human.py:1202`)
- `undo_impossible` (`nicsoft/modes/humain/human.py:748`)
- `undo_wait_position` (`nicsoft/modes/humain/human.py:1205`)

Toutes vérifiées à nouveau dans le code actuel (et non reprises aveuglément
d'un inventaire antérieur) avant l'écriture des règles et des listes
blanches ci-dessus.

Tâche 2 de l'issue (test instable à l'ordre aléatoire de `pytest-randomly`)
abandonnée sur consigne explicite de la relance du 18/11/2026 — reportée,
non traitée dans ce commit.
