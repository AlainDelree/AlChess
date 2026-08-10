# AlChess — Tâches et bugs

---

## ⚡ Prioritaire

- **Release v1.3.1 à packager** `[Linux/Windows]` — regrouper les correctifs depuis v1.3.0 (dont issue #96) : `./make_release.sh 1.3.1` + tag + `gh release create`.
- **ACTION ALAIN — Validation VM NSIS** `[Windows]` — relancer `AlChess_Setup.exe` sur VM Windows et confirmer l'installation/lancement de bout en bout (issues #64–#67, #58).
- **Tester une partie réelle Rodent sur Windows** `[Windows]` — sur portable physique (jeu + changement d'Elo + redémarrage).
- **Tester vc_redist sur un Windows sans le runtime VC++** `[Windows]` — la VM actuelle a déjà le runtime, il faut un Windows propre.

---

## 🐛 Bugs actifs

### À corriger
- **HH — écran de rangement ignoré si échiquier déconnecté silencieusement** `[Windows]`

### En veille (peu prioritaires)
- **Race condition LEDs** `[Linux]`
- **WAIT_FISH lent intermittent** `[Les deux]`
- **`git submodule update --init` échoue sur clone frais** `[Les deux]`
- **Pédagogique — boucle infinie de double-bip si pièce mal jouée puis corrigée manuellement** `[Linux]`
- **Numéros de lignes échiquier mal alignés (rendu police Windows)** `[Windows]`

---

## 💡 Fonctionnalités à venir

- **Chantier « l'UI reflète l'état réel du système »** `[Les deux]` — reste : déconnexion échiquier en cours de session mal gérée (modes physiques pas grisés).
- **Tutoriels utilisateur** `[Les deux]` — autres aides in-app à ajouter au fil des besoins.
- **Nettoyer le dossier Rodent dans le packaging** — trier par OS (`mac/`, `sources/`, `books/` volumineux inutiles au paquet final).
- **Réduire la taille des ZIP** (~210/215 Mo) — élagage `books/`/`exe/`/`docs/` de Rodent à valider avec Alain.
- **i18n — corrections résiduelles au fil des tests DE** (edge cases, `eco_import.py`).
- **Améliorer la visibilité moteurs de recherche** `[Les deux]` — image de prévisualisation sociale, communautés (r/chess, forums Chessnut).

---

## 🧪 Tests automatisés

- **Niveau 1** — Checklist manuelle : `TESTS.md` (smoke 5 min / régression 20 min)
- **Niveau 2** — `nicsoft/tests/test_app_state.py` (25 tests pytest)
- **Niveau 3** — `nicsoft/tests/e2e/` (42 tests Playwright headless)
- **Mode test aléatoire** — `NICLINK_TEST=random python -m nicsoft.web` + bouton 🎲

---

## 📝 Notes techniques

- **USB Chessnut** : quirk `/etc/modprobe.d/chessnut.conf` — voir `INSTALLATION_ALCHESS.md` section 4b.
- **`retranscription_en_cours`** au démarrage : normal (reprise), ne traiter que sur l'écran Retranscription.
- **Bridge mode écriture** : label GitHub `mode_write` arme l'écriture ; détail dans `BRIDGE_AGENT_DOC.md`.
- **Runtime VC++ (Windows)** : `lc0.exe` (Maia) exige `MSVCP140.dll`, sinon crash `0xC0000135`.
- **VM Windows (VirtualBox)** : `AlChess-Win11`, EFI+TPM 2.0, 6 Go RAM, 2 CPU, compte local (`Maj+F10` → `start ms-cxh:localonly`).
