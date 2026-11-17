# AlChess — Moteurs (`engine_manager.py`)

Lire avant toute tâche touchant la détection ou l'exécution des moteurs UCI.

`find_stockfish/lc0/maia_weights(elo)/rodent()` + `*_available()` ; `server.py` met en cache au démarrage et émet `*_status` ; le front grise ou replie sur le premier disponible.

- **Stockfish** : Linux système/PATH/`engines/stockfish`, Win `engines/stockfish*.exe` ; détection = présence.
- **Maia** : `engines/maia/lc0` et `lc0.exe` + poids `maia-*.pb.gz` (suivis par git).
- **Rodent IV** : Linux `engines/rodent-iv/` ignoré par git (binaire compilé localement, plus un sous-module depuis #260) ; Win `engines/rodent-iv-win/` : 3 fichiers **suivis par git**, téléchargement tout-ou-rien vérifié par SHA-256 (#286). Détection = handshake UCI ; `setoption` Personality→UCI_LimitStrength→UCI_Elo.
