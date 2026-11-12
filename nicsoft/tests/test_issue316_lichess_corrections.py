"""
nicsoft/tests/test_issue316_lichess_corrections.py — AlChess

Issue #316 — trois défauts constatés lors d'essais réels en partie amicale
contre l'IA de Lichess (le mode #315 — orientation côté noirs — fonctionne) :

1. Nulle : une offre faite avant notre coup était silencieusement annulée
   par Lichess dès que nous jouions (notre coup ne portait jamais le
   paramètre offeringDraw), et le prochain gameState était alors interprété
   à tort comme un refus de l'adversaire. Corrigé dans
   LichessGame._submit_move() (nicsoft/modes/lichess/game.py) : le coup
   emporte désormais l'offre encore en attente. Un état "acceptée" distinct
   est aussi émis (lichess_draw_accepted) quand notre offre mène à la nulle.
2. Écran d'attente du premier coup des blancs (avant création de la partie
   chez Lichess) : fond uni, titre à faible contraste. Corrigé en réutilisant
   l'échiquier de mise en place (position de départ, blancs en bas — board +
   fonctions app.js généralisées avec un id/préfixe paramétrables) et le
   style `.card`/`.card-title-lg` (contraste suffisant), déjà utilisés par
   l'écran "position initiale" voisin.
3. Pendules Lichess qui ne suivaient pas les noms au retournement manuel de
   l'échiquier (bouton ⇅) : flipBoard() échangeait les noms mais pas les
   pendules, qui restaient câblées sur une convention fixe (haut=adversaire,
   bas=utilisateur). Corrigé via un drapeau _lichessClockRowsSwapped, suivi
   par la fonction _lichessRenderClock() (nouvelle, extraite du handler
   socket "lichess_clock").

Entièrement sans réseau ni matériel, comme les autres tests du mode Lichess
(faux transport/client, faux plateau). Les volets JS (fonctions pures ou à
DOM minimal, extraites du fichier réel — jamais réimplémentées) sont
exécutés via le binaire système `node`, comme test_issue315_lichess_orientation.py.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import chess
import pytest

from nicsoft.tests.test_issue311_lichess_sequencing import _make_bare_game

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / "nicsoft" / "web" / "static" / "app.js"
INDEX_HTML = REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html"


def _node_available() -> bool:
    return shutil.which("node") is not None


# ═══════════════════════════════════════════════════════════════════════
# 1. Nulle — l'offre part avec le coup, jamais de faux refus
# ═══════════════════════════════════════════════════════════════════════

def _started_white(game, client, monkeypatch):
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 2},
        "state": {"status": "started", "moves": ""},
    })
    assert game.user_color == "white"
    assert game.board.turn == chess.WHITE


def test_submit_move_envoie_offer_draw_quand_nulle_en_attente(monkeypatch):
    """Le coup physique soumis pendant que notre offre est en attente doit
    la porter (offeringDraw) pour que Lichess ne l'annule pas (issue #316,
    point 1 — cause racine du bug)."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    sent = []
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append((uci, offer_draw)))

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True

    game._submit_move("e2e4")
    assert sent == [("e2e4", True)]


def test_submit_move_sans_offre_en_attente_envoie_offer_draw_false(monkeypatch):
    """Sans offre en attente, le comportement habituel (aucun paramètre
    offeringDraw) ne doit pas changer."""
    game, events, _, _ = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    sent = []
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append((uci, offer_draw)))

    game._submit_move("e2e4")
    assert sent == [("e2e4", False)]


