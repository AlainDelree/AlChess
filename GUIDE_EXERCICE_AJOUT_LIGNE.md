# 📖 Guide — Ajouter ses propres lignes d'ouverture dans NicLink

## Vue d'ensemble

Le module **Mes lignes** permet d'importer vos propres lignes d'ouverture
au format PGN et de les entraîner directement dans NicLink, comme les
ouvertures du catalogue.

---

## Étape 1 — Créer un fichier PGN

Chaque ligne est un fichier `.pgn` séparé, organisé en sous-dossiers
dans :

```
~/NicLink/data/mes_lignes/
├── Chigorine/
│   ├── Chigorine1.pgn
│   ├── Chigorine2.pgn
│   └── Chigorine3.pgn
├── Sicilienne/
│   └── najdorf_principale.pgn
└── ...
```

Le programme parcourt tous les sous-dossiers automatiquement.

### Format du fichier

```pgn
[Event "Chigorine — Ligne 1"]
[CampSuggere "black"]
[InitMoves "d2d4 d7d5 c2c4"]

1. d4 d5 2. c4 Nc6 3. cxd5 Qxd5 4. Nc3 Qa5
```

### Explication des headers

| Header | Obligatoire | Description |
|--------|-------------|-------------|
| `[Event "..."]` | Non | Nom affiché dans l'interface |
| `[CampSuggere "..."]` | Non | `white` ou `black` (défaut : `white`) |
| `[InitMoves "..."]` | Non | Coups déjà joués au démarrage (en UCI) |
| `[ECO "..."]` | Non | Code ECO optionnel (ex: `D06`) |

### Le header `[InitMoves]`

Ce header définit la **position de départ** — les coups déjà joués sur
l'échiquier quand la session commence. Les coups doivent être en notation
**UCI** (case départ + case arrivée).

**Exemple :** `[InitMoves "d2d4 d7d5 c2c4"]` → la session commence
après 1.d4 d5 2.c4, et vous devez jouer à partir de là.

Sans ce header, la session commence depuis la position initiale et
tous les coups du PGN font partie de la ligne.

### Les coups du PGN

Les coups sont en notation **SAN anglaise** :

| Pièce | Lettre |
|-------|--------|
| Roi   | `K` |
| Dame  | `Q` |
| Tour  | `R` |
| Fou   | `B` |
| Cavalier | `N` |
| Pion  | (rien) |

⚠️ **Pas de notation française** (`D`, `F`, `C`, `T`, `R`) — utilisez
les lettres anglaises.

**Exemples de coups valides :**
```
1. d4 d5 2. c4 Nc6 3. cxd5 Qxd5 4. Nc3 Qa5
```

---

## Étape 2 — Trouver les coups UCI pour `[InitMoves]`

Si vous ne connaissez pas la notation UCI, utilisez l'option 7 du gestionnaire :

```bash
python -m nicsoft.exercices.manage
```

Choisissez **option 7 — Convertir SAN → UCI**, collez votre ligne PGN,
et appuyez sur Entrée deux fois. Le programme affiche chaque coup avec
sa traduction UCI :

```
  d4          → d2d4
  d5          → d7d5
  c4          → c2c4
  Nc6         → b8c6
  cxd5        → c4d5
  ...

InitMoves complet : "d2d4 d7d5 c2c4 b8c6 c4d5 ..."
```

Copiez la portion qui vous intéresse dans `[InitMoves]`.

---

## Étape 3 — Importer les fichiers

```bash
python -m nicsoft.exercices.manage
```

Choisissez **option 6 — Importer mes lignes PGN**.

Le programme parcourt tous les fichiers `.pgn` du dossier et génère
`~/NicLink/data/mes_lignes.json`.

```
  ✓ Chigorine1.pgn — Chigorine — Ligne 1 (5 coups, init=3, black)
  ✓ Chigorine2.pgn — Chigorine — Ligne 2 (6 coups, init=3, black)

✓ 2 ligne(s) importée(s)
```

---

## Étape 4 — Utiliser dans NicLink

1. Lancez NicLink : `python -m nicsoft.web`
2. Menu → **Exercices**
3. Cliquez sur l'onglet **★ Mes lignes**
4. Choisissez votre ligne et cliquez **♔ Blancs** ou **♚ Noirs**

---

## Mettre à jour une ligne

Modifiez le fichier `.pgn`, relancez l'option 6 du manage, puis
relancez NicLink.

---

## Conseils pratiques

**Nommage des fichiers :** utilisez des noms descriptifs, ils servent
d'identifiant interne si le header `[Event]` est absent.

```
ruy_lopez_berlin.pgn
sicilienne_najdorf_ligne_principale.pgn
chigorine_ligne_1.pgn
```

**Un fichier = une ligne.** Si une ouverture a plusieurs variantes,
créez un fichier par variante — c'est plus facile à gérer et à driller
séparément.

**Importer depuis Chess.com ou Lichess :** exportez votre partie en
PGN, copiez la ligne qui vous intéresse dans un fichier, ajoutez les
headers `[CampSuggere]` et `[InitMoves]` si nécessaire, et importez.

---

## Résumé des commandes

```bash
# Ouvrir le gestionnaire
python -m nicsoft.exercices.manage

# Option 6 : importer les PGN
# Option 7 : convertir SAN → UCI

# Dossier des fichiers PGN
~/NicLink/data/mes_lignes/

# Fichier généré
~/NicLink/data/mes_lignes.json
```
