"""
nicsoft/tests/test_hid_backend_exceptions.py — NicLink
Vérifie que get_fen()/disconnect() (nicsoft/niclink/hid_backend.py) absorbent
bien le ValueError('not open') réellement levé par le binding hidapi
(hid.pyx) quand le handle a déjà été fermé par un autre thread — l'issue
#288 avait resserré ces deux sites en `(OSError, IOError)`, qui ne couvre
pas ce cas (ValueError n'est pas une sous-classe d'OSError). Aucun
matériel ni réseau : `_dev` est remplacé par un faux objet qui lève
ValueError, comme le ferait un hid.device() fermé entre-temps.
"""
from nicsoft.niclink import hid_backend


class _FermeEntreTemps:
    """Simule un hid.device() dont le handle C a été libéré par un autre
    thread (ex. disconnect() concurrent) : toute méthode lève ValueError('not open'),
    comme le fait réellement hid.pyx (cython-hidapi)."""

    def read(self, *a, **kw):
        raise ValueError("not open")

    def write(self, *a, **kw):
        raise ValueError("not open")

    def close(self):
        raise ValueError("not open")


def test_get_fen_absorbe_value_error_sans_lever(monkeypatch):
    monkeypatch.setattr(hid_backend, "_dev", _FermeEntreTemps())
    monkeypatch.setattr(hid_backend, "_connected", True)
    assert hid_backend.get_fen() == ""
    assert hid_backend._connected is False


def test_disconnect_absorbe_value_error_sans_lever(monkeypatch):
    monkeypatch.setattr(hid_backend, "_dev", _FermeEntreTemps())
    monkeypatch.setattr(hid_backend, "_connected", True)
    monkeypatch.setattr(hid_backend, "_last_write", 0.0)
    hid_backend.disconnect()  # ne doit pas lever
    assert hid_backend._dev is None
    assert hid_backend._connected is False
