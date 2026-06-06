#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MagicVoice TTS Studio - Smart Installer
Tu dong phat hien GPU/CUDA va cai dung moi truong.
"""
import sys, os, subprocess, re, time, platform, traceback
from datetime import datetime

# ── ANSI colors (Windows 10+) ─────────────────────────────
os.system("")  # Enable ANSI on Windows terminal
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
    Returns (driver_cuda_ver_str, gpu_name, compute_cap_float)
    Vi du: ("12.4", "NVIDIA GeForce RTX 4090", 8.9)
    Returns (None, None, None) neu khong co GPU NVIDIA.
    """
    try:
        r = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        if r.returncode != 0:
            return None, None, None

        # CUDA version tu header: "| CUDA Version: 12.4 |"
        m = re.search(r"CUDA Version:\s*(\d+\.\d+)", r.stdout)
        driver_cuda = m.group(1) if m else None

        # GPU name + compute capability
        r2 = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,compute_cap",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        gpu_name    = None
        compute_cap = None
        if r2.returncode == 0 and r2.stdout.strip():
            # Co the co nhieu GPU - lay GPU dau tien
            lines = [l.strip() for l in r2.stdout.strip().splitlines() if l.strip()]
            if lines:
                parts = lines[0].split(",")
                if len(parts) >= 2:
                    gpu_name = parts[0].strip()
                    try:
                        compute_cap = float(parts[1].strip())
                    except ValueError:
                        pass

        return driver_cuda, gpu_name, compute_cap

    except FileNotFoundError:
        return None, None, None   # nvidia-smi khong ton tai
    except Exception as e:
        _log(f"GPU detect error: {e}", "warn")
        return None, None, None


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
    (118, 6.0,  "https://download.pytorch.org/whl/cu118", "cu118",
     "CUDA 11.8 — RTX 2xxx / GTX 16xx"),
]

def select_torch_build(driver_cuda_ver, compute_cap):
    """
    Tra ve (index_url, tag, desc).
    index_url = None nghia la CPU-only.
    """
    if driver_cuda_ver is None or compute_cap is None:
        return None, "cpu", "CPU (khong co GPU NVIDIA)"

    # Compute capability qua cu (< 6.0 = Pascal va cu hon)
    if compute_cap < 6.0:
        return None, "cpu", f"CPU (GPU compute {compute_cap:.1f} — qua cu, khong ho tro CUDA PyTorch)"

    try:
        major, minor = driver_cuda_ver.split(".", 1)
        drv_int = int(major) * 10 + int(minor)   # "12.4" -> 124
    except Exception:
        return None, "cpu", "CPU (khong doc duoc CUDA version)"

    for min_drv, min_cc, url, tag, desc in _TORCH_BUILDS:
        if drv_int >= min_drv and compute_cap >= min_cc:
            return url, tag, desc

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
                timeout=timeout, encoding="utf-8", errors="replace"
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

def can_import(module):
    """Kiem tra import module co thanh cong khong."""
    try:
        r = subprocess.run(
            [PY, "-c", f"import {module}"],
            capture_output=True, timeout=30
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
            capture_output=True, text=True, timeout=60
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

    extra = ["--index-url", index_url] if index_url else []
    ok_install = _pip(
        ["install", "torch", "torchvision", "torchaudio"] + extra,
        timeout=600, retries=2
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

    if tag != "cpu":
        warn("Cai CUDA that bai — thu CPU fallback...")
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
    ("omnivoice",      "omnivoice",       ["--no-cache-dir"],       True),
    ("firebase_admin", "firebase-admin",  [],                       True),
    ("edge_tts",       "edge-tts",        [],                       True),
    ("soundfile",      "soundfile",       [],                       True),
    ("scipy",          "scipy",           [],                       True),
    ("PIL",            "Pillow",          [],                       True),
    ("numpy",          "numpy",           [],                       True),
    ("requests",       "requests",        [],                       True),
    ("tqdm",           "tqdm",            [],                       True),
    ("imageio_ffmpeg", "imageio-ffmpeg",  [],                       True),
    ("sounddevice",    "sounddevice",     [],                       False),  # optional
    ("pyaudiowpatch",  "pyaudiowpatch",   [],                       False),  # optional
    ("pydub",          "pydub",           [],                       False),  # optional
    ("psutil",         "psutil",          [],                       False),  # optional
]

def ensure_package(imp, pip_pkg, extra, required):
    """Install package neu chua co. Tra ve True neu OK."""
    if can_import(imp):
        ok(f"{pip_pkg}")
        return True

    info(f"Cai {pip_pkg}...")
    if _pip(["install", pip_pkg] + extra, retries=2):
        if can_import(imp):
            ok(f"{pip_pkg} — da cai")
            return True

    # Retry upgrade
    _pip(["install", pip_pkg, "--upgrade", "--no-cache-dir"], retries=1)
    if can_import(imp):
        ok(f"{pip_pkg} — da cai (upgrade)")
        return True

    if required:
        err(f"{pip_pkg} — THAT BAI")
        _fail_list.append(pip_pkg)
    else:
        warn(f"{pip_pkg} — khong cai duoc (tuy chon, khong anh huong chinh)")
    return False


# ─────────────────────────────────────────────────────────
# FFMPEG
# ─────────────────────────────────────────────────────────
def ensure_ffmpeg():
    portable = os.path.join(BASE_DIR, "ffmpeg_portable",
                            "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe")
    if os.path.exists(portable):
        ok("ffmpeg portable")
        return

    # imageio_ffmpeg co san?
    try:
        r = subprocess.run(
            [PY, "-c", "import imageio_ffmpeg; imageio_ffmpeg.get_ffmpeg_exe()"],
            capture_output=True, timeout=20
        )
        if r.returncode == 0:
            ok("ffmpeg (qua imageio-ffmpeg)")
            return
    except Exception:
        pass

    # System ffmpeg?
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=8)
        if r.returncode == 0:
            ok("ffmpeg (system)")
            return
    except FileNotFoundError:
        pass

    info("Tai ffmpeg portable...")
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
        os.remove(tmp)
        if os.path.exists(portable):
            ok("ffmpeg portable — da tai")
            return
    except Exception as e:
        _log(f"ffmpeg download failed: {e}", "warn")

    warn("ffmpeg chua cai duoc — xuat file se dung WAV thay MP3")


