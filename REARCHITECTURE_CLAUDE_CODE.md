# Plan de réarchitecture AlChess — Document technique pour Claude Code

**À lire avant de commencer tout travail de réarchitecture.**
**Lire aussi CLAUDE.md, TACHES.md et CONTEXTE.md.**

---

## Contexte

AlChess est une application Python/Flask-SocketIO connectant un échiquier physique Chessnut Air (USB) à une interface web. L'objectif de cette réarchitecture est de rendre le projet multiplateforme (Linux → Windows → Android) sans réécrire l'essentiel.

**Contrainte absolue :** chaque étape doit laisser AlChess entièrement fonctionnel sur Linux. Jamais de régression entre les étapes.

---

## État actuel — problèmes identifiés

### 1. `_niclink.so` — dépendance Linux-only
`nicsoft/niclink/driver.py` importe `from . import _niclink` — une extension C++ compilée via pybind11/Rust, spécifique Linux (`.so`). Elle expose :
- `_niclink.lights_out()`
- `_niclink.set_all_leds(r0..r7)`
- `_niclink.set_led(row, col, val)`
- `_niclink.beep()`
- `_niclink.gameover_lights()`
- La connexion USB au Chessnut Air (`idVendor=0x2d80, idProduct=0x8003`)

**Solution :** remplacer par `hidapi` (Python pur, multiplateforme).

### 2. Chemins hardcodés
`pathlib.Path.home() / "NicLink" / ...` apparaît dans `alchess.py`, `server.py`, et plusieurs modules. Sur Windows, le dossier s'appelle probablement autrement.

**Solution :** centraliser dans un module `nicsoft/config.py` avec une constante `APP_DIR`.

### 3. Appels OS Linux-only dans `alchess.py`
- `subprocess.run(["sudo", "systemctl", "stop", "ModemManager"])` — Linux uniquement
- `os.dup2(devnull_fd, 1)` — redirige stdout, fonctionne aussi sur Windows mais fragile
- `signal.SIGINT` dans `on_disconnect` — fonctionne sur Windows mais à vérifier

### 4. Mélange logique/transport dans `alchess.py`
`alchess.py` (1350 lignes) contient à la fois :
- La boucle principale de menu et dispatch des modes
- Le lancement et la gestion des threads de jeu
- Des accès directs à `web_server._app_state` (couplage fort)
- Des instanciations de `NicLinkManager` (USB) directement dans les `_run_*` functions

---

## Étape 1 — Remplacer `_niclink.so` par `hidapi`

### Objectif
Rendre `driver.py` indépendant de `_niclink.so` en communiquant directement avec le Chessnut Air via `hid` (Python hidapi).

### Protocole Chessnut Air (connu)
- USB HID, `idVendor=0x2d80`, `idProduct=0x8003`
- Lecture position : envoyer une commande, lire 64 bytes en retour → FEN
- LEDs : commandes de type `set_all_leds` avec 8 rangées de bits
- Beep : commande dédiée

**À vérifier en premier :** le protocole exact est dans `src/niclink_src/` (sources C++). Lire `src/niclink_src/` pour extraire les commandes USB brutes avant de coder quoi que ce soit.

### Plan d'implémentation

1. **Créer `nicsoft/niclink/hid_backend.py`** — nouveau backend hidapi
   ```python
   import hid
   VENDOR_ID  = 0x2d80
   PRODUCT_ID = 0x8003  # Air ; Air+ peut différer
   
   class ChessnutHID:
       def connect(self): ...
       def get_raw_position(self) -> bytes: ...
       def set_leds(self, pattern: list[str]): ...
       def lights_out(self): ...
       def beep(self): ...
   ```

2. **Modifier `driver.py`** — remplacer `from . import _niclink` par `from .hid_backend import ChessnutHID` et adapter les appels.

3. **Garder `_niclink.so` comme fallback** pendant la période de transition :
   ```python
   try:
       from .hid_backend import ChessnutHID as _backend
   except ImportError:
       from . import _niclink as _backend  # fallback legacy
   ```

4. **Tests** : vérifier que `get_fen()`, LEDs et beep fonctionnent identiquement.

### Dépendance à ajouter
```
hidapi==0.14.0
```
(`pip install hidapi` — fonctionne sur Linux, Windows, Mac sans compilation)

