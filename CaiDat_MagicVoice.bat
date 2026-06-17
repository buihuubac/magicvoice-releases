@echo off
setlocal enabledelayedexpansion
title MagicVoice TTS Studio - Cai Dat v3.47
cd /d "%~dp0"

echo.
echo  ================================================
echo    MagicVoice TTS Studio - Cai Dat Tu Dong v3.47
echo  ================================================
echo.

REM === Kiem tra quyen Admin ===
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo  Yeu cau quyen Admin de cai dat day du.
    echo  Dang khoi dong lai voi quyen Admin...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

REM === Tim Python 3.11 ===
echo  [1/3] Tim Python 3.11...
set "PY311="

py -3.11 --version >nul 2>&1
if not errorlevel 1 (
    set "PY311=py -3.11"
    goto :py_found
)

REM Thu tung duong dan pho bien
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "C:\Python311\python.exe"
    "D:\Python311\python.exe"
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

REM Python 3.11 chua co - thu 3 phuong an theo thu tu

REM --- Phuong an 1: winget (Windows 10/11 co san, ~25MB) ---
echo  Chua co Python 3.11. Thu cai qua winget...
set "WINGET_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe"
if not exist "%WINGET_EXE%" set "WINGET_EXE=winget"
"%WINGET_EXE%" install --id Python.Python.3.11 --version 3.11.9 --silent --accept-package-agreements --accept-source-agreements >nul 2>&1

set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :py_found
)

REM --- Phuong an 2: py install 3.11 (py launcher moi tren Windows 11) ---
echo  Thu cai qua py install 3.11...
py install 3.11 >nul 2>&1
timeout /t 5 /nobreak >nul
py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )

REM --- Phuong an 3: tai truc tiep tu python.org (~25MB) ---
echo  Thu tai truc tiep tu python.org...
set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PY_SETUP=%TEMP%\python311_setup.exe"
powershell -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;(New-Object Net.WebClient).DownloadFile('%PY_URL%','%PY_SETUP%')" >nul 2>&1

if exist "%PY_SETUP%" (
    echo  Dang cai Python 3.11...
    "%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
    del "%PY_SETUP%" >nul 2>&1
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :py_found
    )
)

echo.
echo  LOI: Khong tu dong cai duoc Python 3.11.
echo  Vui long cai thu cong:
echo    1. Mo PowerShell hoac CMD
echo    2. Chay: winget install Python.Python.3.11
echo    hoac tai: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
echo    3. Cai xong, chay lai file nay.
pause
exit /b 1

:py_found
for /f "tokens=*" %%v in ('!PY311! --version 2^>^&1') do echo   Dung: %%v

REM === Chay Smart Installer ===
echo.
echo  [2/3] Chay Smart Installer (setup_helper.py)...
echo        (mat 5-20 phut tuy toc do mang va cau hinh GPU)
echo.

!PY311! "%~dp0setup_helper.py"
set "SETUP_CODE=%errorlevel%"

REM === Tao shortcut Desktop ===
echo.
echo  [3/3] Tao shortcut Desktop...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\MagicVoice TTS Studio.lnk');$s.TargetPath='%~dp0Chay_MagicVoice.bat';$s.WorkingDirectory='%~dp0';$s.IconLocation='%~dp0MagicVoice.ico';$s.Save()" >nul 2>&1
echo   Shortcut Desktop: OK

REM === Ket qua va khoi dong app ===
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
start "" "%~dp0Chay_MagicVoice.bat"
exit
