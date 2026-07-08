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

echo  Chua co Python 3.11. Dang tai (khoang 25MB)...
set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PY_SETUP=%TEMP%\python311_setup.exe"
powershell -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;(New-Object Net.WebClient).DownloadFile('%PY_URL%','%PY_SETUP%')" >nul 2>&1
if not exist "%PY_SETUP%" (
    echo  LOI: Khong tai duoc Python!
    REM FIX v3.65: cua so cai dat se chay AN (hidden) tu MagicVoice.iss, "pause"
    REM se treo vinh vien khong ai thay/bam duoc. Dung _ShowError.vbs (hien
    REM duoc dung rieng, du console cha dang an) roi thoat luon.
    REM FIX v3.65 (11): kiem tra file ton tai truoc - khach dang o ban CU HON
    REM v3.65 khi update len co the CHUA co _ShowError.vbs (loi kien truc
    REM "cham 1 buoc" da ghi trong DEV_NOTES) - neu thieu, bo qua an toan
    REM thay vi crash "khong tim thay file .vbs".
    if exist "%~dp0_ShowError.vbs" (
        cscript //nologo "%~dp0_ShowError.vbs" "Khong tai duoc Python 3.11 (loi mang). Vui long kiem tra ket noi Internet roi chay lai file cai dat MagicVoice."
    ) else (
        echo  ^(Khong tim thay _ShowError.vbs - xem install_log.txt de biet chi tiet loi^)
    )
    exit /b 1
)
echo  Dang cai Python 3.11...
"%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
del /f "%PY_SETUP%" >nul 2>&1
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :py_found
)
echo  LOI: Cai Python 3.11 that bai!
if exist "%~dp0_ShowError.vbs" (
    cscript //nologo "%~dp0_ShowError.vbs" "Cai dat Python 3.11 that bai. Vui long chay lai file cai dat MagicVoice, hoac lien he admin de duoc ho tro."
) else (
    echo  ^(Khong tim thay _ShowError.vbs - xem install_log.txt de biet chi tiet loi^)
)
exit /b 1

:py_found
for /f "tokens=*" %%v in ('!PY311! --version 2^>^&1') do echo   Dung: %%v

echo.
echo  [2/3] Chay Smart Installer (setup_helper.py)...
echo        (mat 5-20 phut tuy toc do mang va cau hinh GPU)
echo.
!PY311! "%~dp0setup_helper.py"
set "SETUP_CODE=%errorlevel%"

echo.
echo  [3/3] Tao shortcut Desktop...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\MagicVoice TTS Studio.lnk');$s.TargetPath='%~dp0Chay_MagicVoice.bat';$s.WorkingDirectory='%~dp0';$s.IconLocation='%~dp0MagicVoice.ico';$s.Save()" >nul 2>&1
echo   Shortcut Desktop: OK

echo.
if "%SETUP_CODE%"=="0" (
    echo  ================================================
    echo    CAI DAT HOAN CHINH - San sang su dung!
    echo  ================================================
) else (
    echo  ================================================
    echo    CAI DAT XONG - Xem install_log.txt neu co loi
    echo  ================================================
)
echo.
echo  Dang mo MagicVoice TTS Studio...
timeout /t 2 /nobreak >nul
if exist "%~dp0.caidat_running" del /f "%~dp0.caidat_running" >nul 2>&1
REM FIX v3.65: goi qua MagicVoice.vbs (wscript, an cua so hoan toan) thay vi
REM Chay_MagicVoice.bat truc tiep - mo .bat luon nhay 1 cua so den (console
REM host) du chay xong rat nhanh, nhin thieu chuyen nghiep luc vua cai xong.
REM Luc nay Python chac chan da cai xong nen khong can nhanh du phong "chua
REM cai Python" cua Chay_MagicVoice.bat nua.
start "" wscript.exe "%~dp0MagicVoice.vbs"
exit /b 0
