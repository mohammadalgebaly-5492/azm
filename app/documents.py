"""وثائق المشروع (الدستور، البند 3.1): سجل الوثائق، ومراجعاتها، وحالة اعتماد كل مراجعة كما وردت من المالك أو الاستشاري."""
from . import audit
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .registers import catalog
from .resources import _date

ISSUERS = {"company": "The company", "owner": "Owner", "consultant": "Consultant", "other": "Other party"}
REV_STATUS = {"review": "Under review", "approved": "Approved", "approved_notes": "Approved with comments",
              "rejected": "Rejected"}
DRAWING_TYPES = ("DRW", "SHD")   # المخططات والمخططات التنفيذية
SPEC_TYPES = ("SPC",)


def documents(db, pid, doc_type=None):
    """وثائق المشروع مع آخر مراجعة لكل وثيقة."""
    sql = ("SELECT d.*, r.rev_no, r.status AS rev_status, r.rev_date, w.code AS wbs_code, b.code AS item_code "
           "FROM documents d LEFT JOIN document_revisions r ON r.id = "
           "(SELECT x.id FROM document_revisions x WHERE x.document_id = d.id ORDER BY x.rev_no DESC LIMIT 1) "
           "LEFT JOIN wbs_nodes w ON w.id = d.wbs_id LEFT JOIN boq_items b ON b.id = d.boq_item_id WHERE d.project_id = ?")
    args = [pid]
    if doc_type:
        sql += " AND d.doc_type = ?"
        args.append(doc_type)
    return db.execute(sql + " ORDER BY d.code", args).fetchall()


def document(db, pid, did):
    return db.execute("SELECT * FROM documents WHERE id = ? AND project_id = ?", (did, pid)).fetchone()


def revisions(db, did):
    return db.execute("SELECT r.*, e.name AS entity_name, p.full_name AS person_name FROM document_revisions r "
                      "LEFT JOIN entities e ON e.id = r.approver_entity_id "
                      "LEFT JOIN entity_people p ON p.id = r.approver_person_id "
                      "WHERE r.document_id = ? ORDER BY r.rev_no DESC", (did,)).fetchall()


def _link(db, pid, raw):
    """«قسم أو بند مرتبط» من قائمة واحدة: wbs-<id> أو item-<id>."""
    raw = str(raw or "")
    kind, _sep, num = raw.partition("-")
    if not raw:
        return None, None
    if num.isdigit() and kind == "wbs" and db.execute("SELECT 1 FROM wbs_nodes WHERE id = ? AND project_id = ?",
                                                      (int(num), pid)).fetchone():
        return int(num), None
    if num.isdigit() and kind == "item" and db.execute("SELECT 1 FROM boq_items WHERE id = ? AND project_id = ?",
                                                       (int(num), pid)).fetchone():
        return None, int(num)
    raise AuthError(_("Choose the section or item from this project."))


def _clean_document(db, pid, form, new=True):
    d = {"title": (form.get("title") or "").strip(), "issuer": form.get("issuer") or "",
         "issuer_ref": (form.get("issuer_ref") or "").strip() or None,
         "issued_on": _date(form.get("issued_on"), _("the issue date")), "summary": (form.get("summary") or "").strip() or None}
    if len(d["title"]) < 3:
        raise AuthError(_("Enter the document title."))
    if d["issuer"] not in ISSUERS:
        raise AuthError(_("Choose who issued the document."))
    d["wbs_id"], d["boq_item_id"] = _link(db, pid, form.get("link"))
    if new:
        d["doc_type"] = form.get("doc_type") or ""
        if d["doc_type"] not in {r["code"] for r in catalog(db, "doc_type", active_only=True)}:
            raise AuthError(_("Choose the document type."))
    return d


def _clean_revision(db, form, last_no=None):
    raw = str(form.get("rev_no") if form.get("rev_no") not in (None, "") else (0 if last_no is None else last_no + 1))
    if not raw.isdigit():
        raise AuthError(_("Enter the revision number as a whole number."))
    r = {"rev_no": int(raw), "status": form.get("status") or "review",
         "notes": (form.get("notes") or "").strip() or None}
    if last_no is not None and r["rev_no"] <= last_no:
        raise AuthError(_("The new revision number must be higher than {n}.", n=last_no))
    if r["status"] not in REV_STATUS:
        raise AuthError(_("Choose the approval status."))
    r.update(_decision(db, form, r["status"], r["notes"]))
    return r


def _decision(db, form, status, notes):
    """الجهة المعتمِدة وممثلها وتاريخ الاعتماد. الاعتماد بملاحظات والرفض يحتاجان الملاحظات."""
    ent, person = str(form.get("approver_entity_id") or ""), str(form.get("approver_person_id") or "")
    out = {"approver_entity_id": int(ent) if ent.isdigit() else None,
           "approver_person_id": int(person) if person.isdigit() else None,
           "approved_on": _date(form.get("approved_on"), _("the approval date"), required=False)}
    if out["approver_entity_id"] and not db.execute("SELECT 1 FROM entities WHERE id = ?",
                                                    (out["approver_entity_id"],)).fetchone():
        raise AuthError(_("Choose the approving entity."))
    if out["approver_person_id"] and not db.execute("SELECT 1 FROM entity_people WHERE id = ? AND entity_id = ?",
                                                    (out["approver_person_id"], out["approver_entity_id"] or 0)).fetchone():
        raise AuthError(_("The representative must belong to the approving entity."))
    if status in ("approved_notes", "rejected") and not notes:
        raise AuthError(_("Write the approval notes."))
    if status == "review":
        out = {"approver_entity_id": None, "approver_person_id": None, "approved_on": None}
    return out


