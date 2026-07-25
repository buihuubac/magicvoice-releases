@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "APP_VER=?"
for /f "usebackq tokens=* delims=" %%v in ("%~dp0version.txt") do (
    set "APP_VER=%%v"
    goto :ver_done
)
:ver_done

title MagicVoice TTS Studio - Cai Dat v%APP_VER%

echo.
echo  ================================================
echo    MagicVoice TTS Studio - Cai Dat Tu Dong v%APP_VER%
echo  ================================================
echo.

REM FIX v3.65 (13): BO check+re-elevate qua "net session"/Start-Process RunAs.
REM Ly do: cai dat vao {userappdata} (khong dung Program Files) va Python
REM duoc cai kieu per-user (InstallAllUsers=0) - KHONG can quyen Admin o buoc
REM nao ca. Re-elevate truoc day tao ra 1 PROCESS TACH RIENG (khong phai con
REM cua oShell.Run trong CaiDat_Silent.vbs) roi "exit /b" ngay - khien
REM CaiDat_Silent.vbs / [Run] cua Inno / wait-bat cua _do_update() tuong cai
REM dat DA XONG trong khi ban elevated van dang chay ngam that su - gay lech
REM pha (app tu mo lai qua som/2 lan trong luc dang update).

echo  [1/3] Tim Python 3.11...
set "PY311="

py -3.11 --version >nul 2>&1
if not errorlevel 1 (
    set "PY311=py -3.11"
    goto :py_found
)

for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "C:\Python311\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
) do (
    if exist %%~p (
        %%~p --version >nul 2>&1
        if not errorlevel 1 (
            set "PY311=%%~p"
            goto :py_found
        )
    )
)

echo  Chua co Python 3.11...
REM FIX v3.66 (3): BO HOAN TOAN kieu cai qua MSI installer (.exe bootstrap
REM cua python.org) - da XAC MINH THUC TE (khong phai ly thuyet) tren chinh
REM may dev: khi chay AN (hidden, giong dung cach CaiDat_Silent.vbs goi),
REM installer giao viec cho dich vu Windows Installer (msiexec) chay o
REM Session 0 (session he thong, tach biet khoi may dung) - va TREO VINH
REM VIEN o do, khong bao gio hoan tat, khong bao loi, khong timeout tu
REM nhien. Day chinh la nguyen nhan goc cua rat nhieu ca "bao khong tim
REM thay Python" lap di lap lai suot ca ngay - khong phai do mang, khong
REM phai do AV, khong phai do Python khac xung dot.
REM
REM Thay bang ban Python "embeddable" (python-3.11.9-embed-amd64.zip) -
REM CHI LA FILE NEN, giai nen thang vao thu muc, KHONG co installer, KHONG
REM dung MSI, KHONG bao gio can Session 0/Admin/UAC. Sau khi giai nen, bat
REM "import site" trong python311._pth (mac dinh tat) de site-packages/pip
REM hoat dong, roi bootstrap pip qua get-pip.py (dong goi san). Da test
REM THUC TE tren may dev: giai nen + cai pip + cai thu 1 package xong trong
REM vai giay, khong treo, khong loi.
set "PY311DIR=%LOCALAPPDATA%\Programs\Python\Python311"
if not exist "%~dp0_bundled\python-3.11.9-embed-amd64.zip" (
    echo  LOI: Thieu file Python dong goi san!
    if exist "%~dp0_ShowError.vbs" (
        cscript //nologo "%~dp0_ShowError.vbs" "Thieu file can thiet (python-3.11.9-embed-amd64.zip). Vui long tai lai bo cai dat MagicVoice day du, hoac lien he ho tro Zalo 0985 483 623."
    )
    exit /b 1
)

echo  Dang giai nen Python 3.11 (khong can cai dat, khong the treo)...
if not exist "%PY311DIR%" mkdir "%PY311DIR%" >nul 2>&1
powershell -NoProfile -Command "Expand-Archive -Path '%~dp0_bundled\python-3.11.9-embed-amd64.zip' -DestinationPath '%PY311DIR%' -Force" >nul 2>&1

