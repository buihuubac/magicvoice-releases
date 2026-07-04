@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Doc version
set "APP_VER=?"
for /f "usebackq tokens=* delims=" %%v in ("%~dp0version.txt") do (
    set "APP_VER=%%v" & goto :ver_done
)
:ver_done
title MagicVoice TTS Studio - Smart Installer v%APP_VER%

echo.
echo  =======================================================
echo    MagicVoice TTS Studio - Smart Installer v%APP_VER%
echo  =======================================================
echo.

:: Kiem tra Admin
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo  [!] Can quyen Admin - dang khoi dong lai voi quyen Admin...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: =========================================================
:: BUOC 0 - Kiem tra moi truong he thong
:: =========================================================
echo  [BUOC 0/6] Kiem tra moi truong he thong...

:: Check VC++ Redist 2015-2022 x64 (bat buoc de torch hoat dong)
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Version >nul 2>&1
if not errorlevel 1 (
    echo   [v] Visual C++ Redist: Da co
) else (
    echo   [*] Dang tai Visual C++ Redist 2022 x64...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12';(New-Object Net.WebClient).DownloadFile('https://aka.ms/vs/17/release/vc_redist.x64.exe','%TEMP%\vc_redist_mv.exe')" >nul 2>&1
    if exist "%TEMP%\vc_redist_mv.exe" (
        "%TEMP%\vc_redist_mv.exe" /quiet /norestart >nul 2>&1
        del "%TEMP%\vc_redist_mv.exe" >nul 2>&1
        echo   [v] Visual C++ Redist: Da cai xong
    ) else (
        echo   [!] Khong tai duoc VC++ Redist - co the anh huong torch
    )
)

:: =========================================================
:: BUOC 1 - Quet GPU va chon CUDA build
:: =========================================================
echo.
echo  [BUOC 1/6] Quet GPU va chon CUDA build...
set "GPU_NAME="
set "CUDA_TAG=cpu"
set "GPU_GEN=none"

:: Thu nvidia-smi truoc (chinh xac nhat)
for /f "tokens=*" %%G in ('nvidia-smi --query-gpu=name --format=csv,noheader 2^>nul') do (
    if not defined GPU_NAME set "GPU_NAME=%%G"
)

:: Fallback wmic neu khong co nvidia-smi hoac driver cu
if not defined GPU_NAME (
    for /f "skip=1 delims=" %%G in ('wmic path win32_VideoController get Name 2^>nul') do (
        set "_WTMP=%%G"
        if defined _WTMP (
            echo !_WTMP! | findstr /i "nvidia" >nul 2>&1
            if not errorlevel 1 if not defined GPU_NAME set "GPU_NAME=%%G"
        )
    )
)

if not defined GPU_NAME (
    echo   [!] Khong phat hien GPU NVIDIA - su dung CPU mode
    set "GPU_GEN=none"
    set "CUDA_TAG=cpu"
    goto :gpu_done
)

echo   [v] GPU phat hien: !GPU_NAME!

:: RTX 5000 Blackwell -> cu128 (compute 8.9+)
echo !GPU_NAME! | findstr /i "5090 5080 5070 5060 5050 5040 5030" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu128" & set "GPU_GEN=5xxx" & goto :gpu_done )

:: RTX 4000 Ada -> cu126 (compute 8.9)
echo !GPU_NAME! | findstr /i "4090 4080 4070 4060 4050 4030" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu126" & set "GPU_GEN=ok" & goto :gpu_done )

:: RTX 3000 Ampere -> cu126 (compute 8.0-8.6)
echo !GPU_NAME! | findstr /i "3090 3080 3070 3060 3050 3040" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu126" & set "GPU_GEN=ok" & goto :gpu_done )

:: RTX 2000 Turing -> cu126 (compute 7.5)
echo !GPU_NAME! | findstr /i "2080 2070 2060 2050" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu126" & set "GPU_GEN=ok" & goto :gpu_done )

