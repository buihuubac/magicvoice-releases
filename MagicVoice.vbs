' MagicVoice TTS Studio - Launcher
' FIX v3.66: bat On Error Resume Next cho CA FILE (khong chi 1 doan nho nhu
' truoc) - day la script CHAY AN (wscript, khong console), bat ky loi runtime
' nao khong bat duoc se hien popup "Windows Script Host" xau xi, ky thuat,
' lam khach hoang mang - DU app van mo duoc binh thuong qua duong khac (da
' xac nhan thuc te). Viec cua script nay chi la CO GANG mo app, khong phai
' noi can bao loi ky thuat cho khach thay.
On Error Resume Next
Set oShell = CreateObject("WScript.Shell")
Set fso    = CreateObject("Scripting.FileSystemObject")
strDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Doc bien moi truong dung cach VBScript
Dim sLocal : sLocal = oShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
Dim sUser  : sUser  = oShell.ExpandEnvironmentStrings("%USERPROFILE%")

Dim PYW : PYW = ""

' FIX v3.68 (BUG THAT SU nghiem trong, phat hien 2026-07-29): truoc day file
' nay TU DO TIM Python doc lap voi CaiDat_MagicVoice.bat (thu tu uu tien
' KHAC NHAU giua 2 file) - may khach co >=2 ban Python 3.11 co the bi cai
' thu vien vao 1 ban nhung mo app bang ban KHAC (chua cai gi), gay
' "No module named ..." du cai dat da bao thanh cong. Sua GOC: doc THANG
' file "python_used.txt" ma CaiDat_MagicVoice.bat da ghi lai duong dan
' CHINH XAC vua dung de cai thu vien - day la NGUON SU THAT DUY NHAT, uu
' tien tuyet doi truoc moi logic do tim khac ben duoi (chi dung lam du
' phong cho khach dang o ban cai cu chua co file nay).
Dim usedFile : usedFile = strDir & "python_used.txt"
If fso.FileExists(usedFile) Then
    Dim tsUsed, sUsedPath
    Set tsUsed = fso.OpenTextFile(usedFile, 1)
    sUsedPath = Trim(tsUsed.ReadLine())
    tsUsed.Close
    If sUsedPath <> "" And fso.FileExists(sUsedPath) Then PYW = sUsedPath
End If

Dim paths(5)
paths(0) = sLocal & "\Programs\Python\Python311\pythonw.exe"
paths(1) = "C:\Python311\pythonw.exe"
paths(2) = "C:\Program Files\Python311\pythonw.exe"
paths(3) = sUser & "\AppData\Local\Programs\Python\Python311\pythonw.exe"
paths(4) = "C:\Users\Default\AppData\Local\Programs\Python\Python311\pythonw.exe"

Dim i
If PYW = "" Then
    For i = 0 To 4
        If fso.FileExists(paths(i)) Then PYW = paths(i) : Exit For
    Next
End If

' Fallback: hoi py launcher
' (On Error Resume Next da bat toan cuc o dau file - khong can bat/tat lai
' o day nua, giu nguyen suot ca script)
If PYW = "" Then
    Dim oExec
    Set oExec = oShell.Exec("py -3.11 -c ""import sys;print(sys.executable)""")
    Dim pyexe : pyexe = Trim(oExec.StdOut.ReadAll())
    If pyexe <> "" Then
        PYW = Replace(pyexe, "python.exe", "pythonw.exe")
        If Not fso.FileExists(PYW) Then PYW = pyexe
    End If
End If

If PYW = "" Then
    ' FIX v3.66: truoc day den day la BO CUOC - hien MsgBox roi thoat,
    ' bat khach tu tay chay lai CaiDat_MagicVoice.bat. Nhung logic tim
    ' Python o day (VBS) YEU HON logic ben CaiDat_MagicVoice.bat (.bat da
    ' tim thay + dung Python OK de chay setup_helper.py xong xuoi, nhung
    ' toi luc mo app qua VBS nay lai "khong tim thay" do 2 noi kiem tra
    ' khac nhau) - khien khach gap dead-end vo ly ngay sau khi cai xong.
    ' Gio KHONG bo cuoc - tu dong goi lai CaiDat_MagicVoice.bat (co logic
    ' tim/cai Python day du hon) thay vi chi bao loi roi dung yen.
    '
    ' FIX v3.66 (audit): 2 van de phat sinh tu doan tu-dong-cai o tren da
    ' bi phat hien khi doc lai ky: (1) chay HOAN TOAN AM THAM (window=0,
    ' khong cho biet gi) trong luc cai dat that ra mat 5-20 phut - khach
    ' rat de tuong app "khong phan hoi gi" roi bam lai icon lan 2, tao ra
    ' 2 tien trinh CaiDat_MagicVoice.bat/setup_helper.py chay SONG SONG
    ' cung ghi/doc site-packages, co the lam hong moi truong Python giua
    ' chung; (2) khong dung chung lock file ".caidat_running" ma
    ' Chay_MagicVoice.bat da dung san cho dung muc dich nay. Gio: kiem
    ' tra lock truoc (neu dang co tien trinh cai chay roi thi CHI bao +
    ' thoat, khong chay tiep lan 2), tao lock ngay truoc khi chay, va
    ' hien 1 MsgBox ngan gon bao khach biet dang tu cai dat + can cho.
    ' (Lock se duoc CaiDat_MagicVoice.bat tu xoa khi xong, giong cach
    ' Chay_MagicVoice.bat da lam.)
    If fso.FileExists(strDir & ".caidat_running") Then
        MsgBox "MagicVoice dang tu dong cai dat o mot cua so khac (mat 5-20 phut)." _
             & vbCrLf & vbCrLf & "Vui long doi cho cai dat xong roi mo lai, khong bam nhieu lan.", _
               48, "MagicVoice - Dang cai dat"
        WScript.Quit
    End If
    oShell.Run "cmd /c echo. > " & Chr(34) & strDir & ".caidat_running" & Chr(34), 0, True
    MsgBox "Chua tim thay Python 3.11 - MagicVoice se TU DONG cai dat moi truong can thiet." _
         & vbCrLf & vbCrLf & "Qua trinh nay mat khoang 5-20 phut tuy toc do mang, mot cua so" _
         & vbCrLf & "cai dat se hien ra. Vui long KHONG tat may tinh trong luc cho." _
         & vbCrLf & vbCrLf & "Bam OK de bat dau.", 64, "MagicVoice - Tu dong cai dat"
    oShell.Run Chr(34) & strDir & "CaiDat_MagicVoice.bat" & Chr(34), 1, False
    WScript.Quit
End If

' Chay app (an cua so CMD)
oShell.Run Chr(34) & PYW & Chr(34) & " " & Chr(34) & strDir & "magicvoice.py" & Chr(34), 0, False
