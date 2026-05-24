"""
magicvoice_gui.py — BOOTSTRAP v3.36 (v2 - chong voi lap)

Logic:
- Lan 1: Tai bo v3.36 day du, sua launcher (.bat/.vbs) tro magicvoice.py, chay magicvoice.py
- Lan 2+: Thay flag .migrated_v336 -> chi chay magicvoice.py, KHONG tai lai

File nay duoc tai ve boi auto-update v3.35 va de magicvoice_gui.py cu.
Khi v3.35 restart -> chay file nay -> migrate.
"""
import os
import sys
import time
import shutil
import urllib.request
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
MIGRATION_FLAG = APP_DIR / ".migrated_v336"

# ============================================================
# CHECK FLAG: Neu da migrate -> chi chay magicvoice.py, exit
# ============================================================
if MIGRATION_FLAG.exists():
    magicvoice_py = APP_DIR / "magicvoice.py"
    if magicvoice_py.exists():
        # Chay magicvoice.py va exit ngay (khong show GUI bootstrap nua)
        subprocess.Popen([sys.executable, str(magicvoice_py)], cwd=str(APP_DIR))
        sys.exit(0)
    # Neu vi mot ly do nao do magicvoice.py bi xoa -> tiep tuc tai lai (recover)

# ============================================================
# LAN DAU MIGRATE: GUI progress + download
# ============================================================
import tkinter as tk
from tkinter import messagebox

BASE_URL = "https://raw.githubusercontent.com/buihuubac/magicvoice-releases/main"
FILES_V336 = [
    "magicvoice_core.cp311-win_amd64.pyd",
    "auth_manager.cp311-win_amd64.pyd",
    "license_guard.cp311-win_amd64.pyd",
    "magicvoice.py",
    "script_processor.py",
    "updater.bat",
    "version.txt",
]


def _patch_launcher_files():
    """Sua cac file launcher cua v3.35 (Chay_MagicVoice.bat, MagicVoice.vbs, MagicVoice.bat)
    de tro toi magicvoice.py thay vi magicvoice_gui.py.
    Tranh khach bam shortcut Desktop -> chay magicvoice_gui.py (bootstrap) -> lap vo han.
    """
    LAUNCHER_FILES = ["Chay_MagicVoice.bat", "MagicVoice.bat", "MagicVoice.vbs"]
    patched = []
    for fname in LAUNCHER_FILES:
        fpath = APP_DIR / fname
        if not fpath.exists():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            if "magicvoice_gui.py" in content:
                new_content = content.replace("magicvoice_gui.py", "magicvoice.py")
                # Backup file goc 1 lan
                bak = fpath.with_suffix(fpath.suffix + ".v335.bak")
                if not bak.exists():
                    shutil.copy(str(fpath), str(bak))
                fpath.write_text(new_content, encoding="utf-8")
                patched.append(fname)
        except Exception as e:
            print(f"[Bootstrap] Khong sua duoc {fname}: {e}")
    return patched


