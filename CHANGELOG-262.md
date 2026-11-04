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
