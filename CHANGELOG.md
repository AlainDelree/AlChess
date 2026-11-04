# Changelog — Issue #255

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