def test_nulle_proposee_puis_coup_ne_declenche_pas_de_faux_refus(monkeypatch):
    """Reproduit le scénario exact du bug rapporté : proposer la nulle,
    puis jouer son propre coup, ne doit jamais afficher « Nulle refusée ».
    Seule une vraie réponse de l'adversaire (ici : il joue sans accepter)
    doit déclencher ce message."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    sent = []
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append((uci, offer_draw)))

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert ("lichess_draw_proposed", {}) in events

    game._submit_move("e2e4")
    assert sent == [("e2e4", True)]  # l'offre part bien avec le coup

    # Lichess confirme notre coup en préservant l'offre (offeringDraw honoré).
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": True, "bdraw": False})
    assert game._my_draw_offer_pending is True
    assert ("lichess_draw_refused", {}) not in events

    # L'adversaire répond sans accepter : l'offre est alors réellement refusée.
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_refused", {}) in events


def test_offre_faite_pendant_le_tour_de_l_adversaire(monkeypatch):
    """L'utilisateur (noirs) propose la nulle alors que c'est aux blancs
    (l'IA) de jouer : l'offre part immédiatement (rien à y attacher dans
    l'instant), et le prochain coup physique de l'utilisateur doit, lui
    aussi, la conserver (issue #316, point 1)."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    draw_calls = []
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: draw_calls.append(accept))
    game._apply_game_full({
        "white": {"aiLevel": 2}, "black": {"id": "alain"},
        "state": {"status": "started", "moves": ""},
    })
    assert game.user_color == "black"
    assert game.board.turn == chess.WHITE  # tour de l'IA (adversaire)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert draw_calls == [True]
    assert game._my_draw_offer_pending is True

    # L'IA joue son coup : l'offre n'est pas encore remise en cause, c'est
    # toujours à l'utilisateur de répondre par son propre coup.
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": False, "bdraw": True})
    assert game._my_draw_offer_pending is True
    assert ("lichess_draw_refused", {}) not in events

    sent = []
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: sent.append((uci, offer_draw)))
    game._submit_move("e7e5")
    assert sent == [("e7e5", True)]


def test_nulle_acceptee_envoie_evenement_dedie(monkeypatch):
    """Quand notre propre offre mène directement à la nulle (l'adversaire
    accepte), un état « acceptée » distinct doit être émis — jamais
    « refusée » (issue #316, point 1)."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True

    game._apply_game_state({"status": "draw", "moves": "", "wdraw": True, "bdraw": True, "winner": ""})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_accepted", {}) in events
    assert ("lichess_draw_refused", {}) not in events
    assert game.game_over is True


def test_pat_sans_offre_en_cours_n_envoie_pas_nulle_acceptee(monkeypatch):
    """Une nulle qui ne vient pas de notre offre (ex. pat) ne doit jamais
    déclencher l'événement « acceptée » (pas de faux positif)."""
    game, events, _, _ = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)

    game._apply_game_state({"status": "stalemate", "moves": "", "winner": ""})
    assert ("lichess_draw_accepted", {}) not in events


@pytest.mark.parametrize("atype, accept_expected", [
    ("lichess_draw_accept", True),
    ("lichess_draw_refuse", False),
])
def test_reponse_a_une_offre_de_l_adversaire(monkeypatch, atype, accept_expected):
    """La proposition de nulle de l'adversaire (cas distinct de notre
    propre offre) doit toujours pouvoir être acceptée ou refusée — vérifié
    explicitement par l'issue #316, point 1."""
    game, events, _, actions = _make_bare_game(monkeypatch)
    client = game.client
    _started_white(game, client, monkeypatch)
    calls = []
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: calls.append(accept))

    game._apply_game_state({"status": "started", "moves": "", "bdraw": True})
    assert game._draw_offered_by_opponent is True

    actions.put({"type": atype})
    game._process_browser_actions()
    assert calls == [accept_expected]
    assert game._draw_offered_by_opponent is False


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_nouvelle_cle_i18n_nulle_acceptee(locale):
    path = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("toast.lichess_draw_accepted")


def test_appjs_wiring_nulle_acceptee():
    src = APP_JS.read_text(encoding="utf-8")
    assert 'socket.on("lichess_draw_accepted"' in src


# ═══════════════════════════════════════════════════════════════════════
# 2. Écran d'attente du premier coup — échiquier visible et lisible
# ═══════════════════════════════════════════════════════════════════════

def test_ecran_attente_premier_coup_contient_un_echiquier():
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(
        r'<div id="screen-lichess-wait-first-move"[^>]*class="([^"]*)"[^>]*>(.*?)</div>\s*<!-- ── Lichess : fin',
        html, re.DOTALL,
    )
    assert m, "écran d'attente du premier coup introuvable (balise ou structure modifiée ?)"
    screen_class, body = m.group(1), m.group(2)
    # Plus un fond uni sans échiquier (screen-connecting) : la même grille
    # échiquier + panneau que l'écran "position initiale" voisin.
    assert "screen-board-layout" in screen_class
    assert 'id="board-lichess-wait-first-move"' in body
    # Contraste suffisant : style de carte clair (comme pos_init.titre), pas
    # l'ancien ".connecting-msg" (gris clair sur fond clair, bug rapporté).
    assert 'class="card-title-lg"' in body
    assert 'class="connecting-msg"' not in body


