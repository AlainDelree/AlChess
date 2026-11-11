"""
nicsoft/tests/test_issue310_lichess_corrections.py — AlChess

Issue #310 : premier essai réel du mode Lichess (#309) sur l'échiquier
physique — corrections après coup.

1. "cannot join thread before it is started" à toute fin de partie :
   LichessGame.start() exécute run() de façon synchrone (le vrai threading
   vit dans le lanceur) mais l'ancien code appelait quand même game.join()
   juste après — Thread.join() sur un Thread dont Thread.start() natif n'a
   jamais été appelé lève inconditionnellement cette RuntimeError. Capturée
   par le except Exception générique du lanceur, elle écrasait ensuite
   l'état "game_over" déjà posé par LichessGame._finalize() (PGN enregistré,
   historique prêt) en forçant un retour menu avec toast d'erreur — d'où
   partie finie "en erreur", sans écran de résultat ni analyse.
2. Lancement refusé proprement si un autre mode est déjà actif.
3. Enchaînement de deux modes (faux échiquiers) dans la même instance :
   l'échiquier doit être libéré entre les deux.
4. Isolation des tests : le dossier réel des parties ne doit jamais recevoir
   d'écriture pendant les tests (fixture globale conftest.py).
5. Nulle : "proposée" puis "refusée" si le statut ne passe pas à nulle.
6. Clés i18n : toute clé de traduction liée à Lichess utilisée par le code
   (Python ou app.js) doit exister dans les trois langues — extraction
   programmatique, pas une liste figée (qui avait laissé passer les 6 clés
   toast.lichess_* manquantes lors du premier essai réel).
"""
import json
import re
from pathlib import Path

import pytest

import nicsoft.core.game_manager_modes.humain as humain_launcher
import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.game as game_mod
from nicsoft.core.game_manager_modes.state import set_nl_inst_ref, set_virtual_mode
from nicsoft.modes.lichess.game import LichessGame
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, FakeTransport, _make_game, _make_recorder

REPO_ROOT = Path(__file__).resolve().parents[2]


class _TrackedFakeBoard(FakeBoard):
    """FakeBoard (test_issue309) + indicateur disconnect() — ce double ne
    trace pas cet appel, nécessaire ici pour vérifier la libération."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.disconnected = False

    def disconnect(self):
        self.disconnected = True


@pytest.fixture(autouse=True)
def _reset_shared_state():
    set_nl_inst_ref(None)
    set_virtual_mode(False)
    yield
    set_nl_inst_ref(None)
    set_virtual_mode(False)


# ── 1. Fin de partie sans "cannot join thread" ──────────────────────────────

class _FakeClientPartieRapide:
    """Simule un client Lichess dont la partie se termine (mat) dès le
    premier événement de flux — suffisant pour exercer tout le chemin
    normal de fin de partie du lanceur sans dépendre du minutage d'un vrai
    thread de flux."""

    def __init__(self, token, transport=None):
        pass

    def create_ai_game(self, **kwargs):
        return {"id": "gid_310"}


def test_launch_lichess_partie_terminee_normalement_sans_exception(monkeypatch, tmp_path):
    """Régression du bug principal de l'issue #310 : une partie qui se
    termine (ici par mat) ne doit jamais faire remonter "cannot join
    thread before it is started", et l'état affiché doit rester
    "game_over" (pas écrasé par un retour menu + toast d'erreur)."""
    board = _TrackedFakeBoard()
    saved_pgn = []

    class _Client(_FakeClientPartieRapide):
        def stream_game(self, game_id, sleep=None):
            yield {
                "type": "gameFull",
                "white": {"id": "alain"}, "black": {"aiLevel": 1},
                "state": {
                    "status": "mate", "winner": "white",
                    "moves": "e2e4 e7e5 f1c4 b8c6 d1h5 g8f6 h5f7",
                },
            }

    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test"})
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: board)
    monkeypatch.setattr(lichess_launcher, "_wait_initial_position_lichess", lambda nl_inst: None)
    monkeypatch.setattr(lichess_launcher, "GameClient", _Client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "menu", raising=False)

    final_path = tmp_path / "out.pgn"
    monkeypatch.setattr(game_mod, "build_final_path", lambda mode, gtype, white, black: str(final_path))
    monkeypatch.setattr(game_mod, "build_and_save_pgn",
                         lambda headers=None, moves=None, output_path=None: saved_pgn.append(output_path))

    # Couleur explicite "black" (issue #311) : la partie se crée
    # immédiatement après la position, sans attendre un premier coup
    # physique — ce chemin blancs a son propre test dédié.
    lichess_launcher.launch_lichess({"level": 1, "cadence": "15+10", "color": "black", "player": "Alain"})

    assert lichess_launcher.web_server._app_state == "game_over"
    assert saved_pgn == [str(final_path)]
    assert board.disconnected is True


