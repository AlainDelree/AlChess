"""
nicsoft/platform_utils.py — NicLink
Fonctions dépendantes du système d'exploitation (Linux/Windows/Mac).
Centralise les appels OS pour faciliter le portage multiplateforme.
"""

import sys
import subprocess


def stop_modem_manager() -> None:
    """Stoppe ModemManager — no-op sur les systèmes non-Linux."""
    if sys.platform != "linux":
        return
    try:
        # Commande sudo/systemctl fixe, sans entrée utilisateur ni réseau
        result = subprocess.run(["sudo", "systemctl", "stop", "ModemManager"], capture_output=True, timeout=5)  # noqa: S607  # nosec B603 B607
        if result.returncode == 0:
            print("[NicLink] ModemManager arrêté.")
    except (OSError, subprocess.TimeoutExpired):
        pass  # pas de sudo configuré (binaire absent) ou commande trop lente — pas bloquant


def start_modem_manager() -> None:
    """Relance ModemManager — no-op sur les systèmes non-Linux."""
    if sys.platform != "linux":
        return
    try:
        # Commande sudo/systemctl fixe, sans entrée utilisateur ni réseau
        subprocess.run(["sudo", "systemctl", "start", "ModemManager"], capture_output=True, timeout=5)  # noqa: S607  # nosec B603 B607
    except (OSError, subprocess.TimeoutExpired):
        pass  # pas de sudo configuré (binaire absent) ou commande trop lente — pas bloquant
