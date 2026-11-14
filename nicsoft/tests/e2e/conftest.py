"""
Fixtures e2e — Lance le serveur AlChess en subprocess et fournit
une page Playwright connectée pour les tests end-to-end.
"""
import os
import queue
import re
import subprocess
import threading
import time
import pytest
import requests

# Racine du dépôt (ou worktree) où tournent ces tests, déduite de
# l'emplacement de ce fichier : nicsoft/tests/e2e/conftest.py → remonter de 3.
REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Python de l'environnement virtuel de l'utilisateur (hidapi, Flask-SocketIO,
# etc.) — seul le code importé (REPO_DIR) doit venir du dépôt testé, pas ce
# Python lui-même.
PYTHON = os.path.join(os.path.expanduser("~/NicLink"), "venv", "bin", "python")

# Limite stricte d'attente de l'URL du serveur (issue #312) — au-delà, on
# arrête le process et on fait échouer le test plutôt que de rester bloqué.
STARTUP_TIMEOUT_S = 20


def _start_line_reader(stream):
    """
    Démarre un fil daemon qui lit `stream` ligne par ligne et empile chaque
    ligne dans une queue.Queue. readline() peut bloquer indéfiniment sur ce
    fil (processus silencieux, pipe jamais fermé) sans jamais bloquer
    l'appelant : seul ce fil daemon reste coincé, le thread principal
    continue de consommer la queue avec un timeout réel (issue #312 — avant
    cette fixture, la lecture bloquante de stdout empêchait la limite de
    20s d'être jamais vérifiée).
    """
    line_queue = queue.Queue()

    def _reader():
        try:
            for line in iter(stream.readline, ""):
                line_queue.put(line)
        except (ValueError, OSError):
            pass  # flux fermé (process terminé pendant la lecture)
        finally:
            line_queue.put(None)  # sentinelle : fin de flux

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    return line_queue


def _kill_process(proc):
    """Arrête `proc` par son PID exact : terminate(), puis kill() si le
    process ne répond pas dans les quelques secondes qui suivent."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def wait_for_server_url(proc, line_queue, timeout_s=STARTUP_TIMEOUT_S):
    """
    Consomme `line_queue` (remplie par un fil de lecture non bloquant,
    voir _start_line_reader) jusqu'à trouver l'URL du serveur AlChess
    (ligne "[NicLink] Interface disponible sur http://...", garantie par
    nicsoft/web/server.py indépendamment de la configuration de
    journalisation — issue #312) ou jusqu'à expiration de `timeout_s`.

    Ne bloque jamais plus de `timeout_s` au total, quel que soit l'état du
    process (silencieux, planté, boucle infinie sans sortie). En cas de
    dépassement ou de fin de flux sans URL trouvée, arrête `proc` par son
    PID exact et lève RuntimeError avec les dernières lignes lues.
    Retourne (url, lignes_lues) en cas de succès.
    """
    lines = []
    deadline = time.time() + timeout_s
    url = None
    while time.time() < deadline:
        remaining = deadline - time.time()
        try:
            line = line_queue.get(timeout=max(0.0, min(0.2, remaining)))
        except queue.Empty:
            continue
        if line is None:
            break  # flux terminé (process a fermé stdout) — pas d'URL trouvée
        lines.append(line)
        m = re.search(r"http://127\.0\.0\.1:(\d+)", line)
        if m:
            url = f"http://127.0.0.1:{m.group(1)}"
            break

    if not url:
        _kill_process(proc)
        derniere = "".join(lines[-20:]) or "(aucune sortie lue)"
        raise RuntimeError(
            f"Serveur AlChess non démarré — URL non trouvée en {timeout_s}s. "
            f"Dernières lignes lues :\n{derniere}"
        )
    return url, lines


@pytest.fixture(scope="session")
def server_url():
    """Lance le serveur AlChess (code de REPO_DIR) et retourne son URL."""
    env = os.environ.copy()
    env["BROWSER"] = "/bin/true"  # empêche l'ouverture automatique du navigateur
    env["ALCHESS_SKIP_BOARD"] = "1"  # n'interroge pas l'échiquier USB réel
    # Données réelles (ECO, livres d'ouvertures...) non versionnées dans le dépôt
    # (data/ est dans .gitignore) : un worktree de test ne les a pas. On pointe
    # ALCHESS_DIR vers le dossier utilisateur pour les tests qui en dépendent,
    # tout en gardant le CODE importé depuis REPO_DIR (cwd ci-dessous).
    env.setdefault("ALCHESS_DIR", os.path.expanduser("~/NicLink"))
    # ALCHESS_DIR ci-dessus pouvant être le dossier du vrai serveur d'Alain,
    # ce serveur de test ne doit jamais lire ni écrire son marqueur
    # d'instance unique, ni être arrêté ni bloqué par lui (issue #324).
    env["ALCHESS_SKIP_SINGLE_INSTANCE"] = "1"

    proc = subprocess.Popen(
        [PYTHON, "-m", "nicsoft.web"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_DIR,
        env=env,
    )

    try:
        line_queue = _start_line_reader(proc.stdout)
        try:
            url, _lines = wait_for_server_url(proc, line_queue)
        except RuntimeError as e:
            pytest.fail(str(e))

        # Attendre que Flask réponde — sans ouvrir de navigateur avant ça.
        ready = False
        for _ in range(30):
            try:
                if requests.get(url, timeout=1).status_code == 200:
                    ready = True
                    break
            except requests.exceptions.RequestException:
                pass  # boucle de polling pendant le démarrage du serveur de test
            time.sleep(0.3)
        if not ready:
            _kill_process(proc)
            pytest.fail(f"Serveur AlChess démarré ({url}) mais ne répond jamais 200")

        yield url
    finally:
        # Finaliseur : le serveur est arrêté dans tous les cas (succès,
        # échec de démarrage, exception dans un test) — issue #312.
        _kill_process(proc)


@pytest.fixture(scope="session")
def page(server_url):
    """
    Page Playwright connectée au serveur, mode virtuel activé.
    Session-scoped : une seule page pour toute la suite de tests,
    ce qui évite de déclencher le timer de déconnexion (5s).
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        pg = ctx.new_page()

        pg.goto(server_url, wait_until="networkidle")

        # L'overlay de démarrage disparaît 5s après la connexion SocketIO
        pg.wait_for_selector("#startup-overlay", state="hidden", timeout=15000)

        # Mode virtuel coché par défaut sur la carte Pédagogique (issue #205 —
        # le bouton unique "menu-btn-primary" + checkbox globale #chk-virtual-mode
        # ont été remplacés par une checkbox "Mode virtuel" par carte lors du
        # refactoring des cartes menu Pédagogique/Labo).
        pg.wait_for_selector(
            ".menu-card-primary .menu-card-head",
            timeout=5000,
        )

        yield pg

        browser.close()


@pytest.fixture
def at_menu(page):
    """
    Garantit qu'on est sur l'écran menu avant chaque test.
    Utilisez cette fixture plutôt que `page` directement pour les tests qui
    commencent depuis le menu.
    """
    if not page.locator("#screen-menu").is_visible():
        page.evaluate("sendAction({type: 'back_menu'})")
        page.wait_for_selector("#screen-menu", state="visible", timeout=5000)
    return page
