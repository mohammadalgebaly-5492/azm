from flask import Blueprint, abort, flash, g, make_response, redirect, render_template, request, url_for

from .. import avatars, projects as P, registers as R
from ..auth import AuthError, login_required
from ..db import get_db, utcnow
from ..i18n import _
from ..auth import permission_required
from ..rbac import can, can_view_project

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def home():
    db = get_db()
    plist = P.visible_projects(db, g.user, can(g.user, "projects.view_all"))
    stats = None
    if can(g.user, "users.manage"):
        stats = {
            "users": db.execute("SELECT COUNT(*) FROM users WHERE status = 'active'").fetchone()[0],
            "pending_first_login": db.execute(
                "SELECT COUNT(*) FROM users WHERE status = 'active' AND must_change_password = TRUE").fetchone()[0],
            "locked": db.execute(
                "SELECT COUNT(*) FROM users WHERE locked_until > ?", (utcnow(),)).fetchone()[0],
        }
    team_counts = {r[0]: r[1] for r in db.execute(
        "SELECT project_id, COUNT(*) FROM project_members GROUP BY project_id")}
    return render_template("home.html", projects=plist, stats=stats, team_counts=team_counts)


@bp.get("/projects/<int:pid>")
@login_required
def project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    team = P.members(db, pid)
    candidates = []
    if can(g.user, "projects.manage"):
        candidates = db.execute(
            "SELECT id, code, full_name, role FROM users WHERE status = 'active' AND id NOT IN "
            "(SELECT user_id FROM project_members WHERE project_id = ?) ORDER BY role, full_name", (pid,)).fetchall()
    activity = db.execute(
        "SELECT a.*, u.full_name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
        "WHERE a.project_id = ? ORDER BY a.id DESC LIMIT 20", (pid,)).fetchall()
    boq_count, boq_total = db.execute(
        "SELECT COUNT(*), CAST(COALESCE(SUM(amount), 0) AS BIGINT) FROM boq_items WHERE project_id = ?",
        (pid,)).fetchone()
    parties = {kind: R.entity(db, p[f"{kind}_entity_id"]) if p[f"{kind}_entity_id"] else None
               for kind in ("owner", "consultant")}
    reps = R.representatives(db, pid)
    return render_template("project.html", p=p, team=team, candidates=candidates, activity=activity,
                           boq_count=boq_count, boq_total=boq_total, parties=parties, reps=reps,
                           parties_complete=R.parties_complete(db, pid), MIN_REPS=R.MIN_REPRESENTATIVES)


@bp.get("/analytics")
@permission_required("analytics.view")
def analytics():
    from .. import analytics as A
    db = get_db()
    scope = {"projects": P.visible_projects(db, g.user, can(g.user, "projects.view_all"))}
    return render_template("analytics.html", widgets=A.render_all(db, g.user, scope))


@bp.get("/account")
@login_required
def account():
    db = get_db()
    plist = P.visible_projects(db, g.user, False)
    return render_template("account.html", my_projects=plist)


@bp.post("/account/preferences")
@login_required
def account_preferences():
    db = get_db()
    on = request.form.get("show_guide") == "1"
    db.execute("UPDATE users SET show_guide = ? WHERE id = ?", (on, g.user["id"]))
    flash(_("Explanations are shown across the platform.") if on else _("Explanations are hidden."), "ok")
    return redirect(url_for("main.account") + "#preferences")


@bp.post("/account/avatar")
@login_required
def account_avatar():
    db = get_db()
    action = request.form.get("action")
    try:
        if action == "preset":
            avatars.set_preset(db, g.user["id"], request.form.get("preset", ""))
        elif action == "upload":
            f = request.files.get("photo")
            if not f or not f.filename:
                raise AuthError(_("Choose a photo to upload."))
            avatars.save_upload(db, g.user["id"], f.stream)
        elif action == "clear":
            avatars.clear(db, g.user["id"])
        else:
            abort(400)
    except AuthError as e:
        flash(str(e), "bad")
    else:
        flash(_("Profile picture updated."), "ok")
    return redirect(url_for("main.account") + "#avatar")


@bp.get("/avatar/<int:uid>")
@login_required
def avatar_image(uid):
    img = avatars.load(get_db(), uid)
    if img is None:
        abort(404)
    resp = make_response(img[1])
    resp.headers["Content-Type"] = img[0]
    # الرابط يتغير مع كل صورة جديدة (?v=)، فالتخزين المؤقت آمن
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp
