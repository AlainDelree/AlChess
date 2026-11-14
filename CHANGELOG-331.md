# Changelog — Issue #331

## Lichess : bip optionnel quand l'adversaire joue, LED + bandeau quand il abandonne, propose la nulle ou termine la partie

Essai réel d'Alain le 14/11/2026 : environ cinq minutes passées devant
l'échiquier physique à attendre le coup de l'adversaire humain sans voir
que celui-ci avait abandonné — l'écran affichait la fin de partie, mais
rien ne le signalait sur l'échiquier ni par le son.

**Règle absolue respectée à la lettre** : aucune recherche, partie ni défi
réel sur lichess.org à aucun moment de ce travail. Le vrai jeton d'Alain
n'a jamais été lu ni utilisé — tous les tests utilisent un faux
transport/client et un faux pilote de plateau (LED/USB simulés), jamais de
connexion réelle. Le garde réseau de
`conftest.py::_guard_no_real_lichess_network` reste actif et inchangé.

### Point 1 — Case « Bip quand l'adversaire joue »

- `core/config_manager.py` : nouvelle clé `lichess_beep_opponent_move`
  (défaut `False` — aucun réglage de son existant ne couvrait déjà ce cas,
  seule `tts_enabled` s'en approchait sans rapport fonctionnel) ; écriture
  atomique existante (`save_config`) réutilisée sans modification, jamais
  de contact avec `lichess_token`.
- `templates/index.html` : case à cocher dans le panneau Actions pendant
  la partie (`#lichess-beep-toggle-row`), visible seulement en partie
  Lichess (IA ou humain — un seul écran de jeu `LichessGame` pour les
  deux) ; `static/app.js` : `lichessToggleBeep()` sauvegarde immédiatement
  via `config_save` (même mécanisme que la synthèse vocale) ; état restauré
  à l'ouverture de l'écran de configuration Lichess (`config_get` déjà
  appelé à ce moment).
- Traductions ajoutées dans `i18n/{fr,en,de}.json`.
- `modes/lichess/game.py::_maybe_beep_opponent()` relit `load_config()` à
  CHAQUE évènement (jamais mis en cache) : cocher/décocher en cours de
  partie change le comportement dès le coup suivant, sans redémarrage.

### Point 2 — Sons : bip matériel de l'échiquier, pas le navigateur

Méthode choisie et pourquoi : réutilisation du bip matériel existant de
l'échiquier Chessnut (`nl_inst.beep()`, déjà utilisé pour le premier coup
de l'IA) plutôt que le son du navigateur (Web Audio `playBeep()` déjà
présent dans `app.js`, utilisé par l'Explorateur d'ouvertures) ou un outil
système (`paplay`/`aplay`). Un bip hors navigateur est fiable par
construction, y compris onglet en arrière-plan ou minimisé — la fiabilité
réelle du son d'onglet en arrière-plan dépend du navigateur et n'a pas pu
être mesurée ici (pas d'instance de navigateur avec onglet caché
disponible dans ce bac à sable) ; le bip matériel évite la question
entièrement, et s'entend directement là où Alain regarde (l'échiquier).
Aucune nouvelle dépendance, aucune modification de `driver.py` (les
méthodes utilisées — `beep()`, `set_all_leds()`, `turn_off_all_leds()` —
existaient déjà).

- `game.py::_hardware_beep()` : bip simple, ou double (deux bips espacés
  de 0,3 s, émis par un petit fil dédié — jamais de `time.sleep()` dans la
  boucle de jeu) pour un signal distinct.
- Bip simple à chaque coup de l'adversaire (`_apply_new_moves`, jamais
  pour un coup de l'utilisateur — vérifié par couleur du coup). Le bip
  inconditionnel existant pour le tout premier coup de l'IA (utilisateur
  noirs) est laissé inchangé, non rattaché à la case (comportement déjà en
  place avant cette issue).
- Bip double à l'apparition d'une offre de nulle adverse et à toute fin de
  partie provoquée par l'adversaire (voir point 3).
- Non vérifié sur le vrai échiquier (aucun matériel disponible pour cette
  issue) : le minutage exact des deux bips et leur perception sonore
  réelle restent à confirmer par Alain.

### Point 3 — Signal LED (moitié de l'échiquier côté adversaire)

