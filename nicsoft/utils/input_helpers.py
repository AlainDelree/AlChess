import sys
import re


def quit_or_retry(message="Entree invalide."):
    print(message)
    try:
        answer = input("Appuie sur Entree pour recommencer, ou q pour quitter : ").strip().lower()
    except KeyboardInterrupt:
        print("\nArret demande par l'utilisateur.")
        sys.exit(0)

    if answer == "q":
        print("Fermeture du programme.")
        sys.exit(0)


def ask_choice(prompt, valid_choices, default=None):
    while True:
        try:
            raw = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nArret demande par l'utilisateur.")
            sys.exit(0)

        if not raw and default is not None:
            return default

        if raw in valid_choices:
            return raw

        quit_or_retry()


def ask_int(prompt, min_value=None, max_value=None, default=None):
    while True:
        try:
            raw = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nArret demande par l'utilisateur.")
            sys.exit(0)

        if not raw and default is not None:
            return default

        try:
            value = int(raw)
        except ValueError:
            quit_or_retry("Merci d'entrer un nombre valide.")
            continue

        if min_value is not None and value < min_value:
            quit_or_retry(f"Valeur trop petite (min: {min_value})")
            continue

        if max_value is not None and value > max_value:
            quit_or_retry(f"Valeur trop grande (max: {max_value})")
            continue

        return value


def ask_nonempty_string(prompt, default=None):
    while True:
        try:
            raw = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nArret demande par l'utilisateur.")
            sys.exit(0)

        if raw:
            return raw

        if default is not None:
            return default

        quit_or_retry("Ce champ ne peut pas etre vide.")


def parse_player_input(raw: str, known_players=None):
    """
    Interprete intelligemment une saisie joueur.

    Cas reconnus :
    - "1"      -> joueur n1, couleur non definie
    - "1 b"    -> joueur n1, blancs  (avec espace)
    - "1b"     -> joueur n1, blancs  (sans espace — NOUVEAU)
    - "2n"     -> joueur n2, noirs   (sans espace — NOUVEAU)
    - "2 n"    -> joueur n2, noirs   (avec espace)
    - "Alain b"-> nom Alain, blancs
    - "Jess a" -> nom Jess, aleatoire

    Retourne un dict :
    {
        "name": str,
        "color": "b" | "n" | "a" | None,
        "used_shortcut": bool,
        "matched_known_player": bool,
    }
    """
    if known_players is None:
        known_players = []

    raw = raw.strip()

    result = {
        "name": "",
        "color": None,
        "used_shortcut": False,
        "matched_known_player": False,
    }

    if not raw:
        return result

    # ── Cas 0 : index+couleur colles, ex: "1b" "2n" "3a" ─────────────────
    # Nouveau : on detecte le pattern chiffre(s) suivi directement d'une
    # lettre de couleur, sans espace.
    m = re.fullmatch(r"(\d+)([bna])", raw, re.IGNORECASE)
    if m:
        idx = int(m.group(1)) - 1
        color = m.group(2).lower()
        if 0 <= idx < len(known_players):
            result["name"] = str(known_players[idx]).strip()
            result["color"] = color
            result["used_shortcut"] = True
            result["matched_known_player"] = True
            return result

    parts = raw.split()

    # ── Cas 1 : index + couleur avec espace, ex: "1 b" ───────────────────
    if len(parts) == 2 and parts[0].isdigit() and parts[1].lower() in {"b", "n", "a"}:
        idx = int(parts[0]) - 1
        if 0 <= idx < len(known_players):
            result["name"] = str(known_players[idx]).strip()
            result["color"] = parts[1].lower()
            result["used_shortcut"] = True
            result["matched_known_player"] = True
            return result

    # ── Cas 2 : index seul, ex: "1" ──────────────────────────────────────
    if len(parts) == 1 and parts[0].isdigit():
        idx = int(parts[0]) - 1
        if 0 <= idx < len(known_players):
            result["name"] = str(known_players[idx]).strip()
            result["color"] = None
            result["used_shortcut"] = True
            result["matched_known_player"] = True
            return result

    # ── Cas 3 : nom + couleur, ex: "Alain b" ─────────────────────────────
    if len(parts) >= 2 and parts[-1].lower() in {"b", "n", "a"}:
        name = " ".join(parts[:-1]).strip()
        if name:
            result["name"] = name
            result["color"] = parts[-1].lower()
            result["used_shortcut"] = True
            result["matched_known_player"] = False
            return result

    # ── Cas 4 : comportement classique ───────────────────────────────────
    result["name"] = raw
    return result