def test_ecran_attente_premier_coup_garde_le_bouton_retour_et_la_bannicre_reconnexion():
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(
        r'<div id="screen-lichess-wait-first-move".*?</div>\s*<!-- ── Lichess : fin',
        html, re.DOTALL,
    )
    assert m
    body = m.group(0)
    assert 'id="lichess-wait-board-lost-firstmove"' in body
    assert 'data-action="back_menu"' in body


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_nouvelle_cle_i18n_attente_premier_coup(locale):
    path = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("lichess.attente_premier_coup.en_attente")


def test_appjs_bascule_vers_lichess_wait_first_move_construit_l_echiquier():
    src = APP_JS.read_text(encoding="utf-8")
    assert '_buildBoardPosInit(false, "board-lichess-wait-first-move", "lwfm")' in src
    assert 'renderBoardPosInit(' in src
    assert '"lwfm"' in src


# ── Exécution réelle (Node) des fonctions app.js généralisées ──────────────

def _extract(pattern: str, label: str, flags=re.DOTALL) -> str:
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(pattern, src, flags)
    assert m, f"{label} introuvable dans app.js — a-t-elle été renommée ?"
    return m.group(0)


def _board_render_js_prelude() -> str:
    """Prélude JS commun : DOM minimal (pas de dépendance jsdom) puis les
    vraies fonctions extraites d'app.js (jamais réimplémentées)."""
    esc_src           = _extract(r"function esc\([^)]*\)\s*\{.*?\n\}", "esc()")
    base_src          = _extract(r'const BASE = "[^"]*";', "BASE")
    pieces_src        = _extract(r"const PIECES = \{.*?\n\};", "PIECES")
    fen_to_board_src  = _extract(r"function fenToBoard\([^)]*\)\s*\{.*?\n\}", "fenToBoard()")
    build_src         = _extract(r"function _buildBoardPosInit\([^)]*\)\s*\{.*?\n\}", "_buildBoardPosInit()")
    render_src        = _extract(r"function renderBoardPosInit\([^)]*\)\s*\{.*?\n\}", "renderBoardPosInit()")
    return "\n".join([
        """
        class FakeClassList {
          constructor() { this._set = new Set(); }
          toggle(name, force) { if (force) this._set.add(name); else this._set.delete(name); }
          contains(name) { return this._set.has(name); }
        }
        class FakeElement {
          constructor(id) {
            this.id = id || ""; this.className = ""; this.innerHTML = "";
            this.textContent = ""; this.style = {}; this.classList = new FakeClassList();
          }
          appendChild(child) { if (child.id) _registry.set(child.id, child); }
        }
        const _registry = new Map();
        const document = {
          createElement() { return new FakeElement(); },
          getElementById(id) { return _registry.get(id) || null; },
        };
        function _register(id) { const el = new FakeElement(id); _registry.set(id, el); return el; }
        """,
        base_src, esc_src, pieces_src, fen_to_board_src, build_src, render_src,
    ])


@pytest.mark.skipif(not _node_available(), reason="binaire `node` absent de l'environnement")
def test_board_pos_init_generalise_fonctionne_avec_id_et_prefixe_distincts():
    """_buildBoardPosInit()/renderBoardPosInit() généralisées (issue #316,
    point 2) doivent toujours peindre la position de départ correctement
    quand on leur passe l'id/préfixe du nouvel écran d'attente, exactement
    comme pour l'écran "position initiale" d'origine."""
    script = _board_render_js_prelude() + """
        _register("board-lichess-wait-first-move");
        _buildBoardPosInit(false, "board-lichess-wait-first-move", "lwfm");
        renderBoardPosInit("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR", "lwfm");
        const out = {
          a1: document.getElementById("lwfm-0-0").innerHTML,
          h1: document.getElementById("lwfm-7-0").innerHTML,
          a8: document.getElementById("lwfm-0-7").innerHTML,
          h8: document.getElementById("lwfm-7-7").innerHTML,
          e4: document.getElementById("lwfm-4-3").innerHTML,
        };
        console.log(JSON.stringify(out));
    """
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip())
    assert "wR.svg" in out["a1"]
    assert "wR.svg" in out["h1"]
    assert "bR.svg" in out["a8"]
    assert "bR.svg" in out["h8"]
    assert out["e4"] == ""


# ═══════════════════════════════════════════════════════════════════════
# 3. Pendules qui suivent les noms au retournement manuel
# ═══════════════════════════════════════════════════════════════════════

