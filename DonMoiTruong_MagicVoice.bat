@echo off
setlocal enabledelayedexpansion
title MagicVoice - Don Moi Truong

:: FIX v3.65 (24): bo check Admin - khong can thiet (Python cai per-user vao
:: %LOCALAPPDATA%, khong dung Program Files) - giong fix da lam o
:: CaiDat_MagicVoice.bat. Truoc day yeu cau Admin khong dung ly do gi.

echo.
echo  =====================================================
echo    MagicVoice - Don Sach Moi Truong (Fix Xung Dot)
echo  =====================================================
echo.
echo  Buoc nay se go sach torch/torchvision/torchaudio cu va cai lai.
echo  Vui long KHONG tat cua so nay!
echo.

:: Tim Python 3.11
set "PY="
set "PYDIR="
py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY=py -3.11" & goto :py_ok )
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python311"
    goto :py_ok
)
echo  LOI: Khong tim thay Python 3.11!
pause & exit /b 1

:py_ok
echo  [1/4] Go sach torch, torchvision, torchaudio, torchcodec...
%PY% -m pip uninstall torch torchvision torchaudio torchcodec -y 2>nul
echo   Xong.

echo.
echo  [2/4] Xoa pip cache (tranh tai lai ban cu)...
%PY% -m pip cache purge 2>nul
echo   Xong.

echo.
echo  [3/4] Xoa tay thu muc torch/torchaudio/torchvision/torchcodec con sot
echo        (FIX v3.65 (24): pip uninstall doi khi khong don sach het DLL
echo        hong, gay loi "Entry Point Not Found" lap lai mai khong tu het) ...
%PY% -c "import glob,shutil,site,os; [shutil.rmtree(j,ignore_errors=True) or print('  Xoa:',j) for sp in (site.getsitepackages() or []) + [site.getusersitepackages()] for pat in ('torch','torchvision*','torchaudio*','torchcodec*','~*') for j in glob.glob(os.path.join(sp,pat))]" 2>nul
echo   Xong.

echo.
echo  [4/4] Moi truong da sach. Dang chay lai cai dat MagicVoice...
echo.

:: FIX v3.65 (25): file nay gio duoc dong goi CHUNG voi installer
:: (MagicVoice_Setup_vX.XX.exe) trong zip gui khach, KHONG con di kem
:: CaiDat_MagicVoice.bat rieng nua o ban dong goi moi - truoc day chi tim
:: CaiDat_MagicVoice.bat nen don xong khong tu cai lai duoc, bao sai ten
:: file khong ton tai trong zip. Uu tien tim installer .exe TRUOC (cung
:: thu muc), roi moi fallback ve CaiDat_MagicVoice.bat (truong hop dung
:: file nay trong 1 thu muc client\ da cai san).
set "SETUP_EXE="
for %%f in ("%~dp0MagicVoice_Setup_*.exe") do set "SETUP_EXE=%%~ff"

set "CAIDAT="
if exist "%~dp0CaiDat_MagicVoice.bat" set "CAIDAT=%~dp0CaiDat_MagicVoice.bat"
if not defined CAIDAT (
    for %%d in ("%~dp0..") do (
        if exist "%%~fd\CaiDat_MagicVoice.bat" set "CAIDAT=%%~fd\CaiDat_MagicVoice.bat"
    )
)

if defined SETUP_EXE (
    echo  Tim thay: !SETUP_EXE!
    echo  Dang chay lai bo cai dat...
    start "" "!SETUP_EXE!"
) else if defined CAIDAT (
    echo  Tim thay: !CAIDAT!
    echo  Dang chay cai dat lai...
    call "!CAIDAT!"
) else (
    echo  =====================================================
    echo    MOI TRUONG DA SACH XONG!
    echo    Hay chay lai file MagicVoice_Setup_vX.XX.exe (hoac
    echo    CaiDat_MagicVoice.bat neu dang dung thu muc client cu).
    echo  =====================================================
)
