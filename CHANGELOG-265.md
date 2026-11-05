# Changelog — Issue #265

## Journal de l'application : ne plus enregistrer la bannière de démarrage des moteurs d'échecs

Le logger `chess.engine` (utilisé en interne par python-chess pour relayer en
WARNING la sortie stderr des moteurs UCI externes — bannière lc0/Maia au
démarrage : version, backend de calcul, poids chargés, cœurs...) est
désormais relevé au niveau `ERROR` dans `_setup_logging()`
(`nicsoft/web/alchess.py`). Choix assumé : on accepte de ne plus journaliser
la sortie stderr brute des moteurs (niveau WARNING chez python-chess), au
profit d'un journal applicatif lisible — les échecs réels de démarrage ou
d'arrêt inattendu d'un moteur restent signalés indépendamment, via les
`logger.error(...)` explicites d'`engine_manager.py` (sur le logger
`"niclink"`), qui ne dépendent pas de la sortie stderr relayée par
python-chess. Rien d'autre n'est modifié : ni le niveau global (`WARNING`),
ni les autres loggers. Verrouillé par `nicsoft/tests/test_logging_config.py`.
