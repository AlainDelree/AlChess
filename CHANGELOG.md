# Changelog — Issue #255

# Changelog — Issue #306

# Issue #306 — Lichess L0 : jeton personnel dans les paramètres, jamais envoyé au navigateur, et bouton « Tester la connexion »

- **Contexte** : première étape de la connexion à Lichess (plan validé par Alain, étape « L0 »). Objectif unique : enregistrer un jeton personnel Lichess et vérifier qu'il fonctionne — aucune partie, aucun nouveau mode de jeu. Le jeton suit exactement le mécanisme de la clé API LLM mis en place par l'issue #304 (jamais renvoyé au navigateur, indicateur de présence + indice 4 derniers caractères, remplacement, suppression explicite) ; les règles d'échappement de l'issue #303 s'appliquent au texte renvoyé par Lichess.

- **Configuration** (`nicsoft/core/config_manager.py`) : nouvelle clé `lichess_token` dans `DEFAULT_CONFIG`, valeur par défaut `""`.

- **Nouveau module** `nicsoft/modes/lichess/` (n'importe jamais `nicsoft.web`, ARC-001 — couvert automatiquement par `test_no_web_import.py`) :
  - `client.py` : `test_token(token)` interroge `POST https://lichess.org/api/token/test` (urllib standard, schéma vérifié par `nicsoft.utils.net_safety.ensure_https` avant tout appel, délai 10 s, `User-Agent: AlChess/<version>` via `importlib.metadata`, lecture de la réponse plafonnée à 64 Ko). Retourne un statut structuré : `ok` (compte, liste des scopes, `has_board_play`), `invalid`, `rate_limited` (HTTP 429), `network_error` (toute autre erreur réseau/HTTP). Le jeton n'apparaît jamais dans une exception journalisée.

- **Serveur** (`nicsoft/web/server.py`) :
  - `on_config_get` : retire `lichess_token` de la config avant émission, ajoute `has_lichess_token` (booléen) et `lichess_token_hint` (4 derniers caractères si longueur ≥ 12, sinon vide) — même logique que `llm_api_key`.
  - `on_config_save` : `lichess_token` vide = inchangé ; valeur non vide = remplacement (espaces autour retirés) ; `lichess_token_delete: true` = suppression explicite. Jamais réémis dans `config_saved`.
  - Nouvel événement `lichess_test_connection` : utilise le jeton tapé dans le champ (pas encore enregistré) si présent, sinon celui déjà en config ; appelle `client.test_token` dans un thread daemon (comme les autres appels réseau du serveur) et émet `lichess_test_result` au client concerné (`to=sid`). Toute exception inattendue est journalisée sans le jeton (seul le nom de la classe d'exception est loggé) et traduite en `{"status": "network_error"}`.

- **Paramètres (écran)** (`nicsoft/web/templates/index.html`, `nicsoft/web/static/app.js`, `nicsoft/web/static/css/main.css`) : nouvelle section « Lichess » entre l'Assistant LLM et la Synthèse vocale — champ masqué sans remplissage automatique (`#param-lichess-token`), indice « Jeton enregistré (…1234) » / « Jeton enregistré » / « Aucun jeton », bouton « 🗑 Supprimer le jeton », aide en trois phrases (créer un jeton sur lichess.org, lui donner au moins `board:play`, ne jamais le partager), bouton « Tester la connexion » (désactivé pendant la requête — un seul test à la fois) et zone de résultat. Le résultat (compte, scopes, avertissement si `board:play` manquant, limite de requêtes, jeton invalide, réseau indisponible) est toujours affiché via `textContent` — jamais `innerHTML` — car il contient du texte renvoyé par Lichess (issue #303).

- **i18n** (`fr.json`/`en.json`/`de.json`, mêmes clés dans les trois) : `parametres.lichess.titre`, `.aide1/.aide2/.aide3`, `.token`, `.token_placeholder`, `.jeton_enregistre` (`{suffix}`), `.jeton_enregistre_sans_indice`, `.aucun_jeton`, `.supprimer_jeton`, `.tester`, `.toast.jeton_supprime`, `.resultat.compte` (`{compte}`), `.resultat.board_play_ok`, `.resultat.board_play_manquant`, `.resultat.autres_droits` (`{droits}`), `.resultat.limite`, `.resultat.reseau`, `.resultat.invalide`. **La traduction allemande doit être relue par un germanophone** (traduction directe, non revérifiée par un locuteur natif).

- **CONTEXTE.md** : une ligne ajoutée dans « Principes techniques » (jeton Lichess toujours côté serveur, jamais journalisé ; aucun moteur/aide/livre ne doit tourner pendant une partie Lichess — fair-play, pour les étapes suivantes). Les deux lignes existantes sur les secrets/l'échappement ont été mises à jour (« futur jeton Lichess » → « jeton Lichess », maintenant implémenté).

- **Nouveau test de garde** `nicsoft/tests/test_issue306_lichess.py` (24 tests, sans réseau — `urllib.request.urlopen` mocké — ni matériel) : `test_token` (valide avec/sans `board:play`, invalide, réseau coupé, HTTP 429, autre erreur HTTP, schéma non-https refusé sans appel réseau, `User-Agent` correct) ; `config_get`/`config_save` (jamais le jeton, indicateur + indice, champ vide conserve, valeur remplace avec espaces retirés, suppression explicite, jamais d'écho) ; `lichess_test_connection` (jeton tapé prioritaire sur celui en config, aucun jeton du tout, exception inattendue jamais journalisée avec le jeton — capture des journaux) ; présence des nouvelles clés i18n dans `fr/en/de.json` ; `app.js` utilise bien `textContent` pour le résultat Lichess. Le test de garde d'échappement HTML existant (`test_issue303_html_escaping.py`) continue de passer sans modification.

- **Hors périmètre, non touché** : `driver.py`, `.audit.json`, `requirements.txt`, les modes de jeu existants (pédagogique/humain/exercices/retranscription/labo) ; aucune suppression d'outil de sécurité.

- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 680 passed, 77 skipped. Syntaxe JS vérifiée (`node --check app.js`) : OK. `py_compile` sur les fichiers Python modifiés : OK. Serveur réel démarré (`ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`) : page `/` et `/static/i18n/fr.json` servent bien la nouvelle section et les nouvelles clés ; arrêté proprement par son PID après vérification.

## Vérification manuelle restant à faire par Alain

Cette tâche n'a pas pu la faire elle-même : aucun navigateur piloté n'a été utilisé pendant ce traitement (vérification faite par requêtes HTTP directes sur le serveur de test), et surtout un vrai jeton Lichess est nécessaire pour les points 4 et 5.

1. Coller un faux jeton « lip_test1234567890abcd », enregistrer, rouvrir l'écran Paramètres : le champ doit être vide et l'indice afficher « …abcd ».
2. Cliquer sur « Tester la connexion » avec ce faux jeton : message de jeton invalide, sans erreur technique affichée.
3. Supprimer le jeton : l'indice doit revenir à « Aucun jeton ».
4. Avec un vrai jeton créé sur lichess.org avec le droit `board:play` : le nom du compte doit s'afficher et `board:play` doit être signalé présent.
5. Changer la langue en anglais puis en allemand : vérifier l'affichage de la section Lichess (et signaler toute formulation allemande à corriger — non revérifiée par un germanophone).

# Changelog — Issue #304

# Issue #304 — Sécurité de l'interface 2 : la clé API n'est plus envoyée au navigateur, et les routes HTTP à effet de bord vérifient leur origine

- **Contexte** : suite de la relecture de sécurité du 8 novembre 2026 (confirmée par la contre-vérification de l'issue #302). Deux constats : (1) la clé API LLM était renvoyée en clair au navigateur par `config_get` et réécrite telle quelle à chaque sauvegarde — tout script exécuté dans la page pouvait la lire ; (2) plusieurs routes HTTP n'exigeaient aucun contrôle d'origine ni d'hôte (`/toggle-autoupdate`, `/test/save-config`, `/logs`, `/debug/*`), alors que les connexions Socket.IO l'étaient déjà (`_is_allowed_origin`).

- **Clé API — plus aucun secret envoyé au navigateur** (`nicsoft/web/server.py`) :
  - `on_config_get` (événement `config_get`) ne renvoie plus `llm_api_key` : la clé est retirée de la config avant émission, remplacée par `has_llm_api_key` (booléen) et `llm_api_key_hint` (4 derniers caractères, seulement si la clé fait ≥ 12 caractères — sinon chaîne vide, pour ne pas donner d'indice exploitable sur une clé courte).
  - `on_config_save` (événement `config_save`) : un `llm_api_key` vide ne touche plus la clé existante (« champ vide = inchangée ») ; `llm_api_key_delete: true` l'efface explicitement ; une valeur non vide la remplace. Le stockage sur disque (`config_manager.save_config`, fusion + écriture atomique) n'a pas changé.
  - **Front** (`nicsoft/web/static/app.js`, `nicsoft/web/templates/index.html`) : le champ `#param-llm-api-key` reste toujours vide à l'affichage ; un indicateur `#param-llm-api-key-hint` affiche « Clé enregistrée (…1234) » ou « Aucune clé » (texte traduit, jamais la clé elle-même). Nouveau bouton explicite « 🗑 Supprimer la clé » (`parametresSupprimerCle()`, action `parametres_delete_key`) qui envoie `{llm_api_key: "", llm_api_key_delete: true}` sans toucher aux autres champs. `_explHasApiKey` (disponibilité du chat de l'Explorateur d'ouvertures) utilise désormais `data.has_llm_api_key` au lieu de tester la présence de la clé elle-même. Après chaque sauvegarde réussie, la page redemande `config_get` pour rafraîchir l'indice (clé remplacée/supprimée) sans jamais redemander la clé.
  - Recherche dans tout le serveur et l'interface : les seuls autres usages de `llm_api_key` sont des lectures internes côté serveur pour l'appel LLM lui-même (`_emit_explorer_explanation`, `_emit_explorer_chat_response`, `_emit_analyse_llm_response`, `llm_functions.py`, `llm_provider.py`) — jamais réémis au navigateur ; `llm_provider.py` documente déjà ne jamais journaliser la clé. Aucune autre fuite trouvée (pas de route, pas de journal, pas de config de test touchant cette clé — `/test/save-config` sert une config de test sans rapport, Pédagogique/HH/Retranscription).

- **Routes HTTP — contrôle d'origine et d'hôte** (`nicsoft/web/server.py`) :
  - Nouvelles fonctions `_is_allowed_host(host)` (compare à `127.0.0.1:<port>`/`localhost:<port>`, port fixé par `set_server_port()`/`start_server()`), `_require_allowed_origin()` et `_require_allowed_host()` (abort 403).
  - `POST /toggle-autoupdate` et `POST /test/save-config` : exigent désormais un `Origin` autorisé (même règle que Socket.IO, `_is_allowed_origin`) **et** un `Host` correct — 403 sinon, avant toute autre logique (y compris la vérification `TEST_MODE == "random"` de `/test/save-config`, qui reste inchangée par ailleurs).
  - `/logs`, `/debug/mark`, `/debug/mode` : exigent un `Host` correct (pas de contrôle d'Origin, ce sont des routes GET/navigation). `/debug/mark` garde son contrôle `DEBUG_MODE` existant, après le contrôle d'hôte.
  - `/` et les fichiers statiques restent ouverts, inchangés.
  - Le lien « logs » de l'en-tête et la case « Mises à jour automatiques » du menu fonctionnent normalement (requêtes même origine depuis un navigateur réel → Host/Origin corrects). Les tests e2e (Playwright, navigateur réel) ne sont pas affectés, pour la même raison — aucun test existant n'appelait ces routes sans en-tête réel.

- **Nouveau test de garde** `nicsoft/tests/test_issue304_security.py` (31 tests, client de test Flask, aucun matériel) : `_is_allowed_host` (127.0.0.1, localhost, étranger, mauvais port, absent, port serveur non fixé) ; `/logs`, `/debug/mode`, `/debug/mark` avec Host correct/étranger (et `DEBUG_MODE` forcé pour isoler le contrôle d'hôte) ; `/toggle-autoupdate` et `/test/save-config` avec les quatre combinaisons Origin/Host (absent, étranger, correct) ; `config_get` ne contient jamais `llm_api_key` (clé longue → indice, clé courte → pas d'indice, pas de clé) ; `config_save` (champ vide conserve, valeur remplace, suppression explicite, jamais d'écho de la clé dans `config_saved`) ; présence des nouvelles clés i18n dans `fr/en/de.json` ; analyse statique d'`app.js` (indicateur basé sur `has_llm_api_key`, plus aucune lecture de `data.llm_api_key` hors son indice).

- **i18n** (`fr.json`/`en.json`/`de.json`, mêmes clés dans les trois) : `parametres.llm.api_key_placeholder`, `parametres.llm.cle_enregistree` (`{suffix}`), `parametres.llm.cle_enregistree_sans_indice`, `parametres.llm.aucune_cle`, `parametres.llm.supprimer_cle`, `parametres.toast.cle_supprimee`. **La traduction allemande doit être relue par un germanophone** (traduction directe, non revérifiée par un locuteur natif).

- **CONTEXTE.md** : une ligne ajoutée dans « Principes techniques » (aucun secret envoyé au navigateur ; garde = nom du nouveau test).

- **Hors périmètre, non touché** : `driver.py`, `.audit.json`, `requirements.txt`, format de stockage de `config.json`, suppressions d'outil de sécurité.

- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 647 passed, 75 skipped. Syntaxe JS vérifiée (`node --check app.js`) : OK. `py_compile` sur les fichiers Python modifiés : OK.

## Vérification manuelle

Faite pendant cette tâche (serveur réel démarré avec `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1`, piloté par Playwright) :

1. Paramètres : saisie de `sk-test-1234567890`, enregistrement, réouverture → champ vide, indice « …7890 » affiché. ✅
2. Nouvel enregistrement avec le champ vide → l'indice « …7890 » reste inchangé. ✅
3. « Supprimer la clé » → l'indice devient « Aucune clé ». ✅
4. Lien « logs » de l'en-tête (ouverture dans un nouvel onglet, 200) et case « Mises à jour automatiques » du menu (bascule puis restauration) → fonctionnent normalement. ✅
5. Arrêt et relance du serveur (clé ressaisie puis process redémarré) → l'indice « …7890 » est toujours affiché après redémarrage (lu depuis `config.json` sur disque, jamais depuis l'ancienne session navigateur). ✅

# Changelog — Issue #303

# Issue #303 — Sécurité de l'interface 1 : tout texte venu de l'extérieur est échappé avant d'être inséré dans la page

- **Contexte** : relecture de sécurité du JS (8 novembre 2026, confirmée par la contre-vérification de l'issue #302) — du texte externe (joueur, serveur, fichier PGN, réponse LLM) était inséré via `innerHTML`/`insertAdjacentHTML` sans échappement ; `_pgnLibEsc` (seule fonction d'échappement existante) n'échappait pas les guillemets alors qu'elle sert dans des attributs `value="…"`. La connexion Lichess à venir apportera davantage de texte externe (noms, en-têtes, commentaires).
- **Fonction commune `esc()`** (`nicsoft/web/static/app.js`, tout en haut du fichier, avant tout usage) : échappe `& < > " '`, traite `null`/`undefined` comme `""`. `_pgnLibEsc` délègue désormais à `esc()` (échappe donc aussi les guillemets).
- **`markdownToHtml`** : échappe le texte (`esc(text)`) avant d'appliquer les remplacements de mise en forme (titres, gras, italique, paragraphes, retours à la ligne) — un texte contenant une balise s'affiche désormais comme texte, `**gras**` reste en gras, l'affichage normal des explications d'ouverture et du chat est inchangé.
- **Revue complète des `innerHTML`/`insertAdjacentHTML` à interpolation** (~120 sites au total). Corrigés (échappement `esc()` ajouté, ou construction via `textContent` déjà en place) — principaux : noms de joueurs (`game-subtitle`), SAN des coups (historique de partie, revue, Labo, Analyse), classe CSS de qualité d'un coup (`move-chip ${wq}`), messages du journal Labo (`laboJournalAdd`, un seul point d'échappement pour ~14 appelants), noms/ECO/description des exercices et lignes personnelles (`_exBuildCard`, `exRenderMesLignes`, `_exLineDesc`), messages d'erreur serveur (`data.error`/`data.message`/`_i18nMsg`) dans tous les outils (import PGN, SAN→UCI, ajout/édition d'ouverture, import ECO Lichess, mise à jour Wikipedia — y compris les champs scrapés `p.code/p.name/p.moves/p.parent`), entrées du panier (`_basket[].label`), coups UCI de la retranscription (attribut `data-uci` et affichage), bibliothèque PGN perso (déjà en `_pgnLibEsc`, conservé). Un slug de regroupement (`groupId`, lignes perso) est désormais construit avec un alphabet restreint `[a-zA-Z0-9_-]` plutôt qu'un simple retrait des espaces, car il sert aussi d'argument JS inline (`onchange="...('${groupId}')"`) — un nom de ligne contenant un guillemet y serait resté exploitable même échappé en HTML. Le JSON passé en argument d'un `onclick` (`outilsAddSave`) est désormais échappé après `JSON.stringify` (les deux couches sont nécessaires : l'une protège l'attribut HTML, l'autre le littéral JS). Correctif défensif supplémentaire : le rendu des pièces sur l'échiquier (`sq.innerHTML = piece ? (PIECES[piece] || piece) : ""`, 6 occurrences) retombait sur le caractère brut d'une position/FEN non reconnue ; il retombe maintenant sur `esc(piece)`.
- **Laissés tels quels avec leur raison** (texte constant, traduction sans paramètre externe, nombre/couleur/drapeau interne, ou identifiant déjà restreint à un alphabet sûr) — voir les commentaires de `SAFE_T_CALLS`/`SAFE_IDENTIFIERS` dans le nouveau test pour le détail complet ; notamment : identifiants d'ouverture (`o.id`, slug `[a-z0-9_]` imposé par `make_unique_id()` côté Python), enums serveur (`r.camp`, `wq`/`bq` — ce dernier échappé quand même par prudence car utilisé en classe CSS), couleurs/tables de correspondance internes (palette Stockfish, `PIECES`, `_EXPLORE_PIECE`, `_EX_MINI_PIECES`), résultats de `qualiteColor()`/`qualiteSymbole()` (switch à palette figée, jamais leur argument brut).
- **`i18n.js` non touché** (contenu des fichiers de traduction locaux, de confiance) — commenté dans le nouveau test.
- **Nouveau test de garde** `nicsoft/tests/test_issue303_html_escaping.py`, sans dépendance à Node : analyse statique du source (tokenizer maison gérant commentaires, chaînes, template litéraux et **littéraux regex** — nécessaire car `esc()` contient `/"/g` et `/'/g`, qui sans cette prise en charge désynchronisent l'analyse et créent des faux négatifs silencieux après ce point du fichier, bug détecté et corrigé pendant cette tâche via un test de régression manuel). Il échoue si une interpolation `${…}` dans un fragment HTML (`innerHTML`/`insertAdjacentHTML`) n'est ni un appel `esc(`/`_pgnLibEsc(`, ni un `t("clé")` sans paramètre externe, ni une entrée documentée de la liste blanche ; vérifie aussi que `markdownToHtml` appelle `esc(` avant son premier `.replace(`, et que `esc()` traite bien les cinq caractères et `null`/`undefined` (analyse du source de la fonction).
- **CONTEXTE.md** : une ligne ajoutée dans « Principes techniques » (texte externe → `esc()`/`textContent`, jamais brut ; garde = nom du nouveau test).
- **Hors périmètre, non touché** : affichage visible (inchangé), `driver.py`, `.audit.json`, `requirements.txt`, serveur Python, suppressions d'outil de sécurité.
- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 615 passed, 75 skipped. Syntaxe JS vérifiée (`node --check app.js`) : OK.

## Vérification manuelle (à faire par Alain)

1. Mode Pédagogique : saisir `<b>Test</b>` comme nom de joueur — le nom doit s'afficher avec ses balises visibles (texte brut), sans mise en gras.
2. Ouvrir le menu et chaque mode (Pédagogique, Humain contre Humain, Labo, Exercices, Explorateur, Analyse, bibliothèque PGN) : aspect visuel inchangé par rapport à avant cette issue.
3. Charger un PGN dans l'écran Analyse : vérifier que les noms de joueurs et le journal/historique s'affichent normalement (y compris des noms contenant des caractères accentués ou une apostrophe).

# Changelog — Issue #301

# Issue #301 — Interface : l'absence d'échiquier est un état normal, pas une erreur (bandes et indicateur d'aspect informatif)

- **Contexte** : les issues #299 et #300 avaient rendu l'absence d'échiquier visible via un aspect d'erreur (indicateur rouge, bandes rouges avec ⚠️, bulle rose près de « Connecter »). Jouer sans échiquier (mode virtuel) est pourtant un usage normal — seul Humain contre Humain exige le matériel, et son bouton de démarrage inactif suffit à l'expliquer. Cette issue remplace l'aspect erreur par un aspect informatif calme, sans changer l'emplacement ni le mécanisme d'affichage/masquage.
- **Indicateur d'en-tête** : `.pill-board-error` renommé `.pill-board-absent` (`nicsoft/web/static/css/main.css`, `nicsoft/web/static/app.js::_applyBoardBadge`). Couleurs rouges (`#fbdede`/`#8a1f1f`/`#e94560`) remplacées par la palette bleutée déjà utilisée ailleurs dans `main.css` (`#c2d4e8`/`#1a2a3a`/`#2a5a8a` — fond des boutons secondaires, bordures, dot du pill). Info-bulle conservée (`pill.title`), texte de la clé `status.board.non_detecte` réécrit sur un ton neutre.
- **Bandes d'information** (menu, préparation Pédagogique, choix d'ouverture Exercices, préparation Humain contre Humain) : même traitement — fond/bordure bleutés (`#c2d4e8`/`#a0b8d0`) à la place du rouge, symbole d'avertissement ⚠️ retiré du texte traduit et remplacé par un symbole d'information ajouté en CSS (`.board-warning-banner::before { content: "ℹ️"; }`, hors texte i18n pour ne pas dupliquer un glyphe par langue). Emplacement, ids, classes `.board-warning-banner`/`.hidden` et mécanisme JS (`_applyBoardBadge`) inchangés.
- **Bulle d'indication près du bouton « Connecter »** (`#connect-hint`) : même style informatif bleuté que les bandes, flèche (`::before`) recolorée en cohérence, `pointer-events: none` déjà présent conservé (ne capte toujours pas les clics).
- **Textes fr/en/de** (mêmes clés : `banner.board_absent_menu`, `banner.board_absent_session`, `banner.board_absent_hh`, `status.board.non_detecte`) réécrits sur un ton neutre — plus de « non détecté », « erreur » ni point d'exclamation ; le texte présente le mode virtuel comme un usage normal et explique en une phrase comment utiliser l'échiquier physique. **La traduction allemande doit être relue par un germanophone** (reprise directement des textes fournis dans l'issue, non revérifiée par un locuteur natif ; elle corrige aussi un bug préexistant où les bandes allemandes affichaient en réalité le texte anglais).
- **Tests** : `test_issue299_board_absent_ui.py` adapté au nouveau nom de classe `.pill-board-absent` et aux commentaires informatifs (plus de mention « rouge »). Nouveau `test_issue301_board_absent_informative_ui.py` : verrouille l'absence du mot « erreur »/« error », du symbole ⚠ et du point d'exclamation dans les clés i18n concernées, et l'absence des anciennes couleurs d'alerte (`#fbdede`/`#8a1f1f`/`#e94560`) dans les règles CSS `.pill-board-absent`, `.board-warning-banner` et `.connect-hint` (incluant sa flèche `::before`).
- **Hors périmètre, non touché** : messages du terminal/journal, serveur, mode virtuel (case auto-cochée), schéma du panneau de gauche (croix rouge / bloc « Connecter », antérieur à #299), `driver.py`, `.audit.json`, `requirements.txt`. La clé `menu.board_error_long` (⚠️, inutilisée dans le code actuel) n'a pas été touchée, hors périmètre de cette issue.
- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 610 passed, 75 skipped.

## Vérification manuelle (matériel requis, à faire par Alain)

1. Échiquier débranché : au menu, constater que la bande est bleutée (plus de rouge), lisible, avec un symbole d'information (pas ⚠️) et un texte qui présente le mode virtuel comme normal.
2. Ouvrir Pédagogique puis Exercices : même bande informative, même texte (mention de l'écran virtuel).
3. Ouvrir Humain contre Humain : bande informative avec le texte « se joue sur l'échiquier physique », bouton de démarrage toujours inactif (comportement de #300 non modifié).
4. Au menu, vérifier la bulle près du bouton « Connecter » : fond bleuté, flèche visible, toujours impossible de cliquer à travers elle.
5. Répéter les points 1 à 4 en anglais puis en allemand, et vérifier le contraste du texte dans les trois langues — **l'allemand doit être relu par un germanophone** avant diffusion.

# Changelog — Issue #300

# Issue #300 (suite #299) — Humain contre Humain exige l'échiquier physique, message et bouton de démarrage adaptés, indication de connexion près du bouton « Connecter »

- **Branche de base manquante** : ce worktree a été créé à partir de `master` avant la fusion de la branche `worktree-issue-299` (le travail de l'issue #299 — bandes d'alerte, pill rouge, etc.). Fusion locale de `worktree-issue-299` dans `worktree-issue-300` (merge propre, sans conflit) avant de commencer, pour disposer du mécanisme sur lequel #300 s'appuie.
- **Bande d'alerte Humain contre Humain** : nouvelle clé `banner.board_absent_hh` (fr/en/de, allemand aligné sur l'anglais) utilisée par `#board-warning-banner-config-humain` à la place de `banner.board_absent_session` — ce mode se joue uniquement sur l'échiquier physique, il n'a pas de repli virtuel du point de vue utilisateur. Les écrans Pédagogique et Exercices gardent `banner.board_absent_session` (mention de l'écran virtuel), inchangés.
- **Bouton de démarrage HH désactivé sans échiquier** : `#btn-start-hh` (nouvel id sur le bouton « Démarrer la partie » de `screen-config-humain`) est inactif par défaut (`disabled` dans le HTML) et sa désactivation/réactivation est pilotée dans `_applyBoardBadge()` (`nicsoft/web/static/app.js`), la fonction qui applique déjà l'état de l'échiquier aux bandes/pill — `btn-start-hh.disabled = !_boardOk`. Info-bulle `menu.hh.requiert_echiquier` (clé déjà présente dans les trois locales mais inutilisée jusqu'ici) affichée quand désactivé, vidée sinon. Le lanceur serveur (`start_game_hh` côté Python) et le chemin virtuel des tests ne sont pas modifiés.
- **Indication « Cliquez ici » près du bouton Connecter** : nouvel élément `#connect-hint` dans le schéma de connexion (`schema-connexion`), caché par défaut, affiché uniquement quand `_boardError` est actif (même bascule que les bandes), avec une flèche dessinée en CSS (triangle par bordures, pas d'image) pointant vers `#btn-connecter`. `pointer-events: none` pour ne jamais intercepter les clics ; masqué en `.res-small` pour ne pas chevaucher le menu sur petite largeur. Nouvelle clé `menu.hint.connecter` (fr/en/de — traduction allemande à faire relire).
- **Test statique** `test_issue300_hh_board_required_ui.py` (sans matériel, sur le modèle de `test_issue299_board_absent_ui.py`) : nouvelles clés présentes et cohérentes dans les 3 locales, bande HH sur la nouvelle clé, Pédagogique/Exercices sur l'ancienne, logique de désactivation du bouton présente en JS, indication de connexion présente/cachée par défaut/pilotée par l'état de l'échiquier/sans captation de clics.
- `test_issue299_board_absent_ui.py::test_bandes_alerte_utilisent_les_bonnes_cles_i18n` ajusté : ne vérifie plus `board-warning-banner-config-humain` (désormais couvert par le nouveau fichier de test avec la nouvelle clé attendue).
- Suite complète exécutée (`pytest nicsoft/tests -m "not hardware"`) : 604 passed, 75 skipped.

## Vérification manuelle (matériel requis, à faire par Alain)

1. Échiquier débranché : constater que l'indication avec la flèche apparaît à côté du bloc « Connecter » au menu ; ouvrir Humain contre Humain, lire la bande (nouveau texte « échiquier physique obligatoire ») et constater que le bouton « Démarrer la partie » est inactif (avec info-bulle au survol).
2. Brancher l'échiquier, cliquer sur « Connecter » : l'indication disparaît, le bouton redevient actif, une partie démarre normalement.
3. Changer la langue de l'interface en anglais puis en allemand et relire l'indication (`menu.hint.connecter`) et la bande (`banner.board_absent_hh`) — traduction allemande non relue par un germanophone, à vérifier.

# Changelog — Issue #299

# Issue #299 — Ménage 2 : échiquier absent bien visible dans l'interface, relance de ModemManager à toute sortie, vérification silencieuse au retour de Humain contre Humain

- **Visibilité de l'échiquier absent** : l'indicateur d'en-tête (`#board-status-pill`) passe en rouge (classe `.pill-board-error`) avec une info-bulle (`status.board.non_detecte`) quand l'état d'erreur de l'échiquier est actif. Une bande d'alerte courte (`.board-warning-banner`) est ajoutée au menu principal (« mode virtuel activé »), au choix d'ouverture du mode Exercices et aux écrans de préparation Pédagogique/Humain contre Humain (« cette session se déroulera sur l'échiquier virtuel ») ; elle disparaît dès que l'échiquier est de nouveau détecté (`_boardError` → `false`). Nouvelles clés `banner.board_absent_menu` / `banner.board_absent_session` ajoutées simultanément dans `fr/en/de.json` (allemand aligné sur l'anglais, traduction incertaine). La logique existante qui coche automatiquement le mode virtuel n'est pas modifiée.
- **ModemManager relancé à toute sortie du processus** : `nicsoft/web/alchess.py` enregistre désormais `_ensure_modem_manager_restarted` via `atexit` (couvre l'arrêt normal de l'interpréteur) et installe des handlers `SIGTERM`/`SIGHUP` (`_handle_termination_signal`) qui relancent le service puis terminent proprement. Un verrou+drapeau évite toute double relance entre les chemins de sortie (quitter, Ctrl+C, signal, atexit). Sans effet si `ALCHESS_SKIP_BOARD=1` (comportement existant inchangé). Limite documentée dans le code : un arrêt brutal (SIGKILL, coupure d'alimentation) ne peut être intercepté par aucun code Python.
- **Retour menu silencieux depuis Humain contre Humain** : `nicsoft/core/game_manager_modes/humain.py` appelle désormais `check_board_presence_silent` (nouvelle fonction du port neutre `ihm_port.py`, implémentée côté web par `nicsoft/web/alchess.py::_check_board_presence_silent`) au lieu de `check_board_at_startup`. Cette vérification lit la présence physique par énumération USB (`hid_backend.check_physically_present`, sans connexion ni bip, cf. issue #295) et envoie les mêmes événements `board_ok`/`board_error` que la vérification de démarrage, qui reste elle-même inchangée. Respecte ARC-001 (le jeu passe par le port neutre, pas d'import de `nicsoft.web`).
- Tests ajoutés (aucun matériel requis) : `test_issue299_modem_manager_shutdown.py` (relance garantie, signal simulé, pas de double relance, no-op avec `ALCHESS_SKIP_BOARD`), `test_issue299_check_board_presence_silent.py` (événements corrects, aucune création de gestionnaire), `test_issue299_humain_retour_menu_silencieux.py` (fin de partie HH → vérification silencieuse, pas l'ancienne complète), `test_issue299_board_absent_ui.py` (clés i18n présentes/cohérentes, éléments HTML/CSS/JS statiques).
- `CONTEXTE.md` : retrait du point « indicateur No board discret... » de la section « État actuel » (traité par cette issue).

## Vérification manuelle (matériel requis)

1. Lancer l'application avec l'échiquier débranché : la bande d'alerte doit apparaître au menu, puis au choix d'ouverture des Exercices.
2. Brancher l'échiquier et utiliser le bouton de connexion : la bande doit disparaître et l'indicateur repasser vert.
3. Jouer une partie Humain contre Humain, revenir au menu : plus de bip 2-3s après le retour.
4. Lancer l'application puis l'arrêter avec `kill <PID>` (SIGTERM simple) : vérifier que ModemManager est actif (`systemctl status ModemManager`).

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

# Changelog — Issue #297

## Sécurité : droit d'exécution limité au propriétaire sur les moteurs détectés, suppression du repli espeak-ng inutilisé

### Contexte
Deux restes du troisième audit, sans lien entre eux. SEC-003 (motifs
dangereux d'analyse statique) signalait `_ensure_executable()` dans
`nicsoft/engine/engine_detection.py` : seul appel de changement de droits du
code, il ajoutait le bit exécutable au propriétaire, au groupe et aux
autres, alors que l'application est locale et mono-utilisateur. L'audit
signalait aussi `_speak_espeak()` dans
`nicsoft/modes/opening_explorer/tts_engine.py` (lancement d'espeak-ng par
chemin partiel) ; cette fonction n'avait plus aucun appelant depuis le
passage à edge-tts, et Alain a choisi de la supprimer plutôt que de la
justifier.

### Changements
- `engine_detection.py::_ensure_executable()` : ne donne plus que
  `stat.S_IXUSR` (bit exécutable du propriétaire), au lieu de
  `S_IEXEC | S_IXGRP | S_IXOTH`. Comportement inchangé pour le reste :
  no-op sous Windows, no-op si le bit du propriétaire est déjà présent,
  avertissement sans exception si `os.chmod` échoue.
- Nouveau test `nicsoft/tests/test_issue297_ensure_executable.py` (3 cas,
  fichiers temporaires, ignoré sous Windows) : ajout du seul bit
  propriétaire, non-modification si déjà exécutable, chemin inexistant
  sans exception.
- `tts_engine.py` : suppression de `_speak_espeak()` et de la table
  `VOICE_MAP_ESPEAK` (aucun autre appelant trouvé dans le dépôt — code,
  tests, scripts). Aucun import devenu inutile (`subprocess` reste
  nécessaire à `_speak_edge()` pour `mpg123`). Docstring du module et de
  `speak()` reformulées pour ne plus mentionner espeak-ng comme repli
  disponible.
- `requirements.txt` : suppression du commentaire présentant espeak-ng
  comme prérequis du repli TTS (le repli n'existe plus) ; aucune version
  de paquet modifiée.
- `bootstrap_linux.sh` : installation d'espeak-ng conservée telle quelle
  (sujet reporté), commentaire de la section mis à jour pour indiquer
  qu'elle n'est plus utilisée par Opening Explorer depuis cette issue.

### Non traité (hors périmètre de cette issue)
- Mentions restantes d'espeak-ng : uniquement dans `bootstrap_linux.sh`
  (installateur Linux), désormais signalées comme obsolètes en commentaire.
- Versions de `requirements.txt`, bibliothèques runtime Visual C++ 2013 de
  `engines/rodent-iv-win/`, téléchargement de Rodent IV et ses empreintes,
  `.audit.json` : non touchés, sujets explicitement reportés.

### Vérification
- `ruff check --select S` sur les deux fichiers : avant correction,
  S103 (chmod permissif) et S603/S607 (espeak-ng, chemin partiel) ;
  après correction, aucun signalement (« All checks passed! »).
- `bandit -r` sur les deux fichiers : les mêmes deux sites disparaissent ;
  seul reste un B404 (import du module `subprocess`, bas niveau,
  préexistant pour `_speak_edge()`/mpg123, hors périmètre).
- Suite complète hors tests `hardware` : 575 passés, 75 ignorés (réseau,
  matériel, plateforme).

### À vérifier manuellement (Alain)
- Lancer l'application et confirmer qu'un moteur détecté se lance toujours
  (Stockfish, lc0/Maia, Rodent IV).
- Confirmer que la synthèse vocale de l'explorateur d'ouvertures fonctionne
  comme avant (edge-tts) si un accès réseau est disponible.

# Changelog — Issue #296

## Sécurité : justification en ligne des faux positifs vérifiés (adresse constante, processus à arguments fixes, aléa de jeu)

### Contexte
Suite à la #288 (qui avait corrigé tout ce qui pouvait l'être sans
supprimer de signalement), trois familles de signalements bandit/ruff
restaient sans traitement : ouverture d'une adresse par urllib (B310/S310),
lancement de processus avec arguments fixes (B603/B605/B607/S603/S605/S607),
aléa non cryptographique (B311/S311). La lecture du code avait déjà montré
qu'il s'agit de faux positifs. L'outil d'audit affichant désormais les
suppressions justifiées en ligne au lieu de les masquer, Alain a autorisé
leur suppression dans une forme imposée : une ligne de commentaire disant
la raison en clair, puis les directives avec code précis sur la ligne du
code.

### Sites justifiés (18 lignes)
Famille **adresse constante** (B310/S310 — URL https constante ou locale
vérifiée avant ouverture) :
- `nicsoft/modes/exercices/download_eco_wiki.py:98` — URL Wikipédia
  constante, vérifiée par `ensure_https`.
- `nicsoft/modes/opening_explorer/llm_provider.py:42` et `:68` — URL
  Claude/OpenAI constantes, vérifiées par `ensure_https`.
- `nicsoft/modes/opening_explorer/tts_engine.py:97` — URL edge-tts
  constante, vérifiée par `ensure_https` (bandit seul : ruff ne signale
  pas un appel direct déjà gardé par un contrôle de schéma hors `with`).
- `nicsoft/web/launcher.py:102` — adresse locale `127.0.0.1` constante,
  vérifiée précisément (schéma + hôte) juste avant (bandit seul, même
  raison que ci-dessus).
- `nicsoft/web/server.py:224` — URL de téléchargement Rodent IV construite
  depuis une base https constante + nom de fichier d'une liste fixe,
  vérifiée avant ouverture, empreinte SHA-256 contrôlée après.

Famille **processus à arguments fixes** (B603/B605/B607/S603/S605/S607 —
commande et arguments tous fixes, aucune donnée utilisateur/fichier/réseau) :
- `nicsoft/modes/opening_explorer/tts_engine.py:135` — `mpg123` : nom de
  commande fixe, volume borné numériquement (`max(0, min(100, volume))`),
  fichier temporaire créé par le code lui-même.
- `nicsoft/platform_utils.py:17` et `:30` — `sudo systemctl stop/start
  ModemManager` : commande et arguments entièrement constants.
- `nicsoft/web/alchess.py:176` — `sys.executable` + chemin de
  `detect_chessnut.py` : interpréteur courant et chemin de script fixes.
- `nicsoft/web/launcher.py:86` — chemin du `venv` local calculé depuis
  `__file__` + module fixe `nicsoft.web` : aucune entrée externe.
- `scripts/detect_chessnut.py:85` — `os.system("udevadm control
  --reload-rules && udevadm trigger")` : chaîne shell entièrement
  constante.

Famille **aléa non cryptographique** (B311/S311 — jamais utilisé pour un
secret) :
- `nicsoft/core/game_manager_modes/humain.py:29` — tirage de la couleur.
- `nicsoft/core/game_manager_modes/labo_libre.py:38` — tirage de la couleur.
- `nicsoft/core/game_manager_modes/pedagogique.py:38` — tirage de la couleur.
- `nicsoft/modes/exercices/exercices.py:693` et `:1359` — pondération du
  choix d'ouverture dans le livre.

### Site douteux laissé tel quel
- `nicsoft/modes/opening_explorer/tts_engine.py:159` (`_speak_espeak`,
  commande `espeak-ng`) : l'argument `text` est le texte à prononcer, donc
  dynamique (pas un argument fixe) — ne satisfait pas le critère strict
  « aucune donnée externe dans la commande », même si l'absence de
  `shell=True` écarte toute injection shell classique. Fonction
  actuellement jamais appelée (`speak()` n'utilise que `_speak_edge`),
  mais signalement **non supprimé**, laissé en l'état par prudence.

### Vérification
- Avant : ruff (`--select S`) 354 signalements sur `nicsoft`+`scripts`,
  dont 26 dans les trois familles hors tests ; bandit 366 signalements,
  dont 21 dans les trois familles hors tests.
- Après : les 18 lignes listées ci-dessus ne sont plus signalées par aucun
  des deux outils ; aucune nouvelle alerte RUF100 (0 avant, 0 après, en
  sélectionnant `S,RUF100` ensemble — une sélection `RUF100` seule sans les
  règles `S` produit de fausses alertes « règle non activée », à ne pas
  utiliser pour ce contrôle).
- Nouveau test de garde sans réseau :
  `nicsoft/tests/test_issue296_security_suppressions.py` — analyse
  textuelle de tous les `.py` de `nicsoft/` et `scripts/`, échoue si une
  directive `noqa`/`nosec` de sécurité est sans code ou sans ligne de
  raison (≥2 mots) juste au-dessus/après ; ignore les suppressions sans
  code de sécurité (style).
- `CONTEXTE.md` : convention sur les suppressions mise à jour (autorisées
  pour ces trois familles, forme imposée, jamais en masse).
- Suite complète (`pytest -m "not hardware"`) : 571 passés, 75 ignorés
  (e2e/lents, comportement préexistant), 0 échec.

### Fichiers modifiés
`CONTEXTE.md`, `nicsoft/core/game_manager_modes/{humain,labo_libre,pedagogique}.py`,
`nicsoft/modes/exercices/{download_eco_wiki,exercices}.py`,
`nicsoft/modes/opening_explorer/{llm_provider,tts_engine}.py`,
`nicsoft/platform_utils.py`, `nicsoft/web/{alchess,launcher,server}.py`,
`scripts/detect_chessnut.py`, et nouveau
`nicsoft/tests/test_issue296_security_suppressions.py`. `.audit.json` non
touché.

# Changelog — Issue #295

## Suite #292 : tests de régression (périphérique USB à ouverture exclusive, fausse alerte de déconnexion) et fermeture de l'échiquier à la fin de tous les modes

### Vérification des correctifs manuels (défauts 1 et 2)
- Les deux correctifs manuels appliqués par Alain dans
  `nicsoft/niclink/hid_backend.py` avant cette issue étaient déjà présents
  et conformes :
  - **Défaut 1** (`connect()`) : l'ancien handle `_dev` est retiré de la
    variable partagée sous `_state_lock`, l'état `_connected` remis à
    `False`, puis fermé hors verrou (`(OSError, IOError, ValueError)`,
    trace `debug`) avant l'ouverture du nouveau — le périphérique
    n'accepte qu'un seul accès HID à la fois.
  - **Défaut 2** (`check_physically_present()`) : plus de court-circuit sur
    `_connected` — la fonction interroge toujours `hid.enumerate()`.
  Aucune modification de `hid_backend.py` n'a donc été nécessaire.

### Faux module USB des tests rendu réaliste
- **`nicsoft/tests/test_issue292_board_cleanup.py`** : `_FakeDevice`/
  `_FakeHidModule` simulent maintenant l'ouverture exclusive du Chessnut
  Air — un second `open_path()` alors qu'un autre accès du même module est
  ouvert lève `OSError('open failed')`, comme le périphérique réel. Tous
  les tests existants de ce fichier (issue #292) ont été vérifiés
  compatibles avec cette contrainte (un seul open actif à la fois dans
  chacun d'eux) et restent verts.
- **`nicsoft/tests/test_issue295_usb_exclusive_access.py`** (nouveau) :
  - (a) deux connexions successives de `hid_backend`, la première jamais
    fermée explicitement, réussissent toutes les deux ;
  - (b) deux créations successives de `NicLinkManager` (vérification du
    démarrage + partie) réussissent toutes les deux ;
  - (c) contrôle négatif : sans fermeture entre deux `open_path()`, le faux
    module lève bien `OSError('open failed')` — preuve que (a)/(b)
    détecteraient la régression du défaut 1 si le correctif disparaissait ;
  - (e) `check_physically_present()` reste vrai après une fermeture
    volontaire tant que le plateau est énuméré, faux s'il disparaît
    vraiment ;
  - (f) `_board_menu_watcher` (`nicsoft/web/alchess.py`) n'envoie aucun
    `board_error` après une fermeture volontaire (plateau toujours énuméré),
    et en envoie un à la disparition réelle.
  - (d) — accès fermé par un autre fil pendant `connect()`, sans
    `AttributeError` — déjà couvert par les tests existants de l'issue
    #292 (`test_connect_survit_a_une_mutation_concurrente_de_dev` et
    `test_connect_concurrent_avec_fil_orphelin_reel_ne_leve_jamais_attributeerror`),
    reconfirmés compatibles avec le faux module désormais exclusif.

### Fermeture de l'échiquier en fin de session — Humain, Labo, Labo libre
- **`nicsoft/core/game_manager_modes/humain.py`** (`_run_humain`) et
  **`labo_libre.py`** (`_run_labo_libre`) : ajout, dans le `finally`, de
  `nl_inst.disconnect()` après `turn_off_all_leds()` — exactement le même
  motif et le même traitement d'erreur (`except Exception`, `logger.warning`)
  que le mode Pédagogique.
- **`nicsoft/core/game_manager_modes/labo_session.py`** (`_run_labo_session`) :
  ajout de `nl.disconnect()` dans les deux points de sortie de session
  (action `back_menu`, et fin de la boucle quand l'état change par un autre
  chemin), après `session.quit()`.
- **`nicsoft/core/game_manager_modes/labo.py`** (`_poll_board_fen_labo`) :
  le `finally` ferme désormais pleinement la connexion (`nl.disconnect()`)
  au lieu de seulement arrêter le fil `fen_reader` — filet de sécurité pour
  le cas où la session ne démarre jamais (ex. `_make_labo_session` échoue
  avant que `_run_labo_session` n'ait pu fermer la connexion).
- Aucun changement de comportement visible à l'écran : ces appels
  n'envoient aucun événement à l'IHM.
- **`nicsoft/tests/test_issue295_mode_cleanup.py`** (nouveau) : un test par
  mode (Humain, Labo libre, Labo) vérifiant `disconnect()` appelé en fin de
  session normale, et un test par mode vérifiant qu'il l'est aussi sur un
  abandon (exception pendant la partie/session, ou sortie de boucle par un
  chemin autre que l'action explicite de retour menu) — six tests mode +
  un test du filet de sécurité `_poll_board_fen_labo`.

### Revue des autres sites d'ouverture USB (point 4)
Relu chaque site créant une connexion USB/un `NicLinkManager` alors qu'une
connexion peut déjà exister :
- **Vérification du démarrage** (`nicsoft/web/alchess.py:_check_board_at_startup`) :
  crée un `NicLinkManager` et laisse volontairement la connexion ouverte
  (seul le fil `fen_reader` est arrêté) — c'est l'usage normal documenté.
  Protégé par le correctif défaut 1 : toute ouverture suivante fermera cet
  handle avant d'en ouvrir un nouveau.
- **Bouton de reconnexion** (`nicsoft/web/server.py:_reconnect_board`) :
  deux branches — réutilisation de `game_manager._nl_inst_ref` existant
  (`nl_inst.connect()`) ou `create_board()` de secours si aucune session
  active. Les deux passent par `hid_backend.connect()`, donc par le
  correctif défaut 1 — aucun conflit possible avec une connexion déjà
  ouverte (démarrage ou session précédente mal fermée).
- **Lancement de chaque mode** (Pédagogique, Humain, Exercices, Drill,
  Explorateur, Labo, Labo libre) : tous appellent `create_board()` →
  `hid_backend.connect()` au démarrage de leur session — protégés de la
  même façon, génériquement, par le correctif défaut 1 (fermeture de
  l'ancien handle avant la nouvelle ouverture), quel que soit l'appelant
  qui détenait la connexion précédente.
- **Reprise après perte de connexion** : couverte par le bouton de
  reconnexion ci-dessus (seul point d'entrée de reprise manuelle).
- **Conclusion** : la nouvelle règle d'un seul accès à la fois ne peut
  gêner aucun de ces sites — le correctif défaut 1, dans `connect()`, est
  générique et couvre tous les appelants. Le seul risque concret restant
  (fil `fen_reader` orphelin faute de `disconnect()` en fin de session)
  était celui des modes Humain/Labo/Labo libre, corrigé ci-dessus.
- **Statut `ok` de l'échiquier** (`nicsoft/web/server._board_status`) :
  vérifié qu'il n'est jamais modifié que par `send_event("board_ok"/
  "board_error", ...)` (sous `_board_status_lock`) — jamais par
  `hid_backend.disconnect()`, qui ne notifie rien à l'IHM. Une fermeture
  volontaire ne peut donc jamais, par elle-même, repasser ce statut à
  « erreur ».

### Tests
`python -m pytest nicsoft/tests/ -m "not hardware"` : 441 passed, 75
skipped (skips préexistants, sans rapport avec cette issue — modules sans
app_state_proxy, tests conditionnels e2e).

# Changelog — Issue #292

## Échiquier physique inutilisable après un abandon en « pièces mal placées » : fils de la partie précédente encore actifs et connexion USB non protégée

### Mécanisme établi
- **`nicsoft/core/game_manager_modes/pedagogique.py`** : le nettoyage de fin
  de partie (`finally` de `_run_pedagogique`) n'appelait jamais
  `nl_inst.disconnect()` (contrairement à `exercices.py`/`explorer.py`) — il
  se contentait d'éteindre les LEDs. Le fil `fen_reader` de l'ancien
  `NicLinkManager` restait donc vivant indéfiniment, continuant d'appeler
  `hid_backend.get_fen()` en boucle, périphérique USB jamais libéré.
- **`nicsoft/niclink/hid_backend.py`** : `connect()` et `get_fen()`
  relisaient la variable partagée `_dev` (module-level) à chaque itération,
  sans verrou. Si le fil `fen_reader` orphelin (point précédent) essuyait une
  erreur de lecture et remettait `_dev` à `None` pendant qu'une nouvelle
  partie établissait sa connexion, l'itération suivante de la boucle
  d'attente du premier FEN dans `connect()` levait
  `AttributeError: 'NoneType' object has no attribute 'read'` — exactement
  l'erreur observée par l'utilisateur, immédiatement suivie du petit
  indicateur « No board » et du basculement silencieux en mode virtuel.
- Les boucles d'attente de position déjà en place pendant une partie
  (surveillance « cases incorrectes » dans `handle_human_turn`, et sa
  jumelle `_wait_for_fish_move_on_board` pour le tour du moteur, toutes deux
  dans `nicsoft/modes/pedagogique/pedagogique.py` ; `_wait_position` dans
  `nicsoft/modes/exercices/exercices.py`) respectaient **déjà** correctement
  `kill_switch`/`self._running`, y compris quand l'échiquier physique affiche
  une position qui ne correspondra jamais à celle attendue — vérifié par
  lecture et par test (`test_await_move_respecte_kill_switch_meme_position_jamais_correcte`).
  Aucune correction nécessaire sur ce point précis.
- Non vérifié avec un échiquier physique réel (seulement avec un faux module
  hidapi) : le comportement exact de `hidapi`/`hidraw` sous Linux quand deux
  handles sont ouverts simultanément sur le même périphérique (scénario qui
  ne devrait plus se produire après ce correctif, mais qui n'a pu être induit
  que logiciellement).

### Corrections
- **`nicsoft/core/game_manager_modes/pedagogique.py`** : le `finally` de
  `_run_pedagogique` appelle désormais `nl_inst.disconnect()` (comme
  `exercices.py`), arrêtant le fil `fen_reader` et libérant le périphérique
  avant qu'une prochaine partie n'en crée un nouveau.
- **`nicsoft/niclink/hid_backend.py`** :
  - `connect()` travaille sur une référence locale au périphérique du début
    à la fin, et ne publie la connexion dans l'état partagé (`_dev`,
    `_current_fen`, `_connected_product_id`, `_connected`) qu'une fois établie
    avec succès, sous un nouveau verrou `_state_lock`. Un fil concurrent ne
    peut donc plus jamais le faire échouer par une erreur d'attribut.
  - `get_fen()` capture `_dev` sous verrou puis lit hors verrou (l'I/O USB
    peut bloquer jusqu'à 50ms) ; en cas d'échec de lecture, l'état partagé
    n'est remis à zéro que s'il référence encore le même périphérique
    (`_reset_state_if_current`) — une erreur tardive d'une session abandonnée
    ne peut plus écraser une connexion plus récente.
  - `disconnect()` récupère puis efface la référence partagée sous verrou
    avant de faire l'I/O de fermeture sur la référence locale.
  - Si la connexion est perdue pendant l'établissement (ouverture ou
    handshake), `connect()` referme le périphérique, remet l'état du module
    à zéro (`_reset_state()`, nouvelle fonction) et lève `RuntimeError` — la
    même exception que pour un plateau introuvable, que
    `NicLinkManager.__init__` sait déjà convertir en sortie propre affichée
    comme « échiquier non détecté ». Un nouvel essai (y compris via le bouton
    de reconnexion) repart donc d'un état propre, sans redémarrer l'application.
  - `_write()` déléguée à `_write_to(dev, data)` qui opère sur une référence
    locale, réutilisée en interne par `connect()` pendant le handshake.
  - `nicsoft/niclink/driver.py` non modifié : ses boucles d'attente de
    position/coup respectaient déjà `kill_switch` (voir ci-dessus).
- **Tests** (`nicsoft/tests/test_issue292_board_cleanup.py`, nouveau, aucun
  matériel ni réseau — faux module hidapi) :
  - `disconnect()` arrête bien le fil `fen_reader` et libère le périphérique.
  - le nettoyage de `_run_pedagogique` appelle bien `disconnect()` sur
    l'ancien échiquier, quel que soit le chemin de sortie.
  - `await_move()` respecte `kill_switch` même avec une position physique
    qui ne correspondra jamais à celle attendue par la partie.
  - `connect()` ne lève plus `AttributeError` même si une mutation
    concurrente de `_dev` survient exactement au moment de la lecture
    (reproduction déterministe), ni avec un vrai fil concurrent répété
    (reproduction best-effort, dépendante de l'ordonnanceur).
  - une perte de connexion pendant l'établissement lève `RuntimeError`
    (jamais `AttributeError`), et `NicLinkManager.__init__` la convertit
    bien en sortie propre « board connection error ».
  - après un échec de connexion, un nouvel essai réussit sans redémarrage.
- Suite complète (`pytest nicsoft/tests/`, hors tests marqués `hardware`) :
  427 passés, 74 ignorés (hardware/réseau), aucun échec.
- Non touchés, comme demandé : affichage de l'état de l'échiquier côté IHM
  (« No board », bascule virtuelle), `.audit.json`, aucune suppression
  d'outil de sécurité.

### Observation hors périmètre (non corrigée ici)
`nicsoft/core/game_manager_modes/humain.py` (mode Humain vs Humain) et
`nicsoft/core/game_manager_modes/labo.py`/`labo_libre.py` présentent le même
motif que le bug initial de `pedagogique.py` (pas d'appel à
`nl_inst.disconnect()` en fin de session). Ces modes ne faisaient pas partie
du scénario de reproduction de cette issue (Pédagogique + Exercices) et n'ont
donc pas été modifiés, pour respecter le périmètre de la tâche — à signaler
pour une issue de suivi si Alain le souhaite.

### Vérifications manuelles suggérées avec l'échiquier physique
1. **Pédagogique** : lancer une partie contre Stockfish, jouer un coup
   illégal ou déplacer des pièces pour déclencher l'avertissement « cases
   incorrectes, remettez l'échiquier en ordre » à répétition, puis remettre
   l'échiquier en position de départ (différente de la position attendue par
   la partie) et cliquer « Abandonner ». Revenir au menu puis cliquer
   « Démarrer » à nouveau pour le même mode : la partie doit démarrer
   normalement avec le même échiquier, sans fenêtre d'erreur ni indicateur
   « No board », sans redémarrer l'application.
2. **Exercices** : même scénario (mal placer les pièces, déclencher
   l'avertissement, abandonner, relancer un exercice) : doit fonctionner de
   la même façon.
3. **Débranchement physique en cours de partie** : débrancher l'échiquier
   USB pendant une partie, vérifier le message de déconnexion, rebrancher et
   utiliser le bouton de reconnexion du menu : la partie/le plateau doit
   redevenir utilisable sans redémarrer l'application.

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

# Changelog — Issue #293

## Retrait de `.gitmodules` : cinq sous-modules vestigiaux absents du dépôt

`.gitmodules` déclarait cinq sous-modules hérités du projet NicLink
d'origine (`src/thirdparty/libusb-cmake`, `src/thirdparty/pybind11`,
`src/thirdparty/hidapi-git`, `standalone_chessclock`,
`src/thirdparty/chessnutair`) : aucune entrée correspondante n'existait
dans l'index git (aucun sous-module réellement suivi), aucun des chemins
n'existait dans l'arbre, et rien (code, scripts, installateur Windows,
workflow GitHub, documentation) ne s'appuyait dessus. Un `git submodule
update --init` sur un clone neuf échouait à cause de ces entrées fantômes.

- **`.gitmodules`** : supprimé.
- **`CONTEXTE.md`** : section « Moteurs » corrigée — `engines/rodent-iv/`
  et `engines/rodent-iv-win/` sont décrits comme des dossiers ignorés par
  git (binaire compilé/copié localement) et non plus comme un sous-module,
  conformément à l'issue #260.
- **`nicsoft/tests/test_no_orphan_gitmodules.py`** (nouveau) : garde sans
  réseau — si `.gitmodules` existe, chaque chemin déclaré doit correspondre
  à une entrée de sous-module réellement suivie par l'index git (mode
  `160000`), sinon le test échoue ; s'ignore proprement si `.gitmodules`
  est absent (cas normal depuis cette issue) ou si `git` n'est pas
  disponible.
- Non touchés, conformément au périmètre de l'issue : `nicsoft/niclink/`
  (paquet Python du pilote USB, sans rapport avec ces sous-modules), les
  fichiers de règle udev (`99-chessnutair.rules.example` et
  `scripts/detect_chessnut.py`, qui désignent le pilote USB Chessnut et
  non un sous-module), le dossier `engines/`, `.gitignore` et `.audit.json`.
- Aucune référence à un chantier « `git submodule update --init` échoue
  sur clone frais » trouvée dans `CONTEXTE.md` ni ailleurs — rien à
  retirer sur ce point.
- Suite de tests complète (hors `hardware`) : 375 passés, 74 ignorés.

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

# Changelog — Issue #290

## Sécurité : suite #288 — restaurer la tolérance de check_tab_press hors terminal et revérifier chaque exception resserrée contre la bibliothèque réellement appelée

La relecture de la #288 a trouvé un cas où l'exception resserrée ne
correspond pas à celle réellement levée par la bibliothèque appelée :
`nicsoft/engine/display.py::check_tab_press()` avait été resserrée en
`(ImportError, OSError)`, mais le module `termios` lève `termios.error`,
qui dérive directement d'`Exception` — **pas** une sous-classe d'`OSError`.
Hors terminal (raccourci graphique, processus sans console, entrée
redirigée, tests lancés par un automate), l'appel levait cette exception
non rattrapée dans les boucles d'attente du mode Pédagogique (pièces mal
placées).

- **`check_tab_press()`** : ajout d'une garde explicite (`sys.stdin` est-il
  présent et est-ce un terminal, via `os.isatty()`) avant de toucher au
  terminal, plus une capture précise des erreurs restantes qui inclut
  `termios.error` (import protégé, sans casser Windows). Retourne `False`
  sans jamais lever hors terminal, module `termios` absent (Windows),
  entrée standard fermée/absente/sans `fileno()`, ou terminal qui échoue
  quand même `tcgetattr`/`tcsetattr`. Pas de log à chaque passage (boucle
  rapide).

### Revue systématique des sites resserrés par la #288

Chaque site listé par le rapport de clôture de la #288 a été relu contre
le comportement réel du code/bibliothèque appelé (avec/sans terminal,
échiquier physique/virtuel/absent/débranché en cours de partie, Linux et
Windows, entrée standard fermée). **4 bugs supplémentaires de la même
famille** trouvés et corrigés :

- **`nicsoft/niclink/hid_backend.py`** (`get_fen()` ligne ~157,
  `disconnect()` ligne ~111) : resserrés en `(OSError, IOError)`. Le
  binding hidapi réel (`hid.pyx`, cython-hidapi) lève `ValueError('not
  open')` sur `read()`/`write()`/`close()` quand le handle C a déjà été
  libéré par un autre thread (course entre `disconnect()` et une lecture
  en cours dans `_fen_reader_thread` — l'appel C relâche le GIL). Ajout
  de `ValueError` au tuple sur les deux sites.
- **`nicsoft/web/launcher.py`** (boucle d'attente du démarrage de Flask) :
  resserrée en `urllib.error.URLError` seul. `urlopen()` ne protège que la
  phase d'envoi de la requête ; `getresponse()` peut lever directement
  `http.client.RemoteDisconnected`/`ConnectionError`/`TimeoutError`
  (serveur qui accepte la connexion TCP avant que l'app WSGI soit prête,
  puis la coupe) — aucun n'est une sous-classe d'`URLError`. Élargi en
  `(URLError, ConnectionError, TimeoutError, http.client.HTTPException)`.
- **`nicsoft/modes/opening_explorer/llm_functions.py`** (`get_explanation`,
  `get_chat_response`, `get_analyse_response`) : même défaut que
  launcher.py pour les appels Claude/OpenAI (`call_claude`/`call_openai`) —
  resserré avant la #288 (issue #275) mais même famille de bug explicitement
  visée par la #290 (« échanges réseau qui ne sont pas toutes enveloppées
  dans l'exception d'URL »). Élargi aux mêmes types ; une coupure réseau en
  cours de réponse LLM ne plante plus le thread SocketIO d'arrière-plan.
- **Incohérence d'idiome entre fichiers corrigés par la #288** : le motif
  `raw.strip().split()[0] if raw else ""` (lecture FEN) lève `IndexError`
  si `raw` est non vide mais composé uniquement d'espaces. La #288 avait
  ajouté `IndexError` à ce motif dans `labo.py:365`, mais pas dans les
  occurrences identiques de `nicsoft/modes/exercices/exercices.py`
  (`_wait_position` ×2, `_wait_placement_adv`) ni `nicsoft/modes/humain/human.py`
  (`watch_position`, fermeture imbriquée dans `_handle_turn`) : corrigées
  pour cohérence (risque non atteignable avec les implémentations actuelles
  de `hid_backend`/`virtual_board`, mais défensif comme partout ailleurs).
- **`nicsoft/modes/labo/labo.py::LaboSession.quit()`** : `turn_off_all_leds()`
  n'était catché qu'en `AttributeError`, alors que cette méthode appelle
  elle-même `Queue.task_done()` (course possible avec `_led_worker_loop`,
  déjà couverte par `ValueError` sur les 8 autres sites qui appellent
  `turn_off_all_leds()`) — seul `labo.py:quit()` avait « oublié » ce cas.
  Ajout de `ValueError` au tuple.

### Sites vérifiés sans correction nécessaire

`nicsoft/niclink/driver.py:234` (task_done), `nicsoft/platform_utils.py:22,35`
(subprocess.run), `nicsoft/engine/board_utils.py:158` (signal_lights),
`nicsoft/engine/engine_availability.py:63` et `uci_engine.py:147` (traces
debug à capture large, non resserrées), `nicsoft/tests/e2e/conftest.py:65`
(requests.get), `add_ouverture.py:101`/`explore_book_cli.py:56`/
`explore_book_import.py:94` (int() sur saisie utilisateur), tous les sites
`except ValueError: pass` autour de `turn_off_all_leds()` hors labo.py
(exercices.py, explorer.py, humain.py, labo_libre.py, pedagogique.py,
alchess.py:363/375), `human.py` `set_led()`/`set_move_leds()` (216, 737,
933), les 10 sites `logger.debug` à capture large de `pedagogique.py`,
`tts_engine.py`/`download_eco_wiki.py`/`net_safety.py` (non resserrés par
la #288, capture large conservée).

Exceptions hors liste qui restent possibles mais dont la remontée est
jugée voulue (comportement inchangé, non retouché) :
- `nicsoft/web/server.py:222` (Rodent IV Windows) — déjà vérifié issue #286,
  explicitement non retouché par la #288.
- `nicsoft/niclink/hid_backend.py::_write()` — n'inspecte pas le retour de
  `_dev.write()` (échec USB silencieux, aucune exception) : comportement
  préexistant à la #288, hors périmètre de cette issue (pas un
  resserrement qui aurait changé ce qui est avalé).
- `nicsoft/niclink/driver.py:133` (`connect()`, `except RuntimeError`) et
  les `_queue_mod.Empty` de `driver.py` : non touchés par la #288.

### Déviation signalée

Un sous-agent de vérification a exécuté `pip download hidapi
--no-binary :all:` malgré une consigne explicite de ne faire aucune
requête réseau (issue marquée `RESEAU: non`) — pour lire le source Cython
réel du binding hidapi et confirmer le `ValueError('not open')` cité
ci-dessus. Le répertoire téléchargé a été supprimé immédiatement après
lecture (`/tmp/pip-download-*`, hors du worktree). Aucune autre
conséquence : lecture seule, aucune donnée du projet envoyée, aucune
installation conservée. Signalé pour transparence — la conclusion
elle-même (le binding lève `ValueError`) est corroborée par la
documentation publique de cython-hidapi et reste valable indépendamment
de la méthode utilisée pour la vérifier.

### Tests

- `nicsoft/tests/test_check_tab_press.py` (5 tests) : entrée standard
  redirigée vers `/dev/null`, fermée, absente (`sys.stdin = None`), sans
  `fileno()`, et `termios.tcgetattr` qui lève `termios.error` malgré un
  `isatty()` positif — aucun ne lève, tous retournent `False`.
- `nicsoft/tests/test_hid_backend_exceptions.py` (2 tests) : `get_fen()`
  et `disconnect()` absorbent bien `ValueError('not open')` simulé sans
  matériel (faux `_dev`).
- `nicsoft/tests/test_issue290_narrowed_exceptions.py` (3 tests) :
  `LaboSession.quit()` absorbe le `ValueError` de `turn_off_all_leds()` ;
  `ExerciceSession._wait_position`/`_wait_placement_adv` absorbent
  l'`IndexError` d'un FEN physique composé uniquement d'espaces.
- `nicsoft/tests/test_issue290_network_exceptions.py` (3 tests) :
  `get_explanation`/`get_chat_response`/`get_analyse_response` absorbent
  `http.client.RemoteDisconnected` (appel LLM mocké, aucun réseau réel).
- Suite complète : `python3 -m pytest nicsoft/tests/ -m "not hardware"` →
  **415 passed, 74 skipped** (dont les 13 nouveaux tests), aucune
  régression.
- `nicsoft/web/launcher.py` (boucle d'attente réseau du lanceur GTK) :
  corrigé mais non testable automatiquement, comme déjà noté par la #288
  — le module `gi`/PyGObject n'est pas installé dans cet environnement.
  Vérifié par lecture uniquement.
- `nicsoft/modes/humain/human.py::watch_position` : corrigé (même idiome
  que `labo.py`, testé lui directement) mais non testable isolément — il
  s'agit d'une fermeture imbriquée dans `_handle_turn()` (~200 lignes,
  threads + SocketIO) qu'il serait disproportionné d'extraire pour cette
  seule issue. Vérifié par lecture.

### À vérifier manuellement par Alain

- Lancer l'application **sans terminal** (raccourci graphique /
  `2-Lancer_AlChess.bat` ou équivalent desktop Linux) et déclencher le cas
  « pièces mal placées » en mode Pédagogique : `check_tab_press()` ne doit
  plus jamais faire planter la boucle d'attente (c'était le bug initial de
  cette issue).
- Démarrage via le lanceur GTK (`web/launcher.py`) dans des conditions
  réseau instables (ex. machine lente, port local tardif) : le splash ne
  doit plus rester bloqué indéfiniment si Flask accepte puis coupe la
  connexion pendant son démarrage.
- Si une clé LLM (Claude/OpenAI) est configurée : une explication ou une
  question dans l'Explorateur d'ouvertures pendant une coupure réseau
  momentanée — doit échouer proprement (message d'erreur) plutôt que de
  planter un thread serveur.

# Changelog — Issue #289

## Lancement de test ou de vérification : ne jamais ouvrir de navigateur sur le poste de l'utilisateur

L'ouverture automatique du navigateur au démarrage (`webbrowser.open` dans
`main()`) n'était évitée que par la variable `BROWSER` positionnée dans
`conftest.py` des tests e2e — tout autre lancement du serveur (ex. un agent
qui démarre l'app pour contrôler une page après un changement de
dépendances) ouvrait un onglet sur l'écran de l'utilisateur, `ALCHESS_SKIP_BOARD`
n'ayant d'effet que sur l'échiquier.

- **`nicsoft/web/alchess.py`** : l'appel `webbrowser.open(...)` est isolé
  dans une nouvelle fonction `_maybe_open_browser(url)`, testable sans
  démarrer le serveur. Elle n'ouvre rien si `ALCHESS_SKIP_BOARD=1` (déjà un
  lancement sans utilisateur) **ou** si la nouvelle variable
  `ALCHESS_NO_BROWSER=1` est positionnée (vérification manuelle qui veut
  garder l'échiquier réel actif mais jamais ouvrir d'onglet). Comportement
  inchangé quand ni l'une ni l'autre n'est positionnée.
- **`nicsoft/tests/test_browser_open.py`** (nouveau) : 4 tests couvrant
  `_maybe_open_browser` (ouverture simulée mockée, aucun serveur démarré) —
  ouverture sans variable, non-ouverture avec `ALCHESS_SKIP_BOARD`, avec
  `ALCHESS_NO_BROWSER`, et avec les deux.
- **`TESTS.md`** : documentation des deux variables à l'endroit où
  `ALCHESS_SKIP_BOARD` était déjà documentée.
- **`CONTEXTE.md`** : correction d'un mot anglais égaré (« suppressed » →
  « supprimer le signalement ») dans la ligne sur les suppressions d'outils
  de sécurité, et ajout d'une règle dans « Conventions » : toute
  vérification qui démarre le serveur doit positionner `ALCHESS_SKIP_BOARD=1`
  et `ALCHESS_NO_BROWSER=1`, jamais sans.

La variable `BROWSER` des tests e2e (`conftest.py`) n'a pas été modifiée —
elle reste une défense supplémentaire indépendante.

Suite complète hors `hardware` : 402 passés, 74 ignorés.

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

# Changelog — Issue #287

## Dépendances : retrait des paquets inutilisés de requirements.txt

Audit manuel confirmant qu'aucun des six paquets n'est importé, appelé
indirectement, ni référencé par un script d'installation (Linux/Windows)
ou le workflow GitHub :

- `pyproject-toml` (aucune référence — distinct du fichier `nicsoft/pyproject.toml`,
  qui utilise `setuptools.build_meta` sans dépendre de ce paquet).
- `pybind11` — reste de l'ancienne extension C++ ; le `.gitmodules` référence
  toujours le sous-module `src/thirdparty/pybind11` (code source C++, non
  touché), mais le paquet pip du même nom n'est plus utilisé depuis le
  passage à `nicsoft/niclink/hid_backend.py` (hidapi pur Python).
- `readchar`, `pyserial` — aucune utilisation trouvée.
- `stockfish` (paquet pip) — le moteur Stockfish est piloté via `python-chess`
  (`chess.engine.SimpleEngine.popen_uci`, cf. `nicsoft/engine/`) ; toutes les
  mentions « Stockfish » dans le code et la doc désignent le moteur lui-même
  (binaire `apt install stockfish` / téléchargement Windows), pas ce paquet.
- `pyttsx3` — le module indique lui-même son abandon
  (`nicsoft/modes/opening_explorer/tts_engine.py`) ; le fallback TTS local
  hors-ligne appelle directement le binaire système `espeak-ng` en
  sous-processus, sans passer par ce paquet.

- `requirements.txt` : suppression des six lignes. Le commentaire sur le
  prérequis système `espeak-ng` est conservé et reformulé pour ne plus
  dépendre de `pyttsx3` (il documente maintenant directement le fallback
  TTS de `tts_engine.py`).
- `ETAT_PROJET.md` : retrait de `stockfish`, `pyserial`, `readchar` de
  l'inventaire des versions Python (section 5).
- Aucune autre doc ne présentait l'un de ces six paquets comme nécessaire.
  Mentions laissées volontairement, hors sujet des six paquets :
  `INSTALLATION_ALCHESS.md` section 4c (recompilation historique du driver
  C++, ne cite aucun des six paquets) et toutes les mentions « Stockfish »
  (le moteur, pas le paquet pip) dans `SPECIFICATIONS.md`, `README.md`,
  `TESTS.md`, `HISTORIQUE_BUGS.md`, `INSTALLATION_ALCHESS.md`.
- `setuptools`, `wheel`, `python-socketio`, `Werkzeug`, `numpy`, `hidapi`,
  `chess`, `Flask`, `Flask-SocketIO`, `edge-tts` non touchés, comme demandé.
  `.gitmodules` et `.audit.json` non touchés.

**Vérifications dans un venv temporaire** (`python3 -m venv`, supprimé en fin
de tâche) construit depuis le nouveau `requirements.txt` + `pip-audit` +
`pytest` :
- `pip install -r requirements.txt` : résolu sans erreur (Flask 3.1.3,
  Flask-SocketIO 5.6.1, python-socketio 5.16.2, Werkzeug 3.1.9, chess 1.10.0,
  hidapi 0.15.0, numpy 2.5.4, edge-tts 7.3.1, setuptools 84.1.0, wheel 0.46.2
  + dépendances transitives : aiohttp, python-engineio, simple-websocket,
  etc.).
- `pip check` : aucune dépendance cassée.
- `pip-audit` : aucune vulnérabilité connue.
- Import de tous les modules de `nicsoft` sans matériel : OK, à l'exception
  attendue et pré-existante de `nicsoft.web.launcher` (`import gi` —
  `python3-gi`, paquet système apt, jamais présent dans `requirements.txt`,
  sans rapport avec les six paquets retirés).
- `pytest --ignore=nicsoft/tests/e2e -m "not hardware"` dans le venv
  temporaire : **334 passed, 72 skipped**.
- Démarrage de `python -m nicsoft.web` dans le venv temporaire : aucun
  échiquier physique connecté sur cette machine → bascule automatique sur
  l'échiquier virtuel sans solliciter de matériel ; `GET /` → `200 OK`.
  (Le démarrage a transitoirement arrêté `ModemManager` sur la machine hôte
  comme le fait l'application au lancement — remis à `active` en fin de
  vérification.)

**Suite de tests complète, environnement habituel** (hors `e2e`, hors
`hardware`) : **334 passed, 72 skipped** — identique au venv temporaire.

Les tests `e2e` (environnement utilisateur, non modifié) n'ont pas été
exécutés, conformément à la consigne.

**Commande pour qu'Alain désinstalle ces paquets de son propre
environnement** (`~/NicLink/venv`) :
```bash
pip uninstall -y pyproject-toml pybind11 readchar pyserial stockfish pyttsx3
```

# Changelog — Issue #286

## Téléchargement Rodent IV (Windows) : installation tout-ou-rien, vérifiée dans un dossier temporaire (SEC-025)

`nicsoft/web/server.py` téléchargeait chaque binaire Rodent IV directement
dans `ENGINES_DIR/rodent-iv-win/` avant de vérifier son empreinte SHA-256
(issue #256) : une interruption réseau ou un délai dépassé en cours de
lecture pouvait laisser un fichier tronqué dans le dossier du moteur, et un
échec sur le dernier des trois fichiers laissait les deux premiers en place
sans que rien ne signale l'installation incomplète. Une installation
existante qui fonctionnait pouvait donc être détruite par une tentative de
mise à jour ratée.

- **Téléchargement dans un dossier temporaire** `ENGINES_DIR/rodent-iv-win.tmp`
  (même volume que `rodent-iv-win/`, donc bascule finale atomique) : les
  trois fichiers y sont téléchargés et vérifiés (délai d'attente, empreinte
  SHA-256) avant toute écriture dans le dossier définitif.
- **Mise en place tout-ou-rien** (`_installer_rodent_depuis_temp`) : une fois
  les trois fichiers conformes, le dossier définitif est remplacé en une
  seule opération (`os.replace`, via un dossier `.bak` intermédiaire). Si la
  bascule elle-même échoue (fichier verrouillé parce que le moteur tourne,
  disque plein...), l'ancien dossier est restauré à l'identique et l'erreur
  est propagée — aucune installation existante n'est jamais perdue.
  `_telecharger_fichier_rodent` ne touche donc plus jamais le dossier
  définitif : il écrit uniquement dans le dossier temporaire, ce qui
  supprime du même coup le risque de troncature d'un fichier déjà installé.
- **Nettoyage systématique** du dossier temporaire (`_nettoyer_dossier_temp_rodent`)
  en tout début de tentative (résidu d'un arrêt brutal précédent) et à la
  fin de chaque tentative, succès ou échec — le dossier définitif n'est
  plus créé par avance, et ne reste jamais vide après un échec.
- **Vérification du schéma d'adresse** : `_telecharger_fichier_rodent` refuse
  toute URL qui ne commence pas par `https://`, avant la moindre requête
  réseau, avec le même échec propre (rien n'est installé) que les autres cas
  (empreinte invalide, référence absente). Aucun commentaire `noqa`/`nosec`
  ajouté (consigne projet) — à vérifier si l'outil d'audit de sécurité
  continue malgré tout de signaler cet appel `urlopen`.
- **Logique extraite et testable sans Windows** : `_telecharger_et_installer_rodent`
  orchestre téléchargement + mise en place indépendamment du handler
  SocketIO (`on_download_rodent`), qui ne fait plus que l'appeler et émettre
  les événements de progression/résultat/statut — séquence d'événements
  inchangée en cas de succès.
- **Tests** (`nicsoft/tests/test_rodent.py`, sans réseau ni matériel, tout en
  `tmp_path`, jamais le vrai `ENGINES_DIR`) : succès complet des trois
  fichiers ; empreinte invalide sur le troisième fichier → dossier définitif
  absent ; coupure réseau en cours de lecture du deuxième fichier → aucun
  fichier tronqué ; échec de bascule finale (simulant un fichier verrouillé)
  → ancienne installation restaurée à l'identique ; échec alors qu'une
  installation valide existait → anciens fichiers strictement inchangés ;
  nettoyage d'un dossier temporaire résiduel laissé par un arrêt brutal ;
  URL non-https refusée sans accès réseau.
- `.audit.json` non modifié. Suite de tests complète hors `hardware`
  (`pytest -m "not hardware"`) : 378 passed, 73 skipped (13 nouveaux/révisés
  dans `test_rodent.py`, tous verts).

**Vérification manuelle suggérée sous Windows** (non faisable depuis ce
dépôt Linux) : lancer le téléchargement depuis l'interface, couper le réseau
en cours de route, et constater que `engines/rodent-iv-win/` est strictement
inchangé (aucun fichier tronqué, aucune installation existante perdue).

## Audit : justifie deux captures silencieuses, corrige des commentaires pris pour du code mort, documente deux gros fichiers (issue #285)

- `nicsoft/modes/exercices/exercices.py` (ligne ~906, PRO-012) : la capture de file d'attente vide dans `_wait_placement_adv` passe à `contextlib.suppress(_q.Empty)`, ciblée sur la seule exception de file vide, sans changer le flux de contrôle (le `except Exception: pass` voisin, déjà commenté, reste inchangé pour les erreurs transitoires).
- `nicsoft/modes/exercices/add_ouverture.py` (ligne ~186, PRO-012) : la capture générique autour de `tmp.san(e.move)` dans `verify_from_web()` passe de `except Exception: pass` à `except Exception as e2: logger.debug(...)`. `chess.polyglot.find_all()` ne renvoie que des coups déjà légaux pour la position, donc l'échec de `san()` ne devrait pas survenir en pratique ; resserrer l'exception aurait demandé de deviner son type exact sans garantie. La même fonction CLI (`main()`, ligne 89-90) applique déjà ce traitement par trace `debug` depuis l'issue #261 — choix aligné sur ce précédent, aucun changement de comportement (le coup reste simplement absent de l'affichage en cas d'échec).
- `nicsoft/engine/engine_analysis.py` (PRO-013) : reformulation en phrases des commentaires explicatifs pris pour du code désactivé (lignes 95, 105, 109-110, 117) — suppression des signes `=`/`→`, information inchangée, aucune modification de code.
- `CONTEXTE.md` (ARC-004) : ajout de `exercices.py` (~1350 l.) et `labo.py` (~450 l.) à la liste des gros fichiers conservés volontairement, avec leurs coutures naturelles de découpage ; mise à jour de la ligne « Ordre ».
- `CONTEXTE.md` (Conventions) : ajout de la règle « pas de `noqa`/`nosec` » en attendant l'évolution de l'outil d'audit — corriger plutôt que supprimer.
- `.audit.json` non modifié. Suite de tests complète (hors hardware) : 370 passed, 73 skipped.

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

# Changelog — Issue #283

## Retranscription : bandeau de reprise à chaque ouverture, reprise en un clic, libellé clarifié

- **Bandeau « Session en cours » proposé à chaque ouverture de l'écran de
  retranscription**, pas seulement 1,5s après le démarrage du programme.
  `nicsoft/web/alchess.py` : extraction de l'envoi de l'événement
  `retranscription_en_cours` dans une fonction dédiée
  `_check_retranscription_session()` (relit le fichier de session via
  `nicsoft.modes.retranscription.retranscription.load_session()`), appelée
  à chaque fois que l'action de menu `mode/retranscription` est traitée.
  Suppression de l'envoi unique au démarrage (`main()`), devenu redondant.
  Côté frontend (`app.js`), le bandeau est masqué explicitement (valeur
  `"none"`, jamais un effacement de style en ligne) à chaque ouverture de
  l'écran, avant d'être réaffiché si le serveur retrouve une session.
- **« Reprendre » rouvre la session en un seul clic** : `retransResume(true)`
  appelle désormais directement `startRetranscription()` (mêmes données que
  « Démarrer la partie », avec l'indicateur `resume: true`) au lieu de se
  contenter de masquer le bandeau et d'attendre un second clic. Le
  comportement de « Nouvelle » est inchangé.
- **Libellé clarifié** pour le bouton qui termine la retranscription et
  exporte le PGN avec un résultat inconnu (`retrans.btn.sauver`, fr/en/de) :
  dit désormais explicitement qu'il termine la partie (sans résultat) au
  lieu de laisser croire à une simple sauvegarde réversible. « Quitter sans
  sauver » est inchangé, aucun nouveau bouton ajouté.
- **Tests** (`nicsoft/tests/`, aucun accès au vrai dossier de données
  utilisateur — `SAVE_PATH` monkeypatché vers un `tmp_path`) :
  - `test_retranscription_resume_event.py` — l'événement de reprise est
    envoyé quand une session existe, absent sinon ; renvoyé à chaque appel
    (pas seulement une fois) ; la simple lecture ne modifie pas le fichier.
  - `test_retrans_resume_banner_display.py` — verrou ciblé sur ce bandeau :
    aucune affectation `style.display = ""` ne doit viser
    `#retrans-resume-banner` tant que sa classe CSS le cache par défaut
    (complète le garde-fou générique `test_css_extraction_hidden_elements.py`
    de l'issue #279).

### Vérification manuelle
Retranscrire quelques coups, arrêter brutalement le programme (Ctrl+C dans
le terminal), relancer, ouvrir Retranscription, cliquer sur « Reprendre » —
la partie doit se rouvrir immédiatement, sans second clic. Puis quitter
proprement (terminer et enregistrer, ou quitter sans sauver) et rouvrir
l'écran Retranscription : le bandeau ne doit plus s'afficher tant qu'aucune
session n'est en attente.

# Changelog — Issue #282

## Fix : nulle acceptée traitée comme une erreur en mode Pédagogique

`Game._traiter_nulle` (`nicsoft/modes/pedagogique/pedagogique.py`) englobait
dans un seul bloc `except Exception` à la fois l'évaluation de la position
et l'appel à `_end_game(...)` qui termine la partie en levant volontairement
`BackMenuExit` (exception de contrôle de flux, sans message). Le bloc avalait
cette exception : la partie ne se terminait jamais, le fil de surveillance de
l'échiquier continuait de tourner (d'où les « cases incorrectes » répétées en
comparant au plateau final), le lanceur restait signalé « partie en cours »
et le mode Pédagogique ne pouvait plus être relancé sans redémarrer. En plus,
l'utilisateur recevait un toast « nulle refusée » alors que la nulle venait
d'être acceptée, avec un journal affichant « Erreur évaluation nulle: »
(message vide).

- Seule l'évaluation moteur reste protégée par le `try/except` ; l'appel de
  fin de partie (`_end_game`) en est sorti, laissant `BackMenuExit` remonter
  normalement jusqu'au lanceur (`nicsoft/core/game_manager_modes/pedagogique.py`,
  qui l'intercepte déjà correctement avant son `except Exception`).
- Seuil d'acceptation (150 centipions, décision utilisateur conservée tel
  quel) extrait en constante nommée `SEUIL_ACCEPTATION_NULLE_CP`, avec
  commentaire explicatif.
- Le nom réel de l'adversaire (ex. « Rodent 1200 (Tal) », « Maia 1200 »,
  « Stockfish ~1500elo » — celui déjà affiché au-dessus de l'échiquier) est
  désormais transmis au fil de partie (`game.opponent_label`) et utilisé dans
  le titre de la boîte de confirmation de nulle et dans le motif de refus, à
  la place du texte fixe « Stockfish », dans les 3 langues (clés
  `modal.nulle_stockfish_titre` et `toast.nulle_refusee_default` paramétrées
  avec `{opponent}`).
- Recherche systématique des autres modes (humain, exercices, labo,
  retranscription, explorer, lanceurs) : aucun autre bloc `except` générique
  n'avale une exception de contrôle de flux équivalente à `BackMenuExit`
  (celle-ci n'existe que dans ce fichier). Points de vigilance relevés sans
  correction (mécanismes différents, actuellement sûrs) : `human.py` utilise
  `sys.exit(0)` pour terminer une partie, protégé par un `except SystemExit`
  placé avant le `except Exception` — fragile en cas de futur
  `except BaseException` ou réordonnancement ; `exercices.py` utilise
  `ExitNicLink` de la même façon, également bien ordonné aujourd'hui.
- Tests ajoutés (`nicsoft/tests/test_pedagogique_nulle.py`, moteur et
  interface simulés, sans matériel) : nulle acceptée → `BackMenuExit` remonte
  sans aucun événement de refus ; nulle refusée car l'adversaire est trop
  bien placé ; évaluation impossible → refus avec le message dédié et la
  partie continue ; valeurs limites du seuil (150 accepté, 151 refusé) ; nom
  de l'adversaire transmis dans le message de refus.

### À vérifier manuellement par Alain (échiquier physique)

- Proposer la nulle contre Stockfish, Maia et Rodent chacun dans une position
  où le moteur est nettement mieux (doit refuser, message citant le bon nom)
  et une où il est égal ou moins bien (doit accepter et terminer la partie).
- Après une nulle acceptée suivie d'un retour au menu (ou d'une analyse puis
  retour au menu), relancer le mode Pédagogique sans redémarrer le programme,
  et vérifier qu'aucun message « cases incorrectes » ne réapparaît (preuve que
  l'ancien fil de partie s'est bien arrêté).

# Changelog — Issue #278

## Découpage de game_manager.py en lanceurs par mode (ARC-004)

`nicsoft/core/game_manager.py` (~1180 lignes) orchestrait les sept modes
de jeu dans un seul fichier, avec un état global partagé entre leurs
fonctions. L'audit (règle ARC-004) le signalait comme fichier à
découper ; le rapport le jugeait à risque moyen (couplage à sens unique,
game_manager → modes, jamais l'inverse).

- **Nouveau sous-dossier `nicsoft/core/game_manager_modes/`** (9 fichiers,
  tous nettement sous 300 lignes) :
  - `state.py` (143 l.) — état réellement partagé entre plusieurs modes
    (échiquier courant, mode virtuel) via accesseurs
    (`get_nl_inst_ref`/`set_nl_inst_ref`, `get_virtual_mode`/`set_virtual_mode`),
    plus utilitaires communs (attente de position, toasts d'erreur,
    lecture config moteur).
  - `pedagogique.py` (158 l.), `humain.py` (111 l.),
    `retranscription.py` (45 l.), `exercices.py` (245 l. — exercices et
    drill, avec leur état de session propre : plus exporté nulle part),
    `labo.py` (98 l.) + `labo_session.py` (256 l. — boucle d'actions de la
    session labo, avec le drapeau d'annulation de copie propre à ce
    couple de modules), `labo_libre.py` (140 l.), `explorer.py`
    (139 l. — état de session Opening Explorer propre à ce module).
  - État qui ne servait qu'à un seul mode (session d'exercice/drill, flag
    d'annulation de copie labo, session explorer) rendu local au module de
    ce mode plutôt qu'exporté globalement.
- **`nicsoft/core/game_manager.py` devient une façade** (36 lignes) :
  réexporte les mêmes objets fonctions qu'avant (mêmes noms, y compris les
  privées utilisées par un test — `_run_humain` — et par alchess.py/server.py
  via import local — `_run_exercice`, `_run_drill`, `_make_labo_session`,
  etc.). Aucune variable d'état réaffectable réexportée : uniquement des
  fonctions.
- **Nouvelle fonction d'accès `get_virtual_mode()`** (`state.py`) : remplace
  les deux lectures directes de `gm._virtual_mode` dans
  `nicsoft/web/alchess.py` (handler `set_virtual_mode` du menu), qui
  auraient figé une copie périmée après le découpage puisque la variable
  n'est plus un simple module-global importable en toute sécurité par
  `from ... import`.
- Comportement inchangé : aucun événement envoyé, message de log, ou
  branche d'exception modifiés — seule la répartition du code entre
  fichiers a changé. Les nouveaux modules n'importent toujours jamais
  `nicsoft.web` (ARC-001, vérifié par la suite de tests existante qui
  découvre désormais ces 9 nouveaux fichiers automatiquement : 63 → 73
  fichiers surveillés, 308 → 344 tests passés hors tests matériel, 0 échec).
- Aucun nouveau dossier hors de `nicsoft/core/` : le découpage reste
  entièrement contenu dans `nicsoft/core/game_manager_modes/`.

# Changelog — Issue #281

## Découpage de explore_book.py et eco_import.py, mutualisation de la logique d'import du catalogue

Les deux fichiers dépassaient le seuil de taille de l'audit (règle ARC-004) :
`explore_book.py` (~410 lignes) et `eco_import.py` (~630 lignes). Découpés en
modules par section, sans changement de comportement.

- **`explore_book.py`** devient un point d'entrée qui réexporte les mêmes
  objets publics, répartis dans :
  - `explore_book_display.py` — affichage terminal (échiquier ASCII, ligne
    de coups) : `weight_bar`, `print_board`, `format_move_line`.
  - `explore_book_import.py` — ajout interactif au catalogue : `do_import`.
  - `explore_book_cli.py` — boucle interactive en ligne de commande : `main`.
  - `explore_book_web.py` — fonctions appelées par le serveur web :
    `list_books_for_web`, `get_moves_from_web`.
- **`eco_import.py`** devient de même un point d'entrée, réparti dans :
  - `eco_import_data.py` — chargement des fichiers TSV ECO et filtre :
    `ECO_FILES`, `load_eco`, `parse_filter`.
  - `eco_import_display.py` — popularité dans les livres et affichage des
    résultats : `get_popularity`, `pop_bar`, `pop_label`, `display_results`.
  - `eco_import_import.py` — import d'une entrée, interactif ou en lot :
    `import_entry`, `quick_import_batch`.
  - `eco_import_cli.py` — boucle interactive en ligne de commande : `main`.
  - `eco_import_web.py` — fonctions appelées par le serveur web :
    `search_eco_from_web`, `import_eco_from_web`.
- **Mutualisation de la logique de catalogue dupliquée** : la vérification
  « cette séquence de coups est-elle déjà dans le catalogue ? » était
  recopiée à l'identique 6 fois entre `explore_book.py` (×2) et
  `eco_import.py` (×3), plus une fois de plus sous un nom différent
  (`in_catalogue`) — regroupée dans une nouvelle fonction
  `trouve_doublon(uci_moves, existing_inits)` ajoutée à `_catalogue.py`, et
  réutilisée partout. `do_import` (explorateur) réimplémentait aussi la
  boucle `check_books()` ligne pour ligne ; remplacé par un appel direct à
  la fonction déjà partagée.
  - **Non mutualisé, volontairement** : `search_eco_from_web` construit un
    dict `{tuple(coups): id}` pour vérifier jusqu'à 300 lignes en O(1)
    chacune, plutôt que de rappeler `trouve_doublon` en boucle (O(n) à
    chaque appel) — comportement équivalent, mais le remplacer aurait
    dégradé les performances sur un gros catalogue. De même, la sélection
    du livre cible reste différente entre `do_import` (menu interactif
    numéroté si plusieurs livres correspondent) et
    `import_entry`/`quick_import_batch`/`import_eco_from_web` (sélection
    automatique via `best_book_for`, déjà partagée) : ce sont deux
    parcours utilisateur réellement différents (l'un demande à l'humain,
    l'autre choisit seul), pas une duplication à fusionner.
- **Aucun fichier de données renommé ni déplacé** (`eco_a.tsv`…`eco_e.tsv`,
  `books/*.bin`, `exercices.py`) — les tests e2e qui lisent les vraies
  données ECO de l'utilisateur continuent de fonctionner sans changement.
- `manage.py` et `server.py` continuent d'importer `main`,
  `search_eco_from_web`, `import_eco_from_web`, `list_books_for_web`,
  `get_moves_from_web` directement depuis `explore_book`/`eco_import` —
  aucune modification nécessaire dans ces deux fichiers.
- Les tests de garde ARC-001 (`test_no_web_import.py`,
  `test_no_undefined_names.py`) découvrent automatiquement les nouveaux
  fichiers via le glob de `_arc001_discovery.py` — vérifié : les 9 nouveaux
  modules apparaissent dans la liste découverte, sans mise à jour manuelle.

# Changelog — Issue #280

## Suppression de cinq fichiers morts découverts par les tests de garde ARC-001

Suite de l'élargissement de la découverte ARC-001 à tous les fichiers de
`core`, `modes`, `niclink`, `utils` et `engine` (issue #272), qui avait mis
en évidence cinq fichiers cassés et jamais appelés, documentés comme
exclusions avec test miroir plutôt que supprimés sur le moment.

- Vérification à jour par recherche dans tout le dépôt (code, scripts,
  packaging, documentation, hors changelogs) : aucune référence réelle à
  l'un des cinq fichiers (seules les occurrences de `light_board` sont le
  nom d'un paramètre dans `driver.py`/`virtual_board.py`, sans rapport).
- **Fichiers supprimés** :
  - `nicsoft/utils/light_board.py`
  - `nicsoft/utils/turn_out_all_lights.py`
  - `nicsoft/modes/exercices/__main__.py`
  - `nicsoft/modes/labo/__main__.py`
  - `nicsoft/modes/retranscription/__main__.py`
- `nicsoft/tests/test_no_web_import.py` : retrait de
  `MODULES_NON_IMPORTABLES_SEULS` (les 5 exclusions) et de son test miroir
  `test_modules_non_importables_restent_documentes` ; tous les modules
  découverts passent désormais par les tests normaux.
- `nicsoft/tests/test_no_undefined_names.py` : retrait de l'exclusion
  `nicsoft/utils/light_board.py` (`FICHIERS_AVEC_NOMS_NON_DEFINIS_CONNUS`)
  et de son test miroir `test_fichiers_exclus_restent_documentes`.
- `.audit.json` non touché, comme demandé.
- Suite complète (`pytest -m "not hardware"`) : 293 passed, 60 skipped,
  0 failed — même niveau de protection, aucun fichier supplémentaire
  ignoré.

# Changelog — Issue #279

## Interface : correction des éléments restés cachés ou bloqués depuis l'extraction des styles en ligne vers le CSS

Suite des issues #230-#248 (déplacement des styles `style="..."` écrits
dans le HTML vers des classes CSS). Pour les éléments cachés/désactivés par
défaut (`display:none`, `pointer-events:none`, `opacity<1`), le JS se
contentait d'effacer le style en ligne (`el.style.X = ""`) pour les
« révéler » — ça fonctionnait quand la valeur cachante était seulement
inline, mais ne fait plus rien depuis qu'elle vient d'une règle CSS de
classe : l'élément reste caché, sans la moindre erreur console (visible
seulement en test manuel réel ou via un moteur de rendu).

### Cinq cas confirmés par le rapport, corrigés dans `nicsoft/web/static/app.js`

1. **Contrôles de navigation de l'écran d'analyse** (lecture auto, curseur
   de vitesse, Précédent, Suivant) : `pointer-events` — déjà corrigé à la
   main par Alain avant cette issue (commit "interface : corrige à la main
   l'affichage du bandeau de reprise et la navigation de l'analyse"),
   vérifié et laissé tel quel.
2. **Exercices — bouton « Continuer avec Stockfish »** en fin de ligne
   théorique (`#ex-btn-continuer` / `.exr-btn-continuer`) : `style.display`
   passé de `""` à `"block"`.
3. **Retranscription — formulaire de l'onglet « Exercice »**
   (`#retrans-form-exercice` / `.retrans-form-card-hidden-init`) :
   `style.display` passé de `""` à `"block"` dans `retransSelectTab()`
   (et, par cohérence, le formulaire « Partie » du même switch).
4. **Retranscription, mode exercice — bouton « Sauver et continuer »**
   (`#btn-retrans-save-continue` / `.retrans-game-btn-save-continue`) :
   `style.display` passé de `""` à `"block"`.
5. **Configuration d'une partie — alerte « aucun moteur disponible »**
   (`#cfg-no-engine-alert` / `.cfg-no-engine-alert`) : `style.display`
   passé de `""` à `"block"` dans `_checkNoEngineAvailable()`.

### Sixième cas trouvé par la recherche systématique de cette issue

- **Messages « moteur non installé »** (`#cfg-stockfish-unavailable`,
  `#cfg-maia-unavailable`, `#cfg-rodent-unavailable`, classe partagée
  `.cfg-engine-unavailable-msg { display:none }`) : `_applyStockfishAvailability()`,
  `_applyMaiaAvailability()`, `_applyRodentAvailability()` effaçaient le
  style en ligne (`""`) pour les révéler quand le moteur correspondant est
  absent — jamais affichés depuis l'extraction. Passé à `"block"`. Les
  éléments jumeaux `#labo-*-unavailable` (classe `.labo-unavail-msg`, sans
  `display` en CSS, style `display:none` resté inline dans le HTML) ne sont
  pas affectés par ce bug et continuent de fonctionner avec `""`/`"block"`
  indifféremment — la valeur `"block"` leur convient donc aussi.

### Recherche systématique — cas examinés et écartés (déjà corrects)

Tout `.style.(display|opacity|pointerEvents|visibility)` du fichier
effaçant un style en ligne (`= ""`) a été passé en revue (une quarantaine
d'occurrences). Écartés parce que la classe CSS de l'élément ne cache rien
par défaut (pas de règle concurrente), ou parce que le code utilise déjà
une valeur explicite, ou une bascule de classe d'état
(`classList.toggle/add/remove`) avec une règle CSS correspondante :
`card-nav-save`, `pgn-lib-import-btn`/`-spinner`, `labo-cfg-sf/maia/rodent`
(style inline, pas de classe), `ex-variete-bar`/`ex-drill-bar`,
`modal-cancel` (4 occurrences), `btn-pause`/`btn-pause-hh`, `pause-select`
(opacité), `basket-select` (opacité/pointer-events), `syncBtn`
(`ex-btn-sync`), `#toast` (classe `.show`), `#modal-overlay` (classe
`.open`), `#coller-pgn-zone` (classe `.is-open`), `#autoupdate-warning`
(classe `.hidden`), `#cfg-section-*` (classe `.cfg-section-hidden` via
`classList.toggle`), et tous les écrans `#screen-*` (toujours des valeurs
explicites `"flex"/"grid"/"none"`).

### Cas douteux, non corrigés (hors périmètre de cette issue)

- **`#btn-pause-abandonner`** : déjà documenté lors d'une extraction
  antérieure comme bouton jamais montré par aucun JS (mort), figé en classe
  `.game-pause-hidden-init` sans changement de comportement voulu —
  confirmé inchangé, pas une régression de #230-#248.
- **`#countdown { display:none !important; }`** : règle CSS avec
  `!important` qui bloquerait de toute façon toute tentative du JS de la
  révéler (même avec une valeur explicite) — mais `startCountdown()`, la
  seule fonction qui tente de l'afficher, n'est appelée nulle part dans le
  code (fonction morte). Pré-existe très probablement à la série
  #230-#248 (pas un style en ligne effacé, un `!important` CSS direct).
  Hors périmètre ; signalé pour mémoire.
- **`#labo-feedback`** : deux éléments distincts partagent cet id
  (`.labo-feedback-center` et `.labo-feedback-side`, tous deux
  `display:none` en CSS) ; le seul code JS qui le référence ne fait que le
  masquer (`style.display = "none"`), jamais l'afficher — semble vestigial/
  mort plutôt que lié au défaut de cette issue (aucun effacement de style
  en ligne en cause). Non corrigé, signalé pour mémoire.

### Test de garde (sans navigateur)

`nicsoft/tests/test_css_extraction_hidden_elements.py` — analyse
statiquement `templates/index.html` (association id→classes), `css/main.css`
(règles de classe simples, hors `@media`, qui cachent par défaut :
`display:none`, `pointer-events:none`, `opacity<1`, `visibility:hidden`) et
`static/app.js` (motif `document.getElementById("id")...style.PROP = ""`,
y compris via variable intermédiaire). Échoue si un élément correspond aux
deux. Vérifié qu'il détecte bien les 4 régressions ci-dessus quand
réintroduites (et qu'il ne produit aucun faux positif sur l'état actuel).
Aucune exception documentée nécessaire à ce jour (`EXCEPTIONS_ID_PROP`
prévu pour les futurs cas légitimes).

### Tests e2e (Playwright, infrastructure existante dans `nicsoft/tests/e2e/`)

`nicsoft/tests/e2e/test_review_nav_279_e2e.py` (nouveau) :
- charge une courte partie via « Coller PGN » dans l'écran Analyse (chemin
  déjà utilisé par `test_smoke_e2e.py` comme proxy de l'état `game_over`
  sans échiquier ni partie jouée ; `parsePgn()` est purement client, aucun
  appel socket ni écriture disque) ;
- vérifie que Précédent/Suivant ne sont pas `disabled` **et** que
  `pointer-events` n'est pas `none` (le symptôme exact du cas #1) ;
- vérifie qu'un clic sur Précédent puis Suivant fait réellement changer le
  coup affiché (`#review-move-san`), pas seulement l'attribut `disabled`.
- Vérifié manuellement que ces deux tests échouent (timeout Playwright
  « intercepts pointer events ») si on réintroduit la régression du cas #1,
  et passent une fois corrigé.

Test e2e pour le bouton « Continuer » des Exercices **non ajouté** : pas
réaliste avec l'infrastructure actuelle sans risque de régresser sur les
contraintes de l'issue — atteindre une vraie fin de ligne théorique suppose
(a) un catalogue d'ouvertures réel, qui n'est pas versionné dans le dépôt
(`data/` est dans `.gitignore`, dépend du dossier utilisateur), donc un
test non reproductible/portable entre environnements, et (b) une
synchronisation par coup via le thread d'exercice (plateau virtuel), chemin
jamais exercé par l'infrastructure e2e actuelle (tous les tests existants
sont purement navigationnels, aucun ne joue de coup réel) — risque de
flakiness et de dépendance non maîtrisée au dossier de données réel.

### Vérifications manuelles suggérées

1. Terminer une partie (ou charger un PGN en Analyse), puis cliquer sur
   Précédent/Suivant, survoler le curseur de vitesse et le bouton lecture
   automatique : tout doit réagir normalement.
2. Exercices : jouer une ligne théorique jusqu'au bout → le bouton
   « Continuer avec Stockfish » doit apparaître (si un moteur est
   disponible).
3. Retranscription : ouvrir l'onglet « Exercice » → le formulaire doit
   s'afficher ; démarrer une retranscription en mode exercice → le bouton
   « Sauver et continuer » doit apparaître pendant la partie.
4. Configuration d'une partie sans aucun moteur disponible (si faisable) :
   l'alerte « Aucun moteur d'échecs n'est disponible » doit s'afficher et
   le bouton Démarrer doit être grisé.

### Tests

- `nicsoft/tests/test_css_extraction_hidden_elements.py` (nouveau).
- `nicsoft/tests/e2e/test_review_nav_279_e2e.py` (nouveau, 2 tests).
- Suite complète hors hardware (`pytest nicsoft/tests -m "not hardware"`) :
  311 passed, 65 skipped.

# Changelog — Issue #277

## Retranscription et Outils : ne plus afficher des demi-coups sous le nom de « coups »

Suite du rapport de l'issue #274 (confusion demi-coup/coup aux échecs), pour
les deux endroits qu'elle avait listés sans les corriger.

- **Règle de conversion partagée** : `pgn_move_number`/`pgn_moves_played`
  déplacées de `nicsoft/modes/exercices/exercices.py` vers
  `nicsoft/engine/board_utils.py` (module neutre partagé, ne dépend jamais
  de `nicsoft.web` — ARC-001). `exercices.py` les réimporte désormais
  depuis ce module ; comportement et test existant
  (`test_exercices_pgn_move_count.py`) inchangés.
- **Retranscription — bannière de session reprise** (`app.js`, handler
  `retranscription_en_cours`) : `nicsoft/web/alchess.py` envoyait le nombre
  brut de demi-coups de la session sauvegardée dans le champ `moves` ;
  converti via `pgn_moves_played()`. Pluriel correct ajouté dans les 3
  langues (nouvelle clé `common.n_coup`, singulier, à côté de
  `common.n_coups` déjà existante) ; `app.js` choisit la bonne clé selon
  `data.moves === 1`.
- **Retranscription — champ `move_num` de l'événement par coup** : non lu
  par aucun code (interface, tests, autres modules — vérifié par grep),
  renommé en `half_moves_played` dans
  `nicsoft/modes/retranscription/retranscription.py` pour refléter sa
  vraie nature (nombre brut de demi-coups, pas un numéro de coup PGN).
- **Outils (panneau d'administration du catalogue)** : les trois libellés
  techniques comptant des demi-coups sans les convertir — `outils.label.coups`
  ("Coups"/"Moves"/"Züge"), `outils.polyglot.profondeur` (profondeur
  d'exploration du livre), `outils.init_coups` (coups d'initialisation
  d'une ligne) — renommés en « Demi-coups »/« Half-moves »/« Halbzüge »
  dans les 3 langues, sans toucher aux valeurs ni à aucun format de
  fichier. Nouvelle clé `outils.n_demi_coups` ajoutée pour que le compte
  affiché à côté de la liste de coups (`outils.label.coups`, ligne ~6036
  d'`app.js`) reste cohérent avec le libellé renommé (il réutilisait avant
  `common.n_coups`, partagé avec d'autres écrans non concernés par cette
  issue).
- Mode Humain contre Humain et mode Pédagogique non touchés, comme demandé.

### Autres endroits avec la même confusion, trouvés en route mais non corrigés (hors périmètre de cette issue)

- `app.js` ligne ~1693 : options de la combobox `rv-seq-moves` (mode
  Pédagogique, replay vidéo) — `t("common.n_coups", {n: opt.value})`.
- `app.js` ligne ~3461 : journal du Labo à l'import d'un PGN —
  `t("common.n_coups", {n: history.length})`, `history.length` étant un
  nombre de demi-coups.
- `app.js` ligne ~4403 : cartes de sélection de lignes à l'entraînement
  (drill) en mode Exercices — `t("common.n_coups", {n: nb})` où `nb =
  (o.line || o.init || []).length` est un nombre de demi-coups.
- `app.js` ligne ~6051/6057 : `outils.livre_count` ("{count} coup(s)
  suivant : {next}") — vérifié : `count` est un poids/fréquence Polyglot,
  pas un compte de demi-coups ; pas la même confusion, laissé tel quel.

### Vérification manuelle suggérée

1. Retranscription : commencer une retranscription, jouer quelques coups
   (demi-coups impair et pair à tester), quitter sans terminer (`Retour
   menu` ou fermer l'app), puis relancer l'app : la bannière de reprise
   doit afficher un nombre de coups conforme à la convention PGN
   (singulier/pluriel correct) dans les 3 langues.
2. Outils : ouvrir le panneau Outils des exercices (administration du
   catalogue), vérifier une ligne existante et l'exploration du livre
   Polyglot : les libellés doivent dire « Demi-coups »/« Half-moves »/
   « Halbzüge » (profondeur, coups d'une ligne, coups d'initialisation),
   valeurs inchangées.

### Tests

- `nicsoft/tests/test_board_utils_pgn_move_count.py` (nouveau) : couvre
  `pgn_move_number`/`pgn_moves_played` depuis leur nouvel emplacement
  (0, 1, 2, 5, 24 demi-coups) et la valeur envoyée pour une session de
  retranscription reprise.
- `nicsoft/tests/test_exercices_pgn_move_count.py` : inchangé, toujours
  vert (les fonctions sont réimportées, pas redéfinies).
- Suite complète hors hardware (`pytest nicsoft/tests/ -m "not hardware"`) :
  260 passed, 54 skipped.

# Changelog — Issue #276

## Découpage de engine_manager.py en modules cohérents

`nicsoft/engine/engine_manager.py` (833 lignes, règle ARC-004) mélangeait
détection des binaires, disponibilité, classe générique de moteur UCI,
spécialisations Maia/Rodent et classification des coups. Découpé sans
changement de comportement en 7 modules du dossier `nicsoft/engine/` :

- `move_quality.py` (39 lignes) — `classifier_coup`, `score_to_cp`,
  seuils `SEUIL_BON`/`SEUIL_IMPRECISION`/`SEUIL_ERREUR` (logique pure).
- `engine_analysis.py` (277 lignes) — `EngineAnalysisMixin` : `evaluate`,
  `evaluate_move`, `get_punishment_line`, `get_multipv`, `analyser_partie`,
  `wdl_to_bar`. Extrait de la classe `EngineManager` d'origine (qui
  dépassait seule 380 lignes) en mixin hérité, pour que chaque module
  reste nettement sous 300 lignes sans toucher au comportement ni à la
  structure de classe (MaiaEngine/RodentEngine héritent toujours de
  `EngineManager`, qui hérite du mixin).
- `uci_engine.py` (150 lignes) — `EngineManager` (init, `_apply_elo`,
  `get_move`, `set_elo`, `quit`, propriétés) + constantes `ELO_MIN`/
  `ELO_MAX`/`ELO_DEFAUT`.
- `engine_detection.py` (132 lignes) — `find_stockfish`, `find_lc0`,
  `find_rodent`, `find_maia_weights`, `MAIA_LEVELS`, `_ensure_executable`.
- `engine_availability.py` (64 lignes) — `stockfish_available`,
  `maia_available`, `rodent_available` (ce dernier lance réellement
  Rodent pour le handshake UCI, comportement inchangé).
- `maia_engine.py` (114 lignes) — `MaiaEngine`.
- `rodent_engine.py` (132 lignes) — `RodentEngine` + constantes
  `RODENT_PERSONALITIES`/`RODENT_ELO_MIN`/`RODENT_ELO_MAX`/
  `RODENT_ELO_DEFAUT`/`RODENT_PERSONALITY_DEFAUT`.

`engine_manager.py` (63 lignes) devient un point d'entrée qui réexporte
tous ces objets — aucun import existant (serveur web, `analyse.py`, mode
labo, `test_rodent.py`, `test_analyse_engine_path.py`) n'a dû être modifié.

Logger applicatif inchangé : chaque nouveau module reprend
`logging.getLogger("EngineManager")`, exactement comme l'ancien fichier
unique (même nom partout, donc même objet Logger).

Aucun test n'a dû être adapté : `test_analyse_engine_path.py` monkeypatch
`nicsoft.engine.engine_manager.find_stockfish`, et `analyse.py` continue
de faire `from nicsoft.engine.engine_manager import find_stockfish` à
l'intérieur de la fonction au moment de l'appel — ce remplacement agit
donc toujours sur le nom réellement utilisé, puisque `engine_manager.py`
réexpose `find_stockfish` (défini maintenant dans `engine_detection.py`)
comme un attribut de son propre module. Vérifié en relançant les deux
tests concernés après le découpage.

Suite complète hors tests `hardware` : 278 passed, 61 skipped (inchangé
par rapport à avant le découpage).

# Changelog — Issue #275

## Découpage de llm_explainer.py en modules cohérents (ARC-004)

`nicsoft/modes/opening_explorer/llm_explainer.py` dépassait 360 lignes et
concentrait plusieurs responsabilités (appel réseau aux fournisseurs,
cache disque, construction des consignes, fonctions publiques). Découpé en
4 modules dans le même dossier, `llm_explainer.py` devenant un simple point
d'entrée qui réexporte les 3 fonctions publiques sans aucun changement de
comportement :

- `llm_provider.py` (61 lignes) — `call_claude`/`call_openai` : appel HTTP
  bas niveau aux fournisseurs. Ne journalise ni clé d'API ni URL complète
  (inchangé).
- `llm_cache.py` (35 lignes) — `load_cache`/`save_cache` : cache disque
  JSON des explications déjà générées.
- `llm_prompts.py` (183 lignes) — consignes système/utilisateur par langue
  (`SYSTEM_PROMPTS`, `ANALYSE_SYSTEM_PROMPTS`, `CHAT_SUFFIX`), construction
  des prompts (`build_user_prompt`, `build_chat_prompt`,
  `build_analyse_context_text`) et extraction des flèches (`extract_arrows`).
- `llm_functions.py` (128 lignes) — les 3 fonctions publiques
  `get_explanation`, `get_chat_response`, `get_analyse_response`, qui
  orchestrent cache + consignes + appel fournisseur.
- `llm_explainer.py` (17 lignes) — réexporte les 3 fonctions publiques
  depuis `llm_functions.py` ; `nicsoft/web/server.py` les importe toujours
  depuis ce même chemin, sans aucune modification nécessaire côté serveur.

Le motif de compteur d'annulation de requête mentionné par l'issue
(`tts_engine._tts_generation` côté Explorer, `_analyse_llm_request_id`
côté drawer Analyse) ne vit pas dans `llm_explainer.py` mais dans
`tts_engine.py`/`server.py` — fichiers non touchés par ce découpage, donc
le motif reste bien dans un seul module, inchangé.

- 2 nouveaux fichiers de tests, aucun accès réseau (fonctions pures /
  cache sur répertoire temporaire) :
  - `nicsoft/tests/test_llm_cache.py` — round-trip load/save, cache
    absent, JSON corrompu ignoré.
  - `nicsoft/tests/test_llm_prompts.py` — construction des prompts
    (ouverture, alternatives, fallback FEN invalide, contexte Analyse) et
    extraction des flèches (3 langues, cases invalides, limite à 4).
- Suite de tests complète (hors `hardware`) : 284 passed, 58 skipped.

# Changelog — Issue #274

## Exercices : numéros et nombres de coups selon la convention des échecs

Le serveur envoyait au navigateur le nombre brut de **demi-coups**
(`len(board.move_stack)` ou `len(init_moves)`) pour les champs `move_num`
(progression pendant la ligne), `move_count` (position de départ à
reproduire) et `moves` (fin de ligne théorique) — affiché tel quel avec les
libellés "Coup"/"Move"/"Zug" ou "coups"/"moves"/"Züge", alors qu'aux échecs
un coup compte une paire blanc+noir.

- Deux fonctions ajoutées dans `nicsoft/modes/exercices/exercices.py` :
  - `pgn_move_number(half_moves)` = `half_moves // 2 + 1` — numéro du coup
    PGN en cours (celui que les blancs commencent ou que les noirs doivent
    répondre). Ex. 24 ou 25 demi-coups → coup 13.
  - `pgn_moves_played(half_moves)` = `(half_moves + 1) // 2` — nombre de
    coups complets joués ; pour un nombre impair de demi-coups (dernier
    coup commencé mais pas encore répondu), compte ce coup comme joué
    (choix documenté ici, demandé par l'issue). Ex. 4 demi-coups → 2 coups ;
    5 demi-coups → 3 coups.
- Les 6 points d'envoi dans `exercices.py` utilisent maintenant ces
  fonctions (`move_count` ×3, `moves` ×2, `move_num` ×1) — aucun nouvel
  événement, les noms de champs sont inchangés.
- `exercice_end_of_line` faisait déjà un `Math.floor(data.moves / 2)` côté
  JS (arrondi vers le bas, incorrect pour un nombre impair) : supprimé
  puisque `data.moves` est désormais déjà le nombre de coups complets.
- Pluriel correct dans les 3 langues pour les deux libellés concernés
  (`fr/en/de.json`) : nouvelles clés `exercices.coup_joue`/`coups_joues`
  (position de départ) et `exercices.end_of_line_feedback_un` (fin de
  ligne, variante singulier de la clé existante). `exercices.reproduire_position`
  n'inclut plus le participe "joués"/"played"/"gespielt" en dur (il fait
  maintenant partie du libellé choisi selon le pluriel).
- `common.coup_num` ("Coup {n}") n'a pas besoin de variante plurielle (un
  numéro de coup ne se pluralise pas) — seule la valeur envoyée était
  fausse, pas le libellé.
- Test ajouté : `nicsoft/tests/test_exercices_pgn_move_count.py`, vérifie
  les deux fonctions sur 0, 1, 2, 4, 5, 24 et 25 demi-coups.
- Suite complète (`pytest nicsoft/tests/ -m "not hardware"`) : 257 passed,
  54 skipped (tests matériel), aucun échec.

### Autres endroits avec la même confusion demi-coup/coup, non corrigés (hors périmètre de cette issue)

- `nicsoft/web/alchess.py` (événement `retranscription_en_cours`, bannière
  de reprise de partie) envoie `len(moves)` (demi-coups) affiché via
  `common.n_coups` dans `app.js` (~ligne 5705) : une partie à 25 demi-coups
  affiche "25 coups" au lieu de 13.
- `nicsoft/modes/retranscription/retranscription.py:247` — le champ
  `move_num` de l'événement `retranscription_move` est lui aussi un compte
  de demi-coups brut, mais n'est actuellement lu par aucun code JS
  (`_retransRenderHistory`/`_retransUpdateTurn` ne s'en servent pas) : pas
  de bug visible aujourd'hui, mais le nom du champ est trompeur. À noter :
  l'affichage du tour en cours dans ce même mode (`_retransUpdateTurn`,
  `app.js:5697`) applique déjà la bonne formule PGN
  (`Math.floor(length / 2) + 1`), donc ce mode n'a pas le bug visible pour
  l'utilisateur.
- Outils Exercices (panneau d'administration du catalogue, pas le mode
  Exercices lui-même) : `outils.label.coups` (`app.js:6032`) et
  `outils.init_coups` (`app.js:6371`) affichent le nombre de demi-coups
  d'une séquence d'initialisation comme "N coups" ; de même le champ
  `depth` envoyé par `nicsoft/modes/exercices/explore_book.py` (ligne 410,
  affiché via `outils.polyglot.profondeur`, `app.js:6238`) est aussi un
  compte de demi-coups.
- `explore_book.py:format_move_line()` (affichage terminal, outil CLI) est
  en revanche déjà correct : il construit la notation `N.san` selon la
  vraie numérotation PGN.

# Changelog — Issue #273

## Exercices : ne plus voir l'erreur "livre introuvable" en revenant dans un exercice une fois le livre restauré

Suite de #271. Cause établie par analyse du code (confirmée par le test
manuel décrit dans l'issue, qui pointait déjà vers cette piste) :

- **Cause 1 (interface) — confirmée.** `exSetFeedback()` (`app.js`) affiche
  le bandeau de feedback avec `duration = 0` pour les messages "livre
  introuvable" et "fin de ligne" (vert) : ni l'un ni l'autre ne disparaît
  automatiquement — c'est voulu, l'utilisateur doit agir. Mais le handler
  `socket.on("exercice_init", ...)`, qui construit l'écran d'un nouvel
  exercice, ne vidait jamais ce bandeau (`#ex-feedback`) : un message laissé
  affiché par un exercice précédent (ex. l'erreur livre manquant) restait
  visible indéfiniment au-dessus du nouvel exercice, même une fois sa cause
  disparue.
  - En revanche, la ligne de statut (`#ex-run-status`) modifiée par
    l'erreur est déjà réinitialisée par `exercice_init` **avant** la
    branche `if (_virtualMode) { ... } else { ... }`
    (`app.js:4623-4624` avant ce fix, code antérieur à #270/#271) : cette réinitialisation
    s'applique donc déjà identiquement aux deux modes (virtuel et échiquier
    physique) — contrairement à l'hypothèse soulevée dans l'issue, aucune
    asymétrie n'a été trouvée sur ce point précis à la lecture du code
    actuel ; aucun changement n'y était donc nécessaire.
- **Cause 2 (serveur) — non confirmée.** `ExerciceSession.run()`, dans la
  branche "livre manquant", boucle sur `_wait_action_end()` jusqu'à
  recevoir une action différente de "RETRY", puis fait un `return` normal
  (`exercices.py:974-979`). Les deux actions de sortie côté IHM ("Retour au
  menu" et "← Choisir autre ouverture") envoient toutes deux le même type
  d'action `exercice_back` (`index.html:922-924`, `app.js:97-98`), traité
  de façon identique par `_wait_action_end()` (`exercices.py:1219-1221`) :
  `self._running = False`, puis retour. `game_manager._run_exercice()`
  attend donc bien la fin réelle de `session.run()` avant son bloc
  `finally`, qui remet `_exercice_running = False`
  (`game_manager.py:505-507`) — le lanceur repasse donc bien à "aucun
  exercice en cours" et un nouveau lancement (`start_exercice` /
  `_run_exercice`) crée normalement une nouvelle session. Aucune
  modification serveur n'a donc été nécessaire ; un test de garde-fou a
  été ajouté pour verrouiller ce comportement.

### Modifications

- `nicsoft/web/static/app.js` — `socket.on("exercice_init", ...)` : efface
  désormais le bandeau de feedback résiduel (`#ex-feedback`, masqué et
  texte vidé) dès la réception de l'événement d'initialisation d'un
  exercice, avant toute autre mise à jour d'écran. Les messages temporaires
  (durée > 0, ex. "✓ coup théorique") ne sont pas concernés : ce
  changement ne touche que l'état résiduel au moment où un nouvel exercice
  démarre.
- `nicsoft/tests/test_exercices_book_missing.py` — nouveau test
  `test_nouvelle_session_apres_restauration_du_livre` (sans interface ni
  matériel) : une première `ExerciceSession` avec livre manquant est créée,
  tourne dans un thread, reste en attente (pas de retour automatique), puis
  se termine proprement sur une action `exercice_back`. Une seconde
  `ExerciceSession` est alors créée avec un livre Polyglot minimal
  construit pour le test (une seule entrée `e2e4`) : elle ne signale aucune
  erreur (`exercice_sync_error` absent des événements), émet
  `exercice_wait_position` (démarrage normal), et ne se termine pas
  immédiatement (le thread reste vivant, en attente de la synchro
  initiale) — exactement le comportement attendu quand on revient dans un
  exercice une fois le livre restauré.
- Cas inchangés vérifiés : "pièces mal placées" (`exercice_sync_error` hors
  livre manquant) et cas normal (livre présent, fin de ligne théorique) —
  aucun des tests existants n'a été modifié dans son comportement, seuls
  ajouts.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 255 passed,
  54 skipped.

### Reproduction manuelle

1. Renommer temporairement le fichier du livre d'ouvertures attendu (ex.
   `data/books/gm2001.bin` → `gm2001.bin.bak`).
2. Ouvrir un exercice d'ouverture quelconque : le message « Livre
   d'ouvertures introuvable : <chemin> » s'affiche, reste affiché (pas de
   retour automatique).
3. Quitter (← Retour au menu ou ← Choisir autre ouverture).
4. Remettre le fichier du livre à sa place (annuler le renommage de
   l'étape 1).
5. Rouvrir un exercice d'ouverture (le même ou un autre) : avant ce fix, le
   bandeau d'erreur « Livre d'ouvertures introuvable » restait affiché par-
   dessus le nouvel exercice bien que le livre existe de nouveau — il
   fallait cliquer sur « Synchroniser » pour le faire disparaître. Après ce
   fix, l'exercice démarre normalement, sans bandeau ni statut d'erreur
   résiduels, aussi bien avec un échiquier physique qu'en mode virtuel.

# Changelog — Issue #272

## Tests de garde ARC-001 : découverte automatique des fichiers au lieu de listes écrites à la main

Les trois tests qui verrouillent ARC-001 (le moteur n'importe jamais
`nicsoft.web`) listaient à la main huit ou neuf fichiers. Deux défauts :
`engine`, `utils` et `niclink/driver` n'y figuraient pas (un import web y
serait passé inaperçu), et un nouveau fichier créé lors d'un découpage
n'était couvert par aucun test, sans qu'aucune alerte ne le signale.

- `nicsoft/tests/_arc001_discovery.py` (nouveau) : découverte commune —
  parcourt `nicsoft/{core,modes,niclink,utils,engine}` et retourne tous les
  `.py` (hors `__pycache__`), avec un garde-fou (`verifier_decouverte_non_cassee`)
  qui échoue si la liste est vide ou si `game_manager.py` /
  `virtual_board.py` manquent.
- `nicsoft/tests/test_no_web_import.py`, `test_ihm_port_contract.py`,
  `test_no_undefined_names.py` : remplacent leur liste écrite à la main par
  cette découverte automatique, chacun avec un test dédié qui vérifie que la
  découverte n'est pas cassée.
- Modules qui ne s'importent pas seuls pour des raisons sans rapport avec
  ARC-001 (bugs préexistants dans du code mort, mis en lumière par la
  découverte élargie) : exclus explicitement avec une raison écrite, jamais
  en silence — et un test dédié (`test_modules_non_importables_restent_documentes`,
  `test_fichiers_exclus_restent_documentes`) échoue si le bug sous-jacent est
  corrigé sans retirer l'exclusion, pour qu'elle ne devienne pas obsolète :
  - `nicsoft.utils.light_board` : `List` et `np` non importés (NameError).
  - `nicsoft.utils.turn_out_all_lights` : `from niclink import NicLinkManager`
    cassé (devrait être `nicsoft.niclink`).
  - `nicsoft.modes.{exercices,labo,retranscription}.__main__` : importent
    `main` depuis leur module, qui ne le définit plus depuis le découplage
    #263/#264 (entry-points CLI morts, l'app web ne les utilise plus).
  - Ces cinq cas sont des bugs préexistants dans du code mort (jamais appelé
    ailleurs dans le projet), sans lien avec ARC-001 et sans risque pour le
    comportement actuel de l'application — non corrigés ici par prudence
    (la correction de `light_board.py` notamment nécessiterait de deviner un
    comportement voulu, au-delà d'un ajout d'import trivial).
- Temps ajouté à la suite ARC-001 : environ 3 s (passée de ~2,1 s à ~5,1 s
  sur cette machine) — reste de l'ordre de quelques secondes, le pre-push
  hook lance cette suite avant chaque push.
- Vérifié concrètement : un fichier fautif temporaire (`import nicsoft.web`
  + nom non défini) ajouté dans chacun des cinq dossiers (`core`, `modes`,
  `niclink`, `utils`, `engine`) fait échouer `test_no_web_import.py` et
  `test_no_undefined_names.py` automatiquement, sans modification des
  fichiers de test ; fichiers retirés sans être committés.
- Suite complète hors tests `hardware` : 252 passed, 54 skipped.
- `.audit.json` non modifié.

# Changelog — Issue #271

## Exercices : l'erreur "livre introuvable" reste affichée jusqu'à une action de l'utilisateur

Suite de #270. Le message d'erreur (livre Polyglot introuvable) était bien
émis mais `ExerciceSession.run()` terminait aussitôt après (`return`
immédiat) : le lanceur d'exercice (`game_manager._run_exercice`) voyait
alors la session se terminer et exécutait son nettoyage normal de fin
d'exercice, qui renvoie aussitôt la liste des ouvertures — l'écran d'erreur
disparaissait donc en moins d'une seconde, le rendant inutilisable en
pratique.

- `nicsoft/modes/exercices/exercices.py` (`ExerciceSession.run()`) : le cas
  « livre manquant » affiche désormais la position de départ de l'exercice
  demandé (`self._send_position()` — plus l'échiquier de l'exercice
  précédent) puis attend une action utilisateur via `_wait_action_end()`,
  exactement comme à la fin normale d'une ligne (mêmes actions possibles :
  retour au menu, choisir une autre ouverture, recommencer). Sur
  « recommencer », l'erreur est simplement réaffichée (le livre est
  toujours manquant) sans relancer `_restart()` ni repasser par la boucle
  de jeu normale — pas de boucle infinie (bloqué sur l'action utilisateur)
  ni de nouveau log (le log d'absence du livre reste unique, à la
  construction de la session). Seule la méthode `run()` a été modifiée ;
  le nettoyage de fin de session dans `game_manager._run_exercice` est
  inchangé, et le mécanisme d'attente/actions (`_wait_action_end`) est
  celui déjà utilisé pour la fin de ligne théorique normale.
- Cas inchangés vérifiés : livre présent et cas « pièces mal placées »
  (`exercice_sync_error` hors livre manquant).
- `nicsoft/tests/test_exercices_book_missing.py` : test existant mis à jour
  (fournit désormais une action de retour pour débloquer `run()`) et deux
  nouveaux tests — la session reste en attente tant qu'aucune action n'est
  reçue puis se termine proprement sur un retour, sans jamais émettre
  `exercice_end_of_line` ; et "recommencer" avec le livre toujours
  manquant réaffiche l'erreur (au moins 2 occurrences) sans log
  supplémentaire ni `exercice_end_of_line`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 125 passed,
  10 skipped.

### Reproduction manuelle

1. Renommer temporairement le fichier du livre d'ouvertures attendu (ex.
   `data/books/gm2001.bin` → `gm2001.bin.bak`), ou renommer le dossier
   `data/books/` lui-même.
2. Lancer un exercice d'ouverture quelconque depuis l'interface.
3. Observer : le message « Livre d'ouvertures introuvable : <chemin> »
   reste affiché tant qu'aucune action n'est prise — pas de retour
   automatique à la liste, l'échiquier affiché est celui de la position de
   départ de l'exercice choisi (pas celui d'un exercice précédent).
4. Cliquer « ↺ Recommencer l'exercice » : l'erreur est réaffichée à
   l'identique (toujours pas de retour à la liste).
5. Cliquer « ← Choisir autre ouverture » ou « ← Retour au menu » : retour
   normal à la liste des ouvertures / au menu.
6. Restaurer le fichier/dossier renommé à l'étape 1.

# Changelog — Issue #270

## Exercices : message clair quand le livre d'ouvertures est introuvable

Avant le fix, si le fichier du livre Polyglot était introuvable (ex. dossier
`data/` absent), `ExerciceSession._get_book_moves` avalait l'exception et
retournait une liste vide — indistinguable d'une vraie fin de ligne
théorique. L'IHM annonçait donc « Ligne terminée ! Bravo » alors que
l'exercice n'avait jamais pu se dérouler, et le serveur loggait l'erreur
« Livre : fichier ou dossier inexistant » à chaque coup.

- `nicsoft/modes/exercices/exercices.py` : l'existence du fichier du livre
  (`self._book_path`) est vérifiée une seule fois, à la construction de
  `ExerciceSession` (`self._book_missing`), et loggée une seule fois par
  exercice (`logger.error`, pas à chaque coup). `run()` détecte ce cas en
  tout premier lieu et émet `exercice_sync_error` (événement d'erreur IHM
  déjà utilisé par l'exercice pour la synchro de plateau) au lieu de
  dérouler la boucle de jeu — plus de faux `exercice_end_of_line`.
  `_get_book_moves` ne retente plus l'ouverture du fichier une fois le livre
  connu manquant, et ne logge plus qu'une fois les erreurs imprévues
  (livre corrompu, etc.) via `self._book_error_logged`.
- `nicsoft/web/static/app.js` : le handler `exercice_sync_error` accepte
  désormais deux champs optionnels — `status_key` (texte de statut
  personnalisé) et `show_sync_btn` (désactive le bouton Synchroniser quand
  resynchroniser ne résoudra rien) — sans changer le comportement par
  défaut (cas existant : pièces mal placées).
- `nicsoft/web/static/i18n/{fr,en,de}.json` : nouvelles clés
  `exercices.book_missing_status` et `exercices.book_missing_msg`
  (interpolée avec le chemin attendu du livre).
- Cas inchangés vérifiés : livre présent (coup du livre toujours trouvé) et
  vraie fin de ligne théorique (livre présent mais sans entrée pour la
  position) toujours traitée comme une fin de ligne normale.
- Nouveau test `nicsoft/tests/test_exercices_book_missing.py` (sans
  interface ni matériel) : livre absent → `exercice_sync_error` émis,
  `exercice_end_of_line` jamais émis, un seul log d'erreur ; livre présent
  → comportement inchangé ; livre présent mais vide pour la position →
  fin de ligne normale toujours distincte d'un livre manquant.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 122 passed,
  10 skipped.

# CHANGELOG-269 (issue #269)

## Échiquier virtuel : ajout de la méthode disconnect (plus de faux avertissement à la sortie des modes)

- `nicsoft/niclink/virtual_board.py` : ajout de `VirtualBoard.disconnect()`, no-op comme ses méthodes voisines (`turn_off_all_leds`, `beep`, etc.) — rien à fermer côté USB en mode virtuel.
- Cause : `nicsoft/core/game_manager.py` appelle `nl_inst.disconnect()` en sortie d'explorateur d'ouvertures, d'exercices et de drill (3 endroits, non modifiés — l'appel côté appelant était correct). Avec un échiquier virtuel, cette méthode n'existait pas : `AttributeError` avalée par un `except` qui journalisait un faux avertissement « Déconnexion échiquier échouée ... object has no attribute disconnect » à chaque sortie de ces modes en mode virtuel.
- Vérification des autres méthodes de `NicLinkManager` appelées par `game_manager.py` ou les modes sur l'objet échiquier (`get_fen`, `turn_off_all_leds`, `signal_lights`, `connect`, `start`...) : toutes déjà présentes dans `VirtualBoard` ou appelées uniquement après vérification que l'instance est physique (`connect()` dans `server.py`, gardé par `hasattr(nl_inst, "nl_interface")`). Aucune autre méthode manquante.
- `nicsoft/tests/test_virtual_board.py` (nouveau) : crée un `VirtualBoard` et appelle `disconnect()` sans erreur.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 120 passed, 10 skipped.

# CHANGELOG-267 (issue #267)

## Tests e2e : serveur lancé depuis le code testé, échiquier réel ignoré

- `nicsoft/tests/e2e/conftest.py` : le dossier de lancement du serveur de test (donc le code importé par `python -m nicsoft.web`) n'est plus le dépôt principal codé en dur (`~/NicLink`), mais déduit de l'emplacement de `conftest.py` (racine du dépôt ou du worktree où tourne pytest). Les tests valident donc le code sur lequel ils sont exécutés. Le Python reste celui du venv utilisateur (`~/NicLink/venv/bin/python`).
- `nicsoft/web/alchess.py` : nouvelle variable d'environnement `ALCHESS_SKIP_BOARD=1` qui désactive `_check_board_at_startup` (détection/connexion de l'échiquier USB réel au démarrage) et évite de lancer `_board_menu_watcher` ; absente, le comportement est inchangé. Positionnée uniquement dans l'environnement du serveur lancé par `conftest.py`.
- `data/` n'étant pas versionné, un worktree n'a pas les fichiers de référence réels (ECO `eco_*.tsv`, `eco_hierarchy.json`, livres d'ouvertures…) dont dépendent 3 tests de recherche ECO (`test_outils_exercices_e2e.py`). L'isolation complète via un dossier `ALCHESS_DIR` temporaire (point optionnel de l'issue) a été tentée puis abandonnée pour cette raison ; `ALCHESS_DIR` est positionnée vers le vrai dossier de données de l'utilisateur (`~/NicLink`) pour ces tests — seul le code vient du worktree, pas les données. Documenté dans `TESTS.md`.
- Suite complète hors `hardware` (`pytest -m "not hardware"`) : 119 passed, 10 skipped, lancée depuis le worktree, sans navigateur visible ni sollicitation de l'échiquier USB.

# CHANGELOG-266 (issue #266)

## Retrait de l'outil de sauvegarde backup_manager

- Suppression de `nicsoft/utils/backup_manager.py` et de `nicsoft/utils/Lancer et autre outil Backup.txt`.
- Retrait de toutes les références (commandes, consignes de backup épinglé) dans `CLAUDE.md`, `CONTEXTE.md`, `SPECIFICATIONS.md`, `TESTS.md`, `ETAT_PROJET.md` et `INSTALLATION/CONFIGURATION_SYSTEME.md`.
- Là où la consigne de backup épinglé disparaît, remplacement par un rappel explicite : la protection du travail repose sur git (commits ciblés, retour arrière par git, push fait par Alain après revue).
- `CONTEXTE.md` : suppression de l'affirmation périmée selon laquelle CCL travaille exclusivement dans `~/NicLink` (devenu faux depuis le passage aux worktrees isolés par issue).
- Aucun code Python n'importait cet outil ; suite de tests (`pytest -m "not hardware"`) : 96 passed, 4 skipped.

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

# Changelog — Issue #264

## Suite #263 : correction des régressions du découplage (Humain contre Humain + abandon Pédagogique)

Le test manuel avec échiquier physique a révélé deux régressions introduites
par le découplage nicsoft.web de la #263, non détectées par
`test_no_web_import.py` (qui ne vérifie que l'absence d'import de
`nicsoft.web`, pas que chaque appel migré trouve bien sa cible).

### Régression 1 — mode Humain contre Humain

`nicsoft/core/game_manager.py:320` appelait `web_server.set_history(...)` où
`web_server` est l'alias local de `ihm_port.app_state_proxy`
(`_AppStateProxy`). Cet objet n'expose que `_app_state` et `action_queue`
(façade volontairement limitée à l'ancien accès direct `web_server._app_state`
/ `.action_queue`) — pas `set_history`, qui est une fonction de module de
`ihm_port.py`, pas une méthode du proxy. Résultat : `AttributeError`
immédiatement après la création du plateau virtuel/physique → retour menu,
déconnexion/reconnexion visible côté échiquier.

**Fix** : `game_manager.py` importe désormais `set_history` directement
depuis `nicsoft.core.ihm_port` (même motif que `human.py`, qui l'importait
déjà correctement) et l'appelle sans passer par le proxy.

### Régression 2 — abandon en mode Pédagogique

`nicsoft/modes/pedagogique/pedagogique.py:376` (`Game._end_game`) lisait
`_game_state.get("init", {})`. `_game_state` était un dict interne de
`nicsoft.web.server`, importé localement avant la #263
(`from nicsoft.web.server import set_app_state, _game_state`). L'étape 6/8 de
la #263 a retiré cet import (remplacé par `get_history()` pour la lecture de
l'historique) mais a laissé cette seconde référence orpheline → `NameError:
name '_game_state' is not defined` au clic sur « Abandonner », juste avant
l'envoi de l'état `game_over` → retour menu avec popup d'erreur.

**Fix** : ajout d'un accesseur dédié `get_init_data()` — dans
`nicsoft/web/server.py` (lecture verrouillée de `_game_state["init"]`, miroir
de `get_history()`), exposé par `_WebBackend` (`nicsoft/web/alchess.py`) et
`_NullBackend`/module `nicsoft/core/ihm_port.py`. `pedagogique.py` l'importe
et l'appelle au lieu de lire `_game_state` directement.

### Recensement systématique (point 3 de la demande)

Vérification exhaustive, par analyse statique, de tous les fichiers migrés
par la #263 (`game_manager`, `human`, `pedagogique`, `exercices`, `labo`,
`virtual_board`, `board_adapter`, `retranscription`) :

- **Appels sur l'objet d'interface (`ihm_port`/`app_state_proxy`)** : les deux
  régressions ci-dessus sont les **deux seuls** cas trouvés où un appel migré
  ne correspond à aucun élément réellement fourni par le port ou par le
  proxy. Tous les autres imports depuis `ihm_port` et tous les autres appels
  sur l'alias de `app_state_proxy` (`web_server`/`_web_server`) correspondent
  à un élément réel.
- **Noms non définis (reste de l'ancien `nicsoft.web`)** : `_game_state`
  (régression 2) est le **seul** nom non lié trouvé sur l'ensemble des
  fichiers migrés (vérifié avec `pyflakes` et avec le test
  `test_no_undefined_names.py` ci-dessous).

### Tests ajoutés (point 4)

- `nicsoft/tests/test_ihm_port_contract.py` — analyse statique (ast) : chaque
  nom importé depuis `nicsoft.core.ihm_port` dans les fichiers migrés existe
  réellement dans ce module ; chaque attribut accédé sur l'alias local de
  `app_state_proxy` existe réellement sur `_AppStateProxy` ; `_NullBackend` et
  `_WebBackend` exposent chacun toutes les méthodes utilisées par les
  fonctions de module de `ihm_port.py`.
- `nicsoft/tests/test_no_undefined_names.py` — équivalent restreint de
  pyflakes ("undefined name"), implémenté avec le seul module standard `ast`
  (pas de nouvelle dépendance de test) : pour chaque fichier migré, vérifie
  qu'aucun nom lu n'est totalement non lié dans le fichier.
- `nicsoft/tests/test_humain_startup_virtuel.py` (bonus) — exécute
  `game_manager._run_humain(virtual=True)` avec un plateau virtuel et un
  double léger de `GameWeb`, jusqu'après l'enregistrement de l'historique
  initial via le port — sans matériel ni serveur Flask-SocketIO.

Les trois nouveaux tests ont été vérifiés manuellement contre l'état d'avant
correction (`git stash`) : ils échouent bien sur les deux régressions
(`AttributeError` et `NameError`) et passent après le fix.

### Comportement

Strictement identique à avant la #263 — aucun changement de motif de thread
SocketIO, aucune nouvelle dépendance.

### Vérifications manuelles à refaire avec l'échiquier physique

- Mode Humain contre Humain : lancer une partie, vérifier que l'échiquier
  s'affiche et reste connecté (pas de retour menu / déconnexion-reconnexion).
- Mode Pédagogique : lancer une partie, cliquer sur « Abandonner », vérifier
  qu'aucune popup d'erreur n'apparaît et que l'écran de fin de partie
  (historique, titre) s'affiche normalement avant le retour menu.

# Changelog — Issue #263

## Découplage de la logique de jeu : plus d'import de nicsoft.web depuis core/modes/niclink/utils/engine (règle ARC-001)

Recensement complet refait avant correction (l'audit initial, limité à
`nicsoft/modes`, comptait 32 sites) : **34 sites réels** répartis sur 7
fichiers — `nicsoft/core/game_manager.py` (11), `nicsoft/modes/humain/human.py` (7),
`nicsoft/modes/pedagogique/pedagogique.py` (7), `nicsoft/modes/exercices/exercices.py` (5),
`nicsoft/niclink/virtual_board.py` (3), `nicsoft/modes/labo/labo.py` (1),
`nicsoft/core/board_adapter.py` (1). (`nicsoft/utils/debug.py` et
`nicsoft/utils/timing.py` ne mentionnaient `nicsoft.web` que dans un
commentaire/docstring — aucun import réel.) `nicsoft/modes/retranscription/retranscription.py`
était déjà découplé : il reçoit `web_server` en paramètre (injection de
dépendance) plutôt que de l'importer — c'est le motif qui a inspiré la
solution retenue pour les autres fichiers.

**Solution retenue** : un port neutre, **`nicsoft/core/ihm_port.py`**, expose
aux modules de jeu les primitives dont ils ont besoin (`send_event`,
`get_action`, `set_app_state`, `set_virtual_board`, `get_history`/`set_history`,
`get_action_queue`, `get_app_state`/`set_raw_app_state`, `check_board_at_startup`,
`emit`). Tant qu'aucun backend n'est branché (import isolé, tests), un
backend neutre (`_NullBackend`) répond sans effet de bord — permet d'importer
n'importe quel module de jeu sans lancer le serveur web. Au démarrage réel,
`nicsoft/web/alchess.py` branche l'implémentation Flask-SocketIO via
`ihm_port.register_backend()`.

Les très nombreux sites qui accédaient directement au module
`nicsoft.web.server` (`web_server._app_state = ...`, `web_server.action_queue...`)
— notamment dans `game_manager.py` et `human.py`, pour la course critique
SocketIO qui écrit `_app_state` silencieusement avant d'appeler `set_app_state()`
(pour éviter une fenêtre de race pendant la notification navigateur) — n'ont
*pas* été réécrits un par un : `ihm_port.app_state_proxy` reproduit exactement
le même objet dupliqué (property `_app_state` + `action_queue`), ce qui a
permis de ne changer que la ligne d'import sur ces sites et de garder le reste
du code strictement identique. Seul `game_manager.py:304` (import différé de
`nicsoft.web.alchess._check_board_at_startup`, seul cas de cycle réel —
`alchess.py` importe `game_manager` au niveau module) devient
`ihm_port.check_board_at_startup()`.

Migration faite mode par mode, un commit par étape (points de retour arrière) :
port neutre → `niclink/virtual_board.py` → `core/board_adapter.py` →
`modes/labo/labo.py` → `modes/exercices/exercices.py` →
`modes/pedagogique/pedagogique.py` → `modes/humain/human.py` →
`core/game_manager.py` → test d'isolation.

Ajout de `server.emit()` (émission SocketIO directe, hors `event_queue`) pour
couvrir un site (`pedagogique.py`) qui faisait `socketio.emit()` directement
pour un popup ponctuel, sans passer par `send_event()`.

Un site a changé de forme sans changer de résultat : `pedagogique.py` lisait
`_game_state["history"]` directement (sans le verrou), remplacé par
`get_history()[0]`, l'accesseur déjà prévu par `server.py` pour cet usage
précis d'après sa propre docstring ("à utiliser par tout module hors
server.py").

**Résultat** : plus aucun import de `nicsoft.web` depuis `core`, `modes`,
`niclink`, `utils`, `engine` (vérifié par recherche dans le code — seules des
mentions en commentaire/docstring subsistent dans `ihm_port.py`, `debug.py`,
`timing.py`). Comportement strictement identique : mêmes événements, mêmes
files d'actions, mêmes fils d'exécution.

**Fichiers modifiés :**

`nicsoft/core/ihm_port.py` (nouveau), `nicsoft/web/server.py`,
`nicsoft/web/alchess.py`, `nicsoft/niclink/virtual_board.py`,
`nicsoft/core/board_adapter.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/core/game_manager.py`,
`nicsoft/tests/test_no_web_import.py` (nouveau).

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
54 passed, 3 skipped (hardware), dont le nouveau
`test_no_web_import.py` (14 cas, chacun dans un sous-processus Python
propre pour ne pas être pollué par d'autres tests qui importent
`nicsoft.web.server` pour leurs propres besoins). Smoke-test manuel du
serveur réel (`start_server()` + requête HTTP sur `/`) : backend branché,
`_app_state` piloté via le port identique à l'ancien accès direct au
module. Suite e2e non lancée (nécessite Playwright + serveur lancé depuis
`~/NicLink`, hors périmètre du worktree).

**À vérifier manuellement par Alain, avec l'échiquier physique branché**
(aucun hardware disponible dans l'environnement de l'agent) :
- Mode Pédagogique (Stockfish/Maia/Rodent) : coup joué, feedback LED,
  pause sur erreur/blunder, reprise, abandon, fin de partie (mat/nulle),
  notification popup mat/pat.
- Mode Humain vs Humain : coups, undo, abandon, nulle par accord mutuel,
  retour menu depuis un état actif (vérification silencieuse du plateau
  au retour menu).
- Mode Exercices : synchronisation initiale, détection hors-théorie,
  retry/continue, retour menu.
- Mode Labo : suivi du plateau physique, meilleur coup, mode auto,
  analyse, copie de position.
- Déconnexion USB en cours de partie (callback `_board_lost_cb` →
  `board_error`) : le message doit toujours apparaître côté navigateur.
- Démarrage de l'appli complète (`python -m nicsoft.web`) suivi d'un tour
  dans chaque mode, pour confirmer qu'aucune régression de câblage n'est
  passée inaperçue dans l'environnement sans hardware de l'agent.

# Changelog — Issue #262

## Analyse de partie : ignorer le chemin du moteur sauvegardé s'il n'existe pas sur cette machine

`analyser_partie()` (`nicsoft/engine/analyse.py`) lisait le chemin du moteur
enregistré dans `data/config.json` et le transmettait tel quel à
`EngineManager`, sans vérifier qu'il existait sur la machine courante. Une
configuration copiée depuis une autre machine, ou un moteur désinstallé/déplacé,
faisait planter l'analyse au lieu de retomber sur la recherche automatique de
Stockfish (`find_stockfish()`) — repli qui n'était utilisé que lorsque le
chemin était vide.

La logique de validation (`chemin sauvegardé conservé seulement s'il existe`)
existait déjà dans `nicsoft/core/game_manager.py` sous le nom
`_validated_engine_path()`, utilisée par les autres modes de jeu. Pour éviter
une troisième copie tout en respectant le sens des dépendances (`engine` ne
doit pas dépendre de `game_manager`, qui dépend de la couche web), cette aide
est déplacée vers **`nicsoft/core/config_manager.py`** (module neutre, déjà
point d'accès centralisé à `config.json` depuis #259), renommée
`validated_engine_path()` (devenue un helper public partagé plutôt qu'un
détail interne de `game_manager`). `game_manager.py` pointe maintenant vers
cette version déplacée, sans changement de comportement.

`analyser_partie()` réutilise aussi `read_json_with_defaults()` (lecture de
config partagée introduite par #259) à la place de sa propre lecture JSON
manuelle, avec le même message de log en cas d'échec.

**Fichiers modifiés :**
- `nicsoft/core/config_manager.py` — ajout de `validated_engine_path()`.
- `nicsoft/core/game_manager.py` — utilise `validated_engine_path()` importé de `config_manager` (suppression de la copie locale `_validated_engine_path`).
- `nicsoft/engine/analyse.py` — `analyser_partie()` valide le chemin moteur sauvegardé et réutilise `read_json_with_defaults()`.
- `nicsoft/tests/test_analyse_engine_path.py` (nouveau) — 3 tests avec `EngineManager` simulé (aucun vrai moteur lancé) : chemin inexistant → repli `find_stockfish()`, chemin existant → conservé, chemin vide → comportement inchangé.

Suite de tests complète (hors `hardware`) : 82 passed, 4 skipped.

# Changelog — Issue #261

## Erreurs silencieuses : trace ou justification de chaque except sans traitement (règle PRO-012)

L'audit relevait 52 captures d'erreur silencieuses (exemples : `platform_utils.py`,
`labo.py`, `retranscription.py`, sept occurrences dans `game_manager.py`). Un
recensement complet refait avant correction (les numéros de ligne de l'audit
avaient bougé) a trouvé **133 occurrences réelles** réparties sur 29 fichiers —
l'audit initial était partiel.

Pour chaque occurrence, choix au cas par cas, sans jamais modifier le flux de
contrôle (aucun nouveau `raise`, aucune valeur de retour changée) :

- si l'erreur peut révéler une vraie panne → journalisée avec le logger du
  module (`logger.warning`/`logger.error` pour les cas significatifs,
  `logger.debug` dans les boucles d'interrogation rapides du plateau physique
  ou pour les fallbacks fréquents/attendus, afin de ne pas inonder les logs) ;
- si le repli silencieux est voulu (valeur par défaut, fichier optionnel
  absent, nettoyage best-effort en fin de programme/thread, idiome de vidage
  de `queue.Empty`, saisie interactive interrompue, exception de contrôle de
  flux comme `BackMenuExit`/`ExitNicLink`) → conservé, avec un commentaire
  explicatif ajouté dans le corps du `except`.

**Résultat : 72 cas journalisés, 61 cas justifiés par commentaire.**

Cas le plus significatif : `nicsoft/niclink/driver.py`, `_fen_reader_loop()`
— tout le thread de lecture USB était silencieux ; passé en `logger.debug`
(boucle à 50ms, erreurs transitoires fréquentes, mais désormais visibles en
mode `NICLINK_LOG=DEBUG`). Autre cas notable : `nicsoft/core/config_manager.py`
— `load_config()` ignorait un `config.json` corrompu sans aucune trace nulle
part ; utilise maintenant le paramètre `on_error` déjà prévu par
`read_json_with_defaults()` pour journaliser, sans changer la valeur retournée
(les défauts restent utilisés comme avant).

**Fichiers modifiés (29) :**

`nicsoft/platform_utils.py`, `nicsoft/core/config_manager.py`,
`nicsoft/core/game_manager.py`, `nicsoft/engine/analyse.py`,
`nicsoft/engine/board_utils.py`, `nicsoft/engine/display.py`,
`nicsoft/engine/engine_manager.py`, `nicsoft/engine/pgn_manager.py`,
`nicsoft/modes/exercices/_catalogue.py`,
`nicsoft/modes/exercices/add_ouverture.py`,
`nicsoft/modes/exercices/eco_import.py`,
`nicsoft/modes/exercices/exercices.py`,
`nicsoft/modes/exercices/explore_book.py`,
`nicsoft/modes/exercices/import_lignes.py`,
`nicsoft/modes/humain/human.py`, `nicsoft/modes/labo/labo.py`,
`nicsoft/modes/opening_explorer/explorer_session.py`,
`nicsoft/modes/opening_explorer/llm_explainer.py`,
`nicsoft/modes/opening_explorer/sources.py`,
`nicsoft/modes/opening_explorer/tts_engine.py`,
`nicsoft/modes/pedagogique/pedagogique.py`,
`nicsoft/modes/retranscription/retranscription.py`,
`nicsoft/niclink/driver.py`, `nicsoft/niclink/hid_backend.py`,
`nicsoft/niclink/virtual_board.py`, `nicsoft/tests/e2e/conftest.py`,
`nicsoft/web/alchess.py`, `nicsoft/web/launcher.py`, `nicsoft/web/server.py`.

**Tests :** `python -m pytest nicsoft/tests/ --ignore=nicsoft/tests/e2e` →
37 passed, 3 skipped (hardware). Suite e2e non lancée (nécessite Playwright
+ un serveur lancé depuis `~/NicLink`, hors périmètre du worktree).

# Changelog — Issue #260

## Rodent IV Linux : fin du faux dépôt imbriqué, documentation corrigée

`engines/rodent-iv` était enregistré dans l'index git comme un lien vers un
dépôt imbriqué (clone de `nescitus/rodent-iv`) sans jamais être déclaré comme
sous-module (`.gitmodules` ne le mentionnait pas). Conséquences : dossier vide
après un clonage frais, binaire local signalé en permanence comme
« modifié » sur la machine de dev, et documentation affirmant à tort que le
binaire Linux était inclus dans le dépôt (vrai seulement pour `lc0`).

**Changé :**

- `.gitignore` — ajout de `engines/rodent-iv/` : le dossier (dépôt git
  imbriqué + binaire compilé localement) n'est plus jamais suivi ni signalé
  comme modifié.
- Index git — `git rm --cached engines/rodent-iv` : retire l'entrée de
  dépôt imbriqué de l'index, sans toucher aux fichiers sur disque.
- `INSTALLATION/INSTALLATION_NICLINK.md` — ne prétend plus que le binaire
  Linux de Rodent IV est inclus dans le dépôt ; ajoute les instructions pour
  l'obtenir (clone + compilation de `https://github.com/nescitus/rodent-iv`,
  binaire à placer en `engines/rodent-iv/rodentIV` et à rendre exécutable) et
  corrige l'URL du dépôt source (était `nescior/Rodent_IV`, inexistant/non
  utilisé).
- `install.sh` — message clair quand `engines/rodent-iv/rodentIV` est
  absent (cas normal après un `git clone`), avec pointeur vers la section
  de compilation de la doc. Pas de téléchargement/compilation automatique.
- `make_release.sh` — commentaires corrigés : ne parlent plus de
  « sous-module » (qui n'a jamais existé pour ce chemin) mais de « dépôt git
  imbriqué, jamais déclaré en sous-module ». Comportement du script
  inchangé.

**Vérifié :**

- `find_rodent()` (`nicsoft/engine/engine_manager.py`) ne dépend que de
  l'existence du fichier `engines/rodent-iv/rodentIV` — inchangé par ce
  correctif, qui ne touche à aucun fichier Python.
- `make_release.sh` continue de supposer (comme avant) que le dépôt imbriqué
  réel, avec le binaire compilé, est présent sur la machine de build —
  c'est toujours la machine de dev d'Alain qui alimente le ZIP de release.

**À faire manuellement par Alain (voir commentaire de clôture de l'issue) :**
sauvegarde du binaire compilé avant la fusion sur la machine réelle, puis
vérification qu'il est toujours présent après.

# Changelog — Issue #259

## Factorisation du code dupliqué entre les fichiers du moteur (règle PRO-014)

L'audit signalait ~27 lignes identiques réparties sur plusieurs fichiers
(hypothèse initiale : `board_adapter.py`, `config_manager.py`,
`game_manager.py`, `analyse.py`, `board_utils.py`). Après vérification,
les blocs réellement dupliqués ne sont pas exactement ceux listés par
l'audit mais relèvent bien de la même cause : la lecture de
`data/config.json`, dupliquée localement — point que `config_manager.py`
documentait déjà lui-même comme "hors scope pour l'instant".

**Fusionné :**

- `nicsoft/core/config_manager.py` — nouvelle fonction
  `read_json_with_defaults(path, defaults, on_error=None)`, qui isole la
  logique « lit un JSON, fusionne sur des defaults, retombe sur les
  defaults si absent/invalide ». `load_config()` du module l'utilise
  désormais.
- `nicsoft/modes/pedagogique/pedagogique.py` et
  `nicsoft/modes/humain/human.py` — leurs `load_config()` locaux (mêmes
  defaults et même niveau de log qu'avant) délèguent maintenant la lecture
  JSON à `read_json_with_defaults()` au lieu de la dupliquer. Import
  `json` devenu inutile, retiré.
- `nicsoft/core/game_manager.py` — `launch_pedagogique()` et
  `launch_labo_libre()` contenaient le même bloc de 11 lignes (lecture de
  `engine_elo`/`engine_path` depuis `config.json`, byte pour byte
  identique, y compris le message de log). Extrait en
  `_read_engine_elo_and_path()`.

**Non fusionné (écarts de comportement réels, signalés sans forcer) :**

- Trois autres blocs de `game_manager.py` (exercice libre, drill, labo)
  lisent aussi `engine_elo`/`engine_path` depuis `config.json`, mais
  diffèrent sur des points fonctionnels : portée du `try/except` (un
  échec JSON désactive entièrement le moteur dans un cas, retombe sur des
  defaults dans un autre), ordre du repli `find_stockfish()`, et pour le
  mode labo l'`engine_elo` provient en réalité d'un dict de configuration
  runtime (pas du fichier). Les fusionner sans vérification individuelle
  aurait changé ces comportements.
- `nicsoft/engine/analyse.py` lit aussi `engine_path` depuis
  `config.json`, mais sans passer par la validation d'existence du
  chemin sur la plateforme courante (`_validated_engine_path`) — une
  différence de comportement pré-existante, potentiellement un écart à
  signaler séparément, pas touchée ici.
- `nicsoft/modes/humain/human.py` (fonction CLI historique, hors flux
  web) instancie `NicLinkManager` directement plutôt que via
  `nicsoft.core.board_adapter.create_board()` : ce chemin CLI n'a pas le
  callback `_board_lost_cb` (qui dépend de `nicsoft.web.server`), donc le
  fusionner aurait introduit une dépendance et un comportement nouveaux.
- `nicsoft/core/game_manager.py` (`_wait_initial_position_web` /
  `_wait_position_web`) ressemble à `wait_for_initial_position()` de
  `nicsoft/engine/board_utils.py`, mais la version web pilote
  `set_app_state`/`send_event` au lieu d'imprimer dans le terminal —
  différence de transport volontaire, non fusionnée.

**Tests** : `python -m pytest nicsoft/tests/` → 79 passed, 4 skipped
(tests matériel auto-skippés en l'absence d'USB), aucune régression.

# Changelog — Issue #256

## Téléchargement Rodent IV (Win) : délai d'attente et vérification d'intégrité

`on_download_rodent` (`nicsoft/web/server.py`) récupérait les 3 fichiers du
moteur Rodent IV Windows (`rodent-iv-x64.exe`, `msvcr120.dll`,
`msvcp120.dll`) via `urllib.request.urlretrieve`, sans délai d'attente ni
vérification, avant de les rendre utilisables (règles EXP-013 et SEC-022 de
l'audit).

Nouvelle fonction `_telecharger_fichier_rodent()` :
- télécharge via `urllib.request.urlopen(..., timeout=15)` (remplace
  `urlretrieve`, qui ne supporte aucun paramètre de délai) ;
- calcule l'empreinte SHA-256 du contenu pendant le téléchargement et la
  compare à une référence connue (`_RODENT_WIN_SHA256`) ;
- en cas d'écart, de délai dépassé, ou d'absence de référence connue pour
  un nom de fichier : supprime le fichier téléchargé (jamais installé) et
  laisse l'exception remonter — l'échec est signalé à l'interface via
  l'événement `rodent_download_result` existant (comportement inchangé,
  déjà adapté).

**Provenance des empreintes de référence** — calculées directement depuis
les fichiers déjà versionnés dans ce dépôt sous `engines/rodent-iv-win/`
(commit courant), qui sont exactement la même release que celle
re-téléchargée par ce handler pour les installations NSIS standalone
n'embarquant pas ces fichiers. Aucune empreinte n'a été calculée à partir
d'un téléchargement non vérifié. Les 3 fichiers du moteur ont pu être
couverts par cette référence versionnée — aucun fichier n'a dû être laissé
sans référence :
- `rodent-iv-x64.exe` → `39c879b2dfdaf0252e94db547397d95422fee76ea8bafa584bfdc03e4d648de5`
- `msvcr120.dll` → `ad32240bb1de55c3f5fcac8789f583a17057f9d14914c538c2a7a5ad346b341c`
- `msvcp120.dll` → `81fbc2824e73f0d101d91854694a52e79db0ffaadbb2a10deaaf47b3b7f9b2b0`

Tests ajoutés dans `nicsoft/tests/test_rodent.py` (4 nouveaux, aucun accès
réseau réel, `urllib.request.urlopen` mocké) :
- délai dépassé → `URLError` propagée, aucun fichier créé ;
- empreinte invalide → `ValueError`, fichier supprimé ;
- nom de fichier sans référence connue → refusé avant toute requête réseau ;
- empreinte valide → fichier écrit normalement.

Suite complète (hors `test_move_matching.py`/`test_players.py`, en échec
préexistant dans cet environnement faute du module `hid`, sans rapport
avec ce changement) : 74 passed, 4 skipped, aucune régression.

Backup pinné : `avant-issue256-rodent-timeout-integrite`.

## Dépendances : correctifs de sécurité, épinglage des versions flottantes, retrait de berserk

Audit `requirements.txt` : 4 paquets en retard de correctifs de sécurité
(SEC-001), 2 non épinglés (EXP-001), et `berserk` déclaré mais jamais
importé (reste de NicLink).

- **Correctifs de sécurité** (`pip-audit` : 11 vulnérabilités → 0) :
  - `setuptools` 69.1.1 → 84.1.0 (PYSEC-2025-49, PYSEC-2026-1918,
    PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w)
  - `wheel` 0.42.0 → 0.46.2 (CVE-2026-24049)
  - `python-socketio` 5.16.1 → 5.16.2 (PYSEC-2026-3042)
  - `Werkzeug` 3.1.7 → 3.1.9 (PYSEC-2026-4312)
- **Épinglage** des versions flottantes, sur la version installée/testée :
  - `numpy` `>=1.26.4` → `==2.5.4`
  - `edge-tts` `>=6.1.0` → `==7.3.1`
- **Retrait de `berserk`** (`requirements.txt` + tableau d'inventaire
  `ETAT_PROJET.md`) : aucun import dans le code, aucune référence dans les
  scripts d'installation (`1-Installer.bat`, `bootstrap_linux.sh`) ni
  l'installeur Windows.

Aucun conflit de compatibilité : `pip check` propre avec Flask 3.1.3 et
Flask-SocketIO 5.6.1 après les 4 montées de version. Suite de tests
complète (hors marqueur `hardware`) : 75 passed, 4 skipped.

`ETAT_PROJET.md` mis à jour en cohérence (tableau §5, versions
`python-socketio`/`Werkzeug`/`numpy`, ligne `berserk` supprimée).

# Changelog — Issue #212

## Tests e2e Exercices mis à jour pour le nouveau chemin de navigation

`test_exercices_liste_affichee` et `test_retour_depuis_exercices`
(`nicsoft/tests/e2e/test_smoke_e2e.py`) ciblaient encore le bouton direct
"Exercices" du menu principal, retiré au commit e648146 (issue #141,
réorganisation "Ouvertures"). Le chemin actuel comporte 2 étapes : clic sur
le bouton du wrapper `#wrap-ouvertures` (mène à `#screen-ouvertures`), puis
clic sur la carte `.outil-card-clickable` portant
`onclick="_menuCardLaunch('exercices', this)"` (mène à `#screen-exercices`).

Ajout d'un helper `go_exercices(page)` qui suit ce chemin en 2 étapes avec
des sélecteurs indépendants de la langue (même approche que le fix #208) :
- `#wrap-ouvertures button` — id déjà unique, pas de filtre sur le texte.
- `.outil-card-clickable[onclick*="'exercices'"]` — fragment d'attribut
  `onclick`, indépendant des libellés traduits ("📖 Openings"/"📚 Exercises"
  en anglais, langue par défaut de l'environnement de test).

Vérifié : aucune autre référence à l'ancien sélecteur
`button, has_text="📚 Exercices"` dans le fichier. Le bouton "← Menu" de
retour depuis `#screen-exercices` (ligne ~873 de `index.html`) est du texte
brut sans `data-i18n`, donc déjà indépendant de la locale — inchangé.

Suite `nicsoft/tests/e2e/test_smoke_e2e.py` complète : 12 passed, 1 skipped
(hardware), aucune régression.

Backup pinné : `avant-fix-e2e-exercices-navigation-issue212`.

# Changelog — Issue #201

## Suppression du code mort dupliqué (modes pédagogique et labo)

Suppression de deux fichiers orphelins, non importés nulle part dans le
code (aucun `import`, aucune référence dans les scripts `.sh`/`.bat`/`.ps1`,
aucune référence dans `.github/`) :

- `nicsoft/modes/pedagogique/__main__ (pedagogique).py` (1691 lignes) —
  nom de fichier non conforme (espace + parenthèses), donc non importable
  comme module Python de toute façon.
- `nicsoft/modes/labo/__main__labo.py` (409 lignes).

Comparaison ligne à ligne avec les fichiers canoniques réellement utilisés
(`pedagogique.py`, importé par `nicsoft/core/game_manager.py`, et `labo.py`,
importé par le même fichier ainsi que par `nicsoft/modes/labo/__main__.py`) :
les deux fichiers canoniques sont des évolutions strictement plus complètes
des fichiers supprimés (mêmes fonctionnalités + i18n, `RodentEngine`,
pipeline de précalcul du coup moteur, `kill_switch`, `BackMenuExit`, etc.).
Aucune portion de logique utile n'a été identifiée comme présente
uniquement dans les fichiers supprimés — le reste des différences est de la
plomberie CLI obsolète (ancien point d'entrée `main()`/`argparse`/`input()`
préexistant à l'architecture web actuelle).

`py_compile` OK sur les fichiers canoniques après suppression.

Backup pinné : `avant-suppression-code-mort-201`.

# Changelog — Issue #200

## Rapatrier socket.io et chess.js en local

- Téléchargé `socket.io.min.js` (v4.7.2) et `chess.min.js` (v0.10.3) dans
  `nicsoft/web/static/vendor/socket.io/` et `nicsoft/web/static/vendor/chess.js/`.
- `index.html` référence désormais `/static/vendor/socket.io/socket.io.min.js`
  et `/static/vendor/chess.js/chess.min.js` au lieu de cdnjs.cloudflare.com.
- Testé : démarrage serveur Flask OK, page servie sans requête vers cdnjs,
  handshake Socket.IO fonctionnel, fichiers vendor servis en HTTP 200.

## Issue #181 — Vérification version Python dans l'installeur NSIS (essai2)

- `installer-exe/alchess_setup.nsi` : nouvelle fonction `CheckPythonVersionWarning`, appelée juste après détection réussie de Python (SecPython, toutes stratégies : `py -0p`, PATH, scan des dossiers standards) et avant la création du venv. Avertit — sans bloquer — si le Python détecté est une pré-publication (suffixe `rc`/`a`/`b` dans la version complète, ex. `3.15.0rc1`) ou une version ancienne (< 3.10).
- Cas non couvert par la comparaison existante (`CompareVersionToMinimum`) : elle ne compare que "X.Y" (ex. "3.15") au minimum requis (3.12), donc une RC comme `3.15.0rc1` passait la vérification sans que son suffixe soit examiné — cause du bug constaté (Python 3.15rc1 : `hidapi` ne compile pas faute de MSVC, aucun wheel précompilé n'existant pour une RC).
- Ajout de `ExtractFullVersionFromPythonOutput` (garde le suffixe complet de la version, contrairement à `ExtractVersionFromPythonOutput` qui tronque à "X.Y") et de la macro `StrFunc` `StrStr` (recherche de sous-chaîne).
- `MessageBox MB_OKCANCEL` non bloquante : affiche la version détectée, recommande Python 3.12/3.13 stable avec lien vers python.org, l'utilisateur peut continuer quand même (IDCANCEL → Abort propre).
- Non appelée après `InstallPython312NSIS` (installation via winget) : cette voie installe toujours une 3.12 stable, jamais concernée.
- Vérifié : `makensis -V4 alchess_setup.nsi` compile sans erreur (exit 0).

## Issue #170 — llm_explainer : préciser le joueur et interdire les coups futurs dans le prompt

- `nicsoft/modes/opening_explorer/llm_explainer.py` : `_build_user_prompt` identifie désormais le camp qui vient de jouer (Blancs/Noirs, déduit du FEN) et l'inclut explicitement dans le prompt envoyé au LLM ("Les Blancs viennent de jouer : e4"). Ajout d'une consigne explicite interdisant de mentionner les coups futurs de l'adversaire, pour corriger le comportement où le LLM expliquait la réponse probable de l'adversaire au lieu du coup joué.
- Cache LLM vidé (`data/explorer_cache.json`) pour forcer la régénération des explications avec le nouveau prompt.
- Suite de l'issue #168.

# Changelog — issue #148

## Opening Explorer — flèches SVG illustrant les coups mentionnés par le LLM

- `nicsoft/modes/opening_explorer/llm_explainer.py` : prompt système enrichi
  (FR/EN/DE) pour demander au LLM d'ajouter une ligne `[FLECHES: e2-e4, ...]`
  (`[ARROWS: ...]` / `[PFEILE: ...]` selon la langue, même tag interne
  `FLECHES|ARROWS|PFEILE` accepté au parsing) ; ajout de `extract_arrows(text)`
  qui retire cette ligne et retourne la liste des flèches (2 à 4 max, cases
  validées a-h/1-8, from == to ignoré). `get_explanation()` et
  `get_chat_response()` retournent désormais `(texte, flèches)` ; le cache
  disque stocke `{"text": ..., "arrows": [...]}` (rétrocompatible avec les
  anciennes entrées `str`).
- `nicsoft/web/server.py` : `explorer_explanation` et `explorer_chat_response`
  émettent désormais `{"text": ..., "arrows": [["e2","e4"], ...]}`.
- `nicsoft/web/templates/index.html` : `#expl-board` enveloppé dans un
  conteneur `position:relative` avec un `<svg id="expl-arrows">` en
  surimpression (`pointer-events:none`) et un marker `#expl-arrowhead`.
- `nicsoft/web/static/app.js` : `explDrawArrows(arrows)` dessine des flèches
  rouges semi-transparentes (`rgba(232,69,96,0.75)`, épaisseur ~8% d'une
  case) entre les centres des cases, en tenant compte de `_explFlipped`.
  `explClearArrows()` vide le SVG (en conservant `<defs>`) ; appelé dans
  `explorer_state`, `explLoad()` et avant chaque nouveau dessin.

py_compile OK sur `llm_explainer.py` et `server.py` ; `node --check` OK sur
`app.js`.

