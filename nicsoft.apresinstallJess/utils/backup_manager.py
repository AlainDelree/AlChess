"""
backup_manager.py — NicLink
Gestion des sauvegardes du projet NicLink.

Structure sur disque :
  ~/NicLink_backups/
  ├── pinned/
  │   ├── 📌_2026-03-20_14-00-00_menus-stables/
  │   │   ├── NicLink_backup.tar.gz
  │   │   └── README.txt
  │   └── 📌_2026-03-19_10-00-00_detection-coups/
  │       ├── NicLink_backup.tar.gz
  │       └── README.txt
  └── normal/
      ├── 2026-03-20_18-00-00/
      │   ├── NicLink_backup.tar.gz
      │   └── README.txt
      └── 2026-03-19_22-00-00/
          ├── NicLink_backup.tar.gz
          └── README.txt

Fonctionnalités :
  - Backup dans un dossier HORS du projet
  - Dossiers séparés : pinned/ et normal/
  - Rotation automatique sur les normaux uniquement
  - Épinglage / désépinglage d'un backup existant
  - Vérification d'intégrité de l'archive
  - README dans chaque dossier de backup
  - Mode dry-run

Utilisation depuis le code :
    from nicsoft.utils.backup_manager import run_backup
    run_backup()
    run_backup(pinned=True, label="menus stables")

Utilisation en ligne de commande :
    python -m nicsoft.utils.backup_manager
    python -m nicsoft.utils.backup_manager --pin --label "menus stables"
    python -m nicsoft.utils.backup_manager --dry-run
    python -m nicsoft.utils.backup_manager --max-backups 5
    python -m nicsoft.utils.backup_manager --list
    python -m nicsoft.utils.backup_manager --pin-existing 2026-03-20_18-00-00
    python -m nicsoft.utils.backup_manager --unpin "📌_2026-03-20_14-00-00_menus-stables"
"""

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

# Dossier SOURCE à sauvegarder
PROJECT_DIR = Path.home() / "NicLink"

# Dossier DESTINATION — hors du projet
BACKUP_ROOT = Path.home() / "NicLink_backups"
PINNED_DIR  = BACKUP_ROOT / "pinned"
NORMAL_DIR  = BACKUP_ROOT / "normal"

# Nombre maximum de backups normaux à conserver
DEFAULT_MAX_BACKUPS = 5

# Dossiers/fichiers à exclure de la sauvegarde
EXCLUDES = [
    "Idees_Et_Backup",
    "Idees_Et_Backup (Copie)",
    "venv",
    "__pycache__",
    "*.pyc",
    ".git",
]


# ──────────────────────────────────────────────
# Helpers internes
# ──────────────────────────────────────────────

def _make_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _sanitize_label(label: str) -> str:
    """Transforme un label en nom de dossier valide (max 40 car.)."""
    safe = label.strip().replace(" ", "-")
    safe = "".join(c for c in safe if c.isalnum() or c in "-_")
    return safe[:40]


def _folder_name(timestamp: str, pinned: bool, label: str = "") -> str:
    """Construit le nom du dossier de backup."""
    if pinned:
        base = f"📌_{timestamp}"
        if label:
            base += f"_{_sanitize_label(label)}"
        return base
    return timestamp


def _write_readme(folder: Path, timestamp: str, pinned: bool, label: str) -> None:
    """Écrit le README dans le dossier de backup."""
    pin_line   = "Oui — jamais supprimé automatiquement" if pinned else "Non"
    label_line = label if label else "(aucun)"
    content = f"""Backup NicLink
══════════════════════════════
Date        : {timestamp}
Source      : {PROJECT_DIR}
Destination : {folder}
Épinglé     : {pin_line}
Label       : {label_line}

Exclusions :
{chr(10).join(f'  - {ex}' for ex in EXCLUDES)}

Pour restaurer :
  tar -xzf "{folder / 'NicLink_backup.tar.gz'}" -C ~/
"""
    (folder / "README.txt").write_text(content, encoding="utf-8")


