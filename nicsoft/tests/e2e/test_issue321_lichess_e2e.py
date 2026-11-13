"""
nicsoft/tests/e2e/test_issue321_lichess_e2e.py — AlChess

Issue #321 : essais réels d'Alain (13 novembre 2026) — boutons Abandonner/
Proposer nulle actifs à tout moment côté interface, messages de nulle
éphémères (ratés en alternant regard écran/échiquier), et aucune indication
lisible lorsque la position physique devient illégale pendant le tour de
l'utilisateur (coup noir remplacé par erreur par un coup blanc).

Vérifie ici, dans un vrai navigateur (Playwright), uniquement ce qui ne
peut pas l'être côté Python : l'effet des événements socket côté DOM
(attribut disabled des boutons, visibilité et contenu des bannières,
classe CSS "lichess-banner-danger"). La logique serveur (quand ces
événements sont émis) est testée sans navigateur dans
nicsoft/tests/test_issue321_lichess_boutons_et_nulle.py.

Même technique que test_issue310_lichess_e2e.py : événements socket
simulés en invoquant directement les callbacks déjà enregistrés par
`socket.on(...)` côté client (socket.listeners(event)), sans requête
réseau ni partie Lichess réelle.

Lancer : pytest nicsoft/tests/e2e/test_issue321_lichess_e2e.py -v
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import (
    FEN_DEPART,
    _declencher_evenement_socket_client,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def at_game_lichess_noir(at_menu):
    """Partie simulée côté noirs : l'IA (blancs) vient de jouer, boutons
    désactivés par défaut (comme le ferait lichess_init), avant tout
    lichess_action_buttons — reproduit l'état réel au tout début d'une
    partie où l'utilisateur joue les noirs (issue #321, point 1)."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART, "color": "black", "level": 3, "player": "Testeur e2e"},
    )
    return at_menu


# ═══════════════════════════════════════════════════════════════════════
# 1. Boutons Abandonner/Proposer nulle — activés/désactivés par le signal
#    serveur unique lichess_action_buttons (issue #321, points 1 et 2).
# ═══════════════════════════════════════════════════════════════════════

def test_boutons_desactives_par_defaut_des_lichess_init(at_game_lichess_noir):
    """Avant tout lichess_action_buttons, les deux boutons sont grisés —
    y compris pour les noirs, au tout début de partie."""
    page = at_game_lichess_noir
    assert page.locator("#btn-resign").is_disabled()
    assert page.locator("#btn-nulle").is_disabled()
    assert page.locator("#lichess-actions-hint").is_visible()


def test_boutons_sactivent_sur_lichess_action_buttons(at_game_lichess_noir):
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_action_buttons", {"resign_enabled": True, "draw_enabled": True},
    )
    assert not page.locator("#btn-resign").is_disabled()
    assert not page.locator("#btn-nulle").is_disabled()
    assert page.locator("#lichess-actions-hint").is_hidden()


def test_abandon_seul_reste_actif_echiquier_perdu(at_game_lichess_noir):
    """Exception de sécurité (issue #321, point 2) : Abandonner reste
    cliquable même quand Proposer nulle est grisé."""
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_action_buttons", {"resign_enabled": True, "draw_enabled": False},
    )
    assert not page.locator("#btn-resign").is_disabled()
    assert page.locator("#btn-nulle").is_disabled()


# ═══════════════════════════════════════════════════════════════════════
# 2. Messages de nulle persistants près de « Tour en cours » (issue #321,
#    point 3) — jusqu'au coup suivant de l'utilisateur, pas un toast bref.
# ═══════════════════════════════════════════════════════════════════════

def test_nulle_proposee_affiche_bandeau_persistant_apres_le_coup(at_game_lichess_noir):
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(page, "lichess_draw_proposed", {})
    banner = page.locator("#lichess-draw-wait-msg")
    assert banner.is_visible()
    texte = (banner.text_content() or "").lower()
    # Le texte doit indiquer que la réponse vient APRÈS le coup de
    # l'utilisateur — pas la confusion réelle d'Alain le 13/11/2026.
    assert "apr" in texte or "after" in texte or "nach" in texte


