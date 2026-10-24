"""منصة الكوست كنترول — تطبيق Flask."""
import os
import secrets

from flask import Flask, g, render_template, request, url_for

from . import auth, db as dbmod, settings
from .audit import action_label, describe
from .avatars import PRESETS as AVATARS
from .boq import TYPES, fmt_qty
from .i18n import LANGS, _, current_lang
from .projects import fmt_money
from .rbac import ADMIN_AREA, can, can_any, role_label, roles

COMPACT_UNITS = ((1e9, "{n}B"), (1e6, "{n}M"), (1e3, "{n}K"))  # اختصار المبالغ الكبيرة في التحليلات

ERRORS = {  # الكود: (العنوان، الرسالة الافتراضية)
    400: ("Invalid request", "The request couldn't be processed."),
    403: ("Not allowed", "This action is outside your account's permissions."),
    404: ("Page not found", "The page you're looking for doesn't exist or was moved."),
    405: ("Not allowed", "This action is outside your account's permissions."),
    413: ("File too large", "The uploaded file is larger than the allowed size."),
    500: ("Something went wrong", "An unexpected error happened. Try again, and if it continues contact the admin."),
}


MONTHS = {
    "ar": ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
}
WEEKDAYS = {
    "ar": ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}


def today_label() -> str:
    """تاريخ اليوم بلغة الواجهة (توقيت السعودية): «السبت، 24 أكتوبر 2026»."""
    from datetime import datetime, timedelta, timezone
    d = datetime.now(timezone(timedelta(hours=3)))
    lang = current_lang()
    return f"{WEEKDAYS[lang][d.weekday()]}، {d.day} {MONTHS[lang][d.month - 1]} {d.year}" if lang == "ar" else \
        f"{WEEKDAYS[lang][d.weekday()]}, {d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        # DATABASE_URL (Postgres/Supabase) له الأولوية، وإلا ملف SQLite محلي
        DATABASE=(os.environ.get("DATABASE_URL")
                  or os.environ.get("CC_DATABASE", os.path.join(app.instance_path, "costcontrol.sqlite3"))),
        SECRET_KEY=os.environ.get("CC_SECRET_KEY") or secrets.token_hex(32),
        # القيم الافتراضية للجلسات؛ مدير النظام يغيّرها من صفحة الإعدادات
        SESSION_IDLE_MINUTES=int(os.environ.get("CC_SESSION_IDLE_MINUTES", "120")),
        SESSION_ABSOLUTE_HOURS=int(os.environ.get("CC_SESSION_ABSOLUTE_HOURS", "12")),
        SESSION_COOKIE_SECURE=os.environ.get("CC_COOKIE_SECURE", "1") == "1",
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if dbmod.is_postgres_url(app.config["DATABASE"]):
        # مع عدة نسخ (Vercel) كل نسخة لازم توقّع الكوكيز بنفس المفتاح
        if not os.environ.get("CC_SECRET_KEY") and not (test_config or {}).get("SECRET_KEY"):
            raise RuntimeError("CC_SECRET_KEY is required when using DATABASE_URL")
    else:
        os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)

    conn = dbmod.connect(app.config["DATABASE"])
    dbmod.migrate(conn)
    conn.close()

    if os.environ.get("CC_BEHIND_PROXY") == "1" or os.environ.get("VERCEL"):  # Vercel يضبط VERCEL=1 تلقائيًا
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(dbmod.close_db)
    app.before_request(auth.init_request)
    app.before_request(auth.check_csrf)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'")
        if request.endpoint != "static":
            resp.vary.add("Cookie")  # الصفحة تختلف حسب اللغة والحساب
        if g.get("user"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.context_processor
    def inject():
        lang = current_lang()
        return {
            "_": _,
            "lang": lang,
            "dir": LANGS[lang],
            "me": g.get("user"),
            "csrf": g.session["csrf_token"] if g.get("session") else "",
            "can": lambda perm: can(g.get("user"), perm),
            "admin_area": can_any(g.get("user"), ADMIN_AREA),
            "role_label": role_label,
            "ROLES": roles(),
            "money": fmt_money,
            "compact": compact,
            "qty": fmt_qty,
            "TYPES": TYPES,
            "type_label": lambda t: _(TYPES[t][0]) if t in TYPES else t,
            "action_label": action_label,
            "describe": describe,
            "AVATARS": AVATARS,
            "company": settings.company_name(),
            "platform": settings.platform_name(),
            "site": settings.current(),
            "today": today_label(),
        }

    # الملفات الثابتة تُخزَّن مؤقتًا لمدة طويلة، ورابطها يتغير مع كل تعديل (?v=) فلا تتأخر الصفحات ولا تظهر نسخ قديمة
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000
    versions = {}

    def asset(filename):
        if filename not in versions or app.debug:
            path = os.path.join(app.static_folder, filename)
            versions[filename] = int(os.path.getmtime(path)) if os.path.exists(path) else 0
        return url_for("static", filename=filename, v=versions[filename])

    app.jinja_env.globals["asset"] = asset

    @app.template_filter("first_name")
    def first_name(full):
        """الاسم الأول بدون الألقاب المختصرة مثل «م.» أو «Eng.»."""
        parts = [w for w in (full or "").split() if not w.endswith(".")]
        return parts[0] if parts else (full or "")

    def compact(h):
        """مبلغ بالهللة بصيغة مختصرة للعرض: 22.95M / 850K."""
        if h is None:
            return "—"
        v = h / 100
        for size, unit in COMPACT_UNITS:
            if abs(v) >= size:
                return _(unit, n=f"{v / size:.2f}".rstrip("0").rstrip("."))
        return f"{v:,.0f}"

    @app.template_filter("dt")
    def fmt_dt(v):
        return (v or "").replace("T", " ")[:16].replace("+00:00", "")

    def error_page(e):
        code = getattr(e, "code", 500) or 500
        title, default = ERRORS.get(code, ERRORS[500])
        # رسالة مخصصة من abort(..., description=...) وإلا الرسالة الافتراضية المترجمة
        custom = getattr(e, "description", None)
        message = custom if custom and custom != type(e).description else _(default)
        return render_template("error.html", code=code, title=_(title), message=message), code

    for code in ERRORS:
        app.register_error_handler(code, error_page)

    @app.get("/healthz")
    def healthz():
        return "ok", 200, {"Content-Type": "text/plain"}

    from .views import admin, auth_views, boq_views, main, registers
    app.register_blueprint(auth_views.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(boq_views.bp)
    app.register_blueprint(registers.bp)
    return app
