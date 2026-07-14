; ============================================================================
;  alchess_setup.nsi  —  Spike de faisabilite NSIS (phase 1)
;  Installeur Windows compile AlChess_Setup, developpe EN PARALLELE de
;  install_alchess.ps1 (script PowerShell existant, non modifie).
;
;  Objectif du spike : valider que l'outillage NSIS (makensis) fonctionne
;  sur le poste Linux et produit un .exe Windows. La logique reelle de
;  install_alchess.ps1 (Python 3.12, venv, dependances, Stockfish) N'EST
;  PAS encore portee ici.
;
;  Compilation : makensis installer-exe/alchess_setup.nsi
;  Voir GitHub issue #50 pour le contexte et les phases suivantes.
; ============================================================================

Unicode true

!include "MUI2.nsh"
!include "WinVer.nsh"          ; fournit la macro ${AtLeastWin10}

; ---------------------------------------------------------------------------
;  Branding — coherent avec le header de install_alchess.ps1
;  ("AlChess - Windows Installer")
; ---------------------------------------------------------------------------
Name "AlChess - Windows Installer"
BrandingText "AlChess - Windows Installer (spike NSIS)"
OutFile "AlChess_Setup_spike.exe"
InstallDir "$LOCALAPPDATA\AlChess"
RequestExecutionLevel user
ShowInstDetails show

; ---------------------------------------------------------------------------
;  Pages de l'assistant (interface moderne MUI2)
; ---------------------------------------------------------------------------
!define MUI_WELCOMEPAGE_TITLE "AlChess - Windows Installer"
!define MUI_WELCOMEPAGE_TEXT "Spike de faisabilite NSIS (phase 1).$\r$\n$\r$\nCet assistant ne fait encore rien d'autre que valider la chaine de compilation NSIS."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

; ---------------------------------------------------------------------------
;  Verification de la version de Windows au lancement (Windows 10+)
; ---------------------------------------------------------------------------
Function .onInit
    ${IfNot} ${AtLeastWin10}
        MessageBox MB_OK|MB_ICONSTOP "AlChess requiert Windows 10 ou superieur."
        Abort
    ${EndIf}
FunctionEnd

; ---------------------------------------------------------------------------
;  Section unique : affiche la MessageBox de validation du spike et quitte.
;  Le "bouton" est le bouton Install de la page INSTFILES qui declenche
;  cette section.
; ---------------------------------------------------------------------------
Section "Spike NSIS" SecSpike
    MessageBox MB_OK "Spike NSIS OK"
    DetailPrint "Spike NSIS OK — aucune installation reelle effectuee."
SectionEnd
