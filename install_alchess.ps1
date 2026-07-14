#Requires -Version 5.1
<#
.SYNOPSIS
    AlChess installer for Windows 10+
.DESCRIPTION
    Installs Python 3.12, creates the venv, installs the dependencies,
    and offers to download Stockfish.
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
    Write-Host "   AlChess - Windows Installer" -ForegroundColor Cyan
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

# -- Windows 10+ check --------------------------------------------------------

function Assert-Windows10 {
    $build = [System.Environment]::OSVersion.Version.Build
    if ($build -lt 10240) {
        Write-Fail "Windows 10 or later required (detected build: $build)."
        Write-Host "    Download Python 3.12 manually: https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }
}

# -- Python 3.12 check / installation -----------------------------------------

function Test-PythonVersionString($versionString) {
    if ($versionString -match "Python (\d+\.\d+)(\.\d+)?") {
        try { return [version]$Matches[1] } catch { return $null }
    }
    return $null
}

function Get-Python312 {
    $minVersion = [version]"3.12"

    # 1. py -0p : enumere toutes les versions Python enregistrees aupres du
    #    lanceur Windows avec leur chemin complet - plus fiable qu'un test
    #    unique sur "-3.12".
    try {
        $list = & py -0p 2>$null
        if ($LASTEXITCODE -eq 0 -and $list) {
            foreach ($line in $list) {
                if ($line -match "-(\d+\.\d+)(?:-\d+)?\s+(.+\.exe)\s*$") {
                    $v = [version]$Matches[1]
                    $path = $Matches[2].Trim()
                    if ($v -ge $minVersion -and (Test-Path $path)) {
                        Write-Step "Python $v detected via py launcher: $path"
                        return $path
                    }
                }
            }
        }
    } catch {}

    # 2. python --version dans le PATH
    try {
        $ver = & python --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            $v = Test-PythonVersionString "$ver"
            if ($v -and $v -ge $minVersion) {
                Write-Step "Python $v detected in PATH: $ver"
                return "python"
            }
        }
    } catch {}

    # 3. Chemins d'installation standards, si ni py ni python ne sont dans
    #    le PATH (cas signale par un utilisateur externe).
    $searchRoots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "$env:ProgramFiles",
        "${env:ProgramFiles(x86)}"
    )
    foreach ($root in $searchRoots) {
        if (-not (Test-Path $root)) { continue }
        $dirs = Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "^Python3(1[2-9]|[2-9]\d)$" } |
            Sort-Object Name -Descending
        foreach ($dir in $dirs) {
            $exe = Join-Path $dir.FullName "python.exe"
            if (-not (Test-Path $exe)) { continue }
            try {
                $ver = & $exe --version 2>$null
                if ($LASTEXITCODE -eq 0) {
                    $v = Test-PythonVersionString "$ver"
                    if ($v -and $v -ge $minVersion) {
                        Write-Step "Python $v detected at $exe"
                        return $exe
                    }
                }
            } catch {}
        }
    }

    return $null
}

function Install-Python312 {
    Write-Warn "Python 3.12+ not found. Attempting installation via winget..."

    # Check winget
    try {
        & winget --version | Out-Null
    } catch {
        Write-Fail "winget is not available on this system."
        Write-Host ""
        Write-Host "    Install Python 3.12 manually from:" -ForegroundColor Yellow
        Write-Host "    https://www.python.org/downloads/release/python-3120/" -ForegroundColor Cyan
        Write-Host "    Check 'Add Python to PATH' during installation." -ForegroundColor Yellow
        Write-Host "    Then re-run this script." -ForegroundColor Yellow
        exit 1
    }

    Write-Info "Installing Python 3.12 via winget (non-destructive)..."
    & winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "winget installation failed."
        Write-Host "    Install Python 3.12 manually: https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }

    # Refresh the PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")

    $pyCmd = Get-Python312
    if (-not $pyCmd) {
        Write-Fail "Python 3.12 installed but not detected. Restart the terminal and re-run."
        exit 1
    }
    return $pyCmd
}

# -- Venv creation ------------------------------------------------------------

function New-Venv($pyCmd) {
    $venvPath = "$scriptDir\venv"
    if (Test-Path "$venvPath\Scripts\python.exe") {
        Write-Step "Virtual environment already present - updating dependencies."
    } else {
        Write-Step "Creating the virtual environment..."
        & $pyCmd -m venv "$venvPath"
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Failed to create the venv."
            exit 1
        }
    }
}

# -- Dependencies installation ------------------------------------------------

function Install-Dependencies {
    Write-Step "Installing Python dependencies..."
    $pip = "$scriptDir\venv\Scripts\pip.exe"
    & $pip install --upgrade pip --quiet
    & $pip install -r "$scriptDir\requirements.txt" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to install dependencies."
        exit 1
    }
    Write-Info "Dependencies installed."
}

# -- Stockfish ----------------------------------------------------------------

function Find-Stockfish {
    if (-not (Test-Path $ENGINES_DIR)) { return $false }
    $exes = @(Get-ChildItem -Path $ENGINES_DIR -Filter "stockfish*.exe" -Recurse -ErrorAction SilentlyContinue)
    return ($exes.Count -gt 0)
}

