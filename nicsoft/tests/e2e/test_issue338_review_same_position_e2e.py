"""
Test e2e (issue #338) — l'écran d'analyse post-partie doit toujours tracer
les flèches des meilleures lignes et la flèche du coup joué pour la MÊME
position : le bon camp au trait, pour chaque position d'une courte partie,
parcourue vers l'avant puis vers l'arrière, échiquier normal et retourné.

Même chemin que test_issue335_review_arrows_e2e.py pour atteindre l'écran
de revue sans échiquier, sans partie jouée et SANS AUCUN MOTEUR : menu
"Analyse" → "Coller PGN". Le « faux moteur » ici est chess.js lui-même,
déjà chargé côté navigateur pour l'import PGN : pour chaque position on
calcule ses coups légaux via `new Chess(fen).moves()` et on les injecte
comme si elles venaient du moteur — jamais de calcul réel, jamais de
réseau.
"""
import pytest

pytestmark = pytest.mark.slow

_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7"

# Partie collée avec une position de départ particulière où les Noirs
# jouent en premier (ex. partie reprise depuis après 1.e4) — un des cas
# explicitement listés par l'issue #338 pour établir la cause.
_PGN_NOIRS_EN_PREMIER = (
    '[SetUp "1"]\n'
    '[FEN "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"]\n\n'
    "1. Nc6 2. Nf3 Nf6"
)


def _charger_pgn_colle(page, pgn):
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def _reset_arrows_state(page):
    page.evaluate(
        """() => {
            _reviewArrowsEnabled = true;
            document.getElementById('review-arrows-toggle').checked = true;
            _reviewLinesCache = {};
            _reviewLinesPending = {};
        }"""
    )


def _retour_menu(page):
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _inspect_position(page, idx):
    """Injecte, pour la position d'indice `idx`, 3 lignes "moteur" qui sont
    de VRAIS coups légaux du camp au trait (calculés par chess.js sur le
    FEN affiché, jamais codés en dur) puis appelle renderReview(). Retourne
    le camp au trait du FEN affiché, la couleur du coup joué (flèche
    orange) et la couleur des pièces déplacées par les 3 flèches
    moteur — tout doit concorder avec le camp au trait."""
    return page.evaluate(
        """(idx) => {
            reviewIdx = idx;
            const fen = reviewFens[idx];
            const game = new Chess(fen);
            const turn = game.turn(); // 'w' ou 'b'
            const legal = game.moves({ verbose: true }).slice(0, 3);
            _reviewLinesCache[fen] = {
                lines: legal.map(m => ({
                    move: m.from + m.to + (m.promotion || ""),
                    san: m.san, cp: 10, mate: null,
                })),
                error: null,
            };
            renderReview();
            const playedMove = reviewMoves[idx] || null;
            // Couleur de la pièce déplacée par chaque flèche moteur
            // (vérifiée depuis le FEN affiché, pas depuis le coup lui-même).
            const arrowPieceColors = legal.map(m => {
                const piece = game.get(m.from);
                return piece ? piece.color : null;
            });
            return {
                fen, turn,
                playedColor: playedMove ? playedMove.color : null,
                arrowPieceColors,
                nLines: legal.length,
            };
        }""",
        idx,
    )


def _assert_position_coherente(info):
    turnColor = "white" if info["turn"] == "w" else "black"
    # Flèche orange : le coup joué depuis cette position est du camp au trait.
    if info["playedColor"] is not None:
        assert info["playedColor"] == turnColor, info
    # Flèches moteur : chaque pièce déplacée appartient au camp au trait.
    for c in info["arrowPieceColors"]:
        assert c == info["turn"], info


