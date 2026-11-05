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