- `driver.py` confirmé INCHANGÉ : `set_all_leds()` (déjà existant) poste
  un pattern de 8 rangées en **un seul paquet USB**, via la queue
  fire-and-forget déjà en place — aucune limitation à une case à la fois.
  `signal_lights()` (déjà existant) utilise les mêmes motifs de moitié de
  plateau mais s'éteint automatiquement après 1,5 s ; ce comportement ne
  convenait pas (il faut rester allumé jusqu'à acquittement), donc
  `game.py` appelle directement `set_all_leds()` avec les mêmes 8 chaînes
  binaires que `signal_lights(2)`/`signal_lights(3)`.
- `game.py::opponent_half_led_pattern()` : choisit la bonne moitié (rangs
  1-4 ou 5-8) selon la couleur jouée par l'utilisateur.
- Allumage, toujours (indépendant de la case à cocher) : offre de nulle de
  l'adversaire, et toute fin de partie provoquée par l'adversaire (abandon,
  temps écoulé, mat, nulle acceptée — jamais pour un abandon/une
  annulation demandés par l'utilisateur, ni pour une nulle qu'il vient
  lui-même d'accepter, ni pour un mat qu'il délivre lui-même avec son
  propre coup physique).
- Extinction : réponse explicite à la nulle (accepter/refuser, comme
  avant) ; bouton « J'ai vu » sur le bandeau de fin de partie, ou tout
  retour au menu depuis cet écran (acquittement implicite) ; au plus tard,
  à la libération de l'échiquier par le lanceur
  (`game_manager_modes/lichess.py`, déjà existant, inchangé) ou au
  `reset()` de la partie suivante (driver.py, inchangé) — jamais de LED
  restante d'une partie à l'autre.
- L'attente d'acquittement bloque le fil du LANCEUR de la partie (celui
  qui attend déjà la partie entière de façon synchrone, comme tous les
  autres modes), jamais le fil socketio ni la boucle menu — `_finalize()`
  elle-même reste non bloquante (calcule seulement `opponent_caused_end`),
  pour que les appels directs existants (tests, et tout appelant futur)
  continuent de retourner immédiatement.
- Affichage normal du coup adverse (2 cases) non perturbé dans le cas
  courant ; limite connue, non corrigée : si l'adversaire propose la nulle
  EXACTEMENT au moment de son propre coup (un seul évènement Lichess), le
  signal de moitié de plateau remplace temporairement les 2 cases du coup
  — cas rare, non vérifié sur le vrai plateau.

### Point 4 — Bandeau de fin de partie provoquée par l'adversaire

- `templates/index.html` : `#lichess-opponent-end-banner` (réutilise la
  classe `.lichess-info-banner` existante) sur l'écran de fin de partie,
  avec bouton « J'ai vu » (clé i18n `lichess.jai_vu`) — affiché seulement
  quand `game_over` porte `opponent_caused_end=true`, avec un court texte
  de cause (`opponent_cause_key` : abandon/temps écoulé/mat/nulle/
  générique).
- Le bandeau de nulle proposée existant (`#lichess-draw-offer-banner`,
  Accepter/Refuser) est inchangé et sert toujours pour ce cas précis.

### Point 5 — Journal de partie

- Une ligne `[STATE]` par bip effectivement émis
  (`bip émis — <raison> (n/total).`) et par commande LED envoyée
  (`LED allumées —`/`LED éteintes —` avec la raison) dans le journal dédié
  de la partie (`GameLog`, déjà existant, inchangé) — rien de secret.

### Point 6 — Tests (nouveau fichier, 21 tests, aucun réseau ni matériel réel)

`nicsoft/tests/test_issue331_lichess_opponent_alerts.py` :

- bip émis/non selon la case, y compris basculée en cours de partie
  (effet immédiat, sans redémarrage) ;
- mémorisation de la case, sans aucun effet sur `lichess_token` ; valeur
  par défaut décochée ;
- LED de la bonne moitié pour abandon, nulle proposée, temps écoulé, mat
  de l'adversaire — pour les deux orientations (utilisateur blancs et
  noirs) ;
- acquittement (`lichess_ack_game_over`, réponse à la nulle, ou
  `back_menu`) qui éteint le signal ;
- aucun bip ni LED pour un coup, un abandon, une acceptation de nulle ou
  un mat provoqués par l'UTILISATEUR lui-même (régression détectée et
  corrigée pendant le développement : le mat délivré par le propre coup
  de l'utilisateur déclenchait à tort l'alerte) ;
- présence des lignes de journal attendues.

Toute la suite Lichess existante (536 tests) et l'ensemble de la suite du
projet (1241 tests) ont été rejoués après ces changements — aucune
régression.

### Non vérifié sans l'échiquier physique ni une vraie partie

- Le son réel du bip matériel (volume, perceptibilité à distance) et le
  minutage du bip double.
- L'allumage effectif et la bonne moitié sur le vrai plateau Chessnut
  (le pilote USB bas niveau, `hid_backend.py`, n'a pas été modifié et
  n'a pas pu être exercé avec du vrai matériel).
- Le comportement réel du son du navigateur en onglet arrière-plan — non
  mesuré, d'où le choix du bip matériel qui évite la question.
