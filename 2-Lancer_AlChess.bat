@echo off
rem ============================================================================
rem  2-Lancer_AlChess.bat  --  Lanceur AlChess, 100%% batch pur (issue #70)
rem ----------------------------------------------------------------------------
rem  POURQUOI CETTE REECRITURE (signal de securite originel : issue #58)
rem  L'ancienne version invoquait powershell.exe DEUX fois (avec
rem  -ExecutionPolicy Bypass) pour reecrire puis lancer start_alchess.ps1.
rem  Le Bypass passe en ligne de commande (scope Process) surclasse la policy
rem  PAR DEFAUT (LocalMachine = Restricted), mais il est IGNORE si une policy
rem  est imposee par Group Policy (scope MachinePolicy/UserPolicy, prioritaire).
rem  Consequence : une machine sous GPO stricte pouvait INSTALLER AlChess
rem  (via AlChess_Setup.exe, chantier NSIS #50-#69) puis rester bloquee AU
rem  LANCEMENT -- exactement le blocage que tout le chantier NSIS visait a
rem  eviter, ressurgissant un cran plus loin.
rem  Ce lanceur en batch pur ne met AUCUNE policy PowerShell en jeu : il se
rem  lance quelle que soit la configuration Group Policy de la machine.
rem
rem  start_alchess.ps1 N'EST PAS supprime (usage manuel / developpeur) ; ce
rem  fichier .bat ne l'appelle simplement plus.
rem
rem  EQUIVALENCES avec l'ancien start_alchess.ps1 (rien de perdu) :
rem    $scriptDir                    -> %~dp0  (dossier de ce .bat, \ final)
rem    Set-Location $scriptDir       -> cd /d "%~dp0"
rem    $env:PYTHONPYCACHEPREFIX      -> set "PYTHONPYCACHEPREFIX=%TEMP%\alchess_pyc"
rem    $env:PYTHONIOENCODING="utf-8" -> set "PYTHONIOENCODING=utf-8"
rem    & "$scriptDir\venv\Scripts\python.exe" -m nicsoft.web
rem  L'ancien premier appel PowerShell servait uniquement a reecrire le .ps1
rem  en UTF-8 BOM (contrainte de lecture de PowerShell 5.1) : sans .ps1, cette
rem  etape n'a plus lieu d'etre. L'ouverture du navigateur n'est PAS faite ici
rem  ni dans le .ps1 : c'est nicsoft.web (webbrowser.open, alchess.py) qui s'en
rem  charge -- comportement inchange.
rem
rem  CHOIX DE LOGGING (point de conception tranche en #70)
rem  cmd.exe n'a pas de "tee" natif : impossible d'AFFICHER dans la console ET
rem  d'ecrire dans alchess_log.txt simultanement comme le faisait Tee-Object.
rem  -> Option retenue : (a) redirection vers alchess_log.txt UNIQUEMENT.
rem  Raison : nicsoft.web ouvre le navigateur automatiquement, donc
rem  l'utilisateur final travaille dans le navigateur, pas dans cette fenetre.
rem  Le fichier log reste COMPLET -- c'est lui qui sert au support/debogage
rem  (rapports de bug via le bridge). On ECRASE le log a chaque lancement
rem  (redirection ">"), comme l'ancien Tee-Object sans -Append : une session =
rem  un log, taille bornee.
rem
rem  Le serveur tourne en continu : la fenetre reste ouverte tant qu'AlChess
rem  tourne (python.exe bloque). Le "pause" final ne se declenche donc QU'APRES
rem  l'arret du serveur -- utile pour lire un message d'erreur si python.exe
rem  s'arrete tout de suite (sinon la fenetre se fermerait sans rien montrer,
rem  la sortie etant redirigee dans le log).
rem ============================================================================

setlocal
set "PYTHONPYCACHEPREFIX=%TEMP%\alchess_pyc"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

echo(
echo   AlChess demarre... le navigateur va s'ouvrir automatiquement.
echo   Gardez cette fenetre OUVERTE tant que vous utilisez AlChess.
echo   (fermer cette fenetre arrete le serveur)
echo   Journal : "%~dp0alchess_log.txt"
echo(

"%~dp0venv\Scripts\python.exe" -m nicsoft.web > "%~dp0alchess_log.txt" 2>&1

echo(
echo   AlChess s'est arrete. En cas de probleme, consultez le journal :
echo   "%~dp0alchess_log.txt"
echo(
pause
endlocal
