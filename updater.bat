@echo off
REM ============================================================
REM updater.bat — Swap file .new -> file thuc + restart app
REM Goi tu app: updater.bat <PID_app_dang_chay>
REM Viet lai: BO for %%p (tranh loi 'p'), BO py -3.11w (sai cu phap)
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"
set "APP_PID=%~1"

REM === Doi app dong (toi da 15s) ===
set /a RETRY=0
:wait_loop
if "%APP_PID%"=="" goto start_swap
tasklist /FI "PID eq %APP_PID%" 2>nul | find "%APP_PID%" >nul
if errorlevel 1 goto start_swap
set /a RETRY+=1
if %RETRY% GEQ 15 goto force_kill
timeout /t 1 /nobreak >nul
goto wait_loop

:force_kill
taskkill /F /PID %APP_PID% >nul 2>&1
timeout /t 2 /nobreak >nul

:start_swap
REM === Swap tat ca file .new -> file thuc ===
call :swap_file "magicvoice_core.cp311-win_amd64.pyd"
call :swap_file "auth_manager.cp311-win_amd64.pyd"
call :swap_file "license_guard.cp311-win_amd64.pyd"
call :swap_file "magicvoice.py"
call :swap_file "script_processor.py"
call :swap_file "version.txt"

REM === Khoi dong lai app: tim pythonw.exe bang if exist tuan tu ===
REM (KHONG dung for %%p de tranh loi 'p' khi chay qua cmd /C)
set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Python311\pythonw.exe" set "PYW=C:\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python311\pythonw.exe" set "PYW=C:\Program Files\Python311\pythonw.exe"
if not defined PYW if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe" set "PYW=%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files (x86)\Python311\pythonw.exe" set "PYW=C:\Program Files (x86)\Python311\pythonw.exe"

if defined PYW (
    start "" "%PYW%" "%~dp0magicvoice.py"
    goto done
)

REM Fallback 1: Chay_MagicVoice.bat (da co logic tim python rieng)
if exist "%~dp0Chay_MagicVoice.bat" (
    start "" "%~dp0Chay_MagicVoice.bat"
    goto done
)

REM Fallback 2: MagicVoice.vbs
if exist "%~dp0MagicVoice.vbs" (
    start "" "%~dp0MagicVoice.vbs"
    goto done
)

:done
exit /b 0

REM ============================================================
REM Subroutine: Swap 1 file (.new -> goc), retry 3 lan
REM ============================================================
:swap_file
set "FNAME=%~1"
if not exist "%~dp0%FNAME%.new" exit /b 0
set /a SW_RETRY=0
:swap_retry
if exist "%~dp0%FNAME%" del /F /Q "%~dp0%FNAME%" >nul 2>&1
ren "%~dp0%FNAME%.new" "%FNAME%" >nul 2>&1
if exist "%~dp0%FNAME%" exit /b 0
set /a SW_RETRY+=1
if %SW_RETRY% GEQ 3 exit /b 1
timeout /t 1 /nobreak >nul
goto swap_retry
