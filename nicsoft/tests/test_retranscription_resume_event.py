"""
Test issue #283 — l'événement de reprise de la retranscription
(`retranscription_en_cours`) doit être envoyé à CHAQUE ouverture de l'écran
retranscription (pas seulement une fois, 1,5s après le démarrage du
programme), et seulement quand une session est effectivement sauvegardée.

`nicsoft/web/alchess.py::_check_retranscription_session()` est appelée côté
serveur dans le traitement de l'action de menu qui ouvre l'écran
("mode"/"retranscription"). Ce test l'exerce directement, sans navigateur,
sans lancer `main()`, et sans jamais toucher au vrai dossier de données
utilisateur : le chemin de sauvegarde (`SAVE_PATH`) est monkeypatché vers un
fichier dans un dossier temporaire dédié (`tmp_path`).
"""
import json
from unittest.mock import MagicMock

import nicsoft.modes.retranscription.retranscription as retranscription
import nicsoft.web.alchess as alchess


def test_ouverture_sans_session_n_envoie_pas_retranscription_en_cours(tmp_path, monkeypatch):
    """Pas de fichier de session -> aucun événement de reprise envoyé
    (le frontend masque le bandeau par défaut à chaque ouverture)."""
    monkeypatch.setattr(retranscription, "SAVE_PATH", tmp_path / "retranscription_en_cours.json")
    mock_send_event = MagicMock()
    monkeypatch.setattr(alchess, "send_event", mock_send_event)

    alchess._check_retranscription_session()

    mock_send_event.assert_not_called()


def test_ouverture_avec_session_envoie_retranscription_en_cours(tmp_path, monkeypatch):
    """Une session sauvegardée existe -> l'événement est envoyé avec les
    bons joueurs et le bon nombre de coups PGN (règle #274/#277, non modifiée
    ici : pgn_moves_played(3 demi-coups) == 2)."""
    save_path = tmp_path / "retranscription_en_cours.json"
    save_path.write_text(json.dumps({
        "mode": "partie", "white": "Alice", "black": "Bob",
        "date": "", "event": "", "result": "*", "nom": "", "camp_suggere": "white",
        "moves": ["e2e4", "e7e5", "g1f3"],
    }), encoding="utf-8")
    monkeypatch.setattr(retranscription, "SAVE_PATH", save_path)
    mock_send_event = MagicMock()
    monkeypatch.setattr(alchess, "send_event", mock_send_event)

    alchess._check_retranscription_session()

    mock_send_event.assert_called_once_with("retranscription_en_cours", {
        "white": "Alice", "black": "Bob", "moves": 2,
    })


def test_ouverture_repetee_reenvoie_a_chaque_fois_sans_effet_de_bord(tmp_path, monkeypatch):
    """Régression #283 : l'ancien code n'envoyait l'événement qu'une seule
    fois au démarrage du programme. Revenir plusieurs fois sur l'écran doit
    renvoyer l'événement à chaque fois, sans supprimer ni modifier la
    session (simple lecture)."""
    save_path = tmp_path / "retranscription_en_cours.json"
    contenu = json.dumps({"white": "Alice", "black": "Bob", "moves": ["e2e4"]})
    save_path.write_text(contenu, encoding="utf-8")
    monkeypatch.setattr(retranscription, "SAVE_PATH", save_path)
    mock_send_event = MagicMock()
    monkeypatch.setattr(alchess, "send_event", mock_send_event)

    alchess._check_retranscription_session()
    alchess._check_retranscription_session()
    alchess._check_retranscription_session()

    assert mock_send_event.call_count == 3
    assert save_path.read_text(encoding="utf-8") == contenu
