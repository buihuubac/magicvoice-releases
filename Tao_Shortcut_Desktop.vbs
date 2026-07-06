Set oWS = WScript.CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Shortcut tren Desktop
sLink = oWS.SpecialFolders("Desktop") & "\MagicVoice TTS Studio.lnk"
Set oLink = oWS.CreateShortcut(sLink)
oLink.TargetPath = strDir & "MagicVoice.vbs"
oLink.WorkingDirectory = Left(strDir, Len(strDir)-1)
If fso.FileExists(strDir & "MagicVoice.ico") Then
    oLink.IconLocation = strDir & "MagicVoice.ico"
End If
oLink.Description = "MagicVoice TTS Studio v2.1"
oLink.WindowStyle = 7
oLink.Save

MsgBox "Da tao shortcut 'MagicVoice TTS Studio' tren Desktop!", 64, "MagicVoice"
