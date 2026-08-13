' Lance 2-Lancer_AlChess.bat sans afficher de fenetre console.
' Le log applicatif va deja dans alchess_log.txt, la console est inutile
' en usage normal.

Dim objShell, objFSO, strFolder, strBat

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strFolder = objFSO.GetParentFolderName(WScript.ScriptFullName)
strBat = strFolder & "\2-Lancer_AlChess.bat"

objShell.Run """" & strBat & """", 0, False
