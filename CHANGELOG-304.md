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
