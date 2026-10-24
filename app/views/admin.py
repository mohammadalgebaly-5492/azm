from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import auth, invites as I, projects as P, settings
from ..auth import AuthError, permission_required
from ..db import get_db, utcnow
from ..i18n import _
from .. import rbac
from ..rbac import ADMIN_AREA, OWNER, PERMISSION_GROUPS, PERMISSIONS, can, can_any, load_role_permissions

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _user_or_404(db, uid):
    u = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if u is None:
        abort(404)
    return u


def _guard_owner_account(u):
    """حسابات مدير النظام يديرها مدير النظام فقط."""
    if u["role"] == OWNER and not can(g.user, "users.manage_owners"):
        abort(403)


def _check_role_allowed(role):
    if role == OWNER and not can(g.user, "users.manage_owners"):
        raise AuthError(_("Only a System Owner can give the System Owner role."))


def _role_options():
    internal = [r for r in rbac.internal_roles() if r != OWNER or can(g.user, "users.manage_owners")]
    return internal, rbac.external_roles()


def _active_sessions_query(extra=""):
    now = datetime.now(timezone.utc)
    idle_cutoff = (now - timedelta(minutes=settings.get("session_idle_minutes"))).isoformat(timespec="seconds")
    return (f"FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.expires_at > ? AND s.last_seen > ? {extra}",
            [now.isoformat(timespec="seconds"), idle_cutoff])


def device_label(ua: str | None) -> str:
    ua = ua or ""
    browser = next((b for k, b in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"), ("Firefox/", "Firefox"),
                                   ("Safari/", "Safari")) if k in ua), _("Browser"))
    system = next((s for k, s in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                  ("Windows", "Windows"), ("Mac OS", "macOS"), ("Linux", "Linux")) if k in ua), "")
    return f"{browser} · {system}" if system else browser


# ---------- لوحة الإدارة ----------

@bp.get("")
@auth.login_required
def console():
    if not can_any(g.user, ADMIN_AREA):
        abort(403)
    db = get_db()
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0]
    sql, args = _active_sessions_query()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    stats = {
        "users": one("SELECT COUNT(*) FROM users WHERE status = 'active'"),
        "disabled": one("SELECT COUNT(*) FROM users WHERE status = 'disabled'"),
        "pending": one("SELECT COUNT(*) FROM users WHERE status = 'active' AND must_change_password = TRUE"),
        "locked": one("SELECT COUNT(*) FROM users WHERE locked_until > ?", utcnow()),
        "sessions": db.execute(f"SELECT COUNT(*) {sql}", args).fetchone()[0],
        "failed_24h": one("SELECT COUNT(*) FROM audit_log WHERE action IN ('login_failed', 'account_locked') AND at > ?",
                          since),
        "projects": one("SELECT COUNT(*) FROM projects"),
        "projects_active": one("SELECT COUNT(*) FROM projects WHERE status = 'active'"),
    }
    by_role = {r: n for r, n in db.execute(
        "SELECT role, COUNT(*) FROM users WHERE status = 'active' GROUP BY role")}
    recent = db.execute(
        "SELECT a.*, u.full_name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
        "ORDER BY a.id DESC LIMIT 12").fetchall()
    return render_template("admin/console.html", stats=stats, by_role=by_role, recent=recent)


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
    if role in rbac.roles():
        sql += " AND u.role = ?"
        args.append(role)
    sql += " ORDER BY u.status, u.role, u.code"
    return render_template("admin/users.html", users=db.execute(sql, args).fetchall(), q=q, role=role,
                           EXTERNAL=rbac.external_roles())


