' MagicVoice TTS Studio - Launcher
Set oShell = CreateObject("WScript.Shell")
Set fso    = CreateObject("Scripting.FileSystemObject")
strDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Doc bien moi truong dung cach VBScript
Dim sLocal : sLocal = oShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
Dim sUser  : sUser  = oShell.ExpandEnvironmentStrings("%USERPROFILE%")

Dim PYW : PYW = ""
Dim paths(5)
paths(0) = sLocal & "\Programs\Python\Python311\pythonw.exe"
paths(1) = "C:\Python311\pythonw.exe"
paths(2) = "C:\Program Files\Python311\pythonw.exe"
paths(3) = sUser & "\AppData\Local\Programs\Python\Python311\pythonw.exe"
paths(4) = "C:\Users\Default\AppData\Local\Programs\Python\Python311\pythonw.exe"

Dim i
For i = 0 To 4
    If fso.FileExists(paths(i)) Then PYW = paths(i) : Exit For
Next

' Fallback: hoi py launcher
If PYW = "" Then
    On Error Resume Next
    Dim oExec
    Set oExec = oShell.Exec("py -3.11 -c ""import sys;print(sys.executable)""")
    Dim pyexe : pyexe = Trim(oExec.StdOut.ReadAll())
    On Error GoTo 0
    If pyexe <> "" Then
        PYW = Replace(pyexe, "python.exe", "pythonw.exe")
        If Not fso.FileExists(PYW) Then PYW = pyexe
    End If
End If

If PYW = "" Then
    MsgBox "Chua cai Python 3.11!" & Chr(13) & Chr(13) & _
           "Vui long chay CaiDat_MagicVoice.bat truoc.", _
           48, "MagicVoice TTS Studio"
    WScript.Quit
End If

' Chay app (an cua so CMD)
oShell.Run Chr(34) & PYW & Chr(34) & " " & Chr(34) & strDir & "magicvoice.py" & Chr(34), 0, False
