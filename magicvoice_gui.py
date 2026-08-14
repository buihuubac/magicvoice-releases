#!/usr/bin/env python3
"""
MagicVoice TTS Studio v3
Giao diện hiện đại kiểu ứng dụng TTS chuyên nghiệp
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading, os, sys, re, time, json, subprocess, shutil
from pathlib import Path

# ── FIX (v3.18): Loi 'charmap' codec can't encode character '\u1eaf' (chu "ắ") ──
# Nguyen nhan: tren Windows, pythonw.exe (chay an console qua MagicVoice.vbs)
# co sys.stdout/stderr dung encoding cp1252 (charmap). Khi thu vien ben duoi
# (omnivoice, transformers, torchaudio, ...) print text tieng Viet co dau ->
# crash voi UnicodeEncodeError.
# Fix: ep stdout/stderr ve UTF-8 NGAY khi import, truoc khi bat ky thu vien
# nao co the print. Cung set PYTHONIOENCODING cho subprocess con ke thua.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
for _stream_name in ("stdout", "stderr"):
    _s = getattr(sys, _stream_name, None)
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    elif _s is None:
        # pythonw.exe: stdout/stderr = None -> gan dummy de print() khong crash
        try:
            import io as _io
            setattr(sys, _stream_name, _io.StringIO())
        except Exception:
            pass

# ── FIX v3.68 (theo bao cao khach 2026-07-26): "urlopen error [SSL:
# CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local
# issuer certificate" khi bam "Cap Nhat Ngay" - toan bo app dung urllib.request
# TRUC TIEP (khong qua requests) de tai model/update, dua vao SSL context
# MAC DINH cua Python. Tren mot so may khach (dac biet Python embeddable/
# portable hoac Windows thieu cap nhat goc chung chi), context mac dinh
# KHONG tim thay chuoi chung thuc CA cua GitHub -> tai that bai o MOI lan
# update, khach khong tu go duoc (loi xay ra o chinh buoc tai bo cai moi).
# Fix GOC: cai dat 1 SSL context dung bo chung chi CA cua thu vien `certifi`
# (da co san tren may vi la dependency giao tiep cua `requests`/nhieu thu
# vien khac) lam DEFAULT cho toan bo urllib.request trong app - ap dung 1
# lan duy nhat luc import module nay, KHONG can sua tung noi goi
# urlopen/urlretrieve (check_for_update, _do_update, tai model Google Drive...).
# An toan tuyet doi: neu certifi chua co san (chua tung xay ra tren may da
# test), bo qua lang, giu nguyen hanh vi SSL mac dinh nhu truoc.
def _install_certifi_ssl_context():
    try:
        import ssl, certifi, urllib.request
        _ctx = ssl.create_default_context(cafile=certifi.where())
        _https_handler = urllib.request.HTTPSHandler(context=_ctx)
        urllib.request.install_opener(urllib.request.build_opener(_https_handler))
    except Exception:
        pass
_install_certifi_ssl_context()

# ── Patch torchaudio.load để tránh lỗi TorchCodec trên các máy chưa cài ──
def _patch_torchaudio():
    try:
        import torchaudio as _ta
        if not hasattr(_ta, "load"):
            return
        _original_load = _ta.load

        def _safe_load(uri, *args, **kwargs):
            # Neu da chi dinh backend thi dung luon
            if "backend" in kwargs:
                return _original_load(uri, *args, **kwargs)
            # Thu soundfile truoc (khong can TorchCodec)
            for _bk in ["soundfile", "ffmpeg", "sox", None]:
                try:
                    if _bk is None:
                        return _original_load(uri, *args, **kwargs)
                    return _original_load(uri, *args, backend=_bk, **kwargs)
                except Exception as _e:
                    if "TorchCodec" in str(_e) or "torchcodec" in str(_e).lower():
                        continue
                    if _bk != "sox":
                        raise
            return _original_load(uri, *args, **kwargs)

        _ta.load = _safe_load
    except ImportError:
        pass

# FIX (toi uu toc do 2026-08-14, theo bao cao anh Bac "mo app rat lau"):
# _patch_torchaudio() import torchaudio - thu vien NANG NHAT trong toan bo
# app (co the mat vai giay den vai chuc giay tuy may) - truoc day goi
# THANG o day (module-level, chay dong bo NGAY khi import module nay),
# chan toan bo tien trinh TRUOC CA khi man hinh dang nhap kip hien ra.
# Torchaudio.load() (ham duoc patch) chi thuc su duoc goi luc TAO VOICE
# (sau khi dang nhap + tai model xong, ban than buoc tai model da import
# torch/mat nhieu thoi gian hon nhieu) - nen KHONG can patch xong truoc
# khi hien login. Chuyen sang chay nen (thread rieng) de import nang
# nay chay SONG SONG voi luc hien man dang nhap, khong con chan nua.
import threading as _th_patch_early
_th_patch_early.Thread(target=_patch_torchaudio, daemon=True).start()
try:
    from script_processor import optimize_for_tts, preview_script
    HAS_SCRIPT_PROC = True
except ImportError:
    HAS_SCRIPT_PROC = False

try:
    import ghep_video_core as _ghep
    _ghep.resolve_tools()
    HAS_GHEP = True
except ImportError:
    HAS_GHEP = False
from dataclasses import dataclass, asdict
from typing import Optional

# ── Tự động tìm & thêm ffmpeg vào PATH ──────────────────────────
def _setup_ffmpeg():
    """Tìm ffmpeg theo thứ tự ưu tiên và thêm vào PATH."""
    script_dir = Path(__file__).parent

    # 1. Đọc cache file từ setup_and_run.py
    for cache_name in (".ffmpeg_bin_dir", ".ffmpeg_path"):
        cache = script_dir / cache_name
        if cache.exists():
            bin_dir = cache.read_text(encoding="utf-8").strip()
            if bin_dir and Path(bin_dir).exists():
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return bin_dir

    # 2. Tự scan thư mục ffmpeg_portable/
    portable = script_dir / "ffmpeg_portable"
    if portable.exists():
        for root, dirs, files in os.walk(portable):
            exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
            if exe in files:
                os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                # Lưu cache để lần sau nhanh hơn
                (script_dir / ".ffmpeg_bin_dir").write_text(root, encoding="utf-8")
                return root

    # 3. Kiểm tra PATH hệ thống sẵn có
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5,
                       creationflags=0x08000000 if os.name=="nt" else 0)
        return "system"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None  # Không tìm thấy

_FFMPEG_DIR = _setup_ffmpeg()

WIN  = sys.platform == "win32"
FN   = "Segoe UI"  if WIN else "SF Pro Display"
FN2  = "Segoe UI"  if WIN else "Helvetica Neue"

# ══════════ PALETTE ══════════
P = {
    # backgrounds — nhẹ nhàng, dễ nhìn
    "bg":       "#f0f4fa",   # xanh nhạt nhẹ
    "white":    "#ffffff",
    "sidebar":  "#f8fafc",
    "hover":    "#eef2ff",
    "sel":      "#e0e7ff",   # xanh tím nhạt khi chọn
    # accents — xanh dương chủ đạo
    "purple":   "#4f72f5",   # xanh dương (giống tool mẫu)
    "purple2":  "#6b8bf7",
    "blue":     "#3b82f6",
    "pink":     "#8b5cf6",
    "grad1":    "#4f72f5",
    # text
    "text":     "#1e293b",
    "sub":      "#64748b",
    "dim":      "#94a3b8",
    "label":    "#334155",
    # borders — mỏng nhẹ
    "border":   "#e2e8f0",
    "border2":  "#cbd5e1",
    # status
    "green":    "#10b981",
    "red":      "#ef4444",
    "gold":     "#f59e0b",
    "orange":   "#f97316",
}

# Dùng resolve() để luôn lấy đường dẫn TUYỆT ĐỐI, bất kể chạy từ đâu
_SCRIPT_DIR    = Path(__file__).resolve().parent
VOICES_FILE      = _SCRIPT_DIR / "voices_library.json"
CONFIG_FILE      = _SCRIPT_DIR / "app_config.json"
CLONE_REFS_DIR   = _SCRIPT_DIR / "clone_refs"
PHONETIC_FILE    = _SCRIPT_DIR / "phonetic_dict.json"

def load_config() -> dict:
    """Đọc cấu hình đã lưu."""
    defaults = {"dtype": "float32",
                "out_dir": str(Path.home()/"Downloads"/"MagicVoice"),
                "fmt": ".mp3", "steps": 24, "auto_load": True}
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text("utf-8"))
            defaults.update(saved)
        except: pass
    return defaults

def save_config(cfg: dict):
    """Lưu cấu hình."""
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    except: pass

# ══════════ STYLES ══════════
def style_entry(w, width=None):
    w.configure(relief="flat", bg=P["white"], fg=P["text"],
                insertbackground=P["purple"],
                highlightthickness=1,
                highlightbackground=P["border"],
                highlightcolor=P["purple"],
                font=(FN, 10))
    if width: w.configure(width=width)

def style_btn(w, kind="default"):
    styles = {
        "default": dict(bg=P["white"], fg=P["label"], relief="flat",
                        highlightthickness=1, highlightbackground=P["border2"],
                        activebackground=P["sel"], activeforeground=P["purple"],
                        cursor="hand2", font=(FN, 9), padx=10, pady=4),
        "primary": dict(bg=P["purple"], fg="#fff", relief="flat",
                        highlightthickness=0,
                        activebackground="#3b60e0", activeforeground="#fff",
                        cursor="hand2", font=(FN, 11, "bold"), padx=14, pady=6),
        "ghost":   dict(bg=P["bg"], fg=P["sub"], relief="flat",
                        highlightthickness=0,
                        activebackground=P["sel"], activeforeground=P["purple"],
                        cursor="hand2", font=(FN, 9), padx=10, pady=4),
        "tag":     dict(bg=P["sel"], fg=P["purple"], relief="flat",
                        highlightthickness=0,
                        activebackground=P["purple"], activeforeground="#fff",
                        cursor="hand2", font=(FN, 8), padx=8, pady=3),
        "danger":  dict(bg="#fef2f2", fg=P["red"], relief="flat",
                        highlightthickness=1, highlightbackground="#fca5a5",
                        activebackground="#fee2e2", activeforeground=P["red"],
                        cursor="hand2", font=(FN, 9)),
    }
    w.configure(**styles.get(kind, styles["default"]))

# ══════════ DATA ══════════
@dataclass
class VoiceProfile:
    name:      str
    mode:      str   # clone | design | auto
    ref_audio: str = ""
    ref_text:  str = ""
    instruct:  str = ""
    # FIX v3.65 (9): mac dinh RONG (khong phai "vi") - rong nghia la "chua
    # chon tuong minh, dung heuristic doan cu (ten/instruct)" de tuong thich
    # nguoc voi cac voice da luu truoc khi co tinh nang chon ngon ngu nay.
    # Neu mac dinh la "vi" se gia dinh SAI cho moi voice cu chua tung set
    # field nay (kem ca voice tieng Anh/nuoc khac da luu truoc do).
    lang:      str = ""
    speed:     float = 1.0
    volume:    float = 1.0
    pitch:     float = 1.0
    note:      str = ""
    created:   str = ""

@dataclass
class SRTEntry:
    index: int; start: str; end: str
    text: str; start_ms: int; end_ms: int

def srt_ms(t):
    t = t.strip().replace(",",".")
    h,m,s = t.split(":")
    return int((int(h)*3600+int(m)*60+float(s))*1000)

def _ms_to_srt_ts(ms: int) -> str:
    """Nghich dao cua srt_ms(): so ms -> chuoi 'HH:MM:SS,mmm' chuan SRT."""
    ms = max(0, int(round(ms)))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms  = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _split_text_for_sub(text: str, max_words: int = 8, max_chars: int = 40):
    """FIX v3.67 (2026-07-25, theo yeu cau anh Bac): tach 1 doan text dai
    thanh cac cum NGAN kieu CapCut/YouTube auto-caption, de khong tran man
    hinh. Ap dung 2 chien luoc tuy ngon ngu (tu dong nhan biet, KHONG can
    biet truoc ngon ngu la gi):

    (A) Ngon ngu CO khoang trang giua tu (Anh, Viet, Han Quoc...): tach
        theo TU, gioi han BOI CA HAI - toi da max_words tu VA toi da
        max_chars ky tu (dieu kien nao cham truoc thi cat) - uu tien cat
        sau dau cau (.!?,;:) neu diem do nam gan nguong.

    (B) Ngon ngu KHONG dung khoang trang giua tu (Nhat, Thai, Trung...):
        text.split() se chi ra 1 "tu" duy nhat (ca cau dinh lien khong co
        khoang trang) - phat hien truong hop nay (so tu qua it so voi do
        dai chuoi) va CHUYEN SANG cat truc tiep theo SO KY TU (max_chars),
        uu tien cat sau dau cau ban ngu (.!?,、。！？，) neu gan nguong.

    Ham THUAN, chi xu ly chuoi - khong lien quan am thanh. Tra ve list[str]
    (khong bao gio rong neu text khong rong)."""
    text = text.strip()
    if not text:
        return []

    words = text.split()
    _avg_word_len = len(text) / max(1, len(words))
    _has_real_spacing = len(words) > 1 and _avg_word_len <= (max_chars / 2)

    _PUNCT = ".!?,;:、。！？，．"

    if _has_real_spacing:
        # --- Chien luoc (A): tach theo tu, gioi han ca so tu lan so ky tu ---
        chunks = []
        i = 0
        n = len(words)
        while i < n:
            j = i
            cur_len = 0
            cut = None
            while j < n:
                add_len = len(words[j]) + (1 if j > i else 0)
                if cur_len + add_len > max_chars or (j - i) >= max_words:
                    break
                cur_len += add_len
                if words[j] and words[j][-1] in _PUNCT and (j - i) >= max(1, max_words - 3):
                    cut = j + 1
                j += 1
            end = cut if cut else max(j, i + 1)
            chunks.append(" ".join(words[i:end]))
            i = end
        return chunks
    else:
        # --- Chien luoc (B): ngon ngu khong khoang trang -> cat theo ky tu ---
        chunks = []
        i = 0
        n = len(text)
        while i < n:
            end = min(i + max_chars, n)
            if end < n:
                best_cut = None
                for j in range(end - 1, max(i, end - 8) - 1, -1):
                    if text[j] in _PUNCT:
                        best_cut = j + 1
                        break
                if best_cut:
                    end = best_cut
            chunks.append(text[i:end].strip())
            i = end
        return [c for c in chunks if c]


def _export_srt_timeline(entries_data, gap_ms: float, out_srt_path: str, max_words_per_line: int = 8, max_chars_per_line: int = 40):
    """FIX v3.67 (tinh nang moi 2026-07-25, theo yeu cau anh Bac): xuat file
    .srt co timeline khop CHINH XAC voi audio vua tao (SRT goc bi lech vi
    giong doc tu nhien nhanh/cham khac SRT goc). Text goc cua entry (KHONG
    transcribe/Whisper) - chuan 100%, ap moi ngon ngu - duoc TACH NHO thanh
    nhieu dong sub ngan (~max_words_per_line tu/dong, kieu CapCut) de khong
    tran man hinh, thay vi 1 entry dai = 1 dong sub dai nhu truoc.

    entries_data: list[(text_goc: str, dur_giay: float)] - CHI cac entry
        DA TAO THANH CONG (entry loi/khong co audio da bi loai truoc khi
        truyen vao day, khong lam lech cong don cac entry sau).
    gap_ms: gap dong theo cai dat khach (self.gap_var.get()) tai thoi diem
        chay - doi don vi giay ngay trong ham.
    Cong thuc entry-level (END TIME kieu (1) - chu het dung luc het tieng,
    gap la khoang trong KHONG sub, giua end[i] va start[i+1]):
        start[0] = 0
        end[i]     = start[i] + dur_that[i]
        start[i+1] = end[i] + G   (G = gap_ms/1000, entry cuoi KHONG cong gap sau)
    Trong 1 entry, KHONG co timestamp that cho tung cum nho (khong dung
    Whisper/forced-alignment de giu text goc 100%) - thoi luong entry duoc
    CHIA THEO TY LE SO KY TU cua tung cum (cum dai hon duoc nhieu thoi gian
    hon) - uoc luong hop ly nhat khi khong co timestamp per-tu that, tong
    thoi luong cac cum trong 1 entry LUON = dung dur_that[i] (khong lech).
    Day la ham THUAN (khong doc/ghi self.*, khong dung Backend.gen) - chi
    doc do dai da do san + gap - hoan toan tach biet luong tao voice.
    """
    G = max(0.0, gap_ms) / 1000.0
    lines = []
    t_cur = 0.0
    idx = 0
    for text, dur in entries_data:
        if dur is None or dur <= 0:
            continue
        sub_chunks = _split_text_for_sub(text, max_words_per_line, max_chars_per_line)
        if not sub_chunks:
            continue
        char_counts = [max(1, len(c)) for c in sub_chunks]
        total_chars = sum(char_counts)
        t_local = t_cur
        n_sub = len(sub_chunks)
        for si, (chunk_text, cc) in enumerate(zip(sub_chunks, char_counts)):
            idx += 1
            sub_dur = dur * cc / total_chars
            sub_start = t_local
            # Dong sub CUOI cung cua entry: chot dung end[i] = start[i]+dur_that
            # (tranh sai so cong don lam tren/lam tron qua nhieu dong).
            sub_end = (t_cur + dur) if si == n_sub - 1 else (t_local + sub_dur)
            lines.append(f"{idx}\n{_ms_to_srt_ts(sub_start * 1000)} --> {_ms_to_srt_ts(sub_end * 1000)}\n{chunk_text}\n")
            t_local = sub_end
        t_cur = t_cur + dur + G
    content = "\n".join(lines).strip() + "\n"
    with open(out_srt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return out_srt_path, idx


def parse_srt(txt):
    """Parse SRT - chap nhan ca SRT co va khong co dong trong giua entries."""
    out = []
    # Thu 1: Split theo dong trong (SRT chuan)
    blocks = re.split(r"\n\s*\n", txt.strip())
    if len(blocks) > 1:
        for blk in blocks:
            lines = blk.strip().splitlines()
            if len(lines) < 3: continue
            try:
                idx = int(lines[0].strip())
                m = re.match(r"(\S+)\s*-->\s*(\S+)", lines[1])
                if not m: continue
                text = re.sub(r"<[^>]+>", "", "\n".join(lines[2:])).strip()
                out.append(SRTEntry(idx, m[1], m[2], text, srt_ms(m[1]), srt_ms(m[2])))
            except: pass
        if out: return out

    # Thu 2: Parse theo pattern so + timestamp (SRT khong co dong trong)
    pattern = re.compile(
        r"^(\d+)\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n"
        r"((?:(?!\d+\s*\n\d{2}:\d{2}).)+)",
        re.MULTILINE | re.DOTALL
    )
    for m in pattern.finditer(txt.strip()):
        try:
            idx  = int(m.group(1))
            ts   = m.group(2)
            te   = m.group(3)
            text = re.sub(r"<[^>]+>", "", m.group(4)).strip()
            if text:
                out.append(SRTEntry(idx, ts, te, text, srt_ms(ts), srt_ms(te)))
        except: pass
    return out

# ══════════ VOICE LIBRARY ══════════
class VoiceLib:
    def __init__(self):
        self.profiles: list[VoiceProfile] = []
        self._load()

    def _load(self):
        """Load voice library an toàn - không xóa/đổi tên file khi lỗi."""
        if VOICES_FILE.exists():
            try:
                raw = json.loads(VOICES_FILE.read_text("utf-8"))
                if isinstance(raw, list) and len(raw) > 0:
                    loaded = []
                    for d in raw:
                        if not isinstance(d, dict):
                            continue
                        if not d.get("name") or not d.get("mode"):
                            continue
                        # Dùng .get() với default - không bao giờ lỗi
                        vp = VoiceProfile(
                            name     = str(d.get("name", "")),
                            mode     = str(d.get("mode", "auto")),
                            ref_audio= str(d.get("ref_audio", "")),
                            ref_text = str(d.get("ref_text", "")),
                            instruct = str(d.get("instruct", "")),
                            lang     = str(d.get("lang", "")),
                            speed    = float(d.get("speed", 1.0)),
                            volume   = float(d.get("volume", 1.0)),
                            pitch    = float(d.get("pitch", 1.0)),
                            note     = str(d.get("note", "")),
                            created  = str(d.get("created", "")),
                        )
                        loaded.append(vp)
                    if loaded:
                        # Loc bo Auto voice cu (neu co trong library cu)
                        self.profiles = [vp for vp in loaded if vp.mode != "auto"]
                        self._migrate_voices()
                        return
            except Exception as e:
                # KHÔNG đổi tên/xóa file - giữ nguyên để debug
                print(f"[VoiceLib] Lỗi đọc file: {e}")
                print(f"[VoiceLib] File: {VOICES_FILE}")

        # Tạo mặc định nếu chưa có file (lần đầu dùng)
        self.profiles = []
        self._add_edge_defaults()
        if not VOICES_FILE.exists():
            self.save()

    _EDGE_DEFAULTS = [
        ("Aria - Nu My",  "en-US-AriaNeural",   "Nu My tu nhien, tre trung"),
        ("Andrew - Nam My", "en-US-AndrewNeural", "Nam My am, tu nhien"),
    ]

    def _add_edge_defaults(self):
        for _name, _code, _note in self._EDGE_DEFAULTS:
            self.profiles.append(VoiceProfile(
                name=_name, mode='edge',
                ref_audio=_code, instruct='edge:' + _code, note=_note))

    def _migrate_voices(self):
        _old = {'Nu tre Anh', 'Nam truong thanh', 'Nữ trẻ Anh', 'Nam trưởng thành'}
        changed = False
        new_list = [p for p in self.profiles
                    if not (p.mode == 'design' and p.name in _old)]
        if len(new_list) != len(self.profiles):
            self.profiles = new_list
            changed = True
        if not any(p.mode == 'edge' for p in self.profiles):
            self._add_edge_defaults()
            changed = True
        if changed:
            self.save()

    def _localize_ref_audio(self, vp):
        """Copy file audio clone vào clone_refs/ để tránh mất file khi di chuyển."""
        import dataclasses as _dc
        if vp.mode != "clone" or not vp.ref_audio:
            return vp
        src = Path(vp.ref_audio)
        if not src.exists():
            return vp
        try:
            CLONE_REFS_DIR.mkdir(parents=True, exist_ok=True)
            if src.resolve().parent == CLONE_REFS_DIR.resolve():
                return vp
        except Exception:
            return vp
        dst = CLONE_REFS_DIR / src.name
        counter = 0
        while dst.exists():
            counter += 1
            dst = CLONE_REFS_DIR / f"{src.stem}_{counter}{src.suffix}"
        try:
            shutil.copy2(str(src), str(dst))
            print(f"[VoiceLib] Copy audio clone → clone_refs/{dst.name}")
            return _dc.replace(vp, ref_audio=str(dst))
        except Exception as e:
            print(f"[VoiceLib] Không copy được audio: {e}")
            return vp

    def save(self):
        try:
            VOICES_FILE.write_text(
                json.dumps([asdict(v) for v in self.profiles],
                           ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except PermissionError:
            import tkinter.messagebox as _mb
            _mb.showerror("Lỗi lưu Voice",
                f"Không có quyền ghi file:\n{VOICES_FILE}\n\n"
                "Hãy chuyển thư mục MagicVoice sang ổ D:\\ hoặc chạy lại với quyền Admin.")
        except Exception as e:
            print(f"[VoiceLib] Lỗi lưu: {e}")

    def add(self, vp):
        vp = self._localize_ref_audio(vp)
        self.profiles.append(vp)
        self.save()
        print(f"[VoiceLib] Đã lưu voice: {vp.name} → {VOICES_FILE}")

    def remove(self, i):
        if 0 <= i < len(self.profiles):
            self.profiles.pop(i)
            self.save()

    def update(self, i, vp):
        if 0 <= i < len(self.profiles):
            vp = self._localize_ref_audio(vp)
            self.profiles[i] = vp
            self.save()

# ══════════ PAUSE PROCESSOR ══════════
# Ký hiệu nghỉ → thời gian im lặng (giây)
PAUSE_MARKERS = [
    ("//",   0.8),   # Nghỉ dài
    ("/",    0.4),   # Nghỉ ngắn
    ("…",   0.5),   # Dấu chấm lửng
    ("...", 0.4),   # 3 chấm
]

def split_with_pauses(text: str) -> list:
    """
    Tách văn bản tại các marker nghỉ.
    Trả về list[(segment_text, pause_after_seconds)]
    Ví dụ: "Hello / world // done"
    → [("Hello", 0.4), ("world", 0.8), ("done", 0.0)]
    """
    import re as _re

    # Tạo regex pattern từ markers (dài nhất trước)
    markers_sorted = sorted(PAUSE_MARKERS, key=lambda x: -len(x[0]))
    pattern = "|".join(_re.escape(m) for m, _ in markers_sorted)
    pause_map = {m: d for m, d in markers_sorted}

    pending_pause = 0.0
    current = ""
    # FIX: khởi tạo parts (split giữ lại marker nhờ capturing group) và result
    parts  = _re.split(f"({pattern})", text)
    result = []

    for part in parts:
        if part in pause_map:
            # Gặp marker → lưu đoạn hiện tại + pause
            seg = current.strip()
            if seg:
                result.append((seg, pause_map[part]))
            elif result:
                # Không có text nhưng có pause → cộng vào pause trước
                prev_text, prev_pause = result[-1]
                result[-1] = (prev_text, prev_pause + pause_map[part])
            current = ""
        else:
            current += part

    # Đoạn cuối
    seg = current.strip()
    if seg:
        result.append((seg, 0.0))

    return result if result else [(text.strip(), 0.0)]


# ══════════ NARRATOR PREPROCESSING ══════════
def narrator_preprocess(txt):
    """Tach van ban thanh segments voi pause tu nhien."""
    import re as _re
    result = []
    # Tach theo dau cau, giu dau
    tokens = _re.split(r'([.!?,;:])', txt)
    buf = ""
    pause = 0.0
    for tok in tokens:
        if tok in ('.', '!', '?'):
            buf = (buf + tok).strip()
            if buf:
                result.append((buf, 0.65))
            buf = ""; pause = 0.0
        elif tok == ',':
            buf = (buf + tok).strip()
            if len(buf) > 12:
                result.append((buf, 0.22))
                buf = ""
        elif tok == ';':
            if buf.strip():
                result.append((buf.strip(), 0.45))
            buf = ""
        elif tok == ':':
            if buf.strip():
                result.append((buf.strip() + ":", 0.35))
            buf = ""
        else:
            buf = (buf + " " + tok).strip() if buf else tok.strip()
    if buf.strip():
        result.append((buf.strip(), 0.0))
    # Gop segment qua ngan
    merged = []
    i = 0
    while i < len(result):
        txt_s, p = result[i]
        if len(txt_s) < 12 and i+1 < len(result):
            nxt, np = result[i+1]
            merged.append((txt_s + " " + nxt, np))
            i += 2
        else:
            merged.append((txt_s, p))
            i += 1
    return merged or [(txt.strip(), 0.0)]

# ══════════ BACKEND ══════════
class Backend:
    _model         = None
    _offline       = False   # True = offline mode, set boi App._apply_network_mode()
    _gen_lock      = None
    _loaded_device = None    # Device model da duoc load voi

    @classmethod
    def _get_lock(cls):
        import threading as _th
        if cls._gen_lock is None:
            cls._gen_lock = _th.Lock()
        return cls._gen_lock

    @classmethod
    def load(cls,device,dtype_str,log=None):
        if cls._model: return
        if log: log("正 Đang tải model MagicVoice…","info")
        import torch
        from omnivoice import OmniVoice as MagicVoice
        dt={"float32":torch.float32,"float16":torch.float16,"bfloat16":torch.bfloat16}[dtype_str]
        cls._model=MagicVoice.from_pretrained("k2-fsa/OmniVoice",device_map=device,dtype=dt)
        # torch.compile tăng tốc ~30% sau lần warm-up đầu (PyTorch 2.x+)
        # FIX v3.66 (2026-07-24, theo yeu cau anh Bac - "van cham du giam
        # cau hinh"): torch.compile() can Triton de hoat dong - Triton HO
        # TRO WINDOWS con rat han che/hay loi. Da xac nhan THUC TE tren may
        # dev bang test doc lap (khong dung OmniVoice, chi model gia lap de
        # tranh rui ro): torch.compile() wrap khong loi ngay, nhung LAN GOI
        # FORWARD DAU TIEN moi bao "TritonMissing: Cannot find a working
        # triton installation" - tuc la o dung luc Backend.gen() goi model
        # lan dau, KHONG phai o dong torch.compile() nay (try/except o day
        # KHONG bat duoc loi that). Neu Triton thieu, moi lan load model deu
        # ganh chi phi thu/that bai ma khong bao gio dat duoc toc do nhanh
        # hon nhu quang cao trong log - day rat co the la nguyen nhan chinh
        # gay cham keo dai, khong lien quan gi den dtype/steps khach chinh.
        # Gio KIEM TRA Triton co dung duoc THAT SU truoc (khong chi "co cai
        # dat goi triton" ma phai compile+chay thu 1 ham cuc nho) - CHI goi
        # torch.compile() cho model that neu that su dung duoc, tranh lap
        # lai chi phi thu-roi-that-bai nay tren MOI may khach thieu Triton
        # (rat pho bien tren Windows).
        if "cuda" in device:
            _triton_usable = False
            try:
                import triton  # noqa: F401
                @torch.compile(mode="reduce-overhead")
                def _triton_probe(x):
                    return x + 1
                _triton_probe(torch.zeros(1, device=device))
                _triton_usable = True
            except Exception:
                _triton_usable = False
            if _triton_usable:
                try:
                    if log: log("⚙ Dang bien dich CUDA (torch.compile) — lan dau ~3-5 phut, vui long doi...","warn")
                    cls._model = torch.compile(cls._model, mode="reduce-overhead")
                    if log: log("⚡ torch.compile OK — cac lan tao sau se nhanh hon","ok")
                except Exception:
                    pass
            else:
                if log: log("ℹ torch.compile bo qua (thieu Triton tren may nay) — van chay binh thuong, chi khong co tang toc nay","info")
        if log: log("✓ Model san sang!","ok")

    _seed = 42  # Seed cố định → giọng nhất quán

    @classmethod
    def _whisper_is_cached(cls) -> bool:
        """Kiem tra Whisper da duoc cache local chua."""
        from pathlib import Path as _P
        cache = _P.home() / ".cache" / "huggingface" / "hub"
        for name in ["models--openai--whisper-large-v3-turbo",
                     "models--openai--whisper-large-v3",
                     "models--openai--whisper-base",
                     "models--openai--whisper-small"]:
            if (cache / name).exists():
                return True
        return False

    @classmethod
    def gen(cls,text,ref_audio=None,ref_text=None,instruct=None,num_step=16,speed=1.0):
        """Tao voice - model da load vao RAM/VRAM, khong can internet."""
        if not cls._model: raise RuntimeError('Model chua tai!')
        import torch as _t
        _t.manual_seed(cls._seed)
        if _t.cuda.is_available():
            _t.cuda.manual_seed_all(cls._seed)
            _t.cuda.empty_cache()
        kw = dict(text=text, num_step=num_step, speed=speed)
        if ref_audio: kw['ref_audio'] = ref_audio
        if ref_text:  kw['ref_text']  = ref_text
        if instruct:  kw['instruct']  = _normalize_instruct(instruct)

        # FIX (theo doc OmniVoice chinh thuc github.com/k2-fsa/OmniVoice):
        # OmniVoice nhan param "guidance_scale" (default 2.0), KHONG phai
        # "cfg_strength" hay "sway_sampling_coef" (do la F5-TTS, khong ap dung).
        # guidance_scale cao hon 2.0 -> bam text chat hon, it chen tu lac.
        # Truyen 2.0 (default) de giu giong tu nhien.
        kw["guidance_scale"] = 2.0

        try:
            with _t.inference_mode():
                try:
                    result = cls._model.generate(**kw)
                except TypeError as _te:
                    # Phien ban omnivoice cu khong nhan guidance_scale -> bo va gen lai
                    err_str = str(_te).lower()
                    if "unexpected keyword" in err_str or "got an unexpected" in err_str:
                        kw.pop("guidance_scale", None)
                        result = cls._model.generate(**kw)
                    else:
                        raise
            if _t.cuda.is_available():
                _t.cuda.empty_cache()
            return result
        except RuntimeError as _e:
            if "out of memory" in str(_e).lower():
                if _t.cuda.is_available():
                    _t.cuda.empty_cache()
                raise RuntimeError(
                    "CUDA het bo nho (Out of Memory)!\n\n"
                    "Cach khac phuc:\n"
                    "  - Giam Steps xuong 4-8\n"
                    "  - Doi sang float16\n"
                    "  - Van ban ngan hon (< 200 ky tu)\n"
                    "  - Doi sang CPU trong Header"
                )
            raise

    # FIX v3.66 (hieu nang 2026-07-24, theo yeu cau anh Bac): 2 ham MOI rieng
    # biet - KHONG sua Backend.gen() o tren mot chu nao (dung y "tuyet doi
    # khong dung Backend.gen()"). Van de phat hien: Clone Voice truyen
    # ref_audio (duong dan tho, khong co ref_text) cho MOI CHUNK van ban -
    # ben trong thu vien omnivoice, moi lan nhu vay se TU DONG phien am lai
    # (Whisper) + ma hoa lai audio mau TU DAU (xem
    # omnivoice/models/omnivoice.py, ham create_voice_clone_prompt() goi tu
    # generate() khi thieu voice_clone_prompt) - van ban cang nhieu chunk,
    # audio mau cang bi xu ly lai dư thua cang nhieu lan, rat cham. 2 ham
    # nay cho phep tinh 1 LAN duy nhat (create_voice_clone_prompt) roi tai
    # su dung cho moi chunk trong cung 1 phien, thay vi truyen lai ref_audio
    # tho moi lan.
    _vc_prompt_cache = {}  # {(ref_audio_path, ref_text, mtime): VoiceClonePrompt}

    @classmethod
    def get_voice_clone_prompt(cls, ref_audio, ref_text=None):
        """Tinh (hoac lay tu cache) VoiceClonePrompt cho 1 file ref_audio -
        tranh Whisper transcribe + audio-tokenize lai moi lan goi gen. Cache
        theo (duong dan, ref_text, mtime file) - tu dong tinh lai neu file
        audio mau thay doi."""
        import os as _os_vc
        if not cls._model: raise RuntimeError('Model chua tai!')
        try:
            _mtime = _os_vc.path.getmtime(ref_audio)
        except Exception:
            _mtime = 0
        key = (str(ref_audio), ref_text or "", _mtime)
        cached = cls._vc_prompt_cache.get(key)
        if cached is not None:
            return cached
        vcp = cls._model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text or None)
        cls._vc_prompt_cache[key] = vcp
        return vcp

    @classmethod
    def gen_with_clone_prompt(cls, text, voice_clone_prompt, num_step=16, speed=1.0):
        """Giong het Backend.gen() ve seed/guidance_scale/error-handling,
        NHUNG dung voice_clone_prompt DA TINH SAN thay vi ref_audio tho -
        tranh phien am+ma hoa lai audio mau moi chunk. La ham RIENG, KHONG
        goi/sua Backend.gen()."""
        if not cls._model: raise RuntimeError('Model chua tai!')
        import torch as _t
        _t.manual_seed(cls._seed)
        if _t.cuda.is_available():
            _t.cuda.manual_seed_all(cls._seed)
            _t.cuda.empty_cache()
        kw = dict(text=text, num_step=num_step, speed=speed,
                  voice_clone_prompt=voice_clone_prompt, guidance_scale=2.0)
        try:
            with _t.inference_mode():
                try:
                    result = cls._model.generate(**kw)
                except TypeError as _te:
                    err_str = str(_te).lower()
                    if "unexpected keyword" in err_str or "got an unexpected" in err_str:
                        kw.pop("guidance_scale", None)
                        result = cls._model.generate(**kw)
                    else:
                        raise
            if _t.cuda.is_available():
                _t.cuda.empty_cache()
            return result
        except RuntimeError as _e:
            if "out of memory" in str(_e).lower():
                if _t.cuda.is_available():
                    _t.cuda.empty_cache()
                raise RuntimeError(
                    "CUDA het bo nho (Out of Memory)!\n\n"
                    "Cach khac phuc:\n"
                    "  - Giam Steps xuong 4-8\n"
                    "  - Doi sang float16\n"
                    "  - Van ban ngan hon (< 200 ky tu)\n"
                    "  - Doi sang CPU trong Header"
                )
            raise

    @classmethod
    def set_seed(cls, seed): cls._seed = seed


def _safe_audio_load(path: str):
    """Load audio an toan. Uu tien soundfile (khong subprocess) de tranh flash tren Windows."""
    import torch, numpy as _np
    # 1. soundfile (libsndfile) - pure C, khong spawn subprocess, khong flash
    try:
        import soundfile as _sf
        data, sr = _sf.read(path, dtype='float32', always_2d=True)
        t = torch.from_numpy(data.T.copy())
        return t, sr
    except Exception:
        pass
    # 2. scipy fallback - pure Python, khong subprocess
    try:
        import scipy.io.wavfile as _wav
        sr, data = _wav.read(path)
        if data.dtype == _np.int16:
            data = data.astype(_np.float32) / 32768.0
        t = torch.from_numpy(data).unsqueeze(0) if data.ndim == 1 else torch.from_numpy(data.T.copy())
        return t, sr
    except Exception:
        pass
    # 3. torchaudio - chi dung neu 2 cach tren that bai (ffmpeg backend co the flash)
    import torchaudio
    errors = []
    for backend in ["soundfile", None, "sox"]:
        try:
            if backend is None:
                t, sr = torchaudio.load(path)
            else:
                t, sr = torchaudio.load(path, backend=backend)
            return t, sr
        except Exception as e:
            errors.append(f"{backend}: {e}")
    raise RuntimeError(f"Khong the load audio {path}:\n" + "\n".join(errors))

def _normalize_instruct(text: str) -> str:
    """Chuan hoa instruct text cho omnivoice - thay the pho bien."""
    if not text:
        return text
    # Map cac cum tu hay dung sai → dung
    fixes = {
        "middle aged":      "middle-aged",
        "high pitched":     "high-pitched",
        "low pitched":      "low-pitched",
        "high pitch":       "high pitch",
        "low pitch":        "low pitch",
        "moderate pitched": "moderate pitch",
        "well educated":    "well-educated",
        "deep voiced":      "deep-voiced",
        "soft spoken":      "soft-spoken",
    }
    result = text.lower().strip()
    for wrong, right in fixes.items():
        result = result.replace(wrong, right)
    return result

def _trim_silence(tensor, sr=24000, threshold=0.003, pad_ms=50):
    """Cat bot khoang lang dau/cuoi audio."""
    wav = tensor.squeeze(0)
    # Tim vi tri dau tien co am thanh
    energy = wav.abs()
    pad = int(pad_ms * sr / 1000)
    start = 0
    for i in range(len(energy)):
        if energy[i] > threshold:
            start = max(0, i - pad)
            break
    # Tim vi tri cuoi cung co am thanh
    end = len(energy)
    for i in range(len(energy)-1, -1, -1):
        if energy[i] > threshold:
            end = min(len(energy), i + pad)
            break
    if start >= end:
        return tensor
    return wav[start:end].unsqueeze(0)


def _concat_crossfade(parts, sr=24000, fade_ms=15):
    """Noi audio voi crossfade ngan o diem noi -> het 'cup/vap'."""
    import torch
    if not parts: return None
    if len(parts) == 1: return parts[0]
    fade = int(sr * fade_ms / 1000)
    out = parts[0]
    for nxt in parts[1:]:
        is_silence = bool(nxt.abs().max() < 1e-4) or bool(out.abs().max() < 1e-4)
        n = min(fade, out.shape[-1], nxt.shape[-1])
        if is_silence or n < 8:
            out = torch.cat([out, nxt], dim=-1); continue
        ramp = torch.linspace(0.0, 1.0, n, device=out.device, dtype=out.dtype)
        mixed = out[..., -n:] * (1.0 - ramp) + nxt[..., :n] * ramp
        out = torch.cat([out[..., :-n], mixed, nxt[..., n:]], dim=-1)
    return out


def _post_process(tensor, sr=24000):
    """
    Xử lý hậu kỳ audio để đạt chất lượng tốt nhất:
    - Peak normalize -1dB (tránh clipping)
    - High-pass filter 60Hz (loại tiếng ồn tần số thấp / ồm)
    - Low-pass filter 12kHz (loại nhiễu tần số cao / rè)
    - Soft clip (tránh distortion khi ghép)
    """
    import torch, torchaudio.functional as F

    # 1. Loại DC offset
    tensor = tensor - tensor.mean()

    # 2. High-pass filter 60Hz — loại ồm/rề tần số thấp
    try:
        tensor = F.highpass_biquad(tensor, sr, cutoff_freq=60.0, Q=0.707)
    except Exception:
        pass

    # 3. Low-pass filter 11000Hz — loại rè/nhiễu tần số cao
    try:
        tensor = F.lowpass_biquad(tensor, sr, cutoff_freq=11000.0, Q=0.707)
    except Exception:
        pass

    # 4. Soft clipping (tránh hard clip gây distortion)
    import torch
    tensor = torch.tanh(tensor * 0.95) / 0.95

    # 5. Peak normalize về -1 dBFS
    peak = tensor.abs().max()
    if peak > 0.001:
        target = 0.891  # -1 dBFS
        tensor = tensor * (target / peak)

    return tensor



def _get_ffmpeg():
    """Tim duong dan ffmpeg: portable → imageio_ffmpeg → system PATH."""
    # 1. ffmpeg_portable trong thu muc app
    for _fp in [
        _SCRIPT_DIR / "ffmpeg_portable" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg.exe",
        _SCRIPT_DIR / "ffmpeg_portable" / "bin" / "ffmpeg.exe",
        _SCRIPT_DIR / "ffmpeg.exe",
    ]:
        if _fp.exists():
            return str(_fp)
    # 2. imageio-ffmpeg (pip install imageio-ffmpeg)
    try:
        import imageio_ffmpeg as _iff
        _exe = _iff.get_ffmpeg_exe()
        if _exe and os.path.isfile(_exe):
            return _exe
    except Exception:
        pass
    # 3. system PATH
    return "ffmpeg"

def to_mp3(tensor, path):
    """Luu tensor thanh MP3 320kbps. Raise RuntimeError neu khong luu duoc."""
    import torchaudio
    # Dam bao thu muc ton tai
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp.wav"
    # Luu WAV tam bang soundfile (pure C, khong subprocess, tranh flash Windows)
    wav_ok = False
    try:
        import soundfile as _sf
        _sf.write(tmp, tensor.squeeze().cpu().numpy(), 24000)
        wav_ok = True
    except Exception as _e1:
        try:
            import torchaudio as _ta_mp3
            _ta_mp3.save(tmp, tensor, 24000)
            wav_ok = True
        except Exception as _e2:
            raise RuntimeError(f"Khong luu duoc WAV tam: soundfile={_e1} | torchaudio={_e2}")
    # Convert sang MP3
    _ffmpeg = _get_ffmpeg()
    _flags = 0x08000000 if os.name == "nt" else 0
    try:
        r = subprocess.run([
            _ffmpeg, "-y", "-i", tmp,
            "-codec:a", "libmp3lame",
            "-qscale:a", "0",
            "-b:a", "320k",
            "-ar", "44100",
            path
        ], capture_output=True, creationflags=_flags)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode()[-300:])
        if not os.path.exists(path):
            raise RuntimeError("ffmpeg chay OK nhung file MP3 khong duoc tao")
        try: os.remove(tmp)
        except: pass
    except Exception as _fe:
        # ffmpeg that bai → fallback luu WAV thay the
        wav_path = path.replace(".mp3", ".wav")
        if os.path.exists(tmp):
            try:
                import shutil as _sh
                _sh.move(tmp, wav_path)
                if not os.path.exists(wav_path):
                    raise RuntimeError(f"ffmpeg loi: {_fe} | WAV fallback cung that bai")
                # Thanh cong voi WAV — khong raise, tra ve duong dan WAV
                return wav_path
            except Exception as _we:
                raise RuntimeError(f"ffmpeg loi: {_fe} | WAV fallback loi: {_we}")
        raise RuntimeError(f"ffmpeg loi: {_fe} | Khong co file WAV tam de fallback")


def to_wav(tensor, path):
    """Lưu tensor thành WAV 32-bit — KHÔNG post-process ở đây.
    FIX v3.65 (20): torchaudio.save() truc tiep dispatch sang torchcodec
    backend tren may khong cai torchcodec -> "TorchCodec is required for
    save_with_torchcodec" (cung lop loi da fix o _gen_one truoc day, nhung
    to_wav() chua duoc ap dung). Dung soundfile truoc (khong phu thuoc
    torchcodec), chi fallback torchaudio khi soundfile that bai.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        import soundfile as _sf
        _sf.write(path, tensor.squeeze().cpu().numpy(), 24000, subtype="FLOAT")
    except Exception as _e1:
        try:
            import torchaudio
            torchaudio.save(path, tensor, 24000, encoding="PCM_F", bits_per_sample=32)
        except Exception as _e2:
            raise RuntimeError(f"Khong luu duoc WAV: soundfile={_e1} | torchaudio={_e2}")

def _ensure_deps():
    """
    Kiem tra va cai tu dong cac thu vien con thieu khi khoi dong app.
    Chay trong background thread, khong block UI.
    """
    import sys, subprocess as _sp

    REQUIRED = [
        ("firebase_admin", "firebase-admin"),  # Bat buoc cho dang nhap
        # omnivoice KHONG import o day: no keo theo torch/torchaudio → neu DLL loi se hien dialog 2 lan
        # omnivoice duoc kiem tra / cai lai boi setup_helper.py va _auto_repair_model
        ("edge_tts",       "edge-tts"),
        ("soundfile",      "soundfile"),
        ("sounddevice",    "sounddevice"),
        ("pyaudiowpatch",  "pyaudiowpatch"),
        ("scipy",          "scipy"),
        ("psutil",         "psutil"),
        ("pydub",          "pydub"),
        ("requests",       "requests"),
    ]

    _flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    _python = sys.executable

    for _mod, _pkg in REQUIRED:
        try:
            __import__(_mod)
        except ImportError:
            try:
                _sp.run(
                    [_python, "-m", "pip", "install", _pkg,
                     "--quiet", "--no-cache-dir"],
                    creationflags=_flags,
                    capture_output=True,
                    timeout=120
                )
            except Exception:
                pass

# ══════════ CUSTOM WIDGETS ══════════
class RoundedFrame(tk.Canvas):
    """Canvas with rounded rectangle background"""
    def __init__(self, parent, radius=10, bg=P["white"],
                 border_color=P["border"], **kwargs):
        super().__init__(parent, bg=parent["bg"] if isinstance(parent, tk.Frame) else P["bg"],
                         highlightthickness=0, **kwargs)
        self._radius=radius; self._bg=bg; self._bc=border_color
        self.bind("<Configure>", self._draw)

    def _draw(self, e=None):
        self.delete("all")
        w,h=self.winfo_width(),self.winfo_height()
        r=self._radius
        self.create_polygon(
            r,0, w-r,0, w,r, w,h-r, w-r,h, r,h, 0,h-r, 0,r,
            smooth=True, fill=self._bg, outline=self._bc, width=1)

class _RoundedBtn:
    """Canvas-based rounded button; .config() compatible with tk.Button API.
    Dùng cho nút Tạo để có góc bo tròn thật sự."""
    def __init__(self, parent, text, command, bg="#4f72f5", fg="white",
                 active_bg="#3b60e0", disabled_bg="#94a3b8",
                 font=None, padx=24, pady=10, radius=10):
        self._bg_n  = bg
        self._bg_a  = active_bg
        self._bg_d  = disabled_bg
        self._fg    = fg
        self._text  = text
        self._cmd   = command
        self._font  = font or ("Segoe UI", 12, "bold")
        self._state = "normal"
        self._r     = radius
        import tkinter.font as _tkf
        _fo = _tkf.Font(family=self._font[0], size=abs(self._font[1]),
                        weight=self._font[2] if len(self._font) > 2 else "normal")
        _w  = _fo.measure(text) + padx * 2
        _h  = _fo.metrics("linespace") + pady * 2
        try: _pbg = parent.cget("bg")
        except Exception: _pbg = P["white"]
        self._c = tk.Canvas(parent, width=_w, height=_h,
                            cursor="hand2", highlightthickness=0, bd=0, bg=_pbg)
        self._c.bind("<Configure>",      lambda e: self._draw(self._cur_bg()))
        self._c.bind("<Enter>",          lambda e: self._on_enter())
        self._c.bind("<Leave>",          lambda e: self._draw(self._cur_bg()))
        self._c.bind("<ButtonPress-1>",  lambda e: self._on_press())
        self._c.bind("<ButtonRelease-1>",lambda e: self._on_release())
        self._c.after(30, lambda: self._draw(self._cur_bg()))

    def _cur_bg(self):
        return self._bg_d if self._state == "disabled" else self._bg_n

    def _draw(self, color):
        c = self._c; c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 4 or h < 4: return
        r = min(self._r, w // 2, h // 2)
        for sx, sy in [(0,0),(w-2*r,0),(0,h-2*r),(w-2*r,h-2*r)]:
            ext = [90,0,270,180][[(0,0),(w-2*r,0),(0,h-2*r),(w-2*r,h-2*r)].index((sx,sy))]
            c.create_arc(sx, sy, sx+2*r, sy+2*r, start=ext,
                         extent=90, fill=color, outline=color)
        c.create_rectangle(r, 0,   w-r, h,   fill=color, outline=color)
        c.create_rectangle(0, r,   w,   h-r, fill=color, outline=color)
        _fg = self._fg if self._state != "disabled" else "#e2e8f0"
        c.create_text(w//2, h//2, text=self._text, fill=_fg, font=self._font)

    def _on_enter(self):
        if self._state == "normal": self._draw(self._bg_a)
    def _on_press(self):
        if self._state == "normal": self._draw("#2d4ec0")
    def _on_release(self):
        self._draw(self._cur_bg())
        if self._state == "normal" and self._cmd: self._cmd()

    def config(self, cnf=None, **kw):
        if isinstance(cnf, dict): kw.update(cnf)
        if "state" in kw: self._state = kw["state"]
        if "text"  in kw: self._text  = kw["text"]
        if "bg"    in kw: self._bg_n  = kw["bg"]
        self._draw(self._cur_bg())
    configure = config

    def pack(self, **kw):  self._c.pack(**kw)
    def grid(self, **kw):  self._c.grid(**kw)
    def cget(self, k):
        if k == "state": return self._state
        if k == "text":  return self._text
        return ""

class ModernSlider(tk.Frame):
    """Slider với label value"""
    def __init__(self, parent, label, var, from_, to, resolution=0.05, **kw):
        super().__init__(parent, bg=P["white"])
        tk.Label(self, text=label, font=(FN,9), bg=P["white"],
                 fg=P["sub"]).pack(anchor="w")
        row=tk.Frame(self, bg=P["white"]); row.pack(fill="x")
        self.val_lbl=tk.Label(row, text=f"{var.get():.2f}",
                               font=(FN,9,"bold"), bg=P["white"],
                               fg=P["purple"], width=5, anchor="e")
        self.val_lbl.pack(side="right")
        s=ttk.Scale(row, from_=from_, to=to, variable=var,
                    orient="horizontal",
                    command=lambda v: self.val_lbl.config(text=f"{float(v):.2f}"))
        s.pack(side="left", fill="x", expand=True)

class Chip(tk.Button):
    def __init__(self, parent, text, command, **kw):
        super().__init__(parent, text=text, command=command, **kw)
        style_btn(self, "tag")
        self.configure(padx=8, pady=2)

# ══════════ ADD VOICE DIALOG ══════════
class VoiceDialog(tk.Toplevel):
    def __init__(self, parent, vp=None):
        super().__init__(parent)
        self.result=None
        self.title("Thêm / Chỉnh sửa Voice")
        # FIX v3.65 (10): tang chieu cao 600->660 - sau khi them dong "Ngon
        # ngu giong" (muc 13) ma khong tang height, nut Luu/Huy bi day ra
        # ngoai khung nhin thay (anh Bac bao "khung lưu bị ẩn mất").
        self.geometry("580x660")
        self.configure(bg=P["bg"])
        self.resizable(False,False)
        self.transient(parent)
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build(vp)

    def _build(self, vp):
        # Title
        hdr=tk.Frame(self,bg=P["purple"],pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr,text="🎤  Cấu Hình Voice Clone",font=(FN,13,"bold"),
                 bg=P["purple"],fg="white").pack(padx=20,anchor="w")

        body=tk.Frame(self,bg=P["bg"])
        body.pack(fill="both",expand=True,padx=20,pady=16)

        def row(parent, label, widget_fn):
            f=tk.Frame(parent,bg=P["bg"]); f.pack(fill="x",pady=4)
            tk.Label(f,text=label,font=(FN,9),bg=P["bg"],
                     fg=P["label"],width=14,anchor="w").pack(side="left")
            widget_fn(f)
            return f

        # Name
        self.name_var=tk.StringVar(value=vp.name if vp else "")
        row(body,"Tên voice:", lambda f: tk.Entry(
            f,textvariable=self.name_var,
            font=(FN,10),relief="flat",bg=P["white"],fg=P["text"],
            insertbackground=P["purple"],
            highlightthickness=1,highlightbackground=P["border"],
            highlightcolor=P["purple"],width=30).pack(side="left",ipady=4,padx=(0,4)))

        # Note
        self.note_var=tk.StringVar(value=vp.note if vp else "")
        row(body,"Ghi chú:", lambda f: tk.Entry(
            f,textvariable=self.note_var,
            font=(FN,10),relief="flat",bg=P["white"],fg=P["text"],
            insertbackground=P["purple"],
            highlightthickness=1,highlightbackground=P["border"],
            highlightcolor=P["purple"],width=30).pack(side="left",ipady=4))

        # FIX v3.65 (9): chon TUONG MINH ngon ngu cua giong dang luu - de
        # nghe thu sau nay KHONG con phai doan qua ten/instruct (de sai, vd
        # bug "vietnu" nghe ra tieng Anh do doan nham) - _detect_preview_lang()
        # se uu tien dung gia tri nay neu khac rong. "(Tu dong doan)" = de
        # trong, giu nguyen hanh vi doan cu (tuong thich nguoc voi voice cu).
        self._LANG_OPTIONS = [
            ("(Tự động đoán)", ""),
            ("Tiếng Việt", "vi"), ("English", "en"), ("日本語 (Nhật)", "ja"),
            ("한국어 (Hàn)", "ko"), ("中文 (Trung)", "zh"), ("Français (Pháp)", "fr"),
            ("Deutsch (Đức)", "de"), ("Español (TBN)", "es"), ("ไทย (Thái)", "th"),
            ("Indonesia", "id"), ("Português (BĐN)", "pt"), ("Italiano (Ý)", "it"),
            ("Русский (Nga)", "ru"),
        ]
        self._lang_label_to_code = dict(self._LANG_OPTIONS)
        _lang_code_to_label = {v: k for k, v in self._LANG_OPTIONS}
        self.lang_var = tk.StringVar(
            value=_lang_code_to_label.get(vp.lang if vp else "", "(Tự động đoán)"))
        row(body, "Ngôn ngữ giọng:", lambda f: ttk.Combobox(
            f, textvariable=self.lang_var,
            values=[lbl for lbl, _ in self._LANG_OPTIONS],
            state="readonly", font=(FN,9), width=27).pack(side="left", ipady=2))

        # Mode tabs
        mode_lf=tk.LabelFrame(body,text="  Chế Độ Giọng  ",
                               font=(FN,9),bg=P["bg"],fg=P["purple"],
                               relief="flat",highlightbackground=P["border"],
                               highlightthickness=1,padx=12,pady=8)
        mode_lf.pack(fill="x",pady=(8,4))

        self.mode_var=tk.StringVar(value=vp.mode if vp else "clone")
        mrow=tk.Frame(mode_lf,bg=P["bg"]); mrow.pack(fill="x",pady=(0,8))
        self._mode_btns={}
        for val,lbl,icon in [("clone","Voice Clone","🎯"),
                              ("design","Voice Design","✨")]:
            b=tk.Button(mrow,text=f"{icon} {lbl}",
                        command=lambda v=val:self._set_mode(v),
                        font=(FN,9),relief="flat",cursor="hand2",padx=12,pady=5)
            b.pack(side="left",padx=(0,4))
            self._mode_btns[val]=b

        # Clone section
        self.clone_lf=tk.Frame(mode_lf,bg=P["bg"])
        af=tk.Frame(self.clone_lf,bg=P["bg"]); af.pack(fill="x",pady=2)
        tk.Label(af,text="File audio mẫu:",font=(FN,9),bg=P["bg"],
                 fg=P["label"],width=14,anchor="w").pack(side="left")
        self.ref_audio_var=tk.StringVar(value=vp.ref_audio if vp else "")
        en=tk.Entry(af,textvariable=self.ref_audio_var,font=(FN,9),
                    relief="flat",bg=P["white"],fg=P["text"],
                    insertbackground=P["purple"],
                    highlightthickness=1,highlightbackground=P["border"],
                    width=24); en.pack(side="left",ipady=3,padx=(0,4))
        tk.Button(af,text="📂 Chọn",command=self._pick_audio,
                  font=(FN,9),bg=P["purple"],fg="white",relief="flat",
                  cursor="hand2",padx=8,pady=3).pack(side="left")
        # Nút ghi âm
        self._rec_btn=tk.Button(af,text="🎙 Ghi Âm",command=self._toggle_record,
                  font=(FN,9),bg=P["green"],fg="white",relief="flat",
                  cursor="hand2",padx=8,pady=3)
        self._rec_btn.pack(side="left",padx=(6,0))

        # Chọn nguồn ghi âm
        src_row=tk.Frame(self.clone_lf,bg=P["bg"]); src_row.pack(fill="x",pady=(2,0))
        tk.Label(src_row,text="Nguồn ghi âm:",font=(FN,9),
                 bg=P["bg"],fg=P["label"]).pack(side="left",padx=(14,6))
        self._rec_src=tk.StringVar(value="loopback")
        tk.Radiobutton(src_row,text="🖥 Thu âm đang phát trên máy (web, nhạc...)",
                       variable=self._rec_src,value="loopback",
                       bg=P["bg"],fg=P["label"],font=(FN,8),
                       selectcolor=P["bg"],activebackground=P["bg"]
                       ).pack(side="left")
        tk.Radiobutton(src_row,text="🎤 Thu từ Micro",
                       variable=self._rec_src,value="mic",
                       bg=P["bg"],fg=P["label"],font=(FN,8),
                       selectcolor=P["bg"],activebackground=P["bg"]
                       ).pack(side="left",padx=(8,0))

        # Row chọn thời gian ghi âm
        self._dur_row=tk.Frame(self.clone_lf,bg=P["bg"]); self._dur_row.pack(fill="x",pady=(2,0))
        tk.Label(self._dur_row,text="⏱ Thời gian ghi (giây):",font=(FN,9),
                 bg=P["bg"],fg=P["label"]).pack(side="left",padx=(14,4))
        self._rec_dur_var=tk.IntVar(value=15)
        spb=tk.Spinbox(self._dur_row,from_=3,to=60,increment=1,
                       textvariable=self._rec_dur_var,width=4,
                       font=(FN,10,"bold"),fg=P["purple"],relief="flat",
                       bg=P["white"],justify="center",
                       highlightthickness=1,highlightbackground=P["border"])
        spb.pack(side="left")
        tk.Label(self._dur_row,text="giây  (3–60s)",font=(FN,8),
                 bg=P["bg"],fg=P["dim"]).pack(side="left",padx=4)

        # Row trạng thái ghi âm (ẩn mặc định)
        self._rec_row=tk.Frame(self.clone_lf,bg=P["bg"]); self._rec_row.pack(fill="x",pady=(2,0))
        self._rec_status=tk.Label(self._rec_row,text="",font=(FN,9,"bold"),
                                   bg=P["bg"],fg=P["red"])
        self._rec_status.pack(side="left",padx=14)
        self._rec_row.pack_forget()

        self.audio_info_lbl=tk.Label(self.clone_lf,text="",font=(FN,8),
                                      bg=P["bg"],fg=P["sub"])
        self.audio_info_lbl.pack(anchor="w",padx=14)
        if vp and vp.ref_audio: self._set_audio_info(vp.ref_audio)

        # State ghi âm
        self._recording=False
        self._rec_thread=None
        self._rec_frames=[]
        self._rec_timer=0
        self._rec_after=None

        rtf=tk.Frame(self.clone_lf,bg=P["bg"]); rtf.pack(fill="x",pady=2)
        tk.Label(rtf,text="Transcription:",font=(FN,9),bg=P["bg"],
                 fg=P["label"],width=14,anchor="w").pack(side="left")
        self.ref_text_var=tk.StringVar(value=vp.ref_text if vp else "")
        tk.Entry(rtf,textvariable=self.ref_text_var,font=(FN,9),
                 relief="flat",bg=P["white"],fg=P["text"],
                 insertbackground=P["purple"],
                 highlightthickness=1,highlightbackground=P["border"],
                 width=32).pack(side="left",ipady=3)
        tk.Label(self.clone_lf,
                 text="💡 Để trống → Whisper nhận dạng (cần internet) | Offline: điền thủ công",
                 font=(FN,8),bg=P["bg"],fg=P["dim"]).pack(anchor="w",padx=14)

        # Design section
        self.design_lf=tk.Frame(mode_lf,bg=P["bg"])
        df=tk.Frame(self.design_lf,bg=P["bg"]); df.pack(fill="x",pady=2)
        tk.Label(df,text="Mô tả giọng:",font=(FN,9),bg=P["bg"],
                 fg=P["label"],width=14,anchor="w").pack(side="left")
        self.instruct_var=tk.StringVar(value=vp.instruct if vp else "female, young adult, british accent")
        tk.Entry(df,textvariable=self.instruct_var,font=(FN,10),
                 relief="flat",bg=P["white"],fg=P["text"],
                 insertbackground=P["purple"],
                 highlightthickness=1,highlightbackground=P["border"],
                 width=32).pack(side="left",ipady=4)
        # Preset chips
        pf=tk.Frame(self.design_lf,bg=P["bg"]); pf.pack(fill="x",pady=4,padx=14)
        tk.Label(pf,text="Gợi ý nhanh:",font=(FN,8),bg=P["bg"],fg=P["dim"]).pack(anchor="w")
        chips_row=tk.Frame(pf,bg=P["bg"]); chips_row.pack(fill="x")
        for p2 in ["female, young, vietnamese","male, deep, vietnamese",
                   "female, elderly, british","male, child","female, american accent"]:
            Chip(chips_row,p2,lambda x=p2:self.instruct_var.set(x)).pack(side="left",padx=(0,4),pady=2)

        # Sliders
        sld_frame=tk.LabelFrame(body,text="  Thông Số Giọng  ",
                                  font=(FN,9),bg=P["bg"],fg=P["purple"],
                                  relief="flat",highlightbackground=P["border"],
                                  highlightthickness=1,padx=12,pady=8)
        sld_frame.pack(fill="x",pady=(8,0))
        self.speed_var=tk.DoubleVar(value=vp.speed if vp else 1.0)
        self.vol_var=tk.DoubleVar(value=vp.volume if vp else 1.0)
        self.pitch_var=tk.DoubleVar(value=vp.pitch if vp else 1.0)
        for lbl,var,lo,hi in [("Tốc độ",self.speed_var,0.5,2.0),
                               ("Âm lượng",self.vol_var,0.5,2.0),
                               ("Cao độ",self.pitch_var,0.5,2.0)]:
            row_f=tk.Frame(sld_frame,bg=P["bg"]); row_f.pack(fill="x",pady=2)
            tk.Label(row_f,text=lbl,font=(FN,9),bg=P["bg"],fg=P["label"],
                     width=10,anchor="w").pack(side="left")
            vlbl=tk.Label(row_f,text=f"{var.get():.2f}",font=(FN,9,"bold"),
                           bg=P["bg"],fg=P["purple"],width=5)
            vlbl.pack(side="right")
            ttk.Scale(row_f,from_=lo,to=hi,variable=var,orient="horizontal",
                      command=lambda v,l=vlbl:l.config(text=f"{float(v):.2f}")
                      ).pack(side="left",fill="x",expand=True,padx=(0,4))

        # Save button
        tk.Frame(self,bg=P["border"],height=1).pack(fill="x")
        btn_row=tk.Frame(self,bg=P["bg"]); btn_row.pack(fill="x",padx=20,pady=12)
        tk.Button(btn_row,text="  💾  Lưu Voice  ",command=self._save,
                  font=(FN,11,"bold"),bg=P["purple"],fg="white",
                  relief="flat",cursor="hand2",padx=20,pady=8
                  ).pack(side="left")
        tk.Button(btn_row,text="Hủy",command=self.destroy,
                  font=(FN,10),bg=P["bg"],fg=P["sub"],
                  relief="flat",cursor="hand2",padx=12
                  ).pack(side="left",padx=(8,0))

        self._set_mode(self.mode_var.get())

    def _set_mode(self, mode):
        self.mode_var.set(mode)
        self.clone_lf.pack_forget()
        self.design_lf.pack_forget()
        active=dict(bg=P["purple"],fg="white")
        inactive=dict(bg=P["hover"],fg=P["label"])
        for k,b in self._mode_btns.items():
            b.configure(**(active if k==mode else inactive))
        if mode=="clone": self.clone_lf.pack(fill="x",pady=(4,0))
        elif mode=="design": self.design_lf.pack(fill="x",pady=(4,0))

    def _pick_audio(self):
        p=filedialog.askopenfilename(
            title="Chọn file audio tham chiếu (3-15 giây)",
            filetypes=[("Audio","*.wav *.mp3 *.flac *.ogg *.m4a"),("*","*.*")])
        if p: self.ref_audio_var.set(p); self._set_audio_info(p)

    # ─── GHI ÂM LOOPBACK ──────────────────────────────────────
    def _toggle_record(self):
        if not self._recording:
            self._start_record()
        else:
            self._stop_record()

    def _start_record(self):
        """Ghi âm: loopback (âm đang phát trên máy) hoặc micro."""
        src = self._rec_src.get()
        max_dur = self._rec_dur_var.get()

        if src == "loopback":
            self._start_record_loopback(max_dur)
        else:
            self._start_record_mic(max_dur)

    def _start_record_loopback(self, max_dur):
        """Thu âm đang phát trên máy tính qua WASAPI loopback."""
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            messagebox.showerror(
                "Thiếu thư viện",
                "Cần cài pyaudiowpatch để thu âm máy tính:\n\n"
                "  py -3.11 -m pip install pyaudiowpatch\n\n"
                "Sau khi cài xong hãy khởi động lại app.",
                parent=self)
            return

        try:
            import numpy as np
            pa = pyaudio.PyAudio()
            # Tìm thiết bị WASAPI loopback (âm đang phát)
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            # Tìm loopback counterpart
            loopback_dev = None
            for lb in pa.get_loopback_device_info_generator():
                if speakers["name"] in lb["name"]:
                    loopback_dev = lb
                    break
            if loopback_dev is None:
                loopback_dev = next(pa.get_loopback_device_info_generator(), None)
            if loopback_dev is None:
                messagebox.showerror("Lỗi",
                    "Không tìm thấy thiết bị loopback.\n"
                    "Hãy kiểm tra driver âm thanh.", parent=self)
                pa.terminate(); return
        except Exception as e:
            messagebox.showerror("Lỗi thiết bị",
                f"Không khởi động được WASAPI:\n{e}", parent=self)
            return

        SAMPLERATE = int(loopback_dev["defaultSampleRate"])
        # Loopback device: dùng maxOutputChannels vì nó là output device
        CHANNELS   = int(loopback_dev.get("maxOutputChannels") or
                         loopback_dev.get("maxInputChannels") or 2)
        CHANNELS   = max(1, min(CHANNELS, 2))  # giới hạn 1-2 kênh
        CHUNK      = 1024
        self._rec_samplerate = SAMPLERATE
        self._rec_channels   = CHANNELS

        self._recording = True
        self._rec_frames = []
        self._rec_timer  = 0
        self._rec_btn.config(text="⏹ Dừng Lưu", bg=P["red"])
        self._rec_row.pack(fill="x", pady=(2,0))
        self._rec_status.config(text="⏺ Đang thu âm máy tính... 0s")
        self._update_rec_timer()

        def _loop():
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=SAMPLERATE,
                    frames_per_buffer=CHUNK,
                    input=True,
                    input_device_index=loopback_dev["index"],
                )
                total = int(SAMPLERATE / CHUNK * max_dur)
                for _ in range(total):
                    if not self._recording: break
                    raw = stream.read(CHUNK, exception_on_overflow=False)
                    # QUAN TRỌNG: reshape (-1, CHANNELS) để giữ đúng kênh
                    data = (np.frombuffer(raw, dtype=np.int16)
                              .reshape(-1, CHANNELS)
                              .astype(np.float32) / 32768.0)
                    self._rec_frames.append(data)
                stream.stop_stream(); stream.close()
                pa.terminate()
                if self._recording:
                    self._recording = False
                    self.after(0, self._finish_record)
            except Exception as e:
                self._recording = False
                pa.terminate()
                self.after(0, lambda err=e: messagebox.showerror(
                    "Lỗi ghi âm", f"Lỗi loopback:\n{err}", parent=self))

        self._rec_thread = threading.Thread(target=_loop, daemon=True)
        self._rec_thread.start()

    def _start_record_mic(self, max_dur):
        """Thu từ microphone."""
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            messagebox.showerror(
                "Thiếu thư viện",
                "Cần cài sounddevice:\n\n"
                "  py -3.11 -m pip install sounddevice\n\n"
                "Sau khi cài xong hãy khởi động lại app.",
                parent=self)
            return

        SAMPLERATE = 44100
        CHANNELS   = 1
        CHUNK      = 1024
        self._rec_samplerate = SAMPLERATE
        self._rec_channels   = CHANNELS

        self._recording = True
        self._rec_frames = []
        self._rec_timer  = 0
        self._rec_btn.config(text="⏹ Dừng Lưu", bg=P["red"])
        self._rec_row.pack(fill="x", pady=(2,0))
        self._rec_status.config(text="⏺ Đang thu micro... 0s")
        self._update_rec_timer()

        def _loop():
            try:
                with sd.InputStream(samplerate=SAMPLERATE, channels=CHANNELS,
                                    dtype="float32", blocksize=CHUNK) as stream:
                    total = int(SAMPLERATE / CHUNK * max_dur)
                    for _ in range(total):
                        if not self._recording: break
                        data, _ = stream.read(CHUNK)
                        self._rec_frames.append(data.copy())
                if self._recording:
                    self._recording = False
                    self.after(0, self._finish_record)
            except Exception as e:
                self._recording = False
                self.after(0, lambda err=e: messagebox.showerror(
                    "Lỗi ghi âm", f"Lỗi micro:\n{err}", parent=self))

        self._rec_thread = threading.Thread(target=_loop, daemon=True)
        self._rec_thread.start()

    def _update_rec_timer(self):
        if self._recording:
            self._rec_timer += 1
            max_dur = self._rec_dur_var.get()
            self._rec_status.config(
                text=f"⏺ Đang ghi âm... {self._rec_timer}/{max_dur}s  (nhấn ⏹ để dừng sớm)")
            self._rec_after = self.after(1000, self._update_rec_timer)

    def _finish_record(self):
        """Gọi khi hết thời gian — tự động dừng giống nhấn nút Dừng."""
        if self._rec_after:
            self.after_cancel(self._rec_after)
            self._rec_after = None
        self._rec_btn.config(text="🎙 Ghi Âm", bg=P["green"])
        self._rec_row.pack_forget()
        self._do_save_recording()

    def _stop_record(self):
        """Nhấn nút Dừng — dừng ghi âm và lưu."""
        self._recording = False
        if self._rec_after:
            self.after_cancel(self._rec_after)
            self._rec_after = None
        self._rec_btn.config(text="🎙 Ghi Âm", bg=P["green"])
        self._rec_row.pack_forget()
        self._do_save_recording()

    def _do_save_recording(self):
        """Xử lý audio: stereo→mono, giữ SR gốc, normalize, lưu MP3 chất lượng cao."""
        if not self._rec_frames:
            messagebox.showwarning("Không có dữ liệu", "Chưa ghi được âm thanh nào!", parent=self)
            return

        import numpy as np

        # Hoi nguoi dung co muon loc tap am
        remove_noise = messagebox.askyesno(
            "Loc tap am / nhac nen",
            "Ban co muon tu dong loc tap am va nhac nen khong?\n\n"
            "Co  — Tach giong nguoi khoi am nen (mat ~10-30 giay)\n"
            "Khong — Luu nguyen ban ghi am\n\n"
            "Nen chon Co neu audio co nhac nen hoac tieng on.",
            parent=self)


        # ── 1. Ghép chunks ─────────────────────────────────────
        audio_np = np.concatenate(self._rec_frames, axis=0)

        # ── 2. Chuẩn hoá float32 [-1,1] ───────────────────────
        if audio_np.dtype == np.int16:
            audio_np = audio_np.astype(np.float32) / 32768.0
        else:
            audio_np = audio_np.astype(np.float32)

        # ── 3. Stereo → Mono ───────────────────────────────────
        if audio_np.ndim == 2:
            audio_np = audio_np.mean(axis=1)
        audio_np = audio_np.flatten()

        src_sr  = getattr(self, "_rec_samplerate", 44100)
        dur_raw = len(audio_np) / src_sr

        if dur_raw < 2.0:
            messagebox.showwarning("Quá ngắn",
                f"Đoạn ghi chỉ {dur_raw:.1f}s — cần ít nhất 3 giây.", parent=self)
            return

        # ── 4. Cắt lặng đầu/cuối ──────────────────────────────
        nonsilent = np.where(np.abs(audio_np) > 0.005)[0]
        if len(nonsilent) > 0:
            pad   = src_sr // 5   # 0.2s
            start = max(0, nonsilent[0] - pad)
            end   = min(len(audio_np), nonsilent[-1] + pad)
            audio_np = audio_np[start:end]

        # ── 5. Peak normalize → -1dB ───────────────────────────
        peak = np.max(np.abs(audio_np))
        if peak > 0.001:
            audio_np = audio_np / peak * 0.891

        dur = len(audio_np) / src_sr
        if dur < 2.0:
            messagebox.showwarning("Quá ngắn",
                "Sau khi cắt lặng đoạn ghi quá ngắn.\nThử ghi lâu hơn.", parent=self)
            return

        # ── 6. Tach giong / loc tap am (neu nguoi dung chon) ──
        if remove_noise:
            try:
                # Thu demucs truoc (tot nhat, can cai them)
                from demucs.pretrained import get_model
                from demucs.apply import apply_model
                import torch as _torch
                _model = get_model("htdemucs_ft")
                _model.eval()
                _t = _torch.from_numpy(audio_np).unsqueeze(0).unsqueeze(0)
                with _torch.no_grad():
                    _sources = apply_model(_model, _t, device="cpu")
                # index 3 = vocals track
                audio_np = _sources[0, 3, 0].numpy().astype(np.float32)
                print("[Rec] Demucs vocal separation OK")
            except ImportError:
                # Fallback: chi dung high-pass filter don gian
                try:
                    import scipy.signal as _sig
                    sos = _sig.butter(5, 100.0/(src_sr/2), btype="high", output="sos")
                    audio_np = _sig.sosfilt(sos, audio_np).astype(np.float32)
                    print("[Rec] High-pass filter OK")
                except Exception as _fe:
                    print(f"[Rec] Filter failed: {_fe}")
            except Exception as _e:
                print(f"[Rec] Noise removal error: {_e}")
            # Re-normalize sau loc
            _pk = np.max(np.abs(audio_np))
            if _pk > 0.001:
                audio_np = audio_np / _pk * 0.891

        # ── 7. Lưu MP3 chất lượng cao qua pydub ───────────────
        # Dam bao thu muc clone_refs ton tai
        _clone_dir = Path(_SCRIPT_DIR) / "clone_refs"
        _clone_dir.mkdir(parents=True, exist_ok=True)

        fname    = time.strftime("rec_%Y%m%d_%H%M%S.mp3")
        out_path = _clone_dir / fname

        try:
            import wave, torch as _tc
            # Buoc 1: Luu WAV tam thoi bang wave (khong can ffmpeg/pydub)
            wav_tmp = _clone_dir / fname.replace(".mp3", "_tmp.wav")
            audio_16 = (audio_np * 32767).clip(-32768, 32767).astype(np.int16)
            with wave.open(str(wav_tmp), "w") as wf:
                wf.setnchannels(1); wf.setsampwidth(2)
                wf.setframerate(src_sr)
                wf.writeframes(audio_16.tobytes())

            # Buoc 2: Convert sang MP3 dung to_mp3() cua app
            # (to_mp3 tu tim ffmpeg_portable hoac system ffmpeg)
            try:
                t_wav, sr_wav = _safe_audio_load(str(wav_tmp))
                if sr_wav != 24000:
                    import torchaudio
                    t_wav = torchaudio.functional.resample(t_wav, sr_wav, 24000)
                to_mp3(t_wav, str(out_path))
                try: wav_tmp.unlink()
                except: pass
                out_final = out_path
                fmt_label = "MP3 320kbps"
            except Exception as _mp3_err:
                # Fallback: giu WAV neu MP3 that bai - dung _clone_dir chinh xac
                _wav_out = _clone_dir / fname.replace(".mp3", ".wav")
                try:
                    wav_tmp.rename(_wav_out)
                except Exception:
                    import shutil as _sh
                    _sh.copy2(str(wav_tmp), str(_wav_out))
                out_final = _wav_out
                fmt_label = f"WAV"

            self.ref_audio_var.set(str(out_final))
            self._set_audio_info(str(out_final))
            sz = out_final.stat().st_size / 1024
            messagebox.showinfo(
                "Ghi âm xong!",
                f"Da luu {dur:.1f}s — {fmt_label}\n"
                f"Dung luong: {sz:.0f} KB\n"
                f"→ clone_refs/{out_final.name}\n\n"
                "San sang dung de clone voice!",
                parent=self)
        except Exception as e:
            messagebox.showerror("Loi luu file", f"Khong luu duoc:\n{e}", parent=self)
    # ─── HẾT GHI ÂM ───────────────────────────────────────────

    def _set_audio_info(self,p):
        if os.path.isfile(p):
            sz=os.path.getsize(p)/1_048_576
            self.audio_info_lbl.config(text=f"  📎 {Path(p).name}  ({sz:.1f} MB)")

    def _save(self):
        try:
            name=self.name_var.get().strip()
            if not name:
                messagebox.showwarning("Thiếu tên","Vui lòng nhập tên voice!",parent=self); return
            mode=self.mode_var.get()
            if mode=="clone" and not self.ref_audio_var.get().strip():
                messagebox.showwarning("Thiếu audio","Hãy chọn file audio tham chiếu!",parent=self); return
            # FIX v3.65 (8): CHI luu "instruct" khi mode="design" - day la
            # truong danh rieng cho Voice Design (mo ta AI bang tieng Anh).
            # Truoc day luu instruct du dang o mode nao, neu widget con sot
            # text cu tu luc truoc do dang o tab Design (vd "...british
            # accent") roi doi qua tab Clone luu, du lieu rac nay se bam
            # theo profile Clone -> gay nham lan khi nghe thu (tuong la
            # tieng Anh vi co chu "accent", trong khi Clone thuc te la
            # giong Viet that).
            _instruct_to_save = self.instruct_var.get().strip() if mode == "design" else ""
            # FIX v3.65 (9): luu ngon ngu tuong minh khach da chon (rong neu
            # chon "(Tu dong doan)" - giu nguyen hanh vi doan cu).
            _lang_to_save = self._lang_label_to_code.get(self.lang_var.get(), "")
            self.result=VoiceProfile(
            name=name, mode=mode,
            ref_audio=self.ref_audio_var.get().strip(),
            ref_text=self.ref_text_var.get().strip(),
            instruct=_instruct_to_save,
            lang=_lang_to_save,
            speed=round(float(self.speed_var.get()), 2),
            volume=round(float(self.vol_var.get()), 2),
            pitch=round(float(self.pitch_var.get()), 2),
            note=self.note_var.get().strip(),
            created=time.strftime("%Y-%m-%d %H:%M"),
            )
            self.destroy()
        except Exception as e:
            messagebox.showerror("Lỗi lưu voice", f"Không lưu được:\n{e}", parent=self)


# ══════════ TEXT PREPROCESSOR ══════════════════════════════════

def _to_tensor(a):
    """Convert ket qua Backend.gen() sang torch tensor chuan."""
    import torch as _t, numpy as _np
    item = a[0] if hasattr(a, '__getitem__') else a
    if isinstance(item, _np.ndarray):
        item = _t.from_numpy(item.copy())
    if hasattr(item, 'dim') and item.dim() == 1:
        item = item.unsqueeze(0)
    return item


_fast_pipelines: dict = {}   # cache KPipeline theo lang_code, tranh nap lai model moi lan gen


def _fast_generate(text: str, voice_id: str, speed: float = 1.0):
    """FIX v3.68 (tinh nang moi 2026-07-25, theo yeu cau anh Bac): sinh
    giong cho mode "MG Nhanh" (ten noi bo/ky thuat: dua tren thu
    vien kokoro - KHONG duoc de lo ten nay ra UI/log gui khach, xem
    NOTES_kokoro_feature.md). Day la ham HOAN TOAN RIENG, KHONG dung/sua
    Backend.gen() hay bat ky logic OmniVoice nao - engine khac hoan toan,
    chay CPU/GPU tuy may, khong can ref_audio (khong phai voice clone).
    Tra ve tensor (1, T) @ 24000Hz - dung SR mac dinh cua kokoro, khop
    luon voi SR chuan cua app (24000), KHONG can resample.
    Raise RuntimeError voi thong bao ro rang neu thieu thu vien (khach
    chua cai dat du moi truong)."""
    try:
        from kokoro import KPipeline
    except ImportError as _ie:
        raise RuntimeError(
            "Thieu thanh phan cho 'MG Nhanh'. Vui long vao "
            "'Cai dat lai moi truong (Python/AI)' de cai bo sung."
        ) from _ie
    import numpy as _np, torch as _t

    lang_code = _fast_lang_code(voice_id)
    pipeline = _fast_pipelines.get(lang_code)
    if pipeline is None:
        pipeline = KPipeline(lang_code=lang_code)
        _fast_pipelines[lang_code] = pipeline

    parts = []
    for result in pipeline(text, voice=voice_id, speed=speed):
        parts.append(result.audio.numpy() if hasattr(result.audio, "numpy") else _np.asarray(result.audio))
    if not parts:
        raise RuntimeError("Khong sinh duoc audio (van ban rong hoac loi noi bo).")
    audio = _np.concatenate(parts)
    return _t.from_numpy(audio.copy()).unsqueeze(0).float()


def _check_license_gs(username):
    """Check license — delegate sang license_guard.verify_license().
    FAIL-CLOSED: neu module loi/thieu → TU CHOI (khong con fail-open nhu ban cu).
    """
    try:
        from license_guard import verify_license
        return verify_license(username)
    except ImportError as _ie:
        # Module bi xoa/thieu → tu choi de tranh bypass
        return False, ("Module license_guard bi thieu. "
                       "Vui long cai dat lai app. Chi tiet: " + str(_ie))
    except Exception as _e:
        return False, "Loi kiem tra license: " + str(_e)

_phon_cache: dict = {}

def _load_phonetic_dict() -> dict:
    """Doc phonetic_dict.json, cache theo mtime."""
    if not PHONETIC_FILE.exists():
        return {}
    try:
        mtime = PHONETIC_FILE.stat().st_mtime
        if _phon_cache.get('mtime') == mtime:
            return _phon_cache.get('data', {})
        data = json.loads(PHONETIC_FILE.read_text('utf-8'))
        if isinstance(data, dict):
            _phon_cache['mtime'] = mtime
            _phon_cache['data'] = data
            return data
    except Exception:
        pass
    return {}

def _apply_phonetic(txt: str) -> str:
    """Thay the ten rieng / tu kho doc bang phien am tu phonetic_dict.json.
    Key viet hoa (ten rieng): khop chinh xac case.
    Key viet thuong (tu thuong): khop khong phan biet hoa/thuong.
    Key bat dau bang '_': bo qua (comment/huong dan)."""
    d = _load_phonetic_dict()
    if not d:
        return txt
    import re as _re
    for word, rep in d.items():
        if not word or word.startswith('_'):
            continue
        pat = r'\b' + _re.escape(word) + r'\b'
        if word[0].isupper():
            txt = _re.sub(pat, rep, txt)           # case-sensitive
        else:
            txt = _re.sub(pat, rep, txt, flags=_re.IGNORECASE)  # case-insensitive
    return txt

def _edge_smart_pause(txt: str, max_words: int = 8) -> str:
    """
    Cai thien ngat nghi cho Edge TTS:
    1. Cau dai khong co dau phay -> chen dau phay sau cac tu noi tu nhien
       (that, who, which, when, while, because, but, and, so, or, ...)
       de Edge TTS co ngat nghi.
    2. Tang space sau dau . va , -> Edge TTS ngat lau hon, doc co cam xuc hon.
    """
    import re as _re
    if not txt: return txt

    # Tu noi co the chen dau phay TRUOC chung de tao ngat nghi tu nhien
    BREAK_WORDS = {
        "that","which","who","whom","whose","when","while","where",
        "because","since","although","though","unless","until",
        "but","and","or","so","yet","nor",
        "before","after","if","as","with","over","into","onto","upon",
        "from","through","without","within"
    }
    # Khoang cach toi thieu giua 2 lan chen dau phay (so tu)
    MIN_GAP = 3

    out_lines = []
    for line in txt.split("\n"):
        # Tach theo cau (.!?)
        sentences = _re.split(r"(?<=[.!?])\s+", line)
        new_sentences = []
        for sent in sentences:
            if not sent.strip():
                new_sentences.append(sent); continue

            words = sent.split()
            n_words = len(words)

            # Cau ngan -> bo qua
            if n_words <= max_words:
                new_sentences.append(sent); continue

            # Lap qua tu, chen dau phay TRUOC tu noi neu da qua MIN_GAP tu
            # tu lan ngat truoc
            result_words = []
            words_since_break = 0
            for i, w in enumerate(words):
                clean = _re.sub(r"[^\w]", "", w).lower()
                # Neu tu da co dau cau cuoi -> reset counter, khong them gi
                if w and w[-1] in ",.!?;:":
                    result_words.append(w)
                    words_since_break = 0
                    continue

                # Chen dau phay vao tu truoc neu:
                #  - Tu hien tai la tu noi
                #  - Da qua MIN_GAP tu tu lan ngat truoc
                #  - Khong phai tu dau cau (i>0)
                #  - Con > 2 tu phia sau (tranh ngat sat cuoi cau)
                if (clean in BREAK_WORDS
                    and words_since_break >= MIN_GAP
                    and i > 0
                    and (n_words - i) > 2):
                    # Chen dau phay vao cuoi tu truoc
                    if result_words and not result_words[-1].endswith(","):
                        result_words[-1] = result_words[-1] + ","
                        words_since_break = 0
                    result_words.append(w)
                    words_since_break += 1
                else:
                    result_words.append(w)
                    words_since_break += 1

            new_sent = " ".join(result_words)
            new_sentences.append(new_sent)

        out_lines.append(" ".join(new_sentences))

    result = "\n".join(out_lines)

    # Don dep
    result = _re.sub(r",\s*,", ",", result)
    result = _re.sub(r" {2,}", " ", result)

    return result


def preprocess_text(txt):
    """
    Tien xu ly van ban truoc khi dua vao model TTS:
    - // -> ngat dai (dau cham)
    - /  -> ngat ngan (dau phay)
    - ...  -> dung lai tu nhien
    - "text" -> them dau ngat xung quanh de nhan nha
    - -- -> ngat giua cau
    """
    import re as _re

    # 1. // -> ngat dai
    txt = txt.replace("//", ". ")
    # 2. / -> ngat ngan (bo qua http://, c://)
    txt = _re.sub(r"(?<![a-zA-Z0-9:])\/(?![a-zA-Z0-9:/\\])", ", ", txt)
    # 3. ... hoac ellipsis -> dung
    txt = txt.replace("…", "... ")
    txt = _re.sub(r"\.{3,}", "... ", txt)
    # 4. -- va emdash -> space (Qwen3 BPE khong co token em-dash)
    txt = _re.sub(r'\s*--\s*', ' ', txt)
    txt = _re.sub(u'\s*—\s*', ' ', txt)
    # 5. Van ban trong ngoac kep -> nhan nha
    def _emph(m):
        return ", " + m.group(1).strip() + ","
    txt = _re.sub(r'"([^"]{2,})"', _emph, txt)
    txt = _re.sub(u"[“”]([^“”]{2,})[“”]", _emph, txt)
    # 6. Don dep
    txt = _re.sub(r" {2,}", " ", txt)
    txt = _re.sub(r",\s*,", ",", txt)

    # Fix: ten rieng truoc dau phay bi model bo tu cuoi
    # "Jonathan Roumie, the" → "Jonathan Roumie. The" de model doc du ten
    import re as _re3
    def _fix_name_comma(m):
        name = m.group(1)
        rest = m.group(2)
        # Chuyen phay thanh cham sau ten rieng, viet hoa chu tiep theo
        return f"{name}. {rest[0].upper()}{rest[1:]}"
    txt = _re3.sub(
        r"(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),\s+([a-z])",
        _fix_name_comma, txt)

    return txt.strip()


# ══════════ TTS-FRIENDLY: toi uu van ban cho de doc (khong doi tu) ══════
def _tts_friendly(text: str, split_long_sentences: bool = True) -> str:
    """
    Toi uu van ban cho de doc (TTS-friendly) truoc khi tao voice.
    GIU NGUYEN 100% TU NGU - chi doi dau cau / khoang trang / gach noi /
    hoa-thuong o dau cau moi. Tuyet doi khong them/bot/doi tu nao.

    Ly do can: giong chay seed co dinh (42) -> cung 1 text luon ra cung 1
    audio, nen khi voice "vap" o 1 cho, tao lai bao nhieu lan cung vap
    y cho do - chi sua duoc bang cach doi CAU TRUC VAN BAN, khong sua
    duoc bang model. 2 nguyen nhan vap pho bien:
    - Cau qua dai (~60 tu, nhieu dau phay) -> model "khoi dong lai" nhip
      sau dau phay giua cau, de vap o giua.
    - Gach noi trong tu ghep (vd "well-dressed") + chum phu am day -> model
      hay doc giat o cho co dau gach noi.

    A. Bo gach noi trong tu ghep, doi gach dai (em/en dash) dung ngat y
       thanh dau phay nghi mem.
    B. Tach cau qua dai (>28 tu) CHI tai ranh gioi manh: dau phay + lien tu
       noi menh de doc lap (", and " ", but " ", so " ", yet " ", and the ").
       Toi da 2 lan tach/cau, khong tao manh < 4 tu, uu tien tach gan giua
       cau nhat. Neu khong co ranh gioi an toan -> de nguyen, khong tach bua.
       CHI danh cho MagicVoice (model co van de vap cau dai vi seed co
       dinh) - KHONG danh cho Edge TTS (xem split_long_sentences).
    C. Chuan hoa khoang trang/dau cau: dung 1 khoang trang sau dau cau, gop
       khoang trang thua, dam bao cau ket bang dau ket cau.

    split_long_sentences: FIX v3.66 - Edge TTS (Microsoft) khong bi "vap"
    cau dai nhu MagicVoice (khong dung seed co dinh), nhung lai tu nghi
    lau hon o MOI dau cham theo prosody rieng cua no. Truoc day ham nay
    luon chen them dau cham khi tach cau dai (rule B) bat ke dang dung
    Edge hay MagicVoice - voi Edge, dieu nay CONG DON qua nhieu doan nghi
    dai khong can thiet (van ban von dung dau phay la du, khong vap).
    Goi voi split_long_sentences=False cho Edge TTS de chi ap dung A+C
    (an toan, co loi cho ca 2 chieu), bo qua B.
    """
    import re as _re

    # FIX: giu nguyen ranh gioi DOAN VAN ("\n\n") - tab Van Ban dung dung
    # dau nay de tao khoang nghi 500ms giua doan (_run_text split theo
    # "\n\n"). Ban dau ham nay tach cau qua \s+ (khop ca \n\n) roi noi lai
    # bang ' '.join(...), lam MAT HAN "\n\n" giua cac doan - phat hien qua
    # test truoc khi build, xu ly TUNG DOAN rieng roi ghep lai dung "\n\n".
    _paragraphs = text.split('\n\n')
    _out_paragraphs = []
    for _para in _paragraphs:
        _out_paragraphs.append(_tts_friendly_one_paragraph(_para, split_long_sentences))
    return '\n\n'.join(_out_paragraphs)


def _tts_friendly_one_paragraph(text: str, split_long_sentences: bool = True) -> str:
    """Xu ly TTS-friendly cho 1 doan van don le (khong chua \\n\\n)."""
    import re as _re

    # ── A. Bo gach noi trong tu ghep + gach dai dung ngat y ──────────
    text = _re.sub(r'(?<=[A-Za-zÀ-ỹ])-(?=[A-Za-zÀ-ỹ])', ' ', text)
    text = _re.sub(r'\s*[—–]\s*', ', ', text)

    if not split_long_sentences:
        return _tts_friendly_cleanup_spacing(text)

    # ── B. Tach cau qua dai o ranh gioi lien tu an toan ──────────────
    _CONN_RE = _re.compile(r', (and the|and|but|so|yet) ')

    def _split_one(sent):
        if len(sent.split()) <= 28:
            return None
        matches = list(_CONN_RE.finditer(sent))
        if not matches:
            return None
        mid = len(sent) / 2
        valid = [m for m in matches
                 if len(sent[:m.start()].split()) >= 4
                 and len(sent[m.end():].split()) >= 4]
        if not valid:
            return None
        m = min(valid, key=lambda mm: abs((mm.start() + mm.end()) / 2 - mid))
        left = sent[:m.start()].rstrip()
        if left and left[-1] not in '.!?':
            left += '.'
        conn = m.group(1)
        conn_cap = conn[0].upper() + conn[1:]
        right = conn_cap + ' ' + sent[m.end():].lstrip()
        return left, right

    sentences = _re.split(r'(?<=[.!?])\s+', text)
    out_sentences = []
    for sent in sentences:
        pieces = [sent]
        splits_done = 0
        i = 0
        while i < len(pieces) and splits_done < 2:
            r = _split_one(pieces[i])
            if r:
                pieces[i:i + 1] = [r[0], r[1]]
                splits_done += 1
                i += 2
            else:
                i += 1
        out_sentences.extend(pieces)
    text = ' '.join(out_sentences)

    return _tts_friendly_cleanup_spacing(text)


def _tts_friendly_cleanup_spacing(text: str) -> str:
    """Buoc C: chuan hoa khoang trang / dau cau - dung chung cho ca 2 nhanh
    (co/khong tach cau dai). Chi chen khoang trang khi dau cau theo sau boi
    CHU/SO (khong phai dau cau khac) - tranh pha hong chuoi dau lien tiep
    nhu "..." (ellipsis) thanh ". . ." (FIX: phat hien qua test voi fragment
    co "...")."""
    import re as _re
    text = _re.sub(r'([.,;:!?])(?=[A-Za-zÀ-ỹ0-9])', r'\1 ', text)
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = text.strip()
    if text and text[-1] not in '.!?':
        text += '.'
    return text


# ══════════ TTS QUALITY VERIFICATION (Whisper verify + retry) ════════
_wv_pipe_cache = {}   # {'model': WhisperModel} — load mot lan, dung mai

def _wv_load_pipe():
    """Tra ve faster-whisper WhisperModel (CPU, nho, "small") de verify phat am.
    FIX v3.66 (bat lai Whisper-verify): TRUOC DAY ham nay tim cache theo ten
    "openai/whisper-*" qua transformers.pipeline - nhung tu v3.66,
    setup_helper.py KHONG con tai san Whisper (buoc nay da bi bo so voi
    v3.58), va tinh nang Clone Voice (_auto_transcribe_ref) dung faster-whisper
    (dinh dang cache HOAN TOAN KHAC "openai/whisper-*") - nen truoc day neu bat
    lai verify, ham nay se GAN NHU LUON tra ve None (khong tim thay cache nao
    ca) → verify coi nhu van tat du da go return som. Gio DOI SANG dung CHUNG
    faster-whisper voi Clone Voice: tu cai neu chua co (giong het pattern da
    dung o _auto_transcribe_ref), model "small" (~244MB, tai 1 lan, dung
    chung cho ca Clone Voice lan verify nay neu Clone Voice cung dung "small").
    Tra ve None neu khong cai/tai duoc (vd may khong co mang lan dau)."""
    if 'model' in _wv_pipe_cache:
        return _wv_pipe_cache['model']
    try:
        try:
            from faster_whisper import WhisperModel as _WM_v
        except ImportError:
            import subprocess as _sp_wv, sys as _sys_wv
            _flags_wv = 0x08000000 if os.name == "nt" else 0
            _sp_wv.run([_sys_wv.executable, "-m", "pip", "install",
                       "faster-whisper", "--quiet", "--no-cache-dir"],
                      creationflags=_flags_wv, timeout=180)
            from faster_whisper import WhisperModel as _WM_v
        _m = _WM_v("small", device="cpu", compute_type="int8")
        _wv_pipe_cache['model'] = _m
        return _m
    except Exception:
        pass
    _wv_pipe_cache['model'] = None
    return None


def _wv_score(expected: str, transcribed: str) -> float:
    """Tinh ty le tu noi dung (>= 3 ky tu) trong expected xuat hien trong transcribed."""
    import re as _re
    def _words(t):
        t = t.lower()
        t = _re.sub(r"[^a-z0-9'\s]", " ", t)
        return set(w for w in t.split() if len(w) >= 3)
    exp = _words(expected)
    tra = _words(transcribed)
    if not exp:
        return 1.0
    return len(exp & tra) / len(exp)


def _wv_transcribe(pipe, tensor):
    """Transcribe mot tensor audio (1, T) @ 24kHz bang faster-whisper. Tra ve chuoi.
    Dung numpy array truc tiep (khong ghi file tam) de tranh subprocess flash.
    FIX v3.66: faster-whisper (giong nhu Whisper goc) can audio 16kHz, khac
    24kHz cua OmniVoice - phai resample truoc khi transcribe, neu khong
    ket qua se sai/rong (Whisper doc nham toc do audio)."""
    try:
        import numpy as _np_wv
        import torchaudio as _ta_wv
        t16 = _ta_wv.functional.resample(tensor, 24000, 16000)
        arr = t16.squeeze().cpu().numpy().astype(_np_wv.float32)
        segments, _info_wv = pipe.transcribe(arr, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
    except Exception:
        return ''


def _gen_cached(text: str, steps: int, speed: float, kw: dict):
    """FIX v3.66 (hieu nang 2026-07-24): dispatcher dung chung - neu kw co
    "ref_audio" (Clone Voice), dung voice_clone_prompt DA CACHE (tinh 1 lan
    cho ca phien, khong phien am/ma hoa lai audio mau moi chunk). Neu khong
    phai clone (Design/khong co ref_audio), goi Backend.gen() y nguyen nhu
    truoc - KHONG doi hanh vi Design mode. Day la ham RIENG, KHONG dung
    hay sua Backend.gen()."""
    ref_audio = kw.get("ref_audio")
    if ref_audio:
        vcp = Backend.get_voice_clone_prompt(ref_audio, kw.get("ref_text"))
        return Backend.gen_with_clone_prompt(text, vcp, num_step=steps, speed=speed)
    return Backend.gen(text, num_step=steps, speed=speed, **kw)


def _gen_verified(text: str, steps: int, speed: float, kw: dict,
                  log_fn=None, max_retry: int = 2):
    """
    Goi Backend.gen() va kiem tra phat am bang Whisper.
    - Lan 1 gen voi seed mac dinh (42)
    - Neu score < 78% hoac transcription qua ngan → retry voi seed khac (toi da max_retry lan)
    - Tra ve tensor co score cao nhat
    Returns: (audio_tensor, is_ok: bool, transcribed: str)
    """
    _THRESHOLD = 0.78
    _RETRY_SEEDS = [43, 44, 45]

    def _do_gen(seed_override=None):
        _orig = Backend._seed
        if seed_override is not None:
            Backend._seed = seed_override
        try:
            return _gen_cached(text, steps, speed, kw)
        finally:
            Backend._seed = _orig

    # --- Attempt 0 ---
    a0 = _do_gen()
    t0 = _to_tensor(a0)
    # FIX v3.66 (tat lai 2026-07-24, theo lenh truc tiep anh Bac): sang nay
    # da bat lai co che nay (sua _wv_load_pipe/_wv_transcribe sang faster-
    # whisper de verify hoat dong that su) - nhung ngay sau do anh Bac bao
    # chat luong Clone Voice XAU HAN RO RET (lap tu/meo tieng nhieu hon han)
    # so voi ban truoc khi bat verify. Nghi van chinh: retry-doi-seed (43/
    # 44/45) khi verify (co the SAI, Whisper nghe nham) cham diem duoi 78% -
    # seed=42 la seed rieng da duoc chon on dinh nhat cho Clone Voice, doi
    # seed khac de "qua verify" co the ra giong KEM KHOP voi audio mau hon,
    # du diem Whisper-match cao hon. Theo LENH TRUC TIEP anh Bac (2026-07-24,
    # "Tat han Whisper-verify — ve dung trang thai truoc sang nay"): TAT LAI
    # HOAN TOAN, khong con ban gan-dead-code nhu lan tat truoc (lan do van
    # con nham "khong tim thay pipe" dead code o duoi) - return thang o day,
    # KHONG goi _wv_load_pipe/_wv_transcribe nua, dam bao MOI chunk deu chi
    # dung dung 1 lan seed=42, khong bao gio retry doi seed.
    #
    # FIX v3.66 (dò lặp cụm 2026-07-25): da thu them 1 lop "dò lap n-gram +
    # tao lai giu nguyen seed=42" nhung anh Bac chi ra dung logic sai: seed=42
    # da duoc chung minh TAT DINH (5/5, 8/8 lan giong het nhau tung chu qua
    # nhieu test that) - neu vay tao lai VOI CUNG SEED chi ra lai DUNG BAN
    # LAP HET, khong sua duoc gi (ban chat la Whisper-verify-retry trá hình).
    # DA GO BO co che do. KHONG duoc bat lai kieu "tao lai giu seed" nay tru
    # khi co bang chung ro rang co yeu to thuc su thay doi giua 2 lan tao.
    return t0, True, ''

    tr0 = _wv_transcribe(pipe, t0)
    sc0 = _wv_score(text, tr0)
    # Kiem tra word ratio: neu Whisper nghe duoc < 50% so tu → ep score xuong de force retry
    _w_in  = len(text.split())
    _w_out = len(tr0.split())
    if _w_in >= 5 and _w_out < _w_in * 0.5:
        sc0 = min(sc0, 0.45)

    if sc0 >= _THRESHOLD:
        if log_fn:
            log_fn(f"    🎯 verify {sc0:.0%}: {tr0[:70]}", "info")
        return t0, True, tr0

    if log_fn:
        log_fn(f"    ⚠ phat am {sc0:.0%} < {_THRESHOLD:.0%} → retry\n"
               f"      input : {text[:70]}\n"
               f"      heard : {tr0[:70]}", "warn")

    # --- Retry voi seed khac ---
    best_t, best_sc, best_tr = t0, sc0, tr0
    for ri in range(min(max_retry, len(_RETRY_SEEDS))):
        ar = _do_gen(seed_override=_RETRY_SEEDS[ri])
        tr = _to_tensor(ar)
        trr = _wv_transcribe(pipe, tr)
        scr = _wv_score(text, trr)
        if log_fn:
            log_fn(f"    retry {ri+1}/seed={_RETRY_SEEDS[ri]}: {scr:.0%} | {trr[:60]}", "info")
        if scr > best_sc:
            best_t, best_sc, best_tr = tr, scr, trr
        if best_sc >= _THRESHOLD:
            break

    ok = best_sc >= _THRESHOLD
    if log_fn:
        if ok:
            log_fn(f"    ✅ verify {best_sc:.0%}: {best_tr[:70]}", "info")
        else:
            log_fn(f"    ⚠ chap nhan {best_sc:.0%} (da thu {min(max_retry, len(_RETRY_SEEDS))+1} lan): {best_tr[:70]}", "warn")
    return best_t, ok, best_tr


def _smart_chunks(txt: str, sr: int = 24000, max_ch: int = 350):
    """
    Chia text thanh chunks theo ranh gioi cau (.!?) — chi vay thoi.

    Nguyen tac don gian:
      - Chi split tai .!? (cau hoan chinh) — de OmniVoice tu xu ly nhip nghi ,; noi bo
      - Gom cac cau ngan lai cho den max_ch (duoi nguong 375 noi bo cua OmniVoice)
      - Cau don le > max_ch: giu nguyen 1 chunk, OmniVoice tu xu ly
      - KHONG bao gio split tai phay/cham phay

    Returns: list of (text: str, pause_ms: int)
      pause_ms = 350ms giua cac nhom cau, 0 cho chunk cuoi
    """
    import re as _re
    if not txt or not txt.strip():
        return []
    txt = txt.strip()
    if len(txt) <= max_ch:
        return [(txt, 0)]

    sents = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', txt) if s.strip()]

    result = []
    buf = ''
    for s in sents:
        if not buf:
            buf = s
        elif len(buf) + 1 + len(s) <= max_ch:
            buf += ' ' + s
        else:
            result.append((buf, 350))
            buf = s
    if buf:
        result.append((buf, 0))

    return result if result else [(txt, 0)]


# ══════════════════════════ EDGE TTS VOICES (module-level) ═══════════
# Phai dat o module-level de moi noi (build_left, build_sidebar) deu dung duoc
# FIX v3.68 (tinh nang moi 2026-07-25, theo yeu cau anh Bac): danh sach
# giong "MG Nhanh" - hien thi TEN NOI BO, KHONG duoc de lo ten
# thu vien/model goc o bat ky dau (xem NOTES_kokoro_feature.md). Gom
# tieng Anh (My/Anh) + Tay Ban Nha/Phap/Hindi/Y/Bo Dao Nha - TAT CA da
# test THAT tung giong, chay duoc chi voi "pip install kokoro" (khong
# can thu vien phu). Nhat (pyopenjtalk) va Trung (pypinyin) CHUA them vi
# can cai them thu vien rieng, chua verify on dinh tren may khach.
FAST_VOICES_LIST = [
    # ── 🇺🇸 Nu My ──
    ("af_heart",  "🇺🇸 Heart - Nữ Mỹ (mặc định, tự nhiên)"),
    ("af_bella",  "🇺🇸 Bella - Nữ Mỹ"),
    ("af_nicole", "🇺🇸 Nicole - Nữ Mỹ"),
    ("af_sarah",  "🇺🇸 Sarah - Nữ Mỹ"),
    ("af_sky",    "🇺🇸 Sky - Nữ Mỹ"),
    ("af_nova",   "🇺🇸 Nova - Nữ Mỹ"),
    ("af_river",  "🇺🇸 River - Nữ Mỹ"),
    ("af_jessica","🇺🇸 Jessica - Nữ Mỹ"),
    ("af_kore",   "🇺🇸 Kore - Nữ Mỹ"),
    ("af_alloy",  "🇺🇸 Alloy - Nữ Mỹ"),
    ("af_aoede",  "🇺🇸 Aoede - Nữ Mỹ"),
    # ── 🇺🇸 Nam My ──
    ("am_michael","🇺🇸 Michael - Nam Mỹ"),
    ("am_adam",   "🇺🇸 Adam - Nam Mỹ"),
    ("am_echo",   "🇺🇸 Echo - Nam Mỹ"),
    ("am_eric",   "🇺🇸 Eric - Nam Mỹ"),
    ("am_fenrir", "🇺🇸 Fenrir - Nam Mỹ"),
    ("am_liam",   "🇺🇸 Liam - Nam Mỹ"),
    ("am_onyx",   "🇺🇸 Onyx - Nam Mỹ"),
    ("am_puck",   "🇺🇸 Puck - Nam Mỹ"),
    ("am_santa",  "🇺🇸 Santa - Nam Mỹ"),
    # ── 🇬🇧 Nu Anh ──
    ("bf_emma",     "🇬🇧 Emma - Nữ Anh"),
    ("bf_isabella", "🇬🇧 Isabella - Nữ Anh"),
    ("bf_alice",    "🇬🇧 Alice - Nữ Anh"),
    ("bf_lily",     "🇬🇧 Lily - Nữ Anh"),
    # ── 🇬🇧 Nam Anh ──
    ("bm_george", "🇬🇧 George - Nam Anh"),
    ("bm_daniel", "🇬🇧 Daniel - Nam Anh"),
    ("bm_lewis",  "🇬🇧 Lewis - Nam Anh"),
    ("bm_fable",  "🇬🇧 Fable - Nam Anh"),
    # FIX v3.68 (bo sung 2026-07-25, da test THAT tung giong - chi them
    # ngon ngu KHONG can thu vien phu, tranh loi cai dat cho khach). Nhat
    # (pyopenjtalk) va Trung (pypinyin) CHUA them vi can cai them thu vien
    # rieng, chua verify on dinh tren may khach.
    # ── 🇪🇸 Tay Ban Nha ──
    ("ef_dora",  "🇪🇸 Dora - Nữ Tây Ban Nha"),
    ("em_alex",  "🇪🇸 Alex - Nam Tây Ban Nha"),
    ("em_santa", "🇪🇸 Santa - Nam Tây Ban Nha"),
    # ── 🇫🇷 Phap ──
    ("ff_siwis", "🇫🇷 Siwis - Nữ Pháp"),
    # ── 🇮🇳 Hindi (An Do) ──
    ("hf_alpha", "🇮🇳 Alpha - Nữ Hindi"),
    ("hf_beta",  "🇮🇳 Beta - Nữ Hindi"),
    ("hm_omega", "🇮🇳 Omega - Nam Hindi"),
    ("hm_psi",   "🇮🇳 Psi - Nam Hindi"),
    # ── 🇮🇹 Y ──
    ("if_sara",   "🇮🇹 Sara - Nữ Ý"),
    ("im_nicola", "🇮🇹 Nicola - Nam Ý"),
    # ── 🇵🇹 Bo Dao Nha (Brazil) ──
    ("pf_dora",  "🇵🇹 Dora - Nữ Bồ Đào Nha"),
    ("pm_alex",  "🇵🇹 Alex - Nam Bồ Đào Nha"),
    ("pm_santa", "🇵🇹 Santa - Nam Bồ Đào Nha"),
]

def _fast_lang_code(voice_id: str) -> str:
    """FIX v3.68: lay lang_code cho KPipeline tu ky tu dau tien cua voice_id
    (dung quy uoc chinh thuc cua thu vien: a=My, b=Anh, e=TBN, f=Phap,
    h=Hindi, i=Y, p=BDN - chi gom cac ngon ngu da verify khong can thu
    vien phu, xem FAST_VOICES_LIST)."""
    return voice_id[0] if voice_id and voice_id[0] in "abefhip" else "a"


EDGE_VOICES_LIST = [
    # ── 🇺🇸 Tieng Anh My ──
    ("en-US-AriaNeural",        "🇺🇸 Aria - Nữ Mỹ (tự nhiên, trẻ trung)"),
    ("en-US-JennyNeural",       "🇺🇸 Jenny - Nữ Mỹ (rõ ràng, chuyên nghiệp)"),
    ("en-US-EmmaNeural",        "🇺🇸 Emma - Nữ Mỹ (trẻ, năng động)"),
    ("en-US-MichelleNeural",    "🇺🇸 Michelle - Nữ Mỹ (ấm áp, thân thiện)"),
    ("en-US-AnaNeural",         "🇺🇸 Ana - Nữ Mỹ (trẻ em)"),
    ("en-US-AndrewNeural",      "🇺🇸 Andrew - Nam Mỹ (ấm, tự nhiên)"),
    ("en-US-GuyNeural",         "🇺🇸 Guy - Nam Mỹ (trầm, mạnh mẽ)"),
    ("en-US-ChristopherNeural", "🇺🇸 Christopher - Nam Mỹ (chắc chắn)"),
    ("en-US-EricNeural",        "🇺🇸 Eric - Nam Mỹ (trung tính, rõ)"),
    ("en-US-RogerNeural",       "🇺🇸 Roger - Nam Mỹ (lớn tuổi)"),
    ("en-US-SteffanNeural",     "🇺🇸 Steffan - Nam Mỹ (kể chuyện)"),
    ("en-US-BrianNeural",       "🇺🇸 Brian - Nam Mỹ (gần gũi, chân thành)"),
    # FIX v3.65: xoa Davis/Jason/Tony - Microsoft da khai tu, chon vao se loi
    # khong tao duoc audio (doi chieu voi `edge-tts --list-voices` that su).
    # ── 🇬🇧 Tieng Anh Anh ──
    ("en-GB-SoniaNeural",       "🇬🇧 Sonia - Nữ Anh (chuẩn, thanh lịch)"),
    ("en-GB-LibbyNeural",       "🇬🇧 Libby - Nữ Anh (trẻ, hiện đại)"),
    ("en-GB-MaisieNeural",      "🇬🇧 Maisie - Nữ Anh (nhẹ nhàng)"),
    ("en-GB-RyanNeural",        "🇬🇧 Ryan - Nam Anh (chuẩn, trầm)"),
    ("en-GB-ThomasNeural",      "🇬🇧 Thomas - Nam Anh (trang trọng)"),
    # ── 🇦🇺 Tieng Anh Uc ──
    ("en-AU-NatashaNeural",     "🇦🇺 Natasha - Nữ Úc (tự nhiên)"),
    # FIX v3.65: en-AU-WilliamNeural (ban thuong) da bi Microsoft khai tu,
    # thay bang ban Multilingual con ton tai that.
    ("en-AU-WilliamMultilingualNeural", "🇦🇺 William - Nam Úc (trầm ấm, đa ngôn ngữ)"),
    # ── 🇨🇦 Tieng Anh Canada ──
    ("en-CA-ClaraNeural",       "🇨🇦 Clara - Nữ Canada"),
    ("en-CA-LiamNeural",        "🇨🇦 Liam - Nam Canada"),
    # ── 🇮🇪 Tieng Anh Ireland ──
    ("en-IE-EmilyNeural",       "🇮🇪 Emily - Nữ Ireland"),
    ("en-IE-ConnorNeural",      "🇮🇪 Connor - Nam Ireland"),
    # ── 🇮🇳 Tieng Anh An Do ──
    ("en-IN-NeerjaNeural",      "🇮🇳 Neerja - Nữ Ấn Độ"),
    ("en-IN-PrabhatNeural",     "🇮🇳 Prabhat - Nam Ấn Độ"),
    # ── 🇻🇳 Tieng Viet ──
    ("vi-VN-HoaiMyNeural",      "🇻🇳 Hoài My - Nữ Việt (Miền Bắc, chuẩn)"),
    ("vi-VN-NamMinhNeural",     "🇻🇳 Nam Minh - Nam Việt (Miền Bắc, rõ)"),
    # ── 🇨🇳 Tieng Trung ──
    ("zh-CN-XiaoxiaoNeural",    "🇨🇳 Xiaoxiao - Nữ Trung (phổ thông, ấm)"),
    ("zh-CN-XiaoyiNeural",      "🇨🇳 Xiaoyi - Nữ Trung (trẻ)"),
    ("zh-CN-YunjianNeural",     "🇨🇳 Yunjian - Nam Trung (kể chuyện)"),
    ("zh-CN-YunxiNeural",       "🇨🇳 Yunxi - Nam Trung (trẻ)"),
    ("zh-CN-YunyangNeural",     "🇨🇳 Yunyang - Nam Trung (phổ thông, rõ)"),
    # FIX v3.65: zh-CN-XiaochenNeural da bi Microsoft khai tu, xoa.
    ("zh-HK-HiuMaanNeural",     "🇭🇰 HiuMaan - Nữ Hong Kong"),
    ("zh-TW-HsiaoChenNeural",   "🇹🇼 HsiaoChen - Nữ Đài Loan"),
    # ── 🇯🇵 Tieng Nhat ──
    ("ja-JP-NanamiNeural",      "🇯🇵 Nanami - Nữ Nhật (tự nhiên)"),
    ("ja-JP-KeitaNeural",       "🇯🇵 Keita - Nam Nhật (trầm)"),
    # ── 🇰🇷 Tieng Han ──
    ("ko-KR-SunHiNeural",       "🇰🇷 SunHi - Nữ Hàn (tự nhiên)"),
    ("ko-KR-InJoonNeural",      "🇰🇷 InJoon - Nam Hàn (trầm)"),
    # ── 🇫🇷 Tieng Phap ──
    ("fr-FR-DeniseNeural",      "🇫🇷 Denise - Nữ Pháp"),
    ("fr-FR-HenriNeural",       "🇫🇷 Henri - Nam Pháp"),
    # ── 🇩🇪 Tieng Duc ──
    ("de-DE-KatjaNeural",       "🇩🇪 Katja - Nữ Đức"),
    ("de-DE-ConradNeural",      "🇩🇪 Conrad - Nam Đức"),
    # ── 🇪🇸 Tieng Tay Ban Nha ──
    ("es-ES-ElviraNeural",      "🇪🇸 Elvira - Nữ TBN"),
    ("es-ES-AlvaroNeural",      "🇪🇸 Alvaro - Nam TBN"),
    ("es-MX-DaliaNeural",       "🇲🇽 Dalia - Nữ Mexico"),
    ("es-MX-JorgeNeural",       "🇲🇽 Jorge - Nam Mexico"),
    # ── 🇮🇹 Tieng Y ──
    ("it-IT-ElsaNeural",        "🇮🇹 Elsa - Nữ Ý"),
    ("it-IT-DiegoNeural",       "🇮🇹 Diego - Nam Ý"),
    # ── 🇵🇹 Tieng Bo Dao Nha ──
    ("pt-BR-FranciscaNeural",   "🇧🇷 Francisca - Nữ Brazil"),
    ("pt-BR-AntonioNeural",     "🇧🇷 Antonio - Nam Brazil"),
    # ── 🇷🇺 Tieng Nga ──
    ("ru-RU-SvetlanaNeural",    "🇷🇺 Svetlana - Nữ Nga"),
    ("ru-RU-DmitryNeural",      "🇷🇺 Dmitry - Nam Nga"),
    # ── 🇹🇭 Tieng Thai ──
    ("th-TH-PremwadeeNeural",   "🇹🇭 Premwadee - Nữ Thái"),
    ("th-TH-NiwatNeural",       "🇹🇭 Niwat - Nam Thái"),
    # ── 🇮🇩 Tieng Indo ──
    ("id-ID-GadisNeural",       "🇮🇩 Gadis - Nữ Indo"),
    ("id-ID-ArdiNeural",        "🇮🇩 Ardi - Nam Indo"),
]


# ══════════════════════════ VOICE PRESETS ════════════════════════
VOICE_PRESETS = {
    "🇻🇳 Tiếng Việt": [
        ("Nữ trẻ tự nhiên",        "female, young adult"),
        ("Nam trẻ tự nhiên",       "male, young adult"),
        ("Nữ trung niên",          "female, middle-aged"),
        ("Nam trung niên",         "male, middle-aged"),
        ("Nữ cao tuổi",            "female, elderly"),
        ("Nam cao tuổi",           "male, elderly"),
        ("Nữ giọng cao",           "female, high pitch"),
        ("Nam giọng trầm",         "male, low pitch"),
        ("Trẻ em gái",             "female, child"),
        ("Trẻ em trai",            "male, child"),
        ("Thì thầm nữ",            "female, whisper"),
        ("Thì thầm nam",           "male, whisper"),
    ],
    "🇬🇧 English — British": [
        ("Female Young British",   "female, young adult, british accent"),
        ("Male Young British",     "male, young adult, british accent"),
        ("Female Elderly British", "female, elderly, british accent"),
        ("Male Deep British",      "male, middle-aged, low pitch, british accent"),
        ("Child British",          "female, child, british accent"),
    ],
    "🇺🇸 English — American": [
        ("Female American",        "female, young adult, american accent"),
        ("Male American",          "male, young adult, american accent"),
        ("Female Mature American", "female, middle-aged, american accent"),
        ("Male Deep American",     "male, middle-aged, low pitch, american accent"),
        ("Male Elderly American",  "male, elderly, american accent"),
        ("High Pitch Female",      "female, young adult, high pitch, american accent"),
    ],
    "🌏 English — Other Accents": [
        ("Female Australian",      "female, young adult, australian accent"),
        ("Male Australian",        "male, young adult, australian accent"),
        ("Female Canadian",        "female, young adult, canadian accent"),
        ("Male Canadian",          "male, young adult, canadian accent"),
        ("Female Indian",          "female, young adult, indian accent"),
        ("Male Indian",            "male, young adult, indian accent"),
    ],
    # FIX v3.65 (2): RUT GON lai chi con dung 10 accent model THAT SU ho tro -
    # xac nhan qua thong bao loi that khi anh Bac bam Nghe Thu:
    #   "Valid English items: american accent, australian accent,
    #    british accent, canadian accent, chinese accent, indian accent,
    #    japanese accent, korean accent, portuguese accent, russian accent"
    # Truoc do em da THEM NHAM 13 accent khong ton tai trong model (thai,
    # filipino, indonesian, malaysian, french, german, italian, spanish,
    # mexican, brazilian, dutch, turkish, arabic, irish, south african) ->
    # chon vao se bi loi "Unsupported instruct items". Day la bai hoc: Voice
    # Design KHONG phai instruct tu do hoan toan, ma la 1 tap gia tri CO DINH
    # (closed vocabulary) model da duoc huan luyen - khac voi Edge TTS (that
    # su la danh sach giong theo tung quoc gia/ngon ngu that).
    # => Neu anh can giong THAT SU noi ngon ngu cua nuoc do (Phap, Duc, Y,
    # TBN, Thai, Indo...) thi dung Edge TTS (da co du ~80 giong that/20 nuoc,
    # xac thuc qua API that) - Voice Design chi la giong TIENG ANH voi 10 sac
    # thai accent nghe-nhu-nguoi-nuoc-ngoai noi tieng Anh, khong sinh duoc
    # tieng noi that cua ngon ngu do.
    "🇨🇳 English — Chinese Accent": [
        ("Female Chinese", "female, young adult, chinese accent"),
        ("Male Chinese",   "male, young adult, chinese accent"),
    ],
    "🇰🇷 English — Korean Accent": [
        ("Female Korean", "female, young adult, korean accent"),
        ("Male Korean",   "male, young adult, korean accent"),
    ],
    "🇯🇵 English — Japanese Accent": [
        ("Female Japanese", "female, young adult, japanese accent"),
        ("Male Japanese",   "male, young adult, japanese accent"),
    ],
    "🇵🇹 English — Portuguese Accent": [
        ("Female Portuguese", "female, young adult, portuguese accent"),
        ("Male Portuguese",   "male, young adult, portuguese accent"),
    ],
    "🇷🇺 English — Russian Accent": [
        ("Female Russian", "female, young adult, russian accent"),
        ("Male Russian",   "male, middle-aged, russian accent"),
    ],

    "🎭 Đặc Biệt": [
        ("Thì thầm bí ẩn",         "female, young adult, whisper"),
        ("Kể chuyện trầm ấm",      "male, middle-aged, low pitch"),
        ("Giọng trẻ em vui",       "female, child, high pitch"),
        ("Narrator uy quyền",      "male, elderly, low pitch, american accent"),
        ("Podcast nữ",             "female, young adult, moderate pitch, american accent"),
        ("Tin tức nam",            "male, middle-aged, moderate pitch, british accent"),
        ("Thuyết minh phim",       "male, young adult, low pitch"),
        ("Hướng dẫn nhẹ nhàng",   "female, middle-aged, moderate pitch"),
    ],
}

class VoiceBrowserDialog(tk.Toplevel):
    """Dialog duyệt & chọn giọng từ 600+ kết hợp Voice Design"""
    def __init__(self, parent, on_select=None):
        super().__init__(parent)
        self.on_select = on_select
        self.result_instruct = None
        self.title("🎙 Chọn Giọng — Voice Browser")
        self.geometry("780x580")
        self.configure(bg=P["bg"])
        self.resizable(True, True)
        self.grab_set()
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=P["purple"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎙  Voice Browser — Thư Viện Giọng MagicVoice",
                 font=(FN, 13, "bold"), bg=P["purple"], fg="white").pack(side="left", padx=20)
        # FIX v3.65 (7): bo hoan toan danh muc Voice Design theo yeu cau -
        # dialog nay gio chi con "Giong That" (Edge TTS, du quoc gia that).
        tk.Label(hdr, text="Giọng thật — chọn đúng quốc gia, nghe đúng ngôn ngữ",
                 font=(FN, 9), bg=P["purple"], fg="#ddd").pack(side="right", padx=20)

        # Body: left categories + right presets
        body = tk.Frame(self, bg=P["bg"])
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # LEFT: category list
        cat_frame = tk.Frame(body, bg=P["white"], width=180)
        cat_frame.pack(side="left", fill="y")
        cat_frame.pack_propagate(False)
        tk.Label(cat_frame, text="Danh mục", font=(FN, 9, "bold"),
                 bg=P["sidebar"], fg=P["label"], pady=8).pack(fill="x", padx=8)

        # FIX v3.65: them Canvas + Scrollbar cho danh sach danh muc - truoc day
        # cac nut duoc pack() THANG vao cat_frame (chieu cao co dinh cua dialog),
        # nen khi tang len 23 danh muc (sau khi tach rieng tung nuoc o fix truoc)
        # bi tran ra ngoai, khong co con lan de xem cac danh muc phia duoi
        # (Turkish, Arabic, Dac Biet...). Dung lai dung pattern Canvas+Scrollbar
        # da co san o middle preset_lb (vsb) cho dong bo.
        cat_canvas = tk.Canvas(cat_frame, bg=P["white"], highlightthickness=0)
        cat_vsb = tk.Scrollbar(cat_frame, orient="vertical", command=cat_canvas.yview)
        cat_canvas.configure(yscrollcommand=cat_vsb.set)
        cat_vsb.pack(side="right", fill="y")
        cat_canvas.pack(side="left", fill="both", expand=True)

        cat_inner = tk.Frame(cat_canvas, bg=P["white"])
        cat_win = cat_canvas.create_window((0, 0), window=cat_inner, anchor="nw")

        def _cat_inner_configure(event):
            cat_canvas.configure(scrollregion=cat_canvas.bbox("all"))
        cat_inner.bind("<Configure>", _cat_inner_configure)

        def _cat_canvas_configure(event):
            cat_canvas.itemconfig(cat_win, width=event.width)
        cat_canvas.bind("<Configure>", _cat_canvas_configure)

        # Cuon bang chuot khi tro dang o vung danh muc (khong anh huong vung khac)
        def _cat_mousewheel(event):
            cat_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        cat_canvas.bind("<Enter>", lambda e: cat_canvas.bind_all("<MouseWheel>", _cat_mousewheel))
        cat_canvas.bind("<Leave>", lambda e: cat_canvas.unbind_all("<MouseWheel>"))

        # FIX v3.65 (7): BO HAN danh muc Voice Design theo yeu cau anh Bac
        # (gay hieu nham lien tuc vi khong tao duoc tieng noi that) - dialog
        # nay gio CHI con danh muc Giong That (Edge TTS, tu self.master._edge_full
        # - da co san ~80 giong/20 nuoc, xac thuc that qua API). Van giu lai
        # VOICE_PRESETS + _design_frame trong code (khong xoa) phong khi can
        # dung lai sau nay, nhung KHONG con hien nut danh muc nao cho no nua.
        self.cat_btns = {}
        self.current_cat = tk.StringVar()
        self._edge_cats = set()
        if hasattr(self.master, "_edge_full") and self.master._edge_full:
            tk.Label(cat_inner, text="🌐 Giọng Thật (Đầy Đủ Quốc Gia)",
                     font=(FN, 8, "bold"), bg=P["sidebar"], fg=P["label"],
                     pady=4).pack(fill="x")
            for cat in self.master._edge_full:
                self._edge_cats.add(cat)
                b = tk.Button(cat_inner, text=cat, font=(FN, 9),
                              bg=P["white"], fg=P["label"], relief="flat",
                              cursor="hand2", anchor="w", padx=12, pady=6,
                              command=lambda c=cat: self._show_cat(c))
                b.pack(fill="x")
                self.cat_btns[cat] = b
        self._is_edge_cat = False

        # MIDDLE: preset list
        mid = tk.Frame(body, bg=P["bg"])
        mid.pack(side="left", fill="both", expand=True)

        tk.Label(mid, text="Giọng có sẵn — click để chọn:",
                 font=(FN, 9, "bold"), bg=P["bg"], fg=P["label"],
                 pady=6).pack(anchor="w", padx=12)

        lf = tk.Frame(mid, bg=P["bg"])
        lf.pack(fill="both", expand=True, padx=8)
        vsb = tk.Scrollbar(lf); vsb.pack(side="right", fill="y")
        self.preset_lb = tk.Listbox(lf, font=(FN, 10), bg=P["white"],
                                     fg=P["text"], selectbackground=P["sel"],
                                     selectforeground=P["purple"],
                                     relief="flat", highlightthickness=1,
                                     highlightbackground=P["border"],
                                     activestyle="none",
                                     yscrollcommand=vsb.set)
        self.preset_lb.pack(fill="both", expand=True)
        vsb.config(command=self.preset_lb.yview)
        self.preset_lb.bind("<<ListboxSelect>>", self._on_select)
        self.preset_lb.bind("<Double-Button-1>", lambda e: self._use())
        self._preset_data = []

        # RIGHT: builder + preview
        right = tk.Frame(body, bg=P["white"], width=240)
        right.pack(side="right", fill="y", padx=0)
        right.pack_propagate(False)

        # FIX v3.65 (5): tach thanh 2 khung rieng - _design_frame (Voice
        # Design, giu nguyen nhu cu) va _edge_ctrl_frame (Edge TTS, MOI) -
        # _show_cat() se dong/mo dung 1 trong 2 tuy theo danh muc dang chon.
        self._design_frame = tk.Frame(right, bg=P["white"])

        tk.Label(self._design_frame, text="🔧 Tự Tùy Chỉnh",
                 font=(FN, 10, "bold"), bg=P["sidebar"],
                 fg=P["purple"], pady=8).pack(fill="x", padx=8)

        self._attr_vars = {}
        attrs = [
            ("Giới tính", "gender", ["(auto)", "female", "male"]),
            ("Tuổi",       "age",    ["(auto)", "child", "teenager", "young adult",
                                       "middle-aged", "elderly"]),
            ("Cao độ",     "pitch",  ["(auto)", "very low pitch", "low pitch",
                                       "moderate pitch", "high pitch", "very high pitch"]),
            ("Phong cách", "style",  ["(auto)", "whisper"]),
            # FIX v3.65 (2): CHI giu dung 10 accent model THAT SU ho tro - xac
            # nhan qua thong bao loi that ("Valid English items: ..."). Da bo
            # het cac accent bia/khong ton tai (irish, south african, thai,
            # filipino, indonesian, malaysian, french, german, italian,
            # spanish, mexican, brazilian, dutch, turkish, arabic) - chon vao
            # se bi loi "Unsupported instruct items".
            ("Accent EN",  "accent", ["(auto)", "american accent", "british accent",
                                       "australian accent", "canadian accent",
                                       "indian accent", "chinese accent",
                                       "korean accent", "japanese accent",
                                       "portuguese accent", "russian accent"]),

        ]
        for label, key, options in attrs:
            tk.Label(self._design_frame, text=label+":", font=(FN, 8),
                     bg=P["white"], fg=P["label"]).pack(anchor="w", padx=12, pady=(4,0))
            var = tk.StringVar(value=options[0])
            self._attr_vars[key] = var
            cb = ttk.Combobox(self._design_frame, textvariable=var, values=options,
                              state="readonly", width=22, font=(FN, 8))
            cb.pack(padx=12, pady=(0,2), fill="x")
            cb.bind("<<ComboboxSelected>>", self._update_preview)

        tk.Frame(self._design_frame, bg=P["border"], height=1).pack(fill="x", padx=8, pady=6)
        tk.Label(self._design_frame, text="Instruct string:", font=(FN, 8, "bold"),
                 bg=P["white"], fg=P["label"]).pack(anchor="w", padx=12)
        self.preview_var = tk.StringVar(value="")
        preview_en = tk.Entry(self._design_frame, textvariable=self.preview_var,
                              font=(FN, 9), bg=P["sidebar"], fg=P["purple"],
                              relief="flat", highlightthickness=1,
                              highlightbackground=P["border"])
        preview_en.pack(padx=12, fill="x", ipady=4, pady=(2,6))

        # FIX v3.65 (5): khung dieu khien Edge TTS - Toc do/Am luong/Cao do,
        # dung dung pattern (slider 0.5-2.0) nhu panel "Thiet Ke Giong Edge
        # TTS" o sidebar chinh (_edge_speed_var/_edge_vol_var/_edge_pitch_var)
        # de dong bo trai nghiem - dat ten bien khac (_eb_...) de khong dung
        # cham voi bien cung ten cua App chinh.
        self._edge_ctrl_frame = tk.Frame(right, bg=P["white"])
        tk.Label(self._edge_ctrl_frame, text="🌐 Tùy Chỉnh Giọng Edge",
                 font=(FN, 10, "bold"), bg=P["sidebar"],
                 fg=P["purple"], pady=8).pack(fill="x", padx=8)

        # FIX v3.65 (7): loc Gioi tinh cho danh sach - day la thu DUY NHAT
        # trong 5 thuoc tinh Voice Design (Gioi tinh/Tuoi/Cao do/Phong cach/
        # Accent) THAT SU ap dung duoc cho Edge TTS, vi moi giong Edge co san
        # da co gioi tinh co dinh -> loc list theo gioi tinh la hop ly (giong
        # dung bo loc "Tat ca/Nu/Nam" da co san o panel sidebar chinh). Cac
        # thuoc tinh con lai (Tuoi/Accent) KHONG ap dung duoc vi Edge khong
        # nhan instruct nhu Voice Design - da giai thich va anh Bac xac nhan
        # chi lam bo loc Gioi tinh nay thoi.
        gender_row = tk.Frame(self._edge_ctrl_frame, bg=P["white"])
        gender_row.pack(fill="x", padx=12, pady=(4,2))
        tk.Label(gender_row, text="Giới tính:", font=(FN,8),
                 bg=P["white"], fg=P["dim"]).pack(side="left")
        self._eb_gender_var = tk.StringVar(value="Tất cả")
        for g in ["Tất cả", "Nữ", "Nam"]:
            tk.Radiobutton(gender_row, text=g, variable=self._eb_gender_var,
                           value=g, font=(FN,8), bg=P["white"],
                           activebackground=P["white"], cursor="hand2",
                           command=self._refresh_edge_list).pack(side="left", padx=4)
        tk.Frame(self._edge_ctrl_frame, bg=P["border"], height=1).pack(fill="x", padx=8, pady=(4,2))

        self._eb_speed_var = tk.DoubleVar(value=1.0)
        self._eb_vol_var   = tk.DoubleVar(value=1.0)
        self._eb_pitch_var = tk.DoubleVar(value=1.0)
        for lbl, var in [("🚀 Tốc độ", self._eb_speed_var),
                          ("🔊 Âm lượng", self._eb_vol_var),
                          ("🎵 Cao độ", self._eb_pitch_var)]:
            row = tk.Frame(self._edge_ctrl_frame, bg=P["white"])
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=lbl, font=(FN,8),
                     bg=P["white"], fg=P["dim"], width=10,
                     anchor="w").pack(side="left")
            vlbl = tk.Label(row, text="1.00", font=(FN,8,"bold"),
                             bg=P["white"], fg=P["purple"], width=4)
            vlbl.pack(side="right")
            ttk.Scale(row, from_=0.5, to=2.0, variable=var,
                      orient="horizontal",
                      command=lambda v, l=vlbl: l.config(text=f"{float(v):.2f}")
                      ).pack(side="left", fill="x", expand=True, padx=4)
        tk.Label(self._edge_ctrl_frame,
                 text="Đây là giọng THẬT (Edge TTS)\nnói đúng ngôn ngữ đã chọn.",
                 font=(FN, 8), bg=P["white"], fg=P["dim"], justify="left",
                 wraplength=200).pack(anchor="w", padx=12, pady=(8,0))

        # FIX v3.65 (7): Voice Design khong con danh muc nao de chon nua,
        # nen mac dinh hien khung Edge TTS luon (thay vi _design_frame nhu truoc).
        self._edge_ctrl_frame.pack(fill="both", expand=True)

        # Bottom buttons
        tk.Frame(self, bg=P["border"], height=1).pack(fill="x")
        btn_row = tk.Frame(self, bg=P["bg"])
        btn_row.pack(fill="x", padx=16, pady=10)

        # FIX v3.65: nut Nghe Thu - de khach nghe truoc khi bam Dung Giong Nay,
        # dung chung engine voi nut "Thu Giong" o sidebar chinh (qua
        # self.master._preview_instruct) nhung khong can luu voice truoc.
        self.preview_btn = tk.Button(btn_row, text="🔊  Nghe Thử",
                                      command=self._preview,
                                      font=(FN, 11, "bold"), bg="#f0fdf4", fg="#16a34a",
                                      relief="flat", cursor="hand2", padx=20, pady=8,
                                      highlightthickness=1, highlightbackground="#86efac")
        self.preview_btn.pack(side="left")
        self.use_btn = tk.Button(btn_row, text="✅  Dùng Giọng Này",
                                  command=self._use,
                                  font=(FN, 11, "bold"), bg=P["purple"], fg="white",
                                  relief="flat", cursor="hand2", padx=20, pady=8,
                                  state="disabled")
        self.use_btn.pack(side="left", padx=(8, 0))
        # FIX v3.65 (5): luu reference de an di khi dang o danh muc Edge TTS -
        # "Dung Custom" chi co y nghia voi Voice Design (tuy chinh instruct
        # tu do), khong ap dung cho giong Edge that (khong co khai niem instruct).
        self.use_custom_btn = tk.Button(btn_row, text="🔧 Dùng Custom",
                  command=self._use_custom,
                  font=(FN, 9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=12, pady=6)
        self.use_custom_btn.pack(side="left", padx=(8, 0))
        tk.Button(btn_row, text="Đóng", command=self.destroy,
                  font=(FN, 9), bg=P["bg"], fg=P["sub"],
                  relief="flat", cursor="hand2", padx=12
                  ).pack(side="right")

        # FIX v3.65 (7): mac dinh mo danh muc Edge TTS dau tien (Voice Design
        # khong con nut danh muc nao de mo nua).
        if self._edge_cats:
            first_cat = list(self.master._edge_full.keys())[0]
            self._show_cat(first_cat)

    def _show_cat(self, cat):
        for k, b in self.cat_btns.items():
            b.configure(bg=P["sel"] if k == cat else P["white"],
                        fg=P["purple"] if k == cat else P["label"],
                        font=(FN, 9, "bold") if k == cat else (FN, 9))
        self.current_cat.set(cat)
        self._edge_sel_code = None

        # FIX v3.65 (5)(7): phan biet danh muc Voice Design (instruct AI,
        # tieng Anh - hien khong con nut nao de mo) voi danh muc Edge TTS
        # (giong THAT, dung self.master._edge_full) - moi loai co cau truc
        # du lieu va khung dieu khien rieng ben phai.
        if cat in self._edge_cats:
            self._is_edge_cat = True
            self._edge_full_list = self.master._edge_full.get(cat, [])
            self._design_frame.pack_forget()
            self._edge_ctrl_frame.pack(fill="both", expand=True)
            self.use_custom_btn.pack_forget()
            self._refresh_edge_list()
        else:
            self._is_edge_cat = False
            self.preset_lb.delete(0, "end")
            self._preset_data = VOICE_PRESETS.get(cat, [])
            for name, instruct in self._preset_data:
                self.preset_lb.insert("end", f"  {name}")
            self._edge_ctrl_frame.pack_forget()
            self._design_frame.pack(fill="both", expand=True)
            self.use_custom_btn.pack(side="left", padx=(8, 0))
        self.use_btn.config(state="disabled")

    def _refresh_edge_list(self):
        """FIX v3.65 (7): loc self._edge_full_list theo Gioi tinh dang chon
        (Tat ca/Nu/Nam) va ve lai preset_lb. self._preset_data luon la danh
        sach DA LOC dang hien thi (index khop voi preset_lb) de _on_select
        tra cuu dung."""
        if not self._is_edge_cat:
            return
        self.preset_lb.delete(0, "end")
        self._edge_sel_code = None
        self.use_btn.config(state="disabled")
        gfilter = self._eb_gender_var.get()
        filtered = self._edge_full_list
        if gfilter != "Tất cả":
            filtered = [v for v in filtered if v[2] == gfilter]
        self._preset_data = filtered
        for code, name, gender, desc in filtered:
            icon = "👩" if gender == "Nữ" else "👨"
            self.preset_lb.insert("end", f"  {icon} {name} — {desc}")

    def _on_select(self, event=None):
        sel = self.preset_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        if self._is_edge_cat:
            code, name, gender, desc = self._preset_data[idx]
            self._edge_sel_code = code
            self._edge_sel_name = name
            self._edge_sel_gender = gender
            self._edge_sel_desc = desc
            self.use_btn.config(state="normal")
        else:
            _, instruct = self._preset_data[idx]
            self.result_instruct = instruct
            self.preview_var.set(instruct)
            self.use_btn.config(state="normal")

    def _update_preview(self, event=None):
        parts = []
        for key in ["gender", "age", "pitch", "style", "accent", "dialect"]:
            v = self._attr_vars[key].get()
            if v and v != "(auto)":
                parts.append(v)
        self.preview_var.set(", ".join(parts) if parts else "")

    def _preview(self):
        """FIX v3.65: nghe thu giong dang chon/tuy chinh TRUOC khi luu.
        FIX v3.65 (5): them nhanh Edge TTS - nghe DUNG ngon ngu that cua
        giong dang chon (khong phai mau tieng Anh nhu Voice Design)."""
        if self._is_edge_cat:
            if not self._edge_sel_code:
                messagebox.showwarning("Chưa chọn",
                    "Hãy chọn giọng từ danh sách trước!", parent=self)
                return
            code = self._edge_sel_code
            lang = self.master._detect_preview_lang(code)
            sample = self.master._PREVIEW_SAMPLES.get(lang, self.master._PREVIEW_SAMPLES["en"])
            self.master._run_voice_preview(sample, f"Edge: {code}",
                                            btn_ref=self.preview_btn,
                                            override_edge_code=code)
            return

        # Dung self.preview_var - da duoc dong bo boi ca _on_select (chon
        # preset co san) lan _update_preview (tuy chinh thuoc tinh), nen luon
        # phan anh dung instruct hien tai dang duoc xem.
        instruct = self.preview_var.get().strip()
        if not instruct:
            messagebox.showwarning("Chưa chọn",
                "Hãy chọn giọng có sẵn hoặc tùy chỉnh thuộc tính trước!", parent=self)
            return
        self.master._preview_instruct(instruct, f"Preview: {instruct[:50]}",
                                       btn_ref=self.preview_btn)

    def _use(self):
        # FIX v3.65 (5): danh muc Edge TTS - tra ve dict (khac voi string
        # instruct cua Voice Design) de _browse_voices() ben App phan biet
        # duoc va luu VoiceProfile mode="edge" thay vi mode="design".
        if self._is_edge_cat:
            if not self._edge_sel_code:
                messagebox.showwarning("Chưa chọn", "Hãy chọn giọng trước!", parent=self)
                return
            if self.on_select:
                self.on_select({
                    "mode": "edge",
                    "code": self._edge_sel_code,
                    "name": self._edge_sel_name,
                    "gender": self._edge_sel_gender,
                    "desc": self._edge_sel_desc,
                    "lang": self.current_cat.get(),
                    "speed": self._eb_speed_var.get(),
                    "volume": self._eb_vol_var.get(),
                    "pitch": self._eb_pitch_var.get(),
                })
            self.destroy()
            return
        if self.result_instruct:
            if self.on_select:
                self.on_select(self.result_instruct)
            self.destroy()

    def _use_custom(self):
        instruct = self.preview_var.get().strip()
        if not instruct:
            messagebox.showwarning("Trống", "Hãy chọn ít nhất 1 thuộc tính!", parent=self)
            return
        self.result_instruct = instruct
        if self.on_select:
            self.on_select(instruct)
        self.destroy()


# ══════════════════════════ MAIN APP ══════════════════════════════
# ══════════ AUTO UPDATE ══════════
# URL mac dinh (Render server cu). Co the override qua update_config.json
# Vi du update_config.json (de canh magicvoice_gui.py):
#   {
#     "version_url":  "https://raw.githubusercontent.com/USER/REPO/main/version.txt",
#     "download_url": "https://raw.githubusercontent.com/USER/REPO/main/magicvoice_gui.py"
#   }
_UPDATE_DEFAULT_URL  = "https://magicvoice-update-1.onrender.com/download/magicvoice_gui.py"
_UPDATE_DEFAULT_VER  = "https://magicvoice-update-1.onrender.com/version"
# v3.22.1: Default extra_files (fallback khi update_config.json khong khai bao)
# -> Dam bao auth_manager.py + license_guard.py luon duoc tai cung khi update
_UPDATE_DEFAULT_EXTRA = {
    "auth_manager.py":  "https://raw.githubusercontent.com/buihuubac/magicvoice-releases/main/auth_manager.py",
    "license_guard.py": "https://raw.githubusercontent.com/buihuubac/magicvoice-releases/main/license_guard.py",
}

def _load_update_config():
    """Doc update_config.json neu co. Tra ve (download_url, version_url, extra_files).
    extra_files: dict {filename: url} cho cac file bo sung can update kem theo.
    Format mới:
      {
        "version_url":  "...",
        "download_url": "...",  // file chinh (magicvoice_gui.py)
        "extra_files": {        // cac file kem theo (optional)
          "license_guard.py": "https://..."
        }
      }
    """
    extra = {}
    try:
        _cfg_file = Path(__file__).parent / "update_config.json"
        if _cfg_file.exists():
            _d = json.loads(_cfg_file.read_text(encoding="utf-8"))
            _du = (_d.get("download_url") or "").strip()
            _vu = (_d.get("version_url")  or "").strip()
            _ef = _d.get("extra_files") or {}
            if isinstance(_ef, dict):
                for k, v in _ef.items():
                    if isinstance(k, str) and isinstance(v, str) and v.strip():
                        # Chi cho phep ten file an toan (khong path traversal)
                        safe_name = Path(k).name
                        if safe_name == k and not k.startswith("."):
                            extra[safe_name] = v.strip()
            # v3.22.1: Neu config khong co extra_files HOAC thieu file quan trong
            # -> bo sung tu default (dam bao auth_manager.py luon duoc tai)
            for _fname, _furl in _UPDATE_DEFAULT_EXTRA.items():
                if _fname not in extra:
                    extra[_fname] = _furl
            if _du and _vu:
                print(f"[Update] Dung URL tu update_config.json: {_vu}")
                if extra:
                    print(f"[Update] Extra files: {list(extra.keys())}")
                return _du, _vu, extra
    except Exception as _e:
        print(f"[Update] Loi doc update_config.json: {_e}")
    # Khong co config local hoac loi -> dung default (CO extra_files default)
    return _UPDATE_DEFAULT_URL, _UPDATE_DEFAULT_VER, dict(_UPDATE_DEFAULT_EXTRA)

UPDATE_URL, VERSION_URL, UPDATE_EXTRA_FILES = _load_update_config()

# Doc version tu file local version.txt (duoc cap nhat cung voi magicvoice_gui.py)
def _read_local_version():
    try:
        vf = Path(__file__).parent / "version.txt"
        if vf.exists():
            # FIX v3.37: dung utf-8-sig de tu dong strip BOM
            # (PowerShell `echo > file` mac dinh ghi BOM UTF-8 -> tool parse loi)
            return vf.read_text(encoding="utf-8-sig").strip()
    except Exception:
        pass
    return "2.1"  # fallback neu chua co file

CURRENT_VERSION = _read_local_version()
# ── Google Drive Model Config ─────────────────────────────
MODEL_DRIVE_ID   = "13UA5GLL7we60qKJZzJ3wDAWBsG2E242-"
MODEL_DRIVE_NAME = "MagicVoice_model.zip"
MODEL_CACHE_DIR  = Path.home() / ".cache" / "huggingface" / "hub"
MODEL_MARKER     = MODEL_CACHE_DIR / "models--k2-fsa--OmniVoice" / ".cache_ok"

def _model_is_cached() -> bool:
    """Kiem tra model da duoc tai ve chua."""
    snap = MODEL_CACHE_DIR / "models--k2-fsa--OmniVoice" / "snapshots"
    if not snap.exists():
        return False
    # Co it nhat 1 snapshot co file
    for d in snap.iterdir():
        if any(d.iterdir()):
            return True
    return False

def _download_model_from_drive(log_fn=None, progress_fn=None):
    """
    Tai model tu Google Drive ve cache HuggingFace.
    log_fn(msg, level): callback hien log
    progress_fn(pct, msg): callback hien tien trinh 0-100
    """
    import urllib.request, zipfile, tempfile, shutil, os

    def _log(msg, lv="info"):
        if log_fn: log_fn(msg, lv)
        else: print(msg)

    def _prog(pct, msg=""):
        if progress_fn: progress_fn(pct, msg)

    # URL voi cookie bypass cho file lon
    file_id = MODEL_DRIVE_ID
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"

    _log("Bat dau tai MagicVoice Model tu Google Drive...", "info")
    _prog(0, "Dang ket noi Google Drive...")

    tmp_zip = Path(tempfile.gettempdir()) / MODEL_DRIVE_NAME

    try:
        # Tai file voi progress
        def _reporthook(count, block_size, total_size):
            if total_size > 0:
                pct = min(90, int(count * block_size / total_size * 90))
                mb_done = count * block_size / 1_048_576
                mb_total = total_size / 1_048_576
                _prog(pct, f"Dang tai... {mb_done:.0f}MB / {mb_total:.0f}MB")

        _log(f"Dang tai {MODEL_DRIVE_NAME}...", "info")
        urllib.request.urlretrieve(url, str(tmp_zip), _reporthook)
        _prog(90, "Tai xong! Dang giai nen...")

        if not tmp_zip.exists() or tmp_zip.stat().st_size < 1_000_000:
            raise RuntimeError("File tai ve bi loi hoac qua nho!")

        # Giai nen vao HuggingFace cache
        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _log("Dang giai nen vao cache...", "info")

        with zipfile.ZipFile(str(tmp_zip), "r") as zf:
            total_files = len(zf.namelist())
            for i, member in enumerate(zf.namelist()):
                zf.extract(member, str(MODEL_CACHE_DIR))
                if i % 10 == 0:
                    pct = 90 + int(i / total_files * 9)
                    _prog(pct, f"Giai nen... {i}/{total_files}")

        _prog(100, "Hoan tat!")
        _log("Model da san sang!", "ok")
        return True

    except Exception as e:
        _log(f"Loi tai model: {e}", "err")
        raise
    finally:
        if tmp_zip.exists():
            try: tmp_zip.unlink()
            except: pass



def check_for_update(root, silent=False):
    """Kiem tra update tu GitHub moi khi mo app."""
    import threading

    def _check():
        try:
            import urllib.request
            with urllib.request.urlopen(VERSION_URL, timeout=8) as r:
                latest = r.read().decode().strip()

            if not latest:
                return

            # So sanh version
            def _ver(v):
                try: return tuple(int(x) for x in v.split("."))
                except: return (0,)

            if _ver(latest) <= _ver(CURRENT_VERSION):
                if not silent:
                    root.after(0, lambda: messagebox.showinfo(
                        "Cap nhat",
                        f"Ban dang dung phien ban moi nhat (v{CURRENT_VERSION})."))
                return

            # Co ban moi
            root.after(0, lambda: _ask(latest))

        except Exception:
            pass  # Khong co mang — bo qua lang

    def _ask(latest):
        # Dialog dep hon
        dlg = tk.Toplevel(root)
        dlg.title("Co ban cap nhat moi!")
        dlg.geometry("400x200")
        dlg.configure(bg=P["white"])
        dlg.resizable(False, False)
        dlg.grab_set()
        try: dlg.iconbitmap(str(_SCRIPT_DIR / "MagicVoice.ico"))
        except: pass

        tk.Label(dlg, text="Co ban cap nhat moi!", font=(FN,13,"bold"),
                 bg=P["white"], fg=P["purple"]).pack(pady=(20,4))
        tk.Label(dlg, text=f"Phien ban hien tai:  v{CURRENT_VERSION}",
                 font=(FN,10), bg=P["white"], fg=P["sub"]).pack()
        tk.Label(dlg, text=f"Phien ban moi nhat:  v{latest}",
                 font=(FN,10,"bold"), bg=P["white"], fg=P["green"]).pack()
        tk.Label(dlg, text="Cap nhat tu dong — app tu khoi dong lai sau khi tai xong.",
                 font=(FN,8), bg=P["white"], fg=P["dim"]).pack(pady=(6,0))

        btn_row = tk.Frame(dlg, bg=P["white"]); btn_row.pack(pady=16)
        tk.Button(btn_row, text="  Cap Nhat Ngay  ",
                  command=lambda: [dlg.destroy(), _do_update(latest)],
                  font=(FN,10,"bold"), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", padx=14, pady=6).pack(side="left", padx=6)
        tk.Button(btn_row, text="De Sau",
                  command=dlg.destroy,
                  font=(FN,9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=12, pady=6).pack(side="left")

    def _do_update(new_ver):
        """FIX v3.65 (12): tai va chay THANG bo cai dat day du
        (MagicVoice_Setup_vX.XX.exe, /VERYSILENT) thay vi va tung file rieng
        le (FILES_TO_UPDATE + updater.bat swap nhu truoc). Giai quyet DUT
        DIEM van de "cham 1 buoc" (khong con file nao co the bi thieu nua,
        vi moi lan update la cai dat lai TOAN BO tu ban moi nhat, khong con
        phu thuoc FILES_TO_UPDATE/files_manifest.json).

        Doi lai: cham hon vai chuc giay - vai phut (setup_helper.py tu kiem
        tra da cai chua, KHONG cai lai tu dau) thay vi vai giay nhu truoc.

        voices_library.json cua khach duoc BAO VE (installer dung
        Flags: onlyifdoesntexist rieng cho file nay - xem MagicVoice.iss) -
        khong bi xoa sach giong da luu moi lan update.

        LUU Y QUAN TRONG: co che nay CHI co hieu luc TU v3.65 TRO DI - khach
        dang o v3.64 tro ve truoc khi bam Cap Nhat se van chay CODE UPDATE
        CU cua chinh ho (dang FILES_TO_UPDATE cu), khong the "nhay" thang
        sang co che moi nay ngay duoc - gioi han kien truc khong the tranh
        khoi (code quyet dinh CACH update la code dang chay TRUOC KHI
        update, khong phai code cua ban moi). Tu khach da len duoc v3.65,
        cac lan update SAU (v3.65->v3.66...) moi thuc su dung co che nay.
        """
        try:
            import urllib.request, subprocess as _sp, sys as _sys, os as _os, tempfile as _tf
            import socket as _sock2

            # FIX v3.65 (14): dat rieng timeout du dai (60s/lan doc socket) cho
            # buoc tai installer nay - khong phu thuoc gia tri con sot lai tu
            # _is_online()/_check_network_badge() (truoc day set toi 2-3s toan
            # cuc, khien urlretrieve() file lon vai MB bi "read operation timed
            # out" giua chung du mang binh thuong - xem FIX 14 o 2 ham do).
            _sock2.setdefaulttimeout(60)

            app_dir = Path(__file__).resolve().parent
            installer_url = (
                f"https://github.com/buihuubac/magicvoice-releases/releases/"
                f"download/v{new_ver}/MagicVoice_Setup_v{new_ver}.exe"
            )

            # Progress window
            prog = tk.Toplevel(root)
            prog.title("Dang cap nhat...")
            prog.geometry("420x160")
            prog.configure(bg=P["white"])
            prog.resizable(False, False)
            prog.grab_set()
            try: prog.iconbitmap(str(_SCRIPT_DIR / "MagicVoice.ico"))
            except: pass

            lbl = tk.Label(prog, text=f"Dang tai v{new_ver}...",
                           font=(FN,11,"bold"), bg=P["white"], fg=P["purple"], pady=12)
            lbl.pack()
            status_lbl = tk.Label(prog, text="Chuan bi...",
                                  font=(FN,9), bg=P["white"], fg=P["sub"])
            status_lbl.pack()
            bar_bg = tk.Frame(prog, bg=P["border"], height=8, width=360)
            bar_bg.pack(pady=10)
            bar = tk.Frame(bar_bg, bg=P["purple"], height=8, width=0)
            bar.place(x=0, y=0, height=8)
            tk.Label(prog, text="Vui long khong tat app...",
                     font=(FN,8), bg=P["white"], fg=P["dim"]).pack()
            prog.update()

            installer_path = _os.path.join(_tf.gettempdir(), f"MagicVoice_Setup_v{new_ver}.exe")

            def _report(block_num, block_size, total_size):
                if total_size > 0:
                    pct = min(100, int(block_num * block_size * 100 / total_size))
                    bar.config(width=int(360 * pct / 100))
                    status_lbl.config(text=f"Dang tai bo cai dat... {pct}%")
                    prog.update()

            try:
                urllib.request.urlretrieve(installer_url, installer_path, _report)
            except Exception as _dl_err:
                try: _os.remove(installer_path)
                except Exception: pass
                raise RuntimeError(f"Tai bo cai dat that bai: {_dl_err}") from _dl_err

            if not _os.path.exists(installer_path) or _os.path.getsize(installer_path) < 500_000:
                try: _os.remove(installer_path)
                except Exception: pass
                raise RuntimeError("File cai dat tai ve khong hop le (qua nho/rong)")

            bar.config(width=360)
            status_lbl.config(text="Hoan tat, dang cai dat lai...")
            prog.update()
            import time
            time.sleep(0.5)
            prog.destroy()

            messagebox.showinfo(
                "Cap nhat thanh cong!",
                f"Da tai xong v{new_ver}!\n\n"
                "App se dong lai va tu cai dat lai trong giay lat (co the mat "
                "vai chuc giay - vai phut), sau do tu mo lai. "
                "Vui long KHONG tat may tinh trong luc nay.")

            # FIX v3.65 (12): sinh 1 file .bat TAM (khong can co san tren may
            # khach - tu tao ngay tai day) de: (1) cho app HIEN TAI dong han
            # roi moi tiep tuc (tranh loi file .pyd dang bi khoa khi installer
            # ghi de - dung lai chinh xac pattern wait-loop da chung minh on
            # dinh cua updater.bat cu), (2) chay installer IM LANG, cai DUNG
            # vao thu muc hien tai (/DIR=...) de bao toan duong dan cai dat
            # cua khach (co the khac mac dinh cua Inno neu ho cai tu ban .bat/
            # zip cu truoc day), (3) tu don dep installer + chinh no sau khi xong.
            _pid = _os.getpid()
            _wait_bat = _os.path.join(_tf.gettempdir(), f"_mv_update_{_pid}.bat")
            _bat_content = (
                "@echo off\r\n"
                f"set \"APP_PID={_pid}\"\r\n"
                ":wait_loop\r\n"
                "tasklist /FI \"PID eq %APP_PID%\" 2>nul | find \"%APP_PID%\" >nul\r\n"
                "if errorlevel 1 goto :run_installer\r\n"
                "ping -n 2 127.0.0.1 >nul 2>&1\r\n"
                "goto :wait_loop\r\n"
                ":run_installer\r\n"
                "ping -n 2 127.0.0.1 >nul 2>&1\r\n"
                f"\"{installer_path}\" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=\"{app_dir}\"\r\n"
                f"del /f \"{installer_path}\" >nul 2>&1\r\n"
                "del /f \"%~f0\" >nul 2>&1\r\n"
            )
            with open(_wait_bat, "w", encoding="utf-8") as _f:
                _f.write(_bat_content)

            # SW_HIDE + CREATE_NEW_PROCESS_GROUP: an cua so CMD, process tiep
            # tuc song sau khi app chinh da dong (giong pattern cu da on dinh).
            _si = _sp.STARTUPINFO()
            _si.dwFlags = _sp.STARTF_USESHOWWINDOW
            _si.wShowWindow = 0   # SW_HIDE
            _sp.Popen(
                ["cmd.exe", "/C", _wait_bat],
                creationflags=0x00000200,  # CREATE_NEW_PROCESS_GROUP
                startupinfo=_si,
            )

            # Dong app de installer co the ghi de file dang bi khoa
            root.after(300, lambda: (root.destroy(), _sys.exit(0)))

        except Exception as e:
            try: prog.destroy()
            except: pass
            messagebox.showerror("Loi cap nhat",
                f"Cap nhat that bai:\n{e}\n\nThu lai sau.")

    threading.Thread(target=_check, daemon=True).start()


def _quick_cuda_check() -> bool:
    """Kiem tra CUDA co san KHONG import torch (~0ms, chi check file)."""
    import os
    # Windows: check NVIDIA CUDA driver DLL
    for p in [r"C:\Windows\System32\nvcuda.dll",
              r"C:\Windows\System32\nvml.dll",
              r"C:\Windows\System32\nvidia-smi.exe",
              r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"]:
        if os.path.exists(p):
            return True
    return False


class App(tk.Tk):
    def __init__(self, login_msg="", username=""):
        super().__init__()
        self._login_msg = login_msg
        self._username  = username

        # v3.22: Single-session heartbeat
        self._heartbeat_stop = False
        self._heartbeat_fail_count = 0  # Demem so lan goi server fail lien tiep
        # FIX v3.66 (bao mat 2026-07-24, theo yeu cau anh Bac): truoc day
        # heartbeat CHI dong app khi server chu dong bao "kicked" (bi may
        # khac dang nhap de) - neu khach (hoac ke crack) CHAN HAN MANG toi
        # server (vd sua file hosts) ngay sau khi dang nhap 1 lan hop le,
        # heartbeat mai mai chi nhan "error" (khong lien lac duoc server),
        # KHONG BAO GIO bi kick -> app chay VO THOI HAN khong can server
        # xac nhan lai lan nao nua. Gio theo doi THOI GIAN LIEN TUC mat ket
        # noi - qua nguong (8 tieng) thi hien canh bao + tu dong dong app
        # sau vai phut neu khach khong phan hoi.
        self._heartbeat_offline_since = None      # timestamp bat dau mat ket noi lien tuc
        self._heartbeat_offline_prompted = False  # da hien canh bao cho chu ky nay chua
        self._offline_warn_win = None             # cua so canh bao dang hien (neu co)

        # FIX: Tu xoa cache rac 1 lan khi update len v3.17.
        # Vi sao: khach v3.16 update len v3.17 -> chay code update CUA v3.16 (cu),
        # khong co logic xoa cache moi. Cache rac (ref_text Whisper sai luu vinh vien)
        # van con -> voice clone van loi.
        # Giai phap: chay xoa cache ngay khi App khoi dong, dung flag file de chi
        # chay 1 LAN duy nhat sau update.
        self._auto_clear_legacy_cache_once()

        self.title(f"MagicVoice TTS Studio  v{CURRENT_VERSION}")
        # Set icon: taskbar + title bar + Alt+Tab
        try:
            import ctypes
            # Phai set AppUserModelID TRUOC KHI tao cua so de Windows hien dung icon
            app_id = "MagicVoice.TTS.Studio.v2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass
        try:
            icon_path = _SCRIPT_DIR / "MagicVoice.ico"
            if icon_path.exists():
                ico_str = str(icon_path)
                # Dat icon cho window (title bar)
                self.iconbitmap(default=ico_str)
                # Dat icon cho taskbar (Windows can after(0) de hieu luc)
                self.after(0, lambda: self._set_taskbar_icon(ico_str))
        except Exception:
            pass
        # FIX v3.68 (theo anh Bac bao loi 2026-07-26): kich thuoc co dinh
        # "1160x780" khien nut "Tao" (statusbar duoi cung) bi che/khuat tren
        # may man hinh nho hoac do phan giai thap (vd laptop 1366x768 tro
        # xuong, sau khi tru taskbar Windows co the khong con du 780px cao).
        # Sua: mo TOI DA HOA theo dung man hinh that cua khach (Windows
        # 'zoomed' state) thay vi 1 kich thuoc co dinh - dam bao luon du
        # cho hien statusbar bat ke do phan giai may nao. Van giu minsize
        # lam san neu khach tu bo phong to.
        self.minsize(960,660)
        try:
            self.state('zoomed')
        except Exception:
            self.geometry("1160x780")
        self.configure(bg=P["bg"])

        self.lib=VoiceLib()
        self.sel_idx=0
        self.model_loaded=False
        self.is_running=False
        self._running_tab=None   # MOI: theo doi tab dang chay (text/srt/batch/None)
        self.cancel_ev=threading.Event()

        # config
        # Tải cấu hình đã lưu
        self._cfg = load_config()

        # FIX v3.68 (theo anh Bac bao loi 2026-07-26, khoi dong bi crash):
        # BUG THAT SU - self.tts_mode/edge_voice_var/fast_voice_var truoc
        # day CHI duoc tao BEN TRONG _build_sidebar() (goi o dong ~3642),
        # nhung _build_left() (goi o dong ~3633, TRUOC _build_sidebar) lai
        # goi _build_srt_tab() - noi vua them nut chon nhanh THAM CHIEU
        # THANG self.tts_mode.get() NGAY LUC TAO WIDGET (khong phai trong
        # callback) -> AttributeError vi thuoc tinh chua ton tai, crash
        # ngay khoi dong. Sua GOC: tao truoc cac bien trang thai dung chung
        # nay O DAY (truoc khi bat ky tab/sidebar nao duoc build), de moi
        # noi tham chieu deu an toan bat ke thu tu build.
        self.tts_mode = tk.StringVar(value="omnivoice")
        self.edge_voice_var = tk.StringVar(value="en-US-AriaNeural")
        self.edge_voice_display = tk.StringVar(value=EDGE_VOICES_LIST[0][1])
        self.fast_voice_var = tk.StringVar(value=FAST_VOICES_LIST[0][0])
        self.fast_voice_display = tk.StringVar(value=FAST_VOICES_LIST[0][1])

        _default_device = "cuda:0" if _quick_cuda_check() else "cpu"
        self.device_var   =tk.StringVar(value=self._cfg.get("device", _default_device))
        self.dtype_var    =tk.StringVar(value=self._cfg.get("dtype","float32"))
        self.steps_var    =tk.IntVar(value=self._cfg.get("steps",24))
        self.speed_var    =tk.DoubleVar(value=1.0)
        self.vol_var      =tk.DoubleVar(value=1.0)
        self.pitch_var    =tk.DoubleVar(value=1.0)
        self.out_dir_var  =tk.StringVar(value=self._cfg.get("out_dir",
                            str(Path.home()/"Downloads"/"MagicVoice")))
        self.out_name_var =tk.StringVar(value="output")
        self.fmt_var      =tk.StringVar(value=self._cfg.get("fmt",".wav"))
        self.post_proc_var=tk.BooleanVar(value=self._cfg.get("post_process", True))
        self.text_proc_var=tk.BooleanVar(value=self._cfg.get("text_process", True))
        self.gap_var      =tk.IntVar(value=400)
        self.narrator_var  =tk.BooleanVar(value=self._cfg.get('narrator_mode',False))
        self.script_proc_var=tk.BooleanVar(value=self._cfg.get('script_proc',False))
        # FIX v3.67 (tinh nang moi, theo yeu cau anh Bac): xuat .srt timeline
        # khop audio vua tao o tab SRT - mac dinh TAT (khach chu dong tich khi can).
        self.srt_timeline_var = tk.BooleanVar(value=bool(self._cfg.get('srt_timeline_export', False)))
        self.srt_entries: list[SRTEntry]=[]
        self._txt_files:  list[str]=[]

        # ── MOI: Naming options TOAN CUC (ap dung cho moi tab) ──
        # Mac dinh: giu ten goc (neu khong dat ten, tu dong luu dung ten file input)
        self.out_name_mode   = tk.StringVar(value=self._cfg.get("out_name_mode","keep"))
        self.out_prefix_var  = tk.StringVar(value=self._cfg.get("out_prefix","voice_"))
        self.out_start_var   = tk.IntVar(value=int(self._cfg.get("out_start",1)))
        self.out_pad_var     = tk.IntVar(value=int(self._cfg.get("out_pad",2)))
        self.out_ask_name_var= tk.BooleanVar(value=bool(self._cfg.get("out_ask_name",False)))
        # Counter session - chay dan moi lan gen file (cho tab Text/SRT don le)
        self._out_counter_offset = 0

        self._detect_devices()
        self._build()
        self._apply_ttk_styles()
        # Khôi phục voice đã chọn từ lần trước
        saved_name = self._cfg.get("sel_voice_name", "")
        if saved_name:
            for i, vp in enumerate(self.lib.profiles):
                if vp.name == saved_name:
                    self.sel_idx = i
                    break
        # Lưu cấu hình khi đóng app
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Auto-reload model khi doi device (sau khi _build xong)
        self.device_var.trace_add("write", self._on_device_changed)
        # Log thông tin voices khi khởi động
        self.after(300, self._log_startup_info)
        # Kiem tra mang NGAY khi khoi dong - set TRANSFORMERS_OFFLINE truoc khi load model
        self.after(100, self._init_network_mode)
        # Kiem tra update tu dong khi khoi dong (silent - khong thong bao neu dang moi nhat)
        self.after(3000, lambda: check_for_update(self, silent=True))
        self.after(800, self._check_gpu_and_warn)
        # v3.22: Bat dau heartbeat single-session sau 30s (de tranh kick ngay khi vua login)
        self.after(30000, self._start_heartbeat_thread)
        # Tự động tải model nếu đã từng tải trước đó
        if self._cfg.get("auto_load", True):
            self.after(1000, self._auto_load_model)  # Cho _init_network_mode chay truoc
        else:
            self._log("💡 Nhấn '⬇ Tải Model' để bắt đầu. Lần sau sẽ tự động tải!", "info")
        # Tu dong cai thu vien con thieu (dung sys.executable - chinh xac 100%)
        threading.Thread(target=_ensure_deps, daemon=True).start()

    def _detect_devices(self):
        self.devices = ["cpu"]
        threading.Thread(target=self._detect_devices_bg, daemon=True).start()

    def _detect_devices_bg(self):
        """Detect GPU/CUDA trong background — KHONG block UI."""
        try:
            import torch
            devs = ["cpu"]
            for i in range(torch.cuda.device_count()):
                devs.append(f"cuda:{i}")
            if getattr(getattr(torch, "backends", None), "mps", None) and \
               torch.backends.mps.is_available():
                devs.append("mps")
            self.devices = devs
            # Neu quick_check sai (khong co CUDA that su) va device_var la cuda:0 → sua ve cpu
            if self.device_var.get().startswith("cuda") and not torch.cuda.is_available():
                self.after(0, lambda: self.device_var.set("cpu"))
            # Cap nhat combobox values neu da tao roi
            if hasattr(self, "_device_cb"):
                self.after(0, lambda d=devs: self._device_cb.configure(values=d))
            # Lan dau chay: tu dong chon preset phu hop voi GPU
            if not self._cfg.get("preset_detected"):
                self._auto_detect_preset()
        except Exception:
            pass

    def _auto_detect_preset(self):
        """Phat hien GPU/VRAM va tu dong chon preset lan dau chay."""
        try:
            import torch
            _vram_gb = 0.0
            _gpu_name = "CPU only"
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                _vram_gb = props.total_memory / (1024 ** 3)
                _gpu_name = props.name
            # >= 6GB VRAM: Chuan (float32/24 steps)
            # < 6GB hoac CPU: May yeu (float16/8 steps)
            if _vram_gb >= 6.0:
                preset, dtype, steps = "Chuẩn", "float32", 24
            else:
                preset, dtype, steps = "Máy yếu", "float16", 8

            def _apply():
                self.dtype_var.set(dtype)
                self.steps_var.set(steps)
                if hasattr(self, "_cfg_preset_var"):
                    self._cfg_preset_var.set(preset)
                self._cfg.update({"dtype": dtype, "steps": steps,
                                   "preset_detected": True})
                save_config(self._cfg)
                if _vram_gb > 0:
                    self._log(
                        f"🖥 GPU: {_gpu_name} ({_vram_gb:.1f}GB VRAM)"
                        f" → tự động chọn [{preset}]"
                        f" (float{dtype[-2:]}/steps={steps})", "info")
                else:
                    self._log(
                        "🖥 Không có GPU → tự động chọn [Máy yếu]"
                        " (float16/steps=8)", "info")
            self.after(0, _apply)
        except Exception:
            pass

    # ─────────────────────────── LAYOUT ───────────────────────────
    def _build(self):
        # ── Topbar ──
        self._build_topbar()
        tk.Frame(self,bg=P["border"],height=1).pack(fill="x")

        # ── Main ──
        main=tk.Frame(self,bg=P["bg"])
        main.pack(fill="both",expand=True)

        # LEFT — content tabs
        left=tk.Frame(main,bg=P["bg"])
        left.pack(side="left",fill="both",expand=True)
        self._build_left(left)

        self._right_divider=tk.Frame(main,bg=P["border"],width=1)
        self._right_divider.pack(side="left",fill="y")

        # RIGHT — settings sidebar
        self._right_pane=tk.Frame(main,bg=P["white"],width=290)
        self._right_pane.pack(side="right",fill="y")
        self._right_pane.pack_propagate(False)
        self._build_sidebar(self._right_pane)

        # ── Statusbar ──
        self._statusbar_sep=tk.Frame(self,bg=P["border"],height=1)
        self._statusbar_sep.pack(fill="x")
        self._build_statusbar()

    def _build_topbar(self):
        bar=tk.Frame(self,bg=P["white"],pady=0)
        bar.pack(fill="x")

        # Logo
        logo=tk.Frame(bar,bg=P["white"])
        logo.pack(side="left",padx=16,pady=10)
        tk.Label(logo,text="🎙",font=("",18),bg=P["white"]).pack(side="left")
        tk.Label(logo,text=" MagicVoice TTS Studio",
                 font=(FN,13,"bold"),bg=P["white"],fg=P["text"]).pack(side="left")
        tk.Label(logo,text=f"  v{CURRENT_VERSION}",
                 font=(FN,9),bg=P["white"],fg=P["dim"]).pack(side="left")

        # Hien thi thong tin tai khoan (so ngay con lai)
        if hasattr(self, "_login_msg") and self._login_msg:
            self._show_account_badge(bar)
        # Kiem tra mang va hien badge
        self.after(1500, lambda: self._check_network_badge(bar))

        # Right controls
        rc=tk.Frame(bar,bg=P["white"]); rc.pack(side="right",padx=16,pady=8)

        self.model_dot=tk.Label(rc,text="●",font=(FN,12),
                                 bg=P["white"],fg=P["red"])
        self.model_dot.pack(side="left")
        self.model_lbl=tk.Label(rc,text=" Chưa tải model",
                                 font=(FN,9),bg=P["white"],fg=P["sub"])
        self.model_lbl.pack(side="left",padx=(0,10))

        # Device / dtype
        for var,vals,w in [(self.device_var,self.devices,7),
                            (self.dtype_var,["float32","float16","bfloat16"],9)]:
            cb=ttk.Combobox(rc,textvariable=var,values=vals,
                            state="readonly",width=w,font=(FN,9))
            cb.pack(side="left",padx=3)
            if var is self.device_var:
                self._device_cb = cb
            elif var is self.dtype_var:
                cb.bind("<<ComboboxSelected>>", self._on_model_cfg_changed)

        # Steps spinbox
        tk.Label(rc,text="Steps:",font=(FN,8),bg=P["white"],
                 fg=P["dim"]).pack(side="left",padx=(6,0))
        _spx = tk.Spinbox(rc,from_=4,to=50,increment=1,textvariable=self.steps_var,
                   width=4,font=(FN,9),relief="flat",
                   bg=P["white"],fg=P["text"],
                   highlightthickness=1,highlightbackground=P["border"],
                   command=self._on_model_cfg_changed)
        _spx.pack(side="left",padx=(2,6),ipady=2)
        _spx.bind("<FocusOut>", self._on_model_cfg_changed)
        _spx.bind("<Return>",   self._on_model_cfg_changed)

        # Cau hinh nhanh: Chuan (24/fp32) hoac May yeu (8/fp16)
        self._cfg_preset_var = tk.StringVar(value="Chuẩn")
        _cfg_cb = ttk.Combobox(rc,textvariable=self._cfg_preset_var,
                               values=["Chuẩn","Máy yếu"],
                               state="readonly",width=9,font=(FN,9))
        _cfg_cb.pack(side="left",padx=(0,6))
        def _apply_cfg(e=None):
            if self._cfg_preset_var.get() == "Máy yếu":
                self.steps_var.set(8)
                self.dtype_var.set("float16")
            else:
                self.steps_var.set(24)
                self.dtype_var.set("float32")
            # Luu lua chon cua user, danh dau da set de lan sau khong auto-override
            self._cfg.update({"steps": self.steps_var.get(),
                               "dtype": self.dtype_var.get(),
                               "preset_detected": True})
            save_config(self._cfg)
        _cfg_cb.bind("<<ComboboxSelected>>",_apply_cfg)

        self.load_btn=tk.Button(rc,text="⬇  Tải Model",
                                 command=self._load_model,
                                 font=(FN,9,"bold"),bg=P["purple"],fg="white",
                                 relief="flat",cursor="hand2",
                                 padx=12,pady=5)
        self.load_btn.pack(side="left",padx=(6,0))

    def _build_left(self, parent):
        # Tab buttons
        tab_bar=tk.Frame(parent,bg=P["bg"],pady=0)
        tab_bar.pack(fill="x",padx=0)

        self.tab_frames={}
        self.tab_btns={}
        self._tab_labels={}   # MOI: luu text goc de restore khi bo cham tron
        tabs=[("text","📄 Văn Bản"),("srt","🎞 Phụ Đề SRT"),
              ("batch","📁 Hàng Loạt"),("clone","🎤 Clone Voice"),
              ("script","✍ Kịch Bản"),("ghep","🎬 Ghép Video"),
              ("giahan","💳 Gia Hạn")]

        content=tk.Frame(parent,bg=P["bg"])
        content.pack(fill="both",expand=True)

        self._tab_indicators = {}  # bottom-border indicator frames
        for key,label in tabs:
            frm=tk.Frame(content,bg=P["bg"])
            self.tab_frames[key]=frm
            # Wrap tab button + indicator trong 1 frame dọc
            _tw = tk.Frame(tab_bar, bg=P["bg"])
            _tw.pack(side="left")
            btn=tk.Button(_tw,text=label,
                          command=lambda k=key:self._switch_tab(k),
                          font=(FN,10),relief="flat",cursor="hand2",
                          padx=16,pady=9,bg=P["bg"],fg=P["sub"],
                          bd=0,
                          activebackground=P["sel"],activeforeground=P["purple"])
            btn.pack(fill="x")
            # Indicator line (bottom-border)
            ind = tk.Frame(_tw, bg=P["bg"], height=3)
            ind.pack(fill="x")
            self._tab_indicators[key] = ind
            self.tab_btns[key]=btn
            self._tab_labels[key]=label   # luu label goc

        self._build_text_tab(self.tab_frames["text"])
        self._build_srt_tab(self.tab_frames["srt"])
        self._build_batch_tab(self.tab_frames["batch"])
        self._build_clone_tab(self.tab_frames["clone"])
        self._build_script_tab(self.tab_frames["script"])
        self._build_ghep_tab(self.tab_frames["ghep"])
        self._build_giahan_tab(self.tab_frames["giahan"])
        self._switch_tab("text")

    def _switch_tab(self, key):
        if key == "srt" and hasattr(self, "_refresh_srt_voices"):
            self.after(50, self._refresh_srt_voices)
        for k,f in self.tab_frames.items():
            f.pack_forget()
        self.tab_frames[key].pack(fill="both",expand=True,padx=0)

        # Tab Ghép Video: ẩn sidebar TTS + thanh tạo (không liên quan đến ghép video)
        _prev_ghep = getattr(self, "_ghep_tab_active", False)
        _now_ghep  = (key == "ghep")
        self._ghep_tab_active = _now_ghep
        _panels = [getattr(self, "_right_divider", None),
                   getattr(self, "_right_pane", None),
                   getattr(self, "_statusbar_sep", None),
                   getattr(self, "_statusbar_frame", None),
                   getattr(self, "_log_bar", None),
                   getattr(self, "logbox", None)]
        _panels = [w for w in _panels if w is not None]
        if _now_ghep:
            for w in _panels:
                w.pack_forget()
        elif _prev_ghep:
            # Khôi phục đúng thứ tự pack: sidebar → statusbar → log
            self._right_pane.pack(side="right", fill="y")
            self._right_divider.pack(side="left", fill="y")
            self._statusbar_sep.pack(fill="x")
            self._statusbar_frame.pack(fill="x")
            if hasattr(self, "_log_bar"):
                self._log_bar.pack(fill="x")
            if hasattr(self, "logbox"):
                self.logbox.pack(fill="x", padx=0)
        for k,b in self.tab_btns.items():
            active=k==key
            # MOI: danh dau tab dang chay bang cham tron (•)
            is_run = (k == getattr(self, "_running_tab", None))
            _orig = self._tab_labels.get(k, "") if hasattr(self, "_tab_labels") else b.cget("text").replace(" •","").rstrip()
            _label = _orig + (" •" if is_run else "")
            if is_run:
                _bg = "#fef3c7"; _fg = P["red"]; _ind = P["red"]
            elif active:
                _bg = P["sel"]; _fg = P["purple"]; _ind = P["purple"]
            else:
                _bg = P["bg"]; _fg = P["sub"]; _ind = P["bg"]
            b.configure(
                text=_label, fg=_fg, bg=_bg,
                font=(FN,10,"bold") if (active or is_run) else (FN,10),
            )
            if hasattr(self, "_tab_indicators") and k in self._tab_indicators:
                self._tab_indicators[k].configure(bg=_ind)

    def _refresh_tab_indicators(self):
        """Update style nut tab (cham tron •) MA KHONG goi _switch_tab."""
        if not hasattr(self, "tab_btns"): return
        try:
            cur = next((k for k,f in self.tab_frames.items() if f.winfo_ismapped()), None)
            run = getattr(self, "_running_tab", None)
            for k, b in self.tab_btns.items():
                active = (k == cur)
                is_run = (k == run)
                _orig  = self._tab_labels.get(k, "")
                _label = _orig + (" •" if is_run else "")
                if is_run:
                    _bg = "#fef3c7"; _fg = P["red"]; _ind = P["red"]
                elif active:
                    _bg = P["sel"]; _fg = P["purple"]; _ind = P["purple"]
                else:
                    _bg = P["bg"]; _fg = P["sub"]; _ind = P["bg"]
                b.configure(
                    text=_label, fg=_fg, bg=_bg,
                    font=(FN,10,"bold") if (active or is_run) else (FN,10),
                )
                if hasattr(self, "_tab_indicators") and k in self._tab_indicators:
                    self._tab_indicators[k].configure(bg=_ind)
        except Exception:
            pass

    # ─────── Tab: Văn Bản ──────────────────────────────────────────
    def _build_text_tab(self, p):
        inner = tk.Frame(p, bg=P["white"],
                         highlightthickness=1,
                         highlightbackground=P["border"])
        inner.pack(fill="both", expand=True, padx=14, pady=10)

        # ── Toolbar row 1: label + action buttons (luôn đủ các nút) ──
        tb = tk.Frame(inner, bg=P["white"], pady=5)
        tb.pack(fill="x", padx=10)
        # Pack right-side buttons TRƯỚC (đảm bảo luôn hiển thị dù window hẹp)
        self.char_lbl = tk.Label(tb, text="0 ký tự",
                                  font=(FN,9), bg=P["white"], fg=P["dim"])
        self.char_lbl.pack(side="right", padx=(4,0))
        tk.Frame(tb, bg=P["border"], width=1).pack(side="right", fill="y", pady=2, padx=4)
        for txt, cmd, _bg, _fg in [
            ("📂 Mở TXT", self._import_txt,     P["hover"],  P["label"]),
            ("🗑 Xóa",    lambda: self.txt_in.delete("1.0","end"), "#fff5f5", P["red"]),
        ]:
            tk.Button(tb, text=txt, command=cmd,
                      font=(FN,9), bg=_bg, fg=_fg,
                      relief="flat", cursor="hand2", padx=8, pady=4,
                      activebackground=P["sel"], activeforeground=P["purple"],
                      highlightthickness=1, highlightbackground=P["border"]
                      ).pack(side="right", padx=(0,3))
        self._txt_prev_btn = tk.Button(tb, text="🎧 Nghe Thử",
                      command=self._preview_text_input,
                      font=(FN,9,"bold"), bg="#f0fdf4", fg="#16a34a",
                      relief="flat", cursor="hand2", padx=10, pady=4,
                      activebackground="#dcfce7", activeforeground="#15803d",
                      highlightthickness=1, highlightbackground="#86efac")
        self._txt_prev_btn.pack(side="right", padx=(0,4))
        tk.Label(tb, text="📝 Văn Bản",
                 font=(FN,10,"bold"), bg=P["white"],
                 fg=P["label"]).pack(side="left")

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Char cleaner bar ──
        cbar = tk.Frame(inner, bg=P["sidebar"], pady=3)
        cbar.pack(fill="x")
        tk.Label(cbar, text="  Xóa ký tự:",
                 font=(FN,8), bg=P["sidebar"],
                 fg=P["dim"]).pack(side="left")
        for lbl, ch in [("*","*"),("/","/"),(  "#","#"),("---","---"),("...","...")]:
            tk.Button(cbar, text=lbl,
                      command=lambda c=ch: self._del_char_from_text(c),
                      font=("Consolas",8), bg=P["white"], fg=P["label"],
                      relief="flat", cursor="hand2", padx=7, pady=3,
                      activebackground=P["sel"], activeforeground=P["purple"],
                      highlightthickness=1, highlightbackground=P["border"]
                      ).pack(side="left", padx=2)
        tk.Label(cbar, text="|  Tùy chỉnh:",
                 font=(FN,8), bg=P["sidebar"],
                 fg=P["dim"]).pack(side="left", padx=(8,2))
        self.custom_char_var = tk.StringVar()
        tk.Entry(cbar, textvariable=self.custom_char_var,
                 font=("Consolas",9), width=8,
                 bg=P["white"], fg=P["text"], relief="flat",
                 highlightthickness=1,
                 highlightbackground=P["border"]
                 ).pack(side="left", ipady=3)
        tk.Button(cbar, text="Xóa Tất Cả",
                  command=self._del_custom_char,
                  font=(FN,8,"bold"), bg=P["red"], fg="white",
                  relief="flat", cursor="hand2", padx=8, pady=3,
                  activebackground="#dc2626", activeforeground="white"
                  ).pack(side="left", padx=4)
        tk.Button(cbar, text="🔄 Khôi phục",
                  command=self._restore_text,
                  font=(FN,8), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=8, pady=3,
                  activebackground=P["sel"], activeforeground=P["purple"]
                  ).pack(side="left", padx=2)

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Toi uu doc (TTS-friendly) bar ──
        # Bat mac dinh - chi doi dau cau/khoang trang/gach noi, KHONG doi tu.
        # Chi ap dung tren BAN SAO ngay truoc khi tao voice (o _do_text),
        # khong sua o van ban goc cua khach.
        tfbar = tk.Frame(inner, bg=P["sidebar"], pady=3)
        tfbar.pack(fill="x")
        self.tts_friendly_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tfbar, text="✨ Tối ưu đọc (TTS-friendly)",
                        variable=self.tts_friendly_var,
                        font=(FN,8,"bold"), bg=P["sidebar"], fg=P["label"],
                        activebackground=P["sidebar"], selectcolor=P["white"],
                        cursor="hand2"
                        ).pack(side="left", padx=(4,2))
        tk.Label(tfbar, text="(tách câu quá dài, bỏ gạch nối — giữ nguyên từ ngữ)",
                 font=(FN,7), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        tk.Button(tfbar, text="👁 Xem trước",
                  command=self._preview_tts_friendly,
                  font=(FN,8), bg=P["white"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=8, pady=2,
                  activebackground=P["sel"], activeforeground=P["purple"],
                  highlightthickness=1, highlightbackground=P["border"]
                  ).pack(side="right", padx=4)

        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): them tuy chon "Xuat
        # file phu de .srt khop giong doc" cho tab Van Ban - giong het tinh
        # nang da co o tab Phu De SRT (self.srt_timeline_var), nhung dung
        # bien RIENG cho tab nay vi day la 1 lua chon doc lap voi tab SRT.
        _txt_tl_bar = tk.Frame(inner, bg=P["sidebar"], pady=3)
        _txt_tl_bar.pack(fill="x")
        self.text_srt_timeline_var = tk.BooleanVar(value=False)
        tk.Checkbutton(_txt_tl_bar, text="📝 Xuất file phụ đề .srt khớp giọng đọc",
                        variable=self.text_srt_timeline_var,
                        font=(FN,8,"bold"), bg=P["sidebar"], fg=P["label"],
                        activebackground=P["sidebar"], selectcolor=P["white"],
                        cursor="hand2").pack(side="left", padx=(4,2))
        tk.Label(_txt_tl_bar, text="(timeline khớp đúng audio vừa tạo)",
                 font=(FN,7), bg=P["sidebar"], fg=P["dim"]).pack(side="left")

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Text area ──
        sb = tk.Scrollbar(inner, orient="vertical")
        sb.pack(side="right", fill="y")
        self.txt_in = tk.Text(inner, wrap="word", relief="flat",
                               bg=P["white"], fg=P["text"],
                               insertbackground=P["purple"],
                               font=(FN,11), padx=14, pady=10,
                               highlightthickness=0,
                               yscrollcommand=sb.set)
        self.txt_in.pack(fill="both", expand=True)
        sb.config(command=self.txt_in.yview)
        self._ph(self.txt_in,
                 "Nhập nội dung văn bản tại đây…\n\n"
                 "Hỗ trợ 600+ ngôn ngữ: Tiếng Việt, English, 中文, 日本語, 한국어…")
        self.txt_in.bind("<KeyRelease>",
            lambda e: self.char_lbl.config(
                text=f"{len(self.txt_in.get('1.0','end-1c')):,} ký tự"))

    def _build_srt_tab(self, p):
        inner=tk.Frame(p,bg=P["white"],
                       highlightthickness=1,highlightbackground=P["border"])
        inner.pack(fill="both",expand=True,padx=14,pady=10)

        # ── Toolbar ──
        top=tk.Frame(inner,bg=P["white"],pady=6)
        top.pack(fill="x",padx=10)
        self.srt_path=tk.StringVar()
        tk.Entry(top,textvariable=self.srt_path,
                 font=(FN,9),relief="flat",bg=P["sidebar"],
                 fg=P["text"],insertbackground=P["purple"],
                 highlightthickness=1,highlightbackground=P["border"],
                 highlightcolor=P["purple"],width=28
                 ).pack(side="left",padx=(0,4),ipady=4)
        tk.Button(top,text="📂 Mở .srt",command=self._open_srt,
                  font=(FN,9),bg=P["purple"],fg="white",
                  relief="flat",cursor="hand2",padx=8,pady=4
                  ).pack(side="left",padx=(0,4))
        tk.Button(top,text="🗑 Xóa",
                  command=self._srt_clear,
                  font=(FN,9),bg=P["hover"],fg=P["label"],
                  relief="flat",cursor="hand2",padx=8,pady=4
                  ).pack(side="left",padx=(0,4))
        tk.Button(top,text="🔁 Gọi lại phiên cũ",
                  command=lambda: self._recall_session(tab_filter="srt"),
                  font=(FN,9),bg=P["gold"],fg="white",
                  relief="flat",cursor="hand2",padx=8,pady=4
                  ).pack(side="left")
        self.srt_cnt_lbl=tk.Label(top,text="",font=(FN,9),
                                   bg=P["white"],fg=P["dim"])
        self.srt_cnt_lbl.pack(side="right")

        # FIX v3.68 (theo anh Bac bao loi 2026-07-26, sua lai lan 8): lan
        # truoc TUONG da gop chung 1 hang nhung thuc ra van tao THEM 1 frame
        # rieng (row2) dat NGAY DUOI - van la 2 hang, lam TANG chieu cao,
        # day nut "Tao" (statusbar) ra ngoai man hinh vi cua so co the khong
        # tu gian them. Sua THAT SU: nhet TRUC TIEP vao chung frame "top"
        # (cung 1 hang voi Mo .srt/Xoa/Goi lai phien cu), khong tao frame
        # rieng nua.
        tk.Label(top, text="Chế độ:", font=(FN,9,"bold"),
                 bg=P["white"], fg=P["label"]).pack(side="left", padx=(14,4))
        _srt_mode_btns = {}
        for _mval, _mlbl in [("omnivoice","🤖 MagicVoice"),("edge","🌐 Edge"),("fast","⚡ MG Nhanh")]:
            _is_sel = self.tts_mode.get() == _mval
            _b = tk.Button(top, text=_mlbl, font=(FN,8,"bold" if _is_sel else "normal"),
                           bg=P["purple"] if _is_sel else P["hover"],
                           fg="white" if _is_sel else P["sub"],
                           relief="flat", cursor="hand2", padx=7, pady=3, bd=0,
                           activebackground="#3b60e0", activeforeground="white",
                           command=lambda m=_mval: self._set_tts_mode(m))
            _b.pack(side="left", padx=(0,3))
            _srt_mode_btns[_mval] = _b
        self._mode_btns_srt = _srt_mode_btns

        # Combobox chon giong - ghi THANG vao bien chia se, khong giu trang
        # thai rieng. Mode MagicVoice cung liet ke danh sach preset da luu
        # (Clone/Design) - chon xong tu dong doi self.sel_idx + dong bo
        # sidebar giong het bam preset o "Cai Dat San".
        tk.Label(top, text="Giọng:", font=(FN,9,"bold"),
                 bg=P["white"], fg=P["label"]).pack(side="left", padx=(10,4))
        self.srt_pick_var = tk.StringVar()
        self.srt_pick_cb = ttk.Combobox(top, textvariable=self.srt_pick_var,
                                         state="readonly", font=(FN,9), width=22)
        def _on_srt_pick(e=None):
            _idx = self.srt_pick_cb.current()
            _m = self.tts_mode.get()
            if _m == "edge" and 0 <= _idx < len(EDGE_VOICES_LIST):
                self.edge_voice_var.set(EDGE_VOICES_LIST[_idx][0])
                self._set_tts_mode("edge")
            elif _m == "fast" and 0 <= _idx < len(FAST_VOICES_LIST):
                self.fast_voice_var.set(FAST_VOICES_LIST[_idx][0])
                self._set_tts_mode("fast")
            else:
                _magic_presets = [i for i, vp in enumerate(self.lib.profiles)
                                   if vp.mode in ("clone", "design")]
                if 0 <= _idx < len(_magic_presets):
                    self.sel_idx = _magic_presets[_idx]
                    self._set_tts_mode("omnivoice")
                    self._update_sidebar()
        self.srt_pick_cb.bind("<<ComboboxSelected>>", _on_srt_pick)
        self.srt_pick_cb.pack(side="left")

        self.srt_voice_info = tk.Label(top, text="")
        self._refresh_srt_voices()

        tk.Frame(inner,bg=P["border"],height=1).pack(fill="x")

        # ── Paned: trái nhập text, phải preview ──
        paned=tk.PanedWindow(inner,orient="horizontal",
                              bg=P["border"],sashwidth=4,
                              sashrelief="flat")
        paned.pack(fill="both",expand=True)

        # LEFT: ô nhập văn bản tự do
        left_pane=tk.Frame(paned,bg=P["white"])
        paned.add(left_pane,minsize=200)

        _srt_lbl_row=tk.Frame(left_pane,bg=P["white"])
        _srt_lbl_row.pack(fill="x",padx=8,pady=(6,2))
        tk.Label(_srt_lbl_row,
                 text="📝 Nhập văn bản hoặc SRT:",
                 font=(FN,9,"bold"),bg=P["white"],fg=P["label"]
                 ).pack(side="left")
        self._srt_prev_btn=tk.Button(_srt_lbl_row,text="🎧 Nghe Thử",
                command=self._preview_srt_input,
                font=(FN,9,"bold"),bg="#f0fdf4",fg="#16a34a",
                relief="flat",cursor="hand2",padx=10,pady=2,
                highlightthickness=1,highlightbackground="#86efac")
        self._srt_prev_btn.pack(side="right")

        # ── Toi uu doc (TTS-friendly) cho SRT ──
        # Chi sua CHU trong tung entry (bo gach noi, tach cau qua dai o lien
        # tu an toan) - KHONG dung/xoa entry, KHONG dam timestamp, nen an
        # toan ve so dong/timing phu de.
        _srt_tf_row = tk.Frame(left_pane, bg=P["white"])
        _srt_tf_row.pack(fill="x", padx=8, pady=(0,4))
        self.srt_tts_friendly_var = tk.BooleanVar(value=True)
        tk.Checkbutton(_srt_tf_row, text="✨ Tối ưu đọc (TTS-friendly)",
                        variable=self.srt_tts_friendly_var,
                        font=(FN,8,"bold"), bg=P["white"], fg=P["label"],
                        activebackground=P["white"], selectcolor=P["sidebar"],
                        cursor="hand2").pack(side="left")
        tk.Label(_srt_tf_row, text="(chỉ sửa chữ trong từng dòng, không đổi timing)",
                 font=(FN,7), bg=P["white"], fg=P["dim"]).pack(side="left", padx=(4,0))

        # FIX v3.67 (tinh nang moi, theo yeu cau anh Bac): checkbox bat/tat
        # xuat file .srt timeline khop audio vua tao (mac dinh TAT).
        _srt_tl_row = tk.Frame(left_pane, bg=P["white"])
        _srt_tl_row.pack(fill="x", padx=8, pady=(0,4))
        tk.Checkbutton(_srt_tl_row, text="📝 Xuất file phụ đề .srt khớp giọng đọc",
                        variable=self.srt_timeline_var,
                        font=(FN,8,"bold"), bg=P["white"], fg=P["label"],
                        activebackground=P["white"], selectcolor=P["sidebar"],
                        cursor="hand2").pack(side="left")
        tk.Label(_srt_tl_row, text="(timeline khớp đúng audio vừa tạo, không dùng SRT gốc)",
                 font=(FN,7), bg=P["white"], fg=P["dim"]).pack(side="left", padx=(4,0))

        txt_frame=tk.Frame(left_pane,bg=P["white"])
        txt_frame.pack(fill="both",expand=True,padx=8,pady=(0,4))
        tsb=tk.Scrollbar(txt_frame); tsb.pack(side="right",fill="y")
        self.srt_editor=tk.Text(txt_frame,wrap="word",
                                 bg=P["sidebar"],fg=P["text"],
                                 insertbackground=P["purple"],
                                 font=(FN,10),relief="flat",
                                 highlightthickness=1,
                                 highlightbackground=P["border"],
                                 highlightcolor=P["purple"],
                                 yscrollcommand=tsb.set,
                                 padx=8,pady=6)
        self.srt_editor.pack(fill="both",expand=True)
        tsb.config(command=self.srt_editor.yview)
        self._ph(self.srt_editor, "Dan van ban / SRT vao day... Moi dong = 1 cau")
        # Auto-clear preview khi paste/nhap kịch bản mới
        def _on_srt_paste(e=None):
            self.after(50, self._clear_srt_preview)
        self.srt_editor.bind("<<Paste>>", _on_srt_paste)
        # Hint label
        tk.Label(left_pane,
                 text="Paste SRT hoac van ban vao day → nhan Tao de doc",
                 font=(FN,8),bg=P["white"],fg=P["dim"]
                 ).pack(anchor="w",padx=8,pady=(0,6))

        # RIGHT: preview bảng
        right_pane=tk.Frame(paned,bg=P["white"])
        paned.add(right_pane,minsize=200)

        tk.Label(right_pane,text="📋 Preview SRT:",
                 font=(FN,9,"bold"),bg=P["white"],fg=P["label"]
                 ).pack(anchor="w",padx=8,pady=(6,2))

        tf=tk.Frame(right_pane,bg=P["white"])
        tf.pack(fill="both",expand=True,padx=8,pady=(0,4))
        vsb=tk.Scrollbar(tf,orient="vertical"); vsb.pack(side="right",fill="y")
        hsb=tk.Scrollbar(tf,orient="horizontal"); hsb.pack(side="bottom",fill="x")
        cols=("no","start","end","text")
        self.srt_tree=ttk.Treeview(tf,columns=cols,show="headings",
                                    yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        for c,w,t in [("no",32,"#"),("start",90,"Bắt đầu"),
                       ("end",90,"Kết thúc"),("text",300,"Nội dung")]:
            self.srt_tree.heading(c,text=t)
            self.srt_tree.column(c,width=w,stretch=(c=="text"))
        self.srt_tree.pack(fill="both",expand=True)
        vsb.config(command=self.srt_tree.yview)
        hsb.config(command=self.srt_tree.xview)

        # Options
        opt=tk.Frame(inner,bg=P["white"],pady=4); opt.pack(fill="x",padx=10)
        tk.Label(opt,text="Khoảng lặng (ms):",font=(FN,9),
                 bg=P["white"],fg=P["label"]).pack(side="left")
        tk.Spinbox(opt,from_=0,to=3000,increment=100,textvariable=self.gap_var,
                   width=6,font=(FN,9),relief="flat",
                   bg=P["sidebar"],fg=P["text"],
                   highlightthickness=1,highlightbackground=P["border"]
                   ).pack(side="left",padx=(4,14),ipady=2)
        self.merge_var=tk.BooleanVar(value=True)
        tk.Checkbutton(opt,text="Ghép thành 1 file",variable=self.merge_var,
                       bg=P["white"],fg=P["label"],font=(FN,9),
                       selectcolor=P["white"],activebackground=P["white"]
                       ).pack(side="left")




    # ─────── Tab: Batch ────────────────────────────────────────────
    def _build_batch_tab(self, p):
        inner=tk.Frame(p,bg=P["white"],
                       highlightthickness=1,highlightbackground=P["border"])
        inner.pack(fill="both",expand=True,padx=14,pady=10)

        # Input dir picker
        idf=tk.LabelFrame(inner,text="  📂 Thư Mục Input (.txt + .srt)  ",
                           font=(FN,9),bg=P["white"],fg=P["purple"],
                           relief="flat",highlightbackground=P["border"],
                           highlightthickness=1)
        idf.pack(fill="x",padx=10,pady=8)
        irow=tk.Frame(idf,bg=P["white"]); irow.pack(fill="x",padx=10,pady=6)
        self.in_dir=tk.StringVar()
        tk.Entry(irow,textvariable=self.in_dir,font=(FN,9),relief="flat",
                 bg=P["sidebar"],fg=P["text"],insertbackground=P["purple"],
                 highlightthickness=1,highlightbackground=P["border"],
                 width=36).pack(side="left",ipady=4,padx=(0,6))
        tk.Button(irow,text="📂 Chọn",command=self._browse_indir,
                  font=(FN,9),bg=P["purple"],fg="white",relief="flat",
                  cursor="hand2",padx=10,pady=4).pack(side="left")
        tk.Button(irow,text="🔄 Quét",command=self._scan_txt,
                  font=(FN,9),bg=P["hover"],fg=P["label"],relief="flat",
                  cursor="hand2",padx=10,pady=4).pack(side="left",padx=(4,0))

        # ── MOI: Gioi thieu naming global (thay cho frame cu trong tab) ──
        hint = tk.Frame(inner, bg=P["white"])
        hint.pack(fill="x", padx=10, pady=(0,4))
        tk.Label(hint,
            text="🏷 Cấu hình tên output (áp dụng cho mọi tab): bấm nút 🏷 trên thanh dưới",
            font=(FN,8,"italic"), bg=P["white"], fg=P["dim"]
        ).pack(anchor="w")

        # ── Toi uu doc (TTS-friendly) - dung CHUNG bien voi tab SRT ──
        # (tab SRT la noi tao bien nay - Batch build sau nen bien da co san)
        _tf_batch_row = tk.Frame(inner, bg=P["white"])
        _tf_batch_row.pack(fill="x", padx=10, pady=(0,4))
        tk.Checkbutton(_tf_batch_row, text="✨ Tối ưu đọc (TTS-friendly)",
                        variable=self.srt_tts_friendly_var,
                        font=(FN,8,"bold"), bg=P["white"], fg=P["label"],
                        activebackground=P["white"], selectcolor=P["sidebar"],
                        cursor="hand2").pack(side="left")
        tk.Label(_tf_batch_row, text="(áp dụng cho .txt trong Hàng Loạt — dùng chung với tab SRT)",
                 font=(FN,7), bg=P["white"], fg=P["dim"]).pack(side="left", padx=(4,0))

        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): them tuy chon "Xuat
        # file phu de .srt khop giong doc" cho tab Hang Loat - dung CHUNG
        # bien self.srt_timeline_var voi tab SRT (giong cach lam voi
        # srt_tts_friendly_var ngay o tren), ap dung cho ca file .txt lan .srt.
        _batch_tl_row = tk.Frame(inner, bg=P["white"])
        _batch_tl_row.pack(fill="x", padx=10, pady=(0,4))
        tk.Checkbutton(_batch_tl_row, text="📝 Xuất file phụ đề .srt khớp giọng đọc",
                        variable=self.srt_timeline_var,
                        font=(FN,8,"bold"), bg=P["white"], fg=P["label"],
                        activebackground=P["white"], selectcolor=P["sidebar"],
                        cursor="hand2").pack(side="left")
        tk.Label(_batch_tl_row, text="(áp dụng cho mọi file trong Hàng Loạt — dùng chung với tab SRT)",
                 font=(FN,7), bg=P["white"], fg=P["dim"]).pack(side="left", padx=(4,0))

        # File list
        tk.Label(inner,text="Danh sách file sẽ xử lý:",font=(FN,9),
                 bg=P["white"],fg=P["label"]).pack(anchor="w",padx=10,pady=(0,2))

        # MOI: PanedWindow chia doi - tren la listbox file, duoi la preview noi dung
        import tkinter.ttk as _ttk
        paned = tk.PanedWindow(inner, orient="vertical", bg=P["white"],
                                sashrelief="flat", sashwidth=6, bd=0)
        paned.pack(fill="both", expand=True, padx=10)

        # ── Frame tren: file list ──
        lf=tk.Frame(paned,bg=P["white"])
        paned.add(lf, minsize=100)
        vsb=tk.Scrollbar(lf); vsb.pack(side="right",fill="y")
        self.batch_lb=tk.Listbox(lf,font=(FN2,9),bg=P["sidebar"],
                                  fg=P["text"],selectbackground=P["sel"],
                                  selectforeground=P["purple"],
                                  relief="flat",highlightthickness=0,
                                  yscrollcommand=vsb.set)
        self.batch_lb.pack(fill="both",expand=True)
        vsb.config(command=self.batch_lb.yview)

        # ── Frame duoi: preview noi dung ──
        pf = tk.Frame(paned, bg=P["white"])
        paned.add(pf, minsize=80)

        _phead = tk.Frame(pf, bg=P["white"]); _phead.pack(fill="x", pady=(4,2))
        tk.Label(_phead, text="📖 Nội dung file (preview):",
                 font=(FN,9), bg=P["white"], fg=P["label"]
                 ).pack(side="left")
        self.batch_preview_info = tk.Label(_phead, text="",
                                            font=(FN,8,"italic"),
                                            bg=P["white"], fg=P["dim"])
        self.batch_preview_info.pack(side="left", padx=(10,0))

        pv_wrap = tk.Frame(pf, bg=P["white"]); pv_wrap.pack(fill="both", expand=True)
        pv_vsb = tk.Scrollbar(pv_wrap); pv_vsb.pack(side="right", fill="y")
        self.batch_preview = tk.Text(pv_wrap, font=(FN2,9),
                                      bg=P["sidebar"], fg=P["text"],
                                      relief="flat", highlightthickness=1,
                                      highlightbackground=P["border"],
                                      wrap="word", state="disabled",
                                      yscrollcommand=pv_vsb.set, height=6)
        self.batch_preview.pack(side="left", fill="both", expand=True)
        pv_vsb.config(command=self.batch_preview.yview)

        # Bind click event de preview
        self.batch_lb.bind("<<ListboxSelect>>", self._batch_on_select)

        foot=tk.Frame(inner,bg=P["white"],pady=4); foot.pack(fill="x",padx=10)
        self.batch_cnt=tk.Label(foot,text="0 file",font=(FN,9),
                                 bg=P["white"],fg=P["dim"])
        self.batch_cnt.pack(side="left")
        for txt,cmd in [("➕ Thêm file",self._add_txt),
                        ("✖ Xóa tất cả",self._clear_batch)]:
            tk.Button(foot,text=txt,command=cmd,font=(FN,9,"bold"),
                      bg=P["purple"],fg="white",relief="flat",
                      activebackground=P["purple2"],activeforeground="white",
                      cursor="hand2",padx=10,pady=4
                      ).pack(side="right",padx=(4,0))
        tk.Button(foot,text="📂 Phiên cũ",
                  command=lambda: self._recall_session(tab_filter="batch"),
                  font=(FN,9),bg=P["gold"],fg="white",relief="flat",
                  cursor="hand2",padx=10,pady=4
                  ).pack(side="right",padx=(4,0))

    # ─────── Tab: Kịch Bản ────────────────────────────────────────
    # ─────── Tab: Kịch Bản ────────────────────────────────────────
    @staticmethod
    def _count_words(t):
        return len(t.strip().split()) if t.strip() else 0

    @staticmethod
    def _split_clauses(text):
        parts, buf = [], ""
        for ch in text:
            buf += ch
            if ch in ".!?…;。！？；":
                if buf.strip(): parts.append(buf.strip())
                buf = ""
        if buf.strip(): parts.append(buf.strip())
        return [p for p in parts if p]

    def _do_split(self, text, min_w, max_w, ovfl, by_clause):
        """
        Chia text thanh cac dong SRT theo min_w/max_w tu.

        by_clause=True (mac dinh):
          - Don vi la CLAUSE (ket thuc bang .!?;) — giu nguyen, khong cat giua clause.
          - Tich luy clause cho den khi cw >= min_w, sau do flush ngay (clause boundary).
          - Moi dong LUON ket thuc bang dau cau (.!?;).
          - Neu clause don le dai hon max_w + ovfl: chap nhan lam 1 dong rieng
            (khong the cat giua cau vi se mat nghia).
          - Dong cuoi co the < min_w neu het noi dung.

        by_clause=False:
          - Don vi la tung TU. Tich luy theo min/max thuan tuy.
          - Sub-split "unit" nao > max_w (truong hop ly thuyet, para.split() luon = 1 tu).
        """
        import re as _re
        paras = [p.strip() for p in _re.split(r"\n\s*\n", text) if p.strip()]

        def _flush(c):
            chunks.append(" ".join(c).strip())
            return [], 0

        chunks = []

        if by_clause:
            # ── CHE DO BY_CLAUSE: don vi la clause nguyen ─────────────────────────
            # Thu thap toan bo clauses
            all_clauses = []
            for para in paras:
                all_clauses.extend(self._split_clauses(para))

            cur, cw = [], 0
            for clause in all_clauses:
                uw = self._count_words(clause)
                if uw == 0:
                    continue

                if cw == 0:
                    # Bat dau chunk moi
                    cur.append(clause); cw += uw
                    # Neu clause duy nhat nay da >= min_w, no san sang flush
                    # (se flush khi gap clause tiep theo)
                elif cw >= min_w:
                    # Da du min_w tu o clause boundary hien tai
                    # → flush, bat dau chunk moi voi clause nay
                    cur, cw = _flush(cur)
                    cur.append(clause); cw += uw
                else:
                    # Chua du min_w: LUON them vao, khong flush som
                    # min_w la rang buoc CUNG — khong bao gio cat doan ngan hon min_w
                    # max_w la rang buoc MEM — co the bi vuot neu can thiet de dat min_w
                    cur.append(clause); cw += uw

        else:
            # ── CHE DO BY_WORD: don vi la tung tu ─────────────────────────────────
            all_words = []
            for para in paras:
                all_words.extend(para.split())

            cur, cw = [], 0
            for word in all_words:
                uw = 1
                if cw == 0:
                    cur.append(word); cw += uw
                elif cw < min_w:
                    cur.append(word); cw += uw
                    # Khong flush khi chua du min_w (tuong tu fix by_clause)
                else:
                    if cw + uw <= max_w + ovfl:
                        cur.append(word); cw += uw
                        if cw >= max_w + ovfl:
                            cur, cw = _flush(cur)
                    else:
                        cur, cw = _flush(cur)
                        cur.append(word); cw = uw

        # B3: xu ly chunk cuoi con lai
        if cur:
            joined = " ".join(cur).strip()
            cw_cur = self._count_words(joined)
            if cw_cur < min_w and chunks:
                # Chunk cuoi qua ngan: thu gop voi chunk truoc
                last = chunks[-1]
                if self._count_words(last) + cw_cur <= max_w + ovfl:
                    chunks[-1] = last + " " + joined
                else:
                    chunks.append(joined)
            else:
                chunks.append(joined)

        return [c for c in chunks if c.strip()]

    @staticmethod
    def _fmt_time(ms):
        h,m,s,cs = ms//3600000,(ms%3600000)//60000,(ms%60000)//1000,ms%1000
        return f"{h:02d}:{m:02d}:{s:02d},{cs:03d}"

    def _make_srt(self, lines, mpc, gap, char_only=False):
        """
        Tinh thoi gian SRT dua tren ki tu (va tu neu char_only=False).
        char_only=True: chi dung n_chars * mpc — dung cho che do Theo Giay
                        de dam bao thoi gian khop voi target da split.
        char_only=False (mac dinh): lay max(char, word, floor) nhu cu.
        """
        srt, t, idx = "", 0, 1
        ms_per_word = max(int(mpc * 5.83), 50)
        floor_ms = max(int(mpc * 13), 200)
        for line in lines:
            if not line.strip(): continue
            n_chars = len(line)
            n_words = len(line.split())
            dur_by_char = n_chars * mpc
            if char_only:
                dur = max(dur_by_char, floor_ms)
            else:
                dur = max(dur_by_char, n_words * ms_per_word, floor_ms)
            srt += f"{idx}\n{self._fmt_time(t)} --> {self._fmt_time(t+dur)}\n{line}\n\n"
            t += dur + gap; idx += 1
        return srt

    def _build_script_tab(self, p):
        inner = tk.Frame(p, bg=P["white"],
                         highlightthickness=1,
                         highlightbackground=P["border"])
        inner.pack(fill="both", expand=True, padx=14, pady=10)

        # ── Toolbar trên ──
        tb = tk.Frame(inner, bg=P["white"], pady=6)
        tb.pack(fill="x", padx=8)

        tk.Label(tb, text="✍  Kịch Bản & SRT",
                 font=(FN,11,"bold"), bg=P["white"],
                 fg=P["purple"]).pack(side="left")
        self.script_stats = tk.StringVar(value="Paste kịch bản → tự động xử lý")
        tk.Label(tb, textvariable=self.script_stats,
                 font=(FN,8), bg=P["white"],
                 fg=P["dim"]).pack(side="left", padx=10)
        tk.Button(tb, text="📂 Mở File",
                  command=self._script_open_file,
                  font=(FN,8), bg=P["hover"],
                  fg=P["label"], relief="flat",
                  cursor="hand2", padx=8, pady=3
                  ).pack(side="right", padx=2)
        tk.Button(tb, text="🗑 Xóa",
                  command=self._script_clear,
                  font=(FN,8), bg=P["hover"],
                  fg=P["label"], relief="flat",
                  cursor="hand2", padx=8, pady=3
                  ).pack(side="right", padx=2)

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Custom char cleaner bar (script tab) ──
        scbar = tk.Frame(inner, bg=P["sidebar"], pady=4)
        scbar.pack(fill="x")
        tk.Label(scbar, text="  Xóa ký tự:",
                 font=(FN,8), bg=P["sidebar"],
                 fg=P["dim"]).pack(side="left")
        QUICK_SC = [
            ("*","*"), ("/","/"), ("#","#"),
            ("---","---"), ('"','"'), ("[]","[]"),
        ]
        for lbl, ch in QUICK_SC:
            tk.Button(scbar, text=lbl,
                      command=lambda c=ch: self._del_char_from_script(c),
                      font=("Consolas",8), bg=P["white"],
                      fg=P["text"], relief="flat",
                      cursor="hand2", padx=6, pady=2,
                      highlightthickness=1,
                      highlightbackground=P["border"]
                      ).pack(side="left", padx=2)
        tk.Label(scbar, text="|  Tùy chỉnh:",
                 font=(FN,8), bg=P["sidebar"],
                 fg=P["dim"]).pack(side="left", padx=(8,2))
        self.script_del_var = tk.StringVar()
        tk.Entry(scbar, textvariable=self.script_del_var,
                 font=("Consolas",9), width=8,
                 bg=P["white"], fg=P["text"],
                 relief="flat",
                 highlightthickness=1,
                 highlightbackground=P["border"]
                 ).pack(side="left", ipady=3)
        tk.Button(scbar, text="Xóa Tất Cả",
                  command=self._del_custom_script_char,
                  font=(FN,8,"bold"), bg=P["red"],
                  fg="white", relief="flat",
                  cursor="hand2", padx=8, pady=3
                  ).pack(side="left", padx=4)
        tk.Button(scbar, text="🔄 Khôi phục",
                  command=self._restore_script,
                  font=(FN,8), bg=P["hover"],
                  fg=P["label"], relief="flat",
                  cursor="hand2", padx=8, pady=3
                  ).pack(side="left", padx=2)

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Settings bar ──
        sbar = tk.Frame(inner, bg=P["sidebar"], pady=5)
        sbar.pack(fill="x", padx=0)

        # Nhịp nghỉ — biến giữ lại để code dùng, không hiển thị UI
        self.script_thresh = tk.IntVar(value=60)
        self.srt_mpc = tk.IntVar(value=60)

        # SRT settings — Gap
        tk.Label(sbar, text="  Gap:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        tk.Spinbox(sbar, from_=0, to=2000, textvariable=self.gap_var,
                   width=5, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(sbar, text="ms  |",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")

        # Che do chia SRT — radio button
        tk.Label(sbar, text="  Chế độ:",
                 font=(FN,8,"bold"), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        self.srt_mode = tk.IntVar(value=0)  # 0=min/max tu, 1=theo giay

        # --- Frame cho che do 0: Min Max tu ---
        self.srt_min_w = tk.IntVar(value=20)
        self.srt_max_w = tk.IntVar(value=30)
        self.srt_by_clause = tk.BooleanVar(value=True)
        self.srt_min_s = tk.IntVar(value=8)
        self.srt_max_s = tk.IntVar(value=10)

        _frm_word = tk.Frame(sbar, bg=P["sidebar"])
        tk.Label(_frm_word, text="Min:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        tk.Spinbox(_frm_word, from_=3, to=30, textvariable=self.srt_min_w,
                   width=3, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(_frm_word, text="Max:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        tk.Spinbox(_frm_word, from_=8, to=50, textvariable=self.srt_max_w,
                   width=3, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(_frm_word, text="từ",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left", padx=(2,6))
        tk.Checkbutton(_frm_word, text="Tách mệnh đề",
                       variable=self.srt_by_clause,
                       font=(FN,8), bg=P["sidebar"], fg=P["label"],
                       activebackground=P["sidebar"],
                       cursor="hand2").pack(side="left")

        # --- Frame cho che do 1: Theo giay ---
        _frm_time = tk.Frame(sbar, bg=P["sidebar"])
        tk.Label(_frm_time, text="Min:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        tk.Spinbox(_frm_time, from_=3, to=60, textvariable=self.srt_min_s,
                   width=3, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(_frm_time, text="Max:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        tk.Spinbox(_frm_time, from_=5, to=60, textvariable=self.srt_max_s,
                   width=3, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(_frm_time, text="giây",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left", padx=2)

        # Toggle hien/an frame khi chon radio
        def _toggle_srt_mode():
            if self.srt_mode.get() == 0:
                _frm_time.pack_forget()
                _frm_word.pack(side="left")
                self.gap_var.set(400)
            else:
                _frm_word.pack_forget()
                _frm_time.pack(side="left")
                self.gap_var.set(400)

        tk.Radiobutton(sbar, text="Min/Max từ",
                       variable=self.srt_mode, value=0,
                       command=_toggle_srt_mode,
                       font=(FN,8), bg=P["sidebar"], fg=P["label"],
                       activebackground=P["sidebar"],
                       cursor="hand2").pack(side="left", padx=(0,2))
        tk.Radiobutton(sbar, text="⏱ Theo giây",
                       variable=self.srt_mode, value=1,
                       command=_toggle_srt_mode,
                       font=(FN,8), bg=P["sidebar"], fg=P["label"],
                       activebackground=P["sidebar"],
                       cursor="hand2").pack(side="left", padx=(0,6))

        # Hien frame mac dinh (che do 0)
        _frm_word.pack(side="left")

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Main area: 3 cột ──
        main = tk.Frame(inner, bg=P["bg"])
        main.pack(fill="both", expand=True)

        # Cột 1: Input
        col1 = tk.Frame(main, bg=P["white"])
        col1.pack(side="left", fill="both", expand=True,
                  padx=(0,2), pady=2)

        tk.Label(col1, text="📝 Kịch bản gốc",
                 font=(FN,9,"bold"), bg=P["white"],
                 fg=P["label"]).pack(anchor="w", padx=6, pady=(4,2))

        self.script_in = tk.Text(col1, font=(FN,10), wrap="word",
                                  bg=P["white"], fg=P["text"],
                                  relief="flat", padx=6, pady=4,
                                  insertbackground=P["purple"],
                                  highlightthickness=0)
        sb1 = ttk.Scrollbar(col1, command=self.script_in.yview)
        self.script_in.configure(yscrollcommand=sb1.set)
        sb1.pack(side="right", fill="y")
        self.script_in.pack(fill="both", expand=True)
        # Khong tu dong xu ly - chi xu ly khi bam nut
        pass

        # Cột 2: Kịch bản đã xử lý — ẩn khỏi layout, giữ widget để code đọc/ghi
        _col2_hidden = tk.Frame(inner)  # không pack → không hiển thị
        self.script_out = tk.Text(_col2_hidden, font=(FN,10), wrap="word",
                                   bg="#f8fffe", fg=P["text"],
                                   relief="flat", padx=6, pady=4,
                                   highlightthickness=0)

        # Cot 3: SRT - hien thi de user thay ket qua khi bam "SRT tu Goc/Nhip"
        col3 = tk.Frame(main, bg=P["white"])
        col3.pack(side="left", fill="both", expand=True, padx=(2,0), pady=2)

        # Header cua cot SRT
        h3 = tk.Frame(col3, bg=P["white"])
        h3.pack(fill="x", padx=6, pady=(4,2))
        tk.Label(h3, text="🎞 Phụ đề SRT",
                 font=(FN,9,"bold"), bg=P["white"],
                 fg="#0369a1").pack(side="left")
        tk.Button(h3, text="📋",
                  command=lambda: self._srt_copy() if hasattr(self,"_srt_copy") else None,
                  font=(FN,8), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=4, pady=1
                  ).pack(side="right")

        self.srt_out = tk.Text(col3, font=("Consolas",8), wrap="word",
                                bg="#0f1117", fg="#a6e3a1",
                                relief="flat", padx=6, pady=4,
                                state="disabled",
                                highlightthickness=0)
        sb3 = ttk.Scrollbar(col3, command=self.srt_out.yview)
        self.srt_out.configure(yscrollcommand=sb3.set)
        sb3.pack(side="right", fill="y")
        self.srt_out.pack(fill="both", expand=True)

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Action bar dưới ──
        abar = tk.Frame(inner, bg=P["white"], pady=6)
        abar.pack(fill="x", padx=8)

        tk.Button(abar, text="🎬 SRT từ Gốc",
                  command=lambda: self._generate_srt(use_original=True),
                  font=(FN,9), bg="#0369a1", fg="white",
                  relief="flat", cursor="hand2", padx=10, pady=5
                  ).pack(side="left", padx=4)

        tk.Button(abar, text="🎬 SRT từ Nhịp",
                  command=lambda: self._generate_srt(use_original=False),
                  font=(FN,9,"bold"), bg="#f59e0b", fg="white",
                  relief="flat", cursor="hand2", padx=10, pady=5
                  ).pack(side="left", padx=4)

        tk.Button(abar, text="🎙 Xử Lý & Đọc Luôn",
                  command=self._script_send_and_read,
                  font=(FN,10,"bold"), bg=P["green"], fg="white",
                  relief="flat", cursor="hand2", padx=14, pady=5,
                  activebackground="#059669"
                  ).pack(side="right", padx=4)

        tk.Button(abar, text="▶ Gửi Văn Bản",
                  command=self._script_send_to_text,
                  font=(FN,9), bg=P["blue"], fg="white",
                  relief="flat", cursor="hand2", padx=10, pady=5
                  ).pack(side="right", padx=4)

        tk.Button(abar, text="🎞 Gửi SRT",
                  command=self._script_send_to_srt,
                  font=(FN,9), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", padx=10, pady=5
                  ).pack(side="right", padx=4)

        # Separator
        tk.Frame(abar, bg=P["border"], width=1).pack(side="left", fill="y", padx=4)

        # Save buttons
        tk.Button(abar, text="💾 Lưu .txt",
                  command=self._save_script_txt,
                  font=(FN,9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=10, pady=5
                  ).pack(side="left", padx=2)

        tk.Button(abar, text="💾 Lưu .srt",
                  command=self._export_srt,
                  font=(FN,9,"bold"), bg=P["gold"], fg="#1a1a1a",
                  relief="flat", cursor="hand2", padx=10, pady=5
                  ).pack(side="left", padx=2)

    def _del_char_from_script(self, char):
        txt = self.script_in.get("1.0", "end-1c")
        if not txt: return
        if not hasattr(self, "_script_backup"):
            self._script_backup = txt
        new_txt = txt.replace(char, "")
        self.script_in.delete("1.0", "end")
        self.script_in.insert("1.0", new_txt)
        n = txt.count(char)
        self._log(f"🗑 Xóa '{char}': {n} chỗ", "info")
        self._process_script()

    def _del_custom_script_char(self):
        char = self.script_del_var.get()
        if not char:
            messagebox.showwarning("Trống", "Nhập ký tự muốn xóa!")
            return
        self._del_char_from_script(char)

    def _restore_script(self):
        if hasattr(self, "_script_backup") and self._script_backup:
            self.script_in.delete("1.0", "end")
            self.script_in.insert("1.0", self._script_backup)
            del self._script_backup
            self._process_script()
            self._log("✅ Đã khôi phục kịch bản gốc", "ok")
        else:
            messagebox.showinfo("Thông báo", "Không có bản sao lưu!")

    def _script_clear(self):
        self.script_in.delete("1.0", "end")
        self.script_out.delete("1.0", "end")
        self.srt_out.config(state="normal")
        self.srt_out.delete("1.0", "end")
        self.srt_out.config(state="disabled")
        self.script_stats.set("Paste kịch bản → tự động xử lý")

    def _auto_process_script(self):
        txt = self.script_in.get("1.0", "end-1c").strip()
        if len(txt) > 20:
            self._process_script(show_warn=False)

    def _process_script(self, show_warn=False):
        """Chi lam sach ky tu la - KHONG them /."""
        import re as _re
        txt = self.script_in.get("1.0", "end-1c").strip()
        if not txt:
            if show_warn:
                messagebox.showwarning("Trống", "Nhập kịch bản vào ô bên trái!")
            return

        # Lam sach ky tu dac biet
        txt = _re.sub(r"^\s*[-=*#~>_]{2,}\s*$", "", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"^#{1,6}\s+", "", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"[*_]{1,3}(.+?)[*_]{1,3}", r"\1", txt)
        txt = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", txt)
        txt = _re.sub(r"^>+\s*", "", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"\s*---+\s*", " ", txt)
        txt = _re.sub(r"\s*===+\s*", " ", txt)
        txt = _re.sub(r"\s*/+\s*", " ", txt)  # Xoa / da co san
        txt = _re.sub(r" {2,}", " ", txt)
        txt = _re.sub(r"\n{3,}", "\n\n", txt).strip()

        # Hien ket qua - giu nguyen, khong them /
        self.script_out.delete("1.0", "end")
        self.script_out.insert("1.0", txt)
        self.script_stats.set(f"{len(txt.split())} từ | nhấn 🎬 để tạo SRT")
        self._generate_srt()

    def _do_split_by_time(self, text, min_s, max_s, mpc):
        """
        Split text thanh SRT lines dua tren thoi gian mong muon (giay).
        - Tinh min_ch / max_ch tu seconds * 1000 / mpc
        - Tich luy tung TU, flush khi:
            + Dang o cuoi cau (.!?;) VA da >= min_ch ky tu → flush chuan
            + Them tu tiep theo se vuot max_ch → flush ep
        - Dam bao moi dong ~ min_s .. max_s giay
        """
        import re as _re
        min_ch = max(20, int(min_s * 1000 / mpc * 0.8))
        max_ch = max(min_ch + 20, int(max_s * 1000 / mpc * 0.8))
        _sent_end = set('.!?;')

        paras = [p.strip() for p in _re.split(r"\n\s*\n", text) if p.strip()]
        words = []
        for para in paras:
            words.extend(para.split())

        chunks, cur, cur_ch = [], [], 0

        for word in words:
            w_ch = len(word)

            if not cur:
                cur.append(word); cur_ch = w_ch
                continue

            # Neu them word nay se qua max → flush truoc
            if cur_ch + 1 + w_ch > max_ch:
                chunks.append(" ".join(cur))
                cur = [word]; cur_ch = w_ch
                continue

            # Neu dang o cuoi cau va da du min → flush
            at_boundary = cur[-1][-1] in _sent_end if cur else False
            if at_boundary and cur_ch >= min_ch:
                chunks.append(" ".join(cur))
                cur = [word]; cur_ch = w_ch
            else:
                cur.append(word); cur_ch += 1 + w_ch

        if cur:
            joined = " ".join(cur)
            # Dong cuoi qua ngan → gop vao dong truoc neu duoc
            if len(joined) < min_ch * 0.5 and chunks:
                merged = chunks[-1] + " " + joined
                if len(merged) <= max_ch * 1.3:
                    chunks[-1] = merged
                else:
                    chunks.append(joined)
            else:
                chunks.append(joined)

        return [c for c in chunks if c.strip()]

    def _generate_srt(self, use_original=False):
        """Tao SRT."""
        try:
            if use_original:
                txt = self.script_in.get("1.0", "end-1c").strip()
                self._log("🎬 Tạo SRT từ bản gốc", "info")
            else:
                txt = self.script_out.get("1.0", "end-1c").strip()
                self._log("🎬 Tạo SRT từ bản đã xử lý", "info")
            if not txt:
                txt = self.script_in.get("1.0", "end-1c").strip()
            if not txt:
                messagebox.showwarning("Trống", "Chưa có nội dung để tạo SRT!")
                return
            mpc = self.srt_mpc.get()
            gap = self.gap_var.get()
            if self.srt_mode.get() == 1:
                lines = self._do_split_by_time(txt,
                                               min_s=self.srt_min_s.get(),
                                               max_s=self.srt_max_s.get(),
                                               mpc=mpc)
                lines = [l for l in lines if l.strip()]
                srt = self._make_srt(lines, mpc, 0, char_only=True)
            else:
                _max_w = self.srt_max_w.get()
                lines = self._do_split(txt,
                                       min_w=self.srt_min_w.get(),
                                       max_w=_max_w,
                                       ovfl=max(4, _max_w // 3),
                                       by_clause=self.srt_by_clause.get())
                lines = [l for l in lines if l.strip()]
                srt = self._make_srt(lines, mpc, gap)
            self.srt_out.config(state="normal")
            self.srt_out.delete("1.0", "end")
            self.srt_out.insert("1.0", srt)
            self.srt_out.config(state="disabled")
            # FIX: dung cung floor logic voi _make_srt (scale theo mpc)
            _floor = max(int(mpc * 13), 200)
            total_ms = sum(max(len(l)*mpc, _floor) + gap for l in lines)
            m, s = total_ms//60000, (total_ms%60000)//1000
            self.script_stats.set(
                f"{len(txt.split())} từ | {len(lines)} dòng SRT | ~{m}p{s:02d}s")
            self._log(f"✅ SRT: {len(lines)} dòng", "ok")
        except Exception as e:
            self._log(f"❌ Lỗi tạo SRT: {e}", "err")
            messagebox.showerror("Lỗi", str(e))

    def _save_script_txt(self):
        """Luu van ban da xu ly nhip ve may."""
        from tkinter import filedialog as _fd
        # Uu tien ban da xu ly, fallback ban goc
        txt = self.script_out.get("1.0", "end-1c").strip()
        if not txt:
            txt = self.script_in.get("1.0", "end-1c").strip()
        if not txt:
            messagebox.showwarning("Trống", "Chưa có nội dung để lưu!")
            return
        path = _fd.asksaveasfilename(
            defaultextension=".txt",
            initialfile="script.txt",
            filetypes=[("Text","*.txt"),("All","*.*")])
        if path:
            open(path,"w",encoding="utf-8").write(txt)
            messagebox.showinfo("✅ Đã lưu", path)

    def _export_srt(self):
        from tkinter import filedialog as _fd
        content = self.srt_out.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showwarning("Trống", "Nhấn 🎬 Tạo SRT trước!"); return
        path = _fd.asksaveasfilename(defaultextension=".srt",
                                     initialfile="subtitle.srt",
                                     filetypes=[("SRT","*.srt"),("All","*.*")])
        if path:
            open(path,"w",encoding="utf-8").write(content)
            messagebox.showinfo("✅ Đã lưu", path)

    def _export_txt_split(self):
        from tkinter import filedialog as _fd
        content = self.script_out.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showwarning("Trống", "Chưa có nội dung!"); return
        path = _fd.asksaveasfilename(defaultextension=".txt",
                                     initialfile="script.txt",
                                     filetypes=[("Text","*.txt"),("All","*.*")])
        if path:
            open(path,"w",encoding="utf-8").write(content)
            messagebox.showinfo("✅ Đã lưu", path)

    def _script_open_file(self):
        from tkinter import filedialog as _fd
        path = _fd.askopenfilename(
            title="Chọn file kịch bản",
            filetypes=[("Text","*.txt"),("All","*.*")])
        if path:
            try:
                content = open(path,"r",encoding="utf-8",errors="ignore").read()
                self.script_in.delete("1.0","end")
                self.script_in.insert("1.0", content)
                self._process_script()
            except Exception as e:
                messagebox.showerror("Lỗi", str(e))

    def _script_copy(self):
        txt = self.script_out.get("1.0","end-1c")
        if txt:
            self.clipboard_clear(); self.clipboard_append(txt)
            messagebox.showinfo("OK","Đã copy!")

    def _script_send_to_text(self):
        txt = self.script_out.get("1.0","end-1c").strip()
        if not txt: txt = self.script_in.get("1.0","end-1c").strip()
        if not txt: return
        self.txt_in.delete("1.0","end")
        self.txt_in.insert("1.0", txt)
        self._switch_tab("text")

    def _script_send_to_srt(self):
        srt = self.srt_out.get("1.0","end-1c").strip()
        if not srt:
            messagebox.showwarning("Trống","Nhấn 🎬 Tạo SRT trước!"); return
        if hasattr(self,"srt_editor"):
            self.srt_editor.delete("1.0","end")
            self.srt_editor.insert("1.0", srt)
        self._switch_tab("srt")

    # ─────── Tab: Ghép Video ─────────────────────────────────────────
    def _build_ghep_tab(self, p):
        if not HAS_GHEP:
            tk.Label(p, text="⚠  Không tìm thấy ghep_video_core.py\nVui lòng đặt file này cùng thư mục với magicvoice.py.",
                     bg=P["bg"], fg=P["red"], font=(FN, 11), justify="center").pack(expand=True)
            return

        root_fr = tk.Frame(p, bg=P["bg"])
        root_fr.pack(fill="both", expand=True)

        # ── Header ──
        hdr = tk.Frame(root_fr, bg=P["purple"], pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎬  GHÉP VIDEO KHỚP VOICE", bg=P["purple"], fg="white",
                 font=(FN, 14, "bold")).pack(anchor="w", padx=20)
        tk.Label(hdr, text="Tự động co giãn mỗi video cho khớp đúng độ dài đoạn voice",
                 bg=P["purple"], fg="#c7d2fe", font=(FN, 9)).pack(anchor="w", padx=20)

        body = tk.Frame(root_fr, bg=P["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=12)

        # ── Folder selectors ──
        card = tk.Frame(body, bg=P["white"], highlightthickness=1,
                        highlightbackground=P["border"])
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)

        self._ghep_voice_var  = tk.StringVar()
        self._ghep_video_var  = tk.StringVar()
        self._ghep_out_var    = tk.StringVar()

        def _row(parent, r, label, var):
            tk.Label(parent, text=label, bg=P["white"], fg=P["label"],
                     font=(FN, 10)).grid(row=r, column=0, sticky="w", padx=14, pady=8)
            tk.Entry(parent, textvariable=var, bg=P["sel"], fg=P["text"],
                     relief="flat", font=(FN, 10),
                     highlightbackground=P["border"], highlightthickness=1
                     ).grid(row=r, column=1, sticky="ew", pady=8, ipady=4)
            tk.Button(parent, text="Chọn…", font=(FN, 9), bg=P["purple"], fg="white",
                      relief="flat", cursor="hand2", padx=12, pady=4,
                      command=lambda v=var: self._ghep_pick_dir(v)
                      ).grid(row=r, column=2, padx=12, pady=8)

        _row(card, 0, "📁  Thư mục VOICE",      self._ghep_voice_var)
        _row(card, 1, "🎞️  Thư mục VIDEO / ẢNH", self._ghep_video_var)

        # Output row — ẩn khi CapCut mode ON
        self._ghep_out_card = tk.Frame(body, bg=P["white"], highlightthickness=1,
                                        highlightbackground=P["border"])
        self._ghep_out_card.pack(fill="x", pady=(4, 0))
        self._ghep_out_card.columnconfigure(1, weight=1)
        _row(self._ghep_out_card, 0, "💾  Lưu KẾT QUẢ", self._ghep_out_var)

        # ── Resolution + options ──
        opt_fr = tk.Frame(body, bg=P["white"], highlightthickness=1,
                          highlightbackground=P["border"])
        opt_fr.pack(fill="x", pady=(8, 0))

        tk.Label(opt_fr, text="🖼️  Khung hình", bg=P["white"], fg=P["label"],
                 font=(FN, 10)).grid(row=0, column=0, sticky="w", padx=14, pady=8)
        self._ghep_res_var = tk.StringVar(value=list(_ghep.RESOLUTIONS.keys())[0])
        ttk.Combobox(opt_fr, textvariable=self._ghep_res_var,
                     values=list(_ghep.RESOLUTIONS.keys()), state="readonly", width=32
                     ).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=8)
        opt_fr.columnconfigure(1, weight=1)

        chk_fr = tk.Frame(opt_fr, bg=P["white"])
        chk_fr.grid(row=1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 10))

        self._ghep_concat_var = tk.BooleanVar(value=True)
        self._ghep_fade_var   = tk.BooleanVar(value=True)
        self._ghep_kb_var     = tk.BooleanVar(value=True)
        self._ghep_trans_var  = tk.BooleanVar(value=False)
        self._ghep_limit_var  = tk.BooleanVar(value=False)

        def _chk(parent, text, var):
            return tk.Checkbutton(parent, text=text, variable=var,
                                  bg=P["white"], fg=P["text"], selectcolor=P["sel"],
                                  font=(FN, 10), activebackground=P["white"],
                                  activeforeground=P["text"], cursor="hand2",
                                  highlightthickness=0, bd=0)

        self._ghep_concat_chk = _chk(chk_fr, "Chỉ xuất 1 video final (nối tất cả, xóa clip lẻ)", self._ghep_concat_var)
        self._ghep_concat_chk.pack(anchor="w", pady=1)
        _chk(chk_fr, "Chuyển cảnh mượt (mờ dần giữa các cảnh)",                          self._ghep_fade_var).pack(anchor="w", pady=1)
        _chk(chk_fr, "Chuyển động ngẫu nhiên cho ẢNH (zoom/pan/chéo — không áp dụng cho video)", self._ghep_kb_var).pack(anchor="w", pady=1)
        _chk(chk_fr, "Chuyển tiếp ngẫu nhiên giữa các cảnh (xfade — chỉ khi xuất final)", self._ghep_trans_var).pack(anchor="w", pady=1)
        _chk(chk_fr, "Giới hạn tốc độ (tránh nhanh/chậm quá mức)",                      self._ghep_limit_var).pack(anchor="w", pady=1)

        # ── Tên file output ──
        self._ghep_name_fr = name_fr = tk.Frame(body, bg=P["white"], highlightthickness=1,
                                                  highlightbackground=P["border"])
        name_fr.pack(fill="x", pady=(8, 0))
        name_fr.columnconfigure(1, weight=1)
        self._ghep_name_lbl = tk.Label(name_fr, text="📝  Tên file output",
                                        bg=P["white"], fg=P["label"], font=(FN, 10))
        self._ghep_name_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=8)
        self._ghep_name_var = tk.StringVar(value="final")
        tk.Entry(name_fr, textvariable=self._ghep_name_var, bg=P["sel"], fg=P["text"],
                 relief="flat", font=(FN, 10),
                 highlightbackground=P["border"], highlightthickness=1
                 ).grid(row=0, column=1, sticky="ew", pady=8, ipady=4)
        self._ghep_name_ext = tk.Label(name_fr, text=".mp4", bg=P["white"],
                                        fg=P["sub"], font=(FN, 10))
        self._ghep_name_ext.grid(row=0, column=2, padx=(4, 14))

        # ── Gửi vào CapCut ──
        self._ghep_autocap_var = tk.BooleanVar(value=False)
        self._ghep_autocap_var.trace_add("write", self._ghep_toggle_mode)

        ac_wrap = tk.Frame(body, bg=P["white"], highlightthickness=1,
                           highlightbackground=P["border"])
        ac_wrap.pack(fill="x", pady=(6, 0))

        # Header row: checkbox bật/tắt
        ac_hdr = tk.Frame(ac_wrap, bg=P["white"])
        ac_hdr.pack(fill="x", padx=14, pady=(8, 2))
        _chk(ac_hdr, "Gửi vào CapCut (đẩy ảnh+voice trực tiếp vào project)", self._ghep_autocap_var
             ).pack(side="left")

        # Draft folder row
        ac_row1 = tk.Frame(ac_wrap, bg=P["white"])
        ac_row1.pack(fill="x", padx=14, pady=2)
        tk.Label(ac_row1, text="Thư mục CapCut Draft:", bg=P["white"], fg=P["label"],
                 font=(FN, 9), width=22, anchor="w").pack(side="left")
        self._ghep_draft_var = tk.StringVar()
        tk.Entry(ac_row1, textvariable=self._ghep_draft_var,
                 bg=P["sel"], fg=P["text"], relief="flat", font=(FN2, 9),
                 highlightbackground=P["border"], highlightthickness=1
                 ).pack(side="left", fill="x", expand=True, ipady=3, padx=(4, 4))
        tk.Button(ac_row1, text="📂", font=(FN, 9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=8, pady=2,
                  command=lambda: (lambda d=filedialog.askdirectory():
                                   (self._ghep_draft_var.set(d),
                                    self._ghep_reload_projects(manual=True)) if d else None)()
                  ).pack(side="left")
        tk.Button(ac_row1, text="🔍 Tự dò", font=(FN, 9), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", padx=8, pady=2,
                  activebackground=P["sel"], activeforeground=P["purple"],
                  command=self._ghep_redetect_draft
                  ).pack(side="left", padx=(4, 0))

        # Hint path — hiện trạng thái tìm tự động vs thủ công + số project
        self._ghep_draft_hint = tk.Label(ac_wrap, text="", bg=P["white"], fg=P["dim"],
                                          font=(FN, 8), anchor="w")
        self._ghep_draft_hint.pack(fill="x", padx=14)

        # Auto-detect lần đầu (không blocking — chạy sau khi UI xong)
        self.after(100, self._ghep_redetect_draft)

        # Project dropdown row
        ac_row2 = tk.Frame(ac_wrap, bg=P["white"])
        ac_row2.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(ac_row2, text="Project template:", bg=P["white"], fg=P["label"],
                 font=(FN, 9), width=22, anchor="w").pack(side="left")
        self._ghep_proj_var  = tk.StringVar()
        self._ghep_proj_data = []   # [(display, folder_path)]
        self._ghep_proj_cmb  = ttk.Combobox(ac_row2, textvariable=self._ghep_proj_var,
                                              state="readonly", font=(FN, 9), width=34)
        self._ghep_proj_cmb.pack(side="left", padx=(4, 4))
        self._ghep_proj_cmb.bind("<<ComboboxSelected>>", self._ghep_on_proj_select)
        tk.Button(ac_row2, text="🔄 Tải lại", font=(FN, 9), bg=P["blue"], fg="white",
                  relief="flat", cursor="hand2", padx=8, pady=2,
                  command=self._ghep_reload_projects).pack(side="left")

        # Project info
        self._ghep_proj_info = tk.Label(ac_wrap, text="", bg=P["white"], fg=P["purple"],
                                         font=(FN, 8), anchor="w")
        self._ghep_proj_info.pack(fill="x", padx=14, pady=(2, 4))

        # (auto-detect đã được schedule ở trên tại after(100, _ghep_redetect_draft))

        # ── Start/Stop buttons + progress ──
        _ghep_btn_fr = tk.Frame(body, bg=P["white"])
        _ghep_btn_fr.pack(fill="x", pady=(10, 4))
        self._ghep_run_btn = tk.Button(
            _ghep_btn_fr, text="▶  BẮT ĐẦU GHÉP", font=(FN, 11, "bold"),
            bg=P["purple"], fg="white", activebackground=P["purple2"],
            activeforeground="white", relief="flat", cursor="hand2",
            padx=20, pady=10, command=self._ghep_start,
        )
        self._ghep_run_btn.pack(side="left", fill="x", expand=True)
        self._ghep_stop_btn = tk.Button(
            _ghep_btn_fr, text="■  DỪNG", font=(FN, 11, "bold"),
            bg="#c62828", fg="white", activebackground="#b71c1c",
            activeforeground="white", relief="flat", cursor="hand2",
            padx=16, pady=10, command=self._ghep_stop,
        )
        self._ghep_stop_btn.pack(side="right", padx=(6, 0))
        self._ghep_stop_btn.pack_forget()   # ẩn khi chưa chạy

        self._ghep_prog = ttk.Progressbar(body, mode="determinate")
        self._ghep_prog.pack(fill="x", pady=(0, 6))

        tk.Label(body, text="NHẬT KÝ", bg=P["bg"], fg=P["sub"],
                 font=(FN, 9, "bold")).pack(anchor="w")
        self._ghep_log = scrolledtext.ScrolledText(
            body, height=9, font=("Consolas", 9), bg=P["sel"],
            fg=P["text"], relief="flat", bd=0,
            highlightbackground=P["border"], highlightthickness=1,
        )
        self._ghep_log.pack(fill="both", expand=True, pady=(2, 0))
        self._ghep_log_append("Sẵn sàng. Chọn thư mục Voice + Video rồi bấm BẮT ĐẦU GHÉP.")

    def _ghep_toggle_mode(self, *_):
        """Làm mờ/khôi phục các tùy chọn không dùng ở mode hiện tại; đổi label tên field."""
        is_cap = self._ghep_autocap_var.get()
        state  = "disabled" if is_cap else "normal"

        def _set_state(w):
            try:
                w.config(state=state)
            except Exception:
                pass
            for child in w.winfo_children():
                _set_state(child)

        _set_state(self._ghep_out_card)
        self._ghep_concat_chk.config(state=state)

        # Đổi label và ẩn/hiện đuôi .mp4 theo mode
        if is_cap:
            self._ghep_name_lbl.config(text="📝  Tên project mới")
            self._ghep_name_ext.grid_remove()
        else:
            self._ghep_name_lbl.config(text="📝  Tên file output")
            self._ghep_name_ext.grid()

    def _ghep_process_capcut(self, voice_dir, video_dir):
        """Headless: đẩy ảnh+voice vào CapCut project mà không mở GUI."""
        import traceback
        try:
            idx = self._ghep_proj_cmb.current()
            if idx < 0 or idx >= len(self._ghep_proj_data):
                self.after(0, lambda: messagebox.showerror(
                    "Lỗi", "Chọn project template trước!"))
                return
            _, template_path = self._ghep_proj_data[idx]
            draft    = self._ghep_draft_var.get().strip()
            new_name = self._ghep_name_var.get().strip() or "project_moi"

            def _log(msg):
                self._ghep_log_append(msg)
            def _prog(v):
                self.after(0, lambda v=v: self._ghep_set_progress(v))
            def _on_start(total):
                self.after(0, lambda: self._ghep_prog.config(maximum=total, value=0))

            self._ghep_log_append(
                f"Tạo project '{new_name}' từ template: {os.path.basename(template_path)}")
            folder, n, mins, secs = _ghep.push_to_capcut(
                video_dir, voice_dir, template_path, draft,
                new_name, False, _log, _prog, on_start=_on_start,
            )
            msg = (f"✅ Tạo project '{new_name}' thành công!\n"
                   f"{n} cặp ảnh+voice  |  {mins}p {secs}s\n\n"
                   f"Tắt CapCut → Mở lại → Project xuất hiện đầu danh sách ✓")
            self._ghep_log_append(f"✅ Hoàn tất! {n} cặp, {mins}p {secs}s")
            self.after(0, lambda: messagebox.showinfo("Thành công", msg))
        except Exception as e:
            err = str(e)
            self._ghep_log_append(f"❌ Lỗi: {err}\n{traceback.format_exc()}")
            self.after(0, lambda err=err: messagebox.showerror("Lỗi CapCut", err))
        finally:
            self.after(0, lambda: self._ghep_run_btn.config(
                state="normal", text="▶  BẮT ĐẦU GHÉP"))

    def _ghep_launch_capcut(self, voice_dir, video_dir):
        """(Legacy) Mở capcut_clone.py với pre-fill khi CapCut mode."""
        idx = self._ghep_proj_cmb.current()
        project_path = ""
        if 0 <= idx < len(self._ghep_proj_data):
            _, project_path = self._ghep_proj_data[idx]
        draft = self._ghep_draft_var.get().strip()

        self._ghep_log_append(f"Đang mở CapCut Clone Tool...")
        self._ghep_log_append(f"  📁 Ảnh/Video: {video_dir}")
        self._ghep_log_append(f"  🎵 Voice:     {voice_dir}")
        if project_path:
            self._ghep_log_append(f"  🎬 Template:  {os.path.basename(project_path)}")

        ok, info = _ghep.launch_capcut_prefilled(video_dir, voice_dir, draft, project_path)
        if ok:
            self._ghep_log_append("✔  capcut_clone.py đã mở — hãy kiểm tra và bấm Tạo Project.")
        else:
            self._ghep_log_append(f"⚠  Không mở được: {info}")
            self.after(0, lambda: messagebox.showerror("Lỗi", f"Không mở được capcut_clone.py:\n{info}"))

    def _ghep_redetect_draft(self):
        """Chạy lại auto-detect CapCut draft folder — cập nhật ô path + hint."""
        if not HAS_GHEP:
            return
        try:
            self._ghep_draft_hint.config(text="  🔍 Đang tìm thư mục CapCut Draft...", fg=P["dim"])
            self.update_idletasks()
            found = _ghep.detect_capcut_draft()
        except Exception as _e:
            self._ghep_draft_hint.config(text=f"  ❌ Lỗi tìm: {_e}", fg=P["red"])
            return
        if found:
            self._ghep_draft_var.set(found)
            self._ghep_reload_projects(auto_detected=True)
        else:
            self._ghep_draft_hint.config(
                text="  ⚠ Không tìm thấy tự động — hãy bấm 📂 để trỏ thủ công",
                fg=P["gold"])

    def _ghep_reload_projects(self, manual=False, auto_detected=False):
        if not HAS_GHEP:
            return
        draft = self._ghep_draft_var.get().strip()
        projects = _ghep.list_capcut_projects(draft) if draft else []
        self._ghep_proj_data = projects
        names = [d for d, _ in projects]
        self._ghep_proj_cmb.config(values=names)
        if names:
            self._ghep_proj_cmb.current(0)
            self._ghep_on_proj_select()
            _src = "tự động" if auto_detected else ("thủ công" if manual else "")
            _src_txt = f"  [{_src}]" if _src else ""
            _short = draft[:55] + "…" if len(draft) > 55 else draft
            self._ghep_draft_hint.config(
                text=f"  ✅ {_short}{_src_txt}  •  {len(names)} project",
                fg=P["green"])
        else:
            self._ghep_proj_var.set("")
            self._ghep_proj_info.config(text="(Không tìm thấy project — kiểm tra thư mục Draft)")
            if draft:
                _short = draft[:55] + "…" if len(draft) > 55 else draft
                self._ghep_draft_hint.config(
                    text=f"  ⚠ {_short}  •  0 project — thư mục có thể sai",
                    fg=P["gold"])

    def _ghep_on_proj_select(self, _event=None):
        idx = self._ghep_proj_cmb.current()
        if idx < 0 or idx >= len(self._ghep_proj_data):
            self._ghep_proj_info.config(text="")
            return
        display, folder = self._ghep_proj_data[idx]
        self._ghep_proj_info.config(text=f"  📁 {folder}")

    def _ghep_pick_dir(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _ghep_log_append(self, msg):
        def _do():
            self._ghep_log.insert("end", msg + "\n")
            self._ghep_log.see("end")
        self.after(0, _do)

    def _ghep_set_progress(self, done, total=None):
        def _do():
            if total is not None:
                self._ghep_prog["maximum"] = total
            self._ghep_prog["value"] = done
        self.after(0, _do)

    def _ghep_start(self):
        if not HAS_GHEP:
            return
        voice_dir = self._ghep_voice_var.get().strip()
        video_dir = self._ghep_video_var.get().strip()
        if not voice_dir or not video_dir:
            messagebox.showwarning("Thiếu thư mục", "Chọn thư mục Voice và Video trước nhé.")
            return

        self._ghep_run_btn.config(state="disabled", text="⏳  ĐANG XỬ LÝ...")
        self._ghep_stop_btn.pack(side="right", padx=(6, 0))
        self._ghep_log.delete("1.0", "end")
        self._ghep_set_progress(0)
        self._ghep_cancel_ev = threading.Event()

        # CapCut mode: đẩy headless vào CapCut project, không ffmpeg
        if self._ghep_autocap_var.get():
            threading.Thread(
                target=self._ghep_process_capcut,
                args=(voice_dir, video_dir),
                daemon=True,
            ).start()
            return

        # Mode thường: ghép video → lưu file
        out_dir = self._ghep_out_var.get().strip()
        if not out_dir:
            out_dir = os.path.join(os.path.dirname(video_dir) or ".", "output")
            self._ghep_out_var.set(out_dir)
        threading.Thread(target=self._ghep_process,
                         args=(voice_dir, video_dir, out_dir), daemon=False).start()

    def _ghep_stop(self):
        ev = getattr(self, "_ghep_cancel_ev", None)
        if ev:
            ev.set()
        self._ghep_stop_btn.config(state="disabled", text="⏳  Đang dừng...")

    def _ghep_process(self, voice_dir, video_dir, out_dir):
        import traceback
        try:
            if not _ghep.resolve_tools():
                self._ghep_log_append("ffmpeg chưa có → đang tự cài (khoảng 80 MB)...")
                ok = _ghep.install_ffmpeg(self._ghep_log_append, self._ghep_set_progress)
                if not ok:
                    self.after(0, lambda: messagebox.showerror(
                        "Lỗi ffmpeg",
                        "Không tải được ffmpeg tự động.\n"
                        "Kiểm tra mạng hoặc cài thủ công: winget install ffmpeg"))
                    return
                self._ghep_set_progress(0)

            voices = _ghep.list_media(voice_dir, _ghep.VOICE_EXTS)
            videos, _n_vid_rep = _ghep.list_media_video_priority(video_dir)
            if _n_vid_rep:
                self._ghep_log_append(
                    f"🎬 Ưu tiên video: {_n_vid_rep} ảnh bị thay bằng video cùng tên")
            if not voices or not videos:
                self._ghep_log_append(f"Không tìm thấy file. voice={len(voices)}, video={len(videos)}")
                return
            # Bù thiếu media: nếu media ít hơn voice → lặp lại media cuối để ghép đủ
            if len(videos) < len(voices):
                _n_pad = len(voices) - len(videos)
                self._ghep_log_append(
                    f"⚠ Thiếu {_n_pad} media → bù bằng: {os.path.basename(videos[-1])}")
                videos = list(videos) + [videos[-1]] * _n_pad
            n = min(len(voices), len(videos))
            if len(videos) > len(voices):
                self._ghep_log_append(f"⚠  Thừa media: {len(videos)} media / {len(voices)} voice. Xử lý {n} cặp đầu.")

            w, h        = _ghep.RESOLUTIONS[self._ghep_res_var.get()]
            limit       = self._ghep_limit_var.get()
            fade        = self._ghep_fade_var.get()
            kenburns    = self._ghep_kb_var.get()
            trans       = self._ghep_trans_var.get()
            only_final  = self._ghep_concat_var.get()
            final_name  = (self._ghep_name_var.get().strip() or "final")

            os.makedirs(out_dir, exist_ok=True)
            self._ghep_log_append(f"Bắt đầu xử lý {n} cặp...\n" + "─" * 52)

            final_path, n_loi = _ghep.process_pairs(
                voices, videos, out_dir,
                w, h, limit, fade, kenburns, only_final,
                self._ghep_log_append, self._ghep_set_progress,
                final_name=final_name, transitions=trans,
                cancel_ev=getattr(self, "_ghep_cancel_ev", None),
            )

            self._ghep_log_append("─" * 52)
            if n_loi:
                self._ghep_log_append(f"⚠  Có {n_loi} cặp lỗi đã bỏ qua.")
            if final_path:
                dur = _ghep.get_duration(final_path)
                self._ghep_log_append(f"✔  Video hoàn chỉnh ({dur:.2f}s):\n   {final_path}")
            elif not only_final:
                self._ghep_log_append(f"✔  Clip lẻ đã lưu vào:\n   {out_dir}")
            else:
                self._ghep_log_append("[LỖI] Không có clip nào hợp lệ.")
                self.after(0, lambda: messagebox.showerror(
                    "Lỗi", "Tất cả cặp đều lỗi. Kiểm tra lại file voice/video."))
                return
            self._ghep_log_append("\n═══  HOÀN TẤT  ═══")
            self.after(0, lambda: messagebox.showinfo("Xong", "Đã ghép xong!"))
        except Exception as e:
            self._ghep_log_append(f"\n[LỖI] {e}")
            tb = traceback.format_exc()
            self._ghep_log_append(tb[-600:])
            self.after(0, lambda err=str(e): messagebox.showerror("Lỗi", err))
        finally:
            def _reset_ghep_btn():
                self._ghep_run_btn.config(state="normal", text="▶  BẮT ĐẦU GHÉP")
                self._ghep_stop_btn.pack_forget()
                self._ghep_stop_btn.config(state="normal", text="■  DỪNG")
            self.after(0, _reset_ghep_btn)

    def _script_send_and_read(self):
        txt = self.script_out.get("1.0","end-1c").strip()
        srt = self.srt_out.get("1.0","end-1c").strip()
        if not txt:
            self._process_script(show_warn=True)
            txt = self.script_out.get("1.0","end-1c").strip()
            srt = self.srt_out.get("1.0","end-1c").strip()
        if not txt: return

        dlg = tk.Toplevel(self)
        dlg.title("Chọn chế độ đọc")
        dlg.geometry("380x180")
        dlg.configure(bg=P["white"])
        dlg.resizable(False,False)
        dlg.grab_set(); dlg.lift()
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth()-380)//2
        y = (dlg.winfo_screenheight()-180)//2
        dlg.geometry(f"380x180+{x}+{y}")

        tk.Label(dlg, text="Chọn chế độ đọc voice:",
                 font=(FN,11,"bold"), bg=P["white"],
                 fg=P["text"], pady=12).pack()
        row = tk.Frame(dlg, bg=P["white"]); row.pack()

        def go_text():
            dlg.destroy()
            self.txt_in.delete("1.0","end")
            self.txt_in.insert("1.0", txt)
            self._switch_tab("text")
            self._do_text()

        def go_srt():
            dlg.destroy()
            if not srt:
                messagebox.showwarning("Trống","Nhấn 🎬 Tạo SRT trước!"); return
            self._script_send_to_srt()
            self.after(200, self._do_srt)

        tk.Button(row, text="📄 Văn Bản",
                  command=go_text, font=(FN,10), bg=P["hover"],
                  fg=P["text"], relief="flat", cursor="hand2",
                  padx=20, pady=10).pack(side="left", padx=8)
        tk.Button(row, text="🎬 Phụ Đề SRT",
                  command=go_srt, font=(FN,10,"bold"), bg=P["purple"],
                  fg="white", relief="flat", cursor="hand2",
                  padx=20, pady=10).pack(side="left", padx=8)
        tk.Button(dlg, text="Hủy", command=dlg.destroy,
                  font=(FN,9), bg=P["hover"], fg=P["dim"],
                  relief="flat", cursor="hand2").pack(pady=8)

    # ─────── Tab: Clone Voice ──────────────────────────────────────
    def _build_clone_tab(self, p):
        inner=tk.Frame(p,bg=P["bg"])
        inner.pack(fill="both",expand=True,padx=14,pady=10)

        # Header (full width)
        hdr=tk.Frame(inner,bg=P["bg"]); hdr.pack(fill="x",pady=(0,10))
        tk.Label(hdr,text="🎤  Thư Viện Voice Clone",
                 font=(FN,13,"bold"),bg=P["bg"],fg=P["text"]).pack(side="left")
        tk.Button(hdr,text="🎙 Duyệt Giọng",command=self._browse_voices,
                  font=(FN,9,"bold"),bg=P["blue"],fg="white",
                  relief="flat",cursor="hand2",padx=12,pady=5
                  ).pack(side="right",padx=(0,4))
        tk.Button(hdr,text="＋  Thêm Voice Mới",command=self._add_voice,
                  font=(FN,9,"bold"),bg=P["purple"],fg="white",
                  relief="flat",cursor="hand2",padx=12,pady=5
                  ).pack(side="right")

        # Main horizontal split: LEFT (voice list) + RIGHT (guide)
        main=tk.Frame(inner,bg=P["bg"])
        main.pack(fill="both",expand=True)

        # LEFT — voice list panel (fixed 360px wide)
        left=tk.Frame(main,bg=P["bg"],width=360)
        left.pack(side="left",fill="y")
        left.pack_propagate(False)

        # Separator
        tk.Frame(main,bg=P["border"],width=1).pack(side="left",fill="y",padx=(0,10))

        # RIGHT — guide panel (fills remaining space)
        right=tk.Frame(main,bg=P["bg"])
        right.pack(side="left",fill="both",expand=True)
        self._build_clone_guide(right)

        # Search (inside left)
        sf=tk.Frame(left,bg=P["bg"],
                    highlightthickness=1,highlightbackground=P["border"])
        sf.pack(fill="x",pady=(0,8))
        tk.Label(sf,text="🔍",bg=P["white"],fg=P["dim"],font=(FN,11),padx=6).pack(side="left")
        self.search_var=tk.StringVar()
        self.search_var.trace_add("write",lambda *_:self._refresh_voices())
        tk.Entry(sf,textvariable=self.search_var,font=(FN,10),
                 bg=P["white"],fg=P["text"],relief="flat",
                 insertbackground=P["purple"],
                 highlightthickness=0).pack(side="left",fill="x",expand=True,ipady=6)

        # Voice cards grid (inside left)
        self.voice_scroll_frame=tk.Frame(left,bg=P["bg"])
        self.voice_scroll_frame.pack(fill="both",expand=True)

        canvas=tk.Canvas(self.voice_scroll_frame,bg=P["bg"],highlightthickness=0)
        vsb=tk.Scrollbar(self.voice_scroll_frame,orient="vertical",command=canvas.yview)
        vsb.pack(side="right",fill="y")
        canvas.pack(side="left",fill="both",expand=True)
        canvas.configure(yscrollcommand=vsb.set)
        self.voices_inner=tk.Frame(canvas,bg=P["bg"])
        self._voices_canvas=canvas
        canvas.create_window((0,0),window=self.voices_inner,anchor="nw")
        self.voices_inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Bottom action bar (inside left)
        act=tk.Frame(left,bg=P["bg"],pady=4)
        act.pack(fill="x")
        for txt,cmd in [("✏️ Sửa",self._edit_voice),
                        ("🗑 Xóa",self._del_voice)]:
            tk.Button(act,text=txt,command=cmd,font=(FN,9),
                      bg=P["hover"],fg=P["label"],relief="flat",
                      cursor="hand2",padx=10,pady=4
                      ).pack(side="left",padx=(0,4))

        self._refresh_voices()

    def _voice_card(self, parent, vp: VoiceProfile, idx: int):
        sel=idx==self.sel_idx
        bg=P["sel"] if sel else P["white"]
        bd=P["purple"] if sel else P["border"]

        card=tk.Frame(parent,bg=bg,cursor="hand2",
                      highlightthickness=2 if sel else 1,
                      highlightbackground=bd)
        card.pack(fill="x",pady=3,padx=2)

        # Left color bar
        bar=tk.Frame(card,bg=P["purple"] if sel else P["border2"],width=4)
        bar.pack(side="left",fill="y")

        body=tk.Frame(card,bg=bg); body.pack(side="left",fill="x",expand=True,padx=10,pady=8)

        # Top row
        top=tk.Frame(body,bg=bg); top.pack(fill="x")
        mode_color={"clone":P["purple"],"design":P["blue"]}
        mode_icon={"clone":"🎯","design":"✨"}
        tk.Label(top,text=mode_icon.get(vp.mode,"●"),font=("",14),
                 bg=bg).pack(side="left",padx=(0,6))
        tk.Label(top,text=vp.name,font=(FN,11,"bold"),
                 bg=bg,fg=P["text"]).pack(side="left")

        badge=tk.Label(top,text=f" {vp.mode.upper()} ",font=(FN,7,"bold"),
                       bg=mode_color.get(vp.mode,P["dim"]),fg="white",padx=4,pady=1)
        badge.pack(side="left",padx=(6,0))

        if sel:
            tk.Label(top,text="✓ Đang dùng",font=(FN,8),
                     bg=bg,fg=P["green"]).pack(side="right",padx=4)

        # Details
        details=[]
        if vp.mode=="clone" and vp.ref_audio:
            details.append(f"📎 {Path(vp.ref_audio).name}")
        elif vp.mode=="design" and vp.instruct:
            details.append(f"🎨 {vp.instruct[:50]}")
        if vp.note: details.append(f"📝 {vp.note}")
        if vp.created: details.append(f"🕐 {vp.created}")
        detail_str=" · ".join(details) if details else "Không có mô tả"
        tk.Label(body,text=detail_str,font=(FN,8),bg=bg,fg=P["sub"],
                 anchor="w",wraplength=500).pack(fill="x",pady=(2,0))

        # Params
        params=tk.Frame(body,bg=bg); params.pack(fill="x",pady=(4,0))
        for lbl,val in [("Tốc độ",f"{vp.speed:.1f}×"),
                        ("Âm lượng",f"{vp.volume:.1f}"),
                        ("Cao độ",f"{vp.pitch:.1f}")]:
            chip=tk.Frame(params,bg=P["hover"],padx=6,pady=2)
            chip.pack(side="left",padx=(0,4))
            tk.Label(chip,text=f"{lbl}: {val}",font=(FN,8),
                     bg=P["hover"],fg=P["label"]).pack()

        # Click to select
        def select(e,i=idx):
            self.sel_idx=i
            # Chuyen mode dung theo loai voice
            _vp = self.lib.profiles[i]
            if _vp.mode=="edge" and _vp.instruct.startswith("edge:"):
                _code = _vp.instruct.replace("edge:","").strip()
                if hasattr(self,"edge_voice_var"):
                    self.edge_voice_var.set(_code)
                self._set_tts_mode("edge")
            else:
                self._set_tts_mode("omnivoice")
            self._refresh_voices()
            self._update_sidebar()
        for w in [card,body,bar]+list(body.winfo_children()):
            w.bind("<Button-1>",select)
        card.bind("<Double-Button-1>",lambda e,i=idx:self._edit_voice())

    def _refresh_voices(self):
        for w in self.voices_inner.winfo_children(): w.destroy()
        q=self.search_var.get().lower() if hasattr(self,"search_var") else ""
        for i,vp in enumerate(self.lib.profiles):
            if q and q not in vp.name.lower() and q not in vp.note.lower(): continue
            self._voice_card(self.voices_inner, vp, i)
        if not self.lib.profiles:
            tk.Label(self.voices_inner,text="Chưa có voice nào\nNhấn '+ Thêm Voice Mới' để bắt đầu",
                     font=(FN,10),bg=P["bg"],fg=P["dim"],justify="center").pack(pady=40)

    def _build_clone_guide(self, parent):
        """Huong dan - hien thi ben phai danh sach voice (panel doc lap)."""
        guide=tk.Frame(parent,bg="#eef2ff",
                       highlightthickness=1,highlightbackground="#c7d2fe")
        guide.pack(fill="both",expand=True)

        # Wrapper canh giua theo chieu doc
        wrap=tk.Frame(guide,bg="#eef2ff")
        wrap.pack(expand=True)

        # Arrow + header
        hdr=tk.Frame(wrap,bg="#eef2ff")
        hdr.pack(pady=(24,8))
        tk.Label(hdr,text="↑",font=(FN,20,"bold"),
                 bg="#eef2ff",fg=P["purple"]).pack(side="left",padx=(0,8))
        tk.Label(hdr,text='Nhấn  "+ Thêm Voice Mới"  để thêm giọng clone',
                 font=(FN,10,"bold"),bg="#eef2ff",fg=P["purple"]).pack(side="left")

        tk.Frame(wrap,bg="#c7d2fe",height=1).pack(fill="x",padx=16,pady=(0,10))

        tk.Label(wrap,
                 text="📋  Cách chuẩn bị file audio để clone giọng tốt nhất:",
                 font=(FN,9,"bold"),bg="#eef2ff",fg=P["text"],
                 anchor="w").pack(fill="x",padx=16,pady=(0,6))

        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): them dong canh bao MAU
        # DO, TO, noi bat - khach thuong lam theo thoi quen KHONG doc huong
        # dan ben duoi, hay dua nguyen ca doan dai vuot qua 30s vao lam file
        # mau clone gay loi. Dat NGAY DUOI tieu de, truoc khi vao 5 buoc, de
        # dap vao mat truoc tien.
        tk.Label(wrap,
                 text="⚠️  BẮT BUỘC: File audio mẫu chỉ ĐÚNG 10–30 GIÂY —"
                      " tuyệt đối KHÔNG đưa cả đoạn dài vào, dễ gây lỗi!",
                 font=(FN,10,"bold"),bg="#eef2ff",fg="#dc2626",
                 anchor="w",justify="left",wraplength=420
                 ).pack(fill="x",padx=16,pady=(0,10))

        steps=[
            ("1","Lấy đoạn video/audio chứa giọng cần clone"),
            ("2","Đưa vào CapCut → bỏ phần đầu lộn xộn, chỉ giữ 10–30 giây rõ nhất"),
            ("3",'Tách giọng nói: chuột phải clip → "Tách giọng nói" → chọn "Giữ lời"'
                 ' → lọc sạch nhạc nền và tạp âm'),
            ("4","Cắt đầu / cuối tại điểm lặng — tránh bắt đầu hoặc kết thúc đột ngột"),
            ("5","Xuất WAV hoặc MP3 → chọn làm File audio mẫu khi nhấn Thêm Voice Mới"),
        ]

        body=tk.Frame(wrap,bg="#eef2ff")
        body.pack(fill="x",padx=16,pady=(0,24))

        for num,text in steps:
            row=tk.Frame(body,bg="#eef2ff")
            row.pack(fill="x",pady=3)
            tk.Label(row,text=num,font=(FN,9,"bold"),
                     bg=P["purple"],fg="white",
                     width=2,pady=3).pack(side="left",padx=(0,10))
            tk.Label(row,text=text,font=(FN,9),
                     bg="#eef2ff",fg=P["text"],
                     anchor="w",justify="left",wraplength=400
                     ).pack(side="left",fill="x",expand=True)

    def _browse_voices(self):
        """Mở dialog duyệt 600+ giọng Voice Design + giọng thật Edge TTS"""
        def on_select(result):
            # FIX v3.65 (5): danh muc Edge TTS tra ve dict (khac voi string
            # instruct cua Voice Design) - luu truc tiep VoiceProfile mode=
            # "edge" giong het _save_edge_preset(), khong qua VoiceDialog vi
            # Edge khong co khai niem "instruct" tu do.
            if isinstance(result, dict) and result.get("mode") == "edge":
                from tkinter import simpledialog as _sd
                lang = result.get("lang", "")
                default_name = f"{result['name']} ({lang.split()[-1] if lang else ''})"
                new_name = _sd.askstring("Đặt tên giọng",
                    "Tên hiển thị cho giọng này:",
                    initialvalue=default_name, parent=self)
                if not new_name:
                    return
                import time as _time
                vp = VoiceProfile(
                    name=new_name,
                    mode="edge",
                    ref_audio=result["code"],
                    ref_text=result.get("desc", ""),
                    instruct=f"edge:{result['code']}",
                    speed=result.get("speed", 1.0),
                    volume=result.get("volume", 1.0),
                    pitch=result.get("pitch", 1.0),
                    note=f"{result.get('gender','')} · {result.get('desc','')}",
                    created=_time.strftime("%Y-%m-%d %H:%M"),
                )
                self.lib.add(vp)
                self.sel_idx = len(self.lib.profiles) - 1
                self._refresh_voices()
                self._update_sidebar()
                self._refresh_srt_voices()
                self._log(f"✅ Thêm voice Edge: {vp.name}", "ok")
                return

            instruct = result
            """Mo VoiceDialog de dat ten va luu voice."""
            vdlg = VoiceDialog(self)
            vdlg.mode_var.set("design")
            vdlg._set_mode("design")
            vdlg.instruct_var.set(instruct)
            # Goi y ten
            for label, val in [("female","Giong Nu"),("male","Giong Nam"),
                                ("british","British"),("american","American"),
                                ("young","Tre Trung"),("elderly","Cao Tuoi"),
                                ("child","Tre Em")]:
                if label in instruct.lower():
                    vdlg.name_var.set(val); break
            self.wait_window(vdlg)
            if vdlg.result:
                self.lib.add(vdlg.result)
                self.sel_idx = len(self.lib.profiles)-1
                self._refresh_voices()
                self._update_sidebar()
                self._log(f"✅ Them voice: {vdlg.result.name}","ok")

        dlg = VoiceBrowserDialog(self, on_select=on_select)
        dlg.transient(self)
        dlg.lift()
        dlg.focus_set()
        self.wait_window(dlg)

    def _add_voice(self):
        dlg=VoiceDialog(self); self.wait_window(dlg)
        if dlg.result:
            self.lib.add(dlg.result)
            self.sel_idx=len(self.lib.profiles)-1
            self._refresh_voices(); self._update_sidebar()
            self._log(f"✅ Thêm voice: {dlg.result.name}","ok")

    def _edit_voice(self):
        if self.sel_idx>=len(self.lib.profiles): return
        dlg=VoiceDialog(self,self.lib.profiles[self.sel_idx])
        self.wait_window(dlg)
        if dlg.result:
            self.lib.update(self.sel_idx,dlg.result)
            self._refresh_voices(); self._update_sidebar()
            self._log(f"✅ Cập nhật: {dlg.result.name}","ok")

    def _del_voice(self):
        if self.sel_idx>=len(self.lib.profiles): return
        name=self.lib.profiles[self.sel_idx].name
        if messagebox.askyesno("Xóa voice",f"Xóa '{name}'?"):
            self.lib.remove(self.sel_idx)
            self.sel_idx=max(0,self.sel_idx-1)
            self._refresh_voices(); self._update_sidebar()

    # ─────── RIGHT SIDEBAR ─────────────────────────────────────────
    def _build_sidebar(self, parent):
        # ── Section: Chế độ TTS ──
        self._sb_section(parent,"Chế độ TTS")
        self.tts_mode=tk.StringVar(value="omnivoice")
        m_row=tk.Frame(parent,bg=P["white"]); m_row.pack(fill="x",padx=12,pady=(0,6))
        self._mode_btns_sb={}
        for val,lbl in [("omnivoice","MagicVoice"),("edge","Edge TTS"),("fast","MG Nhanh")]:
            is_sel = val == "omnivoice"
            b=tk.Button(m_row,text=lbl,command=lambda v=val:self._set_tts_mode(v),
                        font=(FN,9,"bold" if is_sel else "normal"),
                        relief="flat",cursor="hand2",padx=16,pady=7,
                        bg=P["purple"] if is_sel else P["bg"],
                        fg="white" if is_sel else P["sub"],
                        bd=0, highlightthickness=0,
                        activebackground="#3b60e0",activeforeground="white")
            b.pack(side="left",padx=(0,3))
            self._mode_btns_sb[val]=b

        # Edge TTS voice dropdown — hiện ngay dưới mode buttons
        # FIX: dung EDGE_VOICES_LIST module-level (60 giong)
        self._edge_voices = EDGE_VOICES_LIST
        EDGE_VOICES = EDGE_VOICES_LIST
        self.edge_voice_var = tk.StringVar(value="en-US-AriaNeural")
        self.edge_voice_display = tk.StringVar(value=EDGE_VOICES[0][1])
        self.edge_frame = tk.Frame(parent, bg=P["white"])
        # Ẩn ban đầu - chỉ hiện khi chọn Edge TTS
        tk.Label(self.edge_frame, text="🌐 Giọng Edge TTS:",
                 font=(FN,8,"bold"), bg=P["white"], fg="#0369a1").pack(anchor="w")
        self.edge_cb = ttk.Combobox(self.edge_frame,
                                     textvariable=self.edge_voice_display,
                                     values=[v[1] for v in EDGE_VOICES],
                                     state="readonly", font=(FN,8), width=22)
        self.edge_cb.pack(fill="x", pady=(2,0))
        self.edge_cb.current(0)
        self.edge_voice_display.set(EDGE_VOICES[0][1])  # show name
        def _on_ev(e):
            idx = self.edge_cb.current()
            self.edge_voice_var.set(EDGE_VOICES[idx][0])
            self.edge_voice_display.set(EDGE_VOICES[idx][1])
            # Tự chuyển sang Edge mode và bỏ chọn preset
            self._set_tts_mode("edge")
        # Ẩn/hiện theo mode
        self.edge_cb.bind("<<ComboboxSelected>>", _on_ev)

        # FIX v3.68 (tinh nang moi, theo yeu cau anh Bac): danh sach giong
        # "MG Nhanh" - LUC DAU dung dropdown ttk.Combobox nho, nhung anh Bac
        # yeu cau (2026-07-25) hien LUON danh sach day du co thanh cuon,
        # thay han vao cho khung "Cai Dat San" (dang trong rong o mode nay)
        # thay vi phai bam moi thay. Doi sang tk.Listbox + Scrollbar, cung
        # vi tri/kich thuoc voi khung "Cai Dat San (Voices)".
        self._fast_voices = FAST_VOICES_LIST
        self.fast_voice_var = tk.StringVar(value=FAST_VOICES_LIST[0][0])
        self.fast_voice_display = tk.StringVar(value=FAST_VOICES_LIST[0][1])
        self.fast_frame = tk.Frame(parent, bg=P["white"])
        tk.Label(self.fast_frame, text=f"⚡ Chọn giọng MG Nhanh ({len(FAST_VOICES_LIST)} giọng):",
                 font=(FN,8,"bold"), bg=P["white"], fg="#0369a1").pack(anchor="w", padx=10, pady=(4,2))
        _flb_container = tk.Frame(self.fast_frame, bg=P["white"],
                                   highlightthickness=1, highlightbackground=P["border"])
        _flb_container.pack(fill="both", expand=True, padx=10, pady=(0,6))
        _flb_sb = tk.Scrollbar(_flb_container, orient="vertical")
        _flb_sb.pack(side="right", fill="y")
        self.fast_listbox = tk.Listbox(_flb_container, yscrollcommand=_flb_sb.set,
                                        font=(FN,9), relief="flat", height=15,
                                        activestyle="none", bg=P["white"], fg=P["text"],
                                        selectbackground=P["purple"], selectforeground="white",
                                        highlightthickness=0, exportselection=False)
        self.fast_listbox.pack(side="left", fill="both", expand=True)
        _flb_sb.config(command=self.fast_listbox.yview)
        for _v_id, _v_lbl in FAST_VOICES_LIST:
            self.fast_listbox.insert("end", f"  {_v_lbl}")
        self.fast_listbox.selection_set(0)
        # Giu lai fast_cb (an, khong pack) de tuong thich code cu con tham chieu
        self.fast_cb = ttk.Combobox(self.fast_frame, textvariable=self.fast_voice_display,
                                     values=[v[1] for v in FAST_VOICES_LIST], state="readonly")
        def _on_fast_list_select(e=None):
            sel = self.fast_listbox.curselection()
            if not sel: return
            idx = sel[0]
            self.fast_voice_var.set(FAST_VOICES_LIST[idx][0])
            self.fast_voice_display.set(FAST_VOICES_LIST[idx][1])
            try: self.fast_cb.current(idx)
            except Exception: pass
            self._set_tts_mode("fast")
        self.fast_listbox.bind("<<ListboxSelect>>", _on_fast_list_select)

        # Voice label ẩn - vẫn giữ để không lỗi code tham chiếu
        self.cur_voice_lbl = tk.Label(parent, bg=P["white"])
        self.cur_voice_sub = tk.Label(parent, bg=P["white"])
        self._omni_only_start = True

        # ── Preview Voice button ──
        prev_row=tk.Frame(parent,bg=P["white"]); prev_row.pack(fill="x",padx=12,pady=(2,8))
        self.prev_btn=tk.Button(prev_row,text="▶  Thử Giọng",
                                command=self._preview_voice,
                                font=(FN,9,"bold"),
                                bg="#f0fdf4",fg="#16a34a",
                                relief="flat",cursor="hand2",
                                padx=10,pady=5,
                                highlightthickness=1,
                                highlightbackground="#86efac")
        self.prev_btn.pack(side="left",fill="x",expand=True)
        self.prev_stop_btn=tk.Button(prev_row,text="⏹",
                                     command=self._preview_stop,
                                     font=(FN,9),
                                     bg=P["hover"],fg=P["label"],
                                     relief="flat",cursor="hand2",
                                     padx=8,pady=5)
        self.prev_stop_btn.pack(side="left",padx=(4,0))
        tk.Button(parent,text="🎙 Duyệt 600+ Giọng",
                  command=lambda:(self._switch_tab("clone"), self._browse_voices()),
                  font=(FN,8,"bold"),bg=P["purple"],fg="white",relief="flat",
                  cursor="hand2",padx=12,pady=4
                  ).pack(anchor="w",padx=10,pady=(0,2))
        tk.Button(parent,text="↗ Chuyển sang Clone Voice",
                  command=lambda:self._switch_tab("clone"),
                  font=(FN,8),bg=P["bg"],fg=P["purple"],relief="flat",
                  cursor="hand2",padx=12,pady=3
                  ).pack(anchor="w",padx=10,pady=(0,4))

        # ── Section: Presets — boc toan bo vao 1 frame de de di chuyen ──
        self._preset_section_frame = tk.Frame(parent, bg=P["white"])
        self._preset_section_frame.pack(fill="both", expand=True)
        _psf = self._preset_section_frame  # alias ngan

        tk.Frame(_psf, bg=P["border"], height=1).pack(fill="x", padx=10, pady=6)
        self._sb_section(_psf, "💾 Cài Đặt Sẵn (Voices)")
        # Preset list voi scrollbar
        preset_container = tk.Frame(_psf, bg=P["white"],
                                     highlightthickness=1,
                                     highlightbackground=P["border"])
        if not hasattr(self,"_omni_hide_widgets"): self._omni_hide_widgets=[]
        self._preset_container = preset_container
        preset_container.pack(fill="both", expand=True, padx=10, pady=(0,6))

        pcanvas = tk.Canvas(preset_container, bg=P["white"],
                            highlightthickness=0, height=220)
        psb = tk.Scrollbar(preset_container, orient="vertical",
                           command=pcanvas.yview)
        psb.pack(side="right", fill="y")
        pcanvas.pack(side="left", fill="both", expand=True)
        pcanvas.configure(yscrollcommand=psb.set)

        self.preset_frame = tk.Frame(pcanvas, bg=P["white"])
        self._pcanvas_win = pcanvas.create_window(
            (0,0), window=self.preset_frame, anchor="nw")
        self.preset_frame.bind("<Configure>",
            lambda e: pcanvas.configure(
                scrollregion=pcanvas.bbox("all"),
                width=e.width))
        pcanvas.bind("<Configure>",
            lambda e: pcanvas.itemconfig(self._pcanvas_win, width=e.width))
        # Scroll bang chuot - chi khi chuot o tren canvas (khong dung bind_all)
        def _on_wheel(e):
            pcanvas.yview_scroll(int(-1*(e.delta/120)), "units")
        pcanvas.bind("<MouseWheel>", _on_wheel)
        pcanvas.bind("<Enter>", lambda e: pcanvas.bind_all("<MouseWheel>", _on_wheel))
        pcanvas.bind("<Leave>", lambda e: pcanvas.unbind_all("<MouseWheel>"))

        self._update_sidebar()

        # ── Thư Mục Lưu đã có trong các tab content, không hiện lại ở sidebar ──
        # Đảm bảo trạng thái ban đầu đúng: ẩn Edge design frame
        self.after(100, lambda: self._set_tts_mode("omnivoice"))
        # Luu reference separator de _show_preset_after_edge_save co the pack dung vi tri
        self._sb_edge_sep = tk.Frame(parent, bg=P["border"], height=1)
        self._sb_edge_sep.pack(fill="x", padx=10, pady=6)

        # ── Section: Thiết Kế Giọng Edge ── (ẩn mặc định, chỉ hiện khi chọn Edge TTS)
        self._edge_design_frame = tk.Frame(parent, bg=P["white"])
        # KHÔNG pack ngay — _set_tts_mode sẽ điều khiển ẩn/hiện
        _ep = self._edge_design_frame   # alias ngắn để dùng dưới đây
        self._sb_section(_ep,"🎙 Thiết Kế Giọng Edge TTS")

        # Danh sách giọng Edge theo ngôn ngữ
        # FIX v3.65 (2): danh sach lay TRUC TIEP tu `edge-tts --list-voices`
        # (dung ban cai tren may dev, chinh la thu vien app dang dung) de dam
        # bao MOI ma giong (ShortName) deu con ton tai that su tren Microsoft.
        # Phat hien va xoa cac giong da bi Microsoft KHAI TU (chon vao se loi,
        # khong tao duoc audio): en-AU CarlyNeural/DarrenNeural/WilliamNeural
        # (ban thuong), zh-CN XiaochenNeural, va cac giong "Monica/Sara/Nancy/
        # Amber/Ashley/Tony/Davis/Jason" o en-US (khong con trong danh sach
        # that). Dong thoi bo sung nhieu giong moi Microsoft da them (cac
        # giong "Multilingual", them giong HK/TW/An Do/Chau Au...).
        EDGE_FULL = {
            "🇺🇸 English (US)": [
                ("en-US-AriaNeural",              "Aria",             "Nữ", "Tự nhiên, tích cực"),
                ("en-US-AnaNeural",                "Ana",              "Nữ", "Trẻ em"),
                ("en-US-AvaNeural",                "Ava",              "Nữ", "Biểu cảm, thân thiện"),
                ("en-US-AvaMultilingualNeural",    "Ava (Đa ngôn ngữ)","Nữ", "Biểu cảm, đa ngôn ngữ"),
                ("en-US-EmmaNeural",               "Emma",             "Nữ", "Vui vẻ, rõ ràng"),
                ("en-US-EmmaMultilingualNeural",   "Emma (Đa ngôn ngữ)","Nữ","Vui vẻ, đa ngôn ngữ"),
                ("en-US-JennyNeural",              "Jenny",            "Nữ", "Thân thiện, chu đáo"),
                ("en-US-MichelleNeural",           "Michelle",         "Nữ", "Thân thiện, dễ chịu"),
                ("en-US-AndrewNeural",              "Andrew",              "Nam","Ấm, tự nhiên"),
                ("en-US-AndrewMultilingualNeural",  "Andrew (Đa ngôn ngữ)","Nam","Ấm, đa ngôn ngữ"),
                ("en-US-BrianNeural",                "Brian",              "Nam","Gần gũi, chân thành"),
                ("en-US-BrianMultilingualNeural",    "Brian (Đa ngôn ngữ)","Nam","Gần gũi, đa ngôn ngữ"),
                ("en-US-ChristopherNeural",          "Christopher",        "Nam","Đáng tin cậy"),
                ("en-US-EricNeural",                 "Eric",               "Nam","Lý trí, rõ ràng"),
                ("en-US-GuyNeural",                  "Guy",                "Nam","Nhiệt huyết"),
                ("en-US-RogerNeural",                "Roger",              "Nam","Sôi nổi"),
                ("en-US-SteffanNeural",              "Steffan",            "Nam","Lý trí, kể chuyện"),
            ],
            "🇬🇧 English (UK)": [
                ("en-GB-SoniaNeural",  "Sonia",  "Nữ", "Anh chuẩn, thanh lịch"),
                ("en-GB-LibbyNeural",  "Libby",  "Nữ", "Trẻ, hiện đại"),
                ("en-GB-MaisieNeural", "Maisie", "Nữ", "Nhẹ nhàng"),
                ("en-GB-RyanNeural",   "Ryan",   "Nam","Anh chuẩn, trầm"),
                ("en-GB-ThomasNeural", "Thomas", "Nam","Trang trọng"),
            ],
            "🇦🇺 English (AU)": [
                ("en-AU-NatashaNeural",             "Natasha",             "Nữ", "Úc tự nhiên"),
                ("en-AU-WilliamMultilingualNeural", "William (Đa ngôn ngữ)","Nam","Úc trầm ấm, đa ngôn ngữ"),
            ],
            "🇨🇦 English (CA)": [
                ("en-CA-ClaraNeural", "Clara", "Nữ", "Canada"),
                ("en-CA-LiamNeural",  "Liam",  "Nam","Canada"),
            ],
            "🇮🇪 English (IE)": [
                ("en-IE-EmilyNeural",  "Emily",  "Nữ", "Ireland"),
                ("en-IE-ConnorNeural", "Connor", "Nam","Ireland"),
            ],
            "🇮🇳 English (IN)": [
                ("en-IN-NeerjaNeural",           "Neerja",             "Nữ", "Ấn Độ, chuẩn"),
                ("en-IN-NeerjaExpressiveNeural", "Neerja (Biểu cảm)",  "Nữ", "Ấn Độ, biểu cảm"),
                ("en-IN-PrabhatNeural",          "Prabhat",            "Nam","Ấn Độ"),
            ],
            "🇻🇳 Tiếng Việt": [
                ("vi-VN-HoaiMyNeural", "Hoài My","Nữ","Miền Bắc, chuẩn"),
                ("vi-VN-NamMinhNeural","Nam Minh","Nam","Miền Bắc, rõ"),
            ],
            "🇯🇵 Japanese": [
                ("ja-JP-NanamiNeural", "Nanami", "Nữ","Nhật tự nhiên"),
                ("ja-JP-KeitaNeural",  "Keita",  "Nam","Nhật trầm"),
            ],
            "🇰🇷 Korean": [
                ("ko-KR-SunHiNeural",              "SunHi",                "Nữ", "Hàn tự nhiên"),
                ("ko-KR-InJoonNeural",             "InJoon",               "Nam","Hàn trầm"),
                ("ko-KR-HyunsuMultilingualNeural", "Hyunsu (Đa ngôn ngữ)", "Nam","Hàn, đa ngôn ngữ"),
            ],
            "🇨🇳 Chinese (CN)": [
                ("zh-CN-XiaoxiaoNeural",  "Xiaoxiao",  "Nữ", "Phổ thông, ấm"),
                ("zh-CN-XiaoyiNeural",    "Xiaoyi",    "Nữ", "Trẻ, hoạt bát"),
                ("zh-CN-YunxiNeural",     "Yunxi",     "Nam","Trẻ, tươi sáng"),
                ("zh-CN-YunxiaNeural",    "Yunxia",    "Nam","Dễ thương"),
                ("zh-CN-YunjianNeural",   "Yunjian",   "Nam","Kể chuyện, thể thao"),
                ("zh-CN-YunyangNeural",   "Yunyang",   "Nam","Phổ thông, chuyên nghiệp"),
                ("zh-CN-liaoning-XiaobeiNeural", "Xiaobei (Liêu Ninh)", "Nữ", "Phương ngữ, hài hước"),
                ("zh-CN-shaanxi-XiaoniNeural",   "Xiaoni (Thiểm Tây)",  "Nữ", "Phương ngữ, tươi sáng"),
            ],
            "🇭🇰 Chinese (HK)": [
                ("zh-HK-HiuMaanNeural", "HiuMaan", "Nữ", "Hong Kong, chuẩn"),
                ("zh-HK-HiuGaaiNeural", "HiuGaai", "Nữ", "Hong Kong"),
                ("zh-HK-WanLungNeural", "WanLung", "Nam","Hong Kong"),
            ],
            "🇹🇼 Chinese (TW)": [
                ("zh-TW-HsiaoChenNeural", "HsiaoChen", "Nữ", "Đài Loan, chuẩn"),
                ("zh-TW-HsiaoYuNeural",   "HsiaoYu",   "Nữ", "Đài Loan"),
                ("zh-TW-YunJheNeural",    "YunJhe",    "Nam","Đài Loan"),
            ],
            "🇫🇷 French": [
                ("fr-FR-DeniseNeural",             "Denise",                "Nữ", "Pháp, chuẩn"),
                ("fr-FR-EloiseNeural",             "Eloise",                "Nữ", "Pháp"),
                ("fr-FR-VivienneMultilingualNeural","Vivienne (Đa ngôn ngữ)","Nữ","Pháp, đa ngôn ngữ"),
                ("fr-FR-HenriNeural",              "Henri",                 "Nam","Pháp, chuẩn"),
                ("fr-FR-RemyMultilingualNeural",   "Remy (Đa ngôn ngữ)",    "Nam","Pháp, đa ngôn ngữ"),
            ],
            "🇩🇪 German": [
                ("de-DE-KatjaNeural",                "Katja",                  "Nữ", "Đức, chuẩn"),
                ("de-DE-AmalaNeural",                "Amala",                  "Nữ", "Đức"),
                ("de-DE-SeraphinaMultilingualNeural","Seraphina (Đa ngôn ngữ)","Nữ", "Đức, đa ngôn ngữ"),
                ("de-DE-ConradNeural",               "Conrad",                 "Nam","Đức, chuẩn"),
                ("de-DE-KillianNeural",              "Killian",                "Nam","Đức"),
                ("de-DE-FlorianMultilingualNeural",  "Florian (Đa ngôn ngữ)",  "Nam","Đức, đa ngôn ngữ"),
            ],
            "🇪🇸 Spanish": [
                ("es-ES-ElviraNeural", "Elvira", "Nữ", "Tây Ban Nha, chuẩn"),
                ("es-ES-XimenaNeural", "Ximena", "Nữ", "Tây Ban Nha"),
                ("es-ES-AlvaroNeural", "Alvaro", "Nam","Tây Ban Nha"),
                ("es-MX-DaliaNeural",  "Dalia",  "Nữ", "Mexico"),
                ("es-MX-JorgeNeural",  "Jorge",  "Nam","Mexico"),
            ],
            "🇮🇹 Italian": [
                ("it-IT-ElsaNeural",               "Elsa",                   "Nữ", "Ý, chuẩn"),
                ("it-IT-IsabellaNeural",           "Isabella",               "Nữ", "Ý"),
                ("it-IT-DiegoNeural",               "Diego",                  "Nam","Ý, chuẩn"),
                ("it-IT-GiuseppeMultilingualNeural","Giuseppe (Đa ngôn ngữ)", "Nam","Ý, đa ngôn ngữ"),
            ],
            "🇧🇷 Portuguese": [
                ("pt-BR-FranciscaNeural",           "Francisca",             "Nữ", "Brazil, chuẩn"),
                ("pt-BR-ThalitaMultilingualNeural", "Thalita (Đa ngôn ngữ)", "Nữ", "Brazil, đa ngôn ngữ"),
                ("pt-BR-AntonioNeural",             "Antonio",               "Nam","Brazil"),
            ],
            "🇷🇺 Russian": [
                ("ru-RU-SvetlanaNeural", "Svetlana", "Nữ", "Nga"),
                ("ru-RU-DmitryNeural",   "Dmitry",   "Nam","Nga"),
            ],
            "🇹🇭 Thai": [
                ("th-TH-PremwadeeNeural", "Premwadee", "Nữ", "Thái"),
                ("th-TH-NiwatNeural",     "Niwat",     "Nam","Thái"),
            ],
            "🇮🇩 Indonesian": [
                ("id-ID-GadisNeural", "Gadis", "Nữ", "Indo"),
                ("id-ID-ArdiNeural",  "Ardi",  "Nam","Indo"),
            ],
        }
        self._edge_full = EDGE_FULL

        # Dropdown chọn ngôn ngữ
        lang_row = tk.Frame(_ep, bg=P["white"])
        lang_row.pack(fill="x", padx=10, pady=(4,2))
        tk.Label(lang_row, text="Ngôn ngữ:", font=(FN,8),
                 bg=P["white"], fg=P["dim"]).pack(side="left")
        self._edge_lang_var = tk.StringVar(value=list(EDGE_FULL.keys())[0])
        lang_cb = ttk.Combobox(lang_row,
                               textvariable=self._edge_lang_var,
                               values=list(EDGE_FULL.keys()),
                               state="readonly", font=(FN,8), width=18)
        lang_cb.pack(side="left", padx=(4,0), fill="x", expand=True)
        lang_cb.current(0)

        # Chọn Nam/Nữ
        gender_row = tk.Frame(_ep, bg=P["white"])
        gender_row.pack(fill="x", padx=10, pady=2)
        tk.Label(gender_row, text="Giọng:", font=(FN,8),
                 bg=P["white"], fg=P["dim"]).pack(side="left")
        self._edge_gender_var = tk.StringVar(value="Tất cả")
        for g in ["Tất cả","Nữ","Nam"]:
            tk.Radiobutton(gender_row, text=g,
                           variable=self._edge_gender_var, value=g,
                           font=(FN,8), bg=P["white"],
                           activebackground=P["white"],
                           cursor="hand2",
                           command=self._refresh_edge_voice_list
                           ).pack(side="left", padx=4)

        # Danh sách giọng cuộn
        vlist_frame = tk.Frame(_ep, bg=P["white"],
                                highlightthickness=1,
                                highlightbackground=P["border"])
        vlist_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self._edge_listbox = tk.Listbox(vlist_frame,
                                         font=(FN,8), height=15,
                                         bg=P["white"], fg=P["text"],
                                         selectbackground=P["purple"],
                                         selectforeground="white",
                                         relief="flat",
                                         highlightthickness=0,
                                         activestyle="none",
                                         cursor="hand2")
        vsb = ttk.Scrollbar(vlist_frame, command=self._edge_listbox.yview)
        self._edge_listbox.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._edge_listbox.pack(fill="both", expand=True)
        self._edge_listbox.bind("<ButtonRelease-1>",
                                lambda e: self.after(10, self._on_edge_voice_select))

        # Sliders tốc độ / âm lượng / cao độ
        self._edge_speed_var  = tk.DoubleVar(value=1.0)
        self._edge_vol_var    = tk.DoubleVar(value=1.0)
        self._edge_pitch_var  = tk.DoubleVar(value=1.0)

        for lbl, var in [("🚀 Tốc độ", self._edge_speed_var),
                          ("🔊 Âm lượng", self._edge_vol_var),
                          ("🎵 Cao độ", self._edge_pitch_var)]:
            row = tk.Frame(_ep, bg=P["white"])
            row.pack(fill="x", padx=10, pady=1)
            tk.Label(row, text=lbl, font=(FN,8),
                     bg=P["white"], fg=P["dim"], width=10,
                     anchor="w").pack(side="left")
            vlbl = tk.Label(row, text="1.00", font=(FN,8,"bold"),
                             bg=P["white"], fg=P["purple"], width=4)
            vlbl.pack(side="right")
            ttk.Scale(row, from_=0.5, to=2.0, variable=var,
                      orient="horizontal",
                      command=lambda v, l=vlbl: l.config(text=f"{float(v):.2f}")
                      ).pack(side="left", fill="x", expand=True, padx=4)

        # Nút lưu cấu hình
        tk.Button(_ep, text="💾  Lưu Cấu Hình Vào Danh Sách",
                  command=self._save_edge_preset,
                  font=(FN,9,"bold"), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", pady=6
                  ).pack(fill="x", padx=10, pady=(6,2))

        # Init danh sách
        lang_cb.bind("<<ComboboxSelected>>",
                     lambda e: self._refresh_edge_voice_list())
        lang_cb.bind("<<ComboboxSelected>>",
                     lambda e: self._refresh_edge_voice_list(), add="+")
        self._refresh_edge_voice_list()

    def _set_taskbar_icon(self, ico_str):
        """Set icon cho taskbar va Alt+Tab sau khi window da render."""
        try:
            self.iconbitmap(default=ico_str)
            self.wm_iconbitmap(default=ico_str)
        except Exception:
            pass
        try:
            # Dung iconphoto lam fallback cho cac truong hop iconbitmap khong hoat dong
            from PIL import Image, ImageTk
            img = Image.open(ico_str)
            img = img.resize((32, 32), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, photo)
            self._icon_photo = photo  # Giu reference tranh garbage collect
        except Exception:
            pass

    def _auto_clear_legacy_cache_once(self):
        """Tu xoa cache rac 1 LAN duy nhat sau update.
        Dung flag file .cache_cleared_v318 de chi chay 1 lan.
        Cac cache xoa:
          1. __pycache__/ - bytecode Python cu
          2. .deps_installed - flag check pip
          3. *_trim*.wav - ref_audio cache cu
          4. ref_text RAC trong voices_library.json (placeholder cu)
        Voi voice clone: chi reset ref_text NGHI LA RAC, khong dung voice nao.
        """
        try:
            from pathlib import Path as _P
            import shutil as _sh
            _script_dir = _P(__file__).parent
            _flag = _script_dir / ".cache_cleared_v318"
            # Da chay roi -> bo qua
            if _flag.exists():
                return

            _cleared = []
            # 1. __pycache__
            try:
                _pc = _script_dir / "__pycache__"
                if _pc.exists():
                    _sh.rmtree(str(_pc), ignore_errors=True)
                    _cleared.append("__pycache__")
            except Exception: pass

            # 2. .deps_installed
            try:
                _df = _script_dir / ".deps_installed"
                if _df.exists():
                    _df.unlink()
                    _cleared.append(".deps_installed")
            except Exception: pass

            # 3. _trim*.wav cache
            try:
                for _tf in _script_dir.rglob("*_trim*.wav"):
                    try:
                        _tf.unlink()
                        _cleared.append(_tf.name)
                    except Exception: pass
            except Exception: pass

            # 4. ref_text RAC trong voices_library.json (NGUYEN NHAN CHINH)
            try:
                import json as _jc
                _vf = _script_dir / "voices_library.json"
                if _vf.exists():
                    _data = _jc.loads(_vf.read_text(encoding="utf-8"))
                    _reset_count = 0
                    for _v in _data:
                        if _v.get("ref_audio") and _v.get("ref_text"):
                            _old_ref = _v.get("ref_text", "")
                            _is_garbage = (
                                "Xin chào, đây là giọng đọc mẫu" in _old_ref
                                or "This is a sample voice recording" in _old_ref
                                or "Đây là đoạn ghi âm giọng" in _old_ref
                                or "dùng làm tham chiếu" in _old_ref
                                or len(_old_ref.strip()) < 10
                            )
                            if _is_garbage:
                                _v["ref_text"] = ""
                                _reset_count += 1
                    if _reset_count > 0:
                        _vf.write_text(
                            _jc.dumps(_data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
                        _cleared.append(f"reset {_reset_count} voice ref_text rac")
            except Exception as _ve:
                print(f"[AutoClearCache] Loi reset ref_text: {_ve}")

            # Tao flag file de khong chay lai
            try:
                _flag.write_text(f"v3.18 cleared: {', '.join(_cleared)}", encoding="utf-8")
            except Exception: pass

            if _cleared:
                print(f"[AutoClearCache] Da xoa: {', '.join(_cleared)}")
        except Exception as _e:
            print(f"[AutoClearCache] Loi: {_e}")

    def _init_network_mode(self):
        """Kiem tra mang trong background — KHONG block UI."""
        def _check():
            import socket as _sock, time as _t
            try:
                _s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                _s.settimeout(1.5)
                _s.connect(("8.8.8.8", 53))
                _s.close()
                online = True
            except Exception:
                online = False
            now = _t.time()
            self.after(0, lambda o=online, n=now: self._finish_network_init(o, n))

        threading.Thread(target=_check, daemon=True).start()

    def _finish_network_init(self, online: bool, ts: float):
        import time as _t
        self._apply_network_mode(online)
        self._online_cache_val  = online
        self._online_cache_time = ts

    def _apply_network_mode(self, online: bool):
        """Cap nhat trang thai mang cho Backend."""
        import os as _os, time as _t
        Backend._offline = not online
        if not online:
            _os.environ["HF_HUB_OFFLINE"] = "1"
            self._log("📵 Offline mode", "warn")
        else:
            _os.environ.pop("HF_HUB_OFFLINE", None)
            _os.environ.pop("TRANSFORMERS_OFFLINE", None)
            # Reset cache _is_online() ngay → _vkw() biet la online
            self._online_cache_val  = True
            self._online_cache_time = _t.time()
            self._log("🌐 Online mode - san sang tao voice", "ok")

    def _is_online(self) -> bool:
        """Kiem tra ket noi internet nhanh - cache ket qua 10 giay."""
        import socket as _sock, time as _time
        now = _time.time()
        # Dung cache neu kiem tra gan day (tranh check nhieu lan)
        if hasattr(self, "_online_cache_time") and \
                now - self._online_cache_time < 10:
            return self._online_cache_val
        result = False
        for _host, _port in [("8.8.8.8", 53), ("hf-mirror.com", 443)]:
            try:
                # FIX v3.65 (14): dung s.settimeout() (rieng cho socket nay)
                # thay vi socket.setdefaulttimeout() (toan cuc, anh huong ca
                # urllib.request.urlretrieve() cua _do_update() sau nay - tai
                # file .exe update se bi ke thua timeout 2s nay va bao loi
                # "read operation timed out" giua chung du mang binh thuong).
                s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                s.settimeout(2)
                s.connect((_host, _port))
                s.close()
                result = True
                break
            except Exception:
                continue
        self._online_cache_time = now
        self._online_cache_val  = result
        return result

    def _check_network_badge(self, parent):
        """Hien badge Offline neu mat mang."""
        def _check():
            import socket as _sock
            online = False
            for _host, _port in [("8.8.8.8", 53), ("hf-mirror.com", 443)]:
                try:
                    # FIX v3.65 (14): tuong tu _is_online() - dung settimeout()
                    # rieng cho socket nay, khong dung setdefaulttimeout() toan cuc.
                    _s = _sock.socket()
                    _s.settimeout(3)
                    _s.connect((_host, _port))
                    _s.close()
                    online = True
                    break
                except Exception:
                    continue
            self.after(0, lambda: _update(online))
        def _update(online):
            was_offline = hasattr(self, "_offline_badge")
            # LUON cap nhat Backend._offline - khong phu thuoc vao badge
            self._apply_network_mode(online)

            if not online:
                if not was_offline:
                    badge = tk.Frame(parent, bg="#64748b", padx=2, pady=2)
                    badge.pack(side="left", padx=(4,0), pady=10)
                    tk.Label(badge, text="  📵 Offline  ",
                             font=(FN,9,"bold"), bg="#64748b", fg="white").pack()
                    self._offline_badge = badge
            else:
                if was_offline:
                    try: self._offline_badge.destroy()
                    except: pass
                    del self._offline_badge
                    self._log("🌐 Co mang — da chuyen Online!", "ok")
                self._online_cache_time = 0  # Force re-check lan sau
        import threading
        threading.Thread(target=_check, daemon=True).start()
        # Kiem tra lai moi 30 giay
        self.after(10000, lambda: self._check_network_badge(parent))

    def _show_account_badge(self, parent):
        """Hien thi badge so ngay con lai o header."""
        msg = self._login_msg
        # Lay so ngay tu message
        import re as _re
        days_match = _re.search(r"C[oò]n (\d+) ng[aà]y", msg, _re.IGNORECASE)
        is_forever  = "vinh vien" in msg.lower() or "vinh-vien" in msg.lower() or "vĩnh viễn" in msg.lower()

        if is_forever:
            text  = "  ∞  Vinh vien  "
            color = P["purple"]
        elif days_match:
            days = int(days_match.group(1))
            text  = f"  🗓  Con {days} ngay  "
            if days <= 3:
                color = P["red"]
            elif days <= 7:
                color = "#f97316"  # orange
            else:
                color = P["green"]
        else:
            text  = "  ✓  Da dang nhap  "
            color = P["green"]

        badge = tk.Frame(parent, bg=color, padx=2, pady=2)
        badge.pack(side="left", padx=(8,0), pady=10)
        tk.Label(badge, text=text, font=(FN,9,"bold"),
                 bg=color, fg="white").pack()

    def _giahan_status_text(self):
        import re as _re
        msg = self._login_msg or ""
        if "vinh vien" in msg.lower() or "vĩnh viễn" in msg.lower():
            return "Tài khoản: Vĩnh viễn"
        m = _re.search(r"C[oò]n (\d+) ng[aà]y", msg, _re.IGNORECASE)
        if m:
            return f"Còn lại: {m.group(1)} ngày"
        return "Trạng thái: Đã đăng nhập"

    def _build_giahan_tab(self, parent):
        """Tab Gia Han: tao QR VietQR 300k/30 ngay, tu dong cong ngay qua
        webhook SePay o server (khong can nhap tay ma admin). Dung
        urllib.request (khong dung requests) - giong het quy uoc SSL context
        certifi da patch o dau file, tranh loi CERTIFICATE_VERIFY_FAILED."""
        import json as _json, urllib.request as _ureq, threading as _th, io as _io
        _GIAHAN_SERVER = "https://magicvoice-update-1.onrender.com"

        parent.configure(bg=P["bg"])
        wrap = tk.Frame(parent, bg=P["bg"])
        wrap.pack(fill="both", expand=True)

        card = tk.Frame(wrap, bg=P["white"], highlightthickness=1, highlightbackground=P["border"])
        card.pack(pady=40)

        tk.Label(card, text="💳  Gia Hạn Tài Khoản", font=(FN,16,"bold"), bg=P["white"], fg=P["text"]).pack(pady=(28,4), padx=60)
        tk.Label(card, text="300.000đ  —  30 ngày sử dụng", font=(FN,10), bg=P["white"], fg=P["sub"]).pack()

        status_lbl = tk.Label(card, text=self._giahan_status_text(), font=(FN,11,"bold"), bg=P["white"], fg=P["purple"])
        status_lbl.pack(pady=(14,2))
        tk.Label(card, text=f"Tài khoản: {self._username}", font=(FN,9), bg=P["white"], fg=P["dim"]).pack(pady=(0,10))

        qr_lbl = tk.Label(card, bg=P["white"])
        qr_lbl.pack(pady=4)

        info_var = tk.StringVar(value="")
        tk.Label(card, textvariable=info_var, font=(FN,9), bg=P["white"], fg=P["sub"], justify="center").pack(pady=(2,8))

        result_var = tk.StringVar(value="")
        result_lbl = tk.Label(card, textvariable=result_var, font=(FN,10,"bold"), bg=P["white"], fg=P["sub"], wraplength=340, justify="center")
        result_lbl.pack(pady=(0,6))

        gh_state = {"order_code": None, "stop": False, "photo": None}

        def _api(path, payload=None, method="GET"):
            data = _json.dumps(payload).encode("utf-8") if payload is not None else None
            req = _ureq.Request(_GIAHAN_SERVER + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
            with _ureq.urlopen(req, timeout=15) as resp:
                return _json.loads(resp.read().decode("utf-8"))

        def _fail(msg):
            btn_qr.config(state="normal", text="Tạo Mã QR")
            result_var.set("Lỗi: " + msg); result_lbl.config(fg=P["red"])

        def _on_paid():
            gh_state["stop"] = True
            result_var.set("✅ Đã gia hạn thành công! Số ngày còn lại cập nhật ở lần đăng nhập tiếp theo.")
            result_lbl.config(fg=P["green"])
            btn_qr.config(text="Đã Gia Hạn Xong", state="disabled", bg=P["green"])

        def _poll_loop():
            while not gh_state["stop"]:
                time.sleep(3)
                if gh_state["stop"]: return
                try:
                    r = _api(f"/api/order_status?order_code={gh_state['order_code']}")
                    if r.get("ok") and r.get("status") == "paid":
                        self.after(0, _on_paid); return
                except Exception:
                    pass

        def _show_qr(img_bytes, r):
            try:
                from PIL import Image, ImageTk
                img = Image.open(_io.BytesIO(img_bytes))
                img.thumbnail((300, 300), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                gh_state["photo"] = photo
                qr_lbl.config(image=photo)
            except Exception:
                pass
            result_var.set("Quét mã QR bằng app ngân hàng để chuyển khoản")
            result_lbl.config(fg=P["sub"])
            amount_txt = f"{r['amount']:,}".replace(",", ".")
            info_var.set(f"Nội dung CK: {r['order_code']}\nSố tiền: {amount_txt}đ\n{r['account_name']} - {r['account_no']}")
            _th.Thread(target=_poll_loop, daemon=True).start()

        def _create_qr():
            u = (self._username or "").strip()
            if not u:
                result_var.set("Không xác định được tài khoản, vui lòng đăng nhập lại."); result_lbl.config(fg=P["red"]); return
            btn_qr.config(state="disabled", text="Đang tạo QR...")
            result_var.set("")
            def _work():
                try:
                    r = _api("/api/create_qr", {"username": u}, method="POST")
                    if not r.get("ok"):
                        self.after(0, lambda: _fail(r.get("error","Lỗi không xác định"))); return
                    gh_state["order_code"] = r["order_code"]
                    img_bytes = _ureq.urlopen(r["qr_image_url"], timeout=15).read()
                    self.after(0, lambda: _show_qr(img_bytes, r))
                except Exception as ex:
                    _err_msg = str(ex)[:80]
                    self.after(0, lambda: _fail(_err_msg))
            _th.Thread(target=_work, daemon=True).start()

        btn_qr = tk.Button(card, text="Tạo Mã QR", command=_create_qr, font=(FN,11,"bold"),
                            bg=P["gold"], fg="white", relief="flat", cursor="hand2", padx=30, pady=10)
        btn_qr.pack(pady=(4,30))

    def _sb_section(self, parent, title):
        f=tk.Frame(parent,bg=P["bg"],pady=0); f.pack(fill="x",pady=(4,0))
        tk.Label(f,text=title,font=(FN,9,"bold"),
                 bg=P["bg"],fg=P["purple"],padx=12,pady=5).pack(anchor="w")

    def _refresh_edge_voice_list(self, keep_current=False):
        """Loc danh sach giong Edge theo ngon ngu va gioi tinh."""
        if not hasattr(self, "_edge_full"): return
        lang = self._edge_lang_var.get()
        gender = self._edge_gender_var.get()
        voices = self._edge_full.get(lang, [])
        if gender != "Tất cả":
            voices = [v for v in voices if v[2] == gender]
        # Tam unbind de tranh trigger _on_edge_voice_select khi selection_set
        self._edge_listbox.unbind("<<ListboxSelect>>")
        self._edge_listbox.delete(0, "end")
        self._edge_voices_filtered = voices
        cur = self.edge_voice_var.get() if hasattr(self,"edge_voice_var") else ""
        sel_idx = 0
        for i, (code, name, g, desc) in enumerate(voices):
            icon = "👩" if g == "Nữ" else "👨"
            self._edge_listbox.insert("end", f"  {icon} {name} — {desc}")
            if code == cur:
                sel_idx = i
        if voices:
            self._edge_listbox.selection_set(sel_idx)
            # Sync edge_voice_var voi item dang chon
            if sel_idx < len(voices):
                self.edge_voice_var.set(voices[sel_idx][0])
        # Re-bind sau khi xong
        self._edge_listbox.bind("<ButtonRelease-1>",
                                lambda e: self.after(10, self._on_edge_voice_select))

    def _on_edge_voice_select(self):
        """Chon giong Edge tu listbox → set voice + chuyen Edge mode."""
        if not hasattr(self, "_edge_voices_filtered"): return
        sel = self._edge_listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx < len(self._edge_voices_filtered):
            code = self._edge_voices_filtered[idx][0]
            self.edge_voice_var.set(code)
            # Goi _set_tts_mode de cap nhat tat ca UI
            self._set_tts_mode("edge")
            self._log(f"🌐 Chon Edge: {code}", "info")

    def _save_edge_preset(self):
        """Luu cau hinh giong Edge vao danh sach Cai Dat San."""
        if not hasattr(self, "_edge_voices_filtered"): return
        sel = self._edge_listbox.curselection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn giọng từ danh sách!")
            return
        idx = sel[0]
        if idx >= len(self._edge_voices_filtered): return

        code, name, gender, desc = self._edge_voices_filtered[idx]
        lang = self._edge_lang_var.get()
        speed  = self._edge_speed_var.get()
        vol    = self._edge_vol_var.get()
        pitch  = self._edge_pitch_var.get()

        # Tao VoiceProfile dang Edge
        import time as _time
        vp = VoiceProfile(
            name=f"{name} ({lang.split()[1] if len(lang.split())>1 else lang})",
            mode="edge",
            ref_audio=code,   # Luu ma giong Edge vao ref_audio
            ref_text=desc,
            instruct=f"edge:{code}",
            speed=speed,
            volume=vol,
            pitch=pitch,
            note=f"{gender} · {desc}",
            created=_time.strftime("%Y-%m-%d %H:%M"),
        )
        self.lib.profiles.append(vp)
        self.lib.save()
        self.sel_idx = len(self.lib.profiles) - 1
        self._refresh_voices()
        self._update_sidebar()
        self._refresh_srt_voices()
        self._show_preset_after_edge_save()
        messagebox.showinfo("Da luu", f"Da them '{vp.name}' vao Cai Dat San!")

    def _ensure_fast_preset_visible(self, code):
        """FIX v3.68 (tinh nang moi, theo yeu cau anh Bac): sau khi
        'MG Nhanh' generate xong, auto-save voice vao library
        (neu chua co) + hien preset list. Phong dung _ensure_edge_preset_visible."""
        import time as _time
        existing_idx = next((i for i, vp in enumerate(self.lib.profiles)
                             if vp.instruct == f"fast:{code}"), -1)
        if existing_idx < 0:
            name = code
            for c, lbl in FAST_VOICES_LIST:
                if c == code:
                    name = f"Nhanh — {lbl}"
                    break
            vp = VoiceProfile(
                name=name, mode="fast", ref_audio=code,
                instruct=f"fast:{code}",
                created=_time.strftime("%Y-%m-%d %H:%M"),
            )
            self.lib.profiles.append(vp)
            self.lib.save()
            self.sel_idx = len(self.lib.profiles) - 1
        else:
            self.sel_idx = existing_idx
        self._refresh_voices()
        self._update_sidebar()
        self._refresh_srt_voices()
        self._show_preset_after_edge_save()

    def _ensure_edge_preset_visible(self, code):
        """Sau khi Edge TTS generate xong: auto-save voice vao library (neu chua co) + hien preset list."""
        import time as _time
        existing_idx = next((i for i, vp in enumerate(self.lib.profiles)
                             if vp.instruct == f"edge:{code}"), -1)
        if existing_idx < 0:
            name = code
            for lang_voices in getattr(self, "_edge_full", {}).values():
                for c, n, g, d in lang_voices:
                    if c == code:
                        name = f"Edge — {n}"
                        break
            vp = VoiceProfile(
                name=name, mode="edge", ref_audio=code,
                instruct=f"edge:{code}",
                created=_time.strftime("%Y-%m-%d %H:%M"),
            )
            self.lib.profiles.append(vp)
            self.lib.save()
            self.sel_idx = len(self.lib.profiles) - 1
        else:
            self.sel_idx = existing_idx
        self._refresh_voices()
        self._update_sidebar()
        self._refresh_srt_voices()
        self._show_preset_after_edge_save()

    def _show_preset_after_edge_save(self):
        """Sau khi luu edge preset: collapse picker panel, hien preset list dung vi tri.

        Root cause: _edge_design_frame (listbox + sliders) chiem ~275px, day
        _preset_section_frame xuong ngoai vung hien thi cua sidebar.
        Fix: an picker (da chon xong), pack _preset_section_frame TRUOC separator
        (_sb_edge_sep) de dam bao no hien thi dung vi tri ban dau.
        """
        # 1. An panel chon giong - da chon xong, khong can hien
        if hasattr(self, "_edge_design_frame"):
            self._edge_design_frame.pack_forget()
        # 2. Hien Cai Dat San TRUOC separator (giu thu tu: preset → sep → edge_design)
        if hasattr(self, "_preset_section_frame"):
            if hasattr(self, "_sb_edge_sep"):
                self._preset_section_frame.pack(fill="both", expand=True,
                                                before=self._sb_edge_sep)
            else:
                self._preset_section_frame.pack(fill="both", expand=True)

    def _set_tts_mode(self, mode):
        """Chuyen che do TTS - khong goi _update_sidebar de tranh recursion."""
        self.tts_mode.set(mode)
        # Cap nhat style cac nut mode
        if hasattr(self, "_mode_btns_sb"):
            for v, b in self._mode_btns_sb.items():
                b.config(bg=P["purple"] if v==mode else P["bg"],
                         fg="white" if v==mode else P["sub"],
                         font=(FN, 9, "bold") if v==mode else (FN, 9))
        # An/hien Edge dropdown nhanh (combobox)
        # edge_frame (dropdown don gian) da duoc thay bang _edge_design_frame
        # Luon an de tranh hien 2 lua chon giong
        if hasattr(self, "edge_frame"):
            self.edge_frame.pack_forget()

        # FIX v3.68 (theo anh Bac bao loi 2026-07-25 - lan 4): BUG THAT SU -
        # cac khoi duoi day tung dung pack(before=self._preset_section_frame)
        # trong khi _preset_section_frame co the DANG BI AN (pack_forget) tu
        # lan goi truoc do (vd vua o mode "fast"). Tkinter YEU CAU widget
        # lam moc "before" phai DANG duoc quan ly boi cung 1 geometry manager
        # tai thoi diem goi - neu khong se loi/khong lam gi ca (that bai am
        # tham), khien _edge_design_frame KHONG HIEN RA khi chuyen tu "fast"
        # sang "edge". Sua GOC: luon pack_forget() HET cac khung dieu kien
        # TRUOC, roi quyet dinh hien _preset_section_frame TRUOC TIEN (vi no
        # la "moc" duoc cac khung khac dung), CUOI CUNG moi pack khung can
        # thiet theo dung mode - dam bao "before" luon tro toi 1 widget dang
        # duoc quan ly that su (hoac khong dung "before" khi khong can).
        if hasattr(self, "fast_frame"):
            self.fast_frame.pack_forget()
        if hasattr(self, "_edge_design_frame"):
            self._edge_design_frame.pack_forget()

        # FIX v3.65: LUON hien phan "Cai Dat San" du dang o mode nao (truoc day
        # an hoan toan khi mode=="edge" -> khach luu giong Edge xong (VoiceProfile
        # mode="edge" van nam chung trong self.lib.profiles, khong tach rieng)
        # nhung KHONG THAY danh sach do dau vi bi an -> phai chuyen qua MagicVoice
        # roi chuyen lai moi thay, rat kho dung. Gio luon hien de chon lai nhanh,
        # khong phai "di tim" nhu anh Bac yeu cau.
        # FIX v3.68 (theo anh Bac bao loi 2026-07-25 - lan 2): RIENG mode
        # "fast" thi AN khung nay - da thay the bang Listbox day du o tren
        # (fast_frame), tranh 1 khung "Cai Dat San" trong rong gay roi mat.
        # QUAN TRONG: phai quyet dinh xong TRUOC KHI pack fast_frame/
        # _edge_design_frame ben duoi, vi 2 khung do dung "before=" tro toi
        # _preset_section_frame.
        # FIX v3.68 (theo anh Bac bao 2026-07-26): mode "edge" cung AN khung
        # nay - trung lap voi danh sach giong Edge ngay ben tren, gay roi
        # mat/chong cheo. Giong het cach da lam cho mode "fast".
        if hasattr(self, "_preset_section_frame"):
            if mode in ("fast", "edge"):
                self._preset_section_frame.pack_forget()
            else:
                self._preset_section_frame.pack(fill="both", expand=True)

        # FIX v3.68: danh sach "MG Nhanh" la Listbox DAY DU + thanh cuon,
        # THAY HAN vi tri cua khung "Cai Dat San" (da an o tren khi mode=="fast").
        if mode == "fast" and hasattr(self, "fast_frame"):
            self.fast_frame.pack(fill="both", expand=True)
            # Dong bo lai lua chon dang hien trong Listbox voi fast_voice_var
            # hien tai (vd sau khi khoi phuc preset).
            if hasattr(self, "fast_listbox") and hasattr(self, "fast_voice_var"):
                _cur_fv = self.fast_voice_var.get() or FAST_VOICES_LIST[0][0]
                _codes_fv = [v[0] for v in FAST_VOICES_LIST]
                _idx_fv = _codes_fv.index(_cur_fv) if _cur_fv in _codes_fv else 0
                self.fast_listbox.selection_clear(0, "end")
                self.fast_listbox.selection_set(_idx_fv)
                self.fast_listbox.see(_idx_fv)
                self.fast_voice_display.set(FAST_VOICES_LIST[_idx_fv][1])

        # An/hien toan bo khung Thiet Ke Giong Edge TTS.
        # FIX v3.68 (theo anh Bac bao 2026-07-26): "Cai Dat San" gio da AN
        # het khi mode=="edge" (xem khoi tren) nen KHONG con can "before="
        # de chen truoc no nua - pack binh thuong voi fill="both", expand=True
        # de danh sach giong Edge chiem het khoang trong vua duoc giai phong,
        # dai ra giong het cach lam cho "MG Nhanh".
        if mode == "edge" and hasattr(self, "_edge_design_frame"):
            self._edge_design_frame.pack(fill="both", expand=True, pady=(0,4))

        # FIX v3.68 (theo anh Bac bao loi 2026-07-26): tab SRT KHONG CON bo
        # chon mode/giong rieng nua (da bo han - xem ghi chu o _build_srt_tab
        # va _refresh_srt_voices) - chi con 1 nguon duy nhat la sidebar. Moi
        # lan doi mode/giong o day, cap nhat lai nhan hien thi read-only
        # trong tab SRT cho khop.
        if hasattr(self, "_refresh_srt_voices"):
            self._refresh_srt_voices()

        # FIX v3.68 (theo anh Bac bao loi 2026-07-25 - lan 5): DA BO goi
        # _update_sidebar() o day. Ly do THEM (2026-07-25 lan 2) la de loc
        # lai "Cai Dat San" theo mode - nhung sau do anh Bac yeu cau HOAN
        # TAC bo loc (luon hien tat ca preset moi mode). Voi bo loc da bo,
        # goi _update_sidebar() o day KHONG CON CAN THIET NUA, va no gay ra
        # BUG THAT: _update_sidebar() doc self.sel_idx (preset dang chon
        # trong "Cai Dat San") va GHI DE NGUOC lai fast_voice_var/edge_voice_var
        # ve dung giong cua preset do - xoa mat lua chon giong VUA BAM trong
        # Listbox/dropdown (vd bam giong khac trong "MG Nhanh" nhung
        # _update_sidebar() lap tuc set lai ve giong cu cua preset dang
        # chon) - day chinh la nguyen nhan loi "thu giong nao cung ra 1
        # giong" anh Bac bao. KHONG duoc them lai loi goi nay tru khi that
        # su can thiet VA da kiem tra ky khong gay overwrite lua chon.

    def _update_sidebar(self):
        if not hasattr(self,"cur_voice_lbl"): return
        if self.sel_idx >= 0 and self.sel_idx<len(self.lib.profiles):
            vp=self.lib.profiles[self.sel_idx]
            self.cur_voice_lbl.config(text=vp.name)
            sub=f"mode: {vp.mode}"
            if vp.mode=="design": sub+=f" · {vp.instruct[:30]}"
            elif vp.mode=="clone" and vp.ref_audio:
                sub+=f" · {Path(vp.ref_audio).name[:25]}"
            self.cur_voice_sub.config(text=sub)
            # Neu la Edge preset → chi set voice, KHONG goi _set_tts_mode (tranh recursion)
            if vp.mode=="edge" and vp.instruct.startswith("edge:"):
                edge_code = vp.instruct.replace("edge:","").strip()
                if hasattr(self,"edge_voice_var"):
                    self.edge_voice_var.set(edge_code)
                if hasattr(self,"edge_cb") and hasattr(self,"_edge_voices"):
                    codes = [v[0] for v in self._edge_voices]
                    if edge_code in codes:
                        self.edge_cb.current(codes.index(edge_code))
            # FIX v3.68: preset "MG Nhanh" → khoi phuc dung giong
            # da luu (giong het pattern Edge o tren, KHONG goi _set_tts_mode)
            elif vp.mode=="fast" and vp.instruct.startswith("fast:"):
                fast_code = vp.instruct.replace("fast:","").strip()
                if hasattr(self,"fast_voice_var"):
                    self.fast_voice_var.set(fast_code)
                if hasattr(self,"_fast_voices"):
                    codes = [v[0] for v in self._fast_voices]
                    if fast_code in codes:
                        _idx_fc = codes.index(fast_code)
                        if hasattr(self, "fast_cb"):
                            self.fast_cb.current(_idx_fc)
                        if hasattr(self, "fast_listbox"):
                            self.fast_listbox.selection_clear(0, "end")
                            self.fast_listbox.selection_set(_idx_fc)
                            self.fast_listbox.see(_idx_fc)

        # Preset list — hien TAT CA moi mode (FIX v3.65 goc). FIX v3.68
        # (2026-07-25): tung thu loc theo dung mode dang chon, nhung anh
        # Bac xac nhan muon quay lai hanh vi goc - luon hien du du preset
        # (Edge/Clone/Design/Fast tron lan, phan biet bang icon) de de doi
        # qua lai, khong bi "mat" giong khoi tam nhin khi doi mode. Rieng
        # mode "fast" van AN CA khung nay (thay bang Listbox rieng o tren,
        # xem _set_tts_mode) nen khong anh huong gi vong lap duoi day.
        for w in self.preset_frame.winfo_children(): w.destroy()
        for i, vp in enumerate(self.lib.profiles):
            mode_icon = {"clone":"🎯","design":"✨","edge":"🌐","fast":"⚡"}.get(vp.mode,"●")
            sel = (i == self.sel_idx)
            bg  = P["sel"] if sel else P["white"]

            row = tk.Frame(self.preset_frame, bg=bg)
            row.pack(fill="x", pady=1)

            # Icon + tên (click để chọn)
            tk.Label(row, text=mode_icon, font=("",10),
                     bg=bg).pack(side="left", padx=(6,2), pady=3)
            name_lbl = tk.Label(row, text=vp.name,
                                 font=(FN, 9, "bold" if sel else "normal"),
                                 bg=bg, fg=P["purple"] if sel else P["text"],
                                 cursor="hand2")
            name_lbl.pack(side="left", fill="x", expand=True)
            name_lbl.bind("<Button-1>", lambda e, i=i: click(e, i))

            if True:  # Hien nut X cho tat ca voice
                def del_voice(idx=i):
                    name = self.lib.profiles[idx].name
                    if messagebox.askyesno("Xóa voice", f"Xóa voice '{name}'?"):
                        self.lib.remove(idx)
                        if self.sel_idx >= len(self.lib.profiles):
                            self.sel_idx = max(0, len(self.lib.profiles)-1)
                        self._refresh_voices()
                        self._update_sidebar()
                        self._log(f"🗑 Đã xóa: {name}", "warn")
                tk.Button(row, text="✕", command=del_voice,
                          font=(FN, 8), bg=bg, fg=P["dim"],
                          relief="flat", cursor="hand2",
                          padx=4, pady=0,
                          activebackground="#fee2e2",
                          activeforeground=P["red"]
                          ).pack(side="right", padx=4)

            if sel:
                tk.Label(row, text="✓", font=(FN,9),
                         bg=bg, fg=P["green"]).pack(side="right", padx=2)

            def click(e, idx=i):
                self.sel_idx = idx
                vp_clicked = self.lib.profiles[idx]
                if vp_clicked.mode == "edge" and vp_clicked.instruct.startswith("edge:"):
                    edge_code = vp_clicked.instruct.replace("edge:","").strip()
                    if hasattr(self,"edge_voice_var"):
                        self.edge_voice_var.set(edge_code)
                    # Kich hoat edge mode nhung GIU preset list hien thi
                    # KHONG goi _set_tts_mode("edge") vi no se an preset list
                    self.tts_mode.set("edge")
                    if hasattr(self, "_mode_btns_sb"):
                        for _v, _b in self._mode_btns_sb.items():
                            _b.config(
                                bg=P["purple"] if _v=="edge" else P["bg"],
                                fg="white"     if _v=="edge" else P["sub"],
                                font=(FN,9,"bold") if _v=="edge" else (FN,9))
                elif vp_clicked.mode == "fast" and vp_clicked.instruct.startswith("fast:"):
                    # FIX v3.68: bam preset "fast" da luu trong "Cai Dat San"
                    # -> chuyen dung sang mode "fast" (hien Listbox rieng),
                    # dong bo dung giong da luu. An toan goi _set_tts_mode
                    # (khong con overwrite lua chon nua - da bo _update_
                    # sidebar() thua trong ham do, xem ghi chu tai do).
                    fast_code = vp_clicked.instruct.replace("fast:","").strip()
                    if hasattr(self,"fast_voice_var"):
                        self.fast_voice_var.set(fast_code)
                    self._set_tts_mode("fast")
                else:
                    self._set_tts_mode("omnivoice")
                self._refresh_voices()
                self._update_sidebar()
                # FIX v3.68 (theo anh Bac bao loi 2026-07-26): nhanh "edge"
                # o tren KHONG goi _set_tts_mode() (co ly do rieng, xem ghi
                # chu) nen khong tu dong refresh nhan SRT - goi rieng o day
                # de dam bao MOI nhanh (edge/fast/omnivoice) deu cap nhat
                # dung nhan hien thi trong tab SRT.
                if hasattr(self, "_refresh_srt_voices"):
                    self._refresh_srt_voices()
            row.bind("<Button-1>", click)
            name_lbl.bind("<Button-1>", click)

    # ─────── STATUS BAR ────────────────────────────────────────────
    def _build_statusbar(self):
        self._statusbar_frame=bar=tk.Frame(self,bg=P["white"],pady=0)
        bar.pack(fill="x")

        # Right: output dir + buttons + BIG CREATE BUTTON
        # Pack TRƯỚC left để luôn hiển thị dù màn hình nhỏ
        right=tk.Frame(bar,bg=P["white"]); right.pack(side="right",padx=0,pady=0)

        # Output dir mini
        of_mini=tk.Frame(right,bg=P["white"]); of_mini.pack(side="left",padx=8)
        tk.Label(of_mini,text="Lưu tại:",font=(FN,8),
                 bg=P["white"],fg=P["dim"]).pack(anchor="w")
        tk.Entry(of_mini,textvariable=self.out_dir_var,font=(FN,8),
                 bg=P["sidebar"],fg=P["label"],relief="flat",
                 highlightthickness=1,highlightbackground=P["border"],
                 width=18).pack(ipady=3)

        tk.Button(right,text="📂",command=self._browse_out,
                  font=(FN,10),bg=P["white"],fg=P["sub"],relief="flat",
                  cursor="hand2",padx=4).pack(side="left")

        tk.Button(right,text="🏷",command=self._show_naming_dialog,
                  font=(FN,10),bg=P["white"],fg=P["purple"],relief="flat",
                  cursor="hand2",padx=4).pack(side="left")

        # Cancel
        self.cancel_btn=tk.Button(right,text="⏹",command=self._cancel,
                                   font=(FN,10),bg=P["white"],fg=P["red"],
                                   relief="flat",cursor="hand2",padx=6,
                                   state="disabled")
        self.cancel_btn.pack(side="left",padx=4)

        # Big Tạo button
        self.create_btn = tk.Button(right, text="  ▶  Tạo  ",
                                    command=self._create,
                                    font=(FN, 12, "bold"),
                                    bg=P["purple"], fg="white",
                                    activebackground="#3b60e0",
                                    activeforeground="white",
                                    relief="flat", cursor="hand2",
                                    padx=28, pady=12)
        self.create_btn.pack(side="left", padx=(6,0))

        # Left: status + progress — pack SAU right, fill phần còn lại
        left=tk.Frame(bar,bg=P["white"]); left.pack(side="left",fill="x",expand=True,padx=14,pady=6)
        # FIX v3.68 (theo anh Bac bao loi 2026-07-27): status_lbl (dong chu
        # tien do dai/ngan thay doi lien tuc, vd "[2/9] And now an imaginary
        # wife?...") duoc pack TRUOC timer/progressbar cung hang (side="left")
        # -> moi lan doi do dai chu, timer+progressbar bi DAY DICH CHUYEN VI
        # TRI theo, nhin giat/kho chiu. Anh Bac chi muon thay dong ho + thanh
        # chay, KHONG can dong chu nay nua. Van giu widget ton tai (khong xoa
        # han) de ham self._st() o rat nhieu noi trong code khong bi loi khi
        # goi .config() - chi KHONG pack ra man hinh nua.
        self.status_lbl=tk.Label(left,text="Sẵn sàng",font=(FN,9),
                                  bg=P["white"],fg=P["sub"])
        self._timer_label=tk.Label(left,text="",font=(FN,9,"bold"),
                                    bg=P["white"],fg=P["purple"])
        self._timer_label.pack(side="left")
        self._timer_running=False
        self._timer_start=0.0
        self.pb=ttk.Progressbar(left,mode="determinate",maximum=100,length=260)
        self.pb.pack(side="left",padx=(12,0))

        # Log (collapsible) — lưu log_bar thành self._log_bar để re-pack đúng thứ tự
        self._log_bar=tk.Frame(self,bg=P["bg"]); self._log_bar.pack(fill="x")
        tk.Label(self._log_bar,text="📋 Log:",font=(FN,8),
                 bg=P["bg"],fg=P["dim"],padx=8).pack(side="left",pady=2)
        tk.Button(self._log_bar,text="Xóa",command=lambda:self.logbox.delete("1.0","end"),
                  font=(FN,8),bg=P["bg"],fg=P["dim"],relief="flat",cursor="hand2"
                  ).pack(side="right",padx=8)
        self.logbox=scrolledtext.ScrolledText(self,height=4,state="disabled",
                                               bg=P["panel"] if False else "#f8f9fb",
                                               fg=P["text"],relief="flat",
                                               font=(FN2,8),wrap="word",
                                               highlightthickness=1,
                                               highlightbackground=P["border"])
        self.logbox.pack(fill="x",padx=0)
        self.logbox.tag_configure("ok",   foreground=P["green"])
        self.logbox.tag_configure("err",  foreground=P["red"])
        self.logbox.tag_configure("warn", foreground=P["gold"])
        self.logbox.tag_configure("info", foreground=P["blue"])

    # ─────── STARTUP INFO ──────────────────────────────────────────
    # ─── PREVIEW SAMPLES theo ngôn ngữ ────────────────────────────
    _PREVIEW_SAMPLES = {
        "vi": ("Xin chào! Đây là đoạn kiểm tra giọng đọc. "
               "Giọng nghe có tự nhiên và rõ ràng không? "
               "Hãy lắng nghe kỹ để cảm nhận chất lượng và sắc thái của giọng này nhé."),
        "en": ("Hello! This is a voice preview sample to check quality and naturalness. "
               "Does this voice sound clear, smooth, and comfortable to listen to? "
               "I hope you enjoy the tone and clarity of this voice."),
        "ja": ("こんにちは！これは音声プレビューのサンプルです。"
               "声は自然でクリアに聞こえますか？この声の品質と特徴をぜひご確認ください。"),
        "ko": ("안녕하세요! 이것은 음성 미리보기 샘플입니다. "
               "목소리가 자연스럽고 선명하게 들리나요? 이 음성의 품질과 특색을 확인해 보세요."),
        "zh": ("你好！这是语音预览示例，用于检查这个声音的质量和自然度。"
               "这个声音听起来清晰、流畅吗？希望您对这个声音的音质感到满意。"),
        "fr": ("Bonjour! Voici un exemple de prévisualisation vocale. "
               "Cette voix vous semble-t-elle claire et naturelle? "
               "Prenez le temps d'écouter attentivement la qualité de cette voix."),
        "de": ("Hallo! Dies ist ein Sprachvorschau-Beispiel. "
               "Klingt diese Stimme klar und natürlich? "
               "Hören Sie genau hin, um die Qualität dieser Stimme zu beurteilen."),
        "es": ("¡Hola! Este es un ejemplo de vista previa de voz. "
               "¿Esta voz suena clara y natural? "
               "Escuche con atención para apreciar la calidad y el tono de esta voz."),
        "th": ("สวัสดี! นี่คือตัวอย่างการแสดงตัวอย่างเสียง "
               "เสียงฟังดูชัดเจนและเป็นธรรมชาติหรือไม่? "
               "โปรดฟังอย่างตั้งใจเพื่อประเมินคุณภาพของเสียงนี้"),
        "id": ("Halo! Ini adalah sampel pratinjau suara. "
               "Apakah suara ini terdengar jelas dan alami? "
               "Dengarkan dengan seksama untuk menilai kualitas suara ini."),
        "pt": ("Olá! Este é um exemplo de pré-visualização de voz. "
               "Essa voz soa clara e natural? "
               "Ouça com atenção para avaliar a qualidade desta voz."),
        "it": ("Ciao! Questo è un campione di anteprima vocale. "
               "Questa voce suona chiara e naturale? "
               "Ascolta attentamente per valutare la qualità di questa voce."),
        "ru": ("Привет! Это образец предварительного просмотра голоса. "
               "Звучит ли этот голос четко и естественно? "
               "Внимательно послушайте, чтобы оценить качество этого голоса."),
    }

    def _detect_preview_lang(self, edge_code="", vp=None, instruct=None):
        if edge_code:
            return edge_code.split("-")[0].lower()
        # FIX v3.65 (9): uu tien TUYET DOI vp.lang neu khach da chon tuong
        # minh luc luu voice (dropdown "Ngon ngu giong" trong VoiceDialog) -
        # chinh xac 100%, khong con phai doan qua ten/instruct nua. Neu rong
        # (voice cu chua co field nay, hoac khach chon "(Tu dong doan)") thi
        # roi xuong cac buoc doan heuristic ben duoi nhu truoc.
        if vp and getattr(vp, "lang", ""):
            return vp.lang
        # FIX v3.65: cac preset Voice Design trong VOICE_PRESETS thuoc nhom
        # "English - British/American/Other Accents" deu co instruct chua tu
        # "... accent" (vd "female, young adult, british accent") - day la
        # giong TIENG ANH voi am sac khac nhau, KHONG phai giong ban ngu.
        # Truoc day ham nay chi doan ngon ngu qua TEN preset (vp.name) va
        # khong co keyword nao cho tieng Anh -> moi preset tieng Anh deu roi
        # ve mac dinh "vi" o cuoi ham, khien nghe thu giong Anh lai doc mau
        # tieng Viet. Gio check instruct truoc: co "accent" -> chac chan la "en".
        #
        # FIX v3.65 (8): CHI ap dung luat "accent" nay khi vp.mode=="design"
        # (hoac khi goi truc tiep voi instruct string, khong kem vp - vd tu
        # VoiceBrowserDialog._preview()). Bug thuc te: giong CLONE "vietnu"
        # (tieng Viet that) bi nghe thu ra tieng Anh vi truong instruct cua
        # no con sot chu "accent" tu VoiceDialog._save() truoc day KHONG
        # phan biet mode luc luu (da fix rieng o _save()) - nhung van can
        # chot an toan o day phong truong hop du lieu cu da luu tu truoc.
        _instruct = instruct if instruct is not None else (getattr(vp, "instruct", "") or "" if vp else "")
        _is_design = (vp is None) or (getattr(vp, "mode", None) == "design")
        if _is_design and "accent" in (_instruct or "").lower():
            return "en"
        if vp:
            n = vp.name.lower()
            # FIX v3.65 (8): bo keyword "anh" don le - qua rong, de trung
            # nham voi rat nhieu ten tieng Viet co chua chuoi "anh" (Thanh,
            # Khanh, Oanh, Ngoc Anh...). Giu lai "english/british/american"
            # vi it kha nang trung ngau nhien hon.
            for kw, lang in [("việt","vi"),("viet","vi"),(" vn","vi"),
                              ("nhật","ja"),("japan","ja"),
                              ("hàn","ko"),("korea","ko"),
                              ("trung","zh"),("china","zh"),("chinese","zh"),
                              ("pháp","fr"),("french","fr"),
                              ("đức","de"),("german","de"),
                              ("tây ban","es"),("spanish","es"),
                              ("thái","th"),("thai","th"),
                              ("indo","id"),("bahasa","id"),
                              ("english","en"),
                              ("british","en"),("american","en")]:
                if kw in n: return lang
        return "vi"

    def _run_voice_preview(self, text, log_label, btn_ref=None, override_kw=None, override_edge_code=None, override_fast_code=None):
        """Core preview: generate audio từ text + voice đang chọn, phát không lưu.
        btn_ref: button cần disable/restore (ngoài self.prev_btn); có thể None.
        override_kw: FIX v3.65 - neu truyen vao (vd {"instruct": "..."}), dung
        THANG kw nay cho Backend.gen() thay vi doc tu self.lib.profiles/sel_idx.
        Dung boi VoiceBrowserDialog de nghe thu 1 instruct TRUOC khi luu voice.
        override_edge_code: FIX v3.65 (2) - neu truyen vao (vd "es-ES-ElviraNeural"),
        dung THANG ma Edge nay thay vi doc vp.instruct tu self.lib.profiles/sel_idx.
        Dung boi nut "Thu Giong" chinh khi dang o Edge TTS mode, de nghe thu DUNG
        giong dang duyet trong panel "Thiet Ke Giong Edge TTS" (truoc day doc
        nham theo voice DA LUU cu trong sel_idx, khong phai giong vua chon)."""
        if hasattr(self, "_prev_thread") and self._prev_thread and self._prev_thread.is_alive():
            self._log("⏳ Đang phát thử, vui lòng chờ...", "warn"); return False

        vp = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        # FIX v3.68 (theo anh Bac bao loi 2026-07-25 - lan 6): BUG THAT -
        # khi override_fast_code duoc truyen (nghe thu MG Nhanh), _is_edge
        # VAN duoc tinh doc lap tu vp.mode (preset dang CHON trong "Cai Dat
        # San", KHONG lien quan gi toi giong vua bam trong danh sach MG
        # Nhanh) - neu preset dang chon tinh co la Edge, _is_edge = True SE
        # "thang" truoc trong if/elif ben duoi, bo qua het override_fast_code.
        # Sua: chi tinh _is_edge tu vp.mode khi KHONG co ca override_edge_code
        # LAN override_fast_code (tuc dang o truong hop "nghe thu theo preset
        # dang chon", khong phai "nghe thu theo lua chon nhanh vua bam").
        if override_edge_code:
            _is_edge = True
            _edge_code = override_edge_code
        elif override_fast_code:
            _is_edge = False
            _edge_code = ""
        else:
            _is_edge = (override_kw is None and vp and vp.mode == "edge" and
                        hasattr(vp, "instruct") and vp.instruct.startswith("edge:"))
            _edge_code = vp.instruct.replace("edge:", "").strip() if _is_edge else ""

        # FIX v3.68 (tinh nang moi, theo yeu cau anh Bac): nghe thu mode
        # "MG Nhanh" - phong dung pattern _is_edge o tren.
        if override_fast_code:
            _is_fast = True
            _fast_code = override_fast_code
        else:
            _is_fast = (override_kw is None and not _is_edge and vp and vp.mode == "fast" and
                        hasattr(vp, "instruct") and vp.instruct.startswith("fast:"))
            _fast_code = vp.instruct.replace("fast:", "").strip() if _is_fast else ""

        if not self.model_loaded and not _is_edge and not _is_fast:
            messagebox.showwarning("Chưa tải model", "Hãy tải model trước!"); return False

        self._log(f"🎧 Nghe thử: {log_label}", "info")
        # Disable cả 2 button nếu có
        self.prev_btn.config(text="⏳ Đang tạo...", state="disabled", bg="#fef9c3")
        if btn_ref:
            btn_ref.config(text="⏳ Đang tạo...", state="disabled", bg="#fef9c3")

        def _gen():
            try:
                import tempfile, os as _os
                tmp = tempfile.mktemp(suffix=".wav")

                if _is_edge:
                    import asyncio, edge_tts, inspect as _ins, wave as _wave
                    _use_pcm = 'codec' in _ins.signature(
                        edge_tts.Communicate.__init__).parameters

                    async def _do_edge():
                        # FIX v3.65 (10): them thu lai 3 lan - truoc day chi
                        # thu 1 lan, neu Microsoft Edge TTS tra ve rong (loi
                        # "No audio was received" - hay gap khi goi lien tuc
                        # nhieu request/mang chap chon) se bao loi ngay.
                        # Dong bo voi retry 3 lan da co san o luong tao SRT
                        # hang loat (_gen_one). Kem verify file khong rong
                        # truoc khi coi la thanh cong.
                        _last_err = None
                        for _attempt in range(3):
                            try:
                                if _use_pcm:
                                    tmp_pcm = tmp + ".pcm"
                                    comm = edge_tts.Communicate(
                                        text, _edge_code,
                                        codec="audio-24khz-16bit-mono-pcm")
                                    await comm.save(tmp_pcm)
                                    if not _os.path.exists(tmp_pcm) or _os.path.getsize(tmp_pcm) < 100:
                                        raise RuntimeError("Khong nhan duoc audio (file PCM rong)")
                                    with open(tmp_pcm, 'rb') as f: pcm = f.read()
                                    with _wave.open(tmp, 'wb') as wf:
                                        wf.setnchannels(1); wf.setsampwidth(2)
                                        wf.setframerate(24000); wf.writeframes(pcm)
                                    try: _os.remove(tmp_pcm)
                                    except Exception: pass
                                else:
                                    tmp_mp3 = tmp + ".mp3"
                                    comm = edge_tts.Communicate(text, _edge_code)
                                    await comm.save(tmp_mp3)
                                    if not _os.path.exists(tmp_mp3) or _os.path.getsize(tmp_mp3) < 100:
                                        raise RuntimeError("Khong nhan duoc audio (file MP3 rong)")
                                    import imageio_ffmpeg as _iff
                                    import subprocess as _spe
                                    _spe.run(
                                        [_iff.get_ffmpeg_exe(), '-i', tmp_mp3,
                                         '-ar', '24000', '-ac', '1', '-f', 'wav',
                                         tmp, '-y', '-loglevel', 'quiet'],
                                        timeout=30, check=True,
                                        creationflags=0x08000000)
                                    try: _os.remove(tmp_mp3)
                                    except Exception: pass
                                _last_err = None
                                break
                            except Exception as _e_edge:
                                _last_err = _e_edge
                                if _attempt < 2:
                                    await asyncio.sleep(1.5)
                        if _last_err:
                            raise _last_err

                    asyncio.run(_do_edge())
                elif _is_fast:
                    # FIX v3.68 (tinh nang moi, theo yeu cau anh Bac): nghe
                    # thu mode "MG Nhanh" - local, khong can mang.
                    import soundfile as _sf_fp
                    _t_fp = _fast_generate(text, _fast_code, speed=self._get_speed())
                    _sf_fp.write(tmp, _t_fp.squeeze().numpy(), 24000, subtype='PCM_16')
                else:
                    import soundfile as _sf_p, numpy as _np_p
                    if override_kw is not None:
                        kw = override_kw
                    else:
                        kw = {}
                        if vp and vp.mode == "clone":
                            ref = vp.ref_audio
                            if ref and not _os.path.isfile(ref):
                                from pathlib import Path as _Pp
                                _alt = _Pp(_SCRIPT_DIR) / "clone_refs" / _Pp(ref).name
                                if _alt.exists(): ref = str(_alt)
                            if ref and _os.path.isfile(ref):
                                kw["ref_audio"] = self._prepare_ref_audio(ref)
                            else:
                                raise ValueError(f"Không tìm thấy file audio mẫu: {vp.ref_audio}")
                        elif vp and vp.mode == "design":
                            if not vp.instruct:
                                raise ValueError("Voice Design thiếu mô tả!")
                            kw["instruct"] = _normalize_instruct(vp.instruct)

                    a = Backend.gen(text, num_step=self.steps_var.get(),
                                    speed=self._get_speed(), **kw)
                    _aud = a
                    if isinstance(_aud, (list, tuple)): _aud = _aud[0]
                    if hasattr(_aud, 'cpu'): _aud = _aud.detach().cpu().numpy()
                    _aud = _np_p.squeeze(_aud)
                    if _aud.ndim == 0: _aud = _aud.reshape(1)
                    _sf_p.write(tmp, _aud.astype('float32'), 24000, subtype='PCM_16')

                self._prev_tmp = tmp
                if sys.platform == "win32":
                    import winsound, threading as _thr30
                    self.after(0, lambda: [
                        self.prev_btn.config(text="🔊 Đang phát...", bg="#dbeafe"),
                        btn_ref.config(text="🔊 Đang phát...", bg="#dbeafe") if btn_ref else None
                    ])
                    # Auto-stop sau 30 giây
                    def _autostop():
                        import time; time.sleep(30)
                        try: winsound.PlaySound(None, winsound.SND_PURGE)
                        except Exception: pass
                    _thr30.Thread(target=_autostop, daemon=True).start()
                    winsound.PlaySound(tmp, winsound.SND_FILENAME)
                else:
                    import subprocess as _sp, threading as _thr30
                    proc = _sp.Popen(["aplay", tmp])
                    def _autostop():
                        import time; time.sleep(30)
                        try: proc.terminate()
                        except Exception: pass
                    _thr30.Thread(target=_autostop, daemon=True).start()
                self._log(f"✅ Nghe thử xong: {log_label}", "ok")
            except Exception as e:
                self._log(f"❌ Lỗi nghe thử: {e}", "err")
            finally:
                self.after(0, lambda: [
                    self.prev_btn.config(text="▶  Thử Giọng", state="normal", bg="#f0fdf4"),
                    btn_ref.config(text="🎧 Nghe Thử", state="normal", bg="#f0fdf4") if btn_ref else None
                ])

        import threading
        self._prev_thread = threading.Thread(target=_gen, daemon=True)
        self._prev_thread.start()
        return True

    def _preview_instruct(self, instruct, label, btn_ref=None):
        """FIX v3.65: nghe thu TRUC TIEP 1 cau instruct (dung boi VoiceBrowserDialog
        de khach nghe thu giong TRUOC khi bam Luu) - khong phu thuoc vao
        self.lib.profiles/sel_idx nhu _preview_voice."""
        if not instruct or not instruct.strip():
            messagebox.showwarning("Thiếu mô tả", "Hãy chọn giọng hoặc nhập Instruct trước!")
            return False
        if not self.model_loaded:
            messagebox.showwarning("Chưa tải model", "Hãy tải model trước!"); return False
        lang = self._detect_preview_lang(instruct=instruct)
        sample = self._PREVIEW_SAMPLES.get(lang, self._PREVIEW_SAMPLES["en"])
        kw = {"instruct": _normalize_instruct(instruct)}
        return self._run_voice_preview(sample, label, btn_ref=btn_ref, override_kw=kw)

    def _preview_voice(self):
        """Thử giọng bằng đoạn mẫu tự động đúng ngôn ngữ."""
        # FIX v3.65 (2): neu dang o che do Edge TTS, uu tien dung edge_voice_var
        # (giong DANG duoc chon/duyet trong panel "Thiet Ke Giong Edge TTS")
        # thay vi doc qua self.lib.profiles[sel_idx] (co the la voice CU da
        # luu tu truoc, khac voi giong vua chon) - dam bao nghe thu DUNG giong
        # se dung khi bam nut "Tao" that su.
        if (hasattr(self, "tts_mode") and self.tts_mode.get() == "edge"
                and hasattr(self, "edge_voice_var") and self.edge_voice_var.get()):
            _edge_code = self.edge_voice_var.get()
            _lang = self._detect_preview_lang(_edge_code)
            sample = self._PREVIEW_SAMPLES.get(_lang, self._PREVIEW_SAMPLES["en"])
            self._run_voice_preview(sample, f"Edge: {_edge_code}", override_edge_code=_edge_code)
            return

        # FIX v3.68 (tinh nang moi, theo yeu cau anh Bac): nghe thu dung
        # giong DANG duoc chon trong dropdown "MG Nhanh", phong
        # dung pattern Edge o tren.
        if (hasattr(self, "tts_mode") and self.tts_mode.get() == "fast"
                and hasattr(self, "fast_voice_var") and self.fast_voice_var.get()):
            _fast_code = self.fast_voice_var.get()
            sample = self._PREVIEW_SAMPLES.get("en", "")
            self._run_voice_preview(sample, f"Nhanh: {_fast_code}", override_fast_code=_fast_code)
            return

        vp = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        _is_edge = (vp and vp.mode == "edge" and
                    hasattr(vp, "instruct") and vp.instruct.startswith("edge:"))
        _edge_code = vp.instruct.replace("edge:", "").strip() if _is_edge else ""
        _lang = self._detect_preview_lang(_edge_code, vp)
        sample = self._PREVIEW_SAMPLES.get(_lang, self._PREVIEW_SAMPLES["en"])
        vname = vp.name if vp else ""
        self._run_voice_preview(sample, vname)

    @staticmethod
    def _smart_trim_preview(raw, max_chars=300):
        """Cắt text tại cuối câu gần nhất trong max_chars ký tự."""
        if len(raw) <= max_chars:
            return raw
        chunk = raw[:max_chars]
        # Tìm cuối câu cuối cùng (cả dấu Việt/Nhật/Trung)
        last_end = max(
            chunk.rfind('.'), chunk.rfind('!'), chunk.rfind('?'),
            chunk.rfind('。'), chunk.rfind('！'), chunk.rfind('？'),
            chunk.rfind('…'),
        )
        if last_end > max_chars // 3:
            return chunk[:last_end + 1].strip()
        last_space = chunk.rfind(' ')
        if last_space > 0:
            return chunk[:last_space].strip()
        return chunk.strip()

    def _preview_text_input(self):
        """Nghe thử đoạn văn bản đang nhập — tối đa ~30s, tự dừng."""
        raw = self.txt_in.get("1.0", "end-1c").strip()
        if not raw:
            messagebox.showinfo("Trống", "Hãy nhập văn bản trước khi nghe thử!"); return
        text = self._smart_trim_preview(raw, max_chars=300)
        if len(raw) > len(text):
            self._log(f"ℹ️  Nghe thử {len(text)} ký tự đầu · tự dừng sau 30s", "info")
        # FIX v3.68 (theo anh Bac bao loi 2026-07-26): BUG THAT - nut "Xem
        # truoc"/"Nghe Thu" o tab Van Ban truoc day LUON doc giong tu preset
        # dang chon trong "Cai Dat San" (self.sel_idx), BO QUA hoan toan che
        # do dang chon o sidebar (Edge TTS / MG Nhanh) - khac voi nut "Thu
        # Giong" chinh o sidebar (_preview_voice) da uu tien dung tts_mode.
        # Day chinh la nguyen nhan: chon giong Adam (MG Nhanh) nhung bam
        # "Nghe Thu" o tab Van Ban lai ra giong Aria (preset Edge dang chon).
        # Sua: ap dung DUNG pattern uu tien tts_mode nhu _preview_voice.
        if (hasattr(self, "tts_mode") and self.tts_mode.get() == "edge"
                and hasattr(self, "edge_voice_var") and self.edge_voice_var.get()):
            _edge_code = self.edge_voice_var.get()
            self._run_voice_preview(text, f"Edge: {_edge_code} · {len(text)} ký tự",
                                    btn_ref=self._txt_prev_btn, override_edge_code=_edge_code)
            return
        if (hasattr(self, "tts_mode") and self.tts_mode.get() == "fast"
                and hasattr(self, "fast_voice_var") and self.fast_voice_var.get()):
            _fast_code = self.fast_voice_var.get()
            self._run_voice_preview(text, f"Nhanh: {_fast_code} · {len(text)} ký tự",
                                    btn_ref=self._txt_prev_btn, override_fast_code=_fast_code)
            return
        vp = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        vname = vp.name if vp else "giọng đang chọn"
        self._run_voice_preview(text, f"{vname} · {len(text)} ký tự",
                                btn_ref=self._txt_prev_btn)

    def _preview_srt_input(self):
        """Nghe thử nội dung SRT đang nhập — strip timestamp, tối đa ~30s."""
        import re as _re
        raw = self.srt_editor.get("1.0", "end-1c").strip()
        if not raw:
            messagebox.showinfo("Trống", "Hãy nhập nội dung SRT trước khi nghe thử!"); return
        # Strip số thứ tự và timestamp SRT
        lines = raw.splitlines()
        text_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            if line.isdigit(): continue
            if _re.match(r'^\d+:\d+:\d+[,\.]\d+\s*-->\s*\d+:\d+:\d+[,\.]\d+', line): continue
            text_lines.append(line)
        plain = ' '.join(text_lines)
        if not plain.strip():
            messagebox.showinfo("Trống", "Không tìm thấy nội dung text trong SRT!"); return
        text = self._smart_trim_preview(plain, max_chars=300)
        if len(plain) > len(text):
            self._log(f"ℹ️  Nghe thử {len(text)} ký tự đầu SRT · tự dừng sau 30s", "info")
        # FIX v3.68 (theo anh Bac bao loi 2026-07-26): tab SRT khong con bo
        # chon rieng - doc THANG theo sidebar (self.tts_mode), giong het
        # pattern _preview_text_input.
        if (hasattr(self, "tts_mode") and self.tts_mode.get() == "edge"
                and hasattr(self, "edge_voice_var") and self.edge_voice_var.get()):
            _edge_code = self.edge_voice_var.get()
            self._run_voice_preview(text, f"SRT · Edge: {_edge_code} · {len(text)} ký tự",
                                    btn_ref=self._srt_prev_btn, override_edge_code=_edge_code)
            return
        if (hasattr(self, "tts_mode") and self.tts_mode.get() == "fast"
                and hasattr(self, "fast_voice_var") and self.fast_voice_var.get()):
            _fast_code = self.fast_voice_var.get()
            self._run_voice_preview(text, f"SRT · Nhanh: {_fast_code} · {len(text)} ký tự",
                                    btn_ref=self._srt_prev_btn, override_fast_code=_fast_code)
            return
        # Lấy voice từ SRT tab (MagicVoice preset)
        vp = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        vname = vp.name if vp else "giọng đang chọn"
        self._run_voice_preview(text, f"SRT · {vname} · {len(text)} ký tự",
                                btn_ref=self._srt_prev_btn)

    def _preview_stop(self):
        """Dừng phát thử giọng."""
        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            if hasattr(self, "_prev_tmp") and os.path.exists(self._prev_tmp):
                try: os.remove(self._prev_tmp)
                except: pass
        except Exception:
            pass
        self.prev_btn.config(text="▶  Thử Giọng", state="normal", bg="#f0fdf4")
        if hasattr(self, "_txt_prev_btn"):
            self._txt_prev_btn.config(text="🎧 Nghe Thử", state="normal", bg="#f0fdf4")
        if hasattr(self, "_srt_prev_btn"):
            self._srt_prev_btn.config(text="🎧 Nghe Thử", state="normal", bg="#f0fdf4")
        self._log("⏹ Đã dừng thử giọng", "info")

    def _check_gpu_and_warn(self):
        """Kiem tra GPU va hien canh bao neu cau hinh yeu."""
        try:
            import torch
            has_cuda = torch.cuda.is_available()

            if not has_cuda:
                # Kiem tra co GPU NVIDIA that su khong (qua nvcuda.dll)
                import os as _os
                _has_nvidia_hw = any(_os.path.exists(p) for p in [
                    r"C:\Windows\System32\nvcuda.dll",
                    r"C:\Windows\System32\nvml.dll",
                ])
                if _has_nvidia_hw:
                    title = "GPU NVIDIA Chưa Kích Hoạt CUDA"
                    msg = (
                        "Phát hiện GPU NVIDIA nhưng CUDA chưa hoạt động.\n\n"
                        "Nguyên nhân thường gặp:\n"
                        "  - PyTorch cài bản CPU thay vì bản CUDA\n"
                        "  - Driver NVIDIA chưa cập nhật\n\n"
                        "Vui lòng mở thư mục cài đặt MagicVoice và chạy lại CaiDat_MagicVoice.bat "
                        "(hoặc tải lại bộ cài đặt mới nhất và cài đè lên), hoặc liên hệ hỗ trợ: Zalo 0985 483 623"
                    )
                    color = P["orange"]
                    gpu_info = "GPU NVIDIA — CUDA chưa kích hoạt"
                else:
                    title = "Khong Co GPU NVIDIA"
                    msg = (
                        "May ban dang chay che do CPU.\n\n"
                        "Anh huong:\n"
                        "  - Tao voice rat cham (30-60s/cau)\n"
                        "  - Voice Clone co the khong on dinh\n\n"
                        "Goi y:\n"
                        "  - Dung Edge TTS cho van ban dai\n"
                        "  - Chi dung MagicVoice cho doan ngan\n"
                        "  - Upgrade GPU NVIDIA de dung tot hon"
                    )
                    color = P["red"]
                    gpu_info = "Khong co GPU NVIDIA"
                show_edge_btn = True
                show_repair_btn = _has_nvidia_hw
            else:
                vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
                gpu_name = torch.cuda.get_device_name(0)
                if vram >= 5.0:
                    return  # GPU tot, khong can canh bao
                title = "GPU VRAM Thap"
                msg = (
                    f"GPU: {gpu_name} ({vram:.1f}GB VRAM)\n\n"
                    "VRAM duoi 5GB co the gap su co!\n\n"
                    "De su dung on dinh:\n"
                    "  - Dung float16, Steps 4-8\n"
                    "  - Van ban toi da 500 ky tu/lan\n"
                    "  - Dung Edge TTS cho van ban dai\n\n"
                    "Neu bi loi CUDA out of memory:\n"
                    "  - Doi sang CPU trong Header app"
                )
                color = P["orange"]
                gpu_info = f"{gpu_name} ({vram:.1f}GB)"
                show_edge_btn = True
                show_repair_btn = False

            dlg = tk.Toplevel(self)
            dlg.title("Thong Tin Cau Hinh")
            dlg.geometry("460x300")
            dlg.configure(bg=P["white"])
            dlg.resizable(False, False)
            dlg.grab_set()
            dlg.lift()

            tk.Label(dlg, text="Canh Bao Cau Hinh",
                     font=(FN,12,"bold"), bg=P["gold"], fg="white",
                     pady=10).pack(fill="x")
            tk.Label(dlg, text=gpu_info,
                     font=(FN,10,"bold"), bg=P["white"],
                     fg=color, pady=4).pack()
            tk.Label(dlg, text=msg, font=(FN,9),
                     bg=P["white"], fg=P["text"],
                     justify="left").pack(padx=20, pady=4)

            btn_row = tk.Frame(dlg, bg=P["white"])
            btn_row.pack(pady=8)
            if show_edge_btn:
                tk.Button(btn_row, text="Doi sang Edge TTS",
                          command=lambda: (dlg.destroy(),
                                          self._set_tts_mode("edge")),
                          font=(FN,9), bg=P["blue"], fg="white",
                          relief="flat", cursor="hand2",
                          padx=12, pady=6).pack(side="left", padx=4)
            tk.Button(btn_row, text="Da hieu, tiep tuc",
                      command=dlg.destroy,
                      font=(FN,9), bg=P["purple"], fg="white",
                      relief="flat", cursor="hand2",
                      padx=12, pady=6).pack(side="left", padx=4)

        except Exception:
            pass

    def _log_startup_info(self):
        """Log thông tin voice library khi khởi động."""
        n = len(self.lib.profiles)
        self._log(f"📁 Voices file: {VOICES_FILE}", "info")
        if VOICES_FILE.exists():
            size = VOICES_FILE.stat().st_size
            self._log(f"✅ Đã load {n} voice ({size} bytes):", "ok")
            for i, vp in enumerate(self.lib.profiles):
                marker = " ◀ đang chọn" if i == self.sel_idx else ""
                self._log(f"   [{i}] {vp.name} ({vp.mode}){marker}", "info")
        else:
            self._log("⚠ Chưa có voices_library.json — sẽ tạo khi thêm voice", "warn")
        # Refresh clone voice tab và sidebar
        self._refresh_voices()
        self._update_sidebar()

    def _clear_srt_preview(self):
        """Xoa preview SRT khi paste kịch ban moi."""
        self.srt_entries = []
        self.srt_tree.delete(*self.srt_tree.get_children())
        if hasattr(self, "srt_cnt_lbl"):
            self.srt_cnt_lbl.config(text="0 câu")

    # ── Hệ thống đa phiên ──────────────────────────────────────────
    _SESSIONS_DIR = Path(__file__).parent / "sessions"

    def _save_session(self, srt_text: str, voice_name: str, out_dir: str):
        """Luu phien SRT vao sessions/."""
        import json as _json, time as _time
        try:
            self._SESSIONS_DIR.mkdir(exist_ok=True)
            ts = int(_time.time())
            data = {
                "tab": "srt",
                "timestamp": ts,
                "line_count": len([l for l in srt_text.splitlines() if l.strip()]),
                "srt_text":   srt_text,
                "voice_name": voice_name,
                "out_dir":    out_dir,
                "gap_ms":     self.gap_var.get(),
            }
            f = self._SESSIONS_DIR / f"session_{ts}.json"
            f.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as _e:
            print(f"[Session] Luu that bai: {_e}")

    def _save_batch_session(self):
        """Luu phien Hang Loat vao sessions/."""
        import json as _json, time as _time
        try:
            self._SESSIONS_DIR.mkdir(exist_ok=True)
            ts = int(_time.time())
            files = list(getattr(self, "_txt_files", []))
            data = {
                "tab": "batch",
                "timestamp": ts,
                "line_count": len(files),
                "files":   files,
                "in_dir":  self.in_dir.get(),
                "out_dir": self.out_dir_var.get(),
                "voice_name": self.lib.profiles[self.sel_idx].name if 0 <= self.sel_idx < len(self.lib.profiles) else "",
            }
            f = self._SESSIONS_DIR / f"session_{ts}.json"
            f.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as _e:
            print(f"[Session] Luu batch that bai: {_e}")

    def _recall_session(self, tab_filter=None):
        """Mo dialog chon phien de goi lai."""
        import json as _json, datetime as _dt
        import tkinter.ttk as _ttk
        self._SESSIONS_DIR.mkdir(exist_ok=True)
        files = sorted(self._SESSIONS_DIR.glob("session_*.json"), reverse=True)
        if tab_filter:
            filtered = []
            for f in files:
                try:
                    d = _json.loads(f.read_text(encoding="utf-8"))
                    if d.get("tab") == tab_filter:
                        filtered.append(f)
                except: pass
            files = filtered
        if not files:
            messagebox.showinfo("Không có phiên", "Chưa có phiên nào được lưu.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Chọn phiên")
        dlg.resizable(True, True)
        dlg.grab_set()
        dlg.configure(bg=P["white"])
        dlg.geometry("560x420")
        dlg.minsize(460, 340)

        tk.Label(dlg, text="📁  Chọn phiên để tải lại",
                 font=(FN, 11, "bold"), bg=P["white"], fg=P["purple"]
                 ).pack(anchor="w", padx=16, pady=(14, 8))

        # Buttons — đặt TRƯỚC treeview để pack bottom trước
        btn_row = tk.Frame(dlg, bg=P["white"])
        btn_row.pack(side="bottom", pady=12, fill="x", padx=14)

        # Treeview
        frm = tk.Frame(dlg, bg=P["white"]); frm.pack(fill="both", expand=True, padx=14, pady=(0,4))
        vsb = tk.Scrollbar(frm); vsb.pack(side="right", fill="y")
        cols = ("name", "task", "time")
        tree = _ttk.Treeview(frm, columns=cols, show="headings",
                              yscrollcommand=vsb.set, height=8)
        tree.heading("name", text="Phiên")
        tree.heading("task", text="Tác vụ")
        tree.heading("time", text="Thời gian")
        tree.column("name", width=210)
        tree.column("task", width=90, anchor="center")
        tree.column("time", width=170, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        vsb.config(command=tree.yview)

        session_map = {}
        for f in files:
            try:
                d = _json.loads(f.read_text(encoding="utf-8"))
                ts = d.get("timestamp", 0)
                dt_str = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                lc = d.get("line_count", 0)
                tab = d.get("tab", "srt")
                task_str = f"{lc} dòng" if tab == "srt" else f"{lc} file"
                iid = tree.insert("", "end", values=(f.name, task_str, dt_str))
                session_map[iid] = (f, d)
            except: pass
        if tree.get_children():
            tree.selection_set(tree.get_children()[0])

        def _do_load():
            sel = tree.selection()
            if not sel: return
            f, d = session_map[sel[0]]
            dlg.destroy()
            self._restore_session(d)

        def _do_excel():
            try:
                import openpyxl as _xl
                wb = _xl.Workbook(); ws = wb.active
                ws.title = "Phiên làm việc"
                ws.append(["Phiên", "Tab", "Tác vụ", "Thời gian", "Voice", "Output"])
                import datetime as _dt2
                for iid, (f, d) in session_map.items():
                    ts = d.get("timestamp", 0)
                    dt_s = _dt2.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    ws.append([f.name, d.get("tab",""), d.get("line_count",0), dt_s,
                                d.get("voice_name",""), d.get("out_dir","")])
                out_xl = self._SESSIONS_DIR / "sessions_export.xlsx"
                wb.save(out_xl)
                import subprocess; subprocess.Popen(["explorer", str(self._SESSIONS_DIR)])
                messagebox.showinfo("Xuất Excel", f"Đã lưu:\n{out_xl}")
            except ImportError:
                messagebox.showerror("Thiếu thư viện", "Cần cài openpyxl:\npip install openpyxl")
            except Exception as _xe:
                messagebox.showerror("Lỗi", str(_xe))

        tk.Button(btn_row, text="✓ Tải", command=_do_load,
                  font=(FN,10,"bold"), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", padx=20, pady=6
                  ).pack(side="left", padx=6)
        tk.Button(btn_row, text="📊 Xuất Excel", command=_do_excel,
                  font=(FN,9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=12, pady=6
                  ).pack(side="left", padx=6)
        tk.Button(btn_row, text="Hủy", command=dlg.destroy,
                  font=(FN,9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=12, pady=6
                  ).pack(side="left", padx=6)
        tree.bind("<Double-1>", lambda e: _do_load())

    def _restore_session(self, data: dict):
        """Phuc hoi trang thai tu session data."""
        tab = data.get("tab", "srt")
        # Chon voice
        vname = data.get("voice_name", "")
        for i, vp in enumerate(self.lib.profiles):
            if vp.name == vname:
                self.sel_idx = i
                # FIX v3.68 (theo anh Bac bao loi 2026-07-26): truoc day CHI
                # doi self.sel_idx, KHONG dong bo lai self.tts_mode (sidebar)
                # theo dung mode cua preset vua khoi phuc - neu dang o mode
                # "fast"/"edge" ma goi lai 1 phien MagicVoice (hoac nguoc
                # lai), sidebar/cac tab se hien SAI mode so voi giong vua
                # khoi phuc. Dong bo dung nhu pattern click() preset o
                # _update_sidebar().
                if vp.mode == "edge" and vp.instruct.startswith("edge:"):
                    if hasattr(self, "edge_voice_var"):
                        self.edge_voice_var.set(vp.instruct.replace("edge:","").strip())
                    self._set_tts_mode("edge")
                elif vp.mode == "fast" and vp.instruct.startswith("fast:"):
                    if hasattr(self, "fast_voice_var"):
                        self.fast_voice_var.set(vp.instruct.replace("fast:","").strip())
                    self._set_tts_mode("fast")
                else:
                    self._set_tts_mode("omnivoice")
                self._update_sidebar()
                if hasattr(self, "_refresh_srt_voices"):
                    self._refresh_srt_voices()
                break
        # Dat output dir
        if data.get("out_dir"):
            self.out_dir_var.set(data["out_dir"])

        if tab == "srt":
            # Chuyen sang tab SRT
            self._switch_tab("srt")
            # Dien lai SRT editor
            srt_text = data.get("srt_text", "")
            self.srt_editor.delete("1.0", "end")
            self.srt_editor.insert("1.0", srt_text)
            if "gap_ms" in data:
                self.gap_var.set(data["gap_ms"])
            # Parse lai
            txt = srt_text.strip()
            if "-->" in txt:
                self._load_srt_content(txt, "phien cu")
            elif txt:
                self._text_to_srt_entries(txt)
            self._st("✅ Đã gọi lại phiên SRT — nhấn Tạo để tạo voice", P["green"])

        elif tab == "batch":
            # Chuyen sang tab Hang Loat
            self._switch_tab("batch")
            files = data.get("files", [])
            if data.get("in_dir"):
                self.in_dir.set(data["in_dir"])
            # Load lai file list
            if hasattr(self, "_txt_files"):
                self._txt_files = [f for f in files if Path(f).exists()]
                self.batch_lb.delete(0, "end")
                for f in self._txt_files:
                    sz = Path(f).stat().st_size / 1024
                    ext = Path(f).suffix.upper().replace(".", "")
                    self.batch_lb.insert("end", f"  [{ext}]  {Path(f).name:<42} {sz:.1f} KB")
                self.batch_cnt.config(text=f"{len(self._txt_files)} file")
            self._st("✅ Đã gọi lại phiên Hàng Loạt — nhấn Chạy để tạo voice", P["green"])

    # ─────── CLOSE & CONFIG ────────────────────────────────────────
    def _done_notify_srt(self, out_path: str, parts_dir: str):
        """Thong bao SRT hoan thanh - 1 popup duy nhat, khong nháy."""
        # Tranh tao nhieu popup neu goi nhieu lan
        if getattr(self, "_srt_notify_shown", False):
            return
        self._srt_notify_shown = True

        try:
            dlg = tk.Toplevel(self)
            dlg.title("✅ Tạo SRT hoàn thành!")
            dlg.configure(bg=P["white"])
            dlg.resizable(False, False)
            dlg.geometry("420x220")
            x = (dlg.winfo_screenwidth()-420)//2
            y = (dlg.winfo_screenheight()-220)//2
            dlg.geometry(f"420x220+{x}+{y}")
            dlg.lift()
            dlg.focus_force()
            # KHONG grab_set() - tranh nháy/focus storm

            tk.Label(dlg, text="✅  Tạo SRT hoàn thành!",
                     font=(FN,13,"bold"), bg=P["white"], fg=P["purple"]).pack(pady=(20,6))

            info = tk.Frame(dlg, bg=P["sidebar"], padx=12, pady=8)
            info.pack(fill="x", padx=16, pady=(0,12))
            tk.Label(info, text=f"🎵  {Path(out_path).name}",
                     font=(FN,9), bg=P["sidebar"], fg=P["label"]).pack(anchor="w")
            tk.Label(info, text=f"📁  {Path(parts_dir).name}/",
                     font=(FN,9), bg=P["sidebar"], fg=P["purple"]).pack(anchor="w", pady=(4,0))

            btn_row = tk.Frame(dlg, bg=P["white"]); btn_row.pack()
            def _open_and_close():
                try:
                    # explorer /select, <path> -> mo va trỏ chuột vao file
                    if WIN:
                        import subprocess as _sp
                        _sp.Popen(["explorer", "/select,", str(Path(out_path))])
                    else:
                        os.startfile(str(Path(out_path).parent))
                except Exception:
                    try: os.startfile(str(Path(out_path).parent))
                    except Exception: pass
                dlg.destroy()
                setattr(self, "_srt_notify_shown", False)
            tk.Button(btn_row, text="📂 Mở thư mục output",
                      command=_open_and_close,
                      font=(FN,10,"bold"), bg=P["purple"], fg="white",
                      relief="flat", cursor="hand2", padx=16, pady=8).pack(side="left", padx=6)
            tk.Button(btn_row, text="Đóng",
                      command=lambda: [dlg.destroy(), setattr(self,"_srt_notify_shown",False)],
                      font=(FN,10), bg=P["hover"], fg=P["label"],
                      relief="flat", cursor="hand2", padx=16, pady=8).pack(side="left", padx=6)
        except Exception:
            self._srt_notify_shown = False

    def _done_notify(self, out_path: str, duration_s: int = 0, parts_dir: str = None):
        """Thông báo hoàn thành + nút mở thư mục."""
        name = Path(out_path).name
        folder = str(Path(out_path).parent)
        file_ok = Path(out_path).exists()
        size_kb = int(Path(out_path).stat().st_size / 1024) if file_ok else 0

        dlg = tk.Toplevel(self)
        dlg.title("✅ Hoàn thành!" if file_ok else "⚠ Lỗi lưu file")
        dlg.geometry("420x200")
        dlg.configure(bg=P["white"])
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

        if not file_ok:
            tk.Label(dlg, text="⚠  Không tìm thấy file output!",
                     font=(FN,12,"bold"), bg="#fff7ed", fg="#c2410c",
                     pady=10).pack(fill="x")
            tk.Label(dlg, text="ffmpeg chưa cài đủ — chạy lại CaiDat_MagicVoice.bat (trong thư mục cài đặt) để sửa.",
                     font=(FN,9), bg=P["white"], fg=P["sub"],
                     wraplength=380, pady=4).pack()
            tk.Button(dlg, text="Đóng", command=dlg.destroy,
                      font=(FN,10), bg=P["hover"], fg=P["label"],
                      relief="flat", cursor="hand2", padx=14, pady=6).pack(pady=12)
            return

        tk.Label(dlg, text="✅  Tạo voice thành công!",
                 font=(FN,12,"bold"), bg="#f0fdf4", fg="#16a34a",
                 pady=10).pack(fill="x")

        tk.Label(dlg, text=f"📄 {name}",
                 font=(FN,9,"bold"), bg=P["white"],
                 fg=P["text"], pady=4).pack()
        tk.Label(dlg, text=f"📁 {folder}",
                 font=(FN,8), bg=P["white"],
                 fg=P["dim"], wraplength=380).pack()
        if size_kb > 0:
            tk.Label(dlg, text=f"💾 {size_kb} KB",
                     font=(FN,8), bg=P["white"], fg=P["dim"]).pack()

        btn_row = tk.Frame(dlg, bg=P["white"]); btn_row.pack(pady=12)
        def _open_and_close():
            try:
                if WIN:
                    import subprocess as _sp
                    # /select, → tro chuot vao file vua tao
                    _sp.Popen(["explorer", "/select,", str(Path(out_path))])
                else:
                    os.startfile(folder)
            except Exception:
                try: os.startfile(folder)
                except Exception: pass
            dlg.destroy()
        tk.Button(btn_row, text="📂 Mở thư mục",
                  command=_open_and_close,
                  font=(FN,10,"bold"), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", padx=14, pady=6
                  ).pack(side="left", padx=6)
        tk.Button(btn_row, text="Đóng",
                  command=dlg.destroy,
                  font=(FN,9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=10, pady=6
                  ).pack(side="left")

    # ════════════════════════════════════════════════════════════
    # v3.22: SINGLE-SESSION HEARTBEAT
    # ════════════════════════════════════════════════════════════
    def _start_heartbeat_thread(self):
        """Bat dau thread kiem tra session 2 phut/lan.
        Neu server bao kicked -> tool tu logout + dong app.
        Grace 3 lan fail lien tiep truoc khi kick (tranh kick oan khi mang yeu)."""
        if not self._username:
            return  # Khong co username -> bo qua
        import threading
        def _hb_loop():
            import time
            HEARTBEAT_INTERVAL = 120  # 2 phut
            MAX_FAIL = 3              # cho phep 3 lan fail truoc khi kick
            # FIX v3.66 (bao mat 2026-07-24): nguong mat ket noi LIEN TUC toi
            # server truoc khi bat buoc dong app - xem ghi chu day du o
            # __init__ (_heartbeat_offline_since). 8 tieng theo yeu cau anh
            # Bac: du de khong lam phien khach mat mang tam thoi trong ngay
            # lam viec, nhung khong de "chan mang vinh vien" chay app mai mai.
            OFFLINE_TOO_LONG_SEC = 8 * 3600
            while not self._heartbeat_stop:
                # Doi 2 phut moi lan check (chia nho de stop nhanh khi close app)
                for _ in range(HEARTBEAT_INTERVAL):
                    if self._heartbeat_stop:
                        return
                    time.sleep(1)
                if self._heartbeat_stop:
                    return
                _reachable = False
                try:
                    from auth_manager import check_session_alive, get_session_token
                    token = get_session_token(self._username)
                    if not token:
                        # Khong co token (account legacy hoac da bi xoa cache) -> bo qua
                        continue
                    status, msg = check_session_alive(self._username, token, timeout=8)
                    if status == "kicked":
                        # Bi day ra -> kick UI (chay tren main thread)
                        self.after(0, lambda m=msg: self._kick_user_out(m))
                        return
                    elif status == "error":
                        # Loi mang/server -> tang counter, KHONG kick ngay
                        self._heartbeat_fail_count += 1
                        if self._heartbeat_fail_count >= MAX_FAIL:
                            try:
                                self.after(0, lambda: self._log(
                                    f"⚠ Khong ket noi server qua {MAX_FAIL*2} phut", "warn"))
                            except Exception:
                                pass
                            self._heartbeat_fail_count = 0  # reset de khong spam
                    else:
                        # OK -> reset counter
                        self._heartbeat_fail_count = 0
                        _reachable = True
                except Exception:
                    # Loi bat ngo (vd import that bai, DNS fail) -> KHONG kick,
                    # nhung van tinh la "khong lien lac duoc" cho bo dem thoi
                    # gian offline lien tuc ben duoi.
                    pass

                if _reachable:
                    self._heartbeat_offline_since = None
                    self._heartbeat_offline_prompted = False
                else:
                    if self._heartbeat_offline_since is None:
                        self._heartbeat_offline_since = time.time()
                    _offline_dur = time.time() - self._heartbeat_offline_since
                    if _offline_dur >= OFFLINE_TOO_LONG_SEC and not self._heartbeat_offline_prompted:
                        self._heartbeat_offline_prompted = True
                        self.after(0, self._show_offline_too_long_warning)
        t = threading.Thread(target=_hb_loop, daemon=True)
        t.start()

    def _show_offline_too_long_warning(self):
        """FIX v3.66 (bao mat 2026-07-24): hien khi mat ket noi LIEN TUC toi
        server qua 8 tieng - khong tu dong dong app ngay (tranh dong oan khi
        khach dang lam viec that su, chi la mang cham/server Render dang
        khoi dong lai). Hien canh bao ro rang + dem nguoc; neu khach KHONG
        bam nut trong vai phut (chung to khong ai dang ngoi may that su theo
        doi) thi tu dong dong app - khach can dung se mo lai + dang nhap lai
        (luc do se goi lai server that su)."""
        if getattr(self, "_offline_warn_win", None) is not None:
            return  # Da dang hien, khong tao trung
        GRACE_SEC = 300  # 5 phut de khach phan hoi truoc khi tu dong dong

        win = tk.Toplevel(self)
        self._offline_warn_win = win
        win.title("Mất kết nối kéo dài")
        win.geometry("420x220")
        win.configure(bg="#1a1d2e")
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", lambda: None)  # bat khach bam nut, khong cho X

        tk.Label(win, text="⚠ Mất kết nối tới server đã hơn 8 giờ",
                 font=("Segoe UI", 11, "bold"), bg="#1a1d2e", fg="#fbbf24",
                 wraplength=380, justify="left").pack(padx=16, pady=(16, 6), anchor="w")
        tk.Label(win,
                 text="Vui lòng kiểm tra lại kết nối mạng.\n"
                      "Nếu bạn không phản hồi, ứng dụng sẽ tự đóng để đảm bảo\n"
                      "phiên đăng nhập được xác thực lại đúng quy định.",
                 font=("Segoe UI", 9), bg="#1a1d2e", fg="#c8cae0",
                 wraplength=380, justify="left").pack(padx=16, pady=(0, 10), anchor="w")
        cd_var = tk.StringVar()
        tk.Label(win, textvariable=cd_var, font=("Segoe UI", 9), bg="#1a1d2e", fg="#ef4444").pack(anchor="w", padx=16)

        def _dismiss():
            self._heartbeat_offline_since = None
            self._heartbeat_offline_prompted = False
            self._offline_warn_win = None
            try: win.destroy()
            except Exception: pass

        tk.Button(win, text="Tôi vẫn ở đây, tiếp tục dùng", command=_dismiss,
                  bg="#4f72f5", fg="white", relief="flat", padx=12, pady=6,
                  cursor="hand2").pack(padx=16, pady=(10, 16), anchor="w")

        _deadline = time.time() + GRACE_SEC
        def _tick():
            if getattr(self, "_offline_warn_win", None) is not win:
                return  # da dismiss hoac app dang dong
            remain = int(_deadline - time.time())
            if remain <= 0:
                self._offline_warn_win = None
                try: win.destroy()
                except Exception: pass
                self._on_close()
                return
            cd_var.set(f"Tự động đóng sau {remain}s nếu không phản hồi...")
            win.after(1000, _tick)
        _tick()

    def _kick_user_out(self, msg: str):
        """Bi server day ra do may khac da login. Logout + dong app."""
        self._heartbeat_stop = True
        # Xoa session_token + offline cache de buoc login lai
        try:
            from auth_manager import clear_session_token, clear_offline_cache
            clear_session_token()
            clear_offline_cache()
        except Exception:
            pass
        # Hien popup va dong app
        try:
            messagebox.showwarning(
                "Phiên đăng nhập đã kết thúc",
                f"Tài khoản '{self._username}' đã được đăng nhập trên thiết bị khác.\n\n"
                f"Lý do: {msg}\n\n"
                "Bạn cần đăng nhập lại để tiếp tục sử dụng.\n"
                "Một tài khoản chỉ được dùng trên một máy tại một thời điểm.",
                parent=self
            )
        except Exception:
            pass
        # Dong app
        try:
            self.destroy()
        except Exception:
            import sys; sys.exit(0)

    def _on_close(self):
        """Lưu cấu hình trước khi đóng."""
        # MOI: luu cau hinh naming TOAN CUC (khong con la batch)
        _name_cfg = {}
        try:
            _name_cfg = {
                "out_name_mode": self.out_name_mode.get(),
                "out_prefix":    self.out_prefix_var.get(),
                "out_start":     int(self.out_start_var.get()),
                "out_pad":       int(self.out_pad_var.get()),
                "out_ask_name":  bool(self.out_ask_name_var.get()),
            }
        except Exception:
            pass
        save_config({
            "device":           self.device_var.get(),
            "dtype":            self.dtype_var.get(),
            "steps":            self.steps_var.get(),
            "preset_detected":  self._cfg.get("preset_detected", False),
            "out_dir":          self.out_dir_var.get(),
            "fmt":              self.fmt_var.get(),
            "auto_load":        True,
            "model_cached":     self.model_loaded or self._cfg.get("model_cached", False),
            "post_process":     self.post_proc_var.get(),
            "narrator_mode":    self.narrator_var.get(),
            "script_proc":      self.script_proc_var.get(),
            "text_process":     self.text_proc_var.get(),
            "srt_timeline_export": self.srt_timeline_var.get(),
            "sel_voice_idx":    self.sel_idx,
            "sel_voice_name":   self.lib.profiles[self.sel_idx].name
                                if self.sel_idx < len(self.lib.profiles) else "",
            **_name_cfg,
        })
        self.lib.save()  # Đảm bảo lưu voices trước khi đóng
        # v3.22: Stop heartbeat thread truoc khi destroy
        self._heartbeat_stop = True
        self.destroy()

    def _on_model_cfg_changed(self, *_):
        """Auto-save khi user tu tay doi dtype hoac steps."""
        self._cfg.update({
            "dtype": self.dtype_var.get(),
            "steps": self.steps_var.get(),
            "preset_detected": True,
        })
        save_config(self._cfg)

    def _on_device_changed(self, *_):
        """Trace callback: khi doi device dropdown → tu dong reload model neu can."""
        if Backend._loaded_device is None:
            return  # Model chua load lan nao, khong can reload
        new_device = self.device_var.get()
        if not new_device or new_device == Backend._loaded_device:
            return  # Khong doi gi
        if self.is_running:
            self._log(f"⚠ Device → {new_device}: se ap dung sau khi tao xong", "warn")
            return
        self._log(f"🔄 Device {Backend._loaded_device} → {new_device}: reload model…", "info")
        self._load_model()

    def _auto_load_model(self):
        """Tự động tải model khi khởi động (đã cache)."""
        self._log("🔄 Tự động tải model (đã cache sẵn)…", "info")
        self._load_model()

    # ─────── MODEL ─────────────────────────────────────────────────
    def _find_local_model_snapshot(self):
        """Tim snapshot OmniVoice trong HF cache — tranh contact Hub khi da co local."""
        import shutil as _sh, json as _json
        try:
            _cache = Path.home() / ".cache" / "huggingface" / "hub" / \
                     "models--k2-fsa--OmniVoice" / "snapshots"
            if not _cache.exists():
                return None
            best_full = None
            best_part = None
            for snap in _cache.iterdir():
                if not snap.is_dir():
                    continue
                has_w = (snap / "model.safetensors").exists()
                has_c = (snap / "config.json").exists()
                if has_w and has_c:
                    best_full = snap
                    break
                elif has_w:
                    best_part = snap
            chosen = best_full or best_part
            if chosen is None:
                return None
            if not (chosen / "config.json").exists():
                for snap2 in _cache.iterdir():
                    if snap2 == chosen or not snap2.is_dir():
                        continue
                    if (snap2 / "config.json").exists():
                        try:
                            for _jf in snap2.glob("*.json"):
                                _dst = chosen / _jf.name
                                if not _dst.exists():
                                    _sh.copy2(str(_jf), str(_dst))
                        except Exception:
                            pass
                        break
            # Validate config.json — neu rong hoac thieu model_type → tu va lai
            _cfg_path = chosen / "config.json"
            if _cfg_path.exists():
                try:
                    _cfg_data = _json.loads(_cfg_path.read_text("utf-8"))
                    if not _cfg_data.get("model_type"):
                        _cfg_data["model_type"] = "omnivoice"
                        _cfg_path.write_text(
                            _json.dumps(_cfg_data, ensure_ascii=False, indent=2), "utf-8")
                        self._log("⚠ config.json thiếu model_type — tự vá → omnivoice", "warn")
                except Exception:
                    # File bi hong hoan toan → viet lai config toi thieu
                    try:
                        _cfg_path.write_text(
                            _json.dumps({"model_type": "omnivoice"}, indent=2), "utf-8")
                        self._log("⚠ config.json hỏng — đã ghi lại tối thiểu", "warn")
                    except Exception:
                        pass
            return str(chosen)
        except Exception:
            return None

    def _load_model(self):
        # Reset để cho phép tải lại
        Backend._model = None
        self.load_btn.config(state="disabled", text="⏳ Đang tải…", bg=P["gold"])
        self.model_dot.config(fg=P["gold"])
        self.model_lbl.config(text=" Đang tải…", fg=P["gold"])
        self._log("⏳ Bắt đầu tải MagicVoice (~4GB lần đầu, đã cache = nhanh)…", "info")
        self._load_timer_active = True
        self._load_timer_secs = 0
        self._tick_load_timer()
        threading.Thread(target=self._do_load, daemon=True).start()

    def _tick_load_timer(self):
        if not getattr(self, "_load_timer_active", False):
            return
        m, s = divmod(self._load_timer_secs, 60)
        self.after(0, lambda mm=m, ss=s: self.model_lbl.config(
            text=f" Đang tải… ({mm:02d}:{ss:02d})", fg=P["gold"]))
        self._load_timer_secs += 1
        self.after(1000, self._tick_load_timer)

    def _do_load(self):
        try:
            import torch, traceback
            device   = self.device_var.get()
            dtype_str= self.dtype_var.get()
            self._log(f"   Device: {device}  |  Dtype: {dtype_str}", "info")

            # Kiem tra model da cache chua — neu chua: tu dong tai
            if not _model_is_cached():
                self._log("⬇ MagicVoice Engine chưa có — đang tải...", "info")
                self.after(0, lambda: self.model_lbl.config(
                    text=" Đang tải MagicVoice Engine...", fg=P["gold"]))
                # Thu 1: snapshot_download tu HuggingFace (qua mirror hf-mirror.com)
                _dl_ok = False
                import os as _os_dl
                _os_dl.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                try:
                    self._log("   Thử máy chủ tải MagicVoice Engine (hf-mirror.com)...", "info")
                    from huggingface_hub import snapshot_download as _snd
                    _snd("k2-fsa/OmniVoice")
                    _dl_ok = True
                    self._log("   ✓ Tải MagicVoice Engine xong", "ok")
                except Exception as _hf_err:
                    self._log(f"   ✗ Tải thất bại: {_hf_err}", "warn")
                # Thu 2: fallback Google Drive neu HuggingFace loi
                if not _dl_ok:
                    self._log("   Fallback → Google Drive...", "info")
                    self.after(0, lambda: self.model_lbl.config(
                        text=" Tải từ Drive...", fg=P["gold"]))
                    try:
                        _download_model_from_drive(
                            log_fn=lambda m, lv="info": self._log(f"   {m}", lv),
                            progress_fn=lambda pct, msg="": self.after(0, lambda p=pct, t=msg:
                                self.model_lbl.config(text=f" Drive {p}% {t}", fg=P["gold"]))
                        )
                        self._log("   ✓ Tải xong từ Google Drive", "ok")
                    except Exception as _dr_err:
                        self._log(f"   ✗ Drive thất bại: {_dr_err}", "err")
                        raise RuntimeError(
                            f"Không tải được model!\n\n"
                            f"HuggingFace: {_hf_err}\nGoogle Drive: {_dr_err}\n\n"
                            "Kiểm tra internet rồi nhấn Thử lại."
                        )

            from omnivoice import OmniVoice as MagicVoice
            dt = {"float32": torch.float32,
                  "float16": torch.float16,
                  "bfloat16": torch.bfloat16}[dtype_str]
            import os as _os
            # Xoa offline flags truoc — tranh block hub khi can resume/download
            for _ev in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
                _os.environ.pop(_ev, None)

            local_path = self._find_local_model_snapshot()
            if local_path:
                self._log(f"   Load model tu cache local (khong can mang)...", "info")
                Backend._model = MagicVoice.from_pretrained(
                    local_path, device_map=device, dtype=dt)
            else:
                self._log("   Cache trong — tai model qua hf-mirror.com (~4GB)...", "info")
                self.after(0, lambda: self.model_lbl.config(
                    text=" Dang tai model (~4GB)…", fg=P["gold"]))
                _os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                _dl_ok = False
                try:
                    from huggingface_hub import snapshot_download as _snd
                    _snd("k2-fsa/OmniVoice")
                    _dl_ok = True
                    self._log("✓ Tai xong — dang load...", "info")
                except Exception as _dle:
                    self._log(f"   ✗ HuggingFace that bai: {_dle}", "warn")
                if not _dl_ok:
                    self._log("   Fallback → Google Drive...", "info")
                    self.after(0, lambda: self.model_lbl.config(
                        text=" Tai tu Drive...", fg=P["gold"]))
                    try:
                        _download_model_from_drive(
                            log_fn=lambda m, lv="info": self._log(f"   {m}", lv),
                            progress_fn=lambda pct, msg="": self.after(0, lambda p=pct, t=msg:
                                self.model_lbl.config(text=f" Drive {p}% {t}", fg=P["gold"]))
                        )
                        self._log("✓ Tai xong tu Google Drive — load model...", "info")
                    except Exception as _dre:
                        raise RuntimeError(
                            f"Khong tai duoc model!\n\nGoogle Drive: {_dre}\n\n"
                            "Kiem tra internet roi nhan Thu lai.")
                local_path2 = self._find_local_model_snapshot()
                if local_path2:
                    Backend._model = MagicVoice.from_pretrained(
                        local_path2, device_map=device, dtype=dt)
                else:
                    Backend._model = MagicVoice.from_pretrained(
                        "k2-fsa/OmniVoice", device_map=device, dtype=dt)
            Backend._loaded_device = device
            self.model_loaded = True
            # Clear offline env sau load — cho OmniVoice download Whisper khi Clone
            for _ev in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
                _os.environ.pop(_ev, None)
            self._log("✅ Model san sang!", "ok")
            self._load_timer_active = False
            # Đánh dấu đã cache để lần sau tự động tải
            self._cfg["model_cached"] = True
            save_config({**self._cfg,
                "device": self.device_var.get(),
                "dtype":  self.dtype_var.get(),
                "model_cached": True,
            })
            self.after(0, self.model_dot.config,  {"fg": P["green"]})
            self.after(0, self.model_lbl.config,  {"text": " Model sẵn sàng", "fg": P["green"]})
            self.after(0, self.load_btn.config,
                       {"text": "✓ Đã tải", "bg": P["green"], "state": "disabled"})
        except Exception as e:
            self._load_timer_active = False
            import traceback
            detail = traceback.format_exc()
            self._log(f"❌ Lỗi: {e}", "err")
            self._log(detail[-600:], "err")
            self.after(0, self.model_dot.config, {"fg": P["red"]})
            self.after(0, self.model_lbl.config, {"text": " Lỗi tải", "fg": P["red"]})
            self.after(0, self.load_btn.config,
                       {"text": "↺ Thử lại", "bg": P["purple"], "state": "normal"})
            s = str(e).lower()
            _is_cache_miss = ("localentrynotfound" in type(e).__name__.lower() or
                              ("local cache" in s and "cannot find" in s))
            # FIX v3.65 (32): "Unrecognized configuration class <NoneType>"
            # nghia la config.json trong cache model bi hong/khong doc duoc
            # dung (thuong do model download bi dut giua chung lan truoc) -
            # thay vi bat khach tu tay xoa cache + chay lai .bat, TU DONG
            # xoa cache hong + tai lai model NGAY (1 lan) - chuyen nghiep hon,
            # it truong hop can can thiep tay.
            _is_bad_config = ("unrecognized configuration class" in s and "nonetype" in s)
            if _is_bad_config and not getattr(self, "_model_cfg_autofix_done", False):
                self._model_cfg_autofix_done = True
                try:
                    import shutil as _sh2, pathlib as _pl2
                    _bad_cache = _pl2.Path.home() / ".cache" / "huggingface" / "hub" / "models--k2-fsa--OmniVoice"
                    if _bad_cache.exists():
                        _sh2.rmtree(_bad_cache, ignore_errors=True)
                        self._log("⚠ config.json model bị hỏng (tải dở trước đó) — đã tự xoá cache, đang tải lại...", "warn")
                    self.after(0, self._load_model)
                    return
                except Exception as _fix_err:
                    self._log(f"Tu dong sua cache model that bai: {_fix_err}", "warn")
            # Loi mang: chi can retry, khong can sua moi truong
            # Phai loai tru LocalEntryNotFoundError (co chua "connect" trong message nhung khong phai loi mang)
            if not _is_cache_miss and ("getaddrinfo" in s or any(x in s for x in ["connect","timeout","network","ssl","name resolution"])):
                self.after(200, lambda: messagebox.showerror("Lỗi mạng",
                    "Không kết nối được HuggingFace.\n\nKiểm tra internet rồi nhấn ↺ Thử lại."))
            elif _is_bad_config:
                self.after(200, lambda err=str(e): messagebox.showerror("Lỗi tải model",
                    f"Đã tự xoá cache và tải lại nhưng vẫn lỗi:\n{err[:300]}\n\n"
                    "Vui lòng:\n"
                    "1. Kiểm tra kết nối internet ổn định rồi bấm Thử lại\n"
                    "2. Nếu vẫn lỗi: chạy DonMoiTruong_MagicVoice.bat rồi cài lại\n"
                    "3. Liên hệ hỗ trợ: Zalo 0985 483 623"))
            else:
                self.after(200, lambda err=str(e): messagebox.showerror("Lỗi tải model",
                    f"Lỗi tải model:\n{err[:300]}\n\n"
                    "Vui lòng:\n"
                    "1. Mở thư mục cài đặt MagicVoice, chạy lại CaiDat_MagicVoice.bat\n"
                    "   (hoặc tải lại bộ cài đặt MagicVoice_Setup mới nhất và cài đè lên)\n"
                    "2. Nếu vẫn lỗi: chạy DonMoiTruong_MagicVoice.bat rồi cài lại\n"
                    "3. Liên hệ hỗ trợ: Zalo 0985 483 623"))

    # ─────── CREATE (dispatch) ─────────────────────────────────────
    def _create(self):
        if not self.model_loaded:
            messagebox.showwarning("Chưa tải model","Nhấn '⬇ Tải Model' trước!"); return
        if self.is_running:
            # MOI: hien ten tab dang chay de user khong bi nham
            _tab_label = {"text": "📄 Văn Bản", "srt": "🎞 Phụ Đề SRT",
                          "batch": "📁 Hàng Loạt"}.get(self._running_tab or "", "?")
            messagebox.showinfo("Đang chạy",
                f"Tab {_tab_label} đang xử lý. Vui lòng đợi hoàn thành "
                "hoặc bấm ⏹ để hủy trước khi bắt đầu tác vụ mới.\n\n"
                "Bạn vẫn có thể chuyển sang tab khác để xem/sửa dữ liệu trong khi chờ.")
            return
        tab=next(k for k,f in self.tab_frames.items() if f.winfo_ismapped())
        # MOI: log tab bat dau de user biet ro dang lam gi
        _tab_names = {"text": "📄 Văn Bản", "srt": "🎞 Phụ Đề SRT",
                      "batch": "📁 Hàng Loạt", "clone": "🎤 Clone Voice",
                      "script": "✍ Kịch Bản"}
        if tab in ("text","srt","batch"):
            self._log(f"▶ Bắt đầu tác vụ tại tab {_tab_names.get(tab, tab)}", "info")
        if tab=="text":   self._do_text()
        elif tab=="srt":  self._do_srt()
        elif tab=="batch":self._do_batch()
        elif tab=="clone":messagebox.showinfo("Thông báo",
            "Hãy chuyển sang tab Văn Bản / SRT / Hàng Loạt để tạo giọng với voice đã chọn!")
        elif tab=="script":messagebox.showinfo("Thông báo",
            "Tab Kịch Bản chỉ xử lý nội dung. Dùng nút 'Gửi sang Văn Bản' hoặc 'Gửi sang SRT' rồi bấm Tạo.")

    def _vkw(self):
        """Lay kwargs cho Backend.gen() tu voice profile dang chon."""
        if self.sel_idx < 0 or self.sel_idx >= len(self.lib.profiles):
            return {}
        vp = self.lib.profiles[self.sel_idx]
        kw = {}
        if vp.mode == "clone":
            ref = vp.ref_audio
            # Neu path cu khong ton tai → tim lai trong clone_refs hien tai
            if ref and not os.path.isfile(ref):
                _alt = Path(_SCRIPT_DIR) / "clone_refs" / Path(ref).name
                if _alt.exists():
                    ref = str(_alt)
            if not ref or not os.path.isfile(ref):
                raise ValueError(
                    f"File audio mau chua duoc cai dat tren may nay!\n\n"
                    f"Voice '{vp.name}' can file audio: {Path(vp.ref_audio).name}\n\n"
                    f"Cach khac phuc:\n"
                    f"  1. Tab Clone Voice → Sua voice '{vp.name}'\n"
                    f"  2. Chon lai file audio mau (mp3/wav)\n"
                    f"  3. Hoac ghi am moi roi luu voice")
            # Trim ref_audio 10-30s toi uu cho clone
            kw["ref_audio"] = self._prepare_ref_audio(ref)
            # === SUA: KHONG auto-transcribe, KHONG truyen ref_text mac dinh ===
            # Ly do: Whisper local (faster-whisper/openai-whisper) transcribe sai
            # tieng Viet -> text sai bi truyen vao model -> model lech alignment
            # giua am thanh va text -> doc lung tung, lap tu, nuot tu.
            #
            # OmniVoice CHINH NO da co Whisper noi bo va xu ly tot hon.
            # Doc OmniVoice (github.com/k2-fsa/OmniVoice):
            #   "If you don't want to input ref_text manually, you can directly
            #    omit the ref_text. The model will use Whisper ASR to auto-
            #    transcribe it."
            #
            # -> OMIT ref_text mac dinh = tra ve hanh vi cu (chi can ref_audio)
            #    da chay on dinh truoc khi them tinh nang auto-transcribe.
            #
            # Neu user MUON dung ref_text thu cong (nhap chinh xac cau audio
            # dang doc) thi van ho tro: bo comment 2 dong duoi va dam bao
            # vp.ref_text khong phai rac tu auto-transcribe cu.
            #
            # if vp.ref_text and vp.ref_text.strip():
            #     kw["ref_text"] = vp.ref_text
            pass  # clone mode silently
        elif vp.mode == "design":
            if not vp.instruct:
                raise ValueError("Voice Design thiếu mô tả!")
            kw["instruct"] = _normalize_instruct(vp.instruct)
        return kw

    # ── MOI: Auto-transcribe ref audio voi fallback chain ────────────
    # Cache transcribed text de khong transcribe lai cung 1 file
    _transcribe_cache = {}

    def _auto_transcribe_ref(self, audio_path: str, vp=None) -> str:
        """Transcribe ref_audio thanh text. Tra "" neu khong xu ly duoc.
        Thu lan luot:
          1. Cache da transcribe truoc do
          2. faster-whisper (nhe, nhanh - ~80MB)
          3. openai-whisper (chinh hang - ~140MB)
          4. transformers + WhisperForConditionalGeneration
        Tu dong save vao vp.ref_text de lan sau khong phai transcribe."""
        # 1. Cache check
        cache_key = str(audio_path)
        if cache_key in self._transcribe_cache:
            cached = self._transcribe_cache[cache_key]
            if vp and not vp.ref_text:
                vp.ref_text = cached
                try: self.lib.save()
                except Exception: pass
            return cached

        # 2. Thu faster-whisper (uu tien - nhe va nhanh)
        # Neu chua cai -> tu dong cai (chi 1 lan)
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            self._log("  ⏳ Lan dau dung clone voice - dang cai faster-whisper...", "info")
            try:
                import subprocess as _sp_w, sys as _sys_w
                _flags_w = 0x08000000 if os.name == "nt" else 0
                _sp_w.run([_sys_w.executable, "-m", "pip", "install",
                          "faster-whisper", "--quiet", "--no-cache-dir"],
                         creationflags=_flags_w, timeout=180)
                from faster_whisper import WhisperModel  # thu import lai
                self._log("  ✓ Cai faster-whisper thanh cong", "ok")
            except Exception as _e:
                self._log(f"  ⚠ Khong cai duoc faster-whisper: {str(_e)[:80]}", "warn")
                WhisperModel = None
        try:
            if WhisperModel is None:
                raise ImportError("WhisperModel not available")
            self._log("  ⏳ Đang nhận diện ref_audio (faster-whisper medium)...", "info")
            # FIX v3.18: doi tu "small" (244MB) -> "medium" (~1.5GB)
            # de transcribe CHINH XAC hon, tranh sai chu lam clone bi nghen.
            # User chi tai 1 lan, sau do cache.
            # beam_size=5 thay 1 -> chinh xac hon, cham hon ~30%
            model = WhisperModel("medium", device="cpu", compute_type="int8")
            segments, info = model.transcribe(
                audio_path,
                beam_size=5,
                vad_filter=True,        # Loc bo doan im lang
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            if text:
                self._log(f"  📝 Detected language: {info.language} (prob={info.language_probability:.2f})", "info")
                self._transcribe_cache[cache_key] = text
                if vp:
                    vp.ref_text = text
                    try: self.lib.save()
                    except Exception: pass
                return text
        except ImportError:
            pass  # Khong co thu vien -> thu cach khac
        except Exception as _e:
            self._log(f"  ⚠ faster-whisper loi: {str(_e)[:80]}", "warn")
            # Fallback: thu lai voi model "small" (nhe hon, neu medium thieu RAM)
            try:
                from faster_whisper import WhisperModel as _WM
                self._log("  ⏳ Thu lai voi faster-whisper small...", "info")
                model = _WM("small", device="cpu", compute_type="int8")
                segments, info = model.transcribe(audio_path, beam_size=5, vad_filter=True)
                text = " ".join(s.text.strip() for s in segments).strip()
                if text:
                    self._transcribe_cache[cache_key] = text
                    if vp:
                        vp.ref_text = text
                        try: self.lib.save()
                        except Exception: pass
                    return text
            except Exception:
                pass

        # 3. Thu openai-whisper
        try:
            import whisper as _ow
            self._log("  ⏳ Đang nhận diện ref_audio (openai-whisper)...", "info")
            model = _ow.load_model("base")
            r = model.transcribe(audio_path)
            text = (r.get("text") or "").strip()
            if text:
                self._transcribe_cache[cache_key] = text
                if vp:
                    vp.ref_text = text
                    try: self.lib.save()
                    except Exception: pass
                return text
        except ImportError:
            pass
        except Exception as _e:
            self._log(f"  ⚠ openai-whisper loi: {str(_e)[:80]}", "warn")

        # 4. Thu transformers truc tiep voi whisper-base (nho hon turbo)
        try:
            from transformers import pipeline
            self._log("  ⏳ Đang nhận diện ref_audio (transformers + whisper-base)...", "info")
            pipe = pipeline("automatic-speech-recognition",
                          model="openai/whisper-base",
                          device=-1)  # CPU de tranh CUDA conflict
            r = pipe(audio_path)
            text = (r.get("text") or "").strip()
            if text:
                self._transcribe_cache[cache_key] = text
                if vp:
                    vp.ref_text = text
                    try: self.lib.save()
                    except Exception: pass
                return text
        except Exception as _e:
            self._log(f"  ⚠ transformers whisper loi: {str(_e)[:80]}", "warn")

        # 5. Tat ca fallback fail -> bao user nhap thu cong
        self._log(
            "  ❌ Khong nhan dien duoc ref_audio. Vui long vao tab Clone Voice "
            "→ Sua voice → nhap 'Noi dung audio mau' (ref_text) thu cong.", "err")
        return ""

    def _prepare_ref_audio(self, audio_path: str) -> str:
        """Chuan bi file audio mau cho clone.
        FIX (v3.18): KHONG cat 30s nua. omnivoice/F5 chay tot voi 10-90s.
        Chi cat khi qua 90s de tranh OOM. Giu nguyen nhung gi user da chuan bi.
        """
        try:
            import torchaudio, torch
            from pathlib import Path as _P
            MAX_SEC = 30   # FIX v3.19: ve lai 30s nhu v2.8. 90s qua dai
                           # khien model "lo loc" tu trong ref audio sang output
            t, sr = _safe_audio_load(audio_path)
            dur = t.shape[1] / sr
            # Khong cat neu trong gioi han -> giu nguyen chat luong clone
            if dur <= MAX_SEC:
                return audio_path
            # Cat khi qua dai (tranh OOM)
            max_samples = int(MAX_SEC * sr)
            t_trim = t[:, :max_samples]
            cache = str(_P(audio_path).with_suffix("")) + "_trim30s.wav"
            torchaudio.save(cache, t_trim, sr)
            pass  # trim silently
            return cache
        except Exception:
            return audio_path

    def _trim_sil(self, t, thr=0.01, win_ms=10):
        """Trim leading/trailing silence dung windowed RMS — chong MP3 codec noise."""
        import torch as _tc
        sr = 24000
        win = max(1, int(win_ms * sr / 1000))
        s = t.abs().squeeze(0)
        n = s.shape[0]
        if n == 0:
            return t
        pad = (win - n % win) % win
        sp = _tc.nn.functional.pad(s, (0, pad))
        rms = sp.reshape(-1, win).mean(dim=1)
        active = (rms > thr).nonzero(as_tuple=False)
        if len(active) == 0:
            return t
        start = active[0].item() * win
        end = min(n, (active[-1].item() + 1) * win)
        return t[:, start:end]

    def _trim_tail(self, t, thr=0.005, win_ms=20):
        """Chi trim duoi audio (khong cat dau) — danh cho trailing settling noise cua TTS.
        thr=0.005 bat duoc muc noise thap hon _trim_sil (0.01) ma model sinh sau tu cuoi.
        win_ms=20 tranh cat consonant cuoi cau (x, s, t, ...) voi nang luong thap."""
        import torch as _tc
        sr = 24000
        win = max(1, int(win_ms * sr / 1000))
        s = t.abs().squeeze(0)
        n = s.shape[0]
        if n == 0:
            return t
        pad = (win - n % win) % win
        sp = _tc.nn.functional.pad(s, (0, pad))
        rms = sp.reshape(-1, win).mean(dim=1)
        active = (rms > thr).nonzero(as_tuple=False)
        if len(active) == 0:
            return t
        end = min(n, (active[-1].item() + 1) * win)
        return t[:, :end]   # giu nguyen dau, chi cat duoi

    def _get_speed(self):
        """Lay toc do: uu tien speed tu voice profile, fallback sidebar."""
        if 0 <= self.sel_idx < len(self.lib.profiles):
            vp = self.lib.profiles[self.sel_idx]
            if vp.speed and vp.speed != 1.0:
                return vp.speed
        spd = self.speed_var.get()
        return spd

    def _out(self, name=None, ext=None):
        d=self.out_dir_var.get(); os.makedirs(d,exist_ok=True)
        n=name or self.out_name_var.get() or "output"
        e=ext or self.fmt_var.get()
        p=os.path.join(d,n+e); i=1
        while os.path.exists(p): p=os.path.join(d,f"{n}_{i}{e}"); i+=1
        # Luu path cuoi cung vao bien de tranh ghi de trong cung session
        self._last_out_path = p
        return p

    def _save(self, tensor, path):
        """Luu audio. Returns duong dan file thuc su (co the la .wav neu ffmpeg khong co)."""
        import torch
        if hasattr(self, "post_proc_var") and self.post_proc_var.get():
            tensor = _post_process(tensor)
        else:
            peak = tensor.abs().max()
            if peak > 0.95:
                tensor = tensor * (0.891 / peak)
        if path.endswith(".mp3"):
            result = to_mp3(tensor, path)  # tra ve wav_path neu ffmpeg fallback, None neu OK
            if result and result != path:
                self._log(f"⚠ ffmpeg khong co — luu WAV thay MP3: {Path(result).name}", "warn")
                return result
            return path
        else:
            to_wav(tensor, path)
            return path

    def _del_char_from_text(self, char):
        """Xoa ky tu cu the khoi text box."""
        txt = self.txt_in.get("1.0", "end-1c")
        if not txt: return
        # Luu ban goc neu chua co
        if not hasattr(self, "_txt_backup"):
            self._txt_backup = txt
        new_txt = txt.replace(char, "")
        self.txt_in.delete("1.0", "end")
        self.txt_in.insert("1.0", new_txt)
        n = txt.count(char)
        self._log(f"🗑 Xoa '{char}': {n} cho", "info")

    def _del_custom_char(self):
        """Xoa ky tu tuy chinh nguoi dung nhap."""
        char = self.custom_char_var.get()
        if not char:
            messagebox.showwarning("Trống", "Nhập ký tự muốn xóa!")
            return
        self._del_char_from_text(char)

    def _restore_text(self):
        """Khoi phuc van ban goc truoc khi xoa."""
        if hasattr(self, "_txt_backup") and self._txt_backup:
            self.txt_in.delete("1.0", "end")
            self.txt_in.insert("1.0", self._txt_backup)
            del self._txt_backup
            self._log("✅ Đã khôi phục văn bản gốc", "ok")
        else:
            messagebox.showinfo("Thông báo", "Không có bản sao lưu!")

    def _preview_tts_friendly(self):
        """Hien dialog so sanh van ban truoc/sau khi Toi uu doc (TTS-friendly).
        Chi xem, KHONG sua o van ban goc trong o nhap."""
        txt = self.txt_in.get("1.0", "end-1c").strip()
        if not txt or txt.startswith("Nhập nội dung"):
            messagebox.showwarning("Trống", "Hãy nhập văn bản!"); return
        # FIX v3.66: xem truoc phai khop dung voi luc tao that (Edge TTS
        # khong tach cau dai - xem ghi chu split_long_sentences)
        _is_edge_preview = getattr(self, "tts_mode", None) and self.tts_mode.get() == "edge"
        # FIX v3.66 (audit 2026-07-24): xem truoc phai khop voi _do_text() -
        # neu dang chon voice clone, TTS-friendly se KHONG duoc ap dung luc
        # tao that (xem ghi chu o _do_text), nen preview cung phai hien
        # "khong doi gi" thay vi hien ket qua gia (lam khach tuong se ap
        # dung nhung thuc te khong).
        _cur_vp_preview = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        if _cur_vp_preview and _cur_vp_preview.mode == "clone":
            messagebox.showinfo(
                "Voice Clone — không áp dụng",
                "Giọng đang chọn là Clone Voice.\n\n"
                "Tối ưu đọc (TTS-friendly) KHÔNG áp dụng cho Clone Voice để giữ "
                "nguyên 100% văn bản (đúng ngữ điệu/nhịp audio mẫu) — văn bản sẽ "
                "được đọc y nguyên như bạn nhập, không xem trước gì thêm.")
            return
        after = _tts_friendly(txt, split_long_sentences=not _is_edge_preview)
        # So sanh CHUOI TU THUC SU (chi lay ky tu chu cai, bo qua dau cau/
        # khoang trang/gach noi) - dung cach nay thay vi dem theo khoang
        # trang don thuan, vi split-gach-noi ("well-dressed"->"well","dressed")
        # va bo dau gach dai dung rieng deu lam thay doi SO LUONG TOKEN theo
        # khoang trang du KHONG mat/doi tu ngu nao thuc su.
        import re as _re_wc
        def _words_only(s):
            return [w.lower() for w in _re_wc.findall(r"[A-Za-zÀ-ỹ]+", s)]
        _wb, _wa = _words_only(txt), _words_only(after)
        _same = (_wb == _wa)

        dlg = tk.Toplevel(self)
        dlg.title("👁 Xem trước — Tối ưu đọc (TTS-friendly)")
        dlg.geometry("640x520")
        dlg.configure(bg=P["white"])
        dlg.transient(self); dlg.grab_set()

        tk.Label(dlg, text=("✓ Giữ nguyên 100% từ ngữ" if _same
                             else "⚠ CẢNH BÁO: có thể lệch từ ngữ — kiểm tra kỹ trước khi dùng!"),
                 font=(FN,9,"bold"), bg=P["white"],
                 fg=P["green"] if _same else P["red"]
                 ).pack(anchor="w", padx=12, pady=(10,4))

        tk.Label(dlg, text="Sau khi tối ưu (sẽ dùng để tạo voice):",
                 font=(FN,9,"bold"), bg=P["white"], fg=P["label"]).pack(anchor="w", padx=12)
        _txt_after = tk.Text(dlg, wrap="word", font=(FN,10), height=16,
                              bg=P["white"], fg=P["text"], relief="flat",
                              highlightthickness=1, highlightbackground=P["border"])
        _txt_after.pack(fill="both", expand=True, padx=12, pady=(2,10))
        _txt_after.insert("1.0", after)
        _txt_after.config(state="disabled")

        tk.Button(dlg, text="Đóng", command=dlg.destroy,
                  font=(FN,9,"bold"), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", padx=16, pady=6
                  ).pack(pady=(0,12))

    @staticmethod
    def _clean_text_for_tts(txt):
        """Lam sach van ban truoc khi dua vao TTS."""
        import re as _re
        txt = _re.sub(r"^#{1,6}\s+", "", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"[*_]{1,3}(.+?)[*_]{1,3}", r"\1", txt)  # FIX: giu noi dung bold/italic
        txt = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", txt)  # FIX: giu text markdown link
        txt = _re.sub(r"^>+\s*", "", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"^\s*[-=*#~_]{2,}\s*$", "", txt, flags=_re.MULTILINE)
        txt = _re.sub(r"\s*---+\s*", " ", txt)
        txt = _re.sub(r"\s*===+\s*", " ", txt)
        txt = _re.sub(r"\s*/+\s*", " ", txt)
        txt = _re.sub(r"[|\\<\>\[\]\{\}\^\`~]", " ", txt)
        txt = _re.sub(r" {2,}", " ", txt)
        txt = _re.sub(r"\n{3,}", "\n\n", txt)

        return txt.strip()

    def _do_text(self):
        txt=self.txt_in.get("1.0","end-1c").strip()
        if not txt or txt.startswith("Nhập nội dung"):
            messagebox.showwarning("Trống","Hãy nhập văn bản!"); return
        # Lam sach trong main thread (an toan)
        txt = self._clean_text_for_tts(txt)
        if not txt:
            messagebox.showwarning("Trống","Văn bản trống sau khi làm sạch!"); return
        # Toi uu doc (TTS-friendly): chi ap dung tren BAN SAO ngay truoc khi
        # tao voice - KHONG sua o van ban goc trong o nhap cua khach.
        # FIX v3.66: Edge TTS khong tach cau dai (rule B) - Edge khong bi
        # "vap" cau dai nhu MagicVoice, tach them dau cham chi lam Edge tu
        # nghi lau hon khong can thiet (khach bao "sau dau cham nghi lau").
        # FIX v3.66 (audit 2026-07-24, theo yeu cau anh Bac): TRUOC DAY ap
        # dung TTS-friendly GIONG HET cho ca mode="clone" va mode="design" -
        # day la nguyen nhan "tieng la" ngau nhien khach bao khi dung voice
        # clone (clone can giu NGUYEN VAN 100% van ban de dung ngu dieu/nhip
        # cua audio mau, moi thay doi cau truc du nho - tach cau, doi gach
        # noi - co the lam lech alignment audio-text ma model clone dua vao).
        # Khach hang da xac nhan dung tool cho nhieu ngon ngu (chu yeu Anh,
        # ngoai ra Tay Ban Nha/Nhat/Phap/Han/Thai...) - Rule B chi nhan dien
        # lien tu tieng Anh nen chi anh huong ro nhat o van ban tieng Anh,
        # nhung Rule A (bo gach noi)/Rule C (chuan hoa khoang trang) van doi
        # van ban cho MOI ngon ngu - nen tat CA TTS-friendly (khong chi Rule
        # B) cho rieng mode=clone, giu nguyen cho mode=design.
        _cur_vp_txt = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        _is_clone_mode_txt = bool(_cur_vp_txt and _cur_vp_txt.mode == "clone")
        if getattr(self, "tts_friendly_var", None) and self.tts_friendly_var.get() and not _is_clone_mode_txt:
            _is_edge_mode = self.tts_mode.get() == "edge"
            txt = _tts_friendly(txt, split_long_sentences=not _is_edge_mode)
        # Lock se tu dong ngan thread moi neu thread cu van dang gen()
        # Khong can check thu cong nua

        if self.is_running:
            return  # Tranh double-click tao nhieu thread
        self.is_running = True  # Set ngay truoc khi start thread
        self._running_tab = "text"
        self.after(0, self._refresh_tab_indicators)   # MOI: hien cham tron tab dang chay
        self.after(0, self.create_btn.config, {"state": "disabled"})
        self.cancel_ev.clear()
        mode = self.tts_mode.get()
        if mode == "edge":
            t = threading.Thread(target=self._run_edge_text,args=(txt,),daemon=True)
        elif mode == "fast":
            t = threading.Thread(target=self._run_fast_text,args=(txt,),daemon=True)
        else:
            t = threading.Thread(target=self._run_text,args=(txt,),daemon=True)
        self._gen_thread = t
        t.start()
    def _split_sentences(self, txt: str) -> list:
        """Tách văn bản thành câu ngắn để xử lý tuần tự."""
        import re as _re
        # Tách theo dấu câu hoặc xuống dòng
        # FIX: dùng raw string để tránh SyntaxWarning về \s. Unicode escape viết trực tiếp.
        delim = _re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+")
        parts = delim.split(txt.strip())
        result = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if len(p) > 200:
                # FIX: raw string để tránh SyntaxWarning về \s
                comma_pat = _re.compile(r"[,;\uff0c\uff1b]\s*")
                sub = comma_pat.split(p)
                result.extend([s.strip() for s in sub if s.strip()])
            else:
                result.append(p)
        return result if result else [txt.strip()]

    def _start_timer(self):
        """Bắt đầu đếm thời gian hiển thị trên status."""
        self._timer_start = time.time()
        self._timer_running = True
        self._tick_timer()

    def _tick_timer(self):
        if not self._timer_running: return
        elapsed = int(time.time() - self._timer_start)
        m, s = divmod(elapsed, 60)
        self._timer_label.config(text=f"⏱ {m:02d}:{s:02d}")
        self.after(1000, self._tick_timer)

    def _stop_timer(self):
        self._timer_running = False
        self._timer_label.config(text="")

    # ── MOI: Helper license check dung chung cho moi run method ──
    def _verify_license_or_abort(self) -> bool:
        """Check license. Tra True neu OK, False neu fail (da tu dong popup).
        Dung session cache nen goi nhieu lan khong chậm."""
        _u = getattr(self, "_username", "")
        if not _u:
            # FIX (bao mat 2026-08-14): TRUOC DAY return True (bo qua kiem tra)
            # o day - day chinh la lo hong khach dung tool free vinh vien neu
            # username bi rong (vd tung phu thuoc file cache co the trong).
            # Gio fail-CLOSED dung triet ly cua chinh license_guard.py: khong
            # xac dinh duoc user -> TU CHOI, khong cho tao voice.
            self.after(0, lambda: messagebox.showerror(
                "License không hợp lệ",
                "Không xác định được tài khoản đăng nhập.\n\n"
                "Vui lòng khởi động lại app và đăng nhập lại.\n"
                "Hỗ trợ: Zalo 0985 483 623",
                parent=self))
            return False
        try:
            ok, msg = _check_license_gs(_u)
        except Exception as e:
            ok, msg = False, str(e)
        if not ok:
            self.after(0, lambda m=msg: messagebox.showerror(
                "License không hợp lệ",
                f"{m}\n\nVui lòng kết nối internet và khởi động lại app.\n"
                "Hỗ trợ: Zalo 0985 483 623",
                parent=self))
            self._log(f"❌ License từ chối: {msg}", "err")
        return ok

    def _run_text(self, txt):
        """
        Tách nhỏ → đọc nhanh từng đoạn → nối lại:
        1. Tách theo câu/đoạn (~200 ký tự/chunk)
        2. Đọc từng chunk nhanh (text ngắn = gen nhanh hơn)
        3. Nối tensor trong RAM → lưu 1 lần
        """
        # Kiem tra license truoc khi tao voice
        if not self._verify_license_or_abort():
            return
        self.cancel_ev.clear()   # Reset trạng thái hủy
        self._busy(True)
        self._start_timer()

        try:
            import torch, re as _re
            kw    = self._vkw()
            vp    = self.lib.profiles[self.sel_idx] if self.sel_idx < len(self.lib.profiles) else None
            vname = vp.name if vp else ""
            steps = self.steps_var.get()
            speed = self._get_speed()  # Uu tien speed tu voice profile
            SR    = 24000

            # ── Tách text thành chunks tối ưu ───────────────────────
            # Dung _smart_chunks: max_ch=280 (duoi nguong 375 OmniVoice), pause thong minh
            # 350ms sau .!? (sentence), 100ms sau ,; (clause), 500ms giua doan van (\n\n)
            _paras = [p.strip() for p in txt.split("\n\n") if p.strip()]
            chunks = []
            for _pi, _para in enumerate(_paras):
                _pc = _smart_chunks(_para, SR)
                if not _pc:
                    continue
                # Tat ca chunk trong doan: giu pause cua _smart_chunks
                for _ct, _cm in _pc[:-1]:
                    chunks.append((_ct, _cm))
                # Chunk cuoi doan: 500ms giua doan (tru doan cuoi cung)
                _last_t, _ = _pc[-1]
                chunks.append((_last_t, 500 if _pi < len(_paras) - 1 else 0))
            if not chunks:
                chunks = [(txt.strip(), 0)]

            total = len(chunks)
            self._log(f"🎙 {vname} | Steps:{steps} | Speed:{speed:.1f}x | {total} chunks | {len(txt)} ký tự", "info")
            self.after(0, lambda: self.pb.configure(mode="determinate", value=0))

            # Tạo thư mục output trước khi gen để lưu từng chunk ngay
            out_d = self.out_dir_var.get()
            os.makedirs(out_d, exist_ok=True)
            _fname = self._next_out_name_single("")
            try:
                if self.out_ask_name_var.get():
                    _v = self._ask_output_filename(_fname, "Tab Văn Bản")
                    if _v and _v.strip():   _fname = _v.strip()
                    elif _v is None:        self._log("⏭ Dùng tên mặc định", "warn")
            except Exception:
                pass
            _out_folder = os.path.join(out_d, _fname)
            os.makedirs(_out_folder, exist_ok=True)
            self._log(f"📁 {_out_folder}", "info")

            # ── Đọc từng chunk & nối ────────────────────────────────
            parts = []
            # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): [(text, dur_giay)]
            # cho tung chunk THANH CONG - dung xuat .srt timeline sau, dur da
            # gom ca khoang lang pause_ms (neu co) vi no la 1 phan "thoi
            # gian thuc" giua noi dung, giong cach _run_srt xu ly gap.
            _srt_timeline_data = []
            for ci, (chunk_txt, pause_ms) in enumerate(chunks):
                if self.cancel_ev.is_set():
                    self._log("⏹ Đã hủy", "warn"); return

                pct = ci / total * 100
                self.after(0, lambda v=pct: self.pb.configure(value=v))
                self._st(f"[{ci+1}/{total}] {chunk_txt[:45]}…")

                if self.cancel_ev.is_set():
                    self._log("⏹ Đã hủy (trước gen)", "warn"); return

                t0 = time.time()
                if self.cancel_ev.is_set():
                    self._log(f"⏹ Đã hủy chunk {ci+1}", "warn"); return

                # FIX: Gen 1 lan don gian nhu v3.5.
                # Truoc day mình gen 3 lan voi seed khac va chon ban "deviation thap nhat"
                # so voi expected = n_words * 220ms. Logic do co loi:
                #   - Voice clone giong cham (280ms/tu) -> moi ban deu lech expected
                #   - Bản BO TU thuong NGAN HON expected -> deviation NHO -> bi chon
                #   - Ket qua: chon nham ban bo tu lam ket qua chinh thuc!
                # Theo doc OmniVoice, model gen 1 lan voi guidance_scale=2.0 da on dinh.
                # _gen_verified: gen + Whisper verify + auto-retry neu phat am sai
                audio_t, _vok, _vtr = _gen_verified(
                    chunk_txt, steps, speed, kw, log_fn=self._log)

                elapsed = time.time() - t0

                if audio_t is None or audio_t.abs().max() < 0.0001:
                    self._log(f"  [{ci+1}/{total}] ⚠ Audio rong - bo qua", "warn")
                    continue
                self._log(f"  [{ci+1}/{total}] {elapsed:.1f}s | {chunk_txt[:40]}", "info")

                audio_t = self._trim_sil(audio_t)   # trim model padding per chunk
                parts.append(audio_t)

                # FIX: tab Van Ban CHI xuat 1 file hoan chinh - khong luu
                # tung chunk rieng (voice le chi danh cho tab SRT, noi moi
                # dong = 1 don vi noi dung rieng biet co timing). Truoc day
                # code nay luu tung chunk ({ci+1:03d}.mp3) vao _out_folder
                # ngay ca khi chi doc van ban thuong, gay nham lan voi
                # "voice le" cua SRT.

                _chunk_dur = audio_t.shape[-1] / SR

                # Thêm im lặng giữa các chunk
                if pause_ms > 0:
                    parts.append(torch.zeros(1, int(pause_ms * SR / 1000)))
                    _chunk_dur += pause_ms / 1000.0
                _srt_timeline_data.append((chunk_txt, _chunk_dur))

            # ── Nối tất cả trong RAM ─────────────────────────────────
            if not parts:
                raise RuntimeError(
                    "Khong tao duoc audio!\n\n"
                    "Nguyen nhan thuong gap:\n"
                    "  1. Voice clone chua co Transcription\n"
                    "     → Sua voice, dien vai cau vao o Transcription\n"
                    "  2. CUDA Out of Memory\n"
                    "     → Giam Steps xuong 4-8, doi float16\n"
                    "  3. Model chua tai xong\n"
                    "     → Doi model load xong roi tao\n\n"
                    "Xem Log phia duoi de biet chi tiet loi."
                )
            self._log("🔗 Nối các đoạn trong RAM…", "info")
            final = _concat_crossfade(parts, sr=SR if 'SR' in dir() else 24000, fade_ms=15)
            final = self._trim_tail(final)   # cat trailing settling noise cuoi toan bo audio

            # Lưu file ghép tổng vào thư mục đã tạo
            try:
                _ext = f".{self.fmt_var.get()}"
            except Exception:
                _ext = ".mp3"
            _merged_path = os.path.join(_out_folder, f"{_fname}{_ext}")
            actual_path = self._save(final, _merged_path)
            if not os.path.exists(actual_path):
                raise RuntimeError(
                    f"File da tao nhung khong tim thay:\n{actual_path}\n\n"
                    "Kiem tra quyen ghi thu muc output."
                )

            # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): xuat .srt timeline
            # khop audio vua tao, giong tinh nang da co o tab SRT - gap_ms=0
            # vi khoang lang giua chunk da duoc GOM SAN vao dur cua tung
            # entry trong _srt_timeline_data (xem noi append o tren).
            try:
                if getattr(self, "text_srt_timeline_var", None) and self.text_srt_timeline_var.get():
                    _srt_out_path = str(Path(actual_path).with_suffix("")) + "_timeline.srt"
                    _srt_saved_path, _srt_n = _export_srt_timeline(
                        _srt_timeline_data, 0, _srt_out_path)
                    self._log(f"📝 SRT timeline ({_srt_n} dòng): {_srt_saved_path}", "ok")
            except Exception as _srt_exp_err:
                self._log(f"⚠ Không xuất được .srt timeline: {_srt_exp_err}", "warn")

            total_t = int(time.time() - self._timer_start)
            self._st(f"✅ Xong! {total_t}s → {Path(actual_path).name}", P["green"])
            self._log(f"✅ {actual_path}", "ok")
            self.after(0, lambda: self.pb.configure(value=100))
            self.after(100, lambda p=actual_path, t=total_t: self._done_notify(p, t))

        except Exception as e:
            import traceback
            self._log(f"❌ {e}", "err")
            self._log(traceback.format_exc()[-400:], "err")
            self._st(f"❌ {str(e)[:80]}", P["red"])
            e_msg = str(e)
            self.after(100, lambda err=e_msg: messagebox.showerror(
                "Lỗi tạo voice", f"{err[:400]}"))
        finally:
            self._stop_timer()
            self.after(0, lambda: self.pb.stop())
            self.after(0, lambda: self.pb.configure(mode="determinate", value=0))
            # Reset CUDA state sau failed gen - tranh loi cho lan sau
            try:
                import torch as _tc
                if _tc.cuda.is_available():
                    _tc.cuda.empty_cache()
                    _tc.cuda.synchronize()
            except Exception:
                pass
            self._busy(False)

    def _run_edge_text(self, txt):
        """
        Đọc văn bản bằng Edge TTS (Microsoft) — nhanh, online.
        Tách theo đoạn → gọi Edge TTS song song → nối lại.
        """
        # MOI: kiem tra license truoc
        if not self._verify_license_or_abort():
            return
        self._busy(True)
        self._start_timer()
        try:
            import asyncio, tempfile, torchaudio, torch, re as _re

            # Lay voice tu edge_voice_var - luon dung gia tri hien tai
            # edge_voice_var duoc set boi _on_edge_voice_select khi chon listbox
            voice = self.edge_voice_var.get() if hasattr(self, "edge_voice_var") else "en-US-AriaNeural"
            if not voice:
                voice = "en-US-AriaNeural"
            self._log(f"🌐 Edge TTS | Voice: {voice} | {len(txt)} ký tự", "info")

            # Tách theo đoạn (dòng trống)
            paras = [p.strip() for p in txt.split("\n\n") if p.strip()]
            if not paras:
                paras = [txt.strip()]

            total = len(paras)
            self.after(0, lambda: self.pb.configure(mode="determinate", value=0))

            SR = 24000
            parts = []
            silence = torch.zeros(1, int(0.7 * SR))
            # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): [(text, dur_giay)]
            # cho tung doan THANH CONG - dung xuat .srt timeline sau.
            _srt_timeline_data = []

            async def gen_edge(text, out_path, voice_id):
                """Gen Edge TTS voi retry 3 lan + verify file size.
                Ho tro edge_tts cu (PCM codec) va moi (>= 6.x, chi co MP3).
                Return: True (OK) / False (loi khac) / 'fallback' (mat mang)."""
                import edge_tts, asyncio as _aio, wave as _wave, inspect as _ins
                # Detect API version once: edge_tts < 6.x co 'codec', >= 6.x thi khong
                _use_pcm = 'codec' in _ins.signature(edge_tts.Communicate.__init__).parameters
                last_err = None
                for _attempt in range(3):
                    pcm_path = out_path + ".pcm"
                    mp3_path = out_path + ".mp3"
                    try:
                        for _p in [out_path, pcm_path, mp3_path]:
                            try:
                                if os.path.exists(_p): os.remove(_p)
                            except Exception: pass
                        if _use_pcm:
                            # edge_tts cu: PCM, khong encoder delay
                            comm = edge_tts.Communicate(text, voice_id,
                                                        codec="audio-24khz-16bit-mono-pcm")
                            await comm.save(pcm_path)
                            if not os.path.exists(pcm_path):
                                last_err = "file khong duoc tao"
                            else:
                                sz = os.path.getsize(pcm_path)
                                if sz < 100:
                                    last_err = f"file rong/loi ({sz} bytes)"
                                    try: os.remove(pcm_path)
                                    except Exception: pass
                                else:
                                    with open(pcm_path, "rb") as _f:
                                        _pcm = _f.read()
                                    with _wave.open(out_path, "wb") as _wf:
                                        _wf.setnchannels(1); _wf.setsampwidth(2)
                                        _wf.setframerate(24000); _wf.writeframes(_pcm)
                                    try: os.remove(pcm_path)
                                    except Exception: pass
                                    return True
                        else:
                            # edge_tts >= 6.x: khong co 'codec', luu MP3 roi convert WAV
                            comm = edge_tts.Communicate(text, voice_id)
                            await comm.save(mp3_path)
                            if not os.path.exists(mp3_path):
                                last_err = "file khong duoc tao"
                            else:
                                sz = os.path.getsize(mp3_path)
                                if sz < 100:
                                    last_err = f"file rong/loi ({sz} bytes)"
                                    try: os.remove(mp3_path)
                                    except Exception: pass
                                else:
                                    # FIX 11: soundfile backend khong doc MP3 → dung imageio_ffmpeg convert truoc
                                    import imageio_ffmpeg as _iff11
                                    import subprocess as _sp11
                                    _wav_tmp11 = mp3_path + "_24k.wav"
                                    try:
                                        _sp11.run(
                                            [_iff11.get_ffmpeg_exe(), '-i', mp3_path,
                                             '-ar', '24000', '-ac', '1', '-f', 'wav',
                                             _wav_tmp11, '-y', '-loglevel', 'quiet'],
                                            timeout=30, check=True,
                                            creationflags=0x08000000)
                                        _wv, _sr = _safe_audio_load(_wav_tmp11)
                                    finally:
                                        try: os.remove(_wav_tmp11)
                                        except Exception: pass
                                    if _sr != 24000:
                                        _wv = torchaudio.functional.resample(_wv, _sr, 24000)
                                    if _wv.shape[0] > 1:
                                        _wv = _wv.mean(dim=0, keepdim=True)
                                    import soundfile as _sf_sv0
                                    _sf_sv0.write(out_path, _wv.squeeze().numpy(), 24000, subtype='PCM_16')
                                    try: os.remove(mp3_path)
                                    except Exception: pass
                                    return True
                    except Exception as e:
                        last_err = str(e)
                        err_msg = str(e).lower()
                        if any(x in err_msg for x in ["network","connect","timeout","ssl","winerror","dns","resolve"]):
                            self._log(f"  ⚠ Edge TTS mat mang — chuyen sang MagicVoice Clone", "warn")
                            return "fallback"
                    finally:
                        for _p in [pcm_path, mp3_path]:
                            try:
                                if os.path.exists(_p): os.remove(_p)
                            except Exception: pass
                    if _attempt < 2:
                        self._log(f"  ⚠ Edge TTS thu {_attempt+1}/3 fail ({str(last_err)[:60]}) — retry...", "warn")
                        await _aio.sleep(1.5 * (_attempt + 1))
                # FIX v3.68 (theo anh Bac yeu cau 2026-07-30, khach bi antivirus/
                # firewall chan ket noi Microsoft): truoc day CHI fallback ngay
                # sang MagicVoice khi thong diep loi khop dung 1 trong vai tu
                # khoa co dinh (network/connect/timeout/ssl/winerror/dns/
                # resolve) - neu phan mem diet virus/firewall chan theo kieu
                # tra ve thong diep loi KHONG khop dung tu nao trong danh sach
                # (rat nhieu bien the tuy tung hang AV), Edge TTS thu du 3 lan
                # roi BO CUOC HOAN TOAN, hien popup loi bat khach tu di sua
                # mang/tuong lua - dung khi thuc te khong lien quan toc do/on
                # dinh mang (anh Bac da xac nhan mang binh thuong). Gio: DA
                # THU DU 3 LAN THAT SU MA VAN LOI (bat ke thong diep loi la
                # gi) -> luon fallback sang MagicVoice, khong con truong hop
                # bo cuoc hoan toan nua.
                self._log(f"  ⚠ Edge TTS loi sau 3 lan retry ({last_err}) — chuyen sang MagicVoice Clone", "warn")
                return "fallback"

            tmp_dir = tempfile.mkdtemp(prefix="ov_edge_")

            for pi, para in enumerate(paras):
                if self.cancel_ev.is_set():
                    self._log("⏹ Đã hủy", "warn"); return

                pct = pi / total * 100
                self.after(0, lambda v=pct: self.pb.configure(value=v))
                self._st(f"[{pi+1}/{total}] {para[:45]}…")

                # MOI: chen dau phay vao cau dai khong co dau de Edge TTS
                # ngat nghi tu nhien, doc co cam xuc hon
                para_for_tts = _edge_smart_pause(para, max_words=8)
                if para_for_tts != para:
                    n_added = para_for_tts.count(",") - para.count(",")
                    self._log(f"  ↪ Tự thêm {n_added} dấu phẩy để ngắt nghỉ tự nhiên", "info")

                tmp_wav = f"{tmp_dir}/p{pi:04d}.wav"
                t0 = time.time()

                # Chạy async trong sync context
                ok = asyncio.run(gen_edge(para_for_tts, tmp_wav, voice))
                elapsed = time.time() - t0

                # Fallback: mat mang -> dung MagicVoice clone voice
                if ok == "fallback":
                    self._log(f"  🔄 [{pi+1}] Dung MagicVoice thay Edge TTS", "info")
                    try:
                        kw = self._vkw()
                        tensor = Backend.gen(para, **kw,
                                             num_step=self._cfg.get("steps",24),
                                             speed=self._get_speed())
                        parts.append(tensor)
                        parts.append(silence)
                        _srt_timeline_data.append((para, tensor.shape[-1]/SR + 0.7))
                    except Exception as fb_e:
                        self._log(f"  ✗ Fallback that bai: {fb_e}", "err")
                    continue

                if ok and Path(tmp_wav).exists():
                    try:
                        tensor, sr = _safe_audio_load(tmp_wav)
                        if tensor.numel() == 0 or tensor.shape[-1] == 0:
                            self._log(f"  ⚠ [{pi+1}] Audio rong — bo qua doan nay", "warn")
                        else:
                            if sr != SR:
                                tensor = torchaudio.functional.resample(tensor, sr, SR)
                            if tensor.shape[0] > 1:
                                tensor = tensor.mean(dim=0, keepdim=True)
                            parts.append(tensor)
                            _dur = tensor.shape[-1]/SR
                            if pi < total - 1:
                                parts.append(silence)
                                _dur += 0.7
                            _srt_timeline_data.append((para, _dur))
                            self._log(f"  [{pi+1}/{total}] {elapsed:.1f}s ✓", "info")
                    except Exception as _le:
                        # File tao duoc nhung load fail (file bi corrupt)
                        # -> Thu fallback MagicVoice cho doan nay
                        self._log(f"  ⚠ [{pi+1}] File MP3 loi ({str(_le)[:60]}) — thu MagicVoice", "warn")
                        try:
                            kw = self._vkw()
                            a = Backend.gen(para, **kw,
                                            num_step=self.steps_var.get(),
                                            speed=self._get_speed())
                            tensor = _to_tensor(a)
                            if tensor is not None and tensor.abs().max() > 0.0001:
                                parts.append(tensor)
                                _dur = tensor.shape[-1]/SR
                                if pi < total - 1:
                                    parts.append(silence)
                                    _dur += 0.7
                                _srt_timeline_data.append((para, _dur))
                                self._log(f"  ✓ [{pi+1}] MagicVoice fallback OK", "info")
                        except Exception as _fbe:
                            self._log(f"  ✗ [{pi+1}] Fallback that bai: {_fbe}", "err")
                else:
                    self._log(f"  [{pi+1}/{total}] Lỗi — bỏ qua", "warn")

            if not parts and not self.cancel_ev.is_set():
                self._log("❌ Edge TTS: Khong tao duoc audio. Kiem tra ket noi internet va module edge_tts.", "err")
                self._st("❌ Edge TTS thất bại — xem Log", P["red"])
                self.after(0, lambda: messagebox.showerror(
                    "Edge TTS Lỗi",
                    "Không tạo được audio.\n\n"
                    "Nguyên nhân có thể:\n"
                    "• Mất kết nối internet\n"
                    "• Server Microsoft bị chặn bởi tường lửa\n"
                    "• Module edge_tts chưa cài đúng\n\n"
                    "Xem chi tiết trong Log bên phải.\n"
                    "Thử lại hoặc dùng chế độ MagicVoice."))

            if parts and not self.cancel_ev.is_set():
                final = _concat_crossfade(parts, sr=SR if 'SR' in dir() else 24000, fade_ms=15)
                if hasattr(self, "post_proc_var") and self.post_proc_var.get():
                    final = _post_process(final, SR)
                # MOI: dat ten theo cau hinh naming global
                # Fallback stem cho mode='keep': ten voice edge
                _vname = voice.replace("Neural","").replace("en-US-","").replace("en-GB-","").replace("vi-VN-","").replace("en-AU-","").replace("ja-JP-","").replace("ko-KR-","").replace("zh-CN-","")
                _fallback = f"{_vname}_Edge"
                out_name = self._next_out_name_single(_fallback)
                try:
                    if self.out_ask_name_var.get():
                        _v = self._ask_output_filename(out_name, "Tab Văn Bản (Edge TTS)")
                        if _v and _v.strip(): out_name = _v.strip()
                except Exception:
                    pass
                path = self._out(name=out_name)
                if path.endswith(".mp3"):
                    to_mp3(final, path)
                    # FIX: to_mp3 silent-fallback WAV neu ffmpeg thieu → check va dung dung path
                    if not os.path.exists(path):
                        _wav_fb = path.replace(".mp3", ".wav")
                        if os.path.exists(_wav_fb):
                            path = _wav_fb
                            self._log("  ⚠ Luu WAV thay MP3 (ffmpeg chua cai day du) — chay lai CaiDat de sua", "warn")
                        else:
                            raise RuntimeError("Khong luu duoc file output — chay lai CaiDat_MagicVoice.bat de cai ffmpeg")
                else:
                    to_wav(final, path)

                # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): xuat .srt
                # timeline khop audio vua tao.
                try:
                    if getattr(self, "text_srt_timeline_var", None) and self.text_srt_timeline_var.get():
                        _srt_out_path = str(Path(path).with_suffix("")) + "_timeline.srt"
                        _srt_saved_path, _srt_n = _export_srt_timeline(
                            _srt_timeline_data, 0, _srt_out_path)
                        self._log(f"📝 SRT timeline ({_srt_n} dòng): {_srt_saved_path}", "ok")
                except Exception as _srt_exp_err:
                    self._log(f"⚠ Không xuất được .srt timeline: {_srt_exp_err}", "warn")

                total_t = int(time.time() - self._timer_start)
                self._st(f"✅ Edge TTS xong! {total_t}s → {Path(path).name}", P["green"])
                self._log(f"✅ {path}", "ok")
                self.after(0, lambda: self.pb.configure(value=100))
                self.after(100, lambda p=path, t=total_t: self._done_notify(p, t))
                self.after(150, lambda v=voice: self._ensure_edge_preset_visible(v))

        except Exception as e:
            import traceback
            self._log(f"❌ Edge TTS: {e}", "err")
            self._log(traceback.format_exc()[-300:], "err")
            self._st(f"❌ {str(e)[:80]}", P["red"])
        finally:
            self._stop_timer()
            self.after(0, lambda: self.pb.stop())
            self.after(0, lambda: self.pb.configure(mode="determinate", value=100))
            self._busy(False)
            # FIX (bao cao bug 2026-08-14): rmtree truoc day nam CUOI khoi try -
            # neu co loi xay ra o bat ky buoc nao truoc do (mang, ffmpeg, huy
            # giua chung...), thu muc tam ov_edge_* bi bo lai vinh vien tren
            # may khach, tich luy dung luong theo thoi gian. Chuyen vao finally
            # de LUON don dep du thanh cong hay loi.
            try:
                if 'tmp_dir' in dir():
                    import shutil as _sc2
                    _sc2.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def _run_fast_text(self, txt):
        """FIX v3.68 (tinh nang moi 2026-07-25, theo yeu cau anh Bac): doc
        van ban bang mode "MG Nhanh" — chay LOCAL (khong can mang),
        dung _fast_generate() rieng, KHONG dung Backend.gen()/OmniVoice.
        Cau truc phong theo _run_edge_text() (tach doan, noi bang silence,
        luu output) nhung don gian hon vi khong can retry-network/PCM-MP3."""
        if not self._verify_license_or_abort():
            return
        self._busy(True)
        self._start_timer()
        try:
            import torch, tempfile, shutil as _sh0

            voice = self.fast_voice_var.get() if hasattr(self, "fast_voice_var") else FAST_VOICES_LIST[0][0]
            self._log(f"⚡ MG Nhanh | Voice: {voice} | {len(txt)} ký tự", "info")

            paras = [p.strip() for p in txt.split("\n\n") if p.strip()]
            if not paras:
                paras = [txt.strip()]
            total = len(paras)
            self.after(0, lambda: self.pb.configure(mode="determinate", value=0))

            SR = 24000
            parts = []
            silence = torch.zeros(1, int(0.7 * SR))
            speed = self._get_speed()
            # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): [(text, dur_giay)]
            # cho tung doan THANH CONG - dung xuat .srt timeline sau.
            _srt_timeline_data = []

            for pi, para in enumerate(paras):
                if self.cancel_ev.is_set():
                    self._log("⏹ Đã hủy", "warn"); return
                pct = pi / total * 100
                self.after(0, lambda v=pct: self.pb.configure(value=v))
                self._st(f"[{pi+1}/{total}] {para[:45]}…")
                t0 = time.time()
                try:
                    tensor = _fast_generate(para, voice, speed=speed)
                    if tensor is None or tensor.abs().max().item() < 0.0001:
                        self._log(f"  ⚠ [{pi+1}] Audio rỗng — bỏ qua đoạn này", "warn")
                        continue
                    parts.append(tensor)
                    _dur = tensor.shape[-1] / SR
                    if pi < total - 1:
                        parts.append(silence)
                        _dur += 0.7
                    _srt_timeline_data.append((para, _dur))
                    self._log(f"  [{pi+1}/{total}] {time.time()-t0:.1f}s ✓", "info")
                except Exception as _fe:
                    self._log(f"  ✗ [{pi+1}] Lỗi: {_fe}", "err")

            if not parts and not self.cancel_ev.is_set():
                self._log("❌ MG Nhanh: Không tạo được audio.", "err")
                self._st("❌ MG Nhanh thất bại — xem Log", P["red"])
                self.after(0, lambda: messagebox.showerror(
                    "MG Nhanh — Lỗi",
                    "Không tạo được audio.\n\n"
                    "Kiểm tra: đã cài đủ môi trường chưa (chạy lại "
                    "'Cài đặt lại môi trường (Python/AI)' nếu cần).\n\n"
                    "Xem chi tiết trong Log bên phải."))

            if parts and not self.cancel_ev.is_set():
                final = torch.cat(parts, dim=-1)
                if hasattr(self, "post_proc_var") and self.post_proc_var.get():
                    final = _post_process(final, SR)
                _vname = voice
                _fallback = f"{_vname}_Nhanh"
                out_name = self._next_out_name_single(_fallback)
                try:
                    if self.out_ask_name_var.get():
                        _v = self._ask_output_filename(out_name, "Tab Văn Bản (MG Nhanh)")
                        if _v and _v.strip(): out_name = _v.strip()
                except Exception:
                    pass
                path = self._out(name=out_name)
                if path.endswith(".mp3"):
                    to_mp3(final, path)
                    if not os.path.exists(path):
                        _wav_fb = path.replace(".mp3", ".wav")
                        if os.path.exists(_wav_fb):
                            path = _wav_fb
                            self._log("  ⚠ Lưu WAV thay MP3 (ffmpeg chưa cài đầy đủ)", "warn")
                        else:
                            raise RuntimeError("Không lưu được file output — chạy lại CaiDat_MagicVoice.bat để cài ffmpeg")
                else:
                    to_wav(final, path)

                # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): xuat .srt
                # timeline khop audio vua tao.
                try:
                    if getattr(self, "text_srt_timeline_var", None) and self.text_srt_timeline_var.get():
                        _srt_out_path = str(Path(path).with_suffix("")) + "_timeline.srt"
                        _srt_saved_path, _srt_n = _export_srt_timeline(
                            _srt_timeline_data, 0, _srt_out_path)
                        self._log(f"📝 SRT timeline ({_srt_n} dòng): {_srt_saved_path}", "ok")
                except Exception as _srt_exp_err:
                    self._log(f"⚠ Không xuất được .srt timeline: {_srt_exp_err}", "warn")

                total_t = int(time.time() - self._timer_start)
                self._st(f"✅ MG Nhanh xong! {total_t}s → {Path(path).name}", P["green"])
                self._log(f"✅ {path}", "ok")
                self.after(0, lambda: self.pb.configure(value=100))
                self.after(100, lambda p=path, t=total_t: self._done_notify(p, t))
                self.after(150, lambda v=voice: self._ensure_fast_preset_visible(v))

        except Exception as e:
            import traceback
            self._log(f"❌ MG Nhanh: {e}", "err")
            self._log(traceback.format_exc()[-300:], "err")
            self._st(f"❌ {str(e)[:80]}", P["red"])
        finally:
            self._stop_timer()
            self.after(0, lambda: self.pb.stop())
            self.after(0, lambda: self.pb.configure(mode="determinate", value=100))
            self._busy(False)

    def _refresh_srt_voices(self):
        """Cap nhat nhan hien thi (read-only) engine/giong dang dung trong
        tab SRT. FIX v3.68 (theo anh Bac bao loi 2026-07-26): KHONG con
        combobox rieng de chon - tab SRT chi HIEN THI dung engine/giong
        dang active o sidebar (self.tts_mode), tranh lech trang thai.
        Ham nay duoc goi lai o nhieu noi (doi mode sidebar, luu/xoa/chon
        preset, mo tab SRT...) de nhan luon cap nhat kip thoi."""
        if not hasattr(self, "srt_voice_info"):
            return
        _mode = self.tts_mode.get() if hasattr(self, "tts_mode") else "omnivoice"
        # FIX v3.68 (theo anh Bac bao loi 2026-07-26, lan 7): _mode_btns_srt
        # gio la tk.Button kieu pill (khong con Radiobutton do render loi) -
        # can tu cap nhat mau moi lan doi mode, giong het _mode_btns_sb ben
        # sidebar.
        if hasattr(self, "_mode_btns_srt"):
            for v, b in self._mode_btns_srt.items():
                b.config(bg=P["purple"] if v==_mode else P["hover"],
                         fg="white" if v==_mode else P["sub"],
                         font=(FN,8,"bold") if v==_mode else (FN,8,"normal"))

        # Cap nhat combobox chon giong - FIX v3.68 (theo anh Bac bao loi
        # 2026-07-26, lan 5): mode MagicVoice gio CUNG liet ke danh sach
        # preset Clone/Design da luu (truoc day chi Edge/Fast moi co danh
        # sach, MagicVoice de trong khien anh Bac phai chay qua sidebar).
        if hasattr(self, "srt_pick_cb"):
            if _mode == "edge":
                self.srt_pick_cb["values"] = [v[1] for v in EDGE_VOICES_LIST]
            elif _mode == "fast":
                self.srt_pick_cb["values"] = [v[1] for v in FAST_VOICES_LIST]
            else:
                _magic_presets = [vp for vp in self.lib.profiles if vp.mode in ("clone","design")]
                self.srt_pick_cb["values"] = [vp.name for vp in _magic_presets]
            self.srt_pick_cb.pack(side="left")

        if _mode == "edge" and hasattr(self, "edge_voice_var"):
            _code = self.edge_voice_var.get()
            _codes = [v[0] for v in EDGE_VOICES_LIST]
            _label = EDGE_VOICES_LIST[_codes.index(_code)][1] if _code in _codes else _code
            self.srt_voice_info.config(text=f"🌐 Edge — {_label}", fg="#2563eb")
            if hasattr(self, "srt_pick_cb"): self.srt_pick_var.set(_label)
        elif _mode == "fast" and hasattr(self, "fast_voice_var"):
            _code = self.fast_voice_var.get()
            _codes = [v[0] for v in FAST_VOICES_LIST]
            _label = FAST_VOICES_LIST[_codes.index(_code)][1] if _code in _codes else _code
            self.srt_voice_info.config(text=f"⚡ MG Nhanh — {_label}", fg="#0369a1")
            if hasattr(self, "srt_pick_cb"): self.srt_pick_var.set(_label)
        else:
            vp = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
            if vp:
                mode_icon = {"clone":"🎯","design":"✨"}.get(vp.mode,"●")
                self.srt_voice_info.config(text=f"{mode_icon} MagicVoice — {vp.name}", fg=P["purple"])
                if hasattr(self, "srt_pick_cb") and vp.mode in ("clone","design"):
                    self.srt_pick_var.set(vp.name)
            else:
                self.srt_voice_info.config(text="🤖 MagicVoice — (chưa chọn voice)", fg=P["dim"])

    def _do_srt(self):
        """Đọc SRT — tự nhận biết định dạng từ editor nếu chưa parse."""
        # FIX: Tranh double-click khi tac vu chua xong
        if self.is_running:
            messagebox.showinfo("Đang chạy",
                "Đang xử lý tác vụ trước, vui lòng đợi hoặc bấm ⏹ để hủy.")
            return
        # Nếu chưa có entries, tự parse từ editor
        if not self.srt_entries:
            txt = self.srt_editor.get("1.0","end-1c").strip()
            ph  = "Dan van ban / SRT vao day"
            if not txt or txt.startswith(ph[:10]):
                messagebox.showwarning("Trống",
                    "Hãy paste văn bản hoặc SRT vào ô bên trái!"); return
            # Nhận biết SRT hay văn bản thường
            if "-->" in txt:
                self._load_srt_content(txt, "editor")
            else:
                self._text_to_srt_entries(txt)
        if not self.srt_entries:
            messagebox.showwarning("Trống","Không parse được nội dung!"); return
        # FIX: set is_running NGAY truoc khi start thread, tranh race
        self.is_running = True
        self._running_tab = "srt"
        self.after(0, self._refresh_tab_indicators)
        # FIX v3.68 (theo anh Bac bao loi 2026-07-26): tab SRT khong con bo
        # chon rieng (srt_tts_mode) - dispatch THANG theo sidebar
        # (self.tts_mode), CHI 1 nguon duy nhat, khong the lech trang thai.
        _srt_mode = self.tts_mode.get() if hasattr(self, "tts_mode") else "omnivoice"
        if _srt_mode == "edge":
            voice_id = self.edge_voice_var.get() if hasattr(self, "edge_voice_var") else "en-US-AriaNeural"
            class _FakeVP:
                mode = "edge"
                instruct = f"edge:{voice_id}"
                name = voice_id
            threading.Thread(target=self._run_srt_edge,
                             args=(self.srt_entries, _FakeVP()),
                             daemon=True).start()
        elif _srt_mode == "fast":
            voice_id = self.fast_voice_var.get() if hasattr(self, "fast_voice_var") else FAST_VOICES_LIST[0][0]
            class _FakeVPFast:
                mode = "fast"
                instruct = f"fast:{voice_id}"
                name = voice_id
            threading.Thread(target=self._run_srt_fast,
                             args=(self.srt_entries, _FakeVPFast()),
                             daemon=True).start()
        else:
            threading.Thread(target=self._run_srt, daemon=True).start()

    def _text_to_srt_entries(self, txt: str):
        """Chuyển văn bản thường → SRT entries với pause tại dấu câu."""
        import re as _re
        # Tách theo dấu câu lớn (. ! ?) giữ dấu
        sentences = _re.split(r"(?<=[.!?。！？])\s+", txt.strip())
        # Gộp câu ngắn < 20 ký tự vào câu kế tiếp
        merged = []
        buf = ""
        for s in sentences:
            s = s.strip()
            if not s: continue
            if len(buf) + len(s) < 200:
                buf = (buf + " " + s).strip() if buf else s
            else:
                if buf: merged.append(buf)
                buf = s
        if buf: merged.append(buf)

        # Tạo SRT entries với timestamp giả (dùng sequential mode)
        # Không cần timestamp thật vì sẽ dùng sequential mode
        t = 0.0
        entries = []
        for i, sent in enumerate(merged, 1):
            # Ước tính duration: ~15 ký tự/giây, min 1.5s
            dur = max(1.5, len(sent) / 15)
            # Pause thêm sau dấu phẩy/chấm phẩy (0.3s)
            if sent.rstrip()[-1:] in ",.;،،":
                pause = 0.3
            else:
                pause = 0.5
            from dataclasses import dataclass
            e = SRTEntry(
                index=i,
                start=f"00:00:{t:06.3f}".replace(".",","),
                end=f"00:00:{t+dur:06.3f}".replace(".",","),
                text=sent,
                start_ms=int(t*1000),
                end_ms=int((t+dur)*1000),
            )
            entries.append(e)
            t += dur + pause

        self.srt_entries = entries
        # Cập nhật preview
        self.srt_tree.delete(*self.srt_tree.get_children())
        for e in entries:
            self.srt_tree.insert("","end", values=(
                e.index, e.start, e.end,
                e.text.replace("\n"," ")[:120]))
        self.srt_cnt_lbl.config(text=f"{len(entries)} câu")
        self._log(f"✅ Tạo {len(entries)} câu từ văn bản thường","ok")

    def _run_srt_edge(self, entries, vp):
        """Tao SRT bang Edge TTS - danh cho may cau hinh yeu, khong can GPU."""
        # MOI: kiem tra license truoc
        if not self._verify_license_or_abort():
            return
        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): bo dem gio - ham nay
        # co the duoc goi truc tiep (khong qua _run_srt()) khi khach chon
        # san mode Edge o sidebar, nen can tu quan ly start/stop rieng.
        self._start_timer()
        # FIX (bao cao bug 2026-08-14): TRUOC DAY _stop_timer()/_busy(False)
        # chi chay khi ham xong BINH THUONG - neu torch.cat() hoac buoc nao o
        # duoi loi (vd fallback MagicVoice tra ve so kenh audio khac voi cac
        # doan da tich luy), exception se bay len KHONG bi bat, khien nut
        # "Tao" ket disable vinh vien (is_running khong bao gio ve False),
        # khach tuong app treo phai khoi dong lai. Boc try/finally dam bao
        # LUON don dep du co loi hay khong.
        try:
            self._run_srt_edge_body(entries, vp)
        finally:
            self._stop_timer()
            self._busy(False)

    def _run_srt_edge_body(self, entries, vp):
        import asyncio, tempfile, torch, torchaudio as _ta

        # Lay edge voice id
        voice_id = "en-US-AriaNeural"
        if vp.instruct and vp.instruct.startswith("edge:"):
            voice_id = vp.instruct.replace("edge:", "").strip()
        elif hasattr(self, "edge_voice_var"):
            voice_id = self.edge_voice_var.get()

        self._log(f"🌐 SRT Edge TTS | Voice: {voice_id}", "info")
        # Luu phien ngay khi bat dau (de co the goi lai du da dung giua chung)
        try:
            _vname_e = vp.name if vp else ""
            self._save_session(self.srt_editor.get("1.0","end").strip(), _vname_e, self.out_dir_var.get())
        except Exception: pass

        SR = 24000
        silence = torch.zeros(1, int(self.gap_var.get() * SR / 1000))
        _gap_zero = (self.gap_var.get() == 0)
        tensors = []
        all_parts = []
        ok = fail = 0
        total = sum(1 for e in entries if e.text.strip())

        async def _gen_one(text, voice):
            """Gen Edge TTS cho 1 SRT entry voi retry 3 lan + verify file.
            Ho tro edge_tts cu (PCM codec) va moi (>= 6.x, chi co MP3)."""
            import edge_tts, asyncio as _aio, os as _os, wave as _wave, inspect as _ins
            import torchaudio as _ta_one
            _use_pcm = 'codec' in _ins.signature(edge_tts.Communicate.__init__).parameters
            last_err = None
            for _attempt in range(3):
                tmp_wav = tempfile.mktemp(suffix=".wav")
                tmp_pcm = tmp_wav + ".pcm"
                tmp_mp3 = tmp_wav + ".mp3"
                try:
                    if _use_pcm:
                        comm = edge_tts.Communicate(text, voice,
                                                    codec="audio-24khz-16bit-mono-pcm")
                        await comm.save(tmp_pcm)
                        if _os.path.exists(tmp_pcm):
                            sz = _os.path.getsize(tmp_pcm)
                            if sz >= 100:
                                with open(tmp_pcm, "rb") as _f:
                                    _pcm = _f.read()
                                with _wave.open(tmp_wav, "wb") as _wf:
                                    _wf.setnchannels(1); _wf.setsampwidth(2)
                                    _wf.setframerate(24000); _wf.writeframes(_pcm)
                                try: _os.remove(tmp_pcm)
                                except Exception: pass
                                return tmp_wav
                            else:
                                last_err = f"file rong ({sz} bytes)"
                        else:
                            last_err = "file khong duoc tao"
                    else:
                        # edge_tts >= 6.x: luu MP3 roi convert WAV
                        comm = edge_tts.Communicate(text, voice)
                        await comm.save(tmp_mp3)
                        if _os.path.exists(tmp_mp3):
                            sz = _os.path.getsize(tmp_mp3)
                            if sz >= 100:
                                # FIX 11: soundfile backend khong doc MP3 → dung imageio_ffmpeg convert truoc
                                import imageio_ffmpeg as _iff11b
                                import subprocess as _sp11b
                                _wav_tmp11b = tmp_mp3 + "_24k.wav"
                                try:
                                    _sp11b.run(
                                        [_iff11b.get_ffmpeg_exe(), '-i', tmp_mp3,
                                         '-ar', '24000', '-ac', '1', '-f', 'wav',
                                         _wav_tmp11b, '-y', '-loglevel', 'quiet'],
                                        timeout=30, check=True,
                                        creationflags=0x08000000)
                                    _wv, _sr = _safe_audio_load(_wav_tmp11b)
                                finally:
                                    try: _os.remove(_wav_tmp11b)
                                    except Exception: pass
                                if _sr != 24000:
                                    _wv = _ta_one.functional.resample(_wv, _sr, 24000)
                                if _wv.shape[0] > 1:
                                    _wv = _wv.mean(dim=0, keepdim=True)
                                import soundfile as _sf_sv1
                                _sf_sv1.write(tmp_wav, _wv.squeeze().numpy(), 24000, subtype='PCM_16')
                                try: _os.remove(tmp_mp3)
                                except Exception: pass
                                return tmp_wav
                            else:
                                last_err = f"file rong ({sz} bytes)"
                        else:
                            last_err = "file khong duoc tao"
                except Exception as e:
                    last_err = str(e)
                finally:
                    for _p in [tmp_pcm, tmp_mp3]:
                        try:
                            if _os.path.exists(_p): _os.remove(_p)
                        except Exception: pass
                if _attempt < 2:
                    await _aio.sleep(1.5 * (_attempt + 1))
            self._log(f"   ⚠ Edge TTS that bai sau 3 lan: {last_err}", "warn")
            return None

        # Dat ten theo stem file SRT (mode=keep) hoac prefix (mode=prefix)
        _srt_stem = Path(self.srt_path.get()).stem if self.srt_path.get() else ""
        _name = self._next_out_name_single(_srt_stem)
        try:
            if self.out_ask_name_var.get():
                _v = self._ask_output_filename(_name, "Tab SRT (Edge TTS)")
                if _v and _v.strip(): _name = _v.strip()
        except Exception:
            pass
        out = self._out(name=_name)
        if _gap_zero:
            out = str(Path(out).with_suffix(".wav"))
        parts_dir = Path(out).parent / (Path(out).stem + "_parts")
        parts_dir.mkdir(parents=True, exist_ok=True)

        entry_num = 0
        _srt_timeline_data = []  # FIX v3.67: [(text_goc, dur_giay), ...] entry THANH CONG, de xuat .srt timeline sau
        for i, e in enumerate(entries):
            if self.cancel_ev.is_set(): break
            txt = e.text.strip()
            for ch in ["♪","♫","<i>","</i>","<b>","</b>"]:
                txt = txt.replace(ch, "")
            if not txt: continue
            _orig_txt_for_srt = txt  # FIX v3.67: text GOC (truoc phonetic/TTS-friendly) de xuat .srt timeline

            entry_num += 1
            self._st(f"[{entry_num}/{total}] {txt[:50]}")
            self.after(0, lambda v=entry_num/total*100: self.pb.configure(value=v))

            try:
                txt = _apply_phonetic(txt)
                # FIX v3.66: Edge TTS khong tach cau dai (rule B) - xem ghi
                # chu o _do_text().
                if getattr(self, "srt_tts_friendly_var", None) and self.srt_tts_friendly_var.get():
                    txt = _tts_friendly(txt, split_long_sentences=False)
                txt_for_tts = _edge_smart_pause(txt, max_words=8)

                import sys as _sys
                if _sys.platform == "win32":
                    _asyncio_pol = asyncio.WindowsSelectorEventLoopPolicy()
                    asyncio.set_event_loop_policy(_asyncio_pol)
                _evloop = asyncio.new_event_loop()
                try:
                    tmp_wav = _evloop.run_until_complete(_gen_one(txt_for_tts, voice_id))
                finally:
                    _evloop.close()
                if not tmp_wav or not Path(tmp_wav).exists():
                    # FIX v3.68 (theo anh Bac yeu cau 2026-07-30, khach bi
                    # antivirus/firewall chan ket noi Microsoft - khong lien
                    # quan toc do mang): truoc day het 3 lan retry la RAISE
                    # loi luon, ca entry bi bo qua hoan toan - khac voi tab
                    # Van Ban (_run_edge_text) da co san fallback sang
                    # MagicVoice khi Edge TTS loi. Dong bo hoa: tab SRT cung
                    # tu dong dung MagicVoice thay the cho entry loi, thay vi
                    # bo qua/bat khach tu di sua mang/tuong lua.
                    self._log(f"  🔄 [{entry_num}] Edge TTS lỗi — dùng MagicVoice thay thế", "warn")
                    try:
                        kw = self._vkw()
                        t = Backend.gen(txt_for_tts, **kw,
                                         num_step=self._cfg.get("steps", 24),
                                         speed=self._get_speed())
                    except Exception as _fbe:
                        raise RuntimeError(f"Edge TTS loi va Fallback MagicVoice cung loi: {_fbe}")
                else:
                    t, sr = _safe_audio_load(tmp_wav)
                    try: Path(tmp_wav).unlink()
                    except: pass
                    if sr != SR:
                        t = _ta.functional.resample(t, sr, SR)
                    if t.shape[0] > 1:
                        t = t.mean(dim=0, keepdim=True)
                _t = self._trim_sil(t) if _gap_zero else t
                all_parts.append(_t)
                tensors.append(_t)
                if entry_num < total:
                    tensors.append(silence)
                # FIX v3.67: do dai audio THAT cua entry nay (NGAY TRUOC khi
                # chen gap), luu kem text goc de xuat .srt timeline sau khi ghep.
                _srt_timeline_data.append((_orig_txt_for_srt, _t.shape[-1] / SR))
                ok += 1
                self._log(f"  [{entry_num}/{total}] ✓ {txt[:50]}", "info")
                # Luu ngay vao parts_dir sau moi entry (user thay file lien)
                try:
                    if _gap_zero:
                        _pt_save = _t.unsqueeze(0) if _t.dim() == 1 else _t
                        to_wav(_pt_save, str(parts_dir / f"{entry_num:03d}.wav"))
                    else:
                        _pt_save = torch.cat([_t, silence], dim=-1)
                        _pt_save = _pt_save.unsqueeze(0) if _pt_save.dim() == 1 else _pt_save
                        to_mp3(_pt_save, str(parts_dir / f"{entry_num:03d}.mp3"))
                except Exception as _pe:
                    self._log(f"  ⚠ Luu le {entry_num}: {_pe}", "warn")
            except Exception as ex:
                fail += 1
                self._log(f"  [{entry_num}] ❌ {ex}", "err")

        if tensors and not self.cancel_ev.is_set():
            self._log(f"🔗 Ghep {ok} doan...", "info")
            final = torch.cat(tensors, dim=1)
            try:
                actual_out = self._save(final, out)
                if not os.path.exists(actual_out):
                    raise RuntimeError(f"File khong duoc tao: {actual_out}")
                self._log(f"✅ Full: {actual_out}", "ok")
                # FIX v3.67 (tinh nang moi, ap dung ca Edge TTS - xem ghi chu
                # day du o _run_srt()): xuat .srt timeline khop audio vua tao.
                # FIX v3.67 (checkbox bat/tat): CHI xuat neu khach tich chon -
                # tat thi bo qua hoan toan, hanh vi giong het truoc khi co tinh nang.
                try:
                    if self.srt_timeline_var.get():
                        _srt_out_path = str(Path(actual_out).with_suffix("")) + "_timeline.srt"
                        _srt_saved_path, _srt_n = _export_srt_timeline(
                            _srt_timeline_data, self.gap_var.get(), _srt_out_path)
                        self._log(f"📝 SRT timeline ({_srt_n} dòng): {_srt_saved_path}", "ok")
                except Exception as _srt_exp_err:
                    self._log(f"⚠ Không xuất được .srt timeline: {_srt_exp_err}", "warn")
            except Exception as _sv_err:
                self._log(f"❌ Loi luu file: {_sv_err}", "err")
                self.after(0, lambda e=str(_sv_err): messagebox.showerror(
                    "Lỗi lưu file",
                    f"Tạo voice xong nhưng không lưu được!\n\n{e}\n\n"
                    "Kiểm tra: ffmpeg, quyền ghi thư mục, dung lượng ổ đĩa."))
                self._stop_timer()
                self._busy(False)
                return
            self._log(f"📁 Parts ({ok} files): {parts_dir.name}/", "ok")
            self._st(f"✅ Xong! {ok} cau → {Path(actual_out).name}", P["green"])
            self.after(0, lambda: self.pb.configure(value=100))
            self._srt_notify_shown = False  # Reset de lan sau van hien popup
            # Luu phien de goi lai
            _vname = self.lib.profiles[self.sel_idx].name if 0 <= self.sel_idx < len(self.lib.profiles) else ""
            self._save_session(self.srt_editor.get("1.0","end").strip(), _vname, self.out_dir_var.get())
        self.after(100, lambda o=out, d=str(parts_dir): self._done_notify_srt(o, d))

    def _run_srt_fast(self, entries, vp):
        """FIX v3.68 (tinh nang moi 2026-07-25, theo yeu cau anh Bac): tao
        SRT bang mode "MG Nhanh" — phong theo _run_srt_edge() nhung
        dung _fast_generate() (local, khong can mang, khong retry-network)."""
        if not self._verify_license_or_abort():
            return
        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): bo dem gio - ham nay
        # co the duoc goi truc tiep (khong qua _run_srt()) khi khach chon
        # san mode MG Nhanh o sidebar, nen can tu quan ly start/stop rieng.
        self._start_timer()
        # FIX (bao cao bug 2026-08-14): xem ghi chu day du o _run_srt_edge() -
        # cung loai loi, boc try/finally de khong bao gio ket UI vinh vien.
        try:
            self._run_srt_fast_body(entries, vp)
        finally:
            self._stop_timer()
            self._busy(False)

    def _run_srt_fast_body(self, entries, vp):
        import torch

        voice_id = FAST_VOICES_LIST[0][0]
        if vp.instruct and vp.instruct.startswith("fast:"):
            voice_id = vp.instruct.replace("fast:", "").strip()
        elif hasattr(self, "fast_voice_var"):
            voice_id = self.fast_voice_var.get()

        self._log(f"⚡ SRT MG Nhanh | Voice: {voice_id}", "info")
        try:
            _vname_e = vp.name if vp else ""
            self._save_session(self.srt_editor.get("1.0","end").strip(), _vname_e, self.out_dir_var.get())
        except Exception: pass

        SR = 24000
        silence = torch.zeros(1, int(self.gap_var.get() * SR / 1000))
        _gap_zero = (self.gap_var.get() == 0)
        tensors = []
        ok = fail = 0
        total = sum(1 for e in entries if e.text.strip())

        _srt_stem = Path(self.srt_path.get()).stem if self.srt_path.get() else ""
        _name = self._next_out_name_single(_srt_stem)
        try:
            if self.out_ask_name_var.get():
                _v = self._ask_output_filename(_name, "Tab SRT (MG Nhanh)")
                if _v and _v.strip(): _name = _v.strip()
        except Exception:
            pass
        out = self._out(name=_name)
        if _gap_zero:
            out = str(Path(out).with_suffix(".wav"))
        parts_dir = Path(out).parent / (Path(out).stem + "_parts")
        parts_dir.mkdir(parents=True, exist_ok=True)

        entry_num = 0
        _srt_timeline_data = []
        speed = self._get_speed()
        for i, e in enumerate(entries):
            if self.cancel_ev.is_set(): break
            txt = e.text.strip()
            for ch in ["♪","♫","<i>","</i>","<b>","</b>"]:
                txt = txt.replace(ch, "")
            if not txt: continue
            _orig_txt_for_srt = txt

            entry_num += 1
            self._st(f"[{entry_num}/{total}] {txt[:50]}")
            self.after(0, lambda v=entry_num/total*100: self.pb.configure(value=v))

            try:
                t = _fast_generate(txt, voice_id, speed=speed)
                _t = self._trim_sil(t) if _gap_zero else t
                tensors.append(_t)
                if entry_num < total:
                    tensors.append(silence)
                _srt_timeline_data.append((_orig_txt_for_srt, _t.shape[-1] / SR))
                ok += 1
                self._log(f"  [{entry_num}/{total}] ✓ {txt[:50]}", "info")
                try:
                    if _gap_zero:
                        _pt_save = _t.unsqueeze(0) if _t.dim() == 1 else _t
                        to_wav(_pt_save, str(parts_dir / f"{entry_num:03d}.wav"))
                    else:
                        _pt_save = torch.cat([_t, silence], dim=-1)
                        _pt_save = _pt_save.unsqueeze(0) if _pt_save.dim() == 1 else _pt_save
                        to_mp3(_pt_save, str(parts_dir / f"{entry_num:03d}.mp3"))
                except Exception as _pe:
                    self._log(f"  ⚠ Luu le {entry_num}: {_pe}", "warn")
            except Exception as ex:
                fail += 1
                self._log(f"  [{entry_num}] ❌ {ex}", "err")

        if tensors and not self.cancel_ev.is_set():
            self._log(f"🔗 Ghep {ok} doan...", "info")
            final = torch.cat(tensors, dim=1)
            try:
                actual_out = self._save(final, out)
                if not os.path.exists(actual_out):
                    raise RuntimeError(f"File khong duoc tao: {actual_out}")
                self._log(f"✅ Full: {actual_out}", "ok")
                try:
                    if self.srt_timeline_var.get():
                        _srt_out_path = str(Path(actual_out).with_suffix("")) + "_timeline.srt"
                        _srt_saved_path, _srt_n = _export_srt_timeline(
                            _srt_timeline_data, self.gap_var.get(), _srt_out_path)
                        self._log(f"📝 SRT timeline ({_srt_n} dòng): {_srt_saved_path}", "ok")
                except Exception as _srt_exp_err:
                    self._log(f"⚠ Không xuất được .srt timeline: {_srt_exp_err}", "warn")
            except Exception as _sv_err:
                self._log(f"❌ Loi luu file: {_sv_err}", "err")
                self.after(0, lambda e=str(_sv_err): messagebox.showerror(
                    "Lỗi lưu file",
                    f"Tạo voice xong nhưng không lưu được!\n\n{e}\n\n"
                    "Kiểm tra: ffmpeg, quyền ghi thư mục, dung lượng ổ đĩa."))
                self._stop_timer()
                self._busy(False)
                return
            self._log(f"📁 Parts ({ok} files): {parts_dir.name}/", "ok")
            self._st(f"✅ Xong! {ok} cau → {Path(actual_out).name}", P["green"])
            self.after(0, lambda: self.pb.configure(value=100))
            self._srt_notify_shown = False
            _vname = self.lib.profiles[self.sel_idx].name if 0 <= self.sel_idx < len(self.lib.profiles) else ""
            self._save_session(self.srt_editor.get("1.0","end").strip(), _vname, self.out_dir_var.get())
        self.after(100, lambda o=out, d=str(parts_dir): self._done_notify_srt(o, d))

    def _run_srt(self):
        """
        Đọc SRT khớp timeline chính xác bằng ffmpeg adelay:
        1. Tạo WAV cho từng câu SRT
        2. Dùng ffmpeg filter_complex + adelay đặt đúng timestamp
        → Không bị lỗi resample, không bị mất âm
        """
        # MOI: kiem tra license truoc
        if not self._verify_license_or_abort():
            return
        import torchaudio, tempfile
        self._busy(True); self.cancel_ev.clear()
        # Luu phien ngay khi bat dau (de co the goi lai du da dung giua chung)
        try:
            _vname_s = self.lib.profiles[self.sel_idx].name if 0 <= self.sel_idx < len(self.lib.profiles) else ""
            self._save_session(self.srt_editor.get("1.0","end").strip(), _vname_s, self.out_dir_var.get())
        except Exception: pass
        entries   = self.srt_entries
        total     = len(entries)
        _total_nonempty_s = sum(1 for e in entries if e.text.strip() and len(e.text.strip()) >= 2)
        tmp       = Path(tempfile.mkdtemp(prefix="ov_srt_"))
        SR        = 24000
        # Kiểm tra voice trước khi chạy
        if self.sel_idx < 0 or self.sel_idx >= len(self.lib.profiles):
            self._log("❌ Chưa chọn voice! Hãy chọn voice trong danh sách trước khi tạo.", "err")
            self.after(0, lambda: messagebox.showerror(
                "Chưa chọn Voice",
                "Bạn chưa chọn voice!\n\nHãy chọn một voice trong danh sách bên phải rồi bấm Tạo lại."))
            self._busy(False)
            shutil.rmtree(tmp, ignore_errors=True)
            return

        try:
            kw = self._vkw()
        except Exception as _kw_err:
            self._log(f"❌ Loi cau hinh voice: {_kw_err}", "err")
            self.after(0, lambda e=str(_kw_err): messagebox.showerror(
                "Loi Voice",
                f"Khong lay duoc thong tin voice:\n{e}\n\n"
                "Kiem tra lai:\n"
                "  - Da chon voice trong o Voice chua?\n"
                "  - File audio mau con ton tai khong?"))
            self._busy(False)
            shutil.rmtree(tmp, ignore_errors=True)
            return

        # Neu voice mode = edge → dung Edge TTS (nhe hon, cho may yeu)
        vp_cur = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        if vp_cur and vp_cur.mode == "edge":
            self._run_srt_edge(entries, vp_cur)
            shutil.rmtree(tmp, ignore_errors=True)
            return
        # FIX v3.68: Neu voice mode = fast ("MG Nhanh") → dung
        # _fast_generate() (khong can GPU/mang).
        if vp_cur and vp_cur.mode == "fast":
            self._run_srt_fast(entries, vp_cur)
            shutil.rmtree(tmp, ignore_errors=True)
            return

        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): bo dem gio da co san
        # (self._timer_label/_start_timer/_stop_timer) nhung truoc day CHI
        # noi cho tab Van Ban - tab SRT (nhanh MagicVoice mac dinh) chua co,
        # khach khong biet da tao duoc bao lau, de sot ruot.
        self._start_timer()

        # Log rõ voice đang dùng — khách có thể kiểm tra trước khi chờ lâu
        _mode_labels = {"clone": "Clone", "design": "Design", "edge": "Edge TTS"}
        _mode_str = _mode_labels.get(vp_cur.mode, vp_cur.mode or "Default") if vp_cur else "?"
        if not kw:
            self._log(f"⚠ Voice '{vp_cur.name if vp_cur else '?'}' dùng chế độ '{_mode_str}' "
                      f"— không có ref_audio/instruct → sẽ dùng giọng mặc định!", "warn")
        else:
            self._log(f"🎤 SRT MagicVoice | Voice: {vp_cur.name if vp_cur else '?'} "
                      f"[{_mode_str}] | {total} câu", "info")

        try:
            # ══ Sequential mode: ghép tuần tự ═══════════════════════
            self._log("🔗 Sequential mode — ghép tuần tự", "info")
            import torch
            # Canh bao lan dau tao voice trong phien (torch.compile warm-up)
            if not getattr(Backend, '_warmed_up', False):
                self._log("⚠ Lan dau tao voice: CUDA dang khoi dong (~2-5 phut). Vui long doi, dung tat app!", "warn")
                self._st("Dang khoi dong CUDA lan dau — vui long doi...", "#f59e0b")
            tensors   = []   # chi audio, khong silence
            _gap_zero = (self.gap_var.get() == 0)
            silence   = torch.zeros(1, int(self.gap_var.get() * SR / 1000))
            all_parts = []   # list tensor audio rieng le
            ok = fail = 0

            # ── Tạo thư mục voice_le NGAY KHI BẮT ĐẦU (như batch tab) ──
            _srt_stem_pre = Path(self.srt_path.get()).stem if self.srt_path.get() else ""
            _name_pre = self._next_out_name_single(_srt_stem_pre)
            try:
                if self.out_ask_name_var.get():
                    _v = self._ask_output_filename(_name_pre, "Tab SRT (Sequential mode)")
                    if _v and _v.strip(): _name_pre = _v.strip()
            except Exception: pass
            _out_pre = self._out(name=_name_pre)
            if _gap_zero:
                _out_pre = str(Path(_out_pre).with_suffix(".wav"))
            _parts_dir = Path(_out_pre).parent / (Path(_out_pre).stem + "_le")
            _parts_dir.mkdir(parents=True, exist_ok=True)
            self._log(f"📁 Thư mục voice lẻ: {_parts_dir}", "info")
            _part_ext = ".wav" if _gap_zero else ".mp3"

            entry_num = 0  # dem so entry SRT thuc su (co text)
            _srt_timeline_data = []  # FIX v3.67: [(text_goc, dur_giay), ...] entry THANH CONG, de xuat .srt timeline sau
            for i, e in enumerate(entries):
                if self.cancel_ev.is_set(): break
                txt = e.text.strip().replace('\n', ' ')
                for ch in ["♪","♫","<i>","</i>","<b>","</b>"]:
                    txt = txt.replace(ch, "")
                # NOTE: KHONG normalize curly quotes - OmniVoice xu ly duoc U+201C/201D/2018/2019
                # FIX 20: normalize \n -> space (SRT dung nhieu dong de hien thi, khong phai ngat cau)
                # Backend.gen() tu reset seed(42)+cuda+empty_cache ben trong → khong can FIX 17 ben ngoai
                if not txt: continue
                _orig_txt_for_srt = txt  # FIX v3.67: text GOC (truoc phonetic/TTS-friendly) de xuat .srt timeline
                txt = _apply_phonetic(txt)
                # Toi uu doc (TTS-friendly): chi sua CHU trong entry nay,
                # khong tao/xoa entry, khong dam timestamp.
                # FIX v3.66 (audit 2026-07-24): bo qua TTS-friendly khi
                # mode=clone - xem ghi chu day du o _do_text() (tab Van Ban).
                if (getattr(self, "srt_tts_friendly_var", None) and self.srt_tts_friendly_var.get()
                        and not (vp_cur and vp_cur.mode == "clone")):
                    txt = _tts_friendly(txt)

                entry_num += 1
                self._st(f"[{entry_num}/{total}] {txt[:50]}")
                self.after(0, lambda v=i/total*100: self.pb.configure(value=v))
                try:
                    # Entry ngan (< 350 chars): 1 chunk, khong trim → giu ngat nghi tu nhien OmniVoice (nhu v3.55)
                    # Entry dai (>= 350 chars): split tai ranh gioi cau, trim per-chunk, noi bang silence 350ms
                    _gap_zero = (self.gap_var.get() == 0)
                    _segs = _smart_chunks(txt, SR)
                    _seg_parts = []
                    _seg_pauses = []
                    for _ck, _pause_ms in _segs:
                        _at, _vok, _vtr = _gen_verified(
                            _ck, self.steps_var.get(), self._get_speed(),
                            kw, log_fn=self._log)
                        _seg_parts.append(_at)
                        _seg_pauses.append(_pause_ms)
                    if len(_seg_parts) > 1:
                        # Entry dai: trim per-chunk roi noi — tranh double silence tai diem noi
                        _joined = []
                        for _pi, _pt in enumerate(_seg_parts):
                            _joined.append(self._trim_tail(self._trim_sil(_pt)))
                            if _pi < len(_seg_parts) - 1:
                                _sil_ms = max(_seg_pauses[_pi], 80)
                                _joined.append(torch.zeros(1, int(_sil_ms * SR / 1000)))
                        _out_t = torch.cat(_joined, dim=-1)
                    else:
                        # Entry ngan (1 chunk): khong trim — giu ngat nghi tu nhien OmniVoice sinh ra (nhu v3.55)
                        _out_t = _seg_parts[0] if _seg_parts else torch.zeros(1, 1)
                    _le_silence = torch.zeros(1, int(self.gap_var.get() * SR / 1000))
                    # Trim CHI leading silence (cat dau): loai bo OmniVoice natural leading sil
                    # GIU trailing silence tu nhien de effective gap = natural_trailing + gap_var (nhu cu)
                    if not _gap_zero:
                        _wls = max(1, int(10 * SR / 1000))
                        _abs_ls = _out_t.abs().squeeze(0)
                        _n_ls = _abs_ls.shape[0]
                        _pad_ls = (_wls - _n_ls % _wls) % _wls
                        _sp_ls = torch.nn.functional.pad(_abs_ls, (0, _pad_ls))
                        _rms_ls = _sp_ls.reshape(-1, _wls).mean(dim=1)
                        _act_ls = (_rms_ls > 0.01).nonzero(as_tuple=False)
                        _out_t_m = _out_t[:, _act_ls[0].item() * _wls:] if len(_act_ls) > 0 else _out_t
                    else:
                        _out_t_m = _out_t
                    tensors.append(_out_t_m)
                    if entry_num < _total_nonempty_s:
                        tensors.append(silence)
                    # FIX v3.67: do dai audio THAT cua entry nay (NGAY TRUOC khi
                    # chen gap - dung SR that de doi ra giay), luu kem text goc
                    # de xuat .srt timeline sau khi ghep xong.
                    _srt_timeline_data.append((_orig_txt_for_srt, _out_t_m.shape[-1] / SR))
                    ok += 1
                    self._log(f"  [{entry_num}/{total}] ✓ {txt[:50]}", "info")
                    # Lưu voice lẻ NGAY sau khi tạo xong — mọi file đều có gap ở đuôi
                    try:
                        _pi_path = str(_parts_dir / f"{entry_num:03d}{_part_ext}")
                        if _gap_zero:
                            _save_raw = _out_t
                            _save_t = _save_raw.unsqueeze(0) if _save_raw.dim() == 1 else _save_raw
                            to_wav(_save_t, _pi_path)
                        else:
                            _save_raw = torch.cat([_out_t_m, _le_silence], dim=-1)
                            _save_t = _save_raw.unsqueeze(0) if _save_raw.dim() == 1 else _save_raw
                            to_mp3(_save_t, _pi_path)
                    except Exception as _pe:
                        self._log(f"  ⚠ Lưu lẻ {entry_num}: {_pe}", "warn")
                    if ok == 1:
                        Backend._warmed_up = True
                except Exception as ex:
                    fail += 1
                    self._log(f"  [{entry_num}] ❌ {ex}", "err")

            if tensors and not self.cancel_ev.is_set():
                # Dùng output path + thư mục đã tạo sẵn từ trước vòng lặp
                out      = _out_pre
                parts_dir = _parts_dir
                self._log(f"✅ {ok} voice lẻ → {parts_dir.name}/", "ok")

                # Ghep hoan chinh
                final = torch.cat(tensors, dim=1)
                if hasattr(self,"post_proc_var") and self.post_proc_var.get():
                    final = _post_process(final, SR)
                try:
                    self._save(final, out)
                    # Kiem tra file co thuc su duoc tao khong
                    _saved = out if os.path.exists(out) else out.replace(".mp3", ".wav")
                    if not os.path.exists(_saved):
                        raise RuntimeError(f"File khong duoc tao tai: {out}")
                    self._st(f"✅ Xong! {ok} câu → {Path(_saved).name}", P["green"])
                    self._log(f"✅ Full: {_saved}", "ok")
                    # FIX v3.67 (tinh nang moi, theo yeu cau anh Bac): xuat them
                    # 1 file .srt co timeline khop CHINH XAC audio vua tao (SRT
                    # goc bi lech vi giong doc tu nhien nhanh/cham khac). Text
                    # moi dong = text GOC entry (khong transcribe/Whisper).
                    # Hoan toan doc-only voi luong tao voice - khong sua gi ben tren.
                    # FIX v3.67 (checkbox bat/tat): CHI xuat neu khach tich chon -
                    # tat thi bo qua hoan toan, hanh vi giong het truoc khi co tinh nang.
                    try:
                        if self.srt_timeline_var.get():
                            _srt_out_path = str(Path(_saved).with_suffix("")) + "_timeline.srt"
                            _srt_saved_path, _srt_n = _export_srt_timeline(
                                _srt_timeline_data, self.gap_var.get(), _srt_out_path)
                            self._log(f"📝 SRT timeline ({_srt_n} dòng): {_srt_saved_path}", "ok")
                    except Exception as _srt_exp_err:
                        self._log(f"⚠ Không xuất được .srt timeline: {_srt_exp_err}", "warn")
                except Exception as _save_err:
                    self._log(f"❌ Loi luu file: {_save_err}", "err")
                    self._st(f"❌ Lỗi lưu file: {_save_err}", "red")
                    self.after(0, lambda e=str(_save_err): messagebox.showerror(
                        "Lỗi lưu file",
                        f"Tạo voice xong nhưng không lưu được file!\n\n{e}\n\n"
                        f"Thư mục output: {self.out_dir_var.get()}\n"
                        "Kiểm tra: ffmpeg, quyền ghi thư mục, dung lượng ổ đĩa."))
                self._log(f"📁 Parts: {parts_dir}", "ok")
                self.after(0, lambda: self.pb.configure(value=100))
                self._srt_notify_shown = False  # Reset de lan sau van hien popup
                # Luu phien de goi lai
                _vname = self.lib.profiles[self.sel_idx].name if 0 <= self.sel_idx < len(self.lib.profiles) else ""
                self._save_session(self.srt_editor.get("1.0","end").strip(), _vname, self.out_dir_var.get())
                self.after(100, lambda o=out, d=str(parts_dir): self._done_notify_srt(o, d))

        except RuntimeError as _srt_rt:
            _msg = str(_srt_rt)
            self._log(f"❌ {_msg[:200]}", "err")
            if "out of memory" in _msg.lower() or "CUDA" in _msg:
                _show = ("CUDA het bo nho!\n\nGiam Steps xuong 4-8\n"
                         "Doi sang float16 hoac CPU\nVan ban ngan hon")
            else:
                _show = _msg[:300]
            self.after(0, lambda m=_show: messagebox.showerror("Loi SRT", m))
        except Exception as _srt_err:
            import traceback
            self._log(f"❌ Loi tao SRT: {_srt_err}", "err")
            self._log(traceback.format_exc()[-300:], "err")
            self.after(0, lambda e=str(_srt_err): messagebox.showerror(
                "Loi tao SRT", f"{e[:300]}"))
        finally:
            self._stop_timer()
            shutil.rmtree(tmp, ignore_errors=True)
            self._busy(False)

    # ══ MOI: Naming helpers & dialog TOAN CUC (ap dung cho moi tab) ══
    def _compute_output_name(self, src_stem: str = "", idx: int = 0) -> str:
        """Tinh ten output (khong co extension) theo cau hinh global.
        src_stem: ten goc (dung cho mode 'keep')
        idx: zero-based index trong 1 lot (cho tab Batch hoac SRT nhieu entry).
             Tab Text/SRT don le -> dung counter offset session."""
        try:
            mode = self.out_name_mode.get()
        except Exception:
            mode = "prefix"
        if mode == "keep":
            return (src_stem or "output").strip() or "output"
        # Mode: prefix + number
        try:
            pr  = (self.out_prefix_var.get() or "voice_").strip() or "voice_"
            st  = int(self.out_start_var.get())
            pad = max(1, int(self.out_pad_var.get()))
        except Exception:
            pr, st, pad = "voice_", 1, 2
        n = st + idx
        return f"{pr}{n:0{pad}d}"

    def _next_out_name_single(self, src_stem: str = "") -> str:
        """Sinh ten cho 1 file don le (tab Text/SRT).
        Neu mode='prefix' -> dung counter offset + quet thu muc de khong trung so.
        Neu mode='keep' va co src_stem -> dung src_stem.
        Neu mode='keep' va khong co src_stem (tab Text/SRT ko co file nguon) -> prefix."""
        try:
            mode = self.out_name_mode.get()
        except Exception:
            mode = "prefix"
        if mode == "keep" and src_stem.strip():
            return src_stem.strip()
        # prefix mode: tim so thap nhat chua bi dung trong out_dir
        try:
            pr  = (self.out_prefix_var.get() or "voice_").strip() or "voice_"
            st  = int(self.out_start_var.get())
            pad = max(1, int(self.out_pad_var.get()))
            fmt = self.fmt_var.get() if hasattr(self, "fmt_var") else ".mp3"
            d   = self.out_dir_var.get()
        except Exception:
            return self._compute_output_name(src_stem, 0)
        import os as _os
        try:
            _os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        i = 0
        while True:
            n = st + self._out_counter_offset + i
            name = f"{pr}{n:0{pad}d}"
            # Check trung ca .mp3 va .wav de an toan
            if not (_os.path.exists(_os.path.join(d, name + fmt))
                    or _os.path.exists(_os.path.join(d, name + ".mp3"))
                    or _os.path.exists(_os.path.join(d, name + ".wav"))):
                self._out_counter_offset += i + 1  # lan sau nhay tiep
                return name
            i += 1
            if i > 9999:
                # Tranh infinite loop bat ngo
                import time as _t
                return f"{pr}{int(_t.time())}"

    def _ask_output_filename(self, default_name: str, src_label: str = ""):
        """Hien dialog hoi ten truoc khi luu. Tra None neu user huy."""
        from tkinter import simpledialog
        result = {"v": None, "done": False}
        def _ask():
            v = simpledialog.askstring(
                "Đặt tên file output",
                (f"Nguồn: {src_label}\n\n" if src_label else "") +
                "Tên file output (không cần phần mở rộng):",
                initialvalue=default_name, parent=self)
            result["v"] = v
            result["done"] = True
        self.after(0, _ask)
        # Neu duoc goi tu worker thread -> poll; neu tu main thread -> chay luon
        import threading as _th, time as _t
        if _th.current_thread() is _th.main_thread():
            # Khong poll duoc tren main thread -> xu ly sync
            _ask()
        else:
            for _ in range(600):  # ~10 phut
                if result["done"] or not self.is_running:
                    break
                _t.sleep(1.0)
        return result["v"]

    def _show_naming_dialog(self):
        """Dialog cau hinh dat ten file output toan cuc."""
        dlg = tk.Toplevel(self)
        dlg.title("🏷 Cấu hình tên file output")
        dlg.transient(self); dlg.grab_set()
        dlg.configure(bg=P["white"])
        dlg.resizable(False, False)

        pad = tk.Frame(dlg, bg=P["white"]); pad.pack(padx=18, pady=16)

        tk.Label(pad, text="Áp dụng cho MỌI tab (Văn Bản, SRT, Hàng Loạt)",
                 font=(FN,9,"italic"), bg=P["white"], fg=P["dim"]
                 ).pack(anchor="w", pady=(0,10))

        # Radio mode
        rf = tk.Frame(pad, bg=P["white"]); rf.pack(fill="x", pady=2)
        tk.Label(rf, text="Chế độ:", font=(FN,10,"bold"),
                 bg=P["white"], fg=P["label"], width=10, anchor="w").pack(side="left")
        tk.Radiobutton(rf, text="Tiền tố + số thứ tự", variable=self.out_name_mode,
                       value="prefix", font=(FN,9), bg=P["white"], fg=P["label"],
                       selectcolor=P["white"], activebackground=P["white"],
                       cursor="hand2").pack(side="left")
        tk.Radiobutton(rf, text="Giữ tên gốc", variable=self.out_name_mode,
                       value="keep", font=(FN,9), bg=P["white"], fg=P["label"],
                       selectcolor=P["white"], activebackground=P["white"],
                       cursor="hand2").pack(side="left", padx=(12,0))

        # Prefix
        for label, var, width in [("Tiền tố:", self.out_prefix_var, 18),
                                  ("Bắt đầu từ:", self.out_start_var, 8),
                                  ("Số chữ số:", self.out_pad_var, 6)]:
            row = tk.Frame(pad, bg=P["white"]); row.pack(fill="x", pady=3)
            tk.Label(row, text=label, font=(FN,10),
                     bg=P["white"], fg=P["label"], width=10, anchor="w"
                     ).pack(side="left")
            tk.Entry(row, textvariable=var, font=(FN,10),
                     relief="flat", bg=P["sidebar"], fg=P["text"],
                     highlightthickness=1, highlightbackground=P["border"],
                     highlightcolor=P["purple"], width=width
                     ).pack(side="left", ipady=3)

        # Checkbox: ask before save
        arow = tk.Frame(pad, bg=P["white"]); arow.pack(fill="x", pady=(8,2))
        tk.Checkbutton(arow,
                       text="Hỏi tên từng file trước khi lưu (để đặt tên dễ nhận biết)",
                       variable=self.out_ask_name_var,
                       font=(FN,9), bg=P["white"], fg=P["label"],
                       selectcolor=P["white"], activebackground=P["white"],
                       cursor="hand2").pack(anchor="w")

        # Preview
        prev_lbl = tk.Label(pad, text="", font=(FN,9,"italic"),
                            bg=P["white"], fg=P["purple"])
        prev_lbl.pack(anchor="w", pady=(8,2))
        def _upd_preview(*a):
            try:
                if self.out_name_mode.get() == "keep":
                    prev_lbl.config(text="→ Ví dụ: giữ nguyên tên file nguồn")
                else:
                    pr  = self.out_prefix_var.get() or "voice_"
                    st  = int(self.out_start_var.get())
                    pd  = max(1, int(self.out_pad_var.get()))
                    prev_lbl.config(
                        text=f"→ Ví dụ: {pr}{st:0{pd}d}.mp3, {pr}{st+1:0{pd}d}.mp3, {pr}{st+2:0{pd}d}.mp3, …")
            except Exception:
                prev_lbl.config(text="")
        for _v in (self.out_name_mode, self.out_prefix_var,
                   self.out_start_var, self.out_pad_var):
            _v.trace_add("write", _upd_preview)
        _upd_preview()

        # Buttons
        btns = tk.Frame(pad, bg=P["white"]); btns.pack(fill="x", pady=(14,0))
        def _reset_counter():
            self._out_counter_offset = 0
            self._log("🔄 Reset bộ đếm số thứ tự file về 0", "info")
        tk.Button(btns, text="🔄 Reset bộ đếm",
                  command=_reset_counter,
                  font=(FN,9), bg=P["bg"], fg=P["sub"],
                  relief="flat", cursor="hand2", padx=10, pady=5
                  ).pack(side="left")
        tk.Button(btns, text="✅ Đóng", command=dlg.destroy,
                  font=(FN,10,"bold"), bg=P["purple"], fg="white",
                  relief="flat", cursor="hand2", padx=18, pady=6
                  ).pack(side="right")

    # ══ (Batch helpers - giu nguyen de tuong thich) ══
    def _do_batch(self):
        if not self._txt_files:
            messagebox.showwarning("Trống","Chưa có file nào!"); return
        if self.is_running:
            messagebox.showinfo("Đang chạy","Đang xử lý tác vụ khác, vui lòng đợi!")
            return
        # MOI: Check model load truoc khi start thread
        if not self.model_loaded:
            messagebox.showwarning("Chưa tải model","Nhấn '⬇ Tải Model' trước khi bắt đầu batch!")
            return
        # MOI: Check voice da chon chua
        try:
            _ = self._vkw()
        except Exception as _kw_err:
            messagebox.showerror("Lỗi Voice",
                f"Không thể bắt đầu batch vì cấu hình voice có vấn đề:\n\n{_kw_err}\n\n"
                "Hãy kiểm tra lại voice đang chọn (clone thì cần ref_audio).")
            return
        # MOI: set is_running NGAY de tranh race khi double-click
        self.is_running = True
        self._running_tab = "batch"
        self.after(0, self._refresh_tab_indicators)
        # Hiện tiến độ trong preview box
        try:
            self.batch_preview.config(state="normal")
            self.batch_preview.delete("1.0", "end")
            self.batch_preview.insert("1.0", f"⏳ Đang chuẩn bị batch {len(self._txt_files)} file...")
            self.batch_preview.config(state="disabled")
            self.batch_preview_info.config(text=f"0 / {len(self._txt_files)} file")
        except Exception:
            pass

        # MOI: thong bao ro rang de user biet da start
        self._log(f"▶ Bắt đầu batch: {len(self._txt_files)} file", "info")
        self._st(f"▶ Đang chuẩn bị batch ({len(self._txt_files)} file)...", P["blue"])
        threading.Thread(target=self._run_batch,daemon=True).start()

    def _batch_on_select(self, event=None):
        """Khi user click 1 file trong listbox -> hien noi dung preview."""
        try:
            sel = self.batch_lb.curselection()
            if not sel:
                return
            idx = sel[0]
            if idx >= len(self._txt_files):
                return
            fp = self._txt_files[idx]
            ext = Path(fp).suffix.lower()
            try:
                content = Path(fp).read_text("utf-8", errors="ignore")
            except Exception as e:
                content = f"[Không đọc được file: {e}]"

            # Thong tin ngan o header
            n_lines = content.count("\n") + 1
            n_chars = len(content)
            info = f"{Path(fp).name}  •  {n_chars:,} ký tự  •  {n_lines:,} dòng"
            if ext == ".srt":
                try:
                    n_entries = len(parse_srt(content))
                    info += f"  •  {n_entries} entries"
                except Exception:
                    pass
            self.batch_preview_info.config(text=info)

            # Cap nhat preview box
            self.batch_preview.config(state="normal")
            self.batch_preview.delete("1.0", "end")
            # Gioi han 50KB cho preview kho phai load file khong lo
            if len(content) > 50000:
                self.batch_preview.insert("1.0",
                    content[:50000] + "\n\n[... đã cắt, file quá lớn để preview đầy đủ ...]")
            else:
                self.batch_preview.insert("1.0", content)
            self.batch_preview.config(state="disabled")
            self.batch_preview.see("1.0")
        except Exception as e:
            # Khong de exception vo tinh pha app
            try:
                self._log(f"⚠ Preview lỗi: {e}", "warn")
            except Exception:
                pass

    # ── Helpers cho batch naming ──────────────────────────────────────
    # (Giu lai de tuong thich - delegate sang helper global)
    def _batch_compute_output_name(self, src_path: str, idx0: int) -> str:
        """DEPRECATED: dung _compute_output_name. Giu de khong break code cu."""
        return self._compute_output_name(Path(src_path).stem, idx0)

    def _batch_ask_filename(self, default_name: str, src_path: str):
        """DEPRECATED: dung _ask_output_filename."""
        return self._ask_output_filename(default_name, Path(src_path).name)

    def _batch_gen_srt_file(self, srt_path: str, kw: dict, parts_dir: str = None, on_entry_progress=None):
        """Sinh audio tu 1 file .srt: parse -> gen tung entry -> concat.
        Tra ve (final_tensor, entry_tensors) hoac (None, None) neu rong/huy.
          final_tensor: tensor da noi + silence giua cac entry
          entry_tensors: list[tensor] tung entry rieng le
          parts_dir: neu co, luu tung entry ngay vao parts_dir/001.mp3, 002.mp3...
          on_entry_progress(j, status, total_e, part_idx): callback tien do tung dong
        Khong post-process (se lam trong _save)."""
        import torch
        try:
            raw = Path(srt_path).read_text("utf-8").strip()
        except Exception:
            raw = Path(srt_path).read_text("utf-8", errors="ignore").strip()
        if not raw: return None, None, None
        entries = parse_srt(raw)
        if not entries:
            # Fallback: coi nhu van ban thuong, tach theo dau cau
            return None, None, None

        SR    = 24000
        gap   = int(self.gap_var.get())
        steps = self.steps_var.get()
        speed = self._get_speed()
        silence = torch.zeros(1, int(gap * SR / 1000))

        tensors = []        # de ghep final (co silence giua)
        entry_tensors = []  # tung entry rieng
        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): text GOC tuong ung
        # tung entry_tensors, dung xuat .srt timeline sau (xem _run_batch).
        entry_texts = []
        ok = skip = part_idx = 0
        total_e = len(entries)
        _total_nonempty = sum(1 for e in entries if e.text.strip() and len(e.text.strip()) >= 2)
        for j, e in enumerate(entries):
            if self.cancel_ev.is_set(): return None, None, None
            txt = e.text.strip()
            # Lam sach nhac cu / tag HTML
            import re as _re
            for ch in ["♪","♫","♩","♬"]:
                txt = txt.replace(ch, "")
            txt = _re.sub(r"<[^>]+>", "", txt).strip()
            if not txt or len(txt) < 2:
                skip += 1
                continue
            _orig_txt_for_srt = txt  # FIX v3.68: text GOC truoc phonetic/TTS-friendly, dung xuat .srt timeline
            txt = _apply_phonetic(txt)
            # FIX v3.66 (audit 2026-07-24): bo qua TTS-friendly khi mode=
            # clone - ham nay CHI duoc goi cho profile khong phai edge (xem
            # _run_batch), nen co the la clone hoac design. Xem ghi chu day
            # du o _do_text() (tab Van Ban).
            _vp_batch_srt = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
            if (getattr(self, "srt_tts_friendly_var", None) and self.srt_tts_friendly_var.get()
                    and not (_vp_batch_srt and _vp_batch_srt.mode == "clone")):
                txt = _tts_friendly(txt)
            if on_entry_progress:
                on_entry_progress(j, "start", total_e, part_idx)
            try:
                # Dung _smart_chunks de tranh OmniVoice _generate_chunked()
                import torch as _tch
                _bsegs = _smart_chunks(txt, SR)
                _bparts = []
                _b_multi = len(_bsegs) > 1  # entry dai -> nhieu chunk
                for _bck, _bpause in _bsegs:
                    # FIX v3.66 (hieu nang 2026-07-24): dung _gen_cached thay
                    # Backend.gen() truc tiep - tranh Clone Voice phien am lai
                    # audio mau moi chunk (xem ghi chu day du o _gen_cached).
                    _ba = _gen_cached(_bck, steps, speed, kw)
                    _bt = _to_tensor(_ba)
                    if _bt is None or _bt.abs().max() < 0.0001:
                        continue
                    if _b_multi:
                        # Entry dai: trim trailing silence tung chunk tranh double silence tai diem noi
                        _bt_s = _bt.abs().squeeze(0)
                        _win = max(1, int(10 * SR / 1000))
                        _pad = (_win - _bt_s.shape[0] % _win) % _win
                        _sp = _tch.nn.functional.pad(_bt_s, (0, _pad))
                        _rms = _sp.reshape(-1, _win).mean(dim=1)
                        _act = (_rms > 0.01).nonzero(as_tuple=False)
                        if len(_act) > 0:
                            _end = min(_bt_s.shape[0], (_act[-1].item() + 1) * _win)
                            _bt = _bt[:, :_end]
                    # Entry ngan (1 chunk): giu audio tho, khong trim — bao toan ngat nghi tu nhien OmniVoice (nhu v3.55)
                    _bparts.append(_bt)
                    if _bpause > 0:
                        _bparts.append(_tch.zeros(1, int(_bpause * SR / 1000)))
                if not _bparts:
                    if on_entry_progress:
                        on_entry_progress(j, "skip", total_e, part_idx)
                    skip += 1; continue
                t = _tch.cat(_bparts, dim=-1)
                if t is None or t.abs().max() < 0.0001:
                    if on_entry_progress:
                        on_entry_progress(j, "skip", total_e, part_idx)
                    skip += 1; continue
                # Trim CHI leading silence (cat dau, giu trailing tu nhien cua OmniVoice)
                # → effective gap = OmniVoice_natural_trailing + gap_var (nhu phien ban cu)
                if gap > 0:
                    _wlb = max(1, int(10 * SR / 1000))
                    _abs_lb = t.abs().squeeze(0)
                    _n_lb = _abs_lb.shape[0]
                    _pad_lb = (_wlb - _n_lb % _wlb) % _wlb
                    _sp_lb = _tch.nn.functional.pad(_abs_lb, (0, _pad_lb))
                    _rms_lb = _sp_lb.reshape(-1, _wlb).mean(dim=1)
                    _act_lb = (_rms_lb > 0.01).nonzero(as_tuple=False)
                    _t_clean = t[:, _act_lb[0].item() * _wlb:] if len(_act_lb) > 0 else t
                else:
                    _t_clean = t
                tensors.append(_t_clean)
                entry_tensors.append(_t_clean)
                entry_texts.append(_orig_txt_for_srt)
                part_idx += 1
                if parts_dir:
                    try:
                        _mp3 = os.path.join(parts_dir, f"{part_idx:03d}.mp3")
                        if gap > 0:
                            _gap_sil = _tch.zeros(1, int(gap * SR / 1000))
                            _out_t = _tch.cat([_t_clean, _gap_sil], dim=-1)
                        else:
                            _out_t = _t_clean
                        _out_t = _out_t.unsqueeze(0) if _out_t.dim() == 1 else _out_t
                        to_mp3(_out_t, _mp3)
                    except Exception:
                        pass
                if on_entry_progress:
                    on_entry_progress(j, "ok", total_e, part_idx)
                if part_idx < _total_nonempty:
                    tensors.append(silence)
                ok += 1
            except Exception as _ge:
                self._log(f"    ⚠ entry {j+1}: {_ge}", "warn")
                if on_entry_progress:
                    on_entry_progress(j, "skip", total_e, part_idx)
                skip += 1
        if not tensors:
            return None, None, None
        self._log(f"    🎞 {ok} entry OK, {skip} bỏ qua → ghép", "info")
        return torch.cat(tensors, dim=1), entry_tensors, entry_texts

    def _batch_gen_srt_file_edge(self, srt_path: str, vp, parts_dir: str = None, on_entry_progress=None) -> tuple:
        """Edge TTS version of _batch_gen_srt_file. Returns (final_tensor, entry_tensors)."""
        import asyncio, tempfile, torch, torchaudio as _ta, re as _re
        voice_id = "en-US-AriaNeural"
        if vp.instruct and vp.instruct.startswith("edge:"):
            voice_id = vp.instruct.replace("edge:", "").strip()
        try:
            raw = Path(srt_path).read_text("utf-8").strip()
        except Exception:
            raw = Path(srt_path).read_text("utf-8", errors="ignore").strip()
        if not raw: return None, None, None
        entries = parse_srt(raw)
        if not entries: return None, None, None

        SR = 24000
        gap_be = int(self.gap_var.get())
        silence = torch.zeros(1, int(gap_be * SR / 1000))
        tensors = []
        entry_tensors = []
        entry_texts = []
        ok = skip = 0
        total_e = len(entries)
        _total_nonempty_be = sum(1 for e in entries if e.text.strip() and len(e.text.strip()) >= 2)

        async def _gen_one(text, voice):
            import edge_tts, asyncio as _aio, os as _os, wave as _wave, inspect as _ins
            import torchaudio as _ta_one
            _use_pcm = 'codec' in _ins.signature(edge_tts.Communicate.__init__).parameters
            last_err = None
            for _attempt in range(3):
                tmp_wav = tempfile.mktemp(suffix=".wav")
                tmp_pcm = tmp_wav + ".pcm"
                tmp_mp3 = tmp_wav + ".mp3"
                try:
                    if _use_pcm:
                        comm = edge_tts.Communicate(text, voice,
                                                    codec="audio-24khz-16bit-mono-pcm")
                        await comm.save(tmp_pcm)
                        if _os.path.exists(tmp_pcm):
                            sz = _os.path.getsize(tmp_pcm)
                            if sz >= 100:
                                with open(tmp_pcm, "rb") as _f:
                                    _pcm = _f.read()
                                with _wave.open(tmp_wav, "wb") as _wf:
                                    _wf.setnchannels(1); _wf.setsampwidth(2)
                                    _wf.setframerate(24000); _wf.writeframes(_pcm)
                                try: _os.remove(tmp_pcm)
                                except Exception: pass
                                return tmp_wav
                            else:
                                last_err = f"file rong ({sz} bytes)"
                        else:
                            last_err = "file khong duoc tao"
                    else:
                        comm = edge_tts.Communicate(text, voice)
                        await comm.save(tmp_mp3)
                        if _os.path.exists(tmp_mp3):
                            sz = _os.path.getsize(tmp_mp3)
                            if sz >= 100:
                                import imageio_ffmpeg as _iff
                                import subprocess as _sp
                                _wav_tmp = tmp_mp3 + "_24k.wav"
                                try:
                                    _sp.run(
                                        [_iff.get_ffmpeg_exe(), '-i', tmp_mp3,
                                         '-ar', '24000', '-ac', '1', '-f', 'wav',
                                         _wav_tmp, '-y', '-loglevel', 'quiet'],
                                        timeout=30, check=True,
                                        creationflags=0x08000000)
                                    _wv, _sr = _safe_audio_load(_wav_tmp)
                                finally:
                                    try: _os.remove(_wav_tmp)
                                    except Exception: pass
                                if _sr != 24000:
                                    _wv = _ta_one.functional.resample(_wv, _sr, 24000)
                                if _wv.shape[0] > 1:
                                    _wv = _wv.mean(dim=0, keepdim=True)
                                import soundfile as _sf_sv2
                                _sf_sv2.write(tmp_wav, _wv.squeeze().numpy(), 24000, subtype='PCM_16')
                                try: _os.remove(tmp_mp3)
                                except Exception: pass
                                return tmp_wav
                            else:
                                last_err = f"file rong ({sz} bytes)"
                        else:
                            last_err = "file khong duoc tao"
                except Exception as e:
                    last_err = str(e)
                finally:
                    for _p in [tmp_pcm, tmp_mp3]:
                        try:
                            if _os.path.exists(_p): _os.remove(_p)
                        except Exception: pass
                if _attempt < 2:
                    await _aio.sleep(1.5 * (_attempt + 1))
            self._log(f"   ⚠ Edge TTS that bai sau 3 lan: {last_err}", "warn")
            return None

        self._log(f"🌐 Batch SRT Edge TTS | Voice: {voice_id}", "info")
        part_idx = 0
        for j, e in enumerate(entries):
            if self.cancel_ev.is_set(): return None, None, None
            txt = e.text.strip()
            for ch in ["♪","♫","♩","♬"]:
                txt = txt.replace(ch, "")
            txt = _re.sub(r"<[^>]+>", "", txt).strip()
            if not txt or len(txt) < 2:
                skip += 1; continue
            _orig_txt_for_srt = txt  # FIX v3.68: text GOC, dung xuat .srt timeline
            txt = _apply_phonetic(txt)
            # FIX v3.66: Edge TTS khong tach cau dai (rule B).
            if getattr(self, "srt_tts_friendly_var", None) and self.srt_tts_friendly_var.get():
                txt = _tts_friendly(txt, split_long_sentences=False)
            if on_entry_progress:
                on_entry_progress(j, "start", total_e, part_idx)
            try:
                txt_for_tts = _edge_smart_pause(txt, max_words=8)
                import sys as _sys, asyncio as _asyncio_b
                if _sys.platform == "win32":
                    _asyncio_b.set_event_loop_policy(_asyncio_b.WindowsSelectorEventLoopPolicy())
                _evloop_b = _asyncio_b.new_event_loop()
                try:
                    tmp_wav = _evloop_b.run_until_complete(_gen_one(txt_for_tts, voice_id))
                finally:
                    _evloop_b.close()
                if not tmp_wav or not Path(tmp_wav).exists():
                    # FIX v3.68 (theo anh Bac yeu cau 2026-07-30, khach bi
                    # antivirus/firewall chan ket noi Microsoft - khong lien
                    # quan toc do mang): dong bo voi tab Van Ban/SRT - tu dong
                    # dung MagicVoice thay the entry loi, khong bo qua/raise.
                    self._log(f"  🔄 Edge TTS lỗi — dùng MagicVoice thay thế", "warn")
                    try:
                        kw = self._vkw()
                        t = Backend.gen(txt_for_tts, **kw,
                                         num_step=self._cfg.get("steps", 24),
                                         speed=self._get_speed())
                    except Exception as _fbe:
                        raise RuntimeError(f"Edge TTS loi va Fallback MagicVoice cung loi: {_fbe}")
                else:
                    t, sr = _safe_audio_load(tmp_wav)
                    try: Path(tmp_wav).unlink()
                    except: pass
                    if sr != SR:
                        t = _ta.functional.resample(t, sr, SR)
                    if t.shape[0] > 1:
                        t = t.mean(dim=0, keepdim=True)
                if t is None or t.abs().max() < 0.0001:
                    if on_entry_progress:
                        on_entry_progress(j, "skip", total_e, part_idx)
                    skip += 1; continue
                tensors.append(t)
                entry_tensors.append(t)
                entry_texts.append(_orig_txt_for_srt)
                part_idx += 1
                if parts_dir:
                    try:
                        _mp3 = os.path.join(parts_dir, f"{part_idx:03d}.mp3")
                        if gap_be > 0:
                            _gap_be = torch.zeros(1, int(gap_be * SR / 1000))
                            _out_t = torch.cat([t, _gap_be], dim=-1)
                        else:
                            _out_t = t
                        _out_t = _out_t.unsqueeze(0) if _out_t.dim() == 1 else _out_t
                        to_mp3(_out_t, _mp3)
                    except Exception:
                        pass
                if on_entry_progress:
                    on_entry_progress(j, "ok", total_e, part_idx)
                if part_idx < _total_nonempty_be:
                    tensors.append(silence)
                ok += 1
            except Exception as _ge:
                self._log(f"    ⚠ entry {j+1}: {_ge}", "warn")
                if on_entry_progress:
                    on_entry_progress(j, "skip", total_e, part_idx)
                skip += 1

        if not tensors:
            return None, None, None
        self._log(f"    🎞 {ok} entry OK (Edge TTS), {skip} bỏ qua → ghép", "info")
        return torch.cat(tensors, dim=1), entry_tensors, entry_texts

    def _batch_gen_srt_file_fast(self, srt_path: str, vp, parts_dir: str = None, on_entry_progress=None) -> tuple:
        """FIX v3.68 (tinh nang moi, theo yeu cau anh Bac): mode "MagicVoice
        Nhanh" version cua _batch_gen_srt_file - phong theo ban Edge nhung
        don gian hon nhieu (khong can async/retry-mang, _fast_generate()
        chay dong bo local). Returns (final_tensor, entry_tensors)."""
        import torch, re as _re
        voice_id = FAST_VOICES_LIST[0][0]
        if vp.instruct and vp.instruct.startswith("fast:"):
            voice_id = vp.instruct.replace("fast:", "").strip()
        try:
            raw = Path(srt_path).read_text("utf-8").strip()
        except Exception:
            raw = Path(srt_path).read_text("utf-8", errors="ignore").strip()
        if not raw: return None, None, None
        entries = parse_srt(raw)
        if not entries: return None, None, None

        SR = 24000
        gap_bf = int(self.gap_var.get())
        silence = torch.zeros(1, int(gap_bf * SR / 1000))
        tensors = []
        entry_tensors = []
        entry_texts = []
        ok = skip = 0
        total_e = len(entries)
        _total_nonempty_bf = sum(1 for e in entries if e.text.strip() and len(e.text.strip()) >= 2)

        self._log(f"⚡ Batch SRT MG Nhanh | Voice: {voice_id}", "info")
        part_idx = 0
        speed = self._get_speed()
        for j, e in enumerate(entries):
            if self.cancel_ev.is_set(): return None, None, None
            txt = e.text.strip()
            for ch in ["♪","♫","♩","♬"]:
                txt = txt.replace(ch, "")
            txt = _re.sub(r"<[^>]+>", "", txt).strip()
            if not txt or len(txt) < 2:
                skip += 1; continue
            _orig_txt_for_srt = txt  # FIX v3.68: text GOC, dung xuat .srt timeline
            txt = _apply_phonetic(txt)
            if getattr(self, "srt_tts_friendly_var", None) and self.srt_tts_friendly_var.get():
                txt = _tts_friendly(txt, split_long_sentences=False)
            if on_entry_progress:
                on_entry_progress(j, "start", total_e, part_idx)
            try:
                t = _fast_generate(txt, voice_id, speed=speed)
                if t is None or t.abs().max() < 0.0001:
                    if on_entry_progress:
                        on_entry_progress(j, "skip", total_e, part_idx)
                    skip += 1; continue
                tensors.append(t)
                entry_tensors.append(t)
                entry_texts.append(_orig_txt_for_srt)
                part_idx += 1
                if parts_dir:
                    try:
                        _mp3 = os.path.join(parts_dir, f"{part_idx:03d}.mp3")
                        if gap_bf > 0:
                            _gap_bf = torch.zeros(1, int(gap_bf * SR / 1000))
                            _out_t = torch.cat([t, _gap_bf], dim=-1)
                        else:
                            _out_t = t
                        _out_t = _out_t.unsqueeze(0) if _out_t.dim() == 1 else _out_t
                        to_mp3(_out_t, _mp3)
                    except Exception:
                        pass
                if on_entry_progress:
                    on_entry_progress(j, "ok", total_e, part_idx)
                if part_idx < _total_nonempty_bf:
                    tensors.append(silence)
                ok += 1
            except Exception as _ge:
                self._log(f"    ⚠ entry {j+1}: {_ge}", "warn")
                if on_entry_progress:
                    on_entry_progress(j, "skip", total_e, part_idx)
                skip += 1

        if not tensors:
            return None, None, None
        self._log(f"    🎞 {ok} entry OK (MG Nhanh), {skip} bỏ qua → ghép", "info")
        return torch.cat(tensors, dim=1), entry_tensors, entry_texts

    def _run_batch(self):
        # MOI: kiem tra license truoc
        if not self._verify_license_or_abort():
            self._running_tab = None
            self.is_running = False
            self.after(0, self._refresh_tab_indicators)
            return
        self._busy(True); self.cancel_ev.clear()
        # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): bo dem gio da co san
        # (self._timer_label) nhung truoc day CHI noi cho tab Van Ban - tab
        # Hang Loat da co san 1 loi goi _stop_timer() "mo coi" (khong co
        # _start_timer() tuong ung) o cuoi ham, gio noi dung lai.
        self._start_timer()
        total=len(self._txt_files); ok=fail=skipped=0

        # FIX v3.68 (theo anh Bac bao loi 2026-07-26, ra soat toan dien):
        # BUG THAT SU giong het loi da sua o tab Van Ban/SRT - Batch truoc
        # day CHI doc giong tu self.lib.profiles[self.sel_idx] (preset dang
        # chon trong "Cai Dat San"), BO QUA HOAN TOAN che do dang chon o
        # sidebar (self.tts_mode/fast_voice_var/edge_voice_var). Neu khach
        # chi moi BAM CHON giong o sidebar (MG Nhanh/Edge) ma CHUA duoc luu
        # thanh preset (hoac preset dang chon trong "Cai Dat San" la 1 giong
        # khac), Batch se am tham dung SAI giong. Sua: uu tien che do sidebar
        # dang chon, giong het pattern da dung o _do_srt().
        _batch_mode = self.tts_mode.get() if hasattr(self, "tts_mode") else "omnivoice"
        _batch_override_vp = None
        if _batch_mode == "edge" and hasattr(self, "edge_voice_var") and self.edge_voice_var.get():
            _bec = self.edge_voice_var.get()
            class _BatchFakeVPEdge:
                mode = "edge"
                instruct = f"edge:{_bec}"
                name = _bec
            _batch_override_vp = _BatchFakeVPEdge()
        elif _batch_mode == "fast" and hasattr(self, "fast_voice_var") and self.fast_voice_var.get():
            _bfc = self.fast_voice_var.get()
            class _BatchFakeVPFast:
                mode = "fast"
                instruct = f"fast:{_bfc}"
                name = _bfc
            _batch_override_vp = _BatchFakeVPFast()

        # Chuan bi index cho mode tien to: chi dem file TXT+SRT hop le
        # (bo qua hoan toan _vkw() khi sidebar dang o mode edge/fast - _vkw()
        # doc theo preset MagicVoice dang chon trong "Cai Dat San", co the
        # thieu ref_audio/instruct va bao loi oan, du khong lien quan gi den
        # giong se dung that su)
        if _batch_override_vp is not None:
            kw = {}
        else:
            try:
                kw=self._vkw()
            except Exception as _kw_err:
                self._log(f"❌ Lỗi voice: {_kw_err}", "err")
                self._stop_timer()
                self._busy(False)
                self._running_tab = None
                return

        # Diagnostic: hien thi voice dang dung de de debug "giong la"
        _vp_diag = _batch_override_vp or (self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None)
        _mode_labels_b = {"clone": "Clone", "design": "Design", "edge": "Edge TTS", "fast": "MG Nhanh"}
        _mode_str_b = _mode_labels_b.get(_vp_diag.mode, _vp_diag.mode or "Default") if _vp_diag else "?"
        if not kw and _vp_diag and _vp_diag.mode not in ("edge","fast"):
            self._log(f"⚠ Batch | Voice '{_vp_diag.name}' [{_mode_str_b}] — không có ref_audio/instruct → sẽ dùng giọng mặc định!", "warn")
        elif _vp_diag:
            _ref_name_b = Path(kw.get("ref_audio","")).name if "ref_audio" in kw else ""
            self._log(
                f"🎤 Batch | Voice: {_vp_diag.name} [{_mode_str_b}]" +
                (f" | ref: {_ref_name_b}" if _ref_name_b else "") +
                f" | {total} file", "info")

        fmt = self.fmt_var.get()
        ask_name = False  # Batch luôn dùng tên mặc định, không hỏi
        _total_files = len(self._txt_files)
        _done_files  = []  # track tên file đã xong để update preview

        try:
            for i,fp in enumerate(self._txt_files):
                if self.cancel_ev.is_set():
                    self._log("⏹ Đã hủy batch", "warn"); break
                stem   = Path(fp).stem
                ext    = Path(fp).suffix.lower()
                self._st(f"[{i+1}/{total}] {stem}{ext}")
                self._log(f"[{i+1}/{total}] {Path(fp).name}","info")
                # MOI: highlight file dang xu ly trong listbox + auto-scroll
                try:
                    self.after(0, lambda idx=i: (
                        self.batch_lb.selection_clear(0, "end"),
                        self.batch_lb.selection_set(idx),
                        self.batch_lb.see(idx),
                    ))
                except Exception:
                    pass

                # Batch luon dat ten theo ten file input (khong phu thuoc out_name_mode)
                default_name = (stem or f"output_{i+1:02d}").strip() or f"output_{i+1:02d}"
                if ask_name:
                    v = self._ask_output_filename(default_name, Path(fp).name)
                    if v is None or v.strip() == "":
                        self._log(f"  ⏭ Bỏ qua (user không đặt tên)", "warn")
                        skipped += 1; continue
                    default_name = v.strip()

                # Tạo thư mục ngay khi bắt đầu xử lý file này
                _stem_dir     = os.path.join(self.out_dir_var.get(), default_name)
                _parts_dir_srt = os.path.join(_stem_dir, "voice_le") if ext == ".srt" else None
                try:
                    os.makedirs(_parts_dir_srt if _parts_dir_srt else _stem_dir, exist_ok=True)
                except Exception:
                    pass

                # Preview: bắt đầu xử lý file này
                def _show_start(sn=default_name, fi=i, tot=_total_files, nd=len(_done_files)):
                    try:
                        self.batch_preview.config(state="normal")
                        self.batch_preview.delete("1.0", "end")
                        self.batch_preview.insert("1.0", f"⏳ Đang tạo voice {sn}... ({fi+1}/{tot})")
                        self.batch_preview.config(state="disabled")
                        self.batch_preview_info.config(text=f"{nd} / {tot} file")
                    except Exception:
                        pass
                self.after(0, _show_start)

                # Callback tiến độ từng dòng SRT
                _done_entries = []  # list of (j, part_idx) đã hoàn thành
                _cur_e        = [None]  # (j, total_e) đang tạo

                def _on_ep(j, status, total_e, part_idx, sn=default_name, fi=i, tot=_total_files):
                    if status == "start":
                        _cur_e[0] = (j, total_e)
                        _snap_done = list(_done_entries)
                        _snap_cur  = (j, total_e)
                    elif status == "ok":
                        _done_entries.append((j, part_idx))
                        _cur_e[0]  = None
                        _snap_done = list(_done_entries)
                        _snap_cur  = None
                    else:
                        _cur_e[0]  = None
                        _snap_done = list(_done_entries)
                        _snap_cur  = None
                    def _upd(done=_snap_done, cur=_snap_cur, stem_name=sn, fi=fi, tot=tot):
                        try:
                            lines = [f"⏳ Đang tạo voice {stem_name}... ({fi+1}/{tot})"]
                            for (_dj, _dp) in done:
                                lines.append(f"  ✅ Dòng {_dj+1} → {_dp:03d}.mp3")
                            if cur:
                                lines.append(f"  ⏳ Dòng {cur[0]+1}/{cur[1]} đang tạo...")
                            self.batch_preview.config(state="normal")
                            self.batch_preview.delete("1.0", "end")
                            self.batch_preview.insert("1.0", "\n".join(lines))
                            self.batch_preview.config(state="disabled")
                        except Exception:
                            pass
                    self.after(0, _upd)

                try:
                    tensor = None
                    entry_tensors = None
                    # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): [(text, dur)]
                    # dung xuat .srt timeline sau (chi dung cho nhanh .txt -
                    # nhanh .srt tu xay dung tu entry_tensors/entry_texts ngay
                    # ben duoi, xem sau khoi if/else nay).
                    _srt_timeline_data = []
                    if ext == ".srt":
                        _vp_b = _batch_override_vp or (self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None)
                        entry_texts = None
                        if _vp_b and _vp_b.mode == "edge":
                            tensor, entry_tensors, entry_texts = self._batch_gen_srt_file_edge(fp, _vp_b, _parts_dir_srt, _on_ep)
                        elif _vp_b and _vp_b.mode == "fast":
                            tensor, entry_tensors, entry_texts = self._batch_gen_srt_file_fast(fp, _vp_b, _parts_dir_srt, _on_ep)
                        else:
                            tensor, entry_tensors, entry_texts = self._batch_gen_srt_file(fp, kw, _parts_dir_srt, _on_ep)
                        if tensor is None:
                            self._log("  ⚠ SRT rỗng hoặc không parse được", "warn")
                            fail += 1; continue
                        # Ghep (text, dur) tu entry_tensors/entry_texts (cung
                        # thu tu, gap giua cac entry da GOM SAN vao audio nen
                        # dur = do dai tensor + gap_var, gap_ms=0 khi export.
                        if entry_texts:
                            _gap_sec_b = int(self.gap_var.get()) / 1000.0
                            for _bi, (_bt_txt, _bt_ten) in enumerate(zip(entry_texts, entry_tensors)):
                                _bt_dur = _bt_ten.shape[-1] / 24000
                                if _bi < len(entry_texts) - 1:
                                    _bt_dur += _gap_sec_b
                                _srt_timeline_data.append((_bt_txt, _bt_dur))
                    else:
                        # .txt (hoac extension la - doc nhu text thuong)
                        txt=Path(fp).read_text("utf-8", errors="ignore").strip()
                        if not txt:
                            self._log("  ⚠ File trống", "warn")
                            skipped += 1; continue
                        _vp_txt = _batch_override_vp or (self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None)
                        # Toi uu doc (TTS-friendly): dung chung checkbox voi
                        # tab SRT - ap tren ban sao, khong sua file goc.
                        # FIX v3.66: Edge TTS khong tach cau dai (rule B) -
                        # phai biet mode TRUOC khi goi (doi cho voi _vp_txt).
                        # FIX v3.66 (audit 2026-07-24): bo qua TTS-friendly
                        # khi mode=clone - xem ghi chu day du o _do_text().
                        _is_clone_batch = bool(_vp_txt and _vp_txt.mode == "clone")
                        if (getattr(self, "srt_tts_friendly_var", None) and self.srt_tts_friendly_var.get()
                                and not _is_clone_batch):
                            _is_edge_batch = bool(_vp_txt and _vp_txt.mode == "edge")
                            txt = _tts_friendly(txt, split_long_sentences=not _is_edge_batch)
                        if _vp_txt and _vp_txt.mode == "edge":
                            # Edge TTS cho .txt: tach thanh cac doan ngan, gen tung doan
                            import asyncio, tempfile, torch as _tch_b, torchaudio as _ta_b, inspect as _ins_b
                            _ev_b = getattr(_vp_txt, "instruct", "") or ""
                            _edge_vid_b = _ev_b.replace("edge:","").strip() if _ev_b.startswith("edge:") else "vi-VN-HoaiMyNeural"
                            self._log(f"  🌐 Edge TTS [{_edge_vid_b}]", "info")
                            _use_pcm_b = 'codec' in _ins_b.signature(__import__("edge_tts").Communicate.__init__).parameters
                            async def _edge_txt_gen(_text, _vid, _use_pcm):
                                import edge_tts as _et, wave as _wv_b
                                _tw = tempfile.mktemp(suffix=".wav")
                                _tp = _tw + ".pcm"
                                _tm = _tw + ".mp3"
                                if _use_pcm:
                                    await _et.Communicate(_text, _vid, codec="audio-24khz-16bit-mono-pcm").save(_tp)
                                    if os.path.exists(_tp) and os.path.getsize(_tp) >= 100:
                                        with open(_tp,"rb") as _f: _pcm_b=_f.read()
                                        with _wv_b.open(_tw,"wb") as _wf_b:
                                            _wf_b.setnchannels(1);_wf_b.setsampwidth(2)
                                            _wf_b.setframerate(24000);_wf_b.writeframes(_pcm_b)
                                        try: os.remove(_tp)
                                        except Exception: pass
                                        return _tw
                                else:
                                    await _et.Communicate(_text, _vid).save(_tm)
                                    if os.path.exists(_tm) and os.path.getsize(_tm) >= 100:
                                        import imageio_ffmpeg as _iff_b, subprocess as _spb
                                        _wt2 = _tm + "_24k.wav"
                                        _spb.run([_iff_b.get_ffmpeg_exe(),'-i',_tm,'-ar','24000',
                                                  '-ac','1','-f','wav',_wt2,'-y','-loglevel','quiet'],
                                                 timeout=30,check=True,creationflags=0x08000000)
                                        _wv2,_sr2 = _safe_audio_load(_wt2)
                                        try: os.remove(_wt2); os.remove(_tm)
                                        except Exception: pass
                                        if _sr2 != 24000:
                                            _wv2 = _ta_b.functional.resample(_wv2,_sr2,24000)
                                        if _wv2.shape[0] > 1: _wv2=_wv2.mean(dim=0,keepdim=True)
                                        import soundfile as _sfb
                                        _sfb.write(_tw, np.squeeze(_wv2.numpy()), 24000, subtype='PCM_16')
                                        return _tw
                                return None
                            # Tach text thanh chunks (tranh Edge TTS timeout voi text qua dai)
                            _chunk_limit = 900
                            _raw_txt_b = preprocess_text(txt)
                            _chunks_b = []
                            _buf_b = ""
                            for _sent_b in (_raw_txt_b.replace("。","。\n").replace("！","！\n")
                                             .replace("？","？\n").replace("!","!\n")
                                             .replace("?","?\n").replace(".",".\n").splitlines()):
                                _sent_b = _sent_b.strip()
                                if not _sent_b: continue
                                if len(_buf_b) + len(_sent_b) + 1 > _chunk_limit and _buf_b:
                                    _chunks_b.append(_buf_b.strip())
                                    _buf_b = _sent_b
                                else:
                                    _buf_b += (" " if _buf_b else "") + _sent_b
                            if _buf_b.strip(): _chunks_b.append(_buf_b.strip())
                            if not _chunks_b: _chunks_b = [_raw_txt_b[:_chunk_limit]]
                            _SR_b = 24000
                            _gap_b = int(self.gap_var.get())
                            _sil_b = _tch_b.zeros(1, int(_gap_b * _SR_b / 1000))
                            _parts_b = []
                            for _cbi, _ck_b in enumerate(_chunks_b):
                                if self.cancel_ev.is_set(): break
                                try:
                                    _loop_b = asyncio.new_event_loop()
                                    _wp_b = _loop_b.run_until_complete(_edge_txt_gen(_ck_b, _edge_vid_b, _use_pcm_b))
                                    _loop_b.close()
                                    if _wp_b and os.path.exists(_wp_b):
                                        _t_b, _sr_b = _safe_audio_load(_wp_b)
                                        try: os.remove(_wp_b)
                                        except Exception: pass
                                        if _sr_b != _SR_b:
                                            _t_b = _ta_b.functional.resample(_t_b,_sr_b,_SR_b)
                                        if _t_b.shape[0] > 1: _t_b=_t_b.mean(dim=0,keepdim=True)
                                        _parts_b.append(_t_b)
                                        _dur_b = _t_b.shape[-1] / _SR_b
                                        if len(_chunks_b) > 1 and _cbi < len(_chunks_b) - 1:
                                            _parts_b.append(_sil_b)
                                            _dur_b += _gap_b / 1000.0
                                        _srt_timeline_data.append((_ck_b, _dur_b))
                                except Exception as _eb: self._log(f"  ⚠ Edge chunk lỗi: {_eb}","warn")
                            if _parts_b:
                                tensor = _tch_b.cat(_parts_b, dim=1) if len(_parts_b) > 1 else _parts_b[0]
                            else:
                                tensor = None
                        elif _vp_txt and _vp_txt.mode == "fast":
                            # FIX v3.68 (tinh nang moi, theo yeu cau anh Bac):
                            # mode "MG Nhanh" cho Batch .txt - don gian
                            # hon Edge nhieu (khong can async/PCM/mang), chi
                            # tach doan + goi _fast_generate() tuan tu.
                            import torch as _tch_f
                            _fv_txt = getattr(_vp_txt, "instruct", "") or ""
                            _fast_vid_txt = _fv_txt.replace("fast:","").strip() if _fv_txt.startswith("fast:") else FAST_VOICES_LIST[0][0]
                            self._log(f"  ⚡ MG Nhanh [{_fast_vid_txt}]", "info")
                            _paras_f = [p.strip() for p in preprocess_text(txt).split("\n\n") if p.strip()] or [txt.strip()]
                            _sil_f = _tch_f.zeros(1, int(self.gap_var.get() * 24000 / 1000))
                            _parts_f = []
                            for _pfi, _para_f in enumerate(_paras_f):
                                if self.cancel_ev.is_set(): break
                                try:
                                    _t_f = _fast_generate(_para_f, _fast_vid_txt, speed=self._get_speed())
                                    _parts_f.append(_t_f)
                                    _dur_f = _t_f.shape[-1] / 24000
                                    if _pfi < len(_paras_f) - 1:
                                        _parts_f.append(_sil_f)
                                        _dur_f += self.gap_var.get() / 1000.0
                                    _srt_timeline_data.append((_para_f, _dur_f))
                                except Exception as _ef:
                                    self._log(f"  ⚠ MG Nhanh đoạn lỗi: {_ef}", "warn")
                            tensor = _tch_f.cat(_parts_f, dim=-1) if _parts_f else None
                        else:
                            # FIX v3.66 (hieu nang 2026-07-24): dung _gen_cached
                            # thay Backend.gen() truc tiep - xem ghi chu o _gen_cached.
                            _txt_pp = preprocess_text(txt)
                            a=_gen_cached(_txt_pp, self.steps_var.get(),
                                          self._get_speed(), kw)
                            tensor = _to_tensor(a)
                            # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): mode
                            # MagicVoice cho .txt trong Batch KHONG tach doan
                            # (gen 1 lan ca file) - chi co the coi ca file la
                            # 1 "entry" duy nhat cho xuat .srt timeline (uoc
                            # luong tho hon Edge/Fast, nhung van dung ty le).
                            if tensor is not None and tensor.abs().max() > 0.0001:
                                _srt_timeline_data.append((_txt_pp, tensor.shape[-1] / 24000))

                    if tensor is None or tensor.abs().max() < 0.0001:
                        self._log("  ⚠ Audio rỗng", "warn")
                        fail += 1; continue

                    # _stem_dir đã tạo ở trên
                    out = os.path.join(_stem_dir, f"{default_name}.{fmt}")
                    self._save(tensor, out)
                    self._log(f"  ✅ → {default_name}/", "ok"); ok += 1
                    _done_files.append(fp)

                    # FIX v3.68 (theo anh Bac yeu cau 2026-07-26): xuat .srt
                    # timeline khop audio vua tao - dung chung checkbox
                    # self.srt_timeline_var voi tab SRT, ap dung cho ca .srt
                    # lan .txt trong Hang Loat. gap_ms=0 vi khoang lang giua
                    # entry/chunk/doan da GOM SAN vao dur trong _srt_timeline_data.
                    try:
                        if getattr(self, "srt_timeline_var", None) and self.srt_timeline_var.get() and _srt_timeline_data:
                            _srt_out_path = str(Path(out).with_suffix("")) + "_timeline.srt"
                            _srt_saved_path, _srt_n = _export_srt_timeline(
                                _srt_timeline_data, 0, _srt_out_path)
                            self._log(f"  📝 SRT timeline ({_srt_n} dòng): {Path(_srt_saved_path).name}", "ok")
                    except Exception as _srt_exp_err:
                        self._log(f"  ⚠ Không xuất được .srt timeline: {_srt_exp_err}", "warn")

                    # Voice lẻ SRT đã lưu từng cái bên trong gen func, log tổng kết
                    if ext == ".srt" and entry_tensors and _parts_dir_srt:
                        try:
                            _saved_n = len([_f for _f in os.listdir(_parts_dir_srt) if _f.endswith(".mp3")])
                            self._log(f"  📁 {_saved_n}/{len(entry_tensors)} file lẻ → voice_le/", "ok")
                        except Exception:
                            pass

                    # Cập nhật preview box: tổng kết file-level
                    def _upd_prev(done=list(_done_files)):
                        try:
                            done_set = set(done)
                            lines = [f"✅ Đã xong: {len(done_set)}/{_total_files} file"]
                            for _f in self._txt_files:
                                nm = Path(_f).name
                                lines.append(f"  {'✅' if _f in done_set else '⬜'} {nm}")
                            self.batch_preview.config(state="normal")
                            self.batch_preview.delete("1.0", "end")
                            self.batch_preview.insert("1.0", "\n".join(lines))
                            self.batch_preview.config(state="disabled")
                            self.batch_preview_info.config(text=f"{len(done_set)} / {_total_files} file")
                        except Exception:
                            pass
                    self.after(0, _upd_prev)

                except Exception as e:
                    self._log(f"  ❌ {Path(fp).name}: {e}","err"); fail+=1
                self.after(0,lambda v=(i+1)/total*100:self.pb.configure(value=v))
        finally:
            msg=f"✅ Batch xong: {ok}/{total}"
            if fail:    msg+=f", {fail} lỗi"
            if skipped: msg+=f", {skipped} bỏ qua"
            self._st(msg,P["green"]); self._log(msg,"ok")
            # Cap nhat counter cho lan gen sau (tab Text/SRT don le)
            if ok > 0:
                try:
                    if self.out_name_mode.get() == "prefix":
                        self._out_counter_offset += ok
                except Exception:
                    pass
            if ok > 0:
                try:
                    self._save_batch_session()
                except Exception:
                    pass
            self._running_tab = None
            self._stop_timer()
            self._busy(False)

    def _concat(self, segs, out, gap_ms):
        """Ghép danh sách tensor hoặc WAV file thành 1 file output."""
        import torch, torchaudio, tempfile
        SR = 24000

        # segs có thể là list[Tensor] hoặc list[str] (WAV paths)
        tensors = []
        silence = torch.zeros(1, int(gap_ms * SR / 1000))

        for j, seg in enumerate(segs):
            if isinstance(seg, torch.Tensor):
                tensors.append(seg)
            elif isinstance(seg, str) and os.path.isfile(seg):
                t, sr = _safe_audio_load(seg)
                if sr != SR:
                    t = torchaudio.functional.resample(t, sr, SR)
                tensors.append(t)
            if j < len(segs)-1:
                tensors.append(silence)

        if not tensors:
            return

        final = torch.cat(tensors, dim=1)
        # Lưu qua _save (xử lý post-process bên trong)
        self._save(final, out)

        # Dọn WAV tạm nếu có
        for seg in segs:
            if isinstance(seg, str):
                try: os.remove(seg)
                except: pass

    # ─────── SRT loader ────────────────────────────────────────────
    def _show_script_preview(self):
        """Hiện preview script đã tối ưu."""
        if not HAS_SCRIPT_PROC:
            messagebox.showinfo("Thiếu module",
                "Cần file script_processor.py trong cùng thư mục!"); return
        txt = self.txt_in.get("1.0","end-1c").strip()
        if not txt:
            messagebox.showwarning("Trống","Hãy nhập văn bản trước!"); return

        dlg = tk.Toplevel(self)
        dlg.title("🎬 Script Optimizer Preview")
        dlg.geometry("680x520")
        dlg.configure(bg=P["bg"])

        tk.Label(dlg,text="🎬  Script Optimizer — Xem trước cách tách câu",
                 font=(FN,12,"bold"),bg=P["purple"],fg="white",pady=10).pack(fill="x")

        # Legend
        leg = tk.Frame(dlg,bg=P["bg"]); leg.pack(fill="x",padx=16,pady=6)
        for sym,label,color in [
            ("‖","Nghỉ dài (0.6-0.9s)","#dc2626"),
            ("|","Nghỉ vừa (0.35-0.5s)","#d97706"),
            ("·","Nghỉ ngắn (0.25s)","#65a30d"),
        ]:
            tk.Label(leg,text=f"  {sym} = {label}  ",
                     font=(FN,8),bg=P["bg"],fg=color).pack(side="left")

        # Preview text
        fr=tk.Frame(dlg,bg=P["bg"]); fr.pack(fill="both",expand=True,padx=16,pady=(0,8))
        sb=tk.Scrollbar(fr); sb.pack(side="right",fill="y")
        out=tk.Text(fr,wrap="word",font=(FN,10),
                    bg=P["white"],fg=P["text"],
                    relief="flat",highlightthickness=1,
                    highlightbackground=P["border"],
                    padx=12,pady=10,yscrollcommand=sb.set)
        out.pack(fill="both",expand=True)
        sb.config(command=out.yview)

        preview = preview_script(txt)
        segs = optimize_for_tts(txt)
        out.insert("1.0", preview)

        # Tag màu cho các marker
        out.tag_config("long",foreground="#dc2626",font=(FN,10,"bold"))
        out.tag_config("mid", foreground="#d97706",font=(FN,10,"bold"))
        out.tag_config("short",foreground="#65a30d",font=(FN,10,"bold"))
        for sym,tag in [("‖","long"),("|","mid"),("·","short")]:
            idx = "1.0"
            while True:
                pos = out.search(sym,idx,tk.END)
                if not pos: break
                out.tag_add(tag,pos,f"{pos}+1c")
                idx = f"{pos}+1c"

        # Info
        tk.Label(dlg,
                 text=f"✅ {len(segs)} segments | Bật 'Script Optimizer' trong sidebar rồi nhấn ▶ Tạo",
                 font=(FN,9),bg=P["bg"],fg="#16a34a",pady=6).pack()

        tk.Button(dlg,text="Đóng",command=dlg.destroy,
                  font=(FN,9),bg=P["hover"],fg=P["label"],
                  relief="flat",cursor="hand2",padx=12,pady=5).pack(pady=(0,8))

    def _srt_clear(self):
        """Xóa toàn bộ SRT."""
        self.srt_entries = []
        self.srt_tree.delete(*self.srt_tree.get_children())
        self.srt_editor.delete("1.0","end")
        self.srt_path.set("")
        self.srt_cnt_lbl.config(text="")
        self._log("🗑 Đã xóa SRT","warn")

    def _srt_auto_generate(self):
        """Tạo SRT tự động từ văn bản thường trong editor."""
        txt = self.srt_editor.get("1.0","end-1c").strip()
        ph = "Dan van ban hoac SRT vao day..."
        if not txt or txt.startswith(ph[:10]):
            messagebox.showwarning("Trống","Hãy nhập hoặc dán văn bản vào ô bên trái!")
            return
        # Tách dòng → câu
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        if not lines:
            messagebox.showwarning("Trống","Không tìm thấy nội dung!")
            return
        dur = self.srt_dur_var.get()
        gap = self.srt_gap2_var.get()
        def fmt_time(s):
            h=int(s//3600); m=int((s%3600)//60); sec=s%60
            return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".",",")
        srt_lines = []
        t = 0.0
        for i, line in enumerate(lines, 1):
            srt_lines += [str(i),
                          f"{fmt_time(t)} --> {fmt_time(t+dur)}",
                          line, ""]
            t += dur + gap
        srt_content = "\n".join(srt_lines)
        self._load_srt_content(srt_content, f"auto ({len(lines)} cau)")

    def _load_srt_content(self, content: str, source: str = ""):
        """Parse và hiển thị SRT content vào tree + editor."""
        self.srt_entries = parse_srt(content)
        # Cập nhật editor
        self.srt_editor.config(fg=P["text"])
        self.srt_editor.delete("1.0","end")
        self.srt_editor.insert("1.0", content)
        n = len(self.srt_entries)
        self.srt_cnt_lbl.config(text=f"{n} câu")
        self._log(f"✅ Tải {n} câu SRT{' từ ' + source if source else ''}", "ok")

        # Kiem tra entry qua dai so voi thoi gian
        self.after(100, self._check_srt_density)

    def _check_srt_density(self):
        """Phat hien entry qua dai — chi canh bao trong Log, khong hoi/split nua.
        FIX v3.65 (21): bo han hop thoai Yes/No + _auto_split_srt() - gay loi
        "tao xong khong ra voice" khi chon Yes (kich ban dai). Khong can thiet:
        chi la canh bao mat can doi text/thoi luong, khong anh huong kha nang
        tao voice thanh cong hay khong.
        """
        if not self.srt_entries: return
        CHARS_PER_SEC = 15
        too_long = [e for e in self.srt_entries
                    if (e.end_ms - e.start_ms) / 1000 > 0
                    and len(e.text) > (e.end_ms - e.start_ms) / 1000 * CHARS_PER_SEC * 1.3]
        if too_long:
            self._log(f"⚠ {len(too_long)} entry text khá dài so với thời gian hiển thị "
                       f"(không ảnh hưởng tạo voice)", "warn")
        self._refresh_srt_preview()

    def _auto_split_srt(self, too_long_entries):
        """Tu dong split cac entry qua dai thanh 2-3 entry nho hon."""
        import re as _re
        CHARS_PER_SEC = 15
        new_entries = []

        for e in self.srt_entries:
            if e not in too_long_entries:
                new_entries.append(e)
                continue

            dur_s = (e.end_ms - e.start_ms) / 1000
            txt = e.text.strip()

            # Tinh so entry can thiet
            n_parts = max(2, int(len(txt) / (dur_s * CHARS_PER_SEC)) + 1)

            # Tach text tai dau cau [.!?] hoac [,] neu khong co
            sents = _re.split(r"(?<=[.!?])\s+", txt)
            if len(sents) < 2:
                sents = _re.split(r"(?<=[,;])\s+", txt)
            if len(sents) < 2:
                # Tach theo so tu
                words = txt.split()
                mid = len(words) // 2
                sents = [" ".join(words[:mid]), " ".join(words[mid:])]

            # Gop cau lai thanh n_parts doan deu nhau
            target = len(txt) / n_parts
            parts = []
            buf = ""
            for s in sents:
                if not buf:
                    buf = s
                elif len(buf) < target:
                    buf += " " + s
                else:
                    parts.append(buf)
                    buf = s
            if buf: parts.append(buf)

            # Chia timestamp deu theo so ky tu
            total_chars = sum(len(p) for p in parts)
            t_cur = e.start_ms
            for pi, part in enumerate(parts):
                ratio = len(part) / total_chars if total_chars else 1/len(parts)
                dur_part = int((e.end_ms - e.start_ms) * ratio)
                t_end = t_cur + dur_part

                def ms_to_srt(ms):
                    h = ms // 3600000; ms %= 3600000
                    m = ms // 60000;   ms %= 60000
                    s = ms // 1000;    ms %= 1000
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

                new_e = SRTEntry(
                    index=0,  # se cap nhat lai sau
                    start=ms_to_srt(t_cur),
                    end=ms_to_srt(t_end),
                    text=part,
                    start_ms=t_cur,
                    end_ms=t_end
                )
                new_entries.append(new_e)
                t_cur = t_end + 10  # 10ms gap

        # Cap nhat lai index
        for i, e in enumerate(new_entries, 1):
            e.index = i

        self.srt_entries = new_entries
        n = len(new_entries)
        self.srt_cnt_lbl.config(text=f"{n} câu")
        self._log(f"✅ Đã split → {n} entry chuẩn hơn", "ok")
        self._refresh_srt_preview()

    def _refresh_srt_preview(self):
        """Cap nhat bang Preview SRT."""
        self.srt_tree.delete(*self.srt_tree.get_children())
        for e in self.srt_entries:
            dur_s = (e.end_ms - e.start_ms) / 1000
            ratio = len(e.text) / dur_s if dur_s > 0 else 0
            # Highlight do neu van qua dai sau split
            tag = "toolong" if ratio > 20 else ""
            self.srt_tree.insert("","end", values=(
                e.index, e.start, e.end,
                e.text.replace("\n"," ")[:120]), tags=(tag,))
        try:
            self.srt_tree.tag_configure("toolong", foreground="#ef4444")
        except: pass

    def _open_srt(self):
        p = filedialog.askopenfilename(title="Chọn file .srt",
                                        filetypes=[("SubRip","*.srt"),("*","*.*")])
        if not p: return
        self.srt_path.set(p)
        text = ""
        for enc in ("utf-8","utf-8-sig","utf-16","latin-1"):
            try: text = Path(p).read_text(encoding=enc); break
            except: pass
        self._load_srt_content(text, Path(p).name)

    def _srt_paste(self):
        """Paste SRT từ clipboard."""
        try:
            text = self.clipboard_get()
            if text.strip():
                self._load_srt_content(text, "clipboard")
        except Exception as e:
            messagebox.showwarning("Không có dữ liệu",
                                    f"Clipboard trống hoặc không phải text.\n{e}")

    def _srt_parse_editor(self):
        """Parse SRT từ nội dung trong editor."""
        text = self.srt_editor.get("1.0","end-1c").strip()
        if not text:
            messagebox.showwarning("Trống","Hãy nhập nội dung SRT!")
            return
        self._load_srt_content(text, "editor")

    def _srt_manual_input(self):
        """Mở dialog nhập SRT thủ công từ văn bản thường."""
        dlg = tk.Toplevel(self)
        dlg.title("✏️ Tạo SRT từ văn bản")
        dlg.geometry("640x520")
        dlg.configure(bg=P["bg"])
        dlg.grab_set()

        tk.Label(dlg, text="✏️  Tạo SRT nhanh từ văn bản thường",
                 font=(FN,12,"bold"), bg=P["purple"], fg="white",
                 pady=10).pack(fill="x")

        tk.Label(dlg,
                 text="Nhập văn bản (mỗi dòng = 1 câu SRT). App sẽ tự tạo timestamp.",
                 font=(FN,9), bg=P["bg"], fg=P["label"], pady=4).pack()

        # Settings row
        cfg = tk.Frame(dlg, bg=P["bg"]); cfg.pack(fill="x", padx=16, pady=4)
        tk.Label(cfg, text="Thời lượng mỗi câu (giây):",
                 font=(FN,9), bg=P["bg"], fg=P["label"]).pack(side="left")
        dur_var = tk.DoubleVar(value=4.0)
        tk.Spinbox(cfg, from_=1, to=30, increment=0.5,
                   textvariable=dur_var, width=6,
                   font=(FN,9), relief="flat",
                   bg=P["white"], fg=P["text"],
                   highlightthickness=1, highlightbackground=P["border"]
                   ).pack(side="left", padx=(4,12), ipady=2)
        tk.Label(cfg, text="Khoảng cách (giây):",
                 font=(FN,9), bg=P["bg"], fg=P["label"]).pack(side="left")
        gap_var = tk.DoubleVar(value=0.5)
        tk.Spinbox(cfg, from_=0, to=5, increment=0.1,
                   textvariable=gap_var, width=5,
                   font=(FN,9), relief="flat",
                   bg=P["white"], fg=P["text"],
                   highlightthickness=1, highlightbackground=P["border"]
                   ).pack(side="left", padx=4, ipady=2)

        # Text input
        tf2 = tk.Frame(dlg, bg=P["bg"]); tf2.pack(fill="both", expand=True, padx=16, pady=4)
        sb2 = tk.Scrollbar(tf2); sb2.pack(side="right", fill="y")
        txt = tk.Text(tf2, wrap="word", font=(FN,10), bg=P["white"],
                      fg=P["text"], insertbackground=P["purple"],
                      relief="flat", highlightthickness=1,
                      highlightbackground=P["border"],
                      highlightcolor=P["purple"],
                      yscrollcommand=sb2.set)
        txt.pack(fill="both", expand=True)
        sb2.config(command=txt.yview)
        self._ph(txt, "Nhập văn bản ở đây...\nMỗi dòng sẽ thành 1 câu SRT.\n\nVí dụ:\nXin chào, đây là câu đầu tiên.\nĐây là câu thứ hai.\nVà câu thứ ba.")

        def generate_srt():
            lines = [l.strip() for l in txt.get("1.0","end-1c").splitlines() if l.strip()]
            if not lines:
                messagebox.showwarning("Trống","Hãy nhập văn bản!", parent=dlg)
                return
            dur = dur_var.get()
            gap = gap_var.get()
            srt_lines = []
            t = 0.0
            for i, line in enumerate(lines, 1):
                def fmt(s):
                    h=int(s//3600); m=int((s%3600)//60); sec=s%60
                    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".",",")
                srt_lines.append(str(i))
                srt_lines.append(f"{fmt(t)} --> {fmt(t+dur)}")
                srt_lines.append(line)
                srt_lines.append("")
                t += dur + gap
            srt_content = "\n".join(srt_lines)
            self._load_srt_content(srt_content, "thủ công")
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=P["bg"]); btn_row.pack(fill="x", padx=16, pady=8)
        tk.Button(btn_row, text="✅ Tạo SRT",
                  command=generate_srt,
                  font=(FN,11,"bold"), bg=P["green"], fg="white",
                  relief="flat", cursor="hand2", padx=16, pady=7
                  ).pack(side="left")
        tk.Button(btn_row, text="Đóng", command=dlg.destroy,
                  font=(FN,9), bg=P["bg"], fg=P["sub"],
                  relief="flat", cursor="hand2", padx=10
                  ).pack(side="left", padx=(8,0))

    # ─────── Batch helpers ─────────────────────────────────────────
    def _browse_indir(self):
        d=filedialog.askdirectory(title="Chọn thư mục input chứa .txt / .srt")
        if d: self.in_dir.set(d); self._scan_txt()

    def _scan_txt(self):
        d=self.in_dir.get()
        if not os.path.isdir(d): return
        # MOI: quet ca .txt lan .srt, sort theo ten
        _exts = ("*.txt", "*.srt")
        _found = []
        for _pat in _exts:
            _found.extend(str(p) for p in Path(d).glob(_pat))
        self._txt_files = sorted(_found)
        self.batch_lb.delete(0,"end")
        n_txt = n_srt = 0
        for f in self._txt_files:
            sz=os.path.getsize(f)/1024
            ext = Path(f).suffix.lower()
            tag = "📄 TXT" if ext==".txt" else "🎞 SRT"
            if ext == ".srt": n_srt += 1
            else:             n_txt += 1
            self.batch_lb.insert("end",f"  {tag}  {Path(f).name:<42} {sz:.1f} KB")
        self.batch_cnt.config(text=f"{len(self._txt_files)} file  ({n_txt} txt, {n_srt} srt)")
        self._log(f"📁 Tìm thấy {len(self._txt_files)} file  ({n_txt} txt, {n_srt} srt)","info")

    def _add_txt(self):
        # MOI: chap nhan them .srt
        files=filedialog.askopenfilenames(
            title="Chọn file .txt hoặc .srt",
            filetypes=[("Text & SRT","*.txt *.srt"),
                       ("Text","*.txt"),
                       ("SRT","*.srt"),
                       ("Tất cả","*.*")])
        for f in files:
            if f not in self._txt_files:
                self._txt_files.append(f)
                sz=os.path.getsize(f)/1024
                ext = Path(f).suffix.lower()
                tag = "📄 TXT" if ext==".txt" else ("🎞 SRT" if ext==".srt" else "📎 ???")
                self.batch_lb.insert("end",f"  {tag}  {Path(f).name:<42} {sz:.1f} KB")
        self.batch_cnt.config(text=f"{len(self._txt_files)} file")

    def _clear_batch(self):
        self._txt_files=[]; self.batch_lb.delete(0,"end")
        self.batch_cnt.config(text="0 file")

    # ─────── Output ────────────────────────────────────────────────
    def _browse_out(self):
        d=filedialog.askdirectory(title="Chọn thư mục lưu output")
        if d: self.out_dir_var.set(d)

    def _open_out(self):
        d=self.out_dir_var.get(); os.makedirs(d,exist_ok=True)
        if WIN: os.startfile(d)
        elif sys.platform=="darwin": subprocess.Popen(["open",d])
        else: subprocess.Popen(["xdg-open",d])

    # ─────── Helpers ───────────────────────────────────────────────
    def _import_txt(self):
        p=filedialog.askopenfilename(title="Mở file TXT",
                                      filetypes=[("Text","*.txt"),("*","*.*")])
        if p:
            try:
                self.txt_in.delete("1.0","end")
                self.txt_in.insert("1.0",Path(p).read_text("utf-8"))
                self.txt_in.config(fg=P["text"])
            except Exception as e:
                messagebox.showerror("Lỗi",str(e))

    def _ph(self, widget, text):
        widget.insert("1.0",text); widget.config(fg=P["dim"])
        def fi(e):
            if widget.get("1.0","end-1c")==text:
                widget.delete("1.0","end"); widget.config(fg=P["text"])
        def fo(e):
            if not widget.get("1.0","end-1c").strip():
                widget.insert("1.0",text); widget.config(fg=P["dim"])
        widget.bind("<FocusIn>",fi); widget.bind("<FocusOut>",fo)

    def _busy(self, v):
        self.is_running = v
        self.after(0, self.cancel_btn.config, {"state": "normal" if v else "disabled"})
        # Chi bat create_btn neu KHONG phai dang cancel
        if not v and not self.cancel_ev.is_set():
            self.after(0, self.create_btn.config, {"state": "normal"})
        elif v:
            self.after(0, self.create_btn.config, {"state": "disabled"})
        if not v:
            self.after(0, lambda: self.pb.configure(value=0))
            # Reset cancel event de lan sau dung lai duoc
            self.cancel_ev.clear()
            # MOI: reset tab dang chay khi tac vu ket thuc
            self._running_tab = None
        # MOI: cap nhat cham tron tren tab button
        self.after(0, self._refresh_tab_indicators)

    def _cancel(self):
        """Huy generation - reset UI ngay."""
        self.cancel_ev.set()
        self._log("⏹ Đã hủy", "warn")
        self.is_running = False
        self._running_tab = None   # MOI: reset tab dang chay
        self._stop_timer()  # Dung timer ngay lap tuc
        self.after(0, self._refresh_tab_indicators)   # MOI: bo cham tron
        self.after(0, self.create_btn.config, {"state": "normal",
                                                "text": "  ▶  Tạo  ",
                                                "bg": P["purple"]})
        self.after(0, self.cancel_btn.config, {"state": "disabled"})
        self.after(0, lambda: self.pb.configure(value=0, mode="determinate"))
        self.after(0, self.status_lbl.config, {"text": "Đã hủy - sẵn sàng",
                                                "fg": P["gold"]})

    def _st(self, msg, col=None):
        self.after(0,self.status_lbl.config,{"text":msg,"fg":col or P["sub"]})

    def _log(self, msg, tag=""):
        ts=time.strftime("%H:%M:%S")
        self.logbox.config(state="normal")
        self.logbox.insert("end",f"[{ts}] {msg}\n",tag)
        self.logbox.see("end"); self.logbox.config(state="disabled")

    def _apply_ttk_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")   # clam theme cho slider đẹp hơn

        # Progress bar — FIX v3.68 (theo anh Bac yeu cau 2026-07-27): sau khi
        # bo dong chu trang thai (xem statusbar), co nhieu khoang trong hon -
        # lam thanh chay DAY va DAI hon (thickness 6->10, length 130->240 o
        # noi tao widget) cho no bat + "sang" hon, troughcolor doi sang mau
        # nen nhat (hover) thay vi xam border - tuong phan ro voi mau tim
        # cua thanh chay dang tien do.
        s.configure("TProgressbar",
                    troughcolor=P["hover"],
                    background=P["purple"],
                    thickness=10,
                    borderwidth=0)

        # Treeview — sạch, bo nhẹ
        s.configure("Treeview",
                    background=P["white"],
                    foreground=P["text"],
                    fieldbackground=P["white"],
                    borderwidth=0,
                    rowheight=26,
                    font=(FN, 9))
        s.configure("Treeview.Heading",
                    background=P["sidebar"],
                    foreground=P["label"],
                    borderwidth=0,
                    font=(FN, 9, "bold"),
                    padding=4)
        s.map("Treeview",
              background=[("selected", P["sel"])],
              foreground=[("selected", P["purple"])])

        # Combobox — viền mỏng xanh khi focus
        s.configure("TCombobox",
                    fieldbackground=P["white"],
                    background=P["white"],
                    foreground=P["text"],
                    borderwidth=1,
                    relief="flat",
                    padding=4)
        s.map("TCombobox",
              fieldbackground=[("readonly", P["white"])],
              selectbackground=[("readonly", P["white"])],
              selectforeground=[("readonly", P["text"])])

        # Scale slider — bo tròn, xanh dương
        s.configure("TScale",
                    background=P["bg"],
                    troughcolor="#dbeafe",        # xanh nhạt
                    sliderlength=18,
                    sliderrelief="flat",
                    borderwidth=0)
        s.configure("Horizontal.TScale",
                    background=P["bg"],
                    troughcolor="#dbeafe",
                    sliderlength=18)
        s.map("TScale",
              background=[("active", P["purple"]),
                          ("!active", P["purple"])])
        s.map("Horizontal.TScale",
              background=[("active", P["purple"]),
                          ("!active", P["purple"])],
              troughcolor=[("active", "#bfdbfe")])

        # Notebook tabs
        s.configure("TNotebook",
                    background=P["bg"],
                    borderwidth=0)
        s.configure("TNotebook.Tab",
                    background=P["sidebar"],
                    foreground=P["sub"],
                    padding=(12, 6),
                    borderwidth=0,
                    font=(FN, 9))
        s.map("TNotebook.Tab",
              background=[("selected", P["white"])],
              foreground=[("selected", P["purple"])],
              font=[("selected", (FN, 9, "bold"))])


# v3.36: Wrap entry point vao function de Nuitka compile sang .pyd
def _main_entry():
    # ── Cai tu dong firebase-admin va omnivoice TRUOC khi chay ────
    # FIX v3.20: Chi check & cai khi LAN DAU (track qua flag file).
    # Nhung lan sau, neu thieu module thi import se loi -> bao user.
    # Tranh moi lan startup phai dot 1-2s check dependency.
    import sys as _sys_pre, subprocess as _sp_pre, os as _os_pre
    from pathlib import Path as _Path_pre

    _flag_file = _Path_pre(__file__).parent / ".deps_installed"
    _ver_file  = _Path_pre(__file__).parent / "version.txt"

    # Doc version hien tai va version da cai truoc do
    _cur_ver = ""
    _ins_ver = ""
    try:
        if _ver_file.exists():
            _cur_ver = _ver_file.read_text("utf-8").strip()
    except Exception: pass
    try:
        if _flag_file.exists():
            _ins_ver = _flag_file.read_text("utf-8").strip()
    except Exception: pass

    # Can chay setup neu: lan dau chua co flag HOAC version thay doi
    _need_setup = not _flag_file.exists() or (_cur_ver and _ins_ver != _cur_ver)

    if _need_setup:
        _flags_pre = 0x08000000 if _os_pre.name == "nt" else 0
        _setup_py  = _Path_pre(__file__).parent / "setup_helper.py"
        _all_ok = True
        if _setup_py.exists():
            # Chay setup_helper.py day du: tu dong upgrade package theo phien ban moi
            try:
                _r_setup = _sp_pre.run(
                    [_sys_pre.executable, str(_setup_py)],
                    creationflags=_flags_pre, timeout=1200
                )
                if _r_setup.returncode != 0:
                    _all_ok = False  # setup_helper bao loi -> khong ghi flag -> chay lai lan sau
            except Exception:
                _all_ok = False
        else:
            # Fallback: chi cai 2 goi chinh neu setup_helper khong co
            for _mod_pre, _pkg_pre in [("firebase_admin","firebase-admin"),("omnivoice","omnivoice")]:
                try:
                    __import__(_mod_pre)
                except ImportError:
                    try:
                        _sp_pre.run(
                            [_sys_pre.executable, "-m", "pip", "install",
                             _pkg_pre, "--quiet", "--no-cache-dir"],
                            creationflags=_flags_pre, timeout=300
                        )
                    except Exception:
                        _all_ok = False
        # Ghi version moi vao flag de lan sau khong chay lai
        if _all_ok:
            try: _flag_file.write_text(_cur_ver or "ok")
            except Exception: pass

    # FIX v3.20: warm-up server o background ngay khi startup
    # de luc user dien xong form login, server da san sang
    try:
        import threading as _th_pre
        from auth_manager import warm_up_server as _warm
        _th_pre.Thread(target=_warm, daemon=True).start()
    except Exception:
        pass

    # ── Dang nhap tai khoan ───────────────────────────────────────
    import tkinter as _tk_login

    _QR_SERVER_BASE = "https://magicvoice-update-1.onrender.com"

    def _open_qr_renewal_window(parent, username_hint=""):
        """Cua so QR gia han 300k/30 ngay. Dung urllib.request (KHONG dung
        requests) de goi API - toan bo app da patch SSL context cua
        urllib.request bang certifi luc import (xem dau file), tranh lap lai
        loi CERTIFICATE_VERIFY_FAILED tren may khach thieu goc chung chi."""
        import tkinter as _tk, json as _json, urllib.request as _ureq, threading as _thq, io as _io

        win = _tk.Toplevel(parent)
        win.title("Gia Hạn Tài Khoản")
        win.configure(bg="#0f1117")
        win.resizable(False, False)
        W, H = 420, 700
        win.geometry(f"{W}x{H}")
        win.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        win.geometry(f"{W}x{H}+{px+(pw-W)//2}+{py+(ph-H)//2}")
        try:
            win.transient(parent); win.grab_set()
            win.attributes("-topmost", True)
            win.lift()
            win.focus_force()
        except Exception: pass

        _tk.Label(win, text="Gia Hạn Tài Khoản", font=("Segoe UI",14,"bold"), bg="#0f1117", fg="#e8eaf6").pack(pady=(20,2))
        _tk.Label(win, text="300.000đ  —  30 ngày sử dụng", font=("Segoe UI",10), bg="#0f1117", fg="#9094b8").pack()

        body = _tk.Frame(win, bg="#0f1117")
        body.pack(fill="both", expand=True, padx=24, pady=(14,0))

        uv = _tk.StringVar(value=username_hint)
        _tk.Label(body, text="Tên tài khoản cần gia hạn", font=("Segoe UI",8,"bold"), bg="#0f1117", fg="#9094b8", anchor="w").pack(fill="x")
        uf = _tk.Frame(body, bg="#252845", highlightthickness=1, highlightbackground="#2d3154")
        uf.pack(fill="x", pady=(4,0))
        ue = _tk.Entry(uf, textvariable=uv, font=("Segoe UI",11), bg="#252845", fg="#e8eaf6", insertbackground="#6c63ff", relief="flat", bd=0)
        ue.pack(fill="x", ipady=8, padx=8)

        status_var = _tk.StringVar(value="")
        status_lbl = _tk.Label(body, textvariable=status_var, font=("Segoe UI",9), bg="#0f1117", fg="#9094b8", wraplength=320, justify="center")
        status_lbl.pack(pady=(10,4))

        qr_lbl = _tk.Label(body, bg="#0f1117")
        qr_lbl.pack()

        info_var = _tk.StringVar(value="")
        _tk.Label(body, textvariable=info_var, font=("Segoe UI",9), bg="#0f1117", fg="#6b7280", justify="center").pack(pady=(6,0))

        state = {"order_code": None, "stop": False, "photo": None}

        def _api(path, payload=None, method="GET"):
            data = _json.dumps(payload).encode("utf-8") if payload is not None else None
            req = _ureq.Request(_QR_SERVER_BASE + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
            with _ureq.urlopen(req, timeout=15) as resp:
                return _json.loads(resp.read().decode("utf-8"))

        def _fail(msg):
            btn_qr.config(state="normal", text="Tạo Mã QR")
            status_var.set("Lỗi: " + msg); status_lbl.config(fg="#ef4444")

        def _on_paid():
            state["stop"] = True
            status_var.set("✅ Đã gia hạn thành công! Vui lòng đăng nhập lại.")
            status_lbl.config(fg="#00d68f")
            btn_close.config(text="Đóng - Đăng nhập lại")

        def _poll_loop():
            while not state["stop"]:
                time.sleep(3)
                if state["stop"]: return
                try:
                    r = _api(f"/api/order_status?order_code={state['order_code']}")
                    if r.get("ok") and r.get("status") == "paid":
                        win.after(0, _on_paid); return
                except Exception:
                    pass

        def _show_qr(img_bytes, r):
            try:
                from PIL import Image, ImageTk
                img = Image.open(_io.BytesIO(img_bytes))
                img.thumbnail((300, 300), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                state["photo"] = photo
                qr_lbl.config(image=photo)
            except Exception:
                pass
            status_var.set("Quét mã QR bằng app ngân hàng để chuyển khoản")
            status_lbl.config(fg="#9094b8")
            amount_txt = f"{r['amount']:,}".replace(",", ".")
            info_var.set(f"Nội dung CK: {r['order_code']}\nSố tiền: {amount_txt}đ\n{r['account_name']} - {r['account_no']}")
            btn_qr.pack_forget()
            _thq.Thread(target=_poll_loop, daemon=True).start()

        def _create_qr():
            u = uv.get().strip()
            if not u:
                status_var.set("Nhập tên tài khoản!"); status_lbl.config(fg="#ef4444"); return
            btn_qr.config(state="disabled", text="Đang tạo QR...")
            status_var.set(""); win.update()
            def _work():
                try:
                    r = _api("/api/create_qr", {"username": u}, method="POST")
                    if not r.get("ok"):
                        win.after(0, lambda: _fail(r.get("error", "Lỗi không xác định"))); return
                    state["order_code"] = r["order_code"]
                    img_bytes = _ureq.urlopen(r["qr_image_url"], timeout=15).read()
                    win.after(0, lambda: _show_qr(img_bytes, r))
                except Exception as ex:
                    _err_msg = str(ex)[:80]
                    win.after(0, lambda: _fail(_err_msg))
            _thq.Thread(target=_work, daemon=True).start()

        btn_qr = _tk.Button(body, text="Tạo Mã QR", command=_create_qr, font=("Segoe UI",11,"bold"),
                             bg="#6c63ff", fg="white", relief="flat", cursor="hand2", activebackground="#8b85ff")
        btn_qr.pack(fill="x", ipady=9, pady=(6,0))

        def _close():
            state["stop"] = True
            win.destroy()
        btn_close = _tk.Button(win, text="Đóng", command=_close, font=("Segoe UI",9),
                                bg="#1a1d2e", fg="#9094b8", relief="flat", cursor="hand2")
        btn_close.pack(pady=(14,16))

        win.protocol("WM_DELETE_WINDOW", _close)
        if username_hint: btn_qr.focus_set()
        else: ue.focus_set()

    def _open_qr_signup_window(parent, on_paid):
        """Cua so DANG KY TAI KHOAN MOI qua QR - khach khong nhap gi ca,
        tu dong tao QR ngay khi mo. Khi thanh toan xong, goi on_paid(u,p)
        de man hinh dang nhap tu dien username/password, khach chi bam
        Dang Nhap. Cung quy uoc urllib.request nhu _open_qr_renewal_window
        (khong dung requests, dua vao SSL context certifi da patch dau file)."""
        import tkinter as _tk, json as _json, urllib.request as _ureq, threading as _thq, io as _io

        win = _tk.Toplevel(parent)
        win.title("Đăng Ký Tài Khoản Mới")
        win.configure(bg="#0f1117")
        win.resizable(False, False)
        W, H = 420, 700
        win.geometry(f"{W}x{H}")
        win.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        win.geometry(f"{W}x{H}+{px+(pw-W)//2}+{py+(ph-H)//2}")
        try:
            win.transient(parent); win.grab_set()
            win.attributes("-topmost", True)
            win.lift()
            win.focus_force()
        except Exception: pass

        _tk.Label(win, text="Đăng Ký Tài Khoản Mới", font=("Segoe UI",14,"bold"), bg="#0f1117", fg="#e8eaf6").pack(pady=(20,2))
        _tk.Label(win, text="300.000đ  —  30 ngày sử dụng", font=("Segoe UI",10), bg="#0f1117", fg="#9094b8").pack()

        body = _tk.Frame(win, bg="#0f1117")
        body.pack(fill="both", expand=True, padx=24, pady=(14,0))

        status_var = _tk.StringVar(value="Đang tạo mã QR...")
        status_lbl = _tk.Label(body, textvariable=status_var, font=("Segoe UI",9), bg="#0f1117", fg="#9094b8", wraplength=320, justify="center")
        status_lbl.pack(pady=(10,4))

        qr_lbl = _tk.Label(body, bg="#0f1117")
        qr_lbl.pack()

        info_var = _tk.StringVar(value="")
        _tk.Label(body, textvariable=info_var, font=("Segoe UI",9), bg="#0f1117", fg="#6b7280", justify="center").pack(pady=(6,0))

        state = {"order_code": None, "stop": False, "photo": None}

        def _api(path, payload=None, method="GET"):
            data = _json.dumps(payload).encode("utf-8") if payload is not None else None
            req = _ureq.Request(_QR_SERVER_BASE + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
            with _ureq.urlopen(req, timeout=15) as resp:
                return _json.loads(resp.read().decode("utf-8"))

        def _fail(msg):
            status_var.set("Lỗi: " + msg); status_lbl.config(fg="#ef4444")

        def _on_paid(username, password):
            state["stop"] = True
            status_var.set("✅ Đã tạo tài khoản thành công!")
            status_lbl.config(fg="#00d68f")
            info_var.set("")
            btn_close.config(text="Đóng - Đăng Nhập Ngay")
            win.after(600, lambda: (on_paid(username, password), _close()))

        def _poll_loop():
            while not state["stop"]:
                time.sleep(3)
                if state["stop"]: return
                try:
                    r = _api(f"/api/order_status?order_code={state['order_code']}")
                    if r.get("ok") and r.get("status") == "paid":
                        win.after(0, lambda: _on_paid(r.get("username"), r.get("password"))); return
                except Exception:
                    pass

        def _show_qr(img_bytes, r):
            try:
                from PIL import Image, ImageTk
                img = Image.open(_io.BytesIO(img_bytes))
                img.thumbnail((300, 300), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                state["photo"] = photo
                qr_lbl.config(image=photo)
            except Exception:
                pass
            status_var.set("Quét mã QR bằng app ngân hàng để chuyển khoản")
            status_lbl.config(fg="#9094b8")
            amount_txt = f"{r['amount']:,}".replace(",", ".")
            info_var.set(f"Nội dung CK: {r['order_code']}\nSố tiền: {amount_txt}đ\n{r['account_name']} - {r['account_no']}\n\nTài khoản sẽ tự động được tạo\nngay sau khi chuyển khoản thành công.")
            _thq.Thread(target=_poll_loop, daemon=True).start()

        def _create_qr():
            def _work():
                try:
                    r = _api("/api/signup_qr", {}, method="POST")
                    if not r.get("ok"):
                        win.after(0, lambda: _fail(r.get("error", "Lỗi không xác định"))); return
                    state["order_code"] = r["order_code"]
                    img_bytes = _ureq.urlopen(r["qr_image_url"], timeout=15).read()
                    win.after(0, lambda: _show_qr(img_bytes, r))
                except Exception as ex:
                    _err_msg = str(ex)[:80]
                    win.after(0, lambda: _fail(_err_msg))
            _thq.Thread(target=_work, daemon=True).start()

        def _close():
            state["stop"] = True
            win.destroy()
        btn_close = _tk.Button(win, text="Đóng", command=_close, font=("Segoe UI",9),
                                bg="#1a1d2e", fg="#9094b8", relief="flat", cursor="hand2")
        btn_close.pack(pady=(14,16))

        win.protocol("WM_DELETE_WINDOW", _close)
        _create_qr()

    def _show_login():
        import json as _json, tkinter as _tk
        from pathlib import Path as _P

        _cache = _P(__file__).parent / ".login_cache"
        def _load():
            try:
                if _cache.exists():
                    d = _json.loads(_cache.read_text("utf-8"))
                    return d.get("username",""), d.get("password",""), d.get("remember",False)
            except: pass
            # FIX (theo anh Bac 2026-08-14): mac dinh TICK SAN khi chua co
            # cache (khach moi/lan dau tren may nay) - tranh truong hop khach
            # tao tai khoan qua QR (username/password tu sinh, kho nho) roi
            # lo bo tick, lan sau khong dang nhap lai duoc phai lien he ho tro.
            return "","",True
        def _save(u,p): 
            try: _cache.write_text(_json.dumps({"username":u,"password":p,"remember":True}),"utf-8")
            except: pass
        def _clear():
            try:
                if _cache.exists(): _cache.unlink()
            except: pass

        su, sp, sr = _load()
        ok = [False, "", ""]

        win = _tk.Tk()
        win.title("MagicVoice TTS Studio")
        win.geometry("440x668")
        win.configure(bg="#0f1117")
        win.resizable(False,False)
        win.update_idletasks()
        x = (win.winfo_screenwidth()-440)//2
        y = (win.winfo_screenheight()-668)//2
        win.geometry(f"440x668+{x}+{y}")
        try:
            ico = _P(__file__).parent / "MagicVoice.ico"
            if ico.exists():
                ico_str = str(ico)
                win.iconbitmap(default=ico_str)
                win.after(0, lambda: win.iconbitmap(default=ico_str))
        except: pass

        c = _tk.Canvas(win,width=440,height=668,bg="#0f1117",highlightthickness=0)
        c.pack(fill="both",expand=True)
        c.create_oval(-60,-60,200,200,fill="#1a1040",outline="")
        c.create_oval(280,-40,520,200,fill="#0d1535",outline="")
        c.create_text(220,70,text="MV",font=("Segoe UI",36,"bold"),fill="#6c63ff")
        c.create_text(220,118,text="MagicVoice TTS Studio",font=("Segoe UI",14,"bold"),fill="#e8eaf6")
        c.create_text(220,142,text="Đăng nhập để sử dụng",font=("Segoe UI",9),fill="#6b7280")
        c.create_line(60,165,380,165,fill="#2d3154",width=1)

        frm = _tk.Frame(c,bg="#1a1d2e")
        c.create_window(220,285,window=frm,width=360,height=230)

        _tk.Label(frm,text="Tên tài khoản",font=("Segoe UI",8,"bold"),bg="#1a1d2e",fg="#9094b8",anchor="w").pack(fill="x",padx=20,pady=(16,2))
        uv = _tk.StringVar(value=su)
        uf = _tk.Frame(frm,bg="#252845",highlightthickness=1,highlightbackground="#2d3154")
        uf.pack(fill="x",padx=20)
        _tk.Label(uf,text="👤",bg="#252845",fg="#6b7280").pack(side="left",padx=8)
        ue = _tk.Entry(uf,textvariable=uv,font=("Segoe UI",11),bg="#252845",fg="#e8eaf6",insertbackground="#6c63ff",relief="flat",bd=0)
        ue.pack(side="left",fill="x",expand=True,ipady=10,pady=2)

        _tk.Label(frm,text="Mật khẩu",font=("Segoe UI",8,"bold"),bg="#1a1d2e",fg="#9094b8",anchor="w").pack(fill="x",padx=20,pady=(10,2))
        pv = _tk.StringVar(value=sp)
        pf = _tk.Frame(frm,bg="#252845",highlightthickness=1,highlightbackground="#2d3154")
        pf.pack(fill="x",padx=20)
        _tk.Label(pf,text="🔒",bg="#252845",fg="#6b7280").pack(side="left",padx=8)
        pe = _tk.Entry(pf,textvariable=pv,show="*",font=("Segoe UI",11),bg="#252845",fg="#e8eaf6",insertbackground="#6c63ff",relief="flat",bd=0)
        pe.pack(side="left",fill="x",expand=True,ipady=10,pady=2)

        rv = _tk.BooleanVar(value=sr)
        rf = _tk.Frame(frm,bg="#1a1d2e")
        rf.pack(fill="x",padx=20,pady=(8,0))
        _tk.Checkbutton(rf,text="Ghi nhớ tài khoản",variable=rv,font=("Segoe UI",9),bg="#1a1d2e",fg="#9094b8",activebackground="#1a1d2e",selectcolor="#252845",cursor="hand2").pack(side="left")

        mv = _tk.StringVar()
        ml = _tk.Label(c,textvariable=mv,font=("Segoe UI",9),bg="#0f1117",fg="#ef4444",wraplength=360)
        c.create_window(220,430,window=ml)

        def login(e=None):
            u=uv.get().strip(); p=pv.get().strip()
            if not u or not p: mv.set("Nhập đầy đủ thông tin!"); return
            btn.config(text="Đang kiểm tra...",state="disabled",bg="#3d3888")
            mv.set(""); win.update()
            try:
                from auth_manager import verify_login, verify_login_offline

                # FIX (v3.18): KHONG check internet bang socket connect 8.8.8.8:53.
                # Ly do: cach do bi false negative tren may khach co:
                #   - Firewall/Antivirus (Kaspersky, Bitdefender, ...) chan
                #     outbound port 53 den IP la
                #   - VPN dang bat -> chan DNS truc tiep
                #   - Mang cham -> timeout 1s khong du
                #   - Captive portal wifi chua login
                # -> _has_internet() return False -> di luon vao offline
                # -> bao "Chua co cache offline" DU MAY CO MANG.
                #
                # Cach moi: GOI LUON API server. verify_login() da co timeout
                # 8/20/30s va retry 3 lan. Neu fail mang thuc su -> fallback
                # offline. Logic moi handle dung ca 4 case tren.
                r, m = verify_login(u, p)
                is_offline = False
                # Neu API fail va co the la do mang/server -> thu offline
                if not r and ("kết nối" in m.lower() or "kết nối" in m.lower()
                              or "ket noi" in m.lower() or "timeout" in m.lower()
                              or "connection" in m.lower()):
                    r_off, m_off = verify_login_offline(u, p)
                    if r_off:
                        r, m = r_off, m_off
                        is_offline = True

                if r:
                    ok[0] = True
                    ok[1] = m
                    ok[2] = u
                    if rv.get(): _save(u,p)
                    else: _clear()
                    btn.config(text="Thành công!", bg="#00d68f")
                    mv.set(m); ml.config(fg="#00d68f")
                    win.after(700, win.quit)
                else:
                    # Chi fallback offline khi loi MANG, khong fallback khi server tu choi (sai pass)
                    _is_net_err = ("kết nối" in m.lower() or "ket noi" in m.lower()
                                   or "timeout" in m.lower() or "connection" in m.lower()
                                   or "server" in m.lower())
                    if not is_offline and _is_net_err:
                        r2, m2 = verify_login_offline(u, p)
                        if r2:
                            ok[0] = True
                            ok[1] = m2
                            ok[2] = u
                            if rv.get(): _save(u,p)
                            else: _clear()
                            btn.config(text="Thành công!", bg="#00d68f")
                            mv.set(m2); ml.config(fg="#00d68f")
                            win.after(700, win.quit)
                            return
                    btn.config(text="Đăng Nhập", state="normal", bg="#6c63ff")
                    mv.set(m); ml.config(fg="#ef4444")
            except Exception as _ex:
                btn.config(text="Đăng Nhập", state="normal", bg="#6c63ff")
                mv.set("Lỗi kết nối! " + str(_ex)[:60]); ml.config(fg="#ef4444")

        btn = _tk.Button(c,text="Đăng Nhập",command=login,font=("Segoe UI",12,"bold"),bg="#6c63ff",fg="white",relief="flat",cursor="hand2",activebackground="#8b85ff")
        c.create_window(220,405,window=btn,width=360,height=44)

        c.create_line(60,460,380,460,fill="#1e2135",width=1)
        c.create_text(220,478,text="Liên hệ - Zalo: 0985 483 623",font=("Segoe UI",9,"bold"),fill="#00b4d8")
        def zalo():
            import webbrowser; webbrowser.open("https://zalo.me/g/bqroiqc6wbcpph3s6sdd")
        bz = _tk.Button(c,text="📲  Tham Gia Nhóm Zalo",command=zalo,font=("Segoe UI",9,"bold"),bg="#0068ff",fg="white",relief="flat",cursor="hand2")
        c.create_window(220,510,window=bz,width=240,height=32)

        def open_signup():
            def _on_signup_paid(new_u, new_p):
                uv.set(new_u); pv.set(new_p)
                mv.set(f"Đã tạo tài khoản {new_u}! Bấm Đăng Nhập để vào.")
                ml.config(fg="#00d68f")
            _open_qr_signup_window(win, _on_signup_paid)
        bs = _tk.Button(c,text="🆕  Chưa Có Tài Khoản? Đăng Ký Ngay — 300k/30 ngày",command=open_signup,font=("Segoe UI",9,"bold"),bg="#6c63ff",fg="white",relief="flat",cursor="hand2",activebackground="#8b85ff")
        c.create_window(220,552,window=bs,width=340,height=32)

        def open_qr():
            _open_qr_renewal_window(win, uv.get().strip())
        bq = _tk.Button(c,text="💳  Gia Hạn Tài Khoản — 300k/30 ngày",command=open_qr,font=("Segoe UI",9,"bold"),bg="#f59e0b",fg="white",relief="flat",cursor="hand2",activebackground="#fbbf24")
        c.create_window(220,592,window=bq,width=280,height=32)

        c.create_text(220,636,text="🎁 Dùng thử? Liên hệ Zalo để được hỗ trợ",font=("Segoe UI",8),fill="#6b7280")

        win.protocol("WM_DELETE_WINDOW",win.destroy)
        win.bind("<Return>",login)
        if sr and su: pe.focus_set()
        else: ue.focus_set()

        win.mainloop()
        try: win.destroy()
        except: pass
        return ok[0], ok[1], ok[2]

    import os as _os, sys as _sys

    # ── Single instance: chi 1 cua so lam viec ────────────────────
    import tempfile, atexit
    _lock_file = _os.path.join(tempfile.gettempdir(), "magicvoice_studio.lock")

    def _check_single_instance():
        """Kiem tra neu da co instance dang chay - dung PID check chinh xac."""
        if _os.path.exists(_lock_file):
            try:
                with open(_lock_file, "r") as f:
                    pid = int(f.read().strip())
                # Chi bao loi neu process do THUC SU dang chay
                is_running = False
                try:
                    import psutil as _ps
                    # FIX v3.66: truoc day chi kiem tra TEN process co chua
                    # "python"/"magicvoice" - qua rong, de bi NHAN NHAM voi
                    # BAT KY tien trinh python nao khac tren may (setup_helper.py,
                    # 1 script python khac cua khach...) neu PID cu bi Windows
                    # TAI SU DUNG cho tien trinh moi sau khi MagicVoice thuc su
                    # da tat - gay bao "dang chay" GIA, app tu thoat voi ma
                    # THANH CONG (khong phai loi) - khach thay "khong len app,
                    # khong bao loi gi ca" du thuc te khong co gi dang chay
                    # that. Gio kiem tra CHINH XAC hon: dung command line phai
                    # chua ten file "magicvoice.py" that su, khong chi ten
                    # process chung chung. (Da xac nhan: magicvoice.py la
                    # entry point CHAY THANG qua pythonw.exe - chi
                    # magicvoice_gui.py duoc compile thanh .pyd, ban than
                    # magicvoice.py van la script .py binh thuong - nen
                    # cmdline cua tien trinh that su LUON chua "magicvoice.py".)
                    try:
                        proc = _ps.Process(pid)
                        if proc.is_running() and proc.status() != _ps.STATUS_ZOMBIE:
                            try:
                                cmdline = " ".join(proc.cmdline()).lower()
                            except Exception:
                                cmdline = ""
                            if "magicvoice.py" in cmdline or "magicvoice_core" in cmdline:
                                is_running = True
                    except _ps.NoSuchProcess:
                        # FIX v3.66 (audit 2026-07-24): PID nay THAT SU khong
                        # con ton tai - an toan xoa lock cu, dung nhu truoc day.
                        try: _os.remove(_lock_file)
                        except: pass
                    except _ps.AccessDenied:
                        # FIX v3.66 (audit 2026-07-24): day la truong hop DUY
                        # NHAT ma truoc day fail-open SAI - AccessDenied nghia
                        # la PID VAN TON TAI THAT (Windows tu choi cho doc
                        # cmdline do khac quyen/session), khac han NoSuchProcess.
                        # Truoc day rơi chung vao 1 khoi "except Exception" nen
                        # bi xoa lock giong het truong hop "da mat" - cho phep
                        # mo instance thu 2 ngay ca khi instance dau VAN DANG
                        # CHAY that. Day la LOI DUY NHAT can sua chac chan, vi
                        # AccessDenied la bang chung RO RANG process con song -
                        # gio gia dinh AN TOAN "van dang chay" (khong xoa lock,
                        # khong ghi de PID) thay vi coi nhu da mat.
                        is_running = True
                except ImportError:
                    # Khong co psutil (goi optional, co the chua cai) → khong
                    # the kiem tra PID chinh xac. GIU NGUYEN hanh vi cu (fail-
                    # open, coi nhu khong chay) - day la truong hop da tung
                    # gay bao "dang chay" GIA duoc ghi lai o comment tren, KHONG
                    # doi sang fail-safe o day de tranh regress dung bug do.
                    try: _os.remove(_lock_file)
                    except: pass

                if is_running:
                    import tkinter as _tk2
                    _r = _tk2.Tk(); _r.withdraw()
                    # FIX v3.66: bat topmost de cua so canh bao LUON hien len
                    # tren cung - truoc day co the bi Windows chan dua ra
                    # foreground (dac biet khi app duoc mo qua tien trinh
                    # nen/an nhu MagicVoice.vbs), khien canh bao ton tai
                    # nhung khach khong thay gi ca, tuong app "khong len".
                    _r.attributes("-topmost", True)
                    _tk2.messagebox.showwarning(
                        "Canh bao",
                        "MagicVoice TTS Studio dang chay!\nChi duoc mo 1 cua so lam viec.")
                    _r.destroy()
                    _sys.exit(0)
                else:
                    # Lock cu (app bi tat dot ngot) → xoa va tiep tuc
                    try: _os.remove(_lock_file)
                    except: pass
            except (ValueError, PermissionError, OSError):
                # File lock bi loi → xoa va tiep tuc
                try: _os.remove(_lock_file)
                except: pass
        # Ghi PID hien tai
        try:
            with open(_lock_file, "w") as f:
                f.write(str(_os.getpid()))
            atexit.register(lambda: _os.remove(_lock_file)
                            if _os.path.exists(_lock_file) else None)
        except Exception:
            pass

    try:
        _check_single_instance()
    except Exception:
        pass  # Neu loi thi cho chay binh thuong

    # ── Kiem tra firebase & dang nhap ─────────────────────────────
    # Dang nhap qua API Server (khong can firebase_credentials.json)
    logged_in, login_msg, _last_username = _show_login()
    if not logged_in:
        _sys.exit(0)
    # FIX (bao mat 2026-08-14, theo bao cao khach bypass tu anh Bac): TRUOC DAY
    # username duoc doc lai tu file .login_cache - file nay CHI duoc ghi neu
    # khach tick "Ghi nho tai khoan". Khach KHONG tick -> cache rong ->
    # _last_username = "" -> _verify_license_or_abort() (fail-open cu: "if not
    # _u: return True") BO QUA HOAN TOAN kiem tra license CA PHIEN - dung tool
    # free vinh vien sau 1 lan dang nhap, khong lien quan checkbox. Gio lay
    # thang username tu ket qua dang nhap THANH CONG (_show_login tra ve),
    # khong con phu thuoc file cache/checkbox nay nua.

    # ── MOI: Kiem tra license NGAY sau login (fail-closed) ─────────
    # Neu license khong hop le -> khong cho mo app
    if _last_username:
        try:
            from license_guard import verify_license as _vfl
            _lok, _lmsg = _vfl(_last_username)
            if not _lok:
                import tkinter as _lk
                _lr = _lk.Tk(); _lr.withdraw()
                _lk.messagebox.showerror(
                    "License khong hop le",
                    f"Khong the khoi dong MagicVoice:\n\n{_lmsg}\n\n"
                    "Vui long kiem tra ket noi internet va dang nhap lai.\n"
                    "Neu van khong duoc, lien he ho tro qua Zalo: 0985 483 623")
                _lr.destroy()
                _sys.exit(1)
        except ImportError:
            import tkinter as _lk
            _lr = _lk.Tk(); _lr.withdraw()
            _lk.messagebox.showerror(
                "Loi he thong",
                "Thieu module license_guard.py.\n\n"
                "Vui long cai dat lai app bang CaiDat_MagicVoice.bat\n"
                "hoac lien he Zalo: 0985 483 623")
            _lr.destroy()
            _sys.exit(1)
        except Exception as _le:
            # Loi bat ngo khac — van tu choi, khong fail-open
            import tkinter as _lk
            _lr = _lk.Tk(); _lr.withdraw()
            _lk.messagebox.showerror(
                "Loi kiem tra license",
                f"Loi: {_le}\n\nLien he ho tro: 0985 483 623")
            _lr.destroy()
            _sys.exit(1)

    import traceback as _tb
    _log_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "error_log.txt")
    try:
        App(login_msg=login_msg, username=_last_username).mainloop()
    except Exception as _e:
        with open(_log_file, "w", encoding="utf-8") as _f:
            _f.write(_tb.format_exc())
        import tkinter as _ek
        _er = _ek.Tk(); _er.withdraw()
        _ek.messagebox.showerror("Loi Khoi Dong", f"Loi:\n{_e}\n\nXem: {_log_file}")
        _er.destroy()


if __name__ == "__main__":
    _main_entry()
