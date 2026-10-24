"""إعدادات المنصة: يعدّلها مدير النظام من الواجهة، وتُحفظ في جدول settings.

أي إعداد غير محفوظ يأخذ قيمته الافتراضية من DEFAULTS (أو من متغيرات البيئة للجلسات).
"""
from flask import current_app, g, has_request_context

from . import audit
from .db import tx, utcnow
from .errors import AuthError
from .i18n import _, current_lang

TEXT_KEYS = ("platform_name_ar", "platform_name_en", "company_name_ar", "company_name_en")
BOOL_KEYS = ("signup_enabled",)
INT_KEYS = {  # المفتاح: (أقل قيمة، أكبر قيمة)
    "session_idle_minutes": (5, 24 * 60),
    "session_absolute_hours": (1, 7 * 24),
}


def defaults() -> dict:
    cfg = current_app.config
    return {
        "platform_name_ar": "عزم",
        "platform_name_en": "AZM",
        "company_name_ar": "الإنماء الحر للمقاولات",
        "company_name_en": "Alenmaa Alhor Construction",
        "session_idle_minutes": cfg["SESSION_IDLE_MINUTES"],
        "session_absolute_hours": cfg["SESSION_ABSOLUTE_HOURS"],
        "signup_enabled": False,
    }


def load(db) -> dict:
    values = defaults()
    for key, value in db.execute("SELECT key, value FROM settings"):
        if key in TEXT_KEYS:
            values[key] = value
        elif key in INT_KEYS:
            values[key] = int(value)
        elif key in BOOL_KEYS:
            values[key] = value == "1"
    return values


def current() -> dict:
    """إعدادات الطلب الحالي (تُقرأ من قاعدة البيانات مرة واحدة لكل طلب)."""
    if not has_request_context():
        return defaults()
    if "settings" not in g:
        from .db import get_db
        g.settings = load(get_db())
    return g.settings


def get(key: str):
    return current()[key]


def platform_name() -> str:
    return get(f"platform_name_{current_lang()}")


def company_name() -> str:
    return get(f"company_name_{current_lang()}")


def set_value(db, key: str, value: str, actor_id: int):
    old = load(db)[key]
    with tx(db):
        db.execute("INSERT INTO settings(key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, "
                   "updated_by = excluded.updated_by", (key, value, utcnow(), actor_id))
        audit.log(db, actor_id, "settings_updated", "settings", None, **{key: {"from": old, "to": value == "1" if key in BOOL_KEYS else value}})
    g.pop("settings", None)


def save(db, form, actor_id: int) -> int:
    old = load(db)
    new = {}
    for key in TEXT_KEYS:
        v = (form.get(key) or "").strip()
        if not v or len(v) > 80:
            raise AuthError(_("Names must be between 1 and 80 characters."))
        new[key] = v
    for key, (lo, hi) in INT_KEYS.items():
        try:
            v = int(str(form.get(key) or "").strip())
        except ValueError:
            raise AuthError(_("Session limits must be whole numbers."))
        if not lo <= v <= hi:
            raise AuthError(_("Session limits are out of the allowed range."))
        new[key] = v
    if new["session_idle_minutes"] > new["session_absolute_hours"] * 60:
        raise AuthError(_("The idle timeout can't be longer than the maximum session length."))
    changes = {k: v for k, v in new.items() if old[k] != v}
    if not changes:
        return 0
    now = utcnow()
    with tx(db):
        for k, v in changes.items():
            db.execute("INSERT INTO settings(key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, "
                       "updated_by = excluded.updated_by", (k, str(v), now, actor_id))
        audit.log(db, actor_id, "settings_updated", "settings", None,
                  **{k: {"from": old[k], "to": v} for k, v in changes.items()})
    g.pop("settings", None)
    return len(changes)
