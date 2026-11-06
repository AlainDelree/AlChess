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

# Racine du dépôt (ou worktree) où tournent ces tests, déduite de
# l'emplacement de ce fichier : nicsoft/tests/e2e/conftest.py → remonter de 3.
REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Python de l'environnement virtuel de l'utilisateur (hidapi, Flask-SocketIO,
# etc.) — seul le code importé (REPO_DIR) doit venir du dépôt testé, pas ce
# Python lui-même.
PYTHON = os.path.join(os.path.expanduser("~/NicLink"), "venv", "bin", "python")


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

    proc = subprocess.Popen(
        [PYTHON, "-m", "nicsoft.web"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_DIR,
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
        except requests.exceptions.RequestException:
            pass  # boucle de polling pendant le démarrage du serveur de test
        time.sleep(0.3)

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()  # arrêt forcé si le process ne répond pas à terminate()


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
