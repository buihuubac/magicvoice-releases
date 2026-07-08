# -*- coding: utf-8 -*-
"""
Module xử lý ghép video khớp voice — dùng chung cho GhepVideoVoice app và MagicVoice tab.
Không chứa GUI (thuần logic + ffmpeg).
"""
import os
import re
import glob
import json
import shutil
import zipfile
import subprocess
import urllib.request

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif")
MEDIA_EXTS = VIDEO_EXTS + IMAGE_EXTS
VOICE_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")

ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-threads", "1",   # prevents x264 assertion: mv_max_spel || i_thread_frames==1
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-pix_fmt", "yuv420p"]

ENC_GPU = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-pix_fmt", "yuv420p"]

TARGET_FPS    = 30
SPEED_PTS_MIN = 0.80
SPEED_PTS_MAX = 1.25

# Danh sách xfade transitions ngẫu nhiên
_XFADE_TRANS = [
    "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circleopen", "circleclose", "dissolve",
    "diagtl", "diagtr", "diagbl", "diagbr",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
]

RESOLUTIONS = {
    "Ngang 1920×1080 (Full HD)":        (1920, 1080),
    "Dọc 1080×1920 (Shorts / TikTok)":  (1080, 1920),
    "Ngang 1280×720 (HD)":              (1280, 720),
    "Giữ nguyên gốc":                   (None, None),
}

_APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "GhepVideoVoiceApp", "ffmpeg",
)
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

FFMPEG_EXE  = "ffmpeg"
FFPROBE_EXE = "ffprobe"


# ─────────────────────────── utils ───────────────────────────

def no_window_kwargs():
    kw = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if os.name == "nt":
        import subprocess as _sp
        si = _sp.STARTUPINFO()
        si.dwFlags |= _sp.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kw


_has_nvenc = None  # None = chưa kiểm tra; True/False sau lần đầu gọi _check_nvenc()


def _check_nvenc():
    """Kiểm tra NVENC (NVIDIA GPU encode) có khả dụng không. Cache kết quả."""
    global _has_nvenc
    if _has_nvenc is not None:
        return _has_nvenc
    try:
        cmd = [FFMPEG_EXE, "-y", "-f", "lavfi", "-i", "color=black:s=128x128:d=0.1",
               "-c:v", "h264_nvenc", "-f", "null", "-"]
        r = subprocess.run(cmd, timeout=10, **no_window_kwargs())
        _has_nvenc = (r.returncode == 0)
    except Exception:
        _has_nvenc = False
    return _has_nvenc


def _enc():
    """Encoding args: NVENC (GPU) nếu khả dụng, libx264 (CPU) nếu không."""
    return ENC_GPU if _check_nvenc() else ENC


def natural_key(path):
    name = os.path.basename(path)
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_media(folder, exts):
    files = [f for f in glob.glob(os.path.join(folder, "*"))
             if f.lower().endswith(exts)]
    return sorted(files, key=natural_key)


def list_media_video_priority(folder):
    """
    List tất cả media trong folder, tự động ưu tiên video hơn ảnh khi cùng tên cơ sở.
    Ví dụ: có 1.mp4 và 1.jpg → dùng 1.mp4, bỏ 1.jpg.
    Trả (files_list, n_replaced): n_replaced = số ảnh bị thay bằng video cùng tên.
    """
    all_files = [f for f in glob.glob(os.path.join(folder, "*"))
                 if f.lower().endswith(MEDIA_EXTS)]
    by_stem = {}
    for f in all_files:
        stem = os.path.splitext(os.path.basename(f))[0].lower()
        bk = by_stem.setdefault(stem, {"v": [], "i": []})
        (bk["v"] if f.lower().endswith(VIDEO_EXTS) else bk["i"]).append(f)

    result = []
    n_replaced = 0
    for bk in by_stem.values():
        if bk["v"]:
            result.append(sorted(bk["v"], key=natural_key)[0])
            if bk["i"]:
                n_replaced += 1
        else:
            result.append(sorted(bk["i"], key=natural_key)[0])

    return sorted(result, key=natural_key), n_replaced


def is_image(path):
    return path.lower().endswith(IMAGE_EXTS)


# ─────────────────────────── ffmpeg tự cài ───────────────────────────

def _find_tools(root):
    fm = fp = None
    if not os.path.isdir(root):
        return None, None
    for dp, _, files in os.walk(root):
        for fn in files:
            low = fn.lower()
            if low in ("ffmpeg", "ffmpeg.exe"):
                fm = os.path.join(dp, fn)
            elif low in ("ffprobe", "ffprobe.exe"):
                fp = os.path.join(dp, fn)
    return fm, fp


def resolve_tools():
    global FFMPEG_EXE, FFPROBE_EXE
    fm, fp = _find_tools(_APP_DIR)
    if fm and fp:
        FFMPEG_EXE, FFPROBE_EXE = fm, fp
        return True
    pm, pp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if pm and pp:
        FFMPEG_EXE, FFPROBE_EXE = pm, pp
        return True
    return False