@bp.route("/users/new", methods=["GET", "POST"])
@permission_required("users.manage")
def user_new():
    db = get_db()
    plist = db.execute("SELECT id, code, name FROM projects WHERE status != 'closed' ORDER BY code").fetchall()
    error = None
    if request.method == "POST":
        f = request.form
        try:
            _check_role_allowed(f.get("role"))
            uid, code, pw = auth.create_user(
                db, username=f.get("username"), email=f.get("email"), full_name=f.get("full_name"),
                role=f.get("role"), phone=f.get("phone"), job_title=f.get("job_title"), created_by=g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            open_ids = {p["id"] for p in plist}
            for pid in request.form.getlist("projects"):
                if pid.isdigit() and int(pid) in open_ids:
                    P.add_member(db, int(pid), uid, g.user["id"])
            u = _user_or_404(db, uid)
            return render_template("admin/credentials.html", u=u, password=pw, created=True,
                                   login_url=url_for("auth.login", _external=True))
    internal, external = _role_options()
    return render_template("admin/user_form.html", u=None, projects=plist, error=error, form=request.form,
                           INTERNAL=internal, EXTERNAL=external, assigned=set())


@bp.route("/users/<int:uid>", methods=["GET", "POST"])
@permission_required("users.manage")
def user_edit(uid):
    db = get_db()
    u = _user_or_404(db, uid)
    _guard_owner_account(u)
    plist = db.execute("SELECT id, code, name FROM projects WHERE status != 'closed' ORDER BY code").fetchall()
    assigned = {r[0] for r in db.execute("SELECT project_id FROM project_members WHERE user_id = ?", (uid,))}
    error = None
    if request.method == "POST":
        f = request.form
        try:
            _check_role_allowed(f.get("role"))
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
            flash(_("Account saved."), "ok")
            return redirect(url_for("admin.user_edit", uid=uid))
    log = db.execute(
        "SELECT a.*, u.full_name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
        "WHERE (a.entity = 'user' AND a.entity_id = ?) ORDER BY a.id DESC LIMIT 25", (uid,)).fetchall()
    internal, external = _role_options()
    return render_template("admin/user_form.html", u=u, projects=plist, error=error,
                           form=request.form if error else dict(u), INTERNAL=internal, EXTERNAL=external,
                           assigned=assigned, log=log)


@bp.post("/users/<int:uid>/reset")
@permission_required("users.manage")
def user_reset(uid):
    db = get_db()
    u = _user_or_404(db, uid)
    _guard_owner_account(u)
    pw = auth.reset_password(db, uid, g.user["id"])
    return render_template("admin/credentials.html", u=u, password=pw, created=False,
                           login_url=url_for("auth.login", _external=True))


@bp.post("/users/<int:uid>/status")
@permission_required("users.manage")
def user_status(uid):
    db = get_db()
    _guard_owner_account(_user_or_404(db, uid))
    status = request.form.get("status")
    if status not in ("active", "disabled"):
        abort(400)
    try:
        auth.set_status(db, uid, status, g.user["id"])
    except AuthError as e:
        flash(str(e), "bad")
    else:
        flash(_("The account is disabled and its sessions have ended.") if status == "disabled"
              else _("The account is active again."), "ok")
    return redirect(url_for("admin.user_edit", uid=uid))


# ---------- الأدوار والصلاحيات ----------

@bp.get("/roles")
@permission_required("roles.manage")
def roles():
    db = get_db()
    counts = {r: n for r, n in db.execute("SELECT role, COUNT(*) FROM users GROUP BY role")}
    return render_template("admin/roles.html", roles=rbac.roles(db), counts=counts, perms=load_role_permissions(db),
                           n_perms=len(PERMISSIONS))


@bp.route("/roles/new", methods=["GET", "POST"])
@permission_required("roles.manage")
def role_new():
    db = get_db()
    error = None
    if request.method == "POST":
        try:
            key = rbac.create_role(db, request.form, g.user["id"])
            rbac.save_role_permissions(db, key, set(request.form.getlist("perm")), g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Role created."), "ok")
            return redirect(url_for("admin.roles"))
    return render_template("admin/role_form.html", r=None, form=request.form, error=error,
                           granted=set(request.form.getlist("perm")), PERMISSIONS=PERMISSIONS, GROUPS=PERMISSION_GROUPS, n_users=0)


@bp.route("/roles/<key>", methods=["GET", "POST"])
@permission_required("roles.manage")
def role_edit(key):
    db = get_db()
    r = rbac.roles(db).get(key)
    if r is None:
        abort(404)
    error = None
    if request.method == "POST":
        if r["system"]:
            abort(403)
        try:
            rbac.update_role(db, key, request.form, g.user["id"])
            rbac.save_role_permissions(db, key, set(request.form.getlist("perm")), g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Role saved."), "ok")
            return redirect(url_for("admin.roles"))
    granted = set(PERMISSIONS) if r["system"] else load_role_permissions(db).get(key, set())
    n_users = db.execute("SELECT COUNT(*) FROM users WHERE role = ?", (key,)).fetchone()[0]
    return render_template("admin/role_form.html", r=r, form=request.form if error else dict(r), error=error,
                           granted=set(request.form.getlist("perm")) if error else granted,
                           PERMISSIONS=PERMISSIONS, GROUPS=PERMISSION_GROUPS, n_users=n_users)


@bp.post("/roles/<key>/delete")
@permission_required("roles.manage")
def role_delete(key):
    try:
        rbac.delete_role(get_db(), key, g.user["id"])
    except AuthError as e:
        flash(str(e), "bad")
        return redirect(url_for("admin.role_edit", key=key))
    flash(_("Role deleted."), "ok")
    return redirect(url_for("admin.roles"))


# ---------- روابط التسجيل ----------

@bp.get("/invites")
@permission_required("admin.invites")
def invites():
    db = get_db()
    roles = [k for k in rbac.roles(db) if k != OWNER]
    return render_template("admin/invites.html", rows=I.active(db), roles=roles, DAYS=I.DAYS, USES=I.USES,
                           new_link=request.args.get("new"))


@bp.post("/invites")
@permission_required("admin.invites")
def invite_create():
    f = request.form
    try:
        token = I.create(get_db(), f.get("role"), f.get("days"), f.get("max_uses"), f.get("note"), g.user["id"])
    except AuthError as e:
        flash(str(e), "bad")
        return redirect(url_for("admin.invites"))
    flash(_("Sign-up link created. Copy it and send it to the person."), "ok")
    return redirect(url_for("admin.invites", new=token))


@bp.post("/invites/<int:iid>/revoke")
@permission_required("admin.invites")
def invite_revoke(iid):
    I.revoke(get_db(), iid, g.user["id"])
    flash(_("Sign-up link revoked."), "ok")
    return redirect(url_for("admin.invites"))


@bp.post("/invites/toggle")
@permission_required("admin.invites")
def invites_toggle():
    on = request.form.get("enabled") == "1"
    I.set_enabled(get_db(), on, g.user["id"])
    flash(_("Sign-up links are on.") if on else _("Sign-up links are off. No link works until you turn them on."), "ok")
    return redirect(url_for("admin.invites"))


# ---------- الجلسات ----------

@bp.get("/sessions")
@permission_required("admin.sessions")
def sessions():
    db = get_db()
    sql, args = _active_sessions_query()
    rows = db.execute(f"SELECT s.id AS sid, s.created_at, s.last_seen, s.ip, s.user_agent, u.id, u.full_name, "
                      f"u.code, u.role, u.avatar {sql} ORDER BY s.last_seen DESC", args).fetchall()
    return render_template("admin/sessions.html", rows=rows, device=device_label)


@bp.post("/sessions/<int:sid>/revoke")
@permission_required("admin.sessions")
def session_revoke(sid):
    if sid == g.session["id"]:
        flash(_("To end your own session, sign out."), "bad")
    elif auth.revoke_session(get_db(), sid, g.user["id"]):
        flash(_("Session ended. That device is signed out."), "ok")
    return redirect(url_for("admin.sessions"))


@bp.post("/sessions/revoke-others")
@permission_required("admin.sessions")
def sessions_revoke_others():
    n = auth.revoke_other_sessions(get_db(), g.session["id"], g.user["id"])
    flash(_("{n} sessions ended. Everyone except you is signed out.", n=n), "ok")
    return redirect(url_for("admin.sessions"))


# ---------- الإعدادات ----------

@bp.route("/settings", methods=["GET", "POST"])
@permission_required("admin.settings")
def platform_settings():
    db = get_db()
    error = None
    if request.method == "POST":
        try:
            n = settings.save(db, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Settings saved.") if n else _("No changes to save."), "ok")
            return redirect(url_for("admin.platform_settings"))
    return render_template("admin/settings.html", form=request.form if error else settings.load(db), error=error)


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
            flash(_("Project {code} created. Now assign its team.", code=code), "ok")
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
            flash(_("Project details saved."), "ok")
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
            flash(_("Member removed from the project."), "ok")
        else:
            P.add_member(db, pid, int(uid), g.user["id"])
            flash(_("Member assigned to the project."), "ok")
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
