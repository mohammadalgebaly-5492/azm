"""شاشات نطاق العمل: حالة نطاق كل بنود المشروع، وصفحة البند بنطاقه ومخططاته وخطوات تنفيذه."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import registers as R, resources as S, scope as W
from ..auth import AuthError, login_required, permission_required
from ..boq import is_locked
from ..contracts import fmt_pct
from ..db import get_db
from ..documents import DRAWING_TYPES, SPEC_TYPES
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("scope", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


@bp.get("/projects/<int:pid>/scope")
@login_required
def page(pid):
    db, p = _project(pid)
    rows = W.overview(db, pid)
    return render_template("scope/page.html", p=p, rows=rows, METHODS=W.METHODS, fmt_pct=fmt_pct,
                           n_complete=sum(1 for r in rows if r["complete"]), n_reviewed=sum(1 for r in rows if r["reviewed"]))


@bp.get("/projects/<int:pid>/scope/<int:iid>")
@login_required
def item(pid, iid):
    db, p = _project(pid)
    it = db.execute("SELECT * FROM boq_items WHERE id = ? AND project_id = ?", (iid, pid)).fetchone()
    if it is None:
        abort(404)
    sc, rows, checks = W.scope_of(db, iid), W.steps(db, iid), W.checks(db, iid)
    docs = db.execute("SELECT id, code, title, doc_type FROM documents WHERE project_id = ? ORDER BY code", (pid,)).fetchall()
    linked = {d["id"] for d in W.scope_docs(db, iid)}
    users = {r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()}
    return render_template(
        "scope/item.html", p=p, it=it, sc=sc, steps=rows, checks=checks, complete=all(ok for ok, _t in checks),
        method=W.method(rows),
        drawings=[d for d in docs if d["doc_type"] in DRAWING_TYPES], specs=[d for d in docs if d["doc_type"] in SPEC_TYPES],
        linked=linked, linked_docs=W.scope_docs(db, iid), users=users, weight=sum(r["weight_bp"] for r in rows),
        crews=S.crews(db, active_only=True), equipment=S.equipment(db, usable_only=True),
        subs=[e for e in R.entities(db, "subcontractor", active_only=True) if e["approval_status"] == "approved"],
        eq_names=R.catalog_names(db, "equipment"), PARTIES=W.PARTIES, fmt_pct=fmt_pct, METHODS=W.METHODS, locked=is_locked(db, pid),
        types=R.catalog_names(db, "doc_type"))


def _back(pid, iid, anchor=""):
    return redirect(url_for("scope.item", pid=pid, iid=iid) + anchor)


def _run(pid, iid, anchor, fn, ok):
    db, _p = _project(pid)
    try:
        fn(db)
        flash(ok, "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, iid, anchor)


@bp.post("/projects/<int:pid>/scope/<int:iid>")
@permission_required("documents.manage")
def save(pid, iid):
    return _run(pid, iid, "", lambda db: W.save_scope(db, pid, iid, request.form, g.user["id"]), _("Scope saved."))


@bp.post("/projects/<int:pid>/scope/<int:iid>/steps")
@permission_required("documents.manage")
def step_add(pid, iid):
    return _run(pid, iid, "#steps", lambda db: W.add_step(db, pid, iid, request.form, g.user["id"]), _("Step added."))


@bp.post("/projects/<int:pid>/scope/<int:iid>/steps/<int:sid>")
@permission_required("documents.manage")
def step_edit(pid, iid, sid):
    return _run(pid, iid, "#steps", lambda db: W.update_step(db, pid, sid, request.form, g.user["id"]), _("Step saved."))


@bp.post("/projects/<int:pid>/scope/<int:iid>/steps/<int:sid>/delete")
@permission_required("documents.manage")
def step_delete(pid, iid, sid):
    return _run(pid, iid, "#steps", lambda db: W.delete_step(db, pid, sid, g.user["id"]), _("Step deleted."))


@bp.post("/projects/<int:pid>/scope/<int:iid>/review")
@permission_required("projects.manage")
def review(pid, iid):
    return _run(pid, iid, "", lambda db: W.review_scope(db, pid, iid, g.user["id"]), _("Scope reviewed and locked."))


@bp.post("/projects/<int:pid>/scope/<int:iid>/reopen")
@login_required
def reopen(pid, iid):
    approver = can(g.user, "changes.approve")
    if not (approver or can(g.user, "projects.manage")):
        abort(403)
    return _run(pid, iid, "", lambda db: W.reopen_scope(db, pid, iid, request.form.get("reason"), g.user["id"],
                                                        may_approve=approver), _("Scope reopened for changes."))
