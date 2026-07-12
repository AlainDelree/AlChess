@echo off
rem Reecrit le PS1 en UTF-8 BOM + CRLF (requis par PowerShell 5.1), puis l'execute
powershell -ExecutionPolicy Bypass -Command "$f='%~dp0install_alchess.ps1';$t='%~dp0_install_tmp.ps1';Get-Content $f -Encoding UTF8 | Out-File $t -Encoding UTF8;& powershell -ExecutionPolicy Bypass -File $t;Remove-Item $t -EA 0"
pause