:: GTX 16xx Turing -> cu126 (compute 7.5)
echo !GPU_NAME! | findstr /i "1660 1650 1630" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu126" & set "GPU_GEN=ok" & goto :gpu_done )

:: GTX 10xx Pascal -> cu118 (compute 6.1)
echo !GPU_NAME! | findstr /i "1080 1070 1060 1050 1030" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu118" & set "GPU_GEN=ok" & goto :gpu_done )

:: GTX 980/970/960/950 Maxwell -> cu118 (compute 5.2)
echo !GPU_NAME! | findstr /i "GTX 980 GTX 970 GTX 960 GTX 950" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu118" & set "GPU_GEN=ok" & goto :gpu_done )

:: GTX 750/750Ti Maxwell -> cu118 (compute 5.0)
echo !GPU_NAME! | findstr /i "GTX 750" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu118" & set "GPU_GEN=ok" & goto :gpu_done )

:: MX series -> cu118
echo !GPU_NAME! | findstr /i "MX 5 MX 4 MX 3 MX 2 MX 1 MX5 MX4 MX3 MX2 MX1" >nul 2>&1
if not errorlevel 1 ( set "CUDA_TAG=cu118" & set "GPU_GEN=ok" & goto :gpu_done )

:: GTX 8xx / 7xx / 6xx -> qua cu (compute < 5.0) -> CPU
echo !GPU_NAME! | findstr /i "GTX 8 GTX 7 GTX 6 GTX 5" >nul 2>&1
if not errorlevel 1 (
    echo   [!] Card doi cu (GTX 8xx/7xx/6xx) - khong ho tro CUDA moi - dung CPU mode
    set "GPU_GEN=none" & set "CUDA_TAG=cpu" & goto :gpu_done
)

:: GT series cu -> CPU
echo !GPU_NAME! | findstr /i "GT710 GT730 GT610 GT 7 GT 6 GT 5 GT 4 GT 3 GT 2" >nul 2>&1
if not errorlevel 1 (
    echo   [!] Card GT doi cu - dung CPU mode
    set "GPU_GEN=none" & set "CUDA_TAG=cpu" & goto :gpu_done
)

:: Khong nhan ra doi card -> thu cu118 (an toan nhat)
echo   [!] Khong nhan dang doi card - thu cu118 an toan
set "CUDA_TAG=cu118"
set "GPU_GEN=ok"

:gpu_done
echo   [v] CUDA build chon: !CUDA_TAG!

:: =========================================================
:: BUOC 2 - Kiem tra / Cai Python 3.11
:: =========================================================
echo.
echo  [BUOC 2/6] Kiem tra Python 3.11...
set "PY311="

py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )

for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "C:\Python311\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
) do ( if exist %%~p ( set "PY311=%%~p" & goto :py_found ) )

echo   [!] Chua co Python 3.11 - dang tai (~25MB)...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12';(New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe','%TEMP%\py311_mv_setup.exe')" >nul 2>&1
if not exist "%TEMP%\py311_mv_setup.exe" (
    echo   [X] Khong tai duoc Python 3.11!
    echo       Tai thu cong: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    pause & exit /b 1
)
echo   [*] Dang cai Python 3.11...
"%TEMP%\py311_mv_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
del "%TEMP%\py311_mv_setup.exe" >nul 2>&1
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
py -3.11 --version >nul 2>&1
if not errorlevel 1 ( set "PY311=py -3.11" & goto :py_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :py_found
)
echo   [X] Cai Python 3.11 that bai! & pause & exit /b 1

:py_found
for /f "tokens=*" %%v in ('!PY311! --version 2^>^&1') do echo   [v] %%v
!PY311! -m pip install --upgrade pip --quiet >nul 2>&1

:: =========================================================
:: BUOC 3 - PyTorch 2.8.0 (thong minh + fallback)
:: =========================================================
echo.
echo  [BUOC 3/6] Cai PyTorch 2.8.0 + !CUDA_TAG!...
echo   (Co the mat 10-20 phut tuy toc do mang - KHONG dong cua so nay)

