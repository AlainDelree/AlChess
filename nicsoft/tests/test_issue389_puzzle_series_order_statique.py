"""
nicsoft/tests/test_issue389_puzzle_series_order_statique.py — AlChess

Issue #389, point 2 : ordre d'affichage des boutons "Série à jouer" —
Thème, puis Phase de partie, puis Mélange en dernier (demande d'Alain,
suite de #388). Valeur par défaut/mémorisée et logique de résolution de
l'angle (_resolve_puzzle_series_angle) inchangées — vérifié séparément par
test_issue388_lichess_puzzle_config_screen.py, toujours vert après ce
changement d'ordre purement visuel.

Garde statique sur index.html, sans navigateur ni serveur."""
import pathlib
import re

HTML_PATH = pathlib.Path(__file__).parent.parent / "web" / "templates" / "index.html"


def _html():
    return HTML_PATH.read_text(encoding="utf-8")


def test_ordre_affichage_theme_puis_phase_puis_melange():
    html = _html()
    positions = {
        mode: html.index(f'data-serie-mode="{mode}"')
        for mode in ("theme", "phase", "mix")
    }
    assert positions["theme"] < positions["phase"] < positions["mix"], (
        f"ordre inattendu des boutons de série : {positions}"
    )


def test_bouton_melange_reste_selectionne_par_defaut_visuellement():
    """La classe "selected" posée en dur dans le HTML (avant toute réponse
    de config.json) doit rester sur "Mélange", comportement par défaut
    inchangé par le réordonnancement visuel."""
    html = _html()
    match = re.search(
        r'<button[^>]*data-serie-mode="mix"[^>]*>', html,
    )
    assert match, "bouton 'Mélange' introuvable"
    assert "selected" in match.group(0)
    for mode in ("theme", "phase"):
        other = re.search(rf'<button[^>]*data-serie-mode="{mode}"[^>]*>', html)
        assert other, f"bouton '{mode}' introuvable"
        assert "selected" not in other.group(0)


# ── Issue #389, point 4 : bouton "Retour aux réglages" (fin de problème,
#    en cours de séance, bilan) — jamais "back_menu" ────────────────────────

def test_boutons_retour_du_panneau_probleme_et_du_bilan_envoient_back_config_lichess():
    html = _html()
    screen_puzzle = html[html.index('id="screen-lichess-puzzle"'):html.index('id="screen-lichess-puzzle-summary"')]
    screen_summary = html[html.index('id="screen-lichess-puzzle-summary"'):]
    for label, screen in (("screen-lichess-puzzle", screen_puzzle), ("screen-lichess-puzzle-summary", screen_summary)):
        match = re.search(r'<button[^>]*data-i18n="lichess\.puzzle\.retour_reglages"[^>]*>', screen)
        assert match, f"bouton 'Retour aux réglages' introuvable dans {label}"
        assert 'data-action="back_config_lichess"' in match.group(0), (
            f"{label} : bouton de retour n'envoie pas back_config_lichess : {match.group(0)}"
        )
        assert 'data-action="back_menu"' not in match.group(0)
