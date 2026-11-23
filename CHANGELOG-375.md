# Changelog — Issue #375

## Tests e2e Lichess intermittents (310/323/333/344/365/366) : cause réelle, pas #373/#374

### Mesure (avant toute modification)

Chaîne complète des 6 fichiers e2e Lichess (310, 323, 333, 344, 365, 366), 10 exécutions par état, dans des répertoires de travail séparés (`git worktree add`) :

| Test | cea30f5 (avant #373) | 0187229 (après #373) | master actuel (après #374) |
|---|---|---|---|
| 344::test_case_classee_masquee_contre_ia | 5/10 | 1/10 | 5/10 |
| 365::test_probleme_mode_echiquier_grise_sans_echiquier_avec_explication | 0/10 | 0/10 | 1/10 |
| 366::test_clic_manuel_echiquier_respecte_et_memorise | 1/10 | 4/10 | 2/10 |

**#373 ou #374 est-il à l'origine de l'intermittence ? Non.** Les trois tests échouent déjà, avec un taux comparable, sur `cea30f5` (dernier état avant #373) — #373/#374 n'ont fait que déplacer/dupliquer la fixture de détachement de `lichess_resumable`, sans rapport avec la cause réelle.

### Diagnostic (confirmé par instrumentation temporaire, console.log + capture Playwright, retirée avant commit)

1. **`test_case_classee_masquee_contre_ia`** (et toute dépendance à l'état `disabled` de `#cfg-lichess-rated`) : `#cfg-lichess-rated` portait l'attribut générique `data-needs-network`. `_applyLichessNetworkState()` (appelée de façon différée par une vraie réponse serveur à `config_get`/`lichess_network_check`, après l'entrée sur l'écran) réactivait alors la case sans condition (`el.disabled = !_lichessNetworkAvailable`), écrasant le grisage posé par `selectOpponentTypeLichess('ai')` dès que cette réponse réseau arrivait après le clic du test — course serveur/navigateur, exactement le défect de « second mécanisme » déjà identifié par #368 pour `btn-start-lichess`/`btn-start-lichess-puzzle`, mais pas corrigé pour `cfg-lichess-rated`.
2. **`test_probleme_mode_echiquier_grise_sans_echiquier_avec_explication`** et **`test_clic_manuel_echiquier_respecte_et_memorise`** : `_applyLichessNetworkState()` appelait `_applyBoardBadge()` en entier, qui appelle entre autres `_lichessPuzzleSyncDisplayMode()` — fonction à effet de bord (bascule automatique du mode problème « Échiquier »→« Sur l'écran » sans échiquier). Une réponse réseau tardive, sans aucun rapport avec l'échiquier, ré-exécutait donc cette bascule à un moment imprévisible et écrasait le choix manuel « Échiquier » fait par le test juste avant.

Cause établie par comparaison : le comportement racé est identique sur les trois états mesurés (cea30f5/0187229/master) — ce n'est pas un défaut des fixtures ajoutées par #373/#374, mais un vrai défaut applicatif (app.js) préexistant, révélé par ces tests.

### Correction (code applicatif — cause confirmée ci-dessus)

- `nicsoft/web/templates/index.html` : retrait de `data-needs-network` sur `#cfg-lichess-rated` (plus géré par la boucle générique).
- `nicsoft/web/static/app.js` :
  - `selectOpponentTypeLichess()` : `#cfg-lichess-rated.disabled` combine désormais type d'adversaire ET `_lichessNetworkAvailable` (côté « Contre un humain »), même pattern que `_applyLichessPuzzleBoardState()`.
  - `_applyLichessNetworkState()` : recalcule explicitement `#cfg-lichess-rated.disabled` (type d'adversaire + réseau) ; n'appelle plus `_applyBoardBadge()` en entier mais seulement les calculs qui dépendent aussi du réseau (`btn-start-lichess`, `_applyLichessPuzzleBoardState()`) — `_lichessPuzzleSyncDisplayMode()` n'est plus jamais déclenchée par une simple vérification réseau ; l'entrée sur l'écran Lichess (seul endroit qui en a réellement besoin) continue de l'appeler elle-même séparément.
- `nicsoft/tests/test_issue368_lichess_network.py` : `cfg-lichess-rated` déplacé de la liste « grisage générique » vers la liste des cas spéciaux à calcul dédié (même convention que `btn-start-lichess`/`btn-start-lichess-puzzle`) ; nouveau test `test_appjs_case_classee_combine_type_adversaire_et_reseau` vérifiant ce calcul combiné.
- `docs/contexte/lichess.md` : ligne réseau mise à jour (ajout de `cfg-lichess-rated` aux cas spéciaux, précision sur `_applyLichessNetworkState()` ne devant jamais appeler `_applyBoardBadge()` en entier).

Aucune correction de test (attente, ordre de fixture) n'était nécessaire : la cause était entièrement côté application. Point 4 de la tâche (garde défensive `if (!window...)` dans `test_issue365`) : non pertinent une fois la cause réelle corrigée — la garde existante dans les autres fichiers protège un scénario différent (fichier antérieur n'ayant pas restauré), sans rapport avec cette intermittence ; non ajoutée, pour ne pas empiler une protection sans objet démontré.

### Vérification après correction

- Chaîne complète des 6 fichiers e2e Lichess : 10 exécutions consécutives sans aucun échec, puis 5 exécutions supplémentaires sous charge CPU (6 processus `yes` sur une machine à 8 cœurs, arrêtés par PID exact) — toujours sans aucun échec (61/61 à chaque fois).
- Suite complète `-m "not hardware"` : exécutée deux fois de suite, **1771 réussis** (1770 + le nouveau test ajouté ci-dessus), **86 ignorés**, 1 désélectionné, aucun échec.

### Fichiers modifiés

- `nicsoft/web/templates/index.html`
- `nicsoft/web/static/app.js`
- `nicsoft/tests/test_issue368_lichess_network.py`
- `docs/contexte/lichess.md`
- `CHANGELOG-375.md` (ce fichier)
