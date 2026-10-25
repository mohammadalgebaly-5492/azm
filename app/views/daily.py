"""شاشات التقرير اليومي للموقع ومراجعته، وشاشة أداء المشروع بالقيمة المكتسبة وحالته بالألوان."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import daily as Y, performance as P, periodic as PR, registers as R, schedule as T
from ..auth import AuthError, login_required, permission_required
from ..boq import fmt_qty
from ..contracts import fmt_pct
from ..db import get_db
from ..i18n import _
from ..rbac import can_view_project

bp = Blueprint("daily", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _names(db):
    return {"eq_names": R.catalog_names(db, "equipment"), "STATUS": Y.STATUS, "IDLE": Y.IDLE, "fmt_qty": fmt_qty,
            "fmt_pct": fmt_pct, "users": {r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()}}


@bp.get("/projects/<int:pid>/reports")
@login_required
def page(pid):
    db, p = _project(pid)
    rows = Y.reports(db, pid)
    return render_template("daily/page.html", p=p, rows=rows, waiting=sum(1 for r in rows if r["status"] == "review"),
                           **_names(db))


def _form_ctx(db, pid, on, rid=None):
    return {"acts": T.activities(db, pid), "steps": Y.open_steps(db, pid, rid),
            "items": db.execute("SELECT id, code, description, unit FROM boq_items WHERE project_id = ? ORDER BY code",
                                (pid,)).fetchall(),
            "allocs": Y.allocations_on(db, pid, on), "on": on}


@bp.route("/projects/<int:pid>/reports/new", methods=["GET", "POST"], defaults={"rid": None})
@bp.route("/projects/<int:pid>/reports/<int:rid>/edit", methods=["GET", "POST"])
@permission_required("schedule.manage")
def form(pid, rid):
    db, p = _project(pid)
    cur = Y.report(db, pid, rid) if rid else None
    if rid and (cur is None or cur["status"] == "approved"):
        abort(404)
    error = None
    if request.method == "POST":
        try:
            if cur:
                warns = Y.update_report(db, pid, rid, request.form, g.user["id"])
            else:
                rid, code, warns = Y.create_report(db, pid, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Report saved. It waits for the cost control engineer's review."), "ok")
            for w in warns:
                flash(w, "warn")
            return redirect(url_for("daily.view", pid=pid, rid=rid))
    on = request.values.get("report_date") or (str(cur["report_date"])[:10] if cur else T.today().isoformat())
    if error or not cur:
        data = request.form if request.method == "POST" else None
        chosen = {"activities": set(), "steps": set(), "quantities": {}, "resources": {}}
        if data is not None:
            chosen = {"activities": {int(x) for x in data.getlist("activities") if x.isdigit()},
                      "steps": {int(x) for x in data.getlist("steps") if x.isdigit()}, "quantities": {}, "resources": {}}
        issues = data.get("issues", "") if data is not None else ""
    else:
        chosen, issues = Y.details(db, rid), cur["issues"] or ""
    return render_template("daily/form.html", p=p, cur=cur, error=error, chosen=chosen, issues=issues, form=request.form,
                           **_form_ctx(db, pid, on, rid), **_names(db))


@bp.get("/projects/<int:pid>/reports/<int:rid>")
@login_required
def view(pid, rid):
    db, p = _project(pid)
    r = Y.report(db, pid, rid)
    if r is None:
        abort(404)
    d = Y.details(db, rid)
    from ..resources import allocations
    allocs = {a["id"]: a for a in allocations(db, pid)}
    acts = {a["id"]: a for a in T.activities(db, pid)}
    steps = db.execute("SELECT s.*, b.code AS item_code FROM dsr_steps x JOIN scope_steps s ON s.id = x.step_id "
                       "JOIN boq_items b ON b.id = s.boq_item_id WHERE x.report_id = ? ORDER BY b.code, s.seq", (rid,)).fetchall()
    items = {b["id"]: b for b in db.execute("SELECT id, code, description, unit FROM boq_items WHERE project_id = ?", (pid,))}
    return render_template("daily/view.html", p=p, r=r, d=d, allocs=allocs, acts=acts, steps=steps, items=items,
                           total=sum(x["cost"] for x in d["resources"].values()), **_names(db))


@bp.post("/projects/<int:pid>/reports/<int:rid>/approve")
@permission_required("projects.manage")
def approve(pid, rid):
    db, _p = _project(pid)
    try:
        Y.approve_report(db, pid, rid, g.user["id"])
        flash(_("Report approved. Its progress and cost now count in the indicators."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("daily.view", pid=pid, rid=rid))


@bp.post("/projects/<int:pid>/reports/<int:rid>/pm-check")
@permission_required("project.lead")
def pm_check(pid, rid):
    db, _p = _project(pid)
    try:
        Y.pm_check(db, pid, rid, g.user["id"])
        flash(_("Checked by the project manager. It waits for the cost control engineer."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("daily.view", pid=pid, rid=rid))


@bp.post("/projects/<int:pid>/reports/<int:rid>/return")
@permission_required("projects.manage")
def send_back(pid, rid):
    db, _p = _project(pid)
    try:
        Y.return_report(db, pid, rid, request.form.get("reason"), g.user["id"])
        flash(_("Report returned to its preparer with the reason."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("daily.view", pid=pid, rid=rid))


@bp.route("/engineers", methods=["GET", "POST"])
@login_required
def engineers():
    from .. import authority as A
    from ..rbac import can
    if not (can(g.user, "projects.manage") or can(g.user, "changes.approve")):
        abort(403)
    db = get_db()
    if request.method == "POST":
        if not can(g.user, "projects.manage"):
            abort(403)
        uid = str(request.form.get("user_id") or "")
        try:
            if not uid.isdigit():
                raise AuthError(_("Choose the engineer."))
            A.set_level(db, int(uid), request.form.get("level"), request.form.get("reason"), g.user["id"])
            flash(_("Authority changed. The Director is notified."), "ok")
        except AuthError as e:
            flash(str(e), "bad")
        return redirect(url_for("daily.engineers"))
    cache = {}
    return render_template("daily/engineers.html", cards=A.scorecards(db, cache), teams=A.team_cards(db, cache), LEVELS=A.LEVELS,
                           changes=A.recent_changes(db, 90),
                           fmt_pct=fmt_pct, names={r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()})


@bp.get("/projects/<int:pid>/performance")
@login_required
def performance(pid):
    db, p = _project(pid)
    ind = P.indicators(db, pid)
    worst = P.most_deviating(ind)
    items = {b["id"]: b for b in ind["item_rows"]}
    return render_template("daily/performance.html", p=p, ind=ind, m=ind["project"], worst=[items[i] for i in worst],
                           items=items, RAG=P.RAG, top=[n for n in ind["wbs"] if n["parent_id"] is None],
                           waiting=db.execute("SELECT COUNT(*) FROM daily_reports WHERE project_id = ? AND status = 'review'",
                                              (pid,)).fetchone()[0], fmt_pct=fmt_pct)


@bp.get("/projects/<int:pid>/status-reports")
@login_required
def periodic(pid):
    db, p = _project(pid)
    return render_template("daily/periodic.html", p=p, weeks=PR.periods(db, pid, "weekly"), months=PR.periods(db, pid, "monthly"))


@bp.get("/projects/<int:pid>/status-reports/<kind>/<end>")
@login_required
def periodic_view(pid, kind, end):
    db, p = _project(pid)
    try:
        on = date.fromisoformat(end)
    except ValueError:
        abort(404)
    r = PR.build(db, pid, kind, on)
    if r is None:
        abort(404)
    return render_template("daily/periodic_view.html", p=p, r=r, m=r["m"], RAG=P.RAG, KINDS=PR.KINDS, fmt_pct=fmt_pct)
