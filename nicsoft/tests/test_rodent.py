"""
Tests backend Rodent IV (issue #13a).

Vérifie :
  - les constantes de défaut (Personality=Tal, Elo=1200) ;
  - que le moteur répond au handshake UCI avant d'être déclaré disponible ;
  - que l'ordre des setoption (Personality → LimitStrength → Elo) est appliqué
    et que le moteur joue effectivement un coup.

Les tests nécessitant le binaire sont automatiquement ignorés (skip) s'il est
absent, pour ne pas casser la CI sur une machine sans Rodent installé.
"""

import hashlib
import pathlib
import socket
import urllib.error
from unittest.mock import patch

import chess
import pytest

from nicsoft.engine.engine_manager import (
    find_rodent,
    rodent_available,
    RODENT_PERSONALITIES,
    RODENT_PERSONALITY_DEFAUT,
    RODENT_ELO_DEFAUT,
)
from nicsoft.web.server import (
    _telecharger_fichier_rodent,
    _telecharger_et_installer_rodent,
    _installer_rodent_depuis_temp,
    _nettoyer_dossier_temp_rodent,
    _RODENT_WIN_SHA256,
    _RODENT_WIN_FILES,
)

_RODENT_ABSENT = find_rodent() is None
_skip_no_rodent = pytest.mark.skipif(_RODENT_ABSENT, reason="binaire Rodent IV absent")


def test_rodent_defauts_constants():
    """Les défauts backend correspondent à la spécification de l'issue #13a."""
    assert RODENT_PERSONALITY_DEFAUT == "Tal"
    assert RODENT_PERSONALITY_DEFAUT in RODENT_PERSONALITIES
    assert RODENT_ELO_DEFAUT == 1200


def test_config_json_contient_defauts_rodent():
    """data/config.json expose les clés Rodent avec les bons défauts."""
    import json
    from nicsoft.config import DATA_DIR

    cfg_path = DATA_DIR / "config.json"
    if not cfg_path.exists():
        pytest.skip("config.json absent")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg.get("rodent_personality") == "Tal"
    assert cfg.get("rodent_elo") == 1200


@_skip_no_rodent
def test_rodent_repond_au_handshake_uci():
    """Rodent complète uci/isready et expose ses options → considéré disponible."""
    assert rodent_available() is True


@_skip_no_rodent
def test_rodent_setoption_ordre_et_joue():
    """
    Instancie RodentEngine (ordre Personality → LimitStrength → Elo garanti par
    _apply_rodent_options) et vérifie qu'il joue un coup légal.
    """
    from nicsoft.engine.engine_manager import RodentEngine, find_stockfish

    eng = RodentEngine(
        find_rodent(),
        personality="Tal",
        rodent_elo=1200,
        stockfish_path=find_stockfish(),
    )
    try:
        assert eng.personality == "Tal"
        assert eng.engine_elo == 1200
        board = chess.Board()
        move = eng.get_move(board, think_time=0.2)
        assert move is not None
        assert move in board.legal_moves
    finally:
        eng.quit()


# ── Téléchargement Windows (issue #256) : délai d'attente + intégrité ──────────

def test_telecharger_fichier_rodent_delai_depasse(tmp_path):
    """Un serveur injoignable (délai dépassé) lève une erreur, sans fichier créé."""
    dest = tmp_path / "rodent-iv-x64.exe"
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError(socket.timeout("timed out")),
    ):
        with pytest.raises(urllib.error.URLError):
            _telecharger_fichier_rodent("https://example.invalid/rodent-iv-x64.exe", dest)
    assert not dest.exists()


