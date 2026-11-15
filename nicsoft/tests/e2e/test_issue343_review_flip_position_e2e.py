"""
Test e2e (issue #343) — écran d'analyse post-partie : retourner l'échiquier
(flipBoard()) sur une position quelconque doit redessiner les pièces de
CETTE position (jamais la position de départ), redessiner les flèches des
meilleurs coups/du coup joué dans la nouvelle orientation, et laisser
l'historique/le titre de navigation inchangés — barre d'évaluation et
légende restent celles déjà affichées (valeurs indépendantes de
l'orientation, voir #341).

Cause du défaut (établie par relecture directe de flipBoard(), confirmée en
retirant temporairement le correctif dans ce même worktree, sans écrire sur
l'arbre principal) : flipBoard() redessinait les pièces depuis `currentFen`
— une variable globale que ni "Analyse → Coller PGN" ni la reprise d'une
partie jouée dans AlChess ne mettent à jour (ces deux chemins alimentent
seulement `reviewFens`/`reviewIdx`, comme le fait le code de app_state pour
`data.state === "game_over"`) — au lieu de `reviewFens[reviewIdx]`, la
position réellement affichée. `currentFen` reste donc à sa valeur par
défaut, la position de départ, d'où les pièces retrouvant leur place
initiale après un flip. Les flèches n'étaient, de leur côté, jamais
redessinées du tout après un flip (coordonnées pixel figées au moment du
tracé, dépendantes de `_boardFlipped` via `boardSquareCenter()`) : ce défaut
remonte à #335 (introduction des flèches), flipBoard() n'ayant jamais été
mis à jour pour les rafraîchir. Bug pré-existant à #339/#341, pas introduit
par eux : flipBoard() date d'un commit antérieur à #335 lui-même ; la barre
d'évaluation (#341), elle, recalculait déjà correctement sa valeur ET son
orientation CSS depuis reviewFens[reviewIdx] dans ce même flipBoard() —
seules les pièces et les flèches étaient en cause.

Même chemin que test_issue335_review_arrows_e2e.py / test_issue341_review_
eval_bar_e2e.py pour atteindre l'écran de revue sans échiquier, sans partie
jouée et SANS AUCUN MOTEUR : menu "Analyse" → "Coller PGN", résultat moteur
simulé en écrivant `_reviewLinesCache[fen]` côté client.
"""
import pytest

pytestmark = pytest.mark.slow

_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7"


def _desactiver_requetes_moteur(page):
    """Neutralise socket.emit("review_request_lines", ...) pour toute la
    durée du test (jusqu'à _reactiver_requetes_moteur) : le serveur de test
    peut avoir un vrai moteur disponible sur la machine (voir docstring du
    fichier), et le chargement d'un PGN collé affiche AUTOMATIQUEMENT le
    DERNIER coup (reviewIdx = reviewFens.length - 1, voir socket.on
    "app_state" côté client) — c'est-à-dire exactement la position que ces
    tests examinent le plus souvent. Sans neutralisation, une requête
    réelle partie à ce moment-là (avant même que le test ait eu la main)
    peut recevoir sa réponse en plein milieu des assertions — y compris
    dans un test SUIVANT si la même position est rechargée (même PGN) — et
    écraser silencieusement les flèches/valeurs injectées par le test.
    _reviewLinesPending seul ne suffit pas : il bloque une NOUVELLE requête
    mais pas l'arrivée tardive d'une réponse déjà partie avant le test."""
    page.evaluate(
        """() => {
            if (!socket.__origEmit343) socket.__origEmit343 = socket.emit.bind(socket);
            socket.emit = function(event, ...args) {
                if (event === 'review_request_lines') return;
                return socket.__origEmit343(event, ...args);
            };
        }"""
    )


def _reactiver_requetes_moteur(page):
    page.evaluate(
        """() => {
            if (socket.__origEmit343) { socket.emit = socket.__origEmit343; }
        }"""
    )


