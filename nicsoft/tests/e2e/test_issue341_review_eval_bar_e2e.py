"""
Test e2e (issue #341) — écran d'analyse post-partie (#335) : barre
d'évaluation verticale à gauche de l'échiquier + légende à côté des
flèches toujours exprimée du point de vue des Blancs.

Même chemin que test_issue335_review_arrows_e2e.py / test_issue339_review_
arrow_outline_e2e.py pour atteindre l'écran de revue sans échiquier, sans
partie jouée et SANS AUCUN MOTEUR : menu "Analyse" → "Coller PGN", puis
résultat moteur simulé directement en écrivant `_reviewLinesCache[fen]`
côté client (comme le ferait `review_lines_result` reçu du serveur, déjà
exprimé point de vue Blancs par review_multipv.py) avant de rappeler
`renderReview()`. Le calcul de conversion/plafond lui-même est couvert
sans navigateur par test_issue341_review_eval_pov.py.
"""
import pytest

pytestmark = pytest.mark.slow

_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7"


def _charger_pgn_colle(page, pgn):
    page.locator("button.menu-btn-analyse").click()
    page.wait_for_selector("#panel-gameover", state="visible", timeout=5000)
    page.locator("#panel-gameover button[data-action=\"toggle_coller_pgn\"]").click()
    page.locator("#coller-pgn-input").fill(pgn)
    page.locator("button[data-action=\"charger_pgn_colle\"]").click()
    page.wait_for_selector("#btn-review-prev:not([disabled])", timeout=5000)


def _reset_state(page):
    """Remet l'état JS flèches/barre à son défaut — la page Playwright est
    partagée (session-scoped) entre tous les tests."""
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


def _injecter_resultat(page, idx, payload):
    """Injecte un résultat déjà calculé (lines/terminal/bar_fraction/
    bar_text) pour la position `idx`, exactement comme `review_lines_
    result` l'aurait fait, puis rappelle `renderReview()`."""
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


def _bar_state(page):
    return page.evaluate(
        """() => {
            const bar = document.getElementById('review-eval-bar');
            const white = document.getElementById('review-eval-bar-white');
            const black = document.getElementById('review-eval-bar-black');
            const labelWhite = document.getElementById('review-eval-bar-label-white');
            const labelBlack = document.getElementById('review-eval-bar-label-black');
            return {
                display: bar.style.display,
                neutral: bar.classList.contains('review-eval-bar-neutral'),
                flipped: bar.classList.contains('review-eval-bar-flipped'),
                whiteGrow: parseFloat(white.style.flexGrow || '0'),
                blackGrow: parseFloat(black.style.flexGrow || '0'),
                labelWhite: labelWhite.textContent,
                labelBlack: labelBlack.textContent,
                title: bar.title,
                ariaLabel: bar.getAttribute('aria-label'),
            };
        }"""
    )


def _retour_menu(page):
    page.locator("#panel-gameover button[data-action=\"back_menu\"]").click()
    page.wait_for_selector("#screen-menu", state="visible", timeout=5000)


# ── Présence de la barre, indépendante de la case « Afficher les flèches » ─

def test_barre_presente_meme_fleches_masquees(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "d2d4", "san": "d4", "cp": 50, "mate": None, "score_text": "+0.50"}],
        "bar_fraction": 0.62, "bar_text": "+0.50",
    })
    assert _bar_state(at_menu)["display"] != "none"

    at_menu.locator("#review-arrows-toggle").uncheck()
    etat = _bar_state(at_menu)
    assert etat["display"] != "none", "la barre doit rester affichée, la case ne la contrôle pas"
    # La légende, elle, doit bien être masquée (comportement #335 inchangé).
    legend_visible = at_menu.evaluate(
        "() => document.getElementById('review-arrows-legend').style.display !== 'none'"
    )
    assert not legend_visible

    at_menu.locator("#review-arrows-toggle").check()
    _retour_menu(at_menu)


# ── Bonne proportion / bon côté selon la situation ──────────────────────────

def test_proportion_avantage_blanc(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "d2d4", "san": "d4", "cp": 200, "mate": None, "score_text": "+2.00"}],
        "bar_fraction": 0.85, "bar_text": "+2.00",
    })
    etat = _bar_state(at_menu)
    assert etat["whiteGrow"] > etat["blackGrow"]
    assert etat["labelWhite"] == "+2.00"
    assert etat["labelBlack"] == ""
    assert "+2.00" in etat["title"]
    assert "+2.00" in etat["ariaLabel"]
    _retour_menu(at_menu)


