"""
nicsoft/tests/test_issue315_lichess_orientation.py — AlChess

Issue #315 : avant le premier essai du mode Lichess avec les noirs, lecture
de app.js (lichess_init / lichess_clock) révélait trois incohérences —
l'échiquier de l'écran n'était jamais retourné côté noirs, les noms et
pendules étaient inversés pour les noirs, et l'écran de mise en place
restait toujours orienté blancs en bas.

Deux volets testés ici :
1. Backend Python : la couleur résolue (plus jamais "random" à ce stade,
   voir lichess.py) est bien transmise jusqu'à l'écran de mise en place
   (set_app_state("position_initiale", {..., "color": ...})).
2. Frontend JS : la fonction réutilisable orientationIsFlipped() (app.js),
   qui décide de l'orientation à partir de la couleur, mappe bien noirs →
   retourné et blancs/valeur absente → non retourné. Exécutée via le
   binaire système `node` (déjà présent, aucune dépendance ajoutée) sur le
   texte réel de la fonction extrait d'app.js — pas une réimplémentation
   qui pourrait diverger silencieusement du code livré.

Le test de bout en bout (orientation de l'échiquier de jeu, de l'écran de
mise en place, noms/pendules, bouton de retournement) est couvert côté
Playwright par nicsoft/tests/e2e/test_issue315_lichess_orientation_e2e.py.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.tests.test_issue310_lichess_corrections import _TrackedFakeBoard

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / "nicsoft" / "web" / "static" / "app.js"


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ── 1. Backend : la couleur résolue atteint l'écran de mise en place ────────

class _FakeBoardPosInit:
    """Double minimal pour _wait_initial_position_lichess : `fen_sequence`
    est consommée dans l'ordre puis répétée sur sa dernière valeur (pas de
    get_fen() complet comme driver.py — seul le FEN board-only est lu)."""

    def __init__(self, fen_sequence):
        self._seq = list(fen_sequence)

    def get_fen(self):
        if len(self._seq) > 1:
            return self._seq.pop(0)
        return self._seq[0]

    def turn_off_all_leds(self):
        pass

    def signal_lights(self, sig):
        pass


INITIAL_BOARD_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


@pytest.mark.parametrize("color", ["white", "black"])
def test_wait_initial_position_transmet_la_couleur_resolue(monkeypatch, color):
    """La position de départ n'étant pas encore atteinte, l'écran de mise
    en place doit recevoir la couleur résolue de l'utilisateur à chaque
    mise à jour — c'est elle qui permettra à app.js d'orienter l'écran
    (issue #315, point 3)."""
    monkeypatch.setattr(lichess_launcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")
    states = []
    monkeypatch.setattr(
        lichess_launcher, "set_app_state",
        lambda state, data=None: states.append((state, data)),
    )
    board = _FakeBoardPosInit(["8/8/8/8/8/8/8/8", INITIAL_BOARD_FEN])

    lichess_launcher._wait_initial_position_lichess(board, color)

    position_payloads = [data for (state, data) in states if state == "position_initiale"]
    assert position_payloads, "aucun état position_initiale émis"
    assert all(p.get("color") == color for p in position_payloads)
    assert ("connecting", None) in states


def test_launch_lichess_couleur_aleatoire_est_resolue_avant_l_ecran_de_mise_en_place(monkeypatch):
    """La couleur "aléatoire" choisie en configuration doit être résolue
    (pile ou face) avant d'atteindre _wait_initial_position_lichess : ce
    dernier ne doit jamais recevoir la valeur "random" elle-même."""
    captured = {}

    def _fake_wait(nl_inst, color):
        captured["color"] = color

    monkeypatch.setattr(lichess_launcher, "_wait_initial_position_lichess", _fake_wait)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test"})
    board = _TrackedFakeBoard()
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher.random, "choice", lambda seq: "black")
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "menu", raising=False)

    class _Client:
        def __init__(self, token, transport=None):
            pass

        def create_ai_game(self, **kwargs):
            return {"id": "gid_315"}

        def stream_game(self, game_id, sleep=None):
            yield {
                "type": "gameFull", "white": {"id": "alain"}, "black": {"aiLevel": 1},
                "state": {"status": "aborted", "winner": "", "moves": ""},
            }

    monkeypatch.setattr(lichess_launcher, "GameClient", _Client)

    lichess_launcher.launch_lichess({"level": 1, "cadence": "15+10", "color": "random", "player": "Alain"})

    assert captured.get("color") == "black"


# ── 2. Frontend : correspondance couleur → orientation (app.js) ────────────

_FUNC_RE = re.compile(
    r"function orientationIsFlipped\([^)]*\)\s*\{.*?\n\}", re.DOTALL,
)


def _extract_orientation_function() -> str:
    text = APP_JS.read_text(encoding="utf-8")
    m = _FUNC_RE.search(text)
    assert m, "orientationIsFlipped() introuvable dans app.js — a-t-elle été renommée ?"
    return m.group(0)


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="binaire `node` absent de l'environnement")
@pytest.mark.parametrize(
    "color, expected_flipped",
    [
        ("black", True),
        ("white", False),
        (None, False),
        ("", False),
    ],
)
def test_orientation_is_flipped_correspondances(color, expected_flipped):
    """Exécute la vraie fonction orientationIsFlipped() d'app.js (extraite
    par regex, pas réimplémentée) via `node` : noirs → échiquier retourné,
    blancs ou couleur absente/vide → échiquier normal (issue #315, point
    1 — réutilisée aussi pour l'écran de mise en place, point 3)."""
    func_source = _extract_orientation_function()
    script = (
        f"{func_source}\n"
        f"console.log(JSON.stringify(orientationIsFlipped({json.dumps(color)})));"
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) is expected_flipped
