#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MagicVoice TTS Studio - Smart Installer
Tu dong phat hien GPU/CUDA va cai dung moi truong.
"""
import sys, os, subprocess, re, time, platform, traceback
from datetime import datetime

# CREATE_NO_WINDOW: an cua so console tren Windows
_CFLAGS = 0x08000000 if os.name == "nt" else 0

# ── ANSI colors (Windows 10+) ─────────────────────────────
import ctypes as _ct
try:
    _k32 = _ct.windll.kernel32
    _hout = _k32.GetStdHandle(-11)
    _mode = _ct.c_ulong(0)
    _k32.GetConsoleMode(_hout, _ct.byref(_mode))
    _k32.SetConsoleMode(_hout, _mode.value | 4)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
except Exception:
    pass
C = {
    "R": "\033[91m", "G": "\033[92m", "Y": "\033[93m",
    "B": "\033[94m", "C": "\033[96m", "W": "\033[97m",
    "D": "\033[90m", "X": "\033[0m",  "BO": "\033[1m",
}

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
LOG_FILE   = os.path.join(BASE_DIR, "install_log.txt")
_log_buf   = []
_fail_list = []   # packages that failed to install

# ─────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────
def _now(): return datetime.now().strftime("%H:%M:%S")

def _log(msg, level="info"):
    _log_buf.append(f"[{_now()}] [{level.upper():<5}] {msg}")
    if len(_log_buf) % 10 == 0:
        _flush_log()

def _flush_log():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(_log_buf))
    except Exception:
        pass

def _p(msg, col="W", indent=0, end="\n"):
    prefix = "  " * indent
    print(f"{C.get(col,'')}{prefix}{msg}{C['X']}", end=end, flush=True)
    _log(("  " * indent) + msg)

def ok(msg, indent=1):
    print(f"{'  '*indent}{C['G']}✓{C['X']} {msg}", flush=True)
    _log(f"{'  '*indent}OK: {msg}")

def warn(msg, indent=1):
    print(f"{'  '*indent}{C['Y']}⚠{C['X']} {msg}", flush=True)
    _log(f"WARN: {msg}", "warn")

def err(msg, indent=1):
    print(f"{'  '*indent}{C['R']}✗{C['X']} {msg}", flush=True)
    _log(f"ERR: {msg}", "error")

def info(msg, indent=1):
    print(f"{'  '*indent}{C['D']}→{C['X']} {msg}", flush=True)
    _log(f"    {msg}")

def section(title, step=""):
    bar = "─" * 56
    print(f"\n{C['C']}{bar}{C['X']}")
    tag = f"  [{step}] " if step else "  "
    print(f"{tag}{C['BO']}{title}{C['X']}")
    print(f"{C['C']}{bar}{C['X']}", flush=True)
    _log(f"\n{'='*20} {title} {'='*20}")

# ─────────────────────────────────────────────────────────
# GPU DETECTION
# ─────────────────────────────────────────────────────────
def detect_gpu():
    """
    Returns (driver_cuda_ver_str, gpu_name, compute_cap_float, driver_ver_str)
    Vi du: ("12.4", "NVIDIA GeForce RTX 4090", 8.9, "551.23")
    Returns (None, None, None, None) neu khong co GPU NVIDIA.
    """
    # Tim nvidia-smi: PATH truoc, sau do cac duong dan pho bien
    _NSMI_PATHS = [
        "nvidia-smi",
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\SysWOW64\nvidia-smi.exe",
    ]
    _nsmi = None
    for _p in _NSMI_PATHS:
        try:
            _tr = subprocess.run([_p], capture_output=True, timeout=8, creationflags=_CFLAGS)
            if _tr.returncode == 0:
                _nsmi = _p; break
        except Exception:
            continue
    if _nsmi is None:
        return None, None, None, None

    try:
        r = subprocess.run(
            [_nsmi],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
            creationflags=_CFLAGS
        )
        if r.returncode != 0:
            return None, None, None, None

        # CUDA version tu header: "| CUDA Version: 12.4 |"
        m = re.search(r"CUDA Version:\s*(\d+\.\d+)", r.stdout)
        driver_cuda = m.group(1) if m else None

        # GPU name + compute capability + driver version
        r2 = subprocess.run(
            [_nsmi,
             "--query-gpu=name,compute_cap,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
            creationflags=_CFLAGS
        )
        gpu_name    = None
        compute_cap = None
        driver_ver  = None
        if r2.returncode == 0 and r2.stdout.strip():
            lines = [l.strip() for l in r2.stdout.strip().splitlines() if l.strip()]
            if lines:
                parts = lines[0].rsplit(",", 2)
                if len(parts) == 3:
                    gpu_name   = parts[0].strip()
                    driver_ver = parts[2].strip()
                    try:
                        compute_cap = float(parts[1].strip())
                    except ValueError:
                        pass
                elif len(parts) == 2:
                    # fallback neu khong co driver_version
                    last_comma = lines[0].rfind(",")
                    gpu_name = lines[0][:last_comma].strip()
                    try:
                        compute_cap = float(lines[0][last_comma+1:].strip())
                    except ValueError:
                        pass

        # Fallback: neu query compute_cap that bai nhung nvidia-smi chinh hoat dong
        if gpu_name is None:
            r3 = subprocess.run(
                [_nsmi, "--query-gpu=name,driver_version",
                 "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace", creationflags=_CFLAGS
            )
            if r3.returncode == 0 and r3.stdout.strip():
                blines = [l.strip() for l in r3.stdout.strip().splitlines() if l.strip()]
                if blines:
                    bparts = blines[0].rsplit(",", 1)
                    gpu_name   = bparts[0].strip()
                    driver_ver = bparts[1].strip() if len(bparts) > 1 else None
                    compute_cap = _infer_compute_cap(gpu_name)
                    _log(f"compute_cap inferred {compute_cap} from '{gpu_name}'", "warn")

        return driver_cuda, gpu_name, compute_cap, driver_ver

    except FileNotFoundError:
        return None, None, None, None
    except Exception as e:
        _log(f"GPU detect error: {e}", "warn")
        return None, None, None, None


# ─────────────────────────────────────────────────────────
# PYTORCH BUILD SELECTION
# Dua vao compute_cap + driver CUDA de chon build chinh xac
# ─────────────────────────────────────────────────────────
# (min_driver_cuda_int, min_compute_cap, index_url, tag, desc)
_TORCH_BUILDS = [
    (128, 8.9,  "https://download.pytorch.org/whl/cu128", "cu128",
     "CUDA 12.8 — RTX 5xxx / Ada Lovelace"),
    (126, 7.5,  "https://download.pytorch.org/whl/cu126", "cu126",
     "CUDA 12.6"),
    (124, 7.5,  "https://download.pytorch.org/whl/cu124", "cu124",
     "CUDA 12.4"),
    (118, 5.0,  "https://download.pytorch.org/whl/cu118", "cu118",
     "CUDA 11.8 — RTX 2xxx / GTX 16xx / GTX 9xx"),
]

_CU118_URL  = "https://download.pytorch.org/whl/cu118"
_CU118_TAG  = "cu118"
_CU118_DESC = "CUDA 11.8 (auto-fallback cho GPU doi cu)"

def select_torch_build(driver_cuda_ver, compute_cap):
    """
    Tra ve (index_url, tag, desc).
    index_url = None nghia la CPU-only.
    """
    if compute_cap is None:
        return None, "cpu", "CPU (khong co GPU NVIDIA)"
    # Co GPU nhung khong doc duoc driver CUDA version → fallback cu118
    if driver_cuda_ver is None:
        if compute_cap >= 5.0:
            return _CU118_URL, _CU118_TAG, "CUDA 11.8 (fallback — khong doc duoc driver CUDA version)"
        return None, "cpu", f"CPU (GPU compute {compute_cap:.1f} — qua cu)"

    # Compute capability < 5.0 (Kepler tro ve) — cu118 khong ho tro
    if compute_cap < 5.0:
        return None, "cpu", f"CPU (GPU compute {compute_cap:.1f} — qua cu, khong ho tro CUDA PyTorch)"

    try:
        major, minor = driver_cuda_ver.split(".", 1)
        drv_int = int(major) * 10 + int(minor)   # "12.4" -> 124
    except Exception:
        # Khong doc duoc driver version — neu compute >= 5.0 thi thu cu118
        if compute_cap >= 5.0:
            return _CU118_URL, _CU118_TAG, _CU118_DESC
        return None, "cpu", "CPU (khong doc duoc CUDA version)"

    for min_drv, min_cc, url, tag, desc in _TORCH_BUILDS:
        if drv_int >= min_drv and compute_cap >= min_cc:
            return url, tag, desc

    # Driver qua cu nhung GPU co the chay cu118 — thu fallback
    if compute_cap >= 5.0:
        return _CU118_URL, _CU118_TAG, _CU118_DESC

    return None, "cpu", f"CPU (driver CUDA {driver_cuda_ver} qua cu)"


# ─────────────────────────────────────────────────────────
# PIP HELPERS
# ─────────────────────────────────────────────────────────
PY = sys.executable

def _pip(args, timeout=360, retries=2):
    """Chay pip voi retry. Tra ve True neu OK."""
    # --no-warn-script-location chi hop le voi 'pip install', khong dung cho uninstall/cache
    _extra = ["--quiet", "--disable-pip-version-check"]
    if args and args[0] == "install":
        _extra.append("--no-warn-script-location")
    cmd = [PY, "-m", "pip"] + args + _extra
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
                creationflags=_CFLAGS
            )
            if r.returncode == 0:
                _log(f"pip {' '.join(args[:4])}: OK")
                return True
            _log(f"pip attempt {attempt+1}: {r.stderr[-300:]}", "warn")
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
        except subprocess.TimeoutExpired:
            _log(f"pip timeout attempt {attempt+1}", "warn")
            if attempt < retries:
                time.sleep(5)
        except Exception as e:
            _log(f"pip exception: {e}", "warn")
    return False

def _infer_compute_cap(name):
    """Infer compute capability tu ten GPU khi nvidia-smi compute_cap query that bai."""
    n = name.upper()
    # RTX / Workstation moi
    if any(x in n for x in ["RTX 50", "BLACKWELL"]):          return 9.0
    if any(x in n for x in ["RTX 40", "ADA", "L40", "H100", "A100"]): return 8.9
    if any(x in n for x in ["RTX 30", "A30", "A40", "A10"]):  return 8.0
    if any(x in n for x in ["RTX 20", "GTX 16", "T4"]):       return 7.5
    if any(x in n for x in ["GTX 10", "MX 5", "P100", "V100"]): return 6.1
    # GTX 9xx / MX series trung binh
    if any(x in n for x in ["GTX 9", "GTX 750", "MX 4", "MX 3", "MX 2", "MX 1"]): return 5.2
    # GTX 8xx / 7xx / 6xx — compute 3.x-4.x, khong ho tro cu118+ → CPU mode
    if any(x in n for x in ["GTX 8", "GTX 7", "GTX 6", "GT 10", "GT 9", "GT 8",
                              "GT 7", "GT 6", "GT 5", "GT 4", "GT 3", "GT 2",
                              "NVS ", "QUADRO K", "QUADRO M1", "QUADRO M2"]):
        return 3.5  # duoi 5.0 → CPU mode
    # Mac dinh: an toan cho GPU NVIDIA khong nhan dang → thu cu118
    return 5.2


def _pip_with_dots(args, timeout=1200, retries=1):
    """Chay pip, in dau cham moi 10s de user biet chuong trinh van chay (dung cho torch ~2-3GB)."""
    import threading as _thr
    _stop = _thr.Event()
    def _dot_worker():
        elapsed = 0
        while not _stop.is_set():
            _stop.wait(10)
            if not _stop.is_set():
                elapsed += 10
                print(f"  {C['D']}... {elapsed}s{C['X']}", flush=True)
    t = _thr.Thread(target=_dot_worker, daemon=True)
    t.start()
    try:
        return _pip(args, timeout=timeout, retries=retries)
    finally:
        _stop.set()
        t.join(timeout=2)


def can_import(module):
    """Kiem tra import module co thanh cong khong."""
    try:
        r = subprocess.run(
            [PY, "-c", f"import {module}"],
            capture_output=True, timeout=30,
            creationflags=_CFLAGS
        )
        return r.returncode == 0
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# PYTORCH CHECK + INSTALL
# ─────────────────────────────────────────────────────────
def _torch_status():
    """Tra ve (installed, cuda_avail, version_str) hoac (False,False,None).
    Tach 2 buoc: (1) kiem tra torch co import duoc + lay version;
                 (2) kiem tra CUDA rieng — khong anh huong ket qua "installed".
    Tranh truong hop torch.cuda.is_available() raise exception → bao nham la chua cai.
    """
    # Buoc 1: chi import va lay version
    try:
        r = subprocess.run(
            [PY, "-c", "import torch; print(torch.__version__)"],
            capture_output=True, text=True, timeout=60,
            creationflags=_CFLAGS
        )
        if r.returncode != 0 or not r.stdout.strip():
            return False, False, None
        ver = r.stdout.strip().splitlines()[0].strip()
    except Exception:
        return False, False, None

    # Buoc 2: kiem tra CUDA (rieng, khong lam thi "installed" sai)
    cuda_ok = False
    try:
        r2 = subprocess.run(
            [PY, "-c",
             "import torch; print('yes' if torch.cuda.is_available() else 'no')"],
            capture_output=True, text=True, timeout=30,
            creationflags=_CFLAGS
        )
        if r2.returncode == 0:
            cuda_ok = r2.stdout.strip().lower() == "yes"
    except Exception:
        pass

    return True, cuda_ok, ver

def install_torch(index_url, tag, desc):
    """Gỡ torch cũ rồi cài đúng version. Trả về True nếu thành công."""
    info(f"Đang cài PyTorch ({desc})...")
    info("Gỡ phiên bản cũ nếu có...")
    _pip(["uninstall", "torch", "torchvision", "torchaudio", "-y"])
    time.sleep(1)

    info("Tải PyTorch (~2-3 GB lần đầu) — KHÔNG đóng cửa sổ, đang chạy ngầm...")
    # CPU fallback phai dung index-url pytorch.org/whl/cpu — torch 2.8.0 khong co tren PyPI
    if index_url:
        extra = ["--index-url", index_url]
    else:
        extra = ["--index-url", "https://download.pytorch.org/whl/cpu"]
    ok_install = _pip_with_dots(
        ["install", "torch==2.8.0", "torchaudio==2.8.0"] + extra,
        timeout=1200, retries=1
    )
    if not ok_install:
        return False

    inst, cuda_ok, ver = _torch_status()
    if not inst:
        # Kiem tra co phai loi DLL khong tuong thich (WinError 126)
        try:
            _tr = subprocess.run([PY, "-c", "import torch"],
                capture_output=True, text=True, timeout=30, creationflags=_CFLAGS)
            if "WinError 126" in _tr.stderr or "winerror 126" in _tr.stderr.lower():
                warn(f"DLL khong tuong thich voi he thong ({tag}) — se thu build thap hon")
        except Exception:
            pass
        return False
    if tag == "cpu" or cuda_ok:
        return True
    # torch cai duoc nhung CUDA khong hoat dong → warn, van tiep tuc
    warn(f"torch {ver} cai OK nhung CUDA chua xac nhan — co the can khoi dong lai")
    return True

def ensure_torch(index_url, tag, desc, has_gpu):
    """
    Kiem tra torch hien tai co phu hop khong.
    Chi cai lai neu can thiet.
    """
    inst, cuda_ok, ver = _torch_status()

    if inst and ver and ver.startswith("2.8"):
        # Torch 2.8.x da co — KHONG cai lai du CUDA status the nao
        # CUDA status sau cai co the chua chinh xac (DLL/driver can restart)
        # Tranh vong lap uninstall/reinstall khong can thiet
        if not has_gpu:
            ok(f"PyTorch {ver} (CPU mode)")
        elif cuda_ok:
            ok(f"PyTorch {ver} — CUDA ✓")
        else:
            ok(f"PyTorch {ver} — da co (CUDA se xac nhan sau khi khoi dong lai app)")
        return True
    elif inst:
        # Torch da co nhung sai phien ban (< 2.8) → cai lai
        warn(f"PyTorch {ver} — sai phien ban (can 2.8.x) — cai lai...")
    else:
        info("Chua co PyTorch — dang cai...")

    if install_torch(index_url, tag, desc):
        inst2, cuda2, ver2 = _torch_status()
        if inst2:
            cuda_str = "CUDA ✓" if cuda2 else "CPU mode"
            ok(f"PyTorch {ver2} — {cuda_str}")
            return True

    # CUDA build dau tien that bai → thu fallback theo thu tu AN TOAN (cu118 truoc)
    if tag != "cpu":
        _fallback_builds = [
            ("https://download.pytorch.org/whl/cu118", "cu118", "CUDA 11.8"),  # an toan nhat
            ("https://download.pytorch.org/whl/cu124", "cu124", "CUDA 12.4"),
            ("https://download.pytorch.org/whl/cu126", "cu126", "CUDA 12.6"),
        ]
        for _url, _tag, _desc in _fallback_builds:
            if _tag == tag:
                continue  # da thu roi
            warn(f"Thu CUDA fallback: {_desc}...")
            if install_torch(_url, _tag, _desc):
                inst3, cuda3, ver3 = _torch_status()
                if inst3:
                    cuda_str = "CUDA ✓" if cuda3 else "CPU mode"
                    ok(f"PyTorch {ver3} — {cuda_str}")
                    return True
        # Het CUDA → thu CPU
        warn("Tat ca CUDA that bai — thu CPU fallback...")
        if install_torch(None, "cpu", "CPU fallback"):
            ok("PyTorch (CPU fallback)")
            return True

    err("KHONG CAI DUOC PYTORCH!")
    _fail_list.append("torch")
    return False


# ─────────────────────────────────────────────────────────
# PACKAGE TABLE
# (import_name, pip_package, extra_pip_args, required)
# required=False: warn nhung khong dem vao loi
# ─────────────────────────────────────────────────────────
PACKAGES = [
    # (import_name, pip_package, extra_pip_args, required, always_upgrade)
    # always_upgrade=True: luon upgrade package nay, tranh loi tuong thich khi update app
    ("huggingface_hub","huggingface_hub", ["--upgrade"],            True,  True),   # can chinh xac de tai model
    ("firebase_admin", "firebase-admin",  [],                       True,  False),
    ("edge_tts",       "edge-tts",        [],                       True,  True),   # API thay doi giua cac phien ban
    ("soundfile",      "soundfile",       [],                       True,  False),
    ("scipy",          "scipy",           [],                       True,  False),
    ("PIL",            "Pillow",          [],                       True,  False),
    ("numpy",          "numpy",           [],                       True,  False),
    ("requests",       "requests",        [],                       True,  False),
    ("tqdm",           "tqdm",            [],                       True,  False),
    ("imageio_ffmpeg", "imageio-ffmpeg",  ["--force-reinstall"],    True,  True),   # can moi nhat de lay ffmpeg exe
    ("sounddevice",    "sounddevice",     [],                       False, False),  # optional
    ("pyaudiowpatch",  "pyaudiowpatch",   [],                       False, False),  # optional
    ("pydub",          "pydub",           [],                       False, False),  # optional
    ("psutil",         "psutil",          [],                       False, False),  # optional
]

def ensure_package(imp, pip_pkg, extra, required, always_upgrade=False, display_name=None):
    """Install package neu chua co. Tra ve True neu OK.
    always_upgrade=True: luon upgrade len latest du da co (dung cho package hay doi API)."""
    label = display_name or pip_pkg
    if can_import(imp):
        if always_upgrade:
            info(f"Nang cap {label} len phien ban moi nhat...")
            _pip(["install", pip_pkg, "--upgrade", "--no-cache-dir"] + extra, retries=1)
        ok(f"{label}")
        return True

    info(f"Cai {label}...")
    if _pip(["install", pip_pkg] + extra, retries=2):
        if can_import(imp):
            ok(f"{label} — da cai")
            return True

    # Retry upgrade
    _pip(["install", pip_pkg, "--upgrade", "--no-cache-dir"], retries=1)
    if can_import(imp):
        ok(f"{label} — da cai (upgrade)")
        return True

    if required:
        err(f"{label} — THAT BAI")
        _fail_list.append(pip_pkg)
    else:
        warn(f"{label} — khong cai duoc (tuy chon, khong anh huong chinh)")
    return False


# ─────────────────────────────────────────────────────────
# PREREQUISITES (VC++ Redist, .NET) — BUOC 0
# ─────────────────────────────────────────────────────────
def _winget_install(pkg_id, desc):
    """Cai package qua winget. Tra ve True neu OK hoac da co san."""
    try:
        r = subprocess.run(
            ["winget", "install", "--id", pkg_id,
             "--silent", "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True, timeout=180,
            creationflags=_CFLAGS
        )
        out = (r.stdout + r.stderr).lower()
        # winget bao "already installed" hoac "no applicable upgrade" -> da co
        if r.returncode == 0 or any(x in out for x in [
            "already installed", "no applicable upgrade",
            "da duoc cai dat", "khong tim thay goi nao"
        ]):
            ok(f"{desc}")
            return True
        warn(f"{desc} — winget exit {r.returncode}")
        return False
    except FileNotFoundError:
        warn("winget khong co — bo qua (Windows co the can update)")
        return False
    except Exception as e:
        warn(f"{desc} — {e}")
        return False

def _vcruntime_ok():
    """Kiem tra VCRUNTIME140.dll load duoc khong (can cho torch)."""
    import ctypes as _ct
    for dll in ["VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll"]:
        try:
            _ct.cdll.LoadLibrary(dll)
        except OSError:
            return False
    return True

def _dotnet4_ok():
    """Kiem tra .NET Framework 4.7.2+ da cai chua (qua registry)."""
    try:
        r = subprocess.run(
            ["reg", "query",
             r"HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full",
             "/v", "Release"],
            capture_output=True, text=True, timeout=5, creationflags=_CFLAGS
        )
        if r.returncode == 0:
            m = re.search(r"Release\s+REG_DWORD\s+0x([0-9a-fA-F]+)", r.stdout)
            if m:
                return int(m.group(1), 16) >= 461808  # 461808 = 4.7.2
    except Exception:
        pass
    return False

def ensure_prerequisites():
    """Cai VC++ Redist + .NET Framework neu chua co — can thiet de torch DLLs hoat dong."""
    # VC++ Redistributable
    if _vcruntime_ok():
        ok("Visual C++ Redistributable — da co")
    else:
        info("Thieu Visual C++ Redistributable — dang cai tu dong...")
        _winget_install("Microsoft.VCRedist.2015+.x64",
                        "Visual C++ Redistributable 2015+ x64")
        _winget_install("Microsoft.VCRedist.2015+.x86",
                        "Visual C++ Redistributable 2015+ x86")

    # .NET Framework 4
    if _dotnet4_ok():
        ok(".NET Framework 4 — da co")
    else:
        info("Dang cai .NET Framework 4...")
        _winget_install("Microsoft.DotNet.Framework.DeveloperPack_4",
                        ".NET Framework 4 Developer Pack")


# ─────────────────────────────────────────────────────────
# FFMPEG
# ─────────────────────────────────────────────────────────
def _ffmpeg_exe_ok(path):
    """Kiem tra mot duong dan ffmpeg co chay duoc khong."""
    try:
        r = subprocess.run([path, "-version"], capture_output=True,
                           timeout=8, creationflags=_CFLAGS)
        return r.returncode == 0
    except Exception:
        return False

def ensure_ffmpeg():
    portable = os.path.join(BASE_DIR, "ffmpeg_portable",
                            "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe")

    # 1. ffmpeg_portable da co san
    if os.path.exists(portable):
        ok("ffmpeg portable")
        return

    # 2. imageio-ffmpeg da cai va co ffmpeg exe hop le
    try:
        r = subprocess.run(
            [PY, "-c",
             "import imageio_ffmpeg, os; p=imageio_ffmpeg.get_ffmpeg_exe(); "
             "assert os.path.isfile(p)"],
            capture_output=True, timeout=20, creationflags=_CFLAGS
        )
        if r.returncode == 0:
            ok("ffmpeg (qua imageio-ffmpeg)")
            return
    except Exception:
        pass

    # 3. System ffmpeg (da trong PATH)
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                           timeout=8, creationflags=_CFLAGS)
        if r.returncode == 0:
            ok("ffmpeg (system PATH)")
            return
    except FileNotFoundError:
        pass

    # 4. Winget — nhanh, tin cay, khong can tai file lon (~7MB)
    info("Cai ffmpeg qua winget...")
    winget_ok = _winget_install("Gyan.FFmpeg", "ffmpeg (winget)")
    if winget_ok:
        # Winget cap nhat PATH system nhung process hien tai chua thay
        # → kiem tra cac vi tri winget thuong cai
        winget_paths = [
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        # Tim them qua where.exe (tim trong PATH moi cua system)
        try:
            wr = subprocess.run(["where", "ffmpeg"], capture_output=True,
                                text=True, timeout=8, creationflags=_CFLAGS)
            if wr.returncode == 0:
                for line in wr.stdout.strip().splitlines():
                    line = line.strip()
                    if line and os.path.isfile(line):
                        winget_paths.insert(0, line)
        except Exception:
            pass
        for wp in winget_paths:
            if _ffmpeg_exe_ok(wp):
                ok(f"ffmpeg winget — {wp}")
                return
        # Winget bao thanh cong nhung chua tim thay exe
        # → co the can khoi dong lai shell; van OK vi PATH se cap nhat
        ok("ffmpeg winget — se hoat dong sau khi khoi dong lai app")
        return

    # 5. Tai ffmpeg portable tu GitHub (~100MB, du phong cuoi)
    info("Tai ffmpeg portable tu GitHub (co the mat vai phut)...")
    try:
        import urllib.request, zipfile, tempfile
        url = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
               "latest/ffmpeg-master-latest-win64-gpl.zip")
        ffmpeg_dir = os.path.join(BASE_DIR, "ffmpeg_portable")
        os.makedirs(ffmpeg_dir, exist_ok=True)
        tmp = os.path.join(tempfile.gettempdir(), "ffmpeg_mv.zip")
        urllib.request.urlretrieve(url, tmp)
        with zipfile.ZipFile(tmp, "r") as z:
            z.extractall(ffmpeg_dir)
        try:
            os.remove(tmp)
        except Exception:
            pass
        if os.path.exists(portable):
            ok("ffmpeg portable — da tai tu GitHub")
            return
    except Exception as e:
        _log(f"ffmpeg GitHub download that bai: {e}", "warn")

    # 6. Force reinstall imageio-ffmpeg (co ffmpeg nho hon, ~30MB)
    info("Thu cai imageio-ffmpeg (ffmpeg nho)...")
    try:
        subprocess.run(
            [PY, "-m", "pip", "install", "imageio-ffmpeg",
             "--upgrade", "--force-reinstall", "--no-cache-dir", "--quiet"],
            capture_output=True, timeout=120, creationflags=_CFLAGS
        )
        r = subprocess.run(
            [PY, "-c",
             "import imageio_ffmpeg, os; p=imageio_ffmpeg.get_ffmpeg_exe(); "
             "assert os.path.isfile(p); print(p)"],
            capture_output=True, text=True, timeout=20, creationflags=_CFLAGS
        )
        if r.returncode == 0:
            ok(f"ffmpeg (imageio-ffmpeg reinstall)")
            return
    except Exception:
        pass

    warn("ffmpeg chua cai duoc — xuat file se dung WAV thay MP3\n"
         "   → Chay: winget install Gyan.FFmpeg trong CMD (admin)")


# ─────────────────────────────────────────────────────────
# FINAL VERIFICATION
# ─────────────────────────────────────────────────────────
VERIFY_IMPORTS = [
    ("torch",           "PyTorch"),
    ("torchaudio",      "torchaudio"),
    ("huggingface_hub", "huggingface-hub"),
    ("firebase_admin",  "firebase-admin"),
    ("edge_tts",        "edge-tts"),
    ("soundfile",       "soundfile"),
    ("scipy",           "scipy"),
    ("PIL",             "Pillow"),
    ("imageio_ffmpeg",  "imageio-ffmpeg"),
    ("numpy",           "numpy"),
    ("requests",        "requests"),
]

def final_verify():
    """Import kiem tra lan cuoi. Tra ve so goi loi."""
    failed_count = 0
    for imp, name in VERIFY_IMPORTS:
        if can_import(imp):
            ok(name)
        else:
            err(f"{name} — KHONG IMPORT DUOC")
            failed_count += 1
    return failed_count


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
def _download_model():
    """Download MagicVoice Engine ve cache HuggingFace neu chua co."""
    MODEL_ID     = "k2-fsa/OmniVoice"
    _MODEL_HASH  = "999c332499c708b116876ff5fe1aa5dd15f422ce"
    _BLOB_MAIN   = "730839316de585f4c8298ec0e1712efc10fb19c6fa4e36eb741cb8d51ebcf6aa"
    _BLOB_AUDIO  = "fe7c5e8785e0a05833e1bfc3e002ec7f55af21e306b2e7154a448c1f54ccfb0d"
    _BLOB_TOK    = "408f669b7e2b045fdf54201d815bd364e6667dbd845115da81239c40bc6dcfd1"
    _GH_BASE     = "https://github.com/buihuubac/magicvoice-releases/releases/download/v3.58"

    import pathlib as _pl, os as _os, shutil as _sh, tempfile as _tf, zipfile as _zf
    import urllib.request as _ur

    _hf_hub    = _pl.Path.home() / ".cache" / "huggingface" / "hub"
    cache_dir  = _hf_hub / "models--k2-fsa--OmniVoice"
    _blobs_dir = cache_dir / "blobs"
    _snap_dir  = cache_dir / "snapshots" / _MODEL_HASH

    _has_model = cache_dir.exists() and any(
        list(cache_dir.rglob("*.safetensors")) +
        list(cache_dir.rglob("*.bin")) +
        list(cache_dir.rglob("*.pt"))
    )
    if _has_model:
        ok("MagicVoice Engine da co trong cache — khong tai lai")
        return

    # ── Buoc 1: Thu tai tu GitHub Release (nhanh, on dinh) ──────────────
    info("Thu tai MagicVoice Engine tu GitHub Release (3 files, tong ~3.1 GB)...")
    _gh_files = [
        (_GH_BASE + "/MagicVoice_Model_main_p1.bin",        "model_p1.bin",    1_800_000_000),
        (_GH_BASE + "/MagicVoice_Model_main_p2.bin",        "model_p2.bin",      400_000_000),
        (_GH_BASE + "/MagicVoice_Model_audio_configs.zip",  "audio_configs.zip", 500_000_000),
    ]

    def _dl_with_progress(url, dest_path, label):
        _last = [0]
        def _hook(count, block, total):
            done = count * block
            if total > 0 and done - _last[0] >= 50_000_000:
                _last[0] = done
                pct = min(100, done * 100 // total)
                info(f"    {label}: {done/1e6:.0f}/{total/1e6:.0f} MB ({pct}%)")
        _ur.urlretrieve(url, str(dest_path), _hook)

    _tmp = _pl.Path(_tf.mkdtemp(prefix="mv_model_"))
    _gh_ok = False
    try:
        _all_ok = True
        for _url, _fname, _min_sz in _gh_files:
            _dest = _tmp / _fname
            info(f"  Tai {_fname}...")
            try:
                _dl_with_progress(_url, _dest, _fname)
                _actual = _dest.stat().st_size if _dest.exists() else 0
                if _actual < _min_sz:
                    warn(f"  {_fname}: {_actual/1e6:.0f} MB < yeu cau {_min_sz/1e6:.0f} MB — file co the chua duoc upload")
                    _all_ok = False
                    break
                ok(f"  {_fname}: {_actual/1e6:.0f} MB ✓")
            except Exception as _ue:
                warn(f"  Loi tai {_fname}: {_ue}")
                _all_ok = False
                break

        if _all_ok:
            info("Dang ghep va cai dat model vao cache...")
            _blobs_dir.mkdir(parents=True, exist_ok=True)
            _snap_dir.mkdir(parents=True, exist_ok=True)
            (_snap_dir / "audio_tokenizer").mkdir(exist_ok=True)

            # Join p1 + p2 → blob file model.safetensors
            _blob_main = _blobs_dir / _BLOB_MAIN
            info("  Ghep model.safetensors (1.9 GB + 0.55 GB)...")
            with open(str(_blob_main), "wb") as _fo:
                for _pf in [_tmp / "model_p1.bin", _tmp / "model_p2.bin"]:
                    with open(str(_pf), "rb") as _fi:
                        _sh.copyfileobj(_fi, _fo, length=64 * 1024 * 1024)
            ok(f"  model.safetensors: {_blob_main.stat().st_size/1e9:.2f} GB")

            # Tao hardlink trong snapshot → blob (Hub reuse khi sync online)
            _snap_main = _snap_dir / "model.safetensors"
            try:
                _os.link(str(_blob_main), str(_snap_main))
            except OSError:
                _sh.copy2(str(_blob_main), str(_snap_main))

            # Extract audio_configs.zip → snapshot (audio_tokenizer + config files)
            info("  Giai nen audio_tokenizer + config...")
            with _zf.ZipFile(str(_tmp / "audio_configs.zip"), "r") as _z:
                _z.extractall(str(_snap_dir))

            # Tao blob hardlink cho audio tokenizer model
            _blob_audio = _blobs_dir / _BLOB_AUDIO
            _snap_audio = _snap_dir / "audio_tokenizer" / "model.safetensors"
            if _snap_audio.exists() and not _blob_audio.exists():
                try:
                    _os.link(str(_snap_audio), str(_blob_audio))
                except OSError:
                    _sh.copy2(str(_snap_audio), str(_blob_audio))

            # Tao blob hardlink cho tokenizer.json
            _blob_tok = _blobs_dir / _BLOB_TOK
            _snap_tok = _snap_dir / "tokenizer.json"
            if _snap_tok.exists() and not _blob_tok.exists():
                try:
                    _os.link(str(_snap_tok), str(_blob_tok))
                except OSError:
                    pass

            # Set refs/main → MODEL_HASH
            (cache_dir / "refs").mkdir(exist_ok=True)
            (cache_dir / "refs" / "main").write_text(_MODEL_HASH, encoding="utf-8")

            ok("MagicVoice Engine da cai dat tu GitHub!")
            _gh_ok = True

    except Exception as _ge:
        warn(f"Loi khi cai dat tu GitHub: {_ge}")
    finally:
        _sh.rmtree(str(_tmp), ignore_errors=True)

    if _gh_ok:
        return

    # ── Buoc 2: Fallback HuggingFace / hf-mirror ────────────────────────
    info("GitHub that bai — thu tai tu HuggingFace (co the mat 10-30 phut)...")
    _dl_script = (
        "from huggingface_hub import snapshot_download; "
        f"p = snapshot_download('{MODEL_ID}', ignore_patterns=['*.onnx']); "
        "print('OK:', p)"
    )
    _ENDPOINTS = [
        ("https://huggingface.co",  "HuggingFace chinh"),
        ("https://hf-mirror.com",   "hf-mirror.com (mirror VN)"),
    ]
    for _ep_url, _ep_name in _ENDPOINTS:
        _env = {**_os.environ, "HF_ENDPOINT": _ep_url}
        info(f"Thu tai qua {_ep_name}...")
        try:
            result = subprocess.run(
                [PY, "-c", _dl_script],
                timeout=3600,
                creationflags=_CFLAGS,
                env=_env,
            )
            if result.returncode == 0:
                ok(f"Tai MagicVoice Engine hoan tat ({_ep_name})!")
                return
            warn(f"{_ep_name}: that bai (exit code {result.returncode})")
        except subprocess.TimeoutExpired:
            warn(f"{_ep_name}: Qua thoi gian (1 gio)")
        except Exception as _e:
            warn(f"{_ep_name}: {_e}")

    warn("Khong tai duoc model — khi mo app lan dau, bam 'Tai Model'.")


def _download_whisper():
    """Download Whisper model cho Clone Voice. Non-blocking neu that bai."""
    import pathlib as _pl
    hf_cache = _pl.Path.home() / ".cache" / "huggingface" / "hub"
    _whisper_models = [
        ("models--openai--whisper-large-v3-turbo", "openai/whisper-large-v3-turbo"),
        ("models--openai--whisper-large-v3",       "openai/whisper-large-v3"),
        ("models--openai--whisper-base",            "openai/whisper-base"),
        ("models--openai--whisper-small",           "openai/whisper-small"),
    ]
    for _dir_name, _model_id in _whisper_models:
        _wdir = hf_cache / _dir_name
        if _wdir.exists() and any(
            list(_wdir.rglob("*.bin")) +
            list(_wdir.rglob("*.safetensors")) +
            list(_wdir.rglob("*.pt"))
        ):
            ok(f"Whisper da co trong cache ({_dir_name.split('--')[-1]})")
            return True

    info("Whisper chua co — dang tai tu HuggingFace (can cho Clone Voice)...")
    import os as _os
    _WEPS = [
        ("https://huggingface.co", "HuggingFace chinh"),
        ("https://hf-mirror.com",  "hf-mirror.com"),
    ]
    for _dir_name, _model_id in _whisper_models:
        for _wep_url, _wep_name in _WEPS:
            _wenv = {**_os.environ, "HF_ENDPOINT": _wep_url}
            _short = _model_id.split("/")[-1]
            info(f"Thu tai {_short} qua {_wep_name}...")
            try:
                result = subprocess.run(
                    [PY, "-c",
                     f"from huggingface_hub import snapshot_download; "
                     f"snapshot_download('{_model_id}'); print('Whisper OK')"],
                    timeout=3600,
                    creationflags=_CFLAGS,
                    env=_wenv,
                )
                if result.returncode == 0:
                    ok(f"Whisper ({_short}) tai thanh cong qua {_wep_name}!")
                    return True
                warn(f"  {_short} / {_wep_name}: exit {result.returncode}")
            except subprocess.TimeoutExpired:
                warn(f"  {_short} / {_wep_name}: timeout 1 gio")
            except Exception as _e:
                warn(f"  {_short} / {_wep_name}: {str(_e)[:80]}")

    warn("Khong tai duoc Whisper — Clone Voice se yeu cau internet khi su dung lan dau.")
    warn("De su dung Clone Voice offline: mo app -> bam 'Tu dong sua moi truong' -> tu tai.")
    return False


def main():
    os.chdir(BASE_DIR)

    # ── Header ──────────────────────────────────────────────
    print(f"""
{C['C']}{'═'*56}
{C['BO']}   MagicVoice TTS Studio — Smart Installer v3.58{C['X']}
{C['D']}   Python : {sys.version.split()[0]}
   OS     : {platform.release()} {platform.machine()}
   Thu muc: {BASE_DIR}
{C['C']}{'═'*56}{C['X']}""")

    _log(f"Python: {sys.version}")
    _log(f"Platform: {platform.platform()}")
    _log(f"Base dir: {BASE_DIR}")

    # ── Buoc 0: Prerequisites (VC++ Redist) ─────────────────
    section("BUOC 0/7 — Moi truong he thong (VC++ Redist)", "0/6")
    ensure_prerequisites()

    # ── Buoc 1: GPU Detection ────────────────────────────────
    section("BUOC 1/7 — Phat hien GPU & chon CUDA", "1/6")
    driver_cuda, gpu_name, compute_cap, driver_ver = detect_gpu()

    has_gpu = gpu_name is not None
    if has_gpu:
        ok(f"GPU     : {gpu_name}")
        ok(f"Compute : {compute_cap}")
        ok(f"Driver  : {driver_ver or 'N/A'}  |  CUDA max: {driver_cuda or 'N/A'}")
        # Canh bao driver qua cu cho CUDA 11.8 (can >= 452.39)
        try:
            drv_major = float(driver_ver.split(".")[0]) if driver_ver else 999
            if drv_major < 452:
                warn(f"Driver {driver_ver} qua cu — CUDA 11.8 can driver >= 452.39")
                warn("Cap nhat driver tai: https://www.nvidia.com/Download/index.aspx")
        except Exception:
            pass
    else:
        warn("Khong phat hien GPU NVIDIA — se dung CPU mode")

    index_url, cuda_tag, cuda_desc = select_torch_build(driver_cuda, compute_cap)

    # GPU co mat nhung detection chon CPU:
    # - Neu compute >= 5.0 → co the thu cu118
    # - Neu compute < 5.0 (card doi qua cu, Kepler...) → giu CPU, khong thu CUDA
    if has_gpu and cuda_tag == "cpu":
        if compute_cap is not None and compute_cap >= 5.0:
            warn("GPU hop le nhung driver qua cu — tu dong thu cu118...")
            index_url, cuda_tag, cuda_desc = _CU118_URL, _CU118_TAG, _CU118_DESC
        else:
            warn(f"GPU compute {compute_cap} qua cu (< 5.0) — dung CPU mode (CUDA khong ho tro)")

    info(f"Chon build: {C['Y']}{cuda_desc}{C['X']}")

    # ── Kiem tra disk space truoc khi tai torch (~3GB) ──────
    try:
        import shutil as _sh
        _free_gb = _sh.disk_usage(str(BASE_DIR)).free / (1024**3)
        if _free_gb < 4.0:
            warn(f"O dia con {_free_gb:.1f} GB — can it nhat 4 GB de cai PyTorch!")
            warn("Vui long giai phong dung luong truoc khi tiep tuc.")
        else:
            ok(f"Dung luong o dia: {_free_gb:.1f} GB — du cho cai dat")
    except Exception:
        pass

    # ── Buoc 2: Upgrade pip + fix numpy ─────────────────────
    section("BUOC 2/7 — Nang cap pip & fix numpy", "2/6")
    _pip(["install", "--upgrade", "pip"], retries=1)
    ok("pip")
    # numpy 2.x gap loi tuong thich voi torch/omnivoice — pin 1.26.4
    info("Pin numpy==1.26.4 (tranh loi tuong thich)...")
    _pip(["install", "numpy==1.26.4", "--quiet"], retries=2)
    ok("numpy==1.26.4")

    # ── Buoc 3: PyTorch TRUOC (giai phap chuan) ──────────────
    # DUNG CHUAN: cai torch+torchaudio TRUOC, XONG moi cai packages.
    # Khi omnivoice duoc cai sau, pip thay torch da co → KHONG ghi de.
    section("BUOC 3/7 — PyTorch", "3/6")
    ensure_torch(index_url, cuda_tag, cuda_desc, has_gpu)

    # ── Buoc 4: Thu vien Python (SAU torch) ─────────────────
    section("BUOC 4/7 — Thu vien Python", "4/6")
    for entry in PACKAGES:
        imp, pip_pkg, extra, required, always_upgrade = entry[:5]
        display = entry[5] if len(entry) > 5 else None
        ensure_package(imp, pip_pkg, extra, required, always_upgrade, display_name=display)

    # Kiem tra torchaudio — neu omnivoice keo CPU build ve → chi cai lai torchaudio (KHONG cai lai torch)
    if has_gpu and index_url:
        _ta_r = subprocess.run(
            [PY, "-c", "import torchaudio; print(torchaudio.__version__)"],
            capture_output=True, text=True, timeout=20, creationflags=_CFLAGS)
        _ta_ver = _ta_r.stdout.strip()
        if _ta_r.returncode == 0 and "+cu" not in _ta_ver:
            warn(f"torchaudio {_ta_ver} mat CUDA build — cai lai torchaudio (chi torchaudio, giu torch)...")
            _pip(["install", "torchaudio==2.8.0",
                  "--index-url", index_url, "--force-reinstall", "--no-deps"], timeout=600)
        else:
            ok(f"torchaudio {_ta_ver} — CUDA build hop le")

    # ── Buoc 5: ffmpeg ──────────────────────────────────────
    section("BUOC 5/7 — ffmpeg", "5/7")
    ensure_ffmpeg()

    # ── Buoc 6: Download model TTS ──────────────────────────
    section("BUOC 6/7 — Tai MagicVoice Engine", "6/7")
    _download_model()

    # ── Buoc 7: Download Whisper (Clone Voice) ───────────────
    section("BUOC 7/7 — Tai Whisper model (cho Clone Voice)", "7/7")
    _download_whisper()

    # ── Kiem tra cuoi ───────────────────────────────────────
    section("KIEM TRA CUOI — Xac nhan moi truong")
    fail_count = final_verify()

    # Torch + CUDA info
    inst, cuda_ok, ver = _torch_status()
    if inst:
        if cuda_ok:
            r2 = subprocess.run(
                [PY, "-c",
                 "import torch; "
                 "print(torch.cuda.get_device_name(0), "
                 "torch.cuda.memory_reserved(0)//1024//1024, 'MB VRAM')"],
                capture_output=True, text=True, timeout=30,
                creationflags=_CFLAGS
            )
            gpu_info = r2.stdout.strip() if r2.returncode == 0 else ""
            ok(f"PyTorch {ver} — CUDA OK | {gpu_info}")
        else:
            ok(f"PyTorch {ver} — CPU mode")
            if has_gpu:
                warn("GPU co mat nhung CUDA khong hoat dong — tu dong thu cai lai...")
                _retry_builds = [
                    ("https://download.pytorch.org/whl/cu126", "cu126", "CUDA 12.6"),
                    ("https://download.pytorch.org/whl/cu124", "cu124", "CUDA 12.4"),
                    ("https://download.pytorch.org/whl/cu118", "cu118", "CUDA 11.8"),
                ]
                for _url, _tag, _desc in _retry_builds:
                    warn(f"  Thu lai: {_desc}...")
                    if install_torch(_url, _tag, _desc):
                        _, cuda_ok2, ver2 = _torch_status()
                        if cuda_ok2:
                            ok(f"PyTorch {ver2} — CUDA OK sau retry!")
                            break
                        warn(f"  {_desc}: torch cai OK nhung CUDA van khong nhan")
                else:
                    warn("Khong the kich hoat CUDA. Nguyen nhan co the:")
                    warn("  - Driver NVIDIA chua cap nhat (tai tai nvidia.com/download)")
                    warn("  - GPU khong tuong thich CUDA")
                    warn("Khi mo app: bam 'Tai Model' → tool se tu dong sua them.")

    # ── Tong ket ────────────────────────────────────────────
    # ===== BUOC CUOI CUNG: go torchvision (app khong dung truc tiep) =====
    # Phai o cuoi — SAU moi buoc cai — de khong bi keo lai boi dependency
    info("Xoa pip cache (tranh torchvision cu quay lai tu cache)...")
    _pip(["cache", "purge"])
    info("Go torchvision (app dung PYD truc tiep, khong can torchvision ngoai)...")
    _pip(["uninstall", "torchvision", "-y"])
    # Don folder rac ~* (invalid distribution tu lan cai do dang)
    try:
        import glob as _gl, shutil as _sh, site as _st
        for _sp2 in (_st.getsitepackages() or []) + [_st.getusersitepackages()]:
            for _junk in _gl.glob(os.path.join(_sp2, "~*")):
                _sh.rmtree(_junk, ignore_errors=True)
    except Exception:
        pass
    ok("torchvision da go (buoc cuoi) + don rac ~*")

    _flush_log()
    bar = "═" * 56
    print(f"\n{C['C']}{bar}{C['X']}")

    # Ghi .deps_installed neu torch OK — ke ca optional package fail
    # Tranh vong lap setup chay lai moi lan mo app chi vi optional package
    if "torch" not in _fail_list:
        try:
            import pathlib as _pl
            _ver_str = "ok"
            _vf = _pl.Path(BASE_DIR) / "version.txt"
            if _vf.exists():
                _ver_str = _vf.read_text("utf-8").strip() or "ok"
            (_pl.Path(BASE_DIR) / ".deps_installed").write_text(_ver_str)
        except Exception:
            pass

    if fail_count == 0 and "torch" not in _fail_list:
        print(f"{C['G']}{C['BO']}  ✅ CAI DAT HOAN TAT — Khong co loi!{C['X']}")
        print(f"  Tool san sang su dung.")
        print(f"{C['C']}{bar}{C['X']}\n")
        _log("=== THANH CONG ===")
        return 0
    elif "torch" not in _fail_list:
        msg = f"CANH BAO: {fail_count} goi phu chua cai duoc (app van chay duoc)"
        if _fail_list:
            msg += f" ({', '.join(_fail_list)})"
        print(f"{C['Y']}{C['BO']}  ⚠ {msg}{C['X']}")
        print(f"  App van hoat dong binh thuong. Xem chi tiet: install_log.txt")
        print(f"{C['C']}{bar}{C['X']}\n")
        _log(f"=== XONG VOI CANH BAO: {msg} ===", "warn")
        return 0  # Tra 0 de bao hieu thanh cong (torch OK, app chay duoc)
    else:
        msg = f"LOI NGHIEM TRONG: torch/core package that bai"
        if _fail_list:
            msg += f" ({', '.join(_fail_list)})"
        print(f"{C['R']}{C['BO']}  ✗ {msg}{C['X']}")
        print(f"  Xem chi tiet: install_log.txt")
        print(f"{C['C']}{bar}{C['X']}\n")
        _log(f"=== LOI: {msg} ===", "error")
        return 1


if __name__ == "__main__":
    try:
        code = main()
        sys.exit(code)
    except KeyboardInterrupt:
        warn("Da huy cai dat.")
        _flush_log()
        sys.exit(1)
    except Exception as exc:
        err(f"Loi khong mong doi: {exc}")
        _log(traceback.format_exc(), "error")
        _flush_log()
        sys.exit(2)
