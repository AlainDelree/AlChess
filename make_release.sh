#!/usr/bin/env bash
# =============================================================================
#  make_release.sh — Construit des paquets AlChess propres et téléchargeables
#  pour Linux et Windows, à partir du dépôt.
#
#  À exécuter depuis la RACINE du dépôt AlChess :
#      chmod +x make_release.sh
#      ./make_release.sh 1.0.0
#
#  Produit dans ./dist/ :
#      AlChess-v1.0.0-linux-x86_64.zip
#      AlChess-v1.0.0-windows-x86_64.zip
#
#  Principe : LISTE BLANCHE. On copie uniquement ce dont l'utilisateur a
#  besoin ; tout le reste (docs de dev, .claude, .github, logs, png,
#  handoffs, make_release.sh lui-même…) est exclu par construction.
#
#  Le script NE committe rien et NE publie rien : il prépare juste les ZIP.
#  La publication se fait ensuite avec `gh release create` (voir la fin).
# =============================================================================

set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Usage : ./make_release.sh <version>   (ex : ./make_release.sh 1.0.0)"
  exit 1
fi

REPO_ROOT="$(pwd)"
DIST="$REPO_ROOT/dist"
STAGE="$DIST/_stage"
NAME="AlChess-v$VERSION"

if [[ ! -f "$REPO_ROOT/requirements.txt" || ! -d "$REPO_ROOT/nicsoft" ]]; then
  echo "❌ Ce script doit être lancé depuis la racine du dépôt AlChess."
  exit 1
fi

echo "=== Nettoyage de dist/ ==="
rm -rf "$DIST"
mkdir -p "$STAGE"

# -----------------------------------------------------------------------------
#  1) LISTE BLANCHE : uniquement les éléments nécessaires au fonctionnement.
# -----------------------------------------------------------------------------
echo "=== Copie des fichiers nécessaires (liste blanche) ==="
INCLUDE=(
  nicsoft
  engines
  INSTALLATION
  requirements.txt
  README.md
  LICENSE
  install.sh
  start_alchess.sh
  installer.bat
  install_alchess.ps1
  start_alchess.ps1
  99-chessnutair.rules.example
)

for item in "${INCLUDE[@]}"; do
  if [[ -e "$REPO_ROOT/$item" ]]; then
    rsync -a \
      --exclude '.git/' --exclude '.pytest_cache/' \
      --exclude '.mypy_cache/' --exclude '.ruff_cache/' \
      --exclude '__pycache__/' \
      --exclude '*.pyc' --exclude '*.pyo' --exclude '*.so' \
      --exclude '*.log' \
      "$REPO_ROOT/$item" "$STAGE/"
    echo "  ✓ $item"
  else
    echo "  ⚠️  Introuvable (ignoré) : $item"
  fi
done

# Retirer les tests unitaires (inutiles pour l'utilisateur final)
rm -rf "$STAGE/nicsoft/tests"

# Rodent IV inclus dans le ZIP standard depuis v1.1 (binaires Linux + Windows
# validés, issue #12/#13). Les sous-dossiers non-livrables (mac/, sources/, .git)
# sont élagués ci-dessous.
# Élagage du paquet Rodent : on ne livre pas le binaire macOS, le code source C++,
# les outils de dev ni le dépôt git imbriqué.
rm -rf "$STAGE/engines/rodent-iv/mac" \
       "$STAGE/engines/rodent-iv/sources" \
       "$STAGE/engines/rodent-iv/tools" \
       "$STAGE/engines/rodent-iv/.git"

# Binaire Windows de Rodent IV.
# Il vit dans engines/rodent-iv/win/ (tracké par git : rodent-iv-x64.exe +
# msvcp120.dll + msvcr120.dll — build reproductible sur clone frais). Or
# find_rodent() (nicsoft/engine/engine_manager.py) attend un unique
# engines/rodent-iv/rodentIV.exe. On unifie donc la structure AU MOMENT DU
# PACKAGING seulement : on copie le .exe 64 bits sous le nom rodentIV.exe + ses
# DLL runtime dans engines/rodent-iv/, à côté du binaire Linux rodentIV.
# → Aucun fichier n'est renommé/déplacé dans le dépôt git ; tout se passe dans
#   le staging. build_linux et build_windows retirent ensuite le binaire de
#   l'autre OS (le .exe + DLL côté Linux, l'ELF côté Windows).
RODENT_WIN_SRC="$REPO_ROOT/engines/rodent-iv/win"
if [[ -f "$RODENT_WIN_SRC/rodent-iv-x64.exe" ]]; then
  cp "$RODENT_WIN_SRC/rodent-iv-x64.exe" "$STAGE/engines/rodent-iv/rodentIV.exe"
  cp "$RODENT_WIN_SRC/msvcp120.dll" "$RODENT_WIN_SRC/msvcr120.dll" \
     "$STAGE/engines/rodent-iv/"
  echo "  ✓ Rodent Windows : rodentIV.exe + DLL copiés dans engines/rodent-iv/"
else
  echo "  ⚠️  $RODENT_WIN_SRC/rodent-iv-x64.exe introuvable — ZIP Windows SANS Rodent"
fi
# Le sous-dossier win/ (tracké) a été rsyncé dans le staging : ses fichiers ont
# déjà été copiés/renommés en rodentIV.exe + DLL au niveau supérieur ci-dessus.
# On le supprime du staging pour ne pas livrer une seconde copie redondante des
# binaires Windows dans les ZIP.
rm -rf "$STAGE/engines/rodent-iv/win"

