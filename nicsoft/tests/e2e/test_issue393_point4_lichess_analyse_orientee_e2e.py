"""
nicsoft/tests/e2e/test_issue393_point4_lichess_analyse_orientee_e2e.py —
AlChess

Issue #393, point 4 : le bouton « Analyser sur Lichess » (après un
problème) ouvrait toujours lichess.org/analysis/<fen> sans orientation,
quelle que soit la couleur jouée par l'utilisateur dans le problème.
Confirmé le 26/11/2026 par lecture du code source public de lila
(app/controllers/UserAnalysis.scala::load -> getColor(), défaut "color" —
RequestGetter.scala) et de scalachess (Color.scala::fromName, strictement
"white"/"black" en minuscules) : le paramètre d'adresse "color" fixe
l'orientation, toute autre valeur étant ignorée côté Lichess — AlChess ne
doit donc jamais en envoyer une autre. `_lichessAnalysisColorParam` est
une fonction PURE, testée ici directement via `page.evaluate`."""


def test_couleur_blanc_acceptee(page):
    assert page.evaluate("() => _lichessAnalysisColorParam('white')") == "white"


def test_couleur_noir_acceptee(page):
    assert page.evaluate("() => _lichessAnalysisColorParam('black')") == "black"


def test_valeur_invalide_refusee(page):
    for invalide in ["White", "BLACK", "random", "", None, "w", "b"]:
        assert page.evaluate("(c) => _lichessAnalysisColorParam(c)", invalide) == "", invalide


def test_adresse_construite_avec_orientation_blancs(page):
    url = page.evaluate(
        """() => {
            window.__capturedUrl = null;
            const realOpen = window.open;
            window.open = (u) => { window.__capturedUrl = u; };
            _puzzleSetupFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
            _puzzleSetupColor = 'white';
            _lichessPuzzleAnalyseOnLichess();
            window.open = realOpen;
            return window.__capturedUrl;
        }"""
    )
    assert url.startswith("https://lichess.org/analysis/")
    assert url.endswith("?color=white")


def test_adresse_construite_avec_orientation_noirs(page):
    url = page.evaluate(
        """() => {
            window.__capturedUrl = null;
            const realOpen = window.open;
            window.open = (u) => { window.__capturedUrl = u; };
            _puzzleSetupFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1';
            _puzzleSetupColor = 'black';
            _lichessPuzzleAnalyseOnLichess();
            window.open = realOpen;
            return window.__capturedUrl;
        }"""
    )
    assert url.endswith("?color=black")


def test_couleur_absente_ou_invalide_naugmente_pas_ladresse(page):
    url = page.evaluate(
        """() => {
            window.__capturedUrl = null;
            const realOpen = window.open;
            window.open = (u) => { window.__capturedUrl = u; };
            _puzzleSetupFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
            _puzzleSetupColor = '';
            _lichessPuzzleAnalyseOnLichess();
            window.open = realOpen;
            return window.__capturedUrl;
        }"""
    )
    assert "color=" not in url


def test_copier_fen_ne_change_jamais_le_contenu_copie(page):
    """Le FEN copié reste celui de _puzzleSetupFen seul — jamais une
    orientation ajoutée (un FEN ne peut pas en porter une) : _puzzleSetupFen
    n'est lu nulle part ailleurs que via navigator.clipboard/le repli
    textarea (voir _lichessPuzzleCopyFen, inchangée par #393) — ce test
    vérifie que l'appel ne modifie jamais cette variable elle-même ni ne
    lève d'exception, orientation réglée ou non."""
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
    unchanged = page.evaluate(
        """(fen) => {
            _puzzleSetupFen = fen;
            _puzzleSetupColor = 'black';
            _lichessPuzzleCopyFen();
            return _puzzleSetupFen;
        }""",
        fen,
    )
    assert unchanged == fen
