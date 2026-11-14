"""
nicsoft/tests/test_issue333_lichess_human_resume.py — AlChess

Issue #333 : reprise d'une partie Lichess en cours contre un HUMAIN,
y compris depuis le menu principal, avec reconnexion rapide des flux.

Le mode jouable (LichessGame) est déjà générique IA/humain (nulle,
décompte du premier coup, pendules, écran de mise en place — voir
test_issue323_lichess_resume.py, `_make_resuming_game(..., opponent_is_ai=
False)`, déjà vert avant cette issue) : les tests ici couvrent
spécifiquement ce qui restait lié à l'IA dans la REPRISE
(`_run_lichess_resume`, `core/game_manager_modes/lichess.py`) — déduction
de la couleur utilisateur sans `aiLevel`, câblage de la couleur connue
depuis la liste des parties en cours, journal dédié du cycle de reprise —
ainsi que la reconnexion du flux de partie en cours de reprise/partie et
le bandeau du menu principal (point 3).

Entièrement sans réseau (FakeTransport/FakeBoard, voir test_issue309) et
sans matériel physique.
"""
import json
from pathlib import Path

import chess
import pytest

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.game as game_mod
import nicsoft.modes.lichess.game_log as game_log_mod
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.game_log import GameLog
from nicsoft.modes.lichess.transport import TransportNetworkError
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, FakeTransport, _line
from nicsoft.tests.test_issue323_lichess_resume import _make_resuming_game

REPO_ROOT = Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════════════════
# 1. _run_lichess_resume — couleur utilisateur pour une partie humaine
#    (issue #333, point 2 : aucun des deux camps ne porte `aiLevel`)
# ═══════════════════════════════════════════════════════════════════════

class _RecordingGame:
    """Double de LichessGame — enregistre les arguments reçus, ne lance
    jamais réellement de partie (`.start()` est un no-op) : évite de
    bloquer le test dans la boucle synchrone de `run()` (voir docstring de
    `_run_lichess`/`_run_lichess_resume`, « ne jamais appeler game.join()
    ensuite », même principe ici — un test ne doit pas non plus laisser le
    thread tourner)."""
    captured = None

    def __init__(self, nl_inst, client, game_id, level, player_name,
                 clock_limit_s, clock_increment_s, chosen_color_setting="random",
                 cadence_key="", resuming=False, initial_wtime_ms=None,
                 initial_btime_ms=None, clock_known=True, game_log=None,
                 known_user_color="", **kwargs):
        _RecordingGame.captured = {
            "game_id": game_id, "level": level, "player_name": player_name,
            "chosen_color_setting": chosen_color_setting, "resuming": resuming,
            "game_log": game_log, "known_user_color": known_user_color,
        }

    def start(self):
        pass


def _human_full_event(moves="e2e4", status="started"):
    """gameFull sans `aiLevel` d'aucun côté — partie contre un humain,
    exactement le cas qui manquait à `_run_lichess_resume` avant #333."""
    return {
        "type": "gameFull",
        "white": {"id": "alain", "name": "Alain"},
        "black": {"id": "bob", "name": "Bob"},
        "clock": {"initial": 900000, "increment": 0},
        "state": {"status": status, "moves": moves, "wtime": 820000, "btime": 900000},
    }


@pytest.fixture
def _resume_env(monkeypatch, tmp_path):
    """Environnement partagé : LichessGame remplacée par le double
    recorder, GameLog redirigée vers tmp_path (jamais le vrai dossier de
    logs — règle du projet), échiquier physique une FakeBoard."""
    _RecordingGame.captured = None
    monkeypatch.setattr(game_mod, "LichessGame", _RecordingGame)
    monkeypatch.setattr(game_log_mod, "GameLog", lambda game_id: GameLog(game_id, logs_dir=tmp_path))
    monkeypatch.setattr(lichess_launcher, "_open_board_with_retry", lambda name: FakeBoard())
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "connecting", raising=False)
    return tmp_path


