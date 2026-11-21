"""
nicsoft/tests/test_issue368_lichess_network.py — AlChess

Issue #368, partie 1 : absence de réseau dans l'écran Lichess.

Constat corrigé : `test_token()` (client.py) confondait toute erreur HTTP
non-429 (donc une vraie réponse de Lichess, réseau disponible) avec
l'absence de réseau ("network_error") ; `launch_lichess_puzzle()`
(game_manager_modes/lichess.py) mappait ensuite TOUT statut différent de
"ok"/"rate_limited" — "network_error" inclus — sur le message « jeton
refusé » (toast.lichess_invalid_token), trompeur quand la vraie cause est
le réseau. Voir test_issue306_lichess.py pour les tests de classification
de test_token() lui-même (mis à jour par cette même issue) ; ce fichier
couvre : le nouveau statut "lichess_error", la correction de
launch_lichess_puzzle, le nouveau mécanisme de vérification réseau
(check_lichess_network_status/lichess_network_status), et le câblage
HTML/JS/i18n du bandeau permanent + grisage des boutons de l'écran
Lichess.

Entièrement sans réseau (urlopen/test_token monkeypatchés) et sans
matériel.
"""
import json
import threading
import time
from pathlib import Path

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
import nicsoft.modes.lichess.client as lichess_client

REPO_ROOT = Path(__file__).resolve().parents[2]
NICSOFT_DIR = REPO_ROOT / "nicsoft"
APP_JS = NICSOFT_DIR / "web" / "static" / "app.js"
ALCHESS_PY = NICSOFT_DIR / "web" / "alchess.py"
HTML_PATH = NICSOFT_DIR / "web" / "templates" / "index.html"
I18N_DIR = NICSOFT_DIR / "web" / "static" / "i18n"


# ═══════════════════════════════════════════════════════════════════════
# 1. launch_lichess_puzzle — le réseau n'est plus confondu avec un jeton
#    refusé (bug réel corrigé par cette issue)
# ═══════════════════════════════════════════════════════════════════════

def test_launch_lichess_puzzle_reseau_indisponible_ne_dit_jamais_jeton_refuse(monkeypatch):
    """Avant correction : un statut "network_error" de test_token() faisait
    afficher toast.lichess_invalid_token (« Jeton Lichess refusé »), message
    trompeur — la cause réelle est l'absence de réseau, pas le jeton."""
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token_12345"})
    lichess_launcher.web_server._app_state = "config_lichess"

    monkeypatch.setattr(lichess_client, "test_token", lambda token: {"status": "network_error"})

    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"

    assert sent_states
    state, data = sent_states[-1]
    assert state == "config_lichess"
    assert data["toast_message_key"] == "toast.lichess_network_error"
    assert data["toast_message_key"] != "toast.lichess_invalid_token"


def test_launch_lichess_puzzle_jeton_vraiment_refuse_dit_bien_jeton_refuse(monkeypatch):
    """Non-régression : un jeton réellement refusé par Lichess (statut
    "invalid", Lichess a répondu) garde bien le message « jeton refusé »."""
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token_12345"})
    lichess_launcher.web_server._app_state = "config_lichess"

    monkeypatch.setattr(lichess_client, "test_token", lambda token: {"status": "invalid"})

    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"

    assert sent_states
    state, data = sent_states[-1]
    assert state == "config_lichess"
    assert data["toast_message_key"] == "toast.lichess_invalid_token"


def test_launch_lichess_puzzle_autre_erreur_lichess_message_dedie(monkeypatch):
    """Une erreur applicative Lichess (5xx, réseau disponible) a son propre
    message générique — jamais "jeton refusé" ni "réseau"."""
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token_12345"})
    lichess_launcher.web_server._app_state = "config_lichess"

    monkeypatch.setattr(lichess_client, "test_token", lambda token: {"status": "lichess_error"})

    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"

    assert sent_states
    state, data = sent_states[-1]
    assert state == "config_lichess"
    assert data["toast_message_key"] == "toast.lichess_error"


