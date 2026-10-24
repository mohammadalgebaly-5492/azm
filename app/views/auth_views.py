import hmac
import os

from flask import Blueprint, abort, flash, g, make_response, redirect, render_template, request, url_for

from .. import auth, i18n, invites as I
from ..db import get_db
from ..i18n import _
from ..rbac import OWNER

bp = Blueprint("auth", __name__)


def _safe_next(n):
    return n if n and n.startswith("/") and not n.startswith("//") else url_for("main.home")


def _has_accounts(db):
    """الإعداد الأول للمنصة الفارغة فقط؛ بعد أول حساب تُنشأ الحسابات من داخل المنصة."""
    return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def _setup_allowed():
    """الإعداد الأول مسموح فقط قبل وجود أي حساب إداري، ومن نفس الجهاز أو بالرمز السري CC_SETUP_TOKEN."""
    token = os.environ.get("CC_SETUP_TOKEN", "")
    sent = request.values.get("token", "")
    if token and sent and hmac.compare_digest(sent, token):
        return True
    return request.remote_addr in ("127.0.0.1", "::1")


@bp.get("/lang/<code>")
def set_lang(code):
    return i18n.switch(code, _safe_next(request.args.get("next")))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    db = get_db()
    if _has_accounts(db):
        return redirect(url_for("auth.login"))
    if not _setup_allowed():
        abort(403, description=_("First-time setup only works from the server itself or with the secret setup link."))
    error = None
    f = request.form
    if request.method == "POST":
        if f.get("password", "") != f.get("confirm_password", ""):
            error = _("The passwords don't match.")
        else:
            errs = auth.password_problems(f.get("password", ""), (f.get("username") or "").strip().lower())
            if errs:
                error = " ".join(errs)
        if not error:
            try:
                auth.create_user(db, username=f.get("username"), email=f.get("email"), full_name=f.get("full_name"),
                                 role=OWNER, job_title=f.get("job_title") or None, password=f.get("password"))
                token = auth.login(db, f.get("username"), f.get("password"), ip=request.remote_addr,
                                   user_agent=request.headers.get("User-Agent"))
            except auth.AuthError as e:
                error = str(e)
            else:
                flash(_("Your System Owner account is ready. Start by creating the team's accounts or the first "
                        "project."), "ok")
                return auth.set_session_cookie(make_response(redirect(url_for("main.home"))), token)
    return render_template("setup.html", error=error, form=f, token=request.values.get("token", ""))


@bp.route("/join/<token>", methods=["GET", "POST"])
def join(token):
    """التسجيل برابط دعوة. بدون رابط صالح لا يوجد تسجيل ذاتي على المنصة."""
    if g.get("user"):
        return redirect(url_for("main.home"))
    db = get_db()
    invite = I.find_valid(db, token)
    if invite is None:
        abort(404, description=_("This sign-up link is no longer valid. Ask the platform administrator for a new one."))
    error = None
    if request.method == "POST":
        try:
            I.redeem(db, invite, request.form)
            session_token = auth.login(db, request.form.get("username"), request.form.get("password"),
                                       ip=request.remote_addr, user_agent=request.headers.get("User-Agent"))
        except auth.AuthError as e:
            error = str(e)
        else:
            flash(_("Welcome. Your account is ready."), "ok")
            return auth.set_session_cookie(make_response(redirect(url_for("main.home"))), session_token)
    return render_template("join.html", invite=invite, error=error, form=request.form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("main.home"))
    if not _has_accounts(get_db()):
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
            error = _("The new passwords don't match.")
        else:
            try:
                auth.change_password(get_db(), g.user, request.form.get("current_password", ""), new, g.session["id"])
            except auth.AuthError as e:
                error = str(e)
            else:
                flash(_("Your password has been changed."), "ok")
                return redirect(url_for("main.home"))
    return render_template("change_password.html", error=error, forced=bool(g.user["must_change_password"]))
