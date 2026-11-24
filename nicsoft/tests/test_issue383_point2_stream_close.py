"""
nicsoft/tests/test_issue383_point2_stream_close.py — AlChess

Issue #383, point 2 : étude #382 — après l'annulation d'une recherche
d'adversaire humain, le nettoyage des deux flux Lichess (board/seek,
stream/event) ne se terminait jamais. Établi par essai réel (sans aucun
réseau extérieur, serveur HTTP local 127.0.0.1 uniquement) : un simple
`StreamHandle.close()` appelé depuis un AUTRE fil pendant qu'un fil de
lecture est bloqué dans `lines()` ne réveille PAS ce fil — pire, close()
lui-même se bloque alors jusqu'à l'arrivée naturelle de données suivantes
(ou jamais, si aucune ne vient), le verrou interne du tampon
(`io.BufferedReader`) étant partagé entre lecture et fermeture.

`StreamHandle.close()` coupe désormais la connexion TCP sous-jacente
(`socket.shutdown(SHUT_RDWR)`) AVANT de fermer la réponse — seule opération
garantie de débloquer immédiatement un `recv()` en cours dans un autre fil,
identique sur Linux et Windows (API Winsock).

Règle absolue de cette issue : AUCUN réseau extérieur — le serveur HTTP de
ce module n'écoute que sur 127.0.0.1, jamais lichess.org ; aucun accès à
l'échiquier physique.
"""
import http.client
import http.server
import re
import threading
import time
from pathlib import Path

import pytest

from nicsoft.modes.lichess.transport import StreamHandle

REPO_ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = REPO_ROOT / "nicsoft" / "web" / "templates" / "index.html"
APP_JS_PATH = REPO_ROOT / "nicsoft" / "web" / "static" / "app.js"


# ═══════════════════════════════════════════════════════════════════════
# 1. Fermeture fiable d'un flux — faux serveur local qui n'envoie plus rien
#    après la première ligne (jamais de second envoi qui "réveillerait"
#    accidentellement la lecture, contrairement à test_issue328 qui
#    n'avait que 3s à attendre).
# ═══════════════════════════════════════════════════════════════════════

