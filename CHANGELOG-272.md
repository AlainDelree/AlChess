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
