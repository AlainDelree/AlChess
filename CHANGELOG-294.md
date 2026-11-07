# Changelog — Issue #294

## Documentation : attribution de NicLink dans le README et THIRD_PARTY_NOTICES.md

AlChess est dérivé de NicLink (https://github.com/nicvagn/NicLink, GPL-3.0),
mais ni le README ni aucun fichier du dépôt ne le mentionnait, et les
composants tiers redistribués (moteurs Maia/lc0, Rodent IV, bibliothèques
Windows, bibliothèques JS, jeu de pièces SVG) n'étaient listés nulle part.

- **`README.md`** : la section « License »/« Licence » (anglais et
  français) attribue maintenant NicLink et son auteur nicvagn, précise que
  les modifications sont © 2026 Alain Delrée, et renvoie vers
  `THIRD_PARTY_NOTICES.md` pour le détail des composants tiers.
- **`THIRD_PARTY_NOTICES.md`** (nouveau, bilingue comme le README) : tableau
  de chaque composant tiers redistribué (rôle, fichiers, origine, version,
  licence). Versions établies en exécutant les binaires (`lc0`/`lc0.exe`
  via Wine/`uci`, `rodent-iv-x64.exe` via Wine/`uci`) ou en lisant l'en-tête
  du fichier (Socket.IO). Jeu de pièces SVG comparé octet à octet (tracés
  `d=`) au jeu « cburnett » officiel de Lichess (`lichess-org/lila`) :
  identique sur les 12 fichiers → attribué à Colin M. L. Burnett, triple
  licence GPL v2+/BSD/GFDL. Informations non vérifiables marquées
  « non établie » plutôt que supposées (version d'OpenBLAS, de
  `msvcr120.dll`/`msvcp120.dll`, de `chess.min.js`, des poids Maia).
- **`nicsoft/tests/test_third_party_notices.py`** (nouveau) : garde-fou sans
  réseau — chaque fichier binaire suivi par git dans `engines/maia` et
  `engines/rodent-iv-win` doit être cité (nom exact ou motif) dans
  `THIRD_PARTY_NOTICES.md`, pour qu'un futur binaire ajouté ne reste pas
  sans notice.

Aucun binaire, ni `CONTRIBUTING.md`, ni `.audit.json` n'a été modifié.
Suite complète (hors tests `hardware`) : 421 passed, 74 skipped.
