# NicLink — Configuration système requise

Ces deux configurations sont à effectuer **une seule fois** sur chaque PC utilisé avec NicLink.
Elles sont persistantes (survivent aux redémarrages) et ciblées uniquement sur l'échiquier Chessnut Air.

---

## 1. Désactiver l'autosuspend USB pour le Chessnut Air

### Pourquoi

Linux gère l'énergie des périphériques USB en les "suspendant" après une période d'inactivité.
Pour un clavier ou une souris, ce mécanisme est transparent car ils se réveillent à la première
interaction. Pour le Chessnut Air, la suspension provoque des déconnexions brutales suivies de
reconnexions ratées — le driver HID échoue avec l'erreur `-75` et l'échiquier devient
non-fonctionnel pendant plusieurs minutes, jusqu'à une deuxième tentative de reconnexion.

C'est la cause principale des lenteurs de détection de coups observées par vagues irrégulières.

### Commande

```bash
echo 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2d80", ATTR{idProduct}=="8003", TEST=="power/autosuspend", ATTR{power/autosuspend}="-1"' | sudo tee /etc/udev/rules.d/99-chessnut.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Et pour appliquer immédiatement sans rebrancher l'échiquier :

```bash
echo -1 | sudo tee /sys/bus/usb/devices/1-1.1/power/autosuspend
```

### Impact sur les autres périphériques USB

**Aucun.** La règle cible exclusivement le Chessnut Air via ses identifiants matériels
(`idVendor=2d80`, `idProduct=8003`). Clavier, souris, disque externe, dongle Bluetooth,
et tout autre périphérique USB conservent leur gestion d'énergie habituelle.

### Pour vérifier que c'est actif

```bash
cat /sys/bus/usb/devices/1-1.1/power/autosuspend
# Doit afficher : -1
```

### Pour annuler

```bash
sudo rm /etc/udev/rules.d/99-chessnut.rules
sudo udevadm control --reload-rules
```

---

## 2. Autoriser NicLink à gérer ModemManager sans mot de passe

### Pourquoi

ModemManager est un service Linux qui surveille les périphériques de type modem — modems GSM,
dongles 4G, certains adaptateurs série. Au démarrage, il sonde tous les ports USB en leur
envoyant des commandes AT pour détecter des modems. Le Chessnut Air, qui se présente comme
un périphérique HID, peut être perturbé par ces tentatives de sondage, causant des
déconnexions ou des comportements imprévisibles.

NicLink stoppe ModemManager automatiquement à son démarrage et le relance à la fermeture.
Pour pouvoir le faire sans demander le mot de passe à chaque fois, il faut une règle sudoers.

### Commande

```bash
echo "$USER ALL=(ALL) NOPASSWD: /bin/systemctl stop ModemManager, /bin/systemctl start ModemManager" | sudo tee /etc/sudoers.d/niclink-modemmanager
sudo chmod 440 /etc/sudoers.d/niclink-modemmanager
```

### Impact sur les autres connecteurs USB et périphériques

**Dongle Bluetooth :** non affecté. Le Bluetooth est géré par `bluetoothd`, un service
indépendant de ModemManager. Le dongle Bluetooth continuera à fonctionner normalement
pendant et après l'utilisation de NicLink.

**Clavier, souris, disque externe, webcam :** non affectés. Ces périphériques HID et
de stockage ne sont pas gérés par ModemManager.

**Dongle 4G / modem USB :** si tu utilises un dongle 4G ou un modem USB sur ce PC,
il sera temporairement non-fonctionnel pendant qu'une session NicLink est ouverte.
Il redeviendra disponible dès la fermeture de NicLink. Si c'est problématique,
il suffit de ne pas configurer cette règle sudoers et de stopper ModemManager
manuellement avant chaque session : `sudo systemctl stop ModemManager`.

**Adaptateur série USB (RS-232) :** potentiellement affecté pendant la session NicLink,
pour la même raison que le dongle 4G.

### Ce que NicLink fait exactement

- Au démarrage de `python -m nicsoft.web` : `sudo systemctl stop ModemManager`
- À la fermeture (bouton Quitter ou Ctrl+C) : `sudo systemctl start ModemManager`

Si la règle sudoers n'est pas configurée, NicLink affiche un message d'échec silencieux
et continue de fonctionner — c'est non-bloquant.

### Pour vérifier que la règle est active

```bash
sudo -n systemctl stop ModemManager && echo "OK — pas de mot de passe requis"
```

### Pour annuler

```bash
sudo rm /etc/sudoers.d/niclink-modemmanager
```

---

## Résumé — checklist sur un nouveau PC

```bash
# 1. Règle autosuspend Chessnut Air
echo 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2d80", ATTR{idProduct}=="8003", TEST=="power/autosuspend", ATTR{power/autosuspend}="-1"' | sudo tee /etc/udev/rules.d/99-chessnut.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# 2. Règle sudoers ModemManager
echo "$USER ALL=(ALL) NOPASSWD: /bin/systemctl stop ModemManager, /bin/systemctl start ModemManager" | sudo tee /etc/sudoers.d/niclink-modemmanager
sudo chmod 440 /etc/sudoers.d/niclink-modemmanager

