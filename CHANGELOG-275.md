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
