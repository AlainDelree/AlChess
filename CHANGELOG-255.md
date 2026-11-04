# Changelog — Issue #255

## Dépendances : correctifs de sécurité, épinglage des versions flottantes, retrait de berserk

Audit `requirements.txt` : 4 paquets en retard de correctifs de sécurité
(SEC-001), 2 non épinglés (EXP-001), et `berserk` déclaré mais jamais
importé (reste de NicLink).

- **Correctifs de sécurité** (`pip-audit` : 11 vulnérabilités → 0) :
  - `setuptools` 69.1.1 → 84.1.0 (PYSEC-2025-49, PYSEC-2026-1918,
    PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w)
  - `wheel` 0.42.0 → 0.46.2 (CVE-2026-24049)
  - `python-socketio` 5.16.1 → 5.16.2 (PYSEC-2026-3042)
  - `Werkzeug` 3.1.7 → 3.1.9 (PYSEC-2026-4312)
- **Épinglage** des versions flottantes, sur la version installée/testée :
  - `numpy` `>=1.26.4` → `==2.5.4`
  - `edge-tts` `>=6.1.0` → `==7.3.1`
- **Retrait de `berserk`** (`requirements.txt` + tableau d'inventaire
  `ETAT_PROJET.md`) : aucun import dans le code, aucune référence dans les
  scripts d'installation (`1-Installer.bat`, `bootstrap_linux.sh`) ni
  l'installeur Windows.

Aucun conflit de compatibilité : `pip check` propre avec Flask 3.1.3 et
Flask-SocketIO 5.6.1 après les 4 montées de version. Suite de tests
complète (hors marqueur `hardware`) : 75 passed, 4 skipped.

`ETAT_PROJET.md` mis à jour en cohérence (tableau §5, versions
`python-socketio`/`Werkzeug`/`numpy`, ligne `berserk` supprimée).
