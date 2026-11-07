"""
Garde-fou sans réseau (issue #294) : tout fichier binaire suivi par git dans
engines/maia et engines/rodent-iv-win doit être cité (par son nom exact ou
par un motif de noms, ex. "maia-*.pb.gz") dans THIRD_PARTY_NOTICES.md, pour
qu'un futur binaire ajouté à ces dossiers ne reste jamais sans notice.
"""
import subprocess

from nicsoft.tests._arc001_discovery import REPO_ROOT

DOSSIERS_SURVEILLES = ["engines/maia", "engines/rodent-iv-win"]
NOTICE_PATH = REPO_ROOT / "THIRD_PARTY_NOTICES.md"


def _fichiers_binaires_suivis() -> list:
    """Fichiers suivis par git dans les dossiers surveillés, chemins relatifs
    posix (ex. "engines/maia/lc0"). Utilise git ls-files : pas de réseau,
    pas de dépendance au contenu binaire lui-même."""
    fichiers = []
    for dossier in DOSSIERS_SURVEILLES:
        try:
            resultat = subprocess.run(
                ["git", "ls-files", dossier],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            fichiers.extend(ligne for ligne in resultat.stdout.splitlines() if ligne)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Copie sans dépôt git (ex. copie propre du crochet de pre-push) :
            # la copie ne contient que les fichiers suivis, on liste donc le dossier.
            chemin = REPO_ROOT / dossier
            if chemin.is_dir():
                fichiers.extend(
                    f"{dossier}/{p.name}" for p in chemin.iterdir() if p.is_file()
                )
    return sorted(fichiers)


def _cite_dans_notice(nom_fichier: str, texte_notice: str) -> bool:
    """Un fichier est "cité" soit par son nom exact, soit par un motif de
    noms reconnaissable (ex. les neuf fichiers maia-NNNN.pb.gz couverts par
    un seul motif "maia-*.pb.gz" ou "maia-1100.pb.gz … maia-1900.pb.gz")."""
    if nom_fichier in texte_notice:
        return True
    if nom_fichier.startswith("maia-") and nom_fichier.endswith(".pb.gz"):
        return "maia-*.pb.gz" in texte_notice or "maia-" in texte_notice
    return False


_FICHIERS_BINAIRES = _fichiers_binaires_suivis()


def test_decouverte_couvre_les_binaires_connus():
    """Garde-fou (comme _arc001_discovery) : une découverte cassée (dossier
    renommé, git absent) ne doit jamais passer inaperçue en trouvant 0
    fichier."""
    assert len(_FICHIERS_BINAIRES) >= 10


def test_chaque_binaire_tiers_est_cite_dans_third_party_notices():
    assert NOTICE_PATH.is_file(), "THIRD_PARTY_NOTICES.md est introuvable à la racine du dépôt"
    texte_notice = NOTICE_PATH.read_text(encoding="utf-8")

    non_cites = [
        f for f in _FICHIERS_BINAIRES
        if not _cite_dans_notice(f.rsplit("/", 1)[-1], texte_notice)
    ]
    assert non_cites == [], (
        "Fichier(s) binaire(s) tiers non cité(s) dans THIRD_PARTY_NOTICES.md : "
        f"{non_cites}"
    )
