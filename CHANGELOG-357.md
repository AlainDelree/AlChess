# Changelog — issue #357

## Garde de taille/index pour CONTEXTE.md + tri des documents périmés signalés par #356

### Garde ajoutée

`nicsoft/tests/test_issue357_contexte_guard.py` (3 tests, lecture de fichiers du dépôt uniquement, aucun réseau/matériel) : `CONTEXTE.md` ≤ 3700 caractères (`wc -m`) ; chaque fichier de `docs/contexte/` est cité dans l'index de `CONTEXTE.md` ; chaque fichier cité dans l'index existe sur disque.

### CONTEXTE.md

Ajout de 2 règles dans l'en-tête : limite de 3700 caractères (`wc -m`, test dédié) et `TACHES.md` privé/gitignoré (jamais modifié) — cette dernière avait disparu de la restructuration #356. Reformulations pour tenir sous la limite (aucune règle perdue) : section Règles condensée, « Fichiers de référence non déplacés » → « Fichiers de référence », « nettement en avance » → « en avance », ligne d'index `historique_bugs.md` mise à jour (voir ci-dessous). Taille finale : 3678 caractères (`wc -m`).

### docs/contexte/architecture.md

2 règles ajoutées, issues du tri de `historique_bugs.md` (pièges encore généralisables) : réinitialiser toute variable d'état résiduelle (JS/Python) au retour menu avant un nouveau lancement de mode ; vérifier l'équilibre des balises après modification de `index.html` (deux bugs passés par balise fermante manquante).

### docs/contexte/historique_bugs.md

BUG-001 à BUG-010 : vérifiés dans le code actuel, toutes les corrections tiennent toujours (preuves : `#screen-pos-init` hors de `#screen-game` dans `index.html`, aucun `window.confirm()` dans `app.js`, `_gameSource` réinitialisé au retour menu, `labo_copy_start` efface `labo-last-move`, quirk usbhid et mutex USB/threads LED daemon déjà documentés dans `echiquier_usb_led.md`, handler manquant déjà couvert par `architecture.md`). Récit supprimé — pièges encore vivants déplacés en règles (voir ci-dessus). BUG-011 laissé tel quel (voir « Laissé pour décision d'Alain »). Section « Bugs résolus — mai 2026 (lot 2) » : hors périmètre de cette tâche (l'issue ne visait que BUG-001 à BUG-011), non touchée.

### Documents supprimés (`git rm`, preuve de péremption)

- `ETAT_PROJET.md` : snapshot daté 2026-05-22 (6 mois), non cité par `CONTEXTE.md` ni la table « Fichiers de suivi » de `CLAUDE.md`/`SPECIFICATIONS.md`. Chiffres massivement faux aujourd'hui (`app.js` 5716→9302 lignes, `index.html` 1447→2220, `main.css` 642→1828, i18n 606→847 clés, `test_app_state.py` annoncé à part des tests E2E alors que 203 tests E2E existent désormais) ; dossiers/fichiers listés en §7 « à nettoyer » tous déjà absents du disque (`nicsoft/test/`, `nl_bluetooth/`, `TRAVAIL_EN_COURS/`, `Lenteur/`, `build/`, `src/`, etc.).
- `CORRECTION_TRADUCTION.md` : note de travail i18n sans date, non citée ailleurs. Les 4 points relevés sont corrigés dans le code actuel (`menu.btn.reconnect`/`config.pause.*`/`game.btn.changer_couleur` ont leurs clés fr/en/de ; CSS dédiée `#screen-outils-exercices` ajoutée depuis).

### Non modifiés — laissé pour décision d'Alain

- `historique_bugs.md`, BUG-011 : son récit attribue l'ancien blocage à `sys.exit(0)` dans un thread de jeu qui « tuait tout le processus Flask ». Or `nicsoft/modes/humain/human.py` utilise encore aujourd'hui `sys.exit(0)` pour son propre retour menu (ligne ~1085), jamais converti en `BackMenuExit`. Sans pouvoir relancer un serveur réel (hors périmètre de cette tâche, pas de matériel), impossible de trancher si ce `sys.exit(0)`-là est sans danger (vrai `threading.Thread`, `async_mode="threading"` dans `server.py`) ou si le risque décrit est toujours vivant dans `human.py`. Entrée laissée intacte, signalée ici pour vérification/décision.
- `SPECIFICATIONS.md` : document de spécification, non supprimé en bloc. Corrigé uniquement ce qui était clairement faux (extension C++ `_niclink.so` → `hid_backend.py`, compteurs i18n 515→847, tests E2E 42→203 — `test_app_state.py` à 25 tests restait exact, vérifié par `pytest --collect-only`). Lacune non corrigée (ajout de contenu, pas correction d'erreur, hors périmètre) : section « 5. Modes de fonctionnement » ne décrit toujours pas le mode Lichess (`modes/lichess/`), pourtant présent dans `CONTEXTE.md`/`CLAUDE.md` et dans le reste de la base — à compléter dans une tâche dédiée.
- `TEST_RESULTATS.md` : laissé intact. Une seule entrée (2026-05-02), mais c'est un journal daté par nature (comme `CHANGELOG.md`) — son unique entrée ancienne n'est pas une erreur, juste une absence de mise à jour récente ; le mécanisme reste référencé et valide dans `CLAUDE.md`/`SPECIFICATIONS.md`.

### Suite de tests

`python -m pytest nicsoft/tests -m "not hardware"` rejouée après toutes les modifications ci-dessus — verte, nouveau test de garde inclus.
