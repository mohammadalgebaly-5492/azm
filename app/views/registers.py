"""شاشات السجلات المشتركة: الجهات وأشخاصها، والأدلة، وأطراف كل مشروع."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import registers as R
from ..auth import AuthError, permission_required
from ..db import get_db
from ..i18n import _

bp = Blueprint("registers", __name__)


def _entity_or_404(db, eid):
    e = R.entity(db, eid)
    if e is None:
        abort(404)
    return e


# ---------- الجهات ----------

@bp.get("/registers/entities")
@permission_required("registers.manage")
def entities():
    kind = request.args.get("kind", "")
    kind = kind if kind in R.ENTITY_KINDS else ""
    q = request.args.get("q", "").strip()
    return render_template("registers/entities.html", rows=R.entities(get_db(), kind or None, q), kind=kind, q=q,
                           KINDS=R.ENTITY_KINDS, APPROVAL=R.APPROVAL)


@bp.route("/registers/entities/new", methods=["GET", "POST"])
@permission_required("registers.manage")
def entity_new():
    db = get_db()
    kind = request.values.get("kind", "owner")
    if kind not in R.ENTITY_KINDS:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            eid, code = R.create_entity(db, kind, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Entity {code} created. Now add its addresses and people.", code=code), "ok")
            return redirect(url_for("registers.entity_edit", eid=eid))
    return render_template("registers/entity_form.html", e=None, kind=kind, form=request.form, error=error,
                           chosen=set(request.form.getlist("specialties")), **_entity_lists(db))


def _entity_lists(db):
    return {"KINDS": R.ENTITY_KINDS, "APPROVAL": R.APPROVAL, "ADDRESS_LABELS": R.ADDRESS_LABELS,
            "specialties": R.catalog(db, "specialty", active_only=True), "label": R.label}


@bp.route("/registers/entities/<int:eid>", methods=["GET", "POST"])
@permission_required("registers.manage")
def entity_edit(eid):
    db = get_db()
    e = _entity_or_404(db, eid)
    error = None
    if request.method == "POST":
        try:
            R.update_entity(db, eid, request.form, g.user["id"])
        except AuthError as ex:
            error = str(ex)
        else:
            flash(_("Entity details saved."), "ok")
            return redirect(url_for("registers.entity_edit", eid=eid))
    form = request.form if error else dict(e)
    chosen = set(request.form.getlist("specialties")) if error else set(R.specialties_of(db, eid))
    projects = db.execute("SELECT id, code, name FROM projects WHERE owner_entity_id = ? OR consultant_entity_id = ? "
                          "ORDER BY code", (eid, eid)).fetchall()
    return render_template("registers/entity_form.html", e=e, kind=e["kind"], form=form, error=error, chosen=chosen,
                           addresses=R.addresses(db, eid), people=R.people(db, eid), projects=projects,
                           spec_names=R.catalog_names(db, "specialty"), **_entity_lists(db))


@bp.post("/registers/entities/<int:eid>/addresses")
@permission_required("registers.manage")
def address_add(eid):
    db = get_db()
    _entity_or_404(db, eid)
    try:
        R.add_address(db, eid, request.form, g.user["id"])
        flash(_("Address added."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("registers.entity_edit", eid=eid) + "#addresses")


@bp.post("/registers/entities/<int:eid>/addresses/<int:aid>/delete")
@permission_required("registers.manage")
def address_remove(eid, aid):
    db = get_db()
    try:
        R.remove_address(db, eid, aid, g.user["id"])
        flash(_("Address removed."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("registers.entity_edit", eid=eid) + "#addresses")


@bp.post("/registers/entities/<int:eid>/people")
@permission_required("registers.manage")
def person_add(eid):
    db = get_db()
    _entity_or_404(db, eid)
    try:
        _pid, code = R.add_person(db, eid, request.form, g.user["id"])
        flash(_("Person {code} added.", code=code), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("registers.entity_edit", eid=eid) + "#people")


@bp.route("/registers/entities/<int:eid>/people/<int:person_id>", methods=["GET", "POST"])
@permission_required("registers.manage")
def person_edit(eid, person_id):
    db = get_db()
    e = _entity_or_404(db, eid)
    person = db.execute("SELECT * FROM entity_people WHERE id = ? AND entity_id = ?", (person_id, eid)).fetchone()
    if person is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            R.update_person(db, eid, person_id, request.form, g.user["id"])
        except AuthError as ex:
            error = str(ex)
        else:
            flash(_("Person details saved."), "ok")
            return redirect(url_for("registers.entity_edit", eid=eid) + "#people")
    return render_template("registers/person_form.html", e=e, person=person, form=request.form if error else dict(person),
                           error=error)


# ---------- الأدلة ----------

@bp.get("/registers/lists")
@permission_required("registers.manage")
def catalogs():
    db = get_db()
    kind = request.args.get("kind", "unit")
    if kind not in R.CATALOGS:
        kind = "unit"
    types = {r["code"]: R.label(r) for r in R.catalog(db, "equipment_type")}
    return render_template("registers/catalogs.html", kind=kind, rows=R.catalog(db, kind), CATALOGS=R.CATALOGS,
                           types=types, active_types=R.catalog(db, "equipment_type", active_only=True),
                           COST_UNITS=R.COST_UNITS, label=R.label, form={})


@bp.post("/registers/lists/<kind>")
@permission_required("registers.manage")
def catalog_add(kind):
    if kind not in R.CATALOGS:
        abort(404)
    try:
        R.add_catalog_item(get_db(), kind, request.form, g.user["id"])
        flash(_("Entry added to the list."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("registers.catalogs", kind=kind))


@bp.route("/registers/lists/item/<int:iid>", methods=["GET", "POST"])
@permission_required("registers.manage")
def catalog_edit(iid):
    db = get_db()
    item = db.execute("SELECT * FROM catalog_items WHERE id = ?", (iid,)).fetchone()
    if item is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            R.update_catalog_item(db, iid, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Entry saved."), "ok")
            return redirect(url_for("registers.catalogs", kind=item["kind"]))
    return render_template("registers/catalog_form.html", item=item, form=request.form if error else dict(item), error=error,
                           CATALOGS=R.CATALOGS, COST_UNITS=R.COST_UNITS, label=R.label,
                           active_types=R.catalog(db, "equipment_type", active_only=True))


@bp.post("/registers/lists/item/<int:iid>/status")
@permission_required("registers.manage")
def catalog_status(iid):
    db = get_db()
    item = db.execute("SELECT kind FROM catalog_items WHERE id = ?", (iid,)).fetchone()
    if item is None:
        abort(404)
    try:
        R.set_catalog_active(db, iid, request.form.get("active") == "1", g.user["id"])
        flash(_("Entry saved."), "ok")
    except AuthError as e:
        flash(str(e), "bad")
    return redirect(url_for("registers.catalogs", kind=item["kind"]))


# ---------- أطراف المشروع ----------

@bp.route("/projects/<int:pid>/parties", methods=["GET", "POST"])
@permission_required("projects.manage")
def project_parties(pid):
    db = get_db()
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            R.set_project_parties(db, pid, request.form, g.user["id"])
        except AuthError as e:
            error = str(e)
        else:
            flash(_("Project parties saved."), "ok")
            return redirect(url_for("main.project", pid=pid) + "#parties")
    groups = {}
    for kind in ("owner", "consultant"):
        groups[kind] = [(ent, R.people(db, ent["id"], active_only=True))
                        for ent in R.entities(db, kind, active_only=True)]
    if error:
        sel = {"owner": request.form.get("owner_entity_id", ""), "consultant": request.form.get("consultant_entity_id", "")}
        picked = {int(x) for k in ("owner_reps", "consultant_reps") for x in request.form.getlist(k) if x.isdigit()}
    else:
        sel = {"owner": str(p["owner_entity_id"] or ""), "consultant": str(p["consultant_entity_id"] or "")}
        picked = {r["id"] for r in R.representatives(db, pid)}
    return render_template("registers/project_parties.html", p=p, groups=groups, sel=sel, picked=picked, error=error,
                           MIN=R.MIN_REPRESENTATIVES)
