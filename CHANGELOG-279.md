# Changelog — Issue #279

## Interface : correction des éléments restés cachés ou bloqués depuis l'extraction des styles en ligne vers le CSS

Suite des issues #230-#248 (déplacement des styles `style="..."` écrits
dans le HTML vers des classes CSS). Pour les éléments cachés/désactivés par
défaut (`display:none`, `pointer-events:none`, `opacity<1`), le JS se
contentait d'effacer le style en ligne (`el.style.X = ""`) pour les
« révéler » — ça fonctionnait quand la valeur cachante était seulement
inline, mais ne fait plus rien depuis qu'elle vient d'une règle CSS de
classe : l'élément reste caché, sans la moindre erreur console (visible
seulement en test manuel réel ou via un moteur de rendu).

### Cinq cas confirmés par le rapport, corrigés dans `nicsoft/web/static/app.js`

1. **Contrôles de navigation de l'écran d'analyse** (lecture auto, curseur
   de vitesse, Précédent, Suivant) : `pointer-events` — déjà corrigé à la
   main par Alain avant cette issue (commit "interface : corrige à la main
   l'affichage du bandeau de reprise et la navigation de l'analyse"),
   vérifié et laissé tel quel.
2. **Exercices — bouton « Continuer avec Stockfish »** en fin de ligne
   théorique (`#ex-btn-continuer` / `.exr-btn-continuer`) : `style.display`
   passé de `""` à `"block"`.
3. **Retranscription — formulaire de l'onglet « Exercice »**
   (`#retrans-form-exercice` / `.retrans-form-card-hidden-init`) :
   `style.display` passé de `""` à `"block"` dans `retransSelectTab()`
   (et, par cohérence, le formulaire « Partie » du même switch).
4. **Retranscription, mode exercice — bouton « Sauver et continuer »**
   (`#btn-retrans-save-continue` / `.retrans-game-btn-save-continue`) :
   `style.display` passé de `""` à `"block"`.
5. **Configuration d'une partie — alerte « aucun moteur disponible »**
   (`#cfg-no-engine-alert` / `.cfg-no-engine-alert`) : `style.display`
   passé de `""` à `"block"` dans `_checkNoEngineAvailable()`.

### Sixième cas trouvé par la recherche systématique de cette issue

- **Messages « moteur non installé »** (`#cfg-stockfish-unavailable`,
  `#cfg-maia-unavailable`, `#cfg-rodent-unavailable`, classe partagée
  `.cfg-engine-unavailable-msg { display:none }`) : `_applyStockfishAvailability()`,
  `_applyMaiaAvailability()`, `_applyRodentAvailability()` effaçaient le
  style en ligne (`""`) pour les révéler quand le moteur correspondant est
  absent — jamais affichés depuis l'extraction. Passé à `"block"`. Les
  éléments jumeaux `#labo-*-unavailable` (classe `.labo-unavail-msg`, sans
  `display` en CSS, style `display:none` resté inline dans le HTML) ne sont
  pas affectés par ce bug et continuent de fonctionner avec `""`/`"block"`
  indifféremment — la valeur `"block"` leur convient donc aussi.

### Recherche systématique — cas examinés et écartés (déjà corrects)

Tout `.style.(display|opacity|pointerEvents|visibility)` du fichier
effaçant un style en ligne (`= ""`) a été passé en revue (une quarantaine
d'occurrences). Écartés parce que la classe CSS de l'élément ne cache rien
par défaut (pas de règle concurrente), ou parce que le code utilise déjà
une valeur explicite, ou une bascule de classe d'état
(`classList.toggle/add/remove`) avec une règle CSS correspondante :
`card-nav-save`, `pgn-lib-import-btn`/`-spinner`, `labo-cfg-sf/maia/rodent`
(style inline, pas de classe), `ex-variete-bar`/`ex-drill-bar`,
`modal-cancel` (4 occurrences), `btn-pause`/`btn-pause-hh`, `pause-select`
(opacité), `basket-select` (opacité/pointer-events), `syncBtn`
(`ex-btn-sync`), `#toast` (classe `.show`), `#modal-overlay` (classe
`.open`), `#coller-pgn-zone` (classe `.is-open`), `#autoupdate-warning`
(classe `.hidden`), `#cfg-section-*` (classe `.cfg-section-hidden` via
`classList.toggle`), et tous les écrans `#screen-*` (toujours des valeurs
explicites `"flex"/"grid"/"none"`).

### Cas douteux, non corrigés (hors périmètre de cette issue)

- **`#btn-pause-abandonner`** : déjà documenté lors d'une extraction
  antérieure comme bouton jamais montré par aucun JS (mort), figé en classe
  `.game-pause-hidden-init` sans changement de comportement voulu —
  confirmé inchangé, pas une régression de #230-#248.
- **`#countdown { display:none !important; }`** : règle CSS avec
  `!important` qui bloquerait de toute façon toute tentative du JS de la
  révéler (même avec une valeur explicite) — mais `startCountdown()`, la
  seule fonction qui tente de l'afficher, n'est appelée nulle part dans le
  code (fonction morte). Pré-existe très probablement à la série
  #230-#248 (pas un style en ligne effacé, un `!important` CSS direct).
  Hors périmètre ; signalé pour mémoire.
- **`#labo-feedback`** : deux éléments distincts partagent cet id
  (`.labo-feedback-center` et `.labo-feedback-side`, tous deux
  `display:none` en CSS) ; le seul code JS qui le référence ne fait que le
  masquer (`style.display = "none"`), jamais l'afficher — semble vestigial/
  mort plutôt que lié au défaut de cette issue (aucun effacement de style
  en ligne en cause). Non corrigé, signalé pour mémoire.

### Test de garde (sans navigateur)

`nicsoft/tests/test_css_extraction_hidden_elements.py` — analyse
statiquement `templates/index.html` (association id→classes), `css/main.css`
(règles de classe simples, hors `@media`, qui cachent par défaut :
`display:none`, `pointer-events:none`, `opacity<1`, `visibility:hidden`) et
`static/app.js` (motif `document.getElementById("id")...style.PROP = ""`,
y compris via variable intermédiaire). Échoue si un élément correspond aux
deux. Vérifié qu'il détecte bien les 4 régressions ci-dessus quand
réintroduites (et qu'il ne produit aucun faux positif sur l'état actuel).
Aucune exception documentée nécessaire à ce jour (`EXCEPTIONS_ID_PROP`
prévu pour les futurs cas légitimes).

### Tests e2e (Playwright, infrastructure existante dans `nicsoft/tests/e2e/`)

`nicsoft/tests/e2e/test_review_nav_279_e2e.py` (nouveau) :
- charge une courte partie via « Coller PGN » dans l'écran Analyse (chemin
  déjà utilisé par `test_smoke_e2e.py` comme proxy de l'état `game_over`
  sans échiquier ni partie jouée ; `parsePgn()` est purement client, aucun
  appel socket ni écriture disque) ;
- vérifie que Précédent/Suivant ne sont pas `disabled` **et** que
  `pointer-events` n'est pas `none` (le symptôme exact du cas #1) ;
- vérifie qu'un clic sur Précédent puis Suivant fait réellement changer le
  coup affiché (`#review-move-san`), pas seulement l'attribut `disabled`.
- Vérifié manuellement que ces deux tests échouent (timeout Playwright
  « intercepts pointer events ») si on réintroduit la régression du cas #1,
  et passent une fois corrigé.

Test e2e pour le bouton « Continuer » des Exercices **non ajouté** : pas
réaliste avec l'infrastructure actuelle sans risque de régresser sur les
contraintes de l'issue — atteindre une vraie fin de ligne théorique suppose
(a) un catalogue d'ouvertures réel, qui n'est pas versionné dans le dépôt
(`data/` est dans `.gitignore`, dépend du dossier utilisateur), donc un
test non reproductible/portable entre environnements, et (b) une
synchronisation par coup via le thread d'exercice (plateau virtuel), chemin
jamais exercé par l'infrastructure e2e actuelle (tous les tests existants
sont purement navigationnels, aucun ne joue de coup réel) — risque de
flakiness et de dépendance non maîtrisée au dossier de données réel.

### Vérifications manuelles suggérées

1. Terminer une partie (ou charger un PGN en Analyse), puis cliquer sur
   Précédent/Suivant, survoler le curseur de vitesse et le bouton lecture
   automatique : tout doit réagir normalement.
2. Exercices : jouer une ligne théorique jusqu'au bout → le bouton
   « Continuer avec Stockfish » doit apparaître (si un moteur est
   disponible).
3. Retranscription : ouvrir l'onglet « Exercice » → le formulaire doit
   s'afficher ; démarrer une retranscription en mode exercice → le bouton
   « Sauver et continuer » doit apparaître pendant la partie.
4. Configuration d'une partie sans aucun moteur disponible (si faisable) :
   l'alerte « Aucun moteur d'échecs n'est disponible » doit s'afficher et
   le bouton Démarrer doit être grisé.

### Tests

- `nicsoft/tests/test_css_extraction_hidden_elements.py` (nouveau).
- `nicsoft/tests/e2e/test_review_nav_279_e2e.py` (nouveau, 2 tests).
- Suite complète hors hardware (`pytest nicsoft/tests -m "not hardware"`) :
  311 passed, 65 skipped.
