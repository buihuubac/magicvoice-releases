@echo off
REM ============================================================
REM updater.bat — Swap file .new -> file thuc + restart app
REM Goi tu app khi co update: updater.bat <PID_app_dang_chay>
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "APP_PID=%~1"

REM === Doi app dong (toi da 15s) ===
set /a RETRY=0
:wait_loop
if "%APP_PID%"=="" goto :start_swap
tasklist /FI "PID eq %APP_PID%" 2>nul | find "%APP_PID%" >nul
if errorlevel 1 goto :start_swap
set /a RETRY+=1
if %RETRY% GEQ 15 goto :force_kill
timeout /t 1 /nobreak >nul
goto :wait_loop

:force_kill
REM App khong tu dong, kill bang vu luc
taskkill /F /PID %APP_PID% >nul 2>&1
timeout /t 2 /nobreak >nul

:start_swap
REM === Swap tat ca file .new -> file thuc ===
REM Retry tung file 3 lan vi co the bi Defender scan tam thoi

call :swap_file "magicvoice_core.cp311-win_amd64.pyd"
call :swap_file "auth_manager.cp311-win_amd64.pyd"
call :swap_file "license_guard.cp311-win_amd64.pyd"
call :swap_file "magicvoice.py"
call :swap_file "script_processor.py"
call :swap_file "version.txt"

REM === Tim pythonw.exe TRIET DE (KHONG goi .bat khac de tranh loi 'p') ===
set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Python311\pythonw.exe" set "PYW=C:\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python311\pythonw.exe" set "PYW=C:\Program Files\Python311\pythonw.exe"
if not defined PYW if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe" set "PYW=%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files (x86)\Python311\pythonw.exe" set "PYW=C:\Program Files (x86)\Python311\pythonw.exe"
if not defined PYW if exist "D:\Python311\pythonw.exe" set "PYW=D:\Python311\pythonw.exe"

REM Fallback: hoi py launcher duong dan that (qua file temp, KHONG dung for /f)
if not defined PYW (
    py -3.11 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\mv_pyw.txt" 2>nul
    if exist "%TEMP%\mv_pyw.txt" (
        set /p PYW=<"%TEMP%\mv_pyw.txt"
        del /Q "%TEMP%\mv_pyw.txt" >nul 2>&1
    )
)

REM Fallback 2: where pythonw
if not defined PYW (
    where pythonw > "%TEMP%\mv_pyw2.txt" 2>nul
    if exist "%TEMP%\mv_pyw2.txt" (
        set /p PYW=<"%TEMP%\mv_pyw2.txt"
        del /Q "%TEMP%\mv_pyw2.txt" >nul 2>&1
    )
)

REM Mo app — CHI dung pythonw + magicvoice.py, TUYET DOI khong goi .bat khac
if defined PYW (
    if exist "%PYW%" (
        start "MagicVoice" "%PYW%" "%~dp0magicvoice.py"
        goto done
    )
)

REM Khong tim thay python -> bao loi ro rang (KHONG goi Chay_MagicVoice.bat)
echo Khong tim thay Python 3.11. Vui long mo app thu cong tu shortcut Desktop.
timeout /t 3 /nobreak >nul

:done
exit /b 0

REM ============================================================
REM Subroutine: Swap 1 file (xoa cu + rename .new -> goc)
REM Retry 3 lan, moi lan cach 1s
REM ============================================================
:swap_file
set "FNAME=%~1"
if not exist "%~dp0%FNAME%.new" exit /b 0

set /a SW_RETRY=0
:swap_retry
REM Xoa file goc (neu co)
if exist "%~dp0%FNAME%" del /F /Q "%~dp0%FNAME%" >nul 2>&1
REM Rename .new -> goc
ren "%~dp0%FNAME%.new" "%FNAME%" >nul 2>&1
if exist "%~dp0%FNAME%" exit /b 0

set /a SW_RETRY+=1
if %SW_RETRY% GEQ 3 (
    REM Khong swap duoc -> de file .new lai, lan sau app khoi dong se thay
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :swap_retry
