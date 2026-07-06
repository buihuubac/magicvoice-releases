Set oShell = CreateObject("WScript.Shell")
oShell.Run "py -3.11 """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\QuanLyTaiKhoan_GUI.py""", 0, False
