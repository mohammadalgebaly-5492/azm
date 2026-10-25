"""شاشة طلبات التغيير، وصفحة «مهامي»."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import changes as CH, tasks as TK
from ..auth import AuthError, login_required, permission_required
from ..db import get_db
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("changes", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


@bp.get("/projects/<int:pid>/changes")
@login_required
def page(pid):
    db, p = _project(pid)
    rows = CH.requests(db, pid)
    return render_template("changes/page.html", p=p, rows=rows, items={r["id"]: CH.items_of(db, r["id"]) for r in rows},
                           boq=db.execute("SELECT id, code, description FROM boq_items WHERE project_id = ? ORDER BY code",
                                          (pid,)).fetchall(),
                           acts=db.execute("SELECT id, code, name FROM activities WHERE project_id = ? ORDER BY code", (pid,)).fetchall(),
                           KINDS=CH.KINDS, SOURCES=CH.SOURCES, STATUS=CH.STATUS, LIMIT=CH.LIMIT,
                           users={r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()})


@bp.post("/projects/<int:pid>/changes")
@permission_required("changes.request")
def new(pid):
    db, _p = _project(pid)
    try:
        code = CH.create(db, pid, request.form, g.user["id"])
        flash(_("Change request {code} raised. It waits for the project manager.", code=code), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("changes.page", pid=pid))


@bp.post("/projects/<int:pid>/changes/<int:cid>/<action>")
@login_required
def act(pid, cid, action):
    db, _p = _project(pid)
    r = db.execute("SELECT status FROM change_requests WHERE id = ? AND project_id = ?", (cid, pid)).fetchone()
    if r is None:
        abort(404)
    role = {"pm_review": "pm", "cc_review": "cc", "dir_review": "director"}.get(r["status"])
    need = {"pm": "changes.request", "cc": "projects.manage", "director": "changes.approve"}.get(role)
    if need is None or action not in ("approve", "return") or not can(g.user, need):
        abort(403)
    try:
        if action == "approve":
            CH.advance(db, pid, cid, g.user["id"], role)
            flash(_("Saved."), "ok")
        else:
            CH.send_back(db, pid, cid, request.form.get("reason"), g.user["id"])
            flash(_("Returned with the reason."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("changes.page", pid=pid))


@bp.get("/tasks")
@login_required
def tasks():
    rows = TK.collect(get_db(), g.user)
    return render_template("tasks.html", rows=rows, late=TK.LATE_DAYS)
