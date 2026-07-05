@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM updater.bat v3.43 — Swap .new -> thuc + restart app
REM FIX: Dung ping thay timeout (timeout khong chay trong DETACHED_PROCESS)
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "APP_PID=%~1"
set "APPDIR=%~dp0"

REM === Doi app dong (toi da 30 giay) ===
set /a RETRY=0
:wait_loop
if "%APP_PID%"=="" goto :start_swap
tasklist /FI "PID eq %APP_PID%" 2>nul | find "%APP_PID%" >nul
if errorlevel 1 goto :start_swap
set /a RETRY+=1
if %RETRY% GEQ 30 goto :force_kill
ping -n 2 127.0.0.1 >nul 2>&1
goto :wait_loop

:force_kill
taskkill /F /PID %APP_PID% >nul 2>&1
ping -n 4 127.0.0.1 >nul 2>&1

:start_swap
REM Them 3s de .pyd duoc giai phong hoan toan sau khi process chet
ping -n 4 127.0.0.1 >nul 2>&1

REM === Swap file .new -> file thuc (retry 5 lan) ===
call :swap_file "magicvoice_core.cp311-win_amd64.pyd"
call :swap_file "auth_manager.cp311-win_amd64.pyd"
call :swap_file "license_guard.cp311-win_amd64.pyd"
call :swap_file "magicvoice.py"
call :swap_file "script_processor.py"
call :swap_file "setup_helper.py"
call :swap_file "CaiDat_MagicVoice.bat"
call :swap_file "version.txt"

REM === Xoa file .new con du lai (neu co) ===
for %%f in ("%APPDIR%*.new") do del /F /Q "%%f" >nul 2>&1

REM === Tim pythonw.exe ===
set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Python311\pythonw.exe" set "PYW=C:\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python311\pythonw.exe" set "PYW=C:\Program Files\Python311\pythonw.exe"
if not defined PYW if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe" set "PYW=%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files (x86)\Python311\pythonw.exe" set "PYW=C:\Program Files (x86)\Python311\pythonw.exe"
if not defined PYW if exist "D:\Python311\pythonw.exe" set "PYW=D:\Python311\pythonw.exe"

if not defined PYW (
    py -3.11 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\mv_pyw.txt" 2>nul
    if exist "%TEMP%\mv_pyw.txt" (
        set /p PYW=<"%TEMP%\mv_pyw.txt"
        del "%TEMP%\mv_pyw.txt" >nul 2>&1
    )
)

REM === Khoi dong app ===
REM Dung cmd /c start de tao console moi, tranh van de detached-process
if defined PYW (
    if exist "!PYW!" (
        cmd /c start "MagicVoice" "!PYW!" "%APPDIR%magicvoice.py"
        goto :done
    )
)

REM Fallback: Chay_MagicVoice.bat
if exist "%APPDIR%Chay_MagicVoice.bat" (
    cmd /c start "MagicVoice" "%APPDIR%Chay_MagicVoice.bat"
)

:done
exit /b 0

REM ============================================================
REM Swap 1 file: xoa cu + rename .new -> goc (retry 5 lan)
REM ============================================================
:swap_file
set "FNAME=%~1"
if not exist "%APPDIR%%FNAME%.new" exit /b 0

set /a SW_RETRY=0
:swap_retry
if exist "%APPDIR%%FNAME%" del /F /Q "%APPDIR%%FNAME%" >nul 2>&1
ren "%APPDIR%%FNAME%.new" "%FNAME%" >nul 2>&1
if exist "%APPDIR%%FNAME%" exit /b 0
set /a SW_RETRY+=1
if %SW_RETRY% GEQ 5 exit /b 1
ping -n 2 127.0.0.1 >nul 2>&1
goto :swap_retry
