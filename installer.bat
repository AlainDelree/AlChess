@echo off
rem Lit en UTF-8, convertit LF->CRLF, puis execute le script PowerShell
powershell -ExecutionPolicy Bypass -Command "$f='%~dp0install_alchess.ps1';$t='%~dp0_install_tmp.ps1';$c=[IO.File]::ReadAllText($f,[Text.Encoding]::UTF8);$c=$c -replace \"`r`n\",\"`n\" -replace \"`n\",\"`r`n\";[IO.File]::WriteAllText($t,$c,[Text.UTF8Encoding]::new($false));& powershell -ExecutionPolicy Bypass -File $t;Remove-Item $t -EA 0"
pause
