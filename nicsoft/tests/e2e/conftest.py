"""
Fixtures e2e — Lance le serveur AlChess en subprocess et fournit
une page Playwright connectée pour les tests end-to-end.
"""
import os
import re
import subprocess
import time
import pytest
import requests

BASE_DIR = os.path.expanduser("~/NicLink")
PYTHON   = os.path.join(BASE_DIR, "venv", "bin", "python")


@pytest.fixture(scope="session")
def server_url():
    """Lance le serveur AlChess et retourne son URL."""
    env = os.environ.copy()
    env["BROWSER"] = "/bin/false"  # empêche l'ouverture automatique du navigateur

    proc = subprocess.Popen(
        [PYTHON, "-m", "nicsoft.web"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=BASE_DIR,
        env=env,
    )

    # Lire stdout jusqu'à trouver l'URL du serveur
    url = None
    deadline = time.time() + 20
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        m = re.search(r"http://127\.0\.0\.1:(\d+)", line)
        if m:
            url = f"http://127.0.0.1:{m.group(1)}"
            break

    if not url:
        proc.terminate()
        pytest.fail("Serveur AlChess non démarré — URL non trouvée dans stdout")

    # Attendre que Flask réponde
    for _ in range(30):
        try:
            if requests.get(url, timeout=1).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.3)

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


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

        # Activer le mode virtuel (côté JS — active immédiatement les boutons)
        pg.check("#chk-virtual-mode")

        # Vérifier que le bouton Pédagogique est débloqué
        pg.wait_for_selector(
            "button.menu-btn-primary:not([disabled])",
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
