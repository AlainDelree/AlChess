"""
nicsoft/tests/test_issue393_point2_lichess_detail_translation.py — AlChess

Issue #393, point 2 (suite de l'étude #391) : un texte brut venu de l'API
Lichess (toujours en anglais) ne doit plus jamais être inséré directement
dans la phrase affichée à l'utilisateur. `errors.py::translate_api_detail`
reconnaît les messages déjà observés (code ou tests existants) et
retourne une clé i18n (jamais le texte anglais lui-même) ; un message
inconnu retombe sur une clé générique. Ce fichier teste cette fonction
PURE, ainsi que les points d'appel qui la relaient désormais (jamais le
texte anglais brut dans `vars`) — le texte brut reste disponible par
ailleurs dans le journal (déjà écrit par chaque appelant AVANT cet appel,
inchangé ici)."""
import pytest

from nicsoft.modes.lichess.errors import translate_api_detail
from nicsoft.modes.lichess.game import _move_refused_payload


@pytest.mark.parametrize("message,expected_key,expected_vars", [
    ("Not your turn, or game already over",
     "lichess.detail.pas_votre_tour_ou_terminee", {}),
    ("NOT YOUR TURN, OR GAME ALREADY OVER",
     "lichess.detail.pas_votre_tour_ou_terminee", {}),
    ("Piece on c2 cannot move to c4",
     "lichess.detail.piece_ne_peut_aller", {"depart": "c2", "arrivee": "c4"}),
    ("piece on a7 cannot move to a8",
     "lichess.detail.piece_ne_peut_aller", {"depart": "a7", "arrivee": "a8"}),
    ("Game is already over",
     "lichess.detail.partie_terminee", {}),
    ("Too soon to claim victory",
     "lichess.detail.generique", {}),
    ("You already have an offer",
     "lichess.detail.generique", {}),
    ("", "", {}),
])
def test_translate_api_detail_messages_connus_et_inconnus(message, expected_key, expected_vars):
    key, vars_ = translate_api_detail(message)
    assert key == expected_key
    assert vars_ == expected_vars


def test_translate_api_detail_ne_leve_jamais_sur_entree_absente():
    assert translate_api_detail(None) == ("", {})


def test_move_refused_payload_garde_le_message_brut_pour_le_journal_et_la_logique():
    """`message` reste le texte EXACT de Lichess — consommé par la logique
    de resynchronisation/relecture (#347/#368/#392), jamais seulement pour
    l'affichage : ce champ ne doit JAMAIS disparaître ni être traduit."""
    payload = _move_refused_payload("Not your turn, or game already over")
    assert payload["message"] == "Not your turn, or game already over"
    assert payload["detail_key"] == "lichess.detail.pas_votre_tour_ou_terminee"
    assert payload["detail_vars"] == {}


def test_move_refused_payload_coup_illegal_porte_les_cases():
    payload = _move_refused_payload("Piece on e2 cannot move to e5")
    assert payload["detail_key"] == "lichess.detail.piece_ne_peut_aller"
    assert payload["detail_vars"] == {"depart": "e2", "arrivee": "e5"}


def test_aucune_valeur_i18n_lichess_detail_ne_contient_de_texte_anglais_brut():
    """Garde-fou statique (issue #393, point 2) : les clés lichess.detail.*
    ajoutées pour cette traduction ne doivent jamais contenir un fragment
    anglais reconnaissable des messages bruts de Lichess, dans AUCUNE des
    3 langues (une clé i18n n'est jamais "la traduction anglaise redite")."""
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    i18n_dir = repo_root / "nicsoft" / "web" / "static" / "i18n"
    forbidden = ("not your turn", "cannot move to", "piece on")
    for locale in ("fr", "de"):
        data = json.loads((i18n_dir / f"{locale}.json").read_text(encoding="utf-8"))
        for key, value in data.items():
            if not key.startswith("lichess.detail."):
                continue
            lowered = value.lower()
            for fragment in forbidden:
                assert fragment not in lowered, (locale, key, value)
