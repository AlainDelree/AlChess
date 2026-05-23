#!/usr/bin/env bash
# install.sh — Installation automatique AlChess sur Ubuntu
# Usage : bash ~/NicLink/install.sh
# Idempotent — peut être relancé sans danger.

set -euo pipefail

# ── Couleurs ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
info() { echo -e "${BLUE}  ▸${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
err()  { echo -e "${RED}  ✗${NC} $*" >&2; }
step() { echo -e "\n${BOLD}${BLUE}══ $* ══${NC}"; }

ask_yn() {
    # ask_yn "Question ?" [y|n]  — défaut y si omis
    local prompt="$1" default="${2:-y}"
    local yn
    if [[ "$default" == "y" ]]; then
        read -rp "$(echo -e "${YELLOW}  ?${NC} ${prompt} [O/n] ")" yn
        [[ -z "$yn" || "$yn" =~ ^[OoYy] ]]
    else
        read -rp "$(echo -e "${YELLOW}  ?${NC} ${prompt} [o/N] ")" yn
        [[ "$yn" =~ ^[OoYy] ]]
    fi
}

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="$(whoami)"

echo -e "\n${BOLD}AlChess — Script d'installation${NC}"
echo -e "Répertoire : ${BLUE}${REPO}${NC}\n"

# ── 1. Python ─────────────────────────────────────────────────────────────────
step "Détection de Python"

if ! command -v python3 &>/dev/null; then
    err "python3 introuvable. Installez Python 3.10+ et relancez."
    exit 1
fi
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
ok "Python ${PY_VERSION}"

# ── 2. Paquets système ────────────────────────────────────────────────────────
step "Paquets système"

PKGS=(
    libhidapi-hidraw0 libopenblas0 cpufrequtils stockfish
    python3-gi python3-gi-cairo gir1.2-gtk-3.0
)
MISSING=()
for pkg in "${PKGS[@]}"; do
    dpkg -s "$pkg" &>/dev/null || MISSING+=("$pkg")
done

if [[ ${#MISSING[@]} -eq 0 ]]; then
    ok "Tous les paquets requis sont installés"
else
    warn "Paquets manquants : ${MISSING[*]}"
    if ask_yn "Installer maintenant ? (sudo requis)"; then
        sudo apt-get update -qq
        sudo apt-get install -y "${MISSING[@]}"
        ok "Paquets installés"
    else
        warn "Installation ignorée — certaines étapes pourraient échouer"
    fi
fi

# ── 3. Environnement Python (venv) ────────────────────────────────────────────
step "Environnement Python (venv)"

if [[ ! -d "$REPO/venv" ]]; then
    info "Création du venv..."
    python3 -m venv "$REPO/venv"
fi
info "Mise à jour des dépendances pip..."
"$REPO/venv/bin/pip" install -q --upgrade pip
"$REPO/venv/bin/pip" install -q -r "$REPO/requirements.txt"
ok "Venv prêt : $REPO/venv"

# ── 4. Règles udev (Chessnut Air) ────────────────────────────────────────────
step "Règles udev (Chessnut Air)"

UDEV_FILE="/etc/udev/rules.d/99-chessnut.rules"
if [[ -f "$UDEV_FILE" ]]; then
    ok "Règles udev déjà en place"
else
    if ask_yn "Installer les règles udev ? (sudo requis)"; then
        sudo tee "$UDEV_FILE" > /dev/null << 'EOF'
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="2d80", ATTR{idProduct}=="8003", MODE="0666", ATTR{power/control}="on", ATTR{power/autosuspend}="-1"
KERNEL=="hidraw*", ATTRS{idVendor}=="2d80", ATTRS{idProduct}=="8003", MODE="0666"
EOF
        sudo udevadm control --reload-rules
        ok "Règles udev installées"
        warn "Débranchez et rebranchez le Chessnut pour appliquer les règles"
    fi
fi

# ── 5. Quirk usbhid (optionnel) ──────────────────────────────────────────────
step "Quirk usbhid (optionnel)"

QUIRK_FILE="/etc/modprobe.d/chessnut.conf"
if [[ -f "$QUIRK_FILE" ]]; then
    ok "Quirk déjà configuré"
else
    info "Nécessaire seulement si le Chessnut n'apparaît pas dans /sys/bus/hid/devices/"
    info "Symptôme : 'Error: Can not connect to the chess board' malgré le branchement"
    if ask_yn "Activer le quirk usbhid ?" "n"; then
        echo 'options usbhid quirks=0x2d80:0x8003:0x40' | sudo tee "$QUIRK_FILE" > /dev/null
        sudo update-initramfs -u
        ok "Quirk configuré"
        warn "Redémarrez le PC et rebranchez le Chessnut pour appliquer"
    else
        info "Ignoré — activable plus tard si le Chessnut n'est pas détecté"
    fi
fi

# ── 6. Sudoers ModemManager ──────────────────────────────────────────────────
step "Sudoers ModemManager"

SUDOERS_FILE="/etc/sudoers.d/niclink"
if [[ -f "$SUDOERS_FILE" ]]; then
    ok "Règle sudoers déjà en place"
else
    info "Permet à AlChess d'arrêter ModemManager sans mot de passe"
    info "(ModemManager interfère avec l'USB du Chessnut)"
    if ask_yn "Créer la règle sudoers ? (sudo requis)"; then
        echo "${USER_NAME} ALL=(ALL) NOPASSWD: /bin/systemctl stop ModemManager, /bin/systemctl start ModemManager" \
            | sudo tee "$SUDOERS_FILE" > /dev/null
        sudo chmod 440 "$SUDOERS_FILE"
        ok "Règle sudoers créée pour ${USER_NAME}"
    fi
fi

# ── 7. Gouverneur CPU ────────────────────────────────────────────────────────
step "Gouverneur CPU"

CURRENT_GOV="$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'inconnu')"
if [[ "$CURRENT_GOV" == "performance" || "$CURRENT_GOV" == "schedutil" ]]; then
    ok "Gouverneur déjà réglé : ${CURRENT_GOV}"
else
    warn "Gouverneur actuel : ${CURRENT_GOV} (peut rendre AlChess lent sur batterie)"
    if ask_yn "Configurer en 'performance' ? (sudo requis)"; then
        echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils > /dev/null
        echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
        ok "Gouverneur réglé en performance"
    fi
fi

# ── 8. Raccourci bureau ──────────────────────────────────────────────────────
step "Raccourci bureau"

# Détecter le dossier bureau selon la locale (Bureau / Desktop)
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[[ -d "$DESKTOP_DIR" ]] || DESKTOP_DIR="$HOME/Bureau"
[[ -d "$DESKTOP_DIR" ]] || DESKTOP_DIR="$HOME/Desktop"
[[ -d "$DESKTOP_DIR" ]] || DESKTOP_DIR="$HOME"

DESKTOP_FILE="$DESKTOP_DIR/AlChess.desktop"
if [[ -f "$DESKTOP_FILE" ]]; then
    ok "Raccourci déjà en place : $DESKTOP_FILE"
else
    if ask_yn "Créer le raccourci bureau ?"; then
        cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AlChess
Comment=Entraînement aux échecs avec échiquier physique
Exec=bash -c "/usr/bin/python3 ${REPO}/nicsoft/web/launcher.py"
Icon=${REPO}/nicsoft/web/static/favicon.svg
Terminal=false
StartupNotify=false
Categories=Game;
EOF
        chmod +x "$DESKTOP_FILE"
        ok "Raccourci créé : $DESKTOP_FILE"
    fi
fi

# ── 9. Vérifications finales ──────────────────────────────────────────────────
step "Vérifications"

ERRORS=0

# hidapi Python
if "$REPO/venv/bin/python" -c "import hid" 2>/dev/null; then
    ok "hidapi disponible"
else
    err "hidapi manquant dans le venv"
    ERRORS=$((ERRORS + 1))
fi

# GTK pour le launcher
if /usr/bin/python3 -c "import gi" 2>/dev/null; then
    ok "GTK (python3-gi) disponible"
else
    warn "GTK non disponible — le launcher splash ne fonctionnera pas"
fi

# Stockfish
if command -v stockfish &>/dev/null; then
    ok "Stockfish installé"
else
    warn "Stockfish non trouvé dans le PATH"
fi

# Chessnut branché ?
if lsusb 2>/dev/null | grep -q "2d80"; then
    ok "Chessnut Air détecté (USB)"
    # HID device créé ?
    if ls /sys/bus/hid/devices/ 2>/dev/null | grep -q "2D80"; then
        ok "Device HID créé"
    else
        warn "Chessnut USB visible mais pas de device HID — règles udev ou quirk peut-être nécessaires"
    fi
else
    info "Chessnut non branché — branchez-le pour vérifier la détection"
fi

# Résumé
echo ""
if [[ $ERRORS -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}✓ Installation terminée avec succès !${NC}"
    echo ""
    echo -e "  Lancer AlChess :"
    echo -e "  ${BLUE}/usr/bin/python3 ${REPO}/nicsoft/web/launcher.py${NC}"
else
    echo -e "${RED}${BOLD}Installation terminée avec ${ERRORS} erreur(s).${NC}"
    echo "  Consultez les messages ci-dessus pour corriger."
    exit 1
fi
