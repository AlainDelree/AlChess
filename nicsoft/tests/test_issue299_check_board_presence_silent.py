"""
nicsoft/tests/test_issue299_check_board_presence_silent.py — NicLink
Issue #299, point 3 : la vérification au retour menu depuis Humain contre
Humain ne doit plus créer de gestionnaire de l'échiquier (reconnexion,
bip 2-3s après le retour) — seulement lire la présence physique par
énumération USB (hid_backend.check_physically_present, déjà utilisée sans
connexion depuis l'issue #295) et émettre le même événement que la
vérification de démarrage. Aucun matériel requis : hid_backend et
create_board sont mockés.
"""
from unittest.mock import patch

from nicsoft.niclink import hid_backend
from nicsoft.web import alchess


def test_board_ok_envoye_si_echiquier_present(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    monkeypatch.setattr(hid_backend, "check_physically_present", lambda: True)
    with patch("nicsoft.web.alchess.send_event") as mock_send, \
         patch("nicsoft.web.alchess.create_board") as mock_create:
        alchess._check_board_presence_silent()
    mock_send.assert_called_once_with("board_ok", {})
    mock_create.assert_not_called()


def test_board_error_envoye_si_echiquier_absent(monkeypatch):
    monkeypatch.delenv("ALCHESS_SKIP_BOARD", raising=False)
    monkeypatch.setattr(hid_backend, "check_physically_present", lambda: False)
    with patch("nicsoft.web.alchess.send_event") as mock_send, \
         patch("nicsoft.web.alchess.create_board") as mock_create:
        alchess._check_board_presence_silent()
    mock_create.assert_not_called()
    mock_send.assert_called_once()
    event_type, data = mock_send.call_args.args
    assert event_type == "board_error"
    assert data.get("message_key") == "error.board.deconnecte"


def test_sans_effet_avec_alchess_skip_board(monkeypatch):
    monkeypatch.setenv("ALCHESS_SKIP_BOARD", "1")
    with patch("nicsoft.web.alchess.send_event") as mock_send, \
         patch.object(hid_backend, "check_physically_present") as mock_present:
        alchess._check_board_presence_silent()
    mock_send.assert_not_called()
    mock_present.assert_not_called()


def test_backend_web_route_bien_vers_la_verification_silencieuse(monkeypatch):
    """La méthode du port neutre (_WebBackend.check_board_presence_silent)
    doit appeler cette même fonction, pas la vérification complète."""
    calls = []
    monkeypatch.setattr(alchess, "_check_board_presence_silent", lambda: calls.append(1))
    alchess._WebBackend().check_board_presence_silent()
    assert calls == [1]
