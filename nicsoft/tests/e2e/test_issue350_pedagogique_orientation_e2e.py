"""
Test e2e (issue #350) — même défaut que #345/#348, mais en mode Pédagogique
(partie contre moteur) : `socket.on("init")` et `socket.on("swap_color")`
affectaient toujours "haut=adversaire, bas=joueur" ou l'inverse selon la
couleur du joueur, sans jamais tenir compte de `_boardFlipped` — échiquier
retourné pendant une partie Pédagogique, les noms affichés en haut/bas ne
correspondaient plus aux pièces réellement présentes de ce côté.

Le résultat réel de la partie (1-0/0-1, PGN) n'est pas affecté : décidé
côté serveur par `self.playing_white` (voir pedagogique.py), jamais depuis
une position écran — seul le texte affiché était trompeur. Voir aussi
`ouvrirModalNulle()` (branche moteur, hors HH/Lichess) qui lisait le nom de
l'adversaire via une formule "isWhite ? top : bottom" figée, même défaut.

En passant, `socket.on("init_hh")` (démarrage HH) a été aligné sur
`_reviewSetTopBottomNames()` par cohérence (même défaut latent, non
observable en pratique car `_boardFlipped` est toujours remis à false au
retour menu avant un nouveau départ de partie — mais la nouvelle écriture
ne dépend plus de cet invariant).

Corrigé en réutilisant `_reviewSetTopBottomNames()` /
`_reviewWhiteBlackFromTopBottom()` (#345/#348) sans dupliquer la logique
d'orientation.

Tests simulés par événements socket (`socket.listeners(...).forEach(h =>
h(data))`), sans échiquier physique — même procédé que
test_issue348_hh_abandon_orientation_e2e.py.
"""
import pytest

pytestmark = pytest.mark.slow


def _init_pedagogique(page, player="Alice", color="white", opponent="Stockfish ~500elo"):
    page.evaluate("() => { _gameMode = ''; }")
    page.evaluate(
        """(data) => { socket.listeners('init').forEach(h => h(data)); }""",
        {
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "player": player,
            "color": color,
            "level": 5,
            "pause": None,
            "analyse": True,
            "opponent": opponent,
            "engine_type": "stockfish",
        },
    )


def _swap_color(page, player="Alice", color="black", level=5, opponent="Stockfish ~500elo"):
    page.evaluate(
        """(data) => { socket.listeners('swap_color').forEach(h => h(data)); }""",
        {"player": player, "color": color, "level": level, "opponent": opponent},
    )


def _flip(page):
    page.evaluate("() => { flipBoard(); }")


def _reset_state(page):
    page.evaluate("() => { if (_boardFlipped) { flipBoard(); } _gameMode = ''; currentPlayerColor = 'white'; }")


def _top_bottom_names(page):
    return page.evaluate(
        """() => ({
            top: document.getElementById('player-top-name').textContent,
            bottom: document.getElementById('player-bottom-name').textContent,
        })"""
    )


# ── Point 1 de l'issue : démarrage ("init") de la partie Pédagogique ───────

def test_init_pedagogique_joueur_blanc_non_retourne(at_menu):
    _init_pedagogique(at_menu, player="Alice", color="white", opponent="Stockfish")
    # Non flippé : haut=Noir(adversaire), bas=Blanc(joueur).
    assert _top_bottom_names(at_menu) == {"top": "Stockfish", "bottom": "Alice"}
    _reset_state(at_menu)


def test_init_pedagogique_joueur_noir_non_retourne(at_menu):
    _init_pedagogique(at_menu, player="Alice", color="black", opponent="Stockfish")
    # Non flippé : haut=Noir(joueur), bas=Blanc(adversaire).
    assert _top_bottom_names(at_menu) == {"top": "Alice", "bottom": "Stockfish"}
    _reset_state(at_menu)


