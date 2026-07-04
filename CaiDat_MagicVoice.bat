@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "APP_VER=?"
for /f "usebackq tokens=* delims=" %%v in ("%~dp0version.txt") do (
    set "APP_VER=%%v" & goto :ver_done
)
:ver_done
title MagicVoice TTS Studio - Cai Dat v%APP_VER%

echo.
echo  ================================================
echo    MagicVoice TTS Studio - Cai Dat Tu Dong v%APP_VER%
echo  ================================================
echo.

:: Kiem tra Admin
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo  Yeu cau quyen Admin. Dang khoi dong lai...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: === Tim Python 3.11 ===
echo  [1/3] Tim Python 3.11...
set "PY311="

py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )

for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "C:\Python311\python.exe"
    "D:\Python311\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
) do (
    if exist %%~p (
        set "PY311=%%~p"
        goto :py_found
    )
)

:: Chua co - tu dong tai va cai
echo  Chua co Python 3.11. Dang tai (~25MB)...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12';(New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe','%TEMP%\py311_mv.exe')" >nul 2>&1
if not exist "%TEMP%\py311_mv.exe" (
    echo  LOI: Khong tai duoc Python 3.11!
    echo  Tai thu cong: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    pause & exit /b 1
)
echo  Dang cai Python 3.11...
"%TEMP%\py311_mv.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
del "%TEMP%\py311_mv.exe" >nul 2>&1
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :py_found
)
echo  LOI: Cai Python 3.11 that bai!
echo  Khoi dong lai may tinh roi chay lai file nay.
pause & exit /b 1

:py_found
for /f "tokens=*" %%v in ('!PY311! --version 2^>^&1') do echo   Dung: %%v

:: === Chay Smart Installer ===
echo.
echo  [2/3] Chay bo cai dat (mat 5-30 phut tuy GPU va mang)...
echo        KHONG dong cua so nay!
echo.

!PY311! "%~dp0setup_helper.py"
set "SETUP_CODE=%errorlevel%"

:: === Tao Shortcut Desktop ===
echo.
echo  [3/3] Tao shortcut Desktop...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\MagicVoice TTS Studio.lnk');$s.TargetPath='%~dp0Chay_MagicVoice.bat';$s.WorkingDirectory='%~dp0';$ico='%~dp0MagicVoice.ico';if(Test-Path $ico){$s.IconLocation=$ico};$s.Save()" >nul 2>&1
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
start "" "%~dp0Chay_MagicVoice.bat"
exit /b 0