def test_launch_lichess_puzzle_rate_limited_inchange(monkeypatch):
    """Non-régression : la limite de requêtes garde son propre message."""
    sent_states = []
    monkeypatch.setattr(lichess_launcher, "set_app_state", lambda state, data=None: sent_states.append((state, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token_12345"})
    lichess_launcher.web_server._app_state = "config_lichess"

    monkeypatch.setattr(lichess_client, "test_token", lambda token: {"status": "rate_limited"})

    try:
        lichess_launcher.launch_lichess_puzzle({"player": "Alain"})
    finally:
        lichess_launcher.web_server._app_state = "menu"

    assert sent_states
    state, data = sent_states[-1]
    assert state == "config_lichess"
    assert data["toast_message_key"] == "toast.lichess_rate_limited"


# ═══════════════════════════════════════════════════════════════════════
# 2. check_lichess_network_status — classification statut → disponibilité,
#    jamais mêlée au statut du jeton
# ═══════════════════════════════════════════════════════════════════════

def _run_check(monkeypatch, status, token="lip_test_token_12345"):
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data=None: events.append((etype, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": token})
    monkeypatch.setattr(lichess_client, "test_token", lambda t: {"status": status})
    lichess_launcher.check_lichess_network_status()
    return events


def test_check_network_status_ok_disponible(monkeypatch):
    events = _run_check(monkeypatch, "ok")
    assert events == [("lichess_network_status", {"available": True})]


def test_check_network_status_jeton_refuse_reste_disponible(monkeypatch):
    """Un jeton refusé prouve que Lichess est joignable — jamais signalé
    comme un problème réseau (c'est précisément le bug #368)."""
    events = _run_check(monkeypatch, "invalid")
    assert events == [("lichess_network_status", {"available": True})]


def test_check_network_status_rate_limited_reste_disponible(monkeypatch):
    events = _run_check(monkeypatch, "rate_limited")
    assert events == [("lichess_network_status", {"available": True})]


def test_check_network_status_erreur_lichess_reste_disponible(monkeypatch):
    events = _run_check(monkeypatch, "lichess_error")
    assert events == [("lichess_network_status", {"available": True})]


def test_check_network_status_reseau_indisponible(monkeypatch):
    events = _run_check(monkeypatch, "network_error")
    assert events == [("lichess_network_status", {"available": False})]


def test_check_network_status_sans_jeton_pas_d_alarme(monkeypatch):
    """Écran normalement inaccessible sans jeton (issue #365) — rien à
    tester, jamais un faux "indisponible" dans ce cas."""
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data=None: events.append((etype, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": ""})
    called = []
    monkeypatch.setattr(lichess_client, "test_token", lambda t: called.append(t) or {"status": "ok"})
    lichess_launcher.check_lichess_network_status()
    assert events == [("lichess_network_status", {"available": True})]
    assert called == []


def test_check_network_status_une_seule_verification_a_la_fois(monkeypatch):
    """Verrou non bloquant : un appel reçu pendant qu'une vérification est
    déjà en cours est ignoré — jamais de requêtes empilées."""
    events = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data=None: events.append((etype, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test_token_12345"})

    release = threading.Event()
    entered = threading.Event()

    def slow_test_token(token):
        entered.set()
        release.wait(timeout=2)
        return {"status": "ok"}

    monkeypatch.setattr(lichess_client, "test_token", slow_test_token)

    t = threading.Thread(target=lichess_launcher.check_lichess_network_status, daemon=True)
    t.start()
    assert entered.wait(timeout=2), "la première vérification n'a jamais démarré"

    # Pendant que la première tourne, un second appel doit être ignoré sans bloquer.
    lichess_launcher.check_lichess_network_status()
    assert events == []  # le second appel n'a rien émis (verrou déjà pris)

    release.set()
    t.join(timeout=2)
    assert events == [("lichess_network_status", {"available": True})]


# ═══════════════════════════════════════════════════════════════════════
# 3. game_manager.py (façade) — réexporte bien la nouvelle fonction
# ═══════════════════════════════════════════════════════════════════════

def test_game_manager_reexporte_check_lichess_network_status():
    import nicsoft.core.game_manager as gm
    assert hasattr(gm, "check_lichess_network_status")
    assert gm.check_lichess_network_status is lichess_launcher.check_lichess_network_status


# ═══════════════════════════════════════════════════════════════════════
# 4. Câblage alchess.py — action "lichess_network_check" + ouverture de
#    l'écran Lichess déclenchent bien la vérification (inspection du
#    câblage, sur le modèle de test_issue333_lichess_human_resume.py).
# ═══════════════════════════════════════════════════════════════════════

def test_alchess_py_route_lichess_network_check():
    src = ALCHESS_PY.read_text(encoding="utf-8")
    assert '"lichess_network_check"' in src
    bloc = src[src.index('"lichess_network_check"'):]
    assert "check_lichess_network_status" in bloc[:400]


def test_alchess_py_verifie_le_reseau_a_l_ouverture_de_l_ecran_lichess():
    src = ALCHESS_PY.read_text(encoding="utf-8")
    bloc = src[src.index('action.get("value") == "lichess":'):]
    assert "check_lichess_network_status" in bloc[:800]


# ═══════════════════════════════════════════════════════════════════════
# 5. Câblage app.js — garde #359 (tout évènement émis a un gestionnaire),
#    bandeau permanent, grisage générique, minuterie, online/offline.
# ═══════════════════════════════════════════════════════════════════════

def test_appjs_gere_l_evenement_lichess_network_status():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'socket.on("lichess_network_status"' in js


def test_appjs_bandeau_reseau_pilote_par_la_fonction_dediee():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'getElementById("lichess-network-banner")' in js
    assert "function _applyLichessNetworkState()" in js


def test_appjs_grisage_generique_data_needs_network():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'document.querySelectorAll("#screen-config-lichess [data-needs-network]")' in js


def test_appjs_minuterie_raisonnable_une_seule_verification_a_la_fois():
    js = APP_JS.read_text(encoding="utf-8")
    assert "LICHESS_NETWORK_CHECK_INTERVAL_MS" in js
    assert "_lichessNetworkCheckPending" in js
    # Intervalle raisonnable : ni en rafale (quelques secondes), ni trop
    # long pour rester réactif pendant que l'écran reste ouvert.
    import re
    m = re.search(r"LICHESS_NETWORK_CHECK_INTERVAL_MS\s*=\s*(\d+)", js)
    assert m
    assert 10000 <= int(m.group(1)) <= 60000


def test_appjs_ecoute_les_evenements_online_offline_du_navigateur():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'window.addEventListener("online"' in js
    assert 'window.addEventListener("offline"' in js


def test_appjs_timer_demarre_et_arrete_avec_l_ecran_lichess():
    js = APP_JS.read_text(encoding="utf-8")
    assert "_lichessNetworkCheckTimer = setInterval" in js
    assert "clearInterval(_lichessNetworkCheckTimer)" in js
    assert "_onLichessConfigScreen" in js


def test_appjs_boutons_lancement_puzzle_et_partie_combinent_reseau():
    """btn-start-lichess-puzzle et btn-start-lichess restent gérés par leurs
    calculs dédiés (board + jeton + réseau combinés) — jamais par la
    boucle générique data-needs-network, qui écraserait leur état selon
    l'ordre d'exécution (second mécanisme interdit, voir architecture.md)."""
    js = APP_JS.read_text(encoding="utf-8")
    assert '!_lichessNetworkAvailable' in js
    bloc_puzzle = js[js.index("function _applyLichessPuzzleBoardState()"):]
    assert "_lichessNetworkAvailable" in bloc_puzzle[:600]
    bloc_badge = js[js.index("function _applyBoardBadge()"):js.index("function _applyLichessCardState()")]
    assert '!_lichessNetworkAvailable' in bloc_badge


# ═══════════════════════════════════════════════════════════════════════
# 6. Câblage index.html — bandeau permanent (même style que le bandeau
#    échiquier absent), caché par défaut, boutons/contrôles grisables.
# ═══════════════════════════════════════════════════════════════════════

def test_html_bandeau_reseau_meme_style_que_bandeau_echiquier():
    import re
    html = HTML_PATH.read_text(encoding="utf-8")
    bloc = re.search(r'<div[^>]*id="lichess-network-banner"[^>]*>', html)
    assert bloc, "bandeau #lichess-network-banner introuvable"
    attrs = bloc.group(0)
    assert "board-warning-banner" in attrs, "doit réutiliser la classe du bandeau échiquier (même style)"
    assert "hidden" in attrs, "caché par défaut"
    assert 'data-i18n="banner.lichess_network_absent"' in attrs


def test_html_retour_ne_porte_jamais_data_needs_network():
    import re
    html = HTML_PATH.read_text(encoding="utf-8")
    debut = html.index('id="screen-config-lichess"')
    fin = html.index('id="screen-lichess-seeking"')
    bloc_ecran = html[debut:fin]
    for m in re.finditer(r'<button[^>]*data-action="back_menu"[^>]*>', bloc_ecran):
        assert "data-needs-network" not in m.group(0), "« Retour » doit toujours rester actif"


def test_html_boutons_lancement_grisables_sans_second_mecanisme():
    """btn-start-lichess-puzzle et btn-start-lichess ne portent pas
    data-needs-network dans le HTML (gérés par calcul dédié en JS, voir
    test_appjs_boutons_lancement_puzzle_et_partie_combinent_reseau) —
    tandis que les autres contrôles de lancement/choix de l'écran en
    portent bien un (grisage générique)."""
    import re
    html = HTML_PATH.read_text(encoding="utf-8")
    for btn_id in ("btn-start-lichess-puzzle", "btn-start-lichess"):
        bloc = re.search(rf'<button[^>]*id="{btn_id}"[^>]*>', html)
        assert bloc, f"#{btn_id} introuvable"
        assert "data-needs-network" not in bloc.group(0)

    debut = html.index('id="screen-config-lichess"')
    fin = html.index('id="screen-lichess-seeking"')
    bloc_ecran = html[debut:fin]
    controles_attendus = [
        "cfg-lichess-puzzle-mode-board", "cfg-lichess-puzzle-mode-virtual",
        "cfg-lichess-opponent-human", "cfg-lichess-opponent-ai",
        "cfg-lichess-rated", "cfg-lichess-level", "cfg-lichess-cadence",
        "cfg-lichess-white", "cfg-lichess-black", "cfg-lichess-random",
        "cfg-lichess-player",
    ]
    for ctrl_id in controles_attendus:
        m = re.search(rf'id="{ctrl_id}"[^>]*>', bloc_ecran)
        assert m, f"#{ctrl_id} introuvable dans l'écran Lichess"
        assert "data-needs-network" in m.group(0), f"#{ctrl_id} doit être grisable (data-needs-network)"


# ═══════════════════════════════════════════════════════════════════════
# 7. i18n — nouvelles clés présentes et cohérentes dans les 3 locales
# ═══════════════════════════════════════════════════════════════════════

NOUVELLES_CLES = [
    "banner.lichess_network_absent",
    "parametres.lichess.resultat.erreur_lichess",
]


def _load(locale):
    return json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def test_nouvelles_cles_presentes_dans_les_trois_locales():
    for locale in ("fr", "en", "de"):
        data = _load(locale)
        for cle in NOUVELLES_CLES:
            assert cle in data, f"{locale}.json n'a pas la clé {cle}"
            assert data[cle].strip(), f"{locale}.json : {cle} est vide"


def test_json_des_trois_locales_reste_valide():
    for locale in ("fr", "en", "de"):
        _load(locale)  # lève si invalide
