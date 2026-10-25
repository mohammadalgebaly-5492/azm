"""شاشات وثائق المشروع: السجل، والوثيقة ومراجعاتها، ورد المالك أو الاستشاري، ومراجعة اكتمال البيانات."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import documents as D, registers as R
from ..auth import AuthError, login_required, permission_required
from ..db import get_db
from ..i18n import _
from ..rbac import can_view_project

bp = Blueprint("documents", __name__)


def _project(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not can_view_project(db, g.user, pid):
        abort(404)
    return db, p


def _approvers(db):
    """الجهات المعتمِدة (المالك والاستشاري) وممثلو كل جهة."""
    ents = [e for e in R.entities(db, active_only=True) if e["kind"] in ("owner", "consultant")]
    return ents, [(e, R.people(db, e["id"], active_only=True)) for e in ents]


def _links(db, pid):
    return (db.execute("SELECT id, code, name FROM wbs_nodes WHERE project_id = ? ORDER BY code", (pid,)).fetchall(),
            db.execute("SELECT id, code, description FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall())


def _ctx(db):
    return {"types": R.catalog_names(db, "doc_type"), "ISSUERS": D.ISSUERS, "REV_STATUS": D.REV_STATUS, "label": R.label}


@bp.get("/projects/<int:pid>/documents")
@login_required
def page(pid):
    db, p = _project(pid)
    kind = request.args.get("type") or ""
    rows = D.documents(db, pid, kind or None)
    counts = {}
    for r in D.documents(db, pid):
        counts[r["doc_type"]] = counts.get(r["doc_type"], 0) + 1
    return render_template("documents/page.html", p=p, rows=rows, kind=kind, counts=counts,
                           type_list=R.catalog(db, "doc_type"), **_ctx(db))


@bp.route("/projects/<int:pid>/documents/new", methods=["GET", "POST"], defaults={"did": None})
@bp.route("/projects/<int:pid>/documents/<int:did>/edit", methods=["GET", "POST"])
@permission_required("documents.manage")
def form(pid, did):
    db, p = _project(pid)
    doc = D.document(db, pid, did) if did else None
    if did and doc is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            if doc:
                D.update_document(db, pid, did, request.form, g.user["id"])
            else:
                did, code = D.create_document(db, pid, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Document saved."), "ok")
            return redirect(url_for("documents.view", pid=pid, did=did))
    if error or not doc:
        data = request.form if error else {"doc_type": request.args.get("type") or "DRW", "issuer": "consultant"}
    else:
        link = f"item-{doc['boq_item_id']}" if doc["boq_item_id"] else (f"wbs-{doc['wbs_id']}" if doc["wbs_id"] else "")
        data = dict(doc, link=link, issued_on=str(doc["issued_on"])[:10])
    sections, items = _links(db, pid)
    ents, reps = _approvers(db)
    return render_template("documents/form.html", p=p, doc=doc, form=data, error=error, sections=sections, items=items,
                           type_list=R.catalog(db, "doc_type", True), ents=ents, reps=reps, **_ctx(db))


@bp.get("/projects/<int:pid>/documents/<int:did>")
@login_required
def view(pid, did):
    db, p = _project(pid)
    doc = D.document(db, pid, did)
    if doc is None:
        abort(404)
    link = None
    if doc["boq_item_id"]:
        link = db.execute("SELECT code, description AS name FROM boq_items WHERE id = ?", (doc["boq_item_id"],)).fetchone()
    elif doc["wbs_id"]:
        link = db.execute("SELECT code, name FROM wbs_nodes WHERE id = ?", (doc["wbs_id"],)).fetchone()
    users = {r[0]: r[1] for r in db.execute("SELECT id, full_name FROM users").fetchall()}
    scope_items = db.execute("SELECT b.id, b.code, b.description FROM item_scope_docs s JOIN boq_items b ON b.id = s.boq_item_id "
                             "WHERE s.document_id = ? ORDER BY b.code", (did,)).fetchall()
    revs = D.revisions(db, did)
    ents, reps = _approvers(db)
    return render_template("documents/view.html", p=p, doc=doc, link=link, revs=revs, users=users, ents=ents, reps=reps,
                           next_rev=(revs[0]["rev_no"] + 1) if revs else 0, scope_items=scope_items, **_ctx(db))


def _back(pid, did, anchor=""):
    return redirect(url_for("documents.view", pid=pid, did=did) + anchor)


@bp.post("/projects/<int:pid>/documents/<int:did>/revisions")
@permission_required("documents.manage")
def revision_add(pid, did):
    db, _p = _project(pid)
    try:
        n = D.add_revision(db, pid, did, request.form, g.user["id"])
        flash(_("Revision {n} recorded.", n=n), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, did, "#revisions")


@bp.post("/projects/<int:pid>/documents/<int:did>/revisions/<int:rid>/response")
@permission_required("documents.manage")
def revision_response(pid, did, rid):
    db, _p = _project(pid)
    try:
        D.decide_revision(db, pid, rid, request.form, g.user["id"])
        flash(_("Response recorded."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, did, "#revisions")


@bp.post("/projects/<int:pid>/documents/<int:did>/review")
@permission_required("projects.manage")
def review(pid, did):
    db, _p = _project(pid)
    try:
        D.review_document(db, pid, did, g.user["id"])
        flash(_("Document data reviewed."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return _back(pid, did)
