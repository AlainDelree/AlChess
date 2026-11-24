"""
nicsoft/tests/test_issue380_i18n_global_parity.py — AlChess

Issue #380 : garde-fou global de parité i18n, indépendant de tout issue
ponctuelle. L'étude #379 a relevé qu'environ 14 tests dispersés ne
vérifient chacun que quelques clés propres à leur propre issue — aucun ne
détectait une clé retirée d'une seule langue (fr/en/de) parmi les ~860
existantes. Ce fichier comble ce trou une fois pour toutes, sans remplacer
ni modifier les tests ponctuels existants.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "nicsoft" / "web" / "static" / "i18n"
LOCALES = ("fr", "en", "de")


def _load(locale):
    return json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def test_meme_jeu_de_cles_exactement_dans_les_trois_locales():
    data = {locale: _load(locale) for locale in LOCALES}
    cles = {locale: set(d) for locale, d in data.items()}
    reference = cles["fr"]
    for locale in LOCALES:
        if cles[locale] != reference:
            manquantes = reference - cles[locale]
            en_trop = cles[locale] - reference
            raise AssertionError(
                f"{locale}.json diverge de fr.json — "
                f"manquantes : {sorted(manquantes)} ; en trop : {sorted(en_trop)}"
            )


def test_toutes_les_valeurs_non_vides_dans_les_trois_locales():
    for locale in LOCALES:
        data = _load(locale)
        vides = [cle for cle, valeur in data.items() if not isinstance(valeur, str) or not valeur.strip()]
        assert not vides, f"{locale}.json : clés vides ou non textuelles : {vides}"
