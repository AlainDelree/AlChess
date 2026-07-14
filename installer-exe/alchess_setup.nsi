; ============================================================================
;  alchess_setup.nsi  —  Squelette reel de l'installeur AlChess (phase 2)
;
;  Installeur Windows compile (AlChess_Setup.exe), developpe EN PARALLELE de
;  install_alchess.ps1 (script PowerShell existant, non modifie).
;
;  --- ARCHITECTURE (decision prise, issue #52 / suite #50) --------------------
;  Le .exe reste CO-LOCALISE avec l'app extraite, exactement comme
;  install_alchess.ps1 aujourd'hui : l'utilisateur telecharge le ZIP de
;  release (qui contient deja le code + engines/), l'extrait, et lance le .exe
;  DEPUIS ce dossier. L'installeur ne "s'installe" donc PAS ailleurs : il
;  configure SUR PLACE. La racine de reference est $EXEDIR (le dossier du .exe),
;  equivalent NSIS de $scriptDir dans le .ps1.
;  => PAS d'installeur autonome qui telecharge le code de l'app (hors scope).
;
;  --- ETAT DES PHASES --------------------------------------------------------
;  Phase 1 (#50, #51) : outillage NSIS valide, plugin Inetc en place.
;  Phase 2 (#52, CE FICHIER) : vrai squelette (pages MUI2, sections vides).
;  Phase 3  : Section "Verification Python"  — portage de Get-Python312.
;  Phase 4  : Section "Installation Stockfish" — portage de Install-Stockfish.
;  Phase 5  : Section "Runtime Visual C++"   — portage de Install-VCRedist.
;
;  Compilation : makensis installer-exe/alchess_setup.nsi
;  Voir GitHub issue #50 pour le contexte global et les phases suivantes.
; ============================================================================

Unicode true

!include "MUI2.nsh"
!include "WinVer.nsh"          ; fournit la macro ${AtLeastWin10}

; ---------------------------------------------------------------------------
;  Variables de chemin — equivalents des chemins de install_alchess.ps1.
;  Toutes les references sont relatives a $EXEDIR (dossier du .exe execute),
;  jamais figees a la compilation. NSIS resout $EXEDIR au runtime, donc le
;  binaire "suit" le dossier ou il se trouve, comme $scriptDir cote .ps1.
;
;    NSIS                         PowerShell (install_alchess.ps1)
;    ---------------------------  ------------------------------------------
;    $EXEDIR                      $scriptDir  (Split-Path du .ps1)
;    $EXEDIR\engines             $ENGINES_DIR = "$scriptDir\engines"
;    $EXEDIR\venv                $venvPath    = "$scriptDir\venv"
;
;  Note : $EXEDIR n'est pas assignable ; on definit des !define pour les
;  sous-chemins afin de garder un point unique a maintenir dans les phases 3-5.
; ---------------------------------------------------------------------------
!define ENGINES_SUBDIR "engines"     ; ~ $ENGINES_DIR (relatif a $EXEDIR)
!define VENV_SUBDIR    "venv"        ; ~ $venvPath    (relatif a $EXEDIR)

; ---------------------------------------------------------------------------
;  Branding — coherent avec Write-Header de install_alchess.ps1
;  ("AlChess - Windows Installer").
; ---------------------------------------------------------------------------
Name "AlChess - Windows Installer"
BrandingText "AlChess - Windows Installer"
OutFile "AlChess_Setup.exe"

; Pas de InstallDir : on ne s'installe pas, on configure sur place ($EXEDIR).
; RequestExecutionLevel user : aucune ecriture hors du dossier de l'app.
; (Les phases 3-5 pourront relever le niveau si l'install de Python/VC++ le
;  necessite ; a evaluer le moment venu.)
RequestExecutionLevel user
ShowInstDetails show

; ---------------------------------------------------------------------------
;  Finish page : case a cocher "Lancer AlChess" (preparation du lancement de
;  l'app une fois toutes les phases terminees). La cible est encore inactive
;  (fonction LaunchAlChess = placeholder) ; elle pointera vers le lanceur
;  co-localise (2-Lancer_AlChess.bat / start_alchess) dans une phase ulterieure.
; ---------------------------------------------------------------------------
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Lancer AlChess"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchAlChess

; ---------------------------------------------------------------------------
;  Pages de l'assistant (interface moderne MUI2).
;  Welcome  : accueil / branding.
;  InstFiles: barre de progression (accueillera telechargements + install
;             de Python/Stockfish/VC++ dans les phases 3-5).
;  Finish   : fin + option "Lancer AlChess".
; ---------------------------------------------------------------------------
!define MUI_WELCOMEPAGE_TITLE "AlChess - Windows Installer"
!define MUI_WELCOMEPAGE_TEXT "Cet assistant configure AlChess sur votre PC (Windows 10 ou superieur).$\r$\n$\r$\nIl verifie Python 3.12, prepare l'environnement, et propose de telecharger le moteur d'echecs Stockfish ainsi que le runtime Visual C++ necessaire a Maia.$\r$\n$\r$\nAlChess sera configure directement dans ce dossier."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ---------------------------------------------------------------------------
;  Langue : francais (coherent avec le projet).
;  i18n futur possible : ajouter d'autres !insertmacro MUI_LANGUAGE ici (ex.
;  "English") + un bloc de selection de langue. Non urgent — le projet cible
;  un public francophone pour l'instant.
; ---------------------------------------------------------------------------
!insertmacro MUI_LANGUAGE "French"

; ---------------------------------------------------------------------------
;  Verification de la version de Windows au lancement (Windows 10+).
;  Equivalent de Assert-Windows10 dans le .ps1.
; ---------------------------------------------------------------------------
Function .onInit
    ${IfNot} ${AtLeastWin10}
        MessageBox MB_OK|MB_ICONSTOP "AlChess requiert Windows 10 ou superieur."
        Abort
    ${EndIf}
FunctionEnd

; ---------------------------------------------------------------------------
;  Placeholder du bouton "Lancer AlChess" de la page Finish.
;  Sera implemente quand toutes les phases seront terminees (lancera le
;  binaire co-localise depuis $EXEDIR).
; ---------------------------------------------------------------------------
Function LaunchAlChess
    ; TODO (phase finale) : Exec '"$EXEDIR\2-Lancer_AlChess.bat"'
    DetailPrint "Lancement d'AlChess — a implementer (phase finale)."
FunctionEnd

; ============================================================================
;  SECTIONS DE CONFIGURATION
;  Toutes co-localisees sur $EXEDIR. Vides pour l'instant (un DetailPrint
;  chacune) — remplies dans les phases 3-5.
; ============================================================================

SectionGroup "Configuration AlChess" SecGroupConfig

    ; -- Phase 3 : portage de Get-Python312 / Install-Python312 --------------
    Section "Verification Python" SecPython
        DetailPrint "Racine de configuration (EXEDIR) : $EXEDIR"
        DetailPrint "[Phase 3] Verification de Python 3.12 — a implementer."
        DetailPrint "  venv cible : $EXEDIR\${VENV_SUBDIR}"
    SectionEnd

    ; -- Phase 4 : portage de Find-Stockfish / Install-Stockfish -------------
    Section "Installation Stockfish" SecStockfish
        DetailPrint "[Phase 4] Installation de Stockfish — a implementer."
        DetailPrint "  dossier moteurs : $EXEDIR\${ENGINES_SUBDIR}"
    SectionEnd

    ; -- Phase 5 : portage de Install-VCRedist -------------------------------
    Section "Runtime Visual C++" SecVCRedist
        DetailPrint "[Phase 5] Installation du runtime Visual C++ (Maia) — a implementer."
    SectionEnd

SectionGroupEnd
