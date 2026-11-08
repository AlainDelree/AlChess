"""
nicsoft/tests/test_issue299_humain_retour_menu_silencieux.py — NicLink
Issue #299, point 3 : à la fin d'une partie Humain contre Humain,
launch_humain() doit déclencher la vérification silencieuse de présence
(check_board_presence_silent, port neutre ihm_port) plutôt que la
vérification complète avec reconnexion (check_board_at_startup) — qui
faisait bipper le plateau 2-3s après le retour au menu. Aucun matériel
requis : _run_humain et threading.Thread sont remplacés par des doubles
synchrones.
"""
import nicsoft.core.game_manager_modes.humain as humain_launcher


class _FakeWebServerHumain:
    _app_state = "connecting"


class _SyncThread:
    """Remplace threading.Thread : exécute la cible immédiatement et de
    façon synchrone, pour un test déterministe sans vrai threading."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=False):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)

    def join(self):
        pass


def _patch_commun(monkeypatch, web_server, virtual_mode, fake_run_humain):
    monkeypatch.setattr(humain_launcher, "web_server", web_server)
    monkeypatch.setattr(humain_launcher, "get_virtual_mode", lambda: virtual_mode)
    monkeypatch.setattr(humain_launcher, "set_app_state", lambda *a, **k: None)
    monkeypatch.setattr(humain_launcher, "_run_humain", fake_run_humain)
    monkeypatch.setattr(humain_launcher.threading, "Thread", _SyncThread)


def test_fin_normale_appelle_la_verification_silencieuse_pas_de_gestionnaire(monkeypatch):
    web_server = _FakeWebServerHumain()

    def fake_run_humain(white, black, game_type, _error=None, virtual=False):
        web_server._app_state = "menu"  # fin de partie normale, retour menu

    _patch_commun(monkeypatch, web_server, virtual_mode=False, fake_run_humain=fake_run_humain)

    create_board_calls = []
    monkeypatch.setattr(humain_launcher, "create_board", lambda **kw: create_board_calls.append(kw))
    silent_calls = []
    monkeypatch.setattr(humain_launcher, "check_board_presence_silent", lambda: silent_calls.append(1))

    humain_launcher.launch_humain({"white": "Alice", "black": "Bob"})

    assert silent_calls == [1], "la vérification silencieuse doit être déclenchée au retour menu"
    assert create_board_calls == [], (
        "aucun gestionnaire de l'échiquier ne doit être créé pour cette vérification "
        "(régression : reconnexion complète qui fait bipper le plateau)"
    )


def test_mode_virtuel_ne_declenche_aucune_verification(monkeypatch):
    web_server = _FakeWebServerHumain()

    def fake_run_humain(white, black, game_type, _error=None, virtual=False):
        web_server._app_state = "menu"

    _patch_commun(monkeypatch, web_server, virtual_mode=True, fake_run_humain=fake_run_humain)

    silent_calls = []
    monkeypatch.setattr(humain_launcher, "check_board_presence_silent", lambda: silent_calls.append(1))

    humain_launcher.launch_humain({"white": "Alice", "black": "Bob"})

    assert silent_calls == []


def test_module_humain_n_importe_plus_la_verification_complete():
    """Verrou structurel : l'ancienne vérification complète avec
    reconnexion ne doit plus être importée du tout dans ce module."""
    assert not hasattr(humain_launcher, "check_board_at_startup")
    assert hasattr(humain_launcher, "check_board_presence_silent")