class _SilentAfterFirstLineHandler(http.server.BaseHTTPRequestHandler):
    """N'envoie qu'une seule ligne puis se tait pendant `hold_s` (très
    supérieur au délai borné attendu de la fermeture) — jamais de seconde
    ligne avant la fin du test, pour ne jamais masquer un faux positif
    (close() qui ne ferait qu'attendre la prochaine donnée plutôt que de
    réveiller activement le lecteur, comme avant cette correction)."""

    first_line_sent = threading.Event()
    hold_s = 20.0

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(b"premiere-ligne\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        type(self).first_line_sent.set()
        time.sleep(type(self).hold_s)

    def log_message(self, *a, **kw):
        pass


@pytest.fixture
def fake_silent_lichess_server():
    _SilentAfterFirstLineHandler.first_line_sent = threading.Event()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SilentAfterFirstLineHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_fermeture_depuis_un_autre_fil_libere_le_lecteur_bloque_dans_un_delai_borne(fake_silent_lichess_server):
    """Reproduction directe du bug #382 : StreamHandle.close() appelé
    depuis le fil de test PENDANT qu'un autre fil est bloqué dans lines()
    en attente de la ligne suivante, qui ne viendra plus avant longtemps
    (hold_s=20s, bien au-delà du délai de ce test) — le lecteur doit être
    libéré rapidement, pas seulement avant la fin du test par coïncidence."""
    port = fake_silent_lichess_server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", "/stream")
    resp = conn.getresponse()
    handle = StreamHandle(resp)

    collected = []

    def _reader():
        collected.extend(handle.lines())

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    assert _SilentAfterFirstLineHandler.first_line_sent.wait(timeout=5), "première ligne jamais reçue"
    time.sleep(0.3)  # laisse le fil de lecture se rebloquer sur la ligne suivante

    t0 = time.monotonic()
    handle.close()
    close_elapsed = time.monotonic() - t0
    reader.join(timeout=5.0)
    total_elapsed = time.monotonic() - t0

    assert not reader.is_alive(), "le fil de lecture ne s'est jamais terminé après close()"
    assert total_elapsed < 5.0, f"libération trop lente ({total_elapsed:.2f}s) — pas de vrai réveil actif"
    assert close_elapsed < 5.0, f"close() lui-même est resté bloqué {close_elapsed:.2f}s"
    assert collected == ["premiere-ligne"]
    conn.close()


def test_close_est_sans_effet_si_le_flux_nutilise_pas_de_vrai_socket():
    """`_shutdown_underlying_socket()` doit rester best-effort (jamais
    d'exception) même sans la chaîne d'attributs attendue — ex. un double
    de test minimal utilisé ailleurs dans le projet."""

    class _FakeResponse:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake_response = _FakeResponse()
    handle = StreamHandle(fake_response)
    handle.close()  # ne doit lever aucune exception
    assert fake_response.closed is True
    handle.close()  # idempotent


# ═══════════════════════════════════════════════════════════════════════
# 2. Garde statique : "Annuler la recherche" et "Retour au menu" envoient
#    exactement le même geste ("back_menu") — jamais deux mécanismes
#    distincts qui pourraient diverger à l'avenir.
# ═══════════════════════════════════════════════════════════════════════

def _html():
    return HTML_PATH.read_text(encoding="utf-8")


def _app_js():
    return APP_JS_PATH.read_text(encoding="utf-8")


def test_bouton_annuler_recherche_et_bouton_retour_menu_portent_le_meme_data_action():
    """Les DEUX boutons visés par l'issue : "Annuler la recherche" (écran
    d'attente d'adversaire, screen-lichess-seeking) et "Retour au menu" de
    l'écran de fin de partie partagé (game_over, affiché aussi après une
    partie Lichess) — jamais le générique "Retour" de tout autre écran
    (ex. game-btn-quitter, qui ouvre une confirmation modale avant de
    quitter une partie moteur en cours, un geste volontairement distinct)."""
    html = _html()

    annuler_match = re.search(
        r'<button[^>]*data-i18n="lichess\.recherche\.annuler"[^>]*>', html,
    )
    assert annuler_match, "bouton 'Annuler la recherche' introuvable (clé lichess.recherche.annuler)"
    assert 'data-action="back_menu"' in annuler_match.group(0), (
        "le bouton 'Annuler la recherche' n'envoie plus le même geste que 'Retour au menu' "
        "(data-action='back_menu' attendu)"
    )

    retour_menu_match = re.search(
        r'<button[^>]*class="btn game-gameover-btn-retour"[^>]*>', html,
    )
    assert retour_menu_match, "bouton 'Retour au menu' de l'écran de fin de partie introuvable"
    assert 'data-action="back_menu"' in retour_menu_match.group(0), (
        f"bouton 'Retour au menu' sans data-action=back_menu : {retour_menu_match.group(0)}"
    )


def test_data_action_back_menu_envoie_toujours_exactement_le_meme_type_daction():
    """Garde contre une divergence future : un seul switch-case gère
    `data-action="back_menu"` dans app.js, qui envoie toujours
    `{type: "back_menu"}` — jamais de traitement spécifique à l'écran
    "lichess_seeking" qui enverrait un type différent."""
    app_js = _app_js()
    case_match = re.search(
        r'case\s+"back_menu"\s*:\s*\n\s*sendAction\(\{\s*type:\s*"back_menu"\s*\}\s*\)\s*;',
        app_js,
    )
    assert case_match, "le switch-case data-action -> back_menu ne correspond plus au motif attendu dans app.js"
    # Un seul point d'envoi pour ce geste (pas un second mécanisme ad hoc
    # pour l'écran de recherche Lichess qui enverrait un type différent).
    assert app_js.count('sendAction({ type: "back_menu" })') == 1
