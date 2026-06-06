@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title MagicVoice TTS Studio - Cai Dat v3.43
cd /d "%~dp0"

echo.
echo  ================================================
echo    MagicVoice TTS Studio - Cai Dat Tu Dong v3.43
echo  ================================================
echo.

:: ─────────────────────────────────────────────────────────
:: Kiem tra quyen Admin (can cho cai Python + PyTorch)
:: ─────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo  Yeu cau quyen Admin de cai dat day du.
    echo  Dang khoi dong lai voi quyen Admin...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: ─────────────────────────────────────────────────────────
:: Tim Python 3.11
:: ─────────────────────────────────────────────────────────
echo  [1/3] Tim Python 3.11...
set "PY311="

py -3.11 --version >nul 2>&1
if !errorlevel!==0 (
    set "PY311=py -3.11"
    goto :py_found
)

for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "%PROGRAMFILES(X86)%\Python311\python.exe"
    "C:\Python311\python.exe"
    "D:\Python311\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
) do (
    if exist %%~p (
        %%~p --version >nul 2>&1
        if !errorlevel!==0 (
            set "PY311=%%~p"
            goto :py_found
        )
    )
)

:: ─── Python 3.11 chua co → cai tu dong ───────────────────
echo  Chua co Python 3.11. Dang tai (khoang 25MB)...
set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PY_SETUP=%TEMP%\python311_setup.exe"

powershell -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%PY_URL%','%PY_SETUP%')" >nul 2>&1
if not exist "%PY_SETUP%" (
    echo  LOI: Khong tai duoc Python 3.11!
    echo  Vui long tai thu cong:
    echo    https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    pause
    exit /b 1
)

echo  Dang cai Python 3.11...
"%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
del "%PY_SETUP%" >nul 2>&1

:: Refresh PATH
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

py -3.11 --version >nul 2>&1
if !errorlevel!==0 (
    set "PY311=py -3.11"
    goto :py_found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :py_found
)

echo  LOI: Cai Python 3.11 that bai!
pause
exit /b 1

:py_found
for /f "tokens=*" %%v in ('!PY311! --version 2^>^&1') do echo   Dung: %%v

:: ─────────────────────────────────────────────────────────
:: Chay Smart Installer Python
:: ─────────────────────────────────────────────────────────
echo.
echo  [2/3] Chay Smart Installer...
echo        (mat 5-20 phut tuy toc do mang va GPU)
echo.

!PY311! "%~dp0setup_helper.py"
set "SETUP_CODE=!errorlevel!"

:: ─────────────────────────────────────────────────────────
:: Tao shortcut Desktop
:: ─────────────────────────────────────────────────────────
echo.
echo  [3/3] Tao shortcut Desktop...
powershell -NoProfile -Command ^
    "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\MagicVoice TTS Studio.lnk');" ^
    "$s.TargetPath='%~dp0Chay_MagicVoice.bat';" ^
    "$s.WorkingDirectory='%~dp0';" ^
    "$s.IconLocation='%~dp0MagicVoice.ico';" ^
    "$s.Save()" >nul 2>&1
echo   Shortcut tren Desktop: OK

:: ─────────────────────────────────────────────────────────
:: Ket qua va khoi dong app
:: ─────────────────────────────────────────────────────────
echo.
if !SETUP_CODE!==0 (
    echo  ================================================
    echo    CAI DAT HOAN CHỈNH - San sang su dung!
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
