#!/usr/bin/env python3
"""Launcher GTK — affiche un splash pendant le démarrage de NicLink."""
import threading
import subprocess
import sys
import pathlib
import time
import urllib.request
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

class SplashWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="NicLink")
        self.set_default_size(300, 160)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_decorated(False)
        self.set_resizable(False)

        css = b"""
        window { background-color: #d8e4f0; border: 2px solid #a0b8d0; border-radius: 12px; }
        label.title { font-size: 20px; font-weight: bold; color: #1a2a3a; }
        label.sub   { font-size: 12px; color: #2a3a4a; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        title = Gtk.Label(label="♟  NicLink")
        title.get_style_context().add_class("title")

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(40, 40)
        self.spinner.start()

        self.status = Gtk.Label(label="Démarrage en cours…")
        self.status.get_style_context().add_class("sub")

        box.pack_start(title, False, False, 0)
        box.pack_start(self.spinner, False, False, 0)
        box.pack_start(self.status, False, False, 0)
        self.add(box)
        self.show_all()

    def set_status(self, msg):
        GLib.idle_add(self.status.set_text, msg)

    def close_splash(self):
        GLib.idle_add(self.destroy)
        GLib.idle_add(Gtk.main_quit)


def _find_free_port(start=5000):
    import socket
    port = start
    while port < 5100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    return start


def launch_niclink(splash):
    port = _find_free_port(5000)
    niclink_dir = pathlib.Path(__file__).parent.parent.parent
    venv_python = niclink_dir / "venv" / "bin" / "python"

    splash.set_status("Lancement de NicLink…")
    subprocess.Popen(
        [str(venv_python), "-m", "nicsoft.web"],
        cwd=str(niclink_dir)
    )

    # Attendre que Flask réponde
    for _ in range(40):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=1)
            break
        except Exception:
            continue

    splash.set_status("Prêt !")
    time.sleep(0.4)
    splash.close_splash()


if __name__ == "__main__":
    win = SplashWindow()
    win.connect("destroy", Gtk.main_quit)
    threading.Thread(target=launch_niclink, args=(win,), daemon=True).start()
    Gtk.main()
