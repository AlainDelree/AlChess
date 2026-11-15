# Changelog — issue #340

## Lichess : signal visible sur l'échiquier dès que l'adversaire quitte la partie, et signal distinct quand la réclamation devient possible

Essai réel du 15/11/2026 (partie contre un humain, Alain jouait les noirs) : le bandeau de #334 est bien apparu, mais pendant les 85s avant réclamation possible, aucun signal physique — et plusieurs défauts sont apparus une fois la réclamation devenue possible/exercée.

### Point 1 — signal dès le départ de l'adversaire

`LichessGame._apply_opponent_gone()` déclenche désormais `_signal_opponent_gone_departure()` dès le PREMIER événement `opponentGone(gone=true)` d'une période d'absence : bip simple (si `config.json::lichess_beep_opponent_move` est cochée) + LED PARTIELLE persistante (nouveau pattern, voir point 2). Reste allumé jusqu'au retour de l'adversaire, à l'acquittement « J'ai vu » ou à la fin de la partie.

### Point 2 — signal distinct à la réclamation possible, motifs retenus

Deux patterns LED, réalisables avec la seule primitive disponible pour un affichage persistant (`set_all_leds`, pattern statique — pas de clignotement, voir « non vérifié » plus bas) :
- **Départ** (nouveau) : `opponent_gone_departure_led_pattern()` / `_RANKS_3_4_LIT` / `_RANKS_5_6_LIT` — seulement les **2 rangs centraux** du camp adverse (les plus proches du milieu de l'échiquier).
- **Réclamation possible** (inchangé, réutilisé de #331/#334) : `opponent_half_led_pattern()` / `_RANKS_1_4_LIT` / `_RANKS_5_8_LIT` — la **moitié complète** (4 rangs) du camp adverse, avec le bip double déjà existant.

Le pattern complet est visuellement plus étendu que le partiel : on distingue les deux sans lire l'écran.

### Point 3 — cadre sur l'échiquier de l'écran

`#board-wrapper` reçoit la classe `board-opponent-gone-frame` (orange/or, départ) ou `board-opponent-gone-frame-claimable` (rouge, réclamable), gérées par `app.js::_lichessUpdateOpponentGoneFrame()`, appelée depuis le handler `socket.on("lichess_opponent_gone", ...)` et depuis le clic sur « J'ai vu » (cadre purement local, suit le signal bip/LED — contrairement au bandeau texte qui reste affiché après ce clic, comportement #334 inchangé). CSS ajouté dans `main.css`. Les boutons et le bandeau existants ne changent pas.

### Point 4 — retour de l'adversaire

- LED/bip : `_apply_opponent_gone()` éteint désormais le signal dès que `_opponent_gone_departure_signaled` OU `_opponent_gone_claimable` était vrai (**corrigé** — avant cette issue, l'extinction ne se faisait que si la réclamation était déjà devenue possible : la LED du simple signal de départ serait restée allumée indéfiniment si l'adversaire revenait avant ce délai).
- Écran : toast `lichess.adversaire_revenu` (3 langues) affiché quand `gone` passe de vrai à faux.
- Retour au menu : `app.js`, handler `socket.on("app_state", ...)`, appelle désormais `_lichessHideStatusBanners()` (qui nettoie aussi le cadre) à **toute** arrivée réelle sur le menu, pas seulement via le chemin `game_over` normal — **lacune corrigée au passage** : le chemin `back_menu` envoie `game_over` avec `skip=true`, qui ignore volontairement cet appel (`if (data.skip) return;`), donc rien ne nettoyait jamais ces banners/le cadre sur un retour au menu en cours de partie avant ce correctif (risque de cadre orange/rouge résiduel visible au démarrage d'un AUTRE mode, `#board-wrapper` étant partagé entre tous les modes).

### Point 5 — priorité au coup

Nouvelle méthode `_apply_opponent_gone_led_state(reason)` : si `self._awaiting_physical_replication` est vrai (coup adverse en cours d'affichage via `_start_opponent_replication_wait`/`set_led` additif, pas encore confirmé), la pose du pattern LED du signal est **différée** (seul le bip, qui ne partage aucune ressource LED, est émis normalement) ; `_check_replication()` rappelle cette même méthode juste après avoir confirmé le coup et éteint ses LED, ce qui **rétablit** le signal encore dû. Le seul point de conflit identifié dans `game.py` est celui-ci : l'affichage du coup de l'utilisateur lui-même n'utilise aucune LED (il le voit directement sur le plateau physique), et `_start_opponent_replication_wait` pose ses deux LED de façon additive (`set_led`, qui préserve le pattern déjà affiché) — seule l'extinction de `_check_replication()` écrasait le signal. Les signaux pré-existants de #331 (nulle proposée par l'adversaire, fin de partie provoquée par l'adversaire) ne sont PAS couverts par cette restauration : leur extinction par le cycle de LED du coup suivant était déjà le mécanisme de sortie voulu dès #331 (documenté dans le code existant) — changer ce comportement sortait du périmètre de cette issue.

### Point 6 — journal dédié

Chaque pose/extinction de LED (départ, réclamable, ou différée pendant l'affichage d'un coup) écrit une ligne `state_change` avec sa raison, via le helper factorisé `_set_opponent_alert_leds()`/`_clear_opponent_alert_leds()`/`_apply_opponent_gone_led_state()`. Déjà couvert par les tests existants (`"LED allumées" in content`) et par les nouveaux tests de ce fichier.

### Point 7 — tests sans connexion réelle

Aucune recherche d'adversaire, aucune partie, aucun jeton réel n'a été utilisé — tout est simulé (faux transport Lichess `FakeTransport`, faux plateau `_AlertBoard`, garde réseau `conftest.py` active, serveur de test lancé uniquement avec `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`).

- `nicsoft/tests/test_issue340_lichess_opponent_signal.py` (nouveau, 9 tests) : signal de départ une seule fois (y compris à 0s), unicité du signal réclamable malgré des événements répétés (y compris plusieurs à 0s), nouveau départ après retour qui redéclenche bien, extinction au retour pendant la phase départ seule, priorité au coup adverse affiché puis rétablissement du signal, aucun signal après réclamation réussie (victoire et nulle).
- `nicsoft/tests/test_issue334_lichess_opponent_claim.py` (modifié) : 3 tests ajustés pour refléter le nouveau comportement (signal de départ en plus du signal réclamable, donc bip/LED supplémentaires attendus) + 1 test ajouté (bonne moitié du pattern partiel selon l'orientation).
- `nicsoft/tests/e2e/test_issue340_lichess_opponent_signal_e2e.py` (nouveau, 4 tests Playwright, exécutés avec succès) : cadre absent par défaut, cadre départ puis réclamable puis disparition au retour (+ toast), disparition sur « J'ai vu » sans attendre le serveur, absence du cadre après retour au menu — les deux orientations ne changent rien côté écran (le cadre suit `gone`/`claimable`, pas la couleur de l'utilisateur).
- Suite complète : `1371 passed, 84 skipped` (aucune régression), suite e2e complète : `139 passed, 1 skipped`.

### Point 8 — moitié allumée côté noirs (bug d'orientation)

**Établi, pas une hypothèse** : `_RANKS_1_4_LIT`/`_RANKS_5_8_LIT` (posées par #331) allumaient en réalité l'**inverse** de ce que leur nom et leur commentaire annonçaient. La convention « indice i du tableau de 8 chaînes = rangée physique (i+1) » est confirmée par **trois lectures indépendantes et concordantes** du code existant, jamais modifiées par cette issue :
1. `hid_backend.py::set_all_leds(r1, r2, ..., r8)` — docstring explicite : « r1..r8 = rangées 1 à 8 ».
2. `driver.py::_led_worker_loop`, commande `"set_all"` : `set_all_leds(str(arr[0]), str(arr[1]), ..., str(arr[7]))` — `arr[0]` passé comme `r1`, `arr[7]` comme `r8`.
3. `driver.py::build_led_map_for_move`/`square_cords` (affichage normal des coups, jamais mis en cause) : `led_map[rang - 1]`.

Avec cette convention, l'ancien `_RANKS_1_4_LIT = ["00000000"]*4 + ["11111111"]*4` avait ses 4 premières chaînes (rangs 1-4) à `0` et les 4 dernières (rangs 5-8) à `1` : il allumait donc les rangs 5-8, pas 1-4 comme son nom l'indique — l'inverse exact de `_RANKS_5_8_LIT`. `opponent_half_led_pattern()` demandait pourtant la bonne constante nommée (`_RANKS_1_4_LIT` pour un adversaire blanc, `_RANKS_5_8_LIT` pour un adversaire noir) : **seul le contenu des deux constantes était faux**, pas la logique d'orientation. C'est exactement ce qui explique l'observation d'Alain (noirs) : le code croyait allumer les rangs 1-4 (camp adverse, blanc) mais allumait physiquement les rangs 5-8 (son propre camp).

**Preuve par le journal** citée dans l'issue : « LED allumées — moitié adversaire (rangs 1-4 (blancs)) » — avec l'ancien code, ce texte de journal (qui décrit l'INTENTION, lue depuis le nom de la constante) correspondait à une pose physique des rangs 5-8. Après correction (contenu des deux constantes échangé, noms et `opponent_half_led_pattern()` inchangés), le texte de journal et le pattern physiquement posé coïncident.

**Corrigé** pour les deux couleurs : nouveaux tests paramétrés `test_signal_reclamable_bonne_moitie_selon_orientation`/`test_signal_depart_bonne_moitie_selon_orientation` (`white`→`_RANKS_5_8_LIT`/`_RANKS_5_6_LIT`, `black`→`_RANKS_1_4_LIT`/`_RANKS_3_4_LIT`) vérifient le pattern RENVOYÉ par les fonctions — ils ne peuvent pas, par construction (sans échiquier physique), vérifier la case qui s'allume PHYSIQUEMENT ; c'est la lecture croisée des trois points de code ci-dessus qui établit que le pattern renvoyé correspond désormais à la bonne rangée physique. **Reste hypothèse** : confirmation sur le vrai échiquier (aucun matériel disponible pour cette issue).

Même mécanisme, donc même correctif, pour les autres signaux de #331 qui réutilisent `_light_opponent_half()`/`opponent_half_led_pattern()` : abandon, nulle proposée, temps écoulé, mat (tous `self._light_opponent_half(...)` dans `_apply_game_state`/`_finalize`) — corrigés par la même modification des deux constantes, pas de code dupliqué.

### Point 9 — un seul signal par transition

**Cause établie** : `_apply_opponent_gone()` remettait `_opponent_gone_claimable`/`_opponent_gone_signal_acked` à `False` à **chaque** événement `opponentGone(gone=true)`, y compris les événements répétés de la MÊME période d'absence (Lichess en renvoie environ toutes les 5s, y compris après que le délai affiché a atteint 0). Quand le délai était déjà à 0, chaque répétition remettait `_opponent_gone_claimable` à `False` puis `_push_opponent_gone_state()` le repoussait immédiatement à `True` dans la même frappe, ce qui faisait croire à une NOUVELLE transition vers « réclamable » et redéclenchait le signal (bip double + LED) — observé exactement 3 fois (06:04:41/42/47) dans la partie réelle.

**Corrigé** : `is_new_period = not self._opponent_gone` calculé AVANT de marquer `self._opponent_gone = True` ; `_opponent_gone_claimable`/`_opponent_gone_signal_acked`/`_opponent_gone_departure_signaled` ne sont réarmés que si `is_new_period` est vrai. `claim_win_in_seconds` continue d'être mis à jour à chaque événement de la même période (c'est le countdown légitime envoyé par Lichess, pas un signal à réarmer).

Tests ajoutés : événements répétés à 0s après un délai qui diminue normalement, événements répétés dès le premier événement à 0s, et un nouveau VRAI départ après un retour qui redéclenche bien le signal (l'unicité ne doit jamais empêcher un second départ légitime).

### Point 10 — pas de signal après sa propre réclamation

**Cause établie** : `_handle_claim_action()` appelait `_safe_claim_call(claim_fn, request_label)` sans jamais marquer `self._user_initiated_end = True` (contrairement à `_request_resign_or_abort()`, qui le fait). Quand le flux confirmait ensuite la fin de partie (statut Lichess brut, ex. `"timeout"` — identique à celui d'un abandon de temps subi), `_finalize()` ne pouvait pas distinguer cette fin de celle causée par l'adversaire et rallumait le signal LED/bip « fin de partie provoquée par l'adversaire » — observé dans la partie réelle (réclamation acceptée à 06:04:48, signal redonné juste après).

**Corrigé** : `_handle_claim_action()` pose `self._user_initiated_end = True` dès que `_safe_claim_call()` renvoie vrai (réclamation acceptée par Lichess). `_finalize()` exclut déjà `_user_initiated_end` de son calcul de `opponent_caused_end` — aucun autre changement nécessaire : les LED encore allumées (signal réclamable) sont éteintes par la branche `else` déjà existante, aucun bip supplémentaire n'est émis.

Tests ajoutés (victoire ET nulle) : vérifient `game._user_initiated_end is True` après l'action, puis `opponent_caused_end is False`, `game_over["opponent_cause_key"] is None`, une seule extinction de LED, aucun bip supplémentaire.

## Non vérifié sans le vrai échiquier

- Pattern LED partiel (2 rangs centraux) réellement visible et distinct du pattern complet sur le matériel réel.
- Priorité au coup/rétablissement du signal (point 5) en conditions réelles (latence USB, lecture FEN).
- Confirmation physique de la bonne moitié allumée pour chaque couleur (point 8) — établi par lecture croisée du code, pas par essai matériel.
- Clignotement : non implémenté — la seule primitive disponible pour un affichage persistant (`set_all_leds`) pose un pattern statique ; un clignotement aurait exigé un fil dédié gérant lui-même l'alternance marche/arrêt, jamais testé sur le vrai échiquier pour cette issue. Les deux patterns statiques (partiel/complet) ont été jugés suffisants pour distinguer les deux signaux.

## Fichiers modifiés

- `nicsoft/modes/lichess/game.py` — constantes LED corrigées + nouvelles (`_RANKS_1_4_LIT`/`_RANKS_5_8_LIT` corrigées, `_RANKS_3_4_LIT`/`_RANKS_5_6_LIT` ajoutées), `opponent_gone_departure_led_pattern()` (nouveau), `_set_opponent_alert_leds()`/`_light_opponent_departure()`/`_apply_opponent_gone_led_state()`/`_signal_opponent_gone_departure()` (nouveaux), `_apply_opponent_gone()` (réécrit pour l'unicité par période), `_check_replication()` (rétablissement du signal), `_handle_claim_action()` (`_user_initiated_end`).
- `nicsoft/web/static/app.js` — cadre `#board-wrapper` (`_lichessUpdateOpponentGoneFrame`), toast de retour, nettoyage générique au retour au menu, acquittement local du cadre sur « J'ai vu ».
- `nicsoft/web/static/css/main.css` — classes `.board-opponent-gone-frame`/`-claimable`.
- `nicsoft/web/static/i18n/{fr,en,de}.json` — clé `lichess.adversaire_revenu`.
- `nicsoft/tests/test_issue340_lichess_opponent_signal.py` (nouveau), `nicsoft/tests/e2e/test_issue340_lichess_opponent_signal_e2e.py` (nouveau), `nicsoft/tests/test_issue334_lichess_opponent_claim.py` (ajusté).