# Dossier de sauvegarde des parties : présent mais VIDE (aucune donnée perso)
mkdir -p "$STAGE/games"
find "$STAGE/games" -mindepth 1 -delete 2>/dev/null || true

# -----------------------------------------------------------------------------
#  2) Paquet Linux : garde les binaires Linux, retire ceux de Windows
# -----------------------------------------------------------------------------
build_linux() {
  local out="$DIST/$NAME-linux-x86_64"
  echo "=== Construction du paquet Linux ==="
  rsync -a "$STAGE"/ "$out"/
  rm -f "$out/installer.bat" "$out/install_alchess.ps1" "$out/start_alchess.ps1"
  rm -f "$out/engines/maia/lc0.exe" "$out/engines/rodent-iv/rodentIV.exe"
  rm -f "$out"/engines/maia/*.dll
  rm -f "$out"/engines/rodent-iv/*.dll
  ( cd "$DIST" && zip -qr "$NAME-linux-x86_64.zip" "$NAME-linux-x86_64" )
  rm -rf "$out"
  validate "$DIST/$NAME-linux-x86_64.zip" "linux"
}

# -----------------------------------------------------------------------------
#  3) Paquet Windows : garde les binaires Windows, retire ceux de Linux (ELF)
# -----------------------------------------------------------------------------
build_windows() {
  local out="$DIST/$NAME-windows-x86_64"
  echo "=== Construction du paquet Windows ==="
  rsync -a "$STAGE"/ "$out"/
  rm -f "$out/install.sh" "$out/start_alchess.sh" "$out/99-chessnutair.rules.example"
  rm -f "$out/engines/maia/lc0" "$out/engines/rodent-iv/rodentIV"
  ( cd "$DIST" && zip -qr "$NAME-windows-x86_64.zip" "$NAME-windows-x86_64" )
  rm -rf "$out"
  validate "$DIST/$NAME-windows-x86_64.zip" "windows"
}

# -----------------------------------------------------------------------------
#  4) Validation : signale ce qui manque pour un paquet réellement fonctionnel
# -----------------------------------------------------------------------------
validate() {
  local zipfile="$1" os="$2"
  echo "----- Vérification : $(basename "$zipfile") -----"
  local list; list="$(unzip -Z1 "$zipfile")"
  # NB : on utilise des here-strings (<<<) et non un tube « echo | grep ».
  # Un tube + grep -q + pipefail peut renvoyer un faux négatif (SIGPIPE sur echo
  # quand grep sort tôt) → verdict non déterministe. Le here-string l'évite.

  grep -qE "nicsoft/web/__main__\.py" <<<"$list" \
    && echo "  ✅ Point d'entrée nicsoft.web présent" \
    || echo "  ❌ Point d'entrée nicsoft.web ABSENT"

  grep -qE "engines/maia/maia-1500\.pb\.gz" <<<"$list" \
    && echo "  ✅ Poids Maia présents" \
    || echo "  ⚠️  Poids Maia absents"

  if [[ "$os" == "linux" ]]; then
    grep -qE "engines/maia/lc0$" <<<"$list" \
      && echo "  ✅ Binaire lc0 (Linux) présent" \
      || echo "  ⚠️  lc0 (Linux) absent"
    grep -qiE "engines/rodent.*/rodentIV$" <<<"$list" \
      && echo "  ✅ Binaire Rodent (Linux) présent" \
      || echo "  ⚠️  Rodent (Linux) absent"
  else
    grep -qiE "lc0\.exe" <<<"$list" \
      && echo "  ✅ lc0.exe (Windows) présent" \
      || echo "  ⚠️  lc0.exe (Windows) ABSENT — à ajouter (Round 2)"
    grep -qiE "rodentIV\.exe" <<<"$list" \
      && echo "  ✅ Rodent (Windows) présent" \
      || echo "  ⚠️  Rodent (Windows) absent"
  fi

  # Détection d'intrus : uniquement ce qui peut se faufiler via un sous-dossier
  # d'un élément inclus (dépôts git imbriqués, caches). Les fichiers de dev de
  # la racine sont déjà écartés par la liste blanche.
  local junk
  junk="$(grep -iE '(^|/)(\.git/|\.pytest_cache|\.mypy_cache|\.ruff_cache|__pycache__)|\.pyc$' <<<"$list" || true)"
  if [[ -n "$junk" ]]; then
    echo "  ❌ INTRUS détectés dans le paquet :"
    sed 's/^/       /' <<<"$junk"
  else
    echo "  ✅ Paquet propre (aucun fichier de dev détecté)"
  fi

  echo "  ℹ️  Taille : $(du -h "$zipfile" | cut -f1)"
}

build_linux
build_windows

echo ""
echo "=== Terminé. Paquets dans : $DIST ==="
ls -1 "$DIST"/*.zip
echo ""
echo "Pour publier ensuite la release sur GitHub (après avoir créé un tag) :"
echo ""
echo "  git tag v$VERSION && git push origin v$VERSION"
echo "  gh release create v$VERSION \\"
echo "     dist/$NAME-linux-x86_64.zip \\"
echo "     dist/$NAME-windows-x86_64.zip \\"
echo "     --title \"AlChess v$VERSION\" \\"
echo "     --notes \"Première version téléchargeable. Voir le README pour l'installation.\""
