"""شاشات تقارير المهندس: قسم في التقرير اليومي وطلب الشراء، وصفحة لكل طلب تغيير ومستخلص وفاتورة ومحضر استلام."""
from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import attachments as A, files
from ..auth import AuthError, login_required
from ..db import get_db
from ..i18n import _
from ..rbac import can, can_view_project

bp = Blueprint("attachments", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _back(pid, kind, doc_id):
    return {"dsr": url_for("daily.view", pid=pid, rid=doc_id), "pr": url_for("procurement.view", pid=pid, rid=doc_id)}.get(
        kind, url_for("attachments.page", pid=pid, kind=kind, doc_id=doc_id))


@bp.app_template_global()
def report_counts(pid, kind):
    return A.counts(get_db(), pid, kind)


@bp.app_template_global()
def report_entries(pid, kind, doc_id):
    return A.entries(get_db(), pid, kind, doc_id)


@bp.app_template_global()
def report_can_add(kind):
    return kind in A.DOCS and can(g.user, A.DOCS[kind][1])


@bp.app_template_global()
def report_storage():
    return files.enabled()


@bp.route("/projects/<int:pid>/engineer-reports/<kind>/<int:doc_id>", methods=["GET", "POST"])
@login_required
def page(pid, kind, doc_id):
    db, p = _project(pid)
    try:
        d = A.doc(db, pid, kind, doc_id)
    except AuthError:
        abort(404)
    if request.method == "POST":
        if not report_can_add(kind):
            abort(403)
        f = request.files.get("file")
        try:
            A.add(db, pid, kind, doc_id, request.form.get("body"), f.stream if f and f.filename else None,
                  f.filename if f and f.filename else None, g.user["id"])
            flash(_("Engineer report added."), "ok")
        except AuthError as e:
            flash(str(e), "bad")
        return redirect(_back(pid, kind, doc_id) + "#engineer-reports")
    return render_template("attachments/page.html", p=p, d=d, kind=kind, title=A.DOCS[kind][2],
                           back={"cr": url_for("changes.page", pid=pid), "payable": url_for("payables.page", pid=pid) + "#payables",
                                 "grn": url_for("payables.page", pid=pid) + "#receipts"}.get(kind, _back(pid, kind, doc_id)))


@bp.get("/projects/<int:pid>/engineer-reports/file/<int:aid>")
@login_required
def file(pid, aid):
    db, _p = _project(pid)
    try:
        data, name = A.content(db, pid, aid)
    except AuthError as e:
        flash(str(e), "bad")
        return redirect(url_for("main.project", pid=pid))
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})
