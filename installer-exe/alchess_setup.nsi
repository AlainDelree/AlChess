; ============================================================================
;  alchess_setup.nsi  —  Installeur AlChess (phase 6 : finitions, code complet)
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
;  Phase 1 (#50, #51, #56) : outillage NSIS valide, plugins Inetc
;                            (telechargement) et nsisunz (extraction ZIP)
;                            en place.
;  Phase 2 (#52) : vrai squelette (pages MUI2, sections vides).
;  Phase 3 (#53, #54) : Section "Verification Python" — portage de
;                        Get-Python312 en NSIS natif (3 strategies).
;  Phase 3bis (#60) : portage de Install-Python312 — si les 3 strategies de
;                     detection echouent, installation automatique de Python
;                     3.12 via winget (fonction InstallPython312NSIS), puis
;                     re-detection via TryScanStandardDirs (aveugle au PATH).
;                     Complete enfin le parcours "sans Python" qui plantait
;                     auparavant au lancement de l'app (venv jamais cree).
;  Phase 4 (#55, #56) : Section "Installation Stockfish" — portage de
;                        Install-Stockfish avec cascade CPU (avx2 ->
;                        sse41-popcnt -> base) et test d'execution reel.
;                        Extraction ZIP via plugin nsisunz (#56).
;  Phase 5 (#57) : Section "Runtime Visual C++" — portage de
;                  Install-VCRedist. Utilise ExecShell "open" pour declencher
;                  l'UAC (requireAdministrator dans le manifeste vc_redist),
;                  avec verification post-installation via MSVCP140.dll.
;  Phase 6 (#58, CE FICHIER) : finitions. Raccourci bureau natif
;                              (CreateShortcut, cible 2-Lancer_AlChess.bat),
;                              implementation reelle de LaunchAlChess (bouton
;                              "Lancer AlChess" de la page Finish), message de
;                              fin. Le code des 6 phases est desormais COMPLET.
;                              => VALIDATION VM WINDOWS RESTE A FAIRE (aucune
;                                 phase n'a jamais tourne sur un vrai Windows).
;
;  --- AVERTISSEMENT PHASE 3 --------------------------------------------------
;  Cette section SecPython a ete validee uniquement par COMPILATION (makensis
;  sous Linux). Elle n'a JAMAIS ete executee sur un vrai Windows. Le portage
;  de la logique regex du .ps1 vers du decoupage de chaines NSIS est sujet a
;  erreurs : la syntaxe StrStr, FileReadLine, FindFirst/FindNext a ete suivie
;  selon la doc NSIS officielle, mais des bugs de runtime sont tres probables.
;  Les hypotheses non certaines :
;  - FileReadLine renvoie une ligne vide ("") en fin de fichier (pas d'erreur).
;  - nsExec::ExecToStack avec redirection cmd /c fonctionne comme attendu.
;  - Les chemins $LOCALAPPDATA, $PROGRAMFILES, $PROGRAMFILES64 sont fiables.
;  La validation VM sera plus longue que d'habitude pour cette phase.
;
;  Compilation : makensis installer-exe/alchess_setup.nsi
;  Voir GitHub issue #50 pour le contexte global et les phases suivantes.
; ============================================================================

Unicode true

!include "MUI2.nsh"
!include "WinVer.nsh"
!include "LogicLib.nsh"
!include "WordFunc.nsh"
!include "FileFunc.nsh"

; ---------------------------------------------------------------------------
;  Variables globales
; ---------------------------------------------------------------------------
Var PythonExe        ; Chemin vers python.exe detecte, ou vide si rien trouve
Var TempLine         ; Ligne temporaire pour lecture de fichier
Var TempVersion      ; Version extraite (ex: "3.12")
Var TempPath         ; Chemin extrait
Var TempMajor        ; Partie majeure de la version (ex: 3)
Var TempMinor        ; Partie mineure de la version (ex: 12)
Var VersionOK        ; 1 si version >= 3.12, 0 sinon

; Variables pour la section Stockfish (phase 4)
Var HasAvx2          ; 1 si AVX2 present, 0 sinon
Var StockfishOK      ; 1 si une variante Stockfish fonctionnelle a ete installee

; Variables pour la section VCRedist (phase 5)
Var VCRedistOK       ; 1 si VC++ installe avec succes, 0 sinon

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
!define MIN_PYTHON_MAJOR 3
!define MIN_PYTHON_MINOR 12

; URLs Stockfish — cascade de variantes (avx2 -> sse41-popcnt -> base)
; Meme logique que Get-StockfishUrl dans install_alchess.ps1
!define SF_URL_AVX2 "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-avx2.zip"
!define SF_URL_SSE41 "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-sse41-popcnt.zip"
!define SF_URL_BASE "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64.zip"

; URL Visual C++ Runtime (phase 5, issue #57)
; Meme URL que $VCREDIST_URL dans install_alchess.ps1
!define VCREDIST_URL "https://aka.ms/vs/17/release/vc_redist.x64.exe"

; Code de sortie "illegal instruction" (CPU incompatible) :
; 0xC000001D = -1073741795 en decimal signe
!define EXIT_ILLEGAL_INSTRUCTION -1073741795

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
;  Finish page : case a cocher "Lancer AlChess". Active (phase 6, #58) : la
;  fonction LaunchAlChess lance le lanceur co-localise 2-Lancer_AlChess.bat
;  depuis $EXEDIR via Exec.
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
;  LaunchAlChess (phase 6, issue #58)
;  Cible du bouton "Lancer AlChess" de la page Finish. Lance le lanceur
;  co-localise 2-Lancer_AlChess.bat depuis $EXEDIR — JAMAIS le .ps1
;  directement (le .bat encapsule l'appel PowerShell avec -ExecutionPolicy
;  Bypass, exactement comme le raccourci bureau, cf. install_alchess.ps1).
;
;  Exec (et non ExecWait) : l'installeur se ferme juste apres cette page,
;  inutile d'attendre le retour de l'app — le serveur AlChess reste ouvert
;  en continu (le .bat n'a volontairement pas de "pause" final).
; ---------------------------------------------------------------------------
Function LaunchAlChess
    Exec '"$EXEDIR\2-Lancer_AlChess.bat"'
FunctionEnd

; ============================================================================
;  FONCTIONS UTILITAIRES POUR LA DETECTION PYTHON
; ============================================================================

; ---------------------------------------------------------------------------
;  ExtractVersionFromLine
;  Extrait une version X.Y d'une ligne contenant "-V:X.Y" (format py -0p).
;  Entree : ligne dans $TempLine
;  Sortie : version dans $TempVersion (ou vide si non trouvee)
;           chemin dans $TempPath (ou vide si non trouve)
;
;  Format attendu : "-V:3.12 *  C:\path\to\python.exe" ou sans le *
;  Le * optionnel indique la version par defaut du lanceur.
; ---------------------------------------------------------------------------
Function ExtractVersionFromLine
    StrCpy $TempVersion ""
    StrCpy $TempPath ""

    ; Chercher "-V:" dans la ligne
    StrCpy $R0 $TempLine
    StrCpy $R1 0  ; position de depart

    ; Recherche manuelle de "-V:" dans la chaine
    StrLen $R2 $R0
    ${If} $R2 == 0
        Return
    ${EndIf}

    ; Parcourir la chaine pour trouver "-V:"
    StrCpy $R3 0  ; index courant
    find_vcolon_loop:
        IntCmp $R3 $R2 not_found 0 not_found
        StrCpy $R4 $R0 3 $R3  ; extraire 3 caracteres a partir de $R3
        StrCmp $R4 "-V:" found_vcolon 0
        IntOp $R3 $R3 + 1
        Goto find_vcolon_loop

    not_found:
        Return

    found_vcolon:
        ; $R3 = position de "-V:"
        ; Extraire la version apres "-V:"
        IntOp $R5 $R3 + 3  ; position apres "-V:"

        ; Extraire jusqu'a l'espace, la fin de ligne, ou tout caractere qui
        ; n'est ni un chiffre ni un point (issue #54, correctif secondaire).
        ; Evite d'absorber un suffixe d'architecture colle sans espace, ex.
        ; "-V:3.12-32" (install 32-bit) ne doit donner que "3.12", pas "3.12-32".
        StrCpy $R6 ""  ; accumulateur de version
        extract_version_loop:
            StrCpy $R7 $R0 1 $R5  ; caractere courant
            StrCmp $R7 "" version_done 0
            ; whitelist : n'accepter qu'un chiffre ou un point, sinon on s'arrete
            StrCmp $R7 "." keep_ver_char 0
            StrCmp $R7 "0" keep_ver_char 0
            StrCmp $R7 "1" keep_ver_char 0
            StrCmp $R7 "2" keep_ver_char 0
            StrCmp $R7 "3" keep_ver_char 0
            StrCmp $R7 "4" keep_ver_char 0
            StrCmp $R7 "5" keep_ver_char 0
            StrCmp $R7 "6" keep_ver_char 0
            StrCmp $R7 "7" keep_ver_char 0
            StrCmp $R7 "8" keep_ver_char 0
            StrCmp $R7 "9" keep_ver_char 0
            Goto version_done
            keep_ver_char:
                StrCpy $R6 "$R6$R7"
                IntOp $R5 $R5 + 1
                Goto extract_version_loop

        version_done:
            StrCpy $TempVersion $R6

            ; L'extraction de version a pu s'arreter sur un suffixe d'archi
            ; colle (ex. "-32" dans "-V:3.12-32"). Sauter ce reste de token
            ; jusqu'au prochain espace (ou fin de ligne) avant de chercher le
            ; chemin, sinon le "-32" serait pris pour le debut du chemin.
            skip_arch_suffix:
                StrCpy $R7 $R0 1 $R5
                StrCmp $R7 "" path_not_found 0
                StrCmp $R7 " " skip_spaces_and_star 0
                IntOp $R5 $R5 + 1
                Goto skip_arch_suffix

            ; Maintenant chercher le chemin (apres le * optionnel)
            ; Sauter les espaces et le * eventuel
            skip_spaces_and_star:
                StrCpy $R7 $R0 1 $R5
                StrCmp $R7 "" path_not_found 0
                StrCmp $R7 " " skip_char 0
                StrCmp $R7 "*" skip_char 0
                Goto start_extract_path
                skip_char:
                    IntOp $R5 $R5 + 1
                    Goto skip_spaces_and_star

            start_extract_path:
                ; Le reste de la ligne est le chemin
                StrCpy $TempPath $R0 "" $R5
                ; Nettoyer les espaces en fin de chemin (trim)
                StrLen $R8 $TempPath
                ${If} $R8 > 0
                    IntOp $R8 $R8 - 1
                    trim_loop:
                        IntCmp $R8 0 trim_done 0 trim_done
                        StrCpy $R9 $TempPath 1 $R8
                        StrCmp $R9 " " do_trim 0
                        StrCmp $R9 "$\r" do_trim 0
                        StrCmp $R9 "$\n" do_trim 0
                        Goto trim_done
                        do_trim:
                            StrCpy $TempPath $TempPath $R8
                            IntOp $R8 $R8 - 1
                            Goto trim_loop
                ${EndIf}
                trim_done:
                Return

            path_not_found:
                StrCpy $TempPath ""
                Return
FunctionEnd

; ---------------------------------------------------------------------------
;  ExtractVersionFromPythonOutput
;  Extrait la version X.Y d'une sortie "Python X.Y.Z".
;  Entree : sortie dans $TempLine
;  Sortie : version dans $TempVersion (ou vide si non trouvee)
; ---------------------------------------------------------------------------
Function ExtractVersionFromPythonOutput
    StrCpy $TempVersion ""

    ; Chercher "Python " dans la ligne
    StrCpy $R0 $TempLine
    StrLen $R2 $R0

    ${If} $R2 < 10
        Return
    ${EndIf}

    ; Chercher "Python "
    StrCpy $R3 0
    find_python_loop:
        IntCmp $R3 $R2 not_found_py 0 not_found_py
        StrCpy $R4 $R0 7 $R3  ; "Python "
        StrCmp $R4 "Python " found_python 0
        IntOp $R3 $R3 + 1
        Goto find_python_loop

    not_found_py:
        Return

    found_python:
        ; Extraire la version apres "Python "
        IntOp $R5 $R3 + 7

        ; Extraire X.Y (premier et deuxieme segment seulement)
        StrCpy $R6 ""  ; accumulateur
        StrCpy $R7 0   ; compteur de points
        extract_py_ver_loop:
            StrCpy $R8 $R0 1 $R5
            StrCmp $R8 "" py_ver_done 0
            StrCmp $R8 " " py_ver_done 0
            StrCmp $R8 "$\r" py_ver_done 0
            StrCmp $R8 "$\n" py_ver_done 0
            ; Si c'est un point, incrementer le compteur
            StrCmp $R8 "." check_dots 0
            ; Sinon, ajouter le caractere
            StrCpy $R6 "$R6$R8"
            IntOp $R5 $R5 + 1
            Goto extract_py_ver_loop

            check_dots:
                IntOp $R7 $R7 + 1
                ; Si on a deja 1 point, on s'arrete (on veut X.Y, pas X.Y.Z).
                ; IntCmp val1 val2 <egal> <inferieur> <superieur> : au 1er point
                ; (R7==1) on ajoute le point et on continue ; au 2e point et
                ; au-dela (R7>1) on s'arrete. Le cas <superieur> DOIT donc
                ; pointer sur py_ver_done, sinon "3.9.7" donne "3.9.7" (bug #54)
                ; puis un minor gonfle ("97") qui accepte a tort une version < 3.12.
                IntCmp $R7 1 add_dot py_ver_done py_ver_done
                add_dot:
                    StrCpy $R6 "$R6."
                    IntOp $R5 $R5 + 1
                    Goto extract_py_ver_loop

        py_ver_done:
            StrCpy $TempVersion $R6
            Return
FunctionEnd

; ---------------------------------------------------------------------------
;  CompareVersionToMinimum
;  Compare $TempVersion (format "X.Y") au minimum requis (3.12).
;  Sortie : $VersionOK = 1 si >= 3.12, 0 sinon
; ---------------------------------------------------------------------------
Function CompareVersionToMinimum
    StrCpy $VersionOK 0
    StrCpy $TempMajor ""
    StrCpy $TempMinor ""

    ; Extraire major et minor de $TempVersion
    StrCpy $R0 $TempVersion
    StrLen $R1 $R0

    ${If} $R1 == 0
        Return
    ${EndIf}

    ; Trouver le point
    StrCpy $R2 0  ; index
    find_dot_loop:
        IntCmp $R2 $R1 no_dot 0 no_dot
        StrCpy $R3 $R0 1 $R2
        StrCmp $R3 "." found_dot 0
        IntOp $R2 $R2 + 1
        Goto find_dot_loop

    no_dot:
        Return

    found_dot:
        ; $R2 = position du point
        StrCpy $TempMajor $R0 $R2        ; partie avant le point
        IntOp $R4 $R2 + 1
        StrCpy $TempMinor $R0 "" $R4     ; partie apres le point

        ; Nettoyer TempMinor (peut avoir des caracteres parasites)
        StrCpy $R5 ""
        StrCpy $R6 0
        clean_minor_loop:
            StrCpy $R7 $TempMinor 1 $R6
            StrCmp $R7 "" clean_minor_done 0
            ; Garder seulement les chiffres
            StrCmp $R7 "0" add_digit 0
            StrCmp $R7 "1" add_digit 0
            StrCmp $R7 "2" add_digit 0
            StrCmp $R7 "3" add_digit 0
            StrCmp $R7 "4" add_digit 0
            StrCmp $R7 "5" add_digit 0
            StrCmp $R7 "6" add_digit 0
            StrCmp $R7 "7" add_digit 0
            StrCmp $R7 "8" add_digit 0
            StrCmp $R7 "9" add_digit 0
            Goto clean_minor_done
            add_digit:
                StrCpy $R5 "$R5$R7"
                IntOp $R6 $R6 + 1
                Goto clean_minor_loop
        clean_minor_done:
            StrCpy $TempMinor $R5

        ; Comparer major > MIN_PYTHON_MAJOR ?
        IntCmp $TempMajor ${MIN_PYTHON_MAJOR} check_minor version_too_old version_ok

        check_minor:
            ; major == MIN_PYTHON_MAJOR, comparer minor
            IntCmp $TempMinor ${MIN_PYTHON_MINOR} version_ok version_too_old version_ok

        version_too_old:
            StrCpy $VersionOK 0
            Return

        version_ok:
            StrCpy $VersionOK 1
            Return
FunctionEnd

; ---------------------------------------------------------------------------
;  TryPy0p
;  Strategie 1 : utiliser "py -0p" pour enumerer les versions Python
;  Sortie : $PythonExe contient le chemin si trouve, sinon vide
; ---------------------------------------------------------------------------
Function TryPy0p
    DetailPrint "Strategie 1 : recherche via py -0p (lanceur Windows)..."

    ; Executer py -0p et rediriger vers un fichier temporaire
    nsExec::ExecToStack 'cmd /c py -0p > "$TEMP\py0p.txt" 2>NUL'
    Pop $R0  ; exit code
    Pop $R1  ; output (vide car redirige)

    ; Si py n'existe pas, exit code != 0
    IntCmp $R0 0 py_found py_not_found py_not_found

    py_not_found:
        DetailPrint "  Lanceur py non disponible."
        Delete "$TEMP\py0p.txt"
        Return

    py_found:
        ; Ouvrir le fichier et parcourir les lignes
        FileOpen $R2 "$TEMP\py0p.txt" r
        ${If} $R2 == ""
            DetailPrint "  Impossible d'ouvrir le fichier temporaire."
            Return
        ${EndIf}

        read_line_loop:
            FileRead $R2 $TempLine
            StrCmp $TempLine "" end_of_file 0

            ; Appeler la fonction d'extraction
            Call ExtractVersionFromLine

            ; Verifier si on a trouve une version
            StrCmp $TempVersion "" read_line_loop 0

            ; Comparer la version
            Call CompareVersionToMinimum
            IntCmp $VersionOK 1 check_path read_line_loop read_line_loop

            check_path:
                ; Verifier que le chemin existe
                StrCmp $TempPath "" read_line_loop 0
                IfFileExists $TempPath found_valid_python read_line_loop

            found_valid_python:
                DetailPrint "  Python $TempVersion detecte : $TempPath"
                StrCpy $PythonExe $TempPath
                FileClose $R2
                Delete "$TEMP\py0p.txt"
                Return

        end_of_file:
            FileClose $R2
            Delete "$TEMP\py0p.txt"
            DetailPrint "  Aucune version compatible trouvee via py -0p."
            Return
FunctionEnd

; ---------------------------------------------------------------------------
;  TryPythonInPath
;  Strategie 2 : tester "python --version" dans le PATH
;  Sortie : $PythonExe = "python" si trouve, sinon inchange
; ---------------------------------------------------------------------------
Function TryPythonInPath
    DetailPrint "Strategie 2 : recherche de python dans le PATH..."

    nsExec::ExecToStack 'cmd /c python --version 2>&1'
    Pop $R0  ; exit code
    Pop $TempLine  ; output "Python X.Y.Z"

    IntCmp $R0 0 python_in_path python_not_in_path python_not_in_path

    python_not_in_path:
        DetailPrint "  python non trouve dans le PATH."
        Return

    python_in_path:
        ; Extraire la version
        Call ExtractVersionFromPythonOutput
        StrCmp $TempVersion "" python_not_in_path 0

        ; Comparer
        Call CompareVersionToMinimum
        IntCmp $VersionOK 1 python_path_ok python_not_in_path python_not_in_path

        python_path_ok:
            DetailPrint "  Python $TempVersion detecte dans le PATH."
            StrCpy $PythonExe "python"
            Return
FunctionEnd

; ---------------------------------------------------------------------------
;  TryScanStandardDirs
;  Strategie 3 : scanner les dossiers d'installation standards
;  Sortie : $PythonExe contient le chemin si trouve, sinon inchange
; ---------------------------------------------------------------------------
Function TryScanStandardDirs
    DetailPrint "Strategie 3 : scan des dossiers d'installation standards..."

    ; Liste des racines a scanner :
    ; 1. $LOCALAPPDATA\Programs\Python\Python3*
    ; 2. $PROGRAMFILES\Python3*
    ; 3. $PROGRAMFILES64\Python3*

    ; --- Racine 1 : LOCALAPPDATA ---
    StrCpy $R0 "$LOCALAPPDATA\Programs\Python"
    IfFileExists "$R0\*.*" scan_localappdata skip_localappdata

    scan_localappdata:
        DetailPrint "  Scan de $R0..."
        FindFirst $R1 $R2 "$R0\Python3*"
        ${If} $R1 != ""
            scan_localappdata_loop:
                StrCmp $R2 "" scan_localappdata_done 0
                StrCmp $R2 "." scan_localappdata_next 0
                StrCmp $R2 ".." scan_localappdata_next 0

                ; Verifier si c'est un dossier Python3xx valide
                StrCpy $R3 "$R0\$R2\python.exe"
                IfFileExists $R3 test_localappdata_python scan_localappdata_next

                test_localappdata_python:
                    Call TestPythonExe
                    IntCmp $VersionOK 1 found_in_localappdata scan_localappdata_next scan_localappdata_next

                found_in_localappdata:
                    DetailPrint "  Python $TempVersion detecte : $R3"
                    StrCpy $PythonExe $R3
                    FindClose $R1
                    Return

                scan_localappdata_next:
                    FindNext $R1 $R2
                    Goto scan_localappdata_loop

            scan_localappdata_done:
                FindClose $R1
        ${EndIf}

    skip_localappdata:

    ; --- Racine 2 : PROGRAMFILES ---
    StrCpy $R0 "$PROGRAMFILES"
    IfFileExists "$R0\*.*" scan_programfiles skip_programfiles

    scan_programfiles:
        DetailPrint "  Scan de $R0..."
        FindFirst $R1 $R2 "$R0\Python3*"
        ${If} $R1 != ""
            scan_programfiles_loop:
                StrCmp $R2 "" scan_programfiles_done 0
                StrCmp $R2 "." scan_programfiles_next 0
                StrCmp $R2 ".." scan_programfiles_next 0

                StrCpy $R3 "$R0\$R2\python.exe"
                IfFileExists $R3 test_programfiles_python scan_programfiles_next

                test_programfiles_python:
                    Call TestPythonExe
                    IntCmp $VersionOK 1 found_in_programfiles scan_programfiles_next scan_programfiles_next

                found_in_programfiles:
                    DetailPrint "  Python $TempVersion detecte : $R3"
                    StrCpy $PythonExe $R3
                    FindClose $R1
                    Return

                scan_programfiles_next:
                    FindNext $R1 $R2
                    Goto scan_programfiles_loop

            scan_programfiles_done:
                FindClose $R1
        ${EndIf}

    skip_programfiles:

    ; --- Racine 3 : PROGRAMFILES64 (si different de PROGRAMFILES) ---
    StrCmp $PROGRAMFILES64 $PROGRAMFILES done_scanning 0
    StrCpy $R0 "$PROGRAMFILES64"
    IfFileExists "$R0\*.*" scan_programfiles64 done_scanning

    scan_programfiles64:
        DetailPrint "  Scan de $R0..."
        FindFirst $R1 $R2 "$R0\Python3*"
        ${If} $R1 != ""
            scan_programfiles64_loop:
                StrCmp $R2 "" scan_programfiles64_done 0
                StrCmp $R2 "." scan_programfiles64_next 0
                StrCmp $R2 ".." scan_programfiles64_next 0

                StrCpy $R3 "$R0\$R2\python.exe"
                IfFileExists $R3 test_programfiles64_python scan_programfiles64_next

                test_programfiles64_python:
                    Call TestPythonExe
                    IntCmp $VersionOK 1 found_in_programfiles64 scan_programfiles64_next scan_programfiles64_next

                found_in_programfiles64:
                    DetailPrint "  Python $TempVersion detecte : $R3"
                    StrCpy $PythonExe $R3
                    FindClose $R1
                    Return

                scan_programfiles64_next:
                    FindNext $R1 $R2
                    Goto scan_programfiles64_loop

            scan_programfiles64_done:
                FindClose $R1
        ${EndIf}

    done_scanning:
        DetailPrint "  Aucune version compatible trouvee dans les dossiers standards."
        Return
FunctionEnd

; ---------------------------------------------------------------------------
;  TestPythonExe
;  Teste un executable Python et verifie sa version.
;  Entree : $R3 = chemin vers python.exe
;  Sortie : $TempVersion = version, $VersionOK = 1 si >= 3.12
; ---------------------------------------------------------------------------
Function TestPythonExe
    StrCpy $VersionOK 0
    StrCpy $TempVersion ""

    ; Executer python --version
    nsExec::ExecToStack 'cmd /c "$R3" --version 2>&1'
    Pop $R4  ; exit code
    Pop $TempLine  ; output

    IntCmp $R4 0 extract_test_version test_failed test_failed

    test_failed:
        Return

    extract_test_version:
        Call ExtractVersionFromPythonOutput
        StrCmp $TempVersion "" test_failed 0
        Call CompareVersionToMinimum
        Return
FunctionEnd

; ---------------------------------------------------------------------------
;  InstallPython312NSIS (phase 3bis, issue #60)
;  Portage de Install-Python312 (install_alchess.ps1 ~l.130-164).
;  Appelee UNIQUEMENT quand les 3 strategies de detection de SecPython
;  (#53/#54) n'ont rien trouve. Installe Python 3.12 via winget, puis
;  reutilise TryScanStandardDirs (strategie 3, phase 3) pour confirmer la
;  detection.
;
;  POURQUOI RE-SCAN plutot que rafraichir le PATH : apres un winget install,
;  le PATH mis a jour n'est ecrit que dans le registre (HKLM/HKCU\Environment).
;  Le process NSIS a capture SON PATH au demarrage et ne le verra jamais
;  changer. Reconstruire le PATH a la main (concat registre Machine + User)
;  est fragile. TryScanStandardDirs scanne directement
;  %LOCALAPPDATA%\Programs\Python\Python3* (ou winget installe par defaut en
;  scope utilisateur, l'installeur tournant en RequestExecutionLevel user) :
;  il trouve Python fraichement installe sans dependre du PATH du tout.
;
;  ELEVATION UAC : contrairement a vc_redist.x64.exe (phase 5), winget en
;  scope utilisateur ne demande normalement PAS d'elevation. On utilise donc
;  nsExec (et non ExecShell comme pour le VC++ redist) : nsExec attend
;  reellement la fin du process et recupere son vrai code de sortie, sans
;  Sleep fixe a deviner. ExecToLog (plutot qu'ExecToStack) affiche en plus la
;  progression de winget en direct, utile car le telechargement de Python peut
;  prendre un moment. HYPOTHESE NON VERIFIEE (Linux) : si un test VM revele que
;  winget demande malgre tout une elevation, il faudra le documenter plutot que
;  de forcer un correctif non teste.
;
;  Cette fonction Abort proprement (message clair + lien manuel) dans les 3
;  cas d'echec : winget absent, install ratee, installe-mais-non-detecte.
;  En cas de succes, $PythonExe contient le chemin (renseigne par
;  TryScanStandardDirs) et la fonction Return normalement.
; ---------------------------------------------------------------------------
Function InstallPython312NSIS
    DetailPrint "================================================"
    DetailPrint "Installation automatique de Python 3.12 via winget"
    DetailPrint "================================================"

    ; 1. Verifier que winget est disponible. cmd /c garantit un lancement
    ;    (cmd.exe existe toujours) : si winget est absent, cmd renvoie un code
    ;    non-zero (9009 = commande introuvable), qu'on teste ci-dessous.
    DetailPrint "Verification de la disponibilite de winget..."
    nsExec::ExecToStack 'cmd /c winget --version'
    Pop $R0  ; code de sortie
    Pop $R1  ; sortie (version winget si present)
    IntCmp $R0 0 winget_ok winget_absent winget_absent

    winget_absent:
        DetailPrint "================================================"
        DetailPrint "ECHEC : winget n'est pas disponible sur ce systeme."
        DetailPrint "================================================"
        DetailPrint "Installez Python 3.12 manuellement depuis :"
        DetailPrint "  https://www.python.org/downloads/release/python-3120/"
        DetailPrint "Cochez 'Add Python to PATH' pendant l'installation,"
        DetailPrint "puis relancez cet installeur."
        MessageBox MB_OK|MB_ICONSTOP "winget n'est pas disponible sur ce systeme.$\r$\n$\r$\nInstallez Python 3.12 manuellement depuis :$\r$\nhttps://www.python.org/downloads/release/python-3120/$\r$\n$\r$\nCochez 'Add Python to PATH' pendant l'installation, puis relancez cet installeur."
        Abort

    winget_ok:
        DetailPrint "  winget disponible."

        ; 2. Installer Python 3.12 via winget. ExecToLog affiche la progression
        ;    en direct dans les details (telechargement potentiellement long).
        DetailPrint "Installation de Python 3.12 via winget (le telechargement peut prendre un moment)..."
        nsExec::ExecToLog 'cmd /c winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements'
        Pop $R0  ; code de sortie (ExecToLog ne pousse que le code, pas la sortie)
        IntCmp $R0 0 winget_install_ok winget_install_fail winget_install_fail

    winget_install_fail:
        DetailPrint "================================================"
        DetailPrint "ECHEC : l'installation de Python via winget a echoue (code $R0)."
        DetailPrint "================================================"
        DetailPrint "Installez Python 3.12 manuellement depuis :"
        DetailPrint "  https://www.python.org/downloads/release/python-3120/"
        DetailPrint "puis relancez cet installeur."
        MessageBox MB_OK|MB_ICONSTOP "L'installation de Python via winget a echoue (code $R0).$\r$\n$\r$\nInstallez Python 3.12 manuellement depuis :$\r$\nhttps://www.python.org/downloads/release/python-3120/$\r$\n$\r$\npuis relancez cet installeur."
        Abort

    winget_install_ok:
        DetailPrint "  Installation winget terminee."

        ; 3. Re-scan des dossiers standards (strategie 3, reutilisation directe).
        ;    Aveugle au PATH : trouve Python fraichement installe sans bidouiller
        ;    de variable d'environnement (cf. commentaire d'en-tete).
        DetailPrint "Verification de la detection de Python fraichement installe..."
        Call TryScanStandardDirs
        StrCmp $PythonExe "" python_installed_not_detected python_install_success

    python_installed_not_detected:
        DetailPrint "================================================"
        DetailPrint "Python a ete installe mais n'est pas encore detecte."
        DetailPrint "================================================"
        DetailPrint "Redemarrez votre PC puis relancez cet installeur."
        MessageBox MB_OK|MB_ICONEXCLAMATION "Python 3.12 a ete installe mais n'est pas encore detecte par l'installeur.$\r$\n$\r$\nRedemarrez votre PC puis relancez cet installeur."
        Abort

    python_install_success:
        DetailPrint "  Python detecte apres installation : $PythonExe"
        Return
FunctionEnd

; ============================================================================
;  FONCTIONS UTILITAIRES POUR STOCKFISH (PHASE 4)
; ============================================================================

; ---------------------------------------------------------------------------
;  TestAvx2Support
;  Detecte si le CPU supporte AVX2 via IsProcessorFeaturePresent(40).
;  Equivalent de Test-Avx2Support dans install_alchess.ps1.
;  ATTENTION : ce test NE detecte PAS BMI2 (non fiable avant Windows 11 24H2).
;  Le test d'execution reel reste la seule methode robuste.
;  Sortie : $HasAvx2 = 1 si AVX2 present, 0 sinon
; ---------------------------------------------------------------------------
Function TestAvx2Support
    ; PF_AVX2_INSTRUCTIONS_AVAILABLE = 40
    System::Call "kernel32::IsProcessorFeaturePresent(i 40) i .r0"
    StrCpy $HasAvx2 $R0
FunctionEnd

; ---------------------------------------------------------------------------
;  DownloadStockfish
;  Telecharge une variante Stockfish via Inetc.
;  Entree : $R0 = URL, $R1 = label pour affichage
;  Sortie : $R2 = "OK" si succes, message d'erreur sinon
;           Fichier telecharge dans $TEMP\stockfish.zip
; ---------------------------------------------------------------------------
Function DownloadStockfish
    DetailPrint "Telechargement Stockfish ($R1)..."
    DetailPrint "  Source : $R0"
    inetc::get /caption "Telechargement Stockfish ($R1)" "$R0" "$TEMP\stockfish.zip" /end
    Pop $R2  ; "OK" ou message d'erreur
FunctionEnd

; ---------------------------------------------------------------------------
;  ProbeStockfish
;  Lance l'executable Stockfish avec "quit" en entree pour verifier qu'il
;  fonctionne sur ce CPU. Equivalent de Invoke-StockfishProbe dans le .ps1.
;
;  ATTENTION TIMEOUT : nsExec::ExecToStack attend indefiniment la fin du
;  process. Pour eviter un blocage, on passe "quit" via une redirection
;  stdin depuis un fichier temporaire (cmd /c < fichier). Si Stockfish
;  demarre normalement, il lit "quit" et quitte immediatement (exit code 0).
;  Si le binaire crashe (illegal instruction), le code de sortie est
;  0xC000001D (-1073741795).
;
;  Entree : $R0 = chemin vers stockfish.exe
;  Sortie : $R3 = code de sortie (0 = OK, -1073741795 = illegal instruction)
;
;  NOTE : contrairement au .ps1 qui utilisait Start-Process avec timeout
;  explicite (5s), NSIS n'a pas de timeout natif pour nsExec. Le risque
;  theorique de blocage est mitige par le fait que Stockfish lit toujours
;  stdin au demarrage (meme les variantes incompatibles crashent avant la
;  boucle UCI). Si un binaire ne reagit pas a "quit", l'installeur se
;  bloquerait — accepte pour l'instant, pas de meilleure solution NSIS.
; ---------------------------------------------------------------------------
Function ProbeStockfish
    ; Creer le fichier stdin avec "quit"
    FileOpen $R4 "$TEMP\sf_probe_in.txt" w
    FileWrite $R4 "quit$\r$\n"
    FileClose $R4

    ; Lancer Stockfish avec redirection stdin depuis le fichier
    ; La syntaxe cmd /c ... < file fonctionne avec nsExec
    nsExec::ExecToStack 'cmd /c "$R0" < "$TEMP\sf_probe_in.txt"'
    Pop $R3  ; exit code
    Pop $R5  ; output (ignore)

    ; Nettoyer le fichier temporaire
    Delete "$TEMP\sf_probe_in.txt"
FunctionEnd

; ---------------------------------------------------------------------------
;  CleanupStockfishVariant
;  Supprime la variante Stockfish en echec. Garde-fou : ne supprime que le
;  sous-dossier stockfish/, jamais engines/ entier (qui contient Maia/Rodent).
;  Equivalent du bloc "Remove-Item ... -ne (Resolve-Path $ENGINES_DIR)"
;  dans install_alchess.ps1.
;
;  Entree : $R0 = chemin vers stockfish.exe qui a echoue
; ---------------------------------------------------------------------------
Function CleanupStockfishVariant
    ; Determiner le dossier parent de l'exe
    ; L'exe est dans $EXEDIR\engines\stockfish\stockfish-xxx.exe
    ; On veut supprimer $EXEDIR\engines\stockfish\ mais JAMAIS $EXEDIR\engines\
    ; Strategie : supprimer uniquement $EXEDIR\${ENGINES_SUBDIR}\stockfish (chemin fixe)
    ; car c'est toujours le dossier d'extraction de l'asset officiel
    IfFileExists "$EXEDIR\${ENGINES_SUBDIR}\stockfish\*.*" do_cleanup skip_cleanup

    do_cleanup:
        DetailPrint "  Nettoyage du dossier stockfish echoue..."
        RMDir /r "$EXEDIR\${ENGINES_SUBDIR}\stockfish"
        Return

    skip_cleanup:
        ; L'exe etait peut-etre directement dans engines/ (cas anormal)
        ; Supprimer seulement l'exe, pas le dossier engines/ entier
        Delete "$R0"
        Return
FunctionEnd

; ---------------------------------------------------------------------------
;  TryStockfishVariant
;  Essaie d'installer une variante Stockfish : telecharge, extrait, teste.
;  Entree : $R0 = URL, $R1 = label (ex: "avx2", "sse41-popcnt", "x86-64 base")
;  Sortie : $StockfishOK = 1 si succes, 0 sinon
;
;  EXTRACTION ZIP (#56) : realisee via le plugin nsisunz (nsisunz::UnzipToLog),
;  installe dans /usr/share/nsis/Plugins/ (meme processus qu'Inetc en #51).
;  NSIS n'ayant pas de dezipage natif, ce plugin est requis pour extraire
;  l'asset Stockfish telecharge.
; ---------------------------------------------------------------------------
Function TryStockfishVariant
    StrCpy $StockfishOK 0

    ; 1. Telecharger
    Call DownloadStockfish
    StrCmp $R2 "OK" dl_ok dl_fail

    dl_fail:
        DetailPrint "  Echec telechargement ($R1) : $R2"
        Delete "$TEMP\stockfish.zip"
        Return

    dl_ok:
        DetailPrint "  Telechargement reussi."

        ; 2. Creer le dossier engines s'il n'existe pas
        IfFileExists "$EXEDIR\${ENGINES_SUBDIR}\*.*" extract_zip create_engines_dir

        create_engines_dir:
            CreateDirectory "$EXEDIR\${ENGINES_SUBDIR}"

        extract_zip:
            ; ============================================================
            ; Extraction ZIP via plugin nsisunz (installe systeme, #56)
            ; ============================================================
            ; NSIS n'a pas de dezipage natif. Le plugin nsisunz
            ; (nsisunz::UnzipToLog) est desormais installe dans
            ; /usr/share/nsis/Plugins/ (issue #56, meme processus qu'Inetc
            ; en #51). Choix nsisunz plutot que ZipDLL : origine zlib/NSIS,
            ; contrainte de licence moindre. AlChess etant sous GPL v3, les
            ; deux auraient convenu ; nsisunz privilegie par prudence.
            ; ============================================================
            DetailPrint "  Extraction..."
            nsisunz::UnzipToLog "$TEMP\stockfish.zip" "$EXEDIR\${ENGINES_SUBDIR}"
            Pop $R6  ; "success" ou message d'erreur
            StrCmp $R6 "success" extract_ok extract_fail

        extract_fail:
            DetailPrint "  Echec extraction : $R6"
            Delete "$TEMP\stockfish.zip"
            Return

        extract_ok:
            Delete "$TEMP\stockfish.zip"

        ; 3. Trouver l'executable (apres extraction)
        ; L'asset Stockfish s'extrait dans stockfish/stockfish-windows-x86-64[-variante].exe
        FindFirst $R6 $R7 "$EXEDIR\${ENGINES_SUBDIR}\stockfish\stockfish*.exe"
        StrCmp $R6 "" no_exe_found found_exe

        no_exe_found:
            DetailPrint "  Aucun executable trouve apres extraction."
            FindClose $R6
            ; A ce stade $R0 contient ENCORE l'URL de telechargement (jamais
            ; reassignee, car aucun exe n'a ete trouve — la reaffectation en
            ; chemin de fichier n'a lieu que dans found_exe). Or
            ; CleanupStockfishVariant fait "Delete $R0" dans sa branche
            ; skip_cleanup : sans ce reset, il tenterait de supprimer une
            ; chaine d'URL (echoue silencieusement, sans effet utile). On vide
            ; $R0 pour neutraliser ce cas. (bug latent releve en relecture #55,
            ; corrige #56)
            StrCpy $R0 ""
            Call CleanupStockfishVariant
            Return

        found_exe:
            StrCpy $R0 "$EXEDIR\${ENGINES_SUBDIR}\stockfish\$R7"
            FindClose $R6
            DetailPrint "  Executable trouve : $R0"

        ; 4. Test d'execution reel (probe)
        DetailPrint "  Test d'execution..."
        Call ProbeStockfish

        ; Verifier le code de sortie
        IntCmp $R3 0 probe_ok check_illegal check_illegal

        check_illegal:
            IntCmp $R3 ${EXIT_ILLEGAL_INSTRUCTION} probe_illegal probe_other probe_other

        probe_illegal:
            DetailPrint "  ECHEC : illegal instruction (CPU incompatible)."
            DetailPrint "  Code de sortie : $R3"
            Call CleanupStockfishVariant
            Return

        probe_other:
            ; Autre code de sortie non-zero : peut etre une erreur mineure
            ; On considere que si ce n'est pas "illegal instruction", ca passe
            ; (meme comportement que le .ps1 qui ne testait que -1073741795)
            DetailPrint "  Code de sortie : $R3 (non fatal, on continue)"

        probe_ok:
            DetailPrint "  Stockfish ($R1) installe et fonctionnel !"
            StrCpy $StockfishOK 1
            Return
FunctionEnd

; ============================================================================
;  SECTIONS DE CONFIGURATION
;  Toutes co-localisees sur $EXEDIR. Remplies progressivement (phases 3-5).
; ============================================================================

SectionGroup "Configuration AlChess" SecGroupConfig

    ; -- Phase 3 : portage de Get-Python312 / Install-Python312 --------------
    Section "Verification Python" SecPython
        DetailPrint "Racine de configuration (EXEDIR) : $EXEDIR"
        DetailPrint "================================================"
        DetailPrint "Recherche de Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+..."
        DetailPrint "================================================"

        ; Initialiser la variable resultat
        StrCpy $PythonExe ""

        ; Strategie 1 : py -0p
        Call TryPy0p
        StrCmp $PythonExe "" try_path found_python

        try_path:
            ; Strategie 2 : python dans le PATH
            Call TryPythonInPath
            StrCmp $PythonExe "" try_scan found_python

        try_scan:
            ; Strategie 3 : scan des dossiers standards
            Call TryScanStandardDirs
            StrCmp $PythonExe "" no_python found_python

        found_python:
            DetailPrint "================================================"
            DetailPrint "Python detecte : $PythonExe"
            DetailPrint "================================================"
            DetailPrint "  venv cible : $EXEDIR\${VENV_SUBDIR}"
            Goto end_python_section

        no_python:
            DetailPrint "================================================"
            DetailPrint "AUCUN Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ detecte."
            DetailPrint "================================================"
            DetailPrint "Tentative d'installation automatique via winget (phase 3bis, #60)..."

            ; Phase 3bis (#60) : installer Python automatiquement au lieu de se
            ; contenter d'un message d'echec. InstallPython312NSIS gere seule les
            ; cas d'echec (winget absent, install ratee, non detecte apres
            ; install) : message clair + lien manuel + Abort propre. Si elle
            ; Return, l'install a reussi ET $PythonExe est renseigne (via le
            ; re-scan TryScanStandardDirs).
            Call InstallPython312NSIS

            DetailPrint "================================================"
            DetailPrint "Python installe automatiquement avec succes : $PythonExe"
            DetailPrint "================================================"
            DetailPrint "  venv cible : $EXEDIR\${VENV_SUBDIR}"

        end_python_section:
    SectionEnd

    ; -- Phase 4 : portage de Install-Stockfish (cascade CPU) ----------------
    ; Equivalent de Install-Stockfish dans install_alchess.ps1 (issue #49).
    ;
    ; Cascade de variantes, de la plus rapide a la plus compatible :
    ;   avx2 -> sse41-popcnt -> base (x86-64)
    ; On ne garde que la premiere qui s'execute sans crasher (illegal instr).
    ;
    ; EXTRACTION ZIP (#56) : via plugin nsisunz, installe dans
    ; /usr/share/nsis/Plugins/ (meme processus qu'Inetc en #51).
    ; La chaine complete (telechargement Inetc + extraction nsisunz + probe)
    ; reste a valider en execution reelle sur VM Windows.
    Section "Installation Stockfish" SecStockfish
        DetailPrint "================================================"
        DetailPrint "Installation de Stockfish"
        DetailPrint "================================================"
        DetailPrint "  dossier moteurs : $EXEDIR\${ENGINES_SUBDIR}"

        ; Initialiser le flag de succes
        StrCpy $StockfishOK 0

        ; Verifier si Stockfish est deja present
        FindFirst $R8 $R9 "$EXEDIR\${ENGINES_SUBDIR}\stockfish\stockfish*.exe"
        StrCmp $R8 "" check_avx2 already_present

        already_present:
            FindClose $R8
            DetailPrint "Stockfish deja present : $EXEDIR\${ENGINES_SUBDIR}\stockfish\$R9"
            DetailPrint "Installation sautee."
            StrCpy $StockfishOK 1
            Goto end_stockfish

        check_avx2:
            FindClose $R8

            ; Test AVX2 (filtre rapide, non decisif pour BMI2)
            Call TestAvx2Support
            IntCmp $HasAvx2 1 try_avx2 skip_avx2 skip_avx2

        try_avx2:
            DetailPrint "AVX2 detecte — tentative variante avx2..."
            StrCpy $R0 "${SF_URL_AVX2}"
            StrCpy $R1 "avx2"
            Call TryStockfishVariant
            IntCmp $StockfishOK 1 end_stockfish try_sse41 try_sse41

        skip_avx2:
            DetailPrint "AVX2 non detecte — variante avx2 ignoree."

        try_sse41:
            DetailPrint "Tentative variante sse41-popcnt..."
            StrCpy $R0 "${SF_URL_SSE41}"
            StrCpy $R1 "sse41-popcnt"
            Call TryStockfishVariant
            IntCmp $StockfishOK 1 end_stockfish try_base try_base

        try_base:
            DetailPrint "Tentative variante base (x86-64)..."
            StrCpy $R0 "${SF_URL_BASE}"
            StrCpy $R1 "x86-64 base"
            Call TryStockfishVariant
            IntCmp $StockfishOK 1 end_stockfish all_failed all_failed

        all_failed:
            DetailPrint "================================================"
            DetailPrint "ECHEC : aucune variante Stockfish fonctionnelle."
            DetailPrint "================================================"
            DetailPrint "Telechargez Stockfish manuellement depuis :"
            DetailPrint "  https://stockfishchess.org/download/"
            DetailPrint "et placez l'executable dans le dossier engines\"

        end_stockfish:
            DetailPrint "================================================"
    SectionEnd

    ; -- Phase 5 : portage de Install-VCRedist (issue #57) --------------------
    ; Equivalent de Install-VCRedist dans install_alchess.ps1.
    ;
    ; Le runtime Visual C++ est requis par lc0 (moteur Maia). L'installeur
    ; vc_redist.x64.exe porte un manifeste requireAdministrator. Contrairement
    ; a nsExec::ExecToStack (utilise pour Stockfish), qui passe par CreateProcess
    ; et NE declenche PAS l'elevation UAC, ExecShell passe par ShellExecuteEx
    ; et DECLENCHE correctement l'invite UAC pour un exe avec ce manifeste.
    ;
    ; LIMITE ACCEPTEE : ExecShell ne permet pas d'attendre la fin du process
    ; ni de recuperer son code de sortie nativement. Un plugin type
    ; "ExecShellWaitEx" ou "ShellExecAsUser" n'est pas installe par defaut.
    ; Alternative retenue : lancer l'installeur, attendre un delai fixe (5s),
    ; puis verifier la presence de MSVCP140.dll pour confirmer le succes.
    ; C'est moins precis qu'un code de sortie, mais suffisant pour notre cas
    ; d'usage (install silent d'un runtime officiel Microsoft).
    ;
    ; SIMPLIFICATION VS .PS1 : le test de connexion prealable (Test-Connection)
    ; est omis. Si le telechargement Inetc echoue, on affiche directement le
    ; message d'avertissement (equivalent au cas "pas de connexion" du .ps1).
    ; Resultat fonctionnellement identique, code plus simple.
    Section "Runtime Visual C++" SecVCRedist
        DetailPrint "================================================"
        DetailPrint "Runtime Visual C++ (requis pour Maia)"
        DetailPrint "================================================"

        ; Initialiser le flag
        StrCpy $VCRedistOK 0

        ; 1. Verifier si deja present ($SYSDIR = $env:SystemRoot\System32)
        IfFileExists "$SYSDIR\MSVCP140.dll" vcredist_present vcredist_needed

        vcredist_present:
            DetailPrint "Runtime Visual C++ deja installe."
            StrCpy $VCRedistOK 1
            Goto end_vcredist

        vcredist_needed:
            DetailPrint "Runtime Visual C++ non detecte — telechargement..."

            ; 2. Telecharger via Inetc (meme methode que Stockfish)
            DetailPrint "  Source : ${VCREDIST_URL}"
            inetc::get /caption "Telechargement Visual C++ Runtime" "${VCREDIST_URL}" "$TEMP\vc_redist.x64.exe" /end
            Pop $R0  ; "OK" ou message d'erreur

            StrCmp $R0 "OK" vcredist_dl_ok vcredist_dl_fail

        vcredist_dl_fail:
            ; Echec telechargement : message equivalent au .ps1 (pas de connexion)
            DetailPrint "Echec du telechargement : $R0"
            DetailPrint "================================================"
            DetailPrint "AVERTISSEMENT : Le runtime Visual C++ n'a pas pu"
            DetailPrint "etre telecharge. Le moteur Maia (lc0) ne fonctionnera"
            DetailPrint "pas sans ce runtime."
            DetailPrint ""
            DetailPrint "Telechargez-le manuellement depuis :"
            DetailPrint "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
            DetailPrint ""
            DetailPrint "Stockfish et les autres modes fonctionneront normalement."
            DetailPrint "================================================"
            ; Pas de MessageBox ici : l'echec de telechargement n'est pas bloquant
            ; (meme comportement que le .ps1 qui continue sans Maia)
            Goto end_vcredist

        vcredist_dl_ok:
            DetailPrint "  Telechargement reussi."
            DetailPrint "  Installation du runtime (invite UAC attendue)..."

            ; ================================================================
            ; POINT CRITIQUE : ELEVATION UAC
            ; ================================================================
            ; vc_redist.x64.exe porte un manifeste requireAdministrator.
            ; nsExec::ExecToStack (utilise pour Stockfish) passe par CreateProcess
            ; qui NE declenche PAS l'elevation automatique -> erreur.
            ; ExecShell passe par ShellExecuteEx qui DECLENCHE l'UAC.
            ;
            ; Syntaxe : ExecShell "open" "chemin" "parametres" SW_HIDE
            ; On passe /install /quiet /norestart comme le .ps1.
            ;
            ; LIMITE : ExecShell n'attend pas la fin du process. On ne peut pas
            ; recuperer le code de sortie (0=succes, 3010=redemarrage requis).
            ; Alternative : attendre un delai fixe puis verifier MSVCP140.dll.
            ; ================================================================
            ExecShell "open" "$TEMP\vc_redist.x64.exe" "/install /quiet /norestart" SW_HIDE

            ; Remplace le Sleep 5000 fixe par un polling : verifie MSVCP140.dll
            ; toutes les 2 secondes, jusqu'a 60 secondes au total. Laisse le temps
            ; a l'utilisateur de voir l'invite UAC et de cliquer "Oui" avant de
            ; conclure a un echec (le Sleep fixe de 5s etait beaucoup trop court
            ; pour une interaction humaine, confirme par test VM reel - issue #57).
            DetailPrint "  Installation en cours (repondez a l'invite de securite Windows si elle apparait)..."
            StrCpy $R1 0  ; compteur de tentatives (30 x 2s = 60s max)
        vcredist_poll_loop:
            Sleep 2000
            IntOp $R1 $R1 + 1
            IfFileExists "$SYSDIR\MSVCP140.dll" vcredist_poll_done vcredist_poll_continue
        vcredist_poll_continue:
            ; Tant que le compteur < 30, on continue le polling ; sinon timeout.
            IntCmp $R1 30 vcredist_poll_done vcredist_poll_loop vcredist_poll_done

        vcredist_poll_done:
            ; Nettoyer le fichier telecharge
            Delete "$TEMP\vc_redist.x64.exe"

            ; Verification finale via la presence de MSVCP140.dll
            IfFileExists "$SYSDIR\MSVCP140.dll" vcredist_install_ok vcredist_install_fail

        vcredist_install_ok:
            DetailPrint "Runtime Visual C++ installe avec succes."
            StrCpy $VCRedistOK 1
            Goto end_vcredist

        vcredist_install_fail:
            ; Echec d'installation : message + question Y/N comme le .ps1
            DetailPrint "================================================"
            DetailPrint "ECHEC : Le runtime Visual C++ n'a pas pu etre installe."
            DetailPrint ""
            DetailPrint "Le moteur Maia (lc0) ne fonctionnera pas sans ce runtime."
            DetailPrint "Stockfish et les autres modes fonctionneront normalement."
            DetailPrint ""
            DetailPrint "Pour corriger plus tard, telechargez et installez :"
            DetailPrint "  https://aka.ms/vs/17/release/vc_redist.x64.exe"
            DetailPrint "================================================"

            ; MessageBox Y/N : equivalent de Read-Host "Continue? (Y/N)" du .ps1
            MessageBox MB_YESNO|MB_ICONQUESTION "L'installation du runtime Visual C++ a echoue.$\r$\n$\r$\nLe moteur Maia ne fonctionnera pas sans ce runtime.$\r$\nStockfish et les autres modes fonctionneront normalement.$\r$\n$\r$\nContinuer l'installation sans le support Maia ?" IDYES vcredist_continue IDNO vcredist_abort

        vcredist_abort:
            DetailPrint "Installation annulee par l'utilisateur."
            Abort

        vcredist_continue:
            DetailPrint "Poursuite de l'installation sans le support Maia."

        end_vcredist:
            DetailPrint "================================================"
    SectionEnd

SectionGroupEnd

; ============================================================================
;  SECTION FINALE — RACCOURCI BUREAU + MESSAGE DE FIN (phase 6, issue #58)
; ============================================================================
;  Portage du bloc COM WScript.Shell de install_alchess.ps1 (~l.285-302).
;  Le raccourci cible TOUJOURS 2-Lancer_AlChess.bat (jamais le .ps1
;  directement) : le .bat encapsule l'appel PowerShell avec -ExecutionPolicy
;  Bypass, ce qui evite le blocage de policy au double-clic d'un .ps1.
;
;  NSIS a une instruction native (CreateShortcut) bien plus simple que le COM
;  du .ps1. En cas d'echec (dossier bureau protege, droits, etc.), on affiche
;  un avertissement NON bloquant — comme le .ps1 qui catch l'erreur COM sans
;  arreter l'installation.
; ============================================================================
Section "Raccourci bureau" SecShortcut
    DetailPrint "================================================"
    DetailPrint "Creation du raccourci bureau"
    DetailPrint "================================================"

    ; Reinitialiser le flag d'erreur avant CreateShortcut pour que IfErrors
    ; ne remonte pas une erreur laissee par une instruction anterieure.
    ClearErrors
    CreateShortcut "$DESKTOP\AlChess.lnk" "$EXEDIR\2-Lancer_AlChess.bat" "" \
        "" "" SW_SHOWNORMAL "" "Launch AlChess"
    IfErrors shortcut_failed shortcut_ok

    shortcut_failed:
        DetailPrint "AVERTISSEMENT : impossible de creer le raccourci bureau."
        DetailPrint "  Vous pourrez lancer AlChess directement via :"
        DetailPrint "  $EXEDIR\2-Lancer_AlChess.bat"
        Goto end_shortcut

    shortcut_ok:
        DetailPrint "Raccourci cree : $DESKTOP\AlChess.lnk"

    end_shortcut:
        ; -- Message de fin, coherent avec install_alchess.ps1 -------------
        DetailPrint "================================================"
        DetailPrint "Configuration d'AlChess terminee."
        DetailPrint "================================================"
        DetailPrint "Pour lancer AlChess :"
        DetailPrint "  - double-cliquez le raccourci AlChess sur le bureau, OU"
        DetailPrint "  - double-cliquez 2-Lancer_AlChess.bat dans ce dossier."
        DetailPrint "AlChess ouvrira votre navigateur sur l'interface web."
        DetailPrint "================================================"
SectionEnd