def test_proportion_avantage_noir(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "a7a6", "san": "a6", "cp": -300, "mate": None, "score_text": "-3.00"}],
        "bar_fraction": 0.15, "bar_text": "-3.00",
    })
    etat = _bar_state(at_menu)
    assert etat["blackGrow"] > etat["whiteGrow"]
    assert etat["labelBlack"] == "-3.00"
    assert etat["labelWhite"] == ""
    _retour_menu(at_menu)


def test_mat_blanc_barre_pleine(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "d2d4", "san": "d4", "cp": None, "mate": 1, "score_text": "#1"}],
        "bar_fraction": 1.0, "bar_text": "#1",
    })
    etat = _bar_state(at_menu)
    assert etat["blackGrow"] == pytest.approx(0, abs=0.001)
    assert etat["labelWhite"] == "#1"
    _retour_menu(at_menu)


def test_mat_noir_barre_pleine(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "a7a6", "san": "a6", "cp": None, "mate": -2, "score_text": "-#2"}],
        "bar_fraction": 0.0, "bar_text": "-#2",
    })
    etat = _bar_state(at_menu)
    assert etat["whiteGrow"] == pytest.approx(0, abs=0.001)
    assert etat["labelBlack"] == "-#2"
    _retour_menu(at_menu)


# ── Échiquier normal / retourné ──────────────────────────────────────────

def test_orientation_normale_puis_retournee(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "d2d4", "san": "d4", "cp": 50, "mate": None, "score_text": "+0.50"}],
        "bar_fraction": 0.6, "bar_text": "+0.50",
    })
    assert _bar_state(at_menu)["flipped"] is False

    at_menu.locator("#btn-flip").click()
    etat = _bar_state(at_menu)
    assert etat["flipped"] is True
    # Les proportions (quel côté gagne) ne changent pas avec l'orientation —
    # seul le rendu visuel (haut/bas) s'inverse, piloté par la classe CSS.
    assert etat["whiteGrow"] > etat["blackGrow"]

    at_menu.locator("#btn-flip").click()  # remet l'orientation par défaut
    assert _bar_state(at_menu)["flipped"] is False
    _retour_menu(at_menu)


# ── Légende : signes corrects pour les 3 lignes, dont un mat lent ──────────

def test_legende_signes_corrects_dont_mat_lent(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [
            {"move": "d2d4", "san": "d4", "cp": None, "mate": 1,  "score_text": "#1",  "within_gap": True},
            {"move": "g1f3", "san": "Nf3", "cp": None, "mate": 5, "score_text": "#5",  "within_gap": True},
            # within_gap forcé à True : ce test vérifie le FORMAT (signes,
            # notation #N) des 3 lignes, pas le filtrage par écart (issue
            # #352) — sans ce champ, la 3e ligne (loin derrière les deux
            # mats) serait masquée et l'assertion "-1.20" ci-dessous échouerait.
            {"move": "a2a3", "san": "a3",  "cp": -120, "mate": None, "score_text": "-1.20", "within_gap": True},
        ],
        "bar_fraction": 1.0, "bar_text": "#1",
    })
    list_items = at_menu.locator("#review-arrows-list li")
    texts = [list_items.nth(i).inner_text() for i in range(list_items.count())]
    assert any("(#1)" in t for t in texts)        # mat des Blancs en 1
    assert any("(#5)" in t for t in texts)        # mat des Blancs en 5 (mat lent)
    assert any("(-1.20)" in t for t in texts)     # avantage Noir, aucun mat
    _retour_menu(at_menu)