---

## Étape 2 — Centraliser les chemins dans `config.py`

### Créer `nicsoft/config.py`
```python
import pathlib, os

# Dossier de base de l'application
# Peut être surchargé via variable d'environnement ALCHESS_DIR
_default = pathlib.Path.home() / "NicLink"
APP_DIR = pathlib.Path(os.environ.get("ALCHESS_DIR", str(_default)))

LOGS_DIR    = APP_DIR / "logs"
DATA_DIR    = APP_DIR / "data"
GAMES_DIR   = APP_DIR / "games"
ENGINES_DIR = APP_DIR / "engines"
```

### Remplacements dans le code
Chercher toutes les occurrences de `pathlib.Path.home() / "NicLink"` et `os.path.expanduser("~/NicLink")` dans :
- `alchess.py` (nombreuses occurrences)
- `server.py` (LOG_FILE, TEST_CONFIG_DIR, _get_game_folders)
- Tous les modules sous `nicsoft/modes/`

Remplacer par `from nicsoft.config import APP_DIR, LOGS_DIR, DATA_DIR, GAMES_DIR`.

---

## Étape 3 — Isoler les appels OS dans `alchess.py`

### Créer `nicsoft/platform_utils.py`
```python
import sys, subprocess

def stop_modem_manager():
    """No-op sur Windows."""
    if sys.platform != "linux":
        return
    try:
        subprocess.run(["sudo", "systemctl", "stop", "ModemManager"],
                       capture_output=True, timeout=5)
    except Exception:
        pass

def start_modem_manager():
    if sys.platform != "linux":
        return
    try:
        subprocess.run(["sudo", "systemctl", "start", "ModemManager"],
                       capture_output=True, timeout=5)
    except Exception:
        pass
```

Remplacer les appels directs dans `alchess.py` par ces fonctions.

---

## Étape 4 — Séparer Core et Transport (optionnel pour Windows, requis pour Android)

### Objectif
Extraire la logique de jeu pure dans `nicsoft/core/` indépendant de Flask.

### Structure cible
```
nicsoft/
├── core/                    # Nouveau — logique pure, pas de Flask
│   ├── game_manager.py      # Machine d'état, dispatch modes
│   ├── board_interface.py   # Abstraction échiquier (physique ou virtuel)
│   └── engine_runner.py     # Lancement moteurs UCI
├── web/                     # Inchangé — Flask/SocketIO
│   ├── server.py
│   ├── alchess.py           # Devient un adaptateur web → core
│   └── ...
└── niclink/                 # Inchangé — driver échiquier
    └── driver.py
```

**Note :** cette étape est la plus longue (2-3 sessions). Ne pas la commencer avant que l'étape 1 soit validée en production.

---

## Ordre d'exécution

```
Étape 1 : hidapi          → branche dev → tester → merger master
Étape 2 : config.py       → branche dev → tester → merger master  
Étape 3 : platform_utils  → branche dev → tester → merger master
Étape 4 : core/           → branche dev → tester → merger master
Portage Windows           → branche windows → tester → merger master
```

---

## Règles de travail

- **Backup pinné avant chaque étape** : `python -m nicsoft.utils.backup_manager --pin --label "avant-etape-N-..."`
- **Ne jamais casser Linux** : tester après chaque modification
- **Un commit par sous-étape** avec message descriptif
- **Modifier `TACHES.md`** après chaque étape terminée
- **Signaler les fins de tâche** par : `python3 ~/NicLink/bip.py`

---

## Points d'attention critiques

- **`NicLinkManager` fait un `sys.exit()` si l'échiquier n'est pas détecté** (driver.py ligne 128) — à remplacer par une exception custom pour ne pas tuer Flask.
- **`web_server._app_state` est accédé directement** depuis `alchess.py` — couplage fort à réduire progressivement.
- **Le FEN reader thread tourne à 50ms** — la performance doit être identique avec hidapi.
- **`os.dup2(devnull_fd, 1)`** dans plusieurs `_run_*` de `alchess.py` — redirection stdout pour masquer les logs C++ de lc0. Avec hidapi, plus besoin de ça.
- **Chessnut Air+** a peut-être un `idProduct` différent de `0x8003` — prévoir une config ou auto-détection dans `hid_backend.py`.
