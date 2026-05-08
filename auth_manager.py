"""
auth_manager.py — Xac thuc qua API Server (an toan hon)
Khong can firebase_credentials.json tren may khach
v3.22: Them session_token cho single-session real-time
"""
import hashlib, os, platform, uuid
from datetime import datetime, timedelta
from pathlib import Path
import json as _json

# ── Cau hinh API Server ───────────────────────────────────────────
_API_URL = "https://magicvoice-update-1.onrender.com"
_API_KEY  = "mv_secret_2025"

# ── Machine ID (CACHE de tranh wmic chay nhieu lan, moi lan ~3-5s) ─
_MACHINE_ID_CACHE = None

def get_machine_id() -> str:
    """Return machine ID, cached after first call to avoid slow wmic."""
    global _MACHINE_ID_CACHE
    if _MACHINE_ID_CACHE:
        return _MACHINE_ID_CACHE
    try:
        if platform.system() == "Windows":
            import subprocess
            try:
                result = subprocess.run(
                    ["wmic", "csproduct", "get", "UUID"],
                    capture_output=True, text=True, timeout=2
                )
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                uid = lines[-1] if len(lines) >= 2 else ""
                if uid and uid != "UUID" and len(uid) > 10:
                    _MACHINE_ID_CACHE = hashlib.sha256(uid.encode()).hexdigest()[:32]
                    return _MACHINE_ID_CACHE
            except Exception:
                pass
        # Fallback: MAC + hostname
        mac  = hex(uuid.getnode())[2:].upper()
        host = platform.node()
        _MACHINE_ID_CACHE = hashlib.sha256(f"{mac}_{host}".encode()).hexdigest()[:32]
        return _MACHINE_ID_CACHE
    except Exception:
        _MACHINE_ID_CACHE = hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:32]
        return _MACHINE_ID_CACHE

def _hash_pass(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ── Session Token Storage (luu sau khi login thanh cong) ─────────
_SESSION_FILE = Path(__file__).parent / ".session_token"

def save_session_token(username: str, token: str):
    """Luu session_token sau khi login OK. Heartbeat se doc lai."""
    try:
        import base64
        data = {"u": username, "t": token, "saved": datetime.now().isoformat()}
        encoded = base64.b64encode(_json.dumps(data).encode()).decode()
        _SESSION_FILE.write_text(encoded, encoding="utf-8")
    except Exception:
        pass

def get_session_token(username: str) -> str:
    """Doc session_token tu file. Tra '' neu khong co hoac sai username."""
    try:
        if not _SESSION_FILE.exists():
            return ""
        import base64
        encoded = _SESSION_FILE.read_text(encoding="utf-8").strip()
        data = _json.loads(base64.b64decode(encoded).decode())
        if data.get("u") == username:
            return data.get("t", "")
    except Exception:
        pass
    return ""

def clear_session_token():
    """Xoa session_token (khi bi kick / logout)."""
    try:
        if _SESSION_FILE.exists():
            _SESSION_FILE.unlink()
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
_OFFLINE_CACHE = Path(__file__).parent / ".offline_auth"
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
        _OFFLINE_CACHE.write_text(encoded, encoding="utf-8")
    except Exception:
        pass

def verify_login_offline(username: str, password: str):
    try:
        if not _OFFLINE_CACHE.exists():
            return False, "Chưa có cache offline. Cần đăng nhập online ít nhất 1 lần."
        import base64
        encoded = _OFFLINE_CACHE.read_text(encoding="utf-8").strip()
        data    = _json.loads(base64.b64decode(encoded).decode())
        if data.get("mid") != get_machine_id():
            return False, "Cache không hợp lệ trên máy này."
        exp_dt = datetime.fromisoformat(data["exp"])
        if datetime.now() > exp_dt:
            return False, f"Cache offline đã hết hạn {exp_dt.strftime('%d/%m/%Y')}.\nKết nối internet và đăng nhập lại."
        if data.get("u") != username:
            return False, "Sai tên tài khoản (offline)."
        if data.get("p") != _hash_pass(password):
            return False, "Sai mật khẩu (offline)."
        days_left = (exp_dt - datetime.now()).days
        return True, data.get("msg", "Đăng nhập thành công!") + f" [Offline - còn {days_left} ngày]"
    except Exception as e:
        return False, f"Lỗi đọc cache: {e}"

def clear_offline_cache():
    try:
        if _OFFLINE_CACHE.exists():
            _OFFLINE_CACHE.unlink()
    except Exception:
        pass
