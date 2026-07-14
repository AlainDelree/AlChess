# CONTEXTE_METIER.md — Rôle Spec-Métier

Fiche de rôle pour le CCL spécialisé **Métier** (pattern Chef + Specs MVC, §15
du BRIDGE_AGENT_DOC). Reflète la structure réelle vérifiée le 14 juillet 2026.

## Périmètre (dossiers dédiés)

- `nicsoft/core/` — gestion de partie, adaptation Core ⇄ Transport
- `nicsoft/engine/` — moteurs UCI, joueurs, utilitaires échecs
- `nicsoft/modes/` — logique des modes de jeu
- `nicsoft/niclink/` — driver échiquier, backend USB, verrous
- `nicsoft/web/alchess.py` + `server.py` — orchestration & machine d'état

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `core/game_manager.py` | Gestion de partie (coups, historique, état) |
| `core/board_adapter.py` | Adaptation Core ⇄ Transport |
| `engine/engine_manager.py` | Détection + wrappers Stockfish/Maia/Rodent |
| `engine/players.py`, `board_utils.py`, `pgn_manager.py`, `analyse.py` | Joueurs, utils python-chess, PGN, analyse |
| `niclink/driver.py` | Driver Chessnut Air, `_fen_reader_thread` (50 ms) |
| `niclink/hid_backend.py` | Backend USB hidapi Python pur |
| `web/alchess.py` | Chef d'orchestre (boucle principale) |
| `web/server.py` | Flask-SocketIO, machine d'état `_app_state`, queues |

## Principes d'architecture (déjà documentés)

- **`board.move_stack` = source de vérité** de l'historique des coups.
  `chess.Board(fen)` efface `move_stack` → reconstruire depuis l'historique.
- **Contention USB** : tout accès USB passe par `_fen_reader_thread`. Verrous
  `_fen_lock` (exclusif à `get_fen()`) et `_led_lock` (LEDs). Ne jamais appeler
  `get_fen()` depuis un autre thread.
- **`action_queue` à vider** (`get_nowait`) avant d'attendre une position
  physique, sinon d'anciennes actions parasitent l'attente.
- Boucles de polling : toujours `time.sleep()` ≥ 0.05 s. Threads LED en daemon.
- Ordre `setoption` Rodent impératif : Personality → UCI_LimitStrength → UCI_Elo.