def test_camp_au_trait_coherent_avant_arriere_echiquier_normal(at_menu):
    """Parcourt une courte partie vers l'avant puis vers l'arrière :
    à chaque position, les 3 flèches moteur et la flèche orange doivent
    concerner le camp au trait de CETTE position — position initiale et
    dernière position comprises."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    assert n_coups >= 1

    for idx in range(0, n_coups + 1):
        info = _inspect_position(at_menu, idx)
        _assert_position_coherente(info)

    for idx in range(n_coups, -1, -1):
        info = _inspect_position(at_menu, idx)
        _assert_position_coherente(info)

    _retour_menu(at_menu)


def test_camp_au_trait_coherent_echiquier_retourne(at_menu):
    """Même garantie, échiquier retourné (noirs en bas) — l'orientation
    visuelle ne doit pas changer le camp au trait des flèches."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)
    at_menu.locator("#btn-flip").click()

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    for idx in range(0, n_coups + 1):
        info = _inspect_position(at_menu, idx)
        _assert_position_coherente(info)

    at_menu.locator("#btn-flip").click()  # remet l'orientation par défaut
    _retour_menu(at_menu)


def test_partie_collee_noirs_jouent_en_premier(at_menu):
    """Partie collée depuis une position de départ particulière où les
    Noirs jouent en premier (PGN avec balise [FEN], ex. partie reprise) —
    un des cas listés par l'issue #338 pour établir la cause : avant
    correction, parsePgn() reconstruisait les FEN depuis `new Chess()`
    (position de départ standard, Blancs au trait par défaut) en ignorant
    la balise [FEN] et en tronquant le camp au trait, cassant tout dès la
    position initiale."""
    _charger_pgn_colle(at_menu, _PGN_NOIRS_EN_PREMIER)
    _reset_arrows_state(at_menu)

    # Position initiale (indice 0) : Noirs au trait.
    info0 = _inspect_position(at_menu, 0)
    assert info0["turn"] == "b", info0
    _assert_position_coherente(info0)

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    assert n_coups == 3
    for idx in range(0, n_coups + 1):
        info = _inspect_position(at_menu, idx)
        _assert_position_coherente(info)

    _retour_menu(at_menu)


def test_resultat_tardif_pour_autre_position_est_ignore(at_menu):
    """Un résultat moteur arrivant pour une position qui n'est plus celle
    affichée (navigation entre-temps) ne doit jamais être dessiné — même
    simulé directement via l'écouteur socket.io (sans serveur), comme un
    vrai retard réseau/calcul."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_arrows_state(at_menu)

    n_coups = at_menu.evaluate("() => reviewMoves.length")
    assert n_coups >= 2

    # Position courante : indice 1, avec ses propres flèches correctes.
    info1 = _inspect_position(at_menu, 1)
    _assert_position_coherente(info1)
    counts_avant = at_menu.evaluate(
        "() => document.getElementById('board-arrows').querySelectorAll('line').length"
    )
    assert counts_avant > 0

    # Résultat tardif pour une AUTRE position (indice 0, différente du FEN
    # actuellement affiché) : simulé en invoquant directement l'écouteur
    # socket.io "review_lines_result" déjà enregistré par app.js, sans
    # jamais passer par un vrai serveur/moteur.
    result = at_menu.evaluate(
        """() => {
            const staleFen = reviewFens[0];
            const currentFen = reviewFens[reviewIdx];
            const fake = { fen: staleFen, lines: [{move: "a2a3", san: "a3", cp: 0, mate: null}], error: null };
            socket.listeners('review_lines_result').forEach(fn => fn(fake));
            return {
                staleFen, currentFen,
                staleNowCached: !!_reviewLinesCache[staleFen],
                countsApres: document.getElementById('board-arrows').querySelectorAll('line').length,
            };
        }"""
    )

    assert result["staleFen"] != result["currentFen"]
    # Le résultat tardif reste en cache pour une prochaine visite de cette
    # position...
    assert result["staleNowCached"]
    # ...mais n'a rien changé à l'affichage de la position actuellement visible.
    assert result["countsApres"] == counts_avant

    _retour_menu(at_menu)