if not exist "%PY311DIR%\python.exe" (
    echo  LOI: Giai nen Python that bai!
    if exist "%~dp0_ShowError.vbs" (
        cscript //nologo "%~dp0_ShowError.vbs" "Giai nen Python 3.11 that bai (co the do dia day hoac quyen ghi bi chan). Vui long kiem tra dung luong o dia, hoac lien he ho tro Zalo 0985 483 623."
    )
    exit /b 1
)

REM FIX v3.66 (4): ban Python "embeddable" KHONG co san tkinter (chi co
REM phan loi toi thieu) - MagicVoice dung tkinter cho TOAN BO giao dien
REM (kể ca man hinh splash dau tien). Thieu tkinter -> app crash NGAY LAP
REM TUC luc mo (bao "nhay 1 cai roi bien mat" - da gap thuc te tren may
REM khach). Giai nen them goi tkinter dong goi rieng (_tkinter.pyd,
REM tcl86t.dll, tk86t.dll, thu muc tkinter/, thu muc tcl/) - da test
REM THUC TE tren may dev, tkinter chay dung (TkVersion 8.6).
if exist "%~dp0_bundled\tkinter_bundle.zip" (
    echo  Dang giai nen tkinter (can cho giao dien app)...
    powershell -NoProfile -Command "Expand-Archive -Path '%~dp0_bundled\tkinter_bundle.zip' -DestinationPath '%PY311DIR%' -Force" >nul 2>&1
)

REM Bat "import site" (mac dinh bi comment trong ban embeddable) de pip va
REM site-packages hoat dong binh thuong.
powershell -NoProfile -Command "(Get-Content '%PY311DIR%\python311._pth') -replace '#import site','import site' | Set-Content '%PY311DIR%\python311._pth'" >nul 2>&1

echo  Dang cai pip...
"%PY311DIR%\python.exe" "%~dp0_bundled\get-pip.py" --no-warn-script-location >nul 2>&1

"%PY311DIR%\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo  LOI: Python vua giai nen khong chay duoc!
    if exist "%~dp0_ShowError.vbs" (
        cscript //nologo "%~dp0_ShowError.vbs" "Python 3.11 vua giai nen nhung khong chay duoc. Vui long lien he ho tro Zalo 0985 483 623 kem anh chup loi nay."
    )
    exit /b 1
)

REM Kiem tra tkinter chay duoc that su - day la thu vien BAT BUOC cho toan
REM bo giao dien app, thieu la app crash ngay khi mo (khong hien loi ro
REM rang, chi "nhay 1 cai roi mat").
"%PY311DIR%\python.exe" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo  LOI: tkinter khong chay duoc - giao dien app se khong mo duoc!
    if exist "%~dp0_ShowError.vbs" (
        cscript //nologo "%~dp0_ShowError.vbs" "Thieu thu vien giao dien (tkinter) - app se khong mo duoc man hinh. Vui long tai lai bo cai dat MagicVoice day du, hoac lien he ho tro Zalo 0985 483 623."
    )
    exit /b 1
)

set "PY311=%PY311DIR%\python.exe"
goto :py_found

:py_found
for /f "tokens=*" %%v in ('!PY311! --version 2^>^&1') do echo   Dung: %%v

