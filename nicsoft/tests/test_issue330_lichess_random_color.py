"""
nicsoft/tests/test_issue330_lichess_random_color.py — AlChess

Issue #330 : essai réel d'Alain le 14/11/2026, après #329. Une recherche
d'adversaire humain en 15+10 avec les blancs est refusée par Lichess avec
« You must also play some games as Black. » (HTTP 400) — règle de Lichess
qui impose d'équilibrer les couleurs quand le compte demande toujours la
même. Le choix "Aléatoire" de l'écran de recherche contre un humain était
jusqu'ici tiré PAR AlChess avant la recherche (pile ou face local, voir
issue #311) : Lichess recevait donc toujours une couleur précise, et
refusait la moitié du temps.

Établi par lecture du code source public de lila (modules/lobby/src/main/
BoardApiHookStream.scala::mustPlayAsColor, app/controllers/Setup.scala,
lus le 14/11/2026) : le refus d'équilibre des couleurs est sauté
ENTIÈREMENT quand la couleur demandée à board/seek est "random" (donc
vide ici, cf. doc/specs/tags/board/api-board-seek.yaml du dépôt
lichess-org/api : « Better left empty to automatically get 50% white »).
Ce fichier vérifie que :

  1. une recherche "aléatoire" envoie bien AUCUN paramètre `color` à
     board/seek (jamais une valeur résolue localement) ;
  2. l'écran de mise en place reste affiché (orientation arbitraire, la
     position de départ étant identique pour les deux camps) ;
  3. la couleur réelle obtenue (via l'évènement gameStart, qui peut être
     n'importe laquelle des deux) atteint correctement LichessGame/
     lichess_init pour l'orientation réelle de l'échiquier/noms/pendules ;
  4. une recherche à couleur précise (blancs/noirs) est inchangée ;
  5. le refus d'équilibre des couleurs affiche le texte de Lichess ET une
     explication (clé i18n dédiée, dans les 3 langues) ; un autre refus
     400 n'affiche que le texte de Lichess, comme avant ;
  6. la partie contre l'IA (_run_lichess/launch_lichess) n'est pas
     modifiée par cette issue — elle continue de résoudre "aléatoire"
     localement (random.choice), ce qui est correct car jamais concernée
     par la règle d'équilibre des couleurs (parties IA jamais comptées,
     voir rapport de clôture).

Règle absolue de cette issue (comme pour toutes les précédentes sur
Lichess) : AUCUNE connexion réseau réelle, AUCUNE recherche/partie réelle
sur lichess.org — entièrement sans réseau (faux transport/client) et sans
matériel (faux plateau scripté). Voir aussi
nicsoft/tests/conftest.py::_guard_no_real_lichess_network.
"""
import json

import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.lichess import _classify_seek_error_event
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.errors import detect_color_balance_refusal
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.game_log import GameLog
from nicsoft.tests.test_issue311_lichess_sequencing import INITIAL_FEN_W, _ScriptedBoard
from nicsoft.tests.test_issue327_lichess_human import (
    _FakeHandleForClient,
    _gamestart_line,
    _HumanGameClient,
)


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ═══════════════════════════════════════════════════════════════════════
# 1. detect_color_balance_refusal() — reconnaissance du texte exact de lila
#    (établi par lecture du code source public, voir en-tête de module).
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("message,expected", [
    ("You must also play some games as Black", "black"),
    ("You must also play some games as White", "white"),
    ("you must also play some games as black.", "black"),  # casse/ponctuation
    ("Game already in progress", ""),
    ("Invalid clock", ""),
    ("", ""),
])
def test_detect_color_balance_refusal(message, expected):
    assert detect_color_balance_refusal(message) == expected


# ═══════════════════════════════════════════════════════════════════════
# 2. _classify_seek_error_event — explication fr/en/de pour le refus
#    d'équilibre, texte de Lichess seul pour tout autre refus 400.
# ═══════════════════════════════════════════════════════════════════════

def test_classification_refus_equilibre_couleur_a_sa_propre_cle():
    ev = {"status_code": 400, "detail": "You must also play some games as Black"}
    key, vars_ = _classify_seek_error_event(ev)
    assert key == "toast.lichess_refus_equilibre_couleur"
    assert "You must also play some games as Black" in vars_["detail"]


