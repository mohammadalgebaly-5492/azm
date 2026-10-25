"""شاشات بوابة بدء التنفيذ، والإنذار المبكر وخطط التعافي والتأخير، والإغلاق. والمشروع المغلق للقراءة فقط."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import changes as CH, governance as G, performance as P
from ..auth import AuthError, login_required, permission_required
from ..contracts import fmt_pct
from ..db import get_db
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("governance", __name__)


@bp.before_app_request
def closed_is_read_only():
    """المشروع المغلق تبقى بياناته للقراءة فقط (البند 4.10)."""
    pid = (request.view_args or {}).get("pid")
    if request.method == "POST" and pid:
        p = get_db().execute("SELECT status FROM projects WHERE id = ?", (pid,)).fetchone()
        if p and p["status"] == "closed":
            abort(403)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _users(db):
    return {r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()}


def _run(fn, ok, back):
    try:
        out = fn()
        flash(ok.replace("{code}", out) if isinstance(out, str) else ok, "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(back)


@bp.get("/projects/<int:pid>/kickoff")
@login_required
def kickoff(pid):
    db, p = _project(pid)
    crs = [r for r in CH.requests(db, pid) if r["status"] != "returned"]
    return render_template("governance/kickoff.html", p=p, reviews=G.kickoff_reviews(db, pid), crs=crs, ELEMENTS=G.ELEMENTS,
                           DECISIONS=G.DECISIONS, users=_users(db))


@bp.post("/projects/<int:pid>/kickoff")
@permission_required("project.lead")
def kickoff_review(pid):
    db, _p = _project(pid)
    return _run(lambda: G.review_element(db, pid, request.form, g.user["id"]), _("Saved."), url_for("governance.kickoff", pid=pid))


@bp.post("/projects/<int:pid>/kickoff/start")
@permission_required("project.lead")
def kickoff_start(pid):
    db, _p = _project(pid)
    return _run(lambda: G.start_execution(db, pid, g.user["id"]), _("Execution started. Kickoff record {code}."),
                url_for("governance.kickoff", pid=pid))


@bp.get("/projects/<int:pid>/control")
@login_required
def control(pid):
    db, p = _project(pid)
    ind = P.indicators(db, pid)
    status = ind["project"]["status"]
    acts = db.execute("SELECT id, code, name FROM activities WHERE project_id = ? ORDER BY code", (pid,)).fetchall()
    return render_template("governance/control.html", p=p, m=ind["project"], status=status, alert=G.alert(status),
                           plan_due=G.plan_due(db, pid, status), suggestions=G.suggestions(db, pid, ind["rows"]),
                           plans=G.plans(db, pid), delays=G.delays(db, pid), acts=acts, cost=G.delay_cost_per_day(db, pid),
                           RAG=P.RAG, OPTIONS=G.OPTIONS, PLAN_STATUS=G.PLAN_STATUS, RESPONSIBLE=G.RESPONSIBLE,
                           users=_users(db), fmt_pct=fmt_pct)


@bp.post("/projects/<int:pid>/control/plans")
@permission_required("project.lead")
def plan_add(pid):
    db, _p = _project(pid)
    return _run(lambda: G.add_plan(db, pid, request.form, g.user["id"]), _("Recovery plan {code} raised. It waits for cost control."),
                url_for("governance.control", pid=pid) + "#plans")


@bp.post("/projects/<int:pid>/control/plans/<int:plan_id>/<action>")
@login_required
def plan_decide(pid, plan_id, action):
    db, _p = _project(pid)
    x = db.execute("SELECT status FROM recovery_plans WHERE id = ? AND project_id = ?", (plan_id, pid)).fetchone()
    if x is None or action not in ("approve", "return"):
        abort(404)
    director = x["status"] == "cc_reviewed"
    if not can(g.user, "changes.approve" if director else "projects.manage"):
        abort(403)
    return _run(lambda: G.decide_plan(db, pid, plan_id, action, request.form.get("reason"), g.user["id"], director),
                _("Saved."), url_for("governance.control", pid=pid) + "#plans")


@bp.post("/projects/<int:pid>/control/overhead")
@permission_required("projects.manage")
def overhead(pid):
    db, _p = _project(pid)
    return _run(lambda: G.set_overhead(db, pid, request.form.get("daily_overhead"), g.user["id"]), _("Saved."),
                url_for("governance.control", pid=pid) + "#delays")


@bp.post("/projects/<int:pid>/control/delays")
@permission_required("projects.manage")
def delay_add(pid):
    db, _p = _project(pid)
    return _run(lambda: G.record_delay(db, pid, request.form, g.user["id"]), _("Delay {code} recorded."),
                url_for("governance.control", pid=pid) + "#delays")


@bp.get("/projects/<int:pid>/closeout")
@login_required
def closeout(pid):
    db, p = _project(pid)
    return render_template("governance/closeout.html", p=p, co=G.closeout(db, pid), r=G.final_report(db, pid), RAG=P.RAG,
                           users=_users(db), fmt_pct=fmt_pct)


@bp.post("/projects/<int:pid>/closeout/lessons")
@login_required
def lessons(pid):
    db, _p = _project(pid)
    role = "cc" if request.form.get("role") == "cc" else "pm"
    if not can(g.user, "projects.manage" if role == "cc" else "project.lead"):
        abort(403)
    return _run(lambda: G.save_lessons(db, pid, request.form, g.user["id"], role), _("Saved."),
                url_for("governance.closeout", pid=pid))


@bp.post("/projects/<int:pid>/closeout/close")
@permission_required("changes.approve")
def close(pid):
    db, _p = _project(pid)
    return _run(lambda: G.close_project(db, pid, g.user["id"]), _("Project closed. Closing report {code}. Its data is now read-only."),
                url_for("governance.closeout", pid=pid))
