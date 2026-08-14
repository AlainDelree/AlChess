#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/share/AlChess"
REPO_URL="https://github.com/AlainDelree/AlChess.git"
DESKTOP_FILE="$HOME/Desktop/AlChess.desktop"

echo "=== AlChess — Installation Linux ==="

# 1. Vérifier les prérequis
for cmd in git python3; do
    if ! command -v $cmd &>/dev/null; then
        echo "ERREUR : $cmd est requis. Installez-le avec : sudo apt install $cmd"
        exit 1
    fi
done

if ! python3 -c "import venv" &>/dev/null; then
    echo "ERREUR : python3-venv est requis : sudo apt install python3-venv"
    exit 1
fi

# 2. Cloner ou mettre à jour le repo
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "AlChess déjà installé — mise à jour..."
    git -C "$INSTALL_DIR" fetch --tags origin
    LATEST=$(git -C "$INSTALL_DIR" tag --sort=-version:refname | head -1)
    git -C "$INSTALL_DIR" checkout "$LATEST"
else
    echo "Clonage d'AlChess dans $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    git -C "$INSTALL_DIR" init
    git -C "$INSTALL_DIR" remote add origin "$REPO_URL"
    git -C "$INSTALL_DIR" fetch --depth=1 --tags origin
    LATEST=$(git -C "$INSTALL_DIR" tag --sort=-version:refname | head -1)
    git -C "$INSTALL_DIR" checkout "$LATEST"
fi

echo "Version installée : $LATEST"

# 3. Créer le venv et installer les dépendances
if [ ! -f "$INSTALL_DIR/venv/bin/python" ]; then
    echo "Création de l'environnement virtuel..."
    python3 -m venv "$INSTALL_DIR/venv"
fi

echo "Installation des dépendances..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet

# 4. espeak-ng (moteur TTS système requis par pyttsx3 pour la synthèse vocale)
if ! command -v espeak-ng &>/dev/null; then
    echo "Installation d'espeak-ng (synthèse vocale)..."
    if sudo -n true 2>/dev/null; then
        sudo apt-get install -y espeak-ng
    else
        echo "AVERTISSEMENT : droits sudo requis pour installer espeak-ng."
        echo "Exécutez manuellement : sudo apt-get install espeak-ng"
    fi
fi

# 5. Règles udev Chessnut (optionnel — demande sudo)
UDEV_RULE='SUBSYSTEM=="usb", ATTRS{idVendor}=="2d80", MODE="0666", GROUP="plugdev", TAG+="uaccess"'
UDEV_FILE="/etc/udev/rules.d/99-chessnut-alchess.rules"

echo "Configuration du périphérique USB Chessnut..."
if sudo -n true 2>/dev/null; then
    echo "$UDEV_RULE" | sudo tee "$UDEV_FILE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "Règles udev configurées."
else
    echo "AVERTISSEMENT : droits sudo requis pour la règle udev."
    echo "Exécutez manuellement :"
    echo "  echo '$UDEV_RULE' | sudo tee $UDEV_FILE"
    echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
fi

# 6. Créer le lanceur .desktop sur le bureau
mkdir -p "$HOME/Desktop"
cat > "$DESKTOP_FILE" << DESK
[Desktop Entry]
Name=AlChess
Comment=Entraînement aux échecs sur échiquier physique Chessnut
Exec=bash -c "cd $INSTALL_DIR && $INSTALL_DIR/venv/bin/python -m nicsoft.web"
Icon=$INSTALL_DIR/alchess.ico
Terminal=false
Type=Application
Categories=Game;
DESK
chmod +x "$DESKTOP_FILE"

echo ""
echo "=== Installation terminée ==="
echo "Lancez AlChess avec le raccourci sur le Bureau,"
echo "ou : cd $INSTALL_DIR && venv/bin/python -m nicsoft.web"
