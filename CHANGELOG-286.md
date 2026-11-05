# Changelog — Issue #286

## Téléchargement Rodent IV (Windows) : installation tout-ou-rien, vérifiée dans un dossier temporaire (SEC-025)

`nicsoft/web/server.py` téléchargeait chaque binaire Rodent IV directement
dans `ENGINES_DIR/rodent-iv-win/` avant de vérifier son empreinte SHA-256
(issue #256) : une interruption réseau ou un délai dépassé en cours de
lecture pouvait laisser un fichier tronqué dans le dossier du moteur, et un
échec sur le dernier des trois fichiers laissait les deux premiers en place
sans que rien ne signale l'installation incomplète. Une installation
existante qui fonctionnait pouvait donc être détruite par une tentative de
mise à jour ratée.

- **Téléchargement dans un dossier temporaire** `ENGINES_DIR/rodent-iv-win.tmp`
  (même volume que `rodent-iv-win/`, donc bascule finale atomique) : les
  trois fichiers y sont téléchargés et vérifiés (délai d'attente, empreinte
  SHA-256) avant toute écriture dans le dossier définitif.
- **Mise en place tout-ou-rien** (`_installer_rodent_depuis_temp`) : une fois
  les trois fichiers conformes, le dossier définitif est remplacé en une
  seule opération (`os.replace`, via un dossier `.bak` intermédiaire). Si la
  bascule elle-même échoue (fichier verrouillé parce que le moteur tourne,
  disque plein...), l'ancien dossier est restauré à l'identique et l'erreur
  est propagée — aucune installation existante n'est jamais perdue.
  `_telecharger_fichier_rodent` ne touche donc plus jamais le dossier
  définitif : il écrit uniquement dans le dossier temporaire, ce qui
  supprime du même coup le risque de troncature d'un fichier déjà installé.
- **Nettoyage systématique** du dossier temporaire (`_nettoyer_dossier_temp_rodent`)
  en tout début de tentative (résidu d'un arrêt brutal précédent) et à la
  fin de chaque tentative, succès ou échec — le dossier définitif n'est
  plus créé par avance, et ne reste jamais vide après un échec.
- **Vérification du schéma d'adresse** : `_telecharger_fichier_rodent` refuse
  toute URL qui ne commence pas par `https://`, avant la moindre requête
  réseau, avec le même échec propre (rien n'est installé) que les autres cas
  (empreinte invalide, référence absente). Aucun commentaire `noqa`/`nosec`
  ajouté (consigne projet) — à vérifier si l'outil d'audit de sécurité
  continue malgré tout de signaler cet appel `urlopen`.
- **Logique extraite et testable sans Windows** : `_telecharger_et_installer_rodent`
  orchestre téléchargement + mise en place indépendamment du handler
  SocketIO (`on_download_rodent`), qui ne fait plus que l'appeler et émettre
  les événements de progression/résultat/statut — séquence d'événements
  inchangée en cas de succès.
- **Tests** (`nicsoft/tests/test_rodent.py`, sans réseau ni matériel, tout en
  `tmp_path`, jamais le vrai `ENGINES_DIR`) : succès complet des trois
  fichiers ; empreinte invalide sur le troisième fichier → dossier définitif
  absent ; coupure réseau en cours de lecture du deuxième fichier → aucun
  fichier tronqué ; échec de bascule finale (simulant un fichier verrouillé)
  → ancienne installation restaurée à l'identique ; échec alors qu'une
  installation valide existait → anciens fichiers strictement inchangés ;
  nettoyage d'un dossier temporaire résiduel laissé par un arrêt brutal ;
  URL non-https refusée sans accès réseau.
- `.audit.json` non modifié. Suite de tests complète hors `hardware`
  (`pytest -m "not hardware"`) : 378 passed, 73 skipped (13 nouveaux/révisés
  dans `test_rodent.py`, tous verts).

**Vérification manuelle suggérée sous Windows** (non faisable depuis ce
dépôt Linux) : lancer le téléchargement depuis l'interface, couper le réseau
en cours de route, et constater que `engines/rodent-iv-win/` est strictement
inchangé (aucun fichier tronqué, aucune installation existante perdue).