def test_classification_autre_refus_400_inchangee():
    ev = {"status_code": 400, "detail": "Already playing too many games"}
    key, vars_ = _classify_seek_error_event(ev)
    assert key == "toast.lichess_refus_requete"
    assert "Already playing too many games" in vars_["detail"]


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_cle_refus_equilibre_presente_et_distincte_dans_les_3_langues(locale):
    import pathlib
    path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("toast.lichess_refus_equilibre_couleur"), f"clé absente/vide dans {locale}.json"
    assert data["toast.lichess_refus_equilibre_couleur"] != data.get("toast.lichess_refus_requete")
    assert "{detail}" in data["toast.lichess_refus_equilibre_couleur"]


# ═══════════════════════════════════════════════════════════════════════
# 3. Lanceur humain — "aléatoire" n'envoie plus de couleur précise.
# ═══════════════════════════════════════════════════════════════════════

class _RecordingSeekClient(_HumanGameClient):
    """Enregistre les arguments positionnels reçus par open_seek_stream
    (couleur demandée) avant de déléguer au double existant (#327)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seek_calls = []

    def open_seek_stream(self, *a, **kw):
        self.seek_calls.append((a, kw))
        return super().open_seek_stream(*a, **kw)


def _run_human_seek(monkeypatch, chosen_color, client):
    board = _ScriptedBoard([INITIAL_FEN_W])
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "GameClient", lambda token: client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    monkeypatch.setattr(lichess_launcher, "get_app_state", lambda: "connecting")

    def _no_random_choice(seq):
        raise AssertionError(
            "random.choice() appelé pour la recherche humaine — 'aléatoire' ne doit "
            "plus être résolu localement (issue #330)"
        )
    monkeypatch.setattr(lichess_launcher.random, "choice", _no_random_choice)

    _error = {"occurred": False, "toast_key": None, "return_to": "config_lichess"}
    lichess_launcher._run_lichess_human(
        "lip_x", 900, 10, chosen_color, "15+10", "Alain", _error,
    )
    return _error


def test_recherche_aleatoire_nenvoie_aucune_couleur_precise(monkeypatch):
    """La couleur "aléatoire" ne doit plus jamais être résolue localement :
    open_seek_stream doit recevoir une couleur vide ("" — Lichess choisit
    lui-même, jamais concerné par la règle d'équilibre, voir en-tête de
    module), jamais "white"/"black"."""
    client = _RecordingSeekClient(game_id="hgid1", user_color="black", opponent_name="Bob")
    _error = _run_human_seek(monkeypatch, "random", client)

    assert _error["occurred"] is False
    assert len(client.seek_calls) == 1
    args, _kwargs = client.seek_calls[0]
    requested_color = args[2]
    assert requested_color == "", f"couleur envoyée à Lichess non vide : {requested_color!r}"


@pytest.mark.parametrize("chosen_color", ["white", "black"])
def test_recherche_couleur_precise_inchangee(monkeypatch, chosen_color):
    """Une couleur explicitement choisie continue d'être transmise telle
    quelle (aucune régression, issue #327/#328)."""
    client = _RecordingSeekClient(game_id="hgid1", user_color=chosen_color, opponent_name="Bob")
    _error = _run_human_seek(monkeypatch, chosen_color, client)

    assert _error["occurred"] is False
    args, _kwargs = client.seek_calls[0]
    assert args[2] == chosen_color


def test_recherche_aleatoire_ecran_mise_en_place_reste_affiche(monkeypatch):
    """La position de départ étant identique pour les deux camps, l'écran
    de mise en place avant la recherche reste valable pour "aléatoire" —
    il reçoit une couleur arbitraire (ici "white"), jamais "random" lui-
    même (qui romprait l'orientation côté app.js, orientationIsFlipped())."""
    captured = {}

    def _fake_wait(nl_inst, color):
        captured["color"] = color

    monkeypatch.setattr(lichess_launcher, "_wait_initial_position_lichess", _fake_wait)
    client = _RecordingSeekClient(game_id="hgid1", user_color="black", opponent_name="Bob")
    _error = _run_human_seek(monkeypatch, "random", client)

    assert _error["occurred"] is False
    assert captured["color"] in ("white", "black")  # jamais "random"/vide/None


# ═══════════════════════════════════════════════════════════════════════
# 4. Orientation réelle appliquée au vrai début de partie (couleur
#    confirmée par Lichess, y compris quand elle diffère de l'écran de
#    mise en place) — réutilise known_user_color/LichessGame existants.
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("confirmed_color", ["white", "black"])
def test_recherche_aleatoire_couleur_confirmee_atteint_known_user_color(monkeypatch, tmp_path, confirmed_color):
    """Quel que soit le côté réellement assigné par Lichess à une
    recherche "aléatoire" (confirmé par gameStart), il doit atteindre
    LichessGame(known_user_color=...), qui pilote à son tour l'orientation
    réelle (lichess_init -> orientationIsFlipped(), inchangé par cette
    issue) — jamais la couleur arbitraire utilisée pour l'écran de mise en
    place."""
    captured = {}
    client = _HumanGameClient(game_id="hgid1", user_color=confirmed_color, opponent_name="Bob")

    import nicsoft.modes.lichess.game as game_module
    real_init = game_module.LichessGame.__init__

    def _capturing_init(self, *a, **kw):
        captured["known_user_color"] = kw.get("known_user_color")
        return real_init(self, *a, **kw)

    monkeypatch.setattr(game_module.LichessGame, "__init__", _capturing_init)
    # GameLog est importé localement dans _run_lichess_human (import à
    # l'appel) : patcher le module source nicsoft.modes.lichess.game_log,
    # pas lichess_launcher (qui n'en porte pas d'attribut) — même pattern
    # que test_issue326_lichess_game_log.py.
    monkeypatch.setattr(
        "nicsoft.modes.lichess.game_log.GameLog",
        lambda game_id, token="": GameLog(game_id, logs_dir=tmp_path),
    )

    _error = _run_human_seek(monkeypatch, "random", client)

    assert _error["occurred"] is False
    assert captured["known_user_color"] == confirmed_color


def test_recherche_aleatoire_journal_porte_couleur_demandee_et_obtenue(monkeypatch, tmp_path):
    """Issue #330, point 4 : le journal de recherche porte la couleur
    demandée à Lichess ("aléatoire" ici, jamais une couleur précise) et,
    une fois l'adversaire trouvé, la couleur réelle obtenue."""
    client = _HumanGameClient(game_id="hgid1", user_color="black", opponent_name="Bob")
    monkeypatch.setattr(
        "nicsoft.modes.lichess.game_log.GameLog",
        lambda game_id, token="": GameLog(game_id, logs_dir=tmp_path),
    )

    _error = _run_human_seek(monkeypatch, "random", client)
    assert _error["occurred"] is False

    log_files = list(tmp_path.glob("*.log")) or list(tmp_path.iterdir())
    assert log_files, "aucun fichier de journal créé"
    content = "\n".join(f.read_text(encoding="utf-8") for f in log_files if f.is_file())
    assert "couleur=aléatoire" in content, content
    assert "couleur=black" in content, content


# ═══════════════════════════════════════════════════════════════════════
# 5. GameClient.open_seek_stream — aucun paramètre "color" dans la requête
#    HTTP quand la couleur est vide (niveau le plus bas, sans lanceur).
# ═══════════════════════════════════════════════════════════════════════

class _RecordingOpenStreamTransport:
    def __init__(self):
        self.calls = []

    def open_stream(self, method, url, token, fields=None):
        self.calls.append((method, url, fields))
        return _FakeHandleForClient([""])


def test_open_seek_stream_couleur_vide_omet_le_parametre_color():
    transport = _RecordingOpenStreamTransport()
    client = GameClient("lip_x", transport=transport)
    client.open_seek_stream(15.0, 10, "")
    _method, _url, fields = transport.calls[0]
    assert "color" not in fields, f"'color' présent alors que vide : {fields}"


def test_open_seek_stream_couleur_precise_transmise():
    transport = _RecordingOpenStreamTransport()
    client = GameClient("lip_x", transport=transport)
    client.open_seek_stream(15.0, 10, "white")
    _method, _url, fields = transport.calls[0]
    assert fields["color"] == "white"


# ═══════════════════════════════════════════════════════════════════════
# 6. Partie contre l'IA — inchangée (tirage local conservé, jamais
#    concernée par l'équilibre des couleurs, parties IA non comptées).
# ═══════════════════════════════════════════════════════════════════════

def test_partie_ia_continue_de_resoudre_aleatoire_localement(monkeypatch):
    """launch_lichess (IA) doit continuer d'appeler random.choice pour
    "aléatoire" — contrairement à la recherche humaine, cette résolution
    locale reste correcte ici (jamais soumise à l'équilibre des couleurs,
    voir rapport de clôture)."""
    from nicsoft.tests.test_issue310_lichess_corrections import _TrackedFakeBoard

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
            return {"id": "gid_330_ia"}

        def stream_game(self, game_id, sleep=None):
            yield {
                "type": "gameFull", "white": {"id": "alain"}, "black": {"aiLevel": 1},
                "state": {"status": "aborted", "winner": "", "moves": ""},
            }

    monkeypatch.setattr(lichess_launcher, "GameClient", _Client)

    lichess_launcher.launch_lichess({"level": 1, "cadence": "15+10", "color": "random", "player": "Alain"})

    assert captured.get("color") == "black"