def test_lichess_game_join_est_un_no_op_securise():
    """Garde-fou direct sur le bug : appeler .join() sur une LichessGame
    jamais démarrée via Thread.start() ne doit jamais lever (ni avant, ni
    après, le fix de game.py)."""
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    game = LichessGame(board, client, "gid_310", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10)
    game.join()  # ne doit jamais lever RuntimeError("cannot join thread before it is started")
    game.join(timeout=2.0)


# ── 2. Lancement refusé si un autre mode est déjà actif ─────────────────────

@pytest.mark.parametrize("etat_actif", ["playing", "connecting", "config_humain"])
def test_launch_lichess_refuse_si_mode_deja_actif(monkeypatch, etat_actif):
    def _boom(**kw):
        raise AssertionError("create_board ne doit jamais être appelé — lancement déjà refusé")

    monkeypatch.setattr(lichess_launcher, "create_board", _boom)
    toasts = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: toasts.append((etype, data)))
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", etat_actif, raising=False)

    lichess_launcher.launch_lichess({"level": 1, "cadence": "15+10", "color": "random"})

    assert lichess_launcher.web_server._app_state == etat_actif  # état inchangé
    assert toasts and toasts[-1] == ("lichess_toast", {"message_key": "toast.lichess_mode_actif", "type": "warning"})


# ── 3. Enchaînement de deux modes (faux échiquiers), libération de l'échiquier ─

class _FakeGameWebHumain:
    """Double minimal de GameWeb (mode Humain) — termine la partie
    immédiatement, comme _FakeGameWeb de test_issue295_mode_cleanup.py."""

    def __init__(self, nl_inst, white_name="Anonyme1", black_name="Anonyme2",
                 default_game_type="Serious", **kwargs):
        self.nl_inst = nl_inst
        self.game_over = False

    def save_pgn_tmp(self, *a, **kw):
        pass

    def start(self):
        self.game_over = True


def test_enchainement_humain_puis_lichess_libere_l_echiquier(monkeypatch, tmp_path):
    """Un mode (Humain, faux échiquier) joué puis quitté normalement ne
    doit jamais empêcher le lancement du mode Lichess qui suit dans la
    même instance — l'échiquier du premier mode doit être libéré avant
    que le second ne construise le sien (issue #310, point 4)."""
    nl_humain = _TrackedFakeBoard()
    nl_lichess = _TrackedFakeBoard()

    monkeypatch.setattr(humain_launcher, "create_board", lambda **kw: nl_humain)
    monkeypatch.setattr(humain_launcher, "_wait_initial_position_web", lambda nl_inst: None)
    import nicsoft.modes.humain.human as human_mod
    monkeypatch.setattr(human_mod, "GameWeb", _FakeGameWebHumain)

    _error = {"occurred": False, "toast_key": None}
    humain_launcher._run_humain("Alice", "Bob", "Serious", _error, virtual=False)

    assert nl_humain.disconnected is True, "l'échiquier du mode Humain doit être libéré en fin de partie"

    class _Client:
        def __init__(self, token, transport=None):
            pass

        def create_ai_game(self, **kwargs):
            return {"id": "gid_chain"}

        def stream_game(self, game_id, sleep=None):
            yield {
                "type": "gameFull", "white": {"id": "alain"}, "black": {"aiLevel": 1},
                "state": {"status": "aborted", "winner": "", "moves": ""},
            }

    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test"})
    monkeypatch.setattr(lichess_launcher, "create_board", lambda **kw: nl_lichess)
    monkeypatch.setattr(lichess_launcher, "_wait_initial_position_lichess", lambda nl_inst: None)
    monkeypatch.setattr(lichess_launcher, "GameClient", _Client)
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "menu", raising=False)

    lichess_launcher.launch_lichess({"level": 1, "cadence": "15+10", "color": "black", "player": "Alain"})

    assert nl_lichess.disconnected is True, "l'échiquier du mode Lichess doit lui aussi être libéré en fin de partie"


# ── 4. Nulle : proposée puis refusée ─────────────────────────────────────────

def test_nulle_proposee_puis_refusee_si_statut_ne_passe_pas_a_nulle(monkeypatch):
    events, states, actions = _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient("lip_test", transport=FakeTransport())
    game = LichessGame(board, client, "gid_draw", level=1, player_name="Alain",
                        clock_limit_s=900, clock_increment_s=10)
    monkeypatch.setattr(game, "client", client)
    monkeypatch.setattr(client, "answer_draw", lambda game_id, accept: None)

    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    assert game.user_color == "white"

    actions.put({"type": "lichess_propose_draw"})
    game._process_browser_actions()
    assert game._my_draw_offer_pending is True
    assert ("lichess_draw_proposed", {}) in events

    # L'adversaire répond en jouant un coup, sans accepter : wdraw repasse à
    # False sans que le statut passe à "draw" → la proposition est refusée.
    game._apply_game_state({"status": "started", "moves": "e2e4 e7e5", "wdraw": False, "bdraw": False})
    assert game._my_draw_offer_pending is False
    assert ("lichess_draw_refused", {}) in events