REM FIX v3.66 (5): truoc day buoc bo sung tkinter CHI chay khi vua giai nen
REM Python moi tinh - neu Python DA CO SAN tu 1 lan cai TRUOC (truoc khi
REM em them tkinter vao ban dong goi), cac nhanh phat hien o tren (py
REM launcher / duong dan truc tiep) di thang toi day ma KHONG BAO GIO chay
REM qua doan bo sung tkinter - khach cai di cai lai bao nhieu lan cung
REM khong bao gio duoc sua, vi Python "co ve nhu OK" (--version chay duoc)
REM nhung thieu tkinter. Da xac nhan THUC TE qua error_log.txt cua khach:
REM "ModuleNotFoundError: No module named 'tkinter'". Gio kiem tra tkinter
REM O DAY - diem hoi tu CHUNG cua moi nhanh tim Python - neu thieu thi tu
REM dong bo sung ngay, bat ke Python co san hay moi cai.
!PY311! -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo   Thieu tkinter - dang tu dong bo sung...
    for /f "tokens=*" %%d in ('!PY311! -c "import sys; print(sys.prefix)" 2^>nul') do set "PY311DIR=%%d"
    if defined PY311DIR if exist "%~dp0_bundled\tkinter_bundle.zip" (
        powershell -NoProfile -Command "Expand-Archive -Path '%~dp0_bundled\tkinter_bundle.zip' -DestinationPath '!PY311DIR!' -Force" >nul 2>&1
        !PY311! -c "import tkinter" >nul 2>&1
        if not errorlevel 1 ( echo   Da bo sung tkinter thanh cong. )
    )
)

echo.
echo  [2/3] Chay Smart Installer (setup_helper.py)...
echo        (mat 5-20 phut tuy toc do mang va cau hinh GPU)
echo.
!PY311! "%~dp0setup_helper.py"
set "SETUP_CODE=%errorlevel%"

echo.
echo  [3/3] Tao shortcut Desktop...
REM FIX v3.66: TRUOC DAY shortcut tro vao Chay_MagicVoice.bat - file nay mo
REM 1 cua so console (DOS) den nhay len roi moi bien mat, nhin khong chuyen
REM nghiep. File Tao_Shortcut_Desktop.vbs (chay rieng, khach tu bam) da tro
REM DUNG vao MagicVoice.vbs (an cua so hoan toan, dung wscript.exe) - nhung
REM shortcut do CAI DAT TU DONG tao o day lai KHONG dong bo, tro sai vao
REM Chay_MagicVoice.bat. Ket qua: cai dat lan dau/cai lai qua CaiDat_MagicVoice.bat
REM se AM THAM lam khach quay lai ban launcher co console-flash cu. Gio tro
REM ve dung 1 muc tieu duy nhat: MagicVoice.vbs.
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\MagicVoice TTS Studio.lnk');$s.TargetPath='%~dp0MagicVoice.vbs';$s.WorkingDirectory='%~dp0';$s.IconLocation='%~dp0MagicVoice.ico';$s.Save()" >nul 2>&1
echo   Shortcut Desktop: OK

