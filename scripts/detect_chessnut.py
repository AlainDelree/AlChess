#!/usr/bin/env python3
"""
detect_chessnut.py — Détection automatique des modèles Chessnut non reconnus.

Énumère tous les appareils HID avec idVendor=2d80 (Chessnut).
Pour chaque idProduct trouvé absent de PRODUCT_IDS dans hid_backend.py :
  - L'ajoute à la liste dans hid_backend.py (modification ciblée par regex)
  - Sur Linux : ajoute la règle udev dans /etc/udev/rules.d/99-chessnutair.rules

Codes de sortie :
  0 = OK, rien à faire (tous les modèles branchés déjà connus, ou aucun échiquier branché)
  1 = Nouveaux idProduct ajoutés — l'utilisateur doit relancer AlChess
  2 = Erreur (hid non disponible, hid_backend.py introuvable, etc.)

Usage :
  python3 scripts/detect_chessnut.py [--hid-backend CHEMIN] [--dry-run]
"""

import sys
import os
import re
import platform
import argparse
from pathlib import Path

VENDOR_ID = 0x2d80

# Chemin par défaut de hid_backend.py (relatif à ce script : ../nicsoft/niclink/hid_backend.py)
DEFAULT_HID_BACKEND = Path(__file__).parent.parent / "nicsoft" / "niclink" / "hid_backend.py"

# Fichier de règles udev (Linux uniquement)
UDEV_RULES_FILE = Path("/etc/udev/rules.d/99-chessnutair.rules")


def lire_product_ids(hid_backend_path: Path) -> list[int]:
    """Lit PRODUCT_IDS depuis hid_backend.py par regex. Retourne la liste des int."""
    contenu = hid_backend_path.read_text(encoding="utf-8")
    m = re.search(r"PRODUCT_IDS\s*=\s*\[([^\]]*)\]", contenu)
    if not m:
        raise ValueError(f"PRODUCT_IDS introuvable dans {hid_backend_path}")
    ids_str = m.group(1)
    ids = [int(x.strip(), 16) for x in ids_str.split(",") if x.strip()]
    return ids


def ajouter_product_id(hid_backend_path: Path, new_id: int, nom_modele: str) -> None:
    """Ajoute new_id à PRODUCT_IDS dans hid_backend.py par substitution regex."""
    contenu = hid_backend_path.read_text(encoding="utf-8")
    m = re.search(r"(PRODUCT_IDS\s*=\s*\[)([^\]]*?)(\]\s*(?:#.*)?)", contenu)
    if not m:
        raise ValueError(f"PRODUCT_IDS introuvable dans {hid_backend_path}")
    avant = m.group(1)
    ids_str = m.group(2).rstrip(", ")
    apres_crochet = "]"
    # Reconstruire le commentaire en ajoutant le nouveau modèle
    commentaire_actuel = m.group(3)
    commentaire_m = re.search(r"#(.*)", commentaire_actuel)
    commentaire = commentaire_m.group(1).strip() if commentaire_m else ""
    if commentaire:
        nouveau_commentaire = f"  # {commentaire}, {hex(new_id)}={nom_modele}"
    else:
        nouveau_commentaire = f"  # {hex(new_id)}={nom_modele}"
    nouvelle_ligne = f"{avant}{ids_str}, {hex(new_id)}{apres_crochet}{nouveau_commentaire}"
    nouveau_contenu = contenu[:m.start()] + nouvelle_ligne + contenu[m.end():]
    hid_backend_path.write_text(nouveau_contenu, encoding="utf-8")


