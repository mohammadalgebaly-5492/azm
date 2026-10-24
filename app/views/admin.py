from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import auth, projects as P
from ..auth import AuthError, permission_required
from ..db import get_db
from ..rbac import EXTERNAL, INTERNAL, ROLES

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _user_or_404(db, uid):
    u = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if u is None:
        abort(404)
    return u


# ---------- الحسابات ----------

@bp.get("/users")
@permission_required("users.manage")
def users():
    db = get_db()
    q = (request.args.get("q") or "").strip()
    role = request.args.get("role") or ""
    sql = ("SELECT u.*, (SELECT COUNT(*) FROM project_members m WHERE m.user_id = u.id) AS n_projects "
           "FROM users u WHERE 1=1")
    args = []
    if q:
        sql += (" AND (LOWER(u.full_name) LIKE ? OR LOWER(u.username) LIKE ? OR LOWER(u.email) LIKE ?"
                " OR LOWER(u.code) LIKE ?)")
        args += [f"%{q.lower()}%"] * 4
    if role in ROLES:
        sql += " AND u.role = ?"
        args.append(role)
    sql += " ORDER BY u.status, u.role, u.code"
    return render_template("admin/users.html", users=db.execute(sql, args).fetchall(), q=q, role=role,
                           INTERNAL=INTERNAL, EXTERNAL=EXTERNAL)


@bp.route("/users/new", methods=["GET", "POST"])
@permission_required("users.manage")
def user_new():
    db = get_db()
    plist = db.execute("SELECT id, code, name FROM projects WHERE status != 'closed' ORDER BY code").fetchall()
    error = None
    if request.method == "POST":
        f = request.form
        try:
            uid, code, pw = auth.create_user(
                db, username=f.get("username"), email=f.get("email"), full_name=f.get("full_name"),
                role=f.get("role"), phone=f.get("phone"), job_title=f.get("job_title"), created_by=g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            for pid in request.form.getlist("projects"):
                if pid.isdigit():
                    P.add_member(db, int(pid), uid, g.user["id"])
            u = _user_or_404(db, uid)
            return render_template("admin/credentials.html", u=u, password=pw, created=True,
                                   login_url=url_for("auth.login", _external=True))
    return render_template("admin/user_form.html", u=None, projects=plist, error=error, form=request.form,
                           INTERNAL=INTERNAL, EXTERNAL=EXTERNAL, assigned=set())


@bp.route("/users/<int:uid>", methods=["GET", "POST"])
@permission_required("users.manage")
def user_edit(uid):
    db = get_db()
    u = _user_or_404(db, uid)
    plist = db.execute("SELECT id, code, name FROM projects WHERE status != 'closed' ORDER BY code").fetchall()
    assigned = {r[0] for r in db.execute("SELECT project_id FROM project_members WHERE user_id = ?", (uid,))}
    error = None
    if request.method == "POST":
        f = request.form
        try:
            auth.update_user(db, uid, g.user["id"], full_name=f.get("full_name", ""), email=f.get("email"),
                             role=f.get("role"), phone=f.get("phone"), job_title=f.get("job_title"))
            want = {int(p) for p in f.getlist("projects") if p.isdigit()}
            open_ids = {p["id"] for p in plist}
            for pid in (want - assigned) & open_ids:
                P.add_member(db, pid, uid, g.user["id"])
            for pid in (assigned - want) & open_ids:
                P.remove_member(db, pid, uid, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash("تم حفظ الحساب.", "ok")
            return redirect(url_for("admin.user_edit", uid=uid))
    log = db.execute(
        "SELECT a.*, u.full_name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
        "WHERE (a.entity = 'user' AND a.entity_id = ?) ORDER BY a.id DESC LIMIT 25", (uid,)).fetchall()
    return render_template("admin/user_form.html", u=u, projects=plist, error=error, form=request.form if error else dict(u),
                           INTERNAL=INTERNAL, EXTERNAL=EXTERNAL, assigned=assigned, log=log)


@bp.post("/users/<int:uid>/reset")
@permission_required("users.manage")
def user_reset(uid):
    db = get_db()
    u = _user_or_404(db, uid)
    pw = auth.reset_password(db, uid, g.user["id"])
    return render_template("admin/credentials.html", u=u, password=pw, created=False,
                           login_url=url_for("auth.login", _external=True))


@bp.post("/users/<int:uid>/status")
@permission_required("users.manage")
def user_status(uid):
    db = get_db()
    _user_or_404(db, uid)
    status = request.form.get("status")
    if status not in ("active", "disabled"):
        abort(400)
    try:
        auth.set_status(db, uid, status, g.user["id"])
    except AuthError as e:
        flash(str(e), "bad")
    else:
        flash("تم إيقاف الحساب وإنهاء جلساته." if status == "disabled" else "تمت إعادة تفعيل الحساب.", "ok")
    return redirect(url_for("admin.user_edit", uid=uid))


# ---------- المشروعات ----------

@bp.route("/projects/new", methods=["GET", "POST"])
@permission_required("projects.create")
def project_new():
    error = None
    if request.method == "POST":
        try:
            pid, code = P.create_project(get_db(), request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(f"تم إنشاء المشروع {code}. أسند الطاقم الآن.", "ok")
            return redirect(url_for("main.project", pid=pid))
    return render_template("admin/project_form.html", p=None, form=request.form, error=error)


@bp.route("/projects/<int:pid>/edit", methods=["GET", "POST"])
@permission_required("projects.manage")
def project_edit(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            P.update_project(db, pid, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash("تم حفظ بيانات المشروع.", "ok")
            return redirect(url_for("main.project", pid=pid))
    form = request.form if error else dict(p, contract_value=P.fmt_money(p["contract_value"]).replace(",", "")
                                           if p["contract_value"] is not None else "")
    return render_template("admin/project_form.html", p=p, form=form, error=error)


@bp.post("/projects/<int:pid>/members")
@permission_required("projects.manage")
def project_members(pid):
    db = get_db()
    if db.execute("SELECT 1 FROM projects WHERE id = ?", (pid,)).fetchone() is None:
        abort(404)
    uid = request.form.get("user_id", "")
    if not uid.isdigit():
        abort(400)
    try:
        if request.form.get("op") == "remove":
            P.remove_member(db, pid, int(uid), g.user["id"])
            flash("أُزيل العضو من المشروع.", "ok")
        else:
            P.add_member(db, pid, int(uid), g.user["id"])
            flash("أُسند العضو للمشروع.", "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("main.project", pid=pid) + "#team")


# ---------- السجل ----------

@bp.get("/audit")
@permission_required("audit.view")
def audit_log():
    db = get_db()
    rows = db.execute(
        "SELECT a.*, u.full_name AS actor, u.code AS actor_code, p.code AS project_code FROM audit_log a "
        "LEFT JOIN users u ON u.id = a.actor_id LEFT JOIN projects p ON p.id = a.project_id "
        "ORDER BY a.id DESC LIMIT 500").fetchall()
    return render_template("admin/audit.html", rows=rows)
