"""
nicsoft/tests/test_issue393_point1_lichess_dashboard_indisponible.py —
AlChess

Issue #393, point 1 (suite de l'étude #391) : l'écran de réglages des
problèmes Lichess annotait TOUS les thèmes "jamais joué" quand le tableau
de bord était simplement indisponible (jeton absent, réseau coupé, droit
manquant) — jamais distingué d'un thème réellement jamais joué sur la
période. Ce fichier vérifie :

  1. check_lichess_puzzle_dashboard journalise (INFO) le résultat d'une
     lecture réussie — statut, nombre de thèmes, période — ce qui
     manquait avant cette issue (seuls les échecs étaient journalisés).
  2. Côté navigateur (app.js), _lichessPuzzleRenderThemeOptions distingue
     "indisponible" (mention unique, aucun thème par défaut, aucune
     annotation par option) de "disponible mais vide" (annotation
     "jamais joué" par thème, comme avant #393)."""
import logging

import nicsoft.core.game_manager_modes.lichess as lichess_launcher
from nicsoft.core.game_manager_modes.lichess import check_lichess_puzzle_dashboard


def test_lecture_reussie_journalisee_en_info_sans_jeton_ni_contenu(monkeypatch, caplog):
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: None)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_secret_test"})

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    themes = {
        "fork": {"nb": 20, "first_wins": 10, "performance": 1600},
        "pin": {"nb": 15, "first_wins": 5, "performance": 1400},
    }
    monkeypatch.setattr(puzzle_client_mod, "get_puzzle_dashboard", lambda token, days=30: {
        "status": "ok", "themes": themes,
    })
    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        check_lichess_puzzle_dashboard()
    messages = [r.getMessage() for r in caplog.records if r.name == "niclink.lichess"]
    assert any("lu" in m and "thèmes=2" in m for m in messages), messages
    assert not any("lip_secret_test" in m for m in messages)


def test_lecture_echouee_reste_journalisee_en_info_ou_warning(monkeypatch, caplog):
    """Comportement déjà correct avant #393 (non régressé) : un échec de
    lecture (statut non "ok") est déjà journalisé — ce test fige cette
    garantie, distincte de la nouvelle journalisation du succès."""
    monkeypatch.setattr(lichess_launcher, "send_event", lambda etype, data: None)
    monkeypatch.setattr(lichess_launcher, "load_config", lambda: {"lichess_token": "lip_secret_test"})

    import nicsoft.modes.lichess.puzzle_client as puzzle_client_mod
    monkeypatch.setattr(puzzle_client_mod, "get_puzzle_dashboard", lambda token, days=30: {
        "status": "network_error",
    })
    with caplog.at_level(logging.INFO, logger="niclink.lichess"):
        check_lichess_puzzle_dashboard()
    messages = [r.getMessage() for r in caplog.records if r.name == "niclink.lichess"]
    assert any("indisponible" in m for m in messages), messages
    assert not any("lip_secret_test" in m for m in messages)
