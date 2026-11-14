# Changelog — Issue #324

# Issue #324 — Tests : un serveur lancé par les tests ne doit jamais lire, arrêter ni être bloqué par le serveur réel de l'utilisateur

## Contexte

Le push de master (8317a99, 13/11/2026 23:32) avait été refusé par le crochet de pré-push : 93 erreurs, toutes dans `nicsoft/tests/e2e`, message « Serveur AlChess non démarré ». Cause lue dans le code : depuis #320 (instance unique), tout serveur AlChess qui démarre lit le marqueur `DATA_DIR/server_instance.json` et, s'il y trouve une instance vivante, soit l'**arrête** (si au menu), soit **refuse de démarrer** (si en partie). La fixture `nicsoft/tests/e2e/conftest.py::server_url` lançait son serveur avec `ALCHESS_DIR` par défaut égal au dossier utilisateur réel (`~/NicLink`) — donc avec le **même marqueur** que le serveur réel d'Alain.

**Cause confirmée** par reproduction contrôlée (voir « Vérification » ci-dessous) : aucun vrai serveur d'Alain n'était en cours au moment de cette tâche (`~/NicLink/data/server_instance.json` absent au départ), donc la panne originale du 13/11 n'a pas pu être rejouée avec le véritable processus d'Alain — mais le mécanisme exact a été reproduit avec un second processus `python -m nicsoft.web` jouant le rôle du « vrai » serveur (voir plus bas), ce qui confirme la cause sans aucun doute raisonnable.

## 1. Isolation du marqueur d'instance en test (point 1)

