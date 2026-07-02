#!/usr/bin/env bash
# start_alchess.sh — Lance l'interface web d'AlChess depuis le venv local.
# Symétrique de start_alchess.ps1 (Windows). Fonctionne quel que soit le
# répertoire courant : on se place toujours dans le dossier du script.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -x "./venv/bin/python" ]]; then
    echo "Environnement introuvable. Lancez d'abord ./install.sh" >&2
    exit 1
fi

export PYTHONIOENCODING=utf-8

# Lance le serveur web ; l'interface s'ouvre dans le navigateur.
exec ./venv/bin/python -m nicsoft.web "$@"
