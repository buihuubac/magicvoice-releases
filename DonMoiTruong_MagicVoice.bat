@echo off
setlocal enabledelayedexpansion
title MagicVoice - Don Moi Truong

:: Kiem tra Admin
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo  =====================================================
echo    MagicVoice - Don Sach Moi Truong (Fix Xung Dot)
echo  =====================================================
echo.
echo  Buoc nay se go sach torch/torchvision cu va cai lai.
echo  Vui long KHONG tat cua so nay!
echo.

:: Tim Python 3.11
set "PY="
py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY=py -3.11" & goto :py_ok )
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :py_ok
)
echo  LOI: Khong tim thay Python 3.11!
pause & exit /b 1

:py_ok
echo  [1/4] Go sach torch, torchvision, torchaudio...
%PY% -m pip uninstall torch torchvision torchaudio -y 2>nul
echo   Xong.

echo.
echo  [2/4] Xoa pip cache (tranh tai lai ban cu)...
%PY% -m pip cache purge 2>nul
echo   Xong.

echo.
echo  [3/4] Don folder rac trong site-packages...
%PY% -c "import glob,shutil,site,os; [shutil.rmtree(j,ignore_errors=True) or print('  Xoa:',j) for sp in (site.getsitepackages() or []) + [site.getusersitepackages()] for j in glob.glob(os.path.join(sp,'~*')) + glob.glob(os.path.join(sp,'torchvision*'))]" 2>nul
echo   Xong.

echo.
echo  [4/4] Moi truong da sach. Dang chay lai cai dat MagicVoice...
echo.

:: Tim CaiDat_MagicVoice.bat trong cung thu muc hoac thu muc cha
set "CAIDAT="
if exist "%~dp0CaiDat_MagicVoice.bat" set "CAIDAT=%~dp0CaiDat_MagicVoice.bat"
if not defined CAIDAT (
    for %%d in ("%~dp0..") do (
        if exist "%%~fd\CaiDat_MagicVoice.bat" set "CAIDAT=%%~fd\CaiDat_MagicVoice.bat"
    )
)

if defined CAIDAT (
    echo  Tim thay: !CAIDAT!
    echo  Dang chay cai dat lai...
    call "!CAIDAT!"
) else (
    echo  =====================================================
    echo    MOI TRUONG DA SACH XONG!
    echo    Hay chay lai file CaiDat_MagicVoice.bat
    echo  =====================================================
)