def _print_folder_line(folder: Path) -> None:
    """Affiche une ligne résumé pour un dossier de backup."""
    archive = folder / "NicLink_backup.tar.gz"
    size_mb = archive.stat().st_size / (1024 * 1024) if archive.exists() else 0
    mtime   = datetime.fromtimestamp(folder.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    label   = ""
    readme  = folder / "README.txt"
    if readme.exists():
        for line in readme.read_text(encoding="utf-8").splitlines():
            if line.startswith("Label"):
                val = line.split(":", 1)[-1].strip()
                if val != "(aucun)":
                    label = f"  →  {val}"
                break
    print(f"    {mtime}  {size_mb:6.1f} Mo  {folder.name}{label}")


# ──────────────────────────────────────────────
# Fonctions principales
# ──────────────────────────────────────────────

def create_backup(
    pinned: bool = False,
    label: str = "",
    dry_run: bool = False,
) -> Path | None:
    """
    Crée un dossier de backup avec archive tar.gz + README.

    pinned=True  → dans pinned/, jamais touché par la rotation.
    label        → apparaît dans le nom du dossier et dans le README.
    dry_run      → simule sans rien créer.

    Retourne le chemin du dossier créé, ou None en cas d'erreur.
    """
    timestamp   = _make_timestamp()
    folder_name = _folder_name(timestamp, pinned, label)
    dest_parent = PINNED_DIR if pinned else NORMAL_DIR
    folder      = dest_parent / folder_name
    archive     = folder / "NicLink_backup.tar.gz"

    pin_info = " 📌 ÉPINGLÉ" if pinned else ""
    print(f"\n📦 Source      : {PROJECT_DIR}{pin_info}")
    print(f"📂 Destination : {folder}")
    if label:
        print(f"🏷  Label       : {label}")

    if dry_run:
        print("🔍 [DRY-RUN] Aucun fichier créé.")
        return None

    folder.mkdir(parents=True, exist_ok=True)

    cmd = ["tar", "-czf", str(archive)]
    for ex in EXCLUDES:
        cmd += ["--exclude", ex]
    cmd += ["-C", str(PROJECT_DIR.parent), PROJECT_DIR.name]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("❌ Erreur lors de la création du backup :")
        print(result.stderr)
        shutil.rmtree(folder, ignore_errors=True)
        return None

    print("✅ Archive créée.")
    _write_readme(folder, timestamp, pinned, label)
    print("📝 README créé.")

    return folder


def verify_backup(folder: Path) -> bool:
    """
    Vérifie qu'une archive dans un dossier de backup est valide et non vide.
    Retourne True si l'archive est saine.
    """
    archive = folder / "NicLink_backup.tar.gz"

    if not archive.exists():
        print(f"❌ Archive introuvable dans {folder}")
        return False

    size_mb = archive.stat().st_size / (1024 * 1024)
    if size_mb == 0:
        print("❌ Archive vide.")
        return False

    print(f"📁 Taille : {size_mb:.1f} Mo")

    result = subprocess.run(
        ["tar", "-tzf", str(archive)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("❌ Archive corrompue.")
        print(result.stderr)
        return False

    print("✅ Archive valide.")
    return True


def rotate_backups(max_backups: int = DEFAULT_MAX_BACKUPS, dry_run: bool = False) -> None:
    """
    Supprime les dossiers normaux les plus anciens si on dépasse max_backups.
    Les dossiers dans pinned/ ne sont JAMAIS touchés.
    """
    if not NORMAL_DIR.exists():
        return

    folders = sorted(
        [f for f in NORMAL_DIR.iterdir() if f.is_dir()],
        key=lambda f: f.stat().st_mtime,
    )

    to_delete = folders[: max(0, len(folders) - max_backups)]

    if not to_delete:
        print(f"🔄 Rotation : {len(folders)}/{max_backups} backups normaux — rien à supprimer.")
        return

    print(f"🔄 Rotation : {len(folders)} backups normaux, maximum {max_backups}.")
    print(f"   → {len(to_delete)} dossier(s) à supprimer :")

    for folder in to_delete:
        print(f"   🗑  {folder.name}")
        if not dry_run:
            shutil.rmtree(folder, ignore_errors=True)
        else:
            print("       [DRY-RUN] non supprimé.")


def list_backups() -> None:
    """Affiche la liste des backups, épinglés en premier."""
    pinned_folders = sorted(
        [f for f in PINNED_DIR.iterdir() if f.is_dir()],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    ) if PINNED_DIR.exists() else []

    normal_folders = sorted(
        [f for f in NORMAL_DIR.iterdir() if f.is_dir()],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    ) if NORMAL_DIR.exists() else []

    total = len(pinned_folders) + len(normal_folders)

    if total == 0:
        print(f"📭 Aucun backup trouvé dans {BACKUP_ROOT}")
        return

    print(f"\n📋 Backups dans {BACKUP_ROOT} ({total} au total) :\n")

    if pinned_folders:
        print(f"  📌 Épinglés ({len(pinned_folders)}) — jamais supprimés automatiquement :")
        for folder in pinned_folders:
            _print_folder_line(folder)
        print()

    if normal_folders:
        print(f"  🔄 Normaux ({len(normal_folders)}) — rotation automatique :")
        for folder in normal_folders:
            _print_folder_line(folder)
    print()


def pin_existing(folder_name: str, dry_run: bool = False) -> None:
    """
    Déplace un dossier de normal/ vers pinned/ en ajoutant 📌_ au nom.
    """
    src = NORMAL_DIR / folder_name
    if not src.exists():
        print(f"❌ Dossier introuvable : {src}")
        return

    new_name = f"📌_{folder_name}"
    dst = PINNED_DIR / new_name

    print(f"📌 Épinglage : {src.name} → {new_name}")
    if not dry_run:
        PINNED_DIR.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        readme = dst / "README.txt"
        if readme.exists():
            content = readme.read_text(encoding="utf-8")
            content = content.replace(
                "Épinglé     : Non",
                "Épinglé     : Oui — jamais supprimé automatiquement",
            )
            readme.write_text(content, encoding="utf-8")
        print("✅ Backup épinglé.")
    else:
        print("   [DRY-RUN] Aucun dossier déplacé.")


def unpin(folder_name: str, dry_run: bool = False) -> None:
    """
    Déplace un dossier de pinned/ vers normal/ en retirant 📌_ du nom.
    Il redevient éligible à la rotation automatique.
    """
    src = PINNED_DIR / folder_name
    if not src.exists():
        print(f"❌ Dossier introuvable : {src}")
        return

    new_name = folder_name.replace("📌_", "", 1)
    dst = NORMAL_DIR / new_name

    print(f"🔓 Désépinglage : {src.name} → {new_name}")
    if not dry_run:
        NORMAL_DIR.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        readme = dst / "README.txt"
        if readme.exists():
            content = readme.read_text(encoding="utf-8")
            content = content.replace(
                "Épinglé     : Oui — jamais supprimé automatiquement",
                "Épinglé     : Non",
            )
            readme.write_text(content, encoding="utf-8")
        print("✅ Backup désépinglé — éligible à la rotation.")
    else:
        print("   [DRY-RUN] Aucun dossier déplacé.")


# ──────────────────────────────────────────────
# Fonction principale (appelée depuis d'autres modules)
# ──────────────────────────────────────────────

def run_backup(
    max_backups: int = DEFAULT_MAX_BACKUPS,
    pinned: bool = False,
    label: str = "",
    dry_run: bool = False,
) -> Path | None:
    """
    Point d'entrée principal : crée un backup, le vérifie, fait la rotation.

    pinned=True  → backup épinglé, jamais supprimé par la rotation.
    label        → note libre, apparaît dans le nom du dossier et le README.
    Retourne le chemin du dossier créé ou None.
    """
    print("\n" + "═" * 50)
    print("  NicLink — Sauvegarde du projet")
    print("═" * 50)

    folder = create_backup(pinned=pinned, label=label, dry_run=dry_run)

    if folder:
        print("\n🔍 Vérification...")
        verify_backup(folder)

    print()
    rotate_backups(max_backups=max_backups, dry_run=dry_run)
    list_backups()

    print("═" * 50 + "\n")
    return folder


# ──────────────────────────────────────────────
# Point d'entrée CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gestionnaire de sauvegardes NicLink",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  backup normal      : python -m nicsoft.utils.backup_manager
  backup épinglé     : python -m nicsoft.utils.backup_manager --pin --label "menus stables"
  simuler            : python -m nicsoft.utils.backup_manager --dry-run
  lister             : python -m nicsoft.utils.backup_manager --list
  épingler existant  : python -m nicsoft.utils.backup_manager --pin-existing 2026-03-20_18-00-00
  désépingler        : python -m nicsoft.utils.backup_manager --unpin "📌_2026-03-20_14-00-00_menus-stables"
        """,
    )
    parser.add_argument("--pin", action="store_true",
                        help="Crée un backup épinglé (jamais supprimé par la rotation)")
    parser.add_argument("--label", type=str, default="",
                        help='Note libre, ex: "menus stables"')
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule sans rien créer ni supprimer")
    parser.add_argument("--max-backups", type=int, default=DEFAULT_MAX_BACKUPS,
                        help=f"Nombre max de backups normaux (défaut : {DEFAULT_MAX_BACKUPS})")
    parser.add_argument("--list", action="store_true",
                        help="Liste les backups existants et quitte")
    parser.add_argument("--pin-existing", metavar="DOSSIER",
                        help="Épingle un backup normal existant (nom du dossier dans normal/)")
    parser.add_argument("--unpin", metavar="DOSSIER",
                        help="Désépingle un backup (nom du dossier dans pinned/)")
    args = parser.parse_args()

    if args.list:
        list_backups()
        return

    if args.pin_existing:
        pin_existing(args.pin_existing, dry_run=args.dry_run)
        return

    if args.unpin:
        unpin(args.unpin, dry_run=args.dry_run)
        return

    run_backup(
        max_backups=args.max_backups,
        pinned=args.pin,
        label=args.label,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
