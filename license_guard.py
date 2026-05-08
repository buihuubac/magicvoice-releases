"""
license_guard.py — Kiem tra license dua tren session_token cua auth_manager.
v3.4: Bo Google Apps Script, dung /check_session cua Render server
       -> Tu dong tuan theo logic slot 2 may single-active.

Logic:
  1. Doc session_token tu auth_manager (file .session_token).
  2. Goi /check_session de verify token con hop le.
     - kicked=true -> may khac da login -> tu choi ngay.
     - ok=true     -> luu cache 3 ngay.
  3. Mat mang -> dung cache offline (neu con hop le).
  4. Cache HMAC-signed, bind theo machine_id.

Trang thai fail-CLOSED: khong xac dinh duoc -> tu choi.
"""
from __future__ import annotations
import os, sys, json, time, hmac, hashlib
from pathlib import Path

# ══════════ ENDPOINTS ══════════
_API_URL = "https://magicvoice-update-1.onrender.com"
_API_KEY = "mv_secret_2025"

# ══════════ CONFIG ══════════
_CACHE_TTL_SEC     = 3 * 86400      # 3 ngay: offline toi da 3 ngay
_SESSION_CACHE_SEC = 300            # 5 phut: cache RAM giam tai server
_ONLINE_TIMEOUT    = 8              # 8s timeout khi goi /check_session
_CLOCK_FUTURE_OK   = 3600           # 1 gio tolerance cho clock

# ══════════ SECRET cho HMAC cache (giu de cache cu van read duoc) ══════════
_LIC_SECRET = "mv_lic_2025"

# ══════════ MACHINE ID ══════════
def _get_machine_id() -> str:
    """Lay machine_id tu auth_manager (cung 1 source -> bao dam dong bo)."""
    try:
        from auth_manager import get_machine_id
        mid = get_machine_id()
        if mid:
            return str(mid)
    except Exception:
        pass
    # Fallback
    try:
        import uuid, getpass
        return f"{uuid.getnode():x}_{getpass.getuser()}"
    except Exception:
        return "unknown"

# ══════════ CACHE PATH ══════════
def _cache_path() -> Path:
    """Cache o LOCALAPPDATA (Windows) hoac ~/.local/share (linux)."""
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
    """Derived key = SHA256(secret + machine_id). Moi may 1 key khac."""
    return hashlib.sha256((_LIC_SECRET + "|" + _get_machine_id()).encode()).digest()

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
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x02)  # HIDDEN
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

    required = ("user", "mid", "ts", "exp", "sig")
    if not all(k in d for k in required):
        return False, "malformed"

    sig_saved = d.pop("sig")
    if not hmac.compare_digest(_sign(d), sig_saved):
        return False, "sig_invalid"

    if d.get("user") != username:
        return False, "user_mismatch"

    if d.get("mid") != _get_machine_id():
        return False, "machine_mismatch"

    now = int(time.time())
    ts  = int(d.get("ts", 0))
    exp = int(d.get("exp", 0))
    if ts > now + _CLOCK_FUTURE_OK:
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
    """
    Goi /check_session cua Render server.
    Tra:
      (True,  msg)  -> session con hop le
      (False, msg)  -> bi kick / tai khoan invalid -> reject ngay
    Raise Exception neu network error -> fallback cache.
    """
    import requests
    try:
        from auth_manager import get_session_token
        token = get_session_token(username)
    except Exception as e:
        raise Exception(f"Cannot read session_token: {e}")

    if not token:
        # Chua login qua auth_manager -> khong co token de check
        # Tra (False, msg) -> reject (khong fallback cache)
        return False, "Chua dang nhap. Vui long dang nhap lai."

    r = requests.post(
        f"{_API_URL}/check_session",
        json={"username": username, "session_token": token},
        headers={"X-API-Key": _API_KEY},
        timeout=_ONLINE_TIMEOUT
    )
    d = r.json()

    if d.get("kicked"):
        return False, d.get("msg") or "Tai khoan da dang nhap tren may khac."

    if d.get("ok"):
        return True, d.get("msg", "")

    # ok=false, kicked=false -> loi server -> raise de fallback cache
    raise Exception(d.get("msg") or "Server error")

# ══════════ PUBLIC API ══════════
def verify_license(username: str):
    """
    Kiem tra license cho username. Tra (ok: bool, msg: str).

    Fail-CLOSED: neu khong xac dinh duoc license la hop le, TU CHOI.
    """
    if not username:
        return False, "Thieu thong tin dang nhap."

    # 0. Session cache RAM (5 phut) — tranh hit server moi lan gen voice
    if _session_ok(username):
        return True, ""

    # 1. Thu online qua /check_session
    online_ok = None
    online_msg = ""
    try:
        online_ok, online_msg = _check_online(username)
    except Exception:
        online_ok = None  # Network error -> fallback cache

    if online_ok is True:
        # Server xac nhan OK -> luu cache 3 ngay
        _save_cache(username, _CACHE_TTL_SEC)
        _session_set(username)
        return True, online_msg

    if online_ok is False:
        # Server tu choi ro rang (kicked / khong co token) -> reject + xoa cache
        clear_cache()
        return False, online_msg or "License khong hop le."

    # online_ok is None -> network error -> fallback cache offline
    ok, reason = _load_cache(username)
    if ok:
        _session_set(username, 60)  # cache RAM ngan hon (1 phut) khi offline
        return True, ""

    # Cache khong co hoac khong hop le -> TU CHOI
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
    """Xoa session cache RAM — goi khi chuyen tai khoan."""
    _session["user"]  = None
    _session["until"] = 0