def install_ffmpeg(log_fn, progress_fn):
    """Tải ffmpeg về thư mục app rồi giải nén. Trả True nếu thành công."""
    os.makedirs(_APP_DIR, exist_ok=True)
    zip_path = os.path.join(_APP_DIR, "_download.zip")
    log_fn("⬇  Đang tải ffmpeg... (khoảng 80 MB)")
    req = urllib.request.Request(FFMPEG_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(zip_path, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        progress_fn(done, total)
    except Exception:
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except OSError:
            pass
        raise
    log_fn("📦  Tải xong. Đang giải nén...")
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(_APP_DIR)
    except zipfile.BadZipFile:
        try:
            os.remove(zip_path)
        except OSError:
            pass
        raise RuntimeError("File tải về bị lỗi (corrupt). Thử lại nhé.")
    except OSError as e:
        raise RuntimeError(f"Lỗi giải nén (có thể đĩa đầy): {e}")
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass
    ok = resolve_tools()
    if ok:
        log_fn("✔  Đã cài ffmpeg thành công.")
    return ok


# ─────────────────────────── xử lý video ───────────────────────────

def get_duration(path):
    """Đọc thời lượng bằng ffprobe. Ném RuntimeError nếu không đọc được."""
    cmd = [FFPROBE_EXE, "-v", "quiet", "-print_format", "json", "-show_format", path]
    r = subprocess.run(cmd, **no_window_kwargs())
    try:
        data = json.loads(r.stdout or b"{}")
        dur = float(data["format"]["duration"])
        if dur <= 0:
            raise ValueError("duration=0")
        return dur
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        stderr = (r.stderr.decode("utf-8", "ignore")[-200:] if r.stderr else "").strip()
        detail = f"\n{stderr}" if stderr else ""
        raise RuntimeError(
            f"Không đọc được thời lượng: {os.path.basename(path)} ({e}){detail}"
        ) from e


def _run_ff(cmd):
    p = subprocess.run(cmd, **no_window_kwargs())
    if p.returncode != 0:
        stderr = p.stderr.decode("utf-8", "ignore")
        all_lines = [l for l in stderr.splitlines() if l.strip()]
        # Ưu tiên dòng có từ khóa lỗi thực sự
        _err_kw = ("error", "invalid", "failed", "no such", "could not", "unable",
                   "cannot", "unsupported", "corrupt", "not found", "no decoder",
                   "assertion", "aborted", "segmentation")
        err_lines = [l for l in all_lines if any(k in l.lower() for k in _err_kw)]
        # Lọc thêm: bỏ dòng metadata thường bị nhận nhầm là lỗi
        _meta_skip = ("encoder         :", "cpb properties", "side data", "timecode",
                      "handler_name", "soundhandler", "videohandler",
                      "creation_time", "compatible_brands", "minor_version",
                      "major_brand", "vendor_id",
                      "    metadata", "metadata:",
                      "input #", "output #", "stream #",
                      "duration:", "start:", "bitrate:")
        err_lines = [l for l in err_lines if not any(m in l.lower() for m in _meta_skip)]
        if err_lines:
            msg = "\n".join(err_lines[-8:])
        else:
            prog_filtered = [l for l in all_lines
                             if "speed=" not in l and not l.lstrip().startswith("frame=")
                             and not any(m in l.lower() for m in _meta_skip)]
            msg = "\n".join(prog_filtered[-15:]) if prog_filtered else stderr[-400:]
        raise RuntimeError(msg)


def _scale_filter(w, h):
    if w and h:
        sc = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")
    else:
        sc = "setsar=1"
    if TARGET_FPS:
        sc += f",fps={TARGET_FPS}"
    return sc


def _img_motion_core(tw, th, frames, idx):
    """Trả (tên_hiệu_ứng, filter_core) cho ảnh dùng zoompan ngẫu nhiên.
    10 kiểu: zoom in/out, pan 4 hướng, zoom+pan chéo, pan chéo.

    QUAN TRỌNG: với -loop 1, `on` tăng vô hạn vượt d-1 → phải clamp z >= 1.001
    và dùng ease-in-out curve để motion mượt mà, tránh sub-pixel stepping.
    """
    d   = max(2, min(frames, 300))   # tối đa 10 giây animation
    d1  = max(d - 1, 1)
    zh  = 1.12          # zoom cao nhất
    zp  = 1.25          # zoom cố định cho pan

    # Ease-in-out: 0→1 theo đường cong cos → khởi đầu/kết thúc chậm, giữa nhanh
    # Hoàn toàn hợp lệ trong ffmpeg expression evaluator
    ease = f"0.5*(1-cos(PI*min(on,{d1})/{d1}))"
    dz   = f"{zh - 1.0:.6f}"   # biên độ zoom (0.12)

    sel = (idx * 7 + (idx >> 1) * 11 + (idx >> 3) * 5) % 10

    if sel == 0:
        name = "zoom in"
        z = f"1+{dz}*{ease}"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif sel == 1:
        name = "zoom out"
        z = f"max(1.001,{zh}-{dz}*{ease})"   # clamp dưới tránh BSOD
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif sel == 2:
        name = "pan phải →"
        z = str(zp)
        x = f"(iw-iw/{zp})*{ease}"
        y = f"ih/2-(ih/{zp}/2)"
    elif sel == 3:
        name = "pan trái ←"
        z = str(zp)
        x = f"(iw-iw/{zp})*(1-{ease})"
        y = f"ih/2-(ih/{zp}/2)"
    elif sel == 4:
        name = "pan lên ↑"
        z = str(zp)
        x = f"iw/2-(iw/{zp}/2)"
        y = f"(ih-ih/{zp})*(1-{ease})"
    elif sel == 5:
        name = "pan xuống ↓"
        z = str(zp)
        x = f"iw/2-(iw/{zp}/2)"
        y = f"(ih-ih/{zp})*{ease}"
    elif sel == 6:
        name = "zoom in + drift phải"
        z = f"1+{dz}*{ease}"
        x = f"(iw-iw/zoom)*{ease}*0.45"
        y = "ih/2-(ih/zoom/2)"
    elif sel == 7:
        name = "zoom out + drift trái"
        z = f"max(1.001,{zh}-{dz}*{ease})"
        x = f"(iw-iw/zoom)*(1-{ease}*0.45)"
        y = "ih/2-(ih/zoom/2)"
    elif sel == 8:
        name = "pan chéo ↘"
        z = str(zp)
        x = f"(iw-iw/{zp})*{ease}"
        y = f"(ih-ih/{zp})*{ease}"
    else:
        name = "pan chéo ↖"
        z = str(zp)
        x = f"(iw-iw/{zp})*(1-{ease})"
        y = f"(ih-ih/{zp})*(1-{ease})"

    # 2x scale + bicubic: sub-pixel resolution mịn hơn 1.5x, z-clamp ngăn crash
    sw, sh = tw * 2, th * 2
    core = (f"scale={sw}:{sh}:flags=bicubic:force_original_aspect_ratio=increase,"
            f"crop={sw}:{sh},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={d}:"
            f"s={tw}x{th}:fps={TARGET_FPS},setsar=1")
    return name, core


def _clean_video(src, dst):
    # ultrafast + me_range=8 + refs=1 tránh x264 assertion "mv_max_spel" với video nguồn phức tạp
    # -threads 1: assertion x264 "mv[1]<=mv_max_spel || i_thread_frames==1"
    # → với 1 thread thì i_thread_frames==1 → assertion KHÔNG BAO GIỜ fire
    _run_ff([FFMPEG_EXE, "-y",
             "-err_detect", "ignore_err", "-fflags", "+genpts+igndts",
             "-i", src, "-an",
             "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
             "-pix_fmt", "yuv420p", "-bf", "0",
             "-refs", "1", "-me_range", "8", "-threads", "1",
             dst])


def _clean_audio(src, dst):
    _run_ff([FFMPEG_EXE, "-y", "-err_detect", "ignore_err", "-i", src,
             "-vn", "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k", dst])


def build_clip(video, voice, out_path, w, h, limit_speed, log_fn, fade=True, kenburns=False, idx=0):
    vdur = get_duration(voice)
    sc   = _scale_filter(w, h)

    fade_str = ""
    if fade and vdur > 1.0:
        fd = min(0.4, vdur * 0.15)
        fade_str = (f",fade=t=in:st=0:d={fd:.3f},"
                    f"fade=t=out:st={vdur-fd:.3f}:d={fd:.3f}")

    if is_image(video):
        if kenburns:
            tw, th = (w or 1920), (h or 1080)
            frames = max(2, int(round(vdur * TARGET_FPS)))
            motion_name, core = _img_motion_core(tw, th, frames, idx)
            log_fn(f"   [ẢNH] {motion_name}, khớp {vdur:.2f}s")
            vf = f"[0:v]{core}{fade_str}[v]"
        else:
            log_fn(f"   [ẢNH] giữ hình khớp {vdur:.2f}s")
            vf = f"[0:v]{sc}{fade_str}[v]"
        cmd = [FFMPEG_EXE, "-y", "-sws_flags", "bicubic",
               "-loop", "1", "-i", video, "-i", voice,
               "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
               "-t", f"{vdur:.3f}"] + _enc() + [out_path]
        _run_ff(cmd)
        return

    vidur = get_duration(video)
    need  = vdur / vidur
    if not limit_speed:
        speed = 1.0 / need
        log_fn(f"   [VIDEO] {'làm chậm' if speed<1 else 'tăng tốc'} ×{speed:.2f}  "
               f"(video {vidur:.2f}s → {vdur:.2f}s)")
        core = f"{sc},setpts={need:.5f}*PTS,setpts=PTS-STARTPTS"
        if need > 1.0:
            core += ",tpad=stop_mode=clone:stop_duration=1.0"
    elif SPEED_PTS_MIN <= need <= SPEED_PTS_MAX:
        log_fn(f"   [VIDEO] chỉnh tốc độ nhẹ ×{1/need:.2f}")
        core = f"{sc},setpts={need:.5f}*PTS,setpts=PTS-STARTPTS"
    elif need > SPEED_PTS_MAX:
        remain = vdur - SPEED_PTS_MAX * vidur + 0.3
        log_fn(f"   [VIDEO] làm chậm ×{1/SPEED_PTS_MAX:.2f} + giữ khung cuối {remain:.1f}s")
        core = (f"{sc},setpts={SPEED_PTS_MAX:.5f}*PTS,setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={remain:.3f}")
    else:
        log_fn(f"   [VIDEO] tăng tốc ×{1/SPEED_PTS_MIN:.2f} + cắt phần thừa")
        core = (f"{sc},setpts={SPEED_PTS_MIN:.5f}*PTS,"
                f"trim=0:{vdur:.3f},setpts=PTS-STARTPTS")

    vf  = f"[0:v]{core}{fade_str}[v]"
    cmd = [FFMPEG_EXE, "-y",
           "-err_detect", "ignore_err", "-fflags", "+genpts+igndts",
           "-i", video, "-i", voice,
           "-filter_complex", vf, "-map", "[v]", "-map", "1:a:0",
           "-t", f"{vdur:.3f}"] + _enc() + [out_path]
    _run_ff(cmd)


# ─────────────────────────── CapCut integration ───────────────────────────

_CAPCUT_CLONE_PY = r"D:\VideoA-Z\Autocapcut_FIXED\Autocapcut\capcut_clone.py"
_PROJECTS_ROOT   = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "CapCut", "User Data", "Projects",
)


def detect_capcut_draft():
    """Tìm thư mục com.lveditor.draft — 5 strategies, trả về path có nhiều project nhất."""
    import string, json as _json
    _APP_NAMES = (
        "CapCut", "CapCut PC", "Capcut PC", "Capcut", "cap cut", "capcut",
        "CapCut for Business", "CapCut Business", "CapCutBusiness",
        "TikTok Studio", "TikTokStudio",
        "剪映", "JianyingPro", "Jianying Pro",
    )
    _DRAFT_NAME = "com.lveditor.draft"
    _DRAFT_SUF  = os.path.join("User Data", "Projects", _DRAFT_NAME)
    _REG_KEYS   = (
        (None, r"SOFTWARE\ByteDance\CapCut"),
        (None, r"SOFTWARE\ByteDance\JianyingPro"),
        (None, r"SOFTWARE\ByteDance\CapCutBusiness"),
        (None, r"SOFTWARE\ByteDance\TikTokStudio"),
        (None, r"SOFTWARE\WOW6432Node\ByteDance\CapCut"),
        (None, r"SOFTWARE\WOW6432Node\ByteDance\JianyingPro"),
    )

    seen = set()
    candidates = []

    def _add(path):
        p = os.path.normpath(path)
        if p not in seen and os.path.isdir(p):
            seen.add(p)
            candidates.append(p)

    # Strategy 1: LOCALAPPDATA + APPDATA với tất cả tên variant
    for base_env in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(base_env, "")
        if base:
            for app in _APP_NAMES:
                _add(os.path.join(base, app, _DRAFT_SUF))

    # Strategy 2: Tất cả ổ đĩa (CapCut cài ngoài C:\)
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        username = os.environ.get("USERNAME", "")
        for i, letter in enumerate(string.ascii_uppercase):
            if not (bitmask & (1 << i)):
                continue
            drive = letter + ":\\"
            for app in _APP_NAMES:
                _add(os.path.join(drive, app, _DRAFT_SUF))
                if username:
                    for ad in (
                        os.path.join("Users", username, "AppData", "Local"),
                        os.path.join("Users", username, "AppData", "Roaming"),
                    ):
                        _add(os.path.join(drive, ad, app, _DRAFT_SUF))
    except Exception:
        pass

    # Strategy 3: Registry — ByteDance lưu đường dẫn tuỳ chỉnh
    try:
        import winreg
        _reg_hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
        for hive in _reg_hives:
            for _, key_path in _REG_KEYS:
                try:
                    with winreg.OpenKey(hive, key_path) as k:
                        for val in ("UserDataPath", "ProjectPath", "DataPath",
                                    "InstallPath", "WorkingDir", "DraftPath"):
                            try:
                                v, _ = winreg.QueryValueEx(k, val)
                                if v and isinstance(v, str):
                                    _add(os.path.join(v, "Projects", _DRAFT_NAME))
                                    _add(os.path.join(v, _DRAFT_NAME))
                                    _add(v)
                            except FileNotFoundError:
                                pass
                except FileNotFoundError:
                    pass
    except Exception:
        pass

    # Strategy 4: Đọc config/Preferences JSON của CapCut để tìm Working Directory tuỳ chỉnh
    # Khi user đổi ổ lưu draft trong Settings CapCut, path được ghi vào file này
    try:
        for base_env in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(base_env, "")
            if not base:
                continue
            for app in _APP_NAMES:
                app_dir = os.path.join(base, app)
                if not os.path.isdir(app_dir):
                    continue
                # Chromium/Electron Preferences (chứa mọi setting app)
                _cfg_files = [
                    os.path.join(app_dir, "User Data", "Default", "Preferences"),
                    os.path.join(app_dir, "User Data", "Local State"),
                    os.path.join(app_dir, "pc_settings.json"),
                    os.path.join(app_dir, "user_settings.json"),
                    os.path.join(app_dir, "settings.json"),
                    os.path.join(app_dir, "config.json"),
                    os.path.join(app_dir, "userData.json"),
                ]
                for cfg in _cfg_files:
                    if not os.path.isfile(cfg):
                        continue
                    try:
                        with open(cfg, "r", encoding="utf-8", errors="ignore") as _f:
                            _data = _json.load(_f)

                        def _scan_json(obj, _depth=0):
                            if _depth > 8:
                                return
                            if isinstance(obj, str):
                                if _DRAFT_NAME in obj:
                                    _add(obj)
                                elif len(obj) > 4 and ("Projects" in obj or "draft" in obj.lower()):
                                    _add(os.path.join(obj, "Projects", _DRAFT_NAME))
                                    _add(os.path.join(obj, _DRAFT_NAME))
                            elif isinstance(obj, dict):
                                for _v in obj.values():
                                    _scan_json(_v, _depth + 1)
                            elif isinstance(obj, list):
                                for _v in obj:
                                    _scan_json(_v, _depth + 1)

                        _scan_json(_data)
                    except Exception:
                        pass
    except Exception:
        pass

    # Strategy 5: Walk thư mục AppData tìm "com.lveditor.draft" trực tiếp
    # Giới hạn chỉ đi vào thư mục tên có chứa keyword CapCut/ByteDance/TikTok
    _KW = ("capcut", "cap cut", "byted", "tiktok", "jianying", "剪映", "lveditor")
    try:
        for base_env in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(base_env, "")
            if not base or not os.path.isdir(base):
                continue
            try:
                for _entry in os.scandir(base):
                    if not _entry.is_dir(follow_symlinks=False):
                        continue
                    if not any(_kw in _entry.name.lower() for _kw in _KW):
                        continue
                    # Walk sâu tối đa 6 cấp trong thư mục này
                    for _root, _dirs, _ in os.walk(_entry.path):
                        _rel_depth = _root[len(_entry.path):].count(os.sep)
                        if _rel_depth >= 6:
                            _dirs.clear()
                            continue
                        if os.path.basename(_root) == _DRAFT_NAME:
                            _add(_root)
                        _dirs[:] = [d for d in _dirs if not d.startswith(".")]
            except (PermissionError, OSError):
                pass
    except Exception:
        pass

    # Strategy 6: neu van chua tim thay gi, quet THANG toan bo ổ đĩa (bỏ qua
    # thư mục hệ thống) tìm đúng tên "com.lveditor.draft" — bắt được trường
    # hợp khách đã đổi "Draft storage location" trong Settings CapCut sang
    # 1 thư mục tuỳ ý (không nằm trong AppData, tên không chứa keyword CapCut
    # nào cả) mà Strategy 1-5 không đoán được. Chỉ chạy khi chưa có candidate
    # nào (tốn thời gian hơn) — giới hạn độ sâu để không quét vô hạn.
    if not candidates:
        _SKIP_TOP = {
            "windows", "program files", "program files (x86)", "programdata",
            "$recycle.bin", "system volume information", "recovery",
            "msocache", "perflogs", "boot",
        }
        try:
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i, letter in enumerate(string.ascii_uppercase):
                if not (bitmask & (1 << i)):
                    continue
                drive = letter + ":\\"
                try:
                    for _root, _dirs, _ in os.walk(drive):
                        _rel = _root[len(drive):]
                        _depth = _rel.count(os.sep) if _rel else 0
                        if _depth == 0:
                            _dirs[:] = [d for d in _dirs
                                        if d.lower() not in _SKIP_TOP and not d.startswith(".")]
                        if _depth >= 7:
                            _dirs.clear()
                            continue
                        if os.path.basename(_root) == _DRAFT_NAME:
                            _add(_root)
                            _dirs.clear()
                except (PermissionError, OSError):
                    pass
        except Exception:
            pass

    # Kết quả
    if not candidates:
        _fallback = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "CapCut", "User Data", "Projects"
        )
        return _fallback if os.path.isdir(_fallback) else ""

    if len(candidates) == 1:
        return candidates[0]

    # Nhiều candidate → chọn thư mục có nhiều project nhất (đang dùng thực sự)
    def _count_projects(d):
        try:
            return sum(1 for x in os.listdir(d)
                       if os.path.isdir(os.path.join(d, x)) and not x.startswith("com.lveditor"))
        except Exception:
            return 0

    return max(candidates, key=_count_projects)


