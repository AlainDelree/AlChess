"""
nicsoft/tests/test_issue317_lichess_corrections.py — AlChess

Issue #317 — essai réel d'Alain avec les blancs :

1. L'écran d'attente du premier coup (#316) affichait un panneau
   explicatif de trois phrases — pas assez visible, Alain n'a pas pensé à
   le lire et a cru l'écran bloqué. Remplacé par un message court, grand,
   sur une carte de couleur différente (verte) de celle de l'écran "Position
   incorrecte" voisin (bleue) — contraste évident au premier coup d'œil.
2. Une relance faite quelques secondes après un retour au menu depuis cet
   écran échouait avec "échiquier non détecté" alors qu'une relance plus
   tardive fonctionnait. Un seul essai d'ouverture était fait
   (create_board() dans _run_lichess) ; _open_board_with_retry() (nouveau)
   retente pendant quelques secondes avant d'abandonner.
3. Si l'ouverture échoue malgré les essais, l'erreur doit rester visible
   (toast "toast.board_not_found" existant, inchangé) plutôt que de
   revenir silencieusement au menu.

Entièrement sans réseau (faux transport/client, voir test_issue309) et sans
matériel (faux plateau, faux create_board) — driver.py n'est jamais modifié
ni mocké à un niveau plus bas que nécessaire.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.lichess import _open_board_with_retry
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.errors import LichessAuthError
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / "nicsoft" / "web" / "static" / "app.js"
INDEX_HTML = REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html"
CSS = REPO_ROOT / "nicsoft" / "web" / "static" / "css" / "main.css"


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ═══════════════════════════════════════════════════════════════════════
# 1. Écran d'attente du premier coup — message court, carte de couleur
#    distincte de l'écran "Position incorrecte"
# ═══════════════════════════════════════════════════════════════════════

def _wait_first_move_screen_body() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(
        r'<div id="screen-lichess-wait-first-move".*?</div>\s*<!-- ── Lichess : fin',
        html, re.DOTALL,
    )
    assert m, "écran d'attente du premier coup introuvable (balise ou structure modifiée ?)"
    return m.group(0)


def test_ecran_pret_a_jouer_est_court_et_sur_une_carte_distincte():
    body = _wait_first_move_screen_body()
    # Carte dédiée ("prêt à jouer"), pas la carte neutre partagée par les
    # autres écrans — changement de couleur immédiatement visible.
    assert 'class="card card-lichess-ready"' in body
    # Plus de panneau explicatif de plusieurs phrases ni de spinner
    # d'attente passive : un seul message, visible, une seule classe.
    assert "pos-init-texte" not in body
    assert "pos-init-attente" not in body
    assert "pos-init-spinner" not in body
    assert body.count('class="lichess-ready-message"') == 1
    # Toujours l'échiquier et le bouton de retour au menu.
    assert 'id="board-lichess-wait-first-move"' in body
    assert 'data-action="back_menu"' in body
    assert 'id="lichess-wait-board-lost-firstmove"' in body


def test_ecran_position_incorrecte_reste_sur_la_carte_neutre():
    """L'écran de mise en place (#316, "Position incorrecte") ne doit pas
    porter le style "prêt à jouer" — c'est le contraste entre les deux
    écrans qui doit signaler le changement d'état, pas une couleur unique
    réutilisée partout."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(r'<div id="screen-pos-init".*?</div>\s*<!-- ── Écran Exercices', html, re.DOTALL)
    assert m
    assert "card-lichess-ready" not in m.group(0)


def test_css_carte_pret_a_jouer_definit_une_couleur_differente():
    css = CSS.read_text(encoding="utf-8")
    assert ".card-lichess-ready" in css
    assert ".lichess-ready-message" in css


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_i18n_message_pret_a_jouer_court_non_vide(locale):
    path = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    titre = data.get("lichess.attente_premier_coup.titre")
    message = data.get("lichess.attente_premier_coup.en_attente")
    assert titre and message
    # "Une seule phrase, pas de paragraphe" (issue #317, point 1) : pas de
    # multiples points ni de retour à la ligne HTML dans le message affiché.
    assert "<br>" not in message
    assert message.count(".") <= 1
    assert len(message) < 80


@pytest.mark.skipif(not _node_available(), reason="binaire `node` absent de l'environnement")
def test_appjs_bascule_toujours_vers_lichess_wait_first_move():
    """Le câblage app.js généralisé par #316 (construction/rendu de
    l'échiquier de cet écran) n'a pas été touché par #317 — seul le
    contenu HTML du panneau a changé."""
    src = APP_JS.read_text(encoding="utf-8")
    assert 'data.state === "lichess_wait_first_move"' in src
    assert '_buildBoardPosInit(false, "board-lichess-wait-first-move", "lwfm")' in src


# ═══════════════════════════════════════════════════════════════════════
# 2. Relance rapide après libération — réessai d'ouverture de l'échiquier
# ═══════════════════════════════════════════════════════════════════════

