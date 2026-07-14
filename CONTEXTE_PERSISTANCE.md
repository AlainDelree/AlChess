# CONTEXTE_PERSISTANCE.md — Rôle Spec-Persistance

Fiche de rôle pour le CCL spécialisé **Persistance** (pattern Chef + Specs MVC,
§15 du BRIDGE_AGENT_DOC). Reflète la structure réelle vérifiée le 14 juil. 2026.

## Périmètre (dossiers dédiés)

- `nicsoft/utils/backup_manager.py` — sauvegardes pinnées / normales
- `nicsoft/engine/pgn_manager.py` — import / export PGN
- `nicsoft/config.py` — chemins centralisés (`APP_DIR`, `DATA_DIR`…)
- `data/` — config JSON, bases ECO/ouvertures, `players.json`
- `games/` — parties PGN sauvegardées
- `backups/` (hors dépôt) — dossiers `pinned/` et `normal/`

## Fichiers & chemins clés

| Élément | Rôle |
|---------|------|
| `config.py` | `APP_DIR` auto-détecté ; `DATA_DIR`, `GAMES_DIR`, `LOGS_DIR`, `ENGINES_DIR` |
| `utils/backup_manager.py` | Backups (`--pin`, `--list`, `--pin-existing`, `--unpin`) |
| `engine/pgn_manager.py` | `build_tmp_path()`, `build_final_path()`, sauvegarde dans `GAMES_DIR/<mode>/<type>` |
| `data/config.json` | Config runtime de l'appli |
| `data/mes_lignes.json`, `data/eco_*.tsv`, `eco_hierarchy.json` | Ouvertures / ECO |
| `games/{Human,Stockfish,Transcription,externe,tmp}/` | PGN par catégorie |

## Conventions de persistance

- **Backup pinné AVANT toute modification majeure** :
  `python -m nicsoft.utils.backup_manager --pin --label "avant-<desc>"`.
  Les backups pinnés (`📌_…`) ne sont jamais supprimés par la rotation ;
  les normaux tournent automatiquement (5 conservés).
- Ne jamais coder de chemin en dur : passer par `nicsoft/config.py`
  (plus de dépendance à `~/NicLink` en dur).
- PGN : fichier temporaire (`build_tmp_path`) puis chemin final
  (`build_final_path`) rangé par mode / type dans `games/`.
