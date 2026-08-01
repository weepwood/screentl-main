Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ws.Run """" & scriptDir & "\screenshot_weepwood.bat"" /start", 0, False
