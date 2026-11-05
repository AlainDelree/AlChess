# Changelog — Issue #255

# Changelog — Issue #282

## Fix : nulle acceptée traitée comme une erreur en mode Pédagogique

`Game._traiter_nulle` (`nicsoft/modes/pedagogique/pedagogique.py`) englobait
dans un seul bloc `except Exception` à la fois l'évaluation de la position
et l'appel à `_end_game(...)` qui termine la partie en levant volontairement
`BackMenuExit` (exception de contrôle de flux, sans message). Le bloc avalait
cette exception : la partie ne se terminait jamais, le fil de surveillance de
l'échiquier continuait de tourner (d'où les « cases incorrectes » répétées en
comparant au plateau final), le lanceur restait signalé « partie en cours »
et le mode Pédagogique ne pouvait plus être relancé sans redémarrer. En plus,
l'utilisateur recevait un toast « nulle refusée » alors que la nulle venait
d'être acceptée, avec un journal affichant « Erreur évaluation nulle: »
(message vide).

- Seule l'évaluation moteur reste protégée par le `try/except` ; l'appel de
  fin de partie (`_end_game`) en est sorti, laissant `BackMenuExit` remonter
  normalement jusqu'au lanceur (`nicsoft/core/game_manager_modes/pedagogique.py`,
  qui l'intercepte déjà correctement avant son `except Exception`).
- Seuil d'acceptation (150 centipions, décision utilisateur conservée tel
  quel) extrait en constante nommée `SEUIL_ACCEPTATION_NULLE_CP`, avec
  commentaire explicatif.
- Le nom réel de l'adversaire (ex. « Rodent 1200 (Tal) », « Maia 1200 »,
  « Stockfish ~1500elo » — celui déjà affiché au-dessus de l'échiquier) est
  désormais transmis au fil de partie (`game.opponent_label`) et utilisé dans
  le titre de la boîte de confirmation de nulle et dans le motif de refus, à
  la place du texte fixe « Stockfish », dans les 3 langues (clés
  `modal.nulle_stockfish_titre` et `toast.nulle_refusee_default` paramétrées
  avec `{opponent}`).
- Recherche systématique des autres modes (humain, exercices, labo,
  retranscription, explorer, lanceurs) : aucun autre bloc `except` générique
  n'avale une exception de contrôle de flux équivalente à `BackMenuExit`
  (celle-ci n'existe que dans ce fichier). Points de vigilance relevés sans
  correction (mécanismes différents, actuellement sûrs) : `human.py` utilise
  `sys.exit(0)` pour terminer une partie, protégé par un `except SystemExit`
  placé avant le `except Exception` — fragile en cas de futur
  `except BaseException` ou réordonnancement ; `exercices.py` utilise
  `ExitNicLink` de la même façon, également bien ordonné aujourd'hui.
- Tests ajoutés (`nicsoft/tests/test_pedagogique_nulle.py`, moteur et
  interface simulés, sans matériel) : nulle acceptée → `BackMenuExit` remonte
  sans aucun événement de refus ; nulle refusée car l'adversaire est trop
  bien placé ; évaluation impossible → refus avec le message dédié et la
  partie continue ; valeurs limites du seuil (150 accepté, 151 refusé) ; nom
  de l'adversaire transmis dans le message de refus.

### À vérifier manuellement par Alain (échiquier physique)

- Proposer la nulle contre Stockfish, Maia et Rodent chacun dans une position
  où le moteur est nettement mieux (doit refuser, message citant le bon nom)
  et une où il est égal ou moins bien (doit accepter et terminer la partie).
- Après une nulle acceptée suivie d'un retour au menu (ou d'une analyse puis
  retour au menu), relancer le mode Pédagogique sans redémarrer le programme,
  et vérifier qu'aucun message « cases incorrectes » ne réapparaît (preuve que
  l'ancien fil de partie s'est bien arrêté).

# Changelog — Issue #278

## Découpage de game_manager.py en lanceurs par mode (ARC-004)

`nicsoft/core/game_manager.py` (~1180 lignes) orchestrait les sept modes
de jeu dans un seul fichier, avec un état global partagé entre leurs
fonctions. L'audit (règle ARC-004) le signalait comme fichier à
découper ; le rapport le jugeait à risque moyen (couplage à sens unique,
game_manager → modes, jamais l'inverse).

- **Nouveau sous-dossier `nicsoft/core/game_manager_modes/`** (9 fichiers,
  tous nettement sous 300 lignes) :
  - `state.py` (143 l.) — état réellement partagé entre plusieurs modes
    (échiquier courant, mode virtuel) via accesseurs
    (`get_nl_inst_ref`/`set_nl_inst_ref`, `get_virtual_mode`/`set_virtual_mode`),
    plus utilitaires communs (attente de position, toasts d'erreur,
    lecture config moteur).
  - `pedagogique.py` (158 l.), `humain.py` (111 l.),
    `retranscription.py` (45 l.), `exercices.py` (245 l. — exercices et
    drill, avec leur état de session propre : plus exporté nulle part),
    `labo.py` (98 l.) + `labo_session.py` (256 l. — boucle d'actions de la
    session labo, avec le drapeau d'annulation de copie propre à ce
    couple de modules), `labo_libre.py` (140 l.), `explorer.py`
    (139 l. — état de session Opening Explorer propre à ce module).
  - État qui ne servait qu'à un seul mode (session d'exercice/drill, flag
    d'annulation de copie labo, session explorer) rendu local au module de
    ce mode plutôt qu'exporté globalement.
- **`nicsoft/core/game_manager.py` devient une façade** (36 lignes) :
  réexporte les mêmes objets fonctions qu'avant (mêmes noms, y compris les
  privées utilisées par un test — `_run_humain` — et par alchess.py/server.py
  via import local — `_run_exercice`, `_run_drill`, `_make_labo_session`,
  etc.). Aucune variable d'état réaffectable réexportée : uniquement des
  fonctions.
- **Nouvelle fonction d'accès `get_virtual_mode()`** (`state.py`) : remplace
  les deux lectures directes de `gm._virtual_mode` dans
  `nicsoft/web/alchess.py` (handler `set_virtual_mode` du menu), qui
  auraient figé une copie périmée après le découpage puisque la variable
  n'est plus un simple module-global importable en toute sécurité par
  `from ... import`.
- Comportement inchangé : aucun événement envoyé, message de log, ou
  branche d'exception modifiés — seule la répartition du code entre
  fichiers a changé. Les nouveaux modules n'importent toujours jamais
  `nicsoft.web` (ARC-001, vérifié par la suite de tests existante qui
  découvre désormais ces 9 nouveaux fichiers automatiquement : 63 → 73
  fichiers surveillés, 308 → 344 tests passés hors tests matériel, 0 échec).
- Aucun nouveau dossier hors de `nicsoft/core/` : le découpage reste
  entièrement contenu dans `nicsoft/core/game_manager_modes/`.

# Changelog — Issue #281

## Découpage de explore_book.py et eco_import.py, mutualisation de la logique d'import du catalogue

Les deux fichiers dépassaient le seuil de taille de l'audit (règle ARC-004) :
`explore_book.py` (~410 lignes) et `eco_import.py` (~630 lignes). Découpés en
modules par section, sans changement de comportement.

- **`explore_book.py`** devient un point d'entrée qui réexporte les mêmes
  objets publics, répartis dans :
  - `explore_book_display.py` — affichage terminal (échiquier ASCII, ligne
    de coups) : `weight_bar`, `print_board`, `format_move_line`.
  - `explore_book_import.py` — ajout interactif au catalogue : `do_import`.
  - `explore_book_cli.py` — boucle interactive en ligne de commande : `main`.
  - `explore_book_web.py` — fonctions appelées par le serveur web :
    `list_books_for_web`, `get_moves_from_web`.
- **`eco_import.py`** devient de même un point d'entrée, réparti dans :
  - `eco_import_data.py` — chargement des fichiers TSV ECO et filtre :
    `ECO_FILES`, `load_eco`, `parse_filter`.
  - `eco_import_display.py` — popularité dans les livres et affichage des
    résultats : `get_popularity`, `pop_bar`, `pop_label`, `display_results`.
  - `eco_import_import.py` — import d'une entrée, interactif ou en lot :
    `import_entry`, `quick_import_batch`.
  - `eco_import_cli.py` — boucle interactive en ligne de commande : `main`.
  - `eco_import_web.py` — fonctions appelées par le serveur web :
    `search_eco_from_web`, `import_eco_from_web`.
