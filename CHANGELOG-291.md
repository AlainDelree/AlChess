# Changelog — Issue #291

## Suite #289 : ne jamais arrêter ModemManager lorsque l'application est lancée sans échiquier

L'isolation faite par la #289 ne couvrait que l'ouverture du navigateur ;
l'arrêt/la relance de ModemManager (service système touché au démarrage
pour éviter toute interférence USB avec l'échiquier) restait inconditionnel.
Conséquence : chaque exécution des tests de bout en bout (ALCHESS_SKIP_BOARD=1),
donc chaque crochet de pre-push, pouvait arrêter ModemManager sur le poste
de l'utilisateur sans jamais le relancer (le serveur de test est terminé
par la méthode standard, pas par les sorties propres du menu).

- **`nicsoft/web/alchess.py`** : `_stop_modem_manager()` et
  `_start_modem_manager()` ne font plus rien quand `ALCHESS_SKIP_BOARD=1`
  est positionnée — un lancement sans échiquier n'a aucune raison de
  toucher à un service système. `nicsoft/platform_utils.py` reste un simple
  adaptateur système, inchangé.
- Comportement normal (variable absente) strictement inchangé : arrêt au
  démarrage, relance aux deux sorties propres (`quit` et `KeyboardInterrupt`).
- **Tests** : `nicsoft/tests/test_modem_manager_skip_board.py` (nouveau) —
  `stop_modem_manager`/`start_modem_manager` mockées, aucun serveur démarré,
  aucun accès au vrai service.
- **Documentation** : `TESTS.md` et `CONTEXTE.md` précisent que
  `ALCHESS_SKIP_BOARD=1` empêche aussi tout arrêt/relance de ModemManager.

### Vérification manuelle suggérée
- Pendant une exécution de la suite e2e (`pytest nicsoft/tests/e2e/`) :
  `systemctl status ModemManager` avant/après — doit rester inchangé.
- Pendant une session normale (`python -m nicsoft.web`, sans
  `ALCHESS_SKIP_BOARD`) : `systemctl status ModemManager` doit passer
  inactif au démarrage, puis actif après une sortie propre (bouton
  Quitter ou Ctrl+C).
