"""
nicsoft/tests/e2e/test_issue389_puzzle_theme_sort_e2e.py — AlChess

Issue #389, point 1 : tri de la liste déroulante des thèmes des problèmes
Lichess — thèmes jamais joués en tête (ordre alphabétique du libellé),
puis les autres par performance croissante (égalité -> taux de réussite du
1er coup le plus bas -> ordre alphabétique). Fonction PURE
`_lichessPuzzleSortThemeKeys` (app.js) testée directement via
`page.evaluate` (aucun accès DOM dans la fonction elle-même), puis
vérification de son utilisation réelle par `_lichessPuzzleRenderThemeOptions`
sur l'écran de réglages (ordre des <option>, sélection utilisateur jamais
perdue à la reconstruction).

Sans réseau ni échiquier réel (serveur de test ALCHESS_SKIP_BOARD=1, jeton
toujours vide — voir conftest.py) : le tableau de bord est simulé en
invoquant directement le callback socket.io "lichess_puzzle_dashboard",
détaché du vrai serveur de test pour la durée de ce module (même procédé
que test_issue368_lichess_network_e2e.py) pour ne jamais être écrasé par
la vraie réponse (toujours `available: False` ici, jeton vide)."""
import pytest

pytestmark = pytest.mark.slow


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const attaches = socket.listeners(event) || []; "
        "const cbs = attaches.length ? attaches : (window['__real389_' + event] || []); "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


@pytest.fixture(scope="module", autouse=True)
def _detacher_dashboard_et_config_data_reels(page):
    """Détache "lichess_puzzle_dashboard" ET "config_data" pour toute la
    durée de ce module (même procédé que test_issue368_lichess_network_e2e.py)
    — le vrai serveur de test répond réellement à "config_get" (émis par
    app.js dès l'entrée sur config_lichess) ; sans ce détachement, cette
    réponse réelle réinitialiserait `_lichessPuzzleThemeTouchedByUser` à un
    moment non déterministe et casserait la vérification de persistance de
    la sélection utilisateur (comportement voulu par ailleurs, juste hors
    de portée de ce test)."""
    page.evaluate(
        "() => { "
        "['lichess_puzzle_dashboard', 'config_data'].forEach((ev) => { "
        "window['__real389_' + ev] = socket.listeners(ev).slice(); "
        "socket.off(ev); "
        "}); "
        "}"
    )
    yield
    page.evaluate(
        "() => { "
        "['lichess_puzzle_dashboard', 'config_data'].forEach((ev) => { "
        "(window['__real389_' + ev] || []).forEach((cb) => socket.on(ev, cb)); "
        "delete window['__real389_' + ev]; "
        "}); "
        "}"
    )


def go_menu(page):
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


@pytest.fixture
def at_config_lichess(at_menu):
    page = at_menu
    page.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    page.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    # config_data réel détaché (voir _detacher_dashboard_et_config_data_reels
    # ci-dessus) — réponse simulée déterministe à la place, comme à une
    # ouverture normale de l'écran sans réglage mémorisé.
    _declencher_evenement_socket_client(page, "config_data", {
        "lichess_puzzle_series_mode": "mix", "lichess_puzzle_theme": "", "lichess_puzzle_phase": "middlegame",
    })
    yield page
    go_menu(page)


# ═══════════════════════════════════════════════════════════════════════
# 1. _lichessPuzzleSortThemeKeys — fonction pure, aucun DOM/socket impliqué.
# ═══════════════════════════════════════════════════════════════════════

def test_tri_jamais_joues_en_tete_puis_performance_croissante(page):
    result = page.evaluate(
        """() => _lichessPuzzleSortThemeKeys(
            ['fork', 'pin', 'skewer', 'mate'],
            {
              'fork': {nb: 20, performance: 1500, first_wins: 10},
              'pin': {nb: 5, performance: 1400, first_wins: 2},
            },
            (key) => key,
        )"""
    )
    # "skewer"/"mate" jamais joués -> alphabétique en tête ; "pin" (1400) puis
    # "fork" (1500) -> performance croissante.
    assert result == ["mate", "skewer", "pin", "fork"]


def test_tri_egalite_de_performance_departagee_par_taux_1er_coup_puis_alpha(page):
    result = page.evaluate(
        """() => _lichessPuzzleSortThemeKeys(
            ['alpha', 'beta', 'gamma'],
            {
              'alpha': {nb: 10, performance: 1500, first_wins: 8},   // taux 0.8
              'beta': {nb: 10, performance: 1500, first_wins: 3},    // taux 0.3 -> avant alpha
              'gamma': {nb: 10, performance: 1500, first_wins: 3},   // taux 0.3, égalité -> alpha avant gamma
            },
            (key) => key,
        )"""
    )
    # "beta"/"gamma" à égalité (performance et taux) -> alphabétique entre
    # eux ; "alpha" (taux plus haut, donc meilleur) passe en dernier.
    assert result == ["beta", "gamma", "alpha"]


