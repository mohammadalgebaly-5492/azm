"""شاشات الموارد: سجلات الأفراد والأطقم والمعدات، والهيكل التنظيمي والتخصيص في كل مشروع."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import registers as R, resources as S, scope as W
from ..auth import AuthError, login_required, permission_required
from ..boq import is_locked
from ..db import get_db
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("resources", __name__)


def _names(db):
    return {"professions": R.catalog_names(db, "profession"), "job_titles": R.catalog_names(db, "job_title"),
            "specialties": R.catalog_names(db, "specialty"), "eq_names": R.catalog_names(db, "equipment"),
            "label": R.label, "PERSON_STATUS": S.PERSON_STATUS, "EQUIPMENT_STATUS": S.EQUIPMENT_STATUS,
            "OWNERSHIP": S.OWNERSHIP}


# ---------- الأفراد ----------

@bp.get("/registers/people")
@permission_required("registers.manage")
def people():
    db = get_db()
    return render_template("resources/people.html", rows=S.people(db), **_names(db))


@bp.route("/registers/people/new", methods=["GET", "POST"], defaults={"person_id": None})
@bp.route("/registers/people/<int:person_id>", methods=["GET", "POST"])
@permission_required("registers.manage")
def person_form(person_id):
    db = get_db()
    person = db.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone() if person_id else None
    if person_id and person is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            S.save_person(db, request.form, g.user["id"], person_id)
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Person saved."), "ok")
            return redirect(url_for("resources.people"))
    form = request.form if (error or not person) else dict(person, daily_cost=f"{person['daily_cost'] / 100:.2f}")
    accounts = db.execute("SELECT id, code, full_name FROM users WHERE status = 'active' ORDER BY full_name").fetchall()
    return render_template("resources/person_form.html", person=person, form=form, error=error, accounts=accounts,
                           prof_list=R.catalog(db, "profession", True), title_list=R.catalog(db, "job_title", True),
                           **_names(db))


# ---------- الأطقم ----------

@bp.get("/registers/crews")
@permission_required("registers.manage")
def crews():
    db = get_db()
    rows = S.crews(db)
    return render_template("resources/crews.html", rows=rows, costs={c["id"]: S.crew_daily_cost(db, c) for c in rows},
                           **_names(db))


@bp.route("/registers/crews/new", methods=["GET", "POST"], defaults={"crew_id": None})
@bp.route("/registers/crews/<int:crew_id>", methods=["GET", "POST"])
@permission_required("registers.manage")
def crew_form(crew_id):
    db = get_db()
    crew = db.execute("SELECT * FROM crews WHERE id = ?", (crew_id,)).fetchone() if crew_id else None
    if crew_id and crew is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            S.save_crew(db, request.form, g.user["id"], crew_id)
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Crew saved."), "ok")
            return redirect(url_for("resources.crews"))
    if error or not crew:
        form, members = request.form, {int(x) for x in request.form.getlist("members") if x.isdigit()}
    else:
        form = dict(crew, daily_cost=f"{crew['daily_cost'] / 100:.2f}" if crew["daily_cost"] is not None else "")
        members = {p["id"] for p in S.crew_members(db, crew_id)}
    return render_template("resources/crew_form.html", crew=crew, form=form, members=members, error=error,
                           all_people=S.people(db, active_only=True), spec_list=R.catalog(db, "specialty", True),
                           **_names(db))


# ---------- المعدات ----------

@bp.get("/registers/equipment")
@permission_required("registers.manage")
def equipment():
    db = get_db()
    return render_template("resources/equipment.html", rows=S.equipment(db), **_names(db))


@bp.route("/registers/equipment/new", methods=["GET", "POST"], defaults={"eq_id": None})
@bp.route("/registers/equipment/<int:eq_id>", methods=["GET", "POST"])
@permission_required("registers.manage")
def equipment_form(eq_id):
    db = get_db()
    eq = db.execute("SELECT * FROM equipment WHERE id = ?", (eq_id,)).fetchone() if eq_id else None
    if eq_id and eq is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            S.save_equipment(db, request.form, g.user["id"], eq_id)
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Equipment saved."), "ok")
            return redirect(url_for("resources.equipment"))
    form = request.form if (error or not eq) else dict(eq, daily_cost=f"{eq['daily_cost'] / 100:.2f}")
    types = {r["code"]: R.label(r) for r in R.catalog(db, "equipment_type")}
    catalog = [(t, [e for e in R.catalog(db, "equipment", True) if e["parent_code"] == t["code"]])
               for t in R.catalog(db, "equipment_type", True)]
    return render_template("resources/equipment_form.html", eq=eq, form=form, error=error, catalog=catalog, types=types,
                           **_names(db))


# ---------- موارد المشروع ----------

def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


@bp.get("/projects/<int:pid>/resources")
@login_required
def project(pid):
    db, p = _project(pid)
    allocs = S.allocations(db, pid)
    evals = {a["id"]: S.evaluate(db, a) for a in allocs}
    current = [r for r in S.positions(db, pid) if not r["to_date"]]
    return render_template(
        "resources/project.html", p=p, tree=S.org_tree(db, pid), positions=current,
        history=[r for r in S.positions(db, pid) if r["to_date"]], allocs=allocs, evals=evals,
        demand=S.weekly_demand(db, pid), all_people=S.people(db, active_only=True), all_crews=S.crews(db, active_only=True),
        all_equipment=S.equipment(db, usable_only=True),
        subs=[e for e in R.entities(db, "subcontractor", active_only=True) if e["approval_status"] == "approved"],
        items=db.execute("SELECT id, code, description, unit FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall(),
        title_list=R.catalog(db, "job_title", True), RESOURCE_KINDS=S.RESOURCE_KINDS, ALLOCATION_STATUS=S.ALLOCATION_STATUS,
        locked=is_locked(db, pid), step_groups=_step_groups(db, pid),
        activities=db.execute("SELECT id, code, name, planned_start, planned_finish FROM activities WHERE project_id = ? "
                              "ORDER BY code", (pid,)).fetchall(), PARTIES=W.PARTIES, planned_total=sum(evals[a["id"]]["cost"] for a in allocs if a["status"] in S.LIVE), **_names(db))


def _step_groups(db, pid):
    out = {}
    for s in W.project_steps(db, pid):
        out.setdefault(s["boq_item_id"], []).append(s)
    return out


def _back(pid, anchor):
    return redirect(url_for("resources.project", pid=pid) + anchor)


@bp.post("/projects/<int:pid>/positions")
@permission_required("projects.manage")
def position_add(pid):
    db, _p = _project(pid)
    try:
        S.add_position(db, pid, request.form, g.user["id"])
        flash(_("Position added to the organization chart."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, "#org")


@bp.post("/projects/<int:pid>/positions/<int:oid>/end")
@permission_required("projects.manage")
def position_end(pid, oid):
    db, _p = _project(pid)
    try:
        S.end_position(db, pid, oid, request.form.get("to_date"), g.user["id"])
        flash(_("Position ended. It stays in the history."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, "#org")


@bp.post("/projects/<int:pid>/allocations")
@permission_required("projects.manage")
def allocation_add(pid):
    db, _p = _project(pid)
    try:
        _aid, code, warnings = S.add_allocation(db, pid, request.form, g.user["id"])
        flash(_("Allocation {code} recorded. It waits for the Director's approval.", code=code), "ok")
        for w in warnings:
            flash(w, "warn")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, "#allocations")


@bp.post("/projects/<int:pid>/allocations/<int:aid>/approve")
@permission_required("changes.approve")
def allocation_approve(pid, aid):
    db, _p = _project(pid)
    try:
        S.approve_allocation(db, pid, aid, g.user["id"])
        flash(_("Allocation approved."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, "#allocations")


@bp.post("/projects/<int:pid>/allocations/<int:aid>/cancel")
@login_required
def allocation_cancel(pid, aid):
    approver = can(g.user, "changes.approve")
    if not (approver or can(g.user, "projects.manage")):
        abort(403)
    db, _p = _project(pid)
    try:
        S.cancel_allocation(db, pid, aid, request.form.get("reason"), g.user["id"], may_approve=approver)
        flash(_("Allocation cancelled."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, "#allocations")
