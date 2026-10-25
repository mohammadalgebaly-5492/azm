"""شاشات المشتريات: الطلبات والأوامر الصادرة، وطلب جديد، وصفحة الطلب بعروضه وجدول المقارنة ومسار الاعتماد."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import procurement as Q, registers as R
from ..auth import AuthError, login_required, permission_required
from ..boq import fmt_qty
from ..db import get_db
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("procurement", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _ctx(db):
    return {"KINDS": Q.KINDS, "STATUS": Q.STATUS, "EVALUATION": Q.EVALUATION, "fmt_qty": fmt_qty, "LIMIT": Q.LIMIT,
            "users": {r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()}}


@bp.get("/projects/<int:pid>/procurement")
@login_required
def page(pid):
    db, p = _project(pid)
    return render_template("procurement/page.html", p=p, rows=Q.requests(db, pid), orders=Q.commitments(db, pid),
                           budget=Q.budget_by_item(db, pid), **_ctx(db))


@bp.route("/projects/<int:pid>/procurement/new", methods=["GET", "POST"])
@permission_required("procurement.request")
def new(pid):
    db, p = _project(pid)
    error = None
    if request.method == "POST":
        try:
            rid, code = Q.create_request(db, pid, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Request {code} raised. Procurement collects the quotes now.", code=code), "ok")
            return redirect(url_for("procurement.view", pid=pid, rid=rid))
    items = db.execute("SELECT id, code, description, unit, amount FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall()
    steps = db.execute("SELECT s.id, s.code, s.name, s.boq_item_id, b.code AS item_code FROM scope_steps s "
                       "JOIN boq_items b ON b.id = s.boq_item_id WHERE s.project_id = ? ORDER BY b.code, s.seq", (pid,)).fetchall()
    docs = db.execute("SELECT id, code, title FROM documents WHERE project_id = ? ORDER BY code", (pid,)).fetchall()
    dates = {i["id"]: Q.suggested_date(db, pid, i["id"]) for i in items}
    return render_template("procurement/form.html", p=p, error=error, form=request.form, items=items, steps=steps, docs=docs,
                           dates=dates, avail={i["id"]: Q.available(db, i["id"]) for i in items}, **_ctx(db))


@bp.get("/projects/<int:pid>/procurement/<int:rid>")
@login_required
def view(pid, rid):
    db, p = _project(pid)
    r = Q.request(db, pid, rid)
    if r is None:
        abort(404)
    want = "subcontractor" if r["kind"] == "subcontract" else "supplier"
    vendors = [e for e in R.entities(db, want, active_only=True) if e["approval_status"] == "approved"]
    steps = db.execute("SELECT s.code, s.name FROM pr_steps x JOIN scope_steps s ON s.id = x.step_id WHERE x.request_id = ? "
                       "ORDER BY s.seq", (rid,)).fetchall()
    docs = db.execute("SELECT d.id, d.code, d.title FROM pr_documents x JOIN documents d ON d.id = x.document_id "
                      "WHERE x.request_id = ? ORDER BY d.code", (rid,)).fetchall()
    order = db.execute("SELECT * FROM commitments WHERE request_id = ?", (rid,)).fetchone()
    return render_template("procurement/view.html", p=p, r=r, cmp=Q.comparison(db, r), vendors=vendors, steps=steps, docs=docs,
                           order=order, want=want, **_ctx(db))


def _run(pid, rid, fn, ok):
    try:
        fn()
        flash(ok, "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("procurement.view", pid=pid, rid=rid))


@bp.post("/projects/<int:pid>/procurement/<int:rid>/quotes")
@permission_required("procurement.quotes")
def quote(pid, rid):
    db, _p = _project(pid)
    return _run(pid, rid, lambda: Q.add_quote(db, pid, rid, request.form, g.user["id"]), _("Quote added."))


@bp.post("/projects/<int:pid>/procurement/<int:rid>/select")
@permission_required("procurement.select")
def select(pid, rid):
    db, _p = _project(pid)
    qid = str(request.form.get("quote_id") or "")
    return _run(pid, rid, lambda: Q.select_quote(db, pid, rid, int(qid) if qid.isdigit() else 0, request.form.get("reason"),
                                                 g.user["id"]), _("Quote chosen. It waits for cost control."))


@bp.post("/projects/<int:pid>/procurement/<int:rid>/approve")
@login_required
def approve(pid, rid):
    db, _p = _project(pid)
    r = Q.request(db, pid, rid)
    if r is None:
        abort(404)
    director = r["status"] == "cc_approved"
    if not can(g.user, "changes.approve" if director else "procurement.approve"):
        abort(403)
    try:
        code = (Q.director_approve if director else Q.cc_approve)(db, pid, rid, g.user["id"])
    except AuthError as e:
        flash(str(e), "bad")
    else:
        flash(_("Approved. Order {code} issued.", code=code) if code else
              _("Approved by cost control. It waits for the Director because it is above 10,000 SAR."), "ok")
    return redirect(url_for("procurement.view", pid=pid, rid=rid))


@bp.post("/projects/<int:pid>/procurement/<int:rid>/return")
@login_required
def send_back(pid, rid):
    db, _p = _project(pid)
    director = can(g.user, "changes.approve")
    if not (director or can(g.user, "procurement.approve")):
        abort(403)
    return _run(pid, rid, lambda: Q.return_request(db, pid, rid, request.form.get("reason"), g.user["id"], may_director=director),
                _("Request returned with the reason."))


@bp.post("/projects/<int:pid>/procurement/<int:rid>/cancel")
@permission_required("procurement.request")
def cancel(pid, rid):
    db, _p = _project(pid)
    return _run(pid, rid, lambda: Q.cancel_request(db, pid, rid, request.form.get("reason"), g.user["id"]), _("Request cancelled."))
