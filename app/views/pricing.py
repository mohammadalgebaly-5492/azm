"""شاشات تحليل سعر البند: كل البنود بتكلفتها وهامشها، وصفحة البند بسطور التحليل."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import pricing as PR
from ..auth import AuthError, login_required, permission_required
from ..boq import fmt_qty, is_locked
from ..contracts import fmt_pct
from ..db import get_db
from ..i18n import _
from ..rbac import can_view_project

bp = Blueprint("pricing", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


@bp.get("/projects/<int:pid>/pricing")
@login_required
def page(pid):
    db, p = _project(pid)
    items = db.execute("SELECT * FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall()
    rows = [(b, PR.result(db, b)) for b in items]
    return render_template("pricing/page.html", p=p, rows=rows, fmt_pct=fmt_pct, fmt_qty=fmt_qty,
                           n_done=sum(1 for _b, r in rows if r["has"]), locked=is_locked(db, pid))


@bp.get("/projects/<int:pid>/pricing/<int:iid>")
@login_required
def item(pid, iid):
    db, p = _project(pid)
    it = db.execute("SELECT * FROM boq_items WHERE id = ? AND project_id = ?", (iid, pid)).fetchone()
    if it is None:
        abort(404)
    return render_template("pricing/item.html", p=p, it=it, r=PR.result(db, it), COST_TYPES=PR.COST_TYPES,
                           line_total=PR.line_total, fmt_pct=fmt_pct, fmt_qty=fmt_qty, locked=is_locked(db, pid))


def _run(pid, iid, fn, ok):
    try:
        fn()
        flash(ok, "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("pricing.item", pid=pid, iid=iid))


@bp.post("/projects/<int:pid>/pricing/<int:iid>/lines")
@permission_required("boq.manage")
def line_add(pid, iid):
    db, _p = _project(pid)
    return _run(pid, iid, lambda: PR.add_line(db, pid, iid, request.form, g.user["id"]), _("Line added."))


@bp.post("/projects/<int:pid>/pricing/<int:iid>/lines/<int:lid>/delete")
@permission_required("boq.manage")
def line_delete(pid, iid, lid):
    db, _p = _project(pid)
    return _run(pid, iid, lambda: PR.delete_line(db, pid, iid, lid, g.user["id"]), _("Line deleted."))


@bp.post("/projects/<int:pid>/pricing/<int:iid>/rates")
@permission_required("boq.manage")
def rates(pid, iid):
    db, _p = _project(pid)
    return _run(pid, iid, lambda: PR.set_rates(db, pid, iid, request.form, g.user["id"]), _("Saved."))