def _charger_pgn_colle(page, pgn):
    _desactiver_requetes_moteur(page)
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def _reset_state(page):
    """Remet l'état JS flèches/barre/orientation à son défaut — la page
    Playwright est partagée (session-scoped) entre tous les tests."""
    page.evaluate(
        """() => {
            _reviewArrowsEnabled = true;
            document.getElementById('review-arrows-toggle').checked = true;
            _reviewLinesCache = {};
            _reviewLinesPending = {};
            _gameSource = 'niclink';
            if (_boardFlipped) { flipBoard(); }
        }"""
    )


def _retour_menu(page):
    _reactiver_requetes_moteur(page)
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


def _goto_review_idx(page, index):
    page.evaluate("(i) => { reviewIdx = i; renderReview(); }", index)


def _pieces_dom(page):
    """Grille case -> pièce réellement affichée dans le DOM (comparable au
    résultat de fenToBoard())."""
    return page.evaluate(
        """() => {
            const out = {};
            for (let rank = 0; rank <= 7; rank++) {
              for (let file = 0; file <= 7; file++) {
                const id = `${file}-${rank}`;
                const sq = document.getElementById(`sq-${id}`);
                out[id] = sq ? sq.innerHTML : null;
              }
            }
            return out;
        }"""
    )


def _pieces_attendues(page):
    """Reproduit exactement le rendu de renderBoard() (grille FEN -> glyphe
    Unicode via PIECES) pour comparer aux textContent du DOM."""
    return page.evaluate(
        """() => {
            const grid = fenToBoard(reviewFens[reviewIdx]);
            const out = {};
            for (let rank = 0; rank <= 7; rank++) {
              for (let file = 0; file <= 7; file++) {
                const id = `${file}-${rank}`;
                const piece = grid[id];
                out[id] = piece ? (PIECES[piece] || piece) : "";
              }
            }
            return out;
        }"""
    )


def _nav_state(page):
    return page.evaluate(
        """() => {
            return {
                reviewIdx,
                moveInfo: document.getElementById('review-move-info').textContent,
                moveSan: document.getElementById('review-move-san').textContent,
                historique: document.getElementById('historique').innerHTML,
            };
        }"""
    )


def _injecter_resultat(page, idx, payload):
    return page.evaluate(
        """({idx, payload}) => {
            reviewIdx = idx;
            const fen = reviewFens[idx];
            _reviewLinesCache[fen] = {
                lines: payload.lines || [],
                error: null,
                terminal: payload.terminal || null,
                bar_fraction: (payload.bar_fraction === undefined) ? null : payload.bar_fraction,
                bar_text: payload.bar_text || null,
            };
            renderReview();
            return fen;
        }""",
        {"idx": idx, "payload": payload},
    )


def _arrows_html(page):
    return page.evaluate("() => document.getElementById('board-arrows').innerHTML")


def _nb_fleches_tracees(page):
    """Nombre de <line> réellement tracées — ignore les <defs> (marqueurs
    de flèches) toujours présents dans le SVG, même quand aucune flèche
    n'est dessinée (clearReviewArrows() les conserve)."""
    return page.evaluate(
        "() => document.querySelectorAll('#board-arrows .review-arrow-line').length"
    )


def _bar_etat(page):
    return page.evaluate(
        """() => {
            return {
                whiteGrow: document.getElementById('review-eval-bar-white').style.flexGrow,
                blackGrow: document.getElementById('review-eval-bar-black').style.flexGrow,
                labelWhite: document.getElementById('review-eval-bar-label-white').textContent,
                labelBlack: document.getElementById('review-eval-bar-label-black').textContent,
                flipped: document.getElementById('review-eval-bar').classList.contains('review-eval-bar-flipped'),
            };
        }"""
    )


def _legende_textes(page):
    items = page.locator("#review-arrows-list li")
    return [items.nth(i).inner_text() for i in range(items.count())]


# ── Pièces : jamais la position de départ, quelle que soit la position ────