echo.
REM FIX v3.66 (audit 2026-07-24): TRUOC DAY xoa ".caidat_running" NGAY O DAY,
REM tuc TRUOC KHI kiem tra SETUP_CODE/retry o duoi - nghia la neu lan cai dau
REM that bai va phai retry toan bo setup_helper.py (co the mat THEM 5-20 phut
REM nua), lock DA BI XOA tu truoc trong suot khoang retry nay. Day chinh la
REM khoang thoi gian khach DE HOANG MANG/bam lai icon NHAT (thay "khong co gi
REM xay ra" du that ra dang retry ngam) - nhung luc do lock lai khong con bao
REM ve nua, MagicVoice.vbs se khong biet dang co tien trinh cai chay de chan
REM bam trung. Gio CHUYEN viec xoa lock xuong DUNG 2 diem thoat that su: dau
REM nhan :open_app (thanh cong) va nhanh loi ben duoi (that bai sau retry) -
REM lock ton tai SUOT toan bo thoi gian cai dat that su dang chay, ke ca retry.
REM FIX v3.66: TRUOC DAY, that bai (SETUP_CODE != 0) la HIEN POPUP LOI +
REM KHONG mo app - khach thay canh bao ngay sau khi cai xong, hoang mang du
REM thuc te nhieu truong hop van mo/dung duoc phan lon tinh nang (chi thieu
REM 1-2 goi phu). Dung y "that bai la bao loi cho khach" thay vi "tu tim
REM cach bo sung". Gio doi lai: (1) NEU CHUA XONG, tu dong CHAY LAI TOAN BO
REM setup_helper.py 1 LAN NUA am tham (khong popup) - nhieu loi la tam thoi
REM (mang chop nhoang, file dang bi khoa...) nen retry toan bo co co hoi
REM tu het that su; (2) DU sau retry van con thieu 1 vai goi PHU (khong
REM phai torch/torchaudio - 2 goi CHINH bat buoc de mo app), VAN CU MO APP
REM binh thuong - cac tinh nang thieu se tu bao/tu sua khi khach dung toi
REM (vd nut "Tai Model" da co san trong app). CHI that su khong mo app khi
REM torch/torchaudio (loi lan (1)) van thieu SAU CA retry - luc do app se
REM crash ngay khi mo nen khong mo con hon mo ra crash xau xi, va
REM magicvoice.py da co san co che TU SUA (goi setup_helper.py --repair-torch)
REM ngay trong lan mo app dau tien, khong can khach lam gi.
if "%SETUP_CODE%"=="0" goto :open_app

echo  Cai dat chua xong het - tu dong thu lai 1 lan nua (am tham)...
!PY311! "%~dp0setup_helper.py"
set "SETUP_CODE=%errorlevel%"

REM FIX v3.66: TRUOC DAY sau khi retry, code KHONG kiem tra lai SETUP_CODE
REM lan 2 - di thang xuong :open_app bat ke retry co thanh cong hay khong.
REM Neu ca 2 lan cai deu that bai, app van duoc mo trong tinh trang chac
REM chan hong. Gio kiem tra that bang cach doc "last_setup_fail.txt" - file
REM nay do CHINH tien trinh setup_helper.py tu ghi ra khi co goi cai loi
REM (KHONG goi lai "py"/python nao tu batch de kiem tra - da thu cach goi
REM lai truoc day va gay loi GIA tren may co nhieu ban Python/launcher).
set "TORCH_REALLY_MISSING="
if exist "%~dp0last_setup_fail.txt" (
    findstr /i "torch" "%~dp0last_setup_fail.txt" >nul 2>&1
    if not errorlevel 1 set "TORCH_REALLY_MISSING=1"
) else (
    REM Khong co file fail (vd setup_helper.py crash truoc khi kip ghi) -
    REM khong biet chac torch co on khong - an toan hon la KHONG mo app,
    REM giong dung y ban dau "chi mo khi chac chan on".
    if not "%SETUP_CODE%"=="0" set "TORCH_REALLY_MISSING=1"
)

if not defined TORCH_REALLY_MISSING goto :open_app

echo  LOI: torch/torchaudio van chua cai duoc sau khi da thu lai.
if exist "%~dp0.caidat_running" del /f "%~dp0.caidat_running" >nul 2>&1
if exist "%~dp0_ShowError.vbs" (
    cscript //nologo "%~dp0_ShowError.vbs" "Cai dat chua hoan tat: thieu thu vien PyTorch bat buoc (torch/torchaudio) du da thu lai. Vui long kiem tra mang internet roi chay lai CaiDat_MagicVoice.bat, hoac lien he ho tro Zalo 0985 483 623 kem file install_log.txt."
)
exit /b 1

:open_app
if exist "%~dp0.caidat_running" del /f "%~dp0.caidat_running" >nul 2>&1
echo  ================================================
echo    Dang mo MagicVoice TTS Studio...
echo  ================================================
echo.
timeout /t 2 /nobreak >nul
REM FIX v3.65: goi qua MagicVoice.vbs (wscript, an cua so hoan toan) thay
REM vi Chay_MagicVoice.bat truc tiep - mo .bat luon nhay 1 cua so den
REM (console host) du chay xong rat nhanh, nhin thieu chuyen nghiep luc
REM vua cai xong.
start "" wscript.exe "%~dp0MagicVoice.vbs"
exit /b 0
