#Requires -Version 5.1
<#
.SYNOPSIS
    Installateur AlChess pour Windows 10+
.DESCRIPTION
    Installe Python 3.12, crée le venv, installe les dépendances,
    et propose de télécharger Stockfish.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$STOCKFISH_URL = "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-avx2.zip"
$STOCKFISH_ZIP = "$env:TEMP\stockfish.zip"
$ENGINES_DIR   = "$scriptDir\engines"
$VCREDIST_URL  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
$VCREDIST_EXE  = "$env:TEMP\vc_redist.x64.exe"

function Write-Header {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "   AlChess - Installateur Windows" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step($msg) {
    Write-Host "[+] $msg" -ForegroundColor Green
}

function Write-Info($msg) {
    Write-Host "    $msg" -ForegroundColor Gray
}

function Write-Warn($msg) {
    Write-Host "[!] $msg" -ForegroundColor Yellow
}

function Write-Fail($msg) {
    Write-Host "[X] $msg" -ForegroundColor Red
}

# -- Vérification Windows 10+ -------------------------------------------------

function Assert-Windows10 {
    $build = [System.Environment]::OSVersion.Version.Build
    if ($build -lt 10240) {
        Write-Fail "Windows 10 ou supérieur requis (build détecté : $build)."
        Write-Host "    Téléchargez Python 3.12 manuellement : https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }
}

# -- Vérification / installation Python 3.12 ----------------------------------

function Get-Python312 {
    # Tente py -3.12 (Windows Launcher)
    try {
        $ver = & py -3.12 --version 2>&1
        if ($ver -match "Python 3\.1[2-9]") {
            Write-Step "Python 3.12+ détecté : $ver"
            return "py -3.12"
        }
    } catch {}

    # Tente python --version (si 3.12+ dans PATH)
    try {
        $ver = & python --version 2>&1
        if ($ver -match "Python 3\.1[2-9]") {
            Write-Step "Python 3.12+ détecté : $ver"
            return "python"
        }
    } catch {}

    return $null
}

function Install-Python312 {
    Write-Warn "Python 3.12+ non trouvé. Tentative d'installation via winget..."

    # Vérifier winget
    try {
        & winget --version | Out-Null
    } catch {
        Write-Fail "winget non disponible sur ce système."
        Write-Host ""
        Write-Host "    Installez Python 3.12 manuellement depuis :" -ForegroundColor Yellow
        Write-Host "    https://www.python.org/downloads/release/python-3120/" -ForegroundColor Cyan
        Write-Host "    Cochez 'Add Python to PATH' lors de l'installation." -ForegroundColor Yellow
        Write-Host "    Puis relancez ce script." -ForegroundColor Yellow
        exit 1
    }

    Write-Info "Installation de Python 3.12 via winget (non-destructif)..."
    & winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Échec de l'installation via winget."
        Write-Host "    Installez Python 3.12 manuellement : https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }

    # Rafraîchir le PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")

    $pyCmd = Get-Python312
    if (-not $pyCmd) {
        Write-Fail "Python 3.12 installé mais non détecté. Redémarrez le terminal et relancez."
        exit 1
    }
    return $pyCmd
}

# -- Création du venv ---------------------------------------------------------

function New-Venv($pyCmd) {
    $venvPath = "$scriptDir\venv"
    if (Test-Path "$venvPath\Scripts\python.exe") {
        Write-Step "Environnement virtuel déjà présent - mise à jour des dépendances."
    } else {
        Write-Step "Création de l'environnement virtuel..."
        if ($pyCmd -eq "py -3.12") {
            & py -3.12 -m venv "$venvPath"
        } else {
            & python -m venv "$venvPath"
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Échec de la création du venv."
            exit 1
        }
    }
}

# -- Installation des dépendances ---------------------------------------------

function Install-Dependencies {
    Write-Step "Installation des dépendances Python..."
    $pip = "$scriptDir\venv\Scripts\pip.exe"
    & $pip install --upgrade pip --quiet
    & $pip install -r "$scriptDir\requirements.txt" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Échec de l'installation des dépendances."
        exit 1
    }
    Write-Info "Dépendances installées."
}

# -- Stockfish ----------------------------------------------------------------

function Find-Stockfish {
    if (-not (Test-Path $ENGINES_DIR)) { return $false }
    $exes = Get-ChildItem -Path $ENGINES_DIR -Filter "stockfish*.exe" -Recurse -ErrorAction SilentlyContinue
    return ($exes.Count -gt 0)
}

function Install-Stockfish {
    Write-Step "Téléchargement de Stockfish..."
    try {
        Write-Info "Source : $STOCKFISH_URL"
        Invoke-WebRequest -Uri $STOCKFISH_URL -OutFile $STOCKFISH_ZIP -UseBasicParsing
        Write-Info "Extraction..."
        if (-not (Test-Path $ENGINES_DIR)) { New-Item -ItemType Directory -Path $ENGINES_DIR | Out-Null }
        Expand-Archive -Path $STOCKFISH_ZIP -DestinationPath $ENGINES_DIR -Force
        Remove-Item $STOCKFISH_ZIP -ErrorAction SilentlyContinue
        Write-Step "Stockfish installé dans $ENGINES_DIR"
    } catch {
        Write-Warn "Échec du téléchargement : $_"
        Write-Info "Téléchargez Stockfish manuellement depuis https://stockfishchess.org/download/"
        Write-Info "et placez le .exe dans le dossier engines\"
    }
}

# -- Visual C++ runtime (requis par lc0/Maia) ---------------------------------
# NOTE : messages EN ANGLAIS pour cette fonction (destinés à l'utilisateur final).

function Install-VCRedist {
    # a. Déjà présent ?
    if (Test-Path "$env:SystemRoot\System32\MSVCP140.dll") {
        Write-Step "Visual C++ runtime already present"
        return
    }

    # b. Pas de runtime : tester la connexion internet AVANT de télécharger.
    if (-not (Test-Connection -ComputerName aka.ms -Count 1 -Quiet)) {
        Write-Warn "No internet connection detected."
        Write-Warn "The Visual C++ runtime is required for the Maia engine (lc0)."
        Write-Warn "Please download it manually from:"
        Write-Warn "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
        Write-Warn "then re-run this installer. Continuing without it for now."
        return
    }

    # c. Connexion OK : télécharger puis installer en silencieux.
    Write-Step "Downloading Visual C++ runtime (required for Maia engine)..."
    try {
        Write-Info "Source: $VCREDIST_URL"
        Invoke-WebRequest -Uri $VCREDIST_URL -OutFile $VCREDIST_EXE -UseBasicParsing
        Write-Info "Installing Visual C++ runtime (silent)..."
        & $VCREDIST_EXE /install /quiet /norestart
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 3010) {
            throw "vc_redist installer returned exit code $LASTEXITCODE"
        }
        Remove-Item $VCREDIST_EXE -ErrorAction SilentlyContinue
        Write-Step "Visual C++ runtime installed"
    } catch {
        # d. Échec : message clair + choix de continuer sans Maia.
        Write-Warn "Failed to install the Visual C++ runtime: $_"
        Write-Warn "The Maia engine (lc0) will NOT work without this runtime."
        Write-Warn "To fix this later, download and install it manually from:"
        Write-Warn "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
        Write-Warn "Stockfish and the other modes will still work fine."
        Write-Host ""
        $rep = Read-Host "Continue installation without Maia support? (Y/N)"
        if ($rep -match "^[nN]") {
            Write-Fail "Installation aborted by user."
            exit 1
        }
        Write-Info "Continuing without Maia support."
    }
}

