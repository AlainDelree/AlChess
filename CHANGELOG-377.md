# Changelog — Issue #377

## Robustesse réseau en partie Lichess : horloge hors ligne et faux « coup refusé » (suite de #368)

Suite de l'étude #376 (lecture seule), qui avait confirmé deux défauts réels laissés ouverts par #368.

### Point 1 — Horloge hors ligne

Pendant une coupure réseau, le décompte des pendules continuait d'être extrapolé localement à partir de la dernière valeur confirmée par Lichess, sans jamais avertir l'utilisateur que l'adversaire (toujours connecté, lui) pouvait avoir joué et changé le trait pendant ce temps.

Solution simple retenue (celle demandée en priorité) : réutilisation pure des évènements de reconnexion déjà émis par `game.py` et déjà gérés côté navigateur (`lichess_reconnecting`/`lichess_reconnected`) — aucune nouvelle information serveur, pas de champ « non confirmé » dans le message d'horloge (solution complémentaire non nécessaire ici).

- `nicsoft/web/static/app.js` : nouvelle fonction `_lichessSetClocksUnreliable(active)` — pose/retire la classe CSS `clock-unreliable` et une infobulle (`title`) sur `#clock-top`/`#clock-bottom`. Appelée `true` par `socket.on("lichess_reconnecting")`, `false` par `socket.on("lichess_reconnected")`. Appelée aussi `false` depuis `_lichessHideStatusBanners()` (jamais de marquage bloqué) — cette fonction est déjà invoquée par les trois chemins qui doivent garantir la disparition : retour au menu en pleine coupure (`data.state === "menu"`), resynchronisation par un nouveau `gameFull` (`socket.on("lichess_init")`), et fin de partie (`socket.on("game_over")` côté Lichess).
- `nicsoft/web/static/css/main.css` : règle `.lichess-clock.clock-unreliable` (hachures grises semi-transparentes par-dessus la couleur de fond habituelle, `is-turn`/`is-low` restent visibles dessous).
- `nicsoft/web/static/i18n/{fr,en,de}.json` : nouvelle clé `lichess.horloge_non_fiable` (infobulle), ajoutée simultanément dans les trois fichiers (parité vérifiée : 861 clés chacun).
- `nicsoft/tests/e2e/test_issue377_lichess_clock_unreliable_e2e.py` (nouveau) : marquage absent par défaut ; posé par `lichess_reconnecting` puis retiré par `lichess_reconnected` (classe + infobulle non vide) ; retiré au retour menu en pleine coupure (sans `lichess_reconnected` reçu) ; retiré à la resynchronisation par un nouveau `lichess_init` ; retiré en fin de partie (`game_over`). 10 exécutions consécutives sans échec.
- `docs/contexte/lichess.md` mis à jour (section « Réseau et robustesse »).

### Vérification

- `nicsoft/tests/e2e/test_issue377_lichess_clock_unreliable_e2e.py` : 5/5 passés, 10 exécutions consécutives sans échec.
- Suite complète `-m "not hardware"` : verte (voir le commit suivant, point 2, pour le décompte final après les deux points).

### À vérifier à la main (hors périmètre de cette tâche automatisée — jamais de vraie partie Lichess pendant le développement)

Avec une vraie partie Lichess et une coupure réseau réelle en cours de partie :
1. Au début de la coupure (`lichess_reconnecting` reçu) : les deux pendules doivent se griser/hachurer visuellement, avec une infobulle au survol.
2. Au retour du réseau (`lichess_reconnected`) : le marquage doit disparaître et les pendules reprendre leur affichage normal (couleurs `is-turn`/`is-low` inchangées).
