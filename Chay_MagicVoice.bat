@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

set "PYW="

REM FIX v3.68 (BUG THAT SU nghiem trong, phat hien 2026-07-29): xem ghi chu
REM day du o CaiDat_MagicVoice.bat/MagicVoice.vbs - file nay TUNG tu do tim
REM Python doc lap (thu tu khac cac file kia), co the mo app bang 1 ban
REM Python KHAC voi ban da duoc cai thu vien vao, gay "No module named ...".
REM Sua: doc THANG "python_used.txt" (nguon su that duy nhat do CaiDat_
REM MagicVoice.bat ghi lai) truoc tien.
if exist "%~dp0python_used.txt" (
    for /f "usebackq tokens=* delims=" %%v in ("%~dp0python_used.txt") do set "PYW=%%v"
    if defined PYW if not exist "!PYW!" set "PYW="
)
if defined PYW goto :found

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
