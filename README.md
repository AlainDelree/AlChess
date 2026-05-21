# AlChess

**🇫🇷 Français** | [🇬🇧 English below](#english)

---

## 🇫🇷 Français

Application d'entraînement aux échecs connectant un échiquier physique **Chessnut Air** à une interface web locale. Jouez contre Stockfish, Maia ou un autre humain — avec votre vrai échiquier.

### Fonctionnalités

- ♟️ **Partie pédagogique** — jouez contre Stockfish avec évaluation et feedback à chaque coup
- 👥 **Humain vs Humain** — deux joueurs sur le même échiquier physique
- 📖 **Exercices d'ouvertures** — entraînement sur des lignes personnalisées ou des livres Polyglot
- 🔍 **Analyse de partie** — navigation coup par coup, import de PGN externes (ex: Chess.com)
- 📝 **Retranscription PGN** — rejouez et exportez vos parties
- 🧪 **Mode Labo** — échiquier virtuel sans matériel physique
- 🌐 **Interface multilingue** — français, anglais et allemand (🇫🇷 🇬🇧 🇩🇪)

> ℹ️ Tous les modes (sauf Humain vs Humain) fonctionnent sans échiquier physique grâce à un échiquier virtuel intégré.

### Systèmes supportés

| Système | Support |
|---------|---------|
| Ubuntu 22.04 / 24.04 (x86_64) | ✅ Complet |
| Windows 10 / 11 (x86_64) | ✅ Complet |

> ⚠️ Le Chessnut Air+ a un `idProduct` différent du Chessnut Air — vérifier avec `lsusb | grep 2d80` (Linux) ou le Gestionnaire de périphériques (Windows).

### Installation — Windows

1. Téléchargez le dépôt : bouton **Code → Download ZIP** sur GitHub, puis extrayez
2. Double-cliquez sur **`installer.bat`**
3. Le script installe Python 3.12 si nécessaire, crée l'environnement virtuel et installe les dépendances
4. Répondez **O** pour télécharger Stockfish automatiquement (ou **N** pour le placer manuellement dans `engines\`)
5. Lancez AlChess en double-cliquant sur **`start_alchess.ps1`**

> ℹ️ L'interface s'ouvre dans votre navigateur. Ne fermez pas la fenêtre PowerShell pendant l'utilisation.

### Installation — Linux (Ubuntu)

Voir [`INSTALLATION/INSTALLATION_NICLINK.md`](INSTALLATION/INSTALLATION_NICLINK.md) pour le guide complet.

```bash
git clone https://github.com/AlainDelree/AlChess.git ~/AlChess
cd ~/AlChess
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Lancement — Linux

```bash
cd ~/AlChess && source venv/bin/activate && python -m nicsoft.web
```

### Moteurs inclus

| Moteur | Linux | Windows |
|--------|-------|---------|
| Stockfish | `sudo apt install stockfish` | Téléchargé par `installer.bat` |
| Maia (lc0) | Binaire inclus (x86_64) | Binaire inclus (x86_64) |
| Rodent IV | Binaire inclus (x86_64) | Binaire inclus (x86_64) |

### Contribuer

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une **Issue** pour signaler un bug ou proposer une fonctionnalité, ou une **Pull Request** pour soumettre du code.

L'interface est disponible en français, anglais et allemand. Les contributions dans ces langues sont les bienvenues.

---

<a name="english"></a>
## 🇬🇧 English

A chess training application connecting a **Chessnut Air** physical chessboard to a local web interface. Play against Stockfish, Maia, or another human — on your real board.

### Features

- ♟️ **Pedagogical mode** — play against Stockfish with per-move evaluation and feedback
- 👥 **Human vs Human** — two players on the same physical board
- 📖 **Opening exercises** — train on custom lines or Polyglot opening books
- 🔍 **Game analysis** — move-by-move navigation, import external PGN files (e.g. from Chess.com)
- 📝 **PGN retranscription** — replay and export your games
- 🧪 **Lab mode** — virtual board without physical hardware
- 🌐 **Multilingual interface** — French, English and German (🇫🇷 🇬🇧 🇩🇪)

> ℹ️ All modes (except Human vs Human) work without a physical board thanks to a built-in virtual chessboard.

### Supported systems

| System | Support |
|--------|---------|
| Ubuntu 22.04 / 24.04 (x86_64) | ✅ Full |
| Windows 10 / 11 (x86_64) | ✅ Full |

> ⚠️ The Chessnut Air+ has a different `idProduct` from the Chessnut Air — check with `lsusb | grep 2d80` (Linux) or Device Manager (Windows).

### Installation — Windows

1. Download the repo: click **Code → Download ZIP** on GitHub, then extract
2. Double-click **`installer.bat`**
3. The script installs Python 3.12 if needed, creates the virtual environment and installs dependencies
4. Answer **Y** to download Stockfish automatically (or **N** to place it manually in `engines\`)
5. Launch AlChess by double-clicking **`start_alchess.ps1`**

> ℹ️ The interface opens in your browser. Do not close the PowerShell window while using the app.

### Installation — Linux (Ubuntu)

See [`INSTALLATION/INSTALLATION_NICLINK.md`](INSTALLATION/INSTALLATION_NICLINK.md) for the full guide.

```bash
git clone https://github.com/AlainDelree/AlChess.git ~/AlChess
cd ~/AlChess
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Launch — Linux

```bash
cd ~/AlChess && source venv/bin/activate && python -m nicsoft.web
```

### Engines

| Engine | Linux | Windows |
|--------|-------|---------|
| Stockfish | `sudo apt install stockfish` | Downloaded by `installer.bat` |
| Maia (lc0) | Binary included (x86_64) | Binary included (x86_64) |
| Rodent IV | Binary included (x86_64) | Binary included (x86_64) |

### Contributing

Contributions are welcome! Feel free to open an **Issue** to report a bug or suggest a feature, or a **Pull Request** to submit code.

The interface is available in French, English and German. Contributions in these languages are welcome.

### License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
