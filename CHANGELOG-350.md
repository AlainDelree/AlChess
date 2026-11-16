# Changelog — issue #350

## Mode Pédagogique : les noms Blanc/Noir doivent suivre l'orientation de l'échiquier

Suite de #345/#348, qui avaient laissé ce défaut hors périmètre pour le mode Pédagogique (note laissée dans `CONTEXTE.md` par #345, reprise par #348) : constaté par lecture de code CCL, pas en réel par Alain.

### Diagnostic — confirmé

**`socket.on("init", ...)` (démarrage d'une partie Pédagogique, `app.js`).** Affectait inconditionnellement `player-top-name = adversaire` / `player-bottom-name = joueur` (ou l'inverse selon la couleur du joueur), sans jamais consulter `_boardFlipped` — même cause racine que les défauts déjà corrigés par #345/#348.

**`socket.on("swap_color", ...)` (changement de camp pendant une pause Pédagogique, `pedagogique.py` → `send_event("swap_color", ...)`).** Même défaut exact : toujours figé sur une convention "haut=Noir/bas=Blanc" implicite via `isWhite`, sans tenir compte de `_boardFlipped`, alors que ce changement de camp peut survenir en cours de partie, donc avec l'échiquier potentiellement déjà retourné par `#btn-flip` (partagé par tous les écrans de jeu, y compris pendant une partie Pédagogique).

**Troisième site trouvé en cherchant le même motif dans `app.js` : `ouvrirModalNulle()`, branche moteur (hors HH/Lichess).** La modale "Proposer nulle à <adversaire>" retrouvait le nom de l'adversaire via une formule figée `isWhite ? player-top-name : player-bottom-name`, sans consulter `_boardFlipped` — échiquier retourné, elle affichait à tort le nom du JOUEUR dans son propre titre.

**Quatrième site, par cohérence (hors scénario observable en pratique) : `socket.on("init_hh", ...)`.** Même défaut latent que le "init" Pédagogique ci-dessus, mais côté HH : affectait inconditionnellement `player-top-name = Noir` / `player-bottom-name = Blanc`. Non observable en pratique car `_boardFlipped` est toujours remis à `false` au retour au menu (`data.state === "menu"`) avant qu'un nouveau "init"/"init_hh" ne puisse survenir — mais la nouvelle écriture ne dépend plus de cet invariant fragile, et le correctif est trivial par réutilisation de la même fonction déjà en place.

**Résultat de partie et PGN du mode Pédagogique : vérifiés CORRECTS, non affectés.** `pedagogique.py` dérive entièrement en-têtes PGN (`White`/`Black`), gagnant et résultat (`1-0`/`0-1`) depuis `self.playing_white` (état serveur), jamais depuis une position écran — vérifié par lecture de code (lignes 326-327, 404-405, 439-442, 733-734, 899, 973, 1206, 1324 de `pedagogique.py`). Même garantie que pour #348/HH : le défaut était purement un bug d'affichage client.

**Recherche élargie (point 2 de la tâche) — aucun autre site fautif trouvé.** Le mode Labo n'affiche aucun nom de joueur haut/bas (pas de notion de camp sur cet écran). Les modes Exercices (`ex-player-top`/`ex-player-bottom`) et Retranscription (`retrans-player-top`/`retrans-player-bottom`) gèrent chacun leur propre variable d'orientation locale et cohérente (`_exBoardFlipped`, `_rtFlipped`), indépendante de `_boardFlipped` et correctement câblée de bout en bout (plateau + noms synchronisés) — pas le même défaut. Le mode Lichess, délibérément orienté "haut=adversaire / bas=utilisateur" quelle que soit la couleur jouée (#315), n'a volontairement pas été touché.

### Corrections

Réutilisation des fonctions déjà factorisées par #345 (aucune duplication de la logique d'orientation) :

- `socket.on("init", ...)` (Pédagogique) : écrit désormais les deux cases via `_reviewSetTopBottomNames(white, black)`.
- `socket.on("swap_color", ...)` (Pédagogique) : idem.
- `socket.on("init_hh", ...)` : idem, par cohérence.
- `ouvrirModalNulle()` (branche moteur) : le nom de l'adversaire vient désormais de `_reviewWhiteBlackFromTopBottom()` (lit `player-top-name`/`player-bottom-name` et reconstruit Blanc/Noir selon `_boardFlipped`), au lieu de la formule figée `isWhite ? top : bottom`.

Les lignes de coloration positionnelle (`topName.style.color = "#3a5a7a"` / `botName.style.color = "#1a2a3a"`) sont inchangées : purement liées à la position écran (haut/bas), pas au camp — déjà correctes.

### Tests

Nouveau `nicsoft/tests/e2e/test_issue350_pedagogique_orientation_e2e.py` (9 tests, Playwright, événements socket simulés via `socket.listeners(...).forEach(h => h(data))` — même procédé que #345/#348, sans échiquier physique, sans navigateur ouvert, aucun moteur) :
- noms corrects au démarrage ("init") d'une partie Pédagogique, joueur Blanc puis Noir, échiquier non retourné puis retourné ;
- `swap_color` suit l'orientation, non retourné puis retourné ;
- `ouvrirModalNulle()` affiche le bon nom d'adversaire, non retourné puis retourné ;
- non-régression de la convention par défaut de `init_hh`.

Suite complète non-`slow` rejouée sans régression après le correctif, ainsi que `test_issue345_analyse_lichess_fixes_e2e.py` et `test_issue348_hh_abandon_orientation_e2e.py` (18 tests au total avec les nouveaux, tous verts).

### Mise à jour de CONTEXTE.md

La note laissée par #345 et reprise par #348 ("Même défaut repéré ... mode Pédagogique ... non corrigé, laissé pour une future issue dédiée") est remplacée par une note "Corrigé par #350", avec la recherche élargie (labo/exercices/retranscription, rien trouvé) mentionnée comme vérifiée.