@pytest.mark.parametrize("known_color", ["white", "black"])
def test_run_lichess_resume_humain_couleur_connue_transmise(monkeypatch, _resume_env, known_color):
    """Issue #333, point 2 : sans `aiLevel`, la couleur transmise par
    l'appelant (depuis la liste des parties en cours) devient à la fois
    `chosen_color_setting` et `known_user_color` de LichessGame — jamais
    devinée."""
    monkeypatch.setattr(lichess_launcher, "_peek_game_full",
                         lambda client, gid: _human_full_event())
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess_resume("lip_x", "gid1", "Alain", known_color, _error)
    assert _error["occurred"] is False
    captured = _RecordingGame.captured
    assert captured is not None
    assert captured["chosen_color_setting"] == known_color
    assert captured["known_user_color"] == known_color
    assert captured["resuming"] is True


def test_run_lichess_resume_humain_sans_couleur_connue_est_refusee(monkeypatch, _resume_env):
    """Issue #333, point 2 : sans couleur connue pour une partie contre un
    humain, la reprise est refusée explicitement (toast) plutôt que de
    deviner une couleur — jouer/orienter le camp adverse serait pire que
    refuser. Ne doit jamais atteindre la construction de LichessGame."""
    monkeypatch.setattr(lichess_launcher, "_peek_game_full",
                         lambda client, gid: _human_full_event())
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess_resume("lip_x", "gid1", "Alain", "", _error)
    assert _error["occurred"] is True
    assert _RecordingGame.captured is None


def test_run_lichess_resume_ia_couleur_toujours_deduite_sans_regression(monkeypatch, _resume_env):
    """Non-régression : une partie contre l'IA continue de déduire la
    couleur depuis `aiLevel`, comme avant #333 — même si un `known_color`
    (éventuellement périmé) est transmis par erreur, il est ignoré."""
    full_event = {
        "white": {"id": "alain"}, "black": {"aiLevel": 3},
        "clock": {"initial": 900000, "increment": 0},
        "state": {"status": "started", "moves": "", "wtime": 900000, "btime": 900000},
    }
    monkeypatch.setattr(lichess_launcher, "_peek_game_full", lambda client, gid: full_event)
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess_resume("lip_x", "gid1", "Alain", "black", _error)
    assert _error["occurred"] is False
    assert _RecordingGame.captured["chosen_color_setting"] == "white"
    assert _RecordingGame.captured["level"] == 3


def test_run_lichess_resume_journal_dedie_couvre_la_demande_et_la_position_cible(_resume_env, monkeypatch):
    """Issue #333, point 6 : le journal dédié de CETTE partie (pas le
    journal général) couvre la demande de reprise et la lecture de la
    position cible — pas seulement le déroulement de la partie une fois
    LichessGame construite."""
    monkeypatch.setattr(lichess_launcher, "_peek_game_full",
                         lambda client, gid: _human_full_event(moves="e2e4 e7e5"))
    _error = {"occurred": False, "toast_key": None, "return_to": "menu"}
    lichess_launcher._run_lichess_resume("lip_x", "gid42", "Alain", "white", _error)
    game_log = _RecordingGame.captured["game_log"]
    assert game_log is not None and game_log.path is not None
    contenu = game_log.path.read_text(encoding="utf-8")
    assert "reprise demandée" in contenu
    assert "position cible lue" in contenu
    assert "couleur=white" in contenu


def test_launch_lichess_resume_transmet_la_couleur_de_la_liste(monkeypatch):
    """Issue #333, point 2 : la couleur reçue du navigateur (déjà connue
    depuis l'évènement "lichess_resumable", voir app.js::lichessResumeGame)
    doit atteindre _run_lichess_resume."""
    monkeypatch.setattr(lichess_launcher.web_server, "_app_state", "menu", raising=False)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_x"})
    calls = []

    def fake_run(token, game_id, player_name, known_color, _error):
        calls.append((token, game_id, player_name, known_color))

    monkeypatch.setattr(lichess_launcher, "_run_lichess_resume", fake_run)
    lichess_launcher.launch_lichess_resume({"game_id": "gid1", "player": "Alain", "color": "black"})
    assert calls == [("lip_x", "gid1", "Alain", "black")]


