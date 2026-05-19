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
        result = subprocess.run(
            ["sudo", "systemctl", "stop", "ModemManager"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            print("[NicLink] ModemManager arrêté.")
    except Exception:
        pass  # pas de sudo configuré ou ModemManager absent — pas bloquant


def start_modem_manager() -> None:
    """Relance ModemManager — no-op sur les systèmes non-Linux."""
    if sys.platform != "linux":
        return
    try:
        subprocess.run(
            ["sudo", "systemctl", "start", "ModemManager"],
            capture_output=True, timeout=5
        )
    except Exception:
        pass
