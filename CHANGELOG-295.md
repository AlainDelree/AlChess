# Changelog — Issue #295

## Suite #292 : tests de régression (périphérique USB à ouverture exclusive, fausse alerte de déconnexion) et fermeture de l'échiquier à la fin de tous les modes

### Vérification des correctifs manuels (défauts 1 et 2)
- Les deux correctifs manuels appliqués par Alain dans
  `nicsoft/niclink/hid_backend.py` avant cette issue étaient déjà présents
  et conformes :
  - **Défaut 1** (`connect()`) : l'ancien handle `_dev` est retiré de la
    variable partagée sous `_state_lock`, l'état `_connected` remis à
    `False`, puis fermé hors verrou (`(OSError, IOError, ValueError)`,
    trace `debug`) avant l'ouverture du nouveau — le périphérique
    n'accepte qu'un seul accès HID à la fois.
  - **Défaut 2** (`check_physically_present()`) : plus de court-circuit sur
    `_connected` — la fonction interroge toujours `hid.enumerate()`.
  Aucune modification de `hid_backend.py` n'a donc été nécessaire.

### Faux module USB des tests rendu réaliste
- **`nicsoft/tests/test_issue292_board_cleanup.py`** : `_FakeDevice`/
  `_FakeHidModule` simulent maintenant l'ouverture exclusive du Chessnut
  Air — un second `open_path()` alors qu'un autre accès du même module est
  ouvert lève `OSError('open failed')`, comme le périphérique réel. Tous
  les tests existants de ce fichier (issue #292) ont été vérifiés
  compatibles avec cette contrainte (un seul open actif à la fois dans
  chacun d'eux) et restent verts.
- **`nicsoft/tests/test_issue295_usb_exclusive_access.py`** (nouveau) :
  - (a) deux connexions successives de `hid_backend`, la première jamais
    fermée explicitement, réussissent toutes les deux ;
  - (b) deux créations successives de `NicLinkManager` (vérification du
    démarrage + partie) réussissent toutes les deux ;
  - (c) contrôle négatif : sans fermeture entre deux `open_path()`, le faux
    module lève bien `OSError('open failed')` — preuve que (a)/(b)
    détecteraient la régression du défaut 1 si le correctif disparaissait ;
  - (e) `check_physically_present()` reste vrai après une fermeture
    volontaire tant que le plateau est énuméré, faux s'il disparaît
    vraiment ;
  - (f) `_board_menu_watcher` (`nicsoft/web/alchess.py`) n'envoie aucun
    `board_error` après une fermeture volontaire (plateau toujours énuméré),
    et en envoie un à la disparition réelle.
  - (d) — accès fermé par un autre fil pendant `connect()`, sans
    `AttributeError` — déjà couvert par les tests existants de l'issue
    #292 (`test_connect_survit_a_une_mutation_concurrente_de_dev` et
    `test_connect_concurrent_avec_fil_orphelin_reel_ne_leve_jamais_attributeerror`),
    reconfirmés compatibles avec le faux module désormais exclusif.

### Fermeture de l'échiquier en fin de session — Humain, Labo, Labo libre
- **`nicsoft/core/game_manager_modes/humain.py`** (`_run_humain`) et
  **`labo_libre.py`** (`_run_labo_libre`) : ajout, dans le `finally`, de
  `nl_inst.disconnect()` après `turn_off_all_leds()` — exactement le même
  motif et le même traitement d'erreur (`except Exception`, `logger.warning`)
  que le mode Pédagogique.
- **`nicsoft/core/game_manager_modes/labo_session.py`** (`_run_labo_session`) :
  ajout de `nl.disconnect()` dans les deux points de sortie de session
  (action `back_menu`, et fin de la boucle quand l'état change par un autre
  chemin), après `session.quit()`.
- **`nicsoft/core/game_manager_modes/labo.py`** (`_poll_board_fen_labo`) :
  le `finally` ferme désormais pleinement la connexion (`nl.disconnect()`)
  au lieu de seulement arrêter le fil `fen_reader` — filet de sécurité pour
  le cas où la session ne démarre jamais (ex. `_make_labo_session` échoue
  avant que `_run_labo_session` n'ait pu fermer la connexion).
- Aucun changement de comportement visible à l'écran : ces appels
  n'envoient aucun événement à l'IHM.
- **`nicsoft/tests/test_issue295_mode_cleanup.py`** (nouveau) : un test par
  mode (Humain, Labo libre, Labo) vérifiant `disconnect()` appelé en fin de
  session normale, et un test par mode vérifiant qu'il l'est aussi sur un
  abandon (exception pendant la partie/session, ou sortie de boucle par un
  chemin autre que l'action explicite de retour menu) — six tests mode +
  un test du filet de sécurité `_poll_board_fen_labo`.

### Revue des autres sites d'ouverture USB (point 4)
Relu chaque site créant une connexion USB/un `NicLinkManager` alors qu'une
connexion peut déjà exister :
- **Vérification du démarrage** (`nicsoft/web/alchess.py:_check_board_at_startup`) :
  crée un `NicLinkManager` et laisse volontairement la connexion ouverte
  (seul le fil `fen_reader` est arrêté) — c'est l'usage normal documenté.
  Protégé par le correctif défaut 1 : toute ouverture suivante fermera cet
  handle avant d'en ouvrir un nouveau.
- **Bouton de reconnexion** (`nicsoft/web/server.py:_reconnect_board`) :
  deux branches — réutilisation de `game_manager._nl_inst_ref` existant
  (`nl_inst.connect()`) ou `create_board()` de secours si aucune session
  active. Les deux passent par `hid_backend.connect()`, donc par le
  correctif défaut 1 — aucun conflit possible avec une connexion déjà
  ouverte (démarrage ou session précédente mal fermée).
- **Lancement de chaque mode** (Pédagogique, Humain, Exercices, Drill,
  Explorateur, Labo, Labo libre) : tous appellent `create_board()` →
  `hid_backend.connect()` au démarrage de leur session — protégés de la
  même façon, génériquement, par le correctif défaut 1 (fermeture de
  l'ancien handle avant la nouvelle ouverture), quel que soit l'appelant
  qui détenait la connexion précédente.
- **Reprise après perte de connexion** : couverte par le bouton de
  reconnexion ci-dessus (seul point d'entrée de reprise manuelle).
- **Conclusion** : la nouvelle règle d'un seul accès à la fois ne peut
  gêner aucun de ces sites — le correctif défaut 1, dans `connect()`, est
  générique et couvre tous les appelants. Le seul risque concret restant
  (fil `fen_reader` orphelin faute de `disconnect()` en fin de session)
  était celui des modes Humain/Labo/Labo libre, corrigé ci-dessus.
- **Statut `ok` de l'échiquier** (`nicsoft/web/server._board_status`) :
  vérifié qu'il n'est jamais modifié que par `send_event("board_ok"/
  "board_error", ...)` (sous `_board_status_lock`) — jamais par
  `hid_backend.disconnect()`, qui ne notifie rien à l'IHM. Une fermeture
  volontaire ne peut donc jamais, par elle-même, repasser ce statut à
  « erreur ».

### Tests
`python -m pytest nicsoft/tests/ -m "not hardware"` : 441 passed, 75
skipped (skips préexistants, sans rapport avec cette issue — modules sans
app_state_proxy, tests conditionnels e2e).
