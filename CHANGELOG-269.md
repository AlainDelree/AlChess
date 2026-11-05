# CHANGELOG-269 (issue #269)

## Échiquier virtuel : ajout de la méthode disconnect (plus de faux avertissement à la sortie des modes)

- `nicsoft/niclink/virtual_board.py` : ajout de `VirtualBoard.disconnect()`, no-op comme ses méthodes voisines (`turn_off_all_leds`, `beep`, etc.) — rien à fermer côté USB en mode virtuel.
- Cause : `nicsoft/core/game_manager.py` appelle `nl_inst.disconnect()` en sortie d'explorateur d'ouvertures, d'exercices et de drill (3 endroits, non modifiés — l'appel côté appelant était correct). Avec un échiquier virtuel, cette méthode n'existait pas : `AttributeError` avalée par un `except` qui journalisait un faux avertissement « Déconnexion échiquier échouée ... object has no attribute disconnect » à chaque sortie de ces modes en mode virtuel.
- Vérification des autres méthodes de `NicLinkManager` appelées par `game_manager.py` ou les modes sur l'objet échiquier (`get_fen`, `turn_off_all_leds`, `signal_lights`, `connect`, `start`...) : toutes déjà présentes dans `VirtualBoard` ou appelées uniquement après vérification que l'instance est physique (`connect()` dans `server.py`, gardé par `hasattr(nl_inst, "nl_interface")`). Aucune autre méthode manquante.
- `nicsoft/tests/test_virtual_board.py` (nouveau) : crée un `VirtualBoard` et appelle `disconnect()` sans erreur.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 120 passed, 10 skipped.