Nouvelle variable d'environnement `ALCHESS_SKIP_SINGLE_INSTANCE=1` (`nicsoft/web/single_instance.py`) : quand elle vaut `"1"`, `resolve_startup()` retourne immédiatement `(True, None)` **sans lire le marqueur**, et `write_marker()`/`remove_marker()` ne font rien — aucune lecture, aucune écriture, aucune suppression, quel que soit le contenu de `DATA_DIR`. Choisie plutôt qu'un second dossier de marqueur dédié parce qu'elle protège tous les appelants de `single_instance.py` d'un seul coup, sans toucher à `config.py`/`ALCHESS_DIR` (qui reste nécessaire, inchangé, pour les données réelles — ECO, livres d'ouvertures — dont certains tests ont besoin).

La vérification normale (usage réel, sans cette variable) n'est pas modifiée.

## 2. Test de non-régression (point 2)

`nicsoft/tests/test_issue320_single_instance.py` :
- `test_skip_single_instance_ignore_le_marqueur_reel[menu|playing]` : un faux « vrai » serveur (processus lancé par le test, marqueur écrit dans le `DATA_DIR` isolé de la fixture existante `_isolated_data_dir`) reste vivant et son marqueur intact après `resolve_startup()` avec la variable active, que son état simulé (`_query_state` monkeypatché) soit `"menu"` ou `"playing"`.
- `test_skip_single_instance_write_remove_marker_sont_des_no_op` : un marqueur « réel » préexistant n'est ni écrasé par `write_marker()` ni supprimé par `remove_marker()` appelés avec la variable active.
- `test_integration_serveur_de_test_ignore_vrai_serveur_au_menu` (marqué `slow`) : **deux vrais** processus `python -m nicsoft.web` partageant le même `ALCHESS_DIR` (`tmp_path`, jamais le dossier réel) — le premier sans la variable (joue le « vrai » serveur, au menu), le second avec (joue un serveur de test). Le second démarre sans jamais arrêter le premier, qui reste actif tout du long.

Aucun arrêt par nom de programme dans ces tests ; chaque nettoyage utilise le PID exact capturé à la création du sous-processus.

## 3. Revue des autres lancements de serveur dans les tests (point 3)

Seuls trois endroits dans `nicsoft/tests/` lancent un vrai `python -m nicsoft.web` :
- `nicsoft/tests/e2e/conftest.py::server_url` — corrigé : `ALCHESS_SKIP_SINGLE_INSTANCE=1` ajouté à l'environnement du subprocess, en plus du `ALCHESS_DIR` existant (inchangé).
- `nicsoft/tests/test_issue312_server_startup.py::test_adresse_affichee_en_moins_de_10s_sortie_redirigee` — déjà isolé via `ALCHESS_DIR=tmp_path` (pas le même marqueur que le réel), protection ajoutée par défense en profondeur (`ALCHESS_SKIP_SINGLE_INSTANCE=1`) puisque ce test ne porte pas sur #320.
- `nicsoft/tests/test_issue320_single_instance.py::test_integration_deuxieme_instance_remplace_la_premiere_restee_au_menu` — **non modifié** : ce test vérifie justement le remplacement entre deux vraies instances (#320) et doit garder la vérification active ; il utilise déjà son propre `ALCHESS_DIR` isolé (`tmp_path`), donc jamais le marqueur réel non plus. Il continue de passer (vérifié ci-dessous).

## 4. Vérification (point 4)

Suite complète exécutée deux fois :
1. Sans serveur réel en cours : `python -m pytest nicsoft/tests/` → **1053 passés, 81 ignorés** (dont la suite e2e, 99 passés + 1 ignoré en l'isolant).
2. **Avec un serveur AlChess « réel » lancé pendant la vérification** : un processus `python -m nicsoft.web` a été démarré par ce traitement, avec `ALCHESS_DIR=~/NicLink` (le vrai dossier utilisateur), `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1` (comme l'exigent les consignes projet), **sans** `ALCHESS_SKIP_SINGLE_INSTANCE` — ce qui en fait, pour le code, une instance indistinguable d'un vrai serveur d'Alain au menu. Son PID a été relevé à la création. La suite complète (`python -m pytest nicsoft/tests/`, e2e compris) a ensuite tourné pendant que ce processus restait actif : **aucune erreur**, et le marqueur réel (`~/NicLink/data/server_instance.json`) ainsi que le PID de ce processus sont restés identiques avant/après — il n'a jamais été lu, arrêté ni modifié par les serveurs de test. Ce processus a ensuite été arrêté par son PID exact (jamais par nom) ; son propre nettoyage `atexit` a supprimé son marqueur normalement, dossier utilisateur réel laissé propre.

**Non vérifié** : le cas « vrai serveur en partie » n'a pas été reproduit avec un second vrai sous-processus (aurait demandé de simuler une partie complète dans ce second processus). Ce cas est cependant couvert par le test unitaire paramétré `test_skip_single_instance_ignore_le_marqueur_reel[playing]`, qui prouve que `resolve_startup()` retourne `(True, None)` **avant même de lire le marqueur ou d'interroger l'état** dès que `ALCHESS_SKIP_SINGLE_INSTANCE=1` est actif — l'état réel (menu ou en partie) ne peut donc, par construction du correctif, avoir aucune influence sur le comportement.

Aucun vrai serveur d'Alain n'était en cours avant cette tâche (vérifié : marqueur absent) ; celui utilisé pour la vérification a été créé, puis entièrement arrêté et nettoyé par ce même traitement.

## 5. CONTEXTE.md (point 5)

Phrase ajoutée à la fin du paragraphe « Instance unique (#320) » : la règle « les serveurs de test ne partagent jamais le marqueur d'instance du serveur réel », avec le nom de la variable d'environnement.

## Fichiers modifiés

- `nicsoft/web/single_instance.py` — variable `ALCHESS_SKIP_SINGLE_INSTANCE`, fonction `_skip_check()`, court-circuit dans `resolve_startup()`/`write_marker()`/`remove_marker()`.
- `nicsoft/tests/e2e/conftest.py` — `ALCHESS_SKIP_SINGLE_INSTANCE=1` dans l'environnement du serveur de test.
- `nicsoft/tests/test_issue312_server_startup.py` — même variable, par défense en profondeur.
- `nicsoft/tests/test_issue320_single_instance.py` — nouveaux tests de non-régression (point 2).
- `CONTEXTE.md` — phrase ajoutée au paragraphe #320.

## Ce qui reste à faire

Rien d'identifié pour cette issue. Point d'attention pour une tâche future : si un autre test ou script venait à lancer un vrai serveur AlChess avec `ALCHESS_DIR` pointé vers le dossier utilisateur réel, il doit reprendre le même réflexe (`ALCHESS_SKIP_SINGLE_INSTANCE=1`).