def create_document(db, pid, form, actor_id) -> tuple[int, str]:
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    d = _clean_document(db, pid, form)
    r = _clean_revision(db, form)
    counter = "doc-%d-%s" % (pid, d["doc_type"])
    with tx(db):
        code = f"{p['code']}-DOC-{d['doc_type']}-{next_counter(db, counter):04d}"
        did = db.execute(f"INSERT INTO documents(project_id, code, {', '.join(d)}, created_at, created_by) "
                         f"VALUES (?, ?, {', '.join('?' for _ in d)}, ?, ?) RETURNING id",
                         (pid, code, *d.values(), utcnow(), actor_id)).fetchone()[0]
        _insert_revision(db, did, r, d["issued_on"], actor_id)
        audit.log(db, actor_id, "document_added", "project", pid, pid, code=code, title=d["title"])
    return did, code


def _insert_revision(db, did, r, rev_date, actor_id):
    decided = r["status"] != "review"
    db.execute("INSERT INTO document_revisions(document_id, rev_no, rev_date, status, approver_entity_id, approver_person_id, "
               "approved_on, notes, created_at, created_by, decided_at, decided_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (did, r["rev_no"], rev_date, r["status"], r["approver_entity_id"], r["approver_person_id"], r["approved_on"],
                r["notes"], utcnow(), actor_id, utcnow() if decided else None, actor_id if decided else None))


def update_document(db, pid, did, form, actor_id):
    cur = document(db, pid, did)
    if cur is None:
        raise AuthError(_("This document doesn't exist."))
    d = _clean_document(db, pid, form, new=False)
    changes = {k: v for k, v in d.items() if (str(cur[k])[:10] if k == "issued_on" else cur[k]) != v}
    if not changes:
        return
    with tx(db):
        # تعديل بيانات وثيقة رُوجعت يعيدها للمراجعة
        db.execute(f"UPDATE documents SET {', '.join(f'{k} = ?' for k in changes)}, reviewed_at = NULL, reviewed_by = NULL "
                   f"WHERE id = ?", (*changes.values(), did))
        audit.log(db, actor_id, "document_updated", "project", pid, pid, code=cur["code"],
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items() if k not in ("wbs_id", "boq_item_id")})


def add_revision(db, pid, did, form, actor_id) -> int:
    cur = document(db, pid, did)
    if cur is None:
        raise AuthError(_("This document doesn't exist."))
    last = db.execute("SELECT MAX(rev_no) FROM document_revisions WHERE document_id = ?", (did,)).fetchone()[0]
    r = _clean_revision(db, form, last)
    rev_date = _date(form.get("rev_date"), _("the revision date"))
    with tx(db):
        _insert_revision(db, did, r, rev_date, actor_id)
        audit.log(db, actor_id, "document_revised", "project", pid, pid, code=cur["code"], number=r["rev_no"])
    return r["rev_no"]


def decide_revision(db, pid, rid, form, actor_id):
    """يسجل رد المالك أو الاستشاري على مراجعة قيد المراجعة. الرد لا يُعدَّل بعد تسجيله؛ التغيير بمراجعة جديدة."""
    r = db.execute("SELECT r.*, d.code FROM document_revisions r JOIN documents d ON d.id = r.document_id "
                   "WHERE r.id = ? AND d.project_id = ?", (rid, pid)).fetchone()
    if r is None or r["status"] != "review":
        raise AuthError(_("Only a revision under review can get a response."))
    status, notes = form.get("status") or "", (form.get("notes") or "").strip() or None
    if status not in REV_STATUS or status == "review":
        raise AuthError(_("Choose the approval status."))
    dec = _decision(db, form, status, notes)
    with tx(db):
        db.execute("UPDATE document_revisions SET status = ?, approver_entity_id = ?, approver_person_id = ?, approved_on = ?, "
                   "notes = ?, decided_at = ?, decided_by = ? WHERE id = ?",
                   (status, dec["approver_entity_id"], dec["approver_person_id"], dec["approved_on"], notes, utcnow(),
                    actor_id, rid))
        audit.log(db, actor_id, "document_response", "project", pid, pid, code=r["code"], number=r["rev_no"], status=status)


def review_document(db, pid, did, actor_id):
    """مراجعة مهندس تحكم تكلفة لاكتمال بيانات الوثيقة. من سجّلها لا يراجعها."""
    cur = document(db, pid, did)
    if cur is None or cur["reviewed_at"]:
        raise AuthError(_("This document is already reviewed."))
    if cur["created_by"] == actor_id:
        raise AuthError(_("Whoever records a document can't review it."))
    with tx(db):
        db.execute("UPDATE documents SET reviewed_at = ?, reviewed_by = ? WHERE id = ?", (utcnow(), actor_id, did))
        audit.log(db, actor_id, "document_reviewed", "project", pid, pid, code=cur["code"])
