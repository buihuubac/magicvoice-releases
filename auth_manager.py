"""
auth_manager.py — Xac thuc qua API Server (an toan hon)
Khong can firebase_credentials.json tren may khach
v3.22: Them session_token cho single-session real-time
v3.22.3: PERSIST machine_id xuong LOCALAPPDATA de tranh wmic flaky
         (wmic timeout=2s qua ngan -> rot fallback MAC+hostname -> MID doi)
v3.22.4: CHUYEN .session_token + .offline_auth sang LOCALAPPDATA
         (tranh permission denied khi tool cai o Program Files)
"""
import hashlib, os, platform, uuid, base64 as _b64
from datetime import datetime, timedelta
from pathlib import Path
import json as _json

# ── Cau hinh API Server (obfuscated) ──────────────────────────────
def _d(s):
    """Decode chuoi obfuscated: reverse + base64 decode 2 lan."""
    try:
        return _b64.b64decode(_b64.b64decode(s[::-1]).decode()).decode()
    except Exception:
        return ""

_API_URL = _d("=0TPRJmdO1GT5Z1RaVnVtNWd50GT4BzUaBjRHp1dWhFTs50VhZnWzkFckdVW0lTeMZTTINGMShUY")
_API_KEY = _d("=0TVq10dJpHWwYVbjpmVyMmZahlY")

# ── Machine ID Persist Storage ────────────────────────────────────
def _get_mid_storage_path():
    """Tra ve path file luu machine_id.
    Uu tien LOCALAPPDATA de persist qua reinstall/update tool.
    """
    try:
        if platform.system() == "Windows":
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if base:
                d = Path(base) / "MagicVoice"
                d.mkdir(parents=True, exist_ok=True)
                return d / "machine_id.dat"
        else:
            home = os.environ.get("HOME") or os.path.expanduser("~")
            if home:
                d = Path(home) / ".magicvoice"
                d.mkdir(parents=True, exist_ok=True)
                return d / "machine_id.dat"
    except Exception:
        pass
    # Fallback cuoi cung: ben canh file auth_manager
    return Path(__file__).parent / ".machine_id"

_MID_FILE = _get_mid_storage_path()
_MACHINE_ID_CACHE = None

def _compute_machine_id_raw() -> str:
    """Compute MID lan dau. Co the cham ~3-5s do wmic."""
    try:
        if platform.system() == "Windows":
            import subprocess
            try:
                # Tang timeout 2s -> 10s de tranh fallback flaky
                result = subprocess.run(
                    ["wmic", "csproduct", "get", "UUID"],
                    capture_output=True, text=True, timeout=10
                )
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                uid = lines[-1] if len(lines) >= 2 else ""
                if uid and uid != "UUID" and len(uid) > 10:
                    return hashlib.sha256(uid.encode()).hexdigest()[:32]
            except Exception:
                pass
        # Fallback: MAC + hostname
        mac  = hex(uuid.getnode())[2:].upper()
        host = platform.node()
        return hashlib.sha256(f"{mac}_{host}".encode()).hexdigest()[:32]
    except Exception:
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:32]

def get_machine_id() -> str:
    """Return machine ID. Persist xuong file de bao dam ON DINH qua cac lan chay."""
    global _MACHINE_ID_CACHE
    if _MACHINE_ID_CACHE:
        return _MACHINE_ID_CACHE

    # 1. Doc tu file persist (uu tien cao nhat — bao dam on dinh)
    try:
        if _MID_FILE.exists():
            saved = _MID_FILE.read_text(encoding="utf-8").strip()
            if saved and 16 <= len(saved) <= 64 and saved.isalnum():
                _MACHINE_ID_CACHE = saved
                return saved
    except Exception:
        pass

    # 2. Compute lan dau va save xuong file
    mid = _compute_machine_id_raw()
    _MACHINE_ID_CACHE = mid
    try:
        _MID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MID_FILE.write_text(mid, encoding="utf-8")
    except Exception:
        pass
    return mid

