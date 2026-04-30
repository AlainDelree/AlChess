import json
import pathlib
import subprocess
import sys

CONFIG_FILE = pathlib.Path.home() / "NicLink" / "data" / "config.json"
DEFAULT_CONFIG = {
    "turn_signal": "both",
    "stockfish_level": 5,
    "game_type": "serieuse",
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(config: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def run_module(module_name):
    try:
        subprocess.run([sys.executable, "-m", module_name])
    except KeyboardInterrupt:
        pass

def menu_parametres():
    """Menu de configuration des paramètres par défaut."""
    config = load_config()

    while True:
        print()
        print("=== Paramètres ===")

        # Signaux
        sig_labels = {
            "both": "Bip + LEDs",
            "beep": "Bip seulement",
            "leds": "LEDs seulement",
            "none": "Aucun signal",
        }
        sig_actuel = sig_labels.get(config.get("turn_signal", "both"), "Bip + LEDs")
        print(f"1. Signaux de tour        : {sig_actuel}")

        # Niveau Stockfish
        print(f"2. Niveau Stockfish       : {config.get('stockfish_level', 5)}/20")

        # Type de partie par défaut
        print(f"3. Type de partie défaut  : {config.get('game_type', 'serieuse')}")
        
        #Intensité reaction partie Pédagogique
        print(f"4. Feedback pédagogique   : {config.get('pedagogique_pause', 'blunder')}")

        print("R. Retour au menu principal")
        print()

        try:
            choice = input("Votre choix : ").strip().lower()
        except KeyboardInterrupt:
            break

        if choice == "1":
            print()
            print("  Signaux de début de tour :")
            print("  1. Bip + LEDs")
            print("  2. Bip seulement")
            print("  3. LEDs seulement")
            print("  4. Aucun signal")
            try:
                raw = input("  Choix [1-4] : ").strip()
            except KeyboardInterrupt:
                continue
            mapping = {"1": "both", "2": "beep", "3": "leds", "4": "none"}
            if raw in mapping:
                config["turn_signal"] = mapping[raw]
                save_config(config)
                print(f"  ✓ Signaux mis à jour : {sig_labels[mapping[raw]]}")
            else:
                print("  Choix invalide.")

        elif choice == "2":
            print()
            try:
                raw = input(f"  Niveau Stockfish [1-20, actuel={config.get('stockfish_level', 5)}] : ").strip()
            except KeyboardInterrupt:
                continue
            if raw.isdigit() and 1 <= int(raw) <= 20:
                config["stockfish_level"] = int(raw)
                save_config(config)
                print(f"  ✓ Niveau mis à jour : {raw}")
            elif raw == "":
                pass
            else:
                print("  Valeur invalide (1-20).")

        elif choice == "3":
            print()
            print("  Type de partie par défaut :")
            print("  1. serieuse")
            print("  2. pedagogique")
            print("  3. amusement")
            try:
                raw = input("  Choix [1-3] : ").strip()
            except KeyboardInterrupt:
                continue
            mapping = {"1": "serieuse", "2": "pedagogique", "3": "amusement"}
            if raw in mapping:
                config["game_type"] = mapping[raw]
                save_config(config)
                print(f"  ✓ Type mis à jour : {mapping[raw]}")
            else:
                print("  Choix invalide.")
        elif choice == "4":
            print()
            print("  Feedback pédagogique :")
            print("  1. Pause pour tout")
            print("  2. Pause erreur + blunder")
            print("  3. Pause blunder seulement")
            print("  4. Jamais de pause")
            try:
                raw = input("  Choix [1-4] : ").strip()
            except KeyboardInterrupt:
                continue
            mapping = {"1": "toujours", "2": "erreur", "3": "blunder", "4": "jamais"}
            if raw in mapping:
                config["pedagogique_pause"] = mapping[raw]
                save_config(config)
                print(f"  ✓ Feedback mis à jour : {mapping[raw]}")
            else:
                print("  Choix invalide.")
        elif choice in ("r", "retour"):
            break
        else:
            print("Choix invalide.")


def main():
    try:
        while True:
            config = load_config()
            print()
            print("=== NicLink Chess ===")
            print("1. Humain vs Humain")
            print("2. Humain vs Ordinateur")
            print("3. Mode Pédagogique")
            print("4. Paramètres")
            print("Q. Quitter")
            
            print()

            # Afficher les paramètres actifs en résumé
            sig_labels = {
                "both": "Bip+LEDs", "beep": "Bip",
                "leds": "LEDs", "none": "Aucun",
            }
            sig = sig_labels.get(config.get("turn_signal", "both"), "Bip+LEDs")
            lvl = config.get("stockfish_level", 5)
            print(f"  [Signaux: {sig} | Niveau Stockfish: {lvl}]")

            try:
                choice = input("Votre choix : ").strip().lower()
            except KeyboardInterrupt:
                print("\nAu revoir 👋")
                break

            if choice == "1":
                run_module("nicsoft.play_human")
            elif choice == "2":
                run_module("nicsoft.play_stockfish")
            elif choice == "3":
                run_module("nicsoft.play_pedagogique")        
            elif choice == "4":
                menu_parametres()    
            elif choice in ("q", "quit", "quitter"):
                print("Au revoir 👋")
                break
            else:
                print("Choix invalide.")

    except Exception as e:
        print(f"\nErreur inattendue dans le menu : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
