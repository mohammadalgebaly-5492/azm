"""منصة الكوست كنترول — تطبيق Flask."""
import os
import secrets

from flask import Flask, g, render_template

from . import auth, db as dbmod
from .audit import ACTION_LABELS
from .boq import TYPES, fmt_qty
from .projects import fmt_money
from .rbac import ROLES, can, role_label


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        DATABASE=os.environ.get("CC_DATABASE", os.path.join(app.instance_path, "costcontrol.sqlite3")),
        SECRET_KEY=os.environ.get("CC_SECRET_KEY") or secrets.token_hex(32),
        SESSION_IDLE_MINUTES=int(os.environ.get("CC_SESSION_IDLE_MINUTES", "120")),
        SESSION_ABSOLUTE_HOURS=int(os.environ.get("CC_SESSION_ABSOLUTE_HOURS", "12")),
        SESSION_COOKIE_SECURE=os.environ.get("CC_COOKIE_SECURE", "1") == "1",
        COMPANY_NAME=os.environ.get("CC_COMPANY_NAME", "الإنماء الحر للمقاولات"),
        PLATFORM_NAME=os.environ.get("CC_PLATFORM_NAME", "عزم"),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)

    conn = dbmod.connect(app.config["DATABASE"])
    dbmod.migrate(conn)
    conn.close()

    if os.environ.get("CC_BEHIND_PROXY") == "1":
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
        if g.get("user"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def inject():
        return {
            "me": g.get("user"),
            "csrf": g.session["csrf_token"] if g.get("session") else "",
            "can": lambda perm: can(g.get("user"), perm),
            "role_label": role_label,
            "ROLES": ROLES,
            "money": fmt_money,
            "qty": fmt_qty,
            "TYPES": TYPES,
            "action_label": lambda a: ACTION_LABELS.get(a, a),
            "company": app.config["COMPANY_NAME"],
            "platform": app.config["PLATFORM_NAME"],
        }

    @app.template_filter("dt")
    def fmt_dt(v):
        return (v or "").replace("T", " ")[:16].replace("+00:00", "")

    for code, title in ((400, "طلب غير صالح"), (403, "غير مسموح"), (404, "الصفحة غير موجودة")):
        app.register_error_handler(code, lambda e, c=code, t=title: (
            render_template("error.html", code=c, title=t, message=getattr(e, "description", "")), c))

    @app.get("/healthz")
    def healthz():
        return "ok", 200, {"Content-Type": "text/plain"}

    from .views import admin, auth_views, boq_views, main
    app.register_blueprint(auth_views.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(boq_views.bp)
    return app
