"""الحسابات: كلمات المرور، الدخول مع القفل، الجلسات على الخادم، و CSRF."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, current_app, g, redirect, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import audit
from .db import get_db, next_counter, tx, utcnow
from .rbac import ROLES, can, role_code

COOKIE = "cc_session"
MAX_FAILED = 5
LOCK_MINUTES = 15
GENERIC_LOGIN_ERROR = "اسم المستخدم أو كلمة المرور غير صحيحة."
TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


class AuthError(Exception):
    pass


# ---------- كلمات المرور ----------

def hash_password(pw: str) -> str:
    return generate_password_hash(pw, method="scrypt")


def verify_password(stored: str, pw: str) -> bool:
    return check_password_hash(stored, pw)


# يُستخدم لمقارنة زمنية ثابتة عند عدم وجود المستخدم، حتى لا يكشف الزمن وجود الحساب
_DUMMY_HASH = generate_password_hash("not-a-real-password-0", method="scrypt")


def password_problems(pw: str, username: str = "") -> list[str]:
    errs = []
    if len(pw) < 10:
        errs.append("كلمة المرور يجب ألا تقل عن 10 أحرف.")
    if not re.search(r"[A-Za-z؀-ۿ]", pw) or not re.search(r"\d", pw):
        errs.append("كلمة المرور يجب أن تحتوي على حروف وأرقام.")
    if username and username.lower() in pw.lower():
        errs.append("كلمة المرور يجب ألا تحتوي على اسم المستخدم.")
    return errs


def temp_password() -> str:
    while True:
        pw = "".join(secrets.choice(TEMP_ALPHABET) for _ in range(12))
        if not password_problems(pw):
            return pw


# ---------- إنشاء وإدارة الحسابات ----------

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_user(db, *, username, email, full_name, role, created_by=None, phone=None, job_title=None, password=None):
    """ينشئ حسابًا بكلمة مرور مؤقتة. يرجع (id, code, كلمة المرور المؤقتة)."""
    username = (username or "").strip().lower()
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()
    errs = []
    if not USERNAME_RE.match(username):
        errs.append("اسم المستخدم من 3 إلى 32 حرفًا لاتينيًا صغيرًا أو أرقام أو . _ -")
    if not EMAIL_RE.match(email):
        errs.append("البريد الإلكتروني غير صحيح.")
    if len(full_name) < 3:
        errs.append("أدخل الاسم الكامل.")
    if role not in ROLES:
        errs.append("الدور غير معروف.")
    if errs:
        raise AuthError(" ".join(errs))
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise AuthError("اسم المستخدم مستخدم بالفعل.")
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise AuthError("البريد الإلكتروني مسجل لحساب آخر.")
    pw = password or temp_password()
    with tx(db):
        n = next_counter(db, f"user-{role}")
        code = f"USR-{role_code(role)}-{n:02d}"
        cur = db.execute(
            "INSERT INTO users(code, username, email, full_name, role, password_hash, must_change_password, "
            "phone, job_title, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (code, username, email, full_name, role, hash_password(pw), not password,
             phone, job_title, utcnow(), created_by),
        )
        uid = cur.fetchone()[0]
        audit.log(db, created_by, "user_created", "user", uid, code=code, username=username, role=role)
    return uid, code, pw


def reset_password(db, user_id: int, actor_id: int) -> str:
    pw = temp_password()
    with tx(db):
        db.execute(
            "UPDATE users SET password_hash = ?, must_change_password = TRUE, failed_attempts = 0, locked_until = NULL "
            "WHERE id = ?", (hash_password(pw), user_id))
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        audit.log(db, actor_id, "password_reset", "user", user_id)
    return pw


def set_status(db, user_id: int, status: str, actor_id: int):
    if user_id == actor_id and status == "disabled":
        raise AuthError("لا يمكنك إيقاف حسابك.")
    target = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        raise AuthError("الحساب غير موجود.")
    if status == "disabled" and target["role"] == "admin" and _active_admins(db) <= 1:
        raise AuthError("لا يمكن إيقاف آخر حساب أدمن فعّال.")
    with tx(db):
        db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
        if status == "disabled":
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        audit.log(db, actor_id, "user_disabled" if status == "disabled" else "user_enabled", "user", user_id)


def update_user(db, user_id: int, actor_id: int, *, full_name, email, role, phone, job_title):
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("البريد الإلكتروني غير صحيح.")
    if role not in ROLES:
        raise AuthError("الدور غير معروف.")
    cur = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if cur is None:
        raise AuthError("الحساب غير موجود.")
    if db.execute("SELECT 1 FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone():
        raise AuthError("البريد الإلكتروني مسجل لحساب آخر.")
    if cur["role"] == "admin" and role != "admin" and cur["status"] == "active" and _active_admins(db) <= 1:
        raise AuthError("لا يمكن تغيير دور آخر حساب أدمن فعّال.")
    changes = {}
    for k, v in (("full_name", full_name.strip()), ("email", email), ("role", role),
                 ("phone", (phone or "").strip() or None), ("job_title", (job_title or "").strip() or None)):
        if cur[k] != v:
            changes[k] = v
    if not changes:
        return
    with tx(db):
        sets = ", ".join(f"{k} = ?" for k in changes)
        db.execute(f"UPDATE users SET {sets} WHERE id = ?", (*changes.values(), user_id))
        if "role" in changes:
            # الدور تغير: كود الحساب يبقى كما هو كمعرّف ثابت، والجلسات تُلغى لتطبيق الصلاحية الجديدة فورًا
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        audit.log(db, actor_id, "user_updated", "user", user_id,
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items()})


def _active_admins(db) -> int:
    return db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active'").fetchone()[0]


# ---------- الدخول والجلسات ----------

def _now():
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(db, username: str, password: str, ip=None, user_agent=None) -> str:
    """يرجع رمز الجلسة، أو يرفع AuthError برسالة عامة."""
    username = (username or "").strip().lower()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        verify_password(_DUMMY_HASH, password or "")
        raise AuthError(GENERIC_LOGIN_ERROR)
    if user["locked_until"] and datetime.fromisoformat(user["locked_until"]) > _now():
        verify_password(_DUMMY_HASH, password or "")
        raise AuthError(f"الحساب مقفول مؤقتًا بعد {MAX_FAILED} محاولات خاطئة. حاول بعد {LOCK_MINUTES} دقيقة أو تواصل مع الأدمن.")
    ok = verify_password(user["password_hash"], password or "")
    if not ok or user["status"] != "active":
        with tx(db):
            if not ok:
                fails = user["failed_attempts"] + 1
                locked = None
                if fails >= MAX_FAILED:
                    locked = (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
                    fails = 0
                db.execute("UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                           (fails, locked, user["id"]))
                audit.log(db, user["id"], "account_locked" if locked else "login_failed", "user", user["id"])
            else:
                audit.log(db, user["id"], "login_failed", "user", user["id"], reason="disabled")
        raise AuthError(GENERIC_LOGIN_ERROR)
    token = secrets.token_urlsafe(32)
    now = _now()
    absolute = now + timedelta(hours=current_app.config["SESSION_ABSOLUTE_HOURS"])
    with tx(db):
        db.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
                   (now.isoformat(timespec="seconds"), user["id"]))
        db.execute(
            "INSERT INTO sessions(token_hash, user_id, csrf_token, created_at, last_seen, expires_at, ip, user_agent) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (_hash_token(token), user["id"], secrets.token_urlsafe(24), now.isoformat(timespec="seconds"),
             now.isoformat(timespec="seconds"), absolute.isoformat(timespec="seconds"), ip, (user_agent or "")[:200]))
        audit.log(db, user["id"], "login", "user", user["id"])
    return token


def load_session(db, token: str | None):
    """يرجع (user, session) أو (None, None). يطبق انتهاء الخمول والانتهاء المطلق."""
    if not token:
        return None, None
    s = db.execute("SELECT * FROM sessions WHERE token_hash = ?", (_hash_token(token),)).fetchone()
    if s is None:
        return None, None
    now = _now()
    idle = timedelta(minutes=current_app.config["SESSION_IDLE_MINUTES"])
    if datetime.fromisoformat(s["expires_at"]) <= now or datetime.fromisoformat(s["last_seen"]) + idle <= now:
        db.execute("DELETE FROM sessions WHERE id = ?", (s["id"],))
        return None, None
    user = db.execute("SELECT * FROM users WHERE id = ?", (s["user_id"],)).fetchone()
    if user is None or user["status"] != "active":
        db.execute("DELETE FROM sessions WHERE id = ?", (s["id"],))
        return None, None
    if (now - datetime.fromisoformat(s["last_seen"])).total_seconds() > 60:
        db.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (now.isoformat(timespec="seconds"), s["id"]))
    return user, s


def logout(db, token: str | None, user_id=None):
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
    if user_id:
        audit.log(db, user_id, "logout", "user", user_id)


def change_password(db, user, current: str, new: str, keep_session_id: int):
    if not verify_password(user["password_hash"], current or ""):
        raise AuthError("كلمة المرور الحالية غير صحيحة.")
    errs = password_problems(new, user["username"])
    if verify_password(user["password_hash"], new):
        errs.append("اختر كلمة مرور مختلفة عن الحالية.")
    if errs:
        raise AuthError(" ".join(errs))
    with tx(db):
        db.execute("UPDATE users SET password_hash = ?, must_change_password = FALSE, password_changed_at = ? WHERE id = ?",
                   (hash_password(new), utcnow(), user["id"]))
        # إنهاء أي جلسة أخرى مفتوحة على أجهزة ثانية
        db.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user["id"], keep_session_id))
        audit.log(db, user["id"], "password_changed", "user", user["id"])


# ---------- ربط Flask ----------

def init_request():
    if request.endpoint == "static":  # الملفات الثابتة لا تحتاج جلسة ولا اتصالًا بقاعدة البيانات
        g.user = g.session = None
        return
    db = get_db()
    g.user, g.session = load_session(db, request.cookies.get(COOKIE))


def check_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.endpoint in ("auth.login", "auth.setup"):
            return  # لا جلسة قبل الدخول؛ الحماية هنا بـ SameSite=Strict على كوكي الجلسة
        sent = request.form.get("csrf_token", "")
        if g.session is None or not hmac.compare_digest(sent, g.session["csrf_token"]):
            abort(400, description="انتهت صلاحية النموذج. أعد تحميل الصفحة وحاول مرة أخرى.")


def set_session_cookie(resp, token: str):
    resp.set_cookie(COOKIE, token, httponly=True, secure=current_app.config["SESSION_COOKIE_SECURE"],
                    samesite="Strict", max_age=current_app.config["SESSION_ABSOLUTE_HOURS"] * 3600, path="/")
    return resp


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.user["must_change_password"] and request.endpoint not in ("auth.change_password", "auth.logout"):
            return redirect(url_for("auth.change_password"))
        return view(*a, **kw)
    return wrapped


def permission_required(perm: str):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(*a, **kw):
            if not can(g.user, perm):
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco
