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

### Point 2 — Faux « coup refusé »

Si une requête de coup était bien acceptée par Lichess mais que seule la réponse HTTP se perdait (coupure juste après l'envoi), `_submit_move` renvoyait le même coup ; Lichess refusait ce doublon avec le message ambigu HTTP 400 « Not your turn, or game already over ». `_handle_move_rejected` relisait déjà le flux (`_drain_pending_stream_events`, issue #347) mais seulement pour détecter une fin de partie — si la partie continuait (adversaire pas encore rejoué), un « coup refusé » s'affichait quand même, alors que le premier envoi avait réussi. Documenté comme « gap connu » par `test_issue368_lichess_game_network_loss.py` avant cette correction.

- `nicsoft/modes/lichess/game.py` : nouvelle méthode `LichessGame._move_already_applied(uci)` — vrai si `uci` est déjà le dernier coup de `self.board.move_stack` ET que son auteur (`self._last_move_mover_color`) est l'utilisateur. `_handle_move_rejected` teste cette condition juste après la relecture bornée du flux, avant le test « partie déjà terminée » existant : si vrai, retour silencieux (aucun `lichess_move_refused`, aucune remise en place physique demandée). Le renvoi du coup lui-même est inchangé — Lichess refuse toujours le doublon, aucun risque de le rejouer.
- `nicsoft/tests/test_issue368_lichess_game_network_loss.py` : l'ancien test « gap connu »
  (`test_double_envoi_apres_reponse_perdue_produit_un_faux_coup_refuse_gap_connu`) est remplacé par deux tests — `test_double_envoi_apres_reponse_perdue_confirmee_pendant_la_relecture_najamais_de_faux_refus` (le flux confirme le coup pendant la relecture : aucun message d'erreur, coup bien présent dans `self.board.move_stack`) et `test_vrai_refus_apres_relecture_sans_confirmation_affiche_toujours_lerreur` (aucune confirmation ni fin de partie : message d'erreur toujours affiché, non-régression). En-tête du fichier mis à jour (le défaut n'est plus un gap connu, il est corrigé).

### Contraintes respectées

- Fair-play : `test_issue333_lichess_no_engine.py` (test statique AST) toujours vert — aucun import de moteur/livre/explorateur ajouté dans `modes/lichess/*`.
- Logique de réclamation victoire/nulle : non touchée.
- `configs/*.conf`, `.audit.json`, `driver.py`, `TACHES.md` : non touchés.
- `docs/contexte/lichess.md` mis à jour (section « Réseau et robustesse ») ; `CONTEXTE.md` inchangé, toujours sous 3700 caractères (3535).

### Vérification

- `nicsoft/tests/test_issue368_lichess_game_network_loss.py` : 6/6 passés.
- `nicsoft/tests/e2e/test_issue377_lichess_clock_unreliable_e2e.py` : 5/5 passés, 10 exécutions consécutives sans échec.
- Suite complète `-m "not hardware"` : exécutée deux fois de suite, **1778 réussis** (1771 + 7 nouveaux : 2 remplaçant le test « gap connu » + 5 e2e), **86 ignorés**, 1 désélectionné, aucun échec les deux fois.

### À vérifier à la main (hors périmètre de cette tâche automatisée — jamais de vraie partie Lichess pendant le développement)

Avec une vraie partie Lichess et une coupure réseau réelle en cours de partie :
1. Au début de la coupure (`lichess_reconnecting` reçu) : les deux pendules doivent se griser/hachurer visuellement, avec une infobulle au survol.
2. Au retour du réseau (`lichess_reconnected`) : le marquage doit disparaître et les pendules reprendre leur affichage normal (couleurs `is-turn`/`is-low` inchangées).
3. Un coup physique joué juste avant une coupure, dont seule la réponse HTTP se perd : ne doit plus jamais afficher « coup refusé » si Lichess l'avait en fait accepté (vérifiable via l'historique Lichess de la partie, qui doit contenir ce coup une seule fois).
