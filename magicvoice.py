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
    # FIX v3.65 (28): mot nguyen nhan RAT PHO BIEN gay "[WinError 1114] DLL
    # initialization routine failed" khi torch load c10.dll tren Windows la
    # xung dot giua 2 ban Intel OpenMP runtime (libiomp5md.dll) - 1 ban di
    # kem torch, 1 ban di kem numpy/MKL. Day la workaround CHINH THUC duoc
    # PyTorch/Intel khuyen dung (KHONG phai giai phap tam) - dat truoc khi
    # import bat cu thu gi dung torch. Dat o day (truoc ca subprocess setup
    # o duoi) de propagate sang ca tien trinh setup_helper.py neu no chay.
    _os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    _base = _os.path.dirname(_os.path.abspath(__file__))
    _log  = _os.path.join(_base, "error_log.txt")

    # FIX v3.65 (30): truoc day "_sp.run(setup_helper.py)" va "import
    # magicvoice_core" chay THANG tren main thread, khong bom (pump) vong lap
    # Tk trong luc cho (co the mat vai chuc giay - vai phut lan dau) - Windows
    # thay cua so splash khong phan hoi tin nhan se tu dong hien "(Not
    # Responding)", khien khach tuong app bi treo dù no van dang chay ngam
    # binh thuong. Gio chay ca 2 buoc nay trong 1 thread nen, main thread
    # tiep tuc goi _splash.update() deu dan de giu cua so "song" + hien thoi
    # gian da cho, khach thay ro app van dang xu ly.
    import threading as _th, time as _time

    _worker_result = {"entry": None, "error": None}

    def _worker():
        try:
            # ── Auto-setup sau khi update ──────────────────────
            # So sanh version.txt vs .deps_installed
            # Neu khac nhau (vua update) → tu dong chay setup_helper.py
            try:
                _ver_file  = _os.path.join(_base, "version.txt")
                _deps_file = _os.path.join(_base, ".deps_installed")
                _cur_ver   = open(_ver_file,  encoding="utf-8").read().strip() if _os.path.exists(_ver_file)  else ""
                _dep_ver   = open(_deps_file, encoding="utf-8").read().strip() if _os.path.exists(_deps_file) else ""
                if _cur_ver and _dep_ver != _cur_ver:
                    _worker_result["status"] = f"Cap nhat v{_cur_ver} — dang cai dat..."
                    _setup = _os.path.join(_base, "setup_helper.py")
                    if _os.path.exists(_setup):
                        _sp.run([_sys.executable, _setup], timeout=3600)
            except Exception:
                pass  # Neu setup that bai, app van khoi dong binh thuong
            # ──────────────────────────────────────────────────

            _worker_result["status"] = "Dang tai module chinh..."
            from magicvoice_core import _main_entry
            _worker_result["entry"] = _main_entry
        except Exception:
            _worker_result["error"] = _tb.format_exc()

    _worker_result["status"] = "Dang khoi dong..."
    _t = _th.Thread(target=_worker, daemon=True)
    _t.start()
    _t0 = _time.time()
    _last_status = None
    while _t.is_alive():
        _cur_status = _worker_result.get("status")
        _elapsed = int(_time.time() - _t0)
        _shown = _cur_status if _elapsed < 20 else f"{_cur_status} ({_elapsed}s)"
        if _shown != _last_status:
            _status_lbl.config(text=_shown)
            _last_status = _shown
        try:
            _splash.update()
        except Exception:
            break
        _time.sleep(0.15)
    _t.join(timeout=1)

    if _worker_result["error"]:
        try: _splash.destroy()
        except Exception: pass
        with open(_log, "w", encoding="utf-8") as _f:
            _f.write(_worker_result["error"])
        import tkinter as _tk2
        _r = _tk2.Tk(); _r.withdraw()
        _tk2.messagebox.showerror(
            "Loi Khoi Dong",
            f"Khong the tai module chinh:\n\nXem: {_log}\n\n"
            "Thu chay lai CaiDat_MagicVoice.bat de sua.")
        _r.destroy()
        _sys.exit(1)

    try:
        _splash.destroy()
    except Exception:
        pass

    _worker_result["entry"]()
