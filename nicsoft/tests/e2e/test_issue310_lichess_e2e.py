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
    # Dans une vraie partie, ce second événement suit lichess_init dans la
    # même fonction Python (_apply_game_full appelle _sync_turn_ready() en
    # dernier) : les blancs, à leur tour dès le début, position physique
    # supposée alignée (issue #321, point 1) — Abandonner/Proposer nulle
    # actifs. Simulé ici puisque ce test n'exécute pas de vraie boucle
    # LichessGame côté Python.
    _declencher_evenement_socket_client(
        at_menu, "lichess_action_buttons", {"resign_enabled": True, "draw_enabled": True},
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
    """Le bouton Proposer nulle est visible et activé une fois le signal
    serveur lichess_action_buttons reçu (issue #321, point 1 : désactivé
    par défaut dès lichess_init, jusqu'à ce signal)."""
    btn = at_game_lichess.locator("#btn-nulle")
    assert _dans_la_fenetre(at_game_lichess, "#btn-nulle")
    assert not btn.is_disabled()


# ── Partie C — jamais de fin silencieuse + compte à rebours (issue #311) ──────

def test_game_lichess_aborted_affiche_message_explicite_et_deux_boutons(at_game_lichess):
    """Une fin de partie inattendue (ex. premier coup non joué à temps)
    affiche une fenêtre persistante avec un message traduit et les deux
    boutons "Rejouer avec les mêmes réglages" / "Retour au menu" — jamais
    de retour silencieux au menu (issue #311, point 3)."""
    _declencher_evenement_socket_client(
        at_game_lichess, "lichess_aborted",
        {
            "message_key": "lichess.annulee_premier_coup_trop_tard",
            "replay_settings": {"level": 3, "cadence": "15+10", "color": "black", "player": "Testeur e2e"},
        },
    )
    at_game_lichess.wait_for_selector("#lichess-aborted-overlay", state="visible", timeout=5000)
    assert at_game_lichess.locator("#lichess-aborted-overlay").is_visible()
    message = at_game_lichess.locator("#lichess-aborted-message").text_content()
    # "annul" n'apparaît qu'en français — la page démarre sans cookie de
    # locale, donc en anglais (DEFAULT_LOCALE de i18n.js) : on vérifie sur
    # "lichess", présent dans les 3 traductions de cette clé (issue #312 —
    # ce test, ajouté par #311, n'avait encore jamais tourné : le serveur
    # e2e restait bloqué avant d'atteindre le navigateur).
    assert message and "lichess" in message.lower()
    assert _dans_la_fenetre(at_game_lichess, "#lichess-aborted-replay-btn")


def test_game_lichess_aborted_retour_menu_ferme_la_fenetre(at_game_lichess):
    """Le bouton "Retour au menu" de la fenêtre d'annulation la referme."""
    _declencher_evenement_socket_client(
        at_game_lichess, "lichess_aborted",
        {"message_key": "lichess.annulee_cause_inconnue", "replay_settings": None},
    )
    at_game_lichess.wait_for_selector("#lichess-aborted-overlay", state="visible", timeout=5000)
    at_game_lichess.evaluate("lichessAbortedBackMenu()")
    assert not at_game_lichess.locator("#lichess-aborted-overlay").is_visible()


def test_game_lichess_premier_coup_decompte_apparait_puis_disparait(at_game_lichess):
    """Le compte à rebours du premier coup (noirs) apparaît avec le nombre
    de secondes reçu puis disparaît dès qu'un coup est joué (issue #311,
    point 2)."""
    _declencher_evenement_socket_client(
        at_game_lichess, "lichess_first_move_deadline", {"active": True, "seconds": 18},
    )
    at_game_lichess.wait_for_selector("#lichess-first-move-deadline", state="visible", timeout=5000)
    texte = at_game_lichess.locator("#lichess-first-move-deadline").text_content()
    assert "18" in texte
    _declencher_evenement_socket_client(
        at_game_lichess, "lichess_first_move_deadline", {"active": False},
    )
    assert not at_game_lichess.locator("#lichess-first-move-deadline").is_visible()


# ── Partie D — orientation de l'échiquier selon la couleur (issue #315) ───────

def _case_box(page, prefix, file, rank):
    """Bounding box de la case `file-rank` (0-indexée) de l'échiquier
    identifié par `prefix` ("sq" pour #board, "pi" pour #board-pos-init)."""
    return page.locator(f"#{prefix}-{file}-{rank}").bounding_box()


def _a1_en_haut_a_droite_de_h8(page, prefix):
    """True si a1 (file=0,rank=0) est visuellement au-dessus et à droite de
    h8 (file=7,rank=7) — signe d'un échiquier retourné (noirs en bas) ;
    False si c'est l'inverse (orientation normale, blancs en bas)."""
    a1 = _case_box(page, prefix, 0, 0)
    h8 = _case_box(page, prefix, 7, 7)
    assert a1 and h8, f"case(s) introuvable(s) pour le préfixe {prefix!r}"
    return a1["y"] < h8["y"] and a1["x"] > h8["x"]


@pytest.fixture
def game_lichess_noirs(at_menu):
    """Écran de partie Lichess simulé avec l'utilisateur aux noirs (mêmes
    événements simulés que `at_game_lichess`, couleur différente)."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART, "color": "black", "level": 3, "player": "Testeur e2e noirs"},
    )
    return at_menu


@pytest.fixture
def game_lichess_blancs(at_menu):
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART, "color": "white", "level": 3, "player": "Testeur e2e blancs"},
    )
    return at_menu


def test_lichess_noirs_echiquier_retourne(game_lichess_noirs):
    """Issue #315, point 1 : en jouant les noirs, l'échiquier de l'écran de
    jeu est retourné — a1 se retrouve en haut à droite."""
    assert _a1_en_haut_a_droite_de_h8(game_lichess_noirs, "sq")


def test_lichess_noirs_rangee_haut_montre_l_adversaire(game_lichess_noirs):
    """Issue #315, point 2 : la rangée du haut montre toujours l'adversaire
    (nom), celle du bas l'utilisateur — y compris pour les noirs, alors que
    lichess_clock suppose déjà cette convention."""
    top = game_lichess_noirs.locator("#player-top-name").text_content()
    bottom = game_lichess_noirs.locator("#player-bottom-name").text_content()
    assert bottom == "Testeur e2e noirs"
    assert top == "Lichess AI (level 3)"


def test_lichess_noirs_pendules_coherentes_avec_les_rangees(game_lichess_noirs):
    """Issue #315, point 2 : la pendule du haut montre le temps de
    l'adversaire (blancs ici), celle du bas celui de l'utilisateur (noirs)."""
    _declencher_evenement_socket_client(
        game_lichess_noirs, "lichess_clock",
        {"white_ms": 50000, "black_ms": 80000, "turn": "black"},
    )
    assert game_lichess_noirs.locator("#clock-top").text_content() == "0:50"
    assert game_lichess_noirs.locator("#clock-bottom").text_content() == "1:20"


def test_lichess_noirs_bouton_flip_inverse_l_orientation(game_lichess_noirs):
    """Le bouton de retournement manuel continue de fonctionner par-dessus
    l'orientation automatique."""
    assert _a1_en_haut_a_droite_de_h8(game_lichess_noirs, "sq")
    game_lichess_noirs.evaluate("flipBoard()")
    assert not _a1_en_haut_a_droite_de_h8(game_lichess_noirs, "sq")


def test_lichess_blancs_echiquier_et_rangees_inchanges(game_lichess_blancs):
    """Issue #315 : pour les blancs, rien ne change par rapport au
    comportement d'avant #315 — échiquier normal, noms non inversés."""
    assert not _a1_en_haut_a_droite_de_h8(game_lichess_blancs, "sq")
    top = game_lichess_blancs.locator("#player-top-name").text_content()
    bottom = game_lichess_blancs.locator("#player-bottom-name").text_content()
    assert bottom == "Testeur e2e blancs"
    assert top == "Lichess AI (level 3)"


def test_lichess_mise_en_place_orientee_pour_les_noirs(at_menu):
    """Issue #315, point 3 : l'écran de mise en place (cases à corriger en
    rouge) s'oriente aussi du point de vue de l'utilisateur."""
    _declencher_evenement_socket_client(
        at_menu, "app_state",
        {"state": "position_initiale", "fen": FEN_DEPART, "color": "black"},
    )
    at_menu.wait_for_selector("#screen-pos-init", state="visible", timeout=5000)
    assert _a1_en_haut_a_droite_de_h8(at_menu, "pi")


def test_lichess_mise_en_place_normale_pour_les_blancs(at_menu):
    """Même écran, inchangé pour les blancs."""
    _declencher_evenement_socket_client(
        at_menu, "app_state",
        {"state": "position_initiale", "fen": FEN_DEPART, "color": "white"},
    )
    at_menu.wait_for_selector("#screen-pos-init", state="visible", timeout=5000)
    assert not _a1_en_haut_a_droite_de_h8(at_menu, "pi")
