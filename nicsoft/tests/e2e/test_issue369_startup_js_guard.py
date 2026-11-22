"""
nicsoft/tests/e2e/test_issue369_startup_js_guard.py — AlChess

Issue #369 : #368 a introduit une régression qui empêchait la page de
terminer son démarrage (`#startup-overlay` restait affiché indéfiniment,
JS cassé dès le chargement : `socket.on(...)` de premier niveau référencé
avant la déclaration `const socket = io();`, plus bas dans app.js — TDZ,
"Cannot access 'socket' before initialization"). `test_smoke_e2e.py`
l'a détecté par ricochet (tous les tests en erreur), mais aucun garde ne
vérifiait directement, et séparément, l'absence d'erreur JS au chargement.

Lance son PROPRE serveur (comme `server_url`, conftest.py, mais dédié à ce
test, jamais le serveur de session partagé par le reste de la suite) :
ce serveur suppose un seul client à la fois (`_app_state`, queues
globales, voir CLAUDE.md/architecture.md) — y connecter un second
navigateur casserait la session de tous les tests e2e suivants (constaté :
"ERROR" en cascade sur tout fichier e2e exécuté après celui-ci dans la
même session pytest, car la page de session partagée est renvoyée au
menu/perturbée par la connexion d'un second client socket.io). Réutilise
en revanche le `Browser` déjà lancé par la fixture `page` (session-scoped)
via `page.context.browser.new_context()` plutôt qu'un second
`sync_playwright()` : celui-ci reste actif pour toute la session, et une
seconde instance sur le même fil lève "It looks like you are using
Playwright Sync API inside the asyncio loop".

Sans échiquier ni Lichess réels (ALCHESS_SKIP_BOARD=1, jeton toujours vide
via `_build_isolated_alchess_dir`, mêmes garanties que `server_url`).

Lancer : pytest nicsoft/tests/e2e/test_issue369_startup_js_guard.py -v
"""
import os
import time

import pytest
import requests

from nicsoft.tests.e2e.conftest import (
    PYTHON,
    REPO_DIR,
    _build_isolated_alchess_dir,
    _kill_process,
    _start_line_reader,
    wait_for_server_url,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def serveur_dedie(tmp_path_factory):
    """Serveur AlChess indépendant, jamais celui de session (voir docstring
    du module) : démarré et arrêté (PID exact) pour ce seul test."""
    import subprocess

    env = os.environ.copy()
    env["BROWSER"] = "/bin/true"
    env["ALCHESS_SKIP_BOARD"] = "1"
    env["ALCHESS_DIR"] = str(_build_isolated_alchess_dir(tmp_path_factory))
    env["ALCHESS_SKIP_SINGLE_INSTANCE"] = "1"
    env["ALCHESS_SKIP_AUTO_ANALYSE"] = "1"

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

        ready = False
        for _ in range(30):
            try:
                if requests.get(url, timeout=1).status_code == 200:
                    ready = True
                    break
            except requests.exceptions.RequestException:
                pass
            time.sleep(0.3)
        if not ready:
            _kill_process(proc)
            pytest.fail(f"Serveur AlChess démarré ({url}) mais ne répond jamais 200")

        yield url
    finally:
        _kill_process(proc)


def test_demarrage_sans_erreur_js_et_overlay_masque(page, serveur_dedie):
    ctx = page.context.browser.new_context()
    try:
        fresh_page = ctx.new_page()
        erreurs = []
        fresh_page.on("pageerror", lambda exc: erreurs.append(str(exc)))

        fresh_page.goto(serveur_dedie, wait_until="networkidle")
        fresh_page.wait_for_selector("#startup-overlay", state="hidden", timeout=15000)

        assert erreurs == [], f"erreur(s) JS au démarrage : {erreurs}"
        assert fresh_page.locator("#screen-menu").is_visible()
    finally:
        ctx.close()
