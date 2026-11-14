# Changelog — Issue #336

## Tests : rendre fiable le test de reconnaissance d'un processus AlChess par sa ligne de commande

### Cause établie par lecture + essai reproductible

`single_instance._is_alchess_process(pid)` lit `/proc/<pid>/cmdline` juste après avoir reçu un PID de `subprocess.Popen(...)`. Un essai reproductible dédié (boucle Python, `/proc/<pid>/cmdline` lu immédiatement puis à intervalles rapprochés) a établi :

- **Fait établi** : juste après le retour de `Popen()`, une lecture immédiate de `/proc/<pid>/cmdline` renvoie parfois une chaîne **vide** (jamais la ligne de commande du parent — l'hypothèse initiale de l'issue sur « la ligne de commande du processus parent » n'est donc pas confirmée telle quelle, mais le mécanisme général — lecture trop précoce du fichier de description du processus — l'est). Sans charge artificielle, 500 répétitions ont produit 107 lectures vides immédiates sur 500 (plus de 20 %) ; la fenêtre se résorbe normalement en quelques dizaines à centaines de microsecondes (mesuré par échantillonnage rapproché : vide à t=0, peuplé dès t≈65µs). Sous charge CPU/fork concurrente, une seule lecture synchrone juste après le spawn peut retomber dans cette fenêtre avec une fréquence comparable (31/400 observés avec le code d'avant correctif sous charge), ce qui explique l'échec intermittent constaté dans #324/#329/#331.
- **Hypothèse restée hypothèse** : le mécanisme kernel exact de cette fenêtre (ordre d'écriture des `arg_start`/`arg_end` pendant `execve()`) n'a pas été vérifié dans les sources du noyau — seul le comportement observé (vide puis peuplé, jamais autre chose) a été établi par la mesure.
- Le code de production (`single_instance.py`) n'a pas de défaut ici : à l'usage réel, `resolve_startup()` lit ce marqueur un certain temps après le démarrage effectif de l'autre instance (requête HTTP, I/O), largement après la fin de cette fenêtre. Seul le test lit le PID **immédiatement** après le `Popen()` du test lui-même, sans aucune marge. Aucune modification de code de production.

### Correction (test seulement)

`nicsoft/tests/test_issue320_single_instance.py` — `_spawn_fake_process()` attend désormais, de façon bornée (poll 10 ms, limite 5 s, via le `_wait_until` déjà présent dans le fichier), que `single_instance._cmdline_for_pid(pid)` soit non vide avant de rendre le PID à l'appelant ; échec explicite (`AssertionError` avec PID et délai) si la limite est atteinte sans jamais rien de peuplé. Pas de pause fixe arbitraire — la boucle se termine dès que la ligne de commande est disponible (typiquement sous une milliseconde).

### Autres tests semblables corrigés

Tous les appels à `_spawn_fake_process()` du même fichier passent par ce point d'entrée unique, donc bénéficient automatiquement de la même attente bornée — pas de correctif séparé nécessaire :
`test_is_alchess_process_par_cmdline`, `test_is_alchess_process_faux_pour_programme_etranger`, `test_pid_reutilise_par_programme_etranger_non_touche`, `test_ancienne_instance_inactive_remplacee`, `test_ancienne_instance_en_partie_refusee`, `test_tous_les_etats_de_partie_refusent`, `test_etat_impossible_a_confirmer_refuse_par_precaution`, `test_skip_single_instance_ignore_le_marqueur_reel`. Plusieurs de ces tests (ceux qui appellent `resolve_startup()` juste après le spawn, ex. `test_ancienne_instance_inactive_remplacee`) étaient exposés à la même course par un chemin indirect (`resolve_startup()` appelle `_is_alchess_process()` en interne) : corrigés par le même changement.

Recherche élargie (`grep` sur `Popen`/`_pid_alive`/`/proc/` dans tout `nicsoft/`) : aucun autre fichier de test du dépôt ne lance un processus puis lit aussitôt son état — seuls `test_issue312_server_startup.py` et `tests/e2e/conftest.py` utilisent `subprocess.Popen`, mais ils attendent déjà une ligne de sortie du serveur via une boucle bornée (`wait_for_server_url`), pas une lecture immédiate de `/proc`.

### Fiabilité démontrée

Essais menés dans un dossier temporaire du worktree (`.repro_tmp_336/`, supprimé après usage — jamais écrit hors du périmètre) :

- **Avant correctif** (reproduction du code d'origine, sans attente) : 31 échecs sur 400 répétitions sous charge CPU + fork/exec concurrente — confirme la cause.
- **Après correctif**, répété bien au-delà des 200 répétitions demandées, **aucun échec** :
  - 300/300 répétitions via le code corrigé (`_spawn_fake_process` + `_is_alchess_process`) sous charge CPU + fork/exec concurrente artificielle.
  - 250/250 répétitions supplémentaires **pendant l'exécution simultanée, en arrière-plan, de toute la suite de tests du projet** (`pytest nicsoft/tests/ -q -m "not slow"`, 1172 passés) — scénario demandé explicitement par l'issue.
  - 40/40 appels directs au point d'entrée réel du test (`test_is_alchess_process_par_cmdline()`, corps exact, y compris le nettoyage d'origine par PID) sous la même charge.
  - Suite complète du fichier (`pytest nicsoft/tests/test_issue320_single_instance.py -m "not slow"`) : 23 passés, aucun échec, après correctif.
- Aucun processus lancé pendant ces essais n'est resté actif (vérifié par `ps` après coup) ; tout arrêt, dans le test comme dans les essais, s'est fait par le PID exact, jamais par nom.

### Fichiers modifiés

- `nicsoft/tests/test_issue320_single_instance.py` — attente bornée ajoutée dans `_spawn_fake_process()` (+17 lignes, aucune suppression).

Aucune modification de code de production, aucun fichier `.audit.json`, aucune dépendance touchée, aucun moteur exécuté. Serveur de test non démarré pour cette tâche (pas nécessaire — tests unitaires avec faux processus uniquement).
