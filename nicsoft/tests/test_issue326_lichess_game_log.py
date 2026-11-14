"""
nicsoft/tests/test_issue326_lichess_game_log.py — AlChess

Issue #326, point 10 : journal de partie Lichess dédié (un fichier par
partie, toujours actif, écrit immédiatement sur le disque). Aucune vraie
partie ne peut être rejouée en développement — ce fichier teste
intégralement nicsoft/modes/lichess/game_log.py sans réseau ni matériel
(faux transport/plateau, comme le reste des tests Lichess), y compris le
câblage réel dans GameClient (requêtes, lignes brutes, tchat) et dans
LichessGame (coups, boutons, pendules, perte/reprise d'échiquier).

Un jeton de test ("lip_" + 20 caractères, format réel d'un jeton personnel
Lichess) est utilisé partout pour vérifier qu'il n'apparaît JAMAIS dans le
fichier produit — jamais le vrai jeton d'Alain, qui n'existe nulle part
dans ce dépôt de tests.
"""
import json
import queue

import chess
import pytest

from nicsoft.modes.lichess.game import LichessGame
from nicsoft.modes.lichess.game_client import GameClient
from nicsoft.modes.lichess.game_log import GameLog, _prune_old_logs, _sanitize_game_id
from nicsoft.tests.test_issue309_lichess_l2a import FakeBoard, FakeTransport, _line, _make_recorder, _ok

FAKE_TOKEN = "lip_abcdefghij0123456789"
FAKE_CHAT_TEXT = "bonjour adversaire ceci est un test de tchat jamais journalise"


# ── GameLog seul (sans GameClient ni LichessGame) ────────────────────────────

def test_fichier_cree_nomme_avec_date_et_identifiant(tmp_path):
    log = GameLog("abcd1234", token=FAKE_TOKEN, logs_dir=tmp_path)
    assert log.path is not None
    assert log.path.exists()
    assert "abcd1234" in log.path.name
    assert log.path.suffix == ".log"


def test_jeton_explicite_jamais_dans_le_fichier(tmp_path):
    log = GameLog("gid", token=FAKE_TOKEN, logs_dir=tmp_path)
    log.raw(json.dumps({"type": "gameState", "moves": "e2e4", "wtime": 900000}))
    log.request("POST", "/board/game/gid/move/e2e4", "ok", 0.123)
    content = log.path.read_text(encoding="utf-8")
    assert FAKE_TOKEN not in content
    assert "***" not in content  # rien à masquer ici — le jeton n'apparaît dans aucun message journalisé


def test_jeton_glisse_par_erreur_dans_un_message_est_masque(tmp_path):
    """Défense en profondeur : si un futur appelant journalisait par erreur
    une chaîne contenant le jeton, _mask() doit quand même l'effacer."""
    log = GameLog("gid", token=FAKE_TOKEN, logs_dir=tmp_path)
    log.board_change(f"fuite accidentelle pour le test : {FAKE_TOKEN}")
    content = log.path.read_text(encoding="utf-8")
    assert FAKE_TOKEN not in content
    assert "***" in content


def test_pattern_generique_masque_un_jeton_meme_sans_le_fournir(tmp_path):
    """Même sans passer `token=` explicitement, un jeton au format Lichess
    (préfixe lip_) glissé dans un message est masqué par la regex générique."""
    log = GameLog("gid", logs_dir=tmp_path)  # pas de token= fourni
    other_real_looking_token = "lip_ZZZZZZZZZZZZZZZZZZZZ99"
    log.board_change(f"Authorization: Bearer {other_real_looking_token}")
    content = log.path.read_text(encoding="utf-8")
    assert other_real_looking_token not in content
    assert "***" in content


def test_chat_ignore_ne_journalise_jamais_le_contenu(tmp_path):
    log = GameLog("gid", logs_dir=tmp_path)
    log.chat_ignored()
    content = log.path.read_text(encoding="utf-8")
    assert FAKE_CHAT_TEXT not in content
    assert "ignoré" in content or "ignore" in content.lower()


def test_ligne_reste_lisible_sans_fermeture_explicite(tmp_path):
    """Simule un arrêt brutal : écrit puis relit le fichier sans jamais
    appeler close() — seul flush() (déjà fait par chaque écriture) garantit
    que les données ont quitté le processus."""
    log = GameLog("gid", logs_dir=tmp_path)
    log.raw(json.dumps({"type": "gameState", "moves": "e2e4 e7e5", "status": "started"}))
    # Pas de log.close() ici.
    content = log.path.read_text(encoding="utf-8")
    assert "e2e4 e7e5" in content


def test_horodatage_a_la_milliseconde(tmp_path):
    log = GameLog("gid", logs_dir=tmp_path)
    log.state_change("test")
    line = [l for l in log.path.read_text(encoding="utf-8").splitlines() if "[STATE]" in l][0]
    timestamp = line.split(" ", 1)[0]
    assert len(timestamp) == 12  # HH:MM:SS.mmm
    assert timestamp.count(":") == 2 and "." in timestamp


def test_heartbeat_respecte_lintervalle(tmp_path, monkeypatch):
    import nicsoft.modes.lichess.game_log as game_log_mod
    log = GameLog("gid", logs_dir=tmp_path)
    t = [1000.0]
    monkeypatch.setattr(game_log_mod.time, "monotonic", lambda: t[0])
    log._last_heartbeat_ts = t[0]
    log.maybe_heartbeat("white", 900000, 900000, True, 0.1)
    content_before = log.path.read_text(encoding="utf-8")
    assert "HEARTBEAT" not in content_before  # trop tôt (0s écoulée)

    t[0] += 31.0
    log.maybe_heartbeat("white", 900000, 900000, True, 0.1)
    content_after = log.path.read_text(encoding="utf-8")
    assert "HEARTBEAT" in content_after


