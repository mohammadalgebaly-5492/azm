import hmac
import os

from flask import Blueprint, abort, flash, g, make_response, redirect, render_template, request, url_for

from .. import auth
from ..db import get_db

bp = Blueprint("auth", __name__)


def _safe_next(n):
    return n if n and n.startswith("/") and not n.startswith("//") else url_for("main.home")


def _has_admin(db):
    return db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone() is not None


def _setup_allowed():
    """الإعداد الأول مسموح فقط قبل وجود أي أدمن، ومن نفس الجهاز أو بالرمز السري CC_SETUP_TOKEN."""
    token = os.environ.get("CC_SETUP_TOKEN", "")
    sent = request.values.get("token", "")
    if token and sent and hmac.compare_digest(sent, token):
        return True
    return request.remote_addr in ("127.0.0.1", "::1")


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    db = get_db()
    if _has_admin(db):
        return redirect(url_for("auth.login"))
    if not _setup_allowed():
        abort(403, description="الإعداد الأول يتم من نفس السيرفر أو برابط الإعداد السري.")
    error = None
    f = request.form
    if request.method == "POST":
        if f.get("password", "") != f.get("confirm_password", ""):
            error = "كلمتا المرور غير متطابقتين."
        else:
            errs = auth.password_problems(f.get("password", ""), (f.get("username") or "").strip().lower())
            if errs:
                error = " ".join(errs)
        if not error:
            try:
                auth.create_user(db, username=f.get("username"), email=f.get("email"), full_name=f.get("full_name"),
                                 role="admin", job_title=f.get("job_title") or "مهندس كوست كنترول",
                                 password=f.get("password"))
                token = auth.login(db, f.get("username"), f.get("password"), ip=request.remote_addr,
                                   user_agent=request.headers.get("User-Agent"))
            except auth.AuthError as e:
                error = str(e)
            else:
                flash("تم إنشاء حساب الأدمن. ابدأ بإنشاء أول مشروع أو حسابات الفريق.", "ok")
                return auth.set_session_cookie(make_response(redirect(url_for("main.home"))), token)
    return render_template("setup.html", error=error, form=f, token=request.values.get("token", ""))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("main.home"))
    if not _has_admin(get_db()):
        return redirect(url_for("auth.setup"))
    error = None
    if request.method == "POST":
        try:
            token = auth.login(get_db(), request.form.get("username"), request.form.get("password"),
                               ip=request.remote_addr, user_agent=request.headers.get("User-Agent"))
        except auth.AuthError as e:
            error = str(e)
        else:
            resp = make_response(redirect(_safe_next(request.args.get("next"))))
            return auth.set_session_cookie(resp, token)
    return render_template("login.html", error=error, username=request.form.get("username", "")), (401 if error else 200)


@bp.post("/logout")
def logout():
    auth.logout(get_db(), request.cookies.get(auth.COOKIE), g.user["id"] if g.get("user") else None)
    resp = make_response(redirect(url_for("auth.login")))
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@bp.route("/account/password", methods=["GET", "POST"])
@auth.login_required
def change_password():
    error = None
    if request.method == "POST":
        new, confirm = request.form.get("new_password", ""), request.form.get("confirm_password", "")
        if new != confirm:
            error = "كلمتا المرور الجديدتان غير متطابقتين."
        else:
            try:
                auth.change_password(get_db(), g.user, request.form.get("current_password", ""), new, g.session["id"])
            except auth.AuthError as e:
                error = str(e)
            else:
                flash("تم تغيير كلمة المرور.", "ok")
                return redirect(url_for("main.home"))
    return render_template("change_password.html", error=error, forced=bool(g.user["must_change_password"]))
