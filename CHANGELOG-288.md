# Changelog — Issue #288

## Sécurité : corriger plutôt que supprimer les exceptions ignorées en silence et les ouvertures d'adresses non vérifiées

L'audit sécurité (ruff/bandit) signalait deux familles de lignes dans
`nicsoft/` : des blocs `except Exception: pass`/`continue` sans trace
(S110/S112, bandit B110/B112) et des ouvertures d'adresse avec `urllib`
sans vérification de schéma (S310, bandit B310). Conformément à la
consigne du projet (jamais de `# noqa`/`# nosec`), chaque site a été
corrigé dans le code plutôt que la ligne d'audit supprimée.

- **Famille A (57 sites, ~18 fichiers)** : chaque bloc a été traité au cas
  par cas après lecture du code réellement appelé (python-chess, `queue`,
  hidapi, `chess.engine`, `subprocess`, `requests`...) :
  - resserrement en exception(s) précise(s) quand une seule cause
    documentée existe (ex. `ValueError` de `int()` sur une saisie
    utilisateur, `ValueError`/`IndexError` de `NicLinkManager.set_led()`,
    `ValueError` de `queue.Queue.task_done()` appelé en double par course
    avec le thread `_led_worker_loop`) ;
  - trace `logger.debug(...)` (formatage différé) ajoutée en conservant
    la capture large quand le bloc est un nettoyage « best effort » aux
    causes d'échec trop hétérogènes pour une liste précise (LEDs/bip
    côté `pedagogique.py`/`human.py`/`labo.py`, `quit()` d'un moteur UCI) ;
  - dans les boucles d'interrogation rapides du plateau (lecture FEN,
    attente d'action), resserrement sans trace pour ne pas spammer les
    logs à chaque passage.
  - Resserrer une capture générique change ce qui est propagé : voir le
    commentaire de clôture de l'issue #288 pour le détail site par site
    des exceptions qui ne sont plus avalées silencieusement.
- **Famille B (5 sites)** : `nicsoft/utils/net_safety.py` (nouveau module
  neutre, n'importe jamais `nicsoft.web`) expose `ensure_https(url)`,
  utilisée avant l'ouverture des adresses distantes constantes de
  Wikipedia (`download_eco_wiki.py`), Claude/OpenAI (`llm_provider.py`,
  2 sites) et edge-tts (`tts_engine.py`). `nicsoft/web/launcher.py`
  (adresse locale `127.0.0.1` uniquement, jamais distante) vérifie
  schéma et hôte précisément avant d'interroger le serveur Flask local
  pendant son démarrage. `nicsoft/web/server.py` (Rodent IV Windows,
  issue #286) n'a pas été retouché.
  - ruff/bandit continuent de signaler ces 5 lignes (ils ne reconnaissent
    pas une vérification faite juste avant l'appel) : aucune suppression
    n'a été faite pour autant — voir le commentaire de clôture de
    l'issue #288.
- **Tests** : `test_net_safety.py` (vérification de schéma, adresses
  `file:`/`ftp:`/http distant refusées, https accepté, sans accès
  réseau) et `test_family_a_narrowed_exceptions.py` (comportement
  conservé quand l'exception réellement attendue se produit, pour les
  sites où une exception précise remplace la capture générique).
- Hors périmètre, non modifié : processus lancés avec chemin partiel ou
  sans shell (S603/S605/S607) et aléa non cryptographique (S311).
