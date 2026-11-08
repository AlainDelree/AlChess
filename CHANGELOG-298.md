# Issue #298 — Ménage 1 : mode Labo libre, éléments d'interface morts, journal d'abandon, actions GitHub, modèles d'échiquier au README

- Suppression du mode Labo libre, mort depuis #278/#295 : `nicsoft/core/game_manager_modes/labo_libre.py` supprimé, import/export retirés de `game_manager.py`, branche `start_labo_libre` retirée d'`alchess.py`, tests dédiés retirés de `test_issue295_mode_cleanup.py` (modes Humain et Labo conservés).
- Suppression des éléments d'interface morts (issue #279) :
  - zone `#countdown` (index.html) et tout le code JS associé, mort depuis l'origine (`startCountdown` jamais appelé) : variable `countdownTimer`, fonctions `startCountdown`/`stopCountdown`, appels résiduels, règle CSS `#countdown { display:none !important; }`.
  - bouton `#btn-pause-abandonner` (écran pause), toujours masqué par la classe `game-pause-hidden-init` et jamais révélé par le JS — redondant avec le bouton « Abandonner » actif pendant la partie. Classe `.game-pause-hidden-init` retirée (plus utilisée).
  - doublon d'id `#labo-feedback` : `document.getElementById` ne cible toujours que le premier élément (zone centrale) ; la zone latérale (`.labo-feedback-side`) n'était jamais affichée ni remplie. Zone latérale et sa règle CSS retirées, la zone centrale conservée inchangée.
- `nicsoft/modes/humain/human.py` : l'échec d'`await_move()` dû au `kill_switch` (pause/abandon/retour menu) est désormais journalisé en `info` au lieu d'`error` ; toute autre cause reste en `error`. Logique de jeu inchangée.
- `.github/workflows/python-app.yml` : `actions/checkout` v4→v7 et `actions/setup-python` v3→v7 (dernières versions majeures stables, toutes deux `node24`, vérifiées sur les releases officielles des deux actions). Version Python et reste du workflow inchangés.
- `README.md` (FR/EN, section Systèmes et matériel) : remplacement de l'avertissement Air+ par la liste des modèles reconnus par `hid_backend.py` (Chessnut Air, Air Plus, Go, et deux anciens identifiants sans nom commercial), sans affirmer qu'ils sont tous testés ; commande de vérification `lsusb` conservée.
- `CONTEXTE.md` : retrait de la mention « code mort » de la liste « À traiter » (traitée par cette issue).