def test_nulle_refusee_reste_visible_jusquau_coup_de_lutilisateur(at_game_lichess_noir):
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(page, "lichess_draw_proposed", {})
    _declencher_evenement_socket_client(page, "lichess_draw_refused", {})
    banner = page.locator("#lichess-draw-wait-msg")
    assert banner.is_visible()

    # Le coup qu'on reproduit ensuite est celui de l'ADVERSAIRE (celui qui
    # vient de refuser) : le bandeau doit rester affiché.
    _declencher_evenement_socket_client(
        page, "lichess_move",
        {"fen": FEN_DEPART.split(" ")[0], "san": "Nf3", "uci": "g1f3",
         "color": "white", "opponent_move": True},
    )
    assert banner.is_visible()

    # Le coup suivant JOUÉ PAR L'UTILISATEUR fait disparaître le bandeau.
    _declencher_evenement_socket_client(
        page, "lichess_move",
        {"fen": FEN_DEPART.split(" ")[0], "san": "Nf6", "uci": "g8f6",
         "color": "black", "opponent_move": False},
    )
    assert banner.is_hidden()


def test_nulle_acceptee_affiche_bandeau_dedie(at_game_lichess_noir):
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(page, "lichess_draw_accepted", {})
    banner = page.locator("#lichess-draw-wait-msg")
    assert banner.is_visible()


# ═══════════════════════════════════════════════════════════════════════
# 3. Position physique incorrecte (issue #321, point 5) — message
#    persistant, cases en rouge sur l'échiquier, remplace la phrase du
#    premier coup tant qu'elle est active.
# ═══════════════════════════════════════════════════════════════════════

def test_position_incorrecte_remplace_la_phrase_du_premier_coup(at_game_lichess_noir):
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": 20, "estimated": False},
    )
    assert page.locator("#lichess-first-move-deadline").is_visible()

    _declencher_evenement_socket_client(
        page, "lichess_illegal_position",
        {"active": True,
         "expected_fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR",
         "physical_fen": "rnbqkbnr/ppp2ppp/8/3pp3/4P3/8/PPP2PPP/RNBQKBNR"},
    )
    illegal_banner = page.locator("#lichess-illegal-position")
    assert illegal_banner.is_visible()
    assert page.locator("#lichess-first-move-deadline").is_hidden()

    # Au moins une case de l'échiquier porte la classe d'erreur rouge
    # (réutilisation de renderBoardWithErrors()).
    assert page.locator("#board .sq-error").count() > 0

    # Position corrigée : le message disparaît, la phrase du premier coup
    # peut réapparaître.
    _declencher_evenement_socket_client(page, "lichess_illegal_position", {"active": False})
    assert illegal_banner.is_hidden()
    assert page.locator("#lichess-first-move-deadline").is_visible()


# ═══════════════════════════════════════════════════════════════════════
# 4. Décompte du premier coup — rouge à environ 5 secondes (issue #321,
#    point 6), exact ou estimé.
# ═══════════════════════════════════════════════════════════════════════

def test_decompte_premier_coup_pas_rouge_au_dessus_de_5_secondes(at_game_lichess_noir):
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": 12, "estimated": False},
    )
    el = page.locator("#lichess-first-move-deadline")
    assert "lichess-banner-danger" not in (el.get_attribute("class") or "")


def test_decompte_premier_coup_rouge_a_5_secondes_ou_moins(at_game_lichess_noir):
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": 5, "estimated": False},
    )
    el = page.locator("#lichess-first-move-deadline")
    assert "lichess-banner-danger" in (el.get_attribute("class") or "")


def test_decompte_premier_coup_estime_mentionne_environ(at_game_lichess_noir):
    """Issue #321, point 6 : jamais présenté comme exact quand Lichess
    n'envoie pas `expiration` — le texte doit le dire (« environ »/
    « approximately »/« etwa »)."""
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": 25, "estimated": True},
    )
    texte = (page.locator("#lichess-first-move-deadline").text_content() or "").lower()
    assert any(mot in texte for mot in ("environ", "approximately", "etwa"))
