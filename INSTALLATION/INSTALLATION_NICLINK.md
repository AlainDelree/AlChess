# Guide d'installation NicLink — Nouvelle machine Ubuntu

Basé sur l'installation réelle du 13 avril 2026 sur ThinkPad X1 Carbon Gen 13.
Mis à jour le 30 avril 2026 — launcher GTK, port automatique.
Mis à jour le 10 mai 2026 — installation depuis GitHub, moteurs, .gitignore.

---

## 1. Prérequis système

```bash
sudo apt install libhidapi-hidraw0
sudo apt install libopenblas0
sudo apt install cpufrequtils
sudo apt install stockfish
# Requis pour le launcher GTK (splash de démarrage)
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

---

## 2. Copie du projet

### Option A — Depuis une machine existante (rsync)

Copier le dossier `~/NicLink/` depuis la machine source **sans le venv** :

```bash
rsync -av --exclude=venv alain@machine-source:~/NicLink/ ~/NicLink/
```

> ⚠️ Si copie via clé USB depuis un gestionnaire de fichiers graphique : des messages
> "Erreur lors de la copie — le système ne gère pas les liens symboliques" peuvent
> apparaître. Ces liens concernent uniquement `venv/lib64` qui est recréé
> automatiquement — ils peuvent être ignorés sans problème.

### Option B — Depuis GitHub

```bash
git clone https://github.com/AlainDelree/AlChess.git ~/NicLink
```

> ⚠️ Les binaires `engines/maia/lc0` et `engines/rodent-iv/rodentIV` sont inclus
> dans le repo et compilés pour une architecture **x86_64 Linux**. Sur une autre
> architecture (ARM, etc.), il faudra les recompiler depuis leurs sources respectives
> (voir section 7).

> ⚠️ Le driver Rust `_niclink.so` (interface USB Chessnut) n'est **pas** dans le repo
> car il est compilé pour la machine cible. Il doit être copié depuis une machine
> fonctionnelle ou recompilé depuis les sources (voir section 7).

---

## 3. Recréer le venv

```bash
cd ~/NicLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Règles udev — Chessnut Air

Créer le fichier de règles :

```bash
echo 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2d80", ATTR{idProduct}=="8003", MODE="0666", ATTR{power/control}="on", ATTR{power/autosuspend}="-1"
KERNEL=="hidraw*", ATTRS{idVendor}=="2d80", ATTRS{idProduct}=="8003", MODE="0666"' | sudo tee /etc/udev/rules.d/99-chessnut.rules

sudo udevadm control --reload-rules
```

> ⚠️ **Important** : débrancher et rebrancher le Chessnut **après** avoir appliqué
> les règles pour qu'elles prennent effet.

> ⚠️ **Note sur hidraw** : sur certaines machines, le device `hidraw` du Chessnut
> peut ne pas être couvert par la règle au premier branchement. Vérifier avec :
> ```bash
> ls -la /dev/hidraw*
> ```
> Tous doivent être `crw-rw-rw-`. Si l'un est `crw-------`, faire un
> débranchement/rebranchement — la règle doit s'appliquer automatiquement.

---

## 5. Sudoers — ModemManager

