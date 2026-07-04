# magicvoice.py — Entry point cho MagicVoice TTS Studio v3.60
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

    # NOTE: Khong tu dong chay setup khi co update — chi chay setup khi PYD that su loi.
    # Neu update chi la thay file Python/config → PYD van load OK → app chay binh thuong.
    # setup_helper chi chay khi PYD import that bai (DLL, ImportError...).

    _status_lbl.config(text="Dang tai module chinh...")
    _splash.update()

    # Bao ve: PYD update mechanism tao ra magicvoice_core.py → Python import .py truoc .pyd → crash
    # Fix 1: Xoa file .py/.pyc + invalidate_caches (don dep tu lan truoc)
    # Fix 2: Cai PydFirst finder → luon load tu .pyd bat ke .py co ton tai hay khong
    try:
        import glob as _gl, importlib as _il, importlib.util as _ilu

        _core_py = _os.path.join(_base, "magicvoice_core.py")
        if _os.path.exists(_core_py):
            try: _os.remove(_core_py)
            except Exception: pass
        for _pyc in _gl.glob(_os.path.join(_base, "__pycache__", "magicvoice_core*")):
            try: _os.remove(_pyc)
            except Exception: pass
        _il.invalidate_caches()

        _pyd_path = _os.path.join(_base, "magicvoice_core.cp311-win_amd64.pyd")

        class _PydFirst:
            def find_spec(self, fullname, path, target=None):
                if fullname != "magicvoice_core":
                    return None
                if _os.path.exists(_pyd_path):
                    return _ilu.spec_from_file_location(fullname, _pyd_path)
                return None

        _sys.meta_path.insert(0, _PydFirst())
    except Exception:
        pass

    # Kiem tra torch version — neu sai (khong phai 2.8.x) thi chay setup truoc, tranh PYD
    # tu dong bat dialog "Tu dong sua" moi lan user dung Clone Voice / load model.
    # Chay VISIBLE (CREATE_NEW_CONSOLE) de user biet va khong tat app giua chung.
    try:
        _tr = _sp.run(
            [_sys.executable, "-c", "import torch; print(torch.__version__)"],
            capture_output=True, text=True, timeout=30
        )
        _tv = _tr.stdout.strip().split("+")[0] if _tr.returncode == 0 else ""
        if not _tv.startswith("2.8"):
            _setup_pre = _os.path.join(_base, "setup_helper.py")
            if _os.path.exists(_setup_pre):
                _status_lbl.config(text="Nang cap moi truong (lan dau, vui long cho)...")
                _splash.update()
                _sp.run([_sys.executable, _setup_pre],
                        creationflags=_sp.CREATE_NEW_CONSOLE, timeout=3600)
    except Exception:
        pass

    # Kiem tra torchvision — Clone Voice can torchvision==0.23.x
    # Neu chua co hoac sai version (khi update tu ban cu) → chay setup_helper de cai
    try:
        _tv2 = _sp.run(
            [_sys.executable, "-c",
             "import torchvision; print(torchvision.__version__)"],
            capture_output=True, text=True, timeout=20
        )
        _tv_installed = _tv2.stdout.strip().split("+")[0] if _tv2.returncode == 0 else ""
        if not _tv_installed.startswith("0.23"):
            _setup_tv = _os.path.join(_base, "setup_helper.py")
            if _os.path.exists(_setup_tv):
                _status_lbl.config(text="Cap nhat torchvision cho Clone Voice...")
                _splash.update()
                _sp.run([_sys.executable, _setup_tv],
                        creationflags=_sp.CREATE_NEW_CONSOLE, timeout=3600)
    except Exception:
        pass

    # Kiem tra model va set offline mode — gop 1 block de tranh loi bien chua dinh nghia
    # Fix v3.61: khach co torch+torchvision OK nhung model chua download
    # → torchvision check tren bo qua setup_helper → model khong bao gio duoc tai
    try:
        import pathlib as _pl2
        _hf_model = _pl2.Path.home() / ".cache" / "huggingface" / "hub" / "models--k2-fsa--OmniVoice"

        def _has_model_files():
            return _hf_model.exists() and any(
                list(_hf_model.rglob("*.safetensors")) +
                list(_hf_model.rglob("*.bin")) +
                list(_hf_model.rglob("*.pt"))
            )

        if not _has_model_files():
            # Model chua co → chay setup_helper (step 6: _download_model se xu ly)
            _setup_dl = _os.path.join(_base, "setup_helper.py")
            if _os.path.exists(_setup_dl):
                _status_lbl.config(text="Dang tai MagicVoice Engine (lan dau ~10-30 phut)...")
                _splash.update()
                _sp.run([_sys.executable, _setup_dl],
                        creationflags=_sp.CREATE_NEW_CONSOLE, timeout=3600)

        # Set offline mode neu model co trong cache (kiem tra lai sau khi setup xong)
        if _has_model_files():
            import os as _os2
            _os2.environ["HF_HUB_OFFLINE"] = "1"
    except Exception:
        pass

    # Kiem tra torchvision co load OK khong — neu DLL loi thi go (se duoc cai lai lan sau)
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
                _sp.run([_sys.executable, "-m", "pip", "cache", "purge"],
                        capture_output=True, timeout=30)
            except Exception:
                pass

    _repair_lock = _os.path.join(_base, ".repair_lock")

    def _needs_reinstall(exc):
        """Cac loi co the tu sua bang chay lai setup_helper: DLL, ImportError, thieu package."""
        _msg = str(exc).lower()
        _type = type(exc).__name__
        # Loi torchvision da duoc xu ly o buoc tren → khong trigger full reinstall
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
        # PYD load thanh cong — cap nhat .deps_installed voi version hien tai
        try:
            _ver_file  = _os.path.join(_base, "version.txt")
            _deps_file = _os.path.join(_base, ".deps_installed")
            _cur_ver   = open(_ver_file, encoding="utf-8").read().strip() if _os.path.exists(_ver_file) else ""
            if _cur_ver:
                open(_deps_file, "w", encoding="utf-8").write(_cur_ver)
        except Exception:
            pass
        # Xoa repair_lock neu con tu lan cu
        if _os.path.exists(_repair_lock):
            try: _os.remove(_repair_lock)
            except Exception: pass
        # Remove _NoTorchvision guard sau khi PYD da load xong.
        # PYD cai guard nay vao sys.meta_path trong __init__; guard block moi import torchvision.
        # Clone Voice (trong PYD) can torchvision → import bi chan → "torchvision disabled" → loop.
        # Sau khi PYD load xong, ta co the xoa guard de torchvision import binh thuong.
        try:
            _sys.meta_path = [_x for _x in _sys.meta_path
                              if type(_x).__name__ not in ("_NoTorchvision", "_BlockTorchvision")]
        except Exception:
            pass
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