# ═══════════════════════════════════════════════════════════════════════
# 2. Nulle de l'adversaire pendant la mise en place (reprise, humain)
#    (issue #333, point 2 : réponse toujours possible)
# ═══════════════════════════════════════════════════════════════════════

def test_nulle_adversaire_pendant_mise_en_place_reste_reponse_possible(monkeypatch):
    """Pendant l'écran de mise en place d'une reprise contre un humain
    (resume_pending=True), l'adversaire propose une nulle : le bandeau de
    nulle doit s'afficher et la réponse (accepter/refuser) doit rester
    traitée — jamais bloquée par la mise en place (distinct du bouton
    "Proposer nulle", lui, grisé pendant cette phase, voir
    test_resume_pending_abandon_actif_mais_pas_nulle)."""
    game, board, _first_events = _make_resuming_game(
        monkeypatch, opponent_is_ai=False, user_color_is_black=False,
    )
    assert game._resume_pending is True

    # L'adversaire (noir) propose une nulle pendant la mise en place.
    game._apply_game_state({"status": "started", "moves": "e2e4", "wdraw": False, "bdraw": True})
    assert game._draw_offered_by_opponent is True

    # Réponse de l'utilisateur, via la même file d'actions que le
    # navigateur (ihm_port.get_action, voir _make_recorder) — toujours
    # traitée bien que resume_pending reste vrai.
    from nicsoft.tests.test_issue309_lichess_l2a import _make_recorder
    events, states, actions = _make_recorder(monkeypatch)
    answered = []
    monkeypatch.setattr(game.client, "answer_draw", lambda gid, yes: answered.append(yes))
    actions.put({"type": "lichess_draw_accept"})
    game._process_browser_actions()
    assert answered == [True]
    assert game._resume_pending is True  # toujours en mise en place, sans régression


# ═══════════════════════════════════════════════════════════════════════
# 3. Reconnexion du flux de partie — sans coup perdu ni rejoué
#    (issue #333, point 4 : vérifier ce qui existe déjà avant de coder)
# ═══════════════════════════════════════════════════════════════════════
#
# Le mécanisme bas niveau (GameClient.stream_game : essais rapprochés puis
# espacés, RECONNECT_DELAYS_S=(1,2,4,8,30), jamais d'abandon automatique)
# existe déjà depuis une issue antérieure et est déjà couvert au niveau
# transport (test_issue307_lichess_l1.py — séquence
# gameFull/reconnecting/reconnected/gameFull/gameState). Ce qui manquait :
# la preuve, au niveau LichessGame, qu'un coup joué par l'adversaire
# PENDANT la coupure n'est ni perdu ni rejoué en double une fois le flux
# rétabli — y compris pour une partie reprise contre un humain.

def test_reconnexion_flux_pendant_partie_reprise_sans_coup_perdu_ni_rejoue(monkeypatch):
    # Reprise déjà terminée (position physique reconstruite) avant la coupure.
    game, board, events = _make_resuming_game(monkeypatch, moves="e2e4", user_color_is_black=False)
    board.current_fen = game.board.board_fen() + " w - - 0 1"
    game._tick_physical()
    assert game._resume_pending is False
    assert game._moves_applied == 1

    # Flux coupé juste après le premier gameFull, puis rétabli : l'adversaire
    # (noir) a joué e7e5 PENDANT la coupure (visible dans le gameFull
    # renvoyé à la reprise de connexion, conformément à la doc officielle
    # — « The first line is always of type gameFull »).
    transport = FakeTransport(stream_batches=[
        [_line(_human_full_event(moves="e2e4")), TransportNetworkError("coupure réseau")],
        [_line(_human_full_event(moves="e2e4 e7e5"))],
    ])
    client = GameClient("lip_x", transport=transport)

    replicated = []
    monkeypatch.setattr(game, "_start_opponent_replication_wait", lambda uci: replicated.append(uci))

    event_types = []
    for event in client.stream_game("gid1", sleep=lambda s: None):
        event_types.append(event["type"])
        game._handle_stream_event(event)

    assert event_types == ["gameFull", "reconnecting", "reconnected", "gameFull"]
    # Message persistant affiché puis retiré (issue #333, point 4) — déjà
    # câblé côté app.js (socket.on("lichess_reconnecting"/"lichess_reconnected")
    # sur #lichess-reconnecting-banner, voir index.html).
    assert [t for t, _ in events if t in ("lichess_reconnecting", "lichess_reconnected")] == [
        "lichess_reconnecting", "lichess_reconnected",
    ]
    # Le coup joué pendant la coupure est appliqué UNE SEULE fois (jamais
    # perdu : moves_applied passe de 1 à 2 ; jamais rejoué en double :
    # toujours 2 après coup, pas 3 ni plus).
    assert game._moves_applied == 2
    attendu = chess.Board()
    attendu.push_uci("e2e4")
    attendu.push_uci("e7e5")
    assert game.board.board_fen() == attendu.board_fen()
    # Réplication physique déclenchée EXACTEMENT pour le nouveau coup
    # adverse (e7e5) — jamais une seconde fois pour e2e4, déjà connu.
    assert replicated == ["e7e5"]