def test_tri_tableau_de_bord_vide_est_entierement_alphabetique(page):
    # Issue #393, point 1 (établi par #391) : "disponible mais vide" (aucun
    # thème joué sur la période) et "indisponible" (jeton/réseau/droit en
    # cause) produisent le MÊME ordre ici — _lichessPuzzleSortThemeKeys ne
    # trie QUE sur les statistiques par thème (absentes dans les deux cas),
    # jamais sur la disponibilité elle-même. Les deux cas restent bien
    # DISTINCTS à l'affichage (libellé, voir
    # test_issue393_point1_lichess_dashboard_indisponible_e2e.py) : c'est
    # _lichessPuzzleRenderThemeOptions, pas le tri, qui porte cette
    # distinction.
    result = page.evaluate(
        """() => _lichessPuzzleSortThemeKeys(['zugzwang', 'fork', 'mate'], {}, (key) => key)"""
    )
    assert result == ["fork", "mate", "zugzwang"]


def test_tri_tableau_de_bord_indisponible_est_entierement_alphabetique(page):
    # Voir le commentaire du test ci-dessus — même ordre que le cas
    # "disponible mais vide", par construction (aucune statistique connue
    # dans les deux cas pour le tri lui-même).
    result = page.evaluate(
        """() => _lichessPuzzleSortThemeKeys(['zugzwang', 'fork', 'mate'], null, (key) => key)"""
    )
    assert result == ["fork", "mate", "zugzwang"]


def test_tri_peu_joue_classe_par_performance_comme_les_autres(page):
    """Un thème "peu joué" (nb < seuil, ici nb=3) reste dans le groupe
    "joué", classé par performance comme les thèmes normaux — seule
    l'annotation affichée (pas le tri) distingue "peu joué"."""
    result = page.evaluate(
        """() => _lichessPuzzleSortThemeKeys(
            ['fork', 'pin'],
            {
              'fork': {nb: 3, performance: 1300, first_wins: 1},
              'pin': {nb: 20, performance: 1600, first_wins: 10},
            },
            (key) => key,
        )"""
    )
    assert result == ["fork", "pin"]


def test_tri_utilise_le_libelle_fourni_pour_lordre_alphabetique(page):
    """labelFn fournit le libellé dans la langue courante — le tri
    alphabétique porte sur CE libellé, jamais sur la clé brute."""
    result = page.evaluate(
        """() => _lichessPuzzleSortThemeKeys(
            ['fork', 'pin'],
            {},
            (key) => (key === 'fork' ? 'Zèbre' : 'Avant'),
        )"""
    )
    assert result == ["pin", "fork"]  # "Avant" < "Zèbre"


# ═══════════════════════════════════════════════════════════════════════
# 2. _lichessPuzzleThemeLabel — thème/phase connus traduits, clé inconnue
#    affichée telle quelle (jamais d'erreur).
# ═══════════════════════════════════════════════════════════════════════

def test_theme_label_connu_egale_la_traduction_officielle(page):
    assert page.evaluate("() => _lichessPuzzleThemeLabel('pin')") == page.evaluate(
        "() => t('lichess.puzzle_theme.pin')"
    )


def test_phase_label_connue_egale_la_traduction_officielle(page):
    assert page.evaluate("() => _lichessPuzzleThemeLabel('endgame')") == page.evaluate(
        "() => t('lichess.puzzle_phase.endgame')"
    )


def test_cle_inconnue_affichee_telle_quelle_sans_erreur(page):
    assert page.evaluate("() => _lichessPuzzleThemeLabel('uneCleInventeeParLichess')") == (
        "uneCleInventeeParLichess"
    )


# ═══════════════════════════════════════════════════════════════════════
# 3. Intégration : ordre réel des <option> de l'écran de réglages, et
#    sélection utilisateur jamais perdue à la reconstruction de la liste.
# ═══════════════════════════════════════════════════════════════════════

def _option_values(page):
    return page.eval_on_selector_all(
        "#cfg-lichess-puzzle-theme option", "opts => opts.map(o => o.value)"
    )


def test_ordre_reel_des_options_reflete_le_tri(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": True,
        "themes": {
            "fork": {"nb": 20, "performance": 1550, "first_wins": 10},
            "pin": {"nb": 15, "performance": 1400, "first_wins": 5},
        },
        "default_theme": "pin",
    })
    values = _option_values(page)
    assert values[0] not in ("fork", "pin")  # un thème jamais joué d'abord
    assert values.index("pin") < values.index("fork")  # performance croissante


def test_selection_utilisateur_survit_a_la_reconstruction_de_la_liste(at_config_lichess):
    page = at_config_lichess
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": True, "themes": {}, "default_theme": "",
    })
    page.eval_on_selector("#cfg-lichess-puzzle-theme", "(sel) => { sel.value = 'skewer'; }")
    page.evaluate("() => lichessSavePuzzleTheme()")
    assert page.eval_on_selector("#cfg-lichess-puzzle-theme", "sel => sel.value") == "skewer"
    # Arrivée tardive d'un nouveau tableau de bord — la liste est
    # entièrement reconstruite (issue #389) : la sélection de l'utilisateur
    # ne doit jamais être écrasée.
    _declencher_evenement_socket_client(page, "lichess_puzzle_dashboard", {
        "available": True,
        "themes": {"fork": {"nb": 50, "performance": 1200, "first_wins": 1}},
        "default_theme": "fork",
    })
    assert page.eval_on_selector("#cfg-lichess-puzzle-theme", "sel => sel.value") == "skewer"