def test_telecharger_fichier_rodent_empreinte_invalide(tmp_path):
    """Un contenu téléchargé dont l'empreinte ne correspond pas à la référence
    est supprimé et signalé en erreur — jamais installé."""
    dest = tmp_path / "rodent-iv-x64.exe"

    class _FakeResponse:
        def __init__(self, data):
            self._data = data

        def read(self, _n):
            data, self._data = self._data, b""
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("urllib.request.urlopen", return_value=_FakeResponse(b"contenu altere")):
        with pytest.raises(ValueError, match="[Ee]mpreinte"):
            _telecharger_fichier_rodent("https://example.invalid/rodent-iv-x64.exe", dest)
    assert not dest.exists()


def test_telecharger_fichier_rodent_sans_reference_connue(tmp_path):
    """Un nom de fichier sans empreinte de référence connue est refusé d'emblée,
    sans requête réseau (on ne doit jamais installer sans vérification possible)."""
    dest = tmp_path / "fichier-inconnu.dll"
    with patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(ValueError, match="[Aa]ucune empreinte"):
            _telecharger_fichier_rodent("https://example.invalid/fichier-inconnu.dll", dest)
    mock_urlopen.assert_not_called()
    assert not dest.exists()


def test_telecharger_fichier_rodent_empreinte_valide(tmp_path):
    """Un contenu dont l'empreinte correspond à la référence est accepté et écrit."""
    dest = tmp_path / "rodent-iv-x64.exe"
    # Contenu fabriqué pour matcher une référence de test dédiée (évite de
    # dépendre du vrai binaire, volumineux et non lisible dans ce test).
    contenu = b"binaire de test"
    import hashlib
    empreinte = hashlib.sha256(contenu).hexdigest()

    class _FakeResponse:
        def __init__(self, data):
            self._data = data

        def read(self, _n):
            data, self._data = self._data, b""
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch.dict(_RODENT_WIN_SHA256, {"rodent-iv-x64.exe": empreinte}):
        with patch("urllib.request.urlopen", return_value=_FakeResponse(contenu)):
            _telecharger_fichier_rodent("https://example.invalid/rodent-iv-x64.exe", dest)
    assert dest.read_bytes() == contenu


def test_telecharger_fichier_rodent_url_non_https_refusee(tmp_path):
    """Une adresse qui ne commence pas par https:// est refusée d'emblée,
    sans la moindre requête réseau (SEC-025, issue #286)."""
    dest = tmp_path / "rodent-iv-x64.exe"
    with patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(ValueError, match="https"):
            _telecharger_fichier_rodent("http://example.invalid/rodent-iv-x64.exe", dest)
    mock_urlopen.assert_not_called()
    assert not dest.exists()


# ── Installation tout-ou-rien (issue #286, SEC-025) ────────────────────────────
#
# `_telecharger_et_installer_rodent` ne dépend ni de la plateforme ni de
# SocketIO : on l'appelle directement avec des dossiers de test (jamais
# ENGINES_DIR), ce qui permet de tester toute la logique de téléchargement et
# de mise en place sur une machine Linux de CI.