def test_legende_partie_jouee_avec_les_noirs(at_menu):
    """Position où les Noirs sont au trait (après 1.e4) : le résultat reçu
    (déjà converti point de vue Blancs par le serveur) doit s'afficher tel
    quel, sans inversion côté client — même convention, quel que soit le
    camp au trait affiché."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 1, {
        "lines": [{"move": "g8f6", "san": "Nf6", "cp": -80, "mate": None, "score_text": "-0.80"}],
        "bar_fraction": 0.3, "bar_text": "-0.80",
    })
    list_items = at_menu.locator("#review-arrows-list li")
    texts = [list_items.nth(i).inner_text() for i in range(list_items.count())]
    assert any("-0.80" in t for t in texts)
    etat = _bar_state(at_menu)
    assert etat["labelBlack"] == "-0.80"
    _retour_menu(at_menu)


# ── Résultat tardif pour une autre position : ignoré (barre comprise) ─────

def test_resultat_tardif_autre_position_ignore_barre_comprise(at_menu):
    """Reproduit le VRAI chemin socket.on("review_lines_result") (pas une
    simulation de cache) via les écouteurs socket.io-client exposés
    (`socket.listeners(event)`, EventEmitter — v4.7.2 ici), pour vérifier
    que la barre respecte la même règle que la légende (#338) : un résultat
    arrivé tard pour une position qui n'est plus affichée est ignoré à
    l'écran (légende ET barre) mais reste en cache."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    fen0 = at_menu.evaluate("() => reviewFens[0]")
    fen1 = at_menu.evaluate("() => reviewFens[1]")
    # Empêche toute vraie requête "review_request_lines" pour la position 1
    # (voir docstring du fichier) : seul le résultat tardif simulé plus bas
    # doit pouvoir faire bouger quoi que ce soit, pour un test déterministe.
    at_menu.evaluate("(f) => { _reviewLinesPending[f] = true; }", fen1)

    # L'utilisateur est déjà passé à la position 1 quand le résultat moteur
    # de la position 0 arrive enfin du serveur.
    at_menu.evaluate("() => { reviewIdx = 1; renderReview(); }")
    etat_avant = _bar_state(at_menu)

    at_menu.evaluate(
        """(fen0) => {
            const data = {
                fen: fen0,
                lines: [{move: 'e2e4', san: 'e4', cp: 999, mate: null, score_text: '+9.99'}],
                error: null, terminal: null, bar_fraction: 1.0, bar_text: '+9.99',
            };
            socket.listeners('review_lines_result').forEach(h => h(data));
        }""",
        fen0,
    )

    # Rien n'a changé à l'écran (reviewIdx == 1, le résultat concernait la
    # position 0) — la barre affiche toujours ce qu'elle affichait avant.
    etat_apres = _bar_state(at_menu)
    assert etat_apres == etat_avant
    assert etat_apres["labelWhite"] != "+9.99"
    # Mais le résultat reste bien en cache pour une prochaine visite de la
    # position 0 (comme pour la légende, #338).
    cache_fen0 = at_menu.evaluate("(fen0) => _reviewLinesCache[fen0]", fen0)
    assert cache_fen0["bar_text"] == "+9.99"
    _retour_menu(at_menu)


# ── Position finale (mat/pat) : barre affiche le résultat sans moteur ─────

def test_position_finale_mat_barre_pleine_sans_legende(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [], "terminal": "checkmate", "bar_fraction": 0.0, "bar_text": "-#",
    })
    etat = _bar_state(at_menu)
    assert etat["whiteGrow"] == pytest.approx(0, abs=0.001)
    assert etat["labelBlack"] == "-#"
    legend_visible = at_menu.evaluate(
        "() => document.getElementById('review-arrows-legend').style.display !== 'none'"
    )
    assert not legend_visible
    _retour_menu(at_menu)


def test_position_finale_nulle_barre_a_moitie(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [], "terminal": "draw", "bar_fraction": 0.5, "bar_text": "½",
    })
    etat = _bar_state(at_menu)
    assert etat["whiteGrow"] == pytest.approx(etat["blackGrow"], abs=0.01)
    _retour_menu(at_menu)


# ── Calcul en cours / aucune ligne : état neutre discret ──────────────────

