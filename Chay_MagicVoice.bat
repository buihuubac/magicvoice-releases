@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Python311\pythonw.exe" set "PYW=C:\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python311\pythonw.exe" set "PYW=C:\Program Files\Python311\pythonw.exe"
if not defined PYW if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe" set "PYW=%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files (x86)\Python311\pythonw.exe" set "PYW=C:\Program Files (x86)\Python311\pythonw.exe"
if defined PYW goto :found

REM Fallback: py launcher
py -3.11 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\mv_pyw.txt" 2>nul
for /f "usebackq tokens=* delims=" %%v in ("%TEMP%\mv_pyw.txt") do set "PYW=%%v"
if exist "%TEMP%\mv_pyw.txt" (cd .) & del /f "%TEMP%\mv_pyw.txt" >nul 2>&1
if defined PYW if exist "%PYW%" goto :found

if exist "%~dp0.caidat_running" (
    del /f "%~dp0.caidat_running" >nul 2>&1
    echo.
    echo  LOI: Khong tim thay Python 3.11 sau khi da cai dat.
    echo  Vui long khoi dong lai may tinh roi thu lai.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo    Python 3.11 chua duoc cai.
echo    Dang khoi dong bo cai MagicVoice...
echo  ============================================
echo.
timeout /t 2 /nobreak >nul
echo. > "%~dp0.caidat_running"
start "" "%~dp0CaiDat_MagicVoice.bat"
exit /b 0

:found
if exist "%~dp0.caidat_running" del /f "%~dp0.caidat_running" >nul 2>&1
start "" "!PYW!" "%~dp0magicvoice.py"
exit