class _FakeResponse:
    """Simule une réponse HTTP dont tout le contenu est lu au premier appel."""

    def __init__(self, data):
        self._data = data

    def read(self, _n):
        data, self._data = self._data, b""
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FlakyResponse:
    """Simule une connexion coupée en cours de lecture : les morceaux listés
    sont renvoyés un par un, un morceau `None` levant une coupure réseau."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, _n):
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if chunk is None:
            raise ConnectionError("connexion perdue en cours de lecture")
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _empreintes_et_reponses(contenus):
    """Construit le dict d'empreintes de référence et la liste de réponses
    factices pour un mapping {nom_fichier: contenu}."""
    empreintes = {nom: hashlib.sha256(contenu).hexdigest() for nom, contenu in contenus.items()}
    reponses = [_FakeResponse(contenus[nom]) for nom in _RODENT_WIN_FILES]
    return empreintes, reponses


def test_telecharger_et_installer_rodent_succes_complet(tmp_path):
    """Les trois fichiers téléchargés et vérifiés sont mis en place dans le
    dossier définitif, et le dossier temporaire ne subsiste pas."""
    dest_dir = tmp_path / "rodent-iv-win"
    tmp_dir = tmp_path / "rodent-iv-win.tmp"
    contenus = {nom: f"contenu-{nom}".encode() for nom in _RODENT_WIN_FILES}
    empreintes, reponses = _empreintes_et_reponses(contenus)

    progress = []
    with patch.dict(_RODENT_WIN_SHA256, empreintes):
        with patch("urllib.request.urlopen", side_effect=reponses):
            _telecharger_et_installer_rodent(
                dest_dir, tmp_dir,
                on_progress=lambda index, total, filename: progress.append((index, total, filename)),
            )

    assert not tmp_dir.exists()
    for nom in _RODENT_WIN_FILES:
        assert (dest_dir / nom).read_bytes() == contenus[nom]
    assert progress == [(i, len(_RODENT_WIN_FILES), nom) for i, nom in enumerate(_RODENT_WIN_FILES, start=1)]


def test_telecharger_et_installer_rodent_empreinte_invalide_troisieme_fichier(tmp_path):
    """Une empreinte invalide sur le dernier fichier ne doit rien laisser dans
    le dossier définitif (installation tout-ou-rien)."""
    dest_dir = tmp_path / "rodent-iv-win"
    tmp_dir = tmp_path / "rodent-iv-win.tmp"
    contenus = {nom: f"contenu-{nom}".encode() for nom in _RODENT_WIN_FILES}
    empreintes, reponses = _empreintes_et_reponses(contenus)
    # Référence falsifiée pour le troisième fichier → échec d'empreinte.
    empreintes[_RODENT_WIN_FILES[2]] = "0" * 64

    with patch.dict(_RODENT_WIN_SHA256, empreintes):
        with patch("urllib.request.urlopen", side_effect=reponses):
            with pytest.raises(ValueError, match="[Ee]mpreinte"):
                _telecharger_et_installer_rodent(dest_dir, tmp_dir)

    assert not tmp_dir.exists()
    assert not dest_dir.exists()


def test_telecharger_et_installer_rodent_interruption_deuxieme_fichier(tmp_path):
    """Une coupure réseau en cours de lecture du deuxième fichier ne laisse
    aucun fichier tronqué, ni dans le dossier temporaire ni dans le définitif."""
    dest_dir = tmp_path / "rodent-iv-win"
    tmp_dir = tmp_path / "rodent-iv-win.tmp"
    contenu_1 = f"contenu-{_RODENT_WIN_FILES[0]}".encode()
    empreintes = {_RODENT_WIN_FILES[0]: hashlib.sha256(contenu_1).hexdigest()}
    reponses = [
        _FakeResponse(contenu_1),
        _FlakyResponse([b"partie-tronquee", None]),
    ]

    with patch.dict(_RODENT_WIN_SHA256, empreintes):
        with patch("urllib.request.urlopen", side_effect=reponses):
            with pytest.raises(ConnectionError):
                _telecharger_et_installer_rodent(dest_dir, tmp_dir)

    assert not tmp_dir.exists()
    assert not dest_dir.exists()


def test_telecharger_et_installer_rodent_echec_preserve_installation_existante(tmp_path):
    """Un échec de téléchargement alors qu'une installation valide existait
    déjà doit laisser les anciens fichiers strictement inchangés."""
    dest_dir = tmp_path / "rodent-iv-win"
    tmp_dir = tmp_path / "rodent-iv-win.tmp"
    dest_dir.mkdir(parents=True)
    anciens_contenus = {nom: f"ancien-{nom}".encode() for nom in _RODENT_WIN_FILES}
    for nom, contenu in anciens_contenus.items():
        (dest_dir / nom).write_bytes(contenu)

    nouveaux_contenus = {nom: f"nouveau-{nom}".encode() for nom in _RODENT_WIN_FILES}
    empreintes, reponses = _empreintes_et_reponses(nouveaux_contenus)
    # Référence falsifiée pour le dernier fichier → la mise en place échoue.
    empreintes[_RODENT_WIN_FILES[-1]] = "0" * 64

    with patch.dict(_RODENT_WIN_SHA256, empreintes):
        with patch("urllib.request.urlopen", side_effect=reponses):
            with pytest.raises(ValueError, match="[Ee]mpreinte"):
                _telecharger_et_installer_rodent(dest_dir, tmp_dir)

    assert not tmp_dir.exists()
    assert not (dest_dir.parent / (dest_dir.name + ".bak")).exists()
    for nom, contenu in anciens_contenus.items():
        assert (dest_dir / nom).read_bytes() == contenu


def test_telecharger_et_installer_rodent_nettoie_residu_arret_brutal(tmp_path):
    """Un dossier temporaire laissé par un arrêt brutal précédent est nettoyé
    avant une nouvelle tentative, et ne contamine pas la mise en place."""
    dest_dir = tmp_path / "rodent-iv-win"
    tmp_dir = tmp_path / "rodent-iv-win.tmp"
    tmp_dir.mkdir(parents=True)
    (tmp_dir / "residu-arret-brutal.tmp").write_bytes(b"debris")

    contenus = {nom: f"contenu-{nom}".encode() for nom in _RODENT_WIN_FILES}
    empreintes, reponses = _empreintes_et_reponses(contenus)

    with patch.dict(_RODENT_WIN_SHA256, empreintes):
        with patch("urllib.request.urlopen", side_effect=reponses):
            _telecharger_et_installer_rodent(dest_dir, tmp_dir)

    assert not tmp_dir.exists()
    assert not (dest_dir / "residu-arret-brutal.tmp").exists()
    for nom in _RODENT_WIN_FILES:
        assert (dest_dir / nom).read_bytes() == contenus[nom]


def test_installer_rodent_depuis_temp_restaure_si_swap_final_echoue(tmp_path, monkeypatch):
    """Si la bascule finale échoue (ex. fichier verrouillé par le moteur en
    cours d'exécution), l'installation existante doit être restaurée à
    l'identique et l'erreur propagée — rien de perdu, rien de partiel."""
    dest_dir = tmp_path / "rodent-iv-win"
    tmp_dir = tmp_path / "rodent-iv-win.tmp"
    dest_dir.mkdir(parents=True)
    (dest_dir / "rodent-iv-x64.exe").write_bytes(b"ancien-exe")
    tmp_dir.mkdir(parents=True)
    (tmp_dir / "rodent-iv-x64.exe").write_bytes(b"nouveau-exe")

    import nicsoft.web.server as server_module
    original_replace = server_module.os.replace
    appels = []

    def replace_qui_echoue_sur_tmp(src, dst):
        appels.append((pathlib.Path(src).name, pathlib.Path(dst).name))
        if pathlib.Path(src) == tmp_dir:
            raise PermissionError("fichier verrouillé (moteur en cours d'exécution)")
        return original_replace(src, dst)

    monkeypatch.setattr(server_module.os, "replace", replace_qui_echoue_sur_tmp)

    with pytest.raises(PermissionError):
        _installer_rodent_depuis_temp(tmp_dir, dest_dir)

    assert dest_dir.exists()
    assert (dest_dir / "rodent-iv-x64.exe").read_bytes() == b"ancien-exe"
    assert not (dest_dir.parent / (dest_dir.name + ".bak")).exists()


def test_nettoyer_dossier_temp_rodent(tmp_path):
    """Supprime un dossier temporaire existant, et ne fait rien s'il est absent."""
    tmp_dir = tmp_path / "rodent-iv-win.tmp"
    tmp_dir.mkdir()
    (tmp_dir / "fichier.tmp").write_bytes(b"x")

    _nettoyer_dossier_temp_rodent(tmp_dir)
    assert not tmp_dir.exists()

    _nettoyer_dossier_temp_rodent(tmp_dir)  # idempotent, aucune exception
    assert not tmp_dir.exists()