def test_open_board_with_retry_reussit_apres_deux_echecs(monkeypatch):
    """Essai réel d'Alain : la première ouverture après une libération
    récente échoue avec "board connection error." — un second ou troisième
    essai, quelques secondes plus tard, doit réussir sans jamais relancer
    deux ouvertures USB en même temps (un seul appel à create_board() en
    vol à la fois, par construction : la boucle est séquentielle)."""
    monkeypatch.setattr(lichess_launcher, "_BOARD_OPEN_RETRY_INTERVAL_S", 0.0)
    calls = []

    def fake_create_board(**kw):
        calls.append(kw)
        if len(calls) < 3:
            raise SystemExit("board connection error.")
        return FakeBoard()

    monkeypatch.setattr(lichess_launcher, "create_board", fake_create_board)
    result = _open_board_with_retry("NicLink_lichess")
    assert isinstance(result, FakeBoard)
    assert len(calls) == 3
    # Jamais un appel concurrent : create_board() n'est rappelé qu'après le
    # retour (succès ou échec) du précédent.


def test_open_board_with_retry_abandonne_apres_le_delai_total(monkeypatch):
    """Si l'échiquier est réellement absent, l'abandon doit rester
    explicite (SystemExit propagée, jamais avalée) — c'est ce que
    _run_lichess sait déjà traduire en message visible (issue #317,
    point 3)."""
    monkeypatch.setattr(lichess_launcher, "_BOARD_OPEN_RETRY_INTERVAL_S", 0.0)
    monkeypatch.setattr(lichess_launcher, "_BOARD_OPEN_RETRY_TOTAL_S", 0.0)
    calls = []

    def fake_create_board(**kw):
        calls.append(kw)
        raise SystemExit("board connection error.")

    monkeypatch.setattr(lichess_launcher, "create_board", fake_create_board)
    with pytest.raises(SystemExit, match="board connection error"):
        _open_board_with_retry("NicLink_lichess")
    assert len(calls) >= 1


def test_open_board_with_retry_ne_retente_pas_une_autre_cause_systemexit(monkeypatch):
    """Seul "board connection error." déclenche un réessai — toute autre
    cause de SystemExit (si jamais introduite ailleurs) doit remonter
    immédiatement, sans délai ni essai supplémentaire."""
    calls = []

    def fake_create_board(**kw):
        calls.append(kw)
        raise SystemExit("autre cause inattendue")

    monkeypatch.setattr(lichess_launcher, "create_board", fake_create_board)
    with pytest.raises(SystemExit, match="autre cause inattendue"):
        _open_board_with_retry("NicLink_lichess")
    assert len(calls) == 1


def test_run_lichess_relance_reussie_apres_un_echec_transitoire(monkeypatch):
    """Bout en bout côté lanceur : _run_lichess ne doit plus abandonner au
    premier échec d'ouverture si create_board() réussit avant la fin de la
    fenêtre de réessai — plus d'erreur "échiquier non détecté" ni de retour
    au menu dans ce cas, comme l'attendait Alain lors de relances faites
    quelques secondes après un retour au menu."""
    monkeypatch.setattr(lichess_launcher, "_BOARD_OPEN_RETRY_INTERVAL_S", 0.0)
    calls = []

    def fake_create_board(**kw):
        calls.append(kw)
        if len(calls) < 2:
            raise SystemExit("board connection error.")
        return FakeBoard()

    monkeypatch.setattr(lichess_launcher, "create_board", fake_create_board)

    class _FakeClient:
        def __init__(self, token, transport=None):
            pass

        def create_ai_game(self, **kwargs):
            raise LichessAuthError(401)

    monkeypatch.setattr(lichess_launcher, "GameClient", _FakeClient)
    monkeypatch.setattr(lichess_launcher, "_wait_initial_position_lichess", lambda nl_inst, color: None)
    monkeypatch.setattr(lichess_launcher, "set_nl_inst_ref", lambda nl_inst: None)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)
    # L'erreur rencontrée est celle de create_ai_game() (après l'ouverture
    # réussie de l'échiquier au second essai) — jamais "board_not_found".
    assert len(calls) == 2
    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.lichess_invalid_token"


def test_run_lichess_echec_definitif_reste_annonce_par_un_toast(monkeypatch):
    """Si l'échiquier reste introuvable malgré les réessais, _run_lichess
    doit toujours produire le toast "échiquier non détecté" existant —
    jamais de retour silencieux au menu (issue #317, point 3)."""
    monkeypatch.setattr(lichess_launcher, "_BOARD_OPEN_RETRY_INTERVAL_S", 0.0)
    monkeypatch.setattr(lichess_launcher, "_BOARD_OPEN_RETRY_TOTAL_S", 0.0)

    def fake_create_board(**kw):
        raise SystemExit("board connection error.")

    monkeypatch.setattr(lichess_launcher, "create_board", fake_create_board)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)

    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: events.append((etype, data)))

    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess("lip_x", 1, 900, 10, "black", "15+10", "Alain", _error)
    assert _error["occurred"] is True
    assert _error["toast_key"] == "toast.board_not_found"
    board_error_events = [d for (etype, d) in events if etype == "board_error"]
    assert board_error_events and board_error_events[-1]["message"]
