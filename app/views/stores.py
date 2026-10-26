"""شاشات المخزن الرئيسي للشركة وسقالات كل مشروع."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import registers as R, stores as ST
from ..auth import AuthError, login_required, permission_required
from ..db import get_db
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("stores", __name__)


def _names(db):
    return {c["code"]: R.label(c) for c in ST.components(db)}


@bp.get("/stores")
@login_required
def page():
    if not (can(g.user, "stores.manage") or can(g.user, "projects.manage") or can(g.user, "changes.approve")):
        abort(403)
    db = get_db()
    return render_template("stores/page.html", parts=ST.components(db), bal=ST.store_balance(db), moves=ST.moves(db),
                           names=_names(db), KINDS=ST.KINDS, PLACES=ST.PLACES, label=R.label)


@bp.post("/stores/moves")
@permission_required("stores.manage")
def move():
    db = get_db()
    form = request.form
    if form.get("kind") not in ("receive", "loss") or (form.get("kind") == "loss" and form.get("place") != "store"):
        abort(400)
    try:
        flash(_("Movement {code} recorded.", code=ST.record(db, form, g.user["id"])), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("stores.page"))


@bp.post("/stores/rates/<code>")
@permission_required("projects.manage")
def rate(code):
    try:
        ST.set_rate(get_db(), code, request.form.get("daily_rate"), g.user["id"])
        flash(_("Saved."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("stores.page"))


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


@bp.get("/projects/<int:pid>/scaffolding")
@login_required
def project(pid):
    db, p = _project(pid)
    bal = ST.project_balance(db, pid)
    items = {b["id"]: b for b in db.execute("SELECT id, code, description FROM boq_items WHERE project_id = ? ORDER BY code",
                                            (pid,)).fetchall()}
    totals = {}
    for (_i, code), b in bal.items():
        t = totals.setdefault(code, {"out": 0, "use": 0, "site": 0})
        for k in t:
            t[k] += b[k]
    rates = {c["code"]: c["daily_rate"] for c in ST.components(db)}
    by_item = [{"item": items[i], "code": code, **b} for (i, code), b in sorted(bal.items()) if b["out"]]
    return render_template("stores/project.html", p=p, parts=ST.components(db), by_item=by_item, totals=totals, items=items,
                           rates=rates, store=ST.store_balance(db), moves=ST.moves(db, pid), names=_names(db),
                           rent=ST.daily_rent(db, pid), cost=sum(ST.cost_by_item(db, pid).values()), KINDS=ST.KINDS,
                           PLACES=ST.PLACES, label=R.label)


@bp.post("/projects/<int:pid>/scaffolding/moves")
@login_required
def project_move(pid):
    db, _p = _project(pid)
    kind, place = request.form.get("kind"), request.form.get("place")
    need = "stores.manage" if kind in ST.STORE_KINDS else "schedule.manage" if kind in ST.SITE_KINDS else None
    if kind == "loss" and place in ("site", "use"):
        need = "stores.manage" if can(g.user, "stores.manage") else "schedule.manage"
    if kind == "receive" or need is None or not can(g.user, need):
        abort(403)
    try:
        flash(_("Movement {code} recorded.", code=ST.record(db, request.form, g.user["id"], pid)), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("stores.project", pid=pid))
