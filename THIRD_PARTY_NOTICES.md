# Third-Party Notices

**🇬🇧 English** | [🇫🇷 Français](#français)

---

## 🇬🇧 English

AlChess bundles the following third-party components. This file lists their role, the files they occupy, their origin, their version (when known), and their license. Information that could not be established from the official repository or from the file itself is marked **not established** rather than guessed.

| Component | Role | Files | Origin | Version | License |
|---|---|---|---|---|---|
| Leela Chess Zero (lc0) | Maia chess engine (UCI binary) | `engines/maia/lc0` (Linux), `engines/maia/lc0.exe` (Windows) | https://github.com/LeelaChessZero/lc0 | Linux binary: `v0.33.0-dev+git.5d8b306` (read from the `uci`/version banner). Windows binary: `v0.31.2`, built Oct 20 2024 (read from the `uci` banner) | GPL-3.0 |
| Maia Chess weights | Neural-network weight files for the Maia engine (one per strength level) | `engines/maia/maia-1100.pb.gz` … `maia-1900.pb.gz` (9 files) | https://github.com/CSSLab/maia-chess | not established | GPL-3.0 |
| OpenBLAS | Linear-algebra library used by the Windows lc0 build | `engines/maia/libopenblas.dll` | https://github.com/OpenMathLib/OpenBLAS | not established (no version information in the file; PE header only shows a 2018-10-22 build timestamp) | BSD 3-Clause |
| mimalloc | Memory allocator used by the Windows lc0 build | `engines/maia/mimalloc-override.dll`, `engines/maia/mimalloc-redirect.dll` | https://github.com/microsoft/mimalloc | 1.7.1 | MIT |
| Rodent IV | Chess engine (UCI binary) | `engines/rodent-iv-win/rodent-iv-x64.exe` | https://github.com/nescitus/rodent-iv | `Rodent IV 022 64-bit/MSVS2017/POPCNT` (read from the `uci` banner), author Pawel Koziol | GPL-3.0 |
| Microsoft Visual C++ 2013 runtime | C/C++ runtime libraries shipped in the Rodent IV folder (the 64-bit executable itself only imports `kernel32.dll`) | `engines/rodent-iv-win/msvcr120.dll` (64-bit), `engines/rodent-iv-win/msvcp120.dll` (32-bit) | © Microsoft Corporation | `msvcr120.dll` 12.00.21005.1 (64-bit), `msvcp120.dll` 12.00.30501.0 (32-bit), read from the files' version resources | Not a free license — redistributed under Microsoft's redistribution terms for this runtime |
| Socket.IO client | Browser/server WebSocket communication library used by the web interface | `nicsoft/web/static/vendor/socket.io/socket.io.min.js` | https://github.com/socketio/socket.io-client | 4.7.2 (from the file's header comment) | MIT |
| chess.js | Chess rules/move-generation library used by the web interface | `nicsoft/web/static/vendor/chess.js/chess.min.js` | https://github.com/jhlywa/chess.js | not established (no version string in the minified file) | BSD 2-Clause |
| Chess piece set | SVG piece images used by the web interface | `nicsoft/web/static/pieces/*.svg` (12 files) | https://github.com/lichess-org/lila (`public/piece/cburnett/`) | — | Confirmed: the path geometry of all 12 local files is byte-for-byte identical to the "cburnett" set distributed by Lichess, authored by Colin M. L. Burnett. Triple-licensed: GPL v2 or later, BSD, and GFDL. |

For the components above licensed under the GPL (lc0, Maia weights, Rodent IV), the corresponding source code is available at the official repository address listed in the table, and the text of the license is in the [LICENSE](LICENSE) file.

Python packages installed via `pip` (see [requirements.txt](requirements.txt)) keep their own licenses, declared in their respective PyPI packages; they are not reproduced here.

Stockfish (GPL-3.0, https://github.com/official-stockfish/Stockfish) is **not redistributed** with AlChess: it is installed separately by the Windows installer or expected to be present on the system (Linux).

---

<a name="français"></a>
## 🇫🇷 Français

AlChess inclut les composants tiers suivants. Ce fichier liste leur rôle, les fichiers qu'ils occupent, leur origine, leur version (quand elle est connue) et leur licence. Les informations qui n'ont pas pu être établies à partir du dépôt officiel ou du fichier lui-même sont marquées **non établie** plutôt que supposées.

| Composant | Rôle | Fichiers | Origine | Version | Licence |
|---|---|---|---|---|---|
| Leela Chess Zero (lc0) | Moteur d'échecs de Maia (binaire UCI) | `engines/maia/lc0` (Linux), `engines/maia/lc0.exe` (Windows) | https://github.com/LeelaChessZero/lc0 | Binaire Linux : `v0.33.0-dev+git.5d8b306` (lue dans la bannière `uci`/version). Binaire Windows : `v0.31.2`, compilé le 20 oct. 2024 (lue dans la bannière `uci`) | GPL-3.0 |
| Poids Maia Chess | Fichiers de poids du réseau de neurones du moteur Maia (un par niveau de force) | `engines/maia/maia-1100.pb.gz` … `maia-1900.pb.gz` (9 fichiers) | https://github.com/CSSLab/maia-chess | non établie | GPL-3.0 |
| OpenBLAS | Bibliothèque d'algèbre linéaire utilisée par la version Windows de lc0 | `engines/maia/libopenblas.dll` | https://github.com/OpenMathLib/OpenBLAS | non établie (aucune information de version dans le fichier ; l'en-tête PE n'indique qu'une date de compilation, le 22/10/2018) | BSD à trois clauses |
| mimalloc | Allocateur mémoire utilisé par la version Windows de lc0 | `engines/maia/mimalloc-override.dll`, `engines/maia/mimalloc-redirect.dll` | https://github.com/microsoft/mimalloc | 1.7.1 | MIT |
| Rodent IV | Moteur d'échecs (binaire UCI) | `engines/rodent-iv-win/rodent-iv-x64.exe` | https://github.com/nescitus/rodent-iv | `Rodent IV 022 64-bit/MSVS2017/POPCNT` (lue dans la bannière `uci`), auteur Pawel Koziol | GPL-3.0 |
| Runtime Microsoft Visual C++ 2013 | Bibliothèques d'exécution C/C++ fournies dans le dossier de Rodent IV (l'exécutable 64 bits lui-même n'importe que `kernel32.dll`) | `engines/rodent-iv-win/msvcr120.dll` (64 bits), `engines/rodent-iv-win/msvcp120.dll` (32 bits) | © Microsoft Corporation | `msvcr120.dll` 12.00.21005.1 (64 bits), `msvcp120.dll` 12.00.30501.0 (32 bits), lues dans les ressources de version des fichiers | Licence non libre — redistribué selon les conditions de redistribution de Microsoft pour ce runtime |
| Client Socket.IO | Bibliothèque de communication WebSocket navigateur/serveur utilisée par l'interface web | `nicsoft/web/static/vendor/socket.io/socket.io.min.js` | https://github.com/socketio/socket.io-client | 4.7.2 (lue dans le commentaire d'en-tête du fichier) | MIT |
| chess.js | Bibliothèque de règles/génération de coups utilisée par l'interface web | `nicsoft/web/static/vendor/chess.js/chess.min.js` | https://github.com/jhlywa/chess.js | non établie (aucune chaîne de version dans le fichier minifié) | BSD à deux clauses |
| Jeu de pièces | Images SVG des pièces utilisées par l'interface web | `nicsoft/web/static/pieces/*.svg` (12 fichiers) | https://github.com/lichess-org/lila (`public/piece/cburnett/`) | — | Confirmé : la géométrie des tracés des 12 fichiers locaux est identique, trait pour trait, au jeu « cburnett » distribué par Lichess, dessiné par Colin M. L. Burnett. Triple licence : GPL v2 ou ultérieure, BSD, et GFDL. |

Pour les composants ci-dessus sous licence GPL (lc0, poids Maia, Rodent IV), le code source correspondant est disponible à l'adresse du dépôt officiel indiquée dans le tableau, et le texte de la licence se trouve dans le fichier [LICENSE](LICENSE).

Les paquets Python installés via `pip` (voir [requirements.txt](requirements.txt)) conservent leurs propres licences, déclarées dans leurs paquets PyPI respectifs ; elles ne sont pas reproduites ici.

Stockfish (GPL-3.0, https://github.com/official-stockfish/Stockfish) n'est **pas redistribué** avec AlChess : il est installé séparément par l'installateur Windows, ou doit être présent sur le système (Linux).