# -- Script de lancement ------------------------------------------------------

function Assert-LaunchScript {
    $ps1 = "$scriptDir\start_alchess.ps1"
    if (-not (Test-Path $ps1)) {
        Write-Warn "start_alchess.ps1 non trouvé - création..."
        @(
            '$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition',
            '$env:PYTHONPYCACHEPREFIX = "$env:TEMP\alchess_pyc"',
            '$env:PYTHONIOENCODING = "utf-8"',
            'Set-Location $scriptDir',
            '& "$scriptDir\venv\Scripts\python.exe" -m nicsoft.web 2>&1 | Tee-Object "$scriptDir\alchess_log.txt"'
        ) | Set-Content $ps1 -Encoding UTF8
    }
}

# -- Main ---------------------------------------------------------------------

Write-Header
Assert-Windows10

# Python
$pyCmd = Get-Python312
if (-not $pyCmd) {
    $pyCmd = Install-Python312
}

# Venv + dépendances
New-Venv $pyCmd
Install-Dependencies

# Stockfish
if (Find-Stockfish) {
    Write-Step "Stockfish déjà présent dans engines\ - aucun téléchargement nécessaire."
} else {
    Write-Host ""
    Write-Host "Stockfish (moteur d'échecs) non détecté." -ForegroundColor Yellow
    $rep = Read-Host "Voulez-vous le télécharger automatiquement ? (O/N)"
    if ($rep -match "^[oOyY]") {
        Install-Stockfish
    } else {
        Write-Info "Pas de téléchargement. Placez stockfish.exe dans le dossier engines\ et relancez."
    }
}

# Visual C++ runtime (requis par lc0/Maia)
Install-VCRedist

Assert-LaunchScript

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   Installation terminée !" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour lancer AlChess :" -ForegroundColor White
Write-Host "   Double-cliquez sur start_alchess.ps1" -ForegroundColor Cyan
Write-Host "   ou dans PowerShell : .\start_alchess.ps1" -ForegroundColor Cyan
Write-Host ""
