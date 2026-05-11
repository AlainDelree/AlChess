# AlChess

**🇫🇷 Français** | [🇬🇧 English below](#english)

---

## 🇫🇷 Français

Application d'entraînement aux échecs connectant un échiquier physique **Chessnut Air** à une interface web locale. Jouez contre Stockfish, Maia ou un autre humain — avec votre vrai échiquier.

### Fonctionnalités

- ♟️ **Partie pédagogique** — jouez contre Stockfish avec évaluation et feedback à chaque coup
- 👥 **Humain vs Humain** — deux joueurs sur le même échiquier physique
- 📖 **Exercices d'ouvertures** — entraînement sur des lignes personnalisées ou des livres Polyglot
- 📝 **Retranscription PGN** — rejouez et exportez vos parties
- 🧪 **Mode Labo** — échiquier virtuel sans matériel physique

### Matériel requis

- Échiquier **Chessnut Air** (USB, `idVendor=2d80 idProduct=8003`)
- Ubuntu 22.04 ou 24.04 (x86_64)

> ⚠️ Le Chessnut Air+ a un `idProduct` différent — vérifier avec `lsusb | grep 2d80`.

### Installation

Voir [`INSTALLATION/INSTALLATION_NICLINK.md`](INSTALLATION/INSTALLATION_NICLINK.md) pour le guide complet.

```bash
git clone https://github.com/AlainDelree/AlChess.git ~/AlChess
cd ~/AlChess
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Lancement

```bash
/usr/bin/python3 ~/AlChess/nicsoft/web/launcher.py
```

### Moteurs inclus

| Moteur | Source |
|--------|--------|
| Stockfish | `sudo apt install stockfish` |
| Maia (lc0) | Binaire inclus (x86_64 Linux) |
| Rodent IV | Binaire inclus (x86_64 Linux) |

### Contribuer

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une **Issue** pour signaler un bug ou proposer une fonctionnalité, ou une **Pull Request** pour soumettre du code.

Le projet est en français mais les contributions en anglais sont tout à fait acceptées.

---

<a name="english"></a>
## 🇬🇧 English

A chess training application connecting a **Chessnut Air** physical chessboard to a local web interface. Play against Stockfish, Maia, or another human — on your real board.

### Features

- ♟️ **Pedagogical mode** — play against Stockfish with per-move evaluation and feedback
- 👥 **Human vs Human** — two players on the same physical board
- 📖 **Opening exercises** — train on custom lines or Polyglot opening books
- 📝 **PGN retranscription** — replay and export your games
- 🧪 **Lab mode** — virtual board without physical hardware

### Hardware required

- **Chessnut Air** chessboard (USB, `idVendor=2d80 idProduct=8003`)
- Ubuntu 22.04 or 24.04 (x86_64)

> ⚠️ The Chessnut Air+ has a different `idProduct` — check with `lsusb | grep 2d80`.

### Installation

See [`INSTALLATION/INSTALLATION_NICLINK.md`](INSTALLATION/INSTALLATION_NICLINK.md) for the full guide.

```bash
git clone https://github.com/AlainDelree/AlChess.git ~/AlChess
cd ~/AlChess
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Launch

```bash
/usr/bin/python3 ~/AlChess/nicsoft/web/launcher.py
```

### Engines

| Engine | Source |
|--------|--------|
| Stockfish | `sudo apt install stockfish` |
| Maia (lc0) | Binary included (x86_64 Linux) |
| Rodent IV | Binary included (x86_64 Linux) |

> ⚠️ The Rust driver `_niclink.so` is not included in the repo — it must be compiled from sources in `nicsoft/niclink/src/` or copied from a working machine. See the installation guide.

### Contributing

Contributions are welcome! Feel free to open an **Issue** to report a bug or suggest a feature, or a **Pull Request** to submit code.

The project interface is currently in French — an English translation is planned. Contributions in English are fully accepted.

### License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
