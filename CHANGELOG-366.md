# Changelog — Issue #366

## Partie 1 — Regrisage générique des boutons `data-needs-board` à la déconnexion

Défaut préexistant signalé par #365 (hors périmètre à l'époque) : `board_ok`
réactivait génériquement tous les boutons `[data-needs-board]`, mais
`board_error`/`board_reconnecting` ne les regrisait jamais de façon
générique — seuls les deux boutons Lichess traités par #365
(`btn-start-lichess`, `btn-start-lichess-puzzle`) suivaient l'état de
l'échiquier en direct. Un bouton comme l'entrée menu Humain contre Humain
pouvait donc rester cliquable après une déconnexion survenue en cours de
session.

- `nicsoft/web/static/app.js` : la (dés)activation générique de
  `[data-needs-board]` (respectant `data-physical-only` en mode virtuel)
  déplacée dans `_applyBoardBadge()` — appelée par les trois évènements
  `board_ok`/`board_error`/`board_reconnecting`, donc regrisage/réactivation
  symétriques, sans second mécanisme. Le forEach ad hoc du handler
  `board_ok` et le bloc de réactivation du retour au menu (`app_state`,
  état `"menu"`) sont retirés au profit de ce mécanisme unique.
- `nicsoft/web/templates/index.html` : `#btn-start-hh` (bouton « Démarrer
  la partie » de l'écran de config Humain contre Humain, jusqu'ici régi par
  un bloc dédié distinct dans `_applyBoardBadge()`) porte désormais aussi
  `data-needs-board data-physical-only` — unifie son état `disabled` sur le
  mécanisme générique (son explication/`title` reste spécifique).
- Tests : `nicsoft/tests/e2e/test_issue366_regrisage_echiquier_e2e.py` —
  échiquier connecté puis déconnecté puis reconnecté : entrée menu Humain
  contre Humain et `#btn-start-hh` suivent l'état en direct ; bouton Lichess
  de #365 (`#btn-start-lichess`, partie réelle) inchangé ; `board_reconnecting`
  regrise comme `board_error`. Le contournement devenu inutile dans
  `test_issue365_lichess_sans_echiquier_e2e.py::_reset_base` (réactivation
  manuelle de `.menu-btn-humain` avant chaque test, nécessaire tant que le
  regrisage générique n'existait pas) est retiré.
- Documentation : `docs/contexte/architecture.md` (1 ligne — règle
  `data-needs-board`/`_applyBoardBadge()`). `CONTEXTE.md` inchangé.

## Partie 2 — Bascule automatique sur « Sur l'écran » sans échiquier

Dans la carte « Problèmes » de l'écran Lichess, sans échiquier connecté, le
mode « Échiquier » restait sélectionné par défaut (ou mémorisé) et « Jouer
un problème » restait grisé avec une explication jusqu'au clic manuel de
l'utilisateur sur « Sur l'écran ». Alain préfère que l'écran bascule seul,
pour que le problème reste jouable immédiatement.

- `nicsoft/web/static/app.js` : `_lichessPuzzleMode` (mode effectif,
  affiché et utilisé pour lancer un problème) et `_lichessPuzzlePreferredMode`
  (nouvelle — préférence mémorisée dans `localStorage`, changée uniquement
  par un clic explicite via `selectPuzzleModeLichess()`) sont désormais
  distincts. Nouvelle `_lichessPuzzleSyncDisplayMode()` : sans échiquier,
  bascule l'effectif sur `"virtual"` (jamais écrit dans `localStorage`) ;
  à la (re)connexion, rétablit l'effectif sur la préférence mémorisée.
  Appelée à l'ouverture de l'écran Lichess (`app_state`, état
  `"config_lichess"`) et à chaque changement d'état de l'échiquier (dans
  `_applyBoardBadge()`, donc sur `board_ok`/`board_error`/
  `board_reconnecting`). Un clic manuel reste toujours respecté et mémorisé
  comme avant #366, y compris « Échiquier » sans échiquier (l'explication
  reste alors affichée) — mais une déconnexion ULTÉRIEURE pendant que
  l'écran reste ouvert rebascule l'affichage sur « Sur l'écran », la
  préférence mémorisée restant elle inchangée.
- Tests : `nicsoft/tests/e2e/test_issue366_puzzle_mode_autobascule_e2e.py`
  — sans échiquier, « Sur l'écran » sélectionné et « Jouer un problème »
  actif sans écraser la préférence mémorisée ; reconnexion rétablit le mode
  mémorisé puis une nouvelle déconnexion rebascule l'affichage ; clic
  manuel sur chaque mode respecté et mémorisé, y compris sans échiquier.
  `test_issue365_lichess_sans_echiquier_e2e.py::
  test_bascule_echiquier_met_a_jour_les_boutons_sans_recharger` adaptée :
  une déconnexion survenant APRÈS une sélection manuelle de « Échiquier »
  bascule désormais aussi sur « Sur l'écran » (seule la partie Lichess
  réelle, toujours liée à l'échiquier physique, reste grisée) — comportement
  intentionnel de cette partie, pas une régression.
  `test_issue366_regrisage_echiquier_e2e.py` (partie 1) simplifié en
  conséquence : ne vérifie plus l'état du bouton de mode « Échiquier » des
  problèmes (désormais couvert par ce nouveau fichier), seulement le
  bouton partie Lichess réelle comme garde-fou #365.
- Documentation : `docs/contexte/lichess.md` (entrée #365 complétée d'une
  phrase sur la distinction préférence/mode effectif). `CONTEXTE.md`
  inchangé.
