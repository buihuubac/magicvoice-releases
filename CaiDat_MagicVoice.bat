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

net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo  Yeu cau quyen Admin de cai dat day du.
    echo  Dang khoi dong lai voi quyen Admin...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

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
if not exist "%PY_SETUP%" ( echo  LOI: Khong tai duoc Python! & pause & exit /b 1 )
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
echo  LOI: Cai Python 3.11 that bai! & pause & exit /b 1

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
start "" "%~dp0Chay_MagicVoice.bat"
exit /b 0
