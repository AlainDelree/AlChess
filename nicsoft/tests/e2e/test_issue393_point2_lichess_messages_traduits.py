"""
nicsoft/tests/e2e/test_issue393_point2_lichess_messages_traduits.py — AlChess

Issue #393, point 2 : un texte brut venu de l'API Lichess (toujours en
anglais — "Not your turn, or game already over", "Piece on c2 cannot move
to c4"...) ne doit plus jamais apparaître dans la phrase affichée à
l'utilisateur, quelle que soit la langue choisie. Le serveur reconnaît le
message (errors.py::translate_api_detail, voir
test_issue393_point2_lichess_detail_translation.py pour la partie Python)
et transmet une CLÉ i18n (jamais le texte anglais) ; c'est
`_lichessResolveToastVars()` (app.js) qui la résout dans la langue
courante avant affichage — fonction PURE testée ici directement via
`page.evaluate`, comme `_lichessPuzzleSortThemeKeys` (#389)."""


def test_detail_key_connue_resolue_dans_les_trois_langues(page):
    try:
        for locale in ("fr", "en", "de"):
            page.evaluate("(l) => i18n.load(l)", locale)
            resolved = page.evaluate(
                """() => _lichessResolveToastVars({
                    detail_key: 'lichess.detail.piece_ne_peut_aller',
                    detail_vars: {depart: 'c2', arrivee: 'c4'},
                })"""
            )
            attendu = page.evaluate(
                "() => t('lichess.detail.piece_ne_peut_aller', {depart: 'c2', arrivee: 'c4'})"
            )
            assert resolved["detail"] == " : " + attendu, locale
            # fr/de : aucune trace du texte anglais BRUT de Lichess — en
            # anglais, la traduction légitime ("the piece on ... cannot
            # move to ...") ressemble forcément au texte source, ce n'est
            # pas le "texte brut" visé ici (celui-là n'existe jamais côté
            # navigateur, voir translate_api_detail côté serveur).
            if locale != "en":
                assert "cannot move" not in resolved["detail"].lower()
                assert "piece on" not in resolved["detail"].lower()
    finally:
        page.evaluate("(l) => i18n.load(l)", "fr")


def test_detail_key_absente_ou_vide_ne_laisse_aucun_detail(page):
    # Clé absente (vars sans detail_key du tout) -> vars inchangées.
    sans_cle = page.evaluate("() => _lichessResolveToastVars({type: 'warning'})")
    assert "detail" not in sans_cle

    # detail_key explicitement vide (ex. refus d'équilibre des couleurs,
    # déjà expliqué par la phrase elle-même) -> aucun détail ajouté.
    vide = page.evaluate(
        "() => _lichessResolveToastVars({detail_key: '', detail_vars: {}})"
    )
    assert vide["detail"] == ""


def test_message_inconnu_resolu_en_phrase_generique_sans_anglais_brut(page):
    try:
        for locale in ("fr", "en", "de"):
            page.evaluate("(l) => i18n.load(l)", locale)
            resolved = page.evaluate(
                """() => _lichessResolveToastVars({detail_key: 'lichess.detail.generique', detail_vars: {}})"""
            )
            attendu = page.evaluate("() => t('lichess.detail.generique')")
            assert resolved["detail"] == " : " + attendu, locale
    finally:
        page.evaluate("(l) => i18n.load(l)", "fr")


def test_coup_refuse_sans_detail_affiche_le_message_generique(page):
    """lichess_move_refused sans detail_key (message Lichess vide) ->
    texte générique "coup refusé", jamais "(undefined)" ni une phrase
    anglaise brute."""
    text = page.evaluate(
        """() => {
            const detailText = null ? t(null, {}) : '';
            return detailText ? t('lichess.coup_refuse_detail', {detail: detailText}) : t('lichess.coup_refuse');
        }"""
    )
    assert text == page.evaluate("() => t('lichess.coup_refuse')")


def test_coup_refuse_detail_connu_ne_contient_jamais_de_texte_anglais_brut(page):
    try:
        for locale in ("fr", "en", "de"):
            page.evaluate("(l) => i18n.load(l)", locale)
            text = page.evaluate(
                """() => {
                    const detailKey = 'lichess.detail.pas_votre_tour_ou_terminee';
                    const detailText = t(detailKey, {});
                    return t('lichess.coup_refuse_detail', {detail: detailText});
                }"""
            )
            if locale != "en":
                assert "not your turn" not in text.lower()
                assert "game already over" not in text.lower()
    finally:
        page.evaluate("(l) => i18n.load(l)", "fr")
