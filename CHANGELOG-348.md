# Changelog — issue #348

## Humain contre Humain : la fenêtre d'abandon doit tenir compte de l'orientation de l'échiquier

Suite de #345, qui avait laissé ce défaut hors périmètre (noté dans `CONTEXTE.md`) : constaté par lecture de code CCL, pas en réel par Alain.

### Diagnostic

**Modale d'abandon HH (`ouvrirModalAbandonner()`, branche `_gameMode === "humain"`, `app.js`).** Affectait inconditionnellement `nomBlanc = player-bottom-name` / `nomNoir = player-top-name`, sans jamais consulter `_boardFlipped` — même cause racine que le défaut n°3 de #345 (`parsePgn()`), mais sur un écran différent (modale d'abandon de l'écran de jeu, pas écran d'analyse). Échiquier retourné (Noirs en bas), le bouton « Blancs abandonnent » affichait le nom du joueur Noir, et inversement.

**Deuxième site trouvé en cherchant le même motif dans `app.js` : `socket.on("swap_color_hh")`** (changement de camp demandé pendant une pause HH, `human.py::_handle_turn_pause` → `send_event("swap_color_hh", ...)`). Même défaut exact : affectait toujours `player-top-name = Noir` / `player-bottom-name = Blanc`, sans tenir compte de `_boardFlipped`, alors que ce changement de camp peut survenir en cours de partie, donc avec l'échiquier potentiellement déjà retourné par le bouton ⇅ (partagé par tous les écrans de jeu, y compris pendant une partie HH).

**Résultat de partie (1-0/0-1) et PGN : vérifiés CORRECTS, non affectés.** Les boutons HTML de la modale (`templates/index.html`) envoient `sendAction({type:'abandonner', couleur:'blanc'})` / `couleur:'noir'` — valeur FIXE, indépendante du texte affiché sur le bouton. Côté serveur, `human.py::_traiter_abandon()` décide gagnant/résultat/PGN uniquement depuis cette `couleur` (jamais depuis une position écran) : `couleur == "blanc"` → `0-1`/gagnant Noir, `couleur == "noir"` → `1-0`/gagnant Blanc — toujours corrects, orientation ou non. Le défaut était donc purement un bug d'affichage client (point 1 de la tâche confirmé pour le nom affiché, pas pour le résultat/PGN).

**Autres sites de même motif, trouvés et non corrigés (hors mode HH, hors périmètre #348)** : `socket.on("init", ...)` et `socket.on("swap_color", ...)` (mode **Pédagogique**, vs moteur) affectent eux aussi `player-top-name`/`player-bottom-name` sans regarder `_boardFlipped`. Observable seulement si `#btn-flip` (bouton partagé par tous les écrans de jeu) est utilisé PENDANT une partie Pédagogique — pas vérifié en réel. Laissé pour une future issue dédiée au mode Pédagogique (consigne de la tâche : ne pas toucher aux modes contre moteur hors défaut clairement fautif et dans le périmètre demandé). Le mode Lichess, lui, est délibérément orienté « haut=adversaire / bas=utilisateur » quelle que soit la couleur jouée (issue #315) — ce n'est pas le même défaut, non concerné.

### Corrections

Dans les deux cas, réutilisation des fonctions déjà factorisées par #345 (aucune duplication de la logique d'orientation) :

- `ouvrirModalAbandonner()` : `nomBlanc`/`nomNoir` viennent désormais de `_reviewWhiteBlackFromTopBottom()` (lit `player-top-name`/`player-bottom-name` et reconstruit Blanc/Noir selon `_boardFlipped`).
- `socket.on("swap_color_hh")` : écrit désormais les deux cases via `_reviewSetTopBottomNames(white, black)` (au lieu de l'affectation inconditionnelle `top=Noir/bottom=Blanc`).

### Tests

Nouveau `nicsoft/tests/e2e/test_issue348_hh_abandon_orientation_e2e.py` (5 tests, Playwright, événements socket simulés via `socket.listeners(...).forEach(h => h(data))` — même procédé que #342/#345, sans échiquier physique, sans navigateur ouvert (`ALCHESS_SKIP_BOARD=1`/`BROWSER=/bin/true` déjà posés par `conftest.py`), aucun moteur) :
- noms corrects sur les boutons de la modale d'abandon HH, échiquier non retourné puis retourné (les deux camps) ;
- non-régression : les boutons de la modale envoient toujours `couleur:'blanc'`/`couleur:'noir'` fixe, quelle que soit l'orientation (le résultat de partie ne dépend jamais de l'affichage) ;
- `swap_color_hh` suit l'orientation, non retourné puis retourné.

Vérifié que ces tests détectent bien la régression : les 2 tests « échiquier retourné » échouent si on revient à l'ancien code (`git stash` du seul `app.js` pendant la vérification, confirmé puis annulé) — 3 passent déjà avant le correctif (non-régression/cas non retourné), 2 échouent avant et passent après.

Suite complète non-`slow` (1305 tests) + `test_issue345_analyse_lichess_fixes_e2e.py` (4 tests) rejouées sans régression après le correctif.

### Mise à jour de CONTEXTE.md

La note laissée par #345 (« Non corrigé, hors périmètre ... `ouvrirModalAbandonner()` ... ») est remplacée par une note « Corrigé par #348 », avec la découverte du mode Pédagogique ajoutée comme point ouvert.
