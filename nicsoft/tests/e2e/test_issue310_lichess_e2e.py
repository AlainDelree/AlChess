"""
nicsoft/tests/e2e/test_issue310_lichess_e2e.py — AlChess

Issue #310, point 9 : un test CSS statique (test_issue310_css_layout_guard.py)
a déjà été ajouté pour garantir que chaque écran basculé en "display: flex"
par app.js possède au moins une règle de mise en page CSS. Mais ce test ne
charge jamais la page dans un vrai navigateur — c'est exactement ce défaut-là
(règle CSS manquante pour #screen-config-lichess, contenu rejeté hors
fenêtre avec scrollbar horizontale) qui n'avait pas été détecté avant le
premier essai réel sur le matériel physique. Ce fichier ajoute le test e2e
Playwright manquant : charger la page pour de vrai et vérifier visuellement
que les éléments de configuration Lichess, puis les éléments de l'écran de
partie, sont bien visibles et dans la fenêtre (pas de défilement horizontal).

Aucun échiquier physique ni jeton Lichess n'est nécessaire : l'écran de
configuration est atteint via `sendAction({type: 'mode', value: 'lichess'})`
(alchess.py ne fait qu'un `set_app_state("config_lichess")` pour cette
action, cf. nicsoft/web/alchess.py ligne ~384 — aucune vérification
d'échiquier ou de jeton à ce stade). L'écran de partie est atteint sans
démarrer de vraie partie Lichess (qui nécessiterait une requête réseau) :
les événements socket "app_state" (state=playing) et "lichess_init" que le
serveur envoie normalement pendant une partie réelle sont simulés en
appelant directement, depuis Playwright, les callbacks déjà enregistrés par
`socket.on(...)` côté client — via la méthode `listeners()` exposée
publiquement par le client Socket.IO (composant Emitter dont hérite
`Socket`, cf. nicsoft/web/static/vendor/socket.io/socket.io.min.js). Cette
technique n'ajoute aucun crochet de test dans le code de production : elle
se contente d'invoquer, depuis le test, des fonctions déjà présentes et
déjà enregistrées par app.js lui-même.

Lancer : pytest nicsoft/tests/e2e/test_issue310_lichess_e2e.py -v
"""
import pytest

pytestmark = pytest.mark.slow


FEN_DEPART = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _dans_la_fenetre(page, selector):
    """True si l'élément `selector` est visible et entièrement contenu dans
    la largeur du viewport (ni x négatif, ni dépassement à droite) — c'est
    précisément ce que le bug de #310 violait (contenu poussé hors écran par
    une règle de mise en page manquante)."""
    loc = page.locator(selector)
    if not loc.is_visible():
        return False
    box = loc.bounding_box()
    if box is None:
        return False
    viewport = page.viewport_size
    return box["x"] >= 0 and (box["x"] + box["width"]) <= viewport["width"]


def _declencher_evenement_socket_client(page, event, data):
    """Invoque directement, côté navigateur, les callbacks déjà enregistrés
    par `socket.on(event, ...)` dans app.js — sans passer par le réseau ni
    par le serveur. Repose sur `Socket.prototype.listeners()`, méthode
    publique du client Socket.IO (héritée du composant Emitter), et non sur
    un quelconque crochet ajouté au code de production."""
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


@pytest.fixture
def at_config_lichess(at_menu):
    """Atteint l'écran de configuration Lichess sans dépendre de l'échiquier
    physique ni d'un jeton Lichess enregistré (le bouton menu correspondant
    est `disabled` tant que ces deux préconditions matérielles ne sont pas
    réunies — cf. app.js ligne ~697-702). `sendAction` est une fonction JS
    globale qui émet directement l'action vers le serveur (`socket.emit`),
    sans passer par un clic DOM sur le bouton menu : elle n'est donc pas
    bloquée par l'attribut `disabled` du bouton."""
    at_menu.evaluate("sendAction({type: 'mode', value: 'lichess'})")
    at_menu.wait_for_selector("#screen-config-lichess", state="visible", timeout=5000)
    return at_menu


# ── Partie A — écran de configuration Lichess ──────────────────────────────────