def test_pieces_bonne_position_apres_flip_premier_milieu_dernier_coup(at_menu):
    page = at_menu
    _charger_pgn_colle(page, _PGN)
    _reset_state(page)
    n = page.evaluate("() => reviewFens.length")
    mid = n // 2

    for idx in (0, mid, n - 1):
        _goto_review_idx(page, idx)
        nav_avant = _nav_state(page)

        # normal -> retourné
        page.locator("#btn-flip").click()
        assert _pieces_dom(page) == _pieces_attendues(page), f"idx={idx} normal->retourné"
        assert _nav_state(page) == nav_avant, f"idx={idx} normal->retourné : navigation modifiée"

        # retourné -> normal
        page.locator("#btn-flip").click()
        assert _pieces_dom(page) == _pieces_attendues(page), f"idx={idx} retourné->normal"
        assert _nav_state(page) == nav_avant, f"idx={idx} retourné->normal : navigation modifiée"

    _retour_menu(page)


# ── Flèches : redessinées dans la nouvelle orientation, bonnes cases ──────

def test_fleches_redessinees_bonne_orientation_apres_flip(at_menu):
    page = at_menu
    _charger_pgn_colle(page, _PGN)
    _reset_state(page)
    n = page.evaluate("() => reviewFens.length")

    _injecter_resultat(page, n - 1, {
        "lines": [{"move": "g1f3", "san": "Nf3", "cp": 40, "mate": None, "score_text": "+0.40"}],
        "bar_fraction": 0.6, "bar_text": "+0.40",
    })
    avant = _arrows_html(page)
    assert avant, "les flèches devraient être dessinées avant le flip"

    page.locator("#btn-flip").click()
    apres = _arrows_html(page)
    assert apres, "les flèches devraient rester dessinées après le flip"
    assert apres != avant, "les flèches doivent être redessinées (coordonnées différentes) après le flip"

    # Les coordonnées redessinées doivent correspondre à boardSquareCenter()
    # dans la NOUVELLE orientation (celle que le tracé aurait dû utiliser).
    coherent = page.evaluate(
        """() => {
            const board = document.getElementById('board');
            const size = board.getBoundingClientRect().width / 8;
            const p1 = boardSquareCenter('g1', size);
            const p2 = boardSquareCenter('f3', size);
            const line = document.querySelector('#board-arrows .review-arrow-line');
            if (!line) return false;
            const close = (a, b) => Math.abs(a - b) < 0.5;
            return close(parseFloat(line.getAttribute('x1')), p1.x)
                && close(parseFloat(line.getAttribute('y1')), p1.y)
                && close(parseFloat(line.getAttribute('x2')), p2.x)
                && close(parseFloat(line.getAttribute('y2')), p2.y);
        }"""
    )
    assert coherent, "la flèche redessinée ne correspond pas à la nouvelle orientation"

    # Second flip : retour à l'orientation normale, cohérence toujours vraie.
    page.locator("#btn-flip").click()
    coherent2 = page.evaluate(
        """() => {
            const board = document.getElementById('board');
            const size = board.getBoundingClientRect().width / 8;
            const p1 = boardSquareCenter('g1', size);
            const line = document.querySelector('#board-arrows .review-arrow-line');
            return line && Math.abs(parseFloat(line.getAttribute('x1')) - p1.x) < 0.5;
        }"""
    )
    assert coherent2
    _retour_menu(page)


# ── Barre et légende : valeurs inchangées (indépendantes de l'orientation) ─

def test_barre_et_legende_valeurs_inchangees_apres_flip(at_menu):
    page = at_menu
    _charger_pgn_colle(page, _PGN)
    _reset_state(page)
    n = page.evaluate("() => reviewFens.length")

    _injecter_resultat(page, n - 1, {
        "lines": [
            {"move": "g1f3", "san": "Nf3", "cp": 40, "mate": None, "score_text": "+0.40"},
            {"move": "b1c3", "san": "Nc3", "cp": -10, "mate": None, "score_text": "-0.10"},
        ],
        "bar_fraction": 0.6, "bar_text": "+0.40",
    })
    bar_avant = _bar_etat(page)
    legende_avant = _legende_textes(page)

    page.locator("#btn-flip").click()
    bar_apres = _bar_etat(page)
    legende_apres = _legende_textes(page)

    assert bar_apres["whiteGrow"] == bar_avant["whiteGrow"]
    assert bar_apres["blackGrow"] == bar_avant["blackGrow"]
    assert bar_apres["labelWhite"] == bar_avant["labelWhite"]
    assert bar_apres["labelBlack"] == bar_avant["labelBlack"]
    assert bar_apres["flipped"] is True and bar_avant["flipped"] is False
    assert legende_apres == legende_avant
    _retour_menu(page)


