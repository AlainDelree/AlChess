"""
nicsoft/tests/e2e/test_issue344_lichess_rated_e2e.py — AlChess

Issue #344, point 1 : écran de choix de la partie Lichess — « Contre un
humain » présélectionné, case « Partie classée » cochée par défaut (sans
objet contre l'IA, où elle est masquée). Vérifié dans un vrai navigateur
(Playwright) car il s'agit d'un défaut d'affichage initial, pas d'une
valeur envoyée au serveur (couvert côté Python par
test_issue344_lichess_rated.py).

Aucune vraie recherche/partie Lichess : l'écran de configuration est atteint
comme dans test_issue310_lichess_e2e.py (sendAction direct, sans échiquier
ni jeton), jamais démarré.
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import _declencher_lichess_resumable

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module", autouse=True)
def _detacher_lichess_resumable_reel(page):
    """Détache, pour toute la durée de ce module, le vrai gestionnaire
    socket.io de "lichess_resumable" — voir
    test_issue310_lichess_e2e.py::_declencher_lichess_resumable pour la
    raison. RESTAURÉ à la fin (issue #373, même défaut que #372/#371
    corrigé pour d'autres fichiers e2e).

    Même garde `if (!window...)` que test_issue310_lichess_e2e.py : réutilise
    une référence déjà laissée par un fichier antérieur n'ayant pas restauré
    (ex. test_issue333_lichess_menu_banner_e2e.py, délibéré) plutôt que de la
    perdre en stashant un tableau vide."""
    page.evaluate(
        "() => { "
        "if (!window.__realLichessResumableHandlers) { "
        "window.__realLichessResumableHandlers = socket.listeners('lichess_resumable').slice(); "
        "} "
        "socket.off('lichess_resumable'); "
        "}"
    )
    yield
    page.evaluate(
        "() => { "
        "(window.__realLichessResumableHandlers || []).forEach((cb) => socket.on('lichess_resumable', cb)); "
        "delete window.__realLichessResumableHandlers; "
        "}"
    )


@pytest.fixture
def at_config_lichess_defaults(at_menu):
    """Comme `at_config_lichess` (test_issue310_lichess_e2e.py) mais SANS
    forcer `selectOpponentTypeLichess('ai')` — ici, on veut précisément
    observer les défauts réels de l'écran tels qu'app.js les pose."""
    at_menu.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    at_menu.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    # "lichess_resumable" est déjà détaché pour tout le module par
    # `_detacher_lichess_resumable_reel` ci-dessus.
    _declencher_lichess_resumable(at_menu, {"available": False, "games": []})
    return at_menu


def test_contre_un_humain_preselectionne(at_config_lichess_defaults):
    page = at_config_lichess_defaults
    assert "selected" in (page.locator("#cfg-lichess-opponent-human").get_attribute("class") or "")
    assert "selected" not in (page.locator("#cfg-lichess-opponent-ai").get_attribute("class") or "")


def test_contre_un_humain_affiche_a_gauche_de_contre_ia(at_config_lichess_defaults):
    """Issue #346 : « Contre un humain » (présélectionné) doit s'afficher à
    gauche de « Contre l'IA » dans la carte Adversaire."""
    page = at_config_lichess_defaults
    ids = page.evaluate(
        "() => Array.from(document.getElementById('cfg-lichess-opponent-human').parentElement.children).map(b => b.id)"
    )
    assert ids == ["cfg-lichess-opponent-human", "cfg-lichess-opponent-ai"]
    assert "selected" in (page.locator("#cfg-lichess-opponent-human").get_attribute("class") or "")


def test_case_classee_cochee_par_defaut_et_visible(at_config_lichess_defaults):
    page = at_config_lichess_defaults
    checkbox = page.locator("#cfg-lichess-rated")
    assert checkbox.is_checked()
    assert page.locator("#cfg-lichess-rated-row").is_visible()


def test_niveau_ia_masque_par_defaut(at_config_lichess_defaults):
    """Contre un humain (présélectionné) : la carte « Niveau de l'IA » n'a
    pas de sens et reste masquée."""
    page = at_config_lichess_defaults
    assert not page.locator("#cfg-lichess-niveau-card").is_visible()


def test_case_classee_masquee_contre_ia(at_config_lichess_defaults):
    """Issue #344, point 1 : la case n'a de sens que contre un humain —
    masquée dès qu'on bascule sur « Contre l'IA », case grisée (disabled)."""
    page = at_config_lichess_defaults
    page.evaluate("selectOpponentTypeLichess('ai')")
    assert not page.locator("#cfg-lichess-rated-row").is_visible()
    assert page.locator("#cfg-lichess-rated").is_disabled()


def test_case_classee_retablie_cochee_en_revenant_sur_humain(at_config_lichess_defaults):
    """« Rétablir la case quand on revient à Contre un humain » — même si
    l'utilisateur l'avait décochée avant de passer sur l'IA."""
    page = at_config_lichess_defaults
    checkbox = page.locator("#cfg-lichess-rated")
    checkbox.uncheck()
    assert not checkbox.is_checked()
    page.evaluate("selectOpponentTypeLichess('ai')")
    page.evaluate("selectOpponentTypeLichess('human')")
    assert checkbox.is_checked()
    assert page.locator("#cfg-lichess-rated-row").is_visible()


def test_bascule_ia_affiche_note_amicale_seulement(at_config_lichess_defaults):
    page = at_config_lichess_defaults
    assert not page.locator("#cfg-lichess-opponent-ai-note").is_visible()
    page.evaluate("selectOpponentTypeLichess('ai')")
    assert page.locator("#cfg-lichess-opponent-ai-note").is_visible()