def _bootstrap_download_and_launch():
    """Tai bo v3.36, sua launcher, tao flag, chay magicvoice.py, exit."""

    root = tk.Tk()
    root.title("MagicVoice — Cap nhat len v3.36")
    root.geometry("440x200")
    root.configure(bg="white")
    root.resizable(False, False)

    try:
        ico = APP_DIR / "MagicVoice.ico"
        if ico.exists():
            root.iconbitmap(str(ico))
    except Exception:
        pass

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 440) // 2
    y = (root.winfo_screenheight() - 200) // 2
    root.geometry(f"440x200+{x}+{y}")

    tk.Label(root, text="Dang cap nhat MagicVoice len v3.36...",
             font=("Segoe UI", 12, "bold"),
             bg="white", fg="#6c63ff", pady=14).pack()

    status_var = tk.StringVar(value="Chuan bi tai file...")
    tk.Label(root, textvariable=status_var,
             font=("Segoe UI", 9),
             bg="white", fg="#666").pack()

    bar_bg = tk.Frame(root, bg="#e0e0e0", height=10, width=380)
    bar_bg.pack(pady=12)
    bar = tk.Frame(bar_bg, bg="#6c63ff", height=10, width=0)
    bar.place(x=0, y=0, height=10)

    tk.Label(root, text="Vui long khong tat. App se tu khoi dong lai khi xong.",
             font=("Segoe UI", 8),
             bg="white", fg="#999").pack(pady=4)

    root.update()

    # ============================================================
    # Tai tung file vao .new (an toan)
    # ============================================================
    total = len(FILES_V336)
    downloaded_new = []

    try:
        for idx, fname in enumerate(FILES_V336, 1):
            status_var.set(f"[{idx}/{total}] Dang tai {fname}...")
            root.update()

            url = f"{BASE_URL}/{fname}"
            new_path = APP_DIR / (fname + ".new")
            urllib.request.urlretrieve(url, str(new_path))

            if new_path.stat().st_size == 0:
                raise RuntimeError(f"File {fname} tai ve rong (0 bytes)")

            downloaded_new.append(new_path)

            bar.config(width=int(380 * idx / total))
            root.update()

    except Exception as e:
        # Rollback
        for p in downloaded_new:
            try: p.unlink()
            except: pass
        for fname in FILES_V336:
            try: (APP_DIR / (fname + ".new")).unlink()
            except: pass
        root.destroy()
        messagebox.showerror(
            "Loi cap nhat",
            f"Khong tai duoc file:\n{e}\n\n"
            "Kiem tra ket noi internet va thu lai.\n"
            "Neu loi tiep dien, lien he Zalo: 0985 483 623"
        )
        sys.exit(1)

    # ============================================================
    # Rename .new -> file thuc
    # ============================================================
    status_var.set("Dang setup cac file moi...")
    root.update()

    try:
        for fname in FILES_V336:
            new_path = APP_DIR / (fname + ".new")
            final_path = APP_DIR / fname
            if final_path.exists():
                try: final_path.unlink()
                except: pass
            new_path.rename(final_path)
    except Exception as e:
        root.destroy()
        messagebox.showerror(
            "Loi cap nhat",
            f"Khong setup duoc file moi:\n{e}\n\n"
            "Vui long tai lai bo cai moi nhat tu Zalo: 0985 483 623"
        )
        sys.exit(1)

    # ============================================================
    # SUA LAUNCHER -> tro magicvoice.py
    # ============================================================
    status_var.set("Dang cap nhat shortcut...")
    root.update()
    patched = _patch_launcher_files()
    print(f"[Bootstrap] Da sua launcher: {patched}")

    # ============================================================
    # Xoa cache cu
    # ============================================================
    try:
        pycache = APP_DIR / "__pycache__"
        if pycache.exists():
            shutil.rmtree(str(pycache), ignore_errors=True)
    except Exception:
        pass

    try:
        deps_flag = APP_DIR / ".deps_installed"
        if deps_flag.exists():
            deps_flag.unlink()
    except Exception:
        pass

    # ============================================================
    # TAO FLAG MIGRATION DA HOAN TAT
    # ============================================================
    try:
        MIGRATION_FLAG.write_text("3.36", encoding="utf-8")
    except Exception as e:
        print(f"[Bootstrap] Khong tao duoc flag: {e}")

    # ============================================================
    # Chay magicvoice.py va exit
    # ============================================================
    bar.config(width=380)
    status_var.set("Cap nhat thanh cong! Dang khoi dong app...")
    root.update()
    time.sleep(1)
    root.destroy()

    magicvoice_py = APP_DIR / "magicvoice.py"
    subprocess.Popen(
        [sys.executable, str(magicvoice_py)],
        cwd=str(APP_DIR),
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        _bootstrap_download_and_launch()
    except Exception as e:
        try:
            import traceback
            log_file = APP_DIR / "bootstrap_error.log"
            log_file.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror(
                "Loi cap nhat v3.36",
                f"Co loi xay ra khi cap nhat:\n{e}\n\n"
                "Vui long lien he Zalo: 0985 483 623 de duoc ho tro."
            )
        except Exception:
            pass
        sys.exit(1)