# ── Flèches masquées : le flip ne les fait pas réapparaître à tort ────────

def test_flip_avec_fleches_masquees(at_menu):
    page = at_menu
    _charger_pgn_colle(page, _PGN)
    _reset_state(page)
    n = page.evaluate("() => reviewFens.length")

    _injecter_resultat(page, n - 1, {
        "lines": [{"move": "g1f3", "san": "Nf3", "cp": 40, "mate": None, "score_text": "+0.40"}],
        "bar_fraction": 0.6, "bar_text": "+0.40",
    })
    page.locator("#review-arrows-toggle").uncheck()
    assert _nb_fleches_tracees(page) == 0

    page.locator("#btn-flip").click()
    assert _nb_fleches_tracees(page) == 0, "les flèches doivent rester masquées après le flip"
    # La barre, elle, doit rester visible et correcte (indépendante de la case).
    assert _bar_etat(page)["labelWhite"] == "+0.40"
    # Les pièces doivent quand même être celles de la position affichée.
    assert _pieces_dom(page) == _pieces_attendues(page)

    page.locator("#review-arrows-toggle").check()
    _retour_menu(page)


# ── Flip pendant la lecture automatique : aucune régression ───────────────

def test_flip_pendant_lecture_automatique(at_menu):
    page = at_menu
    _charger_pgn_colle(page, _PGN)
    _reset_state(page)
    _goto_review_idx(page, 0)

    page.locator("#btn-autoplay").click()
    page.wait_for_function("() => reviewIdx > 0", timeout=5000)

    page.locator("#btn-flip").click()
    assert _pieces_dom(page) == _pieces_attendues(page), "pièces incorrectes après un flip pendant la lecture automatique"

    idx_apres_flip = page.evaluate("() => reviewIdx")
    page.wait_for_function(
        "(i) => reviewIdx > i",
        arg=idx_apres_flip,
        timeout=6000,
    )
    assert _pieces_dom(page) == _pieces_attendues(page), "la lecture automatique continue de dessiner les bonnes pièces après le flip"

    # Arrêt propre de la lecture automatique avant de quitter l'écran.
    autoplay_actif = page.evaluate("() => !!_autoPlayTimer")
    if autoplay_actif:
        page.locator("#btn-autoplay").click()
    page.evaluate("() => { if (_boardFlipped) flipBoard(); }")
    _retour_menu(page)


# ── Revue d'une partie jouée dans AlChess (pas un PGN collé) : même chemin ─
# app_state "game_over" que la reprise ci-dessus (history_fen/history_moves),
# simulée ici directement côté client sans passer par un vrai moteur/driver.

def test_pieces_bonne_position_apres_flip_partie_niclink_simulee(at_menu):
    page = at_menu
    _desactiver_requetes_moteur(page)
    page.evaluate(
        """() => {
            socket.listeners('app_state').forEach(h => h({
                state: 'game_over',
                skip: false,
                source: 'niclink',
                title: 'Partie terminée',
                result: '1-0',
                history_fen: [
                    'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
                    'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
                    'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
                ],
                history_moves: [
                    {uci: 'e2e4', san: 'e4', color: 'white', qualite: 'bon'},
                    {uci: 'e7e5', san: 'e5', color: 'black', qualite: 'bon'},
                ],
            }));
        }"""
    )
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    _reset_state(page)

    _goto_review_idx(page, 2)
    page.locator("#btn-flip").click()
    assert _pieces_dom(page) == _pieces_attendues(page)

    page.locator("#btn-flip").click()  # remet l'orientation par défaut
    _retour_menu(page)
