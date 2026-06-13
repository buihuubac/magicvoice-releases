# magicvoice.py — Entry point cho MagicVoice TTS Studio
if __name__ == "__main__":
    # Hien splash TRUOC khi import module nang (torch/torchaudio mat 30-60s)
    import tkinter as _tk
    _splash = _tk.Tk()
    _splash.overrideredirect(True)
    _splash.configure(bg="#0f1117")
    _sw, _sh = 340, 120
    _sx = (_splash.winfo_screenwidth() - _sw) // 2
    _sy = (_splash.winfo_screenheight() - _sh) // 2
    _splash.geometry(f"{_sw}x{_sh}+{_sx}+{_sy}")
    _splash.attributes("-topmost", True)
    _tk.Label(_splash, text="MagicVoice TTS Studio",
              font=("Segoe UI", 14, "bold"), bg="#0f1117", fg="#c084fc").pack(pady=(18, 4))
    _tk.Label(_splash, text="Dang khoi dong...",
              font=("Segoe UI", 10), bg="#0f1117", fg="#94a3b8").pack()
    _tk.Label(_splash, text="(Lan dau co the mat 30-60 giay)",
              font=("Segoe UI", 8), bg="#0f1117", fg="#475569").pack(pady=(2, 0))
    _splash.update()

    import os as _os, sys as _sys, traceback as _tb, pathlib as _pl
    _log = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "error_log.txt")

    # Neu vua update xong, file .pyd.new ton tai — doi ten truoc khi import
    _here = _pl.Path(_os.path.abspath(__file__)).parent
    _pyd  = _here / "magicvoice_core.cp311-win_amd64.pyd"
    _new_pyd = _pl.Path(str(_pyd) + ".new")
    if _new_pyd.exists():
        try:
            if _pyd.exists():
                _pyd.unlink()
            _new_pyd.rename(_pyd)
        except Exception:
            pass

    try:
        from magicvoice_core import _main_entry
    except Exception as _e:
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