# ─────────────────────────────────────────────────────────
# FINAL VERIFICATION
# ─────────────────────────────────────────────────────────
VERIFY_IMPORTS = [
    ("torch",          "PyTorch"),
    ("torchaudio",     "torchaudio"),
    ("omnivoice",      "MagicVoice Engine"),
    ("firebase_admin", "firebase-admin"),
    ("edge_tts",       "edge-tts"),
    ("soundfile",      "soundfile"),
    ("scipy",          "scipy"),
    ("PIL",            "Pillow"),
    ("imageio_ffmpeg", "imageio-ffmpeg"),
    ("numpy",          "numpy"),
    ("requests",       "requests"),
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
def main():
    os.chdir(BASE_DIR)

    # ── Header ──────────────────────────────────────────────
    print(f"""
{C['C']}{'═'*56}
{C['BO']}   MagicVoice TTS Studio — Smart Installer v3.43{C['X']}
{C['D']}   Python : {sys.version.split()[0]}
   OS     : {platform.release()} {platform.machine()}
   Thu muc: {BASE_DIR}
{C['C']}{'═'*56}{C['X']}""")

    _log(f"Python: {sys.version}")
    _log(f"Platform: {platform.platform()}")
    _log(f"Base dir: {BASE_DIR}")

    # ── Buoc 1: GPU Detection ────────────────────────────────
    section("BUOC 1/5 — Phat hien GPU & chon CUDA", "1/5")
    driver_cuda, gpu_name, compute_cap = detect_gpu()

    has_gpu = gpu_name is not None
    if has_gpu:
        ok(f"GPU     : {gpu_name}")
        ok(f"Compute : {compute_cap}")
        ok(f"CUDA max: {driver_cuda} (ho tro boi driver)")
    else:
        warn("Khong phat hien GPU NVIDIA — se dung CPU mode")

    index_url, cuda_tag, cuda_desc = select_torch_build(driver_cuda, compute_cap)
    info(f"Chon build: {C['Y']}{cuda_desc}{C['X']}")

    # ── Buoc 2: Upgrade pip ──────────────────────────────────
    section("BUOC 2/5 — Nang cap pip", "2/5")
    _pip(["install", "--upgrade", "pip"], retries=1)
    ok("pip")

    # ── Buoc 3: PyTorch ─────────────────────────────────────
    section("BUOC 3/5 — PyTorch", "3/5")
    ensure_torch(index_url, cuda_tag, cuda_desc, has_gpu)

    # ── Buoc 4: Thu vien ────────────────────────────────────
    section("BUOC 4/5 — Thu vien Python", "4/5")
    for imp, pip_pkg, extra, required in PACKAGES:
        ensure_package(imp, pip_pkg, extra, required)

    # ── Buoc 5: ffmpeg ──────────────────────────────────────
    section("BUOC 5/5 — ffmpeg", "5/5")
    ensure_ffmpeg()

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
                capture_output=True, text=True, timeout=30
            )
            gpu_info = r2.stdout.strip() if r2.returncode == 0 else ""
            ok(f"PyTorch {ver} — CUDA OK | {gpu_info}")
        else:
            ok(f"PyTorch {ver} — CPU mode")

    # ── Tong ket ────────────────────────────────────────────
    _flush_log()
    bar = "═" * 56
    print(f"\n{C['C']}{bar}{C['X']}")
    if fail_count == 0 and "torch" not in _fail_list:
        print(f"{C['G']}{C['BO']}  ✅ CAI DAT HOAN TAT — Khong co loi!{C['X']}")
        print(f"  Tool san sang su dung.")
        print(f"{C['C']}{bar}{C['X']}\n")
        _log("=== THANH CONG ===")
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
