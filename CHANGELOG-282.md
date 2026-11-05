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
