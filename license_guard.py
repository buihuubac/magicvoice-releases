"""
license_guard.py — Kiem tra license voi cache offline co ky HMAC.

Logic:
  1. Kiem tra online truoc (Google Apps Script) → neu OK, luu cache 3 ngay.
  2. Neu mang loi → dung cache offline (neu con hop le).
  3. Neu server tu choi ro rang → xoa cache, tu choi ngay.
  4. Clock tampering (tua gio) → invalidate cache.
  5. Cache bind theo machine_id → copy cache sang may khac khong chay duoc.

Trang thai "fail-open" cua ban cu da duoc bo — bay gio tat ca exception
khong xac dinh se tra ve (False, msg).
"""
from __future__ import annotations
import os, sys, json, time, hmac, hashlib, base64
from pathlib import Path

# ══════════ OBFUSCATED CONSTANTS ══════════
# Secret & URL duoc base64 encode de khong grep ra "mv_lic_2025" thang
_SEC_ENC = b"bXZfbGljXzIwMjU="
_URL_ENC = (b"aHR0cHM6Ly9zY3JpcHQuZ29vZ2xlLmNvbS9tYWNyb3Mvcy9BS2Z5Y2J4VE0w"
            b"VWt3UDZWSm1iRkpFOWM2cHlQXy1QQmluc1ZQZS1wendhNWxndHNhRFVDNUNx"
            b"a0pzam94SlljOTliLWJCY3UvZXhlYw==")

def _sec() -> str:
    return base64.b64decode(_SEC_ENC).decode("utf-8")

def _url() -> str:
    return base64.b64decode(_URL_ENC).decode("utf-8")

# ══════════ CONFIG ══════════
_CACHE_TTL_SEC     = 3 * 86400      # 3 ngay: offline toi da 3 ngay
_SESSION_CACHE_SEC = 300            # 5 phut: cache RAM giam tai server
_ONLINE_TIMEOUT    = 15             # 15s timeout khi goi server
_CLOCK_FUTURE_OK   = 3600           # 1 gio tolerance cho clock

# ══════════ MACHINE ID ══════════
def _get_machine_id() -> str:
    """Lay machine_id tu auth_manager (goi cung cach user hien tai dang lam)."""
    try:
        from auth_manager import get_machine_id
        mid = get_machine_id()
        if mid: return str(mid)
    except Exception:
        pass
    # Fallback: MAC address + username
    try:
        import uuid, getpass
        return f"{uuid.getnode():x}_{getpass.getuser()}"
    except Exception:
        return "unknown"

