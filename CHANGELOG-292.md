# Changelog — Issue #292

## Échiquier physique inutilisable après un abandon en « pièces mal placées » : fils de la partie précédente encore actifs et connexion USB non protégée

### Mécanisme établi
- **`nicsoft/core/game_manager_modes/pedagogique.py`** : le nettoyage de fin
  de partie (`finally` de `_run_pedagogique`) n'appelait jamais
  `nl_inst.disconnect()` (contrairement à `exercices.py`/`explorer.py`) — il
  se contentait d'éteindre les LEDs. Le fil `fen_reader` de l'ancien
  `NicLinkManager` restait donc vivant indéfiniment, continuant d'appeler
  `hid_backend.get_fen()` en boucle, périphérique USB jamais libéré.
- **`nicsoft/niclink/hid_backend.py`** : `connect()` et `get_fen()`
  relisaient la variable partagée `_dev` (module-level) à chaque itération,
  sans verrou. Si le fil `fen_reader` orphelin (point précédent) essuyait une
  erreur de lecture et remettait `_dev` à `None` pendant qu'une nouvelle
  partie établissait sa connexion, l'itération suivante de la boucle
  d'attente du premier FEN dans `connect()` levait
  `AttributeError: 'NoneType' object has no attribute 'read'` — exactement
  l'erreur observée par l'utilisateur, immédiatement suivie du petit
  indicateur « No board » et du basculement silencieux en mode virtuel.
- Les boucles d'attente de position déjà en place pendant une partie
  (surveillance « cases incorrectes » dans `handle_human_turn`, et sa
  jumelle `_wait_for_fish_move_on_board` pour le tour du moteur, toutes deux
  dans `nicsoft/modes/pedagogique/pedagogique.py` ; `_wait_position` dans
  `nicsoft/modes/exercices/exercices.py`) respectaient **déjà** correctement
  `kill_switch`/`self._running`, y compris quand l'échiquier physique affiche
  une position qui ne correspondra jamais à celle attendue — vérifié par
  lecture et par test (`test_await_move_respecte_kill_switch_meme_position_jamais_correcte`).
  Aucune correction nécessaire sur ce point précis.
- Non vérifié avec un échiquier physique réel (seulement avec un faux module
  hidapi) : le comportement exact de `hidapi`/`hidraw` sous Linux quand deux
  handles sont ouverts simultanément sur le même périphérique (scénario qui
  ne devrait plus se produire après ce correctif, mais qui n'a pu être induit
  que logiciellement).

### Corrections
- **`nicsoft/core/game_manager_modes/pedagogique.py`** : le `finally` de
  `_run_pedagogique` appelle désormais `nl_inst.disconnect()` (comme
  `exercices.py`), arrêtant le fil `fen_reader` et libérant le périphérique
  avant qu'une prochaine partie n'en crée un nouveau.
- **`nicsoft/niclink/hid_backend.py`** :
  - `connect()` travaille sur une référence locale au périphérique du début
    à la fin, et ne publie la connexion dans l'état partagé (`_dev`,
    `_current_fen`, `_connected_product_id`, `_connected`) qu'une fois établie
    avec succès, sous un nouveau verrou `_state_lock`. Un fil concurrent ne
    peut donc plus jamais le faire échouer par une erreur d'attribut.
  - `get_fen()` capture `_dev` sous verrou puis lit hors verrou (l'I/O USB
    peut bloquer jusqu'à 50ms) ; en cas d'échec de lecture, l'état partagé
    n'est remis à zéro que s'il référence encore le même périphérique
    (`_reset_state_if_current`) — une erreur tardive d'une session abandonnée
    ne peut plus écraser une connexion plus récente.
  - `disconnect()` récupère puis efface la référence partagée sous verrou
    avant de faire l'I/O de fermeture sur la référence locale.
  - Si la connexion est perdue pendant l'établissement (ouverture ou
    handshake), `connect()` referme le périphérique, remet l'état du module
    à zéro (`_reset_state()`, nouvelle fonction) et lève `RuntimeError` — la
    même exception que pour un plateau introuvable, que
    `NicLinkManager.__init__` sait déjà convertir en sortie propre affichée
    comme « échiquier non détecté ». Un nouvel essai (y compris via le bouton
    de reconnexion) repart donc d'un état propre, sans redémarrer l'application.
  - `_write()` déléguée à `_write_to(dev, data)` qui opère sur une référence
    locale, réutilisée en interne par `connect()` pendant le handshake.
  - `nicsoft/niclink/driver.py` non modifié : ses boucles d'attente de
    position/coup respectaient déjà `kill_switch` (voir ci-dessus).
- **Tests** (`nicsoft/tests/test_issue292_board_cleanup.py`, nouveau, aucun
  matériel ni réseau — faux module hidapi) :
  - `disconnect()` arrête bien le fil `fen_reader` et libère le périphérique.
  - le nettoyage de `_run_pedagogique` appelle bien `disconnect()` sur
    l'ancien échiquier, quel que soit le chemin de sortie.
  - `await_move()` respecte `kill_switch` même avec une position physique
    qui ne correspondra jamais à celle attendue par la partie.
  - `connect()` ne lève plus `AttributeError` même si une mutation
    concurrente de `_dev` survient exactement au moment de la lecture
    (reproduction déterministe), ni avec un vrai fil concurrent répété
    (reproduction best-effort, dépendante de l'ordonnanceur).
  - une perte de connexion pendant l'établissement lève `RuntimeError`
    (jamais `AttributeError`), et `NicLinkManager.__init__` la convertit
    bien en sortie propre « board connection error ».
  - après un échec de connexion, un nouvel essai réussit sans redémarrage.
- Suite complète (`pytest nicsoft/tests/`, hors tests marqués `hardware`) :
  427 passés, 74 ignorés (hardware/réseau), aucun échec.
- Non touchés, comme demandé : affichage de l'état de l'échiquier côté IHM
  (« No board », bascule virtuelle), `.audit.json`, aucune suppression
  d'outil de sécurité.

### Observation hors périmètre (non corrigée ici)
`nicsoft/core/game_manager_modes/humain.py` (mode Humain vs Humain) et
`nicsoft/core/game_manager_modes/labo.py`/`labo_libre.py` présentent le même
motif que le bug initial de `pedagogique.py` (pas d'appel à
`nl_inst.disconnect()` en fin de session). Ces modes ne faisaient pas partie
du scénario de reproduction de cette issue (Pédagogique + Exercices) et n'ont
donc pas été modifiés, pour respecter le périmètre de la tâche — à signaler
pour une issue de suivi si Alain le souhaite.

### Vérifications manuelles suggérées avec l'échiquier physique
1. **Pédagogique** : lancer une partie contre Stockfish, jouer un coup
   illégal ou déplacer des pièces pour déclencher l'avertissement « cases
   incorrectes, remettez l'échiquier en ordre » à répétition, puis remettre
   l'échiquier en position de départ (différente de la position attendue par
   la partie) et cliquer « Abandonner ». Revenir au menu puis cliquer
   « Démarrer » à nouveau pour le même mode : la partie doit démarrer
   normalement avec le même échiquier, sans fenêtre d'erreur ni indicateur
   « No board », sans redémarrer l'application.
2. **Exercices** : même scénario (mal placer les pièces, déclencher
   l'avertissement, abandonner, relancer un exercice) : doit fonctionner de
   la même façon.
3. **Débranchement physique en cours de partie** : débrancher l'échiquier
   USB pendant une partie, vérifier le message de déconnexion, rebrancher et
   utiliser le bouton de reconnexion du menu : la partie/le plateau doit
   redevenir utilisable sans redémarrer l'application.
