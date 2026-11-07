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