function Install-Stockfish {
    Write-Step "Downloading Stockfish..."
    try {
        Write-Info "Source: $STOCKFISH_URL"
        Invoke-WebRequest -Uri $STOCKFISH_URL -OutFile $STOCKFISH_ZIP -UseBasicParsing
        Write-Info "Extracting..."
        if (-not (Test-Path $ENGINES_DIR)) { New-Item -ItemType Directory -Path $ENGINES_DIR | Out-Null }
        Expand-Archive -Path $STOCKFISH_ZIP -DestinationPath $ENGINES_DIR -Force
        # Remove the "Mark of the Web" (Zone.Identifier) attribute added to files
        # downloaded from Internet, otherwise Windows refuses to launch the unsigned
        # .exe from a subprocess -> PermissionError [WinError 5] (issue #42).
        Get-ChildItem -Path $ENGINES_DIR -Filter "*.exe" -Recurse | Unblock-File
        Remove-Item $STOCKFISH_ZIP -ErrorAction SilentlyContinue
        Write-Step "Stockfish installed in $ENGINES_DIR"
    } catch {
        Write-Warn "Download failed: $_"
        Write-Info "Download Stockfish manually from https://stockfishchess.org/download/"
        Write-Info "and place the .exe in the engines\ folder"
    }
}

# -- Visual C++ runtime (required by lc0/Maia) --------------------------------

function Install-VCRedist {
    # a. Already present?
    if (Test-Path "$env:SystemRoot\System32\MSVCP140.dll") {
        Write-Step "Visual C++ runtime already present"
        return
    }

    # b. No runtime: test the internet connection BEFORE downloading.
    if (-not (Test-Connection -ComputerName aka.ms -Count 1 -Quiet)) {
        Write-Warn "No internet connection detected."
        Write-Warn "The Visual C++ runtime is required for the Maia engine (lc0)."
        Write-Warn "Please download it manually from:"
        Write-Warn "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
        Write-Warn "then re-run this installer. Continuing without it for now."
        return
    }

    # c. Connection OK: download then install silently.
    Write-Step "Downloading Visual C++ runtime (required for Maia engine)..."
    try {
        Write-Info "Source: $VCREDIST_URL"
        Invoke-WebRequest -Uri $VCREDIST_URL -OutFile $VCREDIST_EXE -UseBasicParsing
        # Remove the "Mark of the Web" attribute so Windows does not block the
        # downloaded installer when launched silently (issue #42).
        Unblock-File -Path $VCREDIST_EXE
        Write-Info "Installing Visual C++ runtime (silent)..."
        & $VCREDIST_EXE /install /quiet /norestart
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 3010) {
            throw "vc_redist installer returned exit code $LASTEXITCODE"
        }
        Remove-Item $VCREDIST_EXE -ErrorAction SilentlyContinue
        Write-Step "Visual C++ runtime installed"
    } catch {
        # d. Failure: clear message + option to continue without Maia.
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

# -- Launch script ------------------------------------------------------------

function Assert-LaunchScript {
    $ps1 = "$scriptDir\start_alchess.ps1"
    if (-not (Test-Path $ps1)) {
        Write-Warn "start_alchess.ps1 not found - creating it..."
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

# Venv + dependencies
New-Venv $pyCmd
Install-Dependencies

# Stockfish
if (Find-Stockfish) {
    Write-Step "Stockfish already present in engines\ - no download needed."
} else {
    Write-Host ""
    Write-Host "Stockfish (chess engine) not detected." -ForegroundColor Yellow
    $rep = Read-Host "Download it automatically? (Y/N)"
    if ($rep -match "^[oOyY]") {
        Install-Stockfish
    } else {
        Write-Info "No download. Place stockfish.exe in the engines\ folder and re-run."
    }
}

# Visual C++ runtime (required by lc0/Maia)
Install-VCRedist

Assert-LaunchScript

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   Installation complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# -- Desktop shortcut ---------------------------------------------------------
# Create a Desktop shortcut pointing to 2-Lancer_AlChess.bat (never the .ps1
# directly, which the PowerShell execution policy can block on double-click).
# The path is resolved dynamically from $scriptDir so the shortcut keeps working
# even if the folder is moved after installation. Failure here is not fatal.
try {
    $desktop  = [Environment]::GetFolderPath("Desktop")
    $lnkPath  = Join-Path $desktop "AlChess.lnk"
    $wsh      = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($lnkPath)
    $shortcut.TargetPath       = "$scriptDir\2-Lancer_AlChess.bat"
    $shortcut.WorkingDirectory = $scriptDir
    $shortcut.Description       = "Launch AlChess"
    $shortcut.Save()
    Write-Host "Desktop shortcut 'AlChess' created." -ForegroundColor Green
} catch {
    Write-Warn "Could not create the Desktop shortcut - you can still launch AlChess manually."
}

Write-Host ""
Write-Host "To launch AlChess:" -ForegroundColor White
Write-Host "   Double-click the 'AlChess' shortcut on your Desktop" -ForegroundColor Cyan
Write-Host "   or double-click 2-Lancer_AlChess.bat in this folder" -ForegroundColor Cyan
Write-Host ""
