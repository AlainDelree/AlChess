# Changelog — Issue #284

## CONTEXTE.md : mise à jour de la section « État actuel » et de l'architecture après les découpages récents

La section « État actuel » datait du 21 juillet 2026 et citait comme
chantier l'échec de `git submodule update --init` sur clone frais, réglé
depuis l'issue #260.

- **« État actuel »** réécrite avec la date du jour, en se basant sur les
  tags git (`v1.3.2`, 18 août 2026, dépôt ~220 commits plus avancé depuis,
  pas de nouvelle release taguée) et sur `CHANGELOG.md` (rien d'inventé).
- **Retiré** : le chantier des sous-modules (réglé, issue #260).
- **Ajouté** : dépendances à jour et épinglées ; découplage jeu/interface
  via `ihm_port.py` ; retrait de l'outil de sauvegarde `backup_manager` ;
  journalisation des erreurs auparavant silencieuses ; tests de garde
  ARC-001 à découverte automatique ; hook pre-push (~40 s) ; découpages en
  façades de `game_manager`, `engine_manager`, `explore_book`/`eco_import`,
  `llm_explainer` ; reprise de session de retranscription à chaque
  ouverture ; régressions d'affichage de l'extraction des styles en ligne
  (issue #279) ; éléments d'interface morts signalés mais non traités
  (bouton d'abandon de la pause, compte à rebours, id dupliqué du labo —
  issue #279) ; pointeur vers la section ARC-004 pour les gros fichiers.
- **Marqué « non revérifié »** (matériel/Windows, non vérifiable depuis le
  dépôt) : rangement HH ignoré si déconnexion USB silencieuse, race LEDs,
  WAIT_FISH lent intermittent, statut « Connected » trompeur, finitions
  Windows.
- **Architecture** : ajout de la description en façade de `game_manager.py`
  (réexporte `core/game_manager_modes/`, issue #278), de `explore_book.py`/
  `eco_import.py` (modules par rôle dans `modes/exercices/`) et de
  `llm_explainer.py` (modules dans `modes/opening_explorer/`). Descriptions
  de `engine_manager.py` et `ihm_port.py` vérifiées, toujours exactes,
  inchangées.
- Ligne de tête : date et branche (`worktree-issue-284`) mises à jour.
- Section « Gros fichiers conservés (ARC-004) » non touchée, `.audit.json`
  non modifié. Fichier passé de 55 à 58 lignes.
- Suite de tests complète hors `hardware` (`pytest -m "not hardware"`) :
  370 passed, 73 skipped — aucun fichier Python modifié.
