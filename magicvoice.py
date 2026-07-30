# magicvoice.py — Entry point cho MagicVoice TTS Studio
if __name__ == "__main__":
    import os as _os, sys as _sys, traceback as _tb
    _base0 = _os.path.dirname(_os.path.abspath(__file__))
    _log0  = _os.path.join(_base0, "error_log.txt")

    # FIX v3.68 (bug he thong CUNG LOAI voi vu pip/_pth truoc do - phat hien
    # 2026-07-30 tu error_log.txt khach: "ModuleNotFoundError: No module
    # named 'tkinter'"): CaiDat_MagicVoice.bat CO san co che tu bo sung
    # tkinter (xem FIX v3.66 (5) trong file do), NHUNG co che nay CHI chay
    # trong luc CAI DAT. Khi khach mo app qua shortcut (MagicVoice.vbs doc
    # thang python_used.txt roi chay thang "pythonw.exe magicvoice.py"),
    # buoc kiem tra nay HOAN TOAN BI BO QUA. Neu tkinter bi mat SAU KHI cai
    # dat da thanh cong (vd antivirus xoa nham tcl86t.dll/tk86t.dll - rat
    # pho bien voi cac DLL la nay bi heuristic AV nghi ngo), app crash vinh
    # vien khong co cach tu sua, du khach cai lai bao nhieu lan (setup_helper.py
    # khong dong toi tkinter, con .bat thi khong duoc chay lai vi Python "co
    # ve nhu OK"). Sua GOC: tu kiem tra + tu bo sung tkinter O DAY - diem hoi
    # tu THAT SU cua MOI duong mo app (VBS/Chay_MagicVoice.bat/updater.bat
    # deu chay toi day dau tien) - truoc ca khi thu import that o duoi.
    try:
        import tkinter as _tk_probe  # noqa: F401
    except ModuleNotFoundError:
        try:
            import zipfile as _zf0
            _tk_zip = _os.path.join(_base0, "_bundled", "tkinter_bundle.zip")
            if _os.path.isfile(_tk_zip):
                with _zf0.ZipFile(_tk_zip) as _z0:
                    _z0.extractall(_sys.prefix)
        except Exception:
            pass

    # FIX v3.66: TOAN BO khoi tao splash (import tkinter + tao cua so) truoc
    # day KHONG duoc boc chong loi - day la nhung dong dau tien chay khi mo
    # app. Neu "import tkinter" hoac "_tk.Tk()" that bai (vd thieu/hong file
    # tcl86t.dll, tk86t.dll do buoc giai nen tkinter luc cai dat bi loi rieng
    # tren 1 may nao do), TOAN BO tien trinh CHET NGAY LAP TUC trong chua
    # toi 1 giay - nhanh den muc Task Manager cung khong kip thay co tien
    # trinh nao chay (da xac nhan thuc te: khach bao "khong len app", kiem
    # tra Task Manager khong thay python.exe/pythonw.exe nao ca). Khong ghi
    # duoc log, khong hien duoc gi ca vi day la truoc ca khi co the dung
    # chinh tkinter de hien loi. Gio boc lai + dung MessageBoxW cua Windows
    # truc tiep (khong can tkinter) de fallback bao loi trong truong hop toi
    # te nhat nay.
    try:
        # Hien splash TRUOC khi import module nang (torch/torchaudio mat 30-60s)
        import tkinter as _tk
        import tkinter.messagebox  # khong tu co san chi voi "import tkinter"
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
    except Exception:
        try:
            with open(_log0, "w", encoding="utf-8") as _f0:
                _f0.write("LOI NGAY LUC KHOI TAO GIAO DIEN (truoc ca buoc kiem tra thu vien):\n\n")
                _f0.write(_tb.format_exc())
        except Exception:
            pass
        try:
            import ctypes as _ct0
            _ct0.windll.user32.MessageBoxW(
                0,
                f"MagicVoice khong the khoi tao giao dien.\n\nChi tiet loi da luu tai:\n{_log0}\n\n"
                "Vui long lien he ho tro Zalo 0985 483 623 va gui kem file loi tren.",
                "Loi Khoi Dong", 0x10)
        except Exception:
            pass
        _sys.exit(1)

    import subprocess as _sp
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
    # FIX v3.66: ban Python "embeddable" (dung tu khi doi sang giai nen thay
    # vi cai dat qua MSI) KHONG tu dong them thu muc chua script dang chay
    # vao sys.path nhu Python binh thuong - vi python311._pth gioi han path
    # chat che. Thieu dong nay -> "ModuleNotFoundError: No module named
    # magicvoice_core" du file .pyd nam ngay cung thu muc - da xac nhan
    # THUC TE day chinh la nguyen nhan "nhay 1 cai roi mat, khong vao duoc
    # app" tren may khach.
    if _base not in _sys.path:
        _sys.path.insert(0, _base)

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
            try:
                from magicvoice_core import _main_entry
                _worker_result["entry"] = _main_entry
            except Exception:
                _tb_str = _tb.format_exc()
                # FIX v3.66: dau hieu dac trung cua file .pyd/.dll torch bi
                # THIEU luc khoi dong (thuong do AV/Defender cach ly file
                # NGAY SAU khi cai xong, du luc cai da bao OK) - truoc day
                # bat khach tu chay lai CaiDat_MagicVoice.bat (5-20 phut,
                # cai lai TAT CA) hoac tu go lenh pip thu cong. Gio tu dong
                # sua NGAY, chi rieng torch/torchaudio (1-3 phut), khach
                # khong can lam gi ca.
                _sig = _tb_str.lower()
                # FIX v3.66: 2 dang loi khac nhau can 2 cach sua khac nhau:
                # (a) file .pyd/.dll TON TAI nhung khong load duoc (thieu
                #     dependency, bi AV cach ly...) -> sua nhanh RIENG
                #     torch/torchaudio (repair_torch, 1-3 phut) la du.
                # (b) module THIEU HOAN TOAN ("No module named ...") - vd
                #     cai dat bi ngat giua chung, chua kip cai goi nao ca -
                #     repair_torch KHONG du (chi sua torch/torchaudio, cac
                #     goi khac nhu omnivoice van thieu) -> phai chay lai
                #     TOAN BO setup_helper.py (5-20 phut) moi du.
                _is_torch_dll_issue = "torch" in _sig and (
                    "filenotfounderror" in _sig
                    or "could not find module" in _sig
                    or "dll load failed" in _sig
                    or "no such file or directory" in _sig
                )
                _is_missing_module = "no module named" in _sig and (
                    "torch" in _sig or "omnivoice" in _sig
                    or "soundfile" in _sig or "edge_tts" in _sig
                    or "huggingface_hub" in _sig or "firebase_admin" in _sig
                )
                if _is_torch_dll_issue or _is_missing_module:
                    _worker_result["status"] = "Phat hien loi cai dat — dang tu dong sua..."
                    _setup = _os.path.join(_base, "setup_helper.py")
                    _repaired = False
                    if _os.path.exists(_setup):
                        try:
                            _args = [_sys.executable, _setup]
                            if _is_torch_dll_issue and not _is_missing_module:
                                _args.append("--repair-torch")
                            _r = _sp.run(_args, timeout=3600)
                            _repaired = (_r.returncode == 0)
                        except Exception:
                            _repaired = False
                    if _repaired:
                        try:
                            _worker_result["status"] = "Da sua xong — dang tai lai..."
                            from magicvoice_core import _main_entry
                            _worker_result["entry"] = _main_entry
                        except Exception:
                            _worker_result["error"] = _tb.format_exc()
                    else:
                        _worker_result["error"] = _tb_str
                else:
                    _worker_result["error"] = _tb_str
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
        # FIX v3.66: khoi hien MsgBox nay TRUOC DAY khong duoc boc try/except
        # - khac voi 2 khoi con lai trong file (dau va cuoi) da duoc boc san.
        # Neu chinh tkinter.Tk()/messagebox loi ngay o day (vd het tai
        # nguyen he thong sau khi vua load torch/omnivoice - da thay that te
        # tren may yeu RAM), tien trinh CHET AM THAM: file error_log.txt van
        # duoc ghi (dong tren) nhung khach khong thay popup nao ca, tuong
        # app "khong lam gi" ma khong biet da co log de gui ho tro. Gio boc
        # lai + fallback MessageBoxW cua Windows (khong can tkinter), giong
        # cach da lam o khoi splash dau file.
        try:
            import tkinter as _tk2
            _r = _tk2.Tk(); _r.withdraw()
            _tk2.messagebox.showerror(
                "Loi Khoi Dong",
                "MagicVoice da tu dong thu sua loi cai dat nhung khong thanh cong.\n\n"
                f"Chi tiet loi da luu tai:\n{_log}\n\n"
                "Vui long lien he ho tro Zalo 0985 483 623 va gui kem file loi tren.")
            _r.destroy()
        except Exception:
            try:
                import ctypes as _ct1
                _ct1.windll.user32.MessageBoxW(
                    0,
                    "MagicVoice da tu dong thu sua loi cai dat nhung khong thanh cong.\n\n"
                    f"Chi tiet loi da luu tai:\n{_log}\n\n"
                    "Vui long lien he ho tro Zalo 0985 483 623 va gui kem file loi tren.",
                    "Loi Khoi Dong", 0x10)
            except Exception:
                pass
        _sys.exit(1)

    try:
        _splash.destroy()
    except Exception:
        pass

    # FIX v3.66: goi _main_entry() TRUOC DAY khong duoc boc try/except - neu
    # no crash (vd loi runtime khi dung torch/omnivoice lan dau, khong lien
    # quan gi den buoc import ban dau da bat o tren), toan bo tien trinh
    # CHET AM THAM khong ghi log, khong hien gi ca ("nhay 1 cai roi mat" -
    # da xac nhan thuc te tren may khach). Gio boc lai de LUON ghi duoc loi
    # that, du crash o buoc nao.
    try:
        _worker_result["entry"]()
    except Exception:
        with open(_log, "w", encoding="utf-8") as _f:
            _f.write(_tb.format_exc())
        try:
            import tkinter as _tk3
            _r3 = _tk3.Tk(); _r3.withdraw()
            _tk3.messagebox.showerror(
                "Loi Khoi Dong",
                f"MagicVoice gap loi khi mo giao dien chinh.\n\nChi tiet loi da luu tai:\n{_log}\n\n"
                "Vui long lien he ho tro Zalo 0985 483 623 va gui kem file loi tren.")
            _r3.destroy()
        except Exception:
            pass
        _sys.exit(1)
