"""
nicsoft/tests/test_issue295_usb_exclusive_access.py — NicLink
Suite #292 (issue #295) : deux défauts révélés par le test manuel avec
l'échiquier physique, tous deux déjà corrigés à la main dans
nicsoft/niclink/hid_backend.py avant cette issue — ces tests les
verrouillent.

Défaut 1 (régression #292) : « Start game » échouait avec « échiquier non
détecté ». La vérification de présence au démarrage (nicsoft/web/alchess.py)
laisse volontairement une connexion ouverte (le menu s'en sert pour savoir
que l'échiquier est connecté) ; la fonction de connexion du lancement
d'une partie ouvrait un second accès avant que le premier soit fermé, alors
que le Chessnut Air n'accepte qu'un seul accès HID à la fois (OSError
« open failed »). Correctif : hid_backend.connect() ferme l'ancien handle
sous verrou avant d'ouvrir le nouveau.

Défaut 2 : fausse alerte « échiquier déconnecté » au menu après une partie
terminée par retour au menu (sans abandon) — check_physically_present()
retournait faux dès que la connexion était fermée (court-circuit), sans
jamais interroger le bus USB, alors que sa documentation dit qu'elle le
fait. Correctif : suppression de ce court-circuit — la fonction interroge
toujours hid.enumerate().

Les tests ci-dessous utilisent les faux hidapi (_FakeDevice/_FakeHidModule)
de test_issue292_board_cleanup.py, rendus réalistes pour cette issue : un
second open_path() alors qu'un autre accès du même module est ouvert lève
désormais OSError('open failed'), comme le périphérique réel. Avant cette
modification, le faux module acceptait plusieurs ouvertures simultanées et
ne pouvait donc pas détecter le défaut 1 (voir test (c) ci-dessous).

Aucun matériel ni réseau requis.
"""
import pytest

from nicsoft.niclink import hid_backend
from nicsoft.niclink.driver import NicLinkManager
from nicsoft.tests.test_issue292_board_cleanup import _FakeDevice, _FakeHidModule


@pytest.fixture(autouse=True)
def _reset_hid_backend_state(monkeypatch):
    monkeypatch.setattr(hid_backend, "_decode_fen", lambda data: "8/8/8/8/8/8/8/8")
    monkeypatch.setattr(hid_backend.time, "sleep", lambda *a, **k: None)
    hid_backend._reset_state()
    yield
    hid_backend._reset_state()


# ── (c) Contrôle négatif : le faux module détecte bien la régression ─────────

def test_fake_hid_module_detecte_la_regression_sans_fermeture():
    """(c) Si l'ancien handle n'est pas fermé avant la nouvelle ouverture
    (comportement d'avant le correctif du défaut 1), le faux module hidapi
    lève bien OSError('open failed') — preuve que (a)/(b) ci-dessous
    auraient échoué sans le correctif connect(), et ne passent donc pas
    par accident."""
    hm = _FakeHidModule(lambda: _FakeDevice())
    dev1 = hm.device()
    dev1.open_path(b"/fake/chessnut")  # première ouverture — réussit

    dev2 = hm.device()
    with pytest.raises(OSError, match="open failed"):
        dev2.open_path(b"/fake/chessnut")  # pas de close() entre les deux — échoue

    dev1.close()
    dev2.open_path(b"/fake/chessnut")  # après fermeture de dev1 — réussit


# ── (a) Deux connexions successives de hid_backend, la première jamais fermée

def test_hid_backend_connect_deux_fois_ancien_handle_laisse_ouvert_reussit():
    """(a) Reproduit le défaut 1 au niveau hid_backend : une première
    connexion (comme la vérification du démarrage) reste ouverte, puis une
    seconde (comme le lancement d'une partie) est tentée sans disconnect()
    entre les deux. Les deux doivent réussir."""
    devices = iter([_FakeDevice(), _FakeDevice()])
    hm = _FakeHidModule(lambda: next(devices))

    import nicsoft.niclink.hid_backend as hb
    hb.hid = hm
    try:
        hid_backend.connect()
        first_dev = hid_backend._dev
        assert hid_backend.is_connected() is True

        hid_backend.connect()  # pas de disconnect() entre les deux — doit réussir
        assert hid_backend.is_connected() is True
        assert hid_backend._dev is not first_dev
        assert first_dev.closed is True  # fermé automatiquement par connect(), pas par l'appelant
    finally:
        hid_backend.disconnect()


