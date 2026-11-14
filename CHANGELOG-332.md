# Changelog — Issue #332

## Écran d'analyse après partie : la navigation (Précédent/Suivant) ne se déplace plus selon l'état du bouton « Voir le meilleur coup »

### Cause

Sur l'écran d'analyse après partie (`panel-gameover`, partagé par tous les
modes — pédagogique, humain contre humain, retranscription, Lichess),
`_updateReviewBestMoveBtn()` (`app.js`) faisait
`row.style.display = hasBest ? "block" : "none"` sur `#review-best-move-row`.
Ce bloc est positionné juste au-dessus de la ligne Précédent/Suivant, dans
le même flux de mise en page (`card-nav-save`) : le retirer/remettre selon
que le meilleur coup du moteur diffère ou non du coup joué changeait la
hauteur du panneau et poussait le bouton « Suivant » vers le haut ou le bas
à chaque navigation — exactement le symptôme décrit par Alain (clic à côté
du bouton en lisant l'échiquier, sans regarder le panneau).

### Correction

- `nicsoft/web/templates/index.html` : `#review-best-move-row` n'a plus
  `style="display:none"` à l'initialisation — la ligne (et son bouton) est
  désormais toujours présente dans le flux, place réservée en permanence.
  Le bouton `#btn-review-best` démarre `disabled` (grisé), avec
  `data-i18n="game.btn.meilleur"` ajouté par cohérence (clé déjà existante
  dans `fr/en/de.json`, utilisée par l'équivalent du panneau pause).
- `nicsoft/web/static/app.js::_updateReviewBestMoveBtn()` : ne touche plus
  `row.style.display`. Le bouton `#btn-review-best` est désactivé/grisé
  (`disabled`, `opacity`, `pointerEvents`) quand il n'y a pas de meilleur
  coup différent à montrer pour le coup courant — même motif que
  `_setNavControls()` et que `#btn-pause-meilleur` (panneau pause), qui
  suivaient déjà ce principe et n'étaient pas concernés par le bug.
- Comportement inchangé : le bouton garde sa fonction
  (`data-action="review_best_move"`), son texte, et son état logique
  (actif seulement si le moteur a un meilleur coup différent du coup joué
  pour la position courante).

### Autres éléments vérifiés (aucun déplacement constaté)

- `#review-move-san` (coup affiché, ex. « Nf3 ») : a déjà `min-height:2rem`
  en CSS — hauteur stable.
- `#review-best-move-san` (texte du meilleur coup, affiché seulement après
  clic sur « Voir le meilleur coup ») : reste masqué par défaut et remis à
  zéro à chaque navigation — ne varie jamais « d'un coup à l'autre » au
  sens du scénario de l'issue (seulement pendant la lecture du coup
  courant, après un clic explicite, pas en cliquant Suivant/Précédent).
- `#btn-rv-sequence` (bouton séquence punitive) : son apparition/disparition
  est dans une autre carte, plus bas dans le panneau, sans élément en
  dessous dont la position doive rester fixe — pas concerné.
- Panneau pause (`panel-pause`) : `#btn-pause-meilleur` était déjà toujours
  visible (disabled/opacity, jamais retiré du flux) — motif déjà correct,
  rien à corriger. `#pause-feedback-box` ne change que lors de l'entrée en
  pause, jamais pendant la navigation Précédent/Suivant interne au
  panneau — pas concerné non plus.
- Écran Exercices (`screen-exercice-running`) : pas de navigation
  Précédent/Suivant ni de bouton « meilleur coup » apparaissant/disparaissant
  — structure différente, pas concerné.
- `rv-game-info` (infos partie) : fixé une seule fois à l'entrée en revue,
  ne varie jamais pendant la navigation.

### Tests (navigateur, événements simulés — aucun moteur lancé)

Nouveau fichier `nicsoft/tests/e2e/test_issue332_review_nav_stable_position_e2e.py`
(Playwright, réutilise la fixture `at_menu` et le chemin « Coller PGN » déjà
utilisé par `test_review_nav_279_e2e.py` pour atteindre l'écran de revue
sans échiquier ni moteur). La présence/absence de meilleur coup est simulée
directement en JS (écriture de `reviewMoves[i].best_move` et `_isAnalysed`
via `page.evaluate`, puis `renderReview()`) — aucun appel socket, aucun
moteur Stockfish :

- position (`getBoundingClientRect`) de `#btn-review-next` strictement
  identique sur plusieurs coups consécutifs, en alternant un meilleur coup
  actif/grisé ;
- même vérification après retournement de l'échiquier (`#btn-flip`) ;
- même vérification avec une fenêtre réduite (1024×700, au lieu de
  1400×900).

Les 3 tests échouent sur le code d'avant correction (vérifié par
`git stash`/re-run) et passent après. Suite complète
`pytest nicsoft/tests/ -m "not slow"` (1111 passed, 82 skipped) toujours
verte ; les e2e déjà existants (`test_review_nav_279_e2e.py`,
`test_smoke_e2e.py`) passent toujours.

### Fichiers modifiés

- `nicsoft/web/templates/index.html`
- `nicsoft/web/static/app.js`
- `nicsoft/tests/e2e/test_issue332_review_nav_stable_position_e2e.py` (nouveau)
- `CHANGELOG-332.md` (nouveau)