:: Da co torch 2.8.0 hop le -> giu nguyen, bo qua
if "!GPU_GEN!"=="none" (
    !PY311! -c "import torch;v=torch.__version__;assert v.startswith('2.8')" >nul 2>&1
    if not errorlevel 1 ( echo   [v] torch 2.8.0 CPU da co - giu nguyen & goto :torch_done )
) else (
    !PY311! -c "import torch;v=torch.__version__;assert v.startswith('2.8');assert torch.cuda.is_available()" >nul 2>&1
    if not errorlevel 1 ( echo   [v] torch 2.8.0 CUDA da co - giu nguyen & goto :torch_done )
)

:: Go torch cu (KHONG go thu vien hinh anh - app khong dung, tranh Entry Point Not Found)
echo   [*] Go phien ban torch cu neu co...
!PY311! -m pip uninstall torch torchaudio -y --quiet >nul 2>&1

:: CPU mode (khong GPU hop le)
if "!GPU_GEN!"=="none" (
    echo   [*] Cai torch==2.8.0 CPU (khong GPU)...
    !PY311! -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu --quiet
    !PY311! -c "import torch" >nul 2>&1
    if errorlevel 1 goto :torch_fail
    echo   [v] torch 2.8.0 CPU OK
    goto :torch_done
)

:: Co GPU: cai theo CUDA_TAG da detect
echo   [*] Dang tai torch==2.8.0+!CUDA_TAG! (2-3 GB, vui long cho)...
!PY311! -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/!CUDA_TAG! --quiet
!PY311! -c "import torch;assert torch.cuda.is_available()" >nul 2>&1
if not errorlevel 1 (
    echo   [v] torch 2.8.0 + !CUDA_TAG! CUDA OK
    goto :torch_done
)

:: Fallback 1: thu cu118 an toan hon (driver cu / DLL khong tuong thich)
if not "!CUDA_TAG!"=="cu118" (
    echo   [!] !CUDA_TAG! CUDA khong hoat dong - thu cu118...
    !PY311! -m pip uninstall torch torchaudio -y --quiet >nul 2>&1
    !PY311! -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu118 --quiet
    !PY311! -c "import torch;assert torch.cuda.is_available()" >nul 2>&1
    if not errorlevel 1 (
        echo   [v] torch 2.8.0 + cu118 CUDA OK
        goto :torch_done
    )
)

:: Fallback cuoi: CPU (van chay duoc, chi cham hon GPU)
echo   [!] Tat ca CUDA that bai - cai torch CPU fallback...
!PY311! -m pip uninstall torch torchaudio -y --quiet >nul 2>&1
!PY311! -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu --quiet
!PY311! -c "import torch" >nul 2>&1
if not errorlevel 1 (
    echo   [!] torch 2.8.0 CPU mode (CUDA khong kha dung - app van hoat dong)
    goto :torch_done
)

:torch_fail
echo   [X] KHONG CAI DUOC PYTORCH!
echo       Kiem tra: ket noi mang, dung luong o dia (can >= 4GB), Windows Firewall
echo       Thu tat tam Antivirus roi chay lai. Neu van loi, lien he admin.
pause & exit /b 1

:torch_done
!PY311! -c "import torch; print('   [v] torch', torch.__version__, '| CUDA:', str(torch.cuda.is_available()))"

:: =========================================================
:: BUOC 4 - Cai thu vien Python
:: =========================================================
echo.
echo  [BUOC 4/6] Cai thu vien Python...

:: Pin numpy 1.26.4 (tuong thich tot nhat voi torch 2.8)
echo   [*] numpy 1.26.4...
!PY311! -m pip install "numpy==1.26.4" --quiet >nul 2>&1

:: Cai tat ca thu vien can thiet 1 lan
echo   [*] Cai cac thu vien (vui long cho)...
!PY311! -m pip install omnivoice firebase-admin edge-tts soundfile sounddevice pyaudiowpatch scipy Pillow psutil requests imageio-ffmpeg "huggingface_hub>=0.23" tqdm --quiet

