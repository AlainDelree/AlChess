@echo off
rem Convertit LF -> CRLF puis execute le script PowerShell
powershell -ExecutionPolicy Bypass -Command "$f='%~dp0install_alchess.ps1'; $t='%~dp0_install_tmp.ps1'; (Get-Content $f) | Set-Content $t; & powershell -ExecutionPolicy Bypass -File $t; Remove-Item $t -ErrorAction SilentlyContinue"
pause