# 3. Vérifications
cat /sys/bus/usb/devices/1-1.1/power/autosuspend   # doit afficher -1
sudo -n systemctl stop ModemManager && echo "sudoers OK"
```

Ces deux configurations suffisent. NicLink gère ensuite tout automatiquement.

---

## 3. Installation de NicLink

### Prérequis système

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
# Moteur Stockfish
sudo apt install stockfish -y
```

### Copier NicLink sur le PC

Copier le dossier `NicLink` depuis une clé USB ou par réseau :

```bash
# Depuis une clé USB (adapter le chemin)
cp -r /media/$USER/USB/NicLink ~/NicLink

# Ou depuis un autre PC via réseau local
scp -r source@adresse-pc:~/NicLink ~/NicLink
```

### Créer l'environnement virtuel

```bash
cd ~/NicLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Vérifier le driver Chessnut

```bash
ls ~/NicLink/nicsoft/niclink/_niclink.so
# Doit afficher le fichier — si absent, contacter l'administrateur
```

### Lancer NicLink

```bash
cd ~/NicLink
source venv/bin/activate
python -m nicsoft.web
```

### Créer un raccourci bureau (optionnel)

```bash
cat > ~/Desktop/NicLink.desktop << 'DESK'
[Desktop Entry]
Name=NicLink
Exec=bash -c "cd ~/NicLink && source ~/NicLink/venv/bin/activate && python -m nicsoft.web"
Icon=applications-games
Terminal=false
Type=Application
DESK
chmod +x ~/Desktop/NicLink.desktop
```

---

## 4. Données et fichiers

| Dossier | Contenu |
|---|---|
| `~/NicLink/data/books/` | Livres Polyglot (.bin) pour les exercices |
| `~/NicLink/data/eco_hierarchy.json` | Hiérarchie ECO (généré par `manage.py`) |
| `~/NicLink/data/eco_*.tsv` | Catalogue ECO Lichess (à télécharger) |
| `~/NicLink/games/` | Parties sauvegardées (PGN) |
| `~/NicLink/logs/niclink.log` | Journal des erreurs |
| `~/NicLink/backups/` | Sauvegardes pinned |

### Télécharger les fichiers ECO Lichess (pour les exercices)

```bash
cd ~/NicLink/data
for letter in a b c d e; do
  curl -o eco_${letter}.tsv https://raw.githubusercontent.com/lichess-org/chess-openings/master/${letter}.tsv
done
```

### Mettre à jour la hiérarchie ECO Wikipedia

```bash
cd ~/NicLink
source venv/bin/activate
python -m nicsoft.exercices.manage
# Choisir option 5
```

### Gérer le catalogue d'ouvertures

```bash
cd ~/NicLink
source venv/bin/activate
python -m nicsoft.exercices.manage
```

---

## 5. En cas de problème

### L'échiquier n'est pas détecté

1. Vérifier que l'échiquier est allumé et branché
2. Vérifier la règle udev : `cat /sys/bus/usb/devices/*/idVendor | grep 2d80`
3. Redémarrer NicLink — il tentera une reconnexion automatique
4. En dernier recours : débrancher/rebrancher l'échiquier

### Envoyer les logs en cas de bug

Le fichier `~/NicLink/logs/niclink.log` contient les erreurs enregistrées.
Il est aussi accessible depuis l'interface web : cliquer sur `📋 logs` en haut à droite.

```bash
# Voir les dernières erreurs
tail -50 ~/NicLink/logs/niclink.log
```

---

## Résumé — checklist complète sur un nouveau PC

```bash
# 1. Règle autosuspend Chessnut Air
echo 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2d80", ATTR{idProduct}=="8003", TEST=="power/autosuspend", ATTR{power/autosuspend}="-1"' | sudo tee /etc/udev/rules.d/99-chessnut.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# 2. Règle sudoers ModemManager
echo "$USER ALL=(ALL) NOPASSWD: /bin/systemctl stop ModemManager, /bin/systemctl start ModemManager" | sudo tee /etc/sudoers.d/niclink-modemmanager
sudo chmod 440 /etc/sudoers.d/niclink-modemmanager

# 3. Installation NicLink
cp -r /media/$USER/USB/NicLink ~/NicLink   # adapter le chemin
cd ~/NicLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo apt install stockfish -y

# 4. Fichiers ECO (exercices)
cd ~/NicLink/data
for letter in a b c d e; do
  curl -o eco_${letter}.tsv https://raw.githubusercontent.com/lichess-org/chess-openings/master/${letter}.tsv
done

# 5. Vérifications
cat /sys/bus/usb/devices/1-1.1/power/autosuspend   # doit afficher -1
sudo -n systemctl stop ModemManager && echo "sudoers OK"
ls ~/NicLink/nicsoft/niclink/_niclink.so && echo "driver OK"

# 6. Lancer
source ~/NicLink/venv/bin/activate
python -m nicsoft.web
```
