@echo off
rem Lit le PS1, le reecrit avec CRLF, puis l'execute
rem ReadAllLines/WriteAllLines gere le CRLF automatiquement sur Windows
powershell -ExecutionPolicy Bypass -Command "$f='%~dp0install_alchess.ps1';$t='%~dp0_install_tmp.ps1';$lines=[IO.File]::ReadAllLines($f,[Text.Encoding]::UTF8);[IO.File]::WriteAllLines($t,$lines,[Text.UTF8Encoding]::new($false));& powershell -ExecutionPolicy Bypass -File $t;Remove-Item $t -EA 0"
pause
