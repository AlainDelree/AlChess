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
