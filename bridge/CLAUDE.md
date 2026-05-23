# Bridge Protocol — Communication inter-agents

Ce dossier sert de documentation au protocole de communication entre l'agent Linux et l'agent Windows via les GitHub Issues du repo AlChess.

## Rôles
- **Agent Linux** : machine de développement principale (Ubuntu), gère le backend NicLink/AlChess
- **Agent Windows** : VM Windows, gère les tests et l'installateur Windows

## Protocole

### Créer une tâche pour l'autre agent
```bash
gh issue create \
  --repo AlainDelree/AlChess \
  --title "TITRE COURT ET CLAIR" \
  --body "## Contexte\n\n## Tâche demandée\n\n## Résultat attendu" \
  --label "bridge,for-windows"   # ou for-linux selon la cible
```

### Lire ses tâches en attente
```bash
# Agent Linux lit ses tâches
gh issue list --repo AlainDelree/AlChess --label "bridge,for-linux"

# Agent Windows lit ses tâches
gh issue list --repo AlainDelree/AlChess --label "bridge,for-windows"
```

### Clore une tâche traitée
```bash
gh issue close NUMERO --repo AlainDelree/AlChess --label "done" --comment "Résultat : ..."
```

## Règles
- Toujours mettre le label `bridge` + `for-linux` ou `for-windows`
- Un issue = une tâche atomique
- Commenter le résultat avant de clore
- Ne jamais modifier le code AlChess directement depuis ce protocole sans approbation humaine
