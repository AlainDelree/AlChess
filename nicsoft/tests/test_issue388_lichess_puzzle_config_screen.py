"""
nicsoft/tests/test_issue388_lichess_puzzle_config_screen.py — AlChess

Issue #388, point 2 : écran de configuration des problèmes Lichess — choix
de la série à jouer (mélange/thème/phase), résolution de l'angle réel
(`_resolve_puzzle_series_angle`/`_build_puzzle_session`,
game_manager_modes/lichess.py) et tableau de bord en arrière-plan
(`check_lichess_puzzle_dashboard`). Aucun réseau réel (get_puzzle_dashboard
monkeypatché), aucun jeton réel — même esprit que
test_issue387_lichess_puzzle_session.py."""

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.lichess import (
    _build_puzzle_session,
    _resolve_puzzle_series_angle,
    check_lichess_puzzle_dashboard,
)
from nicsoft.core.config_manager import DEFAULT_CONFIG


# ── config_manager.py : nouveaux réglages mémorisés ─────────────────────────

def test_config_defaults_contiennent_les_nouveaux_reglages():
    assert DEFAULT_CONFIG["lichess_puzzle_series_mode"] == "mix"
    assert DEFAULT_CONFIG["lichess_puzzle_theme"] == ""
    assert DEFAULT_CONFIG["lichess_puzzle_phase"] == "middlegame"


# ── _resolve_puzzle_series_angle — pur, sans réseau ─────────────────────────

def test_resolve_angle_mode_mix_toujours_vide():
    assert _resolve_puzzle_series_angle({"lichess_puzzle_series_mode": "mix"}) == ""
    assert _resolve_puzzle_series_angle({}) == ""


def test_resolve_angle_mode_theme_valide():
    cfg = {"lichess_puzzle_series_mode": "theme", "lichess_puzzle_theme": "fork"}
    assert _resolve_puzzle_series_angle(cfg) == "fork"


def test_resolve_angle_mode_theme_invalide_replie_sur_mix():
    cfg = {"lichess_puzzle_series_mode": "theme", "lichess_puzzle_theme": "n_importe_quoi"}
    assert _resolve_puzzle_series_angle(cfg) == ""
    cfg2 = {"lichess_puzzle_series_mode": "theme", "lichess_puzzle_theme": "middlegame"}  # phase, pas un thème
    assert _resolve_puzzle_series_angle(cfg2) == ""
    cfg3 = {"lichess_puzzle_series_mode": "theme"}  # absent
    assert _resolve_puzzle_series_angle(cfg3) == ""


def test_resolve_angle_mode_phase_valide():
    cfg = {"lichess_puzzle_series_mode": "phase", "lichess_puzzle_phase": "endgame"}
    assert _resolve_puzzle_series_angle(cfg) == "endgame"


def test_resolve_angle_mode_phase_invalide_replie_sur_middlegame():
    cfg = {"lichess_puzzle_series_mode": "phase", "lichess_puzzle_phase": "n_importe_quoi"}
    assert _resolve_puzzle_series_angle(cfg) == "middlegame"
    cfg2 = {"lichess_puzzle_series_mode": "phase", "lichess_puzzle_phase": "fork"}  # thème, pas une phase
    assert _resolve_puzzle_series_angle(cfg2) == "middlegame"
    cfg3 = {"lichess_puzzle_series_mode": "phase"}  # absent
    assert _resolve_puzzle_series_angle(cfg3) == "middlegame"


def test_resolve_angle_mode_inconnu_replie_sur_mix():
    cfg = {"lichess_puzzle_series_mode": "n_importe_quoi", "lichess_puzzle_theme": "fork"}
    assert _resolve_puzzle_series_angle(cfg) == ""


# ── _build_puzzle_session — intègre la résolution d'angle ──────────────────

def test_build_puzzle_session_theme_choisi(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_puzzle_session_size": 10,
        "lichess_puzzle_series_mode": "theme",
        "lichess_puzzle_theme": "skewer",
    })
    session = _build_puzzle_session()
    assert session.total == 10
    assert session.current_theme == "skewer"


def test_build_puzzle_session_phase_choisie(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {
        "lichess_puzzle_series_mode": "phase",
        "lichess_puzzle_phase": "opening",
    })
    session = _build_puzzle_session()
    assert session.current_theme == "opening"


def test_build_puzzle_session_defaut_reste_mix(monkeypatch):
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {})
    session = _build_puzzle_session()
    assert session.current_theme == ""


# ── check_lichess_puzzle_dashboard ──────────────────────────────────────────

def test_dashboard_sans_jeton_signale_indisponible(monkeypatch):
    sent = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent.append((etype, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {})
    check_lichess_puzzle_dashboard()
    assert sent == [("lichess_puzzle_dashboard", {"available": False, "themes": {}, "default_theme": ""})]


def test_dashboard_ok_calcule_le_theme_par_defaut(monkeypatch):
    sent = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent.append((etype, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test"})

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    themes = {
        "fork": {"nb": 20, "first_wins": 10, "performance": 1600},
        "pin": {"nb": 15, "first_wins": 5, "performance": 1400},
    }
    monkeypatch.setattr(puzzle_client_mod, "get_puzzle_dashboard", lambda token, days=30: {
        "status": "ok", "themes": themes,
    })
    check_lichess_puzzle_dashboard()
    assert len(sent) == 1
    etype, data = sent[0]
    assert etype == "lichess_puzzle_dashboard"
    assert data["available"] is True
    assert data["themes"] == themes
    assert data["default_theme"] == "pin"


def test_dashboard_statut_non_ok_signale_indisponible_sans_erreur(monkeypatch):
    sent = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent.append((etype, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test"})

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_puzzle_dashboard", lambda token, days=30: {
        "status": "network_error",
    })
    check_lichess_puzzle_dashboard()
    assert sent == [("lichess_puzzle_dashboard", {"available": False, "themes": {}, "default_theme": ""})]


def test_dashboard_exception_jamais_propagee(monkeypatch):
    sent = []
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: sent.append((etype, data)))
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_test"})

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod

    def boom(token, days=30):
        raise RuntimeError("panne simulée")

    monkeypatch.setattr(puzzle_client_mod, "get_puzzle_dashboard", boom)
    check_lichess_puzzle_dashboard()  # ne doit jamais lever
    assert sent == [("lichess_puzzle_dashboard", {"available": False, "themes": {}, "default_theme": ""})]
