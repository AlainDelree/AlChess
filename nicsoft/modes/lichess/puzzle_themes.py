"""
nicsoft/modes/lichess/puzzle_themes.py — AlChess

Issue #388, point 0 : clés d'« angle » (thème ou phase de partie) acceptées
par l'API publique des problèmes Lichess (`GET /api/puzzle/next?angle=...`,
`GET/POST /api/puzzle/batch/{angle}`) — jamais une chaîne arbitraire
insérée dans l'adresse (voir puzzle_client.py::get_next_puzzle).

Vérification faite le 25/11/2026, en lecture seule, SANS jeton (requêtes
anonymes vers `https://lichess.org/api/puzzle/next?angle=<clé>`, réponse
200 avec la clé effectivement présente dans `puzzle.themes` ⇒ clé valide ;
404 ⇒ clé refusée) :
  - Phases de partie CONFIRMÉES par cette méthode : "opening", "middlegame",
    "endgame" (chacune testée individuellement, HTTP 200, thème demandé bien
    présent dans la réponse).
  - "mix" (mélange, comportement par défaut d'AlChess — angle omis plutôt
    qu'envoyé explicitement, les deux étant équivalents d'après la doc
    publique) et une soixantaine de thèmes tactiques testés un par un
    (fork, pin, skewer, mateIn1..5, les "XMate", les variantes de finale
    pièce par pièce, etc.) : tous confirmés HTTP 200 de la même façon.
  - "zugzwang" : présent dans la ressource source publique ci-dessous mais
    NON reconfirmé en direct (limite de requêtes anonymes atteinte après
    plus de 70 appels successifs — HTTP 429 — volontairement non
    recommencé pour rester raisonnable envers l'API publique) : conservé
    ici sur la seule foi de la documentation (hypothèse, pas une
    vérification réseau directe).
  - Rejetés (HTTP 404 à la vérification directe, donc PAS de simples clés
    d'angle) : "playerGames" (nécessite des paramètres supplémentaires,
    absents de ce besoin) et "promotePawnToQueenRookOrMinor" (c'est en
    réalité le texte de description de "promotion", pas une clé à part —
    erreur possible de lecture rapide de la ressource source).

Liste complète des clés (74 avant exclusion des phases/du mélange)
établie à partir de la ressource source anglaise officielle de Lichess
(fichier `translation/source/puzzleTheme.xml`, dépôt GitHub public
lichess-org/lila, lu le 25/11/2026 via raw.githubusercontent.com) — chaque
`<string name="X">` (hors suffixe "Description") y correspond exactement
à une clé d'angle valide, à l'exception des trois rejets ci-dessus. Les
libellés fr/en/de de PUZZLE_THEME_KEYS/PUZZLE_PHASE_KEYS (static/i18n/*.json,
espace de noms lichess.puzzle_theme.*/lichess.puzzle_phase.*) viennent des
traductions officielles correspondantes du même dépôt
(translation/dest/puzzleTheme/{fr,de}-*.xml), jamais inventées.

Structure du tableau de bord (`GET /api/puzzle/dashboard/{jours}`, droit
puzzle:read) confirmée par la spécification publique (dépôt GitHub public
lichess-org/api, doc/specs/schemas/PuzzleDashboard.yaml + PuzzlePerformance.yaml
+ exemple doc/specs/examples/puzzles-getYourPuzzleDashboard.json.yaml, lus le
25/11/2026 — endpoint authentifié, jamais appelé directement pour cette
vérification) : {"days", "global": PuzzlePerformance,
"themes": {"<clé>": {"theme": "<libellé affiché par Lichess>",
"results": PuzzlePerformance}}}, avec PuzzlePerformance = {"nb", "firstWins",
"replayWins", "puzzleRatingAvg", "performance"} — voir
puzzle_client.py::get_puzzle_dashboard.

Décision sur l'angle de l'envoi du résultat (POST /api/puzzle/batch/mix,
inchangé) : la spécification publique (doc/specs/tags/puzzles/
api-puzzle-batch-angle.yaml) précise que le segment d'adresse {angle} de ce
POST ne sert qu'à décrire le NOUVEAU lot de problèmes renvoyé quand
`nb` > 0 ("equivalent to calling GET .../batch/{angle}") — AlChess envoie
toujours `nb=0` (aucun nouveau lot demandé par cet appel, voir
puzzle_client.py) : ce segment n'a donc aucun effet sur la mise à jour de
cote ni sur le tableau de bord, qui s'appuient sur les thèmes RÉELS du
problème résolu (`puzzle.themes`), jamais sur l'angle utilisé pour
l'obtenir. Garder "mix" sans condition reste donc correct même pour un
problème demandé avec un thème ou une phase précis — aucun changement
nécessaire ici.
"""

