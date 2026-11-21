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
  contre Humain et `#btn-start-hh` suivent l'état en direct ; boutons
  Lichess de #365 (`#btn-start-lichess`, `#btn-start-lichess-puzzle`)
  inchangés ; `board_reconnecting` regrise comme `board_error`. Le
  contournement devenu inutile dans
  `test_issue365_lichess_sans_echiquier_e2e.py::_reset_base` (réactivation
  manuelle de `.menu-btn-humain` avant chaque test, nécessaire tant que le
  regrisage générique n'existait pas) est retiré.
- Documentation : `docs/contexte/architecture.md` (1 ligne — règle
  `data-needs-board`/`_applyBoardBadge()`). `CONTEXTE.md` inchangé.
