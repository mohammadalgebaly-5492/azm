from flask import Blueprint, abort, g, render_template

from .. import projects as P
from ..auth import login_required
from ..db import get_db
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
                "SELECT COUNT(*) FROM users WHERE status = 'active' AND must_change_password = 1").fetchone()[0],
            "locked": db.execute(
                "SELECT COUNT(*) FROM users WHERE locked_until > strftime('%Y-%m-%dT%H:%M:%S', 'now')").fetchone()[0],
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
    boq_count, boq_total = db.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM boq_items WHERE project_id = ?",
                                      (pid,)).fetchone()
    return render_template("project.html", p=p, team=team, candidates=candidates, activity=activity,
                           boq_count=boq_count, boq_total=boq_total)


@bp.get("/account")
@login_required
def account():
    db = get_db()
    plist = P.visible_projects(db, g.user, False)
    return render_template("account.html", my_projects=plist)
