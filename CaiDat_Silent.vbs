' FIX v3.65: Chay CaiDat_MagicVoice.bat HOAN TOAN AN (khong hien cua so console
' nao ca) - dung boi installer de qua trinh cai dat (5-20 phut) nhin chuyen
' nghiep, khong lo cua so DOS den ra man hinh.
' LUU Y: neu CaiDat_MagicVoice.bat can quyen Admin, hop thoai UAC cua Windows
' van se hien binh thuong (khong the/khong nen an - co che bao mat he thong).
' Neu co loi (vd tai Python that bai), CaiDat_MagicVoice.bat da duoc sua de
' hien MsgBox thong bao loi thay vi "pause" (tranh treo vinh vien khi an).
Set oShell = CreateObject("WScript.Shell")
strDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
oShell.Run """" & strDir & "CaiDat_MagicVoice.bat""", 0, True
