"""شاشات الجدول الزمني: الجدول مجمّعًا حسب الأقسام مع مخطط الأنشطة، ومنحنى التقدم والتدفق النقدي، وصفحة النشاط بتقدمه."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import schedule as T
from ..auth import AuthError, login_required, permission_required
from ..contracts import fmt_pct
from ..db import get_db
from ..i18n import _
from ..rbac import can_view_project

bp = Blueprint("schedule", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _link_options(db, pid):
    return (db.execute("SELECT id, code, name FROM wbs_nodes WHERE project_id = ? ORDER BY code", (pid,)).fetchall(),
            db.execute("SELECT id, code, description FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall())


def _timeline(rows, now):
    """حدود المخطط الزمني ونِسَب الأشرطة لكل نشاط (بالمئة من عرض المخطط)."""
    if not rows:
        return None, {}
    start = min([r["ps"] for r in rows] + [r["fs"] for r in rows])
    end = max([r["pf"] for r in rows] + [r["ff"] for r in rows])
    span = (end - start).days + 1

    def pos(a, b):
        return round((a - start).days * 100 / span, 2), round(((b - a).days + 1) * 100 / span, 2)
    bars = {r["a"]["id"]: {"plan": pos(r["ps"], r["pf"]), "fact": pos(r["fs"], r["ff"])} for r in rows}
    months, d = [], start.replace(day=1)
    while d <= end:
        if d >= start:
            months.append((round((d - start).days * 100 / span, 2), d))
        d = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
    today_x = round((now - start).days * 100 / span, 2) if start <= now <= end else None
    return {"start": start, "end": end, "months": months, "today": today_x}, bars


@bp.get("/projects/<int:pid>/schedule")
@login_required
def page(pid):
    db, p = _project(pid)
    now = T.today()
    rows = T.compute(db, pid, now)
    groups = {}
    for r in rows:
        groups.setdefault((r["a"]["wbs_code"], r["a"]["wbs_name"]), []).append(r)
    timeline, bars = _timeline(rows, now)
    ms = T.milestones(db, pid, rows)
    sections, items = _link_options(db, pid)
    st = T.state(db, pid)
    names = {r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()}
    curve = T.s_curve(db, pid, rows, now)
    flow = T.cash_flow(db, pid, rows, ms)
    return render_template(
        "schedule/page.html", p=p, groups=sorted(groups.items()), rows=rows, timeline=timeline, bars=bars,
        checks=T.checks(db, pid, rows), st=st, names=names, total=T.overall(db, pid, rows, now), curve=curve, flow=flow,
        flow_top=max([f["cost"] for f in flow] + [f["inflow"] for f in flow] + [1]), sections=sections, items=items,
        STATUS=T.STATUS, fmt_pct=fmt_pct, now=now, all_acts=[r["a"] for r in rows])


@bp.get("/projects/<int:pid>/schedule/<int:aid>")
@login_required
def activity(pid, aid):
    db, p = _project(pid)
    now = T.today()
    rows = T.compute(db, pid, now)
    r = next((x for x in rows if x["a"]["id"] == aid), None)
    if r is None:
        abort(404)
    a = r["a"]
    steps = db.execute("SELECT * FROM scope_steps WHERE boq_item_id = ? ORDER BY seq, id", (a["boq_item_id"],)).fetchall() \
        if a["boq_item_id"] else []
    by_id = {x["a"]["id"]: x["a"] for x in rows}
    successors = [x["a"] for x in rows if aid in x["preds"]]
    sections, items = _link_options(db, pid)
    ms = [m for m in T.milestones(db, pid, rows) if m["m"]["activity_id"] == aid]
    link = f"item-{a['boq_item_id']}" if a["boq_item_id"] else f"wbs-{a['wbs_id']}"
    return render_template("schedule/activity.html", p=p, r=r, a=a, steps=steps, preds=[by_id[x] for x in r["preds"] if x in by_id],
                           successors=successors, sections=sections, items=items, ms=ms, link=link,
                           others=[x["a"] for x in rows if x["a"]["id"] != aid], st=T.state(db, pid), STATUS=T.STATUS,
                           fmt_pct=fmt_pct, now=now)


def _run(fn, ok, back):
    try:
        fn()
        flash(ok, "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(back)


@bp.post("/projects/<int:pid>/schedule/activities")
@permission_required("schedule.manage")
def add(pid):
    db, _p = _project(pid)
    return _run(lambda: T.add_activity(db, pid, request.form, g.user["id"]), _("Activity added."),
                url_for("schedule.page", pid=pid) + "#activities")


@bp.post("/projects/<int:pid>/schedule/<int:aid>/edit")
@permission_required("schedule.manage")
def edit(pid, aid):
    db, _p = _project(pid)
    return _run(lambda: T.update_activity(db, pid, aid, request.form, g.user["id"]), _("Activity saved."),
                url_for("schedule.activity", pid=pid, aid=aid))


@bp.post("/projects/<int:pid>/schedule/<int:aid>/delete")
@permission_required("schedule.manage")
def delete(pid, aid):
    db, _p = _project(pid)
    try:
        T.delete_activity(db, pid, aid, g.user["id"])
    except AuthError as e:
        flash(str(e), "bad")
        return redirect(url_for("schedule.activity", pid=pid, aid=aid))
    flash(_("Activity deleted."), "ok")
    return redirect(url_for("schedule.page", pid=pid))


@bp.post("/projects/<int:pid>/schedule/<int:aid>/actual")
@permission_required("schedule.manage")
def actual(pid, aid):
    db, _p = _project(pid)
    return _run(lambda: T.set_actual(db, pid, aid, request.form, g.user["id"]), _("Actual dates saved."),
                url_for("schedule.activity", pid=pid, aid=aid))


@bp.post("/projects/<int:pid>/schedule/<int:aid>/steps/<int:sid>")
@permission_required("schedule.manage")
def step(pid, aid, sid):
    db, _p = _project(pid)
    return _run(lambda: T.finish_step(db, pid, sid, request.form.get("finished_on"), g.user["id"]), _("Progress saved."),
                url_for("schedule.activity", pid=pid, aid=aid) + "#steps")


@bp.post("/projects/<int:pid>/schedule/review")
@permission_required("projects.manage")
def review(pid):
    db, _p = _project(pid)
    return _run(lambda: T.review(db, pid, g.user["id"]), _("Schedule reviewed. It waits for the Director's approval."),
                url_for("schedule.page", pid=pid))


@bp.post("/projects/<int:pid>/schedule/approve")
@permission_required("changes.approve")
def approve(pid):
    db, _p = _project(pid)
    return _run(lambda: T.approve(db, pid, g.user["id"]), _("Schedule approved as the time baseline."),
                url_for("schedule.page", pid=pid))


@bp.post("/projects/<int:pid>/schedule/reopen")
@permission_required("changes.approve")
def reopen(pid):
    db, _p = _project(pid)
    return _run(lambda: T.reopen(db, pid, request.form.get("reason"), g.user["id"]), _("Schedule reopened for changes."),
                url_for("schedule.page", pid=pid))


@bp.post("/projects/<int:pid>/contract/payments")
@permission_required("projects.manage")
def payment_add(pid):
    db, _p = _project(pid)
    return _run(lambda: T.add_milestone(db, pid, request.form, g.user["id"]), _("Payment added."),
                url_for("contracts.page", pid=pid) + "#payments")


@bp.post("/projects/<int:pid>/contract/payments/<int:mid>/delete")
@permission_required("projects.manage")
def payment_delete(pid, mid):
    db, _p = _project(pid)
    return _run(lambda: T.delete_milestone(db, pid, mid, g.user["id"]), _("Payment deleted."),
                url_for("contracts.page", pid=pid) + "#payments")
