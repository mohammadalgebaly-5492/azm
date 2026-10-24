"""روابط التسجيل: الطريق الوحيد ليسجّل شخص حسابه بنفسه.

مفتاح عام (signup_enabled في الإعدادات) يوقف كل الروابط فورًا. كل رابط له دور ومدة صلاحية
وعدد استخدامات، ولا يمكن أن يمنح دور مدير النظام.
"""
import secrets
from datetime import datetime, timedelta, timezone

from . import audit, settings
from .auth import create_user, password_problems
from .db import tx, utcnow
from .errors import AuthError
from .i18n import _
from .rbac import OWNER, role_exists

DAYS = (1, 3, 7, 14, 30)
USES = (1, 5, 10, 25, 50)


def create(db, role: str, days, max_uses, note: str, actor_id: int) -> str:
    if role == OWNER or not role_exists(db, role):
        raise AuthError(_("Choose a role for this link."))
    days, max_uses = int(days or 0), int(max_uses or 0)
    if days not in DAYS or max_uses not in USES:
        raise AuthError(_("Choose how long the link lasts and how many people can use it."))
    token = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
    with tx(db):
        iid = db.execute("INSERT INTO invites(token, role, max_uses, note, expires_at, created_at, created_by) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
                         (token, role, max_uses, (note or "").strip()[:120] or None, expires, utcnow(), actor_id)).fetchone()[0]
        audit.log(db, actor_id, "invite_created", "invite", iid, role=role, max_uses=max_uses, expires_at=expires)
    return token


def active(db):
    return db.execute("SELECT i.*, u.full_name AS creator FROM invites i JOIN users u ON u.id = i.created_by "
                      "WHERE i.revoked_at IS NULL AND i.expires_at > ? AND i.uses < i.max_uses ORDER BY i.id DESC",
                      (utcnow(),)).fetchall()


def revoke(db, invite_id: int, actor_id: int):
    with tx(db):
        n = db.execute("UPDATE invites SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                       (utcnow(), invite_id)).rowcount
        if n:
            audit.log(db, actor_id, "invite_revoked", "invite", invite_id)


def set_enabled(db, enabled: bool, actor_id: int):
    settings.set_value(db, "signup_enabled", "1" if enabled else "0", actor_id)


def find_valid(db, token: str):
    """الرابط صالح فقط لو التسجيل مفعّل، والرابط غير ملغي ولا منتهٍ ولا مستنفد."""
    if not token or not settings.get("signup_enabled"):
        return None
    return db.execute("SELECT * FROM invites WHERE token = ? AND revoked_at IS NULL AND expires_at > ? AND uses < max_uses",
                      (token, utcnow())).fetchone()


def redeem(db, invite, form) -> int:
    username = (form.get("username") or "").strip().lower()
    pw = form.get("password") or ""
    if pw != (form.get("confirm_password") or ""):
        raise AuthError(_("The passwords don't match."))
    errs = password_problems(pw, username)
    if errs:
        raise AuthError(" ".join(errs))
    # حجز مكان في الرابط أولًا؛ لو فشل إنشاء الحساب يُرد الحجز
    with tx(db):
        if not db.execute("UPDATE invites SET uses = uses + 1 WHERE id = ? AND uses < max_uses AND revoked_at IS NULL",
                          (invite["id"],)).rowcount:
            raise AuthError(_("This sign-up link is no longer valid."))
    try:
        uid, _code, _pw = create_user(db, username=username, email=form.get("email"), full_name=form.get("full_name"),
                                      role=invite["role"], password=pw)
    except AuthError:
        db.execute("UPDATE invites SET uses = uses - 1 WHERE id = ?", (invite["id"],))
        raise
    audit.log(db, uid, "invite_used", "invite", invite["id"], user=username)
    return uid
