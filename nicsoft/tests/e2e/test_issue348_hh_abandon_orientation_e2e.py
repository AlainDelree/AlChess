"""
Test e2e (issue #348) — défaut latent signalé par #345 : la fenêtre de
confirmation d'abandon du mode Humain contre Humain (`ouvrirModalAbandonner()`,
branche `_gameMode === "humain"`) lisait toujours "Blanc" dans
#player-bottom-name et "Noir" dans #player-top-name, sans tenir compte de
`_boardFlipped` — échiquier retourné (Noirs en bas), les boutons de la modale
affichaient le nom de l'adversaire sur le mauvais bouton.

Le résultat réel de la partie (1-0/0-1, PGN) n'était PAS affecté : les
boutons HTML envoient `{type:'abandonner', couleur:'blanc'|'noir'}` fixe
(voir templates/index.html), et `human.py::_traiter_abandon()` décide
gagnant/résultat depuis `couleur`, jamais depuis une position écran — seul
le texte affiché sur le bouton était trompeur.

Corrigé en réutilisant `_reviewWhiteBlackFromTopBottom()` (#345) au lieu de
dupliquer la logique d'orientation. Même défaut trouvé et corrigé dans
`socket.on("swap_color_hh")` (changement de camp pendant une pause HH),
réutilisant `_reviewSetTopBottomNames()` (#345).

Tests simulés par événements socket (`socket.listeners(...).forEach(h =>
h(data))`), sans échiquier physique — même procédé que test_issue345_
analyse_lichess_fixes_e2e.py.
"""
import pytest

pytestmark = pytest.mark.slow


def _init_hh(page, white="Alice", black="Bob"):
    page.evaluate("() => { _gameMode = ''; }")
    page.evaluate(
        """(data) => { socket.listeners('init_hh').forEach(h => h(data)); }""",
        {
            "white": white,
            "black": black,
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        },
    )


def _flip(page):
    page.evaluate("() => { flipBoard(); }")


def _reset_state(page):
    page.evaluate("() => { if (_boardFlipped) { flipBoard(); } _gameMode = ''; }")


def _ouvrir_modal_abandonner(page):
    page.evaluate("() => { ouvrirModalAbandonner(); }")


def _fermer_modal(page):
    page.evaluate("() => { fermerModal(); }")


def _modal_btn_textes(page):
    return page.evaluate(
        """() => ({
            blanc: document.getElementById('modal-btn-blanc').textContent,
            noir:  document.getElementById('modal-btn-noir').textContent,
        })"""
    )


def _top_bottom_names(page):
    return page.evaluate(
        """() => ({
            top: document.getElementById('player-top-name').textContent,
            bottom: document.getElementById('player-bottom-name').textContent,
        })"""
    )


# ── Point 2 de l'issue : noms corrects sur la modale d'abandon HH ──────────

def test_modal_abandon_hh_noms_corrects_echiquier_non_retourne(at_menu):
    _init_hh(at_menu)
    # Non flippé : convention #345 — haut=Noir, bas=Blanc (voir init_hh).
    assert _top_bottom_names(at_menu) == {"top": "Bob", "bottom": "Alice"}

    _ouvrir_modal_abandonner(at_menu)
    textes = _modal_btn_textes(at_menu)
    assert "Alice" in textes["blanc"]
    assert "Bob" in textes["noir"]
    _fermer_modal(at_menu)
    _reset_state(at_menu)


def test_modal_abandon_hh_noms_corrects_echiquier_retourne(at_menu):
    """Avant #348 : avec l'échiquier retourné, le bouton "Blancs abandonnent"
    affichait le nom du joueur Noir (lu depuis #player-bottom-name, qui tient
    alors le nom du joueur Noir puisque l'échiquier est retourné) — et
    inversement pour le bouton "Noirs abandonnent"."""
    _init_hh(at_menu)
    _flip(at_menu)
    # Flippé : haut=Blanc, bas=Noir.
    assert _top_bottom_names(at_menu) == {"top": "Alice", "bottom": "Bob"}

    _ouvrir_modal_abandonner(at_menu)
    textes = _modal_btn_textes(at_menu)
    assert "Alice" in textes["blanc"], textes
    assert "Alice" not in textes["noir"], textes
    assert "Bob" in textes["noir"], textes
    assert "Bob" not in textes["blanc"], textes
    _fermer_modal(at_menu)
    _reset_state(at_menu)


# ── Les boutons restent corrects quel que soit le nom affiché : le bouton
# "blanc" envoie toujours couleur:'blanc' (vérifié dans le template, pas
# dépendant de l'orientation) — non-régression du résultat de partie. ──────

def test_modal_abandon_hh_boutons_envoient_toujours_la_bonne_couleur(at_menu):
    _init_hh(at_menu)
    _flip(at_menu)
    _ouvrir_modal_abandonner(at_menu)
    onclick_blanc = at_menu.evaluate(
        "() => document.getElementById('modal-btn-blanc').getAttribute('onclick')"
    )
    onclick_noir = at_menu.evaluate(
        "() => document.getElementById('modal-btn-noir').getAttribute('onclick')"
    )
    assert "couleur:'blanc'" in onclick_blanc
    assert "couleur:'noir'" in onclick_noir
    _fermer_modal(at_menu)
    _reset_state(at_menu)


# ── Changement de camp en pause HH (swap_color_hh) : même défaut, même
# correctif (_reviewSetTopBottomNames) ─────────────────────────────────────

def test_swap_color_hh_suit_lorientation_echiquier_non_retourne(at_menu):
    _init_hh(at_menu)
    at_menu.evaluate(
        """(data) => { socket.listeners('swap_color_hh').forEach(h => h(data)); }""",
        {"white": "Bob", "black": "Alice"},
    )
    assert _top_bottom_names(at_menu) == {"top": "Alice", "bottom": "Bob"}
    _reset_state(at_menu)


def test_swap_color_hh_suit_lorientation_echiquier_retourne(at_menu):
    """Avant #348 : swap_color_hh écrivait toujours haut=Noir/bas=Blanc,
    quelle que soit l'orientation réelle — ici l'échiquier est retourné
    (haut=Blanc/bas=Noir attendu)."""
    _init_hh(at_menu)
    _flip(at_menu)
    at_menu.evaluate(
        """(data) => { socket.listeners('swap_color_hh').forEach(h => h(data)); }""",
        {"white": "Bob", "black": "Alice"},
    )
    assert _top_bottom_names(at_menu) == {"top": "Bob", "bottom": "Alice"}
    _reset_state(at_menu)
