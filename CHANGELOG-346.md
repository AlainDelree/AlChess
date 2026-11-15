# Changelog — issue #346

## Lichess : « Contre un humain » à gauche, « Contre l'IA » à droite

Écran de choix de la partie Lichess, carte « Adversaire » : les deux boutons
sont désormais affichés dans l'ordre « Contre un humain » (toujours
présélectionné) puis « Contre l'IA », au lieu de l'inverse — pour que le
choix par défaut depuis #344 soit aussi le premier affiché.

- `nicsoft/web/templates/index.html` : les deux `<button>` `#cfg-lichess-opponent-human`/`#cfg-lichess-opponent-ai` sont intervertis dans le markup (classe `selected` et logique de présélection inchangées). `app.js` ne dépend que des `id`, aucune modification nécessaire côté JS ni i18n.
- `nicsoft/tests/e2e/test_issue344_lichess_rated_e2e.py` : les tests existants n'identifient les boutons que par `id`, donc aucun n'était affaibli par l'inversion ; nouveau test `test_contre_un_humain_affiche_a_gauche_de_contre_ia` qui vérifie l'ordre réel des deux boutons dans le DOM et que « Contre un humain » reste présélectionné.