def _hash_pass(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ── User Data Directory (cung 1 cho voi machine_id.dat) ──────────
def _get_user_data_dir():
    """Tra ve thu muc luu data nguoi dung (LOCALAPPDATA tren Windows).
    Tranh ghi vao thu muc cai tool (co the bi UAC/read-only).
    """
    try:
        if platform.system() == "Windows":
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if base:
                d = Path(base) / "MagicVoice"
                d.mkdir(parents=True, exist_ok=True)
                return d
        else:
            home = os.environ.get("HOME") or os.path.expanduser("~")
            if home:
                d = Path(home) / ".magicvoice"
                d.mkdir(parents=True, exist_ok=True)
                return d
    except Exception:
        pass
    return Path(__file__).parent

_USER_DATA_DIR = _get_user_data_dir()

# ── Session Token Storage (luu sau khi login thanh cong) ─────────
_SESSION_FILE = _USER_DATA_DIR / ".session_token"
# Backward-compat: doc ca file cu o thu muc tool neu file moi chua co
_SESSION_FILE_LEGACY = Path(__file__).parent / ".session_token"

def save_session_token(username: str, token: str):
    """Luu session_token sau khi login OK. Heartbeat se doc lai."""
    try:
        import base64
        data = {"u": username, "t": token, "saved": datetime.now().isoformat()}
        encoded = base64.b64encode(_json.dumps(data).encode()).decode()
        _SESSION_FILE.write_text(encoded, encoding="utf-8")
    except Exception:
        # Fallback: ghi vao thu muc tool (legacy)
        try:
            import base64
            data = {"u": username, "t": token, "saved": datetime.now().isoformat()}
            encoded = base64.b64encode(_json.dumps(data).encode()).decode()
            _SESSION_FILE_LEGACY.write_text(encoded, encoding="utf-8")
        except Exception:
            pass

def get_session_token(username: str) -> str:
    """Doc session_token tu file. Tra '' neu khong co hoac sai username."""
    import base64
    # Doc tu file moi truoc
    for fpath in (_SESSION_FILE, _SESSION_FILE_LEGACY):
        try:
            if not fpath.exists():
                continue
            encoded = fpath.read_text(encoding="utf-8").strip()
            data = _json.loads(base64.b64decode(encoded).decode())
            if data.get("u") == username:
                return data.get("t", "")
        except Exception:
            continue
    return ""

def clear_session_token():
    """Xoa session_token (khi bi kick / logout)."""
    for fpath in (_SESSION_FILE, _SESSION_FILE_LEGACY):
        try:
            if fpath.exists():
                fpath.unlink()
        except Exception:
            pass

# ── Heartbeat: kiem tra session co bi day ra khong ────────────────
def check_session_alive(username: str, session_token: str, timeout: int = 8) -> tuple:
    """
    Goi server /check_session de kiem tra session_token con hop le.
    Tra ve (status, msg):
      status = "ok"      -> session con OK
      status = "kicked"  -> bi day ra (may khac da login) -> client phai logout
      status = "error"   -> loi mang/server -> client KHONG kick (de tranh kick oan)
    """
    import requests
    if not username or not session_token:
        return "error", "Thieu username/token"
    try:
        resp = requests.post(
            f"{_API_URL}/check_session",
            json={"username": username, "session_token": session_token},
            headers={"X-API-Key": _API_KEY},
            timeout=timeout
        )
        data = resp.json()
        if data.get("kicked"):
            return "kicked", data.get("msg", "Bi day ra")
        if data.get("ok"):
            return "ok", "OK"
        # ok=False, kicked=False -> loi server, KHONG kick
        return "error", data.get("msg", "Loi server")
    except Exception as e:
        return "error", f"Loi mang: {str(e)[:60]}"

# ── Xac thuc online qua API ───────────────────────────────────────
def verify_login(username: str, password: str) -> tuple:
    """Xac thuc qua API server - retry voi timeout tang dan.
    v3.22: Luu session_token sau khi login thanh cong."""
    import requests, time
    last_err = "Lỗi kết nối!"
    timeouts = [8, 20, 30]
    for _attempt in range(3):
        try:
            resp = requests.post(
                f"{_API_URL}/verify",
                json={
                    "username":   username,
                    "password":   password,
                    "machine_id": get_machine_id()
                },
                headers={"X-API-Key": _API_KEY},
                timeout=timeouts[_attempt]
            )
            data = resp.json()
            if data.get("ok"):
                # MOI v3.22: Luu session_token de heartbeat dung
                _stoken = data.get("session_token", "")
                if _stoken:
                    save_session_token(username, _stoken)
                _save_offline_cache(username, password, data.get("msg", ""))
                return True, data.get("msg", "Đăng nhập thành công!")
            else:
                return False, data.get("msg", "Đăng nhập thất bại!")
        except Exception as e:
            last_err = str(e)
            if _attempt < 2:
                time.sleep(1)
                continue
    return False, f"Lỗi kết nối: {last_err}"

def warm_up_server() -> bool:
    """Goi /ping de wake up server. Tra True neu OK."""
    import requests
    try:
        requests.get(f"{_API_URL}/ping", timeout=2)
        return True
    except Exception:
        return False

# ── Offline Cache ─────────────────────────────────────────────────
_OFFLINE_CACHE = _USER_DATA_DIR / ".offline_auth"
_OFFLINE_CACHE_LEGACY = Path(__file__).parent / ".offline_auth"
_OFFLINE_DAYS  = 7

def _save_offline_cache(username: str, password: str, msg: str):
    try:
        import base64
        exp = (datetime.now() + timedelta(days=_OFFLINE_DAYS)).isoformat()
        data = {
            "u":   username,
            "p":   _hash_pass(password),
            "msg": msg,
            "exp": exp,
            "mid": get_machine_id(),
        }
        encoded = base64.b64encode(_json.dumps(data).encode()).decode()
        try:
            _OFFLINE_CACHE.write_text(encoded, encoding="utf-8")
        except Exception:
            _OFFLINE_CACHE_LEGACY.write_text(encoded, encoding="utf-8")
    except Exception:
        pass

def verify_login_offline(username: str, password: str):
    import base64
    last_err = None
    for fpath in (_OFFLINE_CACHE, _OFFLINE_CACHE_LEGACY):
        try:
            if not fpath.exists():
                continue
            encoded = fpath.read_text(encoding="utf-8").strip()
            data    = _json.loads(base64.b64decode(encoded).decode())
            if data.get("mid") != get_machine_id():
                last_err = "Cache không hợp lệ trên máy này."
                continue
            exp_dt = datetime.fromisoformat(data["exp"])
            if datetime.now() > exp_dt:
                last_err = f"Cache offline đã hết hạn {exp_dt.strftime('%d/%m/%Y')}.\nKết nối internet và đăng nhập lại."
                continue
            if data.get("u") != username:
                last_err = "Sai tên tài khoản (offline)."
                continue
            if data.get("p") != _hash_pass(password):
                last_err = "Sai mật khẩu (offline)."
                continue
            days_left = (exp_dt - datetime.now()).days
            return True, data.get("msg", "Đăng nhập thành công!") + f" [Offline - còn {days_left} ngày]"
        except Exception as e:
            last_err = f"Lỗi đọc cache: {e}"
            continue
    return False, last_err or "Chưa có cache offline. Cần đăng nhập online ít nhất 1 lần."

def clear_offline_cache():
    for fpath in (_OFFLINE_CACHE, _OFFLINE_CACHE_LEGACY):
        try:
            if fpath.exists():
                fpath.unlink()
        except Exception:
            pass
