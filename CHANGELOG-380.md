# Changelog — Issue #380

## Tests : accélération de test_issue320_single_instance.py et garde-fou global de parité i18n

Suite de l'étude #379 : `test_issue320_single_instance.py` pesait ~95 s sur ~217 s de suite complète (`-m "not hardware"`).

### Cause réelle trouvée (pas un délai produit)

Les ~20 tests qui spawnent un faux processus (`_spawn_fake_process`) ne faisaient jamais de `proc.wait()`/`proc.poll()` après l'avoir terminé par PID. Sans parent qui le "réclame", l'enfant tué restait **zombie** : `os.kill(pid, 0)` (utilisé par `_pid_alive`, test et produit) le voyait encore comme "vivant" pendant toute la durée du délai d'attente. Deux conséquences mesurées :
- `_cleanup_pid` (helper de test) attendait les 5 s pleines avant de renoncer, à chaque test.
- Pour le seul test qui appelle le vrai `single_instance._terminate_pid` (code produit, `_GRACEFUL_WAIT_S = 5.0`, non touché), le même effet zombie lui faisait aussi consommer le plein délai de grâce.

Mesure du délai réel de terminaison (SIGTERM → mort effective, avec reaper) sur 10 répétitions : 0,6 à 1,5 ms, max 1,53 ms. Le délai de 5 s n'avait donc jamais de rapport avec le temps réel d'arrêt d'un processus.

### Correctif (test seulement, aucun code produit touché)

- `nicsoft/tests/test_issue320_single_instance.py` :
  - `_spawn_fake_process` : démarre désormais un thread démon `threading.Thread(target=proc.wait, daemon=True)` juste après `Popen()` — reproduit ce que ferait un vrai parent (shell, systemd), qui réclame l'enfant dès sa mort réelle au lieu de le laisser zombie.
  - `_cleanup_pid` : délai de sécurité réduit de `5.0` à `2.0` s (marge >1000x sur les ~1,5 ms mesurées), avec commentaire expliquant pourquoi ce n'est plus un délai critique.
  - Aucun autre délai, assertion ou logique de test modifié.

### Vérification rouge/vert (copie jetable, jamais le code réel)

Casse simulée par monkeypatch en mémoire via un plugin pytest jetable (`/tmp/issue380_break_plugin.py`, jamais dans le dépôt), trois modes, chacun confirmé ROUGE puis revérifié VERT après retrait du plugin :

1. `_is_alchess_process` forcé à toujours renvoyer `True` → ROUGE sur `test_pid_reutilise_par_programme_etranger_non_touche` et `test_is_alchess_process_faux_pour_programme_etranger` (2 échecs).
2. `resolve_startup` cassé pour ignorer `BUSY_STATES` et le cas "état impossible à confirmer" (procède toujours à l'arrêt) → ROUGE sur `test_ancienne_instance_en_partie_refusee`, les 9 `test_tous_les_etats_de_partie_refusent[*]` et `test_etat_impossible_a_confirmer_refuse_par_precaution` (11 échecs).
3. `_skip_check` forcé à toujours renvoyer `False` → ROUGE sur `test_skip_single_instance_ignore_le_marqueur_reel[menu/playing]` et `test_skip_single_instance_write_remove_marker_sont_des_no_op` (3 échecs).

Chaque mode retiré → suite à nouveau verte (26/26). Les tests négatifs conservent donc bien leur valeur de garde.

### Durées mesurées (poste de dev, 24/11/2026)

| Mesure | Avant | Après |
|---|---|---|
| `test_issue320_single_instance.py` seul | 97,43 s (26 tests) | 14,0–14,5 s (normal), 16,7–19,0 s (sous charge CPU) |
| Suite complète `-m "not hardware"` | 216,88 s (1785 passed, 86 skipped, 1 deselected) | 127,7–133,9 s (1788 passed, 86 skipped, 1 deselected) |

Objectif "30 s ou moins" atteint avec large marge (14,5 s en pointe normale), y compris sous charge CPU.

10 exécutions consécutives de `test_issue320_single_instance.py` sans aucun échec, dont les 3 dernières avec 6 processus de calcul intensif tournant en continu (charge CPU, machine 8 cœurs) — pas d'intermittence observée.

Suite complète verte deux fois de suite après correctif (1788 passed les deux fois, 127,74 s et 133,90 s).

### Garde-fou global de parité i18n (nouveau fichier)

- `nicsoft/tests/test_issue380_i18n_global_parity.py` (nouveau) : indépendant de toute issue ponctuelle, compare l'intégralité des ~861 clés de `fr.json`/`en.json`/`de.json` (pas seulement celles propres à une issue) et vérifie qu'aucune valeur n'est vide. Aucun test de parité existant supprimé ni modifié (ceux dispersés sur ~14 fichiers restent en place).
- Vérification rouge/vert faite sur une copie jetable dans `/tmp` (jamais les vrais fichiers) : une clé retirée d'un seul fichier, ou une valeur vidée dans un seul fichier, fait échouer le test correspondant ; remis en l'état d'origine, les deux tests repassent au vert.
- Aucune asymétrie réelle trouvée entre les trois fichiers actuels (861 clés identiques, aucune valeur vide) : rien à corriger côté traductions.
- +3 tests collectés au total par ce nouveau fichier : 2 tests propres, plus 1 nouvelle instance paramétrée du garde existant `test_issue296_security_suppressions.py::test_suppressions_securite_bien_formees` (itère automatiquement sur tous les fichiers de test).

### Contraintes respectées

- Aucun fichier produit, `configs/*.conf`, `.audit.json`, `driver.py` ni `TACHES.md` touché.
- Aucune dépendance installée (pytest-xdist non utilisé).
- Arrêts de processus toujours par PID exact (faux processus de test, processus de charge CPU du test de robustesse).
- `CONTEXTE.md` inchangé (3535 caractères) : correctif purement interne aux tests, aucune règle/architecture modifiée.