NicLink arrête ModemManager au démarrage (il interfère avec l'USB).
Il faut une règle sans mot de passe pour l'utilisateur :

```bash
echo "NOM_UTILISATEUR ALL=(ALL) NOPASSWD: /bin/systemctl stop ModemManager, /bin/systemctl start ModemManager" | sudo tee /etc/sudoers.d/niclink
sudo chmod 440 /etc/sudoers.d/niclink
```

> ⚠️ Remplacer `NOM_UTILISATEUR` par le vrai nom d'utilisateur (ex: `jess`).

> ⚠️ **Sans cette règle** : au lancement, le système demandera une authentification
> (mot de passe ou lecteur d'empreintes) — ce qui bloque le démarrage de NicLink.

---

## 6. Gouverneur CPU — Performance

Sur batterie, Ubuntu utilise `powersave` qui bride le CPU et rend NicLink très lent
(tours de 13-25 secondes au lieu de 3-5 secondes).

Vérifier les gouverneurs disponibles :
```bash
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
```

Configurer `performance` de façon permanente :
```bash
sudo apt install cpufrequtils
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

> ℹ️ Si `schedutil` est disponible (meilleur compromis performance/batterie) :
> ```bash
> echo 'GOVERNOR="schedutil"' | sudo tee /etc/default/cpufrequtils
> echo schedutil | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
> ```
> Sur certains CPU Intel récents, `schedutil` n'est pas disponible — utiliser
> `performance` dans ce cas.

> ℹ️ Le gouverneur ne change **pas** automatiquement quand on branche le chargeur.
> La configuration via `cpufrequtils` est nécessaire pour le rendre permanent.

---

## 7. Moteurs et driver

### Stockfish
Installé via apt (inclus dans `requirements.txt`, installé automatiquement via pip) :
```bash
sudo apt install stockfish
```

### Maia (lc0) et Rodent IV

**Option A — depuis une machine existante (recommandé) :**
```bash
rsync -av alain@machine-source:~/NicLink/engines/ ~/NicLink/engines/
```

**Option B — depuis GitHub :**
Les binaires sont inclus dans le repo (x86_64 Linux uniquement).
Après `git clone`, rendre les binaires exécutables :
```bash
chmod +x ~/NicLink/engines/maia/lc0
chmod +x ~/NicLink/engines/rodent-iv/rodentIV
```

**Option C — recompiler depuis les sources (autre architecture) :**
- Rodent IV : https://github.com/nescior/Rodent_IV — `make` dans le dossier sources
- lc0/Maia : https://github.com/LeelaChessZero/lc0 — voir leur guide de compilation

Tester après installation :
```bash
~/NicLink/engines/maia/lc0 --help
echo "quit" | ~/NicLink/engines/rodent-iv/rodentIV
```

### Driver Rust `_niclink.so`

Ce fichier est l'interface bas niveau entre Python et le Chessnut Air via USB.
Il est compilé pour la machine cible et **n'est pas dans le repo GitHub**.

**Option A — copier depuis une machine existante :**
```bash
rsync -av alain@machine-source:~/NicLink/nicsoft/niclink/_niclink.so ~/NicLink/nicsoft/niclink/
```

**Option B — recompiler depuis les sources :**
Les sources Rust se trouvent dans `nicsoft/niclink/src/`. Compiler avec :
```bash
cd ~/NicLink/nicsoft/niclink
source ~/NicLink/venv/bin/activate
pip install maturin
maturin develop
```

Vérifier :
```bash
ls ~/NicLink/nicsoft/niclink/_niclink.so && echo "driver OK"
```

---

## 8. Raccourci bureau

NicLink utilise un launcher GTK qui affiche une fenêtre de démarrage animée
dès le double-clic, avant même que Flask soit prêt.

> ⚠️ Le launcher doit être lancé avec le **python système** (`/usr/bin/python3`)
> et non le python du venv, car `python3-gi` (GTK) est une bibliothèque système
> non installable dans un venv. NicLink lui-même continue à tourner avec le venv —
> seul le splash GTK utilise le python système.

```bash
cat > ~/Bureau/NicLink.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=NicLink
Comment=Entraînement aux échecs avec échiquier physique
Exec=bash -c "/usr/bin/python3 /home/NOM_UTILISATEUR/NicLink/nicsoft/web/launcher.py"
Icon=/home/NOM_UTILISATEUR/NicLink/nicsoft/web/static/pieces/wP.svg
Terminal=false
StartupNotify=false
Categories=Game;
EOF
chmod +x ~/Bureau/NicLink.desktop
```

> ⚠️ Remplacer `NOM_UTILISATEUR` par le vrai nom d'utilisateur.

### Tester le launcher

```bash
/usr/bin/python3 ~/NicLink/nicsoft/web/launcher.py
```

Une fenêtre avec spinner doit apparaître immédiatement, puis NicLink s'ouvre
dans le navigateur et la fenêtre se ferme automatiquement.

---

## 9. Port réseau automatique

NicLink détecte automatiquement le premier port libre à partir de 5000.
Si une instance est déjà en cours (port 5000 occupé), la nouvelle instance
démarre sur 5001, 5002, etc. sans bloquer ni afficher d'erreur.

Aucune configuration requise — c'est automatique.

---

## 10. Vérification complète

```bash
# Chessnut détecté
lsusb | grep 2d80

# Autosuspend désactivé (adapter le chemin selon la machine)
grep -r "2d80" /sys/bus/usb/devices/*/idVendor 2>/dev/null
cat /sys/bus/usb/devices/3-6/power/autosuspend   # attendu : -1
cat /sys/bus/usb/devices/3-6/power/control        # attendu : on

# Gouverneur CPU
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor  # attendu : performance

# GTK disponible pour le launcher
/usr/bin/python3 -c "import gi; print('GTK OK')"

# Driver Rust présent
ls ~/NicLink/nicsoft/niclink/_niclink.so && echo "driver OK"

# Lancement via launcher
/usr/bin/python3 ~/NicLink/nicsoft/web/launcher.py
```

---

## 11. Problèmes rencontrés et solutions

| Problème | Cause | Solution |
|----------|-------|----------|
| `ImportError: libhidapi-hidraw.so.0` | Lib système manquante | `sudo apt install libhidapi-hidraw0` |
| `Error: Can not connect to the chess board` | Permissions hidraw manquantes | Vérifier règle udev + rebrancher |
| Demande d'empreinte/mot de passe au démarrage | Règle sudoers manquante | Créer `/etc/sudoers.d/niclink` |
| Jeu très lent (13-25s par tour) | CPU en mode `powersave` | Changer gouverneur en `performance` |
| Déconnexion du plateau en cours de jeu | Autosuspend USB actif | Règle udev `power/control=on` + `autosuspend=-1` |
| `libopenblas.so.0: cannot open shared object file` | Lib manquante pour lc0/Maia | `sudo apt install libopenblas0` |
| Lecteur d'empreintes bloque sudo | PAM fprintd prioritaire | Désactiver dans Paramètres → Utilisateurs → Empreinte |
| SocketIO reste en polling lent | CPU en mode `powersave` | Réglé par le changement de gouverneur |
| `ModuleNotFoundError: No module named 'gi'` | GTK non installé ou venv actif | `sudo apt install python3-gi` et utiliser `/usr/bin/python3` pour le launcher |
| `Address already in use` sur port 5000 | Instance déjà en cours | NicLink trouve automatiquement le prochain port libre — relancer normalement |
| Fenêtre GTK n'apparaît pas au clic | launcher.py lancé avec le venv python | Vérifier que le `.desktop` utilise `/usr/bin/python3` |
| `_niclink.so` manquant après git clone | Driver non inclus dans le repo | Copier depuis machine source ou recompiler (voir section 7) |
| Binaires engines non exécutables après git clone | Permissions non préservées par git | `chmod +x engines/maia/lc0 engines/rodent-iv/rodentIV` |

---

## 12. Résolution d'écran HiDPI

Pour les écrans à haute résolution (ex: 2880x1800), le zoom du navigateur
s'ajuste normalement automatiquement. Si l'interface paraît trop petite,
utiliser le zoom du navigateur (Ctrl+ / Ctrl-).

---

## 13. Résumé — checklist complète sur un nouveau PC

```bash
# 1. Paquets système
sudo apt install libhidapi-hidraw0 libopenblas0 cpufrequtils stockfish
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0

# 2a. Copie du projet depuis machine source
rsync -av --exclude=venv alain@machine-source:~/NicLink/ ~/NicLink/
# OU
# 2b. Cloner depuis GitHub
git clone https://github.com/AlainDelree/AlChess.git ~/NicLink
# → Si depuis GitHub : copier _niclink.so et rendre les binaires exécutables
#   rsync -av alain@machine-source:~/NicLink/nicsoft/niclink/_niclink.so ~/NicLink/nicsoft/niclink/
#   chmod +x ~/NicLink/engines/maia/lc0 ~/NicLink/engines/rodent-iv/rodentIV

# 3. Venv
cd ~/NicLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Règle udev Chessnut Air
echo 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2d80", ATTR{idProduct}=="8003", MODE="0666", ATTR{power/control}="on", ATTR{power/autosuspend}="-1"
KERNEL=="hidraw*", ATTRS{idVendor}=="2d80", ATTRS{idProduct}=="8003", MODE="0666"' | sudo tee /etc/udev/rules.d/99-chessnut.rules
sudo udevadm control --reload-rules
# → débrancher/rebrancher le Chessnut

# 5. Sudoers ModemManager (remplacer NOM_UTILISATEUR)
echo "NOM_UTILISATEUR ALL=(ALL) NOPASSWD: /bin/systemctl stop ModemManager, /bin/systemctl start ModemManager" | sudo tee /etc/sudoers.d/niclink
sudo chmod 440 /etc/sudoers.d/niclink

# 6. Gouverneur CPU
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 7. Raccourci bureau (remplacer NOM_UTILISATEUR)
cat > ~/Bureau/NicLink.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=NicLink
Comment=Entraînement aux échecs avec échiquier physique
Exec=bash -c "/usr/bin/python3 /home/NOM_UTILISATEUR/NicLink/nicsoft/web/launcher.py"
Icon=/home/NOM_UTILISATEUR/NicLink/nicsoft/web/static/pieces/wP.svg
Terminal=false
StartupNotify=false
Categories=Game;
EOF
chmod +x ~/Bureau/NicLink.desktop

# 8. Vérifications
cat /sys/bus/usb/devices/*/power/autosuspend 2>/dev/null | grep -v "^2$" | head -5
sudo -n systemctl stop ModemManager && echo "sudoers OK"
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
/usr/bin/python3 -c "import gi; print('GTK OK')"
ls ~/NicLink/nicsoft/niclink/_niclink.so && echo "driver OK"

# 9. Lancer
/usr/bin/python3 ~/NicLink/nicsoft/web/launcher.py
```
