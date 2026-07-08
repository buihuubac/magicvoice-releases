' FIX v3.65: Hien MsgBox thong bao loi - dung boi CaiDat_MagicVoice.bat khi
' dang chay AN (hidden). Khong the dung "pause" trong .bat vi console dang
' bi an, khong ai bam phim duoc -> se treo vinh vien. File nay tach rieng de
' tranh loi long escape dau ngoac kep giua batch va VBScript (mshta inline).
' Cach dung: cscript //nologo _ShowError.vbs "Noi dung thong bao loi"
If WScript.Arguments.Count > 0 Then
    MsgBox WScript.Arguments(0), 48, "MagicVoice - Loi cai dat"
End If