def test_init_pedagogique_joueur_blanc_echiquier_retourne(at_menu):
    """Avant #350 : l'échiquier retourné pendant une partie Pédagogique
    précédente (ou retourné juste avant le prochain "init") laissait
    toujours le nom de l'adversaire en haut, quelle que soit l'orientation
    — ici flippé (Blancs en haut), le joueur blanc doit apparaître en
    haut, pas l'adversaire."""
    _flip(at_menu)
    _init_pedagogique(at_menu, player="Alice", color="white", opponent="Stockfish")
    # Flippé : haut=Blanc(joueur), bas=Noir(adversaire).
    assert _top_bottom_names(at_menu) == {"top": "Alice", "bottom": "Stockfish"}
    _reset_state(at_menu)


def test_init_pedagogique_joueur_noir_echiquier_retourne(at_menu):
    _flip(at_menu)
    _init_pedagogique(at_menu, player="Alice", color="black", opponent="Stockfish")
    # Flippé : haut=Blanc(adversaire), bas=Noir(joueur).
    assert _top_bottom_names(at_menu) == {"top": "Stockfish", "bottom": "Alice"}
    _reset_state(at_menu)


# ── Changement de camp en pause Pédagogique (swap_color) : même défaut ─────

def test_swap_color_pedagogique_suit_lorientation_non_retourne(at_menu):
    _init_pedagogique(at_menu, player="Alice", color="white", opponent="Stockfish")
    # Le joueur change de camp : il devient Noir.
    _swap_color(at_menu, player="Alice", color="black", opponent="Stockfish")
    assert _top_bottom_names(at_menu) == {"top": "Alice", "bottom": "Stockfish"}
    _reset_state(at_menu)


def test_swap_color_pedagogique_suit_lorientation_retournee(at_menu):
    """Avant #350 : swap_color écrivait toujours haut/bas selon la seule
    nouvelle couleur du joueur, sans tenir compte de l'échiquier retourné."""
    _init_pedagogique(at_menu, player="Alice", color="white", opponent="Stockfish")
    _flip(at_menu)
    _swap_color(at_menu, player="Alice", color="black", opponent="Stockfish")
    # Flippé : haut=Blanc(adversaire), bas=Noir(joueur).
    assert _top_bottom_names(at_menu) == {"top": "Stockfish", "bottom": "Alice"}
    _reset_state(at_menu)


# ── Modale "Proposer nulle" en Pédagogique : nom de l'adversaire lu selon
# l'orientation (ouvrirModalNulle(), branche moteur hors HH/Lichess) ───────

def test_modal_nulle_pedagogique_nom_adversaire_non_retourne(at_menu):
    _init_pedagogique(at_menu, player="Alice", color="white", opponent="Stockfish")
    titre = at_menu.evaluate(
        """() => { ouvrirModalNulle(); const t = document.getElementById('modal-title').textContent; fermerModal(); return t; }"""
    )
    assert "Stockfish" in titre
    assert "Alice" not in titre
    _reset_state(at_menu)


def test_modal_nulle_pedagogique_nom_adversaire_echiquier_retourne(at_menu):
    """Avant #350 : avec l'échiquier retourné, la modale "proposer nulle"
    lisait le nom du JOUEUR au lieu de l'adversaire (formule figée
    "isWhite ? top : bottom", sans consulter _boardFlipped)."""
    _init_pedagogique(at_menu, player="Alice", color="white", opponent="Stockfish")
    _flip(at_menu)
    titre = at_menu.evaluate(
        """() => { ouvrirModalNulle(); const t = document.getElementById('modal-title').textContent; fermerModal(); return t; }"""
    )
    assert "Stockfish" in titre, titre
    assert "Alice" not in titre, titre
    _reset_state(at_menu)


# ── Init HH aligné sur _reviewSetTopBottomNames() par cohérence : la
# convention par défaut (non flippé) reste inchangée (non-régression) ──────

def test_init_hh_convention_inchangee(at_menu):
    page = at_menu
    page.evaluate("() => { _gameMode = ''; }")
    page.evaluate(
        """(data) => { socket.listeners('init_hh').forEach(h => h(data)); }""",
        {
            "white": "Alice", "black": "Bob",
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        },
    )
    assert _top_bottom_names(page) == {"top": "Bob", "bottom": "Alice"}
    _reset_state(page)
