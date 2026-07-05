@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

set "PYW="
:: Tim pythonw.exe
if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Python311\pythonw.exe" set "PYW=C:\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python311\pythonw.exe" set "PYW=C:\Program Files\Python311\pythonw.exe"
if not defined PYW if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe" set "PYW=%USERPROFILE%\AppData\Local\Programs\Python\Python311\pythonw.exe"
if not defined PYW if exist "C:\Program Files (x86)\Python311\pythonw.exe" set "PYW=C:\Program Files (x86)\Python311\pythonw.exe"
if defined PYW goto :found
:: Tim qua py launcher (ghi ra file tam - tranh for /f %%p)
py -3.11 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\mv_pyw.txt" 2>nul
if exist "%TEMP%\mv_pyw.txt" (
    set /p PYW=<"%TEMP%\mv_pyw.txt"
    del /Q "%TEMP%\mv_pyw.txt" >nul 2>&1
)
if defined PYW if exist "%PYW%" goto :found

:: Khong tim thay Python
echo Python 3.11 chua duoc cai dat!
echo Vui long chay CaiDat_MagicVoice.bat truoc.
pause
exit /b 1

:found
start "" "!PYW!" "%~dp0magicvoice.py"