def test_config_lichess_accessible_sans_echiquier(at_config_lichess):
    """L'écran de configuration Lichess est atteignable et visible sans
    échiquier physique ni jeton Lichess enregistré."""
    assert at_config_lichess.locator("#screen-config-lichess").is_visible()


def test_config_lichess_pas_de_defilement_horizontal(at_config_lichess):
    """Reproduction directe du bug de #310 : le contenu de l'écran de config
    ne doit pas dépasser la largeur de la fenêtre (pas de scrollbar
    horizontale)."""
    scroll_width = at_config_lichess.evaluate("document.documentElement.scrollWidth")
    client_width = at_config_lichess.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width, (
        f"défilement horizontal détecté (scrollWidth={scroll_width} > "
        f"clientWidth={client_width}) — régression du bug #310"
    )


@pytest.mark.parametrize(
    "selector",
    [
        "#cfg-lichess-level",
        "#cfg-lichess-cadence",
        "#cfg-lichess-white",
        "#cfg-lichess-black",
        "#cfg-lichess-random",
        "#cfg-lichess-player",
        "#screen-config-lichess button[data-action=\"back_menu\"]",
        "#btn-start-lichess",
    ],
)
def test_config_lichess_elements_visibles_dans_la_fenetre(at_config_lichess, selector):
    """Chaque élément clé de l'écran de configuration Lichess est visible et
    entièrement contenu dans le viewport — avant le correctif CSS de #310,
    ces éléments étaient rejetés hors de la fenêtre."""
    assert _dans_la_fenetre(at_config_lichess, selector), (
        f"{selector!r} absent, invisible, ou hors fenêtre"
    )


def test_config_lichess_retour_menu(at_config_lichess):
    """Le bouton Retour de l'écran de config Lichess ramène bien au menu."""
    at_config_lichess.locator(
        "#screen-config-lichess button[data-action=\"back_menu\"]"
    ).click()
    at_config_lichess.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    assert at_config_lichess.locator("#screen-menu").is_visible()


# ── Partie B — écran de partie rempli par des événements simulés ──────────────

@pytest.fixture
def at_game_lichess(at_menu):
    """Affiche l'écran de partie en mode Lichess sans démarrer de vraie
    partie (donc sans requête réseau vers lichess.org) : les deux
    événements socket que le serveur envoie normalement en début de partie
    réelle ("app_state" avec state=playing, puis "lichess_init") sont
    simulés en invoquant directement les callbacks déjà enregistrés par
    `socket.on(...)` dans app.js (cf. `_declencher_evenement_socket_client`
    ci-dessus)."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu,
        "lichess_init",
        {
            "fen": FEN_DEPART,
            "color": "white",
            "level": 3,
            "player": "Testeur e2e",
        },
    )
    return at_menu


def test_game_lichess_screen_game_visible(at_game_lichess):
    """L'écran de partie est affiché."""
    assert at_game_lichess.locator("#screen-game").is_visible()


def test_game_lichess_plateau_visible(at_game_lichess):
    """La zone du plateau (#board) est visible et dans la fenêtre."""
    assert _dans_la_fenetre(at_game_lichess, "#board")


@pytest.mark.parametrize("selector", ["#clock-top", "#clock-bottom"])
def test_game_lichess_pendules_visibles(at_game_lichess, selector):
    """Les deux pendules Lichess sont rendues visibles par `lichess_init`
    (masquées par défaut via `style="display:none"` inline, affichées par
    `_lichessSetClocksVisible(true)`)."""
    assert _dans_la_fenetre(at_game_lichess, selector)


def test_game_lichess_bouton_abandonner_visible(at_game_lichess):
    """Le bouton Abandonner (ouvre la modale de confirmation) est visible."""
    assert _dans_la_fenetre(
        at_game_lichess, "button[data-action=\"ouvrir_modal_abandonner\"]"
    )


def test_game_lichess_bouton_nulle_visible(at_game_lichess):
    """Le bouton Proposer nulle est visible et activé (lichess_init
    l'active explicitement : `btnNulle.disabled = false`)."""
    btn = at_game_lichess.locator("#btn-nulle")
    assert _dans_la_fenetre(at_game_lichess, "#btn-nulle")
    assert not btn.is_disabled()
