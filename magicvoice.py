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

    def _is_torch_dll_error(e):
        """Kiem tra loi co phai do torch DLL khong tuong thich (WinError 126)."""
        _msg = str(e).lower()
        return "winerror 126" in _msg and ("torch" in _msg or "c10" in _msg or "cuda" in _msg)

    try:
        from magicvoice_core import _main_entry
    except Exception as _e:
        # ── Fix v3.58: tu dong sua khi torch DLL loi (WinError 126) ──────────
        if _is_torch_dll_error(_e):
            try:
                _splash.destroy()
            except Exception:
                pass
            import tkinter as _tk3
            _r3 = _tk3.Tk(); _r3.withdraw()
            _ans = _tk3.messagebox.askyesno(
                "Loi Torch DLL",
                "Phat hien loi torch khong tuong thich voi may tinh nay.\n\n"
                "Nhan YES de tu dong sua va khoi dong lai app.\n"
                "Qua trinh co the mat 5-10 phut.\n\n"
                "Nhan NO de thoat.")
            _r3.destroy()
            if _ans:
                _setup2 = _os.path.join(_base, "setup_helper.py")
                if _os.path.exists(_setup2):
                    # Xoa .deps_installed de setup chay lai day du
                    _deps2 = _os.path.join(_base, ".deps_installed")
                    try: _os.remove(_deps2)
                    except Exception: pass
                    _sp.run([_sys.executable, _setup2], timeout=3600)
                # Khoi dong lai app sau khi sua
                _sp.Popen([_sys.executable, _os.path.abspath(__file__)])
            _sys.exit(0)
        # ── Loi khac: hien dialog thong thuong ───────────────────────────────
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