# Phases de partie (issue #388, point 2) — ordre d'affichage voulu par
# Alain (ouverture → milieu de jeu → finale) ; défaut "middlegame" (il
# travaillera longtemps le milieu de jeu avant de passer aux finales).
PUZZLE_PHASE_KEYS = ("opening", "middlegame", "endgame")
DEFAULT_PUZZLE_PHASE = "middlegame"

# Angle "mélange" (comportement par défaut, angle omis dans la requête —
# voir get_next_puzzle) — jamais dans PUZZLE_THEME_KEYS/PUZZLE_PHASE_KEYS
# ci-dessous, pour rester distinct du choix explicite d'un thème ou d'une
# phase à l'écran de configuration.
PUZZLE_MIX_ANGLE = "mix"

# 70 thèmes tactiques/catégories (liste complète confirmée, voir ci-dessus)
# — ordre alphabétique (les traductions n'ont pas d'ordre officiel propre).
PUZZLE_THEME_KEYS = (
    "advancedPawn", "advantage", "anastasiaMate", "arabianMate", "attackingF2F7",
    "attraction", "backRankMate", "balestraMate", "bishopEndgame", "blindSwineMate",
    "bodenMate", "capturingDefender", "castling", "clearance", "collinearMove",
    "cornerMate", "crushing", "defensiveMove", "deflection", "discoveredAttack",
    "discoveredCheck", "doubleBishopMate", "doubleCheck", "dovetailMate", "enPassant",
    "epauletteMate", "equality", "exposedKing", "fork", "hangingPiece",
    "hookMate", "interference", "intermezzo", "killBoxMate", "kingsideAttack",
    "knightEndgame", "long", "master", "masterVsMaster", "mate",
    "mateIn1", "mateIn2", "mateIn3", "mateIn4", "mateIn5",
    "morphysMate", "oneMove", "operaMate", "pawnEndgame", "pillsburysMate",
    "pin", "promotion", "queenEndgame", "queenRookEndgame", "queensideAttack",
    "quietMove", "rookEndgame", "sacrifice", "short", "skewer",
    "smotheredMate", "superGM", "swallowstailMate", "trappedPiece", "triangleMate",
    "underPromotion", "veryLong", "vukovicMate", "xRayAttack", "zugzwang",
)

# Tout angle qu'AlChess peut envoyer explicitement à Lichess (thème OU
# phase) — jamais "mix" (mélange = angle omis, voir get_next_puzzle).
ALL_PUZZLE_ANGLES = frozenset(PUZZLE_THEME_KEYS) | frozenset(PUZZLE_PHASE_KEYS)

# Seuil (nombre de problèmes joués sur la période du tableau de bord) en
# dessous duquel un thème est jugé "peu joué" — ni éligible au calcul du
# thème par défaut (point faible), ni considéré comme une statistique
# fiable à l'écran (voir compute_default_theme ci-dessous et
# config.lichess.probleme_* dans app.js/index.html).
PUZZLE_THEME_MIN_PLAYS = 10


def compute_default_theme(themes: dict, min_plays: int = PUZZLE_THEME_MIN_PLAYS) -> str:
    """Thème proposé par défaut à l'écran de configuration (issue #388,
    point 2) : parmi les thèmes du tableau de bord (`themes`, forme
    {clé: {"nb": int, "first_wins": int, "performance": int, ...}}, voir
    puzzle_client.py::get_puzzle_dashboard) joués au moins `min_plays` fois
    ET qui sont de VRAIS thèmes (jamais une phase de partie, ni une clé
    inconnue — PUZZLE_THEME_KEYS fait foi), celui dont la performance
    (cote de performance Lichess, pas un pourcentage) est la plus basse.
    En cas d'égalité, celui dont le taux de réussite du premier coup
    (`first_wins`/`nb`) est le plus bas.

    Chaîne vide si `themes` est vide/invalide ou si aucun thème n'atteint
    `min_plays` — jamais d'exception, jamais de valeur inventée (l'écran
    reste alors utilisable sans valeur par défaut calculée, voir le
    rapport de clôture)."""
    if not isinstance(themes, dict):
        return ""
    candidates = []
    for key, stats in themes.items():
        if key not in PUZZLE_THEME_KEYS or not isinstance(stats, dict):
            continue
        nb = stats.get("nb")
        performance = stats.get("performance")
        if not isinstance(nb, int) or not isinstance(performance, int) or nb < min_plays:
            continue
        first_wins = stats.get("first_wins")
        first_win_rate = (first_wins / nb) if isinstance(first_wins, int) and nb > 0 else 1.0
        candidates.append((performance, first_win_rate, key))
    if not candidates:
        return ""
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0][2]
