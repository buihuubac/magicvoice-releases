"""
magicvoice_gui.py — BOOTSTRAP file v3.36 (cho khach v3.35 migrate len v3.36)

Khi khach v3.35 bam "Cap nhat ngay":
- Logic cu trong v3.35 tai file nay ve va de magicvoice_gui.py
- App v3.35 restart -> chay file nay
- File nay tai toan bo bo v3.36 (3 .pyd + magicvoice.py + updater.bat + ...)
- Sau khi tai xong: chay magicvoice.py (entry point v3.36) -> exit

File nay CHI dung 1 lan duy nhat. Sau khi migrate, magicvoice.py se thay the no.
"""
import os
import sys
import time
import shutil
import urllib.request
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# ============================================================
# CAU HINH
# ============================================================
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
APP_DIR = Path(__file__).resolve().parent


def _bootstrap_download_and_launch():
    """Tai bo v3.36 ve, chay magicvoice.py, exit."""

    # GUI progress
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

    # Center window
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
    # Tai tung file thanh .new (an toan, khong de file dang chay)
    # ============================================================
    total = len(FILES_V336)
    downloaded_new = []  # de rollback neu loi

    try:
        for idx, fname in enumerate(FILES_V336, 1):
            status_var.set(f"[{idx}/{total}] Dang tai {fname}...")
            root.update()

            url = f"{BASE_URL}/{fname}"
            new_path = APP_DIR / (fname + ".new")
            urllib.request.urlretrieve(url, str(new_path))

            # Verify file khong rong
            if new_path.stat().st_size == 0:
                raise RuntimeError(f"File {fname} tai ve rong (0 bytes)")

            downloaded_new.append(new_path)

            bar.config(width=int(380 * idx / total))
            root.update()

    except Exception as e:
        # Rollback: xoa cac file .new da tai
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
    # Rename .new -> file thuc (vi day la lan dau, chua co .pyd cu de bi lock)
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
    # Xoa cac file .py source cu (khong can nua vi da co .pyd)
    # KHONG xoa magicvoice_gui.py vi NO chinh la file dang chay
    # -> Se duoc magicvoice.py xoa o lan sau (hoac de y nhu cuoi cung)
    # ============================================================
    for old_file in ["auth_manager.py", "license_guard.py"]:
        try:
            old_path = APP_DIR / old_file
            if old_path.exists():
                old_path.unlink()
        except Exception:
            pass  # Khong xoa duoc cung khong sao, .pyd se duoc uu tien load

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
    # Chay magicvoice.py (entry point v3.36)
    # ============================================================
    bar.config(width=380)
    status_var.set("Cap nhat thanh cong! Dang khoi dong app...")
    root.update()
    time.sleep(1)
    root.destroy()

    # Chay magicvoice.py va exit
    import subprocess
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
        # Last-resort error handling
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
