"""
nicsoft/tests/e2e/test_issue322_lichess_e2e.py — AlChess

Issue #322 : essai réel d'Alain (13 novembre 2026, partie amicale contre
l'IA de Lichess niveau 1, 15+10, utilisateur aux noirs, juste après 1.e4) —
deux défauts visibles à l'écran, restés après #321 point 6 :

1. Contre l'IA de Lichess, la phrase « la partie sera annulée dans environ
   {n} secondes » et le décompte associé n'auraient jamais dû apparaître :
   sur lichess.org, une partie contre l'IA n'affiche aucune menace
   d'annulation ni de décompte du premier coup (contrairement à une partie
   contre un humain, qui elle les affiche) — confirmé par l'essai réel
   d'Alain (partie non annulée après plus de 28 secondes).
2. La pendule de l'utilisateur affichait 14:57 alors qu'il n'avait pas
   encore joué : elle décomptait localement, alors que sur lichess.org les
   deux pendules restent figées à leur valeur de départ jusqu'à ce que
   chaque camp ait joué son propre premier coup.

Même technique que test_issue310_lichess_e2e.py/test_issue321_lichess_e2e.py :
événements socket simulés en invoquant directement les callbacks déjà
enregistrés par `socket.on(...)` côté client, sans réseau ni partie Lichess
réelle. La logique serveur (quand ces événements sont émis, et avec quelles
valeurs) est testée sans navigateur dans test_issue311_lichess_sequencing.py.

Lancer : pytest nicsoft/tests/e2e/test_issue322_lichess_e2e.py -v
"""
import pytest

from nicsoft.tests.e2e.test_issue310_lichess_e2e import (
    FEN_DEPART,
    _declencher_evenement_socket_client,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def at_game_lichess_noir(at_menu):
    """Partie simulée côté noirs, juste après le premier coup de l'IA
    (blancs) — reproduit l'état écran de l'essai réel d'Alain du
    13/11/2026."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART, "color": "black", "level": 1, "player": "Testeur e2e"},
    )
    return at_menu


# ═══════════════════════════════════════════════════════════════════════
# 1. Contre l'IA : aucune phrase d'annulation, aucun décompte, jamais rouge
#    (issue #322, point 1). Contre un humain : comportement #321 inchangé.
# ═══════════════════════════════════════════════════════════════════════

def test_contre_ia_sans_decompte_affiche_message_informatif_sans_menace(at_game_lichess_noir):
    """Le serveur n'envoie `seconds: None` que contre l'IA sans `expiration`
    explicite (voir game.py::_maybe_activate_first_move_deadline) — le
    texte affiché doit alors être purement informatif, sans mention
    d'annulation ni de délai."""
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": None, "estimated": False},
    )
    el = page.locator("#lichess-first-move-deadline")
    assert el.is_visible()
    texte = (el.text_content() or "").lower()
    for mot_menace in ("annul", "cancel", "abgebrochen", "abbricht"):
        assert mot_menace not in texte, f"menace d'annulation encore présente ({mot_menace!r})"
    assert "lichess-banner-danger" not in (el.get_attribute("class") or "")


def test_contre_ia_sans_decompte_jamais_rouge_meme_apres_un_long_moment(at_game_lichess_noir):
    """Sans secondes (cas IA sans `expiration`), la classe de danger ne doit
    jamais s'appliquer, quel que soit l'événement reçu ensuite tant que
    `seconds` reste `None`."""
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": None, "estimated": False},
    )
    el = page.locator("#lichess-first-move-deadline")
    # Un deuxième envoi (comme le ferait le push régulier du serveur) : la
    # classe rouge ne doit toujours pas apparaître.
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": None, "estimated": False},
    )
    assert "lichess-banner-danger" not in (el.get_attribute("class") or "")


def test_contre_humain_garde_la_menace_et_le_rouge_a_5_secondes(at_game_lichess_noir):
    """Non régression du comportement #321 point 6 : quand le serveur
    envoie un décompte réel (`seconds` non None — cas d'une future partie
    contre un humain, ou d'une IA avec `expiration` explicite), le message
    annonce bien l'annulation et devient rouge à 5 secondes ou moins."""
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": 27, "estimated": True},
    )
    el = page.locator("#lichess-first-move-deadline")
    texte = (el.text_content() or "").lower()
    assert any(mot in texte for mot in ("annul", "cancel", "abgebrochen", "abbricht"))
    assert any(mot in texte for mot in ("environ", "approximately", "etwa"))
    assert "lichess-banner-danger" not in (el.get_attribute("class") or "")

    _declencher_evenement_socket_client(
        page, "lichess_first_move_deadline", {"active": True, "seconds": 5, "estimated": True},
    )
    assert "lichess-banner-danger" in (el.get_attribute("class") or "")


# ═══════════════════════════════════════════════════════════════════════
# 2. Pendules figées avant les premiers coups des deux camps, pour les deux
#    couleurs (issue #322, point 2).
# ═══════════════════════════════════════════════════════════════════════

def test_pendule_utilisateur_figee_avant_son_propre_premier_coup(at_game_lichess_noir):
    """Utilisateur aux noirs, l'IA (blancs) vient de jouer : la pendule
    noire doit afficher la valeur de départ Lichess, jamais une valeur déjà
    décomptée (reproduit le 14:57 observé par Alain, qui aurait dû rester à
    15:00)."""
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_clock", {"white_ms": 900000, "black_ms": 900000, "turn": "black"},
    )
    bottom = page.locator("#clock-bottom")  # l'utilisateur est toujours en bas (lichess_init)
    assert bottom.text_content() == "15:00"


def test_pendule_blanche_figee_avant_le_tout_premier_coup(at_menu):
    """Utilisateur aux blancs, avant même son tout premier coup : la
    pendule blanche doit aussi rester figée à la valeur de départ (les deux
    couleurs sont concernées par le gel initial, pas seulement les noirs)."""
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "playing"})
    at_menu.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        at_menu, "lichess_init",
        {"fen": FEN_DEPART, "color": "white", "level": 1, "player": "Testeur e2e"},
    )
    _declencher_evenement_socket_client(
        at_menu, "lichess_clock", {"white_ms": 900000, "black_ms": 900000, "turn": "white"},
    )
    bottom = at_menu.locator("#clock-bottom")  # l'utilisateur (blancs) est en bas
    assert bottom.text_content() == "15:00"


def test_pendule_decompte_normalement_une_fois_les_deux_premiers_coups_joues(at_game_lichess_noir):
    """Une fois que chaque camp a joué son propre premier coup, le serveur
    envoie des valeurs réellement décomptées — l'affichage doit les suivre
    normalement (pas de gel permanent, seulement avant les premiers
    coups)."""
    page = at_game_lichess_noir
    _declencher_evenement_socket_client(
        page, "lichess_clock", {"white_ms": 895000, "black_ms": 900000, "turn": "white"},
    )
    top = page.locator("#clock-top")  # l'adversaire (IA, blancs) est en haut
    assert top.text_content() == "14:55"