def ajouter_regle_udev(product_id: int, dry_run: bool = False) -> bool:
    """Ajoute une règle udev pour product_id. Retourne True si ajoutée, False sinon."""
    pid_hex = f"{product_id:04x}"
    lignes_a_ajouter = (
        f'\n# Chessnut modèle inconnu (idProduct {pid_hex}, ajouté automatiquement)\n'
        f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="2d80", ATTRS{{idProduct}}=="{pid_hex}", '
        f'GROUP="plugdev", TAG+="uaccess"\n'
        f'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="2d80", '
        f'ATTRS{{idProduct}}=="{pid_hex}", GROUP="plugdev", TAG+="uaccess"\n'
    )
    if dry_run:
        print(f"[DRY-RUN] Ajouterait dans {UDEV_RULES_FILE} :\n{lignes_a_ajouter}")
        return True
    try:
        with open(UDEV_RULES_FILE, "a", encoding="utf-8") as f:
            f.write(lignes_a_ajouter)
        os.system("udevadm control --reload-rules && udevadm trigger")
        return True
    except PermissionError:
        print(f"[WARN] Impossible d'écrire dans {UDEV_RULES_FILE} — relancer avec sudo "
              f"ou ajouter manuellement la règle pour idProduct {pid_hex}.", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Détection auto des modèles Chessnut inconnus")
    parser.add_argument("--hid-backend", type=Path, default=DEFAULT_HID_BACKEND,
                        help="Chemin vers hid_backend.py")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les modifications sans les appliquer")
    args = parser.parse_args()

    # Import hid (dans le venv)
    try:
        import hid
    except ImportError:
        print("[ERREUR] Module 'hid' non disponible. Assurez-vous d'être dans le venv AlChess.",
              file=sys.stderr)
        return 2

    # Vérifier hid_backend.py
    if not args.hid_backend.exists():
        print(f"[ERREUR] hid_backend.py introuvable : {args.hid_backend}", file=sys.stderr)
        return 2

    try:
        product_ids_connus = lire_product_ids(args.hid_backend)
    except (ValueError, Exception) as e:
        print(f"[ERREUR] Lecture PRODUCT_IDS : {e}", file=sys.stderr)
        return 2

    # Énumérer tous les appareils HID vendor Chessnut
    try:
        appareils = hid.enumerate(VENDOR_ID, 0)
    except Exception as e:
        print(f"[ERREUR] hid.enumerate : {e}", file=sys.stderr)
        return 2

    if not appareils:
        print("[INFO] Aucun échiquier Chessnut détecté (branchez-le et relancez AlChess).")
        return 0

    # Identifier les idProduct inconnus (dédupliqués)
    ids_trouves = {a["product_id"] for a in appareils}
    ids_inconnus = [pid for pid in ids_trouves if pid not in product_ids_connus]

    if not ids_inconnus:
        print(f"[INFO] Échiquier détecté et déjà reconnu (idProduct : "
              f"{', '.join(hex(p) for p in ids_trouves)}).")
        return 0

    # Ajouter les idProduct inconnus
    ajoutes = []
    for pid in ids_inconnus:
        nom_modele = f"Chessnut-{pid:04x}"
        # Récupérer le nom produit si dispo
        for a in appareils:
            if a["product_id"] == pid and a.get("product_string"):
                nom_modele = a["product_string"].strip() or nom_modele
                break
        print(f"[NOUVEAU] idProduct {hex(pid)} ({nom_modele}) — ajout à PRODUCT_IDS...")
        if not args.dry_run:
            try:
                ajouter_product_id(args.hid_backend, pid, nom_modele)
                ajoutes.append(pid)
            except Exception as e:
                print(f"[ERREUR] Modification hid_backend.py : {e}", file=sys.stderr)
                return 2
        else:
            print(f"[DRY-RUN] Ajouterait {hex(pid)} à PRODUCT_IDS.")
            ajoutes.append(pid)

        # Linux : règle udev
        if platform.system() == "Linux":
            ajouter_regle_udev(pid, dry_run=args.dry_run)

    if ajoutes:
        print(f"\n✅ {len(ajoutes)} nouveau(x) modèle(s) enregistré(s). "
              f"Relancez AlChess pour que la détection prenne effet.")
        return 1  # signal : relancement nécessaire

    return 0


if __name__ == "__main__":
    sys.exit(main())