def list_capcut_projects(draft_folder):
    """Trả danh sách [(display_name, folder_path)] từ thư mục CapCut draft."""
    results = []
    _skip = {"com.lveditor.cloud", "com.lveditor.draft", "com.lveditor.text"}
    try:
        for item in sorted(os.listdir(draft_folder), key=lambda x: x.lower()):
            if any(item.startswith(s) for s in _skip):
                continue
            p  = os.path.join(draft_folder, item)
            cf = os.path.join(p, "draft_content.json")
            if not (os.path.isdir(p) and os.path.exists(cf)):
                continue
            display = item
            mf = os.path.join(p, "draft_meta_info.json")
            if os.path.exists(mf):
                try:
                    with open(mf, "r", encoding="utf-8") as f:
                        m = json.load(f)
                    dur = m.get("tm_duration", 0) / 1e6
                    display = f"{m.get('draft_name', item)}  [{int(dur)}s]"
                except Exception:
                    pass
            results.append((display, p))
    except Exception:
        pass
    return results


def launch_capcut_clone(video_path=None):
    """Mở capcut_clone.py bình thường."""
    py = shutil.which("pythonw") or shutil.which("python")
    if not py or not os.path.exists(_CAPCUT_CLONE_PY):
        return False
    subprocess.Popen(
        [py, _CAPCUT_CLONE_PY],
        cwd=os.path.dirname(_CAPCUT_CLONE_PY),
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    return True


def launch_capcut_prefilled(video_dir, voice_dir, draft, project_path):
    """
    Mở capcut_clone.py với thư mục ảnh/voice và project được pre-fill sẵn.
    Dùng monkey-patch để không sửa capcut_clone.py.
    """
    import tempfile, textwrap
    py = shutil.which("pythonw") or shutil.which("python")
    if not py or not os.path.exists(_CAPCUT_CLONE_PY):
        return False, "Không tìm thấy capcut_clone.py hoặc Python"

    capcut_dir = os.path.dirname(_CAPCUT_CLONE_PY).replace("\\", "\\\\")
    vd  = video_dir.replace("\\", "\\\\")
    vcd = voice_dir.replace("\\", "\\\\")
    dr  = draft.replace("\\", "\\\\")
    pp  = project_path.replace("\\", "\\\\") if project_path else ""

    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, r\"{capcut_dir}\")
        import capcut_clone as _cc

        # Pre-set draft folder trước khi App khởi tạo
        _orig_detect = _cc.detect_draft
        _cc.detect_draft = lambda: r\"{dr}\"

        # Pre-fill img/voice và chọn project sau khi load
        _orig_init = _cc.App.__init__
        def _patched(self, *a, **kw):
            _orig_init(self, *a, **kw)
            self.v_img.set(r\"{vd}\")
            self.v_mp3.set(r\"{vcd}\")
            _proj = r\"{pp}\"
            def _sel():
                for i, (name, folder) in enumerate(self._projects):
                    if folder == _proj:
                        self.cmb.current(i)
                        self._on_select(None)
                        break
            if _proj:
                self.after(150, _sel)
        _cc.App.__init__ = _patched
        _cc.App().mainloop()
    """).strip()

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8",
        prefix="mv_capcut_",
    )
    tmp.write(script)
    tmp.close()

    try:
        subprocess.Popen(
            [py, tmp.name],
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return True, tmp.name
    except Exception as e:
        return False, str(e)


_CC_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
_CC_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
_CC_MEDIA_EXTS = _CC_IMAGE_EXTS | _CC_VIDEO_EXTS


def _cc_sorted_media(folder):
    """Sort ảnh+video trong folder theo tên tự nhiên (1,2,3...10,11...)."""
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in _CC_MEDIA_EXTS]
    return sorted(files, key=natural_key)


def _cc_sorted_media_priority(folder):
    """Sort ảnh+video, ưu tiên video hơn ảnh khi cùng tên cơ sở (stem).
    VD: có 3.jpg + 3.mp4 → chỉ giữ 3.mp4, bỏ 3.jpg → không lệch 1-1 với voice.
    Trả (sorted_list, n_replaced).
    """
    all_files = [os.path.join(folder, f) for f in os.listdir(folder)
                 if os.path.splitext(f)[1].lower() in _CC_MEDIA_EXTS]
    by_stem = {}
    for f in all_files:
        stem = os.path.splitext(os.path.basename(f))[0].lower()
        bk   = by_stem.setdefault(stem, {"v": [], "i": []})
        (bk["v"] if os.path.splitext(f)[1].lower() in _CC_VIDEO_EXTS else bk["i"]).append(f)

    result = []
    n_replaced = 0
    for bk in by_stem.values():
        if bk["v"]:
            result.append(sorted(bk["v"], key=natural_key)[0])
            if bk["i"]:
                n_replaced += 1   # đếm số ảnh bị bỏ vì có video cùng tên
        else:
            result.append(sorted(bk["i"], key=natural_key)[0])

    return sorted(result, key=natural_key), n_replaced


def _cc_video_wh(path):
    """Đọc width/height của video bằng ffprobe."""
    try:
        cmd = [FFPROBE_EXE, "-v", "quiet", "-print_format", "json",
               "-show_streams", "-select_streams", "v:0", path]
        p = subprocess.run(cmd, **no_window_kwargs())
        info = json.loads(p.stdout.decode("utf-8", "ignore"))
        st = info.get("streams", [{}])[0]
        return st.get("width", 1920), st.get("height", 1080)
    except Exception:
        return 1920, 1080


def _cc_make_video_mat(path, voice_dur_us):
    """Tạo material dict cho VIDEO file (type=video, không phải photo)."""
    import uuid as _uuid, time as _t
    mid = str(_uuid.uuid4()).upper()
    w, h = _cc_video_wh(path)
    pw = path.replace("\\", "/")
    ts = int(_t.time())
    mat = {
        "aigc_type": "none", "audio_fade": None, "cartoon_path": "",
        "category_id": "", "category_name": "local", "check_flag": 63487,
        "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0,
                 "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0,
                 "upper_right_x": 1.0, "upper_right_y": 0.0},
        "crop_ratio": "free", "crop_scale": 1.0, "duration": voice_dur_us,
        "extra_type_option": 0, "file_Path": pw, "filter_id": "", "filter_name": "",
        "has_audio": True, "height": h, "id": mid,
        "import_time": ts, "import_time_ms": ts * 1000,
        "item_source": 1, "md5": "", "media_path": pw, "metetype": "video",
        "path": pw,
        "roughcut_time_range": {"duration": -1, "start": -1},
        "sharpness_flag": 0, "source": "other",
        "stable": {"matrix_path": "", "stable_level": 0,
                   "time_range": {"duration": 0, "start": 0}},
        "team_id": "", "type": "video",
        "video_algorithm": {
            "algorithms": [], "deflicker": None, "motion_blur_config": None,
            "noise_reduction": None, "path": "", "quality_enhance": None, "time_range": None,
        },
        "width": w,
    }
    return mid, mat


def _cc_make_vid_seg_video(mid, actual_dur_us, voice_dur_us, start):
    """Segment cho VIDEO: source_timerange = min(actual, voice), target = voice."""
    import uuid as _uuid
    source_dur = min(actual_dur_us, voice_dur_us)
    return {
        "cartoon": False,
        "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False},
                 "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0},
                 "translation": {"x": 0.0, "y": 0.0}},
        "common_keyframes": [], "enable_adjust": True,
        "enable_color_correct_adjust": False, "enable_color_curves": True,
        "enable_lut": True, "enable_smart_color_adjust": False,
        "extra_material_refs": [], "group_id": "", "hdr_settings": None,
        "id": str(_uuid.uuid4()).upper(),
        "intensifies_audio": False, "is_placeholder": False, "is_tone_modify": False,
        "key_frame_refs": [], "last_nonzero_volume": 1.0, "material_id": mid,
        "render_index": 0,
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                              "size_layout": 0, "target_follow": "",
                              "vertical_pos_layout": 0},
        "reverse": False,
        "source_timerange": {"duration": source_dur, "start": 0},
        "speed": 1.0,
        "target_timerange": {"duration": voice_dur_us, "start": start},
        "template_id": "", "template_scene": "default",
        "track_attribute": 0, "track_render_index": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True, "volume": 1.0,
    }


# ── CapCut JSON helpers (inline — không phụ thuộc capcut_clone.py) ─────────

_CC_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def _cc_sorted_audio(folder):
    """Sort audio files trong folder theo tên tự nhiên."""
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in _CC_AUDIO_EXTS]
    return sorted(files, key=natural_key)


def _cc_get_dur(path):
    """Duration của audio/video file → microseconds (dùng ffprobe)."""
    try:
        cmd = [FFPROBE_EXE, "-v", "quiet", "-print_format", "json",
               "-show_format", "-show_streams", path]
        r = subprocess.run(cmd, **no_window_kwargs())
        info = json.loads(r.stdout.decode("utf-8", "ignore"))
        for s in info.get("streams", []):
            if s.get("codec_type") in ("audio", "video") and s.get("duration"):
                return int(float(s["duration"]) * 1_000_000)
        dur = info.get("format", {}).get("duration")
        if dur:
            return int(float(dur) * 1_000_000)
    except Exception:
        pass
    return 3_000_000  # fallback 3s


def _cc_image_wh(path):
    """Đọc width/height ảnh bằng ffprobe."""
    try:
        cmd = [FFPROBE_EXE, "-v", "quiet", "-print_format", "json",
               "-show_streams", "-select_streams", "v:0", path]
        r = subprocess.run(cmd, **no_window_kwargs())
        info = json.loads(r.stdout.decode("utf-8", "ignore"))
        st = info.get("streams", [{}])[0]
        return st.get("width", 1920), st.get("height", 1080)
    except Exception:
        return 1920, 1080


def _cc_make_photo_mat(path, voice_dur_us):
    """Material dict cho file ẢNH (type=photo)."""
    import uuid as _uuid, time as _t
    mid = str(_uuid.uuid4()).upper()
    w, h = _cc_image_wh(path)
    pw = path.replace("\\", "/")
    ts = int(_t.time())
    return mid, {
        "aigc_type": "none", "audio_fade": None, "cartoon_path": "",
        "category_id": "", "category_name": "local", "check_flag": 63487,
        "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0,
                 "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0,
                 "upper_right_x": 1.0, "upper_right_y": 0.0},
        "crop_ratio": "free", "crop_scale": 1.0, "duration": voice_dur_us,
        "extra_type_option": 0, "file_Path": pw, "filter_id": "", "filter_name": "",
        "has_audio": False, "height": h, "id": mid,
        "import_time": ts, "import_time_ms": ts * 1000,
        "item_source": 1, "md5": "", "media_path": pw, "metetype": "photo",
        "path": pw,
        "roughcut_time_range": {"duration": -1, "start": -1},
        "sharpness_flag": 0, "source": "other",
        "stable": {"matrix_path": "", "stable_level": 0,
                   "time_range": {"duration": 0, "start": 0}},
        "team_id": "", "type": "photo",
        "video_algorithm": {
            "algorithms": [], "deflicker": None, "motion_blur_config": None,
            "noise_reduction": None, "path": "", "quality_enhance": None,
            "time_range": None,
        },
        "width": w,
    }


def _cc_make_photo_seg(mid, voice_dur_us, start):
    """Segment dict cho ẢNH (source = voice_dur, target = voice_dur)."""
    import uuid as _uuid
    return {
        "cartoon": False,
        "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False},
                 "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0},
                 "translation": {"x": 0.0, "y": 0.0}},
        "common_keyframes": [], "enable_adjust": True,
        "enable_color_correct_adjust": False, "enable_color_curves": True,
        "enable_lut": True, "enable_smart_color_adjust": False,
        "extra_material_refs": [], "group_id": "", "hdr_settings": None,
        "id": str(_uuid.uuid4()).upper(),
        "intensifies_audio": False, "is_placeholder": False, "is_tone_modify": False,
        "key_frame_refs": [], "last_nonzero_volume": 1.0, "material_id": mid,
        "render_index": 0,
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                              "size_layout": 0, "target_follow": "",
                              "vertical_pos_layout": 0},
        "reverse": False,
        "source_timerange": {"duration": voice_dur_us, "start": 0},
        "speed": 1.0,
        "target_timerange": {"duration": voice_dur_us, "start": start},
        "template_id": "", "template_scene": "default",
        "track_attribute": 0, "track_render_index": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True, "volume": 1.0,
    }


def _cc_make_aud_mat(path, voice_dur_us):
    """Material dict cho file AUDIO."""
    import uuid as _uuid, time as _t
    amid = str(_uuid.uuid4()).upper()
    pw = path.replace("\\", "/")
    ts = int(_t.time())
    return amid, {
        "audio_fade": None, "category_id": "", "category_name": "",
        "check_flag": 1, "duration": voice_dur_us,
        "effect_id": "", "file_Path": pw, "formula_id": "",
        "id": amid,
        "import_time": ts, "import_time_ms": ts * 1000,
        "item_source": 1, "local_material_id": "", "music_id": "",
        "name": os.path.basename(path), "path": pw,
        "query": "", "request_id": "", "resource_id": "", "search_id": "",
        "source_platform": 0, "team_id": "", "text": "",
        "tone_color": "", "type": "extract_music", "wave_points": [],
    }


def _cc_make_aud_seg(amid, voice_dur_us, start):
    """Segment dict cho AUDIO."""
    import uuid as _uuid
    return {
        "cartoon": False,
        "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False},
                 "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0},
                 "translation": {"x": 0.0, "y": 0.0}},
        "common_keyframes": [], "enable_adjust": True,
        "enable_color_correct_adjust": False, "enable_color_curves": True,
        "enable_lut": False, "enable_smart_color_adjust": False,
        "extra_material_refs": [], "group_id": "", "hdr_settings": None,
        "id": str(_uuid.uuid4()).upper(),
        "intensifies_audio": False, "is_placeholder": False, "is_tone_modify": False,
        "key_frame_refs": [], "last_nonzero_volume": 1.0, "material_id": amid,
        "render_index": 0,
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                              "size_layout": 0, "target_follow": "",
                              "vertical_pos_layout": 0},
        "reverse": False,
        "source_timerange": {"duration": voice_dur_us, "start": 0},
        "speed": 1.0,
        "target_timerange": {"duration": voice_dur_us, "start": start},
        "template_id": "", "template_scene": "default",
        "track_attribute": 0, "track_render_index": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True, "volume": 1.0,
    }


def _cc_apply_to_project(template_path, vid_mats_list, aud_mats_list,
                          vid_segs_list, aud_segs_list, total_dur_us,
                          new_name, is_overwrite, draft_folder, log_fn):
    """
    Đọc template CapCut project → ADD 2 track mới (video + audio) vào DƯỚI CÙNG.
    KHÔNG đụng bất kỳ track/material nào của template (kêu gọi sub, nhạc nền, text...).
    Returns (new_folder, n_segs).
    """
    import shutil as _shu, time as _t, uuid as _uuid
    draft_json = os.path.join(template_path, "draft_content.json")
    with open(draft_json, "r", encoding="utf-8") as _f:
        data = json.load(_f)

    # EXTEND materials — KHÔNG replace, giữ nguyên material gốc của template
    data.setdefault("materials", {})
    data["materials"].setdefault("videos", [])
    data["materials"].setdefault("audios", [])
    data["materials"]["videos"].extend(vid_mats_list)
    data["materials"]["audios"].extend(aud_mats_list)

    # Tạo 2 track MỚI hoàn toàn — INSERT vào đầu mảng tracks (= bottom layer trong CapCut)
    # Track gốc của template (kêu gọi sub, sticker, text, nhạc nền...) KHÔNG bị đụng
    _tracks = data.setdefault("tracks", [])
    _n_old  = len(_tracks)

    new_vid_track = {
        "attribute": 0, "flag": 0,
        "id": str(_uuid.uuid4()).upper(),
        "is_default_name": True, "name": "",
        "segments": vid_segs_list,
        "type": "video",
    }
    new_aud_track = {
        "attribute": 0, "flag": 0,
        "id": str(_uuid.uuid4()).upper(),
        "is_default_name": True, "name": "",
        "segments": aud_segs_list,
        "type": "audio",
    }
    # insert(0, aud) rồi insert(0, vid) → thứ tự cuối: [vid, aud, ...template tracks...]
    # vid ở index 0 = bottom layer; aud ở index 1 = ngay trên vid
    _tracks.insert(0, new_aud_track)
    _tracks.insert(0, new_vid_track)
    log_fn(f"   ℹ  Giữ nguyên {_n_old} track template — thêm mới: 1 video + 1 audio (dưới cùng)")

    # Duration = max để không rút ngắn nhạc nền / kêu gọi sub của template
    data["duration"] = max(data.get("duration", 0), total_dur_us)
    data["name"] = new_name

    # Tạo thư mục project mới
    new_folder = os.path.join(draft_folder, new_name)
    if os.path.exists(new_folder):
        if is_overwrite:
            _shu.rmtree(new_folder, ignore_errors=True)
        else:
            new_folder = os.path.join(draft_folder, f"{new_name}_{int(_t.time())}")
    os.makedirs(new_folder, exist_ok=True)

    # Copy file phụ từ template (thumbnail, meta…) — bỏ qua draft_content.json
    for _item in os.listdir(template_path):
        if _item == "draft_content.json":
            continue
        _src = os.path.join(template_path, _item)
        _dst = os.path.join(new_folder, _item)
        try:
            if os.path.isfile(_src):
                _shu.copy2(_src, _dst)
        except Exception:
            pass

    # Cập nhật draft_meta_info.json nếu có
    _meta = os.path.join(new_folder, "draft_meta_info.json")
    if os.path.isfile(_meta):
        try:
            with open(_meta, "r", encoding="utf-8") as _mf:
                _mdata = json.load(_mf)
            _mdata["draft_name"] = new_name
            _mdata["tm_duration"] = data["duration"]
            with open(_meta, "w", encoding="utf-8") as _mf:
                json.dump(_mdata, _mf, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass

    # Ghi draft_content.json mới
    out_json = os.path.join(new_folder, "draft_content.json")
    with open(out_json, "w", encoding="utf-8") as _f:
        json.dump(data, _f, ensure_ascii=False, separators=(",", ":"))

    log_fn(f"✅ Project '{new_name}' → {new_folder}")
    return new_folder, len(vid_segs_list)


def push_to_capcut(media_dir, voice_dir, template_path, draft_folder,
                   new_name, is_overwrite, log_fn, progress_fn,
                   on_start=None):
    """
    Headless: đẩy ảnh+video+voice 1-1 vào CapCut project.
    Tự động phân biệt ảnh (type=photo) và video (type=video).
    Trả (folder, n_pairs, minutes, seconds).
    Self-contained — không cần capcut_clone.py.
    """
    media_files, n_replaced = _cc_sorted_media_priority(media_dir)
    audio_files = _cc_sorted_audio(voice_dir)

    if not media_files:
        raise RuntimeError(f"Không tìm thấy ảnh/video trong:\n{media_dir}")
    if not audio_files:
        raise RuntimeError(f"Không tìm thấy audio trong:\n{voice_dir}")

    if n_replaced:
        log_fn(f"   🎬 Ưu tiên video: {n_replaced} video thay ảnh cùng tên (ảnh tương ứng bị bỏ)")

    n = min(len(media_files), len(audio_files))
    if len(media_files) != len(audio_files):
        log_fn(f"   ⚠ Media={len(media_files)} / Voice={len(audio_files)} — ghép {n} cặp đầu")
    media_files = media_files[:n]
    audio_files = audio_files[:n]

    n_img = sum(1 for f in media_files if os.path.splitext(f)[1].lower() in _CC_IMAGE_EXTS)
    n_vid = n - n_img
    log_fn(f"▶ Ghép {n} cặp ({n_img} ảnh + {n_vid} video) vào CapCut...")

    if on_start:
        on_start(n)

    vid_mats = {}
    aud_mats = {}
    vid_segs_list = []
    aud_segs_list = []
    cursor = 0

    for i, (media, mp3) in enumerate(zip(media_files, audio_files)):
        voice_dur_us = _cc_get_dur(mp3)
        ext = os.path.splitext(media)[1].lower()

        if ext in _CC_IMAGE_EXTS:
            vmid, vm = _cc_make_photo_mat(media, voice_dur_us)
            vseg = _cc_make_photo_seg(vmid, voice_dur_us, cursor)
        else:
            actual_dur_s = get_duration(media)
            actual_dur_us = int(actual_dur_s * 1_000_000)
            vmid, vm = _cc_make_video_mat(media, actual_dur_us)
            vseg = _cc_make_vid_seg_video(vmid, actual_dur_us, voice_dur_us, cursor)

        amid, am = _cc_make_aud_mat(mp3, voice_dur_us)
        aseg = _cc_make_aud_seg(amid, voice_dur_us, cursor)

        vid_mats[vmid] = vm
        aud_mats[amid] = am
        vid_segs_list.append(vseg)
        aud_segs_list.append(aseg)

        log_fn(f"  [{i+1:03d}] {os.path.basename(media)} ↔ {os.path.basename(mp3)}"
               f"  ({voice_dur_us/1e6:.2f}s)")
        progress_fn(i + 1)
        cursor += voice_dur_us

    folder, _ = _cc_apply_to_project(
        template_path,
        list(vid_mats.values()), list(aud_mats.values()),
        vid_segs_list, aud_segs_list, cursor,
        new_name, is_overwrite, draft_folder, log_fn,
    )
    mins, secs = divmod(int(cursor / 1_000_000), 60)
    return folder, n, mins, secs


def next_final_path(out_dir):
    i = 1
    while True:
        p = os.path.join(out_dir, f"final{i}.mp4")
        if not os.path.exists(p):
            return p
        i += 1


def next_named_path(out_dir, name):
    """Tạo path với tên tùy chỉnh; thêm _N nếu đã tồn tại."""
    p = os.path.join(out_dir, f"{name}.mp4")
    if not os.path.exists(p):
        return p
    i = 1
    while True:
        p = os.path.join(out_dir, f"{name}_{i}.mp4")
        if not os.path.exists(p):
            return p
        i += 1


def concat_clips(clips, final_path, out_dir):
    list_file = os.path.join(out_dir, "_concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            abs_path = os.path.abspath(c).replace("\\", "/")
            escaped  = abs_path.replace("'", "''")
            f.write(f"file '{escaped}'\n")

    def _ok():
        return os.path.exists(final_path) and os.path.getsize(final_path) > 0

    cmd_copy = [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c", "copy", "-movflags", "+faststart", final_path]
    p = subprocess.run(cmd_copy, **no_window_kwargs())
    if p.returncode != 0 or not _ok():
        cmd_enc = [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", list_file
                   ] + _enc() + ["-movflags", "+faststart", final_path]
        _run_ff(cmd_enc)

    try:
        os.remove(list_file)
    except OSError:
        pass


def _concat_clips_xfade(clips, final_path, out_dir, trans_dur=0.4):
    """Nối clips với xfade transitions ngẫu nhiên. Audio dùng concat cứng (không crossfade)."""
    n = len(clips)
    if n == 0:
        return
    if n == 1:
        shutil.copy2(clips[0], final_path)
        return

    # Đọc duration từng clip
    durations = []
    for c in clips:
        try:
            durations.append(get_duration(c))
        except Exception:
            durations.append(5.0)

    # Xây filter_complex: xfade cho video, concat cho audio
    filter_lines = []
    output_dur = durations[0]
    prev_v = "0:v"

    for i in range(1, n):
        offset = max(0.05, output_dur - trans_dur)
        output_dur = output_dur + durations[i] - trans_dur
        # Chọn transition theo idx giả ngẫu nhiên
        trans = _XFADE_TRANS[((i * 7 + (i >> 1) * 11 + len(clips)) % len(_XFADE_TRANS))]
        cur_v = f"xv{i}"
        filter_lines.append(
            f"[{prev_v}][{i}:v]xfade=transition={trans}:duration={trans_dur:.2f}:offset={offset:.3f}[{cur_v}]"
        )
        prev_v = cur_v

    # Audio: concat không overlap
    audio_in = "".join(f"[{i}:a]" for i in range(n))
    filter_lines.append(f"{audio_in}concat=n={n}:v=0:a=1[outa]")

    filter_str = ";\n".join(filter_lines)
    filter_file = os.path.join(out_dir, "_xfade_filter.txt")
    try:
        with open(filter_file, "w", encoding="utf-8") as f:
            f.write(filter_str)

        input_args = []
        for c in clips:
            input_args.extend(["-i", c])

        cmd = ([FFMPEG_EXE, "-y"] + input_args +
               ["-filter_complex_script", filter_file,
                "-map", f"[{prev_v}]", "-map", "[outa]"] +
               _enc() + ["-movflags", "+faststart", final_path])
        _run_ff(cmd)
    except Exception:
        # Fallback: dùng concat thường nếu xfade lỗi
        concat_clips(clips, final_path, out_dir)
    finally:
        try:
            os.remove(filter_file)
        except OSError:
            pass


def process_pairs(voices, videos, out_dir, w, h, limit_speed, fade, kenburns,
                  only_final, log_fn, progress_fn, final_name=None, transitions=False,
                  cancel_ev=None):
    """
    Ghép tất cả cặp voice+video. Dùng bởi cả standalone app lẫn MagicVoice tab.

    log_fn(msg)          — callback in log
    progress_fn(done, total) — callback cập nhật progress bar
    transitions          — dùng xfade transitions ngẫu nhiên giữa các clip (chỉ khi only_final=True)
    Trả (final_path_hoặc_None, n_loi).
    """
    n      = min(len(voices), len(videos))
    clip_dir = os.path.join(out_dir, "_clip_tam") if only_final else out_dir
    os.makedirs(clip_dir, exist_ok=True)

    clips = []
    n_loi = 0
    _nvenc = _check_nvenc()
    log_fn(f"🎬 Encoder: {'NVIDIA GPU (h264_nvenc)' if _nvenc else 'CPU (libx264)'}")
    last_ok_video = None  # media gần nhất ghép thành công — dùng để bù khi media lỗi

    for i in range(n):
        if cancel_ev and cancel_ev.is_set():
            log_fn("⛔  Đã dừng bởi người dùng.")
            break
        out_path = os.path.join(clip_dir, f"clip_{i+1:02d}.mp4")

        def _done(p=out_path):
            return os.path.exists(p) and os.path.getsize(p) > 0

        ok      = False
        err_msg = ""
        try:
            vd = get_duration(voices[i])
            log_fn(f"[{i+1:02d}/{n}]  voice {vd:.2f}s  |  {os.path.basename(videos[i])}")
            build_clip(videos[i], voices[i], out_path, w, h, limit_speed, log_fn, fade, kenburns, i)
            ok = _done()
        except Exception as e1:
            err_msg = str(e1).strip()
            ok = False

        if not ok:
            if err_msg:
                log_fn(f"   ⚠  Lỗi: {err_msg.splitlines()[-1][:200]}")
            log_fn(f"   ⚙  Cặp {i+1} có vấn đề → đang sửa file rồi ghép lại...")
            fv = os.path.join(clip_dir, f"_fixv_{i+1}.mp4")
            fa = os.path.join(clip_dir, f"_fixa_{i+1}.m4a")
            try:
                _clean_audio(voices[i], fa)
                if is_image(videos[i]):
                    build_clip(videos[i], fa, out_path, w, h, limit_speed, log_fn, fade, kenburns, i)
                    ok = _done()
                else:
                    _clean_video(videos[i], fv)      # ultrafast → tránh x264 assertion
                    # Encode trực tiếp bằng ultrafast (không qua build_clip vốn dùng veryfast
                    # có thể trigger assertion trên cùng nội dung video)
                    _vdur_f  = get_duration(fa)
                    _vidur_f = get_duration(fv)
                    _need_f  = _vdur_f / max(_vidur_f, 0.001)
                    _sc_f    = _scale_filter(w, h)
                    _need_f  = max(0.3, min(3.5, _need_f))
                    _core_f  = f"{_sc_f},setpts={_need_f:.5f}*PTS,setpts=PTS-STARTPTS"
                    if _need_f > 1.0:
                        _core_f += ",tpad=stop_mode=clone:stop_duration=1.0"
                    log_fn(f"   [VIDEO-SAFE] {'làm chậm' if _need_f>1 else 'tăng tốc'} ×{1/_need_f:.2f} (ultrafast)")
                    _enc_safe = (
                        ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr",
                         "-cq", "25", "-pix_fmt", "yuv420p",
                         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
                        if _nvenc else
                        ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                         "-pix_fmt", "yuv420p", "-bf", "0", "-refs", "1", "-threads", "1",
                         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
                    )
                    _run_ff([FFMPEG_EXE, "-y",
                             "-err_detect", "ignore_err", "-fflags", "+genpts+igndts",
                             "-i", fv, "-i", fa,
                             "-filter_complex", f"[0:v]{_core_f}[v]",
                             "-map", "[v]", "-map", "1:a:0",
                             "-t", f"{_vdur_f:.3f}"] + _enc_safe + [out_path])
                    ok = _done()
                if ok:
                    log_fn("   ✔  Đã sửa và ghép thành công.")
            except Exception as e2:
                e2s = str(e2).strip()
                # Tìm dòng lỗi thực, bỏ qua metadata
                _e2_lines = [l for l in e2s.splitlines()
                             if l.strip() and not any(m in l.lower() for m in
                             ("handler_name", "metadata", "soundhandler", "videohandler",
                              "creation_time", "compatible_brands"))]
                _e2_disp = _e2_lines[0][:120] if _e2_lines else (e2s[:120] if e2s else "file hỏng nặng")
                log_fn(f"      (sửa không được: {_e2_disp})")
            finally:
                for ftmp in (fv, fa):
                    try:
                        if os.path.exists(ftmp):
                            os.remove(ftmp)
                    except OSError:
                        pass

        # Bù media: nếu vẫn lỗi, dùng media lân cận hoạt động được
        # — Có media trước: dùng media trước (last_ok_video)
        # — Chưa có (cặp đầu lỗi): thử media kế tiếp (videos[i+1])
        _fallback_used = False
        if not ok:
            if last_ok_video is not None:
                _fb = last_ok_video
                _fb_label = "media trước"
            elif i + 1 < len(videos):
                _fb = videos[i + 1]
                _fb_label = "media kế tiếp"
            else:
                _fb = None
                _fb_label = ""
            if _fb is not None:
                log_fn(f"   🔄  Media lỗi → bù bằng {_fb_label}: {os.path.basename(_fb)}")
                try:
                    build_clip(_fb, voices[i], out_path,
                               w, h, limit_speed, log_fn, fade, kenburns, i)
                    ok = _done()
                    if ok:
                        last_ok_video = _fb  # cập nhật đúng file đã dùng
                        _fallback_used = True
                        log_fn("   ✔  Bù thành công.")
                except Exception:
                    ok = False

        if ok:
            if not _fallback_used:
                last_ok_video = videos[i]  # cập nhật bình thường nếu không dùng fallback
            clips.append(out_path)
        else:
            n_loi += 1
            log_fn(f"   ⚠  BỎ QUA cặp {i+1}: {os.path.basename(voices[i])} + {os.path.basename(videos[i])}")

        progress_fn(i + 1, n + (1 if only_final else 0))

    if not clips:
        if only_final and os.path.isdir(clip_dir):
            try:
                shutil.rmtree(clip_dir, ignore_errors=True)
            except OSError:
                pass
        return None, n_loi

    final_path = None
    if only_final:
        final_path = (next_named_path(out_dir, final_name) if final_name
                      else next_final_path(out_dir))
        if transitions and len(clips) > 1:
            log_fn(f"Đang nối với xfade transitions → {os.path.basename(final_path)} ...")
            _concat_clips_xfade(clips, final_path, clip_dir, trans_dur=0.4)
        else:
            log_fn(f"Đang nối tất cả thành {os.path.basename(final_path)} ...")
            concat_clips(clips, final_path, clip_dir)
        progress_fn(n + 1, n + 1)
        try:
            shutil.rmtree(clip_dir, ignore_errors=True)
        except OSError:
            pass

    return final_path, n_loi
