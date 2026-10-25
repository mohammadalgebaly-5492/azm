"""شاشات العقد الرئيسي: البيانات، والضمانات، والتأمينات، وأوامر التغيير."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import contracts as C, schedule as T
from ..auth import AuthError, login_required, permission_required
from ..db import get_db
from ..i18n import _
from ..rbac import can_view_project

bp = Blueprint("contracts", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _lists():
    return {"KINDS": C.KINDS, "PENALTY_METHODS": C.PENALTY_METHODS, "GUARANTEES": C.GUARANTEES,
            "INSURANCES": C.INSURANCES, "VO_STATUS": C.VO_STATUS, "pct": C.fmt_pct}


@bp.get("/projects/<int:pid>/contract")
@login_required
def page(pid):
    db, p = _project(pid)
    c = C.contract_of(db, pid)
    ctx = {}
    if c:
        vos = C.variation_orders(db, c["id"])
        ctx = {"s": C.summary(db, c), "guarantees": C.guarantees(db, c["id"]), "insurances": C.insurances(db, c["id"]),
               "vos": vos, "vo_items": {v["id"]: C.vo_items(db, v["id"]) for v in vos},
               "expiring": C.expiring(db, c["id"]), "ms": T.milestones(db, pid),
               "acts": db.execute("SELECT id, code, name FROM activities WHERE project_id = ? ORDER BY code", (pid,)).fetchall(),
               "schedule_locked": bool(T.state(db, pid)["schedule_approved_at"]),
               "boq": db.execute("SELECT id, code, description FROM boq_items WHERE project_id = ? ORDER BY code",
                                 (pid,)).fetchall()}
    return render_template("contracts/page.html", p=p, c=c, **ctx, **_lists())


@bp.route("/projects/<int:pid>/contract/edit", methods=["GET", "POST"])
@permission_required("projects.manage")
def edit(pid):
    db, p = _project(pid)
    c = C.contract_of(db, pid)
    error = None
    if request.method == "POST":
        try:
            C.save_contract(db, pid, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Contract saved."), "ok")
            return redirect(url_for("contracts.page", pid=pid))
    if error or not c:
        form = request.form if error else {
            "contract_no": p["contract_no"] or "", "start_on": str(p["start_date"] or "")[:10],
            "value_ex_vat": f"{p['contract_value'] / 100:.2f}" if p["contract_value"] else "",
            "vat_pct": "15", "retention_pct": "10"}
    else:
        form = dict(c, value_ex_vat=f"{c['value_ex_vat'] / 100:.2f}",
                    **{k.replace("_bp", "_pct"): (f"{c[k] / 100:g}" if c[k] is not None else "")
                       for k in ("vat_bp", "advance_bp", "advance_recovery_bp", "retention_bp", "retention_cap_bp",
                                 "penalty_cap_bp")})
        if c["penalty_method"] == "daily_pct":
            form["penalty_value"] = f"{c['penalty_value'] / 100:g}"
        elif c["penalty_method"] == "daily_amount":
            form["penalty_value"] = f"{c['penalty_value'] / 100:.2f}"
        for k in ("signed_on", "site_handover_on", "start_on"):
            form[k] = str(c[k])[:10]
    return render_template("contracts/form.html", p=p, c=c, form=form, error=error, **_lists())


def _contract_or_404(db, pid):
    c = C.contract_of(db, pid)
    if c is None:
        abort(404)
    return c


@bp.post("/projects/<int:pid>/contract/guarantees")
@permission_required("projects.manage")
def guarantee_add(pid):
    db, _p = _project(pid)
    c = _contract_or_404(db, pid)
    try:
        C.add_guarantee(db, c["id"], request.form, g.user["id"])
        flash(_("Bank guarantee added."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("contracts.page", pid=pid) + "#guarantees")


@bp.post("/projects/<int:pid>/contract/guarantees/<int:gid>/release")
@permission_required("projects.manage")
def guarantee_release(pid, gid):
    db, _p = _project(pid)
    c = _contract_or_404(db, pid)
    try:
        C.release_guarantee(db, c["id"], gid, g.user["id"])
        flash(_("Guarantee marked as released."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("contracts.page", pid=pid) + "#guarantees")


@bp.post("/projects/<int:pid>/contract/insurances")
@permission_required("projects.manage")
def insurance_add(pid):
    db, _p = _project(pid)
    c = _contract_or_404(db, pid)
    try:
        C.add_insurance(db, c["id"], request.form, g.user["id"])
        flash(_("Insurance policy added."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("contracts.page", pid=pid) + "#insurances")


@bp.post("/projects/<int:pid>/contract/variations")
@permission_required("projects.manage")
def vo_add(pid):
    db, _p = _project(pid)
    c = _contract_or_404(db, pid)
    try:
        _vid, code = C.add_variation_order(db, c["id"], request.form, g.user["id"])
        flash(_("Change order {code} recorded. It now waits for the Director's decision.", code=code), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("contracts.page", pid=pid) + "#variations")


@bp.post("/projects/<int:pid>/contract/variations/<int:vid>/decide")
@permission_required("changes.approve")
def vo_decide(pid, vid):
    db, _p = _project(pid)
    c = _contract_or_404(db, pid)
    try:
        C.decide_variation_order(db, c["id"], vid, request.form.get("decision"), request.form.get("note"), g.user["id"])
        flash(_("Decision saved."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("contracts.page", pid=pid) + "#variations")
