Dans l'ecran menu, Langue FR: 
=============================
- Au démarrage du menu, lors de la recherche de l'échiquier "Check Board" doit etre en francais.
- ⚠ Board not detected — check USB, power on the board and restart
- Bouton Reconnect board
- Si mode virtuel coché, les textes des descriptions des bouton de menu Retranscrire et Outils Exercices se chevauchent.

Dans l'ecran menu, Langue EN: 
=============================
- Les textes des descriptions des boutons de menu sont en francais.
- La Checkbox "Mode sans échiquier physique" est en francais.
- Le bouton Quitter est en francais
- En mode virtuel ce message s'affiche en haut: Mode sans échiquier — choisissez un menu

Pédagogique virtuel ecran config, Langue FR:
============================================
- Analyse coup -> checkbox "Enabled" a mettre en francais
- Afficher les coups légaux checkbox "Enabled" a mettre en francais

Pédagogique virtuel, Langue FR:
===============================
- Dans le cadre de droit en haut,au dessus des nom des joueurs on a "Free game" comme titre
- Danss tour en cours: Magnus's turn (White)
- Bouton "Offer Draw" 
- Lors du clic sur le bouton Retour au menu, la modal est en anglais: "Quit and return to menu?" et le bouton "Quit" mais pas "Annuler".
- Lors d'une pause pédagogique "? Mistake e4 — 185cp loss" à traduire.
- Lors clic sur Abandonner la modal qui apparait à comme titre "Resign?", le bouton "Confirm resignation".
 
 
Pédagogique virtuel ecran config, Langue EN:
============================================
- Cadre Engine, clic sur Maia : La combobox de choix de niveau est en francais et les textes "Niveau Maia" et "Joue comme un humain de ce niveau" aussi.
- Cadre Engine, clic sur Rodent, tout est en francais.
- Pour la pause pédagogique, la combobox est en francais.
- Le titre du cadre Options est en francais.
- la checkbox sound beep est "Activé".

Pédagogique virtuel, Langue EN:
===============================
- Training Cadre: Gukesh contre Rodent 1300-> mettre "contre" en francais.
- Cadre Option à droite a le titre en francais et le bouton pause aussi.
- Comme plus haut, la combobox de la pause pédagogique est en francais.
- Dès que je joue un coup, l'historique se met à jours et on voit apparaitre "Blancs" "Noirs"
- Lors du clic sur pause, le bouton "Changer de couleur" est à traduire.
- Lors du clic sur pause, le titre du cadre Navigation est à traduire.

Autres
======
- Dans pédagogique, ecran config, pour l'analyse, la checkbox doit etre modifier.  Actuellement, elle s'appele, disabled, mais son on coche disabled on a l'analyse et si on décoche disabled on a pas l'analyse, ca devrait etre le contraire.
- Dans pédagogique, écran config, si le parametre analyse est décoché, la combobox pause pédagogique devrait se griser et se degriser si on le coche
- Erreur connexion échiquier : Poids Maia 1400 introuvables dans ~/NicLink/engines/maia/
Traceback (most recent call last):
  File "/home/alain/NicLink/nicsoft/web/alchess.py", line 428, in _run_pedagogique
    game = Game(
           ^^^^^
  File "/home/alain/NicLink/nicsoft/modes/pedagogique/pedagogique.py", line 286, in __init__
    raise RuntimeError(f"Poids Maia {maia_elo} introuvables dans ~/NicLink/engines/maia/")
RuntimeError: Poids Maia 1400 introuvables dans ~/NicLink/engines/maia/
[Pédagogique]
  Joueur: Alireza
  Couleur: black
  Moteur: maia
  ELO SF: 2650
  ELO Maia: 1500
  ELO Rodent: 1300
  Rodent simple: non
  Pause: imprecision
  Analyse: off
  Bip: on
  Coups légaux: off
  
- Dans pédagogique virtuel, je n'arrive pas a jouer quand j'ai les noirs: 
[Pédagogique]
  Joueur: Magnus
  Couleur: random
  Moteur: stockfish
  ELO SF: 1450
  ELO Maia: 1300
  ELO Rodent: 2300
  Rodent simple: non
  Pause: imprecision
  Analyse: on
  Bip: on
  Coups légaux: off