# ═══════════════════════════════════════════════════════════════════════
# 4. Bandeau du menu principal (issue #333, point 3)
# ═══════════════════════════════════════════════════════════════════════

def test_alchess_py_route_lichess_menu_check_vers_check_lichess_resumable():
    """La détection déclenchée par le navigateur à l'arrivée sur le menu
    principal réutilise check_lichess_resumable() telle quelle (même
    évènement "lichess_resumable", même silence en cas d'erreur réseau/
    jeton absent) — vérifié par inspection du câblage (pas d'exécution du
    serveur complet dans ce test)."""
    src = (REPO_ROOT / "nicsoft" / "web" / "alchess.py").read_text(encoding="utf-8")
    assert '"lichess_menu_check"' in src
    bloc = src[src.index('"lichess_menu_check"'):]
    assert "check_lichess_resumable" in bloc[:400]


def test_appjs_menu_banner_une_seule_requete_par_arrivee_sur_le_menu():
    """Issue #333, point 3 : une seule requête à l'ouverture du menu
    principal — jamais à chaque évènement "app_state" redondant tant que
    l'utilisateur reste sur le menu (débounce côté navigateur)."""
    src = (REPO_ROOT / "nicsoft" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "_lichessMenuBannerChecked" in src
    assert 'sendAction({ type: "lichess_menu_check" })' in src


def test_appjs_menu_banner_reutilise_lichess_resumable():
    """Le bandeau du menu principal est alimenté par le même évènement
    "lichess_resumable" que l'écran du mode Lichess — pas une seconde
    détection dupliquée côté navigateur."""
    src = (REPO_ROOT / "nicsoft" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    bloc = src[src.index('socket.on("lichess_resumable"'):]
    assert "lichess-menu-banner" in bloc[:2500]
    assert "lichess-menu-banner-list" in bloc[:2500]


def test_index_html_contient_le_bandeau_du_menu_principal():
    src = (REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="lichess-menu-banner"' in src
    assert 'id="lichess-menu-banner-list"' in src
    # À l'intérieur de #screen-menu — bandeau visible dès l'arrivée sur le
    # menu principal, pas seulement dans l'écran de configuration Lichess.
    menu_idx = src.index('id="screen-menu"')
    banner_idx = src.index('id="lichess-menu-banner"')
    lichess_cfg_idx = src.index('id="screen-config-lichess"')
    assert menu_idx < banner_idx < lichess_cfg_idx


# ═══════════════════════════════════════════════════════════════════════
# 5. Raisons exactes de non-reprenabilité — clés i18n présentes (fr/en/de)
#    (issue #333, point 1)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang", ["fr", "en", "de"])
@pytest.mark.parametrize("cle", [
    "lichess.reprise_non_reprenable_variante",
    "lichess.reprise_non_reprenable_cadence",
    "lichess.menu_banner_titre",
])
def test_cle_i18n_presente_dans_les_trois_langues(lang, cle):
    path = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n" / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert cle in data and data[cle].strip() != ""
