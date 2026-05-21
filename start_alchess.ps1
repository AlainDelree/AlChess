# Lancement d'AlChess — détecte automatiquement son propre répertoire
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\alchess_pyc"
$env:PYTHONIOENCODING = "utf-8"
Set-Location $scriptDir
& "$scriptDir\venv\Scripts\python.exe" -m nicsoft.web 2>&1 | Tee-Object "$scriptDir\alchess_log.txt"
