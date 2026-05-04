#!/usr/bin/env python3
"""
MagicVoice TTS Studio v3
Giao diện hiện đại kiểu ứng dụng TTS chuyên nghiệp
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading, os, sys, re, time, json, subprocess, shutil
from pathlib import Path

# ── Patch torchaudio.load để tránh lỗi TorchCodec trên các máy chưa cài ──
def _patch_torchaudio():
    try:
        import torchaudio as _ta
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

_patch_torchaudio()
try:
    from script_processor import optimize_for_tts, preview_script
    HAS_SCRIPT_PROC = True
except ImportError:
    HAS_SCRIPT_PROC = False
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
VOICES_FILE    = _SCRIPT_DIR / "voices_library.json"
CONFIG_FILE    = _SCRIPT_DIR / "app_config.json"
CLONE_REFS_DIR = _SCRIPT_DIR / "clone_refs"

def load_config() -> dict:
    """Đọc cấu hình đã lưu."""
    defaults = {"device": "cpu", "dtype": "float16",
                "out_dir": str(Path.home()/"Downloads"/"MagicVoice"),
                "fmt": ".mp3", "steps": 16, "auto_load": True}
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
                        activebackground=P["hover"], activeforeground=P["purple"],
                        cursor="hand2", font=(FN, 9)),
        "primary": dict(bg=P["purple"], fg="#fff", relief="flat",
                        highlightthickness=0,
                        activebackground=P["purple2"], activeforeground="#fff",
                        cursor="hand2", font=(FN, 11, "bold")),
        "ghost":   dict(bg=P["bg"], fg=P["sub"], relief="flat",
                        highlightthickness=0,
                        activebackground=P["hover"], activeforeground=P["purple"],
                        cursor="hand2", font=(FN, 9)),
        "tag":     dict(bg=P["sel"], fg=P["purple"], relief="flat",
                        highlightthickness=0,
                        activebackground=P["hover"], activeforeground=P["grad1"],
                        cursor="hand2", font=(FN, 8)),
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
    lang:      str = "vi"
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
                            lang     = str(d.get("lang", "vi")),
                            speed    = float(d.get("speed", 1.0)),
                            volume   = float(d.get("volume", 1.0)),
                            pitch    = float(d.get("pitch", 1.0)),
                            note     = str(d.get("note", "")),
                            created  = str(d.get("created", "")),
                        )
                        loaded.append(vp)
                    if loaded:
                        self.profiles = loaded
                        return
            except Exception as e:
                # KHÔNG đổi tên/xóa file - giữ nguyên để debug
                print(f"[VoiceLib] Lỗi đọc file: {e}")
                print(f"[VoiceLib] File: {VOICES_FILE}")

        # Tạo mặc định nếu chưa có file (lần đầu dùng)
        self.profiles = [
            VoiceProfile("Auto", "auto", note="Giọng tự động"),
            VoiceProfile("Nữ trẻ Anh", "design",
                         instruct="female, young, british accent",
                         lang="en", note="British English"),
            VoiceProfile("Nam trưởng thành", "design",
                         instruct="male, middle aged, american accent",
                         lang="en", note="American English"),
        ]
        # Chỉ save nếu file thực sự chưa tồn tại
        if not VOICES_FILE.exists():
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
    tokens = _re.split(r'([.!?,;])', txt)
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
            if len(buf) > 20:
                result.append((buf, 0.3))
                buf = ""
        elif tok == ';':
            if buf.strip():
                result.append((buf.strip(), 0.45))
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
    _model    = None
    _offline  = False   # True = offline mode, set boi App._apply_network_mode()
    _gen_lock = None

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
        if "cuda" in device:
            try:
                cls._model = torch.compile(cls._model, mode="reduce-overhead")
                if log: log("⚡ torch.compile enabled (CUDA)", "ok")
            except Exception:
                pass
        if log: log("✓ Model sẵn sàng!","ok")

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

    @classmethod
    def set_seed(cls, seed): cls._seed = seed


def _safe_audio_load(path: str):
    """Load audio an toan - thu nhieu backend de tuong thich moi phien ban torchaudio."""
    import torchaudio
    errors = []
    # Thu lan luot cac backend
    for backend in [None, "soundfile", "ffmpeg", "sox"]:
        try:
            if backend is None:
                # Mac dinh - thu khong chi dinh backend
                t, sr = torchaudio.load(path)
            else:
                t, sr = torchaudio.load(path, backend=backend)
            return t, sr
        except Exception as e:
            errors.append(f"{backend}: {e}")
            continue
    # Tat ca that bai - thu scipy
    try:
        import scipy.io.wavfile as _wav
        import torch, numpy as np
        sr, data = _wav.read(path)
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        t = torch.from_numpy(data).unsqueeze(0) if data.ndim == 1 else torch.from_numpy(data.T)
        return t, sr
    except Exception as e:
        errors.append(f"scipy: {e}")
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
    """Luu tensor thanh MP3 320kbps."""
    import torchaudio
    # Dam bao thu muc ton tai
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp.wav"
    # Luu WAV tam
    try:
        torchaudio.save(tmp, tensor, 24000)
    except Exception:
        import soundfile as _sf
        _sf.write(tmp, tensor.squeeze().cpu().numpy(), 24000)
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
        try: os.remove(tmp)
        except: pass
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode()[-300:])
    except (FileNotFoundError, OSError):
        # ffmpeg khong co → doi duoi .mp3 thanh .wav, giu nguyen WAV da save
        wav_path = path.replace(".mp3", ".wav")
        try:
            import shutil as _sh
            _sh.move(tmp, wav_path)
        except Exception:
            pass


def to_wav(tensor, path):
    """Lưu tensor thành WAV 32-bit — KHÔNG post-process ở đây."""
    import torchaudio
    torchaudio.save(path, tensor, 24000, encoding="PCM_F", bits_per_sample=32)

def _ensure_deps():
    """
    Kiem tra va cai tu dong cac thu vien con thieu khi khoi dong app.
    Chay trong background thread, khong block UI.
    """
    import sys, subprocess as _sp

    REQUIRED = [
        ("firebase_admin", "firebase-admin"),  # Bat buoc cho dang nhap
        ("omnivoice",      "omnivoice"),        # Bat buoc cho tao voice
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
        self.geometry("580x600")
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
                              ("design","Voice Design","✨"),
                              ("auto","Auto","🎲")]:
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
            self.result=VoiceProfile(
            name=name, mode=mode,
            ref_audio=self.ref_audio_var.get().strip(),
            ref_text=self.ref_text_var.get().strip(),
            instruct=self.instruct_var.get().strip(),
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
    # 4. -- -> ngat
    txt = _re.sub(r"\s*--\s*", ", ", txt)
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


# ══════════════════════════ EDGE TTS VOICES (module-level) ═══════════
# Phai dat o module-level de moi noi (build_left, build_sidebar) deu dung duoc
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
    ("en-US-BrianNeural",       "🇺🇸 Brian - Nam Mỹ (nghiêm túc)"),
    ("en-US-DavisNeural",       "🇺🇸 Davis - Nam Mỹ (truyền cảm)"),
    ("en-US-JasonNeural",       "🇺🇸 Jason - Nam Mỹ (trẻ trung)"),
    ("en-US-TonyNeural",        "🇺🇸 Tony - Nam Mỹ (sôi nổi)"),
    # ── 🇬🇧 Tieng Anh Anh ──
    ("en-GB-SoniaNeural",       "🇬🇧 Sonia - Nữ Anh (chuẩn, thanh lịch)"),
    ("en-GB-LibbyNeural",       "🇬🇧 Libby - Nữ Anh (trẻ, hiện đại)"),
    ("en-GB-MaisieNeural",      "🇬🇧 Maisie - Nữ Anh (nhẹ nhàng)"),
    ("en-GB-RyanNeural",        "🇬🇧 Ryan - Nam Anh (chuẩn, trầm)"),
    ("en-GB-ThomasNeural",      "🇬🇧 Thomas - Nam Anh (trang trọng)"),
    # ── 🇦🇺 Tieng Anh Uc ──
    ("en-AU-NatashaNeural",     "🇦🇺 Natasha - Nữ Úc (tự nhiên)"),
    ("en-AU-WilliamNeural",     "🇦🇺 William - Nam Úc (trầm ấm)"),
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
    ("zh-CN-XiaochenNeural",    "🇨🇳 Xiaochen - Nữ Trung (chậm)"),
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
        ("Female Indian",          "female, young adult, indian accent"),
        ("Male Indian",            "male, young adult, indian accent"),
        ("Female Korean",          "female, young adult, korean accent"),
        ("Female Japanese",        "female, young adult, japanese accent"),
        ("Male Russian",           "male, middle-aged, russian accent"),
        ("Female Portuguese",      "female, young adult, portuguese accent"),
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
        tk.Label(hdr, text="Voice Design: kết hợp thuộc tính để tạo giọng",
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

        self.cat_btns = {}
        self.current_cat = tk.StringVar()
        for cat in VOICE_PRESETS:
            b = tk.Button(cat_frame, text=cat, font=(FN, 9),
                          bg=P["white"], fg=P["label"], relief="flat",
                          cursor="hand2", anchor="w", padx=12, pady=6,
                          command=lambda c=cat: self._show_cat(c))
            b.pack(fill="x")
            self.cat_btns[cat] = b

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

        tk.Label(right, text="🔧 Tự Tùy Chỉnh",
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
            ("Accent EN",  "accent", ["(auto)", "american accent", "british accent",
                                       "australian accent", "canadian accent",
                                       "indian accent", "korean accent",
                                       "japanese accent", "russian accent",
                                       "portuguese accent"]),

        ]
        for label, key, options in attrs:
            tk.Label(right, text=label+":", font=(FN, 8),
                     bg=P["white"], fg=P["label"]).pack(anchor="w", padx=12, pady=(4,0))
            var = tk.StringVar(value=options[0])
            self._attr_vars[key] = var
            cb = ttk.Combobox(right, textvariable=var, values=options,
                              state="readonly", width=22, font=(FN, 8))
            cb.pack(padx=12, pady=(0,2), fill="x")
            cb.bind("<<ComboboxSelected>>", self._update_preview)

        tk.Frame(right, bg=P["border"], height=1).pack(fill="x", padx=8, pady=6)
        tk.Label(right, text="Instruct string:", font=(FN, 8, "bold"),
                 bg=P["white"], fg=P["label"]).pack(anchor="w", padx=12)
        self.preview_var = tk.StringVar(value="")
        preview_en = tk.Entry(right, textvariable=self.preview_var,
                              font=(FN, 9), bg=P["sidebar"], fg=P["purple"],
                              relief="flat", highlightthickness=1,
                              highlightbackground=P["border"])
        preview_en.pack(padx=12, fill="x", ipady=4, pady=(2,6))

        # Bottom buttons
        tk.Frame(self, bg=P["border"], height=1).pack(fill="x")
        btn_row = tk.Frame(self, bg=P["bg"])
        btn_row.pack(fill="x", padx=16, pady=10)

        self.use_btn = tk.Button(btn_row, text="✅  Dùng Giọng Này",
                                  command=self._use,
                                  font=(FN, 11, "bold"), bg=P["purple"], fg="white",
                                  relief="flat", cursor="hand2", padx=20, pady=8,
                                  state="disabled")
        self.use_btn.pack(side="left")
        tk.Button(btn_row, text="🔧 Dùng Custom",
                  command=self._use_custom,
                  font=(FN, 9), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=12, pady=6
                  ).pack(side="left", padx=(8, 0))
        tk.Button(btn_row, text="Đóng", command=self.destroy,
                  font=(FN, 9), bg=P["bg"], fg=P["sub"],
                  relief="flat", cursor="hand2", padx=12
                  ).pack(side="right")

        # Show first category
        first_cat = list(VOICE_PRESETS.keys())[0]
        self._show_cat(first_cat)

    def _show_cat(self, cat):
        for k, b in self.cat_btns.items():
            b.configure(bg=P["sel"] if k == cat else P["white"],
                        fg=P["purple"] if k == cat else P["label"],
                        font=(FN, 9, "bold") if k == cat else (FN, 9))
        self.preset_lb.delete(0, "end")
        self._preset_data = VOICE_PRESETS.get(cat, [])
        for name, instruct in self._preset_data:
            self.preset_lb.insert("end", f"  {name}")
        self.use_btn.config(state="disabled")

    def _on_select(self, event=None):
        sel = self.preset_lb.curselection()
        if sel:
            _, instruct = self._preset_data[sel[0]]
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

    def _use(self):
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
            if _du and _vu:
                print(f"[Update] Dung URL tu update_config.json: {_vu}")
                if extra:
                    print(f"[Update] Extra files: {list(extra.keys())}")
                return _du, _vu, extra
    except Exception as _e:
        print(f"[Update] Loi doc update_config.json: {_e}")
    return _UPDATE_DEFAULT_URL, _UPDATE_DEFAULT_VER, {}

UPDATE_URL, VERSION_URL, UPDATE_EXTRA_FILES = _load_update_config()

# Doc version tu file local version.txt (duoc cap nhat cung voi magicvoice_gui.py)
def _read_local_version():
    try:
        vf = Path(__file__).parent / "version.txt"
        if vf.exists():
            return vf.read_text(encoding="utf-8").strip()
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
        """Tai file moi, backup ban cu, khoi dong lai."""
        try:
            import urllib.request, shutil

            script = Path(__file__).resolve()
            backup = script.with_suffix(".py.bak")

            # Progress window
            prog = tk.Toplevel(root)
            prog.title("Dang cap nhat...")
            prog.geometry("360x120")
            prog.configure(bg=P["white"])
            prog.resizable(False, False)
            prog.grab_set()
            lbl = tk.Label(prog, text=f"Dang tai v{new_ver}...",
                           font=(FN,10), bg=P["white"], fg=P["purple"], pady=16)
            lbl.pack()
            bar_bg = tk.Frame(prog, bg=P["border"], height=6, width=300)
            bar_bg.pack()
            bar = tk.Frame(bar_bg, bg=P["purple"], height=6, width=0)
            bar.place(x=0, y=0, height=6)
            tk.Label(prog, text="Vui long cho...",
                     font=(FN,8), bg=P["white"], fg=P["dim"]).pack(pady=4)
            prog.update()

            # Animate bar
            for w in range(0, 280, 14):
                bar.config(width=w)
                prog.update()
                import time; time.sleep(0.02)

            # Backup & download
            shutil.copy(script, backup)
            urllib.request.urlretrieve(UPDATE_URL, str(script))

            # MOI: tai extra files (license_guard.py, ...)
            # Neu tai file nao loi -> rollback va bao loi
            extra_backups = {}
            try:
                for _fname, _furl in UPDATE_EXTRA_FILES.items():
                    _dest = script.parent / _fname
                    if _dest.exists():
                        _bak = _dest.with_suffix(_dest.suffix + ".bak")
                        shutil.copy(_dest, _bak)
                        extra_backups[str(_dest)] = str(_bak)
                    urllib.request.urlretrieve(_furl, str(_dest))
            except Exception as _ex_err:
                # Rollback: khoi phuc script chinh
                try: shutil.copy(backup, script)
                except Exception: pass
                # Rollback: khoi phuc extra files
                for _dp, _bp in extra_backups.items():
                    try: shutil.copy(_bp, _dp)
                    except Exception: pass
                raise RuntimeError(
                    f"Khong tai duoc file bo sung: {_ex_err}") from _ex_err

            # Luu version.txt local de lan sau khong hoi lai
            local_ver_file = script.parent / "version.txt"
            urllib.request.urlretrieve(VERSION_URL, str(local_ver_file))

            # FIX: Xoa CACHE CU truoc khi restart de tranh dung cache loi
            # tu phien ban truoc (vi du: ref_text Whisper transcribe sai luu vinh vien
            # vao voices_library.json, .deps_installed flag, __pycache__, .login_cache cu).
            # Voice clone se transcribe lai tu dau voi code moi -> chinh xac hon.
            _cache_cleared = []
            try:
                # 1. Xoa __pycache__ (cache bytecode Python cua phien ban cu)
                _pycache = script.parent / "__pycache__"
                if _pycache.exists():
                    shutil.rmtree(str(_pycache), ignore_errors=True)
                    _cache_cleared.append("__pycache__")

                # 2. Xoa .deps_installed flag de check lai dependencies
                _deps_flag = script.parent / ".deps_installed"
                if _deps_flag.exists():
                    _deps_flag.unlink()
                    _cache_cleared.append(".deps_installed")

                # 3. Xoa cac file _trim*.wav cache cu (ref_audio da cat)
                # de _prepare_ref_audio cat lai voi MAX_SEC moi
                for _trim_file in script.parent.rglob("*_trim*.wav"):
                    try:
                        _trim_file.unlink()
                        _cache_cleared.append(_trim_file.name)
                    except Exception:
                        pass

                # 4. Reset ref_text trong voices_library.json
                # Day la nguyen nhan chinh: ref_text bi rac tu Whisper sai phien ban truoc
                # Reset ve "" -> code moi se transcribe lai voi Whisper moi (chinh xac hon)
                # KHONG xoa voice, chi reset ref_text cua nhung voice co ref_audio
                _voices_file = script.parent / "voices_library.json"
                if _voices_file.exists():
                    try:
                        import json as _jc
                        _data = _jc.loads(_voices_file.read_text(encoding="utf-8"))
                        _reset_count = 0
                        for _v in _data:
                            # Chi reset voice clone (co ref_audio), khong dung voice design
                            if _v.get("ref_audio") and _v.get("ref_text"):
                                _old_ref = _v.get("ref_text", "")
                                # Chi reset neu nghi la rac:
                                # - Placeholder cu (Xin chao..., This is a sample...)
                                # - Qua ngan (< 10 ky tu - chac chan rac)
                                _is_garbage = (
                                    "Xin chào, đây là giọng đọc mẫu" in _old_ref
                                    or "This is a sample voice recording" in _old_ref
                                    or "Đây là đoạn ghi âm giọng" in _old_ref
                                    or len(_old_ref.strip()) < 10
                                )
                                if _is_garbage:
                                    _v["ref_text"] = ""
                                    _reset_count += 1
                        if _reset_count > 0:
                            _voices_file.write_text(
                                _jc.dumps(_data, ensure_ascii=False, indent=2),
                                encoding="utf-8")
                            _cache_cleared.append(f"reset {_reset_count} voice ref_text rac")
                    except Exception as _ve:
                        print(f"[Update] Loi reset ref_text: {_ve}")
            except Exception as _ce:
                print(f"[Update] Loi xoa cache: {_ce}")

            bar.config(width=300)
            prog.update()
            time.sleep(0.3)
            prog.destroy()

            _cache_msg = ""
            if _cache_cleared:
                _cache_msg = f"\n\nDa xoa cache cu: {', '.join(_cache_cleared[:5])}"
                if len(_cache_cleared) > 5:
                    _cache_msg += f" va {len(_cache_cleared)-5} muc khac"

            messagebox.showinfo(
                "Cap nhat thanh cong!",
                f"Da cap nhat len v{new_ver}!{_cache_msg}\n\n"
                "App se tu khoi dong lai ngay bay gio.")

            # Restart app
            import subprocess as _sp, sys as _sys
            _sp.Popen([_sys.executable, str(script)])
            root.after(300, root.destroy)

        except Exception as e:
            try: prog.destroy()
            except: pass
            messagebox.showerror("Loi cap nhat",
                f"Cap nhat that bai:\n{e}\n\nThu lai sau.")

    threading.Thread(target=_check, daemon=True).start()


class App(tk.Tk):
    def __init__(self, login_msg="", username=""):
        super().__init__()
        self._login_msg = login_msg
        self._username  = username

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
        self.geometry("1160x780")
        self.minsize(960,660)
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

        self.device_var   =tk.StringVar(value=self._cfg.get("device",
            "cuda:0" if __import__("torch").cuda.is_available() else "cpu"))
        self.dtype_var    =tk.StringVar(value=self._cfg.get("dtype","float16"))
        self.steps_var    =tk.IntVar(value=self._cfg.get("steps",8))
        self.speed_var    =tk.DoubleVar(value=1.0)
        self.vol_var      =tk.DoubleVar(value=1.0)
        self.pitch_var    =tk.DoubleVar(value=1.0)
        self.out_dir_var  =tk.StringVar(value=self._cfg.get("out_dir",
                            str(Path.home()/"Downloads"/"MagicVoice")))
        self.out_name_var =tk.StringVar(value="output")
        self.fmt_var      =tk.StringVar(value=self._cfg.get("fmt",".mp3"))
        self.post_proc_var=tk.BooleanVar(value=self._cfg.get("post_process", True))
        self.text_proc_var=tk.BooleanVar(value=self._cfg.get("text_process", True))
        self.gap_var      =tk.IntVar(value=300)
        self.narrator_var  =tk.BooleanVar(value=self._cfg.get('narrator_mode',False))
        self.script_proc_var=tk.BooleanVar(value=self._cfg.get('script_proc',False))
        self.srt_timeline_var = tk.BooleanVar(value=False)  # Mac dinh Sequential - doc tu nhien hon
        self.srt_entries: list[SRTEntry]=[]
        self._txt_files:  list[str]=[]

        # ── MOI: Naming options TOAN CUC (ap dung cho moi tab) ──
        # Mac dinh: prefix + so thu tu (voice_01, voice_02, ...)
        self.out_name_mode   = tk.StringVar(value=self._cfg.get("out_name_mode","prefix"))
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
        # Log thông tin voices khi khởi động
        self.after(300, self._log_startup_info)
        # Kiem tra mang NGAY khi khoi dong - set TRANSFORMERS_OFFLINE truoc khi load model
        self.after(100, self._init_network_mode)
        # Kiem tra update tu dong khi khoi dong (silent - khong thong bao neu dang moi nhat)
        self.after(3000, lambda: check_for_update(self, silent=True))
        self.after(800, self._check_gpu_and_warn)
        # Tự động tải model nếu đã từng tải trước đó
        if self._cfg.get("auto_load", True):
            self.after(1000, self._auto_load_model)  # Cho _init_network_mode chay truoc
        else:
            self._log("💡 Nhấn '⬇ Tải Model' để bắt đầu. Lần sau sẽ tự động tải!", "info")
        # Tu dong cai thu vien con thieu (dung sys.executable - chinh xac 100%)
        threading.Thread(target=_ensure_deps, daemon=True).start()

    def _detect_devices(self):
        self.devices=["cpu"]
        try:
            import torch
            for i in range(torch.cuda.device_count()):
                self.devices.append(f"cuda:{i}")
            if getattr(getattr(torch,"backends",None),"mps",None) and \
               torch.backends.mps.is_available():
                self.devices.append("mps")
        except: pass

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

        tk.Frame(main,bg=P["border"],width=1).pack(side="left",fill="y")

        # RIGHT — settings sidebar
        right=tk.Frame(main,bg=P["white"],width=290)
        right.pack(side="right",fill="y")
        right.pack_propagate(False)
        self._build_sidebar(right)

        # ── Statusbar ──
        tk.Frame(self,bg=P["border"],height=1).pack(fill="x")
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
              ("script","✍ Kịch Bản")]

        content=tk.Frame(parent,bg=P["bg"])
        content.pack(fill="both",expand=True)

        for key,label in tabs:
            frm=tk.Frame(content,bg=P["bg"])
            self.tab_frames[key]=frm
            btn=tk.Button(tab_bar,text=label,
                          command=lambda k=key:self._switch_tab(k),
                          font=(FN,10),relief="flat",cursor="hand2",
                          padx=18,pady=11,bg=P["bg"],fg=P["sub"])
            btn.pack(side="left")
            self.tab_btns[key]=btn
            self._tab_labels[key]=label   # luu label goc

        self._build_text_tab(self.tab_frames["text"])
        self._build_srt_tab(self.tab_frames["srt"])
        self._build_batch_tab(self.tab_frames["batch"])
        self._build_clone_tab(self.tab_frames["clone"])
        self._build_script_tab(self.tab_frames["script"])
        self._switch_tab("text")

    def _switch_tab(self, key):
        if key == "srt" and hasattr(self, "_refresh_srt_voices"):
            self.after(50, self._refresh_srt_voices)
        for k,f in self.tab_frames.items():
            f.pack_forget()
        self.tab_frames[key].pack(fill="both",expand=True,padx=0)
        for k,b in self.tab_btns.items():
            active=k==key
            # MOI: danh dau tab dang chay bang cham tron (•)
            is_run = (k == getattr(self, "_running_tab", None))
            _orig = self._tab_labels.get(k, "") if hasattr(self, "_tab_labels") else b.cget("text").replace(" •","").rstrip()
            _label = _orig + (" •" if is_run else "")
            b.configure(
                text=_label,
                fg=(P["red"] if is_run else (P["purple"] if active else P["sub"])),
                bg=P["white"] if active else P["bg"],
                font=(FN,10,"bold") if (active or is_run) else (FN,10),
            )

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
                b.configure(
                    text=_label,
                    fg=(P["red"] if is_run else (P["purple"] if active else P["sub"])),
                    bg=P["white"] if active else P["bg"],
                    font=(FN,10,"bold") if (active or is_run) else (FN,10),
                )
        except Exception:
            pass

    # ─────── Tab: Văn Bản ──────────────────────────────────────────
    def _build_text_tab(self, p):
        inner = tk.Frame(p, bg=P["white"],
                         highlightthickness=1,
                         highlightbackground=P["border"])
        inner.pack(fill="both", expand=True, padx=14, pady=10)

        # ── Toolbar ──
        tb = tk.Frame(inner, bg=P["white"], pady=6)
        tb.pack(fill="x", padx=10)
        tk.Label(tb, text="Nhập văn bản cần đọc",
                 font=(FN,10), bg=P["white"],
                 fg=P["label"]).pack(side="left")
        self.char_lbl = tk.Label(tb, text="0 ký tự",
                                  font=(FN,9), bg=P["white"], fg=P["dim"])
        self.char_lbl.pack(side="right")
        for txt, cmd in [("📂 Mở TXT", self._import_txt),
                          ("🗑 Xóa", lambda: self.txt_in.delete("1.0","end"))]:
            tk.Button(tb, text=txt, command=cmd,
                      font=(FN,9), bg=P["hover"], fg=P["label"],
                      relief="flat", cursor="hand2", padx=8, pady=3
                      ).pack(side="right", padx=(0,4))

        tk.Frame(inner, bg=P["border"], height=1).pack(fill="x")

        # ── Char cleaner bar ──
        cbar = tk.Frame(inner, bg=P["sidebar"], pady=4)
        cbar.pack(fill="x")
        tk.Label(cbar, text="  Xóa ký tự:",
                 font=(FN,8), bg=P["sidebar"],
                 fg=P["dim"]).pack(side="left")
        for lbl, ch in [("*","*"),("/","/"),(  "#","#"),("---","---"),("...","...")]:
            tk.Button(cbar, text=lbl,
                      command=lambda c=ch: self._del_char_from_text(c),
                      font=("Consolas",8), bg=P["white"], fg=P["text"],
                      relief="flat", cursor="hand2", padx=6, pady=2,
                      highlightthickness=1,
                      highlightbackground=P["border"]
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
                  relief="flat", cursor="hand2", padx=8, pady=3
                  ).pack(side="left", padx=4)
        tk.Button(cbar, text="🔄 Khôi phục",
                  command=self._restore_text,
                  font=(FN,8), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=8, pady=3
                  ).pack(side="left", padx=2)

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
                  ).pack(side="left")
        self.srt_cnt_lbl=tk.Label(top,text="",font=(FN,9),
                                   bg=P["white"],fg=P["dim"])
        self.srt_cnt_lbl.pack(side="right")

        # Che do TTS: MagicVoice vs Edge TTS
        self.srt_tts_mode = tk.StringVar(value="magic")
        def _on_srt_mode_change(*a):
            is_edge = self.srt_tts_mode.get() == "edge"
            self.srt_voice_cb.pack_forget() if is_edge else None
            self.srt_edge_cb.pack_forget() if not is_edge else None
            if is_edge:
                self.srt_edge_cb.pack(side="right", padx=(0,4))
                self.srt_voice_info.config(text="🌐 EDGE", fg="#2563eb")
            else:
                self.srt_voice_cb.pack(side="right", padx=(0,4))
                self._refresh_srt_voices()

        tk.Radiobutton(top, text="🌐 Edge", variable=self.srt_tts_mode,
                       value="edge", font=(FN,8), bg=P["white"],
                       fg="#2563eb", activebackground=P["white"],
                       command=_on_srt_mode_change).pack(side="right", padx=(4,0))
        tk.Radiobutton(top, text="🤖 MagicVoice", variable=self.srt_tts_mode,
                       value="magic", font=(FN,8), bg=P["white"],
                       fg=P["purple"], activebackground=P["white"],
                       command=_on_srt_mode_change).pack(side="right", padx=(8,2))

        # Voice selector trong toolbar
        tk.Label(top, text="🎙", font=(FN,11),
                 bg=P["white"], fg=P["purple"]).pack(side="right", padx=(8,2))
        self.srt_voice_info = tk.Label(top, text="", font=(FN,8),
                                        bg=P["white"], fg=P["purple"])
        self.srt_voice_info.pack(side="right")
        self.srt_voice_var = tk.StringVar()
        self.srt_voice_cb  = ttk.Combobox(top, textvariable=self.srt_voice_var,
                                           state="readonly", font=(FN,9), width=22)
        self.srt_voice_cb.pack(side="right", padx=(0,4))
        # Edge TTS voice selector (an khi dung MagicVoice)
        # FIX: Dung EDGE_VOICES_LIST module-level (60 giong) thay vi self._edge_voices
        # vi luc nay sidebar chua build -> self._edge_voices chua ton tai
        self.srt_edge_voice_var = tk.StringVar()
        self.srt_edge_voice_display = tk.StringVar()
        self.srt_edge_cb = ttk.Combobox(top, textvariable=self.srt_edge_voice_display,
                                         state="readonly", font=(FN,9), width=32)
        self.srt_edge_cb["values"] = [v[1] for v in EDGE_VOICES_LIST]
        self.srt_edge_cb.set(EDGE_VOICES_LIST[0][1])
        self.srt_edge_voice_var.set(EDGE_VOICES_LIST[0][0])
        self.srt_edge_voice_display.set(EDGE_VOICES_LIST[0][1])
        # Khi user chon voice -> cap nhat voice_var (la code voice goc)
        def _on_srt_edge_pick(e):
            idx = self.srt_edge_cb.current()
            if 0 <= idx < len(EDGE_VOICES_LIST):
                self.srt_edge_voice_var.set(EDGE_VOICES_LIST[idx][0])
                self.srt_edge_voice_display.set(EDGE_VOICES_LIST[idx][1])
        self.srt_edge_cb.bind("<<ComboboxSelected>>", _on_srt_edge_pick)
        tk.Label(top, text="Voice:", font=(FN,9,"bold"),
                 bg=P["white"], fg=P["purple"]).pack(side="right", padx=(0,2))
        tk.Button(top, text="↻", command=self._refresh_srt_voices,
                  font=(FN,8), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=4
                  ).pack(side="right")
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

        tk.Label(left_pane,
                 text="📝 Nhập văn bản hoặc SRT:",
                 font=(FN,9,"bold"),bg=P["white"],fg=P["label"]
                 ).pack(anchor="w",padx=8,pady=(6,2))

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

        # Timeline mode
        opt2=tk.Frame(inner,bg=P["white"],pady=2); opt2.pack(fill="x",padx=10)
        tk.Checkbutton(opt2,
                       text="📐 Khớp đúng Timeline SRT (mỗi câu đặt đúng timestamp)",
                       variable=self.srt_timeline_var,
                       bg=P["white"],fg=P["purple"],font=(FN,9,"bold"),
                       selectcolor=P["white"],activebackground=P["white"]
                       ).pack(side="left")
        tk.Label(opt2,
                 text="  ← Tắt = ghép tuần tự (file ngắn hơn)",
                 bg=P["white"],fg=P["dim"],font=(FN,8)
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
        Chia text thanh cac dong SRT theo min/max tu.
        FIX: Gop CROSS-PARAGRAPH de moi dong deu trong khoang [min_w, max_w].
        Truoc day: paragraph ngan -> chunk ngan, khong ton trong min_w.
        Gio: dồn toan bo unit thanh 1 list, chi chia khi dat min_w va gan max_w.
        Chi dong CUOI CUNG cua toan bo text moi co the < min_w (vi het noi dung).
        """
        import re as _re
        paras = [p.strip() for p in _re.split(r"\n\s*\n", text) if p.strip()]

        # B1: gom TOAN BO units cua TOAN BO paragraph thanh 1 list
        all_units = []
        for para in paras:
            units = self._split_clauses(para) if by_clause else para.split()
            all_units.extend(units)

        # B2: chia all_units thanh chunks theo min/max
        chunks = []
        cur, cw = [], 0
        for u in all_units:
            uw = self._count_words(u)
            if cw == 0:
                cur.append(u); cw += uw
            elif cw < min_w:
                # CHUA du min -> bat buoc them, ke ca khi vuot max
                cur.append(u); cw += uw
                if cw >= max_w:
                    chunks.append(" ".join(cur).strip()); cur, cw = [], 0
            else:
                # cur da du min_w
                if cw + uw <= max_w:
                    cur.append(u); cw += uw
                    if cw >= max_w:
                        chunks.append(" ".join(cur).strip()); cur, cw = [], 0
                elif cw + uw <= max_w + ovfl:
                    cur.append(u); cw += uw
                    chunks.append(" ".join(cur).strip()); cur, cw = [], 0
                else:
                    chunks.append(" ".join(cur).strip())
                    cur, cw = [u], uw

        # B3: xu ly chunk cuoi cung
        if cur:
            joined = " ".join(cur).strip()
            if cw < min_w and chunks:
                last = chunks[-1]
                if self._count_words(last) + cw <= max_w + ovfl:
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

    def _make_srt(self, lines, mpc, gap):
        """
        Tinh thoi gian SRT dua tren ca ki tu va so tu.
        Dam bao du thoi gian de doc het dong.

        FIX: MS_PER_WORD scale theo mpc thay vi hardcode 350.
        Truoc day: mpc=20 cung khong co tac dung vi MS_PER_WORD=350
        ghi de gia tri tinh theo char.
        Gio: MS_PER_WORD ti le voi mpc (mpc=60 -> ~350, mpc=20 -> ~115)
        => khi user chinh mpc thap se thay tac dung.
        """
        srt, t, idx = "", 0, 1
        # ms moi tu = mpc * 5.83 (vi mpc=60 cho ra ~350ms/word, ti le tu nhien)
        ms_per_word = max(int(mpc * 5.83), 50)  # toi thieu 50ms/word de an toan
        # Floor toi thieu cho 1 dong (truoc day: 800ms; gio scale theo mpc)
        floor_ms = max(int(mpc * 13), 200)  # mpc=60->780, mpc=20->260
        for line in lines:
            if not line.strip(): continue
            n_chars = len(line)
            n_words = len(line.split())
            # Lay max giua tinh theo ki tu va tinh theo tu
            dur_by_char = n_chars * mpc
            dur_by_word = n_words * ms_per_word
            dur = max(dur_by_char, dur_by_word, floor_ms)
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

        # Nhịp nghỉ
        tk.Label(sbar, text="  Ngưỡng câu dài:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        self.script_thresh = tk.IntVar(value=60)
        tk.Spinbox(sbar, from_=30, to=200, textvariable=self.script_thresh,
                   width=4, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(sbar, text="ký tự  |",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")

        # SRT settings
        tk.Label(sbar, text="  SRT — Min:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        self.srt_min_w = tk.IntVar(value=20)
        tk.Spinbox(sbar, from_=3, to=30, textvariable=self.srt_min_w,
                   width=3, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(sbar, text="Max:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        self.srt_max_w = tk.IntVar(value=30)
        tk.Spinbox(sbar, from_=8, to=50, textvariable=self.srt_max_w,
                   width=3, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(sbar, text="từ  |",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")

        self.srt_by_clause = tk.BooleanVar(value=True)
        tk.Checkbutton(sbar, text="Tách mệnh đề",
                       variable=self.srt_by_clause,
                       font=(FN,8), bg=P["sidebar"], fg=P["label"],
                       activebackground=P["sidebar"],
                       cursor="hand2").pack(side="left", padx=4)
        tk.Label(sbar, text="|  ms/ký tự:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        self.srt_mpc = tk.IntVar(value=60)
        tk.Spinbox(sbar, from_=30, to=200, textvariable=self.srt_mpc,
                   width=4, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(sbar, text="Gap:",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")
        self.srt_gap = tk.IntVar(value=150)
        tk.Spinbox(sbar, from_=0, to=2000, textvariable=self.srt_gap,
                   width=5, font=(FN,8), bg=P["white"], relief="flat"
                   ).pack(side="left", padx=2)
        tk.Label(sbar, text="ms",
                 font=(FN,8), bg=P["sidebar"], fg=P["dim"]).pack(side="left")

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

        # Cột 2: Kịch bản đã xử lý
        col2 = tk.Frame(main, bg=P["white"])
        col2.pack(side="left", fill="both", expand=True, padx=2, pady=2)

        h2 = tk.Frame(col2, bg=P["white"])
        h2.pack(fill="x", padx=6, pady=(4,2))
        tk.Label(h2, text="✅ Kịch bản đã xử lý",
                 font=(FN,9,"bold"), bg=P["white"],
                 fg=P["green"]).pack(side="left")
        tk.Button(h2, text="📋",
                  command=self._script_copy,
                  font=(FN,8), bg=P["hover"], fg=P["label"],
                  relief="flat", cursor="hand2", padx=4, pady=1
                  ).pack(side="right")

        self.script_out = tk.Text(col2, font=(FN,10), wrap="word",
                                   bg="#f8fffe", fg=P["text"],
                                   relief="flat", padx=6, pady=4,
                                   highlightthickness=0)
        sb2 = ttk.Scrollbar(col2, command=self.script_out.yview)
        self.script_out.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self.script_out.pack(fill="both", expand=True)

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
            lines = self._do_split(txt,
                                   min_w=self.srt_min_w.get(),
                                   max_w=self.srt_max_w.get(),
                                   ovfl=4,
                                   by_clause=self.srt_by_clause.get())
            lines = [l for l in lines if l.strip()]
            mpc = self.srt_mpc.get()
            gap = self.srt_gap.get()
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

        # Header
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

        # Search
        sf=tk.Frame(inner,bg=P["bg"],
                    highlightthickness=1,highlightbackground=P["border"])
        sf.pack(fill="x",pady=(0,8))
        tk.Label(sf,text="🔍",bg=P["white"],fg=P["dim"],font=(FN,11),padx=6).pack(side="left")
        self.search_var=tk.StringVar()
        self.search_var.trace_add("write",lambda *_:self._refresh_voices())
        tk.Entry(sf,textvariable=self.search_var,font=(FN,10),
                 bg=P["white"],fg=P["text"],relief="flat",
                 insertbackground=P["purple"],
                 highlightthickness=0).pack(side="left",fill="x",expand=True,ipady=6)

        # Voice cards grid
        self.voice_scroll_frame=tk.Frame(inner,bg=P["bg"])
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

        # Bottom action bar
        act=tk.Frame(inner,bg=P["bg"],pady=4)
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
        mode_color={"clone":P["purple"],"design":P["blue"],"auto":P["gold"]}
        mode_icon={"clone":"🎯","design":"✨","auto":"🎲"}
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

    def _browse_voices(self):
        """Mở dialog duyệt 600+ giọng Voice Design"""
        def on_select(instruct):
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
        for val,lbl in [("omnivoice","MagicVoice"),("edge","Edge TTS")]:
            is_sel = val == "omnivoice"
            b=tk.Button(m_row,text=lbl,command=lambda v=val:self._set_tts_mode(v),
                        font=(FN,9,"bold" if is_sel else "normal"),
                        relief="flat",cursor="hand2",padx=16,pady=6,
                        bg=P["purple"] if is_sel else P["bg"],
                        fg="white" if is_sel else P["sub"],
                        bd=0, highlightthickness=0,
                        activebackground=P["purple2"],activeforeground="white")
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
        tk.Frame(parent,bg=P["border"],height=1).pack(fill="x",padx=10,pady=6)

        # ── Section: Thiết Kế Giọng Edge ── (ẩn mặc định, chỉ hiện khi chọn Edge TTS)
        self._edge_design_frame = tk.Frame(parent, bg=P["white"])
        # KHÔNG pack ngay — _set_tts_mode sẽ điều khiển ẩn/hiện
        _ep = self._edge_design_frame   # alias ngắn để dùng dưới đây
        self._sb_section(_ep,"🎙 Thiết Kế Giọng Edge TTS")

        # Danh sách giọng Edge theo ngôn ngữ
        EDGE_FULL = {
            "🇺🇸 English (US)": [
                ("en-US-AriaNeural",   "Aria",   "Nữ", "Tự nhiên, trẻ trung"),
                ("en-US-JennyNeural",  "Jenny",  "Nữ", "Rõ ràng, chuyên nghiệp"),
                ("en-US-EmmaNeural",   "Emma",   "Nữ", "Trẻ, năng động"),
                ("en-US-MichelleNeural","Michelle","Nữ","Ấm áp, thân thiện"),
                ("en-US-AndrewNeural", "Andrew", "Nam","Ấm, tự nhiên"),
                ("en-US-GuyNeural",    "Guy",    "Nam","Trầm, mạnh mẽ"),
                ("en-US-ChristopherNeural","Christopher","Nam","Chắc chắn"),
                ("en-US-EricNeural",   "Eric",   "Nam","Trung tính, rõ"),
            ],
            "🇬🇧 English (UK)": [
                ("en-GB-SoniaNeural",  "Sonia",  "Nữ", "Anh chuẩn, thanh lịch"),
                ("en-GB-LibbyNeural",  "Libby",  "Nữ", "Trẻ, hiện đại"),
                ("en-GB-MaisieNeural", "Maisie", "Nữ", "Nhẹ nhàng"),
                ("en-GB-RyanNeural",   "Ryan",   "Nam","Anh chuẩn, trầm"),
                ("en-GB-ThomasNeural", "Thomas", "Nam","Trang trọng"),
            ],
            "🇦🇺 English (AU)": [
                ("en-AU-NatashaNeural","Natasha","Nữ","Úc tự nhiên"),
                ("en-AU-CarlyNeural",  "Carly",  "Nữ","Vui vẻ"),
                ("en-AU-WilliamNeural","William","Nam","Úc trầm ấm"),
                ("en-AU-DarrenNeural", "Darren", "Nam","Mạnh mẽ"),
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
                ("ko-KR-SunHiNeural",  "SunHi",  "Nữ","Hàn tự nhiên"),
                ("ko-KR-InJoonNeural", "InJoon", "Nam","Hàn trầm"),
            ],
            "🇨🇳 Chinese": [
                ("zh-CN-XiaoxiaoNeural","Xiaoxiao","Nữ","Phổ thông, ấm"),
                ("zh-CN-YunyangNeural","Yunyang","Nam","Phổ thông, rõ"),
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
        vlist_frame.pack(fill="x", padx=10, pady=4)
        self._edge_listbox = tk.Listbox(vlist_frame,
                                         font=(FN,8), height=5,
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
        Dung flag file .cache_cleared_v317 de chi chay 1 lan.
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
            _flag = _script_dir / ".cache_cleared_v317"
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
                _flag.write_text(f"v3.17 cleared: {', '.join(_cleared)}", encoding="utf-8")
            except Exception: pass

            if _cleared:
                print(f"[AutoClearCache] Da xoa: {', '.join(_cleared)}")
        except Exception as _e:
            print(f"[AutoClearCache] Loi: {_e}")

    def _init_network_mode(self):
        """Kiem tra mang ngay khi khoi dong, set env vars va socket timeout."""
        import os as _os, socket as _sock, time as _t
        try:
            _s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
            _s.settimeout(2)
            _s.connect(("8.8.8.8", 53))
            _s.close()
            online = True
        except Exception:
            online = False

        self._apply_network_mode(online)
        self._online_cache_val  = online
        self._online_cache_time = _t.time()

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
        if hasattr(self, "_online_cache_time") and            now - self._online_cache_time < 10:
            return self._online_cache_val
        try:
            _sock.setdefaulttimeout(2)
            s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
            s.connect(("8.8.8.8", 53))
            s.close()
            result = True
        except Exception:
            result = False
        self._online_cache_time = now
        self._online_cache_val  = result
        return result

    def _check_network_badge(self, parent):
        """Hien badge Offline neu mat mang."""
        def _check():
            import socket as _sock
            try:
                _sock.setdefaulttimeout(3)
                _sock.socket().connect(("8.8.8.8", 53))
                online = True
            except:
                online = False
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
        messagebox.showinfo("Da luu", f"Da them '{vp.name}' vao Cai Dat San!")

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
        # An/hien toan bo khung Thiet Ke Giong Edge TTS
        if hasattr(self, "_edge_design_frame"):
            if mode == "edge":
                # Pack TRUOC _preset_section_frame (ca separator + label + list)
                if hasattr(self, "_preset_section_frame"):
                    self._edge_design_frame.pack(
                        fill="x", pady=(0,4),
                        before=self._preset_section_frame)
                else:
                    self._edge_design_frame.pack(fill="x", pady=(0,4))
            else:
                self._edge_design_frame.pack_forget()

        # An/hien phan Cai Dat San (Voices) - chi hien khi dung MagicVoice
        if hasattr(self, "_preset_section_frame"):
            if mode == "edge":
                self._preset_section_frame.pack_forget()
            else:
                self._preset_section_frame.pack(fill="both", expand=True)

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

        # Preset list — hiện TẤT CẢ voice, có nút X xóa
        for w in self.preset_frame.winfo_children(): w.destroy()
        for i, vp in enumerate(self.lib.profiles):
            mode_icon = {"clone":"🎯","design":"✨","auto":"🎲","edge":"🌐"}.get(vp.mode,"●")
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

            # Nút X xóa (ẩn với voice Auto)
            if vp.mode != "auto" or i > 0:
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
                # Tu dong chuyen mode dung theo loai preset
                if vp_clicked.mode == "edge" and vp_clicked.instruct.startswith("edge:"):
                    edge_code = vp_clicked.instruct.replace("edge:","").strip()
                    if hasattr(self,"edge_voice_var"):
                        self.edge_voice_var.set(edge_code)
                    if hasattr(self,"edge_cb") and hasattr(self,"_edge_voices"):
                        codes = [v[0] for v in self._edge_voices]
                        if edge_code in codes:
                            self.edge_cb.current(codes.index(edge_code))
                    self._set_tts_mode("edge")
                else:
                    self._set_tts_mode("omnivoice")
                self._refresh_voices()
                self._update_sidebar()
            row.bind("<Button-1>", click)
            name_lbl.bind("<Button-1>", click)

    # ─────── STATUS BAR ────────────────────────────────────────────
    def _build_statusbar(self):
        bar=tk.Frame(self,bg=P["white"],pady=0)
        bar.pack(fill="x")

        # Left: status + progress
        left=tk.Frame(bar,bg=P["white"]); left.pack(side="left",fill="x",expand=True,padx=14,pady=6)
        self.status_lbl=tk.Label(left,text="Sẵn sàng",font=(FN,9),
                                  bg=P["white"],fg=P["sub"])
        self.status_lbl.pack(side="left")
        self._timer_label=tk.Label(left,text="",font=(FN,9,"bold"),
                                    bg=P["white"],fg=P["purple"])
        self._timer_label.pack(side="left",padx=(8,0))
        self._timer_running=False
        self._timer_start=0.0
        self.pb=ttk.Progressbar(left,mode="determinate",maximum=100,length=180)
        self.pb.pack(side="left",padx=(12,0))

        # Right: output dir + format + BIG CREATE BUTTON
        right=tk.Frame(bar,bg=P["white"]); right.pack(side="right",padx=0,pady=0)

        # Output dir mini
        of_mini=tk.Frame(right,bg=P["white"]); of_mini.pack(side="left",padx=8)
        tk.Label(of_mini,text="Lưu tại:",font=(FN,8),
                 bg=P["white"],fg=P["dim"]).pack(anchor="w")
        tk.Entry(of_mini,textvariable=self.out_dir_var,font=(FN,8),
                 bg=P["sidebar"],fg=P["label"],relief="flat",
                 highlightthickness=1,highlightbackground=P["border"],
                 width=22).pack(ipady=3)

        tk.Button(right,text="📂",command=self._browse_out,
                  font=(FN,10),bg=P["white"],fg=P["sub"],relief="flat",
                  cursor="hand2",padx=4).pack(side="left")

        # MOI: nut cau hinh naming toan cuc
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
        self.create_btn=tk.Button(right,text="  ▶  Tạo  ",
                                   command=self._create,
                                   font=(FN,12,"bold"),
                                   bg=P["purple"],fg="white",
                                   activebackground=P["purple2"],
                                   activeforeground="white",
                                   relief="flat",cursor="hand2",
                                   padx=28,pady=12)
        self.create_btn.pack(side="left",padx=(4,0))

        # Log (collapsible)
        log_bar=tk.Frame(self,bg=P["bg"]); log_bar.pack(fill="x")
        tk.Label(log_bar,text="📋 Log:",font=(FN,8),
                 bg=P["bg"],fg=P["dim"],padx=8).pack(side="left",pady=2)
        tk.Button(log_bar,text="Xóa",command=lambda:self.logbox.delete("1.0","end"),
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
    def _preview_voice(self):
        """Tạo và phát thử giọng đang chọn với câu mẫu ngắn."""
        if not self.model_loaded:
            messagebox.showwarning("Chưa tải model", "Hãy tải model trước!"); return
        if hasattr(self, "_prev_thread") and self._prev_thread and self._prev_thread.is_alive():
            return
        vp = self.lib.profiles[self.sel_idx] if 0 <= self.sel_idx < len(self.lib.profiles) else None
        vname = vp.name if vp else "Auto"
        # Câu mẫu ngắn để thử giọng
        sample = "Hello! This is a quick voice preview. How does this sound to you?"
        self.prev_btn.config(text="⏳ Đang tạo...", state="disabled", bg="#fef9c3")
        self._log(f"🎵 Thử giọng: {vname}", "info")

        def _gen():
            try:
                import torchaudio, tempfile, os
                kw = self._vkw()
                a  = Backend.gen(sample, num_step=self.steps_var.get(),
                                 speed=self._get_speed(), **kw)
                # Lưu file tạm
                tmp = tempfile.mktemp(suffix=".wav")
                torchaudio.save(tmp, a[0], 24000)
                self._prev_tmp = tmp
                # Phát bằng player hệ thống
                if sys.platform == "win32":
                    import winsound
                    self.after(0, lambda: self.prev_btn.config(
                        text="🔊 Đang phát...", bg="#dbeafe"))
                    winsound.PlaySound(tmp, winsound.SND_FILENAME)
                else:
                    import subprocess as _sp
                    _sp.Popen(["aplay", tmp])
                self._log(f"✅ Thử giọng xong: {vname}", "ok")
            except Exception as e:
                self._log(f"❌ Lỗi thử giọng: {e}", "err")
            finally:
                self.after(0, lambda: self.prev_btn.config(
                    text="▶  Thử Giọng", state="normal",
                    bg="#f0fdf4"))

        import threading
        self._prev_thread = threading.Thread(target=_gen, daemon=True)
        self._prev_thread.start()

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
        self._log("⏹ Đã dừng thử giọng", "info")

    def _check_gpu_and_warn(self):
        """Kiem tra GPU va hien canh bao neu cau hinh yeu."""
        try:
            import torch
            has_cuda = torch.cuda.is_available()

            if not has_cuda:
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
        size_kb = int(Path(out_path).stat().st_size / 1024) if Path(out_path).exists() else 0

        dlg = tk.Toplevel(self)
        dlg.title("✅ Hoàn thành!")
        dlg.geometry("420x200")
        dlg.configure(bg=P["white"])
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

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
            "device":       self.device_var.get(),
            "dtype":        self.dtype_var.get(),
            "steps":        self.steps_var.get(),
            "out_dir":      self.out_dir_var.get(),
            "fmt":          self.fmt_var.get(),
            "auto_load":    True,
            "model_cached": self.model_loaded or self._cfg.get("model_cached", False),
            "post_process": self.post_proc_var.get(),
            "narrator_mode": self.narrator_var.get(),
            "script_proc": self.script_proc_var.get(),
            "text_process": self.text_proc_var.get(),
            "sel_voice_idx": self.sel_idx,
            "sel_voice_name": self.lib.profiles[self.sel_idx].name
                              if self.sel_idx < len(self.lib.profiles) else "",
            **_name_cfg,
        })
        self.lib.save()  # Đảm bảo lưu voices trước khi đóng
        self.destroy()

    def _auto_load_model(self):
        """Tự động tải model khi khởi động (đã cache)."""
        self._log("🔄 Tự động tải model (đã cache sẵn)…", "info")
        self._load_model()

    # ─────── MODEL ─────────────────────────────────────────────────
    def _load_model(self):
        # Reset để cho phép tải lại
        Backend._model = None
        # Tự dùng HF mirror nếu chưa set
        if not os.environ.get("HF_ENDPOINT"):
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            self._log("🌐 Dùng mirror: hf-mirror.com", "info")
        self.load_btn.config(state="disabled", text="⏳ Đang tải…", bg=P["gold"])
        self.model_dot.config(fg=P["gold"])
        self.model_lbl.config(text=" Đang tải…", fg=P["gold"])
        self._log("⏳ Bắt đầu tải MagicVoice (~4GB lần đầu, đã cache = nhanh)…", "info")
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        try:
            import torch, traceback
            device   = self.device_var.get()
            dtype_str= self.dtype_var.get()
            self._log(f"   Device: {device}  |  Dtype: {dtype_str}", "info")

            # Kiem tra model da cache chua
            if not _model_is_cached():
                self._log("Model chua co - se tai tu HuggingFace...", "info")
                self._log("(Su dung mirror hf-mirror.com de tranh bi chan)", "info")
                self.after(0, lambda: self.model_lbl.config(
                    text=" Dang tai model...", fg=P["gold"]))

            from omnivoice import OmniVoice as MagicVoice
            dt = {"float32": torch.float32,
                  "float16": torch.float16,
                  "bfloat16": torch.bfloat16}[dtype_str]
            # Kiem tra mang truoc khi tai model
            online = self._is_online()

            if not online:
                # OFFLINE: Set env vars de tat moi ket noi HuggingFace
                import os as _os
                _os.environ["TRANSFORMERS_OFFLINE"] = "1"
                _os.environ["HF_DATASETS_OFFLINE"] = "1"
                _os.environ["HF_HUB_OFFLINE"] = "1"
                self._log("   Offline — Load model tu cache local...", "info")
            else:
                # ONLINE: Xoa flag offline neu da set truoc do
                import os as _os
                _os.environ.pop("TRANSFORMERS_OFFLINE", None)
                _os.environ.pop("HF_HUB_OFFLINE", None)
                self._log("   Dang tai model (cache o ~/.cache)...", "info")

            Backend._model = MagicVoice.from_pretrained(
                "k2-fsa/OmniVoice", device_map=device, dtype=dt)
            self.model_loaded = True
            self._log("✅ Model san sang!", "ok")
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
            import traceback
            detail = traceback.format_exc()
            self._log(f"❌ Lỗi: {e}", "err")
            self._log(detail[-600:], "err")
            self.after(0, self.model_dot.config, {"fg": P["red"]})
            self.after(0, self.model_lbl.config, {"text": " Lỗi tải", "fg": P["red"]})
            self.after(0, self.load_btn.config,
                       {"text": "↺ Thử lại", "bg": P["purple"], "state": "normal"})
            hint = ""
            s = str(e).lower()
            e_str = str(e)
            if "getaddrinfo" in s or any(x in s for x in ["connect","timeout","network","ssl","name resolution"]):
                hint = (
                    "Loi MANG!\n\n"
                    "App da tu dung hf-mirror.com.\n"
                    "Kiem tra internet roi nhan Thu lai."
                )
            elif any(x in e_str for x in ["caffe2_nvrtc", "WinError 126", "caffe2_nvrtc.dll"]) or \
                 ("winerror 126" in s and "dll" in s):
                hint = (
                    "Loi DLL: PyTorch CUDA khong tuong thich voi he thong nay!\n\n"
                    "Cach sua: Cai lai PyTorch phien ban CPU (khong can GPU):\n\n"
                    "  py -3.11 -m pip uninstall torch torchaudio -y\n"
                    "  py -3.11 -m pip install torch==2.8.0 torchaudio==2.8.0\n\n"
                    "Sau do mo lai app va nhan Thu lai."
                )
            elif any(x in s for x in ["omnivoice", "magicvoice", "no module"]):
                hint = (
                    "Thieu thu vien MagicVoice!\n\n"
                    "Chay CMD:\n"
                    "  py -3.11 -m pip install omnivoice\n\n"
                    "Sau do mo lai app."
                )
            elif "module" in s or "dll" in s or "winerror" in s:
                hint = (
                    f"Loi thu vien:\n{e_str[:200]}\n\n"
                    "Cach sua:\n"
                    "  py -3.11 -m pip uninstall torch torchaudio -y\n"
                    "  py -3.11 -m pip install torch==2.8.0 torchaudio==2.8.0\n"
                    "  py -3.11 -m pip install omnivoice\n\n"
                    "Sau do nhan Thu lai."
                )
            else:
                hint = f"Loi:\n{e_str[:300]}\n\nXem Log de biet chi tiet.\nNhan Thu lai."
            self.after(200, lambda h=hint: messagebox.showerror("Loi tai model", h))

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
            self._log("  ✓ Clone mode: chi dung ref_audio, OmniVoice tu xu ly text.", "info")
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
            MAX_SEC = 90   # Truoc: 30s -> qua ngan, mat phong cach giong
            t, sr = _safe_audio_load(audio_path)
            dur = t.shape[1] / sr
            # Khong cat neu trong gioi han -> giu nguyen chat luong clone
            if dur <= MAX_SEC:
                return audio_path
            # Cat khi qua dai (tranh OOM)
            max_samples = int(MAX_SEC * sr)
            t_trim = t[:, :max_samples]
            cache = str(_P(audio_path).with_suffix("")) + "_trim90s.wav"
            torchaudio.save(cache, t_trim, sr)
            self._log(f"  ✂ Trim ref audio: {dur:.1f}s → {MAX_SEC}s (qua dai)", "info")
            return cache
        except Exception:
            return audio_path

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
        """Lưu audio — post-process 1 lần."""
        import torch
        if hasattr(self, "post_proc_var") and self.post_proc_var.get():
            tensor = _post_process(tensor)
        else:
            peak = tensor.abs().max()
            if peak > 0.95:
                tensor = tensor * (0.891 / peak)
        if path.endswith(".mp3"):
            try:
                to_mp3(tensor, path)
                # Neu MP3 khong tao duoc → fallback WAV
                if not os.path.exists(path):
                    wav_path = path.replace(".mp3", ".wav")
                    to_wav(tensor, wav_path)
                    # Doi ten path thanh wav
                    import shutil as _sh
                    if os.path.exists(wav_path):
                        path = wav_path
            except Exception:
                wav_path = path.replace(".mp3", ".wav")
                to_wav(tensor, wav_path)
        else:                     to_wav(tensor, path)

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
            return True  # Khong co username → khong check (luc init)
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
            vname = vp.name if vp else "Auto"
            steps = self.steps_var.get()
            speed = self._get_speed()  # Uu tien speed tu voice profile
            SR    = 24000

            # ── Tách text thành chunks tối ưu ───────────────────────
            def make_chunks(text, max_chars=450):
                """Tách tại dấu câu, mỗi chunk ~max_chars ký tự.
                Đoạn văn (ngăn bởi dòng trống) → pause dài hơn giữa các đoạn.
                FIX: giam pause cho mat, sat voi Edge TTS hon."""
                final = []
                for para in text.split("\n\n"):
                    para = para.strip()
                    if not para: continue
                    sub = make_chunks_para(para, max_chars)
                    if sub:
                        final.extend(sub[:-1])
                        last_txt, _ = sub[-1]
                        # FIX: giam tu 800ms -> 500ms (sat Edge TTS 700ms - bao gom trim audio)
                        final.append((last_txt, 500))
                if final:
                    t, _ = final[-1]
                    final[-1] = (t, 0)
                return final

            def make_chunks_para(text, max_chars=450):
                sents = _re.split(r"(?<=[.!?])\s+", text.strip())
                result = []
                buf = ""
                for s in sents:
                    s = s.strip()
                    if not s: continue
                    if not buf:
                        buf = s
                    elif len(buf) + 1 + len(s) <= max_chars:
                        buf += " " + s
                    else:
                        last = buf.rstrip()[-1:]
                        # FIX: giam pause - sau dau cau .!? = 350ms (cu 600ms)
                        # sau dau , ; = 200ms (cu 300ms)
                        pause = 350 if last in ".!?" else 200
                        result.append((buf, pause))
                        buf = s
                if buf:
                    result.append((buf, 0))
                return result

            chunks = make_chunks(txt)
            if not chunks:
                chunks = [(txt.strip(), 0)]

            total = len(chunks)
            self._log(f"🎙 {vname} | Steps:{steps} | Speed:{speed:.1f}x | {total} chunks | {len(txt)} ký tự", "info")
            self.after(0, lambda: self.pb.configure(mode="determinate", value=0))

            # ── Đọc từng chunk & nối ────────────────────────────────
            parts = []
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
                a = Backend.gen(chunk_txt, num_step=steps, speed=speed, **kw)
                audio_t = _to_tensor(a)

                elapsed = time.time() - t0

                if audio_t is None or audio_t.abs().max() < 0.0001:
                    self._log(f"  [{ci+1}/{total}] ⚠ Audio rong - bo qua", "warn")
                    continue
                self._log(f"  [{ci+1}/{total}] {elapsed:.1f}s | {chunk_txt[:40]}", "info")

                # FIX: Trim silence dau/cuoi + DC offset + fade -> chong giat/pop khi noi
                # 1. Loai DC offset (cho moi chunk co the lech khac nhau)
                audio_t = audio_t - audio_t.mean()
                # 2. Trim silence dau/cuoi de loai khoang lang du thua
                #    (Edge TTS tu lam, MagicVoice phai lam thu cong)
                audio_t = _trim_silence(audio_t, sr=SR, threshold=0.005, pad_ms=30)
                # 3. Fade in/out 8ms de tranh click/pop o cho noi
                _fade_n = int(0.008 * SR)  # 8ms
                if audio_t.shape[1] > _fade_n * 2:
                    _fade = torch.linspace(0., 1., _fade_n)
                    audio_t[0, :_fade_n] *= _fade
                    audio_t[0, -_fade_n:] *= _fade.flip(0)
                parts.append(audio_t)
                # Thêm im lặng giữa các chunk
                if pause_ms > 0:
                    parts.append(torch.zeros(1, int(pause_ms * SR / 1000)))

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
            final = torch.cat(parts, dim=1)

            # Lưu - kiểm tra thư mục output tồn tại
            out_d = self.out_dir_var.get()
            try:
                os.makedirs(out_d, exist_ok=True)
            except Exception as _dir_err:
                raise RuntimeError(
                    f"Khong tao duoc thu muc luu:\n{out_d}\n\n"
                    f"Loi: {_dir_err}\n\n"
                    "Vui long chon thu muc khac trong phan Luu tai."
                )

            # MOI: dat ten theo cau hinh naming global
            import time as _time
            _base = vname.replace(" ", "_")
            # Fallback stem neu mode='keep': dung ten voice + timestamp (giong cu)
            _fallback = f"{_base}_{_time.strftime('%H%M%S')}"
            _fname = self._next_out_name_single(_fallback)
            # Hoi ten neu user bat tuy chon
            try:
                if self.out_ask_name_var.get():
                    _v = self._ask_output_filename(_fname, "Tab Văn Bản")
                    if _v and _v.strip():
                        _fname = _v.strip()
                    elif _v is None:
                        self._log("⏭ User hủy đặt tên - dùng mặc định", "warn")
            except Exception:
                pass
            path = self._out(name=_fname)
            self._save(final, path)

            if not os.path.exists(path):
                raise RuntimeError(
                    f"File da tao nhung khong tim thay:\n{path}\n\n"
                    "Kiem tra quyen ghi thu muc output."
                )

            total_t = int(time.time() - self._timer_start)
            self._st(f"✅ Xong! {total_t}s → {Path(path).name}", P["green"])
            self._log(f"✅ {path}", "ok")
            self.after(0, lambda: self.pb.configure(value=100))
            self.after(100, lambda p=path, t=total_t: self._done_notify(p, t))

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

            async def gen_edge(text, out_path, voice_id):
                """Gen Edge TTS voi retry 3 lan + verify file size.
                Return: True (OK) / False (loi khac) / 'fallback' (mat mang)."""
                import edge_tts, asyncio as _aio
                last_err = None
                for _attempt in range(3):
                    try:
                        # Xoa file cu neu co (tranh nham voi file cu)
                        try:
                            if os.path.exists(out_path):
                                os.remove(out_path)
                        except Exception:
                            pass
                        comm = edge_tts.Communicate(text, voice_id)
                        await comm.save(out_path)
                        # Verify: file phai ton tai va > 1KB (MP3 nho nhat ~500 bytes)
                        if not os.path.exists(out_path):
                            last_err = "file khong duoc tao"
                        else:
                            sz = os.path.getsize(out_path)
                            if sz < 500:
                                last_err = f"file rong/loi ({sz} bytes)"
                                try: os.remove(out_path)
                                except Exception: pass
                            else:
                                return True   # OK
                    except Exception as e:
                        last_err = str(e)
                        err_msg = str(e).lower()
                        # Neu la loi mang -> fallback luon, khong retry
                        if any(x in err_msg for x in ["network","connect","timeout","ssl","winerror","dns","resolve"]):
                            self._log(f"  ⚠ Edge TTS mat mang — chuyen sang MagicVoice Clone", "warn")
                            return "fallback"
                    # Sleep truoc khi retry
                    if _attempt < 2:
                        self._log(f"  ⚠ Edge TTS thu {_attempt+1}/3 fail ({str(last_err)[:60]}) — retry...", "warn")
                        await _aio.sleep(1.5 * (_attempt + 1))  # 1.5s, 3s
                # Het retry -> fail
                self._log(f"  ⚠ Edge TTS loi sau 3 lan retry: {last_err}", "warn")
                return False

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

                tmp_mp3 = f"{tmp_dir}/p{pi:04d}.mp3"
                t0 = time.time()

                # Chạy async trong sync context
                ok = asyncio.run(gen_edge(para_for_tts, tmp_mp3, voice))
                elapsed = time.time() - t0

                # Fallback: mat mang -> dung MagicVoice clone voice
                if ok == "fallback":
                    self._log(f"  🔄 [{pi+1}] Dung MagicVoice thay Edge TTS", "info")
                    try:
                        kw = self._get_voice_kwargs()
                        tensor = Backend.gen(para, **kw,
                                             num_step=self._cfg.get("steps",16),
                                             speed=self._get_speed())
                        parts.append(tensor)
                        parts.append(silence)
                    except Exception as fb_e:
                        self._log(f"  ✗ Fallback that bai: {fb_e}", "err")
                    continue

                if ok and Path(tmp_mp3).exists():
                    try:
                        tensor, sr = _safe_audio_load(tmp_mp3)
                        if sr != SR:
                            tensor = torchaudio.functional.resample(tensor, sr, SR)
                        if tensor.shape[0] > 1:
                            tensor = tensor.mean(dim=0, keepdim=True)
                        parts.append(tensor)
                        if pi < total - 1:
                            parts.append(silence)
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
                                if pi < total - 1:
                                    parts.append(silence)
                                self._log(f"  ✓ [{pi+1}] MagicVoice fallback OK", "info")
                        except Exception as _fbe:
                            self._log(f"  ✗ [{pi+1}] Fallback that bai: {_fbe}", "err")
                else:
                    self._log(f"  [{pi+1}/{total}] Lỗi — bỏ qua", "warn")

            if parts and not self.cancel_ev.is_set():
                final = torch.cat(parts, dim=1)
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
                else:
                    to_wav(final, path)
                total_t = int(time.time() - self._timer_start)
                self._st(f"✅ Edge TTS xong! {total_t}s → {Path(path).name}", P["green"])
                self._log(f"✅ {path}", "ok")
                self.after(0, lambda: self.pb.configure(value=100))
                self.after(100, lambda p=path, t=total_t: self._done_notify(p, t))

            # Dọn temp files
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

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

    def _refresh_srt_voices(self):
        """Cap nhat danh sach voice trong combobox SRT tab."""
        # Guard: widget chua duoc tao (goi qua som)
        if not hasattr(self, "srt_voice_cb") or not hasattr(self, "srt_voice_info"):
            return
        names = [vp.name for vp in self.lib.profiles]
        self.srt_voice_cb["values"] = names
        # Dong bo voi voice dang chon tren sidebar
        if 0 <= self.sel_idx < len(self.lib.profiles):
            cur = self.lib.profiles[self.sel_idx].name
            if cur in names:
                self.srt_voice_cb.set(cur)
                mode = self.lib.profiles[self.sel_idx].mode
                mode_icon = {"clone":"🎯","design":"✨","auto":"🎲","edge":"🌐"}.get(mode,"●")
                self.srt_voice_info.config(
                    text=f"{mode_icon} {mode.upper()}",
                    fg=P["purple"])
            elif names:
                self.srt_voice_cb.current(0)
        elif names:
            self.srt_voice_cb.current(0)

        def _on_change(e=None):
            if not hasattr(self, "srt_voice_info"): return
            name = self.srt_voice_var.get()
            for i, vp in enumerate(self.lib.profiles):
                if vp.name == name:
                    self.sel_idx = i
                    self._update_sidebar()
                    mode = vp.mode
                    mode_icon = {"clone":"🎯","design":"✨","auto":"🎲","edge":"🌐"}.get(mode,"●")
                    self.srt_voice_info.config(
                        text=f"{mode_icon} {mode.upper()}",
                        fg=P["purple"])
                    break
        self.srt_voice_cb.bind("<<ComboboxSelected>>", _on_change)

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
        # Neu chon Edge TTS mode → chay _run_srt_edge truc tiep
        if hasattr(self, "srt_tts_mode") and self.srt_tts_mode.get() == "edge":
            voice_id = self.srt_edge_voice_var.get() if hasattr(self, "srt_edge_voice_var") else "en-US-AriaNeural"
            class _FakeVP:
                mode = "edge"
                instruct = f"edge:{voice_id}"
                name = voice_id
            threading.Thread(target=self._run_srt_edge,
                             args=(self.srt_entries, _FakeVP()),
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
        # Tắt timeline mode để dùng sequential (không cần timestamp chính xác)
        self.srt_timeline_var.set(False)
        self._log(f"✅ Tạo {len(entries)} câu từ văn bản thường","ok")

    def _run_srt_edge(self, entries, vp):
        """Tao SRT bang Edge TTS - danh cho may cau hinh yeu, khong can GPU."""
        # MOI: kiem tra license truoc
        if not self._verify_license_or_abort():
            return
        import asyncio, tempfile, torch, torchaudio as _ta

        # Lay edge voice id
        voice_id = "en-US-AriaNeural"
        if vp.instruct and vp.instruct.startswith("edge:"):
            voice_id = vp.instruct.replace("edge:", "").strip()
        elif hasattr(self, "edge_voice_var"):
            voice_id = self.edge_voice_var.get()

        self._log(f"🌐 SRT Edge TTS | Voice: {voice_id}", "info")

        SR = 24000
        silence = torch.zeros(1, int(self.gap_var.get() * SR / 1000))
        tensors = []
        all_parts = []
        ok = fail = 0
        total = sum(1 for e in entries if e.text.strip())

        async def _gen_one(text, voice):
            """Gen Edge TTS cho 1 SRT entry voi retry 3 lan + verify file."""
            import edge_tts, asyncio as _aio, os as _os
            last_err = None
            for _attempt in range(3):
                tmp_mp3 = tempfile.mktemp(suffix=".mp3")
                try:
                    comm = edge_tts.Communicate(text, voice)
                    await comm.save(tmp_mp3)
                    # Verify file size > 500 bytes
                    if _os.path.exists(tmp_mp3):
                        sz = _os.path.getsize(tmp_mp3)
                        if sz >= 500:
                            return tmp_mp3   # OK
                        else:
                            last_err = f"file rong ({sz} bytes)"
                            try: _os.remove(tmp_mp3)
                            except Exception: pass
                    else:
                        last_err = "file khong duoc tao"
                except Exception as e:
                    last_err = str(e)
                # Retry voi delay tang dan
                if _attempt < 2:
                    await _aio.sleep(1.5 * (_attempt + 1))
            return None

        # MOI: dat ten output theo cau hinh naming global
        _fallback = f"SRT_{voice_id.replace('-','_')}"
        _name = self._next_out_name_single(_fallback)
        try:
            if self.out_ask_name_var.get():
                _v = self._ask_output_filename(_name, "Tab SRT (Edge TTS)")
                if _v and _v.strip(): _name = _v.strip()
        except Exception:
            pass
        out = self._out(name=_name)
        parts_dir = Path(out).parent / (Path(out).stem + "_parts")
        parts_dir.mkdir(parents=True, exist_ok=True)

        entry_num = 0
        for i, e in enumerate(entries):
            if self.cancel_ev.is_set(): break
            txt = e.text.strip()
            for ch in ["♪","♫","<i>","</i>","<b>","</b>"]:
                txt = txt.replace(ch, "")
            if not txt: continue

            entry_num += 1
            self._st(f"[{entry_num}/{total}] {txt[:50]}")
            self.after(0, lambda v=entry_num/total*100: self.pb.configure(value=v))

            try:
                # MOI: chen dau phay vao cau dai khong co dau de Edge TTS
                # ngat nghi tu nhien hon
                txt_for_tts = _edge_smart_pause(txt, max_words=8)

                tmp_mp3 = asyncio.run(_gen_one(txt_for_tts, voice_id))
                if not tmp_mp3 or not Path(tmp_mp3).exists():
                    raise RuntimeError("Edge TTS khong tao duoc audio")
                t, sr = _safe_audio_load(tmp_mp3)
                try: Path(tmp_mp3).unlink()
                except: pass
                if sr != SR:
                    t = _ta.functional.resample(t, sr, SR)
                if t.shape[0] > 1:
                    t = t.mean(dim=0, keepdim=True)
                # Luu part
                _part_mp3 = str(parts_dir / f"{entry_num:03d}.mp3")
                to_mp3(t, _part_mp3)
                all_parts.append(_part_mp3)
                tensors.append(t)
                tensors.append(silence)
                ok += 1
                self._log(f"  [{entry_num}/{total}] ✓ {txt[:50]}", "info")
            except Exception as ex:
                fail += 1
                self._log(f"  [{entry_num}] ❌ {ex}", "err")

        if tensors and not self.cancel_ev.is_set():
            self._log(f"🔗 Ghep {ok} doan...", "info")
            final = torch.cat(tensors, dim=1)
            self._save(final, out)
            self._log(f"✅ Full: {out}", "ok")
            self._log(f"📁 Parts ({len(all_parts)} files): {parts_dir.name}/", "ok")
            self._st(f"✅ Xong! {ok} cau → {Path(out).name}", P["green"])
            self.after(0, lambda: self.pb.configure(value=100))
            self._srt_notify_shown = False  # Reset de lan sau van hien popup
        self.after(100, lambda o=out, d=str(parts_dir): self._done_notify_srt(o, d))

        self._busy(False)

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
        entries   = self.srt_entries
        total     = len(entries)
        tmp       = Path(tempfile.mkdtemp(prefix="ov_srt_"))
        SR        = 24000
        use_tl    = self.srt_timeline_var.get()

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

        try:
            if use_tl:
                # ══ Timeline mode: ffmpeg adelay ═══════════════════════════
                self._log("📐 Timeline mode (ffmpeg adelay) — chính xác tuyệt đối", "info")
                ok = fail = skip = 0
                seg_files = []   # [(start_ms, wav_path)]

                for i, e in enumerate(entries):
                    if self.cancel_ev.is_set(): break

                    # Làm sạch text
                    txt = e.text.strip()
                    for ch in ["♪","♫","♩","♬","<i>","</i>","<b>","</b>","<u>","</u>"]:
                        txt = txt.replace(ch, "")
                    import re as _re
                    txt = _re.sub(r"<[^>]+>", "", txt).strip()

                    if not txt or len(txt) < 2:
                        skip += 1
                        self._log(f"  [{i+1}] ⏭ Bỏ qua (rỗng)", "warn")
                        continue

                    dur_ms = e.end_ms - e.start_ms
                    if dur_ms < 100:
                        skip += 1
                        self._log(f"  [{i+1}] ⏭ Bỏ qua (slot {dur_ms}ms quá ngắn)", "warn")
                        continue

                    pct = i / total * 100
                    self.after(0, lambda v=pct: self.pb.configure(value=v))
                    self._st(f"[{i+1}/{total}] {txt[:45]}…")

                    try:
                        # FIX: Giam MAX_CH tu 300 -> 150 vi cau dai gay F5/OmniVoice
                        # bo doan giua (vi du: "swollen shut, blood dried along her jaw,
                        # and one shoe..." -> bi bo cum giua). 150 chars la nguong
                        # an toan: cau dai duoc chia thanh 2-3 chunk, model xu ly tung
                        # chunk ngan -> khong bo doan, ten rieng van trong cum lien tiep.
                        MAX_CH = 150
                        import re as _re2
                        if len(txt) <= MAX_CH:
                            chunks = [txt]
                        else:
                            # Split at punctuation boundaries
                            raw = _re2.split(r"(?<=[,،،.!?;])\s+", txt)
                            chunks, buf = [], ""
                            for s in raw:
                                if not s.strip(): continue
                                if not buf:
                                    buf = s
                                elif len(buf) + 1 + len(s) <= MAX_CH:
                                    buf += " " + s
                                else:
                                    chunks.append(buf); buf = s
                            if buf: chunks.append(buf)
                            if not chunks: chunks = [txt]

                        # FIX: Timeline mode -> gen voi speed adapt theo slot duration
                        # de audio output VUA voi timestamp SRT (khong dai hon).
                        # Buoc 1: gen thu voi speed mac dinh
                        # Buoc 2: neu audio dai hon slot -> gen lai voi speed cao hon
                        # Cap speed o 1.4 de tranh meo giong qua nhuc
                        import torch as _tc3
                        base_speed = self._get_speed()
                        slot_sec   = dur_ms / 1000.0

                        def _gen_chunks(spd):
                            tensors = []
                            for chunk in chunks:
                                a = Backend.gen(chunk,
                                    num_step=self.steps_var.get(),
                                    speed=spd, **kw)
                                t = _to_tensor(a)
                                if hasattr(self,"post_proc_var") and self.post_proc_var.get():
                                    t = _post_process(t, SR)
                                tensors.append(t)
                            return tensors

                        # Lan 1: gen voi speed binh thuong
                        entry_tensors = _gen_chunks(base_speed)
                        total_samples = sum(t.shape[1] for t in entry_tensors)
                        actual_sec = total_samples / SR

                        # Neu audio dai hon slot -> tinh speed moi va gen lai
                        if use_tl and actual_sec > slot_sec * 1.05:  # 5% tolerance
                            ratio = actual_sec / slot_sec
                            new_speed = min(base_speed * ratio, 1.4)  # cap 1.4
                            if new_speed > base_speed * 1.02:  # chi gen lai neu speed thay doi >2%
                                self._log(
                                    f"  [{i+1}] ⚡ audio {actual_sec:.1f}s > slot {slot_sec:.1f}s "
                                    f"-> gen lai speed {new_speed:.2f}", "info")
                                entry_tensors = _gen_chunks(new_speed)

                        # Ghep tat ca chunks cua entry nay → 1 wav file
                        if len(entry_tensors) > 1:
                            entry_audio = _tc3.cat(entry_tensors, dim=1)
                        else:
                            entry_audio = entry_tensors[0]

                        wp = str(tmp / f"seg_{i:04d}.wav")
                        torchaudio.save(wp, entry_audio, SR)
                        seg_files.append((e.start_ms, wp))

                        ok += 1
                        self._log(f"  [{i+1}/{total}] ✓ {len(chunks)} chunks @ {e.start}", "info")

                    except Exception as ex:
                        import traceback
                        fail += 1
                        self._log(f"  [{i+1}] ❌ {ex} | {txt[:40]}", "err")
                        self._log(traceback.format_exc()[-200:], "err")

                self._log(f"📊 ✓{ok} câu | ❌{fail} lỗi | ⏭{skip} bỏ qua", "info")

                if not self.cancel_ev.is_set() and seg_files:
                    # MOI: dat ten output theo naming global
                    _name = self._next_out_name_single("SRT_timeline")
                    try:
                        if self.out_ask_name_var.get():
                            _v = self._ask_output_filename(_name, "Tab SRT (Timeline mode)")
                            if _v and _v.strip(): _name = _v.strip()
                    except Exception:
                        pass
                    out = self._out(name=_name)
                    # Tao thu muc _parts CUNG CAP VOI file output
                    parts_dir = Path(out).parent / (Path(out).stem + "_parts")
                    parts_dir.mkdir(parents=True, exist_ok=True)

                    # Luu tung part MP3 theo so thu tu SRT
                    self._log(f"💾 Lưu {len(seg_files)} file lẻ → {parts_dir.name}/", "info")
                    saved_parts = []
                    for _pi, (_ms, _wav) in enumerate(seg_files):
                        _part_mp3 = str(parts_dir / f"{_pi+1:03d}.mp3")
                        try:
                            _pt, _psr = _safe_audio_load(_wav)
                            to_mp3(_pt, _part_mp3)
                            saved_parts.append(_part_mp3)
                        except Exception as _pe:
                            self._log(f"  ⚠ Part {_pi+1}: {_pe}", "warn")
                    self._log(f"✅ {len(saved_parts)} file lẻ → {parts_dir.name}/", "ok")

                    # Ghép hoàn chỉnh
                    self._log(f"🔗 Ghép {len(seg_files)} đoạn bằng ffmpeg adelay…", "info")
                    self._ffmpeg_timeline(seg_files, out, SR)
                    self._st(f"✅ Xong! {ok} câu → {Path(out).name}", P["green"])
                    self._log(f"✅ Full: {out}", "ok")
                    self._log(f"📁 Parts: {parts_dir}", "ok")
                    self.after(0, lambda: self.pb.configure(value=100))
                    self.after(100, lambda o=out, d=str(parts_dir): self._done_notify_srt(o, d))

            else:
                # ══ Sequential mode: ghép tuần tự ═══════════════════════
                self._log("🔗 Sequential mode — ghép tuần tự", "info")
                import torch
                tensors   = []   # chi audio, khong silence
                silence   = torch.zeros(1, int(self.gap_var.get() * SR / 1000))
                all_parts = []   # list tensor audio rieng le
                ok = fail = 0

                entry_num = 0  # dem so entry SRT thuc su (co text)
                for i, e in enumerate(entries):
                    if self.cancel_ev.is_set(): break
                    txt = e.text.strip()
                    for ch in ["♪","♫","<i>","</i>","<b>","</b>"]:
                        txt = txt.replace(ch, "")
                    if not txt: continue

                    entry_num += 1
                    self._st(f"[{entry_num}/{total}] {txt[:50]}")
                    self.after(0, lambda v=i/total*100: self.pb.configure(value=v))
                    try:
                        # Gen truc tiep - 1 SRT entry = 1 lan gen = 1 file part
                        a = Backend.gen(txt,
                                        num_step=self.steps_var.get(),
                                        speed=self._get_speed(), **kw)
                        audio_t = _to_tensor(a)
                        all_parts.append(audio_t)  # 1 entry = 1 part
                        tensors.append(audio_t)
                        tensors.append(silence)
                        ok += 1
                        self._log(f"  [{entry_num}/{total}] ✓ {txt[:50]}", "info")
                    except Exception as ex:
                        fail += 1
                        self._log(f"  [{entry_num}] ❌ {ex}", "err")

                if tensors and not self.cancel_ev.is_set():
                    # MOI: dat ten output theo naming global
                    _name = self._next_out_name_single("SRT_sequential")
                    try:
                        if self.out_ask_name_var.get():
                            _v = self._ask_output_filename(_name, "Tab SRT (Sequential mode)")
                            if _v and _v.strip(): _name = _v.strip()
                    except Exception:
                        pass
                    out = self._out(name=_name)
                    parts_dir = Path(out).parent / (Path(out).stem + "_parts")
                    parts_dir.mkdir(parents=True, exist_ok=True)

                    # Luu tung part MP3
                    self._log(f"💾 Đang lưu {len(all_parts)} file lẻ → {parts_dir.name}/", "info")
                    saved_ok = 0
                    for _pi, _t in enumerate(all_parts):
                        _part_path = str(parts_dir / f"{_pi+1:03d}.mp3")
                        try:
                            _out_t = _t.unsqueeze(0) if _t.dim()==1 else _t
                            to_mp3(_out_t, _part_path)
                            saved_ok += 1
                        except Exception as _pe:
                            self._log(f"  ⚠ Part {_pi+1}: {_pe}", "warn")
                    self._log(f"✅ {saved_ok}/{len(all_parts)} file lẻ → {parts_dir.name}/", "ok")

                    # Ghep hoan chinh
                    final = torch.cat(tensors, dim=1)
                    if hasattr(self,"post_proc_var") and self.post_proc_var.get():
                        final = _post_process(final, SR)
                    self._save(final, out)
                    self._st(f"✅ Xong! {ok} câu → {Path(out).name}", P["green"])
                    self._log(f"✅ Full: {out}", "ok")
                    self._log(f"📁 Parts: {parts_dir}", "ok")
                    self.after(0, lambda: self.pb.configure(value=100))
                    self._srt_notify_shown = False  # Reset de lan sau van hien popup
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
            shutil.rmtree(tmp, ignore_errors=True)
            self._busy(False)

    def _ffmpeg_timeline(self, seg_files: list, out: str, sr: int = 24000):
        """
        Ghép audio theo timeline SRT bằng PyTorch trong RAM.
        Audio cua moi entry da duoc gen voi speed adapt vua slot,
        nen o day chi can dat dung start_ms - khong overlap nua.
        """
        import torch, torchaudio

        if not seg_files:
            return

        self._log(f"⚡ Ghép {len(seg_files)} đoạn theo timeline…", "info")
        t0 = time.time()

        # Tinh tong do dai buffer can thiet
        max_end_sample = 0
        loaded = []
        for start_ms, wav_path in seg_files:
            try:
                tensor, file_sr = _safe_audio_load(wav_path)
                if file_sr != sr:
                    tensor = torchaudio.functional.resample(tensor, file_sr, sr)
                if tensor.shape[0] > 1:
                    tensor = tensor.mean(dim=0, keepdim=True)
                start_sample = int(start_ms * sr / 1000)
                end_sample   = start_sample + tensor.shape[1]
                max_end_sample = max(max_end_sample, end_sample)
                loaded.append((start_sample, tensor))
            except Exception as e:
                self._log(f"  ⚠ Bỏ qua: {e}", "warn")

        if not loaded:
            return

        total_samples = max_end_sample + int(0.5 * sr)
        buffer = torch.zeros(1, total_samples)

        # Mix (cong) thay vi gan "=" de neu co overlap nho thi 2 audio chong nhau
        # khong cat audio truoc. Voi speed adapt o tren, overlap se rat hiem.
        for start_sample, tensor in loaded:
            end_sample = min(start_sample + tensor.shape[1], total_samples)
            copy_len   = end_sample - start_sample
            if copy_len > 0:
                buffer[0, start_sample:end_sample] += tensor[0, :copy_len]

        # Normalize neu peak qua 0.95 (do mix co the lam tang amplitude)
        peak = buffer.abs().max()
        if peak > 0.95:
            buffer = buffer * (0.891 / peak)

        if out.endswith(".mp3"):
            to_mp3(buffer, out)
        else:
            to_wav(buffer, out)

        elapsed = time.time() - t0
        self._log(f"  ✓ Ghép xong trong {elapsed:.1f}s", "ok")

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
        Neu mode='keep'  -> dung src_stem."""
        try:
            mode = self.out_name_mode.get()
        except Exception:
            mode = "prefix"
        if mode == "keep":
            return (src_stem or "output").strip() or "output"
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

    def _batch_gen_srt_file(self, srt_path: str, kw: dict):
        """Sinh audio tu 1 file .srt: parse -> gen tung entry -> concat.
        Tra ve (final_tensor, entry_tensors) hoac (None, None) neu rong/huy.
          final_tensor: tensor da noi + silence giua cac entry
          entry_tensors: list[tensor] tung entry rieng le -> de luu _parts/
        Khong post-process (se lam trong _save)."""
        import torch
        try:
            raw = Path(srt_path).read_text("utf-8").strip()
        except Exception:
            raw = Path(srt_path).read_text("utf-8", errors="ignore").strip()
        if not raw: return None, None
        entries = parse_srt(raw)
        if not entries:
            # Fallback: coi nhu van ban thuong, tach theo dau cau
            return None, None

        SR    = 24000
        gap   = int(self.gap_var.get())
        steps = self.steps_var.get()
        speed = self._get_speed()
        silence = torch.zeros(1, int(gap * SR / 1000))

        tensors = []        # de ghep final (co silence giua)
        entry_tensors = []  # tung entry rieng -> luu _parts/
        ok = skip = 0
        total_e = len(entries)
        for j, e in enumerate(entries):
            if self.cancel_ev.is_set(): return None, None
            txt = e.text.strip()
            # Lam sach nhac cu / tag HTML
            import re as _re
            for ch in ["♪","♫","♩","♬"]:
                txt = txt.replace(ch, "")
            txt = _re.sub(r"<[^>]+>", "", txt).strip()
            if not txt or len(txt) < 2:
                skip += 1
                continue
            try:
                a = Backend.gen(txt, num_step=steps, speed=speed, **kw)
                t = _to_tensor(a)
                if t is None or t.abs().max() < 0.0001:
                    skip += 1; continue
                # Luu vao ca 2 list
                tensors.append(t)
                entry_tensors.append(t)   # MOI: luu rieng cho _parts
                if j < total_e - 1:
                    tensors.append(silence)
                ok += 1
            except Exception as _ge:
                self._log(f"    ⚠ entry {j+1}: {_ge}", "warn")
                skip += 1
        if not tensors:
            return None, None
        self._log(f"    🎞 {ok} entry OK, {skip} bỏ qua → ghép", "info")
        return torch.cat(tensors, dim=1), entry_tensors

    def _run_batch(self):
        # MOI: kiem tra license truoc
        if not self._verify_license_or_abort():
            self._running_tab = None
            self.is_running = False
            self.after(0, self._refresh_tab_indicators)
            return
        self._busy(True); self.cancel_ev.clear()
        total=len(self._txt_files); ok=fail=skipped=0
        ask_name  = False
        try:
            ask_name = bool(self.out_ask_name_var.get())   # MOI: global
        except Exception:
            pass

        # Chuan bi index cho mode tien to: chi dem file TXT+SRT hop le
        try:
            kw=self._vkw()
        except Exception as _kw_err:
            self._log(f"❌ Lỗi voice: {_kw_err}", "err")
            self._busy(False)
            self._running_tab = None
            return

        fmt = self.fmt_var.get()
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

                # Tinh ten output (dung helper global)
                default_name = self._compute_output_name(stem, i)
                if ask_name:
                    v = self._ask_output_filename(default_name, Path(fp).name)
                    if v is None or v.strip() == "":
                        self._log(f"  ⏭ Bỏ qua (user không đặt tên)", "warn")
                        skipped += 1; continue
                    default_name = v.strip()

                try:
                    tensor = None
                    entry_tensors = None   # MOI: cho SRT - list tensor tung entry
                    if ext == ".srt":
                        tensor, entry_tensors = self._batch_gen_srt_file(fp, kw)
                        if tensor is None:
                            self._log("  ⚠ SRT rỗng hoặc không parse được", "warn")
                            fail += 1; continue
                    else:
                        # .txt (hoac extension la - doc nhu text thuong)
                        txt=Path(fp).read_text("utf-8", errors="ignore").strip()
                        if not txt:
                            self._log("  ⚠ File trống", "warn")
                            skipped += 1; continue
                        a=Backend.gen(preprocess_text(txt),num_step=self.steps_var.get(),
                                       speed=self._get_speed(),**kw)
                        tensor = _to_tensor(a)

                    if tensor is None or tensor.abs().max() < 0.0001:
                        self._log("  ⚠ Audio rỗng", "warn")
                        fail += 1; continue

                    out=self._out(name=default_name, ext=fmt)
                    self._save(tensor, out)
                    self._log(f"  ✅ → {Path(out).name}","ok"); ok+=1

                    # MOI: luu _parts/ cho file SRT (giong tab SRT don le)
                    if ext == ".srt" and entry_tensors:
                        try:
                            parts_dir = Path(out).parent / (Path(out).stem + "_parts")
                            parts_dir.mkdir(parents=True, exist_ok=True)
                            saved_parts = 0
                            for _pi, _et in enumerate(entry_tensors):
                                _part_mp3 = str(parts_dir / f"{_pi+1:03d}.mp3")
                                try:
                                    _out_t = _et.unsqueeze(0) if _et.dim()==1 else _et
                                    to_mp3(_out_t, _part_mp3)
                                    saved_parts += 1
                                except Exception as _pe:
                                    self._log(f"    ⚠ Part {_pi+1}: {_pe}", "warn")
                            self._log(
                                f"  📁 {saved_parts}/{len(entry_tensors)} file lẻ → {parts_dir.name}/",
                                "ok")
                        except Exception as _dir_err:
                            self._log(f"  ⚠ Không tạo được thư mục parts: {_dir_err}", "warn")
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
            self._running_tab = None
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
        """Phat hien entry qua dai → hoi user co muon split khong."""
        if not self.srt_entries: return
        # Nguong: 15 ky tu / giay la binh thuong
        # Entry qua dai neu: len(text) > duration_s * 15
        CHARS_PER_SEC = 15
        too_long = []
        for e in self.srt_entries:
            dur_s = (e.end_ms - e.start_ms) / 1000
            if dur_s > 0 and len(e.text) > dur_s * CHARS_PER_SEC * 1.3:
                too_long.append(e)

        if not too_long: 
            self._refresh_srt_preview()
            return

        # Hoi user
        msg = (f"Phát hiện {len(too_long)} entry text quá dài so với thời gian:\n\n")
        for e in too_long[:3]:
            dur_s = (e.end_ms - e.start_ms) / 1000
            msg += f"  Entry {e.index}: {len(e.text)} ký tự / {dur_s:.1f}s\n"
        if len(too_long) > 3:
            msg += f"  ... và {len(too_long)-3} entry khác\n"
        msg += "\nTự động split entry quá dài cho chuẩn không?"

        ans = messagebox.askyesno("⚠ SRT Entry Quá Dài", msg, parent=self)
        if ans:
            self._auto_split_srt(too_long)
        else:
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

        # Progress bar — mỏng, màu xanh
        s.configure("TProgressbar",
                    troughcolor=P["border"],
                    background=P["purple"],
                    thickness=6,
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

if __name__ == "__main__":
    # ── Cai tu dong firebase-admin va omnivoice TRUOC khi chay ────
    # FIX v3.20: Chi check & cai khi LAN DAU (track qua flag file).
    # Nhung lan sau, neu thieu module thi import se loi -> bao user.
    # Tranh moi lan startup phai dot 1-2s check dependency.
    import sys as _sys_pre, subprocess as _sp_pre, os as _os_pre
    from pathlib import Path as _Path_pre

    _flag_file = _Path_pre(__file__).parent / ".deps_installed"
    if not _flag_file.exists():
        _flags_pre = 0x08000000 if _os_pre.name == "nt" else 0
        _all_ok = True
        for _mod_pre, _pkg_pre in [("firebase_admin", "firebase-admin"), ("omnivoice", "omnivoice")]:
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
        if _all_ok:
            try: _flag_file.write_text("ok")
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
            return "","",False
        def _save(u,p): 
            try: _cache.write_text(_json.dumps({"username":u,"password":p,"remember":True}),"utf-8")
            except: pass
        def _clear():
            try:
                if _cache.exists(): _cache.unlink()
            except: pass

        su, sp, sr = _load()
        ok = [False, ""]

        win = _tk.Tk()
        win.title("MagicVoice TTS Studio")
        win.geometry("440x580")
        win.configure(bg="#0f1117")
        win.resizable(False,False)
        win.update_idletasks()
        x = (win.winfo_screenwidth()-440)//2
        y = (win.winfo_screenheight()-580)//2
        win.geometry(f"440x580+{x}+{y}")
        try:
            ico = _P(__file__).parent / "MagicVoice.ico"
            if ico.exists():
                ico_str = str(ico)
                win.iconbitmap(default=ico_str)
                win.after(0, lambda: win.iconbitmap(default=ico_str))
        except: pass

        c = _tk.Canvas(win,width=440,height=580,bg="#0f1117",highlightthickness=0)
        c.pack(fill="both",expand=True)
        c.create_oval(-60,-60,200,200,fill="#1a1040",outline="")
        c.create_oval(280,-40,520,200,fill="#0d1535",outline="")
        c.create_text(220,70,text="MV",font=("Segoe UI",36,"bold"),fill="#6c63ff")
        c.create_text(220,118,text="MagicVoice TTS Studio",font=("Segoe UI",14,"bold"),fill="#e8eaf6")
        c.create_text(220,142,text="Dang nhap de su dung",font=("Segoe UI",9),fill="#6b7280")
        c.create_line(60,165,380,165,fill="#2d3154",width=1)

        frm = _tk.Frame(c,bg="#1a1d2e")
        c.create_window(220,285,window=frm,width=360,height=230)

        _tk.Label(frm,text="Ten tai khoan",font=("Segoe UI",8,"bold"),bg="#1a1d2e",fg="#9094b8",anchor="w").pack(fill="x",padx=20,pady=(16,2))
        uv = _tk.StringVar(value=su)
        uf = _tk.Frame(frm,bg="#252845",highlightthickness=1,highlightbackground="#2d3154")
        uf.pack(fill="x",padx=20)
        _tk.Label(uf,text="👤",bg="#252845",fg="#6b7280").pack(side="left",padx=8)
        ue = _tk.Entry(uf,textvariable=uv,font=("Segoe UI",11),bg="#252845",fg="#e8eaf6",insertbackground="#6c63ff",relief="flat",bd=0)
        ue.pack(side="left",fill="x",expand=True,ipady=10,pady=2)

        _tk.Label(frm,text="Mat khau",font=("Segoe UI",8,"bold"),bg="#1a1d2e",fg="#9094b8",anchor="w").pack(fill="x",padx=20,pady=(10,2))
        pv = _tk.StringVar(value=sp)
        pf = _tk.Frame(frm,bg="#252845",highlightthickness=1,highlightbackground="#2d3154")
        pf.pack(fill="x",padx=20)
        _tk.Label(pf,text="🔒",bg="#252845",fg="#6b7280").pack(side="left",padx=8)
        pe = _tk.Entry(pf,textvariable=pv,show="*",font=("Segoe UI",11),bg="#252845",fg="#e8eaf6",insertbackground="#6c63ff",relief="flat",bd=0)
        pe.pack(side="left",fill="x",expand=True,ipady=10,pady=2)

        rv = _tk.BooleanVar(value=sr)
        rf = _tk.Frame(frm,bg="#1a1d2e")
        rf.pack(fill="x",padx=20,pady=(8,0))
        _tk.Checkbutton(rf,text="Ghi nho tai khoan",variable=rv,font=("Segoe UI",9),bg="#1a1d2e",fg="#9094b8",activebackground="#1a1d2e",selectcolor="#252845",cursor="hand2").pack(side="left")

        mv = _tk.StringVar()
        ml = _tk.Label(c,textvariable=mv,font=("Segoe UI",9),bg="#0f1117",fg="#ef4444",wraplength=360)
        c.create_window(220,430,window=ml)

        def login(e=None):
            u=uv.get().strip(); p=pv.get().strip()
            if not u or not p: mv.set("Nhap day du thong tin!"); return
            btn.config(text="Dang kiem tra...",state="disabled",bg="#3d3888")
            mv.set(""); win.update()
            try:
                from auth_manager import verify_login, verify_login_offline
                import socket as _sock

                # Kiem tra co mang khong
                def _has_internet():
                    try:
                        _sock.setdefaulttimeout(1)  # 1s: fail nhanh, giai phong lock som
                        _sock.socket().connect(("8.8.8.8", 53))
                        return True
                    except: return False

                if _has_internet():
                    r, m = verify_login(u, p)
                    is_offline = False
                else:
                    # Mat mang - dung cache offline
                    r, m = verify_login_offline(u, p)
                    is_offline = True

                if r:
                    ok[0] = True
                    ok[1] = m
                    if rv.get(): _save(u,p)
                    else: _clear()
                    btn.config(text="Thanh cong!", bg="#00d68f")
                    mv.set(m); ml.config(fg="#00d68f")
                    win.after(700, win.quit)
                else:
                    # Neu online that bai thi thu offline
                    if not is_offline:
                        r2, m2 = verify_login_offline(u, p)
                        if r2:
                            ok[0] = True
                            ok[1] = m2
                            if rv.get(): _save(u,p)
                            else: _clear()
                            btn.config(text="Thanh cong!", bg="#00d68f")
                            mv.set(m2); ml.config(fg="#00d68f")
                            win.after(700, win.quit)
                            return
                    btn.config(text="Dang Nhap", state="normal", bg="#6c63ff")
                    mv.set(m); ml.config(fg="#ef4444")
            except Exception as _ex:
                btn.config(text="Dang Nhap", state="normal", bg="#6c63ff")
                mv.set("Loi ket noi! " + str(_ex)[:60]); ml.config(fg="#ef4444")

        btn = _tk.Button(c,text="Dang Nhap",command=login,font=("Segoe UI",12,"bold"),bg="#6c63ff",fg="white",relief="flat",cursor="hand2",activebackground="#8b85ff")
        c.create_window(220,405,window=btn,width=360,height=44)

        c.create_line(60,460,380,460,fill="#1e2135",width=1)
        c.create_text(220,478,text="Lien he - Zalo: 0985 483 623",font=("Segoe UI",9,"bold"),fill="#00b4d8")
        def zalo():
            import webbrowser; webbrowser.open("https://zalo.me/g/bqroiqc6wbcpph3s6sdd")
        bz = _tk.Button(c,text="📲  Tham Gia Nhom Zalo",command=zalo,font=("Segoe UI",9,"bold"),bg="#0068ff",fg="white",relief="flat",cursor="hand2")
        c.create_window(220,510,window=bz,width=240,height=32)

        c.create_text(220,548,text="🎁 Dung thu? Lien he Zalo de duoc ho tro",font=("Segoe UI",8),fill="#6b7280")

        win.protocol("WM_DELETE_WINDOW",win.destroy)
        win.bind("<Return>",login)
        if sr and su: pe.focus_set()
        else: ue.focus_set()

        win.mainloop()
        try: win.destroy()
        except: pass
        return ok[0], ok[1]

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
                    proc = _ps.Process(pid)
                    # Kiem tra ten process co phai Python/MagicVoice khong
                    if proc.is_running() and proc.status() != _ps.STATUS_ZOMBIE:
                        name = proc.name().lower()
                        if "python" in name or "magicvoice" in name:
                            is_running = True
                except Exception:
                    # psutil loi hoac process khong ton tai → xoa lock cu
                    try: _os.remove(_lock_file)
                    except: pass

                if is_running:
                    import tkinter as _tk2
                    _r = _tk2.Tk(); _r.withdraw()
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
    logged_in, login_msg = _show_login()
    if not logged_in:
        _sys.exit(0)
    # Lay username tu login_msg hoac cache
    try:
        import json as _jj, base64 as _b64
        _cache = _Path(__file__).parent / ".login_cache"
        _d = _jj.loads(_b64.b64decode(_cache.read_text()).decode())
        _last_username = _d.get("u", "")
    except Exception:
        _last_username = ""

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
