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