# ── (b) Deux créations successives du gestionnaire complet ───────────────────

def test_niclinkmanager_deux_creations_successives_reussissent(monkeypatch):
    """(b) Reproduit le scénario exact du défaut 1 : la vérification du
    démarrage (check_board_at_startup, nicsoft/web/alchess.py) crée un
    NicLinkManager et laisse volontairement sa connexion ouverte (seul le
    fil fen_reader est arrêté) ; une partie en crée un second peu après.
    Avant le correctif, la seconde création levait SystemExit('board
    connection error') — OSError('open failed') sur le second open_path()."""
    devices = iter([_FakeDevice(), _FakeDevice()])
    monkeypatch.setattr(hid_backend, "hid", _FakeHidModule(lambda: next(devices)))

    startup_check = NicLinkManager(refresh_delay=0.1, logger=None, thread_sleep_delay=0.01)
    startup_check._fen_reader_stop.set()  # comme check_board_at_startup — connexion laissée ouverte

    game_nl = NicLinkManager(refresh_delay=0.1, logger=None, thread_sleep_delay=0.01)
    try:
        assert hid_backend.is_connected() is True
        assert hid_backend._dev is not None
    finally:
        game_nl.disconnect()


# ── (e) check_physically_present() après une fermeture volontaire ───────────

def test_check_physically_present_apres_fermeture_volontaire(monkeypatch):
    """(e) Défaut 2 : après une fermeture volontaire (fin de partie, retour
    menu), check_physically_present() doit rester vrai tant que le plateau
    est toujours énuméré sur le bus — et seulement devenir faux s'il
    disparaît réellement (câble débranché)."""
    dev = _FakeDevice()
    hm = _FakeHidModule(lambda: dev, present=True)
    monkeypatch.setattr(hid_backend, "hid", hm)

    hid_backend.connect()
    hid_backend.disconnect()  # fermeture volontaire — is_connected() devient False
    assert hid_backend.is_connected() is False

    assert hid_backend.check_physically_present() is True  # toujours énuméré sur le bus

    hm.present = False  # câble débranché
    assert hid_backend.check_physically_present() is False


# ── (f) Surveillance au menu : pas d'alerte après fermeture volontaire ───────

class _StopWatcherLoop(Exception):
    """Sentinelle pour sortir de la boucle infinie _board_menu_watcher()
    après un nombre d'itérations connu, sans modifier alchess.py."""


def test_board_menu_watcher_fermeture_volontaire_puis_disparition_reelle(monkeypatch):
    """(f) La surveillance au menu (nicsoft/web/alchess.py:_board_menu_watcher,
    toutes les 3s) ne doit envoyer aucun événement d'erreur tant que le
    plateau reste énuméré sur le bus (cas d'une fermeture volontaire en fin
    de session) ; elle doit en envoyer un dès qu'il en disparaît vraiment."""
    import nicsoft.web.alchess as alchess_mod

    class _FakeWebServer:
        _app_state = "menu"
        _board_status = "ok"

    events = []
    iterations = {"n": 0}

    def fake_sleep(_seconds):
        iterations["n"] += 1
        if iterations["n"] > 3:
            raise _StopWatcherLoop()

    # Trois itérations : échiquier toujours énuméré (fermeture volontaire,
    # pas d'erreur) deux fois, puis vraie disparition (câble débranché).
    present_sequence = iter([True, True, False])

    monkeypatch.setattr(alchess_mod, "web_server", _FakeWebServer)
    monkeypatch.setattr(alchess_mod, "send_event", lambda etype, data: events.append((etype, data)))
    monkeypatch.setattr(alchess_mod.time, "sleep", fake_sleep)
    monkeypatch.setattr(hid_backend, "check_physically_present", lambda: next(present_sequence))

    with pytest.raises(_StopWatcherLoop):
        alchess_mod._board_menu_watcher()

    assert events == [("board_error", {
        "message": "Échiquier déconnecté — vérifiez l'USB et reconnectez le plateau.",
        "message_key": "error.board.deconnecte",
    })]