- **Mutualisation de la logique de catalogue dupliquée** : la vérification
  « cette séquence de coups est-elle déjà dans le catalogue ? » était
  recopiée à l'identique 6 fois entre `explore_book.py` (×2) et
  `eco_import.py` (×3), plus une fois de plus sous un nom différent
  (`in_catalogue`) — regroupée dans une nouvelle fonction
  `trouve_doublon(uci_moves, existing_inits)` ajoutée à `_catalogue.py`, et
  réutilisée partout. `do_import` (explorateur) réimplémentait aussi la
  boucle `check_books()` ligne pour ligne ; remplacé par un appel direct à
  la fonction déjà partagée.
  - **Non mutualisé, volontairement** : `search_eco_from_web` construit un
    dict `{tuple(coups): id}` pour vérifier jusqu'à 300 lignes en O(1)
    chacune, plutôt que de rappeler `trouve_doublon` en boucle (O(n) à
    chaque appel) — comportement équivalent, mais le remplacer aurait
    dégradé les performances sur un gros catalogue. De même, la sélection
    du livre cible reste différente entre `do_import` (menu interactif
    numéroté si plusieurs livres correspondent) et
    `import_entry`/`quick_import_batch`/`import_eco_from_web` (sélection
    automatique via `best_book_for`, déjà partagée) : ce sont deux
    parcours utilisateur réellement différents (l'un demande à l'humain,
    l'autre choisit seul), pas une duplication à fusionner.
- **Aucun fichier de données renommé ni déplacé** (`eco_a.tsv`…`eco_e.tsv`,
  `books/*.bin`, `exercices.py`) — les tests e2e qui lisent les vraies
  données ECO de l'utilisateur continuent de fonctionner sans changement.
- `manage.py` et `server.py` continuent d'importer `main`,
  `search_eco_from_web`, `import_eco_from_web`, `list_books_for_web`,
  `get_moves_from_web` directement depuis `explore_book`/`eco_import` —
  aucune modification nécessaire dans ces deux fichiers.
- Les tests de garde ARC-001 (`test_no_web_import.py`,
  `test_no_undefined_names.py`) découvrent automatiquement les nouveaux
  fichiers via le glob de `_arc001_discovery.py` — vérifié : les 9 nouveaux
  modules apparaissent dans la liste découverte, sans mise à jour manuelle.

# Changelog — Issue #280

## Suppression de cinq fichiers morts découverts par les tests de garde ARC-001

Suite de l'élargissement de la découverte ARC-001 à tous les fichiers de
`core`, `modes`, `niclink`, `utils` et `engine` (issue #272), qui avait mis
en évidence cinq fichiers cassés et jamais appelés, documentés comme
exclusions avec test miroir plutôt que supprimés sur le moment.

- Vérification à jour par recherche dans tout le dépôt (code, scripts,
  packaging, documentation, hors changelogs) : aucune référence réelle à
  l'un des cinq fichiers (seules les occurrences de `light_board` sont le
  nom d'un paramètre dans `driver.py`/`virtual_board.py`, sans rapport).
- **Fichiers supprimés** :
  - `nicsoft/utils/light_board.py`
  - `nicsoft/utils/turn_out_all_lights.py`
  - `nicsoft/modes/exercices/__main__.py`
  - `nicsoft/modes/labo/__main__.py`
  - `nicsoft/modes/retranscription/__main__.py`
- `nicsoft/tests/test_no_web_import.py` : retrait de
  `MODULES_NON_IMPORTABLES_SEULS` (les 5 exclusions) et de son test miroir
  `test_modules_non_importables_restent_documentes` ; tous les modules
  découverts passent désormais par les tests normaux.
- `nicsoft/tests/test_no_undefined_names.py` : retrait de l'exclusion
  `nicsoft/utils/light_board.py` (`FICHIERS_AVEC_NOMS_NON_DEFINIS_CONNUS`)
  et de son test miroir `test_fichiers_exclus_restent_documentes`.
- `.audit.json` non touché, comme demandé.
- Suite complète (`pytest -m "not hardware"`) : 293 passed, 60 skipped,
  0 failed — même niveau de protection, aucun fichier supplémentaire
  ignoré.

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

# Changelog — Issue #277

## Retranscription et Outils : ne plus afficher des demi-coups sous le nom de « coups »

Suite du rapport de l'issue #274 (confusion demi-coup/coup aux échecs), pour
les deux endroits qu'elle avait listés sans les corriger.

- **Règle de conversion partagée** : `pgn_move_number`/`pgn_moves_played`
  déplacées de `nicsoft/modes/exercices/exercices.py` vers
  `nicsoft/engine/board_utils.py` (module neutre partagé, ne dépend jamais
  de `nicsoft.web` — ARC-001). `exercices.py` les réimporte désormais
  depuis ce module ; comportement et test existant
  (`test_exercices_pgn_move_count.py`) inchangés.
- **Retranscription — bannière de session reprise** (`app.js`, handler
  `retranscription_en_cours`) : `nicsoft/web/alchess.py` envoyait le nombre
  brut de demi-coups de la session sauvegardée dans le champ `moves` ;
  converti via `pgn_moves_played()`. Pluriel correct ajouté dans les 3
  langues (nouvelle clé `common.n_coup`, singulier, à côté de
  `common.n_coups` déjà existante) ; `app.js` choisit la bonne clé selon
  `data.moves === 1`.
- **Retranscription — champ `move_num` de l'événement par coup** : non lu
  par aucun code (interface, tests, autres modules — vérifié par grep),
  renommé en `half_moves_played` dans
  `nicsoft/modes/retranscription/retranscription.py` pour refléter sa
  vraie nature (nombre brut de demi-coups, pas un numéro de coup PGN).
- **Outils (panneau d'administration du catalogue)** : les trois libellés
  techniques comptant des demi-coups sans les convertir — `outils.label.coups`
  ("Coups"/"Moves"/"Züge"), `outils.polyglot.profondeur` (profondeur
  d'exploration du livre), `outils.init_coups` (coups d'initialisation
  d'une ligne) — renommés en « Demi-coups »/« Half-moves »/« Halbzüge »
  dans les 3 langues, sans toucher aux valeurs ni à aucun format de
  fichier. Nouvelle clé `outils.n_demi_coups` ajoutée pour que le compte
  affiché à côté de la liste de coups (`outils.label.coups`, ligne ~6036
  d'`app.js`) reste cohérent avec le libellé renommé (il réutilisait avant
  `common.n_coups`, partagé avec d'autres écrans non concernés par cette
  issue).
- Mode Humain contre Humain et mode Pédagogique non touchés, comme demandé.

### Autres endroits avec la même confusion, trouvés en route mais non corrigés (hors périmètre de cette issue)

- `app.js` ligne ~1693 : options de la combobox `rv-seq-moves` (mode
  Pédagogique, replay vidéo) — `t("common.n_coups", {n: opt.value})`.
- `app.js` ligne ~3461 : journal du Labo à l'import d'un PGN —
  `t("common.n_coups", {n: history.length})`, `history.length` étant un
  nombre de demi-coups.
- `app.js` ligne ~4403 : cartes de sélection de lignes à l'entraînement
  (drill) en mode Exercices — `t("common.n_coups", {n: nb})` où `nb =
  (o.line || o.init || []).length` est un nombre de demi-coups.
- `app.js` ligne ~6051/6057 : `outils.livre_count` ("{count} coup(s)
  suivant : {next}") — vérifié : `count` est un poids/fréquence Polyglot,
  pas un compte de demi-coups ; pas la même confusion, laissé tel quel.

### Vérification manuelle suggérée

1. Retranscription : commencer une retranscription, jouer quelques coups
   (demi-coups impair et pair à tester), quitter sans terminer (`Retour
   menu` ou fermer l'app), puis relancer l'app : la bannière de reprise
   doit afficher un nombre de coups conforme à la convention PGN
   (singulier/pluriel correct) dans les 3 langues.
2. Outils : ouvrir le panneau Outils des exercices (administration du
   catalogue), vérifier une ligne existante et l'exploration du livre
   Polyglot : les libellés doivent dire « Demi-coups »/« Half-moves »/
   « Halbzüge » (profondeur, coups d'une ligne, coups d'initialisation),
   valeurs inchangées.

### Tests

- `nicsoft/tests/test_board_utils_pgn_move_count.py` (nouveau) : couvre
  `pgn_move_number`/`pgn_moves_played` depuis leur nouvel emplacement
  (0, 1, 2, 5, 24 demi-coups) et la valeur envoyée pour une session de
  retranscription reprise.
- `nicsoft/tests/test_exercices_pgn_move_count.py` : inchangé, toujours
  vert (les fonctions sont réimportées, pas redéfinies).
- Suite complète hors hardware (`pytest nicsoft/tests/ -m "not hardware"`) :
  260 passed, 54 skipped.

# Changelog — Issue #276

## Découpage de engine_manager.py en modules cohérents

`nicsoft/engine/engine_manager.py` (833 lignes, règle ARC-004) mélangeait
détection des binaires, disponibilité, classe générique de moteur UCI,
spécialisations Maia/Rodent et classification des coups. Découpé sans
changement de comportement en 7 modules du dossier `nicsoft/engine/` :

- `move_quality.py` (39 lignes) — `classifier_coup`, `score_to_cp`,
  seuils `SEUIL_BON`/`SEUIL_IMPRECISION`/`SEUIL_ERREUR` (logique pure).
- `engine_analysis.py` (277 lignes) — `EngineAnalysisMixin` : `evaluate`,
  `evaluate_move`, `get_punishment_line`, `get_multipv`, `analyser_partie`,
  `wdl_to_bar`. Extrait de la classe `EngineManager` d'origine (qui
  dépassait seule 380 lignes) en mixin hérité, pour que chaque module
  reste nettement sous 300 lignes sans toucher au comportement ni à la
  structure de classe (MaiaEngine/RodentEngine héritent toujours de
  `EngineManager`, qui hérite du mixin).
- `uci_engine.py` (150 lignes) — `EngineManager` (init, `_apply_elo`,
  `get_move`, `set_elo`, `quit`, propriétés) + constantes `ELO_MIN`/
  `ELO_MAX`/`ELO_DEFAUT`.
- `engine_detection.py` (132 lignes) — `find_stockfish`, `find_lc0`,
  `find_rodent`, `find_maia_weights`, `MAIA_LEVELS`, `_ensure_executable`.
- `engine_availability.py` (64 lignes) — `stockfish_available`,
  `maia_available`, `rodent_available` (ce dernier lance réellement
  Rodent pour le handshake UCI, comportement inchangé).
- `maia_engine.py` (114 lignes) — `MaiaEngine`.
- `rodent_engine.py` (132 lignes) — `RodentEngine` + constantes
  `RODENT_PERSONALITIES`/`RODENT_ELO_MIN`/`RODENT_ELO_MAX`/
  `RODENT_ELO_DEFAUT`/`RODENT_PERSONALITY_DEFAUT`.

`engine_manager.py` (63 lignes) devient un point d'entrée qui réexporte
tous ces objets — aucun import existant (serveur web, `analyse.py`, mode
labo, `test_rodent.py`, `test_analyse_engine_path.py`) n'a dû être modifié.

Logger applicatif inchangé : chaque nouveau module reprend
`logging.getLogger("EngineManager")`, exactement comme l'ancien fichier
unique (même nom partout, donc même objet Logger).

Aucun test n'a dû être adapté : `test_analyse_engine_path.py` monkeypatch
`nicsoft.engine.engine_manager.find_stockfish`, et `analyse.py` continue
de faire `from nicsoft.engine.engine_manager import find_stockfish` à
l'intérieur de la fonction au moment de l'appel — ce remplacement agit
donc toujours sur le nom réellement utilisé, puisque `engine_manager.py`
réexpose `find_stockfish` (défini maintenant dans `engine_detection.py`)
comme un attribut de son propre module. Vérifié en relançant les deux
tests concernés après le découpage.

Suite complète hors tests `hardware` : 278 passed, 61 skipped (inchangé
par rapport à avant le découpage).

# Changelog — Issue #275

## Découpage de llm_explainer.py en modules cohérents (ARC-004)

`nicsoft/modes/opening_explorer/llm_explainer.py` dépassait 360 lignes et
concentrait plusieurs responsabilités (appel réseau aux fournisseurs,
cache disque, construction des consignes, fonctions publiques). Découpé en
4 modules dans le même dossier, `llm_explainer.py` devenant un simple point
d'entrée qui réexporte les 3 fonctions publiques sans aucun changement de
comportement :

- `llm_provider.py` (61 lignes) — `call_claude`/`call_openai` : appel HTTP
  bas niveau aux fournisseurs. Ne journalise ni clé d'API ni URL complète
  (inchangé).
- `llm_cache.py` (35 lignes) — `load_cache`/`save_cache` : cache disque
  JSON des explications déjà générées.
- `llm_prompts.py` (183 lignes) — consignes système/utilisateur par langue
  (`SYSTEM_PROMPTS`, `ANALYSE_SYSTEM_PROMPTS`, `CHAT_SUFFIX`), construction
  des prompts (`build_user_prompt`, `build_chat_prompt`,
  `build_analyse_context_text`) et extraction des flèches (`extract_arrows`).
- `llm_functions.py` (128 lignes) — les 3 fonctions publiques
  `get_explanation`, `get_chat_response`, `get_analyse_response`, qui
  orchestrent cache + consignes + appel fournisseur.
- `llm_explainer.py` (17 lignes) — réexporte les 3 fonctions publiques
  depuis `llm_functions.py` ; `nicsoft/web/server.py` les importe toujours
  depuis ce même chemin, sans aucune modification nécessaire côté serveur.

Le motif de compteur d'annulation de requête mentionné par l'issue
(`tts_engine._tts_generation` côté Explorer, `_analyse_llm_request_id`
côté drawer Analyse) ne vit pas dans `llm_explainer.py` mais dans
`tts_engine.py`/`server.py` — fichiers non touchés par ce découpage, donc
le motif reste bien dans un seul module, inchangé.

- 2 nouveaux fichiers de tests, aucun accès réseau (fonctions pures /
  cache sur répertoire temporaire) :
  - `nicsoft/tests/test_llm_cache.py` — round-trip load/save, cache
    absent, JSON corrompu ignoré.
  - `nicsoft/tests/test_llm_prompts.py` — construction des prompts
    (ouverture, alternatives, fallback FEN invalide, contexte Analyse) et
    extraction des flèches (3 langues, cases invalides, limite à 4).
- Suite de tests complète (hors `hardware`) : 284 passed, 58 skipped.

# Changelog — Issue #274

## Exercices : numéros et nombres de coups selon la convention des échecs

Le serveur envoyait au navigateur le nombre brut de **demi-coups**
(`len(board.move_stack)` ou `len(init_moves)`) pour les champs `move_num`
(progression pendant la ligne), `move_count` (position de départ à
reproduire) et `moves` (fin de ligne théorique) — affiché tel quel avec les
libellés "Coup"/"Move"/"Zug" ou "coups"/"moves"/"Züge", alors qu'aux échecs
un coup compte une paire blanc+noir.

- Deux fonctions ajoutées dans `nicsoft/modes/exercices/exercices.py` :
  - `pgn_move_number(half_moves)` = `half_moves // 2 + 1` — numéro du coup
    PGN en cours (celui que les blancs commencent ou que les noirs doivent
    répondre). Ex. 24 ou 25 demi-coups → coup 13.
  - `pgn_moves_played(half_moves)` = `(half_moves + 1) // 2` — nombre de
    coups complets joués ; pour un nombre impair de demi-coups (dernier
    coup commencé mais pas encore répondu), compte ce coup comme joué
    (choix documenté ici, demandé par l'issue). Ex. 4 demi-coups → 2 coups ;
    5 demi-coups → 3 coups.
- Les 6 points d'envoi dans `exercices.py` utilisent maintenant ces
  fonctions (`move_count` ×3, `moves` ×2, `move_num` ×1) — aucun nouvel
  événement, les noms de champs sont inchangés.
- `exercice_end_of_line` faisait déjà un `Math.floor(data.moves / 2)` côté
  JS (arrondi vers le bas, incorrect pour un nombre impair) : supprimé
  puisque `data.moves` est désormais déjà le nombre de coups complets.
- Pluriel correct dans les 3 langues pour les deux libellés concernés
  (`fr/en/de.json`) : nouvelles clés `exercices.coup_joue`/`coups_joues`
  (position de départ) et `exercices.end_of_line_feedback_un` (fin de
  ligne, variante singulier de la clé existante). `exercices.reproduire_position`
  n'inclut plus le participe "joués"/"played"/"gespielt" en dur (il fait
  maintenant partie du libellé choisi selon le pluriel).
- `common.coup_num` ("Coup {n}") n'a pas besoin de variante plurielle (un
  numéro de coup ne se pluralise pas) — seule la valeur envoyée était
  fausse, pas le libellé.
- Test ajouté : `nicsoft/tests/test_exercices_pgn_move_count.py`, vérifie
  les deux fonctions sur 0, 1, 2, 4, 5, 24 et 25 demi-coups.
- Suite complète (`pytest nicsoft/tests/ -m "not hardware"`) : 257 passed,
  54 skipped (tests matériel), aucun échec.

### Autres endroits avec la même confusion demi-coup/coup, non corrigés (hors périmètre de cette issue)

- `nicsoft/web/alchess.py` (événement `retranscription_en_cours`, bannière
  de reprise de partie) envoie `len(moves)` (demi-coups) affiché via
  `common.n_coups` dans `app.js` (~ligne 5705) : une partie à 25 demi-coups
  affiche "25 coups" au lieu de 13.
- `nicsoft/modes/retranscription/retranscription.py:247` — le champ
  `move_num` de l'événement `retranscription_move` est lui aussi un compte
  de demi-coups brut, mais n'est actuellement lu par aucun code JS
  (`_retransRenderHistory`/`_retransUpdateTurn` ne s'en servent pas) : pas
  de bug visible aujourd'hui, mais le nom du champ est trompeur. À noter :
  l'affichage du tour en cours dans ce même mode (`_retransUpdateTurn`,
  `app.js:5697`) applique déjà la bonne formule PGN
  (`Math.floor(length / 2) + 1`), donc ce mode n'a pas le bug visible pour
  l'utilisateur.
- Outils Exercices (panneau d'administration du catalogue, pas le mode
  Exercices lui-même) : `outils.label.coups` (`app.js:6032`) et
  `outils.init_coups` (`app.js:6371`) affichent le nombre de demi-coups
  d'une séquence d'initialisation comme "N coups" ; de même le champ
  `depth` envoyé par `nicsoft/modes/exercices/explore_book.py` (ligne 410,
  affiché via `outils.polyglot.profondeur`, `app.js:6238`) est aussi un
  compte de demi-coups.
- `explore_book.py:format_move_line()` (affichage terminal, outil CLI) est
  en revanche déjà correct : il construit la notation `N.san` selon la
  vraie numérotation PGN.

# Changelog — Issue #273

## Exercices : ne plus voir l'erreur "livre introuvable" en revenant dans un exercice une fois le livre restauré

Suite de #271. Cause établie par analyse du code (confirmée par le test
manuel décrit dans l'issue, qui pointait déjà vers cette piste) :

- **Cause 1 (interface) — confirmée.** `exSetFeedback()` (`app.js`) affiche
  le bandeau de feedback avec `duration = 0` pour les messages "livre
  introuvable" et "fin de ligne" (vert) : ni l'un ni l'autre ne disparaît
  automatiquement — c'est voulu, l'utilisateur doit agir. Mais le handler
  `socket.on("exercice_init", ...)`, qui construit l'écran d'un nouvel
  exercice, ne vidait jamais ce bandeau (`#ex-feedback`) : un message laissé
  affiché par un exercice précédent (ex. l'erreur livre manquant) restait
  visible indéfiniment au-dessus du nouvel exercice, même une fois sa cause
  disparue.
  - En revanche, la ligne de statut (`#ex-run-status`) modifiée par
    l'erreur est déjà réinitialisée par `exercice_init` **avant** la
    branche `if (_virtualMode) { ... } else { ... }`
    (`app.js:4623-4624` avant ce fix, code antérieur à #270/#271) : cette réinitialisation
    s'applique donc déjà identiquement aux deux modes (virtuel et échiquier
    physique) — contrairement à l'hypothèse soulevée dans l'issue, aucune
    asymétrie n'a été trouvée sur ce point précis à la lecture du code
    actuel ; aucun changement n'y était donc nécessaire.
- **Cause 2 (serveur) — non confirmée.** `ExerciceSession.run()`, dans la
  branche "livre manquant", boucle sur `_wait_action_end()` jusqu'à
  recevoir une action différente de "RETRY", puis fait un `return` normal
  (`exercices.py:974-979`). Les deux actions de sortie côté IHM ("Retour au
  menu" et "← Choisir autre ouverture") envoient toutes deux le même type
  d'action `exercice_back` (`index.html:922-924`, `app.js:97-98`), traité
  de façon identique par `_wait_action_end()` (`exercices.py:1219-1221`) :
  `self._running = False`, puis retour. `game_manager._run_exercice()`
  attend donc bien la fin réelle de `session.run()` avant son bloc
  `finally`, qui remet `_exercice_running = False`
  (`game_manager.py:505-507`) — le lanceur repasse donc bien à "aucun
  exercice en cours" et un nouveau lancement (`start_exercice` /
  `_run_exercice`) crée normalement une nouvelle session. Aucune
  modification serveur n'a donc été nécessaire ; un test de garde-fou a
  été ajouté pour verrouiller ce comportement.

### Modifications

- `nicsoft/web/static/app.js` — `socket.on("exercice_init", ...)` : efface
  désormais le bandeau de feedback résiduel (`#ex-feedback`, masqué et
  texte vidé) dès la réception de l'événement d'initialisation d'un
  exercice, avant toute autre mise à jour d'écran. Les messages temporaires
  (durée > 0, ex. "✓ coup théorique") ne sont pas concernés : ce
  changement ne touche que l'état résiduel au moment où un nouvel exercice
  démarre.
- `nicsoft/tests/test_exercices_book_missing.py` — nouveau test
  `test_nouvelle_session_apres_restauration_du_livre` (sans interface ni
  matériel) : une première `ExerciceSession` avec livre manquant est créée,
  tourne dans un thread, reste en attente (pas de retour automatique), puis
  se termine proprement sur une action `exercice_back`. Une seconde
  `ExerciceSession` est alors créée avec un livre Polyglot minimal
  construit pour le test (une seule entrée `e2e4`) : elle ne signale aucune
  erreur (`exercice_sync_error` absent des événements), émet
  `exercice_wait_position` (démarrage normal), et ne se termine pas
  immédiatement (le thread reste vivant, en attente de la synchro
  initiale) — exactement le comportement attendu quand on revient dans un
  exercice une fois le livre restauré.
- Cas inchangés vérifiés : "pièces mal placées" (`exercice_sync_error` hors
  livre manquant) et cas normal (livre présent, fin de ligne théorique) —
  aucun des tests existants n'a été modifié dans son comportement, seuls
  ajouts.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 255 passed,
  54 skipped.

### Reproduction manuelle

1. Renommer temporairement le fichier du livre d'ouvertures attendu (ex.
   `data/books/gm2001.bin` → `gm2001.bin.bak`).
2. Ouvrir un exercice d'ouverture quelconque : le message « Livre
   d'ouvertures introuvable : <chemin> » s'affiche, reste affiché (pas de
   retour automatique).
3. Quitter (← Retour au menu ou ← Choisir autre ouverture).
4. Remettre le fichier du livre à sa place (annuler le renommage de
   l'étape 1).
5. Rouvrir un exercice d'ouverture (le même ou un autre) : avant ce fix, le
   bandeau d'erreur « Livre d'ouvertures introuvable » restait affiché par-
   dessus le nouvel exercice bien que le livre existe de nouveau — il
   fallait cliquer sur « Synchroniser » pour le faire disparaître. Après ce
   fix, l'exercice démarre normalement, sans bandeau ni statut d'erreur
   résiduels, aussi bien avec un échiquier physique qu'en mode virtuel.

# Changelog — Issue #272

## Tests de garde ARC-001 : découverte automatique des fichiers au lieu de listes écrites à la main

Les trois tests qui verrouillent ARC-001 (le moteur n'importe jamais
`nicsoft.web`) listaient à la main huit ou neuf fichiers. Deux défauts :
`engine`, `utils` et `niclink/driver` n'y figuraient pas (un import web y
serait passé inaperçu), et un nouveau fichier créé lors d'un découpage
n'était couvert par aucun test, sans qu'aucune alerte ne le signale.

- `nicsoft/tests/_arc001_discovery.py` (nouveau) : découverte commune —
  parcourt `nicsoft/{core,modes,niclink,utils,engine}` et retourne tous les
  `.py` (hors `__pycache__`), avec un garde-fou (`verifier_decouverte_non_cassee`)
  qui échoue si la liste est vide ou si `game_manager.py` /
  `virtual_board.py` manquent.
- `nicsoft/tests/test_no_web_import.py`, `test_ihm_port_contract.py`,
  `test_no_undefined_names.py` : remplacent leur liste écrite à la main par
  cette découverte automatique, chacun avec un test dédié qui vérifie que la
  découverte n'est pas cassée.
- Modules qui ne s'importent pas seuls pour des raisons sans rapport avec
  ARC-001 (bugs préexistants dans du code mort, mis en lumière par la
  découverte élargie) : exclus explicitement avec une raison écrite, jamais
  en silence — et un test dédié (`test_modules_non_importables_restent_documentes`,
  `test_fichiers_exclus_restent_documentes`) échoue si le bug sous-jacent est
  corrigé sans retirer l'exclusion, pour qu'elle ne devienne pas obsolète :
  - `nicsoft.utils.light_board` : `List` et `np` non importés (NameError).
  - `nicsoft.utils.turn_out_all_lights` : `from niclink import NicLinkManager`
    cassé (devrait être `nicsoft.niclink`).
  - `nicsoft.modes.{exercices,labo,retranscription}.__main__` : importent
    `main` depuis leur module, qui ne le définit plus depuis le découplage
    #263/#264 (entry-points CLI morts, l'app web ne les utilise plus).
  - Ces cinq cas sont des bugs préexistants dans du code mort (jamais appelé
    ailleurs dans le projet), sans lien avec ARC-001 et sans risque pour le
    comportement actuel de l'application — non corrigés ici par prudence
    (la correction de `light_board.py` notamment nécessiterait de deviner un
    comportement voulu, au-delà d'un ajout d'import trivial).
- Temps ajouté à la suite ARC-001 : environ 3 s (passée de ~2,1 s à ~5,1 s
  sur cette machine) — reste de l'ordre de quelques secondes, le pre-push
  hook lance cette suite avant chaque push.
- Vérifié concrètement : un fichier fautif temporaire (`import nicsoft.web`
  + nom non défini) ajouté dans chacun des cinq dossiers (`core`, `modes`,
  `niclink`, `utils`, `engine`) fait échouer `test_no_web_import.py` et
  `test_no_undefined_names.py` automatiquement, sans modification des
  fichiers de test ; fichiers retirés sans être committés.
- Suite complète hors tests `hardware` : 252 passed, 54 skipped.
- `.audit.json` non modifié.

# Changelog — Issue #271

## Exercices : l'erreur "livre introuvable" reste affichée jusqu'à une action de l'utilisateur

Suite de #270. Le message d'erreur (livre Polyglot introuvable) était bien
émis mais `ExerciceSession.run()` terminait aussitôt après (`return`
immédiat) : le lanceur d'exercice (`game_manager._run_exercice`) voyait
alors la session se terminer et exécutait son nettoyage normal de fin
d'exercice, qui renvoie aussitôt la liste des ouvertures — l'écran d'erreur
disparaissait donc en moins d'une seconde, le rendant inutilisable en
pratique.

- `nicsoft/modes/exercices/exercices.py` (`ExerciceSession.run()`) : le cas
  « livre manquant » affiche désormais la position de départ de l'exercice
  demandé (`self._send_position()` — plus l'échiquier de l'exercice
  précédent) puis attend une action utilisateur via `_wait_action_end()`,
  exactement comme à la fin normale d'une ligne (mêmes actions possibles :
  retour au menu, choisir une autre ouverture, recommencer). Sur
  « recommencer », l'erreur est simplement réaffichée (le livre est
  toujours manquant) sans relancer `_restart()` ni repasser par la boucle
  de jeu normale — pas de boucle infinie (bloqué sur l'action utilisateur)
  ni de nouveau log (le log d'absence du livre reste unique, à la
  construction de la session). Seule la méthode `run()` a été modifiée ;
  le nettoyage de fin de session dans `game_manager._run_exercice` est
  inchangé, et le mécanisme d'attente/actions (`_wait_action_end`) est
  celui déjà utilisé pour la fin de ligne théorique normale.
- Cas inchangés vérifiés : livre présent et cas « pièces mal placées »
  (`exercice_sync_error` hors livre manquant).
- `nicsoft/tests/test_exercices_book_missing.py` : test existant mis à jour
  (fournit désormais une action de retour pour débloquer `run()`) et deux
  nouveaux tests — la session reste en attente tant qu'aucune action n'est
  reçue puis se termine proprement sur un retour, sans jamais émettre
  `exercice_end_of_line` ; et "recommencer" avec le livre toujours
  manquant réaffiche l'erreur (au moins 2 occurrences) sans log
  supplémentaire ni `exercice_end_of_line`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 125 passed,
  10 skipped.

### Reproduction manuelle

1. Renommer temporairement le fichier du livre d'ouvertures attendu (ex.
   `data/books/gm2001.bin` → `gm2001.bin.bak`), ou renommer le dossier
   `data/books/` lui-même.
2. Lancer un exercice d'ouverture quelconque depuis l'interface.
3. Observer : le message « Livre d'ouvertures introuvable : <chemin> »
   reste affiché tant qu'aucune action n'est prise — pas de retour
   automatique à la liste, l'échiquier affiché est celui de la position de
   départ de l'exercice choisi (pas celui d'un exercice précédent).
4. Cliquer « ↺ Recommencer l'exercice » : l'erreur est réaffichée à
   l'identique (toujours pas de retour à la liste).
5. Cliquer « ← Choisir autre ouverture » ou « ← Retour au menu » : retour
   normal à la liste des ouvertures / au menu.
6. Restaurer le fichier/dossier renommé à l'étape 1.

# Changelog — Issue #270

## Exercices : message clair quand le livre d'ouvertures est introuvable

Avant le fix, si le fichier du livre Polyglot était introuvable (ex. dossier
`data/` absent), `ExerciceSession._get_book_moves` avalait l'exception et
retournait une liste vide — indistinguable d'une vraie fin de ligne
théorique. L'IHM annonçait donc « Ligne terminée ! Bravo » alors que
l'exercice n'avait jamais pu se dérouler, et le serveur loggait l'erreur
« Livre : fichier ou dossier inexistant » à chaque coup.

- `nicsoft/modes/exercices/exercices.py` : l'existence du fichier du livre
  (`self._book_path`) est vérifiée une seule fois, à la construction de
  `ExerciceSession` (`self._book_missing`), et loggée une seule fois par
  exercice (`logger.error`, pas à chaque coup). `run()` détecte ce cas en
  tout premier lieu et émet `exercice_sync_error` (événement d'erreur IHM
  déjà utilisé par l'exercice pour la synchro de plateau) au lieu de
  dérouler la boucle de jeu — plus de faux `exercice_end_of_line`.
  `_get_book_moves` ne retente plus l'ouverture du fichier une fois le livre
  connu manquant, et ne logge plus qu'une fois les erreurs imprévues
  (livre corrompu, etc.) via `self._book_error_logged`.
- `nicsoft/web/static/app.js` : le handler `exercice_sync_error` accepte
  désormais deux champs optionnels — `status_key` (texte de statut
  personnalisé) et `show_sync_btn` (désactive le bouton Synchroniser quand
  resynchroniser ne résoudra rien) — sans changer le comportement par
  défaut (cas existant : pièces mal placées).
- `nicsoft/web/static/i18n/{fr,en,de}.json` : nouvelles clés
  `exercices.book_missing_status` et `exercices.book_missing_msg`
  (interpolée avec le chemin attendu du livre).
- Cas inchangés vérifiés : livre présent (coup du livre toujours trouvé) et
  vraie fin de ligne théorique (livre présent mais sans entrée pour la
  position) toujours traitée comme une fin de ligne normale.
- Nouveau test `nicsoft/tests/test_exercices_book_missing.py` (sans
  interface ni matériel) : livre absent → `exercice_sync_error` émis,
  `exercice_end_of_line` jamais émis, un seul log d'erreur ; livre présent
  → comportement inchangé ; livre présent mais vide pour la position →
  fin de ligne normale toujours distincte d'un livre manquant.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 122 passed,
  10 skipped.

# CHANGELOG-269 (issue #269)

## Échiquier virtuel : ajout de la méthode disconnect (plus de faux avertissement à la sortie des modes)

- `nicsoft/niclink/virtual_board.py` : ajout de `VirtualBoard.disconnect()`, no-op comme ses méthodes voisines (`turn_off_all_leds`, `beep`, etc.) — rien à fermer côté USB en mode virtuel.
- Cause : `nicsoft/core/game_manager.py` appelle `nl_inst.disconnect()` en sortie d'explorateur d'ouvertures, d'exercices et de drill (3 endroits, non modifiés — l'appel côté appelant était correct). Avec un échiquier virtuel, cette méthode n'existait pas : `AttributeError` avalée par un `except` qui journalisait un faux avertissement « Déconnexion échiquier échouée ... object has no attribute disconnect » à chaque sortie de ces modes en mode virtuel.
- Vérification des autres méthodes de `NicLinkManager` appelées par `game_manager.py` ou les modes sur l'objet échiquier (`get_fen`, `turn_off_all_leds`, `signal_lights`, `connect`, `start`...) : toutes déjà présentes dans `VirtualBoard` ou appelées uniquement après vérification que l'instance est physique (`connect()` dans `server.py`, gardé par `hasattr(nl_inst, "nl_interface")`). Aucune autre méthode manquante.
- `nicsoft/tests/test_virtual_board.py` (nouveau) : crée un `VirtualBoard` et appelle `disconnect()` sans erreur.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 120 passed, 10 skipped.

# CHANGELOG-267 (issue #267)

## Tests e2e : serveur lancé depuis le code testé, échiquier réel ignoré

- `nicsoft/tests/e2e/conftest.py` : le dossier de lancement du serveur de test (donc le code importé par `python -m nicsoft.web`) n'est plus le dépôt principal codé en dur (`~/NicLink`), mais déduit de l'emplacement de `conftest.py` (racine du dépôt ou du worktree où tourne pytest). Les tests valident donc le code sur lequel ils sont exécutés. Le Python reste celui du venv utilisateur (`~/NicLink/venv/bin/python`).
- `nicsoft/web/alchess.py` : nouvelle variable d'environnement `ALCHESS_SKIP_BOARD=1` qui désactive `_check_board_at_startup` (détection/connexion de l'échiquier USB réel au démarrage) et évite de lancer `_board_menu_watcher` ; absente, le comportement est inchangé. Positionnée uniquement dans l'environnement du serveur lancé par `conftest.py`.
- `data/` n'étant pas versionné, un worktree n'a pas les fichiers de référence réels (ECO `eco_*.tsv`, `eco_hierarchy.json`, livres d'ouvertures…) dont dépendent 3 tests de recherche ECO (`test_outils_exercices_e2e.py`). L'isolation complète via un dossier `ALCHESS_DIR` temporaire (point optionnel de l'issue) a été tentée puis abandonnée pour cette raison ; `ALCHESS_DIR` est positionnée vers le vrai dossier de données de l'utilisateur (`~/NicLink`) pour ces tests — seul le code vient du worktree, pas les données. Documenté dans `TESTS.md`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 119 passed, 10 skipped, lancée depuis le worktree, sans navigateur visible ni sollicitation de l'échiquier USB.

# CHANGELOG-266 (issue #266)

## Retrait de l'outil de sauvegarde backup_manager

- Suppression de `nicsoft/utils/backup_manager.py` et de `nicsoft/utils/Lancer et autre outil Backup.txt`.
- Retrait de toutes les références (commandes, consignes de backup épinglé) dans `CLAUDE.md`, `CONTEXTE.md`, `SPECIFICATIONS.md`, `TESTS.md`, `ETAT_PROJET.md` et `INSTALLATION/CONFIGURATION_SYSTEME.md`.
- Là où la consigne de backup épinglé disparaît, remplacement par un rappel explicite : la protection du travail repose sur git (commits ciblés, retour arrière par git, push fait par Alain après revue).
- `CONTEXTE.md` : suppression de l'affirmation périmée selon laquelle CCL travaille exclusivement dans `~/NicLink` (devenu faux depuis le passage aux worktrees isolés par issue).
- Aucun code Python n'importait cet outil ; suite de tests (`pytest -m "not hardware"`) : 96 passed, 4 skipped.

# Changelog — Issue #265

## Journal de l'application : ne plus enregistrer la bannière de démarrage des moteurs d'échecs

Le logger `chess.engine` (utilisé en interne par python-chess pour relayer en
WARNING la sortie stderr des moteurs UCI externes — bannière lc0/Maia au
démarrage : version, backend de calcul, poids chargés, cœurs...) est
désormais relevé au niveau `ERROR` dans `_setup_logging()`
(`nicsoft/web/alchess.py`). Choix assumé : on accepte de ne plus journaliser
la sortie stderr brute des moteurs (niveau WARNING chez python-chess), au
profit d'un journal applicatif lisible — les échecs réels de démarrage ou
d'arrêt inattendu d'un moteur restent signalés indépendamment, via les
`logger.error(...)` explicites d'`engine_manager.py` (sur le logger
`"niclink"`), qui ne dépendent pas de la sortie stderr relayée par
python-chess. Rien d'autre n'est modifié : ni le niveau global (`WARNING`),
ni les autres loggers. Verrouillé par `nicsoft/tests/test_logging_config.py`.

# Changelog — Issue #264

## Suite #263 : correction des régressions du découplage (Humain contre Humain + abandon Pédagogique)

Le test manuel avec échiquier physique a révélé deux régressions introduites
par le découplage nicsoft.web de la #263, non détectées par
`test_no_web_import.py` (qui ne vérifie que l'absence d'import de
`nicsoft.web`, pas que chaque appel migré trouve bien sa cible).

### Régression 1 — mode Humain contre Humain

`nicsoft/core/game_manager.py:320` appelait `web_server.set_history(...)` où
`web_server` est l'alias local de `ihm_port.app_state_proxy`
(`_AppStateProxy`). Cet objet n'expose que `_app_state` et `action_queue`
(façade volontairement limitée à l'ancien accès direct `web_server._app_state`
/ `.action_queue`) — pas `set_history`, qui est une fonction de module de
`ihm_port.py`, pas une méthode du proxy. Résultat : `AttributeError`
immédiatement après la création du plateau virtuel/physique → retour menu,
déconnexion/reconnexion visible côté échiquier.

**Fix** : `game_manager.py` importe désormais `set_history` directement
depuis `nicsoft.core.ihm_port` (même motif que `human.py`, qui l'importait
déjà correctement) et l'appelle sans passer par le proxy.

### Régression 2 — abandon en mode Pédagogique

`nicsoft/modes/pedagogique/pedagogique.py:376` (`Game._end_game`) lisait
`_game_state.get("init", {})`. `_game_state` était un dict interne de
`nicsoft.web.server`, importé localement avant la #263
(`from nicsoft.web.server import set_app_state, _game_state`). L'étape 6/8 de
la #263 a retiré cet import (remplacé par `get_history()` pour la lecture de
l'historique) mais a laissé cette seconde référence orpheline → `NameError:
name '_game_state' is not defined` au clic sur « Abandonner », juste avant
l'envoi de l'état `game_over` → retour menu avec popup d'erreur.

**Fix** : ajout d'un accesseur dédié `get_init_data()` — dans
`nicsoft/web/server.py` (lecture verrouillée de `_game_state["init"]`, miroir
de `get_history()`), exposé par `_WebBackend` (`nicsoft/web/alchess.py`) et
`_NullBackend`/module `nicsoft/core/ihm_port.py`. `pedagogique.py` l'importe
et l'appelle au lieu de lire `_game_state` directement.

### Recensement systématique (point 3 de la demande)

Vérification exhaustive, par analyse statique, de tous les fichiers migrés
par la #263 (`game_manager`, `human`, `pedagogique`, `exercices`, `labo`,
`virtual_board`, `board_adapter`, `retranscription`) :

- **Appels sur l'objet d'interface (`ihm_port`/`app_state_proxy`)** : les deux
  régressions ci-dessus sont les **deux seuls** cas trouvés où un appel migré
  ne correspond à aucun élément réellement fourni par le port ou par le
  proxy. Tous les autres imports depuis `ihm_port` et tous les autres appels
  sur l'alias de `app_state_proxy` (`web_server`/`_web_server`) correspondent
  à un élément réel.
- **Noms non définis (reste de l'ancien `nicsoft.web`)** : `_game_state`
  (régression 2) est le **seul** nom non lié trouvé sur l'ensemble des
  fichiers migrés (vérifié avec `pyflakes` et avec le test
  `test_no_undefined_names.py` ci-dessous).

### Tests ajoutés (point 4)

- `nicsoft/tests/test_ihm_port_contract.py` — analyse statique (ast) : chaque
  nom importé depuis `nicsoft.core.ihm_port` dans les fichiers migrés existe
  réellement dans ce module ; chaque attribut accédé sur l'alias local de
  `app_state_proxy` existe réellement sur `_AppStateProxy` ; `_NullBackend` et
  `_WebBackend` exposent chacun toutes les méthodes utilisées par les
  fonctions de module de `ihm_port.py`.
- `nicsoft/tests/test_no_undefined_names.py` — équivalent restreint de
  pyflakes ("undefined name"), implémenté avec le seul module standard `ast`
  (pas de nouvelle dépendance de test) : pour chaque fichier migré, vérifie
  qu'aucun nom lu n'est totalement non lié dans le fichier.
- `nicsoft/tests/test_humain_startup_virtuel.py` (bonus) — exécute
  `game_manager._run_humain(virtual=True)` avec un plateau virtuel et un
  double léger de `GameWeb`, jusqu'après l'enregistrement de l'historique
  initial via le port — sans matériel ni serveur Flask-SocketIO.

Les trois nouveaux tests ont été vérifiés manuellement contre l'état d'avant
correction (`git stash`) : ils échouent bien sur les deux régressions
(`AttributeError` et `NameError`) et passent après le fix.

### Comportement

Strictement identique à avant la #263 — aucun changement de motif de thread
SocketIO, aucune nouvelle dépendance.

### Vérifications manuelles à refaire avec l'échiquier physique

- Mode Humain contre Humain : lancer une partie, vérifier que l'échiquier
  s'affiche et reste connecté (pas de retour menu / déconnexion-reconnexion).
- Mode Pédagogique : lancer une partie, cliquer sur « Abandonner », vérifier
  qu'aucune popup d'erreur n'apparaît et que l'écran de fin de partie
  (historique, titre) s'affiche normalement avant le retour menu.

# Changelog — Issue #263

## Découplage de la logique de jeu : plus d'import de nicsoft.web depuis core/modes/niclink/utils/engine (règle ARC-001)

Recensement complet refait avant correction (l'audit initial, limité à
`nicsoft/modes`, comptait 32 sites) : **34 sites réels** répartis sur 7
fichiers — `nicsoft/core/game_manager.py` (11), `nicsoft/modes/humain/human.py` (7),
`nicsoft/modes/pedagogique/pedagogique.py` (7), `nicsoft/modes/exercices/exercices.py` (5),
`nicsoft/niclink/virtual_board.py` (3), `nicsoft/modes/labo/labo.py` (1),
`nicsoft/core/board_adapter.py` (1). (`nicsoft/utils/debug.py` et
`nicsoft/utils/timing.py` ne mentionnaient `nicsoft.web` que dans un
commentaire/docstring — aucun import réel.) `nicsoft/modes/retranscription/retranscription.py`
était déjà découplé : il reçoit `web_server` en paramètre (injection de
dépendance) plutôt que de l'importer — c'est le motif qui a inspiré la
solution retenue pour les autres fichiers.

**Solution retenue** : un port neutre, **`nicsoft/core/ihm_port.py`**, expose
aux modules de jeu les primitives dont ils ont besoin (`send_event`,
`get_action`, `set_app_state`, `set_virtual_board`, `get_history`/`set_history`,
`get_action_queue`, `get_app_state`/`set_raw_app_state`, `check_board_at_startup`,
`emit`). Tant qu'aucun backend n'est branché (import isolé, tests), un
backend neutre (`_NullBackend`) répond sans effet de bord — permet d'importer
n'importe quel module de jeu sans lancer le serveur web. Au démarrage réel,
`nicsoft/web/alchess.py` branche l'implémentation Flask-SocketIO via
`ihm_port.register_backend()`.

Les très nombreux sites qui accédaient directement au module
`nicsoft.web.server` (`web_server._app_state = ...`, `web_server.action_queue...`)
— notamment dans `game_manager.py` et `human.py`, pour la course critique
SocketIO qui écrit `_app_state` silencieusement avant d'appeler `set_app_state()`
(pour éviter une fenêtre de race pendant la notification navigateur) — n'ont
*pas* été réécrits un par un : `ihm_port.app_state_proxy` reproduit exactement
le même objet dupliqué (property `_app_state` + `action_queue`), ce qui a
permis de ne changer que la ligne d'import sur ces sites et de garder le reste
du code strictement identique. Seul `game_manager.py:304` (import différé de
`nicsoft.web.alchess._check_board_at_startup`, seul cas de cycle réel —
`alchess.py` importe `game_manager` au niveau module) devient
`ihm_port.check_board_at_startup()`.

Migration faite mode par mode, un commit par étape (points de retour arrière) :
port neutre → `niclink/virtual_board.py` → `core/board_adapter.py` →
`modes/labo/labo.py` → `modes/exercices/exercices.py` →
`modes/pedagogique/pedagogique.py` → `modes/humain/human.py` →
`core/game_manager.py` → test d'isolation.

Ajout de `server.emit()` (émission SocketIO directe, hors `event_queue`) pour
couvrir un site (`pedagogique.py`) qui faisait `socketio.emit()` directement
pour un popup ponctuel, sans passer par `send_event()`.

Un site a changé de forme sans changer de résultat : `pedagogique.py` lisait
`_game_state["history"]` directement (sans le verrou), remplacé par
`get_history()[0]`, l'accesseur déjà prévu par `server.py` pour cet usage
précis d'après sa propre docstring ("à utiliser par tout module hors
server.py").

**Résultat** : plus aucun import de `nicsoft.web` depuis `core`, `modes`,
`niclink`, `utils`, `engine` (vérifié par recherche dans le code — seules des
mentions en commentaire/docstring subsistent dans `ihm_port.py`, `debug.py`,
`timing.py`). Comportement strictement identique : mêmes événements, mêmes
files d'actions, mêmes fils d'exécution.

**Fichiers modifiés :**

`nicsoft/core/ihm_port.py` (nouveau), `nicsoft/web/server.py`,
`nicsoft/web/alchess.py`, `nicsoft/niclink/virtual_board.py`,
`nicsoft/core/board_adapter.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/core/game_manager.py`,
`nicsoft/tests/test_no_web_import.py` (nouveau).

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
54 passed, 3 skipped (hardware), dont le nouveau
`test_no_web_import.py` (14 cas, chacun dans un sous-processus Python
propre pour ne pas être pollué par d'autres tests qui importent
`nicsoft.web.server` pour leurs propres besoins). Smoke-test manuel du
serveur réel (`start_server()` + requête HTTP sur `/`) : backend branché,
`_app_state` piloté via le port identique à l'ancien accès direct au
module. Suite e2e non lancée (nécessite Playwright + serveur lancé depuis
`~/NicLink`, hors périmètre du worktree).

**À vérifier manuellement par Alain, avec l'échiquier physique branché**
(aucun hardware disponible dans l'environnement de l'agent) :
- Mode Pédagogique (Stockfish/Maia/Rodent) : coup joué, feedback LED,
  pause sur erreur/blunder, reprise, abandon, fin de partie (mat/nulle),
  notification popup mat/pat.
- Mode Humain vs Humain : coups, undo, abandon, nulle par accord mutuel,
  retour menu depuis un état actif (vérification silencieuse du plateau
  au retour menu).
- Mode Exercices : synchronisation initiale, détection hors-théorie,
  retry/continue, retour menu.
- Mode Labo : suivi du plateau physique, meilleur coup, mode auto,
  analyse, copie de position.
- Déconnexion USB en cours de partie (callback `_board_lost_cb` →
  `board_error`) : le message doit toujours apparaître côté navigateur.
- Démarrage de l'appli complète (`python -m nicsoft.web`) suivi d'un tour
  dans chaque mode, pour confirmer qu'aucune régression de câblage n'est
  passée inaperçue dans l'environnement sans hardware de l'agent.

# Changelog — Issue #262

## Analyse de partie : ignorer le chemin du moteur sauvegardé s'il n'existe pas sur cette machine

`analyser_partie()` (`nicsoft/engine/analyse.py`) lisait le chemin du moteur
enregistré dans `data/config.json` et le transmettait tel quel à
`EngineManager`, sans vérifier qu'il existait sur la machine courante. Une
configuration copiée depuis une autre machine, ou un moteur désinstallé/déplacé,
faisait planter l'analyse au lieu de retomber sur la recherche automatique de
Stockfish (`find_stockfish()`) — repli qui n'était utilisé que lorsque le
chemin était vide.

La logique de validation (`chemin sauvegardé conservé seulement s'il existe`)
existait déjà dans `nicsoft/core/game_manager.py` sous le nom
`_validated_engine_path()`, utilisée par les autres modes de jeu. Pour éviter
une troisième copie tout en respectant le sens des dépendances (`engine` ne
doit pas dépendre de `game_manager`, qui dépend de la couche web), cette aide
est déplacée vers **`nicsoft/core/config_manager.py`** (module neutre, déjà
point d'accès centralisé à `config.json` depuis #259), renommée
`validated_engine_path()` (devenue un helper public partagé plutôt qu'un
détail interne de `game_manager`). `game_manager.py` pointe maintenant vers
cette version déplacée, sans changement de comportement.

`analyser_partie()` réutilise aussi `read_json_with_defaults()` (lecture de
config partagée introduite par #259) à la place de sa propre lecture JSON
manuelle, avec le même message de log en cas d'échec.

**Fichiers modifiés :**
- `nicsoft/core/config_manager.py` — ajout de `validated_engine_path()`.
- `nicsoft/core/game_manager.py` — utilise `validated_engine_path()` importé de `config_manager` (suppression de la copie locale `_validated_engine_path`).
- `nicsoft/engine/analyse.py` — `analyser_partie()` valide le chemin moteur sauvegardé et réutilise `read_json_with_defaults()`.
- `nicsoft/tests/test_analyse_engine_path.py` (nouveau) — 3 tests avec `EngineManager` simulé (aucun vrai moteur lancé) : chemin inexistant → repli `find_stockfish()`, chemin existant → conservé, chemin vide → comportement inchangé.

Suite de tests complète (hors `hardware`) : 82 passed, 4 skipped.

# Changelog — Issue #261

## Erreurs silencieuses : trace ou justification de chaque except sans traitement (règle PRO-012)

L'audit relevait 52 captures d'erreur silencieuses (exemples : `platform_utils.py`,
`labo.py`, `retranscription.py`, sept occurrences dans `game_manager.py`). Un
recensement complet refait avant correction (les numéros de ligne de l'audit
avaient bougé) a trouvé **133 occurrences réelles** réparties sur 29 fichiers —
l'audit initial était partiel.

Pour chaque occurrence, choix au cas par cas, sans jamais modifier le flux de
contrôle (aucun nouveau `raise`, aucune valeur de retour changée) :

- si l'erreur peut révéler une vraie panne → journalisée avec le logger du
  module (`logger.warning`/`logger.error` pour les cas significatifs,
  `logger.debug` dans les boucles d'interrogation rapides du plateau physique
  ou pour les fallbacks fréquents/attendus, afin de ne pas inonder les logs) ;
- si le repli silencieux est voulu (valeur par défaut, fichier optionnel
  absent, nettoyage best-effort en fin de programme/thread, idiome de vidage
  de `queue.Empty`, saisie interactive interrompue, exception de contrôle de
  flux comme `BackMenuExit`/`ExitNicLink`) → conservé, avec un commentaire
  explicatif ajouté dans le corps du `except`.

**Résultat : 72 cas journalisés, 61 cas justifiés par commentaire.**

Cas le plus significatif : `nicsoft/niclink/driver.py`, `_fen_reader_loop()`
— tout le thread de lecture USB était silencieux ; passé en `logger.debug`
(boucle à 50ms, erreurs transitoires fréquentes, mais désormais visibles en
mode `NICLINK_LOG=DEBUG`). Autre cas notable : `nicsoft/core/config_manager.py`
— `load_config()` ignorait un `config.json` corrompu sans aucune trace nulle
part ; utilise maintenant le paramètre `on_error` déjà prévu par
`read_json_with_defaults()` pour journaliser, sans changer la valeur retournée
(les défauts restent utilisés comme avant).

**Fichiers modifiés (29) :**

`nicsoft/platform_utils.py`, `nicsoft/core/config_manager.py`,
`nicsoft/core/game_manager.py`, `nicsoft/engine/analyse.py`,
`nicsoft/engine/board_utils.py`, `nicsoft/engine/display.py`,
`nicsoft/engine/engine_manager.py`, `nicsoft/engine/pgn_manager.py`,
`nicsoft/modes/exercices/_catalogue.py`,
`nicsoft/modes/exercices/add_ouverture.py`,
`nicsoft/modes/exercices/eco_import.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/exercices/explore_book.py`,
`nicsoft/modes/exercices/import_lignes.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/opening_explorer/explorer_session.py`,
`nicsoft/modes/opening_explorer/llm_explainer.py`,
`nicsoft/modes/opening_explorer/sources.py`,
`nicsoft/modes/opening_explorer/tts_engine.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/retranscription/retranscription.py`,
`nicsoft/niclink/driver.py`, `nicsoft/niclink/hid_backend.py`,
`nicsoft/niclink/virtual_board.py`, `nicsoft/tests/e2e/conftest.py`,
`nicsoft/web/alchess.py`, `nicsoft/web/launcher.py`, `nicsoft/web/server.py`.

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
37 passed, 3 skipped (hardware). Suite e2e non lancée (nécessite Playwright
+ un serveur lancé depuis `~/NicLink`, hors périmètre du worktree).

# Changelog — Issue #260

## Rodent IV Linux : fin du faux dépôt imbriqué, documentation corrigée

`engines/rodent-iv` était enregistré dans l'index git comme un lien vers un
dépôt imbriqué (clone de `nescitus/rodent-iv`) sans jamais être déclaré comme
sous-module (`.gitmodules` ne le mentionnait pas). Conséquences : dossier vide
après un clonage frais, binaire local signalé en permanence comme
« modifié » sur la machine de dev, et documentation affirmant à tort que le
binaire Linux était inclus dans le dépôt (vrai seulement pour `lc0`).

**Changé :**

- `.gitignore` — ajout de `engines/rodent-iv/` : le dossier (dépôt git
  imbriqué + binaire compilé localement) n'est plus jamais suivi ni signalé
  comme modifié.
- Index git — `git rm --cached engines/rodent-iv` : retire l'entrée de
  dépôt imbriqué de l'index, sans toucher aux fichiers sur disque.
- `INSTALLATION/INSTALLATION_NICLINK.md` — ne prétend plus que le binaire
  Linux de Rodent IV est inclus dans le dépôt ; ajoute les instructions pour
  l'obtenir (clone + compilation de `https://github.com/nescitus/rodent-iv`,
  binaire à placer en `engines/rodent-iv/rodentIV` et à rendre exécutable) et
  corrige l'URL du dépôt source (était `nescior/Rodent_IV`, inexistant/non
  utilisé).
- `install.sh` — message clair quand `engines/rodent-iv/rodentIV` est
  absent (cas normal après un `git clone`), avec pointeur vers la section
  de compilation de la doc. Pas de téléchargement/compilation automatique.
- `make_release.sh` — commentaires corrigés : ne parlent plus de
  « sous-module » (qui n'a jamais existé pour ce chemin) mais de « dépôt git
  imbriqué, jamais déclaré en sous-module ». Comportement du script
  inchangé.

**Vérifié :**

- `find_rodent()` (`nicsoft/engine/engine_manager.py`) ne dépend que de
  l'existence du fichier `engines/rodent-iv/rodentIV` — inchangé par ce
  correctif, qui ne touche à aucun fichier Python.
- `make_release.sh` continue de supposer (comme avant) que le dépôt imbriqué
  réel, avec le binaire compilé, est présent sur la machine de build —
  c'est toujours la machine de dev d'Alain qui alimente le ZIP de release.

**À faire manuellement par Alain (voir commentaire de clôture de l'issue) :**
sauvegarde du binaire compilé avant la fusion sur la machine réelle, puis
vérification qu'il est toujours présent après.

# Changelog — Issue #259

## Factorisation du code dupliqué entre les fichiers du moteur (règle PRO-014)

L'audit signalait ~27 lignes identiques réparties sur plusieurs fichiers
(hypothèse initiale : `board_adapter.py`, `config_manager.py`,
`game_manager.py`, `analyse.py`, `board_utils.py`). Après vérification,
les blocs réellement dupliqués ne sont pas exactement ceux listés par
l'audit mais relèvent bien de la même cause : la lecture de
`data/config.json`, dupliquée localement — point que `config_manager.py`
documentait déjà lui-même comme "hors scope pour l'instant".

**Fusionné :**

- `nicsoft/core/config_manager.py` — nouvelle fonction
  `read_json_with_defaults(path, defaults, on_error=None)`, qui isole la
  logique « lit un JSON, fusionne sur des defaults, retombe sur les
  defaults si absent/invalide ». `load_config()` du module l'utilise
  désormais.
- `nicsoft/modes/pedagogique/pedagogique.py` et
  `nicsoft/modes/humain/human.py` — leurs `load_config()` locaux (mêmes
  defaults et même niveau de log qu'avant) délèguent maintenant la lecture
  JSON à `read_json_with_defaults()` au lieu de la dupliquer. Import
  `json` devenu inutile, retiré.
- `nicsoft/core/game_manager.py` — `launch_pedagogique()` et
  `launch_labo_libre()` contenaient le même bloc de 11 lignes (lecture de
  `engine_elo`/`engine_path` depuis `config.json`, byte pour byte
  identique, y compris le message de log). Extrait en
  `_read_engine_elo_and_path()`.

**Non fusionné (écarts de comportement réels, signalés sans forcer) :**

- Trois autres blocs de `game_manager.py` (exercice libre, drill, labo)
  lisent aussi `engine_elo`/`engine_path` depuis `config.json`, mais
  diffèrent sur des points fonctionnels : portée du `try/except` (un
  échec JSON désactive entièrement le moteur dans un cas, retombe sur des
  defaults dans un autre), ordre du repli `find_stockfish()`, et pour le
  mode labo l'`engine_elo` provient en réalité d'un dict de configuration
  runtime (pas du fichier). Les fusionner sans vérification individuelle
  aurait changé ces comportements.
- `nicsoft/engine/analyse.py` lit aussi `engine_path` depuis
  `config.json`, mais sans passer par la validation d'existence du
  chemin sur la plateforme courante (`_validated_engine_path`) — une
  différence de comportement pré-existante, potentiellement un écart à
  signaler séparément, pas touchée ici.
- `nicsoft/modes/humain/human.py` (fonction CLI historique, hors flux
  web) instancie `NicLinkManager` directement plutôt que via
  `nicsoft.core.board_adapter.create_board()` : ce chemin CLI n'a pas le
  callback `_board_lost_cb` (qui dépend de `nicsoft.web.server`), donc le
  fusionner aurait introduit une dépendance et un comportement nouveaux.
- `nicsoft/core/game_manager.py` (`_wait_initial_position_web` /
  `_wait_position_web`) ressemble à `wait_for_initial_position()` de
  `nicsoft/engine/board_utils.py`, mais la version web pilote
  `set_app_state`/`send_event` au lieu d'imprimer dans le terminal —
  différence de transport volontaire, non fusionnée.

**Tests** : `python -m pytest nicsoft/tests/` → 79 passed, 4 skipped
(tests matériel auto-skippés en l'absence d'USB), aucune régression.

# Changelog — Issue #256

## Téléchargement Rodent IV (Win) : délai d'attente et vérification d'intégrité

`on_download_rodent` (`nicsoft/web/server.py`) récupérait les 3 fichiers du
moteur Rodent IV Windows (`rodent-iv-x64.exe`, `msvcr120.dll`,
`msvcp120.dll`) via `urllib.request.urlretrieve`, sans délai d'attente ni
vérification, avant de les rendre utilisables (règles EXP-013 et SEC-022 de
l'audit).

Nouvelle fonction `_telecharger_fichier_rodent()` :
- télécharge via `urllib.request.urlopen(..., timeout=15)` (remplace
  `urlretrieve`, qui ne supporte aucun paramètre de délai) ;
- calcule l'empreinte SHA-256 du contenu pendant le téléchargement et la
  compare à une référence connue (`_RODENT_WIN_SHA256`) ;
- en cas d'écart, de délai dépassé, ou d'absence de référence connue pour
  un nom de fichier : supprime le fichier téléchargé (jamais installé) et
  laisse l'exception remonter — l'échec est signalé à l'interface via
  l'événement `rodent_download_result` existant (comportement inchangé,
  déjà adapté).

**Provenance des empreintes de référence** — calculées directement depuis
les fichiers déjà versionnés dans ce dépôt sous `engines/rodent-iv-win/`
(commit courant), qui sont exactement la même release que celle
re-téléchargée par ce handler pour les installations NSIS standalone
n'embarquant pas ces fichiers. Aucune empreinte n'a été calculée à partir
d'un téléchargement non vérifié. Les 3 fichiers du moteur ont pu être
couverts par cette référence versionnée — aucun fichier n'a dû être laissé
sans référence :
- `rodent-iv-x64.exe` → `39c879b2dfdaf0252e94db547397d95422fee76ea8bafa584bfdc03e4d648de5`
- `msvcr120.dll` → `ad32240bb1de55c3f5fcac8789f583a17057f9d14914c538c2a7a5ad346b341c`
- `msvcp120.dll` → `81fbc2824e73f0d101d91854694a52e79db0ffaadbb2a10deaaf47b3b7f9b2b0`

Tests ajoutés dans `nicsoft/tests/test_rodent.py` (4 nouveaux, aucun accès
réseau réel, `urllib.request.urlopen` mocké) :
- délai dépassé → `URLError` propagée, aucun fichier créé ;
- empreinte invalide → `ValueError`, fichier supprimé ;
- nom de fichier sans référence connue → refusé avant toute requête réseau ;
- empreinte valide → fichier écrit normalement.

Suite complète (hors `test_move_matching.py`/`test_players.py`, en échec
préexistant dans cet environnement faute du module `hid`, sans rapport
avec ce changement) : 74 passed, 4 skipped, aucune régression.

Backup pinné : `avant-issue256-rodent-timeout-integrite`.

## Dépendances : correctifs de sécurité, épinglage des versions flottantes, retrait de berserk

Audit `requirements.txt` : 4 paquets en retard de correctifs de sécurité
(SEC-001), 2 non épinglés (EXP-001), et `berserk` déclaré mais jamais
importé (reste de NicLink).

- **Correctifs de sécurité** (`pip-audit` : 11 vulnérabilités → 0) :
  - `setuptools` 69.1.1 → 84.1.0 (PYSEC-2025-49, PYSEC-2026-1918,
    PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w)
  - `wheel` 0.42.0 → 0.46.2 (CVE-2026-24049)
  - `python-socketio` 5.16.1 → 5.16.2 (PYSEC-2026-3042)
  - `Werkzeug` 3.1.7 → 3.1.9 (PYSEC-2026-4312)
- **Épinglage** des versions flottantes, sur la version installée/testée :
  - `numpy` `>=1.26.4` → `==2.5.4`
  - `edge-tts` `>=6.1.0` → `==7.3.1`
- **Retrait de `berserk`** (`requirements.txt` + tableau d'inventaire
  `ETAT_PROJET.md`) : aucun import dans le code, aucune référence dans les
  scripts d'installation (`1-Installer.bat`, `bootstrap_linux.sh`) ni
  l'installeur Windows.

Aucun conflit de compatibilité : `pip check` propre avec Flask 3.1.3 et
Flask-SocketIO 5.6.1 après les 4 montées de version. Suite de tests
complète (hors marqueur `hardware`) : 75 passed, 4 skipped.

`ETAT_PROJET.md` mis à jour en cohérence (tableau §5, versions
`python-socketio`/`Werkzeug`/`numpy`, ligne `berserk` supprimée).

# Changelog — Issue #212

## Tests e2e Exercices mis à jour pour le nouveau chemin de navigation

`test_exercices_liste_affichee` et `test_retour_depuis_exercices`
(`nicsoft/tests/e2e/test_smoke_e2e.py`) ciblaient encore le bouton direct
"Exercices" du menu principal, retiré au commit e648146 (issue #141,
réorganisation "Ouvertures"). Le chemin actuel comporte 2 étapes : clic sur
le bouton du wrapper `#wrap-ouvertures` (mène à `#screen-ouvertures`), puis
clic sur la carte `.outil-card-clickable` portant
`onclick="_menuCardLaunch('exercices', this)"` (mène à `#screen-exercices`).

Ajout d'un helper `go_exercices(page)` qui suit ce chemin en 2 étapes avec
des sélecteurs indépendants de la langue (même approche que le fix #208) :
- `#wrap-ouvertures button` — id déjà unique, pas de filtre sur le texte.
- `.outil-card-clickable[onclick*="'exercices'"]` — fragment d'attribut
  `onclick`, indépendant des libellés traduits ("📖 Openings"/"📚 Exercises"
  en anglais, langue par défaut de l'environnement de test).

Vérifié : aucune autre référence à l'ancien sélecteur
`button, has_text="📚 Exercices"` dans le fichier. Le bouton "← Menu" de
retour depuis `#screen-exercices` (ligne ~873 de `index.html`) est du texte
brut sans `data-i18n`, donc déjà indépendant de la locale — inchangé.

Suite `nicsoft/tests/e2e/test_smoke_e2e.py` complète : 12 passed, 1 skipped
(hardware), aucune régression.

Backup pinné : `avant-fix-e2e-exercices-navigation-issue212`.

# Changelog — Issue #201

## Suppression du code mort dupliqué (modes pédagogique et labo)

Suppression de deux fichiers orphelins, non importés nulle part dans le
code (aucun `import`, aucune référence dans les scripts `.sh`/`.bat`/`.ps1`,
aucune référence dans `.github/`) :

- `nicsoft/modes/pedagogique/__main__ (pedagogique).py` (1691 lignes) —
  nom de fichier non conforme (espace + parenthèses), donc non importable
  comme module Python de toute façon.
- `nicsoft/modes/labo/__main__labo.py` (409 lignes).

Comparaison ligne à ligne avec les fichiers canoniques réellement utilisés
(`pedagogique.py`, importé par `nicsoft/core/game_manager.py`, et `labo.py`,
importé par le même fichier ainsi que par `nicsoft/modes/labo/__main__.py`) :
les deux fichiers canoniques sont des évolutions strictement plus complètes
des fichiers supprimés (mêmes fonctionnalités + i18n, `RodentEngine`,
pipeline de précalcul du coup moteur, `kill_switch`, `BackMenuExit`, etc.).
Aucune portion de logique utile n'a été identifiée comme présente
uniquement dans les fichiers supprimés — le reste des différences est de la
plomberie CLI obsolète (ancien point d'entrée `main()`/`argparse`/`input()`
préexistant à l'architecture web actuelle).

`py_compile` OK sur les fichiers canoniques après suppression.

Backup pinné : `avant-suppression-code-mort-201`.

# Changelog — Issue #200

## Rapatrier socket.io et chess.js en local

- Téléchargé `socket.io.min.js` (v4.7.2) et `chess.min.js` (v0.10.3) dans
  `nicsoft/web/static/vendor/socket.io/` et `nicsoft/web/static/vendor/chess.js/`.
- `index.html` référence désormais `/static/vendor/socket.io/socket.io.min.js`
  et `/static/vendor/chess.js/chess.min.js` au lieu de cdnjs.cloudflare.com.
- Testé : démarrage serveur Flask OK, page servie sans requête vers cdnjs,
  handshake Socket.IO fonctionnel, fichiers vendor servis en HTTP 200.

## Issue #181 — Vérification version Python dans l'installeur NSIS (essai2)

- `installer-exe/alchess_setup.nsi` : nouvelle fonction `CheckPythonVersionWarning`, appelée juste après détection réussie de Python (SecPython, toutes stratégies : `py -0p`, PATH, scan des dossiers standards) et avant la création du venv. Avertit — sans bloquer — si le Python détecté est une pré-publication (suffixe `rc`/`a`/`b` dans la version complète, ex. `3.15.0rc1`) ou une version ancienne (< 3.10).
- Cas non couvert par la comparaison existante (`CompareVersionToMinimum`) : elle ne compare que "X.Y" (ex. "3.15") au minimum requis (3.12), donc une RC comme `3.15.0rc1` passait la vérification sans que son suffixe soit examiné — cause du bug constaté (Python 3.15rc1 : `hidapi` ne compile pas faute de MSVC, aucun wheel précompilé n'existant pour une RC).
- Ajout de `ExtractFullVersionFromPythonOutput` (garde le suffixe complet de la version, contrairement à `ExtractVersionFromPythonOutput` qui tronque à "X.Y") et de la macro `StrFunc` `StrStr` (recherche de sous-chaîne).
- `MessageBox MB_OKCANCEL` non bloquante : affiche la version détectée, recommande Python 3.12/3.13 stable avec lien vers python.org, l'utilisateur peut continuer quand même (IDCANCEL → Abort propre).
- Non appelée après `InstallPython312NSIS` (installation via winget) : cette voie installe toujours une 3.12 stable, jamais concernée.
- Vérifié : `makensis -V4 alchess_setup.nsi` compile sans erreur (exit 0).

## Issue #170 — llm_explainer : préciser le joueur et interdire les coups futurs dans le prompt

- `nicsoft/modes/opening_explorer/llm_explainer.py` : `_build_user_prompt` identifie désormais le camp qui vient de jouer (Blancs/Noirs, déduit du FEN) et l'inclut explicitement dans le prompt envoyé au LLM ("Les Blancs viennent de jouer : e4"). Ajout d'une consigne explicite interdisant de mentionner les coups futurs de l'adversaire, pour corriger le comportement où le LLM expliquait la réponse probable de l'adversaire au lieu du coup joué.
- Cache LLM vidé (`data/explorer_cache.json`) pour forcer la régénération des explications avec le nouveau prompt.
- Suite de l'issue #168.

# Changelog — issue #148

## Opening Explorer — flèches SVG illustrant les coups mentionnés par le LLM

- `nicsoft/modes/opening_explorer/llm_explainer.py` : prompt système enrichi
  (FR/EN/DE) pour demander au LLM d'ajouter une ligne `[FLECHES: e2-e4, ...]`
  (`[ARROWS: ...]` / `[PFEILE: ...]` selon la langue, même tag interne
  `FLECHES|ARROWS|PFEILE` accepté au parsing) ; ajout de `extract_arrows(text)`
  qui retire cette ligne et retourne la liste des flèches (2 à 4 max, cases
  validées a-h/1-8, from == to ignoré). `get_explanation()` et
  `get_chat_response()` retournent désormais `(texte, flèches)` ; le cache
  disque stocke `{"text": ..., "arrows": [...]}` (rétrocompatible avec les
  anciennes entrées `str`).
- `nicsoft/web/server.py` : `explorer_explanation` et `explorer_chat_response`
  émettent désormais `{"text": ..., "arrows": [["e2","e4"], ...]}`.
- `nicsoft/web/templates/index.html` : `#expl-board` enveloppé dans un
  conteneur `position:relative` avec un `<svg id="expl-arrows">` en
  surimpression (`pointer-events:none`) et un marker `#expl-arrowhead`.
- `nicsoft/web/static/app.js` : `explDrawArrows(arrows)` dessine des flèches
  rouges semi-transparentes (`rgba(232,69,96,0.75)`, épaisseur ~8% d'une
  case) entre les centres des cases, en tenant compte de `_explFlipped`.
  `explClearArrows()` vide le SVG (en conservant `<defs>`) ; appelé dans
  `explorer_state`, `explLoad()` et avant chaque nouveau dessin.

py_compile OK sur `llm_explainer.py` et `server.py` ; `node --check` OK sur
`app.js`.