# ══════════ CACHE PATH ══════════
def _cache_path() -> Path:
    """Cache o LOCALAPPDATA (Windows) hoac ~/.local/share (linux).
    An duoi thu muc he thong → khach khong de y, khong de xoa."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~/.local/share")
    d = Path(base) / "MagicVoice"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = Path.home() / ".magicvoice"
        d.mkdir(parents=True, exist_ok=True)
    return d / ".lic_data"

# ══════════ SIGNING ══════════
def _derive_key() -> bytes:
    """Derived key = SHA256(secret + machine_id). Moi may 1 key khac nhau."""
    return hashlib.sha256((_sec() + "|" + _get_machine_id()).encode()).digest()

def _sign(payload: dict) -> str:
    """HMAC-SHA256 deterministic signature."""
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(_derive_key(), msg, hashlib.sha256).hexdigest()

# ══════════ CACHE I/O ══════════
def _save_cache(username: str, ttl: int = _CACHE_TTL_SEC) -> None:
    now = int(time.time())
    payload = {
        "user": username,
        "mid":  _get_machine_id(),
        "ts":   now,
        "exp":  now + ttl,
    }
    payload["sig"] = _sign({k: v for k, v in payload.items() if k != "sig"})
    try:
        p = _cache_path()
        p.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        # An file (Windows: hidden attribute)
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x02)  # FILE_ATTRIBUTE_HIDDEN
            except Exception:
                pass
    except Exception:
        pass

def _load_cache(username: str):
    """Return (ok: bool, reason: str)."""
    try:
        raw = _cache_path().read_text(encoding="utf-8")
        d = json.loads(raw)
    except Exception:
        return False, "no_cache"

    # 1. Kiem tra structure
    required = ("user", "mid", "ts", "exp", "sig")
    if not all(k in d for k in required):
        return False, "malformed"

    # 2. Verify HMAC signature (chong tampering)
    sig_saved = d.pop("sig")
    if not hmac.compare_digest(_sign(d), sig_saved):
        return False, "sig_invalid"

    # 3. Check user match
    if d.get("user") != username:
        return False, "user_mismatch"

    # 4. Check machine_id match (chong copy cache sang may khac)
    if d.get("mid") != _get_machine_id():
        return False, "machine_mismatch"

    # 5. Check clock tampering
    now = int(time.time())
    ts  = int(d.get("ts", 0))
    exp = int(d.get("exp", 0))
    if ts > now + _CLOCK_FUTURE_OK:
        # User tua gio may lui xuong sau khi cache → ts > now
        return False, "clock_tamper"
    if now > exp:
        return False, "expired"
    return True, ""

def clear_cache() -> None:
    """Xoa cache offline (goi khi logout hoac license bi revoke)."""
    try:
        _cache_path().unlink()
    except Exception:
        pass

# ══════════ SESSION CACHE (RAM) ══════════
_session = {"user": None, "until": 0}

def _session_ok(username: str) -> bool:
    return (_session["user"] == username
            and int(time.time()) < _session["until"])

def _session_set(username: str, secs: int = _SESSION_CACHE_SEC) -> None:
    _session["user"]  = username
    _session["until"] = int(time.time()) + secs

# ══════════ ONLINE CHECK ══════════
def _check_online(username: str):
    """Tra (ok, msg) hoac raise neu network error."""
    import requests
    mid = _get_machine_id()
    r = requests.post(_url(),
                      json={"username": username, "machine_id": mid, "secret": _sec()},
                      timeout=_ONLINE_TIMEOUT)
    d = r.json()
    return bool(d.get("ok", False)), str(d.get("msg", ""))

# ══════════ PUBLIC API ══════════
def verify_license(username: str):
    """
    Kiem tra license cho username. Tra (ok: bool, msg: str).

    Fail-CLOSED: neu khong xac dinh duoc license la hop le, TU CHOI.
    (Khac voi bo cu 'return True' khi loi.)
    """
    if not username:
        return False, "Thieu thong tin dang nhap."

    # 0. Session cache (5 phut) — tranh hit server moi lan gen voice
    if _session_ok(username):
        return True, ""

    # 1. Thu online
    online_ok = None; online_msg = ""
    try:
        online_ok, online_msg = _check_online(username)
    except Exception:
        online_ok = None  # Network error/timeout/JSON error → fallback cache

    if online_ok is True:
        # Server xac nhan OK → cap nhat cache 3 ngay
        _save_cache(username, _CACHE_TTL_SEC)
        _session_set(username)
        return True, online_msg

    if online_ok is False:
        # Server TU CHOI ro rang → xoa cache + tu choi ngay
        clear_cache()
        return False, online_msg or "License khong hop le."

    # online_ok is None → network error → fallback cache
    ok, reason = _load_cache(username)
    if ok:
        _session_set(username, 60)  # cache RAM ngan hon (1 phut) khi offline
        return True, ""

    # Cache khong co hoac khong hop le → TU CHOI
    reason_msg = {
        "no_cache":        "Chua verify online lan nao. Hay ket noi internet de kich hoat.",
        "expired":         "Cache offline da het han (3 ngay). Hay ket noi internet.",
        "sig_invalid":     "Cache bi chinh sua. Hay ket noi internet de verify lai.",
        "machine_mismatch":"Cache khong thuoc may nay. Hay ket noi internet.",
        "user_mismatch":   "Tai khoan khac lan truoc. Hay ket noi internet.",
        "clock_tamper":    "Dong ho he thong khong dung. Hay chinh lai va ket noi internet.",
        "malformed":       "Cache bi loi. Hay ket noi internet de verify lai.",
    }.get(reason, "Khong the verify license. Hay ket noi internet va thu lai.")
    return False, reason_msg

def invalidate_session():
    """Xoa session cache — goi khi chuyen tai khoan."""
    _session["user"]  = None
    _session["until"] = 0
