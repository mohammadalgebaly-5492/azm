"""شاشات مستخلصات مقاولي الباطن وفواتير الموردين ومحاضر الاستلام، ومستخلصات الشركة للمالك."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import billing as B, payables as X
from ..auth import AuthError, login_required, permission_required
from ..boq import fmt_qty
from ..contracts import fmt_pct
from ..db import get_db
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("payables", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _run(fn, ok, back):
    try:
        out = fn()
        flash(ok.replace("{code}", out) if isinstance(out, str) else ok, "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(back)


@bp.get("/projects/<int:pid>/payables")
@login_required
def page(pid):
    db, p = _project(pid)
    receipts = db.execute("SELECT r.*, c.code AS order_code FROM goods_receipts r JOIN commitments c ON c.id = r.commitment_id "
                          "WHERE r.project_id = ? ORDER BY r.id DESC", (pid,)).fetchall()
    return render_template("payables/page.html", p=p, orders=X.orders(db, pid), rows=X.payables(db, pid), receipts=receipts,
                           KINDS=X.KINDS, STATUS=X.STATUS, fmt_qty=fmt_qty, fmt_pct=fmt_pct,
                           users={r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()})


@bp.post("/projects/<int:pid>/payables/receipts")
@permission_required("payables.raise")
def receipt(pid):
    db, _p = _project(pid)
    return _run(lambda: X.add_receipt(db, pid, request.form, g.user["id"]), _("Goods receipt {code} recorded."),
                url_for("payables.page", pid=pid) + "#receipts")


@bp.post("/projects/<int:pid>/payables")
@permission_required("payables.raise")
def raise_(pid):
    db, _p = _project(pid)
    return _run(lambda: X.raise_payable(db, pid, request.form, g.user["id"]),
                _("{code} raised. It waits for the cost control engineer."), url_for("payables.page", pid=pid) + "#payables")


@bp.post("/projects/<int:pid>/payables/<int:xid>/<action>")
@login_required
def act(pid, xid, action):
    db, _p = _project(pid)
    x = db.execute("SELECT status FROM payables WHERE id = ? AND project_id = ?", (xid, pid)).fetchone()
    if x is None:
        abort(404)
    director = x["status"] == "cc_approved"
    need = {"approve": "changes.approve" if director else "payables.approve",
            "return": "changes.approve" if director else "payables.approve", "pay": "payables.pay"}.get(action)
    if need is None or not can(g.user, need):
        abort(403)
    back = url_for("payables.page", pid=pid) + "#payables"
    if action == "approve":
        return _run(lambda: X.approve(db, pid, xid, g.user["id"], director), _("Approved."), back)
    if action == "return":
        return _run(lambda: X.return_payable(db, pid, xid, request.form.get("reason"), g.user["id"], director),
                    _("Returned with the reason."), back)
    return _run(lambda: X.pay(db, pid, xid, request.form, g.user["id"]), _("Payment recorded."), back)


@bp.get("/projects/<int:pid>/billing")
@login_required
def billing(pid):
    db, p = _project(pid)
    return render_template("billing/page.html", p=p, rows=B.certificates(db, pid), due=B.due_without_certificate(db, pid),
                           receivables=B.receivables(db, pid), STATUS=B.STATUS, fmt_pct=fmt_pct)


@bp.post("/projects/<int:pid>/billing")
@permission_required("billing.prepare")
def billing_new(pid):
    db, _p = _project(pid)
    return _run(lambda: B.create(db, pid, request.form, g.user["id"]),
                _("Draft {code} prepared. It waits for the cost control engineer's agreement."), url_for("payables.billing", pid=pid))


@bp.post("/projects/<int:pid>/billing/<int:oid>/<step>")
@login_required
def billing_step(pid, oid, step):
    db, _p = _project(pid)
    need = {"agree": "projects.manage", "submit": "billing.prepare", "certify": "billing.prepare", "collect": "payables.pay"}.get(step)
    if need is None or not can(g.user, need):
        abort(403)
    return _run(lambda: B.advance(db, pid, oid, step, request.form, g.user["id"]), _("Saved."), url_for("payables.billing", pid=pid))
