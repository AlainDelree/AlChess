# Guide d'installation AlChess — Nouvelle machine Ubuntu

Basé sur l'installation réelle du 13 avril 2026 sur ThinkPad X1 Carbon Gen 13.
Mis à jour le 30 avril 2026 — launcher GTK, port automatique.
Mis à jour le 1 mai 2026 — quirk usbhid Chessnut, recompilation driver .so.
Mis à jour le 3 mai 2026 — GitHub, renommage AlChess.
Mis à jour le 28 juillet 2026 — limitation Smart App Control Windows 11 (issue #85).

---

## ⚠️ Windows 11 — Smart App Control

> Ce guide porte principalement sur l'installation Ubuntu. Cette section
> documente une limitation spécifique à **Windows 11**, pour les
> utilisateurs installant AlChess via `AlChess_Setup.exe` ou
> `install_alchess.ps1` (voir le README, section Windows).

Sur Windows 11 avec **Smart App Control** (Contrôle intelligent des
applications, SAC) activé, le double-clic sur `2-Lancer_AlChess.bat` ou sur
le raccourci bureau est bloqué après l'installation, avec le message :

> « Contrôle intelligent des applications a bloqué un fichier potentiellement
> dangereux »

**Pourquoi ça bloque** : SAC est un mécanisme de Windows 11 qui n'autorise
l'exécution que des applications ayant une réputation établie via le cloud
Microsoft (télémétrie, volume d'installations, signature numérique). AlChess
est un logiciel open source distribué directement en ZIP/exécutable, sans
**certificat de signature de code** (~100 €/an) — il n'a donc aucune
réputation cloud et est traité par défaut comme potentiellement dangereux,
qu'il le soit ou non.

**Différence avec SmartScreen** : SmartScreen (l'avertissement « Windows a
protégé votre ordinateur », plus ancien et plus connu) propose un bouton
« Informations complémentaires » → « Exécuter quand même » qui permet de
passer outre au cas par cas. **Smart App Control ne propose pas cette
option** — c'est un blocage sans contournement possible au niveau de
l'application elle-même. Sans certificat de signature de code, il est
impossible de faire disparaître ce blocage par une modification du code
d'AlChess.

**Premier lancement — cas particulier** : le bouton « Lancer AlChess » à la
fin de l'assistant d'installation NSIS (`AlChess_Setup.exe`) fonctionne
**même avec SAC activé**, car il s'exécute dans le contexte (et hérite de la
confiance) du processus installeur déjà lancé par l'utilisateur — SAC ne le
bloque pas. C'est uniquement le **lancement ultérieur**, depuis le raccourci
bureau ou `2-Lancer_AlChess.bat`, qui déclenche le blocage.

**Contournements :**
- **Option A** : lancer AlChess depuis le bouton « Lancer AlChess » à la fin
  de l'installation (fonctionne toujours, y compris avec SAC activé)
- **Option B** : désactiver Smart App Control dans Paramètres →
  Confidentialité et sécurité → Sécurité Windows → Contrôle des applications
  et du navigateur → Contrôle intelligent des applications → Désactivé
- **Option C** : utiliser Windows 10, ou Windows 11 avec SAC déjà désactivé

---

## 1. Prérequis système

```bash
sudo apt install libhidapi-hidraw0
sudo apt install libopenblas0
sudo apt install cpufrequtils
sudo apt install stockfish
# Requis pour le launcher GTK (splash de démarrage)
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
# Requis pour la recompilation du driver Chessnut (voir section 4b)
sudo apt install cmake pkg-config libudev-dev libhidapi-dev build-essential python3-dev
```

---

## 2. Récupération du projet

**Depuis GitHub (recommandé) :**

```bash
git clone https://github.com/AlainDelree/AlChess.git ~/NicLink
```

**Depuis une machine locale (alternative) :**

```bash
rsync -av --exclude=venv alain@machine-source:~/NicLink/ ~/NicLink/
```

> ⚠️ Si copie via clé USB depuis un gestionnaire de fichiers graphique : des messages
> "Erreur lors de la copie — le système ne gère pas les liens symboliques" peuvent
> apparaître. Ces liens concernent uniquement `venv/lib64` qui est recréé
> automatiquement — ils peuvent être ignorés sans problème.

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

> ℹ️ **Chessnut Air Plus** : même `idVendor` (`2d80`) mais `idProduct` différent
> (`8202` au lieu de `8003`). Vérifier avec `lsusb` et adapter la valeur
> `idProduct` dans la commande ci-dessus en conséquence.

> ℹ️ **Chessnut Go** (modèle de voyage, ref CG100) : même `idVendor` (`2d80`)
> mais `idProduct` différent (`8501` au lieu de `8003`). Vérifier avec
> `lsusb` et adapter la valeur `idProduct` dans la commande ci-dessus en
> conséquence.

> ⚠️ **Note sur hidraw** : sur certaines machines, le device `hidraw` du Chessnut
> peut ne pas être couvert par la règle au premier branchement. Vérifier avec :
> ```bash
> ls -la /dev/hidraw*
> ```
> Tous doivent être `crw-rw-rw-`. Si l'un est `crw-------`, faire un
> débranchement/rebranchement — la règle doit s'appliquer automatiquement.

---

## 4b. Quirk usbhid — si le Chessnut n'apparaît pas comme device HID

Sur certaines machines (testé sur ThinkPad X1 Carbon Gen 7), le kernel ne crée
pas de device HID pour le Chessnut malgré les règles udev. Le Chessnut est vu
par `lsusb` mais absent de `/sys/bus/hid/devices/`.

**Symptôme :** `Error: Can not connect to the chess board` au démarrage de NicLink,
et `ls /sys/bus/hid/devices/` ne montre pas `2D80:8003`.

**Solution — rendre le quirk permanent :**

```bash
echo 'options usbhid quirks=0x2d80:0x8003:0x40' | sudo tee /etc/modprobe.d/chessnut.conf
sudo update-initramfs -u
```

Puis redémarrer le PC et rebrancher le Chessnut. Vérifier :

```bash
ls /sys/bus/hid/devices/ | grep 2D80   # doit afficher 0003:2D80:8003.XXXX
ls -la /dev/hidraw*                    # doit montrer un hidraw avec crw-rw-rw-
```

> ℹ️ Le quirk `0x40` force le kernel à traiter le Chessnut comme un device HID
> complet, contournant le problème de binding automatique.

> ℹ️ **Chessnut Air Plus** : remplacer `0x2d80:0x8003:0x40` par
> `0x2d80:0x8202:0x40` dans la commande ci-dessus (idProduct `8202` au lieu
> de `8003`).

> ℹ️ **Chessnut Go** (CG100) : remplacer `0x2d80:0x8003:0x40` par
> `0x2d80:0x8501:0x40` dans la commande ci-dessus (idProduct `8501` au lieu
> de `8003`).

---

## 4bis. Mon échiquier Chessnut n'est pas détecté

### Principe

Si AlChess affiche « Board not detected » au démarrage, l'idProduct USB de
votre modèle n'est peut-être pas encore connu. Tous les modèles Chessnut
partagent `idVendor=2d80` et le même protocole HID — seul l'idProduct
change. Le correctif est une ligne dans `nicsoft/niclink/hid_backend.py`.

### Étape 1 — Identifier l'idProduct

**Linux :**

```bash
lsusb | grep 2d80
# Exemple : Bus 001 Device 008: ID 2d80:8501 Chessnut Chessnut Go
#                                       ^^^^ = idProduct
```

**Windows :**

Ouvrir PowerShell et lancer :

```powershell
Get-PnpDevice -Class HIDClass | Where-Object { $_.InstanceId -like "*2D80*" } | Select-Object FriendlyName, InstanceId
```

L'InstanceId contient `VID_2D80&PID_XXXX` — les 4 chiffres après `PID_`
sont l'idProduct.

Alternative : Gestionnaire de périphériques → clic droit sur le Chessnut →
Propriétés → Détails → ID matériel.

### Étape 2 — Ajouter l'idProduct dans le code

Ouvrir `nicsoft/niclink/hid_backend.py` (ligne ~12) :

- Linux : `~/NicLink/nicsoft/niclink/hid_backend.py`
- Windows : `<dossier AlChess>\nicsoft\niclink\hid_backend.py` (avec
  Notepad ou VS Code)

Ligne à modifier :

```python
PRODUCT_IDS = [0x8001, 0x8002, 0x8003, 0x8202, 0x8501]  # 8003=Air, 8202=Air Plus, 8501=Chessnut Go
```

Ajouter votre idProduct (en hexadécimal, préfixe `0x`) à la liste. Exemple
pour un idProduct `85AB` :

```python
PRODUCT_IDS = [0x8001, 0x8002, 0x8003, 0x8202, 0x8501, 0x85AB]
```

### Étape 3 (Linux uniquement) — Règle udev

```bash
sudo tee -a /etc/udev/rules.d/99-chessnutair.rules <<EOF
SUBSYSTEM=="usb", ATTRS{idVendor}=="2d80", ATTRS{idProduct}=="XXXX", GROUP="plugdev", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2d80", ATTRS{idProduct}=="XXXX", GROUP="plugdev", TAG+="uaccess"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

(Remplacer `XXXX` par votre idProduct en minuscules, ex. `85ab`)

### Étape 4 — Relancer AlChess

- Linux : `python3 -m nicsoft.web`
- Windows : double-cliquer `2-Lancer_AlChess.bat`

### Signaler votre modèle

Si ça fonctionne, ouvrir une issue sur
https://github.com/AlainDelree/AlChess en indiquant le nom exact du modèle
et l'idProduct — il sera ajouté à la liste officielle pour les prochaines
versions.

---

## 4c. Recompilation du driver — si `_niclink.so` ne fonctionne pas

Le fichier `nicsoft/niclink/_niclink.cpython-312-x86_64-linux-gnu.so` est un
driver C++ compilé. Il doit être **recompilé sur chaque machine** car il dépend
des bibliothèques système locales.

**Symptôme :** NicLink démarre mais ne peut pas ouvrir le Chessnut même avec
le hidraw visible et les permissions correctes.

**Recompilation :**

```bash
# Copier les sources (présentes dans ~/NicLink/src/)
cp -r ~/NicLink/src/ ~/niclink_src/
cd ~/niclink_src

# Adapter la version Python (vérifier avec python3 --version)
sed -i 's/set(PY_VERSION 3.13)/set(PY_VERSION 3.12)/' CMakeLists.txt

# Compiler
mkdir -p build && cd build
cmake .. && make -j4

# Copier le .so compilé dans NicLink
cp _niclink.cpython-312-x86_64-linux-gnu.so ~/NicLink/nicsoft/niclink/
```

> ⚠️ Adapter `3.13` et `3.12` selon les versions réelles (source et cible).
> Vérifier avec `python3 --version` sur la machine cible.

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

## 7. Moteurs

### Stockfish
```bash
sudo apt install stockfish
```

### Maia et Rodent IV
Copier le dossier `engines` depuis la machine source :
```bash
rsync -av alain@machine-source:~/NicLink/engines/ ~/NicLink/engines/
```

Rendre les binaires exécutables :
```bash
chmod +x ~/NicLink/engines/maia/lc0
chmod +x ~/NicLink/engines/rodent-iv/rodentIV
```

Tester :
```bash
~/NicLink/engines/maia/lc0 --help
echo "quit" | ~/NicLink/engines/rodent-iv/rodentIV
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
Name=AlChess
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

# Device HID créé
ls /sys/bus/hid/devices/ | grep 2D80   # doit afficher 0003:2D80:8003.XXXX

# Autosuspend désactivé (adapter le chemin selon la machine)
grep -r "2d80" /sys/bus/usb/devices/*/idVendor 2>/dev/null
cat /sys/bus/usb/devices/3-6/power/autosuspend   # attendu : -1
cat /sys/bus/usb/devices/3-6/power/control        # attendu : on

# Gouverneur CPU
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor  # attendu : performance

# GTK disponible pour le launcher
/usr/bin/python3 -c "import gi; print('GTK OK')"

# Lancement via launcher
/usr/bin/python3 ~/NicLink/nicsoft/web/launcher.py
```

---

## 11. Problèmes rencontrés et solutions

| Problème | Cause | Solution |
|----------|-------|----------|
| `ImportError: libhidapi-hidraw.so.0` | Lib système manquante | `sudo apt install libhidapi-hidraw0` |
| `Error: Can not connect to the chess board` | Permissions hidraw manquantes | Vérifier règle udev + rebrancher |
| Chessnut absent de `/sys/bus/hid/devices/` | Kernel ne bind pas le HID | Quirk usbhid (section 4b) |
| Demande d'empreinte/mot de passe au démarrage | Règle sudoers manquante | Créer `/etc/sudoers.d/niclink` |
| Jeu très lent (13-25s par tour) | CPU en mode `powersave` | Changer gouverneur en `performance` |
| Déconnexion du plateau en cours de jeu | Autosuspend USB actif | Règle udev `power/control=on` + `autosuspend=-1` |
| `libopenblas.so.0: cannot open shared object file` | Lib manquante pour lc0/Maia | `sudo apt install libopenblas0` |
| Lecteur d'empreintes bloque sudo | PAM fprintd prioritaire | Désactiver dans Paramètres → Utilisateurs → Empreinte |
| SocketIO reste en polling lent | CPU en mode `powersave` | Réglé par le changement de gouverneur |
| `ModuleNotFoundError: No module named 'gi'` | GTK non installé ou venv actif | `sudo apt install python3-gi` et utiliser `/usr/bin/python3` pour le launcher |
| `Address already in use` sur port 5000 | Instance déjà en cours | AlChess trouve automatiquement le prochain port libre — relancer normalement |
| Fenêtre GTK n'apparaît pas au clic | launcher.py lancé avec le venv python | Vérifier que le `.desktop` utilise `/usr/bin/python3` |

---

## 12. Résolution d'écran HiDPI

Pour les écrans à haute résolution (ex: 2880x1800), le zoom du navigateur
s'ajuste normalement automatiquement. Si l'interface paraît trop petite,
utiliser le zoom du navigateur (Ctrl+ / Ctrl-).

---

## 14. Mise à jour depuis une ancienne installation

### Si l'installation a été faite via `git clone` (recommandé)

```bash
cd ~/NicLink
git pull
```

Puis recompiler le driver si nécessaire (voir section 4c).

---

### Si l'installation a été faite via clé USB ou rsync

> ⚠️ **Sauvegarder d'abord les données importantes :**
> ```bash
> cp -r ~/NicLink/games ~/Bureau/games_backup
> cp -r ~/NicLink/data ~/Bureau/data_backup
> ```

Initialiser Git et récupérer la version GitHub :

```bash
cd ~/NicLink
git init
git remote add origin https://github.com/AlainDelree/AlChess.git
git fetch
git reset --hard origin/master
```

> ⚠️ `git reset --hard` écrase tout le code local avec la version GitHub.
> Les données dans `games/` et `data/` ne sont pas touchées si elles ne sont
> pas dans le dépôt — mais par précaution, toujours sauvegarder avant.

Ensuite recréer le venv et recompiler le driver :

```bash
cd ~/NicLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Et recompiler le `.so` (voir section 4c).

---

## 13. Résumé — checklist complète sur un nouveau PC

```bash
# 1. Paquets système
sudo apt install git libhidapi-hidraw0 libopenblas0 cpufrequtils stockfish
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
sudo apt install cmake pkg-config libudev-dev libhidapi-dev build-essential python3-dev

# 2. Récupération du projet
git clone https://github.com/AlainDelree/AlChess.git ~/NicLink
# Ou depuis une machine locale :
# rsync -av --exclude=venv alain@machine-source:~/NicLink/ ~/NicLink/

# 3. Venv
cd ~/NicLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Recompilation du driver .so (obligatoire sur chaque nouvelle machine)
cp -r ~/NicLink/src/ ~/niclink_src/
sed -i 's/set(PY_VERSION 3.13)/set(PY_VERSION 3.12)/' ~/niclink_src/CMakeLists.txt
mkdir -p ~/niclink_src/build && cd ~/niclink_src/build
cmake .. && make -j4
cp _niclink.cpython-312-x86_64-linux-gnu.so ~/NicLink/nicsoft/niclink/
cd ~/NicLink

# 5. Règle udev Chessnut Air
# (idProduct 8003 = Chessnut Air ; 8202 = Chessnut Air Plus ; 8501 = Chessnut Go — adapter selon lsusb)
echo 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2d80", ATTR{idProduct}=="8003", MODE="0666", ATTR{power/control}="on", ATTR{power/autosuspend}="-1"
KERNEL=="hidraw*", ATTRS{idVendor}=="2d80", ATTRS{idProduct}=="8003", MODE="0666"' | sudo tee /etc/udev/rules.d/99-chessnut.rules
sudo udevadm control --reload-rules
# → débrancher/rebrancher le Chessnut

# 6. Quirk usbhid (si Chessnut absent de /sys/bus/hid/devices/)
# (remplacer 0x8003 par 0x8202 pour un Chessnut Air Plus, ou 0x8501 pour un Chessnut Go)
echo 'options usbhid quirks=0x2d80:0x8003:0x40' | sudo tee /etc/modprobe.d/chessnut.conf
sudo update-initramfs -u
# → redémarrer le PC

# 7. Sudoers ModemManager (remplacer NOM_UTILISATEUR)
echo "NOM_UTILISATEUR ALL=(ALL) NOPASSWD: /bin/systemctl stop ModemManager, /bin/systemctl start ModemManager" | sudo tee /etc/sudoers.d/niclink
sudo chmod 440 /etc/sudoers.d/niclink

# 8. Gouverneur CPU
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 9. Raccourci bureau (remplacer NOM_UTILISATEUR)
cat > ~/Bureau/NicLink.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=AlChess
Comment=Entraînement aux échecs avec échiquier physique
Exec=bash -c "/usr/bin/python3 /home/NOM_UTILISATEUR/NicLink/nicsoft/web/launcher.py"
Icon=/home/NOM_UTILISATEUR/NicLink/nicsoft/web/static/pieces/wP.svg
Terminal=false
StartupNotify=false
Categories=Game;
EOF
chmod +x ~/Bureau/NicLink.desktop

# 10. Vérifications
ls /sys/bus/hid/devices/ | grep 2D80   # doit afficher 0003:2D80:8003.XXXX
cat /sys/bus/usb/devices/*/power/autosuspend 2>/dev/null | grep -v "^2$" | head -5
sudo -n systemctl stop ModemManager && echo "sudoers OK"
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
/usr/bin/python3 -c "import gi; print('GTK OK')"

# 11. Lancer
/usr/bin/python3 ~/NicLink/nicsoft/web/launcher.py
```
