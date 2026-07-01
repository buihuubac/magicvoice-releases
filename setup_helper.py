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
    (121, 7.5,  "https://download.pytorch.org/whl/cu121", "cu121",
     "CUDA 12.1 — RTX 3xxx / 4xxx"),
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
    cmd = [PY, "-m", "pip"] + args + [
        "--quiet", "--no-warn-script-location",
        "--disable-pip-version-check"
    ]
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
    if any(x in n for x in ["RTX 50", "BLACKWELL"]):
        return 9.0
    if any(x in n for x in ["RTX 40", "ADA", "L40", "H100", "A100"]):
        return 8.9
    if any(x in n for x in ["RTX 30", "A30", "A40", "A10"]):
        return 8.0
    if any(x in n for x in ["RTX 20", "GTX 16", "T4"]):
        return 7.5
    if any(x in n for x in ["GTX 10", "P100", "V100"]):
        return 6.1
    if any(x in n for x in ["GTX 9", "GTX 750"]):
        return 5.2
    return 6.1  # mac dinh an toan cho GPU NVIDIA khong nhan dang duoc (cu118 compatible)


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
    """Tra ve (installed, cuda_avail, version_str) hoac (False,False,None)."""
    try:
        r = subprocess.run(
            [PY, "-c",
             "import torch; "
             "c=torch.cuda.is_available(); "
             "g=torch.cuda.get_device_name(0) if c else 'none'; "
             "print(torch.__version__, c, g)"],
            capture_output=True, text=True, timeout=60,
            creationflags=_CFLAGS
        )
        if r.returncode != 0:
            return False, False, None
        parts = r.stdout.strip().split(" ", 2)
        ver      = parts[0] if len(parts) > 0 else "?"
        cuda_ok  = parts[1].lower() == "true" if len(parts) > 1 else False
        gpu_name = parts[2] if len(parts) > 2 else ""
        return True, cuda_ok, ver
    except Exception:
        return False, False, None

def install_torch(index_url, tag, desc):
    """Gỡ torch cũ rồi cài đúng version. Trả về True nếu thành công."""
    info(f"Đang cài PyTorch ({desc})...")
    info("Gỡ phiên bản cũ nếu có...")
    _pip(["uninstall", "torch", "torchvision", "torchaudio", "-y"])
    time.sleep(1)

    info("Tải PyTorch (~2-3 GB lần đầu) — KHÔNG đóng cửa sổ, đang chạy ngầm...")
    extra = ["--index-url", index_url] if index_url else []
    ok_install = _pip_with_dots(
        ["install", "torch", "torchvision", "torchaudio"] + extra,
        timeout=1200, retries=1
    )
    if not ok_install:
        return False

    inst, cuda_ok, ver = _torch_status()
    if not inst:
        return False
    if tag == "cpu" or cuda_ok:
        return True
    # torch cai duoc nhung CUDA khong hoat dong -> warn nhung khong fail
    warn(f"torch {ver} cai OK nhung CUDA chua xac nhan — co the can khoi dong lai")
    return True   # van coi la thanh cong de tiep tuc cai goi khac

