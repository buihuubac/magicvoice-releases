@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "OUT=%~dp0chan_doan_ket_qua.txt"

echo ================================================ > "%OUT%"
echo  MAGICVOICE - CHAN DOAN TU DONG >> "%OUT%"
echo  %date% %time% >> "%OUT%"
echo ================================================ >> "%OUT%"

echo. >> "%OUT%"
echo [1] Thu muc hien tai va danh sach file >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
echo %~dp0 >> "%OUT%"
dir "%~dp0" >> "%OUT%" 2>&1

echo. >> "%OUT%"
echo [2] Python qua launcher "py -3.11" >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
py -3.11 --version >> "%OUT%" 2>&1

echo. >> "%OUT%"
echo [3] Python theo duong dan truc tiep >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "C:\Python311\python.exe"
) do (
    if exist %%~p (
        echo TON TAI: %%~p >> "%OUT%"
        %%~p --version >> "%OUT%" 2>&1
    ) else (
        echo KHONG CO: %%~p >> "%OUT%"
    )
)

echo. >> "%OUT%"
echo [4] Kiem tra quyen ghi file vao thu muc nay >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
echo test > "%~dp0.write_test.tmp" 2>>"%OUT%"
if exist "%~dp0.write_test.tmp" (
    echo GHI FILE OK >> "%OUT%"
    del /f /q "%~dp0.write_test.tmp" >nul 2>&1
) else (
    echo GHI FILE THAT BAI - CO THE BI PHAN MEM BAO MAT CHAN >> "%OUT%"
)

echo. >> "%OUT%"
echo [5] GPU / Driver NVIDIA >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
nvidia-smi >> "%OUT%" 2>&1

echo. >> "%OUT%"
echo [6] install_log.txt (100 dong cuoi neu co) >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
if exist "%~dp0install_log.txt" (
    powershell -NoProfile -Command "Get-Content '%~dp0install_log.txt' -Tail 100" >> "%OUT%" 2>&1
) else (
    echo (khong co file install_log.txt^) >> "%OUT%"
)

echo. >> "%OUT%"
echo [6b] python_install_*.log (log cai Python, neu co) >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
set "FOUND_PYLOG=0"
for %%f in ("%~dp0python_install_*.log") do (
    if exist "%%~f" (
        set "FOUND_PYLOG=1"
        echo --- %%~nxf --- >> "%OUT%"
        powershell -NoProfile -Command "Get-Content '%%~f' -Encoding Unicode -Tail 60" >> "%OUT%" 2>&1
    )
)
if "%FOUND_PYLOG%"=="0" echo (khong co file python_install_*.log^) >> "%OUT%"

echo. >> "%OUT%"
echo [7] last_setup_fail.txt neu co >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
if exist "%~dp0last_setup_fail.txt" (
    type "%~dp0last_setup_fail.txt" >> "%OUT%"
) else (
    echo (khong co file last_setup_fail.txt^) >> "%OUT%"
)

echo. >> "%OUT%"
echo [8] Windows version >> "%OUT%"
echo ------------------------------------------------ >> "%OUT%"
ver >> "%OUT%"
systeminfo | findstr /B /C:"OS Name" /C:"OS Version" >> "%OUT%" 2>&1

echo.
echo ================================================
echo  XONG! Ket qua da luu vao:
echo  %OUT%
echo ================================================
echo  Gui nguyen file nay (chan_doan_ket_qua.txt) qua Zalo/Email.
echo.
pause
