# magicvoice.py — Entry point cho MagicVoice TTS Studio
if __name__ == "__main__":
    # Hien splash TRUOC khi import module nang (torch/torchaudio mat 30-60s)
    import tkinter as _tk
    _splash = _tk.Tk()
    _splash.overrideredirect(True)
    _splash.configure(bg="#0f1117")
    _sw, _sh = 340, 140
    _sx = (_splash.winfo_screenwidth() - _sw) // 2
    _sy = (_splash.winfo_screenheight() - _sh) // 2
    _splash.geometry(f"{_sw}x{_sh}+{_sx}+{_sy}")
    _splash.attributes("-topmost", True)
    _tk.Label(_splash, text="MagicVoice TTS Studio",
              font=("Segoe UI", 14, "bold"), bg="#0f1117", fg="#c084fc").pack(pady=(18, 4))
    _status_lbl = _tk.Label(_splash, text="Dang khoi dong...",
              font=("Segoe UI", 10), bg="#0f1117", fg="#94a3b8")
    _status_lbl.pack()
    _tk.Label(_splash, text="(Lan dau co the mat 30-60 giay)",
              font=("Segoe UI", 8), bg="#0f1117", fg="#475569").pack(pady=(2, 0))
    _splash.update()

    import os as _os, sys as _sys, traceback as _tb, subprocess as _sp
    _base = _os.path.dirname(_os.path.abspath(__file__))
    _log  = _os.path.join(_base, "error_log.txt")

    # ── Auto-setup sau khi update ──────────────────────────────
    # So sanh version.txt vs .deps_installed
    # Neu khac nhau (vua update) → tu dong chay setup_helper.py
    try:
        _ver_file  = _os.path.join(_base, "version.txt")
        _deps_file = _os.path.join(_base, ".deps_installed")
        _cur_ver   = open(_ver_file,  encoding="utf-8").read().strip() if _os.path.exists(_ver_file)  else ""
        _dep_ver   = open(_deps_file, encoding="utf-8").read().strip() if _os.path.exists(_deps_file) else ""
        if _cur_ver and _dep_ver != _cur_ver:
            _status_lbl.config(text=f"Cap nhat v{_cur_ver} — dang cai dat...")
            _splash.update()
            _setup = _os.path.join(_base, "setup_helper.py")
            if _os.path.exists(_setup):
                _sp.run([_sys.executable, _setup], timeout=3600)
    except Exception:
        pass  # Neu setup that bai, app van khoi dong binh thuong
    # ──────────────────────────────────────────────────────────

    _status_lbl.config(text="Dang tai module chinh...")
    _splash.update()

    # Neu model da trong cache → dung offline mode, tranh HF API timeout khi load PYD
    try:
        import pathlib as _pl2
        _hf_model = _pl2.Path.home() / ".cache" / "huggingface" / "hub" / "models--k2-fsa--OmniVoice"
        if _hf_model.exists() and any(
            list(_hf_model.rglob("*.safetensors")) +
            list(_hf_model.rglob("*.bin")) +
            list(_hf_model.rglob("*.pt"))
        ):
            import os as _os2
            _os2.environ["HF_HUB_OFFLINE"] = "1"
    except Exception:
        pass

    # Go torchvision neu gay loi tuong thich — app khong dung torchvision
    # Lam truoc khi import PYD, khong can restart
    try:
        import torchvision as _tv_test
        del _tv_test
    except ImportError:
        pass  # Chua cai → OK
    except Exception as _tv_err:
        _tv_msg = str(_tv_err).lower()
        if any(k in _tv_msg for k in
               ("circular import", "cannot import name", "entry point", "winerror 126", "dll")):
            try:
                _status_lbl.config(text="Go torchvision loi — dang xu ly...")
                _splash.update()
                _sp.run([_sys.executable, "-m", "pip", "uninstall", "torchvision", "-y"],
                        capture_output=True, timeout=60)
            except Exception:
                pass

    _repair_lock = _os.path.join(_base, ".repair_lock")

    def _needs_reinstall(exc):
        """Cac loi co the tu sua bang chay lai setup_helper: DLL, ImportError, thieu package."""
        _msg = str(exc).lower()
        _type = type(exc).__name__
        # Loi torchvision (circular import, entry point) da duoc xu ly o buoc tren
        # → khong trigger full reinstall
        if "torchvision" in _msg:
            return False
        if "winerror 126" in _msg or "dll load failed" in _msg:
            return True
        if _type in ("ImportError", "ModuleNotFoundError"):
            return True
        _pkgs = ("torch", "torchaudio", "transformers",
                 "k2", "onnx", "numpy", "scipy", "librosa", "soundfile")
        if any(p in _msg for p in _pkgs):
            return True
        return False

    try:
        from magicvoice_core import _main_entry
        if _os.path.exists(_repair_lock):
            try: _os.remove(_repair_lock)
            except Exception: pass
    except Exception as _e:
        if _needs_reinstall(_e):
            if _os.path.exists(_repair_lock):
                # Da tu sua roi nhung van loi → bao loi va thoat
                try: _os.remove(_repair_lock)
                except Exception: pass
                try: _splash.destroy()
                except Exception: pass
                with open(_log, "w", encoding="utf-8") as _f:
                    _f.write(_tb.format_exc())
                import tkinter as _tk2
                _r = _tk2.Tk(); _r.withdraw()
                _tk2.messagebox.showerror(
                    "Loi Khoi Dong",
                    f"Da tu sua nhung van loi:\n{_e}\n\n"
                    f"Vui long lien he ho tro: Zalo 0985 483 623\n"
                    f"Hoac xem log: {_log}")
                _r.destroy()
                _sys.exit(1)
            # Chua thu sua → tu dong sua va restart (khong can hoi)
            try: open(_repair_lock, "w").close()
            except Exception: pass
            _deps2 = _os.path.join(_base, ".deps_installed")
            try: _os.remove(_deps2)
            except Exception: pass
            _setup2 = _os.path.join(_base, "setup_helper.py")
            _status_lbl.config(text="Phat hien loi — dang tu dong sua...")
            _splash.update()
            if _os.path.exists(_setup2):
                _sp.run([_sys.executable, _setup2],
                        creationflags=_sp.CREATE_NEW_CONSOLE, timeout=3600)
            _sp.Popen([_sys.executable, _os.path.abspath(__file__)])
            _sys.exit(0)
        # Loi khong the tu sua → hien dialog thong thuong
        try: _splash.destroy()
        except Exception: pass
        with open(_log, "w", encoding="utf-8") as _f:
            _f.write(_tb.format_exc())
        import tkinter as _tk2
        _r = _tk2.Tk(); _r.withdraw()
        _tk2.messagebox.showerror(
            "Loi Khoi Dong",
            f"Khong the tai module chinh:\n{_e}\n\nXem: {_log}\n\n"
            "Thu chay lai CaiDat_MagicVoice.bat de sua.")
        _r.destroy()
        _sys.exit(1)

    try:
        _splash.destroy()
    except Exception:
        pass

    _main_entry()