def test_appjs_flip_board_echange_aussi_les_pendules():
    """flipBoard() doit échanger le drapeau de pendules juste à côté de
    l'échange des noms, et redessiner les pendules immédiatement — pas
    seulement attendre la prochaine poussée serveur (issue #316, point 3)."""
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"function flipBoard\(\)\s*\{.*?\n\}", src, re.DOTALL)
    assert m, "flipBoard() introuvable dans app.js"
    body = m.group(0)
    name_swap_idx = body.index("botName.textContent = tmp")
    clock_swap_idx = body.index("_lichessClockRowsSwapped = !_lichessClockRowsSwapped")
    clock_render_idx = body.index("_lichessRenderClock(_lichessLastClockData)")
    assert name_swap_idx < clock_swap_idx < clock_render_idx


@pytest.mark.skipif(not _node_available(), reason="binaire `node` absent de l'environnement")
def test_lichess_render_clock_suit_le_drapeau_de_retournement():
    """Exécute la vraie fonction _lichessRenderClock() (extraite d'app.js)
    pour vérifier que les pendules suivent le drapeau _lichessClockRowsSwapped
    dans les deux sens, y compris le marqueur "au trait" — reproduit le bug
    où, après retournement, le nom "Vous" se retrouvait à côté de la
    pendule de l'adversaire (issue #316, point 3)."""
    format_clock_src = _extract(r"function _lichessFormatClock\([^)]*\)\s*\{.*?\n\}", "_lichessFormatClock()")
    render_clock_src = _extract(r"function _lichessRenderClock\([^)]*\)\s*\{.*?\n\}", "_lichessRenderClock()")
    script = f"""
        class FakeClassList {{
          constructor() {{ this._set = new Set(); }}
          toggle(name, force) {{ if (force) this._set.add(name); else this._set.delete(name); }}
          contains(name) {{ return this._set.has(name); }}
        }}
        class FakeElement {{
          constructor(id) {{
            this.id = id; this.textContent = ""; this.classList = new FakeClassList();
          }}
        }}
        const _registry = new Map();
        const document = {{ getElementById(id) {{ return _registry.get(id) || null; }} }};
        _registry.set("clock-top", new FakeElement("clock-top"));
        _registry.set("clock-bottom", new FakeElement("clock-bottom"));

        {format_clock_src}
        {render_clock_src}

        let currentPlayerColor = "white";
        let _lichessClockRowsSwapped = false;
        const data = {{ white_ms: 5000, black_ms: 9000, turn: "white" }};

        _lichessRenderClock(data);
        const beforeFlip = {{
          top: document.getElementById("clock-top").textContent,
          bottom: document.getElementById("clock-bottom").textContent,
          topIsTurn: document.getElementById("clock-top").classList.contains("is-turn"),
          bottomIsTurn: document.getElementById("clock-bottom").classList.contains("is-turn"),
        }};

        _lichessClockRowsSwapped = true;  // retournement manuel — comme dans flipBoard()
        _lichessRenderClock(data);
        const afterFlip = {{
          top: document.getElementById("clock-top").textContent,
          bottom: document.getElementById("clock-bottom").textContent,
          topIsTurn: document.getElementById("clock-top").classList.contains("is-turn"),
          bottomIsTurn: document.getElementById("clock-bottom").classList.contains("is-turn"),
        }};

        console.log(JSON.stringify({{ beforeFlip, afterFlip }}));
    """
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip())

    # Avant tout retournement : haut = adversaire (noir, 9000ms), bas =
    # utilisateur (blanc, 5000ms) — c'est le tour des blancs (l'utilisateur),
    # donc le marqueur "au trait" est en bas.
    assert out["beforeFlip"]["top"] == "0:09"
    assert out["beforeFlip"]["bottom"] == "0:05"
    assert out["beforeFlip"]["topIsTurn"] is False
    assert out["beforeFlip"]["bottomIsTurn"] is True

    # Après retournement manuel : les pendules suivent les noms (haut =
    # utilisateur, bas = adversaire) — même pendant que l'horloge tourne,
    # avec les mêmes données serveur.
    assert out["afterFlip"]["top"] == "0:05"
    assert out["afterFlip"]["bottom"] == "0:09"
    assert out["afterFlip"]["topIsTurn"] is True
    assert out["afterFlip"]["bottomIsTurn"] is False


def test_appjs_lichess_init_reinitialise_le_drapeau_de_retournement():
    """Une nouvelle partie Lichess ne doit jamais hériter d'un retournement
    manuel de la partie précédente."""
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(r'socket\.on\("lichess_init",\s*\(data\)\s*=>\s*\{.*?\n\}\);', src, re.DOTALL)
    assert m, "handler lichess_init introuvable dans app.js"
    body = m.group(0)
    assert "_lichessClockRowsSwapped = false" in body