def test_etat_neutre_pendant_calcul_puis_defilement_rapide(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    n_coups = at_menu.evaluate("() => reviewMoves.length")
    indices = list(range(min(3, n_coups + 1)))
    # Marque chaque position comme "déjà en vol" (_reviewLinesPending) AVANT
    # tout renderReview() : empêche _reviewUpdateArrows() d'émettre une
    # vraie requête "review_request_lines" vers le serveur de test (qui,
    # lui, peut avoir un vrai Stockfish disponible sur la machine — hors
    # périmètre de ce test e2e isolé, voir docstring du fichier). Sans
    # cache ni requête en vol, l'état neutre reste donc déterministe.
    at_menu.evaluate(
        "(idxs) => { idxs.forEach(i => { _reviewLinesPending[reviewFens[i]] = true; }); }",
        indices,
    )
    at_menu.evaluate("() => { reviewIdx = 0; renderReview(); }")
    etat = _bar_state(at_menu)
    assert etat["neutral"] is True
    assert etat["labelWhite"] == "" and etat["labelBlack"] == ""

    # Défilement rapide des coups (plusieurs positions sans résultat) :
    # ne doit jamais lever d'exception et reste discret à chaque étape.
    for idx in indices:
        at_menu.evaluate("(i) => { reviewIdx = i; renderReview(); }", idx)
    etat = _bar_state(at_menu)
    assert etat["neutral"] is True
    _retour_menu(at_menu)


# ── Partie Lichess terminée : la barre reste présente (issue #345) ───────
# Avant #345, _reviewUpdateEvalBar() masquait la barre dès que
# `_gameSource === "lichess"`, pensée à l'origine (#341) pour la règle de
# fair-play Lichess (#333) — mais cette fonction n'est de toute façon
# jamais atteinte pendant une partie Lichess EN COURS (écran "game_over"
# uniquement). Une fois la partie terminée, la barre doit au contraire
# rester visible comme pour toute autre source.

def test_presente_apres_partie_lichess_terminee(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "d2d4", "san": "d4", "cp": 50, "mate": None, "score_text": "+0.50"}],
        "bar_fraction": 0.6, "bar_text": "+0.50",
    })
    assert _bar_state(at_menu)["display"] != "none"

    at_menu.evaluate("() => { _gameSource = 'lichess'; renderReview(); }")
    assert _bar_state(at_menu)["display"] != "none"

    at_menu.evaluate("() => { _gameSource = 'niclink'; }")
    _retour_menu(at_menu)


# ── Libellés d'accessibilité dans les 3 langues ────────────────────────────

def test_libelles_trois_langues(at_menu):
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "d2d4", "san": "d4", "cp": 50, "mate": None, "score_text": "+0.50"}],
        "bar_fraction": 0.6, "bar_text": "+0.50",
    })
    locale_initiale = at_menu.evaluate("() => i18n.locale()")
    try:
        for locale in ("fr", "en", "de"):
            at_menu.evaluate("async (l) => { await i18n.load(l); }", locale)
            at_menu.evaluate("() => { reviewIdx = 0; renderReview(); }")
            etat = _bar_state(at_menu)
            assert etat["ariaLabel"], locale
            assert "+0.50" in etat["ariaLabel"], (locale, etat["ariaLabel"])
            assert etat["ariaLabel"] == etat["title"]
    finally:
        at_menu.evaluate("(l) => i18n.load(l)", locale_initiale)
    _retour_menu(at_menu)


# ── Régression : la barre ne déplace jamais #btn-review-next (cf. #332) ──

def test_barre_ne_deplace_pas_navigation(at_menu):
    """Un résultat (même injecté, voir docstring du fichier) est toujours
    présent avant chaque mesure : sans cette précaution, un vrai moteur
    disponible sur la machine de test pourrait répondre entre deux mesures
    et faire bouger d'autres éléments du panneau (ex. bouton "meilleur
    coup") pour une raison sans rapport avec la barre elle-même.

    Depuis #345, `_gameSource` ne masque plus la barre (elle reste
    toujours visible sur l'écran d'analyse, voir test_presente_apres_
    partie_lichess_terminee) : la bascule présent/absent ci-dessous se
    fait donc directement sur le résultat en cache (null = pas de FEN
    affiché, cas qui masque réellement la barre)."""
    _charger_pgn_colle(at_menu, _PGN)
    _reset_state(at_menu)
    _injecter_resultat(at_menu, 0, {
        "lines": [{"move": "d2d4", "san": "d4", "cp": 50, "mate": None, "score_text": "+0.50"}],
        "bar_fraction": 0.6, "bar_text": "+0.50",
    })
    box_avec_barre = at_menu.locator("#btn-review-next").bounding_box()

    at_menu.evaluate("() => { _reviewUpdateEvalBar(null, null); }")  # barre masquée
    box_sans_barre = at_menu.locator("#btn-review-next").bounding_box()

    at_menu.evaluate("() => { renderReview(); }")  # barre réaffichée (relit le cache)
    box_avec_barre_2 = at_menu.locator("#btn-review-next").bounding_box()

    assert box_avec_barre == box_sans_barre == box_avec_barre_2
    _retour_menu(at_menu)