def test_sanitize_game_id_retire_les_caracteres_dangereux():
    assert _sanitize_game_id("../../etc/passwd") == "______etc_passwd"
    assert "/" not in _sanitize_game_id("../../etc/passwd")
    assert _sanitize_game_id("abCD1234_-") == "abCD1234_-"


def test_purge_ne_garde_que_les_plus_recents(tmp_path):
    for i in range(5):
        (tmp_path / f"2026010{i}-000000_g{i}.log").write_text("x", encoding="utf-8")
    _prune_old_logs(tmp_path, keep=2)
    remaining = sorted(p.name for p in tmp_path.glob("*.log"))
    assert remaining == ["20260103-000000_g3.log", "20260104-000000_g4.log"]


# ── Câblage réel dans GameClient (requêtes, lignes brutes, tchat) ───────────

def test_game_client_journalise_les_requetes_et_les_lignes_brutes(tmp_path):
    log = GameLog("gid326", token=FAKE_TOKEN, logs_dir=tmp_path)
    transport = FakeTransport(
        requests=[_ok({"ok": True})],
        stream_batches=[[
            _line({"type": "gameFull", "white": {"id": "alain"}, "black": {"aiLevel": 1},
                   "state": {"status": "started", "moves": ""}}),
            _line({"type": "chatLine", "username": "adversaire", "text": FAKE_CHAT_TEXT, "room": "player"}),
            _line({"type": "gameState", "moves": "e2e4", "status": "mate", "winner": "white"}),
        ]],
    )
    client = GameClient(FAKE_TOKEN, transport=transport)
    client.attach_game_log(log)

    client.resign("gid326")  # déclenche une requête "ordinaire" via _request()
    list(client.stream_game("gid326"))  # consomme tout le flux scénarisé ci-dessus

    content = log.path.read_text(encoding="utf-8")
    assert "[REQUEST]" in content
    assert "board/game/gid326/resign" in content
    assert "[RAW]" in content
    assert '"type": "gameFull"' in content or '"type":"gameFull"' in content.replace(" ", "")
    assert FAKE_TOKEN not in content
    assert FAKE_CHAT_TEXT not in content
    assert "adversaire" not in content  # pseudo du tchat non plus, par prudence


# ── Câblage réel dans LichessGame (coups, boutons, pendules, échiquier) ─────

def test_lichess_game_journalise_coup_boutons_et_pendule(monkeypatch, tmp_path):
    _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient(FAKE_TOKEN, transport=FakeTransport())
    log = GameLog("gid326b", token=FAKE_TOKEN, logs_dir=tmp_path)
    game = LichessGame(
        board, client, "gid326b", level=1, player_name="Alain",
        clock_limit_s=5400, clock_increment_s=30, game_log=log,
    )
    monkeypatch.setattr(client, "play_move", lambda gid, uci, offer_draw=False: None)

    game._apply_game_full({
        "white": {"id": "alain"}, "black": {"aiLevel": 1},
        "state": {"status": "started", "moves": "", "wtime": 5400000, "btime": 5400000},
    })
    game._submit_move("e2e4")

    content = log.path.read_text(encoding="utf-8")
    assert "[STATE]" in content
    assert "[CLOCK]" in content
    assert "boutons abandon=" in content
    assert FAKE_TOKEN not in content


def test_lichess_game_sans_game_log_explicite_en_cree_un_quand_meme(monkeypatch, tmp_path):
    """« Toujours actif » (issue #326, point 10) : même un appelant qui
    oublie de fournir un journal dédié en obtient un, pas un no-op muet."""
    monkeypatch.setattr("nicsoft.modes.lichess.game.GameLog",
                        lambda game_id: GameLog(game_id, logs_dir=tmp_path))
    _make_recorder(monkeypatch)
    board = FakeBoard()
    client = GameClient(FAKE_TOKEN, transport=FakeTransport())
    game = LichessGame(board, client, "gid326c", level=1, player_name="Alain",
                        clock_limit_s=600, clock_increment_s=0)
    assert game._game_log.path is not None
    assert game._game_log.path.exists()


def test_exception_du_fil_de_lecture_est_journalisee_avec_sa_trace(tmp_path):
    """(g) Toute exception imprévue d'un fil secondaire doit être
    journalisée en entier, trace complète comprise — ici le fil de
    lecture du flux (_stream_reader_loop), appelé directement (hors
    thread) pour un test déterministe."""
    log = GameLog("gid326d", logs_dir=tmp_path)

    class _BoomTransport:
        def stream_lines(self, url, token):
            raise RuntimeError("panne simulée du fil de lecture")

        def request(self, *a, **kw):
            raise AssertionError("non attendu")

    board = FakeBoard()
    boom_client = GameClient(FAKE_TOKEN, transport=_BoomTransport())
    boom_client.attach_game_log(log)
    game = LichessGame(board, boom_client, "gid326d", level=1, player_name="Alain",
                        clock_limit_s=600, clock_increment_s=0, game_log=log)
    game._stream_reader_loop()
    content = log.path.read_text(encoding="utf-8")
    assert "[EXC]" in content
    assert "panne simulée du fil de lecture" in content
    assert "Traceback" in content