# ── 5. Garde d'isolation des écritures de test ───────────────────────────────

def test_fixture_isolation_redirige_bien_games_dir(tmp_path):
    """Vérifie que la fixture autouse de conftest.py a bien pris effet pour
    ce test — nicsoft.engine.pgn_manager.GAMES_DIR doit pointer vers le
    tmp_path de CE test (même fixture tmp_path, réutilisée par
    conftest._isolate_games_dir), jamais vers le vrai dossier de parties
    de l'utilisateur."""
    import nicsoft.config as config_mod
    import nicsoft.engine.pgn_manager as pgn_manager_mod
    assert pgn_manager_mod.GAMES_DIR == tmp_path / "games"
    assert pgn_manager_mod.GAMES_DIR != config_mod.APP_DIR / "games"


def test_partie_lichess_complete_n_ecrit_jamais_dans_le_vrai_dossier_de_parties(monkeypatch):
    """Garde de non-régression (issue #310, point 8) : même en bout de
    partie réelle (sauvegarde PGN incluse), aucune écriture ne doit
    atteindre le vrai dossier de parties — seul celui redirigé par la
    fixture autouse de conftest.py doit recevoir le fichier. config_mod.APP_DIR
    n'est pas patché par cette fixture (volontairement, voir conftest.py) :
    il reflète ici le dossier réel que verrait le code sous test si
    l'isolation GAMES_DIR ne fonctionnait pas."""
    import nicsoft.config as config_mod
    real_games_dir = config_mod.APP_DIR / "games"
    before = set(real_games_dir.rglob("*")) if real_games_dir.exists() else set()

    events, states, _ = _make_recorder(monkeypatch)
    game, _, _ = _make_game(game_id="gid_isolation")
    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "e2e4"},
    })
    game._status = "resign"
    game._winner = "black"
    game._aborted = False
    game._finalize()

    after = set(real_games_dir.rglob("*")) if real_games_dir.exists() else set()
    assert after == before, f"écriture détectée dans le vrai dossier de parties : {after - before}"


# ── 6. Clés i18n Lichess : extraction programmatique ────────────────────────

I18N_NAMESPACES = {
    "aide", "analyse", "analyse_llm", "banner", "common", "config", "confirm",
    "connecting", "elo", "engine", "error", "exercices", "feedback", "game",
    "labo", "lichess", "menu", "modal", "opening_explorer", "outils",
    "ouvertures", "parametres", "pgn", "pgn_lib", "piece", "pieces",
    "pos_init", "retrans", "rodent", "save", "server", "startup", "status", "toast",
}

_KEY_RE = re.compile(r'["\']([a-z][a-z0-9_]*(?:\.[A-Za-z0-9_]+)+)["\']')


def _extract_lichess_i18n_keys(text: str) -> set:
    keys = set()
    for m in _KEY_RE.finditer(text):
        key = m.group(1)
        if key.split(".")[0] in I18N_NAMESPACES and "lichess" in key.lower():
            keys.add(key)
    return keys


def _lichess_i18n_keys_used_in_source() -> set:
    appjs = (REPO_ROOT / "nicsoft" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    keys = _extract_lichess_i18n_keys(appjs)
    for py_file in (REPO_ROOT / "nicsoft").rglob("*.py"):
        if "/tests/" in py_file.as_posix():
            continue
        keys |= _extract_lichess_i18n_keys(py_file.read_text(encoding="utf-8"))
    return keys


def test_extraction_cles_lichess_trouve_bien_des_cles_connues():
    """Garde-fou sur l'extraction elle-même : si elle ne trouve plus rien,
    elle a régressé silencieusement (toujours verte à tort)."""
    keys = _lichess_i18n_keys_used_in_source()
    for attendu in ("toast.lichess_error", "toast.lichess_no_token", "lichess.proposer_nulle_titre",
                    "config.titre.lichess", "toast.lichess_draw_sent", "toast.lichess_draw_refused"):
        assert attendu in keys, f"extraction incomplète : {attendu!r} non trouvée"


@pytest.mark.parametrize("locale", ["fr", "en", "de"])
def test_toutes_les_cles_i18n_lichess_existent_dans_les_3_langues(locale):
    keys = _lichess_i18n_keys_used_in_source()
    path = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = sorted(k for k in keys if not data.get(k))
    assert not missing, f"Clés i18n Lichess absentes ou vides dans {locale}.json : {missing}"