:: Kiem tra omnivoice rieng (quan trong nhat)
!PY311! -c "import omnivoice" >nul 2>&1
if errorlevel 1 (
    echo   [!] omnivoice loi - thu reinstall no-deps...
    !PY311! -m pip install omnivoice --force-reinstall --no-deps --quiet >nul 2>&1
    !PY311! -c "import omnivoice" >nul 2>&1
    if errorlevel 1 (
        echo   [X] CANH BAO: omnivoice KHONG IMPORT DUOC!
        echo       Thu chay lai CaiDat_MagicVoice.bat sau khi kiem tra ket noi mang.
    ) else (
        echo   [v] omnivoice: OK (sau reinstall)
    )
) else (
    echo   [v] omnivoice: OK
)
echo   [v] Thu vien: Hoan thanh

:: =========================================================
:: BUOC 5 - Kiem tra / Tai model MagicVoice Engine
:: =========================================================
echo.
echo  [BUOC 5/6] Kiem tra model MagicVoice Engine...
echo   (Lan dau co the mat 5-15 phut - KHONG dong cua so nay)

:: Thu HuggingFace chinh thuc
!PY311! -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice',ignore_patterns=['*.onnx'])" >nul 2>&1
if not errorlevel 1 (
    echo   [v] Model da co / tai xong (HuggingFace)
    goto :model_done
)

:: Thu mirror hf-mirror.com
echo   [!] HuggingFace chinh that bai - thu mirror hf-mirror.com...
set "HF_ENDPOINT=https://hf-mirror.com"
!PY311! -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice',ignore_patterns=['*.onnx'])" >nul 2>&1
if not errorlevel 1 (
    set "HF_ENDPOINT="
    echo   [v] Model tai xong tu mirror
    goto :model_done
)
set "HF_ENDPOINT="
echo   [!] Khong tai duoc model ngay bay gio - app se tu tai khi chay lan dau

:model_done

:: =========================================================
:: BUOC 6 - Verify cuoi + Shortcut Desktop + Mo app
:: =========================================================
echo.
echo  [BUOC 6/6] Kiem tra ket qua cai dat...
set "VERIFY_OK=1"

!PY311! -c "import torch,torchaudio; print('   [v] torch', torch.__version__, '| CUDA:', str(torch.cuda.is_available()))"
if errorlevel 1 ( echo   [X] torch: LOI & set "VERIFY_OK=0" )

!PY311! -c "import omnivoice; print('   [v] MagicVoice Engine: OK')" 2>nul
if errorlevel 1 ( echo   [X] MagicVoice Engine: CHUA CAI DUOC & set "VERIFY_OK=0" )

:: Tao shortcut Desktop
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\MagicVoice TTS Studio.lnk');$s.TargetPath='%~dp0Chay_MagicVoice.bat';$s.WorkingDirectory='%~dp0';$ico='%~dp0MagicVoice.ico';if(Test-Path $ico){$s.IconLocation=$ico};$s.Save()" >nul 2>&1
echo   [v] Shortcut Desktop: OK

:: Ghi flag da cai xong (setup_helper.py doc de skip reinstall lan sau)
!PY311! -c "open(r'%~dp0.deps_installed','w').write('!APP_VER!')" >nul 2>&1

echo.
echo  =======================================================
if "!VERIFY_OK!"=="1" (
    echo    CAI DAT HOAN CHINH - San sang su dung!
    echo    (Neu app bao loi DLL lan dau, dong va mo lai 1 lan)
) else (
    echo    CANH BAO: Mot so goi chua OK - xem thong bao phia tren
    echo    Chay lai CaiDat_MagicVoice.bat neu gap loi khi dung app
)
echo  =======================================================
echo.
echo  Dang mo MagicVoice TTS Studio...
timeout /t 2 /nobreak >nul
start "" "%~dp0Chay_MagicVoice.bat"
exit /b 0
