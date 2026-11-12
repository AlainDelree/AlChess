"""
nicsoft/tests/e2e/test_issue316_lichess_e2e.py — AlChess

Issue #316, points 2 et 3 — vérification dans un vrai navigateur (Playwright),
comme nicsoft/tests/e2e/test_issue310_lichess_e2e.py :

2. L'écran d'attente du premier coup des blancs (avant création de la
   partie chez Lichess) doit afficher un échiquier en position de départ,
   et le titre doit avoir un contraste suffisant (ratio WCAG) — avant
   correctif, le titre utilisait un gris clair sur fond clair (ratio très
   inférieur au minimum AA de 4.5:1).
3. Les pendules Lichess doivent rester attachées au bon joueur (nom +
   valeur) après un retournement manuel de l'échiquier (bouton ⇅), y
   compris pendant qu'une nouvelle valeur de pendule arrive du serveur —
   vérifié dans les deux sens (couleur noire puis blanche).

Aucune partie Lichess réelle n'est créée (aucune requête réseau) : comme
dans test_issue310_lichess_e2e.py, les événements socket que le serveur
envoie normalement sont simulés en invoquant directement les callbacks déjà
enregistrées par `socket.on(...)` dans app.js.

Lancer : pytest nicsoft/tests/e2e/test_issue316_lichess_e2e.py -v
"""
import pytest

pytestmark = pytest.mark.slow

FEN_DEPART = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _dans_la_fenetre(page, selector):
    loc = page.locator(selector)
    if not loc.is_visible():
        return False
    box = loc.bounding_box()
    if box is None:
        return False
    viewport = page.viewport_size
    return box["x"] >= 0 and (box["x"] + box["width"]) <= viewport["width"]


def _declencher_evenement_socket_client(page, event, data):
    page.evaluate(
        "([event, data]) => { "
        "const cbs = socket.listeners(event) || []; "
        "if (cbs.length === 0) throw new Error('aucun listener pour ' + event); "
        "cbs.forEach((cb) => cb(data)); "
        "}",
        [event, data],
    )


def _contrast_ratio(page, fg_selector, bg_selector):
    """Ratio de contraste WCAG entre la couleur de texte de `fg_selector`
    et le fond de `bg_selector` — AA pour du texte normal exige >= 4.5."""
    return page.evaluate(
        """([fgSel, bgSel]) => {
            function parseRgb(s) {
                const m = s.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                return m ? [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])] : [255, 255, 255];
            }
            function channel(c) {
                c = c / 255;
                return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
            }
            function luminance([r, g, b]) {
                return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
            }
            const fg = parseRgb(getComputedStyle(document.querySelector(fgSel)).color);
            const bg = parseRgb(getComputedStyle(document.querySelector(bgSel)).backgroundColor);
            const l1 = luminance(fg), l2 = luminance(bg);
            const lighter = Math.max(l1, l2), darker = Math.min(l1, l2);
            return (lighter + 0.05) / (darker + 0.05);
        }""",
        [fg_selector, bg_selector],
    )


# ── Point 2 : écran d'attente du premier coup — échiquier + contraste ──────

@pytest.fixture
def at_lichess_wait_first_move(at_menu):
    _declencher_evenement_socket_client(at_menu, "app_state", {"state": "lichess_wait_first_move"})
    at_menu.wait_for_selector("#screen-lichess-wait-first-move", state="visible", timeout=5000)
    return at_menu


def test_attente_premier_coup_echiquier_visible_en_position_de_depart(at_lichess_wait_first_move):
    page = at_lichess_wait_first_move
    assert _dans_la_fenetre(page, "#board-lichess-wait-first-move")
    # Position de départ : 32 pièces, aucune case vide n'affiche d'image.
    assert page.locator("#board-lichess-wait-first-move img").count() == 32


def test_attente_premier_coup_titre_contraste_suffisant(at_lichess_wait_first_move):
    page = at_lichess_wait_first_move
    ratio = _contrast_ratio(
        page,
        "#screen-lichess-wait-first-move h2.card-title-lg",
        "#screen-lichess-wait-first-move .card",
    )
    # Seuil WCAG AA (texte normal) : 4.5:1 — avant correctif (gris clair sur
    # fond clair), ce ratio était largement inférieur à 2:1.
    assert ratio >= 4.5, f"contraste insuffisant ({ratio:.2f}:1) pour le titre de l'écran d'attente"


