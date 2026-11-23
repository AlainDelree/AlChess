# Changelog — Issue #371

## Correctif #368 — fixtures de navigateur laissant la page partagée dans un état anormal (+ bip)

Constat : `nicsoft/tests/e2e/test_issue368_lichess_network_e2e.py` ⟶ `test_smoke_e2e.py` donnait 8 échecs (timeouts Playwright sur `#panel-playing`, `#screen-config-humain`...). Ces mêmes 8 échecs avaient déjà été observés pendant #370 et classés à tort « préexistants, sans rapport » (comparaison par `git stash` : comme le fichier fautif n'était touché ni avant ni après le diff de #370, la comparaison donnait les mêmes 8 échecs dans les deux cas, masquant la vraie cause). Ils n'avaient jamais été exécutés avant #368 : la note de clôture de #368 indiquait la suite e2e « non exécutable dans ce bac à sable ».

**Cause réelle** : `_reset_base()` (teardown de la fixture `at_config_lichess`) simulait un `board_ok` en invoquant directement le VRAI gestionnaire `socket.on("board_ok", ...)` d'`app.js` — jamais un `board_error`, contrairement à la convention déjà en place dans `test_issue365_lichess_sans_echiquier_e2e.py` et `test_issue366_regrisage_echiquier_e2e.py` (base de référence = « pas d'échiquier », cohérente avec `ALCHESS_SKIP_BOARD=1`, qui ne fait jamais émettre de `board_ok` réel côté serveur de test). Ce `board_ok` simulé laissait `_boardOk = true` après la fin du module, ce qui décoche silencieusement toutes les cases « Mode virtuel » (`_syncVirtualCheckboxes()`, app.js — `chk.checked = !_boardOk`). Le test suivant qui clique « Démarrer » envoie alors `sendAction({type:"mode", value:"pedagogique"})` **sans** `virtual:true` → `gm.set_virtual_mode(false)` → au clic sur « Démarrer la partie », `launch_pedagogique()` lance `_run_pedagogique(..., virtual=false)` → `create_board(virtual=False)` (`board_adapter.py`) → `NicLinkManager.__init__` (`driver.py`) appelle immédiatement `self.connect()` → `hid_backend.connect()`, qui tente une vraie ouverture HID du Chessnut Air — bloqué/en échec dans ce bac à sable (pas d'échiquier, d'où les timeouts constatés), mais qui **bipe réellement** (`hid_backend.py` : ouverture → `sleep(2)` → écriture de la commande de bip) sur une machine où un échiquier Chessnut est réellement branché — confirmé par un espion logiciel posé sur `hid_backend._write_to`/`_list_paths` (aucun vrai périphérique sollicité) : avec un chemin de périphérique simulé, `hid_backend.connect()` atteint bien l'écriture de la commande de bip.

Second défaut trouvé dans le même fichier, sans lien avec les 8 échecs mais relevant du même principe de remise en état : `lichess_resumable`/`lichess_network_status` étaient détachés du vrai `socket` (`socket.off`) par la fixture `at_config_lichess`, sans jamais être rattachés — contrairement à `config_data`, déjà correctement restauré par la fixture de module `_detacher_config_data_reel`.

### Correctif

- `nicsoft/tests/e2e/test_issue368_lichess_network_e2e.py` :
  - `_reset_base()` : `board_ok` → `board_error` (base de référence « pas d'échiquier », même convention que #365/#366).
  - Détachement de `lichess_resumable`/`lichess_network_status` déplacé dans la fixture de module `_detacher_config_data_reel` (renommée en esprit, nom inchangé pour limiter le diff), aux côtés de `config_data` — rattachés tous les trois à la fin du module, pour les fichiers e2e suivants qui en ont réellement besoin.
- Aucun changement de code de production : `create_board(virtual=False)`/`hid_backend.connect()` sont le comportement voulu pour un vrai utilisateur qui lance une partie réelle — le bug est entièrement dans la fuite d'état du fichier de test. Rien à corriger côté `driver.py`/`hid_backend.py` pour cette issue.

### Résultats

- `test_issue368_lichess_network_e2e.py` puis `test_smoke_e2e.py` (`-p no:randomly`, `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) :
  - Avant : 8 failed, 9 passed (ou moins selon les variations d'environnement — 1 failed + 16 passed + 1 skipped reproduit dans ce bac à sable, signature identique : timeout sur `#panel-playing`).
  - Après : 17 passed, 1 skipped (HH désactivé en mode virtuel — attendu).
- Suite e2e complète puis suite complète (`-p no:randomly`) : voir rapport de clôture pour le résultat final.

### Vérification réelle demandée à Alain

Lancer `git push` avec l'échiquier Chessnut branché et AlChess fermé : le hook pre-push doit passer (0 échec dans `test_smoke_e2e.py`), et plus aucun bip ne doit se produire pendant l'exécution de la suite e2e.