def ensure_torch(index_url, tag, desc, has_gpu):
    """
    Kiem tra torch hien tai co phu hop khong.
    Chi cai lai neu can thiet.
    """
    inst, cuda_ok, ver = _torch_status()

    if inst:
        if not has_gpu:
            ok(f"PyTorch {ver} (CPU mode)")
            return True
        if cuda_ok:
            ok(f"PyTorch {ver} — CUDA ✓")
            return True
        # Co GPU nhung CUDA khong hoat dong -> cai lai
        warn(f"PyTorch {ver} da co nhung CUDA khong hoat dong — cai lai...")
    else:
        info("Chua co PyTorch — dang cai...")

    if install_torch(index_url, tag, desc):
        inst2, cuda2, ver2 = _torch_status()
        if inst2:
            cuda_str = "CUDA ✓" if cuda2 else "CPU mode"
            ok(f"PyTorch {ver2} — {cuda_str}")
            return True

    # CUDA build dau tien that bai → thu lan luot tat ca CUDA build con lai
    if tag != "cpu":
        _fallback_builds = [
            ("https://download.pytorch.org/whl/cu126", "cu126", "CUDA 12.6"),
            ("https://download.pytorch.org/whl/cu121", "cu121", "CUDA 12.1"),
            ("https://download.pytorch.org/whl/cu124", "cu124", "CUDA 12.4"),
            ("https://download.pytorch.org/whl/cu118", "cu118", "CUDA 11.8"),
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
    ("omnivoice",      "omnivoice",       ["--no-cache-dir"],       True,  True,  "MagicVoice Engine"),  # upgrade khi co phien ban moi
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
    ("omnivoice",       "MagicVoice Engine"),
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
    """Download model k2-fsa/OmniVoice ve cache HuggingFace neu chua co."""
    MODEL_ID = "k2-fsa/OmniVoice"
    import pathlib as _pl
    cache_dir = _pl.Path.home() / ".cache" / "huggingface" / "hub" / "models--k2-fsa--OmniVoice"
    if cache_dir.exists() and any(cache_dir.rglob("*.safetensors")):
        ok(f"Model da co tai: {cache_dir}")
        return
    info("Dang tai model TTS (co the mat 10-30 phut tuy toc do mang)...")
    info(f"Model: {MODEL_ID}")
    # Thu 1: HuggingFace (qua hf-mirror.com)
    import os as _os
    _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    _hf_ok = False
    try:
        info("Dang ket noi HuggingFace (hf-mirror.com)...")
        result = subprocess.run(
            [PY, "-c",
             "from huggingface_hub import snapshot_download; "
             f"p = snapshot_download('{MODEL_ID}'); "
             "print('OK:', p)"],
            timeout=3600,
            creationflags=_CFLAGS,
        )
        if result.returncode == 0:
            ok("Tai model tu HuggingFace hoan tat!")
            _hf_ok = True
        else:
            warn("HuggingFace that bai (returncode != 0)")
    except subprocess.TimeoutExpired:
        warn("HuggingFace: Qua thoi gian (1 gio)")
    except Exception as e:
        warn(f"HuggingFace loi: {e}")

    # Thu 2: Google Drive fallback neu HuggingFace loi
    if not _hf_ok:
        warn("Thu fallback: tai tu Google Drive...")
        _DRIVE_ID   = "13UA5GLL7we60qKJZzJ3wDAWBsG2E242-"
        _DRIVE_NAME = "MagicVoice_model.zip"
        _CACHE_DIR  = str(cache_dir.parent)
        try:
            import urllib.request as _ur, zipfile as _zf, tempfile as _tf
            _url = f"https://drive.usercontent.google.com/download?id={_DRIVE_ID}&export=download&confirm=t"
            _tmp = _tf.gettempdir() + "/" + _DRIVE_NAME
            info(f"Dang tai tu Google Drive (~vài GB)...")
            _ur.urlretrieve(_url, _tmp)
            if _os.path.getsize(_tmp) < 1_000_000:
                raise RuntimeError("File tai ve qua nho — co the bi chan boi Google")
            info("Dang giai nen vao cache...")
            import pathlib as _pl
            _pl.Path(_CACHE_DIR).mkdir(parents=True, exist_ok=True)
            with _zf.ZipFile(_tmp, "r") as _z:
                _z.extractall(_CACHE_DIR)
            _os.remove(_tmp)
            ok("Tai model tu Google Drive hoan tat!")
        except Exception as _de:
            warn(f"Google Drive that bai: {_de}")
            warn("Model se duoc tai khi mo app lan dau — bam 'Tai Model'.")


def main():
    os.chdir(BASE_DIR)

    # ── Header ──────────────────────────────────────────────
    print(f"""
{C['C']}{'═'*56}
{C['BO']}   MagicVoice TTS Studio — Smart Installer v3.54{C['X']}
{C['D']}   Python : {sys.version.split()[0]}
   OS     : {platform.release()} {platform.machine()}
   Thu muc: {BASE_DIR}
{C['C']}{'═'*56}{C['X']}""")

    _log(f"Python: {sys.version}")
    _log(f"Platform: {platform.platform()}")
    _log(f"Base dir: {BASE_DIR}")

    # ── Buoc 0: Prerequisites (VC++ Redist) ─────────────────
    section("BUOC 0/6 — Moi truong he thong (VC++ Redist)", "0/6")
    ensure_prerequisites()

    # ── Buoc 1: GPU Detection ────────────────────────────────
    section("BUOC 1/6 — Phat hien GPU & chon CUDA", "1/6")
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

    # GPU co mat nhung detection chon CPU → tu dong thu cu118 thay vi bo cuoc
    if has_gpu and cuda_tag == "cpu":
        warn("Khong xac dinh duoc CUDA build phu hop — tu dong thu cu118...")
        index_url, cuda_tag, cuda_desc = _CU118_URL, _CU118_TAG, _CU118_DESC

    info(f"Chon build: {C['Y']}{cuda_desc}{C['X']}")

    # ── Buoc 2: Upgrade pip ──────────────────────────────────
    section("BUOC 2/6 — Nang cap pip", "2/6")
    _pip(["install", "--upgrade", "pip"], retries=1)
    ok("pip")

    # ── Buoc 3: PyTorch ─────────────────────────────────────
    section("BUOC 3/6 — PyTorch", "3/6")
    ensure_torch(index_url, cuda_tag, cuda_desc, has_gpu)

    # ── Buoc 4: Thu vien ────────────────────────────────────
    section("BUOC 4/6 — Thu vien Python", "4/6")
    for entry in PACKAGES:
        imp, pip_pkg, extra, required, always_upgrade = entry[:5]
        display = entry[5] if len(entry) > 5 else None
        ensure_package(imp, pip_pkg, extra, required, always_upgrade, display_name=display)

    # ── Buoc 5: ffmpeg ──────────────────────────────────────
    section("BUOC 5/6 — ffmpeg", "5/6")
    ensure_ffmpeg()

    # ── Buoc 6: Download model TTS ──────────────────────────
    section("BUOC 6/6 — Tai model TTS (k2-fsa/OmniVoice)", "6/6")
    _download_model()

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
                    ("https://download.pytorch.org/whl/cu121", "cu121", "CUDA 12.1"),
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
    _flush_log()
    bar = "═" * 56
    print(f"\n{C['C']}{bar}{C['X']}")
    if fail_count == 0 and "torch" not in _fail_list:
        print(f"{C['G']}{C['BO']}  ✅ CAI DAT HOAN TAT — Khong co loi!{C['X']}")
        print(f"  Tool san sang su dung.")
        print(f"{C['C']}{bar}{C['X']}\n")
        _log("=== THANH CONG ===")
        try:
            import pathlib as _pl
            _ver_str = "ok"
            _vf = _pl.Path(BASE_DIR) / "version.txt"
            if _vf.exists():
                _ver_str = _vf.read_text("utf-8").strip() or "ok"
            (_pl.Path(BASE_DIR) / ".deps_installed").write_text(_ver_str)
        except Exception:
            pass
        return 0
    else:
        msg = f"CANH BAO: {fail_count} goi chua cai duoc"
        if _fail_list:
            msg += f" ({', '.join(_fail_list)})"
        print(f"{C['Y']}{C['BO']}  ⚠ {msg}{C['X']}")
        print(f"  Xem chi tiet: install_log.txt")
        print(f"{C['C']}{bar}{C['X']}\n")
        _log(f"=== XONG VOI CANH BAO: {msg} ===", "warn")
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