def test_attente_premier_coup_retour_menu(at_lichess_wait_first_move):
    at_lichess_wait_first_move.locator(
        "#screen-lichess-wait-first-move button[data-action=\"back_menu\"]"
    ).click()
    at_lichess_wait_first_move.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    assert at_lichess_wait_first_move.locator("#screen-menu").is_visible()


# ── Point 3 : pendules qui suivent les noms au retournement manuel ─────────

def _at_game_lichess(page, color, player="Testeur e2e", level=3):
    _declencher_evenement_socket_client(page, "app_state", {"state": "playing"})
    page.wait_for_selector("#screen-game", state="visible", timeout=5000)
    _declencher_evenement_socket_client(
        page, "lichess_init",
        {"fen": FEN_DEPART, "color": color, "level": level, "player": player},
    )
    return page


@pytest.mark.parametrize("color", ["white", "black"])
def test_pendules_suivent_les_noms_au_retournement_manuel(at_menu, color):
    """Reproduit le bug rapporté : après un retournement manuel, le nom
    "Vous" ne doit jamais se retrouver à côté de la pendule de l'adversaire
    — vérifié pour les deux couleurs utilisateur, flip puis déflip, et avec
    une pendule qui continue d'être mise à jour par le serveur."""
    page = _at_game_lichess(at_menu, color)

    # Pendule initiale (issue #311/#315 : convention haut=adversaire,
    # bas=utilisateur, indépendante de _boardFlipped).
    _declencher_evenement_socket_client(page, "lichess_clock", {
        "white_ms": 65000, "black_ms": 40000, "turn": "white",
    })
    top_name_before = page.locator("#player-top-name").inner_text()
    bottom_name_before = page.locator("#player-bottom-name").inner_text()
    top_clock_before = page.locator("#clock-top").inner_text()
    bottom_clock_before = page.locator("#clock-bottom").inner_text()
    # Le nom et la pendule affichés en haut doivent être ceux du même joueur
    # (ici l'adversaire, "IA" — jamais le nom du joueur à ce stade).
    assert "Testeur" not in top_name_before

    # Retournement manuel.
    page.locator("#btn-flip").click()

    top_name_after = page.locator("#player-top-name").inner_text()
    bottom_name_after = page.locator("#player-bottom-name").inner_text()
    top_clock_after = page.locator("#clock-top").inner_text()
    bottom_clock_after = page.locator("#clock-bottom").inner_text()

    # Les noms ont bien été échangés (comportement déjà correct avant #316).
    assert top_name_after == bottom_name_before
    assert bottom_name_after == top_name_before
    # Les pendules doivent avoir suivi le même échange — pas seulement les
    # noms (c'était exactement le bug : pendules restées en place).
    assert top_clock_after == bottom_clock_before
    assert bottom_clock_after == top_clock_before

    # Une mise à jour serveur pendant que la pendule tourne doit continuer à
    # respecter le retournement (pas seulement l'instant du clic).
    _declencher_evenement_socket_client(page, "lichess_clock", {
        "white_ms": 60000, "black_ms": 35000, "turn": "black",
    })
    top_clock_live = page.locator("#clock-top").inner_text()
    bottom_clock_live = page.locator("#clock-bottom").inner_text()
    # Après le flip, le haut montre l'utilisateur et le bas l'adversaire.
    user_ms_live = 60000 if color == "white" else 35000
    opponent_ms_live = 35000 if color == "white" else 60000
    assert top_clock_live == f"{user_ms_live // 60000}:{(user_ms_live // 1000) % 60:02d}"
    assert bottom_clock_live == f"{opponent_ms_live // 60000}:{(opponent_ms_live // 1000) % 60:02d}"

    # Un second retournement doit restaurer la convention d'origine.
    page.locator("#btn-flip").click()
    assert page.locator("#player-top-name").inner_text() == top_name_before
    assert page.locator("#player-bottom-name").inner_text() == bottom_name_before
